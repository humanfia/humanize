//! Wire protocol between the two halves of a session, byte for byte the one
//! `hmz.coganchor.proto` speaks (protocol version 1).
//!
//! A connection carries length-prefixed frames. Each frame pairs a small JSON metadata object
//! with an optional opaque binary body:
//!
//! ```text
//! +---------+----------+---------+------------------+--------------+
//! | u32 LE  | u32 LE   | u64 LE  | meta_len bytes   | remaining    |
//! | payload | meta_len | msg id  | JSON metadata    | binary body  |
//! +---------+----------+---------+------------------+--------------+
//! ```
//!
//! `payload` counts the bytes after the 16-byte header. The frame's kind travels in the
//! metadata as `"k"`, one character, written last. Every exchange shares one `msg id`: `REQ`
//! opens it, either side streams `CHUNK` frames tagged with a [`Stream`] (`"s"`) and marks a
//! direction finished with `END`, and `RSP` or `ERR` closes it. Errors carry the remote errno
//! verbatim, never translated between platforms.
//!
//! A pipe carries the frames as they are. A `tcp://` or `peer://` connection carries them
//! inside TLS ([`crate::tls`]), where the `HELLO` proves a key instead of presenting a token.
//!
//! Strings in the metadata are JSON strings, and a path that is not UTF-8 crosses the wire the
//! way Python's `surrogateescape` spells it: each undecodable byte `0xXX` as the lone surrogate
//! `\udcXX`. [`json`] carries such strings in Rust as UTF-8 with each of those bytes stood in
//! for by a private-use character, and [`json::to_os`] / [`json::from_os`] convert at the
//! operating system's boundary.

pub mod json;
pub mod paths;
pub mod wire;

use std::fmt;
use std::io;

use serde_json::{Map, Value};

pub use paths::{path_key, path_spellings, path_within, rewrite_path_prefix, spelled_twice};
pub use wire::{Channel, read_frame, write_frame};

/// The version both halves must speak.
pub const PROTOCOL_VERSION: u64 = 1;

/// Body size used when splitting large payloads into stream chunks.
pub const CHUNK_SIZE: usize = 1 << 16;

/// Hard ceiling on a single frame, to bound memory use on malformed input.
pub const MAX_FRAME_BYTES: usize = 1 << 30;

/// The size of a frame's fixed header.
pub const HEADER_BYTES: usize = 16;

/// The platforms a target may say it runs, as `sys.platform` spells them.
pub const PLATFORMS: [&str; 2] = ["darwin", "linux"];

/// The platforms whose filesystem does not tell `A` from `a`.
pub const CASE_INSENSITIVE: [&str; 1] = ["darwin"];

/// A frame's metadata: a JSON object, in the order its keys were written.
pub type Meta = Map<String, Value>;

/// Frame kind, spelled on the wire as one character in `"k"`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Kind {
    Req,
    Rsp,
    Err,
    Chunk,
    End,
}

impl Kind {
    /// The character the wire spells this kind with.
    pub fn as_str(self) -> &'static str {
        match self {
            Kind::Req => "q",
            Kind::Rsp => "r",
            Kind::Err => "e",
            Kind::Chunk => "c",
            Kind::End => "z",
        }
    }

    /// The kind a wire spelling names, if any.
    pub fn parse(said: &str) -> Option<Kind> {
        Some(match said {
            "q" => Kind::Req,
            "r" => Kind::Rsp,
            "e" => Kind::Err,
            "c" => Kind::Chunk,
            "z" => Kind::End,
            _ => return None,
        })
    }
}

/// The operations a serving half understands, spelled on the wire in `"op"`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Op {
    Hello,
    Listdir,
    Stat,
    Read,
    Write,
    Mkdir,
    Rmdir,
    Unlink,
    Rename,
    Symlink,
    Link,
    Readlink,
    Chmod,
    Truncate,
    Utime,
    Exec,
    Signal,
    Resize,
    Hold,
    Connect,
}

impl Op {
    /// Every operation, in the order `proto.py` declares them.
    pub const ALL: [Op; 20] = [
        Op::Hello,
        Op::Listdir,
        Op::Stat,
        Op::Read,
        Op::Write,
        Op::Mkdir,
        Op::Rmdir,
        Op::Unlink,
        Op::Rename,
        Op::Symlink,
        Op::Link,
        Op::Readlink,
        Op::Chmod,
        Op::Truncate,
        Op::Utime,
        Op::Exec,
        Op::Signal,
        Op::Resize,
        Op::Hold,
        Op::Connect,
    ];

    /// The name the wire spells this operation with.
    pub fn as_str(self) -> &'static str {
        match self {
            Op::Hello => "hello",
            Op::Listdir => "listdir",
            Op::Stat => "stat",
            Op::Read => "read",
            Op::Write => "write",
            Op::Mkdir => "mkdir",
            Op::Rmdir => "rmdir",
            Op::Unlink => "unlink",
            Op::Rename => "rename",
            Op::Symlink => "symlink",
            Op::Link => "link",
            Op::Readlink => "readlink",
            Op::Chmod => "chmod",
            Op::Truncate => "truncate",
            Op::Utime => "utime",
            Op::Exec => "exec",
            Op::Signal => "signal",
            Op::Resize => "resize",
            Op::Hold => "hold",
            Op::Connect => "connect",
        }
    }

    /// The operation a wire spelling names, or `None` for one this build does not know.
    pub fn parse(said: &str) -> Option<Op> {
        Op::ALL.into_iter().find(|op| op.as_str() == said)
    }
}

/// Which byte stream a `CHUNK` or `END` belongs to.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
#[repr(u8)]
pub enum Stream {
    Stdin = 0,
    Stdout = 1,
    Stderr = 2,
    Data = 3,
}

impl Stream {
    /// The stream a wire number names.
    pub fn from_number(number: u64) -> Option<Stream> {
        Some(match number {
            0 => Stream::Stdin,
            1 => Stream::Stdout,
            2 => Stream::Stderr,
            3 => Stream::Data,
            _ => return None,
        })
    }
}

/// A malformed frame or an unexpected end of stream.
#[derive(Debug, thiserror::Error)]
#[error("{0}")]
pub struct ProtocolError(pub String);

impl From<ProtocolError> for io::Error {
    fn from(error: ProtocolError) -> io::Error {
        io::Error::new(io::ErrorKind::InvalidData, error.0)
    }
}

/// An error that happened on the other machine, carrying that machine's errno verbatim.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RemoteError {
    pub errno: i32,
    pub strerror: String,
    pub filename: Option<String>,
}

impl RemoteError {
    /// An error with this errno and the local description of it.
    pub fn errno(errno: i32) -> RemoteError {
        RemoteError {
            errno,
            strerror: io::Error::from_raw_os_error(errno).to_string_without_code(),
            filename: None,
        }
    }

    /// An error with this errno and message.
    pub fn new(errno: i32, strerror: impl Into<String>) -> RemoteError {
        RemoteError {
            errno,
            strerror: strerror.into(),
            filename: None,
        }
    }

    /// The same error, naming the file it concerns.
    pub fn with_filename(mut self, filename: impl Into<String>) -> RemoteError {
        self.filename = Some(filename.into());
        self
    }

    /// An `io::Error` as the wire carries it: its errno (`EIO` when it has none) and message.
    pub fn from_io(error: &io::Error, filename: Option<&str>) -> RemoteError {
        let errno = error.raw_os_error().unwrap_or(libc::EIO);
        let strerror = match error.raw_os_error() {
            Some(_) => error.to_string_without_code(),
            None => error.to_string(),
        };
        RemoteError {
            errno,
            strerror: if strerror.is_empty() {
                "remote error".into()
            } else {
                strerror
            },
            filename: filename.map(str::to_owned),
        }
    }

    /// The error an `ERR` frame's metadata describes.
    pub fn from_meta(meta: &Meta) -> RemoteError {
        RemoteError {
            errno: meta.get("errno").and_then(Value::as_i64).unwrap_or(0) as i32,
            strerror: meta
                .get("strerror")
                .and_then(Value::as_str)
                .unwrap_or("remote error")
                .to_owned(),
            filename: meta
                .get("filename")
                .and_then(Value::as_str)
                .map(str::to_owned),
        }
    }

    /// The metadata of the `ERR` frame carrying this error.
    pub fn to_meta(&self) -> Meta {
        let mut meta = Meta::new();
        meta.insert("errno".into(), Value::from(self.errno));
        meta.insert("strerror".into(), Value::from(self.strerror.clone()));
        meta.insert(
            "filename".into(),
            self.filename.clone().map_or(Value::Null, Value::from),
        );
        meta
    }

    /// This error as a local `io::Error` carrying the same raw errno, so that a caller
    /// handing it on to a traced process (or matching on it) gets the target's own number.
    /// The message is the local description of that number; [`RemoteError`]'s `Display`
    /// keeps the remote one.
    pub fn to_io(&self) -> io::Error {
        io::Error::from_raw_os_error(self.errno)
    }
}

impl fmt::Display for RemoteError {
    /// Spelled as Python spells an `OSError`: `[Errno N] message: 'file'`.
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "[Errno {}] {}", self.errno, self.strerror)?;
        if let Some(filename) = &self.filename {
            write!(f, ": '{filename}'")?;
        }
        Ok(())
    }
}

impl std::error::Error for RemoteError {}

trait WithoutCode {
    fn to_string_without_code(&self) -> String;
}

impl WithoutCode for io::Error {
    /// The message alone, as `strerror` gives it, without Rust's ` (os error N)` suffix.
    fn to_string_without_code(&self) -> String {
        let full = self.to_string();
        match full.rfind(" (os error ") {
            Some(cut) => full[..cut].to_owned(),
            None => full,
        }
    }
}

/// One protocol frame.
#[derive(Clone, Debug, PartialEq)]
pub struct Frame {
    pub kind: Kind,
    pub id: u64,
    pub meta: Meta,
    pub body: Vec<u8>,
}

impl Frame {
    /// A request opening exchange `id`.
    pub fn request(id: u64, op: Op, mut meta: Meta, body: Vec<u8>) -> Frame {
        let mut first = Meta::new();
        first.insert("op".into(), Value::from(op.as_str()));
        first.append(&mut meta);
        Frame {
            kind: Kind::Req,
            id,
            meta: first,
            body,
        }
    }

    /// A successful reply closing exchange `id`.
    pub fn reply(id: u64, meta: Meta, body: Vec<u8>) -> Frame {
        Frame {
            kind: Kind::Rsp,
            id,
            meta,
            body,
        }
    }

    /// A failed reply closing exchange `id`.
    pub fn error(id: u64, error: &RemoteError) -> Frame {
        Frame {
            kind: Kind::Err,
            id,
            meta: error.to_meta(),
            body: Vec::new(),
        }
    }

    /// A piece of `stream` on exchange `id`.
    pub fn chunk(id: u64, stream: Stream, body: Vec<u8>) -> Frame {
        let mut meta = Meta::new();
        meta.insert("s".into(), Value::from(stream as u8));
        Frame {
            kind: Kind::Chunk,
            id,
            meta,
            body,
        }
    }

    /// The end of `stream` on exchange `id`.
    pub fn end(id: u64, stream: Stream) -> Frame {
        let mut meta = Meta::new();
        meta.insert("s".into(), Value::from(stream as u8));
        Frame {
            kind: Kind::End,
            id,
            meta,
            body: Vec::new(),
        }
    }

    /// The requested operation, or `None` if absent or unknown to this build.
    pub fn op(&self) -> Option<Op> {
        self.meta
            .get("op")
            .and_then(Value::as_str)
            .and_then(Op::parse)
    }

    /// The stream a `CHUNK` or `END` names, `Data` when it names none.
    pub fn stream(&self) -> Stream {
        self.meta
            .get("s")
            .and_then(Value::as_u64)
            .and_then(Stream::from_number)
            .unwrap_or(Stream::Data)
    }

    /// The frame as bytes on the wire.
    pub fn encode(&self) -> Vec<u8> {
        let mut meta = self.meta.clone();
        meta.shift_remove("k");
        meta.insert("k".into(), Value::from(self.kind.as_str()));
        let blob = json::encode(&Value::Object(meta));
        let mut out = Vec::with_capacity(HEADER_BYTES + blob.len() + self.body.len());
        out.extend_from_slice(&((blob.len() + self.body.len()) as u32).to_le_bytes());
        out.extend_from_slice(&(blob.len() as u32).to_le_bytes());
        out.extend_from_slice(&self.id.to_le_bytes());
        out.extend_from_slice(&blob);
        out.extend_from_slice(&self.body);
        out
    }

    /// The frame a header and its payload spell.
    pub fn decode(header: &[u8; HEADER_BYTES], payload: Vec<u8>) -> Result<Frame, ProtocolError> {
        let (_, meta_len, id) = parse_header(header)?;
        let mut payload = payload;
        let body = payload.split_off(meta_len);
        let value = json::decode(&payload)
            .map_err(|error| ProtocolError(format!("malformed frame metadata: {error}")))?;
        let Value::Object(mut meta) = value else {
            return Err(ProtocolError("frame metadata is not an object".into()));
        };
        let kind = match meta.shift_remove("k") {
            Some(Value::String(said)) => Kind::parse(&said),
            _ => None,
        }
        .ok_or_else(|| ProtocolError("invalid frame kind".into()))?;
        Ok(Frame {
            kind,
            id,
            meta,
            body,
        })
    }
}

/// The payload length, metadata length and message id a header says, checked for plausibility.
pub fn parse_header(header: &[u8; HEADER_BYTES]) -> Result<(usize, usize, u64), ProtocolError> {
    let payload = u32::from_le_bytes(header[0..4].try_into().unwrap()) as usize;
    let meta = u32::from_le_bytes(header[4..8].try_into().unwrap()) as usize;
    let id = u64::from_le_bytes(header[8..16].try_into().unwrap());
    if meta > payload || payload > MAX_FRAME_BYTES {
        return Err(ProtocolError(format!(
            "implausible frame header: {payload}/{meta}"
        )));
    }
    Ok((payload, meta, id))
}

/// The platform names a target's `HELLO` reply answers to.
pub fn hello_capabilities(said: &Meta) -> Vec<&'static str> {
    let platform = said.get("platform").and_then(Value::as_str).unwrap_or("");
    PLATFORMS
        .into_iter()
        .filter(|name| *name == platform)
        .collect()
}

/// Whether a target said at the handshake that it can fence the commands it runs.
pub fn hello_fences(said: &Meta, net: bool) -> bool {
    let Some(Value::Object(able)) = said.get("fence") else {
        return false;
    };
    able.get("fs") == Some(&Value::Bool(true))
        && (!net || able.get("net") == Some(&Value::Bool(true)))
}

/// This machine's platform as `sys.platform` spells it.
pub fn this_platform() -> &'static str {
    if cfg!(target_os = "macos") {
        "darwin"
    } else {
        "linux"
    }
}

/// Builds a `Meta` from `key => value` pairs.
#[macro_export]
macro_rules! meta {
    () => { $crate::proto::Meta::new() };
    ($($key:expr => $value:expr),+ $(,)?) => {{
        let mut meta = $crate::proto::Meta::new();
        $( meta.insert(($key).into(), ::serde_json::Value::from($value)); )+
        meta
    }};
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Bytes `proto.py` produced for these frames (checked against Python 3.12).
    #[test]
    fn encodes_as_python_does() {
        let frame = Frame::request(7, Op::Stat, meta! {"path" => "/w/f"}, Vec::new());
        let blob = frame.encode();
        let meta = br#"{"op":"stat","path":"/w/f","k":"q"}"#;
        assert_eq!(&blob[0..4], &(meta.len() as u32).to_le_bytes());
        assert_eq!(&blob[4..8], &(meta.len() as u32).to_le_bytes());
        assert_eq!(&blob[8..16], &7u64.to_le_bytes());
        assert_eq!(&blob[16..], meta);
    }

    #[test]
    fn round_trips() {
        let frame = Frame::chunk(9, Stream::Stderr, b"oops".to_vec());
        let blob = frame.encode();
        let header: [u8; 16] = blob[..16].try_into().unwrap();
        assert_eq!(Frame::decode(&header, blob[16..].to_vec()).unwrap(), frame);
    }

    #[test]
    fn errors_spell_their_errno() {
        let error = RemoteError::errno(libc::ENOENT).with_filename("/x");
        let back = RemoteError::from_meta(&error.to_meta());
        assert_eq!(back, error);
        assert_eq!(back.to_io().raw_os_error(), Some(libc::ENOENT));
        assert_eq!(back.to_io().kind(), io::ErrorKind::NotFound);
    }

    #[test]
    fn unknown_ops_are_none() {
        let frame = Frame::request(1, Op::Hello, Meta::new(), Vec::new());
        assert_eq!(frame.op(), Some(Op::Hello));
        let mut odd = frame.clone();
        odd.meta.insert("op".into(), Value::from("teleport"));
        assert_eq!(odd.op(), None);
    }

    #[test]
    fn fences_are_read_from_hello() {
        let said = meta! {"fence" => serde_json::json!({"fs": true, "net": false})};
        assert!(hello_fences(&said, false));
        assert!(!hello_fences(&said, true));
        assert!(!hello_fences(&Meta::new(), false));
    }
}

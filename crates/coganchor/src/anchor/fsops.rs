//! The filesystem operations, carried out here on real paths. Port of
//! `hmz.coganchor.serve.fsops`. [Unit 1]
//!
//! Each takes a request's metadata, resolves its virtual paths through the [`ExportTable`],
//! and returns the reply's metadata or this machine's exact errno. An operating-system error
//! names the real path it concerns, as Python's `OSError.filename` does; a request that is
//! itself wrong (a missing key, a value of the wrong type, a relative path) is `EINVAL`
//! "malformed {op} request: ...", as the Python server's `KeyError`/`TypeError`/`ValueError`
//! branch spells it.

use std::ffi::{CString, OsString};
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::os::unix::ffi::{OsStrExt, OsStringExt};
use std::os::unix::fs::{DirBuilderExt, MetadataExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::Value;

use crate::anchor::{ExportTable, Outbox, Sink};
use crate::meta;
use crate::proto::json::{from_os, to_os};
use crate::proto::{CHUNK_SIZE, Frame, Meta, Op, RemoteError, Stream};

/// Why an operation failed, before it is spelled for the wire.
enum Fail {
    /// The operating system refused; carried verbatim.
    Os(RemoteError),
    /// The request itself is wrong: what is wrong with it.
    Malformed(String),
}

impl Fail {
    fn into_remote(self, op: Op) -> RemoteError {
        match self {
            Fail::Os(error) => error,
            Fail::Malformed(why) => RemoteError::new(
                libc::EINVAL,
                format!("malformed {} request: {why}", op.as_str()),
            ),
        }
    }
}

impl From<RemoteError> for Fail {
    fn from(error: RemoteError) -> Fail {
        Fail::Os(error)
    }
}

/// An `io::Error` as the wire carries it, naming `path`.
fn os(error: io::Error, path: &Path) -> Fail {
    Fail::Os(RemoteError::from_io(
        &error,
        Some(&from_os(path.as_os_str())),
    ))
}

/// Rename `src` to `dst` in one step, failing with `EEXIST` where `dst` is already there.
fn rename_noreplace(src: &Path, dst: &Path) -> Result<(), Fail> {
    let (from, to) = (c_path(src)?, c_path(dst)?);
    #[cfg(target_os = "macos")]
    let status = unsafe { libc::renamex_np(from.as_ptr(), to.as_ptr(), libc::RENAME_EXCL) };
    #[cfg(not(target_os = "macos"))]
    let status = unsafe {
        libc::syscall(
            libc::SYS_renameat2,
            libc::AT_FDCWD,
            from.as_ptr(),
            libc::AT_FDCWD,
            to.as_ptr(),
            libc::RENAME_NOREPLACE,
        )
    };
    if status != 0 {
        return Err(last(src));
    }
    Ok(())
}

/// The last OS error, naming `path`.
fn last(path: &Path) -> Fail {
    os(io::Error::last_os_error(), path)
}

/// Reading a request's fields the way the Python server's lambdas do.
struct Request<'a>(&'a Meta);

impl Request<'_> {
    fn field(&self, key: &str) -> Result<&Value, Fail> {
        // `str(KeyError('path'))` is `'path'`.
        self.0
            .get(key)
            .ok_or_else(|| Fail::Malformed(format!("'{key}'")))
    }

    fn str(&self, key: &str) -> Result<&str, Fail> {
        let said = self
            .field(key)?
            .as_str()
            .ok_or_else(|| Fail::Malformed(format!("{key} must be a string")))?;
        if said.contains('\0') {
            return Err(Fail::Malformed("embedded null byte".into()));
        }
        Ok(said)
    }

    fn int(&self, key: &str) -> Result<i64, Fail> {
        int(self.field(key)?, key)
    }

    /// An integer that may be absent, falling back to `default`; `null` is not one.
    fn int_or(&self, key: &str, default: i64) -> Result<i64, Fail> {
        self.0.get(key).map_or(Ok(default), |v| int(v, key))
    }

    /// An integer that may be absent or `null`.
    fn maybe_int(&self, key: &str) -> Result<Option<i64>, Fail> {
        match self.0.get(key) {
            None | Some(Value::Null) => Ok(None),
            Some(v) => int(v, key).map(Some),
        }
    }

    /// A flag, read for its truth as Python reads it.
    fn flag(&self, key: &str) -> bool {
        match self.0.get(key) {
            None | Some(Value::Null) => false,
            Some(Value::Bool(b)) => *b,
            Some(Value::Number(n)) => n.as_f64() != Some(0.0),
            Some(Value::String(s)) => !s.is_empty(),
            Some(Value::Array(a)) => !a.is_empty(),
            Some(Value::Object(o)) => !o.is_empty(),
        }
    }

    /// The real path a field names.
    fn real(&self, key: &str, exports: &ExportTable) -> Result<PathBuf, Fail> {
        // `resolve`'s one `EINVAL` is a relative path, which is the request's fault.
        exports
            .resolve(self.str(key)?)
            .map_err(|error| match error.errno {
                libc::EINVAL => Fail::Malformed(error.strerror),
                _ => Fail::Os(error),
            })
    }
}

fn int(value: &Value, key: &str) -> Result<i64, Fail> {
    match value {
        Value::Bool(b) => Ok(i64::from(*b)),
        _ => value
            .as_i64()
            .ok_or_else(|| Fail::Malformed(format!("{key} must be an integer"))),
    }
}

fn c_path(path: &Path) -> Result<CString, Fail> {
    CString::new(path.as_os_str().as_bytes())
        .map_err(|_| Fail::Malformed("embedded null byte".into()))
}

/// Carries out one short operation (everything but `read`, `write`, `exec`, `signal`,
/// `connect` and `hello`), returning the reply's metadata.
pub fn run(op: Op, request: &Meta, exports: &ExportTable) -> Result<Meta, RemoteError> {
    short(op, &Request(request), exports).map_err(|fail| fail.into_remote(op))
}

fn short(op: Op, m: &Request, t: &ExportTable) -> Result<Meta, Fail> {
    match op {
        Op::Stat => describe(&m.real("path", t)?, None),
        Op::Listdir => listdir(&m.real("path", t)?),
        Op::Mkdir => {
            let real = m.real("path", t)?;
            let mode = m.int_or("mode", 0o777)? as u32;
            if m.flag("parents") {
                makedirs(&real, mode)?;
            } else {
                fs::DirBuilder::new()
                    .mode(mode)
                    .create(&real)
                    .map_err(|e| os(e, &real))?;
            }
            Ok(Meta::new())
        }
        Op::Rmdir => {
            let real = m.real("path", t)?;
            fs::remove_dir(&real).map_err(|e| os(e, &real))?;
            Ok(Meta::new())
        }
        Op::Unlink => {
            let real = m.real("path", t)?;
            fs::remove_file(&real).map_err(|e| os(e, &real))?;
            Ok(Meta::new())
        }
        Op::Rename => {
            let (src, dst) = (m.real("src", t)?, m.real("dst", t)?);
            // Only a `replace` that is there and false asks for `RENAME_NOREPLACE`.
            if m.0.contains_key("replace") && !m.flag("replace") {
                rename_noreplace(&src, &dst)?;
            } else {
                fs::rename(&src, &dst).map_err(|e| os(e, &src))?;
            }
            Ok(Meta::new())
        }
        Op::Symlink => {
            let target = m.str("target")?;
            let real = m.real("path", t)?;
            std::os::unix::fs::symlink(to_os(target), &real)
                .map_err(|e| os(e, Path::new(&to_os(target))))?;
            Ok(Meta::new())
        }
        Op::Link => {
            let (src, dst) = (m.real("src", t)?, m.real("dst", t)?);
            let (c_src, c_dst) = (c_path(&src)?, c_path(&dst)?);
            // As `os.link` does: a link to a symbolic link is a link to what it names.
            let done = unsafe {
                libc::linkat(
                    libc::AT_FDCWD,
                    c_src.as_ptr(),
                    libc::AT_FDCWD,
                    c_dst.as_ptr(),
                    libc::AT_SYMLINK_FOLLOW,
                )
            };
            if done != 0 {
                return Err(last(&src));
            }
            Ok(Meta::new())
        }
        Op::Readlink => {
            let real = m.real("path", t)?;
            let target = fs::read_link(&real).map_err(|e| os(e, &real))?;
            Ok(meta! {"target" => from_os(target.as_os_str())})
        }
        Op::Chmod => {
            let real = m.real("path", t)?;
            let mode = (m.int("mode")? as u32) & 0o7777;
            fs::set_permissions(&real, fs::Permissions::from_mode(mode))
                .map_err(|e| os(e, &real))?;
            Ok(Meta::new())
        }
        Op::Truncate => {
            let real = m.real("path", t)?;
            let size = m.int("size")?;
            let path = c_path(&real)?;
            if unsafe { libc::truncate(path.as_ptr(), size as libc::off_t) } != 0 {
                return Err(last(&real));
            }
            Ok(Meta::new())
        }
        Op::Utime => {
            let real = m.real("path", t)?;
            utime(&real, m.maybe_int("atime_ns")?, m.maybe_int("mtime_ns")?)?;
            Ok(Meta::new())
        }
        _ => Err(Fail::Os(RemoteError::new(
            libc::ENOSYS,
            format!("unsupported op {}", op.as_str()),
        ))),
    }
}

/// What a path is, as `stat.S_IS*` sorts the mode a non-following stat gave.
fn kind(info: &fs::Metadata) -> &'static str {
    let is = info.file_type();
    if is.is_dir() {
        "dir"
    } else if is.is_symlink() {
        "link"
    } else if is.is_file() {
        "file"
    } else {
        "other"
    }
}

fn mtime_ns(info: &fs::Metadata) -> i64 {
    info.mtime() * 1_000_000_000 + info.mtime_nsec()
}

/// The wire's description of one path, not following a final symbolic link: `{kind, mode,
/// size, mtime_ns}`, with `name` for a directory entry and `target` for a link.
fn describe(real: &Path, name: Option<String>) -> Result<Meta, Fail> {
    let info = fs::symlink_metadata(real).map_err(|e| os(e, real))?;
    let mut entry = meta! {
        "kind" => kind(&info),
        "mode" => info.mode(),
        "size" => info.size(),
        "mtime_ns" => mtime_ns(&info),
    };
    if let Some(name) = name {
        entry.insert("name".into(), Value::from(name));
    }
    if info.file_type().is_symlink() {
        let target = fs::read_link(real).map_err(|e| os(e, real))?;
        entry.insert("target".into(), Value::from(from_os(target.as_os_str())));
    }
    Ok(entry)
}

/// A whole directory in one reply, in the order the directory gives it, with what a client
/// needs to answer `stat` and `getdents` from its mirror without asking again.
fn listdir(real: &Path) -> Result<Meta, Fail> {
    let mut entries = Vec::new();
    for item in fs::read_dir(real).map_err(|e| os(e, real))? {
        let item = item.map_err(|e| os(e, real))?;
        // An entry that vanished between reading the directory and looking at it is skipped.
        if let Ok(entry) = describe(&item.path(), Some(from_os(&item.file_name()))) {
            entries.push(Value::Object(entry));
        }
    }
    let info = fs::metadata(real).map_err(|e| os(e, real))?;
    Ok(meta! {
        "entries" => entries,
        "mode" => info.mode(),
        "mtime_ns" => mtime_ns(&info),
    })
}

/// `os.makedirs(path, mode, exist_ok=True)`: the directories above made as the umask allows,
/// this one with `mode`, and no error if it is already a directory.
fn makedirs(real: &Path, mode: u32) -> Result<(), Fail> {
    if let Some(parent) = real.parent()
        && !parent.as_os_str().is_empty()
        && !parent.exists()
    {
        fs::create_dir_all(parent).map_err(|e| os(e, parent))?;
    }
    match fs::DirBuilder::new().mode(mode).create(real) {
        Ok(()) => Ok(()),
        Err(_) if real.is_dir() => Ok(()),
        Err(error) => Err(os(error, real)),
    }
}

/// Sets a path's times, following links; both `None` is "now", and one `None` keeps that
/// time as it stands.
fn utime(real: &Path, atime_ns: Option<i64>, mtime_ns_said: Option<i64>) -> Result<(), Fail> {
    let path = c_path(real)?;
    let done = if atime_ns.is_none() && mtime_ns_said.is_none() {
        unsafe { libc::utimensat(libc::AT_FDCWD, path.as_ptr(), std::ptr::null(), 0) }
    } else {
        let info = fs::metadata(real).map_err(|e| os(e, real))?;
        let atime = atime_ns.unwrap_or(info.atime() * 1_000_000_000 + info.atime_nsec());
        let mtime = mtime_ns_said.unwrap_or(mtime_ns(&info));
        let times = [timespec(atime), timespec(mtime)];
        unsafe { libc::utimensat(libc::AT_FDCWD, path.as_ptr(), times.as_ptr(), 0) }
    };
    if done != 0 {
        return Err(last(real));
    }
    Ok(())
}

fn timespec(ns: i64) -> libc::timespec {
    libc::timespec {
        tv_sec: ns.div_euclid(1_000_000_000) as libc::time_t,
        tv_nsec: ns.rem_euclid(1_000_000_000) as _,
    }
}

/// `read`: streams the file as `CHUNK`s on `Data`, then replies `{size, mode, mtime_ns}`.
///
/// The reply describes the file as it was when opened, whatever happens to it while it is
/// being sent.
pub fn read(
    id: u64,
    request: &Meta,
    exports: &ExportTable,
    outbox: &dyn Outbox,
) -> Result<(), RemoteError> {
    stream_file(id, &Request(request), exports, outbox).map_err(|fail| fail.into_remote(Op::Read))
}

fn stream_file(id: u64, m: &Request, t: &ExportTable, outbox: &dyn Outbox) -> Result<(), Fail> {
    let real = m.real("path", t)?;
    let mut file = File::open(&real).map_err(|e| os(e, &real))?;
    let info = file.metadata().map_err(|e| os(e, &real))?;
    if info.is_dir() {
        // Python's `open` refuses a directory outright; read(2) would only say so later.
        return Err(os(io::Error::from_raw_os_error(libc::EISDIR), &real));
    }
    // Whole chunks of `CHUNK_SIZE` until the last, as Python's `read(CHUNK_SIZE)` gives them;
    // each buffer sized for what the file is expected to still hold.
    let mut left = info.size();
    loop {
        let want = left.clamp(1, CHUNK_SIZE as u64);
        let mut chunk = Vec::with_capacity(want as usize);
        (&mut file)
            .take(CHUNK_SIZE as u64)
            .read_to_end(&mut chunk)
            .map_err(|e| os(e, &real))?;
        if chunk.is_empty() {
            break;
        }
        let whole = chunk.len() == CHUNK_SIZE;
        left = left.saturating_sub(chunk.len() as u64);
        outbox
            .send(Frame::chunk(id, Stream::Data, chunk))
            .map_err(|e| Fail::Os(RemoteError::new(libc::EIO, e.0)))?;
        if !whole {
            break;
        }
    }
    let reply = meta! {
        "size" => info.size(),
        "mode" => info.mode(),
        "mtime_ns" => mtime_ns(&info),
    };
    let _ = outbox.send(Frame::reply(id, reply, Vec::new()));
    Ok(())
}

/// Distinguishes concurrent writers within one process: `--listen` serves every connection
/// from the same process, so a name built only from the pid would be shared by two sessions
/// writing the same path.
static WRITERS: AtomicU64 = AtomicU64::new(0);

/// `write`: a sink taking the file's content (the request's body first), replying with the
/// written file's `stat` once the client sends `END`.
///
/// Content lands on a sibling temporary file that is renamed over the target, so a torn
/// connection never leaves a half-written file behind. A symbolic link at the target is
/// followed, matching the write the client already made to its own copy.
pub fn write(
    id: u64,
    request: &Meta,
    body: &[u8],
    exports: &ExportTable,
    outbox: Arc<dyn Outbox>,
) -> Result<Box<dyn Sink>, RemoteError> {
    let m = Request(request);
    let mut writer =
        FileWriter::open(&m, exports, id, outbox).map_err(|f| f.into_remote(Op::Write))?;
    if !body.is_empty() {
        writer.feed(Stream::Data, body)?;
    }
    Ok(Box::new(writer))
}

struct FileWriter {
    id: u64,
    real: PathBuf,
    temp: PathBuf,
    mode: Option<i64>,
    file: Option<File>,
    outbox: Arc<dyn Outbox>,
    done: bool,
}

impl FileWriter {
    fn open(
        m: &Request,
        t: &ExportTable,
        id: u64,
        outbox: Arc<dyn Outbox>,
    ) -> Result<FileWriter, Fail> {
        let mut real = m.real("path", t)?;
        let mode = m.maybe_int("mode")?;
        if fs::symlink_metadata(&real).is_ok_and(|i| i.file_type().is_symlink()) {
            real = realpath(&real);
        }
        let parent = match real.parent() {
            Some(p) if !p.as_os_str().is_empty() => p.to_path_buf(),
            _ => PathBuf::from("/"),
        };
        fs::create_dir_all(&parent).map_err(|e| os(e, &parent))?;
        let seq = WRITERS.fetch_add(1, Ordering::Relaxed);
        let mut temp = OsString::from(real.as_os_str());
        temp.push(format!(".humanize-{}-{seq}.tmp", std::process::id()));
        let temp = PathBuf::from(temp);
        let file = File::create(&temp).map_err(|e| os(e, &temp))?;
        Ok(FileWriter {
            id,
            real,
            temp,
            mode,
            file: Some(file),
            outbox,
            done: false,
        })
    }

    fn finish(&mut self) -> Result<Meta, Fail> {
        drop(self.file.take());
        let mode = match self.mode {
            Some(mode) => Some(mode as u32),
            None => fs::metadata(&self.real).ok().map(|i| i.mode()),
        };
        if let Some(mode) = mode {
            fs::set_permissions(&self.temp, fs::Permissions::from_mode(mode & 0o7777))
                .map_err(|e| os(e, &self.temp))?;
        }
        fs::rename(&self.temp, &self.real).map_err(|e| os(e, &self.temp))?;
        describe(&self.real, None)
    }

    fn abort(&mut self) {
        drop(self.file.take());
        let _ = fs::remove_file(&self.temp);
    }
}

impl Sink for FileWriter {
    fn feed(&mut self, _stream: Stream, body: &[u8]) -> Result<(), RemoteError> {
        let Some(file) = self.file.as_mut() else {
            return Ok(());
        };
        file.write_all(body)
            .map_err(|e| RemoteError::from_io(&e, Some(&from_os(self.temp.as_os_str()))))
    }

    fn end(&mut self, _stream: Stream) -> Result<(), RemoteError> {
        if self.done {
            return Ok(());
        }
        self.done = true;
        match self.finish() {
            Ok(reply) => {
                let _ = self.outbox.send(Frame::reply(self.id, reply, Vec::new()));
                Ok(())
            }
            Err(fail) => {
                self.abort();
                Err(fail.into_remote(Op::Write))
            }
        }
    }

    fn is_done(&self) -> bool {
        self.done
    }

    fn shutdown(&mut self) {
        if self.file.is_some() {
            self.abort();
        }
    }
}

impl Drop for FileWriter {
    fn drop(&mut self) {
        self.shutdown();
    }
}

/// `os.path.realpath`, not strict: every symbolic link on the way followed, and what does not
/// exist (or loops) kept as it is spelled.
fn realpath(path: &Path) -> PathBuf {
    let mut resolved = PathBuf::from("/");
    let mut pending: Vec<OsString> = components(path);
    pending.reverse();
    let mut hops = 0;
    while let Some(part) = pending.pop() {
        match part.as_bytes() {
            b"." => {}
            b".." => {
                resolved.pop();
            }
            _ => {
                let next = resolved.join(&part);
                match fs::read_link(&next) {
                    Ok(target) if hops < 40 => {
                        hops += 1;
                        if target.is_absolute() {
                            resolved = PathBuf::from("/");
                        }
                        let mut more = components(&target);
                        more.reverse();
                        pending.extend(more);
                    }
                    _ => resolved = next,
                }
            }
        }
    }
    resolved
}

fn components(path: &Path) -> Vec<OsString> {
    path.as_os_str()
        .as_bytes()
        .split(|b| *b == b'/')
        .filter(|s| !s.is_empty())
        .map(|s| OsString::from_vec(s.to_vec()))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    use crate::proto::{Kind, ProtocolError};

    #[derive(Default)]
    struct Caught(Mutex<Vec<Frame>>);

    impl Outbox for Caught {
        fn send(&self, frame: Frame) -> Result<(), ProtocolError> {
            self.0.lock().unwrap().push(frame);
            Ok(())
        }
    }

    fn table(real: &Path) -> ExportTable {
        let spec = format!("/w:{}", real.display());
        ExportTable::parse(&[spec]).unwrap()
    }

    fn req(pairs: Value) -> Meta {
        pairs.as_object().unwrap().clone()
    }

    #[test]
    fn stat_and_listdir() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(dir.path().join("f"), b"hello").unwrap();
        std::os::unix::fs::symlink("f", dir.path().join("l")).unwrap();
        let t = table(dir.path());
        let said = run(Op::Stat, &req(serde_json::json!({"path": "/w/f"})), &t).unwrap();
        assert_eq!(said["kind"], "file");
        assert_eq!(said["size"], 5);
        assert!(!said.contains_key("target"));
        let link = run(Op::Stat, &req(serde_json::json!({"path": "/w/l"})), &t).unwrap();
        assert_eq!(link["kind"], "link");
        assert_eq!(link["target"], "f");
        let listed = run(Op::Listdir, &req(serde_json::json!({"path": "/w"})), &t).unwrap();
        let mut names: Vec<_> = listed["entries"]
            .as_array()
            .unwrap()
            .iter()
            .map(|e| e["name"].as_str().unwrap().to_owned())
            .collect();
        names.sort();
        assert_eq!(names, ["f", "l"]);
        assert!(listed["mtime_ns"].as_i64().unwrap() > 0);
    }

    #[test]
    fn errors_are_spelled_as_python_spells_them() {
        let dir = tempfile::tempdir().unwrap();
        let t = table(dir.path());
        let missing = run(Op::Stat, &req(serde_json::json!({"path": "/w/nope"})), &t).unwrap_err();
        assert_eq!(missing.errno, libc::ENOENT);
        assert_eq!(
            missing.filename.as_deref(),
            Some(dir.path().join("nope").to_str().unwrap())
        );
        let keyless = run(Op::Stat, &Meta::new(), &t).unwrap_err();
        assert_eq!(keyless.errno, libc::EINVAL);
        assert_eq!(keyless.strerror, "malformed stat request: 'path'");
        let relative = run(Op::Unlink, &req(serde_json::json!({"path": "w"})), &t).unwrap_err();
        assert_eq!(
            relative.strerror,
            "malformed unlink request: virtual paths must be absolute, got 'w'"
        );
        let outside = run(Op::Stat, &req(serde_json::json!({"path": "/x"})), &t).unwrap_err();
        assert_eq!(outside.errno, libc::EACCES);
    }

    #[test]
    fn a_rename_told_not_to_replace_leaves_a_destination_that_is_there() {
        let dir = tempfile::tempdir().unwrap();
        let t = table(dir.path());
        let (src, dst) = (dir.path().join("src"), dir.path().join("dst"));
        fs::write(&src, b"new").unwrap();
        fs::write(&dst, b"precious").unwrap();
        let rename = |replace: Option<bool>| {
            let mut request = serde_json::json!({"src": "/w/src", "dst": "/w/dst"});
            if let Some(replace) = replace {
                request["replace"] = replace.into();
            }
            run(Op::Rename, &req(request), &t)
        };
        let refused = rename(Some(false)).unwrap_err();
        assert_eq!(refused.errno, libc::EEXIST);
        assert_eq!(fs::read(&src).unwrap(), b"new");
        assert_eq!(fs::read(&dst).unwrap(), b"precious");
        // Without the flag, as with it true, the destination is replaced.
        rename(None).unwrap();
        assert_eq!(fs::read(&dst).unwrap(), b"new");
        fs::write(&src, b"newer").unwrap();
        rename(Some(true)).unwrap();
        assert_eq!(fs::read(&dst).unwrap(), b"newer");
        assert!(!src.exists());
    }

    #[test]
    fn short_operations() {
        let dir = tempfile::tempdir().unwrap();
        let t = table(dir.path());
        let go = |op, v: Value| run(op, &req(v), &t);
        go(
            Op::Mkdir,
            serde_json::json!({"path": "/w/a/b/c", "parents": true}),
        )
        .unwrap();
        go(
            Op::Mkdir,
            serde_json::json!({"path": "/w/a/b/c", "parents": true}),
        )
        .unwrap();
        assert_eq!(
            go(Op::Mkdir, serde_json::json!({"path": "/w/a"}))
                .unwrap_err()
                .errno,
            libc::EEXIST
        );
        fs::write(dir.path().join("f"), b"0123456789").unwrap();
        go(Op::Truncate, serde_json::json!({"path": "/w/f", "size": 3})).unwrap();
        assert_eq!(fs::read(dir.path().join("f")).unwrap(), b"012");
        go(
            Op::Chmod,
            serde_json::json!({"path": "/w/f", "mode": 0o100600}),
        )
        .unwrap();
        assert_eq!(
            fs::metadata(dir.path().join("f")).unwrap().mode() & 0o7777,
            0o600
        );
        go(
            Op::Rename,
            serde_json::json!({"src": "/w/f", "dst": "/w/g", "replace": false}),
        )
        .unwrap();
        go(Op::Link, serde_json::json!({"src": "/w/g", "dst": "/w/h"})).unwrap();
        go(
            Op::Symlink,
            serde_json::json!({"target": "../anywhere", "path": "/w/s"}),
        )
        .unwrap();
        assert_eq!(
            go(Op::Readlink, serde_json::json!({"path": "/w/s"})).unwrap()["target"],
            "../anywhere"
        );
        go(
            Op::Utime,
            serde_json::json!({"path": "/w/g", "atime_ns": null, "mtime_ns": 5_000_000_123i64}),
        )
        .unwrap();
        let info = fs::metadata(dir.path().join("g")).unwrap();
        assert_eq!(mtime_ns(&info), 5_000_000_123);
        go(Op::Utime, serde_json::json!({"path": "/w/g"})).unwrap();
        assert!(mtime_ns(&fs::metadata(dir.path().join("g")).unwrap()) > 5_000_000_123);
        go(Op::Unlink, serde_json::json!({"path": "/w/h"})).unwrap();
        go(Op::Rmdir, serde_json::json!({"path": "/w/a/b/c"})).unwrap();
        assert!(!dir.path().join("a/b/c").exists());
    }

    #[test]
    fn reads_in_chunks() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(dir.path().join("big"), vec![7u8; CHUNK_SIZE + 10]).unwrap();
        let t = table(dir.path());
        let caught = Caught::default();
        read(4, &req(serde_json::json!({"path": "/w/big"})), &t, &caught).unwrap();
        let frames = caught.0.lock().unwrap();
        assert_eq!(frames.len(), 3);
        assert_eq!(frames[0].body.len(), CHUNK_SIZE);
        assert_eq!(frames[1].body.len(), 10);
        assert_eq!(frames[2].kind, Kind::Rsp);
        assert_eq!(frames[2].meta["size"], CHUNK_SIZE as u64 + 10);
        let dir_read = read(5, &req(serde_json::json!({"path": "/w"})), &t, &caught).unwrap_err();
        assert_eq!(dir_read.errno, libc::EISDIR);
    }

    #[test]
    fn writes_through_a_temporary_and_a_link() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(dir.path().join("old"), b"x").unwrap();
        fs::set_permissions(dir.path().join("old"), fs::Permissions::from_mode(0o640)).unwrap();
        std::os::unix::fs::symlink("deep/new", dir.path().join("link")).unwrap();
        let t = table(dir.path());
        let caught = Arc::new(Caught::default());
        let mut sink = write(
            1,
            &req(serde_json::json!({"path": "/w/old", "mode": null})),
            b"ab",
            &t,
            caught.clone(),
        )
        .unwrap();
        sink.feed(Stream::Data, b"cd").unwrap();
        sink.end(Stream::Data).unwrap();
        assert!(sink.is_done());
        assert_eq!(fs::read(dir.path().join("old")).unwrap(), b"abcd");
        assert_eq!(
            fs::metadata(dir.path().join("old")).unwrap().mode() & 0o7777,
            0o640
        );
        assert_eq!(caught.0.lock().unwrap()[0].meta["size"], 4);

        let mut sink = write(
            2,
            &req(serde_json::json!({"path": "/w/link", "mode": 0o600})),
            b"",
            &t,
            caught.clone(),
        )
        .unwrap();
        sink.end(Stream::Data).unwrap();
        assert!(dir.path().join("deep/new").is_file());
        assert!(
            fs::symlink_metadata(dir.path().join("link"))
                .unwrap()
                .file_type()
                .is_symlink()
        );

        let mut torn = write(
            3,
            &req(serde_json::json!({"path": "/w/torn"})),
            b"zz",
            &t,
            caught.clone(),
        )
        .unwrap();
        torn.shutdown();
        let left: Vec<_> = fs::read_dir(dir.path())
            .unwrap()
            .map(|e| e.unwrap().file_name())
            .collect();
        assert!(!left.iter().any(|n| n.to_string_lossy().ends_with(".tmp")));
        assert!(!dir.path().join("torn").exists());
    }
}

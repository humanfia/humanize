//! Frames on a byte stream: reading one, writing one, and a channel that does both.

use std::io::{self, Read, Write};
use std::net::{Shutdown, TcpStream};
use std::os::unix::net::UnixStream;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};

use super::{Frame, HEADER_BYTES, ProtocolError, parse_header};

/// Reads the next frame, or `None` at a clean end of stream (at a frame boundary).
pub fn read_frame(reader: &mut impl Read) -> Result<Option<Frame>, ProtocolError> {
    let mut header = [0u8; HEADER_BYTES];
    if !read_exactly(reader, &mut header, true)? {
        return Ok(None);
    }
    let (payload_len, _, _) = parse_header(&header)?;
    let mut payload = vec![0u8; payload_len];
    read_exactly(reader, &mut payload, false)?;
    Frame::decode(&header, payload).map(Some)
}

/// Writes one frame whole and flushes it.
pub fn write_frame(writer: &mut impl Write, frame: &Frame) -> io::Result<()> {
    writer.write_all(&frame.encode())?;
    writer.flush()
}

/// Fills `buf`, looping over short reads. False only for a clean end of stream before the
/// first byte where `allow_eof` says that is one.
fn read_exactly(
    reader: &mut impl Read,
    buf: &mut [u8],
    allow_eof: bool,
) -> Result<bool, ProtocolError> {
    let mut filled = 0;
    while filled < buf.len() {
        match reader.read(&mut buf[filled..]) {
            Ok(0) if allow_eof && filled == 0 => return Ok(false),
            Ok(0) => {
                return Err(ProtocolError(format!(
                    "truncated frame: wanted {} bytes, got {filled}",
                    buf.len()
                )));
            }
            Ok(n) => filled += n,
            Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
            Err(error) => return Err(ProtocolError(format!("read failed: {error}"))),
        }
    }
    Ok(true)
}

/// What a channel can shut down to wake a thread blocked reading it.
pub trait Waker: Send + Sync {
    /// Shuts the connection both ways, ignoring errors.
    fn wake(&self);
}

impl Waker for TcpStream {
    fn wake(&self) {
        let _ = self.shutdown(Shutdown::Both);
    }
}

impl Waker for UnixStream {
    fn wake(&self) {
        let _ = self.shutdown(Shutdown::Both);
    }
}

/// A framed, bidirectional connection. [`Channel::send`] may be called from any thread;
/// [`Channel::recv`] must be driven by exactly one.
pub struct Channel {
    reader: Mutex<Box<dyn Read + Send>>,
    writer: Mutex<Option<Box<dyn Write + Send>>>,
    waker: Option<Box<dyn Waker>>,
    closed: AtomicBool,
}

impl Channel {
    /// A channel over a reader and a writer, such as a child's stdout and stdin.
    pub fn new(reader: Box<dyn Read + Send>, writer: Box<dyn Write + Send>) -> Channel {
        Channel {
            reader: Mutex::new(reader),
            writer: Mutex::new(Some(writer)),
            waker: None,
            closed: AtomicBool::new(false),
        }
    }

    /// A channel over a connected TCP socket.
    pub fn from_tcp(stream: TcpStream) -> io::Result<Channel> {
        let _ = stream.set_nodelay(true);
        let reader = stream.try_clone()?;
        let writer = stream.try_clone()?;
        Ok(Channel {
            reader: Mutex::new(Box::new(reader)),
            writer: Mutex::new(Some(Box::new(writer))),
            waker: Some(Box::new(stream)),
            closed: AtomicBool::new(false),
        })
    }

    /// A channel over a connected Unix socket.
    pub fn from_unix(stream: UnixStream) -> io::Result<Channel> {
        let reader = stream.try_clone()?;
        let writer = stream.try_clone()?;
        Ok(Channel {
            reader: Mutex::new(Box::new(reader)),
            writer: Mutex::new(Some(Box::new(writer))),
            waker: Some(Box::new(stream)),
            closed: AtomicBool::new(false),
        })
    }

    /// Sends one frame. Fails once the channel is closed or the peer has gone.
    pub fn send(&self, frame: &Frame) -> Result<(), ProtocolError> {
        let blob = frame.encode();
        let mut writer = self.writer.lock().unwrap();
        let Some(out) = writer
            .as_mut()
            .filter(|_| !self.closed.load(Ordering::SeqCst))
        else {
            return Err(ProtocolError("channel is closed".into()));
        };
        if let Err(error) = out.write_all(&blob).and_then(|()| out.flush()) {
            self.closed.store(true, Ordering::SeqCst);
            return Err(ProtocolError(format!("send failed: {error}")));
        }
        Ok(())
    }

    /// Reads the next frame, or `None` at a clean end of stream.
    pub fn recv(&self) -> Result<Option<Frame>, ProtocolError> {
        let mut reader = self.reader.lock().unwrap();
        read_frame(&mut *reader)
    }

    /// Whether [`Channel::close`] has been called or a send has failed.
    pub fn is_closed(&self) -> bool {
        self.closed.load(Ordering::SeqCst)
    }

    /// Closes the channel: a socket is shut down (waking a blocked `recv`), and the writer is
    /// dropped so a pipe peer sees end of input. Idempotent.
    pub fn close(&self) {
        if self.closed.swap(true, Ordering::SeqCst) {
            return;
        }
        if let Some(waker) = &self.waker {
            waker.wake();
        }
        self.writer.lock().unwrap().take();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::meta;
    use crate::proto::{Op, Stream};

    #[test]
    fn frames_cross_a_socket() {
        let (a, b) = UnixStream::pair().unwrap();
        let left = Channel::from_unix(a).unwrap();
        let right = Channel::from_unix(b).unwrap();
        let sent = Frame::request(3, Op::Read, meta! {"path" => "/w"}, Vec::new());
        let expected = sent.clone();
        let sender = std::thread::spawn(move || {
            left.send(&sent).unwrap();
            left.send(&Frame::chunk(3, Stream::Data, vec![7; 200_000]))
                .unwrap();
            left.close();
        });
        assert_eq!(right.recv().unwrap().unwrap(), expected);
        assert_eq!(right.recv().unwrap().unwrap().body.len(), 200_000);
        assert!(right.recv().unwrap().is_none());
        sender.join().unwrap();
    }

    #[test]
    fn truncation_is_an_error() {
        let blob = Frame::end(1, Stream::Stdin).encode();
        let mut short = &blob[..blob.len() - 1];
        assert!(read_frame(&mut short).is_err());
        let mut empty: &[u8] = &[];
        assert!(read_frame(&mut empty).unwrap().is_none());
    }
}

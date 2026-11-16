//! TCP tunnels opened for a client. Port of the tunnel half of
//! `hmz.coganchor.serve.sessions`. [Unit 2]
//!
//! `CONNECT {host, port}` connects from this machine (30 s timeout, every address tried),
//! relays the client's `CHUNK`s out and the socket's bytes back as `CHUNK`s on `Data`, shuts
//! the socket's writing half on the client's `END`, and closes with `RSP {}` when the remote
//! side ends.
//!
//! `TunnelSession` connects on a thread of its own but has the connection's reader wait, up to
//! the same 30 s, for the socket before relaying a chunk. Here the reader does not wait on the
//! connecting: what the client sends before the socket is up is queued (in memory, unbounded)
//! and sent, in order, once it is, from a thread of its own while the answer is read. Once
//! open, a chunk is written from the reader, as `TunnelSession` writes it.
//!
//! A name that does not resolve is an `ERR` carrying `getaddrinfo`'s own code as the errno
//! (`EAI_NONAME` and the like, negative on Linux) with `gai_strerror`'s message, as Python's
//! `socket.gaierror` carries them; `EAI_SYSTEM` carries the errno behind it. A name that
//! resolves to no address is `EHOSTUNREACH`, and a connection that times out `ETIMEDOUT`.

use std::ffi::{CStr, CString};
use std::io::{self, Read, Write};
use std::net::{Ipv4Addr, Ipv6Addr, Shutdown, SocketAddr, SocketAddrV4, SocketAddrV6, TcpStream};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use serde_json::Value;

use crate::anchor::{Outbox, Sink};
use crate::proto::{CHUNK_SIZE, Frame, Meta, RemoteError, Stream};

/// How long one address is given to accept the connection, as `create_connection` gives it.
const CONNECT_TIMEOUT: Duration = Duration::from_secs(30);

/// Opens the tunnel `request` asks for, as exchange `id`.
pub fn connect(
    id: u64,
    request: &Meta,
    outbox: Arc<dyn Outbox>,
) -> Result<Box<dyn Sink>, RemoteError> {
    let invalid = |what: &str| RemoteError::new(libc::EINVAL, what.to_owned());
    let host = request
        .get("host")
        .and_then(Value::as_str)
        .ok_or_else(|| invalid("host must be a string"))?
        .to_owned();
    // `int(request["port"])` takes a number, a whole float, or its spelling.
    let port = match request.get("port") {
        Some(Value::Number(said)) => said.as_u64().or_else(|| {
            said.as_f64()
                .filter(|port| port.fract() == 0.0 && *port >= 0.0)
                .map(|port| port as u64)
        }),
        Some(Value::String(said)) => said.trim().parse::<u64>().ok(),
        _ => None,
    }
    .and_then(|port| u16::try_from(port).ok())
    .ok_or_else(|| invalid("port must be a port number"))?;

    let shared = Arc::new(Shared {
        state: Mutex::new(State::Connecting {
            queued: Vec::new(),
            ended: false,
            cancelled: false,
        }),
        done: AtomicBool::new(false),
    });
    {
        let shared = Arc::clone(&shared);
        thread::Builder::new()
            .name(format!("tunnel-{id}"))
            .spawn(move || {
                let reply = relay(id, &host, port, &shared, &*outbox);
                let _ = outbox.send(match reply {
                    Ok(()) => Frame::reply(id, Meta::new(), Vec::new()),
                    Err(error) => Frame::error(id, &error),
                });
                shared.done.store(true, Ordering::SeqCst);
            })
            .map_err(|e| RemoteError::from_io(&e, None))?;
    }
    Ok(Box::new(TunnelSink { shared }))
}

/// Where the tunnel's socket stands.
enum State {
    /// Still connecting: what the client has sent so far, whether it has ended, and whether
    /// the connection has gone.
    Connecting {
        queued: Vec<Vec<u8>>,
        ended: bool,
        cancelled: bool,
    },
    Open(Arc<TcpStream>),
    Closed,
}

/// What the tunnel's thread shares with its sink.
struct Shared {
    state: Mutex<State>,
    /// Whether the closing `RSP` (or `ERR`) has been sent.
    done: AtomicBool,
}

impl Shared {
    fn state(&self) -> std::sync::MutexGuard<'_, State> {
        self.state.lock().unwrap_or_else(|e| e.into_inner())
    }
}

/// Connects, has what was queued meanwhile sent, and relays the remote side's bytes until it
/// ends.
fn relay(
    id: u64,
    host: &str,
    port: u16,
    shared: &Arc<Shared>,
    outbox: &dyn Outbox,
) -> Result<(), RemoteError> {
    let socket = match open(host, port, shared) {
        Ok(socket) => Arc::new(socket),
        Err(error) => {
            *shared.state() = State::Closed;
            return Err(error);
        }
    };
    // The queue is sent from a thread of its own, so that the remote side's answer is read
    // meanwhile: a peer that answers before it reads on would otherwise wait on this thread
    // as it waits on the peer.
    let flusher = {
        let socket = Arc::clone(&socket);
        let shared = Arc::clone(shared);
        thread::Builder::new()
            .name(format!("tunnel-out-{id}"))
            .spawn(move || flush(&socket, &shared))
    };
    if flusher.is_err() {
        flush(&socket, shared);
    }
    let mut buffer = vec![0u8; CHUNK_SIZE];
    loop {
        match (&*socket).read(&mut buffer) {
            Ok(0) => break,
            Ok(n) => {
                let _ = outbox.send(Frame::chunk(id, Stream::Data, buffer[..n].to_vec()));
            }
            Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
            Err(_) => break,
        }
    }
    *shared.state() = State::Closed;
    let _ = socket.shutdown(Shutdown::Both);
    Ok(())
}

/// Sends what the client queued while connecting, batch by batch and outside the lock, so the
/// connection's reader only ever queues behind it; once the queue is empty the tunnel is open
/// and later chunks are written as they come.
fn flush(socket: &Arc<TcpStream>, shared: &Shared) {
    loop {
        let batch = {
            let mut state = shared.state();
            let State::Connecting {
                queued,
                ended,
                cancelled,
            } = &mut *state
            else {
                return;
            };
            if *cancelled {
                *state = State::Closed;
                let _ = socket.shutdown(Shutdown::Both);
                return;
            }
            if queued.is_empty() {
                let ended = *ended;
                *state = State::Open(Arc::clone(socket));
                if ended {
                    let _ = socket.shutdown(Shutdown::Write);
                }
                return;
            }
            std::mem::take(queued)
        };
        for data in batch {
            if (&**socket).write_all(&data).is_err() {
                *shared.state() = State::Closed;
                let _ = socket.shutdown(Shutdown::Both);
                return;
            }
        }
    }
}

/// A connection to `host:port`, trying every address it resolves to, made blocking. The
/// connection going meanwhile stops the trying.
fn open(host: &str, port: u16, shared: &Shared) -> Result<TcpStream, RemoteError> {
    let mut last = None;
    for address in resolve(host, port)? {
        if matches!(
            *shared.state(),
            State::Connecting {
                cancelled: true,
                ..
            }
        ) {
            return Err(RemoteError::errno(libc::ECONNABORTED));
        }
        match TcpStream::connect_timeout(&address, CONNECT_TIMEOUT) {
            Ok(socket) => {
                socket
                    .set_nonblocking(false)
                    .and_then(|()| socket.set_read_timeout(None))
                    .and_then(|()| socket.set_write_timeout(None))
                    .map_err(|e| RemoteError::from_io(&e, None))?;
                return Ok(socket);
            }
            Err(error) if error.kind() == io::ErrorKind::TimedOut => {
                last = Some(RemoteError::errno(libc::ETIMEDOUT));
            }
            Err(error) => last = Some(RemoteError::from_io(&error, None)),
        }
    }
    Err(last.unwrap_or_else(|| {
        RemoteError::new(libc::EHOSTUNREACH, "getaddrinfo returns an empty list")
    }))
}

/// Every stream address `host` has, in `getaddrinfo`'s order; its failure carries the `EAI_*`
/// code as the errno, as `socket.gaierror` does.
fn resolve(host: &str, port: u16) -> Result<Vec<SocketAddr>, RemoteError> {
    let node =
        CString::new(host).map_err(|_| RemoteError::new(libc::EINVAL, "embedded null byte"))?;
    let service = CString::new(port.to_string()).expect("digits have no NUL");
    // SAFETY: an all-zero addrinfo is a valid set of hints.
    let mut hints: libc::addrinfo = unsafe { std::mem::zeroed() };
    hints.ai_family = libc::AF_UNSPEC;
    hints.ai_socktype = libc::SOCK_STREAM;
    let mut list = std::mem::MaybeUninit::<*mut libc::addrinfo>::uninit();
    // SAFETY: every pointer is valid for the call; the list is freed below.
    let rc =
        unsafe { libc::getaddrinfo(node.as_ptr(), service.as_ptr(), &hints, list.as_mut_ptr()) };
    if rc != 0 {
        if rc == libc::EAI_SYSTEM {
            return Err(RemoteError::from_io(&io::Error::last_os_error(), None));
        }
        // SAFETY: gai_strerror returns a static string.
        let message = unsafe { CStr::from_ptr(libc::gai_strerror(rc)) };
        return Err(RemoteError::new(rc, message.to_string_lossy()));
    }
    // SAFETY: a successful getaddrinfo wrote the list's head, possibly null.
    let found = unsafe { list.assume_init() };
    let mut addresses = Vec::new();
    let mut at = found;
    // SAFETY: `at` walks the list getaddrinfo returned, which is alive until freed below.
    while let Some(info) = unsafe { at.as_ref() } {
        // SAFETY: each non-null `ai_addr` is sized for its family.
        unsafe {
            if info.ai_addr.is_null() {
                at = info.ai_next;
                continue;
            }
            match info.ai_family {
                libc::AF_INET => {
                    let addr = &*(info.ai_addr as *const libc::sockaddr_in);
                    addresses.push(SocketAddr::V4(SocketAddrV4::new(
                        Ipv4Addr::from(u32::from_be(addr.sin_addr.s_addr)),
                        u16::from_be(addr.sin_port),
                    )));
                }
                libc::AF_INET6 => {
                    let addr = &*(info.ai_addr as *const libc::sockaddr_in6);
                    addresses.push(SocketAddr::V6(SocketAddrV6::new(
                        Ipv6Addr::from(addr.sin6_addr.s6_addr),
                        u16::from_be(addr.sin6_port),
                        addr.sin6_flowinfo,
                        addr.sin6_scope_id,
                    )));
                }
                _ => {}
            }
            at = info.ai_next;
        }
    }
    if !found.is_null() {
        // SAFETY: `found` came from getaddrinfo and is freed once.
        unsafe { libc::freeaddrinfo(found) };
    }
    Ok(addresses)
}

/// A tunnel, as the connection sees it.
struct TunnelSink {
    shared: Arc<Shared>,
}

impl Sink for TunnelSink {
    /// Sends a chunk (whatever its stream) to the remote side, or queues it while connecting.
    /// A send that fails tears the socket down, which ends the tunnel.
    fn feed(&mut self, _stream: Stream, body: &[u8]) -> Result<(), RemoteError> {
        let socket = match &mut *self.shared.state() {
            State::Connecting { queued, .. } => {
                queued.push(body.to_vec());
                return Ok(());
            }
            State::Open(socket) => Arc::clone(socket),
            State::Closed => return Ok(()),
        };
        if (&*socket).write_all(body).is_err() {
            let _ = socket.shutdown(Shutdown::Both);
        }
        Ok(())
    }

    fn end(&mut self, _stream: Stream) -> Result<(), RemoteError> {
        match &mut *self.shared.state() {
            State::Connecting { ended, .. } => *ended = true,
            State::Open(socket) => {
                let _ = socket.shutdown(Shutdown::Write);
            }
            State::Closed => {}
        }
        Ok(())
    }

    fn is_done(&self) -> bool {
        self.shared.done.load(Ordering::SeqCst)
    }

    fn shutdown(&mut self) {
        match &mut *self.shared.state() {
            State::Connecting { cancelled, .. } => *cancelled = true,
            State::Open(socket) => {
                let _ = socket.shutdown(Shutdown::Both);
            }
            State::Closed => {}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::proto::Kind;
    use std::net::TcpListener;
    use std::time::Instant;

    /// Held by each test binding a port: a port one test lets go of could otherwise be the
    /// next another binds, and its listener then accept a connection meant to be refused.
    static PORTS: Mutex<()> = Mutex::new(());

    fn ports() -> std::sync::MutexGuard<'static, ()> {
        PORTS.lock().unwrap_or_else(|e| e.into_inner())
    }

    #[derive(Default)]
    struct Recorder(Mutex<Vec<Frame>>);

    impl Outbox for Recorder {
        fn send(&self, frame: Frame) -> Result<(), crate::proto::ProtocolError> {
            self.0.lock().unwrap().push(frame);
            Ok(())
        }
    }

    impl Recorder {
        fn closed(&self) -> Vec<Frame> {
            let deadline = Instant::now() + Duration::from_secs(40);
            loop {
                let frames = self.0.lock().unwrap().clone();
                if frames
                    .iter()
                    .any(|f| matches!(f.kind, Kind::Rsp | Kind::Err))
                {
                    return frames;
                }
                assert!(Instant::now() < deadline, "no reply: {frames:?}");
                thread::sleep(Duration::from_millis(10));
            }
        }
    }

    fn tunnel(host: &str, port: u16) -> (Box<dyn Sink>, Arc<Recorder>) {
        let recorder = Arc::new(Recorder::default());
        let outbox: Arc<dyn Outbox> = recorder.clone();
        let meta = crate::meta! {"host" => host, "port" => port};
        (connect(3, &meta, outbox).unwrap(), recorder)
    }

    #[test]
    fn relays_both_ways() {
        let _ports = ports();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let echo = thread::spawn(move || {
            let (mut peer, _) = listener.accept().unwrap();
            let mut said = Vec::new();
            peer.read_to_end(&mut said).unwrap();
            peer.write_all(&said).unwrap();
            said
        });
        // Fed at once, most likely while still connecting: queued, then sent in order.
        let (mut sink, out) = tunnel("localhost", port);
        sink.feed(Stream::Data, b"ping ").unwrap();
        sink.feed(Stream::Stdin, b"pong").unwrap();
        sink.end(Stream::Data).unwrap();
        assert_eq!(echo.join().unwrap(), b"ping pong");
        let frames = out.closed();
        let back: Vec<u8> = frames
            .iter()
            .filter(|f| f.kind == Kind::Chunk)
            .inspect(|f| assert_eq!(f.stream(), Stream::Data))
            .flat_map(|f| f.body.clone())
            .collect();
        assert_eq!(back, b"ping pong");
        let last = frames.last().unwrap();
        assert_eq!((last.kind, &last.meta), (Kind::Rsp, &Meta::new()));
        assert!(frames.iter().all(|f| f.kind != Kind::End));
        assert!(sink.is_done());
    }

    /// A peer echoing as it reads answers long before it has read what was queued; the queue
    /// is sent while the answer is read, or each side would wait on the other.
    #[test]
    fn a_large_queue_is_sent_while_the_answer_is_read() {
        let _ports = ports();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let echo = thread::spawn(move || {
            let (mut peer, _) = listener.accept().unwrap();
            let mut buffer = [0u8; 4096];
            loop {
                match peer.read(&mut buffer).unwrap() {
                    0 => return,
                    n => peer.write_all(&buffer[..n]).unwrap(),
                }
            }
        });
        let (mut sink, out) = tunnel("127.0.0.1", port);
        let piece = vec![7u8; CHUNK_SIZE];
        for _ in 0..128 {
            sink.feed(Stream::Data, &piece).unwrap();
        }
        sink.end(Stream::Data).unwrap();
        echo.join().unwrap();
        let frames = out.closed();
        let back: usize = frames.iter().map(|f| f.body.len()).sum();
        assert_eq!(back, 128 * CHUNK_SIZE);
        assert_eq!(frames.last().unwrap().kind, Kind::Rsp);
    }

    #[test]
    fn relays_after_connecting() {
        let _ports = ports();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let (mut sink, out) = tunnel("127.0.0.1", port);
        let (mut peer, _) = listener.accept().unwrap();
        // Given a moment, the socket is open and the chunk is written straight away.
        thread::sleep(Duration::from_millis(200));
        sink.feed(Stream::Data, b"x").unwrap();
        let mut one = [0u8; 1];
        peer.read_exact(&mut one).unwrap();
        assert_eq!(&one, b"x");
        drop(peer);
        assert_eq!(out.closed().last().unwrap().kind, Kind::Rsp);
    }

    #[test]
    fn a_refused_connection_is_an_error() {
        let _ports = ports();
        // A port just let go of refuses, unless a test running alongside has taken it since:
        // then the tunnel opens, and another port is tried.
        for _ in 0..10 {
            let port = {
                let listener = TcpListener::bind("127.0.0.1:0").unwrap();
                listener.local_addr().unwrap().port()
            };
            let (_sink, out) = tunnel("127.0.0.1", port);
            let frames = out.closed();
            let last = frames.last().unwrap();
            if last.kind == Kind::Err {
                assert_eq!(RemoteError::from_meta(&last.meta).errno, libc::ECONNREFUSED);
                return;
            }
        }
        panic!("every port tried was taken");
    }

    #[test]
    fn a_name_that_does_not_resolve_carries_its_eai_code() {
        let error = resolve("no-such-host.invalid", 80).unwrap_err();
        assert_ne!(error.errno, 0);
        assert!(!error.strerror.is_empty());
    }

    #[test]
    fn a_malformed_request_is_einval() {
        let outbox: Arc<dyn Outbox> = Arc::new(Recorder::default());
        for meta in [
            crate::meta! {"port" => 80},
            crate::meta! {"host" => "localhost"},
            crate::meta! {"host" => "localhost", "port" => 70000},
        ] {
            let error = connect(1, &meta, Arc::clone(&outbox)).err().unwrap();
            assert_eq!(error.errno, libc::EINVAL);
        }
    }
}

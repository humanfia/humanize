//! Making the agent's own outbound TCP connections come from the target. Port of
//! `hmz.coganchor.netproxy`. [Unit 11]
//!
//! Commands the agent runs already use the target's network, because they run there. This
//! covers what is left: connections the agent process opens itself, such as a built-in web
//! fetch. `connect(2)` is trapped and its destination swapped for a loopback listener made
//! here, one per destination, so the port a connection arrives on says where it was headed
//! and no per-connection state has to be guessed. Each accepted connection is relayed through
//! a tunnel out of the target.
//!
//! The agent's own control-plane traffic (its model API) must keep using this machine, so
//! loopback, link-local and unspecified destinations are left alone, and so is everything
//! `--net-allow` names.
//!
//! This module also holds [`Remote`], the slice of [`RemoteClient`] the cog's proxies use, so
//! that they can be tested against a fake anchor.

use std::collections::{HashMap, HashSet};
use std::io::{self, Read, Write};
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr, Shutdown, SocketAddr, TcpListener, TcpStream};
use std::os::fd::AsFd;
use std::os::unix::net::UnixStream;
use std::sync::mpsc::{self, Receiver};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use nix::errno::Errno;
use nix::poll::{PollFd, PollFlags, PollTimeout, poll};

use crate::client::{Event, Exchange, RemoteClient};
use crate::proto::{CHUNK_SIZE, Meta, RemoteError, Stream};

/// The sending half of an exchange: what a proxy says to a command or tunnel on the target.
pub(crate) trait Outlet: Send + Sync {
    fn send(&self, stream: Stream, body: &[u8]) -> Result<(), RemoteError>;
    fn end(&self, stream: Stream) -> Result<(), RemoteError>;
    fn signal(&self, signal: i32) -> Result<(), RemoteError>;
}

/// An exchange split in two, so one thread can send on it while another reads its events.
pub(crate) struct Conduit {
    pub outlet: Arc<dyn Outlet>,
    pub events: Receiver<Event>,
}

/// What the cog's proxies ask of the anchor: [`RemoteClient`], or a fake of it in tests.
pub(crate) trait Remote: Send + Sync + 'static {
    /// Starts a command; `request` is the `EXEC` metadata without `op`.
    fn start_exec(&self, request: Meta) -> Result<Conduit, RemoteError>;
    /// Opens a TCP tunnel out of the anchor's machine.
    fn open_tunnel(&self, host: &str, port: u16) -> Result<Conduit, RemoteError>;
}

impl Outlet for Mutex<Exchange> {
    fn send(&self, stream: Stream, body: &[u8]) -> Result<(), RemoteError> {
        lock(self).send(stream, body)
    }

    fn end(&self, stream: Stream) -> Result<(), RemoteError> {
        lock(self).end(stream)
    }

    fn signal(&self, signal: i32) -> Result<(), RemoteError> {
        lock(self).signal(signal)
    }
}

/// An [`Exchange`]'s receiver taken out of it, and the rest made shareable.
fn split(mut exchange: Exchange) -> Conduit {
    let events = std::mem::replace(&mut exchange.events, mpsc::channel().1);
    Conduit {
        outlet: Arc::new(Mutex::new(exchange)),
        events,
    }
}

impl Remote for RemoteClient {
    fn start_exec(&self, request: Meta) -> Result<Conduit, RemoteError> {
        RemoteClient::start_exec(self, request).map(split)
    }

    fn open_tunnel(&self, host: &str, port: u16) -> Result<Conduit, RemoteError> {
        RemoteClient::open_tunnel(self, host, port).map(split)
    }
}

/// A lock that a panicked holder has not made unusable: nothing guarded here can be left
/// half-updated.
pub(crate) fn lock<T>(mutex: &Mutex<T>) -> std::sync::MutexGuard<'_, T> {
    mutex
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

/// How long an accept loop pauses after `accept` fails for a reason that persists.
const ACCEPT_BACKOFF: Duration = Duration::from_millis(100);

/// How long a relay waits, once the agent has stopped sending, for the tunnel to close
/// before closing the agent's connection itself (`_Relay._run`).
const LINGER: Duration = Duration::from_secs(30);

/// The listeners standing in for remote destinations.
pub struct NetProxy {
    remote: Arc<dyn Remote>,
    /// `--net-allow` entries, hostnames resolved: an address alone, or an address and port.
    allowed: HashSet<(IpAddr, Option<u16>)>,
    /// Each destination's loopback stand-in.
    listeners: Mutex<HashMap<SocketAddr, SocketAddr>>,
    /// Every accept loop watches the other end of this; dropping it stops them all.
    stop: UnixStream,
    stopped: UnixStream,
}

impl NetProxy {
    /// A proxy leaving loopback, link-local, unspecified and `allow`ed destinations alone.
    pub fn new(client: Arc<RemoteClient>, allow: &[String]) -> io::Result<NetProxy> {
        NetProxy::with(client, allow, resolve)
    }

    /// [`NetProxy::new`] over any [`Remote`], with `resolve` turning allow-list hostnames
    /// into addresses.
    pub(crate) fn with(
        remote: Arc<dyn Remote>,
        allow: &[String],
        resolve: impl Fn(&str) -> io::Result<Vec<IpAddr>>,
    ) -> io::Result<NetProxy> {
        let (stop, stopped) = UnixStream::pair()?;
        Ok(NetProxy {
            remote,
            allowed: allow_list(allow, resolve),
            listeners: Mutex::new(HashMap::new()),
            stop,
            stopped,
        })
    }

    /// The loopback address to connect to instead of `dest`, or `None` to leave it.
    ///
    /// The replacement is in `dest`'s own family: the tracee is about to hand it to a socket
    /// that already has one, and an address of the wrong family fails `EINVAL`. An
    /// IPv4-mapped IPv6 destination is judged, and tunnelled, as the IPv4 address it maps.
    pub fn redirect(&self, dest: SocketAddr) -> io::Result<Option<SocketAddr>> {
        // Keyed by address and port alone: an IPv6 flow label or scope says nothing of where.
        let dest = SocketAddr::new(dest.ip(), dest.port());
        let ip = unmapped(dest.ip());
        if self.stays_here(ip, dest.port()) {
            return Ok(None);
        }
        let mut listeners = lock(&self.listeners);
        if let Some(local) = listeners.get(&dest) {
            return Ok(Some(*local));
        }
        let loopback = match dest {
            SocketAddr::V4(_) => IpAddr::V4(Ipv4Addr::LOCALHOST),
            SocketAddr::V6(_) => IpAddr::V6(Ipv6Addr::LOCALHOST),
        };
        let listener = TcpListener::bind((loopback, 0))?;
        listener.set_nonblocking(true)?;
        let local = listener.local_addr()?;
        let stopped = self.stopped.try_clone()?;
        let remote = Arc::clone(&self.remote);
        let host = ip.to_string();
        let port = dest.port();
        thread::Builder::new()
            .name("netproxy".into())
            .spawn(move || accept_loop(listener, stopped, remote, host, port))?;
        tracing::debug!("tunnelling {local} -> {dest} via the target");
        listeners.insert(dest, local);
        Ok(Some(local))
    }

    /// Whether a connection to `ip:port` keeps using this machine.
    fn stays_here(&self, ip: IpAddr, port: u16) -> bool {
        let local = match ip {
            IpAddr::V4(v4) => v4.is_loopback() || v4.is_link_local() || v4.is_unspecified(),
            IpAddr::V6(v6) => {
                v6.is_loopback() || v6.is_unspecified() || (v6.segments()[0] & 0xffc0) == 0xfe80
            }
        };
        local || self.allowed.contains(&(ip, None)) || self.allowed.contains(&(ip, Some(port)))
    }
}

impl Drop for NetProxy {
    /// Stops every accept loop, closing its listener; relays already running finish.
    fn drop(&mut self) {
        let _ = self.stop.shutdown(Shutdown::Both);
    }
}

/// The IPv4 address an IPv4-mapped IPv6 address stands for, or the address itself.
fn unmapped(ip: IpAddr) -> IpAddr {
    match ip {
        IpAddr::V6(v6) => v6.to_ipv4_mapped().map_or(ip, IpAddr::V4),
        IpAddr::V4(_) => ip,
    }
}

/// The addresses a hostname resolves to here.
fn resolve(host: &str) -> io::Result<Vec<IpAddr>> {
    use std::net::ToSocketAddrs;
    Ok((host, 0).to_socket_addrs()?.map(|a| a.ip()).collect())
}

/// `--net-allow` entries (`HOST`, `HOST:PORT`, `[V6]:PORT`) as the addresses `connect` will
/// name.
///
/// `connect(2)` is trapped after the agent has resolved the name, so the destination is
/// always numeric by then: an entry naming a host only ever matches once resolved, which is
/// done once, here. An entry that does not resolve never matches.
fn allow_list(
    entries: &[String],
    resolve: impl Fn(&str) -> io::Result<Vec<IpAddr>>,
) -> HashSet<(IpAddr, Option<u16>)> {
    let mut allowed = HashSet::new();
    for entry in entries {
        let (host, port) = split_entry(entry);
        let ips = match host.parse::<IpAddr>() {
            Ok(ip) => vec![ip],
            Err(_) => match resolve(host) {
                Ok(ips) => ips,
                Err(error) => {
                    tracing::warn!(
                        "could not resolve --net-allow {entry:?}; it will never match: {error}"
                    );
                    continue;
                }
            },
        };
        allowed.extend(ips.into_iter().map(|ip| (unmapped(ip), port)));
    }
    allowed
}

/// An allow-list entry's host and port. A bare IPv6 address is a host alone; one with a
/// port is bracketed.
fn split_entry(entry: &str) -> (&str, Option<u16>) {
    if entry.parse::<IpAddr>().is_ok() {
        return (entry, None);
    }
    if let Some(rest) = entry.strip_prefix('[') {
        return match rest.split_once(']') {
            Some((host, "")) => (host, None),
            Some((host, port)) => match port.strip_prefix(':').and_then(|p| p.parse().ok()) {
                Some(port) => (host, Some(port)),
                None => (entry, None),
            },
            None => (entry, None),
        };
    }
    match entry.rsplit_once(':') {
        Some((host, port)) if !host.is_empty() => match port.parse() {
            Ok(port) => (host, Some(port)),
            Err(_) => (entry, None),
        },
        _ => (entry, None),
    }
}

/// Accepts connections on one destination's listener until the proxy is dropped, relaying
/// each to `host:port` from the target.
fn accept_loop(
    listener: TcpListener,
    stopped: UnixStream,
    remote: Arc<dyn Remote>,
    host: String,
    port: u16,
) {
    loop {
        let mut fds = [
            PollFd::new(listener.as_fd(), PollFlags::POLLIN),
            PollFd::new(stopped.as_fd(), PollFlags::POLLIN),
        ];
        match poll(&mut fds, PollTimeout::NONE) {
            Ok(_) | Err(Errno::EINTR) => {}
            Err(error) => {
                tracing::warn!("netproxy for {host}:{port} stopped: {error}");
                return;
            }
        }
        if fds[1].any().unwrap_or(true) {
            return;
        }
        match listener.accept() {
            Ok((socket, _)) => {
                let remote = Arc::clone(&remote);
                let target = host.clone();
                let spawned = thread::Builder::new()
                    .name("net-relay".into())
                    .spawn(move || relay(remote.as_ref(), socket, &target, port));
                if let Err(error) = spawned {
                    tracing::warn!("could not relay a connection to {host}:{port}: {error}");
                }
            }
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {}
            Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
            Err(error) => {
                // Out of descriptors, say: the connection stays pending and the listener
                // readable, so pause rather than spin.
                tracing::debug!("accept for {host}:{port} failed: {error}");
                thread::sleep(ACCEPT_BACKOFF);
            }
        }
    }
}

/// Pumps one accepted loopback connection through a tunnel to `host:port`, both ways, each
/// direction's end passed on as a half-close.
fn relay(remote: &dyn Remote, socket: TcpStream, host: &str, port: u16) {
    // An accepted socket inherits nothing from the listener on Linux, but does on macOS.
    let _ = socket.set_nonblocking(false);
    let Conduit { outlet, events } = match remote.open_tunnel(host, port) {
        Ok(conduit) => conduit,
        Err(error) => {
            tracing::debug!("tunnel to {host}:{port} refused: {}", error.strerror);
            return; // dropping the socket closes the agent's connection
        }
    };
    let (finished, closed) = mpsc::channel::<()>();
    let inbound = match socket.try_clone() {
        Ok(writer) => thread::Builder::new()
            .name("net-relay-in".into())
            .spawn(move || {
                pump_inbound(events, writer);
                drop(finished);
            }),
        Err(error) => Err(error),
    };
    if let Err(error) = inbound {
        tracing::debug!("could not relay {host}:{port}: {error}");
        let _ = outlet.end(Stream::Data);
        return;
    }
    pump_outbound(&socket, outlet.as_ref());
    // Disconnected once the tunnel has closed; a far end that never does is let go after
    // a while, the agent's connection closed under it.
    if closed.recv_timeout(LINGER) == Err(mpsc::RecvTimeoutError::Timeout) {
        tracing::debug!("tunnel to {host}:{port} still open; closing the connection");
        let _ = socket.shutdown(Shutdown::Both);
    }
    tracing::debug!("tunnel to {host}:{port} finished");
}

/// The agent's bytes into the tunnel, until the agent stops writing or the tunnel closes.
fn pump_outbound(mut socket: &TcpStream, outlet: &dyn Outlet) {
    let mut buf = vec![0u8; CHUNK_SIZE];
    loop {
        match socket.read(&mut buf) {
            Ok(0) => break,
            Ok(n) => {
                if outlet.send(Stream::Data, &buf[..n]).is_err() {
                    return; // the tunnel is gone; the inbound pump hears its end
                }
            }
            Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
            Err(_) => break,
        }
    }
    let _ = outlet.end(Stream::Data);
}

/// The tunnel's bytes into the agent's socket, until the tunnel closes. Its `END` becomes a
/// write shutdown, so the agent reads EOF while it may still send; its close shuts the
/// socket entirely, which also stops the outbound pump.
fn pump_inbound(events: Receiver<Event>, mut socket: TcpStream) {
    let mut writable = true;
    for event in events.iter() {
        match event {
            Event::Chunk(_, data) if writable => {
                if socket.write_all(&data).is_err() {
                    writable = false;
                    let _ = socket.shutdown(Shutdown::Both);
                }
            }
            Event::Chunk(..) => {}
            Event::End(_) => {
                writable = false;
                let _ = socket.shutdown(Shutdown::Write);
            }
            Event::Done(result) => {
                if let Err(error) = result {
                    tracing::debug!("tunnel ended: {}", error.strerror);
                }
                break;
            }
        }
    }
    let _ = socket.shutdown(Shutdown::Both);
}

/// A fake anchor for the proxies' tests: each exchange opened is handed to the test, which
/// sees what the proxy sends and plays the anchor's events.
#[cfg(test)]
pub(crate) mod fake {
    use std::sync::Mutex;
    use std::sync::mpsc::{self, Receiver, Sender};

    use super::*;

    /// Something a proxy sent on an exchange.
    #[derive(Debug, PartialEq, Eq)]
    pub enum Sent {
        Chunk(Stream, Vec<u8>),
        End(Stream),
        Signal(i32),
    }

    /// One exchange the proxy opened: its request, what it sends, and the anchor's side.
    pub struct Opened {
        pub request: Meta,
        pub sent: Receiver<Sent>,
        pub events: Sender<Event>,
    }

    pub struct FakeRemote {
        opened: Mutex<Sender<Opened>>,
        /// An errno every request fails with, as if the anchor were gone.
        pub refuse: Option<i32>,
    }

    impl FakeRemote {
        pub fn new(refuse: Option<i32>) -> (Arc<FakeRemote>, Receiver<Opened>) {
            let (tx, rx) = mpsc::channel();
            let remote = FakeRemote {
                opened: Mutex::new(tx),
                refuse,
            };
            (Arc::new(remote), rx)
        }

        fn open(&self, request: Meta) -> Result<Conduit, RemoteError> {
            if let Some(errno) = self.refuse {
                return Err(RemoteError::errno(errno));
            }
            let (sent_tx, sent) = mpsc::channel();
            let (events, events_rx) = mpsc::channel();
            let _ = lock(&self.opened).send(Opened {
                request,
                sent,
                events,
            });
            Ok(Conduit {
                outlet: Arc::new(FakeOutlet(Mutex::new(sent_tx))),
                events: events_rx,
            })
        }
    }

    impl Remote for FakeRemote {
        fn start_exec(&self, request: Meta) -> Result<Conduit, RemoteError> {
            self.open(request)
        }

        fn open_tunnel(&self, host: &str, port: u16) -> Result<Conduit, RemoteError> {
            let mut request = Meta::new();
            request.insert("host".into(), host.into());
            request.insert("port".into(), port.into());
            self.open(request)
        }
    }

    struct FakeOutlet(Mutex<Sender<Sent>>);

    impl FakeOutlet {
        fn put(&self, sent: Sent) -> Result<(), RemoteError> {
            lock(&self.0)
                .send(sent)
                .map_err(|_| RemoteError::errno(libc::EPIPE))
        }
    }

    impl Outlet for FakeOutlet {
        fn send(&self, stream: Stream, body: &[u8]) -> Result<(), RemoteError> {
            self.put(Sent::Chunk(stream, body.to_vec()))
        }

        fn end(&self, stream: Stream) -> Result<(), RemoteError> {
            self.put(Sent::End(stream))
        }

        fn signal(&self, signal: i32) -> Result<(), RemoteError> {
            self.put(Sent::Signal(signal))
        }
    }
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use super::fake::{FakeRemote, Opened, Sent};
    use super::*;

    fn names(host: &str) -> io::Result<Vec<IpAddr>> {
        match host {
            "api.example" => Ok(vec![
                "203.0.113.5".parse().unwrap(),
                "2001:db8::5".parse().unwrap(),
            ]),
            _ => Err(io::Error::other("unknown")),
        }
    }

    fn running() -> (NetProxy, Receiver<Opened>) {
        let (remote, opened) = FakeRemote::new(None);
        let allow = [
            "api.example",
            "198.51.100.7:443",
            "nowhere.invalid",
            "[2001:db8::7]:22",
        ]
        .map(String::from);
        (NetProxy::with(remote, &allow, names).unwrap(), opened)
    }

    fn at(said: &str) -> SocketAddr {
        said.parse().unwrap()
    }

    #[test]
    fn what_must_stay_here_is_left_alone() {
        let (proxy, _) = running();
        for dest in [
            "127.0.0.1:80",
            "[::1]:80",
            "169.254.1.1:80",
            "[fe80::1]:80",
            "0.0.0.0:80",
            "[::]:80",
            "[::ffff:127.0.0.1]:80",
            "203.0.113.5:443",
            "[2001:db8::5]:443",
            "[::ffff:203.0.113.5]:443",
            "198.51.100.7:443",
            "[2001:db8::7]:22",
        ] {
            assert_eq!(proxy.redirect(at(dest)).unwrap(), None, "{dest}");
        }
        assert!(lock(&proxy.listeners).is_empty());
    }

    #[test]
    fn an_allowed_host_is_allowed_on_its_port_alone() {
        let (proxy, _) = running();
        assert!(proxy.redirect(at("198.51.100.7:80")).unwrap().is_some());
        assert!(proxy.redirect(at("[2001:db8::7]:23")).unwrap().is_some());
    }

    #[test]
    fn entries_are_split_into_host_and_port() {
        assert_eq!(split_entry("example.com"), ("example.com", None));
        assert_eq!(split_entry("example.com:8443"), ("example.com", Some(8443)));
        assert_eq!(split_entry("10.0.0.1:22"), ("10.0.0.1", Some(22)));
        assert_eq!(split_entry("2001:db8::5"), ("2001:db8::5", None));
        assert_eq!(split_entry("[2001:db8::5]:443"), ("2001:db8::5", Some(443)));
        assert_eq!(split_entry("[2001:db8::5]"), ("2001:db8::5", None));
    }

    #[test]
    fn a_connection_elsewhere_is_sent_to_a_listener_of_its_own() {
        let (proxy, _) = running();
        let first = proxy.redirect(at("203.0.113.9:80")).unwrap().unwrap();
        let again = proxy.redirect(at("203.0.113.9:80")).unwrap().unwrap();
        let other = proxy.redirect(at("203.0.113.9:81")).unwrap().unwrap();
        assert_eq!(first, again);
        assert_eq!(first.ip(), IpAddr::V4(Ipv4Addr::LOCALHOST));
        assert_ne!(first.port(), other.port());
        assert_eq!(lock(&proxy.listeners).len(), 2);
    }

    #[test]
    fn the_listener_is_in_the_destinations_own_family() {
        let (proxy, _) = running();
        let found = proxy.redirect(at("[2001:db8::9]:80")).unwrap().unwrap();
        assert_eq!(found.ip(), IpAddr::V6(Ipv6Addr::LOCALHOST));
        let mapped = proxy
            .redirect(at("[::ffff:203.0.113.9]:80"))
            .unwrap()
            .unwrap();
        assert_eq!(mapped.ip(), IpAddr::V6(Ipv6Addr::LOCALHOST));
    }

    /// Plays a tunnel that answers what it is sent in upper case, ending when the proxy
    /// ends, and returns the request it was opened with.
    fn echo_upper(opened: Opened) -> Meta {
        loop {
            match opened.sent.recv_timeout(Duration::from_secs(5)).unwrap() {
                Sent::Chunk(Stream::Data, data) => {
                    let _ = opened
                        .events
                        .send(Event::Chunk(Stream::Data, data.to_ascii_uppercase()));
                }
                Sent::End(Stream::Data) => break,
                other => panic!("unexpected {other:?}"),
            }
        }
        let _ = opened.events.send(Event::End(Stream::Data));
        let _ = opened.events.send(Event::Done(Ok(Meta::new())));
        opened.request
    }

    #[test]
    fn a_connection_round_trips_through_the_tunnel_half_closing() {
        let (proxy, opened) = running();
        let local = proxy.redirect(at("203.0.113.9:8080")).unwrap().unwrap();
        let mut agent = TcpStream::connect(local).unwrap();
        agent.write_all(b"ping ").unwrap();
        let anchor =
            thread::spawn(move || echo_upper(opened.recv_timeout(Duration::from_secs(5)).unwrap()));
        agent.write_all(b"pong").unwrap();
        agent.shutdown(Shutdown::Write).unwrap();
        agent
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let mut got = Vec::new();
        agent.read_to_end(&mut got).unwrap();
        assert_eq!(got, b"PING PONG");
        let request = anchor.join().unwrap();
        assert_eq!(request["host"], "203.0.113.9");
        assert_eq!(request["port"], 8080);
    }

    #[test]
    fn an_ipv6_connection_round_trips_and_a_mapped_one_names_ipv4() {
        let (proxy, opened) = running();
        for (dest, host) in [
            ("[2001:db8::9]:80", "2001:db8::9"),
            ("[::ffff:203.0.113.9]:80", "203.0.113.9"),
        ] {
            let local = proxy.redirect(at(dest)).unwrap().unwrap();
            let mut agent = TcpStream::connect(local).unwrap();
            agent.write_all(b"hi").unwrap();
            agent.shutdown(Shutdown::Write).unwrap();
            let request = echo_upper(opened.recv_timeout(Duration::from_secs(5)).unwrap());
            let mut got = Vec::new();
            agent.read_to_end(&mut got).unwrap();
            assert_eq!(got, b"HI");
            assert_eq!(request["host"], host);
        }
    }

    #[test]
    fn the_tunnel_closing_closes_the_agents_connection() {
        let (proxy, opened) = running();
        let local = proxy.redirect(at("203.0.113.9:80")).unwrap().unwrap();
        let mut agent = TcpStream::connect(local).unwrap();
        let tunnel = opened.recv_timeout(Duration::from_secs(5)).unwrap();
        tunnel
            .events
            .send(Event::Chunk(Stream::Data, b"bye".to_vec()))
            .unwrap();
        tunnel
            .events
            .send(Event::Done(Err(RemoteError::errno(libc::ECONNRESET))))
            .unwrap();
        agent
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let mut got = Vec::new();
        let _ = agent.read_to_end(&mut got);
        assert_eq!(got, b"bye");
        // The outbound pump stopped too, and said so.
        assert_eq!(
            tunnel.sent.recv_timeout(Duration::from_secs(5)).unwrap(),
            Sent::End(Stream::Data)
        );
    }

    #[test]
    fn a_refused_tunnel_closes_the_agents_connection() {
        let (remote, _opened) = FakeRemote::new(Some(libc::ECONNREFUSED));
        let proxy = NetProxy::with(remote, &[], names).unwrap();
        let local = proxy.redirect(at("203.0.113.9:80")).unwrap().unwrap();
        let mut agent = TcpStream::connect(local).unwrap();
        agent
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let mut got = Vec::new();
        let _ = agent.read_to_end(&mut got);
        assert!(got.is_empty());
    }

    #[test]
    fn dropping_the_proxy_closes_every_listener() {
        let (proxy, _opened) = running();
        let local = proxy.redirect(at("203.0.113.9:80")).unwrap().unwrap();
        drop(proxy);
        for _ in 0..100 {
            if TcpStream::connect(local).is_err() {
                return;
            }
            thread::sleep(Duration::from_millis(20));
        }
        panic!("{local} still accepts after the proxy was dropped");
    }
}

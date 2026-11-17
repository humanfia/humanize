//! A half's side of a meeting. Port of `dial`, `_punch`, `_knocking`, `_answering`, `_greet`
//! and the socket helpers in `hmz.coganchor.rendezvous`. [Unit 3]
//!
//! Both halves open outward from, and listen on, the one port the broker saw them at, and do
//! it at once: where a NAT is address-independent each side's outbound attempt opens the hole
//! the peer's arrives through. The first punched connection that proves it is the other half
//! of this session is kept; if none does, the connection to the broker carries the session.

use std::io::{self, Write};
use std::net::{Ipv4Addr, SocketAddr, SocketAddrV4, TcpListener, TcpStream, ToSocketAddrs};
use std::os::fd::{AsFd, AsRawFd, OwnedFd};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, mpsc};
use std::thread;
use std::time::{Duration, Instant};

use nix::errno::Errno;
use nix::fcntl::{FcntlArg, FdFlag, fcntl};
use nix::poll::{PollFd, PollFlags, PollTimeout, poll};
use nix::sys::socket::{self as sock, AddressFamily, Backlog, SockFlag, SockType, SockaddrIn};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use tracing::debug;

use super::{
    ANSWERING, Candidate, Event, GO, GREETING, MAGIC, Meeting, NAMING, OK, Role, TRIES,
    candidates_json, inet_aton, pairs, python_str, read_line, read_object, refused, say, seconds,
    truthy,
};

/// Meets the other half through the broker, returning a blocking, `TCP_NODELAY` socket that is
/// either a direct connection to it or the broker relaying for both.
///
/// `timeout` is how long to wait at the broker for the other half (`PAIRING` in the Python).
/// Fails if the broker cannot be reached, the other half never arrives, or the broker will
/// not join the two.
pub fn dial(meeting: &Meeting, role: Role, timeout: Duration) -> io::Result<TcpStream> {
    // The broker, and anyone between, is told a name for the meeting and never its ticket,
    // which is the key the two halves then prove to each other inside TLS.
    let meeting = &Meeting {
        ticket: crate::tls::meeting_name(&meeting.ticket),
        ..meeting.clone()
    };
    // One port for both, taken before either is used: the broker has to see this half at the
    // port its peer will be sent at, and the peer has to find something listening there.
    let (home, ear, port) = both()?;
    let home = TcpStream::from(home);
    let broker = resolve(&meeting.host, meeting.port)?;
    connect_within(&home, broker, timeout)?;
    let punched = meet(&home, ear.as_ref(), port, meeting, role, timeout)?;
    drop(ear);
    match punched {
        Some(punched) => {
            debug!("joined {} directly", short(&meeting.ticket));
            drop(home);
            settled(punched)
        }
        None => {
            debug!("joined {} through the broker", short(&meeting.ticket));
            settled(home)
        }
    }
}

fn short(ticket: &str) -> &str {
    ticket.get(..8).unwrap_or(ticket)
}

/// The broker's half of `dial`: hello, `seen`, `peer`, the punch, the verdict, and the
/// broker's word on it. `Some` is a punched socket to use, `None` is `home` relayed.
fn meet(
    home: &TcpStream,
    ear: Option<&TcpListener>,
    port: u16,
    meeting: &Meeting,
    role: Role,
    timeout: Duration,
) -> io::Result<Option<TcpStream>> {
    let at = candidates_json(&mine(home, port)?);
    say(
        home,
        &json!({"ticket": meeting.ticket, "role": role.as_str(), "at": at}),
    )?;
    let seen = read_object(home, timeout)?;
    let seen = seen.get("seen").cloned().unwrap_or_default();
    debug!("the broker sees this half at {seen}");
    // A little longer than the broker is patient for, so a half that gave up on the same
    // tick hears the broker's own account of what it had been waiting for.
    let said = read_object(home, timeout.saturating_add(ANSWERING))?;
    let Some(peer) = said.get("peer") else {
        // `str(said.get("why") or "the other half never arrived")`.
        let why = said.get("why").filter(|why| truthy(Some(why)));
        let why = match why {
            Some(why) => python_str(Some(why)),
            None => "the other half never arrived".to_owned(),
        };
        return Err(refused(why));
    };
    let punch = python_float_of(said.get("punch"))?;
    let punched = punch_through(
        ear,
        port,
        &pairs(Some(peer)),
        &meeting.ticket,
        role,
        seconds(punch),
    );
    say(home, &json!({"direct": punched.is_some()}))?;
    // The broker's word rather than this half's: one end can hold a socket the other never
    // learned it had, and two halves disagreeing about which pipe the session is on hang.
    let agreed = read_object(home, ANSWERING)?;
    match (agreed.get("go"), punched) {
        (Some(Value::String(go)), Some(punched)) if go == "direct" => Ok(Some(punched)),
        (Some(Value::String(go)), _) if go == "relay" => Ok(None),
        (go, _) => {
            let go = go.map_or_else(|| "None".to_owned(), |go| python_str(Some(go)));
            Err(refused(format!(
                "the broker will not join this session: {go}"
            )))
        }
    }
}

/// `float(said.get("punch", 0.0))`: a number, a bool, or a string spelling one.
fn python_float_of(said: Option<&Value>) -> io::Result<f64> {
    let unreadable = || {
        io::Error::new(
            io::ErrorKind::InvalidData,
            format!(
                "could not convert the broker's punch to a number: {}",
                python_str(said)
            ),
        )
    };
    match said {
        None => Ok(0.0),
        Some(Value::Number(n)) => n.as_f64().ok_or_else(unreadable),
        Some(Value::Bool(b)) => Ok(f64::from(u8::from(*b))),
        // Rust's parser, like `float()`, takes `inf`, `nan` and a sign in any case.
        Some(Value::String(s)) => s.trim().replace('_', "").parse().map_err(|_| unreadable()),
        Some(_) => Err(unreadable()),
    }
}

// ------------------------------------------------------------------------ punching a hole

/// What the punching threads share (`won`, `claimed`, `stop` in `_punch`).
struct Punch {
    name: String,
    role: Role,
    deadline: Instant,
    /// Taken once, never given back: whichever GO the serving half reads first is the socket.
    claimed: AtomicBool,
    stop: Event,
}

/// Opens holes at every address the other half gave, and listens for its own (`_punch`).
/// Returns the socket joining the two, or None if the window closed with nothing through it.
fn punch_through(
    ear: Option<&TcpListener>,
    port: u16,
    candidates: &[Candidate],
    name: &str,
    role: Role,
    window: Duration,
) -> Option<TcpStream> {
    let mut where_to: Vec<SocketAddrV4> = Vec::new();
    for (host, at) in candidates {
        // A bool is the int it is in Python; a port out of range is skipped where Python's
        // `connect` would raise.
        let at = match at {
            Value::Bool(b) => Some(u16::from(*b)),
            _ => at.as_u64().and_then(|p| u16::try_from(p).ok()),
        };
        let (Some(ip), Some(at)) = (inet_aton(host), at) else {
            continue;
        };
        let one = SocketAddrV4::new(ip, at);
        if !where_to.contains(&one) {
            where_to.push(one);
        }
    }
    if where_to.is_empty() && ear.is_none() {
        return None;
    }
    // A window too long to add is a year, which is as good as forever here.
    let now = Instant::now();
    let deadline = now
        .checked_add(window)
        .or_else(|| now.checked_add(Duration::from_secs(365 * 24 * 3600)))
        .unwrap_or(now);
    let shared = Arc::new(Punch {
        name: name.to_owned(),
        role,
        deadline,
        claimed: AtomicBool::new(false),
        stop: Event::default(),
    });
    let (won, winner) = mpsc::channel::<TcpStream>();
    for target in where_to {
        let (shared, won) = (Arc::clone(&shared), won.clone());
        let _ = thread::Builder::new()
            .name("rendezvous-knock".into())
            .spawn(move || knocking(target, port, &shared, &won));
    }
    if let Some(ear) = ear.and_then(|ear| ear.try_clone().ok()) {
        let (shared, won) = (Arc::clone(&shared), won.clone());
        let _ = thread::Builder::new()
            .name("rendezvous-ear".into())
            .spawn(move || answering(&ear, &shared, &won));
    }
    drop(won);
    let got = winner
        .recv_timeout(deadline.saturating_duration_since(Instant::now()))
        .ok();
    shared.stop.set();
    // Anything that arrives after the winner is closed as the receiver goes.
    got
}

/// Keeps opening outward at one candidate until something answers or time runs out
/// (`_knocking`).
fn knocking(target: SocketAddrV4, port: u16, shared: &Punch, won: &mpsc::Sender<TcpStream>) {
    while !shared.stop.is_set() && Instant::now() < shared.deadline {
        match knock(target, port, shared.deadline) {
            Ok(knocked) => {
                debug!("opened outward to {target}");
                greet(knocked, shared, won);
                return;
            }
            Err(e) => {
                debug!("knocked at {target} and got {e}");
                // A beat before the next one: a refused connection is instant, and a tight
                // loop would spend the window on syscalls.
                shared.stop.wait(Some(Duration::from_millis(50)));
            }
        }
    }
}

/// One knock: from this half's own port where it can be had, else from any.
fn knock(target: SocketAddrV4, port: u16, deadline: Instant) -> io::Result<TcpStream> {
    let made = outward()?;
    if bind_any(&made, port).is_err() {
        // Somebody else has this half's port this moment. The hole this opens is at another
        // port, so a NAT will not be punched -- but a neighbour is reached all the same.
        bind_any(&made, 0)?;
    }
    let made = TcpStream::from(made);
    let left = deadline.saturating_duration_since(Instant::now());
    let within = left.clamp(Duration::from_millis(200), Duration::from_secs(1));
    connect_within(&made, target, within)?;
    Ok(made)
}

/// Greets whatever arrives on the shared port, which is where the peer's punch lands
/// (`_answering`).
fn answering(ear: &TcpListener, shared: &Arc<Punch>, won: &mpsc::Sender<TcpStream>) {
    if ear.set_nonblocking(true).is_err() {
        return;
    }
    while !shared.stop.is_set() && Instant::now() < shared.deadline {
        let left = shared.deadline.saturating_duration_since(Instant::now());
        let wait = left.clamp(Duration::from_millis(100), Duration::from_millis(500));
        if !ready(ear.as_fd(), PollFlags::POLLIN, wait) {
            continue;
        }
        let Ok((arrived, _)) = ear.accept() else {
            continue;
        };
        debug!("something arrived on the shared port");
        // Accepted sockets inherit the listener's non-blocking flag on BSDs.
        if arrived.set_nonblocking(false).is_err() {
            continue;
        }
        let (shared, won) = (Arc::clone(shared), won.clone());
        let _ = thread::Builder::new()
            .name("rendezvous-greet".into())
            .spawn(move || greet(arrived, &shared, &won));
    }
}

/// Bytes split on ASCII whitespace as Python's `bytes.split()` splits them.
fn words(line: &[u8]) -> Vec<&[u8]> {
    line.split(|b| matches!(b, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c))
        .filter(|word| !word.is_empty())
        .collect()
}

/// Proves a connection is the other half of this session, and settles who keeps it
/// (`_greet`). Both ends say `HMZ1 <sha256(ticket)> <role>` first; then the anchoring half
/// offers `GO` on each socket it has and the serving half accepts exactly one with `OK`.
fn greet(punched: TcpStream, shared: &Punch, won: &mpsc::Sender<TcpStream>) {
    match greeting(&punched, shared) {
        Ok(true) => {
            // A failed send is a receiver already gone; the socket closes as it drops.
            let _ = won.send(punched);
        }
        Ok(false) => {}
        Err(e) => debug!("a greeting came to nothing: {e}"),
    }
}

fn greeting(punched: &TcpStream, shared: &Punch) -> io::Result<bool> {
    punched.set_write_timeout(Some(GREETING))?;
    let proof = hex::encode(Sha256::digest(shared.name.as_bytes()));
    let mut hello = Vec::with_capacity(80);
    hello.extend_from_slice(MAGIC);
    hello.push(b' ');
    hello.extend_from_slice(proof.as_bytes());
    hello.push(b' ');
    hello.extend_from_slice(shared.role.as_str().as_bytes());
    hello.push(b'\n');
    (&*punched).write_all(&hello)?;
    let line = read_line(punched, GREETING)?;
    let said = words(&line);
    let opposite = shared.role.opposite().as_str().as_bytes();
    if said.len() < 3 || said[0] != MAGIC || said[1] != proof.as_bytes() || said[2] != opposite {
        return Ok(false);
    }
    if shared.role == Role::Anchor {
        (&*punched).write_all(b"GO\n")?;
        if words(&read_line(punched, GREETING)?).first() != Some(&OK) {
            return Ok(false);
        }
    } else {
        if words(&read_line(punched, GREETING)?).first() != Some(&GO) {
            return Ok(false);
        }
        // Tested and taken in one step, so two offers arriving together cannot both be
        // answered, which would leave the two halves on two different sockets.
        if shared
            .claimed
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_err()
        {
            return Ok(false);
        }
        (&*punched).write_all(b"OK\n")?;
    }
    Ok(true)
}

// ------------------------------------------------------------------------------- sockets

/// Marks a descriptor close-on-exec, as every socket std opens is.
pub(crate) fn cloexec(fd: &OwnedFd) -> io::Result<()> {
    fcntl(fd, FcntlArg::F_SETFD(FdFlag::FD_CLOEXEC))?;
    Ok(())
}

/// A socket that may share the port every other socket of this session uses (`_outward`):
/// `SO_REUSEADDR`, and `SO_REUSEPORT` where the kernel has it.
fn outward() -> io::Result<OwnedFd> {
    let made = sock::socket(
        AddressFamily::Inet,
        SockType::Stream,
        SockFlag::empty(),
        None,
    )?;
    cloexec(&made)?;
    sock::setsockopt(&made, sock::sockopt::ReuseAddr, &true)?;
    let _ = sock::setsockopt(&made, sock::sockopt::ReusePort, &true);
    Ok(made)
}

/// Binds to `("", port)`: every interface, that port.
fn bind_any(fd: &OwnedFd, port: u16) -> io::Result<()> {
    let at = SockaddrIn::from(SocketAddrV4::new(Ipv4Addr::UNSPECIFIED, port));
    sock::bind(fd.as_raw_fd(), &at)?;
    Ok(())
}

/// The port a bound socket landed on.
fn port_of(fd: &OwnedFd) -> io::Result<u16> {
    let at: SockaddrIn = sock::getsockname(fd.as_raw_fd())?;
    Ok(at.port())
}

/// A socket to dial the broker from and a listener, sharing one port (`_both`).
///
/// The listener is bound first and the dialling socket to the port it landed on: taking an
/// ephemeral port by connecting and asking for it again is a race the second bind can lose.
/// Retried [`TRIES`] times; a half with no listener still punches outward.
fn both() -> io::Result<(OwnedFd, Option<TcpListener>, u16)> {
    for _ in 0..TRIES {
        let ear = outward()?;
        let shared = (|| -> io::Result<(OwnedFd, u16)> {
            bind_any(&ear, 0)?;
            sock::listen(&ear, Backlog::new(8)?)?;
            let port = port_of(&ear)?;
            let home = outward()?;
            bind_any(&home, port)?;
            Ok((home, port))
        })();
        match shared {
            Ok((home, port)) => return Ok((home, Some(TcpListener::from(ear)), port)),
            Err(e) => debug!("could not take a port for both halves of a punch: {e}"),
        }
    }
    let home = outward()?;
    bind_any(&home, 0)?;
    let port = port_of(&home)?;
    Ok((home, None, port))
}

/// Waits up to `wait` for `fd` to be ready for `events`.
fn ready(fd: std::os::fd::BorrowedFd<'_>, events: PollFlags, wait: Duration) -> bool {
    let millis = u16::try_from(wait.as_millis()).unwrap_or(u16::MAX);
    let mut fds = [PollFd::new(fd, events)];
    matches!(poll(&mut fds, PollTimeout::from(millis)), Ok(n) if n > 0)
}

/// `connect` with a deadline on an already-bound socket, as Python's `settimeout` then
/// `connect` does; the socket is left blocking either way.
fn connect_within(made: &TcpStream, target: SocketAddrV4, within: Duration) -> io::Result<()> {
    made.set_nonblocking(true)?;
    let result = connecting(made, target, within);
    made.set_nonblocking(false)?;
    result
}

fn connecting(made: &TcpStream, target: SocketAddrV4, within: Duration) -> io::Result<()> {
    match sock::connect(made.as_raw_fd(), &SockaddrIn::from(target)) {
        Ok(()) => return Ok(()),
        Err(Errno::EINPROGRESS | Errno::EINTR | Errno::EAGAIN) => {}
        Err(e) => return Err(e.into()),
    }
    let deadline = Instant::now().checked_add(within);
    loop {
        let left = match deadline {
            Some(deadline) => deadline.saturating_duration_since(Instant::now()),
            None => Duration::from_secs(3600),
        };
        if left.is_zero() {
            return Err(io::Error::new(io::ErrorKind::TimedOut, "timed out"));
        }
        let millis = i32::try_from(left.as_millis().max(1)).unwrap_or(i32::MAX);
        let mut fds = [PollFd::new(made.as_fd(), PollFlags::POLLOUT)];
        match poll(
            &mut fds,
            PollTimeout::try_from(millis).unwrap_or(PollTimeout::MAX),
        ) {
            Ok(0) => continue,
            Ok(_) => break,
            Err(Errno::EINTR) => continue,
            Err(e) => return Err(e.into()),
        }
    }
    match sock::getsockopt(made, sock::sockopt::SocketError)? {
        0 => Ok(()),
        code => Err(io::Error::from_raw_os_error(code)),
    }
}

/// Where the broker is, as an `AF_INET` socket's `connect` would resolve it.
fn resolve(host: &str, port: u16) -> io::Result<SocketAddrV4> {
    if let Some(ip) = inet_aton(host) {
        return Ok(SocketAddrV4::new(ip, port));
    }
    (host, port)
        .to_socket_addrs()?
        .find_map(|one| match one {
            SocketAddr::V4(v4) => Some(v4),
            SocketAddr::V6(_) => None,
        })
        .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "no IPv4 address for this host"))
}

/// Hands a socket on as the session wants it: blocking, nothing timing it out, and
/// `TCP_NODELAY` (`_settled`).
fn settled(held: TcpStream) -> io::Result<TcpStream> {
    held.set_nonblocking(false)?;
    held.set_read_timeout(None)?;
    held.set_write_timeout(None)?;
    held.set_nodelay(true)?;
    Ok(held)
}

/// Where this half says it can be reached, before the broker adds what it saw (`_mine`):
/// the address it reached the broker from, then its other names, all at `port`.
fn mine(home: &TcpStream, port: u16) -> io::Result<Vec<Candidate>> {
    let mut addresses = vec![home.local_addr()?.ip().to_string()];
    for address in named() {
        if !addresses.contains(&address) {
            addresses.push(address);
        }
    }
    Ok(addresses
        .into_iter()
        .map(|address| (address, json!(port)))
        .collect())
}

/// `getaddrinfo(name, None, AF_INET, SOCK_STREAM)`'s addresses, in its order. Asked for
/// IPv4 alone, as the Python asks, so a resolver slow to answer for IPv6 is not waited on.
fn ipv4_of(name: &std::ffi::OsStr) -> Vec<String> {
    use std::os::unix::ffi::OsStrExt;
    let Ok(name) = std::ffi::CString::new(name.as_bytes()) else {
        return Vec::new();
    };
    // SAFETY: an all-zero `addrinfo` is the documented way to start a set of hints.
    let mut hints: libc::addrinfo = unsafe { std::mem::zeroed() };
    hints.ai_family = libc::AF_INET;
    hints.ai_socktype = libc::SOCK_STREAM;
    let mut head = std::mem::MaybeUninit::<*mut libc::addrinfo>::uninit();
    // SAFETY: `name` is NUL-terminated, the service may be null, and the list it receives is
    // freed below and not used after.
    let failed =
        unsafe { libc::getaddrinfo(name.as_ptr(), std::ptr::null(), &hints, head.as_mut_ptr()) };
    if failed != 0 {
        return Vec::new();
    }
    // SAFETY: a successful getaddrinfo wrote the list's head, possibly null.
    let list = unsafe { head.assume_init() };
    let mut found = Vec::new();
    let mut at = list;
    // SAFETY: `at` is a node of the list `getaddrinfo` returned, which is still alive.
    while let Some(one) = unsafe { at.as_ref() } {
        if one.ai_family == libc::AF_INET && !one.ai_addr.is_null() {
            // SAFETY: an `AF_INET` entry's address is a `sockaddr_in`.
            let v4 = unsafe { &*(one.ai_addr as *const libc::sockaddr_in) };
            found.push(Ipv4Addr::from(u32::from_be(v4.sin_addr.s_addr)).to_string());
        }
        at = one.ai_next;
    }
    if !list.is_null() {
        // SAFETY: `list` came from a successful `getaddrinfo` and is freed once.
        unsafe { libc::freeaddrinfo(list) };
    }
    found
}

/// This machine's IPv4 addresses by its own name, or none if the name takes longer than
/// [`NAMING`] to resolve (`_named`): a Mac's `.local` name can take half a minute to fail.
fn named() -> Vec<String> {
    let (said, heard) = mpsc::channel();
    let asking = thread::Builder::new()
        .name("rendezvous-names".into())
        .spawn(move || {
            let found = nix::unistd::gethostname()
                .ok()
                .map(|name| ipv4_of(&name))
                .unwrap_or_default();
            let _ = said.send(found);
        });
    if asking.is_err() {
        return Vec::new();
    }
    heard.recv_timeout(NAMING).unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn words_split_as_bytes_split() {
        assert_eq!(
            words(b" HMZ1\t a\x0bserve\r"),
            vec![&b"HMZ1"[..], b"a", b"serve"]
        );
        assert!(words(b"   ").is_empty());
    }

    #[test]
    fn both_share_one_port() {
        let (home, ear, port) = both().unwrap();
        assert_eq!(port_of(&home).unwrap(), port);
        assert_eq!(ear.unwrap().local_addr().unwrap().port(), port);
    }

    #[test]
    fn a_connect_to_nothing_fails_quickly() {
        let gone = TcpListener::bind("127.0.0.1:0").unwrap();
        let at = match gone.local_addr().unwrap() {
            SocketAddr::V4(v4) => v4,
            SocketAddr::V6(_) => unreachable!(),
        };
        drop(gone);
        let made = TcpStream::from(outward().unwrap());
        assert!(connect_within(&made, at, Duration::from_secs(2)).is_err());
    }
}

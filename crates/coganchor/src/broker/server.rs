//! The broker's side of a meeting. Port of `Broker`, `_Pair`, `_splice` and `_pour` in
//! `hmz.coganchor.rendezvous`, and of `_rendezvous` in `hmz.cli.anchor`. [Unit 3]
//!
//! A thread per half being introduced, and nothing per session already under way unless the
//! broker is carrying it, which costs a thread per direction. Threads, not `async`: a half
//! spends nearly all of its time blocked on one socket, which is what a thread is for.

use std::collections::HashMap;
use std::io::{self, Read, Write};
use std::net::ToSocketAddrs;
use std::net::{Ipv4Addr, Shutdown, SocketAddr, SocketAddrV4, TcpListener, TcpStream};
use std::os::fd::OwnedFd;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, MutexGuard};
use std::thread;
use std::time::Duration;

use nix::sys::socket::{self as sock, AddressFamily, Backlog, SockFlag, SockType, SockaddrIn};
use serde_json::{Value, json};
use tracing::{debug, error, info};

use super::{
    ANSWERING, CONVINCED, Candidate, DISBELIEVING, Event, HOPELESS, PAIRING, RELAY, Role, TICKETS,
    ascii_json, candidates_json, pairs, python_float, python_str, read_object, say, truthy,
};
use crate::cli::BrokerArgs;
use crate::exit;

/// The stack a relaying thread gets. Small, because a broker carrying a fleet holds thousands
/// of them, and one does nothing but copy through a buffer on the heap.
const STACK: usize = 128 * 1024;

/// A broker listening for halves.
pub struct Broker {
    addr: SocketAddr,
    listener: TcpListener,
    state: Arc<State>,
}

/// What every half's thread shares: the meetings, and what the broker has learned.
struct State {
    /// How long one half waits for the other (`patience`).
    patience: Duration,
    /// How long the two are given to punch, in seconds as the wire says it (`punching`).
    punching: f64,
    tables: Mutex<Tables>,
    /// How many sessions this broker carried rather than introduced (`carried`).
    carried: AtomicU64,
}

#[derive(Default)]
struct Tables {
    /// The meetings in progress, by ticket (`_meetings`).
    meetings: HashMap<String, Arc<Pair>>,
    /// Pairs of machines, as the world addresses them, and how often they failed (`_failed`).
    failed: HashMap<(String, String), u64>,
}

impl Broker {
    /// Binds `host:port` (IPv4), giving halves `punching` to reach each other directly.
    pub fn bind(host: &str, port: u16, punching: Duration) -> io::Result<Broker> {
        let at = resolve(host, port)?;
        let listener = listening(at)?;
        let addr = listener.local_addr()?;
        Ok(Broker {
            addr,
            listener,
            state: Arc::new(State {
                patience: PAIRING,
                punching: punching.as_secs_f64(),
                tables: Mutex::new(Tables::default()),
                carried: AtomicU64::new(0),
            }),
        })
    }

    /// The same broker, with halves waiting `patience` for each other rather than
    /// [`PAIRING`] (`Broker(patience=...)`).
    pub fn with_patience(mut self, patience: Duration) -> Broker {
        if let Some(state) = Arc::get_mut(&mut self.state) {
            state.patience = patience;
        }
        self
    }

    /// The same broker, with the punching window given as the float the command line was,
    /// so the `punch` the halves are sent is the Python's to the byte.
    pub fn with_punching(mut self, seconds: f64) -> Broker {
        if let Some(state) = Arc::get_mut(&mut self.state) {
            state.punching = seconds;
        }
        self
    }

    /// The address it is bound to.
    pub fn local_addr(&self) -> SocketAddr {
        self.addr
    }

    /// How many sessions this broker had to carry rather than merely introduce.
    pub fn carried(&self) -> u64 {
        self.state.carried.load(Ordering::Relaxed)
    }

    /// Holds meetings until the process ends.
    pub fn serve_forever(self) -> io::Result<()> {
        info!(
            "rendezvous listening on {}:{}",
            self.addr.ip(),
            self.addr.port()
        );
        loop {
            let (half, whence) = match self.listener.accept() {
                Ok(accepted) => accepted,
                Err(e) if passing(&e) => {
                    debug!("could not accept a half: {e}");
                    // Out of descriptors, most likely, which a moment's sessions ending cures.
                    thread::sleep(Duration::from_millis(50));
                    continue;
                }
                Err(e) => return Err(e),
            };
            let SocketAddr::V4(whence) = whence else {
                continue;
            };
            let state = Arc::clone(&self.state);
            // The default stack, not [`STACK`]: this thread parses a line a stranger sent,
            // nested as deep as `serde_json` allows.
            let spawned = thread::Builder::new()
                .name("rendezvous".into())
                .spawn(move || state.introduce(half, whence));
            if let Err(e) = spawned {
                debug!("could not start a thread for a half: {e}");
            }
        }
    }
}

/// Whether an `accept` failure is one to wait out rather than stop on.
fn passing(e: &io::Error) -> bool {
    matches!(
        e.kind(),
        io::ErrorKind::Interrupted | io::ErrorKind::ConnectionAborted | io::ErrorKind::WouldBlock
    ) || matches!(
        e.raw_os_error(),
        Some(libc::EMFILE | libc::ENFILE | libc::ENOBUFS | libc::ENOMEM | libc::ECONNABORTED)
    )
}

/// `host` as an IPv4 address, resolving a name the way an `AF_INET` socket's `bind` does.
fn resolve(host: &str, port: u16) -> io::Result<SocketAddrV4> {
    if let Ok(ip) = host.parse::<Ipv4Addr>() {
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

/// A listener with `SO_REUSEADDR`, bound to `at`, with as deep a backlog as the kernel gives
/// (`_BACKLOG = SOMAXCONN`): a fleet coming up brings two halves per agent at once, and a
/// connection the backlog drops is a session whose other half never arrived.
fn listening(at: SocketAddrV4) -> io::Result<TcpListener> {
    let fd: OwnedFd = sock::socket(
        AddressFamily::Inet,
        SockType::Stream,
        SockFlag::empty(),
        None,
    )?;
    super::peer::cloexec(&fd)?;
    sock::setsockopt(&fd, sock::sockopt::ReuseAddr, &true)?;
    sock::bind(std::os::fd::AsRawFd::as_raw_fd(&fd), &SockaddrIn::from(at))?;
    sock::listen(&fd, Backlog::MAXCONN)?;
    Ok(TcpListener::from(fd))
}

fn locked<T>(m: &Mutex<T>) -> MutexGuard<'_, T> {
    m.lock().unwrap_or_else(|e| e.into_inner())
}

impl State {
    /// Takes one half from its first word to its last, whichever way it ends (`_introduce`).
    fn introduce(self: Arc<Self>, half: TcpStream, whence: SocketAddrV4) {
        let mut pair = None;
        let mut role = None;
        if let Err(e) = self.introducing(&half, whence, &mut pair, &mut role) {
            debug!(
                "a half of {} left: {e}",
                role.map_or("a meeting", Role::as_str)
            );
        }
        if let (Some(pair), Some(role)) = (pair, role) {
            self.forget(&pair, role);
        }
        drop(half);
    }

    fn introducing(
        &self,
        half: &TcpStream,
        whence: SocketAddrV4,
        pair_out: &mut Option<Arc<Pair>>,
        role_out: &mut Option<Role>,
    ) -> io::Result<()> {
        let hello = read_object(half, ANSWERING)?;
        let name = python_str(hello.get("ticket"));
        let role = hello
            .get("role")
            .and_then(Value::as_str)
            .and_then(Role::parse);
        let Some(role) = role.filter(|_| !name.is_empty()) else {
            return say(half, &json!({"go": "no", "why": "say a ticket and a role"}));
        };
        *role_out = Some(role);
        // Its own address as the world has it, which is the one fact about a machine behind a
        // NAT that only somebody outside it can supply.
        let seen_ip = whence.ip().to_string();
        say(half, &json!({"seen": [seen_ip, whence.port()]}))?;
        let mut mine = pairs(hello.get("at"));
        mine.push((seen_ip, json!(whence.port())));
        let Some(pair) = self.join(&name, role, half.try_clone()?, mine) else {
            return say(
                half,
                &json!({
                    "go": "no",
                    "why": format!("this rendezvous is already holding {TICKETS} meetings"),
                }),
            );
        };
        *pair_out = Some(Arc::clone(&pair));
        let Some(other) = pair.await_other(role, self.patience) else {
            return say(
                half,
                &json!({"go": "no", "why": "the other half never arrived"}),
            );
        };
        let between = pair.between();
        let punching = if self.worth(between.as_ref()) {
            self.punching
        } else {
            0.0
        };
        // Spelled out, so the float is written as `json.dumps` writes it (`1e-07`, not `1e-7`).
        let peer = format!(
            "{{\"peer\":{},\"punch\":{}}}\n",
            ascii_json(&candidates_json(&other)),
            python_float(punching)
        );
        (&*half).write_all(peer.as_bytes())?;
        let patience = super::seconds(punching + ANSWERING.as_secs_f64());
        let direct = truthy(read_object(half, patience)?.get("direct"));
        let joined = pair.settle(role, direct, ANSWERING);
        if role == Role::Anchor {
            // Before the half is told, so that what this pair came to is what the next pair
            // of the same two machines is judged by, however soon that one comes.
            self.learn(between.as_ref(), joined);
            if !joined {
                self.carried.fetch_add(1, Ordering::Relaxed);
            }
        }
        say(
            half,
            &json!({"go": if joined { "direct" } else { "relay" }}),
        )?;
        pair.spoke(role);
        if !joined {
            pair.carry(role);
        }
        Ok(())
    }

    /// Whether these two are worth trying to introduce, or have failed too lately (`_worth`).
    fn worth(&self, between: Option<&(String, String)>) -> bool {
        let Some(between) = between else {
            return true;
        };
        let failed = locked(&self.tables)
            .failed
            .get(between)
            .copied()
            .unwrap_or(0);
        // And every so often after that, because a firewall rule is the kind of thing that
        // changes: the modulus answers the attempt after every sixteenth failure.
        failed < CONVINCED || failed % DISBELIEVING == 0
    }

    /// Remembers how that went, so the next pair of these two need not find out (`_learn`).
    fn learn(&self, between: Option<&(String, String)>, worked: bool) {
        let Some(between) = between else {
            return;
        };
        let mut tables = locked(&self.tables);
        if worked {
            tables.failed.remove(between);
        } else if tables.failed.contains_key(between) || tables.failed.len() < HOPELESS {
            *tables.failed.entry(between.clone()).or_insert(0) += 1;
        }
    }

    /// Puts one half into its meeting, making the meeting if it is the first (`_join`).
    fn join(
        &self,
        name: &str,
        role: Role,
        half: TcpStream,
        mine: Vec<Candidate>,
    ) -> Option<Arc<Pair>> {
        let pair = {
            let mut tables = locked(&self.tables);
            match tables.meetings.get(name) {
                Some(pair) => Arc::clone(pair),
                None => {
                    if tables.meetings.len() >= TICKETS {
                        return None;
                    }
                    let pair = Arc::new(Pair::new(name));
                    tables.meetings.insert(name.to_owned(), Arc::clone(&pair));
                    pair
                }
            }
        };
        pair.arrive(role, half, mine);
        Some(pair)
    }

    /// Takes a meeting away once the last half of it has gone (`_forget`).
    fn forget(&self, pair: &Arc<Pair>, role: Role) {
        if pair.leave(role) {
            let mut tables = locked(&self.tables);
            if tables
                .meetings
                .get(&pair.name)
                .is_some_and(|held| Arc::ptr_eq(held, pair))
            {
                tables.meetings.remove(&pair.name);
            }
        }
    }
}

/// One meeting: its two halves, and everything either is waiting on the other for (`_Pair`).
struct Pair {
    name: String,
    inner: Mutex<PairInner>,
    /// Set when that half has said what it is and where it can be reached.
    arrived: [Event; 2],
    /// Set when it has said whether it got through.
    answered: [Event; 2],
    /// Set once that half has been told how the session will be joined.
    told: [Event; 2],
    /// Set once the bytes have finished flowing.
    done: Event,
}

#[derive(Default)]
struct PairInner {
    halves: HashMap<Role, TcpStream>,
    theirs: HashMap<Role, Vec<Candidate>>,
    verdicts: HashMap<Role, bool>,
    /// Where each half is as the broker saw it, which is how a pair of machines is named.
    seen: HashMap<Role, String>,
    /// Direct or not, once the first of them has been told.
    joined: Option<bool>,
}

fn ix(role: Role) -> usize {
    match role {
        Role::Anchor => 0,
        Role::Serve => 1,
    }
}

impl Pair {
    fn new(name: &str) -> Pair {
        Pair {
            name: name.to_owned(),
            inner: Mutex::new(PairInner::default()),
            arrived: Default::default(),
            answered: Default::default(),
            told: Default::default(),
            done: Event::default(),
        }
    }

    fn arrive(&self, role: Role, half: TcpStream, mine: Vec<Candidate>) {
        {
            let mut inner = locked(&self.inner);
            inner.halves.insert(role, half);
            // The last of them is the one the world has: the broker's own view is appended.
            let seen = mine
                .last()
                .map(|(host, _)| host.clone())
                .unwrap_or_default();
            inner.seen.insert(role, seen);
            inner.theirs.insert(role, mine);
        }
        self.arrived[ix(role)].set();
    }

    /// The two machines, sorted, as the world addresses them; None until both have spoken.
    fn between(&self) -> Option<(String, String)> {
        let inner = locked(&self.inner);
        if inner.seen.len() != 2 {
            return None;
        }
        let mut both: Vec<String> = inner.seen.values().cloned().collect();
        both.sort();
        let other = both.pop()?;
        let one = both.pop()?;
        Some((one, other))
    }

    /// Waits for the other half and answers with where it may be reached (`await_other`).
    fn await_other(&self, role: Role, patience: Duration) -> Option<Vec<Candidate>> {
        let other = role.opposite();
        if !self.arrived[ix(other)].wait(Some(patience)) {
            return None;
        }
        Some(
            locked(&self.inner)
                .theirs
                .get(&other)
                .cloned()
                .unwrap_or_default(),
        )
    }

    /// Whether the session goes direct, which needs both to say so; decided once, by whichever
    /// half is told first, and the same answer for the other (`settle`).
    fn settle(&self, role: Role, direct: bool, patience: Duration) -> bool {
        locked(&self.inner).verdicts.insert(role, direct);
        self.answered[ix(role)].set();
        let heard = self.answered[ix(role.opposite())].wait(Some(patience));
        let mut inner = locked(&self.inner);
        if inner.joined.is_none() {
            let both = [Role::Anchor, Role::Serve]
                .iter()
                .all(|one| inner.verdicts.get(one).copied().unwrap_or(false));
            inner.joined = Some(heard && both);
        }
        inner.joined.unwrap_or(false)
    }

    /// Says that half has been told how the session will be joined (`spoke`).
    fn spoke(&self, role: Role) {
        self.told[ix(role)].set();
    }

    /// Moves the bytes between the two, for a pair that could not be introduced (`carry`).
    ///
    /// The anchor's thread carries and the serve's waits for it, so neither socket is closed
    /// from under the splice. And the carrying waits until the serve half has been told a
    /// splice is coming: otherwise the session's first bytes could reach it while it is still
    /// reading a control line one byte at a time, and the stream would be shifted for good.
    fn carry(&self, role: Role) {
        if role != Role::Anchor {
            self.done.wait(None);
            return;
        }
        self.told[ix(Role::Serve)].wait(Some(ANSWERING));
        let (here, there) = {
            let inner = locked(&self.inner);
            let clone = |r| inner.halves.get(&r).and_then(|h| h.try_clone().ok());
            (clone(Role::Anchor), clone(Role::Serve))
        };
        if let (Some(here), Some(there)) = (here, there) {
            splice(here, there);
        }
        self.done.set();
    }

    /// Takes one half out, and says whether that was the last of them (`leave`).
    fn leave(&self, role: Role) -> bool {
        // Whoever goes first releases the other from waiting on a splice that is not coming.
        self.done.set();
        self.told[ix(role)].set();
        self.answered[ix(role)].set();
        self.arrived[ix(role)].set();
        let mut inner = locked(&self.inner);
        inner.halves.remove(&role);
        inner.halves.is_empty()
    }
}

/// Carries bytes each way until both ends have stopped, then shuts the two down (`_splice`).
///
/// A thread per direction, because one loop blocked writing one way is not reading the other,
/// and two ends both mid-transfer would wait on each other. Both sockets are made blocking
/// with no timeout first: a write that timed out mid-frame would shift the session for good.
fn splice(one: TcpStream, two: TcpStream) {
    for end in [&one, &two] {
        let _ = end.set_read_timeout(None);
        let _ = end.set_write_timeout(None);
        let _ = end.set_nonblocking(false);
    }
    let back = match (two.try_clone(), one.try_clone()) {
        (Ok(source), Ok(sink)) => thread::Builder::new()
            .name("rendezvous-relay".into())
            .stack_size(STACK)
            .spawn(move || pour(&source, &sink))
            .ok(),
        _ => None,
    };
    if back.is_none() {
        // Nothing can carry the other way, so neither way is carried.
        let _ = one.shutdown(Shutdown::Both);
        let _ = two.shutdown(Shutdown::Both);
        return;
    }
    pour(&one, &two);
    if let Some(back) = back {
        let _ = back.join();
    }
    let _ = one.shutdown(Shutdown::Both);
    let _ = two.shutdown(Shutdown::Both);
}

/// Moves everything one way, then half-closes the far end so it knows that was the last of
/// it, one direction ending not being the session ending (`_pour`).
fn pour(source: &TcpStream, sink: &TcpStream) {
    let mut moving = vec![0u8; RELAY];
    loop {
        let got = match (&*source).read(&mut moving) {
            Ok(0) => break,
            Ok(got) => got,
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(_) => break,
        };
        if (&*sink).write_all(&moving[..got]).is_err() {
            break;
        }
    }
    let _ = sink.shutdown(Shutdown::Write);
}

/// `[HOST:]PORT` as `_listen_on` reads it: a bare port takes `default` for the host.
fn listen_on(spec: &str, default: &str) -> Option<(String, u16)> {
    let (host, port) = match spec.rsplit_once(':') {
        Some((host, port)) => (host, port),
        None => (default, spec),
    };
    let host = host.trim_matches(['[', ']']);
    let host = if host.is_empty() { default } else { host };
    if port.is_empty() || !port.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    let port = port.parse::<u16>().ok()?;
    Some((host.to_owned(), port))
}

/// What Python's `OSError.strerror` would say for this failure.
fn strerror(e: &io::Error) -> String {
    match e.raw_os_error() {
        Some(code) => nix::errno::Errno::from_raw(code).desc().to_owned(),
        None => {
            let said = e.to_string();
            said.strip_prefix("failed to lookup address information: ")
                .unwrap_or(&said)
                .to_owned()
        }
    }
}

/// `coganchor broker`, writing `hmz internal anchor rendezvous listening BOUND LANDED`.
///
/// `BOUND` is the host it is bound to and `LANDED` the port it landed on, a port of 0 having
/// been the way to ask for any free one; whoever started this reads the port off that line.
pub fn main(args: BrokerArgs) -> i32 {
    crate::log::init(args.log_level.as_deref(), "info");
    // Every interface by default: the halves being introduced are on other machines.
    let Some((host, port)) = listen_on(&args.listen, "0.0.0.0") else {
        crate::log::say(format!(
            "malformed listen address '{}'; expected [HOST:]PORT",
            args.listen
        ));
        return exit::USAGE;
    };
    let broker = match Broker::bind(&host, port, super::seconds(args.punching)) {
        Ok(broker) => broker.with_punching(args.punching),
        Err(e) => return exit::failed(format!("cannot listen on {host}:{port}: {}", strerror(&e))),
    };
    let bound = broker.local_addr();
    {
        let mut err = io::stderr().lock();
        let _ = writeln!(
            err,
            "hmz internal anchor rendezvous listening {} {}",
            bound.ip(),
            bound.port()
        );
        let _ = err.flush();
    }
    // Ctrl-C ends it with 0, as the Python's `KeyboardInterrupt` does: SIGINT is blocked here,
    // before any thread exists to inherit it unblocked, and taken synchronously below.
    let mut interrupt = nix::sys::signal::SigSet::empty();
    interrupt.add(nix::sys::signal::Signal::SIGINT);
    if let Err(e) = interrupt.thread_block() {
        return exit::failed(format!("cannot wait for an interrupt: {e}"));
    }
    let serving = thread::Builder::new()
        .name("rendezvous".into())
        .spawn(move || {
            if let Err(e) = broker.serve_forever() {
                // As the Python's accepting thread: it stops, and the process waits on.
                error!("rendezvous stopped accepting: {e}");
            }
        });
    if let Err(e) = serving {
        return exit::failed(format!("cannot start the rendezvous: {e}"));
    }
    let _ = interrupt.wait();
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn listen_addresses_read_as_python_reads_them() {
        let read = |s| listen_on(s, "0.0.0.0");
        assert_eq!(read("9000"), Some(("0.0.0.0".into(), 9000)));
        assert_eq!(read("127.0.0.1:0"), Some(("127.0.0.1".into(), 0)));
        assert_eq!(read(":5"), Some(("0.0.0.0".into(), 5)));
        assert_eq!(read("[::1]:5"), Some(("::1".into(), 5)));
        for bad in ["nope", "h:", "h:x", "h:65536", "", "h:-1"] {
            assert_eq!(read(bad), None, "{bad}");
        }
    }

    #[test]
    fn truthiness_is_pythons() {
        assert!(truthy(Some(&json!(true))));
        assert!(truthy(Some(&json!(1))));
        assert!(truthy(Some(&json!("false"))));
        assert!(!truthy(Some(&json!(0))));
        assert!(!truthy(Some(&json!(""))));
        assert!(!truthy(None));
        assert!(!truthy(Some(&Value::Null)));
    }

    #[test]
    fn a_hopeless_pair_is_tried_again_now_and_then() {
        let state = State {
            patience: PAIRING,
            punching: 4.0,
            tables: Mutex::new(Tables::default()),
            carried: AtomicU64::new(0),
        };
        let pair = ("1.1.1.1".to_owned(), "2.2.2.2".to_owned());
        let mut worth = Vec::new();
        for _ in 0..33 {
            worth.push(state.worth(Some(&pair)));
            state.learn(Some(&pair), false);
        }
        let tried: Vec<usize> = (0..33).filter(|&i| worth[i]).collect();
        assert_eq!(tried, vec![0, 1, 2, 16, 32]);
        state.learn(Some(&pair), true);
        assert!(state.worth(Some(&pair)));
        assert!(state.worth(None));
    }

    #[test]
    fn strerror_is_the_bare_reason() {
        let e = io::Error::from_raw_os_error(libc::EADDRINUSE);
        assert_eq!(strerror(&e), "Address already in use");
    }

    #[test]
    fn an_ip_is_seen_as_ipv4() {
        assert_eq!(
            resolve("127.0.0.1", 1).unwrap(),
            SocketAddrV4::new(Ipv4Addr::LOCALHOST, 1)
        );
    }
}

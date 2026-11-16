//! Unit 3: two halves meeting through a real broker on loopback, as
//! `tests/integration/test_anchor_rendezvous.py` has two Python halves meet.
//!
//! Both halves are this machine, so whether a pair given a window ends up punched through or
//! carried depends on whether the kernel lends one port to two sockets; what is checked is
//! that they are joined either way, and that a broker given no window carries them.

use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpStream;
use std::process::{Command, Stdio};
use std::thread;
use std::time::Duration;

use coganchor::broker::{Broker, Meeting, Role, dial};

const PATIENCE: Duration = Duration::from_secs(20);

fn broker(punching: Duration) -> Meeting {
    serving(Broker::bind("127.0.0.1", 0, punching).unwrap())
}

fn serving(broker: Broker) -> Meeting {
    let at = broker.local_addr();
    thread::spawn(move || broker.serve_forever());
    Meeting::fresh(&at.ip().to_string(), at.port())
}

/// Both halves of one meeting, dialled at once from two threads.
fn met(meeting: &Meeting) -> (TcpStream, TcpStream) {
    let halves: Vec<_> = [Role::Anchor, Role::Serve]
        .into_iter()
        .map(|role| {
            let meeting = meeting.clone();
            thread::spawn(move || dial(&meeting, role, PATIENCE))
        })
        .collect();
    let mut joined = halves.into_iter().map(|h| h.join().unwrap().unwrap());
    let anchor = joined.next().unwrap();
    let serve = joined.next().unwrap();
    // As `dial` hands them on: blocking, with nothing timing them out, and TCP_NODELAY.
    for half in [&anchor, &serve] {
        assert_eq!(half.read_timeout().unwrap(), None);
        assert_eq!(half.write_timeout().unwrap(), None);
        assert!(half.nodelay().unwrap());
    }
    anchor.set_read_timeout(Some(PATIENCE)).unwrap();
    serve.set_read_timeout(Some(PATIENCE)).unwrap();
    (anchor, serve)
}

fn talks_both_ways(mut anchor: TcpStream, mut serve: TcpStream) {
    anchor.write_all(b"ping").unwrap();
    let mut got = [0u8; 4];
    serve.read_exact(&mut got).unwrap();
    assert_eq!(&got, b"ping");
    serve.write_all(b"pong").unwrap();
    anchor.read_exact(&mut got).unwrap();
    assert_eq!(&got, b"pong");
}

#[test]
fn two_halves_are_joined_and_talk_both_ways() {
    let (anchor, serve) = met(&broker(Duration::from_millis(500)));
    talks_both_ways(anchor, serve);
}

#[test]
fn a_pair_given_no_window_is_carried_whole() {
    let meeting = broker(Duration::ZERO);
    let (mut anchor, mut serve) = met(&meeting);
    // Carried means both are talking to the broker.
    assert_eq!(anchor.peer_addr().unwrap().port(), meeting.port);
    assert_eq!(serve.peer_addr().unwrap().port(), meeting.port);
    let big: Vec<u8> = (0..300_000u32).map(|i| i as u8).collect();
    let sending = big.clone();
    let writer = thread::spawn(move || {
        anchor.write_all(&sending).unwrap();
        // The half-close is carried across too.
        anchor.shutdown(std::net::Shutdown::Write).unwrap();
        anchor
    });
    let mut got = Vec::new();
    serve.read_to_end(&mut got).unwrap();
    assert_eq!(got, big);
    let mut anchor = writer.join().unwrap();
    serve.write_all(b"back").unwrap();
    let mut back = [0u8; 4];
    anchor.read_exact(&mut back).unwrap();
    assert_eq!(&back, b"back");
}

#[test]
fn two_meetings_at_one_broker_stay_two_sessions() {
    let one = broker(Duration::from_millis(500));
    let two = Meeting::fresh(&one.host, one.port);
    let (a, b) = (one.clone(), two.clone());
    let first = thread::spawn(move || met(&a));
    let second = thread::spawn(move || met(&b));
    let (mut a1, mut s1) = first.join().unwrap();
    let (mut a2, mut s2) = second.join().unwrap();
    a1.write_all(b"one").unwrap();
    a2.write_all(b"two").unwrap();
    let mut got = [0u8; 3];
    s1.read_exact(&mut got).unwrap();
    assert_eq!(&got, b"one");
    s2.read_exact(&mut got).unwrap();
    assert_eq!(&got, b"two");
}

#[test]
fn a_half_whose_other_half_never_comes_is_told_so() {
    let broker = Broker::bind("127.0.0.1", 0, Duration::from_millis(500))
        .unwrap()
        .with_patience(Duration::from_millis(300));
    let meeting = serving(broker);
    let failed = dial(&meeting, Role::Anchor, Duration::from_secs(5)).unwrap_err();
    assert_eq!(failed.to_string(), "the other half never arrived");
}

#[test]
fn a_half_that_is_neither_half_is_refused() {
    let meeting = broker(Duration::from_millis(500));
    let mut raw = TcpStream::connect((meeting.host.as_str(), meeting.port)).unwrap();
    raw.set_read_timeout(Some(PATIENCE)).unwrap();
    raw.write_all(b"{\"ticket\":\"t\",\"role\":\"spy\",\"at\":[]}\n")
        .unwrap();
    let mut said = String::new();
    raw.read_to_string(&mut said).unwrap();
    assert_eq!(
        said,
        "{\"go\":\"no\",\"why\":\"say a ticket and a role\"}\n"
    );
}

#[test]
fn the_broker_says_where_each_half_is_seen_and_the_peer() {
    let meeting = broker(Duration::ZERO);
    let speak = |role: &str| {
        let mut raw = TcpStream::connect((meeting.host.as_str(), meeting.port)).unwrap();
        raw.set_read_timeout(Some(PATIENCE)).unwrap();
        let hello = format!(
            "{{\"ticket\":\"{}\",\"role\":\"{role}\",\"at\":[[\"10.0.0.1\",7],[\"10.0.0.1\",7],[\"::1\",7]]}}\n",
            meeting.ticket
        );
        raw.write_all(hello.as_bytes()).unwrap();
        raw
    };
    let anchor = speak("anchor");
    let serve = speak("serve");
    let mut lines = BufReader::new(anchor.try_clone().unwrap());
    let mut seen = String::new();
    lines.read_line(&mut seen).unwrap();
    let port = anchor.local_addr().unwrap().port();
    assert_eq!(seen, format!("{{\"seen\":[\"127.0.0.1\",{port}]}}\n"));
    let mut peer = String::new();
    lines.read_line(&mut peer).unwrap();
    let theirs = serve.local_addr().unwrap().port();
    assert_eq!(
        peer,
        format!("{{\"peer\":[[\"10.0.0.1\",7],[\"127.0.0.1\",{theirs}]],\"punch\":0.0}}\n")
    );
}

/// The `coganchor broker` command line: the line it announces itself with, and a malformed
/// address refused with status 2.
#[test]
fn the_command_line_announces_where_it_listens() {
    let bin = env!("CARGO_BIN_EXE_coganchor");
    let refused = Command::new(bin)
        .args(["broker", "--listen", "nope"])
        .output()
        .unwrap();
    assert_eq!(refused.status.code(), Some(2));
    assert_eq!(
        String::from_utf8_lossy(&refused.stderr),
        "hmz: malformed listen address 'nope'; expected [HOST:]PORT\n"
    );

    let mut running = Command::new(bin)
        .args(["broker", "--listen", "127.0.0.1:0", "--log-level", "error"])
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let mut first = String::new();
    BufReader::new(running.stderr.take().unwrap())
        .read_line(&mut first)
        .unwrap();
    let words: Vec<&str> = first.split_whitespace().collect();
    assert_eq!(
        words[..5],
        ["hmz", "internal", "anchor", "rendezvous", "listening"]
    );
    assert_eq!(words[5], "127.0.0.1");
    let port: u16 = words[6].parse().unwrap();
    let meeting = Meeting::fresh("127.0.0.1", port);
    let (anchor, serve) = met(&meeting);
    talks_both_ways(anchor, serve);

    // Ctrl-C ends it with 0.
    nix::sys::signal::kill(
        nix::unistd::Pid::from_raw(running.id() as i32),
        nix::sys::signal::Signal::SIGINT,
    )
    .unwrap();
    assert_eq!(running.wait().unwrap().code(), Some(0));
}

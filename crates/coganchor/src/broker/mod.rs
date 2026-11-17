//! The broker: where two halves meet when neither can dial the other. Port of
//! `hmz.coganchor.rendezvous` and `hmz internal anchor rendezvous`. [Unit 3]
//!
//! A ticket names a meeting. Each half dials the broker with a name derived from it
//! ([`crate::tls::meeting_name`]; the ticket itself is the secret the halves prove to each
//! other inside TLS, and never leaves either) and says which half it is; the broker tells each
//! what the other looks like from outside, starts them at each other at the same instant (hole
//! punching), and carries the bytes itself, still encrypted, where they cannot meet.
//!
//! The broker's wire is one compact JSON object per `\n`-terminated line, read a byte at a
//! time so that nothing of the session that may follow is ever buffered:
//!
//! 1. half: `{"ticket":NAME,"role":"anchor"|"serve","at":[[ip,port],...]}`
//! 2. broker: `{"seen":[ip,port]}` (or `{"go":"no","why":...}`)
//! 3. broker: `{"peer":[[ip,port],...],"punch":SECONDS}` (or `{"go":"no","why":...}`)
//! 4. half, after punching: `{"direct":true|false}`
//! 5. broker: `{"go":"direct"|"relay"}`, and on `relay` the two connections are spliced.

pub mod peer;
pub mod server;

use std::fmt;
use std::io::{self, Read, Write};
use std::net::{Ipv4Addr, TcpStream};
use std::sync::{Condvar, Mutex};
use std::time::{Duration, Instant};

use serde_json::{Map, Value};

pub use peer::dial;
pub use server::Broker;

use crate::cli::BrokerArgs;

/// Which half of a session is dialling.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Role {
    /// The cog's side, spelled `"anchor"` on the wire as the Python half named it.
    Anchor,
    /// The anchor's side, spelled `"serve"` on the wire.
    Serve,
}

impl Role {
    /// Reads a role off the wire, accepting exactly the two of `ROLES`.
    pub fn parse(said: &str) -> Option<Role> {
        match said {
            "anchor" => Some(Role::Anchor),
            "serve" => Some(Role::Serve),
            _ => None,
        }
    }

    /// The other half (`_OPPOSITE`).
    pub fn opposite(self) -> Role {
        match self {
            Role::Anchor => Role::Serve,
            Role::Serve => Role::Anchor,
        }
    }

    /// The role as the broker's line protocol spells it.
    pub fn as_str(self) -> &'static str {
        match self {
            Role::Anchor => "anchor",
            Role::Serve => "serve",
        }
    }
}

/// A meeting at a broker: `TICKET@HOST:PORT`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Meeting {
    pub ticket: String,
    pub host: String,
    pub port: u16,
}

impl Meeting {
    /// Reads `TICKET@HOST:PORT` (split at the first `@`, then the last `:`, `[]` stripped),
    /// as `Meeting.parse` does.
    pub fn parse(said: &str) -> Result<Meeting, String> {
        let malformed = || format!("malformed meeting '{said}'; expected TICKET@HOST:PORT");
        // `spec.partition("@")`, then `authority.rpartition(":")`.
        let (name, authority) = said.split_once('@').ok_or_else(malformed)?;
        let (host, port) = authority.rsplit_once(':').ok_or_else(malformed)?;
        if name.is_empty()
            || host.is_empty()
            || port.is_empty()
            || !port.bytes().all(|b| b.is_ascii_digit())
        {
            return Err(malformed());
        }
        let port = port.parse::<u16>().map_err(|_| malformed())?;
        Ok(Meeting {
            ticket: name.to_owned(),
            host: host.trim_matches(['[', ']']).to_owned(),
            port,
        })
    }

    /// A new, unguessable ticket at this broker: 32 hex digits.
    pub fn fresh(host: &str, port: u16) -> Meeting {
        Meeting {
            ticket: ticket(),
            host: host.to_owned(),
            port,
        }
    }
}

impl fmt::Display for Meeting {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}@{}:{}", self.ticket, self.host, self.port)
    }
}

/// `coganchor broker`: listen, say so, and hold meetings until interrupted.
pub fn main(args: BrokerArgs) -> i32 {
    server::main(args)
}

// ------------------------------------------------------------------------------ constants

/// How long a half waits at the broker for the other one to arrive (`PAIRING`).
pub const PAIRING: Duration = Duration::from_secs(120);

/// How long the two spend opening holes at each other before being carried (`PUNCHING`).
pub const PUNCHING: Duration = Duration::from_secs(4);

/// How long one punched socket has to prove it is the other half (`GREETING`).
pub const GREETING: Duration = Duration::from_secs(3);

/// How long a half waits for its own machine's name to resolve (`_NAMING`).
pub(crate) const NAMING: Duration = Duration::from_secs(1);

/// How long a half waits on the broker's own answers (`_ANSWERING`).
pub(crate) const ANSWERING: Duration = Duration::from_secs(30);

/// How many goes at taking one port for the two sockets that need it (`_TRIES`).
pub(crate) const TRIES: usize = 8;

/// How many tickets one broker holds at once (`_TICKETS`).
pub(crate) const TICKETS: usize = 1 << 16;

/// How many failed pairs of machines a broker remembers (`_HOPELESS`).
pub(crate) const HOPELESS: usize = 1024;

/// How often a pair believed hopeless is tried again anyway (`_DISBELIEVING`).
pub(crate) const DISBELIEVING: u64 = 16;

/// How many failures it takes before a pair is believed hopeless (`_CONVINCED`).
pub(crate) const CONVINCED: u64 = 3;

/// What goes across a punched socket before anything else (`_MAGIC`).
pub(crate) const MAGIC: &[u8] = b"HMZ1";

/// The anchoring half's offer on the socket it chose (`_GO`).
pub(crate) const GO: &[u8] = b"GO";

/// The serving half's acceptance of exactly one offer (`_OK`).
pub(crate) const OK: &[u8] = b"OK";

/// The most a line of this protocol may be (`_LINE`).
pub(crate) const LINE: usize = 1 << 16;

/// How much is moved at a time when the broker carries a session (`_RELAY`).
pub(crate) const RELAY: usize = 1 << 16;

/// Mints a ticket: 16 random bytes as 32 hex digits (`ticket()`, `secrets.token_hex(16)`).
pub fn ticket() -> String {
    hex::encode(rand::random::<[u8; 16]>())
}

// ------------------------------------------------------------------------ shared plumbing

/// A `threading.Event`: set once, waited on by anyone.
#[derive(Default)]
pub(crate) struct Event {
    set: Mutex<bool>,
    changed: Condvar,
}

impl Event {
    pub(crate) fn set(&self) {
        *self.set.lock().unwrap_or_else(|e| e.into_inner()) = true;
        self.changed.notify_all();
    }

    pub(crate) fn is_set(&self) -> bool {
        *self.set.lock().unwrap_or_else(|e| e.into_inner())
    }

    /// Waits until it is set or `patience` passes (forever for `None`); says whether it is.
    pub(crate) fn wait(&self, patience: Option<Duration>) -> bool {
        let guard = self.set.lock().unwrap_or_else(|e| e.into_inner());
        match patience {
            None => *self
                .changed
                .wait_while(guard, |set| !*set)
                .unwrap_or_else(|e| e.into_inner()),
            Some(patience) => {
                *self
                    .changed
                    .wait_timeout_while(guard, patience, |set| !*set)
                    .unwrap_or_else(|e| e.into_inner())
                    .0
            }
        }
    }
}

/// Seconds as a `Duration`, a negative number being none at all and a huge one forever.
pub(crate) fn seconds(said: f64) -> Duration {
    Duration::try_from_secs_f64(said.max(0.0)).unwrap_or(Duration::MAX)
}

/// An error that says what went wrong, as the Python's `ConnectionError(why)` does.
pub(crate) fn refused(why: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::ConnectionAborted, why.into())
}

/// One newline-terminated line, read a byte at a time so nothing after it is buffered
/// (`_line`). Fails on end of stream, on the deadline, and on a line longer than [`LINE`].
pub(crate) fn read_line(sock: &TcpStream, timeout: Duration) -> io::Result<Vec<u8>> {
    let ends = Instant::now().checked_add(timeout);
    let mut held = Vec::new();
    let mut byte = [0u8; 1];
    loop {
        let left = match ends {
            Some(ends) => ends.saturating_duration_since(Instant::now()),
            None => timeout,
        };
        sock.set_read_timeout(Some(left.max(Duration::from_millis(10))))?;
        let got = match (&*sock).read(&mut byte) {
            Ok(got) => got,
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(e) if e.kind() == io::ErrorKind::WouldBlock => {
                return Err(io::Error::new(io::ErrorKind::TimedOut, "timed out"));
            }
            Err(e) => return Err(e),
        };
        if got == 0 {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "the other end went away mid-message",
            ));
        }
        if byte[0] == b'\n' {
            return Ok(held);
        }
        held.push(byte[0]);
        if held.len() > LINE {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "a line of this protocol is longer than it may be",
            ));
        }
    }
}

/// The next line as one JSON object (`_Lines.read`).
pub(crate) fn read_object(sock: &TcpStream, timeout: Duration) -> io::Result<Map<String, Value>> {
    let line = read_line(sock, timeout)?;
    match serde_json::from_slice(&line) {
        Ok(Value::Object(said)) => Ok(said),
        Ok(_) => Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "expected one JSON object per line",
        )),
        Err(e) => Err(io::Error::new(io::ErrorKind::InvalidData, e)),
    }
}

/// Writes one object, whole, with the newline that ends it (`_say`).
pub(crate) fn say(sock: &TcpStream, said: &Value) -> io::Result<()> {
    let mut line = ascii_json(said);
    line.push('\n');
    (&*sock).write_all(line.as_bytes())
}

/// `json.dumps(said, separators=(",", ":"))`: compact, and with `ensure_ascii`, so the bytes
/// on the wire are the Python's own.
pub(crate) fn ascii_json(said: &Value) -> String {
    let compact = said.to_string();
    if compact.is_ascii() {
        return compact;
    }
    let mut out = String::with_capacity(compact.len() + 16);
    for c in compact.chars() {
        if c.is_ascii() {
            out.push(c);
        } else {
            let mut units = [0u16; 2];
            for unit in c.encode_utf16(&mut units) {
                out.push_str(&format!("\\u{unit:04x}"));
            }
        }
    }
    out
}

/// An IPv4 address as `socket.inet_aton` reads one, which is laxer than `Ipv4Addr`'s parser
/// (`127.1`, `0x7f.0.0.1`), so both ends keep exactly the candidates the Python keeps.
///
/// Written out rather than called: the `libc` crate does not bind `inet_aton`. It follows
/// glibc's: up to four `.`-separated parts, each starting with a digit and read as `strtoul`
/// reads a C integer literal (`0x` hex, a leading `0` octal, else decimal), an overflow being
/// refused, and the text ending there or at whitespace, after which anything is ignored.
pub(crate) fn inet_aton(host: &str) -> Option<Ipv4Addr> {
    let said = host.as_bytes();
    let mut at = 0;
    let mut parts: Vec<u32> = Vec::with_capacity(4);
    loop {
        if !said.get(at)?.is_ascii_digit() {
            return None;
        }
        let mut radix = 10;
        if said[at] == b'0' {
            at += 1;
            if matches!(said.get(at), Some(b'x' | b'X'))
                && said.get(at + 1).is_some_and(u8::is_ascii_hexdigit)
            {
                radix = 16;
                at += 1;
            } else {
                // `strtoul` reads a `0x` with no hex digit after it as the `0` alone, which
                // leaves the `x` as trailing text.
                radix = 8;
            }
        }
        let mut value: u32 = 0;
        while let Some(&c) = said.get(at) {
            let Some(digit) = (c as char).to_digit(16).filter(|&d| d < radix) else {
                if radix == 8 && matches!(c, b'8' | b'9') {
                    return None;
                }
                break;
            };
            value = value.checked_mul(radix)?.checked_add(digit)?;
            at += 1;
        }
        parts.push(value);
        if said.get(at) == Some(&b'.') {
            if parts.len() >= 4 {
                return None;
            }
            at += 1;
            continue;
        }
        break;
    }
    if let Some(&c) = said.get(at)
        && !matches!(c, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c)
    {
        return None;
    }
    // The last part fills whatever bytes the ones before it leave.
    let (last, leading) = parts.split_last()?;
    if leading.len() > 3 || leading.iter().any(|&p| p > 0xff) {
        return None;
    }
    let room = 8 * (4 - leading.len() as u32);
    if room < 32 && *last >> room != 0 {
        return None;
    }
    let high = leading
        .iter()
        .enumerate()
        .fold(0u32, |acc, (i, &p)| acc | (p << (24 - 8 * i as u32)));
    Some(Ipv4Addr::from(high | last))
}

/// Python's `str()` of what a JSON value decodes to, for the fields the Python reads that way.
/// Missing is empty; floats and containers are approximated by their compact JSON.
pub(crate) fn python_str(said: Option<&Value>) -> String {
    match said {
        None => String::new(),
        Some(Value::String(s)) => s.clone(),
        Some(Value::Null) => "None".into(),
        Some(Value::Bool(true)) => "True".into(),
        Some(Value::Bool(false)) => "False".into(),
        Some(other) => other.to_string(),
    }
}

/// Python's truthiness of what a JSON value decodes to.
pub(crate) fn truthy(said: Option<&Value>) -> bool {
    match said {
        None | Some(Value::Null) => false,
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_f64().is_some_and(|f| f != 0.0),
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::Object(o)) => !o.is_empty(),
    }
}

/// `repr(float)`, which `json.dumps` writes a float as: the shortest digits that read back
/// the same, fixed between 1e-4 and 1e16 and scientific (`1e-07`, `1e+16`) outside.
pub(crate) fn python_float(f: f64) -> String {
    if f.is_nan() {
        return "NaN".into();
    }
    if f.is_infinite() {
        return if f > 0.0 { "Infinity" } else { "-Infinity" }.into();
    }
    // `{:e}` gives the shortest round-tripping digits: `-1.25e-7`, `4e0`.
    let shortest = format!("{f:e}");
    let (mantissa, exponent) = shortest.split_once('e').unwrap_or((&shortest, "0"));
    let exponent: i32 = exponent.parse().unwrap_or(0);
    let (sign, mantissa) = match mantissa.strip_prefix('-') {
        Some(rest) => ("-", rest),
        None => ("", mantissa),
    };
    let digits: String = mantissa.chars().filter(char::is_ascii_digit).collect();
    if (-4..16).contains(&exponent) {
        let point = exponent + 1;
        let fixed = if point <= 0 {
            format!("0.{}{digits}", "0".repeat((-point) as usize))
        } else if point as usize >= digits.len() {
            format!("{digits}{}.0", "0".repeat(point as usize - digits.len()))
        } else {
            let (whole, fraction) = digits.split_at(point as usize);
            format!("{whole}.{fraction}")
        };
        format!("{sign}{fixed}")
    } else {
        let (first, rest) = digits.split_at(1);
        let rest = if rest.is_empty() {
            String::new()
        } else {
            format!(".{rest}")
        };
        let esign = if exponent < 0 { '-' } else { '+' };
        format!("{sign}{first}{rest}e{esign}{:02}", exponent.abs())
    }
}

/// One candidate as the wire carries it: the host as said, and its port, any JSON integer.
pub(crate) type Candidate = (String, Value);

/// Reads a candidate list off the wire, keeping `[host, port]` pairs whose host is IPv4 and
/// whose port is an integer, deduplicated in order (`_pairs`). One reader for both ends.
///
/// As the Python, the host is `str()` of whatever was said and the port anything
/// `isinstance(port, int)` accepts, which a bool is.
pub(crate) fn pairs(said: Option<&Value>) -> Vec<Candidate> {
    let mut found: Vec<Candidate> = Vec::new();
    let Some(Value::Array(entries)) = said else {
        return found;
    };
    for entry in entries {
        let Value::Array(pair) = entry else { continue };
        if pair.len() != 2 || !(pair[1].is_i64() || pair[1].is_u64() || pair[1].is_boolean()) {
            continue;
        }
        let host = python_str(Some(&pair[0]));
        if inet_aton(&host).is_none() {
            continue;
        }
        let one = (host, pair[1].clone());
        if !found.contains(&one) {
            found.push(one);
        }
    }
    found
}

/// Candidates as the wire spells them: `[[host, port], ...]`.
pub(crate) fn candidates_json(found: &[Candidate]) -> Value {
    Value::Array(
        found
            .iter()
            .map(|(host, port)| Value::Array(vec![Value::String(host.clone()), port.clone()]))
            .collect(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_meeting_reads_as_python_reads_it() {
        let m = Meeting::parse("abc@[::1]:80").unwrap();
        assert_eq!(
            (m.ticket.as_str(), m.host.as_str(), m.port),
            ("abc", "::1", 80)
        );
        let m = Meeting::parse("a@b@host:9").unwrap();
        assert_eq!((m.ticket.as_str(), m.host.as_str()), ("a", "b@host"));
        assert_eq!(m.to_string(), "a@b@host:9");
        for bad in [
            "",
            "abc",
            "@h:1",
            "a@:1",
            "a@h:",
            "a@h:x",
            "a@h",
            "a@h:99999",
            "a@h:-1",
        ] {
            assert!(Meeting::parse(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn a_fresh_ticket_is_32_hex_digits() {
        let m = Meeting::fresh("h", 1);
        assert_eq!(m.ticket.len(), 32);
        assert!(m.ticket.bytes().all(|b| b.is_ascii_hexdigit()));
        assert_ne!(m.ticket, Meeting::fresh("h", 1).ticket);
    }

    #[test]
    fn candidates_keep_ipv4_integer_ports_once() {
        let said = serde_json::json!([
            ["1.2.3.4", 5],
            ["1.2.3.4", 5],
            ["::1", 5],
            ["1.2.3.4", "5"],
            ["127.1", 6],
            ["x", 1],
            [16909060, 2],
            ["9.9.9.9", true],
            [null, 1],
            "no",
            ["1.1.1.1", 1, 2]
        ]);
        let found = pairs(Some(&said));
        assert_eq!(
            candidates_json(&found),
            serde_json::json!([
                ["1.2.3.4", 5],
                ["127.1", 6],
                ["16909060", 2],
                ["9.9.9.9", true]
            ])
        );
        assert!(pairs(None).is_empty());
    }

    /// Checked against CPython's `socket.inet_aton` on glibc and macOS.
    #[test]
    fn inet_aton_reads_as_the_c_library_does() {
        let v4 = Ipv4Addr::new;
        for (said, meant) in [
            ("127.1", v4(127, 0, 0, 1)),
            ("0x7f.0.0.01", v4(127, 0, 0, 1)),
            ("2130706433", v4(127, 0, 0, 1)),
            ("10.1.258", v4(10, 1, 1, 2)),
            ("1.2.3.4 foo", v4(1, 2, 3, 4)),
            ("1.2.3.4\t", v4(1, 2, 3, 4)),
            ("0xffffffff", v4(255, 255, 255, 255)),
        ] {
            assert_eq!(inet_aton(said), Some(meant), "{said}");
        }
        for bad in [
            "",
            "1..2",
            "256.0.0.1",
            "1.2.3.4.5",
            "1.2.3.256",
            "08",
            "09.1",
            "0x",
            "::1",
            "a.b",
            " 1.2.3.4",
            "1.",
            "1.2.3.4x",
            "1.0x1ff.3",
        ] {
            assert_eq!(inet_aton(bad), None, "{bad}");
        }
    }

    #[test]
    fn floats_are_written_as_python_reprs_them() {
        for (f, said) in [
            (0.0, "0.0"),
            (-0.0, "-0.0"),
            (4.0, "4.0"),
            (0.5, "0.5"),
            (0.2, "0.2"),
            (1e-7, "1e-07"),
            (1e16, "1e+16"),
            (1e15, "1000000000000000.0"),
            (0.0001, "0.0001"),
            (0.00001, "1e-05"),
            (0.3333333333333333, "0.3333333333333333"),
            (123.456, "123.456"),
            (-1.0, "-1.0"),
            (1.5e300, "1.5e+300"),
            (2f64.powi(60), "1.152921504606847e+18"),
            (f64::INFINITY, "Infinity"),
        ] {
            assert_eq!(python_float(f), said, "{f}");
        }
    }

    #[test]
    fn lines_are_written_as_json_dumps_writes_them() {
        let said = serde_json::json!({"go": "no", "why": "caf\u{e9} \u{1f600}", "punch": 4.0});
        assert_eq!(
            ascii_json(&said),
            concat!(
                r#"{"go":"no","why":"caf"#,
                "\\u00e9 \\ud83d\\ude00",
                r#"","punch":4.0}"#
            )
        );
        assert_eq!(
            ascii_json(&serde_json::json!({"punch": 0.0})),
            r#"{"punch":0.0}"#
        );
    }
}

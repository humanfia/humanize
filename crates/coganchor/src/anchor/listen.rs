//! `coganchor anchor`: the three ways a session reaches this machine. Port of the `serve`
//! half of `hmz.cli.anchor` and of `hmz.coganchor.serve.listener`. [Unit 1]
//!
//! `--stdio` serves one session on standard input and output (which are then pointed at
//! `/dev/null`); `--listen` serves many, writing `hmz internal anchor serve listening HOST
//! PORT` to standard error once bound, and refusing a non-loopback address without a token;
//! `--peer` meets one through a broker ([`crate::broker::dial`]), its ticket the secret. The
//! last two are TLS under a certificate made as this process starts ([`crate::tls`]), and a
//! client proves the token or ticket inside it; standard input and output are a pipe whoever
//! started this already trusts, and carry the token as it is.
//!
//! Interrupted from the keyboard, any of them stops what its sessions started and exits 0, as
//! the Python half's `KeyboardInterrupt` did.

use std::fs::File;
use std::io::{self, Write};
use std::net::{SocketAddr, TcpListener, ToSocketAddrs};
use std::os::fd::{AsFd, FromRawFd, IntoRawFd, OwnedFd};
use std::sync::Arc;
use std::sync::atomic::{AtomicI32, Ordering};
use std::time::Duration;

use crate::anchor::ExportTable;
use crate::anchor::exports::py_repr;
use crate::anchor::server::{self, Server};
use crate::broker::{Meeting, Role};
use crate::cli::{self, AnchorArgs};
use crate::exit;
use crate::log;
use crate::proto::Channel;
use crate::tls::Identity;

/// The hosts a listener may take without a token: this machine alone can reach them.
const LOOPBACK_HOSTS: [&str; 3] = ["127.0.0.1", "::1", "localhost"];

/// How long a half met through a broker waits for the other (`rendezvous.PAIRING`).
const PAIRING: Duration = Duration::from_secs(120);

/// Runs `coganchor anchor`, returning its exit status.
pub fn main(args: AnchorArgs) -> i32 {
    log::init(args.log_level.as_deref(), "warning");
    if args.peer.is_some() && (args.token.is_some() || args.token_file.is_some()) {
        log::say("--token cannot be given with --peer, whose ticket is the secret");
        return exit::USAGE;
    }
    // `$HUMANIZE_TOKEN` stands in for `--token` everywhere but a meeting, where whatever this
    // process happened to inherit is no business of the session's.
    let token = args.token.clone().or_else(|| {
        std::env::var("HUMANIZE_TOKEN")
            .ok()
            .filter(|token| args.peer.is_none() && !token.is_empty())
    });
    let token = match cli::secret(token.as_deref(), args.token_file.as_deref()) {
        // An empty one is none: a non-loopback listener refuses it below, and a loopback one
        // asks nobody for anything.
        Ok(token) => token.filter(|token| !token.is_empty()),
        Err(error) => return exit::failed(format!("cannot read the token file: {error}")),
    };
    let exports = match ExportTable::parse(&args.exports) {
        Ok(table) => Arc::new(table),
        Err(message) => {
            log::say(message);
            return exit::USAGE;
        }
    };
    // Asked now, while this is the only thread (see `server::fences`).
    server::fences();
    stop_on_interrupt();

    if let Some(peer) = &args.peer {
        let met = Meeting::parse(peer)
            .map_err(|message| io::Error::new(io::ErrorKind::InvalidInput, message))
            .and_then(|meeting| {
                let stream = crate::broker::dial(&meeting, Role::Serve, PAIRING)?;
                let whom = format!("{}:{}", meeting.host, meeting.port);
                // The ticket is the key the cog proves.
                Identity::fresh()?.answer(stream, Some(meeting.ticket.into_bytes()), whom)
            });
        let channel = match met {
            Ok(channel) => Arc::new(channel),
            Err(error) => return exit::failed(error),
        };
        Server::new(channel.clone(), exports, None).run();
        channel.close();
        return 0;
    }

    if args.stdio {
        let channel = match stdio() {
            Ok(channel) => Arc::new(channel),
            Err(error) => return exit::failed(error),
        };
        Server::new(channel, exports, token).run();
        return 0;
    }

    let said = args.listen.as_deref().unwrap_or_default();
    let Some((host, port)) = listen_on(said, "127.0.0.1") else {
        log::say(format!(
            "malformed listen address {}; expected [HOST:]PORT",
            py_repr(said)
        ));
        return exit::USAGE;
    };
    if !LOOPBACK_HOSTS.contains(&host.as_str()) && token.is_none() {
        log::say("cannot listen on a non-loopback address without --token");
        return exit::USAGE;
    }
    let listener = match bind(&host, port) {
        Ok(listener) => listener,
        Err(error) => {
            return exit::failed(format!(
                "cannot listen on {host}:{port}: {}",
                strerror(&error)
            ));
        }
    };
    let identity = match Identity::fresh() {
        Ok(identity) => Arc::new(identity),
        Err(error) => return exit::failed(error),
    };
    serve_forever(listener, exports, identity, token)
}

/// The session's channel on what were standard input and output. Both are duplicated away
/// and fds 0 and 1 pointed at `/dev/null`, so a stray write from this process or a child it
/// starts cannot corrupt the protocol stream; fd 2 keeps carrying the log.
fn stdio() -> io::Result<Channel> {
    // Close-on-exec, as Python's `os.dup` makes them: a command started here must not hold
    // the protocol pipe open, or the client would never see it end.
    let reader = dup_cloexec(&io::stdin())?;
    let writer = dup_cloexec(&io::stdout())?;
    let null = File::options().read(true).write(true).open("/dev/null")?;
    let null = OwnedFd::from(null);
    nix::unistd::dup2_stdin(&null)?;
    nix::unistd::dup2_stdout(&null)?;
    Ok(Channel::new(
        Box::new(File::from(reader)),
        Box::new(File::from(writer)),
    ))
}

fn dup_cloexec(fd: &impl AsFd) -> io::Result<OwnedFd> {
    Ok(
        nix::fcntl::fcntl(fd, nix::fcntl::FcntlArg::F_DUPFD_CLOEXEC(3))
            .map(|raw| unsafe { OwnedFd::from_raw_fd(raw) })?,
    )
}

/// Reads `[HOST:]PORT`: split at the last `:`, brackets stripped, `default` where no host is
/// named. `None` unless the port is digits within range.
pub(crate) fn listen_on(spec: &str, default: &str) -> Option<(String, u16)> {
    let (host, port) = spec.rsplit_once(':').unwrap_or((default, spec));
    let host = host.trim_matches(|c| c == '[' || c == ']');
    let host = if host.is_empty() { default } else { host };
    if port.is_empty() || !port.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    let port: u16 = port.parse().ok()?;
    Some((host.to_owned(), port))
}

/// A listening socket on `host:port`, IPv6 where the host has a `:` in it, IPv4 otherwise;
/// the address is reused (the standard library sets `SO_REUSEADDR` on Unix).
fn bind(host: &str, port: u16) -> io::Result<TcpListener> {
    let six = host.contains(':');
    let mut last = None;
    for address in (host, port).to_socket_addrs()? {
        if address.is_ipv6() != six {
            continue;
        }
        match TcpListener::bind(address) {
            Ok(listener) => return Ok(listener),
            Err(error) => last = Some(error),
        }
    }
    Err(last.unwrap_or_else(|| io::Error::from_raw_os_error(libc::EADDRNOTAVAIL)))
}

/// An error's message as `OSError.strerror` gives it, without Rust's decorations.
fn strerror(error: &io::Error) -> String {
    let full = error.to_string();
    let full = full
        .strip_prefix("failed to lookup address information: ")
        .unwrap_or(&full);
    match full.rfind(" (os error ") {
        Some(cut) => full[..cut].to_owned(),
        None => full.to_owned(),
    }
}

/// Serves every connection to the listener, each on a thread of its own, until interrupted.
fn serve_forever(
    listener: TcpListener,
    exports: Arc<ExportTable>,
    identity: Arc<Identity>,
    token: Option<String>,
) -> i32 {
    let bound: SocketAddr = match listener.local_addr() {
        Ok(bound) => bound,
        Err(error) => return exit::failed(error),
    };
    // Not a message but a handshake: whoever started this reads the port it landed on off
    // this line, a port of 0 having been the way to ask for any free one.
    {
        let mut err = io::stderr().lock();
        let _ = writeln!(
            err,
            "hmz internal anchor serve listening {} {}",
            bound.ip(),
            bound.port()
        );
        let _ = err.flush();
    }
    for stream in listener.incoming() {
        let stream = match stream {
            Ok(stream) => stream,
            Err(error) => {
                // Out of descriptors, say, which accepting again at once would only spin on.
                tracing::warn!("accept failed: {error}");
                std::thread::sleep(Duration::from_millis(100));
                continue;
            }
        };
        let exports = exports.clone();
        let identity = identity.clone();
        let key = token.as_ref().map(|token| token.as_bytes().to_vec());
        std::thread::spawn(move || {
            let peer = stream
                .peer_addr()
                .map_or_else(|_| "?".into(), |a| a.to_string());
            tracing::info!("connection from {peer}");
            let channel = match identity.answer(stream, key, peer.clone()) {
                Ok(channel) => Arc::new(channel),
                Err(error) => {
                    tracing::warn!("connection from {peer} unusable: {error}");
                    return;
                }
            };
            Server::new(channel.clone(), exports, None).run();
            channel.close();
            tracing::info!("connection from {peer} closed");
        });
    }
    0
}

/// The write end of the pipe the `SIGINT` handler wakes [`stop_on_interrupt`]'s thread with.
static INTERRUPTED: AtomicI32 = AtomicI32::new(-1);

extern "C" fn interrupted(_: libc::c_int) {
    let fd = INTERRUPTED.load(Ordering::Relaxed);
    if fd >= 0 {
        // Only async-signal-safe calls here: one byte down a pipe.
        unsafe { libc::write(fd, b"!".as_ptr().cast(), 1) };
    }
}

/// On `SIGINT`, shuts down every session's sinks (killing the commands they started) and
/// exits 0. A handler rather than a blocked signal, so that children do not inherit a mask.
fn stop_on_interrupt() {
    let Ok((read, write)) = nix::unistd::pipe() else {
        return;
    };
    for fd in [&read, &write] {
        let _ = nix::fcntl::fcntl(
            fd,
            nix::fcntl::FcntlArg::F_SETFD(nix::fcntl::FdFlag::FD_CLOEXEC),
        );
    }
    // The pipe outlives the handler: neither end is ever closed.
    INTERRUPTED.store(write.into_raw_fd(), Ordering::Relaxed);
    let action = nix::sys::signal::SigAction::new(
        nix::sys::signal::SigHandler::Handler(interrupted),
        nix::sys::signal::SaFlags::SA_RESTART,
        nix::sys::signal::SigSet::empty(),
    );
    let _ = unsafe { nix::sys::signal::sigaction(nix::sys::signal::Signal::SIGINT, &action) };
    std::thread::spawn(move || {
        let mut byte = [0u8; 1];
        let mut file = File::from(read);
        if io::Read::read(&mut file, &mut byte).is_ok_and(|n| n == 1) {
            server::close_all();
            std::process::exit(0);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn listen_addresses() {
        assert_eq!(
            listen_on("8080", "127.0.0.1"),
            Some(("127.0.0.1".into(), 8080))
        );
        assert_eq!(
            listen_on("0.0.0.0:0", "127.0.0.1"),
            Some(("0.0.0.0".into(), 0))
        );
        assert_eq!(listen_on("[::1]:22", "127.0.0.1"), Some(("::1".into(), 22)));
        assert_eq!(listen_on(":9", "127.0.0.1"), Some(("127.0.0.1".into(), 9)));
        assert_eq!(listen_on("h:65536", "x"), None);
        assert_eq!(listen_on("h:", "x"), None);
        assert_eq!(listen_on("h:-1", "x"), None);
        assert_eq!(listen_on("h:+1", "x"), None);
    }

    #[test]
    fn binds_loopback_by_family() {
        let four = bind("localhost", 0).unwrap();
        assert!(four.local_addr().unwrap().is_ipv4());
        assert!(bind("no-such-host.invalid", 0).is_err());
    }
}

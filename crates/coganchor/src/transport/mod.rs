//! Reaching an anchor on a target. Port of the connecting half of
//! `hmz.coganchor.transport`. [Unit 7]
//!
//! Five ways start the anchor and take the pipe they started it down: `local[:REAL]` runs it
//! as a child; `ssh://`, `docker://`, `apple-container://` and `slurm://` run it on the far
//! side through a [`Road`], having shipped this very binary there (the right one for that
//! machine's OS and architecture) if it is not already in its cache. Two ways find one already
//! running: `tcp://HOST:PORT` dials it, and `peer://TICKET@HOST:PORT` meets it through a broker.

pub mod road;
pub mod ship;
pub mod target;

use std::ffi::OsString;
use std::io;
use std::net::{TcpStream, ToSocketAddrs};
use std::process::{Child, Command, Stdio};
use std::sync::Arc;
use std::time::{Duration, Instant};

pub use road::Road;
pub use target::{Endpoint, Target};

use crate::broker::{Meeting, Role};
use crate::proto::Channel;

/// How long dialling a `tcp://` target may take. `socket.create_connection(timeout=30.0)`.
const DIALLING: Duration = Duration::from_secs(30);

/// How long a half waits at the broker for the other. `rendezvous.PAIRING`.
const PAIRING: Duration = Duration::from_secs(120);

/// How long a started anchor has to end once told to, before it is killed.
const ENDING: Duration = Duration::from_secs(5);

/// A connection to an anchor, and the process carrying it where one was started.
pub struct Link {
    pub channel: Arc<Channel>,
    pub child: Option<Child>,
}

impl Link {
    /// Closes the channel, then ends the process: terminate, five seconds, kill.
    /// Port of `Transport.close`.
    pub fn close(mut self) {
        self.channel.close();
        let Some(mut child) = self.child.take() else {
            return;
        };
        if matches!(child.try_wait(), Ok(Some(_))) {
            return;
        }
        let pid = nix::unistd::Pid::from_raw(child.id() as i32);
        let _ = nix::sys::signal::kill(pid, nix::sys::signal::Signal::SIGTERM);
        let started = Instant::now();
        while started.elapsed() < ENDING {
            if matches!(child.try_wait(), Ok(Some(_))) {
                return;
            }
            std::thread::sleep(Duration::from_millis(20));
        }
        // Reaped rather than left: a run that opens an anchor per agent would otherwise
        // gather a zombie for each one that would not go quietly.
        let _ = child.kill();
        let _ = child.wait();
    }
}

/// Reaches an anchor serving `exports` on `target`, starting it where the target says to.
/// Port of `transport.connect`.
pub fn connect(target: &Target, exports: &[String], token: Option<&str>) -> io::Result<Link> {
    match target.scheme.as_str() {
        "tcp" => {
            let stream = dial(&target.host, target.port.unwrap_or(0))?;
            // Nagle off: this protocol is a small request and a small reply, over and over.
            Ok(Link {
                channel: Arc::new(Channel::from_tcp(stream)?),
                child: None,
            })
        }
        "peer" => {
            let meeting = Meeting {
                ticket: target.path.clone().unwrap_or_default(),
                host: target.host.clone(),
                port: target.port.unwrap_or(0),
            };
            let stream = crate::broker::dial(&meeting, Role::Anchor, PAIRING)?;
            Ok(Link {
                channel: Arc::new(Channel::from_tcp(stream)?),
                child: None,
            })
        }
        _ => spawn(&serve_line(target, exports)?, token),
    }
}

/// The command that leaves an anchor serving `exports` over its own stdin and stdout on the
/// target: `coganchor anchor --stdio --export E...`, shipped there first. Port of
/// `transport.serve_line`.
pub fn serve_line(target: &Target, exports: &[String]) -> io::Result<Vec<OsString>> {
    let mut args: Vec<OsString> = ["anchor", "--stdio"].map(OsString::from).to_vec();
    for export in exports {
        args.push("--export".into());
        args.push(export.into());
    }
    ship::command(&Road::to(target), &args)
}

/// Dials `host:port`, trying each address it resolves to, each for at most [`DIALLING`].
fn dial(host: &str, port: u16) -> io::Result<TcpStream> {
    let mut last = io::Error::new(
        io::ErrorKind::NotFound,
        format!("{host} resolves to no address"),
    );
    for address in (host.trim_matches(['[', ']']), port).to_socket_addrs()? {
        match TcpStream::connect_timeout(&address, DIALLING) {
            Ok(stream) => return Ok(stream),
            Err(error) => last = error,
        }
    }
    Err(last)
}

/// Starts a child serving over its own stdin and stdout. Port of `transport._spawn`.
///
/// The token travels in the child's environment as `HUMANIZE_TOKEN`, never on its command
/// line where any user of the machine could read it. That reaches a `local` anchor; for the
/// others the child is the `ssh` or `docker` client, which does not forward it, and those
/// sessions are authenticated by ssh and by the docker socket themselves.
fn spawn(command: &[OsString], token: Option<&str>) -> io::Result<Link> {
    let (program, args) = command
        .split_first()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "nothing to run"))?;
    tracing::debug!(
        "starting the target: {}",
        command
            .iter()
            .map(|word| word.to_string_lossy())
            .collect::<Vec<_>>()
            .join(" ")
    );
    let mut run = Command::new(program);
    run.args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit());
    if let Some(token) = token.filter(|token| !token.is_empty()) {
        run.env("HUMANIZE_TOKEN", token);
    }
    let mut child = run.spawn()?;
    let stdin = child.stdin.take().expect("piped");
    let stdout = child.stdout.take().expect("piped");
    Ok(Link {
        channel: Arc::new(Channel::new(Box::new(stdout), Box::new(stdin))),
        child: Some(child),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn closing_ends_the_child() {
        let link = spawn(&["sleep", "30"].map(OsString::from), Some("t")).unwrap();
        let pid = nix::unistd::Pid::from_raw(link.child.as_ref().unwrap().id() as i32);
        let started = Instant::now();
        link.close();
        assert!(started.elapsed() < ENDING);
        // Reaped: there is no such process any more.
        assert!(nix::sys::signal::kill(pid, None).is_err());
    }

    #[test]
    fn the_token_goes_in_the_environment() {
        let dir = tempfile::tempdir().unwrap();
        let seen = dir.path().join("seen");
        let link = spawn(
            &[
                OsString::from("sh"),
                OsString::from("-c"),
                OsString::from("printf '%s|%s' \"$HUMANIZE_TOKEN\" \"$*\" > \"$0\""),
                seen.clone().into_os_string(),
            ],
            Some("s3cret"),
        )
        .unwrap();
        let mut child = link.child.unwrap();
        child.wait().unwrap();
        // In the environment, and nowhere on the command line.
        assert_eq!(fs::read_to_string(&seen).unwrap(), "s3cret|");
    }

    #[test]
    fn tcp_and_peer_have_no_road() {
        let target = Target::parse("tcp://127.0.0.1:1").unwrap();
        assert!(Road::to(&target).try_line(&[]).is_err());
    }

    #[test]
    fn tcp_targets_are_dialled() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let target = Target::parse(&format!("tcp://127.0.0.1:{port}")).unwrap();
        let link = connect(&target, &[], None).unwrap();
        let (_accepted, _) = listener.accept().unwrap();
        assert!(link.child.is_none());
        link.close();
    }
}

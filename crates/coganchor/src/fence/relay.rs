//! Carrying loopback across the edge of a network namespace bubblewrap made.
//!
//! A fence that cuts the network under bubblewrap puts the program in a network namespace of
//! its own, whose loopback reaches nothing outside it. Two things still have to cross that
//! edge, and both go through Unix sockets in a directory mounted on both sides of it -- a
//! socket named by a path being the one kind a network namespace does not hold apart:
//!
//! - *Out*: the proxy that is the one way out of every fence listens on this machine's
//!   loopback, and the program is told it is at that port on its own. Inside, a listener at
//!   that port passes each connection to `out-<port>.sock`; outside, a listener there passes it
//!   on to the proxy.
//! - *In*: a CLI that serves itself to its driver at a port it was told to listen on listens on
//!   its namespace's loopback, where the driver cannot reach it. Outside, a listener at that
//!   port on this machine's loopback passes each connection to `in-<port>.sock`; inside, a
//!   listener there passes it on to the port. The file `in-<port>` is what tells the inside
//!   which ports to listen for.
//!
//! The outside is [`outside`], kept by the wrapper that stays outside the wall; the inside is
//! [`main`], which is what `coganchor internal fence --relay` runs as the program bubblewrap
//! starts, before it runs the program it was given and waits for it.

use std::ffi::OsString;
use std::io::{self, Read, Write};
use std::net::{Shutdown, TcpListener, TcpStream};
use std::os::fd::AsRawFd;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;
use std::thread;
use std::time::{Duration, Instant};

use crate::exit;

/// How long a connection waits for the far side of a bridge to be listening: the inside
/// starts listening a moment after the program's namespace is made, the program a moment after
/// that, and a driver may dial the port it was promised as soon as it has asked for it.
const PATIENCE: Duration = Duration::from_secs(30);

/// Either kind of stream a bridge carries.
enum Stream {
    Tcp(TcpStream),
    Unix(UnixStream),
}

impl Stream {
    fn try_clone(&self) -> io::Result<Stream> {
        Ok(match self {
            Stream::Tcp(one) => Stream::Tcp(one.try_clone()?),
            Stream::Unix(one) => Stream::Unix(one.try_clone()?),
        })
    }

    fn shutdown(&self, how: Shutdown) {
        let _ = match self {
            Stream::Tcp(one) => one.shutdown(how),
            Stream::Unix(one) => one.shutdown(how),
        };
    }
}

impl Read for Stream {
    fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
        match self {
            Stream::Tcp(one) => one.read(buffer),
            Stream::Unix(one) => one.read(buffer),
        }
    }
}

impl Write for Stream {
    fn write(&mut self, buffer: &[u8]) -> io::Result<usize> {
        match self {
            Stream::Tcp(one) => one.write(buffer),
            Stream::Unix(one) => one.write(buffer),
        }
    }

    fn flush(&mut self) -> io::Result<()> {
        match self {
            Stream::Tcp(one) => one.flush(),
            Stream::Unix(one) => one.flush(),
        }
    }
}

/// Either kind of listener a bridge takes connections on.
enum Listener {
    Tcp(TcpListener),
    Unix(UnixListener),
}

impl Listener {
    fn accept(&self) -> io::Result<Stream> {
        Ok(match self {
            Listener::Tcp(one) => Stream::Tcp(one.accept()?.0),
            Listener::Unix(one) => Stream::Unix(one.accept()?.0),
        })
    }

    fn raw(&self) -> i32 {
        match self {
            Listener::Tcp(one) => one.as_raw_fd(),
            Listener::Unix(one) => one.as_raw_fd(),
        }
    }
}

/// Where a bridge passes each connection it takes.
#[derive(Clone)]
enum Far {
    Tcp(u16),
    Unix(String),
}

impl Far {
    /// Dials it, waiting for it to be listened at for as long as [`PATIENCE`]: a connection is
    /// taken on one side of the edge before anything need listen on the other, and is held as
    /// it would have waited to be answered.
    fn dial(&self) -> io::Result<Stream> {
        let until = Instant::now() + PATIENCE;
        loop {
            let tried = match self {
                Far::Tcp(port) => TcpStream::connect(("127.0.0.1", *port)).map(Stream::Tcp),
                Far::Unix(path) => UnixStream::connect(path).map(Stream::Unix),
            };
            match tried {
                Err(why)
                    if matches!(why.raw_os_error(), Some(libc::ENOENT | libc::ECONNREFUSED))
                        && Instant::now() < until =>
                {
                    thread::sleep(Duration::from_millis(50));
                }
                done => return done,
            }
        }
    }
}

/// A listener whose every connection is passed to another place, both ways.
pub struct Bridge {
    listener: std::sync::Arc<Listener>,
}

impl Bridge {
    fn start(listener: Listener, far: Far) -> Bridge {
        let listener = std::sync::Arc::new(listener);
        let taking = std::sync::Arc::clone(&listener);
        thread::spawn(move || {
            while let Ok(client) = taking.accept() {
                let far = far.clone();
                thread::spawn(move || {
                    if let Ok(dialled) = far.dial() {
                        splice(client, dialled);
                    }
                });
            }
        });
        Bridge { listener }
    }

    /// Stops taking connections; those already passed go on until either side ends.
    pub fn stop(self) {
        // SAFETY: shutting down a socket this bridge holds open, which wakes its accept.
        unsafe { libc::shutdown(self.listener.raw(), libc::SHUT_RDWR) };
    }
}

/// Carries bytes both ways between two streams until both sides have done sending: a side
/// that stops sending has the other's writing half shut, so that the far end may still answer.
fn splice(one: Stream, other: Stream) {
    let (Ok(one_back), Ok(other_back)) = (one.try_clone(), other.try_clone()) else {
        return;
    };
    let back = thread::spawn(move || pump(other_back, one_back));
    pump(one, other);
    let _ = back.join();
}

fn pump(mut source: Stream, mut sink: Stream) {
    match io::copy(&mut source, &mut sink) {
        Ok(_) => sink.shutdown(Shutdown::Write),
        Err(_) => {
            source.shutdown(Shutdown::Both);
            sink.shutdown(Shutdown::Both);
        }
    }
}

fn tcp(port: u16) -> io::Result<Listener> {
    TcpListener::bind(("127.0.0.1", port)).map(Listener::Tcp)
}

fn unix(path: &str) -> io::Result<Listener> {
    UnixListener::bind(path).map(Listener::Unix)
}

/// The bridges the wrapper outside the namespace keeps, started: the proxy's socket in
/// `directory`, passed on to the proxy at `proxy`; and each port in `listen` on this machine's
/// loopback, passed to the inside, with the file that asks the inside to listen for it.
pub fn outside(directory: &str, proxy: u16, listen: &[u16]) -> io::Result<Vec<Bridge>> {
    let mut listeners = vec![(
        unix(&format!("{directory}/out-{proxy}.sock"))?,
        Far::Tcp(proxy),
    )];
    for port in listen {
        std::fs::write(format!("{directory}/in-{port}"), b"")?;
        listeners.push((
            tcp(*port)?,
            Far::Unix(format!("{directory}/in-{port}.sock")),
        ));
    }
    Ok(listeners
        .into_iter()
        .map(|(listener, far)| Bridge::start(listener, far))
        .collect())
}

/// The bridges inside the namespace that `directory` asks for, started.
pub fn inside(directory: &str) -> io::Result<Vec<Bridge>> {
    let mut names: Vec<String> = std::fs::read_dir(directory)?
        .filter_map(Result::ok)
        .map(|entry| entry.file_name().to_string_lossy().into_owned())
        .collect();
    names.sort();
    let mut listeners = Vec::new();
    for name in names {
        let port = |said: &str| said.parse::<u16>().ok();
        if let Some(port) = name
            .strip_prefix("out-")
            .and_then(|rest| rest.strip_suffix(".sock"))
            .and_then(port)
        {
            listeners.push((tcp(port)?, Far::Unix(format!("{directory}/{name}"))));
        } else if let Some(port) = name.strip_prefix("in-").and_then(port) {
            listeners.push((unix(&format!("{directory}/{name}.sock"))?, Far::Tcp(port)));
        }
    }
    Ok(listeners
        .into_iter()
        .map(|(listener, far)| Bridge::start(listener, far))
        .collect())
}

/// `coganchor internal fence --relay`: carries loopback across the namespace's edge through
/// `directory`, and runs the program inside it. Its status; 126 where the bridges could not be
/// made and the program never ran, 127 where it could not be run.
pub fn main(directory: &str, argv: &[OsString]) -> i32 {
    // It goes when bubblewrap does, which goes when the wrapper does. Said again here, though
    // `--die-with-parent` said it before bubblewrap became this: becoming a program under
    // another AppArmor profile, as Ubuntu's for `bwrap` makes of it, forgets it was said.
    // SAFETY: integer arguments only.
    #[cfg(target_os = "linux")]
    unsafe {
        libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL, 0, 0, 0)
    };
    let bridges = match inside(directory) {
        Ok(bridges) => bridges,
        Err(why) => {
            eprintln!("hmz internal fence: cannot relay loopback: {why}");
            return exit::UNFENCED;
        }
    };
    let mut program = std::process::Command::new(&argv[0]);
    program.args(&argv[1..]);
    #[cfg(target_os = "linux")]
    {
        use std::os::unix::process::CommandExt;
        // SAFETY: getpid has no preconditions.
        let relay = unsafe { libc::getpid() };
        // SAFETY: the closure makes two system calls with integer arguments and allocates
        // nothing where all went well, which is all a forked child may do.
        unsafe {
            program.pre_exec(move || {
                // It goes when the relay does, as the relay goes when the wrapper does:
                // bubblewrap's `--die-with-parent` reaches the relay and no further.
                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL, 0, 0, 0) != 0 {
                    return Err(io::Error::last_os_error());
                }
                if libc::getppid() != relay {
                    return Err(io::Error::from_raw_os_error(libc::ESRCH));
                }
                Ok(())
            });
        }
    }
    let status = match program.spawn() {
        Ok(child) => crate::fence::wrap::waited(child.id() as libc::pid_t),
        Err(why) => {
            eprintln!(
                "hmz internal fence: cannot run {}: {why}",
                Path::new(&argv[0]).display()
            );
            exit::NOT_INSTALLED
        }
    };
    for bridge in bridges {
        bridge.stop();
    }
    status
}

#[cfg(test)]
mod tests {
    use super::*;

    fn echo() -> u16 {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        thread::spawn(move || {
            for mut client in listener.incoming().flatten() {
                thread::spawn(move || {
                    let mut back = client.try_clone().unwrap();
                    let _ = io::copy(&mut client, &mut back);
                });
            }
        });
        port
    }

    fn free() -> u16 {
        TcpListener::bind(("127.0.0.1", 0))
            .unwrap()
            .local_addr()
            .unwrap()
            .port()
    }

    fn echoed(mut stream: Stream) -> Vec<u8> {
        stream.write_all(b"ping").unwrap();
        stream.shutdown(Shutdown::Write);
        let mut held = Vec::new();
        stream.read_to_end(&mut held).unwrap();
        held
    }

    /// A directory short enough for a Unix socket, wherever the tests run.
    fn short() -> tempfile::TempDir {
        tempfile::Builder::new()
            .prefix("hmz-relay-")
            .tempdir_in("/tmp")
            .unwrap()
    }

    #[test]
    fn outside_carries_the_proxy_socket_to_the_proxy() {
        let dir = short();
        let through = dir.path().to_string_lossy().into_owned();
        let port = echo();
        let bridges = outside(&through, port, &[]).unwrap();

        let dialled = UnixStream::connect(format!("{through}/out-{port}.sock")).unwrap();

        assert_eq!(echoed(Stream::Unix(dialled)), b"ping");
        bridges.into_iter().for_each(Bridge::stop);
    }

    #[test]
    fn inside_carries_a_port_one_way_and_a_socket_the_other() {
        let dir = short();
        let through = dir.path().to_string_lossy().into_owned();
        let target = echo();
        // The outside's half of the proxy, standing in: its socket, passed on to the echo.
        let out = free();
        let outer = Bridge::start(
            unix(&format!("{through}/out-{out}.sock")).unwrap(),
            Far::Tcp(target),
        );
        // A port the program inside listens on: here the echo itself.
        std::fs::write(format!("{through}/in-{target}"), b"").unwrap();
        let bridges = inside(&through).unwrap();

        let dialled = TcpStream::connect(("127.0.0.1", out)).unwrap();
        assert_eq!(echoed(Stream::Tcp(dialled)), b"ping");
        let dialled = UnixStream::connect(format!("{through}/in-{target}.sock")).unwrap();
        assert_eq!(echoed(Stream::Unix(dialled)), b"ping");
        bridges.into_iter().chain([outer]).for_each(Bridge::stop);
    }

    #[test]
    fn a_far_side_not_listening_yet_is_waited_for() {
        let dir = short();
        let path = format!("{}/late.sock", dir.path().display());
        let later = path.clone();
        let started = thread::spawn(move || {
            thread::sleep(Duration::from_millis(200));
            let listener = UnixListener::bind(later).unwrap();
            let (mut taken, _) = listener.accept().unwrap();
            taken.write_all(b"hi").unwrap();
        });

        let mut dialled = Far::Unix(path).dial().unwrap();
        let mut said = [0u8; 2];
        dialled.read_exact(&mut said).unwrap();

        assert_eq!(&said, b"hi");
        started.join().unwrap();
    }
}

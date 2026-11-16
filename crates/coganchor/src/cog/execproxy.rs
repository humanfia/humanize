//! Standing in for a process that should have run on the target. Port of
//! `hmz.coganchor.execproxy`. [Unit 11]
//!
//! When a traced process calls `execve`, the new image is not let load. Its three standard
//! descriptors are stolen with `pidfd_getfd`, the command runs on the target, and the
//! target's I/O is pumped through those very descriptors: the agent's pipe carries the
//! target's output, and once the command finishes the stalled `execve` is rewritten into
//! `exit_group` with the remote status. Its end is reported on a channel plus a byte on the
//! supervisor's wake pipe, and nothing here ever blocks the supervisor's thread.

use std::collections::HashSet;
use std::ffi::OsString;
use std::io;
use std::os::fd::{AsFd, AsRawFd, BorrowedFd, OwnedFd, RawFd};
use std::os::unix::ffi::OsStrExt;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{Receiver, RecvTimeoutError, Sender};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use nix::errno::Errno;
use nix::poll::{PollFd, PollFlags, PollTimeout, poll};
use nix::unistd::Pid;
use serde_json::Value;

use crate::client::{Event, RemoteClient};
use crate::cog::netproxy::{Conduit, Outlet, Remote, lock};
use crate::proto::json::from_os;
use crate::proto::{CHUNK_SIZE, Meta, RemoteError, Stream};

/// How often a pump blocked on the agent re-checks whether it should stop (`_STDIN_POLL`).
const POLL: Duration = Duration::from_millis(200);

/// The command to run on the target.
#[derive(Clone, Debug)]
pub struct ExecRequest {
    pub argv: Vec<OsString>,
    pub program: Option<OsString>,
    /// The working directory, as the target names it.
    pub cwd: String,
    pub env: Vec<(OsString, OsString)>,
    /// The fence's levels, where the agent is fenced.
    pub fence: Option<serde_json::Value>,
}

/// How a remote command ended.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Ending {
    Exited(i32),
    Signalled(i32),
    /// It never started: 127 for `ENOENT`, 126 otherwise (`hmz: argv0: strerror` written).
    Failed(i32),
}

impl Ending {
    /// The status to report to the agent, as a shell would (`ExecResult.wait_status`).
    pub fn wait_status(self) -> i32 {
        match self {
            Ending::Exited(code) | Ending::Failed(code) => code,
            Ending::Signalled(signal) => 128 + signal,
        }
    }

    /// The ending an `EXEC` reply says: its `signal` if it has one, else its `exit_code`,
    /// else 1.
    fn from_reply(reply: &Meta) -> Ending {
        let number = |key| reply.get(key).and_then(Value::as_i64).map(|n| n as i32);
        match (number("signal"), number("exit_code")) {
            (Some(signal), _) => Ending::Signalled(signal),
            (None, Some(code)) => Ending::Exited(code),
            (None, None) => Ending::Exited(1),
        }
    }
}

/// A remote command finished, for the stand-in `pid`.
#[derive(Clone, Copy, Debug)]
pub struct Completion {
    pub pid: Pid,
    pub ending: Ending,
}

/// A remote command in progress.
pub struct ExecProxy {
    pub pid: Pid,
    outlet: Arc<dyn Outlet>,
    /// Signals already forwarded: each is forwarded once (`forward_signal`).
    forwarded: Mutex<HashSet<i32>>,
    /// Set by [`ExecProxy::abandon`]: finish without waiting for the target.
    abandoned: Arc<AtomicBool>,
}

impl ExecProxy {
    /// Starts `request` on the target for stand-in `pid`, pumping through `fds` (its stdin,
    /// stdout, stderr). `tty` and the window size come from `fds[0]`; stdin is `/dev/null`
    /// where `borrow_stdin` is false.
    ///
    /// The request goes out first: if the connection is gone this fails before any thread
    /// is started, and the descriptors are closed.
    pub fn start(
        client: Arc<RemoteClient>,
        pid: Pid,
        request: ExecRequest,
        fds: [OwnedFd; 3],
        borrow_stdin: bool,
        done: Sender<Completion>,
        wake: RawFd,
    ) -> io::Result<ExecProxy> {
        ExecProxy::with(client, pid, request, fds, borrow_stdin, done, wake)
    }

    /// [`ExecProxy::start`] over any [`Remote`].
    pub(crate) fn with(
        remote: Arc<dyn Remote>,
        pid: Pid,
        request: ExecRequest,
        fds: [OwnedFd; 3],
        borrow_stdin: bool,
        done: Sender<Completion>,
        wake: RawFd,
    ) -> io::Result<ExecProxy> {
        let [stdin, stdout, stderr] = fds;
        // A copy of the wake pipe of the proxy's own, so the byte can never land in some
        // other file that has since taken the supervisor's descriptor number.
        // SAFETY: the caller hands over an open descriptor, only borrowed for this `dup`.
        let wake = unsafe { BorrowedFd::borrow_raw(wake) }.try_clone_to_owned()?;
        let tty = nix::unistd::isatty(&stdin).unwrap_or(false);
        let winsize = if tty {
            window_size(stdin.as_fd())
        } else {
            None
        };
        let Conduit { outlet, events } = remote
            .start_exec(exec_meta(&request, tty, winsize))
            .map_err(|error| error.to_io())?;
        let stop = Arc::new(AtomicBool::new(false));
        let abandoned = Arc::new(AtomicBool::new(false));
        // Should a pump not start, the command must not run on unwatched.
        let unwatched = |error: io::Error, stop: &AtomicBool| {
            stop.store(true, Ordering::SeqCst);
            let _ = outlet.signal(libc::SIGKILL);
            error
        };
        let stdin_pump = if borrow_stdin {
            let (pumped, pumping) = (Arc::clone(&outlet), Arc::clone(&stop));
            let pump = spawn(format!("exec-in-{pid}"), move || {
                pump_stdin(stdin, pumped.as_ref(), &pumping)
            });
            Some(pump.map_err(|error| unwatched(error, &stop))?)
        } else {
            drop(stdin);
            let _ = outlet.end(Stream::Stdin);
            None
        };
        let output = Output {
            pid,
            argv0: request.argv.first().cloned(),
            stdout,
            stderr,
            stop: Arc::clone(&stop),
            abandoned: Arc::clone(&abandoned),
            stdin_pump,
            done,
            wake,
        };
        spawn(format!("exec-out-{pid}"), move || output.run(events))
            .map_err(|error| unwatched(error, &stop))?;
        Ok(ExecProxy {
            pid,
            outlet,
            forwarded: Mutex::new(HashSet::new()),
            abandoned,
        })
    }

    /// Forwards a signal to the remote command's process group, once per signal: the
    /// stand-in may be stopped for the same signal more than once.
    pub fn signal(&self, signal: i32) {
        if !lock(&self.forwarded).insert(signal) {
            return;
        }
        tracing::debug!(
            "forwarding signal {signal} to the remote command for {}",
            self.pid
        );
        let _ = self.outlet.signal(signal);
    }

    /// The stand-in died: kills the remote command and finishes now, as `Exited(1)` unless
    /// its end had already arrived.
    pub fn abandon(&self) {
        self.abandoned.store(true, Ordering::SeqCst);
        let _ = self.outlet.signal(libc::SIGKILL);
    }
}

/// The `EXEC` request's metadata, in the order `RemoteClient.start_exec` writes it.
fn exec_meta(request: &ExecRequest, tty: bool, winsize: Option<(u16, u16)>) -> Meta {
    let strings = |names: &[OsString]| -> Value {
        names
            .iter()
            .map(|name| Value::from(from_os(name)))
            .collect()
    };
    let env: Meta = request
        .env
        .iter()
        .map(|(name, value)| (from_os(name), Value::from(from_os(value))))
        .collect();
    let mut meta = Meta::new();
    meta.insert("argv".into(), strings(&request.argv));
    meta.insert(
        "program".into(),
        request
            .program
            .as_deref()
            .map_or(Value::Null, |p| from_os(p).into()),
    );
    meta.insert("cwd".into(), request.cwd.clone().into());
    meta.insert("env".into(), Value::Object(env));
    meta.insert("tty".into(), tty.into());
    meta.insert(
        "winsize".into(),
        winsize.map_or(Value::Null, |(rows, cols)| Value::from(vec![rows, cols])),
    );
    meta.insert("fence".into(), request.fence.clone().unwrap_or(Value::Null));
    meta
}

/// Rows and columns of the terminal on `fd`, if it has a size. Without it the remote pty is
/// made 0x0, and anything laying out its output (a pager, a progress bar, `ls`) gets it wrong.
fn window_size(fd: BorrowedFd) -> Option<(u16, u16)> {
    let mut size = libc::winsize {
        ws_row: 0,
        ws_col: 0,
        ws_xpixel: 0,
        ws_ypixel: 0,
    };
    // SAFETY: TIOCGWINSZ writes one `winsize` through the pointer, which is valid for it.
    let got = unsafe { libc::ioctl(fd.as_raw_fd(), libc::TIOCGWINSZ, &mut size) };
    (got == 0 && size.ws_row != 0 && size.ws_col != 0).then_some((size.ws_row, size.ws_col))
}

fn spawn(name: String, body: impl FnOnce() + Send + 'static) -> io::Result<JoinHandle<()>> {
    thread::Builder::new().name(name).spawn(body)
}

/// The output side of a command: what drains its events into the stolen descriptors and
/// reports its end.
struct Output {
    pid: Pid,
    argv0: Option<OsString>,
    stdout: OwnedFd,
    stderr: OwnedFd,
    stop: Arc<AtomicBool>,
    abandoned: Arc<AtomicBool>,
    stdin_pump: Option<JoinHandle<()>>,
    done: Sender<Completion>,
    wake: OwnedFd,
}

impl Output {
    fn run(self, events: Receiver<Event>) {
        let ending = self.drain(&events);
        // Stop and join the stdin pump before giving the descriptors up: once the stand-in
        // exits nothing may still read what the agent meant for the next process.
        self.stop.store(true, Ordering::SeqCst);
        if let Some(pump) = self.stdin_pump {
            let _ = pump.join();
        }
        // Closed before the completion is told, so that the agent's pipe reaches EOF when
        // the stand-in exits.
        drop(self.stdout);
        drop(self.stderr);
        let _ = self.done.send(Completion {
            pid: self.pid,
            ending,
        });
        let _ = nix::unistd::write(&self.wake, &[0]);
    }

    /// Writes the command's output where it belongs until its end arrives.
    fn drain(&self, events: &Receiver<Event>) -> Ending {
        let mut ending = Ending::Exited(1);
        loop {
            if self.abandoned.load(Ordering::SeqCst) {
                return ending;
            }
            let event = match events.recv_timeout(POLL) {
                Ok(event) => event,
                Err(RecvTimeoutError::Timeout) => continue,
                Err(RecvTimeoutError::Disconnected) => return ending,
            };
            match event {
                Event::Chunk(Stream::Stderr, data) => self.write(self.stderr.as_fd(), &data),
                Event::Chunk(_, data) => self.write(self.stdout.as_fd(), &data),
                Event::End(_) => {}
                Event::Done(Ok(reply)) => return Ending::from_reply(&reply),
                Event::Done(Err(error)) => {
                    ending = self.failed(&error);
                    return ending;
                }
            }
        }
    }

    /// Says on the stolen stderr why the command could not start, with the status a shell
    /// would give: 127 for "not found", 126 for "found but not executable".
    fn failed(&self, error: &RemoteError) -> Ending {
        let mut message = b"hmz: ".to_vec();
        match &self.argv0 {
            Some(argv0) => message.extend_from_slice(argv0.as_bytes()),
            None => message.extend_from_slice(b"command"),
        }
        message.extend_from_slice(format!(": {}\n", error.strerror).as_bytes());
        self.write(self.stderr.as_fd(), &message);
        Ending::Failed(if error.errno == libc::ENOENT {
            127
        } else {
            126
        })
    }

    /// Writes all of `data` to `fd`, waiting while a non-blocking descriptor is full. Output
    /// nobody can read any more (`EPIPE`, or any other error) is dropped.
    fn write(&self, fd: BorrowedFd, mut data: &[u8]) {
        while !data.is_empty() {
            match nix::unistd::write(fd, data) {
                Ok(n) => data = &data[n..],
                Err(Errno::EINTR) => {}
                Err(Errno::EAGAIN) => {
                    if self.abandoned.load(Ordering::SeqCst) {
                        return;
                    }
                    let mut fds = [PollFd::new(fd, PollFlags::POLLOUT)];
                    let _ = poll(&mut fds, poll_timeout());
                }
                Err(error) => {
                    tracing::debug!("dropping {} bytes of remote output: {error}", data.len());
                    return;
                }
            }
        }
    }
}

fn poll_timeout() -> PollTimeout {
    PollTimeout::try_from(POLL).unwrap_or(PollTimeout::MAX)
}

/// Forwards what the agent gave the command as stdin, then ends it, unless the command
/// finished first. A descriptor `poll` refuses is read directly: `poll(2)` takes even a
/// regular file (`cmd < input`), always readable and always reaching its end.
fn pump_stdin(stdin: OwnedFd, outlet: &dyn Outlet, stop: &AtomicBool) {
    let mut buf = vec![0u8; CHUNK_SIZE];
    let mut pollable = true;
    while !stop.load(Ordering::SeqCst) {
        if pollable {
            let mut fds = [PollFd::new(stdin.as_fd(), PollFlags::POLLIN)];
            match poll(&mut fds, poll_timeout()) {
                Ok(0) | Err(Errno::EINTR) => continue,
                Ok(_) => {}
                Err(_) => pollable = false,
            }
            if stop.load(Ordering::SeqCst) {
                return;
            }
        }
        match nix::unistd::read(&stdin, &mut buf) {
            Ok(0) => break,
            Ok(n) => {
                if outlet.send(Stream::Stdin, &buf[..n]).is_err() {
                    break; // the target is gone; the output side reports it
                }
            }
            Err(Errno::EINTR) => {}
            // Only met unpolled, on a non-blocking descriptor: wait rather than spin.
            Err(Errno::EAGAIN) => thread::sleep(POLL),
            Err(_) => break,
        }
    }
    if !stop.load(Ordering::SeqCst) {
        let _ = outlet.end(Stream::Stdin);
    }
}

#[cfg(test)]
mod tests {
    use std::fs::File;
    use std::io::{Read, Write};
    use std::os::unix::net::UnixStream;
    use std::sync::mpsc;

    use nix::fcntl::{FcntlArg, OFlag, fcntl};
    use nix::unistd::pipe;

    use super::*;
    use crate::cog::netproxy::fake::{FakeRemote, Opened, Sent};

    const WAIT: Duration = Duration::from_secs(5);

    /// The descriptors a stand-in would have had stolen, and this test's ends of them.
    struct Stdio {
        given: Option<[OwnedFd; 3]>,
        stdin: File,
        stdout: File,
        stderr: File,
    }

    impl Stdio {
        fn new() -> Stdio {
            let (in_r, in_w) = pipe().unwrap();
            let (out_r, out_w) = pipe().unwrap();
            let (err_r, err_w) = pipe().unwrap();
            Stdio {
                given: Some([in_r, out_w, err_w]),
                stdin: in_w.into(),
                stdout: out_r.into(),
                stderr: err_r.into(),
            }
        }

        fn drain(file: &mut File) -> Vec<u8> {
            let mut held = Vec::new();
            file.read_to_end(&mut held).unwrap();
            held
        }
    }

    /// A proxy started for `make all` as stand-in 41, and what the test needs to drive it.
    struct Running {
        proxy: ExecProxy,
        anchor: Opened,
        done: Receiver<Completion>,
        woken: UnixStream,
        _wake: UnixStream,
    }

    impl Running {
        fn finished(&mut self) -> Completion {
            let completion = self.done.recv_timeout(WAIT).unwrap();
            self.woken.set_read_timeout(Some(WAIT)).unwrap();
            let mut byte = [9u8];
            self.woken.read_exact(&mut byte).unwrap();
            assert_eq!(byte, [0]);
            completion
        }

        fn sent(&self) -> Sent {
            self.anchor.sent.recv_timeout(WAIT).unwrap()
        }

        fn answer(&self, event: Event) {
            self.anchor.events.send(event).unwrap();
        }
    }

    fn request() -> ExecRequest {
        ExecRequest {
            argv: vec!["make".into(), "all".into()],
            program: Some("/usr/bin/make".into()),
            cwd: "/w".into(),
            env: vec![("A".into(), "b".into())],
            fence: Some(serde_json::json!({"online": false})),
        }
    }

    fn start(stdio: &mut Stdio, borrow_stdin: bool) -> Running {
        let (remote, opened) = FakeRemote::new(None);
        let (done_tx, done) = mpsc::channel();
        let (wake, woken) = UnixStream::pair().unwrap();
        let proxy = ExecProxy::with(
            remote,
            Pid::from_raw(41),
            request(),
            stdio.given.take().unwrap(),
            borrow_stdin,
            done_tx,
            wake.as_raw_fd(),
        )
        .unwrap();
        let anchor = opened.recv_timeout(WAIT).unwrap();
        Running {
            proxy,
            anchor,
            done,
            woken,
            _wake: wake,
        }
    }

    fn exited(code: i64) -> Event {
        let mut reply = Meta::new();
        reply.insert("exit_code".into(), code.into());
        Event::Done(Ok(reply))
    }

    #[test]
    fn a_result_is_reported_as_a_shell_would() {
        let reply = |json: Value| Ending::from_reply(json.as_object().unwrap());
        assert_eq!(
            reply(serde_json::json!({"exit_code": 0})),
            Ending::Exited(0)
        );
        assert_eq!(
            reply(serde_json::json!({"exit_code": 3})),
            Ending::Exited(3)
        );
        assert_eq!(
            reply(serde_json::json!({"signal": 9})),
            Ending::Signalled(9)
        );
        assert_eq!(
            reply(serde_json::json!({"exit_code": 0, "signal": 15})).wait_status(),
            143
        );
        assert_eq!(reply(serde_json::json!({})).wait_status(), 1);
    }

    #[test]
    fn the_command_is_asked_for_as_given() {
        let mut stdio = Stdio::new();
        let mut running = start(&mut stdio, false);
        assert_eq!(
            Value::Object(running.anchor.request.clone()),
            serde_json::json!({
                "argv": ["make", "all"],
                "program": "/usr/bin/make",
                "cwd": "/w",
                "env": {"A": "b"},
                "tty": false,
                "winsize": null,
                "fence": {"online": false},
            })
        );
        // Not borrowing stdin, the command's ends at once.
        assert_eq!(running.sent(), Sent::End(Stream::Stdin));
        running.answer(exited(0));
        let completion = running.finished();
        assert_eq!(completion.pid, Pid::from_raw(41));
        assert_eq!(completion.ending, Ending::Exited(0));
    }

    #[test]
    fn a_terminal_gives_its_size() {
        let size = libc::winsize {
            ws_row: 33,
            ws_col: 101,
            ws_xpixel: 0,
            ws_ypixel: 0,
        };
        let pty = nix::pty::openpty(Some(&size), None).unwrap();
        let (out_r, out_w) = pipe().unwrap();
        let (err_r, err_w) = pipe().unwrap();
        let mut stdio = Stdio {
            given: Some([pty.slave, out_w, err_w]),
            stdin: pty.master.into(),
            stdout: out_r.into(),
            stderr: err_r.into(),
        };
        let mut running = start(&mut stdio, false);
        assert_eq!(running.anchor.request["tty"], true);
        assert_eq!(
            running.anchor.request["winsize"],
            serde_json::json!([33, 101])
        );
        running.answer(exited(0));
        running.finished();
    }

    #[test]
    fn output_lands_on_the_stand_ins_own_descriptors() {
        let mut stdio = Stdio::new();
        let mut running = start(&mut stdio, false);
        running.answer(Event::Chunk(Stream::Stdout, b"built\n".to_vec()));
        running.answer(Event::Chunk(Stream::Stderr, b"warned\n".to_vec()));
        running.answer(Event::Chunk(Stream::Data, b"more\n".to_vec()));
        running.answer(Event::End(Stream::Stdout));
        running.answer(exited(2));
        assert_eq!(running.finished().ending, Ending::Exited(2));
        assert_eq!(Stdio::drain(&mut stdio.stdout), b"built\nmore\n");
        assert_eq!(Stdio::drain(&mut stdio.stderr), b"warned\n");
    }

    #[test]
    fn a_megabyte_is_pumped_whole_into_a_non_blocking_pipe() {
        let mut stdio = Stdio::new();
        let out_w = &stdio.given.as_ref().unwrap()[1];
        fcntl(out_w, FcntlArg::F_SETFL(OFlag::O_NONBLOCK)).unwrap();
        let mut running = start(&mut stdio, false);
        let sent: Vec<u8> = (0..1 << 20).map(|i: u32| (i % 251) as u8).collect();
        for chunk in sent.chunks(CHUNK_SIZE) {
            running.answer(Event::Chunk(Stream::Stdout, chunk.to_vec()));
        }
        running.answer(exited(0));
        let mut stdout = stdio.stdout.try_clone().unwrap();
        let reader = thread::spawn(move || Stdio::drain(&mut stdout));
        assert_eq!(running.finished().ending, Ending::Exited(0));
        assert_eq!(reader.join().unwrap(), sent);
    }

    #[test]
    fn output_nobody_reads_is_dropped() {
        let mut stdio = Stdio::new();
        let mut running = start(&mut stdio, false);
        drop(stdio.stdout);
        running.answer(Event::Chunk(Stream::Stdout, b"lost".to_vec()));
        running.answer(exited(0));
        assert_eq!(running.finished().ending, Ending::Exited(0));
    }

    #[test]
    fn a_signalled_command_reports_its_signal() {
        let mut stdio = Stdio::new();
        let mut running = start(&mut stdio, false);
        let mut reply = Meta::new();
        reply.insert("signal".into(), 15.into());
        running.answer(Event::Done(Ok(reply)));
        let ending = running.finished().ending;
        assert_eq!(ending, Ending::Signalled(15));
        assert_eq!(ending.wait_status(), 143);
    }

    #[test]
    fn a_command_that_could_not_start_says_so_as_a_shell_would() {
        for (errno, status) in [(libc::ENOENT, 127), (libc::EACCES, 126)] {
            let mut stdio = Stdio::new();
            let mut running = start(&mut stdio, false);
            let error = RemoteError::errno(errno);
            running.answer(Event::Done(Err(error.clone())));
            assert_eq!(running.finished().ending, Ending::Failed(status));
            assert_eq!(
                Stdio::drain(&mut stdio.stderr),
                format!("hmz: make: {}\n", error.strerror).into_bytes()
            );
            assert_eq!(Stdio::drain(&mut stdio.stdout), b"");
        }
    }

    #[test]
    fn a_target_gone_before_the_start_fails_and_closes_the_descriptors() {
        let mut stdio = Stdio::new();
        let (remote, _opened) = FakeRemote::new(Some(libc::EPIPE));
        let (done_tx, done) = mpsc::channel();
        let (wake, _woken) = UnixStream::pair().unwrap();
        let result = ExecProxy::with(
            remote,
            Pid::from_raw(41),
            request(),
            stdio.given.take().unwrap(),
            true,
            done_tx,
            wake.as_raw_fd(),
        );
        assert_eq!(result.err().unwrap().kind(), io::ErrorKind::BrokenPipe);
        assert_eq!(Stdio::drain(&mut stdio.stdout), b"");
        assert_eq!(Stdio::drain(&mut stdio.stderr), b"");
        assert!(done.try_recv().is_err());
    }

    #[test]
    fn borrowed_stdin_is_sent_and_ended_at_eof() {
        let mut stdio = Stdio::new();
        let mut running = start(&mut stdio, true);
        stdio.stdin.write_all(b"hello").unwrap();
        assert_eq!(
            running.sent(),
            Sent::Chunk(Stream::Stdin, b"hello".to_vec())
        );
        drop(stdio.stdin);
        assert_eq!(running.sent(), Sent::End(Stream::Stdin));
        running.answer(exited(0));
        assert_eq!(running.finished().ending, Ending::Exited(0));
    }

    #[test]
    fn a_file_as_stdin_is_read_to_its_end() {
        let mut file = tempfile::tempfile().unwrap();
        file.write_all(b"from a file").unwrap();
        let mut file = File::from(OwnedFd::from(file));
        std::io::Seek::rewind(&mut file).unwrap();
        let (out_r, out_w) = pipe().unwrap();
        let (err_r, err_w) = pipe().unwrap();
        let (_, spare) = pipe().unwrap();
        let mut stdio = Stdio {
            given: Some([file.into(), out_w, err_w]),
            stdin: spare.into(),
            stdout: out_r.into(),
            stderr: err_r.into(),
        };
        let mut running = start(&mut stdio, true);
        assert_eq!(
            running.sent(),
            Sent::Chunk(Stream::Stdin, b"from a file".to_vec())
        );
        assert_eq!(running.sent(), Sent::End(Stream::Stdin));
        running.answer(exited(0));
        running.finished();
    }

    #[test]
    fn stdin_left_open_is_let_go_when_the_command_ends() {
        let mut stdio = Stdio::new();
        let mut running = start(&mut stdio, true);
        running.answer(exited(0));
        running.finished();
        // The stand-in's read end was closed, and stdin never ended: the command was over.
        assert_eq!(
            stdio.stdin.write_all(b"x").unwrap_err().raw_os_error(),
            Some(libc::EPIPE)
        );
        assert!(running.anchor.sent.try_recv().is_err());
    }

    #[test]
    fn a_signal_is_forwarded_once() {
        let mut stdio = Stdio::new();
        let mut running = start(&mut stdio, false);
        assert_eq!(running.sent(), Sent::End(Stream::Stdin));
        running.proxy.signal(15);
        running.proxy.signal(15);
        running.proxy.signal(1);
        assert_eq!(running.sent(), Sent::Signal(15));
        assert_eq!(running.sent(), Sent::Signal(1));
        running.answer(exited(0));
        running.finished();
        assert!(running.anchor.sent.try_recv().is_err());
    }

    #[test]
    fn an_abandoned_command_is_killed_and_finished() {
        let mut stdio = Stdio::new();
        let mut running = start(&mut stdio, false);
        assert_eq!(running.sent(), Sent::End(Stream::Stdin));
        running.proxy.abandon();
        assert_eq!(running.sent(), Sent::Signal(libc::SIGKILL));
        let ending = running.finished().ending;
        assert_eq!(ending.wait_status(), 1);
    }
}

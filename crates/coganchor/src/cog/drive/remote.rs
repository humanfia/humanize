//! Commands on the target: the short ones a turn settles itself with (`_exchanged`, `_ran`,
//! `_status`), and the CLI itself with this process's streams (`_drives`).
//!
//! Everything goes through [`Remote`], which [`RemoteClient`] answers in a session and a
//! recording fake answers in tests.

use std::io::Write;
use std::os::fd::{AsRawFd, RawFd};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError};
use std::sync::{Arc, Mutex, OnceLock};
use std::thread;
use std::time::{Duration, Instant};

use nix::sys::signal::{SaFlags, SigAction, SigHandler, SigSet, Signal, sigaction};
use serde_json::Value;

use crate::client::{Event, Exchange, RemoteClient};
use crate::proto::{CHUNK_SIZE, Meta, RemoteError, Stream};

/// How long a short command may take (`_SETTLING`): generous, since each is a round trip to a
/// machine that may be far away, and bounded, since a target that stopped answering must read
/// as one that has rather than hang the turn.
pub(super) const SETTLING: Duration = Duration::from_secs(120);

/// What a status has added to it to say a signal ended the command (`_SIGNALLED`).
const SIGNALLED: i64 = 128;

/// How long the thread carrying stdin waits before looking again at whether the turn is over
/// (`_LOOKING`), so that it ends when the turn does rather than holding this process's input.
const LOOKING: Duration = Duration::from_millis(200);

/// What a native turn asks of the anchor.
pub(crate) trait Remote {
    /// Shakes hands, presenting `token`.
    fn start(&self, token: Option<&str>) -> Result<(), RemoteError>;
    /// The `HELLO` reply.
    fn info(&self) -> Meta;
    /// Starts a command: `request` is the `EXEC` metadata without `op`.
    fn exec(&self, request: Meta) -> Result<Running, RemoteError>;

    /// How many times the turn was given up on from the keyboard so far.
    fn interrupts(&self) -> usize {
        0
    }

    /// Takes the signals aimed at this process for the CLI `feed` reaches, while what this
    /// answers is held.
    fn onward(&self, feed: Arc<dyn Feed>) -> std::io::Result<Option<Onward>> {
        let _ = feed;
        Ok(None)
    }
}

/// A command started on the target.
pub(crate) struct Running {
    /// What arrives on it, ending with `Event::Done`.
    pub events: Receiver<Event>,
    /// What is sent to it, from any thread.
    pub feed: Arc<dyn Feed>,
}

/// The sending half of a command on the target (`ExecHandle`).
pub(crate) trait Feed: Send + Sync {
    /// Sends bytes to its stdin.
    fn send(&self, body: &[u8]) -> Result<(), RemoteError>;
    /// Ends its stdin.
    fn end(&self) -> Result<(), RemoteError>;
    /// Sends its process group a signal.
    fn signal(&self, signal: i32) -> Result<(), RemoteError>;
}

/// An [`Exchange`] whose events were taken out of it, shared between the threads feeding it.
struct Fed(Mutex<Exchange>);

impl Fed {
    fn held(&self) -> std::sync::MutexGuard<'_, Exchange> {
        self.0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }
}

impl Feed for Fed {
    fn send(&self, body: &[u8]) -> Result<(), RemoteError> {
        self.held().send(Stream::Stdin, body)
    }

    fn end(&self) -> Result<(), RemoteError> {
        self.held().end(Stream::Stdin)
    }

    fn signal(&self, signal: i32) -> Result<(), RemoteError> {
        self.held().signal(signal)
    }
}

impl Remote for RemoteClient {
    fn start(&self, token: Option<&str>) -> Result<(), RemoteError> {
        RemoteClient::start(self, token).map(|_| ())
    }

    fn info(&self) -> Meta {
        RemoteClient::info(self)
    }

    fn exec(&self, request: Meta) -> Result<Running, RemoteError> {
        let mut exchange = self.start_exec(request)?;
        let events = std::mem::replace(&mut exchange.events, mpsc::channel().1);
        Ok(Running {
            events,
            feed: Arc::new(Fed(Mutex::new(exchange))),
        })
    }
}

/// The `EXEC` metadata `RemoteClient.start_exec` sends, keys in its order: no `program` of
/// its own, no terminal.
pub(super) fn request(argv: &[String], cwd: &str, env: Meta, fence: Option<&Meta>) -> Meta {
    let mut meta = Meta::new();
    meta.insert("argv".into(), Value::from(argv.to_vec()));
    meta.insert("program".into(), Value::Null);
    meta.insert("cwd".into(), Value::from(cwd));
    meta.insert("env".into(), Value::Object(env));
    meta.insert("tty".into(), Value::Bool(false));
    meta.insert("winsize".into(), Value::Null);
    meta.insert(
        "fence".into(),
        fence.map_or(Value::Null, |said| Value::Object(said.clone())),
    );
    meta
}

/// The error a connection lost mid-command reads as.
fn lost() -> RemoteError {
    RemoteError::new(libc::EPIPE, "connection to the target lost")
}

/// What a command on the target exited with, as a shell reports it (`_status`): its own
/// status, or 128 plus the signal that killed it; 1 where the target said neither.
pub(super) fn status(result: &Meta) -> i32 {
    if let Some(signal) = result.get("signal").filter(|said| !said.is_null()) {
        return (SIGNALLED + signal.as_i64().unwrap_or(0)) as i32;
    }
    result.get("exit_code").and_then(Value::as_i64).unwrap_or(1) as i32
}

/// Runs one short command on the target and waits, at most `within`, for the whole of what
/// it wrote to stdout (`_exchanged`). One stuck past that is killed there as well as given up
/// on here.
pub(super) fn exchanged(
    remote: &dyn Remote,
    argv: &[String],
    cwd: &str,
    feeding: &[u8],
    within: Duration,
) -> anyhow::Result<(i32, Vec<u8>)> {
    let seen = remote.interrupts();
    let running = remote.exec(request(argv, cwd, Meta::new(), None))?;
    // A frame apiece, at the size the protocol carries one in.
    for piece in feeding.chunks(CHUNK_SIZE) {
        running.feed.send(piece)?;
    }
    running.feed.end()?;
    let until = Instant::now() + within;
    let mut said = Vec::new();
    loop {
        if remote.interrupts() != seen {
            return Err(Interrupted.into());
        }
        let left = until.saturating_duration_since(Instant::now());
        match running.events.recv_timeout(left.min(LOOKING)) {
            Ok(Event::Chunk(Stream::Stdout, data)) => said.extend_from_slice(&data),
            Ok(Event::Chunk(..) | Event::End(_)) => {}
            Err(RecvTimeoutError::Timeout) if !left.is_zero() => {}
            Ok(Event::Done(Ok(result))) => return Ok((status(&result), said)),
            Ok(Event::Done(Err(error))) => return Err(error.into()),
            Err(RecvTimeoutError::Timeout) => {
                let _ = running.feed.signal(libc::SIGKILL);
                anyhow::bail!(
                    "the target did not answer '{}' in {:.0}s",
                    argv[0],
                    within.as_secs_f64()
                );
            }
            Err(RecvTimeoutError::Disconnected) => return Err(lost().into()),
        }
    }
}

/// Runs one short command and answers its status and the line it said, trimmed (`_ran`).
pub(super) fn ran(
    remote: &dyn Remote,
    argv: &[String],
    cwd: &str,
    feeding: &[u8],
) -> anyhow::Result<(i32, String)> {
    let (status, said) = exchanged(remote, argv, cwd, feeding, SETTLING)?;
    Ok((status, String::from_utf8_lossy(&said).trim().to_owned()))
}

/// A turn given up on from the keyboard: `^C` before the CLI runs, or twice while it does.
/// What `KeyboardInterrupt` is in the Python, which exits 130 once the turn is tidied.
#[derive(Debug, thiserror::Error)]
#[error("interrupted")]
pub(super) struct Interrupted;

/// Where the CLI's streams come from and go to.
pub(crate) struct Io<'a> {
    /// What is carried to its stdin, read from the descriptor byte for byte.
    pub stdin: RawFd,
    pub stdout: &'a mut dyn Write,
    pub stderr: &'a mut dyn Write,
}

/// Runs the CLI on the target with this process's streams, and waits for it (`_drives`):
/// byte for byte and never waiting for a line, since the backends this exists for frame their
/// own protocol over these streams. Its status, or 128 plus the signal that killed it.
pub(super) fn drives(
    remote: &dyn Remote,
    argv: &[String],
    cwd: &str,
    environ: Meta,
    fence: Option<&Meta>,
    io: &mut Io<'_>,
) -> anyhow::Result<i32> {
    let seen = remote.interrupts();
    let running = remote.exec(request(argv, cwd, environ, fence))?;
    let onward = remote.onward(running.feed.clone())?;
    let done = Arc::new(AtomicBool::new(false));
    let (over, ended) = mpsc::channel::<()>();
    {
        let (feed, done, fd) = (running.feed.clone(), done.clone(), io.stdin);
        thread::Builder::new()
            .name("hmz-anchor-stdin".into())
            .spawn(move || {
                upward(fd, &*feed, &done);
                // The far end may be gone already, which ends the input all the same.
                let _ = feed.end();
                drop(over);
            })?;
    }
    let outcome = loop {
        if remote.interrupts() != seen {
            break Err(Interrupted.into());
        }
        match running.events.recv_timeout(LOOKING) {
            Ok(Event::Chunk(Stream::Stderr, data)) => {
                let _ = io.stderr.write_all(&data);
                let _ = io.stderr.flush();
            }
            Ok(Event::Chunk(_, data)) => {
                let _ = io.stdout.write_all(&data);
                let _ = io.stdout.flush();
            }
            Ok(Event::End(_)) | Err(RecvTimeoutError::Timeout) => {}
            Ok(Event::Done(result)) => break result.map(|said| status(&said)).map_err(Into::into),
            Err(RecvTimeoutError::Disconnected) => break Err(lost().into()),
        }
    };
    done.store(true, Ordering::SeqCst);
    drop(onward);
    let _ = ended.recv_timeout(LOOKING * 2);
    outcome
}

/// Carries what this process is given to the CLI until there is no more or the turn is over:
/// watched for rather than read into, so the thread ends when the turn does.
fn upward(fd: RawFd, feed: &dyn Feed, done: &AtomicBool) {
    let mut buffer = vec![0u8; CHUNK_SIZE];
    while !done.load(Ordering::SeqCst) {
        let mut watched = libc::pollfd {
            fd,
            events: libc::POLLIN,
            revents: 0,
        };
        // SAFETY: one valid pollfd.
        let ready = unsafe { libc::poll(&mut watched, 1, LOOKING.as_millis() as libc::c_int) };
        if ready < 0 {
            if nix::errno::Errno::last() == nix::errno::Errno::EINTR {
                continue;
            }
            return;
        }
        if ready == 0 {
            continue;
        }
        // SAFETY: reading into a buffer of the length given.
        let got = unsafe { libc::read(fd, buffer.as_mut_ptr().cast(), buffer.len()) };
        if got < 0 {
            if nix::errno::Errno::last() == nix::errno::Errno::EINTR {
                continue;
            }
            return; // stdin closed under us, which is the end of the input either way
        }
        if got == 0 || feed.send(&buffer[..got as usize]).is_err() {
            return;
        }
    }
}

// ---------------------------------------------------------------- signals

/// The write end of the pipe the signal handler notes each signal in: made once and never
/// closed, so a handler running as a turn ends never writes into a descriptor reused since.
static WAKE: OnceLock<RawFd> = OnceLock::new();

/// The turn the signals noted are for, if one is listening.
static LISTENING: Mutex<Option<Arc<Shared>>> = Mutex::new(None);

extern "C" fn caught(number: libc::c_int) {
    let saved = nix::errno::Errno::last_raw();
    if let Some(&fd) = WAKE.get() {
        let byte = number as u8;
        // SAFETY: write(2) is async-signal-safe; one byte from the stack.
        unsafe { libc::write(fd, (&byte as *const u8).cast(), 1) };
    }
    nix::errno::Errno::set_raw(saved);
}

/// The pipe and the thread reading it, made the first time a turn takes a signal.
fn wake() -> std::io::Result<()> {
    if WAKE.get().is_some() {
        return Ok(());
    }
    let (read, write) = nix::unistd::pipe()?;
    for fd in [&read, &write] {
        nix::fcntl::fcntl(
            fd,
            nix::fcntl::FcntlArg::F_SETFD(nix::fcntl::FdFlag::FD_CLOEXEC),
        )?;
    }
    thread::Builder::new()
        .name("hmz-anchor-signals".into())
        .spawn(move || {
            let mut byte = [0u8; 1];
            loop {
                match nix::unistd::read(&read, &mut byte) {
                    Ok(1) => {}
                    Err(nix::errno::Errno::EINTR) => continue,
                    _ => return,
                }
                let listening = LISTENING
                    .lock()
                    .unwrap_or_else(|poisoned| poisoned.into_inner())
                    .clone();
                if let (Some(shared), Ok(signal)) =
                    (listening, Signal::try_from(i32::from(byte[0])))
                {
                    shared.heard(signal);
                }
            }
        })?;
    let _ = WAKE.set(write.as_raw_fd());
    std::mem::forget(write);
    Ok(())
}

/// The disposition sending a signal to [`caught`].
fn taking() -> SigAction {
    SigAction::new(
        SigHandler::Handler(caught),
        SaFlags::SA_RESTART,
        SigSet::empty(),
    )
}

/// What a turn's signals are, and where they go.
#[derive(Default)]
struct Shared {
    /// `SIGINT`s that were not sent on to the CLI: each gives the turn up.
    interrupts: AtomicUsize,
    /// The CLI while it runs.
    cli: Mutex<Option<Cli>>,
}

/// The CLI signals are sent on to, what each signal did before it was taken for it, and
/// which were sent on already.
struct Cli {
    feed: Arc<dyn Feed>,
    before: Vec<(Signal, SigAction)>,
    forwarded: Vec<Signal>,
}

impl Shared {
    /// One signal, as the handler noted it (`onward` in `_drives`, and `KeyboardInterrupt`).
    ///
    /// While the CLI runs, the first of each is sent on to it, which is what stops a turn
    /// stopped by hand, and what it did before is put back, so the second goes where it went
    /// before: for `SIGINT` under its default, that is giving the turn up. Any other `SIGINT`
    /// gives the turn up.
    fn heard(&self, signal: Signal) {
        let feed = {
            let mut cli = self
                .cli
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner());
            match cli.as_mut() {
                Some(cli) if !cli.forwarded.contains(&signal) => {
                    cli.forwarded.push(signal);
                    if let Some((_, was)) = cli.before.iter().find(|(one, _)| *one == signal)
                        && !(signal == Signal::SIGINT && was.handler() == SigHandler::SigDfl)
                    {
                        // SAFETY: putting back what was there.
                        let _ = unsafe { sigaction(signal, was) };
                    }
                    Some(cli.feed.clone())
                }
                _ => None,
            }
        };
        match feed {
            Some(feed) => {
                if let Err(why) = feed.signal(signal as i32) {
                    tracing::debug!("could not forward signal {signal} to remote command: {why}");
                }
            }
            None if signal == Signal::SIGINT => {
                self.interrupts.fetch_add(1, Ordering::SeqCst);
            }
            None => {}
        }
    }
}

/// A turn's signals: `SIGINT` taken for the whole of it, so that `^C` gives it up tidied
/// rather than leaving a credential on the target, and `SIGINT` and `SIGTERM` both while the
/// CLI runs ([`Signals::onward`]).
pub(crate) struct Signals {
    shared: Arc<Shared>,
    /// Whether this takes signals at all; a test's takes none.
    taking: bool,
    /// What `SIGINT` did before, where this took it.
    before: Option<SigAction>,
}

impl Signals {
    /// Signals that are never taken, whose interrupts a test says.
    pub fn quiet() -> Signals {
        Signals {
            shared: Arc::default(),
            taking: false,
            before: None,
        }
    }

    /// Takes `SIGINT` for a turn, unless it is ignored, which a turn leaves as it is.
    pub fn taken() -> std::io::Result<Signals> {
        wake()?;
        let shared = Arc::<Shared>::default();
        *LISTENING
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner()) = Some(shared.clone());
        // SAFETY: the handler only writes to a pipe.
        let was = unsafe { sigaction(Signal::SIGINT, &taking()) }?;
        let before = if was.handler() == SigHandler::SigIgn {
            // SAFETY: putting back what was there.
            unsafe { sigaction(Signal::SIGINT, &was) }?;
            None
        } else {
            Some(was)
        };
        Ok(Signals {
            shared,
            taking: true,
            before,
        })
    }

    /// How many times the turn was given up on so far.
    pub fn interrupts(&self) -> usize {
        self.shared.interrupts.load(Ordering::SeqCst)
    }

    /// Gives the turn up, as a second `^C` does.
    #[cfg(test)]
    pub fn interrupt(&self) {
        self.shared.interrupts.fetch_add(1, Ordering::SeqCst);
    }

    /// Takes `SIGINT` and `SIGTERM` for the CLI `feed` reaches, until what this answers is
    /// dropped.
    pub fn onward(&self, feed: Arc<dyn Feed>) -> std::io::Result<Onward> {
        let mut before = Vec::new();
        let mut installed = Vec::new();
        if self.taking {
            for signal in [Signal::SIGINT, Signal::SIGTERM] {
                match (signal, self.before) {
                    (Signal::SIGINT, Some(was)) => before.push((signal, was)),
                    _ => {
                        // SAFETY: the handler only writes to a pipe.
                        let was = match unsafe { sigaction(signal, &taking()) } {
                            Ok(was) => was,
                            Err(why) => {
                                Onward::undo(&installed);
                                return Err(why.into());
                            }
                        };
                        before.push((signal, was));
                        installed.push((signal, was));
                    }
                }
            }
        }
        *self
            .shared
            .cli
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner()) = Some(Cli {
            feed,
            before,
            forwarded: Vec::new(),
        });
        Ok(Onward {
            shared: self.shared.clone(),
            installed,
        })
    }
}

impl Drop for Signals {
    fn drop(&mut self) {
        if let Some(was) = &self.before {
            // SAFETY: putting back what was there.
            let _ = unsafe { sigaction(Signal::SIGINT, was) };
        }
        if self.taking {
            *LISTENING
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner()) = None;
        }
    }
}

/// The signals taken for the CLI while it runs; put back as they were when dropped.
pub(crate) struct Onward {
    shared: Arc<Shared>,
    installed: Vec<(Signal, SigAction)>,
}

impl Onward {
    fn undo(installed: &[(Signal, SigAction)]) {
        for (signal, was) in installed {
            // SAFETY: putting back what was there.
            let _ = unsafe { sigaction(*signal, was) };
        }
    }
}

impl Drop for Onward {
    fn drop(&mut self) {
        *self
            .shared
            .cli
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner()) = None;
        Onward::undo(&self.installed);
    }
}

/// A connection with the turn's signals beside it.
pub(crate) struct Watched<'a> {
    pub remote: &'a dyn Remote,
    pub signals: &'a Signals,
}

impl Remote for Watched<'_> {
    fn start(&self, token: Option<&str>) -> Result<(), RemoteError> {
        self.remote.start(token)
    }

    fn info(&self) -> Meta {
        self.remote.info()
    }

    fn exec(&self, request: Meta) -> Result<Running, RemoteError> {
        self.remote.exec(request)
    }

    fn interrupts(&self) -> usize {
        self.signals.interrupts()
    }

    fn onward(&self, feed: Arc<dyn Feed>) -> std::io::Result<Option<Onward>> {
        self.signals.onward(feed).map(Some)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Remembers the signals it was sent.
    #[derive(Default)]
    struct Signalled(Mutex<Vec<i32>>);

    impl Feed for Signalled {
        fn send(&self, _: &[u8]) -> Result<(), RemoteError> {
            Ok(())
        }

        fn end(&self) -> Result<(), RemoteError> {
            Ok(())
        }

        fn signal(&self, signal: i32) -> Result<(), RemoteError> {
            self.0.lock().unwrap().push(signal);
            Ok(())
        }
    }

    #[test]
    fn the_first_signal_goes_to_the_cli_and_a_second_interrupt_gives_the_turn_up() {
        let signals = Signals::quiet();
        let feed = Arc::new(Signalled::default());
        // Before the CLI runs, ^C gives the turn up.
        signals.shared.heard(Signal::SIGINT);
        assert_eq!(signals.interrupts(), 1);
        let onward = signals.onward(feed.clone()).unwrap();
        for signal in [Signal::SIGINT, Signal::SIGTERM, Signal::SIGINT] {
            signals.shared.heard(signal);
        }
        assert_eq!(*feed.0.lock().unwrap(), [libc::SIGINT, libc::SIGTERM]);
        assert_eq!(signals.interrupts(), 2);
        drop(onward);
        signals.shared.heard(Signal::SIGTERM);
        assert_eq!(
            feed.0.lock().unwrap().len(),
            2,
            "nothing goes to a CLI that is over"
        );
    }
}

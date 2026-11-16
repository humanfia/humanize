//! The ptrace event loop that keeps the agent honest about where it runs. Port of
//! `hmz.coganchor.supervisor`. [Unit 10]
//!
//! The agent is forked under the trap filter (and the fence's filters and walls), stops
//! itself, and only then is the client started and the handshake made: no thread may exist
//! across the fork. The loop never blocks on the target: a remote command is handed to an
//! [`crate::cog::execproxy::ExecProxy`] and the process that asked for it parked as a
//! stand-in until its completion arrives on the wake pipe.
//!
//! The loop waits on two things at once -- child state changes and finished remote work --
//! with `SIGCHLD` made pollable through a self-pipe its handler writes to, beside the wake
//! pipe every [`crate::cog::execproxy::Completion`] is announced on.

use std::collections::HashMap;
use std::ffi::{CString, OsStr, OsString};
use std::io::{self, IoSlice, IoSliceMut};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::ffi::{OsStrExt, OsStringExt};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicI32, Ordering};
use std::sync::mpsc::{self, Receiver, Sender};
use std::thread::JoinHandle;

use nix::sys::signal::{SaFlags, SigAction, SigHandler, SigSet, Signal, sigaction};
use nix::unistd::Pid;

use crate::client::RemoteClient;
use crate::cog::execproxy::{Completion, Ending, ExecProxy, ExecRequest};
use crate::cog::handlers::{Call, Dispatcher, Memory, Outcome, Session, Verdict, plant};
use crate::cog::netproxy::NetProxy;
use crate::cog::pathcalls::{self, PathCall};
use crate::cog::policy;
use crate::cog::router::{Place, Router};
use crate::cog::shadow::ShadowTree;
use crate::cog::standin::{self, restart, wait_raw};
use crate::cog::walls::Walls;
use crate::proto::json::{from_os, to_os};
use crate::proto::{Meta, Op, RemoteError, hello_fences};
use crate::sys::ptrace::{self, Regs, SyscallStop};
use crate::sys::{procfs, syscalls};

/// The agent to start.
#[derive(Clone, Debug)]
pub struct Launch {
    pub program: PathBuf,
    pub argv: Vec<OsString>,
    pub env: Vec<(OsString, OsString)>,
    pub cwd: PathBuf,
}

/// How the agent is held.
#[derive(Default)]
pub struct Options {
    /// The secret presented at the handshake.
    pub token: Option<String>,
    /// Variables not passed to commands run on the target.
    pub private: Vec<String>,
    /// False where the fence lets nothing be written: mutations fail `EACCES` unasked.
    pub writes: bool,
    /// The fence's walls, put up in the child.
    pub walls: Option<Walls>,
    /// The fence's `EXEC` rules, sent with every remote command.
    pub fence: Option<serde_json::Value>,
}

/// One supervised agent.
pub struct Supervisor {
    launch: Launch,
    client: Arc<RemoteClient>,
    router: Arc<Router>,
    shadow: Arc<ShadowTree>,
    net: Option<NetProxy>,
    options: Options,
}

impl Supervisor {
    pub fn new(
        launch: Launch,
        client: Arc<RemoteClient>,
        router: Arc<Router>,
        shadow: Arc<ShadowTree>,
        net: Option<NetProxy>,
        options: Options,
    ) -> Supervisor {
        Supervisor {
            launch,
            client,
            router,
            shadow,
            net,
            options,
        }
    }

    /// Runs the agent to its end, returning its status (exit code, or 128 plus its signal).
    pub fn run(self) -> io::Result<i32> {
        let mut running = Running::new(self)?;
        let ran = running.run();
        running.flush_final();
        running.teardown();
        ran.map(|()| running.status)
    }
}

/// How long the loop sleeps before looking at parked stand-ins' pending signals.
const IDLE_MS: libc::c_int = 200;

/// Signals an agent cancels a command with; relayed to the remote one.
const CANCEL_SIGNALS: [i32; 4] = [libc::SIGINT, libc::SIGTERM, libc::SIGQUIT, libc::SIGHUP];

/// Signals whose default action terminates, replayed onto a stand-in rather than flattened
/// into an exit code.
const FATAL_SIGNALS: [i32; 14] = [
    libc::SIGHUP,
    libc::SIGINT,
    libc::SIGQUIT,
    libc::SIGILL,
    libc::SIGABRT,
    libc::SIGFPE,
    libc::SIGKILL,
    libc::SIGSEGV,
    libc::SIGPIPE,
    libc::SIGALRM,
    libc::SIGTERM,
    libc::SIGBUS,
    libc::SIGXCPU,
    libc::SIGXFSZ,
];

/// What an agent installed as a script is started by before it is the agent.
const SHELLS: [&str; 5] = ["sh", "bash", "dash", "zsh", "ksh"];
const LAUNCHERS: [&str; 6] = ["sh", "bash", "dash", "zsh", "ksh", "env"];

/// How many subshells deep a launcher's helper is looked for.
const LAUNCHER_DEPTH: usize = 16;

/// Per-process state for one traced task.
struct Tracee {
    attached: bool,
    exec_count: u32,
    /// Set while this process stands in for a command running on the target.
    proxy: Option<ExecProxy>,
    /// The errno to plant at the next syscall-exit stop, for a cancelled syscall.
    pending_errno: Option<i32>,
    /// The cancel signals already relayed to its remote command, as a mask.
    relayed: u64,
    /// Whether it was parked as a stand-in, rather than left at its `execve`.
    parked: bool,
}

impl Tracee {
    fn new(attached: bool) -> Tracee {
        Tracee {
            attached,
            exec_count: 0,
            proxy: None,
            pending_errno: None,
            relayed: 0,
            parked: false,
        }
    }
}

/// What a `waitpid` status says, as the loop acts on it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Stop {
    /// It is gone, with this status (exit code, or 128 plus the signal).
    Died(i32),
    /// A `PTRACE_EVENT_*` stop.
    Event(i32),
    /// A syscall stop (`SIGTRAP | 0x80`).
    Syscall,
    /// A plain `SIGTRAP`.
    Trap,
    /// A signal-delivery (or group) stop.
    Signal(i32),
}

/// Reads a raw `waitpid` status.
pub(crate) fn classify(status: i32) -> Stop {
    if libc::WIFEXITED(status) {
        return Stop::Died(libc::WEXITSTATUS(status));
    }
    if libc::WIFSIGNALED(status) {
        return Stop::Died(128 + libc::WTERMSIG(status));
    }
    let signal = libc::WSTOPSIG(status);
    let event = status >> 16;
    if event != 0 {
        Stop::Event(event)
    } else if signal == libc::SIGTRAP | 0x80 {
        Stop::Syscall
    } else if signal == libc::SIGTRAP {
        Stop::Trap
    } else {
        Stop::Signal(signal)
    }
}

/// The status a stand-in is released with, and the signal it is to die of instead where the
/// remote command died of a fatal one (`ExecResult.wait_status`).
pub(crate) fn release_status(ending: Ending) -> (i32, Option<i32>) {
    match ending {
        Ending::Exited(code) | Ending::Failed(code) => (code, None),
        Ending::Signalled(signal) => (
            128 + signal,
            FATAL_SIGNALS.contains(&signal).then_some(signal),
        ),
    }
}

/// Whether a remote command is handed the stand-in's own stdin (`_stdin`): not where it is
/// this process's own stdin -- the pipe the agent's driver speaks on -- unless that is a tty
/// or the agent is a shell, which hands its stdin to what it runs on purpose.
pub(crate) fn borrows_stdin(same_as_ours: bool, tty: bool, agent_is_shell: bool) -> bool {
    !same_as_ours || tty || agent_is_shell
}

/// Whether the agent was started as a script a shell or `env` runs (`_script`).
pub(crate) fn script(program: &Path) -> bool {
    use std::io::Read;
    let mut first = [0u8; 256];
    let Ok(mut file) = std::fs::File::open(program) else {
        return false;
    };
    let Ok(read) = file.read(&mut first) else {
        return false;
    };
    let line = first[..read].split(|b| *b == b'\n').next().unwrap_or(&[]);
    let Some(rest) = line.strip_prefix(b"#!") else {
        return false;
    };
    let Some(word) = rest
        .split(|b| b.is_ascii_whitespace())
        .find(|w| !w.is_empty())
    else {
        return false;
    };
    let name = word.rsplit(|b| *b == b'/').next().unwrap_or(word);
    LAUNCHERS.iter().any(|l| l.as_bytes() == name)
}

/// Whether `pid` was forked from the agent's launcher (`root`), running nothing since, walked
/// up through the subshells a script's command substitutions fork (`_launched`).
pub(crate) fn launched(
    mut pid: i32,
    root: i32,
    parent_of: impl Fn(i32) -> i32,
    exec_count: impl Fn(i32) -> Option<u32>,
) -> bool {
    for _ in 0..LAUNCHER_DEPTH {
        let parent = parent_of(pid);
        if parent == root {
            return true;
        }
        match exec_count(parent) {
            Some(0) => pid = parent,
            _ => return false,
        }
    }
    false
}

/// An `envp`'s entries as variables, a later one replacing an earlier one in its place, those
/// named `private` dropped (`_as_mapping` and the filter of `begin_remote_exec`).
pub(crate) fn environment(entries: &[OsString], private: &[String]) -> Vec<(OsString, OsString)> {
    let mut env: Vec<(OsString, OsString)> = Vec::new();
    for entry in entries {
        let bytes = entry.as_bytes();
        let Some(cut) = bytes.iter().position(|b| *b == b'=') else {
            continue;
        };
        let name = OsStr::from_bytes(&bytes[..cut]);
        if private.iter().any(|p| p.as_bytes() == name.as_bytes()) {
            continue;
        }
        let value = OsString::from_vec(bytes[cut + 1..].to_vec());
        match env.iter_mut().find(|(n, _)| n == name) {
            Some(slot) => slot.1 = value,
            None => env.push((name.to_owned(), value)),
        }
    }
    env
}

/// The parent of `pid`'s process, as `/proc/<pid>/status` says; 0 where it has gone
/// (`procfs.parent_of`).
fn parent_of(pid: i32) -> i32 {
    std::fs::read_to_string(format!("/proc/{pid}/status"))
        .ok()
        .and_then(|status| {
            status
                .lines()
                .find_map(|line| line.strip_prefix("PPid:"))
                .and_then(|said| said.trim().parse().ok())
        })
        .unwrap_or(0)
}

/// The descriptor the signal handler writes to, -1 while none is installed.
static SIGNAL_FD: AtomicI32 = AtomicI32::new(-1);

/// Wakes the loop and does nothing else: `SIGCHLD` and `SIGINT` (which the supervisor so
/// ignores, leaving `^C` to the agent).
extern "C" fn on_signal(_: libc::c_int) {
    let fd = SIGNAL_FD.load(Ordering::Relaxed);
    if fd >= 0 {
        // SAFETY: write(2) is async-signal-safe; errno is put back for the code interrupted.
        unsafe {
            let saved = *libc::__errno_location();
            let byte = 1u8;
            libc::write(fd, (&byte as *const u8).cast(), 1);
            *libc::__errno_location() = saved;
        }
    }
}

/// A non-blocking, close-on-exec pipe.
fn pipe() -> io::Result<(OwnedFd, OwnedFd)> {
    nix::unistd::pipe2(nix::fcntl::OFlag::O_NONBLOCK | nix::fcntl::OFlag::O_CLOEXEC)
        .map_err(io::Error::from)
}

/// Reads a non-blocking descriptor empty.
fn drain(fd: RawFd) {
    let mut buffer = [0u8; 4096];
    // SAFETY: reading into a buffer of the length given.
    while unsafe { libc::read(fd, buffer.as_mut_ptr().cast(), buffer.len()) } > 0 {}
}

/// Runs a ptrace restart, tolerating a tracee that has already gone (`_try`).
fn tolerate(what: &str, pid: i32, done: io::Result<()>) {
    if let Err(error) = done
        && error.raw_os_error() != Some(libc::ESRCH)
    {
        tracing::debug!("{what}({pid}) failed: {error}");
    }
}

/// A supervised agent, from fork to its end.
struct Running {
    launch: Launch,
    client: Arc<RemoteClient>,
    router: Arc<Router>,
    shadow: Arc<ShadowTree>,
    net: Option<NetProxy>,
    options: Options,
    dispatcher: Dispatcher,
    tracees: HashMap<i32, Tracee>,
    done: Sender<Completion>,
    completions: Receiver<Completion>,
    wake: (OwnedFd, OwnedFd),
    signals: (OwnedFd, OwnedFd),
    /// What this process did with each signal before, put back at teardown.
    handlers: Vec<(Signal, SigAction)>,
    root: i32,
    status: i32,
    /// The descriptor the agent's `bind`s and `listen`s stop at, until it is answered.
    listener: Option<OwnedFd>,
    listens: Option<JoinHandle<()>>,
    /// Whether the agent's own process is still its launcher -- a shell running the script
    /// it was installed as, or `env` finding its interpreter -- rather than the agent.
    launching: bool,
}

impl Running {
    fn new(sup: Supervisor) -> io::Result<Running> {
        let (done, completions) = mpsc::channel();
        let wake = pipe()?;
        let signals = pipe()?;
        let mut running = Running {
            launch: sup.launch,
            client: sup.client,
            router: sup.router,
            shadow: sup.shadow,
            net: sup.net,
            options: sup.options,
            dispatcher: Dispatcher::new(),
            tracees: HashMap::new(),
            done,
            completions,
            wake,
            signals,
            handlers: Vec::new(),
            root: 0,
            status: 1,
            listener: None,
            listens: None,
            launching: false,
        };
        SIGNAL_FD.store(running.signals.1.as_raw_fd(), Ordering::Relaxed);
        let action = SigAction::new(
            SigHandler::Handler(on_signal),
            SaFlags::SA_RESTART,
            SigSet::empty(),
        );
        for signal in [Signal::SIGCHLD, Signal::SIGINT] {
            // SAFETY: the handler only calls write(2).
            let was = unsafe { sigaction(signal, &action) }.map_err(io::Error::from)?;
            running.handlers.push((signal, was));
        }
        Ok(running)
    }

    fn run(&mut self) -> io::Result<()> {
        self.root = self.fork_tracee()?;
        let (_, status) = wait_raw(self.root, 0)?;
        if !libc::WIFSTOPPED(status) {
            self.tracees.clear();
            return Err(io::Error::other(format!(
                "agent exited before it could be traced (status {status})"
            )));
        }
        if let Some(listener) = self.listener.take() {
            self.listens = Some(crate::fence::loopback::supervise(listener));
        }
        // The agent is parked at its SIGSTOP, so threads may start now.
        if let Err(error) = self.handshake() {
            // Left to run, it would be seccomp-filtered with nobody servicing its traps.
            let _ = nix::sys::signal::kill(Pid::from_raw(self.root), Signal::SIGKILL);
            let _ = wait_raw(self.root, 0);
            return Err(error);
        }
        self.tracees.insert(self.root, Tracee::new(true));
        tolerate(
            "cont",
            self.root,
            restart(false, Pid::from_raw(self.root), 0),
        );
        self.serve();
        Ok(())
    }

    /// Starts the client, checks the target can fence what it runs where that is asked, and
    /// sets the agent's trace options.
    fn handshake(&mut self) -> io::Result<()> {
        let info = self
            .client
            .start(self.options.token.as_deref())
            .map_err(|error| error.to_io())?;
        if let Some(fence) = &self.options.fence {
            let net = fence.get("online") == Some(&serde_json::Value::Bool(false));
            if !hello_fences(&info, net) {
                return Err(io::Error::new(
                    io::ErrorKind::PermissionDenied,
                    format!(
                        "the target cannot fence the commands it runs: it needs Landlock{}",
                        if net { " ABI 4 and seccomp" } else { "" }
                    ),
                ));
            }
        }
        let platform = info.get("platform").and_then(|p| p.as_str()).unwrap_or("");
        self.router.learn_platform(platform);
        tracing::info!(
            "connected to the target {}",
            info.get("hostname").and_then(|h| h.as_str()).unwrap_or("?")
        );
        ptrace::set_cog_options(Pid::from_raw(self.root))
    }

    /// Pushes anything written after the last remote command.
    fn flush_final(&self) {
        if self.root == 0 {
            return;
        }
        if let Err(error) = self.shadow.flush() {
            tracing::error!("could not push final changes to the target: {error}");
        }
    }

    fn teardown(&mut self) {
        SIGNAL_FD.store(-1, Ordering::Relaxed);
        for (signal, was) in self.handlers.drain(..) {
            // SAFETY: putting back what was there.
            let _ = unsafe { sigaction(signal, &was) };
        }
        // Answers until the fenced tree is gone, on its own.
        self.listens = None;
        self.listener = None;
        // Dropping a proxy abandons its command.
        self.tracees.clear();
    }

    // ------------------------------------------------------------------ start

    /// Forks the agent under `PTRACE_TRACEME`, the fence and the trap filter. Everything the
    /// child needs is made before the fork, so the child allocates as little as it can.
    fn fork_tracee(&mut self) -> io::Result<i32> {
        let launch = &self.launch;
        let cstring = |bytes: &[u8]| {
            CString::new(bytes).map_err(|_| io::Error::from_raw_os_error(libc::EINVAL))
        };
        let program = cstring(launch.program.as_os_str().as_bytes())?;
        let cwd = cstring(launch.cwd.as_os_str().as_bytes())?;
        let argv = launch
            .argv
            .iter()
            .map(|a| cstring(a.as_bytes()))
            .collect::<io::Result<Vec<_>>>()?;
        let envp = launch
            .env
            .iter()
            .map(|(n, v)| cstring(&[n.as_bytes(), b"=", v.as_bytes()].concat()))
            .collect::<io::Result<Vec<_>>>()?;
        let mut argv_ptrs: Vec<*const libc::c_char> = argv.iter().map(|a| a.as_ptr()).collect();
        argv_ptrs.push(std::ptr::null());
        let mut envp_ptrs: Vec<*const libc::c_char> = envp.iter().map(|e| e.as_ptr()).collect();
        envp_ptrs.push(std::ptr::null());
        let trapped: Vec<i64> = syscalls::TRAPPED
            .iter()
            .filter_map(|name| syscalls::number(name))
            .collect();
        let failure = format!("hmz: cannot launch {}: ", launch.program.display());
        let walls = self.options.walls.as_ref();
        let sockets = walls.is_some_and(|w| w.sockets);

        let pair = if sockets {
            // Orphaned descendants come here, so a daemon that forked twice is still one this
            // process may take a descriptor of, as Yama asks.
            // SAFETY: prctl with integer arguments.
            if unsafe { libc::prctl(libc::PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) } != 0 {
                return Err(io::Error::last_os_error());
            }
            let (ours, theirs) = nix::sys::socket::socketpair(
                nix::sys::socket::AddressFamily::Unix,
                nix::sys::socket::SockType::Stream,
                None,
                nix::sys::socket::SockFlag::SOCK_CLOEXEC,
            )
            .map_err(io::Error::from)?;
            Some((ours, theirs))
        } else {
            None
        };

        // SAFETY: the child only runs `child` below and then execs or exits.
        let pid = unsafe { libc::fork() };
        if pid < 0 {
            return Err(io::Error::last_os_error());
        }
        if pid == 0 {
            let theirs = pair.map(|(_, theirs)| theirs);
            let error = child(
                &cwd, walls, theirs, &trapped, &program, &argv_ptrs, &envp_ptrs,
            );
            let message = format!("{failure}{error}\n");
            // SAFETY: writing a buffer and leaving without running the parent's code again.
            unsafe {
                libc::write(2, message.as_ptr().cast(), message.len());
                libc::_exit(127);
            }
        }
        if let Some((ours, theirs)) = pair {
            drop(theirs);
            // Nothing where the child failed before it could hand it up: it exits rather than
            // stops, which the initial stop says.
            self.listener = receive_fd(&ours);
        }
        Ok(pid)
    }

    // -------------------------------------------------------------- the loop

    fn serve(&mut self) {
        while self.tracees.contains_key(&self.root) {
            self.drain_completions();
            if self.reap_one() {
                continue;
            }
            self.wait_for_events();
        }
    }

    /// Sleeps until a child changes state or remote work finishes; relays pending signals on
    /// an idle tick.
    fn wait_for_events(&mut self) {
        let mut fds = [
            libc::pollfd {
                fd: self.signals.0.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: self.wake.0.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
        ];
        // SAFETY: polling two valid descriptors.
        let ready = unsafe { libc::poll(fds.as_mut_ptr(), fds.len() as libc::nfds_t, IDLE_MS) };
        if ready < 0 {
            return; // interrupted: the loop asks again
        }
        for fd in &fds {
            if fd.revents != 0 {
                drain(fd.fd);
            }
        }
        if ready == 0 {
            self.relay_pending_signals();
        }
    }

    fn reap_one(&mut self) -> bool {
        match wait_raw(-1, libc::WNOHANG) {
            Err(_) => {
                self.tracees.clear();
                false
            }
            Ok((0, _)) => false,
            Ok((pid, status)) => {
                self.on_status(pid, status);
                true
            }
        }
    }

    fn on_status(&mut self, pid: i32, status: i32) {
        let stop = classify(status);
        if let Stop::Died(code) = stop {
            // Dropping its proxy abandons the command it stood in for.
            self.tracees.remove(&pid);
            if pid == self.root {
                self.status = code;
                tracing::debug!("agent exited with status {code}");
            }
            return;
        }
        // A new child may report before its parent's fork event: adopted either way, its
        // first stop (the attach SIGSTOP) suppressed.
        let tracee = self
            .tracees
            .entry(pid)
            .or_insert_with(|| Tracee::new(false));
        if !tracee.attached {
            tracee.attached = true;
            tolerate(
                "setoptions",
                pid,
                ptrace::set_cog_options(Pid::from_raw(pid)),
            );
            tolerate("cont", pid, restart(false, Pid::from_raw(pid), 0));
            return;
        }
        match stop {
            Stop::Event(libc::PTRACE_EVENT_SECCOMP) => self.on_seccomp(pid),
            Stop::Event(
                libc::PTRACE_EVENT_FORK | libc::PTRACE_EVENT_VFORK | libc::PTRACE_EVENT_CLONE,
            ) => {
                self.adopt_child(pid);
                self.resume(pid, 0);
            }
            Stop::Event(libc::PTRACE_EVENT_EXEC) => {
                if pid == self.root && self.launching {
                    // Read off the image it now is: once it is the agent it stays so.
                    self.launching = procfs::exe_name(Pid::from_raw(pid))
                        .is_ok_and(|name| LAUNCHERS.contains(&name.as_str()));
                }
                self.resume(pid, 0);
            }
            Stop::Event(_) | Stop::Trap => self.resume(pid, 0),
            Stop::Syscall => self.finish_cancelled_syscall(pid),
            Stop::Signal(signal) => self.resume(pid, signal),
            Stop::Died(_) => unreachable!(),
        }
    }

    /// Restarts a tracee, delivering `signal`. One with a cancelled syscall whose exit stop has
    /// not been seen yet is restarted to its next syscall stop, so that a signal-delivery stop
    /// arriving in between does not lose the stop the errno is planted at (where the Python
    /// resumed with `PTRACE_CONT`, and the call returned `-ENOSYS`).
    fn resume(&self, pid: i32, signal: i32) {
        let pending = self
            .tracees
            .get(&pid)
            .is_some_and(|t| t.pending_errno.is_some());
        tolerate("resume", pid, restart(pending, Pid::from_raw(pid), signal));
    }

    fn adopt_child(&mut self, parent: i32) {
        if let Ok(child) = nix::sys::ptrace::getevent(Pid::from_raw(parent)) {
            self.tracees
                .entry(child as i32)
                .or_insert_with(|| Tracee::new(false));
        }
    }

    // --------------------------------------------------------- syscall stops

    fn on_seccomp(&mut self, pid: i32) {
        let target = Pid::from_raw(pid);
        let Ok(mut regs) = ptrace::getregs(target) else {
            return;
        };
        if let Some(tracee) = self.tracees.get_mut(&pid) {
            // A seccomp stop is a new syscall: whatever was pending is stale.
            tracee.pending_errno = None;
        }
        let Some(name) = syscalls::name(regs.syscall()) else {
            tolerate("cont", pid, restart(false, target, 0));
            return;
        };
        let mut args = [0u64; 6];
        for (i, arg) in args.iter_mut().enumerate() {
            *arg = regs.arg(i);
        }
        let mut call = Call::new(name, args, regs.sp());
        let memory = LiveMemory { pid: target };
        let outcome = {
            let session = LiveSession {
                router: &self.router,
                shadow: &self.shadow,
                client: &self.client,
                net: self.net.as_ref(),
                writes: self.options.writes,
            };
            self.dispatcher.dispatch(&memory, &session, &mut call)
        };
        let verdict = match outcome {
            Outcome::Verdict(verdict) => verdict,
            Outcome::Exec(ask) => {
                let count = self.tracees.get_mut(&pid).map_or(1, |t| {
                    t.exec_count += 1;
                    t.exec_count
                });
                match (ask.named, ask.resolved) {
                    (Some(named), Some(resolved)) => {
                        if self.is_agent_launch(pid, count, &resolved) {
                            tracing::debug!("pid {pid}: running {resolved} on this machine");
                            if resolved != named {
                                // Run from the name it was given, which here is the mirror's.
                                plant(&memory, &mut call, 0, ask.path_arg, &resolved);
                            }
                            Verdict::Allow
                        } else {
                            self.begin_remote_exec(pid, &regs, &resolved, ask.argv, ask.envp)
                        }
                    }
                    _ => Verdict::Allow,
                }
            }
        };
        match verdict {
            Verdict::Stall => {}
            Verdict::Fail(errno) => {
                tracing::debug!("pid {pid}: {name} -> errno {errno}");
                self.cancel_syscall(pid, regs, errno);
            }
            Verdict::Allow => {
                if call.changed {
                    for (i, arg) in call.args.iter().enumerate() {
                        regs.set_arg(i, *arg);
                    }
                    tolerate("setregs", pid, ptrace::setregs(target, &regs));
                }
                tolerate("cont", pid, restart(false, target, 0));
            }
        }
    }

    /// Skips the syscall (number -1) and plants the errno on the way out: the kernel writes
    /// the result register of a skipped call, so only its exit stop can carry another.
    fn cancel_syscall(&mut self, pid: i32, mut regs: Regs, errno: i32) {
        regs.set_syscall(-1);
        let target = Pid::from_raw(pid);
        let done = ptrace::setregs(target, &regs).and_then(|()| restart(true, target, 0));
        if let Some(tracee) = self.tracees.get_mut(&pid) {
            tracee.pending_errno = done.is_ok().then_some(errno);
        }
    }

    fn finish_cancelled_syscall(&mut self, pid: i32) {
        let target = Pid::from_raw(pid);
        let Some(errno) = self
            .tracees
            .get_mut(&pid)
            .and_then(|t| t.pending_errno.take())
        else {
            tolerate("cont", pid, restart(false, target, 0));
            return;
        };
        if let Ok(Some(SyscallStop::Entry)) = ptrace::syscall_stop(target) {
            // Not the exit stop it is waiting for: keep waiting.
            if let Some(tracee) = self.tracees.get_mut(&pid) {
                tracee.pending_errno = Some(errno);
            }
            tolerate("syscall", pid, restart(true, target, 0));
            return;
        }
        let planted = ptrace::getregs(target).and_then(|mut regs| {
            regs.set_result(-i64::from(errno));
            ptrace::setregs(target, &regs)
        });
        tolerate("setregs", pid, planted);
        tolerate("cont", pid, restart(false, target, 0));
    }

    // ---------------------------------------------------------- exec bridge

    /// Whether a program belongs to this machine rather than the target: the agent, its
    /// runtime, what its launcher runs on the way to starting it, and what it execs into.
    fn is_agent_launch(&mut self, pid: i32, exec_count: u32, program: &str) -> bool {
        if pid == self.root {
            if exec_count == 1 {
                self.launching = script(Path::new(&to_os(program)));
                return true;
            }
            return self.launching || self.router.runs_locally(program);
        }
        if self.launching
            && launched(pid, self.root, parent_of, |p| {
                self.tracees.get(&p).map(|t| t.exec_count)
            })
        {
            return true;
        }
        self.router.runs_locally(program)
    }

    /// One of the tracee's standard descriptors, or `/dev/null` where it cannot be borrowed.
    fn steal(&self, pid: Pid, fd: i32) -> io::Result<(OwnedFd, bool)> {
        match procfs::steal_fd(pid, fd) {
            Ok(stolen) => Ok((stolen, true)),
            Err(error) => {
                tracing::warn!("could not borrow fd {fd} from pid {pid}: {error}");
                let null = std::fs::OpenOptions::new()
                    .read(fd == 0)
                    .write(fd != 0)
                    .open("/dev/null")?;
                Ok((null.into(), false))
            }
        }
    }

    /// Whether the command is given the stand-in's stdin.
    fn borrow_stdin(&self, stolen: &OwnedFd) -> bool {
        use nix::sys::stat::fstat;
        let (Ok(given), Ok(own)) = (fstat(stolen), fstat(std::io::stdin())) else {
            return true;
        };
        let Ok(agent) = procfs::exe_name(Pid::from_raw(self.root)) else {
            return true;
        };
        let tty = nix::unistd::isatty(stolen).unwrap_or(false);
        borrows_stdin(
            (given.st_dev, given.st_ino) == (own.st_dev, own.st_ino),
            tty,
            SHELLS.contains(&agent.as_str()),
        )
    }

    /// Runs a command on the target in place of this `execve`, and parks the process.
    fn begin_remote_exec(
        &mut self,
        pid: i32,
        regs: &Regs,
        program: &str,
        argv_addr: u64,
        envp_addr: u64,
    ) -> Verdict {
        let target = Pid::from_raw(pid);
        let strings = |addr: u64| -> io::Result<Vec<OsString>> {
            if addr == 0 {
                Ok(Vec::new())
            } else {
                procfs::read_strings(target, addr)
            }
        };
        let (argv, envp) = match (strings(argv_addr), strings(envp_addr)) {
            (Ok(argv), Ok(envp)) => (argv, envp),
            (Err(error), _) | (_, Err(error)) => {
                return match error.raw_os_error() {
                    Some(libc::ESRCH) => Verdict::Allow,
                    errno => Verdict::fails(errno.unwrap_or(libc::EIO)),
                };
            }
        };
        if let Err(error) = self.shadow.flush() {
            tracing::warn!("could not push local changes before exec: {error}");
        }
        let stdio = (|| -> io::Result<_> {
            let (stdin, borrowed) = self.steal(target, 0)?;
            let borrow = borrowed && self.borrow_stdin(&stdin);
            Ok((
                [stdin, self.steal(target, 1)?.0, self.steal(target, 2)?.0],
                borrow,
            ))
        })();
        let (fds, borrow_stdin) = match stdio {
            Ok(stdio) => stdio,
            Err(error) => return Verdict::fails(error.raw_os_error().unwrap_or(libc::EIO)),
        };
        let cwd = procfs::cwd(target).unwrap_or_else(|_| from_os(self.launch.cwd.as_os_str()));
        let cwd = self.virtual_of(&cwd);
        let rewrite = |text: &OsStr| to_os(&self.router.rewrite(&from_os(text)));
        let mut argv: Vec<OsString> = argv.iter().map(|a| rewrite(a)).collect();
        if argv.is_empty() {
            argv.push(rewrite(&to_os(program)));
        }
        let env = environment(&envp, &self.options.private)
            .into_iter()
            .map(|(name, value)| (name, rewrite(&value)))
            .collect();
        let remote_program = to_os(&self.router.rewrite(&self.virtual_of(program)));
        tracing::debug!(
            "pid {pid}: running {:?} on the target (cwd {cwd})",
            argv.first()
        );
        let request = ExecRequest {
            argv,
            program: Some(remote_program),
            cwd,
            env,
            fence: self.options.fence.clone(),
        };
        let proxy = ExecProxy::start(
            self.client.clone(),
            target,
            request,
            fds,
            borrow_stdin,
            self.done.clone(),
            self.wake.1.as_raw_fd(),
        );
        let proxy = match proxy {
            Ok(proxy) => proxy,
            Err(error) => return Verdict::fails(error.raw_os_error().unwrap_or(libc::EIO)),
        };
        let (parked, died) = standin::park_reporting(target, regs);
        if let Err(error) = &parked {
            // Unplanted, it waits at its execve and is released from there; lost after the
            // exec, it was killed, and its death abandons the command.
            tracing::debug!("pid {pid}: not parked: {error}");
        }
        if let Some(tracee) = self.tracees.get_mut(&pid) {
            tracee.proxy = Some(proxy);
            tracee.relayed = 0;
            tracee.parked = parked.is_ok();
        }
        if let Some(status) = died {
            // Parking's own wait took its death, which the loop will never be told of.
            self.on_status(pid, status);
        }
        Verdict::Stall
    }

    /// The path the target knows `path` by, or `path` where it is this machine's.
    fn virtual_of(&self, path: &str) -> String {
        match self.router.place(path) {
            Place::Mirror { virtual_path, .. } => virtual_path,
            Place::Local => path.to_owned(),
        }
    }

    fn drain_completions(&mut self) {
        while let Ok(done) = self.completions.try_recv() {
            self.release_stalled(done);
        }
    }

    /// Turns the stalled `execve` into an exit carrying the remote status.
    fn release_stalled(&mut self, done: Completion) {
        let pid = done.pid.as_raw();
        let Some(tracee) = self.tracees.get_mut(&pid) else {
            return;
        };
        if tracee.proxy.take().is_none() {
            return;
        }
        let parked = tracee.parked;
        // Anything the command did on the target invalidates the mirror.
        self.shadow.invalidate();
        let (status, signal) = release_status(done.ending);
        // Only a parked stand-in can be handed a signal; one left at its execve exits.
        let signal = signal.filter(|_| parked);
        if let Err(error) = standin::release(done.pid, status, signal) {
            tracing::debug!("pid {pid} vanished before it could be released: {error}");
        }
    }

    /// Forwards the cancel signals queued against parked stand-ins, each once: a process
    /// stopped by ptrace never dequeues them, so its pending mask is read instead.
    fn relay_pending_signals(&mut self) {
        for (pid, tracee) in &mut self.tracees {
            let Some(proxy) = &tracee.proxy else {
                continue;
            };
            let pending = procfs::pending_signals(Pid::from_raw(*pid)).unwrap_or(0);
            for signal in CANCEL_SIGNALS {
                let bit = 1u64 << (signal - 1);
                if pending & bit != 0 && tracee.relayed & bit == 0 {
                    tracee.relayed |= bit;
                    proxy.signal(signal);
                }
            }
        }
    }
}

/// The forked child: everything up to `execve`, returning only on failure.
fn child(
    cwd: &CString,
    walls: Option<&Walls>,
    theirs: Option<OwnedFd>,
    trapped: &[i64],
    program: &CString,
    argv: &[*const libc::c_char],
    envp: &[*const libc::c_char],
) -> io::Error {
    let steps = || -> io::Result<()> {
        // SAFETY: plain syscalls on valid pointers.
        unsafe {
            if libc::chdir(cwd.as_ptr()) != 0 {
                return Err(io::Error::last_os_error());
            }
            if libc::ptrace(
                libc::PTRACE_TRACEME,
                0,
                std::ptr::null_mut::<libc::c_void>(),
                std::ptr::null_mut::<libc::c_void>(),
            ) < 0
            {
                return Err(io::Error::last_os_error());
            }
        }
        if let Some(walls) = walls {
            if walls.sockets {
                crate::fence::netfilter::install_socket_filter()?;
                let listener = crate::fence::netfilter::install_listener()?;
                let theirs =
                    theirs.ok_or_else(|| io::Error::other("nobody to answer its binds"))?;
                send_fd(&theirs, &listener)?;
                // Closed before the agent runs, not merely on exec: an agent holding the
                // listener could answer its own calls.
                drop(listener);
                drop(theirs);
            }
            walls.ruleset.restrict_self()?;
        }
        crate::sys::trap::install(trapped)?;
        // SAFETY: stopping ourselves for the tracer, then becoming the agent.
        unsafe {
            libc::kill(libc::getpid(), libc::SIGSTOP);
            libc::execve(program.as_ptr(), argv.as_ptr(), envp.as_ptr());
        }
        Err(io::Error::last_os_error())
    };
    match steps() {
        Ok(()) => io::Error::other("execve returned"),
        Err(error) => error,
    }
}

/// Hands `fd` over `socket` (`SCM_RIGHTS`).
fn send_fd(socket: &OwnedFd, fd: &OwnedFd) -> io::Result<()> {
    use nix::sys::socket::{ControlMessage, MsgFlags, sendmsg};
    let fds = [fd.as_raw_fd()];
    let message = [IoSlice::new(b"!")];
    sendmsg::<()>(
        socket.as_raw_fd(),
        &message,
        &[ControlMessage::ScmRights(&fds)],
        MsgFlags::empty(),
        None,
    )
    .map_err(io::Error::from)?;
    Ok(())
}

/// The descriptor handed over `socket`, if one came.
fn receive_fd(socket: &OwnedFd) -> Option<OwnedFd> {
    use nix::sys::socket::{ControlMessageOwned, MsgFlags, recvmsg};
    let mut byte = [0u8; 1];
    let mut buffer = [IoSliceMut::new(&mut byte)];
    let mut space = nix::cmsg_space!([RawFd; 1]);
    let message = loop {
        match recvmsg::<()>(
            socket.as_raw_fd(),
            &mut buffer,
            Some(&mut space),
            MsgFlags::MSG_CMSG_CLOEXEC,
        ) {
            Err(nix::errno::Errno::EINTR) => continue,
            other => break other.ok()?,
        }
    };
    let mut cmsgs = message.cmsgs().ok()?;
    cmsgs.find_map(|cmsg| match cmsg {
        // SAFETY: the kernel just installed this descriptor for us.
        ControlMessageOwned::ScmRights(fds) => {
            fds.first().map(|fd| unsafe { OwnedFd::from_raw_fd(*fd) })
        }
        _ => None,
    })
}

/// The real tracee.
struct LiveMemory {
    pid: Pid,
}

impl Memory for LiveMemory {
    fn read_cstring(&self, addr: u64) -> io::Result<OsString> {
        procfs::read_cstring(self.pid, addr)
    }
    fn read_mem(&self, addr: u64, len: usize) -> io::Result<Vec<u8>> {
        procfs::read_mem(self.pid, addr, len)
    }
    fn write_mem(&self, addr: u64, data: &[u8]) -> io::Result<()> {
        procfs::write_mem(self.pid, addr, data)
    }
    fn resolve_magic(&self, path: &str) -> io::Result<String> {
        procfs::resolve_magic(self.pid, path)
    }
    fn cwd(&self) -> io::Result<String> {
        // A working directory that cannot be read is a tracee that has gone.
        procfs::cwd(self.pid).map_err(|error| match error.kind() {
            io::ErrorKind::NotFound => io::Error::from_raw_os_error(libc::ESRCH),
            _ => error,
        })
    }
    fn fd_path(&self, fd: i32) -> io::Result<String> {
        procfs::fd_path(self.pid, fd)
    }
}

/// The real session.
struct LiveSession<'a> {
    router: &'a Router,
    shadow: &'a ShadowTree,
    client: &'a RemoteClient,
    net: Option<&'a NetProxy>,
    writes: bool,
}

fn local(path: &str) -> PathBuf {
    PathBuf::from(to_os(path))
}

impl Session for LiveSession<'_> {
    fn path_call(&self, name: &str) -> Option<&'static PathCall> {
        pathcalls::find(name)
    }
    fn settles(&self) -> bool {
        // Python asks `router.redirects or router.settles`, and the router declared for this
        // port says nothing of its redirects. Until it does, every path call is read: a
        // redirect skipped would have the agent read the credentials of whoever is at this
        // machine, which is worse than reading a path twice.
        true
    }
    fn canonical(&self, path: &str) -> String {
        self.router.canonical(path)
    }
    fn swap(&self, path: &str) -> Option<String> {
        self.router.swap(path)
    }
    fn remote(&self, path: &str) -> Option<String> {
        match self.router.place(path) {
            Place::Mirror { virtual_path, .. } => Some(virtual_path),
            Place::Local => None,
        }
    }
    fn make_parents(&self, path: &str) -> bool {
        match policy::parents(path) {
            Ok(()) => true,
            Err(error) => {
                tracing::debug!("could not make the directory {path} is answered in: {error}");
                false
            }
        }
    }
    fn writes(&self) -> bool {
        self.writes
    }
    fn ensure_path(&self, path: &str) -> Result<(), RemoteError> {
        self.shadow.ensure_path(&local(path))
    }
    fn ensure_directory(&self, path: &str) -> Result<(), RemoteError> {
        self.shadow.ensure_directory(&local(path))
    }
    fn ensure_content(&self, path: &str) -> Result<(), RemoteError> {
        self.shadow.ensure_content(&local(path))
    }
    fn note_write(&self, path: &str) {
        self.shadow.note_write(&local(path));
    }
    fn note_removed(&self, path: &str) {
        self.shadow.note_removed(&local(path));
    }
    fn note_renamed(&self, from: &str, to: &str) {
        self.shadow.note_renamed(&local(from), &local(to));
    }
    fn flush(&self) -> Result<(), RemoteError> {
        self.shadow.flush()
    }
    fn call(&self, op: Op, request: Meta) -> Result<Meta, RemoteError> {
        self.client.call(op, request)
    }
    fn redirect(
        &self,
        dest: std::net::SocketAddr,
    ) -> Option<io::Result<Option<std::net::SocketAddr>>> {
        self.net.map(|net| net.redirect(dest))
    }
    fn now_ns(&self) -> i64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_or(0, |d| d.as_nanos() as i64)
    }
}

#[cfg(test)]
mod tests {
    use std::io::Write;

    use super::*;

    fn stopped(signal: i32, event: i32) -> i32 {
        (event << 16) | (signal << 8) | 0x7f
    }

    #[test]
    fn statuses_are_read_as_the_loop_acts_on_them() {
        assert_eq!(classify(3 << 8), Stop::Died(3));
        assert_eq!(classify(libc::SIGKILL), Stop::Died(128 + libc::SIGKILL));
        assert_eq!(
            classify(stopped(libc::SIGTRAP, libc::PTRACE_EVENT_SECCOMP)),
            Stop::Event(libc::PTRACE_EVENT_SECCOMP)
        );
        assert_eq!(classify(stopped(libc::SIGTRAP | 0x80, 0)), Stop::Syscall);
        assert_eq!(classify(stopped(libc::SIGTRAP, 0)), Stop::Trap);
        assert_eq!(
            classify(stopped(libc::SIGTERM, 0)),
            Stop::Signal(libc::SIGTERM)
        );
        // A real-time signal is a signal like any other here.
        assert_eq!(classify(stopped(40, 0)), Stop::Signal(40));
    }

    #[test]
    fn a_remote_ending_is_a_status_or_a_signal() {
        assert_eq!(release_status(Ending::Exited(3)), (3, None));
        assert_eq!(release_status(Ending::Failed(127)), (127, None));
        assert_eq!(
            release_status(Ending::Signalled(libc::SIGTERM)),
            (128 + libc::SIGTERM, Some(libc::SIGTERM))
        );
        // A signal that does not kill by default is flattened into a status.
        assert_eq!(
            release_status(Ending::Signalled(libc::SIGUSR1)),
            (128 + libc::SIGUSR1, None)
        );
    }

    #[test]
    fn the_agents_own_stdin_is_not_lent_to_a_probe() {
        assert!(!borrows_stdin(true, false, false));
        assert!(borrows_stdin(false, false, false));
        assert!(borrows_stdin(true, true, false));
        assert!(borrows_stdin(true, false, true));
    }

    #[test]
    fn a_script_run_by_a_shell_or_env_is_a_launcher() {
        let dir = tempfile::tempdir().unwrap();
        let write = |name: &str, body: &[u8]| {
            let path = dir.path().join(name);
            std::fs::File::create(&path)
                .unwrap()
                .write_all(body)
                .unwrap();
            path
        };
        assert!(script(&write("a", b"#!/bin/sh\nexec node x\n")));
        assert!(script(&write("b", b"#! /usr/bin/env node\n")));
        assert!(script(&write("c", b"#!/bin/bash -e\n")));
        assert!(!script(&write("d", b"#!/usr/bin/node\n")));
        assert!(!script(&write("e", b"\x7fELF....")));
        assert!(!script(&write("f", b"")));
        assert!(!script(&dir.path().join("missing")));
    }

    #[test]
    fn a_launchers_helpers_are_found_up_its_subshells() {
        // 10 is the root; 11 a subshell of it running nothing; 12 forked from 11; 13 from
        // 14, which ran a program.
        let parent = |pid| match pid {
            11 => 10,
            12 => 11,
            13 => 14,
            14 => 10,
            _ => 1,
        };
        let execs = |pid| match pid {
            11 => Some(0),
            14 => Some(1),
            _ => None,
        };
        assert!(launched(11, 10, parent, execs));
        assert!(launched(12, 10, parent, execs));
        assert!(!launched(13, 10, parent, execs));
        assert!(!launched(99, 10, parent, execs));
        // Never walked past its depth.
        assert!(!launched(50, 0, |p| p + 1, |_| Some(0)));
    }

    #[test]
    fn an_environment_drops_what_is_private_and_keeps_the_last_word() {
        let entries: Vec<OsString> = ["A=1", "KEY=secret", "B=2", "A=3", "junk", "C=x=y"]
            .into_iter()
            .map(OsString::from)
            .collect();
        let env = environment(&entries, &["KEY".into()]);
        let said: Vec<(String, String)> = env
            .into_iter()
            .map(|(n, v)| (n.into_string().unwrap(), v.into_string().unwrap()))
            .collect();
        assert_eq!(
            said,
            [
                ("A".into(), "3".into()),
                ("B".into(), "2".into()),
                ("C".into(), "x=y".into())
            ]
        );
    }

    #[test]
    fn the_parent_of_this_process_is_read_from_proc() {
        assert_eq!(
            parent_of(std::process::id() as i32),
            nix::unistd::getppid().as_raw()
        );
        assert_eq!(parent_of(i32::MAX), 0);
    }

    #[test]
    fn a_descriptor_crosses_a_socket() {
        let (ours, theirs) = nix::sys::socket::socketpair(
            nix::sys::socket::AddressFamily::Unix,
            nix::sys::socket::SockType::Stream,
            None,
            nix::sys::socket::SockFlag::SOCK_CLOEXEC,
        )
        .unwrap();
        let (read, write) = pipe().unwrap();
        send_fd(&theirs, &write).unwrap();
        drop(write);
        let got = receive_fd(&ours).unwrap();
        nix::unistd::write(&got, b"hi").unwrap();
        let mut buf = [0u8; 2];
        assert_eq!(nix::unistd::read(&read, &mut buf).unwrap(), 2);
        drop(theirs);
        assert!(receive_fd(&ours).is_none());
    }
}

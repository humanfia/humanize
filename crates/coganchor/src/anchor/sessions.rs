//! Commands run for a client. Port of the exec half of `hmz.coganchor.serve.sessions`.
//! [Unit 2]
//!
//! `EXEC {argv, program, cwd, env, tty, winsize, fence}` starts a command in a new session
//! (pipes, or a pty with the window size given), streams its output as `CHUNK`s on `Stdout`
//! and `Stderr` (everything on `Stdout` under a pty), takes `Stdin` chunks and `END`, and
//! closes with one `RSP` of `{exit_code}` or `{signal}` once every output descriptor has
//! reached end of file. No `END` is sent for output. A command asking for a fence runs under
//! `coganchor internal fence` ([`crate::fence::abroad::fenced`]).
//!
//! Unlike `ExecSession`, which starts its process on a thread of its own, [`exec`] starts the
//! process before it returns: a fork and an exec are quick, and an exec that fails is then
//! the `Err` the caller answers with, the child's errno carried back by the standard library's
//! close-on-exec pipe. Everything that can take long (pumping output, feeding input, waiting
//! for the exit) runs on threads of the session's own, so the connection's reader never waits
//! on a command.

use std::collections::HashMap;
use std::ffi::{OsStr, OsString};
use std::fs::File;
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, OwnedFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::process::{CommandExt, ExitStatusExt};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Sender};
use std::sync::{Arc, Condvar, Mutex};
use std::thread;

use serde_json::Value;

use crate::anchor::{ExportTable, Outbox, Sink};
use crate::proto::json::{from_os, to_os};
use crate::proto::{CHUNK_SIZE, Frame, Meta, RemoteError, Stream};

/// Environment variables that describe the *client's* machine and must not leak here, as
/// `HOST_SPECIFIC_ENV` lists them. Everything else the agent set (API keys, `GIT_*`, project
/// variables) passes through, layered on top of this machine's environment.
const HOST_SPECIFIC_ENV: [&str; 20] = [
    "DISPLAY",
    "HOME",
    "HOSTNAME",
    "HOSTTYPE",
    "LOGNAME",
    "MACHTYPE",
    "MAIL",
    "OLDPWD",
    "OSTYPE",
    "PATH",
    "PWD",
    // The login session a macOS client opened, which names a session of that machine's
    // security server and does not exist here.
    "SECURITYSESSIONID",
    "SHELL",
    "SHLVL",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USER",
    "WAYLAND_DISPLAY",
    "_",
];

/// Prefixes of variables that are host-specific or belong to coganchor itself, as
/// `HOST_SPECIFIC_PREFIXES` lists them. `DYLD_` is macOS's `LD_`; `Apple`, `XPC_` and `__CF`
/// are what a macOS client's launchd session puts in the environment, each naming that
/// machine and not this one.
const HOST_SPECIFIC_PREFIXES: [&str; 8] = [
    "Apple",
    "DYLD_",
    "HUMANIZE_",
    "LD_",
    "SSH_",
    "XDG_",
    "XPC_",
    "__CF",
];

/// The `ioctl` claiming a controlling terminal, which the `libc` crate leaves out for Apple
/// targets: `_IO('t', 97)`.
#[cfg(target_os = "macos")]
const TIOCSCTTY: libc::c_ulong = 0x2000_7461;
#[cfg(not(target_os = "macos"))]
const TIOCSCTTY: libc::Ioctl = libc::TIOCSCTTY;

/// Starts the command `request` asks for, as exchange `id`. Errors the request itself makes
/// (no `argv`, no `cwd`) are `EINVAL`; failing to start the program is that errno.
pub fn exec(
    id: u64,
    request: &Meta,
    exports: Arc<ExportTable>,
    outbox: Arc<dyn Outbox>,
) -> Result<Box<dyn Sink>, RemoteError> {
    let request = Request::parse(request)?;
    start(id, request, &*exports, outbox)
}

/// What a command's paths are translated through: the export table, or a stand-in in tests
/// (the table's own translation is another unit's).
trait Place {
    fn resolve(&self, virtual_path: &str) -> Result<PathBuf, RemoteError>;
    fn rewrite(&self, text: &str) -> String;
    fn fenced(
        &self,
        argv: &[OsString],
        program: Option<&OsString>,
        said: &Value,
    ) -> Result<Vec<OsString>, RemoteError>;
}

impl Place for ExportTable {
    fn resolve(&self, virtual_path: &str) -> Result<PathBuf, RemoteError> {
        ExportTable::resolve(self, virtual_path)
    }

    fn rewrite(&self, text: &str) -> String {
        ExportTable::rewrite(self, text)
    }

    fn fenced(
        &self,
        argv: &[OsString],
        program: Option<&OsString>,
        said: &Value,
    ) -> Result<Vec<OsString>, RemoteError> {
        crate::fence::abroad::fenced(argv, program, said, self)
    }
}

/// An `EXEC` request's fields, checked.
struct Request {
    argv: Vec<String>,
    program: Option<String>,
    cwd: String,
    env: Vec<(String, String)>,
    tty: bool,
    winsize: Option<(u16, u16)>,
    fence: Option<Value>,
}

impl Request {
    fn parse(meta: &Meta) -> Result<Request, RemoteError> {
        let invalid = |what: &str| RemoteError::new(libc::EINVAL, what.to_owned());
        let argv = match meta.get("argv") {
            Some(Value::Array(items)) => items
                .iter()
                .map(|item| item.as_str().map(str::to_owned))
                .collect::<Option<Vec<_>>>()
                .ok_or_else(|| invalid("argv must be a list of strings"))?,
            _ => return Err(invalid("argv must be a list of strings")),
        };
        if argv.is_empty() {
            return Err(invalid("argv must not be empty"));
        }
        // An empty program is no program, as `ExecSession` takes it.
        let program = match meta.get("program") {
            None | Some(Value::Null) => None,
            Some(Value::String(said)) if said.is_empty() => None,
            Some(Value::String(said)) => Some(said.clone()),
            Some(_) => return Err(invalid("program must be a string")),
        };
        let cwd = meta
            .get("cwd")
            .and_then(Value::as_str)
            .ok_or_else(|| invalid("cwd must be a string"))?
            .to_owned();
        let env = match meta.get("env") {
            None | Some(Value::Null) => Vec::new(),
            Some(Value::Object(said)) => said
                .iter()
                .map(|(name, value)| match value.as_str() {
                    // A name holding `=` would be a second variable's entry, past the lists of
                    // those dropped; Python's `Popen` refuses one too.
                    Some(_) if name.is_empty() || name.contains(['=', '\0']) => {
                        Err(invalid("env names must be names"))
                    }
                    Some(value) => Ok((name.clone(), value.to_owned())),
                    None => Err(invalid("env values must be strings")),
                })
                .collect::<Result<Vec<_>, _>>()?,
            Some(_) => return Err(invalid("env must be an object")),
        };
        let tty = match meta.get("tty") {
            None | Some(Value::Null) => false,
            Some(Value::Bool(said)) => *said,
            Some(_) => return Err(invalid("tty must be a boolean")),
        };
        let winsize = match meta.get("winsize") {
            None | Some(Value::Null) => None,
            Some(Value::Array(said)) if said.is_empty() => None,
            Some(Value::Array(said)) => {
                let size = |at: usize| {
                    said.get(at)
                        .and_then(Value::as_u64)
                        .and_then(|n| u16::try_from(n).ok())
                };
                match (said.len(), size(0), size(1)) {
                    (2, Some(rows), Some(cols)) => Some((rows, cols)),
                    _ => return Err(invalid("winsize must be [rows, cols]")),
                }
            }
            Some(_) => return Err(invalid("winsize must be [rows, cols]")),
        };
        let fence = match meta.get("fence") {
            None | Some(Value::Null) => None,
            Some(said) => Some(said.clone()),
        };
        Ok(Request {
            argv,
            program,
            cwd,
            env,
            tty,
            winsize,
            fence,
        })
    }
}

/// Starts the command, then the threads that serve it.
fn start(
    id: u64,
    request: Request,
    place: &dyn Place,
    outbox: Arc<dyn Outbox>,
) -> Result<Box<dyn Sink>, RemoteError> {
    let cwd = match place.resolve(&request.cwd) {
        Ok(real) => real,
        // A command launched from outside the workspace must still run; it runs in this
        // machine's home directory instead.
        Err(error) if error.errno == libc::EACCES => home(),
        Err(error) => return Err(error),
    };
    let mut argv: Vec<OsString> = request
        .argv
        .iter()
        .map(|item| to_os(&place.rewrite(item)))
        .collect();
    let mut program = request.program.as_deref().map(|p| to_os(&place.rewrite(p)));
    let client_env = request
        .env
        .iter()
        .map(|(name, value)| (name.as_str(), to_os(&place.rewrite(value))));
    let env = compose_env(client_env, cwd.as_os_str(), request.tty);
    if let Some(rules) = &request.fence {
        argv = place.fenced(&argv, program.as_ref(), rules)?;
        program = None;
        if argv.is_empty() {
            return Err(RemoteError::new(libc::EIO, "the fence gave no command"));
        }
    }

    // Looked up before the fork, as `sysconf` is not safe to call between it and the exec.
    // SAFETY: sysconf takes no pointers.
    let max_fd = unsafe { libc::sysconf(libc::_SC_OPEN_MAX) }.clamp(3, 1 << 20) as libc::c_int;
    let pty = if request.tty {
        let winsize = request.winsize.map(|(rows, cols)| nix::pty::Winsize {
            ws_row: rows,
            ws_col: cols,
            ws_xpixel: 0,
            ws_ypixel: 0,
        });
        let pty = nix::pty::openpty(winsize.as_ref(), None).map_err(nix_error)?;
        // Close-on-exec, as `os.openpty` makes them: a copy of the slave anything else here
        // starts would keep the master from ever reaching its end.
        for fd in [&pty.master, &pty.slave] {
            nix::fcntl::fcntl(
                fd,
                nix::fcntl::FcntlArg::F_SETFD(nix::fcntl::FdFlag::FD_CLOEXEC),
            )
            .map_err(nix_error)?;
        }
        Some(pty)
    } else {
        None
    };
    let (mut child, master) = match pty {
        Some(pty) => {
            // The slave goes to the child; the parent's copies close with `spawn`'s command.
            let child = spawn(
                &argv,
                program.as_deref(),
                &cwd,
                &env,
                Some(&pty.slave),
                max_fd,
            )?;
            drop(pty.slave);
            (child, Some(File::from(pty.master)))
        }
        None => (
            spawn(&argv, program.as_deref(), &cwd, &env, None, max_fd)?,
            None,
        ),
    };

    let pid = child.id() as libc::pid_t;
    let shared = Arc::new(Shared {
        reaped: Mutex::new(false),
        done: AtomicBool::new(false),
        held: Mutex::new(false),
        let_go: Condvar::new(),
    });
    let (stdin, inbox) = mpsc::channel::<Option<Vec<u8>>>();

    // What the client's stdin goes to, what output comes from, and what a `RESIZE` sets the
    // window of: a copy of the master, which neither ends the output nor holds it open, since
    // that ends with the last copy of the slave.
    let mut terminal = None;
    let (input, outputs): (Option<Input>, Vec<(File, Stream)>) = match master {
        Some(master) => {
            let writer = master.try_clone().map_err(|e| abandon(&mut child, &e))?;
            terminal = Some(OwnedFd::from(
                master.try_clone().map_err(|e| abandon(&mut child, &e))?,
            ));
            (Some(Box::new(writer)), vec![(master, Stream::Stdout)])
        }
        None => {
            let input = child.stdin.take().map(|pipe| Box::new(pipe) as Input);
            let mut outputs = Vec::new();
            if let Some(out) = child.stdout.take() {
                outputs.push((File::from(OwnedFd::from(out)), Stream::Stdout));
            }
            if let Some(err) = child.stderr.take() {
                outputs.push((File::from(OwnedFd::from(err)), Stream::Stderr));
            }
            (input, outputs)
        }
    };

    if let Err(error) = thread::Builder::new()
        .name(format!("stdin-{id}"))
        .spawn(move || feed_stdin(input, inbox))
    {
        return Err(abandon(&mut child, &error));
    }
    let pumps = outputs
        .into_iter()
        .map(|(file, stream)| {
            let outbox = Arc::clone(&outbox);
            let shared = Arc::clone(&shared);
            thread::Builder::new()
                .name(format!("pump-{id}"))
                .spawn(move || pump(id, file, stream, &*outbox, &shared))
        })
        .collect::<io::Result<Vec<_>>>();
    let pumps = match pumps {
        Ok(pumps) => pumps,
        Err(error) => return Err(abandon(&mut child, &error)),
    };
    // The waiting thread owns the child; should it not start, the child comes back to be
    // abandoned.
    let (keep, back) = mpsc::channel::<Child>();
    let _ = keep.send(child);
    let waiter = {
        let shared = Arc::clone(&shared);
        let stdin = stdin.clone();
        thread::Builder::new()
            .name(format!("session-{id}"))
            .spawn(move || {
                let Ok(mut child) = back.recv() else { return };
                for pump in pumps {
                    let _ = pump.join();
                }
                let _ = stdin.send(None);
                let reply = finish(&mut child, &shared);
                let _ = outbox.send(reply.map_or_else(
                    |error| Frame::error(id, &error),
                    |meta| Frame::reply(id, meta, Vec::new()),
                ));
                shared.done.store(true, Ordering::SeqCst);
            })
    };
    if let Err(error) = waiter {
        // SAFETY: killpg and waitpid take no pointers but the status, which is null.
        unsafe {
            libc::killpg(pid, libc::SIGKILL);
            libc::waitpid(pid, std::ptr::null_mut(), 0);
        }
        return Err(RemoteError::from_io(&error, None));
    }

    Ok(Box::new(ExecSink {
        pid,
        stdin,
        shared,
        terminal,
    }))
}

/// Kills the command's group and reaps it, when what serves it could not be started: the
/// `EXEC` fails, and nothing is left running unwatched.
fn abandon(child: &mut Child, error: &io::Error) -> RemoteError {
    // SAFETY: killpg takes no pointers.
    unsafe { libc::killpg(child.id() as libc::pid_t, libc::SIGKILL) };
    let _ = child.wait();
    RemoteError::from_io(error, None)
}

/// The environment of a command: this machine's (so `PATH`, `HOME` and friends describe this
/// machine), overlaid with the variables the client chose, less the ones naming the client's
/// machine. Port of `compose_env`.
fn compose_env<'a>(
    client: impl Iterator<Item = (&'a str, OsString)>,
    cwd: &OsStr,
    tty: bool,
) -> HashMap<OsString, OsString> {
    let mut env: HashMap<OsString, OsString> = std::env::vars_os().collect();
    for (name, value) in client {
        if HOST_SPECIFIC_ENV.contains(&name)
            || HOST_SPECIFIC_PREFIXES
                .iter()
                .any(|prefix| name.starts_with(prefix))
        {
            continue;
        }
        env.insert(to_os(name), value);
    }
    env.insert("PWD".into(), cwd.to_owned());
    if tty {
        env.entry("TERM".into())
            .or_insert_with(|| "xterm-256color".into());
    }
    env
}

/// This user's home directory, where a command outside every export runs.
fn home() -> PathBuf {
    if let Some(home) = std::env::var_os("HOME").filter(|home| !home.is_empty()) {
        return home.into();
    }
    nix::unistd::User::from_uid(nix::unistd::getuid())
        .ok()
        .flatten()
        .map_or_else(|| PathBuf::from("/"), |user| user.dir)
}

/// Starts `argv` (or `program`, given as `argv[0]`) in a session of its own, falling back to
/// a `PATH` lookup for agent-local tools, as `ExecSession._spawn` does: agents bundle helpers
/// (ripgrep, for instance) under their own install directory, a path that exists on the
/// client's machine but not here, so a literal path that is missing is retried by its bare
/// name on the child's `PATH`. `argv[0]` stays what the client sent.
fn spawn(
    argv: &[OsString],
    program: Option<&OsStr>,
    cwd: &Path,
    env: &HashMap<OsString, OsString>,
    slave: Option<&OwnedFd>,
    max_fd: libc::c_int,
) -> Result<Child, RemoteError> {
    let mut candidates = vec![program.unwrap_or(&argv[0]).to_owned()];
    if let Some(program) = program {
        let bytes = program.as_bytes();
        if let Some(slash) = bytes.iter().rposition(|&b| b == b'/') {
            candidates.push(OsStr::from_bytes(&bytes[slash + 1..]).to_owned());
        }
    }
    let tty = slave.is_some();
    let mut last = None;
    for executable in candidates {
        let mut command = Command::new(&executable);
        command
            .arg0(&argv[0])
            .args(&argv[1..])
            .current_dir(cwd)
            .env_clear()
            .envs(env);
        match slave {
            Some(slave) => {
                let stdio = || -> Result<Stdio, RemoteError> {
                    Ok(Stdio::from(
                        slave
                            .try_clone()
                            .map_err(|e| RemoteError::from_io(&e, None))?,
                    ))
                };
                command.stdin(stdio()?).stdout(stdio()?).stderr(stdio()?);
            }
            None => {
                command
                    .stdin(Stdio::piped())
                    .stdout(Stdio::piped())
                    .stderr(Stdio::piped());
            }
        }
        // SAFETY: only async-signal-safe calls (setsid, ioctl, fcntl, syscall) run between the
        // fork and the exec.
        unsafe {
            command.pre_exec(move || {
                if libc::setsid() == -1 {
                    return Err(io::Error::last_os_error());
                }
                if tty {
                    // A slave inherited rather than opened does not become the controlling
                    // terminal by itself; it is claimed here, and an error is ignored.
                    libc::ioctl(0, TIOCSCTTY as _, 0);
                }
                close_fds_on_exec(max_fd);
                Ok(())
            });
        }
        match command.spawn() {
            Ok(child) => return Ok(child),
            Err(error)
                if matches!(
                    error.raw_os_error(),
                    Some(libc::ENOENT) | Some(libc::ENOTDIR)
                ) =>
            {
                last = Some(RemoteError::from_io(&error, Some(&from_os(&executable))));
            }
            Err(error) => return Err(RemoteError::from_io(&error, Some(&from_os(&executable)))),
        }
    }
    Err(last.unwrap_or_else(|| RemoteError::new(libc::ENOENT, "no program to run")))
}

/// Marks every descriptor above stderr close-on-exec, in the forked child: `close_fds`. The
/// standard library opens its own descriptors close-on-exec already, but one inherited from
/// elsewhere, or a pty another thread opened a moment ago, may not be.
fn close_fds_on_exec(max_fd: libc::c_int) {
    #[cfg(target_os = "linux")]
    // SAFETY: close_range takes no pointers.
    unsafe {
        if libc::syscall(
            libc::SYS_close_range,
            3 as libc::c_uint,
            libc::c_uint::MAX,
            libc::CLOSE_RANGE_CLOEXEC,
        ) == 0
        {
            return;
        }
    }
    // SAFETY: fcntl takes no pointers.
    unsafe {
        for fd in 3..max_fd {
            let flags = libc::fcntl(fd, libc::F_GETFD);
            if flags >= 0 && flags & libc::FD_CLOEXEC == 0 {
                libc::fcntl(fd, libc::F_SETFD, flags | libc::FD_CLOEXEC);
            }
        }
    }
}

/// Writes the client's stdin to the command until the end of it, then closes the pipe (for
/// a pty, the master's copy this owns).
fn feed_stdin(input: Option<Input>, inbox: mpsc::Receiver<Option<Vec<u8>>>) {
    let Some(mut input) = input else { return };
    while let Ok(Some(data)) = inbox.recv() {
        if input.write_all(&data).is_err() {
            break;
        }
    }
}

/// Streams one output descriptor as `CHUNK`s until its end. A pty master has two ways of
/// saying the child holding the other end is gone, as `_read_stream` explains: Linux fails
/// the read with `EIO`, macOS ends the file. Both end the output. Nothing is read while the
/// client holds the command (`HOLD`), so that what it writes fills its pipe or its terminal
/// and it waits there.
fn pump(id: u64, mut file: File, stream: Stream, outbox: &dyn Outbox, shared: &Shared) {
    let mut buffer = vec![0u8; CHUNK_SIZE];
    loop {
        let held = shared.held.lock().unwrap_or_else(|e| e.into_inner());
        drop(
            shared
                .let_go
                .wait_while(held, |held| *held)
                .unwrap_or_else(|e| e.into_inner()),
        );
        match file.read(&mut buffer) {
            Ok(0) => return,
            Ok(n) => {
                let _ = outbox.send(Frame::chunk(id, stream, buffer[..n].to_vec()));
            }
            Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
            Err(_) => return,
        }
    }
}

/// Waits for the command to exit and reaps it, answering its status. The exit is awaited
/// without reaping first, so that a signal sent meanwhile still reaches a group whose leader's
/// number nothing else can have taken; the reaping then happens under the lock `signal`
/// takes.
fn finish(child: &mut Child, shared: &Shared) -> Result<Meta, RemoteError> {
    let pid = child.id() as libc::id_t;
    loop {
        // SAFETY: `info` is a valid siginfo_t to fill in.
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        let rc =
            unsafe { libc::waitid(libc::P_PID, pid, &mut info, libc::WEXITED | libc::WNOWAIT) };
        if rc == 0 || io::Error::last_os_error().raw_os_error() != Some(libc::EINTR) {
            break;
        }
    }
    let mut reaped = shared.reaped.lock().unwrap_or_else(|e| e.into_inner());
    let status = child.wait();
    *reaped = true;
    drop(reaped);
    let status = status.map_err(|e| RemoteError::from_io(&e, None))?;
    Ok(match (status.code(), status.signal()) {
        (Some(code), _) => crate::meta! {"exit_code" => code},
        (None, Some(signal)) => crate::meta! {"signal" => signal},
        (None, None) => return Err(RemoteError::new(libc::EIO, "no exit status")),
    })
}

/// Where the client's stdin goes: the pipe, or a copy of the pty master.
type Input = Box<dyn Write + Send>;

/// What the session's threads share with its sink.
struct Shared {
    /// Whether the command has been reaped, its number free for another process.
    reaped: Mutex<bool>,
    /// Whether the closing `RSP` (or `ERR`) has been sent.
    done: AtomicBool,
    /// Whether the client holds the command: its output is not read meanwhile.
    held: Mutex<bool>,
    /// Told when the client lets go of it.
    let_go: Condvar,
}

/// A running command, as the connection sees it.
struct ExecSink {
    pid: libc::pid_t,
    stdin: Sender<Option<Vec<u8>>>,
    shared: Arc<Shared>,
    /// The pty master the command runs under, if it runs under one.
    terminal: Option<OwnedFd>,
}

impl Sink for ExecSink {
    fn feed(&mut self, stream: Stream, body: &[u8]) -> Result<(), RemoteError> {
        if stream == Stream::Stdin {
            let _ = self.stdin.send(Some(body.to_vec()));
        }
        Ok(())
    }

    fn end(&mut self, stream: Stream) -> Result<(), RemoteError> {
        // Stdin ends: the pipe is closed. Under a pty nothing reaches the command (no `^D`,
        // which is the client's to send if it means one, and the master stays the output's);
        // what the client sends after is no longer forwarded, as `ExecSession` stops.
        if stream == Stream::Stdin {
            let _ = self.stdin.send(None);
        }
        Ok(())
    }

    /// Signals the command's process group: while the command is alive, and after it has
    /// exited for as long as it has not been reaped, since what it started in the background
    /// is in its group and is then what holds the session open. `ExecSession.signal` waits up
    /// to five seconds for the process to start; here it has started before the sink exists.
    fn signal(&mut self, signal: i32) {
        let reaped = self.shared.reaped.lock().unwrap_or_else(|e| e.into_inner());
        if !*reaped {
            // SAFETY: killpg takes no pointers; an error (the group gone) is ignored.
            unsafe { libc::killpg(self.pid, signal) };
        }
    }

    /// Sets the window of the command's terminal, which the kernel tells its foreground
    /// process group of with `SIGWINCH`. A command run on pipes has no window to set.
    fn resize(&mut self, rows: u16, cols: u16) {
        if let Some(master) = &self.terminal {
            let size = libc::winsize {
                ws_row: rows,
                ws_col: cols,
                ws_xpixel: 0,
                ws_ypixel: 0,
            };
            // SAFETY: `size` is a valid winsize for the kernel to read; an error (the terminal
            // gone with the command) is ignored.
            unsafe { libc::ioctl(master.as_raw_fd(), libc::TIOCSWINSZ, &size) };
        }
    }

    /// Stops the reading of the command's output, or starts it again. What was read before
    /// the client asked is still sent.
    fn hold(&mut self, held: bool) {
        *self.shared.held.lock().unwrap_or_else(|e| e.into_inner()) = held;
        self.shared.let_go.notify_all();
    }

    fn is_done(&self) -> bool {
        self.shared.done.load(Ordering::SeqCst)
    }

    fn shutdown(&mut self) {
        // Let go of first: the output is read to its end before the command is reaped.
        self.hold(false);
        self.signal(libc::SIGKILL);
        let _ = self.stdin.send(None);
    }
}

/// An errno from `nix` as the wire carries it.
fn nix_error(errno: nix::errno::Errno) -> RemoteError {
    RemoteError::errno(errno as i32)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::proto::Kind;
    use std::time::{Duration, Instant};

    /// The frames sent, in order.
    #[derive(Default)]
    struct Recorder(Mutex<Vec<Frame>>);

    impl Outbox for Recorder {
        fn send(&self, frame: Frame) -> Result<(), crate::proto::ProtocolError> {
            self.0.lock().unwrap().push(frame);
            Ok(())
        }
    }

    impl Recorder {
        fn frames(&self) -> Vec<Frame> {
            self.0.lock().unwrap().clone()
        }

        /// Waits for the exchange to close, returning its frames.
        fn closed(&self, within: Duration) -> Vec<Frame> {
            let deadline = Instant::now() + within;
            loop {
                let frames = self.frames();
                if frames
                    .iter()
                    .any(|f| matches!(f.kind, Kind::Rsp | Kind::Err))
                {
                    return frames;
                }
                assert!(Instant::now() < deadline, "no reply: {frames:?}");
                thread::sleep(Duration::from_millis(10));
            }
        }
    }

    /// Paths taken as they are; a fence that runs its own command instead.
    struct Here;

    impl Place for Here {
        fn resolve(&self, virtual_path: &str) -> Result<PathBuf, RemoteError> {
            if virtual_path.starts_with("/outside") {
                return Err(RemoteError::errno(libc::EACCES));
            }
            Ok(PathBuf::from(virtual_path))
        }

        fn rewrite(&self, text: &str) -> String {
            text.replace("/virtual", "/tmp")
        }

        fn fenced(
            &self,
            argv: &[OsString],
            _program: Option<&OsString>,
            said: &Value,
        ) -> Result<Vec<OsString>, RemoteError> {
            if said == "refuse" {
                return Err(RemoteError::errno(libc::EPERM));
            }
            let mut fenced: Vec<OsString> = vec!["sh".into(), "-c".into()];
            fenced.push("echo fenced; exec \"$@\"".into());
            fenced.push("fence".into());
            fenced.extend(argv.iter().cloned());
            Ok(fenced)
        }
    }

    fn run(meta: Meta) -> (Result<Box<dyn Sink>, RemoteError>, Arc<Recorder>) {
        let recorder = Arc::new(Recorder::default());
        let outbox: Arc<dyn Outbox> = recorder.clone();
        let sink = Request::parse(&meta).and_then(|request| start(7, request, &Here, outbox));
        (sink, recorder)
    }

    fn sh(script: &str) -> Meta {
        crate::meta! {"argv" => serde_json::json!(["sh", "-c", script]), "cwd" => "/tmp"}
    }

    fn output(frames: &[Frame], stream: Stream) -> Vec<u8> {
        frames
            .iter()
            .filter(|f| f.kind == Kind::Chunk && f.stream() == stream)
            .flat_map(|f| f.body.clone())
            .collect()
    }

    fn reply(frames: &[Frame]) -> &Frame {
        let last = frames.last().unwrap();
        assert!(matches!(last.kind, Kind::Rsp | Kind::Err), "{frames:?}");
        assert!(frames.iter().all(|f| f.kind != Kind::End));
        last
    }

    const WAIT: Duration = Duration::from_secs(20);

    #[test]
    fn answers_the_exit_code_and_splits_output() {
        let (sink, out) = run(sh("echo out; echo err >&2; exit 3"));
        let sink = sink.unwrap();
        let frames = out.closed(WAIT);
        assert_eq!(output(&frames, Stream::Stdout), b"out\n");
        assert_eq!(output(&frames, Stream::Stderr), b"err\n");
        assert_eq!(reply(&frames).meta, crate::meta! {"exit_code" => 3});
        assert!(sink.is_done());
    }

    #[test]
    fn feeds_stdin_until_its_end() {
        let (sink, out) = run(sh("cat; echo done"));
        let mut sink = sink.unwrap();
        sink.feed(Stream::Stdin, b"hello ").unwrap();
        sink.feed(Stream::Stdout, b"ignored").unwrap();
        sink.feed(Stream::Stdin, b"world\n").unwrap();
        sink.end(Stream::Stdin).unwrap();
        let frames = out.closed(WAIT);
        assert_eq!(output(&frames, Stream::Stdout), b"hello world\ndone\n");
        assert_eq!(reply(&frames).meta, crate::meta! {"exit_code" => 0});
    }

    #[test]
    fn answers_the_signal_that_killed_it() {
        let (sink, out) = run(sh("echo up; sleep 30"));
        let mut sink = sink.unwrap();
        let deadline = Instant::now() + WAIT;
        while output(&out.frames(), Stream::Stdout).is_empty() {
            assert!(Instant::now() < deadline);
            thread::sleep(Duration::from_millis(10));
        }
        sink.signal(libc::SIGTERM);
        let frames = out.closed(WAIT);
        assert_eq!(reply(&frames).meta, crate::meta! {"signal" => 15});
    }

    #[test]
    fn runs_under_a_pty() {
        let mut meta = sh("test -t 0 && test -t 1 && echo tty; stty size; echo oops >&2");
        meta.insert("tty".into(), Value::Bool(true));
        meta.insert("winsize".into(), serde_json::json!([33, 101]));
        let (sink, out) = run(meta);
        sink.unwrap();
        let frames = out.closed(WAIT);
        let text = String::from_utf8(output(&frames, Stream::Stdout)).unwrap();
        assert_eq!(text, "tty\r\n33 101\r\noops\r\n");
        assert!(output(&frames, Stream::Stderr).is_empty());
        assert_eq!(reply(&frames).meta, crate::meta! {"exit_code" => 0});
    }

    #[test]
    fn resizes_the_terminal_it_runs_under() {
        let mut meta = sh("stty size; read line; stty size");
        meta.insert("tty".into(), Value::Bool(true));
        meta.insert("winsize".into(), serde_json::json!([24, 80]));
        let (sink, out) = run(meta);
        let mut sink = sink.unwrap();
        let deadline = Instant::now() + WAIT;
        while !output(&out.frames(), Stream::Stdout).ends_with(b"24 80\r\n") {
            assert!(Instant::now() < deadline, "{:?}", out.frames());
            thread::sleep(Duration::from_millis(10));
        }
        sink.resize(50, 132);
        sink.feed(Stream::Stdin, b"go\n").unwrap();
        let frames = out.closed(WAIT);
        let text = String::from_utf8(output(&frames, Stream::Stdout)).unwrap();
        assert_eq!(text, "24 80\r\ngo\r\n50 132\r\n");
        assert_eq!(reply(&frames).meta, crate::meta! {"exit_code" => 0});
    }

    #[test]
    fn a_held_command_waits_in_its_terminal_and_loses_nothing() {
        // Far more than a terminal or a pipe keeps: unread, it stops the command.
        let mut meta = sh("stty -echo; echo ready; read go; seq 1 300000; echo E-N-D");
        meta.insert("tty".into(), Value::Bool(true));
        let (sink, out) = run(meta);
        let mut sink = sink.unwrap();
        let deadline = Instant::now() + WAIT;
        while !output(&out.frames(), Stream::Stdout).ends_with(b"ready\r\n") {
            assert!(Instant::now() < deadline, "{:?}", out.frames());
            thread::sleep(Duration::from_millis(10));
        }
        sink.hold(true);
        sink.feed(Stream::Stdin, b"go\n").unwrap();
        // At most what one read was already waiting for arrives, then nothing more.
        let mut seen = usize::MAX;
        let deadline = Instant::now() + WAIT;
        loop {
            thread::sleep(Duration::from_millis(300));
            let now = output(&out.frames(), Stream::Stdout).len();
            if now == seen {
                break;
            }
            assert!(Instant::now() < deadline);
            seen = now;
        }
        assert!(seen <= CHUNK_SIZE, "{seen} bytes read of a held command");
        assert!(!out.frames().iter().any(|f| f.kind == Kind::Rsp));

        sink.hold(false);
        let frames = out.closed(WAIT);
        // A line whose writing a full terminal held up may be ended `\r\r\n`, as macOS
        // ends it.
        let text = String::from_utf8(output(&frames, Stream::Stdout)).unwrap();
        let lines: Vec<&str> = text
            .lines()
            .map(|line| line.trim_end_matches('\r'))
            .collect();
        let numbers: Vec<String> = (1..=300_000).map(|n| n.to_string()).collect();
        assert_eq!(lines.len(), numbers.len() + 2);
        assert_eq!(lines[0], "ready");
        assert!(
            lines[1..=numbers.len()] == numbers[..],
            "what a held command wrote was lost or came out of order"
        );
        assert_eq!(lines[numbers.len() + 1], "E-N-D");
        assert_eq!(reply(&frames).meta, crate::meta! {"exit_code" => 0});
    }

    #[test]
    fn a_held_command_is_let_go_of_when_the_connection_goes() {
        let (sink, out) = run(sh("echo up; sleep 30"));
        let mut sink = sink.unwrap();
        sink.hold(true);
        sink.shutdown();
        let frames = out.closed(WAIT);
        assert_eq!(reply(&frames).meta, crate::meta! {"signal" => 9});
    }

    #[test]
    fn a_command_on_pipes_has_no_window_to_resize() {
        let (sink, out) = run(sh("echo plain"));
        let mut sink = sink.unwrap();
        sink.resize(10, 10);
        let frames = out.closed(WAIT);
        assert_eq!(output(&frames, Stream::Stdout), b"plain\n");
    }

    #[test]
    fn a_missing_program_is_enoent() {
        let mut meta = sh("true");
        meta.insert("program".into(), Value::from("/no/such/program"));
        let error = run(meta).0.err().unwrap();
        assert_eq!(error.errno, libc::ENOENT);
        let meta =
            crate::meta! {"argv" => serde_json::json!(["/no/such/program"]), "cwd" => "/tmp"};
        assert_eq!(run(meta).0.err().unwrap().errno, libc::ENOENT);
    }

    #[test]
    fn a_missing_path_falls_back_to_the_name() {
        let mut meta = sh("echo found $0");
        meta.insert("program".into(), Value::from("/agent/bundle/bin/sh"));
        let (sink, out) = run(meta);
        sink.unwrap();
        let frames = out.closed(WAIT);
        assert_eq!(output(&frames, Stream::Stdout), b"found sh\n");
    }

    #[test]
    fn a_background_child_holds_the_session_open() {
        let started = Instant::now();
        let (sink, out) = run(sh("(sleep 1; echo late) & echo early"));
        sink.unwrap();
        let frames = out.closed(WAIT);
        assert!(started.elapsed() >= Duration::from_millis(900));
        assert_eq!(output(&frames, Stream::Stdout), b"early\nlate\n");
        assert_eq!(reply(&frames).meta, crate::meta! {"exit_code" => 0});
    }

    #[test]
    fn a_signal_reaches_what_holds_the_session_open() {
        let (sink, out) = run(sh("(sleep 30; echo late) & echo early"));
        let mut sink = sink.unwrap();
        let deadline = Instant::now() + WAIT;
        while output(&out.frames(), Stream::Stdout).is_empty() {
            assert!(Instant::now() < deadline);
            thread::sleep(Duration::from_millis(10));
        }
        thread::sleep(Duration::from_millis(200));
        sink.shutdown();
        let frames = out.closed(WAIT);
        assert_eq!(output(&frames, Stream::Stdout), b"early\n");
    }

    #[test]
    fn composes_the_environment() {
        let mut meta = sh("echo \"$PWD|$HOME_HERE|$PATH_SET|$KEEP|$TERM\"");
        meta.insert(
            "env".into(),
            serde_json::json!({
                "KEEP": "/virtual/x", "PATH": "/client/bin", "HUMANIZE_X": "1",
                "LD_PRELOAD": "x", "HOME_HERE": "yes",
            }),
        );
        meta.insert("cwd".into(), Value::from("/outside/the/exports"));
        let (sink, out) = run(meta);
        sink.unwrap();
        let frames = out.closed(WAIT);
        let text = String::from_utf8(output(&frames, Stream::Stdout)).unwrap();
        let parts: Vec<&str> = text.trim_end().split('|').collect();
        assert_eq!(PathBuf::from(parts[0]), home());
        assert_eq!(parts[1], "yes");
        assert_eq!(parts[3], "/tmp/x");
        let env = compose_env(
            [("PATH", OsString::from("/client")), ("LD_X", "1".into())].into_iter(),
            OsStr::new("/w"),
            true,
        );
        assert_ne!(
            env.get(OsStr::new("PATH")),
            Some(&OsString::from("/client"))
        );
        assert!(!env.contains_key(OsStr::new("LD_X")));
        assert_eq!(env[OsStr::new("PWD")], "/w");
        assert!(env.contains_key(OsStr::new("TERM")));
    }

    #[test]
    fn runs_the_fenced_command() {
        let mut meta = sh("echo inside");
        meta.insert("fence".into(), serde_json::json!({"fs": "workspace"}));
        let (sink, out) = run(meta);
        sink.unwrap();
        let frames = out.closed(WAIT);
        assert_eq!(output(&frames, Stream::Stdout), b"fenced\ninside\n");
        let mut meta = sh("true");
        meta.insert("fence".into(), Value::from("refuse"));
        assert_eq!(run(meta).0.err().unwrap().errno, libc::EPERM);
    }

    #[test]
    fn a_malformed_request_is_einval() {
        for meta in [
            crate::meta! {"cwd" => "/tmp"},
            crate::meta! {"argv" => serde_json::json!(["true"])},
            crate::meta! {"argv" => serde_json::json!([]), "cwd" => "/tmp"},
            crate::meta! {"argv" => "true", "cwd" => "/tmp"},
            crate::meta! {"argv" => serde_json::json!(["true"]), "cwd" => "/tmp", "env" => 3},
            crate::meta! {
                "argv" => serde_json::json!(["true"]), "cwd" => "/tmp",
                "env" => serde_json::json!({"PATH=/client/bin": "x"}),
            },
        ] {
            assert_eq!(run(meta).0.err().unwrap().errno, libc::EINVAL);
        }
    }
}

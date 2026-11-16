//! The credential tracer. Port of `hmz.coganchor.providers._trace`, the supervisor half of
//! `hmz.coganchor.providers.redirect` (`read`, `run`, `_supervised`, `_program`,
//! `_supervising`, `supervises`) and `hmz.cli.cred`. [Unit 15]
//!
//! Every syscall that names a path stops on the way in (the trap filter, installed by the
//! program on itself). The path is resolved as the kernel would resolve it, and if it is one
//! the table answers, the answer is planted below the tracee's stack pointer and the argument
//! pointed at it; the call then runs natively against the file it was given. One that cannot
//! be rewritten is failed with `EIO` rather than let through: a turn that read the credentials
//! of whoever is at this machine would be a turn run as the wrong account.
//!
//! Which answer depends on what the call is about to do: one that only asks about a credential
//! or opens it to read is given the copy [`Staging`] keeps in memory, one that could change it
//! is given the account's own file and drops the copy. A kept path (a session's) is never given
//! a copy.
//!
//! The decisions ([`Swaps`], [`theirs`], [`normpath`], [`changes`], [`creates`], [`copyable`],
//! [`scratch`]) are pure functions, tested without ptrace; [`Tracer`] is the loop around them.

use std::collections::{HashMap, HashSet};
use std::ffi::{CString, OsStr, OsString};
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, OwnedFd};
use std::os::unix::ffi::{OsStrExt, OsStringExt};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::sync::atomic::{AtomicI32, Ordering};
use std::time::{Duration, Instant};

use nix::fcntl::OFlag;
use nix::sys::signal::{SaFlags, SigAction, SigHandler, SigSet, Signal, sigaction};
use nix::sys::wait::waitpid;
use nix::unistd::{ForkResult, Pid, fork, getpid, getppid, pipe2, setsid};

use super::staging::Staging;
use crate::cli::CredArgs;
use crate::cog::lending;
use crate::cog::pathcalls::{self, PathCall};
use crate::cog::policy;
use crate::exit;
use crate::sys::{ARCH, procfs, ptrace, syscalls, trap};

/// `AT_FDCWD`: the descriptor that means "wherever the process is".
const AT_FDCWD: i32 = -100;

/// Where `struct open_how` keeps its flags (the front of it) and its resolve flags.
const OPEN_HOW_FLAGS: u64 = 0;
const OPEN_HOW_RESOLVE: u64 = 16;

/// `RESOLVE_BENEATH | RESOLVE_IN_ROOT`: resolutions an absolute path elsewhere cannot honour,
/// so an `openat2` asking for either is failed rather than answered (`_RESOLVE_CONFINED`).
const RESOLVE_CONFINED: u64 = 0x08 | 0x10;

/// What an `open` has to ask for to be one that changes things: anything but reading
/// (`_WRITING`).
const WRITING: u64 =
    (libc::O_WRONLY | libc::O_RDWR | libc::O_CREAT | libc::O_TRUNC | libc::O_APPEND) as u64;

/// The lookups a copy answers as well as the file does (`_READS`). Said this way round on
/// purpose: a call nobody has thought about is one that changes things and reaches the
/// account's own file. `readlink` of a copy (a regular file) answers `EINVAL` as the original
/// would; `chdir` never reaches a copy, since directories are not copied. The other lookups of
/// the path table (xattrs, `statfs`, watches, handles) are given the account's own file.
const READS: &[&str] = &[
    "stat",
    "lstat",
    "access",
    "readlink",
    "chdir",
    "newfstatat",
    "statx",
    "faccessat",
    "faccessat2",
    "readlinkat",
];

/// The calls whose flags say whether they write or create, and where those flags are.
const OPENS: &[&str] = &["open", "openat", "openat2"];

/// What a syscall whose path could not be rewritten is failed with (`UNSWAPPABLE`).
pub const UNSWAPPABLE: i32 = libc::EIO;

/// What a program the tracer could not take on exits with: it was never run (`_UNSUPERVISED`).
const UNSUPERVISED: i32 = 1;

/// `PR_SET_PTRACER`: the one process Yama is to let trace this one.
const PR_SET_PTRACER: libc::c_int = 0x5961_6D61;

/// What the tracer is told about: `TRACESYSGOOD|FORK|VFORK|CLONE|EXEC|SECCOMP|EXITKILL`, the
/// options [`ptrace::set_cog_options`] sets on every later tracee.
const OPTIONS: libc::c_int = libc::PTRACE_O_TRACESYSGOOD
    | libc::PTRACE_O_TRACEFORK
    | libc::PTRACE_O_TRACEVFORK
    | libc::PTRACE_O_TRACECLONE
    | libc::PTRACE_O_TRACEEXEC
    | libc::PTRACE_O_TRACESECCOMP
    | libc::PTRACE_O_EXITKILL;

/// The usage line, as `argparse` printed it for `hmz internal cred`.
const USAGE: &str = "usage: hmz internal cred [-h] [--map FROM=TO] [--keep FROM=TO] ...";

// ---------------------------------------------------------------------------------------------
// The table and the decisions: pure.

/// Which paths a traced process is given instead of the ones it named (`Swaps`): `pairs` are
/// credentials, whose reads may be answered with a copy; `kept` are sessions, answered with the
/// file itself always. Each is tidied and longest first.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Swaps {
    pub pairs: Vec<(String, String)>,
    pub kept: Vec<(String, String)>,
}

/// `(what the agent names, what it gets)` pairs, tidied, without empty halves, longest first
/// (`_table`).
fn table(pairs: impl IntoIterator<Item = (String, String)>) -> Vec<(String, String)> {
    let mut held: Vec<(String, String)> = pairs
        .into_iter()
        .filter(|(one, other)| !one.is_empty() && !other.is_empty())
        .map(|(one, other)| (normpath(&one), normpath(&other)))
        .collect();
    held.sort_by_key(|(named, _)| std::cmp::Reverse(named.len()));
    held
}

impl Swaps {
    /// A table from `(what the agent names, what it gets)` pairs (`Swaps.of`).
    pub fn of(
        pairs: impl IntoIterator<Item = (String, String)>,
        kept: impl IntoIterator<Item = (String, String)>,
    ) -> Self {
        Swaps {
            pairs: table(pairs),
            kept: table(kept),
        }
    }

    /// Reads the table off `--map` and `--keep` (`redirect.read`): each `FROM=TO`, split at the
    /// first `=`, both absolute.
    pub fn read(maps: &[String], keeps: &[String]) -> Result<Self, String> {
        fn pairs(of: &[String]) -> Result<Vec<(String, String)>, String> {
            of.iter()
                .map(|one| match one.split_once('=') {
                    Some((named, instead))
                        if named.starts_with('/') && instead.starts_with('/') =>
                    {
                        Ok((named.to_owned(), instead.to_owned()))
                    }
                    _ => Err(format!("'{one}' is not FROM=TO, of two absolute paths")),
                })
                .collect()
        }
        Ok(Swaps::of(pairs(maps)?, pairs(keeps)?))
    }

    /// Whether nothing is pointed anywhere else.
    pub fn is_empty(&self) -> bool {
        self.pairs.is_empty() && self.kept.is_empty()
    }

    /// What `path` (absolute, normalised) is answered with and whether it is kept, or `None`
    /// for a path that is its own (`Swaps.answer`): the longest entry that answers it across
    /// both tables, each entry read by [`policy::answered`].
    pub fn answer(&self, path: &str) -> Option<(String, bool)> {
        let mut best: Option<(usize, String, bool)> = None;
        for (held, kept) in [(&self.pairs, false), (&self.kept, true)] {
            for entry in held {
                if best.as_ref().is_some_and(|(len, ..)| entry.0.len() <= *len) {
                    break;
                }
                if let Some(found) = policy::answered(std::slice::from_ref(entry), path) {
                    best = Some((entry.0.len(), found, kept));
                    break;
                }
            }
        }
        best.map(|(_, found, kept)| (found, kept))
    }

    /// What every path the table could answer starts with: each entry's [`policy::head`].
    pub fn prefixes(&self) -> Vec<Vec<u8>> {
        self.pairs
            .iter()
            .chain(&self.kept)
            .map(|(named, _)| policy::head(named).into_bytes())
            .collect()
    }

    /// The credentials the table answers with, which a run lends to itself.
    pub fn credentials(&self) -> Vec<PathBuf> {
        self.pairs
            .iter()
            .map(|(_, instead)| PathBuf::from(instead))
            .collect()
    }
}

/// `os.path.normpath` on a POSIX path: doubled separators, `.` and `..` collapsed lexically,
/// exactly two leading separators kept (which [`Tracer`] then reads as one, as Linux does).
pub fn normpath(path: &str) -> String {
    if path.is_empty() {
        return ".".to_owned();
    }
    let leading = if path.starts_with("//") && !path.starts_with("///") {
        2
    } else if path.starts_with('/') {
        1
    } else {
        0
    };
    let mut parts: Vec<&str> = Vec::new();
    for part in path.split('/') {
        match part {
            "" | "." => {}
            ".." if leading == 0 && parts.last().is_none_or(|last| *last == "..") => {
                parts.push(part)
            }
            ".." => {
                parts.pop();
            }
            _ => parts.push(part),
        }
    }
    let joined = format!("{}{}", "/".repeat(leading), parts.join("/"));
    if joined.is_empty() {
        ".".to_owned()
    } else {
        joined
    }
}

/// Whether a path spelled as `raw` may read as something other than what it says: a doubled
/// separator, a `.` or `..` of its own, or a separator on the end (`_UNTIDY`).
fn untidy(raw: &[u8]) -> bool {
    raw.windows(2).any(|pair| pair == b"//")
        || raw.ends_with(b"/")
        || raw.ends_with(b"/.")
        || raw.ends_with(b"/..")
        || raw.windows(3).any(|three| three == b"/./")
        || raw.windows(4).any(|four| four == b"/../")
}

/// Whether a tidy absolute path reaches another file through a `/proc` link (`_MAGICAL`:
/// `/proc/(self|thread-self|<n>)/(fd/<digit>|cwd|exe|root|task/)`, as a prefix).
///
/// `/dev/fd/<digit>` too, which is a link to `/proc/self/fd` the Python let past: it is
/// spelled back as `/proc/self/fd/` ([`unaliased`]) and resolved the same way.
fn magical(raw: &[u8]) -> bool {
    if raw
        .strip_prefix(b"/dev/fd/")
        .is_some_and(|fd| fd.first().is_some_and(u8::is_ascii_digit))
    {
        return true;
    }
    let Some(rest) = raw.strip_prefix(b"/proc/") else {
        return false;
    };
    let rest = if let Some(rest) = rest.strip_prefix(b"self/") {
        rest
    } else if let Some(rest) = rest.strip_prefix(b"thread-self/") {
        rest
    } else {
        let digits = rest.iter().take_while(|byte| byte.is_ascii_digit()).count();
        match rest[digits..].strip_prefix(b"/") {
            Some(rest) if digits > 0 => rest,
            _ => return false,
        }
    };
    rest.strip_prefix(b"fd/")
        .is_some_and(|fd| fd.first().is_some_and(u8::is_ascii_digit))
        || [&b"cwd"[..], b"exe", b"root", b"task/"]
            .iter()
            .any(|link| rest.starts_with(link))
}

/// Whether a path is the program's own, decided on the bytes it was named with (`_theirs`):
/// absolute, tidy, not through `/proc`, and starting with none of `prefixes`. Nearly every
/// stop ends here. False means "maybe": the path is resolved and held against the table.
pub fn theirs(raw: &[u8], prefixes: &[Vec<u8>]) -> bool {
    raw.first() == Some(&b'/')
        && !prefixes.iter().any(|prefix| raw.starts_with(prefix))
        && !magical(raw)
        && !untidy(raw)
}

/// Whether `call` could change what is at the path it names (`_changes`), given the flags an
/// `open` asked for (`None` where an `openat2`'s could not be read, which is taken as a write:
/// unknown is the durable answer). Reads and lookups do not; anything else does.
pub fn changes(call: &PathCall, flags: Option<u64>) -> bool {
    if READS.contains(&call.name) || call.looks {
        return false;
    }
    if OPENS.contains(&call.name) {
        return flags.is_none_or(|flags| flags & WRITING != 0);
    }
    true
}

/// Whether a call that changes things may make something at a path it names (`_creates`):
/// one that creates, links or renames, and an `open` asking to create.
pub fn creates(call: &PathCall, flags: Option<u64>) -> bool {
    if call.makes {
        return true;
    }
    OPENS.contains(&call.name) && flags.is_some_and(|flags| flags & libc::O_CREAT as u64 != 0)
}

/// Whether a read by `call` may be answered with a copy: anything but a lookup a copy cannot
/// answer for its original (`_UNCOPIED = LOOKS - _READS`).
pub fn copyable(call: &PathCall) -> bool {
    !call.looks || READS.contains(&call.name)
}

/// Where `size` bytes may be planted below a tracee's stack pointer `sp`, clear of the red
/// zone (`Registers.scratch`).
pub fn scratch(sp: u64, red_zone: u64, size: u64) -> u64 {
    sp.wrapping_sub(red_zone).wrapping_sub(size)
}

/// `/dev/fd/...` spelled as what it links to, `/proc/self/fd/...`; any other path as it is.
fn unaliased(path: String) -> String {
    match path.strip_prefix("/dev/fd/") {
        Some(rest) => format!("/proc/self/fd/{rest}"),
        None => path,
    }
}

/// `os.path.join(under, said)` for a relative `said`.
fn joined(under: &str, said: &str) -> String {
    if under.ends_with('/') {
        format!("{under}{said}")
    } else {
        format!("{under}/{said}")
    }
}

// ---------------------------------------------------------------------------------------------
// The loop.

/// Why a path could not be named.
enum Unnamed {
    /// A `/proc` link that could not be followed: the call is cancelled.
    Unresolved,
    /// The process went away mid-read, or the descriptor is not a directory here: skipped.
    Skipped,
}

/// One redirected run (`Tracing`): what it answers, and the processes it watches.
pub struct Tracer {
    swaps: Swaps,
    staging: Staging,
    prefixes: Vec<Vec<u8>>,
    /// The path calls this architecture has, by number.
    calls: HashMap<i64, &'static PathCall>,
    /// The directories a session's path has been given already.
    made: HashSet<String>,
    /// Every process watched, and whether its first stop has been seen.
    watching: HashMap<i32, bool>,
    /// What to plant at the exit stop of a cancelled syscall, by process.
    owed: HashMap<i32, i32>,
    root: i32,
    /// Which process started each process, and which process each thread is one of.
    parents: HashMap<i32, i32>,
    threads: HashMap<i32, i32>,
    /// The processes that went while the program ran, which what they started left it by.
    gone: HashSet<i32>,
    /// Whether the program is over, and the processes that went with it.
    over: bool,
    doomed: HashSet<i32>,
}

impl Tracer {
    /// A run watching nothing yet.
    pub fn new(swaps: Swaps) -> Self {
        let calls = pathcalls::table()
            .iter()
            .filter_map(|call| syscalls::number(call.name).map(|nr| (nr, call)))
            .collect();
        Tracer {
            prefixes: swaps.prefixes(),
            swaps,
            staging: Staging::new(),
            calls,
            made: HashSet::new(),
            watching: HashMap::new(),
            owed: HashMap::new(),
            root: 0,
            parents: HashMap::new(),
            threads: HashMap::new(),
            gone: HashSet::new(),
            over: false,
            doomed: HashSet::new(),
        }
    }

    /// The syscalls the filter stops: every one that names a path.
    pub fn trapped(&self) -> Vec<i64> {
        let mut numbers: Vec<i64> = self.calls.keys().copied().collect();
        numbers.sort_unstable();
        numbers
    }

    /// Takes away the copies this run answered reads with.
    pub fn close(&mut self) {
        self.staging.close();
    }

    /// Takes on the program, which has named this process its tracer.
    pub fn attach(&mut self, pid: i32) -> io::Result<()> {
        request(libc::PTRACE_SEIZE, pid, 0, OPTIONS as usize)?;
        self.root = pid;
        self.watching.insert(pid, true);
        Ok(())
    }

    /// Services the program and everything it starts until the last of them is over
    /// (`serve`): what the program left running when it ended goes with it, all but what left
    /// it while it ran (a job it detached, `setsid nohup ... &`), served here until it is over.
    pub fn serve(&mut self) -> io::Result<()> {
        while !self.watching.is_empty() {
            let mut status = 0;
            // SAFETY: waitpid writes the status into the local.
            let got = unsafe { libc::waitpid(-1, &mut status, libc::__WALL) };
            if got < 0 {
                let why = io::Error::last_os_error();
                match why.raw_os_error() {
                    Some(libc::EINTR) => continue,
                    Some(libc::ECHILD) => break,
                    _ => return Err(why),
                }
            }
            self.stopped(got, status);
        }
        Ok(())
    }

    /// Acts on one thing that happened to one watched process (`_stopped`).
    fn stopped(&mut self, pid: i32, status: libc::c_int) {
        if libc::WIFEXITED(status) || libc::WIFSIGNALED(status) {
            self.watching.remove(&pid);
            self.owed.remove(&pid);
            if self.threads.remove(&pid).is_none() && !self.over {
                self.gone.insert(pid);
            }
            if pid != self.root {
                return;
            }
            self.over = true;
            let watched: Vec<i32> = self.watching.keys().copied().collect();
            for each in watched {
                let process = self.threads.get(&each).copied().unwrap_or(each);
                if !self.left(process) {
                    self.doomed.insert(process);
                }
            }
            for &process in &self.doomed {
                // SAFETY: kill has no memory effects.
                unsafe { libc::kill(process, libc::SIGKILL) };
            }
            return;
        }
        if !self.watching.get(&pid).copied().unwrap_or(false) {
            // Its first stop, whether or not the fork event has arrived.
            self.watching.insert(pid, true);
            let _ = ptrace::set_cog_options(Pid::from_raw(pid));
            let _ = resume(libc::PTRACE_CONT, pid, 0);
            return;
        }
        let event = status >> 16;
        let said = libc::WSTOPSIG(status);
        if event == libc::PTRACE_EVENT_SECCOMP {
            self.syscall(pid);
        } else if [
            libc::PTRACE_EVENT_FORK,
            libc::PTRACE_EVENT_VFORK,
            libc::PTRACE_EVENT_CLONE,
        ]
        .contains(&event)
        {
            let mut child: libc::c_ulong = 0;
            if request(
                libc::PTRACE_GETEVENTMSG,
                pid,
                0,
                &mut child as *mut libc::c_ulong as usize,
            )
            .is_ok()
            {
                self.born(pid, child as i32, event);
            }
            let _ = resume(libc::PTRACE_CONT, pid, 0);
        } else if event != 0 || said == libc::SIGTRAP {
            let _ = resume(libc::PTRACE_CONT, pid, 0);
        } else if said == libc::SIGTRAP | 0x80 {
            self.answer(pid);
        } else {
            let _ = resume(libc::PTRACE_CONT, pid, said);
        }
    }

    /// Writes down who started a new process or thread (`_born`).
    fn born(&mut self, pid: i32, child: i32, event: libc::c_int) {
        let process = self.threads.get(&pid).copied().unwrap_or(pid);
        self.watching.entry(child).or_insert(false);
        // A clone is a thread more often than not, and a thread's parent is its process's.
        // One whose thread group cannot be read is taken for a thread, as the Python took a
        // parent it could not read.
        if event == libc::PTRACE_EVENT_CLONE
            && procfs::tgid(Pid::from_raw(child)).map(Pid::as_raw).ok() != Some(child)
        {
            self.threads.insert(child, process);
            return;
        }
        self.gone.remove(&child);
        self.parents.insert(child, process);
        if self.doomed.contains(&process) {
            self.doomed.insert(child);
            // SAFETY: kill has no memory effects.
            unsafe { libc::kill(child, libc::SIGKILL) };
        }
    }

    /// Whether a process left the program while it ran: one it came from went first (`_left`).
    fn left(&self, mut process: i32) -> bool {
        while process != self.root {
            if self.gone.contains(&process) {
                return true;
            }
            process = self.parents.get(&process).copied().unwrap_or(self.root);
        }
        false
    }

    /// Rewrites the paths one stopped syscall names, and lets it run (`_syscall`).
    fn syscall(&mut self, raw_pid: i32) {
        let pid = Pid::from_raw(raw_pid);
        let Ok(mut regs) = ptrace::getregs(pid) else {
            return;
        };
        let Some(call) = self.calls.get(&regs.syscall()).copied() else {
            let _ = resume(libc::PTRACE_CONT, raw_pid, 0);
            return;
        };
        let mut taken = 0;
        let mut dirty = false;
        // Read at the first path that is the table's, which is none at nearly every stop.
        let mut flags: Option<Option<u64>> = None;
        for arg in call.args {
            let Ok(raw) = procfs::read_cstring(pid, regs.arg(arg.path)) else {
                continue;
            };
            let raw = raw.as_bytes();
            if raw.is_empty() || theirs(raw, &self.prefixes) {
                continue;
            }
            let said = String::from_utf8_lossy(raw);
            let named = match self.named(pid, &regs, arg.dirfd, &said) {
                Ok(named) => named,
                Err(Unnamed::Unresolved) => return self.cancel(raw_pid, regs),
                Err(Unnamed::Skipped) => continue,
            };
            let Some((instead, kept)) = self.swaps.answer(&named) else {
                continue;
            };
            // A name that is not text cannot be answered faithfully; failed, not let through.
            if std::str::from_utf8(raw).is_err() {
                return self.cancel(raw_pid, regs);
            }
            let flags = *flags.get_or_insert_with(|| open_flags(pid, &regs, call));
            let mut instead = PathBuf::from(instead);
            if kept {
                // A session's, never a copy; its directory is made as something is created.
                if changes(call, flags) && creates(call, flags) {
                    self.parents_of(&instead);
                }
            } else if changes(call, flags) {
                self.staging.wrote(&instead.to_string_lossy());
            } else if copyable(call)
                && let Some(copy) = self.staging.reading(&instead.to_string_lossy())
            {
                instead = copy;
            }
            if confined(pid, &regs, call) {
                return self.cancel(raw_pid, regs);
            }
            match plant(pid, &mut regs, taken, arg.path, instead.as_os_str()) {
                Some(room) => {
                    taken += room;
                    dirty = true;
                }
                None => return self.cancel(raw_pid, regs),
            }
        }
        if dirty {
            let _ = ptrace::setregs(pid, &regs);
        }
        let _ = resume(libc::PTRACE_CONT, raw_pid, 0);
    }

    /// The absolute, tidy path one argument names, resolved as the kernel would (`_named`).
    fn named(
        &self,
        pid: Pid,
        regs: &ptrace::Regs,
        dirfd: Option<usize>,
        said: &str,
    ) -> Result<String, Unnamed> {
        let named = if said.starts_with('/') {
            said.to_owned()
        } else {
            let at = dirfd.map_or(AT_FDCWD, |i| regs.arg(i) as i32);
            let under = if at == AT_FDCWD {
                procfs::cwd(pid)
            } else {
                procfs::fd_path(pid, at)
            }
            .map_err(|_| Unnamed::Skipped)?;
            if !under.starts_with('/') {
                return Err(Unnamed::Skipped); // a descriptor that is not a directory here
            }
            joined(&under, said)
        };
        // A path spelled through a descriptor the process holds reaches the same file as one
        // spelled out in full, which is what the table is keyed by.
        let named = unaliased(named);
        let named = if named.contains("/proc/") {
            procfs::resolve_magic(pid, &named).map_err(|_| Unnamed::Unresolved)?
        } else {
            named
        };
        let tidy = normpath(&named);
        // Linux reads exactly two leading separators as one; `normpath` keeps them.
        Ok(match tidy.strip_prefix("//") {
            Some(rest) => format!("/{rest}"),
            None => tidy,
        })
    }

    /// Makes the directory a kept path is in, once per directory (`policy.parents`).
    fn parents_of(&mut self, path: &Path) {
        let Some(parent) = path
            .parent()
            .map(|parent| parent.to_string_lossy().into_owned())
        else {
            return;
        };
        if self.made.contains(&parent) {
            return;
        }
        if policy::parents(&path.to_string_lossy()).is_ok() {
            self.made.insert(parent);
        }
    }

    /// Fails a syscall whose path could not be rewritten (`_cancel`): skipped now, and
    /// [`UNSWAPPABLE`] planted at its exit stop, since the kernel overwrites the result of a
    /// skipped call.
    fn cancel(&mut self, pid: i32, mut regs: ptrace::Regs) {
        regs.set_syscall(-1);
        self.owed.insert(pid, UNSWAPPABLE);
        if ptrace::setregs(Pid::from_raw(pid), &regs).is_err()
            || resume(libc::PTRACE_SYSCALL, pid, 0).is_err()
        {
            self.owed.remove(&pid);
        }
    }

    /// Plants the errno owed to a cancelled syscall at its exit stop (`_answer`).
    fn answer(&mut self, pid: i32) {
        let Some(code) = self.owed.remove(&pid) else {
            let _ = resume(libc::PTRACE_CONT, pid, 0);
            return;
        };
        let tracee = Pid::from_raw(pid);
        if let Ok(mut regs) = ptrace::getregs(tracee) {
            regs.set_result(-i64::from(code));
            if ptrace::setregs(tracee, &regs).is_ok() {
                let _ = resume(libc::PTRACE_CONT, pid, 0);
            }
        }
    }
}

/// The flags an `open` asked for: from its register, or from the front of an `openat2`'s
/// `struct open_how` (`None` where that cannot be read, and for every other call).
fn open_flags(pid: Pid, regs: &ptrace::Regs, call: &PathCall) -> Option<u64> {
    match call.name {
        "open" => Some(regs.arg(1)),
        "openat" => Some(regs.arg(2)),
        "openat2" => word(pid, regs.arg(2) + OPEN_HOW_FLAGS),
        _ => None,
    }
}

/// Whether an `openat2` insisted on staying beneath its descriptor (`_confined`).
fn confined(pid: Pid, regs: &ptrace::Regs, call: &PathCall) -> bool {
    call.name == "openat2"
        && word(pid, regs.arg(2) + OPEN_HOW_RESOLVE)
            .is_some_and(|resolve| resolve & RESOLVE_CONFINED != 0)
}

/// The 64-bit word of the tracee's memory at `addr`.
fn word(pid: Pid, addr: u64) -> Option<u64> {
    let raw = procfs::read_mem(pid, addr, 8).ok()?;
    Some(u64::from_ne_bytes(raw.try_into().ok()?))
}

/// Writes `path` into the tracee below its stack pointer, past the `taken` bytes earlier paths
/// of this call used, verifies it by reading it back, and points argument `argument` at it
/// (`_plant`). The bytes it took, or `None` where it could not be written.
fn plant(
    pid: Pid,
    regs: &mut ptrace::Regs,
    taken: u64,
    argument: usize,
    path: &OsStr,
) -> Option<u64> {
    let mut blob = path.as_bytes().to_vec();
    blob.push(0);
    let room = blob.len() as u64;
    let at = scratch(regs.sp(), ARCH.red_zone, taken + room);
    procfs::write_mem(pid, at, &blob).ok()?;
    if procfs::read_mem(pid, at, blob.len()).ok()? != blob {
        return None;
    }
    regs.set_arg(argument, at);
    Some(room)
}

/// What `ptrace` takes its request as: an unsigned int in glibc, an int in musl.
#[cfg(target_env = "gnu")]
type Request = libc::c_uint;
#[cfg(not(target_env = "gnu"))]
type Request = libc::c_int;

/// A raw `ptrace` request, as an `io::Result`. Raw rather than `nix::sys::ptrace`, whose
/// `cont` takes a `Signal` and so cannot pass a real-time signal on to the tracee.
fn request(what: Request, pid: i32, addr: usize, data: usize) -> io::Result<()> {
    // SAFETY: every request made here takes integers, or (GETEVENTMSG) a pointer to a live
    // local of the size the kernel writes.
    let done = unsafe {
        libc::ptrace(
            what,
            pid,
            addr as *mut libc::c_void,
            data as *mut libc::c_void,
        )
    };
    if done < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(())
    }
}

/// Resumes a stopped tracee, delivering `signal` (any number, real-time ones included).
fn resume(how: Request, pid: i32, signal: libc::c_int) -> io::Result<()> {
    request(how, pid, 0, signal as usize)
}

// ---------------------------------------------------------------------------------------------
// The processes.

/// Runs `coganchor internal cred` (`hmz.cli.cred`): the program, with the paths it was given
/// answered by others. A run that cannot be supervised never runs unsupervised.
pub fn main(args: CredArgs) -> i32 {
    let mut command = args.command;
    if command.first().is_some_and(|first| first == "--") {
        command.remove(0);
    }
    if command.is_empty() {
        return usage("no program given; try `hmz internal cred --map FROM=TO -- claude`");
    }
    let swaps = match Swaps::read(&args.maps, &args.keeps) {
        Ok(swaps) => swaps,
        Err(why) => return usage(&why),
    };
    if swaps.is_empty() {
        return usage("nothing to answer with anything: give at least one --map or --keep");
    }
    match run(swaps, &command) {
        Ok(code) => code,
        Err(why) => {
            eprintln!("hmz internal cred: {why}");
            exit::FAILED
        }
    }
}

/// Says what was wrong with the command line, as `argparse` would, and returns [`exit::USAGE`].
fn usage(why: &str) -> i32 {
    eprintln!("{USAGE}\nhmz internal cred: error: {why}");
    exit::USAGE
}

/// Runs `command` with the paths `swaps` names answered by others, and waits for it
/// (`redirect.run`): its exit status, or 128 plus the signal that killed it. A sign-in that
/// refreshes itself is held, shared, for as long as the program runs.
pub fn run(swaps: Swaps, command: &[OsString]) -> io::Result<i32> {
    let argv = command
        .iter()
        .map(|one| CString::new(one.clone().into_vec()))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|why| io::Error::new(io::ErrorKind::InvalidInput, why))?;
    let _lent = lending::lent(&swaps.credentials(), false)?;
    supervised(Tracer::new(swaps), &argv)
}

/// The pid of the program, for the handler passing signals on to it.
static PROGRAM: AtomicI32 = AtomicI32::new(0);

extern "C" fn passed(signum: libc::c_int) {
    let pid = PROGRAM.load(Ordering::Relaxed);
    if pid > 0 {
        // SAFETY: kill is async-signal-safe.
        unsafe { libc::kill(pid, signum) };
    }
}

/// Runs the program under a tracer outside its tree, and waits for it (`_supervised`).
///
/// The program is this process's child, as an unsupervised one would be. The tracer is not: it
/// may outlive the program (a job the program detached is still served), so it is started by a
/// double fork into a session of its own, and the program asks to be traced by it. Two pipes
/// carry the handshake: the tracer says its pid, the program its own, the tracer that it
/// traces it. This process stays single-threaded throughout, so the forked children may
/// allocate.
fn supervised(tracer: Tracer, argv: &[CString]) -> io::Result<i32> {
    let numbers = tracer.trapped();
    let (said, saying) = pipe2(OFlag::O_CLOEXEC)?;
    let (traced, tracing_it) = pipe2(OFlag::O_CLOEXEC)?;
    // SAFETY: this process is single-threaded.
    match unsafe { fork() }? {
        ForkResult::Child => {
            let _ = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                if setsid().is_ok()
                    // SAFETY: still single-threaded.
                    && let Ok(ForkResult::Child) = unsafe { fork() }
                {
                    drop((saying, traced));
                    supervising(tracer, said, tracing_it);
                }
            }));
            // SAFETY: leaves the forked child without running the parent's code.
            unsafe { libc::_exit(0) }
        }
        ForkResult::Parent { child } => {
            while let Err(nix::errno::Errno::EINTR) = waitpid(child, None) {}
        }
    }
    let turn = getpid();
    // SAFETY: this process is single-threaded.
    let pid = match unsafe { fork() }? {
        ForkResult::Child => {
            drop((said, tracing_it));
            program(argv, saying, traced, turn, &numbers)
        }
        ForkResult::Parent { child } => child,
    };
    drop((said, saying, traced, tracing_it));

    // A signal aimed at this process is aimed at the program, and passed on; SIGINT is
    // ignored, since a ctrl-c at a terminal already reaches the whole group.
    PROGRAM.store(pid.as_raw(), Ordering::Relaxed);
    let passing = SigAction::new(
        SigHandler::Handler(passed),
        SaFlags::SA_RESTART,
        SigSet::empty(),
    );
    let ignoring = SigAction::new(SigHandler::SigIgn, SaFlags::empty(), SigSet::empty());
    let mut was = Vec::new();
    for (signal, then) in [
        (Signal::SIGINT, &ignoring),
        (Signal::SIGTERM, &passing),
        (Signal::SIGQUIT, &passing),
        (Signal::SIGHUP, &passing),
    ] {
        // SAFETY: the handler only loads an atomic and calls kill.
        if let Ok(before) = unsafe { sigaction(signal, then) } {
            was.push((signal, before));
        }
    }
    let status = loop {
        match waitpid(pid, None) {
            Err(nix::errno::Errno::EINTR) => continue,
            done => break done,
        }
    };
    for (signal, before) in was {
        // SAFETY: puts back what was there.
        let _ = unsafe { sigaction(signal, &before) };
    }
    PROGRAM.store(0, Ordering::Relaxed);
    Ok(exit::of_wait(status?))
}

/// Reads a decimal number on a line of its own from `fd`, 0 for nothing.
fn heard(fd: &OwnedFd) -> i32 {
    let Ok(fd) = fd.try_clone() else {
        return 0;
    };
    let mut file = std::fs::File::from(fd);
    let mut line = Vec::new();
    let mut byte = [0u8; 1];
    while let Ok(1) = file.read(&mut byte) {
        if byte[0] == b'\n' {
            break;
        }
        line.push(byte[0]);
    }
    std::str::from_utf8(&line)
        .ok()
        .and_then(|said| said.trim().parse().ok())
        .unwrap_or(0)
}

/// Writes `blob` to `fd`.
fn say(fd: &OwnedFd, blob: &[u8]) -> io::Result<()> {
    std::fs::File::from(fd.try_clone()?).write_all(blob)
}

/// Writes straight to standard error, from a forked child.
fn complain(said: &str) {
    let _ = io::stderr().write_all(said.as_bytes());
}

/// The program's half (`_program`): go with the turn, let the tracer trace it, install the
/// trap filter, and become the program. Never returns.
fn program(argv: &[CString], saying: OwnedFd, traced: OwnedFd, turn: Pid, numbers: &[i64]) -> ! {
    let why = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| -> String {
        // SAFETY: prctl with integer arguments.
        unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL, 0, 0, 0) };
        if getppid() != turn {
            // The turn went before that was said.
            // SAFETY: leaves the forked child.
            unsafe { libc::_exit(128 + libc::SIGKILL) };
        }
        let supervisor = heard(&traced);
        // Refused where there is no Yama to ask, which then lets any process of this user.
        // SAFETY: prctl with integer arguments.
        unsafe { libc::prctl(PR_SET_PTRACER, supervisor as libc::c_ulong, 0, 0, 0) };
        let _ = say(&saying, format!("{}\n", getpid()).as_bytes());
        drop(saying);
        let mut bang = [0u8; 1];
        let traced_now =
            supervisor != 0 && matches!(std::fs::File::from(traced).read(&mut bang), Ok(1));
        if !traced_now {
            complain("hmz internal cred: nothing could supervise it\n");
            // SAFETY: leaves the forked child.
            unsafe { libc::_exit(UNSUPERVISED) };
        }
        if let Err(why) = trap::install(numbers) {
            return why.to_string();
        }
        match nix::unistd::execvp(&argv[0], argv) {
            Err(why) => io::Error::from(why).to_string(),
        }
    }))
    .unwrap_or_else(|_| "panicked".to_owned());
    complain(&format!(
        "hmz: cannot run {}: {why}\n",
        argv[0].to_string_lossy()
    ));
    // SAFETY: leaves the forked child.
    unsafe { libc::_exit(exit::NOT_INSTALLED) }
}

/// The tracer's half (`_supervising`): trace the program and what it leaves, then take the
/// copies away and exit. Never returns.
fn supervising(mut tracer: Tracer, said: OwnedFd, tracing_it: OwnedFd) -> ! {
    let done = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| -> io::Result<()> {
        say(&tracing_it, format!("{}\n", getpid()).as_bytes())?;
        let pid = heard(&said);
        drop(said);
        if pid != 0 {
            tracer.attach(pid)?;
            say(&tracing_it, b"!")?;
            drop(tracing_it);
            // What reads the turn's output waits for it to close, which must not wait on this.
            let nothing = std::fs::OpenOptions::new()
                .read(true)
                .write(true)
                .open("/dev/null")?;
            for fd in 0..3 {
                // SAFETY: dup2 onto the standard descriptors.
                unsafe { libc::dup2(nothing.as_raw_fd(), fd) };
            }
            drop(nothing);
            tracer.serve()?;
        }
        Ok(())
    }));
    let code = match done {
        Ok(Ok(())) => 0,
        Ok(Err(why)) => {
            complain(&format!("hmz internal cred: {why}\n"));
            1
        }
        Err(_) => 1,
    };
    tracer.close();
    // SAFETY: leaves the forked child.
    unsafe { libc::_exit(code) }
}

// ---------------------------------------------------------------------------------------------
// The probe.

/// What [`supervises`] last answered in this process, and when.
static SUPERVISES: Mutex<Option<(bool, Instant)>> = Mutex::new(None);

/// How long a no is taken as the answer before the kernel is asked again (`_AGAIN`).
const AGAIN: Duration = Duration::from_secs(60);

/// How long the probe may take (`timeout=60`).
const PATIENCE: Duration = Duration::from_secs(60);

/// Whether a turn can be supervised on this machine (`redirect.supervises`): asked by running
/// `true` under the tracer, which only a kernel that hands this process a tracee answers yes
/// to. A yes is kept for the life of the process, a no for a minute.
pub fn supervises() -> bool {
    let mut last = SUPERVISES
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    if let Some((said, when)) = *last
        && (said || when.elapsed() < AGAIN)
    {
        return said;
    }
    let answer = probe().unwrap_or(false);
    *last = Some((answer, Instant::now()));
    answer
}

/// Runs `true` (or, on a machine without one, this program's `--version`) under the tracer,
/// from `/`, which is there whatever this process stands in.
fn probe() -> io::Result<bool> {
    let me = std::env::current_exe()?;
    let nothing = std::env::var_os("PATH").and_then(|path| {
        std::env::split_paths(&path)
            .map(|dir| dir.join("true"))
            .find(|at| at.is_file())
    });
    let mut line = std::process::Command::new(&me);
    line.args([
        "internal",
        "cred",
        "--map=/nonexistent/hmz-probe=/nonexistent/hmz-probed",
        "--",
    ]);
    match nothing {
        Some(at) => line.arg(at),
        None => line.arg(&me).arg("--version"),
    };
    let mut child = line
        .current_dir("/")
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()?;
    let began = Instant::now();
    loop {
        if let Some(status) = child.try_wait()? {
            return Ok(status.success());
        }
        if began.elapsed() > PATIENCE {
            let _ = child.kill();
            let _ = child.wait();
            return Ok(false);
        }
        std::thread::sleep(Duration::from_millis(10));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cog::pathcalls::PathArg;

    fn swaps(pairs: &[(&str, &str)], kept: &[(&str, &str)]) -> Swaps {
        let owned = |of: &[(&str, &str)]| -> Vec<(String, String)> {
            of.iter()
                .map(|(a, b)| ((*a).to_owned(), (*b).to_owned()))
                .collect()
        };
        Swaps::of(owned(pairs), owned(kept))
    }

    fn strings(of: &[&str]) -> Vec<String> {
        of.iter().map(|one| (*one).to_owned()).collect()
    }

    const ARGS: &[PathArg] = &[PathArg {
        path: 0,
        dirfd: None,
    }];

    fn call(name: &'static str, looks: bool, makes: bool) -> PathCall {
        PathCall {
            name,
            args: ARGS,
            looks,
            makes,
        }
    }

    #[test]
    fn an_empty_table_points_nothing_anywhere() {
        assert!(swaps(&[], &[]).is_empty());
        assert!(!swaps(&[], &[("/a", "/b")]).is_empty());
    }

    #[test]
    fn a_table_is_tidied_and_longest_first() {
        let held = swaps(
            &[("/a/", "/x"), ("/a//b/c", "/y/./z"), ("", "/n"), ("/m", "")],
            &[],
        );

        assert_eq!(
            held.pairs,
            vec![("/a/b/c".into(), "/y/z".into()), ("/a".into(), "/x".into())]
        );
    }

    #[test]
    fn swaps_named_on_a_command_line_are_read_back() {
        let held = Swaps::read(&strings(&["/a=/b", "/c/d=/e"]), &strings(&["/s=/t"])).unwrap();

        assert_eq!(
            held,
            swaps(&[("/a", "/b"), ("/c/d", "/e")], &[("/s", "/t")])
        );
        // Split at the first `=`, so a target may hold one.
        let held = Swaps::read(&strings(&["/a=/b=c"]), &[]).unwrap();
        assert_eq!(held.pairs, vec![("/a".into(), "/b=c".into())]);
    }

    #[test]
    fn a_swap_that_is_not_two_absolute_paths_is_refused() {
        for said in ["/a", "a=/b", "/a=b", "=/b"] {
            let why = Swaps::read(&strings(&[said]), &[]).unwrap_err();
            assert!(why.contains("not FROM=TO"), "{said}: {why}");
            assert!(Swaps::read(&[], &strings(&[said])).is_err());
        }
    }

    #[test]
    fn the_credentials_lent_are_what_the_pairs_answer_with() {
        let held = swaps(&[("/h/a", "/p/a")], &[("/h/s", "/r/s")]);

        assert_eq!(held.credentials(), vec![PathBuf::from("/p/a")]);
    }

    // `Swaps::answer` reads each entry with `policy::answered`, which unit 8 fills in.
    #[test]
    #[ignore = "needs unit 8 (policy::answered)"]
    fn a_file_a_directory_and_a_rotated_file_are_answered() {
        let held = swaps(
            &[
                ("/h/.codex/auth.json", "/p/auth.json"),
                ("/h/.kimi/creds", "/p/creds"),
            ],
            &[],
        );
        for (path, answer) in [
            ("/h/.codex/auth.json", Some("/p/auth.json")),
            ("/h/.codex/auth.json.tmp", Some("/p/auth.json.tmp")),
            ("/h/.codex/auth.jsonx", None),
            ("/h/.kimi/creds/one", Some("/p/creds/one")),
            ("/h/.kimi/creds", Some("/p/creds")),
            ("/h/.kimi/credsx", None),
            ("/elsewhere", None),
        ] {
            assert_eq!(
                held.answer(path).map(|(found, _)| found).as_deref(),
                answer,
                "{path}"
            );
        }
    }

    #[test]
    #[ignore = "needs unit 8 (policy::answered)"]
    fn a_pattern_answers_every_path_its_names_match() {
        let held = swaps(&[("/h/state_*.sqlite", "/p/state_*.sqlite")], &[]);
        let swap = |path: &str| held.answer(path).map(|(found, _)| found);

        assert_eq!(
            swap("/h/state_5.sqlite").as_deref(),
            Some("/p/state_5.sqlite")
        );
        assert_eq!(
            swap("/h/state_5.sqlite/wal").as_deref(),
            Some("/p/state_5.sqlite/wal")
        );
        assert_eq!(swap("/h/other.sqlite"), None);
    }

    #[test]
    #[ignore = "needs unit 8 (policy::answered)"]
    fn the_entry_that_says_most_about_a_path_wins_across_both_tables() {
        let held = swaps(
            &[("/h/.claude", "/p/creds")],
            &[("/h/.claude/projects", "/s/projects")],
        );

        assert_eq!(
            held.answer("/h/.claude/projects/a.jsonl"),
            Some(("/s/projects/a.jsonl".into(), true))
        );
        assert_eq!(
            held.answer("/h/.claude/.credentials.json"),
            Some(("/p/creds/.credentials.json".into(), false))
        );
        assert_eq!(held.answer("/nowhere"), None);
    }

    #[test]
    fn normpath_tidies_as_posix_does() {
        for (path, tidy) in [
            ("", "."),
            ("/", "/"),
            ("//", "//"),
            ("///", "/"),
            ("//a//b", "//a/b"),
            ("/a/./b/../c/", "/a/c"),
            ("/..", "/"),
            ("/a/../..", "/"),
            ("a/../..", ".."),
            ("../a", "../a"),
            ("a/.", "a"),
        ] {
            assert_eq!(normpath(path), tidy, "{path}");
        }
    }

    #[test]
    fn a_tidy_absolute_path_outside_the_table_is_theirs() {
        let prefixes = vec![b"/h/.codex/auth.json".to_vec(), b"/h/state_".to_vec()];

        assert!(theirs(b"/usr/lib/libc.so", &prefixes));
        assert!(theirs(b"/proc/self/status", &prefixes));
        assert!(theirs(b"/proc/stat", &prefixes));
        assert!(theirs(b"/proc/12/statm", &prefixes));
        assert!(theirs(b"/a/.hidden/..x", &prefixes));
        // One the table may answer, or whose spelling must be worked out first.
        for maybe in [
            &b"/h/.codex/auth.json"[..],
            b"/h/.codex/auth.json.tmp",
            b"/h/state_5.sqlite",
            b"relative/auth.json",
            b"/a//b",
            b"/a/./b",
            b"/a/../b",
            b"/a/.",
            b"/a/..",
            b"/a/",
            b"/proc/self/fd/3/x",
            b"/proc/thread-self/cwd",
            b"/proc/42/root/etc",
            b"/proc/self/exe",
            b"/proc/self/task/1/fd/3",
            b"/dev/fd/3/.credentials.json",
        ] {
            assert!(
                !theirs(maybe, &prefixes),
                "{}",
                String::from_utf8_lossy(maybe)
            );
        }
    }

    #[test]
    fn what_a_call_does_decides_between_the_copy_and_the_file() {
        let stat = call("stat", true, false);
        let getxattr = call("getxattr", true, false);
        let unlink = call("unlink", false, false);
        let rename = call("rename", false, true);
        let open = call("open", false, false);
        let openat2 = call("openat2", false, false);
        let rdonly = libc::O_RDONLY as u64;

        assert!(!changes(&stat, None) && copyable(&stat));
        assert!(!changes(&getxattr, None) && !copyable(&getxattr));
        assert!(changes(&unlink, None) && !creates(&unlink, None));
        assert!(changes(&rename, None) && creates(&rename, None));
        assert!(!changes(&open, Some(rdonly)) && copyable(&open));
        for writes in [libc::O_WRONLY, libc::O_RDWR, libc::O_TRUNC, libc::O_APPEND] {
            assert!(changes(&open, Some(writes as u64)) && !creates(&open, Some(writes as u64)));
        }
        let creat = (libc::O_CREAT | libc::O_WRONLY) as u64;
        assert!(changes(&open, Some(creat)) && creates(&open, Some(creat)));
        // An `open_how` that could not be read is a write, and not a create.
        assert!(changes(&openat2, None) && !creates(&openat2, None));
    }

    #[test]
    fn a_dev_fd_path_is_resolved_as_the_proc_link_it_is() {
        assert_eq!(unaliased("/dev/fd/3/x".into()), "/proc/self/fd/3/x");
        assert_eq!(unaliased("/dev/null".into()), "/dev/null");
    }

    #[test]
    fn a_path_is_planted_below_the_red_zone() {
        assert_eq!(scratch(0x1000, 128, 16), 0x1000 - 128 - 16);
        assert_eq!(scratch(0x1000, 0, 16), 0x1000 - 16);
    }

    #[test]
    fn a_relative_path_is_joined_to_its_directory() {
        assert_eq!(joined("/a", "b"), "/a/b");
        assert_eq!(joined("/", "b"), "/b");
    }

    #[test]
    fn a_command_line_that_names_nothing_usable_is_a_usage_error() {
        let line = |maps: &[&str], command: &[&str]| CredArgs {
            maps: strings(maps),
            keeps: vec![],
            command: command.iter().map(OsString::from).collect(),
        };
        assert_eq!(main(line(&[], &["--", "true"])), exit::USAGE);
        assert_eq!(main(line(&["relative=/abs"], &["true"])), exit::USAGE);
        assert_eq!(main(line(&["/abs/only"], &["true"])), exit::USAGE);
        assert_eq!(main(line(&["/a=/b"], &["--"])), exit::USAGE);
    }
}

//! What the supervisor does with each trapped syscall. Port of `hmz.coganchor.handlers`.
//! [Unit 10]
//!
//! Every handler sees the tracee at syscall *entry* and returns a [`Verdict`]: `Allow` lets
//! the syscall run natively (reads and lookups, once the mirror has been made to tell the
//! target's truth), `Fail(errno)` cancels it with the target's exact error, `Stall` leaves the
//! process stopped while a remote command stands in for it (`execve` only).
//!
//! Mutating syscalls are replayed on the target *first*, so its errno wins, and then allowed to
//! run locally, which keeps the mirror in step -- unless the agent's fence keeps it from
//! changing its workspace ([`Session::writes`]), when they fail `EACCES` and the target is
//! never asked.
//!
//! The dispatcher reads the tracee through [`Memory`] and the session through [`Session`], so
//! its decisions are tested against fakes; the supervisor gives it the real ones.

use std::collections::HashSet;
use std::ffi::OsString;
use std::io;
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr};
use std::os::unix::ffi::OsStrExt;

use serde_json::Value;

use crate::cog::pathcalls::PathCall;
use crate::meta;
use crate::proto::json::{from_os, to_os};
use crate::proto::{Meta, Op, RemoteError};
use crate::sys::ARCH;

/// What becomes of one stopped syscall.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Verdict {
    /// Let it run as (possibly rewritten) now.
    Allow,
    /// Cancel it, returning `-errno`.
    Fail(i32),
    /// Leave the tracee stopped: a remote command is standing in for it.
    Stall,
}

impl Verdict {
    /// The verdict failing a syscall with `errno`, or `EIO` where it names none (`fails`).
    pub fn fails(errno: i32) -> Verdict {
        Verdict::Fail(if errno == 0 { libc::EIO } else { errno })
    }
}

/// `AT_FDCWD`, `AT_REMOVEDIR`, `AT_SYMLINK_NOFOLLOW`: <linux/fcntl.h>, shared by every
/// architecture.
pub const AT_FDCWD: i32 = -100;
pub const AT_REMOVEDIR: u64 = 0x200;
pub const AT_SYMLINK_NOFOLLOW: u64 = 0x100;

pub const O_WRONLY: u64 = 0o1;
pub const O_RDWR: u64 = 0o2;
pub const O_CREAT: u64 = 0o100;
pub const O_TRUNC: u64 = 0o1000;
pub const O_ACCMODE: u64 = 0o3;

/// The flags `creat` is `open` with.
const CREAT_FLAGS: u64 = O_CREAT | O_WRONLY | O_TRUNC;

/// `struct open_how`: its flags are the first `u64`, its resolution the third.
const OPEN_HOW_FLAGS: usize = 8;
const OPEN_HOW_RESOLVE: usize = 16;
/// `RESOLVE_BENEATH | RESOLVE_IN_ROOT`: resolutions an answered path cannot honour.
const RESOLVE_CONFINED: u64 = 0x08 | 0x10;

/// What of a mode says which kind of file `mknod` makes, and the plain-file kind.
const S_IFMT: u64 = 0o170000;
const S_IFREG: u64 = 0o100000;

/// `UTIME_NOW` and `UTIME_OMIT`, from <linux/stat.h>.
pub const UTIME_NOW: i64 = (1 << 30) - 1;
pub const UTIME_OMIT: i64 = (1 << 30) - 2;

/// The calls that change what of a file the target is never sent (owner, extended
/// attributes), and so need its contents in the mirror first (`_KEEPS`).
const KEEPS: [&str; 7] = [
    "setxattr",
    "lsetxattr",
    "removexattr",
    "lremovexattr",
    "chown",
    "lchown",
    "fchownat",
];

/// The calls with a handler of their own, besides [`PathCall::looks`] and [`KEEPS`].
const HANDLED: [&str; 30] = [
    "execve",
    "execveat",
    "open",
    "openat",
    "openat2",
    "creat",
    "chdir",
    "mkdir",
    "mkdirat",
    "rmdir",
    "unlink",
    "unlinkat",
    "rename",
    "renameat",
    "renameat2",
    "symlink",
    "symlinkat",
    "link",
    "linkat",
    "mknod",
    "mknodat",
    "chmod",
    "fchmodat",
    "fchmodat2",
    "truncate",
    "utimensat",
    "utimes",
    "futimesat",
    "utime",
    "connect",
];

/// One stopped syscall: its name, arguments and stack pointer, with any argument the
/// dispatcher rewrites (`dirty` in the Python).
#[derive(Clone, Debug)]
pub struct Call {
    pub name: &'static str,
    pub args: [u64; 6],
    pub sp: u64,
    /// Whether an argument was changed and the registers must be written back.
    pub changed: bool,
}

impl Call {
    pub fn new(name: &'static str, args: [u64; 6], sp: u64) -> Call {
        Call {
            name,
            args,
            sp,
            changed: false,
        }
    }

    /// Argument `i` as the `int` the kernel reads a descriptor as.
    pub fn fd(&self, i: usize) -> i32 {
        self.args[i] as i32
    }

    pub fn set_arg(&mut self, i: usize, value: u64) {
        self.args[i] = value;
        self.changed = true;
    }
}

/// Where `size` bytes may be written below the tracee's stack pointer, clear of the red zone
/// (`Registers.scratch`).
pub fn scratch(sp: u64, size: usize) -> u64 {
    sp.wrapping_sub(ARCH.red_zone).wrapping_sub(size as u64)
}

/// A stopped tracee, as the dispatcher reads it. Errors carrying `ESRCH` mean it is gone.
pub trait Memory {
    /// The NUL-terminated string at `addr` (never called with 0).
    fn read_cstring(&self, addr: u64) -> io::Result<OsString>;
    fn read_mem(&self, addr: u64, len: usize) -> io::Result<Vec<u8>>;
    fn write_mem(&self, addr: u64, data: &[u8]) -> io::Result<()>;
    /// `procfs::resolve_magic` for this tracee.
    fn resolve_magic(&self, path: &str) -> io::Result<String>;
    fn cwd(&self) -> io::Result<String>;
    fn fd_path(&self, fd: i32) -> io::Result<String>;
}

/// The session a dispatcher answers for: routing, the mirror, the target.
pub trait Session {
    /// Where `name` keeps the paths it names (`pathcalls::find`).
    fn path_call(&self, name: &str) -> Option<&'static PathCall>;
    /// Whether any path can need settling or answering (`router.redirects or router.settles`).
    fn settles(&self) -> bool;
    fn canonical(&self, path: &str) -> String;
    fn swap(&self, path: &str) -> Option<String>;
    /// The path the target knows `path` by, where it is the mirror's; `None` for a local one.
    fn remote(&self, path: &str) -> Option<String>;
    /// Makes the directories an answered path about to be created lives in; false where that
    /// failed, so it is tried again next time.
    fn make_parents(&self, path: &str) -> bool;
    /// False where the fence lets nothing in the workspace be written.
    fn writes(&self) -> bool;
    fn ensure_path(&self, path: &str) -> Result<(), RemoteError>;
    fn ensure_directory(&self, path: &str) -> Result<(), RemoteError>;
    fn ensure_content(&self, path: &str) -> Result<(), RemoteError>;
    fn note_write(&self, path: &str);
    fn note_removed(&self, path: &str);
    fn note_renamed(&self, from: &str, to: &str);
    fn flush(&self) -> Result<(), RemoteError>;
    /// One request to the target.
    fn call(&self, op: Op, request: Meta) -> Result<Meta, RemoteError>;
    /// Where the network proxy sends a connection to `dest`; `None` without a proxy.
    fn redirect(&self, dest: SocketAddr) -> Option<io::Result<Option<SocketAddr>>>;
    /// The time, in nanoseconds since the epoch, `UTIME_NOW` and a null pointer mean.
    fn now_ns(&self) -> i64;
}

/// An `execve` or `execveat` read off the tracee, for the supervisor to decide.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExecAsk {
    /// The program as asked for, absolute and with magic links followed; `None` where it could
    /// not be read (the call is then allowed).
    pub named: Option<String>,
    /// The same, settled onto this machine's spelling.
    pub resolved: Option<String>,
    /// The argument holding the program's path.
    pub path_arg: usize,
    pub argv: u64,
    pub envp: u64,
}

/// What dispatching a call came to.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Outcome {
    Verdict(Verdict),
    /// An exec, which the supervisor runs here or on the target.
    Exec(ExecAsk),
}

/// Why a handler stopped short.
#[derive(Debug)]
enum Halt {
    /// The tracee vanished: let the call go, it no longer matters.
    Gone,
    Errno(i32),
}

impl From<io::Error> for Halt {
    fn from(error: io::Error) -> Halt {
        match error.raw_os_error() {
            Some(libc::ESRCH) => Halt::Gone,
            Some(errno) if errno != 0 => Halt::Errno(errno),
            _ => Halt::Errno(libc::EIO),
        }
    }
}

impl From<RemoteError> for Halt {
    fn from(error: RemoteError) -> Halt {
        Halt::Errno(if error.errno == 0 {
            libc::EIO
        } else {
            error.errno
        })
    }
}

type Step<T> = Result<T, Halt>;

/// How a call that sets times lays out the pair it is given.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Times {
    /// Two `timespec`s (`utimensat`), with the `UTIME_NOW`/`UTIME_OMIT` sentinels.
    Timespec,
    /// Two `timeval`s (`utimes`, `futimesat`): microseconds.
    Timeval,
    /// A `utimbuf` (`utime`): two whole seconds.
    Utimbuf,
}

impl Times {
    /// How many bytes the pair takes.
    pub fn size(self) -> usize {
        match self {
            Times::Utimbuf => 16,
            _ => 32,
        }
    }
}

/// The `(atime, mtime)` in nanoseconds a pair says, `None` for one to leave alone.
/// `raw` is `None` for a null pointer, which means both now (`_read_times`).
pub fn decode_times(shape: Times, raw: Option<&[u8]>, now: i64) -> (Option<i64>, Option<i64>) {
    let Some(raw) = raw else {
        return (Some(now), Some(now));
    };
    if raw.len() < shape.size() {
        return (None, None);
    }
    let word = |i: usize| i64::from_le_bytes(raw[i * 8..i * 8 + 8].try_into().unwrap());
    match shape {
        Times::Utimbuf => (
            Some(word(0).wrapping_mul(1_000_000_000)),
            Some(word(1).wrapping_mul(1_000_000_000)),
        ),
        Times::Timeval => (
            Some(timeval_ns(word(0), word(1))),
            Some(timeval_ns(word(2), word(3))),
        ),
        Times::Timespec => (
            timespec_ns(word(0), word(1), now),
            timespec_ns(word(2), word(3), now),
        ),
    }
}

/// Nanoseconds for one `timeval`; a tracee's nonsense wraps rather than panics.
fn timeval_ns(seconds: i64, microseconds: i64) -> i64 {
    seconds
        .wrapping_mul(1_000_000_000)
        .wrapping_add(microseconds.wrapping_mul(1000))
}

/// Nanoseconds for one `timespec`: `UTIME_OMIT` is `None`, `UTIME_NOW` this machine's clock
/// (the protocol can say "leave it", but not "now").
fn timespec_ns(seconds: i64, nanoseconds: i64, now: i64) -> Option<i64> {
    match nanoseconds {
        UTIME_OMIT => None,
        UTIME_NOW => Some(now),
        _ => Some(
            seconds
                .wrapping_mul(1_000_000_000)
                .wrapping_add(nanoseconds),
        ),
    }
}

/// `os.path.normpath` for a POSIX path.
pub fn normpath(path: &str) -> String {
    if path.is_empty() {
        return ".".into();
    }
    let slashes = if path.starts_with("//") && !path.starts_with("///") {
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
            ".." => {
                if parts.last().is_some_and(|last| *last != "..") {
                    parts.pop();
                } else if slashes == 0 {
                    parts.push("..");
                }
            }
            _ => parts.push(part),
        }
    }
    let joined = format!("{}{}", "/".repeat(slashes), parts.join("/"));
    if joined.is_empty() {
        ".".into()
    } else {
        joined
    }
}

/// `os.path.join(base, path)` for a relative `path`.
fn join(base: &str, path: &str) -> String {
    if path.starts_with('/') {
        path.to_owned()
    } else if base.is_empty() || base.ends_with('/') {
        format!("{base}{path}")
    } else {
        format!("{base}/{path}")
    }
}

/// The parent directory of `path` (`os.path.dirname`).
fn dirname(path: &str) -> &str {
    match path.rfind('/') {
        Some(0) => "/",
        Some(cut) => path[..cut].trim_end_matches('/'),
        None => "",
    }
}

/// Writes `path` into the tracee below its stack pointer, past the `taken` bytes earlier paths
/// of this call used, and points argument `arg` at it (`_plant`). Returns the bytes it took,
/// confirmed by reading them back, or `None` where it could not be written.
pub fn plant(
    memory: &dyn Memory,
    call: &mut Call,
    taken: usize,
    arg: usize,
    path: &str,
) -> Option<usize> {
    let mut blob = to_os(path).as_bytes().to_vec();
    blob.push(0);
    let address = scratch(call.sp, taken + blob.len());
    memory.write_mem(address, &blob).ok()?;
    if memory.read_mem(address, blob.len()).ok()? != blob {
        return None;
    }
    call.set_arg(arg, address);
    Some(blob.len())
}

/// A `connect` destination: the family, as the tracee's socket has it, and where.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Endpoint {
    pub family: i32,
    pub addr: SocketAddr,
}

/// Decodes an IPv4 or IPv6 `sockaddr` read from the tracee (`raw` is its first
/// `min(len, 28)` bytes), ignoring anything else.
pub fn decode_sockaddr(raw: &[u8]) -> Option<Endpoint> {
    if raw.len() < 8 {
        return None;
    }
    let family = i32::from(u16::from_le_bytes([raw[0], raw[1]]));
    let port = u16::from_be_bytes([raw[2], raw[3]]);
    let ip = if family == libc::AF_INET {
        IpAddr::V4(Ipv4Addr::new(raw[4], raw[5], raw[6], raw[7]))
    } else if family == libc::AF_INET6 && raw.len() >= 24 {
        let octets: [u8; 16] = raw[8..24].try_into().unwrap();
        IpAddr::V6(Ipv6Addr::from(octets))
    } else {
        return None;
    };
    Some(Endpoint {
        family,
        addr: SocketAddr::new(ip, port),
    })
}

/// A replacement `sockaddr` in the family the tracee's socket already has: an `AF_INET6`
/// socket handed a `sockaddr_in` fails `EINVAL`. `None` where the address cannot be said in
/// that family.
pub fn encode_sockaddr(family: i32, addr: SocketAddr) -> Option<Vec<u8>> {
    let mut blob = Vec::with_capacity(28);
    if family == libc::AF_INET6 {
        let ip = match addr.ip() {
            IpAddr::V6(ip) => ip,
            IpAddr::V4(ip) => ip.to_ipv6_mapped(),
        };
        blob.extend_from_slice(&(libc::AF_INET6 as u16).to_le_bytes());
        blob.extend_from_slice(&addr.port().to_be_bytes());
        blob.extend_from_slice(&[0; 4]); // sin6_flowinfo
        blob.extend_from_slice(&ip.octets());
        blob.extend_from_slice(&[0; 4]); // sin6_scope_id
    } else {
        let ip = match addr.ip() {
            IpAddr::V4(ip) => ip,
            IpAddr::V6(ip) => ip.to_ipv4_mapped()?,
        };
        blob.extend_from_slice(&(libc::AF_INET as u16).to_le_bytes());
        blob.extend_from_slice(&addr.port().to_be_bytes());
        blob.extend_from_slice(&ip.octets());
        blob.extend_from_slice(&[0; 8]); // sin_zero
    }
    Some(blob)
}

/// Routes each trapped syscall to its handler (`SyscallDispatcher`).
#[derive(Default)]
pub struct Dispatcher {
    /// The directories answered paths have been given, so making sure of one is a lookup.
    made: HashSet<String>,
}

impl Dispatcher {
    pub fn new() -> Dispatcher {
        Dispatcher::default()
    }

    /// Whether `name`, whose path table is `table`, has a handler at all; a call without one
    /// is allowed unread.
    fn handles(name: &str, table: Option<&PathCall>) -> bool {
        table.is_some_and(|call| call.looks) || HANDLED.contains(&name) || KEEPS.contains(&name)
    }

    /// What to do with `call`, stopped at its seccomp stop in the tracee `memory` reads.
    pub fn dispatch(
        &mut self,
        memory: &dyn Memory,
        session: &dyn Session,
        call: &mut Call,
    ) -> Outcome {
        // Looked up once: this is on the way into every trapped syscall.
        let table = session.path_call(call.name);
        if !Dispatcher::handles(call.name, table) {
            return Outcome::Verdict(Verdict::Allow);
        }
        let result = match self.answer(memory, session, table, call) {
            Ok(Some(verdict)) => Ok(Outcome::Verdict(verdict)),
            Ok(None) => Handler {
                memory,
                session,
                table,
            }
            .handle(call),
            Err(halt) => Err(halt),
        };
        match result {
            Ok(outcome) => outcome,
            Err(Halt::Gone) => Outcome::Verdict(Verdict::Allow),
            Err(Halt::Errno(errno)) => {
                tracing::debug!("{} failed: errno {errno}", call.name);
                Outcome::Verdict(Verdict::fails(errno))
            }
        }
    }

    /// Points a call's paths at what this machine will really touch (`_answer`): a path a
    /// redirect answers with another, and a spelling only the target has settled onto this
    /// machine's. A redirect that cannot be planted fails the call `EIO`; a spelling that
    /// cannot is left as the tracee wrote it.
    fn answer(
        &mut self,
        memory: &dyn Memory,
        session: &dyn Session,
        table: Option<&PathCall>,
        call: &mut Call,
    ) -> Step<Option<Verdict>> {
        let Some(table) = table else {
            return Ok(None);
        };
        if table.args.is_empty() || !session.settles() {
            return Ok(None);
        }
        let mut taken = 0;
        for arg in table.args {
            let dirfd = arg.dirfd.map_or(AT_FDCWD, |i| call.fd(i));
            let Some(named) = raw(memory, dirfd, call.args[arg.path])? else {
                continue;
            };
            let settled = session.canonical(&named);
            let answered = session.swap(&settled);
            let instead = answered.clone().unwrap_or(settled);
            if instead == named {
                continue;
            }
            if let Some(answered) = &answered
                && creates(memory, table, call)
            {
                let parent = dirname(answered).to_owned();
                if !self.made.contains(&parent) && session.make_parents(answered) {
                    self.made.insert(parent);
                }
            }
            if confined(memory, call) {
                if answered.is_none() {
                    continue;
                }
                tracing::warn!(
                    "openat2 insisted on a resolution {instead} cannot be given; failing it"
                );
                return Ok(Some(Verdict::Fail(libc::EIO)));
            }
            match plant(memory, call, taken, arg.path, &instead) {
                Some(room) => taken += room,
                None if answered.is_none() => continue,
                None => {
                    tracing::warn!("{} could not be given {instead}; failing it", call.name);
                    return Ok(Some(Verdict::Fail(libc::EIO)));
                }
            }
        }
        Ok(None)
    }
}

/// Whether a stopped call may make something at a path it names (`_creates`).
fn creates(memory: &dyn Memory, table: &PathCall, call: &Call) -> bool {
    if table.makes {
        return true;
    }
    match call.name {
        "open" => call.args[1] & O_CREAT != 0,
        "openat" => call.args[2] & O_CREAT != 0,
        "openat2" => memory
            .read_mem(call.args[2], OPEN_HOW_FLAGS)
            .ok()
            .and_then(|raw| raw.try_into().ok().map(u64::from_le_bytes))
            .is_some_and(|flags| flags & O_CREAT != 0),
        _ => false,
    }
}

/// Whether an `openat2` asked for a resolution an answered path cannot be given.
fn confined(memory: &dyn Memory, call: &Call) -> bool {
    if call.name != "openat2" {
        return false;
    }
    memory
        .read_mem(call.args[2], OPEN_HOW_RESOLVE + 8)
        .ok()
        .and_then(|raw| {
            raw.get(OPEN_HOW_RESOLVE..OPEN_HOW_RESOLVE + 8)
                .map(|w| u64::from_le_bytes(w.try_into().unwrap()))
        })
        .is_some_and(|resolve| resolve & RESOLVE_CONFINED != 0)
}

/// The string at `addr`, `None` for a null pointer or one that cannot be read.
fn cstring(memory: &dyn Memory, addr: u64) -> Option<String> {
    if addr == 0 {
        return None;
    }
    memory.read_cstring(addr).ok().map(|s| from_os(&s))
}

/// What descriptor `fd` names, where it is a path (`_fd_path`).
fn fd_path(memory: &dyn Memory, fd: i32) -> Option<String> {
    memory.fd_path(fd).ok().filter(|p| p.starts_with('/'))
}

/// The path a syscall argument names, as the tracee spelled it but with `/proc` magic links
/// followed (`_raw`): an empty path is the descriptor's own file, a relative one is joined to
/// the working directory or the descriptor's, and `..` is collapsed only after links are
/// followed. An unresolvable magic link fails the call.
fn raw(memory: &dyn Memory, dirfd: i32, addr: u64) -> Step<Option<String>> {
    let Some(said) = cstring(memory, addr) else {
        return Ok(None);
    };
    if said.is_empty() {
        return Ok(if dirfd == AT_FDCWD {
            None
        } else {
            fd_path(memory, dirfd)
        });
    }
    let named = if said.starts_with('/') {
        said
    } else {
        let base = if dirfd == AT_FDCWD {
            Some(memory.cwd()?)
        } else {
            fd_path(memory, dirfd)
        };
        let Some(base) = base else {
            return Ok(None);
        };
        join(&base, &said)
    };
    Ok(Some(normpath(&memory.resolve_magic(&named)?)))
}

/// `renameat2`'s `RENAME_NOREPLACE`, which the target's `rename` can honour (`replace`).
const RENAME_NOREPLACE: u64 = 1;

/// Which two-path mutation [`Handler::relate`] replays.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Relate {
    Link,
    /// A rename, with `renameat2`'s flags.
    Rename(u64),
}

/// The handlers proper, over one tracee and one session.
struct Handler<'a> {
    memory: &'a dyn Memory,
    session: &'a dyn Session,
    /// The call's entry in the path table.
    table: Option<&'a PathCall>,
}

impl Handler<'_> {
    fn handle(&self, call: &mut Call) -> Step<Outcome> {
        let a = call.args;
        let cwd = AT_FDCWD;
        let verdict = match call.name {
            "execve" => return Ok(Outcome::Exec(self.exec(call, None, 0, a[1], a[2])?)),
            "execveat" => {
                return Ok(Outcome::Exec(self.exec(
                    call,
                    Some(call.fd(0)),
                    1,
                    a[2],
                    a[3],
                )?));
            }
            "open" => self.prepare_open(self.path(cwd, a[0])?, a[1])?,
            "openat" => self.prepare_open(self.path(call.fd(0), a[1])?, a[2])?,
            "openat2" => {
                let path = self.path(call.fd(0), a[1])?;
                let raw = self.memory.read_mem(a[2], OPEN_HOW_FLAGS)?;
                let flags = raw.try_into().map(u64::from_le_bytes).unwrap_or(0);
                self.prepare_open(path, flags)?
            }
            "creat" => self.prepare_open(self.path(cwd, a[0])?, CREAT_FLAGS)?,
            "chdir" => {
                if let Some(path) = self.path(cwd, a[0])?
                    && self.session.remote(&path).is_some()
                {
                    self.session.ensure_directory(&path)?;
                }
                Verdict::Allow
            }
            "mkdir" => self.make_dir(self.path(cwd, a[0])?, a[1])?,
            "mkdirat" => self.make_dir(self.path(call.fd(0), a[1])?, a[2])?,
            "rmdir" => self.remove(self.path(cwd, a[0])?, true)?,
            "unlink" => self.remove(self.path(cwd, a[0])?, false)?,
            "unlinkat" => self.remove(self.path(call.fd(0), a[1])?, a[2] & AT_REMOVEDIR != 0)?,
            "rename" => self.relate(
                self.path(cwd, a[0])?,
                self.path(cwd, a[1])?,
                Relate::Rename(0),
            )?,
            "renameat" => self.relate(
                self.path(call.fd(0), a[1])?,
                self.path(call.fd(2), a[3])?,
                Relate::Rename(0),
            )?,
            "renameat2" => self.relate(
                self.path(call.fd(0), a[1])?,
                self.path(call.fd(2), a[3])?,
                Relate::Rename(a[4]),
            )?,
            "link" => self.relate(self.path(cwd, a[0])?, self.path(cwd, a[1])?, Relate::Link)?,
            "linkat" => self.relate(
                self.path(call.fd(0), a[1])?,
                self.path(call.fd(2), a[3])?,
                Relate::Link,
            )?,
            "symlink" => self.make_symlink(cstring(self.memory, a[0]), self.path(cwd, a[1])?)?,
            "symlinkat" => {
                self.make_symlink(cstring(self.memory, a[0]), self.path(call.fd(1), a[2])?)?
            }
            "mknod" => self.make_node(self.path(cwd, a[0])?, a[1])?,
            "mknodat" => self.make_node(self.path(call.fd(0), a[1])?, a[2])?,
            "chmod" => self.change_mode(self.path(cwd, a[0])?, a[1])?,
            "fchmodat" => self.change_mode(self.path(call.fd(0), a[1])?, a[2])?,
            "fchmodat2" => self.fchmodat2(call)?,
            "truncate" => self.truncate(self.path(cwd, a[0])?)?,
            "utimensat" => self.timing(call, Some(0), 1, 2, Times::Timespec)?,
            "utimes" => self.timing(call, None, 0, 1, Times::Timeval)?,
            "futimesat" => self.timing(call, Some(0), 1, 2, Times::Timeval)?,
            "utime" => self.timing(call, None, 0, 1, Times::Utimbuf)?,
            "connect" => self.connect(call)?,
            name => {
                // A lookup, or one of the calls whose change stays in the mirror.
                let Some(table) = self.table else {
                    return Ok(Outcome::Verdict(Verdict::Allow));
                };
                let Some(first) = table.args.first() else {
                    return Ok(Outcome::Verdict(Verdict::Allow));
                };
                let dirfd = first.dirfd.map_or(cwd, |i| call.fd(i));
                let path = self.path(dirfd, a[first.path])?;
                if KEEPS.contains(&name)
                    && let Some(path) = &path
                    && self.session.remote(path).is_some()
                {
                    self.session.ensure_content(path)?;
                }
                self.peek(path.as_deref())?
            }
        };
        Ok(Outcome::Verdict(verdict))
    }

    /// The path an argument names, as this machine spells it (`_path`).
    fn path(&self, dirfd: i32, addr: u64) -> Step<Option<String>> {
        Ok(raw(self.memory, dirfd, addr)?.map(|p| self.session.canonical(&p)))
    }

    /// The target's name for a path already known to be the mirror's.
    fn virtual_path(&self, path: &str) -> String {
        self.session.remote(path).unwrap_or_else(|| path.to_owned())
    }

    fn is_remote(&self, path: &Option<String>) -> Option<String> {
        path.as_deref()
            .filter(|p| self.session.remote(p).is_some())
            .map(str::to_owned)
    }

    fn peek(&self, path: Option<&str>) -> Step<Verdict> {
        if let Some(path) = path
            && self.session.remote(path).is_some()
        {
            self.session.ensure_path(path)?;
        }
        Ok(Verdict::Allow)
    }

    /// Makes a local `open` of a mirror path behave as one on the target would.
    fn prepare_open(&self, path: Option<String>, flags: u64) -> Step<Verdict> {
        let Some(path) = self.is_remote(&path) else {
            return Ok(Verdict::Allow);
        };
        let shadow = self.session;
        shadow.ensure_path(&path)?;
        if flags & ARCH.o_directory as u64 != 0 {
            shadow.ensure_directory(&path)?;
            return Ok(Verdict::Allow);
        }
        let writable = flags & (O_WRONLY | O_RDWR | O_CREAT) != 0;
        // A truncating write never needs the old bytes; everything else does.
        if !(flags & O_TRUNC != 0 && flags & O_ACCMODE == O_WRONLY) {
            shadow.ensure_content(&path)?;
        }
        if writable && shadow.writes() {
            // Where the workspace may not be written, the wall refuses the open itself.
            shadow.note_write(&path);
        }
        Ok(Verdict::Allow)
    }

    /// Performs a mutation on the target, its errno the syscall's (`_replay`).
    fn replay(&self, op: Op, request: Meta) -> Verdict {
        let done = self
            .session
            .flush()
            .and_then(|()| self.session.call(op, request));
        match done {
            Ok(_) => Verdict::Allow,
            Err(error) => Verdict::fails(error.errno),
        }
    }

    fn make_dir(&self, path: Option<String>, mode: u64) -> Step<Verdict> {
        let Some(path) = self.is_remote(&path) else {
            return Ok(Verdict::Allow);
        };
        if !self.session.writes() {
            return Ok(Verdict::Fail(libc::EACCES));
        }
        self.session.ensure_path(&path)?;
        let request = meta! {
            "path" => self.virtual_path(&path),
            "mode" => mode & 0o7777,
            "parents" => false,
        };
        Ok(self.replay(Op::Mkdir, request))
    }

    fn remove(&self, path: Option<String>, is_dir: bool) -> Step<Verdict> {
        let Some(path) = self.is_remote(&path) else {
            return Ok(Verdict::Allow);
        };
        if !self.session.writes() {
            return Ok(Verdict::Fail(libc::EACCES));
        }
        self.session.ensure_path(&path)?;
        let op = if is_dir { Op::Rmdir } else { Op::Unlink };
        let verdict = self.replay(op, meta! {"path" => self.virtual_path(&path)});
        if verdict == Verdict::Allow {
            self.session.note_removed(&path);
        }
        Ok(verdict)
    }

    /// Replays a two-path mutation (`rename`, `link`) on the target, then mirrors it.
    fn relate(&self, source: Option<String>, target: Option<String>, how: Relate) -> Step<Verdict> {
        let (Some(source), Some(target)) = (source, target) else {
            return Ok(Verdict::Allow);
        };
        let (from, to) = (self.session.remote(&source), self.session.remote(&target));
        let (from, to) = match (from, to) {
            (None, None) => return Ok(Verdict::Allow),
            (Some(from), Some(to)) => (from, to),
            // Crossing the boundary would need a copy: refused as a cross-device rename is,
            // so callers fall back.
            _ => return Ok(Verdict::Fail(libc::EXDEV)),
        };
        if !self.session.writes() {
            return Ok(Verdict::Fail(libc::EACCES));
        }
        let flags = match how {
            Relate::Rename(flags) if flags & !RENAME_NOREPLACE != 0 => {
                // An exchange or a whiteout has no `RENAME` to be replayed as; refused as a
                // filesystem without them refuses, so callers fall back.
                return Ok(Verdict::Fail(libc::EINVAL));
            }
            Relate::Rename(flags) => flags,
            Relate::Link => 0,
        };
        self.session.ensure_path(&source)?;
        self.session.ensure_path(&target)?;
        if how == Relate::Link {
            // The mirror cannot yet record a second name for a placeholder (`duplicate`), so
            // the first name's content is made real before the link shares it. Best effort:
            // what the target says of the link is the syscall's answer.
            let _ = self.session.ensure_content(&source);
            return Ok(self.replay(Op::Link, meta! {"src" => from, "dst" => to}));
        }
        let replace = flags & RENAME_NOREPLACE == 0;
        let verdict = self.replay(
            Op::Rename,
            meta! {"src" => from, "dst" => to, "replace" => replace},
        );
        if verdict == Verdict::Allow {
            self.session.note_renamed(&source, &target);
        }
        Ok(verdict)
    }

    fn make_symlink(&self, target: Option<String>, path: Option<String>) -> Step<Verdict> {
        let (Some(target), Some(path)) = (target, self.is_remote(&path)) else {
            return Ok(Verdict::Allow);
        };
        if !self.session.writes() {
            return Ok(Verdict::Fail(libc::EACCES));
        }
        self.session.ensure_path(&path)?;
        Ok(self.replay(
            Op::Symlink,
            meta! {"target" => target, "path" => self.virtual_path(&path)},
        ))
    }

    /// `fchmodat` with flags: Linux keeps no mode on a link, so a `NOFOLLOW` on one is left
    /// to the kernel (`EOPNOTSUPP`) rather than replayed through the link on the target.
    fn fchmodat2(&self, call: &Call) -> Step<Verdict> {
        let path = self.path(call.fd(0), call.args[1])?;
        if let Some(path) = &path
            && call.args[3] & AT_SYMLINK_NOFOLLOW != 0
        {
            self.peek(Some(path))?;
            if std::fs::symlink_metadata(to_os(path)).is_ok_and(|m| m.file_type().is_symlink()) {
                return Ok(Verdict::Allow);
            }
        }
        self.change_mode(path, call.args[2])
    }

    /// Makes room for a node; a plain file reaches the target with the next flush, while a
    /// pipe, socket or device stays in the mirror.
    fn make_node(&self, path: Option<String>, mode: u64) -> Step<Verdict> {
        let Some(path) = self.is_remote(&path) else {
            return Ok(Verdict::Allow);
        };
        if !self.session.writes() {
            return Ok(Verdict::Fail(libc::EACCES));
        }
        self.session.ensure_path(&path)?;
        if matches!(mode & S_IFMT, 0 | S_IFREG) {
            self.session.note_write(&path);
        }
        Ok(Verdict::Allow)
    }

    fn change_mode(&self, path: Option<String>, mode: u64) -> Step<Verdict> {
        let Some(path) = self.is_remote(&path) else {
            return Ok(Verdict::Allow);
        };
        if !self.session.writes() {
            return Ok(Verdict::Fail(libc::EACCES));
        }
        self.session.ensure_path(&path)?;
        Ok(self.replay(
            Op::Chmod,
            meta! {"path" => self.virtual_path(&path), "mode" => mode & 0o7777},
        ))
    }

    /// Truncation reshapes local content, which the next flush pushes: no call of its own.
    fn truncate(&self, path: Option<String>) -> Step<Verdict> {
        let Some(path) = self.is_remote(&path) else {
            return Ok(Verdict::Allow);
        };
        if !self.session.writes() {
            return Ok(Verdict::Fail(libc::EACCES));
        }
        self.session.ensure_content(&path)?;
        self.session.note_write(&path);
        Ok(Verdict::Allow)
    }

    /// One of the calls setting a file's times, replayed on the target.
    fn timing(
        &self,
        call: &Call,
        descriptor: Option<usize>,
        argument: usize,
        given: usize,
        shape: Times,
    ) -> Step<Verdict> {
        let dirfd = descriptor.map_or(AT_FDCWD, |i| call.fd(i));
        let address = call.args[argument];
        // No path at all is the descriptor's own file: `futimens(fd)` is `utimensat(fd, NULL)`.
        let path = if address != 0 || dirfd == AT_FDCWD {
            self.path(dirfd, address)?
        } else {
            fd_path(self.memory, dirfd)
        };
        let Some(path) = self.is_remote(&path) else {
            return Ok(Verdict::Allow);
        };
        let pointer = call.args[given];
        let raw = if pointer == 0 {
            None
        } else {
            Some(self.memory.read_mem(pointer, shape.size())?)
        };
        let (atime, mtime) = decode_times(shape, raw.as_deref(), self.session.now_ns());
        if atime.is_none() && mtime.is_none() {
            return Ok(Verdict::Allow); // both omitted: no change at all
        }
        if !self.session.writes() {
            return Ok(Verdict::Fail(libc::EACCES));
        }
        self.session.ensure_path(&path)?;
        let request = meta! {
            "path" => self.virtual_path(&path),
            "atime_ns" => atime.map_or(Value::Null, Value::from),
            "mtime_ns" => mtime.map_or(Value::Null, Value::from),
        };
        Ok(self.replay(Op::Utime, request))
    }

    /// Points a `connect` the network proxy takes at its loopback listener, in place.
    fn connect(&self, call: &mut Call) -> Step<Verdict> {
        let (address, length) = (call.args[1], call.args[2]);
        if address == 0 || length < 8 {
            return Ok(Verdict::Allow);
        }
        let Ok(raw) = self.memory.read_mem(address, length.min(28) as usize) else {
            return Ok(Verdict::Allow);
        };
        let Some(endpoint) = decode_sockaddr(&raw) else {
            return Ok(Verdict::Allow);
        };
        let Some(redirected) = self.session.redirect(endpoint.addr) else {
            return Ok(Verdict::Allow);
        };
        let Some(instead) = redirected? else {
            return Ok(Verdict::Allow);
        };
        let Some(blob) = encode_sockaddr(endpoint.family, instead) else {
            return Ok(Verdict::Allow);
        };
        if self.memory.write_mem(address, &blob).is_err() {
            return Ok(Verdict::Allow);
        }
        call.set_arg(2, blob.len() as u64);
        Ok(Verdict::Allow)
    }

    /// Reads an exec's program: absolute, magic links followed, tidied, then settled.
    fn exec(
        &self,
        call: &Call,
        dirfd: Option<i32>,
        path_arg: usize,
        argv: u64,
        envp: u64,
    ) -> Step<ExecAsk> {
        let program = match dirfd {
            None => cstring(self.memory, call.args[0]),
            Some(dirfd) => raw(self.memory, dirfd, call.args[1])?,
        };
        let named = match program {
            None => None,
            Some(program) => {
                let joined = if program.starts_with('/') {
                    program
                } else {
                    join(&self.memory.cwd()?, &program)
                };
                Some(normpath(&self.memory.resolve_magic(&joined)?))
            }
        };
        let resolved = named.as_deref().map(|n| self.session.canonical(n));
        Ok(ExecAsk {
            named,
            resolved,
            path_arg,
            argv,
            envp,
        })
    }
}

#[cfg(test)]
mod tests {
    use std::cell::RefCell;
    use std::collections::HashMap;

    use super::*;
    use crate::cog::pathcalls::PathArg;

    const ONE: &[PathArg] = &[PathArg {
        path: 1,
        dirfd: Some(0),
    }];
    const ZERO: &[PathArg] = &[PathArg {
        path: 0,
        dirfd: None,
    }];
    const TWO: &[PathArg] = &[
        PathArg {
            path: 1,
            dirfd: Some(0),
        },
        PathArg {
            path: 3,
            dirfd: Some(2),
        },
    ];

    fn entry(name: &'static str, args: &'static [PathArg], looks: bool, makes: bool) -> PathCall {
        PathCall {
            name,
            args,
            looks,
            makes,
        }
    }

    static TABLE: std::sync::LazyLock<Vec<PathCall>> = std::sync::LazyLock::new(|| {
        vec![
            entry("openat", ONE, false, false),
            entry("openat2", ONE, false, false),
            entry("mkdirat", ONE, false, true),
            entry("unlinkat", ONE, false, false),
            entry("renameat2", TWO, false, true),
            entry("linkat", TWO, false, true),
            entry(
                "symlinkat",
                &[PathArg {
                    path: 2,
                    dirfd: Some(1),
                }],
                false,
                true,
            ),
            entry("fchmodat", ONE, false, false),
            entry("utimensat", ONE, false, false),
            entry("truncate", ZERO, false, false),
            entry("mknodat", ONE, false, true),
            entry("newfstatat", ONE, true, false),
            entry("fchownat", ONE, false, false),
        ]
    });

    /// The tracee's strings and bytes, by address; its working directory is `/m/cwd`.
    #[derive(Default)]
    struct Fake {
        strings: HashMap<u64, String>,
        bytes: RefCell<HashMap<u64, Vec<u8>>>,
        gone: bool,
    }

    impl Memory for Fake {
        fn read_cstring(&self, addr: u64) -> io::Result<OsString> {
            if self.gone {
                return Err(io::Error::from_raw_os_error(libc::ESRCH));
            }
            if let Some(s) = self.strings.get(&addr) {
                return Ok(s.into());
            }
            let held = self.bytes.borrow();
            let blob = held
                .get(&addr)
                .ok_or(io::Error::from_raw_os_error(libc::EFAULT))?;
            let end = blob.iter().position(|b| *b == 0).unwrap_or(blob.len());
            Ok(OsString::from(
                String::from_utf8(blob[..end].to_vec()).unwrap(),
            ))
        }
        fn read_mem(&self, addr: u64, len: usize) -> io::Result<Vec<u8>> {
            let held = self.bytes.borrow();
            let blob = held
                .get(&addr)
                .ok_or(io::Error::from_raw_os_error(libc::EFAULT))?;
            Ok(blob[..len.min(blob.len())].to_vec())
        }
        fn write_mem(&self, addr: u64, data: &[u8]) -> io::Result<()> {
            self.bytes.borrow_mut().insert(addr, data.to_vec());
            Ok(())
        }
        fn resolve_magic(&self, path: &str) -> io::Result<String> {
            if path.starts_with("/proc/self/fd/9") {
                return Err(io::Error::from_raw_os_error(libc::EBADF));
            }
            Ok(path.to_owned())
        }
        fn cwd(&self) -> io::Result<String> {
            Ok("/m/cwd".into())
        }
        fn fd_path(&self, fd: i32) -> io::Result<String> {
            Ok(format!("/m/fd{fd}"))
        }
    }

    /// Everything under `/m` is the target's `/v`; records every call, failing those in
    /// `fails`.
    #[derive(Default)]
    struct World {
        calls: RefCell<Vec<(String, String)>>,
        fails: HashMap<&'static str, i32>,
        readonly: bool,
        settles: bool,
        redirects: Vec<(String, String)>,
        net: Option<SocketAddr>,
    }

    impl World {
        fn note(&self, what: &str, detail: impl Into<String>) {
            self.calls.borrow_mut().push((what.into(), detail.into()));
        }
        fn named(&self) -> Vec<String> {
            self.calls.borrow().iter().map(|(n, _)| n.clone()).collect()
        }
        fn remote_calls(&self) -> Vec<(String, String)> {
            self.calls
                .borrow()
                .iter()
                .filter(|(n, _)| n.starts_with("rpc:"))
                .cloned()
                .collect()
        }
        fn shadow(&self, what: &str, path: &str) -> Result<(), RemoteError> {
            self.note(what, path);
            Ok(())
        }
    }

    impl Session for World {
        fn path_call(&self, name: &str) -> Option<&'static PathCall> {
            TABLE.iter().find(|c| c.name == name)
        }
        fn settles(&self) -> bool {
            self.settles || !self.redirects.is_empty()
        }
        fn canonical(&self, path: &str) -> String {
            match path.strip_prefix("/M/") {
                Some(rest) => format!("/m/{rest}"),
                None => path.to_owned(),
            }
        }
        fn swap(&self, path: &str) -> Option<String> {
            self.redirects
                .iter()
                .find(|(from, _)| from == path)
                .map(|(_, to)| to.clone())
        }
        fn remote(&self, path: &str) -> Option<String> {
            if path == "/m" || path.starts_with("/m/") {
                Some(format!("/v{}", &path[2..]))
            } else {
                None
            }
        }
        fn make_parents(&self, path: &str) -> bool {
            self.note("parents", path);
            true
        }
        fn writes(&self) -> bool {
            !self.readonly
        }
        fn ensure_path(&self, path: &str) -> Result<(), RemoteError> {
            self.shadow("ensure_path", path)
        }
        fn ensure_directory(&self, path: &str) -> Result<(), RemoteError> {
            self.shadow("ensure_directory", path)
        }
        fn ensure_content(&self, path: &str) -> Result<(), RemoteError> {
            self.shadow("ensure_content", path)
        }
        fn note_write(&self, path: &str) {
            self.note("note_write", path);
        }
        fn note_removed(&self, path: &str) {
            self.note("note_removed", path);
        }
        fn note_renamed(&self, from: &str, to: &str) {
            self.note("note_renamed", format!("{from}>{to}"));
        }
        fn flush(&self) -> Result<(), RemoteError> {
            self.note("flush", "");
            Ok(())
        }
        fn call(&self, op: Op, request: Meta) -> Result<Meta, RemoteError> {
            let said = serde_json::to_string(&request).unwrap();
            self.note(&format!("rpc:{}", op.as_str()), said);
            match self.fails.get(op.as_str()) {
                Some(errno) => Err(RemoteError::errno(*errno)),
                None => Ok(Meta::new()),
            }
        }
        fn redirect(&self, dest: SocketAddr) -> Option<io::Result<Option<SocketAddr>>> {
            self.net.map(|to| {
                Ok(if dest.ip().is_loopback() {
                    None
                } else {
                    Some(to)
                })
            })
        }
        fn now_ns(&self) -> i64 {
            42
        }
    }

    const FDCWD: u64 = AT_FDCWD as i64 as u64;
    const SP: u64 = 0x7fff_0000;

    fn stopped(name: &'static str, given: &[u64]) -> Call {
        let mut args = [0; 6];
        args[..given.len()].copy_from_slice(given);
        Call::new(name, args, SP)
    }

    fn fake(strings: &[(u64, &str)]) -> Fake {
        Fake {
            strings: strings.iter().map(|(a, s)| (*a, (*s).to_owned())).collect(),
            ..Fake::default()
        }
    }

    fn dispatch(memory: &Fake, world: &World, call: &mut Call) -> Outcome {
        Dispatcher::new().dispatch(memory, world, call)
    }

    fn verdict(memory: &Fake, world: &World, mut call: Call) -> Verdict {
        match dispatch(memory, world, &mut call) {
            Outcome::Verdict(verdict) => verdict,
            other => panic!("not a verdict: {other:?}"),
        }
    }

    const ALLOW: Verdict = Verdict::Allow;

    #[test]
    fn the_three_answers() {
        assert_eq!(Verdict::fails(libc::EEXIST), Verdict::Fail(libc::EEXIST));
        assert_eq!(Verdict::fails(0), Verdict::Fail(libc::EIO));
    }

    #[test]
    fn a_syscall_nothing_handles_is_allowed() {
        let world = World::default();
        assert_eq!(verdict(&fake(&[]), &world, stopped("getpid", &[])), ALLOW);
        assert!(world.named().is_empty());
    }

    #[test]
    fn a_directory_made_in_the_workspace_is_made_on_the_target_first() {
        let world = World::default();
        let call = stopped("mkdirat", &[FDCWD, 1, 0o40755]);
        assert_eq!(verdict(&fake(&[(1, "/m/new")]), &world, call), ALLOW);
        assert_eq!(
            world.remote_calls(),
            [(
                "rpc:mkdir".into(),
                r#"{"path":"/v/new","mode":493,"parents":false}"#.into()
            )]
        );
        assert!(world.named().contains(&"ensure_path".into()));
        // Replayed after a flush, so pushed edits land before the change.
        let named = world.named();
        let flush = named.iter().position(|n| n == "flush").unwrap();
        assert!(flush < named.iter().position(|n| n == "rpc:mkdir").unwrap());
    }

    #[test]
    fn the_targets_error_is_the_syscalls() {
        let world = World {
            fails: HashMap::from([("mkdir", libc::EEXIST)]),
            ..World::default()
        };
        let call = stopped("mkdirat", &[FDCWD, 1, 0o755]);
        assert_eq!(
            verdict(&fake(&[(1, "/m/there")]), &world, call),
            Verdict::Fail(libc::EEXIST)
        );
    }

    #[test]
    fn a_relative_path_is_read_against_the_working_directory() {
        let world = World::default();
        verdict(
            &fake(&[(1, "sub/../d")]),
            &world,
            stopped("mkdirat", &[FDCWD, 1, 0o700]),
        );
        assert_eq!(
            world.remote_calls()[0].1,
            r#"{"path":"/v/cwd/d","mode":448,"parents":false}"#
        );
    }

    #[test]
    fn a_relative_path_is_read_against_its_descriptor() {
        let world = World::default();
        verdict(
            &fake(&[(1, "d")]),
            &world,
            stopped("mkdirat", &[5, 1, 0o700]),
        );
        assert!(world.remote_calls()[0].1.contains("/v/fd5/d"));
    }

    #[test]
    fn a_path_outside_the_workspace_runs_here() {
        let world = World::default();
        let memory = fake(&[(1, "/tmp/x")]);
        assert_eq!(
            verdict(&memory, &world, stopped("mkdirat", &[FDCWD, 1, 0o755])),
            ALLOW
        );
        assert_eq!(
            verdict(&memory, &world, stopped("unlinkat", &[FDCWD, 1, 0])),
            ALLOW
        );
        assert!(world.remote_calls().is_empty());
    }

    #[test]
    fn a_removal_is_made_on_the_target_and_forgotten_here() {
        for (flags, removes) in [(0, "rpc:unlink"), (AT_REMOVEDIR, "rpc:rmdir")] {
            let world = World::default();
            let call = stopped("unlinkat", &[FDCWD, 1, flags]);
            assert_eq!(verdict(&fake(&[(1, "/m/gone")]), &world, call), ALLOW);
            assert_eq!(
                world.remote_calls(),
                [(removes.into(), r#"{"path":"/v/gone"}"#.into())]
            );
            assert!(
                world
                    .calls
                    .borrow()
                    .contains(&("note_removed".into(), "/m/gone".into()))
            );
        }
    }

    #[test]
    fn a_removal_the_target_refuses_is_not_forgotten() {
        let world = World {
            fails: HashMap::from([("unlink", libc::EACCES)]),
            ..World::default()
        };
        let call = stopped("unlinkat", &[FDCWD, 1, 0]);
        assert_eq!(
            verdict(&fake(&[(1, "/m/kept")]), &world, call),
            Verdict::Fail(libc::EACCES)
        );
        assert!(!world.named().contains(&"note_removed".into()));
    }

    #[test]
    fn an_open_makes_the_mirror_tell_the_truth_first() {
        let o_directory = ARCH.o_directory as u64;
        let cases: [(u64, &[&str]); 4] = [
            (0, &["ensure_path", "ensure_content"]),
            (
                O_WRONLY | O_CREAT,
                &["ensure_path", "ensure_content", "note_write"],
            ),
            (O_WRONLY | O_TRUNC, &["ensure_path", "note_write"]),
            (o_directory, &["ensure_path", "ensure_directory"]),
        ];
        for (flags, asked) in cases {
            let world = World::default();
            let call = stopped("openat", &[FDCWD, 1, flags]);
            assert_eq!(verdict(&fake(&[(1, "/m/f")]), &world, call), ALLOW);
            assert_eq!(world.named(), asked, "flags {flags:o}");
        }
    }

    #[test]
    fn an_openat2_reads_its_flags_from_open_how() {
        let world = World::default();
        let memory = fake(&[(1, "/m/f")]);
        let mut how = (O_WRONLY | O_TRUNC).to_le_bytes().to_vec();
        how.extend_from_slice(&[0; 16]);
        memory.bytes.borrow_mut().insert(0x900, how);
        let call = stopped("openat2", &[FDCWD, 1, 0x900, 24]);
        assert_eq!(verdict(&memory, &world, call), ALLOW);
        assert_eq!(world.named(), ["ensure_path", "note_write"]);
    }

    /// Every call that changes the workspace: the paths at 1 and 2.
    fn changes() -> Vec<Call> {
        vec![
            stopped("mkdirat", &[FDCWD, 1, 0o755]),
            stopped("unlinkat", &[FDCWD, 1, 0]),
            stopped("unlinkat", &[FDCWD, 1, AT_REMOVEDIR]),
            stopped("renameat2", &[FDCWD, 1, FDCWD, 2, 0]),
            stopped("linkat", &[FDCWD, 1, FDCWD, 2, 0]),
            stopped("symlinkat", &[1, FDCWD, 2]),
            stopped("fchmodat", &[FDCWD, 1, 0o600]),
            stopped("utimensat", &[FDCWD, 1, 0, 0]),
            stopped("truncate", &[1, 0]),
            stopped("mknodat", &[FDCWD, 1, 0o100644, 0]),
        ]
    }

    #[test]
    fn a_workspace_the_agent_may_not_write_is_never_changed_on_the_target() {
        for call in changes() {
            let name = call.name;
            let world = World {
                readonly: true,
                ..World::default()
            };
            let memory = fake(&[(1, "/m/a"), (2, "/m/b")]);
            assert_eq!(
                verdict(&memory, &world, call),
                Verdict::Fail(libc::EACCES),
                "{name}"
            );
            assert!(world.remote_calls().is_empty(), "{name}");
            assert!(!world.named().contains(&"note_write".into()), "{name}");
        }
    }

    #[test]
    fn a_workspace_the_agent_may_write_is_changed_as_ever() {
        for call in changes() {
            let name = call.name;
            let world = World::default();
            let memory = fake(&[(1, "/m/a"), (2, "/m/b")]);
            assert_eq!(verdict(&memory, &world, call), ALLOW, "{name}");
            assert!(
                !world.remote_calls().is_empty() || world.named().contains(&"note_write".into()),
                "{name}"
            );
        }
    }

    #[test]
    fn a_workspace_the_agent_may_not_write_is_still_read() {
        let world = World {
            readonly: true,
            ..World::default()
        };
        let memory = fake(&[(1, "/m/f")]);
        assert_eq!(
            verdict(&memory, &world, stopped("openat", &[FDCWD, 1, 0])),
            ALLOW
        );
        assert_eq!(world.named(), ["ensure_path", "ensure_content"]);
        let call = stopped("openat", &[FDCWD, 1, O_WRONLY | O_CREAT]);
        assert_eq!(verdict(&memory, &world, call), ALLOW);
        assert!(!world.named().contains(&"note_write".into()));
        assert!(world.remote_calls().is_empty());
    }

    #[test]
    fn a_rename_is_replayed_and_carried_across() {
        let world = World::default();
        let memory = fake(&[(1, "/m/a"), (2, "/m/b")]);
        let call = stopped("renameat2", &[FDCWD, 1, FDCWD, 2, 0]);
        assert_eq!(verdict(&memory, &world, call), ALLOW);
        assert_eq!(
            world.remote_calls()[0].1,
            r#"{"src":"/v/a","dst":"/v/b","replace":true}"#
        );
        assert!(
            world
                .calls
                .borrow()
                .contains(&("note_renamed".into(), "/m/a>/m/b".into()))
        );
    }

    #[test]
    fn a_rename_that_may_not_replace_says_so_and_an_exchange_is_refused() {
        let memory = fake(&[(1, "/m/a"), (2, "/m/b")]);
        let world = World::default();
        let call = stopped("renameat2", &[FDCWD, 1, FDCWD, 2, RENAME_NOREPLACE]);
        assert_eq!(verdict(&memory, &world, call), ALLOW);
        assert_eq!(
            world.remote_calls()[0].1,
            r#"{"src":"/v/a","dst":"/v/b","replace":false}"#
        );
        let world = World::default();
        let call = stopped("renameat2", &[FDCWD, 1, FDCWD, 2, 2]); // RENAME_EXCHANGE
        assert_eq!(verdict(&memory, &world, call), Verdict::Fail(libc::EINVAL));
        assert!(world.remote_calls().is_empty());
    }

    #[test]
    fn a_rename_across_the_mirror_is_cross_device() {
        let world = World::default();
        let memory = fake(&[(1, "/m/a"), (2, "/tmp/b")]);
        let call = stopped("renameat2", &[FDCWD, 1, FDCWD, 2, 0]);
        assert_eq!(verdict(&memory, &world, call), Verdict::Fail(libc::EXDEV));
        let call = stopped("linkat", &[FDCWD, 1, FDCWD, 2, 0]);
        assert_eq!(verdict(&memory, &world, call), Verdict::Fail(libc::EXDEV));
        assert!(world.remote_calls().is_empty());
    }

    #[test]
    fn a_device_made_in_the_workspace_stays_here() {
        let world = World::default();
        let call = stopped("mknodat", &[FDCWD, 1, 0o010644, 0]); // a FIFO
        assert_eq!(verdict(&fake(&[(1, "/m/p")]), &world, call), ALLOW);
        assert_eq!(world.named(), ["ensure_path"]);
    }

    #[test]
    fn a_null_path_is_left_to_the_kernel() {
        let world = World::default();
        assert_eq!(
            verdict(&fake(&[]), &world, stopped("openat", &[FDCWD, 0, 0])),
            ALLOW
        );
        assert!(world.named().is_empty());
    }

    #[test]
    fn a_tracee_gone_mid_call_is_let_go() {
        let world = World::default();
        let memory = Fake {
            gone: true,
            ..Fake::default()
        };
        // A string that cannot be read is no path; a vanished one is let go either way.
        assert_eq!(
            verdict(&memory, &world, stopped("mkdirat", &[FDCWD, 1, 0])),
            ALLOW
        );
    }

    #[test]
    fn an_unresolved_magic_link_fails_with_its_errno() {
        let world = World::default();
        let memory = fake(&[(1, "/proc/self/fd/9/x")]);
        let call = stopped("mkdirat", &[FDCWD, 1, 0]);
        assert_eq!(verdict(&memory, &world, call), Verdict::Fail(libc::EBADF));
    }

    #[test]
    fn lookups_and_kept_changes_materialise_the_path() {
        let world = World::default();
        let memory = fake(&[(1, "/m/a")]);
        assert_eq!(
            verdict(&memory, &world, stopped("newfstatat", &[FDCWD, 1])),
            ALLOW
        );
        assert_eq!(world.named(), ["ensure_path"]);
        let world = World::default();
        assert_eq!(
            verdict(&memory, &world, stopped("fchownat", &[FDCWD, 1])),
            ALLOW
        );
        assert_eq!(world.named(), ["ensure_content", "ensure_path"]);
    }

    #[test]
    fn times_are_replayed_with_now_and_omit() {
        let world = World::default();
        let memory = fake(&[(1, "/m/a")]);
        let mut pair = Vec::new();
        for word in [5i64, UTIME_NOW, 7, UTIME_OMIT] {
            pair.extend_from_slice(&word.to_le_bytes());
        }
        memory.bytes.borrow_mut().insert(0x500, pair);
        let call = stopped("utimensat", &[FDCWD, 1, 0x500, 0]);
        assert_eq!(verdict(&memory, &world, call), ALLOW);
        assert_eq!(
            world.remote_calls()[0].1,
            r#"{"path":"/v/a","atime_ns":42,"mtime_ns":null}"#
        );
    }

    #[test]
    fn times_both_omitted_change_nothing() {
        let world = World::default();
        let memory = fake(&[(1, "/m/a")]);
        let mut pair = Vec::new();
        for word in [0i64, UTIME_OMIT, 0, UTIME_OMIT] {
            pair.extend_from_slice(&word.to_le_bytes());
        }
        memory.bytes.borrow_mut().insert(0x500, pair);
        let call = stopped("utimensat", &[FDCWD, 1, 0x500, 0]);
        assert_eq!(verdict(&memory, &world, call), ALLOW);
        assert!(world.named().is_empty());
    }

    #[test]
    fn a_futimens_names_its_descriptor() {
        let world = World::default();
        let call = stopped("utimensat", &[3, 0, 0, 0]);
        let memory = Fake::default();
        assert_eq!(verdict(&memory, &world, call), ALLOW);
        // /m/fd3 is the mirror's: replayed, both times now.
        assert_eq!(
            world.remote_calls()[0].1,
            r#"{"path":"/v/fd3","atime_ns":42,"mtime_ns":42}"#
        );
    }

    #[test]
    fn time_shapes_decode() {
        let words = |w: [i64; 4]| w.iter().flat_map(|x| x.to_le_bytes()).collect::<Vec<u8>>();
        assert_eq!(decode_times(Times::Timespec, None, 9), (Some(9), Some(9)));
        assert_eq!(
            decode_times(Times::Timeval, Some(&words([1, 2, 3, 4])), 0),
            (Some(1_000_002_000), Some(3_000_004_000))
        );
        assert_eq!(
            decode_times(Times::Utimbuf, Some(&words([1, 2, 0, 0])[..16]), 0),
            (Some(1_000_000_000), Some(2_000_000_000))
        );
        assert_eq!(
            decode_times(Times::Timespec, Some(&words([1, 2, 3, UTIME_OMIT])), 0),
            (Some(1_000_000_002), None)
        );
        assert_eq!(
            decode_times(Times::Timespec, Some(&[0; 8]), 0),
            (None, None)
        );
        // Nonsense from a tracee wraps rather than taking the supervisor down.
        let huge = decode_times(Times::Timeval, Some(&words([i64::MAX, i64::MAX, 0, 0])), 0);
        assert!(huge.0.is_some());
    }

    #[test]
    fn paths_normalise_as_python_does() {
        for (said, want) in [
            ("/a/b/../c", "/a/c"),
            ("/../x", "/x"),
            ("a/./b/", "a/b"),
            ("../a", "../a"),
            ("//x/y", "//x/y"),
            ("///x", "/x"),
            ("", "."),
            ("a/..", "."),
        ] {
            assert_eq!(normpath(said), want, "{said}");
        }
        assert_eq!(dirname("/a/b"), "/a");
        assert_eq!(dirname("/a"), "/");
    }

    #[test]
    fn a_spelling_only_the_target_has_is_planted() {
        let world = World {
            settles: true,
            ..World::default()
        };
        let memory = fake(&[(1, "/M/f")]);
        let mut call = stopped("openat", &[FDCWD, 1, 0]);
        assert_eq!(
            dispatch(&memory, &world, &mut call),
            Outcome::Verdict(ALLOW)
        );
        let blob = b"/m/f\0";
        let at = scratch(SP, blob.len());
        assert_eq!(call.args[1], at);
        assert!(call.changed);
        assert_eq!(memory.bytes.borrow()[&at], blob);
        // The handler read the settled path back from where it was planted.
        assert_eq!(
            world.calls.borrow()[0],
            ("ensure_path".into(), "/m/f".into())
        );
    }

    #[test]
    fn two_paths_are_planted_one_below_the_other() {
        let world = World {
            redirects: vec![
                ("/h/a".into(), "/r/a".into()),
                ("/h/b".into(), "/r/bb".into()),
            ],
            ..World::default()
        };
        let memory = fake(&[(1, "/h/a"), (2, "/h/b")]);
        let mut call = stopped("renameat2", &[FDCWD, 1, FDCWD, 2, 0]);
        assert_eq!(
            dispatch(&memory, &world, &mut call),
            Outcome::Verdict(ALLOW)
        );
        let first = scratch(SP, 5);
        let second = scratch(SP, 5 + 6);
        assert_eq!((call.args[1], call.args[3]), (first, second));
        assert_eq!(memory.bytes.borrow()[&second], b"/r/bb\0");
        // A rename makes its target: the directory it is answered in is made first, once.
        let parents: Vec<_> = world
            .calls
            .borrow()
            .iter()
            .filter(|(n, _)| n == "parents")
            .cloned()
            .collect();
        assert_eq!(parents.len(), 1);
    }

    #[test]
    fn a_confined_openat2_cannot_be_answered() {
        let world = World {
            redirects: vec![("/h/a".into(), "/r/a".into())],
            ..World::default()
        };
        let memory = fake(&[(1, "/h/a")]);
        let mut how = vec![0u8; 16];
        how.extend_from_slice(&0x08u64.to_le_bytes());
        memory.bytes.borrow_mut().insert(0x900, how);
        let call = stopped("openat2", &[FDCWD, 1, 0x900, 24]);
        assert_eq!(verdict(&memory, &world, call), Verdict::Fail(libc::EIO));
    }

    #[test]
    fn an_exec_is_read_for_the_supervisor() {
        let world = World::default();
        let memory = fake(&[(1, "bin/../tool")]);
        let mut call = stopped("execve", &[1, 0x10, 0x20]);
        assert_eq!(
            dispatch(&memory, &world, &mut call),
            Outcome::Exec(ExecAsk {
                named: Some("/m/cwd/tool".into()),
                resolved: Some("/m/cwd/tool".into()),
                path_arg: 0,
                argv: 0x10,
                envp: 0x20,
            })
        );
        let memory = fake(&[(1, "/M/x")]);
        let mut call = stopped("execveat", &[FDCWD, 1, 0x10, 0x20, 0]);
        let Outcome::Exec(ask) = dispatch(&memory, &world, &mut call) else {
            panic!("not an exec");
        };
        assert_eq!(ask.named.as_deref(), Some("/M/x"));
        assert_eq!(ask.resolved.as_deref(), Some("/m/x"));
        assert_eq!(ask.path_arg, 1);
    }

    #[test]
    fn a_connect_is_pointed_at_the_proxy_in_its_family() {
        let world = World {
            net: Some("127.0.0.1:4000".parse().unwrap()),
            ..World::default()
        };
        let memory = Fake::default();
        let mut v4 = vec![2, 0, 0x01, 0xbb, 93, 184, 216, 34];
        v4.extend_from_slice(&[0; 8]);
        memory.bytes.borrow_mut().insert(0x700, v4);
        let mut call = stopped("connect", &[3, 0x700, 16]);
        assert_eq!(
            dispatch(&memory, &world, &mut call),
            Outcome::Verdict(ALLOW)
        );
        let written = memory.bytes.borrow()[&0x700].clone();
        assert_eq!(&written[..8], &[2, 0, 0x0f, 0xa0, 127, 0, 0, 1]);
        assert_eq!(call.args[2], 16);

        let mut v6 = vec![10, 0, 0, 80, 0, 0, 0, 0];
        v6.extend_from_slice(&"2001:db8::1".parse::<Ipv6Addr>().unwrap().octets());
        v6.extend_from_slice(&[0; 4]);
        memory.bytes.borrow_mut().insert(0x800, v6);
        let mut call = stopped("connect", &[3, 0x800, 28]);
        dispatch(&memory, &world, &mut call);
        let written = memory.bytes.borrow()[&0x800].clone();
        let back = decode_sockaddr(&written).unwrap();
        assert_eq!(back.family, libc::AF_INET6);
        assert_eq!(back.addr, "[::ffff:127.0.0.1]:4000".parse().unwrap());
        assert_eq!(call.args[2], 28);
    }

    #[test]
    fn a_connect_without_a_proxy_is_left_alone() {
        let world = World::default();
        let mut call = stopped("connect", &[3, 0x700, 16]);
        assert_eq!(
            dispatch(&Fake::default(), &world, &mut call),
            Outcome::Verdict(ALLOW)
        );
        assert!(!call.changed);
    }
}

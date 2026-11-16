//! Reaching into a stopped tracee: its memory, its `/proc` view, its descriptors. Port of
//! `hmz.coganchor.linux.procfs`. [Unit 6]
//!
//! Memory goes through `process_vm_readv`/`process_vm_writev`, which need no descriptor, and
//! descriptors are duplicated with `pidfd_getfd`, which -- unlike opening `/proc/<pid>/fd/N`
//! -- also reaches the AF_UNIX socketpairs Node and Rust use for a child's stdio.
//!
//! Errors are `io::Error`s carrying the kernel's errno. A tracee that has gone shows as
//! `ESRCH` (or `ENOENT` from its `/proc` directory), which callers take as "let it run": its
//! syscalls no longer matter. [`resolve_magic`] is the exception, and fails with an
//! [`Unresolved`] instead (see there).

use std::ffi::OsString;
use std::fmt;
use std::fs;
use std::io::{self, Read};
use std::os::fd::{FromRawFd, OwnedFd};
use std::os::unix::ffi::{OsStrExt, OsStringExt};
use std::sync::OnceLock;

use std::io::{IoSlice, IoSliceMut};

use nix::sys::uio::{RemoteIoVec, process_vm_readv, process_vm_writev};
use nix::unistd::{Pid, SysconfVar, sysconf};

use crate::proto::json::from_os;

/// The longest path the kernel takes, terminator included.
pub const PATH_MAX: usize = 4096;

/// The most entries [`read_strings`] reads from one `argv` or `envp`.
const MAX_ARGV_ENTRIES: usize = 65536;

/// How many magic links one path may cross: the kernel's own `SYMLOOP_MAX`. A lower number
/// would refuse a path the kernel serves, and a refusal fails the call, so a tracee could not
/// use one to slip past -- but it would break a program that did nothing wrong.
const MAX_MAGIC_HOPS: usize = 40;

/// What `readlink` appends to a descriptor whose file has been unlinked.
const DELETED: &str = " (deleted)";

/// How much of `/proc/<pid>/status` holds `Tgid` (its fourth line), read without the rest.
const STATUS_HEAD: usize = 512;

/// The page size, below which one `process_vm_readv` either reads all or nothing.
fn page_size() -> usize {
    static PAGE: OnceLock<usize> = OnceLock::new();
    *PAGE.get_or_init(|| {
        sysconf(SysconfVar::PAGE_SIZE)
            .ok()
            .flatten()
            .and_then(|size| usize::try_from(size).ok())
            .filter(|&size| size > 0)
            .unwrap_or(4096)
    })
}

/// The kernel's ceiling on one `argv` or `envp` entry, `MAX_ARG_STRLEN`: thirty-two pages.
/// What a command may be, as opposed to what a path may be.
pub fn max_arg_strlen() -> usize {
    32 * page_size()
}

fn readv(pid: Pid, addr: u64, buffer: &mut [u8]) -> io::Result<usize> {
    let remote = RemoteIoVec {
        base: addr as usize,
        len: buffer.len(),
    };
    Ok(process_vm_readv(
        pid,
        &mut [IoSliceMut::new(buffer)],
        &[remote],
    )?)
}

/// Reads `len` bytes of the tracee's memory at `addr` (`process_vm_readv`). Fewer come back
/// where the range runs into an unmapped page.
pub fn read_mem(pid: Pid, addr: u64, len: usize) -> io::Result<Vec<u8>> {
    if len == 0 {
        return Ok(Vec::new());
    }
    let mut buffer = vec![0u8; len];
    let count = readv(pid, addr, &mut buffer)?;
    buffer.truncate(count);
    Ok(buffer)
}

/// Writes `data` into the tracee's memory at `addr` (`process_vm_writev`). A write that
/// stops short, at an unmapped page, fails with `EFAULT`.
pub fn write_mem(pid: Pid, addr: u64, data: &[u8]) -> io::Result<()> {
    if data.is_empty() {
        return Ok(());
    }
    let remote = RemoteIoVec {
        base: addr as usize,
        len: data.len(),
    };
    let count = process_vm_writev(pid, &[IoSlice::new(data)], &[remote])?;
    if count != data.len() {
        return Err(io::Error::from_raw_os_error(libc::EFAULT));
    }
    Ok(())
}

/// The NUL-terminated string at `addr`, up to `PATH_MAX`.
///
/// A NULL `addr`, which several syscalls accept in place of a path, is the caller's to check
/// first: here it fails with `EFAULT`, as does a string whose first page is unreadable. One
/// that runs into an unreadable page later is what was read before it, as in Python.
pub fn read_cstring(pid: Pid, addr: u64) -> io::Result<OsString> {
    read_cstring_limit(pid, addr, PATH_MAX)
}

/// [`read_cstring`] with a ceiling of `limit` bytes rather than `PATH_MAX`.
///
/// Read a page at a time, so a string ending just before an unmapped page is still read
/// whole: one `process_vm_readv` across the boundary would fail outright.
pub fn read_cstring_limit(pid: Pid, addr: u64, limit: usize) -> io::Result<OsString> {
    Ok(OsString::from_vec(cstring(pid, addr, limit)?.0))
}

/// The bytes before the terminator at `addr`, at most `limit` of them, and whether the
/// terminator was found. Read straight into the string's own buffer, a page at a time.
fn cstring(pid: Pid, addr: u64, limit: usize) -> io::Result<(Vec<u8>, bool)> {
    if addr == 0 {
        return Err(io::Error::from_raw_os_error(libc::EFAULT));
    }
    let page = page_size() as u64;
    let mut out: Vec<u8> = Vec::new();
    let mut at = addr;
    while out.len() < limit {
        let span = ((page - at % page) as usize).min(limit - out.len());
        let filled = out.len();
        out.resize(filled + span, 0);
        let count = match readv(pid, at, &mut out[filled..]) {
            Ok(count) => count,
            Err(error) if filled == 0 => return Err(error),
            Err(_) => 0,
        };
        out.truncate(filled + count);
        if count == 0 {
            if filled == 0 {
                return Err(io::Error::from_raw_os_error(libc::EFAULT));
            }
            return Ok((out, false));
        }
        if let Some(end) = out[filled..].iter().position(|&b| b == 0) {
            out.truncate(filled + end);
            return Ok((out, true));
        }
        at += count as u64;
    }
    Ok((out, false))
}

/// The NULL-terminated array of strings at `addr` (an `argv` or `envp`).
///
/// Each entry is read up to `MAX_ARG_STRLEN`, not `PATH_MAX`: a shell command is routinely
/// longer than a path, and a truncated one would run on the target meaning something else.
/// So, unlike Python's `read_string_array`, an entry with no terminator within that fails with
/// `E2BIG`, and one that cannot be read fails with its error, as the kernel's own `execve`
/// would: a command with a hole in it is not the command the tracee asked for.
/// A NULL `addr` is an empty array.
pub fn read_strings(pid: Pid, addr: u64) -> io::Result<Vec<OsString>> {
    const WORD: u64 = 8;
    let mut values = Vec::new();
    if addr == 0 {
        return Ok(values);
    }
    let page = page_size() as u64;
    let limit = max_arg_strlen();
    let mut at = addr;
    while values.len() < MAX_ARGV_ENTRIES {
        // The pointers up to the end of this page in one read, rather than one apiece.
        let span = (page - at % page).max(WORD) as usize;
        let block = read_mem(pid, at, span)?;
        let words = block.len() / WORD as usize;
        if words == 0 {
            break;
        }
        for word in block.as_chunks::<{ WORD as usize }>().0 {
            let pointer = u64::from_le_bytes(*word);
            if pointer == 0 || values.len() >= MAX_ARGV_ENTRIES {
                return Ok(values);
            }
            let (value, whole) = cstring(pid, pointer, limit)?;
            if !whole {
                return Err(io::Error::from_raw_os_error(libc::E2BIG));
            }
            values.push(OsString::from_vec(value));
        }
        at += (words as u64) * WORD;
    }
    Ok(values)
}

/// A `/proc` magic link in a path a tracee named that could not be followed
/// (`UnresolvedPathError`).
///
/// Its own type because callers must do the opposite of what they do for a tracee that has
/// gone: a path that could not be resolved could be anywhere, the credentials this session
/// answers with others among them, so the syscall is failed with [`Unresolved::errno`] rather
/// than let through. A tracee that wanted an unexamined path would otherwise need only spell
/// one it could break -- a descriptor it has just closed, say.
#[derive(Debug)]
pub struct Unresolved {
    /// What the kernel said; the tracee is told the same.
    pub errno: i32,
    /// The path as the tracee named it.
    pub path: String,
}

impl fmt::Display for Unresolved {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "could not resolve {}: {}",
            self.path,
            io::Error::from_raw_os_error(self.errno)
        )
    }
}

impl std::error::Error for Unresolved {}

impl Unresolved {
    fn error(errno: i32, path: &str) -> io::Error {
        io::Error::new(
            io::Error::from_raw_os_error(errno).kind(),
            Unresolved {
                errno,
                path: path.to_owned(),
            },
        )
    }

    /// The [`Unresolved`] an error from [`resolve_magic`] is, if it is one.
    pub fn of(error: &io::Error) -> Option<&Unresolved> {
        error.get_ref()?.downcast_ref()
    }
}

fn errno_of(error: &io::Error, otherwise: i32) -> i32 {
    error.raw_os_error().unwrap_or(otherwise)
}

/// Resolves `/proc/self`, `/proc/thread-self`, `/proc/<pid>/{cwd,root,exe,fd/N,task/..}` magic
/// links the way the tracee would see them (40 hops at most), or fails: an unresolvable magic
/// link fails the call rather than being guessed at.
///
/// Coding CLIs write a file the atomic way, and several spell "beneath this directory" as
/// `/proc/self/fd/<n>/name`; a rule about path prefixes would let that past unexamined. So
/// the links are followed here, before anything is compared. `self` is the tracee's thread
/// group and `thread-self` the stopped thread; a `<pid>` written out is asked as written.
/// `..` is collapsed after a link is followed, as the kernel does; a path beginning `//` is
/// read as `/`. What comes back is tidied as `os.path.normpath` would, without following
/// ordinary symlinks.
///
/// Returns `path` untouched when there is nothing to settle (no `/proc/` in it and no leading
/// `//`), and also where a link names what is not a file of this filesystem -- a pipe, a
/// socket, an unlinked file -- none of which can be inside a workspace.
///
/// Fails with an [`Unresolved`] (see [`Unresolved::of`]) if a link could not be read, the
/// tracee's thread group could not be learned, or the hops ran out (`ELOOP`).
pub fn resolve_magic(pid: Pid, path: &str) -> io::Result<String> {
    if !path.contains("/proc/") && !path.starts_with("//") {
        return Ok(path.to_owned());
    }
    let mut walked: Vec<String> = Vec::new();
    let mut hops = 0;
    for name in path.split('/') {
        // Following a link replaces what has been walked and leaves the rest of the name to
        // carry on against it, so one forward pass is the whole of the algorithm.
        match name {
            "" | "." => continue,
            ".." => {
                walked.pop();
                continue;
            }
            _ => walked.push(name.to_owned()),
        }
        let Some(link) = magic_link(pid, &walked, path)? else {
            continue;
        };
        hops += 1;
        if hops > MAX_MAGIC_HOPS {
            return Err(Unresolved::error(libc::ELOOP, path));
        }
        // A descriptor that is not there fails the call, and is not taken for a tracee that
        // has gone: a tracee could otherwise name one it has just closed.
        let target = fs::read_link(&link)
            .map_err(|why| Unresolved::error(errno_of(&why, libc::EIO), path))?;
        let target = from_os(target.as_os_str());
        if !target.starts_with('/') || target.ends_with(DELETED) {
            return Ok(path.to_owned());
        }
        walked = target
            .split('/')
            .filter(|part| !part.is_empty())
            .map(str::to_owned)
            .collect();
    }
    Ok(format!("/{}", walked.join("/")))
}

/// Whether a path component is a number procfs would read as one: ASCII digits only.
fn numeric(name: &str) -> bool {
    !name.is_empty() && name.bytes().all(|b| b.is_ascii_digit())
}

/// Where this process reads the magic link `walked` spells, or `None` for anything else
/// (`_magic_link`): `/proc/<who>/fd/<n>` and `/proc/<who>/{cwd,exe,root}`, each also reachable
/// as `/proc/<who>/task/<tid>/...`. Nothing the tracee wrote reaches the name returned except
/// as digits, so a component cannot be spelled to step out of `/proc/<digits>/`.
fn magic_link(pid: Pid, walked: &[String], path: &str) -> io::Result<Option<String>> {
    let [proc_, whose, rest @ ..] = walked else {
        return Ok(None);
    };
    if proc_ != "proc" {
        return Ok(None);
    }
    // Only a component that could end a magic link is worth asking `Tgid` for.
    let shaped = match rest {
        [name] => matches!(name.as_str(), "cwd" | "exe" | "root"),
        [fd, n] => fd == "fd" && numeric(n),
        [task, t, name] => {
            task == "task" && numeric(t) && matches!(name.as_str(), "cwd" | "exe" | "root")
        }
        [task, t, fd, n] => task == "task" && numeric(t) && fd == "fd" && numeric(n),
        _ => false,
    };
    if !shaped {
        return Ok(None);
    }
    if !matches!(whose.as_str(), "self" | "thread-self") && !numeric(whose) {
        return Ok(None);
    }
    // A thread written out names itself: `/proc/<pid>/task/<tid>/fd/<n>` is `/proc/<tid>/fd/<n>`,
    // so what it was reached through needs no resolving.
    let (whose, rest) = match rest {
        [task, thread, below @ ..] if task == "task" => (thread.clone(), below),
        _ => (
            match whose.as_str() {
                "self" => tgid(pid)
                    .map_err(|why| Unresolved::error(errno_of(&why, libc::ESRCH), path))?
                    .to_string(),
                "thread-self" => pid.to_string(),
                other => other.to_owned(),
            },
            rest,
        ),
    };
    Ok(Some(match rest {
        [name] => format!("/proc/{whose}/{name}"),
        [_, number] => format!("/proc/{whose}/fd/{number}"),
        _ => unreachable!("shaped above"),
    }))
}

fn read_link(path: &str) -> io::Result<String> {
    Ok(from_os(fs::read_link(path)?.as_os_str()))
}

/// The tracee's working directory.
pub fn cwd(pid: Pid) -> io::Result<String> {
    read_link(&format!("/proc/{pid}/cwd"))
}

/// What descriptor `fd` of the tracee names.
pub fn fd_path(pid: Pid, fd: i32) -> io::Result<String> {
    read_link(&format!("/proc/{pid}/fd/{fd}"))
}

/// A duplicate of the tracee's descriptor `fd`: `pidfd_getfd`, falling back to reopening its
/// `/proc` name (read-only for 0, write-only otherwise) where that call is refused.
///
/// `pidfd_getfd` hands over the descriptor itself, so a pipe, a socket and a tty arrive as
/// what they are. But it asks for ptrace-attach rights, and a container's default seccomp
/// profile refuses it without `CAP_SYS_PTRACE`; a cog in one would trace its agent and lose
/// every byte it wrote. A reopened name is a second handle on the same pipe or file, which is
/// enough for somewhere to put the output. A socket has no name to reopen, and fails with the
/// first way's error, the one worth acting on.
pub fn steal_fd(pid: Pid, fd: i32) -> io::Result<OwnedFd> {
    // SAFETY: integer-argument syscalls; a descriptor returned is ours to own.
    let pidfd = unsafe { libc::syscall(libc::SYS_pidfd_open, pid.as_raw(), 0) };
    let refused = if pidfd >= 0 {
        // SAFETY: `pidfd` was just returned to us, and is closed when this drops.
        let pidfd = unsafe { OwnedFd::from_raw_fd(pidfd as i32) };
        // SAFETY: as above.
        let stolen = unsafe {
            libc::syscall(
                libc::SYS_pidfd_getfd,
                std::os::fd::AsRawFd::as_raw_fd(&pidfd),
                fd,
                0,
            )
        };
        if stolen >= 0 {
            // SAFETY: a new descriptor of ours, close-on-exec as `pidfd_getfd` makes it.
            return Ok(unsafe { OwnedFd::from_raw_fd(stolen as i32) });
        }
        io::Error::last_os_error()
    } else {
        io::Error::last_os_error()
    };
    // Read for the input and write for the other two, because that is what each is: a pipe
    // reopened the wrong way round cannot be used, and `O_RDWR` on a pipe's read end fails.
    let mut options = fs::OpenOptions::new();
    if fd == 0 {
        options.read(true);
    } else {
        options.write(true);
    }
    match options.open(format!("/proc/{pid}/fd/{fd}")) {
        Ok(file) => Ok(file.into()),
        Err(_) => Err(refused),
    }
}

/// The head of `/proc/<pid>/status`, where `Tgid` and the pending masks are.
fn status(pid: Pid, head: Option<usize>) -> io::Result<String> {
    let file = fs::File::open(format!("/proc/{pid}/status"))?;
    let mut text = Vec::new();
    match head {
        Some(limit) => file.take(limit as u64).read_to_end(&mut text)?,
        None => (&file).read_to_end(&mut text)?,
    };
    Ok(String::from_utf8_lossy(&text).into_owned())
}

/// The signals pending for the tracee (`SigPnd | ShdPnd` of `/proc/<pid>/status`).
///
/// A process stopped by ptrace never dequeues ordinary signals, so this is how an agent's
/// `SIGTERM` to a parked stand-in is seen. Bit `n - 1` is signal `n`, on every architecture.
pub fn pending_signals(pid: Pid) -> io::Result<u64> {
    let mut mask = 0;
    for line in status(pid, None)?.lines() {
        if let Some(hex) = line
            .strip_prefix("SigPnd:")
            .or_else(|| line.strip_prefix("ShdPnd:"))
        {
            mask |= u64::from_str_radix(hex.trim(), 16)
                .map_err(|_| io::Error::from_raw_os_error(libc::EINVAL))?;
        }
    }
    Ok(mask)
}

/// The thread-group id of thread `tid`: what `/proc/self` names for it. Asked of
/// `/proc/<tid>/status` rather than remembered; `tid` itself where the file does not say.
pub fn tgid(tid: Pid) -> io::Result<Pid> {
    for line in status(tid, Some(STATUS_HEAD))?.lines() {
        if let Some(said) = line.strip_prefix("Tgid:") {
            let said = said.trim();
            if numeric(said)
                && let Ok(n) = said.parse()
            {
                return Ok(Pid::from_raw(n));
            }
            break;
        }
    }
    Ok(tid)
}

/// The basename of `/proc/<pid>/exe`.
pub fn exe_name(pid: Pid) -> io::Result<String> {
    let exe = fs::read_link(format!("/proc/{pid}/exe"))?;
    let name = exe.file_name().map(|n| n.as_bytes()).unwrap_or_default();
    Ok(crate::proto::json::from_bytes(name))
}

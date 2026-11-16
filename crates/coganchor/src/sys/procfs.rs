//! Reaching into a stopped tracee: its memory, its `/proc` view, its descriptors. [Unit 6]

use std::ffi::OsString;
use std::io;
use std::os::fd::OwnedFd;

use nix::unistd::Pid;

/// Reads `len` bytes of the tracee's memory at `addr` (`process_vm_readv`).
pub fn read_mem(pid: Pid, addr: u64, len: usize) -> io::Result<Vec<u8>> {
    todo!("unit 6")
}

/// Writes `data` into the tracee's memory at `addr` (`process_vm_writev`).
pub fn write_mem(pid: Pid, addr: u64, data: &[u8]) -> io::Result<()> {
    todo!("unit 6")
}

/// The NUL-terminated string at `addr`, up to `PATH_MAX`.
pub fn read_cstring(pid: Pid, addr: u64) -> io::Result<OsString> {
    todo!("unit 6")
}

/// The NULL-terminated array of strings at `addr` (an `argv` or `envp`).
pub fn read_strings(pid: Pid, addr: u64) -> io::Result<Vec<OsString>> {
    todo!("unit 6")
}

/// Resolves `/proc/self`, `/proc/thread-self`, `/proc/<pid>/{cwd,root,fd/N,task/..}` magic
/// links the way the tracee would see them (40 hops at most), or fails: an unresolvable magic
/// link fails the call rather than being guessed at.
pub fn resolve_magic(pid: Pid, path: &str) -> io::Result<String> {
    todo!("unit 6")
}

/// The tracee's working directory.
pub fn cwd(pid: Pid) -> io::Result<String> {
    todo!("unit 6")
}

/// What descriptor `fd` of the tracee names.
pub fn fd_path(pid: Pid, fd: i32) -> io::Result<String> {
    todo!("unit 6")
}

/// A duplicate of the tracee's descriptor `fd`: `pidfd_getfd`, falling back to reopening its
/// `/proc` name (read-only for 0, write-only otherwise) where that call is refused.
pub fn steal_fd(pid: Pid, fd: i32) -> io::Result<OwnedFd> {
    todo!("unit 6")
}

/// The signals pending for the tracee (`SigPnd | ShdPnd` of `/proc/<pid>/status`).
pub fn pending_signals(pid: Pid) -> io::Result<u64> {
    todo!("unit 6")
}

/// The thread-group id of thread `tid`.
pub fn tgid(tid: Pid) -> io::Result<Pid> {
    todo!("unit 6")
}

/// The basename of `/proc/<pid>/exe`.
pub fn exe_name(pid: Pid) -> io::Result<String> {
    todo!("unit 6")
}

//! Turning a traced process into a stand-in for a command running elsewhere. Port of
//! `hmz.coganchor.standin`. [Unit 10]
//!
//! The `execve` is redirected at a stub (`/bin/true`, `/usr/bin/true`, or this binary), let
//! through to release a `vfork`/`posix_spawn` parent and close close-on-exec descriptors, and
//! caught at `PTRACE_EVENT_EXEC` before the stub runs; later rewritten into `exit_group` with
//! the remote status.

use std::io;

use nix::unistd::Pid;

use crate::sys::ptrace::Regs;

/// Parks `pid`, stopped at the `execve` whose registers are `regs`, as a stand-in.
pub fn park(pid: Pid, regs: &Regs) -> io::Result<()> {
    todo!("unit 10")
}

/// Releases a parked stand-in with `status` (`exit_group`), or delivers `signal` where the
/// remote command died of a fatal one.
pub fn release(pid: Pid, status: i32, signal: Option<i32>) -> io::Result<()> {
    todo!("unit 10")
}

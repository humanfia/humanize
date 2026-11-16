//! The trap filter: which syscalls stop for the tracer. [Unit 6]
//!
//! `SECCOMP_RET_TRACE` for the cold syscalls named, `SECCOMP_RET_ALLOW` for everything else
//! (and for a foreign architecture), so hot syscalls never pay a ptrace stop.

use std::io;

/// Installs, on the calling thread, a filter stopping exactly `numbers` for the tracer, after
/// setting `no_new_privs`. Call in a freshly forked child just before `execve`.
pub fn install(numbers: &[i64]) -> io::Result<()> {
    todo!("unit 6")
}

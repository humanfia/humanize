//! The Linux facilities the cog and the cred tracer stand on. Port of
//! `hmz.coganchor.linux.{syscalls,ptrace,procfs}` and the trap filter of
//! `hmz.coganchor.linux.seccomp`. [Unit 6]
//!
//! x86-64 and aarch64 only; any other architecture fails to build rather than ship an
//! untested register map.

pub mod procfs;
pub mod ptrace;
pub mod syscalls;
pub mod trap;

pub use syscalls::{ARCH, Arch};

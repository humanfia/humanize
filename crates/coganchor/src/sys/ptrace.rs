//! A minimal `ptrace(2)` layer over `PTRACE_GETREGSET`/`SETREGSET`, the one form aarch64 has.
//! [Unit 6]
//!
//! Everything here must be called from the thread that attached to the tracee.

use std::io;

use nix::unistd::Pid;

/// A stopped tracee's registers, read as a whole and written back as a whole.
#[derive(Clone, Debug)]
pub struct Regs {
    pub raw: libc::user_regs_struct,
    /// aarch64 only: the syscall number, which lives outside the general registers.
    pub nr: Option<i64>,
}

impl Regs {
    /// The syscall number.
    pub fn syscall(&self) -> i64 {
        todo!("unit 6")
    }
    /// Changes the syscall number (-1 cancels it).
    pub fn set_syscall(&mut self, nr: i64) {
        todo!("unit 6")
    }
    /// Syscall argument `i` (0-5).
    pub fn arg(&self, i: usize) -> u64 {
        todo!("unit 6")
    }
    /// Sets syscall argument `i`.
    pub fn set_arg(&mut self, i: usize, value: u64) {
        todo!("unit 6")
    }
    /// The return-value register.
    pub fn result(&self) -> i64 {
        todo!("unit 6")
    }
    /// Sets the return-value register.
    pub fn set_result(&mut self, value: i64) {
        todo!("unit 6")
    }
    /// The stack pointer.
    pub fn sp(&self) -> u64 {
        todo!("unit 6")
    }
}

/// Reads a stopped tracee's registers.
pub fn getregs(pid: Pid) -> io::Result<Regs> {
    todo!("unit 6")
}

/// Writes them back (and, on aarch64, a changed syscall number via `NT_ARM_SYSTEM_CALL`).
pub fn setregs(pid: Pid, regs: &Regs) -> io::Result<()> {
    todo!("unit 6")
}

/// Where in its syscall a tracee stopped, as `PTRACE_GET_SYSCALL_INFO` says.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SyscallStop {
    Entry,
    Exit,
    Seccomp,
    Other,
}

/// `PTRACE_GET_SYSCALL_INFO`, `None` where the kernel lacks it.
pub fn syscall_stop(pid: Pid) -> io::Result<Option<SyscallStop>> {
    todo!("unit 6")
}

/// The options the cog traces with: `TRACESYSGOOD|FORK|VFORK|CLONE|EXEC|SECCOMP|EXITKILL`.
pub fn set_cog_options(pid: Pid) -> io::Result<()> {
    todo!("unit 6")
}

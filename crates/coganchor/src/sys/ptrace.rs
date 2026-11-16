//! A minimal `ptrace(2)` layer over `PTRACE_GETREGSET`/`SETREGSET`, the one form aarch64 has.
//! Port of `hmz.coganchor.linux.ptrace`. [Unit 6]
//!
//! The supervisor needs four things of ptrace: to stop a tracee when the trap filter fires, to
//! read and rewrite its registers, to cancel a syscall and substitute a result, and to replace
//! one outright (`execve` becomes `exit_group`). The register set does all of that but the
//! last on aarch64, which latches the syscall number out of `x8` before the stop is reported:
//! there a new number goes through the `NT_ARM_SYSTEM_CALL` regset instead (see [`setregs`]).
//!
//! Everything here must be called from the thread that attached to the tracee; the kernel
//! enforces that.

use std::io;

use nix::sys::ptrace;
use nix::sys::signal::Signal;
use nix::unistd::Pid;

/// `NT_PRSTATUS` from `<linux/elf.h>`: the general-purpose registers.
const NT_PRSTATUS: libc::c_long = 1;

/// `NT_ARM_SYSTEM_CALL` from `<linux/elf.h>`: a one-`int` regset that is the only way to
/// change which syscall an aarch64 tracee is about to make.
pub const NT_ARM_SYSTEM_CALL: libc::c_long = 0x404;

const PTRACE_GETREGSET: libc::c_long = 0x4204;
const PTRACE_SETREGSET: libc::c_long = 0x4205;
const PTRACE_GET_SYSCALL_INFO: libc::c_long = 0x420E;

/// `PTRACE_EVENT_*` codes, delivered in bits 16-23 of a wait status.
pub const EVENT_FORK: i32 = 1;
pub const EVENT_VFORK: i32 = 2;
pub const EVENT_CLONE: i32 = 3;
pub const EVENT_EXEC: i32 = 4;
pub const EVENT_SECCOMP: i32 = 7;

/// The bit `TRACESYSGOOD` sets in the stop signal of a syscall stop.
pub const SYSCALL_STOP_SIG: i32 = 0x80;

/// The options every tracee of the cog is traced with: follow the whole process tree, report
/// trap-filter stops, tell syscall stops from signals, and kill everything if the tracer dies
/// (`OPTIONS`).
pub fn cog_options() -> ptrace::Options {
    ptrace::Options::PTRACE_O_TRACESYSGOOD
        | ptrace::Options::PTRACE_O_TRACEFORK
        | ptrace::Options::PTRACE_O_TRACEVFORK
        | ptrace::Options::PTRACE_O_TRACECLONE
        | ptrace::Options::PTRACE_O_TRACEEXEC
        | ptrace::Options::PTRACE_O_TRACESECCOMP
        | ptrace::Options::PTRACE_O_EXITKILL
}

/// A stopped tracee's registers, read as a whole and written back as a whole.
#[derive(Clone, Debug)]
pub struct Regs {
    pub raw: libc::user_regs_struct,
    /// aarch64 only: the syscall number, which lives outside the general registers. `None`
    /// until [`Regs::set_syscall`] renumbers the call, and only then written by [`setregs`]:
    /// `x8` holds the number the tracee asked for, and the kernel has already read it.
    pub nr: Option<i64>,
}

impl Regs {
    /// The syscall number.
    pub fn syscall(&self) -> i64 {
        #[cfg(target_arch = "x86_64")]
        return self.raw.orig_rax as i64;
        #[cfg(target_arch = "aarch64")]
        return self.nr.unwrap_or(self.raw.regs[8] as i64);
    }

    /// Changes the syscall number (-1 cancels it).
    pub fn set_syscall(&mut self, nr: i64) {
        #[cfg(target_arch = "x86_64")]
        {
            self.raw.orig_rax = nr as u64;
        }
        // Writing `x8` back would change nothing and lie to whoever read it again; the number
        // is held beside the registers and `setregs` writes it through the regset that acts.
        #[cfg(target_arch = "aarch64")]
        {
            self.nr = Some(nr);
        }
    }

    fn arg_slot(&mut self, i: usize) -> &mut u64 {
        #[cfg(target_arch = "x86_64")]
        return match i {
            0 => &mut self.raw.rdi,
            1 => &mut self.raw.rsi,
            2 => &mut self.raw.rdx,
            3 => &mut self.raw.r10,
            4 => &mut self.raw.r8,
            5 => &mut self.raw.r9,
            _ => panic!("syscall argument {i} out of range"),
        };
        #[cfg(target_arch = "aarch64")]
        {
            assert!(i < 6, "syscall argument {i} out of range");
            &mut self.raw.regs[i]
        }
    }

    /// Syscall argument `i` (0-5).
    pub fn arg(&self, i: usize) -> u64 {
        #[cfg(target_arch = "x86_64")]
        return match i {
            0 => self.raw.rdi,
            1 => self.raw.rsi,
            2 => self.raw.rdx,
            3 => self.raw.r10,
            4 => self.raw.r8,
            5 => self.raw.r9,
            _ => panic!("syscall argument {i} out of range"),
        };
        #[cfg(target_arch = "aarch64")]
        {
            assert!(i < 6, "syscall argument {i} out of range");
            self.raw.regs[i]
        }
    }

    /// Syscall argument `i` as the C `int` its low 32 bits are (a `dirfd`, say).
    pub fn signed_arg(&self, i: usize) -> i32 {
        self.arg(i) as u32 as i32
    }

    /// Sets syscall argument `i`.
    pub fn set_arg(&mut self, i: usize, value: u64) {
        *self.arg_slot(i) = value;
    }

    /// The return-value register.
    pub fn result(&self) -> i64 {
        #[cfg(target_arch = "x86_64")]
        return self.raw.rax as i64;
        #[cfg(target_arch = "aarch64")]
        return self.raw.regs[0] as i64;
    }

    /// Sets the return-value register.
    pub fn set_result(&mut self, value: i64) {
        #[cfg(target_arch = "x86_64")]
        {
            self.raw.rax = value as u64;
        }
        #[cfg(target_arch = "aarch64")]
        {
            self.raw.regs[0] = value as u64;
        }
    }

    /// The stack pointer.
    pub fn sp(&self) -> u64 {
        #[cfg(target_arch = "x86_64")]
        return self.raw.rsp;
        #[cfg(target_arch = "aarch64")]
        return self.raw.sp;
    }

    /// Where `size` bytes may be written in the tracee, for a path it is to be given: below the
    /// stack pointer, clear of the architecture's red zone (`Registers.scratch`). Only as many
    /// bytes as are written are skipped, since a thread's own stack may have little left; and
    /// the tracee runs no instruction between the write and the kernel's read of it.
    pub fn scratch(&self, size: u64) -> u64 {
        self.sp() - super::ARCH.red_zone - size
    }
}

/// `ptrace(2)` as the raw syscall, whose argument types are the same on glibc and musl (the
/// libc wrappers disagree on the request's type).
fn raw(
    request: libc::c_long,
    pid: Pid,
    addr: libc::c_long,
    data: *mut libc::c_void,
) -> io::Result<libc::c_long> {
    // SAFETY: every caller hands `data` pointing at a live buffer of the size the request
    // describes (an iovec it owns, or a buffer of `addr` bytes).
    let done = unsafe {
        libc::syscall(
            libc::SYS_ptrace,
            request,
            libc::c_long::from(pid.as_raw()),
            addr,
            data,
        )
    };
    if done == -1 {
        Err(io::Error::last_os_error())
    } else {
        Ok(done)
    }
}

/// Reads a stopped tracee's registers.
pub fn getregs(pid: Pid) -> io::Result<Regs> {
    // SAFETY: `user_regs_struct` is plain integers, for which all-zeroes is a value.
    let mut regs = Regs {
        raw: unsafe { std::mem::zeroed() },
        nr: None,
    };
    let mut vector = libc::iovec {
        iov_base: (&raw mut regs.raw).cast(),
        iov_len: std::mem::size_of::<libc::user_regs_struct>(),
    };
    raw(PTRACE_GETREGSET, pid, NT_PRSTATUS, (&raw mut vector).cast())?;
    Ok(regs)
}

/// Writes them back (and, on aarch64, a changed syscall number via `NT_ARM_SYSTEM_CALL`):
/// without that second write a cancelled syscall would run anyway, and a stand-in would never
/// become an `exit_group`.
pub fn setregs(pid: Pid, regs: &Regs) -> io::Result<()> {
    let mut copy = regs.raw;
    let mut vector = libc::iovec {
        iov_base: (&raw mut copy).cast(),
        iov_len: std::mem::size_of::<libc::user_regs_struct>(),
    };
    raw(PTRACE_SETREGSET, pid, NT_PRSTATUS, (&raw mut vector).cast())?;
    #[cfg(target_arch = "aarch64")]
    if let Some(nr) = regs.nr {
        let mut number = nr as libc::c_int;
        let mut vector = libc::iovec {
            iov_base: (&raw mut number).cast(),
            iov_len: std::mem::size_of::<libc::c_int>(),
        };
        raw(
            PTRACE_SETREGSET,
            pid,
            NT_ARM_SYSTEM_CALL,
            (&raw mut vector).cast(),
        )?;
    }
    Ok(())
}

/// Where in its syscall a tracee stopped, as `PTRACE_GET_SYSCALL_INFO` says.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SyscallStop {
    Entry,
    Exit,
    Seccomp,
    Other,
}

/// `PTRACE_GET_SYSCALL_INFO`, `None` where the kernel lacks it (before Linux 5.3).
///
/// Asked rather than inferred from the `-ENOSYS` the kernel parks in the result register at
/// an entry stop, which x86-64 does and aarch64 does not (`syscall_stop_kind`).
pub fn syscall_stop(pid: Pid) -> io::Result<Option<SyscallStop>> {
    // Only the first word is read: its first byte is the op, and the kernel copies no more
    // than it is given room for.
    let mut head = [0u8; 8];
    match raw(
        PTRACE_GET_SYSCALL_INFO,
        pid,
        head.len() as libc::c_long,
        head.as_mut_ptr().cast(),
    ) {
        Ok(_) => {}
        Err(error) if matches!(error.raw_os_error(), Some(libc::EIO | libc::EINVAL)) => {
            return Ok(None);
        }
        Err(error) => return Err(error),
    }
    Ok(Some(match head[0] {
        1 => SyscallStop::Entry,
        2 => SyscallStop::Exit,
        3 => SyscallStop::Seccomp,
        _ => SyscallStop::Other,
    }))
}

/// The options the cog traces with: `TRACESYSGOOD|FORK|VFORK|CLONE|EXEC|SECCOMP|EXITKILL`.
pub fn set_cog_options(pid: Pid) -> io::Result<()> {
    Ok(ptrace::setoptions(pid, cog_options())?)
}

/// Called in a forked child to ask to be traced by its parent.
pub fn traceme() -> io::Result<()> {
    Ok(ptrace::traceme()?)
}

/// Traces a running process without stopping it, with `options` from the start. For a
/// tracer that is not the process's parent.
pub fn seize(pid: Pid, options: ptrace::Options) -> io::Result<()> {
    Ok(ptrace::seize(pid, options)?)
}

/// Stops a seized tracee (`PTRACE_INTERRUPT`).
pub fn interrupt(pid: Pid) -> io::Result<()> {
    Ok(ptrace::interrupt(pid)?)
}

/// Resumes until the next stop, delivering `signal` on the way if one is given.
pub fn cont(pid: Pid, signal: Option<Signal>) -> io::Result<()> {
    Ok(ptrace::cont(pid, signal)?)
}

/// Resumes until the next syscall entry or exit stop.
pub fn syscall(pid: Pid, signal: Option<Signal>) -> io::Result<()> {
    Ok(ptrace::syscall(pid, signal)?)
}

/// Lets a tracee go, delivering `signal` if one is given.
pub fn detach(pid: Pid, signal: Option<Signal>) -> io::Result<()> {
    Ok(ptrace::detach(pid, signal)?)
}

/// The payload of the `PTRACE_EVENT_*` stop a tracee is at: a new child's pid, say.
pub fn event_message(pid: Pid) -> io::Result<u64> {
    Ok(ptrace::getevent(pid)? as u64)
}

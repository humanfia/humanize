//! Turning a traced process into a stand-in for a command running elsewhere. Port of
//! `hmz.coganchor.standin`. [Unit 10]
//!
//! The `execve` is redirected at a stub (`/bin/true`, `/usr/bin/true`, or this binary), let
//! through to release a `vfork`/`posix_spawn` parent and close close-on-exec descriptors, and
//! caught at `PTRACE_EVENT_EXEC` before the stub runs; later rewritten into `exit_group` with
//! the remote status.
//!
//! Releasing the parent is the point: a parent that spawned with `vfork` or `posix_spawn` is
//! suspended until its child execs or exits, and one that forked blocks on a close-on-exec
//! pipe. Both are released by exactly one event, a successful `execve`, so an exec is made to
//! happen -- just not the one that was asked for.

use std::io;
use std::sync::{Once, OnceLock};

use nix::unistd::Pid;

use crate::cog::handlers::{AT_FDCWD, scratch};
use crate::sys::ARCH;
use crate::sys::ptrace::{self, Regs, SyscallStop};
use crate::sys::{procfs, syscalls};

/// Syscall stops walked through looking for an entry stop.
const MAX_STEPS_TO_ENTRY: usize = 4;

/// Signal-delivery stops passed through on the way to one syscall stop.
const MAX_SIGNALS_PER_STEP: usize = 8;

/// The program a stand-in execs: one the kernel can load and that is caught before it runs a
/// single instruction (`_choose_stub`). `/proc/self/exe` is resolved in the tracee, so it names
/// whatever that process already runs.
pub fn stub() -> &'static str {
    static STUB: OnceLock<&'static str> = OnceLock::new();
    STUB.get_or_init(|| {
        ["/bin/true", "/usr/bin/true"]
            .into_iter()
            .find(|candidate| {
                nix::unistd::access(*candidate, nix::unistd::AccessFlags::X_OK).is_ok()
            })
            .unwrap_or("/proc/self/exe")
    })
}

/// Parks `pid`, stopped at the `execve` whose registers are `regs`, as a stand-in.
///
/// On success the process is left at a syscall-entry (or seccomp) stop, ready to be turned
/// into `exit_group`. Where the stub's path cannot be planted the process stays where it was,
/// and is released from there; where anything fails once the exec may have been let through,
/// the process is killed, since a stub allowed to run would exit 0 and read as success.
pub fn park(pid: Pid, regs: &Regs) -> io::Result<()> {
    park_reporting(pid, regs).0
}

/// [`park`], also giving the raw `waitpid` status of the stand-in's death where parking's
/// own waits took it, which the supervisor's loop will then never see.
pub(crate) fn park_reporting(pid: Pid, regs: &Regs) -> (io::Result<()>, Option<i32>) {
    let execveat = syscalls::number("execveat").is_some_and(|nr| nr == regs.syscall());
    let mut live = Live {
        pid,
        regs: regs.clone(),
        died: None,
    };
    let parked = park_with(&mut live, regs.sp(), execveat);
    (parked, live.died)
}

/// Releases a parked stand-in with `status` (`exit_group`), or delivers `signal` where the
/// remote command died of a fatal one.
///
/// A signal is only injected where the stand-in waits at a syscall-entry stop, which the
/// kernel delivers it from; at an event stop (an unparked `execve`'s seccomp stop) an injected
/// signal is dropped and the call would run as asked, so the status is given there instead.
pub fn release(pid: Pid, status: i32, signal: Option<i32>) -> io::Result<()> {
    if let Some(signal) = signal
        && matches!(
            ptrace::syscall_stop(pid),
            Ok(Some(SyscallStop::Entry)) | Ok(None)
        )
    {
        // The stand-in dies of the very signal, so the agent's `wait` sees a signal death.
        return restart(false, pid, signal);
    }
    let exit_group = syscalls::number("exit_group")
        .ok_or_else(|| io::Error::other("this architecture has no exit_group"))?;
    let mut regs = ptrace::getregs(pid)?;
    regs.set_syscall(exit_group);
    regs.set_arg(0, status as u32 as u64);
    ptrace::setregs(pid, &regs)?;
    restart(false, pid, 0)
}

/// Restarts a stopped tracee, to its next syscall stop where `syscall` (`PTRACE_SYSCALL`) or
/// freely (`PTRACE_CONT`), delivering `signal`.
pub(crate) fn restart(syscall: bool, pid: Pid, signal: i32) -> io::Result<()> {
    let request = if syscall {
        libc::PTRACE_SYSCALL
    } else {
        libc::PTRACE_CONT
    };
    // SAFETY: a ptrace restart request takes no pointers; `data` is the signal number.
    let done = unsafe {
        libc::ptrace(
            request,
            pid.as_raw(),
            std::ptr::null_mut::<libc::c_void>(),
            signal as libc::c_long as *mut libc::c_void,
        )
    };
    if done < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(())
    }
}

/// A blocking `waitpid(pid, __WALL)`, its raw status.
pub(crate) fn wait_raw(pid: libc::pid_t, flags: libc::c_int) -> io::Result<(libc::pid_t, i32)> {
    let mut status = 0;
    loop {
        // SAFETY: `status` is a valid out-pointer.
        let got = unsafe { libc::waitpid(pid, &mut status, flags | libc::__WALL) };
        if got >= 0 {
            return Ok((got, status));
        }
        let error = io::Error::last_os_error();
        if error.kind() != io::ErrorKind::Interrupted {
            return Err(error);
        }
    }
}

/// What parking does to a tracee, so the sequence can be followed without one.
pub(crate) trait Stepper {
    /// Writes `blob` at `addr` and reads it back.
    fn plant(&mut self, addr: u64, blob: &[u8]) -> io::Result<bool>;
    /// Sets the given arguments and writes the registers back.
    fn point(&mut self, args: &[(usize, u64)]) -> io::Result<()>;
    fn cont(&mut self) -> io::Result<()>;
    /// Resumes to the next syscall stop, delivering `signal`.
    fn syscall(&mut self, signal: i32) -> io::Result<()>;
    /// Waits for the tracee's next state change, its raw status.
    fn wait(&mut self) -> io::Result<i32>;
    fn stop_kind(&mut self) -> io::Result<Option<SyscallStop>>;
    fn result(&mut self) -> io::Result<i64>;
    fn kill(&mut self);
}

/// The status of a ptrace event stop.
pub(crate) fn event_of(status: i32) -> i32 {
    status >> 16
}

/// The parking sequence (`park`), over any [`Stepper`].
pub(crate) fn park_with(steps: &mut dyn Stepper, sp: u64, execveat: bool) -> io::Result<()> {
    let mut blob = stub().as_bytes().to_vec();
    blob.push(0);
    let address = scratch(sp, blob.len());
    if !steps.plant(address, &blob).unwrap_or(false) {
        tracing::debug!("no scratch space for the stub path");
        return Err(io::Error::from_raw_os_error(libc::EFAULT));
    }
    let parked = (|| -> io::Result<bool> {
        if execveat {
            steps.point(&[(0, AT_FDCWD as i64 as u64), (1, address)])?;
        } else {
            steps.point(&[(0, address)])?;
        }
        steps.cont()?;
        Ok(await_exec_event(steps)? && step_to_syscall_entry(steps)?)
    })();
    match parked {
        Ok(true) => Ok(()),
        outcome => {
            if let Err(error) = &outcome {
                tracing::debug!("could not be parked: {error}");
            }
            tracing::warn!("lost control of the stand-in; failing the command");
            steps.kill();
            Err(outcome
                .err()
                .unwrap_or_else(|| io::Error::other("stand-in lost")))
        }
    }
}

fn await_exec_event(steps: &mut dyn Stepper) -> io::Result<bool> {
    let status = steps.wait()?;
    Ok(libc::WIFSTOPPED(status) && event_of(status) == libc::PTRACE_EVENT_EXEC)
}

/// Leaves the tracee where a syscall number can still be rewritten: an exec event can leave
/// the completing `execve`'s exit stop pending, so stepping once is not enough.
fn step_to_syscall_entry(steps: &mut dyn Stepper) -> io::Result<bool> {
    for _ in 0..MAX_STEPS_TO_ENTRY {
        if !step(steps)? {
            return Ok(false);
        }
        if at_syscall_entry(steps)? {
            return Ok(true);
        }
    }
    Ok(false)
}

/// Resumes to the next syscall stop and confirms it got there.
///
/// A signal arriving first (a terminal resize, a child's `SIGCHLD`) is a signal-delivery stop,
/// not a loss of control: it is delivered as the agent sent it and the step goes on. Where it
/// kills the stub, that is the stand-in dying of what was sent to it.
fn step(steps: &mut dyn Stepper) -> io::Result<bool> {
    let mut signal = 0;
    for _ in 0..MAX_SIGNALS_PER_STEP {
        steps.syscall(signal)?;
        let status = steps.wait()?;
        if !libc::WIFSTOPPED(status) {
            return Ok(false);
        }
        let stopped = libc::WSTOPSIG(status);
        let event = event_of(status);
        if stopped == libc::SIGTRAP | 0x80
            || (stopped == libc::SIGTRAP && event == libc::PTRACE_EVENT_SECCOMP)
        {
            return Ok(true);
        }
        if event != 0 || stopped == libc::SIGTRAP {
            return Ok(false);
        }
        signal = stopped;
    }
    Ok(false)
}

/// Whether a stopped tracee is on its way into a syscall. The kernel says outright since 5.3;
/// before that x86-64 parks `-ENOSYS` in the result register at entry, and aarch64 leaves
/// nothing to read, so the stand-in is given up on there.
fn at_syscall_entry(steps: &mut dyn Stepper) -> io::Result<bool> {
    if let Some(kind) = steps.stop_kind()? {
        return Ok(matches!(kind, SyscallStop::Entry | SyscallStop::Seccomp));
    }
    if !ARCH.entry_plants_enosys {
        static BLAME: Once = Once::new();
        BLAME.call_once(|| {
            tracing::error!(
                "this kernel does not answer PTRACE_GET_SYSCALL_INFO, which arrived in Linux \
                 5.3, and on this architecture there is no -ENOSYS parked in the result \
                 register to read instead -- so no command can be stood in for here, and every \
                 one of them will fail. Run the agent on Linux 5.3 or newer."
            );
        });
        return Ok(false);
    }
    Ok(steps.result()? == -i64::from(libc::ENOSYS))
}

/// The real tracee.
struct Live {
    pid: Pid,
    regs: Regs,
    /// The raw status of its death, where a wait here took it.
    died: Option<i32>,
}

impl Stepper for Live {
    fn plant(&mut self, addr: u64, blob: &[u8]) -> io::Result<bool> {
        procfs::write_mem(self.pid, addr, blob)?;
        Ok(procfs::read_mem(self.pid, addr, blob.len())? == blob)
    }
    fn point(&mut self, args: &[(usize, u64)]) -> io::Result<()> {
        for &(i, value) in args {
            self.regs.set_arg(i, value);
        }
        ptrace::setregs(self.pid, &self.regs)
    }
    fn cont(&mut self) -> io::Result<()> {
        restart(false, self.pid, 0)
    }
    fn syscall(&mut self, signal: i32) -> io::Result<()> {
        restart(true, self.pid, signal)
    }
    fn wait(&mut self) -> io::Result<i32> {
        let status = wait_raw(self.pid.as_raw(), 0)?.1;
        if libc::WIFEXITED(status) || libc::WIFSIGNALED(status) {
            self.died = Some(status);
        }
        Ok(status)
    }
    fn stop_kind(&mut self) -> io::Result<Option<SyscallStop>> {
        ptrace::syscall_stop(self.pid)
    }
    fn result(&mut self) -> io::Result<i64> {
        Ok(ptrace::getregs(self.pid)?.result())
    }
    fn kill(&mut self) {
        let _ = nix::sys::signal::kill(self.pid, nix::sys::signal::Signal::SIGKILL);
    }
}

#[cfg(test)]
mod tests {
    use std::collections::VecDeque;

    use super::*;

    const SP: u64 = 0x7fff_f000;

    /// Raw statuses, as `waitpid` reports them.
    const EXEC_EVENT: i32 = (libc::PTRACE_EVENT_EXEC << 16) | (libc::SIGTRAP << 8) | 0x7f;
    const SECCOMP_EVENT: i32 = (libc::PTRACE_EVENT_SECCOMP << 16) | (libc::SIGTRAP << 8) | 0x7f;
    const SYSCALL_STOP: i32 = ((libc::SIGTRAP | 0x80) << 8) | 0x7f;
    const SIGNAL_STOP: i32 = (libc::SIGCHLD << 8) | 0x7f;
    const EXITED: i32 = 0;

    struct Fake {
        writable: bool,
        echo: bool,
        settable: bool,
        statuses: VecDeque<i32>,
        kinds: VecDeque<Option<SyscallStop>>,
        result: i64,
        memory: Vec<(u64, Vec<u8>)>,
        set: Vec<Vec<(usize, u64)>>,
        asked: Vec<&'static str>,
        killed: bool,
    }

    impl Default for Fake {
        fn default() -> Fake {
            Fake {
                writable: true,
                echo: true,
                settable: true,
                statuses: VecDeque::from([EXEC_EVENT, SECCOMP_EVENT]),
                kinds: VecDeque::from([Some(SyscallStop::Seccomp)]),
                result: 0,
                memory: Vec::new(),
                set: Vec::new(),
                asked: Vec::new(),
                killed: false,
            }
        }
    }

    impl Stepper for Fake {
        fn plant(&mut self, addr: u64, blob: &[u8]) -> io::Result<bool> {
            if !self.writable {
                return Err(io::Error::from_raw_os_error(libc::EFAULT));
            }
            self.memory.push((addr, blob.to_vec()));
            Ok(self.echo)
        }
        fn point(&mut self, args: &[(usize, u64)]) -> io::Result<()> {
            if !self.settable {
                return Err(io::Error::from_raw_os_error(libc::ESRCH));
            }
            self.asked.push("setregs");
            self.set.push(args.to_vec());
            Ok(())
        }
        fn cont(&mut self) -> io::Result<()> {
            self.asked.push("cont");
            Ok(())
        }
        fn syscall(&mut self, signal: i32) -> io::Result<()> {
            self.asked.push(if signal == 0 {
                "syscall"
            } else {
                "syscall+signal"
            });
            Ok(())
        }
        fn wait(&mut self) -> io::Result<i32> {
            Ok(self.statuses.pop_front().unwrap_or(SYSCALL_STOP))
        }
        fn stop_kind(&mut self) -> io::Result<Option<SyscallStop>> {
            Ok(self.kinds.pop_front().unwrap_or(Some(SyscallStop::Exit)))
        }
        fn result(&mut self) -> io::Result<i64> {
            Ok(self.result)
        }
        fn kill(&mut self) {
            self.killed = true;
        }
    }

    fn blob() -> Vec<u8> {
        let mut blob = stub().as_bytes().to_vec();
        blob.push(0);
        blob
    }

    #[test]
    fn the_stub_is_a_program_the_kernel_can_load() {
        assert!(nix::unistd::access(stub(), nix::unistd::AccessFlags::X_OK).is_ok());
    }

    #[test]
    fn an_execve_is_pointed_at_the_stub_and_caught_after_it() {
        let mut fake = Fake::default();
        let at = scratch(SP, blob().len());
        park_with(&mut fake, SP, false).unwrap();
        assert_eq!(fake.memory, [(at, blob())]);
        assert_eq!(fake.set, [vec![(0, at)]]);
        assert_eq!(fake.asked, ["setregs", "cont", "syscall"]);
        assert!(!fake.killed);
    }

    #[test]
    fn an_execveat_is_pointed_at_the_stub_from_the_working_directory() {
        let mut fake = Fake::default();
        let at = scratch(SP, blob().len());
        park_with(&mut fake, SP, true).unwrap();
        assert_eq!(fake.set, [vec![(0, (-100i64) as u64), (1, at)]]);
    }

    #[test]
    fn it_steps_past_an_exit_stop_to_the_next_entry() {
        for kind in [SyscallStop::Entry, SyscallStop::Seccomp] {
            let mut fake = Fake {
                statuses: VecDeque::from([EXEC_EVENT, SYSCALL_STOP, SECCOMP_EVENT]),
                kinds: VecDeque::from([Some(SyscallStop::Exit), Some(kind)]),
                ..Fake::default()
            };
            park_with(&mut fake, SP, false).unwrap();
            assert_eq!(fake.asked, ["setregs", "cont", "syscall", "syscall"]);
        }
    }

    #[test]
    fn no_room_for_the_stub_leaves_the_process_where_it_was() {
        for writable in [false, true] {
            let mut fake = Fake {
                writable,
                echo: false,
                ..Fake::default()
            };
            assert!(park_with(&mut fake, SP, false).is_err());
            assert!(fake.asked.is_empty());
            assert!(!fake.killed);
        }
    }

    #[test]
    fn a_stand_in_lost_after_the_exec_is_killed() {
        let entry = Some(SyscallStop::Entry);
        let cases: [(&[i32], Option<SyscallStop>); 5] = [
            (&[EXITED], entry),
            (&[SIGNAL_STOP], entry),
            (&[EXEC_EVENT, EXITED], entry),
            (&[EXEC_EVENT, SIGNAL_STOP, EXITED], entry),
            (
                &[
                    EXEC_EVENT,
                    SYSCALL_STOP,
                    SYSCALL_STOP,
                    SYSCALL_STOP,
                    SYSCALL_STOP,
                ],
                Some(SyscallStop::Exit),
            ),
        ];
        for (statuses, kind) in cases {
            let mut fake = Fake {
                statuses: statuses.iter().copied().collect(),
                kinds: VecDeque::from([kind; 4]),
                ..Fake::default()
            };
            assert!(park_with(&mut fake, SP, false).is_err(), "{statuses:?}");
            assert!(fake.killed, "{statuses:?}");
        }
    }

    #[test]
    fn a_signal_on_the_way_to_the_entry_is_delivered_and_stepped_past() {
        let mut fake = Fake {
            statuses: VecDeque::from([EXEC_EVENT, SIGNAL_STOP, SECCOMP_EVENT]),
            ..Fake::default()
        };
        park_with(&mut fake, SP, false).unwrap();
        assert_eq!(fake.asked, ["setregs", "cont", "syscall", "syscall+signal"]);
        assert!(!fake.killed);
    }

    #[test]
    fn a_tracee_gone_before_the_exec_is_killed_too() {
        let mut fake = Fake {
            settable: false,
            ..Fake::default()
        };
        assert!(park_with(&mut fake, SP, false).is_err());
        assert!(fake.killed);
    }

    #[test]
    fn an_old_kernel_is_read_by_the_enosys_it_parks() {
        for (result, parked) in [(-i64::from(libc::ENOSYS), true), (0, false)] {
            let mut fake = Fake {
                kinds: VecDeque::from([None; 4]),
                result,
                statuses: VecDeque::from([
                    EXEC_EVENT,
                    SYSCALL_STOP,
                    SYSCALL_STOP,
                    SYSCALL_STOP,
                    SYSCALL_STOP,
                ]),
                ..Fake::default()
            };
            let got = park_with(&mut fake, SP, false).is_ok();
            assert_eq!(got, parked && ARCH.entry_plants_enosys, "result {result}");
        }
    }
}

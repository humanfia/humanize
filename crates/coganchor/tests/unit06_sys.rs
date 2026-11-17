//! The Linux sys layer against real tracees: a forked child under the trap filter, its
//! registers read and rewritten, its memory and descriptors reached into. Ports the cases of
//! `tests/unit/coganchor/linux/test_{procfs,ptrace,seccomp,syscalls}.py` that need a process.
#![cfg(target_os = "linux")]

use std::ffi::{CString, OsStr, OsString};
use std::os::fd::{AsRawFd, OwnedFd};
use std::os::unix::ffi::OsStrExt;
use std::path::Path;

use coganchor::sys::procfs::{self, Unresolved};
use coganchor::sys::ptrace::{self, SyscallStop};
use coganchor::sys::syscalls::{nr, trapped};
use coganchor::sys::{ARCH, trap};
use nix::sys::signal::{Signal, kill};
use nix::sys::wait::{WaitPidFlag, WaitStatus, waitpid};
use nix::unistd::{ForkResult, Pid, fork};

/// A pid no process has: above any `pid_max` the kernel allows.
const NOBODY: Pid = Pid::from_raw(1 << 30);

/// Forks a child that asks to be traced, stops itself, and once resumed runs `body`, exiting
/// with what it returns. Returns with the child at that first stop and the cog's options set.
///
/// `body` runs in a fork of a threaded test binary, so it allocates nothing and panics never.
fn traced(body: impl FnOnce() -> i32) -> Pid {
    // SAFETY: the child only makes raw syscalls before exiting with `_exit`.
    match unsafe { fork() }.expect("fork") {
        ForkResult::Child => {
            let code = if ptrace::traceme().is_ok() {
                // SAFETY: raise has no preconditions.
                unsafe { libc::raise(libc::SIGSTOP) };
                body()
            } else {
                99
            };
            // SAFETY: leaving the fork without running the parent's destructors.
            unsafe { libc::_exit(code) }
        }
        ForkResult::Parent { child } => {
            assert_eq!(wait(child), WaitStatus::Stopped(child, Signal::SIGSTOP));
            ptrace::set_cog_options(child).expect("options");
            child
        }
    }
}

fn wait(pid: Pid) -> WaitStatus {
    waitpid(pid, Some(WaitPidFlag::__WALL)).expect("waitpid")
}

/// Kills and reaps a child left at a stop.
fn finish(pid: Pid) {
    let _ = kill(pid, Signal::SIGKILL);
    while !matches!(
        waitpid(pid, Some(WaitPidFlag::__WALL)),
        Ok(WaitStatus::Signaled(..) | WaitStatus::Exited(..)) | Err(_)
    ) {}
}

fn errno() -> i32 {
    std::io::Error::last_os_error().raw_os_error().unwrap_or(0)
}

fn os(bytes: &[u8]) -> OsString {
    OsStr::from_bytes(bytes).to_owned()
}

/// Resumes `pid` and expects it at the trap filter's next stop.
fn to_trap(pid: Pid) {
    ptrace::cont(pid, None).unwrap();
    assert_eq!(
        wait(pid),
        WaitStatus::PtraceEvent(pid, Signal::SIGTRAP, ptrace::EVENT_SECCOMP)
    );
}

#[test]
fn a_cancelled_syscall_returns_the_errno_planted_at_its_exit() {
    let dir = tempfile::tempdir().unwrap();
    let target = CString::new(dir.path().join("made").as_os_str().as_bytes()).unwrap();
    let program = trap::build(&trapped()).unwrap();
    let child = traced(|| {
        if trap::load(&program).is_err() {
            return 2;
        }
        // Not trapped: runs without a stop.
        // SAFETY: integer syscalls on a live NUL-terminated string.
        unsafe { libc::getpid() };
        let done =
            unsafe { libc::syscall(libc::SYS_mkdirat, libc::AT_FDCWD, target.as_ptr(), 0o755) };
        if done == -1 && errno() == libc::EXDEV {
            0
        } else {
            1
        }
    });

    to_trap(child);
    assert!(matches!(
        ptrace::syscall_stop(child).unwrap(),
        Some(SyscallStop::Seccomp) | None
    ));
    let mut regs = ptrace::getregs(child).unwrap();
    assert_eq!(regs.syscall(), nr("mkdirat"));
    assert_eq!(regs.signed_arg(0), libc::AT_FDCWD);
    assert_eq!(regs.arg(2), 0o755);
    assert_eq!(
        procfs::read_cstring(child, regs.arg(1)).unwrap(),
        os(target.as_bytes())
    );

    regs.set_syscall(-1);
    assert_eq!(regs.syscall(), -1);
    ptrace::setregs(child, &regs).unwrap();
    ptrace::syscall(child, None).unwrap();
    assert_eq!(wait(child), WaitStatus::PtraceSyscall(child));
    assert!(matches!(
        ptrace::syscall_stop(child).unwrap(),
        Some(SyscallStop::Exit) | None
    ));

    let mut regs = ptrace::getregs(child).unwrap();
    regs.set_result(-i64::from(libc::EXDEV));
    assert_eq!(regs.result(), -i64::from(libc::EXDEV));
    ptrace::setregs(child, &regs).unwrap();
    ptrace::cont(child, None).unwrap();

    assert_eq!(wait(child), WaitStatus::Exited(child, 0));
    assert!(!dir.path().join("made").exists());
}

#[test]
fn a_rewritten_argument_is_the_path_the_kernel_acts_on() {
    let dir = tempfile::tempdir().unwrap();
    let asked = CString::new(dir.path().join("asked").as_os_str().as_bytes()).unwrap();
    let given = dir.path().join("given");
    let program = trap::build(&trapped()).unwrap();
    let child = traced(|| {
        if trap::load(&program).is_err() {
            return 2;
        }
        // SAFETY: integer syscalls on a live NUL-terminated string.
        let done =
            unsafe { libc::syscall(libc::SYS_mkdirat, libc::AT_FDCWD, asked.as_ptr(), 0o755) };
        if done == 0 { 0 } else { 1 }
    });

    to_trap(child);
    let mut regs = ptrace::getregs(child).unwrap();
    let mut blob = given.as_os_str().as_bytes().to_vec();
    blob.push(0);
    let at = regs.scratch(blob.len() as u64);
    assert_eq!(at, regs.sp() - ARCH.red_zone - blob.len() as u64);
    procfs::write_mem(child, at, &blob).unwrap();
    assert_eq!(procfs::read_mem(child, at, blob.len()).unwrap(), blob);
    regs.set_arg(1, at);
    assert_eq!(regs.arg(1), at);
    ptrace::setregs(child, &regs).unwrap();
    ptrace::cont(child, None).unwrap();

    assert_eq!(wait(child), WaitStatus::Exited(child, 0));
    assert!(given.is_dir());
    assert!(!dir.path().join("asked").exists());
}

#[test]
fn a_cancelled_execve_can_become_exit_group() {
    let program = trap::build(&trapped()).unwrap();
    let path = c"/bin/true";
    let argv = [path.as_ptr(), std::ptr::null()];
    let envp = [std::ptr::null::<libc::c_char>()];
    let child = traced(|| {
        if trap::load(&program).is_err() {
            return 2;
        }
        // SAFETY: NUL-terminated arrays of live strings.
        unsafe { libc::execve(path.as_ptr(), argv.as_ptr(), envp.as_ptr()) };
        3
    });

    to_trap(child);
    let mut regs = ptrace::getregs(child).unwrap();
    assert_eq!(regs.syscall(), nr("execve"));
    assert_eq!(
        procfs::read_strings(child, regs.arg(1)).unwrap(),
        vec![os(b"/bin/true")]
    );
    assert_eq!(
        procfs::read_strings(child, regs.arg(2)).unwrap(),
        Vec::<OsString>::new()
    );
    regs.set_syscall(nr("exit_group"));
    regs.set_arg(0, 42);
    ptrace::setregs(child, &regs).unwrap();
    ptrace::cont(child, None).unwrap();

    assert_eq!(wait(child), WaitStatus::Exited(child, 42));
}

#[test]
fn memory_strings_and_arrays_are_read_out_of_the_child() {
    let page = 4096usize.max(unsafe { libc::sysconf(libc::_SC_PAGESIZE) } as usize);
    let mut buffer = vec![0u8; 3 * page];
    // A string straddling a page boundary.
    let base = buffer.as_ptr() as usize;
    let start = (base / page + 1) * page - 10 - base;
    let strings = [c"first".to_owned(), c"second".to_owned()];
    let array = [strings[0].as_ptr(), strings[1].as_ptr(), std::ptr::null()];
    let raw = buffer.as_mut_ptr();
    let child = traced(|| {
        // Written after the fork, so only the child's memory holds it.
        let text = b"across-a-page-boundary\xff\0";
        for (i, &b) in text.iter().enumerate() {
            // SAFETY: inside the child's copy of `buffer`.
            unsafe { *raw.add(start + i) = b };
        }
        // SAFETY: as in `traced`.
        unsafe { libc::raise(libc::SIGSTOP) };
        0
    });
    ptrace::cont(child, None).unwrap();
    assert_eq!(wait(child), WaitStatus::Stopped(child, Signal::SIGSTOP));
    // A signal-delivery stop is no syscall stop.
    assert!(matches!(
        ptrace::syscall_stop(child).unwrap(),
        Some(SyscallStop::Other) | None
    ));

    let at = (base + start) as u64;
    assert_eq!(
        procfs::read_cstring(child, at).unwrap(),
        os(b"across-a-page-boundary\xff")
    );
    assert_eq!(
        procfs::read_strings(child, array.as_ptr() as u64).unwrap(),
        vec![os(b"first"), os(b"second")]
    );
    assert_eq!(
        procfs::read_strings(child, 0).unwrap(),
        Vec::<OsString>::new()
    );
    assert_eq!(
        procfs::read_cstring(child, 0).unwrap_err().raw_os_error(),
        Some(libc::EFAULT)
    );
    assert!(procfs::read_mem(child, at, 0).unwrap().is_empty());
    procfs::write_mem(child, at, b"rewritten\0").unwrap();
    assert_eq!(procfs::read_cstring(child, at).unwrap(), os(b"rewritten"));
    // The parent's own copy is untouched.
    assert_eq!(buffer[start], 0);

    assert_eq!(procfs::tgid(child).unwrap(), child);
    let me = std::env::current_exe().unwrap();
    assert_eq!(
        procfs::exe_name(child).unwrap(),
        me.file_name().unwrap().to_str().unwrap()
    );
    finish(child);

    let gone = procfs::read_mem(child, at, 8).unwrap_err().raw_os_error();
    assert_eq!(gone, Some(libc::ESRCH));
}

#[test]
fn pending_signals_are_the_blocked_ones_sent() {
    let child = traced(|| {
        // SAFETY: plain signal-mask calls on a stack set.
        unsafe {
            let mut set: libc::sigset_t = std::mem::zeroed();
            libc::sigemptyset(&mut set);
            libc::sigaddset(&mut set, libc::SIGUSR1);
            libc::sigprocmask(libc::SIG_BLOCK, &set, std::ptr::null_mut());
            libc::raise(libc::SIGSTOP);
        }
        0
    });
    ptrace::cont(child, None).unwrap();
    assert_eq!(wait(child), WaitStatus::Stopped(child, Signal::SIGSTOP));
    assert_eq!(procfs::pending_signals(child).unwrap() & (1 << 9), 0);
    kill(child, Signal::SIGUSR1).unwrap();
    assert_ne!(
        procfs::pending_signals(child).unwrap() & (1 << (libc::SIGUSR1 - 1)),
        0
    );
    finish(child);
    assert!(procfs::pending_signals(NOBODY).is_err());
}

#[test]
fn steal_fd_hands_over_the_same_file() {
    let dir = tempfile::tempdir().unwrap();
    let file = std::fs::File::create(dir.path().join("file")).unwrap();
    let held = file.as_raw_fd();
    let child = traced(|| 0);

    let stolen: OwnedFd = procfs::steal_fd(child, held).unwrap();
    assert_ne!(stolen.as_raw_fd(), held);
    let ours = nix::sys::stat::fstat(&file).unwrap();
    let theirs = nix::sys::stat::fstat(&stolen).unwrap();
    assert_eq!((ours.st_dev, ours.st_ino), (theirs.st_dev, theirs.st_ino));
    assert!(procfs::fd_path(child, held).unwrap().ends_with("/file"));
    finish(child);

    assert!(procfs::steal_fd(NOBODY, 1).is_err());
}

#[test]
fn the_working_directory_link_is_the_tracees() {
    let dir = tempfile::tempdir().unwrap();
    let real = dir.path().canonicalize().unwrap();
    let there = CString::new(real.as_os_str().as_bytes()).unwrap();
    let child = traced(|| {
        // SAFETY: a live NUL-terminated string.
        unsafe { libc::chdir(there.as_ptr()) };
        // SAFETY: as in `traced`.
        unsafe { libc::raise(libc::SIGSTOP) };
        0
    });
    ptrace::cont(child, None).unwrap();
    assert_eq!(wait(child), WaitStatus::Stopped(child, Signal::SIGSTOP));

    let real = real.to_str().unwrap();
    assert_eq!(procfs::cwd(child).unwrap(), real);
    for spelling in [
        "/proc/self/cwd/a",
        "/proc/thread-self/cwd/a",
        "/proc/{pid}/cwd/a",
    ] {
        let path = spelling.replace("{pid}", &child.to_string());
        assert_eq!(
            procfs::resolve_magic(child, &path).unwrap(),
            format!("{real}/a")
        );
    }
    finish(child);
}

fn me() -> Pid {
    Pid::this()
}

#[test]
fn a_path_with_no_link_in_it_names_what_it_did() {
    for (path, resolved) in [
        ("/srv/./plain//path/", "/srv/./plain//path/"),
        ("/home/me/proc/self/fd/3", "/home/me/proc/self/fd/3"),
        ("/proc/self/stat", "/proc/self/stat"),
        ("/proc/sys/./kernel//x", "/proc/sys/kernel/x"),
        ("/proc/self/fd", "/proc/self/fd"),
    ] {
        assert_eq!(procfs::resolve_magic(me(), path).unwrap(), resolved);
    }
    assert_eq!(
        procfs::resolve_magic(me(), "//srv/project/x").unwrap(),
        "/srv/project/x"
    );
}

#[test]
fn a_descriptors_link_is_followed() {
    let dir = tempfile::tempdir().unwrap();
    let real = dir.path().canonicalize().unwrap();
    let directory = std::fs::File::open(&real).unwrap();
    let fd = directory.as_raw_fd();
    let pid = me();
    let real = real.to_str().unwrap();
    for spelling in [
        "/proc/self/fd/{fd}/name",
        "/proc/{pid}/fd/{fd}/name",
        "/proc/{pid}/task/{pid}/fd/{fd}/name",
        "/proc/self/task/{pid}/fd/{fd}/name",
        "/proc/thread-self/fd/{fd}/name",
        "/proc/self/fd/{fd}/./sub/../name",
    ] {
        let path = spelling
            .replace("{fd}", &fd.to_string())
            .replace("{pid}", &pid.to_string());
        assert_eq!(
            procfs::resolve_magic(pid, &path).unwrap(),
            format!("{real}/name"),
            "{spelling}"
        );
    }
    // `..` is taken after the link is followed.
    let parent = Path::new(real).parent().unwrap().to_str().unwrap();
    assert_eq!(
        procfs::resolve_magic(pid, &format!("/proc/self/fd/{fd}/../beside")).unwrap(),
        format!("{parent}/beside")
    );
}

#[test]
fn a_link_to_what_is_not_a_file_leaves_the_path_alone() {
    let (read, _write) = nix::unistd::pipe().unwrap();
    let path = format!("/proc/self/fd/{}", read.as_raw_fd());
    assert_eq!(procfs::resolve_magic(me(), &path).unwrap(), path);

    let dir = tempfile::tempdir().unwrap();
    let doomed = dir.path().join("doomed");
    let held = std::fs::File::create(&doomed).unwrap();
    std::fs::remove_file(&doomed).unwrap();
    let path = format!("/proc/self/fd/{}", held.as_raw_fd());
    assert_eq!(procfs::resolve_magic(me(), &path).unwrap(), path);
}

#[test]
fn an_unfollowable_link_is_unresolved() {
    // No process holds a million descriptors; one that is not there fails as a closed one.
    let closed = 1_000_000;
    let error = procfs::resolve_magic(me(), &format!("/proc/self/fd/{closed}/x")).unwrap_err();
    let unresolved = Unresolved::of(&error).expect("an Unresolved");
    assert_eq!(unresolved.errno, libc::ENOENT);

    let error = procfs::resolve_magic(NOBODY, "/proc/self/fd/0").unwrap_err();
    assert!(Unresolved::of(&error).is_some());
    // A tracee gone is not unresolved elsewhere: plain errors.
    let error = procfs::cwd(NOBODY).unwrap_err();
    assert!(Unresolved::of(&error).is_none());
}

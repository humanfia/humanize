//! `coganchor internal fence` run for real on Linux: what a fenced program may write, the
//! statuses the wrapper exits with, and the socket and listen filters answered from outside.
//! Skipped where the kernel has no Landlock (or, for the network, no ABI 4 and user
//! notifications).
#![cfg(target_os = "linux")]

use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::process::{Command, Output};

use coganchor::fence::{landlock, loopback, netfilter};

fn fence(policy: &str, argv: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_coganchor"))
        .args(["internal", "fence", &format!("--policy={policy}"), "--"])
        .args(argv)
        .output()
        .expect("coganchor runs")
}

fn policy(write: &str) -> String {
    format!(
        r#"{{"read":["/"],"write":["{write}"],"online":true,"hosts":[],"tmp":"","scopes":[],"listen":[]}}"#
    )
}

fn stderr(done: &Output) -> String {
    String::from_utf8_lossy(&done.stderr).into_owned()
}

#[test]
fn a_fenced_program_writes_only_what_the_fence_writes() {
    if landlock::abi() < 1 {
        eprintln!("skipped: no Landlock");
        return;
    }
    let dir = tempfile::tempdir_in(env!("CARGO_MANIFEST_DIR")).unwrap();
    let root = std::fs::canonicalize(dir.path()).unwrap();
    let (inside, outside) = (root.join("x"), root.join("y"));
    std::fs::create_dir(&inside).unwrap();
    std::fs::create_dir(&outside).unwrap();
    let script = format!(
        "touch {}/ok && echo ok; touch {}/no 2>&1; echo $TMPDIR",
        inside.display(),
        outside.display()
    );
    let done = fence(&policy(&inside.to_string_lossy()), &["sh", "-c", &script]);
    let said = String::from_utf8_lossy(&done.stdout);
    assert!(done.status.success(), "{}", stderr(&done));
    assert!(said.starts_with("ok\n"), "{said}");
    assert!(said.contains("Permission denied"), "{said}");
    assert!(inside.join("ok").exists());
    assert!(!outside.join("no").exists());
    // The scratch was made for the one run, and is gone.
    let scratch = said.lines().last().unwrap();
    assert!(scratch.contains("hmz-fence-"), "{scratch}");
    assert!(!std::path::Path::new(scratch).exists());
}

#[test]
fn statuses_are_the_programs_or_the_wrappers_own() {
    if landlock::abi() < 1 {
        eprintln!("skipped: no Landlock");
        return;
    }
    let open = policy("/");
    assert_eq!(fence(&open, &["sh", "-c", "exit 7"]).status.code(), Some(7));
    assert_eq!(
        fence(&open, &["sh", "-c", "kill -TERM $$"]).status.code(),
        Some(128 + 15)
    );
    let missing = fence(&open, &["/no/such/program"]);
    assert_eq!(missing.status.code(), Some(127));
    assert!(
        stderr(&missing).starts_with("hmz internal fence: cannot run /no/such/program: "),
        "{}",
        stderr(&missing)
    );
    let bad = fence(r#"{"nope":1}"#, &["true"]);
    assert_eq!(bad.status.code(), Some(126));
    assert_eq!(stderr(&bad), "hmz internal fence: not a fence's: nope\n");
}

#[test]
fn a_scratch_left_a_link_out_is_refused_before_anything_runs() {
    if landlock::abi() < 1 {
        eprintln!("skipped: no Landlock");
        return;
    }
    let dir = tempfile::tempdir_in(env!("CARGO_MANIFEST_DIR")).unwrap();
    let root = std::fs::canonicalize(dir.path()).unwrap();
    let (state, home) = (root.join("state"), root.join("home"));
    std::fs::create_dir(&state).unwrap();
    std::fs::create_dir(&home).unwrap();
    std::os::unix::fs::symlink(&home, state.join("scratch")).unwrap();
    let said = format!(
        r#"{{"read":["/"],"write":["{}"],"tmp":"{}"}}"#,
        state.display(),
        state.join("scratch").display()
    );
    let done = fence(&said, &["sh", "-c", "touch $TMPDIR/x"]);
    assert_eq!(done.status.code(), Some(126));
    assert!(
        stderr(&done).contains("a link where a fenced program could have made one"),
        "{}",
        stderr(&done)
    );
    assert!(!home.join("x").exists());
}

#[test]
fn a_ruleset_keeps_signals_inside_it() {
    if landlock::abi() < 6 {
        eprintln!("skipped: needs Landlock scopes (ABI 6)");
        return;
    }
    // The wrapper is outside the ruleset: a signal to it does not reach.
    let done = fence(
        &policy("/"),
        &["sh", "-c", "kill -0 $PPID 2>/dev/null || echo kept"],
    );
    assert_eq!(String::from_utf8_lossy(&done.stdout), "kept\n");
}

/// The socket and listen filters in a forked child, answered by the supervisor here.
#[test]
fn only_loopback_listens_and_only_tcp_sockets_are_made() {
    if !(landlock::able().net) {
        eprintln!("skipped: this machine cannot cut the network");
        return;
    }
    let mut pair = [0; 2];
    // SAFETY: `pair` is two ints for the kernel to fill.
    assert_eq!(
        unsafe { libc::socketpair(libc::AF_UNIX, libc::SOCK_STREAM, 0, pair.as_mut_ptr()) },
        0
    );
    // SAFETY: the child makes syscalls only, and leaves with `_exit`.
    let pid = unsafe { libc::fork() };
    if pid == 0 {
        // SAFETY: as above.
        unsafe { libc::_exit(child(pair[1])) };
    }
    // SAFETY: the descriptor was just made, and nothing else owns it.
    let ours = unsafe { OwnedFd::from_raw_fd(pair[0]) };
    // SAFETY: as above.
    drop(unsafe { OwnedFd::from_raw_fd(pair[1]) });
    let listener = receive_fd(&ours);
    let _supervisor = loopback::supervise(listener);
    let mut status = 0;
    // SAFETY: `status` is a valid out-pointer.
    unsafe { libc::waitpid(pid, &mut status, 0) };
    assert!(libc::WIFEXITED(status));
    assert_eq!(
        libc::WEXITSTATUS(status),
        0,
        "step {} failed",
        libc::WEXITSTATUS(status)
    );
}

fn receive_fd(socket: &OwnedFd) -> OwnedFd {
    let mut byte = [0u8; 1];
    let mut space = [0u64; 8]; // aligned as a cmsghdr must be
    let mut iov = libc::iovec {
        iov_base: byte.as_mut_ptr().cast(),
        iov_len: 1,
    };
    // SAFETY: an all-zero msghdr is valid to fill in.
    let mut message: libc::msghdr = unsafe { std::mem::zeroed() };
    message.msg_iov = &mut iov;
    message.msg_iovlen = 1;
    message.msg_control = space.as_mut_ptr().cast();
    message.msg_controllen = std::mem::size_of_val(&space) as _;
    // SAFETY: `message` points at buffers alive for the call.
    assert_eq!(
        unsafe { libc::recvmsg(socket.as_raw_fd(), &mut message, 0) },
        1
    );
    // SAFETY: the kernel filled one control message carrying one descriptor.
    unsafe {
        let header = libc::CMSG_FIRSTHDR(&message);
        assert!(!header.is_null());
        let fd = std::ptr::read_unaligned(libc::CMSG_DATA(header) as *const i32);
        OwnedFd::from_raw_fd(fd)
    }
}

/// The child's half: 0 where everything was refused or allowed as it should be, else the
/// number of the step that was not.
fn child(handoff: i32) -> i32 {
    if netfilter::install_socket_filter().is_err() {
        return 1;
    }
    let Ok(listener) = netfilter::install_listener() else {
        return 2;
    };
    let fds = listener.as_raw_fd();
    let mut space = [0u64; 8]; // aligned as a cmsghdr must be
    let mut byte = *b"!";
    let mut iov = libc::iovec {
        iov_base: byte.as_mut_ptr().cast(),
        iov_len: 1,
    };
    // SAFETY: building one SCM_RIGHTS message in `space`, as cmsg(3) does.
    unsafe {
        let mut message: libc::msghdr = std::mem::zeroed();
        message.msg_iov = &mut iov;
        message.msg_iovlen = 1;
        message.msg_control = space.as_mut_ptr().cast();
        message.msg_controllen = libc::CMSG_SPACE(4) as _;
        let header = libc::CMSG_FIRSTHDR(&message);
        (*header).cmsg_level = libc::SOL_SOCKET;
        (*header).cmsg_type = libc::SCM_RIGHTS;
        (*header).cmsg_len = libc::CMSG_LEN(4) as _;
        std::ptr::write_unaligned(libc::CMSG_DATA(header) as *mut i32, fds);
        if libc::sendmsg(handoff, &message, 0) != 1 {
            return 3;
        }
    }
    drop(listener);
    let errno = || std::io::Error::last_os_error().raw_os_error().unwrap_or(0);
    // SAFETY: plain socket syscalls on descriptors this child owns.
    unsafe {
        if libc::socket(libc::AF_INET, libc::SOCK_DGRAM, 0) >= 0 || errno() != libc::EACCES {
            return 4;
        }
        let tcp = libc::socket(libc::AF_INET, libc::SOCK_STREAM, 0);
        if tcp < 0 {
            return 5;
        }
        let mut address: libc::sockaddr_in = std::mem::zeroed();
        address.sin_family = libc::AF_INET as _;
        let size = std::mem::size_of::<libc::sockaddr_in>() as libc::socklen_t;
        // Every address: refused.
        if libc::bind(tcp, (&address as *const libc::sockaddr_in).cast(), size) == 0
            || errno() != libc::EACCES
        {
            return 6;
        }
        // Unbound, listen would bind every address: refused.
        if libc::listen(tcp, 1) == 0 || errno() != libc::EACCES {
            return 7;
        }
        address.sin_addr.s_addr = u32::from_be_bytes([127, 0, 0, 1]).to_be();
        if libc::bind(tcp, (&address as *const libc::sockaddr_in).cast(), size) != 0 {
            return 8;
        }
        if libc::listen(tcp, 1) != 0 {
            return 9;
        }
    }
    0
}

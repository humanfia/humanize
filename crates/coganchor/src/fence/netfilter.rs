//! The seccomp filters that finish cutting the network: one refusing every socket but Unix,
//! netlink and TCP, and one stopping `bind` and `listen` for a supervisor outside to decide.
//! Port of the socket and listen filters of `hmz.coganchor.linux.seccomp`. [Unit 4]
//!
//! Assembled by hand rather than with `seccompiler`, which has no `SECCOMP_RET_USER_NOTIF`
//! and cannot install with `SECCOMP_FILTER_FLAG_NEW_LISTENER`; the two programs are short
//! enough to read as the Python writes them. Also here are the user-notification calls the
//! supervisor ([`crate::fence::loopback`]) answers with.

use std::io;

use crate::fence::policy::last_os_error;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};

#[cfg(target_arch = "x86_64")]
mod nr {
    pub const SOCKET: u32 = 41;
    pub const BIND: u32 = 49;
    pub const LISTEN: u32 = 50;
    pub const IO_URING_SETUP: u32 = 425;
    pub const SECCOMP: libc::c_long = 317;
    pub const PIDFD_GETFD: libc::c_long = 438;
    pub const PIDFD_OPEN: libc::c_long = 434;
    pub const AUDIT_ARCH: u32 = 0xC000_003E;
}

#[cfg(target_arch = "aarch64")]
mod nr {
    pub const SOCKET: u32 = 198;
    pub const BIND: u32 = 200;
    pub const LISTEN: u32 = 201;
    pub const IO_URING_SETUP: u32 = 425;
    pub const SECCOMP: libc::c_long = 277;
    pub const PIDFD_GETFD: libc::c_long = 438;
    pub const PIDFD_OPEN: libc::c_long = 434;
    pub const AUDIT_ARCH: u32 = 0xC000_00B7;
}

#[cfg(not(any(target_arch = "x86_64", target_arch = "aarch64")))]
compile_error!("the fence knows the syscall numbers of x86-64 and aarch64 only");

pub use nr::{BIND, LISTEN, PIDFD_GETFD, PIDFD_OPEN};

const SECCOMP_SET_MODE_FILTER: libc::c_uint = 1;
const SECCOMP_GET_ACTION_AVAIL: libc::c_uint = 2;
const SECCOMP_GET_NOTIF_SIZES: libc::c_uint = 3;
const FILTER_FLAG_NEW_LISTENER: libc::c_uint = 1 << 3;

const RET_ALLOW: u32 = 0x7FFF_0000;
const RET_USER_NOTIF: u32 = 0x7FC0_0000;
const RET_ERRNO: u32 = 0x0005_0000;

// BPF instruction classes and modes, from <linux/filter.h>.
const LD_W_ABS: u16 = 0x20;
const JMP_JEQ_K: u16 = 0x15;
const JMP_JGE_K: u16 = 0x35;
const ALU_AND_K: u16 = 0x54;
const RET_K: u16 = 0x06;

// Offsets into `struct seccomp_data`.
const OFFSET_NR: u32 = 0;
const OFFSET_ARCH: u32 = 4;
const OFFSET_ARGS: u32 = 16;

/// `__X32_SYSCALL_BIT`.
const X32_BIT: u32 = 0x4000_0000;
/// `SOCK_TYPE_MASK`.
const SOCK_TYPE_MASK: u32 = 0xF;

/// `sizeof(struct seccomp_notif)`, `sizeof(struct seccomp_notif_resp)`,
/// `sizeof(struct seccomp_data)`.
const NOTIF_SIZE: usize = 80;
const RESP_SIZE: usize = 24;
const DATA_SIZE: usize = 64;
const USER_NOTIF_FLAG_CONTINUE: u32 = 1;

/// `_IOWR('!', nr, size)`, or `_IOW` where the kernel only reads.
const fn iowr(nr: u64, size: u64, read: bool) -> u64 {
    ((if read { 3 } else { 1 }) << 30) | (size << 16) | ((b'!' as u64) << 8) | nr
}

const IOCTL_NOTIF_RECV: u64 = iowr(0, NOTIF_SIZE as u64, true);
const IOCTL_NOTIF_SEND: u64 = iowr(1, RESP_SIZE as u64, true);
const IOCTL_NOTIF_ID_VALID: u64 = iowr(2, 8, false);

/// `struct seccomp_notif`.
#[repr(C)]
#[derive(Debug, Default, Clone, Copy)]
pub struct Notification {
    /// The kernel's cookie for the call.
    pub id: u64,
    /// The thread that made it.
    pub pid: u32,
    pub flags: u32,
    /// The syscall number.
    pub nr: i32,
    pub arch: u32,
    pub instruction_pointer: u64,
    /// Its six arguments.
    pub args: [u64; 6],
}

/// `struct seccomp_notif_resp`.
#[repr(C)]
struct Response {
    id: u64,
    val: i64,
    error: i32,
    flags: u32,
}

/// One instruction whose jumps may name a label.
enum Step {
    Insn(u16, Jump, Jump, u32),
    Label(&'static str),
}

#[derive(Clone, Copy)]
enum Jump {
    By(u8),
    To(&'static str),
}

use Jump::{By, To};

fn insn(code: u16, jt: Jump, jf: Jump, k: u32) -> Step {
    Step::Insn(code, jt, jf, k)
}

/// A flat program whose jumps name the labels written between its instructions.
fn assemble(body: &[Step]) -> Vec<libc::sock_filter> {
    let mut labels: Vec<(&str, usize)> = Vec::new();
    let mut count = 0;
    for step in body {
        match step {
            Step::Label(name) => labels.push((name, count)),
            Step::Insn(..) => count += 1,
        }
    }
    let target = |at: usize, to: Jump| -> u8 {
        match to {
            By(n) => n,
            To(name) => {
                let (_, there) = labels
                    .iter()
                    .find(|(one, _)| *one == name)
                    .expect("a label");
                u8::try_from(there - at - 1).expect("a jump within reach")
            }
        }
    };
    body.iter()
        .filter_map(|step| match step {
            Step::Insn(code, jt, jf, k) => Some((*code, *jt, *jf, *k)),
            Step::Label(_) => None,
        })
        .enumerate()
        .map(|(at, (code, jt, jf, k))| libc::sock_filter {
            code,
            jt: target(at, jt),
            jf: target(at, jf),
            k,
        })
        .collect()
}

fn arg(index: u32) -> u32 {
    OFFSET_ARGS + 8 * index
}

/// The program refusing every socket but a TCP one, a Unix one or a netlink one, and
/// `io_uring_setup`; a foreign architecture or an x32 number is refused too
/// (`build_socket_program`).
pub fn socket_program() -> Vec<libc::sock_filter> {
    assemble(&[
        insn(LD_W_ABS, By(0), By(0), OFFSET_ARCH),
        insn(JMP_JEQ_K, By(0), To("deny"), nr::AUDIT_ARCH),
        insn(LD_W_ABS, By(0), By(0), OFFSET_NR),
        insn(JMP_JGE_K, To("deny"), By(0), X32_BIT),
        insn(JMP_JEQ_K, To("deny"), By(0), nr::IO_URING_SETUP),
        insn(JMP_JEQ_K, By(0), To("allow"), nr::SOCKET),
        insn(LD_W_ABS, By(0), By(0), arg(0)),
        insn(JMP_JEQ_K, To("allow"), By(0), libc::AF_UNIX as u32),
        insn(JMP_JEQ_K, To("allow"), By(0), libc::AF_NETLINK as u32),
        insn(JMP_JEQ_K, To("inet"), By(0), libc::AF_INET as u32),
        insn(JMP_JEQ_K, By(0), To("deny"), libc::AF_INET6 as u32),
        Step::Label("inet"),
        insn(LD_W_ABS, By(0), By(0), arg(1)),
        insn(ALU_AND_K, By(0), By(0), SOCK_TYPE_MASK),
        insn(JMP_JEQ_K, By(0), To("deny"), libc::SOCK_STREAM as u32),
        insn(LD_W_ABS, By(0), By(0), arg(2)),
        insn(JMP_JEQ_K, To("allow"), By(0), 0),
        insn(JMP_JEQ_K, To("allow"), To("deny"), libc::IPPROTO_TCP as u32),
        Step::Label("allow"),
        insn(RET_K, By(0), By(0), RET_ALLOW),
        Step::Label("deny"),
        insn(RET_K, By(0), By(0), RET_ERRNO | libc::EACCES as u32),
    ])
}

/// The program handing every `bind` and `listen` to a supervisor; a foreign architecture or
/// an x32 number is refused (`build_listen_program`).
pub fn listen_program() -> Vec<libc::sock_filter> {
    assemble(&[
        insn(LD_W_ABS, By(0), By(0), OFFSET_ARCH),
        insn(JMP_JEQ_K, By(0), To("deny"), nr::AUDIT_ARCH),
        insn(LD_W_ABS, By(0), By(0), OFFSET_NR),
        insn(JMP_JGE_K, To("deny"), By(0), X32_BIT),
        insn(JMP_JEQ_K, To("notify"), By(0), nr::BIND),
        insn(JMP_JEQ_K, To("notify"), By(0), nr::LISTEN),
        insn(RET_K, By(0), By(0), RET_ALLOW),
        Step::Label("notify"),
        insn(RET_K, By(0), By(0), RET_USER_NOTIF),
        Step::Label("deny"),
        insn(RET_K, By(0), By(0), RET_ERRNO | libc::EACCES as u32),
    ])
}

/// Sets `no_new_privs` and installs one program; returns what the kernel returned.
fn load(program: &[libc::sock_filter], flags: libc::c_uint) -> io::Result<libc::c_long> {
    // SAFETY: integer arguments only.
    if unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) } != 0 {
        return Err(last_os_error("prctl(PR_SET_NO_NEW_PRIVS)"));
    }
    let fprog = libc::sock_fprog {
        len: u16::try_from(program.len()).expect("a short program"),
        filter: program.as_ptr() as *mut libc::sock_filter,
    };
    // SAFETY: `fprog` and the program it points at outlive the call.
    let done = unsafe {
        libc::syscall(
            nr::SECCOMP,
            SECCOMP_SET_MODE_FILTER,
            flags,
            &fprog as *const libc::sock_fprog,
        )
    };
    if done < 0 {
        return Err(last_os_error("seccomp(SECCOMP_SET_MODE_FILTER)"));
    }
    Ok(done)
}

/// Installs the socket filter on the calling thread.
pub fn install_socket_filter() -> io::Result<()> {
    load(&socket_program(), 0).map(drop)
}

/// Installs the `bind`/`listen` user-notification filter, returning its listener descriptor.
/// `EBUSY` means the caller is already inside a fence that cuts the network.
pub fn install_listener() -> io::Result<OwnedFd> {
    let fd = load(&listen_program(), FILTER_FLAG_NEW_LISTENER)?;
    // SAFETY: the kernel just returned this descriptor, which nothing else owns.
    Ok(unsafe { OwnedFd::from_raw_fd(fd as RawFd) })
}

/// Whether this kernel has user notifications of the sizes this build was written against.
pub fn notifiable() -> bool {
    let action: u32 = RET_USER_NOTIF;
    // SAFETY: `action` is a valid u32 for the kernel to read.
    if unsafe {
        libc::syscall(
            nr::SECCOMP,
            SECCOMP_GET_ACTION_AVAIL,
            0,
            &action as *const u32,
        )
    } != 0
    {
        return false;
    }
    let mut sizes = [0u16; 3];
    // SAFETY: `sizes` is the `struct seccomp_notif_sizes` the kernel writes.
    if unsafe { libc::syscall(nr::SECCOMP, SECCOMP_GET_NOTIF_SIZES, 0, sizes.as_mut_ptr()) } != 0 {
        return false;
    }
    sizes == [NOTIF_SIZE as u16, RESP_SIZE as u16, DATA_SIZE as u16]
}

fn ioctl(fd: RawFd, request: u64, argument: *mut libc::c_void, name: &str) -> io::Result<()> {
    // SAFETY: `argument` points at the struct `request` names, alive for the call.
    if unsafe { libc::ioctl(fd, request as _, argument) } != 0 {
        return Err(last_os_error(name));
    }
    Ok(())
}

/// Waits for the next call a filter stopped. `ENOENT` where the caller went before it could
/// be read.
pub fn receive(listener: &impl AsRawFd) -> io::Result<Notification> {
    let mut said = Notification::default();
    ioctl(
        listener.as_raw_fd(),
        IOCTL_NOTIF_RECV,
        &mut said as *mut Notification as *mut _,
        "SECCOMP_IOCTL_NOTIF_RECV",
    )?;
    Ok(said)
}

/// How a stopped call is answered.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Answer {
    /// Let the kernel run it after all.
    Go,
    /// Fail it with this errno.
    Error(i32),
    /// Return this.
    Value(i64),
}

/// Answers a stopped call.
pub fn respond(listener: &impl AsRawFd, id: u64, answer: Answer) -> io::Result<()> {
    let (val, error, flags) = match answer {
        Answer::Go => (0, 0, USER_NOTIF_FLAG_CONTINUE),
        Answer::Error(errno) => (0, -errno, 0),
        Answer::Value(value) => (value, 0, 0),
    };
    let mut resp = Response {
        id,
        val,
        error,
        flags,
    };
    ioctl(
        listener.as_raw_fd(),
        IOCTL_NOTIF_SEND,
        &mut resp as *mut Response as *mut _,
        "SECCOMP_IOCTL_NOTIF_SEND",
    )
}

/// Whether a call is still stopped, and its caller therefore still the process it was.
pub fn valid(listener: &impl AsRawFd, id: u64) -> bool {
    let mut cookie = id;
    ioctl(
        listener.as_raw_fd(),
        IOCTL_NOTIF_ID_VALID,
        &mut cookie as *mut u64 as *mut _,
        "ID_VALID",
    )
    .is_ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn structures_are_the_sizes_the_kernel_says() {
        assert_eq!(std::mem::size_of::<Notification>(), NOTIF_SIZE);
        assert_eq!(std::mem::size_of::<Response>(), RESP_SIZE);
        assert_eq!(IOCTL_NOTIF_RECV, 0xC050_2100);
        assert_eq!(IOCTL_NOTIF_SEND, 0xC018_2101);
        assert_eq!(IOCTL_NOTIF_ID_VALID, 0x4008_2102);
    }

    #[test]
    fn programs_jump_where_the_python_does() {
        let listen = listen_program();
        assert_eq!(listen.len(), 9);
        // The arch check jumps past everything to the refusal.
        assert_eq!((listen[1].jt, listen[1].jf), (0, 6));
        assert_eq!((listen[4].jt, listen[5].jt), (2, 1));
        let socket = socket_program();
        assert_eq!(socket.len(), 19);
        assert_eq!(socket[18].k, RET_ERRNO | libc::EACCES as u32);
        assert_eq!((socket[16].jt, socket[16].jf), (0, 1));
    }
}

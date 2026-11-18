//! Answering a fenced tree's `bind` and `listen` from outside it: loopback only. Port of
//! `hmz.coganchor.fence.loopback`. [Unit 4]
//!
//! Landlock decides which TCP ports a fenced program may bind, and cannot see the address, so
//! every `bind` and `listen` inside a fence that cuts the network is stopped by the listen
//! filter ([`crate::fence::netfilter`]) and answered here, in the wrapper outside the fence.
//!
//! `listen` is where it is decided: a duplicate of the caller's socket is taken with
//! `pidfd_getfd`, asked what it is bound to, and -- where that is loopback, or the socket is
//! not an internet one -- made to listen here, the answer being what that returned. A socket
//! bound anywhere else, or not bound at all, is refused with `EACCES`. `bind` is answered early
//! for the error to arrive where a program expects it: an internet address off loopback is
//! refused, anything else let run under the caller's own Landlock rules.

use std::io;
use std::net::{Ipv4Addr, Ipv6Addr};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::thread::JoinHandle;

use crate::fence::netfilter::{self, Answer, Notification};

/// `sizeof(struct sockaddr_storage)`.
const SOCKADDR: usize = 128;
/// `sizeof(struct sockaddr_in)` and `SIN6_LEN_RFC2133`.
const INET: usize = 16;
const INET6: usize = 24;
/// `PIDFD_THREAD`, which is `O_EXCL`.
const PIDFD_THREAD: libc::c_uint = libc::O_EXCL as libc::c_uint;
const YAMA: &str = "/proc/sys/kernel/yama/ptrace_scope";

/// Whether a socket address is on loopback (`Some(true)`), an internet address off it or
/// `AF_UNSPEC` (`Some(false)`), or of another family this does not judge (`None`).
pub fn loopback(sockaddr: &[u8]) -> Option<bool> {
    if sockaddr.len() < 2 {
        return None;
    }
    let family = i32::from(u16::from_ne_bytes([sockaddr[0], sockaddr[1]]));
    match family {
        libc::AF_UNSPEC => Some(false),
        libc::AF_INET => Some(
            sockaddr.len() >= INET
                && Ipv4Addr::new(sockaddr[4], sockaddr[5], sockaddr[6], sockaddr[7]).is_loopback(),
        ),
        libc::AF_INET6 => {
            if sockaddr.len() < INET6 {
                return Some(false);
            }
            let octets: [u8; 16] = sockaddr[8..24].try_into().expect("sixteen bytes");
            let address = Ipv6Addr::from(octets);
            Some(match address.to_ipv4_mapped() {
                Some(mapped) => mapped.is_loopback(),
                None => address.is_loopback(),
            })
        }
        _ => None,
    }
}

fn pidfd_open(pid: libc::pid_t, flags: libc::c_uint) -> io::Result<OwnedFd> {
    // SAFETY: integer arguments only.
    let fd = unsafe { libc::syscall(netfilter::PIDFD_OPEN, pid, flags) };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: the kernel just returned this descriptor, which nothing else owns.
    Ok(unsafe { OwnedFd::from_raw_fd(fd as RawFd) })
}

/// `pidfd_getfd`: a descriptor of this process's on another's, or the errno it failed with.
fn getfd(pidfd: &OwnedFd, fd: RawFd) -> Result<OwnedFd, i32> {
    // SAFETY: integer arguments only.
    let held = unsafe { libc::syscall(netfilter::PIDFD_GETFD, pidfd.as_raw_fd(), fd, 0u32) };
    if held < 0 {
        return Err(io::Error::last_os_error()
            .raw_os_error()
            .unwrap_or(libc::EIO));
    }
    // SAFETY: the kernel just returned this descriptor, which nothing else owns.
    Ok(unsafe { OwnedFd::from_raw_fd(held as RawFd) })
}

/// The value of `/proc/sys/kernel/yama/ptrace_scope`, where this kernel has Yama and it reads
/// as a number.
pub fn ptrace_scope() -> Option<i64> {
    std::fs::read_to_string(YAMA).ok()?.trim().parse().ok()
}

/// Whether this process can take another's descriptor with `pidfd_getfd`, as the supervisor
/// answering a fenced tree's binds does.
pub fn pidfd_getfd() -> bool {
    let Ok(pidfd) = pidfd_open(std::process::id() as libc::pid_t, 0) else {
        return false;
    };
    getfd(&pidfd, pidfd.as_raw_fd()).is_ok()
}

/// Whether this machine lets a supervisor take a tracee's descriptor (`ptrace_scope` < 2 and a
/// working `pidfd_getfd`).
pub fn supervisable() -> bool {
    ptrace_scope().is_none_or(|scope| scope < 2) && pidfd_getfd()
}

/// A pidfd on a thread whose descriptors are the ones it names: the thread itself where the
/// kernel opens one on a thread (6.9 on), its thread group otherwise.
fn pidfd(tid: u32) -> io::Result<OwnedFd> {
    let tid = tid as libc::pid_t;
    if let Ok(fd) = pidfd_open(tid, PIDFD_THREAD) {
        return Ok(fd);
    }
    let status = std::fs::read(format!("/proc/{tid}/status"))?;
    let said = String::from_utf8_lossy(&status[..status.len().min(4096)]);
    let tgid = said
        .lines()
        .find_map(|line| line.strip_prefix("Tgid:"))
        .and_then(|rest| rest.trim().parse().ok())
        .unwrap_or(tid);
    pidfd_open(tgid, 0)
}

/// Reads `len` bytes of another process's memory at `at`.
fn read_mem(pid: u32, at: u64, len: usize) -> io::Result<Vec<u8>> {
    let mut buffer = vec![0u8; len];
    if len == 0 {
        return Ok(buffer);
    }
    let local = libc::iovec {
        iov_base: buffer.as_mut_ptr().cast(),
        iov_len: len,
    };
    let remote = libc::iovec {
        iov_base: at as *mut libc::c_void,
        iov_len: len,
    };
    // SAFETY: `local` describes `buffer`, alive and `len` bytes long; `remote` is only read
    // by the kernel, in the other process.
    let done = unsafe { libc::process_vm_readv(pid as libc::pid_t, &local, 1, &remote, 1, 0) };
    if done < 0 {
        return Err(io::Error::last_os_error());
    }
    buffer.truncate(done as usize);
    Ok(buffer)
}

/// Answers the notifications arriving on `listener` from a thread of its own until the fenced
/// tree is gone. The descriptor is closed as the thread ends; from then on the kernel answers
/// every call with `ENOSYS`.
pub fn supervise(listener: OwnedFd) -> JoinHandle<()> {
    std::thread::Builder::new()
        .name("fence-listen".into())
        .spawn(move || {
            if let Err(why) = answering(&listener) {
                tracing::error!("the fence stopped answering its binds: {why}");
            }
        })
        .expect("a thread to answer binds")
}

fn answering(listener: &OwnedFd) -> io::Result<()> {
    loop {
        let mut polled = libc::pollfd {
            fd: listener.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        // SAFETY: `polled` is one valid pollfd.
        if unsafe { libc::poll(&mut polled, 1, -1) } < 0 {
            let why = io::Error::last_os_error();
            if why.raw_os_error() == Some(libc::EINTR) {
                continue;
            }
            return Err(why);
        }
        if polled.revents & (libc::POLLHUP | libc::POLLERR | libc::POLLNVAL) != 0 {
            return Ok(()); // every process the filter held is gone
        }
        if polled.revents & libc::POLLIN == 0 {
            continue;
        }
        let call = match netfilter::receive(listener) {
            Ok(call) => call,
            Err(why)
                if matches!(
                    crate::fence::policy::errno_of(&why),
                    Some(libc::ENOENT | libc::EINTR)
                ) =>
            {
                continue;
            }
            Err(why) => return Err(why),
        };
        answer(listener, &call);
    }
}

/// Answers one call, whatever goes wrong in between: with `EACCES` where it could not be
/// decided.
fn answer(listener: &OwnedFd, call: &Notification) {
    let decided = if call.nr as u32 == netfilter::LISTEN {
        listen(listener, call)
    } else if call.nr as u32 == netfilter::BIND {
        Ok(bind(listener, call))
    } else {
        Ok(Answer::Error(libc::ENOSYS))
    };
    let answer = decided.unwrap_or_else(|why| {
        tracing::error!("the fence could not decide a {}: {why}", call.nr);
        Answer::Error(libc::EACCES)
    });
    // The caller has gone, or was interrupted: nobody to answer.
    let _ = netfilter::respond(listener, call.id, answer);
}

/// `bind(fd, addr, len)`: refused where the address is off loopback, else run.
fn bind(listener: &OwnedFd, call: &Notification) -> Answer {
    let at = call.args[1];
    let length = call.args[2] as i32;
    let Ok(length) = usize::try_from(length) else {
        return Answer::Go; // the kernel refuses it, having read nothing
    };
    if length > SOCKADDR {
        return Answer::Go;
    }
    let Ok(address) = read_mem(call.pid, at, length) else {
        // Not readable, as the kernel will find it too, or not by this process; `listen` is
        // what holds either way.
        return Answer::Go;
    };
    if !netfilter::valid(listener, call.id) {
        return Answer::Go; // read from whatever has the pid now; the answer reaches nobody
    }
    if loopback(&address) == Some(false) {
        Answer::Error(libc::EACCES)
    } else {
        Answer::Go
    }
}

/// `listen(fd, backlog)`: made here, on the socket itself, where it is on loopback.
fn listen(listener: &OwnedFd, call: &Notification) -> io::Result<Answer> {
    let fd = call.args[0] as i32;
    let backlog = call.args[1] as i32;
    let held = {
        let pidfd = pidfd(call.pid)?;
        if !netfilter::valid(listener, call.id) {
            return Ok(Answer::Error(libc::ESRCH)); // not the process it was
        }
        match getfd(&pidfd, fd) {
            Ok(held) => held,
            Err(libc::EBADF) => return Ok(Answer::Error(libc::EBADF)),
            Err(_) => return Ok(Answer::Error(libc::EACCES)),
        }
    };
    let mut name = [0u8; SOCKADDR];
    let mut size = SOCKADDR as libc::socklen_t;
    // SAFETY: `name` is `size` bytes long.
    if unsafe { libc::getsockname(held.as_raw_fd(), name.as_mut_ptr().cast(), &mut size) } != 0 {
        return Ok(Answer::Error(last_errno()));
    }
    if loopback(&name[..(size as usize).min(SOCKADDR)]) == Some(false) {
        return Ok(Answer::Error(libc::EACCES));
    }
    // SAFETY: integer arguments only.
    if unsafe { libc::listen(held.as_raw_fd(), backlog) } != 0 {
        return Ok(Answer::Error(last_errno()));
    }
    Ok(Answer::Value(0))
}

fn last_errno() -> i32 {
    io::Error::last_os_error()
        .raw_os_error()
        .unwrap_or(libc::EIO)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn inet(address: [u8; 4]) -> Vec<u8> {
        let mut said = (libc::AF_INET as u16).to_ne_bytes().to_vec();
        said.extend([0, 0]);
        said.extend(address);
        said.extend([0; 8]);
        said
    }

    fn inet6(address: Ipv6Addr) -> Vec<u8> {
        let mut said = (libc::AF_INET6 as u16).to_ne_bytes().to_vec();
        said.extend([0; 6]);
        said.extend(address.octets());
        said.extend([0; 4]);
        said
    }

    #[test]
    fn loopback_is_told_from_everywhere_else() {
        assert_eq!(loopback(&inet([127, 0, 0, 1])), Some(true));
        assert_eq!(loopback(&inet([127, 9, 9, 9])), Some(true));
        assert_eq!(loopback(&inet([0, 0, 0, 0])), Some(false));
        assert_eq!(loopback(&inet([10, 0, 0, 1])[..8]), Some(false));
        assert_eq!(loopback(&inet6(Ipv6Addr::LOCALHOST)), Some(true));
        assert_eq!(loopback(&inet6(Ipv6Addr::UNSPECIFIED)), Some(false));
        assert_eq!(
            loopback(&inet6(Ipv4Addr::new(127, 0, 0, 1).to_ipv6_mapped())),
            Some(true)
        );
        assert_eq!(
            loopback(&(libc::AF_UNSPEC as u16).to_ne_bytes()),
            Some(false)
        );
        assert_eq!(loopback(&(libc::AF_UNIX as u16).to_ne_bytes()), None);
        assert_eq!(loopback(&[1]), None);
    }

    #[test]
    fn probes_agree_with_supervision() {
        assert_eq!(
            supervisable(),
            ptrace_scope().is_none_or(|scope| scope < 2) && pidfd_getfd()
        );
        if let Some(scope) = ptrace_scope() {
            assert!(scope >= 0, "ptrace_scope is {scope}");
        }
    }
}

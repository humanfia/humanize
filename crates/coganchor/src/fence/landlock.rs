//! Landlock: the paths and TCP ports a process tree may use. Port of
//! `hmz.coganchor.linux.landlock`. [Unit 4]
//!
//! Spoken in raw syscalls rather than through the `landlock` crate: the crate's
//! compatibility layer decides on its own which rights to drop on an older kernel, where this
//! has to grant exactly the masks the Python grants (a right too new for the kernel dropped,
//! network rules never dropped), and to grant the very descriptors [`Fence::ready`] opened
//! and checked rather than look a path up again.
//!
//! [`Fence::ready`]: crate::fence::Fence::ready

use std::ffi::CString;
use std::io;

use crate::fence::policy::last_os_error;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::ffi::OsStrExt;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use crate::fence::{Able, loopback, netfilter};

// One number apiece on every architecture.
const NR_CREATE_RULESET: libc::c_long = 444;
const NR_ADD_RULE: libc::c_long = 445;
const NR_RESTRICT_SELF: libc::c_long = 446;

const CREATE_RULESET_VERSION: u32 = 1 << 0;
const RULE_PATH_BENEATH: libc::c_int = 1;
const RULE_NET_PORT: libc::c_int = 2;

// `LANDLOCK_ACCESS_FS_*`, from <linux/landlock.h>.
const FS_EXECUTE: u64 = 1 << 0;
const FS_WRITE_FILE: u64 = 1 << 1;
const FS_READ_FILE: u64 = 1 << 2;
const FS_READ_DIR: u64 = 1 << 3;
const FS_REFER: u64 = 1 << 13; // ABI 2
const FS_TRUNCATE: u64 = 1 << 14; // ABI 3
const FS_IOCTL_DEV: u64 = 1 << 15; // ABI 5
/// The thirteen rights ABI 1 already had, `EXECUTE` through `MAKE_SYM`.
const FS_ABI1: u64 = (1 << 13) - 1;
/// The rights that mean anything on a file rather than a directory.
const FS_FILE: u64 = FS_EXECUTE | FS_WRITE_FILE | FS_READ_FILE | FS_TRUNCATE | FS_IOCTL_DEV;
/// What "read" grants: open and list, and run what is there.
const FS_READ: u64 = FS_EXECUTE | FS_READ_FILE | FS_READ_DIR;

// `LANDLOCK_ACCESS_NET_*`, ABI 4.
const NET_BIND_TCP: u64 = 1 << 0;
const NET_CONNECT_TCP: u64 = 1 << 1;
/// The first ABI that can govern TCP at all.
pub const NET_ABI: u32 = 4;

// `LANDLOCK_SCOPE_*`, ABI 6.
const SCOPE_ABSTRACT_UNIX_SOCKET: u64 = 1 << 0;
const SCOPE_SIGNAL: u64 = 1 << 1;
/// The first ABI that confines signals and abstract Unix sockets to the ruleset.
pub const SCOPE_ABI: u32 = 6;

/// Why a path is left out of a ruleset rather than failing it (`_UNREACHABLE`).
const UNREACHABLE: [i32; 4] = [libc::ENOENT, libc::ENOTDIR, libc::EACCES, libc::ELOOP];

/// `struct landlock_path_beneath_attr`, which the kernel declares packed.
#[repr(C, packed)]
struct PathBeneath {
    allowed_access: u64,
    parent_fd: i32,
}

/// `struct landlock_net_port_attr`.
#[repr(C)]
struct NetPort {
    allowed_access: u64,
    port: u64,
}

/// `struct landlock_ruleset_attr`, as far as ABI 6.
#[repr(C)]
struct RulesetAttr {
    handled_access_fs: u64,
    handled_access_net: u64,
    scoped: u64,
}

/// The ABI version this kernel speaks, 0 where it has no Landlock.
pub fn abi() -> u32 {
    static ABI: OnceLock<u32> = OnceLock::new();
    *ABI.get_or_init(|| {
        // SAFETY: asking for the version passes no memory.
        let done = unsafe {
            libc::syscall(
                NR_CREATE_RULESET,
                std::ptr::null::<libc::c_void>(),
                0usize,
                CREATE_RULESET_VERSION,
            )
        };
        u32::try_from(done).unwrap_or(0)
    })
}

/// Whether a ruleset can be enforced here: ABI 1, or ABI 4 where it governs TCP.
pub fn available(net: bool) -> bool {
    abi() >= if net { NET_ABI } else { 1 }
}

/// Whether this kernel can confine signals and abstract Unix sockets to the ruleset.
pub fn scopes_sockets() -> bool {
    abi() >= SCOPE_ABI
}

/// What this machine can fence: ABI 1 for paths; ABI 4, the socket filter and loopback
/// supervision for the network too.
pub fn able() -> Able {
    static ABLE: OnceLock<Able> = OnceLock::new();
    *ABLE.get_or_init(|| Able {
        fs: available(false),
        net: available(true) && netfilter::notifiable() && loopback::supervisable(),
    })
}

/// Every filesystem right an ABI version can govern (`handled_fs`).
pub fn handled_fs(version: u32) -> u64 {
    let mut mask = if version >= 1 { FS_ABI1 } else { 0 };
    if version >= 2 {
        mask |= FS_REFER;
    }
    if version >= 3 {
        mask |= FS_TRUNCATE;
    }
    if version >= 5 {
        mask |= FS_IOCTL_DEV;
    }
    mask
}

/// The rights one path is granted (`fs_rights`).
pub fn fs_rights(version: u32, write: bool, directory: bool) -> u64 {
    let rights = if write {
        handled_fs(version)
    } else {
        FS_READ & handled_fs(version)
    };
    if directory { rights } else { rights & FS_FILE }
}

/// A ruleset to restrict the calling thread, and everything it later starts, to.
#[derive(Debug, Default)]
pub struct Ruleset {
    /// Paths that may be read and executed.
    pub read: Vec<PathBuf>,
    /// Directories (opened `O_PATH`) that may also be written.
    pub write: Vec<OwnedFd>,
    /// TCP ports that may be connected to, where `net` governs the network.
    pub connect_ports: Vec<u16>,
    /// TCP ports that may be bound (0 for any ephemeral one), where `net` governs it.
    pub bind_ports: Vec<u16>,
    /// Whether to govern TCP at all.
    pub net: bool,
}

impl Ruleset {
    /// Applies the ruleset to the calling thread, after setting `no_new_privs`. Call in a
    /// freshly forked child just before `execve`.
    ///
    /// A path that is not there, or cannot be reached to begin with, is left out rather than
    /// failing the call. On ABI 6 and later a signal, and a connection to an abstract Unix
    /// socket, cannot reach a process outside the ruleset.
    pub fn restrict_self(&self) -> io::Result<()> {
        let version = abi();
        if (!self.connect_ports.is_empty() || !self.bind_ports.is_empty()) && !self.net {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "ports were given for a ruleset that does not govern TCP",
            ));
        }
        if !available(self.net) {
            let needs = if self.net {
                format!("ABI {NET_ABI} to govern TCP")
            } else {
                "Landlock".to_owned()
            };
            return Err(io::Error::other(format!(
                "this kernel speaks Landlock ABI {version}; needs {needs}"
            )));
        }
        let scoped = if version >= SCOPE_ABI {
            SCOPE_ABSTRACT_UNIX_SOCKET | SCOPE_SIGNAL
        } else {
            0
        };
        let attr = RulesetAttr {
            handled_access_fs: handled_fs(version),
            handled_access_net: if self.net {
                NET_BIND_TCP | NET_CONNECT_TCP
            } else {
                0
            },
            scoped,
        };
        let size: usize = if scoped != 0 {
            24
        } else if self.net {
            16
        } else {
            8
        };
        // SAFETY: `attr` outlives the call and is at least `size` bytes.
        let done =
            unsafe { libc::syscall(NR_CREATE_RULESET, &attr as *const RulesetAttr, size, 0u32) };
        if done < 0 {
            return Err(last_os_error("landlock_create_ruleset"));
        }
        // SAFETY: the kernel just returned this descriptor, which nothing else owns.
        let ruleset = unsafe { OwnedFd::from_raw_fd(done as RawFd) };
        for path in &self.read {
            add_path(&ruleset, path, version)?;
        }
        for fd in &self.write {
            add_held(&ruleset, fd.as_raw_fd(), version, true)?;
        }
        for (ports, right) in [
            (&self.connect_ports, NET_CONNECT_TCP),
            (&self.bind_ports, NET_BIND_TCP),
        ] {
            for port in ports {
                let rule = NetPort {
                    allowed_access: right,
                    port: u64::from(*port),
                };
                add_rule(&ruleset, RULE_NET_PORT, &rule as *const NetPort as *const _)?;
            }
        }
        // SAFETY: prctl with integer arguments only.
        if unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) } != 0 {
            return Err(last_os_error("prctl(PR_SET_NO_NEW_PRIVS)"));
        }
        // SAFETY: integer arguments only.
        if unsafe { libc::syscall(NR_RESTRICT_SELF, ruleset.as_raw_fd(), 0u32) } < 0 {
            return Err(last_os_error("landlock_restrict_self"));
        }
        Ok(())
    }
}

fn add_rule(ruleset: &OwnedFd, kind: libc::c_int, attr: *const libc::c_void) -> io::Result<()> {
    // SAFETY: `attr` points at the attribute struct `kind` names, alive for the call.
    let done = unsafe { libc::syscall(NR_ADD_RULE, ruleset.as_raw_fd(), kind, attr, 0u32) };
    if done < 0 {
        return Err(last_os_error("landlock_add_rule"));
    }
    Ok(())
}

/// Grants one path to read, or nothing where there is nothing there to grant.
fn add_path(ruleset: &OwnedFd, path: &Path, version: u32) -> io::Result<()> {
    let Ok(name) = CString::new(path.as_os_str().as_bytes()) else {
        return Ok(()); // a name with a NUL in it names nothing
    };
    // SAFETY: `name` is NUL-terminated and alive for the call.
    let fd = unsafe { libc::open(name.as_ptr(), libc::O_PATH | libc::O_CLOEXEC) };
    if fd < 0 {
        let why = io::Error::last_os_error();
        if why
            .raw_os_error()
            .is_some_and(|errno| UNREACHABLE.contains(&errno))
        {
            return Ok(());
        }
        return Err(crate::fence::policy::os_error(
            why.raw_os_error().unwrap_or(libc::EIO),
            path.to_string_lossy(),
        ));
    }
    // SAFETY: just opened, owned here.
    let held = unsafe { OwnedFd::from_raw_fd(fd) };
    add_held(ruleset, held.as_raw_fd(), version, false)
}

/// Grants the file or directory a descriptor holds, as it is.
fn add_held(ruleset: &OwnedFd, fd: RawFd, version: u32, write: bool) -> io::Result<()> {
    // SAFETY: an all-zero `stat` is a valid value to be overwritten.
    let mut seen: libc::stat = unsafe { std::mem::zeroed() };
    // SAFETY: `seen` is a valid out-pointer.
    if unsafe { libc::fstat(fd, &mut seen) } != 0 {
        return Err(last_os_error("fstat"));
    }
    let directory = seen.st_mode & libc::S_IFMT == libc::S_IFDIR;
    let rule = PathBeneath {
        allowed_access: fs_rights(version, write, directory),
        parent_fd: fd,
    };
    add_rule(
        ruleset,
        RULE_PATH_BENEATH,
        &rule as *const PathBeneath as *const _,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn probes_follow_the_kernel_abi() {
        assert_eq!(NET_ABI, 4);
        assert_eq!(SCOPE_ABI, 6);
        assert_eq!(available(false), abi() >= 1);
        assert_eq!(available(true), abi() >= NET_ABI);
        assert_eq!(scopes_sockets(), abi() >= SCOPE_ABI);
    }

    #[test]
    fn rights_follow_the_abi() {
        assert_eq!(handled_fs(0), 0);
        assert_eq!(handled_fs(1), (1 << 13) - 1);
        assert_eq!(handled_fs(2), (1 << 14) - 1);
        assert_eq!(handled_fs(4), (1 << 15) - 1);
        assert_eq!(handled_fs(5), (1 << 16) - 1);
        assert_eq!(fs_rights(5, false, true), 0b1101);
        assert_eq!(fs_rights(5, false, false), 0b0101);
        assert_eq!(fs_rights(1, true, false), 0b0111);
        assert_eq!(fs_rights(5, true, false), FS_FILE);
        assert_eq!(std::mem::size_of::<PathBeneath>(), 12);
    }
}

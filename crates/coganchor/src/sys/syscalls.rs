//! Syscall numbers and the facts about an architecture the tracers need. [Unit 6]

/// What differs between architectures, written down once.
#[derive(Debug)]
pub struct Arch {
    /// `AUDIT_ARCH_*` as seccomp sees it.
    pub audit: u32,
    /// Bytes below the stack pointer the ABI lets a leaf function use (128 on x86-64).
    pub red_zone: u64,
    /// `O_DIRECTORY`, which aarch64 spells differently.
    pub o_directory: i32,
    /// Whether a syscall-entry stop already holds `-ENOSYS` in the result register.
    pub entry_plants_enosys: bool,
}

#[cfg(target_arch = "x86_64")]
pub const ARCH: Arch = Arch {
    audit: 0xC000_003E,
    red_zone: 128,
    o_directory: 0o200000,
    entry_plants_enosys: true,
};

#[cfg(target_arch = "aarch64")]
pub const ARCH: Arch = Arch {
    audit: 0xC000_00B7,
    red_zone: 0,
    o_directory: 0o40000,
    entry_plants_enosys: false,
};

#[cfg(not(any(target_arch = "x86_64", target_arch = "aarch64")))]
compile_error!("coganchor's tracers know the register maps of x86-64 and aarch64 only");

/// x86-64's own table, from `<asm/unistd_64.h>`: every call the cog names, under the names
/// `hmz.coganchor.linux.syscalls.Numbers` gives them (`X86_64_NUMBERS`).
#[cfg_attr(not(target_arch = "x86_64"), allow(dead_code))]
const X86_64: &[(&str, i64)] = &[
    ("execve", 59),
    ("execveat", 322),
    ("exit_group", 231),
    ("open", 2),
    ("openat", 257),
    ("openat2", 437),
    ("creat", 85),
    ("stat", 4),
    ("lstat", 6),
    ("newfstatat", 262),
    ("statx", 332),
    ("access", 21),
    ("faccessat", 269),
    ("faccessat2", 439),
    ("readlink", 89),
    ("readlinkat", 267),
    ("chdir", 80),
    ("statfs", 137),
    ("getxattr", 191),
    ("lgetxattr", 192),
    ("listxattr", 194),
    ("llistxattr", 195),
    ("name_to_handle_at", 303),
    ("open_tree", 428),
    ("inotify_add_watch", 254),
    ("fanotify_mark", 301),
    ("mkdir", 83),
    ("mkdirat", 258),
    ("rmdir", 84),
    ("unlink", 87),
    ("unlinkat", 263),
    ("rename", 82),
    ("renameat", 264),
    ("renameat2", 316),
    ("symlink", 88),
    ("symlinkat", 266),
    ("link", 86),
    ("linkat", 265),
    ("chmod", 90),
    ("fchmodat", 268),
    ("fchmodat2", 452),
    ("truncate", 76),
    ("utimensat", 280),
    ("utimes", 235),
    ("utime", 132),
    ("futimesat", 261),
    ("chown", 92),
    ("lchown", 94),
    ("fchownat", 260),
    ("mknod", 133),
    ("mknodat", 259),
    ("setxattr", 188),
    ("lsetxattr", 189),
    ("removexattr", 197),
    ("lremovexattr", 198),
    ("connect", 42),
    ("socket", 41),
    ("bind", 49),
    ("listen", 50),
    ("io_uring_setup", 425),
    ("seccomp", 317),
    ("pidfd_open", 434),
    ("pidfd_getfd", 438),
    ("process_vm_readv", 310),
    ("process_vm_writev", 311),
];

/// aarch64's table, the generic one of `<asm-generic/unistd.h>` (`AARCH64_NUMBERS`). A 64-bit
/// architecture added after the `*at` calls existed got only those, so the nineteen calls libc
/// synthesises from them (`open`, `creat`, `stat`, `lstat`, `access`, `readlink`, `mkdir`,
/// `rmdir`, `unlink`, `rename`, `symlink`, `link`, `chmod`, `utimes`, `utime`, `futimesat`,
/// `chown`, `lchown`, `mknod`) are not here at all, and [`number`] answers `None` for them
/// rather than handing out a placeholder.
#[cfg_attr(not(target_arch = "aarch64"), allow(dead_code))]
const AARCH64: &[(&str, i64)] = &[
    ("execve", 221),
    ("execveat", 281),
    ("exit_group", 94),
    ("openat", 56),
    ("openat2", 437),
    ("newfstatat", 79),
    ("statx", 291),
    ("faccessat", 48),
    ("faccessat2", 439),
    ("readlinkat", 78),
    ("chdir", 49),
    ("statfs", 43),
    ("getxattr", 8),
    ("lgetxattr", 9),
    ("listxattr", 11),
    ("llistxattr", 12),
    ("name_to_handle_at", 264),
    ("open_tree", 428),
    ("inotify_add_watch", 27),
    ("fanotify_mark", 263),
    ("mkdirat", 34),
    ("unlinkat", 35),
    ("renameat", 38),
    ("renameat2", 276),
    ("symlinkat", 36),
    ("linkat", 37),
    ("fchmodat", 53),
    ("fchmodat2", 452),
    ("truncate", 45),
    ("utimensat", 88),
    ("fchownat", 54),
    ("mknodat", 33),
    ("setxattr", 5),
    ("lsetxattr", 6),
    ("removexattr", 14),
    ("lremovexattr", 15),
    ("connect", 203),
    ("socket", 198),
    ("bind", 200),
    ("listen", 201),
    ("io_uring_setup", 425),
    ("seccomp", 277),
    ("pidfd_open", 434),
    ("pidfd_getfd", 438),
    ("process_vm_readv", 270),
    ("process_vm_writev", 271),
];

#[cfg(target_arch = "x86_64")]
const TABLE: &[(&str, i64)] = X86_64;
#[cfg(target_arch = "aarch64")]
const TABLE: &[(&str, i64)] = AARCH64;

/// The number of the syscall `name` on this architecture, `None` where it has none (aarch64
/// has no `open`, `stat`, `readlink`, ...).
pub fn number(name: &str) -> Option<i64> {
    TABLE.iter().find(|(n, _)| *n == name).map(|&(_, nr)| nr)
}

/// The name of syscall `number`, for logs and dispatch. Only the calls the cog names are
/// known; Python's `syscall_name` spells any other one `syscall_<n>`, which a caller logging
/// one can do with the `None`.
pub fn name(number: i64) -> Option<&'static str> {
    TABLE.iter().find(|&&(_, nr)| nr == number).map(|&(n, _)| n)
}

/// The number of a syscall every supported architecture has (`exit_group`, `pidfd_open`,
/// `openat`, ...). Panics on a name outside this architecture's table: that is a typo in the
/// caller, not a fact about the host.
pub fn nr(name: &str) -> i64 {
    number(name).unwrap_or_else(|| panic!("no syscall {name} on this architecture"))
}

/// Every syscall the cog's trap filter stops: those naming a path, starting a program, or
/// opening a connection, by name, whether or not this architecture has them
/// (`Numbers.trapped`). Everything else -- `read`, `write`, `mmap`, `futex`, `getdents64` --
/// runs untouched, at native speed.
pub const TRAPPED: &[&str] = &[
    "execve",
    "execveat",
    "open",
    "openat",
    "openat2",
    "creat",
    "stat",
    "lstat",
    "newfstatat",
    "statx",
    "access",
    "faccessat",
    "faccessat2",
    "readlink",
    "readlinkat",
    "chdir",
    "statfs",
    "getxattr",
    "lgetxattr",
    "listxattr",
    "llistxattr",
    "name_to_handle_at",
    "open_tree",
    "inotify_add_watch",
    "fanotify_mark",
    "mkdir",
    "mkdirat",
    "rmdir",
    "unlink",
    "unlinkat",
    "rename",
    "renameat",
    "renameat2",
    "symlink",
    "symlinkat",
    "link",
    "linkat",
    "chmod",
    "fchmodat",
    "fchmodat2",
    "truncate",
    "utimensat",
    "utimes",
    "utime",
    "futimesat",
    "chown",
    "lchown",
    "fchownat",
    "mknod",
    "mknodat",
    "setxattr",
    "lsetxattr",
    "removexattr",
    "lremovexattr",
    "connect",
];

/// The numbers of [`TRAPPED`] this architecture has, ascending and without repeats: what the
/// trap filter is built from (`TRAPPED_SYSCALLS`).
pub fn trapped() -> Vec<i64> {
    let mut numbers: Vec<i64> = TRAPPED.iter().filter_map(|name| number(name)).collect();
    numbers.sort_unstable();
    numbers.dedup();
    numbers
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_call_has_a_number_and_a_name_of_its_own() {
        for table in [X86_64, AARCH64] {
            let mut numbers: Vec<i64> = table.iter().map(|&(_, nr)| nr).collect();
            numbers.sort_unstable();
            numbers.dedup();
            assert_eq!(numbers.len(), table.len());
            let mut names: Vec<&str> = table.iter().map(|&(n, _)| n).collect();
            names.sort_unstable();
            names.dedup();
            assert_eq!(names.len(), table.len());
        }
    }

    #[test]
    fn every_trapped_call_is_named_in_the_x86_64_table() {
        for name in TRAPPED {
            assert!(X86_64.iter().any(|(n, _)| n == name), "{name}");
        }
    }

    #[test]
    fn a_call_an_architecture_lacks_is_never_trapped() {
        let trapped = trapped();
        assert!(trapped.windows(2).all(|w| w[0] < w[1]));
        assert!(trapped.iter().all(|&n| n >= 0 && name(n).is_some()));
        #[cfg(target_arch = "aarch64")]
        {
            assert_eq!(number("open"), None);
            assert_eq!(number("stat"), None);
            assert_eq!(trapped.len(), TRAPPED.len() - 19);
        }
        #[cfg(target_arch = "x86_64")]
        assert_eq!(trapped.len(), TRAPPED.len());
    }

    #[test]
    fn the_cold_calls_are_trapped_and_the_rest_are_not() {
        let trapped = trapped();
        for call in ["execve", "openat", "connect", "newfstatat", "unlinkat"] {
            assert!(trapped.contains(&nr(call)), "{call}");
        }
        for call in ["exit_group", "socket", "pidfd_getfd", "process_vm_readv"] {
            assert!(!trapped.contains(&nr(call)), "{call}");
        }
    }

    #[test]
    fn the_tables_are_the_kernels() {
        // libc's numbers are the kernel header's; the tables above were copied by hand. Only
        // `fchmodat2` (452 on both) is too new for libc to name.
        for (name, nr) in TABLE {
            let theirs = match *name {
                "execve" => libc::SYS_execve,
                "execveat" => libc::SYS_execveat,
                "exit_group" => libc::SYS_exit_group,
                "openat" => libc::SYS_openat,
                "openat2" => libc::SYS_openat2,
                "newfstatat" => libc::SYS_newfstatat,
                "statx" => libc::SYS_statx,
                "faccessat" => libc::SYS_faccessat,
                "faccessat2" => libc::SYS_faccessat2,
                "readlinkat" => libc::SYS_readlinkat,
                "chdir" => libc::SYS_chdir,
                "statfs" => libc::SYS_statfs,
                "getxattr" => libc::SYS_getxattr,
                "lgetxattr" => libc::SYS_lgetxattr,
                "listxattr" => libc::SYS_listxattr,
                "llistxattr" => libc::SYS_llistxattr,
                "name_to_handle_at" => libc::SYS_name_to_handle_at,
                "open_tree" => libc::SYS_open_tree,
                "inotify_add_watch" => libc::SYS_inotify_add_watch,
                "fanotify_mark" => libc::SYS_fanotify_mark,
                "mkdirat" => libc::SYS_mkdirat,
                "unlinkat" => libc::SYS_unlinkat,
                "renameat" => libc::SYS_renameat,
                "renameat2" => libc::SYS_renameat2,
                "symlinkat" => libc::SYS_symlinkat,
                "linkat" => libc::SYS_linkat,
                "fchmodat" => libc::SYS_fchmodat,
                "truncate" => libc::SYS_truncate,
                "utimensat" => libc::SYS_utimensat,
                "fchownat" => libc::SYS_fchownat,
                "mknodat" => libc::SYS_mknodat,
                "setxattr" => libc::SYS_setxattr,
                "lsetxattr" => libc::SYS_lsetxattr,
                "removexattr" => libc::SYS_removexattr,
                "lremovexattr" => libc::SYS_lremovexattr,
                "connect" => libc::SYS_connect,
                "socket" => libc::SYS_socket,
                "bind" => libc::SYS_bind,
                "listen" => libc::SYS_listen,
                "io_uring_setup" => libc::SYS_io_uring_setup,
                "seccomp" => libc::SYS_seccomp,
                "pidfd_open" => libc::SYS_pidfd_open,
                "pidfd_getfd" => libc::SYS_pidfd_getfd,
                "process_vm_readv" => libc::SYS_process_vm_readv,
                "process_vm_writev" => libc::SYS_process_vm_writev,
                _ => continue,
            };
            assert_eq!(*nr, theirs, "{name}");
        }
    }

    #[test]
    fn syscall_names() {
        assert_eq!(name(nr("execve")), Some("execve"));
        assert_eq!(name(nr("openat")), Some("openat"));
        assert_eq!(name(-1), None);
        assert_eq!(name(99_999), None);
    }
}

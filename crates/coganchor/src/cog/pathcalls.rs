//! The syscalls that name a path, and where each keeps them. Port of
//! `hmz.coganchor.pathcalls`. [Unit 8]
//!
//! One table, read by both tracers that answer a path with another: the cog's supervisor and
//! the cred tracer. What each then does with a call is its own business; what is here is only
//! what the manual pages say -- which calls name a path, in which argument, against which
//! descriptor, and which of them only look a path up or make something at it.
//!
//! `execve` is deliberately absent: what a process becomes is the exec bridge's business.

/// Where one path argument of a call is.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PathArg {
    /// The argument holding the path.
    pub path: usize,
    /// The argument holding the directory descriptor it is relative to, if the call has one.
    pub dirfd: Option<usize>,
}

/// One call that names paths.
#[derive(Clone, Copy, Debug)]
pub struct PathCall {
    pub name: &'static str,
    pub args: &'static [PathArg],
    /// Only looks a path up (stat, access, readlink, ...): `pathcalls.LOOKS`.
    pub looks: bool,
    /// Makes something at the path (creat, mkdir, symlink, ...): `pathcalls.MAKES`. An
    /// `open` is not among them; it makes only where its flags ask, which each tracer reads.
    pub makes: bool,
}

/// A path resolved against the process's own directory.
const fn cwd(path: usize) -> PathArg {
    PathArg { path, dirfd: None }
}

/// A path resolved against the descriptor in the argument before it.
const fn at(dirfd: usize, path: usize) -> PathArg {
    PathArg {
        path,
        dirfd: Some(dirfd),
    }
}

const NONE: u8 = 0;
const LOOKS: u8 = 1;
const MAKES: u8 = 2;

const fn call(name: &'static str, args: &'static [PathArg], kind: u8) -> PathCall {
    PathCall {
        name,
        args,
        looks: kind == LOOKS,
        makes: kind == MAKES,
    }
}

/// `pathcalls.PATHS`, with `LOOKS` and `MAKES` folded in, in the order Python lists them.
static TABLE: &[PathCall] = &[
    call("open", &[cwd(0)], NONE),
    call("creat", &[cwd(0)], MAKES),
    call("stat", &[cwd(0)], LOOKS),
    call("lstat", &[cwd(0)], LOOKS),
    call("access", &[cwd(0)], LOOKS),
    call("readlink", &[cwd(0)], LOOKS),
    call("chdir", &[cwd(0)], NONE),
    call("statfs", &[cwd(0)], LOOKS),
    call("getxattr", &[cwd(0)], LOOKS),
    call("lgetxattr", &[cwd(0)], LOOKS),
    call("listxattr", &[cwd(0)], LOOKS),
    call("llistxattr", &[cwd(0)], LOOKS),
    call("setxattr", &[cwd(0)], NONE),
    call("lsetxattr", &[cwd(0)], NONE),
    call("removexattr", &[cwd(0)], NONE),
    call("lremovexattr", &[cwd(0)], NONE),
    call("mkdir", &[cwd(0)], MAKES),
    call("rmdir", &[cwd(0)], NONE),
    call("unlink", &[cwd(0)], NONE),
    call("chmod", &[cwd(0)], NONE),
    call("chown", &[cwd(0)], NONE),
    call("lchown", &[cwd(0)], NONE),
    call("mknod", &[cwd(0)], MAKES),
    call("truncate", &[cwd(0)], NONE),
    call("utimes", &[cwd(0)], NONE),
    call("utime", &[cwd(0)], NONE),
    // `inotify_add_watch(fd, path, mask)`: the descriptor is the watch's, not a directory.
    call("inotify_add_watch", &[cwd(1)], LOOKS),
    // The link itself, not what it says: a symlink's target is text the kernel does not
    // resolve here.
    call("symlink", &[cwd(1)], MAKES),
    call("link", &[cwd(0), cwd(1)], MAKES),
    call("rename", &[cwd(0), cwd(1)], MAKES),
    call("openat", &[at(0, 1)], NONE),
    call("openat2", &[at(0, 1)], NONE),
    call("newfstatat", &[at(0, 1)], LOOKS),
    call("statx", &[at(0, 1)], LOOKS),
    call("faccessat", &[at(0, 1)], LOOKS),
    call("faccessat2", &[at(0, 1)], LOOKS),
    call("readlinkat", &[at(0, 1)], LOOKS),
    call("name_to_handle_at", &[at(0, 1)], LOOKS),
    call("open_tree", &[at(0, 1)], LOOKS),
    call("mkdirat", &[at(0, 1)], MAKES),
    call("mknodat", &[at(0, 1)], MAKES),
    call("unlinkat", &[at(0, 1)], NONE),
    call("fchmodat", &[at(0, 1)], NONE),
    call("fchmodat2", &[at(0, 1)], NONE),
    call("fchownat", &[at(0, 1)], NONE),
    call("utimensat", &[at(0, 1)], NONE),
    call("futimesat", &[at(0, 1)], NONE),
    // `fanotify_mark(fd, flags, mask, dirfd, path)`; a null path marks the descriptor itself.
    call("fanotify_mark", &[at(3, 4)], LOOKS),
    call("symlinkat", &[at(1, 2)], MAKES),
    call("renameat", &[at(0, 1), at(2, 3)], MAKES),
    call("renameat2", &[at(0, 1), at(2, 3)], MAKES),
    call("linkat", &[at(0, 1), at(2, 3)], MAKES),
];

/// Every call that names a path, by name, whether or not this architecture has it.
pub fn table() -> &'static [PathCall] {
    TABLE
}

/// The entry for `name`.
pub fn find(name: &str) -> Option<&'static PathCall> {
    table().iter().find(|call| call.name == name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_call_is_named_once_and_neither_looks_and_makes() {
        let mut names: Vec<_> = table().iter().map(|one| one.name).collect();
        let all = names.len();
        names.sort_unstable();
        names.dedup();
        assert_eq!(names.len(), all);
        assert_eq!(all, 52);
        assert!(table().iter().all(|one| !(one.looks && one.makes)));
        assert_eq!(table().iter().filter(|one| one.looks).count(), 18);
        assert_eq!(table().iter().filter(|one| one.makes).count(), 12);
    }

    #[test]
    fn what_a_process_becomes_is_not_a_path_call() {
        assert!(find("execve").is_none());
        assert!(find("execveat").is_none());
    }

    #[test]
    fn each_path_follows_the_descriptor_it_resolves_against() {
        for one in table() {
            assert!(!one.args.is_empty());
            for arg in one.args {
                assert!(arg.path < 6);
                assert!(arg.dirfd.is_none_or(|fd| fd + 1 == arg.path));
            }
        }
    }

    #[test]
    fn where_each_call_keeps_its_paths() {
        let pairs = |name: &str| -> Vec<(Option<usize>, usize)> {
            find(name)
                .unwrap()
                .args
                .iter()
                .map(|one| (one.dirfd, one.path))
                .collect()
        };
        assert_eq!(pairs("openat"), [(Some(0), 1)]);
        assert_eq!(pairs("statx"), [(Some(0), 1)]);
        assert_eq!(pairs("renameat2"), [(Some(0), 1), (Some(2), 3)]);
        assert_eq!(pairs("linkat"), [(Some(0), 1), (Some(2), 3)]);
        assert_eq!(pairs("symlinkat"), [(Some(1), 2)]);
        assert_eq!(pairs("fanotify_mark"), [(Some(3), 4)]);
        assert_eq!(pairs("inotify_add_watch"), [(None, 1)]);
        assert_eq!(pairs("mkdirat"), [(Some(0), 1)]);
        assert_eq!(pairs("unlinkat"), [(Some(0), 1)]);
    }

    #[test]
    fn lookups_only_look_makers_make_and_the_rest_neither() {
        for name in ["newfstatat", "statx", "readlinkat", "faccessat"] {
            let one = find(name).unwrap();
            assert!(one.looks && !one.makes, "{name}");
        }
        for name in ["mkdirat", "symlinkat", "linkat", "renameat2", "mknodat"] {
            assert!(find(name).unwrap().makes, "{name}");
        }
        for name in ["openat", "unlinkat", "fchmodat", "utimensat"] {
            let one = find(name).unwrap();
            assert!(!one.looks && !one.makes, "{name}");
        }
    }
}

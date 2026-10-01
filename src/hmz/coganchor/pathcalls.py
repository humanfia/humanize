"""The syscalls that name a path, and where each of them keeps the paths it names.

One table, read by both of the tracers that answer a path with another: the supervisor of an
anchored session (:mod:`hmz.coganchor.handlers`), which also settles a spelling of the mirror
only the target has, and the tracer of a turn run under a provider without an anchor
(:mod:`hmz.coganchor.providers._trace`), which answers a CLI's credentials and sessions with
the provider's. Each of them used to keep its own, and the second fell behind the first: a
call one of them stops and the other lets through is a path the other runs as it was named.

What each tracer then *does* with a call is its own business, and stays beside it. What is
here is only what the manual pages say: which calls name a path, in which argument, against
which descriptor, and which of them only look a path up or make something at it.
"""

from __future__ import annotations

from hmz.coganchor.linux.syscalls import NR

__all__ = ["LOOKS", "MAKES", "PATHS"]

#: Where each syscall keeps the paths it names, as ``(descriptor argument, path argument)``
#: pairs -- the descriptor being ``None`` for a call that has none and resolves against the
#: process's own directory. Read off the manual pages, one line per call: every call an
#: unprivileged process can name a path with, so that whichever of them a path is handed to,
#: it is the path that is answered.
#:
#: ``execve`` is deliberately absent: what a process becomes is the exec bridge's business,
#: and a redirected path is a credential rather than a program. The supervisor settles the
#: spelling of a program itself, knowing whether it runs here at all.
PATHS: dict[int, tuple[tuple[int | None, int], ...]] = {
    NR.OPEN: ((None, 0),),
    NR.CREAT: ((None, 0),),
    NR.STAT: ((None, 0),),
    NR.LSTAT: ((None, 0),),
    NR.ACCESS: ((None, 0),),
    NR.READLINK: ((None, 0),),
    NR.CHDIR: ((None, 0),),
    NR.STATFS: ((None, 0),),
    NR.GETXATTR: ((None, 0),),
    NR.LGETXATTR: ((None, 0),),
    NR.LISTXATTR: ((None, 0),),
    NR.LLISTXATTR: ((None, 0),),
    NR.SETXATTR: ((None, 0),),
    NR.LSETXATTR: ((None, 0),),
    NR.REMOVEXATTR: ((None, 0),),
    NR.LREMOVEXATTR: ((None, 0),),
    NR.MKDIR: ((None, 0),),
    NR.RMDIR: ((None, 0),),
    NR.UNLINK: ((None, 0),),
    NR.CHMOD: ((None, 0),),
    NR.CHOWN: ((None, 0),),
    NR.LCHOWN: ((None, 0),),
    NR.MKNOD: ((None, 0),),
    NR.TRUNCATE: ((None, 0),),
    NR.UTIMES: ((None, 0),),
    NR.UTIME: ((None, 0),),
    # The descriptor first, here, and the path after it: `inotify_add_watch(fd, path,
    # mask)` resolves the path as `open` would, against the process's own directory.
    NR.INOTIFY_ADD_WATCH: ((None, 1),),
    # The link itself, not what it says: what a symlink points at is text the kernel does
    # not resolve here, and rewriting it would answer a question nobody asked.
    NR.SYMLINK: ((None, 1),),
    NR.LINK: ((None, 0), (None, 1)),
    NR.RENAME: ((None, 0), (None, 1)),
    NR.OPENAT: ((0, 1),),
    NR.OPENAT2: ((0, 1),),
    NR.NEWFSTATAT: ((0, 1),),
    NR.STATX: ((0, 1),),
    NR.FACCESSAT: ((0, 1),),
    NR.FACCESSAT2: ((0, 1),),
    NR.READLINKAT: ((0, 1),),
    NR.NAME_TO_HANDLE_AT: ((0, 1),),
    NR.OPEN_TREE: ((0, 1),),
    NR.MKDIRAT: ((0, 1),),
    NR.MKNODAT: ((0, 1),),
    NR.UNLINKAT: ((0, 1),),
    NR.FCHMODAT: ((0, 1),),
    NR.FCHMODAT2: ((0, 1),),
    NR.FCHOWNAT: ((0, 1),),
    NR.UTIMENSAT: ((0, 1),),
    NR.FUTIMESAT: ((0, 1),),
    # `fanotify_mark(fd, flags, mask, dirfd, path)`, the mask one register wide on every
    # architecture a tracee is watched on. A null path marks the descriptor itself.
    NR.FANOTIFY_MARK: ((3, 4),),
    NR.SYMLINKAT: ((1, 2),),
    NR.RENAMEAT: ((0, 1), (2, 3)),
    NR.RENAMEAT2: ((0, 1), (2, 3)),
    NR.LINKAT: ((0, 1), (2, 3)),
}

#: The calls among those that only look a path up: what is there, what it says, what it is
#: on, or a watch on it. None of them changes what is at the path.
LOOKS = frozenset(
    {
        NR.STAT,
        NR.LSTAT,
        NR.ACCESS,
        NR.READLINK,
        NR.NEWFSTATAT,
        NR.STATX,
        NR.FACCESSAT,
        NR.FACCESSAT2,
        NR.READLINKAT,
        NR.STATFS,
        NR.GETXATTR,
        NR.LGETXATTR,
        NR.LISTXATTR,
        NR.LLISTXATTR,
        NR.NAME_TO_HANDLE_AT,
        NR.OPEN_TREE,
        NR.INOTIFY_ADD_WATCH,
        NR.FANOTIFY_MARK,
    }
)

#: The calls among those that make what they name, and so need somewhere to make it -- an
#: `open` among them only where its flags ask to create, which each tracer reads for itself.
MAKES = frozenset(
    {
        NR.CREAT,
        NR.MKDIR,
        NR.MKDIRAT,
        NR.SYMLINK,
        NR.SYMLINKAT,
        NR.LINK,
        NR.LINKAT,
        NR.RENAME,
        NR.RENAMEAT,
        NR.RENAMEAT2,
        NR.MKNOD,
        NR.MKNODAT,
    }
)

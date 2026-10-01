"""What a traced agent runs to name a directory by a path that is answered by another.

A spelling of the workspace only the target has, under an anchored supervisor, or a CLI's
credentials, under a provider. Not a test: the program
:mod:`tests.system.coganchor.test_spellings` and :mod:`tests.system.providers.test_redirect`
hand a traced `python3 -c`, on this machine or on a harness in a container, which has nothing
of this repository. So it imports nothing but the standard library, and is told everything else on
its command line: the directory to name, and the syscall numbers to name it with.

Each call is made as the bare syscall, by number, so that it is the call under test that the
filter stops rather than whichever one libc happens to reach it through -- glibc's `chown` is
`fchownat` on x86-64, and its `utime` is `utimensat`. One line is printed per call, `name=ok`
or `name=` and the errno it failed with; a call this architecture has not got is left out.
"""

from __future__ import annotations

import ctypes
import errno
import json
import os
import select
import subprocess
import sys
from pathlib import Path

AT_FDCWD = -100
IN_CREATE = 0x100
FAN_CLASS_NOTIF = 0
FAN_REPORT_FID = 0x200
FAN_MARK_ADD = 1
FAN_MODIFY = 2
S_IFIFO = 0o010000
O_CLOEXEC = 0o2000000

libc = ctypes.CDLL(None, use_errno=True)
libc.syscall.restype = ctypes.c_long

#: What a call may fail with and still have reached the file it named: a filesystem that keeps
#: no extended attributes, or no handles, says so of a file it has. `ENOENT` is never one of
#: them -- that is the answer a spelling this machine has not got comes back with.
FINE: dict[str, tuple[int, ...]] = {
    "getxattr": (errno.ENODATA, errno.ENOTSUP),
    "lgetxattr": (errno.ENODATA, errno.ENOTSUP),
    "setxattr": (errno.ENOTSUP, errno.EPERM),
    "lsetxattr": (errno.ENOTSUP, errno.EPERM),
    "removexattr": (errno.ENODATA, errno.ENOTSUP, errno.EPERM),
    "lremovexattr": (errno.ENODATA, errno.ENOTSUP, errno.EPERM),
    "name_to_handle_at": (errno.EOPNOTSUPP, errno.EOVERFLOW),
    "open_tree": (errno.EPERM,),
}


def say(line: str) -> None:
    """Writes one line of the probe's answer, at once, for whoever is reading it."""
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def arg(value: object) -> object:
    """One argument as `syscall(2)` takes it: a word, a string, or a buffer."""
    if isinstance(value, str):
        return ctypes.c_char_p(os.fsencode(value))
    if isinstance(value, int):
        return ctypes.c_long(value)
    return value


def call(numbers: dict[str, int], name: str, *args: object) -> None:
    """Makes one syscall by number and says what it came to."""
    number = numbers.get(name, -1)
    if number < 0:
        return
    ctypes.set_errno(0)
    done = libc.syscall(ctypes.c_long(number), *map(arg, args))
    code = ctypes.get_errno()
    if done >= 0 or code in FINE.get(name, ()):
        say(f"{name}=ok")
    else:
        say(f"{name}={errno.errorcode.get(code, code)}")


def readlink(numbers: dict[str, int], name: str, *args: object) -> None:
    """Reads the link by number, and says whether it says what it was made to."""
    if numbers.get(name, -1) < 0:
        return
    text = ctypes.create_string_buffer(512)
    size = libc.syscall(ctypes.c_long(numbers[name]), *map(arg, args), text, arg(256))
    said = text.value[: max(size, 0)]
    say(f"{name}={'ok' if said == b'seed.txt' else size}")


def watch(numbers: dict[str, int], base: Path) -> None:
    """Watches the directory for a file made in it, and makes one there."""
    held = libc.inotify_init1(0)
    ctypes.set_errno(0)
    added = libc.syscall(
        ctypes.c_long(numbers["inotify_add_watch"]),
        ctypes.c_long(held),
        arg(str(base)),
        ctypes.c_long(IN_CREATE),
    )
    if added < 0:
        say(f"inotify_add_watch={errno.errorcode.get(ctypes.get_errno(), '?')}")
        return
    (base / "watched.txt").write_text("seen\n")
    ready, _, _ = select.select([held], [], [], 10)
    heard = os.read(held, 4096) if ready else b""
    say(f"inotify_add_watch={'ok' if b'watched.txt' in heard else 'silent'}")


def mark(numbers: dict[str, int], path: str) -> None:
    """Marks the file for fanotify, where this kernel lets an unprivileged process at all."""
    held = libc.fanotify_init(FAN_CLASS_NOTIF | FAN_REPORT_FID, os.O_RDONLY)
    if held < 0:
        say(f"fanotify_mark=unavailable:{errno.errorcode.get(ctypes.get_errno(), '?')}")
        return
    call(numbers, "fanotify_mark", held, FAN_MARK_ADD, FAN_MODIFY, AT_FDCWD, path)


def main() -> None:
    """Names `argv[1]` every way there is, `argv[2]` being the numbers to name it with.

    And runs a program from it, here and on the target, unless `--no-programs` follows.
    """
    base = Path(sys.argv[1])
    numbers: dict[str, int] = json.loads(sys.argv[2])
    seed = str(base / "seed.txt")
    link = str(base / "link")
    stat = ctypes.create_string_buffer(512)
    text = ctypes.create_string_buffer(512)
    uid, gid = os.getuid(), os.getgid()

    call(numbers, "stat", seed, stat)
    call(numbers, "lstat", link, stat)
    call(numbers, "newfstatat", AT_FDCWD, seed, stat, 0)
    call(numbers, "statx", AT_FDCWD, seed, 0, 0x7FF, stat)
    call(numbers, "access", seed, os.R_OK)
    call(numbers, "faccessat", AT_FDCWD, seed, os.R_OK)
    call(numbers, "faccessat2", AT_FDCWD, seed, os.R_OK, 0)
    call(numbers, "statfs", seed, stat)
    call(numbers, "getxattr", seed, "user.hmz-none", text, 64)
    call(numbers, "lgetxattr", seed, "user.hmz-none", text, 64)
    call(numbers, "listxattr", seed, text, 256)
    call(numbers, "llistxattr", seed, text, 256)
    call(numbers, "setxattr", seed, "user.hmz", "1", 1, 0)
    call(numbers, "lsetxattr", seed, "user.hmz2", "1", 1, 0)
    call(numbers, "removexattr", seed, "user.hmz")
    call(numbers, "lremovexattr", seed, "user.hmz2")
    handle = ctypes.create_string_buffer(8 + 128)
    ctypes.c_uint32.from_buffer(handle).value = 128
    mount = ctypes.c_int()
    call(numbers, "name_to_handle_at", AT_FDCWD, seed, handle, ctypes.byref(mount), 0)
    call(numbers, "open_tree", AT_FDCWD, str(base), O_CLOEXEC)
    call(numbers, "chown", seed, uid, gid)
    call(numbers, "lchown", seed, uid, gid)
    call(numbers, "fchownat", AT_FDCWD, seed, uid, gid, 0)
    call(numbers, "chmod", seed, 0o644)
    call(numbers, "fchmodat", AT_FDCWD, seed, 0o644)
    call(numbers, "fchmodat2", AT_FDCWD, seed, 0o644, 0)
    call(numbers, "utime", seed, None)
    call(numbers, "utimes", seed, None)
    call(numbers, "futimesat", AT_FDCWD, seed, None)
    call(numbers, "utimensat", AT_FDCWD, seed, None, 0)
    call(numbers, "mknod", str(base / "pipe"), S_IFIFO | 0o600, 0)
    call(numbers, "mknodat", AT_FDCWD, str(base / "pipeat"), S_IFIFO | 0o600, 0)
    readlink(numbers, "readlinkat", AT_FDCWD, link)
    readlink(numbers, "readlink", link)
    watch(numbers, base)
    mark(numbers, seed)
    try:
        os.chdir(base)
        say(f"chdir={'ok' if Path('seed.txt').exists() else 'empty'}")
    except OSError as why:
        say(f"chdir={errno.errorcode.get(why.errno or 0, why)}")
    if "--no-programs" in sys.argv[3:]:
        # Answered by a provider rather than settled onto a mirror: a credential is not a
        # program, and what a process becomes is never redirected.
        return
    # The program is read first, as a CLI reads the script it is about to run: that is what
    # brings its bytes into the mirror for the kernel to run here.
    tool = base / "tool.sh"
    tool.read_text()
    for name, program in (("execve-here", tool), ("execve-there", base / "remote.sh")):
        ran = subprocess.run([program], capture_output=True, text=True, check=False)
        say(f"{name}={ran.stdout.strip() or ran.stderr.strip() or ran.returncode}")


if __name__ == "__main__":
    main()

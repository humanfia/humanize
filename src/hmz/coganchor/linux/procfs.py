"""Reaching into a stopped tracee: its memory, its ``/proc`` view, its fds.

Memory access goes through ``process_vm_readv``/``process_vm_writev`` (no file
descriptors to manage), and descriptors are duplicated with ``pidfd_getfd``,
which -- unlike opening ``/proc/<pid>/fd/N`` -- also works for the AF_UNIX
socketpairs that Node and Rust use for child stdio.
"""

from __future__ import annotations

import ctypes
import errno
import os
from typing import Final

from hmz.coganchor.linux.syscalls import NR

__all__ = [
    "MAX_ARG_STRLEN",
    "PATH_MAX",
    "Peek",
    "TraceeGoneError",
    "UnresolvedPathError",
    "fd_target",
    "read_bytes",
    "read_cstring",
    "read_string_array",
    "resolve_magic",
    "steal_fd",
    "working_directory",
    "write_bytes",
]

PATH_MAX: Final = 4096
_PAGE_SIZE: Final = os.sysconf("SC_PAGESIZE")
_MAX_ARGV_ENTRIES: Final = 65536

#: The kernel's own ceiling on one ``argv`` or ``envp`` entry, ``MAX_ARG_STRLEN``: thirty-two
#: pages. What a command may be, as opposed to what a path may be.
MAX_ARG_STRLEN: Final = 32 * _PAGE_SIZE

_libc = ctypes.CDLL("libc.so.6", use_errno=True)


class _Iovec(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("len", ctypes.c_size_t)]


_libc.process_vm_readv.restype = ctypes.c_ssize_t
_libc.process_vm_readv.argtypes = [
    ctypes.c_int,
    ctypes.POINTER(_Iovec),
    ctypes.c_ulong,
    ctypes.POINTER(_Iovec),
    ctypes.c_ulong,
    ctypes.c_ulong,
]
_libc.process_vm_writev.restype = ctypes.c_ssize_t
_libc.process_vm_writev.argtypes = _libc.process_vm_readv.argtypes
_libc.syscall.restype = ctypes.c_long


class TraceeGoneError(OSError):
    """The traced process disappeared mid-inspection."""


class UnresolvedPathError(OSError):
    """A ``/proc`` link in a path a tracee named could not be followed.

    Its own class rather than a bare :class:`OSError` because of what the callers do with
    it: a path this layer could not resolve is one it cannot hold against the workspace or
    against the paths a session answers with others, so the syscall is failed rather than
    let through to find out what the descriptor names.  That is the opposite of what the
    other failures here mean -- a tracee that has exited is one whose syscalls no longer
    matter -- and telling them apart by the errno would be guessing.

    Carries the errno the kernel gave, so the tracee is told what it would have been told
    had the call run: a descriptor that is not there is ``ENOENT`` either way.
    """


def read_bytes(pid: int, address: int, size: int) -> bytes:
    """Read ``size`` bytes from a tracee's address space."""
    if size <= 0:
        return b""
    buffer = ctypes.create_string_buffer(size)
    local = _Iovec(ctypes.addressof(buffer), size)
    remote = _Iovec(ctypes.c_void_p(address), size)
    ctypes.set_errno(0)
    count = _libc.process_vm_readv(
        pid, ctypes.byref(local), 1, ctypes.byref(remote), 1, 0
    )
    if count < 0:
        code = ctypes.get_errno()
        error = TraceeGoneError if code == errno.ESRCH else OSError
        raise error(
            code, os.strerror(code), f"process_vm_readv(pid={pid}, addr={address:#x})"
        )
    return buffer.raw[:count]


def write_bytes(pid: int, address: int, data: bytes) -> int:
    """Write ``data`` into a tracee's address space; returns bytes written."""
    if not data:
        return 0
    buffer = ctypes.create_string_buffer(data, len(data))
    local = _Iovec(ctypes.addressof(buffer), len(data))
    remote = _Iovec(ctypes.c_void_p(address), len(data))
    ctypes.set_errno(0)
    count = _libc.process_vm_writev(
        pid, ctypes.byref(local), 1, ctypes.byref(remote), 1, 0
    )
    if count < 0:
        code = ctypes.get_errno()
        raise OSError(
            code, os.strerror(code), f"process_vm_writev(pid={pid}, addr={address:#x})"
        )
    return int(count)


def read_cstring(pid: int, address: int, limit: int = PATH_MAX) -> str | None:
    """Read a NUL-terminated string, stopping at the first unreadable page.

    Returns ``None`` for a NULL pointer, which several syscalls accept.
    """
    if address == 0:
        return None
    parts: list[bytes] = []
    remaining = limit
    while remaining > 0:
        span = min(remaining, _PAGE_SIZE - (address % _PAGE_SIZE))
        try:
            block = read_bytes(pid, address, span)
        except OSError:
            break
        if not block:
            break
        end = block.find(b"\0")
        if end >= 0:
            parts.append(block[:end])
            return b"".join(parts).decode("utf-8", "surrogateescape")
        parts.append(block)
        address += span
        remaining -= span
    return b"".join(parts).decode("utf-8", "surrogateescape")


class Peek:
    """One buffer, read into over and over, for a tracer that reads a path per stop.

    A supervisor reads one path out of a stopped process and drops it, tens of thousands of
    times a session. A buffer apiece is a page allocated, cleared and collected each time --
    and between two stops the tracee runs, so what that costs is not the allocation but the
    cache it displaces. So the buffer is the reader's, and only the bytes up to the
    terminator come back: the bytes, since the path a tracer is looking for is a path it can
    recognise without ever decoding it.

    Not shared: it is read over by every call, so two tracers are two of these -- which is
    what each of them already is.
    """

    __slots__ = ("_at", "_buffer", "_here", "_local", "_remote", "_size", "_there")

    def __init__(self, size: int = PATH_MAX) -> None:
        """Initializes a window big enough for one path.

        Args:
          size: The most to read, which is what a path may be.
        """
        self._size = size
        # One byte over, so that a read filling the whole of it still has a terminator to
        # stop at: what comes back is the bytes before the first NUL, and a buffer with no
        # NUL in it at all would be read past its own end.
        self._buffer = ctypes.create_string_buffer(size + 1)
        self._at = ctypes.addressof(self._buffer)
        self._local = _Iovec(self._at, size)
        self._remote = _Iovec(None, 0)
        # And the references the call is handed, made once beside what they refer to rather
        # than once a read: they stay good for as long as the vectors do, which is for as
        # long as this window does.
        self._here = ctypes.byref(self._local)
        self._there = ctypes.byref(self._remote)

    def cstring(self, pid: int, address: int) -> bytes | None:
        """Read a NUL-terminated string, stopping at the first unreadable page.

        Args:
          pid: The process whose memory to read.
          address: Where the string starts in it.

        Returns:
          The bytes before its terminator, or None for a NULL pointer -- which several
          syscalls accept. Never longer than this window: a path longer than `PATH_MAX` is
          one the kernel will refuse anyway.
        """
        if address == 0:
            return None
        buffer = self._buffer
        filled = 0
        while filled < self._size:
            span = min(self._size - filled, _PAGE_SIZE - (address % _PAGE_SIZE))
            self._local.base = self._at + filled
            self._local.len = span
            self._remote.base = address
            self._remote.len = span
            ctypes.set_errno(0)
            count = _libc.process_vm_readv(pid, self._here, 1, self._there, 1, 0)
            if count <= 0:
                break
            filled += count
            # Where this read stopped, so that `value` -- which scans in C from the start of
            # the buffer -- cannot run past it into whatever the last path left behind.
            buffer[filled] = 0
            said = buffer.value
            if len(said) < filled:
                return said  # its own terminator, inside what was read
            address += count
        buffer[filled] = 0
        return buffer.value


def read_string_array(
    pid: int, address: int, limit: int = _MAX_ARGV_ENTRIES
) -> list[str]:
    """Read a NULL-terminated array of string pointers (``argv``/``envp``)."""
    if address == 0:
        return []
    values: list[str] = []
    word = ctypes.sizeof(ctypes.c_void_p)
    while len(values) < limit:
        raw = read_bytes(pid, address, word)
        if len(raw) < word:
            break
        pointer = int.from_bytes(raw, "little")
        if pointer == 0:
            break
        # An argv entry is not a path, so PATH_MAX is the wrong ceiling for it: the kernel
        # lets one be MAX_ARG_STRLEN long, and a shell command is routinely longer than a
        # path. Truncating one is worse than failing to read it -- what reaches the target
        # is then a prefix of the command, which runs and means something else.
        text = read_cstring(pid, pointer, MAX_ARG_STRLEN)
        values.append("" if text is None else text)
        address += word
    return values


def working_directory(pid: int) -> str:
    """Current working directory of a tracee, as the kernel sees it."""
    return _readlink(f"/proc/{pid}/cwd")


def fd_target(pid: int, fd: int) -> str:
    """Path a tracee's descriptor refers to (``/proc/<pid>/fd/<n>``)."""
    return _readlink(f"/proc/{pid}/fd/{fd}")


def _readlink(path: str) -> str:
    try:
        return os.readlink(path)
    except FileNotFoundError as exc:
        raise TraceeGoneError(exc.errno, "tracee vanished", path) from exc


#: The names under ``/proc/<pid>`` that are *magic links* -- not a symlink to some text the
#: kernel then resolves, but a jump straight to an open file.  Two of these carry a path
#: below them, which is what makes them a way round a rule written about prefixes; ``exe``
#: does not, and is here because a program is *named* by one: a runtime re-execing itself
#: says ``execve("/proc/self/exe")``, and a supervisor that left that alone would hand the
#: target a path naming the target's own helper instead of the agent's binary.
#:
#: ``map_files/<range>`` is magic too and is left out: reading it wants ``CAP_SYS_ADMIN`` on
#: most kernels, and nothing names a file that way.
_MAGIC_NAMES: Final = frozenset({"cwd", "exe", "root"})

#: What ``thread-self`` means in a path a *tracee* named: the stopped thread, rather than the
#: process reading the path.  Getting this round the wrong way would resolve the agent's paths
#: against the supervisor's own descriptors, which is a different set of files entirely -- the
#: channel to the target among them.
_THREAD_SELF: Final = "thread-self"

#: And what ``self`` means, which is not the same thing: procfs answers it with the thread
#: *group*, so a thread naming it gets the leader's descriptors, working directory and root.
#: Nearly always those are its own -- ``pthread_create`` passes ``CLONE_FILES`` and
#: ``CLONE_FS`` -- but neither is required of a thread: ``CLONE_THREAD`` insists only on
#: ``CLONE_SIGHAND`` and ``CLONE_VM``.  A thread cloned without them has a descriptor table
#: of its own, and reading ``self`` as that thread would resolve ``/proc/self/fd/3`` against
#: a descriptor the kernel is not going to use -- which is a credential read against the
#: wrong table, and the one shape of this defect a hostile turn could still arrange.
_SELF: Final = "self"

#: Where the thread group is written down, and how far in.  ``Tgid`` is the fourth line of
#: ``/proc/<pid>/status`` on every kernel that has the file, so a bounded read finds it
#: without pulling in the fifty lines after it.
_STATUS_HEAD: Final = 512
_TGID: Final = "Tgid:"

#: How many magic links one path may cross before it is called a loop.  A descriptor can
#: point at ``/proc/<pid>/fd`` itself, so one resolution can uncover another.  Forty, which
#: is the kernel's own ``SYMLOOP_MAX``: a lower number would refuse a path the kernel serves,
#: and refusing is not the cheap answer here -- a call this cannot resolve is one the layer
#: above must fail rather than let through, so a tracee could reach an unexamined path simply
#: by spelling it through nine descriptors.
_MAX_MAGIC_HOPS: Final = 40

#: What ``readlink`` appends to a descriptor whose file has been unlinked.  The name is gone,
#: so the text is no longer a path at all -- and a real file may be named this way, so the
#: suffix cannot simply be trimmed off.  Such a descriptor is left to the kernel.
_DELETED: Final = " (deleted)"


def resolve_magic(pid: int, path: str) -> str:
    """The file a tracee's path names, once the ``/proc`` links in it have been followed.

    Every modern coding CLI writes a file the atomic way -- open the directory, create a
    temporary beneath it, rename it over the real name -- and several of them (Claude Code
    2.1.272 among them, on every ``Write`` and every ``Edit``) spell "beneath it" as
    ``/proc/self/fd/<n>/name`` rather than as an ``*at`` call with the descriptor.  The
    kernel resolves that to the same file either way.  A rule written about path prefixes
    does not: ``/proc/self/fd/19/greeting.txt`` begins with nothing the workspace is named
    with, so a supervisor matching text alone lets the create and the rename past
    unexamined, the file lands in the mirror, and nothing ever carries it to the target.
    The agent, which reads back through the plain path, reports success.  So the links are
    followed here, before anything is compared, mirrored, answered or replayed.

    ``self`` and ``thread-self`` are read as the tracee rather than as this process, and as
    the two different things procfs makes them -- the thread group for the first, the stopped
    thread for the second.  A ``<pid>`` written out in full is left as it was written and
    asked of the kernel as it stands: Bun's ``process.pid`` is the thread group, which is the
    fallback spelling in the same bundle, and a number belonging to something else is a
    question the kernel answers the same way for the tracee and for us, since both run as the
    same user.

    ``..`` is collapsed *after* a link is followed and not before, because that is the order
    the kernel does it in: ``/proc/self/fd/19/../x`` is a file beside the directory the
    descriptor holds, not the nonexistent ``/proc/self/fd/x``.  What comes back is tidied
    the way :func:`os.path.normpath` tidies a path, and carries the same caveat it does --
    an ordinary symlink in the middle of a name is not followed, so a path is settled by its
    characters rather than by walking it.  That is the discipline the rest of this layer
    already keeps, and a resolved path is re-checked against the prefix rules exactly as a
    literal one is; nothing here decides that a path is inside the workspace.

    One more spelling is settled on the way past, because it is the same defect by another
    route: a path beginning with exactly two separators.  Linux reads ``//srv/project/x`` as
    ``/srv/project/x``, and :func:`os.path.normpath` is required by POSIX to leave the pair
    alone -- so a name spelled with one extra slash used to miss every prefix this layer
    matches, and a write through it landed in the mirror and went no further.

    Args:
      pid: The stopped tracee that named the path, whose descriptors it resolves against.
      path: The path it named, already absolute but not necessarily tidy.

    Returns:
      The path the kernel will really act on.  The argument itself, untouched, when there is
      nothing in it to settle -- which is every path but a handful in a session -- and also
      when a link names something that is not a file of this filesystem: a pipe, a socket, or
      a file whose name has been unlinked.  None of those can be inside the workspace, and
      the syscall that named one runs against the spelling it gave.

    Raises:
      UnresolvedPathError: If a magic link could not be followed at all.  The caller fails
        the syscall with the errno it carries rather than letting it through: an unresolved
        descriptor is one whose path could be anywhere, including the credentials this
        session answers with another, and a tracee that wants an unexamined path need only
        spell one it can break.
    """
    if "/proc/" not in path and not path.startswith("//"):
        return path
    walked: list[str] = []
    hops = 0
    for name in path.split("/"):
        # Nothing is ever put back to be walked again: following a link replaces what has
        # been walked so far and leaves the rest of the name to carry on against it, which
        # is what makes a forward pass over the components the whole of the algorithm.
        if not name or name == ".":
            continue
        if name == "..":
            if walked:
                walked.pop()
            continue
        walked.append(name)
        link = _magic_link(pid, walked)
        if link is None:
            continue
        hops += 1
        if hops > _MAX_MAGIC_HOPS:
            raise UnresolvedPathError(errno.ELOOP, os.strerror(errno.ELOOP), path)
        # Deliberately not this module's `_readlink`, which answers a missing file with
        # `TraceeGoneError` -- and the supervisor takes that for a tracee that has exited and
        # lets the syscall run. A descriptor that is not there must fail the call instead, or
        # a tracee could name one it has just closed and have the kernel resolve the path
        # nobody examined.
        try:
            target = os.readlink(link)
        except OSError as why:
            raise UnresolvedPathError(
                why.errno or errno.EIO, os.strerror(why.errno or errno.EIO), path
            ) from why
        if not target.startswith("/") or target.endswith(_DELETED):
            return path
        walked = [part for part in target.split("/") if part]
    return "/" + "/".join(walked)


def _magic_link(pid: int, walked: list[str]) -> str | None:
    """Where this machine reads the magic link ``walked`` spells, or ``None`` for anything else.

    Asked once per component of a path under ``/proc``, so the first line is what nearly
    every call answers with.  The shape recognised is the whole of what procfs offers:
    ``/proc/<who>/fd/<n>``, and ``/proc/<who>/`` followed by one of :data:`_MAGIC_NAMES`,
    each of them also reachable one thread down as ``/proc/<who>/task/<tid>/...``.

    Nothing a tracee wrote reaches the name this returns except as digits: the process and
    the descriptor are held to :func:`_numeric` and the rest is a word out of that table, so
    the link read here is always ``/proc/<digits>/...`` and a component cannot be spelled to
    step out of it.

    Args:
      pid: The tracee, which is what ``self`` and ``thread-self`` mean here.
      walked: The components of the path so far, tidied.

    Returns:
      The path this process reads the same link at, or None where these components name no
      link at all -- ``/proc/self/stat``, ``/proc/sys/...``, or a directory that merely has
      a magic link somewhere below it.
    """
    match walked:
        case ["proc", whose, *rest]:
            pass
        case _:
            return None
    if whose == _SELF:
        whose = str(_thread_group(pid))
    elif whose == _THREAD_SELF:
        whose = str(pid)
    elif not _numeric(whose):
        return None
    match rest:
        # A thread written out names itself, so whatever it was reached through is dropped:
        # `/proc/<pid>/task/<tid>/fd/<n>` and `/proc/<tid>/fd/<n>` are one descriptor, and
        # reading it at the shorter name is what keeps `self` from having to mean the thread
        # group here -- `/proc/<this thread>/task/<a sibling>` is a directory nobody has.
        case ["task", thread, *below] if _numeric(thread):
            whose, rest = thread, below
        case _:
            pass  # not a thread's own view of the same descriptors
    match rest:
        case [name] if name in _MAGIC_NAMES:
            return f"/proc/{whose}/{name}"
        case ["fd", number] if _numeric(number):
            return f"/proc/{whose}/fd/{number}"
        case _:
            return None


def _thread_group(pid: int) -> int:
    """The thread group a stopped thread belongs to, which is what ``/proc/self`` names.

    Asked of ``/proc/<pid>/status`` rather than remembered, because nothing here holds a
    tracee: both supervisors that read a path call this, and one of them keeps no table of
    processes at all.  It costs a bounded read of one file, and only on a path that really
    does name a magic link -- a few hundred times in a session, against the tens of thousands
    of stops that never reach here.

    Args:
      pid: The stopped thread.

    Returns:
      Its thread group, or the thread itself where the file does not say -- which is the
      answer for a single-threaded process either way, and the only way to be wrong about it
      is a kernel that stopped writing ``Tgid``.

    Raises:
      UnresolvedPathError: If the file could not be read at all.  The thread has gone, so the
        descriptor it named has gone with it, and the call must fail rather than run against
        whatever the number would otherwise have been.
    """
    try:
        with open(f"/proc/{pid}/status", "rb") as handle:
            head = handle.read(_STATUS_HEAD).decode("ascii", "replace")
    except OSError as why:
        raise UnresolvedPathError(
            why.errno or errno.ESRCH, os.strerror(why.errno or errno.ESRCH), str(pid)
        ) from why
    for line in head.splitlines():
        if line.startswith(_TGID):
            said = line[len(_TGID) :].strip()
            if _numeric(said):
                return int(said)
            break
    return pid


def _numeric(name: str) -> bool:
    """Whether a path component is a number the kernel would read as one.

    ``str.isdigit`` alone is not that question: it says yes to digits of other scripts, and
    ``/proc`` is named in ASCII.  A component that is not one of these is not a process and
    not a descriptor, so the path holding it is nothing this has to follow.
    """
    return name.isascii() and name.isdigit()


def steal_fd(pid: int, fd: int) -> int:
    """Duplicate a tracee's descriptor into this process.

    Uses ``pidfd_getfd(2)``, so pipes, sockets and ttys all work.
    """
    ctypes.set_errno(0)
    pidfd = _libc.syscall(NR.PIDFD_OPEN, pid, 0)
    if pidfd < 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), f"pidfd_open({pid})")
    try:
        ctypes.set_errno(0)
        stolen = _libc.syscall(NR.PIDFD_GETFD, pidfd, fd, 0)
        if stolen < 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), f"pidfd_getfd({pid}, {fd})")
        return int(stolen)
    finally:
        os.close(pidfd)

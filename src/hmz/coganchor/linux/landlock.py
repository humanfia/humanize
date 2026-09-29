"""Landlock: an unprivileged allow-list of the paths and ports a process tree may use.

A :class:`Ruleset` names what may be read, what may be written and which TCP ports may be
connected to or bound, and :meth:`Ruleset.restrict_self` makes that the whole of what the
calling thread -- and everything it later ``execve``\\ s or forks -- is allowed.  It is
called in a forked child just before ``execve``, the same place
:func:`~hmz.coganchor.linux.seccomp.install` is: Landlock restricts a thread, not a
process, and a freshly forked child has only the one.

Landlock grows by ABI version, and a kernel is asked which one it speaks rather than
assumed to speak the newest.  A filesystem right the kernel is too old to know is dropped
from the ruleset, which is the best the kernel can do and is what its own documentation
asks of a caller.  Network rules are not dropped that way: a ruleset asked to govern the
network on a kernel that cannot is refused outright, because dropping them would leave
the network open while the caller believed it shut.

Unlike its neighbours this module is safe to import anywhere, macOS included: nothing is
loaded until it is asked for, and :func:`abi` answers 0 on a host that has no Landlock.
The syscall numbers are the same on every architecture, so there is no table to consult.
"""

from __future__ import annotations

import ctypes
import errno
import functools
import os
import stat
import struct
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["Ruleset", "abi", "available", "fs_rights", "handled_fs"]

# One number apiece on every architecture: they were added after the tables were unified.
_NR_CREATE_RULESET: Final = 444
_NR_ADD_RULE: Final = 445
_NR_RESTRICT_SELF: Final = 446

_CREATE_RULESET_VERSION: Final = 1 << 0
_RULE_PATH_BENEATH: Final = 1
_RULE_NET_PORT: Final = 2

_PR_SET_NO_NEW_PRIVS: Final = 38

# ``LANDLOCK_ACCESS_FS_*``, from <linux/landlock.h>.
_FS_EXECUTE: Final = 1 << 0
_FS_WRITE_FILE: Final = 1 << 1
_FS_READ_FILE: Final = 1 << 2
_FS_READ_DIR: Final = 1 << 3
_FS_REFER: Final = 1 << 13  # ABI 2
_FS_TRUNCATE: Final = 1 << 14  # ABI 3
_FS_IOCTL_DEV: Final = 1 << 15  # ABI 5

#: The thirteen rights ABI 1 already had, ``EXECUTE`` through ``MAKE_SYM``.
_FS_ABI1: Final = (1 << 13) - 1

#: The rights that mean anything on a file rather than a directory: the kernel refuses a
#: rule that grants any other on one.
_FS_FILE: Final = (
    _FS_EXECUTE | _FS_WRITE_FILE | _FS_READ_FILE | _FS_TRUNCATE | _FS_IOCTL_DEV
)

#: What "read" grants: open and list, and run what is there.
_FS_READ: Final = _FS_EXECUTE | _FS_READ_FILE | _FS_READ_DIR

# ``LANDLOCK_ACCESS_NET_*``, ABI 4.
_NET_BIND_TCP: Final = 1 << 0
_NET_CONNECT_TCP: Final = 1 << 1

#: The first ABI that can govern TCP at all.
NET_ABI: Final = 4

#: Why a path is left out of a ruleset rather than failing it: what cannot be reached
#: needs no grant, and leaving a grant out only ever denies more.
_UNREACHABLE: Final = frozenset({errno.ENOENT, errno.ENOTDIR, errno.EACCES, errno.ELOOP})


@functools.cache
def _libc() -> ctypes.CDLL:
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    libc.syscall.restype = ctypes.c_long
    return libc


def _call(number: int, *args: object, what: str) -> int:
    """Make one raw syscall, raising what it failed with.

    Args:
      number: The syscall.
      *args: Its arguments, each already a :mod:`ctypes` value.
      what: What to name it as in the error.

    Returns:
      What it returned, which is not negative.

    Raises:
      OSError: If it failed.
    """
    ctypes.set_errno(0)
    result = int(_libc().syscall(ctypes.c_long(number), *args))
    if result < 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), what)
    return result


@functools.cache
def abi() -> int:
    """The Landlock ABI version this kernel speaks.

    Returns:
      The version, or 0 where there is none to speak: a host that is not Linux, a kernel
      built without Landlock, or one booted with it left out of the ``lsm=`` list.
    """
    if sys.platform != "linux":
        return 0
    try:
        return _call(
            _NR_CREATE_RULESET,
            ctypes.c_void_p(None),
            ctypes.c_size_t(0),
            ctypes.c_uint32(_CREATE_RULESET_VERSION),
            what="landlock_create_ruleset(LANDLOCK_CREATE_RULESET_VERSION)",
        )
    except OSError:
        return 0


def available(net: bool = False) -> bool:
    """Whether a ruleset can be enforced here at all.

    Args:
      net: Whether it would govern TCP as well as the filesystem.

    Returns:
      Whether this kernel speaks ABI 1, or ABI 4 where ``net`` is asked for.
    """
    return abi() >= (NET_ABI if net else 1)


def handled_fs(version: int) -> int:
    """Every filesystem right an ABI version can govern.

    Args:
      version: The ABI version, as :func:`abi` reports it.

    Returns:
      The mask a ruleset for that version handles, and so denies wherever no rule grants.
    """
    mask = _FS_ABI1 if version >= 1 else 0
    if version >= 2:
        mask |= _FS_REFER
    if version >= 3:
        mask |= _FS_TRUNCATE
    if version >= 5:
        mask |= _FS_IOCTL_DEV
    return mask


def fs_rights(version: int, *, write: bool, directory: bool) -> int:
    """The rights one path is granted.

    Args:
      version: The ABI version the ruleset is built for.
      write: Whether the path is writable as well as readable.
      directory: Whether it is a directory; a file can only take the rights of a file.

    Returns:
      The mask to grant beneath the path.
    """
    rights = handled_fs(version) if write else _FS_READ & handled_fs(version)
    return rights if directory else rights & _FS_FILE


@dataclass(frozen=True, slots=True)
class Ruleset:
    """What a restricted process tree may still reach, and nothing else.

    A path grants everything beneath it, and a path given twice is granted the union.
    Anything not granted is denied: a path outside every list cannot be opened, listed or
    run, and with ``net`` a TCP port outside ``connect_ports`` cannot be connected to and
    one outside ``bind_ports`` cannot be bound.  UDP and every other protocol are not
    Landlock's to govern; :func:`~hmz.coganchor.linux.seccomp.install_socket_filter` is
    what shuts them.  Nor is connecting to a Unix socket, which is a way to ask a
    process outside the ruleset -- a container daemon, a session bus -- to act on this
    one's behalf: a caller that must shut that too has to keep such sockets out of every
    path it grants.

    Attributes:
      read: Paths that may be read, listed and executed.
      write: Paths that may be read and changed in every way: created, written,
        truncated, renamed, removed.
      connect_ports: TCP ports that may be connected to, on any address.
      bind_ports: TCP ports that may be bound.
      net: Whether TCP is governed at all.  Without it every connect and bind is left
        alone, and giving ports is a mistake.
    """

    read: Iterable[str | os.PathLike[str]] = ()
    write: Iterable[str | os.PathLike[str]] = ()
    connect_ports: Iterable[int] = ()
    bind_ports: Iterable[int] = ()
    net: bool = False

    def restrict_self(self) -> None:
        """Confine the calling thread, and everything it starts, to this ruleset.

        Irreversible, and meant for a forked child just before ``execve``.  Sets
        ``PR_SET_NO_NEW_PRIVS``, which Landlock needs without ``CAP_SYS_ADMIN`` and which
        also stops a set-uid program below from escaping the ruleset.  A path that does
        not exist, or that cannot be reached to begin with, is left out rather than
        failing the call.

        Raises:
          RuntimeError: If this kernel has no Landlock, or cannot govern TCP and
            ``net`` was asked for.  Nothing has been restricted.
          ValueError: If ports are given without ``net``, or a port is out of range.
          OSError: If the kernel refuses the ruleset.  The thread may or may not be
            restricted, so a caller should treat it as unusable and exit.
        """
        version = abi()
        connect, bind = list(self.connect_ports), list(self.bind_ports)
        if (connect or bind) and not self.net:
            raise ValueError("ports were given for a ruleset that does not govern TCP")
        if not all(0 <= port <= 0xFFFF for port in (*connect, *bind)):
            raise ValueError(f"a TCP port is out of range: {connect + bind}")
        if not available(net=self.net):
            needs = f"ABI {NET_ABI} to govern TCP" if self.net else "Landlock"
            raise RuntimeError(f"this kernel speaks Landlock ABI {version}; needs {needs}")
        handled_net = _NET_BIND_TCP | _NET_CONNECT_TCP if self.net else 0
        attr = struct.pack("<QQ", handled_fs(version), handled_net)
        size = len(attr) if self.net else 8
        ruleset = _call(
            _NR_CREATE_RULESET,
            ctypes.c_char_p(attr),
            ctypes.c_size_t(size),
            ctypes.c_uint32(0),
            what="landlock_create_ruleset",
        )
        try:
            for paths, write in ((self.read, False), (self.write, True)):
                for path in paths:
                    _add_path(ruleset, path, version, write=write)
            for ports, right in ((connect, _NET_CONNECT_TCP), (bind, _NET_BIND_TCP)):
                for port in ports:
                    _add_rule(ruleset, _RULE_NET_PORT, struct.pack("<QQ", right, port))
            ctypes.set_errno(0)
            if _libc().prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
                code = ctypes.get_errno()
                raise OSError(code, os.strerror(code), "prctl(PR_SET_NO_NEW_PRIVS)")
            _call(
                _NR_RESTRICT_SELF,
                ctypes.c_int(ruleset),
                ctypes.c_uint32(0),
                what="landlock_restrict_self",
            )
        finally:
            os.close(ruleset)


def _add_rule(ruleset: int, kind: int, attr: bytes) -> None:
    _call(
        _NR_ADD_RULE,
        ctypes.c_int(ruleset),
        ctypes.c_int(kind),
        ctypes.c_char_p(attr),
        ctypes.c_uint32(0),
        what="landlock_add_rule",
    )


def _add_path(
    ruleset: int, path: str | os.PathLike[str], version: int, *, write: bool
) -> None:
    """Grant one path, or nothing where there is nothing there to grant.

    Args:
      ruleset: The ruleset descriptor.
      path: The file or directory.
      version: The ABI version the ruleset was built for.
      write: Whether to grant writing as well as reading.

    Raises:
      OSError: If the path exists and still could not be granted.
    """
    try:
        fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
    except OSError as why:
        if why.errno in _UNREACHABLE:
            return
        raise
    try:
        directory = stat.S_ISDIR(os.fstat(fd).st_mode)
        rights = fs_rights(version, write=write, directory=directory)
        _add_rule(ruleset, _RULE_PATH_BENEATH, struct.pack("<Qi", rights, fd))
    finally:
        os.close(fd)

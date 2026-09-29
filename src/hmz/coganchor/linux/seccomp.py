"""Classic-BPF seccomp filters: which syscalls reach the supervisor, and which sockets exist.

Each filter is installed once in the forked child, just before ``execve``, and
is inherited by every descendant process and thread.  The trap filter returns
``SECCOMP_RET_TRACE`` for the cold, path-bearing syscalls coganchor cares
about and ``SECCOMP_RET_ALLOW`` for everything else, so hot syscalls never pay
a ptrace stop.

The socket filter is the other half of a process cut off from the network:
Landlock (:mod:`hmz.coganchor.linux.landlock`) decides which TCP ports may be
reached, and cannot see any other protocol, so this refuses to create a socket
of one.  The listen filter is the third: Landlock decides which ports may be
bound and cannot see the address, so ``bind`` and ``listen`` are stopped for a
supervisor outside to decide (:mod:`hmz.coganchor.fence.loopback`), through
the user-notification calls below.  The filters stack -- the kernel runs every
one and takes the stricter answer -- so a child may carry any of them.
"""

from __future__ import annotations

import ctypes
import errno
import os
import socket
import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from hmz.coganchor.linux.syscalls import ARCH, NR

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "Notification",
    "build_listen_program",
    "build_program",
    "build_socket_program",
    "install",
    "install_listener",
    "install_socket_filter",
    "notifiable",
    "receive",
    "respond",
    "valid",
]

_libc = ctypes.CDLL("libc.so.6", use_errno=True)
_libc.syscall.restype = ctypes.c_long

_PR_SET_NO_NEW_PRIVS: Final = 38
_SECCOMP_SET_MODE_FILTER: Final = 1

_SECCOMP_GET_ACTION_AVAIL: Final = 2
_SECCOMP_GET_NOTIF_SIZES: Final = 3
_FILTER_FLAG_NEW_LISTENER: Final = 1 << 3

_RET_ALLOW: Final = 0x7FFF0000
_RET_USER_NOTIF: Final = 0x7FC00000
_RET_TRACE: Final = 0x7FF00000
_RET_ERRNO: Final = 0x00050000

# BPF instruction classes and modes, from <linux/filter.h>.
_LD_W_ABS: Final = 0x20
_JMP_JEQ_K: Final = 0x15
_JMP_JGE_K: Final = 0x35
_ALU_AND_K: Final = 0x54
_RET_K: Final = 0x06

# Offsets into ``struct seccomp_data``.
_OFFSET_NR: Final = 0
_OFFSET_ARCH: Final = 4
_OFFSET_ARGS: Final = 16

#: ``__X32_SYSCALL_BIT``: a number with it set is x86-64's x32 ABI, which reports the
#: same audit architecture and so would otherwise walk past a filter keyed on numbers.
_X32_BIT: Final = 0x40000000

#: ``SOCK_TYPE_MASK``: the socket type, less ``SOCK_NONBLOCK`` and ``SOCK_CLOEXEC``.
_SOCK_TYPE_MASK: Final = 0xF

_MAX_JUMP: Final = 255

#: ``struct seccomp_notif``: the id, the pid, flags, then ``struct seccomp_data`` -- the
#: number, the architecture, the instruction pointer and the six arguments.
_NOTIF: Final = struct.Struct("=QIIiIQ6Q")
_DATA_SIZE: Final = 64
#: ``struct seccomp_notif_resp``: the id, the value, the negated errno, and flags.
_RESP: Final = struct.Struct("=QqiI")
_USER_NOTIF_FLAG_CONTINUE: Final = 1


def _iowr(nr: int, size: int, *, read: bool = True) -> int:
    """``_IOWR('!', nr, size)``, or ``_IOW`` where the kernel only reads, as <linux/seccomp.h>."""
    return ((3 if read else 1) << 30) | (size << 16) | (ord("!") << 8) | nr


_IOCTL_NOTIF_RECV: Final = _iowr(0, _NOTIF.size)
_IOCTL_NOTIF_SEND: Final = _iowr(1, _RESP.size)
_IOCTL_NOTIF_ID_VALID: Final = _iowr(2, 8, read=False)


class _SockFprog(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ushort), ("filter", ctypes.c_void_p)]


def _insn(code: int, jt: int, jf: int, k: int) -> bytes:
    return struct.pack("HBBI", code, jt, jf, k)


def build_program(numbers: Iterable[int]) -> bytes:
    """Assemble the BPF program that traps ``numbers``.

    Foreign architectures (32-bit syscall entry points) are allowed through
    untouched: coganchor is a redirector, not a sandbox, so failing open keeps
    an unexpected personality working rather than killing the agent.

    A number below zero is dropped rather than assembled: that is how
    :class:`~hmz.coganchor.linux.syscalls.Numbers` spells a call this
    architecture has not got, and a caller that builds its trap set by naming
    calls -- which is every caller -- would otherwise be asked to know which of
    them exist here.  Nothing is lost by dropping one: a call the kernel has no
    number for is a call no process can make.

    Args:
      numbers: The syscalls to trap, in any order and with repeats allowed.

    Returns:
      The assembled filter.

    Raises:
      ValueError: If the trap set is too large for a flat filter to jump over.
    """
    ordered = sorted({number for number in numbers if number >= 0})
    if len(ordered) * 2 + 4 > _MAX_JUMP:
        raise ValueError("trap set too large for a flat filter")
    program = [
        _insn(_LD_W_ABS, 0, 0, _OFFSET_ARCH),
        _insn(_JMP_JEQ_K, 1, 0, ARCH.audit_arch),
        _insn(_RET_K, 0, 0, _RET_ALLOW),
        _insn(_LD_W_ABS, 0, 0, _OFFSET_NR),
    ]
    for number in ordered:
        program.append(_insn(_JMP_JEQ_K, 0, 1, number))
        program.append(_insn(_RET_K, 0, 0, _RET_TRACE))
    program.append(_insn(_RET_K, 0, 0, _RET_ALLOW))
    return b"".join(program)


def _arg(index: int) -> int:
    """Offset of the low word of a syscall argument, which is all of an ``int`` one."""
    return _OFFSET_ARGS + 8 * index


def build_socket_program() -> bytes:
    """Assemble the BPF program that refuses every socket but a TCP one.

    ``socket(2)`` on ``AF_INET`` or ``AF_INET6`` is allowed only for
    ``SOCK_STREAM`` with protocol 0 or ``IPPROTO_TCP``: those are the sockets
    Landlock governs, and a stream socket of another protocol -- SCTP, MPTCP --
    is one it does not.  Besides those only ``AF_UNIX`` and ``AF_NETLINK`` are
    allowed, which reach this machine and nothing past it; every other family
    -- ``AF_PACKET``, ``AF_VSOCK`` to a hypervisor, and whatever a kernel adds
    later -- is refused.  So is UDP, and with it a resolver that asks a DNS
    server directly: a process confined by this reaches the network by name
    through a proxy that resolves for it.  The refusal is ``EACCES``, which is
    what a program already expects to be told it may not.

    Two more ways round the check are shut with it.  ``io_uring_setup`` is
    refused, because a ring creates sockets without calling ``socket(2)``; a
    program that probes for io_uring falls back to plain syscalls.  And unlike
    :func:`build_program`, a foreign architecture is refused rather than let
    through, as is an x32 number on x86-64: this filter is a sandbox, and a
    32-bit entry point would reach ``socket`` under a number it does not check.

    Returns:
      The assembled filter.
    """
    return _assemble(
        [
            (_LD_W_ABS, 0, 0, _OFFSET_ARCH),
            (_JMP_JEQ_K, 0, "deny", ARCH.audit_arch),
            (_LD_W_ABS, 0, 0, _OFFSET_NR),
            (_JMP_JGE_K, "deny", 0, _X32_BIT),
            (_JMP_JEQ_K, "deny", 0, NR.IO_URING_SETUP),
            (_JMP_JEQ_K, 0, "allow", NR.SOCKET),
            (_LD_W_ABS, 0, 0, _arg(0)),
            (_JMP_JEQ_K, "allow", 0, socket.AF_UNIX),
            (_JMP_JEQ_K, "allow", 0, socket.AF_NETLINK),
            (_JMP_JEQ_K, "inet", 0, socket.AF_INET),
            (_JMP_JEQ_K, 0, "deny", socket.AF_INET6),
            "inet",
            (_LD_W_ABS, 0, 0, _arg(1)),
            (_ALU_AND_K, 0, 0, _SOCK_TYPE_MASK),
            (_JMP_JEQ_K, 0, "deny", socket.SOCK_STREAM),
            (_LD_W_ABS, 0, 0, _arg(2)),
            (_JMP_JEQ_K, "allow", 0, 0),
            (_JMP_JEQ_K, "allow", "deny", socket.IPPROTO_TCP),
            "allow",
            (_RET_K, 0, 0, _RET_ALLOW),
            "deny",
            (_RET_K, 0, 0, _RET_ERRNO | errno.EACCES),
        ]
    )


def build_listen_program() -> bytes:
    """Assemble the BPF program that hands every ``bind`` and ``listen`` to a supervisor.

    Both calls return ``SECCOMP_RET_USER_NOTIF``, which stops the caller until whoever holds
    the filter's listener descriptor answers; every other call is allowed, and a foreign
    architecture or an x32 number is refused as :func:`build_socket_program` refuses it, so
    that neither reaches ``bind`` under a number this does not check. Stacked on a trace
    filter, a user notification is the stricter answer and wins: a call both trap goes to the
    listener, never to the tracer -- which traps neither of these.

    Returns:
      The assembled filter.
    """
    return _assemble(
        [
            (_LD_W_ABS, 0, 0, _OFFSET_ARCH),
            (_JMP_JEQ_K, 0, "deny", ARCH.audit_arch),
            (_LD_W_ABS, 0, 0, _OFFSET_NR),
            (_JMP_JGE_K, "deny", 0, _X32_BIT),
            (_JMP_JEQ_K, "notify", 0, NR.BIND),
            (_JMP_JEQ_K, "notify", 0, NR.LISTEN),
            (_RET_K, 0, 0, _RET_ALLOW),
            "notify",
            (_RET_K, 0, 0, _RET_USER_NOTIF),
            "deny",
            (_RET_K, 0, 0, _RET_ERRNO | errno.EACCES),
        ]
    )


def _assemble(body: list[tuple[int, int | str, int | str, int] | str]) -> bytes:
    """Assemble a flat program whose jumps name the labels written between its instructions."""
    labels: dict[str, int] = {}
    program: list[tuple[int, int | str, int | str, int]] = []
    for item in body:
        if isinstance(item, str):
            labels[item] = len(program)
        else:
            program.append(item)

    def jump(at: int, to: int | str) -> int:
        return to if isinstance(to, int) else labels[to] - at - 1

    return b"".join(
        _insn(code, jump(at, jt), jump(at, jf), k)
        for at, (code, jt, jf, k) in enumerate(program)
    )


def install(numbers: Iterable[int]) -> None:
    """Install the trap filter on the current thread.

    Called in the forked child between ``PTRACE_TRACEME`` and ``execve``.
    ``PR_SET_NO_NEW_PRIVS`` is required to install a filter without
    ``CAP_SYS_ADMIN``; it also means set-uid binaries below the agent will not
    gain privileges, which is the correct posture for a redirected session.
    """
    _load(build_program(numbers))


def install_socket_filter() -> None:
    """Install the socket filter of :func:`build_socket_program` on the current thread.

    Called in the forked child before ``execve``, like :func:`install`, and
    safe to call alongside it in either order.

    Raises:
      OSError: If the kernel refuses the filter.
    """
    _load(build_socket_program())


def install_listener() -> int:
    """Install the filter of :func:`build_listen_program`, and return its listener.

    Called in the forked child before ``execve``, after :func:`install_socket_filter`. The
    descriptor is close-on-exec, and is handed to the supervisor and closed before the
    program runs: a program holding it could answer its own calls.

    Returns:
      The listener descriptor, which :func:`receive` reads the stopped calls from.

    Raises:
      OSError: If the kernel refuses the filter -- `EBUSY` where a filter this thread already
        carries has a listener of its own, since a thread answers to one at most.
    """
    return _load(build_listen_program(), _FILTER_FLAG_NEW_LISTENER)


def notifiable() -> bool:
    """Whether this kernel stops a call for a supervisor to answer, with room for its answers.

    Returns:
      Whether ``SECCOMP_RET_USER_NOTIF`` is an action here, and the kernel's notification and
      response are the size of the ones this reads and writes: the size is part of each
      request's number, and a kernel whose structures have grown would write past the buffer
      :func:`receive` hands it.
    """
    action = ctypes.c_uint32(_RET_USER_NOTIF)
    ctypes.set_errno(0)
    if _libc.syscall(NR.SECCOMP, _SECCOMP_GET_ACTION_AVAIL, 0, ctypes.byref(action)):
        return False
    sizes = (ctypes.c_uint16 * 3)()
    if _libc.syscall(NR.SECCOMP, _SECCOMP_GET_NOTIF_SIZES, 0, sizes):
        return False
    notif, resp, data = sizes
    return (notif, resp, data) == (_NOTIF.size, _RESP.size, _DATA_SIZE)


@dataclass(frozen=True, slots=True)
class Notification:
    """One call a process is stopped in, as ``struct seccomp_notif`` says it.

    Attributes:
      id: The kernel's cookie for it, which the answer and :func:`valid` name it by.
      pid: The thread that made it, in this process's pid namespace.
      nr: The syscall number.
      args: Its six arguments, as the registers held them.
    """

    id: int
    pid: int
    nr: int
    args: tuple[int, ...]


def receive(listener: int) -> Notification:
    """Wait for the next call a filter stopped, and return it.

    Args:
      listener: The descriptor :func:`install_listener` returned.

    Returns:
      The call.

    Raises:
      OSError: `ENOENT` where the caller went before it could be read, which is nothing to
        answer; anything else the kernel says.
    """
    buffer = ctypes.create_string_buffer(_NOTIF.size)
    _ioctl(listener, _IOCTL_NOTIF_RECV, buffer, "SECCOMP_IOCTL_NOTIF_RECV")
    ident, pid, _flags, nr, _arch, _ip, *args = _NOTIF.unpack(buffer.raw)
    return Notification(ident, pid, nr, tuple(args))


def respond(
    listener: int, ident: int, *, value: int = 0, error: int = 0, go: bool = False
) -> None:
    """Answer a stopped call: with a result, with an error, or by letting it run.

    Args:
      listener: The listener descriptor.
      ident: The call's :attr:`Notification.id`.
      value: What the call returns, where it succeeds.
      error: The `errno` it fails with, or 0.
      go: Whether the kernel runs the call itself after all, as though it had not been
        stopped. It then reads its arguments again, from memory the caller may have changed
        since: an answer that lets a call go is not a check of what it was given.

    Raises:
      OSError: `ENOENT` where the caller has gone or was interrupted, and is past answering.
    """
    buffer = ctypes.create_string_buffer(
        _RESP.pack(ident, value, -error, _USER_NOTIF_FLAG_CONTINUE if go else 0),
        _RESP.size,
    )
    _ioctl(listener, _IOCTL_NOTIF_SEND, buffer, "SECCOMP_IOCTL_NOTIF_SEND")


def valid(listener: int, ident: int) -> bool:
    """Whether a call is still stopped, and its caller is therefore still the process it was.

    Asked after reading anything of the caller's by its pid, since a pid read from a
    notification may have been taken by another process since.
    """
    cookie = ctypes.c_uint64(ident)
    try:
        _ioctl(listener, _IOCTL_NOTIF_ID_VALID, ctypes.byref(cookie), "ID_VALID")
    except OSError:
        return False
    return True


def _ioctl(fd: int, request: int, argument: object, name: str) -> None:
    ctypes.set_errno(0)
    if _libc.ioctl(ctypes.c_int(fd), ctypes.c_ulong(request), argument) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), name)


def _load(blob: bytes, flags: int = 0) -> int:
    """Set ``PR_SET_NO_NEW_PRIVS`` and install one assembled filter; return what the kernel did."""
    ctypes.set_errno(0)
    if _libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), "prctl(PR_SET_NO_NEW_PRIVS)")
    buffer = ctypes.create_string_buffer(blob, len(blob))
    program = _SockFprog(len(blob) // 8, ctypes.cast(buffer, ctypes.c_void_p))
    ctypes.set_errno(0)
    done = _libc.syscall(
        NR.SECCOMP, _SECCOMP_SET_MODE_FILTER, flags, ctypes.byref(program)
    )
    if done < 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), "seccomp(SECCOMP_SET_MODE_FILTER)")
    return int(done)

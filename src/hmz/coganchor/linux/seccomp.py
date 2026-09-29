"""Classic-BPF seccomp filters: which syscalls reach the supervisor, and which sockets exist.

Each filter is installed once in the forked child, just before ``execve``, and
is inherited by every descendant process and thread.  The trap filter returns
``SECCOMP_RET_TRACE`` for the cold, path-bearing syscalls coganchor cares
about and ``SECCOMP_RET_ALLOW`` for everything else, so hot syscalls never pay
a ptrace stop.

The socket filter is the other half of a process cut off from the network:
Landlock (:mod:`hmz.coganchor.linux.landlock`) decides which TCP ports may be
reached, and cannot see any other protocol, so this refuses to create a socket
of one.  The two filters stack -- the kernel runs both and takes the stricter
answer -- so a child may carry either or both.
"""

from __future__ import annotations

import ctypes
import errno
import os
import socket
import struct
from typing import TYPE_CHECKING, Final

from hmz.coganchor.linux.syscalls import ARCH, NR

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "build_program",
    "build_socket_program",
    "install",
    "install_socket_filter",
]

_libc = ctypes.CDLL("libc.so.6", use_errno=True)
_libc.syscall.restype = ctypes.c_long

_PR_SET_NO_NEW_PRIVS: Final = 38
_SECCOMP_SET_MODE_FILTER: Final = 1

_RET_ALLOW: Final = 0x7FFF0000
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
    labels: dict[str, int] = {}
    body: list[tuple[int, int | str, int | str, int] | str] = [
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


def _load(blob: bytes) -> None:
    """Set ``PR_SET_NO_NEW_PRIVS`` and install one assembled filter."""
    ctypes.set_errno(0)
    if _libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), "prctl(PR_SET_NO_NEW_PRIVS)")
    buffer = ctypes.create_string_buffer(blob, len(blob))
    program = _SockFprog(len(blob) // 8, ctypes.cast(buffer, ctypes.c_void_p))
    ctypes.set_errno(0)
    if (
        _libc.syscall(NR.SECCOMP, _SECCOMP_SET_MODE_FILTER, 0, ctypes.byref(program))
        != 0
    ):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), "seccomp(SECCOMP_SET_MODE_FILTER)")

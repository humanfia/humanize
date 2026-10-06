"""What the seccomp filters answer each call with, read by running them here as data.

The filters are classic BPF over `struct seccomp_data`; a few lines below run one against a
call the way the kernel would, so each case says what a process making that call is told.
Nothing is installed. Linux only: collected there and nowhere else (see `conftest.py`).
"""

from __future__ import annotations

import errno
import socket
import struct

import pytest

from hmz.coganchor.linux.seccomp import (
    Notification,
    build_listen_program,
    build_program,
    build_socket_program,
)
from hmz.coganchor.linux.syscalls import ARCH, NR, TRAPPED_SYSCALLS

# `SECCOMP_RET_*`, from <linux/seccomp.h>.
ALLOW = 0x7FFF0000
TRACE = 0x7FF00000
NOTIFY = 0x7FC00000
EACCES = 0x00050000 | errno.EACCES

#: `AUDIT_ARCH_I386`: a 32-bit entry point on either architecture tested here.
FOREIGN = 0x40000003
X32 = 0x40000000


def answer(program: bytes, nr: int, *args: int, arch: int = ARCH.audit_arch) -> int:
    """What the kernel answers a call with, running `program` over its `seccomp_data`."""
    data = struct.pack("=iIQ6Q", nr, arch, 0, *args, *([0] * (6 - len(args))))
    insns = [
        struct.unpack_from("HBBI", program, at) for at in range(0, len(program), 8)
    ]
    accumulator = 0
    pc = 0
    while True:
        code, jt, jf, k = insns[pc]
        pc += 1
        if code == 0x20:  # BPF_LD | BPF_W | BPF_ABS
            (accumulator,) = struct.unpack_from("=I", data, k)
        elif code == 0x54:  # BPF_ALU | BPF_AND | BPF_K
            accumulator &= k
        elif code == 0x15:  # BPF_JMP | BPF_JEQ | BPF_K
            pc += jt if accumulator == k else jf
        elif code == 0x35:  # BPF_JMP | BPF_JGE | BPF_K
            pc += jt if accumulator >= k else jf
        elif code == 0x06:  # BPF_RET | BPF_K
            return k
        else:
            pytest.fail(f"an instruction the kernel would refuse: {code:#x}")


def test_the_trap_filter_traps_what_it_is_given_and_nothing_else() -> None:
    program = build_program([NR.OPENAT, NR.OPENAT, NR.EXECVE, -1000])

    assert answer(program, NR.OPENAT) == TRACE
    assert answer(program, NR.EXECVE) == TRACE
    assert answer(program, NR.SOCKET) == ALLOW
    assert len(program) == 8 * (4 + 2 * 2 + 1)


def test_the_trap_filter_lets_a_foreign_architecture_through() -> None:
    assert answer(build_program([NR.OPENAT]), NR.OPENAT, arch=FOREIGN) == ALLOW


def test_the_whole_trap_set_fits() -> None:
    program = build_program(TRAPPED_SYSCALLS)

    assert all(answer(program, one) == TRACE for one in TRAPPED_SYSCALLS)
    assert answer(program, NR.EXIT_GROUP) == ALLOW


def test_an_empty_trap_set_traps_nothing() -> None:
    assert answer(build_program([]), NR.OPENAT) == ALLOW


def test_a_trap_set_too_large_to_jump_over_is_refused() -> None:
    with pytest.raises(ValueError, match="too large"):
        build_program(range(200))


NONBLOCK = getattr(socket, "SOCK_NONBLOCK", 0)
CLOEXEC = getattr(socket, "SOCK_CLOEXEC", 0)
AF_NETLINK = 16
AF_PACKET = 17
AF_VSOCK = 40
IPPROTO_SCTP = 132


@pytest.mark.parametrize(
    ("family", "kind", "protocol", "said"),
    [
        (socket.AF_INET, socket.SOCK_STREAM, 0, ALLOW),
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, ALLOW),
        (socket.AF_INET6, socket.SOCK_STREAM, 0, ALLOW),
        (socket.AF_INET, socket.SOCK_STREAM | NONBLOCK | CLOEXEC, 0, ALLOW),
        (socket.AF_INET, socket.SOCK_DGRAM, 0, EACCES),
        (socket.AF_INET6, socket.SOCK_DGRAM, socket.IPPROTO_UDP, EACCES),
        (socket.AF_INET, socket.SOCK_RAW, 1, EACCES),
        (socket.AF_INET, socket.SOCK_STREAM, IPPROTO_SCTP, EACCES),
        (socket.AF_UNIX, socket.SOCK_DGRAM, 0, ALLOW),
        (socket.AF_UNIX, socket.SOCK_STREAM, 0, ALLOW),
        (AF_NETLINK, socket.SOCK_RAW, 0, ALLOW),
        (AF_PACKET, socket.SOCK_RAW, 0, EACCES),
        (AF_VSOCK, socket.SOCK_STREAM, 0, EACCES),
    ],
)
def test_the_socket_filter_lets_only_tcp_and_local_sockets_be_made(
    family: int, kind: int, protocol: int, said: int
) -> None:
    assert answer(build_socket_program(), NR.SOCKET, family, kind, protocol) == said


@pytest.mark.parametrize(
    ("nr", "arch", "said"),
    [
        (NR.OPENAT, ARCH.audit_arch, ALLOW),
        (NR.CONNECT, ARCH.audit_arch, ALLOW),
        (NR.IO_URING_SETUP, ARCH.audit_arch, EACCES),
        (NR.SOCKET, FOREIGN, EACCES),
        (NR.OPENAT, FOREIGN, EACCES),
        (NR.SOCKET | X32, ARCH.audit_arch, EACCES),
    ],
)
def test_the_socket_filter_shuts_the_ways_round_it(
    nr: int, arch: int, said: int
) -> None:
    assert (
        answer(
            build_socket_program(), nr, socket.AF_INET, socket.SOCK_STREAM, arch=arch
        )
        == said
    )


@pytest.mark.parametrize(
    ("nr", "arch", "said"),
    [
        (NR.BIND, ARCH.audit_arch, NOTIFY),
        (NR.LISTEN, ARCH.audit_arch, NOTIFY),
        (NR.CONNECT, ARCH.audit_arch, ALLOW),
        (NR.SOCKET, ARCH.audit_arch, ALLOW),
        (NR.BIND, FOREIGN, EACCES),
        (NR.LISTEN | X32, ARCH.audit_arch, EACCES),
    ],
)
def test_the_listen_filter_hands_binds_and_listens_to_a_supervisor(
    nr: int, arch: int, said: int
) -> None:
    assert answer(build_listen_program(), nr, arch=arch) == said


def test_a_notification_is_the_call_it_says() -> None:
    call = Notification(id=7, pid=42, nr=NR.BIND, args=(3, 0, 16, 0, 0, 0))

    assert (call.id, call.pid, call.nr, call.args[0]) == (7, 42, NR.BIND, 3)
    assert call == Notification(7, 42, NR.BIND, (3, 0, 16, 0, 0, 0))

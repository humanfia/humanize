"""The socket filter, read by a BPF interpreter rather than by the kernel.

The kernel's answer is `tests/system/coganchor/test_landlock.py`, which creates the sockets. Here
the assembled program is run over hand-built `seccomp_data`, so that every branch is visited --
a foreign architecture and an x32 number included, which no process on this machine can be
asked to make.
"""

from __future__ import annotations

import errno
import socket
import struct

import pytest

from tests.supervising import WITHOUT_BINDINGS

if WITHOUT_BINDINGS:
    pytest.skip(WITHOUT_BINDINGS, allow_module_level=True)

from hmz.coganchor.linux import seccomp
from hmz.coganchor.linux.syscalls import ARCH, NR

ALLOW = 0x7FFF0000
DENY = 0x00050000 | errno.EACCES


def run(program: bytes, nr: int, *args: int, arch: int = ARCH.audit_arch) -> int:
    """What the filter returns for one syscall, by the handful of cBPF opcodes it uses."""
    data = struct.pack("<iIQ6Q", nr, arch, 0, *args, *[0] * (6 - len(args)))
    insns = [
        struct.unpack("HBBI", program[i : i + 8]) for i in range(0, len(program), 8)
    ]
    pc, acc = 0, 0
    while True:
        code, jt, jf, k = insns[pc]
        pc += 1
        if code == 0x20:
            (acc,) = struct.unpack_from("<I", data, k)
        elif code == 0x54:
            acc &= k
        elif code in (0x15, 0x35):
            taken = acc == k if code == 0x15 else acc >= k
            pc += jt if taken else jf
        elif code == 0x06:
            return k
        else:
            raise AssertionError(f"unexpected opcode {code:#x}")


@pytest.fixture(scope="module")
def program() -> bytes:
    return seccomp.build_socket_program()


@pytest.mark.parametrize("family", [socket.AF_INET, socket.AF_INET6])
@pytest.mark.parametrize("protocol", [0, socket.IPPROTO_TCP])
def test_a_tcp_socket_is_allowed(program: bytes, family: int, protocol: int) -> None:
    kind = socket.SOCK_STREAM | socket.SOCK_NONBLOCK | socket.SOCK_CLOEXEC

    assert run(program, NR.SOCKET, family, kind, protocol) == ALLOW


@pytest.mark.parametrize("family", [socket.AF_INET, socket.AF_INET6])
@pytest.mark.parametrize(
    "kind", [socket.SOCK_DGRAM, socket.SOCK_RAW, socket.SOCK_SEQPACKET]
)
def test_every_other_internet_socket_is_refused(
    program: bytes, family: int, kind: int
) -> None:
    assert run(program, NR.SOCKET, family, kind | socket.SOCK_CLOEXEC, 0) == DENY


@pytest.mark.parametrize("protocol", [132, 262])
def test_a_stream_socket_that_is_not_tcp_is_refused(
    program: bytes, protocol: int
) -> None:
    """SCTP and MPTCP: stream sockets that Landlock's TCP rules do not see."""
    assert run(program, NR.SOCKET, socket.AF_INET, socket.SOCK_STREAM, protocol) == DENY


@pytest.mark.parametrize("family", [socket.AF_PACKET, socket.AF_VSOCK, 30, 44])
@pytest.mark.parametrize("kind", [socket.SOCK_STREAM, socket.SOCK_DGRAM])
def test_every_other_family_is_refused_whatever_its_type(
    program: bytes, family: int, kind: int
) -> None:
    """Packet, a hypervisor's vsock, TIPC, XDP: none of them stay on this machine."""
    assert run(program, NR.SOCKET, family, kind, 0) == DENY


@pytest.mark.parametrize("family", [socket.AF_UNIX, socket.AF_NETLINK])
def test_a_socket_that_stays_on_this_machine_is_allowed(
    program: bytes, family: int
) -> None:
    assert run(program, NR.SOCKET, family, socket.SOCK_DGRAM, 0) == ALLOW


def test_other_syscalls_are_allowed(program: bytes) -> None:
    assert run(program, NR.CONNECT, socket.AF_INET, socket.SOCK_DGRAM) == ALLOW
    assert run(program, NR.OPENAT) == ALLOW


def test_io_uring_is_refused_because_a_ring_makes_sockets_of_its_own(
    program: bytes,
) -> None:
    assert run(program, NR.IO_URING_SETUP, 8, 0) == DENY


def test_a_foreign_architecture_and_an_x32_number_are_refused(program: bytes) -> None:
    assert run(program, 359, socket.AF_INET, socket.SOCK_DGRAM, arch=0x40000003) == DENY
    assert (
        run(program, NR.SOCKET | 0x40000000, socket.AF_INET, socket.SOCK_DGRAM) == DENY
    )


def test_the_trap_filter_is_unchanged_by_it() -> None:
    """Both are installed in one child, so neither may have moved under the other."""
    program = seccomp.build_program([NR.OPENAT])

    assert run(program, NR.OPENAT) == 0x7FF00000
    assert run(program, NR.SOCKET, socket.AF_INET, socket.SOCK_DGRAM) == ALLOW
    assert run(program, NR.OPENAT, arch=0x40000003) == ALLOW

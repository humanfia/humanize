"""Which socket addresses a fence that cuts the network lets a program listen on.

Linux only: collected there and nowhere else (see `conftest.py`).
"""

from __future__ import annotations

import ipaddress
import socket
import struct
import sys

import pytest

from hmz.coganchor.fence.loopback import loopback

#: Not in every platform's `socket`, though it is Linux's own.
AF_NETLINK = 16


def family(number: int) -> bytes:
    return number.to_bytes(2, sys.byteorder)


def inet(address: str, port: int = 8080) -> bytes:
    """A `struct sockaddr_in`."""
    return (
        family(socket.AF_INET)
        + struct.pack("!H", port)
        + ipaddress.IPv4Address(address).packed
        + bytes(8)
    )


def inet6(address: str, port: int = 8080) -> bytes:
    """A `struct sockaddr_in6`."""
    return (
        family(socket.AF_INET6)
        + struct.pack("!HI", port, 0)
        + ipaddress.IPv6Address(address).packed
        + bytes(4)
    )


@pytest.mark.parametrize(
    ("sockaddr", "answer"),
    [
        (inet("127.0.0.1"), True),
        (inet("127.8.9.10"), True),
        (inet("0.0.0.0"), False),  # noqa: S104 -- the address, not a bind
        (inet("10.0.0.1"), False),
        (inet("127.0.0.1")[:8], False),
        (inet6("::1"), True),
        (inet6("::ffff:127.0.0.1"), True),
        (inet6("::"), False),
        (inet6("::ffff:10.0.0.1"), False),
        (inet6("2001:db8::1"), False),
        (inet6("::1")[:20], False),
        (inet6("::1")[:24], True),
        (family(socket.AF_UNSPEC) + bytes(14), False),
        (family(socket.AF_UNIX) + b"/run/some.sock\0", None),
        (family(AF_NETLINK) + bytes(10), None),
        (b"\x02", None),
        (b"", None),
    ],
)
def test_loopback(sockaddr: bytes, answer: bool | None) -> None:
    assert loopback(sockaddr) is answer

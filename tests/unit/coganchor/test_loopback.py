"""Which socket addresses a fence that cuts the network lets a program listen on.

The kernel's answer is `tests/system/coganchor/test_fence.py`, which binds real sockets inside a
real fence. Here the addresses are laid out by hand, as the kernel lays them out in the memory
a `bind` names and in what `getsockname` returns, so that every family and length is visited.
"""

from __future__ import annotations

import socket
import struct
import sys

import pytest

from hmz.coganchor.fence.loopback import loopback


def _family(family: int) -> bytes:
    return family.to_bytes(2, sys.byteorder)


def inet(host: str, port: int = 0) -> bytes:
    """`struct sockaddr_in`."""
    return (
        _family(socket.AF_INET)
        + struct.pack("!H", port)
        + socket.inet_pton(socket.AF_INET, host)
        + bytes(8)
    )


def inet6(host: str, port: int = 0) -> bytes:
    """`struct sockaddr_in6`, with no scope and no flow label."""
    return (
        _family(socket.AF_INET6)
        + struct.pack("!HI", port, 0)
        + socket.inet_pton(socket.AF_INET6, host)
        + bytes(4)
    )


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.53", "127.255.255.254"])
def test_every_ipv4_loopback_address_is_loopback(host: str) -> None:
    assert loopback(inet(host, 8080)) is True


@pytest.mark.parametrize("host", ["::1", "::ffff:127.0.0.1", "::ffff:127.1.2.3"])
def test_ipv6_loopback_and_ipv4_loopback_mapped_into_it_are_loopback(host: str) -> None:
    assert loopback(inet6(host)) is True


@pytest.mark.parametrize("host", ["0.0.0.0", "10.0.0.5", "192.168.1.1", "8.8.8.8"])  # noqa: S104
def test_every_other_ipv4_address_is_not(host: str) -> None:
    assert loopback(inet(host)) is False


@pytest.mark.parametrize(
    "host",
    [
        "::",
        "fe80::1",
        "2001:db8::1",
        "::ffff:0.0.0.0",
        "::ffff:10.0.0.1",
        "::127.0.0.1",
    ],
)
def test_every_other_ipv6_address_is_not(host: str) -> None:
    """`::127.0.0.1` is the deprecated IPv4-compatible form, which is not loopback."""
    assert loopback(inet6(host)) is False


def test_an_address_too_short_for_its_family_is_not() -> None:
    assert loopback(inet("127.0.0.1")[:8]) is False
    assert loopback(inet6("::1")[:20]) is False


def test_an_unspecified_family_is_not_since_ipv4_takes_it_for_every_address() -> None:
    assert loopback(_family(socket.AF_UNSPEC) + bytes(14)) is False


@pytest.mark.parametrize(
    "sockaddr",
    [
        _family(socket.AF_UNIX) + b"/tmp/x.sock\0",
        _family(socket.AF_UNIX) + b"\0abstract",
        _family(socket.AF_UNIX),
        _family(socket.AF_NETLINK) + bytes(10),
        b"",
    ],
)
def test_an_address_of_no_internet_family_is_not_judged(sockaddr: bytes) -> None:
    assert loopback(sockaddr) is None

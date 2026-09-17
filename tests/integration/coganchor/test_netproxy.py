"""Routing the agent's own TCP connections through the target, decided in this process.

Everything here drives :class:`NetProxy` against the `link` fixture -- both halves of a
session wired together over a `socketpair`, with no subprocess, no supervisor and nobody
else's network. What is checked is the decision: which destinations are left alone, which
are given a stand-in, and that the stand-in carries the bytes.

The other half is `tests/system/coganchor/test_netproxy.py`, where the `connect` being
redirected is a real traced agent's.

One thing here is not hermetic, and deliberately: `echo_server` binds an address on this host
that is *not* loopback, because loopback is exactly what the proxy is meant to leave alone --
an echo server on 127.0.0.1 would be left alone too and prove nothing. It never leaves the
machine, but it does need the machine to have a routable interface, and skips aloud where
there is none.
"""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING

from hmz.coganchor.netproxy import NetProxy

if TYPE_CHECKING:
    from tests.coganchor.fixtures import Link


def test_loopback_connections_are_left_alone(link: Link) -> None:
    proxy = NetProxy(link.client)
    proxy.start()
    try:
        assert proxy.redirect("127.0.0.1", 8080, socket.AF_INET) is None
        assert proxy.redirect("::1", 8080, socket.AF_INET6) is None
    finally:
        proxy.close()


def test_allow_listed_hosts_are_left_alone(link: Link) -> None:
    proxy = NetProxy(link.client, keep_local=("203.0.113.7", "198.51.100.9:443"))
    proxy.start()
    try:
        assert proxy.redirect("203.0.113.7", 443, socket.AF_INET) is None
        assert proxy.redirect("198.51.100.9", 443, socket.AF_INET) is None
        assert proxy.redirect("198.51.100.9", 80, socket.AF_INET) is not None
    finally:
        proxy.close()


def test_an_allow_listed_hostname_is_resolved(link: Link) -> None:
    """``connect`` names an address, so a hostname must be resolved to match.

    Without this the entry is compared against a numeric address it can never
    equal, and the connection is tunnelled out of the target regardless.
    """
    proxy = NetProxy(link.client, keep_local=("localhost:443",))
    proxy.start()
    try:
        assert proxy.redirect("127.0.0.1", 443, socket.AF_INET) is None
        # A name that resolves to nothing must not smuggle anything through.
        assert NetProxy(
            link.client, keep_local=("no-such-host.invalid",)
        )._keep_local == frozenset({"no-such-host.invalid"})
    finally:
        proxy.close()


def test_a_destination_always_maps_to_the_same_listener(link: Link) -> None:
    proxy = NetProxy(link.client)
    proxy.start()
    try:
        first = proxy.redirect("203.0.113.7", 443, socket.AF_INET)
        assert first == proxy.redirect("203.0.113.7", 443, socket.AF_INET)
        assert first != proxy.redirect("203.0.113.7", 8443, socket.AF_INET)
    finally:
        proxy.close()


def test_an_ipv6_destination_is_replaced_by_an_ipv6_stand_in(link: Link) -> None:
    """An AF_INET6 socket handed an IPv4 sockaddr fails EINVAL, so keep the family."""
    proxy = NetProxy(link.client)
    proxy.start()
    try:
        stand_in = proxy.redirect("2001:db8::1", 443, socket.AF_INET6)
        assert stand_in is not None
        assert stand_in[0] == "::1", "an IPv6 socket cannot be handed a v4 address"
        listener = proxy._listeners[("2001:db8::1", 443)]
        assert listener.family == socket.AF_INET6, "nor reach a v4 listener"
    finally:
        proxy.close()


def test_traffic_reaches_the_destination_through_the_target(
    link: Link, echo_server: tuple[str, int]
) -> None:
    """Data sent to the loopback stand-in comes back from the real server."""
    proxy = NetProxy(link.client)
    proxy.start()
    try:
        stand_in = proxy.redirect(*echo_server, socket.AF_INET)
        assert stand_in is not None

        with socket.create_connection(stand_in, timeout=10) as connection:
            connection.sendall(b"ping")
            connection.settimeout(10)
            assert connection.recv(100) == b"echo:ping"
    finally:
        proxy.close()

"""Which hosts and ports a fence's allow-list passes, as the proxy asks it."""

from __future__ import annotations

import pytest

from hmz.coganchor.fence import permits


@pytest.mark.parametrize(
    ("allowed", "host", "port", "passes"),
    [
        # An exact host, on either of the usual ports and no other.
        (["api.example.com"], "api.example.com", 443, True),
        (["api.example.com"], "api.example.com", 80, True),
        (["api.example.com"], "api.example.com", 8080, False),
        (["api.example.com"], "example.com", 443, False),
        (["api.example.com"], "evil.api.example.com", 443, False),
        # Compared without case, a trailing dot or surrounding space.
        (["API.Example.com."], "api.example.COM", 443, True),
        ([" api.example.com "], "api.example.com.", 443, True),
        # A wildcard passes every name under its suffix, not the suffix itself.
        (["*.googleapis.com"], "oauth2.googleapis.com", 443, True),
        (["*.googleapis.com"], "a.b.googleapis.com", 443, True),
        (["*.googleapis.com"], "googleapis.com", 443, False),
        (["*.googleapis.com"], "evilgoogleapis.com", 443, False),
        # An entry naming a port passes that port and no other.
        (["gw.internal:8443"], "gw.internal", 8443, True),
        (["gw.internal:8443"], "gw.internal", 443, False),
        # An address passes only where that address is listed.
        (["api.example.com"], "10.0.0.1", 443, False),
        (["10.0.0.1"], "10.0.0.1", 443, True),
        (["10.0.0.1:9000"], "10.0.0.1", 9000, True),
        (["*.0.0.1"], "127.0.0.1", 443, False),
        (["[::1]"], "::1", 443, True),
        (["[::1]"], "[::1]", 80, True),
        (["[::1]:8080"], "::1", 8080, True),
        (["[::1]:8080"], "::1", 443, False),
        (["2001:db8::1"], "2001:db8:0::1", 443, True),
        (["2001:db8::1"], "2001:db8::2", 443, False),
        # Nothing passes an empty host, or an empty list.
        (["api.example.com"], "", 443, False),
        ([], "api.example.com", 443, False),
        # Any one entry is enough.
        (["a.example", "b.example"], "b.example", 443, True),
    ],
)
def test_permits(allowed: list[str], host: str, port: int, passes: bool) -> None:
    assert permits(allowed, host, port) is passes


def test_the_usual_ports_can_be_named() -> None:
    assert permits(["git.example"], "git.example", 22, ports=[22])
    assert not permits(["git.example"], "git.example", 443, ports=[22])

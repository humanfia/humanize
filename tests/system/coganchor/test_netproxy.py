"""The agent's own connections, redirected by the supervisor that traps its ``connect``.

Both tests here run a real program under a real anchored session, so the redirect is decided
in the syscall the agent made rather than by calling :class:`NetProxy` directly: what a
machine without ptrace cannot answer is whether an agent that was never asked still ends up
talking through the target.

The decisions themselves -- which destinations get a stand-in, and that the stand-in carries
bytes -- are `tests/integration/coganchor/test_netproxy.py`, over a `socketpair` and in one
process.

`echo_server` binds an address on this host that is *not* loopback, deliberately: loopback is
what a session leaves alone, so an echo server there would prove nothing either way. Nothing
leaves the machine, but the machine does have to have a routable interface, and the fixture
skips aloud where it has none.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.coganchor.fixtures import Anchorage


@pytest.mark.timeout(120)
def test_agent_connections_are_tunnelled_end_to_end(
    anchorage: Anchorage, echo_server: tuple[str, int]
) -> None:
    """A ``connect`` from the traced agent itself is redirected and still works."""
    host, port = echo_server
    program = (
        "import socket\n"
        f"s = socket.create_connection(({host!r}, {port}), timeout=20)\n"
        "s.sendall(b'from-the-agent')\n"
        "print(s.recv(100).decode())\n"
    )
    result = anchorage.run("python3", "-c", program, net="remote", timeout=90)
    assert "echo:from-the-agent" in result.stdout, result.stderr


@pytest.mark.timeout(120)
def test_local_net_mode_leaves_connections_alone(
    anchorage: Anchorage, echo_server: tuple[str, int]
) -> None:
    """The default keeps the agent's own traffic on this machine and working."""
    host, port = echo_server
    program = (
        "import socket\n"
        f"s = socket.create_connection(({host!r}, {port}), timeout=20)\n"
        "s.sendall(b'direct')\n"
        "print(s.recv(100).decode())\n"
    )
    result = anchorage.run("python3", "-c", program, timeout=90)
    assert "echo:direct" in result.stdout, result.stderr

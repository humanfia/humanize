"""A web on one end's loopback, reached through the other end's, over the stand-in EasyTier.

The stand-in carries TCP the way the real one is told to: what is checked here is that
`serving` and `joining` tell it the same network, the serving end's port and no other, and the
secret in the environment rather than on the command line. The real network is a system
test's.
"""

from __future__ import annotations

import http.server
import socket
import threading
import time
import urllib.request
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import easytier
from tests.integration.doubles_easytier import Core, faked

if TYPE_CHECKING:
    import subprocess
    from collections.abc import Iterator
    from pathlib import Path

SECRET = "correct horse battery staple"
PEERS = ("tcp://node.example:11010",)
PATIENCE = 20.0


def _free() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class _Hello(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        said = b"hello from the server"
        self.send_response(200)
        self.send_header("Content-Length", str(len(said)))
        self.end_headers()
        self.wfile.write(said)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        del format, args


@pytest.fixture
def core(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Core:
    return faked(tmp_path, monkeypatch)


@pytest.fixture
def web() -> Iterator[int]:
    """A web on this machine's loopback, by port."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Hello)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def running() -> Iterator[list[subprocess.Popen[bytes]]]:
    """Whatever a test starts, stopped after it."""
    started: list[subprocess.Popen[bytes]] = []
    yield started
    for one in started:
        one.terminate()
    for one in started:
        one.wait(PATIENCE)


def _got(port: int, patience: float = PATIENCE) -> bytes | None:
    """What the web through a joined port says, or None where nothing reaches it in time."""
    until = time.monotonic() + patience
    while time.monotonic() < until:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/", timeout=2
            ) as answer:
                return answer.read()
        except OSError:
            time.sleep(0.1)
    return None


def _joined(port: int) -> None:
    """Waits for a joining end to listen, so that what it then refuses is the network's."""
    until = time.monotonic() + PATIENCE
    while True:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
        except OSError:
            assert time.monotonic() < until, "the joining end never listened"
            time.sleep(0.05)
        else:
            return


def _served(core: Core) -> None:
    until = time.monotonic() + PATIENCE
    while not any(core.networks.iterdir()):
        assert time.monotonic() < until, "the serving end never joined"
        time.sleep(0.05)


def test_a_joined_port_reaches_the_served_one(
    core: Core, web: int, running: list[subprocess.Popen[bytes]]
) -> None:
    running.append(easytier.serving(SECRET, web, peers=PEERS))
    _served(core)
    local = _free()
    running.append(easytier.joining(SECRET, local, port=web, peers=PEERS))
    assert _got(local) == b"hello from the server"
    name, hidden = easytier.network(SECRET)
    told = core.told()
    assert len(told) == 2
    for argv, secret in told:
        assert secret
        assert name in argv
        assert SECRET not in " ".join(argv)
        assert hidden not in argv


def test_another_secret_reaches_nothing(
    core: Core, web: int, running: list[subprocess.Popen[bytes]]
) -> None:
    running.append(easytier.serving(SECRET, web, peers=PEERS))
    _served(core)
    local = _free()
    running.append(
        easytier.joining(SECRET.replace("horse", "mouse"), local, port=web, peers=PEERS)
    )
    _joined(local)
    assert _got(local, 2.0) is None


def test_only_the_served_port_is_reached(
    core: Core, web: int, running: list[subprocess.Popen[bytes]]
) -> None:
    running.append(easytier.serving(SECRET, _free(), peers=PEERS))
    _served(core)
    local = _free()
    running.append(easytier.joining(SECRET, local, port=web, peers=PEERS))
    _joined(local)
    assert _got(local, 2.0) is None

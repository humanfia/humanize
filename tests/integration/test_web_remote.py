"""Another machine's daemon, reached by the page through `/dial`.

Over `stdio:ssh`, the other machine is this one under a home of its own, reached by the stand-in
`ssh` of `doubles_ssh`. Over `tcp`, it is a daemon of another home serving a listener, paired by
a code it made: the page claims it over `/dial`, which opens mutual TLS as this machine's device.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from typing import TYPE_CHECKING

import pytest
from websockets.exceptions import ConnectionClosed

from hmz.daemon import where
from hmz.reach import WebSocketPipe
from hmz.rpc import Peer, hello
from hmz.trust import pairing

from .doubles_ssh import Host, faked
from .doubles_web import PATIENCE, Browser, served, states

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from pathlib import Path

    from websockets.sync.client import ClientConnection

pytestmark = [
    pytest.mark.timeout(180),
    pytest.mark.usefixtures("daemon"),
    pytest.mark.filterwarnings("ignore:.*use of fork.*:DeprecationWarning"),
]

#: The other machine, as a `stdio:ssh` route names it.
BOX = "stdio:ssh://me@box.example?option=Compression=yes"


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Host]:
    """The other machine, with this version of `hmz`."""
    found = faked(tmp_path, monkeypatch)
    yield found
    # The daemon `hmz daemon connect --stdio` started there, which outlives its client.
    pid = where.held(found.tmp / f"humanize-{os.getuid()}").get("pid")
    if isinstance(pid, int):
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)


def _dial(route: str, pinned: str = "") -> str:
    from urllib.parse import urlencode

    return f"/dial?{urlencode({'route': route, 'id': pinned})}"


def _closed(socket_: ClientConnection) -> tuple[int, str]:
    """How the server closed a WebSocket: its code and its reason."""
    with contextlib.suppress(ConnectionClosed):
        while True:
            socket_.recv(timeout=PATIENCE)
    assert socket_.close_code is not None
    return socket_.close_code, socket_.close_reason or ""


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def test_what_dial_does_not_open_is_refused_saying_why(tmp_path: Path) -> None:
    del tmp_path
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        for route, why in (
            ("unix:", "unix: is not dialed here."),
            ("stdio:local", "stdio:local is not dialed here."),
            (
                "webrtc:wss://relay.example",
                "webrtc:wss://relay.example is not dialed here.",
            ),
            ("nothing", "nothing is not a route."),
            (
                "tcp://127.0.0.1:9",
                "tcp://127.0.0.1:9 needs the id of the daemon it reaches.",
            ),
        ):
            assert _closed(browser.opens(_dial(route))) == (1008, why)


def test_a_daemon_over_ssh_is_dialed_and_spoken_to(host: Host) -> None:
    project = host.home / "project"
    project.mkdir()
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        with browser.session(_dial(BOX)) as there:
            assert there.said["device"] == "local"
            assert len(there.said["daemon_id"]) == 52
            assert there.call("hosts.list") == {"held": []}
            listed = there.call("workspaces.list", here=str(project))
            assert str(project) in str(listed)
            pids = host.pids()
            told = host.told()
            assert any("Compression=yes" in one for one in told[-1])
            assert "hmz daemon connect --stdio" in told[-1][-1]
        # The ssh started for it stops once the page lets it go.
        ending = time.monotonic() + PATIENCE
        while not all(_gone(pid) for pid in pids):
            assert time.monotonic() < ending, "the ssh dialed was never stopped"
            time.sleep(0.05)


def test_another_version_there_is_installed_and_said_as_it_is(
    host: Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.metadata

    real = importlib.metadata.version

    def released(name: str) -> str:
        # A release of this hmz, which a development build is not.
        return "1.2.3" if name == "hmz" else real(name)

    host.installs("1.0.0")
    monkeypatch.setattr(importlib.metadata, "version", released)
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        socket_ = browser.opens(_dial(BOX))
        said = states(socket_)
        socket_.close()
    assert said[0] == {"state": "connecting", "detail": ""}
    assert {"state": "installing", "detail": "hmz 1.2.3"} in said
    assert said[-1] == {"state": "up", "detail": ""}
    assert "hmz==1.2.3" in host.installed()


#: What `/dial` says of a host with no `hmz`: by the route's host, as it is told no name.
MISSING = "hmz is not installed on box.example."


def _asked(socket_: ClientConnection) -> list[dict[str, str]]:
    """Every state `/dial` says until it asks."""
    said: list[dict[str, str]] = []
    while not said or said[-1]["state"] != "asking":
        message = socket_.recv(timeout=PATIENCE)
        assert isinstance(message, str)
        said.append(json.loads(message))
    return said


def test_none_there_is_asked_about_and_installed_once_the_page_says_to(
    host: Host,
) -> None:
    host.installs(None)
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        socket_ = browser.opens(_dial(BOX))
        # An answer to no question does nothing.
        socket_.send(json.dumps({"install": True}))
        said = _asked(socket_)
        assert said[0] == {"state": "connecting", "detail": ""}
        assert said[-1] == {"state": "asking", "detail": MISSING}
        assert not host.installed()

        socket_.send(json.dumps({"install": True}))
        said = states(socket_)
        assert "installing" in [one["state"] for one in said]
        assert said[-1] == {"state": "up", "detail": ""}
        assert host.installed().split()[-1].startswith("hmz")
        peer = Peer(WebSocketPipe(socket_, trusted=True), lambda _: None, name="page")
        try:
            assert hello(peer, "page", "web", timeout=PATIENCE)["device"] == "local"
        finally:
            peer.close()
            socket_.close()


def test_a_no_fails_the_dial(host: Host) -> None:
    host.installs(None)
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        socket_ = browser.opens(_dial(BOX))
        _asked(socket_)
        socket_.send(json.dumps({"install": False}))
        assert states(socket_)[-1] == {"state": "failed", "detail": MISSING}
        assert _closed(socket_) == (1011, MISSING)
        assert not host.installed()


@pytest.mark.parametrize("text", ["hello", "{}", '{"install": 1}', "[true]"])
def test_other_text_before_it_is_up_closes_the_dial(host: Host, text: str) -> None:
    host.installs(None)
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        socket_ = browser.opens(_dial(BOX))
        _asked(socket_)
        socket_.send(text)
        # Closed by the server, whichever of its two threads says so first.
        assert _closed(socket_)[0] in (1000, 1011)
        assert not host.installed()


def test_a_daemon_that_cannot_be_reached_says_why(host: Host) -> None:
    del host
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        socket_ = browser.opens(_dial("stdio:ssh://unreachable.example"))
        said = states(socket_)
        assert said[-1]["state"] == "failed"
        assert "Could not resolve hostname" in said[-1]["detail"]
        code, why = _closed(socket_)
        assert code == 1011
        assert "Could not resolve hostname" in why


def test_a_daemon_that_cannot_be_started_there_says_why(host: Host) -> None:
    host.cannot_connect("No space left on device")
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        socket_ = browser.opens(_dial(BOX))
        assert states(socket_)[-1] == {"state": "up", "detail": ""}
        assert _closed(socket_) == (
            1000,
            "hmz: the daemon cannot be reached: No space left on device",
        )


@contextlib.contextmanager
def _another(tmp_path: Path) -> Generator[pairing.Code]:
    """A daemon of another home, serving a TCP listener, and a pairing code it made."""
    there = dict(os.environ)
    there["HUMANIZE_HOME"] = str(tmp_path / "there-home")
    # Short, as a socket's path under it must be.
    there["TMPDIR"] = tempfile.mkdtemp(prefix="a", dir=os.environ.get("TMPDIR"))
    serving = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "hmz",
            "daemon",
            "serve",
            "--listen",
            "tcp://127.0.0.1:0",
        ],
        env=there,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # Listening once it says so: a pair asked before then starts a daemon of its own,
        # which this one then finds already running.
        assert serving.stdout is not None
        said = serving.stdout.readline()
        assert "listening on tcp://" in said, said + serving.communicate()[1]
        ending = time.monotonic() + PATIENCE
        while True:
            paired = subprocess.run(
                [sys.executable, "-m", "hmz", "daemon", "pair"],
                env=there,
                capture_output=True,
                text=True,
                check=False,
            )
            code = (
                pairing.read(paired.stdout.strip()) if paired.returncode == 0 else None
            )
            if code is not None and code.routes:
                break
            assert serving.poll() is None, serving.communicate()[1]
            assert time.monotonic() < ending, paired.stderr
            time.sleep(0.2)
        yield code
    finally:
        serving.terminate()
        serving.communicate(timeout=PATIENCE)


def test_a_daemon_over_tcp_is_paired_through_dial_and_pinned(tmp_path: Path) -> None:
    with _another(tmp_path) as code, served() as site:
        browser = Browser(site)
        browser.signs_in()
        (route,) = code.routes
        with browser.session(_dial(route, code.id)) as there:
            assert there.said["daemon_id"] == code.id
            assert there.said["paired"] is False
            claimed = there.call("pair.claim", token=code.token, name="this-machine")
            assert claimed == {"daemon_id": code.id, "device": "this-machine"}
        with browser.session(_dial(route, code.id)) as there:
            assert there.said["paired"] is True
            assert there.said["device"] == "this-machine"
            assert there.call("hosts.list") == {"held": []}

        # Pinning another id, the carrier is refused for what answers.
        other = "a" * 52
        socket_ = browser.opens(_dial(route, other))
        said = states(socket_)
        assert said[-1]["state"] == "failed"
        assert "not the daemon" in said[-1]["detail"]

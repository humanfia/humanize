"""A P2P daemon: another machine's `hmz web`, reached over the stand-in EasyTier.

The other machine is this one under a home of its own, its interface served by a process of
its own on the port the network reaches, with the key its secret gives, as `hmz server` keeps
it; the stand-in `easytier-core` of `doubles_easytier` carries TCP between the two ends.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import easytier
from hmz.runtime.doing.daemons import Remotes

from .doubles_easytier import Core, faked
from .doubles_ssh import written
from .doubles_web import PATIENCE, Answer, Browser, served

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

SECRET = "correct horse battery staple"

#: The node a P2P daemon is written down with; the stand-in reaches no node.
PEERS = ["tcp://127.0.0.1:11010"]

#: The other machine's interface: this one's, at the version it is told, its key the one its
#: secret gives, served on the port it is told until its standard input closes.
_FAR = """
import os, sys, threading
import hmz.coganchor
from hmz.coganchor import easytier
from hmz.web import listening

if sys.argv[2]:
    hmz.coganchor.__version__ = sys.argv[2]
with listening(port=int(sys.argv[1]), apart=False) as site:
    site._key = easytier.key(os.environ.pop("FAR_SECRET"))
    threading.Thread(target=site.serve_forever, daemon=True).start()
    print("listening", flush=True)
    sys.stdin.read()
    site.shutdown()
"""


class _Far:
    """The other machine: its interface, and its end of the network, each started here."""

    def __init__(self, there: Path) -> None:
        self.there = there
        self.started: list[subprocess.Popen[Any]] = []

    def starts(self, version: str = "") -> None:
        """Starts its interface, saying this version or this one's, then its end."""
        (self.there / "humanize").mkdir(parents=True, exist_ok=True)
        web = subprocess.Popen(
            [sys.executable, "-c", _FAR, str(easytier.PORT), version],
            cwd=self.there,
            env=os.environ
            | {
                "HOME": str(self.there),
                "HUMANIZE_HOME": str(self.there / "humanize"),
                "FAR_SECRET": SECRET,
            },
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.started.append(web)
        assert web.stdout is not None
        assert web.stdout.readline().strip() == "listening"
        self.serves()

    def serves(self) -> subprocess.Popen[bytes]:
        """Starts its end of the network."""
        server = easytier.serving(SECRET, easytier.PORT, peers=PEERS)
        self.started.append(server)
        return server

    def stops(self) -> None:
        for one in self.started:
            if one.stdin is not None:
                one.stdin.close()
            else:
                one.terminate()
        for one in self.started:
            one.wait(PATIENCE)


def _free() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def core(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Core:
    """The stand-in EasyTier, and a port of the test's own for the network to reach."""
    monkeypatch.setattr(easytier, "PORT", _free())
    return faked(tmp_path, monkeypatch)


@pytest.fixture
def far(tmp_path: Path, core: Core) -> Iterator[_Far]:
    """The other machine, written down here as the P2P daemon `far`."""
    del core
    machine = _Far(tmp_path / "there")
    written({"name": "far", "via": "easytier", "secret": SECRET, "peers": PEERS})
    yield machine
    machine.stops()


def _stands(remotes: Remotes, *states: str) -> dict[str, str]:
    ending = time.monotonic() + PATIENCE
    while (said := remotes.state("far"))["state"] not in states:
        assert time.monotonic() < ending, f"far never came to {states}: {said}"
        time.sleep(0.05)
    return said


def _asked(browser: Browser, path: str) -> Answer:
    ending = time.monotonic() + PATIENCE
    while (answer := browser.get(path)).status == 503:
        assert time.monotonic() < ending, answer.body
        time.sleep(0.1)
    return answer


def _runs(core: Core, *, of: str) -> list[int]:
    """Every run of the stand-in so far told `of`, by pid."""
    runs = [json.loads(line) for line in core.log.read_text().splitlines()]
    return [run["pid"] for run in runs if of in run["argv"]]


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def test_a_page_reads_a_p2p_daemon_through_its_network(core: Core, far: _Far) -> None:
    far.starts()
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        listed = _asked(browser, "/d/far/api/workspaces")
        assert listed.status == 200, listed.body
        assert str(far.there) in str(listed.json())
        state = browser.get("/api/daemons/far/state").json()
        assert state == {"state": "up", "detail": "", "version": "0.0.0"}
        ours = browser.get("/api/daemons").json()["daemons"][1]
        assert (ours["via"], ours["secret"], ours["peers"]) == ("easytier", True, PEERS)
    told = core.told()
    joining = [argv for argv, _ in told if "--port-forward" in argv]
    assert joining
    assert all(argv[argv.index("--peers") + 1] == PEERS[0] for argv in joining)
    assert all(SECRET not in " ".join(argv) for argv, _ in told)


def test_an_older_server_is_refused(far: _Far) -> None:
    far.starts("1.0.0")
    remotes = Remotes(version="1.2.3")
    try:
        remotes.connect("far")
        assert _stands(remotes, "failed") == {
            "state": "failed",
            "detail": "far is served by an older Humanize, hmz 1.0.0; "
            "serve it with hmz 1.2.3.",
            "version": "1.0.0",
        }
    finally:
        remotes.close()


def test_a_server_lost_is_reached_again_and_closing_reaps_easytier(
    core: Core, far: _Far
) -> None:
    far.starts()
    remotes = Remotes()
    try:
        remotes.connect("far")
        _stands(remotes, "up")
        # Its end of the network stopped, as the machine going would stop it.
        os.kill(_runs(core, of="--ipv4")[0], signal.SIGTERM)
        _stands(remotes, "connecting", "failed")
        far.serves()
        assert _stands(remotes, "up")["version"] == "0.0.0"
    finally:
        remotes.close()
    joined = _runs(core, of="--port-forward")
    assert len(joined) >= 2
    assert all(_gone(pid) for pid in joined)
    assert remotes.state("far")["state"] == "idle"

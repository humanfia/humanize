"""The daemon of another machine, reached over its routes as `Remotes` reaches it.

Over `stdio:ssh`, the other machine is this one under a home of its own, reached by the
stand-in `ssh` of `doubles_ssh`, whose `hmz daemon connect --stdio` starts that home's daemon
as the real one would start the one installed there. Over `tcp`, it is `hmz daemon serve`
under a home of its own, listening on loopback, paired from the code `hmz devices pair` makes.
Over `easytier`, it is that same daemon behind the stand-in EasyTier network of
`doubles_easytier`, whose serving end lets its TCP port through, never EasyTier's fixed one.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from importlib.metadata import version
from typing import TYPE_CHECKING

import pytest

from hmz import config
from hmz.coganchor import easytier, settings
from hmz.daemon import link, where
from hmz.reach import SocketPipe
from hmz.runtime.doing.daemons import Daemons, Remotes, Unreached
from hmz.trust import identity, tls
from tests.conftest import places

from . import doubles_easytier
from .doubles_ssh import Host, faked, written

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

pytestmark = [
    pytest.mark.timeout(180),
]

#: How long a test waits for something another process is doing.
PATIENCE = 60.0


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Host]:
    """The other machine, written down as `box`, with this version of `hmz`."""
    found = faked(tmp_path, monkeypatch)
    written(
        {
            "name": "box",
            "id": "",
            "routes": ["stdio:ssh://me@box.example?option=Compression=yes"],
        }
    )
    yield found
    # The daemon `hmz daemon connect --stdio` started there, which outlives its client.
    pid = where.held(found.tmp / f"humanize-{os.getuid()}").get("pid")
    if isinstance(pid, int):
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)


def _stands(remotes: Remotes, name: str, *states: str) -> dict[str, str]:
    """How a daemon stands, once it stands as one of `states`."""
    ending = time.monotonic() + PATIENCE
    while (said := remotes.state(name))["state"] not in states:
        assert time.monotonic() < ending, f"{name} never came to {states}: {said}"
        time.sleep(0.05)
    return said


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def _daemons() -> list[dict[str, object]]:
    return tomllib.loads((config() / "settings.toml").read_text())["daemons"]


def test_a_daemon_over_ssh_is_reached_pinned_and_attached(host: Host) -> None:
    project = host.home / "project"
    project.mkdir()
    remotes = Remotes()
    try:
        client = remotes.client("box")
        assert remotes.state("box") == {
            "state": "up",
            "detail": "",
            "version": version("hmz"),
        }
        assert client.device == "local"
        assert _daemons()[0]["id"] == client.daemon_id
        assert len(client.daemon_id) == 52

        with link.remote(remotes, "box", str(project)) as attached:
            assert attached.client
            assert next(iter(attached))["type"]
        client.call("hosts.stop", {"workspace": str(project)})
        told = host.told()
        assert any("Compression=yes" in one for one in told[-1])
        assert "hmz daemon connect --stdio" in told[-1][-1]
        pids = host.pids()
    finally:
        remotes.close()
    assert remotes.state("box")["state"] == "idle"
    assert all(_gone(pid) for pid in pids)


def test_a_daemon_that_cannot_be_reached_says_why(host: Host) -> None:
    del host
    written({"name": "gone", "id": "", "routes": ["stdio:ssh://unreachable.example"]})
    remotes = Remotes()
    try:
        remotes.connect("gone")
        said = _stands(remotes, "gone", "failed")
        assert "Could not resolve hostname" in said["detail"]
        with pytest.raises(Unreached) as unreached:
            remotes.client("gone")
        assert unreached.value.seen["state"] == "failed"
    finally:
        remotes.close()


def test_a_daemon_that_cannot_be_started_there_says_why(host: Host) -> None:
    host.cannot_connect("No space left on device")
    remotes = Remotes()
    try:
        with pytest.raises(Unreached) as unreached:
            remotes.client("box")
        assert unreached.value.seen == {
            "state": "failed",
            "detail": "hmz: the daemon cannot be reached: No space left on device",
            "version": "",
        }
    finally:
        remotes.close()


def test_another_version_there_is_replaced_with_this_one(host: Host) -> None:
    host.installs("1.0.0")
    remotes = Remotes(version="1.2.3")
    try:
        remotes.connect("box")
        said = _stands(remotes, "box", "up", "failed")
        assert said["state"] == "up", said
        assert host.installed().split() == [
            "tool",
            "install",
            "--force",
            "--python",
            ">=3.12",
            "hmz==1.2.3",
        ]
    finally:
        remotes.close()


def test_one_running_epics_there_is_left_alone(host: Host) -> None:
    host.installs("1.0.0")
    host.runs_epics()
    remotes = Remotes(version="1.2.3")
    try:
        remotes.connect("box")
        said = _stands(remotes, "box", "up", "failed")
        assert "hmz 1.0.0 there holds running epics; hmz 1.2.3 waits" in said["detail"]
        assert not host.installed()
    finally:
        remotes.close()


#: What a host with no `hmz` is said to be, and how long none is tried again is watched for:
#: longer than the first two waits of a daemon that is.
MISSING = "hmz is not installed on box."
QUIET = 3.5


def test_none_there_is_not_installed_with_nobody_to_ask(host: Host) -> None:
    host.installs(None)
    remotes = Remotes(version="1.2.3")
    try:
        remotes.connect("box")
        said = _stands(remotes, "box", "failed")
        assert said["detail"] == MISSING
        probed = len(host.pids())
        time.sleep(QUIET)
        assert len(host.pids()) == probed
        assert remotes.state("box") == said
        assert not host.installed()

        remotes.connect("box")
        ending = time.monotonic() + PATIENCE
        while len(host.pids()) == probed:
            assert time.monotonic() < ending
            time.sleep(0.05)
        assert _stands(remotes, "box", "failed")["detail"] == MISSING
    finally:
        remotes.close()


def test_none_there_is_installed_unasked_where_that_was_said(host: Host) -> None:
    host.installs(None)
    remotes = Remotes(version="1.2.3", install=True)
    seen: set[str] = set()
    try:
        remotes.connect("box")
        while (said := remotes.state("box"))["state"] not in ("up", "failed"):
            seen.add(said["state"])
            time.sleep(0.01)
        assert said["state"] == "up", said
        assert "asking" not in seen
        assert host.installed().split()[-1] == "hmz==1.2.3"
    finally:
        remotes.close()


def test_none_there_is_asked_about_and_installed_on_yes(host: Host) -> None:
    host.installs(None)
    remotes = Remotes(version="1.2.3", install=None)
    try:
        remotes.connect("box")
        said = _stands(remotes, "box", "asking", "up", "failed")
        assert said == {"state": "asking", "detail": MISSING, "version": ""}
        assert not host.installed()
        began = time.monotonic()
        with pytest.raises(Unreached, match="hmz is not installed on box") as unreached:
            remotes.client("box")
        assert time.monotonic() - began < 5
        assert unreached.value.seen["state"] == "asking"
        # The probe has ended: no ssh is left running while the user is asked.
        assert all(_gone(pid) for pid in host.pids())

        assert remotes.answer("box", True)["state"] != "asking"
        assert _stands(remotes, "box", "up", "failed")["state"] == "up"
        assert host.installed().split()[-1] == "hmz==1.2.3"

        # None there again: the yes is remembered, and it is installed unasked.
        host.installs(None)
        os.kill(host.pids()[-1], signal.SIGTERM)
        seen: set[str] = set()
        ending = time.monotonic() + PATIENCE
        while len(host.installed().splitlines()) < 2:
            seen.add(remotes.state("box")["state"])
            assert time.monotonic() < ending
            time.sleep(0.01)
        assert "asking" not in seen
        assert _stands(remotes, "box", "up", "failed")["state"] == "up"
    finally:
        remotes.close()


def test_a_no_fails_it_until_it_is_connected_again(host: Host) -> None:
    host.installs(None)
    remotes = Remotes(version="1.2.3", install=None)
    try:
        remotes.connect("box")
        _stands(remotes, "box", "asking")
        # Nothing to one that is not asking, nor to one nobody holds.
        assert remotes.answer("nobody", True)["state"] == "idle"
        assert remotes.answer("box", False)["state"] in ("connecting", "failed")
        said = _stands(remotes, "box", "failed")
        assert said["detail"] == MISSING
        assert remotes.answer("box", True) == said
        probed = len(host.pids())
        time.sleep(QUIET)
        assert len(host.pids()) == probed
        assert remotes.state("box") == said
        assert not host.installed()

        # A no is not remembered.
        assert remotes.connect("box")["state"] in ("failed", "connecting", "asking")
        assert _stands(remotes, "box", "asking")["detail"] == MISSING
    finally:
        remotes.close()


def test_a_yes_is_not_kept_once_the_routes_it_was_said_of_change(host: Host) -> None:
    host.installs(None)
    remotes = Remotes(version="1.2.3", install=None)
    try:
        remotes.connect("box")
        _stands(remotes, "box", "asking")
        remotes.answer("box", True)
        assert _stands(remotes, "box", "up", "failed")["state"] == "up"

        # Removed, and its name written again for another machine, which has none either.
        Daemons().remove("box")
        host.installs(None)
        written({"name": "box", "id": "", "routes": ["stdio:ssh://other@box.example"]})
        remotes.connect("box")
        assert _stands(remotes, "box", "asking", "failed")["state"] == "asking"
        assert len(host.installed().splitlines()) == 1
        remotes.answer("box", False)
        assert _stands(remotes, "box", "failed")["detail"] == MISSING
        assert len(host.installed().splitlines()) == 1
    finally:
        remotes.close()


def test_a_development_build_installs_nothing_unasked(host: Host) -> None:
    host.installs(None)
    remotes = Remotes(version="0.0.0")
    try:
        remotes.connect("box")
        said = _stands(remotes, "box", "failed")
        assert said["detail"] == MISSING
        assert not host.installed()
    finally:
        remotes.close()


def test_a_development_build_installs_the_latest_release(host: Host) -> None:
    host.installs(None)
    remotes = Remotes(version="0.0.0", install=True)
    try:
        remotes.connect("box")
        said = _stands(remotes, "box", "up", "failed")
        assert said["state"] == "up", said
        assert host.installed().split()[-1] == "hmz"
        assert (host.home / ".hmz-version").read_text() == "9.9.9"
    finally:
        remotes.close()


def test_a_development_build_says_why_none_was_installed(host: Host) -> None:
    host.installs(None)
    host.cannot_install("error: No solution found")
    remotes = Remotes(version="0.0.0", install=True)
    try:
        remotes.connect("box")
        said = _stands(remotes, "box", "failed")
        assert said["detail"] == "error: No solution found"
    finally:
        remotes.close()


def test_a_release_there_with_no_daemon_command_is_said_to_be_too_old(
    host: Host,
) -> None:
    host.installs("0.2.2")
    host.predates_daemons()
    remotes = Remotes(version="0.0.0", install=True)
    try:
        remotes.connect("box")
        said = _stands(remotes, "box", "failed")
        assert said["detail"] == (
            "hmz 0.2.2 on box is too old to be reached: it has no daemon command."
        )
        assert not host.installed()
    finally:
        remotes.close()


def test_a_latest_release_with_no_daemon_command_is_removed_again(host: Host) -> None:
    host.installs(None)
    host.predates_daemons()
    remotes = Remotes(version="0.0.0", install=True)
    try:
        remotes.connect("box")
        said = _stands(remotes, "box", "failed")
        assert said["detail"] == (
            "The latest release of hmz is too old to be reached: it has no daemon command."
        )
        assert host.installed().splitlines()[-1] == "tool uninstall hmz"
        assert not (host.home / ".hmz-version").exists()
    finally:
        remotes.close()


def test_a_development_build_uses_another_release_there(host: Host) -> None:
    host.installs("1.0.0")
    remotes = Remotes(version="0.0.0", install=None)
    seen: set[str] = set()
    try:
        remotes.connect("box")
        while (said := remotes.state("box"))["state"] not in ("up", "failed"):
            seen.add(said["state"])
            time.sleep(0.01)
        assert said["state"] == "up", said
        assert "asking" not in seen
        assert not host.installed()
    finally:
        remotes.close()


def test_another_release_there_is_replaced_and_never_asked_about(host: Host) -> None:
    host.installs("1.0.0")
    remotes = Remotes(version="1.2.3", install=None)
    seen: set[str] = set()
    try:
        remotes.connect("box")
        while (said := remotes.state("box"))["state"] not in ("up", "failed"):
            seen.add(said["state"])
            time.sleep(0.01)
        assert said["state"] == "up", said
        assert "asking" not in seen
        assert host.installed().split()[-1] == "hmz==1.2.3"
    finally:
        remotes.close()


def test_closing_ends_a_question(host: Host) -> None:
    host.installs(None)
    remotes = Remotes(version="1.2.3", install=None)
    remotes.connect("box")
    _stands(remotes, "box", "asking")
    began = time.monotonic()
    remotes.close()
    assert time.monotonic() - began < 5
    assert remotes.state("box")["state"] == "idle"
    assert not host.installed()


def test_the_time_a_question_stands_counts_toward_no_timeout(
    host: Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    host.installs(None)
    monkeypatch.setattr("hmz.reach.OPENING", 8.0)
    remotes = Remotes(version="1.2.3", install=None)
    try:
        remotes.connect("box")
        _stands(remotes, "box", "asking")
        time.sleep(9.0)
        assert remotes.state("box")["state"] == "asking"
        remotes.answer("box", True)
        said = _stands(remotes, "box", "up", "failed")
        assert said["state"] == "up", said
    finally:
        remotes.close()


def test_a_daemon_no_longer_written_down_is_let_go(host: Host) -> None:
    remotes = Remotes()
    try:
        remotes.connect("box")
        _stands(remotes, "box", "up")
        pids = host.pids()
        written({"name": "other", "id": "", "routes": ["stdio:ssh://other.example"]})
        with pytest.raises(LookupError):
            remotes.client("box")
        ending = time.monotonic() + PATIENCE
        while not all(_gone(pid) for pid in pids):
            assert time.monotonic() < ending, "what reached it was never stopped"
            time.sleep(0.05)
    finally:
        remotes.close()


@dataclasses.dataclass(frozen=True)
class _Served:
    """`hmz daemon serve` under a home of its own: its environment and the TCP port it took."""

    env: dict[str, str]
    port: int

    def code(self, *routes: str) -> str:
        """A pairing code it makes, over `routes` or its listener's."""
        said = [one for route in routes for one in ("--route", route)]
        return subprocess.run(
            [sys.executable, "-m", "hmz", "devices", "pair", *said],
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()[0]


@pytest.fixture
def served(tmp_path: Path) -> Iterator[_Served]:
    """`hmz daemon serve` under a home of its own, listening on a TCP port of loopback."""
    there = dict(
        os.environ,
        **places(tmp_path / "served"),
        # Short, as a socket's path under it must be.
        TMPDIR=tempfile.mkdtemp(prefix="s", dir=os.environ["TMPDIR"]),
    )
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
        text=True,
    )
    try:
        assert serving.stdout is not None
        said = serving.stdout.readline()
        assert "listening on tcp://" in said
        yield _Served(there, int(said.strip().rsplit(":", 1)[1]))
    finally:
        serving.terminate()
        serving.wait(10)


def test_a_daemon_over_tcp_is_paired_by_its_code_and_reached(served: _Served) -> None:
    code = served.code()
    remotes = Remotes()
    try:
        with pytest.raises(ValueError, match="not a pairing code"):
            remotes.pair("lab", "hmz-pair:nope")
        written_ = remotes.pair("lab", code, device="laptop")
        assert written_["routes"] == [f"tcp://127.0.0.1:{served.port}"]
        assert _daemons() == [written_]
        with pytest.raises(Unreached) as claimed:
            remotes.pair("again", code)
        assert (claimed.value.status, str(claimed.value)) == (
            403,
            "That pairing code is not valid: ask for a new one.",
        )

        client = remotes.client("lab")
        assert remotes.state("lab")["state"] == "up"
        assert (client.daemon_id, client.device) == (written_["id"], "laptop")
        assert client.call("hosts.list") == {"held": []}
    finally:
        remotes.close()


def test_a_daemon_removed_here_is_added_again_from_a_new_code(served: _Served) -> None:
    remotes = Remotes()
    try:
        first = remotes.pair("lab", served.code(), device="laptop")
        Daemons().remove("lab")
        assert _daemons() == []

        again = remotes.pair("lab", served.code(), device="renamed")
        assert again == first
        assert _daemons() == [again]
        client = remotes.client("lab")
        assert client.device == "laptop"
        assert [one["name"] for one in client.call("devices.list")["devices"]] == [
            "laptop"
        ]
    finally:
        remotes.close()


def _slow(
    monkeypatch: pytest.MonkeyPatch,
    opening: float,
    serves: Callable[[socket.socket], None],
) -> tuple[str, float, str]:
    """How reaching a daemon over TCP fails, each carrier accepted being given to `serves`.

    Returns:
      The route, how many seconds after it was started it was given up on, and what was said.
    """
    monkeypatch.setattr("hmz.reach.OPENING", opening)
    listening = socket.create_server(("127.0.0.1", 0))
    held: list[socket.socket] = []

    def accepts() -> None:
        with contextlib.suppress(OSError):
            while True:
                held.append(listening.accept()[0])
                serves(held[-1])

    threading.Thread(target=accepts, daemon=True).start()
    route = f"tcp://127.0.0.1:{listening.getsockname()[1]}"
    written({"name": "slow", "id": identity.device().fingerprint, "routes": [route]})
    remotes = Remotes()
    try:
        started = time.monotonic()
        remotes.connect("slow")
        said = _stands(remotes, "slow", "failed")
        return route, time.monotonic() - started, said["detail"]
    finally:
        remotes.close()
        listening.close()
        for one in held:
            one.close()


def test_a_daemon_that_never_speaks_tls_did_not_open_in_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route, _, detail = _slow(monkeypatch, 1.0, lambda _: None)
    assert detail == f"{route} did not open within 1 seconds."


def test_tls_and_hello_share_the_time_a_route_has_to_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def serves(carrier: socket.socket) -> None:
        # Secured only once most of the time is gone, and hello never answered.
        time.sleep(3.0)
        tls.answer(SocketPipe(carrier, trusted=False), identity.device())

    route, took, detail = _slow(monkeypatch, 4.0, serves)
    assert detail == f"{route} did not open within 4 seconds."
    assert took < 6.0


#: The secret the EasyTier network is joined with, and the node it is written down with; the
#: stand-in reaches no node.
_SECRET, _NODES = "correct horse battery staple", ["tcp://127.0.0.1:11010"]


@pytest.fixture
def network(
    served: _Served, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[doubles_easytier.Core]:
    """The stand-in EasyTier network `far`, whose serving end lets through the daemon's port.

    The serving end is started here rather than by that daemon, at the port its TCP listener
    took: a daemon listening on `easytier:far` itself takes EasyTier's one fixed port, which
    another test may hold.
    """
    core = doubles_easytier.faked(tmp_path, monkeypatch)
    monkeypatch.setattr(easytier, "PORT", served.port)
    settings.changes(
        lambda held: held.__setitem__(
            "easytier", {"far": {"secret": _SECRET, "nodes": _NODES}}
        )
    )
    serving = easytier.serving(_SECRET, served.port, peers=_NODES)
    try:
        # Joined once it has written its network down, as a real one has once it says so.
        ending = time.monotonic() + PATIENCE
        while not any(core.networks.iterdir()):
            assert time.monotonic() < ending, "the network was never joined"
            time.sleep(0.05)
        yield core
    finally:
        serving.terminate()
        serving.wait(10)


def _runs(core: doubles_easytier.Core, *, of: str) -> list[int]:
    """Every run of the stand-in so far told `of`, by pid."""
    runs = [json.loads(line) for line in core.log.read_text().splitlines()]
    return [run["pid"] for run in runs if of in run["argv"]]


def test_a_daemon_over_easytier_is_paired_reached_again_and_its_easytier_reaped(
    served: _Served, network: doubles_easytier.Core
) -> None:
    remotes = Remotes()
    try:
        paired = remotes.pair("far", served.code("easytier:far"))
        assert paired["routes"] == ["easytier:far"]
        assert remotes.client("far").call("hosts.list") == {"held": []}
        # Its end of the network stopped, as this machine's network going would stop it.
        os.kill(_runs(network, of="--port-forward")[-1], signal.SIGTERM)
        _stands(remotes, "far", "connecting", "failed")
        assert _stands(remotes, "far", "up")["version"] == version("hmz")
    finally:
        remotes.close()
    joined = _runs(network, of="--port-forward")
    assert len(joined) >= 3
    assert all(_gone(pid) for pid in joined)
    assert remotes.state("far")["state"] == "idle"
    assert all(_SECRET not in " ".join(argv) for argv, _ in network.told())


def test_a_connect_over_stdio_that_is_interrupted_exits_without_a_traceback(
    served: _Served,
) -> None:
    connected = subprocess.Popen(
        [sys.executable, "-m", "hmz", "daemon", "connect", "--stdio"],
        env=served.env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert connected.stdout is not None
        assert connected.stdout.readline() == b"hmz-stdio/1\n"
        # As the desktop app stops the process of every pipe it closes.
        connected.send_signal(signal.SIGINT)
        _, said = connected.communicate(timeout=PATIENCE)
    finally:
        connected.kill()
        connected.wait(10)
    assert (connected.returncode, said) == (128 + signal.SIGINT, b"")

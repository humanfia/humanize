"""`hmz server`: a server started apart from the line and stopped, with every process a stand-in.

EasyTier, the web, the daemon's liveness check and the record's writing are mocked; so is the
process `start` starts, which says it is up down the descriptor it is handed.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, ClassVar
from unittest import mock

import pytest

import hmz.web
from hmz import home
from hmz.cli import main
from hmz.cli.server import RECORD, serves
from hmz.coganchor import atomic, easytier
from hmz.daemon import where

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator
    from pathlib import Path

SECRET = "0123456789abcdef"
PEER = "tcp://node.example:11010"
START = ["server", "start", "--mode", "p2p", "--secret", SECRET, "--peer", PEER]


def _checked(secret: str) -> str:
    if len(secret.encode()) < 16:
        msg = "A secret must be at least 16 bytes."
        raise ValueError(msg)
    return secret


def _key(secret: str) -> str:
    return f"key-of-{secret}"


def _nothing(*_: object) -> None:
    return None


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """EasyTier, the record's writing and which processes are alive, mocked."""
    held = SimpleNamespace(alive=set[int](), written={}, binary=mock.Mock())

    def writes(at: Path, said: str, *, mode: int | None = None) -> None:
        held.written[at] = mode
        at.write_text(said)

    def alive(pid: int) -> bool:
        return pid in held.alive

    monkeypatch.setattr(easytier, "checked", _checked)
    monkeypatch.setattr(easytier, "key", _key)
    monkeypatch.setattr(easytier, "binary", held.binary)
    monkeypatch.setattr(atomic, "writes", writes)
    monkeypatch.setattr(where, "alive", alive)
    return held


class _Child:
    """The server `start` starts: it says `said` down its descriptor, and is still running."""

    said = "up\n"
    status: int | None = None
    started: ClassVar[list[_Child]] = []

    def __init__(self, argv: list[str], **how: Any) -> None:
        self.argv = argv
        self.how = how
        self.pid = 4242
        self.stdin = io.BytesIO()
        self.stdin.close = lambda: None  # read after `start` has let go of it
        self.returncode: int | None = None
        self.terminated = False
        if self.said:
            os.write(how["pass_fds"][0], self.said.encode())
        _Child.started.append(self)

    def poll(self) -> int | None:
        self.returncode = self.status
        return self.status

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        return 0


@pytest.fixture
def child(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[_Child]]:
    _Child.started = []
    monkeypatch.setattr(subprocess, "Popen", _Child)
    yield _Child
    _Child.said, _Child.status = "up\n", None


def _record() -> Path:
    return home() / RECORD


def _recorded(pid: int) -> None:
    home().mkdir(parents=True, exist_ok=True)
    _record().write_text(json.dumps({"pid": pid}))


def test_start_starts_the_server_apart_and_records_it(
    world: SimpleNamespace, child: type[_Child], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(START) == 0

    (started,) = child.started
    assert started.argv[:3] == [sys.executable, "-Pm", "hmz.cli.server"]
    assert started.argv[4:] == [PEER]
    assert SECRET not in " ".join(started.argv)
    assert started.how["start_new_session"] is True
    assert started.stdin.getvalue() == SECRET.encode()
    world.binary.assert_called_once()
    said = json.loads(_record().read_text())
    assert said["pid"] == 4242
    assert said["mode"] == "p2p"
    assert said["port"] == easytier.PORT
    assert isinstance(said["version"], str)
    assert world.written[_record()] == 0o600
    assert capsys.readouterr().out == "hmz server: started (pid 4242)\n"


def test_start_says_a_download_where_one_happens(
    world: SimpleNamespace, child: type[_Child], capsys: pytest.CaptureFixture[str]
) -> None:
    def binary(say: Callable[[str], object]) -> None:
        say("Downloading EasyTier 9.9.9")

    world.binary.side_effect = binary
    del child
    assert main(START) == 0
    assert capsys.readouterr().err == "hmz: Downloading EasyTier 9.9.9\n"


def test_start_with_a_server_running_is_refused(
    world: SimpleNamespace, child: type[_Child], capsys: pytest.CaptureFixture[str]
) -> None:
    _recorded(77)
    world.alive.add(77)
    assert main(START) == 1
    assert capsys.readouterr().err == "hmz: a server is already running (pid 77)\n"
    assert not child.started


def test_start_over_a_record_whose_server_is_gone_starts_one(
    world: SimpleNamespace, child: type[_Child]
) -> None:
    del world
    _recorded(77)
    assert main(START) == 0
    assert json.loads(_record().read_text())["pid"] == 4242
    assert child.started


@pytest.mark.parametrize(
    ("said", "status", "why"),
    [
        ("Address already in use\n", None, "Address already in use"),
        ("", 3, "it exited as it started, with status 3"),
    ],
)
@pytest.mark.usefixtures("world")
def test_a_server_that_does_not_come_up_is_said_why(
    child: type[_Child],
    capsys: pytest.CaptureFixture[str],
    said: str,
    status: int | None,
    why: str,
) -> None:
    child.said, child.status = said, status
    assert main(START) == 1
    assert capsys.readouterr().err == f"hmz: the server cannot be started: {why}\n"
    assert not _record().exists()


def test_easytier_that_cannot_be_had_is_said(
    world: SimpleNamespace, child: type[_Child], capsys: pytest.CaptureFixture[str]
) -> None:
    world.binary.side_effect = OSError("no release for this machine")
    assert main(START) == 1
    assert "hmz: the server cannot be started: no release" in capsys.readouterr().err
    assert not child.started


@pytest.mark.usefixtures("world")
@pytest.mark.parametrize(
    ("argv", "said"),
    [
        (["start", "--mode", "p2p", "--secret", "short", "--peer", PEER], "16 bytes"),
        (["start", "--mode", "p2p", "--secret", SECRET], "--peer"),
        (["start", "--mode", "stun", "--secret", SECRET, "--peer", PEER], "--mode"),
        (["start", "--mode", "p2p", "--peer", PEER], "--secret"),
        (["start", "--mode", "p2p", "--secret", SECRET, "--peer", "node:1"], "node"),
        (
            ["start", "--mode", "p2p", "--secret", SECRET, "--peer", "tcp://node"],
            "EasyTier node",
        ),
        (["stop", "--now"], "--now"),
        (["restart"], "restart"),
        ([], "start,stop"),
    ],
)
def test_a_line_short_of_what_it_needs_is_a_usage_error(
    argv: list[str], said: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["server", *argv])
    assert raised.value.code == 2
    assert said in capsys.readouterr().err


def test_stop_terminates_the_server_and_removes_its_record(
    world: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _recorded(77)
    world.alive.add(77)
    killed: list[tuple[int, int]] = []

    def kill(pid: int, signum: int) -> None:
        killed.append((pid, signum))
        world.alive.discard(pid)

    monkeypatch.setattr(os, "kill", kill)
    assert main(["server", "stop"]) == 0
    assert killed == [(77, signal.SIGTERM)]
    assert not _record().exists()
    assert capsys.readouterr().out == "hmz server: stopped\n"


def test_stop_waits_only_so_long(
    world: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _recorded(77)
    world.alive.add(77)
    clock = [0.0]

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    monkeypatch.setattr(os, "kill", _nothing)
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", sleep)
    assert main(["server", "stop"]) == 1
    assert "the server did not stop" in capsys.readouterr().err
    assert _record().exists()


@pytest.mark.usefixtures("world")
def test_stop_with_no_server_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    _recorded(77)
    assert main(["server", "stop"]) == 1
    assert capsys.readouterr().err == "hmz: no server is running\n"
    assert not _record().exists()


#: What `_Core.poll` says to have the server terminated, as `hmz server stop` would.
TERMINATED = -15


class _Core:
    """`easytier-core`, saying each of `said` in turn as it is polled, and the last for ever."""

    def __init__(self, *said: int | None) -> None:
        self.said = list(said)
        self.stopped = False

    def poll(self) -> int | None:
        one = self.said.pop(0) if len(self.said) > 1 else self.said[0]
        if one == TERMINATED:
            signal.raise_signal(signal.SIGTERM)
            return None
        return one

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        return 0

    def terminate(self) -> None:
        self.stopped = True


@pytest.fixture
def serving(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SimpleNamespace]:
    """The server's web and EasyTier, mocked, and its secret on standard input."""
    del world
    held = SimpleNamespace(
        cores=[], told=[], site=mock.Mock(), listened={}, refused=None
    )

    @contextlib.contextmanager
    def listening(**how: Any) -> Generator[Any]:
        if held.refused is not None:
            raise held.refused
        held.listened.update(how)
        yield held.site

    def started(secret: str, **how: Any) -> _Core:
        held.told.append((secret, how))
        return held.cores[len(held.told) - 1]

    monkeypatch.setattr(hmz.web, "listening", listening)
    monkeypatch.setattr(easytier, "serving", started)
    monkeypatch.setattr(
        sys, "stdin", SimpleNamespace(buffer=io.BytesIO(SECRET.encode()))
    )
    reading, telling = os.pipe()
    held.telling = telling
    with os.fdopen(reading, "rb") as read:
        held.read = read
        yield held


def test_the_server_keeps_easytier_going_until_terminated(
    serving: SimpleNamespace,
) -> None:
    was = signal.getsignal(signal.SIGTERM)
    first, last = _Core(None, 1), _Core(TERMINATED)
    serving.cores += [first, last]

    assert serves([str(serving.telling), PEER]) == 0

    assert serving.read.read() == b"up\n"
    assert serving.listened == {
        "port": easytier.PORT,
        "apart": True,
        "key": f"key-of-{SECRET}",
    }
    assert serving.told == [(SECRET, {"peers": [PEER]})] * 2
    assert last.stopped
    assert not first.stopped
    serving.site.serve_forever.assert_called_once()
    serving.site.shutdown.assert_called_once_with()
    assert signal.getsignal(signal.SIGTERM) == was


def test_easytier_gone_as_it_starts_is_said(serving: SimpleNamespace) -> None:
    serving.cores.append(_Core(1))
    assert serves([str(serving.telling), PEER]) == 1
    assert serving.read.read() == b"easytier-core exited as it started, with status 1\n"
    serving.site.shutdown.assert_called_once_with()


def test_a_web_that_cannot_listen_is_said(serving: SimpleNamespace) -> None:
    serving.refused = OSError("Address already in use")
    assert serves([str(serving.telling), PEER]) == 1
    assert serving.read.read() == b"Address already in use\n"
    assert not serving.told

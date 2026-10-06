"""What the machine's daemon says to whatever reaches its socket, and how it comes back.

Bare sockets saying exactly what each test makes them, a daemon of an older humanize stood in
by a socket of the test's own, and daemons and hosts that went away under their frontends.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz import daemon
from hmz.daemon import where
from hmz.daemon.link import reached
from hmz.daemon.proto import CONTROL, GONE, MESSAGE, PROTOCOL, Frames, frame, spoken
from tests.integration.doubles_daemon import hosting, project, standing, until

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = [
    pytest.mark.timeout(90),
    pytest.mark.filterwarnings("ignore:.*use of fork.*:DeprecationWarning"),
]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = project(tmp_path, monkeypatch)
    with hosting():
        yield at


@pytest.fixture
def held(workspace: Path) -> daemon.Daemon:
    return daemon.host()


def _bare() -> socket.socket:
    one = where.connects(where.at())
    one.settimeout(10)
    return one


def _read(one: socket.socket) -> list[tuple[bytes, bytes]]:
    """Every frame the daemon sent, until it closed the socket.

    Linux says a socket closed with what this end sent still unread as a reset rather than an
    end, once what was sent this way has been read.
    """
    frames, read = Frames(), list[tuple[bytes, bytes]]()
    with contextlib.suppress(ConnectionResetError):
        while chunk := one.recv(1 << 16):
            read.extend(frames.feed(chunk))
    return read


def _answer(said: dict[str, Any], kind: bytes = CONTROL) -> dict[str, Any]:
    with _bare() as one:
        one.sendall(spoken(kind, said))
        frames = Frames()
        while chunk := one.recv(1 << 16):
            for _, payload in frames.feed(chunk):
                return json.loads(payload)
    raise AssertionError("the daemon closed without answering")


def test_the_daemon_lists_the_workspaces_it_holds(
    held: daemon.Daemon, workspace: Path
) -> None:
    said = _answer({"do": "list"})

    assert said["ok"]
    assert [(one["workspace"], one["pid"]) for one in said["held"]] == [
        (where.workspace(workspace), held.pid)
    ]
    assert where.held(where.at())["protocol"] == PROTOCOL


def test_a_question_the_daemon_does_not_know_is_refused(held: daemon.Daemon) -> None:
    del held
    assert _answer({"do": "nope"}) == {"ok": False, "why": "no such request: 'nope'"}


def test_a_question_about_a_workspace_is_answered_by_its_host(
    held: daemon.Daemon,
) -> None:
    said = held.asked({"do": "status"})

    assert said["ok"]
    assert (said["pid"], said["state"]) == (held.pid, "idle")


@pytest.mark.parametrize("kind", [CONTROL, MESSAGE])
def test_a_workspace_no_host_holds_is_said_to_be_held_by_nobody(
    held: daemon.Daemon, tmp_path: Path, kind: bytes
) -> None:
    del held
    nowhere = str(tmp_path / "nowhere")
    said = _answer({"do": "hello", "workspace": nowhere, "id": "r1"}, kind)

    assert not said["ok"]
    assert said["why"] == f"no runs are held in {nowhere}"
    with pytest.raises(OSError, match="no runs are held"):
        reached(where.at(), nowhere)


def test_a_reader_of_another_protocol_is_told_so_rather_than_left_waiting(
    held: daemon.Daemon,
) -> None:
    del held
    with _bare() as one:
        one.sendall(frame(b"H", b"{}"))
        ((kind, payload),) = _read(one)

    assert kind == GONE
    assert b"newer humanize" in payload


def test_a_length_no_frame_has_is_closed_on_and_nobody_else_notices(
    held: daemon.Daemon,
) -> None:
    with _bare() as one:
        one.sendall(b"M\xff\xff\xff\xff")
        assert _read(one) == []

    assert held.status()["state"] == "idle"


def test_a_hello_arriving_in_pieces_is_still_handed_to_its_host(
    held: daemon.Daemon,
) -> None:
    hello = frame(
        MESSAGE,
        json.dumps(
            {
                "do": "hello",
                "id": "r1",
                "workspace": held.workspace,
                "name": "slow",
                "kind": "sdk",
                "replay": False,
            }
        ).encode(),
    )
    with _bare() as one:
        one.sendall(hello[:7])
        time.sleep(0.1)
        one.sendall(hello[7:])
        frames, replied = Frames(), None
        while replied is None:
            chunk = one.recv(1 << 16)
            assert chunk, "the daemon closed without replying"
            for _, payload in frames.feed(chunk):
                said = json.loads(payload)
                if said.get("type") == "reply":
                    replied = said
        assert replied["ok"]
        assert replied["to"] == "r1"
        assert [one["name"] for one in held.status()["clients"]] == ["slow"]


def test_runs_held_by_an_older_humanize_are_left_alone(workspace: Path) -> None:
    del workspace
    with standing(where.at(), {}):
        found = daemon.running()
        assert found is not None
        assert found.protocol == 0
        assert [(one.pid, one.protocol) for one in daemon.daemons()] == [(found.pid, 0)]
        with pytest.raises(OSError, match="older humanize"):
            daemon.host()
        with pytest.raises(OSError, match="host"):
            found.link()


def _dead_pid() -> int:
    gone = subprocess.Popen([sys.executable, "-c", ""])
    gone.wait()
    return gone.pid


def test_a_socket_a_dead_daemon_left_behind_is_taken_over(workspace: Path) -> None:
    del workspace
    at = where.at()
    left = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    with where.reached(at) as reaching:
        left.bind(reaching)
    left.close()
    dead = _dead_pid()
    where.wrote(at, {"pid": dead, "started": where.now(), "protocol": PROTOCOL})

    assert daemon.running() is None
    assert daemon.daemons() == []
    found = daemon.host()

    assert found.alive
    assert where.held(at)["pid"] not in (dead, os.getpid())
    assert daemon.running() == found


def test_a_host_that_went_is_started_again(held: daemon.Daemon) -> None:
    assert held.kill()

    again = daemon.host()

    assert again.alive
    assert again.pid != held.pid
    assert daemon.running() == again


def test_the_daemon_going_closes_the_runs_it_was_the_way_to(
    held: daemon.Daemon,
) -> None:
    machine = where.held(where.at())["pid"]
    gone: list[str] = []
    link = held.link(name="watching")
    link.heard(
        lambda said: gone.append(said["why"]) if said["type"] == "gone" else None
    )
    try:
        os.kill(machine, 9)

        assert until(lambda: not held.alive)
        assert until(lambda: gone)
        assert daemon.running() is None
        again = daemon.host()
        assert again.pid != held.pid
        assert where.held(where.at())["pid"] != machine
    finally:
        link.close()

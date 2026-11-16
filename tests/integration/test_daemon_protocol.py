"""What the machine's daemon says to whatever reaches its socket, and how it comes back.

Bare sockets saying exactly what each test makes them, a daemon of an older Humanize stood in
by a socket of the test's own, and daemons and hosts that went away under their frontends.
"""

from __future__ import annotations

import json
import os
import socket
import struct
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz import daemon
from hmz.daemon import where
from hmz.daemon.link import reached
from hmz.rpc import PROTOCOL, Frames, encode
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


def _said(one: socket.socket, *calls: dict[str, Any]) -> list[dict[str, Any]]:
    """Says each call, in frames of its own, and reads an answer to each."""
    frames, answers = Frames(), list[dict[str, Any]]()
    for call in calls:
        one.sendall(encode({"jsonrpc": "2.0", **call}))
    while len(answers) < len(calls):
        chunk = one.recv(1 << 16)
        assert chunk, "the daemon closed without answering"
        answers.extend(json.loads(payload) for payload in frames.feed(chunk))
    return sorted(answers, key=lambda one: one["id"])


_HELLO = {
    "id": 0,
    "method": "session.hello",
    "params": {"protocol": PROTOCOL, "client": {"name": "", "kind": "cli"}},
}


def test_the_daemon_lists_the_workspaces_it_holds(
    held: daemon.Daemon, workspace: Path
) -> None:
    with _bare() as one:
        _, said = _said(one, _HELLO, {"id": 1, "method": "hosts.list"})

    assert [(one["workspace"], one["pid"]) for one in said["result"]["held"]] == [
        (where.workspace(workspace), held.pid)
    ]
    assert where.held(where.at())["protocol"] == PROTOCOL


def test_a_question_about_a_workspace_is_answered_by_its_host(
    held: daemon.Daemon,
) -> None:
    said = held.asked({"do": "status"})

    assert (said["pid"], said["state"]) == (held.pid, "idle")


def test_a_workspace_no_host_holds_is_said_to_be_held_by_nobody(
    held: daemon.Daemon, tmp_path: Path
) -> None:
    del held
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    with _bare() as one:
        _, said = _said(
            one,
            _HELLO,
            {"id": 1, "method": "hosts.status", "params": {"workspace": str(nowhere)}},
        )

    assert said["error"] == {
        "code": 404,
        "message": f"no runs are held in {where.workspace(nowhere)}",
    }


def test_a_chat_whose_host_has_gone_is_not_held_again(workspace: Path) -> None:
    chat = daemon.host(workspace, slot="chat:0a")
    assert chat.kill()
    assert until(lambda: daemon.running(workspace, slot="chat:0a") is None)

    with pytest.raises(OSError, match=r"This chat has folded away\."):
        reached(where.at(), chat.workspace, slot="chat:0a")


def test_a_length_no_frame_has_is_closed_on_and_nobody_else_notices(
    held: daemon.Daemon,
) -> None:
    with _bare() as one:
        one.sendall(struct.pack(">I", 0xFFFFFFFF))
        assert one.recv(1 << 16) == b""

    assert held.status()["state"] == "idle"


def test_a_hello_arriving_in_pieces_is_still_answered(held: daemon.Daemon) -> None:
    del held
    frame = encode({"jsonrpc": "2.0", **_HELLO})
    with _bare() as one:
        one.sendall(frame[:7])
        time.sleep(0.1)
        one.sendall(frame[7:])
        (said,) = (
            _said(one) if False else _said(one, {"id": 1, "method": "rpc.discover"})
        )

    assert said["result"]["info"]["version"] == PROTOCOL


def test_runs_held_by_an_older_humanize_are_left_alone(workspace: Path) -> None:
    del workspace
    with standing(where.at(), {}):
        found = daemon.running()
        assert found is not None
        assert found.protocol == ""
        assert [(one.pid, one.protocol) for one in daemon.daemons()] == [
            (found.pid, "")
        ]
        with pytest.raises(OSError, match="older Humanize"):
            daemon.host()
        with pytest.raises(OSError, match="did not say hello"):
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

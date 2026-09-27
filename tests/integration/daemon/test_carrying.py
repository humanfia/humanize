"""A workspace's runs carried to every frontend reaching them over the socket, in this process.

`tests/integration/daemon/test_hosted.py` holds the runs the way they really are -- a double
fork, and frontends that are processes of their own. Which is the right way to check that a
host outlives whoever started it and the wrong way to check what carrying does with each
thing that can arrive, so this drives the carrying loop directly: a host in this process, the
socket bound here, and frontends that are links -- or bare sockets, for the ones that
misbehave.

The socket is bound by a bare name from inside its own directory: a Unix socket address holds
about a hundred bytes whole, and the directory pytest hands out is longer than that.
"""

from __future__ import annotations

import contextlib
import os
import socket
import struct
import threading
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz.daemon import Daemon, carrying, where
from hmz.daemon.carrying import Carrier
from hmz.daemon.link import Link, reached
from hmz.daemon.proto import GONE, HELLO, MESSAGE, Frames, asked, spoken
from hmz.runtime import Hmz, Host

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

#: How long a test waits for something another thread is doing.
PATIENCE = 20.0


def until(what: Callable[[], object], seconds: float = PATIENCE) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if what():
            return True
        time.sleep(0.01)
    return bool(what())


class Reading:
    """One link, and everything it has been told."""

    def __init__(self, link: Link) -> None:
        self.link = link
        self.seen: list[dict[str, Any]] = []
        link.heard(self.seen.append)

    def printed(self) -> list[str]:
        return [one["text"] for one in list(self.seen) if one["type"] == "printed"]

    def seqs(self) -> list[int]:
        return [one["seq"] for one in list(self.seen) if one["type"] == "printed"]

    def gone(self) -> str | None:
        said = [one for one in list(self.seen) if one["type"] == "gone"]
        return said[-1]["why"] if said else None


class Carried:
    """A host being carried here, with the socket it is reached through."""

    def __init__(self, host: Host, carrier: Carrier, at: Path) -> None:
        self.host = host
        self.carrier = carrier
        self.at = at
        self._opened: list[Link] = []

    def link(self, name: str) -> Reading:
        one = reached(self.at, name)
        self._opened.append(one)
        return Reading(one)

    def raw(self) -> socket.socket:
        """A bare socket onto the host, which says and reads only what the test makes it."""
        one = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        one.connect(where.SOCKET)
        return one

    def close(self) -> None:
        for one in self._opened:
            one.close()


@pytest.fixture
def carried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Carried]:
    monkeypatch.chdir(tmp_path)
    listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listening.bind(where.SOCKET)
    listening.listen(8)
    where.wrote(
        tmp_path,
        {"pid": os.getpid(), "workspace": str(tmp_path), "kind": "host", "protocol": 1},
    )
    host = Hmz().host()
    carrier = Carrier(host, listening, tmp_path)
    carrier.start()
    one = Carried(host, carrier, tmp_path)
    try:
        yield one
    finally:
        one.close()
        host.close()
        carrier.close()


def _hello(one: socket.socket, name: str) -> None:
    one.sendall(spoken(MESSAGE, {"id": "r1", "do": "hello", "name": name}))


def _read_all(one: socket.socket) -> list[tuple[bytes, dict[str, Any]]]:
    """Everything a socket was sent, until the host closes it."""
    frames = Frames()
    said: list[tuple[bytes, dict[str, Any]]] = []
    one.settimeout(PATIENCE)
    with contextlib.suppress(OSError):
        while read := one.recv(1 << 16):
            said.extend((kind, asked(payload)) for kind, payload in frames.feed(read))
    return said


# --------------------------------------------------------------------- in order


@pytest.mark.timeout(60)
def test_every_frontend_is_told_the_same_things_in_the_same_order(
    carried: Carried,
) -> None:
    readings = [carried.link(name) for name in ("alice", "bob", "carol")]

    def prints(who: str) -> None:
        for count in range(50):
            carried.host.printed(f"{who} {count}")

    saying = [threading.Thread(target=prints, args=(who,)) for who in "xyz"]
    for one in saying:
        one.start()
    for one in saying:
        one.join()

    assert until(lambda: all(len(one.printed()) == 150 for one in readings))
    first = readings[0].seqs()
    assert first == sorted(first)
    assert all(one.seqs() == first for one in readings)
    assert all(one.printed() == readings[0].printed() for one in readings)


@pytest.mark.timeout(60)
def test_a_frontend_that_reads_nothing_is_let_go_without_holding_up_the_rest(
    carried: Carried, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(carrying, "_BEHIND", 1 << 16)
    alice = carried.link("alice")
    stuck = carried.raw()
    stuck.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    _hello(stuck, "stuck")
    assert until(lambda: carried.host.attached == 2)

    for count in range(2000):
        carried.host.printed(f"line {count} " + "x" * 1000)
        if count % 20 == 19:
            # Taken as it is said, so that only the one that takes nothing falls behind.
            assert until(lambda at=count: len(alice.printed()) == at + 1)

    assert until(lambda: len(alice.printed()) == 2000)
    assert until(lambda: carried.host.attached == 1)
    said = _read_all(stuck)
    assert said[-1] == (
        MESSAGE,
        {"type": "gone", "why": "too far behind; attach again"},
    )
    # Whole frames to the last: the one it was in the middle of, and then why it went.
    assert all(kind == MESSAGE and one for kind, one in said)


@pytest.mark.timeout(60)
def test_a_listener_that_blocks_holds_up_only_its_own_frontend(
    carried: Carried,
) -> None:
    stuck = threading.Event()
    blocked = reached(carried.at, "stuck")

    def blocks(_said: dict[str, Any]) -> None:
        stuck.wait(PATIENCE)

    blocked.heard(blocks)
    alice = carried.link("alice")

    for count in range(200):
        carried.host.printed(f"line {count}")

    assert until(lambda: len(alice.printed()) == 200)
    assert carried.host.attached == 2
    stuck.set()
    blocked.close()


# --------------------------------------------------------------- what arrives


@pytest.mark.timeout(60)
def test_a_length_no_frame_has_is_refused_and_nobody_else_notices(
    carried: Carried,
) -> None:
    alice = carried.link("alice")
    wrong = carried.raw()

    wrong.sendall(MESSAGE + struct.pack(">I", 0xFFFFFFFF))

    assert _read_all(wrong) == []
    carried.host.printed("still here")
    assert until(lambda: alice.printed() == ["still here"])


@pytest.mark.timeout(60)
def test_a_frontend_says_hello_before_it_asks_anything(carried: Carried) -> None:
    one = carried.raw()
    one.sendall(spoken(MESSAGE, {"id": "r1", "do": "status"}))
    frames = Frames()
    one.settimeout(PATIENCE)

    ((kind, payload),) = frames.feed(one.recv(1 << 16))

    assert kind == MESSAGE
    assert asked(payload) == {
        "type": "reply",
        "to": "r1",
        "ok": False,
        "why": "a frontend says hello first",
    }


@pytest.mark.timeout(60)
def test_a_terminal_reaching_for_runs_held_for_frontends_is_told_so(
    carried: Carried,
) -> None:
    one = carried.raw()

    one.sendall(spoken(HELLO, {"columns": 80, "rows": 24}))
    one.settimeout(PATIENCE)

    assert Frames().feed(one.recv(1 << 16)) == [
        (GONE, b"held for frontends; `hmz attach` reads it")
    ]


@pytest.mark.timeout(60)
def test_a_request_that_takes_its_time_holds_up_no_other(carried: Carried) -> None:
    """An aside is a turn of an agent: the frontend's other requests go on without it."""
    released = threading.Event()
    carried.host._requests["aside"] = lambda _frontend, _said: (
        released.wait(PATIENCE),
        {"ok": True, "answer": "late"},
    )[1]
    alice, bob = carried.link("alice"), carried.link("bob")
    answered: list[dict[str, Any]] = []
    asking = threading.Thread(
        target=lambda: answered.append(alice.link.aside(side="s1", prompt="?"))
    )
    asking.start()

    assert alice.link.claim("planner")["ok"]
    assert bob.link.asked({"do": "status"})["attached"] == 2
    assert not answered
    released.set()
    asking.join(PATIENCE)
    assert answered == [{"ok": True, "answer": "late"}]


# ------------------------------------------------------------------- control


@pytest.mark.timeout(60)
def test_a_question_about_the_runs_is_answered_as_the_daemon_is_asked_it(
    carried: Carried,
) -> None:
    held = Daemon(at=carried.at, workspace="", pid=os.getpid(), started="", protocol=1)
    alice, bob = carried.link("alice"), carried.link("bob")

    status = held.status()

    assert status["ok"]
    assert (status["kind"], status["protocol"], status["attached"]) == ("host", 1, 2)
    assert [one["name"] for one in status["clients"]] == ["alice", "bob"]
    assert (status["state"], status["flows"], status["calls"]) == ("idle", [], [])

    assert held.detach() == 2
    assert until(lambda: alice.gone() == "let go" and bob.gone() == "let go")


@pytest.mark.timeout(60)
def test_stopping_closes_the_host_and_every_frontend_is_told_why(
    carried: Carried,
) -> None:
    held = Daemon(at=carried.at, workspace="", pid=os.getpid(), started="", protocol=1)
    alice = carried.link("alice")

    assert held.asked({"do": "stop"}) == {"ok": True}

    assert until(lambda: alice.gone() == "the host was closed")
    assert carried.carrier.wait(PATIENCE)
    assert carried.host.closed


@pytest.mark.timeout(60)
def test_a_host_everybody_has_left_lets_go(carried: Carried) -> None:
    """Nothing running, nothing stopping, nobody reading: nothing left to hold."""
    alice = carried.link("alice")

    alice.link.close()

    assert carried.carrier.wait(PATIENCE)
    assert carried.host.closed

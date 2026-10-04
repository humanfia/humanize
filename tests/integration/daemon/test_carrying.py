"""A workspace's runs carried to every frontend reaching them over the socket, in this process.

`tests/integration/daemon/test_hosted.py` holds the runs the way they really are -- a double
fork, and frontends that are processes of their own. Which is the right way to check that a
host outlives whoever started it and the wrong way to check what carrying does with each
thing that can arrive, so this drives the carrying loop directly: a host in this process,
this machine's daemon routing to it from a thread of this process too, and frontends that are
links -- or bare sockets, for the ones that misbehave.
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

from hmz.daemon import Daemon, carrying, routing, where
from hmz.daemon.carrying import Carrier
from hmz.daemon.link import Link, reached
from hmz.daemon.proto import (
    CONTROL,
    GONE,
    MESSAGE,
    PROTOCOL,
    Frames,
    asked,
    frame,
    spoken,
)
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
    """A host being carried here, with the daemon it is reached through."""

    def __init__(
        self, host: Host, carrier: Carrier, router: routing.Router, workspace: str
    ) -> None:
        self.host = host
        self.carrier = carrier
        self.router = router
        self.at = where.at()
        self.workspace = workspace
        self._opened: list[Link] = []

    def link(self, name: str) -> Reading:
        one = reached(self.at, self.workspace, name)
        self._opened.append(one)
        return Reading(one)

    def raw(self) -> socket.socket:
        """A bare socket onto the daemon, which says and reads only what the test makes it."""
        return where.connects(self.at)

    def daemon(self) -> Daemon:
        """The host, as a frontend finds it."""
        return Daemon(
            at=self.at,
            workspace=self.workspace,
            pid=os.getpid(),
            started="",
            protocol=PROTOCOL,
        )

    def close(self) -> None:
        for one in self._opened:
            one.close()


@pytest.fixture
def carried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Carried]:
    monkeypatch.chdir(tmp_path)
    at = where.at()
    router = routing.Router(routing._listens(at), at)
    router.start()
    workspace = where.workspace()
    host = Hmz().host()
    # Said to the daemon as a host process says it, on the connection it is handed sockets
    # down.
    handing = where.connects(at)
    said = {
        "pid": os.getpid(),
        "workspace": workspace,
        "kind": "host",
        "protocol": PROTOCOL,
    }
    handing.sendall(spoken(CONTROL, {"do": "serve", **said}))
    assert handing.recv(1) == carrying.TAKEN
    carrier = Carrier(host, handing, said)
    carrier.start()
    one = Carried(host, carrier, router, workspace)
    try:
        yield one
    finally:
        one.close()
        host.close()
        carrier.close()
        router.close()


def _hello(one: socket.socket, name: str, workspace: str) -> None:
    one.sendall(
        spoken(
            MESSAGE, {"id": "r1", "do": "hello", "name": name, "workspace": workspace}
        )
    )


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
    _hello(stuck, "stuck", carried.workspace)
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
    blocked = reached(carried.at, carried.workspace, "stuck")

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
    one.sendall(
        spoken(MESSAGE, {"id": "r1", "do": "status", "workspace": carried.workspace})
    )
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
def test_a_reader_of_another_protocol_is_told_so_rather_than_left_waiting(
    carried: Carried,
) -> None:
    """An older humanize's terminal says hello with a frame of its own, which is no request."""
    one = carried.raw()

    one.sendall(frame(b"H", b'{"columns": 80, "rows": 24}'))
    one.settimeout(PATIENCE)

    assert Frames().feed(one.recv(1 << 16)) == [
        (GONE, b"held for frontends by a newer humanize; `hmz` of it reads it")
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
    held = carried.daemon()
    alice, bob = carried.link("alice"), carried.link("bob")

    status = held.status()

    assert status["ok"]
    assert (status["kind"], status["protocol"], status["attached"]) == (
        "host",
        PROTOCOL,
        2,
    )
    assert [one["name"] for one in status["clients"]] == ["alice", "bob"]
    assert (status["state"], status["flows"], status["calls"]) == ("idle", [], [])

    assert held.detach() == 2
    assert until(lambda: alice.gone() == "let go" and bob.gone() == "let go")


@pytest.mark.timeout(60)
def test_stopping_closes_the_host_and_every_frontend_is_told_why(
    carried: Carried,
) -> None:
    held = carried.daemon()
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


# ------------------------------------------------------------------- the daemon


@pytest.mark.timeout(60)
def test_a_workspace_no_host_holds_is_said_to_be_held_by_nobody(
    carried: Carried, tmp_path: Path
) -> None:
    """Rather than handed to the host of another workspace, or left waiting."""
    elsewhere = where.workspace(tmp_path / "elsewhere")

    with pytest.raises(OSError, match="no runs are held in"):
        reached(carried.at, elsewhere, "lost")
    assert carried.host.attached == 0


@pytest.mark.timeout(60)
def test_a_second_host_of_one_workspace_is_refused(carried: Carried) -> None:
    """Two hosts of one workspace are two flows writing over one epic."""
    second = where.connects(carried.at)
    second.sendall(
        spoken(
            CONTROL,
            {"do": "serve", "pid": os.getpid(), "workspace": carried.workspace},
        )
    )
    second.settimeout(PATIENCE)

    assert second.recv(1) == b""
    assert carried.link("alice").link.client


@pytest.mark.timeout(60)
def test_the_daemon_going_closes_the_runs_it_was_the_way_to(carried: Carried) -> None:
    """Nobody new could reach them, and nothing would be left to stop them."""
    alice = carried.link("alice")

    carried.router.close()

    assert until(lambda: alice.gone() == "the host was closed")
    assert carried.carrier.wait(PATIENCE)
    assert not (carried.at / where.SOCKET).exists()

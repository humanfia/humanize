"""Two halves of a session meeting through a real broker on loopback.

Both halves are this machine, so whether they end up punched through to each other or carried
by the broker depends on whether the kernel lends one port to two sockets; what is checked is
that they are joined either way, and that a broker given no window to punch in carries them.
Two machines that genuinely cannot reach each other are a system test's.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import hmz
from hmz.coganchor.rendezvous import (
    ANCHOR,
    PAIRING,
    PUNCHING,
    SERVE,
    Broker,
    Meeting,
    dial,
    meet,
    standing,
    ticket,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

PATIENCE = 20.0


def _broker(
    *, patience: float = PAIRING, punching: float = PUNCHING
) -> Iterator[Broker]:
    made = Broker("127.0.0.1", 0, patience=patience, punching=punching)
    made.start()
    try:
        yield made
    finally:
        made.close()


@pytest.fixture
def broker() -> Iterator[Broker]:
    """A broker on loopback with a short window to punch in."""
    yield from _broker(punching=0.5)


@pytest.fixture
def carrying() -> Iterator[Broker]:
    """A broker with no window at all, which carries every pair it is given."""
    yield from _broker(punching=0.0)


def met(meeting: Meeting) -> dict[str, socket.socket]:
    """Both halves of one meeting, dialled at once from two threads."""
    held: dict[str, socket.socket] = {}
    failed: dict[str, BaseException] = {}

    def half(role: str) -> None:
        try:
            held[role] = dial(meeting, role, timeout=PATIENCE)
            held[role].settimeout(PATIENCE)
        except BaseException as exc:  # noqa: BLE001 -- reported below
            failed[role] = exc

    both = [threading.Thread(target=half, args=(role,)) for role in (ANCHOR, SERVE)]
    for one in both:
        one.start()
    for one in both:
        one.join(PATIENCE + 10)
    assert not failed, failed
    return held


def _closed(held: dict[str, socket.socket]) -> None:
    for one in held.values():
        one.close()


def test_two_halves_are_joined_and_talk_both_ways(broker: Broker) -> None:
    held = met(Meeting(ticket(), *broker.address))
    try:
        held[ANCHOR].sendall(b"from the anchor")
        assert held[SERVE].recv(64) == b"from the anchor"
        held[SERVE].sendall(b"from the target")
        assert held[ANCHOR].recv(64) == b"from the target"
    finally:
        _closed(held)


def test_a_pair_given_no_window_is_carried_whole(carrying: Broker) -> None:
    payload = bytes(range(256)) * 4096  # a megabyte: many relay frames
    held = met(Meeting(ticket(), *carrying.address))
    try:
        sender = threading.Thread(target=held[ANCHOR].sendall, args=(payload,))
        sender.start()
        got = b""
        while len(got) < len(payload) and (chunk := held[SERVE].recv(65536)):
            got += chunk
        sender.join(PATIENCE)
    finally:
        _closed(held)

    assert got == payload
    assert carrying.carried == 1


def test_two_meetings_at_one_broker_stay_two_sessions(broker: Broker) -> None:
    one = met(Meeting(ticket(), *broker.address))
    other = met(Meeting(ticket(), *broker.address))
    try:
        one[ANCHOR].sendall(b"first")
        other[ANCHOR].sendall(b"second")
        assert one[SERVE].recv(64) == b"first"
        assert other[SERVE].recv(64) == b"second"
    finally:
        _closed(one)
        _closed(other)


def test_one_ticket_is_met_at_again_and_its_halves_each_in_turn(
    broker: Broker,
) -> None:
    meeting = Meeting(ticket(), *broker.address)
    held: dict[str, list[socket.socket]] = {ANCHOR: [], SERVE: []}
    lock = threading.Lock()

    def half(role: str) -> None:
        met = dial(meeting, role, timeout=PATIENCE)
        met.settimeout(PATIENCE)
        with lock:
            held[role].append(met)

    halves = [
        threading.Thread(target=half, args=(role,))
        for _ in range(3)
        for role in (ANCHOR, SERVE)
    ]
    for one in halves:
        one.start()
    for one in halves:
        one.join(3 * PATIENCE)
    try:
        assert [len(held[ANCHOR]), len(held[SERVE])] == [3, 3]
        for at, one in enumerate(held[ANCHOR]):
            one.sendall(bytes([at]))
        for one in held[SERVE]:
            one.sendall(one.recv(1))
        # Each anchoring half hears back its own word, so each was joined to one other.
        assert [one.recv(1) for one in held[ANCHOR]] == [b"\x00", b"\x01", b"\x02"]
    finally:
        for one in held[ANCHOR] + held[SERVE]:
            one.close()


@pytest.fixture
def booking() -> Iterator[Broker]:
    """A broker on loopback that introduces only the meetings booked with it."""
    made = Broker("127.0.0.1", 0, punching=0.5, booked=True)
    made.start()
    try:
        yield made
    finally:
        made.close()


#: What the serving half left at a booked meeting proves itself with, here.
KEY = "k" * 32


def _standing(at: Meeting) -> tuple[threading.Thread, dict[str, object]]:
    """A serving half waiting at a booked meeting, in a thread, and what it came to."""
    came: dict[str, object] = {}

    def wait() -> None:
        try:
            came["met"], came["asked"] = meet(at, SERVE, key=KEY, timeout=PATIENCE)
        except OSError as exc:
            came["failed"] = exc

    waiting = threading.Thread(target=wait)
    waiting.start()
    return waiting, came


def test_a_booked_meeting_joins_halves_holding_a_ticket_each(booking: Broker) -> None:
    serving, anchoring = booking.stand()
    host, port = booking.address
    waiting, came = _standing(Meeting(serving, host, port))

    anchored = dial(
        Meeting(anchoring, host, port), ANCHOR, timeout=PATIENCE, asks=["/w:/real"]
    )
    waiting.join(PATIENCE)
    met = came["met"]
    assert isinstance(met, socket.socket)
    try:
        # Told what the anchor asked to be served, which is all the anchor says of itself.
        assert came["asked"] == ("/w:/real",)
        anchored.sendall(b"from the anchor")
        assert met.recv(64) == b"from the anchor"
        met.sendall(b"from the task")
        assert anchored.recv(64) == b"from the task"
    finally:
        met.close()
        anchored.close()


def test_a_booked_meetings_tickets_let_in_their_own_half_and_nobody_else(
    booking: Broker,
) -> None:
    serving, anchoring = booking.stand()
    host, port = booking.address
    # Met once, so that the ticket is the serving half's before anything else tries it.
    waiting, came = _standing(Meeting(serving, host, port))
    dial(Meeting(anchoring, host, port), ANCHOR, timeout=PATIENCE).close()
    waiting.join(PATIENCE)
    first = came["met"]
    assert isinstance(first, socket.socket)
    first.close()
    waiting, came = _standing(Meeting(serving, host, port))
    refused = "no meeting here lets that half in"
    try:
        # The ticket the task holds, read by anything running there: no way to the task...
        with pytest.raises(OSError, match=refused):
            dial(Meeting(serving, host, port), ANCHOR, timeout=PATIENCE)
        # ...and none to be met in its place, without the key it chose or with another.
        with pytest.raises(OSError, match=refused):
            dial(Meeting(serving, host, port), SERVE, timeout=PATIENCE)
        with pytest.raises(OSError, match=refused):
            meet(Meeting(serving, host, port), SERVE, key="x" * 32, timeout=PATIENCE)
        # The anchor's ticket is the anchor's, and a ticket nobody booked is nobody's.
        with pytest.raises(OSError, match=refused):
            dial(Meeting(anchoring, host, port), SERVE, timeout=PATIENCE)
        with pytest.raises(OSError, match=refused):
            dial(Meeting(ticket(), host, port), ANCHOR, timeout=PATIENCE)
        anchored = dial(Meeting(anchoring, host, port), ANCHOR, timeout=PATIENCE)
    finally:
        waiting.join(PATIENCE)
    met = came["met"]
    assert isinstance(met, socket.socket)
    met.close()
    anchored.close()

    booking.withdraw(serving)

    for name, role in ((anchoring, ANCHOR), (serving, SERVE)):
        with pytest.raises(OSError, match=refused):
            meet(Meeting(name, host, port), role, key=KEY, timeout=PATIENCE)


def test_the_broker_for_booked_meetings_listens_only_where_it_is_dialled() -> None:
    broker, port = standing("127.0.0.1")
    assert broker.address == ("127.0.0.1", port)
    assert standing("127.0.0.1") == (broker, port)
    # An address that is not this machine's -- a NAT's -- is listened for everywhere.
    elsewhere, _ = standing("192.0.2.1")
    assert elsewhere.address[0] == "0.0.0.0"  # noqa: S104


def test_the_keys_of_brokers_whose_process_is_gone_are_removed_by_the_next() -> None:
    home = hmz.machine()
    ended = subprocess.Popen([sys.executable, "-c", "pass"])
    ended.wait()
    gone = home / f"rendezvous-{ended.pid}-a1"
    kept = [
        home / f"rendezvous-{os.getpid()}-b2",  # a process still running: this one
        home / "rendezvous-d4",  # named as no process's
    ]
    for one in (gone, *kept):
        one.mkdir()
        (one / "key.pem").write_text("key")

    # The next process to stand a broker for booked meetings, from its start to its exit.
    made = subprocess.run(
        [
            *(sys.executable, "-P", "-c"),
            (
                "from hmz.coganchor.rendezvous import standing\n"
                "print(standing('127.0.0.1')[0].tls)"
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=PATIENCE,
    )

    assert not gone.exists()
    assert all((one / "key.pem").exists() for one in kept)
    # And its own, made under the same directory, removed as it exited.
    own = Path(made.stdout.strip())
    assert own.parent == home
    assert not own.exists()


def test_a_half_whose_other_half_never_comes_is_told_so() -> None:
    for broker in _broker(patience=0.3):
        with pytest.raises(OSError, match="never arrived"):
            dial(Meeting(ticket(), *broker.address), ANCHOR, timeout=PATIENCE)


def test_a_half_that_is_neither_half_is_refused_before_dialling(
    broker: Broker,
) -> None:
    with pytest.raises(ValueError, match="role"):
        dial(Meeting(ticket(), *broker.address), "onlooker")


def test_a_broker_nobody_runs_cannot_be_met() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    with pytest.raises(OSError, match=r"."):
        dial(Meeting(ticket(), "127.0.0.1", port), ANCHOR, timeout=2)

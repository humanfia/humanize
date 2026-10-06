"""Two halves of a session meeting through a real broker on loopback.

Both halves are this machine, so whether they end up punched through to each other or carried
by the broker depends on whether the kernel lends one port to two sockets; what is checked is
that they are joined either way, and that a broker given no window to punch in carries them.
Two machines that genuinely cannot reach each other are a system test's.
"""

from __future__ import annotations

import socket
import threading
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.rendezvous import ANCHOR, SERVE, Broker, Meeting, dial, ticket

if TYPE_CHECKING:
    from collections.abc import Iterator

PATIENCE = 20.0


def _broker(**settings: float) -> Iterator[Broker]:
    made = Broker("127.0.0.1", 0, **settings)
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

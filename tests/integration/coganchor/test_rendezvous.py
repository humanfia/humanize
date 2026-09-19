"""Two halves of a session introduced over a loopback socket, both ways round.

A real broker on a real port and two real peers dialling it, which is what makes this an
integration test rather than a unit one: the thing being checked is that two sockets end up
joined, and nothing standing in for a socket can say that. Both machines are this one, so the
addresses each half offers the other are its own loopback -- which is a network where the
punching works, and where it can be made not to by closing the window.

What needs two machines that genuinely cannot reach each other is in
`tests/system/coganchor/test_topologies.py`, where the two are containers on networks docker
keeps apart.
"""

from __future__ import annotations

import socket
import threading
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.rendezvous import (
    _CONVINCED,
    _DISBELIEVING,
    ANCHOR,
    PUNCHING,
    SERVE,
    Broker,
    Meeting,
    _both,
    _Pair,
    _splice,
    dial,
    ticket,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

#: Long enough that a loaded machine is not a failure, short enough that a broken one is.
PATIENCE = 30.0

#: A window wide enough for two halves of this machine to find each other through, which on
#: loopback is every window there is -- what these tests vary is whether one is opened at all.
PUNCHING_ENOUGH = PUNCHING


def _shares_a_port() -> bool:
    """Whether this kernel lends one port to two sockets, which is what a punch is made of.

    Both halves open outward from, and listen on, the port they dialled the broker from, and
    a kernel that will not allow that leaves a half punching outward only -- which works
    between two machines and cannot work between two halves of this one, both of them being
    behind the same refusal. So it is asked rather than assumed, and asked of the same call
    `dial` asks it of: the tests that need a direct path say so, and a machine that cannot
    give them one says which thing it could not give.
    """
    home, ear, _ = _both()
    home.close()
    if ear is None:
        return False
    ear.close()
    return True


#: Asked once: it is a fact about the kernel, and it is two sockets to find out.
punches = pytest.mark.skipif(
    not _shares_a_port(), reason="this kernel will not lend one port to two sockets"
)


@pytest.fixture
def broker() -> Iterator[Broker]:
    """A broker on loopback, holding meetings for the length of one test."""
    made = Broker(host="127.0.0.1", port=0)
    made.start()
    yield made
    made.close()


def met(broker: Broker, meeting: Meeting) -> dict[str, socket.socket]:
    """Both halves of one meeting, dialled at once, as the two machines would.

    Args:
      broker: Where they meet.
      meeting: Under what ticket.

    Returns:
      The socket each half ended up holding, by role.

    Raises:
      AssertionError: If either half came away with nothing.
    """
    held: dict[str, socket.socket] = {}
    failed: dict[str, BaseException] = {}

    def half(role: str) -> None:
        try:
            held[role] = dial(meeting, role, timeout=PATIENCE)
        except BaseException as exc:  # noqa: BLE001 -- reported below, not handled
            failed[role] = exc

    both = [threading.Thread(target=half, args=(role,)) for role in (ANCHOR, SERVE)]
    for one in both:
        one.start()
    for one in both:
        one.join(timeout=PATIENCE + 10)
    assert not failed, failed
    assert set(held) == {ANCHOR, SERVE}
    return held


def talk(held: dict[str, socket.socket]) -> None:
    """Sends a word each way and reads it at the other end, then puts both sockets down."""
    try:
        for saying, hearing in ((ANCHOR, SERVE), (SERVE, ANCHOR)):
            held[saying].sendall(f"from the {saying}\n".encode())
            assert held[hearing].recv(64) == f"from the {saying}\n".encode()
    finally:
        for one in held.values():
            one.close()


@punches
def test_two_halves_that_can_reach_each_other_are_introduced(broker: Broker) -> None:
    """And the broker is out of the path, which is what its own count says."""
    meeting = Meeting(ticket(), *broker.address)

    held = met(broker, meeting)

    talk(held)
    assert broker.carried == 0, "the broker carried a session it only had to introduce"


def test_two_halves_that_cannot_are_carried(broker: Broker) -> None:
    """The window is what decides it, so a window of nothing is every network that fails."""
    broker._punching = (
        0.0  # every candidate unreachable, without an unreachable candidate
    )
    meeting = Meeting(ticket(), *broker.address)

    held = met(broker, meeting)

    talk(held)
    assert broker.carried == 1


def test_a_carried_session_moves_more_than_one_frame_fits_in(broker: Broker) -> None:
    """The relay is a splice rather than a message, so nothing about it has a size."""
    broker._punching = 0.0
    held = met(broker, Meeting(ticket(), *broker.address))
    payload = bytes(range(256)) * 4096  # a megabyte, well past any buffer in the way

    try:
        threading.Thread(target=held[ANCHOR].sendall, args=(payload,)).start()
        read = bytearray()
        while len(read) < len(payload):
            block = held[SERVE].recv(1 << 16)
            assert block, "the relay ended early"
            read += block
        assert bytes(read) == payload
    finally:
        for one in held.values():
            one.close()


def test_each_half_is_told_what_it_looks_like_from_outside(broker: Broker) -> None:
    """Which is the one thing about itself a machine behind a NAT cannot work out.

    Asked of the broker directly rather than through `dial`, because what `dial` does with
    the answer is offer it to the other half, and a test that read it back off the candidate
    list would be reading this machine's own address either way.
    """
    with socket.create_connection(broker.address, timeout=PATIENCE) as asking:
        asking.sendall(b'{"ticket": "half-a-meeting", "role": "anchor", "at": []}\n')
        said = asking.recv(4096).decode()
        host, port = asking.getsockname()[0], asking.getsockname()[1]

    assert '"seen"' in said
    assert f'"{host}"' in said, said
    assert str(port) in said, said


def test_a_half_whose_other_half_never_arrives_is_told_so(broker: Broker) -> None:
    """Rather than waiting out a turn on a machine that was never started."""
    broker._patience = 0.5
    meeting = Meeting(ticket(), *broker.address)

    with pytest.raises(OSError, match="never arrived"):
        dial(meeting, ANCHOR, timeout=PATIENCE)


def test_a_meeting_is_read_back_out_of_its_spelling() -> None:
    assert Meeting.parse("cafe@broker.example:9001") == Meeting(
        "cafe", "broker.example", 9001
    )
    assert str(Meeting("cafe", "broker.example", 9001)) == "cafe@broker.example:9001"


@pytest.mark.parametrize(
    "spec",
    ["", "cafe", "cafe@broker", "@broker:9001", "cafe@:9001", "cafe@broker:port"],
)
def test_a_meeting_that_is_not_one_is_refused(spec: str) -> None:
    with pytest.raises(ValueError, match=r"meeting|TICKET"):
        Meeting.parse(spec)


def test_a_half_that_is_neither_half_is_refused(broker: Broker) -> None:
    """Before it has opened anything, since there is no third thing for it to be."""
    with pytest.raises(ValueError, match="role"):
        dial(Meeting(ticket(), *broker.address), "onlooker")


def test_two_meetings_at_one_broker_do_not_meet_each_other(broker: Broker) -> None:
    """A ticket is the whole of what pairs two halves, so two of them are two sessions."""
    one, other = Meeting(ticket(), *broker.address), Meeting(ticket(), *broker.address)

    held, also = met(broker, one), met(broker, other)

    try:
        held[ANCHOR].sendall(b"for the first\n")
        also[ANCHOR].sendall(b"for the second\n")
        assert held[SERVE].recv(64) == b"for the first\n"
        assert also[SERVE].recv(64) == b"for the second\n"
    finally:
        for pair in (held, also):
            for one_end in pair.values():
                one_end.close()


@punches
def test_a_pair_that_could_not_be_introduced_is_not_tried_again(broker: Broker) -> None:
    """Two machines with no route between them do not grow one between two sessions.

    So a later pair of the same two is carried without spending the window on an answer the
    broker already has, which at a hundred sessions is several minutes of nothing happening.
    It takes more than one failure to be believed: a pair here is named by the two addresses
    the world has for the two halves, and every machine behind one NAT wears the same one --
    so a single unlucky punch must not condemn every pair of machines behind them.
    """
    broker._punching = 0.0
    for _ in range(_CONVINCED):
        for one in met(broker, Meeting(ticket(), *broker.address)).values():
            one.close()
    assert broker.carried == _CONVINCED
    broker._punching = PUNCHING_ENOUGH  # a window that would work, if one were opened

    held = met(broker, Meeting(ticket(), *broker.address))

    talk(held)
    assert broker.carried == _CONVINCED + 1, (
        "the broker went looking for a route it had already failed to find"
    )


@punches
def test_a_pair_is_disbelieved_every_so_often(broker: Broker) -> None:
    """A firewall rule is the kind of thing that changes, so the answer is not kept forever."""
    broker._punching = 0.0
    for _ in range(_DISBELIEVING):
        for one in met(broker, Meeting(ticket(), *broker.address)).values():
            one.close()
    broker._punching = PUNCHING_ENOUGH

    held = met(broker, Meeting(ticket(), *broker.address))

    talk(held)
    assert broker.carried == _DISBELIEVING, (
        "the broker never went back to see whether the two could reach each other"
    )


def test_a_carried_session_is_not_cut_short_by_a_deadline_left_on_its_sockets() -> None:
    """The two sockets a splice is handed have just finished carrying the introduction.

    That is read a line at a time under a deadline, so each of them arrives still holding
    whatever timeout the last line left -- which for a meeting that took its time is a very
    short one. A `sendall` that timed out would have sent part of a frame and the far side
    would read the rest of the session shifted by however many bytes went missing, which is
    not something either end can recognise, let alone recover from. So the splice clears them
    before it moves a byte, and this is that.
    """
    one, near = socket.socketpair()
    far, two = socket.socketpair()
    # As short as the last line of an introduction that nearly ran out of patience leaves it.
    near.settimeout(0.001)
    far.settimeout(0.001)
    payload = bytes(range(256)) * 16384  # four mebibytes, many frames' worth

    threading.Thread(target=_splice, args=(near, far), daemon=True).start()
    try:
        threading.Thread(target=one.sendall, args=(payload,), daemon=True).start()
        read = bytearray()
        two.settimeout(PATIENCE)
        while len(read) < len(payload):
            block = two.recv(1 << 16)
            assert block, (
                f"the splice stopped after {len(read)} of {len(payload)} bytes"
            )
            read += block
        assert bytes(read) == payload
    finally:
        for end in (one, near, far, two):
            end.close()


def test_a_pair_is_not_carried_until_both_halves_have_been_told_it_will_be() -> None:
    """Otherwise the session's first bytes arrive where a control line is still expected.

    The two halves are answered by two threads and nothing orders them, so the one that does
    the carrying can reach the splice while the *other* half has not yet been sent the line
    saying a splice is coming. That half is reading a control line a character at a time, and
    what it would read is the first frame of the session -- which it cannot recognise, cannot
    recover from, and would spend the rest of the session shifted by.

    Driven against the pair itself rather than through a broker, because what is being checked
    is an ordering between two threads and a test that hoped to lose a race is a test that
    passes when the race is lost the other way.
    """
    pair = _Pair("a-meeting")
    ends = {role: socket.socketpair() for role in (ANCHOR, SERVE)}
    try:
        for role, (theirs, brokers) in ends.items():
            pair.arrive(role, brokers, [("127.0.0.1", 1)])
            theirs.settimeout(0.5)
        pair.spoke(ANCHOR)  # and not the other one

        threading.Thread(target=pair.carry, args=(ANCHOR,), daemon=True).start()
        ends[ANCHOR][0].sendall(b"the session, starting\n")

        with pytest.raises(TimeoutError):
            ends[SERVE][0].recv(64)
        pair.spoke(SERVE)
        assert ends[SERVE][0].recv(64) == b"the session, starting\n"
    finally:
        pair.leave(ANCHOR)
        pair.leave(SERVE)
        for theirs, brokers in ends.values():
            theirs.close()
            brokers.close()

"""Meetings and tickets: the parts of a rendezvous that are words rather than sockets."""

from __future__ import annotations

import pytest

from hmz.coganchor.rendezvous import ANCHOR, ROLES, SERVE, Broker, Meeting, ticket


def test_a_ticket_is_long_fresh_and_hex() -> None:
    minted = {ticket() for _ in range(64)}
    assert len(minted) == 64
    assert all(len(one) == 32 and int(one, 16) >= 0 for one in minted)


def test_the_two_halves_are_the_two_roles() -> None:
    assert frozenset({ANCHOR, SERVE}) == ROLES
    assert ANCHOR != SERVE


@pytest.mark.parametrize(
    ("spec", "meeting"),
    [
        ("t@host:7", Meeting("t", "host", 7)),
        ("t@10.0.0.1:65535", Meeting("t", "10.0.0.1", 65535)),
        ("t@[::1]:9", Meeting("t", "::1", 9)),
        ("t@a@b:1", Meeting("t", "a@b", 1)),
        ("t@h:7?tls=/srv/tls", Meeting("t", "h", 7, "/srv/tls")),
        ("t@h:7?tls=/a%20b", Meeting("t", "h", 7, "/a b")),
    ],
)
def test_a_meeting_reads_out_of_its_spelling(spec: str, meeting: Meeting) -> None:
    assert Meeting.parse(spec) == meeting


@pytest.mark.parametrize(
    "spec",
    [
        "",
        "t",
        "t@host",
        "@host:7",
        "t@:7",
        "t@host:",
        "t@host:port",
        "host:7",
        # A sealed meeting names one directory, once, and nothing else.
        "t@h:7?",
        "t@h:7?tls",
        "t@h:7?tls=",
        "t@h:7?pin=ab",
        "t@h:7?tls=/a&tls=/b",
        "t@h:7?tls=/a&x=1",
    ],
)
def test_a_misspelled_meeting_is_refused(spec: str) -> None:
    with pytest.raises(ValueError, match="malformed meeting"):
        Meeting.parse(spec)


def test_a_meeting_spells_itself_back() -> None:
    meeting = Meeting(ticket(), "broker.example", 4242)
    assert Meeting.parse(str(meeting)) == meeting
    assert str(meeting).endswith("@broker.example:4242")


def test_a_sealed_meeting_spells_itself_back_with_its_directory() -> None:
    meeting = Meeting(ticket(), "10.0.0.1", 4242, "/tmp/humanize 1/rendezvous-x")
    assert str(meeting).endswith("@10.0.0.1:4242?tls=/tmp/humanize%201/rendezvous-x")
    assert Meeting.parse(str(meeting)) == meeting


def test_a_broker_not_yet_started_has_no_address_and_has_carried_nothing() -> None:
    broker = Broker("127.0.0.1", 0)
    assert broker.carried == 0
    with pytest.raises(RuntimeError, match="not been started"):
        _ = broker.address
    broker.close()

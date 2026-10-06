"""`hmz.daemon.proto`: frames written, and frames read back out of whatever arrived."""

from __future__ import annotations

import json
import struct

import pytest

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


def test_the_three_kinds_are_one_distinct_byte_each() -> None:
    kinds = {CONTROL, GONE, MESSAGE}
    assert len(kinds) == 3
    assert all(isinstance(one, bytes) and len(one) == 1 for one in kinds)
    assert isinstance(PROTOCOL, int)
    assert PROTOCOL > 0


@pytest.mark.parametrize("payload", [b"", b"x", b"hello world", bytes(range(256))])
def test_a_frame_is_its_kind_its_length_and_its_payload(payload: bytes) -> None:
    written = frame(MESSAGE, payload)
    assert written[:1] == MESSAGE
    assert struct.unpack(">I", written[1:5]) == (len(payload),)
    assert written[5:] == payload


def test_a_frame_without_a_payload_is_empty() -> None:
    assert frame(GONE) == GONE + b"\0\0\0\0"


def test_spoken_carries_the_mapping_as_json() -> None:
    written = spoken(CONTROL, {"do": "status", "n": 1})
    assert written[:1] == CONTROL
    assert json.loads(written[5:]) == {"do": "status", "n": 1}


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b'{"ok": true}', {"ok": True}),
        (b"{}", {}),
        (b"[1, 2]", {}),
        (b'"text"', {}),
        (b"not json", {}),
        (b"\xff\xfe", {}),
        (b"", {}),
    ],
)
def test_asked_reads_a_mapping_and_nothing_else(
    payload: bytes, expected: dict[str, object]
) -> None:
    assert asked(payload) == expected


def test_asked_reads_back_what_spoken_wrote() -> None:
    said = {"do": "start", "agents": {"coder": "claude"}, "n": [1, 2]}
    ((kind, payload),) = Frames().feed(spoken(CONTROL, said))
    assert kind == CONTROL
    assert asked(payload) == said


def test_frames_gives_back_every_whole_frame_in_order() -> None:
    data = frame(MESSAGE, b"one") + frame(CONTROL, b"two") + frame(GONE)
    assert Frames().feed(data) == [(MESSAGE, b"one"), (CONTROL, b"two"), (GONE, b"")]


def test_frames_gives_back_nothing_until_a_frame_is_whole() -> None:
    data = frame(MESSAGE, b"payload")
    frames = Frames()
    for at in range(len(data) - 1):
        assert frames.feed(data[at : at + 1]) == []
    assert frames.feed(data[-1:]) == [(MESSAGE, b"payload")]


def test_frames_holds_the_rest_of_a_read_for_the_next() -> None:
    first, second = frame(MESSAGE, b"a"), frame(MESSAGE, b"bb")
    frames = Frames()
    assert frames.feed(first + second[:3]) == [(MESSAGE, b"a")]
    assert frames.feed(second[3:]) == [(MESSAGE, b"bb")]
    assert frames.feed(b"") == []


def test_frames_never_hands_out_a_frame_twice() -> None:
    frames = Frames()
    assert frames.feed(frame(MESSAGE, b"once")) == [(MESSAGE, b"once")]
    assert frames.feed(b"") == []


def test_frames_refuses_a_length_no_frame_has_and_starts_again() -> None:
    frames = Frames()
    with pytest.raises(ValueError, match="bytes is not one of these"):
        frames.feed(MESSAGE + struct.pack(">I", 1 << 30))
    assert frames.feed(frame(MESSAGE, b"after")) == [(MESSAGE, b"after")]


def test_frames_takes_the_longest_frame_there_is() -> None:
    payload = b"x" * (1 << 22)
    assert Frames().feed(frame(MESSAGE, payload)) == [(MESSAGE, payload)]

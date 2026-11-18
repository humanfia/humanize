"""Frames: a big-endian length, then one JSON object in UTF-8 (Section 6.3 of wire.md)."""

import json
import struct
from pathlib import Path

import pytest

from hmz.rpc import LONGEST, FrameError, Frames, encode


def test_a_frame_is_its_length_then_its_json() -> None:
    frame = encode({"a": 1})
    payload = frame[4:]
    assert struct.unpack(">I", frame[:4]) == (len(payload),)
    assert json.loads(payload) == {"a": 1}


def test_non_ascii_is_written_as_itself_and_other_values_as_text() -> None:
    payload = encode({"name": "日本", "path": Path("/tmp/x")})[4:]
    assert "日本".encode() in payload
    assert json.loads(payload) == {"name": "日本", "path": "/tmp/x"}


def test_a_float_that_is_not_finite_is_written_as_its_text() -> None:
    data = encode(
        {"at": Path("/x"), "n": [float("nan"), float("inf")], "d": {"m": -float("inf")}}
    )
    assert json.loads(data[4:], parse_constant=pytest.fail) == {
        "at": "/x",
        "n": ["NaN", "Infinity"],
        "d": {"m": "-Infinity"},
    }


def test_a_cycle_is_still_not_encoded() -> None:
    cycle: dict[str, object] = {"n": float("nan")}
    cycle["self"] = cycle
    with pytest.raises(ValueError, match="Circular"):
        encode(cycle)


def test_every_frame_comes_out_once_and_in_order_however_it_is_split() -> None:
    stream = b"".join(encode({"n": n}) for n in range(5))
    for size in (1, 3, 7, len(stream)):
        frames = Frames()
        out: list[bytes] = []
        for at in range(0, len(stream), size):
            out.extend(frames.feed(stream[at : at + size]))
        assert [json.loads(p)["n"] for p in out] == list(range(5))


def test_a_partial_frame_waits_for_the_rest() -> None:
    frame = encode({"a": 1})
    frames = Frames()
    assert frames.feed(frame[:-1]) == []
    assert frames.feed(frame[-1:]) == [frame[4:]]


@pytest.mark.parametrize("length", [0, LONGEST + 1, 2**32 - 1])
def test_a_length_no_frame_has_is_refused(length: int) -> None:
    with pytest.raises(FrameError):
        Frames().feed(struct.pack(">I", length) + b"{}")


def test_the_longest_frame_is_accepted() -> None:
    head = struct.pack(">I", LONGEST)
    assert Frames().feed(head + b" " * LONGEST) == [b" " * LONGEST]


def test_a_frame_longer_than_a_reader_accepts_is_not_encoded() -> None:
    with pytest.raises(FrameError):
        encode({"a": "x" * LONGEST})

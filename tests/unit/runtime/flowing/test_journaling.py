"""What a resumable run writes down, and what a resumed one reads back: `journaling`."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import atomic
from hmz.flows import StateNotSerializable
from hmz.runtime.flowing import journaling
from hmz.runtime.flowing.journaling import FlowStateImpl, Journal, Past, digest

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


@pytest.fixture(autouse=True)
def _writes_plainly(monkeypatch: pytest.MonkeyPatch) -> None:
    """The atomic write of coganchor's, as a plain one: what it writes is what is asserted."""

    def writes(at: Path, said: str | bytes | Iterable[bytes]) -> None:
        if isinstance(said, str):
            at.write_text(said)
        elif isinstance(said, bytes):
            at.write_bytes(said)
        else:
            at.write_bytes(b"".join(said))

    monkeypatch.setattr(atomic, "writes", writes)


def lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_bytes().splitlines()]


# --------------------------------------------------------------------------- digest


def test_digest_is_stable_and_tells_calls_apart() -> None:
    one = digest("x:y", "task", ["a=claude"], b"{}")
    assert one == digest("x:y", "task", ["a=claude"], b"{}")
    assert len(one) == 32
    assert int(one, 16) >= 0
    others = {
        digest("x:z", "task", ["a=claude"], b"{}"),
        digest("x:y", "other", ["a=claude"], b"{}"),
        digest("x:y", "task", ["a=codex"], b"{}"),
        digest("x:y", "task", ["a=claude"], b'{"n":1}'),
        digest("x:y", "task", [], b"{}"),
    }
    assert one not in others
    assert len(others) == 5


def test_digest_takes_text_python_cannot_encode() -> None:
    assert digest("x", "\udcff", [], b"")


# -------------------------------------------------------------------------- journal


async def test_a_fresh_journal_is_a_header(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "run.jsonl"
    journal, past = Journal.opened(path, asyncio.get_running_loop(), resume=False)
    journal.close()
    assert past is None
    assert lines(path) == [{"t": "journal", "v": 1}]


async def test_resuming_with_nothing_there_starts_afresh(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    journal, past = Journal.opened(path, asyncio.get_running_loop(), resume=True)
    journal.close()
    assert past is None


async def test_records_are_batched_and_state_writes_are_not(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    journal, _ = Journal.opened(path, asyncio.get_running_loop(), resume=False)
    journal.call(1, 0, "d1", 0, b'"m:f"')
    journal.note({"t": "session", "id": 1, "role": "a", "session": "s"})
    assert journal.records == 2
    assert journal.writes == 0
    assert len(lines(path)) == 1
    journal.set(1, "round", b"2")
    assert journal.writes == 1
    assert [one["t"] for one in lines(path)] == ["journal", "call", "session", "set"]
    journal.delete(1, "round")
    journal.end(1, ok=False)
    journal.close()
    journal.close()
    assert lines(path)[-2:] == [
        {"t": "del", "id": 1, "key": "round"},
        {"t": "end", "id": 1, "ok": False},
    ]
    assert journal.records == 5


async def test_a_batch_is_written_when_its_time_comes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(journaling, "BATCH", 0.0)
    path = tmp_path / "run.jsonl"
    journal, _ = Journal.opened(path, asyncio.get_running_loop(), resume=False)
    journal.end(3, ok=True)
    journal.end(4, ok=True)
    assert journal.writes == 0
    for _ in range(3):
        await asyncio.sleep(0)
    assert journal.writes == 1
    assert lines(path)[-2:] == [
        {"t": "end", "id": 3, "ok": True},
        {"t": "end", "id": 4, "ok": True},
    ]
    journal.flush()
    assert journal.writes == 1
    journal.close()


def earlier(path: Path) -> None:
    """A journal an earlier run left: two calls, one ended, and a line cut off."""
    records: list[object] = [
        {"t": "journal", "v": 1},
        {"t": "call", "id": 1, "parent": 0, "digest": "top", "seq": 0, "ref": "m:f"},
        {"t": "set", "id": 1, "key": "round", "value": 1},
        {"t": "set", "id": 1, "key": "round", "value": 2},
        {"t": "set", "id": 1, "key": "gone", "value": True},
        {"t": "del", "id": 1, "key": "gone"},
        {"t": "call", "id": 2, "parent": 1, "digest": "sub", "seq": 0, "ref": "m:g"},
        {"t": "call", "id": 3, "parent": 1, "digest": "sub", "seq": 1, "ref": "m:g"},
        {"t": "session", "id": 2, "role": "a", "session": "s-1"},
        {"t": "end", "id": 2, "ok": True},
        {"t": "set", "id": 99, "key": "orphan", "value": 0},
        {"t": "set", "id": "x", "key": "k"},
        ["not", "a", "record"],
    ]
    text = "\n".join(json.dumps(one) for one in records)
    path.write_text(text + '\n{"t": "set", "id": 1, "ke')


async def test_resuming_picks_up_the_earlier_run_compacted(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    earlier(path)
    journal, past = Journal.opened(path, asyncio.get_running_loop(), resume=True)
    journal.close()
    assert past is not None
    assert past.root == 1
    assert past.next_id == 4
    top = past.calls[1]
    assert (top.ref, top.state, top.ended) == ("m:f", {"round": 2}, None)
    first = past.claim(1, "sub", 0)
    second = past.claim(1, "sub", 1)
    assert first is not None
    assert second is not None
    assert (first.id, first.ended) == (2, True)
    assert second.id == 3
    assert past.claim(1, "sub", 2) is None
    assert past.claim(1, "other", 0) is None
    assert lines(path) == [
        {"t": "journal", "v": 1},
        {"t": "call", "id": 1, "parent": 0, "digest": "top", "seq": 0, "ref": "m:f"},
        {"t": "set", "id": 1, "key": "round", "value": 2},
        {"t": "call", "id": 2, "parent": 1, "digest": "sub", "seq": 0, "ref": "m:g"},
        {"t": "session", "id": 2, "role": "a", "session": "s-1"},
        {"t": "end", "id": 2, "ok": True},
        {"t": "call", "id": 3, "parent": 1, "digest": "sub", "seq": 1, "ref": "m:g"},
    ]


async def test_a_journal_with_no_call_at_the_top_is_nothing_to_resume(
    tmp_path: Path,
) -> None:
    path = tmp_path / "run.jsonl"
    path.write_text('{"t": "journal", "v": 1}\n')
    journal, past = Journal.opened(path, asyncio.get_running_loop(), resume=True)
    journal.close()
    assert past is None


async def test_not_resuming_writes_over_what_was_there(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    earlier(path)
    journal, past = Journal.opened(path, asyncio.get_running_loop(), resume=False)
    journal.close()
    assert past is None
    assert lines(path) == [{"t": "journal", "v": 1}]


def test_an_empty_past_starts_ids_at_one() -> None:
    assert Past().next_id == 1
    assert Past().claim(0, "x", 0) is None


# ---------------------------------------------------------------------------- state


def test_state_without_a_journal_is_a_mapping_of_json() -> None:
    state = FlowStateImpl({}, None, 0)
    held = [1, 2]
    state["list"] = held
    state["tuple"] = (1, "a")
    state["dict"] = {1: "one"}
    held.append(3)
    assert state["list"] == [1, 2]
    assert state["tuple"] == [1, "a"]
    assert state["dict"] == {"1": "one"}
    assert len(state) == 3
    assert list(state) == ["list", "tuple", "dict"]
    assert "list" in state
    assert "nothing" not in state
    assert state.get("nothing", 7) == 7
    del state["list"]
    assert "list" not in state
    assert repr(state) == "FlowState({'tuple': [1, 'a'], 'dict': {'1': 'one'}})"
    with pytest.raises(KeyError):
        _ = state["list"]


@pytest.mark.parametrize("value", [object(), {1, 2}, b"bytes"])
def test_state_refuses_what_json_cannot_hold(value: object) -> None:
    state = FlowStateImpl({}, None, 0)
    with pytest.raises(StateNotSerializable):
        state["x"] = value
    assert "x" not in state


def test_state_refuses_a_key_that_is_not_text() -> None:
    state = FlowStateImpl({}, None, 0)
    with pytest.raises(StateNotSerializable, match="string"):
        state[1] = "x"  # pyright: ignore[reportArgumentType]


async def test_state_writes_land_in_the_journal(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    journal, _ = Journal.opened(path, asyncio.get_running_loop(), resume=False)
    state = FlowStateImpl({}, journal, 5)
    state["round"] = 2
    state["note"] = "é"
    del state["round"]
    journal.close()
    assert lines(path)[1:] == [
        {"t": "set", "id": 5, "key": "round", "value": 2},
        {"t": "set", "id": 5, "key": "note", "value": "é"},
        {"t": "del", "id": 5, "key": "round"},
    ]

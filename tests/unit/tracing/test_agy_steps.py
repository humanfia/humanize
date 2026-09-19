"""What an Antigravity conversation holds, read by field number rather than by name.

Antigravity ships no schema for what it writes, so the reader reaches its fields by
the numbers they are written under -- which is the half of the wire format that
describes itself. That makes two things worth a test that would be free anywhere
else: that the numbers are read as the things the corpus says they are, and that a
message which is not what was hoped is a session with less in it rather than a trace
that stops.

The steps here are built with the same encoder the format uses, so a test that
passes is one the real bytes would pass too.
"""

from __future__ import annotations

import json
import math
import pathlib
import sqlite3
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime.tracing.readers import _wire, agy

if TYPE_CHECKING:
    from hmz.runtime.tracing.session import Action, Session

SESSION = "03341787-6b66-49e0-bfb9-ac5c1a334eaf"
OTHER = "cc2a371c-331d-4498-98db-3ba074869f18"

#: When the one step below began and ended, as Antigravity stamps them.
_BEGAN, _ENDED = 1_789_718_889, 1_789_718_898

_EVER = (-math.inf, math.inf)


def _varint(value: int) -> bytes:
    """One base-128 number, as the wire writes it."""
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _field(number: int, value: int | bytes | str) -> bytes:
    """One field, as a varint where it is a number and as bytes where it is not."""
    if isinstance(value, int):
        return _varint(number << 3 | _wire.VARINT) + _varint(value)
    held = value.encode() if isinstance(value, str) else value
    return _varint(number << 3 | _wire.BYTES) + _varint(len(held)) + held


def _stamp(seconds: int, nanos: int = 0) -> bytes:
    """A `google.protobuf.Timestamp`."""
    return _field(1, seconds) + _field(2, nanos)


def _usage(held: dict[int, int] | None = None) -> bytes:
    """A step's usage message, under the numbers the corpus puts them at.

    A mapping rather than keywords, since the fields are numbers and a number is
    not a name anything could be passed under.
    """
    counts = {1: 1318, 2: 13296, 3: 103, 9: 102, 10: 1, **(held or {})}
    out = b"".join(_field(number, value) for number, value in sorted(counts.items()))
    return out + _field(7, "bot-fe84589c") + _field(11, "afGsaqbqM")


def _step(*, usage: bytes | None = _usage()) -> bytes:
    """One step's metadata: when it ran, and what it cost where it cost anything."""
    out = _field(1, _stamp(_BEGAN, 390_899_738)) + _field(6, _stamp(_ENDED))
    return out + (_field(9, usage) if usage is not None else b"")


def _home(
    tmp_path: pathlib.Path,
    *,
    steps: dict[int, bytes] | None = None,
    opened: dict[str, str] | None = None,
    summaries: bool = True,
) -> pathlib.Path:
    """An Antigravity home holding one conversation of one billed step."""
    home = tmp_path / "antigravity-cli"
    (home / agy.CONVERSATIONS).mkdir(parents=True, exist_ok=True)
    (home / "cache").mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(home / agy.CONVERSATIONS / f"{SESSION}.db")
    connection.execute(
        "create table steps (idx integer, step_type integer, status integer, "
        "metadata blob)"
    )
    for idx, metadata in (steps or {0: _step()}).items():
        connection.execute(
            "insert into steps (idx, step_type, status, metadata) values (?,?,?,?)",
            (idx, 15, 3, metadata),
        )
    connection.commit()
    connection.close()
    (home / "cache" / "last_conversations.json").write_text(
        json.dumps(opened if opened is not None else {"/work": SESSION}),
        encoding="utf-8",
    )
    if summaries:
        held = sqlite3.connect(home / "conversation_summaries.db")
        held.execute(
            "create table conversation_summaries (conversation_id text, title text, "
            "preview text, project_id text, agent_name text, "
            "parent_conversation_id text)"
        )
        held.execute(
            "insert into conversation_summaries values (?,?,?,?,?,?)",
            (
                SESSION,
                "cut the cycle count",
                "a preview",
                "default-cli-project",
                "",
                "",
            ),
        )
        held.commit()
        held.close()
    return home


def _collected(home: pathlib.Path, **held: Any) -> list[Session]:
    return agy.collect(
        home, held.get("workspace"), held.get("sessions"), held.get("window", _EVER)
    )


def _of(session: Session, category: str) -> list[Action]:
    return [action for action in session.actions if action.category == category]


def test_a_conversation_is_read_as_the_session_it_is(tmp_path: pathlib.Path) -> None:
    (session,) = _collected(_home(tmp_path))

    assert session.key == f"agy:{SESSION}"
    assert session.backend == "agy"
    assert session.ident == SESSION
    assert session.label == "main"
    assert session.parent is None
    assert "cut the cycle count" in session.title
    assert session.args["project_id"] == "default-cli-project"


def test_what_a_step_cost_is_read_off_the_numbers_it_is_written_under(
    tmp_path: pathlib.Path,
) -> None:
    """No schema ships with it, so the numbers are the names."""
    (session,) = _collected(_home(tmp_path))

    (call,) = _of(session, "llm")

    assert call.args["usage"] == {
        "toolPromptTokens": 1318,
        "promptTokens": 13296,
        "outputTokens": 103,
        "thoughtsTokens": 102,
        "answerTokens": 1,
    }
    assert call.args["model"] == "bot-fe84589c"
    assert call.start == pytest.approx(_BEGAN + 0.390_899_738)
    assert call.end == _ENDED


def test_the_output_is_the_whole_of_what_was_written(tmp_path: pathlib.Path) -> None:
    """Thinking and answer are counted apart and together, and the whole is field 3.

    A reader that added the two to the third would bill every step twice over.
    """
    (session,) = _collected(_home(tmp_path))

    (call,) = _of(session, "llm")
    usage = call.args["usage"]

    assert usage["thoughtsTokens"] + usage["answerTokens"] == usage["outputTokens"]


def test_a_cached_read_is_counted_beside_what_was_read(
    tmp_path: pathlib.Path,
) -> None:
    """The prompt comes down by what the cache goes up, so both are what it read."""
    cached = _usage({2: 5303, 5: 8123, 3: 30, 9: 0, 10: 30})
    home = _home(tmp_path, steps={0: _step(usage=cached)})

    (session,) = _collected(home)

    (call,) = _of(session, "llm")
    assert call.args["usage"]["promptTokens"] == 5303
    assert call.args["usage"]["cachedTokens"] == 8123


def test_a_step_that_ran_no_model_is_an_event_rather_than_a_call(
    tmp_path: pathlib.Path,
) -> None:
    """The person's own turn, or a tool coming back: neither is billed."""
    home = _home(tmp_path, steps={0: _step(usage=None), 1: _step()})

    (session,) = _collected(home)

    assert len(_of(session, "llm")) == 1
    assert len(_of(session, "event")) == 1


def test_which_workspace_a_conversation_belongs_to_is_read_off_the_cache(
    tmp_path: pathlib.Path,
) -> None:
    """It is not in the conversation, so the map beside it is what is asked."""
    home = _home(tmp_path, opened={"/work": SESSION, "/elsewhere": OTHER})

    assert len(_collected(home, workspace=pathlib.Path("/work"))) == 1
    assert _collected(home, workspace=pathlib.Path("/elsewhere")) == []
    assert len(_collected(home, workspace=None)) == 1


def test_only_the_sessions_asked_for_are_read(tmp_path: pathlib.Path) -> None:
    home = _home(tmp_path)

    assert len(_collected(home, sessions=(SESSION[:8],))) == 1
    assert _collected(home, sessions=("no-such-conversation",)) == []


def test_nothing_outside_the_window_is_read(tmp_path: pathlib.Path) -> None:
    home = _home(tmp_path)

    assert _collected(home, window=(_BEGAN + 100, _BEGAN + 200))[0].actions == []


def test_a_home_with_no_conversations_is_a_backend_with_nothing_to_say(
    tmp_path: pathlib.Path,
) -> None:
    assert agy.collect(tmp_path / "nowhere", None, None, _EVER) == []


def test_a_conversation_nothing_can_be_read_out_of_is_not_a_trace_that_stops(
    tmp_path: pathlib.Path,
) -> None:
    """A file under that name that is not a database, and a home with no cache."""
    home = _home(tmp_path, summaries=False)
    (home / agy.CONVERSATIONS / "9999.db").write_text(
        "not a database", encoding="utf-8"
    )
    (home / "cache" / "last_conversations.json").write_text("{", encoding="utf-8")

    collected = _collected(home)

    assert {one.ident for one in collected} == {SESSION, "9999"}
    assert next(one for one in collected if one.ident == "9999").actions == []

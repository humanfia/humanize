"""What an opencode database holds, and what a reader has to make of each of it.

The first of these whose sessions are rows rather than lines, which is most of what
is worth a test here: a conversation is three tables joined rather than a file read
in order, a tool call is one row holding its input, its output and the moments it
ran between rather than two records answering one another, and what a turn cost is
the message's own rather than anything a part says.

Written against a database this builds itself, with the columns opencode 1.18.30
uses, so that a schema which moved under it is a failing test rather than a backend
that quietly reads back as having done nothing.
"""

from __future__ import annotations

import json
import math
import sqlite3
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime.tracing.readers import opencode

if TYPE_CHECKING:
    import pathlib

    from hmz.runtime.tracing.session import Action, Session

SESSION = "ses_f4c4d5b09ffelxDPbkVWSJLw2U"
CHILD = "ses_aa11bb22ccfeZZZZZZZZZZZZZZ"

#: The moment a conversation opens, in the milliseconds opencode times by.
_BEGAN = 1_789_721_224_000

#: The whole of time, for a test that is not about the window.
_EVER = (-math.inf, math.inf)

_SCHEMA = """
create table session (
  id text primary key, project_id text, workspace_id text, parent_id text,
  slug text, directory text, path text, title text, version text,
  share_url text, summary_additions int, summary_deletions int,
  summary_files int, summary_diffs text, metadata text, cost real,
  tokens_input int, tokens_output int, tokens_reasoning int,
  tokens_cache_read int, tokens_cache_write int, revert text,
  permission text, agent text, model text, time_created int,
  time_updated int, time_compacting int, time_archived int
);
create table message (
  id text primary key, session_id text, time_created int, time_updated int,
  data text
);
create table part (
  id text primary key, message_id text, session_id text, time_created int,
  time_updated int, data text
);
"""


def _tokens(**held: Any) -> dict[str, Any]:
    """One message's token counts, nested the way opencode nests its cache."""
    return {
        "total": 7950,
        "input": 6134,
        "output": 24,
        "reasoning": 0,
        "cache": {"write": 0, "read": 1792},
        **held,
    }


def _database(
    home: pathlib.Path,
    *,
    directory: str = "/work",
    rows: list[tuple[str, int, dict[str, Any], list[dict[str, Any]]]] | None = None,
    child: bool = False,
) -> pathlib.Path:
    """A database holding one conversation, and a sub-session where asked."""
    home.mkdir(parents=True, exist_ok=True)
    path = home / opencode.DATABASE
    connection = sqlite3.connect(path)
    connection.executescript(_SCHEMA)
    named = [(SESSION, None), *([(CHILD, SESSION)] if child else [])]
    for ident, parent in named:
        connection.execute(
            "insert into session (id, parent_id, directory, title, version, "
            "agent, model, time_created) values (?,?,?,?,?,?,?,?)",
            (
                ident,
                parent,
                directory,
                "cut the cycle count",
                "1.18.30",
                "build",
                json.dumps({"modelID": "big-pickle", "providerID": "opencode"}),
                _BEGAN,
            ),
        )
    for index, (role, at, data, parts) in enumerate(rows or []):
        message_id = f"msg_{index}"
        connection.execute(
            "insert into message (id, session_id, time_created, time_updated, "
            "data) values (?,?,?,?,?)",
            (
                message_id,
                SESSION,
                at,
                at + 100,
                json.dumps({"role": role, **data}),
            ),
        )
        for offset, part in enumerate(parts):
            connection.execute(
                "insert into part (id, message_id, session_id, time_created, "
                "data) values (?,?,?,?,?)",
                (
                    f"prt_{index}_{offset}",
                    message_id,
                    SESSION,
                    at + offset,
                    json.dumps(part),
                ),
            )
    connection.commit()
    connection.close()
    return path


@pytest.fixture
def home(tmp_path: pathlib.Path) -> pathlib.Path:
    """A share directory whose database holds one worked conversation."""
    where = tmp_path / "opencode"
    _database(
        where,
        rows=[
            ("user", _BEGAN, {}, [{"type": "text", "text": "cut the cycle count"}]),
            (
                "assistant",
                _BEGAN + 1000,
                {
                    "modelID": "big-pickle",
                    "providerID": "opencode",
                    "tokens": _tokens(),
                },
                [
                    {"type": "step-start"},
                    {
                        "type": "reasoning",
                        "text": "read the kernel first",
                        "time": {"start": _BEGAN + 1100, "end": _BEGAN + 1200},
                    },
                    {
                        "type": "tool",
                        "tool": "read",
                        "callID": "call-1",
                        "state": {
                            "status": "completed",
                            "input": {"filePath": "perf_takehome.py"},
                            "output": "def kernel(): ...",
                            "time": {"start": _BEGAN + 1300, "end": _BEGAN + 1500},
                        },
                    },
                    {"type": "text", "text": "done"},
                    {"type": "step-finish", "reason": "stop", "tokens": _tokens()},
                ],
            ),
        ],
    )
    return where


def _collected(home: pathlib.Path, **held: Any) -> list[Session]:
    """Every session of ``home``, over the whole of time unless told otherwise."""
    return opencode.collect(
        home, held.get("workspace"), held.get("sessions"), held.get("window", _EVER)
    )


def _of(session: Session, category: str) -> list[Action]:
    """Every slice of one kind, in the order the rows gave them."""
    return [action for action in session.actions if action.category == category]


def test_a_conversation_is_read_out_of_the_rows_that_hold_it(
    home: pathlib.Path,
) -> None:
    (session,) = _collected(home)

    assert session.key == f"opencode:{SESSION}"
    assert session.backend == "opencode"
    assert session.ident == SESSION
    assert session.label == "main"
    assert session.parent is None
    assert session.args["cwd"] == "/work"
    assert session.args["version"] == "1.18.30"
    assert session.args["model"] == "big-pickle"
    assert session.args["provider"] == "opencode"


def test_what_a_turn_cost_is_the_message_rather_than_the_step(
    home: pathlib.Path,
) -> None:
    """Both say it, and counting both would bill one turn twice."""
    (session,) = _collected(home)

    (call,) = _of(session, "llm")

    assert call.args["usage"] == _tokens()
    assert call.args["model"] == "big-pickle"


def test_a_tool_call_is_one_row_holding_its_whole_life(home: pathlib.Path) -> None:
    """Not two records answering one another, as every other backend here writes."""
    (session,) = _collected(home)

    (call,) = _of(session, "tool")

    assert call.args["tool"] == "read"
    assert call.args["input"] == {"filePath": "perf_takehome.py"}
    assert call.args["output"] == "def kernel(): ..."
    assert call.args["status"] == "completed"
    assert "unfinished" not in call.args
    assert call.start == (_BEGAN + 1300) / 1000
    assert call.end == (_BEGAN + 1500) / 1000


def test_a_call_that_had_not_finished_says_so(tmp_path: pathlib.Path) -> None:
    """A row is rewritten in place, so a running call is one caught mid-write."""
    where = tmp_path / "opencode"
    _database(
        where,
        rows=[
            (
                "assistant",
                _BEGAN,
                {"modelID": "big-pickle", "tokens": _tokens()},
                [
                    {
                        "type": "tool",
                        "tool": "bash",
                        "callID": "call-1",
                        "state": {"status": "running", "input": {"command": "ls"}},
                    }
                ],
            )
        ],
    )

    (session,) = _collected(where)

    (call,) = _of(session, "tool")
    assert call.args["unfinished"] is True


def test_reasoning_is_the_call_and_text_is_something_said(
    home: pathlib.Path,
) -> None:
    (session,) = _collected(home)

    (call,) = _of(session, "llm")
    assert call.args["thinking"] == "read the kernel first"
    assert [said.args["text"] for said in _of(session, "message")] == ["done"]


def test_the_brackets_around_a_call_are_not_slices_of_their_own(
    home: pathlib.Path,
) -> None:
    """`step-start` and `step-finish` bracket a call rather than holding any of it."""
    (session,) = _collected(home)

    assert [action.category for action in session.actions] == [
        "turn",
        "llm",
        "tool",
        "message",
    ]


def test_a_sub_session_is_hung_off_the_one_that_started_it(
    tmp_path: pathlib.Path,
) -> None:
    where = tmp_path / "opencode"
    _database(where, child=True)

    collected = _collected(where)

    child = next(one for one in collected if one.ident == CHILD)
    assert child.parent == f"opencode:{SESSION}"
    assert child.label == "subagent"


def test_a_session_of_another_workspace_is_not_this_workspace(
    home: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """The session row says its directory, so a workspace is asked of that."""
    assert len(_collected(home, workspace=None)) == 1
    assert _collected(home, workspace=tmp_path / "nowhere") == []


def test_only_the_sessions_asked_for_are_read(home: pathlib.Path) -> None:
    assert len(_collected(home, sessions=(SESSION[:12],))) == 1
    assert _collected(home, sessions=("ses_nosuchsession",)) == []


def test_nothing_outside_the_window_is_read(home: pathlib.Path) -> None:
    began = _BEGAN / 1000

    (session,) = _collected(home, window=(began + 0.5, began + 2))

    assert _of(session, "turn") == []
    assert len(_of(session, "llm")) == 1


def test_a_home_with_no_database_is_a_backend_with_nothing_to_say(
    tmp_path: pathlib.Path,
) -> None:
    """A machine opencode was never run on holds no database to read."""
    assert opencode.collect(tmp_path / "nowhere", None, None, _EVER) == []


def test_a_database_nothing_can_be_read_out_of_is_not_a_trace_that_stops(
    tmp_path: pathlib.Path,
) -> None:
    """A file under that name that is not one is a backend with nothing to say."""
    where = tmp_path / "opencode"
    where.mkdir()
    (where / opencode.DATABASE).write_text("not a database", encoding="utf-8")

    assert opencode.collect(where, None, None, _EVER) == []

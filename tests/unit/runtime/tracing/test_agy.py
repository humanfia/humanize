from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from hmz.runtime.tracing.readers import agy
from tests.unit.runtime.tracing.logs import ALL, field, stamp, varint

T0 = 1_767_225_600
WORKSPACE = "/work/repo"


def usage() -> bytes:
    counts = {1: 1300, 2: 100, 3: 30, 5: 50, 9: 10, 10: 20}
    held = b"".join(field(number, value) for number, value in counts.items())
    return field(9, held + field(7, "gemini-x") + field(11, "resp-1"))


def conversation(home: Path, ident: str, steps: list[tuple[str, str, Any]]) -> Path:
    path = home / agy.CONVERSATIONS / f"{ident}.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("create table steps (idx, step_type, status, metadata)")
        connection.executemany(
            "insert into steps values (?, ?, ?, ?)",
            [(at, kind, status, held) for at, (kind, status, held) in enumerate(steps)],
        )
    connection.close()
    return path


def summaries(home: Path, rows: list[dict[str, Any]]) -> None:
    with sqlite3.connect(home / "conversation_summaries.db") as connection:
        connection.execute(
            "create table conversation_summaries (conversation_id, title, "
            "parent_conversation_id, project_id, agent_name, preview)"
        )
        for row in rows:
            names = ", ".join(row)
            connection.execute(
                f"insert into conversation_summaries ({names}) values "  # noqa: S608
                f"({', '.join('?' for _ in row)})",
                list(row.values()),
            )
    connection.close()


def opened(home: Path, held: object) -> None:
    (home / "cache").mkdir(parents=True, exist_ok=True)
    (home / "cache" / "last_conversations.json").write_text(json.dumps(held))


def test_reads_steps_by_field_number(tmp_path: Path) -> None:
    conversation(
        tmp_path,
        "conv-abcdefgh",
        [
            ("USER", "DONE", stamp(1, T0 + 1) + stamp(6, T0 + 2)),
            (
                "PLAN",
                "DONE",
                # a fixed64 and a fixed32 field the reader steps over, then the times
                varint(4 << 3 | 1)
                + b"\0" * 8
                + varint(4 << 3 | 5)
                + b"\0" * 4
                + stamp(1, T0 + 3, 500_000_000)
                + stamp(6, T0 + 5)
                + usage(),
            ),
            ("TOOL", "DONE", stamp(1, T0 + 6)),
            ("TEXT", "DONE", "not bytes"),
            ("NOTIME", "DONE", field(9, b"")),
            ("CUT", "DONE", stamp(1, T0 + 7)[:-1]),
        ],
    )
    summaries(
        tmp_path,
        [
            {
                "conversation_id": "conv-abcdefgh",
                "title": "Build the thing",
                "project_id": "proj",
                "agent_name": "",
            }
        ],
    )
    [session] = agy.collect(tmp_path, None, None, ALL)
    assert (session.key, session.backend, session.label, session.parent) == (
        "agy:conv-abcdefgh",
        "agy",
        "main",
        None,
    )
    assert session.title == "conv-abc · Build the thing"
    assert session.args["model"] == "gemini-x"
    assert session.args["project_id"] == "proj"
    assert "agent_name" not in session.args

    user, think, tool = session.actions
    assert (user.name, user.category, user.start, user.end) == (
        "step 0",
        "event",
        T0 + 1,
        T0 + 2,
    )
    assert user.args == {"step_type": "USER", "status": "DONE"}
    assert (think.name, think.category, think.start, think.end) == (
        "think",
        "llm",
        T0 + 3.5,
        T0 + 5,
    )
    assert think.args == {
        "model": "gemini-x",
        "response": "resp-1",
        "usage": {
            "toolPromptTokens": 1300,
            "promptTokens": 100,
            "outputTokens": 30,
            "cachedTokens": 50,
            "thoughtsTokens": 10,
            "answerTokens": 20,
        },
        "step_type": "PLAN",
    }
    assert (tool.start, tool.end) == (T0 + 6, T0 + 6)


def test_nested_conversations_and_the_workspace_map(tmp_path: Path) -> None:
    conversation(tmp_path, "root", [("U", "D", stamp(1, T0 + 1))])
    conversation(tmp_path, "nested", [])
    conversation(tmp_path, "lonely", [])
    summaries(
        tmp_path,
        [
            {"conversation_id": "nested", "parent_conversation_id": "root"},
            {"conversation_id": "lonely", "parent_conversation_id": "gone"},
        ],
    )
    opened(tmp_path, {WORKSPACE: "root", "/other": "nested"})
    found = {s.ident: s for s in agy.collect(tmp_path, None, None, ALL)}
    assert (found["nested"].label, found["nested"].parent) == ("subagent", "agy:root")
    assert (found["lonely"].label, found["lonely"].parent) == ("subagent", None)
    assert found["root"].title == "root"
    assert [s.ident for s in agy.collect(tmp_path, Path(WORKSPACE), None, ALL)] == [
        "root"
    ]
    assert agy.collect(tmp_path, Path("/nobody"), None, ALL) == []
    assert [s.ident for s in agy.collect(tmp_path, None, ("agy:lon",), ALL)] == [
        "lonely"
    ]


@pytest.mark.parametrize("cache", ["{torn", "[1, 2]"])
def test_damaged_side_files_are_nothing_said(tmp_path: Path, cache: str) -> None:
    conversation(tmp_path, "c", [("U", "D", stamp(1, T0 + 1))])
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "last_conversations.json").write_text(cache)
    (tmp_path / "conversation_summaries.db").write_bytes(
        b"not sqlite, not even a little bit.."
    )
    [session] = agy.collect(tmp_path, None, None, ALL)
    assert session.title == "c"
    assert agy.collect(tmp_path, Path(WORKSPACE), None, ALL) == []


def test_unreadable_conversation_and_missing_home(tmp_path: Path) -> None:
    assert agy.collect(tmp_path, None, None, ALL) == []
    folder = tmp_path / agy.CONVERSATIONS
    folder.mkdir()
    (folder / "bad.db").write_bytes(b"garbage garbage garbage garbage garbage..")
    sqlite3.connect(folder / "empty.db").close()
    found = agy.collect(tmp_path, None, None, ALL)
    assert [(s.ident, s.actions) for s in found] == [("bad", []), ("empty", [])]


def test_window_cuts_steps(tmp_path: Path) -> None:
    conversation(
        tmp_path, "c", [("A", "D", stamp(1, T0 + 1)), ("B", "D", stamp(1, T0 + 50))]
    )
    [session] = agy.collect(tmp_path, None, None, (T0, T0 + 10))
    assert [a.args["step_type"] for a in session.actions] == ["A"]


@pytest.mark.parametrize(
    "tail",
    [
        # a group, whose end cannot be known without a schema
        pytest.param(varint(8 << 3 | 3), id="group"),
        pytest.param(varint(8 << 3) + b"\xff" * 11, id="varint-too-wide"),
        pytest.param(varint(8 << 3) + b"\xff", id="varint-cut-short"),
    ],
)
def test_walk_stops_where_the_bytes_stop_making_sense(
    tmp_path: Path, tail: bytes
) -> None:
    conversation(tmp_path, "c", [("A", "D", stamp(1, T0 + 1) + tail + usage())])
    [session] = agy.collect(tmp_path, None, None, ALL)
    [step] = session.actions
    assert (step.category, step.start) == ("event", T0 + 1)


def test_a_model_name_that_is_not_text_reads_as_none(tmp_path: Path) -> None:
    broken = field(9, field(2, 5) + field(7, b"\xff\xfe"))
    conversation(tmp_path, "c", [("A", "D", stamp(1, T0 + 1) + broken)])
    [session] = agy.collect(tmp_path, None, None, ALL)
    [think] = session.actions
    assert think.args["model"] == ""
    assert think.args["usage"] == {"promptTokens": 5}
    assert "model" not in session.args

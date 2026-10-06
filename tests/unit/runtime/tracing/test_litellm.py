from __future__ import annotations

from pathlib import Path
from typing import Any

from hmz.runtime.tracing.readers import litellm
from tests.unit.runtime.tracing.logs import ALL, jsonl

T0 = 1_767_225_600
WORKSPACE = "/work/repo"


def msg(at: float, role: str, content: Any, /, **fields: Any) -> dict[str, Any]:
    return {
        "type": "message",
        "timestamp": T0 + at,
        "message": {"role": role, "content": content, **fields},
    }


def header(ident: str, **extra: Any) -> dict[str, Any]:
    return {"type": "session", "id": ident, "cwd": WORKSPACE, "model": "gpt-x", **extra}


def test_reads_a_conversation(tmp_path: Path) -> None:
    jsonl(
        tmp_path / "sessions" / "a.jsonl",
        [
            header("session-abcdefghij"),
            {"type": "message", "timestamp": True},
            {"type": "other", "timestamp": T0},
            msg(1, "user", "hello"),
            msg(
                2, "assistant", "hi", model="gpt-x", usage={"in": 1}, reasoning="greet"
            ),
            msg(2.5, "system", "ignored"),
            msg(3, "user", "bye"),
            msg(4, "assistant", ["not text"]),
            msg(5, "user", "open"),
        ],
    )
    [session] = litellm.collect(tmp_path, None, None, ALL)
    assert (session.key, session.label, session.parent) == (
        "litellm:session-abcdefghij",
        "main",
        None,
    )
    assert session.title == "abcdefgh · hello"
    assert (session.args["model"], session.args["cwd"]) == ("gpt-x", WORKSPACE)
    shape = [(a.category, a.name, a.start - T0, a.end - T0) for a in session.actions]
    assert shape == [
        ("llm", "think: greet", 1, 2),
        ("message", "say: hi", 2, 2),
        ("turn", "turn: hello", 1, 2),
        ("llm", "think", 3, 4),
        ("message", "say: ", 4, 4),
        ("turn", "turn: bye", 3, 4),
        ("turn", "turn: open", 5, 5),
    ]
    first = session.actions[0]
    assert first.args == {"model": "gpt-x", "usage": {"in": 1}, "thinking": "greet"}


def test_answer_without_a_prompt(tmp_path: Path) -> None:
    jsonl(tmp_path / "sessions" / "a.jsonl", [header("s"), msg(1, "assistant", "x")])
    [session] = litellm.collect(tmp_path, None, None, ALL)
    assert [(a.name, a.start) for a in session.actions] == [
        ("think", T0 + 1),
        ("say: x", T0 + 1),
    ]


def test_forks_workspaces_and_damaged_headers(tmp_path: Path) -> None:
    folder = tmp_path / "sessions"
    jsonl(folder / "a.jsonl", [header("root")])
    jsonl(folder / "b.jsonl", [header("fork", parent="root")])
    jsonl(folder / "c.jsonl", [header("far", cwd="/else")])
    jsonl(folder / "d.jsonl", ["{torn"])
    jsonl(folder / "e.jsonl", ["[1]"])
    jsonl(folder / "f.jsonl", [{"type": "message", "id": "nope"}])
    jsonl(folder / "g.jsonl", [header("")])
    found = {s.ident: s for s in litellm.collect(tmp_path, Path(WORKSPACE), None, ALL)}
    assert set(found) == {"root", "fork"}
    assert found["fork"].parent == "litellm:root"
    assert [s.ident for s in litellm.collect(tmp_path, None, ("fa",), ALL)] == ["far"]
    assert litellm.collect(tmp_path / "none", None, None, ALL) == []


def test_window_cuts_records(tmp_path: Path) -> None:
    jsonl(
        tmp_path / "sessions" / "a.jsonl",
        [header("s"), msg(1, "user", "a"), msg(20, "user", "b")],
    )
    [session] = litellm.collect(tmp_path, None, None, (T0 + 10, T0 + 30))
    assert [a.name for a in session.actions] == ["turn: b"]

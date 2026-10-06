from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hmz.runtime.tracing.readers import dsh
from tests.unit.runtime.tracing.logs import ALL, jsonl

T0 = 1_767_225_600
WORKSPACE = "/work/repo"


def ev(at: float, kind: str, /, **data: Any) -> dict[str, Any]:
    return {"time": (T0 + at) * 1000, "type": kind, "data": data}


def header(ident: str, **extra: Any) -> dict[str, Any]:
    return {"type": "session", "id": ident, "cwd": WORKSPACE, "version": 1, **extra}


def log(home: Path, ident: str, rows: list[dict[str, Any] | str]) -> Path:
    return jsonl(home / "sessions" / "2026" / ident / "session.jsonl", rows)


def test_reads_a_session(tmp_path: Path) -> None:
    log(
        tmp_path,
        "session-abcdefghij",
        [
            header("session-abcdefghij"),
            {"time": True, "type": "turn/start"},
            ev(0, "session/title", title="Fixing"),
            ev(
                0.1,
                "request/header",
                header={"config": {"model": "ds", "reasoningEffort": "max"}},
            ),
            ev(1, "turn/start", turn=1),
            ev(1, "user/message", source={"kind": "system"}, content="ignored"),
            ev(1, "user/message", source={"kind": "user"}, content=""),
            ev(1.1, "user/message", source={"kind": "user"}, content="fix it"),
            ev(2, "step/start", turn=1, step=1),
            ev(
                3,
                "assistant/message",
                turn=1,
                step=1,
                usage={"in": 3},
                message={
                    "source": {"provider": "deepseek", "model": "other"},
                    "content": [
                        {"type": "reasoning", "text": "think"},
                        {"type": "text", "text": "a"},
                        {"type": "text", "text": "b"},
                        {"type": "text", "text": ""},
                    ],
                },
            ),
            ev(
                3.5,
                "tool/call",
                name="bash",
                callId="c1",
                arguments=json.dumps({"command": "ls"}),
            ),
            ev(
                4,
                "tool/result",
                error={"code": 1},
                message={
                    "source": {"callId": "c1"},
                    "content": [
                        {"type": "tool-result", "content": "out", "isError": False},
                        {"type": "other", "content": "skip"},
                    ],
                },
            ),
            ev(4.5, "tool/call", name="edit", callId="c2", arguments="raw text"),
            ev(5, "step/end", turn=1, step=1),
            ev(6, "turn/end", reason="done"),
            ev(7, "turn/start", turn=2),
        ],
    )
    [session] = dsh.collect(tmp_path, None, None, ALL)
    assert (session.key, session.label, session.parent) == (
        "dsh:session-abcdefghij",
        "main",
        None,
    )
    assert session.title == "abcdefgh · Fixing"
    assert session.args["model"] == "ds"
    assert session.args["effort"] == "max"
    assert session.args["provider"] == "deepseek"
    assert session.args["cwd"] == WORKSPACE
    assert "title" not in session.args

    by = {(a.category, a.name): a for a in session.actions}
    turn = by["turn", "turn: fix it"]
    assert (turn.start, turn.end) == (T0 + 1, T0 + 6)
    assert turn.args["reason"] == "done"
    think = by["llm", "think: think"]
    assert (think.start, think.end) == (T0 + 2, T0 + 3)
    assert think.args["usage"] == {"in": 3}
    assert think.args["thinking"] == "think"
    assert by["message", "say: ab"].args["text"] == "ab"
    bash = by["tool", "bash: ls"]
    assert (bash.start, bash.end) == (T0 + 3.5, T0 + 4)
    assert bash.args["output"] == "out"
    assert bash.args["error"] is True
    assert bash.args["failure"] == {"code": 1}
    edit = by["tool", "edit: raw text"]
    assert edit.args["unfinished"] is True
    assert by["turn", "turn"].start == T0 + 7


def test_message_without_a_step_opens_one(tmp_path: Path) -> None:
    log(
        tmp_path,
        "s",
        [
            header("s"),
            ev(1, "turn/start", turn=1),
            ev(
                2,
                "assistant/message",
                turn=1,
                step=9,
                content=[{"type": "text", "text": "x"}],
            ),
        ],
    )
    [session] = dsh.collect(tmp_path, None, None, ALL)
    [think] = [a for a in session.actions if a.category == "llm"]
    assert (think.start, think.end) == (T0 + 1, T0 + 2)
    assert think.args == {"turn": 1, "step": 9}
    assert any(a.name == "say: x" for a in session.actions)


def test_descendants_and_labels(tmp_path: Path) -> None:
    log(tmp_path, "p", [header("p")])
    log(
        tmp_path,
        "c",
        [
            header("c", parentSession="p"),
            ev(1, "subagent/descriptor", label="explorer"),
        ],
    )
    log(tmp_path, "d", [header("d", parentSession="c")])
    log(tmp_path, "z", [header("z")])
    found = {s.key: s for s in dsh.collect(tmp_path, None, ("p",), ALL)}
    assert set(found) == {"dsh:p", "dsh:c", "dsh:d"}
    assert (found["dsh:c"].label, found["dsh:c"].parent) == ("explorer", "dsh:p")
    assert (found["dsh:d"].label, found["dsh:d"].parent) == ("subagent", "dsh:c")


def test_skips_damaged_headers_and_other_workspaces(tmp_path: Path) -> None:
    log(tmp_path, "a", ["{torn"])
    log(tmp_path, "b", [{"type": "other", "id": "b"}])
    log(tmp_path, "c", ["[1]"])
    log(tmp_path, "d", [{"type": "session", "id": ""}])
    log(tmp_path, "e", [{"type": "session", "id": "e", "cwd": "/else"}])
    log(tmp_path, "f", [header("f")])
    assert [s.ident for s in dsh.collect(tmp_path, None, None, ALL)] == ["e", "f"]
    assert [s.ident for s in dsh.collect(tmp_path, Path(WORKSPACE), None, ALL)] == ["f"]
    assert dsh.collect(tmp_path / "none", None, None, ALL) == []

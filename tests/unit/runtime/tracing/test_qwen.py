from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from hmz.runtime.tracing.readers import qwen
from tests.unit.runtime.tracing.logs import ALL, jsonl

T0 = 1_767_225_600
WORKSPACE = "/work/repo"


def iso(offset: float) -> str:
    return datetime.datetime.fromtimestamp(T0 + offset, datetime.UTC).isoformat()


def rec(
    at: float, kind: str, /, parts: list[Any] | None = None, **fields: Any
) -> dict[str, Any]:
    return {
        "type": kind,
        "timestamp": iso(at),
        "message": {"parts": parts or []},
        **fields,
    }


def log(
    home: Path, ident: str, rows: list[dict[str, Any] | str], folder: str = "-work-repo"
) -> Path:
    return jsonl(home / "projects" / folder / "chats" / f"{ident}.jsonl", rows)


def test_reads_a_chat(tmp_path: Path) -> None:
    log(
        tmp_path,
        "abcdefghij",
        [
            {"type": "user", "timestamp": "nope"},
            {"type": "user"},
            rec(
                1,
                "user",
                [{"text": "fix"}, {"text": "it"}, "junk"],
                cwd=WORKSPACE,
                version="0.23",
            ),
            rec(
                2,
                "assistant",
                [
                    {"text": "plan", "thought": True},
                    {"text": "ok"},
                    {
                        "functionCall": {
                            "id": "c1",
                            "name": "run",
                            "args": {"command": "ls"},
                        }
                    },
                    {"functionCall": {"id": "c2", "name": "read", "args": {}}},
                    {"other": 1},
                ],
                model="qwen3",
                usageMetadata={"promptTokenCount": 3},
            ),
            rec(
                3,
                "tool_result",
                [
                    {"functionResponse": {"id": "c1", "response": {"output": "a"}}},
                    {"functionResponse": {"id": "nobody"}},
                ],
                toolCallResult={"error": "boom"},
            ),
            rec(3.5, "assistant", model="qwen-later"),
            rec(4, "system", subtype="ui_telemetry", systemPayload={"k": 1}, other=2),
            rec(5, "user", [{"text": "next"}]),
        ],
    )
    [session] = qwen.collect(tmp_path, None, None, ALL)
    assert (session.key, session.label, session.parent) == (
        "qwen:abcdefghij",
        "main",
        None,
    )
    assert session.title == "abcdefgh · fix it"
    assert session.args["cwd"] == WORKSPACE
    assert session.args["model"] == "qwen3"

    by = {(a.category, a.name): a for a in session.actions}
    turn = by["turn", "turn: fix it"]
    assert turn.args["prompt"] == "fix\nit"
    assert (turn.start, turn.end) == (T0 + 1, T0 + 5)
    think = by["llm", "think: plan"]
    assert (think.start, think.end) == (T0 + 1, T0 + 2)
    assert think.args["usage"] == {"promptTokenCount": 3}
    assert by["message", "say: ok"].start == T0 + 2
    run = by["tool", "run: ls"]
    assert (run.start, run.end, run.args["output"]) == (T0 + 2, T0 + 3, "a")
    assert run.args["error"] is True
    assert run.args["result"] == {"error": "boom"}
    assert by["tool", "read"].args["unfinished"] is True
    event = by["event", "system: ui_telemetry"]
    assert event.args == {"subtype": "ui_telemetry", "systemPayload": {"k": 1}}


def test_workspace_folder_and_sessions_narrow(tmp_path: Path) -> None:
    log(tmp_path, "here", [])
    log(tmp_path, "there", [], folder="-else")
    assert [s.ident for s in qwen.collect(tmp_path, Path(WORKSPACE), None, ALL)] == [
        "here"
    ]
    assert [s.ident for s in qwen.collect(tmp_path, None, ("the",), ALL)] == ["there"]
    assert len(qwen.collect(tmp_path, None, None, ALL)) == 2


def test_window_cuts_records(tmp_path: Path) -> None:
    log(
        tmp_path,
        "s",
        [rec(1, "user", [{"text": "a"}]), rec(20, "user", [{"text": "b"}])],
    )
    [session] = qwen.collect(tmp_path, None, None, (T0 + 10, T0 + 30))
    assert [a.name for a in session.actions] == ["turn: b"]

from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path
from typing import Any

from hmz.runtime.tracing.readers import mcode
from tests.unit.runtime.tracing.logs import ALL, jsonl

T0 = 1_767_225_600
WORKSPACE = "/work/repo"


def msg(at: float, role: str, /, **fields: Any) -> dict[str, Any]:
    return {"message": {"timestamp": (T0 + at) * 1000, "role": role, **fields}}


def folder_of(ident: str) -> str:
    encoded = base64.urlsafe_b64encode(ident.encode()).decode().rstrip("=")
    return f"20260101T000000-session_{encoded}"


def log(home: Path, ident: str, rows: list[dict[str, Any] | str]) -> Path:
    path = home / "v2" / "sessions" / "2026" / "01" / "01" / folder_of(ident)
    return jsonl(path / "messages.jsonl", rows)


def database(home: Path, rows: list[tuple[str, str]]) -> None:
    path = home / "v2" / "sqlite" / "runtime-state.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "create table local_runtime_sessions (session_id text, record_json text)"
        )
        connection.executemany("insert into local_runtime_sessions values (?, ?)", rows)
    connection.close()


def test_reads_a_session(tmp_path: Path) -> None:
    log(
        tmp_path,
        "sess-abcdefghijkl",
        [
            {"message": {"timestamp": True, "role": "user"}},
            msg(
                1,
                "user",
                content="<reminder>x</reminder>fix it",
                canonicalTextRange={"startOffset": 22, "endOffset": 28},
            ),
            msg(
                2,
                "assistant",
                provider="minimax",
                model="m2",
                usage={"input": 3},
                stopReason="toolUse",
                content=[
                    {"type": "thinking", "thinking": "plan"},
                    {"type": "text", "text": "ok"},
                    {
                        "type": "toolCall",
                        "id": "c1",
                        "name": "bash",
                        "arguments": {"command": "ls"},
                    },
                    {"type": "toolCall", "id": "c2", "name": "read", "arguments": {}},
                    "junk",
                ],
            ),
            msg(
                3,
                "toolResult",
                toolCallId="c1",
                content=[{"type": "text", "text": "a"}],
            ),
            msg(4, "assistant", model="m3", content="plain"),
            msg(
                5,
                "user",
                content="next",
                canonicalTextRange={"startOffset": 3, "endOffset": 99},
            ),
        ],
    )
    database(
        tmp_path,
        [
            ("sess-abcdefghijkl", json.dumps({"workspaceDir": WORKSPACE})),
            ("other", "not json"),
        ],
    )
    [session] = mcode.collect(tmp_path, None, None, ALL)
    assert (session.key, session.label, session.parent) == (
        "mcode:sess-abcdefghijkl",
        "main",
        None,
    )
    assert session.title == "sess-abcdefg · fix it"
    assert session.args["cwd"] == WORKSPACE
    assert (session.args["model"], session.args["provider"]) == ("m2", "minimax")

    by = {(a.category, a.name): a for a in session.actions}
    turn = by["turn", "turn: fix it"]
    assert (turn.start, turn.end) == (T0 + 1, T0 + 5)
    think = by["llm", "think: plan"]
    assert (think.start, think.end) == (T0 + 1, T0 + 2)
    assert think.args["usage"] == {"input": 3}
    assert think.args["stop"] == "toolUse"
    assert by["message", "say: ok"].start == T0 + 2
    bash = by["tool", "bash: ls"]
    assert (bash.start, bash.end, bash.args["output"]) == (T0 + 2, T0 + 3, "a")
    assert by["tool", "read"].args["unfinished"] is True
    assert by["turn", "turn: next"].args["prompt"] == "next"


def test_workspace_comes_from_the_database(tmp_path: Path) -> None:
    log(tmp_path, "here", [])
    log(tmp_path, "unknown", [])
    database(tmp_path, [("here", json.dumps({"workspaceDir": WORKSPACE}))])
    assert [s.ident for s in mcode.collect(tmp_path, Path(WORKSPACE), None, ALL)] == [
        "here"
    ]
    assert {s.ident for s in mcode.collect(tmp_path, None, None, ALL)} == {
        "here",
        "unknown",
    }
    assert [s.ident for s in mcode.collect(tmp_path, None, ("unk",), ALL)] == [
        "unknown"
    ]


def test_unreadable_database_and_misnamed_folders(tmp_path: Path) -> None:
    log(tmp_path, "s", [])
    broken = tmp_path / "v2" / "sqlite" / "runtime-state.sqlite"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"not a database at all, not even close......")
    misnamed = tmp_path / "v2" / "sessions" / "2026" / "01" / "01"
    jsonl(misnamed / "20260101-session_%%%" / "messages.jsonl", [])
    jsonl(misnamed / "20260101-session_" / "messages.jsonl", [])
    [session] = mcode.collect(tmp_path, None, None, ALL)
    assert session.ident == "s"
    assert "cwd" not in session.args
    assert mcode.collect(tmp_path, Path(WORKSPACE), None, ALL) == []

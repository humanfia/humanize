from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from hmz.runtime.tracing.readers import omp, pi
from tests.unit.runtime.tracing.logs import ALL, jsonl

T0 = 1_767_225_600
WORKSPACE = "/work/repo"


def iso(offset: float) -> str:
    return datetime.datetime.fromtimestamp(T0 + offset, datetime.UTC).isoformat()


def msg(at: float, role: str, /, **fields: Any) -> dict[str, Any]:
    return {
        "type": "message",
        "timestamp": iso(at),
        "message": {"role": role, **fields},
    }


def head(cwd: str = WORKSPACE) -> list[dict[str, Any] | str]:
    return [
        {"type": "session", "cwd": cwd, "version": 3, "timestamp": iso(0)},
        {"type": "model_change", "provider": "anthropic", "modelId": "m1"},
        {"type": "model_change", "provider": "openai", "modelId": "m2"},
        {"type": "thinking_level_change", "thinkingLevel": "high"},
    ]


def log(home: Path, ident: str, rows: list[dict[str, Any] | str]) -> Path:
    return jsonl(
        home / "sessions" / "--work-repo--" / f"2026-01-01_{ident}.jsonl", rows
    )


def test_reads_a_session(tmp_path: Path) -> None:
    log(
        tmp_path,
        "abcdefghij",
        [
            *head(),
            {"type": "message", "timestamp": 5},
            {"type": "message", "timestamp": "not a time"},
            msg(1, "user", content="fix it"),
            msg(
                2,
                "assistant",
                model="m1",
                usage={"input": 1},
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
                    {"type": "toolCall", "id": "c2", "name": "edit", "arguments": {}},
                ],
            ),
            msg(
                3,
                "toolResult",
                toolCallId="c1",
                content=[{"type": "text", "text": "a"}],
            ),
            msg(4, "user", content="next"),
        ],
    )
    [session] = pi.collect(tmp_path, None, None, ALL)
    assert (session.key, session.ident, session.label) == (
        "pi:abcdefghij",
        "abcdefghij",
        "main",
    )
    assert session.title == "abcdefgh · fix it"
    assert session.args["cwd"] == WORKSPACE
    assert session.args["version"] == 3
    assert (session.args["model"], session.args["provider"]) == ("m1", "anthropic")
    assert session.args["effort"] == "high"

    by = {(a.category, a.name): a for a in session.actions}
    turn = by["turn", "turn: fix it"]
    assert (turn.start, turn.end) == (T0 + 1, T0 + 4)
    think = by["llm", "think: plan"]
    assert (think.start, think.end) == (T0 + 1, T0 + 2)
    assert think.args["stop"] == "toolUse"
    assert by["message", "say: ok"].start == T0 + 2
    bash = by["tool", "bash: ls"]
    assert (bash.start, bash.end, bash.args["output"]) == (T0 + 2, T0 + 3, "a")
    assert by["tool", "edit"].args["unfinished"] is True


def test_head_is_read_whatever_the_window(tmp_path: Path) -> None:
    log(
        tmp_path,
        "s",
        [*head(), msg(1, "user", content="early"), msg(50, "user", content="late")],
    )
    [session] = pi.collect(tmp_path, None, None, (T0 + 40, T0 + 60))
    assert session.args["model"] == "m1"
    assert [a.name for a in session.actions] == ["turn: late"]


def test_workspace_is_read_from_the_log(tmp_path: Path) -> None:
    log(tmp_path, "here", head())
    log(tmp_path, "there", head("/else"))
    jsonl(tmp_path / "sessions" / "x" / "noid.jsonl", [])
    assert [s.ident for s in pi.collect(tmp_path, Path(WORKSPACE), None, ALL)] == [
        "here"
    ]
    assert {s.ident for s in pi.collect(tmp_path, None, None, ALL)} == {
        "here",
        "there",
        "noid",
    }
    assert [s.ident for s in pi.collect(tmp_path, None, ("pi:the",), ALL)] == ["there"]


def test_omps_log_is_read_as_pi_reads_its_own(tmp_path: Path) -> None:
    log(
        tmp_path,
        "01a11bbb",
        [
            {"type": "title", "title": "fixing it"},
            {"type": "session", "cwd": WORKSPACE, "version": 3, "timestamp": iso(0)},
            {"type": "model_change", "model": "openrouter/anthropic/claude-x"},
            msg(1, "user", content="fix it"),
            {"type": "custom", "timestamp": iso(1)},
            msg(2, "assistant", content=[{"type": "text", "text": "ok"}]),
        ],
    )
    [session] = omp.collect(tmp_path, None, None, ALL)
    assert (session.key, session.backend) == ("omp:01a11bbb", "omp")
    assert (session.args["provider"], session.args["model"]) == (
        "openrouter",
        "anthropic/claude-x",
    )
    assert session.args["cwd"] == WORKSPACE
    by = {(a.category, a.name): a for a in session.actions}
    assert by["turn", "turn: fix it"].start == T0 + 1
    assert by["message", "say: ok"].start == T0 + 2

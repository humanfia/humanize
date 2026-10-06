from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from hmz.runtime.tracing.readers import claude
from tests.unit.runtime.tracing.logs import ALL, jsonl

T0 = 1_767_225_600  # 2026-01-01T00:00:00Z
WORKSPACE = "/work/repo"
FOLDER = "-work-repo"


def iso(offset: float) -> str:
    return datetime.datetime.fromtimestamp(T0 + offset, datetime.UTC).isoformat()


def user(at: float, content: Any, prompt: str = "p1", **extra: Any) -> dict[str, Any]:
    return {
        "type": "user",
        "timestamp": iso(at),
        "promptId": prompt,
        "message": {"content": content},
        **extra,
    }


def assistant(
    at: float, request: str, blocks: list[dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    return {
        "type": "assistant",
        "timestamp": iso(at),
        "requestId": request,
        "message": {"model": "claude-x", "usage": {"in": 1}, "content": blocks},
        **extra,
    }


def main_log(home: Path, sid: str = "sess-1") -> Path:
    return jsonl(
        home / "projects" / FOLDER / f"{sid}.jsonl",
        [
            {"type": "summary"},  # no timestamp: skipped
            user(0, "fix the bug", cwd=WORKSPACE, version="2.0", sessionId=sid),
            user(1, [{"type": "text", "text": "and test it"}]),
            assistant(
                3,
                "r1",
                [
                    {"type": "thinking", "thinking": "hmm"},
                    {"type": "text", "text": "ok"},
                ],
                effort="high",
            ),
            assistant(
                4,
                "r1",
                [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "Bash",
                        "input": {"command": "pytest"},
                    },
                    {
                        "type": "tool_use",
                        "id": "t2",
                        "name": "Task",
                        "input": {"description": "explore"},
                    },
                ],
            ),
            user(
                6,
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": "passed",
                        "is_error": True,
                    },
                    {"type": "tool_result", "tool_use_id": "nobody"},
                ],
                toolUseResult={"stdout": "passed"},
            ),
            {
                "type": "system",
                "timestamp": iso(7),
                "subtype": "compact",
                "level": "info",
                "ignored": 1,
            },
            {"type": "x", "timestamp": iso(8), "aiTitle": "Bug fixing"},
            user(9, "next", prompt="p2"),
        ],
    )


def test_reads_a_session_into_turns_thinking_tools_and_events(tmp_path: Path) -> None:
    main_log(tmp_path)
    [session] = claude.collect(tmp_path, None, None, ALL)
    assert session.key == "claude:sess-1"
    assert (session.backend, session.ident, session.label, session.parent) == (
        "claude",
        "sess-1",
        "main",
        None,
    )
    assert session.title == "sess-1 · Bug fixing"
    assert session.args["cwd"] == WORKSPACE
    assert session.args["model"] == "claude-x"
    assert session.args["effort"] == "high"
    assert session.args["log"].endswith("sess-1.jsonl")

    by = {(a.category, a.name): a for a in session.actions}
    first = by["turn", "turn: fix the bug and test it"]
    assert first.args["prompt"] == "fix the bug\nand test it"
    assert (first.start, first.end) == (T0, T0 + 9)
    think = by["llm", "think: hmm"]
    assert (think.start, think.end) == (T0 + 1, T0 + 3)
    assert think.args["thinking"] == "hmm"
    assert by["message", "say: ok"].args["text"] == "ok"
    generate = by["llm", "generate"]
    assert (generate.start, generate.end) == (T0 + 3, T0 + 4)
    assert generate.args == {"emits": "Bash"}

    bash = by["tool", "Bash: pytest"]
    assert (bash.start, bash.end) == (T0 + 4, T0 + 6)
    assert bash.args["output"] == "passed"
    assert bash.args["error"] is True
    assert bash.args["result"] == {"stdout": "passed"}
    task = by["tool", "Task: explore"]
    assert task.args["unfinished"] is True
    assert task.end >= task.start

    event = by["event", "system: compact"]
    assert event.args == {"subtype": "compact", "level": "info"}
    last = by["turn", "turn: next"]
    assert last.start == T0 + 9


def test_each_request_is_one_think_slice(tmp_path: Path) -> None:
    jsonl(
        tmp_path / "projects" / FOLDER / "s.jsonl",
        [
            user(0, "go"),
            assistant(2, "r1", [{"type": "text", "text": "a"}]),
            assistant(
                5, "r2", [{"type": "tool_use", "id": "x", "name": "Read", "input": {}}]
            ),
        ],
    )
    [session] = claude.collect(tmp_path, None, None, ALL)
    thinks = [(a.start, a.end) for a in session.actions if a.category == "llm"]
    assert thinks == [(T0, T0 + 2), (T0 + 2, T0 + 5)]
    assert [a.name for a in session.actions if a.category == "tool"] == ["Read"]


def test_synthetic_model_is_not_the_session_model(tmp_path: Path) -> None:
    jsonl(
        tmp_path / "projects" / FOLDER / "s.jsonl",
        [
            {
                "type": "assistant",
                "timestamp": iso(0),
                "message": {"model": "<synthetic>", "content": []},
            },
            assistant(1, "r", []),
        ],
    )
    [session] = claude.collect(tmp_path, None, None, ALL)
    assert session.args["model"] == "claude-x"
    assert "effort" not in session.args


def test_subagents_link_to_the_tool_that_spawned_them(tmp_path: Path) -> None:
    main_log(tmp_path)
    folder = tmp_path / "projects" / FOLDER / "sess-1" / "subagents"
    jsonl(folder / "agent-abcdef1234.jsonl", [user(4.5, "explore the repo")])
    (folder / "agent-abcdef1234.meta.json").write_text(
        json.dumps({"agentType": "Explore", "description": "look", "toolUseId": "t2"})
    )
    jsonl(folder / "workflows" / "wf" / "agent-zz.jsonl", [user(5, "w")])
    (folder / "workflows" / "wf" / "agent-zz.meta.json").write_text("{not json")
    jsonl(folder / "journal.jsonl", [user(5, "skip")])

    found = {s.key: s for s in claude.collect(tmp_path, None, None, ALL)}
    assert set(found) == {
        "claude:sess-1",
        "claude:sess-1:agent-abcdef1234",
        "claude:sess-1:agent-zz",
    }
    child = found["claude:sess-1:agent-abcdef1234"]
    assert child.label == "Explore · look"
    assert child.parent == "claude:sess-1"
    assert child.ident == "sess-1"
    assert child.title == "abcdef12 · explore the repo"
    assert child.args["toolUseId"] == "t2"
    assert "label" not in child.args
    spawner = next(
        a for a in found["claude:sess-1"].actions if a.name == "Task: explore"
    )
    assert spawner.spawn == child.key
    assert found["claude:sess-1:agent-zz"].label == "wf · subagent"


def test_workspace_and_sessions_narrow_what_is_read(tmp_path: Path) -> None:
    main_log(tmp_path, "keep-1")
    jsonl(tmp_path / "projects" / "-elsewhere" / "other.jsonl", [user(0, "x")])
    assert [s.key for s in claude.collect(tmp_path, Path(WORKSPACE), None, ALL)] == [
        "claude:keep-1"
    ]
    assert [s.key for s in claude.collect(tmp_path, None, ("oth",), ALL)] == [
        "claude:other"
    ]
    assert claude.collect(tmp_path / "missing", None, None, ALL) == []


def test_window_cuts_records_outside_it(tmp_path: Path) -> None:
    main_log(tmp_path)
    [session] = claude.collect(tmp_path, None, None, (T0 + 8.5, T0 + 100))
    assert [a.name for a in session.actions] == ["turn: next"]
    assert "cwd" not in session.args

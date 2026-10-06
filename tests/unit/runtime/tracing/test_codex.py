from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from hmz.runtime.tracing.readers import codex
from tests.unit.runtime.tracing.logs import ALL, jsonl

T0 = 1_767_225_600
WORKSPACE = "/work/repo"


def iso(offset: float) -> str:
    return datetime.datetime.fromtimestamp(T0 + offset, datetime.UTC).isoformat()


def row(at: float, kind: str, /, **payload: Any) -> dict[str, Any]:
    return {"timestamp": iso(at), "type": kind, "payload": payload}


def meta(ident: str, **extra: Any) -> dict[str, Any]:
    return row(0, "session_meta", id=ident, cwd=WORKSPACE, cli_version="0.9", **extra)


def ev(at: float, item: str, /, **payload: Any) -> dict[str, Any]:
    return row(at, "event_msg", type=item, **payload)


def ri(at: float, item: str, /, **payload: Any) -> dict[str, Any]:
    return row(at, "response_item", type=item, **payload)


def rollout(home: Path, name: str, rows: list[dict[str, Any] | str]) -> Path:
    return jsonl(home / "sessions" / "2026" / f"rollout-{name}.jsonl", rows)


def test_reads_a_rollout(tmp_path: Path) -> None:
    rollout(
        tmp_path,
        "a",
        [
            meta("thread-aaaaaaaa"),
            row(0.5, "turn_context", model="gpt-5", effort="high", extra="no"),
            ev(1, "task_started", turn_id="t1"),
            ev(1, "user_message", message="refactor it"),
            ri(2, "reasoning", summary=[{"text": "plan"}]),
            ev(2.5, "agent_reasoning", text="more"),
            ev(2.6, "token_count", info={"last_token_usage": {"input": 5}}),
            ri(
                3,
                "function_call",
                name="shell",
                call_id="c1",
                arguments=json.dumps({"command": "ls"}),
            ),
            ri(4, "function_call_output", call_id="c1", output="a b"),
            ri(5, "custom_tool_call", name="apply", call_id="c2", input="not json"),
            ri(6, "web_search_call", action={"query": "docs"}),
            ev(7, "patch_apply_end", changes={"x.py": {}}, success=True),
            ev(7.5, "sub_agent_activity", kind="started", agent_path="root/w"),
            row(7.6, "compacted"),
            ev(8, "agent_message", message="done"),
            ri(8.5, "agent_message", recipient="w", author="root", content="hi"),
            ev(9, "task_complete", last_agent_message="all done"),
            ev(10, "user_message", message="again"),
            "{torn",
        ],
    )
    [session] = codex.collect(tmp_path, None, None, ALL)
    assert (session.key, session.label, session.parent) == (
        "codex:thread-aaaaaaaa",
        "main",
        None,
    )
    assert session.title == "thread-a · refactor it"
    assert session.args["cwd"] == WORKSPACE
    assert session.args["cli_version"] == "0.9"
    assert session.args["model"] == "gpt-5"
    assert session.args["effort"] == "high"
    assert "extra" not in session.args

    by = {(a.category, a.name): a for a in session.actions}
    turn = by["turn", "turn: refactor it"]
    assert (turn.start, turn.end) == (T0 + 1, T0 + 9)
    assert turn.args["result"] == "all done"
    think = by["llm", "think: more"]
    assert think.args["reasoning"] == "plan\nmore"
    assert think.args["usage"] == {"input": 5}
    assert (think.start, think.end) == (T0, T0 + 2.5)
    shell = by["tool", "shell: ls"]
    assert (shell.start, shell.end) == (T0 + 3, T0 + 4)
    assert shell.args["output"] == "a b"
    assert shell.args["input"] == {"command": "ls"}
    apply = by["tool", "apply: not json"]
    assert apply.args["unfinished"] is True
    assert by["tool", "web_search: docs"].args["input"] == {"query": "docs"}
    assert by["tool", "apply_patch: x.py"].args["success"] is True
    assert ("event", "agent started: root/w") in by
    assert ("event", "system: context_compacted") in by
    assert by["message", "say: done"].args["text"] == "done"
    assert by["message", "send: w"].args["text"] == "hi"
    last = by["turn", "turn: again"]
    assert last.start == T0 + 10


def test_subagent_threads_follow_their_parent(tmp_path: Path) -> None:
    rollout(
        tmp_path,
        "p",
        [
            meta("parent-1"),
            ri(
                1,
                "function_call",
                name="spawn",
                call_id="c",
                arguments=json.dumps({"task_name": "worker"}),
            ),
        ],
    )
    rollout(
        tmp_path,
        "c",
        [
            meta("child-1", parent_thread_id="parent-1", agent_path="root/worker"),
            ev(2, "user_message", message="work"),
        ],
    )
    rollout(tmp_path, "g", [meta("grand-1", parent_thread_id="child-1")])
    rollout(tmp_path, "o", [meta("other-1")])

    found = {s.key: s for s in codex.collect(tmp_path, None, ("parent",), ALL)}
    assert set(found) == {"codex:parent-1", "codex:child-1", "codex:grand-1"}
    child = found["codex:child-1"]
    assert (child.label, child.parent) == ("root/worker", "codex:parent-1")
    [spawn] = [a for a in found["codex:parent-1"].actions if a.category == "tool"]
    assert spawn.spawn == "codex:child-1"
    assert found["codex:grand-1"].parent == "codex:child-1"


def test_skips_logs_that_are_not_rollouts_or_are_elsewhere(tmp_path: Path) -> None:
    rollout(tmp_path, "bad", ["not json", ev(1, "user_message", message="x")])
    rollout(tmp_path, "nometa", [ev(1, "user_message", message="x")])
    rollout(tmp_path, "far", [row(0, "session_meta", id="far", cwd="/else")])
    rollout(tmp_path, "here", [meta("here")])
    assert [s.ident for s in codex.collect(tmp_path, None, None, ALL)] == [
        "far",
        "here",
    ]
    assert [s.ident for s in codex.collect(tmp_path, Path(WORKSPACE), None, ALL)] == [
        "here"
    ]


def test_aborted_turn_records_why_and_window_cuts(tmp_path: Path) -> None:
    rollout(
        tmp_path,
        "a",
        [
            meta("t"),
            ev(1, "user_message", message="go"),
            ev(2, "turn_aborted", reason="interrupted"),
            ev(50, "agent_message", message="late"),
        ],
    )
    [session] = codex.collect(tmp_path, None, None, ALL)
    [turn] = [a for a in session.actions if a.category == "turn"]
    assert turn.args["result"] == "interrupted"
    [cut] = codex.collect(tmp_path, None, None, (T0, T0 + 10))
    assert [a.name for a in cut.actions] == ["turn: go"]

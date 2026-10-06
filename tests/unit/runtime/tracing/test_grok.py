from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Any

from hmz.runtime.tracing.readers import grok
from tests.unit.runtime.tracing.logs import ALL, jsonl

T0 = 1_767_225_600
WORKSPACE = "/work/repo"
IDENT = "0199aaaa-bbbb-7ccc-8ddd-eeeeffff0000"


def up(
    at: float, kind: str, /, meta: dict[str, Any] | None = None, **update: Any
) -> dict[str, Any]:
    return {
        "method": "session/update",
        "params": {
            "sessionId": "x",
            "_meta": {"agentTimestampMs": (T0 + at) * 1000, **(meta or {})},
            "update": {"sessionUpdate": kind, **update},
        },
    }


def text(body: str) -> dict[str, str]:
    return {"type": "text", "text": body}


def log(
    home: Path, ident: str, rows: list[dict[str, Any] | str], cwd: str = WORKSPACE
) -> Path:
    folder = urllib.parse.quote(cwd, safe="")
    return jsonl(home / "sessions" / folder / ident / "updates.jsonl", rows)


def stream(start: float) -> dict[str, Any]:
    return {"streamStartMs": (T0 + start) * 1000, "promptId": "p"}


def test_reads_a_session(tmp_path: Path) -> None:
    log(
        tmp_path,
        IDENT,
        [
            {"params": {"update": {"sessionUpdate": "x"}}},  # timed by nothing
            {
                "timestamp": T0 + 0.5,
                "params": {"update": {"sessionUpdate": "plan", "type": "p"}},
            },
            up(
                1,
                "user_message_chunk",
                content=text("fix"),
                _meta={"promptIndex": 0, "modelId": "grok-4"},
            ),
            up(1.1, "user_message_chunk", content=text("it"), _meta={"promptIndex": 0}),
            up(3, "agent_thought_chunk", meta=stream(2), content=text("hmm")),
            up(4, "agent_message_chunk", meta=stream(2), content=text("ok")),
            up(
                5,
                "tool_call",
                toolCallId="c1",
                title="Run",
                rawInput={"command": "ls"},
                _meta={"x.ai/tool": {"name": "bash", "namespace": "sh"}},
            ),
            up(
                5.5,
                "tool_call_update",
                toolCallId="c1",
                kind="execute",
                status="in_progress",
                content=[],
            ),
            up(
                6,
                "tool_call_update",
                toolCallId="c1",
                status="completed",
                content=[{"type": "content", "content": text("a b")}],
            ),
            up(6.5, "tool_call", toolCallId="c2", title="edit", rawInput="x.py"),
            up(
                7,
                "tool_call_update",
                toolCallId="c2",
                status="failed",
                content=[],
                rawOutput={"diff": "-"},
            ),
            up(7.5, "tool_call", title="search"),
            up(
                8, "turn_completed", stop_reason="end", elapsed_ms=7000, usage={"in": 9}
            ),
        ],
    )
    [session] = grok.collect(tmp_path, None, None, ALL)
    assert (session.key, session.label, session.parent) == (
        f"grok:{IDENT}",
        "main",
        None,
    )
    assert session.title == f"{IDENT[:18]} · fix it"
    assert session.args["cwd"] == WORKSPACE
    assert session.args["model"] == "grok-4"

    by = {(a.category, a.name): a for a in session.actions}
    turn = by["turn", "turn: fix it"]
    assert (turn.start, turn.end) == (T0 + 1, T0 + 8)
    assert turn.args["usage"] == {"in": 9}
    assert turn.args["stop_reason"] == "end"
    think = by["llm", "think: hmm"]
    assert (think.start, think.end) == (T0 + 2, T0 + 5)
    say = by["message", "say: ok"]
    assert say.end == T0 + 4
    bash = by["tool", "bash: ls"]
    assert (bash.start, bash.end) == (T0 + 5, T0 + 6)
    assert bash.args["output"] == "a b"
    assert bash.args["error"] is False
    assert bash.args["kind"] == "execute"
    assert bash.args["namespace"] == "sh"
    edit = by["tool", "edit: x.py"]
    assert edit.args["error"] is True
    assert edit.args["result"] == {"diff": "-"}
    search = by["tool", "search"]
    assert (search.start, search.end) == (T0 + 7.5, T0 + 7.5)
    assert by["event", "plan: p"].start == T0 + 0.5


def test_a_turn_nobody_opened_is_still_kept(tmp_path: Path) -> None:
    log(
        tmp_path,
        "s",
        [
            up(1, "agent_message_chunk", content=text("hi")),
            up(2, "turn_completed", usage={"modelUsage": {"grok-build": {}}}),
            up(3, "user_message_chunk", content=text("left open")),
        ],
    )
    [session] = grok.collect(tmp_path, None, None, ALL)
    assert session.args["model"] == "grok-build"
    turns = [a for a in session.actions if a.category == "turn"]
    assert [(t.name, t.start, t.end) for t in turns] == [
        ("turn", T0 + 1, T0 + 2),
        ("turn: left open", T0 + 3, T0 + 3),
    ]


def test_spawned_sessions_become_subagents(tmp_path: Path) -> None:
    log(
        tmp_path,
        "parent",
        [
            up(
                1,
                "subagent_spawned",
                child_session_id="child",
                subagent_type="explore",
                description="look around",
            )
        ],
    )
    log(tmp_path, "child", [up(2, "user_message_chunk", content=text("w"))])
    log(tmp_path, "zother", [up(2, "user_message_chunk", content=text("o"))])
    found = {s.key: s for s in grok.collect(tmp_path, None, ("parent",), ALL)}
    assert set(found) == {"grok:parent", "grok:child"}
    child = found["grok:child"]
    assert (child.parent, child.label) == ("grok:parent", "explore · look around")
    [spawn] = found["grok:parent"].actions
    assert spawn.spawn == "grok:child"
    assert spawn.name == "subagent_spawned: look around"


def test_workspace_is_the_decoded_folder_name(tmp_path: Path) -> None:
    log(tmp_path, "here", [up(1, "x")])
    log(tmp_path, "there", [up(1, "x")], cwd="/else where")
    assert [s.ident for s in grok.collect(tmp_path, Path(WORKSPACE), None, ALL)] == [
        "here"
    ]
    [there] = grok.collect(tmp_path, Path("/else where"), None, ALL)
    assert there.args["cwd"] == "/else where"


def test_window_cuts_records(tmp_path: Path) -> None:
    log(tmp_path, "s", [up(1, "a"), up(20, "b")])
    [session] = grok.collect(tmp_path, None, None, (T0, T0 + 10))
    assert [a.name for a in session.actions] == ["a"]

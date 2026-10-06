from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hmz.runtime.tracing.readers import kimi
from tests.unit.runtime.tracing.logs import ALL, jsonl

T0 = 1_767_225_600
WORKSPACE = "/work/repo"
IDENT = "session_0123456789abcdef"


def rec(at: float, kind: str, /, **fields: Any) -> dict[str, Any]:
    return {"time": (T0 + at) * 1000, "type": kind, **fields}


def loop(at: float, kind: str, /, **event: Any) -> dict[str, Any]:
    return rec(at, "context.append_loop_event", event={"type": kind, **event})


def state(home: Path, agents: dict[str, Any], **extra: Any) -> Path:
    folder = home / "sessions" / "proj" / IDENT
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "state.json").write_text(
        json.dumps({"workDir": WORKSPACE, "agents": agents, **extra})
    )
    return folder


def test_reads_the_agents_of_a_session(tmp_path: Path) -> None:
    home = tmp_path / "home" / "main"
    folder = state(
        tmp_path,
        {
            "main": {"homedir": str(home)},
            "sub": {"type": "coder", "parentAgentId": "main"},
            "lost": {},
        },
        title="Refactor",
    )
    jsonl(
        home / "wire.jsonl",
        [
            {"time": "soon", "type": "turn.prompt"},
            rec(0, "llm.request", modelAlias="kimi-k3", thinkingEffort="high"),
            rec(0, "config.update", profileName="default"),
            rec(0.5, "permission.set_mode", mode="yolo"),
            rec(1, "turn.prompt", input="do it", origin="user"),
            loop(2, "step.begin", uuid="s1", step=1, turnId="t"),
            loop(
                3, "content.part", stepUuid="s1", part={"type": "think", "think": "hmm"}
            ),
            loop(3.5, "content.part", part={"type": "text", "text": "ok"}),
            loop(4, "tool.call", toolCallId="c1", name="bash", args={"command": "ls"}),
            loop(
                5,
                "tool.result",
                toolCallId="c1",
                result={"output": "a", "isError": True},
            ),
            loop(6, "step.end", uuid="s1", usage={"in": 1}, finishReason="stop"),
            loop(6.5, "unknown"),
            loop(7, "tool.call", toolCallId="c2", name="read"),
            rec(8, "turn.cancel"),
            rec(9, "turn.prompt", input="again"),
        ],
    )
    jsonl(
        folder / "agents" / "sub" / "wire.jsonl", [rec(2, "turn.prompt", input="sub")]
    )

    found = {s.key: s for s in kimi.collect(tmp_path, None, None, ALL)}
    assert set(found) == {f"kimi:{IDENT}:main", f"kimi:{IDENT}:sub"}
    main = found[f"kimi:{IDENT}:main"]
    assert (main.ident, main.label, main.parent) == (IDENT, "main", None)
    assert main.title == "01234567 · Refactor"
    assert main.args["model"] == "kimi-k3"
    assert main.args["effort"] == "high"
    assert main.args["profile"] == "default"
    assert main.args["work_dir"] == WORKSPACE

    by = {(a.category, a.name): a for a in main.actions}
    assert ("event", "system: permission yolo") in by
    turn = by["turn", "turn: do it"]
    assert (turn.start, turn.end) == (T0 + 1, T0 + 8)
    assert turn.args["origin"] == "user"
    think = by["llm", "think: hmm"]
    assert (think.start, think.end) == (T0 + 2, T0 + 3)
    assert think.args["usage"] == {"in": 1}
    assert think.args["finishReason"] == "stop"
    assert think.args["thinking"] == "hmm"
    assert by["message", "say: ok"].end == T0 + 3.5
    bash = by["tool", "bash: ls"]
    assert (bash.start, bash.end) == (T0 + 4, T0 + 5)
    assert (bash.args["output"], bash.args["error"]) == ("a", True)
    assert by["tool", "read"].args["unfinished"] is True
    assert by["turn", "turn: again"].start == T0 + 9

    sub = found[f"kimi:{IDENT}:sub"]
    assert (sub.ident, sub.label, sub.parent) == (
        IDENT,
        "coder · sub",
        f"kimi:{IDENT}:main",
    )


def test_think_without_a_step_opens_one(tmp_path: Path) -> None:
    folder = state(tmp_path, {"main": {}})
    jsonl(
        folder / "agents" / "main" / "wire.jsonl",
        [
            rec(1, "turn.prompt", input="x"),
            loop(2, "content.part", part={"type": "think", "think": "a"}),
        ],
    )
    [session] = kimi.collect(tmp_path, None, None, ALL)
    assert session.title == "01234567 · x"
    [think] = [a for a in session.actions if a.category == "llm"]
    assert (think.start, think.end, think.name) == (T0 + 1, T0 + 2, "think: a")


def test_a_silent_step_ends_where_its_end_says(tmp_path: Path) -> None:
    folder = state(tmp_path, {"main": {}})
    jsonl(
        folder / "agents" / "main" / "wire.jsonl",
        [
            loop(1, "step.begin", uuid="s", step=1, turnId="t"),
            loop(4, "step.end", uuid="s", usage={"in": 2}),
            loop(5, "step.end", uuid="unknown"),
        ],
    )
    [session] = kimi.collect(tmp_path, None, None, ALL)
    [step] = session.actions
    assert (step.name, step.start, step.end) == ("think", T0 + 1, T0 + 4)
    assert step.args["usage"] == {"in": 2}
    assert (step.args["step"], step.args["turn"]) == (1, "t")


def test_narrowing_by_workspace_and_session(tmp_path: Path) -> None:
    folder = state(tmp_path, {"main": {}})
    jsonl(folder / "agents" / "main" / "wire.jsonl", [])
    bad = tmp_path / "sessions" / "proj" / "session_bad"
    bad.mkdir(parents=True)
    (bad / "state.json").write_text("{torn")
    assert len(kimi.collect(tmp_path, Path(WORKSPACE), None, ALL)) == 1
    assert kimi.collect(tmp_path, Path("/else"), None, ALL) == []
    assert len(kimi.collect(tmp_path, None, ("0123",), ALL)) == 1
    assert kimi.collect(tmp_path, None, ("zzz",), ALL) == []

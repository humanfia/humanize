"""MiniMax Code: the `mcode exec` a turn is, the rungs it refuses, and the stream read back."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel

from hmz.coganchor import fence, models
from hmz.coganchor.agents import (
    Failed,
    MiniMaxCodeAgent,
    MiniMaxCodeAgentConfig,
    MiniMaxCodeSession,
    Unfenced,
    Unserved,
)
from hmz.coganchor.agents.minimax import taken
from hmz.coganchor.backends import Model
from hmz.coganchor.fence import Fence
from tests.unit.coganchor.agents.doubles_u4 import Spawner, fenceable, offering

if TYPE_CHECKING:
    from pathlib import Path

_MODEL = "minimax/MiniMax-M3"


#: What every agent here is made with unless a test says otherwise.
_DEFAULTS: dict[str, Any] = {"model": _MODEL, "effort": ""}


@pytest.fixture
def spawner(monkeypatch: pytest.MonkeyPatch) -> Spawner:
    """Every process a turn asks for, scripted rather than started."""
    return Spawner(monkeypatch)


@pytest.fixture(autouse=True)
def _catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    """One model at two rungs, one at none, as the account's catalogue last said."""
    listed = (
        Model(name=_MODEL, efforts=("high", "low")),
        Model(name="minimax/plain", efforts=()),
    )
    monkeypatch.setattr(models, "offered", offering(*listed))


def _mcode(**given: Any) -> MiniMaxCodeAgent:
    return MiniMaxCodeAgent(MiniMaxCodeAgentConfig(**_DEFAULTS | given))


def _turn(
    session_id: str = "s-1", answer: str = "done", **usage: int
) -> list[dict[str, Any]]:
    """What one plain turn prints."""
    return [
        {"type": "exec.started", "sessionId": session_id},
        {
            "type": "item.started",
            "item": {"type": "tool_call", "toolCall": {"id": "t1", "name": "bash"}},
        },
        {
            "type": "item.updated",
            "item": {
                "type": "tool_call",
                "toolCall": {"id": "t1", "name": "bash", "input": {"command": "ls"}},
            },
        },
        {
            "type": "item.completed",
            "item": {
                "type": "tool_call",
                "toolCall": {"id": "t1", "name": "bash", "input": {"command": "ls"}},
            },
        },
        {"type": "item.updated", "item": {"type": "agent_message", "content": "do"}},
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "content": answer},
        },
        {"type": "item.completed", "item": {"type": "reasoning", "content": "hm"}},
        {
            "type": "turn.completed",
            "usage": usage,
            "model": {"providerId": "minimax", "modelId": "MiniMax-M3-0101"},
        },
        {"type": "exec.completed", "result": {"status": "succeeded"}},
    ]


@pytest.mark.parametrize(
    ("model", "effort"),
    [
        (_MODEL, "high"),
        (_MODEL, ""),
        (_MODEL, "auto"),
        ("", "high"),
        ("other/x", "max"),
    ],
)
def test_taken_lets_through_what_the_catalogue_allows_or_does_not_know(
    model: str, effort: str
) -> None:
    taken(model, effort, "")


@pytest.mark.parametrize(
    ("model", "effort", "match"),
    [
        (_MODEL, "max", r"runs minimax/MiniMax-M3 high, low, not at 'max'"),
        ("minimax/plain", "high", r"at no rung at all"),
    ],
)
def test_taken_refuses_a_rung_the_model_lacks(
    model: str, effort: str, match: str
) -> None:
    with pytest.raises(Unserved, match=match):
        taken(model, effort, "")


def test_a_catalogue_that_cannot_be_read_refuses_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unreadable(cli: str, provider: str = "") -> tuple[Model, ...]:
        raise OSError("gone")

    monkeypatch.setattr(models, "offered", unreadable)
    taken(_MODEL, "max", "")


@pytest.mark.parametrize(
    ("given", "error", "match"),
    [
        ({"effort": "max"}, Unserved, "not at 'max'"),
        ({"permission": "read-only"}, Unserved, "cannot be held to 'read-only'"),
        ({"service_tier": "fast"}, Unserved, "service tier"),
    ],
)
def test_what_it_cannot_run_is_refused_where_it_is_made(
    given: dict[str, Any], error: type[Exception], match: str
) -> None:
    with pytest.raises(error, match=match):
        _mcode(**given)


def test_a_fence_that_cuts_the_network_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fence, "enforceable", fenceable)
    with pytest.raises(Unfenced, match="grant it online ALL"):
        _mcode(fence=Fence(read=("/",), write=("/tmp",), online=False))


def test_a_turn_is_exec_with_the_prompt_on_stdin(
    spawner: Spawner, tmp_path: Path
) -> None:
    spawner.answering(_turn())
    _mcode(effort="high").new(tmp_path)("--not a flag")
    proc = spawner.last
    assert proc.args == [
        "mcode",
        "exec",
        "--output-format",
        "stream-json",
        "--input",
        "-",
        "--cwd",
        str(tmp_path),
        "--model",
        _MODEL,
        "--effort",
        "high",
    ]
    assert proc.stdin is not None
    assert proc.stdin.lines == ["--not a flag"]


@pytest.mark.parametrize(
    ("permission", "flags"),
    [
        ("workspace-write", ["--permission", "full"]),
        ("auto", ["--permission", "smart"]),
        ("bypass", ["--permission", "full"]),
        ("", []),
    ],
)
def test_each_rung_is_its_permission(
    spawner: Spawner, tmp_path: Path, permission: str, flags: list[str]
) -> None:
    spawner.answering(_turn())
    _mcode(permission=permission).new(tmp_path)("go")
    argv = spawner.last.args
    assert argv[argv.index(str(tmp_path)) + 1 : argv.index("--model")] == flags


def test_no_model_leaves_the_flag_off(spawner: Spawner, tmp_path: Path) -> None:
    spawner.answering(_turn())
    _mcode(model="").new(tmp_path)("go")
    assert "--model" not in spawner.last.args


def test_a_turn_reads_its_events_and_cost(spawner: Spawner, tmp_path: Path) -> None:
    spawner.answering(
        _turn(
            answer="the answer",
            inputTokens=10,
            outputTokens=4,
            cacheReadTokens=2,
            cacheWriteTokens=1,
        )
    )
    session = _mcode().new(tmp_path)
    events = list(session.stream("go"))
    said = [(one.kind, one.text) for one in events]
    assert said[:-1] == [
        ("tool", "bash ls"),
        ("text", "the answer"),
        ("reasoning", "hm"),
    ]
    result = events[-1]
    assert (result.kind, result.text) == ("result", "the answer")
    assert result.tokens == {"minimax/MiniMax-M3-0101": 17}
    assert dict(result.spent) == {
        "input": 10,
        "output": 4,
        "cache_read": 2,
        "cache_write": 1,
    }
    assert session.id == "s-1"
    assert session.named == "s-1"


def test_the_next_turn_carries_the_session_on(spawner: Spawner, tmp_path: Path) -> None:
    spawner.answering(_turn(session_id="s-9"))
    session = _mcode().new(tmp_path)
    session("one")
    session("two")
    first, second = spawner.started
    assert "--session" not in first.args
    assert second.args[-2:] == ["--session", "s-9"]


def test_a_task_is_a_subagent_bracketed_by_its_call(
    spawner: Spawner, tmp_path: Path
) -> None:
    call = {"id": "k", "name": "Task", "input": {"description": "look"}, "status": 1}
    spawner.answering(
        [
            {"type": "exec.started", "sessionId": "s"},
            {"type": "item.started", "item": {"type": "tool_call", "toolCall": call}},
            {"type": "item.completed", "item": {"type": "tool_call", "toolCall": call}},
            {"type": "exec.completed", "result": {"status": "succeeded"}},
        ]
    )
    events = list(_mcode().new(tmp_path).stream("go"))
    assert [(one.kind, one.text, one.whose) for one in events[:-1]] == [
        ("subagent", "Task look", "k"),
        ("subagent-ends", "Task look", "k"),
    ]


class _Verdict(BaseModel):
    ok: bool
    why: str = ""


def test_a_shaped_turn_sends_a_strict_schema_and_reads_the_output(
    spawner: Spawner, tmp_path: Path
) -> None:
    lines = _turn()
    lines[-1] = {
        "type": "exec.completed",
        "result": {"status": "succeeded", "output": {"ok": True, "why": "fine"}},
    }
    spawner.answering(lines)
    answered = _mcode().new(tmp_path)("judge", schema=_Verdict)
    assert answered == _Verdict(ok=True, why="fine")
    argv = spawner.last.args
    schema = json.loads(argv[argv.index("--output-schema") + 1])
    assert schema["required"] == ["ok", "why"]
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(
    ("ending", "match"),
    [
        ({"type": "turn.failed", "error": {"message": "the model refused"}}, "refused"),
        (
            {"type": "exec.completed", "result": {"status": "cancelled"}},
            "cancelled",
        ),
        (
            {
                "type": "exec.completed",
                "result": {"status": "failed", "error": {"message": "bad model"}},
            },
            "bad model",
        ),
    ],
)
def test_a_turn_that_says_it_failed_fails(
    spawner: Spawner, tmp_path: Path, ending: dict[str, Any], match: str
) -> None:
    spawner.answering([{"type": "exec.started", "sessionId": "s"}, ending])
    session = _mcode().new(tmp_path)
    with pytest.raises(Failed, match=match):
        session("go")
    with pytest.raises(RuntimeError):
        _ = session.id


def test_a_turn_that_says_nothing_fails(spawner: Spawner, tmp_path: Path) -> None:
    spawner.answering([])
    with pytest.raises(Failed, match="said nothing at all"):
        _mcode().new(tmp_path)("go")


def test_a_turn_naming_no_session_is_refused(spawner: Spawner, tmp_path: Path) -> None:
    spawner.answering(
        [
            "not json",
            "[]",
            {"type": "exec.completed", "result": {"status": "succeeded"}},
        ]
    )
    with pytest.raises(ValueError, match="named no session"):
        _mcode().new(tmp_path)("go")


def test_new_opens_a_minimax_session(tmp_path: Path) -> None:
    session = _mcode().new(tmp_path)
    assert isinstance(session, MiniMaxCodeSession)
    assert session.named is None


def test_an_agent_nobody_fenced_is_fenced_by_nothing(tmp_path: Path) -> None:
    agent = _mcode()
    agent.keeps = tmp_path
    assert agent.fenced() is None

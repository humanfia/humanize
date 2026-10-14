"""MiniMax Code: the `mcode exec` a turn is, the rungs it refuses, and the stream read back."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from hmz.coganchor import fence, gateway, models, providers
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
from hmz.coganchor.providers import Provider
from tests.unit.coganchor.agents.doubles_u4 import Spawner, fenceable, offering

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


# --------------------------------------------------------------- through a LiteLLM gateway


class _Gateway:
    """A gateway that starts nothing: where it would be, and whether it was taken down."""

    def __init__(self, provider: Provider) -> None:
        self.account = provider
        self.port = 4321
        self.url = "http://127.0.0.1:4321"
        self.key = "sk-master"
        self.running = True

    def stop(self) -> None:
        self.running = False


@dataclass
class _Configured:
    """Every `mcode provider` an agent ran, and what it ran each with."""

    ran: list[list[str]] = field(default_factory=list[list[str]])
    envs: list[dict[str, str]] = field(default_factory=list[dict[str, str]])
    #: What each exits with, by its subcommand.
    exits: dict[str, int] = field(default_factory=dict[str, int])

    def run(
        self, argv: list[str], *, env: dict[str, str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        self.ran.append(argv)
        self.envs.append(env)
        return subprocess.CompletedProcess(argv, self.exits.get(argv[2], 0), "", "no")


def _unswapped(self: Provider) -> tuple[tuple[str, str], ...]:
    """No credential path answered by another, which is the supervisor's to test."""
    del self
    return ()


@pytest.fixture
def routed(monkeypatch: pytest.MonkeyPatch) -> _Configured:
    """An account litellm holds, a gateway only pretended, and `mcode provider` recorded."""
    held = Provider(
        cli="mcode",
        name="gw",
        way="litellm-openai-key",
        env={"OPENAI_API_KEY": "upstream-secret"},
    )

    def find(cli: str, name: str) -> Provider:
        del cli, name
        return held

    monkeypatch.setattr(providers, "find", find)
    monkeypatch.setattr(Provider, "swaps", _unswapped)
    monkeypatch.setattr(gateway, "Gateway", _Gateway)
    monkeypatch.setenv("OPENAI_API_KEY", "lying-about")
    configured = _Configured()
    monkeypatch.setattr(subprocess, "run", configured.run)
    return configured


def test_a_turn_through_a_gateway_asks_for_it_as_a_provider_added_to_its_home(
    spawner: Spawner, routed: _Configured, tmp_path: Path
) -> None:
    spawner.answering(_turn(outputTokens=4))
    agent = _mcode(provider="gw", model="openai/gpt-5")
    session = agent.new(tmp_path)

    session("one")
    result = list(session.stream("two"))[-1]

    # Once a turn, each into the copy of `config.yaml` in the virtual home that turn starts
    # in -- which goes with it -- and never into the account's own.
    added, again = routed.ran
    assert added == again
    homes = [one["MINIMAX_DATA_DIR"] for one in routed.envs]
    assert homes == [(one.env or {})["MINIMAX_DATA_DIR"] for one in spawner.started]
    assert len(set(homes)) == 2
    assert not any(Path(one).exists() for one in homes)
    named = added[4]
    assert named.startswith("hmz-4321-")
    assert added == [
        "mcode",
        "provider",
        "add",
        "--name",
        named,
        "--base-url",
        "http://127.0.0.1:4321",
        "--api-format",
        "openai-completions",
        "--model",
        "openai/gpt-5",
        "--api-key-env",
        "MCODE_PROVIDER_API_KEY",
    ]
    assert routed.envs[0]["MCODE_PROVIDER_API_KEY"] == "sk-master"
    assert "OPENAI_API_KEY" not in routed.envs[0]
    asked = [one.args[one.args.index("--model") + 1] for one in spawner.started]
    assert asked == [f"custom_provider:{named}/openai/gpt-5"] * 2
    assert result.tokens == {"openai/gpt-5": 4}

    agent.stop()

    assert len(routed.ran) == 2  # nothing to take out of the account's own


def test_another_model_is_another_provider_beside_the_first(
    spawner: Spawner, routed: _Configured, tmp_path: Path
) -> None:
    spawner.answering(_turn())
    agent = _mcode(provider="gw", model="openai/gpt-5")
    agent.new(tmp_path)("one")
    agent.reconfigure(replace(agent.config, model="openai/gpt-5-mini"))
    agent.new(tmp_path)("two")

    names = [one[4] for one in routed.ran]
    assert len(set(names)) == 2
    assert all(one[2] == "add" for one in routed.ran)


def test_a_gateway_mcode_will_not_add_fails_the_turn(
    spawner: Spawner, routed: _Configured, tmp_path: Path
) -> None:
    spawner.answering(_turn())
    routed.exits = {"add": 2}

    with pytest.raises(Failed):
        _mcode(provider="gw", model="openai/gpt-5").new(tmp_path)("go")

    assert not spawner.started


@pytest.mark.usefixtures("routed")
def test_an_account_through_a_gateway_names_its_model() -> None:
    with pytest.raises(Unserved, match="name one"):
        _mcode(provider="gw", model="")

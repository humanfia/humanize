"""`hmz.coganchor.agents.agy`: Antigravity's CLI held open on stream-json, or one `--print`."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.agents import (
    AntigravityCLIAgent,
    AntigravityCLIAgentConfig,
    AntigravityCLISession,
    Failed,
    driver,
)
from hmz.coganchor.agents.config import Unserved
from hmz.coganchor.fence import Fence

from .doubles_u5 import configured, heard, line, option, spawning

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    from hmz.coganchor.agents.event import Event


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A home of the test's own: the agents agy is held to are files written into it."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def _agent(**said: Any) -> AntigravityCLIAgent:
    return AntigravityCLIAgent(
        AntigravityCLIAgentConfig(**configured("gemini-3-pro", said))
    )


def _step(**told: Any) -> str:
    return line({"event": "step_update", "step_update": told})


def _result(usage: dict[str, int] | None = None, **told: Any) -> str:
    said = {"response": "done", "status": "SUCCESS", "usage": usage or {}} | told
    return line({"event": "result", "conversation_id": "cv-1", "result": said})


_USAGE = {"input_tokens": 5, "output_tokens": 3, "thinking_tokens": 2}

#: What agy says, a turn at a time, with `--output-format stream-json`.
_SAID = (
    _step(text_delta="hmm", step_type="THINKING"),
    _step(tool_name="view_file", state="RUNNING", tool_info={"path": "a.py"}),
    _step(tool_name="view_file", state="DONE", tool_info={"path": "a.py"}),
    _step(text_delta="do", step_type="TEXT"),
    _step(text_delta="ne", step_type="TEXT"),
    "a plain line\n",
    _result(_USAGE),
)


def _answering(*said: str) -> Callable[[str], Iterable[str]]:
    def answers(told: str) -> Iterable[str]:
        del told
        return said

    return answers


def _turn(session: AntigravityCLISession, prompt: str = "do it") -> list[Event]:
    return list(session.stream(prompt))


def test_agy_is_driven_by_its_own_classes() -> None:
    assert driver("agy") == (AntigravityCLIAgent, AntigravityCLIAgentConfig)
    agent = _agent()
    assert agent.backend == "agy"
    assert isinstance(agent.new(), AntigravityCLISession)
    assert AntigravityCLIAgent.counts == {"input", "output", "reasoning", "cache_read"}


@pytest.mark.parametrize("seconds", [0.0, -1.0, math.inf, math.nan, 1e12])
def test_a_print_timeout_that_is_no_number_of_seconds_is_refused(
    seconds: float,
) -> None:
    with pytest.raises(ValueError, match="print_timeout"):
        AntigravityCLIAgentConfig(model="m", effort="", print_timeout=seconds)


def test_read_only_without_slash_commands_is_refused() -> None:
    with pytest.raises(Unserved, match="plan mode"):
        _agent(permission="read-only", disable_slash_commands=True)


def test_a_fence_is_held_from_outside_whatever_it_is() -> None:
    fence = Fence(online=False)
    assert _agent().natively(fence) is fence


def test_a_turn_is_a_user_line_and_the_steps_it_answers_with(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)

    events = _turn(session, "hello")

    (process,) = spawned
    assert process.args == [
        "agy",
        "--output-format",
        "stream-json",
        "--model",
        "gemini-3-pro",
        "--print-timeout",
        "86400.000s",
        "--add-dir",
        str(tmp_path),
        "--input-format",
        "stream-json",
    ]
    assert [json.loads(one) for one in process.told] == [
        {"event": "user", "message": {"content": "hello"}}
    ]
    assert [(one.kind, one.text) for one in events] == [
        ("reasoning", "hmm"),
        ("tool", "view_file a.py"),
        ("text", "done"),
        ("result", "done"),
    ]
    assert dict(events[-1].spent) == {"input": 5, "output": 3, "reasoning": 2}
    assert events[-1].tokens == {"gemini-3-pro": 10}
    assert session.id == "cv-1"


def test_what_a_turn_cost_is_what_the_running_total_rose_by(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    totals = iter(
        [_USAGE, {"input_tokens": 9, "output_tokens": 4, "thinking_tokens": 2}]
    )

    def answers(told: str) -> Iterable[str]:
        del told
        return [_result(next(totals))]

    spawned = spawning(monkeypatch, answers=answers)
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)

    _turn(session)
    second = _turn(session)[-1]

    assert len(spawned) == 1
    assert dict(second.spent) == {"input": 4, "output": 1, "reasoning": 0}


@pytest.mark.parametrize(
    ("said", "flags"),
    [
        ({"permission": "read-only"}, ["--mode", "plan"]),
        ({"permission": "workspace-write"}, ["--mode", "accept-edits"]),
        ({"permission": "auto"}, ["--dangerously-skip-permissions"]),
        ({"effort": "high"}, ["--effort", "high"]),
        ({"sandbox": True}, ["--sandbox"]),
        ({"disable_slash_commands": True}, ["--disable-slash-commands"]),
        ({"print_timeout": 90.5}, ["--print-timeout", "90.500s"]),
    ],
)
def test_what_the_agent_is_configured_with_goes_on_the_command_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    said: dict[str, Any],
    flags: list[str],
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent(**said)
    heard(agent)

    _turn(agent.new(tmp_path))

    argv = spawned[0].args
    at = argv.index(flags[0])
    assert argv[at : at + len(flags)] == flags


def test_a_model_carrying_its_effort_is_not_told_another(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent(model="gemini-3-pro-low", effort="high")
    heard(agent)

    _turn(agent.new(tmp_path))

    assert "--effort" not in spawned[0].args


def test_without_the_workspace_added_no_directory_is(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent(add_workspace=False)
    heard(agent)

    _turn(agent.new(tmp_path))

    assert "--add-dir" not in spawned[0].args


@pytest.mark.parametrize(
    ("said", "named", "tools"),
    [
        ({"permission": "read-only"}, "hmz-read-only", "view_file"),
        (
            {"permission": "read-only", "web_search": True},
            "hmz-read-only-web",
            "search_web",
        ),
        ({"web_search": False}, "hmz-offline", "run_command"),
    ],
)
def test_what_it_may_reach_is_an_agent_of_humanize_written_into_its_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    said: dict[str, Any],
    named: str,
    tools: str,
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent(**said)
    heard(agent)

    _turn(agent.new(tmp_path))

    assert option(spawned[0].args, "--agent") == named
    defined = tmp_path / f"home/.gemini/antigravity-cli/agents/{named}.md"
    assert f"name: {named}" in defined.read_text()
    assert tools in defined.read_text()


def test_an_agent_with_the_web_and_every_rung_open_is_held_to_no_agent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent(permission="auto", web_search=True)
    heard(agent)

    _turn(agent.new(tmp_path))

    assert "--agent" not in spawned[0].args


def test_a_slash_command_is_a_print_of_its_own(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, opening=_SAID)
    agent = _agent()
    heard(agent)

    events = _turn(agent.new(tmp_path), "/review:quick now")

    (process,) = spawned
    assert process.args[-2:] == ["--print", "/review:quick now"]
    assert "--input-format" not in process.args
    assert events[-1].text == "done"


@pytest.mark.parametrize(
    ("told", "why"),
    [
        ({"status": "FAILED"}, "FAILED"),
        (
            {"status": "FAILED", "error": "the model is not here"},
            "the model is not here",
        ),
    ],
)
def test_a_result_that_did_not_succeed_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, told: dict[str, str], why: str
) -> None:
    spawning(monkeypatch, answers=_answering(_result(None, **told)))
    agent = _agent()
    heard(agent)

    with pytest.raises(Failed) as failed:
        _turn(agent.new(tmp_path))

    assert failed.value.stderr == why

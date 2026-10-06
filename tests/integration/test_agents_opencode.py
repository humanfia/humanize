"""opencode and mimocode, driven against one stand-in installed under both names.

mimocode is opencode under Xiaomi's name, so one script stands in for both: an `opencode run`
that takes the prompt on stdin and answers in the JSON events of one turn, exiting zero even
for a turn that failed. Each turn is a run of its own, resuming the session by `--session`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import (
    AgentBase,
    AgentConfig,
    Failed,
    MimoCodeAgent,
    MimoCodeAgentConfig,
    OpencodeAgent,
    OpencodeAgentConfig,
)
from tests.integration.doubles_agents import Standins, kinds, standins

if TYPE_CHECKING:
    from pathlib import Path

OPENCODE = r"""
import time

said = sys.stdin.read()
note(said)
session = flags.get("--session", "ses_stand_in")


def part(kind, **rest):
    out({"type": kind, "sessionID": session, "part": rest})


if said == "quiet":
    sys.exit(0)
if said == "crash":
    print("opencode: something broke", file=sys.stderr, flush=True)
    sys.exit(3)
if said == "hang":
    time.sleep(600)
if said == "unfinished":
    out({"type": "error", "sessionID": session, "error": {"name": "UnknownError",
         "data": {"message": "it could not finish"}}})
    sys.exit(0)
part("step_start", id="p0", type="step-start")
part("tool_use", id="p1", type="tool", tool="bash",
     state={"status": "completed", "input": {"command": "echo " + said},
            "title": "echo " + said})
part("reasoning", id="p2", type="reasoning", text="thinking about " + said)
part("step_finish", id="p3", type="step-finish", reason="tool-calls",
     tokens={"total": 9, "input": 5, "output": 2, "reasoning": 1,
             "cache": {"read": 1, "write": 0}})
part("text", id="p4", type="text", text=said)
part("step_finish", id="p5", type="step-finish", reason="stop",
     tokens={"total": 3, "input": 2, "output": 1, "reasoning": 0,
             "cache": {"read": 0, "write": 0}})
"""

BACKENDS: list[tuple[str, type[AgentBase], AgentConfig, str]] = [
    (
        "opencode",
        OpencodeAgent,
        OpencodeAgentConfig(model="opencode/stand-in", effort="high"),
        "OPENCODE_PERMISSION",
    ),
    (
        "mimo",
        MimoCodeAgent,
        MimoCodeAgentConfig(model="xiaomi/stand-in", effort="low"),
        "MIMOCODE_PERMISSION",
    ),
]


@pytest.fixture(params=BACKENDS, ids=[one[0] for one in BACKENDS])
def backend(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Standins, AgentBase, str]:
    name, kind, config, permits = request.param
    held = standins(tmp_path, monkeypatch, permits)
    held.install(name, OPENCODE)
    return held, kind(config), permits


def test_a_turn_says_what_it_did_and_what_it_spent(
    backend: tuple[Standins, AgentBase, str],
) -> None:
    _, agent, _ = backend

    said = list(agent.new().stream("hello"))

    assert kinds(said) == ["tool", "reasoning", "text", "result"]
    assert said[0].text == "bash echo hello"
    assert said[-1].text == "hello"
    assert dict(said[-1].tokens) == {agent.config.model: 12}


def test_each_turn_is_a_run_resuming_the_session_it_opened(
    backend: tuple[Standins, AgentBase, str],
) -> None:
    stands, agent, _ = backend
    session = agent.new()

    assert session("one") == "one"
    assert session("two") == "two"

    first, second = stands.calls()
    assert first.argv[:3] == ["run", "--format", "json"]
    assert first.flag("--model") == agent.config.model
    assert first.flag("--variant") == agent.config.effort
    assert first.flag("--session") is None
    assert second.flag("--session") == session.id == "ses_stand_in"
    assert first.pid != second.pid
    assert first.env["HMZ_TEST_INHERITED"] == "from-the-flow"


def test_an_error_event_is_a_failed_turn_leaving_the_session_unopened(
    backend: tuple[Standins, AgentBase, str],
) -> None:
    _, agent, _ = backend
    session = agent.new()

    with pytest.raises(Failed):
        session("unfinished")
    with pytest.raises(RuntimeError):
        _ = session.id
    assert session("unfinished", suppress=True) == ""


def test_a_run_that_says_nothing_or_exits_non_zero_is_a_failed_turn(
    backend: tuple[Standins, AgentBase, str],
) -> None:
    _, agent, _ = backend

    with pytest.raises(Failed):
        agent.new()("quiet")
    with pytest.raises(Failed) as failed:
        agent.new()("crash")
    assert failed.value.returncode == 3
    assert "something broke" in str(failed.value.stderr)


def test_what_the_agent_may_do_is_said_in_the_cli_s_own_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stands = standins(tmp_path, monkeypatch, "OPENCODE_PERMISSION")
    stands.install("opencode", OPENCODE)

    OpencodeAgent(
        OpencodeAgentConfig(model="opencode/m", effort="high", permission="read-only")
    ).new()("hi")
    OpencodeAgent(OpencodeAgentConfig(model="opencode/m", effort="high")).new()("hi")

    reading, unsaid = stands.calls()
    permitted = json.loads(reading.env["OPENCODE_PERMISSION"] or "{}")
    assert permitted["edit"] == "deny"
    assert permitted["bash"] == "deny"
    assert unsaid.env["OPENCODE_PERMISSION"] is None


def test_a_hung_run_is_ended_by_the_watchdog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    standins(tmp_path, monkeypatch).install("opencode", OPENCODE)
    monkeypatch.setenv("HUMANIZE_WATCHDOG", "1")

    with pytest.raises(Failed):
        OpencodeAgent(OpencodeAgentConfig(model="opencode/m", effort="high")).new()(
            "hang"
        )


def test_a_run_cannot_be_talked_to_mid_turn_nor_given_a_goal(
    backend: tuple[Standins, AgentBase, str],
) -> None:
    _, agent, _ = backend

    with pytest.raises(NotImplementedError):
        agent.new().interject("hello?")
    with pytest.raises(NotImplementedError):
        agent.new().pursue("the suite passes")

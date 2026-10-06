"""MiniMax Code, driven through `MiniMaxCodeAgent` against a stand-in `mcode` on PATH.

The stand-in is an `mcode exec --output-format stream-json`: one run per turn with the prompt
on stdin, answering in sequenced JSON lines -- the turn's tool calls, reasoning and message as
`item.*`, then `turn.completed` with what it spent and `exec.completed` with the result. A turn
that failed says `turn.failed`, and exits non-zero. A session is carried on by `--session`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import (
    SUBAGENTS,
    Failed,
    MiniMaxCodeAgent,
    MiniMaxCodeAgentConfig,
    Moment,
    Occasion,
)
from tests.integration.doubles_agents import Standins, kinds, standins

if TYPE_CHECKING:
    from pathlib import Path

MODEL = "custom_provider:gateway/minimax-stand-in"
CONFIG = MiniMaxCodeAgentConfig(model=MODEL, effort="", permission="bypass")

MCODE = r"""
prompt = sys.stdin.read()
note(prompt)
session = flags.get("--session", "mvs_stand_in")
turn = "turn_1"
at = [0]


def say(kind, **rest):
    at[0] += 1
    out({"schemaVersion": 1, "sequence": at[0], "timestampMs": 1, "runId": "exec_" + turn,
         "sessionId": session, "turnId": turn, "type": kind, **rest})


def tool(call, name, status, **rest):
    return {"id": call, "type": "tool_call",
            "toolCall": {"id": call, "name": name, "status": status, **rest}}


model = {"providerId": "custom_provider:gateway", "modelId": "minimax-stand-in"}
say("exec.started")
say("session.resumed" if "--session" in flags else "session.started")
say("turn.started")
say("item.started", item=tool("call_1", "bash", 4))
say("item.completed", item=tool("call_1", "bash", 2, input={"command": "ls src"},
                                 output={"content": [{"type": "text", "text": "x.py"}]}))
if prompt == "fleet":
    ask = {"description": "read the tests", "prompt": "read them", "subagent_type": "explore"}
    say("item.started", item=tool("call_2", "task", 4))
    say("item.updated", item=tool("call_2", "task", 1, input=ask))
    say("item.completed", item=tool("call_2", "task", 2, input=ask,
                                     output={"content": [{"type": "text", "text": "done"}]}))
say("item.completed", item={"id": "m1:reasoning", "type": "reasoning", "content": "hmm"})
say("item.completed", item={"id": "m1:message", "type": "agent_message", "content": prompt})
if prompt == "unfinished":
    error = {"category": "runtime", "message": "it could not finish", "retryable": False}
    say("turn.failed", status="failed", error=error, durationMs=12)
    say("exec.completed", result={"type": "exec.result", "sessionId": session,
                                  "turnId": turn, "status": "failed", "error": error})
    print("mcode exec failed: it could not finish.", file=sys.stderr)
    raise SystemExit(4)
usage = {"inputTokens": 130, "outputTokens": 12, "cacheReadTokens": 90, "totalTokens": 142}
say("turn.completed", model=model, usage=usage, usageIncomplete=False, durationMs=7)
say("exec.completed", result={"type": "exec.result", "sessionId": session, "turnId": turn,
                              "status": "succeeded", "model": model, "usage": usage,
                              "output": prompt})
"""


@pytest.fixture
def mcode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch)
    held.install("mcode", MCODE)
    return held


def test_a_turn_says_what_it_did_and_what_it_spent(mcode: Standins) -> None:
    said = list(MiniMaxCodeAgent(CONFIG).new().stream("hello"))

    assert kinds(said) == ["tool", "reasoning", "text", "result"]
    assert "ls src" in said[0].text
    assert said[-1].text == "hello"
    assert said[-1].spent.output == 12


def test_each_turn_is_a_run_of_exec_carrying_the_session_on(mcode: Standins) -> None:
    session = MiniMaxCodeAgent(CONFIG).new()

    assert session("one") == "one"
    assert session("two") == "two"

    first, second = mcode.calls()
    assert first.argv[0] == "exec"
    assert first.flag("--output-format") == "stream-json"
    assert first.flag("--model") == MODEL
    assert first.flag("--session") is None
    assert second.flag("--session") == session.id == "mvs_stand_in"
    assert mcode.said() == ["one", "two"]


def test_an_agent_it_starts_of_its_own_fires_the_subagent_moments(
    mcode: Standins,
) -> None:
    agent = MiniMaxCodeAgent(CONFIG)
    seen: list[Occasion] = []
    for moment in SUBAGENTS:
        agent.hooks.on(moment, seen.append)

    said = list(agent.new().stream("fleet"))

    assert "subagent" in kinds(said)
    assert [one.moment for one in seen] == [Moment.SUBAGENT_START, Moment.SUBAGENT_STOP]


def test_a_failed_turn_is_a_failure_with_what_it_said(mcode: Standins) -> None:
    session = MiniMaxCodeAgent(CONFIG).new()

    with pytest.raises(Failed, match="it could not finish") as failed:
        session("unfinished")

    assert failed.value.returncode == 4
    with pytest.raises(RuntimeError):
        _ = session.id

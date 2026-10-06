"""Cursor Agent, driven through `CursorAgent` against a stand-in `cursor-agent` on PATH.

The stand-in is a `cursor-agent --print --output-format stream-json`: one run per turn, the
prompt as the last word of its command line, answering in NDJSON that names the chat and ends
on a `result`. A turn resumes its chat with `--resume=<id>`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import (
    SUBAGENTS,
    CursorAgent,
    CursorAgentConfig,
    Failed,
    Moment,
    Occasion,
)
from tests.integration.doubles_agents import Standins, kinds, standins

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = CursorAgentConfig(model="composer-2.5", effort="high")

CURSOR = r"""
import time

prompt = argv[-1]
note(prompt)
resumed = next((one for one in argv if one.startswith("--resume=")), "")
chat = resumed.partition("=")[2] or "chat-0001"

if prompt == "crash":
    print("cursor-agent: something broke", file=sys.stderr, flush=True)
    sys.exit(3)
if prompt == "hang":
    time.sleep(600)
out({"type": "system", "subtype": "init", "session_id": chat, "cwd": ".",
     "model": flags.get("--model", ""), "permissionMode": "default"})
out({"type": "tool_call", "subtype": "started", "call_id": "call-1",
     "tool_call": {"readToolCall": {"args": {"path": "src/x.py"}}}, "session_id": chat})
if prompt == "fleet":
    task = {"description": "read the tests"}
    out({"type": "tool_call", "subtype": "started", "call_id": "call-2",
         "tool_call": {"taskToolCall": {"args": task}}, "session_id": chat})
    out({"type": "tool_call", "subtype": "completed", "call_id": "call-2",
         "tool_call": {"taskToolCall": {"args": task,
                                        "result": {"success": {"content": "done"}}}},
         "session_id": chat})
out({"type": "assistant", "session_id": chat,
     "message": {"role": "assistant", "content": [{"type": "text", "text": prompt}]}})
if prompt == "unfinished":
    out({"type": "result", "subtype": "error", "is_error": True,
         "result": "it could not finish", "session_id": chat})
else:
    out({"type": "result", "subtype": "success", "is_error": False, "duration_ms": 12,
         "result": prompt, "session_id": chat,
         "usage": {"inputTokens": 100, "outputTokens": 20, "cacheReadTokens": 5,
                   "cacheWriteTokens": 3}})
"""


@pytest.fixture
def cursor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch)
    held.install("cursor-agent", CURSOR)
    return held


def test_a_turn_says_what_it_did_and_what_it_spent(cursor: Standins) -> None:
    said = list(CursorAgent(CONFIG).new().stream("hello"))

    assert kinds(said) == ["tool", "text", "result"]
    assert "src/x.py" in said[0].text
    assert said[-1].text == "hello"
    assert sum(said[-1].tokens.values()) == 128
    assert said[-1].spent.output == 20


def test_each_turn_is_a_run_resuming_the_chat_it_opened(cursor: Standins) -> None:
    session = CursorAgent(CONFIG).new()

    assert session("one") == "one"
    assert session("two") == "two"

    first, second = cursor.calls()
    assert "--print" in first.argv
    assert first.flag("--output-format") == "stream-json"
    assert not any(one.startswith("--resume") for one in first.argv)
    assert f"--resume={session.id}" in second.argv
    assert session.id == "chat-0001"
    assert first.env["HMZ_TEST_INHERITED"] == "from-the-flow"


def test_a_subagent_it_sends_out_is_said_and_fires_its_moments(
    cursor: Standins,
) -> None:
    agent = CursorAgent(CONFIG)
    seen: list[Moment] = []

    def watches(occasion: Occasion) -> None:
        seen.append(occasion.moment)

    for moment in SUBAGENTS:
        agent.hooks.on(moment, watches)

    said = list(agent.new().stream("fleet"))

    assert kinds(said) == ["tool", "subagent", "subagent-ends", "text", "result"]
    assert "read the tests" in said[1].text
    assert seen == [Moment.SUBAGENT_START, Moment.SUBAGENT_STOP]


def test_a_result_marked_as_an_error_is_a_failed_turn(cursor: Standins) -> None:
    session = CursorAgent(CONFIG).new()

    with pytest.raises(Failed, match="it could not finish"):
        session("unfinished")
    with pytest.raises(RuntimeError):
        _ = session.id


def test_a_run_that_exits_non_zero_is_a_failed_turn(cursor: Standins) -> None:
    with pytest.raises(Failed) as failed:
        CursorAgent(CONFIG).new()("crash")

    assert failed.value.returncode == 3
    assert "something broke" in str(failed.value.stderr)


def test_a_hung_run_is_ended_by_the_watchdog(
    cursor: Standins, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_WATCHDOG", "1")

    with pytest.raises(Failed):
        CursorAgent(CONFIG).new()("hang")

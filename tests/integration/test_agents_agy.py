"""Antigravity, driven through `AntigravityCLIAgent` against a stand-in `agy` on PATH.

The stand-in is an `agy --print` answering in the events of one turn -- an `init`, a
`step_update` per step, and a `result` -- or, given `--input-format stream-json`, the same for
each message on a stdin held open. Like the real one it insists on hearing the effort exactly
once: from the model's name, or from `--effort`, never both and never neither.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import (
    AntigravityCLIAgent,
    AntigravityCLIAgentConfig,
    Failed,
)
from tests.integration.doubles_agents import Standins, kinds, standins

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AntigravityCLIAgentConfig(model="gemini-stand-in", effort="high")

AGY = r"""
import time

talk = flags.get("--conversation", "conv-agy")
model = flags.get("--model", "")
carried = any(model.endswith("-" + rung) for rung in ("high", "medium", "low"))
if carried and "--effort" in argv:
    sys.exit("--model %s conflicts with --effort" % model)
if not carried and "--effort" not in argv:
    sys.exit("--model %s requires --effort" % model)


def step(index, state, kind, **rest):
    out({"event": "step_update", "step_update": {"conversation_id": talk,
         "step_index": index, "state": state, "step_type": kind, **rest}})


def turn(said):
    note(said)
    if said == "crash":
        print("agy: something broke", file=sys.stderr, flush=True)
        sys.exit(3)
    if said == "hang":
        time.sleep(600)
    out({"event": "init", "conversation_id": talk,
         "init": {"cwd": os.getcwd(), "permission_mode": "always-proceed", "model": model}})
    if said == "unfinished":
        out({"event": "result", "result": {"conversation_id": talk, "status": "ERROR",
             "response": "", "error": "it could not finish", "num_turns": 0,
             "usage": {"input_tokens": 1, "output_tokens": 0}}})
        sys.exit(0)
    step(0, "ACTIVE", "THINKING", text_delta="thinking about " + said)
    step(1, "ACTIVE", "TOOL", tool_name="run_command", tool_info={"command": "echo " + said})
    step(1, "DONE", "TOOL", tool_name="run_command")
    step(2, "ACTIVE", "RESPONSE", text_delta=said)
    out({"event": "result", "result": {"conversation_id": talk, "status": "SUCCESS",
         "response": said, "num_turns": 1, "duration_seconds": 1,
         "usage": {"input_tokens": 5, "output_tokens": 2, "thinking_tokens": 1,
                   "cache_read_tokens": 1}}})


if flags.get("--input-format") == "stream-json":
    for line in sys.stdin:
        turn(json.loads(line)["message"]["content"])
else:
    turn(flags.get("--print", ""))
"""


@pytest.fixture
def agy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch)
    held.install("agy", AGY)
    return held


def test_a_turn_says_what_it_did_and_what_it_spent(agy: Standins) -> None:
    said = list(AntigravityCLIAgent(CONFIG).new().stream("hello"))

    assert kinds(said) == ["reasoning", "tool", "text", "result"]
    assert "echo hello" in said[1].text
    assert said[-1].text == "hello"
    assert dict(said[-1].tokens) == {"gemini-stand-in": 9}
    assert said[-1].spent.output == 2


def test_one_process_holds_the_conversation_and_hears_the_effort_once(
    agy: Standins,
) -> None:
    session = AntigravityCLIAgent(CONFIG).new()

    assert session("one") == "one"
    assert session("two") == "two"

    first, second = agy.calls()
    assert first.flag("--model") == "gemini-stand-in"
    assert first.flag("--effort") == "high"
    assert session.id == "conv-agy"
    assert first.flag("--input-format") == "stream-json"
    assert first.pid == second.pid
    assert first.env["HMZ_TEST_INHERITED"] == "from-the-flow"


def test_a_model_whose_name_carries_its_rung_is_given_no_effort(agy: Standins) -> None:
    config = AntigravityCLIAgentConfig(model="gemini-stand-in-low", effort="low")

    assert AntigravityCLIAgent(config).new()("hello") == "hello"
    assert agy.calls()[0].flag("--effort") is None


def test_a_result_that_is_not_success_is_a_failed_turn(agy: Standins) -> None:
    with pytest.raises(Failed, match="it could not finish"):
        AntigravityCLIAgent(CONFIG).new()("unfinished")


def test_an_agy_that_exits_mid_turn_fails_it(agy: Standins) -> None:
    with pytest.raises(Failed) as failed:
        AntigravityCLIAgent(CONFIG).new()("crash")

    assert "something broke" in str(failed.value.stderr)


def test_a_hung_turn_is_ended_by_the_watchdog(
    agy: Standins, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_WATCHDOG", "1")

    with pytest.raises(Failed):
        AntigravityCLIAgent(CONFIG).new()("hang")

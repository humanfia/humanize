"""Qwen Code, driven through `QwenCodeAgent` against a stand-in `qwen` on PATH.

The stand-in takes ordinary turns as stream-json messages on a stdin held open, and a turn held
to a shape as plain stdin, answering both in the same `system`, `assistant` and `result`
records. A turn that failed says so in its result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel

from hmz.coganchor.agents import Failed, QwenCodeAgent, QwenCodeAgentConfig
from tests.integration.doubles_agents import Standins, kinds, standins

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = QwenCodeAgentConfig(model="qwen-stand-in", effort="high")

QWEN = r"""
import time

session = flags.get("--resume") or flags.get("--session-id") or "ses-qwen"
total = {}


def record(said):
    out({"session_id": session, **said})


def turn(said):
    note(said)
    if said == "crash":
        print("qwen: something broke", file=sys.stderr, flush=True)
        sys.exit(3)
    if said == "hang":
        time.sleep(600)
    record({"type": "system", "subtype": "init", "model": flags.get("--model")})
    if said == "unfinished":
        record({"type": "result", "subtype": "error_during_execution", "is_error": True,
                "result": "", "error": {"message": "it could not finish"},
                "usage": {"input_tokens": 1, "output_tokens": 0}})
        return
    answer = json.dumps({"value": said}) if "--json-schema" in argv else said
    record({"type": "assistant", "message": {"id": "m1", "role": "assistant", "content": [
        {"type": "thinking", "thinking": "thinking about " + said},
        {"type": "tool_use", "id": "c1", "name": "run_shell_command",
         "input": {"command": "echo " + said}},
        {"type": "text", "text": answer}],
        "usage": {"input_tokens": 5, "output_tokens": 2, "cache_read_input_tokens": 1}}})
    for key, value in {"input_tokens": 5, "output_tokens": 2,
                       "cache_read_input_tokens": 1}.items():
        total[key] = total.get(key, 0) + value
    record({"type": "result", "subtype": "success", "is_error": False, "result": answer,
            "usage": total})


if flags.get("--input-format") == "stream-json":
    note()
    for line in sys.stdin:
        turn(json.loads(line)["message"]["content"])
else:
    turn(sys.stdin.read())
"""


class Shape(BaseModel):
    value: str


@pytest.fixture
def qwen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch)
    held.install("qwen", QWEN)
    return held


def test_a_turn_says_what_it_did_and_what_it_spent(qwen: Standins) -> None:
    said = list(QwenCodeAgent(CONFIG).new().stream("hello"))

    assert kinds(said) == ["reasoning", "tool", "text", "result"]
    assert "echo hello" in said[1].text
    assert said[-1].text == "hello"
    assert said[-1].spent.output == 2
    assert sum(said[-1].tokens.values()) == 8


def test_one_process_holds_the_session_across_turns(qwen: Standins) -> None:
    session = QwenCodeAgent(CONFIG).new()

    assert session("one") == "one"
    assert session("two") == "two"

    launch = qwen.calls()[0]
    assert len({one.pid for one in qwen.calls()}) == 1
    assert launch.flag("--model") == "qwen-stand-in"
    assert launch.flag("--input-format") == "stream-json"
    assert qwen.said() == ["one", "two"]
    assert launch.flag("--session-id") == session.id


def test_a_turn_held_to_a_shape_answers_with_the_object(qwen: Standins) -> None:
    session = QwenCodeAgent(CONFIG).new()

    assert session("shaped", schema=Shape) == Shape(value="shaped")
    assert session("after") == "after"

    shaped = next(one for one in qwen.calls() if one.stdin == "shaped")
    after = next(one for one in qwen.calls() if one.stdin == "after")
    assert shaped.flag("--json-schema") is not None
    assert shaped.flag("--session-id") == session.id
    assert after.flag("--resume") == session.id
    assert shaped.pid != after.pid


def test_a_result_marked_as_an_error_is_a_failed_turn(qwen: Standins) -> None:
    with pytest.raises(Failed, match="it could not finish"):
        QwenCodeAgent(CONFIG).new()("unfinished")


def test_a_qwen_that_exits_mid_turn_fails_it(qwen: Standins) -> None:
    with pytest.raises(Failed) as failed:
        QwenCodeAgent(CONFIG).new()("crash")

    assert failed.value.returncode == 3
    assert "something broke" in str(failed.value.stderr)


def test_a_hung_turn_is_ended_by_the_watchdog(
    qwen: Standins, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_WATCHDOG", "1")

    with pytest.raises(Failed):
        QwenCodeAgent(CONFIG).new()("hang")

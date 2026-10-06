"""pi, driven through `PiAgent` against a stand-in `pi --mode rpc` on PATH.

The stand-in holds one process for the whole session and takes its turns as JSON commands on
stdin: a `prompt` is answered with the events of one agent run -- a tool call arriving in
pieces, the thinking, the words -- and ends on `agent_settled`; a `steer` mid-run is a word put
into it; an `abort` stops it.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import Failed, PiAgent, PiAgentConfig
from tests.integration.doubles_agents import Standins, kinds, standins

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = PiAgentConfig(model="openai-codex/stand-in", effort="high")

PI = r"""
import queue, threading, time

note()
lines = queue.Queue()
held = []
SPENT = {"input": 10, "output": 5, "cacheRead": 2, "cacheWrite": 1}


def reading():
    for line in sys.stdin:
        lines.put(line)
    lines.put(None)


def take(waiting=None):
    if held:
        return held.pop(0)
    try:
        line = lines.get(timeout=waiting) if waiting else lines.get()
    except queue.Empty:
        return None
    return None if line is None else json.loads(line)


def part(event):
    out({"type": "message_update", "usage": SPENT, "assistantMessageEvent": event})


def steered(said):
    note("steer " + said)
    out({"type": "message_start", "message": {"role": "user",
         "content": [{"type": "text", "text": said}]}})


threading.Thread(target=reading, daemon=True).start()
while (told := take()) is not None:
    if told["type"] == "steer":
        steered(told["message"])
        continue
    if told["type"] != "prompt":
        note(told["type"])
        out({"type": "response", "command": told["type"], "success": True})
        continue
    said = told["message"]
    note(said)
    if said == "rejected":
        out({"type": "response", "command": "prompt", "success": False,
             "error": "pi would not take it"})
        sys.exit(1)
    if said == "crash":
        print("pi: something broke", file=sys.stderr, flush=True)
        sys.exit(3)
    out({"type": "response", "command": "prompt", "success": True})
    out({"type": "agent_start"})
    out({"type": "message_start", "message": {"role": "user",
         "content": [{"type": "text", "text": said}]}})
    part({"type": "thinking_end", "contentIndex": 0, "content": "thinking about " + said})
    part({"type": "toolcall_start", "contentIndex": 2, "id": "call_1", "toolName": "bash"})
    for piece in ('{"comm', 'and": "echo ', said + '"}'):
        part({"type": "toolcall_delta", "contentIndex": 2, "delta": piece})
    part({"type": "toolcall_end", "contentIndex": 2,
          "toolCall": {"type": "toolCall", "id": "call_1", "name": "bash",
                       "arguments": {"command": "echo " + said}}})
    if said == "slow":
        while (more := take()) is not None and more["type"] != "abort":
            held.append(more)
        note("abort")
        out({"type": "message_end", "message": {"role": "toolResult",
             "toolCallId": "call_1", "isError": True,
             "content": [{"type": "text", "text": "Operation aborted"}]}})
        out({"type": "agent_end"})
        out({"type": "agent_settled"})
        out({"type": "response", "command": "abort", "success": True})
        continue
    part({"type": "text_end", "contentIndex": 1, "content": said})
    errored = {"errorMessage": "it could not finish"} if said == "unfinished" else {}
    out({"type": "message_end", "message": {"role": "assistant",
         "content": [] if errored else [{"type": "text", "text": said}],
         "usage": SPENT, **errored}})
    out({"type": "agent_end"})
    if errored:
        out({"type": "agent_settled"})
        sys.exit(1)
    # A run told `start` goes on until a word is steered into it, which it takes before
    # settling: one run, however many things were said in it.
    if said == "start":
        while (more := take(30)) is not None and more["type"] != "steer":
            held.append(more)
        if more is not None:
            steered(more["message"])
    out({"type": "agent_settled"})
"""


@pytest.fixture
def pi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch)
    held.install("pi", PI)
    return held


def test_a_turn_says_what_it_did_and_what_it_spent(pi: Standins) -> None:
    said = list(PiAgent(CONFIG).new().stream("hello"))

    assert kinds(said) == ["reasoning", "tool", "text", "result"]
    assert said[1].text == "bash echo hello"
    assert said[-1].text == "hello"
    assert dict(said[-1].tokens) == {"openai-codex/stand-in": 18}


def test_one_process_holds_the_session_across_turns(pi: Standins) -> None:
    session = PiAgent(CONFIG).new()

    assert session("one") == "one"
    assert session("two") == "two"

    launch, *_ = pi.calls()
    assert len({one.pid for one in pi.calls()}) == 1
    assert launch.argv[:2] == ["--mode", "rpc"]
    assert launch.flag("--model") == "openai-codex/stand-in"
    assert launch.flag("--thinking") == "high"
    assert launch.flag("--session-id") == session.id
    assert pi.said() == ["one", "two"]


def test_a_word_put_in_mid_run_reaches_it(pi: Standins) -> None:
    session = PiAgent(CONFIG).new()
    said: list[str] = []

    for event in session.stream("start"):
        if event.kind == "reasoning":
            session.interject("actually, stop")
        said.append(event.kind)

    assert said.count("result") == 1
    assert "took" in said
    assert pi.said() == ["start", "steer actually, stop"]
    assert session("after") == "after"


def test_a_turn_cut_off_is_aborted_and_the_session_goes_on(pi: Standins) -> None:
    session = PiAgent(CONFIG).new()

    def cuts() -> None:
        for event in session.stream("slow"):
            if event.kind == "tool":
                threading.Thread(target=session.cut, kwargs={"why": "stopped"}).start()

    cutting = threading.Thread(target=cuts)
    cutting.start()
    cutting.join(30)

    assert not cutting.is_alive()
    assert pi.said() == ["slow", "abort"]
    assert session("after") == "after"


def test_a_refused_prompt_and_an_errored_message_are_failed_turns(
    pi: Standins,
) -> None:
    session = PiAgent(CONFIG).new()

    with pytest.raises(Failed, match="pi would not take it"):
        session("rejected")
    with pytest.raises(Failed, match="it could not finish"):
        PiAgent(CONFIG).new()("unfinished")


def test_a_pi_that_exits_mid_session_fails_the_turn(pi: Standins) -> None:
    with pytest.raises(Failed) as failed:
        PiAgent(CONFIG).new()("crash")

    assert "something broke" in str(failed.value.stderr)


def test_an_agent_that_may_change_nothing_is_given_no_tools_that_would(
    pi: Standins,
) -> None:
    PiAgent(
        PiAgentConfig(
            model="openai-codex/stand-in", effort="high", permission="read-only"
        )
    ).new()("hello")

    assert pi.calls()[0].flag("--exclude-tools") == "bash,edit,write,powershell"

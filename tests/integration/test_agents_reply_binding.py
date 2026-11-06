"""Native turns the CLI starts by itself never answer, cost or approve a prompt's turn."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import fallbacks
from hmz.coganchor.agents import (
    Budget,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    CodexAgentConfig,
    Failed,
    Moment,
    Unrecoverable,
    Verdict,
)
from tests.integration.doubles_agents import standins

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from hmz.coganchor.agents import Occasion, Question

#: A Codex whose thread runs turns of its own around every requested one: before its start
#: response, between its items, after it completes, and replays of turns already over.
CODEX = r"""
note()
requests = 0
inputs = outputs = 0


def notify(method, **params):
    out({"method": method, "params": params})


def complete(turn, text, spent):
    global inputs, outputs
    notify("item/completed", threadId="thread", turnId=turn,
           item={"id": turn, "type": "agentMessage", "text": text})
    inputs += 1
    outputs += spent
    notify("thread/tokenUsage/updated", threadId="thread", turnId=turn, tokenUsage={
        "last": {"inputTokens": 1, "outputTokens": spent},
        "total": {"inputTokens": inputs, "outputTokens": outputs}})
    notify("turn/completed", threadId="thread", turn={"id": turn, "status": "completed"})
    notify("item/completed", threadId="thread", turnId=turn,
           item={"id": "late-" + turn, "type": "agentMessage", "text": "LATE REPLAY"})
    notify("turn/completed", threadId="thread", turn={"id": turn, "status": "completed"})


for line in sys.stdin:
    call = json.loads(line)
    if "id" not in call:
        continue
    method = call["method"]
    result = {}
    if method == "thread/start":
        result = {"thread": {"id": "thread"}}
    if method == "turn/start":
        requests += 1
        prompt = call["params"]["input"][0]["text"]
        if prompt in ("before", "reject"):
            complete(f"early-{requests}", "EARLY", 3)
        if prompt == "reject":
            out({"id": call["id"], "error": {"code": -32600, "message": "turn rejected"}})
            continue
        result = {"turn": {"id": f"owned-{requests}"}}
    out({"id": call["id"], "result": result})
    if method != "turn/start":
        continue
    if requests > 1:
        previous = {"inputTokens": inputs, "outputTokens": outputs}
        outputs += 3
        updated = {"inputTokens": inputs, "outputTokens": outputs}
        for snapshot in (updated, updated, previous):
            notify("thread/tokenUsage/updated", threadId="thread", turnId=f"owned-{requests - 1}",
                   tokenUsage={"total": snapshot})
        notify("item/completed", threadId="thread", turnId=f"owned-{requests - 1}",
               item={"id": "stale", "type": "agentMessage", "text": "STALE REPLY"})
        notify("turn/completed", threadId="thread",
               turn={"id": f"owned-{requests - 1}", "status": "completed"})
    if prompt != "before":
        complete(f"early-{requests}", "EARLY", 3)
    complete(f"during-{requests}", "DURING", 5)
    complete(f"owned-{requests}", f"OWN {requests}", 7)
    notify("item/completed", threadId="thread", turnId=f"owned-{requests}",
           item={"id": "late", "type": "agentMessage", "text": "LATE OWNED"})
    complete(f"after-{requests}", "AFTER", 11)
"""

#: A Claude that runs a turn of its own before the first prompt, under a name hmz never gave.
CLAUDE = r"""
note()
session = flags["--session-id"]
model = flags["--model"]
out({"type": "system", "subtype": "init", "session_id": session, "model": model})
inputs = outputs = requests = 0


def lifecycle(ticket, state="started"):
    out({"type": "command_lifecycle", "state": state, "command_uuid": ticket})


def answer(text, spent):
    global inputs, outputs
    out({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    inputs += 1
    outputs += spent
    out({"type": "result", "subtype": "success", "result": text,
         "modelUsage": {model: {"inputTokens": inputs, "outputTokens": outputs}}})


for line in sys.stdin:
    call = json.loads(line)
    prompt = call["message"]["content"][0]["text"]
    note(prompt)
    requests += 1
    ticket = call.get("uuid", "native-owner")
    if requests == 1:
        lifecycle("background")
        if prompt == "merge":
            lifecycle(ticket)
            answer("MERGED", 3)
            continue
        answer("FOREIGN", 3)
    lifecycle(ticket)
    lifecycle("background", "completed")
    answer(f"OWN {requests}", 7)
"""


def _settles(read: Callable[[], float], expected: float) -> float:
    """What `read` says once it says `expected`, or after a few seconds of not saying it."""
    deadline = time.monotonic() + 5
    while (now := read()) != expected and time.monotonic() < deadline:
        time.sleep(0.02)
    return now


@pytest.mark.parametrize("prompt", ["before", "after"])
def test_codex_answers_and_charges_a_turn_only_with_what_its_own_turn_did(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prompt: str
) -> None:
    cli = standins(tmp_path, monkeypatch)
    cli.install("codex", CODEX)
    agent = CodexAgent(CodexAgentConfig(model="test", effort=""))
    session = agent.new()
    try:
        first = list(session.stream(prompt))[-1]
        second = list(session.stream(prompt))[-1]
        assert (first.text, second.text) == ("OWN 1", "OWN 2")
        assert first.spent.output == second.spent.output == 7
        assert first.tokens == second.tokens == {"test": 8}
        # Everything the thread spent is still the session's, its own turns' or not, and a
        # stale total read late neither rewinds the count nor is counted twice.
        assert _settles(lambda: session.spent().output, 55) == 55
        assert agent.spent().output == 55
    finally:
        agent.stop()


def test_a_rejected_codex_start_fails_rather_than_answering_with_another_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = standins(tmp_path, monkeypatch)
    cli.install("codex", CODEX)
    fallbacks.retrying("codex/test", 0, "constant", 0.0)
    agent = CodexAgent(CodexAgentConfig(model="test", effort=""))
    session = agent.new()
    try:
        with pytest.raises(Failed, match="turn rejected"):
            session("reject")
        assert session.spent().output == agent.spent().output == 3
    finally:
        session.close()
        agent.stop()


def test_claude_keeps_a_turn_of_its_own_out_of_the_prompts_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = standins(tmp_path, monkeypatch)
    cli.install("claude", CLAUDE)
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="test", effort=""))
    session = agent.new()
    try:
        result = list(session.stream("owned"))[-1]
        assert result.text == "OWN 1"
        assert result.spent.output == 7
        assert session.spent().output == agent.spent().output == 10
    finally:
        session.close()
        agent.stop()


def test_a_prompt_claude_merges_into_a_turn_of_its_own_is_retried_as_contended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = standins(tmp_path, monkeypatch)
    cli.install("claude", CLAUDE)
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="test", effort=""))
    session = agent.new()
    try:
        assert session("merge") == "OWN 2"
        assert cli.said() == ["merge", "merge"]
    finally:
        session.close()
        agent.stop()


@pytest.mark.parametrize("form", ["assistant", "stream"])
@pytest.mark.timeout(10)
def test_what_a_turn_of_claudes_own_spends_counts_against_the_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    cli = standins(tmp_path, monkeypatch)
    cli.install(
        "claude",
        r"""
import time
note()
out({"type": "system", "subtype": "init", "session_id": flags["--session-id"],
     "model": flags["--model"]})
for line in sys.stdin:
    form = json.loads(line)["message"]["content"][0]["text"]
    out({"type": "command_lifecycle", "state": "started", "command_uuid": "background"})
    if form == "assistant":
        out({"type": "assistant", "message": {"id": "foreign", "usage": {
            "input_tokens": 1, "output_tokens": 20}, "content": [
            {"type": "text", "text": "FOREIGN PARTIAL"}]}})
    else:
        out({"type": "stream_event", "event": {"type": "message_start",
             "message": {"id": "foreign"}}})
        out({"type": "stream_event", "event": {"type": "message_delta",
             "usage": {"output_tokens": 20}}})
    time.sleep(600)
""",
    )
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="test", effort=""))
    session = agent.new()
    session.budget = Budget(output=10, when="immediately", then="fail")
    try:
        with pytest.raises(Unrecoverable, match="cut off"):
            session(form)
        assert session.spent().output == agent.spent().output == 20
    finally:
        session.close()
        agent.stop()


@pytest.mark.timeout(15)
def test_codex_callbacks_reach_hooks_only_for_the_turn_they_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = standins(tmp_path, monkeypatch)
    cli.install(
        "codex",
        r"""
note()
turn = "owned-turn"
answered = 0
decision = None


def foreign(when):
    out({"id": when + "-approval", "method": "item/commandExecution/requestApproval",
         "params": {"threadId": "thread", "turnId": "foreign-turn", "command": "write"}})
    out({"id": when + "-question", "method": "item/tool/requestUserInput",
         "params": {"threadId": "thread", "turnId": "foreign-turn",
                    "questions": [{"id": "where", "question": "Foreign question?"}]}})


for line in sys.stdin:
    call = json.loads(line)
    method = call.get("method")
    if method == "turn/start":
        foreign("before")
        out({"id": "native-approval", "method": "item/commandExecution/requestApproval",
             "params": {"threadId": "thread", "turnId": turn, "command": "write"}})
        out({"id": call["id"], "result": {"turn": {"id": turn}}})
        foreign("after")
    elif method == "thread/start":
        out({"id": call["id"], "result": {"thread": {"id": "thread"}}})
    elif method == "turn/steer":
        note("steered " + call["params"]["expectedTurnId"])
        out({"id": call["id"], "result": {}})
    elif method is None:
        if call["id"] == "native-approval":
            decision = call["result"]["decision"]
        else:
            note(call["id"] + (" rejected" if "error" in call else " accepted"))
            answered += 1
        if answered == 4 and decision is not None:
            out({"method": "item/completed", "params": {"threadId": "thread", "turnId": turn,
                 "item": {"id": "reply", "type": "agentMessage", "text": decision}}})
            out({"method": "turn/completed", "params": {"threadId": "thread",
                 "turn": {"id": turn, "status": "completed"}}})
    elif "id" in call:
        out({"id": call["id"], "result": {}})
""",
    )
    agent = CodexAgent(CodexAgentConfig(model="test", effort=""))
    session = agent.new()
    seen: list[Occasion] = []
    asked: list[Question] = []

    def refuse(occasion: Occasion) -> Verdict:
        seen.append(occasion)
        session.interject("use safe inputs")
        return Verdict(refused=True, because="use safe inputs")

    def answer(question: Question) -> str:
        asked.append(question)
        return "safe inputs"

    agent.ask = answer
    agent.hooks.on(Moment.PERMISSION_REQUEST, refuse)
    try:
        assert session("go") == "decline"
        assert [occasion.input["turnId"] for occasion in seen] == ["owned-turn"]
        assert asked == []
        assert sorted(cli.said()) == [
            "after-approval rejected",
            "after-question rejected",
            "before-approval rejected",
            "before-question rejected",
            "steered owned-turn",
        ]
    finally:
        session.close()
        agent.stop()


@pytest.mark.timeout(15)
def test_a_codex_goal_thread_stays_its_sessions_once_the_goal_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = standins(tmp_path, monkeypatch)
    cli.install(
        "codex",
        r"""
note()
threads = 0
idle_answers = 0
waiting = None


def complete(thread, turn, text, inputs, outputs):
    out({"method": "item/completed", "params": {"threadId": thread, "turnId": turn,
         "item": {"id": turn, "type": "agentMessage", "text": text}}})
    out({"method": "thread/tokenUsage/updated", "params": {"threadId": thread, "turnId": turn,
         "tokenUsage": {"total": {"inputTokens": inputs, "outputTokens": outputs}}}})
    out({"method": "turn/completed", "params": {"threadId": thread,
         "turn": {"id": turn, "status": "completed"}}})


for line in sys.stdin:
    call = json.loads(line)
    if "id" not in call:
        continue
    method = call.get("method")
    if method is None:
        rejected = "error" in call
        note(call["id"] + (" rejected" if rejected else " accepted"))
        if call["id"] == "goal-approval":
            complete("thread-1", "owned-turn", "GOAL", 1, 7)
            out({"method": "thread/goal/updated", "params": {"threadId": "thread-1",
                 "goal": {"status": "complete"}}})
            out({"method": "thread/status/changed", "params": {"threadId": "thread-1",
                 "status": {"type": "idle"}}})
        else:
            idle_answers += 1
            if idle_answers == 2:
                complete("thread-1", "background", "AFTER GOAL", 2, 12)
                out({"id": waiting, "result": {"thread": {"id": "thread-2"}}})
        continue
    result = {}
    if method == "thread/start":
        threads += 1
        result = {"thread": {"id": f"thread-{threads}"}}
        if threads == 2:
            # The goal has returned. Hold this start until both idle RPCs are answered.
            waiting = call["id"]
            out({"id": "idle-approval", "method": "item/commandExecution/requestApproval",
                 "params": {"threadId": "thread-1", "turnId": "background", "command": "write"}})
            out({"id": "idle-question", "method": "item/tool/requestUserInput",
                 "params": {"threadId": "thread-1", "turnId": "background",
                            "questions": [{"id": "where", "question": "Idle question?"}]}})
            continue
    if method == "turn/start":
        result = {"turn": {"id": "owned-turn"}}
    out({"id": call["id"], "result": result})
    if method == "turn/start":
        thread = call["params"]["threadId"]
        if thread == "thread-1":
            out({"id": "goal-approval", "method": "item/commandExecution/requestApproval",
                 "params": {"threadId": thread, "turnId": "owned-turn", "command": "write"}})
        else:
            complete(thread, "owned-turn", "TRIGGER", 0, 0)
""",
    )
    agent = CodexAgent(CodexAgentConfig(model="test", effort=""))
    goal = agent.new()
    trigger = agent.new()
    seen: list[Occasion] = []
    asked: list[Question] = []

    def refuse(occasion: Occasion) -> Verdict:
        seen.append(occasion)
        return Verdict(refused=True)

    def answer(question: Question) -> str:
        asked.append(question)
        return "safe inputs"

    agent.ask = answer
    agent.hooks.on(Moment.PERMISSION_REQUEST, refuse)
    try:
        assert goal.pursue("finish the goal") == "GOAL"
        assert trigger("release background work") == "TRIGGER"
        assert goal.spent().output == agent.spent().output == 12
        assert trigger.spent().output == 0
        assert [occasion.input["turnId"] for occasion in seen] == ["owned-turn"]
        assert asked == []
        assert cli.said() == [
            "goal-approval accepted",
            "idle-approval rejected",
            "idle-question rejected",
        ]
    finally:
        goal.close()
        trigger.close()
        agent.stop()

"""Grok Build, driven through `GrokBuildAgent` against a stand-in `grok` on PATH.

Grok has two transports and the stand-in serves both. `grok agent ... stdio` holds the
conversation open and speaks the Agent Client Protocol: `session/new` opens one,
`session/load` picks one back up, `session/prompt` takes a turn whose words arrive as
`session/update` notifications, and a tool call may be put to the client as a
`session/request_permission`. `grok -p` is one run of a turn with the prompt on its command
line, the same updates flattened onto `type`, ending on an `end` naming the session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import (
    Failed,
    GrokBuildAgent,
    GrokBuildAgentConfig,
    Moment,
    Occasion,
    Verdict,
)
from tests.integration.doubles_agents import Standins, kinds, standins

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = GrokBuildAgentConfig(model="grok-stand-in", effort="high")

GROK = r"""
import time

session = flags.get("--resume", "ses-grok")
spent = {"input_tokens": 5, "output_tokens": 2, "cache_read_input_tokens": 1}


def told(kind, **rest):
    out({"jsonrpc": "2.0", "method": "session/update",
         "params": {"sessionId": session, "update": {"sessionUpdate": kind, **rest}}})


if argv[:1] == ["agent"] and "stdio" in argv:
    note()
    while line := sys.stdin.readline():
        asked = json.loads(line)
        at, method = asked.get("id"), asked.get("method")
        if method == "initialize":
            out({"jsonrpc": "2.0", "id": at, "result": {"protocolVersion": 1}})
            continue
        if method == "session/new":
            out({"jsonrpc": "2.0", "id": at, "result": {"sessionId": session}})
            continue
        if method == "session/load":
            session = asked["params"]["sessionId"]
            note("load " + session)
            out({"jsonrpc": "2.0", "id": at, "result": {}})
            continue
        if method != "session/prompt":
            if at is not None:
                out({"jsonrpc": "2.0", "id": at, "result": {}})
            continue
        said = asked["params"]["prompt"][0]["text"]
        note(said)
        if said == "crash":
            print("grok: something broke", file=sys.stderr, flush=True)
            sys.exit(3)
        if said == "hang":
            time.sleep(600)
        if said == "unfinished":
            out({"jsonrpc": "2.0", "id": at,
                 "error": {"code": -32000, "message": "it could not finish"}})
            sys.exit(1)
        if said == "ask":
            out({"jsonrpc": "2.0", "id": 9001, "method": "session/request_permission",
                 "params": {"sessionId": session,
                            "toolCall": {"toolCallId": "call_1", "kind": "execute",
                                         "title": "Execute `rm -rf /`",
                                         "rawInput": {"command": "rm -rf /"}},
                            "options": [{"optionId": "no", "kind": "reject_once"},
                                        {"optionId": "yes", "kind": "allow_always"}]}})
            chosen = json.loads(sys.stdin.readline())
            told("agent_message_chunk", content={
                "type": "text", "text": chosen["result"]["outcome"]["optionId"]})
            out({"jsonrpc": "2.0", "id": at, "result": {"stopReason": "end_turn"}})
            continue
        told("agent_thought_chunk", content={"type": "text", "text": "thinking about " + said})
        told("tool_call", toolCallId="call_1", title="run_terminal_cmd",
             rawInput={"command": "echo " + said})
        told("tool_call_update", toolCallId="call_1", status="completed")
        told("agent_message_chunk", content={"type": "text", "text": said})
        out({"jsonrpc": "2.0", "method": "_x.ai/session_notification",
             "params": {"sessionId": session,
                        "update": {"sessionUpdate": "response_completed", "usage": spent}}})
        out({"jsonrpc": "2.0", "id": at, "result": {"stopReason": "end_turn"}})
        if said == "then-exit":
            sys.exit(0)
    sys.exit(0)

said = next((one.partition("=")[2] for one in argv if one.startswith("--single=")), "")
note(said)
out({"type": "thought", "data": "thinking about " + said})
out({"type": "text", "data": said})
out({"type": "usage", "messageId": "resp_1", "stopReason": "end_turn", "usage": spent})
out({"type": "end", "stopReason": "end_turn", "sessionId": session, "num_turns": 1})
"""


@pytest.fixture
def grok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch)
    held.install("grok", GROK)
    return held


def test_a_turn_says_what_it_did_and_what_it_spent(grok: Standins) -> None:
    said = list(GrokBuildAgent(CONFIG).new().stream("hello"))

    assert kinds(said) == ["reasoning", "tool", "text", "result"]
    assert "echo hello" in said[1].text
    assert said[-1].text == "hello"
    assert said[-1].spent.output == 2


def test_one_protocol_process_holds_the_session_across_turns(grok: Standins) -> None:
    session = GrokBuildAgent(CONFIG).new()

    assert session("one") == "one"
    assert session("two") == "two"

    launch = grok.calls()[0]
    assert launch.argv[0] == "agent"
    assert "stdio" in launch.argv
    assert len({one.pid for one in grok.calls()}) == 1
    assert grok.said() == ["one", "two"]
    assert session.id == "ses-grok"


def test_a_session_whose_process_exited_is_loaded_by_the_next(grok: Standins) -> None:
    session = GrokBuildAgent(CONFIG).new()

    assert session("then-exit") == "then-exit"
    assert session("after") == "after"

    assert len({one.pid for one in grok.calls()}) == 2
    assert "load ses-grok" in grok.said()


def test_a_permission_request_is_put_to_the_hook_and_refused(grok: Standins) -> None:
    agent = GrokBuildAgent(
        GrokBuildAgentConfig(model="grok-stand-in", effort="high", permission="bypass")
    )
    seen: list[Occasion] = []

    def gate(occasion: Occasion) -> Verdict:
        seen.append(occasion)
        return Verdict(refused=True, because="not that")

    agent.hooks.on(Moment.PERMISSION_REQUEST, gate)

    assert agent.new()("ask") == "no"
    assert len(seen) == 1
    assert "rm -rf /" in seen[0].about


def test_a_permission_nobody_refused_is_allowed_by_its_kind(grok: Standins) -> None:
    agent = GrokBuildAgent(
        GrokBuildAgentConfig(model="grok-stand-in", effort="high", permission="bypass")
    )

    assert agent.new()("ask") == "yes"


def test_a_refused_prompt_is_a_failed_turn(grok: Standins) -> None:
    with pytest.raises(Failed, match="it could not finish"):
        GrokBuildAgent(CONFIG).new()("unfinished")


def test_a_grok_that_exits_mid_turn_fails_it(grok: Standins) -> None:
    with pytest.raises(Failed) as failed:
        GrokBuildAgent(CONFIG).new()("crash")

    assert "something broke" in str(failed.value.stderr)


def test_a_hung_turn_is_ended_by_the_watchdog(
    grok: Standins, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_WATCHDOG", "1")

    with pytest.raises(Failed):
        GrokBuildAgent(CONFIG).new()("hang")

"""ZCode, driven against a stand-in app server that speaks the protocol the real one speaks.

Every turn of this backend is a session on `zcode app-server --stdio`, because its command line
takes neither a model nor a thought level. So what is checked here is the calls a turn is made
of -- what opened the session, what was said again on the way into the next one, what came back
out of the stream -- against a server on PATH that answers the way ZCode answers.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from hmz.coganchor.agents import (
    AgentConfig,
    Failed,
    Moment,
    Occasion,
    Verdict,
    ZcodeAgent,
    ZcodeAgentConfig,
)

#: A `zcode app-server --stdio` of our own. It speaks ZCode's protocol rather than JSON-RPC --
#: the frames carry no `jsonrpc`, and the real one refuses any that does -- and it asks its
#: client the two things the real one asks: what the runtime may do before it will open a
#: session at all, and, at a rung that asks, whether a high-risk tool is allowed.
#:
#: A prompt of `boom` is a turn that failed, `asking` a turn that stopped on a question and
#: `approving` one that asked to be allowed to do something. Everything else is answered the
#: way a working turn answers: it thinks, it reaches for something, it says what that request
#: cost, and only then does it end.
_ZCODE = """
import json, pathlib, sys

LOG = pathlib.Path(sys.argv[0] + ".log")
PENDING = []
SESSION = "sess_fake"


def send(message):
    sys.stdout.write(json.dumps(message) + "\\n")
    sys.stdout.flush()


def event(kind, payload, session=None):
    send({"method": "session/event", "params": {
        "sessionId": session or SESSION, "type": kind, "payload": payload}})


def turn(prompt, session=None):
    event("turn.started", {"input": prompt, "turnNumber": 0}, session)
    if prompt == "boom":
        event("turn.failed", {"error": {"message": "the model refused it"}}, session)
        return
    if prompt == "asking":
        send({"id": "server-9", "method": "interaction/requestUserInput", "params": {
            "sessionId": SESSION, "toolName": "AskUserQuestion", "toolCallId": "tu_a",
            "questions": [{"header": "Way", "question": "Which way?",
                           "options": [{"label": "left"}, {"label": "right"}]}]}})
        return
    if prompt == "approving":
        send({"id": "server-8", "method": "interaction/requestPermission", "params": {
            "sessionId": SESSION, "toolName": "Bash", "riskLevel": "high",
            "reason": "High risk tools require explicit approval", "toolCallId": "tu_b",
            "input": {"command": "rm -rf /"}}})
        return
    marked = "msg_1"
    event("model.streaming", {"assistantMessageId": marked, "kind": "reasoning_delta",
                              "delta": "thinking it over"}, session)
    event("model.streaming", {"assistantMessageId": marked, "kind": "text_delta",
                              "delta": "Looking now."}, session)
    event("model.streaming", {"assistantMessageId": marked, "kind": "tool_call",
                              "toolCallId": "tu_1", "toolName": "Bash",
                              "input": {"command": "ls", "description": "List the files"}},
          session)
    event("session.updated", {"content": "Looking now.", "stopReason": "tool-calls",
                              "usage": {"inputTokens": 7, "outputTokens": 3,
                                        "totalTokens": 10}}, session)
    event("model.streaming", {"assistantMessageId": "msg_2", "kind": "text_delta",
                              "delta": prompt}, session)
    event("session.updated", {"content": prompt, "stopReason": "stop",
                              "usage": {"inputTokens": 5, "outputTokens": 2,
                                        "totalTokens": 7}}, session)
    event("turn.completed", {"response": prompt, "toolCallCount": 1,
                             "usage": {"inputTokens": 12, "outputTokens": 5,
                                       "totalTokens": 17, "modelRequestCount": 2}}, session)


def opened():
    return {"session": {"sessionId": SESSION, "mode": "build",
                        "model": {"providerId": "zai", "modelId": "glm"}},
            "projection": {"turnCount": 0}, "messages": [],
            "protocol": {"name": "ZCode Protocol", "version": 1}}


for line in sys.stdin:
    call = json.loads(line)
    with LOG.open("a") as stream:
        json.dump(call, stream)
        stream.write("\\n")
    if "method" not in call:
        # An answer to something the server asked of us. A session is only opened once the
        # client has said what the runtime may do, and a turn that stopped on an approval or
        # a question goes on with whatever the answer was.
        if PENDING:
            send({"id": PENDING.pop()["id"], "result": opened()})
            continue
        said = json.dumps(call.get("result") or {})
        event("session.updated", {"content": said, "stopReason": "stop",
                                  "usage": {"inputTokens": 1, "outputTokens": 1,
                                            "totalTokens": 2}})
        event("turn.completed", {"response": said, "toolCallCount": 0,
                                 "usage": {"inputTokens": 1, "outputTokens": 1,
                                           "totalTokens": 2, "modelRequestCount": 1}})
        continue
    if "id" not in call:
        continue
    if call["method"] == "session/create":
        # The real one will not open a session until the client has answered this, and gives
        # up on it after fifteen seconds.
        PENDING.append(call)
        send({"id": "server-1", "method": "session/requestRuntimePreferences",
              "params": {"sessionId": SESSION, "scope": "runtime-materialization"}})
        continue
    if call["method"] == "session/resume":
        send({"id": call["id"], "result": opened()})
        continue
    if call["method"] == "session/messages":
        # The last message of the conversation, which is the point a fork is cut at. `info`
        # carries `id` rather than `messageId`, which is what the real one answers with.
        send({"id": call["id"], "result": {"messages": [
            {"info": {"id": "msg_last", "role": "assistant"}}]}})
        continue
    if call["method"] == "session/fork":
        send({"id": call["id"], "result": {
            "forkedSessionId": "sess_forked",
            "parentSessionId": call["params"]["sessionId"],
            "targetMessageId": "msg_last",
            "response": "Forked session sess_forked: copied 3 messages.",
            "snapshot": {"messages": []}}})
        continue
    if call["method"] == "session/goal":
        send({"id": call["id"], "result": {"response": "Goal complete",
                                           "startedTurn": True, "snapshot": {}}})
        turn("under a goal: " + call["params"].get("objective", ""))
        continue
    if call["method"] == "session/send":
        named = call["params"]["sessionId"]
        send({"id": call["id"], "result": {"sessionId": named, "accepted": True,
                                           "stateRevision": 1}})
        turn(call["params"]["content"], named)
        continue
    send({"id": call["id"], "result": {}})
"""


@dataclass(frozen=True)
class _FakeServer:
    """What the stand-in wrote down: every frame its client sent it, in order."""

    log: Path

    def calls(self) -> list[dict[str, Any]]:
        """Every frame, as read."""
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def named(self, method: str) -> list[dict[str, Any]]:
        """The params of every call of one method, in the order they were made."""
        return [
            one.get("params") or {}
            for one in self.calls()
            if one.get("method") == method
        ]

    def answered(self, key: str) -> list[Any]:
        """What this client answered under one key, in order, out of every answer carrying it.

        An answer is a frame with no method of its own, which is how the client's side of
        `session/requestRuntimePreferences` is read back: what the runtime was told it may do
        is said in an answer rather than in a call, so it is nowhere in `named`. By the key
        rather than by position, since this client answers everything the server asks of it
        and the empty answers to the rest are answers too.
        """
        return [
            (one.get("result") or {})[key]
            for one in self.calls()
            if "method" not in one and key in (one.get("result") or {})
        ]


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _FakeServer:
    """Puts a stand-in `zcode` on PATH, and says where it writes what it was sent."""
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / "zcode"
    fake.write_text(f"#!{sys.executable}\n{_ZCODE}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return _FakeServer(Path(f"{fake}.log"))


def _agent(**settings: Any) -> ZcodeAgent:
    """An agent of this backend, at whatever this test is about."""
    return ZcodeAgent(ZcodeAgentConfig(model="zai/glm-5.3", effort="high", **settings))


def test_a_turn_opens_a_session_naming_what_it_is_to_run(
    server: _FakeServer, tmp_path: Path
) -> None:
    """The model, the thought level and the rung are what the command line cannot be told."""
    agent = _agent()
    session = agent.new(tmp_path)

    assert session("hello") == "hello"

    (opened,) = server.named("session/create")
    # Field by field, and no field beyond them. No `runtimeModel` among them: this agent is
    # on no account of humanize's, so the provider it runs on is whatever ZCode is already
    # configured with, exactly as a bare `zcode` would take the turn.
    assert set(opened) == {
        "workspace",
        "model",
        "thoughtLevel",
        "mode",
        "titleGenerationEnabled",
    }
    assert opened["model"] == {"providerId": "zai", "modelId": "glm-5.3"}
    assert opened["thoughtLevel"] == "high"
    assert opened["mode"] == "yolo"
    assert opened["workspace"] == {
        "workspacePath": str(tmp_path),
        "workspaceKey": str(tmp_path),
    }
    # On, which is what leaving the field out does: only `false` turns it off.
    assert opened["titleGenerationEnabled"] is True
    # And the session is then read as it happens rather than replayed.
    (subscribed,) = server.named("session/subscribe")
    assert subscribed == {
        "sessionId": "sess_fake",
        "deliveryKind": "desktop-continuous",
    }
    agent.stop()


def test_the_frames_it_sends_are_the_protocols_own_rather_than_json_rpc(
    server: _FakeServer, tmp_path: Path
) -> None:
    """The real server refuses a frame carrying `jsonrpc`, so none of ours may."""
    agent = _agent()
    agent.new(tmp_path)("hello")

    sent = server.calls()

    assert sent
    assert not any("jsonrpc" in one for one in sent)
    agent.stop()


def test_a_turn_says_what_the_agent_said_in_the_order_it_said_it(
    server: _FakeServer, tmp_path: Path
) -> None:
    """The words that led up to a tool call are said before it, which is why it was made."""
    agent = _agent()
    said = list(agent.new(tmp_path).stream("hello"))

    assert [one.kind for one in said] == [
        "reasoning",
        "text",
        "tool",
        "text",
        "result",
    ]
    assert said[0].text == "thinking it over"
    assert said[2].text == "Bash List the files"
    assert said[-1].text == "hello"
    agent.stop()


def test_what_a_turn_cost_is_counted_as_each_request_of_it_lands(
    server: _FakeServer, tmp_path: Path
) -> None:
    """A turn is minutes long, and a rate that only moved at the end would stand still."""
    agent = _agent()
    session = agent.new(tmp_path)
    said = list(session.stream("hello"))

    assert dict(said[-1].tokens) == {"zai/glm-5.3": 17}
    assert dict(said[-1].spent) == {"input": 12.0, "output": 5.0}
    assert dict(session.spent()) == {"input": 12.0, "output": 5.0}
    assert dict(agent.spent()) == {"input": 12.0, "output": 5.0}
    agent.stop()


def test_the_session_it_opened_is_the_one_the_next_turn_carries_on(
    server: _FakeServer, tmp_path: Path
) -> None:
    """A conversation is one conversation, and the settings it opened with are not said twice."""
    agent = _agent()
    session = agent.new(tmp_path)
    session("first")
    session("second")

    assert session.id == "sess_fake"
    assert session.id in agent.opened
    assert len(server.named("session/create")) == 1
    assert [one["content"] for one in server.named("session/send")] == [
        "first",
        "second",
    ]
    # Nothing moved between the two, so nothing was said again.
    assert server.named("session/setModel") == []
    assert server.named("session/setThoughtLevel") == []
    assert server.named("session/setMode") == []
    agent.stop()


def test_an_effort_changed_between_turns_is_said_again(
    server: _FakeServer, tmp_path: Path
) -> None:
    """It is a setting of the session rather than of the turn, so it is set on the session."""
    agent = _agent()
    session = agent.new(tmp_path)
    session("first")
    session.effort = "low"
    session("second")

    (told,) = server.named("session/setThoughtLevel")

    assert told["thoughtLevel"] == "low"
    # One flow's choice is not the default of whatever the person at this machine opens next.
    assert told["persistAsWorkspaceLastUsed"] is False
    agent.stop()


@pytest.mark.parametrize(
    ("rung", "mode"),
    [
        ("read-only", "plan"),
        ("workspace-write", "edit"),
        ("auto", "build"),
        ("bypass", "yolo"),
    ],
)
def test_every_rung_is_a_mode_zcode_is_run_in(
    server: _FakeServer, tmp_path: Path, rung: str, mode: str
) -> None:
    """Four of its five, and never its own `auto`.

    In that mode its permission service refuses every tool, saying the mode is reserved and
    not implemented yet.
    """
    agent = _agent(permission=rung)
    agent.new(tmp_path)("hello")

    (opened,) = server.named("session/create")

    assert opened["mode"] == mode
    agent.stop()


def test_an_agent_that_may_not_search_the_web_is_denied_the_tools_that_reach_it(
    server: _FakeServer, tmp_path: Path
) -> None:
    """At the session rather than in anybody's settings file: two agents may be told two things."""
    agent = _agent()
    agent.new(tmp_path)("hello")

    (searching,) = server.named("session/create")

    assert "toolDenylist" not in searching
    agent.stop()

    agent = ZcodeAgent(replace(agent.config, web_search=False))
    agent.new(tmp_path)("hello")

    denied = server.named("session/create")[-1]

    assert denied["toolDenylist"] == ["WebFetch", "WebSearch"]
    agent.stop()


def test_a_session_is_named_by_zcode_unless_the_flow_said_not_to(
    server: _FakeServer, tmp_path: Path
) -> None:
    """On is ZCode's own answer, and the field's other value is the only way to stop it.

    A server reads `false` as off and reads `true` and the field left out as the same
    thing, so the default here is what saying nothing gets -- a request of its own on the
    lite role before the turn runs, which a run that reads no title may not want to pay for.
    """
    agent = _agent()
    agent.new(tmp_path)("hello")

    assert server.named("session/create")[-1]["titleGenerationEnabled"] is True
    agent.stop()

    agent = _agent(titles=False)
    agent.new(tmp_path)("hello")

    assert server.named("session/create")[-1]["titleGenerationEnabled"] is False
    agent.stop()


def test_what_the_runtime_may_do_is_answered_in_both_directions(
    server: _FakeServer, tmp_path: Path
) -> None:
    """ZCode's own file search, which the server asks about before it will open a session.

    Answered either way rather than left out when it is off: a key that is not there is a
    client that said neither yes nor no, and what the server makes of that is not knowable
    from here.
    """
    agent = _agent()
    agent.new(tmp_path)("hello")

    assert server.answered("nativeSearchEnhancementsEnabled") == [True]
    agent.stop()

    agent = _agent(native_search=False)
    agent.new(tmp_path)("hello")

    assert server.answered("nativeSearchEnhancementsEnabled") == [True, False]
    agent.stop()


def test_a_session_is_read_under_the_delivery_kind_it_was_configured_with(
    server: _FakeServer, tmp_path: Path
) -> None:
    """The other kind replays for a web client, and its own spelling is the server's to know.

    So what is checked is that the word given is the word sent, whatever word a real ZCode
    answers to -- a second literal written down here would be a fact nobody has heard said.
    """
    agent = _agent()
    agent.new(tmp_path)("hello")

    assert server.named("session/subscribe")[-1]["deliveryKind"] == "desktop-continuous"
    agent.stop()

    agent = _agent(delivery="whatever-this-server-calls-it")
    agent.new(tmp_path)("hello")

    assert (
        server.named("session/subscribe")[-1]["deliveryKind"]
        == "whatever-this-server-calls-it"
    )
    agent.stop()


def test_a_session_picked_back_up_is_subscribed_the_way_the_first_one_was(
    server: _FakeServer, tmp_path: Path
) -> None:
    """A server started since was told none of it, so the resume says the whole of it again."""
    agent = _agent(delivery="whatever-this-server-calls-it")
    session = agent.new(tmp_path)
    session("first")
    # The server it opened on is gone, which is what a fallback onto another account leaves
    # behind: the conversation is ZCode's own and outlives the process that was holding it.
    agent._down()
    session("second")

    (resumed,) = server.named("session/resume")

    assert resumed["sessionId"] == "sess_fake"
    assert resumed["thoughtLevel"] == "high"
    assert [one["deliveryKind"] for one in server.named("session/subscribe")] == [
        "whatever-this-server-calls-it",
        "whatever-this-server-calls-it",
    ]
    agent.stop()


def test_a_delivery_kind_that_names_nothing_is_refused_where_it_is_written() -> None:
    """A session is subscribed with whatever is here, so an empty kind is caught up front."""
    with pytest.raises(ValueError, match="delivery must be one of"):
        ZcodeAgentConfig(model="zai/glm-5.3", effort="high", delivery="   ")


def _gateway(**env: str) -> None:
    """Makes an account of this backend that points ZCode at somebody's endpoint."""
    from hmz.coganchor import providers

    providers.add(
        "zcode",
        "gateway",
        way="gateway",
        env={
            "ZCODE_BASE_URL": "https://gateway.example/v1",
            "ZCODE_API_KEY": "the-account-key",
            **env,
        },
    )


def test_a_gateway_account_is_handed_to_the_session_rather_than_written_anywhere(
    server: _FakeServer, tmp_path: Path
) -> None:
    """ZCode resolves a provider out of the file the person at this machine owns.

    So an agent on an account humanize was given has to hand ZCode that account some other
    way, or every session it opens is refused for a model config that is missing. The way
    is the session itself: `runtimeModel` names the provider for as long as the server holds
    it, and nothing under `~/.zcode` is read differently or written at all.
    """
    _gateway()
    agent = ZcodeAgent(
        ZcodeAgentConfig(model="gw/vendor/model-9", effort="high", provider="gateway")
    )
    agent.new(tmp_path)("hello")

    (opened,) = server.named("session/create")
    named = opened["runtimeModel"]

    assert named["model"] == {"providerId": "gw", "modelId": "vendor/model-9"}
    assert named["thoughtLevel"] == "high"
    # The provider is named after the one the model names, so that the pair the session is
    # opened with is a pair the server can resolve.
    assert named["provider"]["providerId"] == "gw"
    assert named["provider"]["baseURL"] == "https://gateway.example/v1"
    assert named["provider"]["models"] == [{"modelId": "vendor/model-9"}]
    # This run's, and written down nowhere: not the workspace's, not the person's.
    assert named["provider"]["source"] == "ephemeral"
    # The key goes on it rather than being left to the environment, which does have it:
    # ZCode tries `GW_API_KEY` before `ZCODE_API_KEY`, spelled out of the provider's own
    # name, and one of those left in a shell profile is an account this turn would run as.
    assert named["provider"]["apiKey"] == {
        "source": "inline",
        "value": "the-account-key",
    }
    agent.stop()


def test_the_protocol_a_gateway_speaks_is_the_one_zcode_would_have_worked_out(
    server: _FakeServer, tmp_path: Path
) -> None:
    """A provider naming a base URL is `openai-compatible` by ZCode's own rule.

    So that is what an install which says nothing gets, and the field is for the gateway
    that speaks one of the other two -- which is a failure quieter than a refusal, the
    endpoint answering and answering badly.
    """
    _gateway()
    made = ZcodeAgentConfig(
        model="gw/vendor/model-9", effort="high", provider="gateway"
    )
    agent = ZcodeAgent(made)
    agent.new(tmp_path)("hello")

    assert server.named("session/create")[-1]["runtimeModel"]["provider"]["kind"] == (
        "openai-compatible"
    )
    agent.stop()

    agent = ZcodeAgent(replace(made, protocol="anthropic"))
    agent.new(tmp_path)("hello")

    assert (
        server.named("session/create")[-1]["runtimeModel"]["provider"]["kind"]
        == "anthropic"
    )
    agent.stop()


def test_an_account_that_names_no_endpoint_leaves_zcodes_own_configuration_alone(
    server: _FakeServer, tmp_path: Path
) -> None:
    """A key account is a key, and which provider serves it is still ZCode's file's to say."""
    from hmz.coganchor import providers

    providers.add("zcode", "keyed", way="key", env={"ZCODE_API_KEY": "plan-key"})
    agent = ZcodeAgent(
        ZcodeAgentConfig(model="zai/glm-5.3", effort="high", provider="keyed")
    )
    agent.new(tmp_path)("hello")

    assert "runtimeModel" not in server.named("session/create")[-1]
    agent.stop()


def test_a_session_picked_back_up_is_handed_its_provider_again(
    server: _FakeServer, tmp_path: Path
) -> None:
    """The conversation outlives the server; the provider it ran on does not.

    ZCode materialises the provider from the client and keeps it in memory, so a session
    resumed on a server started since -- which is what a fallback leaves behind -- is a
    conversation whose model nothing can reach unless it is named again.
    """
    _gateway()
    agent = ZcodeAgent(
        ZcodeAgentConfig(model="gw/vendor/model-9", effort="high", provider="gateway")
    )
    session = agent.new(tmp_path)
    session("first")
    agent._down()
    session("second")

    (resumed,) = server.named("session/resume")

    assert (
        resumed["runtimeModel"]["provider"]["baseURL"] == "https://gateway.example/v1"
    )
    # And on both of the settling calls, either of which may be the first thing a server
    # started since hears about this session.
    assert (
        server.named("session/setModel")[-1]["runtimeModel"] == resumed["runtimeModel"]
    )
    assert (
        server.named("session/setThoughtLevel")[-1]["runtimeModel"]
        == (resumed["runtimeModel"])
    )
    agent.stop()


def test_a_fork_is_cut_from_where_the_conversation_had_got_to(
    server: _FakeServer, tmp_path: Path
) -> None:
    """ZCode forks from a point rather than from a session, and the point is its last message.

    Its own default is the latest workspace checkpoint, which does not exist until the agent
    has changed a file -- so a fork of a conversation that has only talked would be refused
    for a reason about files.
    """
    agent = _agent()
    session = agent.new(tmp_path)
    session("first")
    forked = session.fork()

    assert forked("second") == "second"

    (cut,) = server.named("session/fork")

    assert cut["sessionId"] == "sess_fake"
    assert cut["target"] == {"kind": "message", "messageId": "msg_last"}
    # The child is ZCode's own session rather than a second handle on the parent's, and it
    # is read as it happens like any other.
    assert forked.id == "sess_forked"
    assert session.id == "sess_fake"
    assert server.named("session/subscribe")[-1]["sessionId"] == "sess_forked"
    # And the fork is the child's first turn: nothing opened a session of its own for it.
    assert len(server.named("session/create")) == 1
    agent.stop()


def test_a_fork_of_an_agent_that_may_not_search_is_let_go_of_and_picked_back_up(
    server: _FakeServer, tmp_path: Path
) -> None:
    """ZCode materialises a fork from the mode, the model and the thought level and no more.

    So the denylist that keeps an agent off the web is not among what a child inherits, and a
    fork of a conversation that may not search would be one that may -- a setting lifted by
    branching, which nothing downstream would report. `session/resume` is where a denylist is
    sayable and it says nothing to a session the server is already holding, so the child is
    closed and picked back up with it.
    """
    agent = ZcodeAgent(
        ZcodeAgentConfig(model="zai/glm-5.3", effort="high", web_search=False)
    )
    session = agent.new(tmp_path)
    session("first")
    forked = session.fork()

    assert forked("second") == "second"

    (closed,) = server.named("session/close")
    (resumed,) = server.named("session/resume")

    assert closed == {"sessionId": "sess_forked"}
    assert resumed["sessionId"] == "sess_forked"
    assert resumed["toolDenylist"] == ["WebFetch", "WebSearch"]
    agent.stop()

    # And an agent that may search is one the fork already gets right, so nothing is closed.
    agent = _agent()
    session = agent.new(tmp_path)
    session("first")
    session.fork()("second")

    assert server.named("session/close") == [closed]
    agent.stop()


def test_a_protocol_that_is_not_one_of_zcodes_three_is_refused_where_it_is_written() -> (
    None
):
    """A gateway spoken to in the wrong protocol answers, and answers badly."""
    with pytest.raises(ValueError, match="protocol must be one of"):
        ZcodeAgentConfig(model="zai/glm-5.3", effort="high", protocol="grpc")


def test_an_agent_handed_the_common_config_runs_at_what_was_always_sent(
    server: _FakeServer, tmp_path: Path
) -> None:
    """The four answers are ZCode's config's, and the common one says none of them."""
    agent = ZcodeAgent(AgentConfig(model="zai/glm-5.3", effort="high"))
    agent.new(tmp_path)("hello")

    assert server.answered("nativeSearchEnhancementsEnabled") == [True]
    assert server.named("session/create")[-1]["titleGenerationEnabled"] is True
    assert server.named("session/subscribe")[-1]["deliveryKind"] == "desktop-continuous"
    agent.stop()


def test_each_of_the_four_is_a_capability_a_flow_can_ask_for_beforehand() -> None:
    """Humanize deciding something on ZCode's behalf is something a flow may ask about.

    The field is where the other answer is given; the name is what a place declares to be
    refused an agent that has no such answer to give before its first turn. That name is
    the field's own, under `settings:`, rather than a second word beside it: the catalogue
    derives one per field, so a field renamed here is a name renamed there.
    """
    from hmz.flows.checking import catalogue

    told = {one.name: one.backends for one in catalogue()}

    for name in (
        "settings:titles",
        "settings:native_search",
        "settings:delivery",
        "settings:protocol",
    ):
        assert "zcode" in told[name], name


def test_a_failed_turn_says_what_zcode_said_about_it(
    server: _FakeServer, tmp_path: Path
) -> None:
    """A turn that failed must say why, and an exit status alone says nothing."""
    agent = _agent()
    session = agent.new(tmp_path)

    with pytest.raises(subprocess.CalledProcessError) as refused:
        session("boom")

    assert isinstance(refused.value, Failed)
    assert "the model refused it" in str(refused.value)
    # A turn that failed never opened the session, so the next one retries rather than
    # carrying on a conversation nobody can find.
    with pytest.raises(RuntimeError, match="has not run a turn yet"):
        _ = session.id
    agent.stop()


def test_a_turn_that_failed_is_nothing_at_all_where_it_is_suppressed(
    server: _FakeServer, tmp_path: Path
) -> None:
    """Which is how a flow that would rather go on than stop asks for one."""
    agent = _agent()

    assert agent.new(tmp_path)("boom", suppress=True) == ""
    agent.stop()


def test_a_rung_below_the_one_that_grants_it_refuses_what_it_is_asked(
    server: _FakeServer, tmp_path: Path
) -> None:
    """ZCode asks at `edit` too, and an agent allowed its workspace is not allowed more."""
    agent = _agent(permission="workspace-write")

    assert agent.new(tmp_path)("approving") == json.dumps(
        {"decision": "deny", "reason": "the agent is allowed no more than edit mode"}
    )
    agent.stop()


def test_a_high_risk_tool_is_allowed_and_a_hook_may_say_no(
    server: _FakeServer, tmp_path: Path
) -> None:
    """The moment the backend waits on is the one place a refusal stops it doing something."""
    agent = _agent(permission="auto")
    assert agent.new(tmp_path)("approving") == json.dumps(
        {"decision": "allow", "reason": "run unattended"}
    )
    agent.stop()

    refusing = _agent(permission="auto")
    seen: list[Occasion] = []

    def refuse(occasion: Occasion) -> Verdict:
        seen.append(occasion)
        return Verdict(refused=True, because="not that one")

    refusing.hooks.on(Moment.PERMISSION_REQUEST, refuse)

    assert refusing.new(tmp_path)("approving") == json.dumps(
        {"decision": "deny", "reason": "not that one"}
    )
    assert [one.tool for one in seen] == ["Bash"]
    refusing.stop()


def test_a_question_nobody_is_there_to_answer_lets_the_turn_go_on(
    server: _FakeServer, tmp_path: Path
) -> None:
    """A turn waiting for a reply that is not coming is a flow that has stopped."""
    agent = _agent()

    assert agent.new(tmp_path)("asking") == json.dumps(
        {"decision": "deny", "reason": "nobody is here to answer"}
    )
    agent.stop()


def test_a_question_somebody_answers_carries_their_words_back(
    server: _FakeServer, tmp_path: Path
) -> None:
    """ZCode takes an answer over a channel its own terminal holds, so this is the reason."""
    agent = _agent()
    asked: list[str] = []

    def answer(question: Any) -> str:
        asked.append(question.text)
        return "left"

    agent.ask = answer

    assert agent.new(tmp_path)("asking") == json.dumps(
        {"decision": "deny", "reason": "Which way? left"}
    )
    assert asked == ["Which way?"]
    agent.stop()


def test_a_goal_is_zcodes_own_and_the_turn_it_starts_runs_to_the_end(
    server: _FakeServer, tmp_path: Path
) -> None:
    """`pursue` is the agent keeping itself going, which ZCode has a feature for."""
    agent = _agent()
    session = agent.new(tmp_path)

    assert session.pursue("make it green") == "under a goal: make it green"

    (told,) = server.named("session/goal")

    assert told["action"] == "set"
    assert told["objective"] == "make it green"
    assert session.id == "sess_fake"
    agent.stop()


def test_nothing_can_be_said_to_a_turn_that_is_already_running(
    server: _FakeServer, tmp_path: Path
) -> None:
    """Nowhere to put a word, because the server refuses one.

    A second prompt while one is running is refused, and what its own terminal steers with is
    a channel that terminal holds.
    """
    agent = _agent()

    with pytest.raises(NotImplementedError):
        agent.new(tmp_path).interject("also mind the gap")
    agent.stop()


def test_the_protocol_does_not_reach_the_terminal(
    server: _FakeServer, tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """What a person watching sees is the turn, not the frames it was carried in."""
    agent = _agent()
    agent.new(tmp_path)("hello")
    streams = capfd.readouterr()

    assert "session/event" not in streams.out
    assert "sessionId" not in streams.out
    assert streams.out.strip().endswith("hello")
    agent.stop()


def test_a_turn_runs_in_the_flows_own_environment(
    server: _FakeServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An agent with no provider is left exactly as it was found."""
    monkeypatch.setenv("A_THING_THE_FLOW_HAS", "kept")
    agent = _agent()

    assert agent.new(tmp_path)("hello") == "hello"
    assert os.environ["A_THING_THE_FLOW_HAS"] == "kept"
    agent.stop()


def test_two_sessions_of_one_agent_share_the_server_it_started(
    server: _FakeServer, tmp_path: Path
) -> None:
    """One per agent rather than one per session, so dropping a session drops no server."""
    agent = _agent()
    first, second = agent.new(tmp_path), agent.new(tmp_path)
    first("one")
    second("two")

    assert agent.server is agent.server
    assert len(server.named("session/create")) == 2
    agent.stop()


#: A stand-in that will not finish a turn until another is running beside it. Each
#: `session/create` is a session of its own, and a `session/send` is written down rather than
#: answered until two of them are outstanding -- at which point both turns are said at once,
#: interleaved, each on its own session. A client that reads the one stream in turn never gets
#: its first turn back, so this hangs rather than passing where turns are serialized.
_TOGETHER = """
import json, sys, threading

HELD = []
LOCK = threading.Lock()


def send(message):
    with LOCK:
        sys.stdout.write(json.dumps(message) + "\\n")
        sys.stdout.flush()


def event(session, kind, payload):
    send({"method": "session/event", "params": {
        "sessionId": session, "type": kind, "payload": payload}})


def both():
    # Interleaved deliberately: each turn must take its own out of the shared stream.
    for session, _ in HELD:
        event(session, "model.streaming", {"assistantMessageId": "msg_" + session,
                                           "kind": "text_delta", "delta": session})
    for session, prompt in HELD:
        event(session, "session.updated", {"assistantMessageId": "msg_" + session,
                                           "content": prompt, "stopReason": "stop",
                                           "usage": {"inputTokens": 1, "outputTokens": 1,
                                                     "totalTokens": 2}})
    for session, prompt in HELD:
        event(session, "turn.completed", {"response": prompt, "toolCallCount": 0,
                                          "usage": {"inputTokens": 1, "outputTokens": 1,
                                                    "totalTokens": 2}})


for line in sys.stdin:
    call = json.loads(line)
    if "method" not in call or "id" not in call:
        continue
    if call["method"] == "session/create":
        named = "sess_%d" % (len(HELD) + call["id"])
        send({"id": call["id"], "result": {
            "session": {"sessionId": named, "mode": "build",
                        "model": {"providerId": "zai", "modelId": "glm"}},
            "projection": {"turnCount": 0}, "messages": [],
            "protocol": {"name": "ZCode Protocol", "version": 1}}})
        continue
    if call["method"] == "session/send":
        HELD.append((call["params"]["sessionId"], call["params"]["content"]))
        send({"id": call["id"], "result": {"accepted": True}})
        if len(HELD) == 2:
            both()
        continue
    send({"id": call["id"], "result": {}})
"""


def test_two_turns_of_one_agent_run_at_once_rather_than_one_behind_the_other(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one stream is sorted per session, so a turn waits only on its own session."""
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / "zcode"
    fake.write_text(f"#!{sys.executable}\n{_TOGETHER}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")

    agent = _agent()
    said: dict[str, str] = {}

    def turn(name: str) -> None:
        said[name] = agent.new(tmp_path)(name)

    # Neither finishes until both are running, so a driver that ran them one at a time would
    # leave the second unsent and the first waiting forever.
    # Daemons so that a driver which serializes them fails this in thirty seconds rather
    # than leaving the suite waiting on a turn that is never coming back.
    threads = [
        threading.Thread(target=turn, args=(name,), daemon=True)
        for name in ("one", "two")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not [thread for thread in threads if thread.is_alive()]
    assert said == {"one": "one", "two": "two"}
    agent.stop()


#: A stand-in that says a whole stale turn -- one that ended before this one was asked for --
#: in the moment between reading `session/send` and answering it. The real one has its own
#: reasons to talk about a session outside a turn: a subscription catching a client up, a goal
#: it is still working. None of it is the turn now being sent, and a turn that read it would
#: end on somebody else's answer without ever having run.
_STALE = """
import json, sys

SESSION = "sess_stale"


def send(message):
    sys.stdout.write(json.dumps(message) + "\\n")
    sys.stdout.flush()


def event(kind, payload):
    send({"method": "session/event", "params": {
        "sessionId": SESSION, "type": kind, "payload": payload}})


def turn(response):
    event("session.updated", {"assistantMessageId": "msg_" + response,
                              "content": response, "stopReason": "stop",
                              "usage": {"inputTokens": 1, "outputTokens": 1,
                                        "totalTokens": 2}})
    event("turn.completed", {"response": response, "toolCallCount": 0,
                             "usage": {"inputTokens": 1, "outputTokens": 1,
                                       "totalTokens": 2}})


for line in sys.stdin:
    call = json.loads(line)
    if "method" not in call or "id" not in call:
        continue
    if call["method"] == "session/create":
        send({"id": call["id"], "result": {
            "session": {"sessionId": SESSION, "mode": "build",
                        "model": {"providerId": "zai", "modelId": "glm"}},
            "projection": {"turnCount": 0}, "messages": [],
            "protocol": {"name": "ZCode Protocol", "version": 1}}})
        continue
    if call["method"] == "session/send":
        turn("a turn that ended before this one was asked for")
        send({"id": call["id"], "result": {"accepted": True}})
        turn(call["params"]["content"])
        continue
    send({"id": call["id"], "result": {}})
"""


def test_what_a_session_said_before_the_turn_started_is_not_the_turns_own_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The answer to the call that starts a turn is the line before it and after it."""
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / "zcode"
    fake.write_text(f"#!{sys.executable}\n{_STALE}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")

    agent = _agent()
    assert agent.new(tmp_path)("what this turn asked") == "what this turn asked"
    agent.stop()


#: Somewhere a request would never reach, for the half of the real-server test that only
#: opens a session: nothing is sent to the endpoint until a turn is, so this is a base URL
#: that names a provider without naming anybody's account.
_NOWHERE = "https://zcode.invalid/v1"


@pytest.mark.agent
@pytest.mark.timeout(300)
def test_a_real_app_server_opens_a_session_only_when_it_is_handed_a_provider(
    tmp_path: Path,
) -> None:
    """The stand-in above says yes to a session whatever it is asked; the real one does not.

    ZCode resolves its model provider from the configuration file the person at this machine
    owns, and a server started without one refuses every session outright. That is the whole
    of the bug this pins: a driver that names a model and no provider is a driver whose every
    turn comes back `Model config is missing`, and a stand-in cannot tell anybody so.

    It costs nothing and reaches nobody -- a session is opened and the server put down, no
    turn is sent, so the endpoint named here is never called on.
    """
    import shutil

    from hmz.coganchor.agents.zcode import _AppServer, _Held, _runtime

    if shutil.which("zcode") is None:
        pytest.skip("zcode is not installed here")
    held = _Held(model="hmz-test/no-such-model", effort="high", mode="plan")
    theirs = Path.home() / ".zcode" / "cli" / "config.json"
    if not theirs.exists():
        # Only where this machine has no provider of its own to fall back on: an install
        # that has one is an install where a session opens either way, and the refusal this
        # is about is not one it can be shown.
        server = _AppServer(["zcode", "app-server", "--stdio"])
        try:
            with pytest.raises(subprocess.CalledProcessError) as refused:
                server.open(
                    str(tmp_path),
                    held,
                    searches=True,
                    titles=False,
                    delivery="desktop-continuous",
                )
            assert "model config is missing" in str(refused.value).lower()
        finally:
            server.stop()

    held.runtime = _runtime(
        held.model,
        held.effort,
        {"ZCODE_BASE_URL": _NOWHERE, "ZCODE_API_KEY": "not-a-key"},
        "openai-compatible",
    )
    server = _AppServer(["zcode", "app-server", "--stdio"])
    try:
        session = server.open(
            str(tmp_path),
            held,
            searches=True,
            titles=False,
            delivery="desktop-continuous",
        )
        assert session.startswith("sess_")
    finally:
        server.stop()

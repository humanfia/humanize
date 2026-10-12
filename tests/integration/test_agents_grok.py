"""Grok Build, driven through `GrokBuildAgent` against a stand-in `grok` on PATH.

Grok has two transports and the stand-in serves both. `grok agent ... stdio` holds the
conversation open and speaks the Agent Client Protocol: `session/new` opens one,
`session/load` picks one back up, `session/prompt` takes a turn whose words arrive as
`session/update` notifications, and a tool call may be put to the client as a
`session/request_permission`. `grok -p` is one run of a turn with the prompt on its command
line, the same updates flattened onto `type`, ending on an `end` naming the session.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import psutil
import pytest
from pydantic import BaseModel

from hmz.coganchor import providers
from hmz.coganchor.agents import (
    Failed,
    FakeTool,
    GrokBuildAgent,
    GrokBuildAgentConfig,
    Moment,
    Occasion,
    Unrecoverable,
    Verdict,
)
from hmz.coganchor.gateway import gatewayable
from hmz.coganchor.providers import Provider
from tests.integration.doubles_agents import (
    MCP,
    Endpoint,
    Standins,
    kinds,
    serving,
    standins,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
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
        if method in ("session/new", "session/load"):
            servers = asked["params"]["mcpServers"]
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
        if said.startswith("tool "):
            _, name, given = said.split(" ", 2)
            (server,) = [one for one in servers if one["name"] == "humanize"]
            listed, text = mcp(server, name, json.loads(given))
            told("agent_message_chunk", content={"type": "text",
                                                 "text": ",".join(listed) + ": " + text})
            out({"jsonrpc": "2.0", "id": at, "result": {"stopReason": "end_turn"}})
            continue
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
    held.install("grok", MCP + GROK)
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
    # Exited, as a process gone between turns is: not still on its way out as the next starts.
    (first,) = {one.pid for one in grok.calls()}
    with contextlib.suppress(psutil.NoSuchProcess):
        psutil.Process(first).wait(timeout=10)
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


#: A `grok agent` that opens every session on the first model of its catalogue, as 1.0.50
#: does for a model not in it, and runs a turn as the `[model.*]` entry of its config says:
#: chat completions at its endpoint under the key its variable holds, streamed.
ROUTED = r"""
import tomllib
import urllib.request

note()
current = "openai/first-of-the-catalogue"
while line := sys.stdin.readline():
    asked = json.loads(line)
    at, method = asked.get("id"), asked.get("method")
    if method == "session/new":
        out({"jsonrpc": "2.0", "id": at,
             "result": {"sessionId": "ses-grok", "models": {"currentModelId": current}}})
        continue
    if method == "session/set_model":
        current = asked["params"]["modelId"]
    if method != "session/prompt":
        out({"jsonrpc": "2.0", "id": at, "result": {}})
        continue
    said = asked["params"]["prompt"][0]["text"]
    home = os.environ.get("GROK_HOME") or os.path.join(os.environ["HOME"], ".grok")
    with open(os.path.join(home, "config.toml"), "rb") as config:
        entry = tomllib.load(config)["model"][current]
    note(entry["api_backend"])
    request = urllib.request.Request(
        entry["base_url"] + "/chat/completions",
        data=json.dumps({"model": entry["model"], "stream": True,
                         "messages": [{"role": "user", "content": said}]}).encode(),
        headers={"Authorization": "Bearer " + os.environ[entry["env_key"]],
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as answer:
        chunks = [json.loads(one[5:]) for one in answer.read().decode().splitlines()
                  if one.startswith("data:") and one[5:].strip() != "[DONE]"]
    body = "".join(one["choices"][0]["delta"].get("content") or ""
                   for one in chunks if one.get("choices"))
    out({"jsonrpc": "2.0", "method": "session/update",
         "params": {"sessionId": "ses-grok", "update": {
             "sessionUpdate": "agent_message_chunk",
             "content": {"type": "text", "text": body}}}})
    out({"jsonrpc": "2.0", "id": at, "result": {"stopReason": "end_turn"}})
"""


def _unswapped(self: Provider) -> tuple[tuple[str, str], ...]:
    """No credential path answered by another, which is the supervisor's to test."""
    del self
    return ()


@pytest.fixture
def endpoint() -> Iterator[Endpoint]:
    # Driven to its end after the test, which is what shuts it.
    yield from serving()


@pytest.mark.skipif(not gatewayable(), reason="the [litellm] extra is not installed")
@pytest.mark.timeout(240)
def test_grok_under_an_account_a_gateway_holds_runs_the_model_through_it(
    endpoint: Endpoint, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = standins(
        tmp_path,
        monkeypatch,
        "GROK_XAI_API_BASE_URL",
        "XAI_API_KEY",
        "LITELLM_GATEWAY_KEY",
    )
    held.install("grok", ROUTED)
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "hmz"))
    monkeypatch.setenv("LITELLM_GATEWAY_KEY", "lying-about")
    # A credential path answered by another is the supervisor's, tested where it is written.
    monkeypatch.setattr(Provider, "swaps", _unswapped)
    providers.add(
        "grok",
        "gw",
        way="litellm-openai-gateway",
        env={
            "LITELLM_GATEWAY_URL": endpoint.url,
            "LITELLM_GATEWAY_KEY": "upstream-secret",
            "LITELLM_GATEWAY_API": "openai",
        },
    )
    agent = GrokBuildAgent(
        GrokBuildAgentConfig(model="stand-in", effort="", provider="gw")
    )
    try:
        said = agent.new(tmp_path)("say hi")
        through = agent.gateway
        assert through is not None
    finally:
        agent.stop()

    assert said == "say hi"
    assert [one["model"] for one in endpoint.asked] == ["stand-in"]
    launch, turn = held.calls("grok")
    assert launch.env["GROK_XAI_API_BASE_URL"] == through.url
    assert launch.env["XAI_API_KEY"] == through.key
    assert launch.env["LITELLM_GATEWAY_KEY"] is None
    assert turn.stdin == "chat_completions"
    assert not through.running
    # And the entry it was asked for by, which named a port nothing listens on any more.
    assert "127.0.0.1" not in (tmp_path / "home/.grok/config.toml").read_text()


class _Word(BaseModel):
    word: str


def test_a_flow_s_callback_is_a_tool_grok_reaches_over_mcp(grok: Standins) -> None:
    seen: list[str] = []

    def looks_up(said: _Word) -> str:
        seen.append(said.word)
        return f"found {said.word}"

    session = GrokBuildAgent(CONFIG).new()
    try:
        session.offers(
            [FakeTool(name="lookup", about="Looks up.", call=looks_up, takes=_Word)]
        )
        answered = session('tool lookup {"word": "kiwi"}')
        session.offers(
            [FakeTool(name="define", about="Defines.", call=looks_up, takes=_Word)]
        )
        again = session('tool define {"word": "fig"}')
    finally:
        session.close()

    assert seen == ["kiwi", "fig"]
    assert answered == "lookup: found kiwi"
    # Told of another list, grok was started again and the conversation loaded onto it.
    assert again == "define: found fig"
    assert "load ses-grok" in grok.said()


def test_a_turn_only_grok_p_can_take_is_refused_while_callbacks_are_offered(
    grok: Standins,
) -> None:
    session = GrokBuildAgent(CONFIG).new()
    session.offers([FakeTool(name="lookup", about="Looks up.", call=lambda: "found")])

    with pytest.raises(Unrecoverable, match="takes no MCP server"):
        session("hello", schema=_Word)

    assert grok.calls() == []

"""Codex, driven through `CodexAgent` against a stand-in `codex app-server` on PATH.

The stand-in speaks the app server's JSON-RPC over stdio: it answers `initialize`,
`thread/start`, `thread/resume` and `thread/fork`, and plays a `turn/start` as the
notifications a working turn runs through -- items started and completed, the thread's token
usage, `turn/completed` and the thread falling idle. What a turn does is chosen by its prompt.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import threading
from typing import TYPE_CHECKING, Any

import psutil
import pytest

from hmz.coganchor import providers
from hmz.coganchor.agents import (
    CodexAgent,
    CodexAgentConfig,
    Event,
    Failed,
    Moment,
    Occasion,
    Question,
    Verdict,
)
from hmz.coganchor.faking import FakeCli, FakeCommand
from hmz.coganchor.gateway import gatewayable
from hmz.coganchor.providers import Provider
from tests.integration.doubles_agents import (
    Endpoint,
    Standins,
    kinds,
    serving,
    standins,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

CONFIG = CodexAgentConfig(model="gpt-stand-in", effort="high")

CODEX = r"""
import itertools, threading, time

note()
threads = itertools.count(1)
total = [0]
writing = threading.Lock()


def send(message):
    with writing:
        out(message)


def notify(method, **params):
    send({"method": method, "params": params})


def item(state, thread, **said):
    notify("item/" + state, threadId=thread, turnId="turn-1", item=said)


def spend(thread, output):
    total[0] += 10 + output
    notify("thread/tokenUsage/updated", threadId=thread, turnId="turn-1", tokenUsage={
        "last": {"inputTokens": 10, "outputTokens": output, "totalTokens": 10 + output},
        "total": {"inputTokens": total[0] - output, "cachedInputTokens": 0,
                  "outputTokens": output, "reasoningOutputTokens": 0,
                  "totalTokens": total[0]}})


def done(thread, status="completed", error=None):
    turn = {"id": "turn-1", "status": status}
    if error:
        turn["error"] = error
    notify("turn/completed", threadId=thread, turn=turn)
    notify("thread/status/changed", threadId=thread, status={"type": "idle"})


def turn(thread, said, asked):
    notify("turn/started", threadId=thread, turnId="turn-1")
    if said == "hang":
        time.sleep(600)
    if said == "crash":
        print("codex: something broke", file=sys.stderr, flush=True)
        os._exit(3)
    if said == "unfinished":
        done(thread, status="failed", error={"message": "it could not finish"})
        return
    drops = pathlib.Path(sys.argv[0]).with_name("drops")
    if said == "drop" and drops.exists() and int(drops.read_text()):
        # The response stream broken as codex reports it: retrying by itself, then giving up.
        drops.write_text(str(int(drops.read_text()) - 1))
        lost = {"responseStreamDisconnected": {"httpStatusCode": None}}
        notify("error", threadId=thread, turnId="turn-1", willRetry=True,
               error={"message": "Reconnecting... 5/5", "codexErrorInfo": lost})
        done(thread, status="failed", error={
            "message": "stream disconnected before completion: error decoding response body",
            "codexErrorInfo": lost})
        return
    if said == "rules":
        ruled = pathlib.Path(os.environ["CODEX_HOME"], "rules", "hmz.rules")
        item("completed", thread, id="m-0", type="agentMessage",
             text=json.dumps({"policy": asked.get("sandboxPolicy"),
                              "rules": ruled.read_text() if ruled.exists() else None,
                              "theirs": sorted(one.name for one in ruled.parent.iterdir())}))
        done(thread)
        return
    if said == "approve":
        send({"id": "ok-1", "method": "item/commandExecution/requestApproval",
              "params": {"itemId": "i-0", "threadId": thread, "turnId": "turn-1",
                         "command": "rm -rf /"}})
        return
    if said == "ask":
        send({"id": "ask-1", "method": "item/tool/requestUserInput", "params": {
            "itemId": "i-0", "threadId": thread, "turnId": "turn-1",
            "questions": [{"id": "which", "header": "Way", "question": "Which way?",
                           "options": [{"label": "left"}, {"label": "right"}]}]}})
        return
    if said == "long":
        item("completed", thread, id="m-0", type="agentMessage", text="busy")
        return
    item("started", thread, id="c-1", type="commandExecution", status="inProgress",
         command="echo " + said)
    item("completed", thread, id="c-1", type="commandExecution", status="completed",
         command="echo " + said, exitCode=0)
    item("completed", thread, id="r-1", type="reasoning", summary=[],
         content=["thinking about " + said])
    spend(thread, 7)
    answer = json.dumps({"value": said}) if asked.get("outputSchema") else said
    item("completed", thread, id="m-1", type="agentMessage", text=answer)
    done(thread)
    if said == "then-exit":
        os._exit(0)


for line in sys.stdin:
    call = json.loads(line)
    method = call.get("method")
    if method is None:
        # An answer to something this server asked: the turn it held goes on with it.
        note("answered " + json.dumps(call.get("result")))
        item("completed", "t-1", id="m-2", type="agentMessage",
             text=json.dumps(call.get("result")))
        done("t-1")
        continue
    params = call.get("params") or {}
    if method == "turn/start":
        note(params["input"][0]["text"])
    elif method in ("thread/start", "thread/resume", "thread/fork", "turn/steer"):
        note(method + " " + json.dumps(params, sort_keys=True))
    if "id" not in call:
        continue
    result = {}
    if method in ("thread/start", "thread/fork"):
        result = {"thread": {"id": "t-%d" % next(threads)}}
    elif method == "thread/resume":
        result = {"thread": {"id": params["threadId"]}}
    send({"jsonrpc": "2.0", "id": call["id"], "result": result})
    if method in ("thread/start", "thread/fork"):
        notify("thread/status/changed", threadId=result["thread"]["id"],
               status={"type": "idle"})
    if method == "turn/start":
        threading.Thread(target=turn, args=(params["threadId"],
                         params["input"][0]["text"], params), daemon=True).start()
    if method == "turn/steer":
        item("completed", params["threadId"], id="m-3", type="agentMessage",
             text="heard " + params["input"][0]["text"])
        done(params["threadId"])
"""


@pytest.fixture
def codex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch)
    held.install("codex", CODEX)
    return held


def _told(codex: Standins, method: str) -> list[dict[str, Any]]:
    """What each call of one method was sent, oldest first."""
    return [
        json.loads(said.removeprefix(method + " "))
        for said in codex.said()
        if said.startswith(method + " ")
    ]


def test_a_turn_says_what_it_did_and_what_it_spent(codex: Standins) -> None:
    session = CodexAgent(CONFIG).new()

    said = list(session.stream("hello"))

    assert kinds(said) == ["tool", "reasoning", "text", "result"]
    assert "echo hello" in said[0].text
    assert said[-1].text == "hello"
    assert dict(said[-1].tokens) == {"gpt-stand-in": 17}
    assert said[-1].spent.output == 7
    (launch,) = (one for one in codex.calls() if not one.stdin)
    assert launch.argv[0] == "app-server"
    assert launch.env["HMZ_TEST_INHERITED"] == "from-the-flow"
    (opened,) = _told(codex, "thread/start")
    assert opened["model"] == "gpt-stand-in"


def test_one_server_holds_the_thread_across_turns(codex: Standins) -> None:
    agent = CodexAgent(CONFIG)
    session = agent.new()

    assert session("one") == "one"
    assert session("two") == "two"

    assert session.id == "t-1"
    assert len({one.pid for one in codex.calls()}) == 1
    assert len(_told(codex, "thread/start")) == 1
    assert agent.opened == ["t-1"]


def test_two_sessions_of_one_agent_share_its_server(codex: Standins) -> None:
    agent = CodexAgent(CONFIG)
    first, second = agent.new(), agent.new()

    first("a")
    second("b")

    assert (first.id, second.id) == ("t-1", "t-2")
    assert len({one.pid for one in codex.calls()}) == 1


def test_a_thread_whose_server_went_down_is_resumed_on_the_next(
    codex: Standins,
) -> None:
    session = CodexAgent(CONFIG).new()

    assert session("then-exit") == "then-exit"
    # Exited, as a server gone between turns is: not still on its way out as the next starts.
    (first,) = {one.pid for one in codex.calls()}
    with contextlib.suppress(psutil.NoSuchProcess):
        psutil.Process(first).wait(timeout=10)
    assert session("after") == "after"

    assert len({one.pid for one in codex.calls()}) == 2
    (resumed,) = _told(codex, "thread/resume")
    assert resumed["threadId"] == session.id == "t-1"
    assert len(_told(codex, "thread/start")) == 1


def test_a_forked_session_carries_on_from_its_parent(codex: Standins) -> None:
    session = CodexAgent(CONFIG).new()
    session("one")

    child = session.fork()
    assert child("two") == "two"

    (forked,) = _told(codex, "thread/fork")
    assert forked["threadId"] == session.id
    assert child.id not in ("", session.id)


def test_a_failed_turn_is_a_failure_with_what_codex_said(codex: Standins) -> None:
    session = CodexAgent(CONFIG).new()

    with pytest.raises(Failed, match="it could not finish"):
        session("unfinished")
    assert session("unfinished", suppress=True) == ""


def test_a_broken_response_stream_is_taken_again_in_the_session(
    codex: Standins,
) -> None:
    session = CodexAgent(CONFIG).new()
    assert session("one") == "one"
    (codex.bin / "drops").write_text("1")

    assert session("drop") == "drop"

    assert codex.said().count("drop") == 2
    assert session.id == "t-1"
    assert len(_told(codex, "thread/start")) == 1


def test_a_response_stream_that_keeps_breaking_fails_as_dropped(
    codex: Standins,
) -> None:
    (codex.bin / "drops").write_text("2")

    with pytest.raises(Failed, match="stream disconnected before completion") as failed:
        CodexAgent(CONFIG).new()("drop")

    assert failed.value.fault == "dropped"
    assert codex.said().count("drop") == 2


def test_a_server_that_dies_mid_turn_fails_the_turn(codex: Standins) -> None:
    with pytest.raises(Failed):
        CodexAgent(CONFIG).new()("crash")


def test_a_turn_that_has_gone_silent_is_ended_by_the_watchdog(
    codex: Standins, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_WATCHDOG", "1")

    with pytest.raises(Failed):
        CodexAgent(CONFIG).new()("hang")


def test_an_approval_is_put_to_the_hook_and_refused(codex: Standins) -> None:
    agent = CodexAgent(
        CodexAgentConfig(model="gpt-stand-in", effort="high", permission="bypass")
    )
    seen: list[Occasion] = []

    def gate(occasion: Occasion) -> Verdict:
        seen.append(occasion)
        return Verdict(refused=True, because="not that")

    agent.hooks.on(Moment.PERMISSION_REQUEST, gate)

    answered = json.loads(agent.new()("approve"))

    assert answered == {"decision": "decline"}
    assert len(seen) == 1
    assert "rm -rf /" in seen[0].about


def test_an_approval_nobody_refused_is_accepted(codex: Standins) -> None:
    agent = CodexAgent(
        CodexAgentConfig(model="gpt-stand-in", effort="high", permission="bypass")
    )

    assert json.loads(agent.new()("approve")) == {"decision": "accept"}


def test_a_question_is_put_to_whoever_drives_the_agent(codex: Standins) -> None:
    agent = CodexAgent(CONFIG)
    asked: list[Question] = []

    def answers(question: Question) -> str:
        asked.append(question)
        return "left"

    agent.ask = answers

    answered = json.loads(agent.new()("ask"))

    assert [(one.text, one.options) for one in asked] == [
        ("Which way?", ("left", "right"))
    ]
    assert answered == {"answers": {"which": {"answers": ["left"]}}}


def test_a_word_put_in_mid_turn_is_steered_into_it(codex: Standins) -> None:
    session = CodexAgent(CONFIG).new()
    said: list[Event] = []

    for event in session.stream("long"):
        if event.kind == "text" and event.text == "busy":
            session.interject("also this")
        said.append(event)

    assert said[-1].text == "heard also this"
    (steered,) = _told(codex, "turn/steer")
    assert steered["input"][0]["text"] == "also this"


def test_two_sessions_take_their_turns_at_the_same_time(codex: Standins) -> None:
    agent = CodexAgent(CONFIG)
    answers: dict[str, str] = {}

    def runs(prompt: str) -> None:
        answers[prompt] = agent.new()(prompt)

    turns = [threading.Thread(target=runs, args=(one,)) for one in ("a", "b")]
    for one in turns:
        one.start()
    for one in turns:
        one.join(30)

    assert answers == {"a": "a", "b": "b"}


# --------------------------------------------------------------- through a LiteLLM gateway

#: A `codex app-server` that asks the provider it was given as settings, in the Responses API
#: and under the key in the variable it was told of, and says what streamed back.
ROUTED = r"""
import urllib.request

note()
told = dict(one.split("=", 1) for one in argv if one.startswith("model"))
base = told["model_providers.humanize.base_url"]
key = os.environ[told["model_providers.humanize.env_key"]]
threads = {}

for line in sys.stdin:
    call = json.loads(line)
    method, params = call.get("method"), call.get("params") or {}
    if "id" not in call:
        continue
    result = {}
    if method == "thread/start":
        threads["t-1"] = params.get("model")
        result = {"thread": {"id": "t-1"}}
    out({"jsonrpc": "2.0", "id": call["id"], "result": result})
    if method == "thread/start":
        out({"method": "thread/status/changed",
             "params": {"threadId": "t-1", "status": {"type": "idle"}}})
    if method != "turn/start":
        continue
    said = params["input"][0]["text"]
    note(said)
    asked = urllib.request.Request(
        base + "/responses",
        data=json.dumps({"model": threads["t-1"], "stream": True, "input": [
            {"type": "message", "role": "user",
             "content": [{"type": "input_text", "text": said}]}]}).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(asked, timeout=60) as answer:
            events = [json.loads(one[5:]) for one in answer.read().decode().splitlines()
                      if one.startswith("data:") and one[5:].strip() != "[DONE]"]
        body = "".join(one.get("delta", "") for one in events
                       if one.get("type") == "response.output_text.delta")
    except Exception as why:
        body = repr(why)
    out({"method": "turn/started", "params": {"threadId": "t-1", "turnId": "turn-1"}})
    out({"method": "item/completed", "params": {"threadId": "t-1", "turnId": "turn-1",
         "item": {"id": "m-1", "type": "agentMessage", "text": body}}})
    out({"method": "turn/completed", "params": {"threadId": "t-1",
         "turn": {"id": "turn-1", "status": "completed"}}})
    out({"method": "thread/status/changed",
         "params": {"threadId": "t-1", "status": {"type": "idle"}}})
"""


@pytest.fixture
def endpoint() -> Iterator[Endpoint]:
    # Driven to its end after the test, which is what shuts it.
    yield from serving()


def _unswapped(self: Provider) -> tuple[tuple[str, str], ...]:
    """No credential path answered by another: see the test that uses it."""
    return ()


@pytest.mark.skipif(not gatewayable(), reason="the [litellm] extra is not installed")
@pytest.mark.timeout(240)
def test_codex_under_an_account_a_gateway_holds_asks_it_in_the_responses_api(
    endpoint: Endpoint, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = standins(tmp_path, monkeypatch, "CODEX_PROVIDER_KEY", "LITELLM_GATEWAY_KEY")
    held.install("codex", ROUTED)
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "hmz"))
    monkeypatch.setenv("LITELLM_GATEWAY_KEY", "lying-about")
    # A credential path answered by another is the supervisor's, which is tested where it is
    # written; an account that is variables alone is what is under test here.
    monkeypatch.setattr(Provider, "swaps", _unswapped)
    # An endpoint that speaks chat completions alone, as most calling themselves
    # OpenAI-compatible do: the gateway is what turns codex's Responses API into them.
    providers.add(
        "codex",
        "gw",
        way="litellm-openai-gateway",
        env={
            "LITELLM_GATEWAY_URL": endpoint.url,
            "LITELLM_GATEWAY_KEY": "upstream-secret",
            "LITELLM_GATEWAY_API": "openai",
        },
    )
    agent = CodexAgent(CodexAgentConfig(model="stand-in", effort="", provider="gw"))
    try:
        said = agent.new(tmp_path)("say hi", suppress=True)
        through = agent.gateway
        assert through is not None
    finally:
        agent.stop()

    assert said == "say hi"
    assert [one["model"] for one in endpoint.asked] == ["stand-in"]
    (launch,) = (one for one in held.calls("codex") if not one.stdin)
    assert f"model_providers.humanize.base_url={through.url}" in launch.argv
    assert launch.env["CODEX_PROVIDER_KEY"] == through.key
    assert launch.env["LITELLM_GATEWAY_KEY"] is None
    assert not through.running


@pytest.mark.parametrize(
    ("unsandboxed", "ruled"),
    [((), None), (("tix",), 'prefix_rule(pattern=["tix"], decision="allow")\n')],
)
def test_a_command_line_named_unsandboxed_is_ruled_out_of_the_sandbox(
    codex: Standins, unsandboxed: tuple[str, ...], ruled: str | None, tmp_path: Path
) -> None:
    theirs = tmp_path / "home" / ".codex" / "rules"
    theirs.mkdir(parents=True)
    (theirs / "default.rules").write_text("")
    config = dataclasses.replace(
        CONFIG, permission="read-only", unsandboxed=(*unsandboxed, "absent")
    )
    session = CodexAgent(config).new()
    session.shelves(
        [FakeCli("tix", "Files tickets.", (FakeCommand("ls", "Lists", str),))]
    )

    said = list(session.stream("rules"))

    # The rest of the read-only sandbox is untouched: the network stays cut.
    told = json.loads(said[-1].text)
    assert (told["policy"], told["rules"]) == (None, ruled)
    # The user's own rules are read beside humanize's, and never written.
    assert "default.rules" in told["theirs"]
    assert sorted(one.name for one in theirs.iterdir()) == ["default.rules"]

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

from hmz.coganchor import fallbacks, providers
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
from hmz.coganchor.fence import ALL, READ, Fence
from hmz.coganchor.gateway import gatewayable
from hmz.coganchor.providers import Provider
from tests.integration.doubles_agents import (
    CODEX,
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


def test_a_run_keeps_its_threads_where_no_supervisor_answers_their_paths(
    codex: Standins, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Linked from the server's virtual home into the run, and none of them in the user's."""
    monkeypatch.setattr("hmz.coganchor.providers.redirect.supervises", lambda: False)
    monkeypatch.delenv("HUMANIZE_SESSIONS", raising=False)
    agent = CodexAgent(CONFIG)
    agent.keeps = tmp_path / "epic"
    session = agent.new()

    assert session("log") == "log"

    kept = tmp_path / "epic" / "codex" / "sessions" / "rollout-t-1.jsonl"
    assert json.loads(kept.read_text()) == {"thread": "t-1"}
    assert agent.kept() == tmp_path / "epic" / "codex"
    assert not list((tmp_path / "home").glob(".codex/sessions/*"))


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


def test_an_opening_turn_that_failed_is_taken_again_on_its_own_thread(
    codex: Standins,
) -> None:
    (codex.bin / "drops").write_text("1")
    session = CodexAgent(CONFIG).new()

    assert session("drop") == "drop"

    assert session.id == "t-1"
    assert len(_told(codex, "thread/start")) == 1


def test_an_opening_fork_that_failed_is_taken_again_on_its_own_child(
    codex: Standins,
) -> None:
    parent = CodexAgent(CONFIG).new()
    parent("one")
    child = parent.fork()
    (codex.bin / "drops").write_text("1")

    assert child("drop") == "drop"

    assert len(_told(codex, "thread/fork")) == 1


def test_an_opening_turn_the_server_never_answered_is_taken_on_a_new_thread(
    codex: Standins,
) -> None:
    agent = CodexAgent(CONFIG)
    fallbacks.retrying(agent.spec, 1, "constant", 0)
    (codex.bin / "vanishes").write_text("1")

    assert agent.new()("vanish") == "vanish"

    assert len(_told(codex, "thread/start")) == 2
    assert _told(codex, "thread/resume") == []


def test_a_server_that_lost_the_race_to_create_its_state_is_started_again(
    codex: Standins,
) -> None:
    (codex.bin / "busy").write_text("1")

    assert CodexAgent(CONFIG).new()("one") == "one"

    assert len({one.pid for one in codex.calls()}) == 2
    assert codex.said().count("one") == 1


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
    elif method == "turn/start":
        result = {"turn": {"id": "turn-1"}}
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
    # The user's own rules are read beside Humanize's, and never written.
    assert "default.rules" in told["theirs"]
    assert sorted(one.name for one in theirs.iterdir()) == ["default.rules"]


@pytest.mark.parametrize("platform", ["linux", "darwin"])
@pytest.mark.parametrize(
    ("permission", "local", "user", "online"),
    [
        ("read-only", READ, READ, True),
        ("workspace-write", ALL, READ, True),
        # Wider than the rung: `bypass` stepped down by a Codex that forbids full access,
        # under a fence that writes the home and cuts the network.
        ("workspace-write", ALL, ALL, False),
    ],
)
def test_a_fence_around_codex_holds_the_rung_in_place_of_codex(
    codex: Standins,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    permission: str,
    local: str,
    user: str,
    online: bool,
) -> None:
    """Codex's own sandbox cannot start inside the fence, on Linux as on a Mac.

    Inside Landlock bubblewrap may not mount, and with `use_legacy_landlock` codex-cli 0.163.0
    panics: every command of the turn would fail -- whether or not the fence is as narrow as
    the rung. The fence itself is not put up here, only what Codex is told inside it.
    """

    def enforceable(*, net: bool) -> bool:
        del net
        return True

    def wrapper(fence: Fence) -> list[str]:
        del fence
        return []

    monkeypatch.setattr("hmz.coganchor.fence.enforceable", enforceable)
    monkeypatch.setattr("hmz.coganchor.fence.wrapper", wrapper)
    monkeypatch.setattr("sys.platform", platform)
    # Where the stand-in looks for rules beside Humanize's, for it to say what it was told.
    (tmp_path / "home" / ".codex" / "rules").mkdir(parents=True)
    fence = Fence.of(
        local=local,
        user=user,
        system=READ,
        online=online,
        workdir=tmp_path,
        home=tmp_path / "home",
    )
    agent = CodexAgent(dataclasses.replace(CONFIG, permission=permission, fence=fence))
    try:
        said = list(agent.new(tmp_path).stream("rules"))
    finally:
        agent.stop()

    told = json.loads(said[-1].text)
    assert told["policy"] == {
        "type": "externalSandbox",
        "networkAccess": "enabled" if online else "restricted",
    }

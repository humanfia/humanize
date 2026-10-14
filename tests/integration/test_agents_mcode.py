"""MiniMax Code, driven through `MiniMaxCodeAgent` against a stand-in `mcode` on PATH.

The stand-in is an `mcode exec --output-format stream-json`: one run per turn with the prompt
on stdin, answering in sequenced JSON lines -- the turn's tool calls, reasoning and message as
`item.*`, then `turn.completed` with what it spent and `exec.completed` with the result. A turn
that failed says `turn.failed`, and exits non-zero. A session is carried on by `--session`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import providers
from hmz.coganchor.agents import (
    SUBAGENTS,
    Failed,
    MiniMaxCodeAgent,
    MiniMaxCodeAgentConfig,
    Moment,
    Occasion,
)
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

MODEL = "custom_provider:gateway/minimax-stand-in"
CONFIG = MiniMaxCodeAgentConfig(model=MODEL, effort="", permission="bypass")

MCODE = r"""
prompt = sys.stdin.read()
note(prompt)
session = flags.get("--session", "mvs_stand_in")
turn = "turn_1"
at = [0]


def say(kind, **rest):
    at[0] += 1
    out({"schemaVersion": 1, "sequence": at[0], "timestampMs": 1, "runId": "exec_" + turn,
         "sessionId": session, "turnId": turn, "type": kind, **rest})


def tool(call, name, status, **rest):
    return {"id": call, "type": "tool_call",
            "toolCall": {"id": call, "name": name, "status": status, **rest}}


model = {"providerId": "custom_provider:gateway", "modelId": "minimax-stand-in"}
say("exec.started")
say("session.resumed" if "--session" in flags else "session.started")
say("turn.started")
say("item.started", item=tool("call_1", "bash", 4))
say("item.completed", item=tool("call_1", "bash", 2, input={"command": "ls src"},
                                 output={"content": [{"type": "text", "text": "x.py"}]}))
if prompt == "fleet":
    ask = {"description": "read the tests", "prompt": "read them", "subagent_type": "explore"}
    say("item.started", item=tool("call_2", "task", 4))
    say("item.updated", item=tool("call_2", "task", 1, input=ask))
    say("item.completed", item=tool("call_2", "task", 2, input=ask,
                                     output={"content": [{"type": "text", "text": "done"}]}))
say("item.completed", item={"id": "m1:reasoning", "type": "reasoning", "content": "hmm"})
say("item.completed", item={"id": "m1:message", "type": "agent_message", "content": prompt})
if prompt == "unfinished":
    error = {"category": "runtime", "message": "it could not finish", "retryable": False}
    say("turn.failed", status="failed", error=error, durationMs=12)
    say("exec.completed", result={"type": "exec.result", "sessionId": session,
                                  "turnId": turn, "status": "failed", "error": error})
    print("mcode exec failed: it could not finish.", file=sys.stderr)
    raise SystemExit(4)
usage = {"inputTokens": 130, "outputTokens": 12, "cacheReadTokens": 90, "totalTokens": 142}
say("turn.completed", model=model, usage=usage, usageIncomplete=False, durationMs=7)
say("exec.completed", result={"type": "exec.result", "sessionId": session, "turnId": turn,
                              "status": "succeeded", "model": model, "usage": usage,
                              "output": prompt})
"""


@pytest.fixture
def mcode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch)
    held.install("mcode", MCODE)
    return held


def test_a_turn_says_what_it_did_and_what_it_spent(mcode: Standins) -> None:
    said = list(MiniMaxCodeAgent(CONFIG).new().stream("hello"))

    assert kinds(said) == ["tool", "reasoning", "text", "result"]
    assert "ls src" in said[0].text
    assert said[-1].text == "hello"
    assert said[-1].spent.output == 12


def test_each_turn_is_a_run_of_exec_carrying_the_session_on(mcode: Standins) -> None:
    session = MiniMaxCodeAgent(CONFIG).new()

    assert session("one") == "one"
    assert session("two") == "two"

    first, second = mcode.calls()
    assert first.argv[0] == "exec"
    assert first.flag("--output-format") == "stream-json"
    assert first.flag("--model") == MODEL
    assert first.flag("--session") is None
    assert second.flag("--session") == session.id == "mvs_stand_in"
    assert mcode.said() == ["one", "two"]


def test_an_agent_it_starts_of_its_own_fires_the_subagent_moments(
    mcode: Standins,
) -> None:
    agent = MiniMaxCodeAgent(CONFIG)
    seen: list[Occasion] = []
    for moment in SUBAGENTS:
        agent.hooks.on(moment, seen.append)

    said = list(agent.new().stream("fleet"))

    assert "subagent" in kinds(said)
    assert [one.moment for one in seen] == [Moment.SUBAGENT_START, Moment.SUBAGENT_STOP]


def test_a_failed_turn_is_a_failure_with_what_it_said(mcode: Standins) -> None:
    session = MiniMaxCodeAgent(CONFIG).new()

    with pytest.raises(Failed, match="it could not finish") as failed:
        session("unfinished")

    assert failed.value.returncode == 4
    with pytest.raises(RuntimeError):
        _ = session.id


#: An `mcode` keeping the providers added to it in its home, as `provider add` and `provider
#: remove` say, and running a turn of `exec` on one of them: chat completions at its base URL
#: under the key it was added with, streamed -- refusing a model it was not added with.
ROUTED = r"""
import urllib.request

kept = pathlib.Path(os.environ["HOME"]) / ".minimax" / "providers.json"
added = json.loads(kept.read_text()) if kept.exists() else {}
if argv[:1] == ["provider"]:
    note(" ".join(argv))
    if argv[1] == "remove":
        if added.pop(argv[2].removeprefix("custom_provider:"), None) is None:
            raise SystemExit(1)
    else:
        added[flags["--name"]] = {"base": flags["--base-url"], "model": flags["--model"],
                                  "format": flags["--api-format"],
                                  "key": os.environ[flags["--api-key-env"]]}
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text(json.dumps(added))
    raise SystemExit(0)

prompt = sys.stdin.read()
note(prompt)
named, _, model = flags["--model"].removeprefix("custom_provider:").partition("/")
provider = added[named]
assert provider["model"] == model, model
request = urllib.request.Request(
    provider["base"] + "/chat/completions",
    data=json.dumps({"model": model, "stream": True,
                     "messages": [{"role": "user", "content": prompt}]}).encode(),
    headers={"Authorization": "Bearer " + provider["key"],
             "Content-Type": "application/json"})
with urllib.request.urlopen(request, timeout=60) as answer:
    chunks = [json.loads(one[5:]) for one in answer.read().decode().splitlines()
              if one.startswith("data:") and one[5:].strip() != "[DONE]"]
body = "".join(one["choices"][0]["delta"].get("content") or ""
               for one in chunks if one.get("choices"))
session = flags.get("--session", "mvs_stand_in")
out({"type": "exec.started", "sessionId": session})
out({"type": "item.completed", "sessionId": session,
     "item": {"type": "agent_message", "content": body}})
out({"type": "turn.completed", "sessionId": session, "usage": {"outputTokens": 7},
     "model": {"providerId": "custom_provider:" + named, "modelId": model}})
out({"type": "exec.completed", "sessionId": session, "result": {"status": "succeeded"}})
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
def test_mcode_under_an_account_a_gateway_holds_runs_the_model_through_it(
    endpoint: Endpoint, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = standins(tmp_path, monkeypatch, "LITELLM_GATEWAY_KEY", "MINIMAX_DATA_DIR")
    held.install("mcode", ROUTED)
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "hmz"))
    monkeypatch.setenv("LITELLM_GATEWAY_KEY", "lying-about")
    # A credential path answered by another is the supervisor's, tested where it is written.
    monkeypatch.setattr(Provider, "swaps", _unswapped)
    providers.add(
        "mcode",
        "gw",
        way="litellm-openai-gateway",
        env={
            "LITELLM_GATEWAY_URL": endpoint.url,
            "LITELLM_GATEWAY_KEY": "upstream-secret",
            "LITELLM_GATEWAY_API": "openai",
        },
    )
    agent = MiniMaxCodeAgent(
        MiniMaxCodeAgentConfig(model="stand-in", effort="", provider="gw")
    )
    try:
        session = agent.new(tmp_path)
        said = [session("say hi"), session("say more")]
        through = agent.gateway
        assert through is not None
    finally:
        agent.stop()

    assert said == ["say hi", "say more"]
    assert [one["model"] for one in endpoint.asked] == ["stand-in", "stand-in"]
    added, turn, again, _ = held.calls("mcode")
    named = added.flag("--name") or ""
    assert named.startswith(f"hmz-{through.port}-")
    assert added.stdin == (
        f"provider add --name {named} --base-url {through.url} --api-format "
        "openai-completions --model stand-in --api-key-env MCODE_PROVIDER_API_KEY"
    )
    # Added once a turn, into the copy of `config.yaml` in the virtual home that turn starts
    # in -- never the account's own -- and so with nothing to take out afterwards.
    assert again.stdin == added.stdin
    home = added.env["MINIMAX_DATA_DIR"]
    assert home == turn.env["MINIMAX_DATA_DIR"]
    assert home != again.env["MINIMAX_DATA_DIR"]
    assert home is not None
    assert not Path(home).exists()
    assert turn.flag("--model") == f"custom_provider:{named}/stand-in"
    assert turn.env["LITELLM_GATEWAY_KEY"] is None
    assert not through.running

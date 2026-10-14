"""Antigravity, driven through `AntigravityCLIAgent` against a stand-in `agy` on PATH.

The stand-in is an `agy --print` answering in the events of one turn -- an `init`, a
`step_update` per step, and a `result` -- or, given `--input-format stream-json`, the same for
each message on a stdin held open. Like the real one it insists on hearing the effort exactly
once: from the model's name, or from `--effort`, never both and never neither. And like the
real one it reads a plugin's `mcp_config.json` out of every directory it is given with
`--add-dir`: a prompt `call <tool>` starts that server, lists its tools and calls the one named,
answering with what it said.
"""

from __future__ import annotations

import tempfile
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import providers
from hmz.coganchor.agents import (
    AntigravityCLIAgent,
    AntigravityCLIAgentConfig,
    Failed,
    FakeTool,
    Unserved,
)
from hmz.coganchor.agents.skills import Loaded
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

CONFIG = AntigravityCLIAgentConfig(model="gemini-stand-in", effort="high")

AGY = r"""
import subprocess
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


def called(name):
    added = [value for flag, value in zip(argv, argv[1:]) if flag == "--add-dir"]
    for root in added:
        for found in pathlib.Path(root).glob(".agents/plugins/*/mcp_config.json"):
            for server in json.loads(found.read_text())["mcpServers"].values():
                spoken = subprocess.Popen([server["command"], *server["args"]],
                                          stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          text=True)
                asked = [{"method": "initialize", "params": {}},
                         {"method": "tools/list"},
                         {"method": "tools/call", "params": {"name": name, "arguments": {}}}]
                answers = []
                for index, one in enumerate(asked):
                    spoken.stdin.write(json.dumps({"jsonrpc": "2.0", "id": index, **one}) + "\n")
                    spoken.stdin.flush()
                    answers.append(json.loads(spoken.stdout.readline())["result"])
                spoken.stdin.close()
                spoken.wait()
                if any(tool["name"] == name for tool in answers[1]["tools"]):
                    return answers[2]["content"][0]["text"]
    return "no tool " + name


def home():
    named = [one.partition("=")[2] for one in argv if one.startswith("--app_data_dir=")]
    at = pathlib.Path(os.environ["HOME"], ".gemini", *named[-1:] or ["antigravity-cli"])
    return " ".join(sorted("%s/%s" % (kind, one.name) for kind in ("agents", "skills")
                           for one in (at / kind).iterdir() if (at / kind).is_dir()))


def turn(said):
    note(said)
    if said.startswith("call "):
        said = called(said.removeprefix("call "))
    if said == "home":
        said = home()
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


def test_a_turn_runs_in_a_virtual_home_of_humanizes_agents_and_the_flows_skills(
    agy: Standins, tmp_path: Path
) -> None:
    real = tmp_path / "home" / ".gemini" / "antigravity-cli"
    (real / "agents").mkdir(parents=True)
    (real / "agents" / "mine.md").write_text("the user's own\n")
    skill = tmp_path / "flow" / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: review\n---\n")
    agent = AntigravityCLIAgent(
        AntigravityCLIAgentConfig(
            model="gemini-stand-in", effort="high", permission="read-only"
        )
    )
    agent.loads([Loaded("review", skill)])

    said = agent.new()("home")

    found = said.split()
    assert "agents/hmz-read-only.md" in found
    assert "agents/mine.md" in found
    assert "skills/review" in found
    assert sorted(one.name for one in (real / "agents").iterdir()) == ["mine.md"]
    assert not (real / "skills").exists()


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


#: An `agy` in enterprise-gateway mode, as the real one is under `AGY_LLM_GATEWAY_URL`: it
#: takes only a model its gateway was told it serves and no effort for it, and streams Chat
#: Completions from `{url}/v1/chat/completions` under the gateway's key.
AGY_GATEWAY = r"""
import urllib.request

served = os.environ.get("AGY_LLM_GATEWAY_MODELS", "").split(",")
model = flags.get("--model", "")
if model not in served:
    sys.exit("model %s is not served by the gateway" % model)
if "--effort" in argv:
    sys.exit("--effort is not supported for model %s" % model)
assert os.environ["AGY_LLM_GATEWAY_WIRE_PROTOCOL"] == "openai"
for line in sys.stdin:
    said = json.loads(line)["message"]["content"]
    note(said)
    asked = urllib.request.Request(
        os.environ["AGY_LLM_GATEWAY_URL"] + "/v1/chat/completions",
        data=json.dumps({"model": model, "stream": True,
                         "messages": [{"role": "user", "content": said}]}).encode(),
        headers={"Authorization": "Bearer " + os.environ["AGY_LLM_GATEWAY_API_KEY"],
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(asked, timeout=60) as answer:
        pieces = [json.loads(one[5:]) for one in answer.read().decode().splitlines()
                  if one.startswith("data:") and one[5:].strip() != "[DONE]"]
    body = "".join(one["choices"][0]["delta"].get("content") or ""
                   for one in pieces if one.get("choices"))
    out({"event": "result", "result": {"conversation_id": "conv-gw", "status": "SUCCESS",
         "response": body, "usage": {"input_tokens": 1, "output_tokens": 1}}})
"""


def _unswapped(self: Provider) -> tuple[tuple[str, str], ...]:
    """No credential path answered by another: an account of variables alone is under test."""
    return ()


@pytest.fixture
def endpoint() -> Iterator[Endpoint]:
    # Driven to its end after the test, which is what shuts it.
    yield from serving()


@pytest.mark.timeout(240)
@pytest.mark.skipif(not gatewayable(), reason="the [litellm] extra is not installed")
def test_agy_under_an_account_a_gateway_holds_is_its_openai_gateway(
    endpoint: Endpoint, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = standins(
        tmp_path,
        monkeypatch,
        "AGY_LLM_GATEWAY_URL",
        "AGY_LLM_GATEWAY_API_KEY",
        "AGY_LLM_GATEWAY_MODELS",
        "LITELLM_GATEWAY_KEY",
    )
    held.install("agy", AGY_GATEWAY)
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "hmz"))
    monkeypatch.setenv("LITELLM_GATEWAY_KEY", "lying-about")
    monkeypatch.setattr(Provider, "swaps", _unswapped)
    providers.add(
        "agy",
        "gw",
        way="litellm-openai-gateway",
        env={
            "LITELLM_GATEWAY_URL": endpoint.url,
            "LITELLM_GATEWAY_KEY": "upstream-secret",
            "LITELLM_GATEWAY_API": "openai",
        },
    )
    agent = AntigravityCLIAgent(
        AntigravityCLIAgentConfig(model="stand-in", effort="high", provider="gw")
    )
    try:
        said = agent.new(tmp_path)("say hi", suppress=True)
        through = agent.gateway
        assert through is not None
    finally:
        agent.stop()

    assert "say hi" in said
    assert [one["model"] for one in endpoint.asked] == ["stand-in"]
    env = held.calls("agy")[0].env
    assert env["AGY_LLM_GATEWAY_URL"] == through.url
    assert env["AGY_LLM_GATEWAY_API_KEY"] == through.key
    assert env["AGY_LLM_GATEWAY_MODELS"] == "stand-in"
    assert env["LITELLM_GATEWAY_KEY"] is None
    assert not through.running


def test_a_tool_the_flow_offers_is_called_through_a_plugin_of_humanizes(
    agy: Standins,
) -> None:
    asked: list[str] = []
    session = AntigravityCLIAgent(CONFIG).new()

    def secret() -> str:
        asked.append("secret")
        return "zanzibar-417"

    session.offers([FakeTool("secret", "Says the secret word.", secret)])

    assert session("call secret") == "zanzibar-417"
    assert asked == ["secret"]
    session.offers(None)
    assert session("call secret") == "no tool secret"
    first, second = agy.calls()
    assert first.pid != second.pid


def test_tools_carried_where_agy_would_run_its_commands_are_refused(
    agy: Standins, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = AntigravityCLIAgent(CONFIG)
    # Served first, so that its socket is not under the temporary directory moved below.
    agent.toolbox.address()
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "a"))
    session = agent.new(tmp_path / "b")
    session.offers([FakeTool("secret", "Says the secret word.", lambda: "")])

    with pytest.raises(Unserved, match="first of its directories"):
        session("call secret")
    assert agy.calls() == []

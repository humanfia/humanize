"""A local LiteLLM gateway, run for real, in front of a stand-in OpenAI-compatible endpoint.

The gateway is litellm's own proxy, started by `Gateway` as it is for a turn; the endpoint is
`doubles_agents.serving`, in the test's own process. A turn is driven through it twice: asked
of the gateway directly, in the protocol Claude Code speaks, and by `ClaudeCodeAgent` driving
a stand-in `claude` that asks the gateway it was pointed at.
"""

from __future__ import annotations

import json
import os
import stat
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any, cast

import psutil
import pytest

from hmz.coganchor import providers
from hmz.coganchor.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig
from hmz.coganchor.gateway import Gateway, gatewayable
from hmz.coganchor.providers import Provider
from tests.integration.doubles_agents import Endpoint, serving, standins

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = [
    pytest.mark.skipif(
        not gatewayable(), reason="the [litellm] extra is not installed"
    ),
    pytest.mark.timeout(240),
]


@pytest.fixture
def endpoint() -> Iterator[Endpoint]:
    # Driven to its end after the test, which is what shuts it.
    yield from serving()


def _account(endpoint: Endpoint) -> Provider:
    return Provider(
        cli="claude",
        name="gw",
        way="litellm-openai-gateway",
        env={
            "LITELLM_GATEWAY_URL": endpoint.url,
            "LITELLM_GATEWAY_KEY": "upstream-secret",
            "LITELLM_GATEWAY_API": "openai",
        },
    )


def _asked(url: str, key: str, prompt: str) -> str:
    """One Messages API turn, streamed, as Claude Code asks one: the text it streamed back."""
    asked = urllib.request.Request(  # noqa: S310 -- the gateway on loopback
        f"{url}/v1/messages",
        data=json.dumps(
            {
                "model": "stand-in",
                "max_tokens": 64,
                "stream": True,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        },
    )
    said: list[str] = []
    with urllib.request.urlopen(asked, timeout=60) as answer:  # noqa: S310
        for line in answer:
            text = line.decode().strip()
            if not text.startswith("data:"):
                continue
            event: dict[str, Any] = json.loads(text.removeprefix("data:"))
            delta = cast("dict[str, Any]", event.get("delta") or {})
            if delta.get("type") == "text_delta":
                said.append(str(delta.get("text") or ""))
    return "".join(said)


def test_a_gateway_answers_in_claudes_protocol_from_the_accounts_endpoint(
    endpoint: Endpoint,
) -> None:
    held = Gateway(_account(endpoint))
    try:
        assert _asked(held.url, held.key, "say hi") == "say hi"
        assert [one["model"] for one in endpoint.asked] == ["stand-in"]
        with pytest.raises(urllib.error.HTTPError) as refused:
            _asked(held.url, "sk-somebody-else", "say hi")
        assert refused.value.code in (400, 401, 403)
        # What it holds is its own, and nowhere a process listing shows it.
        proxy = _proxy(held)
        argv = " ".join(proxy.cmdline())
        assert "upstream-secret" not in argv
        assert held.key not in argv
        config = argv.split("--config ")[1].split(" ")[0]
        assert stat.S_IMODE(os.stat(config).st_mode) == 0o600  # noqa: PTH116
    finally:
        held.stop()
    assert not held.running
    assert not os.path.exists(config)  # noqa: PTH110
    assert not proxy.is_running() or proxy.status() == psutil.STATUS_ZOMBIE


def _proxy(held: Gateway) -> psutil.Process:
    """The process a gateway is, found as this process's child listening where it is."""
    port = f"--port {held.port}"
    return next(
        one
        for one in psutil.Process().children(recursive=True)
        if port in " ".join(one.cmdline())
    )


def _unswapped(self: Provider) -> tuple[tuple[str, str], ...]:
    """No credential path answered by another: see the test that uses it."""
    return ()


#: A `claude` that asks wherever it was pointed, under the token it was given, and says what
#: came back as Claude Code says a turn's result -- and what it was run with.
CLAUDE = r"""
import urllib.request

note()
session = flags.get("--session-id") or flags.get("--resume") or "s-none"
model = flags.get("--model")
out({"type": "system", "subtype": "init", "session_id": session, "model": model})
for line in sys.stdin:
    said = json.loads(line)["message"]["content"][0]["text"]
    note(said)
    asked = urllib.request.Request(
        os.environ["ANTHROPIC_BASE_URL"] + "/v1/messages",
        data=json.dumps({"model": model, "max_tokens": 64, "stream": True,
                         "messages": [{"role": "user", "content": said}]}).encode(),
        headers={"Authorization": "Bearer " + os.environ["ANTHROPIC_AUTH_TOKEN"],
                 "Content-Type": "application/json", "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(asked, timeout=60) as answer:
            events = [json.loads(one[5:]) for one in answer.read().decode().splitlines()
                      if one.startswith("data:")]
        body = "".join(one["delta"].get("text", "") for one in events if "delta" in one)
    except Exception as why:
        body = repr(why)
    out({"type": "result", "subtype": "success", "is_error": False, "session_id": session,
         "result": body, "usage": {"input_tokens": 1, "output_tokens": 1},
         "modelUsage": {model: {"inputTokens": 1, "outputTokens": 1}}})
"""


def test_claude_under_an_account_a_gateway_holds_is_pointed_at_it(
    endpoint: Endpoint, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = standins(
        tmp_path,
        monkeypatch,
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "LITELLM_GATEWAY_KEY",
    )
    held.install("claude", CLAUDE)
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "hmz"))
    monkeypatch.setenv("LITELLM_GATEWAY_KEY", "lying-about")
    # A credential path answered by another is the supervisor's, which is tested where it is
    # written; an account that is variables alone is what is under test here.
    monkeypatch.setattr(Provider, "swaps", _unswapped)
    account = _account(endpoint)
    providers.add("claude", "gw", way=account.way, env=account.env)
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="stand-in", effort="", provider="gw")
    )
    try:
        said = agent.new(tmp_path)("say hi", suppress=True)
        through = agent.gateway
        assert through is not None
    finally:
        agent.stop()

    assert "say hi" in said
    assert endpoint.asked
    env = held.calls("claude")[0].env
    assert env["ANTHROPIC_BASE_URL"] == through.url
    assert env["ANTHROPIC_AUTH_TOKEN"] == through.key
    assert env["LITELLM_GATEWAY_KEY"] is None
    assert not through.running

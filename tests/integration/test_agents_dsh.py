"""DeepSeek Harness, driven through `DshAgent` and its SDK against a loopback endpoint.

The harness is the SDK's own bundled runtime, started by the driver as it would be anywhere;
what it calls is the model, which here is an `Endpoint` on the loopback that
`DEEPSEEK_BASE_URL` points it at. So a turn is the whole path -- the driver composing the
runtime, the SDK's JSON-RPC to it, the runtime's chat completion -- with only the model
standing in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.agents import DshAgent, DshAgentConfig, Failed
from tests.integration.doubles_agents import Endpoint, kinds, serving

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

CONFIG = DshAgentConfig(model="deepseek-stand-in", effort="high")


@pytest.fixture
def endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Endpoint]:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "dsh"))
    monkeypatch.chdir(tmp_path)
    for held in serving():
        monkeypatch.setenv("DEEPSEEK_BASE_URL", held.url)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-stand-in")
        yield held


def _conversation(asked: dict[str, Any]) -> list[tuple[str, str]]:
    """What one request carried of the conversation, leaving out the harness's own prompt."""
    return [
        (str(one["role"]), str(one.get("content") or ""))
        for one in asked["messages"]
        if one["role"] != "system"
    ]


def test_a_turn_says_what_it_thought_said_and_spent(endpoint: Endpoint) -> None:
    said = list(DshAgent(CONFIG).new().stream("hello"))

    assert kinds(said) == ["reasoning", "text", "result"]
    assert said[0].text == "thinking about hello"
    assert said[-1].text == "hello"
    assert dict(said[-1].tokens) == {"deepseek-stand-in": 18}
    assert said[-1].spent.output == 7
    (asked,) = endpoint.asked
    assert asked["model"] == "deepseek-stand-in"
    assert asked["reasoning_effort"] == "high"
    assert _conversation(asked) == [("user", "hello")]


def test_a_second_turn_carries_the_session_on(endpoint: Endpoint) -> None:
    agent = DshAgent(CONFIG)
    session = agent.new()

    assert session("one") == "one"
    assert session("two") == "two"

    assert _conversation(endpoint.asked[-1]) == [
        ("user", "one"),
        ("assistant", "one"),
        ("user", "two"),
    ]
    assert agent.opened == [session.id]


def test_a_refused_request_is_a_failed_turn_leaving_nothing_open(
    endpoint: Endpoint,
) -> None:
    agent = DshAgent(CONFIG)
    session = agent.new()

    with pytest.raises(Failed):
        session("unfinished")
    assert agent.opened == []


def test_a_model_gone_silent_is_given_up_on_by_the_watchdog(
    endpoint: Endpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_WATCHDOG", "1")

    with pytest.raises(Failed):
        DshAgent(CONFIG).new()("hang")

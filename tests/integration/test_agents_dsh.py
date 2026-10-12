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

from hmz.coganchor.agents import DshAgent, DshAgentConfig, Failed, Unrecoverable
from tests.integration.doubles_agents import Endpoint, harnessed, kinds, serving

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
    """What one request carried of the conversation, leaving out what the harness wrote."""
    return [
        (str(one["role"]), str(one.get("content") or ""))
        for one in asked["messages"]
        if one["role"] != "system" and not harnessed(one)
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


def test_a_callback_offered_is_run_here_when_the_model_reaches_for_it(
    endpoint: Endpoint,
) -> None:
    from pydantic import BaseModel

    from hmz.coganchor.agents import FakeTool

    class Asked(BaseModel):
        word: str

    heard: list[str] = []

    def shout(asked: Asked) -> str:
        heard.append(asked.word)
        return asked.word.upper()

    session = DshAgent(CONFIG).new()
    session.offers([FakeTool("shout", "Says a word louder.", shout, Asked)])

    said = session('use shout {"word": "hi"}')

    assert heard == ["hi"]
    assert said == "the tool said HI"
    offered = [one["function"]["name"] for one in endpoint.asked[0]["tools"]]
    assert "mcp__humanize__shout" in offered


def test_a_new_effort_after_a_turn_is_refused_before_the_runtime_is(
    endpoint: Endpoint,
) -> None:
    session = DshAgent(CONFIG).new()
    assert session("one") == "one"

    session.effort = "low"
    with pytest.raises(Unrecoverable, match="cannot carry") as refused:
        session("two")

    assert "already exists" not in str(refused.value)
    assert len(endpoint.asked) == 1


def test_other_tools_after_a_turn_are_refused_before_the_runtime_is(
    endpoint: Endpoint,
) -> None:
    from pydantic import BaseModel

    from hmz.coganchor.agents import FakeTool

    class Asked(BaseModel):
        word: str

    def shout(asked: Asked) -> str:
        return asked.word.upper()

    session = DshAgent(CONFIG).new()
    assert session("one") == "one"

    session.offers([FakeTool("shout", "Says a word louder.", shout, Asked)])
    with pytest.raises(Unrecoverable, match="cannot carry") as refused:
        session("two")

    assert "already exists" not in str(refused.value)
    assert len(endpoint.asked) == 1


def test_a_fresh_session_takes_its_first_turn_at_a_new_effort(
    endpoint: Endpoint,
) -> None:
    session = DshAgent(CONFIG).new()

    session.effort = "low"

    assert session("one") == "one"
    (asked,) = endpoint.asked
    assert asked["reasoning_effort"] == "low"

"""A model called through litellm, driven by `LiteLLMAgent` against a loopback endpoint.

No CLI here: a turn is one streamed chat completion from this process, sent by litellm to the
OpenAI-compatible endpoint `OPENAI_BASE_URL` names -- which is an `Endpoint` on the loopback.
The conversation is a file of humanize's own, so a second turn is the first one's messages sent
again with the new prompt on the end.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel

from hmz.coganchor.agents import Failed, LiteLLMAgent, LiteLLMAgentConfig
from tests.integration.doubles_agents import Endpoint, kinds, serving

if TYPE_CHECKING:
    from collections.abc import Iterator

CONFIG = LiteLLMAgentConfig(model="openai/stand-in", effort="")


class Shape(BaseModel):
    value: str


@pytest.fixture
def endpoint(monkeypatch: pytest.MonkeyPatch) -> Iterator[Endpoint]:
    for held in serving():
        monkeypatch.setenv("OPENAI_BASE_URL", held.url)
        monkeypatch.setenv("OPENAI_API_BASE", held.url)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-stand-in")
        yield held


def test_a_turn_says_what_it_thought_said_and_spent(endpoint: Endpoint) -> None:
    said = list(LiteLLMAgent(CONFIG).new().stream("hello"))

    assert kinds(said) == ["reasoning", "text", "result"]
    assert said[0].text == "thinking about hello"
    assert said[-1].text == "hello"
    assert dict(said[-1].tokens) == {"openai/stand-in": 18}
    assert said[-1].spent.output == 7
    (asked,) = endpoint.asked
    assert asked["model"] == "stand-in"
    assert asked["stream"] is True
    assert asked["messages"] == [{"role": "user", "content": "hello"}]


def test_a_second_turn_sends_the_conversation_so_far(endpoint: Endpoint) -> None:
    agent = LiteLLMAgent(CONFIG)
    session = agent.new()

    assert session("one") == "one"
    assert session("two") == "two"

    assert endpoint.asked[1]["messages"] == [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "one"},
        {"role": "user", "content": "two"},
    ]
    assert agent.opened == [session.id]


def test_a_fork_carries_the_conversation_and_goes_its_own_way(
    endpoint: Endpoint,
) -> None:
    session = LiteLLMAgent(CONFIG).new()
    session("one")

    child = session.fork()
    assert child("two") == "two"
    assert session("three") == "three"

    assert child.id != session.id
    assert [one["content"] for one in endpoint.asked[2]["messages"]] == [
        "one",
        "one",
        "three",
    ]


def test_a_turn_held_to_a_shape_answers_with_the_object(endpoint: Endpoint) -> None:
    session = LiteLLMAgent(CONFIG).new()

    assert session("shaped", schema=Shape) == Shape(value="shaped")
    assert endpoint.asked[0]["response_format"]["type"] == "json_schema"


def test_a_refused_request_is_a_failed_turn_leaving_nothing_open(
    endpoint: Endpoint,
) -> None:
    agent = LiteLLMAgent(CONFIG)
    session = agent.new()

    with pytest.raises(Failed, match="it could not finish"):
        session("unfinished")
    assert agent.opened == []


@pytest.mark.timeout(6)
@pytest.mark.xfail(
    strict=True,
    reason="the watchdog's cut closes litellm's stream wrapper, which does not close the "
    "socket a read is blocked on, so a silent endpoint holds the turn for the full 600s",
)
def test_an_endpoint_gone_silent_is_given_up_on_by_the_watchdog(
    endpoint: Endpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_WATCHDOG", "1")

    with pytest.raises(Failed):
        LiteLLMAgent(CONFIG).new()("hang")

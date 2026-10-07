"""A model called through litellm, driven by `LiteLLMAgent` against a loopback endpoint.

No CLI here: a turn is one streamed chat completion from this process, sent by litellm to the
OpenAI-compatible endpoint `OPENAI_BASE_URL` names -- which is an `Endpoint` on the loopback.
The conversation is a file of humanize's own, so a second turn is the first one's messages sent
again with the new prompt on the end.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import litellm
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


# Far short of the 600s a turn would wait without the cut, and long enough for litellm's
# first import on a cold CI runner, which alone can take several seconds.
@pytest.mark.timeout(30)
@pytest.mark.parametrize("n", range(40))
def test_an_endpoint_gone_silent_is_given_up_on_by_the_watchdog(
    endpoint: Endpoint, monkeypatch: pytest.MonkeyPatch, n: int
) -> None:
    monkeypatch.setenv("HUMANIZE_WATCHDOG", "1")

    with pytest.raises(Failed):
        LiteLLMAgent(CONFIG).new()("hang")


class _Opened:
    """An answer whose opening took longer than the watchdog's whole ladder.

    Its first chunk is read while it is opened, as litellm may do, and then the opening
    stalls past every rung: by the time the turn holds the answer there is nothing left that
    will cut it, and nothing more is coming off the wire to wake its read.
    """

    def __init__(self, answer: litellm.CustomStreamWrapper, ladder: float) -> None:
        # What the turn closes to cut the answer, so it is the one thing carried over.
        self.completion_stream: object = vars(answer)["completion_stream"]
        self._answer = answer
        next(answer)
        time.sleep(ladder)

    def __iter__(self) -> Iterator[object]:
        return self._answer


@pytest.mark.timeout(30)
def test_an_endpoint_gone_silent_while_its_answer_opened_is_given_up_on(
    endpoint: Endpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_WATCHDOG", "1")
    completion = litellm.completion

    def opened(**asked: object) -> _Opened:
        answer = completion(**asked)
        assert isinstance(answer, litellm.CustomStreamWrapper)
        return _Opened(answer, 6)

    monkeypatch.setattr(litellm, "completion", opened)

    with pytest.raises(Failed):
        LiteLLMAgent(CONFIG).new()("hang")

"""A model called directly through litellm: the call a turn is, and the file it keeps.

litellm itself is stood in for by a module of this test's own, put where `import litellm`
finds it: each turn is one `completion(...)`, recorded, answered with scripted chunks.
"""

from __future__ import annotations

import json
import sys
import types
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel

from hmz.coganchor import providers
from hmz.coganchor.agents import (
    Failed,
    LiteLLMAgent,
    LiteLLMAgentConfig,
    LiteLLMSession,
    SessionBase,
    Unrecoverable,
)
from hmz.coganchor.agents.litellm import LOCAL_MAP
from hmz.coganchor.fence import Fence
from hmz.coganchor.providers import Provider

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path


#: What every agent here is made with unless a test says otherwise.
_DEFAULTS: dict[str, Any] = {"model": "openai/gpt-x", "effort": ""}


class _LiteLLM(types.ModuleType):
    """`litellm`, as far as a turn reaches into it."""

    def __init__(self) -> None:
        super().__init__("litellm")
        self.calls: list[dict[str, Any]] = []
        self.chunks: list[Any] = []
        self.raising: Exception | None = None
        self.schemas = True

    def completion(self, **kwargs: Any) -> Iterator[Any]:
        self.calls.append(kwargs)
        if self.raising is not None:
            raise self.raising
        return iter(self.chunks)

    def supports_response_schema(self, model: str) -> bool:
        del model
        return self.schemas


@pytest.fixture
def litellm(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _LiteLLM:
    """The stand-in, importable as `litellm`, with a home of the test's own."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv(LOCAL_MAP, "True")
    held = _LiteLLM()
    held.chunks = _answer("Hello", " there")
    monkeypatch.setitem(sys.modules, "litellm", held)
    return held


def _answer(*pieces: str, thinking: str = "", **usage: Any) -> list[Any]:
    """The chunks one streamed answer comes in, the usage on the last."""
    chunks: list[Any] = []
    if thinking:
        chunks.append({"choices": [{"delta": {"reasoning_content": thinking}}]})
    chunks += [{"choices": [{"delta": {"content": one}}]} for one in pieces]
    chunks.append({"choices": [], "usage": usage or None})
    return chunks


def _agent(tmp_path: Path, **given: Any) -> LiteLLMAgent:
    agent = LiteLLMAgent(LiteLLMAgentConfig(**_DEFAULTS | given))
    agent.keeps = tmp_path / "kept"
    return agent


def _kept(agent: LiteLLMAgent, session: SessionBase) -> list[dict[str, Any]]:
    kept = agent.kept()
    assert kept is not None
    lines = (kept / "sessions" / f"{session.id}.jsonl").read_text().splitlines()
    return [json.loads(one) for one in lines]


def test_a_turn_is_one_streamed_completion(litellm: _LiteLLM, tmp_path: Path) -> None:
    session = _agent(tmp_path, effort="high").new(tmp_path)
    assert isinstance(session, LiteLLMSession)
    assert session("hi") == "Hello there"
    (call,) = litellm.calls
    assert call["model"] == "openai/gpt-x"
    assert call["messages"] == [{"role": "user", "content": "hi"}]
    assert call["stream"] is True
    assert call["stream_options"] == {"include_usage": True}
    assert call["drop_params"] is True
    assert call["reasoning_effort"] == "high"
    assert "api_key" not in call
    assert "response_format" not in call


def test_no_effort_sends_no_reasoning_effort(litellm: _LiteLLM, tmp_path: Path) -> None:
    _agent(tmp_path).new(tmp_path)("hi")
    assert "reasoning_effort" not in litellm.calls[0]


def test_the_next_turn_sends_the_conversation_so_far(
    litellm: _LiteLLM, tmp_path: Path
) -> None:
    agent = _agent(tmp_path)
    session = agent.new(tmp_path)
    session("one")
    litellm.chunks = _answer("second")
    assert session("two") == "second"
    assert litellm.calls[1]["messages"] == [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "Hello there"},
        {"role": "user", "content": "two"},
    ]
    rows = _kept(agent, session)
    assert rows[0]["type"] == "session"
    assert rows[0]["id"] == session.id
    assert [row["message"]["role"] for row in rows[1:]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_a_turn_says_its_words_and_what_they_cost(
    litellm: _LiteLLM, tmp_path: Path
) -> None:
    litellm.chunks = _answer(
        "ok",
        thinking="let me see",
        prompt_tokens=100,
        completion_tokens=7,
        prompt_tokens_details={"cached_tokens": 30},
        cache_creation_input_tokens=10,
    )
    agent = _agent(tmp_path)
    session = agent.new(tmp_path)
    events = list(session.stream("hi"))
    assert [(one.kind, one.text) for one in events[:-1]] == [
        ("reasoning", "let me see"),
        ("text", "ok"),
    ]
    result = events[-1]
    assert (result.kind, result.text) == ("result", "ok")
    assert dict(result.spent) == {
        "input": 60,
        "output": 7,
        "cache_read": 30,
        "cache_write": 10,
    }
    assert result.tokens == {"openai/gpt-x": 107}
    assert session.spent().total == 107
    answer = _kept(agent, session)[-1]["message"]
    assert answer["reasoning"] == "let me see"
    assert answer["usage"]["output"] == 7


class _Shape(BaseModel):
    ok: bool


@pytest.mark.parametrize("held", [True, False])
def test_a_shaped_turn_asks_for_the_schema_and_reads_it_back(
    litellm: _LiteLLM, tmp_path: Path, held: bool
) -> None:
    litellm.schemas = held
    litellm.chunks = _answer('{"ok": true}')
    assert _agent(tmp_path).new(tmp_path)("judge", schema=_Shape) == _Shape(ok=True)
    call = litellm.calls[0]
    assert call["response_format"]["json_schema"]["name"] == "_Shape"
    asked = call["messages"][-1]["content"]
    assert (asked == "judge") is held
    assert asked.startswith("judge")


def test_a_failed_call_is_a_failed_turn_that_opens_nothing(
    litellm: _LiteLLM, tmp_path: Path
) -> None:
    litellm.raising = RuntimeError("boom")
    session = _agent(tmp_path).new(tmp_path)
    with pytest.raises(RuntimeError, match="boom"):
        session("hi")
    litellm.raising = KeyError("the model refused")
    with pytest.raises(Failed, match="KeyError") as failed:
        session("hi")
    assert not isinstance(failed.value, Unrecoverable)
    assert session.named is None
    assert session("hi", suppress=True) == ""


def test_a_conversation_too_long_for_the_model_is_unrecoverable(
    litellm: _LiteLLM, tmp_path: Path
) -> None:
    class ContextWindowExceededError(Exception):
        pass

    litellm.raising = ContextWindowExceededError("too long")
    with pytest.raises(Unrecoverable):
        _agent(tmp_path).new(tmp_path)("hi", suppress=True)


def test_without_litellm_a_turn_says_how_to_install_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(LOCAL_MAP, "True")
    monkeypatch.setitem(sys.modules, "litellm", None)
    with pytest.raises(ModuleNotFoundError, match="uv sync --extra litellm"):
        _agent(tmp_path).new(tmp_path)("hi")


def _finding(account: Provider) -> Callable[[str, str], Provider]:
    """`hmz.coganchor.providers.find`, for a machine holding that one account."""

    def find(cli: str, name: str) -> Provider:
        del cli, name
        return account

    return find


@pytest.mark.parametrize(
    ("way", "env", "model", "expected", "sent"),
    [
        (
            "openai-key",
            {"OPENAI_API_KEY": "k1"},
            "openai/m",
            {"api_key": "k1"},
            "openai/m",
        ),
        (
            "gateway",
            {
                "LITELLM_GATEWAY_URL": "http://gw",
                "LITELLM_GATEWAY_KEY": "k2",
                "LITELLM_GATEWAY_API": "openai",
            },
            "m",
            {"api_base": "http://gw", "api_key": "k2"},
            "openai/m",
        ),
        (
            "bedrock",
            {"AWS_PROFILE": "p", "AWS_REGION_NAME": "r"},
            "bedrock/m",
            {"aws_profile_name": "p", "aws_region_name": "r"},
            "bedrock/m",
        ),
    ],
)
def test_an_account_is_passed_on_the_call(
    litellm: _LiteLLM,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    way: str,
    env: dict[str, str],
    model: str,
    expected: dict[str, str],
    sent: str,
) -> None:
    account = Provider(cli="litellm", name="acct", way=way, env=env)
    monkeypatch.setattr(providers, "find", _finding(account))
    _agent(tmp_path, model=model, provider="acct").new(tmp_path)("hi")
    call = litellm.calls[0]
    assert call["model"] == sent
    assert {key: call[key] for key in expected} == expected


def test_an_account_made_some_other_way_is_refused(
    litellm: _LiteLLM, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    account = Provider(cli="litellm", name="acct", way="oauth", env={})
    monkeypatch.setattr(providers, "find", _finding(account))
    with pytest.raises(Failed, match="litellm does not offer"):
        _agent(tmp_path, provider="acct").new(tmp_path)("hi")
    assert litellm.calls == []


def test_a_fork_starts_from_the_conversation_it_was_cut_from(
    litellm: _LiteLLM, tmp_path: Path
) -> None:
    agent = _agent(tmp_path)
    parent = agent.new(tmp_path)
    parent("one")
    child = parent.fork()
    litellm.chunks = _answer("forked")
    assert child("two") == "forked"
    assert child.id != parent.id
    assert litellm.calls[-1]["messages"][:2] == [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "Hello there"},
    ]
    assert _kept(agent, child)[0]["parent"] == parent.id


def test_it_fences_nothing_from_outside(tmp_path: Path) -> None:
    rest = _agent(tmp_path).natively(Fence(read=("/x",), write=(), online=False))
    assert rest.open

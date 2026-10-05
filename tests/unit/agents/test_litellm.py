"""litellm as a harness: one chat completion a turn, over a history humanize keeps itself.

Driven here against a stand-in for litellm's `completion`, which records what it was asked
and streams back what the test said -- so each test is about what the driver sends and what
it makes of the answer, and nothing reaches a network. `tests/integration/agents` drives the
real litellm against the loopback endpoint.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel

from hmz.coganchor import backends, providers
from hmz.coganchor.agents import (
    DRIVEN,
    Failed,
    LiteLLMAgent,
    LiteLLMAgentConfig,
    SessionBase,
    Unrecoverable,
)
from hmz.coganchor.agents import litellm as driven

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


class Completions:
    """What stands in for litellm: every call it took, and what each one answers."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.says: list[str] = []
        self.thinks = ""
        self.usage: dict[str, Any] = {"prompt_tokens": 10, "completion_tokens": 3}
        self.raises: Exception | None = None
        self.holds = True

    def supports_response_schema(self, model: str) -> bool:
        del model
        return self.holds

    def completion(self, **kwargs: object) -> Iterator[object]:
        self.calls.append(dict(kwargs))
        if self.raises is not None:
            raise self.raises
        said = self.says.pop(0) if self.says else "ok"
        chunks: list[dict[str, Any]] = [
            {"choices": [{"delta": {"role": "assistant"}}]},
            *(
                [{"choices": [{"delta": {"reasoning_content": self.thinks}}]}]
                if self.thinks
                else []
            ),
            {"choices": [{"delta": {"content": said[:2]}}]},
            {"choices": [{"delta": {"content": said[2:]}}]},
            {"choices": [], "usage": self.usage},
        ]
        return iter(chunks)


@pytest.fixture
def completions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Completions:
    # The unit suite keeps every session where its CLI would, which for litellm is under the
    # home: one of this test's own.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    held = Completions()
    monkeypatch.setattr(driven, "_litellm", lambda: held)
    return held


def _agent(tmp_path: Path, model: str = "openai/gpt-5", **said: Any) -> LiteLLMAgent:
    agent = LiteLLMAgent(LiteLLMAgentConfig(model=model, effort="", **said))
    agent.keeps = tmp_path
    agent.watch(_unheard)
    return agent


def _unheard(*_: object) -> None:
    """Watches a turn, so that nothing it says is put on this process's own streams."""


def _rows(agent: LiteLLMAgent, session: SessionBase) -> list[dict[str, Any]]:
    kept = agent.kept()
    assert kept is not None
    path = kept / "sessions" / f"{session.id}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_it_is_driven_as_litellm() -> None:
    assert DRIVEN["litellm"] == (LiteLLMAgent, LiteLLMAgentConfig)
    profile = backends.named("litellm")
    assert profile is not None
    assert profile.forks
    assert profile.told


def test_an_agent_spec_keeps_the_slashes_of_a_litellm_model() -> None:
    role, profile, model, effort, provider = backends.read(
        "r=litellm@acct/openai/gpt-5:high"
    )
    assert (role, profile.name, model, effort, provider) == (
        "r",
        "litellm",
        "openai/gpt-5",
        "high",
        "acct",
    )


def test_a_turn_streams_the_answer_and_counts_what_it_spent(
    tmp_path: Path, completions: Completions
) -> None:
    completions.says = ["hello there"]
    completions.thinks = "hmm"
    completions.usage = {
        "prompt_tokens": 10,
        "completion_tokens": 3,
        "prompt_tokens_details": {"cached_tokens": 4},
    }
    agent = _agent(tmp_path)
    session = agent.new()

    events = list(session.stream("hi"))

    assert [event.kind for event in events] == ["reasoning", "text", "result"]
    result = next(event for event in events if event.kind == "result")
    assert result.text == "hello there"
    assert result.tokens == {"openai/gpt-5": 13}
    assert dict(session.spent()) == {"input": 6, "output": 3, "cache_read": 4}
    (call,) = completions.calls
    assert call["model"] == "openai/gpt-5"
    assert call["messages"] == [{"role": "user", "content": "hi"}]
    assert call["stream"] is True
    assert call["stream_options"] == {"include_usage": True}
    assert "reasoning_effort" not in call
    assert agent.opened == [session.id]


def test_every_turn_after_the_first_is_sent_the_conversation_so_far(
    tmp_path: Path, completions: Completions
) -> None:
    completions.says = ["one", "two"]
    agent = _agent(tmp_path)
    session = agent.new()

    assert session("first") == "one"
    assert session("second") == "two"

    assert completions.calls[1]["messages"] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "one"},
        {"role": "user", "content": "second"},
    ]
    rows = _rows(agent, session)
    assert rows[0]["type"] == "session"
    assert [row["message"]["role"] for row in rows[1:]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert rows[2]["message"]["usage"] == {"input": 10, "output": 3}


def test_a_new_session_of_the_same_id_resumes_from_the_file(
    tmp_path: Path, completions: Completions
) -> None:
    agent = _agent(tmp_path)
    session = agent.new()
    session("first")

    again = agent.new()
    again._id = session.id
    again("second")

    assert completions.calls[1]["messages"][:2] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "ok"},
    ]


def test_a_fork_carries_the_history_and_goes_its_own_way(
    tmp_path: Path, completions: Completions
) -> None:
    completions.says = ["one", "left", "right"]
    agent = _agent(tmp_path)
    parent = agent.new()
    parent("first")
    child = parent.fork(cwd=tmp_path)

    assert child("go left") == "left"
    assert child.id != parent.id
    assert parent("go right") == "right"

    assert completions.calls[1]["messages"] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "one"},
        {"role": "user", "content": "go left"},
    ]
    assert completions.calls[2]["messages"][-1] == {
        "role": "user",
        "content": "go right",
    }
    assert len(completions.calls[2]["messages"]) == 3
    assert _rows(agent, child)[0]["parent"] == parent.id


class Verdict(BaseModel):
    ok: bool
    why: str


def test_a_shape_is_sent_as_the_response_format(
    tmp_path: Path, completions: Completions
) -> None:
    completions.says = ['{"ok": true, "why": "fine"}']
    session = _agent(tmp_path).new()

    assert session("judge it", schema=Verdict) == Verdict(ok=True, why="fine")

    (call,) = completions.calls
    assert call["messages"][-1]["content"] == "judge it"
    assert call["response_format"]["type"] == "json_schema"
    assert call["response_format"]["json_schema"]["name"] == "Verdict"


def test_a_model_that_may_not_hold_a_shape_is_asked_for_it_as_well(
    tmp_path: Path, completions: Completions
) -> None:
    completions.says = ['{"ok": false, "why": "no"}']
    completions.holds = False
    agent = _agent(tmp_path)
    session = agent.new()

    assert session("judge it", schema=Verdict) == Verdict(ok=False, why="no")

    (call,) = completions.calls
    assert call["messages"][-1]["content"].startswith("judge it")
    assert '"why"' in call["messages"][-1]["content"]
    assert "response_format" in call
    # And what the conversation keeps is the prompt as the flow wrote it.
    assert _rows(agent, session)[1]["message"]["content"] == "judge it"


def test_an_effort_is_the_reasoning_effort(
    tmp_path: Path, completions: Completions
) -> None:
    session = _agent(tmp_path).new()
    session.effort = "low"
    session("hi")
    assert completions.calls[0]["reasoning_effort"] == "low"


@pytest.mark.parametrize(
    ("way", "env", "passed"),
    [
        ("openai-key", {"OPENAI_API_KEY": "sk-o"}, {"api_key": "sk-o"}),
        ("anthropic-key", {"ANTHROPIC_API_KEY": "sk-a"}, {"api_key": "sk-a"}),
        (
            "bedrock",
            {"AWS_PROFILE": "work", "AWS_REGION_NAME": "eu-west-1"},
            {"aws_profile_name": "work", "aws_region_name": "eu-west-1"},
        ),
        (
            "vertex",
            {"VERTEXAI_PROJECT": "p", "VERTEXAI_LOCATION": "us-central1"},
            {"vertex_project": "p", "vertex_location": "us-central1"},
        ),
        (
            "azure",
            {
                "AZURE_API_BASE": "https://r.openai.azure.com",
                "AZURE_API_KEY": "k",
                "AZURE_API_VERSION": "2024-10-21",
            },
            {
                "api_base": "https://r.openai.azure.com",
                "api_key": "k",
                "api_version": "2024-10-21",
            },
        ),
    ],
)
def test_an_account_is_passed_on_the_call(
    tmp_path: Path,
    completions: Completions,
    way: str,
    env: dict[str, str],
    passed: dict[str, str],
) -> None:
    providers.add("litellm", "acct", way, env)
    _agent(tmp_path, provider="acct").new()("hi")
    (call,) = completions.calls
    assert {name: call[name] for name in passed} == passed


@pytest.mark.parametrize(
    ("way", "model", "sent"),
    [
        ("openai-gateway", "served-model", "openai/served-model"),
        ("openai-gateway", "openai/served-model", "openai/served-model"),
        ("anthropic-gateway", "claude-x", "anthropic/claude-x"),
    ],
)
def test_a_gateway_is_its_url_its_key_and_its_protocol(
    tmp_path: Path, completions: Completions, way: str, model: str, sent: str
) -> None:
    profile = backends.named("litellm")
    assert profile is not None
    sets = dict(next(one for one in profile.ways if one.name == way).sets)
    providers.add(
        "litellm",
        "gw",
        way,
        {"LITELLM_GATEWAY_URL": "http://gw", "LITELLM_GATEWAY_KEY": "k", **sets},
    )
    _agent(tmp_path, model=model, provider="gw").new()("hi")
    (call,) = completions.calls
    assert (call["model"], call["api_base"], call["api_key"]) == (
        sent,
        "http://gw",
        "k",
    )


def test_an_account_made_some_other_way_is_refused(
    tmp_path: Path, completions: Completions
) -> None:
    providers.add("litellm", "odd", "env", {"OPENAI_API_KEY": "sk"})
    with pytest.raises(Failed, match="litellm does not offer"):
        _agent(tmp_path, provider="odd").new()("hi")
    assert not completions.calls


def test_a_failed_call_is_a_failed_turn_and_opens_nothing(
    tmp_path: Path, completions: Completions
) -> None:
    completions.raises = ConnectionError("refused")
    session = _agent(tmp_path).new()
    with pytest.raises(Failed, match="refused"):
        session("hi")
    assert session.named is None


def test_a_conversation_too_long_for_the_model_is_unrecoverable(
    tmp_path: Path, completions: Completions
) -> None:
    class ContextWindowExceededError(Exception):
        pass

    completions.raises = ContextWindowExceededError("too long")
    with pytest.raises(Unrecoverable):
        _agent(tmp_path).new()("hi")


def test_a_missing_extra_says_how_to_install_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    real = importlib.import_module

    def without(name: str, package: str | None = None) -> object:
        if name == "litellm":
            raise ModuleNotFoundError(name=name)
        return real(name, package)

    monkeypatch.setattr(importlib, "import_module", without)
    with pytest.raises(ModuleNotFoundError, match=r"\[litellm\] extra"):
        _agent(tmp_path).new()("hi")


def test_nothing_is_put_around_a_turn_that_runs_nothing() -> None:
    from hmz.coganchor.fence import Fence

    fence = Fence(read=("/",), write=(), online=False)
    agent = LiteLLMAgent(LiteLLMAgentConfig(model="openai/gpt-5", effort=""))
    assert agent.natively(fence).open


def test_its_conversations_are_read_by_the_trace_and_the_tally(
    tmp_path: Path, completions: Completions
) -> None:
    from hmz.runtime.tracing.readers import litellm as reader
    from hmz.tui import tally

    completions.says = ["one", "two"]
    agent = _agent(tmp_path)
    session = agent.new(tmp_path)
    session("first")
    session("second")
    kept = agent.kept()
    assert kept is not None

    (traced,) = reader.collect(kept, None, None, (0.0, float("inf")))
    assert traced.key == f"litellm:{session.id}"
    assert [one.category for one in traced.actions].count("turn") == 2
    said = [one.args.get("text") for one in traced.actions if one.category == "message"]
    assert said == ["one", "two"]
    rows = _rows(agent, session)
    model, tokens, kinds, _ = tally._spent("litellm", rows[2])
    assert (model, tokens, kinds) == ("openai/gpt-5", 13, {"input": 10, "output": 3})
    assert tally._spent("litellm", rows[1])[1] == 0


def test_it_offers_no_env_way_and_is_never_the_implicit_choice(tmp_path: Path) -> None:
    from hmz.tui import discover

    assert "env" not in {one.name for one in providers.ways("litellm")}
    assert not discover.ready_to_open("litellm", tmp_path)


def test_its_catalogue_is_litellm_s_own_chat_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib
    from types import SimpleNamespace

    from hmz.coganchor import models

    listed = {
        "gpt-5": {
            "litellm_provider": "openai",
            "mode": "chat",
            "supports_reasoning": True,
        },
        "groq/llama": {"litellm_provider": "groq", "mode": "chat"},
        "gemini-pro": {
            "litellm_provider": "vertex_ai-language-models",
            "mode": "chat",
        },
        "text-embedding-3": {"litellm_provider": "openai", "mode": "embedding"},
        "somebody/else": {"litellm_provider": "nobody", "mode": "chat"},
    }
    real = importlib.import_module

    def faked(name: str, package: str | None = None) -> object:
        return (
            SimpleNamespace(model_cost=listed)
            if name == "litellm"
            else real(name, package)
        )

    monkeypatch.setattr(importlib, "import_module", faked)
    profile = backends.named("litellm")
    assert profile is not None
    found = models._READING["litellm"](profile, lambda *_: "")
    assert [(one.name, bool(one.efforts)) for one in found] == [
        ("openai/gpt-5", True),
        ("groq/llama", False),
        ("vertex_ai/gemini-pro", False),
    ]

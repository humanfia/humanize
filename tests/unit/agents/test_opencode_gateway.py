"""opencode's ways in: a vendor's key, somebody's gateway by protocol, and the clouds.

A gateway account is a provider of opencode's own config, handed in `OPENCODE_CONFIG_CONTENT`
with `{env:VAR}` where each answer goes. opencode substitutes those on the text before it
parses it, which is done here the way it does it, so what is checked is the config opencode
would read. The driver then names the turn's model under that provider, and lists it there.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends
from hmz.coganchor.providers.login import way_of
from hmz.coganchor.agents import OpencodeAgent, OpencodeAgentConfig

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

#: What a gateway account is answered with, and what each protocol is spoken in.
ANSWERS = {
    "OPENCODE_GATEWAY_URL": "https://gw.example/v1",
    "OPENCODE_GATEWAY_KEY": "not-a-real-key",
    "OPENCODE_GATEWAY_MODEL": "m-one",
}
SPOKEN = {
    "openai-gateway": "@ai-sdk/openai-compatible",
    "anthropic-gateway": "@ai-sdk/anthropic",
    "gemini-gateway": "@ai-sdk/google",
}


def _profile() -> backends.Profile:
    profile = backends.named("opencode")
    assert profile is not None
    return profile


def _way(name: str) -> backends.Way:
    way = way_of("opencode", name)
    assert way is not None, name
    return way


def _read(said: str, environ: Mapping[str, str]) -> dict[str, object]:
    """The config opencode reads out of `said`: `{env:VAR}` first, on the text, then JSON."""
    return json.loads(
        re.sub(r"\{env:([^}]+)\}", lambda one: environ.get(one[1], ""), said)
    )


def test_opencode_offers_a_way_per_vendor_protocol_and_cloud() -> None:
    assert [way.name for way in _profile().ways] == [
        "login",
        "wellknown",
        "zen",
        "anthropic-key",
        "openai-key",
        "gemini-key",
        "xai-key",
        "openrouter-key",
        "deepseek-key",
        "mistral-key",
        "openai-gateway",
        "anthropic-gateway",
        "gemini-gateway",
        "bedrock",
        "vertex",
        "azure",
    ]


@pytest.mark.parametrize(
    ("way", "variable"),
    [
        ("anthropic-key", "ANTHROPIC_API_KEY"),
        ("openai-key", "OPENAI_API_KEY"),
        # The one of Google's three names its SDK reads itself: opencode hands it no key for
        # a provider it knows by more than one, so `GEMINI_API_KEY` alone reaches nothing.
        ("gemini-key", "GOOGLE_GENERATIVE_AI_API_KEY"),
        ("xai-key", "XAI_API_KEY"),
        ("openrouter-key", "OPENROUTER_API_KEY"),
        ("deepseek-key", "DEEPSEEK_API_KEY"),
        ("mistral-key", "MISTRAL_API_KEY"),
    ],
)
def test_a_vendor_key_is_asked_for_under_the_name_opencode_reads(
    way: str, variable: str
) -> None:
    (asked,) = _way(way).asks
    assert (asked.env, asked.secret) == (variable, True)


@pytest.mark.parametrize("way", list(SPOKEN))
def test_every_gateway_asks_where_then_the_key_then_the_model(way: str) -> None:
    asks = _way(way).asks
    assert [one.env for one in asks[:3]] == list(ANSWERS)
    assert [one.secret for one in asks[:3]] == [False, True, False]
    # The one URL every gateway way shares is the endpoint its catalogue is asked at.
    assert _profile().endpoint == asks[0].env


@pytest.mark.parametrize(("way", "npm"), list(SPOKEN.items()))
def test_a_gateway_is_a_provider_of_opencodes_config_speaking_its_protocol(
    way: str, npm: str
) -> None:
    held = _way(way)
    answered = {**{one.env: one.fixed for one in held.asks if one.fixed}, **ANSWERS}
    ((variable, said),) = held.sets

    assert variable == "OPENCODE_CONFIG_CONTENT"
    assert ANSWERS["OPENCODE_GATEWAY_KEY"] not in said
    assert _read(said, answered) == {
        "provider": {
            "gateway": {
                "npm": npm,
                "options": {
                    "baseURL": "https://gw.example/v1",
                    "apiKey": "not-a-real-key",
                },
                "models": {"m-one": {}},
            }
        }
    }


def test_openais_gateway_speaks_responses_where_it_is_told_to() -> None:
    held = _way("openai-gateway")
    (said,) = (value for _, value in held.sets)
    read = _read(said, {**ANSWERS, "OPENCODE_GATEWAY_NPM": "@ai-sdk/openai"})

    assert read["provider"]["gateway"]["npm"] == "@ai-sdk/openai"  # pyright: ignore[reportIndexIssue]


def _turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model: str, account: dict[str, str]
) -> tuple[list[str], dict[str, str]]:
    agent = OpencodeAgent(OpencodeAgentConfig(model=model, effort=""))
    monkeypatch.setattr(agent, "environment", lambda: account)
    session = agent.new(tmp_path)
    argv, _ = session._turn("hi")
    return argv, dict(session._environment())


@pytest.mark.parametrize("model", ["m-two", "gateway/m-two"])
def test_a_gateway_turn_runs_at_the_model_it_names_under_that_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model: str
) -> None:
    """Named bare, as the endpoint lists it, or as `opencode models` does -- never doubled."""
    argv, environment = _turn(tmp_path, monkeypatch, model, dict(ANSWERS))

    assert argv[argv.index("--model") + 1] == "gateway/m-two"
    assert environment["OPENCODE_GATEWAY_MODEL"] == "m-two"


def test_any_other_accounts_turn_names_its_model_as_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv, environment = _turn(
        tmp_path, monkeypatch, "anthropic/claude-x", {"ANTHROPIC_API_KEY": "k"}
    )

    assert argv[argv.index("--model") + 1] == "anthropic/claude-x"
    assert "OPENCODE_GATEWAY_MODEL" not in environment


def test_the_clouds_names_that_outrank_the_ways_own_are_hushed() -> None:
    hushed = _profile().hushes()
    assert {
        "AWS_BEARER_TOKEN_BEDROCK",
        "GOOGLE_VERTEX_PROJECT",
        "GOOGLE_VERTEX_LOCATION",
    } <= hushed


def test_a_gateway_accounts_host_is_reachable_behind_a_fence() -> None:
    assert "gw.example" in backends.reachable(_profile(), ANSWERS)


def test_every_vendor_a_key_is_asked_for_is_reachable_behind_a_fence() -> None:
    assert {
        "api.anthropic.com",
        "api.openai.com",
        "generativelanguage.googleapis.com",
        "api.x.ai",
        "openrouter.ai",
        "api.deepseek.com",
        "api.mistral.ai",
    } <= set(_profile().hosts)

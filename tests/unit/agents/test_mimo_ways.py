"""mimocode's ways in: a vendor's key, somebody's endpoint, a cloud, and the turn each makes.

A gateway is a provider of mimocode's own configuration, held in the variable it reads one
from and naming the answers rather than holding them -- so what is checked here is what a way
writes down, and that a turn under such an account names its model the way mimocode lists it.
Whether mimocode then reaches the endpoint on the protocol asked for is a real CLI's to show,
and was shown against 0.1.15 when these ways were written.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends, providers
from hmz.coganchor.agents import MimoCodeAgent, MimoCodeAgentConfig
from hmz.coganchor.providers import login
from tests import logins
from tests.logins import way

if TYPE_CHECKING:
    from pathlib import Path

_GATEWAYS = {
    "openai-gateway": "@ai-sdk/openai-compatible",
    "anthropic-gateway": "@ai-sdk/anthropic",
    "gemini-gateway": "@ai-sdk/google",
}


@pytest.fixture
def house(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This user's home, somewhere temporary: nothing here may read or write the real one."""
    return logins.house(tmp_path, monkeypatch)


def _mimo() -> backends.Profile:
    profile = backends.named("mimo")
    assert profile is not None
    return profile


def test_the_ways_in_are_a_login_the_vendors_keys_the_gateways_and_the_clouds() -> None:
    assert [one.name for one in _mimo().ways] == [
        "login",
        "key",
        "anthropic-key",
        "openai-key",
        "gemini-key",
        "xai-key",
        "openrouter-key",
        "deepseek-key",
        "openai-gateway",
        "anthropic-gateway",
        "gemini-gateway",
        "vertex",
        "bedrock",
        "azure",
    ]


@pytest.mark.parametrize("name", list(_GATEWAYS))
def test_every_gateway_asks_where_it_is_first_and_that_is_the_endpoint(
    name: str,
) -> None:
    gateway = way("mimo", name)

    assert [one.env for one in gateway.asks][:3] == [
        "MIMO_GATEWAY_URL",
        "MIMO_GATEWAY_KEY",
        "MIMO_GATEWAY_MODEL",
    ]
    assert _mimo().endpoint == "MIMO_GATEWAY_URL"
    # Nothing secret on a command line: the key is a variable the configuration names.
    assert not gateway.args
    assert [one.env for one in gateway.asks if one.secret] == ["MIMO_GATEWAY_KEY"]


@pytest.mark.parametrize(("name", "adapter"), list(_GATEWAYS.items()))
def test_a_gateway_is_a_provider_of_mimocodes_own_naming_the_answers(
    name: str, adapter: str, house: Path
) -> None:
    provider = login.make(
        "mimo",
        "mine",
        way("mimo", name),
        {
            "MIMO_GATEWAY_URL": "https://gateway.invalid/v1",
            "MIMO_GATEWAY_KEY": "not-a-real-key",
            "MIMO_GATEWAY_MODEL": "some-model",
        },
    )

    env = dict(provider.env)
    assert env["MIMO_GATEWAY_API"] == adapter
    said = json.loads(env["MIMOCODE_CONFIG_CONTENT"])["provider"]["humanize"]
    assert said == {
        "npm": "{env:MIMO_GATEWAY_API}",
        "options": {
            "baseURL": "{env:MIMO_GATEWAY_URL}",
            "apiKey": "{env:MIMO_GATEWAY_KEY}",
        },
        "models": {"{env:MIMO_GATEWAY_MODEL}": {}},
    }
    assert "not-a-real-key" not in env["MIMOCODE_CONFIG_CONTENT"]


def test_the_openai_gateway_is_asked_which_of_its_apis_and_says_chat_unasked() -> None:
    gateway = way("mimo", "openai-gateway")

    assert login.asked(gateway, {}) == [
        "MIMO_GATEWAY_URL",
        "MIMO_GATEWAY_KEY",
        "MIMO_GATEWAY_MODEL",
    ]
    assert gateway.asks[-1].env == "MIMO_GATEWAY_API"
    assert gateway.asks[-1].fixed == "@ai-sdk/openai-compatible"
    assert "@ai-sdk/openai for Responses" in gateway.asks[-1].about


@pytest.mark.parametrize(
    ("name", "env"),
    [
        ("anthropic-key", "ANTHROPIC_API_KEY"),
        ("openai-key", "OPENAI_API_KEY"),
        ("gemini-key", "GOOGLE_GENERATIVE_AI_API_KEY"),
        ("xai-key", "XAI_API_KEY"),
        ("openrouter-key", "OPENROUTER_API_KEY"),
        ("deepseek-key", "DEEPSEEK_API_KEY"),
    ],
)
def test_a_vendors_key_is_kept_under_the_name_mimocode_reads_it_by(
    name: str, env: str, house: Path
) -> None:
    provider = login.make("mimo", "mine", way("mimo", name), {env: "not-a-real-key"})

    assert dict(provider.env) == {env: "not-a-real-key"}
    # And every other vendor's is one a turn of it runs without.
    assert {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY"} <= _mimo().accounts()


def test_a_cloud_is_asked_only_what_has_no_usual_answer(house: Path) -> None:
    assert login.asked(way("mimo", "vertex"), {}) == ["GOOGLE_CLOUD_PROJECT"]
    assert login.asked(way("mimo", "bedrock"), {}) == ["AWS_PROFILE"]
    assert login.asked(way("mimo", "azure"), {}) == [
        "AZURE_RESOURCE_NAME",
        "AZURE_API_KEY",
    ]
    provider = login.make(
        "mimo", "mine", way("mimo", "vertex"), {"GOOGLE_CLOUD_PROJECT": "p"}
    )
    assert dict(provider.env) == {
        "GOOGLE_CLOUD_PROJECT": "p",
        "GOOGLE_VERTEX_LOCATION": "us-central1",
    }


def _gateway(house: Path) -> None:
    login.make(
        "mimo",
        "gw",
        way("mimo", "openai-gateway"),
        {
            "MIMO_GATEWAY_URL": "https://gateway.invalid/v1",
            "MIMO_GATEWAY_KEY": "not-a-real-key",
            "MIMO_GATEWAY_MODEL": "made-with",
        },
    )


@pytest.mark.parametrize("model", ["vendor/served", "humanize/vendor/served"])
def test_a_gateway_turn_names_its_model_as_the_provider_it_configured_lists_it(
    model: str, house: Path
) -> None:
    _gateway(house)
    session = MimoCodeAgent(
        MimoCodeAgentConfig(model=model, effort="low", provider="gw")
    ).new()

    argv, _ = session._turn("hello")
    environment = session._environment()

    assert argv[argv.index("--model") + 1] == "humanize/vendor/served"
    # The model the account was made with is not the only one a turn may name: whichever one
    # this turn is of is the one the configuration lists.
    assert environment["MIMO_GATEWAY_MODEL"] == "vendor/served"
    assert environment["MIMOCODE_CONFIG_CONTENT"].startswith('{"provider"')


def test_a_turn_under_any_other_account_names_its_model_as_it_was_given(
    house: Path,
) -> None:
    providers.add("mimo", "keyed", way="key", env={"XIAOMI_API_KEY": "nope"})
    session = MimoCodeAgent(
        MimoCodeAgentConfig(model="xiaomi/mimo-v2.5", effort="low", provider="keyed")
    ).new()

    argv, _ = session._turn("hello")

    assert argv[argv.index("--model") + 1] == "xiaomi/mimo-v2.5"
    assert "MIMO_GATEWAY_MODEL" not in session._environment()

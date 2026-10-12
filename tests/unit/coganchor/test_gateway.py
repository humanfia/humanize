from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends, gateway
from hmz.coganchor.gateway import (
    NEEDS,
    argued,
    configured,
    credentials,
    gatewayable,
    prefix,
    spelled,
    spoken,
)
from hmz.coganchor.providers import Provider

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec


def _claude() -> backends.Profile:
    found = backends.named("claude")
    assert found is not None
    return found


GATEWAY = {
    "LITELLM_GATEWAY_URL": "https://gw.example/v1",
    "LITELLM_GATEWAY_KEY": "upstream-key",
    "LITELLM_GATEWAY_API": "openai",
}


@pytest.mark.parametrize(
    ("way", "env", "expected"),
    [
        ("openai-key", {"OPENAI_API_KEY": "k"}, "openai"),
        ("mistral-key", {"MISTRAL_API_KEY": "k"}, "mistral"),
        ("openai-gateway", GATEWAY, "openai"),
        ("bedrock", {"AWS_PROFILE": "p"}, "bedrock"),
        ("vertex", {"VERTEXAI_PROJECT": "p"}, "vertex_ai"),
        ("azure", {"AZURE_API_KEY": "k"}, "azure"),
        ("oauth", {}, ""),
    ],
)
def test_an_account_says_which_provider_litellm_sends_it_to(
    way: str, env: dict[str, str], expected: str
) -> None:
    assert prefix(Provider(cli="litellm", name="a", way=way, env=env)) == expected
    # The same account, through a gateway in front of another backend.
    routed = Provider(cli="claude", name="a", way=f"litellm-{way}", env=env)
    assert prefix(routed) == expected


def test_no_account_is_sent_to_no_provider_in_particular() -> None:
    assert prefix(None) == ""
    assert spelled("openai/gpt-5", None) == "openai/gpt-5"


@pytest.mark.parametrize(
    ("model", "expected"),
    [("gpt-5", "openai/gpt-5"), ("openai/gpt-5", "openai/gpt-5")],
)
def test_a_bare_id_is_the_accounts_providers(model: str, expected: str) -> None:
    account = Provider(cli="litellm", name="a", way="openai-key", env={})
    assert spelled(model, account) == expected


@pytest.mark.parametrize(
    ("way", "env", "expected"),
    [
        ("openai-key", {"OPENAI_API_KEY": "k1"}, {"api_key": "k1"}),
        (
            "openai-gateway",
            GATEWAY,
            {"api_base": "https://gw.example/v1", "api_key": "upstream-key"},
        ),
        (
            "bedrock",
            {"AWS_PROFILE": "p", "AWS_REGION_NAME": "r"},
            {"aws_profile_name": "p", "aws_region_name": "r"},
        ),
        (
            "vertex",
            {"VERTEXAI_PROJECT": "p", "VERTEXAI_LOCATION": "l"},
            {"vertex_project": "p", "vertex_location": "l"},
        ),
        (
            "azure",
            {"AZURE_API_BASE": "b", "AZURE_API_KEY": "k", "AZURE_API_VERSION": "v"},
            {"api_base": "b", "api_key": "k", "api_version": "v"},
        ),
    ],
)
def test_an_account_is_litellms_own_parameters(
    way: str, env: dict[str, str], expected: dict[str, str]
) -> None:
    for account in (
        Provider(cli="litellm", name="a", way=way, env=env),
        Provider(cli="claude", name="a", way=f"litellm-{way}", env=env),
    ):
        assert credentials(account) == expected


def test_an_account_litellm_does_not_offer_is_refused() -> None:
    with pytest.raises(ValueError, match="litellm does not offer"):
        credentials(Provider(cli="litellm", name="a", way="oauth"))
    assert credentials(None) == {}


def test_a_gateway_serves_every_model_of_the_account_under_its_key_alone() -> None:
    account = Provider(
        cli="claude", name="a", way="litellm-openai-gateway", env=GATEWAY
    )

    said = configured(account, "sk-master")

    params = {
        "model": "openai/*",
        "api_base": "https://gw.example/v1",
        "api_key": "upstream-key",
        "use_chat_completions_api": True,
    }
    assert said["model_list"] == [
        {"model_name": "openai/*", "litellm_params": params},
        {"model_name": "*", "litellm_params": params},
    ]
    assert said["general_settings"] == {"master_key": "sk-master"}
    assert said["litellm_settings"]["drop_params"] is True
    assert said["litellm_settings"]["use_chat_completions_url_for_anthropic_messages"]


def test_a_gateway_asks_a_vendor_in_whichever_protocol_it_speaks() -> None:
    account = Provider(
        cli="codex", name="a", way="litellm-openai-key", env={"OPENAI_API_KEY": "k"}
    )

    said = configured(account, "sk-master")

    assert "use_chat_completions_api" not in said["model_list"][0]["litellm_params"]


def test_a_gateway_for_an_account_naming_no_provider_is_refused() -> None:
    account = Provider(cli="claude", name="a", way="litellm-oauth", env={})
    with pytest.raises(ValueError, match="names no provider"):
        configured(account, "sk-master")


def test_claude_is_pointed_at_a_gateway_by_its_own_gateway_way() -> None:
    env = spoken(_claude(), "http://127.0.0.1:4000", "sk-master")

    assert env == {
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:4000",
        "ANTHROPIC_AUTH_TOKEN": "sk-master",
    }
    assert argued(_claude(), env) == ()


@pytest.mark.parametrize(
    ("cli", "expected", "args"),
    [
        (
            "dsh",
            {
                "DEEPSEEK_BASE_URL": "http://127.0.0.1:4000",
                "DEEPSEEK_API_KEY": "sk-master",
                "DSH_GATEWAY_API": "openai-completions",
            },
            (),
        ),
        (
            "kimi",
            {
                "KIMI_MODEL_BASE_URL": "http://127.0.0.1:4000",
                "KIMI_MODEL_API_KEY": "sk-master",
                "KIMI_MODEL_PROVIDER_TYPE": "openai",
            },
            (),
        ),
        (
            "qwen",
            {
                "OPENAI_BASE_URL": "http://127.0.0.1:4000",
                "OPENAI_API_KEY": "sk-master",
                "QWEN_DEFAULT_AUTH_TYPE": "openai",
            },
            ("--auth-type", "openai"),
        ),
    ],
)
def test_a_cli_speaking_openais_api_is_pointed_at_a_gateway_by_its_openai_way(
    cli: str, expected: dict[str, str], args: tuple[str, ...]
) -> None:
    profile = backends.named(cli)
    assert profile is not None

    env = spoken(profile, "http://127.0.0.1:4000", "sk-master")

    assert env == expected
    assert argued(profile, env) == args


@pytest.mark.parametrize(
    ("backend", "fixed"),
    [
        ("opencode", {"OPENCODE_GATEWAY_NPM": "@ai-sdk/openai-compatible"}),
        ("mimo", {"MIMO_GATEWAY_API": "@ai-sdk/openai-compatible"}),
        ("pi", {"PI_GATEWAY_API": "openai-completions"}),
    ],
)
def test_a_cli_speaking_openais_api_is_pointed_at_the_gateways_v1(
    backend: str, fixed: dict[str, str]
) -> None:
    profile = backends.named(backend)
    assert profile is not None
    assert profile.routes == "openai-gateway"

    env = spoken(profile, "http://127.0.0.1:4000", "sk-master")

    assert env[profile.endpoint] == "http://127.0.0.1:4000/v1"
    assert "sk-master" in env.values()
    assert fixed.items() <= env.items()
    # The model is the turn's, which the driver says: nothing here names one.
    assert not any(name.endswith("_MODEL") for name in env)


def test_another_cli_speaking_openais_api_is_given_the_bare_gateway() -> None:
    # One that adds `/v1/chat/completions` itself, as Antigravity's does, is not given `/v1`
    # twice: the version is added only for the backends whose SDKs leave it out.
    agy = backends.named("agy")
    assert agy is not None

    env = spoken(agy, "http://127.0.0.1:4000", "sk-master")

    assert env["AGY_LLM_GATEWAY_URL"] == "http://127.0.0.1:4000"


def test_codex_is_pointed_at_a_gateway_by_its_own_gateway_way() -> None:
    codex = backends.named("codex")
    assert codex is not None

    env = spoken(codex, "http://127.0.0.1:4000", "sk-master")

    # No `/v1` after it: codex asks `{base_url}/responses`, which the gateway serves too.
    assert env == {
        "CODEX_PROVIDER_URL": "http://127.0.0.1:4000",
        "CODEX_PROVIDER_KEY": "sk-master",
    }
    said = argued(codex, env)
    assert "model_providers.humanize.base_url=http://127.0.0.1:4000" in said
    assert "model_providers.humanize.env_key=CODEX_PROVIDER_KEY" in said
    assert "model_providers.humanize.wire_api=responses" in said
    assert "sk-master" not in " ".join(said)


def test_a_backend_naming_no_way_to_a_gateway_is_pointed_nowhere() -> None:
    omp = backends.named("omp")
    assert omp is not None
    assert spoken(omp, "http://127.0.0.1:4000", "sk") == {}
    assert argued(omp, {}) == ()


@pytest.mark.parametrize("missing", NEEDS)
def test_a_gateway_needs_every_module_of_the_extra(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    def find_spec(name: str) -> ModuleSpec | None:
        return None if name == missing else importlib.util.spec_from_loader(name, None)

    monkeypatch.setattr(gateway.importlib.util, "find_spec", find_spec)
    assert gatewayable() is False


def test_a_gateway_can_be_started_with_every_module_of_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def find_spec(name: str) -> ModuleSpec | None:
        return importlib.util.spec_from_loader(name, None)

    monkeypatch.setattr(gateway.importlib.util, "find_spec", find_spec)
    assert gatewayable() is True

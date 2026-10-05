"""agy's two gateway ways: what each asks, what it writes down, and what the fence lets through.

Both are agy's enterprise LLM gateway, which is variables and only variables -- a URL, a key, a
wire protocol of exactly two, and the models it serves -- so an account of either is the
environment a turn runs under and nothing else. What is checked here is that environment, and
that a shell exporting any of it cannot steer a turn under some other account.

Every file touched is under `tmp_path`: this user's home is moved there for each test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends
from hmz.coganchor.providers import login
from tests import logins
from tests.logins import way

if TYPE_CHECKING:
    from pathlib import Path

#: Every variable the binary names for its gateway (agy 1.2.16).
GATEWAY = (
    "AGY_LLM_GATEWAY_API_KEY",
    "AGY_LLM_GATEWAY_CA_CERT",
    "AGY_LLM_GATEWAY_HEADERS",
    "AGY_LLM_GATEWAY_MODELS",
    "AGY_LLM_GATEWAY_PROXY_URL",
    "AGY_LLM_GATEWAY_URL",
    "AGY_LLM_GATEWAY_WIRE_PROTOCOL",
)


@pytest.fixture
def house(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This user's home, somewhere temporary: nothing here may read or write the real one."""
    return logins.house(tmp_path, monkeypatch)


def test_agy_offers_its_ways_in_the_order_they_are_chosen_between() -> None:
    """Sign-ins first, then a key, then the gateways, then the cloud's own credentials."""
    profile = backends.named("agy")
    assert profile is not None

    assert [one.name for one in profile.ways] == [
        "login",
        "key",
        "gemini-gateway",
        "openai-gateway",
        "adc",
    ]


def test_a_gemini_gateway_is_told_where_it_is_and_the_key_it_takes() -> None:
    """Its catalogue is agy's own Gemini models, so there is no list of them to ask for."""
    assert login.asked(way("agy", "gemini-gateway"), {}) == [
        "AGY_LLM_GATEWAY_URL",
        "AGY_LLM_GATEWAY_API_KEY",
    ]


def test_an_openai_gateway_is_also_told_every_model_it_serves() -> None:
    """None of agy's own model names is one an OpenAI endpoint is likely to answer to."""
    assert login.asked(way("agy", "openai-gateway"), {}) == [
        "AGY_LLM_GATEWAY_URL",
        "AGY_LLM_GATEWAY_API_KEY",
        "AGY_LLM_GATEWAY_MODELS",
    ]


@pytest.mark.parametrize(
    ("named", "protocol"), [("gemini-gateway", "genai"), ("openai-gateway", "openai")]
)
def test_a_gateway_account_is_its_answers_and_the_protocol_nobody_types(
    house: Path, named: str, protocol: str
) -> None:
    """The protocol is the way's to say: `genai` or `openai`, the only two agy takes."""
    answers = {
        "AGY_LLM_GATEWAY_URL": "https://gw.example.invalid",
        "AGY_LLM_GATEWAY_API_KEY": "not-a-real-key",
    }
    if named == "openai-gateway":
        answers["AGY_LLM_GATEWAY_MODELS"] = "gpt-x,gpt-y"

    provider = login.make("agy", "mine", way("agy", named), answers)

    assert provider.way == named
    assert dict(provider.env) == answers | {"AGY_LLM_GATEWAY_WIRE_PROTOCOL": protocol}
    # Variables, all of it: a key on a command line is a key in every process listing.
    assert provider.args == ()


def test_no_gateway_variable_left_in_a_shell_reaches_a_turn_under_another_account() -> (
    None
):
    """The URL alone puts agy in gateway mode, ahead of whatever it is signed into."""
    profile = backends.named("agy")
    assert profile is not None

    assert set(GATEWAY) <= profile.hushes()
    # But not the project a Google sign-in may be billed to: no way here could set it back.
    assert "GOOGLE_CLOUD_PROJECT" not in profile.hushes()


def test_a_model_a_gateway_was_told_it_serves_is_offered_at_no_effort() -> None:
    """Agy refuses `--effort` for every one of them, so a rung offered is a turn refused.

    What `agy models` printed under an `openai-gateway` account (agy 1.2.16): the id twice,
    there being no name for a person to read. Its own catalogue keeps its ladder.
    """
    from hmz.coganchor import models

    profile = backends.named("agy")
    assert profile is not None
    said = (
        "gpt-x\tgpt-x\n"
        "gemini-3.7-flash-high\tGemini 3.7 Flash (High)\n"
        "gemini-3-flash-preview\tGemini 3 Flash\n"
    )

    found = models._agy(profile, lambda *_: said)  # pyright: ignore[reportPrivateUsage]

    assert [(one.name, one.efforts) for one in found] == [
        ("gpt-x", ()),
        ("gemini-3.7-flash-high", ("high",)),
        ("gemini-3-flash-preview", profile.efforts),
    ]


def test_the_fence_lets_a_gateway_account_reach_its_gateway() -> None:
    profile = backends.named("agy")
    assert profile is not None

    hosts = backends.reachable(
        profile,
        {
            "AGY_LLM_GATEWAY_URL": "https://gw.example.com/v1",
            "AGY_LLM_GATEWAY_PROXY_URL": "http://proxy.example.com:3128",
        },
    )

    assert "gw.example.com" in hosts
    assert "proxy.example.com:3128" in hosts

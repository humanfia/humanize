"""Kimi Code's ways in: a login per region, a Moonshot key, and a gateway per protocol.

Every way but the login is one provider Kimi builds out of `KIMI_MODEL_*` in memory, and what
tells them apart is `KIMI_MODEL_PROVIDER_TYPE` -- `kimi`, `openai`, `openai_responses`,
`anthropic` or `google-genai`. So what is checked here is that each way lands on its type,
whatever it was answered, and that a gateway's key is only ever a variable: nothing about an
account of Kimi is put on a command line.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends, providers
from hmz.coganchor.providers import login
from tests import logins
from tests.logins import way

if TYPE_CHECKING:
    from pathlib import Path

#: What each gateway is asked for, and nothing else.
_GATEWAY = {
    "KIMI_MODEL_BASE_URL": "https://example.invalid/v1",
    "KIMI_MODEL_API_KEY": "not-a-real-key",
    "KIMI_MODEL_NAME": "some-model",
}


@pytest.fixture
def house(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This user's home, somewhere temporary: nothing here may read or write the real one."""
    return logins.house(tmp_path, monkeypatch)


def test_kimi_offers_a_login_a_key_and_a_gateway_per_protocol() -> None:
    assert [one.name for one in providers.ways("kimi")] == [
        "login",
        "kimi-key",
        "openai-gateway",
        "anthropic-gateway",
        "gemini-gateway",
        "env",
    ]


def test_every_gateway_asks_where_then_the_key_then_the_model() -> None:
    for name in ("openai-gateway", "anthropic-gateway", "gemini-gateway"):
        assert login.asked(way("kimi", name), {}) == [
            "KIMI_MODEL_BASE_URL",
            "KIMI_MODEL_API_KEY",
            "KIMI_MODEL_NAME",
        ]


@pytest.mark.parametrize(
    ("name", "answered", "spoken"),
    [
        ("openai-gateway", {}, "openai"),
        (
            "openai-gateway",
            {"KIMI_MODEL_PROVIDER_TYPE": "openai_responses"},
            "openai_responses",
        ),
        ("anthropic-gateway", {}, "anthropic"),
        ("gemini-gateway", {}, "google-genai"),
    ],
)
def test_a_gateway_is_the_provider_type_its_protocol_is(
    house: Path, name: str, answered: dict[str, str], spoken: str
) -> None:
    made = login.make("kimi", "mine", way("kimi", name), _GATEWAY | answered)

    assert made.way == name
    assert dict(made.env) == _GATEWAY | {"KIMI_MODEL_PROVIDER_TYPE": spoken}
    assert made.args == ()


def test_a_moonshot_key_lands_on_moonshot_unless_told_otherwise(house: Path) -> None:
    key = way("kimi", "kimi-key")

    assert login.asked(key, {}) == ["KIMI_MODEL_API_KEY", "KIMI_MODEL_NAME"]
    made = login.make(
        "kimi", "mine", key, {"KIMI_MODEL_API_KEY": "k", "KIMI_MODEL_NAME": "m"}
    )
    assert dict(made.env) == {
        "KIMI_MODEL_API_KEY": "k",
        "KIMI_MODEL_BASE_URL": "https://api.moonshot.ai/v1",
        "KIMI_MODEL_NAME": "m",
        "KIMI_MODEL_PROVIDER_TYPE": "kimi",
    }


def test_a_login_names_its_region_on_the_command_line_and_keeps_none(
    house: Path,
) -> None:
    signs = way("kimi", "login")

    assert login.asked(signs, {}) == []
    assert [providers.filled(one, {"KIMI_REGION": "mainland-cn"}) for one in signs.argv] == [
        "kimi",
        "login",
        "--region",
        "mainland-cn",
    ]
    made = login.make("kimi", "mine", signs, {})
    assert dict(made.env) == {}


def test_no_way_of_kimi_puts_a_secret_on_a_command_line() -> None:
    profile = backends.named("kimi")
    assert profile is not None
    for one in profile.ways:
        secrets = {f"{{{asked.env}}}" for asked in one.asks if asked.secret}
        assert not any(s in part for s in secrets for part in one.argv + one.args)


def test_every_gateway_points_at_the_endpoint_the_catalogue_is_read_from() -> None:
    profile = backends.named("kimi")
    assert profile is not None
    for one in profile.ways[1:]:
        assert profile.endpoint in {asked.env for asked in one.asks}

"""Making a provider: what a way in is asked of, and what is written down afterwards.

Half of what a login is happens without one. A way in is asked what it still has no answer
for, a provider is made out of the answers, and the store is read back -- what a way keeps,
what it sets whatever it was told, what it fills into a backend's own command line. None of
that reaches a CLI, a socket or a network: every file it touches is under `tmp_path`, which
is what makes it the unit tier.

The other half is a real login -- a backend's own command, spawned under the supervisor that
answers the paths it writes to -- and that is `tests/system/providers/test_login.py`, the tier
meant to be left out where a tracer cannot be counted on. Apart from it so that leaving that
half out does not leave this one out too: a tier is a directory, so a test kept in the wrong
one is a test a gate stops running without ever saying so.

Nothing here may touch the credentials of whoever is running the suite: this user's home is
moved to `tmp_path` for every test that names one, and every backend's own home variable is
taken out of the environment with it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hmz.coganchor import providers
from hmz.coganchor.providers import login
from tests import logins
from tests.logins import way


@pytest.fixture
def house(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This user's home, somewhere temporary: nothing here may read or write the real one."""
    return logins.house(tmp_path, monkeypatch)


# ------------------------------------------------------------ what is asked


def test_a_way_is_found_under_the_name_the_backend_offers_it_by() -> None:
    found = login.way_of("claude-code", "bedrock")

    assert found is not None
    assert found.name == "bedrock"
    assert login.way_of("claude", "env") is providers.ENV
    assert login.way_of("claude", "nope") is None
    assert login.way_of("nope", "login") is None


def test_a_way_still_has_to_be_told_whatever_it_has_no_answer_for() -> None:
    gateway = way("claude", "gateway")

    assert login.asked(gateway, {}) == ["ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"]
    assert login.asked(gateway, {"ANTHROPIC_BASE_URL": "https://x.invalid"}) == [
        "ANTHROPIC_AUTH_TOKEN"
    ]
    assert (
        login.asked(gateway, {"ANTHROPIC_BASE_URL": "x", "ANTHROPIC_AUTH_TOKEN": "y"})
        == []
    )


def test_a_question_with_an_answer_that_is_usually_right_is_not_one_to_ask() -> None:
    assert login.asked(way("claude", "bedrock"), {}) == ["AWS_PROFILE"]
    assert login.asked(way("claude", "login"), {}) == []
    assert login.asked(providers.ENV, {}) == []


# --------------------------------------------------------- what is written down


def test_a_provider_is_what_its_way_in_was_answered_with(house: Path) -> None:
    provider = login.make(
        "claude",
        "mine",
        way("claude", "gateway"),
        {
            "ANTHROPIC_BASE_URL": "https://example.invalid/anthropic",
            "ANTHROPIC_AUTH_TOKEN": "not-a-real-token",
        },
    )

    assert provider.way == "gateway"
    assert dict(provider.env) == {
        "ANTHROPIC_BASE_URL": "https://example.invalid/anthropic",
        "ANTHROPIC_AUTH_TOKEN": "not-a-real-token",
    }
    assert providers.find("claude", "mine") == provider


def test_an_answer_a_way_does_not_keep_is_not_written_down_anywhere(
    house: Path,
) -> None:
    """Codex reads its key into its own store: a second copy is a second place to leak it."""
    provider = login.make(
        "codex", "mine", way("codex", "key"), {"OPENAI_API_KEY": "sk-not-a-real-key"}
    )

    assert dict(provider.env) == {}
    assert "sk-not-a-real-key" not in (provider.at / "provider.json").read_text()


def test_what_a_way_sets_whatever_it_was_answered_is_set(house: Path) -> None:
    """The variable that switches a backend onto a vendor's cloud is nobody's to type."""
    provider = login.make(
        "claude", "mine", way("claude", "bedrock"), {"AWS_PROFILE": "work"}
    )

    assert dict(provider.env) == {
        "AWS_PROFILE": "work",
        "AWS_REGION": "us-east-1",  # the answer nobody was asked for
        "CLAUDE_CODE_USE_BEDROCK": "1",
    }


def test_an_answer_is_filled_into_what_the_backend_takes_on_its_command_line(
    house: Path,
) -> None:
    """Codex takes a provider as settings rather than as variables, so a way carries arguments."""
    provider = login.make(
        "codex",
        "mine",
        way("codex", "openai-gateway"),
        {
            "CODEX_PROVIDER_URL": "https://example.invalid/v1",
            "CODEX_PROVIDER_KEY": "not-a-real-key",
        },
    )

    assert (
        "model_providers.humanize.base_url=https://example.invalid/v1" in provider.args
    )
    assert "model_providers.humanize.wire_api=responses" in provider.args
    assert provider.env["CODEX_PROVIDER_KEY"] == "not-a-real-key"


def test_an_azure_resource_is_a_provider_codex_speaks_azure_to(house: Path) -> None:
    """Named `azure`, so codex sends it what Azure takes, at the version nobody was asked for."""
    provider = login.make(
        "codex",
        "mine",
        way("codex", "azure"),
        {
            "AZURE_OPENAI_BASE_URL": "https://res.openai.azure.com/openai",
            "AZURE_OPENAI_API_KEY": "not-a-real-key",
        },
    )

    assert provider.args == (
        "-c",
        "model_provider=humanize",
        "-c",
        "model_providers.humanize.name=azure",
        "-c",
        "model_providers.humanize.base_url=https://res.openai.azure.com/openai",
        "-c",
        "model_providers.humanize.env_key=AZURE_OPENAI_API_KEY",
        "-c",
        'model_providers.humanize.query_params.api-version="2025-04-01-preview"',
        "-c",
        "model_providers.humanize.wire_api=responses",
    )
    # The key reaches the turn as the variable codex was told to read, never as an argument.
    assert provider.env["AZURE_OPENAI_API_KEY"] == "not-a-real-key"
    assert not any("not-a-real-key" in one for one in provider.args)


@pytest.mark.parametrize(
    ("named", "answers", "args"),
    [
        (
            "bedrock",
            {"AWS_PROFILE": "work"},
            (
                "-c",
                "model_provider=amazon-bedrock",
                "-c",
                "model_providers.amazon-bedrock.aws.profile=work",
                "-c",
                "model_providers.amazon-bedrock.aws.region=us-east-1",
            ),
        ),
        (
            "bedrock-key",
            {"AWS_BEARER_TOKEN_BEDROCK": "not-a-real-key", "AWS_REGION": "eu-west-1"},
            (
                "-c",
                "model_provider=amazon-bedrock",
                "-c",
                "model_providers.amazon-bedrock.aws.region=eu-west-1",
            ),
        ),
        ("ollama", {}, ("-c", "model_provider=ollama")),
        ("lmstudio", {}, ("-c", "model_provider=lmstudio")),
    ],
)
def test_a_provider_codex_has_built_in_is_named_on_its_command_line(
    house: Path, named: str, answers: dict[str, str], args: tuple[str, ...]
) -> None:
    """Bedrock and the local servers are codex's own providers: the account says which."""
    provider = login.make("codex", "mine", way("codex", named), answers)

    assert provider.args == args
    assert not any("not-a-real-key" in one for one in provider.args)


def test_a_local_server_is_where_it_usually_is_unless_somebody_says(
    house: Path,
) -> None:
    """The one variable codex reads a local server's place from, at its own port."""
    ollama = login.make("codex", "o", way("codex", "ollama"))
    elsewhere = login.make(
        "codex",
        "l",
        way("codex", "lmstudio"),
        {"CODEX_OSS_BASE_URL": "http://box:9/v1"},
    )

    assert ollama.env == {"CODEX_OSS_BASE_URL": "http://localhost:11434/v1"}
    assert elsewhere.env == {"CODEX_OSS_BASE_URL": "http://box:9/v1"}


def test_a_workload_identity_is_its_two_variables(house: Path) -> None:
    """Nothing to run: codex trades the token file for a workspace's tokens each start."""
    provider = login.make(
        "codex",
        "ci",
        way("codex", "workload"),
        {
            "OPENAI_FEDERATION_RULE_ID": "rule-1",
            "OPENAI_IDENTITY_TOKEN_FILE": "/var/run/token",
        },
    )

    assert dict(provider.env) == {
        "OPENAI_FEDERATION_RULE_ID": "rule-1",
        "OPENAI_IDENTITY_TOKEN_FILE": "/var/run/token",
    }
    assert provider.args == ()


def test_variables_of_your_own_are_kept_whatever_they_are_called(house: Path) -> None:
    """The way in every backend has: nothing declares these, so nothing may drop them."""
    provider = login.make("pi", "mine", providers.ENV, {"PI_API_KEY": "not-a-real-key"})

    assert dict(provider.env) == {"PI_API_KEY": "not-a-real-key"}


def test_an_answer_nobody_gave_is_not_a_variable_set_to_nothing(house: Path) -> None:
    provider = login.make(
        "claude", "mine", way("claude", "key"), {"ANTHROPIC_API_KEY": ""}
    )

    assert dict(provider.env) == {}


def test_making_a_provider_makes_the_places_its_login_will_write_to(
    house: Path,
) -> None:
    provider = login.make("claude", "mine", way("claude", "login"))

    assert provider.swaps()
    for _, instead in provider.swaps():
        assert Path(instead).parent.is_dir()


def test_a_provider_that_could_not_be_named_is_not_made(house: Path) -> None:
    with pytest.raises(ValueError, match="is not a valid account name"):
        login.make("claude", "../evil", way("claude", "login"))
    with pytest.raises(ValueError, match="nope: unknown agent"):
        login.make("nope", "mine", providers.ENV)


# ------------------------------------------------------------- what signs in


def test_a_way_that_is_only_answers_has_nothing_to_sign_in(house: Path) -> None:
    """It was done when it was written down, so there is no command and no status but zero."""
    provider = login.make(
        "claude", "mine", way("claude", "key"), {"ANTHROPIC_API_KEY": "not-a-real-key"}
    )

    assert login.sign_in(provider, way("claude", "key")) == 0

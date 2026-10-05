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

import subprocess
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
    gateway = way("claude", "anthropic-gateway")

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
        way("claude", "anthropic-gateway"),
        {
            "ANTHROPIC_BASE_URL": "https://example.invalid/anthropic",
            "ANTHROPIC_AUTH_TOKEN": "not-a-real-token",
        },
    )

    assert provider.way == "anthropic-gateway"
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
        way("codex", "gateway"),
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


# ------------------------------------------- what a backend's own command is given


def _signed(
    monkeypatch: pytest.MonkeyPatch, cli: str, name: str, answers: dict[str, str]
) -> tuple[providers.Provider, list[str]]:
    """Makes and signs in an account, and returns it with the command its sign-in ran.

    The command as the way filled it, before the supervisor that would point its paths
    elsewhere is put in front of it -- and nothing is run, which is what keeps this here.
    """
    ran: list[list[str]] = []

    def run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        ran.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    def command(_swaps: object, argv: list[str]) -> list[str]:
        return list(argv)

    monkeypatch.setattr(login.redirect, "command", command)
    monkeypatch.setattr(login.subprocess, "run", run)
    provider = login.make(cli, "mine", way(cli, name), answers)
    assert login.sign_in(provider, way(cli, name), answers) == 0
    (argv,) = ran
    return provider, argv


def test_a_gateway_is_offered_once_for_each_protocol_the_backend_speaks() -> None:
    """Named for the vendor whose API the endpoint speaks, and the same name everywhere."""
    names = [one.name for one in providers.ways("mcode")]
    assert names == ["login", "key", "openai-gateway", "anthropic-gateway", "env"]
    named = [one.name for one in providers.ways("cursor-agent")]
    assert named == ["login", "key", "cursor-gateway", "env"]


def test_an_openai_gateway_asks_which_of_its_apis_and_says_chat_unless_told(
    house: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = {
        "MCODE_GATEWAY_URL": "https://gw.example/v1",
        "MCODE_PROVIDER_API_KEY": "not-a-real-key",
        "MCODE_GATEWAY_MODEL": "m",
    }
    assert login.asked(way("mcode", "openai-gateway"), {}) == [
        "MCODE_GATEWAY_URL",
        "MCODE_PROVIDER_API_KEY",
        "MCODE_GATEWAY_MODEL",
    ]

    provider, argv = _signed(monkeypatch, "mcode", "openai-gateway", answers)
    assert argv[argv.index("--api-format") + 1] == "openai-completions"
    assert argv[argv.index("--base-url") + 1] == "https://gw.example/v1"
    assert argv[argv.index("--model") + 1] == "m"
    # Under the one name a model of it is spelled with, and the key nowhere on the line.
    assert argv[argv.index("--name") + 1] == "gateway"
    assert "not-a-real-key" not in argv
    assert dict(provider.env) == {
        "MCODE_GATEWAY_URL": "https://gw.example/v1",
        "MCODE_PROVIDER_API_KEY": "not-a-real-key",
    }

    _, argv = _signed(
        monkeypatch,
        "mcode",
        "openai-gateway",
        answers | {"MCODE_GATEWAY_FORMAT": "openai-responses"},
    )
    assert argv[argv.index("--api-format") + 1] == "openai-responses"


def test_an_anthropic_gateway_is_added_speaking_messages_without_being_asked(
    house: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = {
        "MCODE_GATEWAY_URL": "https://gw.example",
        "MCODE_PROVIDER_API_KEY": "not-a-real-key",
        "MCODE_GATEWAY_MODEL": "m",
    }
    asks = {one.env for one in way("mcode", "anthropic-gateway").asks}
    assert "MCODE_GATEWAY_FORMAT" not in asks

    _, argv = _signed(monkeypatch, "mcode", "anthropic-gateway", answers)
    assert argv[argv.index("--api-format") + 1] == "anthropic-messages"
    assert argv[argv.index("--name") + 1] == "gateway"
    assert "not-a-real-key" not in argv


def test_a_minimax_sign_in_is_in_the_region_asked_and_global_unless_told(
    house: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider, argv = _signed(monkeypatch, "mcode", "login", {})
    assert argv == ["mcode", "login", "--region", "global"]
    # The sign-in remembers its own region, so the answer is the command line's alone.
    assert dict(provider.env) == {}

    _, argv = _signed(monkeypatch, "mcode", "login", {"MCODE_REGION": "cn"})
    assert argv == ["mcode", "login", "--region", "cn"]


def test_a_minimax_key_is_kept_with_the_region_its_turns_are_sent_to(
    house: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider, argv = _signed(
        monkeypatch, "mcode", "key", {"MCODE_PROVIDER_API_KEY": "not-a-real-key"}
    )
    assert argv == ["mcode", "provider", "set-minimax-key"]
    assert dict(provider.env) == {
        "MCODE_PROVIDER_API_KEY": "not-a-real-key",
        "MAVIS_REGION": "en",
    }


def test_a_cursor_gateway_is_its_endpoint_and_its_key(house: Path) -> None:
    provider = login.make(
        "cursor-agent",
        "mine",
        way("cursor-agent", "cursor-gateway"),
        {
            "CURSOR_API_ENDPOINT": "https://proxy.example",
            "CURSOR_API_KEY": "not-a-real-key",
        },
    )

    assert provider.way == "cursor-gateway"
    assert dict(provider.env) == {
        "CURSOR_API_ENDPOINT": "https://proxy.example",
        "CURSOR_API_KEY": "not-a-real-key",
    }

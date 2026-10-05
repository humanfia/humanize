"""The accounts half of the SDK, which is the same store every other way in walks.

`Accounts` is a facade: each method is one call into :mod:`hmz.coganchor.providers` or
:mod:`hmz.coganchor.models`. What is worth checking about a facade is not the call -- that is one
line
-- but that it is wired to the right one, with the arguments in the right order, so that an
account made from here is the account a command line lists a moment later and the account the
interface offers. So these go through the SDK and read back through the store, and the two
have to agree.

Nothing here signs into anything or starts a backend to ask what it runs: the way in that is
exercised is the one that is only answers, and what a backend said it runs is written down
rather than asked for.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import providers
from hmz.sdk import Hmz

if TYPE_CHECKING:
    from hmz.coganchor.backends import Model


def test_an_account_written_from_here_is_one_the_store_reads_back() -> None:
    held = Hmz().accounts

    made = held.write(
        "claude",
        "mine",
        way="anthropic-gateway",
        env={"ANTHROPIC_BASE_URL": "https://example.invalid/anthropic"},
        args=("--flag", "value"),
    )

    assert providers.find("claude", "mine") == made
    assert made.way == "anthropic-gateway"
    assert made.env["ANTHROPIC_BASE_URL"] == "https://example.invalid/anthropic"
    assert made.args == ("--flag", "value")


def test_an_account_written_without_a_way_in_is_the_one_that_is_only_variables() -> (
    None
):
    """`write` has two calls in it, and which one it makes is whether a way was named."""
    written = Hmz().accounts.write("claude", "plain", env={"ANTHROPIC_API_KEY": "k"})

    assert written.way == providers.ENV.name


def test_an_account_rewritten_with_its_answers_alone_keeps_the_arguments_its_way_adds() -> (
    None
):
    """Codex's gateway is a URL on the command line: corrected, it is the new URL there.

    Which is what the accounts page's `edit settings` does, answers and no arguments. Written
    with none, the account was one whose turns asked api.openai.com with no key at all.
    """
    held = Hmz().accounts
    gateway = held.way("codex", "openai-gateway")
    assert gateway is not None
    held.make(
        "codex",
        "gw",
        gateway,
        {"CODEX_PROVIDER_URL": "https://old.invalid/v1", "CODEX_PROVIDER_KEY": "k"},
    )

    written = held.write(
        "codex",
        "gw",
        "openai-gateway",
        {"CODEX_PROVIDER_URL": "https://new.invalid/v1", "CODEX_PROVIDER_KEY": "k"},
    )

    assert "model_providers.humanize.base_url=https://new.invalid/v1" in written.args
    assert "model_provider=humanize" in written.args
    assert not any("old.invalid" in one for one in written.args)


def test_every_account_is_listed_and_one_backend_s_are_listed_alone() -> None:
    held = Hmz().accounts
    held.write("claude", "first")
    held.write("codex", "second")

    assert [(one.cli, one.name) for one in held.all()] == [
        ("claude", "first"),
        ("codex", "second"),
    ]
    assert [one.name for one in held.all("claude")] == ["first"]


def test_an_account_is_found_by_name_and_a_name_nobody_made_is_nothing() -> None:
    held = Hmz().accounts
    held.write("claude", "mine")

    found = held.find("claude", "mine")

    assert found is not None
    assert found.name == "mine"
    assert held.find("claude", "never-made") is None


def test_where_an_account_is_kept_is_answered_before_it_is_made() -> None:
    """Which is what asks it of a name: a directory is made at what this says."""
    held = Hmz().accounts

    at = held.where("claude", "mine")

    assert at == providers.where("claude", "mine")
    assert not at.exists()
    assert held.write("claude", "mine").at == at


def test_a_name_an_account_may_not_be_kept_under_is_refused() -> None:
    with pytest.raises(ValueError, match="name"):
        Hmz().accounts.where("claude", "../evil")


def test_the_ways_in_a_backend_offers_are_the_ones_it_is_asked_for() -> None:
    held = Hmz().accounts

    assert held.ways("claude") == providers.ways("claude")
    assert [one.name for one in held.ways("claude")]


def test_a_way_in_is_found_by_name_and_a_name_it_does_not_offer_is_nothing() -> None:
    held = Hmz().accounts

    way = held.way("claude", "anthropic-gateway")

    assert way is not None
    assert way.name == "anthropic-gateway"
    assert held.way("claude", "not-a-way") is None


def test_what_a_way_in_still_has_to_be_told_is_what_was_not_answered() -> None:
    held = Hmz().accounts
    way = held.way("claude", "anthropic-gateway")
    assert way is not None

    assert held.asks(way, {}) == ["ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"]
    assert held.asks(way, {"ANTHROPIC_BASE_URL": "https://example.invalid"}) == [
        "ANTHROPIC_AUTH_TOKEN"
    ]


def test_a_way_in_whose_answers_have_a_fixed_one_does_not_ask_for_it() -> None:
    """Bedrock's region has a default, so it is answerable without being answered."""
    held = Hmz().accounts
    way = held.way("claude", "bedrock")
    assert way is not None

    assert "AWS_REGION" not in held.asks(way, {})


def test_an_account_made_out_of_a_way_in_keeps_what_that_way_sets() -> None:
    held = Hmz().accounts
    way = held.way("claude", "bedrock")
    assert way is not None

    made = held.make("claude", "aws", way, {"AWS_PROFILE": "work"})

    assert made.way == "bedrock"
    assert made.env["AWS_PROFILE"] == "work"
    assert made.env["CLAUDE_CODE_USE_BEDROCK"] == "1"
    # And the fixed answer nobody was asked is written down with the rest.
    assert made.env["AWS_REGION"] == "us-east-1"


def test_signing_in_by_a_way_that_is_only_answers_runs_nothing_and_is_already_done() -> (
    None
):
    held = Hmz().accounts
    way = held.way("claude", "key")
    assert way is not None
    made = held.make("claude", "keyed", way, {"ANTHROPIC_API_KEY": "not-a-real-key"})

    assert held.sign_in(made, way) == 0


def test_the_other_backends_an_account_could_run_are_the_vendor_s_rather_than_the_cli_s() -> (
    None
):
    """An Anthropic key is an Anthropic key whoever is holding it."""
    held = Hmz().accounts
    key = held.way("claude", "key")
    assert key is not None
    made = held.make("claude", "mine", key, {"ANTHROPIC_API_KEY": "not-a-real-key"})

    serves = held.serves(made)

    assert serves == providers.serves(made)
    assert "pi" in serves
    assert "claude" not in serves  # the backend it already is, which is not another one


def test_an_account_that_cannot_travel_says_there_is_nowhere_for_it_to_go() -> None:
    """A gateway is reached under one backend's own variables and nothing else reads them."""
    held = Hmz().accounts
    gateway = held.way("claude", "anthropic-gateway")
    assert gateway is not None
    made = held.make(
        "claude",
        "walled",
        gateway,
        {
            "ANTHROPIC_BASE_URL": "https://example.invalid/anthropic",
            "ANTHROPIC_AUTH_TOKEN": "not-a-real-token",
        },
    )

    assert held.serves(made) == ()


def test_an_account_copied_to_another_backend_is_written_down_under_it() -> None:
    held = Hmz().accounts
    key = held.way("claude", "key")
    assert key is not None
    made = held.make("claude", "mine", key, {"ANTHROPIC_API_KEY": "not-a-real-key"})

    copy = held.copies(made, "pi", "copied")

    assert copy.cli == "pi"
    assert copy.name == "copied"
    assert held.find("pi", "copied") == copy


def test_a_copy_made_under_no_name_of_its_own_keeps_the_one_it_already_has() -> None:
    held = Hmz().accounts
    key = held.way("claude", "key")
    assert key is not None
    made = held.make("claude", "mine", key, {"ANTHROPIC_API_KEY": "not-a-real-key"})

    assert held.copies(made, "pi").name == "mine"


def test_an_account_that_could_not_run_another_backend_is_not_copied_to_it() -> None:
    held = Hmz().accounts
    made = held.write("claude", "mine", env={"ANTHROPIC_API_KEY": "not-a-real-key"})

    with pytest.raises(
        ValueError, match="cannot be used with definitely-not-a-backend"
    ):
        held.copies(made, "definitely-not-a-backend")


def test_an_account_says_nothing_about_where_a_failed_turn_goes() -> None:
    """That is the fallback page's to say, between places, and no longer an account's."""
    held = Hmz().accounts

    assert not hasattr(held, "chain")
    assert not hasattr(held, "points")
    assert not hasattr(held.write("claude", "mine"), "fallback")


def test_an_account_taken_away_is_gone_and_taking_it_away_twice_says_so() -> None:
    held = Hmz().accounts
    held.write("claude", "mine")

    assert held.remove("claude", "mine")
    assert held.find("claude", "mine") is None
    assert not held.remove("claude", "mine")


def test_the_account_this_machine_is_signed_into_is_not_one_to_take_away() -> None:
    """Humanize did not make it and keeps no credentials for it."""
    with pytest.raises(ValueError, match="is not a valid account name"):
        Hmz().accounts.remove("claude", "")


def test_variables_are_read_out_of_the_lines_they_were_typed_as() -> None:
    held = Hmz().accounts

    assert held.env("A=one\n# a note\n\nB = two ") == {"A": "one", "B": "two"}


def test_a_line_that_is_not_a_variable_is_a_line_to_correct() -> None:
    with pytest.raises(ValueError, match="NAME=VALUE"):
        Hmz().accounts.env("not a variable")


def test_what_a_turn_runs_with_is_the_account_s_and_nothing_for_no_account() -> None:
    held = Hmz().accounts
    made = held.write("claude", "mine", env={"ANTHROPIC_API_KEY": "not-a-real-key"})

    assert held.environ(made) == {"ANTHROPIC_API_KEY": "not-a-real-key"}
    assert held.environ(None) == {}


def test_what_a_backend_runs_is_read_off_what_was_kept_and_nothing_before_it_was_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hmz.coganchor import models

    held = Hmz().accounts

    assert held.models("claude") == ()
    assert held.asked("claude") == ""

    kept: tuple[Model, ...] = ()

    def answering(
        cli: str, provider: str = "", seconds: float = 0.0
    ) -> tuple[Model, ...]:
        assert (cli, provider) == ("claude", "mine")
        return kept

    monkeypatch.setattr(models, "ask", answering)

    assert held.ask("claude", "mine") == kept


def test_how_long_a_backend_is_given_to_answer_is_passed_on_only_when_it_is_said(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default is that backend's own, which is a different call rather than a number."""
    from hmz.coganchor import models

    seen: list[tuple[str, str, float | None]] = []

    def answering(
        cli: str, provider: str = "", seconds: float | None = None
    ) -> tuple[Model, ...]:
        seen.append((cli, provider, seconds))
        return ()

    monkeypatch.setattr(models, "ask", answering)
    held = Hmz().accounts

    held.ask("claude")
    held.ask("claude", "mine", 12.5)

    assert seen == [("claude", "", None), ("claude", "mine", 12.5)]


@pytest.mark.parametrize(
    ("days", "stale"), [(None, True), (1, False), (6, False), (8, True), (40, True)]
)
def test_what_a_backend_said_it_runs_goes_stale_a_week_after_it_was_asked(
    days: int | None, *, stale: bool
) -> None:
    """So a list a vendor has since moved under is asked again rather than offered for ever.

    `grok-4.5` was in what grok said it runs on the tenth, and an `unknown model id` by the
    twenty-seventh: nothing had asked it again in between, so it was offered all the same.
    """
    import datetime
    import json

    from hmz.coganchor import models

    if days is not None:
        at = models.where("grok")
        at.parent.mkdir(parents=True, exist_ok=True)
        then = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)
        at.write_text(
            json.dumps(
                {
                    "asked": then.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "models": [{"name": "grok-4.5", "efforts": ["low"]}],
                }
            )
        )

    assert Hmz().accounts.stale("grok") is stale


def test_a_qwen_gateway_account_says_which_way_it_signs_in() -> None:
    """qwen-code given only a key and a URL answers `No auth type is selected`."""
    held = Hmz().accounts
    gateway = held.way("qwen", "openai-gateway")
    assert gateway is not None

    made = held.make(
        "qwen",
        "gw",
        gateway,
        {"OPENAI_API_KEY": "k", "OPENAI_BASE_URL": "https://gw.invalid"},
    )

    assert made.args == ("--auth-type", "openai")
    assert made.env["QWEN_DEFAULT_AUTH_TYPE"] == "openai"


def test_a_qwen_gateway_speaking_responses_is_told_so_and_stays_told() -> None:
    """The protocol is kept, so the command line worked out again from it says the same."""
    held = Hmz().accounts
    gateway = held.way("qwen", "openai-gateway")
    assert gateway is not None
    answers = {
        "OPENAI_API_KEY": "k",
        "OPENAI_BASE_URL": "https://gw.invalid/v1",
        "QWEN_DEFAULT_AUTH_TYPE": "openai-responses",
    }

    made = held.make("qwen", "gw", gateway, answers)
    edited = held.write("qwen", "gw", way=made.way, env=made.env)

    assert made.args == ("--auth-type", "openai-responses")
    assert edited.args == made.args
    assert "k" not in made.args  # the key stays a variable


@pytest.mark.parametrize(
    ("way", "answers", "auth"),
    [
        ("coding-plan", {"OPENAI_API_KEY": "k"}, "openai"),
        ("token-plan", {"OPENAI_API_KEY": "k"}, "openai"),
        ("gemini-key", {"GEMINI_API_KEY": "k"}, "gemini"),
        (
            "anthropic-gateway",
            {"ANTHROPIC_BASE_URL": "https://gw.invalid", "ANTHROPIC_API_KEY": "k"},
            "anthropic",
        ),
        (
            "gemini-gateway",
            {"GOOGLE_GEMINI_BASE_URL": "https://gw.invalid", "GEMINI_API_KEY": "k"},
            "gemini",
        ),
        ("vertex", {"GOOGLE_CLOUD_PROJECT": "p"}, "vertex-ai"),
        ("vertex-key", {"GOOGLE_API_KEY": "k"}, "vertex-ai"),
    ],
)
def test_every_qwen_way_names_the_auth_type_it_is(
    way: str, answers: dict[str, str], auth: str
) -> None:
    """Each of Qwen Code's six auth types is one `--auth-type`, said on every turn."""
    held = Hmz().accounts
    chosen = held.way("qwen", way)
    assert chosen is not None

    made = held.make("qwen", way, chosen, answers)

    assert made.args == ("--auth-type", auth)
    assert all(value in made.env.values() for value in answers.values())


def test_a_qwen_plan_or_cloud_is_pointed_where_it_lives_unless_told_otherwise() -> None:
    """The fixed answers: each plan's mainland endpoint, and Vertex's global location."""
    held = Hmz().accounts
    plans = {
        "coding-plan": "https://coding.dashscope.aliyuncs.com/v1",
        "token-plan": (
            "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        ),
    }
    for name, url in plans.items():
        way = held.way("qwen", name)
        assert way is not None
        assert held.make("qwen", name, way, {"OPENAI_API_KEY": "k"}).env == {
            "OPENAI_API_KEY": "k",
            "OPENAI_BASE_URL": url,
        }
    vertex = held.way("qwen", "vertex")
    assert vertex is not None
    made = held.make("qwen", "vx", vertex, {"GOOGLE_CLOUD_PROJECT": "p"})
    assert made.env == {"GOOGLE_CLOUD_PROJECT": "p", "GOOGLE_CLOUD_LOCATION": "global"}

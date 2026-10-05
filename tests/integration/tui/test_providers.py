"""Which account an agent's turns run as: made here, given to one agent, and kept.

An account is credentials rather than a way of running a model, so it is asked about where
the agent is chosen and not where the flow is -- two agents of one CLI may be two accounts.
Nothing here signs anything in: a CLI's own login is the only thing that can perform that
CLI's login, so it is patched out and what is tested is the walk up to it. And making one is
one form -- its CLI, its way in, its name, what that way asks and where else it goes.
"""

from __future__ import annotations

import json
import unittest.mock
from typing import TYPE_CHECKING, cast

import pytest
from textual import events
from textual.content import Content
from textual.widgets import Button, Label, OptionList, Static

from hmz.coganchor import providers, settings
from hmz.coganchor.backends import Model
from hmz.runtime.kept import Runs
from hmz.runtime.settings import Settings
from hmz.tui import Humanize
from hmz.tui.pick import (
    _ACT_ADD,
    _ACT_DONE,
    _ACT_REMOVE,
    _ACT_SAVE,
    _ACT_SEARCH,
    _ACT_SPEAKS,
    Account,
    Accounts,
    Agent,
    Confirms,
    Key,
    Providers,
    Signing,
    reads,
)
from hmz.tui.settings import PAGES, Adjusts
from tests.integration.tui.test_app import (
    bar,
    changes,
    drops,
    ids,
    into_agent,
    into_flows,
    into_settings,
    keeps,
    leaves,
    nexts,
    onto,
    opens,
    picks,
    rows,
    under,
)
from tests.tui.fixtures import set_up, transcript, until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: What one installed CLI looks like, for the tests that walk the agents sheet.
CLAUDE = {"claude": (Model("claude-opus-5", ("max", "high")),)}


def _under(app: Humanize) -> str:
    """What is said under the list, which is where a menu reports itself."""
    return str(app.screen.query_one("#tuning", Label).content)


def _drawn(app: Humanize) -> str:
    """Every row the sheet on top has put up, as one line of words to read.

    Without the colours, and with the lines a long row wraps onto run back together: a row
    says what it says whatever width the screen it was laid out across was.
    """
    return " ".join(
        " ".join(Content.from_markup(str(one.prompt)).plain.split())
        for one in app.screen.query_one("#choices", OptionList).options
    )


async def _doing(app: Humanize, driver: Pilot[None], held: str) -> None:
    """Opens what there is to do with the account under the cursor, and picks one of them.

    Which is what enter on an account is now: two questions about it -- correct it, sign it in
    again -- and a button under them that is rid of it, rather than three letter keys on the
    list of accounts.

    Args:
      app: The interface.
      driver: What is pumping it.
      held: Which of them, by the id its row is put up under or the key of the button.
    """
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Account), driver)
    await until(
        lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
    )
    await onto(app, driver, held)
    await driver.press("enter")


async def _adds(app: Humanize, driver: Pilot[None]) -> Signing:
    """Opens the form an account is made on, from the button under the accounts that says so.

    Args:
      app: The interface.
      driver: What is pumping it.

    Returns:
      The form.
    """
    await until(lambda: _ACT_ADD in bar(app), driver)
    await onto(app, driver, _ACT_ADD)
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Signing), driver)
    await until(
        lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
    )
    return cast("Signing", app.screen)


async def _chooses(app: Humanize, driver: Pilot[None], held: str, value: str) -> None:
    """Picks one row of the form's value from the list dropped under it.

    Args:
      app: The interface.
      driver: What is pumping it.
      held: The row -- `cli`, `way`.
      value: What it is to say.
    """
    sheet = cast("Signing", app.screen)
    if sheet._typed_in.get(held) != value:
        await picks(app, driver, held, value)
    assert sheet._typed_in.get(held) == value


async def _writes(app: Humanize, driver: Pilot[None], held: str, *keys: str) -> None:
    """Writes one question of the form an account is signed in by.

    Enter begins writing it, the keys are typed into it, and enter keeps it.

    Args:
      app: The interface.
      driver: What is pumping it.
      held: The question, by what the answer is kept under -- `name` for the name.
      keys: What to type.
    """
    await until(lambda: isinstance(app.screen, Signing), driver)
    await until(lambda: held in ids(app), driver)
    await changes(app, driver, held, *keys)


async def _answers(app: Humanize, driver: Pilot[None]) -> None:
    """Answers a form from the button below its questions.

    Args:
      app: The interface.
      driver: What is pumping it.
    """
    await onto(app, driver, _ACT_DONE)
    await driver.press("enter")


def _kept(cli: str, name: str = "") -> tuple[Model, ...]:
    """Writes down what one account's CLI said it runs, which is what asking it leaves.

    Args:
      cli: The backend.
      name: The account, or "" for the CLI as this machine already runs it.

    Returns:
      What was written, which is the one model these walks choose between.
    """
    from hmz.coganchor import models

    at = models.where(cli, name)
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(
        json.dumps(
            {
                "asked": "2026-08-12T00:00:00Z",
                "models": [
                    {"name": model.name, "efforts": list(model.efforts)}
                    for model in CLAUDE[cli]
                ],
            }
        )
    )
    return CLAUDE[cli]


def _account(name: str = "deepseek", cli: str = "claude") -> providers.Provider:
    """Writes one account down, as adding one on the accounts menu does, signing nothing in.

    And with the models that account runs already asked for, which is what making one does:
    a walk that has to press a key before there is anything to choose from is a walk nobody
    takes, and this is about the account rather than about the asking.
    """
    made = providers.add(cli, name, way="key", env={"ANTHROPIC_API_KEY": "not-a-key"})
    _kept(cli, name)
    return made


@pytest.mark.timeout(60)
async def test_the_command_opens_the_sheet_of_accounts() -> None:
    """A command of its own, because an account outlives the flow that was set up with it."""
    _account()
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        rows = [str(option.prompt) for option in listing.options]
        await leaves(app, driver)

    # The CLI it is under as a heading, and under it the name, the way and the variables.
    assert any("claude" in row for row in rows)
    assert any("deepseek" in row and "key" in row for row in rows)
    assert any("ANTHROPIC_API_KEY" in row for row in rows)
    # Their names and never a value: this is drawn where somebody can read it.
    assert all("not-a-key" not in row for row in rows)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.coganchor.providers.login.sign_in", return_value=0)
async def test_an_account_made_on_the_sheet_lands_in_the_store(
    signed_in: unittest.mock.MagicMock,
) -> None:
    """One form: which CLI and which way in, stepped where they stand, and a name."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")

        form = await _adds(app, driver)
        # The first CLI and its first way in, which for Claude Code is its own login: that
        # asks nothing else, the CLI's own login being what asks the rest -- and nothing
        # travels, so there is nothing to ask about where else it goes.
        assert rows(app) == ["cli", "way", "name"]
        assert bar(app) == [_ACT_DONE]
        assert form._typed_in["cli"] == "claude"
        assert form._typed_in["way"] == "login"
        # The name is written for you, and the cursor is on the first question.
        assert form._typed_in["name"] == "login"
        assert form.under() == "cli"

        await _writes(app, driver, "name", *"mine")
        await _answers(app, driver)

        # And the page is still the page, with the new one on it and the cursor on it.
        await until(lambda: isinstance(app.screen, Providers), driver)
        await until(
            lambda: "mine" in [one.name for one in providers.providers("claude")],
            driver,
        )
        await until(lambda: under(app) == "claude/mine", driver)
        await leaves(app, driver)
        said = transcript(app)

    made = providers.find("claude", "mine")
    assert made is not None
    assert made.way == "login"
    # The CLI's own way in ran, under this account's own paths, and nothing else did.
    assert signed_in.call_count == 1
    assert "claude/mine saved to" in said
    assert "claude/mine is signed in" in said


@pytest.mark.timeout(60)
async def test_deepseek_offers_its_own_ways_and_no_env_from_providers() -> None:
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        form = await _adds(app, driver)
        await _chooses(app, driver, "cli", "dsh")

        # Its own two, and no `env`: dsh is the one backend that takes no variables of
        # somebody's own, so the ways it names are the whole of what it offers.
        assert list(form.choices("way")) == ["key", "gateway"]
        assert form._typed_in["way"] == "key"
        listing = app.screen.query_one("#choices", OptionList)
        assert "DeepSeek API key" in str(listing.get_option("=way").prompt)
        await _chooses(app, driver, "way", "gateway")
        assert "endpoint speaking" in str(listing.get_option("=way").prompt)

        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Confirms | Providers), driver)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.coganchor.providers.login.sign_in", return_value=0)
async def test_a_secret_is_never_drawn_back(signed_in: unittest.mock.MagicMock) -> None:
    """It is on its way into a credential store, and a screen is somewhere it is read off."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await _adds(app, driver)

        # `key`, which is a variable rather than a login: it asks, and nothing is run.
        await _chooses(app, driver, "way", "key")
        await _writes(app, driver, "name", *"mine")
        await _writes(app, driver, "ANTHROPIC_API_KEY", *"sk-secret")
        form = app.screen.query_one("#choices", OptionList)
        drawn = [str(option.prompt) for option in form.options]
        assert all("sk-secret" not in row for row in drawn)
        assert any("•" * len("sk-secret") in row for row in drawn)

        await _answers(app, driver)
        await until(lambda: isinstance(app.screen, Providers), driver)
        await leaves(app, driver)

    made = providers.find("claude", "mine")
    assert made is not None
    assert made.env == {"ANTHROPIC_API_KEY": "sk-secret"}
    # A way that is only answers has already happened, having been written down.
    assert signed_in.call_count == 0


@pytest.mark.timeout(60)
async def test_a_pasted_secret_is_stored_without_its_trailing_newline() -> None:
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await _adds(app, driver)
        await _chooses(app, driver, "cli", "dsh")
        await _writes(app, driver, "name", *"mine")
        form = app.screen.query_one("#choices", OptionList)
        # Pasted onto the row the key is kept under, which is where a paste lands: onto a
        # written row, begun on as typing into one begins it.
        await onto(app, driver, "DEEPSEEK_API_KEY")
        form.post_message(events.Paste("sk-pasted\r\nignored"))
        await driver.pause()
        await driver.press("enter")
        await driver.pause()
        drawn = [str(option.prompt) for option in form.options]
        assert all("sk-pasted" not in row for row in drawn)
        assert any("•" * len("sk-pasted") in row for row in drawn)
        await _answers(app, driver)
        await until(lambda: isinstance(app.screen, Providers), driver)

    made = providers.find("dsh", "mine")
    assert made is not None
    assert made.env == {"DEEPSEEK_API_KEY": "sk-pasted"}


@pytest.mark.timeout(60)
@pytest.mark.parametrize("key", ["shift+enter", "ctrl+j"])
@unittest.mock.patch("hmz.coganchor.providers.login.sign_in", return_value=0)
async def test_variables_of_your_own_are_given_a_line_apiece(
    signed_in: unittest.mock.MagicMock,
    key: str,
) -> None:
    """The row that takes a list rather than a value, so it is the row a line breaks in.

    Only while it is being written: enter keeps what was written, so a line break is a key of
    its own there.
    """
    del signed_in
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await _adds(app, driver)
        # `env`, the way every backend has: variables of its own, which is the last of them.
        await _chooses(app, driver, "way", "env")
        await _writes(app, driver, "name", *"mine")
        # The variables, which is where a list goes.
        await _writes(
            app,
            driver,
            " ",
            *"ANTHROPIC_BASE_URL=https://example.test",
            key,
            *"ANTHROPIC_AUTH_TOKEN=sk-secret",
        )
        await _answers(app, driver)

        await until(lambda: isinstance(app.screen, Providers), driver)
        await leaves(app, driver)

    made = providers.find("claude", "mine")
    assert made is not None
    # Two of them, which is two lines: one line would have been one variable to correct.
    assert made.env == {
        "ANTHROPIC_BASE_URL": "https://example.test",
        "ANTHROPIC_AUTH_TOKEN": "sk-secret",
    }


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_account_an_agent_runs_as_is_the_first_thing_asked_about_it(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """It decides which credentials the turns run under, which is no side question at all.

    So it is a row of the agent's own, under the CLI whose accounts they are -- an account
    being one backend's -- and above the model, which is the account's to name.
    """
    _account()
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        await opens(app, driver, "provider")
        await until(lambda: isinstance(app.screen, Accounts), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        # This machine's own first, which is what every agent ran as before there were any.
        assert rows(app) == ["", "deepseek"]
        assert _ACT_ADD in bar(app)

        await driver.press("down", "enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        listing = app.screen.query_one("#choices", OptionList)
        assert "deepseek" in str(
            listing.get_option_at_index(rows(app).index("provider")).prompt
        )

        await keeps(app, driver)
        await keeps(app, driver)
        await driver.pause()
        # And on the line above the prompt, beside what it runs.
        assert "deepseek" in str(app.query_one("#above", Static).content)

    chosen = Runs("claude/claude-opus-5:high", "deepseek")
    assert app._models == {"assistant": chosen}
    assert app.settings.agents(app._flow_named) == {"assistant": chosen}
    # And what it may do between the two: nobody narrowed this one, so the line says what
    # that comes to rather than leaving a gap where a rung would be.
    assert reads(("builder",), [chosen]) == [
        "builder · claude/claude-opus-5:high · deepseek"
    ]


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_an_account_can_be_made_from_the_sheet_that_asks_for_one(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The moment somebody finds out they have no account is the moment to offer them one.

    So making one is a button of the question rather than a walk out of it, and what comes
    back is the account chosen: making one here is choosing it -- with the models that account
    runs already asked for, which is what makes the step after it answerable.
    """
    import hmz.coganchor.models

    asked: list[tuple[str, str]] = []

    def note(cli: str, provider: str = "", seconds: float = 0.0) -> tuple[Model, ...]:
        asked.append((cli, provider))
        return _kept(cli, provider)

    monkeypatch.setattr(hmz.coganchor.models, "ask", note)
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        await opens(app, driver, "provider")
        await until(lambda: isinstance(app.screen, Accounts), driver)
        # Nothing to choose but this machine's own, which is where somebody finds out.
        assert rows(app) == [""]
        assert _ACT_ADD in bar(app)

        await onto(app, driver, _ACT_ADD)
        await driver.press("enter")
        # Straight to the form, less the question of which CLI: it is the one the agent is on.
        await until(lambda: isinstance(app.screen, Signing), driver)
        assert rows(app)[0] == "way"
        await _chooses(app, driver, "way", "key")
        await _writes(app, driver, "name", *"mine")
        await _writes(app, driver, "ANTHROPIC_API_KEY", *"not-a-key")
        await _answers(app, driver)

        # Back to the agent, with the account made and given to it: making one here is
        # choosing it, so the row it was asked from is answered.
        await until(lambda: isinstance(app.screen, Agent), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(
            lambda: (
                "mine"
                in str(listing.get_option_at_index(rows(app).index("provider")).prompt)
            ),
            driver,
        )
        # And its CLI asked what it runs from here, without holding up the list it was
        # chosen on: what the model row offers is that account's.
        await until(lambda: ("claude", "mine") in asked, driver)
        await until(lambda: not cast("Agent", app.screen)._said, driver)
        await keeps(app, driver)
        await keeps(app, driver)
        await driver.pause()

    made = providers.find("claude", "mine")
    assert made is not None
    assert dict(made.env) == {"ANTHROPIC_API_KEY": "not-a-key"}
    assert app._models == {"assistant": Runs("claude/claude-opus-5:high", "mine")}
    # The backends installed here are asked as the interface opens, and an account as it
    # lands: an account is made in order to run turns as, and which models those turns may
    # name is the account's rather than this machine's.
    assert asked == [("claude", ""), ("claude", "mine")]


@pytest.mark.timeout(60)
async def test_walking_out_of_the_form_makes_nothing() -> None:
    """Esc off a form nothing was written into is the page again, with nothing written down."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await _adds(app, driver)
        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Providers), driver)
        await leaves(app, driver)

    assert providers.providers() == []


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_making_one_and_walking_out_of_it_changes_nothing(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """Esc off the making is the account question again, with nothing written down."""
    app = Humanize()
    was = None
    async with app.run_test() as driver:
        was = dict(app._models)
        await into_flows(app, driver)
        await into_agent(app, driver)
        await opens(app, driver, "provider")
        await until(lambda: isinstance(app.screen, Accounts), driver)
        await onto(app, driver, _ACT_ADD)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Signing), driver)
        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Accounts), driver)
        # And esc off the accounts is back on the agent, which was not changed by looking.
        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Agent), driver)
        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Providers | Agent) is False, driver)

    assert providers.providers("claude") == []
    assert app._models == was  # walking out changed nothing at all


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_cli_with_no_accounts_says_where_they_come_from(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """A sheet holding one row that changes nothing has to say why it is the only one."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        await opens(app, driver, "provider")
        await until(lambda: isinstance(app.screen, Accounts), driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        said = str(app.screen.query_one("#tuning", Label).content)

        assert "claude has no saved accounts yet" in said
        # And offers one without sending anybody out of the question: the moment somebody
        # finds out they have none is the moment to be offered one. A button under the list
        # rather than a key, a key said at the bottom of the screen being one to go looking
        # for -- and the row of keys says tab reaches it from the list.
        sheet = cast("Accounts", app.screen)
        assert _ACT_ADD in bar(app)
        assert Key("tab", "actions") in sheet._keyed
        await onto(app, driver, _ACT_ADD)
        assert Key("enter", "add") in sheet._keyed


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_first_row_leaves_the_agent_running_as_this_machine(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """Which is what every agent ran as before there were any accounts to choose between."""
    _account()
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        await opens(app, driver, "provider")
        await until(lambda: isinstance(app.screen, Accounts), driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )

        await driver.press("down")  # walked to the account and then off it again
        await driver.press("up")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        listing = app.screen.query_one("#choices", OptionList)
        assert "as local" in str(
            listing.get_option_at_index(rows(app).index("provider")).prompt
        )

        await keeps(app, driver)
        await keeps(app, driver)

    assert app._models == {"assistant": Runs("claude/claude-opus-5:high")}


@pytest.mark.timeout(60)
async def test_walking_out_of_a_form_written_into_asks_and_loses_nothing() -> None:
    """What was typed took typing, so walking out of it asks -- and discarding keeps nothing."""
    _account()
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")

        await _adds(app, driver)
        await _writes(app, driver, "name", *"other")
        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Confirms), driver)
        await driver.press("down", "enter")  # discard
        # Back to the accounts, which is where making one was asked for.
        await until(lambda: isinstance(app.screen, Providers), driver)
        await leaves(app, driver)

    assert [one.name for one in providers.providers()] == ["deepseek"]


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.coganchor.providers.login.sign_in", return_value=0)
async def test_an_account_is_signed_in_again_by_the_way_it_was_made_with(
    signed_in: unittest.mock.MagicMock,
) -> None:
    """A token expires and a subscription is signed out of, and neither remakes the account."""
    providers.add("claude", "deepseek", way="login")
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )

        await _doing(app, driver, "signs-in")
        await until(lambda: signed_in.call_count == 1, driver)
        await until(lambda: isinstance(app.screen, Providers), driver)
        await leaves(app, driver)
        said = transcript(app)

    assert "claude/deepseek is signed in" in said


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.coganchor.providers.login.sign_in", return_value=0)
async def test_signing_in_again_asks_only_what_is_not_written_down(
    signed_in: unittest.mock.MagicMock,
) -> None:
    """A key the CLI keeps in its own store was never kept here, so it is asked for again."""
    providers.add("codex", "work", way="key")
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )

        await _doing(app, driver, "signs-in")
        await until(lambda: isinstance(app.screen, Signing), driver)
        form = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(form.options), driver)
        # And only that: what to call an account that already has a name is not a question,
        # and nor is where else it goes.
        assert rows(app) == ["OPENAI_API_KEY"]
        assert bar(app) == [_ACT_DONE]

        await _writes(app, driver, "OPENAI_API_KEY", *"sk-1")
        await _answers(app, driver)
        await until(lambda: signed_in.call_count == 1, driver)
        await until(lambda: isinstance(app.screen, Providers), driver)
        await leaves(app, driver)

    assert signed_in.call_args.args[2] == {"OPENAI_API_KEY": "sk-1"}


@pytest.mark.timeout(60)
async def test_correcting_what_one_holds_is_held_until_the_menu_is_saved() -> None:
    """Correcting one is the way in it was made by, asked again with what it holds."""
    providers.add("codex", "work", way="key", env={"OPENAI_API_KEY": "old"})
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )

        await _doing(app, driver, "corrects")
        await until(lambda: isinstance(app.screen, Signing), driver)
        form = app.screen.query_one("#choices", OptionList)
        # Only what the way asks, and a secret starts blank: it is on its way into a
        # credential store, and nothing reads one back out to be corrected in place.
        assert rows(app)[0] == "OPENAI_API_KEY"
        assert "old" not in str(form.get_option_at_index(0).prompt)
        assert "leave blank to keep current value" in str(
            form.get_option_at_index(0).prompt
        )

        await _writes(app, driver, "OPENAI_API_KEY", *"new")
        await _answers(app, driver)
        await until(lambda: isinstance(app.screen, Providers), driver)
        await until(
            lambda: "will be updated when this menu is saved" in _under(app), driver
        )
        # Held: what is on the disk is still what was there.
        held = providers.find("codex", "work")
        assert held is not None
        assert dict(held.env) == {"OPENAI_API_KEY": "old"}

        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Providers), driver)

    corrected = providers.find("codex", "work")
    assert corrected is not None
    assert dict(corrected.env) == {"OPENAI_API_KEY": "new"}


@pytest.mark.timeout(60)
async def test_an_account_corrected_is_asked_what_it_runs_once_it_is_saved() -> None:
    """A gateway moved is a list of models from the one it left until it is asked again."""
    providers.add("codex", "work", way="key", env={"OPENAI_API_KEY": "old"})
    app = Humanize()
    with unittest.mock.patch(
        "hmz.tui.app.asks", new=unittest.mock.AsyncMock(return_value=(3, ""))
    ) as asked:
        async with app.run_test() as driver:
            await into_settings(app, driver, "accounts")
            await until(
                lambda: bool(app.screen.query_one("#choices", OptionList).options),
                driver,
            )
            await _doing(app, driver, "corrects")
            await _writes(app, driver, "OPENAI_API_KEY", *"new")
            await _answers(app, driver)
            await until(lambda: isinstance(app.screen, Providers), driver)
            # Not while it is only held: the account still signs in where it did.
            asked.assert_not_called()

            await keeps(app, driver)
            await until(
                lambda: "codex supports 3 models as work" in transcript(app), driver
            )

    asked.assert_awaited_once_with("codex", "work")


@pytest.mark.timeout(60)
async def test_a_backspace_trims_a_name_written_in_rather_than_clearing_it() -> None:
    """The first letter replaces a guess; a backspace is somebody correcting it."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        form = await _adds(app, driver)
        await _chooses(app, driver, "cli", "codex")
        await _chooses(app, driver, "way", "gateway")
        assert form._typed_in["name"] == "gateway"

        await onto(app, driver, "name")
        await driver.press("backspace", "y", "s")
        await driver.press("enter")
        await driver.pause()
        assert form._typed_in["name"] == "gateways"

        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Confirms | Providers), driver)


@pytest.mark.timeout(60)
async def test_a_secret_left_blank_while_correcting_keeps_the_one_it_has() -> None:
    """Correcting the endpoint of a gateway is not a reason to type its key again."""
    providers.add(
        "claude",
        "gate",
        way="anthropic-gateway",
        env={
            "ANTHROPIC_AUTH_TOKEN": "sk-kept",
            "ANTHROPIC_BASE_URL": "https://old.test",
        },
    )
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await until(lambda: "claude/gate" in ids(app), driver)
        await onto(app, driver, "claude/gate")

        await _doing(app, driver, "corrects")
        await until(lambda: isinstance(app.screen, Signing), driver)
        form = cast("Signing", app.screen)
        # What is not a secret is read back to be corrected where it stands.
        assert form._typed_in["ANTHROPIC_BASE_URL"] == "https://old.test"
        await onto(app, driver, "ANTHROPIC_BASE_URL")
        await driver.press("enter", *["backspace"] * len("old.test"), *"new.test")
        await driver.press("enter")
        await driver.pause()
        await _answers(app, driver)
        await until(lambda: isinstance(app.screen, Providers), driver)
        await keeps(app, driver)

    corrected = providers.find("claude", "gate")
    assert corrected is not None
    assert dict(corrected.env) == {
        "ANTHROPIC_AUTH_TOKEN": "sk-kept",
        "ANTHROPIC_BASE_URL": "https://new.test",
    }


@pytest.mark.timeout(60)
async def test_taking_an_account_away_says_what_went_with_it() -> None:
    """Credentials are what is going, and a line that said less would be understating it."""
    _account()
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )

        # From inside what there is to do with it, and held until the menu is saved.
        await _doing(app, driver, _ACT_REMOVE)
        await until(
            lambda: (
                "when this menu is saved"
                in str(app.screen.query_one("#tuning", Label).content)
            ),
            driver,
        )
        assert providers.find("claude", "deepseek") is not None

        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Providers), driver)
        said = transcript(app)

    assert "claude/deepseek and its credentials were removed" in said
    assert providers.find("claude", "deepseek") is None


@pytest.mark.timeout(60)
async def test_an_account_held_to_go_is_offered_the_way_back() -> None:
    """Nothing has happened yet, so the button that marked it is the one that unmarks it."""
    _account()
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await _doing(app, driver, _ACT_REMOVE)
        await until(lambda: isinstance(app.screen, Providers), driver)
        assert "will be removed" in _drawn(app)

        # Open again and the button says the opposite, rather than offering the same thing.
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Account), driver)
        await until(lambda: _ACT_REMOVE in bar(app), driver)
        undo = app.screen.query_one(f"#act-{_ACT_REMOVE}", Button)
        assert str(undo.label) == "Cancel removal"
        await onto(app, driver, _ACT_REMOVE)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Providers), driver)
        await until(lambda: "deepseek stays" in _under(app), driver)

        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Providers), driver)

    assert providers.find("claude", "deepseek") is not None


@pytest.mark.timeout(60)
async def test_an_account_held_to_go_stays_where_the_menu_is_not_saved() -> None:
    """It is a draft until the menu is saved, and credentials are not thrown away on a walk."""
    _account()
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await _doing(app, driver, _ACT_REMOVE)
        await until(lambda: isinstance(app.screen, Providers), driver)

        await drops(app, driver)
        await until(lambda: not isinstance(app.screen, Providers), driver)

    assert providers.find("claude", "deepseek") is not None


@pytest.mark.timeout(60)
async def test_the_key_that_used_to_take_an_account_away_takes_nothing_away() -> None:
    """Asking twice was for a key that acted on the spot, and there is no such key here now."""
    _account()
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )

        await driver.press("d")
        await driver.press("d")
        await driver.pause()

        assert "press d again" not in _under(app)
        assert "will be removed" not in _drawn(app)
        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Providers), driver)

    assert providers.find("claude", "deepseek") is not None


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_an_agent_told_to_run_as_nobody_is_a_line_to_correct(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    hosting: None,
) -> None:
    """An agent that cannot find its account must not quietly run as whoever started it."""
    app = Humanize()
    async with app.run_test() as driver:
        set_up(app, "chat", {"assistant": Runs("claude/claude-opus-5:max", "nonesuch")})
        await driver.press(*"go")
        await driver.press("enter")
        await until(lambda: "nonesuch" in transcript(app), driver)
        await until(lambda: app._run is None, driver)
        said = transcript(app)

    assert "hmz:" in said
    # Said at the prompt, rather than raised out of a thread.
    assert "Traceback" not in said


def test_what_an_agent_runs_as_is_kept_and_read_back(tmp_path: Path) -> None:
    """As `-a` writes it: the account after an `@`, and nothing where there is none."""
    kept = Settings(tmp_path)
    kept.remember(
        "rlar",
        {"actor": Runs("claude/m:high", "deepseek"), "reviewer": Runs("codex/n:low")},
    )

    assert Settings(tmp_path).agents("rlar") == {
        "actor": Runs("claude/m:high", "deepseek"),
        "reviewer": Runs("codex/n:low"),
    }
    held = settings.read()
    agents = held["workspaces"][str(tmp_path.resolve())]["flows"]["rlar"]["agents"]
    assert agents["actor"] == "claude@deepseek/m:high"
    # An agent nobody named one for says nothing -- and reads back as this machine's own.
    assert agents["reviewer"] == "codex/n:low"


@pytest.mark.timeout(60)
async def test_the_account_this_machine_is_signed_into_is_a_row_of_its_own() -> None:
    """It is what an agent nobody gave an account runs as, read beside the ones made."""
    providers.add("codex", "work", way="key", env={"OPENAI_API_KEY": "k"})
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)

        # What is done about the list is the bar under it, saving last, and the one
        # signed in here last in its CLI's group: what somebody came here to read is the
        # accounts they made.
        assert [str(one.id) for one in listing.options if one.id] == [
            "=codex/work",
            "=codex/",
        ]
        assert bar(app) == [_ACT_ADD, _ACT_SPEAKS, _ACT_SEARCH, _ACT_SAVE]
        mine = str(listing.get_option("=codex/").prompt)
        assert "as local" in mine
        assert "signed in on this machine" in mine

        await driver.press("down")  # onto it, from the first account
        await driver.pause()

        # Correcting it, signing it in and taking it away are not offered at all, with the
        # reason said where they would have been: humanize did not make that account and
        # keeps nothing for it. And where a turn under it goes when it fails is not an
        # account's to say at all, so there is no row left -- and no button either.
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Account), driver)
        await until(lambda: "keeps no credentials for it" in _under(app), driver)
        assert ids(app) == []
        assert bar(app) == []
        assert "remove it" in _under(app)
        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Providers), driver)


@pytest.mark.timeout(60)
async def test_an_account_offers_nothing_about_where_a_failed_turn_goes() -> None:
    """That is the fallback page's, between places; an account no longer fails over."""
    providers.add("codex", "work", way="key", env={"OPENAI_API_KEY": "k"})
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await until(lambda: "codex/work" in ids(app), driver)
        await onto(app, driver, "codex/work")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Account), driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )

        assert "falls" not in ids(app)
        assert "fails over" not in _drawn(app)


@pytest.mark.timeout(60)
async def test_a_cli_of_your_own_is_written_down_from_a_button_of_its_own() -> None:
    """Beside the button that adds an account, since what it adds is a backend, not one."""
    from hmz.coganchor import backends
    from hmz.tui.pick import Speaks

    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")

        await onto(app, driver, _ACT_SPEAKS)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Speaks), driver)

        await changes(app, driver, "command", *"my-agent --acp")
        await _answers(app, driver)
        await until(lambda: isinstance(app.screen, Providers), driver)
        assert "added as a backend" in _under(app)
        await leaves(app, driver)

    assert backends.speaking()["my-agent"] == ("my-agent", "--acp")


@pytest.mark.timeout(60)
async def test_an_account_several_backends_could_run_asks_which_to_write_it_down_for() -> (
    None
):
    """One configuration, several CLIs: an Anthropic key is an Anthropic key.

    Asked on the form it is made on, since making the same key four times by hand is four
    places to correct when it is rotated -- a row apiece, on for the ones installed here.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")

        form = await _adds(app, driver)
        await _chooses(app, driver, "way", "key")
        # Straight on to the one thing there is to type, past the name written for it.
        assert form.under() == "ANTHROPIC_API_KEY"
        await _writes(app, driver, "name", *"shared")
        await _writes(app, driver, "ANTHROPIC_API_KEY", *"sk-shared")

        # And then the question this is about: which of the others hold it too.
        assert [one for one in rows(app) if one.startswith("also:")] == [
            "also:pi",
            "also:qwen",
            "also:opencode",
            "also:mimo",
        ]
        # Nothing is installed in this suite, so nothing starts switched on.
        assert not any(form._also(one) for one in ("pi", "qwen", "opencode", "mimo"))
        await nexts(app, driver, "also:opencode")
        # Said where answering it is: by the button that answers it.
        assert "for opencode too" in str(
            app.screen.query_one(f"#act-{_ACT_DONE}", Button).tooltip
        )
        await _answers(app, driver)

        await until(lambda: isinstance(app.screen, Providers), driver)
        await until(lambda: "also saved for opencode" in _under(app), driver)
        await leaves(app, driver)

    held = providers.find("opencode", "shared")
    assert held is not None
    assert dict(held.env) == {"ANTHROPIC_API_KEY": "sk-shared"}
    # And only the one that was switched on.
    assert providers.find("pi", "shared") is None


@pytest.mark.timeout(60)
async def test_correcting_one_corrects_the_copies_it_was_made_for() -> None:
    """Which is the point of copying it: a key rotated is a key rotated everywhere, said once.

    The copies start switched on where a copy is: those are the ones holding the old key.
    """
    one = providers.add("claude", "shared", "key", {"ANTHROPIC_API_KEY": "old"})
    providers.copies(one, "opencode")
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await until(lambda: "claude/shared" in ids(app), driver)
        await onto(app, driver, "claude/shared")

        await _doing(app, driver, "corrects")
        await until(lambda: isinstance(app.screen, Signing), driver)
        form = cast("Signing", app.screen)
        assert form._also("opencode")
        assert not form._also("pi")
        await _writes(app, driver, "ANTHROPIC_API_KEY", *"new")
        await _answers(app, driver)

        await until(lambda: isinstance(app.screen, Providers), driver)
        # Held until the menu is saved, as every other correction is.
        held = providers.find("opencode", "shared")
        assert held is not None
        assert dict(held.env) == {"ANTHROPIC_API_KEY": "old"}

        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Providers), driver)

    for cli_name in ("claude", "opencode"):
        rotated = providers.find(cli_name, "shared")
        assert rotated is not None
        assert dict(rotated.env) == {"ANTHROPIC_API_KEY": "new"}


@pytest.mark.timeout(60)
async def test_an_account_that_travels_nowhere_is_not_asked_about() -> None:
    """A subscription is never asked about, and one left switched off goes nowhere."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await _adds(app, driver)
        # A login writes the CLI's own store, which nothing else reads.
        assert not [one for one in rows(app) if one.startswith("also:")]

        await _chooses(app, driver, "cli", "dsh")
        # DeepSeek's key is read by pi and opencode, so those are asked about -- off, since
        # neither is installed here -- and left off.
        assert [one for one in rows(app) if one.startswith("also:")] == [
            "also:pi",
            "also:opencode",
        ]
        await _writes(app, driver, "name", *"only")
        await _writes(app, driver, "DEEPSEEK_API_KEY", *"sk-only")
        await _answers(app, driver)
        await until(lambda: isinstance(app.screen, Providers), driver)
        await leaves(app, driver)

    assert providers.find("dsh", "only") is not None
    assert providers.find("pi", "only") is None


@pytest.mark.timeout(60)
async def test_the_name_written_for_an_account_is_one_nothing_is_called() -> None:
    """The way in, unless an account of any CLI is called that: a copy must not write over one."""
    providers.add("pi", "key", way="env", env={"ANTHROPIC_API_KEY": "theirs"})
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        form = await _adds(app, driver)
        await _chooses(app, driver, "way", "key")

        assert form._typed_in["name"] == "key-2"
        # And typing into it replaces what was written for it, rather than landing after it.
        await onto(app, driver, "name")
        await driver.press(*"work")
        await driver.pause()
        assert form._typed_in["name"] == "work"


@pytest.mark.timeout(60)
async def test_typing_on_a_row_of_the_form_writes_it_and_enter_moves_on() -> None:
    """A form of questions takes letters as answers: no enter to begin each one."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        form = await _adds(app, driver)
        await _chooses(app, driver, "way", "key")
        assert form.under() == "ANTHROPIC_API_KEY"
        assert Key("type", "to edit") in form._keyed

        await driver.press(*"sk-typed")
        await driver.pause()
        assert form._editing == "ANTHROPIC_API_KEY"
        await driver.press("enter")
        await driver.pause()

        # Kept, and on to what is left, which is nothing but answering it: the focus on the
        # button that does, and the cursor left on the question just answered.
        assert form._typed_in["ANTHROPIC_API_KEY"] == "sk-typed"
        assert form.focused is form.query_one(f"#act-{_ACT_DONE}", Button)
        assert form.under() == "ANTHROPIC_API_KEY"
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Providers), driver)

    made = providers.find("claude", "key")
    assert made is not None
    assert dict(made.env) == {"ANTHROPIC_API_KEY": "sk-typed"}


@pytest.mark.timeout(60)
async def test_what_a_new_account_runs_is_asked_after_it_lands_and_said(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Asked without holding the page up, and what came of it -- and why -- said under it."""
    import threading

    import hmz.coganchor.models

    let_go = threading.Event()

    def refuses(
        cli: str, provider: str = "", seconds: float = 0.0
    ) -> tuple[Model, ...]:
        let_go.wait(10)
        message = f"{cli} exited 1: \x1b[31mnot signed in\x1b[0m"
        raise RuntimeError(message)

    monkeypatch.setattr(hmz.coganchor.models, "ask", refuses)
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await _adds(app, driver)
        await _chooses(app, driver, "way", "key")
        await _writes(app, driver, "ANTHROPIC_API_KEY", *"sk-x")
        await _answers(app, driver)

        await until(lambda: isinstance(app.screen, Providers), driver)
        await until(
            lambda: "checking available models for claude as key" in _under(app),
            driver,
        )
        assert "checking models" in _drawn(app)

        # Read another page meanwhile: what it said lands on the page it was asked from.
        sheet = app.screen
        assert isinstance(sheet, Adjusts)
        await driver.press("escape")
        await until(lambda: sheet._home, driver)
        await driver.press("down", "enter")
        await until(
            lambda: sheet._tab == PAGES.index("runtimes") and not sheet._home, driver
        )
        let_go.set()
        await until(lambda: not sheet._asking, driver)
        assert "could not get models" not in _under(app)
        await driver.press("escape")
        await until(lambda: sheet._home, driver)
        await driver.press("up", "enter")
        await until(lambda: "could not get models" in _under(app), driver)

        # The reason, as words rather than a terminal's colours.
        assert "not signed in" in _under(app)
        assert "\x1b" not in _under(app)
        assert "checking models" not in _drawn(app)


@pytest.mark.timeout(60)
async def test_variables_typed_for_one_way_are_not_written_down_for_another() -> None:
    """What is on no row of the form when it is answered is not part of the answer."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "accounts")
        await _adds(app, driver)
        await _chooses(app, driver, "way", "env")
        await _writes(app, driver, " ", *"FOO=bar")
        await _chooses(app, driver, "way", "key")
        assert " " not in rows(app)
        await _writes(app, driver, "ANTHROPIC_API_KEY", *"sk-only")
        await _answers(app, driver)
        await until(lambda: isinstance(app.screen, Providers), driver)

    made = providers.find("claude", "key")
    assert made is not None
    assert dict(made.env) == {"ANTHROPIC_API_KEY": "sk-only"}

"""The fallback page of `/settings`: where a turn goes when its place cannot take it.

A place is a CLI, an account and a model, and a chain is written from one of them to the
places tried after it, in order. How many times over a failed turn is taken again before the
chain is walked is written there too, both being answers to the one thing that went wrong --
and all of it on one form.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual.content import Content
from textual.widgets import Label, OptionList

from hmz.coganchor import fallbacks
from hmz.coganchor.backends import Model
from hmz.tui import Humanize
from hmz.tui.pick import (
    _ACT_ADD,
    _ACT_DONE,
    _ACT_REMOVE,
    _ACT_SAVE,
    _ACT_SEARCH,
    Confirms,
    Failing,
    Fallbacks,
    Places,
)
from tests.integration.tui.test_app import (
    bar,
    drops,
    ids,
    into_settings,
    keeps,
    nexts,
    onto,
    rows,
    under,
)
from tests.tui.fixtures import until

if TYPE_CHECKING:
    from textual.pilot import Pilot

#: Two installed CLIs, so that choosing a place has something to choose between.
INSTALLED = {
    "claude": (
        Model("claude-opus-5", ("max", "high")),
        Model("claude-sonnet-5", ("max", "high")),
    ),
    "codex": (Model("gpt-5.6-sol", ("xhigh", "high")),),
}


def _under(app: Humanize) -> str:
    """What is said under the list, which is where a menu reports itself."""
    return str(app.screen.query_one("#tuning", Label).content)


def _says(app: Humanize, held: str) -> str:
    """What one row of the sheet on top says, as words.

    Without the colours, and with the lines a long row wraps onto run back together: a row
    says what it says whatever width the screen it was laid out across was.

    Args:
      app: The interface.
      held: The row, by the id it was put up under.
    """
    prompt = app.screen.query_one("#choices", OptionList).get_option(f"={held}").prompt
    return " ".join(Content.from_markup(str(prompt)).plain.split())


def _done(app: Humanize) -> bool:
    """Whether the focus is on the button that answers the form on top."""
    return app.screen.focused is app.screen.query_one(f"#act-{_ACT_DONE}")


async def _opens(app: Humanize, driver: Pilot[None]) -> None:
    """Opens the fallback page of `/settings` and waits for it to be up."""
    await into_settings(app, driver, "fallback")


async def _place(app: Humanize, driver: Pilot[None], place: str) -> None:
    """Chooses one place out of the one list of them, from the row under the cursor.

    Args:
      app: The interface.
      driver: What is pumping it.
      place: The place, as a step names it.
    """
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Places), driver)
    await until(lambda: place in rows(app), driver)
    await onto(app, driver, place)
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Failing), driver)


async def _step(app: Humanize, driver: Pilot[None]) -> Failing:
    """Opens the form of the step under the cursor, and waits for its rows."""
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Failing), driver)
    await until(
        lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
    )
    sheet = app.screen
    assert isinstance(sheet, Failing)
    return sheet


@pytest.fixture(autouse=True)
def _installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two CLIs here, so the list of places has something to offer."""
    import hmz.tui.app

    monkeypatch.setattr(hmz.tui.app, "installed", lambda: dict(INSTALLED))
    monkeypatch.setattr(hmz.tui.app, "installable", dict)


@pytest.mark.timeout(60)
async def test_the_menu_is_the_steps_between_places() -> None:
    """A place is a CLI, an account and a model, and nothing else is asked."""
    fallbacks.points("claude/claude-opus-5", ["codex/gpt-5.6-sol"])
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )

        # The steps are the rows; adding one, searching and saving are the buttons under
        # them, saving last.
        assert rows(app) == ["claude/claude-opus-5"]
        assert bar(app) == [_ACT_ADD, _ACT_SEARCH, _ACT_SAVE]
        assert "falls back to codex/gpt-5.6-sol" in _says(app, "claude/claude-opus-5")
        # And the cursor on the step, which is what turning to the page was for.
        assert under(app) == "claude/claude-opus-5"


@pytest.mark.timeout(60)
async def test_an_empty_menu_opens_on_the_button_that_writes_one_down() -> None:
    """An empty list with nothing to do about it reads as a feature that does not work."""
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await driver.pause()

        # The button that writes one down, which is where to start.
        assert rows(app) == []
        assert bar(app) == [_ACT_ADD, _ACT_SEARCH, _ACT_SAVE]
        # The focus is on the button that writes the first one down.
        assert app.screen.focused is app.screen.query_one("#act-add")
        assert "no fallback rules configured yet" in _under(app)


@pytest.mark.timeout(90)
async def test_a_step_is_one_form_of_two_places_and_is_held_until_the_menu_is_saved() -> (
    None
):
    """The place that cannot run, then the place that takes its turns, on one form."""
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await onto(app, driver, _ACT_ADD)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Failing), driver)
        # The two places, and how it is tried again, and nothing else -- and the button
        # that keeps it, which is the only one on a step not yet written.
        assert rows(app) == ["fails", "goes0", "tries", "policy", "for"]
        assert bar(app) == [_ACT_DONE]

        await _place(app, driver, "claude/claude-opus-5")  # the one that cannot run
        # And straight on to the next thing still to say, which is where it goes.
        assert under(app) == "goes0"
        await _place(app, driver, "codex/gpt-5.6-sol")  # and the one that takes over
        # With nothing left to say, the button that keeps it.
        await until(lambda: _done(app), driver)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Fallbacks), driver)

        # Said, and nothing on disk until the menu is saved.
        assert rows(app) == ["claude/claude-opus-5"]
        assert bar(app) == [_ACT_ADD, _ACT_SEARCH, _ACT_SAVE]
        assert under(app) == "claude/claude-opus-5"
        assert fallbacks.falls() == []

        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Fallbacks), driver)

    assert fallbacks.falls() == [
        fallbacks.Falls("claude/claude-opus-5", ("codex/gpt-5.6-sol",))
    ]


@pytest.mark.timeout(90)
async def test_a_chain_is_added_to_reordered_and_taken_from_on_its_rows() -> None:
    """Each place on the chain is a row; the row after the last adds one to the end."""
    fallbacks.points("claude/claude-opus-5", ["codex/gpt-5.6-sol"])
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        sheet = await _step(app, driver)
        assert rows(app) == ["goes0", "goes1", "tries", "policy", "for"]
        assert bar(app) == [_ACT_REMOVE, _ACT_DONE]

        # Added at the end, from the row after the last.
        await onto(app, driver, "goes1")
        await _place(app, driver, "claude/claude-sonnet-5")
        assert sheet._chain == ["codex/gpt-5.6-sol", "claude/claude-sonnet-5"]
        assert "goes2" in rows(app)

        # Put first by choosing it on the first row, which changes the two round.
        await onto(app, driver, "goes0")
        await _place(app, driver, "claude/claude-sonnet-5")
        assert sheet._chain == ["claude/claude-sonnet-5", "codex/gpt-5.6-sol"]

        await onto(app, driver, _ACT_DONE)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Fallbacks), driver)
        # Broken across lines where the row is narrower than the chain, so read as words.
        assert "falls back to claude/claude-sonnet-5, then codex/gpt-5.6-sol" in _says(
            app, "claude/claude-opus-5"
        )
        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Fallbacks), driver)

    assert fallbacks.chain("claude/claude-opus-5") == [
        "claude/claude-opus-5",
        "claude/claude-sonnet-5",
        "codex/gpt-5.6-sol",
    ]


@pytest.mark.timeout(90)
async def test_nowhere_on_a_row_of_the_chain_takes_that_place_off_it() -> None:
    fallbacks.points(
        "claude/claude-opus-5", ["codex/gpt-5.6-sol", "claude/claude-sonnet-5"]
    )
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        sheet = await _step(app, driver)

        await onto(app, driver, "goes0")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Places), driver)
        await until(lambda: "" in rows(app), driver)
        await onto(app, driver, "")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Failing), driver)

        assert sheet._chain == ["claude/claude-sonnet-5"]
        await onto(app, driver, _ACT_DONE)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Fallbacks), driver)
        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Fallbacks), driver)

    assert fallbacks.tried("claude/claude-opus-5").to == ("claude/claude-sonnet-5",)


@pytest.mark.timeout(90)
async def test_a_place_is_not_offered_as_where_it_falls_back_to() -> None:
    """A step that pointed at itself would be a turn that never ran out of places to go."""
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await onto(app, driver, _ACT_ADD)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Failing), driver)
        await _place(app, driver, "claude/claude-opus-5")

        await driver.press("enter")  # on `goes0`, where the cursor went
        await until(lambda: isinstance(app.screen, Places), driver)
        await until(lambda: "codex/gpt-5.6-sol" in rows(app), driver)
        assert "claude/claude-opus-5" not in rows(app)
        # Falling back nowhere is one of the answers, first.
        assert rows(app)[0] == ""


@pytest.mark.timeout(60)
async def test_a_step_that_says_nothing_is_refused_where_it_was_written() -> None:
    """A place that falls back nowhere and is tried once is a place nobody said anything of."""
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await onto(app, driver, _ACT_ADD)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Failing), driver)
        await _place(app, driver, "claude/claude-opus-5")
        await onto(app, driver, _ACT_DONE)
        await driver.press("enter")
        await driver.pause()

        assert isinstance(app.screen, Failing)  # still asking, rather than gone
        assert "choose a fallback agent or set retries" in _under(app)


@pytest.mark.timeout(60)
async def test_a_step_is_taken_away_from_its_own_form() -> None:
    """Enter opens what a step is, and being rid of it is a button of that.

    Held until the menu is saved, like everything else the sheet is holding: what the row
    says is what lands, and nothing has landed while the menu is still up.
    """
    fallbacks.points("claude/claude-opus-5", ["codex/gpt-5.6-sol"])
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await _step(app, driver)
        # The place it is written against is what the form is about, not a row of it; and
        # being rid of it is what is done about the form, not one of its questions.
        assert rows(app) == ["goes0", "goes1", "tries", "policy", "for"]
        assert bar(app) == [_ACT_REMOVE, _ACT_DONE]
        await onto(app, driver, _ACT_REMOVE)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Fallbacks), driver)

        # Gone from the list, and nothing on disk until the menu is saved.
        assert rows(app) == []
        assert "has no fallback when this menu is saved" in _under(app)
        assert fallbacks.falls()

        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Fallbacks), driver)

    assert fallbacks.falls() == []


@pytest.mark.timeout(60)
async def test_walking_out_of_a_step_taken_away_lands_nothing() -> None:
    """It is a draft until the menu is saved, and a draft thrown away is a step left alone."""
    fallbacks.points("claude/claude-opus-5", ["codex/gpt-5.6-sol"])
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await _step(app, driver)
        await onto(app, driver, _ACT_REMOVE)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Fallbacks), driver)

        await drops(app, driver)
        await until(lambda: not isinstance(app.screen, Fallbacks), driver)

    assert fallbacks.falls() == [
        fallbacks.Falls("claude/claude-opus-5", ("codex/gpt-5.6-sol",))
    ]


@pytest.mark.timeout(60)
async def test_the_key_that_used_to_take_a_step_away_takes_nothing_away() -> None:
    """Asking twice was for a key that acted on the spot, and there is no such key here now."""
    fallbacks.points("claude/claude-opus-5", ["codex/gpt-5.6-sol"])
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await driver.press("d")
        await driver.press("d")
        await driver.pause()

        assert "press d again" not in _under(app)
        assert rows(app) == ["claude/claude-opus-5"]
        assert bar(app) == [_ACT_ADD, _ACT_SEARCH, _ACT_SAVE]


@pytest.mark.timeout(90)
async def test_how_often_a_failed_turn_is_taken_again_is_on_the_same_form() -> None:
    """One thing went wrong, so one form says both what to try and where to go."""
    fallbacks.points("claude/claude-opus-5", ["codex/gpt-5.6-sol"])
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await _step(app, driver)

        await nexts(app, driver, "tries")  # one try beyond the first
        await nexts(app, driver, "policy")  # and the wait stepped on one
        await onto(app, driver, _ACT_DONE)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Fallbacks), driver)

        # Said, and held until the menu is saved.
        assert "1 retry" in _says(app, "claude/claude-opus-5")
        assert fallbacks.tried("claude/claude-opus-5").tries == 0

        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Fallbacks), driver)

    said = fallbacks.tried("claude/claude-opus-5")
    assert said.tries == 1
    assert said.policy == "fibonacci"
    assert said.to == ("codex/gpt-5.6-sol",)  # and where it goes is still where it goes


@pytest.mark.timeout(60)
async def test_leaving_a_step_being_written_asks_whether_to_keep_it() -> None:
    """A form holding something is a menu holding changes, and walking out of one asks."""
    fallbacks.points("claude/claude-opus-5", ["codex/gpt-5.6-sol"])
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await _step(app, driver)
        await nexts(app, driver, "tries")

        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Confirms), driver)
        await driver.press("enter")  # save, which is keeping the step as it now says
        await until(lambda: isinstance(app.screen, Fallbacks), driver)

        assert "1 retry" in _says(app, "claude/claude-opus-5")


@pytest.mark.timeout(60)
async def test_keeping_the_last_rung_moves_on_to_done_and_not_to_taking_it_away() -> (
    None
):
    """Enter twice over the last question must not be enter on the button that removes it."""
    fallbacks.points("claude/claude-opus-5", ["codex/gpt-5.6-sol"])
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await _step(app, driver)
        await nexts(app, driver, "for")

        # The focus on the button that keeps it, and the cursor left on the question.
        assert _done(app)
        assert under(app) == "for"


@pytest.mark.timeout(90)
async def test_a_step_added_for_a_place_that_has_one_starts_from_it() -> None:
    """Rather than quietly writing over how it is tried again with nothing."""
    fallbacks.points("claude/claude-opus-5", ["codex/gpt-5.6-sol"])
    fallbacks.retrying("claude/claude-opus-5", 3, "linear", 300.0)
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await onto(app, driver, _ACT_ADD)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Failing), driver)
        await _place(app, driver, "claude/claude-opus-5")

        sheet = app.screen
        assert isinstance(sheet, Failing)
        assert sheet._chain == ["codex/gpt-5.6-sol"]
        assert sheet._typed_in["tries"] == "3"
        assert "already has a fallback rule" in _under(app)
        await onto(app, driver, _ACT_DONE)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Fallbacks), driver)
        await keeps(app, driver)

    said = fallbacks.tried("claude/claude-opus-5")
    assert (said.tries, said.policy, said.timeout) == (3, "linear", 300.0)


@pytest.mark.timeout(60)
async def test_choosing_an_account_that_has_not_said_what_it_runs_asks_and_stays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Asked, and the list stays up for the place to be chosen once it has said."""
    asked: list[tuple[str, str]] = []

    def asks(cli: str, account: str) -> None:
        asked.append((cli, account))

    app = Humanize()
    async with app.run_test() as driver:
        sheet = Places({"claude": ()}, "Select the agent that fails")
        monkeypatch.setattr(sheet, "_asks", asks)
        answered: list[str | None] = []
        app.push_screen(sheet, callback=answered.append)
        await until(lambda: app.screen is sheet, driver)
        await until(
            lambda: bool(sheet.query("#choices")) and len(rows(app)) == 1, driver
        )
        await driver.press("enter")
        await driver.pause()

        assert asked == [("claude", "")]
        assert app.screen is sheet
        assert answered == []


@pytest.mark.timeout(60)
async def test_a_search_for_falling_back_nowhere_lands_on_it() -> None:
    """`nowhere` answers with nothing, which a search must still be able to land on."""
    app = Humanize()
    async with app.run_test() as driver:
        sheet = Places(INSTALLED, "Select the fallback agent", nowhere=True)
        app.push_screen(sheet)
        await until(lambda: app.screen is sheet, driver)
        await until(lambda: bool(sheet.query("#choices")) and "" in rows(app), driver)
        await until(lambda: _ACT_SEARCH in bar(app), driver)
        await driver.press("slash", *"nowh")
        await driver.pause()

        # Found, and the cursor on it: an answer of nothing is a row like any other.
        assert ids(app) == [""]
        assert sheet.query_one("#choices", OptionList).highlighted == 0
        assert under(app) == ""

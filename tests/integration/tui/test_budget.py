"""What a run of a flow may spend, set from the menu that sets everything else up.

A row on the page the flow's roles are on, because it is a setting of the run rather than of
the flow. What is checked is that the row says what the run is held to without being opened,
that what is set there is written down beside what the flow was set up with and read back,
and that a flow is not saved until a run of it is given one -- except `chat`, the flow
humanize ships, which is a conversation and stops when the person does.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, cast

import pytest
from textual.widgets import Label, OptionList

from hmz.coganchor.backends import Model
from hmz.flows import Budget
from hmz.runtime.kept import Runs
from hmz.runtime.settings import Settings
from hmz.tui import Humanize
from hmz.tui.pick import _BUDGET, _DONE, _SAVE, Configures, Flows, budget_of
from tests.integration.tui.test_app import changes, onto, opens, picks, rows
from tests.stubs import written
from tests.tui.fixtures import until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: One backend, so that the menu has something to set an agent up as and can be saved.
_INSTALLED = {"claude": (Model("m", ("high",)),)}

#: A flow like most: one agent, and a run of it is given a budget.
QUIET = """
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams, flow


class Agents(AgentCollection):
    worker: Agent


@flow(agents=Agents, envs=EnvCollection, params=FlowParams)
async def quiet(task: str, *, agents: Agents, envs: EnvCollection, params: FlowParams,
                ctx: FlowContext) -> None:
    pass
"""


@pytest.fixture
def flows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts the flow where this project's own would be, with a backend to run it."""
    import hmz.tui.app
    import hmz.tui.pick

    monkeypatch.setattr(hmz.tui.app, "installed", lambda: dict(_INSTALLED))
    monkeypatch.setattr(hmz.tui.pick, "installed", lambda: dict(_INSTALLED))
    where = tmp_path / ".hmz" / "flows"
    where.mkdir(parents=True)
    written(where, "quiet", QUIET)
    return where


async def _into(app: Humanize, driver: Pilot[None], flow: str) -> Flows:
    """Opens the menu already inside one flow, which is where the budget row is."""
    await driver.press(*f"/flow {flow}")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Flows), driver)
    sheet = cast("Flows", app.screen)
    await until(lambda: sheet._inside, driver)
    return sheet


def _said(app: Humanize) -> str:
    """What the budget row says, which is what it is for: read without opening it."""
    listing = app.screen.query_one("#choices", OptionList)
    return str(listing.get_option_at_index(rows(app).index(_BUDGET)).prompt)


def _under(app: Humanize) -> str:
    """What the sheet on top says under its list."""
    return str(app.screen.query_one("#tuning", Label).content)


@pytest.mark.timeout(60)
async def test_the_row_says_what_the_run_is_held_to_without_being_opened(
    flows: Path,
) -> None:
    """A budget nobody can see without opening something is one nobody checks."""
    app = Humanize()
    async with app.run_test() as driver:
        await _into(app, driver, "local/quiet")

        assert rows(app) == ["0", _BUDGET, _SAVE]
        assert "none set" in _said(app)


@pytest.mark.timeout(60)
async def test_what_is_set_there_is_kept_and_read_back(
    flows: Path, tmp_path: Path
) -> None:
    """Beside what the flow was set up with, since it is a setting of the run beside it."""
    app = Humanize()
    async with app.run_test() as driver:
        await _into(app, driver, "local/quiet")
        await opens(app, driver, _BUDGET)
        await until(lambda: isinstance(app.screen, Configures), driver)
        sheet = cast("Configures", app.screen)

        # The four `-b` takes, and the row that sets them.
        assert rows(app) == ["duration", "cost", "output_tokens", "graceful", _DONE]

        await changes(app, driver, "duration", *"1h")  # written, as `-b` writes one
        await changes(app, driver, "cost", "1")  # the 0.0 there, selected, typed over
        assert (sheet._typed_in["duration"], sheet._typed_in["cost"]) == ("1h", "1")
        await onto(app, driver, _DONE)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)

        # Said on the row it came back to, so that it is read rather than remembered.
        assert "stops at 1h" in _said(app)
        assert "$1.00" in _said(app)

        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Flows), driver)

    # Written down under the flow, beside its agents, and read back by the next interface.
    assert Settings(tmp_path).budget("local/quiet") == {
        "duration": "PT1H",
        "cost": 1.0,
        "output_tokens": None,
        "graceful": True,
    }
    again = Humanize()
    assert again._budget == Budget(duration=datetime.timedelta(hours=1), cost=1)


@pytest.mark.timeout(60)
async def test_a_flow_is_not_saved_until_a_run_of_it_has_a_budget(
    flows: Path, tmp_path: Path
) -> None:
    """A run is given one before anything runs, and a menu saved without is a run refused."""
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _into(app, driver, "local/quiet")
        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await driver.pause()

        assert app.screen is sheet  # still here, holding everything it was holding
        assert "requires a budget" in _under(app)
        assert Settings(tmp_path).flow != "local/quiet"


@pytest.mark.timeout(60)
async def test_a_budget_that_limits_nothing_is_refused_where_it_is_typed(
    flows: Path,
) -> None:
    """At least one limit, which is what makes it a budget: none is refused on the sheet."""
    app = Humanize()
    async with app.run_test() as driver:
        await _into(app, driver, "local/quiet")
        await opens(app, driver, _BUDGET)
        await until(lambda: isinstance(app.screen, Configures), driver)

        await onto(app, driver, _DONE)
        await driver.press("enter")
        await driver.pause()

        assert isinstance(app.screen, Configures)
        assert "at least one" in _under(app)


@pytest.mark.timeout(60)
async def test_a_run_with_a_budget_saves_at_once(flows: Path, tmp_path: Path) -> None:
    """What was set is read back as the menu opens, and saving it asks nothing."""
    Settings(tmp_path).remember(
        "local/quiet",
        {"worker": Runs("claude/m:high")},
        budget={"duration": "PT2H"},
    )
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _into(app, driver, "local/quiet")
        assert "stops at 2h" in _said(app)

        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await until(lambda: app.screen is not sheet, driver)

    assert Settings(tmp_path).flow == "local/quiet"


@pytest.mark.timeout(60)
async def test_a_flow_run_without_the_menu_is_still_held_to_what_was_set(
    flows: Path, tmp_path: Path
) -> None:
    """`$flow <task>` runs a flow this workspace has set up without opening the menu.

    Which is the whole point of that line -- and a path that dropped the budget on the way
    would start a run the runtime refuses, out of a workspace whose settings say six hours.
    """
    Settings(tmp_path).remember(
        "local/quiet",
        {"worker": Runs("claude/m:high")},
        budget={"duration": "PT6H"},
    )
    app = Humanize()
    async with app.run_test():
        held = app._remembered_for("local/quiet")

        assert held is not None
        assert held.budget == Budget(duration=datetime.timedelta(hours=6))


@pytest.mark.timeout(60)
async def test_one_remembered_with_no_budget_is_asked_about_rather_than_run(
    flows: Path, tmp_path: Path
) -> None:
    """A flow set up before it had one is set up again, rather than started to be refused."""
    Settings(tmp_path).remember("local/quiet", {"worker": Runs("claude/m:high")})
    app = Humanize()
    async with app.run_test():
        assert app._remembered_for("local/quiet") is None
        assert budget_of("local/quiet") is None


@pytest.mark.timeout(60)
async def test_the_conversation_humanize_ships_is_never_asked_for_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`chat` stops when the person does, and runs under no budget of anybody's."""
    import hmz.tui.app

    monkeypatch.setattr(hmz.tui.app, "installed", lambda: dict(_INSTALLED))
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _into(app, driver, "chat")
        assert "none needed" in _said(app)

        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await until(lambda: app.screen is not sheet, driver)

    assert Settings(tmp_path).flow == "chat"
    assert app._budget is None


async def _sets(app: Humanize, driver: Pilot[None]) -> Flows:
    """Answers the budget sheet from its last row, back on to the menu."""
    await onto(app, driver, _DONE)
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Flows), driver)
    return cast("Flows", app.screen)


async def _reopens(app: Humanize, driver: Pilot[None]) -> Configures:
    """Opens the budget sheet from its row on the menu."""
    await opens(app, driver, _BUDGET)
    await until(lambda: isinstance(app.screen, Configures), driver)
    return cast("Configures", app.screen)


@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    ("typed", "shown", "held"),
    [
        ("12d", "12d", datetime.timedelta(days=12)),
        ("400d", "400d", datetime.timedelta(days=400)),
        ("2w", "14d", datetime.timedelta(weeks=2)),
        ("90", "1m30s", datetime.timedelta(seconds=90)),
        ("PT1H30M", "1h30m", datetime.timedelta(hours=1, minutes=30)),
        ("1d0.5s", "1d0.5s", datetime.timedelta(days=1, seconds=0.5)),
    ],
)
async def test_a_duration_set_there_opens_again_as_it_was_written(
    flows: Path, typed: str, shown: str, held: datetime.timedelta
) -> None:
    """In the units `-b duration=` reads, however long it is.

    A duration of a million seconds or more once reopened as `1.0368e+06s`, which the sheet
    it was opened on then refused -- and the interface fell over opening it.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await _into(app, driver, "local/quiet")
        await _reopens(app, driver)
        await changes(app, driver, "duration", *typed)
        menu = await _sets(app, driver)
        assert menu._budget == Budget(duration=held)
        assert f"stops at {shown}" in _said(app)  # and the row says it the same way

        sheet = await _reopens(app, driver)
        assert sheet._typed_in["duration"] == shown

        # And set again untouched, it is the same budget.
        menu = await _sets(app, driver)
        assert menu._budget == Budget(duration=held)


@pytest.mark.timeout(60)
async def test_a_budget_kept_with_a_long_duration_opens(
    flows: Path, tmp_path: Path
) -> None:
    """Read back from the settings file, as the next interface reads it.

    Even one whose only other limit is a cost of nothing, which the sheet would not have set.
    """
    Settings(tmp_path).remember(
        "local/quiet",
        {"worker": Runs("claude/m:high")},
        budget={"duration": "P12DT3H", "cost": 0},
    )
    app = Humanize()
    async with app.run_test() as driver:
        await _into(app, driver, "local/quiet")
        sheet = await _reopens(app, driver)

        assert sheet._typed_in["duration"] == "12d3h"
        assert sheet._typed_in["cost"] == "0.0"


@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    ("held", "keys", "written"),
    [
        ("cost", "5", "5"),
        ("cost", "2.5", "2.5"),
        ("output_tokens", "1000", "1000"),
        ("duration", "12d", "12d"),
    ],
)
async def test_what_is_typed_into_a_limit_is_what_it_holds(
    flows: Path, tmp_path: Path, held: str, keys: str, written: str
) -> None:
    """The value a row is begun on is selected whole, and the first key replaces it.

    Typing `5` into a cost of `0.0` once made it `0.05`.
    """
    Settings(tmp_path).remember(
        "local/quiet",
        {"worker": Runs("claude/m:high")},
        budget={"duration": "PT1H", "cost": 0.5, "output_tokens": 7},
    )
    app = Humanize()
    async with app.run_test() as driver:
        await _into(app, driver, "local/quiet")
        sheet = await _reopens(app, driver)

        await changes(app, driver, held, *keys)
        assert sheet._typed_in[held] == written


@pytest.mark.timeout(60)
async def test_a_limit_is_still_edited_after_the_first_key(flows: Path) -> None:
    """Only the first key replaces: backspace after it takes one letter, and an arrow nothing."""
    app = Humanize()
    async with app.run_test() as driver:
        await _into(app, driver, "local/quiet")
        sheet = await _reopens(app, driver)

        await changes(app, driver, "cost", *"25", "backspace")
        assert sheet._typed_in["cost"] == "2"

        await changes(app, driver, "cost", "backspace")  # the whole value, selected
        assert sheet._typed_in["cost"] == ""

        await changes(app, driver, "output_tokens", "1", "left", "right", *"5")
        assert sheet._typed_in["output_tokens"] == "15"

        # And esc puts back what was there before the row was begun on.
        await onto(app, driver, "duration")
        await driver.press("enter", *"9h", "escape")
        await driver.pause()
        assert sheet._typed_in["duration"] == ""


@pytest.mark.timeout(60)
async def test_whether_a_run_finishes_its_turn_is_picked_from_a_list(
    flows: Path,
) -> None:
    """`graceful` drops `on` and `off` under it, picked by a click or by the keys.

    Not stepped with the arrows across, which once did nothing on it until enter had begun
    it: a value is picked from every value it can take, as `/settings` picks one.
    """
    from hmz.tui.dropdown import Dropdown

    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        await _into(app, driver, "local/quiet")
        sheet = await _reopens(app, driver)
        await changes(app, driver, "duration", *"1h")
        assert sheet._typed_in["graceful"] == "on"
        assert "▾" in str(
            sheet.query_one("#choices", OptionList).get_option_at_index(3).prompt
        )

        # The fourth row, clicked: the list drops, opening on the answer it is not.
        await driver.click("#choices", offset=(8, 3))
        await until(lambda: isinstance(app.screen, Dropdown), driver)
        values = app.screen.query_one(OptionList)
        assert [str(one.id) for one in values.options] == ["=on", "=off"]
        assert values.highlighted == 1
        await driver.click(values, offset=(2, 2))
        await until(lambda: app.screen is sheet, driver)
        assert sheet._typed_in["graceful"] == "off"

        # And back with the keys, enter dropping it and enter taking the one under the cursor.
        await picks(app, driver, "graceful", "on")
        assert sheet._typed_in["graceful"] == "on"
        await picks(app, driver, "graceful", "off")

        menu = await _sets(app, driver)
        assert menu._budget == Budget(
            duration=datetime.timedelta(hours=1), graceful=False
        )

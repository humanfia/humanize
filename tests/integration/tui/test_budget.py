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
from hmz.tui.pick import _BUDGET, _SAVE, Configures, Flows, budget_of
from tests.integration.tui.test_app import onto, opens, rows
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
    where = tmp_path / ".humanize" / "flows"
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
        assert "none yet" in _said(app)


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

        # The four `-b` takes, and nothing else.
        assert rows(app) == ["duration", "cost", "output_tokens", "graceful"]

        await driver.press(*"1h")  # a duration is written, as `-b` writes one
        await driver.press("down", "right")  # cost: 0 -> 1
        await driver.pause()
        assert (sheet._typed_in["duration"], sheet._typed_in["cost"]) == ("1h", "1.0")
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
        assert "given a budget" in _under(app)
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

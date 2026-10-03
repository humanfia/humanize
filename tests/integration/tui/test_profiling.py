"""Whether a run of a flow is profiled, set from the menu that sets its budget.

A row beside the budget's, on the page the flow's roles are on, because it is a thing about a
run of the flow as what the run may spend is -- and remembered with it, per flow, rather than
a setting of the workspace. What is checked is that the row says which it is without being
opened, that it is switched as every switch is -- its two values dropped under it -- that it is
written down with the flow and read back, and that the run started from the interface is asked
to profile where it says so.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from textual.widgets import OptionList

from hmz.runtime.kept import Runs
from hmz.runtime.settings import Settings
from hmz.tui import Humanize
from hmz.tui.flows import _PROFILING, Flows
from hmz.tui.pick import _ACT_SAVE
from tests.integration.tui.test_app import keyed, onto, picks, rows
from tests.integration.tui.test_budget import _into
from tests.integration.tui.test_budget import (
    flows as flows,  # noqa: PLC0414 -- a fixture
)
from tests.tui.fixtures import until

if TYPE_CHECKING:
    from pathlib import Path


def _said(app: Humanize) -> str:
    """What the profiling row says, which is read without opening anything."""
    listing = app.screen.query_one("#choices", OptionList)
    return str(listing.get_option_at_index(rows(app).index(_PROFILING)).prompt)


def _kept(tmp_path: Path, *, profile: bool | None = None) -> None:
    """Sets the flow up here as one ready to run, profiled or not."""
    Settings(tmp_path).remember(
        "local/quiet",
        {"worker": Runs("claude/m:high")},
        budget={"duration": "PT2H"},
        profile=profile,
    )


@pytest.mark.timeout(60)
async def test_the_row_sits_under_the_budget_and_is_off_until_turned_on(
    flows: Path, tmp_path: Path
) -> None:
    """Off unless somebody says otherwise, since it is a sampler running as long as the run."""
    _kept(tmp_path)
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _into(app, driver, "local/quiet")
        assert "off" in _said(app)

        # A switch, picked from the two dropped under it rather than turned over in place.
        await onto(app, driver, _PROFILING)
        assert "enter choose" in keyed(app)
        await picks(app, driver, _PROFILING, "on")
        await until(lambda: sheet._profile, driver)
        assert "on" in _said(app)
        assert sheet._changed
        # Held until the menu is saved, as everything else on it is.
        assert Settings(tmp_path).profile("local/quiet") is False

        await onto(app, driver, _ACT_SAVE)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Flows), driver)
        assert app._profile

    # Written down under the flow, beside its budget, and read back by the next interface.
    assert Settings(tmp_path).profile("local/quiet") is True
    assert Humanize()._profile


@pytest.mark.timeout(60)
async def test_a_flow_run_without_the_menu_is_profiled_as_it_was_set(
    flows: Path, tmp_path: Path
) -> None:
    """`$flow <task>` carries it, exactly as it carries the budget."""
    _kept(tmp_path, profile=True)
    app = Humanize()
    async with app.run_test():
        held = app._remembered_for("local/quiet")

        assert held is not None
        assert held.profile


@pytest.mark.timeout(60)
async def test_the_run_started_is_asked_to_profile(
    flows: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the row says is what the runs are asked for, beside the budget."""
    _kept(tmp_path, profile=True)
    app = Humanize()
    asked: list[dict[str, Any]] = []

    def asks(do: str, *_: object, **said: Any) -> None:
        """Keeps what the runs would have been asked, rather than asking them."""
        asked.append({"do": do, **said})

    async with app.run_test():
        monkeypatch.setattr(app, "_asks", asks)
        app._flow("go")

    (start,) = asked
    assert start["do"] == "start"
    assert start["profile"] is True
    assert cast("dict[str, Any]", start["budget"])["duration"] == "PT2H"

"""Where a flow's agents have their harnesses run, set from the menu that sets up the rest.

A row below the budget on the page the flow's roles are on, because it is a setting of the run
as the budget is. What is checked is that the row says what the setting comes to without being
opened, that what is set on its form is written down beside the rest of the flow and read back
by the next interface, and that a harness on a machine of its own is not set without saying
which machine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from textual.widgets import Label, OptionList

from hmz.coganchor.backends import Model
from hmz.runtime.kept import Runs
from hmz.runtime.settings import Settings
from hmz.tui import Humanize
from hmz.tui.pick import _DONE, _HARNESS, _SAVE, Flows, Harnessing, Placing
from tests.integration.tui.test_app import changes, onto, opens, rows
from tests.integration.tui.test_budget import QUIET
from tests.integration.tui.test_environments import _types
from tests.stubs import written
from tests.tui.fixtures import until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: One backend, so that the menu has something to set an agent up as and can be saved.
_INSTALLED = {"claude": (Model("m", ("high",)),)}

#: A flow whose one agent works on an environment of its own, which may be another machine.
PLACED = """
from hmz.flows import Agent, AgentCollection, Env, EnvCollection, FlowContext, FlowParams, flow


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    repo: Env


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def placed(task: str, *, agents: Agents, envs: Envs, params: FlowParams,
                 ctx: FlowContext) -> None:
    pass
"""


@pytest.fixture
def flows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts the flows where this project's own would be, with a backend to run them."""
    import hmz.tui.app
    import hmz.tui.pick

    monkeypatch.setattr(hmz.tui.app, "installed", lambda: dict(_INSTALLED))
    monkeypatch.setattr(hmz.tui.pick, "installed", lambda: dict(_INSTALLED))
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    written(where, "quiet", QUIET)
    written(where, "placed", PLACED)
    return where


async def _into(app: Humanize, driver: Pilot[None], flow: str) -> Flows:
    """Opens the menu already inside one flow, which is where the harness row is."""
    await driver.press(*f"/flow {flow}")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Flows), driver)
    sheet = cast("Flows", app.screen)
    await until(lambda: sheet._inside, driver)
    return sheet


def _said(app: Humanize) -> str:
    """What the harness row says, read without opening it."""
    listing = app.screen.query_one("#choices", OptionList)
    return str(listing.get_option_at_index(rows(app).index(_HARNESS)).prompt)


@pytest.mark.timeout(60)
async def test_the_row_says_what_adaptive_comes_to(flows: Path, tmp_path: Path) -> None:
    """Here, for work here; and for work on another machine, whatever that machine has."""
    Settings(tmp_path).remember(
        "local/placed",
        {"worker": Runs("claude/m:high")},
        {"repo": "docker@local/srv/repo"},
        budget={"duration": "PT1H"},
    )
    app = Humanize()
    async with app.run_test() as driver:
        await _into(app, driver, "local/quiet")
        assert "adaptive → local" in _said(app)
        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Flows), driver)

        await _into(app, driver, "local/placed")
        assert "adaptive → env where its CLI is installed, else local" in _said(app)


@pytest.mark.timeout(60)
async def test_what_is_set_there_is_kept_and_read_back(
    flows: Path, tmp_path: Path
) -> None:
    """Stepped to on its form, said on the row, written down with the flow, read back."""
    Settings(tmp_path).remember(
        "local/placed",
        {"worker": Runs("claude/m:high")},
        {"repo": "docker@local/srv/repo"},
        budget={"duration": "PT1H"},
    )
    app = Humanize()
    async with app.run_test() as driver:
        await _into(app, driver, "local/placed")
        await opens(app, driver, _HARNESS)
        await until(lambda: isinstance(app.screen, Harnessing), driver)

        # One row, stepped through the modes `-H` takes: no machine to name but a third.
        assert rows(app) == ["where", _DONE]
        await changes(
            app, driver, "where", "right", "right"
        )  # adaptive -> local -> env
        await onto(app, driver, _DONE)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)

        assert "env → on the environment's machine" in _said(app)

        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Flows), driver)

    assert Settings(tmp_path).harness("local/placed") == "env"
    again = Humanize()
    assert again._harness == "env"


@pytest.mark.timeout(60)
async def test_a_standalone_harness_is_not_set_without_its_machine(
    flows: Path,
) -> None:
    """A harness on a machine of its own is on some machine, which is asked for."""
    app = Humanize()
    async with app.run_test() as driver:
        await _into(app, driver, "local/quiet")
        await opens(app, driver, _HARNESS)
        await until(lambda: isinstance(app.screen, Harnessing), driver)
        sheet = cast("Harnessing", app.screen)

        await changes(app, driver, "where", "left")  # adaptive -> standalone
        assert rows(app) == ["where", "on", _DONE]
        await onto(app, driver, _DONE)
        await driver.press("enter")
        await driver.pause()

        assert app.screen is sheet
        assert "choose the machine" in str(
            app.screen.query_one("#tuning", Label).content
        )

        # And one named is taken as `-H` names it.
        sheet._typed_in["on"] = "ssh@gpu-box/~/scratch"
        await onto(app, driver, _DONE)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        assert "standalone → ssh@gpu-box/~/scratch" in _said(app)


@pytest.mark.timeout(60)
async def test_its_machine_is_read_as_the_command_line_reads_it(flows: Path) -> None:
    """`ssh@gpu-box` with no directory is the login's home there, as `-H` takes it.

    The machine is chosen on the form an environment role is placed on, but it is not one:
    it takes no `local`, and a directory left off is filled in as the command line fills it.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await _into(app, driver, "local/quiet")
        await opens(app, driver, _HARNESS)
        await until(lambda: isinstance(app.screen, Harnessing), driver)
        await changes(app, driver, "where", "left")  # adaptive -> standalone
        await opens(app, driver, "on")
        await until(lambda: isinstance(app.screen, Placing), driver)
        form = cast("Placing", app.screen)
        assert "local" not in form.choices("backend")

        # What `-H` refuses, it refuses in its own words.
        await _types(app, driver, "spelled", "bogus@x")
        await onto(app, driver, _DONE)
        await driver.press("enter")
        await driver.pause()
        assert app.screen is form
        said = str(form.query_one("#tuning", Label).content)
        assert "'bogus' is not a backend" in said
        assert "<role>" not in said

        await _types(app, driver, "spelled", "ssh@gpu-box")
        assert (form._typed_in["backend"], form._typed_in["provider"]) == (
            "ssh",
            "gpu-box",
        )
        await onto(app, driver, _DONE)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Harnessing), driver)
        await until(lambda: _DONE in rows(app), driver)

        await onto(app, driver, _DONE)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        assert "standalone → ssh@gpu-box" in _said(app)

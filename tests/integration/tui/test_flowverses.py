"""Choosing a flow out of what is installed, and keeping what is installed up to date.

`/flow` opens on the flows there are to run -- the ones built into humanize, the ones installed
out of a flowverse, and your own -- and a flow an index merely lists is not among them until it
is installed (`test_flowverses_menu.py`). What is checked here is that list, the walk from it
into what a flow runs on, copying one here, and what the interface does with the indexes as it
starts: fetches them, quietly, and says which installed flows have a newer release.

Driven headlessly, as every test of the interface is, so what is checked is where a keystroke
lands rather than how it is drawn.
"""

from __future__ import annotations

import asyncio
import unittest.mock
from typing import TYPE_CHECKING, cast

import pytest
from textual.widgets import Button, Label, OptionList

from hmz.coganchor.backends import Model
from hmz.runtime.flowing import LOCAL, MINE, OFFICIAL, find
from hmz.runtime.flowing import index as shelf
from hmz.runtime.flowing import verses as store
from hmz.tui import Humanize
from hmz.tui.flows import HOME, INSTALLED, Flows
from hmz.tui.pick import Agent, Configures
from tests.integration.tui.test_app import bar, ids, into_agent, onto, rows
from tests.integration.tui.test_flowverses_menu import FLOW, Shelf, mine
from tests.stubs import written
from tests.tui.fixtures import transcript, until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

__all__ = ["mine"]


async def _open(app: Humanize, driver: Pilot[None]) -> Flows:
    """Opens the flow menu, as `/flow` does, and waits for it to be drawn."""
    await driver.press(*"/flow")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Flows), driver)
    sheet = cast("Flows", app.screen)
    await until(lambda: bool(ids(app)), driver)
    return sheet


def _under(sheet: Flows) -> str:
    """What is said under the list, which is where what was done reports itself."""
    return str(sheet.query_one("#tuning", Label).content)


def _drawn(sheet: Flows, held: str) -> str:
    """What the row put up under one id says."""
    return str(sheet.query_one("#choices", OptionList).get_option(f"={held}").prompt)


def _fetched(name: str) -> bool:
    """Whether a flowverse's index has been cloned yet."""
    one = store.named(name)
    return one is not None and one.fetched


def _own(tmp_path: Path) -> Path:
    """This project's own flows, which a test writes flows into."""
    where = tmp_path / MINE[LOCAL]
    where.mkdir(parents=True, exist_ok=True)
    return where


@pytest.mark.timeout(60)
async def test_the_menu_opens_on_what_is_installed_a_step_under_its_first_screen() -> (
    None
):
    """What `/flow` is typed for is a flow to run; the flowverses are a step out and across."""
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        sheet = await _open(app, driver)

        assert sheet._page == INSTALLED
        assert "chat" in rows(app)
        assert "built in" in _drawn(sheet, "chat")
        # The flow in force, ticked, and what it does beside its name.
        assert "✔" in _drawn(sheet, "chat")
        assert "Talks to one agent" in _drawn(sheet, "chat")

        await driver.press("left")
        await until(lambda: sheet._page == HOME, driver)
        assert rows(app) == ["installed", "verses"]
        assert sheet.under() == "installed"  # on the card it came out of

        await driver.press("right")
        await until(lambda: sheet._page == INSTALLED, driver)
        await driver.press("backspace")
        await until(lambda: sheet._page == HOME, driver)
        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Flows), driver)


@pytest.mark.timeout(60)
async def test_a_flow_an_index_only_lists_is_not_one_to_run(mine: Shelf) -> None:
    """Listed is what may be installed; installed is what there is to run."""
    store.add(f"file://{mine.listed}", "mine")
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        await _open(app, driver)
        assert "mine/demo" not in rows(app)

    shelf.install("mine", "demo")
    again = Humanize()
    async with again.run_test(size=(120, 40)) as driver:
        sheet = await _open(again, driver)
        await until(lambda: "mine/demo" in rows(again), driver)

        # Under the flowverse it came from, at the release it is at.
        assert "0.1.0" in _drawn(sheet, "mine/demo")
        assert " [$primary]mine[/]" in [
            str(one.prompt) for one in sheet.query_one("#choices", OptionList).options
        ]


@pytest.mark.timeout(60)
async def test_the_flows_of_your_own_are_listed_under_where_they_are(
    tmp_path: Path,
) -> None:
    """A directory is not a flowverse, but it is a place flows come from."""
    written(_own(tmp_path), "theirs", FLOW)
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        sheet = await _open(app, driver)
        await until(lambda: "local/theirs" in rows(app), driver)

        assert " [$primary]local[/]" in [
            str(one.prompt) for one in sheet.query_one("#choices", OptionList).options
        ]
        # Nothing to update or uninstall: it is yours, and nothing installed it.
        await onto(app, driver, "local/theirs")
        await driver.pause()
        assert app.screen.query_one("#act-uninstall", Button).disabled
        assert app.screen.query_one("#act-update", Button).disabled


@pytest.mark.timeout(60)
async def test_the_keys_stay_inside_the_terminal(tmp_path: Path) -> None:
    """Twenty flows are a list that scrolls, not a screen with no keys on it."""
    for n in range(20):
        written(_own(tmp_path), f"flow_{n:02d}", FLOW)
    app = Humanize()
    async with app.run_test(size=(80, 20)) as driver:
        sheet = await _open(app, driver)
        await until(lambda: len(rows(app)) > 20, driver)
        keys = sheet.query_one("#keys", Label)
        listing = sheet.query_one("#choices", OptionList)

        assert keys.region.bottom <= app.size.height
        assert keys.region.right <= app.size.width
        short = listing.size.height

        await driver.resize_terminal(80, 40)
        await driver.pause()

        assert listing.size.height > short
        assert keys.region.bottom <= app.size.height


#: A file that is three flows and no `run`, which is what humanize1 is.
THREE = '''"""Phases of one thing, which are things to run apiece."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams, flow


class Drafting(AgentCollection):
    """The one that writes."""

    drafter: Agent


class Building(AgentCollection):
    """The one that builds, and the one that reads it."""

    builder: Agent
    reviewer: Agent


class Wide(FlowParams):
    """What the first phase takes."""

    n: int = 6


@flow(agents=Drafting, envs=EnvCollection, params=Wide, name="gen-idea")
async def gen_idea(task: str, *, agents: Drafting, envs: EnvCollection, params: Wide,
                   ctx: FlowContext) -> None:
    """Opens a loose idea into a draft."""


@flow(agents=Building, envs=EnvCollection, params=FlowParams, name="rlcr")
async def rlcr(task: str, *, agents: Building, envs: EnvCollection, params: FlowParams,
               ctx: FlowContext) -> None:
    """Builds it, under review."""
'''


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={"claude": (Model("claude-opus-5", ("max", "high")),)},
)
async def test_one_of_the_flows_a_file_holds_is_chosen_like_any_other(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    tmp_path: Path,
) -> None:
    """The walk on from it is that flow's own: its settings, then its agents."""
    written(_own(tmp_path), "three", THREE)
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        sheet = await _open(app, driver)
        await until(lambda: "local/three:rlcr" in rows(app), driver)
        assert "local/three:gen-idea" in rows(app)

        # The first of them takes an `n`, asked as it is chosen.
        await onto(app, driver, "local/three:gen-idea")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Configures), driver)
        await driver.press("escape")
        await until(lambda: sheet._inside, driver)
        # And it is a row of what the flow runs on, to be opened again.
        assert "\x1eparams" in rows(app)

        await driver.press("escape")
        await until(lambda: not sheet._inside, driver)
        await onto(app, driver, "local/three:rlcr")
        await driver.press("enter")
        await until(lambda: sheet._inside, driver)
        assert sheet._flow == "local/three:rlcr"
        await into_agent(app, driver)
        assert isinstance(app.screen, Agent)
        assert "builder" in str(app.screen.query_one("#asked", Label).content)


@pytest.mark.timeout(60)
async def test_a_flow_is_copied_here_to_be_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copying one here is the way to change a flow at all, an installed one being updated over.

    A flow is a directory, so a copy of one is a flow: what it imports and the skills it
    brings come across with it, under the name it already had -- and your own flows are
    looked in first, so from then on that name means the copy.
    """
    monkeypatch.chdir(tmp_path)
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        sheet = await _open(app, driver)
        await onto(app, driver, "chat")
        assert "copy" in bar(app)

        await onto(app, driver, "copy")
        await driver.press("enter")
        await until(lambda: "copied to" in _under(sheet), driver)

        assert "chat now points to it" in _under(sheet)
        await until(lambda: "local/chat" in rows(app), driver)

        # And once more is a copy already made: one to edit, run or take away instead.
        await onto(app, driver, "chat")
        await onto(app, driver, "copy")
        await driver.press("enter")
        await until(lambda: "already a flow of your own" in _under(sheet), driver)

    at = tmp_path / MINE[LOCAL] / "chat"
    assert "one agent, one session" in (at / "__init__.py").read_text()
    assert find("chat") == str(at / "__init__.py")


@pytest.mark.timeout(60)
async def test_a_flow_that_will_not_load_says_why_it_would_not(tmp_path: Path) -> None:
    """A flow that will not load is a dead end until it says which reason it was."""
    written(
        _own(tmp_path), "broken", "import a_module_that_is_not_installed_anywhere\n"
    )
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        sheet = await _open(app, driver)
        await until(lambda: "local/broken" in rows(app), driver)
        await onto(app, driver, "local/broken")
        await driver.press("enter")
        await until(lambda: "failed to load" in _under(sheet), driver)

        said = _under(sheet)
        assert "local/broken failed to load" in said
        assert "a_module_that_is_not_installed_anywhere" in said


@pytest.mark.timeout(60)
@pytest.mark.usefixtures("freshening")
async def test_every_index_is_fetched_as_the_interface_starts(
    mine: Shelf, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An index only ever fetched on a keypress is one that is months behind.

    The one nobody has fetched yet included -- humanize's own, on a machine installed this
    morning, is a list of flows to install nobody can see until it lands. And nothing is
    installed for anybody: what runs is what somebody chose.
    """
    monkeypatch.setattr(store, "OFFICIAL_URL", f"file://{mine.listed}")
    store.add(f"file://{mine.listed}", "mine")
    mine.releases("0.2.0")
    app = Humanize()
    async with app.run_test() as driver:
        await until(lambda: _fetched(OFFICIAL), driver)
        await until(
            lambda: (
                [one.version for one in shelf.index("mine").versions("demo")]
                == ["0.2.0", "0.1.0"]
            ),
            driver,
        )

    assert shelf.installed() == []


@pytest.mark.timeout(60)
@pytest.mark.usefixtures("freshening")
async def test_a_newer_release_of_an_installed_flow_is_said_once_it_is_fetched(
    mine: Shelf, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Said in the transcript, with where to update it from; and taken by nobody but you."""
    monkeypatch.setattr(store, "OFFICIAL_URL", f"file://{mine.listed}")
    store.add(f"file://{mine.listed}", "mine")
    shelf.install("mine", "demo")
    mine.releases("0.2.0")
    app = Humanize()
    async with app.run_test() as driver:
        await until(lambda: "updates available" in transcript(app), driver)

        assert "mine/demo 0.1.0 ↑ 0.2.0" in transcript(app)
        assert "update from /flow" in transcript(app)

    assert [one.version for one in shelf.installed()] == ["0.1.0"]


@pytest.mark.timeout(60)
@pytest.mark.usefixtures("freshening")
async def test_an_index_somebody_has_written_into_is_left_where_it_is(
    mine: Shelf, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fetch resets the clone, and somebody writing their next manifest would lose it."""
    monkeypatch.setattr(store, "OFFICIAL_URL", f"file://{mine.listed}")
    added = store.add(f"file://{mine.listed}", "mine")
    readme = added.at / "README.md"
    readme.write_text("Mine now.\n")
    mine.releases("0.2.0")
    app = Humanize()
    async with app.run_test() as driver:
        await until(lambda: _fetched(OFFICIAL), driver)
        # Pumped a while, what is being waited for here being something that must not happen.
        for _ in range(40):
            await driver.pause()
            await asyncio.sleep(0.02)

        assert readme.read_text() == "Mine now.\n"
        assert [one.version for one in shelf.index("mine").versions("demo")] == [
            "0.1.0"
        ]


@pytest.mark.timeout(60)
@pytest.mark.usefixtures("freshening")
async def test_a_fetch_that_lands_makes_an_open_menu_read_again(
    mine: Shelf, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The menu holds what it read, and a fetch landing under it makes that the old list."""
    monkeypatch.setattr(store, "OFFICIAL_URL", f"file://{mine.listed}")
    store.add(f"file://{mine.listed}", "mine")
    shelf.install("mine", "demo")
    store.fetch(OFFICIAL)
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        sheet = await _open(app, driver)
        await until(lambda: "mine/demo" in rows(app), driver)
        assert "↑" not in _drawn(sheet, "mine/demo")

        mine.releases("0.2.0")
        await asyncio.to_thread(store.fetch, "mine")
        app._flows_changed()

        await until(lambda: "↑ 0.2.0" in _drawn(sheet, "mine/demo"), driver)

"""A directory's runs: `/epics` lists, exports and imports them; `/resume` picks one up."""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from textual.widgets import OptionList

from hmz.runtime.epic import Epic, epics
from hmz.tui import Humanize
from hmz.tui.pick import Epics, Exporting, ImportingEpic
from tests.integration.doubles_tui import (
    OWN,
    SIZE,
    on,
    opened,
    own_flow,
    rows,
    set_up_own_flow,
    shows,
    stand_in,
    typed,
    until,
)

if TYPE_CHECKING:
    from textual.pilot import Pilot


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, and a resumable flow of the workspace's own."""
    del asking
    workspace = stand_in(tmp_path, monkeypatch)
    own_flow(workspace)
    return workspace


async def chatted(pilot: Pilot[None]) -> None:
    """Runs chat for one turn, and stops it."""
    await opened(pilot)
    await typed(pilot, "hello")
    await shows(pilot, "heard hello")
    await typed(pilot, "/stop")
    await shows(pilot, "stopping the flow")


async def test_with_no_runs_epics_and_resume_say_there_is_nothing(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/resume")
        await shows(pilot, "nothing to resume")

        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await shows(pilot, "no flow has been run in this directory yet")


async def test_a_run_stopped_is_listed_with_its_task_and_how_it_ended(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await chatted(pilot)
        await until(pilot, lambda: bool(epics(workspace)), "the run's record")

        await typed(pilot, "/epics")
        await on(pilot, Epics)

        await shows(pilot, "· chat", "hello · 1 session · stopped")
        assert rows(app) == [one.name for one in epics(workspace)]


async def test_a_run_another_process_holds_is_listed_as_still_going(
    workspace: Path,
) -> None:
    # Held as `hmz exec` holds the run it goes with, which no host here speaks for.
    with Epic("chat", "elsewhere", workspace):
        async with Humanize().run_test(size=SIZE) as pilot:
            await opened(pilot)
            await typed(pilot, "/epics")
            await on(pilot, Epics)

            await shows(pilot, "elsewhere · 0 sessions · is still going")


async def test_a_run_exported_from_epics_is_an_archive_where_it_was_asked_for(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await chatted(pilot)
        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await shows(pilot, "stopped")
        await pilot.press("enter")
        await shows(pilot, "export run", "chat is not resumable")

        await pilot.press("enter")
        await on(pilot, Exporting)
        await pilot.press(*"out.hmzepic", "enter", "enter")

        await on(pilot, Epics)
        await until(pilot, (workspace / "out.hmzepic").exists, "the archive")
        await shows(pilot, " kB ")

    with tarfile.open(workspace / "out.hmzepic") as archive:
        named = archive.getnames()
    (epic,) = epics(workspace)
    assert any(one.endswith("epic.jsonl") for one in named)
    assert any(epic.name in one for one in named)


async def test_resume_picks_the_last_run_of_a_resumable_flow_back_up(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await set_up_own_flow(pilot)
        await typed(pilot, "make it so")
        await shows(pilot, "the flow is done")

        await typed(pilot, "/resume")

        await until(
            pilot,
            lambda: "resumed" in (workspace / "said.txt").read_text(),
            "the run to be picked up",
        )
    assert (workspace / "said.txt").read_text().splitlines() == [
        "started: heard make it so",
        "resumed: heard make it so",
    ]


async def test_epics_turn_to_this_machine_and_remember_it(workspace: Path) -> None:
    # Under home, so that it is said short enough not to be wrapped: `~/elsewhere`.
    elsewhere = Path.home() / "elsewhere"
    elsewhere.mkdir(parents=True)
    with Epic("chat", "here", workspace) as here:
        pass
    with Epic(OWN, "there", elsewhere, resumable=True) as there:
        pass
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await shows(pilot, "Every epic in this directory", "ctrl+t this machine")
        assert rows(app) == [here.path.name]

        await pilot.press("ctrl+t")
        await shows(pilot, "Every epic on this machine", "ctrl+t this directory")
        await until(pilot, lambda: len(rows(app)) == 2, "both epics")
        assert rows(app) == [there.path.name, here.path.name]
        await shows(pilot, "~/elsewhere · there")

        # Another directory's epic is read and exported from here, but not carried on.
        await pilot.press("up", "enter")
        await shows(pilot, "resume run")
        await pilot.press("enter")
        await on(pilot, Epics)
        await shows(pilot, "this epic ran in ~/elsewhere; resume it from hmz there")

        await pilot.press("escape")
        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await until(pilot, lambda: len(rows(app)) == 2, "the scope remembered")


def _exported(epic: Path, name: str) -> None:
    """Exports one epic under home, short enough not to be wrapped, and takes it away."""
    from hmz.runtime.exporting import bundle

    bundle(epic, Path.home() / name)
    shutil.rmtree(epic)


def _cursor(app: Humanize) -> str:
    """The row the cursor of the sheet on top is on, by id."""
    at = app.screen.query_one("#choices", OptionList).highlighted
    return rows(app)[at] if at is not None else ""


async def _imports(pilot: Pilot[None], name: str) -> None:
    """Imports one file under home from `/epics`, with the key that does."""
    await pilot.press("i")
    await on(pilot, ImportingEpic)
    await pilot.press(*f"~/{name}", "enter", "enter")
    await on(pilot, Epics)


async def test_an_epic_imported_from_epics_is_listed_with_the_cursor_on_it(
    workspace: Path,
) -> None:
    elsewhere = Path.home() / "elsewhere"
    elsewhere.mkdir(parents=True)
    with Epic("chat", "here", workspace) as here:
        pass
    with Epic("chat", "there", elsewhere) as there:
        pass
    _exported(here.path, "a.hmzepic")
    _exported(there.path, "b.hmzepic")
    (Path.home() / "c.txt").write_text("not an epic")
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await shows(pilot, "no flow has been run in this directory yet", "Import…")

        await _imports(pilot, "a.hmzepic")
        await until(pilot, lambda: rows(app) == [here.path.name], "the epic imported")
        await shows(pilot, "imported")
        assert _cursor(app) == here.path.name

        await pilot.press("enter")
        await shows(pilot, "export run", "chat is not resumable")
        await pilot.press("escape")
        await on(pilot, Epics)

        # Another directory's turns the list to this machine's, where it is a row.
        await _imports(pilot, "b.hmzepic")
        await shows(pilot, "Every epic on this machine", "~/elsewhere")
        await until(pilot, lambda: len(rows(app)) == 2, "both epics")
        assert _cursor(app) == there.path.name

        await pilot.press("down")
        await _imports(pilot, "b.hmzepic")
        await shows(pilot, "is already here")
        await until(pilot, lambda: _cursor(app) == there.path.name, "the one here")

        await _imports(pilot, "c.txt")
        await shows(pilot, "c.txt is not a .hmzepic file")

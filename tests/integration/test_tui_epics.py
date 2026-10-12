"""A directory's runs: `/epics` lists and exports them, and `/resume` picks the last back up."""

from __future__ import annotations

import tarfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz.runtime.epic import Epic, epics
from hmz.tui import Humanize
from hmz.tui.pick import Epics, Exporting
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
        await pilot.press(*"out.tar.gz", "enter", "enter")

        await on(pilot, Epics)
        await until(pilot, (workspace / "out.tar.gz").exists, "the archive")
        await shows(pilot, " kB ")

    with tarfile.open(workspace / "out.tar.gz") as archive:
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

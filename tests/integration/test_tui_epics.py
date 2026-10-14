"""A directory's runs: `/epics` lists, exports and imports them; `/resume` picks one up."""

from __future__ import annotations

import re
import shutil
import tarfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from textual import events
from textual.widgets import OptionList

from hmz.runtime.doing.epics import Epics as Kept
from hmz.runtime.epic import Epic, Ran, epics, read
from hmz.tui import Humanize
from hmz.tui.epic import Graph, SessionRead
from hmz.tui.exomyth import Exomyth
from hmz.tui.monitoring import Monitoring
from hmz.tui.pick import Does, Epics, Exporting, ImportingEpic
from tests.integration.doubles_tui import (
    OWN,
    SIZE,
    claude_logged,
    folds_fast,
    on,
    opened,
    opens,
    own_flow,
    picks,
    rows,
    screen,
    set_up_own_flow,
    shows,
    stand_in,
    trail,
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
    folds_fast(monkeypatch)
    return workspace


async def chatted(pilot: Pilot[None]) -> None:
    """Runs chat for one turn, and leaves it with `/clear` to fold away, which ends it."""
    await opened(pilot)
    await typed(pilot, "hello")
    await shows(pilot, "heard hello")
    await typed(pilot, "/clear")
    await shows(pilot, "◉ chat")
    workspace = Path.cwd()
    await until(
        pilot,
        lambda: any((read(one) or Ran(one)).how for one in epics(workspace)),
        "the chat to fold away",
    )


def listed(app: Humanize) -> list[str]:
    """The epics `/epics` lists on the page shown, by name, without the rows above them."""
    listing = app.screen.query_one("#choices", OptionList)
    return [
        str(one.id).removeprefix("=")
        for one in listing.options
        if str(one.id).startswith("=")
    ]


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


async def test_a_run_ended_is_listed_with_its_task_and_what_it_came_to(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await chatted(pilot)

        await typed(pilot, "/epics")
        await on(pilot, Epics)

        # Who it was run by, what it spent and how long it took, as the web lists it.
        await shows(pilot, "· chat", "hello · ", " · $0.00 · 200 out · took ")
        # Apart: an agent's name long enough wraps the row between the two.
        await shows(pilot, "1 session")
        assert listed(app) == [one.name for one in epics(workspace)]


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
        await shows(pilot, "1 session")
        await pilot.press("enter")
        await shows(pilot, "continue", "export epic")

        await opens(pilot, "export")
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
        assert listed(app) == [here.path.name]

        await pilot.press("ctrl+t")
        await shows(pilot, "Every epic on this machine", "ctrl+t this directory")
        await until(pilot, lambda: len(listed(app)) == 2, "both epics")
        assert listed(app) == [there.path.name, here.path.name]
        await shows(pilot, "~/elsewhere · there")

        # Another directory's epic is read and exported from here, but not carried on.
        await pilot.press("up", "enter")
        await shows(pilot, "resume epic")
        await pilot.press("enter")
        await on(pilot, Epics)
        await shows(pilot, "this epic ran in ~/elsewhere; resume it from hmz there")

        await pilot.press("escape")
        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await until(pilot, lambda: len(listed(app)) == 2, "the scope remembered")


async def test_an_epic_opened_from_epics_is_its_graph_its_sessions_and_what_each_said(
    workspace: Path, tmp_path: Path
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await set_up_own_flow(pilot)
        began = time.time()
        await typed(pilot, "make it so")
        await shows(pilot, "the flow is done")
        (epic,) = epics(workspace)
        (session,) = Kept(workspace).sessions(epic)
        claude_logged(tmp_path / "claude-home", workspace, session.ident, began)

        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await shows(pilot, f"· {OWN}", "make it so · ", " · took ", "resumable")

        await pilot.press("enter")
        await on(pilot, Does)
        await shows(pilot, "graph", "Exomyth")
        await opens(pilot, "graph")
        await on(pilot, Graph)
        # Its agent as the monitor draws one, its turn read back, its one session under it.
        await shows(pilot, "1 turn · 1 session", f"{session.agent}/1", "6 actions")
        await shows(pilot, trail("hmz", "/epics"), "Exomyth")

        await opens(pilot, f"claude:{session.ident}")
        await on(pilot, SessionRead)
        await shows(
            pilot, f"{session.agent}/1", "turn", "fix the bug", "pytest", "fixed"
        )
        await pilot.press("slash", *"pytest")
        await until(pilot, lambda: len(rows(app)) == 1, "the one tool found")
        await pilot.press("escape", "escape")
        await on(pilot, Graph)

        # The button under it, as the graph of the run going has it across its top.
        await pilot.press("tab", "enter")
        await on(pilot, Exomyth)
        await shows(pilot, "1 session")
        await pilot.press("escape")
        await on(pilot, Graph)


async def test_a_chat_has_no_exomyth_to_open(workspace: Path) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await chatted(pilot)
        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await shows(pilot, "1 session")
        await pilot.press("enter")
        await shows(pilot, "graph", "export epic")
        assert "Exomyth" not in screen(_app_of(pilot))
        await opens(pilot, "graph")
        await on(pilot, Graph)
        await shows(pilot, "1 session")
        assert "Exomyth" not in screen(_app_of(pilot))


async def test_the_epic_going_opens_in_exomyth_from_the_monitor(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await set_up_own_flow(pilot)
        await typed(pilot, "wait for it")
        await shows(pilot, "still on it")

        await pilot.press("left")
        await on(pilot, Monitoring)
        await shows(pilot, "Exomyth", "ctrl+e Exomyth")
        await pilot.press("ctrl+e")
        await on(pilot, Exomyth)
        await shows(pilot, trail("hmz", "monitor"), OWN)
        await pilot.press("escape")
        await on(pilot, Monitoring)


def _app_of(pilot: Pilot[None]) -> Humanize:
    app = pilot.app
    assert isinstance(app, Humanize)
    return app


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
        await until(pilot, lambda: listed(app) == [here.path.name], "the epic imported")
        await shows(pilot, "imported")
        assert _cursor(app) == here.path.name

        await pilot.press("enter")
        await shows(pilot, "continue", "export epic")
        await pilot.press("escape")
        await on(pilot, Epics)

        # Another directory's turns the list to this machine's, where it is a row.
        await _imports(pilot, "b.hmzepic")
        await shows(pilot, "Every epic on this machine", "~/elsewhere")
        await until(pilot, lambda: len(listed(app)) == 2, "both epics")
        assert _cursor(app) == there.path.name

        await pilot.press("down")
        await _imports(pilot, "b.hmzepic")
        await shows(pilot, "is already here")
        await until(pilot, lambda: _cursor(app) == there.path.name, "the one here")

        await _imports(pilot, "c.txt")
        await shows(pilot, "c.txt is not a .hmzepic file")


async def test_an_export_lands_in_downloads_and_a_file_dropped_on_import_is_read(
    workspace: Path,
) -> None:
    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True)
    with Epic("chat", "here", workspace) as here:
        pass
    archive = downloads / f"{here.path.name}.hmzepic"
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await pilot.press("enter")
        await shows(pilot, "export epic")
        await opens(pilot, "export")
        await on(pilot, Exporting)
        await shows(pilot, "~/Downloads/")
        await pilot.click("#act-done")
        await on(pilot, Epics)
        await until(pilot, archive.exists, "the archive in downloads")

        # Dropped onto the terminal, which pastes its path quoted.
        dropped = Path.home() / "my epics" / archive.name
        dropped.parent.mkdir()
        archive.rename(dropped)
        shutil.rmtree(here.path)
        await pilot.press("i")
        await on(pilot, ImportingEpic)
        app.screen.post_message(events.Paste(f"'{dropped}'"))
        # Taken in, whichever line of the row the path wraps onto.
        await until(
            pilot,
            lambda: "myepics" in re.sub(r"[\s│]", "", screen(app)),
            "the path pasted",
        )
        await pilot.click("#act-done")
        await on(pilot, Epics)
        await until(pilot, here.path.is_dir, "the epic imported")
        await shows(pilot, "imported")


async def test_epics_are_found_by_status_flow_workspace_and_task_a_page_at_a_time(
    workspace: Path,
) -> None:
    elsewhere = Path.home() / "elsewhere"
    elsewhere.mkdir(parents=True)
    chats: list[str] = []
    for at in range(50):
        with Epic("chat", f"chat {at}", workspace) as chat:
            chats.append(chat.path.name)
    with Epic(OWN, "own", workspace) as stopped:
        stopped.stopped()
    with Epic(OWN, "there", elsewhere) as there:
        pass
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/epics")
        await on(pilot, Epics)
        # A page of fifty, newest first, under the rows it is found by.
        await shows(pilot, "status", "all ▾", "1\N{EN DASH}50 of 51", "Older")
        assert rows(app)[:2] == ["status", "flow"]
        assert listed(app) == [stopped.path.name, *chats[:0:-1]]

        await pilot.click("#act-older")
        await shows(pilot, "51\N{EN DASH}51 of 51")
        assert listed(app) == [chats[0]]
        await pilot.click("#act-newer")
        await shows(pilot, "1\N{EN DASH}50 of 51")

        await picks(pilot, "status", "stopped")
        await until(pilot, lambda: listed(app) == [stopped.path.name], "the stopped")
        await shows(pilot, "stopped ▾")
        await picks(pilot, "status", "failed")
        await shows(pilot, "no epic is like that")
        await picks(pilot, "status", "")
        await picks(pilot, "flow", "chat")
        await until(pilot, lambda: len(listed(app)) == 50, "the chats")

        await pilot.press("slash", *"chat 7")
        await until(pilot, lambda: len(listed(app)) == 5, "the chats of a 7")
        await pilot.press("escape")
        await until(pilot, lambda: len(listed(app)) == 50, "the search put away")

        # Of this machine, found by its directory as well.
        await pilot.press("ctrl+t")
        await until(pilot, lambda: rows(app)[:3] == ["status", "flow", "workspace"], "")
        await picks(pilot, "flow", "")
        await picks(pilot, "workspace", "~/elsewhere")
        await until(pilot, lambda: listed(app) == [there.path.name], "the one there")

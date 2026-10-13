"""A chat, read as Claude Code reads one: one conversation, running or done, never stopped.

And as many of them as there are: each is an epic of its own, on a host of its own, which goes
on while another is had and folds away once nobody has looked at it for a while -- and is
carried on, in the same epic, from `/epics`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.runtime.epic import Ran, epics, read
from hmz.tui import Humanize
from hmz.tui.monitoring import Monitoring
from hmz.tui.pick import Does, Epics
from tests.integration.doubles_tui import (
    SIZE,
    folds_fast,
    heard,
    on,
    opened,
    opens,
    screen,
    shows,
    stand_in,
    started,
    typed,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, really asked what it runs as the interface opens."""
    del asking
    return stand_in(tmp_path, monkeypatch)


async def test_a_chat_is_running_while_the_assistant_answers_and_done_after(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "wait for it")

        drawn = await shows(pilot, "still on it", "running…")
        assert "stop" not in drawn.splitlines()[-1]
        assert "monitor" not in drawn.splitlines()[-1]

        await typed(pilot, "now")

        drawn = await shows(pilot, "heard wait for it then now", "◉ done")
        assert "waiting for you" not in drawn
        assert "outworlder" not in drawn
    assert heard(workspace) == ["wait for it", "now"]


async def test_ctrl_c_never_stops_a_chat_and_twice_leaves(workspace: Path) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "wait for it")
        await shows(pilot, "still on it")

        await pilot.press(*"half")
        await pilot.press("ctrl+c")
        await until(pilot, lambda: "❯ half" not in screen(app), "the line to clear")
        await pilot.press("ctrl+c")
        await shows(pilot, "press ctrl+c again to exit", "ctrl+c again to exit")
        assert "stopping" not in screen(app)
        await typed(pilot, "still here")
        await shows(pilot, "heard wait for it then still here")

        await pilot.press("ctrl+c", "ctrl+c")

        await until(pilot, lambda: not app.is_running, "the interface to close")


async def test_a_chat_offers_no_stop_monitor_or_views(workspace: Path) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "wait for it")
        await shows(pilot, "still on it")

        await pilot.press("left")
        await pilot.press("tab")
        await pilot.press("shift+tab")
        await pilot.pause()
        assert not any(isinstance(one, Monitoring) for one in app.screen_stack)
        assert "reading" not in screen(app)

        await pilot.press(*"/st")
        await pilot.pause()
        assert "/stop" not in screen(app)
        await pilot.press("ctrl+c")
        await typed(pilot, "/stop")

        await shows(pilot, "a chat is not stopped: /clear starts another")
        await typed(pilot, "go on")
        await shows(pilot, "heard wait for it then go on")


async def test_clear_starts_another_chat_and_the_first_goes_on_to_go_back_to(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "wait for it")
        await shows(pilot, "still on it")

        await typed(pilot, "/clear")
        await shows(pilot, "◉ chat")
        assert "still on it" not in screen(app)
        assert "stopping" not in screen(app)

        await typed(pilot, "again")
        await shows(pilot, "heard again")
        assert len(started(workspace)) == 2  # a conversation of its own

        # Both going, each an epic of its own.
        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await shows(pilot, "wait for it · ", "again · ")
        first, _ = epics(workspace)
        await opens(pilot, first.name)
        await on(pilot, Does)
        await opens(pilot, "continue")

        # Back in the first, as it stands, and talking to it.
        await shows(pilot, "still on it")
        await typed(pilot, "now")
        await shows(pilot, "heard wait for it then now")
    assert heard(workspace) == ["wait for it", "again", "now"]


async def test_a_chat_folded_away_is_continued_from_epics_in_the_same_epic(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folds_fast(monkeypatch)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "hello")
        await shows(pilot, "heard hello", "◉ done")
        await typed(pilot, "/clear")
        await until(pilot, lambda: len(epics(workspace)) == 1, "the epic")
        (epic,) = epics(workspace)
        await until(pilot, lambda: bool((read(epic) or Ran(epic)).ended), "it to fold")

        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await opens(pilot, epic.name)
        await on(pilot, Does)
        await opens(pilot, "continue")
        await shows(pilot, "say something to continue")

        await typed(pilot, "more")
        await shows(pilot, "heard more", "◉ done")
        assert "could not be carried on" not in screen(app)

    # One conversation, so one epic, and the agent's session carried on.
    assert epics(workspace) == [epic]
    began, carried = started(workspace)
    session = began[began.index("--session-id") + 1]
    assert carried[carried.index("--resume") + 1] == session
    assert "--fork-session" in carried


async def test_exit_leaves_a_chat_without_asking(workspace: Path) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "wait for it")
        await shows(pilot, "still on it")

        await typed(pilot, "/exit")

        await until(pilot, lambda: not app.is_running, "the interface to close")

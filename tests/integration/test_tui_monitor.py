"""Watching a run: the monitor `←` goes up to, the views tab steps between, and `/btw` beside it."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from hmz.tui import Humanize
from hmz.tui.monitoring import Monitoring
from tests.integration.doubles_tui import (
    RUNS,
    SIZE,
    heard,
    on,
    onto,
    opened,
    screen,
    shows,
    stand_in,
    typed,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, really asked what it runs as the interface opens."""
    del asking
    return stand_in(tmp_path, monkeypatch)


async def working(pilot: Pilot[None]) -> None:
    """Starts chat on a turn the stand-in holds open until it is told something more."""
    await opened(pilot)
    await typed(pilot, "wait a moment")
    await shows(pilot, "still on it")


async def test_left_goes_up_to_the_monitor_of_the_run_and_right_comes_back(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await working(pilot)

        await pilot.press("left")
        await on(pilot, Monitoring)
        drawn = await shows(pilot, "▣ epic · 1 of 1 working · 1 turn")
        # No node reads every agent at once: the cursor starts on the agent being read.
        assert "all agents" not in drawn
        assert re.search(r"❯ │ ▸ ● \S+", drawn)
        assert RUNS in drawn
        assert "chat" in drawn

        await pilot.press("right")
        await until(pilot, lambda: len(app.screen_stack) == 1, "the prompt")
        # Reading it stopped nothing: the agent is still working, by its own name.
        working_as = re.search(r"(\S+) is working", screen(app))
        assert working_as is not None
        await shows(pilot, f"{working_as[1]}…", f"{working_as[1]} · assistant · ")

        await typed(pilot, "go on")
        await shows(pilot, "heard wait a moment then go on")


async def test_the_monitor_counts_the_tokens_a_finished_turn_spent(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "hello")
        await shows(pilot, "heard hello")

        await pilot.press("left")
        await on(pilot, Monitoring)

        await shows(pilot, "1 turn · 1.2k tok", "1.0k", "200")


async def test_a_node_opened_on_the_monitor_is_the_view_the_prompt_then_reads(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await working(pilot)
        await pilot.press("left")
        await on(pilot, Monitoring)
        await shows(pilot, "1 of 1 working")

        await onto(pilot, "outworlder:human", "#graph")
        await pilot.press("enter")

        await until(pilot, lambda: len(app.screen_stack) == 1, "the prompt")
        await shows(pilot, "reading outworlder human")


async def test_shift_tab_and_tab_step_between_the_views_of_a_run(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await working(pilot)
        assert "all agents" not in screen(app)

        await pilot.press("tab")
        await shows(pilot, "reading outworlder human")
        assert "still on it" not in screen(app)

        await pilot.press("shift+tab")
        await shows(pilot, "· conversation 1 ─", "still on it")

        await pilot.press("shift+tab")
        await shows(pilot, "reading outworlder human")


async def test_btw_asks_a_side_agent_and_leaves_the_run_alone(workspace: Path) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await working(pilot)

        await typed(pilot, "/btw what is it doing")
        await shows(pilot, "btw · what is it doing heard what is it doing")
        await pilot.press("escape")
        await shows(pilot, "btw: exited")

        await typed(pilot, "carry on")
        await shows(pilot, "heard wait a moment then carry on")

    said = heard(workspace)
    assert said[0] == "wait a moment"
    assert said[-1] == "carry on"
    # The question went to an agent of its own, with what the run is doing to go on.
    (aside,) = [one for one in said if "what is it doing" in one]
    assert "flow: chat" in aside


async def test_btw_with_nothing_running_still_answers(workspace: Path) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)

        await typed(pilot, "/btw hey")

        await shows(pilot, "btw · btw agent", "heard hey")

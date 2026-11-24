"""Watching a run: the monitor `←` goes up to, the views tab steps between, and `/btw` beside it."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from textual.app import App

from hmz.runtime.watching.monitor import Monitor
from hmz.tui import Humanize
from hmz.tui.monitoring import Details, Halts, Monitoring
from tests.integration.doubles_tui import (
    OWN,
    RUNS,
    SIZE,
    TALKS,
    heard,
    on,
    onto,
    opened,
    own_flow,
    screen,
    set_up_own_flow,
    shows,
    stand_in,
    started,
    talks_set_up,
    typed,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

    from hmz.coganchor.fence import Fence

#: Every epic here is held by a daemon of the test's own, in this process.
pytestmark = pytest.mark.usefixtures("daemon")

#: The fences the stand-ins were spawned inside, none of them put up.
FENCES: list[Fence] = []


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, really asked what it runs as the interface opens.

    A side conversation runs inside a fence that writes nothing, which is not put up here: the
    stand-in writes what it was asked where the tests read it.
    """
    del asking
    FENCES.clear()

    def enforceable(*, net: bool) -> bool:
        del net
        return True

    def wrapper(fence: Fence) -> list[str]:
        FENCES.append(fence)
        return []

    monkeypatch.setattr("hmz.coganchor.fence.enforceable", enforceable)
    monkeypatch.setattr("hmz.coganchor.fence.wrapper", wrapper)
    workspace = stand_in(tmp_path, monkeypatch)
    talks_set_up(workspace)
    return workspace


async def working(pilot: Pilot[None], flow: str = TALKS) -> None:
    """Starts chat, under another name, on a turn held open until it is told more.

    Or, with no flow named, a chat itself: what a line said starts.
    """
    await opened(pilot)
    await typed(pilot, f"/flow {flow} wait a moment" if flow else "wait a moment")
    await shows(pilot, "still on it")


async def test_left_goes_up_to_the_monitor_of_the_run_and_right_comes_back(
    workspace: Path,
) -> None:
    app = Humanize(flow=TALKS)
    async with app.run_test(size=SIZE) as pilot:
        await working(pilot)

        await pilot.press("left")
        await on(pilot, Monitoring)
        drawn = await shows(pilot, "◫ epic · running · 1 of 1 working · 1 turn")
        # No node reads every agent at once: the cursor starts on the agent being read.
        assert "all agents" not in drawn
        assert re.search(r"❯ ┃█ ▸ ● \S+", drawn)
        assert RUNS in drawn

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
    async with Humanize(flow=TALKS).run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, f"/flow {TALKS} hello")
        await shows(pilot, "heard hello")

        await pilot.press("left")
        await on(pilot, Monitoring)

        await shows(pilot, "1 turn · 1.2k tok", "1.0k", "200")


async def test_a_node_opened_on_the_monitor_is_the_view_the_prompt_then_reads(
    workspace: Path,
) -> None:
    app = Humanize(flow=TALKS)
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
    app = Humanize(flow=TALKS)
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


async def test_btw_asks_a_side_copy_of_the_session_and_leaves_the_run_alone(
    workspace: Path,
) -> None:
    async with Humanize(flow=TALKS).run_test(size=SIZE) as pilot:
        await working(pilot)
        await pilot.press("tab")
        await shows(pilot, "reading outworlder human")
        await pilot.press("shift+tab")
        await shows(pilot, "· conversation 1 ─")

        await typed(pilot, "/btw what is it doing")
        await shows(pilot, "btw · what is it doing")
        await until(
            pilot,
            lambda: any("what is it doing" in one for one in heard(workspace)),
            "the side copy to be asked",
        )
        await pilot.press("escape")
        await shows(pilot, "btw: exited")

        await typed(pilot, "carry on")
        await shows(pilot, "heard wait a moment then carry on")

    said = heard(workspace)
    assert said[0] == "wait a moment"
    assert said[-1] == "carry on"
    # The question went to a side copy of the session, and never into the run's own.
    assert any("what is it doing" in one for one in said)
    # Which ran inside a fence of its own that writes nothing.
    assert any(not fence.writes for fence in FENCES)


async def test_btw_with_no_session_read_is_refused(workspace: Path) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)

        await typed(pilot, "/btw hey")

        await shows(pilot, "/btw is only available on one agent's", "/ai asks")


async def test_btw_over_the_monitor_is_refused_and_opens_nothing(
    workspace: Path,
) -> None:
    own_flow(workspace)
    async with Humanize().run_test(size=SIZE) as pilot:
        await set_up_own_flow(pilot)
        await typed(pilot, f"${OWN} wait a moment")
        await shows(pilot, "still on it")
        # Over the monitor, where there is no session a side question is of.
        await pilot.press("left")
        await on(pilot, Monitoring)

        await typed(pilot, "/btw what is it doing")

        await shows(pilot, "/btw is only available on one agent's", "/ai asks")
    assert _asides(workspace) == []


def _asides(workspace: Path) -> list[list[str]]:
    """The stand-ins started read-only for a side question, oldest first.

    Told `--tools`, which is said only where the file-writing tools are withheld.
    """
    return [one for one in started(workspace) if "--tools" in one]


async def test_the_epic_opens_from_the_monitor_and_is_stopped_there(
    workspace: Path,
) -> None:
    own_flow(workspace)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await set_up_own_flow(pilot)
        await typed(pilot, f"${OWN} wait a moment")
        await shows(pilot, "still on it")
        await pilot.press("left")
        await on(pilot, Monitoring)
        await shows(pilot, "◫ epic · running · 1 of 1 working", "· cost $0.00 of $1.00")

        await onto(pilot, "\x06", "#graph")
        await pilot.press("enter")
        await on(pilot, Details)
        await shows(
            pilot,
            "Figures",
            "time",
            "Budget",
            "cost              $0.00 of $1.00",
            "when spent        the last turn finishes",
            "Set up",
            "task              wait a moment",
            "coder=",
            "profiled          no",
            "Flows",
            "Stop",
        )

        await pilot.press("tab", "enter")
        await on(pilot, Halts)
        await shows(pilot, "Stop this epic?")
        await pilot.press("enter")
        await on(pilot, Details)
        # Stopping, or over already: the stand-in lets its turn go the moment it is told.
        await until(
            pilot,
            lambda: "Stopping." in screen(app) or "Over." in screen(app),
            "the epic to stop",
        )
        await pilot.press("escape")
        await on(pilot, Monitoring)
        await shows(pilot, "stopping the flow")


class _Holding(App[None]):
    """An epic's page alone, over an epic that is stopping until it is forced."""

    def __init__(self) -> None:
        super().__init__()
        self.forced: list[bool] = []
        self.state = "stopping"

    def epic(self) -> dict[str, object]:
        return {"run": 1, "flow": "@local/writes", "state": self.state}

    def stops(self, force: bool) -> None:
        self.forced.append(force)
        self.state = ""

    def on_mount(self) -> None:
        self.push_screen(Details(self.epic, Monitor, tuple, self.stops))


async def test_an_epic_stopping_is_forced_from_its_page_once_asked() -> None:
    app = _Holding()
    async with app.run_test(size=SIZE) as pilot:
        await until(pilot, lambda: "Force stop" in screen(app), "the button")

        await pilot.press("tab", "enter")
        await until(pilot, lambda: isinstance(app.screen, Halts), "the box")
        assert "Close every session now?" in screen(app)
        await pilot.press("enter")

        await until(pilot, lambda: "Over." in screen(app), "the epic to be over")
        assert app.forced == [True]
        assert "Force stop" not in screen(app)

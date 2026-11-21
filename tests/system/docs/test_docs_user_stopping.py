"""The pictures of `docs/user/stopping.md`: stopping a run, and forcing one that lingers.

Each interface a run is stopped from, as the page tells it: the app's Stop button and what
it asks first, Force stop on an epic still unwinding, Stop in the sidebar's menu and the
button that stops one turn of a chat; the terminal's two presses of ctrl+c and the epic's own
page in the monitor; and `hmz exec` interrupted from its terminal. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_stopping.py`.

One flow is staged here beside the world's: `tidy_loop`, a loop of the project's own that
takes its time on the way out, as a flow with something to put away does. An epic of it stays
`stopping` long enough to be drawn so, which no stand-in loop does: they unwind at once.
"""

from __future__ import annotations

import contextlib
import os
import re
import signal
import threading
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import psutil
from playwright.sync_api import expect

from tests.integration.doubles_tui import screen, shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-stopping"

#: The flow the page stops, which only its budget ends, and the task it is set.
_FLOW = "ralph_loop"
_TASK = "Add a discount code to checkout"

#: The project's own loop, which lingers on the way out, and the role its agent plays.
_TIDY = "@local/tidy_loop"

#: What a chat is asked, whose turn is stopped.
_ASKED = "Rename every price to an amount in cents"

#: Where a scene's screens are kept, to be read while a scene is written.
_SEEN = os.environ.get("HMZ_SCENE_SEEN")

#: What the agent says of the task, round after round.
_ROUNDS = [
    "Added a discount code to checkout: charge() takes a code, and WELCOME10 takes 10% off.",
    "Covered the discount code with tests: an unknown code changes nothing. 3 passed.",
    "Refused a code past its date, with a test for it. 4 passed.",
    "Moved the codes into shop/discounts.py, so the catalogue stays what is sold.",
    "A code is now matched whatever its case: welcome10 works too. 5 passed.",
    "Rounded a discount down to a whole cent, with a test at the edge. 6 passed.",
]

_TIDY_LOOP = '''
"""Tidy loop -- the task again and again, and a moment to put things away when it is stopped.

    hmz exec -f @local/tidy_loop -a agent=claude/claude-opus-4-1 -p budget.duration=30m "the task"
"""

import asyncio

from hmz.flows import (
    Agent, AgentCollection, EnvCollection, FlowContext, FlowParams, LocalEnv, flow,
)


class Agents(AgentCollection):
    """The one agent that takes every round."""

    agent: Agent


class Envs(EnvCollection):
    """Where it works: the workspace the run was started in."""

    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def tidy_loop(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """The task again and again, and a moment to put things away when it is stopped."""
    agent = agents["agent"]
    try:
        while True:
            session = await agent.spawn()
            await agent.run(task, session=session, env=envs["workspace"])
    finally:
        await asyncio.sleep(45)
'''


def _seen(app: object, name: str) -> None:
    if _SEEN:
        (Path(_SEEN) / f"{name}.txt").write_text(
            screen(app)  # pyright: ignore[reportArgumentType]
        )


def _look(page: Page, name: str) -> None:
    if _SEEN:
        page.screenshot(path=Path(_SEEN) / f"{name}.png")


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


def _tidy(world: World) -> None:
    """Writes the project's own loop, the one that lingers on its way out."""
    at = world.workspace / ".hmz" / "flows" / "tidy_loop"
    at.mkdir(parents=True)
    (at / "__init__.py").write_text(_TIDY_LOOP)


def _row(page: Page, title: str = "Add a discount") -> Locator:
    """A row of the sidebar, by how its title begins."""
    return page.locator("[data-hmz=sidebar] .side-item").filter(has_text=title).first


def _going(world: World, flow: str = _FLOW) -> str:
    """Starts an epic of a flow and answers its name once it is listed, leaving it going."""
    here = str(world.workspace)
    with world.session() as session:
        sub = session.call("epic.attach", workspace=here)["sub"]
        session.call(
            "epic.start",
            sub=sub,
            flow=flow,
            task=_TASK,
            budget={"duration": 30 * 60},
            agents={"agent": AGENT},
            idem=uuid.uuid4().hex,
        )
        deadline = time.monotonic() + 60
        while True:
            runs = session.call("runs.list", workspace=here)["runs"]
            if found := [str(one["name"]) for one in runs if one["task"] == _TASK]:
                break
            assert time.monotonic() < deadline, "the epic was never listed"
            time.sleep(0.2)
        session.call("epic.detach", sub=sub)
    return found[0]


# -- the app --------------------------------------------------------------------------


def test_an_epic_is_stopped_in_the_app(world: World) -> None:
    world.says({"discount": {"text": _ROUNDS, "after": 2.0}})
    name = _going(world)
    with world.page(desktop=True, height=540) as page:
        go(page, f"/epics/{name}")
        stop = page.get_by_role("button", name="Stop", exact=True)
        expect(stop).to_be_visible()
        expect(page.get_by_text("/2:").first).to_be_visible(timeout=120_000)
        page.get_by_role("button", name="Close panel").click()
        page.wait_for_timeout(600)
        _look(page, "a1-going")
        reel = shots.Reel(f"{_PAGE}-app", window="desktop")
        reel.web(page, hold=1.6, pointer=stop, click=True)
        stop.click()
        expect(page.get_by_text("Stop this epic?")).to_be_visible()
        yes = page.get_by_role("button", name="Stop", exact=True).last
        page.wait_for_timeout(300)
        _look(page, "a2-asked")
        reel.web(page, hold=1.8, pointer=yes, click=True, caption="it asks first")
        yes.click()
        expect(page.get_by_role("button", name="Export")).to_be_visible(timeout=60_000)
        expect(page.get_by_text("Reading its turns")).to_have_count(0)
        expect(_row(page).get_by_text("Stopped")).to_be_visible(timeout=30_000)
        page.wait_for_timeout(600)
        _look(page, "a3-stopped")
        reel.web(page, hold=3.5, caption="stopped", poster=True)
        reel.save()


def test_an_epic_still_unwinding_is_forced_in_the_app(world: World) -> None:
    _tidy(world)
    world.says({"discount": {"text": _ROUNDS, "after": 2.0}})
    name = _going(world, _TIDY)
    with world.page(desktop=True, height=540) as page:
        go(page, f"/epics/{name}")
        stop = page.get_by_role("button", name="Stop", exact=True)
        expect(stop).to_be_visible()
        expect(page.get_by_text("/2:").first).to_be_visible(timeout=120_000)
        page.get_by_role("button", name="Close panel").click()
        stop.click()
        expect(page.get_by_text("Stop this epic?")).to_be_visible()
        page.get_by_role("button", name="Stop", exact=True).last.click()
        force = page.get_by_role("button", name="Force stop")
        expect(force).to_be_visible(timeout=30_000)
        page.wait_for_timeout(400)
        _look(page, "f1-stopping")
        force.click()
        expect(page.get_by_text("Close every session now?")).to_be_visible()
        page.wait_for_timeout(300)
        _look(page, "f2-asked")
        # An epic's page is a heavy one, its graph on a ruled ground: the whole window.
        shots.web(page, f"{_PAGE}-app-force", window="desktop", most=shots.REEL)
        page.get_by_role("button", name="Force stop").last.click()
        expect(page.get_by_role("button", name="Force stop")).to_have_count(
            0, timeout=60_000
        )
        page.wait_for_timeout(500)
        _look(page, "f4-forced")


def test_an_epic_is_stopped_from_the_sidebar(world: World) -> None:
    world.says({"discount": {"text": _ROUNDS, "after": 2.0}})
    name = _going(world)
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        row = _row(page)
        expect(row).to_be_visible()
        row.hover()
        row.get_by_role("button", name="More options").click()
        menu = page.get_by_role("menu")
        item = menu.get_by_role("menuitem", name="Stop")
        expect(item).to_be_visible()
        item.hover()
        page.wait_for_timeout(300)
        _look(page, "s1-menu")
        shots.web(page, f"{_PAGE}-app-menu", clip=menu, pad=44, pointer=item)
        page.keyboard.press("Escape")
    world.stop(name)


def test_a_turn_of_a_chat_is_stopped_in_the_app(world: World) -> None:
    world.says(
        {
            "Rename every price": {
                "text": "Renamed PRICES to AMOUNTS throughout.",
                "tools": [
                    {
                        "name": "Bash",
                        "input": {"command": "grep -rn PRICES shop tests"},
                        "result": "shop/catalogue.py:3:PRICES = {",
                        "takes": 0.5,
                    }
                ],
                "after": 60,
            }
        }
    )
    with world.page(desktop=True, height=540) as page:
        go(page, "/new/chat")
        expect(
            page.get_by_role("button", name=re.compile("Nous: .*Haiku"))
        ).to_be_visible()
        box = page.get_by_role("textbox", name="First message")
        box.click()
        box.press_sequentially(_ASKED)
        page.get_by_role("button", name="Send", exact=True).click()
        stop = page.get_by_role("button", name="Stop", exact=True)
        expect(stop).to_be_visible(timeout=60_000)
        expect(page.get_by_text("grep -rn").first).to_be_visible(timeout=60_000)
        expect(_row(page, "Rename every")).to_be_visible(timeout=30_000)
        page.wait_for_timeout(500)
        _look(page, "c1-open")
        reel = shots.Reel(f"{_PAGE}-app-turn", window="desktop")
        reel.web(page, hold=2.0, pointer=stop, click=True)
        stop.click()
        expect(page.get_by_text("That turn was stopped.")).to_be_visible(timeout=60_000)
        expect(page.get_by_role("button", name="Send", exact=True)).to_be_visible()
        page.wait_for_timeout(500)
        _look(page, "c2-stopped")
        reel.web(page, hold=3.5, poster=True)
        reel.save()


# -- the terminal ---------------------------------------------------------------------


async def test_a_flow_is_stopped_and_forced_in_the_terminal(world: World) -> None:
    _tidy(world)
    world.says({"discount": {"text": _ROUNDS, "after": 2.0}})
    _going(world, _TIDY)
    async with world.tui() as (app, pilot):
        await shows(pilot, "WELCOME10", "ctrl+c twice to stop")
        await shows(pilot, "ctrl+c stop")
        await _settled(pilot)
        _seen(app, "t1-going")
        reel = shots.Reel(f"{_PAGE}-terminal")
        reel.tui(app, hold=1.6)
        await pilot.press("ctrl+c")
        await shows(pilot, "press ctrl+c again to stop the flow")
        await _settled(pilot, 0.2)
        _seen(app, "t2-first")
        reel.tui(app, hold=1.8, keys="ctrl+c", caption="the first press only warns")
        await pilot.press("ctrl+c")
        await shows(pilot, "ctrl+c force stop")
        await _settled(pilot, 0.6)
        _seen(app, "t3-stopping")
        reel.tui(app, hold=2.2, keys="ctrl+c", caption="the second stops the flow")
        await pilot.press("ctrl+c")
        await shows(pilot, "ctrl+c exit")
        await _settled(pilot, 1.0)
        _seen(app, "t4-forced")
        reel.tui(app, hold=3.5, keys="ctrl+c", caption="a third forces it", poster=True)
        reel.save()


async def test_an_epic_is_stopped_from_its_page_in_the_monitor(world: World) -> None:
    world.says({"discount": {"text": _ROUNDS, "after": 2.0}})
    _going(world)
    async with world.tui() as (app, pilot):
        await shows(pilot, "WELCOME10", "ctrl+c twice to stop")
        await pilot.press("left")
        await shows(pilot, "monitor · graph", "time ")
        await _settled(pilot)
        _seen(app, "m1-monitor")
        await pilot.press("up")
        await pilot.pause()
        await pilot.press("enter")
        await shows(pilot, "Running.", "tab actions")
        await _settled(pilot)
        _seen(app, "m2-epic")
        await pilot.press("tab")
        await _settled(pilot)
        _seen(app, "m2b-epic")
        await pilot.press("enter")
        await shows(pilot, "Stop this epic?")
        await _settled(pilot)
        _seen(app, "m3-asked")
        shots.tui(app, f"{_PAGE}-terminal-page")
        await pilot.press("enter")
        await pilot.pause(1.0)
        _seen(app, "m4-after")


async def test_a_turn_of_a_chat_is_stopped_in_the_terminal(world: World) -> None:
    world.says({"Rename every price": {"text": "Renamed.", "after": 60}})
    async with world.tui() as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        await pilot.press(*_ASKED, "enter")
        await shows(pilot, "is working")
        await _settled(pilot, 1.0)
        await pilot.press(*"/stop", "enter")
        await shows(pilot, "That turn was stopped.")
        await _settled(pilot, 1.0)
        _seen(app, "k1-stopped")
        shots.tui(app, f"{_PAGE}-terminal-turn")


# -- the command line -----------------------------------------------------------------


def _interrupted(world: World, after: float = 5.0) -> threading.Thread:
    """Interrupts the `hmz exec` started from here, as ctrl+c does, once its epic is going."""
    here = str(world.workspace)

    def waits() -> None:
        until = time.monotonic() + 90
        while time.monotonic() < until:
            runs = world.call("runs.list", workspace=here)["runs"]
            if any(one["task"] == _TASK for one in runs):
                break
            time.sleep(0.3)
        time.sleep(after)
        for one in psutil.Process().children(recursive=True):
            with contextlib.suppress(psutil.Error, OSError):
                line = one.cmdline()
                if "exec" in line and _TASK in line and "sh" not in line[0]:
                    one.send_signal(signal.SIGINT)

    thread = threading.Thread(target=waits, daemon=True)
    thread.start()
    return thread


def test_exec_is_stopped_by_ctrl_c(world: World) -> None:
    world.says({"discount": {"text": _ROUNDS, "after": 1.5}})
    stopping = _interrupted(world)
    shots.cli(
        [
            "sh",
            "-c",
            (
                f"hmz exec -f {_FLOW} -a agent={AGENT} -p budget.duration=30m"
                f' "{_TASK}"; echo "exit status $?"'
            ),
        ],
        f"{_PAGE}-exec",
    )
    stopping.join(10)

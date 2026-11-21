"""The pictures of `docs/user/leaving.md`: a flow left running, and come back to.

One epic of `ralph_loop`, started in the terminal interface: `/exit` asks what is to become
of it, the app -- open on the same epic while the terminal still is -- lists both frontends,
the terminal detaches, and `hmz` run again in the directory reads the epic from its start and
lists it as going. Beside it, what `hmz exec` prints, which holds its terminal until its epic
ends. Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_leaving.py`.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from hmz.tui.flows import Flows
from hmz.tui.pick import Configures, Confirms, Leaves
from tests.integration.doubles_tui import on, onto, shows, until
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-leaving"

_FLOW = "ralph_loop"
_TASK = "Add a discount code to checkout"

#: What the agent says of the task, round after round, each after a while.
_ROUNDS = {
    "text": [
        "Added a discount code to checkout: charge() takes a code, and WELCOME10 takes 10% off.",
        "Covered the discount code with tests: an unknown code changes nothing. 3 passed.",
        "Refused a code past its date, with a test for it. 4 passed.",
        "Moved the codes into shop/discounts.py, so the catalogue stays what is sold.",
        "A code is now matched whatever its case: welcome10 works too. 5 passed.",
        "Rounded a discount down to a whole cent, with a test at the edge. 6 passed.",
        "Wrote the codes up in README.md, with an example of each.",
        "A cart can take one code only: a second is refused, saying so. 7 passed.",
        "Kept a discount from taking a total below zero. 8 passed.",
        "Typed charge() and its helpers throughout; the type check is clean.",
        "Ran the whole suite twice over: 8 passed, nothing flaky.",
        "Read it through again: the discount code works and its tests pass.",
    ],
    "after": 6.0,
}


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


async def _budgeted(pilot: Pilot[None], flow: str) -> None:
    """Gives a flow half an hour as its budget, on its page of `/flow`, and saves it."""
    await pilot.press(*f"/flow {flow}", "enter")
    await on(pilot, Flows)
    await shows(pilot, "an epic needs one")
    await onto(pilot, "\x1ebudget")
    await pilot.press("enter")
    await on(pilot, Configures)
    await pilot.press("enter")
    await pilot.pause(0.3)
    await pilot.press(*"30m")
    await pilot.press("enter")
    await pilot.pause(0.3)
    await pilot.press("tab")
    await shows(pilot, "enter set")
    await pilot.press("enter")
    await on(pilot, Flows)
    await shows(pilot, "stops at 30m")
    await pilot.press("escape")
    await on(pilot, Confirms)
    await pilot.press("enter")
    await shows(pilot, f"set up: /flow {flow} <task> starts it")


def _in_the_app(world: World) -> None:
    """The app open on the epic the terminal is still attached to: both frontends listed.

    Run on a thread of its own, since the terminal interface holds this one's event loop.
    """
    with world.page(desktop=True) as page:
        row = page.get_by_role("link", name=_TASK).first
        expect(row).to_be_visible()
        row.click()
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        listed = page.locator("[data-hmz=frontends]")
        expect(listed).to_contain_text("tui")
        expect(listed).to_contain_text("this page")
        # Scrolled inside its panel, never the document: the list is the panel's last part.
        listed.scroll_into_view_if_needed()
        # The agent's box counts the seconds it has worked: a frame taken as it ticks is not
        # its screenshot, and is taken again.
        for left in (3, 2, 1, 0):
            try:
                shots.web(page, f"{_PAGE}-app", window="desktop", most=shots.REEL)
            except AssertionError:
                if not left:
                    raise
            else:
                break
        shots.web(page, f"{_PAGE}-frontends", clip=listed, pad=28)


async def test_a_flow_is_left_running_and_found_again(world: World) -> None:
    world.says({"discount": _ROUNDS})
    async with world.tui() as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        await _budgeted(pilot, _FLOW)
        await pilot.press(*f"/flow {_FLOW} {_TASK}", "enter")
        await shows(pilot, "WELCOME10", "ctrl+c twice to stop")
        await _settled(pilot)

        # -- the app, open on the same epic at the same time ------------------------
        await asyncio.to_thread(_in_the_app, world)
        await _settled(pilot)

        # -- leaving it running -----------------------------------------------------
        reel = shots.Reel(f"{_PAGE}-box")
        reel.tui(app, hold=1.4)
        await pilot.press(*"/exit")
        await pilot.pause()
        reel.tui(app, hold=0.9, keys="/exit", cut=True)
        await pilot.press("enter")
        await on(pilot, Leaves)
        await _settled(pilot)
        reel.tui(app, hold=2.2, keys="enter", caption="the box asks")
        await pilot.press("down")
        await pilot.pause()
        reel.tui(app, hold=3.2, keys="down", caption="detach and exit", poster=True)
        reel.save()
        await pilot.press("enter")
        await until(pilot, lambda: not app.is_running, "the interface to close")

    # -- and coming back to it ------------------------------------------------------
    async with world.tui() as (app, pilot):
        await shows(pilot, "WELCOME10", "ctrl+c twice to stop")
        await _settled(pilot, 1.0)
        shots.tui(app, f"{_PAGE}-back")

        await pilot.press(*"/epics", "enter")
        await shows(pilot, "Every epic in this directory")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-epics")
        await pilot.press("escape")
        await _settled(pilot)

        await pilot.press(*"/stop", "enter")
        await shows(pilot, "ctrl+c exit")
        await _settled(pilot, 1.0)


def test_exec_holds_its_terminal_until_its_epic_ends(world: World) -> None:
    world.says(
        {
            "discount": {
                "text": "Added a discount code to checkout: WELCOME10 takes 10% off.",
                "after": 0.8,
            }
        }
    )
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "goal",
            "-a",
            f"worker={AGENT}",
            "-p",
            "budget.duration=30m",
            _TASK,
        ],
        f"{_PAGE}-exec",
        columns=100,
    )

"""The pictures of `docs/user/resuming.md`: an ended epic picked up, on each interface.

One epic of `stateful_ralph`, which can be picked up, ended by its budget, and then carried
on three ways: with **Resume** on its page in the app, from `/epics` and with `/resume` in
the terminal interface, and with `hmz exec --resume` on a command line -- and the refusal a
flow that cannot be picked up gets. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_resuming.py`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from hmz.tui.pick import Does, Epics
from tests.integration.doubles_tui import on, shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-resuming"

#: The flow the page runs, which can be picked up, one that cannot, and the task.
_FLOW = "stateful_ralph"
_PLAIN = "goal"
_TASK = "Add a discount code to checkout"

#: What ends the first epic: a loop that only its budget ends.
_BUDGET = {"output_tokens": 600}

#: What the agent says of the task, round after round: the first epic's budget ends it after
#: eight, and whatever picks it up says the rest.
_ROUNDS = [
    "Added a discount code to checkout: charge() takes a code, and WELCOME10 takes 10% off.",
    "Covered the discount code with tests: an unknown code changes nothing. 3 passed.",
    "Refused a code past its date, with a test for it. 4 passed.",
    "Moved the codes into shop/discounts.py, so the catalogue stays what is sold.",
    "A code is now matched whatever its case: welcome10 works too. 5 passed.",
    "Rounded a discount down to a whole cent, with a test at the edge. 6 passed.",
    "Wrote the codes up in README.md, with an example of each.",
    "Read it through again: the discount code works and its tests pass.",
    "A cart can take one code only: a second is refused, saying so. 7 passed.",
    "Kept a discount from taking a total below zero. 8 passed.",
    "Typed charge() and its helpers throughout; the type check is clean.",
    "Ran the whole suite twice over: 8 passed, nothing flaky.",
    "Named the code that was used on the receipt. 9 passed.",
    "Tidied the tests into one file a module. 9 passed.",
    "Read it through once more: nothing is left to do.",
]


def _stopped(world: World, after: float = 0.3) -> str:
    """An epic of the flow that its budget ended, and its name."""
    world.says({"discount": {"text": _ROUNDS, "after": after}})
    return world.epic(_FLOW, _TASK, budget=_BUDGET)


def _open(page: Page, name: str) -> None:
    """Opens the epic's own page, drawn as an ended epic is."""
    go(page, f"/epics/{name}")
    expect(page.get_by_role("link", name="Resume").first).to_be_visible()
    expect(page.get_by_text("Reading handovers")).to_have_count(0)
    expect(page.get_by_text("Reading its turns")).to_have_count(0)
    expect(page.locator(".side-scroll").get_by_text("Running")).to_have_count(0)


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


# -- in the app -----------------------------------------------------------------------


def test_an_ended_epic_is_resumed_in_the_app(world: World) -> None:
    name = _stopped(world)
    # The epic that picks it up is left going while its pictures are taken.
    world.says({"discount": {"text": _ROUNDS, "after": 60}})
    with world.page(desktop=True) as page:
        _open(page, name)
        resume = page.get_by_role("link", name="Resume").first
        shots.web(
            page,
            f"{_PAGE}-app-ended",
            window="desktop",
            pointer=resume,
            most=shots.REEL,
        )
        resume.click()
        expect(page.get_by_text("Resume epic")).to_be_visible()
        expect(page.get_by_text(f"Picks up {name}")).to_be_visible()
        task = page.get_by_role("textbox", name="Task")
        expect(task).to_have_value(_TASK)
        expect(page.get_by_text("Reading…")).to_have_count(0)
        shots.web(page, f"{_PAGE}-app-form", window="desktop", most=shots.REEL)
        task.press("Enter")
        page.wait_for_url(re.compile(rf".*#/epics/(?!{re.escape(name)})[^/?]+$"))
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        new = page.url.rsplit("/", 1)[-1]
        # Stopped before its record is drawn: a running epic's panel counts its seconds.
        world.stop(new)
        _open(page, new)
        page.get_by_role("tab", name="Epic").click()
        origin = page.get_by_role("link", name=name)
        origin.scroll_into_view_if_needed()
        expect(origin).to_be_visible()
        shots.web(
            page,
            f"{_PAGE}-app-origin",
            clip=page.locator("dl").filter(has=origin),
            pad=4,
        )


def test_resume_is_in_an_epics_menu_in_the_sidebar(world: World) -> None:
    name = _stopped(world)
    with world.page(desktop=True) as page:
        _open(page, name)
        row = page.locator(".side-scroll").get_by_text(_TASK[:18]).first
        row.click(button="right")
        item = page.get_by_role("menuitem", name="Resume")
        expect(item).to_be_visible()
        item.hover()
        shots.web(
            page,
            f"{_PAGE}-app-menu",
            clip=page.get_by_role("menu"),
            pad=24,
            pointer=item,
        )


# -- in the terminal ------------------------------------------------------------------


async def test_an_epic_is_resumed_in_the_terminal(world: World) -> None:
    _stopped(world)
    world.says({"discount": {"text": _ROUNDS, "after": 6.0}})
    async with world.tui() as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)

        # -- from the list of epics: any epic, by its row ---------------------------
        reel = shots.Reel(f"{_PAGE}-terminal-epics")
        await pilot.press(*"/epics")
        await pilot.pause()
        reel.tui(app, hold=1.0, keys="/epics", cut=True)
        await pilot.press("enter")
        await on(pilot, Epics)
        await shows(pilot, "Every epic in this directory")
        await _settled(pilot)
        reel.tui(app, hold=2.0, keys="enter")
        await pilot.press("enter")
        await on(pilot, Does)
        await shows(pilot, "resume epic")
        await _settled(pilot)
        reel.tui(app, hold=2.4, keys="enter", caption="resume epic", poster=True)
        await pilot.press("enter")
        await shows(pilot, "ctrl+c twice to stop", "Worked for")
        await _settled(pilot, 1.0)
        reel.tui(app, hold=3.2, keys="enter", caption="a new epic picks it up")
        reel.save()

        # -- and with /resume: the last one here, once a flow is on the screen ------
        await pilot.press(*"/stop", "enter")
        await shows(pilot, "ctrl+c exit")
        await _settled(pilot, 1.0)
        await pilot.press(*"/resume", "enter")
        await shows(pilot, "ctrl+c twice to stop", "Worked for")
        await _settled(pilot, 1.0)
        shots.tui(app, f"{_PAGE}-terminal-resume")
        await pilot.press(*"/stop", "enter")
        await shows(pilot, "ctrl+c exit")
        await _settled(pilot, 1.0)


# -- from the command line ------------------------------------------------------------


def test_an_epic_is_resumed_from_the_command_line(world: World) -> None:
    _stopped(world)
    world.says({"discount": {"text": _ROUNDS, "after": 0.6}})
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            _FLOW,
            "-a",
            f"agent={AGENT}",
            "-p",
            "budget.output_tokens=300",
            "--resume",
            _TASK,
        ],
        f"{_PAGE}-exec",
        columns=100,
    )


def test_a_flow_that_cannot_be_resumed_is_refused(world: World) -> None:
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            _PLAIN,
            "-a",
            f"worker={AGENT}",
            "-p",
            "budget.output_tokens=300",
            "--resume",
            _TASK,
        ],
        f"{_PAGE}-refused",
        columns=100,
    )

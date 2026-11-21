"""The pictures of `docs/tutorials/overnight-run.md`: a long task left running overnight.

One journey, as the page tells it: a flow is given a time and a cost budget in the terminal
and set to work, its person says they are away, the terminal is closed with the epic left
going, and `hmz` run again in the directory finds what became of it, picks it up where its
budget ended it, and reads it back. The app's side of the same journey is beside it: the
budget of a new epic, the People tab, the notifications, and the epic once it is over. Run it
by naming it: `uv run pytest tests/system/docs/test_docs_tutorials_overnight_run.py`.

A price list is staged here, since the world comes with none and a cost limit on a model
nobody prices says so on screen: a file of made-up list prices for the stand-in's models,
read as `HUMANIZE_PRICES` names it.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from hmz.tui.flows import Flows
from hmz.tui.pick import Configures, Confirms, Leaves
from tests.integration.doubles_tui import on, onto, shows, until
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "tutorials-overnight-run"

#: The flow the page runs, which can be picked up, and the task it is set.
_FLOW = "stateful_ralph"
_TASK = "Add a discount code to checkout"


@pytest.fixture(autouse=True)
def _prices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A price list for the stand-in's models, so that a cost limit holds what they spend."""

    def model(ident: str, name: str, into: float, out: float) -> dict[str, object]:
        return {
            "id": ident,
            "name": name,
            "provider": "anthropic",
            "pricingItems": [
                {"category": "input_tokens", "price": into},
                {"category": "output_tokens", "price": out},
            ],
        }

    at = tmp_path / "prices.json"
    at.write_text(
        json.dumps(
            {
                "currency": "USD",
                "unit": "per 1M tokens",
                "versions": [
                    {
                        "date": "2026-09-01",
                        "models": [
                            model("claude-haiku-4-5", "Claude Haiku 4.5", 600, 3000),
                            model("claude-opus-4-1", "Claude Opus 4.1", 600, 3000),
                        ],
                    }
                ],
            }
        )
    )
    monkeypatch.setenv("HUMANIZE_PRICES", str(at))


#: What the agent says of the task, round after round, each after a while. No tool is said
#: to be used: the stand-in counts a tool's tokens twice over, and the bill is in the picture.
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
    "after": 3.0,
}


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


async def test_an_epic_is_budgeted_left_and_found_again(world: World) -> None:
    world.says({"discount": _ROUNDS})
    async with world.tui() as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)

        # -- a time and a cost budget -----------------------------------------------
        reel = shots.Reel(f"{_PAGE}-budget")
        await pilot.press(*f"/flow {_FLOW}", "enter")
        await on(pilot, Flows)
        await shows(pilot, "an epic needs one")
        await onto(pilot, "\x1ebudget")
        await pilot.pause()
        reel.tui(app, hold=1.6, keys="down", caption="to budget")
        await pilot.press("enter")
        await on(pilot, Configures)
        await shows(pilot, f"Set budget for {_FLOW}")
        reel.tui(app, hold=1.2, keys="enter")
        await pilot.press("enter")
        await pilot.pause(0.3)
        await pilot.press(*"8h")
        await pilot.pause(0.3)
        reel.tui(app, hold=1.2, keys="enter 8h", caption="eight hours")
        await pilot.press("enter")
        await pilot.pause(0.3)
        await pilot.press("down", "enter")
        await pilot.pause(0.3)
        await pilot.press(*"20")
        await pilot.pause(0.3)
        reel.tui(app, hold=1.2, keys="down enter 20", caption="twenty dollars")
        await pilot.press("enter")
        await pilot.pause(0.3)
        await pilot.press("tab")
        await shows(pilot, "enter set")
        reel.tui(app, hold=1.0, keys="enter tab", caption="to Set")
        await pilot.press("enter")
        await on(pilot, Flows)
        await _settled(pilot)
        reel.tui(app, hold=1.8, keys="enter")
        await pilot.press("escape")
        await on(pilot, Confirms)
        await pilot.press("enter")
        await shows(pilot, f"set up: /flow {_FLOW} <task> starts it")
        await _settled(pilot)
        reel.tui(app, hold=3.0, keys="esc enter", caption="saved", poster=True)
        reel.save()

        # -- the task, and saying nobody is here ------------------------------------
        await pilot.press(*f"/flow {_FLOW} {_TASK}", "enter")
        await shows(pilot, "WELCOME10", "ctrl+c twice to stop")
        await _settled(pilot)
        await pilot.press(*"/afk", "enter")
        await shows(pilot, "away: agents that ask are told nobody is here")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-away")

        # -- leaving it running -----------------------------------------------------
        reel = shots.Reel(f"{_PAGE}-leave")
        reel.tui(app, hold=1.2)
        await pilot.press(*"/exit")
        await pilot.pause()
        reel.tui(app, hold=0.8, keys="/exit", cut=True)
        await pilot.press("enter")
        await on(pilot, Leaves)
        await _settled(pilot)
        reel.tui(app, hold=1.8, keys="enter")
        await pilot.press("down")
        await pilot.pause()
        reel.tui(app, hold=3.0, keys="down", caption="detach and exit", poster=True)
        reel.save()
        await pilot.press("enter")
        await until(pilot, lambda: not app.is_running, "the interface to close")

    # -- and coming back to it ------------------------------------------------------
    async with world.tui() as (app, pilot):
        await shows(pilot, "WELCOME10")
        await shows(pilot, "ctrl+c exit")
        await _settled(pilot, 1.0)
        shots.tui(app, f"{_PAGE}-back")

        # -- picked up where its budget ended it ------------------------------------
        await pilot.press(*"/resume", "enter")
        await shows(pilot, "ctrl+c twice to stop")
        await _settled(pilot, 3.0)
        shots.tui(app, f"{_PAGE}-resumed")
        await pilot.press(*"/stop", "enter")
        await shows(pilot, "ctrl+c exit")
        await _settled(pilot, 1.0)

        # -- and read back ----------------------------------------------------------
        await pilot.press(*"/epics", "enter")
        await shows(pilot, "Every epic in this directory")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-epics")
        await pilot.press("enter")
        await _settled(pilot, 1.0)


# -- the app's side of it -------------------------------------------------------------


def _going(world: World, flow: str, task: str, agents: dict[str, str]) -> str:
    """Starts an epic and answers its name once it is listed, leaving it going.

    `World.epic(until=None)` reads the list of epics the moment the epic has started, which
    for a flow of the project's own is before it is listed there: this waits for it.
    """
    here = str(world.workspace)
    with world.session() as session:
        sub = session.call("epic.attach", workspace=here)["sub"]
        session.call(
            "epic.start",
            sub=sub,
            flow=flow,
            task=task,
            budget={"cost": 20, "duration": 8 * 3600},
            agents=agents,
            idem=uuid.uuid4().hex,
        )
        deadline = time.monotonic() + 60
        while True:
            runs = session.call("runs.list", workspace=here)["runs"]
            if found := [str(one["name"]) for one in runs if one["task"] == task]:
                break
            assert time.monotonic() < deadline, "the epic was never listed"
            time.sleep(0.2)
        session.call("epic.detach", sub=sub)
    return found[0]


def test_a_new_epic_is_given_its_budget_in_the_app(world: World) -> None:
    with world.page(desktop=True) as page:
        go(page, f"/new?flow={_FLOW}")
        cost = page.get_by_label("Most it may cost, in dollars")
        expect(cost).to_be_visible()
        expect(page.get_by_text("Asking")).to_have_count(0)
        cost.fill("20")
        page.get_by_label("Longest it may take, in minutes").fill("480")
        page.get_by_role("textbox", name="Task").fill(_TASK)
        shots.web(page, f"{_PAGE}-app-budget", window="desktop", most=shots.REEL)


def test_notifications_are_chosen_in_the_app(world: World) -> None:
    with world.page(desktop=True) as page:
        go(page, "/settings/notifications")
        expect(page.get_by_text("Kinds")).to_be_visible()
        shots.web(
            page, f"{_PAGE}-app-notifications", clip=page.get_by_role("dialog"), pad=0
        )


def test_a_person_says_they_are_away_in_the_app(world: World) -> None:
    world.says(
        {"discount": {"text": "Added a discount code to checkout.", "after": 60}}
    )
    name = _going(world, "@local/sign_off", _TASK, {"coder": AGENT})
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        # The agent's box counts the seconds it has worked: a frame taken as it ticks is not
        # its screenshot, and the reel is taken again from where it began.
        for left in (2, 1, 0):
            reel = shots.Reel(f"{_PAGE}-app-away", window="desktop")
            people = page.get_by_role("tab", name="People")
            reel.web(page, hold=1.4, pointer=people, click=True)
            people.click()
            away = page.get_by_role("button", name="Away for all")
            expect(away).to_be_visible()
            reel.web(page, hold=1.6, pointer=away, click=True)
            away.click()
            back = page.get_by_role("button", name="Back for all")
            expect(back).to_be_visible()
            reel.web(page, hold=3.5, poster=True)
            try:
                reel.save()
            except AssertionError:
                if not left:
                    raise
                back.click()
                expect(away).to_be_visible()
                page.get_by_role("tab", name="Epic").click()
            else:
                break
    world.stop(name)


def test_an_epic_its_budget_ended_is_read_in_the_app(world: World) -> None:
    world.says({"discount": _ROUNDS | {"after": 1.0}})
    name = world.epic(_FLOW, _TASK, budget={"cost": 20, "duration": 8 * 3600})
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_role("link", name="Resume").first).to_be_visible()
        expect(page.get_by_text("Reading handovers")).to_have_count(0)
        expect(page.get_by_text("Reading its turns")).to_have_count(0)
        shots.web(page, f"{_PAGE}-app-ended", window="desktop", most=shots.REEL)

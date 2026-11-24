"""The pictures of `docs/user/budgets.md`: what an epic may spend, and what its limits do.

Each interface where a budget is set and read, as the page tells it: the Budget fields of the
app's New epic page, the meters of an epic going and what the app says of one its budget
ended; the terminal's budget sheet and the epic's own page with its meters; and `hmz exec`
stopped by a limit, and warned of a cost limit over a model nobody prices. Run it by naming
it: `uv run pytest tests/system/docs/test_docs_user_budgets.py`.

A price list is staged for the scenes that show a cost counted, since the world comes with
none: a file of made-up list prices for the stand-in's models, read as `HUMANIZE_PRICES`
names it. The scene of the unpriced model leaves the world as it comes, with no list.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from hmz.coganchor import prices
from hmz.tui.flows import Flows
from hmz.tui.pick import Configures, Confirms
from tests.integration.doubles_tui import on, onto, screen, shows, until
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-budgets"

#: The flow the page runs, which only its budget ends, and the task it is set.
_FLOW = "ralph_loop"
_TASK = "Add a discount code to checkout"


@pytest.fixture
def priced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
                            model("claude-haiku-4-5", "Claude Haiku 4.5", 300, 1500),
                            model("claude-opus-4-1", "Claude Opus 4.1", 300, 1500),
                        ],
                    }
                ],
            }
        )
    )
    monkeypatch.setenv("HUMANIZE_PRICES", str(at))
    # One list is held per process: a scene run after another reads its own, not the last's.
    monkeypatch.setattr(prices, "_listing", None)
    monkeypatch.setattr(prices, "_read_from", None)
    monkeypatch.setattr(prices, "_tried", 0.0)


#: What the agent says of the task, round after round. No tool is said to be used: the
#: stand-in counts a tool's tokens twice over, and the bill is in the picture.
_ROUNDS = [
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
]


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


def _going(world: World, budget: dict[str, object]) -> str:
    """Starts an epic of the flow and answers its name once it is listed, leaving it going."""
    here = str(world.workspace)
    with world.session() as session:
        sub = session.call("epic.attach", workspace=here)["sub"]
        session.call(
            "epic.start",
            sub=sub,
            flow=_FLOW,
            task=_TASK,
            budget=budget,
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


def test_a_new_epic_is_given_its_budget_in_the_app(world: World) -> None:
    with world.page(desktop=True) as page:
        go(page, f"/new?flow={_FLOW}")
        cost = page.get_by_label("Most it may cost, in dollars")
        expect(cost).to_be_visible()
        cost.fill("5")
        page.get_by_label("Longest it may take, in minutes").fill("30")
        page.get_by_label("Most output tokens it may write").fill("200000")
        page.get_by_role("textbox", name="Task").fill(_TASK)
        page.get_by_label("Cost graceful").uncheck()
        group = page.locator("section.option-group").filter(
            has=page.get_by_role("heading", name="Budget")
        )
        shots.web(page, f"{_PAGE}-form", clip=group, pad=10)


@pytest.mark.usefixtures("priced")
def test_the_meters_of_an_epic_going_in_the_app(world: World) -> None:
    world.says({"discount": {"text": _ROUNDS, "after": 3.0}})
    name = _going(
        world,
        {"cost": 20, "duration": 30 * 60, "output_tokens": 2000, "graceful": True},
    )
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        expect(page.get_by_role("meter").first).to_be_visible()
        expect(page.get_by_text("of $20.00")).to_be_visible()
        expect(page.get_by_text("of $20.00")).not_to_contain_text(
            "$0.00 of", timeout=60_000
        )
        page.wait_for_timeout(9000)
        shots.web(page, f"{_PAGE}-meters", window="desktop", most=shots.REEL)
        tiles = page.locator(".tiles").filter(has=page.get_by_role("meter")).first
        shots.web(page, f"{_PAGE}-meters-tiles", clip=tiles, pad=6)
    world.stop(name)


@pytest.mark.usefixtures("priced")
def test_an_epic_its_budget_ended_in_the_app(world: World) -> None:
    world.says({"discount": {"text": _ROUNDS, "after": 0.5}})
    name = world.epic(_FLOW, _TASK, budget={"cost": 3, "duration": 30 * 60})
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_role("main").get_by_text("stopped").first).to_be_visible()
        expect(page.get_by_text("Reading its turns")).to_have_count(0)
        shots.web(page, f"{_PAGE}-spent", window="desktop", most=shots.REEL)


# -- the terminal ---------------------------------------------------------------------


@pytest.mark.usefixtures("priced")
async def test_a_budget_is_set_and_read_in_the_terminal(world: World) -> None:
    world.says({"discount": {"text": _ROUNDS, "after": 2.0}})
    async with world.tui() as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)

        # -- the sheet --------------------------------------------------------------
        reel = shots.Reel(f"{_PAGE}-sheet")
        await pilot.press(*f"/flow {_FLOW}", "enter")
        await on(pilot, Flows)
        await shows(pilot, "an epic needs one")
        await onto(pilot, "\x1ebudget")
        await pilot.pause()
        reel.tui(app, hold=1.6, keys="down", caption="to budget")
        await pilot.press("enter")
        await on(pilot, Configures)
        await shows(pilot, f"Set budget for {_FLOW}")
        reel.tui(app, hold=1.4, keys="enter")
        await pilot.press("enter")
        await pilot.pause(0.3)
        await pilot.press(*"30m")
        await pilot.pause(0.3)
        await pilot.press("enter")
        await pilot.pause(0.3)
        reel.tui(app, hold=1.2, keys="enter 30m enter", caption="thirty minutes")
        await pilot.press("down", "enter")
        await pilot.pause(0.3)
        await pilot.press(*"20")
        await pilot.pause(0.3)
        await pilot.press("enter")
        await pilot.pause(0.3)
        reel.tui(app, hold=1.2, keys="down enter 20 enter", caption="twenty dollars")
        await pilot.press("down", "enter")
        await pilot.pause(0.3)
        await pilot.press(*"2000")
        await pilot.pause(0.3)
        await pilot.press("enter")
        await pilot.pause(0.3)
        reel.tui(app, hold=1.6, keys="down enter 2000 enter", caption="2,000 tokens")
        await pilot.press("tab")
        await shows(pilot, "enter Set")
        reel.tui(app, hold=1.0, keys="tab", caption="to Set")
        await pilot.press("enter")
        await on(pilot, Flows)
        await _settled(pilot)
        reel.tui(app, hold=3.0, keys="enter", caption="the budget row", poster=True)
        reel.save()
        await pilot.press("escape")
        await on(pilot, Confirms)
        await pilot.press("enter")
        await shows(pilot, f"set up: /flow {_FLOW} <task> starts it")
        await _settled(pilot)

        # -- the epic's own page, with its meters -----------------------------------
        await pilot.press(*f"/flow {_FLOW} {_TASK}", "enter")
        await shows(pilot, "5 passed")
        await pilot.press("left")
        await shows(pilot, "monitor · graph", "time ")
        await _settled(pilot)
        await pilot.press("up")
        await pilot.pause()
        await pilot.press("enter")
        await shows(pilot, "when spent")
        await until(
            pilot, lambda: "$0.00 of" not in screen(app), "a cost to be counted"
        )
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-epic-page")
        await pilot.press("escape")
        await pilot.press("right")
        await pilot.press(*"/stop", "enter")
        await shows(pilot, "ctrl+c exit")


# -- the command line -----------------------------------------------------------------


def test_exec_is_stopped_by_its_budget(world: World) -> None:
    world.says({"discount": {"text": _ROUNDS, "after": 0.3}})
    shots.cli(
        [
            "sh",
            "-c",
            (
                f"hmz exec -f {_FLOW} -a agent={AGENT}"
                " -p budget.output_tokens=300 -p budget.duration=10m"
                f' "{_TASK}"; echo "exit status $?"'
            ),
        ],
        f"{_PAGE}-exec",
        columns=100,
    )


def test_exec_says_a_cost_limit_cannot_hold_an_unpriced_model(world: World) -> None:
    world.says({"discount": {"text": _ROUNDS[0], "after": 0.3}})
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "goal",
            "-a",
            f"worker={AGENT}",
            "-p",
            "budget.cost=5",
            "Add a discount code",
        ],
        f"{_PAGE}-unpriced",
        columns=100,
    )

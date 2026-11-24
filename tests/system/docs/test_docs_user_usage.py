"""The pictures of `docs/user/usage.md`: what a chat or an epic costs, and where that is read.

Each interface the page tells of: the app's Usage ring under a chat's box and the popup it
opens, the Usage page of its Settings, and the Spending table of an epic going; the terminal's
cost readout and monitor, and its `/settings usage`; and the bill `hmz exec` prints under each
turn. Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_usage.py`.

Two things are staged that the world comes without:

- prices: a file of made-up list prices for the stand-in's models, read as `HUMANIZE_PRICES`
  names it, since nothing is fetched here and a model nobody prices is shown with no money;
- earlier days: every chat and epic of a scene is run now, so some are then written down as
  begun a few days ago -- each moment of their records moved back by whole days, and their
  directories named for it -- for a page of spending by day to have more than today on it.
"""

from __future__ import annotations

import datetime
import json
import re
import time
import uuid
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from hmz.coganchor import prices
from hmz.rpc.errors import RpcError
from hmz.runtime.kept import Runs
from tests.integration.doubles_tui import screen, shows, until
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-usage"

_TASK = "Add a discount code to checkout"

#: The stand-in's other model, which one scene leaves with no price.
_OPUS = "claude/claude-opus-4-1"


def _priced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *models: str) -> None:
    """Stages a price list for some of the stand-in's models."""
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
                            {
                                "id": ident,
                                "name": ident,
                                "provider": "anthropic",
                                "pricingItems": [
                                    {"category": "input_tokens", "price": 300},
                                    {"category": "output_tokens", "price": 1500},
                                ],
                            }
                            for ident in models
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


@pytest.fixture
def priced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A price for both of the stand-in's models."""
    _priced(tmp_path, monkeypatch, MODEL, "claude-opus-4-1")


@pytest.fixture
def half_priced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A price for one of the stand-in's models, and none for the other."""
    _priced(tmp_path, monkeypatch, MODEL)


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
]

_STAMP = re.compile(r"^(\d{8})T(\d{6}\.\d{3}Z.*)$")
_AT = re.compile(r'("at": ?")(\d{4}-\d{2}-\d{2})(T)')


def _earlier(world: World, name: str, days: int) -> None:
    """Writes a chat or an epic that has ended down as begun some days earlier."""
    back = datetime.timedelta(days=days)
    (at,) = [one for one in world.data.rglob(name) if one.is_dir()]
    # Its last lines are written a moment after it is said to have ended: none is lost.
    deadline = time.monotonic() + 60
    while not any('"ended"' in one.read_text() for one in at.glob("*.jsonl")):
        assert time.monotonic() < deadline, f"{name} never ended"
        time.sleep(0.2)
    time.sleep(0.5)
    for record in at.glob("*.jsonl"):
        record.write_text(
            _AT.sub(
                lambda found: (
                    found[1]
                    + (datetime.date.fromisoformat(found[2]) - back).isoformat()
                    + found[3]
                ),
                record.read_text(),
            )
        )
    stamp = _STAMP.match(name)
    assert stamp, name
    day = datetime.datetime.strptime(stamp[1], "%Y%m%d").date() - back  # noqa: DTZ007
    at.rename(at.with_name(f"{day:%Y%m%d}T{stamp[2]}"))


def _epic(world: World, flow: str, task: str, **budget: float) -> str:
    """Runs an epic to its end, once the one before it has let go of the project's slot.

    An epic its budget ended is said to have ended a moment before its host is free again,
    and one started in that moment is refused.
    """
    deadline = time.monotonic() + 60
    while True:
        try:
            return world.epic(flow, task, budget=budget or None)
        except RpcError as refused:
            if "already running" not in str(refused) or time.monotonic() > deadline:
                raise
            time.sleep(0.5)


def _week(world: World) -> str:
    """A week of work in the project: chats and epics of three flows, today's chat last.

    Returns:
      The chat of today.
    """
    world.says(
        {
            "meticulous reviewer": {
                "json": {"done": True, "notes": "It works: 6 passed."},
                "after": 2.0,
            },
            "currency": {
                "text": "Prices now show a currency symbol: format_price() in"
                " shop/catalogue.py, used by the cart. 4 passed.",
                "after": 3.0,
            },
            "whole cents": {
                "text": "Prices are whole cents throughout: the catalogue refuses a"
                " fraction, and a test says so. 5 passed.",
                "after": 2.0,
            },
            "How does checkout": {
                "text": "charge() in shop/checkout.py takes the cart and returns what it"
                " comes to, in cents. It calls total() in shop/cart.py.",
                "after": 1.5,
            },
            "Where would a discount": {
                "text": "In charge(), after total(): take the code as a second argument"
                " and subtract its share before returning.",
                "after": 1.5,
            },
            "empty cart": {
                "text": "total() returns 0 for an empty cart, and a test now says so.",
                "after": 2.0,
            },
            "discount": {"text": _ROUNDS, "after": 2.0},
        }
    )
    then = [
        (_epic(world, "ralph_loop", _TASK, output_tokens=700), 5),
        (world.chat("What does an empty cart come to?"), 4),
        (_epic(world, "goal", "Show prices with a currency symbol"), 3),
        (
            _epic(
                world,
                "ralph_loop",
                "Test the discount code at its edges",
                output_tokens=400,
            ),
            2,
        ),
        (_epic(world, "rlar", "Refuse a discount code past its date"), 1),
        (_epic(world, "goal", "Keep prices in whole cents"), 1),
    ]
    for name, days in then:
        _earlier(world, name, days)
    _epic(world, "rlar", "Take a discount code whatever its case")
    return world.chat("How does checkout work?", "Where would a discount code go?")


def _going(world: World, flow: str, agents: dict[str, str]) -> str:
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
            agents=agents,
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


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


# -- the app --------------------------------------------------------------------------


@pytest.mark.usefixtures("priced")
def test_the_usage_ring_of_a_chat_and_the_usage_page(world: World) -> None:
    chat = _week(world)
    with world.page(desktop=True) as page:
        go(page, f"/chats/{chat}")
        expect(page.get_by_role("log")).to_contain_text("second")
        ring = page.get_by_role("button", name="Usage", exact=True)
        expect(ring).to_be_visible()
        expect(page.get_by_text("1 live")).to_have_count(0)
        page.wait_for_timeout(800)

        reel = shots.Reel(f"{_PAGE}-chip", window="desktop")
        reel.web(page, hold=1.6, pointer=ring, click=True, caption="the Usage ring")
        ring.click()
        popup = page.locator("[data-hmz=usage-pop]")
        expect(popup.get_by_text("Last 7 days")).to_be_visible()
        expect(popup.get_by_text("Over 8 chats and epics")).to_be_visible()
        page.wait_for_timeout(600)
        shots.web(page, f"{_PAGE}-popup", clip=popup, pad=14)
        link = popup.get_by_text("Usage settings")
        reel.web(
            page,
            hold=3.2,
            pointer=link,
            click=True,
            caption="this chat, then the folder",
        )
        link.click()
        expect(page.get_by_role("heading", name="By flow")).to_be_visible()
        expect(page.get_by_role("link", name="rlar", exact=True)).to_be_visible()
        page.wait_for_timeout(800)
        reel.web(page, hold=3.6, caption="Usage settings", poster=True)
        reel.save()

        shots.web(page, f"{_PAGE}-page", window="desktop", most=shots.REEL)

        # What each flow spent, further down the page.
        flows = page.locator("section.panel").filter(
            has=page.get_by_role("heading", name="By flow")
        )
        flows.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        shots.web(page, f"{_PAGE}-by-flow", clip=flows, pad=0)


@pytest.mark.usefixtures("half_priced")
def test_the_spending_of_an_epic_going_with_a_model_nobody_prices(
    world: World,
) -> None:
    world.says(
        {
            "meticulous reviewer": {
                "json": [
                    {"done": False, "notes": "A code past its date is still accepted."},
                ],
                "after": 1.0,
            },
            "still accepted": {"text": _ROUNDS[2], "after": 240},
            "discount": {"text": _ROUNDS[0], "after": 1.0},
        }
    )
    name = _going(world, "rlar", {"actor": _OPUS, "reviewer": AGENT})
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        table = page.locator("[data-hmz=spending]")
        expect(table).to_contain_text("Haiku", timeout=90_000)
        expect(table).to_contain_text("Opus", timeout=90_000)
        expect(table).to_contain_text("$", timeout=90_000)
        page.wait_for_timeout(7000)
        section = page.locator("section").filter(has=table).last
        shots.web(page, f"{_PAGE}-spending", clip=section, pad=12)
    world.stop(name)


# -- the terminal ---------------------------------------------------------------------


@pytest.mark.usefixtures("priced")
async def test_the_tally_of_an_epic_and_the_usage_page_in_the_terminal(
    world: World,
) -> None:
    _week(world)
    world.says(
        {
            "meticulous reviewer": {
                "json": {
                    "done": False,
                    "notes": "A code past its date is still accepted.",
                },
                "after": 1.0,
            },
            "still accepted": {"text": _ROUNDS[2], "after": 240},
            "discount": {"text": _ROUNDS[0], "after": 1.0},
        }
    )
    async with world.tui(size=(100, 32)) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)

        # -- /settings usage --------------------------------------------------------
        await pilot.press(*"/settings usage", "enter")
        await shows(pilot, "BY FLOW", "rlar")
        await _settled(pilot, 1.0)
        shots.tui(app, f"{_PAGE}-terminal-page")
        await pilot.press("escape")
        await _settled(pilot)
        await pilot.press("escape")
        await _settled(pilot)

        # -- an epic going: the readout over the editor, and the monitor ------------
        app.settings.remember(
            "rlar",
            {"actor": Runs(_OPUS), "reviewer": Runs(AGENT)},
            {},
            None,
            {"duration": "PT30M"},
        )
        await pilot.press(*f"/flow rlar {_TASK}", "enter")
        await shows(pilot, "ctrl+c twice to stop")
        await until(pilot, lambda: "out/s" in screen(app), "a rate over the editor")
        await _settled(pilot, 8.0)
        shots.tui(app, f"{_PAGE}-readout")
        await pilot.press("left")
        await shows(pilot, "monitor · graph", "Tokens", "Kinds")
        await _settled(pilot, 1.0)
        shots.tui(app, f"{_PAGE}-monitor")
        await pilot.press("right")
        await pilot.press(*"/stop", "enter")
        await _settled(pilot, 2.0)


# -- the command line -----------------------------------------------------------------


@pytest.mark.usefixtures("priced")
def test_exec_prints_what_each_turn_cost(world: World) -> None:
    world.says(
        {
            "meticulous reviewer": {
                "json": {"done": True, "notes": "It works: 3 passed."},
                "after": 2.0,
            },
            "discount": {"text": _ROUNDS[0], "after": 3.0},
        }
    )
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "rlar",
            "-a",
            f"actor={_OPUS}",
            "-a",
            f"reviewer={AGENT}",
            "-p",
            "budget.cost=5",
            _TASK,
        ],
        f"{_PAGE}-exec",
        columns=96,
    )

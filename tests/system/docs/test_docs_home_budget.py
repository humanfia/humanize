"""The home page's Budget scene: a run held to a budget, and stopped by it.

`docs/index.md` plays one scene at a time on one stage (`home.py`). This one is the epic of
the page's task with a budget of three limits -- cost, output tokens and time -- as its Epic
panel reads them while the agents work: a meter for each, filling turn after turn, until the
cost meter is full and the budget ends the run. `home-budget` is Humanize Desktop's window,
its sidebar folded, the two agents side by side across the graph and the panel beside them;
`home-budget-phone` is the web page on a phone, where the panel is a sheet and its meters are
most of the screen, under the head of the reviewer in what the sheet leaves of the graph. Run
it by naming it: `uv run pytest tests/system/docs/test_docs_home_budget.py`.

A price list is staged, since the world comes with none and a cost limit counts only what is
priced: a file of made-up list prices for the stand-in's models, read as `HUMANIZE_PRICES`
names it. Only what an agent writes is priced, and every turn is scripted to write as much as
any other, so a turn costs one dollar to the cent and the fifth meets the five the epic may
spend. The reviewer is scripted never to be satisfied, so that only the budget ends it. The
limits of tokens and of time are there to be seen part spent, and are never reached.

The reels open on the second turn's end, two dollars of the five spent, not on the first's:
until the reviewer has handed the work back once, the panel's Handovers are one line and not
two, and everything under them stands a line higher -- the heading of its Environments cut in
half by the window's edge, in that one frame and no other.

What the reels cannot show, the product not drawing it: the meters any larger. They are drawn
in one place, the Budget tile of the Epic panel -- a quarter of its figures, in a panel as
wide at a desk as it is (320 pixels of this window), whose sections under them do not fold.
"""

from __future__ import annotations

import json
import math
import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from hmz.coganchor import prices
from tests.system.docs import home, shots
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from playwright.sync_api import Locator, Page

    from tests.system.docs.conftest import World

#: What the epic may spend: the cost is what it reaches, the other two some half spent by
#: then.
_BUDGET = {"cost": 5, "output_tokens": 800, "duration": 45}

#: What a million tokens written cost: made up, and a dollar for the hundred of every turn.
#: What an agent reads is priced at nothing, since how much it reads changes with the names
#: the agents are given, which are made up anew each run.
_PRICE = 10_000

#: How many tokens the stand-in says a turn wrote, by how long what it said is.
_WRITTEN = 100

#: Seconds a turn takes: long enough that a frame is taken between one turn's end and the next.
_PACE = 4.0

#: The first turn whose end is shown: the reviewer's first, which hands the work back.
_FIRST = 2

#: The seconds each turn's end is shown for, from that one, before the last one's, of the
#: run stopped.
_HOLDS = (1.3, 1.3, 1.5)

#: How long a turn's end, or the run's, is waited for: many times what one takes, since the
#: other scenes are taken beside this one.
_PATIENCE = 60_000

#: How near where it was put something in the graph has to be found, in CSS pixels.
_NEAR = 2

#: How far the desk's flow stands from the sides of its canvas, and from its top: in the
#: canvas's middle once the reviewer has opened its sessions.
_EDGE = 16
_UNDER = 150

#: How wide an agent is drawn in the phone's graph, in CSS pixels: its head as tall as the
#: strip of the graph left over the sheet.
_HEAD_WIDE = 190

#: And how far from the canvas's left side: nearer than the gap an arrow leaves before the
#: agent it ends at, so that the end of the one from the actor, who is off the picture, is
#: off it too and not a stub of a stroke beside the reviewer.
_HEAD_AT = 3

#: What the reviewer asks for, round after round, and what the actor says it did about it,
#: each as long as the other so that each turn costs the same. No tool is said to be used:
#: the stand-in counts a tool's tokens twice over, and the bill is the picture.
_NOTES = (
    "Cover one more case of the coupon with a test, keep pytest passing, "
    "and say how many pass now."
)
_ROUNDS = [
    (
        "Checkout takes a coupon now: WELCOME10 is 10% off, applied to the cart's total "
        "in shop/checkout.py. pytest says 6 passed."
    ),
    (
        "Covered an unknown coupon with a test in tests/test_checkout.py: it changes "
        "nothing about the total. pytest says 7 passed."
    ),
    (
        "Refused a coupon past its date in shop/checkout.py, with a test for it beside "
        "the others. pytest says 8 passed, all green."
    ),
]
_REVIEW = {"done": False, "notes": _NOTES}


@pytest.fixture(autouse=True)
def _prices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A price list for the stand-in's models, so that a cost limit holds what they spend."""

    def model(ident: str, name: str) -> dict[str, object]:
        return {
            "id": ident,
            "name": name,
            "provider": "anthropic",
            "pricingItems": [
                {"category": "output_tokens", "price": _PRICE},
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
                            model("claude-haiku-4-5", "Claude Haiku 4.5"),
                            model("claude-opus-4-1", "Claude Opus 4.1"),
                        ],
                    }
                ],
            }
        )
    )
    monkeypatch.setenv("HUMANIZE_PRICES", str(at))
    # A process fetches its list at most once an hour, and each scene has a home of its own
    # with none kept in it: with nothing ever fresh, this one's is fetched however lately the
    # last scene's was, and it is fetched here, before the run that is held to it.
    monkeypatch.setattr(prices, "STALE", 0.0)
    assert prices.refresh(wait=True), "the staged price list was not kept"
    assert prices.price("claude-haiku-4-5"), "the stand-in's model has no price"


def _going(world: World) -> str:
    """Starts the epic, its reviewer never satisfied, and answers its name, leaving it going."""
    said = [json.dumps(_REVIEW), *_ROUNDS]
    # As the stand-in counts them (`conftest.py`): sixty tokens and one for every three letters.
    assert {60 + len(one) // 3 for one in said} == {_WRITTEN}, "a turn costs a dollar"
    world.says(
        {
            "meticulous reviewer": {"json": _REVIEW, "after": _PACE},
            _NOTES: {"text": _ROUNDS[1:], "after": _PACE},
            "coupon": {"text": _ROUNDS[0], "after": _PACE},
        }
    )
    return world.epic(home.FLOW, home.TASK, budget=_BUDGET, until=None)


def _put(
    page: Page,
    what: Locator,
    wide: float,
    at: tuple[float, float],
    held: tuple[float, float],
) -> None:
    """Pinches the graph until something in it is so wide, and slides it to where it is to be.

    Both with the pointer held over one place of the canvas, `held` from its corner.

    The graph opens fitted with room kept all round it, and is fitted anew each time the
    reviewer opens a session; once it is moved it stays as it is put.
    """
    canvas = page.get_by_role("group", name="The agents of the epic")
    around, box = canvas.bounding_box(), what.bounding_box()
    assert around
    assert box
    page.mouse.move(around["x"] + held[0], around["y"] + held[1])
    page.keyboard.down("Control")
    page.mouse.wheel(0, -100 * math.log(wide / box["width"]))
    page.keyboard.up("Control")
    _stands(page, what, "width", wide)
    box = what.bounding_box()
    assert box
    # Slid as two fingers slide it, which goes as far as it has to from one place.
    page.mouse.wheel(box["x"] - at[0], box["y"] - at[1])
    _stands(page, what, "x", at[0])
    _stands(page, what, "y", at[1])


def _stands(page: Page, what: Locator, side: str, at: float) -> None:
    """Waits until the page has drawn something where it was put: its `x`, `y` or `width`."""
    page.wait_for_function(
        "([one, side, at, near]) => "
        "Math.abs(one.getBoundingClientRect()[side] - at) <= near",
        arg=[what.element_handle(), side, at, _NEAR],
    )


def _filmed(page: Page, reel: shots.Reel, put: Callable[[], None]) -> None:
    """Takes the reel of the Epic panel's meters: filling, then the cost one full, the run over.

    Args:
      page: The page, on the epic, its panel open.
      reel: What the frames are taken into.
      put: Puts the graph where the picture has it, first and again once the run is over:
        the box to say a line in goes with the run, and a canvas grown taller than it is
        wide, as a phone's then is, stands its agents one over another.
    """
    put()
    cost = page.get_by_role("meter", name="cost")
    expect(cost).to_be_visible()
    expect(page.get_by_role("meter")).to_have_count(len(_BUDGET))
    most = _BUDGET["cost"]

    def spent() -> float:
        return float(cost.get_attribute("aria-valuenow") or 0)

    def hidden() -> None:
        """Where its sessions worked is under the panel's fold, heading and all.

        No path is in the picture, and no heading is cut in half by its edge.
        """
        height = (page.viewport_size or {"height": 0})["height"]
        places = page.get_by_role("heading", name="Environments").locator("xpath=..")
        for one in places.locator(":scope > *").all():
            box = one.bounding_box()
            assert box is None or box["y"] >= height, (
                "the panel shows where its sessions worked"
            )

    tiles = page.locator(".tiles")
    agents = page.get_by_role("group", name="The agents of the epic").locator(".node")
    for turn, hold in enumerate(_HOLDS, _FIRST):
        # A frame is taken just after a turn's end moved the meters, with the next a while
        # off: once every place the turn is told in says it, and the next agent has begun.
        expect(cost).to_have_attribute("aria-valuenow", str(turn), timeout=_PATIENCE)
        expect(tiles.get_by_text(f"${turn:.2f}", exact=True)).to_be_visible()
        expect(
            page.get_by_text(re.compile(rf"^took .+ · \${turn:.2f}$"))
        ).to_be_visible()
        # The actor is the first of the two and takes every even turn's handover.
        expect(agents.nth(turn % 2)).to_contain_text("working")
        assert spent() == turn, f"turn {turn} was over before its frame was taken"
        hidden()
        reel.web(page, hold=hold)
    # The budget ended it: the bar says so, and every figure is the last turn's.
    expect(page.get_by_role("link", name="Resume").first).to_be_visible(
        timeout=_PATIENCE
    )
    expect(page.get_by_text("budget", exact=True).first).to_be_visible()
    expect(cost).to_have_attribute("aria-valuenow", str(most))
    expect(tiles.get_by_text(f"${most:.2f}", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Stop")).to_have_count(0)
    # Nobody is at work, and the box to say a line in is gone, which is what moves the graph.
    expect(agents.get_by_text("working")).to_have_count(0)
    expect(page.get_by_placeholder("Message the epic")).to_have_count(0)
    put()
    hidden()
    reel.web(page, hold=4.5, poster=True)
    reel.save()


def test_the_meters_fill_and_the_budget_stops_the_run_at_a_desk(world: World) -> None:
    with home.desk(world) as page:
        # The sidebar is folded: the agents and what they spend are the whole window.
        page.get_by_role("button", name="Hide sidebar").click()
        name = _going(world)
        go(page, f"/epics/{name}")
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        canvas = page.get_by_role("group", name="The agents of the epic")
        around = canvas.bounding_box()
        assert around

        def put() -> None:
            """The flow as wide as the canvas, its two agents side by side, in its middle."""
            _put(
                page,
                canvas.locator(".frame").first,
                around["width"] - 2 * _EDGE,
                (around["x"] + _EDGE, around["y"] + _UNDER),
                (around["width"] / 2, 24),
            )

        _filmed(page, shots.Reel("home-budget", window="desktop"), put)


def test_the_meters_fill_and_the_budget_stops_the_run_on_a_phone(world: World) -> None:
    with home.phone(world) as page:
        name = _going(world)
        go(page, f"/epics/{name}")
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        canvas = page.get_by_role("group", name="The agents of the epic")
        around = canvas.bounding_box()
        assert around
        # On a phone the panel is a sheet over the graph, shut until it is asked for.
        page.get_by_role("button", name="Toggle panel").click()

        def put() -> None:
            """The reviewer's head in the strip of the graph the sheet leaves, the actor off it."""
            _put(
                page,
                canvas.locator(".node").last,
                _HEAD_WIDE,
                (around["x"] + _HEAD_AT, around["y"] + 4),
                (around["width"] - 8, 8),
            )

        _filmed(page, shots.Reel("home-budget-phone"), put)

"""The home page's Replay scene: a finished run read back, its record and its timeline.

`docs/index.md` plays one scene at a time on one stage (`home.py`). This one is the epic of
the page's task after it ended, read back on its own page, under a line that says how long it
took and what it cost. Every step of the record is left folded: a line says what a tool was
and what came of it, and opened it only says its input again.

- `home-replay` is Humanize Desktop's window. It opens on the actor's session as it is written
  down, picked in the sidebar -- the task, each tool it used, what it said, then what the
  reviewer sent it back with and what it did about that. A click on the epic in the sidebar
  shows the whole run as its graph, each session a bar on the run's own time; a click on the
  actor's bar is back in its session.
- `home-replay-phone` is the web page on a phone: the session's second turn, headed by what
  the reviewer sent back, and then the Epic sheet pulled over it, swiped to its figures --
  what was spent, the tokens, how long, how many sessions.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_home_replay.py`.

A price list is staged, since the world comes with none and a run nobody prices says no
cost: a file of made-up list prices for the stand-in's models, read as `HUMANIZE_PRICES`
names it.

What is left out, and why. The desk's panel is shut: under its figures it says the epic's id
and where it is written and worked, with no way to fold that, and at this window's height
they are in view. The reviewer's sessions are not opened: each starts with the whole of the
reviewer's prompt. And the record is not read in Exomyth: the trace's timeline names each
session by the start of its id, and is a canvas, which a picture holds as pixels.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from hmz.coganchor import prices
from tests.system.docs import home, shots
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Locator, Page

    from tests.system.docs.conftest import World

#: What the reviewer sends the actor back with, the first time it reads the work.
_NOTES = (
    "An unknown code is charged in full and nothing says so. Refuse it, with a test."
)

#: Seconds a tool takes, so that the epic took a believable while.
_PACE = 0.5

#: How far under the phone's bar the middle of the turn's first words is, which head the page.
_HEADS = 36

#: How far off the first place it is sent a reel's pointer comes in from (`shots.Reel`).
_FROM = (150, 110)

#: How wide pytest's line of dots is before its share: narrow, so that a phone keeps it whole.
_WIDE = 28


def _tests(passed: int, seconds: str) -> dict[str, object]:
    """A run of the project's tests, as pytest prints one that passed."""
    return {
        "name": "Bash",
        "input": {"command": "pytest -q"},
        "result": f"{'.' * passed:<{_WIDE}}[100%]\n{passed} passed in {seconds}s",
        "takes": 1.5 * _PACE,
    }


_READ = {
    "name": "Read",
    "input": {"file_path": "shop/checkout.py"},
    "result": "def total(cart):",
    "takes": _PACE / 2,
}

_EDIT = {
    "name": "Edit",
    "input": {"file_path": "shop/checkout.py"},
    "result": "edited",
    "takes": _PACE,
}

#: The run: the actor adds the coupon, the reviewer sends it back once, and then passes it.
#: The reviewer is told what the actor last said, which is how its second reading is told
#: from its first: the first key found in a prompt answers it.
_RUN = {
    "test_unknown_code": {
        "json": {"done": True, "notes": "WELCOME10 takes 10% off. 7 passed."},
        "tools": [_tests(7, "0.19")],
        "after": _PACE,
    },
    "meticulous reviewer": {
        "json": {"done": False, "notes": _NOTES},
        "tools": [_tests(6, "0.17")],
        "after": _PACE,
    },
    "unknown code": {
        "text": "An unknown code is refused now, and test_unknown_code covers it. 7 passed.",
        "tools": [_READ, _EDIT, _tests(7, "0.19")],
        "after": _PACE,
    },
    "coupon": {
        "text": "Checkout takes a coupon now: WELCOME10 is 10% off. 6 passed.",
        "tools": [_READ, _EDIT, _tests(6, "0.17")],
        "after": _PACE,
    },
}


@pytest.fixture(autouse=True)
def _prices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A price list for the stand-in's models, so that the epic says what it cost."""

    def model(ident: str, name: str) -> dict[str, object]:
        return {
            "id": ident,
            "name": name,
            "provider": "anthropic",
            "pricingItems": [
                {"category": "input_tokens", "price": 3},
                {"category": "output_tokens", "price": 15},
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
    # One list is held per process: a scene run after another reads its own, not the last's.
    monkeypatch.setattr(prices, "_listing", None)
    monkeypatch.setattr(prices, "_read_from", None)
    monkeypatch.setattr(prices, "_tried", 0.0)


def _ran(world: World) -> str:
    """Runs the epic to its end, and answers its name."""
    world.says(_RUN)
    return world.epic(home.FLOW, home.TASK)


def _ended(page: Page, name: str) -> None:
    """Opens the epic's own page, drawn as an ended epic is."""
    go(page, f"/epics/{name}")
    expect(page.get_by_role("link", name="Resume").first).to_be_visible()
    expect(page.get_by_text("Reading handovers")).to_have_count(0)
    expect(page.locator("[data-hmz=bar]").get_by_text("$").first).to_be_visible()


def _read(page: Page) -> Locator:
    """Waits for the actor's session, read whole, and answers its transcript."""
    thread = page.get_by_role("log")
    expect(thread).to_contain_text("test_unknown_code covers it")
    expect(thread.locator("summary").filter(has_text="pytest")).to_have_count(2)
    return thread


def _still(page: Page) -> None:
    """Takes the pointer off what it last clicked, and waits for the page to settle."""
    page.mouse.move(0, 0)
    page.wait_for_timeout(500)


#: Waits until whatever is moving on the page to an end has got there, and then until the
#: element it is given has stood in one place for six frames running.
_RESTS = """async (it) => {
  const ending = document.getAnimations().filter((one) => {
    const timing = one.effect && one.effect.getComputedTiming()
    return one.playState === 'running' && timing && Number.isFinite(timing.endTime)
  })
  await Promise.allSettled(ending.map((one) => one.finished))
  let last = '', same = 0
  while (same < 6) {
    await new Promise((done) => requestAnimationFrame(done))
    const box = it.getBoundingClientRect()
    const now = [box.x, box.y, box.width, box.height].join()
    same = now === last ? same + 1 : 0
    last = now
  }
}"""

#: Whether the element it is given is no longer as far down the window as it was.
_MOVED = "([it, was]) => it.getBoundingClientRect().y !== was"


def _rests(of: Locator) -> None:
    """Waits for something to be where it will stay: a sheet slid in, a swipe played out."""
    of.evaluate(_RESTS)


def _swiped(page: Page, of: Locator, by: float) -> None:
    """Swipes the page under the pointer, and waits for what is in it to have moved and stopped."""
    was = of.evaluate("(it) => it.getBoundingClientRect().y")
    page.mouse.wheel(0, by)
    page.wait_for_function(_MOVED, arg=[of.element_handle(), was])
    _rests(of)


def _middle(of: Locator) -> tuple[float, float]:
    """The middle of something on the page."""
    box = of.bounding_box()
    assert box is not None, "it is not on the page"
    return (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def test_a_finished_run_is_read_back_at_a_desk(world: World) -> None:
    name = _ran(world)
    with home.desk(world) as page:
        _ended(page, name)
        # The panel beside it says where the epic is written and where it worked, under its
        # figures and with no way to fold that: shut, so that no path is in the picture.
        page.get_by_role("button", name="Toggle panel").click()
        side = page.locator("[data-hmz=sidebar]")
        epic = side.locator("[data-hmz=epic]")
        bar = page.locator("[data-hmz=graph] [data-hmz=graph-session]").first
        expect(bar).to_be_visible()
        _still(page)
        # Where the reel's last click lands, which is where its pointer is as it starts
        # again: a reel's pointer comes in from `_FROM` off the first place it is sent.
        last = _middle(bar)
        side.locator("[data-hmz=session]").first.click()
        _read(page)
        _still(page)
        reel = shots.Reel("home-replay", window="desktop")
        came = (last[0] - _FROM[0], last[1] - _FROM[1])
        reel.web(page, hold=0.5, pointer=came, poster=True)
        reel.web(page, hold=3.1, pointer=epic, click=True, cut=True)
        epic.click()
        expect(bar).to_be_visible()
        _still(page)
        assert _middle(bar) == pytest.approx(last, abs=1), "the graph opened elsewhere"
        reel.web(page, hold=3.0, pointer=bar, click=True)
        reel.save()


def test_a_finished_run_is_read_back_on_a_phone(world: World) -> None:
    name = _ran(world)
    with home.phone(world) as page:
        _ended(page, name)
        page.locator("[data-hmz=graph-session]").first.click()
        thread = _read(page)
        _still(page)
        # The session opens on its end, the second turn's first line under the bar's edge:
        # it is swiped down, and back up until what the reviewer sent the actor back with
        # heads the page. (The first swipe off its end lets go of more than it is given.)
        heads = thread.get_by_text(_NOTES)
        bar = page.locator("[data-hmz=bar]").bounding_box()
        assert bar is not None
        thread.hover()
        _swiped(page, heads, -60)
        _swiped(page, heads, _middle(heads)[1] - (bar["y"] + bar["height"] + _HEADS))
        _still(page)
        panel = page.get_by_role("button", name="Toggle panel")
        reel = shots.Reel("home-replay-phone")
        reel.web(page, hold=2.8, pointer=panel, click=True)
        panel.click()
        sheet = page.locator("[data-hmz=inspector]")
        figures = sheet.locator(".side-section").filter(has_text="Output tokens")
        expect(figures).to_be_visible()
        # The sheet slides up over the page: it is measured where it comes to rest.
        _rests(sheet)
        # The sheet opens on the agent whose session this is; its figures are under that, and
        # are swiped up to the sheet's top, where all four are whole.
        pane = sheet.locator(".panel-pane")
        top, at = pane.bounding_box(), figures.bounding_box()
        assert top is not None, "the sheet has no body"
        assert at is not None, "the sheet has no figures"
        pane.hover()
        _swiped(page, figures, at["y"] - top["y"])
        _still(page)
        fold = home.PHONE[1]
        tiles = [one.bounding_box() for one in figures.locator(".tile").all()]
        assert len(tiles) == 4, "the sheet's figures are not four"
        assert all(
            one and one["y"] >= top["y"] and one["y"] + one["height"] <= fold
            for one in tiles
        ), "a figure is cut by the sheet's edge"
        # Where the epic is written and where it worked is under the sheet's fold.
        for under in (
            sheet.locator(".handovers li").first,
            sheet.get_by_role("heading", name="Setup"),
        ):
            box = under.bounding_box()
            assert box is None or box["y"] >= fold, "the sheet shows what is under it"
        close = page.get_by_role("button", name="Close panel").locator("visible=true")
        reel.web(page, hold=3.8, pointer=close, click=True, poster=True)
        reel.save()

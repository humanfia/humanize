"""The home page's scene Run: agents working in a loop, seen as the graph of a running epic.

One run of `rlar` on the home page's task (`home.py`), watched from the moment the loop first
turns to its end: the reviewer has sent the work back -- the edge that returns is lit and
counts a round -- and the actor works again; the reviewer reads it afresh and sends it back a
second time, the actor works a third, the reviewer passes it, and the epic is done. The graph
is all the picture is of. For a desk the panel beside it is shut, and the sidebar, and the
graph is zoomed until the frame of its flow is as wide as the window. A phone lays the two side by
side while the epic runs, which is wider than a phone at any size they can be read at: there
the picture is of the actor whole, at the window's left, the two edges that leave it and
come back, and as much of the reviewer as says who it is -- its name, its role and the
sessions it reads the work in, a new one each round -- and it stops before the epic ends,
where the page lays the graph out anew. Nobody acts in it, so no pointer is drawn. Run it by
naming it:
`uv run pytest tests/system/docs/test_docs_home_run.py`.

The stand-in agent takes as long over a turn as it is scripted to, and each frame is taken
when the graph says the run has come to it: a turn is long enough here for the frame of it
to be taken twice over, light and dark.
"""

from __future__ import annotations

import math
import re
import time
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.system.docs import home, shots
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from typing import Any

    from playwright.sync_api import FloatRect, Locator, Page

    from tests.system.docs.conftest import World

#: What the reviewer hands back after each of the first two rounds: what the actor is told next.
_FIRST = "No test covers an empty cart with a coupon. Add one."
_SECOND = "An expired coupon still takes 10% off. Refuse it."

#: How many seconds a turn's frame is given to be taken in, at the least.
_TURN = 9.0

#: How wide the graph draws an agent at its own size, and how far from the next, in pixels
#: (`graph.js`).
_WIDE = 248
_APART = 150
#: What the frame of a flow stands out past its agents on either side, and what a desk's window
#: keeps clear of that frame.
_FRAME = 27
_CLEAR = 32

#: How large a phone's reel draws the graph, and how far from the window's left its actor is:
#: the name of the flow they stand in is whole over the actor, the actor is, both edges after
#: it, and the reviewer's name and role begin.
_SMALL = 0.78
_INSET = 18


def _tool(name: str, takes: float, result: str, **said: str) -> dict[str, Any]:
    return {"name": name, "input": said, "result": result, "takes": takes}


def _review(done: bool, notes: str, did: str, saw: str) -> dict[str, Any]:
    return {
        "json": {"done": done, "notes": notes},
        "tools": [_tool("Bash", 2, saw, command=did)],
        "after": _TURN - 2,
    }


def _script(world: World) -> None:
    """Scripts three rounds of `rlar`: the actor works, and is sent back twice.

    The first key found in what an agent is told answers it, so the order here is the order
    they are tried in: the reviews from the last to the first (each later one alone is told
    of the test the actor added before it), then the actor's turns from the last to the first
    (each later one is told the notes of the review before it). The first two turns are over
    before the reel begins: they are as long as the page takes to be opened and its graph set.
    """
    world.says(
        {
            "test_expired_code": _review(
                True,
                "WELCOME10 takes 10% off; empty carts and expired codes are tested.",
                "pytest -q",
                "8 passed in 0.21s",
            ),
            "test_empty_cart": _review(
                False, _SECOND, "pytest -q", "7 passed in 0.19s"
            ),
            "meticulous reviewer": {
                **_review(False, _FIRST, "git diff", "shop/checkout.py | 9 +++++++--"),
                "after": 2,
            },
            "expired coupon": {
                "text": "Expired codes are refused now: test_expired_code. 8 passed.",
                "tools": [
                    _tool("Edit", 2, "edited", file_path="shop/checkout.py"),
                    _tool("Bash", 2, "8 passed in 0.21s", command="pytest -q"),
                ],
                "after": _TURN - 4,
            },
            "empty cart": {
                "text": "Added test_empty_cart: it is charged nothing. 7 passed.",
                "tools": [
                    _tool("Edit", 2, "edited", file_path="shop/checkout.py"),
                    _tool("Bash", 2, "7 passed in 0.19s", command="pytest -q"),
                ],
                "after": _TURN - 4,
            },
            "coupon": {
                "text": "Checkout takes a coupon now: WELCOME10 is 10% off. 6 passed.",
                "tools": [
                    _tool(
                        "Read",
                        3,
                        "def charge(items): ...",
                        file_path="shop/checkout.py",
                    ),
                    _tool("Edit", 3, "edited", file_path="shop/checkout.py"),
                    _tool("Bash", 3, "6 passed in 0.17s", command="pytest -q"),
                ],
                "after": 1,
            },
        }
    )


def _started(world: World) -> str:
    """Starts the flow on the task and answers its epic's name, the epic still running."""
    return world.epic(home.FLOW, home.TASK, until=None)


def _working(node: Locator) -> Locator:
    return node.get_by_text(re.compile(r"^working"))


def _box(part: Locator) -> FloatRect:
    box = part.bounding_box()
    assert box
    return box


def _still(page: Page, part: Locator, *, since: FloatRect | None = None) -> FloatRect:
    """Waits until a part of the page has stopped moving, and answers where it is.

    It is looked for anew at every frame the page draws, since the graph draws its agents
    anew as the run goes on, and is still once it has been in one place for several.

    Args:
      page: The page.
      part: The part: one element.
      since: Where it was before what was to move it, where it is known that it must move:
        it is first waited to be elsewhere, however long the page takes to begin.
    """
    was, frames = since, 0
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        now = _box(part)
        if (
            since
            and abs(now["x"] - since["x"]) + abs(now["width"] - since["width"]) < 0.5
        ):
            pass
        elif now == was:
            frames += 1
            if frames == 4:
                return now
        else:
            since, was, frames = None, now, 0
        page.evaluate("() => new Promise((drawn) => requestAnimationFrame(drawn))")
    raise AssertionError(f"it never came to rest: {was}")


def _set(page: Page, scale: float, *, inset: float | None = None) -> None:
    """Zooms the graph to a scale and moves it to where the reel shows it.

    A pinch zooms it -- twice, the second to mend what the first was off by -- and a drag
    moves it: until what is between its two agents is in the canvas's middle, or its actor
    is where it is said to be, and the agents as they stand in the frame the reel rests on,
    the reviewer two sessions tall, are half above the canvas's middle and half below.

    Args:
      page: The page, on the epic's graph, the epic running.
      scale: How large the graph is drawn: `1` is its own size.
      inset: How far from the canvas's left the actor's left side is put, in pixels: where
        not said, what is between the two agents is put in the canvas's middle.
    """
    canvas = page.locator("[data-hmz=graph]")
    nodes = canvas.locator("[data-hmz=graph-agent]")
    actor, reviewer = nodes.filter(has_text="actor"), nodes.filter(has_text="reviewer")
    expect(actor.locator("[data-hmz=graph-session]")).to_have_count(1)
    view = _box(canvas)
    middle = (view["x"] + view["width"] / 2, view["y"] + view["height"] / 2)
    page.get_by_role("button", name="Recenter").click()
    page.mouse.move(*middle)
    for _ in range(2):
        was = _still(page, actor)
        turn = math.log(scale * _WIDE / was["width"])
        page.keyboard.down("Control")
        page.mouse.wheel(0, -100 * turn)
        page.keyboard.up("Control")
        # A turn of the wheel too small to be seen moves nothing that could be waited for.
        _still(page, actor, since=was if abs(turn) > 0.01 else None)
    left, right = _still(page, actor), _box(reviewer)
    # The actor's node has its one session from the start; the reviewer's is a row taller.
    row = _box(actor.locator("[data-hmz=graph-session]"))["height"]
    if inset is None:
        across = middle[0] - (left["x"] + left["width"] + right["x"]) / 2
    else:
        across = view["x"] + inset - left["x"]
    down = middle[1] - (left["y"] + (left["height"] + row) / 2)
    # A press that hardly moves is a click: it is dragged well past, and then to where it goes.
    page.mouse.down()
    page.mouse.move(middle[0] + 40, middle[1] + 40, steps=4)
    page.mouse.move(middle[0] + across, middle[1] + down, steps=4)
    page.mouse.up()
    there = _still(page, actor)
    assert abs(there["x"] - left["x"] - across) < 2, (there, left, across)
    assert abs(there["width"] - scale * _WIDE) < 2, (there, scale)


def _loop(page: Page, reel: shots.Reel, *, to_the_end: bool) -> None:
    """Takes the run a turn at a time, from the first time it is sent back.

    Args:
      page: The page, on the epic's graph as the reel shows it, the run not yet sent back a
        second time.
      reel: The reel the frames are taken for.
      to_the_end: Whether the last frame is of the epic done, the reviewer's last turn over.
    """
    graph = page.locator("[data-hmz=graph]")
    nodes = graph.locator("[data-hmz=graph-agent]")
    actor, reviewer = nodes.filter(has_text="actor"), nodes.filter(has_text="reviewer")
    sessions = reviewer.locator("[data-hmz=graph-session]")
    latest = graph.locator(".edge.latest text")
    wait = 30_000

    def settled() -> None:
        # A node takes its glow and an edge its colour over a moment: none is caught midway.
        page.wait_for_timeout(700)

    # Sent back: the edge that returns is lit and counts a round, and the actor works again.
    expect(latest).to_have_text("×1", timeout=wait)
    expect(_working(actor)).to_be_visible(timeout=wait)
    settled()
    reel.web(page, hold=2.0)
    # Handed over a second time, to a reviewer that reads it afresh.
    expect(_working(reviewer)).to_be_visible(timeout=wait)
    expect(sessions).to_have_count(2)
    settled()
    reel.web(page, hold=1.3)
    # Sent back again: the same edge counts a second round. What a visitor who asked for less
    # motion sees is the loop turning.
    expect(_working(actor)).to_be_visible(timeout=wait)
    expect(latest).to_have_text("×2")
    settled()
    reel.web(page, hold=2.2, poster=True)
    # Handed over a third time.
    expect(_working(reviewer)).to_be_visible(timeout=wait)
    expect(sessions).to_have_count(3)
    settled()
    reel.web(page, hold=1.5 if to_the_end else 1.7)
    if not to_the_end:
        return
    # The reviewer passes it, and the epic is done.
    expect(page.get_by_role("link", name="Resume").first).to_be_visible(timeout=wait)
    expect(_working(graph)).to_have_count(0)
    settled()
    reel.web(page, hold=1.2)


def test_the_loop_turns_on_a_desk(world: World) -> None:
    _script(world)
    name = _started(world)
    reel = shots.Reel("home-run", window="desktop")
    with home.desk(world) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        # The graph alone, as large as the window lets it be: the panel beside it shut, and
        # the sidebar, and the frame of the flow the two agents stand in zoomed to the
        # window's width, with a little of the canvas left on either side of it.
        # Each leaves the graph wider, over a moment: it is zoomed once it is as wide as
        # it will be.
        canvas = page.locator("[data-hmz=graph]")
        for shut in ("Toggle panel", "Hide sidebar"):
            was = _still(page, canvas)
            page.get_by_role("button", name=shut).click()
            _still(page, canvas, since=was)
        _set(page, (home.DESK[0] - 2 * _CLEAR) / (2 * _WIDE + _APART + 2 * _FRAME))
        page.mouse.move(520, 600)
        _loop(page, reel, to_the_end=True)
    reel.save()


def test_the_loop_turns_on_a_phone(world: World) -> None:
    _script(world)
    name = _started(world)
    reel = shots.Reel("home-run-phone")
    with home.phone(world) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        # A phone's graph opens with both agents side by side and too small to read. It is
        # pinched up until the actor, the edges and the reviewer's name fill the window, the
        # actor at its left: what an agent says of itself begins at its left.
        _set(page, _SMALL, inset=_INSET)
        page.mouse.move(home.PHONE[0] / 2, home.PHONE[1] - 40)
        # When the epic ends the page lays the graph out anew, one agent over the other: the
        # reel stops before it does, on the reviewer's last turn.
        _loop(page, reel, to_the_end=False)
    reel.save()

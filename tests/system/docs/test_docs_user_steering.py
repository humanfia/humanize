"""The pictures of `docs/user/steering.md`: a line said to a flow that is running.

One flow, the stand-in `rlar`, whose actor works, is reviewed, and works again: a line said
between the actor's turns waits, and its next turn takes it. It is said three ways: in the
thread of the actor's session in the app, at the prompt of the terminal interface, and by
another frontend while the terminal reads the same epic. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_steering.py`.

Two things are staged here, since the world comes with neither:

- a script for both of `rlar`'s agents that has the reviewer send the actor back once, so
  that the actor has a second turn for a waiting line to go into;
- a second frontend of the same epic, attached over the page's own bridge under the name a
  browser page or a terminal of the same person has (`alex@web`, `alex@tui`).

The stand-in `claude` never says it took a line put into a turn under way, as the real one
does, so the pictures of a line taken are of one that waited for a turn to start.
"""

from __future__ import annotations

import contextlib
import re
import time
import uuid
from typing import TYPE_CHECKING, Any, Literal

from playwright.sync_api import expect

from hmz.reach import WebSocketPipe
from hmz.rpc import Peer, hello
from hmz.tui.flows import Flows
from hmz.tui.pick import Configures, Confirms
from tests.integration.doubles_tui import on, onto, screen, shows, until
from tests.integration.doubles_web import PATIENCE, Browser
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-steering"

_FLOW = "rlar"
_TASK = "Add a discount code to checkout"

#: What is said to the flow while it runs.
_LINE = "Also refuse expired codes"


def _mended(picture: Path) -> Path:
    """A picture with the bold `u` of the page's face drawn whole.

    `shots` rounds a coordinate of that glyph from just under zero to `0` and so loses the
    minus sign that alone kept it apart from the number before it: `656-0.4` is written
    `6560`, and the letter grows a hairline off to its right. The two numbers are put apart
    again here, the module not being this scene's to change.
    """
    drawn = picture.read_text(encoding="utf-8")
    picture.write_text(
        drawn.replace("697-16 6560 614 14", "697-16 656 0 614 14"), encoding="utf-8"
    )
    return picture


def _says(first: float, review: float, second: float) -> dict[str, Any]:
    """What `rlar`'s agents say, and how long each takes: the actor is sent back once.

    The first key found in what an agent is told answers it, so the reviewer's lines stand
    before the actor's: the second review is told what the actor said last.
    """
    return {
        "ExpiredCode": {
            "json": {"done": True, "notes": "Expired codes are refused; tests pass."},
            "after": 2,
        },
        "meticulous reviewer": {
            "json": {"done": False, "notes": "Add a test for a code used twice."},
            "after": review,
        },
        "used twice": {
            "text": "A code used twice is refused, and charge() raises ExpiredCode "
            "for one past its date. Tests pass.",
            "after": second,
        },
        "discount": {
            "text": "Checkout takes a discount code now: WELCOME10 is 10% off.",
            "after": first,
        },
    }


@contextlib.contextmanager
def _frontend(
    world: World, name: str, kind: Literal["tui", "web"]
) -> Generator[Callable[..., Any]]:
    """Another frontend of the project's epic, attached until the block ends.

    Yields:
      What calls a method of the epic as that frontend: `asks("epic.say", text=..., to="")`.
    """
    browser = Browser(world.site)
    browser.signs_in()
    socket = browser.opens("/rpc")
    peer = Peer(WebSocketPipe(socket, trusted=True), lambda call: None, name="page")
    try:
        hello(peer, name, kind, timeout=PATIENCE)
        sub = peer.call(
            "epic.attach",
            {"workspace": str(world.workspace), "replay": False},
            timeout=PATIENCE,
        )["sub"]

        def asks(method: str, **said: Any) -> Any:
            params = {"sub": sub, "idem": uuid.uuid4().hex, **said}
            return peer.call(method, params, timeout=PATIENCE)

        yield asks
    finally:
        peer.close()
        socket.close()


def _epic(world: World) -> str:
    """Starts the flow on the task and answers the epic's name, left running.

    `World.epic` reads the list of epics once, straight after the start, and on a busy
    machine the new one is not always listed yet: the list is read again here until it is.
    """
    try:
        return world.epic(_FLOW, _TASK, until=None)
    except StopIteration:
        deadline = time.monotonic() + PATIENCE
        while time.monotonic() < deadline:
            runs = world.call("runs.list", workspace=str(world.workspace))["runs"]
            for one in runs:
                if one["task"] == _TASK:
                    return str(one["name"])
            time.sleep(0.2)
        raise


async def _started(pilot: Pilot[None]) -> None:
    """Gives the flow thirty minutes on its page of `/flow`, saves it, and starts it."""
    await pilot.press(*f"/flow {_FLOW}", "enter")
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
    await shows(pilot, "enter Set")
    await pilot.press("enter")
    await on(pilot, Flows)
    await shows(pilot, "stops at 30m")
    await pilot.press("escape")
    await on(pilot, Confirms)
    await pilot.press("enter")
    await shows(pilot, f"Flow set up; `/flow {_FLOW} <task>` starts it.")
    await pilot.press(*f"/flow {_FLOW} {_TASK}", "enter")
    await shows(pilot, "ctrl+c twice to stop")


def test_a_line_is_said_in_the_app(world: World) -> None:
    world.says(_says(4, 22, 8))
    name = _epic(world)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        graph = page.locator("[data-hmz=graph]")
        expect(graph.get_by_text(re.compile(r"^working"))).to_have_count(1)
        expect(graph.get_by_text("not started")).to_have_count(0)
        to = page.get_by_label("Say it to")
        actor = to.locator("option").nth(1).get_attribute("value")
        assert actor
        page.wait_for_timeout(1500)
        # The box under the graph, and who its line may go to.
        shots.web(page, f"{_PAGE}-box", clip="[data-hmz=say]", pad=6)

        # The frontends of the epic: this page, and a terminal reading it too.
        with _frontend(world, "alex@tui", "tui"):
            listed = page.locator("[data-hmz=frontends]")
            expect(listed.get_by_text("alex@tui")).to_be_visible()
            # To the middle of the panel: at its foot the picture's margin would be cut off.
            listed.evaluate("one => one.scrollIntoView({block: 'center'})")
            page.wait_for_timeout(800)
            _mended(
                shots.web(
                    page, f"{_PAGE}-frontends", clip=listed.locator("xpath=.."), pad=14
                )
            )
        expect(listed.get_by_text("alex@tui")).to_have_count(0)
        page.get_by_role("button", name="Close panel").click()

        # The actor's session, between its turns: the line waits, and its next turn takes it.
        page.get_by_text(f"{actor}/1").first.click()
        box = page.get_by_role("textbox", name="What to say")
        expect(box).to_have_attribute("placeholder", f"Message {actor}/1")
        expect(page.get_by_text("WELCOME10")).to_be_visible()
        page.wait_for_timeout(1000)
        reel = shots.Reel(f"{_PAGE}-say", window="desktop")
        reel.web(page, hold=1.4, pointer=box, click=True)
        reel.type(page, box, _LINE, per=5)
        box.press("Enter")
        expect(box).to_have_value("")
        page.wait_for_timeout(600)
        reel.web(page, hold=1.6, keys="enter", caption="it waits for the next turn")
        expect(page.get_by_text("alex@web said")).to_be_visible()
        page.wait_for_timeout(800)
        reel.web(page, hold=2.0, caption="the next turn takes it")
        expect(page.get_by_text("used twice is refused")).to_be_visible()
        page.wait_for_timeout(800)
        reel.web(page, hold=3.5, poster=True)
        _mended(reel.save())


async def test_a_line_is_said_in_the_terminal(world: World) -> None:
    world.says(_says(4, 16, 8))
    async with world.tui((110, 28)) as (app, pilot):
        await shows(pilot, MODEL)
        await _started(pilot)
        await shows(pilot, "Worked for")
        await pilot.pause(1)
        reel = shots.Reel(f"{_PAGE}-terminal")
        reel.tui(app, hold=1.6)
        await pilot.press(*_LINE)
        await pilot.pause(0.3)
        reel.tui(app, hold=1.2, caption="type the line")
        await pilot.press("enter")
        await until(pilot, lambda: "enter send" not in screen(app), "the pin")
        await pilot.pause(0.5)
        reel.tui(app, hold=2.2, keys="enter", caption="pinned until a turn takes it")
        await until(pilot, lambda: screen(app).count("is working") >= 2, "turn two")
        await pilot.pause(0.8)
        reel.tui(app, hold=2.2, caption="taken: it moves into the transcript")
        await shows(pilot, "Flow done")
        reel.tui(app, hold=3.5, poster=True)
        reel.save()


async def test_lines_wait_pinned_above_the_prompt(world: World) -> None:
    world.says(_says(20, 2, 2))
    async with world.tui((120, 24)) as (app, pilot):
        await shows(pilot, MODEL)
        await _started(pilot)
        await shows(pilot, "is working")
        await pilot.pause(1)
        await pilot.press(*_LINE, "enter")
        await pilot.pause(0.5)
        await pilot.press(*"and keep the tests green", "enter")
        await pilot.pause(0.5)
        with _frontend(world, "alex@web", "web") as asks:
            asks("epic.say", text="Keep the old prices", to="")
            await shows(pilot, "by alex@web")
            await pilot.pause(0.5)
            shots.tui(app, f"{_PAGE}-pinned")
        await pilot.press(*"/stop", "enter")
        await shows(pilot, "ctrl+c Exit")

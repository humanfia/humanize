"""The pictures of `docs/user/side-questions.md`: a question asked beside a run, never of it.

The Aside tab of an epic in the app, a chat's side questions, and btw mode in the terminal.
Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_side_questions.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.integration.doubles_tui import shows
from tests.system.docs import shots
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

_PAGE = "user-side-questions"

_TASK = "Add a discount code to checkout"
_DONE = (
    "Checkout takes a discount code now: charge() looks the code up and takes its"
    " discount off the total. WELCOME10 is 10% off."
)

_NOW = "What are you changing right now?"
_NOW_SAID = (
    "I am editing shop/checkout.py so that charge() takes a code. Next I add two tests"
    " and run the suite. Nothing is committed yet."
)
_FILES = "Which files have you touched?"
_FILES_SAID = "Only shop/checkout.py so far. tests/test_checkout.py comes next."
_WHY = "Why is the discount a percentage?"
_WHY_SAID = (
    "CODES maps a code to a percent off, so one code works for a cart of any size."
    " A fixed amount would need a floor at zero."
)

#: What the stand-in says to each side question: found before the task, which a side copy
#: told a snapshot is told too.
_ASIDES = {
    "right now": {"text": _NOW_SAID, "after": 1.5},
    "touched": {"text": _FILES_SAID, "after": 1.0},
    "percentage": {"text": _WHY_SAID, "after": 1.5},
}


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


def test_an_aside_is_asked_of_one_session_of_a_running_epic(world: World) -> None:
    world.says({**_ASIDES, "discount": {"text": _DONE, "after": 90}})
    name = world.epic("rlar", _TASK, until=None)
    try:
        with world.page(desktop=True) as page:
            go(page, f"/epics/{name}")
            expect(page.get_by_role("button", name="Stop")).to_be_visible()
            graph = page.locator("[data-hmz=graph]")
            expect(graph.get_by_text("working").first).to_be_visible()
            tab = page.get_by_role("tab", name="Aside")
            if not tab.is_visible():
                page.get_by_role("button", name="Toggle panel").click()
            expect(tab).to_be_visible()

            reel = shots.Reel(f"{_PAGE}-aside", clip="[data-hmz=inspector]", pad=250)
            reel.web(page, hold=1.4, pointer=tab, click=True)
            tab.click()
            ask = page.get_by_role("button", name="Ask it of")
            expect(ask).to_contain_text("Pick a conversation")
            reel.web(page, hold=1.2, pointer=ask, click=True)
            ask.click()
            agent = page.locator(".ask-list .choice-sub > [role=menuitem]").first
            expect(agent).to_be_visible()
            reel.web(page, hold=1.2, pointer=agent, click=True)
            agent.click()
            session = page.locator("[data-hmz=btw-agent] [role=menuitem]").first
            expect(session).to_be_visible()
            session.hover()
            reel.web(page, hold=1.4, pointer=session, click=True)
            session.click()
            expect(ask).to_contain_text("/1")
            box = page.get_by_role("textbox", name="Side question")
            reel.type(page, box, _NOW, per=len(_NOW), rest=1.0)
            box.press("Enter")
            expect(page.get_by_text("is thinking…")).to_be_visible()
            reel.web(page, hold=1.3, caption="a side copy answers")
            log = page.locator("[data-hmz=btw-log]")
            expect(log).to_contain_text("Nothing is committed yet.")
            # And the epic's own agent is where it was: still on its turn.
            expect(graph.get_by_text("working").first).to_be_visible()
            reel.web(page, hold=4.5, caption="the epic never heard it", poster=True)
            reel.save()
            shots.web(page, f"{_PAGE}-epic", window="desktop", most=shots.REEL)
    finally:
        world.stop(name)


def test_a_chat_is_asked_on_the_side(world: World) -> None:
    world.says({**_ASIDES, "discount": _DONE})
    chat = world.chat(_TASK)
    with world.page(desktop=True) as page:
        go(page, f"/chats/{chat}")
        expect(page.get_by_role("log").first).to_contain_text("WELCOME10")
        box = page.get_by_role("textbox", name="What to say")
        reel = shots.Reel(f"{_PAGE}-chat", window="desktop")
        reel.web(page, hold=1.0, pointer=box, click=True)
        reel.type(page, box, f"/btw {_WHY}", per=12, rest=1.0)
        box.press("Enter")
        panel = page.locator("[data-hmz=btw-log]")
        expect(
            page.get_by_text("Side questions never reach this chat.")
        ).to_be_visible()
        expect(panel).to_contain_text("floor at zero")
        reel.web(page, hold=4.5, caption="answered in the pane", poster=True)
        reel.save()


async def test_btw_mode_in_the_terminal(world: World) -> None:
    world.says({**_ASIDES, "discount": {"text": _DONE, "after": 90}})
    world.epic("rlar", _TASK, until=None)
    async with world.tui((96, 24)) as (app, pilot):
        await shows(pilot, "is working")
        await _settled(pilot)
        reel = shots.Reel(f"{_PAGE}-terminal")
        reel.tui(app, hold=1.4, caption="reading the agent at work")
        line = f"/btw {_NOW}"
        for start in range(0, len(line), 10):
            await pilot.press(*line[start : start + 10])
            await pilot.pause()
            reel.tui(app, hold=0.2, cut=True)
        await pilot.press("enter")
        await shows(pilot, "each line is a question")
        await _settled(pilot, 0.2)
        reel.tui(app, hold=1.6, keys="enter", caption="btw mode is on")
        await shows(pilot, "Nothing is committed yet.")
        await _settled(pilot, 0.2)
        reel.tui(app, hold=3.0, caption="the answer, in cyan")
        await pilot.press(*_FILES)
        await _settled(pilot, 0.2)
        reel.tui(app, hold=1.0, caption="a plain line is the next question")
        await pilot.press("enter")
        await shows(pilot, "comes next.")
        await _settled(pilot, 0.2)
        reel.tui(app, hold=3.0, keys="enter", poster=True)
        await pilot.press("escape")
        await shows(pilot, "btw: Side questions ended")
        await _settled(pilot, 0.2)
        reel.tui(app, hold=2.5, keys="esc", caption="back to the flow")
        reel.save()
        await pilot.press("ctrl+c", "ctrl+c")
        await shows(pilot, "ctrl+c Exit")

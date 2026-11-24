"""The pictures of `docs/user/chat.md`: a chat in the app, in the terminal and from a command.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_chat.py`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.integration.doubles_tui import shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

    from tests.system.docs.conftest import World

_TASK = "Add a discount code to checkout"
_NEXT = "Should an expired code be refused?"
_ASK = "What does charge() do?"

_ANSWER = (
    "Checkout takes a discount code now: charge() looks the code up and takes its"
    " discount off the total. WELCOME10 is 10% off. Two new tests cover it, and all"
    " six pass."
)
_REFUSED = "Yes. charge() now raises ExpiredCode for a code past its date."
_SAID = "charge() answers what a cart costs, in cents: the total shop/cart.py adds up."

_CHECKOUT = '''"""Paying for a cart."""

from shop.cart import total

CODES = {"WELCOME10": 10}


def charge(items: dict[str, int], code: str = "") -> int:
    """What is charged for a cart, in cents, less what a code takes off."""
    owed = total(items)
    return owed - owed * CODES.get(code, 0) // 100
'''

#: What the agent does when told the task: reads, edits, tests, and says so.
_WORK = {
    "text": _ANSWER,
    "tools": [
        {
            "name": "Read",
            "input": {"file_path": "shop/checkout.py"},
            "result": "def charge(items): ...",
            "takes": 0.2,
        },
        {
            "name": "Edit",
            "input": {"file_path": "shop/checkout.py"},
            "result": "edited",
            "takes": 0.2,
        },
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": "6 passed in 0.21s",
            "takes": 0.3,
        },
    ],
    "writes": {"shop/checkout.py": _CHECKOUT},
}


def _ready(page: Page) -> Locator:
    """The box of a new chat, once the agent it would start is on offer under it."""
    expect(page.get_by_role("button", name=re.compile("Nous: .*Haiku"))).to_be_visible()
    return page.get_by_role("textbox", name="First message")


def test_a_chat_is_started_in_the_app(world: World) -> None:
    world.says({"discount": {**_WORK, "after": 1.5}})
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        box = _ready(page)
        shots.web(page, "user-chat-box", clip="[data-hmz=start]", pad=20)

        go(page, "/epics")
        reel = shots.Reel("user-chat-start", window="desktop")
        new = page.get_by_role("link", name=re.compile("New chat")).first
        reel.web(page, hold=1.3, pointer=new, click=True)
        new.click()
        box = _ready(page)
        reel.web(page, hold=0.9, pointer=box, click=True)
        reel.type(page, box, _TASK, per=11)
        box.press("Enter")
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        expect(page.get_by_role("log")).to_contain_text(_TASK)
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        reel.web(page, hold=1.4, caption="the turn is open")
        expect(page.get_by_role("log")).to_contain_text("WELCOME10")
        expect(page.get_by_role("button", name="Send")).to_be_visible()
        reel.web(page, hold=4, poster=True)
        reel.save()


def test_a_chat_is_read_with_its_bar_and_a_pane(world: World) -> None:
    world.says({"discount": _WORK, "expired": _REFUSED})
    chat = world.chat(_TASK, _NEXT)
    with world.page(desktop=True) as page:
        go(page, f"/chats/{chat}")
        expect(page.get_by_role("log")).to_contain_text("ExpiredCode")
        page.get_by_role("button", name="Details").click()
        expect(page.get_by_text("About this chat")).to_be_visible()
        shots.web(page, "user-chat-open", window="desktop")


def test_a_turn_under_way_is_stopped_by_the_send_button(world: World) -> None:
    world.says({"discount": _WORK, "expired": {"text": _REFUSED, "after": 30}})
    chat = world.chat(_TASK)
    with world.page(desktop=True) as page:
        go(page, f"/chats/{chat}")
        expect(page.get_by_role("log")).to_contain_text("WELCOME10")
        box = page.get_by_role("textbox", name="What to say")
        box.fill(_NEXT)
        box.press("Enter")
        stop = page.get_by_role("button", name="Stop")
        expect(stop).to_be_visible()
        expect(page.get_by_role("log")).to_contain_text(_NEXT)
        reel = shots.Reel("user-chat-stop", window="desktop")
        reel.web(page, hold=2.2, pointer=stop, click=True, caption="the turn is open")
        stop.click()
        expect(page.get_by_role("log")).to_contain_text("That turn was stopped.")
        expect(page.get_by_role("button", name="Send")).to_be_visible()
        reel.web(page, hold=4, poster=True)
        reel.save()


async def test_a_chat_in_the_terminal(world: World) -> None:
    world.says({"discount": {"text": _ANSWER, "after": 1.0}})
    async with world.tui((96, 24)) as (app, pilot):
        await shows(pilot, MODEL)
        reel = shots.Reel("user-chat-terminal")
        reel.tui(app, hold=1.4)
        for start in range(0, len(_TASK), 8):
            await pilot.press(*_TASK[start : start + 8])
            await pilot.pause()
            reel.tui(app, hold=0.2, cut=True)
        await pilot.press("enter")
        await shows(pilot, "running")
        reel.tui(app, hold=1.2, keys="enter")
        await shows(pilot, "WELCOME10")
        await shows(pilot, "Worked for")
        reel.tui(app, hold=4, poster=True)
        reel.save()


def test_one_turn_from_the_command_line(world: World) -> None:
    world.says({"charge()": {"text": _SAID, "after": 0.8}})
    reel = shots.Reel("user-chat-cli")
    reel.cli(["hmz", "chat", "start", "-a", AGENT, _ASK], rows=9)
    reel.save()

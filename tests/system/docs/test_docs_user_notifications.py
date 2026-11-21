"""The pictures of `docs/user/notifications.md`: what tells of an epic or chat not looked at.

The Notifications settings in the app's window and in a browser that has yet to allow them; a
chat answered while another view is open, marked unread in the sidebar until it is opened; the
Notifications page of the terminal interface; and a card in its corner as an epic ends under
`/epics`, whose row is dotted. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_notifications.py`.

What the system itself draws -- a macOS notification, a Windows toast, a browser's question
whether to allow them -- is no part of any interface of Humanize's, and is not pictured.
"""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from hmz.tui import Humanize
from tests.integration.doubles_tui import shows, until
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import again, go

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from playwright.sync_api import Locator, Page
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after, and the terminal they are taken in.
_PAGE = "user-notifications"
_SIZE = (96, 26)
#: Tall enough for every row of the Notifications page at once.
_TALL = (96, 34)

_TASK = "Add a discount code to checkout"
_ANSWER = "Checkout takes a discount code now: WELCOME10 is 10% off."

#: A browser that was never asked, and says yes once it is: a headless one says it was asked
#: and said no, and the question itself is the browser's own window, which no page draws.
_ASKED_ONCE = """
(() => {
  let now = 'default'
  Object.defineProperty(Notification, 'permission', { get: () => now })
  Notification.requestPermission = async () => (now = 'granted')
})()
"""


def _ready(page: Page) -> Locator:
    """The box of a new chat, once the agent it would start is on offer under it."""
    expect(page.get_by_role("button", name=re.compile("Nous: .*Haiku"))).to_be_visible()
    return page.get_by_role("textbox", name="First message")


@contextlib.asynccontextmanager
async def _tui(size: tuple[int, int]) -> AsyncGenerator[tuple[Humanize, Pilot[None]]]:
    """The terminal interface as `World.tui` runs it, with its corner cards drawn.

    Textual's test harness leaves the cards out of every screen unless asked for them, and
    the world's own helper does not ask: the app is the same one, in the same staged world.
    """
    app = Humanize()
    async with app.run_test(size=size, notifications=True) as pilot:
        yield app, pilot


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


def test_the_kinds_are_chosen_in_the_app(world: World) -> None:
    with world.page(desktop=True) as page:
        go(page, "/settings/notifications")
        expect(page.get_by_text("Shown by macOS.")).to_be_visible()
        shots.web(page, f"{_PAGE}-settings", clip=page.get_by_role("dialog"), pad=0)


def test_a_browser_is_asked_to_allow_them(world: World) -> None:
    with world.page(width=1040, height=640) as page:
        page.add_init_script(_ASKED_ONCE)
        again(page)
        go(page, "/settings/notifications")
        allow = page.get_by_role("button", name="Allow")
        expect(allow).to_be_visible()
        expect(page.get_by_text("Not asked")).to_be_visible()
        reel = shots.Reel(f"{_PAGE}-allow", window="browser")
        reel.web(page, hold=2.2, pointer=allow, click=True)
        allow.click()
        expect(page.get_by_text("Allowed")).to_be_visible()
        expect(page.get_by_text("Shown by the browser.")).to_be_visible()
        reel.web(page, hold=3.0, poster=True)
        reel.save()


def test_a_chat_answered_elsewhere_is_unread_until_opened(world: World) -> None:
    world.says({"discount": {"text": _ANSWER, "after": 4}})
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        box = _ready(page)
        box.fill(_TASK)
        box.press("Enter")
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        # Left while its turn is open: what it answers is heard on another view.
        go(page, "/new/chat")
        _ready(page)
        sidebar = page.locator("[data-hmz=sidebar]")
        dot = sidebar.locator("[data-hmz=unread]").first
        expect(dot).to_be_visible(timeout=60_000)
        expect(sidebar).not_to_contain_text("Running")
        page.wait_for_timeout(400)
        row = sidebar.locator(".side-item").filter(has_text=_TASK).first
        reel = shots.Reel(f"{_PAGE}-unread", window="desktop")
        reel.web(
            page,
            hold=2.6,
            pointer=row,
            click=True,
            caption="answered while another view was open",
        )
        row.click()
        expect(page.get_by_role("log")).to_contain_text("WELCOME10")
        expect(sidebar.locator("[data-hmz=unread]")).to_have_count(0)
        page.wait_for_timeout(400)
        reel.web(page, hold=3.0, caption="opened, and read", poster=True)
        reel.save()


async def test_the_kinds_are_chosen_in_the_terminal(world: World) -> None:
    async with world.tui(_TALL) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        await pilot.press(*"/settings notifications", "enter")
        await shows(pilot, "Which epics on this machine you are told of", "Shown")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-terminal-settings")


async def test_an_epic_ending_under_a_menu_is_told_by_a_card(world: World) -> None:
    world.says(
        {"discount": {"text": "Added a discount code to checkout.", "after": 30}}
    )
    world.epic("goal", _TASK, until=None)
    async with _tui(_SIZE) as (app, pilot):
        await shows(pilot, "is working")
        await pilot.press(*"/settings", "enter")
        await shows(pilot, "Every setting Humanize keeps")
        await _settled(pilot)
        reel = shots.Reel(f"{_PAGE}-terminal-card")
        reel.tui(
            app, hold=2.0, keys="/settings", caption="in a menu, an epic still going"
        )
        # The epic ends under the menu, which is not the screen it is read on: a card.
        await shows(pilot, "Done", "goal · shop")
        await _settled(pilot, 0.3)
        reel.tui(app, hold=3.5, caption="it ends: a card in the corner", poster=True)
        await pilot.press("escape")
        await until(pilot, lambda: len(app.screen_stack) == 1, "the menu to close")
        await pilot.press(*"/epics", "enter")
        await shows(pilot, "Every epic in this directory", "●")
        # The card goes by itself after a few seconds; the dot stays until the epic is opened.
        await until(pilot, lambda: not app._notifications, "the card to go")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        await _settled(pilot, 0.3)
        reel.tui(
            app, hold=3.5, keys="/epics", caption="and a dot on its row until opened"
        )
        reel.save()

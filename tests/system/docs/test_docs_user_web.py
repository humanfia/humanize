"""The pictures of `docs/user/web.md`: the page a browser is served by `hmz web`.

`hmz web` as it says where it serves; the page in a browser's window; a browser that was not
let in; the sidebar's list arranged by `Group and sort`; a folder's menu; Search opened over
the view by its shortcut; a button that asks, where it stands, before it does what cannot be
undone; and the page at a phone's width, its sidebar a drawer.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_web.py`.
"""

from __future__ import annotations

import contextlib
import re
import signal
import threading
import time
from typing import TYPE_CHECKING

import psutil
from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

    from tests.system.docs.conftest import World

_PAGE = "user-web"

#: The port the guide serves the page on, and what a browser's window says it is at.
_PORT = 8420
_AT = f"127.0.0.1:{_PORT}"

#: A phone's screen, in CSS pixels.
_PHONE = (390, 760)

_TASK = "Add a discount code to checkout"
_NEXT = "Should an expired code be refused?"
_OTHER = "Explain how the cart total is computed"
_EPIC = "Add a gift wrap option to the cart"

_ANSWER = (
    "Checkout takes a discount code now: charge() looks the code up and takes its"
    " discount off the total. WELCOME10 is 10% off. Two new tests cover it, and all"
    " six pass."
)
_REFUSED = "Yes. charge() now raises ExpiredCode for a code past its date."
_TOTAL = "total() in shop/cart.py multiplies each item's price by its count and adds them up."
_WRAPPED = "Gift wrap is an option of the cart now: it adds 300 cents to the total."


def _staged(world: World) -> str:
    """Two chats and an epic in the project; answers the id of the first chat."""
    world.says(
        {
            "discount": _ANSWER,
            "expired": _REFUSED,
            "cart total": _TOTAL,
            "gift wrap": _WRAPPED,
        }
    )
    world.chat(_OTHER)
    world.epic("goal", _EPIC)
    return world.chat(_TASK, _NEXT)


def _ready(page: Page) -> Locator:
    """The box of a new chat, once the agent it would start is on offer under it."""
    expect(page.get_by_role("button", name=re.compile("Nous: .*Haiku"))).to_be_visible()
    return page.get_by_role("textbox", name="First message")


def _interrupted(told: str, after: float = 1.5) -> threading.Thread:
    """Interrupts the `hmz` started from here whose command line holds `told`, once it serves.

    `hmz web` serves until it is stopped, and a picture is of a command that ended: it is
    stopped as ctrl+c stops it, a moment after it has said where it listens.
    """

    def waits() -> None:
        until = time.monotonic() + 90
        while time.monotonic() < until:
            for one in psutil.Process().children(recursive=True):
                with contextlib.suppress(psutil.Error, OSError):
                    if told in one.cmdline() and any(
                        at.laddr.port == _PORT for at in one.net_connections("tcp")
                    ):
                        time.sleep(after)
                        one.send_signal(signal.SIGINT)
                        return
            time.sleep(0.2)

    thread = threading.Thread(target=waits, daemon=True)
    thread.start()
    return thread


def test_hmz_web_says_where_it_serves(world: World) -> None:
    stopping = _interrupted("--no-open")
    shots.cli(
        ["hmz", "web", "--port", str(_PORT), "--no-open"], f"{_PAGE}-serve", columns=72
    )
    stopping.join(10)


def test_the_page_in_a_browser(world: World) -> None:
    chat = _staged(world)
    with world.page() as page:
        go(page, f"/chats/{chat}")
        expect(page.get_by_role("log")).to_contain_text("ExpiredCode")
        page.wait_for_timeout(400)
        shots.web(page, f"{_PAGE}-page", window="browser", address=_AT)


def test_a_browser_without_the_key_is_not_let_in(world: World) -> None:
    with world.page() as page:
        browser = page.context.browser
        assert browser is not None
        # Another browser, which was never given the address with its key.
        other = browser.new_context(viewport={"width": 900, "height": 420})
        try:
            stranger = other.new_page()
            stranger.goto(f"http://127.0.0.1:{world.site.port}/")
            expect(stranger.get_by_text("This browser is not let in.")).to_be_visible()
            stranger.wait_for_timeout(300)
            shots.web(stranger, f"{_PAGE}-not-let-in", window="browser", address=_AT)
        finally:
            other.close()


def test_the_list_is_grouped_by_date(world: World) -> None:
    _staged(world)
    with world.page(height=620) as page:
        go(page, "/new/chat")
        _ready(page)
        sidebar = page.locator("[data-hmz=sidebar]")
        expect(sidebar.get_by_text(_EPIC).first).to_be_visible()
        reel = shots.Reel(f"{_PAGE}-group-sort")
        # Every frame is of the sidebar and of what its menus open into beside it: more than
        # any one thing on the page, which is all `clip=` names.
        reel._at = shots._Box(0, 0, 640, 620)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        heading = sidebar.get_by_text("shop", exact=True).first
        heading.hover()
        sort = sidebar.get_by_role("button", name="Group and sort").first
        expect(sort).to_be_visible()
        reel.web(page, hold=1.5, pointer=sort, click=True)
        sort.click()
        by = page.get_by_role("menuitem", name=re.compile("Group by"))
        expect(by).to_be_visible()
        reel.web(page, hold=1.2, pointer=by, click=True)
        by.click()
        date = page.get_by_role("menuitemradio", name="Date")
        expect(date).to_be_visible()
        reel.web(page, hold=1.2, pointer=date, click=True)
        date.click()
        expect(sidebar.get_by_text("Today", exact=True)).to_be_visible()
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        reel.web(page, hold=3.5, poster=True)
        reel.save()


def test_a_folder_has_a_menu(world: World) -> None:
    _staged(world)
    with world.page(height=620) as page:
        go(page, "/new/chat")
        _ready(page)
        sidebar = page.locator("[data-hmz=sidebar]")
        heading = sidebar.get_by_text("shop", exact=True).first
        heading.click(button="right")
        here = page.get_by_role("menuitem", name="New chat here")
        expect(here).to_be_visible()
        expect(page.get_by_role("menuitem", name="Copy path")).to_be_visible()
        page.wait_for_timeout(300)
        # The menu and the heading it was opened on, over it.
        shots.web(page, f"{_PAGE}-folder-menu", clip=page.get_by_role("menu"), pad=56)


def test_search_opens_over_the_view(world: World) -> None:
    chat = _staged(world)
    with world.page() as page:
        go(page, f"/chats/{chat}")
        expect(page.get_by_role("log")).to_contain_text("ExpiredCode")
        reel = shots.Reel(f"{_PAGE}-search", window="browser", address=_AT)
        reel.web(page, hold=1.6)
        page.keyboard.press("Meta+k")
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible()
        expect(dialog.get_by_text(_EPIC).first).to_be_visible()
        page.wait_for_timeout(400)
        reel.web(page, hold=3, keys="cmd+k", poster=True)
        page.keyboard.press("Escape")
        expect(dialog).not_to_be_visible()
        page.wait_for_timeout(300)
        reel.web(page, hold=1.4, keys="esc")
        reel.save()


def test_a_button_asks_before_it_does_what_cannot_be_undone(world: World) -> None:
    _staged(world)
    with world.page(height=620) as page:
        go(page, "/new/chat")
        _ready(page)
        # The folder's own settings, as its menu opens them: their one button asks first.
        page.locator("[data-hmz=sidebar]").get_by_text("shop", exact=True).first.click(
            button="right"
        )
        page.get_by_role("menuitem", name="Settings").click()
        forget = page.get_by_role("dialog").get_by_role(
            "button", name="Forget", exact=True
        )
        expect(forget).to_be_visible()
        forget.click()
        asked = page.get_by_role("dialog", name=re.compile("^Forget how"))
        expect(asked.get_by_role("button", name="Cancel")).to_be_visible()
        page.wait_for_timeout(300)
        # The question, and the button it was asked by, beside it.
        shots.web(page, f"{_PAGE}-confirm", clip=asked, pad=48)


def test_on_a_narrow_window_the_sidebar_is_a_drawer(world: World) -> None:
    _staged(world)
    with world.page(width=_PHONE[0], height=_PHONE[1]) as page:
        # Over a new chat: the scrim over a chat's title does not print as it is drawn.
        go(page, "/new/chat")
        _ready(page)
        sidebar = page.locator("[data-hmz=sidebar]")
        expect(sidebar).not_to_be_in_viewport()
        show = page.get_by_role("button", name="Show sidebar")
        reel = shots.Reel(f"{_PAGE}-narrow")
        reel.web(page, hold=1.8, pointer=show, click=True)
        show.click()
        expect(sidebar).to_be_in_viewport()
        expect(sidebar.get_by_text(_EPIC).first).to_be_visible()
        # The drawer slides in over the page: the frame is of it come to rest.
        page.wait_for_timeout(1200)
        # The pointer rests on the scrim beside it, which a tap on closes it by.
        reel.web(page, hold=3, pointer=(345.0, 380.0), poster=True)
        reel.save()

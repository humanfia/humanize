"""`hmz web`'s notification centre: the bell, its menu, the cards, and the system's own.

The notifications are the browser's own, gathered from the notices of every daemon it follows:
here those of other daemons are kept in its storage as it would have kept them, and Local's are
told on its wire, as Local tells them over the notices subscription the page opened. So the page
is tested alone: a bell with how many are unread, a menu of them newest first that marks them
read and clears them, a card for each one heard, and -- while the page is not looked at -- one
the system shows, by the browser's `Notification` or by the macOS app. Each in Chromium and
WebKit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, Wire, noticed, opened

if TYPE_CHECKING:
    from playwright.sync_api import Page

pytestmark = pytest.mark.parametrize("engine", ENGINES)

#: What the macOS app's window says it is.
_APP = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) humanize-desktop/0.0.0"
)

#: A page that is never looked at, which the browser's and the app's notifications are stubbed in.
_AWAY = """
Object.defineProperty(document, 'hidden', { get: () => true })
document.hasFocus = () => false
window.shown = []
window.Notification = class {
  static permission = 'granted'
  constructor(title, options) { window.shown.push({ title, ...options }) }
  close() {}
}
"""

#: The app's own notifications, stubbed in once the page has reached its daemon over `/rpc`: set
#: before, the page would take itself for the app and reach every daemon through its pipes.
_APP_NOTIFIES = """() => {
  window.__TAURI_INTERNALS__ = {
    invoke: (command, args) => {
      window.shown.push({ command, ...args })
      return Promise.resolve()
    },
  }
}"""


def _notice(id_: int, kind: str, **more: Any) -> dict[str, Any]:
    """A notice, as a daemon makes one: of an epic, until `more` names a chat and no epic."""
    return {
        "id": id_,
        "kind": kind,
        "workspace": "/w",
        "slot": "",
        "epic": f"e{id_}",
        "chat": "",
        "flow": "ralph",
        "task": "Fix it",
        "role": "",
        "text": "",
        "at": 1760263200,
        **more,
    }


def _items(page: Page) -> list[dict[str, Any]]:
    """The notifications this browser keeps, newest first."""
    return page.evaluate("async () => (await import('/notifications.js')).kept.items()")


def _prefer(page: Page, *, system: bool) -> None:
    """Says whether the system shows them, as `Notifications` does."""
    page.evaluate(
        "async (system) => (await import('/notifications.js')).kept.prefer({ system })",
        system,
    )


def test_the_bell_counts_the_unread_and_its_menu_reads_and_clears_them(
    engine: str,
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        noticed(page, "devbox", _notice(1, "done") | {"read": True})
        noticed(page, "local", _notice(2, "asked", text="Which branch?"))
        bell = page.locator("[data-hmz=notifications]")
        expect(bell).to_be_visible()
        expect(bell.locator("[data-hmz=notification-count]")).to_have_text("1")

        bell.click()
        menu = page.locator("[data-hmz=notification-menu]")
        expect(menu.locator("[data-hmz=notification] .choice-label")).to_have_text(
            ["Question · Local", "Done · devbox"]
        )
        expect(menu.locator("[data-hmz=notification]").first).to_contain_text(
            "Which branch?"
        )
        expect(menu.locator(".notify-unread")).to_have_count(1)

        menu.locator("[data-hmz=notifications-read]").click()
        expect(menu.locator(".notify-unread")).to_have_count(0)
        expect(bell.locator("[data-hmz=notification-count]")).to_be_hidden()
        # Written to the browser's storage after it is drawn.
        page.wait_for_function(
            "async () => (await (await import('/notifications.js')).kept.items())"
            ".every((one) => one.read)"
        )
        assert all(one["read"] for one in _items(page))

        menu.locator("[data-hmz=notifications-clear]").click()
        expect(menu.locator("[data-hmz=notification]")).to_have_count(0)
        expect(menu).to_contain_text("Nothing yet")
        page.wait_for_function(
            "async () => !(await (await import('/notifications.js')).kept.items()).length"
        )


def test_an_item_picked_is_read_and_opens_what_it_is_about(engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        noticed(page, "devbox", _notice(3, "listening", workspace="/w/app"))
        page.locator("[data-hmz=notifications]").click()
        page.locator("[data-hmz=notification]").click()
        expect(page.locator("[data-hmz=notification-menu]")).to_have_count(0)
        assert page.evaluate("location.hash") == "#/@devbox/live?workspace=%2Fw%2Fapp"
        # It is kept as read a moment after it is picked: waited for, not caught up with.
        page.wait_for_function(
            """async () => (await (await import('/notifications.js')).kept.items())
              .every((one) => one.read)"""
        )
        assert [one["read"] for one in _items(page)] == [True]


def test_a_notice_heard_is_a_card_that_opens_it(engine: str) -> None:
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        wire.tell(page, _notice(4, "failed", epic="big-fix"))
        card = page.locator("[data-hmz=toasts] [data-hmz=notification-toast]")
        expect(card).to_have_count(1)
        expect(card).to_contain_text("Failed · Local")
        expect(page.locator("[data-hmz=notification-count]")).to_have_text("1")
        card.locator(".notify-open").click()
        assert page.evaluate("location.hash") == "#/epics/big-fix"
        expect(card).to_have_count(0)
        expect(page.locator("[data-hmz=notification-count]")).to_be_hidden()
        # A chat's names the chat, and no epic: it opens the chat, at its own address.
        wire.faked["chat.get"] = lambda _: None
        turn = _notice(5, "done", slot="chat:ab", epic="", chat="c5", flow="")
        wire.tell(page, turn)
        expect(card).to_have_count(1)
        expect(card).to_contain_text("Waiting · Local")
        card.locator(".notify-open").click()
        assert page.evaluate("location.hash") == "#/chats/c5"
        expect(page.locator("[data-hmz=notification-count]")).to_be_hidden()
        # Followed from the last heard, when the page is opened again.
        assert (
            page.evaluate(
                "async () => (await import('/notifications.js')).kept.after('local')"
            )
            == 5
        )


def test_a_kind_switched_off_is_not_told(engine: str) -> None:
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        page.evaluate(
            """async () => (await import('/notifications.js'))
              .kept.prefer({ kinds: { listening: false } })"""
        )
        # A chat's turn done is a chat turn.
        wire.tell(page, _notice(5, "done", slot="chat:ab", epic="", chat="c5"))
        wire.tell(page, _notice(6, "stopped"))
        expect(page.locator("[data-hmz=notification-toast]")).to_have_count(1)
        assert [one["id"] for one in _items(page)] == [6]


def test_the_bell_is_there(engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        expect(page.locator("[data-hmz=notifications]")).to_be_visible()


def test_the_bells_menu_is_the_one_popup_open(engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        noticed(page, "local", _notice(1, "done"))
        bell = page.locator("[data-hmz=notifications]")
        menu = page.locator("[data-hmz=notification-menu]")
        picker = page.locator("[data-hmz=daemon-picker]")
        bar = page.locator("[data-hmz=daemon-bar]")

        # Another menu opened by the keyboard, with no press outside the bell's, shuts it.
        bell.click()
        expect(menu).to_be_visible()
        bar.focus()
        page.keyboard.press("Enter")
        expect(picker).to_be_visible()
        expect(menu).to_be_hidden()
        expect(bell).to_have_attribute("aria-expanded", "false")

        # And the bell's, opened by the keyboard, shuts that one.
        bell.focus()
        page.keyboard.press("Enter")
        expect(menu).to_be_visible()
        expect(picker).to_be_hidden()

        # Search opened by its key leaves no menu up under it.
        page.keyboard.press("Control+k")
        expect(page.locator("[data-hmz=dialog-search]")).to_be_visible()
        expect(menu).to_be_hidden()


@pytest.mark.parametrize("system", [True, False])
def test_the_browser_shows_one_while_the_page_is_not_looked_at(
    engine: str, system: bool
) -> None:
    wire = Wire()
    with (
        served() as site,
        opened(site, engine=engine, init=_AWAY, routed=wire.routes) as page,
    ):
        _prefer(page, system=system)
        wire.tell(page, _notice(5, "done", text="All green"))
        expect(page.locator("[data-hmz=notification-toast]")).to_have_count(1)
        if system:
            page.wait_for_function("() => window.shown.length > 0")
            assert page.evaluate("window.shown") == [
                {"title": "Done · Local", "body": "ralph · All green", "tag": "local:5"}
            ]
        else:
            page.wait_for_timeout(500)
            assert page.evaluate("window.shown") == []


def test_the_app_shows_one_through_its_own_notifications(engine: str) -> None:
    wire = Wire()
    with (
        served() as site,
        opened(
            site, engine=engine, user_agent=_APP, init=_AWAY, routed=wire.routes
        ) as page,
    ):
        page.evaluate(_APP_NOTIFIES)
        wire.tell(page, _notice(6, "asked", text="Ship it?"))
        expect(page.locator("[data-hmz=notification-toast]")).to_have_count(1)
        page.wait_for_function("() => window.shown.length > 0")
        assert page.evaluate("window.shown") == [
            {
                "command": "notify",
                "title": "Question · Local",
                "body": "ralph · Ship it?",
                "address": "#/live?workspace=%2Fw",
            }
        ]


#: A page looked at, on the epic `e7`.
_ON_E7 = """
history.replaceState(null, '', '#/epics/e7')
document.hasFocus = () => true
"""

#: The sidebar's list of epics: `e7` and `e8`, both of the workspace `/w`.
_RUNS: dict[str, Any] = {
    "runs": [
        {
            "name": name,
            "workspace": "/w",
            "task": f"Fix {name}",
            "kind": "flow",
            "flow": "ralph",
            "how": "done",
            "held": False,
            "began": "2026-10-12T09:00:00Z",
            "agents": [],
        }
        for name in ("e8", "e7")
    ],
    "total": 2,
    "offset": 0,
    "limit": 60,
    "counts": {},
    "flows": [],
}


def test_none_is_told_of_the_epic_the_page_is_on(engine: str) -> None:
    wire = Wire(faked={"runs.list": lambda _: {"result": _RUNS}})
    with (
        served() as site,
        opened(site, engine=engine, init=_ON_E7, routed=wire.routes) as page,
    ):
        expect(page.locator("[data-hmz=epic]")).to_have_count(2)
        wire.tell(page, _notice(9, "asked", epic="e7"))
        wire.tell(page, _notice(10, "done", epic="e8"))
        expect(page.locator("[data-hmz=notification-toast]")).to_have_count(1)
        assert [(one["epic"], one["read"]) for one in _items(page)] == [
            ("e8", False),
            ("e7", True),
        ]
        expect(page.locator("[data-hmz=notification-count]")).to_have_text("1")


def test_an_unread_one_marks_its_epic_until_it_is_opened(engine: str) -> None:
    wire = Wire(faked={"runs.list": lambda _: {"result": _RUNS}})
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        wire.tell(page, _notice(8, "done", epic="e8"))
        expect(page.locator("[data-hmz=notification-toast]")).to_have_count(1)
        row = page.locator("[data-hmz=epics] .side-item[data-epic=e8]")
        expect(row.locator("[data-hmz=unread]")).to_have_count(1)
        expect(page.locator("[data-hmz=unread]")).to_have_count(1)

        # Folded, its workspace carries the mark instead.
        group = page.locator("[data-hmz=workspace][data-path='/w']")
        group.locator(".side-folder .side-toggle").click()
        expect(group.locator(".side-folder [data-hmz=unread]")).to_have_count(1)
        group.locator(".side-folder .side-toggle").click()

        row.locator("[data-hmz=epic]").click()
        expect(page.locator("[data-hmz=unread]")).to_have_count(0)
        expect(page.locator("[data-hmz=notification-count]")).to_be_hidden()
        assert [one["read"] for one in _items(page)] == [True]

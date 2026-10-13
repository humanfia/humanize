"""`hmz web`'s notification centre: the bell, its menu, the cards, and the system's own.

The global notifications are the local server's, of every daemon; here they are answered by
the browser itself, routed before the page asks, so the page is tested alone: a bell with how
many are unread, a menu of them newest first that marks them read and clears them, a card for
each one heard on the stream, and -- while the page is not looked at -- one the system shows,
by the browser's `Notification` or by the macOS app. Each in Chromium and WebKit.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, opened

if TYPE_CHECKING:
    from playwright.sync_api import Page, Route

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
window.__TAURI_INTERNALS__ = {
  invoke: (command, args) => { window.shown.push({ command, ...args }); return Promise.resolve() },
}
"""


def _item(id_: int, kind: str, **more: Any) -> dict[str, Any]:
    return {
        "id": id_,
        "kind": kind,
        "daemon": "local",
        "workspace": "/w",
        "epic": f"e{id_}",
        "flow": "chat",
        "task": "Fix it",
        "role": "",
        "text": "",
        "at": "2026-10-12T10:00:00Z",
        "read": False,
        **more,
    }


@dataclass
class Feed:
    """The server's notifications, as the page is answered them, and what it was sent."""

    items: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    heard: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    system: bool = True
    sent: list[tuple[str, Any]] = field(default_factory=list[tuple[str, Any]])
    asked: int = 0

    def routes(self, page: Page) -> None:
        page.route("**/api/notifications", self._list)
        page.route("**/api/notifications/stream", self._stream)
        page.route("**/api/notifications/settings", self._settings)
        page.route("**/api/notifications/read", self._written)
        page.route("**/api/notifications/clear", self._written)

    def _list(self, route: Route) -> None:
        unread = sum(not one["read"] for one in self.items)
        route.fulfill(json={"items": self.items, "unread": unread})

    def _stream(self, route: Route) -> None:
        # What is heard is told once, and kept with the rest from then on, as the server does.
        said = "retry: 60000\n\n" + "".join(
            f"event: notification\nid: {one['id']}\ndata: {json.dumps(one)}\n\n"
            for one in self.heard
        )
        self.items[:0] = reversed(self.heard)
        self.heard = []
        route.fulfill(
            status=200,
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
            body=said,
        )

    def _settings(self, route: Route) -> None:
        self.asked += 1
        kinds = dict.fromkeys(("done", "failed", "stopped", "asked", "listening"), True)
        route.fulfill(json={"kinds": kinds, "system": self.system})

    def _written(self, route: Route) -> None:
        request = route.request
        what = request.url.rsplit("/", 1)[1]
        said: dict[str, Any] = request.post_data_json or {}
        self.sent.append((what, said))
        if what == "clear":
            self.items = []
        for one in self.items:
            one["read"] = (
                one["read"] or said.get("all") or one["id"] in said.get("ids", [])
            )
        route.fulfill(json={})


def test_the_bell_counts_the_unread_and_its_menu_reads_and_clears_them(
    engine: str,
) -> None:
    feed = Feed(
        items=[
            _item(2, "asked", text="Which branch?"),
            _item(1, "done", daemon="devbox", read=True),
        ]
    )
    with served() as site, opened(site, engine=engine, routed=feed.routes) as page:
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
        assert feed.sent == [("read", {"all": True})]

        menu.locator("[data-hmz=notifications-clear]").click()
        expect(menu.locator("[data-hmz=notification]")).to_have_count(0)
        expect(menu).to_contain_text("Nothing yet")
        assert feed.sent[-1] == ("clear", {})


def test_an_item_picked_is_read_and_opens_what_it_is_about(engine: str) -> None:
    feed = Feed(items=[_item(3, "listening", daemon="devbox", workspace="/w/app")])
    with served() as site, opened(site, engine=engine, routed=feed.routes) as page:
        page.locator("[data-hmz=notifications]").click()
        page.locator("[data-hmz=notification]").click()
        expect(page.locator("[data-hmz=notification-menu]")).to_have_count(0)
        assert page.evaluate("location.hash") == "#/@devbox/live?workspace=%2Fw%2Fapp"
        assert feed.sent == [("read", {"ids": [3]})]


def test_a_notification_heard_is_a_card_that_opens_it(engine: str) -> None:
    feed = Feed(heard=[_item(4, "failed", daemon="devbox", epic="big-fix")])
    with served() as site, opened(site, engine=engine, routed=feed.routes) as page:
        card = page.locator(
            "[data-hmz=notification-toasts] [data-hmz=notification-toast]"
        )
        expect(card).to_have_count(1)
        expect(card).to_contain_text("Failed · devbox")
        expect(page.locator("[data-hmz=notification-count]")).to_have_text("1")
        card.locator(".notify-open").click()
        assert page.evaluate("location.hash") == "#/@devbox/epics/big-fix"
        expect(card).to_have_count(0)
        expect(page.locator("[data-hmz=notification-count]")).to_be_hidden()


def test_there_is_no_bell_where_the_server_has_no_notifications(engine: str) -> None:
    def older(page: Page) -> None:
        # A server of an older humanize, which has none to give.
        page.route(
            re.compile(r".*/api/notifications(/.*|\?.*)?$"),
            lambda route: route.fulfill(status=404, json={"error": "Not found."}),
        )

    with served() as site, opened(site, engine=engine, routed=older) as page:
        expect(page.locator("[data-hmz=sidebar] .brand")).to_be_visible()
        expect(page.locator("[data-hmz=notifications]")).to_be_hidden()


def test_the_bell_is_there_where_the_server_has_notifications(engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        expect(page.locator("[data-hmz=notifications]")).to_be_visible()


@pytest.mark.parametrize("system", [True, False])
def test_the_browser_shows_one_while_the_page_is_not_looked_at(
    engine: str, system: bool
) -> None:
    feed = Feed(heard=[_item(5, "done", text="All green")], system=system)
    with (
        served() as site,
        opened(site, engine=engine, init=_AWAY, routed=feed.routes) as page,
    ):
        expect(page.locator("[data-hmz=notification-toast]")).to_have_count(1)
        if system:
            page.wait_for_function("window.shown.length > 0")
            assert page.evaluate("window.shown") == [
                {"title": "Done · Local", "body": "chat · All green", "tag": "5"}
            ]
        else:
            # The settings are read before the stream is opened: once they are answered, the
            # page has had all it needs to show one, and must have shown none.
            while not feed.asked:
                page.wait_for_timeout(50)
            page.wait_for_timeout(500)
            assert page.evaluate("window.shown") == []


def test_the_app_shows_one_through_its_own_notifications(engine: str) -> None:
    feed = Feed(heard=[_item(6, "asked", text="Ship it?")])
    with (
        served() as site,
        opened(
            site, engine=engine, user_agent=_APP, init=_AWAY, routed=feed.routes
        ) as page,
    ):
        expect(page.locator("[data-hmz=notification-toast]")).to_have_count(1)
        page.wait_for_function("window.shown.length > 0")
        assert page.evaluate("window.shown") == [
            {
                "command": "notify",
                "title": "Question · Local",
                "body": "chat · Ship it?",
                "address": "#/live?workspace=%2Fw",
            }
        ]


#: A page looked at, on the epic `e7`.
_ON_E7 = """
history.replaceState(null, '', '#/epics/e7')
document.hasFocus = () => true
"""


def _listed(page: Page) -> None:
    """Answers the sidebar's list of epics with `e7` and `e8`, both of the workspace `/w`."""
    runs: list[dict[str, Any]] = [
        {
            "name": name,
            "workspace": "/w",
            "task": f"Fix {name}",
            "flow": "chat",
            "how": "done",
            "held": False,
            "began": "2026-10-12T09:00:00Z",
            "agents": [],
        }
        for name in ("e8", "e7")
    ]
    page.route(
        re.compile(r".*/api/runs\?.*"),
        lambda route: route.fulfill(json={"runs": runs, "total": len(runs)}),
    )


def test_none_is_told_of_the_epic_the_page_is_on(engine: str) -> None:
    feed = Feed(heard=[_item(7, "done"), _item(9, "asked", epic="e7")])

    def routed(page: Page) -> None:
        feed.routes(page)
        _listed(page)

    with (
        served() as site,
        opened(site, engine=engine, init=_ON_E7, routed=routed) as page,
    ):
        expect(page.locator("[data-hmz=epic]")).to_have_count(2)
        while {id_ for _, said in feed.sent for id_ in said["ids"]} != {7, 9}:
            page.wait_for_timeout(50)
        expect(page.locator("[data-hmz=notification-toast]")).to_have_count(0)
        expect(page.locator("[data-hmz=notification-count]")).to_be_hidden()
        expect(page.locator("[data-hmz=unread]")).to_have_count(0)


def test_an_unread_one_marks_its_epic_until_it_is_opened(engine: str) -> None:
    feed = Feed(heard=[_item(8, "done")])

    def routed(page: Page) -> None:
        feed.routes(page)
        _listed(page)

    with served() as site, opened(site, engine=engine, routed=routed) as page:
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
        while not feed.sent:
            page.wait_for_timeout(50)
        assert feed.sent == [("read", {"ids": [8]})]

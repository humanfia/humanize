"""`hmz web`'s notifications: the system's own, and the sidebar's marks; none the page draws.

The page follows the notices of every daemon it reaches: here Local's are told on its wire, as
Local tells them over the notices subscription the page opened. So the page is tested alone: no
bell, no list and no card; a mark on the row of what a notice is of, and one the system shows
-- by the browser's `Notification` or by the desktop app -- unless the page is looked at and on
that chat or epic. Each in Chromium and WebKit.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, Wire, opened

if TYPE_CHECKING:
    from playwright.sync_api import Page

pytestmark = pytest.mark.parametrize("engine", ENGINES)

#: What the macOS app's window says it is.
_APP = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) humanize-desktop/0.0.0"
)

#: The browser's notifications, stubbed in and allowed: each made is kept, the last to click.
_ALLOWED = """
window.shown = []
window.Notification = class {
  static permission = 'granted'
  constructor(title, options) { window.shown.push({ title, ...options }); window.last = this }
  close() {}
}
"""

#: A page that is looked at.
_LOOKED = "document.hasFocus = () => true\n"

#: A page that is never looked at.
_AWAY = (
    _ALLOWED
    + """
Object.defineProperty(document, 'hidden', { get: () => true })
document.hasFocus = () => false
"""
)

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
        "at": time.time(),
        **more,
    }


def _unread(page: Page) -> list[str]:
    """The rows this browser keeps as unread, each by its daemon and name."""
    return page.evaluate("JSON.parse(localStorage.getItem('hmz-unread') || '[]')")


def _prefer(page: Page, *, system: bool) -> None:
    """Says whether the system shows them, as `Notifications` does."""
    page.evaluate(
        "async (system) => (await import('/notifications.js')).kept.prefer({ system })",
        system,
    )


def test_the_page_draws_no_notification_of_its_own(engine: str) -> None:
    wire = Wire()
    with (
        served() as site,
        opened(
            site, engine=engine, init=_ALLOWED + _LOOKED, routed=wire.routes
        ) as page,
    ):
        wire.tell(page, _notice(4, "failed", epic="big-fix"))
        page.wait_for_function("() => window.shown.length > 0")
        for gone in ("notifications", "notification-count", "notification-toast"):
            expect(page.locator(f"[data-hmz={gone}]")).to_have_count(0)
        expect(page.get_by_role("button", name="Notifications")).to_have_count(0)
        expect(page.locator("[data-hmz=toasts] > *")).to_have_count(0)


def test_a_page_looked_at_elsewhere_is_told_by_the_system_and_a_click_opens_it(
    engine: str,
) -> None:
    wire = Wire()
    with (
        served() as site,
        opened(
            site, engine=engine, init=_ALLOWED + _LOOKED, routed=wire.routes
        ) as page,
    ):
        wire.tell(page, _notice(4, "failed", epic="big-fix"))
        page.wait_for_function("() => window.shown.length > 0")
        assert page.evaluate("window.shown") == [
            {"title": "Failed · Local", "body": "ralph · Fix it", "tag": "local:4"}
        ]
        assert _unread(page) == ["local big-fix"]
        page.evaluate("window.last.onclick()")
        assert page.evaluate("location.hash") == "#/epics/big-fix"
        page.wait_for_function("() => !localStorage.getItem('hmz-unread')")
        # A chat's names the chat, and no epic: it opens the chat, at its own address.
        wire.faked["chat.get"] = lambda _: None
        chat = _notice(
            5,
            "done",
            slot="chat:ab",
            epic="",
            chat="c5",
            flow="chat",
            task="Cut the tiles",
            text="did: the tiles",
        )
        wire.tell(page, chat)
        page.wait_for_function("() => window.shown.length > 1")
        # A chat has no flow: its task says which chat, before what was answered.
        assert page.evaluate("[window.shown[1].title, window.shown[1].body]") == [
            "Waiting · Local",
            "Cut the tiles · did: the tiles",
        ]
        page.evaluate("window.last.onclick()")
        assert page.evaluate("location.hash") == "#/chats/c5"
        # Told twice, shown once; and followed from the last heard, when the page is opened again.
        wire.tell(page, chat)
        page.wait_for_timeout(300)
        assert page.evaluate("window.shown.length") == 2
        assert (
            page.evaluate(
                "async () => (await import('/notifications.js')).kept.after('local')"
            )
            == 5
        )


def test_a_kind_switched_off_is_not_told(engine: str) -> None:
    wire = Wire()
    with (
        served() as site,
        opened(
            site, engine=engine, init=_ALLOWED + _LOOKED, routed=wire.routes
        ) as page,
    ):
        page.evaluate(
            """async () => (await import('/notifications.js'))
              .kept.prefer({ kinds: { listening: false } })"""
        )
        # A chat's turn done is a chat turn.
        wire.tell(page, _notice(5, "done", slot="chat:ab", epic="", chat="c5"))
        wire.tell(page, _notice(6, "stopped"))
        page.wait_for_function("() => window.shown.length > 0")
        assert [one["tag"] for one in page.evaluate("window.shown")] == ["local:6"]
        assert _unread(page) == ["local e6"]


def test_one_made_long_before_it_is_heard_marks_its_row_and_is_not_shown(
    engine: str,
) -> None:
    wire = Wire()
    with (
        served() as site,
        opened(site, engine=engine, init=_AWAY, routed=wire.routes) as page,
    ):
        wire.tell(page, _notice(3, "done", at=time.time() - 3600))
        page.wait_for_function("() => localStorage.getItem('hmz-unread')")
        assert _unread(page) == ["local e3"]
        page.wait_for_timeout(300)
        assert page.evaluate("window.shown") == []


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
        page.wait_for_function("() => localStorage.getItem('hmz-unread')")
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
        opened(site, engine=engine, init=_ALLOWED + _ON_E7, routed=wire.routes) as page,
    ):
        expect(page.locator("[data-hmz=epic]")).to_have_count(2)
        wire.tell(page, _notice(9, "asked", epic="e7"))
        wire.tell(page, _notice(10, "done", epic="e8"))
        page.wait_for_function("() => window.shown.length > 0")
        assert [one["tag"] for one in page.evaluate("window.shown")] == ["local:10"]
        assert _unread(page) == ["local e8"]
        row = page.locator("[data-hmz=epics] .side-item[data-epic=e8]")
        expect(row.locator("[data-hmz=unread]")).to_have_count(1)
        expect(page.locator("[data-hmz=unread]")).to_have_count(1)


def test_an_unread_one_marks_its_epic_until_it_is_opened(engine: str) -> None:
    wire = Wire(faked={"runs.list": lambda _: {"result": _RUNS}})
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        wire.tell(page, _notice(8, "done", epic="e8"))
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
        assert _unread(page) == []


def test_a_question_clicked_reads_its_epic_wherever_its_address_leads(
    engine: str,
) -> None:
    wire = Wire(faked={"runs.list": lambda _: {"result": _RUNS}})
    with (
        served() as site,
        opened(
            site, engine=engine, init=_ALLOWED + _LOOKED, routed=wire.routes
        ) as page,
    ):
        wire.tell(page, _notice(11, "asked", epic="e8", slot="s", text="Ship it?"))
        page.wait_for_function("() => window.shown.length > 0")
        expect(page.locator("[data-hmz=unread]")).to_have_count(1)
        # A question opens the epic going where it works, by no name: it is read all the same.
        page.evaluate("window.last.onclick()")
        assert page.evaluate("location.hash") == "#/live?workspace=%2Fw&slot=s"
        expect(page.locator("[data-hmz=unread]")).to_have_count(0)
        assert _unread(page) == []


#: A page loaded on the epic `e8`, which this browser keeps as unread.
_MARKED_ON_E8 = """
localStorage.setItem('hmz-unread', JSON.stringify(['local e8', 'local e7']))
history.replaceState(null, '', '#/epics/e8')
"""


def test_a_page_loaded_on_a_marked_epic_reads_it(engine: str) -> None:
    wire = Wire(faked={"runs.list": lambda _: {"result": _RUNS}})
    with (
        served() as site,
        opened(site, engine=engine, init=_MARKED_ON_E8, routed=wire.routes) as page,
    ):
        expect(page.locator("[data-hmz=epic]")).to_have_count(2)
        row = page.locator("[data-hmz=epics] .side-item[data-epic=e7]")
        expect(row.locator("[data-hmz=unread]")).to_have_count(1)
        expect(page.locator("[data-hmz=unread]")).to_have_count(1)
        assert _unread(page) == ["local e7"]

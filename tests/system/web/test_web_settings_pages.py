"""`hmz web`'s Daemons and Notifications settings pages, driven in a browser.

The page is the real one, served in the test's own process; what it asks of the daemons and the
notification settings is answered by fakes routed in the browser, which keep what is written to
them, so that what the page sent is what is checked. Each test runs in Chromium and in WebKit.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, go, opened

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Page, Request, Route

pytestmark = pytest.mark.parametrize("engine", ENGINES)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, and a project to serve."""
    return install(tmp_path, monkeypatch)


class _Daemons:
    """The daemon registry, as the page asks it: kept in a list, and every write recorded."""

    def __init__(self) -> None:
        self.daemons: list[dict[str, Any]] = [
            {
                "name": "box",
                "host": "box.example",
                "user": "me",
                "port": 22,
                "state": "up",
            }
        ]
        self.hosts = [{"alias": "gpu", "host": "gpu.example"}, {"alias": "cpu"}]
        self.writes: list[tuple[str, Any]] = []

    def listed(self) -> dict[str, Any]:
        return {"daemons": [{"name": "local", "state": "up"}, *self.daemons]}

    def answer(self, route: Route) -> None:
        path = urllib.parse.urlsplit(route.request.url).path
        body = json.loads(route.request.post_data or "{}")
        if route.request.method == "POST":
            self.writes.append((path, body))
        if path == "/api/daemons/hosts":
            said: Any = {"hosts": self.hosts}
        elif path == "/api/daemons/import":
            self.daemons += [{"name": one, "host": one} for one in body["aliases"]]
            self.hosts = [
                one for one in self.hosts if one["alias"] not in body["aliases"]
            ]
            said = self.listed()
        elif path == "/api/daemons/remove":
            self.daemons = [one for one in self.daemons if one["name"] != body["name"]]
            said = self.listed()
        elif path.endswith("/connect"):
            route.fulfill(status=409, json={"error": "it did not answer"})
            return
        elif route.request.method == "POST":
            self.daemons = [one for one in self.daemons if one["name"] != body["name"]]
            self.daemons.append({"name": body["name"], **body["fields"]})
            said = self.listed()
        else:
            said = self.listed()
        route.fulfill(json=said)


def _daemons(page: Page) -> _Daemons:
    fake = _Daemons()
    page.route("**/api/daemons**", fake.answer)
    return fake


def test_a_daemon_is_added_a_part_at_a_time(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        fake = _daemons(page)
        go(page, "/settings/daemons")
        rows = page.locator("[data-hmz=daemon]")
        expect(rows).to_have_count(2)
        expect(rows.first).to_contain_text("Local")
        expect(rows.first.get_by_role("button")).to_have_count(0)
        form = page.locator("[data-hmz=write-daemon]")
        form.get_by_label("Name").fill("lab")
        form.get_by_label("Host").fill("lab.example")
        form.get_by_label("User").fill("ann")
        form.get_by_label("Port").fill("2222")
        form.locator("#daemon-identity").fill("~/.ssh/lab")
        form.get_by_label("Proxy jump").fill("me@jump")
        form.get_by_role("button", name="Add", exact=True).first.click()
        form.locator(".pair-key").fill("ServerAliveInterval")
        form.locator(".pair-value").fill("30")
        form.get_by_role("button", name="Add", exact=True).last.click()
        expect(rows).to_have_count(3)
        expect(page.locator("[data-hmz=daemon][data-name=lab]")).to_contain_text(
            "ann@lab.example:2222"
        )
        assert fake.writes[-1] == (
            "/api/daemons",
            {
                "name": "lab",
                "fields": {
                    "host": "lab.example",
                    "user": "ann",
                    "port": 2222,
                    "identity_file": "~/.ssh/lab",
                    "proxy_jump": "me@jump",
                    "options": [["ServerAliveInterval", "30"]],
                },
                "replace": False,
            },
        )


def test_hosts_are_imported_from_the_ssh_config(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        fake = _daemons(page)
        go(page, "/settings/daemons")
        importing = page.locator("[data-hmz=import-daemons]")
        importing.get_by_role("button", name="Read SSH config").click()
        importing.locator("[data-alias=gpu]").check()
        importing.get_by_role("button", name="Import").click()
        expect(page.locator("[data-hmz=daemon][data-name=gpu]")).to_be_visible()
        assert fake.writes[-1] == ("/api/daemons/import", {"aliases": ["gpu"]})


def test_a_daemon_is_removed_once_confirmed(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        fake = _daemons(page)
        go(page, "/settings/daemons")
        row = page.locator("[data-hmz=daemon][data-name=box]")
        row.get_by_role("button", name="Remove").click()
        assert not fake.writes
        row.get_by_role("button", name="Cancel").click()
        row.get_by_role("button", name="Remove").click()
        row.get_by_role("button", name="Remove").click()
        expect(row).to_have_count(0)
        assert fake.writes == [("/api/daemons/remove", {"name": "box"})]


def test_a_refused_connection_is_said_where_it_happened(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _daemons(page)
        go(page, "/settings/daemons")
        row = page.locator("[data-hmz=daemon][data-name=box]")
        row.get_by_role("button", name="Connect").click()
        expect(row.locator(".error")).to_have_text("it did not answer")


def test_without_the_endpoints_the_pages_say_unavailable(
    project: Path, engine: str
) -> None:
    def older(page: Page) -> None:
        # A server of an older humanize, which has neither.
        page.route(
            re.compile(r".*/api/(daemons|notifications)(/.*|\?.*)?$"),
            lambda route: route.fulfill(status=404, json={"error": "Not found."}),
        )

    with served() as site, opened(site, engine=engine, routed=older) as page:
        for name in ("daemons", "notifications"):
            go(page, f"/settings/{name}")
            body = page.locator(f"[data-hmz=settings-{name}]")
            expect(body.locator(".empty")).to_contain_text("Unavailable")
            expect(body.locator(".error")).to_have_count(0)


def _posted(request: Request) -> bool:
    return request.method == "POST"


#: The browser's notifications, as a page that was never asked sees them, granting when asked.
_NOTIFICATION = """
window.Notification = class { constructor() {} }
window.Notification.permission = 'default'
window.Notification.requestPermission = async () => {
  window.__asked = (window.__asked || 0) + 1
  window.Notification.permission = 'granted'
  return 'granted'
}
"""


def test_notification_kinds_are_saved_as_they_are_toggled(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine, init=_NOTIFICATION) as page:
        saved: list[Any] = []
        settings = {"kinds": {"done": True, "failed": False}, "system": True}

        def answer(route: Route) -> None:
            if route.request.method == "POST":
                saved.append(json.loads(route.request.post_data or "{}"))
                settings.update(saved[-1])
            route.fulfill(json=settings)

        page.route("**/api/notifications/settings", answer)
        go(page, "/settings/notifications")
        expect(page.locator("[data-hmz=notify-failed]")).not_to_be_checked()
        expect(page.locator("[data-hmz=notify-asked]")).to_be_checked()
        for label in ("Done", "Failed", "Stopped", "Questions", "Chat turns"):
            expect(page.get_by_label(label, exact=True)).to_be_visible()
        with page.expect_request(_posted):
            page.get_by_label("Questions", exact=True).uncheck()
        expect(page.locator("[data-hmz=notifications-said]")).to_have_text("Saved")
        with page.expect_request(_posted):
            page.locator("[data-hmz=notify-system]").uncheck()
        expect(page.locator("[data-hmz=notifications-said]")).to_have_text("Saved")
        assert saved == [
            {
                "kinds": {
                    "done": True,
                    "failed": False,
                    "stopped": True,
                    "asked": False,
                    "listening": True,
                },
                "system": True,
            },
            {
                "kinds": {
                    "done": True,
                    "failed": False,
                    "stopped": True,
                    "asked": False,
                    "listening": True,
                },
                "system": False,
            },
        ]


def test_notifications_are_allowed_from_a_click(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine, init=_NOTIFICATION) as page:
        page.route(
            "**/api/notifications/settings",
            lambda route: route.fulfill(json={"kinds": {}, "system": True}),
        )
        go(page, "/settings/notifications")
        state = page.locator("[data-hmz=permission-state]")
        expect(state).to_have_text("Not asked")
        page.locator("[data-hmz=allow-notifications]").click()
        expect(state).to_have_text("Allowed")
        expect(page.locator("[data-hmz=allow-notifications]")).to_have_count(0)
        assert page.evaluate("window.__asked") == 1


class _Held:
    """Requests kept from their answer until let go, so what the page shows meanwhile is seen."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.routes: list[Route] = []

    def __call__(self, route: Route) -> None:
        self.routes.append(route)

    def go(self) -> None:
        for _ in range(200):
            if self.routes:
                break
            self.page.wait_for_timeout(50)
        assert self.routes, "the page asked for nothing"
        self.routes.pop(0).fallback()


def test_what_is_being_read_says_so_until_it_is_answered(
    project: Path, engine: str
) -> None:
    (project.parent / "home" / "keys").mkdir(parents=True)
    with served() as site, opened(site, engine=engine) as page:
        _daemons(page)
        held = _Held(page)
        page.route("**/api/daemons", held)
        go(page, "/settings/daemons")
        listing = page.locator("[data-hmz=daemons]")
        expect(listing.locator(".loading")).to_have_text("Reading the daemons…")
        held.go()
        expect(page.locator("[data-hmz=daemon]")).to_have_count(2)
        page.unroute("**/api/daemons", held)

        page.route("**/api/files?**", held)
        page.locator("[data-hmz=write-daemon] [data-hmz=path-browse]").click()
        panel = page.get_by_role("dialog", name="Choose Identity file")
        expect(panel.locator(".loading")).to_have_text("Reading…")
        held.go()
        expect(panel.locator(".path-list")).to_be_visible()
        panel.locator(".path-entry", has_text="keys").click()
        expect(panel).to_have_attribute("aria-busy", "true")
        expect(panel.locator(".crumb").last).to_have_text("~")
        held.go()
        expect(panel).not_to_have_attribute("aria-busy", "true")
        expect(panel.locator(".crumb").last).to_have_text("keys")


def test_a_range_shown_stays_busy_until_the_next_is_read(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/usage")
        usage = page.locator("[data-hmz=usage]")
        expect(usage.locator(".panel").first).to_be_visible()
        held = _Held(page)
        page.route(re.compile(r".*/api/usage\?days=7\b.*"), held)
        page.get_by_role("button", name="7d").click()
        expect(usage).to_have_attribute("aria-busy", "true")
        expect(usage.locator(".panel").first).to_be_visible()
        held.go()
        expect(usage).not_to_have_attribute("aria-busy", "true")

"""`hmz web`'s page on one daemon at a time: the daemon is the first part of every address.

`#/@<name>/<view>` is a view of that daemon, and an address naming none is of Local. Whatever
the page asks of the daemon it is on goes under `/d/<name>/api/`, every link it draws keeps the
daemon its address named, and going to another daemon's address tells the page it switched.
Each in Chromium and in WebKit.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, go, opened, stop

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Page, Request, Route

pytestmark = pytest.mark.parametrize("engine", ENGINES)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, asked what it runs, and a project to serve."""
    return install(tmp_path, monkeypatch)


def _asked(page: Page) -> list[str]:
    """Every path of the API the page asks from here on, as it asks it."""
    paths: list[str] = []

    def heard(request: Request) -> None:
        path = urllib.parse.urlsplit(request.url).path
        # What is the same whichever daemon is shown is asked of the page's own server.
        if "/api/" in path and not re.match(r"/api/(daemons|notifications)\b", path):
            paths.append(path)

    page.on("request", heard)
    return paths


def _other(page: Page) -> None:
    """A daemon named `other`, which is Local answering under another name."""

    def answered(route: Route) -> None:
        route.continue_(url=route.request.url.replace("/d/other/api/", "/d/local/api/"))

    page.route(re.compile(r".*/d/other/api/.*"), answered)


def test_an_address_naming_local_draws_every_view_and_keeps_naming_it(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        asked = _asked(page)

        go(page, "/@local/new")
        expect(page.locator("[data-hmz=flow-picker] b")).to_have_text("chat")
        nav = page.locator(".side-nav a")
        expect(nav).to_have_count(3)
        for one in nav.all():
            expect(one).to_have_attribute("href", re.compile(r"^#/@local/"))
        expect(page.locator(".side-top .brand")).to_have_attribute(
            "href", "#/@local/new"
        )

        page.locator(".side-nav a[data-nav=flows]").click()
        expect(page.locator("[data-hmz=flows] .card").first).to_be_visible()
        assert page.evaluate("location.hash").startswith("#/@local/flows")

        go(page, "/@local/settings/general")
        dialog = page.locator("[data-hmz=dialog-settings]")
        expect(dialog).to_be_visible()
        expect(dialog.locator("nav a").first).to_have_attribute(
            "href", re.compile(r"^#/@local/settings/")
        )
        page.keyboard.press("Escape")
        expect(dialog).to_have_count(0)
        assert page.evaluate("location.hash").startswith("#/@local/flows")

        assert asked
        assert all(path.startswith("/d/local/api/") for path in asked), asked


def test_an_epic_started_on_a_daemon_stays_on_it(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        asked = _asked(page)
        go(page, "/@local/new?flow=chat")
        page.get_by_role("button", name="Options").click()
        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_value("claude-haiku-4-5")
        page.locator("[data-hmz=composer-text]").fill("hello there")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(re.compile(r".*#/@local/epics/[^/]+/sessions/[^/]+%2F1$"))
        expect(page.locator("[data-hmz=thread]")).to_contain_text("did: hello there")

        # The epic's stream, and its links, are the daemon's.
        assert any(path == "/d/local/api/held/stream" for path in asked), asked
        expect(page.locator("[data-hmz=epic]").first).to_have_attribute(
            "href", re.compile(r"^#/@local/epics/")
        )
        stop(page)


def test_another_daemon_is_switched_to_and_back(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _other(page)
        page.evaluate(
            """() => {
                window.switched = []
                addEventListener('hmz:daemon', (event) => switched.push(event.detail.daemon))
            }"""
        )
        asked = _asked(page)

        # The same daemon, named, is no switch.
        go(page, "/@local/new")
        assert page.evaluate("switched") == []

        go(page, "/@other/flows")
        assert page.evaluate("switched") == ["other"]
        expect(page.locator("[data-hmz=flows] .card").first).to_be_visible()
        expect(page.locator(".side-nav a[data-nav=new]")).to_have_attribute(
            "href", "#/@other/new"
        )
        expect(page.locator("[data-hmz=workspace]").first).to_be_visible()
        since = len(asked)
        page.locator(".side-nav a[data-nav=new]").click()
        expect(page.locator("[data-hmz=flow-picker] b")).to_have_text("chat")
        assert page.evaluate("location.hash").startswith("#/@other/new?")
        later = asked[since:]
        assert later
        assert all(path.startswith("/d/other/api/") for path in later), later

        go(page, "/new")
        assert page.evaluate("switched") == ["other", "local"]
        expect(page.locator(".side-nav a[data-nav=flows]")).to_have_attribute(
            "href", "#/flows"
        )

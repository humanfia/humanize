"""`hmz web`'s page on one daemon at a time: the daemon is the first part of every address.

`#/@<name>/<view>` is a view of that daemon, and an address naming none is of Local. Whatever
the page asks of the daemon it is on goes over that daemon's own session, every link it draws
keeps the daemon its address named, and going to another daemon's address tells the page it
switched. Each in Chromium and in WebKit.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, Wire, go, kept, opened, stop

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [
    pytest.mark.parametrize("engine", ENGINES),
    pytest.mark.usefixtures("daemon"),
]

#: A daemon named `other`, which is Local reached under another name, over `/rpc` too.
_OTHER = {"name": "other", "id": "", "routes": ["unix:"]}


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, asked what it runs, and a project to serve."""
    project = install(tmp_path, monkeypatch)
    # The home it gives the CLI is this machine's home, which the daemon's own settings are of.
    (tmp_path / "home").mkdir(exist_ok=True)
    return project


def test_an_address_naming_local_draws_every_view_and_keeps_naming_it(
    project: Path, engine: str
) -> None:
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, "/@local/new")
        expect(page.locator("[data-hmz=flow-picker] b")).to_be_visible()
        nav = page.locator(".side-nav a")
        expect(page.locator(".side-nav a > span:not(.side-badge)")).to_have_text(
            ["New chat", "New epic", "Search", "Flows"]
        )
        for one in nav.all():
            expect(one).to_have_attribute("href", re.compile(r"^#/@local/"))
        # The mark and the first entry open a new chat, the second a new epic.
        expect(page.locator(".side-top .brand")).to_have_attribute(
            "href", "#/@local/new/chat"
        )
        expect(nav.nth(0)).to_have_attribute("href", "#/@local/new/chat")
        expect(nav.nth(1)).to_have_attribute("href", "#/@local/new")
        expect(nav.nth(1)).to_have_attribute("aria-current", "page")

        # A new chat from the first entry, from its keys and from the mark, each its own entry.
        nav.nth(0).click()
        expect(page.locator(".view[data-hmz=new-chat]")).to_be_visible()
        assert page.evaluate("location.hash").startswith("#/@local/new/chat")
        expect(nav.nth(0)).to_have_attribute("aria-current", "page")
        expect(nav.nth(1)).not_to_have_attribute("aria-current", "page")

        page.locator(".side-nav a[data-nav=flows]").click()
        expect(page.locator("[data-hmz=flows] .card").first).to_be_visible()
        assert page.evaluate("location.hash").startswith("#/@local/flows")
        page.keyboard.press("Control+Shift+O")
        expect(page.locator(".view[data-hmz=new-chat]")).to_be_visible()
        assert page.evaluate("location.hash").startswith("#/@local/new/chat")
        page.locator(".side-nav a[data-nav=flows]").click()
        expect(page.locator("[data-hmz=flows] .card").first).to_be_visible()
        page.locator(".side-top .brand").click()
        expect(page.locator(".view[data-hmz=new-chat]")).to_be_visible()
        page.locator(".side-nav a[data-nav=flows]").click()
        expect(page.locator("[data-hmz=flows] .card").first).to_be_visible()

        go(page, "/@local/settings/general")
        dialog = page.locator("[data-hmz=dialog-settings]")
        expect(dialog).to_be_visible()
        expect(dialog.locator("nav a").first).to_have_attribute(
            "href", re.compile(r"^#/@local/settings/")
        )
        page.keyboard.press("Escape")
        expect(dialog).to_have_count(0)
        assert page.evaluate("location.hash").startswith("#/@local/flows")

        # Asked of Local, over its one session.
        assert "flows.list" in [method for method, _ in wire.calls]
        assert set(wire.over) == {1}, wire.over


def test_an_epic_started_on_a_daemon_stays_on_it(project: Path, engine: str) -> None:
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, "/@local/new/chat")
        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_attribute("data-value", "claude-haiku-4-5")
        page.locator("[data-hmz=composer-text]").fill("hello there")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(re.compile(r".*#/@local/epics/[^/]+/sessions/[^/]+%2F1$"))
        expect(page.locator("[data-hmz=thread]")).to_contain_text("did: hello there")

        # The epic followed, and its links, are the daemon's.
        assert [one for one in wire.params("epic.attach") if one.get("figures")]
        expect(page.locator("[data-hmz=epic]").first).to_have_attribute(
            "href", re.compile(r"^#/@local/epics/")
        )
        stop(page)


def test_another_daemon_is_switched_to_and_back(project: Path, engine: str) -> None:
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        kept(page, _OTHER)
        # A workspace `other` knows of its own, as `hmz web` started there would offer it.
        page.evaluate(
            """async (at) => (await import('/api.js')).call(
                'workspaces.add', { workspace: at }, { on: 'other' })""",
            str(project),
        )
        page.evaluate(
            """() => {
                window.switched = []
                addEventListener('hmz:daemon', (event) => switched.push(event.detail.daemon))
            }"""
        )

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
        since = len(wire.calls)
        page.locator(".side-nav a[data-nav=new]").click()
        expect(page.locator("[data-hmz=flow-picker] b")).to_be_visible()
        assert page.evaluate("location.hash").startswith("#/@other/new?")
        # Asked of `other` over a session of its own, not over Local's.
        local = wire.over[0]
        later = [
            on
            for (method, _), on in zip(
                wire.calls[since:], wire.over[since:], strict=True
            )
            if method == "flows.list"
        ]
        assert later
        assert local not in later, wire.over

        go(page, "/new")
        assert page.evaluate("switched") == ["other", "local"]
        expect(page.locator(".side-nav a[data-nav=flows]")).to_have_attribute(
            "href", "#/flows"
        )

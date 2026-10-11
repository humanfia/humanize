"""`hmz web`'s page as a desktop app is used: right-clicked, hovered, and filled in by picking.

A right click opens what can be done to the thing under it and never the browser's own menu,
save where there is text to read or write; what is cut short says itself in full on hover; and
a path or an agent is picked a step at a time rather than spelled. Each in Chromium and WebKit.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import ENGINES, Browser, opened, served

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Locator, Page

pytestmark = pytest.mark.parametrize("engine", ENGINES)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, a home of its own with folders in it, a project."""
    at = install(tmp_path, monkeypatch)
    home = tmp_path / "home"
    (home / "work" / "app").mkdir(parents=True)
    (home / ".ssh").mkdir()
    (home / ".ssh" / "id_ed25519").write_text("not a key\n")
    return at


def _go(page: Page, address: str) -> None:
    page.evaluate("(to) => { location.hash = to }", address)


def _menu(page: Page, target: Locator) -> Locator:
    """Right-clicks something, and answers the menu it opened."""
    target.click(button="right")
    menu = page.locator(".popover.context")
    expect(menu).to_be_visible()
    return menu


def _prevented(page: Page, selector: str) -> bool:
    """Whether a right click there is kept from opening the browser's own menu."""
    return bool(
        page.evaluate(
            """(selector) => {
                const at = document.querySelector(selector)
                const event = new MouseEvent('contextmenu', {bubbles: true, cancelable: true})
                at.dispatchEvent(event)
                document.querySelector('.popover.context')?.remove()
                return event.defaultPrevented
            }""",
            selector,
        )
    )


def test_a_workdir_says_its_whole_path_on_hover_and_offers_it_on_a_right_click(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        folder = page.locator(f"[data-hmz=workspace][data-path='{project.resolve()}']")
        folder.locator(".side-folder-name").hover()
        expect(page.locator(".tip")).to_have_text(str(project.resolve()))

        menu = _menu(page, folder.locator(".side-folder"))
        expect(menu.locator(".context-head")).to_have_text(str(project.resolve()))
        expect(menu.locator(".choice-label")).to_contain_text(
            ["New epic here", "Flows here", "Search here", "Copy path", "Collapse"]
        )
        menu.get_by_role("menuitem", name="New epic here").click()
        expect(page.locator(".popover.context")).to_have_count(0)
        expect(page.locator("[data-hmz=workspace-picker] b")).to_have_text(project.name)


def test_the_page_keeps_the_browsers_menu_to_what_is_there_to_read_or_write(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _go(page, "/new?flow=chat")
        expect(page.locator("[data-hmz=composer-text]")).to_be_visible()
        assert _prevented(page, "[data-hmz=sidebar] .brand")
        assert _prevented(page, ".greeting")
        assert not _prevented(page, "[data-hmz=composer-text]")
        user_select = page.evaluate(
            "(() => { const said = getComputedStyle(document.querySelector('.side-nav a'));"
            " return said.webkitUserSelect || said.userSelect })()"
        )
        assert user_select == "none"


def test_a_folder_is_browsed_for_a_step_at_a_time(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _go(page, "/new?flow=chat")
        page.locator("[data-hmz=workspace-picker]").click()
        page.get_by_role("menuitem", name="Open folder…").click()
        page.locator("[data-hmz=path-browse]").click()
        panel = page.locator("[data-hmz=path-panel]")
        expect(panel.locator(".crumb").last).to_have_text("~")
        panel.locator(".path-entry", has_text="work").click()
        expect(panel.locator(".crumb").last).to_have_text("work")
        panel.locator(".path-entry", has_text="app").click()
        expect(panel.locator(".crumb").last).to_have_text("app")
        panel.locator("[data-hmz=path-choose]").click()
        expect(page.locator("[data-hmz=workspace-path]")).to_have_value("~/work/app")
        page.get_by_role("button", name="Open", exact=True).click()
        expect(page.locator("[data-hmz=workspace-picker] b")).to_have_text("app")


def test_a_runtime_is_set_up_field_by_field(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _go(page, "/settings/runtimes")
        # Read whole -- what is saved and what the SSH config names -- before anything is typed.
        expect(page.locator("[data-hmz=import-runtimes] button")).to_be_visible()
        page.locator("#runtime-name").fill("box")
        page.locator("#runtime-host").fill("box.example")
        page.get_by_role("button", name="Browse for Identity file").click()
        panel = page.locator("[data-hmz=path-panel]")
        panel.get_by_label("Hidden").check()
        panel.locator(".path-entry", has_text=".ssh").click()
        expect(panel.locator(".crumb").last).to_have_text(".ssh")
        panel.locator(".path-entry", has_text="id_ed25519").click()
        expect(page.locator("#runtime-identity_file")).to_have_value(
            "~/.ssh/id_ed25519"
        )
        options = page.locator("#runtime-options").locator("xpath=..")
        options.get_by_role("button", name="Add").click()
        options.get_by_label("Name").fill("ServerAliveInterval")
        options.get_by_label("Value").fill("30")
        affinity = page.locator("#runtime-affinity").locator("xpath=..")
        affinity.get_by_role("button", name="Add").click()
        expect(affinity.get_by_label("Value").locator("option")).to_have_text(
            ["self", "local"]
        )
        affinity.get_by_label("Value").select_option("local")
        page.locator("[data-hmz=write-runtime] .row > .confirm > .btn.primary").click()
        listed = page.locator("[data-hmz=runtime]")
        refused = page.locator("[data-hmz=write-runtime] .error")
        expect(listed.or_(refused)).to_be_visible()
        assert not refused.count(), refused.inner_text()
        expect(listed).to_have_count(1)

        browser = Browser(site)
        browser.signs_in()
        (saved,) = browser.get("/api/runtimes").json()["runtimes"]
        assert saved["identity_file"] == "~/.ssh/id_ed25519"
        assert saved["options"] == {"ServerAliveInterval": "30"}
        assert saved["affinity"] == ["local"]


def test_a_fallback_and_the_btw_agent_are_picked_not_spelled(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _go(page, "/settings/fallback")
        place = page.locator("[data-hmz=fallback-spec]")
        expect(place.locator("[data-hmz=pick-model] option").first).to_have_text(
            "claude-haiku-4-5"
        )
        place.locator("[data-hmz=pick-model]").select_option("claude-opus-4-1")
        then = page.locator("[data-hmz=fallback-place]").first
        expect(then.locator("[data-hmz=pick-model]")).to_have_value("claude-haiku-4-5")
        page.get_by_role("button", name="Save").click()
        expect(page.locator("[data-hmz=step]")).to_have_count(1)

        _go(page, "/settings/general")
        page.locator("[data-hmz=btw-whom]").select_option("chosen")
        agent = page.locator("[data-hmz=btw-agent]")
        expect(agent.locator("[data-hmz=pick-model] option").first).to_have_text(
            "claude-haiku-4-5"
        )
        agent.locator("[data-hmz=pick-effort]").select_option("high")
        page.get_by_role("button", name="Save").click()
        expect(page.get_by_role("button", name="Saved")).to_be_visible()

        browser = Browser(site)
        browser.signs_in()
        (step,) = browser.get("/api/fallbacks").json()["steps"]
        assert (step["spec"], step["to"]) == (
            "claude/claude-opus-4-1",
            ["claude/claude-haiku-4-5"],
        )
        assert (
            browser.get("/api/settings").json()["btw"] == "claude/claude-haiku-4-5:high"
        )


def test_settings_fit_a_phone(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine, width=390, height=844) as page:
        for one in ("general", "runtimes", "workspace", "usage"):
            _go(page, f"/settings/{one}")
            expect(page.locator(f"[data-hmz=settings-{one}]")).to_be_visible()
            wide = page.evaluate("document.querySelector('.dialog').scrollWidth")
            assert wide <= 390, f"{one} is {wide} wide"
            assert re.match(r"\d", str(wide))

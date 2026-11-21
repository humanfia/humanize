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
from tests.integration.doubles_web import Browser, served
from tests.system.web.doubles_browser import ENGINES, go, opened

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Locator, Page

pytestmark = [
    pytest.mark.parametrize("engine", ENGINES),
    pytest.mark.usefixtures("daemon"),
]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, a home of its own with folders in it, a project."""
    at = install(tmp_path, monkeypatch)
    home = tmp_path / "home"
    (home / "work" / "app").mkdir(parents=True)
    (home / ".ssh").mkdir()
    (home / ".ssh" / "id_ed25519").write_text("not a key\n")
    return at


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
            [
                "New chat here",
                "New epic here",
                "Search here",
                "Copy path",
                "Collapse",
            ]
        )
        menu.get_by_role("menuitem", name="New epic here").click()
        expect(page.locator(".popover.context")).to_have_count(0)
        expect(page.locator("[data-hmz=workspace-picker] b")).to_have_text(project.name)


def test_the_page_keeps_the_browsers_menu_to_what_is_there_to_read_or_write(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new?flow=chat")
        expect(page.locator("[data-hmz=composer-text]")).to_be_visible()
        assert _prevented(page, "[data-hmz=sidebar] .brand")
        assert _prevented(page, "[data-hmz=bar] h1")
        assert not _prevented(page, "[data-hmz=composer-text]")
        user_select = page.evaluate(
            "(() => { const said = getComputedStyle(document.querySelector('.side-nav a'));"
            " return said.webkitUserSelect || said.userSelect })()"
        )
        assert user_select == "none"


def test_a_folder_is_browsed_for_a_step_at_a_time(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new?flow=chat")
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
        go(page, "/settings/runtimes")
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
        harness = page.locator("#runtime-harness")
        expect(harness.locator("option")).to_have_text(
            ["Inside the environment", "This machine"]
        )
        expect(harness).to_have_value("env")
        harness.select_option("local")
        page.locator("[data-hmz=write-runtime] .row > .confirm > .btn.primary").click()
        listed = page.locator("[data-hmz=runtime]")
        refused = page.locator("[data-hmz=write-runtime] .error")
        expect(listed.or_(refused)).to_be_visible()
        assert not refused.count(), refused.inner_text()
        expect(listed).to_have_count(1)

        browser = Browser(site)
        browser.signs_in()
        with browser.session() as asked:
            (saved,) = asked.call("runtimes.list")["runtimes"]
        assert saved["identity_file"] == "~/.ssh/id_ed25519"
        assert saved["options"] == {"ServerAliveInterval": "30"}
        assert saved["harness"] == "local"


def test_a_nous_is_picked_not_spelled(project: Path, engine: str) -> None:
    """Sections 3.11.2.6 and 3.8.19.1 of protocol/web.md: found, and picked by levels."""
    with served() as site, opened(site, engine=engine) as page:
        # What a backend runs is asked as a new chat offers it, and offered here once it said.
        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_attribute("data-value", "claude-haiku-4-5")
        go(page, "/settings/nous")
        listing = page.locator("[data-hmz=nous]")
        # Every concrete nous found is listed under its harness, though nothing is written of
        # any: the page never says that there is no nous, and none is made by hand.
        found = listing.locator("[data-hmz=nous-harness][data-cli=claude]")
        expect(found.locator("summary")).to_contain_text("Claude Code")
        rows = found.locator("[data-hmz=concrete-row]")
        expect(rows.first).to_be_visible()
        assert rows.count() > 1
        expect(listing.locator("[data-hmz=nous-scanned]")).to_have_text(
            re.compile(r"^\d+ concrete nous of \d+ harnesses\.$")
        )
        expect(listing.locator("[data-hmz=nous-no-virtual]")).to_contain_text(
            "None yet."
        )
        expect(listing.locator(".empty")).to_have_count(0)
        expect(page.locator("#nous-kind, [data-hmz=nous-spec]")).to_have_count(0)
        expect(page.locator("[data-hmz=write-nous] h2")).to_have_text(
            "New virtual nous"
        )

        # A wait is named shortly in its select, and explained beside it.
        policy = page.locator("[data-hmz=nous-policy]")
        said = policy.locator("option").all_inner_texts()
        assert said[:2] == ["No wait", "Constant"]
        assert not any("—" in one or ":" in one for one in said)
        about = page.locator("[data-hmz=policy-about]")
        expect(about).to_contain_text("for agents that fail at the same moment")
        policy.select_option("fibonacci")
        expect(about).to_have_text("The Fibonacci sequence: 1s, 1s, 2s, 3s, 5s.")

        # A scan asks the harnesses again, and says what there is once it has.
        scan = listing.locator("[data-hmz=nous-scan]")
        scan.click()
        expect(scan).to_have_text("Scan")
        expect(scan).to_be_enabled()
        expect(listing.locator("[data-hmz=nous-scan-failed]")).to_have_count(0)

        # What is written of a concrete nous is edited from its row; its `then` names a nous
        # picked a level at a time, on the first there is until another is.
        opus = rows.and_(page.locator("[data-name='claude/claude-opus-4-1']"))
        opus.get_by_role("button", name="Edit").click()
        then = page.locator("[data-hmz=nous-then]")
        then.locator("[data-hmz=graph-add-use]").click()
        chip = then.locator("[data-hmz=graph-nous] [data-hmz=pick-model]")
        chip.click()
        menu = then.locator("[role=menu]")
        # A row a level, each saying what is picked at it: one account alone is no level.
        expect(menu.locator(".choice.step .choice-label")).to_have_text(
            ["Harness", "Model", "Effort"]
        )
        menu.locator("[data-hmz=step-model]").click()
        expect(menu.locator("[data-hmz=step-back]")).to_have_text("Model")
        menu.locator(".nous-list [data-value=claude-haiku-4-5]").click()
        expect(menu).to_have_count(0)
        expect(chip).to_have_attribute("data-agent", "claude/claude-haiku-4-5")
        page.get_by_role("button", name="Save").click()
        expect(opus.get_by_role("button", name="Reset")).to_be_visible()

        # A virtual nous is made by its name, and is then offered first wherever one is picked.
        listing.locator("[data-hmz=nous-add]").click()
        expect(page.locator("#nous-name")).to_be_focused()
        page.locator("#nous-name").fill("careful")
        graph = page.locator("[data-hmz=nous-graph]")
        graph.locator("[data-hmz=graph-add-use]").click()
        page.get_by_role("button", name="Save").click()
        expect(listing.locator("[data-hmz=nous-row]")).to_have_count(1)
        expect(listing.locator("[data-hmz=nous-row]")).to_have_attribute(
            "data-name", "careful"
        )
        go(page, "/new/chat")
        picker = page.locator("[data-role=assistant] [data-hmz=pick-model]")
        picker.click()
        virtual = page.locator("[role=menu] [data-hmz=pick-virtual]")
        expect(virtual).to_have_text(["careful"])
        virtual.click()
        expect(picker).to_have_text("careful")
        page.keyboard.press("Escape")

        # Ai-chan's is no setting: it is picked on the chip of her box (test_web_aichan.py).
        go(page, "/settings/general")
        expect(page.locator("[data-hmz=harness-sessions]")).to_be_visible()
        expect(page.locator("[data-hmz=ai-chan-setting]")).to_have_count(0)

        browser = Browser(site)
        browser.signs_in()
        with browser.session() as asked:
            nous, careful = asked.call("nous.list")["nous"]
        assert nous["name"] == "claude/claude-opus-4-1"
        assert [one["use"] for one in nous["then"]["nodes"]] == [
            "claude/claude-haiku-4-5"
        ]
        assert (careful["name"], careful["virtual"]) == ("careful", True)
        assert [one["use"] for one in careful["graph"]["nodes"]] == [
            "claude/claude-haiku-4-5"
        ]


def test_settings_fit_a_phone(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine, width=390, height=844) as page:
        for one in ("general", "runtimes", "usage"):
            go(page, f"/settings/{one}")
            expect(page.locator(f"[data-hmz=settings-{one}]")).to_be_visible()
            wide = page.evaluate("document.querySelector('.dialog').scrollWidth")
            assert wide <= 390, f"{one} is {wide} wide"
            assert re.match(r"\d", str(wide))
        # And so do a folder's own settings, which fill the window as Settings does.
        for one in ("setup", "usage", "archived"):
            go(page, f"/workspace/{one}?workspace={project}")
            expect(page.locator(f"[data-hmz=workspace-{one}]")).to_be_visible()
            wide = page.evaluate("document.querySelector('.dialog').scrollWidth")
            assert wide <= 390, f"{one} is {wide} wide"
            box = page.locator("[data-hmz=workspace-of]").bounding_box()
            assert box
            assert box["x"] >= 0
            assert box["x"] + box["width"] <= 390


def _whole(page: Page, popup: Locator) -> None:
    """Asserts a popup is drawn whole within the window: no edge of it past the window's."""
    box = popup.bounding_box()
    assert box is not None
    size = page.viewport_size
    assert size is not None
    assert box["x"] >= 0, box
    assert box["y"] >= 0, box
    assert box["x"] + box["width"] <= size["width"], (box, size)
    assert box["y"] + box["height"] <= size["height"], (box, size)


def test_every_popup_opens_whole_within_the_window(project: Path, engine: str) -> None:
    """A menu opens on the side of its button there is room on, however far down a list it is."""
    with served() as site, opened(site, engine=engine, width=900, height=420) as page:
        # The daemon picker, at the foot of the window: over its button, as wide as it.
        page.locator("[data-hmz=daemon-bar]").click()
        _whole(page, page.get_by_role("menu", name="Daemon"))
        page.keyboard.press("Escape")

        # A path browsed for from the folder a new epic opens, in a window too short for it.
        go(page, "/new?flow=chat")
        page.locator("[data-hmz=workspace-picker]").click()
        _whole(page, page.get_by_role("menu", name="Folders"))
        page.get_by_role("menuitem", name="Open folder…").click()
        _whole(page, page.locator(".workdir-open"))
        page.locator("[data-hmz=path-browse]").click()
        panel = page.locator("[data-hmz=path-panel]")
        expect(panel.locator(".crumb").last).to_have_text("~")
        _whole(page, panel)

        # What a right click opens, at the window's foot.
        go(page, "/settings/themes")
        row = page.locator("[data-hmz=theme]").last
        row.scroll_into_view_if_needed()
        row.click(button="right", position={"x": 300, "y": 20})
        _whole(page, page.locator(".popover.context"))


def _popups(page: Page) -> list[str]:
    """What is open over the page: every popup drawn, by its label or its class."""
    return page.evaluate(
        """() => [...document.querySelectorAll('.popover, [role=menu], [role=tooltip]')]
            .filter((one) => one.getClientRects().length)
            .filter((one) => getComputedStyle(one).visibility !== 'hidden')
            .map((one) => one.getAttribute('aria-label') || one.className)"""
    )


def _flat(page: Page) -> bool:
    """Whether nothing open over the page casts a shadow: a popup is edged by a hairline."""
    return page.evaluate(
        """() => [...document.querySelectorAll('.popover, [role=menu], .dialog, .toast')]
            .filter((one) => one.getClientRects().length)
            .every((one) => getComputedStyle(one).boxShadow === 'none')"""
    )


def test_one_popup_is_open_at_a_time_and_goes_with_what_it_was_opened_on(
    project: Path, engine: str
) -> None:
    """Opening one popup closes the others; a press outside, Escape or leaving closes it."""
    with served() as site, opened(site, engine=engine, width=1296, height=792) as page:
        # A new epic keeps the flow and the folder a control each.
        go(page, "/new")
        folders = page.locator("[data-hmz=workspace-picker]")
        where = page.locator("[data-hmz=flow-picker]")
        folders.click()
        expect(page.get_by_role("menu", name="Folders")).to_be_visible()
        assert _popups(page) == ["Folders"]
        assert _flat(page)

        # A press on another's button is not swallowed: one click closes this and opens that.
        where.click()
        expect(page.get_by_role("menu", name="Folders")).to_have_count(0)
        expect(where).to_have_attribute("aria-expanded", "true")
        expect(folders).to_have_attribute("aria-expanded", "false")
        assert len(_popups(page)) == 1
        # Its own button pressed again closes it.
        where.click()
        expect(where).to_have_attribute("aria-expanded", "false")
        assert _popups(page) == []

        # The form a folder is opened by, and the panel it is browsed for in, are one chain:
        # Escape closes the topmost alone, and a menu opened elsewhere closes the whole of it.
        folders.click()
        page.get_by_role("menuitem", name="Open folder…").click()
        form = page.locator(".workdir-open")
        expect(form).to_be_visible()
        expect(page.get_by_role("menu", name="Folders")).to_have_count(0)
        page.locator("[data-hmz=path-browse]").click()
        panel = page.locator("[data-hmz=path-panel]")
        expect(panel).to_be_visible()
        assert _flat(page)
        page.keyboard.press("Escape")
        expect(panel).to_be_hidden()
        expect(form).to_be_visible()
        where.click()
        expect(form).to_be_hidden()
        expect(where).to_have_attribute("aria-expanded", "true")
        assert len(_popups(page)) == 1
        page.keyboard.press("Escape")
        assert _popups(page) == []

        # A press on nothing closes it, and so does going elsewhere: nothing is left over
        # the dialog the page goes to.
        folders.click()
        page.get_by_role("menuitem", name="Open folder…").click()
        expect(form).to_be_visible()
        page.mouse.click(1000, 600)
        expect(form).to_be_hidden()
        folders.click()
        page.get_by_role("menuitem", name="Open folder…").click()
        expect(form).to_be_visible()
        page.locator("[data-hmz=path-browse]").click()
        expect(panel).to_be_visible()
        go(page, "/settings/themes")
        expect(page.locator("[data-hmz=theme]").first).to_be_visible()
        assert _popups(page) == []
        assert _flat(page)

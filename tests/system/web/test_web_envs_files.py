"""An environment's Files panel, driven in a real browser over an environment held in the page.

The panel is mounted by itself, as the environments frame mounts it, on a stand-in `ctx` that
answers the `env.*` files methods from files held in memory. Its editor is CodeMirror, which the
page imports from `/vendor/codemirror.js`, the bundle the package ships.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, opened

if TYPE_CHECKING:
    from playwright.sync_api import Page

pytestmark = pytest.mark.parametrize("engine", ENGINES)

#: The stand-in `ctx`: an environment of a few files, each call kept in `window.fake.calls`.
_MOUNT = (Path(__file__).parent / "envs_files_ctx.js").read_text()


def _mounted(page: Page) -> None:
    page.evaluate(_MOUNT)
    expect(
        page.locator("[data-hmz=files-tree] [data-path='/w/main.py']")
    ).to_be_visible()


def _calls(page: Page, method: str) -> list[dict[str, Any]]:
    return [
        params
        for called, params in page.evaluate("window.fake.calls")
        if called == method
    ]


def test_a_file_is_opened_edited_and_saved_and_a_conflict_offered(engine: str) -> None:

    with served() as site, opened(site, engine=engine) as page:
        _mounted(page)

        # Opened from the explorer: a preview tab, highlighted as Python.
        page.locator("[data-hmz=files-tree] [data-path='/w/main.py']").click()
        tab = page.locator("[data-hmz=files-tab][data-path='/w/main.py']")
        expect(tab).to_have_class(re.compile("preview"))
        content = page.locator("[data-hmz=files-editor] .cm-content")
        expect(content).to_contain_text("def greet(name):")
        expect(page.locator("[data-hmz=files-language]")).to_have_text("Python")
        assert page.locator("[data-hmz=files-editor] .cm-line span").count() > 0

        # Edited: the tab is pinned, and written back a moment after the typing stops.
        page.locator("[data-hmz=files-editor] .cm-line").first.click()
        page.keyboard.press("Home")
        page.keyboard.type("# hello\n")
        expect(tab).not_to_have_class(re.compile("preview"))
        expect(page.locator("[data-hmz=files-saved]")).to_have_text("Saved")
        writes = _calls(page, "env.write")
        assert len(writes) == 1
        assert writes[0]["if_match"] == "e1"
        assert page.evaluate("window.fake.text('/w/main.py')").startswith(
            "# hello\ndef greet"
        )

        # Changed elsewhere, then edited here: the write is refused, and a banner offers
        # what to do.
        page.evaluate("window.fake.put('/w/main.py', 'theirs\\n')")
        content.click()
        page.keyboard.type("more ")
        banner = page.locator("[data-hmz=files-conflict]")
        expect(banner).to_be_visible()
        expect(tab).to_have_class(re.compile("conflict"))
        banner.locator("[data-hmz=files-compare]").click()
        expect(page.locator("[data-hmz=files-merge] .cm-mergeView")).to_be_visible()
        banner.locator("[data-hmz=files-reload]").click()
        expect(banner).to_have_count(0)
        expect(content).to_have_text("theirs")

        # Quick open closes by Escape from wherever the focus is and by a press outside
        # it, and takes the keys from a name being typed in the tree.
        page.locator("[data-hmz=files-editor] .cm-content").click()
        page.keyboard.press("Control+p")
        quick = page.locator("[data-hmz=files-quick-input]")
        expect(quick).to_be_focused()
        page.keyboard.press("Escape")
        expect(quick).to_be_hidden()
        expect(page.locator("[data-hmz=files-editor] .cm-content")).to_be_focused()
        page.locator("[data-hmz=files-new-file]").click()
        expect(page.locator("[data-hmz=files-name]")).to_be_focused()
        page.keyboard.press("Control+p")
        expect(quick).to_be_focused()
        page.locator("[data-hmz=files-editor] .cm-content").click()
        expect(quick).to_be_hidden()

        # Quick open, by a few letters of the name.
        page.keyboard.press("Control+p")
        expect(quick).to_be_focused()
        quick.fill("utl")
        expect(page.locator("[data-hmz=files-pick]").first).to_have_attribute(
            "data-path", "src/util.py"
        )
        expect(page.locator("[data-hmz=files-pick] mark").first).to_have_text("ut")
        quick.press("Enter")
        expect(page.locator("[data-hmz=files-tab].active")).to_have_attribute(
            "data-path", "/w/src/util.py"
        )
        expect(content).to_contain_text("def here():")

        # Searched: a result opens its file on its line, from another file.
        page.locator("[data-hmz=files-tab][data-path='/w/main.py']").click()
        page.locator("[data-hmz=files-side-search]").click()
        page.locator("[data-hmz=files-search-query]").fill("os")
        page.locator("[data-hmz=files-search-query]").press("Enter")
        expect(page.locator("[data-hmz=files-search-summary]")).to_have_text(
            re.compile("2 results in 1 file")
        )
        page.locator("[data-hmz=files-result][data-line='5']").click()
        expect(page.locator("[data-hmz=files-tab].active")).to_have_attribute(
            "data-path", "/w/src/util.py"
        )
        expect(page.locator("[data-hmz=files-position]")).to_have_text(
            re.compile(r"^Ln 5, Col 12")
        )
        # Flat: nothing drawn here, the editor included, casts a shadow.
        assert (
            page.evaluate(
                """() => [...document.querySelectorAll('*')]
                  .filter((el) => getComputedStyle(el).boxShadow !== 'none')
                  .map((el) => `${el.tagName}.${el.className}`)"""
            )
            == []
        )
        page.screenshot(path=str(_shots() / f"envs_files_{engine}.png"))


def test_a_tab_is_dragged_along_the_strip_by_the_pointer(engine: str) -> None:

    with served() as site, opened(site, engine=engine) as page:
        _mounted(page)
        tabs = page.locator("[data-hmz=files-tab]")
        for name in ("main.py", "README.md"):
            page.locator(f"[data-hmz=files-tree] [data-path='/w/{name}']").click()
            page.locator(f"[data-hmz=files-tab][data-path='/w/{name}']").dblclick()
        expect(tabs).to_have_count(2)

        def order() -> list[str | None]:
            return [tab.get_attribute("data-path") for tab in tabs.all()]

        assert order() == ["/w/main.py", "/w/README.md"]

        # Pressed, moved past the middle of the next tab and let go: it stands after it. Only
        # the pointer is asked, never the browser's drag and drop, which the app's window keeps.
        first = tabs.nth(0).bounding_box()
        second = tabs.nth(1).bounding_box()
        assert first is not None
        assert second is not None
        height = first["y"] + first["height"] / 2
        page.mouse.move(first["x"] + 20, height)
        page.mouse.down()
        page.mouse.move(second["x"] + second["width"] - 4, height, steps=5)
        expect(tabs.nth(0)).to_have_class(re.compile("dragging"))
        page.mouse.up()
        assert order() == ["/w/README.md", "/w/main.py"]
        expect(page.locator("[data-hmz=files-tab].dragging")).to_have_count(0)

        # A press that goes nowhere is still a click, on the tab and on its close button.
        tabs.nth(0).click()
        expect(page.locator("[data-hmz=files-tab].active")).to_have_attribute(
            "data-path", "/w/README.md"
        )
        tabs.nth(0).hover()
        tabs.nth(0).locator("[data-hmz=files-tab-close]").click()
        assert order() == ["/w/main.py"]


def test_the_explorer_makes_renames_and_removes_files(engine: str) -> None:

    with served() as site, opened(site, engine=engine) as page:
        _mounted(page)
        tree = page.locator("[data-hmz=files-tree]")

        # A new file, named in the tree, made only where there is none, and opened.
        page.locator("[data-hmz=files-new-file]").click()
        # Named once it is focused, its name picked out for typing over.
        expect(page.locator("[data-hmz=files-name]")).to_be_focused()
        page.locator("[data-hmz=files-name]").fill("notes.txt")
        page.locator("[data-hmz=files-name]").press("Enter")
        expect(tree.locator("[data-path='/w/notes.txt']")).to_be_visible()
        assert _calls(page, "env.write")[0] == {
            "path": "/w/notes.txt",
            "data": "",
            "if_match": "",
        }
        expect(page.locator("[data-hmz=files-tab].active")).to_have_attribute(
            "data-path", "/w/notes.txt"
        )

        # Renamed with F2: its tab follows.
        tree.locator("[data-path='/w/notes.txt']").click()
        tree.press("F2")
        # Named once it is focused, its name picked out for typing over.
        expect(page.locator("[data-hmz=files-name]")).to_be_focused()
        page.locator("[data-hmz=files-name]").fill("todo.txt")
        page.locator("[data-hmz=files-name]").press("Enter")
        expect(tree.locator("[data-path='/w/todo.txt']")).to_be_visible()
        expect(page.locator("[data-hmz=files-tab].active")).to_have_attribute(
            "data-path", "/w/todo.txt"
        )

        # Deleted with the Delete key: its tab closes.
        tree.locator("[data-path='/w/todo.txt']").click()
        tree.press("Delete")
        expect(tree.locator("[data-path='/w/todo.txt']")).to_have_count(0)
        expect(page.locator("[data-hmz=files-tab]")).to_have_count(0)

        # A binary file opens read-only, saying why.
        tree.locator("[data-path='/w/blob.bin']").click()
        expect(page.locator("[data-hmz=files-read-only]")).to_contain_text(
            "not UTF-8 text"
        )
        expect(page.locator("[data-hmz=files-saved]")).to_have_text("Read-only")

        # A folder opens and closes with the arrow keys.
        tree.locator("[data-path='/w/src']").click()
        expect(tree.locator("[data-path='/w/src/util.py']")).to_be_visible()
        tree.press("ArrowLeft")
        expect(tree.locator("[data-path='/w/src/util.py']")).to_have_count(0)
        tree.press("ArrowRight")
        expect(tree.locator("[data-path='/w/src/util.py']")).to_be_visible()

        # The menu key opens the menu of the entry the keys are on; shut, the tree has them back.
        tree.press("ContextMenu")
        expect(page.get_by_role("menuitem", name="New file…")).to_be_focused()
        expect(page.get_by_role("menu").locator(".popover-head")).to_have_text("src")
        # A right click on another entry while it is open leaves one menu, that entry's.
        # (Pressed past the menu's right edge: the menu lies over the middle of the row.)
        tree.locator("[data-path='/w/blob.bin']").click(
            button="right", position={"x": 230, "y": 11}
        )
        expect(page.get_by_role("menu")).to_have_count(1)
        expect(page.get_by_role("menu").locator(".popover-head")).to_have_text(
            "blob.bin"
        )
        page.keyboard.press("Escape")
        expect(page.get_by_role("menu")).to_have_count(0)
        expect(tree).to_be_focused()

        # The line beside the explorer sizes it, by the keys too, as wide as it was last left.
        split = page.locator("[data-hmz=files-split]")
        before = int(split.get_attribute("aria-valuenow") or 0)
        split.focus()
        page.keyboard.press("ArrowRight")
        expect(split).to_have_attribute("aria-valuenow", str(before + 16))
        assert page.evaluate("localStorage.getItem('hmz-files-side')") == str(
            before + 16
        )


def _shots() -> Path:
    """Where a screenshot is left to be looked at: `HMZ_SHOTS`, else a temporary directory."""
    where = Path(
        os.environ.get("HMZ_SHOTS") or Path(tempfile.gettempdir()) / "hmz-shots"
    )
    where.mkdir(parents=True, exist_ok=True)
    return where

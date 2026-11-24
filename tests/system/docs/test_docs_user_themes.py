"""The pictures of `docs/user/themes.md`: how the page looks, and what it is written in.

The Themes settings and a preset chosen with its dark side, a theme of the person's own in
its editor, the page turned to Chinese, and the terminal interface in the terminal's colours
and in a theme of Textual's. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_themes.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.integration.doubles_tui import shows
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    import pytest
    from playwright.sync_api import Locator, Page

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-themes"

_TASK = "Add a discount code to checkout"

_ANSWER = (
    "Checkout takes a discount code now: charge() looks the code up and takes its"
    " discount off the total. WELCOME10 is 10% off."
)

#: A small picture to lay behind the page: dots, tiled.
_DOTS = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28">'
    '<circle cx="14" cy="14" r="1.6" fill="#7aa2c8" fill-opacity="0.45"/></svg>'
)


def _row(page: Page, key: str) -> Locator:
    """A theme's row in the list, by the theme's key."""
    return page.locator(f"[data-hmz=theme][data-key={key}]")


def test_a_preset_is_chosen_and_shown_dark(world: World) -> None:
    with world.page(desktop=True) as page:
        go(page, "/settings/themes")
        expect(page.get_by_role("heading", name="Presets")).to_be_visible()
        # The whole window is what the page opens on: thirteen swatches are a large picture.
        shots.web(page, f"{_PAGE}-list", window="desktop", most=shots.REEL)

        reel = shots.Reel(f"{_PAGE}-switch", window="desktop")
        use = _row(page, "temperate-gold").get_by_role("button", name="Use")
        reel.web(page, hold=1.6, pointer=use, click=True)
        use.click()
        expect(_row(page, "temperate-gold")).to_contain_text("In use")
        dark = page.get_by_role("group", name="Appearance").get_by_role(
            "button", name="Dark"
        )
        reel.web(page, hold=2.2, caption="Use takes a theme, both its sides")
        reel.web(page, hold=1.0, pointer=dark, click=True)
        dark.click()
        expect(dark).to_have_attribute("aria-pressed", "true")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        reel.web(page, hold=3.2, caption="Appearance picks the side", poster=True)
        reel.save()


def test_a_theme_of_ones_own_is_edited_and_written_out(
    world: World, tmp_path: Path
) -> None:
    dots = tmp_path / "dots.svg"
    dots.write_text(_DOTS)
    with world.page(desktop=True) as page:
        go(page, "/settings/themes")
        page.get_by_role("button", name="New", exact=True).click()
        name = page.get_by_role("textbox", name="Name", exact=True)
        expect(name).to_have_value("New theme")
        name.fill("Harbour")
        page.get_by_role("textbox", name="Page", exact=True).fill("#eef4fb")
        page.get_by_role("textbox", name="Sidebar", exact=True).fill("#dfeaf6")
        page.get_by_role("textbox", name="Brand", exact=True).fill("#1f6feb")
        page.locator("[data-hmz=picture-page]").set_input_files(dots)
        plane = page.locator("[data-hmz=plane-page]")
        expect(plane.get_by_role("button", name="Replace")).to_be_visible()
        plane.get_by_role("combobox").select_option("tile")
        dialog = page.get_by_role("dialog")
        name.scroll_into_view_if_needed()
        dialog.locator("[data-hmz=theme-editor]").evaluate(
            "node => node.scrollIntoView({block: 'start'})"
        )
        shots.web(page, f"{_PAGE}-editor", window="desktop", most=shots.REEL)

        # The pictures, at the foot of the editor.
        plane.scroll_into_view_if_needed()
        shots.web(page, f"{_PAGE}-pictures", clip=plane.locator("xpath=../.."), pad=8)

        # Written out, the file holds the name and both sides.
        with page.expect_download() as saving:
            dialog.get_by_role("button", name="Export").click()
        saved = saving.value
        assert saved.suggested_filename == "Harbour.hmztheme"
        said = json.loads(Path(saved.path()).read_text())
        assert said["hmztheme"] == 1
        assert said["name"] == "Harbour"
        assert said["light"]["colors"]["paper"] == "#eef4fb"
        assert said["light"]["images"]["page"]["fit"] == "tile"
        assert set(said) == {"hmztheme", "name", "light", "dark"}

        # Read back in, it is a second theme of the same name.
        dialog.get_by_role("link", name="Done").click()
        page.locator("[data-hmz=theme-file]").set_input_files(saved.path())
        expect(page.get_by_text("Imported Harbour")).to_be_visible()
        expect(page.locator("[data-hmz=custom] [data-hmz=theme]")).to_have_count(2)
        custom = page.locator("[data-hmz=custom]")
        custom.scroll_into_view_if_needed()
        shots.web(page, f"{_PAGE}-custom", clip=custom, pad=8)


def test_the_page_is_turned_to_chinese(world: World) -> None:
    world.says({"discount": _ANSWER})
    world.chat(_TASK)
    with world.page(desktop=True) as page:
        go(page, "/settings/language")
        pick = page.get_by_label("Language", exact=True)
        expect(pick).to_be_visible()
        reel = shots.Reel(f"{_PAGE}-language", window="desktop")
        reel.web(page, hold=2.0, pointer=pick, click=True)
        pick.select_option("zh-Hans")
        expect(page.locator("html")).to_have_attribute("lang", "zh-Hans")
        expect(page.locator("#language")).to_have_value("zh-Hans")
        page.get_by_text(_TASK).first.wait_for()
        reel.web(page, hold=3.5, caption="简体中文", poster=True)
        reel.save()


async def test_the_terminal_draws_in_the_terminals_colours(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEXTUAL_THEME", "terminal")
    async with world.tui((96, 26)) as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.pause(0.4)
        assert app.theme == "terminal"
        shots.tui(app, f"{_PAGE}-terminal")


async def test_the_terminal_takes_a_theme_of_textuals(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEXTUAL_THEME", "gruvbox")
    async with world.tui((96, 26)) as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.pause(0.4)
        assert app.theme == "gruvbox"
        shots.tui(app, f"{_PAGE}-terminal-theme")

"""`hmz web`'s language, driven in a browser: English, Simplified or Traditional Chinese.

The page is the real one, served in the test's own process. The language is this browser's own:
the one chosen in Settings, kept in its storage, or the one the browser asks for where none is
chosen. Each test runs in Chromium and in WebKit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, again, go, opened

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Page

pytestmark = [
    pytest.mark.parametrize("engine", ENGINES),
    pytest.mark.usefixtures("daemon"),
]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, and a project to serve."""
    project = install(tmp_path, monkeypatch)
    # The home it gives the CLI is this machine's home, which the daemon's own settings are of.
    (tmp_path / "home").mkdir(exist_ok=True)
    return project


def _written(page: Page, language: str) -> None:
    """Waits for the page to be open again, written in `language`, on its Language page."""
    expect(page.locator("html")).to_have_attribute("lang", language)
    page.wait_for_selector("[data-hmz=sidebar] .brand")
    expect(page.locator("[data-hmz=settings-language] select")).to_be_visible()


def _kept(page: Page) -> str | None:
    """The language this browser keeps as chosen, or none."""
    return page.evaluate("localStorage.getItem('hmz-language')")


def _ago(page: Page) -> str:
    """How the page says a moment that has only just been."""
    return page.evaluate("async () => (await import('/dom.js')).ago(Date.now() / 1000)")


def test_a_language_is_chosen_in_settings_and_the_page_is_written_in_it(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        # English until another is chosen, where English is what the browser asks for.
        expect(page.locator("html")).to_have_attribute("lang", "en")
        go(page, "/settings/language")
        nav = page.locator(".settings-nav")
        expect(nav.locator("a:visible")).to_contain_text(
            ["Themes", "Daemons", "Notifications", "Language", "General"]
        )
        expect(page.locator(".settings-head h3")).to_have_text("Language")
        picker = page.get_by_label("Language")
        expect(picker).to_have_attribute("data-hmz", "language")
        expect(picker.locator("option")).to_have_text(
            ["System", "English", "简体中文", "繁體中文"]
        )
        expect(picker).to_have_value("")
        # No daemon is picked for it: it is this browser's, whichever daemon is shown.
        expect(page.locator("[data-hmz=settings-daemon]")).to_have_count(0)
        assert _kept(page) is None
        assert _ago(page) == "just now"

        # Chosen, it is kept, and the page opens again where it was, written in it.
        picker.select_option("zh-Hans")
        _written(page, "zh-Hans")
        assert _kept(page) == "zh-Hans"
        assert page.url.endswith("#/settings/language")
        expect(page.locator(".settings-head h3")).to_have_text("语言")
        expect(nav.locator("[aria-current=page]")).to_have_text("语言")
        picker = page.get_by_label("语言")
        expect(picker).to_have_value("zh-Hans")
        # A language is called what it calls itself; only the system's is the page's word.
        expect(picker.locator("option")).to_have_text(
            ["跟随系统", "English", "简体中文", "繁體中文"]
        )
        assert _ago(page) == "刚刚"

        picker.select_option("zh-Hant")
        _written(page, "zh-Hant")
        expect(page.locator(".settings-head h3")).to_have_text("語言")
        assert _ago(page) == "剛剛"

        # Kept: a page opened anew is written in it, and the choice is shown as made.
        again(page)
        _written(page, "zh-Hant")
        picker = page.get_by_label("語言")
        expect(picker).to_have_value("zh-Hant")

        picker.select_option("en")
        _written(page, "en")
        assert _kept(page) == "en"
        expect(page.locator(".settings-head h3")).to_have_text("Language")

        # Under System nothing is kept, and what the browser asks for is followed.
        page.get_by_label("Language").select_option("")
        _written(page, "en")
        assert _kept(page) is None


@pytest.mark.parametrize(
    ("asked", "language", "heading"),
    [
        ("zh-CN", "zh-Hans", "语言"),
        ("zh-SG", "zh-Hans", "语言"),
        ("zh-TW", "zh-Hant", "語言"),
        ("zh-HK", "zh-Hant", "語言"),
        ("fr-FR", "en", "Language"),
    ],
)
def test_with_none_chosen_the_page_follows_what_the_browser_asks_for(
    project: Path, engine: str, asked: str, language: str, heading: str
) -> None:
    with served() as site, opened(site, engine=engine, locale=asked) as page:
        expect(page.locator("html")).to_have_attribute("lang", language)
        go(page, "/settings/language")
        expect(page.locator(".settings-head h3")).to_have_text(heading)
        picker = page.locator("[data-hmz=language]")
        expect(picker).to_have_value("")
        assert _kept(page) is None

        # One chosen is the page's, whatever the browser asks for; System follows it again.
        picker.select_option("en")
        _written(page, "en")
        expect(page.locator(".settings-head h3")).to_have_text("Language")
        page.locator("[data-hmz=language]").select_option("")
        _written(page, language)
        expect(page.locator(".settings-head h3")).to_have_text(heading)


def test_a_language_chosen_in_one_tab_is_every_tabs(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        other = page.context.new_page()
        other.goto(site.address)
        other.wait_for_selector("[data-hmz=sidebar] .brand")
        expect(other.locator("html")).to_have_attribute("lang", "en")

        go(page, "/settings/language")
        page.locator("[data-hmz=language]").select_option("zh-Hant")
        _written(page, "zh-Hant")
        expect(other.locator("html")).to_have_attribute("lang", "zh-Hant")
        other.wait_for_selector("[data-hmz=sidebar] .brand")


def test_the_language_page_fits_a_phone_in_every_language(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine, width=390, height=780) as page:
        go(page, "/settings/language")
        for language in ("zh-Hans", "zh-Hant", "en"):
            page.locator("[data-hmz=language]").select_option(language)
            _written(page, language)
            body = page.locator("[data-hmz=settings-language]")
            for part in (body.locator("select"), body.locator(".hint")):
                box = part.bounding_box()
                assert box is not None
                assert box["x"] >= 0, language
                assert box["x"] + box["width"] <= 390, language
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), language

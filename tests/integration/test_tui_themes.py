"""Themes and Language: what `/settings` shows before it is chosen, and keeps once it is."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz import config, words
from hmz.tui import Humanize, humanfia
from hmz.tui.settings import Adjusts
from tests.integration.doubles_tui import (
    SIZE,
    on,
    onto,
    opened,
    opens,
    screen,
    shows,
    stand_in,
    trail,
    typed,
    until,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from textual.pilot import Pilot

#: Every epic here is held by a daemon of the test's own, in this process.
pytestmark = [pytest.mark.usefixtures("daemon"), pytest.mark.timeout(120)]

#: The page's presets, as the page keeps them.
PRESETS = Path(humanfia.__file__).parents[1] / "web" / "static" / "presets.js"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, and nothing in the environment that says how to look."""
    del asking
    for name in ("TEXTUAL_THEME", "NO_COLOR", "COLORFGBG", "LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    return stand_in(tmp_path, monkeypatch)


@pytest.fixture(autouse=True)
def english() -> Iterator[None]:
    """Whatever a test chose, the next one is said in English."""
    yield
    words.speak("en")


def kept() -> dict[str, object]:
    """What the settings file keeps of the interface's own."""
    at = config() / "settings.toml"
    held = tomllib.loads(at.read_text()) if at.exists() else {}
    return held.get("tui", {})


async def into(pilot: Pilot[None], page: str) -> Adjusts:
    """Opens `/settings` on one of its pages."""
    await opened(pilot)
    await typed(pilot, f"/settings {page}")
    return await on(pilot, Adjusts)


def _pairs() -> dict[str, tuple[str, dict[str, str], dict[str, str]]]:
    """`PAIRS` of `presets.js`: each pair's name and the colours each side is said in."""
    source = PRESETS.read_text(encoding="utf-8")
    listed = source[source.index("export const PAIRS") : source.index("function rgb")]
    found: dict[str, tuple[str, dict[str, str], dict[str, str]]] = {}
    for pair in re.split(r"\{\s*key: ", listed)[1:]:
        named = re.match(r"'([^']+)',\s*name: '([^']+)'", pair)
        assert named is not None, pair
        key, name = named.groups()
        sides = {
            side: dict(re.findall(r"(\w+): '([^']+)'", said))
            for side, said in re.findall(r"(light|dark): \{([^}]*)\}", pair)
        }
        found[key] = (name, sides.get("light", {}), sides.get("dark", {}))
    return found


def test_the_presets_are_the_pages_value_for_value() -> None:
    pairs = _pairs()

    assert len(pairs) > 1
    assert list(humanfia.PRESETS) == list(pairs)
    for key, (name, light, dark) in pairs.items():
        assert humanfia.PRESETS[key] == humanfia.Pair(name, light, dark), key
        assert words.known(name), name


async def test_f2_opens_settings_and_is_said_on_the_hint_line(workspace: Path) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await until(pilot, lambda: "F2 settings" in screen(app), "the hint line")

        await pilot.press("f2")
        await on(pilot, Adjusts)
        await shows(pilot, "/settings", "APP", "Themes")

        # The key is bound over the page it opens, and does not open it over itself.
        await pilot.press("f2")
        await until(
            pilot, lambda: len(app.screen_stack) == 1, "the page closed by its key"
        )

        await pilot.press("f2")
        await on(pilot, Adjusts)
        assert len(app.screen_stack) == 2

        await pilot.press("escape")
        await until(pilot, lambda: len(app.screen_stack) == 1, "the page closed")


async def test_a_preset_is_shown_as_the_cursor_moves_kept_on_enter_and_opened_in_again(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        assert app.theme == "humanfia-dark"
        await into(pilot, "themes")
        await shows(pilot, trail("/settings", "Themes"), "APPEARANCE", "PRESETS")
        # Opening the page changes nothing: the cursor is on what is in use.
        assert app.theme == "humanfia-dark"

        await onto(pilot, "pair:critical-teal")
        await until(pilot, lambda: app.theme == "critical-teal-dark", "the preview")
        assert kept() == {}

        # Esc puts back what was kept.
        await pilot.press("escape")
        await until(pilot, lambda: app.theme == "humanfia-dark", "the theme put back")
        await shows(pilot, "Humanize Green · Auto")

        await opens(pilot, "themes")
        await onto(pilot, "pair:devoted-pink")
        await pilot.press("enter")
        await shows(pilot, "Saved")
        assert kept() == {"theme": "devoted-pink", "appearance": "auto", "language": ""}

        # And a side of it: the light one, seen on the way to it and kept.
        await onto(pilot, "mode:light")
        await until(pilot, lambda: app.theme == "devoted-pink-light", "its light side")
        await pilot.press("enter")
        await pilot.press("escape")
        await shows(pilot, "Devoted Pink · Light")
        await pilot.press("escape")
        await until(pilot, lambda: len(app.screen_stack) == 1, "the menu closed")
        assert app.theme == "devoted-pink-light"

    again = Humanize()
    async with again.run_test(size=SIZE) as pilot:
        await opened(pilot)
        assert again.theme == "devoted-pink-light"


async def test_the_terminals_own_colours_are_an_appearance_and_a_preset_leaves_them(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await into(pilot, "themes")
        await opens(pilot, "mode:terminal")
        await until(pilot, lambda: app.theme == "terminal", "the terminal's colours")
        assert kept()["appearance"] == "terminal"

        # A preset is chosen to be seen: it goes back to following the terminal.
        await opens(pilot, "pair:surviving-jade")
        await until(pilot, lambda: app.theme == "surviving-jade-dark", "the preset")
        assert kept() == {
            "theme": "surviving-jade",
            "appearance": "auto",
            "language": "",
        }


@pytest.mark.parametrize(
    ("name", "value", "theme"),
    [("NO_COLOR", "1", "terminal"), ("TEXTUAL_THEME", "nord", "nord")],
)
async def test_a_variable_that_decides_the_theme_wins_and_the_page_says_so(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str, value: str, theme: str
) -> None:
    monkeypatch.setenv(name, value)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        assert app.theme == theme
        await into(pilot, "themes")
        await shows(pilot, f"{name} is set in the environment and decides this")

        await opens(pilot, "pair:critical-teal")
        await shows(pilot, "Saved")

        # Kept for when it is not set, and not drawn while it is.
        assert app.theme == theme
        assert kept()["theme"] == "critical-teal"


async def test_a_language_is_shown_as_the_cursor_moves_kept_on_enter_and_opened_in_again(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await into(pilot, "language")
        await shows(pilot, trail("/settings", "Language"), "System", "English")

        await onto(pilot, "lang:zh-Hans")
        await shows(pilot, trail("/settings", "语言"), "跟随系统")
        # Esc puts back the language kept.
        await pilot.press("escape")
        await shows(pilot, "/settings", "Language", "Themes")
        assert kept() == {}

        await opens(pilot, "language")
        await opens(pilot, "lang:zh-Hans")
        await shows(pilot, "已保存")
        assert kept()["language"] == "zh-Hans"
        await pilot.press("escape")
        await shows(pilot, "主题", "通知", "语言", "简体中文")
        await pilot.press("escape")
        await until(pilot, lambda: len(app.screen_stack) == 1, "the menu closed")

        # A view opened after the change is written in it.
        await pilot.press("f1")
        await shows(pilot, "返回")

    again = Humanize()
    async with again.run_test(size=SIZE) as pilot:
        await opened(pilot)
        assert words.language() == "zh-Hans"
        await pilot.press("f1")
        await shows(pilot, "返回")


async def test_system_is_the_language_the_terminal_is_set_to(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANG", "zh_TW.UTF-8")
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        assert words.language() == "zh-Hant"

        await into(pilot, "language")
        await opens(pilot, "lang:en")
        await pilot.press("escape")
        await shows(pilot, "Language", "English")
        assert words.language() == "en"

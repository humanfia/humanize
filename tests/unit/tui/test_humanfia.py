"""`hmz.tui.humanfia`: the themes, which one the interface opens in, and the mark."""

from __future__ import annotations

import pytest

from hmz.tui import humanfia


def test_the_themes_are_the_pages_colours() -> None:
    dark, light = humanfia.THEMES["humanfia-dark"], humanfia.THEMES["humanfia-light"]

    assert (dark.dark, light.dark) == (True, False)
    assert (dark.background, dark.foreground) == ("#0f1418", "#e6eff1")
    assert (light.background, light.foreground) == ("#f4f8f9", "#141a1f")
    # Cyan is what can be followed, pink what is picked out, and green is the mark's alone.
    assert (dark.primary, dark.accent) == ("#4fd8ea", "#ff94c2")
    assert (light.primary, light.accent) == ("#1fb3c7", "#ec6fa3")
    assert dark.variables["hmz-green"] == light.variables["hmz-green"] == "#76b900"
    assert dark.variables["block-cursor-background"] == dark.accent


def test_every_name_a_stylesheet_asks_for_has_a_value_in_any_theme() -> None:
    for theme in humanfia.THEMES.values():
        assert set(humanfia.FALLBACK) <= set(theme.variables)


@pytest.mark.parametrize(
    ("environ", "kept", "theme"),
    [
        ({}, "", "humanfia-dark"),
        ({"COLORFGBG": "0;15"}, "", "humanfia-light"),
        ({"COLORFGBG": "0;default;7"}, "", "humanfia-light"),
        ({"COLORFGBG": "15;0"}, "", "humanfia-dark"),
        ({"COLORFGBG": "0;15"}, "dark", "humanfia-dark"),
        ({}, "light", "humanfia-light"),
        ({}, "terminal", "terminal"),
        ({}, "gone", "humanfia-dark"),
        ({"NO_COLOR": "1"}, "light", "terminal"),
        ({"TEXTUAL_THEME": "nord", "NO_COLOR": "1"}, "light", "nord"),
        ({"TEXTUAL_THEME": "gone"}, "", "humanfia-dark"),
    ],
)
def test_the_theme_opened_in(environ: dict[str, str], kept: str, theme: str) -> None:
    available = {"terminal": 0, "nord": 0, **humanfia.THEMES}

    assert humanfia.chosen(environ, available, kept) == theme


def test_the_mark_is_two_stems_a_diagonal_and_a_dot() -> None:
    assert list(humanfia.MARK) == [
        "████        ▄██▄",
        "████        ▀██▀",
        "████        ▄▄▄█",
        "████  ▄▄▄███████",
        "███████████▀████",
        "█████▀▀▀    ████",
        "████        ████",
        "████        ████",
        "████        ████",
    ]
    assert [len(row) for row in humanfia.mark(8)] == [8] * 4

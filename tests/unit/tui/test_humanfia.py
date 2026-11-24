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
        # A preset kept by its key is whichever of its sides the terminal asks for.
        ({}, "humanize", "humanfia-dark"),
        ({}, "critical-teal", "critical-teal-dark"),
        ({"COLORFGBG": "0;15"}, "critical-teal", "critical-teal-light"),
        ({"COLORFGBG": "0;15"}, "critical-teal-dark", "critical-teal-dark"),
        ({"NO_COLOR": "1"}, "critical-teal", "terminal"),
    ],
)
def test_the_theme_opened_in(environ: dict[str, str], kept: str, theme: str) -> None:
    available = {"terminal": 0, "nord": 0, **humanfia.THEMES}

    assert humanfia.chosen(environ, available, kept) == theme


@pytest.mark.parametrize(
    ("ground", "side"),
    [("", "dark"), ("15;0", "dark"), ("0;15", "light"), ("0;default;7", "light")],
)
def test_the_side_is_the_one_the_terminals_background_asks_for(
    ground: str, side: str
) -> None:
    assert humanfia.side({"COLORFGBG": ground}) == side
    assert humanfia.side({}) == "dark"


def test_every_preset_is_a_light_theme_and_a_dark_one_named_for_it() -> None:
    assert next(iter(humanfia.PRESETS)) == "humanize"
    assert humanfia.PRESETS["humanize"] == humanfia.Pair("Humanize Green")
    assert humanfia.named("humanize", "dark") == "humanfia-dark"
    assert humanfia.named("devoted-pink", "light") == "devoted-pink-light"
    for key in humanfia.PRESETS:
        light = humanfia.THEMES[humanfia.named(key, "light")]
        dark = humanfia.THEMES[humanfia.named(key, "dark")]
        assert (light.dark, dark.dark) == (False, True)
    assert len(humanfia.THEMES) == 2 * len(humanfia.PRESETS)


def test_a_preset_is_drawn_in_its_few_colours_and_what_is_worked_out_of_them() -> None:
    gold = humanfia.PRESETS["temperate-gold"]

    light, dark = humanfia.preset("temperate-gold", gold.light, gold.dark)

    assert (light.name, dark.name) == ("temperate-gold-light", "temperate-gold-dark")
    assert (dark.background, dark.foreground) == ("#17130c", "#f3ead6")
    # What is followed is its accent, what is picked out its highlight, the mark its brand.
    assert (dark.primary, dark.accent) == ("#e3bf6a", "#d9a58a")
    assert dark.variables["hmz-green"] == "#e3b04f"
    assert dark.variables["block-cursor-background"] == dark.accent
    # The planes are the paper with a little of the ink, or of white, mixed in as the page
    # mixes them, a half rounded up.
    assert (dark.surface, light.surface) == ("#242018", "#fdfbf6")
    # And what a preset does not say is humanfia's own of that side.
    assert dark.error == humanfia.DARK["fail"]
    assert light.success == humanfia.LIGHT["done"]


def test_a_preset_of_no_colours_is_humanfias_own() -> None:
    light, dark = humanfia.preset("humanize", {}, {})

    assert (light.name, light.background) == ("humanfia-light", humanfia.LIGHT["paper"])
    assert (dark.name, dark.primary) == ("humanfia-dark", humanfia.DARK["cyan"])


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

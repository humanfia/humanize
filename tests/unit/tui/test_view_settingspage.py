"""`hmz.tui.views.settingspage`: the key that opens `/settings` over the screen."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from hmz.tui.views import settingspage

if TYPE_CHECKING:
    import pytest
    from textual.app import App


def test_settings_is_a_page_opened_by_f2_and_said_on_the_hint_line() -> None:
    (view,) = settingspage.VIEWS

    assert (view.name, view.zone, view.key) == ("settings", "page", "f2")
    assert (view.title, view.hint) == ("Settings", "settings")
    # A page is not open as the interface opens, and says its keys on a sheet of its own.
    assert not view.opens
    assert view.keys == ()


def test_what_it_makes_is_the_settings_menu_on_its_first_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[Any, ...]] = []

    def menu(*given: object) -> str:
        asked.append(given)
        return "the menu"

    monkeypatch.setattr(settingspage, "menu", menu)
    (view,) = settingspage.VIEWS

    made = view.make(cast("App[None]", None))

    assert cast("str", made) == "the menu"
    assert asked == [()]

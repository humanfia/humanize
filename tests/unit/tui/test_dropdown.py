"""`hmz.tui.dropdown`: the values a row can take, as the list dropped under it says them."""

from __future__ import annotations

from textual.binding import Binding
from textual.screen import ModalScreen

from hmz.tui.dropdown import Dropdown, Value


def test_a_value_says_nothing_beside_itself_unless_told() -> None:
    assert Value("on", "On") == ("on", "On", "")
    assert Value("on", "On", "send reports").about == "send reports"


def test_a_dropdown_is_a_screen_of_its_own_answering_with_a_value() -> None:
    dropped = Dropdown(
        "reports",
        [Value("on", "On"), Value("off", "Off")],
        "on",
        cursor="off",
    )

    assert isinstance(dropped, ModalScreen)
    assert any(
        binding.key == "escape"
        for binding in Dropdown.BINDINGS
        if isinstance(binding, Binding)
    )

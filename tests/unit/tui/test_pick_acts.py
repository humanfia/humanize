"""`hmz.tui.pick.Acts`: what one row of a list offers, opened on it with `m`."""

from __future__ import annotations

from hmz.tui.pick import Action, Acts


def test_a_row_s_menu_lists_its_offers_in_order() -> None:
    acts = Acts(
        "box",
        [
            Action("connect", "connect", "reach it now", lambda: None),
            Action("remove", "remove", "take it away", lambda: None, variant="error"),
        ],
    )

    assert acts.asked == "box"
    assert acts.rows() == [
        ("connect", "connect", "reach it now"),
        ("remove", "remove", "take it away"),
    ]
    assert acts.nothing() == ""


def test_a_row_offering_nothing_says_so() -> None:
    assert Acts("Local", []).nothing() == "nothing to do with this one now"

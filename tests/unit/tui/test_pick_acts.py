"""`hmz.tui.pick.Acts`: what one row of a list offers, opened on it with `m`."""

from __future__ import annotations

from textual.app import App
from textual.widgets import Button

from hmz.tui.pick import Action, Acts, Confirms, hinted


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
    assert Acts("Local", []).nothing() == "no actions"


def _drawn(app: App[None]) -> str:
    """The screen as plain text: every cell the screenshot holds, row by row."""
    import html
    import re

    cells = re.findall(r"<text[^>]*>([^<]*)</text>", app.export_screenshot())
    return html.unescape("".join(cells)).replace("\xa0", " ")


async def test_a_menu_is_framed_heavily_with_its_title_in_capitals() -> None:
    app: App[None] = App()
    async with app.run_test(size=(80, 24)) as pilot:
        app.push_screen(
            Acts("the box", [Action("go", "connect", "reach it", lambda: None)])
        )
        await pilot.pause()
        drawn = _drawn(app)

        # Square corners and heavy rules, the title in capitals in the rule.
        assert "┏━ THE BOX ━" in drawn
        assert "╭" not in drawn
        assert "┗" in drawn
        # Its keys, in the page's words.
        assert "enter Choose" in drawn
        assert "esc Back" in drawn


async def test_a_box_is_headed_question_and_its_answer_is_the_one_to_press() -> None:
    app: App[None] = App()
    async with app.run_test(size=(80, 24)) as pilot:
        app.push_screen(Confirms())
        await pilot.pause()
        drawn = _drawn(app)
        assert "┏━ QUESTION ━" in drawn
        assert "Save changes?" in drawn

        save, discard = app.screen.query("#actions Button").results(Button)
        assert [str(save.label), str(discard.label)] == ["Save", "Discard"]
        # The one that answers is the one drawn apart; the other is not.
        assert save.has_class("-primary")
        assert not discard.has_class("-primary")


def test_a_key_said_in_lower_case_is_said_in_the_pages_word_where_it_has_one() -> None:
    assert hinted("open") == "Open"
    assert hinted("back") == "Back"
    # No such text: said as the sheet said it.
    assert hinted("fold all") == "fold all"

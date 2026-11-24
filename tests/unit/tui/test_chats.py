"""The sheets a chat written down is tidied from: `/resume`'s list, and the archived chats."""

from __future__ import annotations

from typing import Any

from hmz.tui.chats import Archived, Deletes, Renames, Resumes

_ONE: dict[str, Any] = {"id": "c1", "title": "the  parser\nand more"}
_LONG: dict[str, Any] = {"id": "c2", "title": "x" * 80}
_BARE: dict[str, Any] = {"id": "c3", "title": ""}


def test_each_chat_is_a_row_by_its_id_with_its_title_on_one_line() -> None:
    sheet = Resumes([_ONE, _LONG, _BARE])

    assert sheet.rows() == [
        ("c1", "the parser and more", "c1"),
        ("c2", f"{'x' * 59}…", "c2"),
        # One with no title is called by its id.
        ("c3", "c3", "c3"),
    ]
    assert sheet.nothing() == ""
    assert sheet.gone == set()


def test_the_archived_chats_say_they_are_being_read_until_they_are() -> None:
    sheet = Archived("/w")

    assert sheet.rows() == []
    assert sheet.nothing() == "Reading archived chats…"


def test_a_title_is_asked_for_on_one_row_until_it_says_something() -> None:
    form = Renames("the parser")

    (asked,) = form.asked()
    assert (asked.held, asked.needed) == ("title", False)
    assert form.done_about() == "renames the chat"


def test_deleting_says_it_is_permanent_and_keeping_is_the_first_answer() -> None:
    box = Deletes("the [parser]")

    assert box.asked == r"Delete the \[parser]?"
    assert "permanently removes" in box.about
    assert "cannot be undone" in box.about
    assert [answer for answer, _, _ in box.rows()] == ["no", "yes"]


async def test_a_title_holding_what_a_text_s_note_is_marked_with_is_asked_about_whole() -> (
    None
):
    from textual.app import App
    from textual.widgets import Label

    app: App[None] = App()
    async with app.run_test(size=(80, 24)) as pilot:
        app.push_screen(Deletes("fix @@todo parser"))
        await pilot.pause()
        asked = app.screen.query_one("#asked", Label)
        assert str(asked.content) == "Delete fix @@todo parser?"
    assert Deletes.PRIMARY == "yes"

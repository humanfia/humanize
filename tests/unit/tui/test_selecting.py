"""`hmz.tui.selecting`: what a selection over a list gives back is the text it was given."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.geometry import Offset
from textual.selection import Selection
from textual.widgets.option_list import Option

from hmz.tui.selecting import Choices, Transcript


@pytest.fixture
def choices() -> Choices:
    listing = Choices(id="choices")
    listing.add_options(
        ["alpha", Option("be[b]ta[/b]"), None, "a much longer line than the rest"]
    )
    return listing


def test_the_whole_list_is_its_options_text_a_line_apiece(choices: Choices) -> None:
    assert choices.get_selection(Selection(None, None)) == (
        "alpha\nbeta\na much longer line than the rest",
        "\n",
    )


def test_a_selection_across_options_is_the_text_between(choices: Choices) -> None:
    taken = choices.get_selection(Selection(Offset(1, 0), Offset(3, 1)))

    assert taken == ("lpha\nbet", "\n")


def test_an_empty_list_gives_back_nothing() -> None:
    assert Choices().get_selection(Selection(None, None)) == ("", "\n")


def test_a_list_can_be_selected_from() -> None:
    assert Choices.ALLOW_SELECT


def test_a_transcript_starts_empty_and_is_emptied_by_clear() -> None:
    transcript = Transcript(id="transcript")
    assert transcript.text == ""
    assert transcript.id == "transcript"

    transcript.clear()

    assert transcript.text == ""


def test_a_transcript_never_takes_the_focus() -> None:
    assert not Transcript().can_focus


class _Shows(App[None]):
    """An app holding nothing but a transcript, so that what is written to it is drawn."""

    def compose(self) -> ComposeResult:
        yield Transcript(id="transcript")


@pytest.mark.parametrize(
    "written",
    [
        # Textual's own colour names, which Rich reads as words: `[/]` closes nothing.
        "[$secondary]●[/] Task[dim](wait) started[/]",
        # A backslash that escapes the tag after it, leaving its close with nothing to close.
        "[green]●[/] foo\\[dim](bar)[/]",
    ],
)
async def test_a_line_that_is_not_markup_is_drawn_as_written(written: str) -> None:
    app = _Shows()
    async with app.run_test(size=(60, 10)) as pilot:
        transcript = app.query_one(Transcript)
        transcript.write("before")
        await pilot.pause()

        transcript.write(written)
        await pilot.resize_terminal(40, 10)
        await pilot.pause()

        assert transcript.text.splitlines() == ["before", written]

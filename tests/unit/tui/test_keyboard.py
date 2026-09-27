"""What a terminal says a key was, read whole however long an input method made it.

Fed to Textual's own parser the way its input thread feeds it -- everything that arrived, then
the end of it -- and read back as what it turned into. What is sent is what Ghostty sends once
Textual has asked for every key as a report with its text inside: an input method's commit is
one report, the key that confirmed it and then every character committed, as code points
between colons.

Nothing here asks for the ceiling to be raised: importing the interface is what does it, and a
test that asked for it itself would go on passing with that gone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual import events
from textual._xterm_parser import XTermParser

from hmz.tui import keyboard

if TYPE_CHECKING:
    from textual.message import Message


def read(sent: str) -> list[Message]:
    """What Textual reads out of what a terminal sent, once nothing more is coming."""
    parser = XTermParser()
    return [*parser.feed(sent), *parser.feed("")]


def keys(sent: str) -> list[events.Key]:
    """The keys among it."""
    return [each for each in read(sent) if isinstance(each, events.Key)]


def typed(sent: str) -> str:
    """What those keys type."""
    return "".join(each.character or "" for each in keys(sent))


def committed(text: str, confirmed: str) -> str:
    """What Ghostty sends for an input method committing `text` on the key `confirmed`."""
    return f"\x1b[{ord(confirmed)};;{':'.join(str(ord(each)) for each in text)}u"


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("你", id="a-character"),  # the one that always arrived
        pytest.param("你帮我检查一下这个代码库", id="a-sentence"),
        pytest.param("satisfaction", id="a-word"),
        # A hundred and fifty characters, and still one report.
        pytest.param("中文输入法" * 30, id="a-paragraph"),
    ],
)
@pytest.mark.parametrize(
    "confirmed",
    [pytest.param(" ", id="on-space"), pytest.param("1", id="on-its-number")],
)
def test_a_commit_arrives_whole_however_long(text: str, confirmed: str) -> None:
    """Rather than as the report it arrived in, typed out a character at a time."""
    assert typed(committed(text, confirmed)) == text


@pytest.mark.parametrize(
    ("sent", "key"),
    [
        # The key the protocol is asked for at all.
        pytest.param("\x1b[13;2u", "shift+enter", id="shift+enter"),
        pytest.param("\x1b[97;;97u", "a", id="a"),
        pytest.param("\x1b[27u", "escape", id="escape"),
        pytest.param("\x1b[9;2u", "shift+tab", id="shift+tab"),
        pytest.param("\x1b[1;5A", "ctrl+up", id="ctrl+up"),
    ],
)
def test_an_ordinary_report_is_still_the_key_it_was(sent: str, key: str) -> None:
    """The pattern a report is read with is not Textual's own, so what it reads is checked."""
    assert [each.key for each in keys(sent)] == [key]


def test_a_resize_reported_in_band_is_still_read() -> None:
    """Its pattern is held to the length it was tried at, which a resize is well inside."""
    resized = [
        each
        for each in read("\x1b[48;24;80;480;1280t")
        if isinstance(each, events.Resize)
    ]

    assert [each.size for each in resized] == [(80, 24)]


@pytest.mark.timeout(10)
@pytest.mark.parametrize(
    "sent",
    [
        pytest.param("\x1b[" + "1" * keyboard.LONGEST, id="a-key-report"),
        pytest.param("\x1b[48;1:" + "1:;" * (keyboard.LONGEST // 3), id="a-resize"),
    ],
)
def test_a_sequence_that_never_ends_is_let_go_of(sent: str) -> None:
    """Typed out as what it was, and at once: every character is checked against all of it.

    The patterns Textual ships each take ten seconds at a quarter of this length, which is
    what its own ceiling of 32 was keeping them from.
    """
    assert typed(sent).endswith(sent.removeprefix("\x1b["))

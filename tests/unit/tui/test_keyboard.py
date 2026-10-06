"""`hmz.tui.keyboard`: a key report is read whole however long an input method made it."""

from __future__ import annotations

import importlib
import time
from typing import Any

import pytest

from hmz.tui import keyboard

#: Textual's parser, reached by name: what this module changes is how it reads, and the
#: parser is the only thing that can say so.
_PARSER: Any = importlib.import_module("textual._xterm_parser")

#: What `reads_long_reports` changes in it, so that each test leaves it as it found it.
_CHANGED = (
    "_MAX_SEQUENCE_SEARCH_THRESHOLD",
    "_re_extended_key",
    "_re_in_band_window_resize",
)


@pytest.fixture(autouse=True)
def _parser_restored(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _CHANGED:
        monkeypatch.setattr(_PARSER, name, getattr(_PARSER, name))
    keyboard.reads_long_reports()


def _keys(sequence: str) -> list[tuple[str, str | None]]:
    """What Textual reads a sequence as, fed one character at a time as a terminal might."""
    parser = _PARSER.XTermParser(debug=False)
    read: list[tuple[str, str | None]] = []
    for character in sequence:
        read.extend(
            (type(event).__name__, getattr(event, "character", None))
            for event in parser.feed(character)
        )
    return read


def _commit(text: str, confirm: int = 32) -> str:
    """An input method's commit of `text`, as a kitty-protocol terminal reports it."""
    return f"\x1b[{confirm};;" + ":".join(str(ord(one)) for one in text) + "u"


def test_the_ceiling_is_what_one_commit_can_be() -> None:
    assert keyboard.LONGEST == 1024
    # Some hundred and sixty characters of Chinese, at six characters of report to each.
    near = "你" * 160
    assert len(_commit(near)) < keyboard.LONGEST
    assert _keys(_commit(near)) == [("Key", "你")] * 160


@pytest.mark.parametrize(
    "text",
    ["你帮我", "你帮我写一个很长的句子吧" * 10, "abcdefghijklmnop"],
    ids=["short", "long-chinese", "letters"],
)
def test_a_commit_arrives_as_the_characters_it_committed(text: str) -> None:
    read = _keys(_commit(text))

    assert read == [("Key", one) for one in text]


def test_an_ordinary_key_report_still_reads_as_its_key() -> None:
    parser = _PARSER.XTermParser(debug=False)

    keys = [getattr(event, "key", None) for event in parser.feed("\x1b[13;2u")]

    assert keys == ["shift+enter"]


def test_a_sequence_that_never_ends_costs_milliseconds_not_seconds() -> None:
    began = time.perf_counter()
    _keys("\x1b[" + "1" * 900)

    assert time.perf_counter() - began < 2.0


def test_reading_long_reports_twice_changes_nothing_more() -> None:
    keyboard.reads_long_reports()

    assert _keys(_commit("你帮我写一个很长的句子")) == [
        ("Key", one) for one in "你帮我写一个很长的句子"
    ]

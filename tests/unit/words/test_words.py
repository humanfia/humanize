"""`hmz.words`: a text, in the language being spoken, with what is given put into it."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz import words
from hmz.words import LANGUAGES, known, language, speak, t, texts

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def english() -> Iterator[None]:
    speak("en")
    yield
    speak("en")


def test_the_languages_are_the_pages() -> None:
    assert list(LANGUAGES) == ["en", "zh-Hans", "zh-Hant"]
    assert words.__all__ == ["LANGUAGES", "known", "language", "speak", "t", "texts"]


def test_a_text_of_the_page_is_known_and_said_as_written() -> None:
    assert known("Cancel")
    assert "Cancel" in texts()
    assert t("Cancel") == "Cancel"


def test_a_text_written_for_an_area_is_known_too() -> None:
    assert known("show this help and exit")
    assert not known("a text nobody wrote")


def test_what_is_given_is_put_at_its_name_and_a_name_given_nothing_stays() -> None:
    assert t("{n}m ago", n=3) == "3m ago"
    assert t("writes {path}") == "writes {path}"


def test_a_note_telling_homographs_apart_is_not_said() -> None:
    assert t("Done@@button") == "Done"


def test_a_count_of_one_takes_the_singular() -> None:
    assert t("{n} sessions", n=1) == "1 session"
    assert t("{n} sessions", n=2) == "2 sessions"
    assert (
        t("Device revoked ({n} sessions closed).", n=1)
        == "Device revoked (1 session closed)."
    )
    assert (
        t("Device revoked ({n} sessions closed).", n=0)
        == "Device revoked (0 sessions closed)."
    )


@pytest.mark.parametrize(
    ("tag", "spoken", "cancel"),
    [
        ("zh-Hans", "zh-Hans", "取消"),
        ("zh_CN.UTF-8", "zh-Hans", "取消"),
        ("zh-TW", "zh-Hant", "取消"),
        ("zh-Hant", "zh-Hant", "取消"),
        ("en_US.UTF-8", "en", "Cancel"),
        ("fr", "en", "Cancel"),
    ],
)
def test_a_text_is_said_in_the_language_spoken(
    tag: str, spoken: str, cancel: str
) -> None:
    speak(tag)

    assert language() == spoken
    assert t("Cancel") == cancel


def test_a_text_the_language_has_none_for_is_said_in_english() -> None:
    speak("zh-Hans")

    assert t("show this help and exit") == "show this help and exit"
    assert t("{n} sessions", n=1) != "1 session"

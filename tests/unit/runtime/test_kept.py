"""An agent written down as one word, and read back off a file."""

from __future__ import annotations

import pytest

from hmz.runtime.kept import Runs, read_back, written


@pytest.mark.parametrize(
    ("runs", "word"),
    [
        (Runs("claude/opus:high"), "claude/opus:high"),
        (Runs("claude/opus:high", "work"), "claude@work/opus:high"),
        (Runs("codex/gpt-5/mini:low", "me"), "codex@me/gpt-5/mini:low"),
    ],
)
def test_an_agent_is_written_as_the_word_dash_a_takes(runs: Runs, word: str) -> None:
    assert written(runs) == word
    assert read_back(word) == runs


def test_an_account_defaults_to_this_machines_sign_in() -> None:
    assert Runs("claude/opus:high").provider == ""


@pytest.mark.parametrize(
    ("said", "runs"),
    [
        ("claude/opus", Runs("claude/opus:auto")),
        ("claude/opus:", Runs("claude/opus:auto")),
        ("claude@team/opus:max", Runs("claude/opus:max", "team")),
        # A model with a colon of its own is the model, at no effort of its own.
        ("mcode/gw:route/m", Runs("mcode/gw:route/m:auto")),
    ],
)
def test_reading_back_fills_in_no_effort_as_auto(said: str, runs: Runs) -> None:
    assert read_back(said) == runs


@pytest.mark.parametrize(
    "said",
    [
        None,
        3,
        ["claude/opus"],
        {"spec": "x"},
        "",
        "claude",
        "/opus:high",
        "claude/",
        "claude/ :x",
    ],
)
def test_what_is_not_an_agent_reads_back_as_none(said: object) -> None:
    assert read_back(said) is None

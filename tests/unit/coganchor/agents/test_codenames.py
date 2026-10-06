"""`hmz.coganchor.agents.codenames`: what an agent nobody named is called."""

from __future__ import annotations

import itertools
import random
import re
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.agents.codenames import (
    HEIRS,
    JOINED,
    JOINS,
    LOCKED,
    SAID,
    SIGNALS,
    STEMS,
    VISITORS,
    WORDS,
    codename,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

_RULED = re.compile(r"(?P<word>[A-Z][A-Za-z]+)(?P<number>\d{3})")


def _hangs(word: str) -> bool:
    """Whether a generated code's word is one the rule may make."""
    if word in {heir for heir, _ in HEIRS} or word in WORDS:
        return True
    return any(word.startswith(one) and word[len(one) :] in STEMS for one in JOINS) or (
        # a counted code is any number of joins and then a stem
        any(word.endswith(stem) for stem in STEMS)
    )


def test_the_canon_is_twenty_nine_whole_designations() -> None:
    assert len(SAID) == 29
    assert len(set(SAID)) == 29
    assert set(SAID) >= {"NeiKos496", "Golem99", "ScreW", *LOCKED, *SIGNALS, *VISITORS}
    assert JOINED >= 2
    assert len(JOINS) >= 2


def test_codenames_are_unique_and_well_formed() -> None:
    drawn = [codename() for _ in range(300)]
    assert len(set(drawn)) == len(drawn)
    for one in drawn:
        if one in SAID:
            continue
        ruled = _RULED.fullmatch(one)
        assert ruled is not None, one
        assert _hangs(ruled["word"]), one


def test_the_canon_half_draws_a_whole_designation_nobody_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    offered: list[list[Any]] = []
    choose = random.choice

    def recording(of: Sequence[Any]) -> Any:
        offered.append(list(of))
        return choose(of)

    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "choice", recording)
    drawn = codename()
    if set(offered[0]) <= set(SAID):
        assert drawn in offered[0]
        assert codename() != drawn
    else:
        # every designation is already out in this process: the role runs again under
        # another number, hung off an heir's word
        assert offered[0] == list(HEIRS)
        ruled = _RULED.fullmatch(drawn)
        assert ruled is not None
        assert ruled["word"] in {heir for heir, _ in HEIRS}


@pytest.mark.parametrize(
    ("rolls", "words"),
    [
        ([0.9, 0.0], [heir for heir, _ in HEIRS]),
        ([0.9, 0.9, 0.0], list(WORDS)),
        ([0.9, 0.9, 0.9], [join + stem for join in JOINS for stem in STEMS]),
    ],
)
def test_the_rule_half_hangs_three_digits_off_a_word(
    monkeypatch: pytest.MonkeyPatch, rolls: list[float], words: list[str]
) -> None:
    left = itertools.cycle(rolls)  # a draw already taken is drawn again the same way
    monkeypatch.setattr(random, "random", lambda: next(left))
    ruled = _RULED.fullmatch(codename())
    assert ruled is not None
    assert ruled["word"] in words


def test_an_unlucky_process_counts_its_way_to_a_free_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def first(of: Sequence[Any]) -> Any:
        return of[0]

    monkeypatch.setattr(random, "random", lambda: 0.9)
    monkeypatch.setattr(random, "choice", first)

    def seven(_: int) -> int:
        return 7

    monkeypatch.setattr(random, "randrange", seven)
    once = codename()  # the one draw luck can find, if nobody holds it yet
    drawn = {codename() for _ in range(5)}
    assert once not in drawn
    assert len(drawn) == 5
    for one in drawn:
        ruled = _RULED.fullmatch(one)
        assert ruled is not None
        assert any(ruled["word"].startswith(join) for join in JOINS)
        assert any(ruled["word"].endswith(stem) for stem in STEMS)

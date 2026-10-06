"""Where a turn goes when the place taking it cannot: each question handed to the file."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import fallbacks
from hmz.runtime import Fallbacks

if TYPE_CHECKING:
    from tests.unit.runtime.doubles_u12 import Stands


@pytest.mark.parametrize(
    ("method", "args", "name", "forwarded"),
    [
        ("all", (), "falls", ()),
        ("named", ("gentle",), "named", ("gentle",)),
        ("reads", ("claude/opus",), "reads", ("claude/opus",)),
        ("spec", ("claude", "opus"), "spec", ("claude", "opus", "")),
        ("spec", ("claude", "opus", "w"), "spec", ("claude", "opus", "w")),
        ("tried", ("claude/opus",), "tried", ("claude/opus",)),
        ("chain", ("claude/opus",), "chain", ("claude/opus",)),
        ("points", ("a", ["b", "c"]), "points", ("a", ["b", "c"])),
        ("retrying", ("a", 2, "gentle", 30.0), "retrying", ("a", 2, "gentle", 30.0)),
        ("clear", ("a",), "clear", ("a",)),
    ],
)
def test_each_question_is_answered_by_the_file(
    method: str,
    args: tuple[Any, ...],
    name: str,
    forwarded: tuple[Any, ...],
    stand: Stands,
) -> None:
    asked = stand(fallbacks, name)

    said = getattr(Fallbacks(), method)(*args)

    assert said is asked.returns
    assert asked.calls == [(forwarded, {})]


def test_the_waits_are_the_files_own(monkeypatch: pytest.MonkeyPatch) -> None:
    policies = (object(), object())
    monkeypatch.setattr(fallbacks, "DEFAULT", "u12-default")
    monkeypatch.setattr(fallbacks, "POLICIES", policies)

    assert Fallbacks().default == "u12-default"
    assert Fallbacks().policies() is policies

"""Every nous, as one object: each question handed to the file."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import nous
from hmz.runtime import NousBook

if TYPE_CHECKING:
    from tests.unit.runtime.doubles_u12 import Stands


@pytest.mark.parametrize(
    ("method", "args", "name", "forwarded"),
    [
        ("all", (), "every", ()),
        ("named", ("gentle",), "named", ("gentle",)),
        ("strategies", (), "strategies", ()),
        ("reads", ("claude/opus",), "reads", ("claude/opus",)),
        ("spec", ("claude", "opus"), "spec", ("claude", "opus", "", "")),
        (
            "spec",
            ("claude", "opus", "w", "high"),
            "spec",
            ("claude", "opus", "w", "high"),
        ),
        ("rule", ("claude/opus",), "rule", ("claude/opus",)),
        ("graph", (["a/b"],), "graph_of", (["a/b"],)),
        ("shown", (None,), "shown", (None,)),
        ("put", ("one",), "put", ("one",)),
        ("check", ("one",), "check", ("one", None)),
        ("checked", ("a", "g"), "checked", ("a", "g")),
        ("then", ("a", ["b", "c"]), "then", ("a", ["b", "c"])),
        ("retrying", ("a", 2, "gentle", 30.0), "retrying", ("a", 2, "gentle", 30.0)),
        ("renamed", ("a", "b"), "renamed", ("a", "b")),
        ("entry", ("a",), "entry", ("a",)),
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
    asked = stand(nous, name)

    said = getattr(NousBook(), method)(*args)

    assert said is asked.returns
    assert asked.calls == [(forwarded, {})]


def test_write_puts_a_whole_nous(stand: Stands) -> None:
    put = stand(nous, "put")
    stand(nous, "graph_of")

    NousBook().write("smart", tries=2, graph=["a/b"])

    (made,), _ = put.calls[0]
    assert (made.name, made.tries, made.policy) == ("smart", 2, nous.DEFAULT)


def test_the_waits_are_the_files_own(monkeypatch: pytest.MonkeyPatch) -> None:
    policies = (object(), object())
    monkeypatch.setattr(nous, "DEFAULT", "u12-default")
    monkeypatch.setattr(nous, "POLICIES", policies)

    assert NousBook().default == "u12-default"
    assert NousBook().policies() is policies
    assert NousBook().faults()[-1] == nous.ANY

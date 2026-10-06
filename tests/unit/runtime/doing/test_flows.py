"""The flows there are and the places they come from, each asked of the engine that knows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.runtime import Flows, Flowverses, flowing
from hmz.runtime.flowing import index, verses

if TYPE_CHECKING:
    from tests.unit.runtime.doubles_u12 import Stands


@dataclass
class Verse:
    name: str
    url: str = ""
    at: Path = Path("/verses/x")


ONE = cast("Any", Verse("theirs"))


@pytest.mark.parametrize(
    ("method", "args", "module", "name", "forwarded"),
    [
        ("all", (), verses, "flowverses", ()),
        ("nearest", (), verses, "nearest", ()),
        ("find", ("theirs",), verses, "named", ("theirs",)),
        ("add", ("o/r",), verses, "add", ("o/r", "")),
        ("add", ("o/r", "mine"), verses, "add", ("o/r", "mine")),
        ("fetch", ("theirs",), verses, "fetch", ("theirs",)),
        ("remove", ("theirs",), verses, "remove", ("theirs",)),
        ("holds", (ONE,), flowing, "offers", (ONE,)),
        ("index", ("theirs",), index, "index", ("theirs",)),
        ("install", ("aot",), index, "install", ("official", "aot", "")),
        (
            "install",
            ("@theirs/alice/k", "1.2"),
            index,
            "install",
            ("theirs", "alice/k", "1.2"),
        ),
        ("uninstall", ("@theirs/k",), index, "uninstall", ("theirs", "k")),
        ("installed", (), index, "installed", ()),
        ("updates", (), index, "updates", ()),
        ("edited", (ONE,), verses, "edited", (Path("/verses/x"),)),
        ("standing", (ONE,), verses, "standing", (Path("/verses/x"),)),
        ("where", ("theirs",), verses, "where", ("theirs",)),
        ("plain", ("https://u:p@h/r",), verses, "plain", ("https://u:p@h/r",)),
    ],
)
def test_each_question_about_the_places_is_asked_of_the_engine(
    method: str,
    args: tuple[Any, ...],
    module: object,
    name: str,
    forwarded: tuple[Any, ...],
    stand: Stands,
) -> None:
    asked = stand(module, name)

    said = getattr(Flowverses(), method)(*args)

    assert said is asked.returns
    assert asked.calls == [(forwarded, {})]


def test_a_name_that_is_no_flows_is_not_installed(stand: Stands) -> None:
    installed = stand(index, "install")

    with pytest.raises(ValueError, match="not a flow's name"):
        Flowverses().install("@theirs/a/b/c")
    assert installed.calls == []


def test_where_a_place_came_from_is_said_with_nothing_secret(stand: Stands) -> None:
    stand(verses, "plain", "https://h/repo")
    places = Flowverses()

    assert (
        places.whence(cast("Any", Verse("theirs", "https://t@h/repo")))
        == "https://h/repo"
    )
    assert places.whence(cast("Any", Verse("theirs"))) == "-"
    assert places.whence(cast("Any", Verse("theirs")), "nowhere") == "nowhere"
    assert places.whence(cast("Any", Verse(verses.LOCAL))) == (
        f"your own flows in {verses.MINE[verses.LOCAL]}"
    )
    assert places.whence(cast("Any", Verse(verses.USER, "x"))) == (
        f"your own flows in {verses.MINE[verses.USER]}"
    )


@pytest.mark.parametrize(
    ("method", "args", "name", "forwarded"),
    [
        ("all", (), "found", ()),
        ("find", ("aot",), "find", ("aot",)),
        ("about", ("aot",), "about", ("aot",)),
        ("fork", ("aot",), "fork", ("aot", None)),
        ("fork", ("aot", "into"), "fork", ("aot", "into")),
        ("running", (), "running", ()),
    ],
)
def test_each_question_about_the_flows_is_asked_of_the_engine(
    method: str,
    args: tuple[Any, ...],
    name: str,
    forwarded: tuple[Any, ...],
    stand: Stands,
) -> None:
    asked = stand(flowing, name)

    said = getattr(Flows(), method)(*args)

    assert said is asked.returns
    assert asked.calls == [(forwarded, {})]


@dataclass
class Declared:
    resumable: bool


@dataclass
class Impl:
    declared: Declared

    def describe(self) -> Declared:
        return self.declared


def test_what_a_flow_declares_is_read_off_it_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    named: list[str] = []

    def resolved(name: str) -> Impl:
        named.append(name)
        return Impl(Declared(resumable=name == "ralph"))

    monkeypatch.setattr(flowing, "resolved", resolved, raising=False)
    flows = Flows()

    assert flows.declared("aot") == Declared(resumable=False)
    assert flows.resumes("ralph") is True
    assert flows.resumes(Path("mine.py")) is False
    assert named == ["aot", "ralph", "./mine.py"]


def test_the_places_are_one_object_however_often_asked() -> None:
    flows = Flows()

    assert isinstance(flows.verses, Flowverses)
    assert flows.verses is flows.verses

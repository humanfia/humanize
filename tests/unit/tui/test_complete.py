"""`hmz.tui.complete`: what the editor offers to finish a command, a flow or a path with."""

from __future__ import annotations

import os
import types
from typing import TYPE_CHECKING

import pytest

import hmz.runtime.flowing
from hmz.tui import complete
from hmz.tui.complete import VIEWS, Command, hinted, offered, paths

if TYPE_CHECKING:
    from pathlib import Path


def _does(app: object, words: list[str]) -> None:
    """What running a command does, which nothing here runs."""


COMMANDS = (
    Command("flow", "choose a flow", _does),
    Command("flowverses", "the flowverses", _does),
    Command(
        "settings", "every setting", _does, offers=("accounts", "general", "runtimes")
    ),
    Command("stop", "stop the flow", _does),
)


@pytest.fixture(autouse=True)
def flows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    """The flows there are, as `hmz.runtime.flowing` would list them."""
    names = ["chat", "rlar", "rlar2", "review"]
    # A directory of the test's own, since a reading of the flows is kept per directory.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        hmz.runtime.flowing,
        "found",
        lambda: [types.SimpleNamespace(name=one) for one in names],
    )
    return names


def test_a_command_is_offered_in_every_view_by_default() -> None:
    one = Command("x", "about", _does)

    assert one.where == VIEWS == {"monitor", "aggregate", "session", "outworlder"}
    assert (one.takes, one.offers, one.refuses, one.unlisted, one.now) == (
        "",
        (),
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("/", ["/flow", "/flowverses", "/settings", "/stop"]),
        ("/s", ["/settings", "/stop"]),
        ("/fl", ["/flow", "/flowverses"]),
        ("/x", []),
        # Written out in full: nothing, so enter sends the line.
        ("/flow", []),
        ("/stop", []),
    ],
)
def test_a_slash_offers_the_commands_it_could_become(
    typed: str, expected: list[str]
) -> None:
    assert offered(typed, COMMANDS) == expected


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("/settings ", ["accounts", "general", "runtimes"]),
        ("/settings g", ["general"]),
        ("/settings general", []),
        ("/settings general more", []),
        ("/stop ", []),
        ("/nothing ", []),
    ],
)
def test_after_a_command_its_own_words_are_offered(
    typed: str, expected: list[str]
) -> None:
    assert offered(typed, COMMANDS) == expected


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("/flow ", ["chat", "review", "rlar", "rlar2"]),
        ("/flow r", ["review", "rlar", "rlar2"]),
        ("/flow rlar", []),
        ("/flow rlar2 more", []),
    ],
)
def test_flow_offers_the_flows(typed: str, expected: list[str]) -> None:
    assert sorted(offered(typed, COMMANDS)) == expected


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("$", ["$chat", "$review", "$rlar", "$rlar2"]),
        ("$rl", ["$rlar", "$rlar2"]),
        ("$rlar", []),
        ("$rlar fix the bug", []),
    ],
)
def test_a_dollar_offers_the_flows_under_the_sigil(
    typed: str, expected: list[str]
) -> None:
    assert sorted(offered(typed, COMMANDS)) == expected


@pytest.mark.parametrize("typed", ["$", "$r", "/flow ", "/flow r"])
def test_no_flow_is_offered_while_one_cannot_be_chosen(typed: str) -> None:
    assert offered(typed, COMMANDS, flows=False) == []


@pytest.mark.parametrize("typed", ["", "fix the bug", " /flow", "a $flow"])
def test_prose_is_offered_nothing(typed: str) -> None:
    assert offered(typed, COMMANDS) == []


def test_the_flows_are_read_once_for_a_moment_of_typing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads: list[None] = []

    def found() -> list[types.SimpleNamespace]:
        reads.append(None)
        return [types.SimpleNamespace(name="once")]

    monkeypatch.setattr(hmz.runtime.flowing, "found", found)
    # One moment of the clock, so that every keystroke here falls inside it.
    monkeypatch.setattr(complete, "time", types.SimpleNamespace(monotonic=lambda: 7.0))

    for typed in ("$", "$o", "$on"):
        assert offered(typed, COMMANDS) == ["$once"]

    assert len(reads) == 1


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("/stop", "stop"),
        ("/settings general", "settings"),
        ("/sto", ""),
        ("stop", ""),
        ("/", ""),
        ("$chat", ""),
    ],
)
def test_hinted_names_the_command_being_written(typed: str, expected: str) -> None:
    assert hinted(typed, COMMANDS) == expected


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "tree"
    (root / "src").mkdir(parents=True)
    (root / "specs").mkdir()
    (root / "setup.py").write_text("")
    (root / ".hidden").write_text("")
    (root / "README.md").write_text("")
    monkeypatch.chdir(root)
    return root


def test_a_path_is_finished_as_a_shell_would(tree: Path) -> None:
    assert paths("s") == ["setup.py", f"specs{os.sep}", f"src{os.sep}"]


def test_a_dot_file_is_offered_only_once_a_dot_is_typed(tree: Path) -> None:
    assert ".hidden" not in paths("")
    assert paths(".") == [".hidden"]


def test_a_path_keeps_the_directory_it_was_typed_under(tree: Path) -> None:
    (tree / "src" / "main.py").write_text("")

    assert paths(f"src{os.sep}m") == [f"src{os.sep}main.py"]


def test_an_absolute_path_is_finished_from_the_root(tree: Path) -> None:
    assert paths(f"{tree}{os.sep}R") == [f"{tree}{os.sep}README.md"]


def test_a_home_is_kept_as_a_tilde(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tree))

    assert paths("~") == [f"~{os.sep}"]
    assert paths(f"~{os.sep}R") == [f"~{os.sep}README.md"]


@pytest.mark.parametrize(
    "typed", ["~somebody", f"no-such-dir{os.sep}x", f"setup.py{os.sep}"]
)
def test_what_cannot_be_read_is_offered_nothing(tree: Path, typed: str) -> None:
    assert paths(typed) == []

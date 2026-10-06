"""`hmz.tui.history`: what was typed before, walked back and forth, kept per directory."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz import home
from hmz.tui.history import History

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def here(tmp_path: Path) -> Path:
    where = tmp_path / "project"
    where.mkdir()
    return where


def _file() -> Path:
    return home() / "history.jsonl"


def _rows() -> list[dict[str, str]]:
    return [json.loads(line) for line in _file().read_text().splitlines()]


def test_a_fresh_history_has_nothing_to_walk(here: Path) -> None:
    history = History(here)

    assert history.back("draft") is None
    assert history.forward() is None


def test_what_is_added_is_written_down_with_where_it_was_typed(here: Path) -> None:
    History(here).add("fix the bug")

    [row] = _rows()
    assert row["text"] == "fix the bug"
    assert row["workdir"] == str(here.resolve())
    assert row["at"].endswith("Z")


def test_walking_back_goes_newest_first_and_stops_at_the_oldest(here: Path) -> None:
    history = History(here)
    for said in ("one", "two", "three"):
        history.add(said)

    assert [history.back("draft") for _ in range(4)] == ["three", "two", "one", None]


def test_walking_forward_gives_the_draft_back_off_the_near_end(here: Path) -> None:
    history = History(here)
    history.add("one")
    history.add("two")

    assert history.back("half typed") == "two"
    assert history.back("two") == "one"
    assert history.forward() == "two"
    assert history.forward() == "half typed"
    assert history.forward() is None


def test_adding_ends_a_walk_under_way(here: Path) -> None:
    history = History(here)
    history.add("one")
    history.back("")
    history.add("two")

    assert history.forward() is None
    assert history.back("") == "two"


@pytest.mark.parametrize("said", ["", "   ", "\n"])
def test_nothing_said_is_not_kept(here: Path, said: str) -> None:
    history = History(here)
    history.add(said)

    assert history.back("") is None
    assert not _file().exists()


def test_a_repeat_of_the_last_line_is_kept_once(here: Path) -> None:
    history = History(here)
    history.add("again")
    history.add("again")

    assert len(_rows()) == 1
    assert history.back("") == "again"
    assert history.back("") is None


def test_a_line_said_before_something_else_is_kept_again(here: Path) -> None:
    history = History(here)
    for said in ("a", "b", "a"):
        history.add(said)

    assert [history.back("") for _ in range(3)] == ["a", "b", "a"]


def test_a_directory_walks_only_what_was_typed_in_it(
    here: Path, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    History(elsewhere).add("theirs")
    History(here).add("mine")

    history = History(here)

    assert history.back("") == "mine"
    assert history.back("") is None


def test_a_directory_with_nothing_typed_walks_everything(
    here: Path, tmp_path: Path
) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    History(first).add("from a")
    History(second).add("from b")

    history = History(here)

    assert [history.back("") for _ in range(3)] == ["from b", "from a", None]


def test_what_is_walked_is_settled_when_it_opens(here: Path) -> None:
    history = History(here)
    History(here).add("typed by another")

    assert history.back("") is None


def test_lines_that_are_not_rows_are_skipped(here: Path) -> None:
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(
        "\n".join(
            [
                "not json",
                json.dumps(["a", "list"]),
                json.dumps({"workdir": str(here.resolve()), "text": 3}),
                json.dumps({"workdir": str(here.resolve()), "text": "kept"}),
                '{"half": ',
            ]
        )
    )

    history = History(here)

    assert history.back("") == "kept"
    assert history.back("") is None


def test_a_row_naming_no_directory_is_everyone_elses(here: Path) -> None:
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(json.dumps({"text": "from nowhere"}) + "\n")

    assert History(here).back("") == "from nowhere"


def test_a_history_nobody_can_write_still_walks_what_was_said(
    here: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blocked = tmp_path / "a-file"
    blocked.write_text("")
    monkeypatch.setenv("HUMANIZE_HOME", str(blocked / "home"))
    history = History(here)

    history.add("still here")

    assert history.back("") == "still here"


def test_the_workspace_defaults_to_this_directory(
    here: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(here)
    History().add("from cwd")

    assert _rows()[0]["workdir"] == str(here.resolve())

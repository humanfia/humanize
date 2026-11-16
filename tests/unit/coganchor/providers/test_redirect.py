from __future__ import annotations

from pathlib import Path

import pytest

from hmz.coganchor import binary
from hmz.coganchor.providers.redirect import Swaps, command


def test_an_empty_table_points_nothing_anywhere() -> None:
    assert not Swaps.of([])
    assert Swaps.of([]).swap("/home/me/.codex/auth.json") is None


def test_a_table_is_tidied_and_longest_first() -> None:
    held = Swaps.of([("/a/", "/x"), ("/a//b/c", "/y/./z"), ("", "/n"), ("/m", "")])

    assert held.pairs == (("/a/b/c", "/y/z"), ("/a", "/x"))


@pytest.mark.parametrize(
    ("path", "answer"),
    [
        ("/h/.codex/auth.json", "/p/auth.json"),
        ("/h/.codex/auth.json.tmp", "/p/auth.json.tmp"),
        ("/h/.codex/auth.jsonx", None),
        ("/h/.kimi/creds/one", "/p/creds/one"),
        ("/h/.kimi/creds", "/p/creds"),
        ("/h/.kimi/credsx", None),
        ("/elsewhere", None),
    ],
)
def test_a_file_a_directory_and_a_rotated_file_are_answered(
    path: str, answer: str | None
) -> None:
    held = Swaps.of(
        [("/h/.codex/auth.json", "/p/auth.json"), ("/h/.kimi/creds", "/p/creds")]
    )

    assert held.swap(path) == answer


def test_a_pattern_answers_every_path_its_names_match() -> None:
    held = Swaps.of([("/h/state_*.sqlite", "/p/state_*.sqlite")])

    assert held.swap("/h/state_5.sqlite") == "/p/state_5.sqlite"
    assert held.swap("/h/state_5.sqlite/wal") == "/p/state_5.sqlite/wal"
    assert held.swap("/h/other.sqlite") is None


def test_the_entry_that_says_most_about_a_path_wins_across_both_tables() -> None:
    held = Swaps.of(
        [("/h/.claude", "/p/creds")], kept=[("/h/.claude/projects", "/s/projects")]
    )

    assert held.answer("/h/.claude/projects/a.jsonl") == ("/s/projects/a.jsonl", True)
    assert held.answer("/h/.claude/.credentials.json") == (
        "/p/creds/.credentials.json",
        False,
    )
    assert held.answer("/nowhere") is None


def test_a_table_holding_only_sessions_still_points_somewhere() -> None:
    assert Swaps.of([], kept=[("/a", "/b")])


def test_nothing_to_point_anywhere_runs_the_command_as_it_is() -> None:
    assert command([], ["codex", "exec"]) == ["codex", "exec"]


def test_the_supervisor_is_coganchor_with_every_swap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(binary, "here", lambda: Path("/opt/coganchor"))

    said = command([("/a", "/b")], ["codex"], kept=[("/s", "/t")])

    assert said == [
        "/opt/coganchor",
        "internal",
        "cred",
        "--map=/a=/b",
        "--keep=/s=/t",
        "--",
        "codex",
    ]
    assert command([], ["codex"]) == ["codex"]

from __future__ import annotations

import os
import sys

import pytest

from hmz.coganchor.providers.redirect import Swaps, command, failed, read


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


def test_swaps_named_on_a_command_line_are_read_back() -> None:
    held = read(["/a=/b", "/c/d=/e"], ["/s=/t"])

    assert held == Swaps.of([("/a", "/b"), ("/c/d", "/e")], [("/s", "/t")])


@pytest.mark.parametrize("said", ["/a", "a=/b", "/a=b", "=/b"])
def test_a_swap_that_is_not_two_absolute_paths_is_refused(said: str) -> None:
    with pytest.raises(ValueError, match="not FROM=TO"):
        read([said])


def test_nothing_to_point_anywhere_runs_the_command_as_it_is() -> None:
    assert command([], ["codex", "exec"]) == ["codex", "exec"]


def test_the_command_runs_the_supervisor_with_every_swap() -> None:
    said = command([("/a", "/b")], ["codex", "exec"], kept=[("/s", "/t")])

    assert said == [
        sys.executable,
        "-Pm",
        "hmz",
        "internal",
        "cred",
        "--map=/a=/b",
        "--keep=/s=/t",
        "--",
        "codex",
        "exec",
    ]


@pytest.mark.skipif(not hasattr(os, "WIFEXITED"), reason="POSIX wait statuses")
@pytest.mark.parametrize(
    ("status", "code"),
    [(0, 0), (3 << 8, 3), (9, 128 + 9), (15, 128 + 15)],
)
def test_a_wait_status_comes_to_an_exit_status(status: int, code: int) -> None:
    assert failed(status) == code

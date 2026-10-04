"""A file written whole, by many writers at once, is always one of theirs and never half."""

from __future__ import annotations

import json
import multiprocessing
import os
import stat
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import atomic

if TYPE_CHECKING:
    from pathlib import Path

#: How many processes write at once, and how many times each.
WRITERS = 8
ROUNDS = 200


def test_many_writers_at_once_leave_a_whole_file_and_nothing_beside_it(
    tmp_path: Path,
) -> None:
    at = tmp_path / "settings.yaml"
    atomic.writes(at, "{}\n")
    spawning = multiprocessing.get_context("spawn")
    workers = [
        spawning.Process(target=_writes, args=(str(at), n)) for n in range(WRITERS)
    ]
    seen = 0
    try:
        for one in workers:
            one.start()
        while any(one.is_alive() for one in workers):
            # Every reading is some writer's whole file, never half of one or none at all.
            said = json.loads(at.read_text(encoding="utf-8"))
            assert said == {} or said["pad"] == "x" * 4096
            seen += 1
        for one in workers:
            one.join()
    finally:
        for one in workers:
            one.kill()
    assert [one.exitcode for one in workers] == [0] * WRITERS
    assert seen
    assert json.loads(at.read_text(encoding="utf-8"))["round"] == ROUNDS - 1
    assert [one.name for one in tmp_path.iterdir()] == ["settings.yaml"]


def _writes(at: str, n: int) -> None:
    """One process's writes, each a file big enough to be caught half-written."""
    from pathlib import Path

    for r in range(ROUNDS):
        atomic.writes(
            Path(at), json.dumps({"writer": n, "round": r, "pad": "x" * 4096}) + "\n"
        )


def test_the_mode_a_file_has_is_the_mode_it_keeps(tmp_path: Path) -> None:
    at = tmp_path / "models.json"
    at.write_text("{}\n", encoding="utf-8")
    at.chmod(0o640)

    atomic.writes(at, "[]\n")

    assert stat.S_IMODE(at.stat().st_mode) == 0o640
    assert at.read_text(encoding="utf-8") == "[]\n"


def test_a_new_file_gets_what_the_umask_leaves(tmp_path: Path) -> None:
    was = os.umask(0o027)
    try:
        atomic.writes(tmp_path / "daemon.json", b"{}\n")
    finally:
        os.umask(was)

    assert stat.S_IMODE((tmp_path / "daemon.json").stat().st_mode) == 0o640


def test_a_mode_asked_for_is_the_mode_it_has(tmp_path: Path) -> None:
    at = tmp_path / "provider.json"
    at.write_text("{}\n", encoding="utf-8")
    at.chmod(0o644)

    atomic.writes(at, "{}\n", mode=0o600)

    assert stat.S_IMODE(at.stat().st_mode) == 0o600


def test_a_write_that_fails_leaves_nothing_beside_it(tmp_path: Path) -> None:
    at = tmp_path / "gone" / "settings.yaml"
    with pytest.raises(FileNotFoundError):
        atomic.writes(at, "{}\n")
    at.parent.mkdir()
    (at.parent / "settings.yaml").mkdir()  # a directory where the file is to go

    with pytest.raises(OSError, match="directory"):
        atomic.writes(at, "{}\n")

    assert [one.name for one in at.parent.iterdir()] == ["settings.yaml"]

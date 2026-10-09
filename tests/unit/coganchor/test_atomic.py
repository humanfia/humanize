"""Writing a file whole: what it holds after, its mode, and nothing left beside it on failure.

And making one only one writer may make: whole, or not at all where one is there already.
"""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.atomic import creates, writes

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path


@pytest.fixture
def umask() -> Iterator[int]:
    """A known umask for the test, put back after."""
    was = os.umask(0o022)
    try:
        yield 0o022
    finally:
        os.umask(was)


def listed(directory: Path) -> list[str]:
    return sorted(one.name for one in directory.iterdir())


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.mark.parametrize(
    ("said", "held"),
    [
        ("text — in UTF-8", "text — in UTF-8".encode()),
        (b"\x00bytes\xff", b"\x00bytes\xff"),
        ([b"one ", b"piece ", b"at a time"], b"one piece at a time"),
        (iter([b"a", b"b"]), b"ab"),
        ("", b""),
    ],
)
def test_writes_holds_what_was_given(
    tmp_path: Path, said: str | bytes | Iterable[bytes], held: bytes
) -> None:
    at = tmp_path / "file"

    writes(at, said)

    assert at.read_bytes() == held
    assert listed(tmp_path) == ["file"]


def test_writes_replaces_what_was_there(tmp_path: Path) -> None:
    at = tmp_path / "file"
    at.write_text("old and longer")

    writes(at, "new")

    assert at.read_text() == "new"


def test_a_new_file_gets_what_the_umask_leaves(tmp_path: Path, umask: int) -> None:
    at = tmp_path / "file"

    writes(at, "x")

    assert mode(at) == 0o666 & ~umask


def test_a_file_keeps_its_own_mode(tmp_path: Path, umask: int) -> None:
    at = tmp_path / "file"
    at.write_text("x")
    at.chmod(0o604)

    writes(at, "y")

    assert mode(at) == 0o604


@pytest.mark.parametrize("asked", [0o600, 0o640, 0o777])
def test_a_mode_given_is_had_exactly(tmp_path: Path, umask: int, asked: int) -> None:
    at = tmp_path / "file"
    at.write_text("x")
    at.chmod(0o644)

    writes(at, "y", mode=asked)

    assert mode(at) == asked


def test_a_failure_leaves_the_old_file_and_nothing_beside_it(tmp_path: Path) -> None:
    at = tmp_path / "file"
    at.write_text("old")

    def pieces() -> Iterator[bytes]:
        yield b"half"
        raise RuntimeError("stopped")

    with pytest.raises(RuntimeError, match="stopped"):
        writes(at, pieces())

    assert at.read_text() == "old"
    assert listed(tmp_path) == ["file"]


def test_a_missing_directory_is_an_os_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        writes(tmp_path / "missing" / "file", "x")

    assert listed(tmp_path) == []


def test_creates_makes_a_file_whole_with_the_mode_given(
    tmp_path: Path, umask: int
) -> None:
    made, given = tmp_path / "made", tmp_path / "given"

    creates(made, [b"one ", b"piece"])
    creates(given, "x", mode=0o640)

    assert made.read_bytes() == b"one piece"
    assert (mode(made), mode(given)) == (0o666 & ~umask, 0o640)
    assert listed(tmp_path) == ["given", "made"]


def test_creates_leaves_a_file_already_there_as_it_was(tmp_path: Path) -> None:
    at = tmp_path / "file"
    at.write_text("first")
    at.chmod(0o600)

    with pytest.raises(FileExistsError):
        creates(at, "second", mode=0o644)

    assert (at.read_text(), mode(at)) == ("first", 0o600)
    assert listed(tmp_path) == ["file"]


def test_creates_that_failed_leaves_nothing(tmp_path: Path) -> None:
    def pieces() -> Iterator[bytes]:
        yield b"half"
        raise RuntimeError("stopped")

    with pytest.raises(RuntimeError, match="stopped"):
        creates(tmp_path / "file", pieces())

    assert listed(tmp_path) == []

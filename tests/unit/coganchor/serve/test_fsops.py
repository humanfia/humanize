"""Filesystem operations, each named by a virtual path and carried out under `tmp_path`."""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.proto import CHUNK_SIZE
from hmz.coganchor.serve import fsops
from hmz.coganchor.serve.exports import ExportTable
from tests.unit.coganchor.doubles_u8 import names

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def real(tmp_path: Path) -> Path:
    root = tmp_path / "real"
    root.mkdir()
    (root / "f.txt").write_bytes(b"hello")
    (root / "d").mkdir()
    (root / "link").symlink_to("f.txt")
    return root


@pytest.fixture
def table(real: Path) -> ExportTable:
    return ExportTable.parse([f"/w:{real}"], insensitive=False)


def test_a_file_is_described_by_kind_mode_size_and_time(real: Path) -> None:
    said = fsops.describe(str(real / "f.txt"), name="f.txt")
    info = (real / "f.txt").lstat()
    assert said == {
        "kind": "file",
        "mode": info.st_mode,
        "size": 5,
        "mtime_ns": info.st_mtime_ns,
        "name": "f.txt",
    }


def test_a_link_is_described_with_what_it_names(real: Path) -> None:
    said = fsops.describe(str(real / "link"))
    assert said["kind"] == "link"
    assert said["target"] == "f.txt"
    assert "name" not in said


def test_a_directory_is_listed_whole(table: ExportTable) -> None:
    listing = fsops.listdir(table, "/w")
    kinds = {one["name"]: one["kind"] for one in listing["entries"]}
    assert kinds == {"f.txt": "file", "d": "dir", "link": "link"}
    assert stat.S_ISDIR(listing["mode"])


def test_stat_resolves_through_the_table(table: ExportTable) -> None:
    assert fsops.stat(table, "/w/d")["kind"] == "dir"


def test_a_file_is_read_in_bounded_chunks(table: ExportTable, real: Path) -> None:
    (real / "big").write_bytes(b"x" * (CHUNK_SIZE * 2 + 1))
    chunks: list[bytes] = []
    said = fsops.read(table, "/w/big", chunks.append)
    assert [len(one) for one in chunks] == [CHUNK_SIZE, CHUNK_SIZE, 1]
    assert said["size"] == CHUNK_SIZE * 2 + 1


def test_a_write_lands_whole_and_keeps_the_old_mode(
    table: ExportTable, real: Path
) -> None:
    (real / "f.txt").chmod(0o640)
    writer = fsops.FileWriter(table, "/w/f.txt", None)
    writer.feed(b"new ")
    writer.feed(b"bytes")
    assert (real / "f.txt").read_bytes() == b"hello"
    said = writer.finish()
    assert (real / "f.txt").read_bytes() == b"new bytes"
    assert stat.S_IMODE((real / "f.txt").stat().st_mode) == 0o640
    assert said["size"] == 9
    assert names(real) == ["d", "f.txt", "link"]


def test_a_write_makes_its_directories_and_takes_the_mode_it_is_given(
    table: ExportTable, real: Path
) -> None:
    writer = fsops.FileWriter(table, "/w/new/deep/f", 0o100600)
    writer.feed(b"x")
    writer.finish()
    assert stat.S_IMODE((real / "new" / "deep" / "f").stat().st_mode) == 0o600


def test_a_write_through_a_link_replaces_what_it_names(
    table: ExportTable, real: Path
) -> None:
    writer = fsops.FileWriter(table, "/w/link", None)
    writer.feed(b"via")
    writer.finish()
    assert (real / "link").is_symlink()
    assert (real / "f.txt").read_bytes() == b"via"


def test_an_aborted_write_leaves_nothing_behind(table: ExportTable, real: Path) -> None:
    writer = fsops.FileWriter(table, "/w/f.txt", None)
    writer.feed(b"half")
    writer.abort()
    assert (real / "f.txt").read_bytes() == b"hello"
    assert names(real) == ["d", "f.txt", "link"]


def test_a_write_that_cannot_land_cleans_up(table: ExportTable, real: Path) -> None:
    writer = fsops.FileWriter(table, "/w/later", None)
    writer.feed(b"x")
    (real / "later").mkdir()
    with pytest.raises(IsADirectoryError):
        writer.finish()
    assert names(real) == ["d", "f.txt", "later", "link"]


def test_directories_are_made_and_removed(table: ExportTable, real: Path) -> None:
    assert fsops.mkdir(table, "/w/a", 0o755, parents=False) == {}
    fsops.mkdir(table, "/w/b/c/d", 0o755, parents=True)
    fsops.mkdir(table, "/w/b/c/d", 0o755, parents=True)
    with pytest.raises(FileExistsError):
        fsops.mkdir(table, "/w/a", 0o755, parents=False)
    with pytest.raises(FileNotFoundError):
        fsops.mkdir(table, "/w/x/y", 0o755, parents=False)
    assert (real / "b" / "c" / "d").is_dir()
    fsops.rmdir(table, "/w/a")
    assert not (real / "a").exists()
    with pytest.raises(OSError, match="not empty"):
        fsops.rmdir(table, "/w/b")


def test_a_file_is_unlinked(table: ExportTable, real: Path) -> None:
    fsops.unlink(table, "/w/f.txt")
    assert not (real / "f.txt").exists()
    with pytest.raises(FileNotFoundError):
        fsops.unlink(table, "/w/f.txt")


def test_a_rename_replaces_unless_told_not_to(table: ExportTable, real: Path) -> None:
    (real / "g.txt").write_bytes(b"g")
    fsops.rename(table, "/w/g.txt", "/w/f.txt", replace=True)
    assert (real / "f.txt").read_bytes() == b"g"
    fsops.rename(table, "/w/f.txt", "/w/h.txt", replace=False)
    assert (real / "h.txt").read_bytes() == b"g"


def test_links_are_made_and_read(table: ExportTable, real: Path) -> None:
    fsops.symlink(table, "../outside", "/w/sym")
    assert fsops.readlink(table, "/w/sym") == {"target": "../outside"}
    fsops.link(table, "/w/f.txt", "/w/hard")
    assert (real / "hard").stat().st_ino == (real / "f.txt").stat().st_ino


def test_mode_size_and_times_are_set(table: ExportTable, real: Path) -> None:
    fsops.chmod(table, "/w/f.txt", 0o100604)
    assert stat.S_IMODE((real / "f.txt").stat().st_mode) == 0o604
    fsops.truncate(table, "/w/f.txt", 2)
    assert (real / "f.txt").read_bytes() == b"he"
    fsops.utime(table, "/w/f.txt", 1_000_000_000, 2_000_000_000)
    info = (real / "f.txt").stat()
    assert (info.st_atime_ns, info.st_mtime_ns) == (1_000_000_000, 2_000_000_000)
    fsops.utime(table, "/w/f.txt", None, 3_000_000_000)
    info = (real / "f.txt").stat()
    assert (info.st_atime_ns, info.st_mtime_ns) == (1_000_000_000, 3_000_000_000)
    fsops.utime(table, "/w/f.txt", None, None)
    assert (real / "f.txt").stat().st_mtime_ns > 3_000_000_000


def test_nothing_outside_the_exports_is_touched(
    table: ExportTable, tmp_path: Path
) -> None:
    (tmp_path / "secret").write_bytes(b"no")
    with pytest.raises(PermissionError):
        fsops.stat(table, str(tmp_path / "secret"))
    with pytest.raises(PermissionError):
        fsops.unlink(table, "/w/../secret")
    assert (tmp_path / "secret").exists()

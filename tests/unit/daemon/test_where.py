"""`hmz.daemon.where`: the daemon's directory, and what is written down in it."""

from __future__ import annotations

import errno
import os
import re
import stat
from pathlib import Path

import pytest

from hmz.daemon import where


def test_the_names_in_the_directory_are_distinct_files() -> None:
    names = {where.SOCKET, where.RECORD, where.LOG, where.LOCK}
    assert len(names) == 4
    assert all("/" not in one for one in names)


def test_at_is_a_private_directory_of_this_users() -> None:
    found = where.at()
    assert found.is_dir()
    assert found.stat().st_uid == os.getuid()
    assert stat.S_IMODE(found.stat().st_mode) & 0o077 == 0
    assert where.at() == found


def test_workspace_follows_every_link(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)
    assert where.workspace(tmp_path / "link") == str(real.resolve())
    assert where.workspace(str(tmp_path / "real" / ".." / "real")) == str(
        real.resolve()
    )


def test_workspace_defaults_to_where_this_is_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert where.workspace() == str(tmp_path.resolve())
    assert where.workspace(None) == where.workspace("")


def test_reached_names_a_short_socket_by_its_whole_path() -> None:
    short = Path("short")
    with where.reached(short) as reaching:
        assert reaching == str(short / where.SOCKET)


def test_reached_stands_in_a_long_directory_and_goes_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    deep = tmp_path / ("d" * 60) / ("e" * 60)
    deep.mkdir(parents=True)
    with where.reached(deep) as reaching:
        assert reaching == where.SOCKET
        assert Path.cwd() == deep.resolve()
    assert Path.cwd() == tmp_path.resolve()


def test_reached_goes_back_even_when_the_block_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    deep = tmp_path / ("d" * 120)
    deep.mkdir()
    with pytest.raises(RuntimeError), where.reached(deep):
        raise RuntimeError
    assert Path.cwd() == tmp_path.resolve()


def test_reached_writes_down_a_directory_it_could_not_go_back_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    deep = tmp_path / ("d" * 120)
    deep.mkdir()
    with where.reached(deep):
        gone.rmdir()
    assert "could not go back" in (deep / where.LOG).read_text()


def test_holds_takes_the_lock_once(tmp_path: Path) -> None:
    held = where.holds(tmp_path)
    try:
        assert (tmp_path / where.LOCK).exists()
        with pytest.raises(BlockingIOError):
            where.holds(tmp_path)
    finally:
        os.close(held)
    os.close(where.holds(tmp_path))


def test_holds_raises_where_the_file_cannot_be_made(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        where.holds(tmp_path / "missing")


def test_wrote_then_held_reads_back_the_record(tmp_path: Path) -> None:
    said = {"pid": os.getpid(), "started": "2026-01-01T00:00:00Z", "protocol": 2}
    where.wrote(tmp_path, said)
    assert where.held(tmp_path) == said
    assert stat.S_IMODE((tmp_path / where.RECORD).stat().st_mode) == 0o600
    assert [one.name for one in tmp_path.iterdir()] == [where.RECORD]


def test_wrote_replaces_the_record_whole(tmp_path: Path) -> None:
    where.wrote(tmp_path, {"pid": os.getpid(), "n": 1})
    where.wrote(tmp_path, {"pid": os.getpid(), "n": 2})
    assert where.held(tmp_path)["n"] == 2


def test_wrote_leaves_nothing_behind_when_it_fails(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        where.wrote(tmp_path, {"pid": object()})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "written",
    [
        None,
        "not json",
        "[1, 2]",
        '{"started": "x"}',
        '{"pid": "1"}',
        '{"pid": 0}',
        '{"pid": -5}',
    ],
)
def test_held_is_nothing_for_a_record_naming_no_live_process(
    tmp_path: Path, written: str | None
) -> None:
    if written is not None:
        (tmp_path / where.RECORD).write_text(written)
    assert where.held(tmp_path) == {}


def test_held_is_nothing_for_a_record_that_cannot_be_decoded(tmp_path: Path) -> None:
    (tmp_path / where.RECORD).write_bytes(b"\xff\xfe")
    assert where.held(tmp_path) == {}


def test_now_is_utc_to_the_second() -> None:
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", where.now())


@pytest.mark.parametrize(("pid", "expected"), [(0, False), (-1, False)])
def test_alive_is_false_for_no_process(pid: int, expected: bool) -> None:
    assert where.alive(pid) is expected


def test_alive_is_true_for_this_process() -> None:
    assert where.alive(os.getpid()) is True


@pytest.mark.parametrize(
    ("errno_", "expected"),
    [(errno.EPERM, True), (errno.ESRCH, False)],
    ids=["EPERM", "ESRCH"],
)
def test_alive_counts_a_process_somebody_else_owns(
    monkeypatch: pytest.MonkeyPatch, errno_: int, expected: bool
) -> None:
    def refuses(pid: int, signal: int) -> None:
        raise OSError(errno_, os.strerror(errno_))

    monkeypatch.setattr(os, "kill", refuses)
    assert where.alive(12345) is expected

"""What a path being typed could become: directories only, spelled as they were typed."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.web.paths import completed

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_a_path_becomes_the_directories_it_starts(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "albums").mkdir()
    (tmp_path / "also.txt").write_text("")
    (tmp_path / ".hidden").mkdir()

    assert completed(f"{tmp_path}/al") == [f"{tmp_path}/albums/", f"{tmp_path}/alpha/"]
    assert completed(f"{tmp_path}/") == [f"{tmp_path}/albums/", f"{tmp_path}/alpha/"]
    assert completed(f"{tmp_path}/.h") == [f"{tmp_path}/.hidden/"]


def test_a_home_is_kept_as_it_was_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "work").mkdir()

    assert completed("~/w") == ["~/work/"]
    assert completed("") == ["~/work/"]


def test_a_path_under_nothing_becomes_nothing(tmp_path: Path) -> None:
    assert completed(f"{tmp_path}/missing/x") == []

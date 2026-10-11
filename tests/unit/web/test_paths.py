"""What a path being typed could become: directories only, spelled as they were typed."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.web.paths import completed, listed
from hmz.web.routing import Refusal

if TYPE_CHECKING:
    from pathlib import Path


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


def test_a_directory_lists_its_folders_first_and_its_files_where_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "b-folder").mkdir()
    (tmp_path / "A-folder").mkdir()
    (tmp_path / "a-file").write_text("")
    (tmp_path / ".hidden").mkdir()

    folders = listed("~", files=False, hidden=False)
    assert (folders["at"], folders["up"]) == ("~", str(tmp_path.parent.resolve()))
    assert [one["name"] for one in folders["entries"]] == ["A-folder", "b-folder"]
    everything = listed("", files=True, hidden=True)
    assert [(one["name"], one["dir"]) for one in everything["entries"]] == [
        (".hidden", True),
        ("A-folder", True),
        ("b-folder", True),
        ("a-file", False),
    ]
    assert listed("~/A-folder", files=False, hidden=False)["up"] == "~"


def test_a_directory_that_is_not_there_is_refused(tmp_path: Path) -> None:
    with pytest.raises(Refusal):
        listed(str(tmp_path / "missing"), files=False, hidden=False)

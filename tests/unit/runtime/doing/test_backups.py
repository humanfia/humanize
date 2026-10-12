"""The backup targets, and an epic backed up to them by hand, with the backing stood in for."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime import backing
from hmz.runtime.doing.backups import Backups
from hmz.runtime.epic import BACKED, Epic, note, read
from hmz.runtime.settings import Target

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

LAB = Target("lab", "/lab")
HOME = Target("home", "/home")


@pytest.fixture
def pushed(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    held: list[tuple[Any, ...]] = []
    monkeypatch.setattr(backing, "configured", lambda: ((LAB, HOME), ("lab",)))

    def push(epic: Path, names: Iterable[str], why: str) -> None:
        held.append((epic, tuple(names), why))

    monkeypatch.setattr(backing, "push", push)
    return held


def _epic(tmp_path: Path, backup: tuple[str, ...] = ()) -> Path:
    with Epic("ralph", "fix it", tmp_path, backup=backup) as one:
        pass
    return one.path


def test_the_targets_and_defaults_are_settings(pushed: list[tuple[Any, ...]]) -> None:
    assert Backups().targets() == (LAB, HOME)
    assert Backups().defaults() == ("lab",)


def test_an_epic_goes_to_the_targets_named(
    pushed: list[tuple[Any, ...]], tmp_path: Path
) -> None:
    at = _epic(tmp_path, ("lab",))

    assert Backups().push(at, ["home"]) == ("home",)
    assert pushed == [(at, ("home",), "manual")]


def test_an_epic_goes_where_it_was_started_to_else_to_the_defaults(
    pushed: list[tuple[Any, ...]], tmp_path: Path
) -> None:
    started = _epic(tmp_path, ("home",))
    nowhere = _epic(tmp_path)
    ran = read(started)
    assert ran is not None

    assert Backups().push(ran) == ("home",)
    assert Backups().push(nowhere) == ("lab",)
    assert pushed == [(started, ("home",), "manual"), (nowhere, ("lab",), "manual")]


def test_a_target_there_is_none_of_is_refused(
    pushed: list[tuple[Any, ...]], tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="no backup target is named x"):
        Backups().push(_epic(tmp_path), ["x"])
    assert pushed == []


def test_how_each_backup_went_is_read_off_the_epic_as_it_is_now(
    pushed: list[tuple[Any, ...]], tmp_path: Path
) -> None:
    at = _epic(tmp_path)
    ran = read(at)
    assert ran is not None
    note(at, BACKED, to="lab", ok=True, error="", why="end")

    state = Backups().state(ran)

    assert set(state) == {"lab"}
    assert state["lab"]["ok"] is True
    assert Backups().state(tmp_path / "nothing") == {}


def test_where_and_waiting_are_the_backings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def where(epic: Path) -> str:
        return f"m/{epic.name}"

    def wait(seconds: float | None = None) -> bool:
        return seconds == 3

    monkeypatch.setattr(backing, "where", where)
    monkeypatch.setattr(backing, "wait", wait)

    assert Backups().where(tmp_path / "e") == "m/e"
    assert Backups().wait(3) is True


def test_listing_and_pulling_are_the_backings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    held = backing.Stored("m/w/e", "m", "/w", "e", "ralph", "t", "", "", "", "")

    def listed(name: str) -> list[backing.Stored]:
        return [held] if name == "lab" else []

    def pulled(name: str, key: str) -> Path:
        return tmp_path / name / key

    monkeypatch.setattr(backing, "listed", listed)
    monkeypatch.setattr(backing, "pulled", pulled)

    assert Backups().listed("lab") == [held]
    assert Backups().pulled("lab", "m/w/e") == tmp_path / "lab" / "m/w/e"

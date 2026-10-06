"""`hmz.tui.pick.exported`: one run's trace gathered beside it, and the run packed up."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest

import hmz.daemon
from hmz.runtime.epic import TRACES
from hmz.tui import pick
from tests.unit.tui import doubles_u14 as doubles

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.runtime.epic import Ran


class _Ran:
    def __init__(self, at: Path) -> None:
        self.at = at


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> doubles.Hmz:
    held = doubles.Hmz()
    monkeypatch.setattr(hmz.daemon, "Hmz", held)
    return held


def _export(tmp_path: Path) -> tuple[Path, int, str]:
    return pick.exported(cast("Ran", _Ran(tmp_path / "run")), str(tmp_path))


def test_exported_traces_beside_the_run_then_packs_it(
    store: doubles.Hmz, tmp_path: Path
) -> None:
    run = tmp_path / "run"

    landed, size, _ = _export(tmp_path)

    assert store.epics.calls == [
        ("traced", run, run / TRACES / pick.EXPORTED),
        ("bundled", run, str(tmp_path)),
    ]
    assert landed == tmp_path / "run.tar.gz"
    assert size == len(store.epics.archive)


@pytest.mark.parametrize(
    ("other", "held"),
    [
        ({"sessions": "1", "slices": "1"}, "1 session, 1 slice"),
        ({"sessions": "2", "slices": "40"}, "2 sessions, 40 slices"),
        ({}, "0 sessions, 0 slices"),
        ({"sessions": "x", "slices": None}, "0 sessions, 0 slices"),
        ({"sessions": 3, "slices": 1, "programs": "0"}, "3 sessions, 1 slice"),
        (
            {"sessions": 1, "slices": 2, "programs": "1"},
            "1 session, 2 slices, 1 program",
        ),
        (
            {"sessions": 1, "slices": 2, "programs": 5},
            "1 session, 2 slices, 5 programs",
        ),
    ],
)
def test_exported_says_what_the_trace_holds(
    store: doubles.Hmz, tmp_path: Path, other: dict[str, Any], held: str
) -> None:
    store.epics.other = other

    assert _export(tmp_path)[2] == held

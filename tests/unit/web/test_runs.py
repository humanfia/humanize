"""`hmz.web.runs`: the runs written down here, as the pages list them, sum them and draw them."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.web.runs import held_by, sessions_of, spending

if TYPE_CHECKING:
    from hmz.runtime.epic import Ran

#: Today, as the tests see it.
_NOW = datetime.datetime(2026, 10, 8, 12, 0, tzinfo=datetime.UTC)


@dataclass(frozen=True)
class _Ran:
    """As much of a run written down as these read."""

    flow: str = "ralph"
    task: str = "fix it"
    began: str = "2026-10-08T10:00:00+00:00"
    ended: str = ""
    how: str = ""
    spent: dict[str, Any] | None = None


def _runs(*runs: _Ran) -> list[Ran]:
    return cast("list[Ran]", list(runs))


def test_spending_counts_each_day_and_flow_and_how_each_run_ended() -> None:
    said = spending(
        _runs(
            _Ran(how="done", spent={"cost": 1.5, "output_tokens": 300, "seconds": 60}),
            _Ran(
                flow="goal",
                began="2026-10-07T23:59:00+00:00",
                how="failed",
                spent={"cost": 2.0, "output_tokens": 100, "seconds": 30},
            ),
            # Still going: a run, and nothing spent yet.
            _Ran(began="2026-10-08T11:00:00+00:00"),
            # Before the days asked about.
            _Ran(began="2026-10-01T10:00:00+00:00", how="done", spent={"cost": 9.0}),
            _Ran(began="not a moment", how="done", spent={"cost": 9.0}),
        ),
        days=2,
        now=_NOW,
    )

    assert [(one["day"], one["runs"], one["cost"]) for one in said["days"]] == [
        ("2026-10-07", 1, 2.0),
        ("2026-10-08", 2, 1.5),
    ]
    assert [(one["flow"], one["runs"]) for one in said["flows"]] == [
        ("goal", 1),  # the costliest first
        ("ralph", 2),
    ]
    assert said["ended"] == {"done": 1, "failed": 1, "unfinished": 1}
    whole = said["whole"]
    assert (whole["runs"], whole["cost"], whole["output_tokens"]) == (3, 3.5, 400)
    assert whole["seconds"] == 90.0


@pytest.mark.parametrize(
    ("standing", "found"),
    [
        ({"state": "running", "flow": "ralph", "task": "fix it", "at": 0.0}, 1),
        ({"state": "stopping", "flow": "ralph", "task": "fix it", "at": 60.0}, 1),
        ({"state": "running", "flow": "ralph", "task": "fix it", "at": 600.0}, None),
        ({"state": "running", "flow": "ralph", "task": "other", "at": 0.0}, None),
        ({"state": "running", "flow": "goal", "task": "fix it", "at": 0.0}, None),
        ({"state": "idle", "flow": "ralph", "task": "fix it", "at": 0.0}, None),
        (None, None),
    ],
)
def test_the_run_going_is_the_one_opened_for_it_as_it_started(
    standing: dict[str, Any] | None, found: int | None
) -> None:
    began = datetime.datetime.fromtimestamp(0, datetime.UTC).isoformat()
    runs = _runs(
        _Ran(began=began, ended=began, how="done"),  # over, so not the one going
        _Ran(began=began),
    )

    held = held_by(runs, standing)

    assert held is (runs[found] if found is not None else None)


def test_a_trace_is_read_as_each_sessions_actions_in_the_order_they_happened() -> None:
    document: dict[str, Any] = {
        "traceEvents": [
            {"ph": "M", "name": "process_name", "pid": 7, "args": {"name": "builder"}},
            {"ph": "X", "cat": "session", "pid": 7, "ts": 0, "dur": 9e6},
            {
                "ph": "X",
                "cat": "tool",
                "name": "Bash",
                "pid": 7,
                "ts": 3e6,
                "dur": 1e6,
                "args": {"session": "claude:s1", "at": "t3", "command": "ls"},
            },
            {
                "ph": "X",
                "cat": "turn",
                "name": "turn 1",
                "pid": 7,
                "ts": 1e6,
                "dur": 5e6,
                "args": {"session": "claude:s1"},
            },
            {
                "ph": "X",
                "cat": "turn",
                "name": "turn 1",
                "pid": 8,
                "ts": 2e6,
                "dur": 1e6,
                "args": {"session": "codex:s2"},
            },
            {"ph": "X", "cat": "turn", "pid": 7, "ts": 0, "dur": 1, "args": {}},
        ]
    }

    sessions = sessions_of(document)

    assert [(one["key"], one["agent"]) for one in sessions] == [
        ("claude:s1", "builder"),
        ("codex:s2", ""),
    ]
    first = sessions[0]["actions"]
    assert [(one["category"], one["start"], one["seconds"]) for one in first] == [
        ("turn", 1.0, 5.0),
        ("tool", 3.0, 1.0),
    ]
    assert first[1]["at"] == "t3"
    assert first[1]["args"] == {"command": "ls"}

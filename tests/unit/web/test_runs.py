"""`hmz.web.runs`: the runs written down here, as the pages list them, sum them and draw them."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.web.runs import held_by, refused, row, sessions_of, spending

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
    workspace: str = "/work/one"
    at: str = ""
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
        # Asked of the daemon, a host says which flow and nothing of the task or when.
        ({"state": "running", "flow": "ralph"}, 1),
        (None, None),
    ],
)
def test_the_run_going_is_the_one_opened_for_it_as_it_started(
    standing: dict[str, Any] | None, found: int | None
) -> None:
    began = datetime.datetime.fromtimestamp(0, datetime.UTC).isoformat()
    runs = _runs(
        _Ran(
            began=began, ended=began, how="done", at="over"
        ),  # over, so not the one going
        _Ran(began=began, at="going"),
        # The same flow on the same task, going in another workspace: that one's, not this.
        _Ran(began=began, at="elsewhere", workspace="/work/two"),
    )
    running = {} if standing is None else {"/work/one": standing}

    held = held_by(runs, running)

    assert set(held) == ({runs[found].at} if found is not None else set())


@pytest.mark.parametrize("turn", ["running", "done", ""])
def test_the_run_going_carries_where_a_chat_is_in_its_turn(turn: str) -> None:
    runs = _runs(_Ran(flow="chat", at="going"))
    standing = {"state": "running", "flow": "chat"} | ({"turn": turn} if turn else {})

    assert held_by(runs, {"/work/one": standing}) == {"going": turn}


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


@pytest.mark.parametrize(
    ("said", "status", "named"),
    [
        (
            "20261012T1015Z-ab12 is already here, at /h/epics/-w/20261012T1015Z-ab12",
            409,
            "20261012T1015Z-ab12",
        ),
        ("an epic is already here, at /h/epics/-w/an epic", 409, "an epic"),
        ("a is already here, at /h/epics/-w/b", 400, None),
        ("x.hmzepic is not a bundle humanize can read: not a gzip file", 400, None),
        ("x.txt is not a .hmzepic file", 400, None),
    ],
)
def test_an_import_refused_is_a_conflict_naming_the_epic_only_where_it_is_here(
    said: str, status: int, named: str | None
) -> None:
    refusal = refused(ValueError(said))

    assert refusal.status == status
    assert str(refusal) == f"{said}."
    assert refusal.said.get("name") == named


@dataclass(frozen=True)
class _Row:
    """As much of a run written down as a row of the list reads."""

    how: str = ""
    name: str = "20261012T135159.936Z-bc3e81"
    workspace: str = "/work/one"
    flow: str = "ralph"
    task: str = "fix it"
    began: str = "2026-10-08T10:00:00+00:00"
    ended: str = ""
    agents: tuple[Any, ...] = ()
    sessions: tuple[Any, ...] = ()
    resumable: bool = False
    spent: dict[str, Any] | None = None
    backup: tuple[str, ...] = ()
    backed: dict[str, Any] | None = None


@pytest.mark.parametrize(
    ("how", "held", "going", "said"),
    [
        ("", True, True, "running"),
        # Held by a process no host speaks for -- `hmz exec` -- and going all the same.
        ("", False, True, "running"),
        ("", False, False, "unfinished"),
        ("done", False, False, "done"),
    ],
)
def test_a_run_is_said_running_while_any_process_holds_it(
    how: str, held: bool, going: bool, said: str
) -> None:
    ran = cast("Ran", _Row(how=how))

    listed = row(ran, held=held, going=going)

    assert listed["how"] == said
    assert listed["held"] is held


@pytest.mark.parametrize(
    ("how", "held", "going", "turn", "said"),
    [
        # The agent is answering.
        ("", True, True, "running", "running"),
        # Between turns: the turn is done, though the chat goes on.
        ("", True, True, "done", "done"),
        # Going where no host says where its turn is.
        ("", False, True, "", "running"),
        # Over: however it was ended but failing, it is done.
        ("", False, False, "", "done"),
        ("stopped", False, False, "", "done"),
        ("done", False, False, "", "done"),
        ("failed", False, False, "", "failed"),
        ("crashed", False, False, "", "crashed"),
    ],
)
def test_a_chat_is_said_running_only_while_its_agent_answers(
    how: str, held: bool, going: bool, turn: str, said: str
) -> None:
    ran = cast("Ran", _Row(flow="chat", how=how))

    assert row(ran, held=held, going=going, turn=turn)["how"] == said


@dataclass(frozen=True)
class _Drove:
    """As much of an agent a run wrote down as a row reads."""

    agent: str
    name: str
    spec: str = "claude/opus"


def test_a_run_lists_each_agent_by_its_own_name_and_the_role_it_filled_beside() -> None:
    # One written before an agent had a name of its own went by its role.
    ran = _Row(agents=(_Drove("builder", "NeiKos496"), _Drove("critic", "")))

    listed = row(cast("Ran", ran), held=False)

    assert [(one["name"], one["role"]) for one in listed["agents"]] == [
        ("NeiKos496", "builder"),
        ("critic", "critic"),
    ]

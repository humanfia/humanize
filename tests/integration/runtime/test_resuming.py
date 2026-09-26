"""A flow that says it can be picked up where a run of it left off.

A loop meant to run for a week is a loop that will be stopped and started: a machine goes
down, somebody presses esc, a turn takes the process with it. What such a flow needs is not a
second copy of the transcript -- the backends keep that -- but the handful of things it is
itself keeping track of: which round it is on, which files it has been through, what it has
decided so far. So a flow says it is `resumable`, keeps those in `ctx.state`, and the engine
writes them into a journal inside the run's own epic as it writes them.

`--resume` -- `resume=True` here -- picks up the newest run of that flow in this workspace that
got as far as writing anything down; without it every run starts from the top. The run that
picks one up is a run of its own, in an epic of its own, handed a copy of the journal it picks
up and saying which run that came from.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.runtime.epic import RESUME, epics, picks_up, read, resumed, state
from hmz.runtime.runner import Refused, Runner
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

#: A flow that counts the runs of it, and fails on the run it is told to.
COUNTS = '''"""Counts the runs of itself."""

from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow


class Params(FlowParams):
    fail: bool = False


@flow(agents=AgentCollection, envs=EnvCollection, params=Params, resumable=True)
async def counts(task, *, agents, envs, params, ctx):
    ctx.state["runs"] = (ctx.state["runs"] if "runs" in ctx.state else 0) + 1
    ctx.state["resumed"] = ctx.resumed
    if params.fail:
        raise RuntimeError("stopped halfway")
    return ctx.state["runs"]


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams, resumable=True)
async def calls(task, *, agents, envs, params, ctx):
    ctx.state["mine"] = "outer"
    return await inner(task, agents={}, envs={}, params=FlowParams())


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams, resumable=True)
async def inner(task, *, agents, envs, params, ctx):
    ctx.state["seen"] = (ctx.state["seen"] if "seen" in ctx.state else 0) + 1
    return ctx.state["seen"]


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def once(task, *, agents, envs, params, ctx):
    return ctx.state
'''

#: What every run here may spend, which is nothing it will reach.
BUDGET = {"cost": 1}


@pytest.fixture
def counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """The flow above, written into this project's own flows; its name."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path / ".humanize" / "flows", "counts", COUNTS)
    return "counts"


def _run(named: str, *, resume: bool | Path = False, fail: bool = False) -> object:
    return Runner(
        named,
        params={"fail": fail} if named == "counts" else None,
        budget=BUDGET,
        resume=resume,
    ).run("go")


def test_a_resumable_flow_is_handed_what_the_run_it_picks_up_left(counts: str) -> None:
    assert _run(counts) == 1
    assert _run(counts, resume=True) == 2
    assert _run(counts, resume=True) == 3

    newest = epics()[-1]
    assert state(newest) == {"runs": 3, "resumed": True}
    assert picks_up(newest)


def test_without_resume_every_run_starts_from_the_top(counts: str) -> None:
    """Picking a run up is asked for; a run that was not asked to is a run of its own."""
    assert _run(counts) == 1
    assert _run(counts) == 1

    assert [state(one) for one in epics()] == [
        {"runs": 1, "resumed": False},
        {"runs": 1, "resumed": False},
    ]


def test_a_run_says_which_run_it_was_picked_up_from(counts: str) -> None:
    _run(counts)
    first = epics()[-1]

    _run(counts, resume=True)

    ran = read(epics()[-1])
    assert ran is not None
    assert ran.picked_up == first.name
    assert ran.resumable
    # And the run picked up keeps what it wrote: a closed epic is never reopened.
    assert state(first) == {"runs": 1, "resumed": False}


def test_a_run_picked_up_from_a_named_epic_takes_that_one_s_journal(
    counts: str,
) -> None:
    _run(counts)
    first = epics()[-1]
    _run(counts, resume=True)
    _run(counts, resume=True)

    assert _run(counts, resume=first) == 2


def test_what_a_run_that_failed_kept_is_there_to_be_picked_up(counts: str) -> None:
    """A state write is flushed as it is made, so a run that died still wrote it."""
    with pytest.raises(RuntimeError, match="halfway"):
        _run(counts, fail=True)

    failed = epics()[-1]
    assert (failed / RESUME).is_file()
    assert resumed("counts:counts") == failed
    assert _run(counts, resume=True) == 2


def test_the_newest_run_that_can_be_picked_up_is_the_one_picked_up(
    counts: str,
) -> None:
    """Not a run of another flow, and not one that was not resumable."""
    _run(counts)
    wanted = epics()[-1]
    _run("counts:once")
    _run("counts:calls")

    assert resumed("counts:counts") == wanted
    assert resumed("counts") == wanted  # as it was named, as well as by its ref
    assert resumed("counts:once") is None


def test_a_called_flow_keeps_its_own_state_under_its_own_name(counts: str) -> None:
    """A resumable run picks up every call it made that is made the same way again."""
    assert _run("counts:calls") == 1
    assert _run("counts:calls", resume=True) == 2

    newest = epics()[-1]
    assert state(newest) == {"mine": "outer"}
    assert state(newest, "counts:inner") == {"seen": 2}


def test_a_flow_that_is_not_resumable_is_not_picked_up(counts: str) -> None:
    with pytest.raises(Refused, match="does not say it can be picked up"):
        Runner("counts:once", budget=BUDGET, resume=True)


def test_a_run_with_nothing_to_pick_up_says_so(counts: str) -> None:
    with pytest.raises(Refused, match="no run here to pick up"):
        Runner("counts", budget=BUDGET, resume=True)


def test_a_flow_that_is_not_resumable_keeps_no_journal_and_no_state(
    counts: str,
) -> None:
    assert _run("counts:once") is None

    (epic,) = epics()
    assert not (epic / RESUME).exists()
    assert not picks_up(epic)

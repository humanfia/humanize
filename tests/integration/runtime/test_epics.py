"""One run of one flow, written down: what each role was given, and what each of them opened.

Nothing else knows that a session was part of a run. The backends log them one at a time, each
under an id of its own, and say nothing about whose they were, which account took their turns
or what they were for -- so a trace of a run can only be gathered afterwards if the run itself
wrote down what it opened, and a person can only find the logs of one if the run points at
them.

The agents here are the engine's fakes, where only what a run writes down is asked about, and
the stand-in `claude` of :mod:`tests.recording`, where what a session is called and where its
log is are: a real process and nothing more, no coding agent CLI, no network, nothing CI has
not got. The one thing that needs more -- what an epic says about the account a session's turns
were taken as, which is a supervised turn and so a kernel that will hand over a tracee -- is in
`tests/system/runtime/test_epics.py`.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.agents import AgentConfig
from hmz.flows import CostExceeded
from hmz.runtime.epic import (
    JOURNAL,
    called,
    epics,
    linked,
    opened,
    read,
    sessions,
    tree,
)
from hmz.runtime.flowing.fakes import FakeAgentDriver
from hmz.runtime.runner import Runner
from tests.recording import AGENT, ONE, TASK, logged, standing_in
from tests.stubs import ShellAgent, events, written

if TYPE_CHECKING:
    from pathlib import Path

#: A flow that opens one session per role, each of which answers once.
FLOW = """
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    actor: Agent
    reviewer: Agent


class Envs(EnvCollection):
    here: LocalEnv


class Params(FlowParams):
    rounds: int = 1


@flow(agents=Agents, envs=Envs, params=Params)
async def flow_(task, *, agents, envs, params, ctx):
    for role in ("actor", "reviewer"):
        session = await agents[role].spawn(env=envs["here"])
        await agents[role].run(task, session=session)
"""

#: A flow that raises, with nothing opened.
RAISES = """
from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def raises(task, *, agents, envs, params, ctx):
    raise RuntimeError(task)
"""

#: A flow that waits for as long as it is let, which is what a stop is tried on.
WAITS = """
import asyncio

from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def waits(task, *, agents, envs, params, ctx):
    await asyncio.sleep(60)
"""

#: A loop with no exit of its own, which is what a budget stops.
LOOPS = """
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    builder: Agent


class Envs(EnvCollection):
    here: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def loops(task, *, agents, envs, params, ctx):
    session = await agents["builder"].spawn(env=envs["here"])
    while True:
        await agents["builder"].run(task, session=session)
"""

#: Flows calling flows: two branches at once, one of which goes a level deeper.
TREE = """
import asyncio

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    builder: Agent


class Envs(EnvCollection):
    here: LocalEnv


class Deep(FlowParams):
    depth: int = 0


@flow(agents=Agents, envs=Envs, params=Deep)
async def branch(task, *, agents, envs, params, ctx):
    session = await agents["builder"].spawn(env=envs["here"])
    await agents["builder"].run(task, session=session)
    if params.depth:
        await branch(task, agents=agents, envs=envs, params=Deep(depth=params.depth - 1))


@flow(agents=Agents, envs=Envs, params=FlowParams, name="flow")
async def tree(task, *, agents, envs, params, ctx):
    await asyncio.gather(
        branch("left", agents=agents, envs=envs, params=Deep(depth=1)),
        branch("right", agents=agents, envs=envs, params=Deep()),
    )
"""

#: What every run here may spend.
BUDGET = {"cost": 5}


def _lines(epic: Path) -> list[dict[str, Any]]:
    """Every event of one epic, in the order it was written."""
    return events(epic)


def _run(tmp_path: Path, source: str, task: str = "go", **agents: object) -> Runner:
    """A flow written into the test's own directory, handed fakes by role."""
    written(tmp_path, "flow", source)
    return Runner(tmp_path / "flow", agents=agents, budget=BUDGET)  # pyright: ignore[reportArgumentType]


def test_a_run_is_one_epic_and_says_what_it_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole of it: what was run, what each role was given, and every session of it."""
    monkeypatch.chdir(tmp_path)

    _run(
        tmp_path,
        FLOW,
        actor=FakeAgentDriver(model="m", effort="high"),
        reviewer=FakeAgentDriver("codex", model="n", provider="work"),
    ).run("go")

    (epic,) = epics()
    began, *held, usage, ended = _lines(epic)
    assert began["flow"] == str(tmp_path / "flow")
    assert began["ref"] == "flow:flow_"
    assert began["task"] == "go"
    assert began["workspace"] == str(tmp_path.resolve())
    assert began["agents"] == [
        {
            "agent": "actor",
            "backend": "claude",
            "model": "m",
            "effort": "high",
            "provider": "",
        },
        {
            "agent": "reviewer",
            "backend": "codex",
            "model": "n",
            "effort": "auto",
            "provider": "work",
        },
    ]
    assert began["params"] == {"rounds": 1}
    assert began["budget"] == {
        "duration": None,
        "cost": 5.0,
        "output_tokens": None,
        "graceful": True,
    }
    assert [(said["agent"], said["backend"], said["provider"]) for said in held] == [
        ("actor", "claude", "local"),
        ("reviewer", "codex", "work"),
    ]
    assert usage["event"] == "usage"
    assert usage["output_tokens"] == 2
    assert ended == {"event": "ended", "at": ended["at"], "how": "done"}
    # And what a trace is gathered by: whose each of those sessions was.
    assert set(opened(epic)) == {"actor", "reviewer"}


def test_a_second_run_is_a_second_epic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An epic is a run and not a workspace: running the flow again is another run."""
    monkeypatch.chdir(tmp_path)

    for _ in range(2):
        _run(tmp_path, FLOW, actor=FakeAgentDriver(), reviewer=FakeAgentDriver()).run(
            "go"
        )

    assert len(epics()) == 2


def test_a_run_that_was_stopped_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stop ends a flow, and an epic that ended that way is not one that finished."""
    from hmz.runtime.doing.running import Run

    monkeypatch.chdir(tmp_path)
    run = Run(_run(tmp_path, WAITS), "go")

    run.start()
    while run.epic is None:
        run.wait(0.05)
    run.stop()

    assert run.wait(10)
    assert isinstance(run.raised, asyncio.CancelledError)
    (epic,) = epics()
    assert _lines(epic)[-1]["how"] == "stopped"


def test_a_run_its_budget_stopped_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A loop with no exit of its own ends when its budget is spent, which is not a failure."""
    monkeypatch.chdir(tmp_path)

    with pytest.raises(CostExceeded):
        _run(tmp_path, LOOPS, builder=FakeAgentDriver(cost=2.0)).run("go")

    (epic,) = epics()
    assert _lines(epic)[-1]["how"] == "stopped"
    assert _lines(epic)[-2]["cost"] == 6.0


def test_a_run_that_failed_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What a flow raises takes the run with it, and the epic says how it went."""
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match="nope"):
        _run(tmp_path, RAISES).run("nope")

    (epic,) = epics()
    assert _lines(epic)[-1]["how"] == "failed"


def test_the_epics_of_one_workspace_are_not_another_workspace_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """They are kept under the workspace they ran in, which is what looks them up."""
    here, there = tmp_path / "here", tmp_path / "there"
    for where in (here, there):
        where.mkdir()
    monkeypatch.chdir(here)
    _run(here, FLOW, actor=FakeAgentDriver(), reviewer=FakeAgentDriver()).run("go")

    assert len(epics(here)) == 1
    assert epics(there) == []


def test_an_agent_driven_by_hand_is_not_a_run_of_anything(tmp_path: Path) -> None:
    """A session opened outside a flow belongs to no epic, and writes to none."""
    agent = ShellAgent(AgentConfig(model="m", effort="high"))

    agent.new()("echo alone")

    assert agent.opened == ["alone"]
    assert epics(tmp_path) == []


def test_a_session_is_named_for_whose_it_is_what_ran_it_and_which_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The id alone says none of that, and a directory of ids is one nobody can read."""
    standing_in(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)

    Runner(tmp_path / "flow", agents={"builder": AGENT}, budget=BUDGET).run(TASK)

    (epic,) = epics()
    (one,) = sessions(epic)
    # The last of those is the record it was opened in, which for the run's own flow is the
    # run's own record.
    assert one == (
        "builder",
        "claude",
        "local",
        one.ident,
        f"builder-claude@local-{one.ident}",
        one.at,
        str(tmp_path / "flow"),
        "",  # forked from nothing, which is what a session nobody branched is
        JOURNAL,
    )
    assert one.name == called("builder", "claude", "", one.ident)


def test_the_logs_of_a_session_are_linked_into_the_epic_that_opened_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A link rather than a copy: humanize reads and writes the log where the backend keeps it."""
    config = standing_in(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)

    Runner(tmp_path / "flow", agents={"builder": AGENT}, budget=BUDGET).run(TASK)

    (epic,) = epics()
    (one,) = sessions(epic)
    log = logged(config, tmp_path.resolve(), one.ident)
    link = epic / "sessions" / one.name / log.name
    assert link.is_symlink()
    assert link.resolve() == log.resolve()
    assert linked(epic) == {one.name: [str(log)]}


def test_a_log_written_after_the_last_turn_is_linked_when_the_run_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sub-agent's transcript is written whenever that sub-agent ran, which is later."""
    config = standing_in(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOGS_UNDER", str(config / "projects"))
    # Written after the session was opened, which is when a sub-agent's transcript is
    # written: the flow stands in for the backend finishing what it was writing.
    written(
        tmp_path,
        "flow",
        ONE.replace(
            '    return await agents["builder"].run(task, session=session)\n',
            '    said = await agents["builder"].run(task, session=session)\n'
            "    import os, pathlib\n"
            '    (log,) = pathlib.Path(os.environ["LOGS_UNDER"]).glob("*/*.jsonl")\n'
            '    late = log.with_suffix("") / "subagents" / "deep" / "explore.jsonl"\n'
            "    late.parent.mkdir(parents=True)\n"
            '    late.write_text("{}\\n")\n'
            "    return said\n",
        ),
    )

    Runner(tmp_path / "flow", agents={"builder": AGENT}, budget=BUDGET).run(TASK)

    (epic,) = epics()
    (one,) = sessions(epic)
    assert sorted(p.name for p in (epic / "sessions" / one.name).iterdir()) == sorted(
        ["explore.jsonl", f"{one.ident}.jsonl"]
    )


def test_a_epic_reads_back_as_what_was_run_and_how_it_went(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is what a listing of them shows, and what one of them can be picked up from."""
    monkeypatch.chdir(tmp_path)

    _run(tmp_path, FLOW, actor=FakeAgentDriver(), reviewer=FakeAgentDriver()).run("go")

    (epic,) = epics()
    ran = read(epic)
    assert ran is not None
    assert (ran.flow, ran.ref, ran.task, ran.how) == (
        str(tmp_path / "flow"),
        "flow:flow_",
        "go",
        "done",
    )
    assert ran.workspace == str(tmp_path.resolve())
    assert ran.name == epic.name
    assert not ran.resumable
    assert [one.agent for one in ran.agents] == ["actor", "reviewer"]
    assert [one.agent for one in ran.sessions] == ["actor", "reviewer"]
    assert ran.params == {"rounds": 1}
    assert ran.budget is not None
    assert ran.budget["cost"] == 5.0


def test_flows_calling_flows_read_back_as_the_tree_they_ran_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each call a record of its own under the one that made it, each session in its own.

    Two branches at once, one of them a level deeper: read as a list it would be three things
    one run did, and nothing would say which of them ran under which.
    """
    monkeypatch.chdir(tmp_path)

    _run(tmp_path, TREE, builder=FakeAgentDriver()).run("go")

    (epic,) = epics()
    calls = tree(epic)
    assert sorted((one.flow, len(one.calls), one.how) for one in calls) == [
        ("flow:branch", 0, "done"),
        ("flow:branch", 1, "done"),
    ]
    (deeper,) = [one for one in calls if one.calls]
    assert [(one.flow, one.how) for one in deeper.calls] == [("flow:branch", "done")]
    # Every session in the record of the call that opened it, and none in the run's own.
    records = {one.record for one in sessions(epic)}
    assert JOURNAL not in records
    assert len(records) == 3


def test_a_run_written_before_calls_had_records_still_reads_as_what_it_called(
    tmp_path: Path,
) -> None:
    """An epic is read where it was written, and older runs were written differently."""
    at = tmp_path / "epic"
    at.mkdir()
    lines: tuple[dict[str, Any], ...] = (
        {"event": "began", "at": "1", "flow": "outer", "task": "go", "agents": []},
        {"event": "called", "at": "2", "flow": "a", "task": "one"},
        {"event": "called", "at": "3", "flow": "b", "task": "two"},
        {"event": "returned", "at": "4", "flow": "b"},
        {"event": "returned", "at": "5", "flow": "a"},
        {"event": "called", "at": "6", "flow": "a", "task": "three"},
        {"event": "ended", "at": "7", "how": "stopped"},
    )
    (at / JOURNAL).write_text(
        "\n".join(json.dumps(one) for one in lines), encoding="utf-8"
    )

    ran = read(at)
    assert ran is not None
    # Three calls and not two: a run that says only which flow is read by taking a return
    # for the last call of that flow still open, which is what nesting is.
    assert [(one.flow, one.task, one.ended) for one in ran.called] == [
        ("a", "one", "5"),
        ("b", "two", "4"),
        ("a", "three", ""),
    ]


def test_a_directory_that_holds_no_run_is_not_one(tmp_path: Path) -> None:
    """An epic is what this wrote; anything else under there is somebody else's directory."""
    (tmp_path / "not-a-epic").mkdir()

    assert read(tmp_path / "not-a-epic") is None

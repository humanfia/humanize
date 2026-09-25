"""What writes a run down as the engine runs it, and what it holds on to while it does.

A run is written into its epic call by call and session by session, and what the run has spent
is read off the recorder while it goes -- so the recorder is with the run for as long as the
run is, which for a loop meant to go for a week is every session that loop ever opened. It
holds the ones still open and a total of the rest, and nothing more.
"""

from __future__ import annotations

import sys
from typing import cast

import pytest

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    HarnessKind,
    LocalEnv,
    flow,
)
from hmz.runtime.epic import Epic, sessions, tree
from hmz.runtime.flowing.fakes import FakeAgentDriver, run_fake
from hmz.runtime.runner import Recorder


class Solo(AgentCollection):
    agent: Agent


class Here(EnvCollection):
    here: LocalEnv


class Rounds(FlowParams):
    rounds: int = 1


#: How many sessions the long loop opens.
SESSIONS = 10_000


@flow(agents=Solo, envs=Here, params=Rounds)
async def rounds(
    task: str, *, agents: Solo, envs: Here, params: Rounds, ctx: FlowContext
) -> None:
    for _ in range(params.rounds):
        session = await agents["agent"].spawn(env=envs["here"])
        await agents["agent"].run(task, session=session)


@flow(agents=Solo, envs=Here, params=Rounds)
async def calls(
    task: str, *, agents: Solo, envs: Here, params: Rounds, ctx: FlowContext
) -> None:
    await rounds(f"{task}, once", agents=agents, envs=envs, params=Rounds())


def _held_by(recorder: Recorder) -> int:
    """The bytes the recorder's own attributes and containers take, in bytes.

    Into its dicts, lists, tuples and sets and no further: an epic or a session it holds is
    counted as the one object it holds, not as everything that object holds in turn.
    """
    seen: set[int] = set()
    reach: list[object] = [*vars(recorder).values()]
    total = sys.getsizeof(recorder)
    while reach:
        one = reach.pop()
        if id(one) in seen:
            continue
        seen.add(id(one))
        total += sys.getsizeof(one)
        if isinstance(one, dict):
            reach.extend(cast("dict[object, object]", one).keys())
            reach.extend(cast("dict[object, object]", one).values())
        elif isinstance(one, list | tuple | set):
            reach.extend(cast("list[object]", one))
    return total


async def test_a_loop_of_ten_thousand_sessions_leaves_the_recorder_holding_none() -> (
    None
):
    """Each session let go of as it closes, what it spent kept as a sum."""
    epic = Epic("rounds", "go")
    recorder = Recorder(epic)
    open_at: list[int] = []
    grown: list[int] = []

    @flow(agents=Solo, envs=Here, params=Rounds)
    async def watched(
        task: str, *, agents: Solo, envs: Here, params: Rounds, ctx: FlowContext
    ) -> None:
        agent = agents["agent"]
        for n in range(params.rounds):
            session = await agent.spawn(env=envs["here"])
            await agent.run(task, session=session)
            open_at.append(len(recorder.sessions))
            if n in (SESSIONS // 10, SESSIONS - 1):
                grown.append(_held_by(recorder))

    # An ACP agent, whose sessions nobody logs: the epic has nothing to link each one to.
    driver = FakeAgentDriver(HarnessKind.ACP, cost=0.001, output_tokens=3)
    with epic:
        await run_fake(
            watched,
            "go",
            agents={"agent": driver},
            params={"rounds": SESSIONS},
            recorder=recorder,
        )

    assert max(open_at) <= 2, "the recorder held sessions that had closed"
    assert recorder.sessions == ()
    early, late = grown
    assert late - early < 1024, f"{late - early} bytes more after 9,000 more sessions"
    spent = recorder.usage()
    assert spent.output_tokens == 3 * SESSIONS
    assert spent.cost == pytest.approx(0.001 * SESSIONS)


async def test_what_a_run_spent_counts_its_open_sessions_and_its_closed_ones() -> None:
    """Read while a session is open, and again once it has closed: the same sum."""
    epic = Epic("rounds", "go")
    recorder = Recorder(epic)
    seen: list[tuple[int, int]] = []

    @flow(agents=Solo, envs=Here, params=Rounds)
    async def spends(
        task: str, *, agents: Solo, envs: Here, params: Rounds, ctx: FlowContext
    ) -> None:
        agent = agents["agent"]
        first = await agent.spawn(env=envs["here"])
        await agent.run(task, session=first)
        del first
        kept = await agent.spawn(env=envs["here"])
        await agent.run(task, session=kept)
        seen.append((len(recorder.sessions), recorder.usage().output_tokens))

    with epic:
        await run_fake(
            spends,
            "go",
            agents={"agent": FakeAgentDriver(output_tokens=5)},
            recorder=recorder,
        )

    assert seen == [(1, 10)]
    assert recorder.sessions == ()
    assert recorder.usage().output_tokens == 10


async def test_a_session_named_late_is_written_down_by_its_name() -> None:
    """Once its CLI has named it, rather than as it opened with a name it did not have."""
    epic = Epic("rounds", "go")
    driver = FakeAgentDriver(names_late=True)
    with epic:
        await run_fake(rounds, "go", agents={"agent": driver}, recorder=Recorder(epic))

    (session,) = sessions(epic.path)
    assert session.ident == driver.sessions[0].id


async def test_what_a_run_spent_is_what_its_budget_was_held_to() -> None:
    """The engine's own reckoning, which a session closed mid-turn goes on adding to."""
    epic = Epic("rounds", "go")
    recorder = Recorder(epic)
    reckoned: list[int] = []

    @flow(agents=Solo, envs=Here, params=Rounds)
    async def spends(
        task: str, *, agents: Solo, envs: Here, params: Rounds, ctx: FlowContext
    ) -> None:
        await rounds(task, agents=agents, envs=envs, params=Rounds(rounds=3))
        reckoned.append(ctx.usage.output_tokens)

    with epic:
        await run_fake(
            spends,
            "go",
            agents={"agent": FakeAgentDriver(output_tokens=7)},
            recorder=recorder,
        )

    assert reckoned == [21]
    assert recorder.finished().output_tokens == 21
    assert recorder.usage().output_tokens == 21


async def test_a_flow_called_is_written_down_with_the_task_it_was_called_with() -> None:
    epic = Epic("calls", "go")
    with epic:
        await run_fake(calls, "go", recorder=Recorder(epic))

    (one,) = tree(epic.path)
    assert (one.flow.rpartition(":")[2], one.task, one.how) == (
        "rounds",
        "go, once",
        "done",
    )

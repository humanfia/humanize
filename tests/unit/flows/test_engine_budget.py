"""What a run may spend: budgets inherited and tightened, usage rolled up, deadlines kept.

A flow's budget is the tighter of its own and what remains of every budget above it. Cost and
tokens spent anywhere count against every flow above, as they are reported; `duration` is a
deadline, not a sum, so concurrent children do not add up to it. Once a budget is spent it
stays spent: every later turn under it raises again.
"""

from __future__ import annotations

import asyncio
import datetime
import math
import time
from typing import Any

import pytest

from hmz.flows import (
    Agent,
    AgentCollection,
    Budget,
    BudgetExceeded,
    CostExceeded,
    DurationExceeded,
    Env,
    EnvCollection,
    FlowContext,
    FlowParams,
    OutputTokensExceeded,
    flow,
)
from hmz.runtime.flowing.fakes import FakeAgentDriver, FakeEnvDriver, run_fake


class Solo(AgentCollection):
    agent: Agent


class Place(EnvCollection):
    env: Env


class Depth(FlowParams):
    left: int = 0
    turns: int = 1
    own: float = -1.0


def _turns(ctx: Any) -> int:
    return ctx.usage.output_tokens


@flow(agents=Solo, envs=Place, params=Depth)
async def spender(
    task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
) -> list[tuple[int, float, int]]:
    """Recurses `left` deep, taking `turns` turns at the bottom; says what each level spent."""
    if params.left:
        below = await spender(
            task,
            agents=agents,
            envs=envs,
            params=Depth(left=params.left - 1, turns=params.turns),
        )
    else:
        agent = agents["agent"]
        session = await agent.spawn(env=envs["env"])
        for _ in range(params.turns):
            await agent.run("spend", session=session)
        below = []
    usage = ctx.usage
    return [(params.left, usage.cost, usage.output_tokens), *below]


async def test_spending_rolls_up_through_ten_levels() -> None:
    driver = FakeAgentDriver(cost=0.25, output_tokens=10, seconds=2.0)
    said = await run_fake(
        spender, params={"left": 9, "turns": 4}, agents={"agent": driver}
    )
    assert len(said) == 10
    assert {(cost, tokens) for _, cost, tokens in said} == {(1.0, 40)}
    assert driver.sessions[0].usage.output_tokens == 40


async def test_spending_rolls_up_across_a_gather() -> None:
    @flow(agents=Solo, envs=Place, params=Depth)
    async def fanning(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> tuple[float, int, float]:
        await asyncio.gather(
            *(
                spender(task, agents=agents, envs=envs, params=Depth(left=3, turns=2))
                for _ in range(5)
            )
        )
        usage = ctx.usage
        return usage.cost, usage.output_tokens, usage.duration.total_seconds()

    driver = FakeAgentDriver(cost=0.5, output_tokens=3, seconds=1.5)
    assert await run_fake(fanning, agents={"agent": driver}) == (5.0, 30, 15.0)


async def test_a_budget_is_the_tighter_of_a_flow_s_own_and_what_remains_above() -> None:
    @flow(agents=Solo, envs=Place, params=Depth)
    async def reading(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> list[Budget]:
        agent = agents["agent"]
        session = await agent.spawn(env=envs["env"])
        await agent.run("spend", session=session)

        @flow(agents=Solo, envs=Place, params=Depth)
        async def inner(
            task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
        ) -> Budget:
            return ctx.budget

        own = Budget(cost=10.0, output_tokens=5)
        tight = Budget(cost=0.5, duration=datetime.timedelta(hours=1))
        return [
            ctx.budget,
            await inner(task, agents=agents, envs=envs, params=params),
            await inner(task, agents=agents, envs=envs, params=params, budget=own),
            await inner(task, agents=agents, envs=envs, params=params, budget=tight),
        ]

    run, inherited, own, tight = await run_fake(
        reading,
        agents={"agent": FakeAgentDriver(cost=1.0, output_tokens=2)},
        budget=Budget(cost=3.0, duration=datetime.timedelta(minutes=10)),
    )
    assert run.cost == 3.0
    assert run.output_tokens is None
    assert run.duration is not None
    assert inherited.cost == 2.0
    assert own.cost == 2.0
    assert own.output_tokens == 5
    assert tight.cost == 0.5
    assert tight.duration is not None
    assert tight.duration <= datetime.timedelta(minutes=10)


async def test_an_unlimited_budget_says_so() -> None:
    @flow(agents=Solo, envs=Place, params=Depth)
    async def reading(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> Budget:
        return ctx.budget

    budget = await run_fake(reading, budget=Budget(cost=math.inf))
    assert budget.cost == math.inf
    assert budget.graceful


@pytest.mark.parametrize(
    ("budget", "raised"),
    [
        (Budget(cost=1.0), CostExceeded),
        (Budget(output_tokens=20), OutputTokensExceeded),
    ],
)
async def test_a_spent_budget_stays_spent(
    budget: Budget, raised: type[BudgetExceeded]
) -> None:
    @flow(agents=Solo, envs=Place, params=Depth)
    async def spending(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> int:
        agent = agents["agent"]
        session = await agent.spawn(env=envs["env"])
        taken = 0
        for _ in range(100):
            try:
                await agent.run("again", session=session)
            except raised:
                break
            taken += 1
        for _ in range(3):
            with pytest.raises(raised):
                await agent.run("once more", session=session)
        return taken

    driver = FakeAgentDriver(cost=0.25, output_tokens=5)
    assert await run_fake(spending, agents={"agent": driver}, budget=budget) == 4
    assert len(driver.prompts) == 4


async def test_a_child_s_own_budget_runs_out_without_its_caller_s() -> None:
    @flow(agents=Solo, envs=Place, params=Depth)
    async def parent(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> tuple[float, float]:
        with pytest.raises(CostExceeded):
            await spender(
                task,
                agents=agents,
                envs=envs,
                params=Depth(turns=10),
                budget=Budget(cost=0.5),
            )
        agent = agents["agent"]
        session = await agent.spawn(env=envs["env"])
        await agent.run("still fine", session=session)
        return ctx.usage.cost, ctx.budget.cost or 0.0

    spent, left = await run_fake(
        parent, agents={"agent": FakeAgentDriver(cost=0.25)}, budget=Budget(cost=10)
    )
    assert spent == 0.75
    assert left == 10


async def test_a_caller_s_spent_budget_stops_its_children() -> None:
    @flow(agents=Solo, envs=Place, params=Depth)
    async def parent(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> None:
        agent = agents["agent"]
        session = await agent.spawn(env=envs["env"])
        await agent.run("spend it all", session=session)
        with pytest.raises(CostExceeded):
            await spender(
                task,
                agents=agents,
                envs=envs,
                params=Depth(left=3),
                budget=Budget(cost=5),
            )

    await run_fake(
        parent, agents={"agent": FakeAgentDriver(cost=1.0)}, budget=Budget(cost=1)
    )


async def test_a_turn_is_told_what_it_may_spend() -> None:
    @flow(agents=Solo, envs=Place, params=Depth)
    async def told(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> None:
        agent = agents["agent"]
        session = await agent.spawn(env=envs["env"])
        await agent.run("one", session=session)
        with pytest.raises(CostExceeded):
            await agent.run(
                "two",
                session=session,
                budget=Budget(cost=0.1, output_tokens=3, graceful=False),
            )
        assert ctx.usage.cost == 0.35

    driver = FakeAgentDriver(cost=0.25, output_tokens=1)
    started = time.monotonic()
    await run_fake(
        told,
        agents={"agent": driver},
        budget=Budget(cost=2.0, duration=datetime.timedelta(minutes=5)),
    )
    first, second = (one.limits for one in driver.sessions[0].requests)
    assert first.cost == 2.0
    assert first.output_tokens is None
    assert first.graceful
    assert first.deadline is not None
    assert started + 290 < first.deadline < started + 310
    assert second.cost == 0.1
    assert second.output_tokens == 3
    assert not second.graceful


async def test_a_hard_limit_is_kept_inside_the_turn_by_the_driver() -> None:
    @flow(agents=Solo, envs=Place, params=Depth)
    async def hard(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> float:
        agent = agents["agent"]
        session = await agent.spawn(env=envs["env"])
        with pytest.raises(CostExceeded):
            await agent.run("too much", session=session)
        return ctx.usage.cost

    spent = await run_fake(
        hard,
        agents={"agent": FakeAgentDriver(cost=5.0)},
        budget=Budget(cost=1.0, graceful=False),
    )
    assert spent == 1.0


# ---------------------------------------------------------------------------- deadlines


@flow(agents=Solo, envs=Place, params=Depth)
async def sleeper(
    task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
) -> str:
    await asyncio.sleep(params.own if params.own >= 0 else 30)
    return "woke"


async def test_a_flow_s_deadline_stops_it() -> None:
    @flow(agents=Solo, envs=Place, params=Depth)
    async def parent(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> str:
        started = time.monotonic()
        with pytest.raises(DurationExceeded) as raised:
            await sleeper(
                task,
                agents=agents,
                envs=envs,
                params=params,
                budget=Budget(duration=datetime.timedelta(seconds=0.05)),
            )
        assert isinstance(raised.value, TimeoutError)
        assert time.monotonic() - started < 5
        return await sleeper(task, agents=agents, envs=envs, params=Depth(own=0))

    assert await run_fake(parent) == "woke"


async def test_a_deadline_is_shared_by_concurrent_children_not_summed() -> None:
    @flow(agents=Solo, envs=Place, params=Depth)
    async def gathering(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> list[str]:
        return await asyncio.gather(
            *(
                sleeper(task, agents=agents, envs=envs, params=Depth(own=0.1))
                for _ in range(10)
            )
        )

    started = time.monotonic()
    said = await run_fake(
        gathering, budget=Budget(duration=datetime.timedelta(seconds=5))
    )
    assert said == ["woke"] * 10
    assert time.monotonic() - started < 4

    started = time.monotonic()
    with pytest.raises(DurationExceeded):
        await run_fake(
            gathering, budget=Budget(duration=datetime.timedelta(seconds=0.05))
        )
    assert time.monotonic() - started < 5


async def test_a_graceful_deadline_lets_the_turn_under_way_finish() -> None:
    finished: list[str] = []
    release = asyncio.Event()

    async def reply(prompt: str, *, session: Any, output_schema: Any) -> str:
        del output_schema
        await release.wait()
        finished.append(prompt)
        return "done"

    @flow(agents=Solo, envs=Place, params=Depth)
    async def turning(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> None:
        agent = agents["agent"]
        session = await agent.spawn(env=envs["env"])
        await agent.run("slow", session=session)
        finished.append("after the turn")
        await asyncio.sleep(30)

    async def let_go() -> None:
        await asyncio.sleep(0.15)
        release.set()

    releasing = asyncio.ensure_future(let_go())
    with pytest.raises(DurationExceeded):
        await run_fake(
            turning,
            agents={"agent": FakeAgentDriver(reply=reply)},
            budget=Budget(duration=datetime.timedelta(seconds=0.05), graceful=True),
        )
    await releasing
    assert finished == ["slow", "after the turn"]


async def test_a_hard_deadline_interrupts_the_turn_under_way() -> None:
    interrupted: list[str] = []

    async def reply(prompt: str, *, session: Any, output_schema: Any) -> str:
        del prompt, output_schema
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            interrupted.append("cancelled")
            raise
        return "never"

    @flow(agents=Solo, envs=Place, params=Depth)
    async def turning(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> None:
        agent = agents["agent"]
        session = await agent.spawn(env=envs["env"])
        await agent.run("slow", session=session)

    driver = FakeAgentDriver(reply=reply)
    with pytest.raises(DurationExceeded):
        await run_fake(
            turning,
            agents={"agent": driver},
            budget=Budget(duration=datetime.timedelta(seconds=0.05), graceful=False),
        )
    assert interrupted == ["cancelled"]
    assert driver.sessions[0].closed


async def test_a_spent_deadline_refuses_the_next_turn() -> None:
    @flow(agents=Solo, envs=Place, params=Depth)
    async def late(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> None:
        agent = agents["agent"]
        session = await agent.spawn(env=envs["env"])
        time.sleep(0.06)  # noqa: ASYNC251 -- the loop must not see the deadline go by
        await agent.run("too late", session=session)

    with pytest.raises(DurationExceeded):
        await run_fake(
            late, budget=Budget(duration=datetime.timedelta(seconds=0.05), cost=1)
        )


async def test_cancelling_a_run_is_not_its_deadline() -> None:
    @flow(agents=Solo, envs=Place, params=Depth)
    async def waiting(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> None:
        await sleeper(
            task,
            agents=agents,
            envs=envs,
            params=params,
            budget=Budget(duration=datetime.timedelta(seconds=20)),
        )

    running = asyncio.ensure_future(
        run_fake(waiting, budget=Budget(duration=datetime.timedelta(seconds=30)))
    )
    await asyncio.sleep(0.05)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running


async def test_a_flow_that_swallows_its_deadline_leaves_nothing_pending() -> None:
    @flow(agents=Solo, envs=Place, params=Depth)
    async def swallowing(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> str:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            return "swallowed"
        return "slept"

    @flow(agents=Solo, envs=Place, params=Depth)
    async def parent(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> list[str]:
        said = await swallowing(
            task,
            agents=agents,
            envs=envs,
            params=params,
            budget=Budget(duration=datetime.timedelta(seconds=0.05)),
        )
        await asyncio.sleep(0.01)
        task_ = asyncio.current_task()
        assert task_ is not None
        return [said, str(task_.cancelling())]

    assert await run_fake(parent) == ["swallowed", "0"]


async def test_usage_and_budget_are_read_off_the_call_as_it_goes() -> None:
    @flow(agents=Solo, envs=Place, params=Depth)
    async def reading(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> list[float]:
        agent = agents["agent"]
        session = await agent.spawn(env=envs["env"])
        said: list[float] = []
        for _ in range(3):
            await agent.run("x", session=session)
            said.append(ctx.usage.cost)
            said.append(ctx.budget.cost or 0.0)
        return said

    said = await run_fake(
        reading, agents={"agent": FakeAgentDriver(cost=1.0)}, budget=Budget(cost=5)
    )
    assert said == [1.0, 5.0, 2.0, 5.0, 3.0, 5.0]


def test_the_env_driver_s_timeout_is_its_own() -> None:
    assert FakeEnvDriver().available


@pytest.mark.parametrize(
    ("run", "own", "turn", "graceful"),
    [
        (Budget(cost=1, graceful=False), None, Budget(output_tokens=1000), False),
        (Budget(cost=1), None, Budget(cost=0.5, graceful=False), False),
        (Budget(cost=1), None, Budget(cost=5, graceful=False), True),
        (Budget(cost=100, graceful=False), Budget(cost=1), None, True),
        (Budget(cost=1, graceful=False), Budget(cost=100), None, False),
        (Budget(cost=1), None, None, True),
    ],
    ids=[
        "hard run, turn budget",
        "hard turn binds",
        "hard turn does not bind",
        "hard run, tighter child",
        "hard run binds a child",
        "all graceful",
    ],
)
async def test_a_turn_is_hard_where_a_budget_that_binds_it_is(
    run: Budget, own: Budget | None, turn: Budget | None, graceful: bool
) -> None:
    @flow(agents=Solo, envs=Place, params=Depth)
    async def one_turn(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> None:
        agent = agents["agent"]
        session = await agent.spawn(env=envs["env"])
        await agent.run("x", session=session, budget=turn)

    @flow(agents=Solo, envs=Place, params=Depth)
    async def calling(
        task: str, *, agents: Solo, envs: Place, params: Depth, ctx: FlowContext
    ) -> None:
        await one_turn(task, agents=agents, envs=envs, params=params, budget=own)

    driver = FakeAgentDriver()
    await run_fake(calling, agents={"agent": driver}, budget=run)
    assert driver.sessions[0].requests[0].limits.graceful is graceful

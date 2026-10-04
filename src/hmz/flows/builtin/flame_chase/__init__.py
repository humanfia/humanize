"""Flame chase (flowbench: flame_chase) -- two agents take turns on the same task.

    hmz exec -f flame_chase -a first_chaser=claude/claude-opus-5:high \
        -a second_chaser=codex/gpt-5.6-sol:high -p budget.cost=10 "the task"

Each turn is a fresh session, so the two share nothing but the repository, and a turn that
fails passes to the other chaser. The budget ends it: the turn that finds it spent raises the
budget's `BudgetExceeded`, and `--resume` picks up with whichever chaser was next. Three
failed turns in a row end it with the last failure.
"""

import asyncio

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    HarnessError,
    LocalEnv,
    flow,
)

FAILED = 3
PAUSE = 5.0


class Agents(AgentCollection):
    """The two that take turns, first the one and then the other."""

    first_chaser: Agent
    second_chaser: Agent


class Envs(EnvCollection):
    """Where both work: the workspace the run was started in."""

    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, resumable=True)
async def flame_chase(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Two agents take turns on the same task until the budget is spent."""
    state = ctx.state
    assert state is not None  # noqa: S101 -- a resumable flow is always handed its state
    chasers = (agents["first_chaser"], agents["second_chaser"])
    at = (state["turn"] if "turn" in state else 0) % len(chasers)
    failed = 0
    while True:
        chaser = chasers[at]
        session = await chaser.spawn(env=envs["workspace"])
        try:
            await chaser.run(task, session=session)
        except HarnessError:
            failed += 1
            if failed >= FAILED:
                raise
        else:
            failed = 0
        at = (at + 1) % len(chasers)
        state["turn"] = at
        if at == 0:
            state["rounds"] = (state["rounds"] if "rounds" in state else 0) + 1
        await asyncio.sleep(PAUSE)

"""Flame chase (flowbench: flame_chase) -- two agents take turns on the same task.

    hmz exec -f flame_chase -a first_chaser=claude/claude-opus-5:high \
        -a second_chaser=codex/gpt-5.6-sol:high -p budget.cost=10 "the task"

Each turn is a fresh session, so the two share nothing but the repository. The budget ends it
-- the turn that finds it spent raises the budget's `BudgetExceeded` -- and a turn that fails
ends it with that failure. Whose turn is next is kept, so `--resume` picks up with that chaser.
"""

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)


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
    turn = state["turn"] if "turn" in state else 0
    while True:
        chaser = chasers[turn]
        session = await chaser.spawn()
        await chaser.run(task, session=session, env=envs["workspace"])
        state["turn"] = turn = (turn + 1) % len(chasers)

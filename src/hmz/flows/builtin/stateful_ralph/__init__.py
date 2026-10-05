"""Stateful ralph (flowbench: stateful_ralph) -- one session, re-sent the task every turn.

    hmz exec -f stateful_ralph -a agent=claude/claude-opus-5:high -p budget.cost=5 "the task"

A turn that fails counts as one answered with nothing, but a CLI that cannot be started where
the workspace is -- not installed there, or unable to hold its sandbox -- ends the run, since no
round would start it. It stops after three rounds in a row answered with nothing, or when the
budget is spent -- the turn that finds it spent raises the budget's `BudgetExceeded` --
and `--resume` carries on counting rounds, in a fresh session.
"""

import asyncio

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    HarnessError,
    HarnessNotInstalled,
    HarnessSandboxed,
    LocalEnv,
    flow,
)

STALLED = 3
PAUSE = 5.0


class Agents(AgentCollection):
    """The one agent that takes every round."""

    agent: Agent


class Envs(EnvCollection):
    """Where it works: the workspace the run was started in."""

    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, resumable=True)
async def stateful_ralph(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """The task again and again, in one session that remembers."""
    state = ctx.state
    assert state is not None  # noqa: S101 -- a resumable flow is always handed its state
    agent = agents["agent"]
    session = await agent.spawn()
    stalled = 0
    while True:
        state["rounds"] = rounds = (state["rounds"] if "rounds" in state else 0) + 1
        print(f"round {rounds}")
        try:
            answered = await agent.run(task, session=session, env=envs["workspace"])
        except (HarnessNotInstalled, HarnessSandboxed):
            raise
        except HarnessError as error:
            print(f"round {rounds} failed: {error}")
            answered = ""
        stalled = 0 if answered else stalled + 1
        if stalled >= STALLED:
            print(f"stopping: {stalled} rounds in a row answered with nothing")
            return
        await asyncio.sleep(PAUSE)

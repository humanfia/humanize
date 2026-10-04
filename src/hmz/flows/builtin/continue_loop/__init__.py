"""Continue loop (flowbench: continue_loop) -- send the task once, then keep nudging "continue".

    hmz exec -f continue_loop -a agent=claude/claude-opus-5:high -p budget.cost=5 "the task"

One session for the whole run. A turn that answered moves the prompt on to "continue"; one
that answered nothing, or failed, is sent again. The budget ends it: the turn that finds it
spent raises the budget's `BudgetExceeded`, which is how the run ends, and `--resume` carries
on counting rounds under a fresh one. Three failed turns in a row end it with the last
failure.
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
    """The one agent that takes every round."""

    agent: Agent


class Envs(EnvCollection):
    """Where it works: the workspace the run was started in."""

    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, resumable=True)
async def continue_loop(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Send the task once, then keep nudging "continue" until the budget is spent."""
    state = ctx.state
    assert state is not None  # noqa: S101 -- a resumable flow is always handed its state
    agent = agents["agent"]
    session = await agent.spawn(env=envs["workspace"])
    prompt = task
    failed = 0
    while True:
        state["rounds"] = (state["rounds"] if "rounds" in state else 0) + 1
        try:
            answered = await agent.run(prompt, session=session)
        except HarnessError:
            failed += 1
            if failed >= FAILED:
                raise
            answered = ""
        else:
            failed = 0
        if answered:
            prompt = "continue"
        await asyncio.sleep(PAUSE)

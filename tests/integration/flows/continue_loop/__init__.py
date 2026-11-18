"""Continue loop (flowbench: continue_loop) -- send the task once, then keep nudging "continue".

    hmz exec -f continue_loop -a agent=claude/claude-opus-5:high -p budget.cost=5 "the task"

One session for the whole run: the task as its first turn, and "continue" as every turn after
it. The budget ends it -- the turn that finds it spent raises the budget's `BudgetExceeded` --
and a turn that fails ends it with that failure.
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
    """The one agent that takes every round."""

    agent: Agent


class Envs(EnvCollection):
    """Where it works: the workspace the run was started in."""

    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def continue_loop(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Send the task once, then keep nudging "continue" until the budget is spent."""
    agent, workspace = agents["agent"], envs["workspace"]
    session = await agent.spawn()
    await agent.run(task, session=session, env=workspace)
    while True:
        await agent.run("continue", session=session, env=workspace)

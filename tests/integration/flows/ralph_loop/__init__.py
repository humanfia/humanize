"""Ralph loop (flowbench: ralph_loop) -- a fresh session every turn, so nothing carries over.

    hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -p budget.cost=5 "the task"

The task again and again, each round in a session of its own: what one round leaves the next
is the repository and nothing else. The budget ends it -- the turn that finds it spent raises
the budget's `BudgetExceeded` -- and a turn that fails ends it with that failure, a turn that
could be taken again having been taken again before it got here. There is nothing to pick up:
the repository is all a Ralph loop keeps, so running it again is carrying it on.
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
async def ralph_loop(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """The task again and again, a fresh session every round."""
    agent = agents["agent"]
    while True:
        session = await agent.spawn()
        await agent.run(task, session=session, env=envs["workspace"])

"""Stateful ralph (flowbench: stateful_ralph) -- one session, re-sent the task every turn.

    hmz exec -f stateful_ralph -a agent=claude/claude-opus-5:high -p budget.cost=5 "the task"

The task again and again, in one session that remembers every round before it. The budget
ends it -- the turn that finds it spent raises the budget's `BudgetExceeded` -- and a turn that
fails ends it with that failure. The session is kept in the state after every round, so
`--resume` carries the conversation on from the last round that finished.
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


@flow(agents=Agents, envs=Envs, params=FlowParams, resumable=True)
async def stateful_ralph(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """The task again and again, in one session that remembers."""
    state = ctx.state
    assert state is not None  # noqa: S101 -- a resumable flow is always handed its state
    agent = agents["agent"]
    session = state["session"] if "session" in state else await agent.spawn()
    while True:
        await agent.run(task, session=session, env=envs["workspace"])
        state["session"] = session

"""Goal (flowbench: goal) -- the task set once as the agent's own goal.

    hmz exec -f goal -a worker=claude/claude-opus-5:high -b cost=5 "the task"

One turn, `/goal <task>`, in one session: the model keeps working until it says the goal is
met, or the budget is spent. Only a harness with a goal command of its own can take it.
"""

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    GoalCommandAgentMixin,
    LocalEnv,
    flow,
)


class Worker(Agent, GoalCommandAgentMixin):
    """An agent whose harness takes `/goal`."""


class Agents(AgentCollection):
    """The one agent that pursues the goal."""

    worker: Worker


class Envs(EnvCollection):
    """Where it works: the workspace the run was started in."""

    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def goal(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """The task set once as the agent's own goal."""
    worker = agents["worker"]
    session = await worker.spawn(env=envs["workspace"])
    await worker.run(f"/goal {task}", session=session)

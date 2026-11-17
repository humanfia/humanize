"""Flame chase (flowbench: flame_chase) -- two agents take turns on the same task.

    hmz exec -f flame_chase -a first_chaser=claude/claude-opus-5:high \
        -a second_chaser=codex/gpt-5.6-sol:high -p budget.cost=10 "the task"

Each turn is a fresh session, so the two share nothing but the repository. The budget ends it
-- the turn that finds it spent raises the budget's `BudgetExceeded` -- and a turn that fails
ends it with that failure. Whose turn is next is kept, so `--resume` picks up with that chaser.

Each chaser's turn may be given a quota of its own, as `-p first_chaser_cost=1.5`,
`-p second_chaser_duration=600` and the like: a turn that reaches its quota is cut off at
once and the other chaser takes over from what it left in the repository.
"""

import datetime

import pydantic

from hmz.flows import (
    Agent,
    AgentCollection,
    Budget,
    BudgetExceeded,
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


class Params(FlowParams):
    """Each chaser's quota for one turn of its own; a limit left out is none.

    Attributes:
      first_chaser_duration: Seconds one turn of the first chaser may run for.
      first_chaser_cost: USD one turn of the first chaser may spend.
      first_chaser_output_tokens: Tokens one turn of the first chaser may write.
      second_chaser_duration: Seconds one turn of the second chaser may run for.
      second_chaser_cost: USD one turn of the second chaser may spend.
      second_chaser_output_tokens: Tokens one turn of the second chaser may write.
    """

    first_chaser_duration: float | None = pydantic.Field(default=None, ge=0)
    first_chaser_cost: float | None = pydantic.Field(default=None, ge=0)
    first_chaser_output_tokens: int | None = pydantic.Field(default=None, ge=0)
    second_chaser_duration: float | None = pydantic.Field(default=None, ge=0)
    second_chaser_cost: float | None = pydantic.Field(default=None, ge=0)
    second_chaser_output_tokens: int | None = pydantic.Field(default=None, ge=0)


def _quota(params: Params, role: str) -> Budget | None:
    """The budget one turn of `role` is held to, cut off at once; None for no quota."""
    duration = getattr(params, f"{role}_duration")
    cost = getattr(params, f"{role}_cost")
    tokens = getattr(params, f"{role}_output_tokens")
    if duration is None and cost is None and tokens is None:
        return None
    return Budget(
        duration=None if duration is None else datetime.timedelta(seconds=duration),
        cost=cost,
        output_tokens=tokens,
        graceful=False,
    )


@flow(agents=Agents, envs=Envs, params=Params, resumable=True)
async def flame_chase(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> None:
    """Two agents take turns on the same task until the budget is spent."""
    state = ctx.state
    assert state is not None  # noqa: S101 -- a resumable flow is always handed its state
    roles = ("first_chaser", "second_chaser")
    quotas = {role: _quota(params, role) for role in roles}
    turn = state["turn"] if "turn" in state else 0
    while True:
        role = roles[turn]
        chaser = agents[role]
        session = await chaser.spawn()
        try:
            await chaser.run(
                task, session=session, env=envs["workspace"], budget=quotas[role]
            )
        except BudgetExceeded as error:
            if not error.own:
                raise
        state["turn"] = turn = (turn + 1) % len(roles)

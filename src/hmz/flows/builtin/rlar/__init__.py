"""RLAR (flowbench: rlar) -- an actor works in one session, and a fresh reviewer reads its work.

    hmz exec -f rlar -a actor=claude/claude-opus-5:high -a reviewer=codex/gpt-5.6-sol:high \
        -p budget.cost=20 "the task"

Each round's reviewer is told the task and what the actor said as it ended its turn, and reads
the repository: what the actor said is its own account, held to what the files show, and is
itself the deliverable of a task that asks for an answer rather than a change.

It ends when the reviewer says the task is done, or when the budget is spent; `--resume`
hands a fresh actor the last review to pick up from. A turn that fails, or a review out of
shape, is taken again next round; three failures in a row end it with the last one.
"""

import asyncio

from pydantic import BaseModel, Field

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    FlowState,
    HarnessError,
    LocalEnv,
    flow,
)

FAILED = 3
PAUSE = 5.0


class Reviewer(Agent):
    """A fresh reader of each round, carrying the flow's own way of writing a review."""

    _skills = ("review-notes",)


class Agents(AgentCollection):
    """The one that works and the one that reads what it did."""

    actor: Agent
    reviewer: Reviewer


class Envs(EnvCollection):
    """Where both work: the workspace the run was started in."""

    workspace: LocalEnv


class Review(BaseModel):
    """What one round's review comes to: whether it is over, and what the actor is told.

    The fields are what the reviewer is asked for -- the descriptions here are the whole of
    the instruction, since they are what the backend is given as the shape to answer in.
    """

    model_config = {"extra": "forbid"}

    done: bool = Field(
        description="True only if the task is completely and correctly done: everything "
        "asked for is implemented, it works, nothing was faked, stubbed or special-cased to "
        "pass, and there is no next step worth taking. False if there is anything at all "
        "left to do or to fix."
    )
    notes: str = Field(
        description="The review itself, written as a message to the coding agent: what is "
        "done, what is wrong or missing, and what to do next, citing specific files, lines "
        "and commands. It is passed on word for word and is all the agent will hear from "
        "you, so leave nothing to be inferred. When done is true, this is what the run "
        "finishes on: say what was built and how it was checked."
    )


REVIEW_PROMPT = """You are a meticulous reviewer, running in the working directory of a coding \
agent that has been given the task below. Use shell tools (cat, ls, git status, git diff, etc.) \
to review what it has actually done against the state of the repository. Be skeptical: treat \
reward hacking -- tests weakened or special-cased, work stubbed out or faked -- as the thing you \
are most there to catch.

Task (TASK.md):
"""

SAID = """

What the agent said as it ended its last turn is below. It is its own account of its work, not \
evidence of it: hold every claim in it to what the repository shows. Where the task asks for an \
answer rather than a change, it is the answer to review.

<agent_said>
{said}
</agent_said>
"""

PICKED_UP = """{task}

Work in this repository is already under way: an earlier run here was stopped before it \
finished, and below is a reviewer's reading of the last round of it. That run may have been on \
the task above or on something else -- what carries over is the repository, not the task. You \
did not do that work and have no record of it beyond what the files now hold, so read them \
first, then carry on with the task above, taking the review as far as it bears on it.

Review of the last round:
{notes}"""


@flow(agents=Agents, envs=Envs, params=FlowParams, resumable=True)
async def rlar(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """An actor works in one session until a fresh reviewer says the task is done."""
    state = ctx.state
    assert state is not None  # noqa: S101 -- a resumable flow is always handed its state
    actor, reviewer = agents["actor"], agents["reviewer"]
    workspace = envs["workspace"]
    working = await actor.spawn()
    notes: str = state["notes"] if "notes" in state else ""
    prompt = PICKED_UP.format(task=task, notes=notes) if notes else task
    failed = 0
    while True:
        try:
            worked = await actor.run(prompt, session=working, env=workspace)
        except HarnessError:
            failed += 1
            if failed >= FAILED:
                raise
            worked = ""
        if worked:
            reading = await reviewer.spawn()
            try:
                review = await reviewer.run(
                    REVIEW_PROMPT + task + SAID.format(said=worked),
                    session=reading,
                    env=workspace,
                    output_schema=Review,
                )
            except HarnessError:
                failed += 1
                if failed >= FAILED:
                    raise
                review = None
            else:
                failed = 0
            if review is not None and review.done:
                print(review.notes)
                _forget(state)
                return review.notes
            if review is not None and review.notes:
                prompt = notes = review.notes
            state["rounds"] = (state["rounds"] if "rounds" in state else 0) + 1
            state["notes"] = notes
        await asyncio.sleep(PAUSE)


def _forget(state: FlowState) -> None:
    """Drops what a run that finished kept, so the next one starts on the task alone."""
    for key in ("notes", "rounds"):
        if key in state:
            del state[key]

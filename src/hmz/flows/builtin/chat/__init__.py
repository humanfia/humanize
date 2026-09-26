"""Chat -- one agent, one session, and every line said back is the next turn of it.

    hmz exec -f chat -a assistant=claude/MODEL:high "what does this repository do?"

Which is talking to a coding agent, with no loop around it: the flow does what it is told and
then waits to be told again. It is the flow the terminal interface opens on, so that saying
something is all it takes to start.

Two agents, then, and the second of them is you: `human` is the outworlder, and saying
something to it is asking what to say next. Run from a command line, where nobody is at a
prompt, the outworlder is away and answers with nothing, so the flow does the one thing it was
given and stops. A question the agent stops to ask its user mid-turn is put to you the same
way, on a harness that asks.

The agent is whatever harness was chosen, with everything that harness can do: `chat` declares
a plain `Agent` -- one allowed the web -- because it talks to any of them, and the runtime hands
the flows humanize ships the harness's full view. It is the one flow that runs with no budget
of its own -- a conversation ends when you stop talking, and the runtime runs it under
`Budget(cost=inf)`.

The first turn is the one allowed to fail out loud. A conversation that could not be started
-- an account refused, a model this harness will not run -- ends the run with what the harness
said about it, rather than answering with nothing and exiting as though the one thing it was
asked for had been done. A turn after it that fails is said to you, and the conversation goes
on.

Nothing of it is kept for a next run to pick up: a session is opened rather than reopened, so
starting this again is another conversation rather than the last one carried on.
"""

from __future__ import annotations

import contextlib
from typing import cast

from hmz.flows import (
    Agent,
    AgentCollection,
    AskUserHookAgentMixin,
    AskUserHookParams,
    AskUserHookResult,
    CapabilityNotGranted,
    EnvCollection,
    FlowContext,
    FlowParams,
    HarnessError,
    HookFn,
    LocalEnv,
    Outworlder,
    Permission,
    PermissionKind,
    Session,
    flow,
)


class Assistant(Agent):
    """Whichever agent was chosen, allowed the web as a person talking to one would expect."""

    _permission = Permission(online=PermissionKind.ALL)


class Agents(AgentCollection):
    """The two sides of a conversation."""

    assistant: Assistant
    human: Outworlder


class Envs(EnvCollection):
    """Where the conversation happens: the workspace it was started in."""

    workspace: LocalEnv


class Params(FlowParams):
    """Nothing: a conversation is set up by what is said in it."""


@flow(agents=Agents, envs=Envs, params=Params)
async def chat(
    task: str,
    *,
    agents: Agents,
    envs: Envs,
    params: Params,  # noqa: ARG001 -- a flow takes its params whether or not it has any
    ctx: FlowContext,  # noqa: ARG001 -- likewise its context
) -> None:
    """Talks to one agent for as long as you keep answering it."""
    assistant, human = agents["assistant"], agents["human"]
    here = envs["workspace"]
    # One session, so the turns are a conversation rather than a series of first turns.
    conversation = await assistant.spawn(env=here)
    person = await human.spawn(env=here)
    with contextlib.suppress(CapabilityNotGranted):
        # A harness that stops to ask its user a question has it put to the person here;
        # one that cannot ask has no such hook to hang, and there is nothing to put.
        cast("AskUserHookAgentMixin", assistant).on_ask_user(_asking(human, person))
    said = task
    opening = True
    while said:
        try:
            answered = await assistant.run(said, session=conversation)
        except HarnessError as failed:
            if opening:
                raise
            answered = f"That turn could not be taken: {failed}"
        opening = False
        # Saying that to the person is asking what to say next, and what they answer with is
        # what they typed -- or nothing, which is a conversation that is over.
        said = await human.run(answered, session=person)


def _asking(
    human: Outworlder, person: Session
) -> HookFn[AskUserHookParams, AskUserHookResult]:
    """The hook that puts a question the agent asked to the person it is talking to."""

    async def asked(params: AskUserHookParams) -> AskUserHookResult:
        offered = f" ({' / '.join(params.options)})" if params.options else ""
        said = await human.run(f"{params.question}{offered}", session=person)
        return AskUserHookResult(answer=said or None)

    return asked

"""Chat -- one agent, one session, and every line said back is the next turn of it.

    hmz exec -f chat -a assistant=claude/MODEL:high "what does this repository do?"

Which is talking to a coding agent, with no loop around it: the flow does what it is told and
then waits to be told again. It is the flow the terminal interface opens on, so that saying
something is all it takes to start.

Two agents, then, and the second of them is you: `human` is the outworlder, and saying
something to it is asking what to say next. Here the outworlder is the conversation itself
rather than a question beside it: a reply waits for your next message, and a follow-up or a
steer typed in the conversation is that message, with no separate ask to answer. A question
the agent stops to ask its user mid-turn is put to you the same way, on a harness that asks,
and shows in the conversation with the options it offered. Run from a command line, where
nobody is at a prompt, the outworlder is away and answers with nothing, so the flow does the
one thing it was given and stops.

The agent is whatever harness was chosen, with everything that harness can do: `chat` declares
a plain `Agent` -- one allowed the web -- because it talks to any of them, and the runtime hands
it, and no other flow, the harness's full view. It is the one flow that runs with no budget
of its own -- a conversation ends when you stop talking, and the runtime runs it under
`Budget(cost=inf)`.

The first turn is the one allowed to fail out loud. A conversation that could not be started
-- an account refused, a model this harness will not run -- ends the run with what the harness
said about it, rather than answering with nothing and exiting as though the one thing it was
asked for had been done. A turn after it that fails is said to you, and the conversation goes
on.

A conversation is kept as it stands when it ends -- the assistant's session, in the flow's
state -- so that one picked up again (`--resume`) is the same conversation carried on: the
same epic, written on from where it stopped, and an agent that remembers everything said in it.
This is what an interface does with a chat nobody has looked at for a while between turns:
folds it away, and carries it on the next time somebody says something in it. One that cannot
be carried on says so in the conversation, and the next line starts a new one.
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
    Session,
    SessionError,
    flow,
)


class Assistant(Agent):
    """Whichever agent was chosen, allowed the web as a person talking to one would expect."""


class Agents(AgentCollection):
    """The two sides of a conversation."""

    assistant: Assistant
    human: Outworlder


class Envs(EnvCollection):
    """Where the conversation happens: the workspace it was started in."""

    workspace: LocalEnv


class Params(FlowParams):
    """Nothing: a conversation is set up by what is said in it."""


@flow(agents=Agents, envs=Envs, params=Params, resumable=True)
async def chat(
    task: str,
    *,
    agents: Agents,
    envs: Envs,
    params: Params,
    ctx: FlowContext,
) -> None:
    """Talks to one agent for as long as you keep answering it."""
    assistant, human = agents["assistant"], agents["human"]
    here = envs["workspace"]
    state = ctx.state
    assert state is not None  # noqa: S101 -- a resumable flow is always handed its state
    # One session, so the turns are a conversation rather than a series of first turns: the
    # one kept when it last stopped, where it is carried on.
    carried: Session | None = None
    unkept = ""
    if ctx.resumed:
        try:
            carried = state["conversation"] if "conversation" in state else None
        except SessionError as why:
            unkept = str(why)
        if carried is None:
            # Said ahead of the first answer, which a new conversation gives.
            unkept = _restarted(
                unkept or "it was not kept as it stopped", "this is a new one"
            )
    conversation = carried if carried is not None else await assistant.spawn()
    person = await human.spawn()
    with contextlib.suppress(CapabilityNotGranted):
        # A harness that stops to ask its user a question has it put to the person here;
        # one that cannot ask has no such hook to hang, and there is nothing to put.
        cast("AskUserHookAgentMixin", assistant).on_ask_user(_asking(human, person))
    said = task
    opening = not ctx.resumed
    try:
        while said:
            try:
                answered = await assistant.run(said, session=conversation, env=here)
            except (HarnessError, SessionError) as failed:
                if opening:
                    raise
                # Only a conversation that cannot be carried on is put down for a new one: a
                # turn that failed -- a limit, the network -- leaves it to be said again.
                if carried is None or not isinstance(failed, SessionError):
                    answered = f"That turn could not be taken: {failed}"
                else:
                    answered = _restarted(
                        str(failed), "what you say next starts a new one"
                    )
                    conversation = await assistant.spawn()
            if unkept:
                answered, unkept = f"{unkept}\n\n{answered}", ""
            opening, carried = False, None
            # Saying that to the person is asking what to say next, and what they answer
            # with is what they typed -- or nothing, which is a conversation that is over.
            said = await human.run(answered, session=person)
    finally:
        # As it stands, for a run picking it up to carry on: one with no turn taken, or
        # one closed under a turn, has nothing to carry on and keeps what it kept before.
        with contextlib.suppress(Exception):
            state["conversation"] = conversation


def _restarted(why: str, so: str) -> str:
    """What the person is told of a conversation that could not be carried on, and so what."""
    return f"This conversation could not be carried on ({why}), so {so}."


def _asking(
    human: Outworlder, person: Session
) -> HookFn[AskUserHookParams, AskUserHookResult]:
    """The hook that puts a question the agent asked to the person it is talking to."""

    async def asked(params: AskUserHookParams) -> AskUserHookResult:
        offered = f" ({' / '.join(params.options)})" if params.options else ""
        said = await human.run(f"{params.question}{offered}", session=person)
        return AskUserHookResult(answer=said or None)

    return asked

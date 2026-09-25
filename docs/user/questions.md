# Questions

An agent can stop mid-turn to ask a question: which approach to take, which file to change,
whether it understood you. A flow can ask you the other way, treating the person at the prompt
as one of its agents. Reach for this whenever a run needs an answer only a person should give.

## Try it

The interface opens on [`chat`](/flows/chat) — you and one agent, taking turns:

```sh
hmz
```

Say something, and when the agent stops mid-turn to ask you something back, the next line you
type is the answer to it.

## At the prompt

The question is shown with whatever it offered. The next line you type is **the answer**, not a
word put into the turn; the status line reads `enter answer` while that is so.

You are not held to the options. Every backend that offers options also takes something else —
the options are what the agent expects, and what an interface shows so the question reads as
one.

If the flow ends or is stopped while a question is still up, the question ends with it.
Stopping a flow is never blocked on a question.

## Whose question it is

An agent's question goes **to the flow** first. A flow that means you to answer its agents —
`chat` does — puts the question to you; a flow that answers them itself, or does not listen,
does not. An agent whose flow hung nothing to hear its questions is told nobody answered, and
carries on.

A flow's own question — its person taking a turn — always comes to you, when you are there.

## When nobody is there

`hmz exec` has nobody at a prompt. [`/afk`](/user/afk) says the same thing on purpose:

```
/afk on
```

In both cases the person is **away**: a question the flow asks is answered at once with
nothing — `""` for text, the answer a shape's defaults make where every field has one — and a
flow that asks for a shape with a field that has no default gets `OutworlderAway` raised, which
it had better handle. An agent's question put to you is told nobody answered, and the agent
carries on. A turn waiting on an answer that is not coming is a flow that has stopped, so this
is the default everywhere except an interface with `/afk` off. Asking starts **allowed**: a flow
that really needs a person gets one unless it has been said that none is there.

While it is on, the status line says `afk` in front of everything else on it — the whole point
of the switch is that nothing stops to tell you, so the mode itself has to be visible.

## From a flow

The rest of this page is the weaver's — whoever wrote the flow.

### The person as an agent

A role typed `Outworlder` is the person at the prompt — see [the person as an
agent](/weaver/human-agent). Nobody fills it with `-a`; humanize does. Running it is asking
what to say next, and what it answers is what you typed:

```python
from hmz.flows import (
    Agent,
    AgentCollection,
    AskUserHookAgentMixin,
    AskUserHookParams,
    AskUserHookResult,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Outworlder,
    flow,
)


class Assistant(Agent, AskUserHookAgentMixin): ...


class Agents(AgentCollection):
    assistant: Assistant
    human: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def talk(task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext):
    """One agent, one session, and every line you type between turns is a turn of it."""
    assistant, human = agents["assistant"], agents["human"]
    you = await human.spawn(env=envs["workspace"])

    async def ask_the_person(params: AskUserHookParams) -> AskUserHookResult:
        said = await human.run(f"{params.question} {params.options}", session=you)
        return AskUserHookResult(answer=said or None)

    assistant.on_ask_user(ask_the_person)
    conversation = await assistant.spawn(env=envs["workspace"])
    said = task
    while said:
        answered = await assistant.run(said, session=conversation)
        said = await human.run(answered, session=you)
```

That is what [`chat`](/flows/chat) does. One `-a` drives it, because nobody is asked what the
person runs:

```sh
hmz exec -f ./talk -a assistant=claude/claude-opus-5:high -b cost=5 "Read README.md and tell me what this is."
```

On a command line nobody is at a prompt, so `human.run(...)` answers `""`, `said` is falsy, and
the flow does the one thing it was given.

### An agent's question, answered by the flow

`on_ask_user` is what an agent stopping mid-turn reaches — on a role declared with
`AskUserHookAgentMixin`, which Claude Code, Codex, Kimi Code, ZCode and pi serve. The hook is
told the `question` and the `options` it offered, and answers with an `AskUserHookResult`:
`answer=` a string, or `None` for "nobody answered". It may answer however the flow likes — put
it to the person, as above, ask another agent, or look it up. A question waits for its hook as
long as the hook takes; nothing times it out.

### Asking the person for a shape

With an `output_schema`, the same run is a questionnaire. The person is not shown a JSON Schema.
They are asked **a question per field**, and the model is built out of what they typed:

```python
from typing import Literal

from pydantic import BaseModel, Field


class Settled(BaseModel):
    """What has to be agreed before anything is built."""

    approach: Literal["fast", "careful"] = Field(description="Which way should this be built?")
    tests: bool = Field(description="Write tests for it?")
    rounds: int = Field(default=3, description="How many rounds may it take?")


settled = await human.run("How should I do this?", session=you, output_schema=Settled)
working = await builder.spawn(env=workspace)
for _ in range(settled.rounds):
    await builder.run(
        f"{task}\n\nBuild this the {settled.approach} way."
        f"{' Write tests.' if settled.tests else ''}",
        session=working,
    )
```

| In the model | What they are asked |
| --- | --- |
| `description=` | the question itself, or the field's name where it has none |
| `Literal[…]` | those words, as the answers it offers |
| `bool` | `yes` and `no` |
| a default | "or `-` for 3" — and a dash takes it |
| `list[str]` | one line, separated by commas |

So a flow settles what only a person can settle in the model it is going to run on, once,
rather than by parsing a sentence. `Settled` has two fields with no default, so a run with
nobody there raises `OutworlderAway` at that line — a flow meant to run unattended too gives
every field a default, or catches it.

The person is not:

- a coding agent — it runs no model and spends nothing;
- in [`/monitor`](/user/monitor)'s handover graph or the cost readout — its turns are not
  bracketed by the events that say whose turn it is;
- one of the conversations **tab** steps between;
- able to run [moments](/weaver/hooks) — a moment is a point in a turn of a model.

### The moment, for a hook

`on_notification` hangs a hook on the agent stopping to tell its user something. It cannot
answer — a notification is heard, not answered — but it can log, notify or wake something up:

```python
async def ring(params: NotificationHookParams) -> NotificationHookResult:
    ring_a_bell(params.message)
    return NotificationHookResult()


agents["assistant"].on_notification(ring)
```

## See also

- [Side questions](/user/btw)
- [Being away](/user/afk)
- [Answers in a shape](/weaver/shapes)
- [The person as an agent](/weaver/human-agent)
- [Hooks](/weaver/hooks)

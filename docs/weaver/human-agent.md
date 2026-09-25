# The person as an agent

An **outworlder** is whoever is outside the run — the person at the prompt, or whatever stands
in for one — taking turns inside a flow as one of its agents. Add one when the flow needs a
human to answer: asking it something is asking what to say next, and it answers with what was
typed.

It is not steering. [Steering](/user/steering) is you putting words into an agent's turn while
it runs; an outworlder takes turns of its own, as an agent of the flow.

## Try it

Declare a role typed `Outworlder`, and it is handed over like the rest:

```python
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Outworlder,
    flow,
)


class Chat(AgentCollection):
    assistant: Agent
    human: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Chat, envs=Envs, params=FlowParams)
async def talk(
    task: str, *, agents: Chat, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """One session, and every line typed between turns is a turn of it."""
    assistant, human, workspace = agents["assistant"], agents["human"], envs["workspace"]
    conversation = await assistant.spawn(env=workspace)
    listening = await human.spawn(env=workspace)
    said = task
    while said:
        answered = await assistant.run(said, session=conversation)
        said = await human.run(answered, session=listening)
```

That is the shape of [`chat`](/flows/chat), the flow the interface opens on. An outworlder is
talked to the way any agent is — a session, then turns in it — and what `run` answers is what
the person typed.

**Nobody is asked what the person runs**, so a role typed `Outworlder` is filled by humanize
and never by `-a`. The flow above drives two agents and is started with one:

```sh
hmz exec -f talk -a assistant=claude/claude-opus-5:high -b cost=2 \
    "Read README.md and tell me what this is."
```

Naming the role on the command line is refused: it is not yours to fill.

## Away

`human.away` is whether anybody is there to answer. A run of `hmz exec` is always away — nobody
is at a prompt — and so is one where [`/afk`](/user/afk) is on in the interface. An outworlder
that is away answers at once, without asking anybody:

| Asked for | Answers |
| --- | --- |
| text | `""` |
| an [`output_schema`](/weaver/shapes) every field of which has a default | the schema built from its defaults |
| an `output_schema` with a field that has none | raises `OutworlderAway` |

So `talk` run from a command line takes one turn, hears `""`, and ends: the flow does the one
thing it was given. That is what you want from `chat` in a script. A flow that asks the person
something it cannot go on without, and wants to run unattended too, writes a default for every
field it asks — the default is what it does when nobody is there to say.

A person at the prompt who walks away mid-question is away too: `/afk` while the question is up
answers it as nobody.

## What it is not

An outworlder is not a coding agent. It runs no model and spends nothing, and its session is a
conversation with a person rather than with a CLI:

- It reaches none of a CLI's [moments](/weaver/hooks). `on_stop` and the rest are there, since
  every agent has them, and a hook hung on one is never called.
- It cannot be forked: `fork` raises `UnsupportedOperation`.
- It carries no skills, so `derive` with `skills=` raises `CapabilityNotGranted`.
- Its turns are not bracketed by the events that say whose turn it is, so the person appears
  in neither the handover graph of [`/monitor`](/user/monitor) nor the
  [cost readout](/user/tally).

## Asking them for a shape — a questionnaire

Give the person an [`output_schema`](/weaver/shapes), and they are asked **a question per
field**. The model is built out of what they typed:

```python
class Settled(BaseModel):
    approach: Literal["fast", "careful"] = Field(
        default="careful", description="Which way should this be built?"
    )
    tests: bool = Field(default=True, description="Write tests for it?")


settled = await human.run("How should I do this?", session=listening, output_schema=Settled)
if settled.tests:
    ...
```

A flow settles what only a person can settle **in the model it is going to run on**, once
rather than by parsing a sentence. Each question takes the road [a coding agent's own
question](/user/questions) takes. Which field becomes which question is a table on [Answers in
a shape](/weaver/shapes#asking-a-person-a-questionnaire).

## When another flow calls yours

A flow that [calls one](/weaver/calling-flows) with an `Outworlder` role may simply leave the
role out, and the callee is handed the run's own — whoever is at the prompt, or nobody:

```python
await load(":talk")(
    task, agents={"assistant": agents["assistant"]}, envs=envs, params=FlowParams()
)
```

Or hand over the one it was handed itself, which is the same person.

## Stand in for the person

Sometimes the caller means to answer for the person: a flow that runs `talk` with a script of
lines, a supervisor that answers a callee's questions with a model of its own.
`Outworlder.new()` makes an outworlder the caller answers for, through a hook of its own:

```python
from hmz.flows import Outworlder, OutworlderRunHookParams, OutworlderRunHookResult

lines = iter(["and the tests", "thanks"])


async def typed(params: OutworlderRunHookParams) -> OutworlderRunHookResult:
    return OutworlderRunHookResult(output=next(lines, ""))


stand_in = Outworlder.new()
stand_in.on_outworlder_run(typed)
await load(":talk")(
    task,
    agents={"assistant": agents["assistant"], "human": stand_in},
    envs=envs,
    params=FlowParams(),
)
```

Every `run` of the callee's `human` is now a call of `typed`, told the `prompt` and the
`output_schema` it was asked for, and answering with `output`: text, or an instance of that
schema. It runs as the flow that hung it, so it may take a turn of an agent of the caller's to
answer:

```python
async def answered(params: OutworlderRunHookParams) -> OutworlderRunHookResult:
    thinking = await supervisor.spawn(env=workspace)
    if params.output_schema is None:
        said = await supervisor.run(params.prompt, session=thinking)
    else:
        said = await supervisor.run(
            params.prompt, session=thinking, output_schema=params.output_schema
        )
    return OutworlderRunHookResult(output=said)
```

An `Outworlder.new()` with no hook hung on it is **away**, and answers as any away outworlder
does. `on_outworlder_run` is only for one made this way: hung on the run's own,
it raises `CapabilityNotGranted`, since the person at the prompt answers for themselves.

## See also

- [Questions](/user/questions)
- [Being away (/afk)](/user/afk)
- [Answers in a shape](/weaver/shapes)
- [Flows › The person at the prompt](/reference/flows#the-person-at-the-prompt)

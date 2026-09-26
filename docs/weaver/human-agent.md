# The person as an agent

An **outworlder** is whoever is outside the run: the person at the prompt, or whatever stands
in for them. Declare one as a role, and the flow takes turns with that person the way it does
with a coding agent: `run` asks them what to say next, and returns what they typed.

This is not [steering](/user/steering). Steering is you putting words into an agent's turn; an
outworlder takes turns of its own, as an agent of the flow.

## Try it

Declare a role typed `Outworlder`, and humanize hands it over like the rest:

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
    human: Outworlder  # [!code highlight]


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Chat, envs=Envs, params=FlowParams)
async def talk(
    task: str, *, agents: Chat, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """One session, and every line typed between turns is a turn of it."""
    assistant, human = agents["assistant"], agents["human"]
    workspace = envs["workspace"]
    conversation = await assistant.spawn(env=workspace)
    listening = await human.spawn(env=workspace)
    said = task
    while said:
        answered = await assistant.run(said, session=conversation)
        said = await human.run(answered, session=listening)  # [!code highlight]
```

That is the shape of [`chat`](/flows/chat), the flow the interface opens on. The person is
driven like any agent, a session and then turns in it, and `run` returns what they typed.

**Nobody picks what the person runs**, so humanize fills an `Outworlder` role and `-a` never
does. This flow drives two agents and is started with one:

```sh
hmz exec -f talk -a assistant=claude/claude-opus-5:high -b cost=2 \
    "Read README.md and tell me what this is."
```

Naming the role with `-a human=…` is refused.

## Ask them for a shape

Give the person an [`output_schema`](/weaver/shapes), and they are asked **a question per
field** instead of being shown a schema. The model is built out of what they typed:

```python
from typing import Literal

from pydantic import BaseModel, Field


class Settled(BaseModel):
    approach: Literal["fast", "careful"] = Field(
        default="careful", description="Which way should this be built?"
    )
    tests: bool = Field(default=True, description="Write tests for it?")
    rounds: int = Field(
        default=3, description="How many rounds may it take?"
    )


settled = await human.run(
    "How should I do this?", session=listening, output_schema=Settled
)
```

At the prompt, that reads:

<pre class="asking-tty" aria-label="The questionnaire at the prompt, drawn after the interface"><span class="said">●</span> How should I do this?

Which way should this be built? -- or `-` for careful
<span class="dim">      · fast
      · careful
   type an answer, or /afk to stop being asked</span>
<span class="you">❯</span> careful
<span class="said">●</span> Write tests for it? -- or `-` for yes
<span class="dim">      · yes
      · no
   type an answer, or /afk to stop being asked</span>
<span class="you">❯</span> -
<span class="said">●</span> How many rounds may it take? (a number) -- or `-` for 3
<span class="dim">   type an answer, or /afk to stop being asked</span>
<span class="you">❯</span> 5
</pre>
<p class="asking-tty-note">Drawn after the interface, not recorded. <code>settled</code> is
<code>Settled(approach='careful', tests=True, rounds=5)</code>.</p>

| In the model | What they are asked |
| --- | --- |
| `description=` | the question, or the field's name where there is none |
| `Literal[…]` | those words, offered as the answers |
| `bool` | `yes` or `no` |
| `int`, `float` | the question, with "(a number)" |
| `list[str]` | one line, "(several, separated by commas)" |
| a default | "-- or `-` for 3", and a dash takes the default |

Each question takes the road [a coding agent's own question](/user/questions) takes. What the
model refuses is asked again on that field, with the model's own message. What only a person
can settle is settled once, in the model the flow runs on, rather than by parsing a sentence.

## Away

`human.away` says whether anybody is there to answer. A run of `hmz exec` is always away, since
nobody is at a prompt. So is a run in the interface while [`/afk`](/user/afk) is on. An
outworlder that is away answers at once, without asking anybody:

| Asked for | Answers |
| --- | --- |
| text | `""` |
| an `output_schema` whose fields all have defaults | the model built from its defaults |
| an `output_schema` with a field that has none | raises `OutworlderAway` |

So `talk` run from a command line takes one turn, hears `""`, and ends: it does the one thing
it was given. A flow that asks the person something and should run unattended too gives every
field a default. The default is what it does when nobody is there to say.

Turning `/afk` on while a question is up answers it as nobody. So does a person who keeps
typing what the model refuses.

## When another flow calls yours

A flow that [calls one](/weaver/calling-flows) with an `Outworlder` role may leave the role
out, and the callee is handed the run's own: whoever is at the prompt, or nobody.

```python
await load(":talk")(
    task,
    agents={"assistant": agents["assistant"]},  # no "human" [!code highlight]
    envs=envs,
    params=FlowParams(),
)
```

It may also pass on the outworlder it was handed, which is the same person.

## Stand in for the person

Sometimes the caller means to answer for the person: a flow that runs `talk` with a script of
lines, or a supervisor that answers a callee's questions with a model of its own.
`Outworlder.new()` makes an outworlder the caller answers for, through `on_outworlder_run`:

```python
from hmz.flows import (
    Outworlder,
    OutworlderRunHookParams,
    OutworlderRunHookResult,
)

lines = iter(["and the tests", "thanks"])


async def typed(
    params: OutworlderRunHookParams,
) -> OutworlderRunHookResult:
    return OutworlderRunHookResult(output=next(lines, ""))


stand_in = Outworlder.new()  # [!code highlight]
stand_in.on_outworlder_run(typed)  # [!code highlight]
await load(":talk")(
    task,
    agents={"assistant": agents["assistant"], "human": stand_in},
    envs=envs,
    params=FlowParams(),
)
```

Every `run` of the callee's `human` now calls `typed`, with the `prompt` and the
`output_schema` it was asked for. The hook answers with `output`: text, or an instance of that
schema. It runs as the flow that hung it, so it may take a turn of one of the caller's agents
to answer:

```python
async def answered(
    params: OutworlderRunHookParams,
) -> OutworlderRunHookResult:
    thinking = await supervisor.spawn(env=workspace)
    if params.output_schema is None:
        said = await supervisor.run(params.prompt, session=thinking)
    else:
        said = await supervisor.run(
            params.prompt,
            session=thinking,
            output_schema=params.output_schema,
        )
    return OutworlderRunHookResult(output=said)
```

An `Outworlder.new()` with no hook hung on it is **away**. `on_outworlder_run` works only on
one made this way: on the run's own outworlder it raises `CapabilityNotGranted`, since the
person at the prompt answers for themselves.

## What it is not

An outworlder is not a coding agent. It runs no model and spends nothing.

- **It reaches none of a CLI's moments.** `on_stop` and the rest are there, since every agent
  has them, but a hook hung on one is never called.
- **It cannot be forked.** `fork` raises `UnsupportedOperation`.
- **It carries no skills.** `derive` with `skills=` raises `CapabilityNotGranted`.

## See also

- [You, as one of the agents](/features/human): the questionnaire, to click through
- [Questions](/user/questions)
- [Being away (/afk)](/user/afk)
- [Answers in a shape](/weaver/shapes)
- [Flows › The person at the prompt](/reference/flows#the-person-at-the-prompt)

<style scoped>
.asking-tty {
  margin: 16px 0 4px;
  padding: 14px 18px;
  border-radius: 12px;
  border: 1px solid var(--hmz-panel-border);
  background: var(--vp-code-block-bg);
  color: var(--vp-c-text-1);
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.asking-tty .said {
  color: var(--vp-c-warning-1);
}

.asking-tty .you {
  color: var(--vp-c-brand-1);
}

.asking-tty .dim {
  color: var(--vp-c-text-3);
}

.asking-tty-note {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--vp-c-text-3);
}
</style>

# Answers in a shape

Pass `run` a pydantic model as `output_schema=`, and the turn answers with an instance of that
model instead of prose. Reach for it whenever the flow has to decide something before it acts.

## Try it

A build loop that stops when a reviewer says there is nothing left to do:

```python
# .humanize/flows/reviewed/__init__.py
"""Build under review until the reviewer says there is nothing left."""

from pydantic import BaseModel, ConfigDict, Field

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    HarnessError,
    LocalEnv,
    flow,
)

REVIEW = """Read the repository and the current diff.
Decide whether there is anything left to do or to fix."""


class Review(BaseModel):  # [!code highlight]
    """What one round's review comes to."""

    model_config = ConfigDict(extra="forbid")

    done: bool = Field(
        description="True only if there is nothing left to do or to fix."
    )
    notes: str = Field(
        description="What to say to the agent, passed on word for word."
    )


class Agents(AgentCollection):
    actor: Agent
    reviewer: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def reviewed(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    actor, reviewer = agents["actor"], agents["reviewer"]
    workspace = envs["workspace"]
    working = await actor.spawn(env=workspace)
    await actor.run(task, session=working)
    for _ in range(12):
        # fresh each round: the reviewer reads the tree, not a story
        reading = await reviewer.spawn(env=workspace)
        try:
            review = await reviewer.run(
                REVIEW, session=reading, output_schema=Review  # [!code highlight]
            )
        except HarnessError:
            continue  # take the round again
        if review.done:  # [!code highlight]
            print("the reviewer says it is finished")
            return
        await actor.run(review.notes, session=working)  # [!code highlight]
    print("twelve rounds and it is still not done")
```

```sh
hmz exec -f reviewed -a actor=claude/claude-opus-5:max \
    -a reviewer=codex/gpt-5.6-sol:high -b cost=30 "$(cat TASK.md)"
```

What the shape buys the flow:

- **It branches on a field.** `review.done` is a `bool`, so the loop never searches a
  paragraph for the word "done".
- **The model is the question.** Its fields, their types, which are required and each
  `description` reach the agent, so the prompt does not repeat them.
- **The answer is typed.** `run` returns a `Review`, so a type checker reads `review.done` and
  `review.notes` too.

This is the shape of the official [`rlar`](/flows/rlar) flow.

## Which CLIs enforce it

Every CLI answers in the shape. Some enforce the schema themselves; the rest are prompted with
it, and humanize reads the model back out of what they say.

| Schema | CLI (`-a`) |
| --- | --- |
| <Badge type="tip" text="enforced" /> | `claude`, `codex`, `agy`, `grok`, `qwen` |
| <Badge type="info" text="prompted" /> | `cursor-agent`, `dsh`, `kimi`, `mimo`, `opencode`, `pi`, `zcode`, an ACP CLI |

Either way, `run` returns the model or raises.

## When the answer does not fit

An answer that cannot be read as the model raises `OutputSchemaError`. It is a `HarnessError`,
so the `except HarnessError` in the flow above catches it along with a turn that failed
outright. In a loop, both usually mean the same thing: take the round again. It is also a
`ValueError`.

## Writing the model

```python
class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")  # [!code highlight]

    done: bool = Field(
        description="True only if there is nothing left to do or to fix."  # [!code highlight]
    )
    notes: str = Field(
        description="What to say to the agent, passed on word for word."
    )
```

- **`extra="forbid"`.** An answer with a field nobody asked for is an answer to a different
  question.
- **A `description` on every field.** It is the only wording the agent sees for that field, so
  it does the work the prompt would otherwise do.
- **Keep it small.** Two or three fields is usually the whole of a decision. A model with
  thirty fields is a form, and a turn spent filling in a form is a turn not spent on the work.
- **Booleans for decisions, strings to pass on.** `done` steers the loop; `notes` becomes the
  next prompt word for word.

## Asking a person instead

Hand the same model to [the person as an agent](/weaver/human-agent), and they get a question
per field instead of a JSON Schema. The same decision can go to a model or to a person.

## See also

- [Answers in a shape](/features/shapes): what the shape moves, drawn
- [The person as an agent](/weaver/human-agent)
- [Testing a flow](/weaver/testing-flows)
- [Flows › Sessions and turns](/reference/flows#sessions-and-turns)

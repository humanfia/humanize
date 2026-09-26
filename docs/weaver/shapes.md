# Answers in a shape

A turn given an `output_schema` answers with an instance of that pydantic model instead of with
text. Reach for it whenever a flow has to decide something before it acts.

## Try it

Declare the answer as a pydantic model:

```python
from pydantic import BaseModel, ConfigDict, Field


class Review(BaseModel):
    """What one round's review comes to."""

    model_config = ConfigDict(extra="forbid")

    done: bool = Field(description="True only if there is nothing left to do or to fix.")
    notes: str = Field(description="What to say to the agent, passed on word for word.")
```

**The model *is* the question.** Its fields, their types, which are required, and the line each
was declared with are what the CLI is given, so nothing has to be repeated in the prompt.

Ask for it:

```python
review = await reviewer.run(REVIEW, session=reading, output_schema=Review)  # a Review
if review.done:
    return
await actor.run(review.notes, session=working)
```

You read `review.done` as a bool instead of searching the agent's prose for a word. `run` is
typed to answer with the model you asked for, so a type checker reads `review.done` too.

## Why a loop wants this

Is this finished? Does this plan belong to this repository? A loop asks that of a field rather
than of the end of a paragraph. That is what [`rlar`](/flows/rlar) ends on, and what
`humanize1` asks its analyst and its reviewer before it starts anything. Here is a whole flow
built on it:

```python
# .humanize/flows/reviewed/__init__.py
"""Build under review, and stop when the reviewer says there is nothing left."""

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


class Review(BaseModel):
    """What one round's review comes to."""

    model_config = ConfigDict(extra="forbid")

    done: bool = Field(description="True only if there is nothing left to do or to fix.")
    notes: str = Field(description="What to say to the agent, passed on word for word.")


class Agents(AgentCollection):
    actor: Agent
    reviewer: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def reviewed(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    actor, reviewer, workspace = agents["actor"], agents["reviewer"], envs["workspace"]
    working = await actor.spawn(env=workspace)
    await actor.run(task, session=working)
    for _ in range(12):
        reading = await reviewer.spawn(env=workspace)   # fresh: it reads the tree, not a story
        try:
            review = await reviewer.run(REVIEW, session=reading, output_schema=Review)
        except HarnessError:
            continue                                    # take the round again
        if review.done:
            print("the reviewer says it is finished")
            return
        await actor.run(review.notes, session=working)
    print("twelve rounds and it is still not done")
```

It asks the reviewer for a `Review` up to twelve times and stops as soon as `review.done` is
true:

```sh
hmz exec -f reviewed -a actor=claude/claude-opus-5:max -a reviewer=codex/gpt-5.6-sol:high \
    -b cost=30 "$(cat TASK.md)"
```

## How each CLI is held to it

| | |
| --- | --- |
| **Claude Code** | `--json-schema`; it validates the answer itself |
| **Antigravity**, **Grok Build**, **Qwen Code** | `--json-schema` on the run |
| **Codex** | the turn's `outputSchema`, held to what its structured outputs take |
| anything else — `dsh`, `kimi`, `pi`, `opencode`, `mimo`, `zcode` | asked in the prompt, and what it says is read back |

Either way the answer arrives as the model, or not at all.

Claude's schema is an argument of the process rather than of the turn. Asking one session for a
shape it was not started with ends that process and starts one that **resumes** the
conversation — the conversation is not restarted, only the process is.

## Failing

An answer that is not the shape it was asked for is a turn that did not do what it was told,
and raises `OutputSchemaError`:

```python
from hmz.flows import OutputSchemaError

try:
    review = await reviewer.run(REVIEW, session=reading, output_schema=Review)
except OutputSchemaError:
    ...                                   # take this round again
```

`OutputSchemaError` is a `HarnessError`, so `except HarnessError` covers it and a turn that
failed outright both — which is almost always what a loop wants: "take this round again". It is
a `ValueError` too.

## Asking a person: a questionnaire

Given a schema, [the person](/weaver/human-agent) is not shown a JSON Schema. They are asked a
question per field, and the model is built out of what they typed:

```python
from typing import Literal


class Settled(BaseModel):
    approach: Literal["fast", "careful"] = Field(
        default="careful", description="Which way should this be built?"
    )
    tests: bool = Field(default=True, description="Write tests for it?")
    rounds: int = Field(default=3, description="How many rounds may it take?")


asking = await human.spawn(env=workspace)
settled = await human.run("How should I do this?", session=asking, output_schema=Settled)
```

| In the model | What they are asked |
| --- | --- |
| `description=` | the question itself, or the field's name where it has none |
| `Literal[…]` | those words, as the answers it offers |
| `bool` | `yes` and `no` |
| a default | "or `-` for 3" — and a dash takes it |
| `list[str]` | one line, separated by commas |

Each question goes the road [a coding agent's own question](/user/questions) takes, so it is a
real question in the interface, options and all. What the model refuses is put back on the
field it was refused for, in the model's own words.

**Nobody may be there.** A run of `hmz exec`, or one where [`/afk`](/user/afk) is on, is one
whose person is *away*, and an away person answers at once: the schema built from its
defaults, where every field has one — which is why every field of `Settled` above has one — and
`OutworlderAway` where one does not. So a flow settles what only a person can settle in the
model it is going to run on, and says in the defaults what it does when nobody is there to say.

The same decision goes to a model or to a person in the same shape.

## Writing the model

- `extra="forbid"`. An answer with a field nobody asked for is an answer to a different
  question.
- A `description` on every field. It is the only wording the model sees for that field, and it
  does the work the prompt would otherwise do.
- Keep it small. A model with thirty fields is a form, and a turn that fills in a form is a
  turn that did not do the work. Two or three fields is usually the whole of a decision.
- Booleans for decisions, strings for what to pass on. `done` steers the loop; `notes` becomes
  the next prompt word for word.
- Defaults on a model a person is asked, for the run where nobody is there.

## See also

- [Questions](/user/questions)
- [The person as an agent](/weaver/human-agent)
- [Agents › Answering in a shape](/reference/agents#answering-in-a-shape)
- [Testing a flow](/weaver/testing-flows)

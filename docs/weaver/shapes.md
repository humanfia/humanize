# Answers in a shape

In this guide you have a turn answer with data your code can branch on, instead of prose. You
build `reviewed`: one agent builds, a second reviews, and the loop ends when the reviewer's
answer says `done`.

Reach for a shape whenever the flow has to decide something before it acts: whether to go
round again, which of two paths to take, what to pass on to the next agent.

::: info Before you start
- A flow of your own running: [Your first flow](/weaver/writing-a-flow).
- [pydantic](https://docs.pydantic.dev/) models. `pydantic` is installed with humanize.
- Two roles in one flow: [Build under test](/weaver/tutorials/build-under-test) is the gentle
  way in.
:::

## How it works

Pass `run` a pydantic model as `output_schema=`, and the turn answers with an instance of that
model:

```python
text = await agent.run("review it", session=session)  # str
review = await agent.run("review it", session=session, output_schema=Review)  # Review
```

The model is the question. Its fields, their types, which are required and each field's
`description` reach the agent as a JSON Schema, so the prompt does not have to repeat them.
Every CLI answers in the shape: some enforce the schema themselves, and the rest are prompted
with it and have the model read back out of what they say. Either way, `run` returns an
instance of the model or raises `OutputSchemaError`.

## Example: build until the reviewer is satisfied

```python
# .humanize/flows/reviewed/__init__.py
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


class Review(BaseModel):  # ①
    """What one round's review comes to."""

    model_config = ConfigDict(extra="forbid")  # ②

    done: bool = Field(description="True only if there is nothing left to do or to fix.")  # ③
    notes: str = Field(description="What to say to the agent, passed on word for word.")


class Agents(AgentCollection):
    actor: Agent
    reviewer: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def reviewed(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> bool:
    """Build under review until the reviewer says there is nothing left."""
    actor, reviewer = agents["actor"], agents["reviewer"]
    workspace = envs["workspace"]
    working = await actor.spawn(env=workspace)
    await actor.run(task, session=working)
    for _ in range(5):
        reading = await reviewer.spawn(env=workspace)  # ④
        try:
            review = await reviewer.run(REVIEW, session=reading, output_schema=Review)  # ⑤
        except HarnessError:  # ⑥
            continue
        print(f"review: done={review.done}")
        if review.done:  # ⑦
            return True
        await actor.run(review.notes, session=working)  # ⑧
    return False
```

### What each part does

1. **`class Review(BaseModel)`** is the shape of one answer. Two fields are the whole of the
   decision: whether it is finished, and what to say if it is not.
2. **`extra="forbid"`** refuses an answer with a field nobody asked for, which would be an
   answer to a different question.
3. **`Field(description=…)`** is the only wording the agent sees for that field, so it does the
   work a prompt would otherwise do. Write one on every field.
4. **A fresh reviewer session every round.** The reviewer reads the tree as it is, not a story
   of how it got there, so an earlier round cannot talk it into approving.
5. **`output_schema=Review`** makes the turn answer with a `Review`. A type checker knows it,
   so `review.done` and `review.notes` are checked too.
6. **`except HarnessError`** takes the round again when the turn failed. An answer that cannot
   be read as the model raises `OutputSchemaError`, which is a `HarnessError`, so a malformed
   review and a failed turn are handled alike.
7. **`review.done`** is a `bool`. The loop branches on a field, never on a search of a
   paragraph for the word "done".
8. **`review.notes`** goes to the actor word for word, in the actor's own session, which
   remembers the work it is being asked to fix.

This is the shape of the official [`rlar`](/flows/rlar) flow.

### Run it

Put a different CLI in each role, so the reviewer does not share the builder's blind spots:

```sh
hmz exec -f reviewed -a actor=claude/claude-sonnet-5-5:high \
    -a reviewer=codex/gpt-5.6-sol:high -b cost=1 \
    "Add subtract(a, b) to calc.py, with a check for it in check.py."
```

A real run, abridged:

```text
● actor is working
● Read(/home/you/calc/calc.py)
● Read(/home/you/calc/check.py)
● Edit(/home/you/calc/calc.py)
● Edit(/home/you/calc/check.py)
● Bash(cd /home/you/calc && python3 check.py)
● I added `subtract(a, b)` to `calc.py` and a check for it in `check.py`, which asserts `subtract(5, 3) == 2`. …
✻ input 8 · output 618 · cache_read 61.8k · cache_write 6.1k · $0.03 · claude-sonnet-5-5 · actor
…
✻ Worked for 7s · actor
● reviewer is working
● {"done":false,"notes":"I’m inspecting the repository instructions, current diff, and relevant tests now. …"}
● Bash(/bin/bash -lc "git diff -- calc.py check.py && …")
● Bash(/bin/bash -lc 'git log --oneline --decorate -8 && git ls-tree -r --name-only HEAD && git diff --check && python che)
● {"done":true,"notes":"No issues found. `subtract(a, b)` is implemented correctly, the check covers the new behavior, `python check.py` passes, and `git diff --check` reports no whitespace errors. …"}
✻ input 90.1k · output 1.0k · gpt-5.6-sol · reviewer
…
✻ Worked for 61s · reviewer
review: done=True
```

- **The reviewer's messages are JSON in the shape of `Review`.** Codex enforces the schema on
  everything it says, so even its progress note is a `Review`. Only the answer the turn ends
  on is what `run` returns.
- **`review: done=True`** is the flow's own `print`. The first review found nothing to fix, so
  the flow returned `True` without a second round.

## Check it worked

`git diff` shows the actor's work. The loop itself is tested with a scripted reviewer, which
answers with mappings that are read into `Review` exactly as a real answer is:

```python
# tests/test_reviewed.py
from hmz.sdk import fakes

DONE = {"done": True, "notes": ""}


async def test_it_passes_the_notes_on_until_the_reviewer_is_done() -> None:
    actor = fakes.FakeAgentDriver()
    reviewer = fakes.FakeAgentDriver(
        reply=[{"done": False, "notes": "check subtract too"}, DONE]  # ①
    )

    done = await fakes.run_fake(
        "reviewed", "add subtract", agents={"actor": actor, "reviewer": reviewer}
    )

    assert done is True
    assert actor.prompts == ["add subtract", "check subtract too"]  # ②


async def test_an_answer_out_of_shape_is_taken_again() -> None:
    reviewer = fakes.FakeAgentDriver(reply=[{"done": "maybe"}, DONE])  # ③

    done = await fakes.run_fake("reviewed", "x", agents={"reviewer": reviewer})

    assert done is True
    assert len(reviewer.prompts) == 2
```

```text
..                                                                       [100%]
2 passed in 0.10s
```

1. **A list of replies** answers turn by turn: first a review that is not done, then one that is.
2. **The notes reach the actor word for word**, as its second prompt.
3. **`{"done": "maybe"}`** cannot be read as a `Review`, so the turn raises
   `OutputSchemaError`, the flow takes the round again, and the second answer ends it.

## Which CLIs enforce it

| Schema | CLI (`-a`) |
| --- | --- |
| <Badge type="tip" text="enforced" /> | `claude`, `codex`, `agy`, `grok`, `mcode`, `qwen` |
| <Badge type="info" text="prompted" /> | `cursor-agent`, `dsh`, `kimi`, `mimo`, `opencode`, `pi`, an ACP CLI |

A prompted CLI is more likely to answer out of shape, which is one more reason to catch
`HarnessError` around the turn.

## Variations

**More than two outcomes.** Use an enum or a `Literal` field when the decision has several
answers:

```python
from typing import Literal


class Triage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: Literal["fix", "test", "ask"] = Field(description="What the next step is.")
    why: str = Field(description="One sentence, for the log.")
```

**Ask a person instead.** Hand the same model to [the person as an agent](/weaver/human-agent),
and they get a question per field instead of a JSON Schema. The same decision can go to a
model or to a person.

## Pitfalls

- **Keep it small.** Two or three fields is usually the whole of a decision. A model with
  thirty fields is a form, and a turn spent filling in a form is a turn not spent on the work.
- **Booleans for decisions, strings to pass on.** `done` steers the loop, and `notes` becomes
  the next prompt word for word. A free-text field the code branches on is prose again.
- **Catch `HarnessError`, not `Exception`.** `except Exception` would also swallow a spent
  budget, and the loop would spin. See [Loops](/weaver/loops).
- **Bound the loop.** A reviewer that is never satisfied would keep the actor going until the
  budget ends the run. `reviewed` gives up after five reviews and returns `False`.

## Next steps

- [Answers in a shape](/features/shapes): what the shape moves, drawn
- [The person as an agent](/weaver/human-agent)
- [Testing a flow](/weaver/testing-flows)
- [Reference › `Agent.run`](/reference/flows#run) and
  [Sessions and turns](/reference/flows#sessions-and-turns)

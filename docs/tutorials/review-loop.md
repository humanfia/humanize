---
title: Build an actor–reviewer loop under test
description: Write a flow in which one agent works on a goal until a second agent approves it, test it with scripted agents, then run it on real ones.
---

# Build an actor–reviewer loop under test

Write a flow with two roles: an actor that works on a goal, and a reviewer that answers with a typed verdict. The flow loops until the reviewer approves. You write the test first with scripted agents, then run the flow on real ones.

![The loop: the actor works on the goal, a fresh reviewer returns a verdict, notes go back to the actor until the verdict is approved or the rounds run out](/diagrams/tutorials-review-loop-1.svg)

## What you need

- `hmz` installed, and one coding agent signed in. This page uses Claude Code. See [Coding agents](/user/agents).
- [uv](https://github.com/astral-sh/uv), to run the tests.
- A project in git. This page uses `~/shop`.

## 1. Make a place for the flow

Create a directory for the flow under `.hmz/flows/` and one for its tests:

```sh
cd ~/shop
mkdir -p .hmz/flows/review_loop .hmz/tests
```

The directory name sets the flow's name. You run it as `@local/review_loop`.

## 2. Declare the roles and the verdict

Save this stub flow as `.hmz/flows/review_loop/__init__.py`. It declares the loop's types and takes a single turn.

```python
# .hmz/flows/review_loop/__init__.py
import pydantic

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    GoalCommandAgentMixin,
    LocalEnv,
    Permission,
    flow,
)


class Verdict(pydantic.BaseModel):
    """What the reviewer decides."""

    approved: bool = pydantic.Field(description="True only if the goal is met.")
    notes: str = pydantic.Field(description="What to fix, said to the actor as it is.")


class Actor(Agent, GoalCommandAgentMixin):
    """Does the work."""


class Reviewer(Agent):
    """Reads the work and changes nothing."""

    _permission = Permission("read-only")


class Agents(AgentCollection):
    actor: Actor
    reviewer: Reviewer


class Envs(EnvCollection):
    workspace: LocalEnv


class Params(FlowParams):
    rounds: int = 3


@flow(agents=Agents, envs=Envs, params=Params)
async def review_loop(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> bool:
    """An actor works on a goal until a reviewer approves it."""
    actor = agents["actor"]
    await actor.run(f"/goal {task}", session=await actor.spawn(), env=envs["workspace"])
    return False
```

| Class | Role in the flow |
| --- | --- |
| `Verdict` | Defines the reviewer's response. Each field's `description` goes to the agent with the schema, as the instruction for that field. |
| `Actor` | Includes `GoalCommandAgentMixin` so the flow can send `/goal`. The agent works until it judges the goal met. |
| `Reviewer` | Uses the `read-only` permission to read the project without changing it. |
| `Params` | Defines the `rounds` setting with a default of 3. |

## 3. Write the test first

Save this test file as `.hmz/tests/test_review_loop.py`:

```python
# .hmz/tests/test_review_loop.py
from hmz.sdk import fakes


async def test_notes_go_back_until_approved() -> None:
    actor = fakes.FakeAgentDriver()
    reviewer = fakes.FakeAgentDriver(
        reply=[
            {"approved": False, "notes": "cover the empty cart"},
            {"approved": True, "notes": ""},
        ]
    )

    approved = await fakes.run_fake(
        "review_loop", "add a coupon", agents={"actor": actor, "reviewer": reviewer}
    )

    assert approved is True
    assert actor.prompts == ["/goal add a coupon", "cover the empty cart"]
    assert len(reviewer.sessions) == 2


async def test_it_gives_up_after_its_rounds() -> None:
    reviewer = fakes.FakeAgentDriver(reply={"approved": False, "notes": "not yet"})

    approved = await fakes.run_fake(
        "review_loop",
        "add a coupon",
        agents={"reviewer": reviewer},
        params={"rounds": 2},
    )

    assert approved is False
    assert len(reviewer.prompts) == 2
```

`run_fake` runs the flow with a `FakeAgentDriver` in each role, which answers from a script at once.

![The same flow run two ways: hmz exec gives its roles real coding agents, run_fake gives them scripted FakeAgentDriver replies](/diagrams/tutorials-review-loop-2.svg)

A list in `reply` gives one answer per turn, and a mapping is parsed as the `Verdict`. Any role you omit gets a fake that answers `ok`. On each fake, `prompts` records every prompt received and `sessions` records every session opened.

The first test checks that reviewer notes become the actor's next prompt and that each review opens a new session. The second test checks that the flow stops after `rounds` rounds.

## 4. Watch the test fail

Run the tests from the project root:

```sh
uvx --with hmz --with pytest-asyncio pytest -q -o asyncio_mode=auto .hmz/tests
```

`uvx` runs pytest with `hmz` and pytest-asyncio without installing them in your project. Both tests fail because the stub flow never calls the reviewer.

![pytest's output: both tests fail, the first on assert approved is True, the second because the reviewer was sent no prompt](/shots/tutorials-review-loop-red.svg)

## 5. Write the loop

Replace the function at the end of `.hmz/flows/review_loop/__init__.py` with the full loop:

```python
@flow(agents=Agents, envs=Envs, params=Params)
async def review_loop(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> bool:
    """An actor works on a goal until a reviewer approves it."""
    actor, reviewer = agents["actor"], agents["reviewer"]
    workspace = envs["workspace"]
    work = await actor.spawn()
    prompt = f"/goal {task}"
    for _ in range(params.rounds):
        await actor.run(prompt, session=work, env=workspace)
        verdict = await reviewer.run(
            f"Review the change in this repository. The goal: {task}",
            session=await reviewer.spawn(),
            env=workspace,
            output_schema=Verdict,
        )
        if verdict.approved:
            return True
        prompt = verdict.notes
    return False
```

The actor's `spawn` stays outside the loop so it keeps one session and remembers every round. The reviewer's `spawn` sits inside the loop so each review starts fresh. Passing `output_schema=Verdict` makes `run` return a `Verdict` instance. If `verdict.approved` is false, `verdict.notes` becomes the actor's next prompt. If the loop finishes `params.rounds` rounds without approval, it returns `False`.

## 6. Run the tests again

Run the pytest command again. Both tests pass in about a second without starting an agent.

![The test command run twice: two tests fail before the loop is written, and pass after it](/shots/tutorials-review-loop-test.svg)

*Before the loop, and after it.*

## 7. Run it on real agents

Run the flow with `-a` to assign each role an agent and `-p` to set the required budget:

```sh
hmz exec -f @local/review_loop \
    -a actor=claude/claude-haiku-4-5 -a reviewer=claude/claude-haiku-4-5 \
    -p budget.output_tokens=20000 "Add a coupon code to checkout"
```

The actor edits the project, and the reviewer responds with JSON that `run` parses as a `Verdict`. When a verdict is not approved, the actor receives the notes and tries again.

![The command's output: the actor edits and tests, the reviewer answers approved false with notes, the actor adds a test, and a second reviewer answers approved true](/shots/tutorials-review-loop-exec.svg)

*Two rounds: the first verdict sends notes back, the second approves.*

Your output will vary and may take one to three rounds. Pass `-p rounds=5` to allow more rounds.

## 8. Read the run in the app

Open Humanize Desktop or run `hmz web`, then select the recorded epic under your project in the sidebar. The graph shows both roles and the handovers between them.

![Humanize Desktop on the finished epic: the actor with one session of two turns, the reviewer with two sessions, and arrows counting the handovers between them](/shots/tutorials-review-loop-epic.svg)

*One session for the actor, a new one for each review.*

Click the **Exomyth** icon (the chart) at the top right of the epic to inspect every turn and tool call on a timeline.

![The epic's trace in Humanize Desktop: the actor's two turns with their tool calls on one row, and each review on a row of its own](/shots/tutorials-review-loop-trace.svg)

## What you did

- Declared an actor, a read-only reviewer, and a typed verdict.
- Tested the flow logic with `run_fake` and `FakeAgentDriver`.
- Wrote a loop that stops on approval or after `rounds` rounds.
- Ran the flow on real agents under a budget and inspected the epic.

## Next

- [Test a flow](/builder/testing): scripted environments, people and budgets.
- [Typed answers](/builder/shapes): what happens when an answer does not fit the model.
- [Goals](/builder/goals): what `/goal` does, and which coding agents serve it.
- [Loops](/builder/loops): what a session remembers, and what ends a loop.

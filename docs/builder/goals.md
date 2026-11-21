---
title: Goals
description: Hand an agent an objective with /goal so it works until it judges the objective met, declare the role that needs it, and use the harness's /loop command.
---

# Goals

A goal is an objective you hand to an agent in place of a prompt. The agent works turn after turn until it judges the objective met. Your flow makes one `run` call and waits.

![One run with a /goal prompt: the harness works turn after turn until the agent judges the objective met, then run returns the last message](/diagrams/builder-goals-1.svg)

## Set a goal from a flow

To set a goal:

1. Add `GoalCommandAgentMixin` to the role's type.
2. Start the `run` prompt with `/goal`, followed by the objective.

```python
# .hmz/flows/aim/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    GoalCommandAgentMixin,
    LocalEnv,
    flow,
)


class Worker(Agent, GoalCommandAgentMixin): ...


class Agents(AgentCollection):
    worker: Worker


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def aim(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """The task, set once as the agent's own goal."""
    worker = agents["worker"]
    session = await worker.spawn()
    return await worker.run(f"/goal {task}", session=session, env=envs["workspace"])
```

Humanize passes the objective to the harness's native goal command instead of sending `/goal` to the model as text. The harness runs for as many turns as it needs, and `run` returns the agent's last message when the goal is met.

The mixin has no methods. It declares that the role may send `/goal`, so only a harness with a goal command can fill it.

To run a goal without writing a flow, install the official `goal` flow from the [catalogue](https://humanfia.ai/flows/).

## Run the flow

Write an objective the agent can verify for itself.

### In the app

Start the flow from **New epic** (see [Flows](/user/flows)), then open the epic and select the worker's session. The thread shows the `/goal` prompt from the flow, everything the agent did, and where it stopped.

![The epic's thread in the app: one /goal prompt, then edits and test runs, then the agent's last message](/shots/builder-goals-thread.svg)

*One prompt and one turn for the flow, however long the agent worked.*

### From the command line

```sh
hmz exec -f @local/aim -a worker=claude/claude-haiku-4-5 \
    -p budget.output_tokens=20000 \
    "checkout takes a coupon code, and pytest -q passes"
```

![hmz exec running the aim flow: the worker edits, runs the tests, edits again, and ends on its last message](/shots/builder-goals-exec.svg)

`run` returns the agent's final message, which `aim` returns as its output.

## Check harness support

| Harness (`-a`) | `/goal` | `/loop` |
| --- | :-: | :-: |
| `claude` | yes | yes |
| `codex` | yes | no |
| `kimi` | yes | no |
| `dsh` | yes | no |
| `acp`, `agy`, `cursor-agent`, `grok`, `litellm`, `mcode`, `mimo`, `omp`, `opencode`, `pi`, `qwen` | no | no |

A harness without the command cannot fill a role that declares the mixin. `hmz exec` refuses before the epic starts:

![hmz exec refusing the aim flow for pi: 'worker' needs GoalCommandAgentMixin, which pi does not support](/shots/builder-goals-refused.svg)

In the terminal, the role picker lists only compatible harnesses. In Python, this raises `CapabilityMissing`.

See [Agents and harnesses](/reference/agents) for full harness capabilities, and [Agent roles](/builder/agents) for declaring roles and mixins.

## Repeat a task with `/loop`

Declare `LoopCommandAgentMixin` on a role to use `/loop <interval> <task>`, the harness's recurring task command. Only `claude` supports it. Humanize passes the prompt to the harness unchanged.

```python
class Watcher(Agent, LoopCommandAgentMixin): ...


class Agents(AgentCollection):
    watcher: Watcher
```

```python
await watcher.run("/loop 10m check CI", session=session, env=envs["workspace"])
```

Import `LoopCommandAgentMixin` from `hmz.flows`. To control a loop from your flow instead, write it in Python (see [Loops](/builder/loops)).

## Choose who decides the work is done

| Way | Who decides | Works on |
| --- | --- | --- |
| `/goal` | The agent, against the objective | `claude`, `codex`, `kimi`, `dsh` |
| A stop hook that blocks | Your code, each time a turn is about to end | Every harness |
| A loop in the flow | Your code, between turns | Every harness |

See [Hooks](/builder/hooks) for stop hooks.

## Test the flow

A fake agent emulates `claude` by default, or any harness you name, with that harness's exact capabilities. Use it to test both the prompt and the refusal (see [Test a flow](/builder/testing)).

```python
# tests/test_aim.py
import pytest

from hmz.flows import CapabilityMissing
from hmz.sdk import fakes


async def test_the_task_becomes_a_goal() -> None:
    worker = fakes.FakeAgentDriver()

    await fakes.run_fake("aim", "ship it", agents={"worker": worker})

    assert worker.prompts == ["/goal ship it"]


async def test_a_harness_without_goals_is_refused() -> None:
    pi = fakes.FakeAgentDriver("pi")

    with pytest.raises(CapabilityMissing):
        await fakes.run_fake("aim", "ship it", agents={"worker": pi})
```

## Good to know

- A role without the mixin cannot send the command, even on `claude`. `run` raises `CapabilityNotGranted` before sending: `worker: /goal needs GoalCommandAgentMixin on the role`. The same applies to `/loop` without `LoopCommandAgentMixin`.
- Start the prompt with exactly `/goal` and one space, with nothing before it. Only that form sets the harness's goal; a prompt with whitespace before `/goal`, or with a tab or newline after it, reaches the harness as ordinary text.
- The role needs the mixin whenever the prompt, after leading whitespace, is `/goal` alone or `/goal` followed by whitespace. `/goals` is an ordinary prompt.
- Humanize interprets no other slash command and passes every other prompt to the harness unchanged.
- Every turn of a goal spends the epic's budget. Set a budget to stop a goal that never settles (see [Budgets in a flow](/builder/budgets)).
- Vague objectives like "Make it better" never settle. Give the agent a condition it can check.
- A stop hook still runs when the goal ends. If it blocks, the turn continues with the hook's reason as an ordinary prompt, not as a new goal.
- A goal does not hold the harness to an `output_schema`. Humanize only reads the last message as that model, and raises `OutputSchemaError` if it is not one, so ask for the JSON in the objective.
- Call `run` with `/goal` again to set a fresh goal in the same session.

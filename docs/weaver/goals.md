# Goals

Give an agent a **goal** instead of a prompt, and it keeps working until it judges the
objective met. Your flow waits on one `run`, and the CLI takes as many turns as the objective
needs. Reach for a goal when "is it done?" is something the model should judge.

## Try it

The official [`goal`](/flows/goal) flow does exactly this. Run it on a task file:

```sh
hmz exec -f goal -a worker=claude/claude-opus-5:max -b cost=20 \
    "$(cat TASK.md)"
```

This is all of it:

```python
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


class Worker(Agent, GoalCommandAgentMixin): ...  # [!code highlight]


class Agents(AgentCollection):
    worker: Worker


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def goal(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    worker = agents["worker"]
    session = await worker.spawn(env=envs["workspace"])
    await worker.run(f"/goal {task}", session=session)  # [!code highlight]
```

Two lines make it a goal:

- **`/goal <objective>` as the prompt.** The objective goes to the CLI's own goal feature.
  `run` returns once the agent says the objective is met, with what it said last.
- **`GoalCommandAgentMixin` on the role.** Only a CLI that has a goal feature can fill it.

Every turn the goal takes counts against the run's [budget](/features/allowances), so `-b` is
what bounds a goal that never settles.

## Which CLIs have one

| CLI (`-a`) | `/goal` | `/loop` |
| --- | :---: | :---: |
| `claude` · Claude Code | <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> |
| `codex` · Codex | <Badge type="tip" text="yes" /> | <Badge type="info" text="no" /> |
| `kimi` · Kimi Code | <Badge type="tip" text="yes" /> | <Badge type="info" text="no" /> |
| `zcode` · ZCode | <Badge type="tip" text="yes" /> | <Badge type="info" text="no" /> |
| `dsh` · DeepSeek Harness | <Badge type="tip" text="yes" /> | <Badge type="info" text="no" /> |
| `agy`, `cursor-agent`, `grok`, `mimo`, `opencode`, `pi`, `qwen`, an ACP CLI | <Badge type="info" text="no" /> | <Badge type="info" text="no" /> |

Every CLI and every capability is in one table [on
Flows](/reference/flows#what-each-harness-serves).

## The role says it needs one

The mixin is how the flow says so, and humanize holds the flow to it both ways.

**A CLI without a goal feature is refused before the first turn**, not an hour into a loop:

```console
$ hmz exec -f goal -a worker=pi/openai-codex/gpt-5.5:high -b cost=5 \
    "fix the build"
hmz exec: error: goal: 'worker' needs GoalCommandAgentMixin, which pi does not do
```

At the prompt, `/flow` offers only the CLIs that have one for that role.

**A role without the mixin cannot set a goal.** A `/goal` prompt on a plain `Agent` raises
`CapabilityNotGranted`, even on Claude Code. A flow that never declared goals cannot start one
by accident.

## A recurring task: `/loop`

`/loop <interval> <task>` is Claude Code's own recurring task. A role that sends one declares
`LoopCommandAgentMixin`, so only Claude Code can fill it, and the prompt goes to the CLI as
written. Without the mixin, a `/loop` prompt raises `CapabilityNotGranted`.

## When your code should decide instead

A goal lets the model judge. When a function can judge, such as an unticked box or a failing
test, hang an `on_stop` [hook](/weaver/hooks) instead. That is an async function humanize calls
each time a turn is about to end. Answer `block=True` with a `reason`, and the agent keeps
going with that reason as its next prompt:

```python
from hmz.flows import StopHookParams, StopHookResult


async def unfinished(params: StopHookParams) -> StopHookResult:
    # the workspace's role declares FilesEnvMixin, so the flow can read it
    if params.again < 5 and b"- [ ]" in await workspace.read("TASK.md"):  # [!code highlight]
        return StopHookResult(
            block=True, reason="TASK.md still has unticked boxes."
        )
    return StopHookResult()  # an empty result lets the turn end


worker.on_stop(unfinished)
await worker.run(task, session=session)
```

`params.again` counts how many times this turn has already been kept going, so the hook can
give up. `on_stop` is on every agent, so it needs no mixin and works on every CLI.

| | Decides it is done | Costs | Works on |
| --- | --- | --- | --- |
| `/goal` | the **model**, against the objective | turns until the model says so | 5 CLIs |
| a blocking `on_stop` | **your code**, against whatever it can read | one more turn per block, bounded by `again` | every CLI |

## See also

- [It decides when it is done](/features/goals): the goal, drawn beside the stop hook
- [Hooks](/weaver/hooks): every moment a flow can hang one on
- [Flows › Asking for an agent that can do
  something](/reference/flows#asking-for-an-agent-that-can-do-something)

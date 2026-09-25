# Goals

A session can be given a **goal** instead of a prompt. The agent decides for itself when it has
met the objective, and until it does, a turn that would have ended starts another. Reach for a
goal when the stopping condition is something the model should judge, not something you can put
in a single prompt.

## Try it

```python
await worker.run("/goal the suite passes and nothing has been stubbed out", session=session)
```

A prompt that starts `/goal` is not sent as a prompt. It goes to the CLI's own goal feature —
the one its `/goal` command reaches — with everything after the word as the objective. The CLI
starts the extra turns itself; `run` follows the goal across all of them and answers with the
last. What they spend counts against the run's [budget](/features/budgets) like any other turn.

A goal that goes quiet has stopped because the goal itself said so. A flow that loops over it
runs the objective again; it does not nudge an agent that stopped early:

```python
while True:
    session = await worker.spawn(env=workspace)
    await worker.run(f"/goal {task}", session=session)
```

## Ask for an agent that has one

A goal is something only some CLIs can do, so a flow that sets one says so on the role, by
mixing `GoalCommandAgentMixin` into its type:

```python
from hmz.flows import Agent, AgentCollection, GoalCommandAgentMixin


class Worker(Agent, GoalCommandAgentMixin):
    """The one it drives, which has to have a goal of its own."""


class Agents(AgentCollection):
    worker: Worker
```

That does two things. An agent handed to `worker` whose CLI has no goal feature is refused
before the first turn rather than an hour into a loop:

```console
$ hmz exec -f pursuing -a worker=pi/openai-codex/gpt-5.5:high -b cost=5 "fix the build"
hmz exec: error: pursuing:pursuing: 'worker' needs GoalCommandAgentMixin, which pi does not serve
```

And a role that did **not** declare it cannot set one, whichever CLI fills it: a `/goal` prompt
on a plain `Agent` raises `CapabilityNotGranted`, even on Claude Code. A flow gets exactly what
it declared, so a flow that never asked for goals is a flow that cannot start one by accident.

Opening that flow in `/flow` offers only the CLIs that have one, so there is no wrong choice to
make.

## Which CLIs have one

| CLI | `/goal` | `/loop` |
| --- | --- | --- |
| Claude Code | yes | yes |
| Codex | yes | no |
| Kimi Code | yes | no |
| ZCode | yes | no |
| DeepSeek Harness | yes | no |
| cursor-agent, opencode, MiMo Code, Qwen Code, Grok Build, pi, Antigravity, an ACP CLI | no | no |

The whole table of what each CLI serves is [on Flows](/reference/flows#what-each-harness-serves).

## A recurring task: `/loop`

`LoopCommandAgentMixin` is the same bargain for Claude Code's own `/loop <interval> <task>`: a
role that declares it may send one, and the prompt goes to the CLI as it is, which runs the
task again on the interval for as long as the turn lasts. Only Claude Code serves it. Without
the mixin, a `/loop` prompt raises `CapabilityNotGranted`.

## A goal by hand: blocking `STOP`

A goal written by hand is a `STOP` [hook](/weaver/hooks) that blocks: the turn is not over
until the hook lets it be. Hang one on a CLI with no goal feature, or when the condition is
something a function can check rather than something the model should judge:

```python
from hmz.flows import StopHookParams, StopHookResult


async def unfinished(params: StopHookParams) -> StopHookResult:
    if params.again < 5 and b"- [ ]" in await workspace.read("TASK.md"):
        return StopHookResult(block=True, reason="TASK.md still has unticked boxes.")
    return StopHookResult()


worker.on_stop(unfinished)
await worker.run(task, session=session)
```

`params.again` counts how many times this turn has already been kept going, so a hook that
keeps blocking can use it to decide when to stop. `on_stop` is on every agent: it needs no
mixin, and every CLI reaches it.

| | Decides it is done | Costs |
| --- | --- | --- |
| `/goal` | the **model**, against the objective in its own words | turns you did not ask for, until it says so |
| a blocking `STOP` hook | **your code**, against whatever it can read | one extra turn per block, bounded by `again` |

## The flow that is this

[`goal`](/flows/goal) sets the task once as the agent's own goal, in a role called `worker`:

```sh
hmz exec -f goal -a worker=claude/claude-opus-5:max -b cost=20 "$(cat TASK.md)"
```

## See also

- [Hooks](/weaver/hooks)
- [It decides when it is done](/features/goals)
- [Flows › Asking for an agent that can do
  something](/reference/flows#asking-for-an-agent-that-can-do-something)

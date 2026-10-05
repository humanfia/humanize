# Goals

In this guide you hand an agent a **goal** instead of a prompt: an objective it keeps working
on, turn after turn, until it judges the objective met. You write `aim`, a flow that sets its
task as a goal, run it, and then write `ticked`, which gets the same effect on any CLI by
letting your own code decide when the work is done.

Reach for a goal when "is it done?" is something the model should judge. When a line of code
can judge it, such as a failing test or an unticked box, reach for the
[stop hook](#when-your-code-should-decide-instead) instead.

::: info Before you start
- A flow of your own running: [Your first flow](/weaver/writing-a-flow).
- A CLI with a goal feature signed in: Claude Code, Codex, Kimi Code or DeepSeek Harness. See
  [Which CLIs have one](#which-clis-have-one).
:::

## How it works

A prompt that starts with `/goal ` is not sent to the model as words. humanize hands the rest
of it to the CLI's own goal feature, and the CLI keeps taking turns against the objective
until it says the objective is met. Your flow waits on one `run` the whole time, and `run`
returns what the agent said last.

Two things make a goal:

- **`/goal <objective>` as the prompt** of a `run`.
- **`GoalCommandAgentMixin` on the role's type.** A role says what it needs of an agent by the
  mixins on its type, and only a CLI with a goal feature can fill one that carries this mixin.

Every turn the goal takes counts against the run's [budget](/features/allowances), so the
budget is what bounds a goal that never settles.

## Example: the task as a goal

`aim` is the official [`goal`](/flows/goal) flow under a name of your own, returning the
answer it ended on:

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


class Worker(Agent, GoalCommandAgentMixin): ...  # ①


class Agents(AgentCollection):
    worker: Worker  # ②


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def aim(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """The task set once as the agent's own goal."""
    worker = agents["worker"]
    session = await worker.spawn()
    return await worker.run(f"/goal {task}", session=session, env=envs["workspace"])  # ③
```

### What each part does

1. **`class Worker(Agent, GoalCommandAgentMixin)`** is a role type that asks for a goal
   feature. The class body is empty: the mixin is a declaration, and the runtime supplies what
   it declares.
2. **`worker: Worker`** gives the role that type. Whoever runs the flow can only fill `worker`
   with a CLI that has a goal feature, and is told so before anything runs.
3. **`run(f"/goal {task}", …)`** hands the task to the CLI's goal feature. `run` returns once
   the agent says the objective is met, with what it said last, however many turns it took.

### Run it

Write the objective as something the agent can check for itself:

::: code-group

```sh [Claude Code]
hmz exec -f aim -a worker=claude/claude-sonnet-5-5:high -p budget.cost=1 \
    "calc.py has a subtract function, and python3 check.py still prints ok"
```

```sh [Codex]
hmz exec -f aim -a worker=codex/gpt-5.6-sol:high -p budget.cost=1 \
    "calc.py has a subtract function, and python3 check.py still prints ok"
```

:::

A real run on Claude Code, where `check.py` asserts `add(2, 3) == 5`:

```text
● worker is working
● Goal set: calc.py has a subtract function, and python3 check.py still prints ok
● Goal acknowledged: add a `subtract` function to calc.py while keeping `python3 check.py` printing ok. Let me look at the files.
● Read(/home/you/calc/calc.py)
● Read(/home/you/calc/check.py)
● Edit(/home/you/calc/calc.py)
● Bash(cd /home/you/calc && python3 check.py)
● I added `subtract(a, b)` to `calc.py`, and `python3 check.py` still prints `ok`. …
✻ input 9 · output 520 · cache_read 41.8k · cache_write 10.4k · $0.04 · claude-sonnet-5-5 · worker
I added `subtract(a, b)` to `calc.py`, and `python3 check.py` still prints `ok`. …
✻ Worked for 9s · worker
```

- **`● Goal set: …`** is the CLI taking the objective as its own goal.
- **`● Bash(… python3 check.py)`** is the agent checking the objective, which is why an
  objective it can check is worth writing.
- **The line after `✻ input …`** is what `run` returned, and so what `aim` returns.

On Codex, the run prints the answer the goal ended on once it is met:

```text
Implemented `subtract(a, b)` in [calc.py](/home/you/calc/calc.py:5).

Verified:

- `subtract(7, 4) == 3`
- `python3 check.py` prints `ok`

Completed in about 46 seconds.
```

### Check it worked

`git diff` shows the change, and the objective is yours to check again: `python3 check.py`.

The flow itself is tested on a fake agent. A fake is one CLI, Claude Code unless you name
another, and serves exactly what that CLI serves, so the refusal is testable too:

```python
# tests/test_goals.py
import pytest

from hmz.flows import CapabilityMissing
from hmz.sdk import fakes


async def test_the_task_becomes_a_goal() -> None:
    worker = fakes.FakeAgentDriver()  # ①

    await fakes.run_fake("aim", "ship it", agents={"worker": worker})

    assert worker.prompts == ["/goal ship it"]


async def test_a_cli_without_goals_is_refused() -> None:
    pi = fakes.FakeAgentDriver("pi")  # ②

    with pytest.raises(CapabilityMissing):
        await fakes.run_fake("aim", "ship it", agents={"worker": pi})
```

1. **A fake Claude Code** serves `GoalCommandAgentMixin`, so the flow runs, and `prompts` shows
   the task went out as a goal.
2. **A fake pi** has no goal feature, so `run_fake` refuses the flow with `CapabilityMissing`
   before the first turn, as `hmz exec` would.

## Which CLIs have one

| CLI (`-a`) | `/goal` | `/loop` |
| --- | :---: | :---: |
| `claude` · Claude Code | <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> |
| `codex` · Codex | <Badge type="tip" text="yes" /> | <Badge type="info" text="no" /> |
| `kimi` · Kimi Code | <Badge type="tip" text="yes" /> | <Badge type="info" text="no" /> |
| `dsh` · DeepSeek Harness | <Badge type="tip" text="yes" /> | <Badge type="info" text="no" /> |
| `agy`, `cursor-agent`, `grok`, `mcode`, `mimo`, `opencode`, `pi`, `qwen`, an ACP CLI | <Badge type="info" text="no" /> | <Badge type="info" text="no" /> |

A CLI without one is refused before the first turn, not an hour into a loop:

```sh
hmz exec -f aim -a worker=mcode/MiniMax-M3:high -p budget.cost=1 "fix the build"
```

```text
hmz exec: error: aim: 'worker' needs GoalCommandAgentMixin, which mcode does not support
```

At the prompt, `/flow` offers only the CLIs that have one for that role. Every CLI and every
capability is in one table [on Flows](/reference/flows#what-each-harness-serves).

## When your code should decide instead

A goal lets the model judge. When a function can judge, hang an `on_stop`
[hook](/weaver/hooks) on the agent instead: an async function humanize calls each time a turn is
about to end. Answer `block=True` with a `reason`, and the agent keeps going, with that reason
as its next prompt. `on_stop` is on every agent, so it needs no mixin and works on every CLI.

`ticked` keeps the agent going until every box in `TASK.md` is ticked:

```python
# .hmz/flows/ticked/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FilesEnvMixin,
    FlowContext,
    FlowParams,
    LocalEnv,
    StopHookParams,
    StopHookResult,
    flow,
)


class Agents(AgentCollection):
    worker: Agent  # ①


class Workspace(LocalEnv, FilesEnvMixin): ...  # ②


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def ticked(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Work through TASK.md, and end the turn only when every box is ticked."""
    worker, workspace = agents["worker"], envs["workspace"]

    async def unfinished(params: StopHookParams) -> StopHookResult:  # ③
        if params.again < 5 and b"- [ ]" in await workspace.read("TASK.md"):  # ④
            return StopHookResult(block=True, reason="TASK.md still has unticked boxes.")
        return StopHookResult()  # ⑤

    worker.on_stop(unfinished)  # ⑥
    session = await worker.spawn()
    await worker.run(task, session=session, env=workspace)
```

1. **A plain `Agent`.** The stop hook is on every agent, so any CLI can fill the role.
2. **`FilesEnvMixin`** lets the flow `read` files in the workspace, which the hook needs.
3. **`unfinished`** is the hook: called with a `StopHookParams` each time a turn is about to
   end, and answering with a `StopHookResult`. It is defined inside the flow so it can see
   `workspace`.
4. **`params.again`** counts how many times this turn has already been kept going, so the hook
   gives up after five rather than spending the budget on an agent that cannot finish.
5. **An empty result** lets the turn end.
6. **`on_stop`** hangs the hook on every session of this agent. Hang it before the `run` it
   should govern.

With a `TASK.md` of two boxes:

```md
- [ ] add `subtract(a, b)` to calc.py
- [ ] add `multiply(a, b)` to calc.py

Tick each box in this file as you finish it.
```

```sh
hmz exec -f ticked -a worker=claude/claude-sonnet-5-5:high -p budget.cost=1 \
    "Do the first box of TASK.md, tick it, and stop there."
```

The task says to stop after one box, so the first turn does. The hook finds a box still open
and keeps the turn going, with its reason as the next prompt:

```text
● worker is working
● Read(/home/you/calc/TASK.md)
● Bash(cd /home/you/calc && printf '\n\ndef subtract(a, b):\n    return a - b\n' >> calc.py && sed -i '1s/- \[ \]/- [x]/' TASK)
● I added `subtract(a, b)` to `calc.py` and ticked the first box in `TASK.md`. I stopped there, so the `multiply` box is still open. …
✻ input 8 · output 358 · cache_read 61.3k · cache_write 5.8k · $0.03 · claude-sonnet-5-5 · worker
…
● worker is working
● Continuing with the second box.
● Bash(cd /home/you/calc && printf '\n\ndef multiply(a, b):\n    return a * b\n' >> calc.py && sed -i '2s/- \[ \]/- [x]/' TASK)
● I added `multiply(a, b)` to `calc.py` and ticked the second box, so both boxes in `TASK.md` are now ticked. …
✻ input 4 · output 592 · cache_read 34.3k · cache_write 726 · $0.01 · claude-sonnet-5-5 · worker
…
✻ Worked for 5s · worker
```

A test drives the hook with a fake agent that ticks one box per turn. Add it to
`tests/test_goals.py`:

```python
async def test_the_turn_goes_on_until_every_box_is_ticked() -> None:
    here = fakes.FakeEnvDriver({"TASK.md": "- [ ] subtract\n- [ ] multiply\n"})

    async def ticks_one(prompt: str, **_: object) -> str:  # ①
        text = here.text("TASK.md").replace("- [ ]", "- [x]", 1)
        await here.write("TASK.md", text.encode())
        return "ticked one"

    worker = fakes.FakeAgentDriver(reply=ticks_one)
    await fakes.run_fake("ticked", "go", agents={"worker": worker}, local=here)

    assert worker.prompts == ["go", "TASK.md still has unticked boxes."]  # ②
    assert "- [ ]" not in here.text("TASK.md")
```

```text
...                                                                      [100%]
3 passed in 0.09s
```

1. **`ticks_one`** is the agent's turn: it ticks one box in the fake workspace.
2. **`prompts`** records the hook's reason as the prompt that kept the turn going. Two prompts
   means the hook blocked once, and let the turn end when both boxes were ticked.

| | Decides it is done | Costs | Works on |
| --- | --- | --- | --- |
| `/goal` | the **model**, against the objective | turns until the model says so | 4 CLIs |
| a blocking `on_stop` | **your code**, against whatever it can read | one more turn per block, bounded by `again` | every CLI |

## A recurring task: `/loop`

`/loop <interval> <task>` is Claude Code's own recurring task. A role that sends one declares
`LoopCommandAgentMixin`, so only Claude Code can fill it, and the prompt goes to the CLI as
written:

```python
class Watcher(Agent, LoopCommandAgentMixin): ...
```

## Pitfalls

- **A role without the mixin cannot set a goal**, even on Claude Code. A `/goal` prompt on a
  plain `Agent` raises, so a flow that never declared goals cannot start one by accident:

  ```text
  hmz.flows.errors.CapabilityNotGranted: worker: /goal needs GoalCommandAgentMixin on the role
  ```

  The same holds for `/loop` without `LoopCommandAgentMixin`.
- **A vague objective never settles.** "Make it better" has no point at which it is met. Name
  something the agent can check, and give the run a budget it can afford to spend.
- **A stop hook that always blocks** keeps one turn going until the budget ends it. Give up on
  `params.again`, as `ticked` does.

## Next steps

- [It decides when it is done](/features/goals): the goal, drawn beside the stop hook
- [Hooks](/weaver/hooks): every moment a flow can hang one on
- [Loops](/weaver/loops): a loop your flow runs, rather than one the CLI does
- [Reference › Asking for an agent that can do
  something](/reference/flows#asking-for-an-agent-that-can-do-something)

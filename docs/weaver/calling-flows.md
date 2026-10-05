# A flow that calls a flow

In this guide you build flows out of other flows. You write `steps`, which splits its task
into steps and runs each as a call to a hidden flow beside it, under a budget of its own. Then
you write `aimed`, which calls the `goal` flow humanize ships and carries on after it.

Reach for `load` when a flow somebody has already written does one step of what you want, or
when a flow of your own has grown steps worth naming, testing and budgeting one at a time.

::: info Before you start
- A flow of your own running: [Your first flow](/weaver/writing-a-flow).
- [Params of its own](/weaver/flow-settings), to pass a called flow its params.
- For `aimed`: a CLI with a goal feature, such as Claude Code or Codex. See
  [Goals](/weaver/goals).
:::

## How it works

`load(ref)` finds a flow by its **ref**, such as `:one-step` or `humanize1:gen-plan`, and hands
it back ready to call. Awaiting it runs that flow inside yours and answers with what it
returned:

```python
review = load(":review")
verdict = await review(task, agents={...}, envs={...}, params=review.expected_params())
```

A called flow is a flow like any other, run as a **branch** of your run:

- **It gets its own `ctx`**, its own line in the running tree, and a budget that is the tighter
  of its own and what is left of yours. What it spends counts against every flow above it.
- **It is handed exactly what it declared.** You pass agents and environments keyed by *its*
  role names, and everything is checked against its declaration before a line of it runs.
- **Its sessions and hooks are its own.** Yours never see them, even when you hand it the same
  agent.
- **It raises what it raised, as it raised it.** A `CostExceeded` three flows down is a
  `CostExceeded` in yours.

At the prompt, the status line names the flow running under yours, and [the
monitor](/user/monitor) draws the tree. The [trace](/user/tracing) keeps every call and
every return.

## Example: steps of your own

One directory can hold several flows. `steps` keeps its step as a hidden flow in the same
module, and calls it once per step:

```python
# .hmz/flows/steps/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    Budget,
    CostExceeded,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    ShellEnvMixin,
    flow,
    load,
)


class Agents(AgentCollection):
    builder: Agent


class Workspace(LocalEnv, ShellEnvMixin): ...


class Envs(EnvCollection):
    workspace: Workspace


class StepParams(FlowParams):  # ①
    check: list[str] = ["python3", "check.py"]


@flow(agents=Agents, envs=Envs, params=StepParams, name="one-step", hidden=True)  # ②
async def one_step(
    task: str, *, agents: Agents, envs: Envs, params: StepParams, ctx: FlowContext
) -> bool:
    """Take one step, and say whether the check still passes."""
    builder, workspace = agents["builder"], envs["workspace"]
    session = await builder.spawn()
    await builder.run(task, session=session, env=workspace)
    code, _, _ = await workspace.exec(params.check)
    return code == 0  # ③


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def steps(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> dict[str, bool]:
    """The task a step at a time, split on ';', each under a budget of its own."""
    step = load(":one-step")  # ④
    passed: dict[str, bool] = {}
    for part in (one.strip() for one in task.split(";")):
        try:
            passed[part] = await step(  # ⑤
                part,
                agents={"builder": agents["builder"]},  # ⑥
                envs=envs,  # ⑦
                params=step.expected_params(),  # ⑧
                budget=Budget(cost=0.5, graceful=False),  # ⑨
            )
        except CostExceeded:  # ⑩
            passed[part] = False
    print(passed)
    return passed
```

### What each part does

1. **`StepParams`** are the step's own params. A called flow is configured like any other:
   with an instance of its `FlowParams` subclass.
2. **`name="one-step", hidden=True`** names the step for its ref and keeps it out of the menus
   at the prompt. It still runs by its ref. Giving a flow meant to be called a `name=` means
   renaming the function does not break the refs that name it.
3. **What the step returns** is what the `await` in ⑤ answers with: here, whether the check
   still passes after the step.
4. **`load(":one-step")`** finds the flow called `one-step` in the same module. A leading `:`
   means "beside me".
5. **Awaiting the flow** runs it to the end, as a branch of this run.
6. **`agents=` is keyed by the callee's role names.** The step's role happens to be called
   `builder` too, but it is the step's declaration that names the key.
7. **`envs=envs`** hands on the workspace. Each environment must carry every mixin the
   callee's role asks for, here `ShellEnvMixin`, and this flow's role declares it.
8. **`step.expected_params()`** builds the step's own params class, at its defaults.
   `step.expected_params(check=["pytest", "-q"])` would change one.
9. **`Budget(cost=0.5, graceful=False)`** gives each step at most 50 cents of what the run has
   left. `graceful=False` interrupts a turn the moment it reaches the limit, rather than
   letting it finish.
10. **`except CostExceeded`** turns a step that ran over into a failed step, and the run goes
    on to the next. The spent budget is the step's own, so the rest of the run is unaffected.

### Run it

```sh
hmz exec -f steps -a builder=claude/claude-sonnet-5-5:high -p budget.cost=1 \
    "add subtract(a, b) to calc.py; add multiply(a, b) to calc.py"
```

`-f steps` finds the directory, and in it the one flow that is not hidden. A real run:

```text
● builder is working
● Bash(cd /home/you/calc && ls && cat calc.py)
● Bash(cd /home/you/calc && printf '\n\ndef subtract(a, b):\n    return a - b\n' >> calc.py && cat calc.py && cat check.py)
● I added `subtract(a, b)` to `calc.py`. It returns `a - b`. …
✻ input 6 · output 296 · cache_read 44.4k · cache_write 5.6k · $0.03 · claude-sonnet-5-5 · builder
…
✻ Worked for 5s · builder
● builder is working
● Read(/home/you/calc/calc.py)
● Edit(/home/you/calc/calc.py)
● I added `multiply(a, b)` to `calc.py`. It returns `a * b` and sits after `subtract`. …
✻ input 6 · output 265 · cache_read 45.8k · cache_write 4.2k · $0.02 · claude-sonnet-5-5 · builder
…
✻ Worked for 5s · builder
{'add subtract(a, b) to calc.py': True, 'add multiply(a, b) to calc.py': True}
```

Each step is a fresh session, in its own call, and the last line is `steps`' own `print` of
what the two calls returned.

### Check it worked

Each step is testable as a call of its own. The second test shows a step over its budget
failing without ending the run:

```python
# tests/test_steps.py
from hmz.sdk import fakes

GREEN = {("python3", "check.py"): (0, "ok\n", "")}  # ①


async def test_each_step_is_a_call_of_its_own() -> None:
    builder = fakes.FakeAgentDriver()
    here = fakes.FakeEnvDriver(run=GREEN)

    passed = await fakes.run_fake(
        "steps", "add subtract; add multiply", agents={"builder": builder}, local=here
    )

    assert passed == {"add subtract": True, "add multiply": True}
    assert [session.prompts for session in builder.sessions] == [  # ②
        ["add subtract"],
        ["add multiply"],
    ]
    assert here.commands == [("python3", "check.py")] * 2


async def test_a_step_over_its_budget_does_not_end_the_run() -> None:
    builder = fakes.FakeAgentDriver(cost=0.75)  # ③

    passed = await fakes.run_fake(
        "steps",
        "add subtract; add multiply",
        agents={"builder": builder},
        local=fakes.FakeEnvDriver(run=GREEN),
    )

    assert passed == {"add subtract": False, "add multiply": False}  # ④
```

```text
..                                                                       [100%]
2 passed in 0.09s
```

1. **`GREEN`** answers the step's check with success.
2. **One session per step**, each given its step's prompt alone: the calls share nothing.
3. **`cost=0.75`** makes every fake turn cost 75 cents, more than a step's 50.
4. **Both steps fail, and the run still returns.** Each turn was interrupted at its step's
   limit with `CostExceeded`, which `steps` caught.

## Example: a published flow

`aimed` calls [`goal`](/flows/goal), which ships with humanize, then takes a turn of its own
once the goal is met:

```python
# .hmz/flows/aimed/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    GoalCommandAgentMixin,
    LocalEnv,
    flow,
    load,
)


class Builder(Agent, GoalCommandAgentMixin): ...  # ①


class Agents(AgentCollection):
    builder: Builder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def aimed(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """The task as a goal, then one more turn to write it up."""
    builder = agents["builder"]
    goal = load("goal")  # ②
    await goal(
        task,
        agents={"worker": builder},  # ③
        envs={},  # ④
        params=goal.expected_params(),
    )
    session = await builder.spawn()
    await builder.run(
        "Describe the uncommitted change in one line, in CHANGES.md.",
        session=session,
        env=envs["workspace"],
    )
```

1. **`GoalCommandAgentMixin` on your role**, because `goal`'s `worker` role asks for it. An
   agent reaches your flow granted what **your** role declared, and that is all it can pass
   on, whatever its CLI could do.
2. **A name**, as `-f` takes one: `goal` ships with humanize, so it is there on every
   machine. A flow of another repository is named by a git ref instead, written the way pip
   writes one: the repository, `@` a branch, tag or commit, and `#` the directory the flow is
   in, as in `git+https://github.com/humanfia/humanize1-flow@v0.1.0#humanize1:rlcr`. It is
   fetched the first time you call it, once per URL and revision per run.
3. **`"worker"`** is `goal`'s role name. Your `builder` fills it.
4. **`envs={}`** leaves `goal`'s `workspace` out. It is a `LocalEnv`, which the run fills, so
   the callee gets the run's own directory.

```sh
hmz exec -f aimed -a builder=claude/claude-sonnet-5-5:high -p budget.cost=1 \
    "calc.py has a subtract function, and python3 check.py still prints ok"
```

```text
● worker is working
● Goal set: calc.py has a subtract function, and python3 check.py still prints ok
● Goal noted: add a `subtract` function to calc.py while keeping `python3 check.py` printing ok. …
● Bash(cd /home/you/calc && printf '\n\ndef subtract(a, b):\n    return a - b\n' >> calc.py && cat calc.py && python3 check.py)
● I added `subtract(a, b)` to `calc.py`. It returns `a - b`. `python3 check.py` still prints `ok`, …
✻ input 9 · output 467 · cache_read 41.8k · cache_write 10.1k · $0.04 · claude-sonnet-5-5 · worker
…
✻ Worked for 8s · worker
● builder is working
● Bash(cd /home/you/calc && git diff && ls CHANGES.md)
● Write(/home/you/calc/CHANGES.md)
● I created `CHANGES.md` with one line: "Added a `subtract(a, b)` function to `calc.py` that returns `a - b`." …
✻ input 6 · output 303 · cache_read 46.0k · cache_write 4.3k · $0.02 · claude-sonnet-5-5 · builder
…
✻ Worked for 5s · builder
```

**The first turn is labelled `worker`**: inside `goal`, your agent fills `goal`'s role, under
`goal`'s name for it. The second is `aimed`'s own turn, as `builder`.

A test runs the called flow too, on the same fake agent:

```python
# tests/test_aimed.py
from hmz.sdk import fakes


async def test_the_goal_goes_first_then_the_write_up() -> None:
    builder = fakes.FakeAgentDriver()

    await fakes.run_fake("aimed", "ship it", agents={"builder": builder})

    assert [session.prompts for session in builder.sessions] == [  # ①
        ["/goal ship it"],
        ["Describe the uncommitted change in one line, in CHANGES.md."],
    ]
```

1. **Both flows' sessions are the driver's**: the first opened by `goal`, the second by
   `aimed`.

## Name the flow

| Ref | Names |
| --- | --- |
| `:one-step` | another `@flow` in the same module as the flow asking |
| `ralph_loop` | a flow by its directory: the flow named after it, else the only visible one |
| `humanize1:rlcr` | one flow of several in a directory |
| `git+<url>@<rev>#humanize1:rlcr` | a flow of a repository, in the directory after `#` (its root without one), at a branch, tag or commit |

A name is looked for beside the flow asking first, among the flows of its own directory (for a
flow installed from a [flowverse](/weaver/flowverses), the others installed from it), and then
wherever `-f` looks, nearest first. A bare name for a directory of several visible flows, such as
`humanize1`, raises `FlowNotFound` listing them: name one. A git ref that cannot be fetched
raises `FlowNotFound` too.

## Hand it what it declares

Everything is checked before a line of the callee runs:

| The callee's role asks for | What you pass must have | Otherwise |
| --- | --- | --- |
| a mixin, such as `ShellEnvMixin` | that mixin, declared by **your** role | `CapabilityMissing` |
| a `_permission` | at least that, scope by scope | `PermissionTooNarrow` |
| one CLI, such as `ClaudeCodeAgent` | that CLI | `HarnessMismatch` |
| CPUs, memory or GPUs | a machine with at least that many | `ResourceUnmet` |
| a required role | anything at all | `MissingRole` |

Each is a `RequirementError`, and nothing of the callee has run or spent anything when it is
raised. Typed as a plain `Agent`, `aimed`'s `builder` is refused at the call, and the exception
ends the run unless you catch it:

```text
hmz.flows.errors.CapabilityMissing: goal:goal: 'worker' needs GoalCommandAgentMixin, which the agent given was not granted
```

The callee is handed exactly what **it** declared, not what you hold. An agent with a steer
and a goal command, passed to a role typed plain `Agent`, is a plain `Agent` there.

## Leave out what the run fills

Two kinds of role are filled by the run: an `Outworlder`, which is [the person at the
prompt](/weaver/human-agent), and a `LocalEnv`, the directory the run was started in. Leave
either out and the callee gets the run's own, with every mixin it asks for. That is why
`envs={}` is the usual thing to pass. Your own `LocalEnv` works too, if your role declared
every mixin the callee's does. An environment on another machine is refused for a `LocalEnv`
role, with `CapabilityMissing`.

To answer the callee's questions yourself instead of the person, pass `Outworlder.new()` and
hang a hook on it. See [The person as an agent](/weaver/human-agent#stand-in-for-the-person).

## Narrow what you hand on

`derive` gives you the same agent under a narrower grant: a smaller permission, fewer skills.

```python
from hmz.flows import Permission, PermissionKind

read_only = Permission(local=PermissionKind.READ)
reader = agents["builder"].derive(permission=read_only)
reading = await reader.spawn()  # may not write
```

It only narrows: asking for more than was granted raises `CapabilityNotGranted`. It is for a
stretch of your own flow, such as a session that reads beside one that writes. You do not need
it to hand an agent on, since the callee's sessions already run under what *its* role
declares. You cannot go below the callee's declaration either: `reader` passed to a role typed
plain `Agent`, whose default permission is `local=ALL`, is refused with `PermissionTooNarrow`.

Environments narrow by being derived too: a subdirectory, a [worktree or a
copy](/weaver/worktrees).

## Pass params

Build the callee's own params class, which it exposes as `expected_params`:

```python
params=step.expected_params(check=["pytest", "-q"])
```

For a flow of your own module, whose class you can name, `StepParams(check=[…])` is the same
thing. Another model or a plain mapping is validated into the callee's class at the call, and
raises `ParamsError` if it does not fit, before the callee has run. See [Params of its
own](/weaver/flow-settings).

## Give it a budget of its own

A called flow runs under the **tighter** of its own `budget=` and what is left of yours, and
reads the result in `ctx.budget`. What it spends counts against every flow above it as it is
spent. `duration` is a deadline rather than a sum, so two children gathered for an hour each
fit in a parent's hour. A spent budget stays spent: every later turn under it raises again. See
[the run's budget](/features/allowances).

## Variations

**Call several at once.** Calls gather like turns do: see [Many turns at
once](/weaver/async-flows#whole-flows-at-once). Each gathered call has its own `ctx`, its own
budget under yours, and its own line in the running tree.

**Call itself.** A flow may call itself, and decide how deep to go from its params or from what
a model said:

```python
class Params(FlowParams):
    left: int = 2


@flow(agents=Agents, envs=Envs, params=Params, name="split", hidden=True)
async def split(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> None:
    if params.left <= 0:
        session = await agents["builder"].spawn()
        await agents["builder"].run(task, session=session, env=envs["workspace"])
        return
    deeper = Params(left=params.left - 1)
    again = load(":split")
    await asyncio.gather(*(
        again(f"{task} / {half}", agents=agents, envs=envs, params=deeper)
        for half in ("left", "right")
    ))
```

Called with `left=2`, it takes four turns, on `root / left / left` through
`root / right / right`. A chain of calls goes **at most 64 deep**. The call that would go
deeper raises `FlowDepthExceeded`, naming the flow. It is also a `RecursionError`.

**Picked up with the flow that called it.** When a resumable run is [picked
up](/user/resuming), each flow it calls again **exactly as before** carries on with the state
it kept. Exactly means the same ref, task, agents (CLI, account, model, effort, permission,
skills), environments and params. A call that differs in anything starts afresh. Identical
calls are told apart by their order, so a loop that calls one flow ten times picks up each of
the ten. A caller that is not resumable itself still passes the picking up through to the flows
it calls.

## Pitfalls

- **Declare what the flows you call need.** Your role's type is all an agent can pass on. A
  type checker holds you to it too.
- **A graceful budget lets the turn finish.** With the default `graceful=True`, a step's budget
  is checked as a turn starts, so a one-turn step can run past it by what that turn spent. Pass
  `graceful=False` to interrupt it at the limit, as `steps` does.
- **Skills come with the callee.** A called flow's agents carry the [skills](/user/skills) the
  called flow names, found in its own `skills/` or fetched from the git URL it gives. A skill
  it names and cannot find raises `FlowDefinitionError` at the call.
- **Reading `expected_params` fetches.** On a git ref that has not been fetched, it fetches on
  the spot, and the whole run waits, every branch included. Call the flow first where you can.
- **Two directories of one name.** Two flows from different directories that import a module
  of the same name, such as your copy of `humanize1` and the official one, cannot both be
  loaded in one run: the second raises `FlowLoadConflict`.
- **Two flows of one name in one directory** raise `FlowDefinitionError`.

`Hmz().flows.running()` from `hmz.sdk` lists every flow call going in the process, oldest
first, each with its `ref`, `depth` and `parent`.

## Next steps

- [Many turns at once](/weaver/async-flows)
- [Params of its own](/weaver/flow-settings)
- [Flowverses](/weaver/flowverses), to publish flows for others to call
- [Reference › Calling another flow](/reference/flows#a-flow-that-calls-another-flow),
  [`load`](/reference/flows#load) and [Refs](/reference/flows#refs)

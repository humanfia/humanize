# A flow that calls a flow

`load` finds a flow by its **ref**, a name such as `humanize1:gen-plan`, and hands it back
ready to call. Awaiting it runs that flow inside yours, on agents you hand it, and answers with
what it returned. Reach for it when a flow someone has already written does one step of what
you want.

## Try it

This flow drafts an idea with `gen-idea` from the official [`humanize1`](/flows/humanize1),
plans it with `gen-plan`, and then builds the plan in three rounds of its own:

```python{28-29,31,37}
# .humanize/flows/planned/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
    load,
)


class Agents(AgentCollection):
    builder: Agent
    critic: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def planned(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    builder, critic = agents["builder"], agents["critic"]
    idea = load("humanize1:gen-idea")  # a flow, by its ref
    plan = load("humanize1:gen-plan")

    draft = await idea(  # runs gen-idea; answers the draft's path
        task,
        agents={"drafter": builder},       # by gen-idea's role names
        envs={},                           # the run's own workspace
        params=idea.expected_params(),     # at their defaults
    )
    written = await plan(
        task,
        agents={"planner": builder, "analyst": critic},
        envs={},
        params=plan.expected_params(input=draft),  # that draft
    )
    for _ in range(3):
        session = await builder.spawn(env=envs["workspace"])
        step = f"Carry out the next part of {written}."
        await builder.run(step, session=session)
```

```sh
hmz exec -f planned -b cost=30 \
    -a builder=claude/claude-opus-5:max -a critic=codex/gpt-5.6-sol:max \
    "add undo to the editor"
```

Each published flow is one `await` in yours. Run it at the prompt instead, as
`$local/planned`, and while `gen-plan` runs the status line reads
`planned ▸ humanize1:gen-plan`, with [`/monitor`](/user/monitor) drawing the same tree. Either
way, the [trace](/user/tracing) keeps every call and every return.

A called flow raises what it raised, **as it raised it**: a `CostExceeded` three flows down is
a `CostExceeded` in yours.

## Name the flow

| Ref | Names |
| --- | --- |
| `:review` | another `@flow` in the same module as the flow asking |
| `ralph_loop` | a flow by its directory: the flow named after it, else the only visible one |
| `humanize1:rlcr` | one flow of several in a directory |
| `git+<url>@<rev>#humanize1:rlcr` | a flow of another flowverse, at a branch, tag or commit |

A name is looked for beside the flow asking first, in its own flowverse, and then wherever
`-f` looks, nearest first. A bare name for a directory of several flows, such as `humanize1`,
raises `FlowNotFound` listing them; name one.

A git ref is written the way pip writes one:
`git+https://github.com/humanfia/flowverse@main#humanize1:rlcr`. It is fetched the first time
you call it, once per URL and revision per run, and raises `FlowNotFound` if it cannot be
fetched.

## Hand it what it declares

`agents` and `envs` are keyed by **the callee's** role names, whatever you call the same agents
yourself. Pass an agent or environment you were handed, or one
[derived](#narrow-what-you-hand-on) from it. Everything is checked before a line of the callee
runs:

| The callee's role asks for | What you pass must have | Otherwise |
| --- | --- | --- |
| a mixin, such as `ShellEnvMixin` | that mixin, declared by **your** role | `CapabilityMissing` |
| a `_permission` | at least that, scope by scope | `PermissionTooNarrow` |
| one CLI, such as `ClaudeCodeAgent` | that CLI | `HarnessMismatch` |
| CPUs, memory or GPUs | a machine with at least that many | `ResourceUnmet` |
| a required role | anything at all | `MissingRole` |

Each is a `RequirementError`, and nothing of the callee has run or spent anything when it is
raised.

::: warning Your role's declaration is what you can pass on
An agent reaches your flow granted what **your** role declared, and that is all it can pass
on, whatever its CLI can do. `humanize1:rlcr` hangs a hook that needs
`PermissionRequestHookAgentMixin` on its builder. A Claude agent in a role typed plain `Agent`
is refused at the call, and the exception ends the run unless you catch it:

```console
Traceback (most recent call last):
  ...
hmz.flows.errors.CapabilityMissing: humanize1:rlcr: 'builder' needs PermissionRequestHookAgentMixin, which the agent given was not granted
```

Declare what the flows you call need, and a type checker holds you to it too:

```python
from hmz.flows import PermissionRequestHookAgentMixin        # [!code ++]


class Builder(Agent, PermissionRequestHookAgentMixin): ...   # [!code ++]


class Agents(AgentCollection):
    builder: Agent      # [!code --]
    builder: Builder    # [!code ++]
    critic: Agent
```
:::

The callee is handed exactly what **it** declared, not what you hold. An agent with a steer
and a goal command, passed to a role typed plain `Agent`, is a plain `Agent` there. The
sessions the callee opens and the [hooks](/weaver/hooks) it hangs are its own, and yours
never see them.

## Leave out what the run fills

Two kinds of role are filled by the run: an `Outworlder`, which is [the person at the
prompt](/weaver/human-agent), and a `LocalEnv`, the directory the run was started in. Leave
either out and the callee gets the run's own:

```python{4-5}
rlcr = load("humanize1:rlcr")
await rlcr(
    task,
    agents={"builder": builder, "reviewer": critic},  # no "human"
    envs={},                                          # no "workspace"
    params=rlcr.expected_params(),
)
```

Here `builder` fills the `Builder` role declared above. rlcr's `human` is whoever is at the
prompt, and its `workspace` is the run's directory, with every mixin rlcr asks for. That is why
`envs={}` is the usual thing to pass. Your own `LocalEnv` works too, if your role declared
every mixin the callee's does. An environment on another machine is refused for a `LocalEnv`
role, with `CapabilityMissing`.

To answer the callee's questions yourself instead of the person, pass `Outworlder.new()` and
hang a hook on it. See [The person as an agent](/weaver/human-agent).

## Narrow what you hand on

`derive` gives you the same agent under a narrower grant: a smaller permission, fewer skills.

```python
from hmz.flows import Permission, PermissionKind

read_only = Permission(local=PermissionKind.READ)
reader = agents["builder"].derive(permission=read_only)
reading = await reader.spawn(env=envs["workspace"])  # may not write
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
await rlcr(
    task, agents=..., envs={}, params=rlcr.expected_params(max=12)
)
```

For a flow of your own module, whose class you can import, `Params(max=12)` is the same thing.
Another model or a plain mapping is validated into the callee's class at the call, and raises
`ParamsError` if it does not fit, before the callee has run. See [Params of its
own](/weaver/flow-settings).

## Give it a budget of its own

```python{7}
from hmz.flows import Budget, CostExceeded

explore = load(":explore")
try:
    await explore(
        task, agents=agents, envs=envs, params=FlowParams(),
        budget=Budget(cost=2.0),  # at most 2 USD of what you have left
    )
except CostExceeded:
    ...  # exploring is over; the rest of the run goes on
```

A called flow runs under the **tighter** of its own budget and what is left of yours, and
reads the result in `ctx.budget`. What it spends counts against every flow above it as it is
spent. `duration` is a deadline rather than a sum, so two children gathered for an hour each
fit in a parent's hour. A spent budget stays spent: every later turn under it raises again. See
[the run's budget](/features/allowances).

## Split a flow into steps

One directory can hold several flows. Mark a step `hidden=True` to keep it out of the menus,
and call it by `:name`:

```python{5-6,17}
@flow(
    agents=Agents,
    envs=Envs,
    params=FlowParams,
    name="fix-one",  # called as ":fix-one"
    hidden=True,     # left out of the menus
)
async def fix_one(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None: ...


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def fix_all(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    step = load(":fix-one")
    for part in ("parser", "printer"):
        said = f"{task}, in the {part}"
        await step(said, agents=agents, envs=envs, params=FlowParams())
```

Each flow in the directory declares its own agents and params, so a step asks only for the
roles it uses. Give a flow meant to be called by others a `name=`, so that renaming the
function does not break the refs that name it. Two flows of one name in one directory raise
`FlowDefinitionError`.

## Call several at once, or itself

Calls gather like turns do (see [Many turns at once](/weaver/async-flows)). Each gathered call
has its own `ctx`, its own budget under yours, and its own line in the running tree.

A flow may call itself, and decide how deep to go from its params or from what a model said:

```python
class Params(FlowParams):
    left: int = 3


@flow(agents=Agents, envs=Envs, params=Params)
async def split(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> None:
    if params.left <= 0:
        session = await agents["builder"].spawn(env=envs["workspace"])
        await agents["builder"].run(task, session=session)
        return
    deeper = Params(left=params.left - 1)
    again = load(":split")
    await asyncio.gather(*(
        again(part, agents=agents, envs=envs, params=deeper)
        for part in parts(task)  # your own way of splitting it
    ))
```

A chain of calls goes **at most 64 deep**. The call that would go deeper raises
`FlowDepthExceeded`, naming the flow. It is also a `RecursionError`.

## Picked up with the flow that called it

When a resumable run is [picked up](/user/resuming), each flow it calls again **exactly as
before** carries on with the state it kept. Exactly means the same ref, task, agents (CLI,
account, model, effort, permission, skills), environments and params. A call that differs in
anything starts afresh. Identical calls are told apart by their order, so a loop that calls one
flow ten times picks up each of the ten. A caller that is not resumable itself still passes the
picking up through to the flows it calls.

::: details Edge cases
- **Skills.** A called flow's agents carry the [skills](/user/skills) the called flow names,
  found in its own `skills/` or fetched from the git URL it gives. A skill it names and cannot
  find raises `FlowDefinitionError` at the call.
- **Fetching early.** Reading `expected_params` off a git ref that has not been fetched fetches
  it on the spot, and the whole run waits while it does, every branch included. Call the flow
  first where you can.
- **Two directories of one name.** Two flows from different directories that import a module
  of the same name, such as your copy of `humanize1` and the official one, cannot both be
  loaded in one run: the second raises `FlowLoadConflict`.
- **What is running, from Python.** `Hmz().flows.running()` from `hmz.sdk` lists every flow
  call going in the process, oldest first, each with its `ref`, `depth` and `parent`.
:::

## See also

- [Many turns at once](/weaver/async-flows)
- [Params of its own](/weaver/flow-settings)
- [Hooks](/weaver/hooks), for getting between an agent and its turn
- [Reference › Flows](/reference/flows), for every argument and error

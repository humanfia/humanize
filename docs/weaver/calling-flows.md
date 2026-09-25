# A flow that calls a flow

`load` finds a flow by its ref, and calling what it answers runs that flow from inside yours,
on the agents and environments you hand it. Reach for it when one flow is a reusable step
another weaver builds on — which is what turns a flowverse into a library rather than a menu.

## Call one

```python
# .humanize/flows/planned/__init__.py
"""Plan it with humanize1, then build it three rounds."""

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
    plan = load("humanize1:gen-plan")
    await plan(
        f"plan this first: {task}",
        agents={"planner": agents["builder"], "analyst": agents["critic"]},
        envs={},
        params=plan.expected_params(),
    )
    builder = agents["builder"]
    for _ in range(3):
        session = await builder.spawn(env=envs["workspace"])
        await builder.run(task, session=session)
```

```sh
hmz exec -f planned -a builder=claude/claude-opus-5:max -a critic=codex/gpt-5.6-sol:max \
    -b cost=30 "add undo to the editor"
```

What `load` answers is a flow like any other: awaited with the task and the same four things
`hmz exec` gives one — `agents` and `envs` by role, `params`, and a `budget` if you want it held
to less than you are. It answers with whatever the flow returned, and raises whatever it
raised, **as it raised it**: a `CostExceeded` three flows down is a `CostExceeded` here, never
wrapped in something of the caller's.

`expected_agents`, `expected_envs` and `expected_params` on it are the classes it declared, so
a caller can read what a flow wants before calling it — and `expected_params()` is its params
at their defaults. `planned` is in this project and `humanize1` is not, so the bare name is
looked for where `-f` would look, nearest first, and found in the official flowverse.

## Name it

A ref is one of four things:

| Ref | Names |
| --- | --- |
| `:review` | a flow in the same module as the flow asking — another `@flow` in the same directory |
| `humanize1` | a flow in the same flowverse as the flow asking, by its directory |
| `humanize1:gen-plan` | one flow of several in that directory |
| `git+https://github.com/humanfia/flowverse@main#humanize1:rlcr` | a flow of another flowverse, at a branch, tag or commit |

A **bare** name — `humanize1` — is the flow named after its directory, else the one visible
flow the directory holds, else nothing: humanize will not choose between several, and
`FlowNotFound` says which there are.

`:review` is relative to the flow asking, and a relative ref with no flow to be relative to
raises `FlowRefError`. `humanize1` and `humanize1:gen-plan` are looked for first beside the flow
asking, in its own flowverse, and then wherever `-f` would look — nearest first, `official/rlar`
and a path included — which is also everything `load` takes from outside every flow: a script,
a test.

A git ref is written the way pip writes one: `git+` and any URL git fetches, `@` and a
revision, `#` and the flow. It is fetched the first time it is called rather than when `load`
is — naming one costs nothing until it is used — then **once per URL and revision per run**,
resolved to the commit that revision stood at, and cloned once per commit. What cannot be
fetched raises `FlowNotFound`. Reading `expected_params` or the rest off one that has not been
fetched yet fetches it there and then, on the thread that asked, so call it first where you can.

A run imports a flow's module once, however often it loads its flows, and never takes one out
from under a flow that is using it: two checkouts that would both be imported under one name in
one run raise `FlowLoadConflict` rather than one quietly replacing the other.

## Hand it what it declares

`agents` and `envs` are dictionaries by **the callee's** role names, whatever you call the same
agents yourself. What you hand over is what you were handed — the agent or environment from
your own `agents` and `envs`, or one [derived](#narrow-what-you-hand-on) from it. Anything else,
a driver of your own making included, is refused.

What you hand over must be **at least** what the callee declared, and is checked before a line
of it runs:

| The callee's role asks for | What you hand over must have been granted | Otherwise |
| --- | --- | --- |
| a mixin — `GoalCommandAgentMixin`, `ShellEnvMixin`, … | that mixin, by your own declaration | `CapabilityMissing` |
| a `_permission` | at least that, scope by scope | `PermissionTooNarrow` |
| a CLI's own protocol — `ClaudeCodeAgent` | that CLI | `HarnessMismatch` |
| CPUs, memory, GPUs | a machine with at least that many | `ResourceUnmet` |
| a required role | anything at all | `MissingRole` |

All of them are `RequirementError`, and nothing of the callee has run or spent a cent when one
is raised.

"By your own declaration" is the part that surprises. An agent is handed to your flow granted
what *your* role declared, and that is what it carries on: a Codex agent in a role typed plain
`Agent` cannot be handed to a role that asks for `GoalCommandAgentMixin`, although Codex has a
goal feature — your flow never asked for it, so it has none to pass on.

```console
__main__:wants_goal: 'worker' needs GoalCommandAgentMixin, which the agent given was not granted
```

Declare what the flows you call need, and a type checker holds you to it too.

**The callee is handed exactly what it declared** — not what you were granted. An agent you
hold with a goal feature and a steer, handed to a role typed plain `Agent`, arrives as a plain
`Agent` there. And it arrives as a view of its own: the sessions the callee opens and the hooks
it hangs are the callee's, and yours never hear of them, nor it of yours.

## Narrow what you hand on

`derive` is the same agent under a narrower grant — a smaller permission, fewer skills:

```python
from hmz.flows import Permission, PermissionKind

reader = agents["builder"].derive(permission=Permission(local=PermissionKind.READ))
reading = await reader.spawn(env=envs["workspace"])      # a session that may not write
```

It only narrows: a permission wider than the one it was granted, or a skill it was not given,
raises `CapabilityNotGranted`. What it is for is a stretch of your own flow — a session that
reads beside one that writes. Handing an agent on does not need it: the callee's sessions run
under the permission and skills *its* role declares, however much more the agent you hand in
holds. Nor can it go below what the callee declares: `reader` handed to a role typed plain
`Agent` — whose permission is the default, `local=ALL` — is refused with `PermissionTooNarrow`.

An environment narrows the same way by being derived: a worktree, a subdirectory, a
[copy](/weaver/worktrees).

## Leave out what the run fills

Two kinds of role are nobody's to fill but the run's: an `Outworlder` — [the person at the
prompt](/weaver/human-agent) — and a `LocalEnv`, the directory the run was started in. Leave
either out of the call and the callee is handed the run's own:

```python
rlcr = load("humanize1:rlcr")
await rlcr(
    task,
    agents={"builder": agents["builder"], "reviewer": agents["critic"]},
    envs={},                    # rlcr's workspace is a LocalEnv: the run's own
    params=rlcr.expected_params(),
)                               # and its human, an Outworlder, is whoever is at the prompt
```

Or answer for the person yourself: `Outworlder.new()` is an outworlder a flow stands in for,
answering every question the callee puts to it with a hook of the caller's. See [The person as
an agent](/weaver/human-agent#stand-in-for-the-person).

## Pass params through

A flow that takes [params of its own](/weaver/flow-settings) is handed an instance of its own
class, which the flow names as `expected_params`:

```python
await rlcr(
    task, agents=..., envs={}, params=rlcr.expected_params.model_validate({"max": 12})
)
```

Where you can import the class itself — a flow of your own module — `params=Params(max=12)` is
the same thing, and one a type checker reads. That instance is taken as it is. An instance of another model, or a mapping of fields, is
validated into the callee's class at the call instead — `ParamsError` where it does not
validate, before the callee has run a line.

## Give it a budget of its own

```python
from hmz.flows import Budget, CostExceeded

try:
    await load(":explore")(task, agents=agents, envs=envs, params=FlowParams(),
                           budget=Budget(cost=2.0))
except CostExceeded:
    ...                         # the exploration is over; the rest of the run goes on
```

A called flow's budget is the **tighter** of its own and what remains of yours, and it reads
the result in `ctx.budget`. What it spends counts against every flow above it as it is spent,
so a child can never spend what its parent has not got. `duration` is a deadline rather than a
sum — two children gathered for an hour each fit in a parent's hour. And a budget spent stays
spent: every later turn under it raises again rather than spending more. See
[Budgets](/features/budgets).

## Run several calls at once

Gather them. Each is a branch of the run in its own right: its own `ctx`, its own budget under
yours, its own state and its own line in the running tree.

```python
import asyncio

split = load(":split")
await asyncio.gather(
    split(left, agents=agents, envs=envs, params=Params(left=n - 1)),
    split(right, agents=agents, envs=envs, params=Params(left=n - 1)),
)
```

Both branches may be handed the same agent: each gets a view of its own, so what one opens and
hangs is not the other's.

## Call as deep as you like

A flow may call itself, and may work out how deep to go from its own params or from what a
model just said:

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
    again = load(":split")
    await asyncio.gather(*(
        again(part, agents=agents, envs=envs, params=Params(left=params.left - 1))
        for part in parts(task)
    ))
```

A call is cheap — no files read, no task started, two frames on the stack — so a tree of ten
thousand calls is a tree of ten thousand calls rather than a problem.

**A chain of calls has a bottom: 64.** The call that would go deeper raises
`FlowDepthExceeded`, naming the flow. It is a `RecursionError` too, so code that already
catches one catches it — but it is raised by humanize at the call, rather than by Python out of
whatever the innermost frame happened to be doing.

## Picked up with the flow that called it

When a resumable run is [picked up](/user/resuming), the flows it calls are picked up too —
each one that is called again **exactly as it was**: the same ref, the same task, the same
agents (CLI, account, model, effort, permission, skills), the same environments, derived the
same way, and the same params. A call that matches carries on with the state it kept; one that
differs in anything starts afresh. Two identical calls are told apart by the order they were
made in, so a loop that calls one flow ten times picks up each of the ten.

A flow that is not resumable keeps nothing itself, and passes the picking up through to the
flows it calls.

## It brings its own skills

A role's [skills](/user/skills) are found in the flow that declares the role — its own
`skills/`, or fetched from the git URL it names — so a called flow's agents carry the called
flow's skills while it runs, and yours carry yours. A skill a flow names and cannot find is
refused at the call, with `FlowDefinitionError`, rather than at the first turn that needed it.

## See that both are running

The interface draws the running tree on its status line and on `/monitor` — `chat ▸ rlar` —
and the run's [record](/user/tracing) keeps every call and every return, so a five-hour trace
where phase two was `gen-plan` says so. From Python,
`hmz.runtime.flowing.engine.running()` answers with every call going now, oldest first, each
with its `ref`, its `depth` and its `parent`.

## Several flows in one file

Three phases of one thing are one thing to write and three to run. Mark each, and each is a
flow of its own, run as `<flow>:<name>`:

```python
"""Three phases of one thing."""

from hmz.flows import FlowContext, flow


@flow(agents=Drafting, envs=Envs, params=Idea, name="gen-idea")
async def gen_idea(task, *, agents: Drafting, envs: Envs, params: Idea, ctx: FlowContext):
    """Opens a loose idea into a repo-grounded draft."""


@flow(agents=Planning, envs=Envs, params=Plan, name="gen-plan")
async def gen_plan(task, *, agents: Planning, envs: Envs, params: Plan, ctx: FlowContext):
    """Turns that draft into a plan both sides have converged on."""
```

```sh
hmz exec -f humanize1:gen-idea -a drafter=claude/claude-opus-5:max -b cost=5 \
    "add undo to the editor"
hmz exec -f humanize1:gen-plan -a planner=claude/claude-opus-5:max \
    -a analyst=codex/gpt-5.6-sol:max -b cost=20 ""
```

Each declares its own agents and its own params: opening one asks about two roles rather than
five, and setting one up shows one phase's params rather than three phases' at once. What
passes between them is whatever they write, usually a file.

**The name is the function's, or `name=`.** A name written down where a flow is run should not
change under whoever renames the function, so a flow meant to be called by others says it
outright. `hidden=True` keeps a flow that is only ever called — a phase, an engine — out of the
lists a person picks from, and it is still loaded and run by its ref. Two flows of one name in
one directory are refused.

`@flow` makes a flow of the function; call it through its ref, or through what the decorator
answered — both are the same flow, and both are awaited the same way.

## See also

- [Hooks](/weaver/hooks) — getting between an agent and its turn.
- [Many turns at once](/weaver/async-flows)
- [Params of its own](/weaver/flow-settings)
- [Tracing](/user/tracing)
- [Reference › Flows › A flow that calls another
  flow](/reference/flows#a-flow-that-calls-another-flow)

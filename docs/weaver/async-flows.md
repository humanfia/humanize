# Many turns at once

Every flow is an `async def`, so every flow can have as many turns going at once as it likes.
Reach for it when you need two hundred files fixed at the same time, or when a flow has to wait
for more than one thing.

## A turn is something to await

`run` is a coroutine. A flow that awaits one turn after another is a flow that takes one turn
at a time, which is what most of them want:

```python
await agent.run(task, session=session)
await agent.run("now review it", session=session)
```

To have more than one going, start several and wait for all of them — `asyncio.gather`, or a
`TaskGroup`. Nothing about how the flow is started changes: `hmz exec` and the interface run
it on a loop of the run's own, and the run is over when the flow returns.

## Fan one agent out

One agent, one session per file, all of them going at once:

```python
# .humanize/flows/fanout/__init__.py
import asyncio

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    ShellEnvMixin,
    flow,
)


class Agents(AgentCollection):
    agent: Agent


class Workspace(LocalEnv, ShellEnvMixin): ...


class Envs(EnvCollection):
    workspace: Workspace


#: How many turns this flow has going at once, however many files there are.
WIDE = 8


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def fanout(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> list[str]:
    """One agent, one session per file, eight of them going at once."""
    agent, workspace = agents["agent"], envs["workspace"]
    _, listed, _ = await workspace.exec(["git", "ls-files", "src/*.py"])
    gate = asyncio.Semaphore(WIDE)

    async def one(path: str) -> str:
        async with gate:
            session = await agent.spawn(env=workspace)
            return await agent.run(f"{task}\n\nThe file is {path}.", session=session)

    return await asyncio.gather(*(one(path) for path in listed.split()))
```

```sh
hmz exec -f fanout -a agent=claude/claude-opus-5:high -b cost=40 \
    "add type annotations to this module"
```

The answers come back in the order the files were listed. **How wide** a fan-out runs is a
question about the machine and the account rather than about this library, so nothing caps it:
`gather` starts everything it is given. The semaphore is where a flow says otherwise, and every
file lands either way — the rest wait behind the ones running.

## Handle a turn that fails

`gather` raises the first failure and leaves the others running with nobody waiting for them.
Two better shapes, depending on what a failure means.

**Where one failed turn is one file to take again**, collect the failures instead of raising
them:

```python
from hmz.flows import HarnessError

said = await asyncio.gather(*(one(path) for path in paths), return_exceptions=True)
failed = [
    path for path, answer in zip(paths, said, strict=True) if isinstance(answer, HarnessError)
]
```

Anything that is not a `HarnessError` — a spent [budget](/features/budgets), a bug in the
flow — is still in `said` as the exception it was; raise it rather than read past it.

**Where one failed turn means the rest are pointless**, a `TaskGroup` cancels the others the
moment one fails, and `except*` takes the failures out by kind:

```python
said: list[str] = []
try:
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(one(path)) for path in paths]
    said = [task.result() for task in tasks]
except* HarnessError as failed:
    print(f"{len(failed.exceptions)} turns failed")
```

Cancelling a task that is taking a turn interrupts the turn: the CLI stops where it is, rather
than going on spending for nobody.

## Gather turns that differ

When the turns differ — two agents, or one agent in several places — gather the calls
themselves:

```python
acting = await agents["actor"].spawn(env=workspace)
reviewing = await agents["reviewer"].spawn(env=workspace)
acted, reviewed = await asyncio.gather(
    agents["actor"].run(task, session=acting),
    agents["reviewer"].run(REVIEW + task, session=reviewing),
)
```

## Gather whole flows

[`load`](/weaver/calling-flows) answers with a flow, and calling one is a coroutine — so whole
flows gather the same way turns do:

```python
from hmz.flows import load

part = load(":fanout")
await asyncio.gather(
    part("the parser", agents=agents, envs=envs, params=FlowParams()),
    part("the printer", agents=agents, envs=envs, params=FlowParams()),
)
```

Each gathered call is **a branch of the run in its own right**: its own `ctx`, its own budget
under what is left of yours, its own [state](/user/resuming) where it keeps one, and its own
line in the running tree the interface draws. The call a flow is in is a context variable, so
two branches gathered side by side are two calls under the one that gathered them, never one
inside the other.

Both branches may be handed the same agent. Each is given a view of its own, granted what that
flow declared: the sessions one opens and the hooks one hangs are that branch's, and the other
never sees them.

## Run one agent in several places

A worktree per task, a checkout per shard: **a session apiece**, each in its own environment,
and their turns going together. The workspace's role asks for worktrees:

```python
class Workspace(LocalEnv, GitWorktreeEnvMixin): ...


async def one(name: str) -> str:
    tree = await workspace.derive_worktree(ref="main")
    session = await agent.spawn(env=tree)
    return await agent.run(f"{task}\n\nYou are working on the {name} part.", session=session)


said = await asyncio.gather(*(one(name) for name in ("parser", "printer", "cli")))
```

The agent is still **one agent**: one CLI, one model, one role in the trace. What differs is
where each conversation works. See [Worktrees, copies and scratch](/weaver/worktrees).

## The one rule that trips people

**A session takes one turn at a time.** A conversation is a conversation: a second `run` on a
session while its first is under way is refused with `SessionError`, rather than queued behind
it or interleaved with it.

```python
await asyncio.gather(agent.run("a", session=s), agent.run("b", session=s))    # SessionError
await asyncio.gather(agent.run("a", session=s1), agent.run("b", session=s2))  # two at once
```

Two turns at once means two **sessions**. A word for a turn already running is
[`steer`](/user/steering), on an agent whose role declared `SteeringAgentMixin`.

## Reading a fan-out at the prompt

Above the editor you see one agent, with how many of its conversations are working. **tab**
and **shift+tab** step between the conversations that are working — not all two hundred, only
the ones thinking right now. The screen keeps the last eight conversations and the last two
thousand lines of each. The rest is in the [trace](/user/tracing). See [Many conversations at
once](/user/conversations).

## See also

- [Many conversations at once](/user/conversations) for the editor view of every conversation
  that is working.
- [Worktrees, copies and scratch](/weaver/worktrees) for giving each conversation a directory
  of its own.
- [A flow that calls a flow](/weaver/calling-flows)
- The [trace](/user/tracing) keeps everything a run writes down.
- [Reference › Flows › A flow that waits for more than one
  thing](/reference/flows#a-flow-that-waits-for-more-than-one-thing)

# Many turns at once

A flow is an `async def` and `agent.run` is a coroutine, so turns you start together run
together: two hundred files fixed at once, or an actor and a reviewer side by side. The one
rule is that **two turns at once need two sessions**.

## Try it

One agent, a session per file, at most eight going at a time:

```python{34,38,42}
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


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def fanout(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> list[str]:
    """One agent, a session per file, eight at a time."""
    agent, workspace = agents["agent"], envs["workspace"]
    _, listed, _ = await workspace.exec(["git", "ls-files", "src/*.py"])
    gate = asyncio.Semaphore(8)  # at most eight turns at once

    async def one(path: str) -> str:
        async with gate:
            session = await agent.spawn(env=workspace)  # one per file
            prompt = f"{task}\n\nThe file is {path}."
            return await agent.run(prompt, session=session)

    return await asyncio.gather(*(one(path) for path in listed.split()))
```

```sh
hmz exec -f fanout -a agent=claude/claude-opus-5:high -b cost=40 \
    "add type annotations to this module"
```

`gather` answers in the order the files were listed. Nothing in humanize caps how many turns
go at once, so the semaphore is yours to set: without it, every file starts at the same moment.
How wide is worth going depends on the CLI and the machine; see [the concurrency
page](/features/concurrency).

## One session, one turn at a time

A second `run` on a session whose turn is still going is refused with `SessionError`. It is not
queued and not interleaved:

```python
# One session: the second run raises SessionError.
await asyncio.gather(agent.run(a, session=s), agent.run(b, session=s))  # [!code error]

# Two sessions: both go at once.
await asyncio.gather(agent.run(a, session=s1), agent.run(b, session=s2))
```

To add a word to a turn that is already running, `steer` it instead. That needs a role that
declared `SteeringAgentMixin`, which Claude Code, Codex, Kimi Code and pi serve. See
[Steering](/user/steering).

## When a turn fails

Plain `gather` raises the first failure and leaves the other turns running with nobody waiting
for them. Pick the shape that matches what a failure means to you:

| Shape | The other turns | What you get back |
| --- | --- | --- |
| `gather(...)` | keep running, unwatched | the first failure, raised |
| `gather(..., return_exceptions=True)` | run to the end | every answer, with failures in place |
| `asyncio.TaskGroup` | cancelled at once, and each CLI stops | an `ExceptionGroup` of the failures |

::: code-group

```python [Collect the failures]
from hmz.flows import HarnessError

said = await asyncio.gather(
    *(one(path) for path in paths), return_exceptions=True
)
failed = [  # the files to take again
    path
    for path, answer in zip(paths, said, strict=True)
    if isinstance(answer, HarnessError)
]
```

```python [Stop at the first failure]
said: list[str] = []
try:
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(one(path)) for path in paths]
    said = [task.result() for task in tasks]
except* HarnessError as failed:
    print(f"{len(failed.exceptions)} turns failed")
```

:::

With `return_exceptions=True`, anything that is not a `HarnessError` also lands in the list: a
spent [budget](/features/allowances), or a bug in your flow. Raise it rather than read past it.

## Different turns at once

Two agents, or one agent with different prompts, gather the same way:

```python
acting = await agents["actor"].spawn(env=workspace)
reviewing = await agents["reviewer"].spawn(env=workspace)
acted, reviewed = await asyncio.gather(
    agents["actor"].run(task, session=acting),
    agents["reviewer"].run(REVIEW + task, session=reviewing),
)
```

## One agent in several places

Sessions that all write to one directory can trip over each other. `derive_worktree` checks out
a fresh git worktree and hands it back as an environment of its own; the role asks for it with
`GitWorktreeEnvMixin`. Spawn a session in each:

```python{1,5}
class Workspace(LocalEnv, GitWorktreeEnvMixin): ...


async def one(name: str) -> str:
    tree = await workspace.derive_worktree(ref="main")  # own checkout
    session = await agent.spawn(env=tree)
    prompt = f"{task}\n\nYou work on the {name} part."
    return await agent.run(prompt, session=session)


names = ("parser", "printer", "cli")
said = await asyncio.gather(*(one(name) for name in names))
```

It is still **one agent**: one CLI, one model, one role in the trace, with several
conversations working in different places. See [Worktrees, copies and
scratch](/weaver/worktrees).

## Whole flows at once

`load` finds a flow by its ref and hands it back ready to await. `"fanout"` is the flow from
[Try it](#try-it), found by its directory (see [A flow that calls a
flow](/weaver/calling-flows)). Whole flows gather the same way turns do:

```python
from hmz.flows import load

part = load("fanout")
await asyncio.gather(
    part("the parser", agents=agents, envs=envs, params=FlowParams()),
    part("the printer", agents=agents, envs=envs, params=FlowParams()),
)
```

Each call is a **branch of the run**, with its own `ctx`, its own budget under what is left of
yours, and its own line in the running tree. Both may be handed the same agent: the sessions
one branch opens and the [hooks](/weaver/hooks) it hangs are its own, and the other never sees
them.

## At the prompt

A fan-out shows as one agent with a count of its working conversations. <kbd>tab</kbd> and
<kbd>shift</kbd>+<kbd>tab</kbd> step between the agents that are working. See [Many
conversations at once](/user/conversations).

## See also

- [Branching a conversation](/weaver/branching), for two sessions that share a history
- [Worktrees, copies and scratch](/weaver/worktrees), for a directory per conversation
- [A flow that calls a flow](/weaver/calling-flows)
- [Reference › Flows](/reference/flows)

# Worktrees, copies and scratch

An **environment** is a working directory on a machine, and a session works in the one it was
spawned in. Derive more environments from the one you were handed when an agent should work in
several places at once: a git worktree per task, a throwaway copy to try something risky, or an
empty directory for the flow's own notes.

## Try it

Three parts of a program, a worktree for each, and one agent working in all three at once:

```python{20,35,36}
import asyncio

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    GitWorktreeEnvMixin,
    LocalEnv,
    flow,
)


class Agents(AgentCollection):
    agent: Agent


# This role may derive worktrees:
class Workspace(LocalEnv, GitWorktreeEnvMixin): ...


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def parts(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> list[str]:
    """A worktree per part, and an agent in each, all at once."""
    agent, workspace = agents["agent"], envs["workspace"]

    async def one(name: str) -> str:
        tree = await workspace.derive_worktree(ref="main")  # at main
        session = await agent.spawn(env=tree)  # works there
        prompt = f"{task}\n\nYou work on the {name} part."
        return await agent.run(prompt, session=session)

    names = ("parser", "printer", "cli")
    return await asyncio.gather(*(one(name) for name in names))
```

```sh
hmz exec -f parts -a agent=claude/claude-opus-5:high -b cost=20 \
    "port the tokenizer"
```

Each conversation has its own checkout, so the three cannot tread on each other's files or
index. They are still one agent, with one CLI, one model and one role in the
[trace](/user/tracing).

A session stays in the environment it was spawned in for every turn it takes. To carry a
conversation somewhere else, [fork](/weaver/branching#fork-into-another-directory) it there.

## Pick the kind

| You want | Call | Removed |
| --- | --- | --- |
| a directory under the workdir | `derive_subdir(subdir=…)` | never |
| a new git worktree | `derive_worktree(ref=…, dir=…)` | never, by humanize |
| a throwaway copy of the workdir | `derive_temp_clone(id)` | when the flow ends* |
| an empty directory of the flow's own | `derive_scratch(id)` | when the flow ends* |

\* A run that can be picked up keeps them: see [How long they last](#how-long-they-last).

Each call but `derive_subdir` needs a mixin on the role's type, exactly as an agent's role
does. A call the role did not declare raises `CapabilityNotGranted`.

```python
from hmz.flows import (
    GitWorktreeEnvMixin,
    LocalEnv,
    ScratchDirEnvMixin,
    TemporaryClonedDirEnvMixin,
)


class Workspace(
    LocalEnv,
    GitWorktreeEnvMixin,         # derive_worktree
    TemporaryClonedDirEnvMixin,  # derive_temp_clone
    ScratchDirEnvMixin,          # derive_scratch
):
    """The run's directory, and what the flow derives from it."""
```

Each call answers with an environment on the same machine, filling the same role and granted
what the one it came from was. A worktree of a workspace that may run programs may run
programs, and you can spawn an agent in any of them.

## Worktrees

```python
tree = await workspace.derive_worktree()               # workdir's HEAD
fixed = await workspace.derive_worktree(ref="v1.4.2")  # any ref
named = await workspace.derive_worktree(ref="main", dir="/srv/review")
```

The worktree is detached at `ref`, or at whatever the workdir has checked out if you give none.
`dir` says where, relative to the workdir or absolute. Leave it out and humanize picks a fresh
directory. A workdir outside a repository, a ref git does not know and a `dir` that is taken
each raise `WorktreeError`.

A worktree is **left in place** when the flow ends. It is a checkout of your repository, and
what an agent committed in it is yours to keep. `git worktree list` shows where each one is,
and `git worktree remove` takes one away.

## Temporary copies

```python
trial = await workspace.derive_temp_clone("try-1")
session = await agent.spawn(env=trial)
await agent.run("try the risky refactor here", session=session)
...
await workspace.destroy_temp_clone("try-1")  # or let the flow end
```

A copy of the workdir **as it is**, uncommitted changes and untracked files included, which a
worktree is not.

An id names one copy. Asking again for the same id from the same environment gives you the same
copy. Asking for it from another environment raises `TempCloneBusy`, and that includes the same
environment handed to a flow you call. So two branches of a run never share a copy that each
thinks is its own. `destroy_temp_clone` removes the copy now and frees the id. Removing one
that is not there does nothing.

## Scratch directories

```python
notes = await workspace.derive_scratch("notes")
# Writing needs FilesEnvMixin on the role too:
await notes.write("round-1.md", said.encode())
```

An empty directory beside the workdir, on the same machine: somewhere for the flow to keep what
it writes for itself, out of the repository. The same id is the same directory.
`destroy_scratch` removes it now. One that cannot be made or removed raises `ScratchError`.

## How long they last

A temporary copy or scratch directory is removed when the flow call that made it ends, and
every flow it called has ended too. It is never removed from under a branch still using it.

A run that [can be picked up](/user/resuming) keeps them instead. Their names come from the
workdir and the id, so a run resumed with `--resume` that asks for the same id finds the copy
it left. In a flow that runs for days, destroy what you are done with yourself.

## On another machine

A role typed `LocalEnv` is always on this machine, and `hmz exec` fills it with the directory
you run it in. Type it `Env` instead and whoever runs the flow names it with `-e`, which may be
a directory on a host `ssh` reaches:

```python
from hmz.flows import Env, GitWorktreeEnvMixin


class Workspace(Env, GitWorktreeEnvMixin): ...    # Env: named with -e
```

```sh
hmz exec -f parts -a agent=claude/claude-opus-5:high \
    -e workspace=ssh@gpu-box/home/me/repo -b cost=20 "port the tokenizer"
```

Everything above works the same there. Worktrees, copies and scratch directories are made on
that machine, `workdir` is a path on it, and an agent spawned in one works on it. See [Remote
execution](/user/remote-execution).

## See also

- [Many turns at once](/weaver/async-flows), for a flow that awaits several things
- [Branching a conversation](/weaver/branching), for the conversation rather than the files
- [Many conversations at once](/user/conversations), for reading them at the prompt
- [Reference › Flows](/reference/flows)

# Worktrees, copies and scratch

An **environment** is a working directory on a machine, and a session works in the one it was
spawned in. Derive more from the one you were handed when you want an agent working in several
places at once: a worktree per task, a throwaway copy to try something in, an empty directory
to keep notes. Each conversation is still one agent with one CLI, one model and one role in the
[trace](/user/tracing).

## Try it

```python
tree = await workspace.derive_worktree(ref="main")   # a new git worktree, at main
session = await agent.spawn(env=tree)                # this conversation works there
await agent.run("make the tests pass", session=session)
tree.workdir                                         # where that is, on its machine
```

A session works in its environment's `workdir` from its first turn to its last. It is not a
per-turn argument, and it does not move once the session is open: that is what a directory is
to a CLI. A conversation that should carry on somewhere else is
[forked](/weaver/branching#fork-into-another-directory) there.

## Ask for what you derive

Each kind of derived directory is something only some environments are asked to do, so the
role's type says which it needs, exactly as an agent's does:

```python
from hmz.flows import (
    GitWorktreeEnvMixin,
    LocalEnv,
    ScratchDirEnvMixin,
    TemporaryClonedDirEnvMixin,
)


class Workspace(LocalEnv, GitWorktreeEnvMixin, TemporaryClonedDirEnvMixin, ScratchDirEnvMixin):
    """The directory the run was started in, and what the flow makes beside it."""
```

| Call | Needs | Makes |
| --- | --- | --- |
| `derive_subdir(subdir=…)` | nothing: every environment | a directory under the workdir, made if missing |
| `derive_worktree(ref=…, dir=…)` | `GitWorktreeEnvMixin` | a new worktree of the repository the workdir is in |
| `derive_temp_clone(id)` | `TemporaryClonedDirEnvMixin` | a throwaway copy of the workdir |
| `derive_scratch(id)` | `ScratchDirEnvMixin` | an empty directory beside the workdir, on the same machine |

A call the role did not declare raises `CapabilityNotGranted`, whatever the machine could have
done. What any of them answers is an environment on the same machine, filling the same role
and granted what the one it came from was — so a worktree of a workspace that may run programs
may run programs, and an agent can be spawned in it.

## Worktrees

```python
tree = await workspace.derive_worktree()                      # what the workdir has checked out
fixed = await workspace.derive_worktree(ref="v1.4.2")         # a tag, a branch, a commit
named = await workspace.derive_worktree(ref="main", dir="/srv/review")
```

`git worktree add`, detached at `ref` — or at whatever the workdir has checked out, where there
is none. `dir` is where, relative to the workdir or absolute; left out, humanize picks a fresh
directory of its own. A workdir that is not in a repository, a ref git does not know and a
`dir` that is taken each raise `WorktreeError`.

A worktree is **left where it is** when the flow ends: it is a checkout of your repository, and
what an agent committed in it is yours to keep. Take it away with `git worktree remove` when you
are done with it.

## Temporary copies

```python
trial = await workspace.derive_temp_clone("try-1")
session = await agent.spawn(env=trial)
await agent.run("try the risky refactor here", session=session)
...
await workspace.destroy_temp_clone("try-1")         # or let the flow's end take it
```

A copy of the workdir as it is — uncommitted changes, untracked files and all — which is what a
worktree is not. It is made with a reflink where the filesystem has them, so a copy of a large
tree costs almost nothing until something in it is written.

**An id is one copy.** The same id asked for again by the same environment is the same copy,
made once. Asked for by *another* — including the same environment handed to a flow you call,
which is a view of its own there — it raises `TempCloneBusy`, so two branches of a run can never
share a throwaway directory they each think is theirs. `destroy_temp_clone` removes it now and
frees the id; removing one that is not there is nothing.

## Scratch directories

```python
notes = await workspace.derive_scratch("notes")
await notes.write("round-1.md", said.encode())       # with FilesEnvMixin on the role
```

An empty directory beside the workdir, on the same machine — somewhere to keep what the flow
writes for itself without putting it in the repository. The same id is the same directory.
`destroy_scratch` removes it now; one that cannot be made or removed raises `ScratchError`.

## How long they last

| | Removed |
| --- | --- |
| a worktree | never by humanize — it is a checkout of yours |
| a temporary copy, a scratch directory | when the flow that made it ends, and every flow it called has too — or when destroyed |
| …of a run that [can be picked up](/user/resuming) | not at all: kept, so that the run picked up finds them |

A copy or scratch directory goes when the flow call that made it is over and everything it
started is — never out from under a branch still using it. A resumable run keeps them instead,
and every name is deterministic — the workdir's path and the id — so a run picked up with
`--resume` that derives the same id from the same workdir finds the copy it left rather than
making another. Destroy what you are done with yourself, in a flow that runs for days.

## Where they live

On whichever machine the environment is — this one, or one reached over ssh — under humanize's
own home there (`~/.humanize` unless `HUMANIZE_HOME` says otherwise):

```
envs/<name>-<digest>/            one per workdir things are derived from
    clones/<id>-<digest>/        a temporary copy
    scratch/<id>-<digest>/       a scratch directory
    worktrees/<ref>-<random>/    a worktree added with no `dir` of its own
```

Under humanize's home rather than `/tmp`, because a resumable run keeps its copies across a
reboot, which a temporary directory that is swept does not promise; because a reflink only
works on the filesystem the workdir is on, which a home directory is far likelier to share with
a project than `/tmp` is; and because one directory holds all of it: `envs/` can be removed
whenever no run is using it.

## A worked fan-out

A worktree per part, and all three going at once:

```python
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


class Workspace(LocalEnv, GitWorktreeEnvMixin): ...


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def parts(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> list[str]:
    """One worktree per part of the program, and an agent in each, all at once."""
    agent, workspace = agents["agent"], envs["workspace"]

    async def one(name: str) -> str:
        tree = await workspace.derive_worktree(ref="main")
        session = await agent.spawn(env=tree)
        return await agent.run(
            f"{task}\n\nYou are working on the {name} part.", session=session
        )

    return await asyncio.gather(*(one(name) for name in ("parser", "printer", "cli")))
```

Each conversation sees its own checkout, so the three turns cannot tread on each other's index.
Each is still the same agent at the same model and effort, in one role in the trace.

## On another machine

A role typed `LocalEnv` is always this machine's workspace. A role typed `Env` is named with
`-e`, and may be a directory on a host `ssh` reaches:

```python
class Repo(Env, GitWorktreeEnvMixin): ...


class Envs(EnvCollection):
    repo: Repo
```

```sh
hmz exec -f parts -a agent=claude/claude-opus-5:high -e repo=ssh@gpu-box/home/me/repo \
    -b cost=20 "port the tokenizer"
```

Everything above works the same there: the worktrees, copies and scratch directories are made
on that machine, under humanize's home *there*, and `workdir` is a path on it. A flow names
where the work happens using the only names the far end has, and an agent spawned in one works
on that machine. See [Remote execution](/user/remote-execution).

## See also

- [Many conversations at once](/user/conversations) — reading them at the prompt
- [Many turns at once](/weaver/async-flows) — a flow that awaits several things
- [Branching a conversation](/weaver/branching) — the conversation rather than the files
- [Reference › Flows › Worktrees, copies and scratch
  directories](/reference/flows#worktrees-copies-and-scratch-directories)

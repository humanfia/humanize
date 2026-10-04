# Worktrees, copies and scratch

In this guide you give a flow more places to work than the one directory it was handed. You
build two flows: `parts`, which checks out a git worktree per part of a program and has an
agent work in each at once, and `guarded`, which snapshots the workspace before a risky turn
and rewinds it when a check fails.

Reach for this page when agents working side by side would tread on each other's files, when
an attempt should be thrown away if it goes wrong, or when the flow needs somewhere of its own
to keep notes out of the repository.

::: info Before you start
- A flow of your own running: [Your first flow](/weaver/writing-a-flow).
- A git repository with a commit on `main`. Worktrees and snapshots are git's.
- For several turns at once, `asyncio.gather`: [Many turns at once](/weaver/async-flows).
:::

## How it works

An **environment** is a working directory on a machine. A session works in the environment it
was spawned in, for every turn it takes, and a flow is handed its environments by role:
`envs["workspace"]`. From one environment a flow can **derive** others on the same machine, and
spawn agents in them like in any other.

What a role may derive is declared on its type, with a mixin per capability, exactly as an
agent's role declares what it may be asked. A call the role did not declare raises
`CapabilityNotGranted`, whatever the machine could do.

### Pick the kind

| You want | Declare on the role | Call | Removed |
| --- | --- | --- | --- |
| a directory under the workdir | nothing | `derive_subdir(subdir=…)` | never |
| a new git worktree, at any ref | `GitWorktreeEnvMixin` | `derive_worktree(ref=…, dir=…)` | never, by humanize |
| a throwaway copy of the workdir as it is | `TemporaryClonedDirEnvMixin` | `derive_temp_clone(id)` | when the flow ends\* |
| an empty directory of the flow's own | `ScratchDirEnvMixin` | `derive_scratch(id)` | when the flow ends\* |
| the workdir put back as it was | `GitEnvMixin` | `snapshot()`, then `rewind(ref)` | never, by humanize |

\* A run that can be picked up keeps them: see [How long they last](#how-long-they-last).

Every derived environment is on the same machine, and is granted what the one it came from
was. A worktree of a workspace that may run programs may run programs.

## Example: a worktree per part

`parts` gives each of three parts of a program its own checkout of `main`, and one agent a
session in each, all at once:

```python
# .hmz/flows/parts/__init__.py
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

PARTS = ("parser", "printer", "cli")


class Agents(AgentCollection):
    agent: Agent


class Workspace(LocalEnv, GitWorktreeEnvMixin):  # ①
    """The run's directory, which the flow may check out more worktrees of."""


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def parts(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> list[str]:
    """A worktree per part, and an agent in each, all at once."""
    agent, workspace = agents["agent"], envs["workspace"]

    async def one(part: str) -> str:
        tree = await workspace.derive_worktree(ref="main")  # ②
        print(f"{part}: {tree.workdir}")
        session = await agent.spawn(env=tree)  # ③
        return await agent.run(f"{task}\n\nYou work on the {part}.", session=session)

    return await asyncio.gather(*(one(part) for part in PARTS))  # ④
```

### What each part does

1. **`class Workspace(LocalEnv, GitWorktreeEnvMixin)`** is the role's type. `LocalEnv` makes
   it the directory the run starts in, and `GitWorktreeEnvMixin` grants `derive_worktree`.
   Without the mixin, the call in ② raises `CapabilityNotGranted`. The machine needs `git` on
   its PATH: a run on one without is refused with `CapabilityMissing` before anything runs.
2. **`derive_worktree(ref="main")`** checks out a new worktree of the repository, detached at
   `main`, and answers with an environment there. Leave `ref` out for whatever the workdir has
   checked out. `tree.workdir` is where it is: humanize picks a fresh directory unless you
   pass `dir=`.
3. **`agent.spawn(env=tree)`** opens a session in the worktree, so every file it edits and
   every command it runs is there, not in your checkout.
4. **`asyncio.gather`** runs the three at once and answers with their three answers, in the
   order of `PARTS`. The three sessions cannot touch each other's files or index. They are
   still one agent: one CLI, one model and one role in the [trace](/user/tracing).

### Run it

```sh
hmz exec -f parts -a agent=claude/claude-sonnet-5-5:low -p budget.cost=1 \
    "Write a one-line file PLAN.md saying what you would build first. Nothing else."
```

A real run, abridged. The three turns start together and finish in any order:

```text
● agent is working
● agent is working
● agent is working
● Write(/home/you/.hmz/envs/calc-82c815b6b57b/worktrees/main-95e4a811/PLAN.md)
● Write(/home/you/.hmz/envs/calc-82c815b6b57b/worktrees/main-636f5a37/PLAN.md)
● Write(/home/you/.hmz/envs/calc-82c815b6b57b/worktrees/main-2c5c858b/PLAN.md)
● I wrote `PLAN.md` as one line: build the parser's tokenizer and a minimal recursive-descent core …
✻ input 4 · output 213 · cache_read 28.1k · cache_write 5.7k · $0.02 · claude-sonnet-5-5 · agent
parser: /home/you/.hmz/envs/calc-82c815b6b57b/worktrees/main-95e4a811
printer: /home/you/.hmz/envs/calc-82c815b6b57b/worktrees/main-636f5a37
cli: /home/you/.hmz/envs/calc-82c815b6b57b/worktrees/main-2c5c858b
…
✻ Worked for 5s · agent
```

### Check it worked

A worktree is left in place when the flow ends: it is a checkout of your repository, and what
an agent committed in it is yours to keep. `git worktree list` shows each one:

```sh
git worktree list
```

```text
/home/you/calc                                                    5ad70a3 [main]
/home/you/.hmz/envs/calc-82c815b6b57b/worktrees/main-2c5c858b  5ad70a3 (detached HEAD)
/home/you/.hmz/envs/calc-82c815b6b57b/worktrees/main-636f5a37  5ad70a3 (detached HEAD)
/home/you/.hmz/envs/calc-82c815b6b57b/worktrees/main-95e4a811  5ad70a3 (detached HEAD)
```

Your own checkout is untouched. `git worktree remove <path>` takes one away.

To test the flow without an agent, the fake workspace makes its worktrees in memory:

```python
# tests/test_parts.py
from hmz.sdk import fakes


async def test_each_part_gets_its_own_worktree() -> None:
    agent = fakes.FakeAgentDriver(reply=lambda prompt, **_: prompt.split()[-1])  # ①

    said = await fakes.run_fake("parts", "plan it", agents={"agent": agent})

    assert said == ["parser.", "printer.", "cli."]  # ②
    places = {session.placement.workdir for session in agent.sessions}
    assert len(places) == 3  # ③
```

```text
.                                                                        [100%]
1 passed in 0.09s
```

1. **A reply function** answers each turn with the last word of its prompt, so each answer
   says which part it came from.
2. **`run_fake` returns what the flow returned**: the three answers, in the order of `PARTS`.
3. **`session.placement.workdir`** is where each fake session worked. Three sessions in three
   places proves no two parts shared a checkout.

## Example: undo a turn that broke the check {#snapshots-and-rewinding}

`guarded` records the workspace before the agent touches it, lets the agent work, and runs a
check. If the check fails, it puts the workspace back exactly as it was, files the agent
created included. The project has a `check.py` that the change must keep passing:

```python
# check.py
from calc import add

assert add(2, 3) == 5, "add(2, 3) should be 5"
print("ok")
```

```python
# .hmz/flows/guarded/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    GitEnvMixin,
    LocalEnv,
    ShellEnvMixin,
    flow,
)

CHECK = ["python3", "check.py"]


class Agents(AgentCollection):
    agent: Agent


class Workspace(LocalEnv, ShellEnvMixin, GitEnvMixin):  # ①
    """The run's directory: the flow may run programs in it, and put it back."""


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def guarded(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> bool:
    """Try the task, and put everything back if the check fails."""
    agent, workspace = agents["agent"], envs["workspace"]
    before = await workspace.snapshot("before-task")  # ②
    session = await agent.spawn(env=workspace)
    await agent.run(task, session=session)
    code, _, err = await workspace.exec(CHECK)  # ③
    if code == 0:
        print("check passed: keeping the change")
        return True
    await workspace.rewind(before)  # ④
    print(f"check failed, rewound to {before}")
    print(err.strip().splitlines()[-1])
    return False
```

### What each part does

1. **`GitEnvMixin`** grants `snapshot`, `rewind` and `snapshots`, done with git.
   `ShellEnvMixin` grants `exec`, to run the check. The machine needs `git` on its PATH: a run
   on one without is refused with `CapabilityMissing` before anything runs.
2. **`snapshot("before-task")`** records the whole git worktree as it is now, untracked files
   and the index included, as a commit kept under `refs/hmz/snapshots/before-task`. Nothing
   checked out moves and no file is touched. It returns that ref. Leave the name out and the
   snapshot gets one of its own, such as `refs/hmz/snapshots/20260930T054022.130819Z-3cfa`.
   Taking the same name again replaces the snapshot kept under it.
3. **`exec(CHECK)`** runs `python3 check.py` in the workdir and answers with its exit status,
   stdout and stderr. The argv runs as it is, with no shell between.
4. **`rewind(before)`** puts the worktree back as the snapshot has it: the commit that was
   checked out, the index and every file. Whatever came since is removed, commits and new
   files included.

### Run it

```sh
hmz exec -f guarded -a agent=claude/claude-sonnet-5-5:high -p budget.cost=1 \
    "Change add in calc.py so that it multiplies its arguments instead, and add a file NOTES.md saying why."
```

The agent does what it was asked, which breaks the check, so the flow puts everything back:

```text
● agent is working
● Bash(cd /home/you/calc && ls && cat calc.py)
● Bash(cd /home/you/calc && cat check.py)
● Edit(/home/you/calc/calc.py)
● Write(/home/you/calc/NOTES.md)
● `add` in `calc.py` now returns `a * b`, and `NOTES.md` explains the change. …
  `check.py` will now fail. It still asserts `add(2, 3) == 5`, and the function returns 6. …
✻ input 8 · output 673 · cache_read 61.2k · cache_write 6.0k · $0.03 · claude-sonnet-5-5 · agent
…
✻ Worked for 8s · agent
check failed, rewound to refs/hmz/snapshots/before-task
AssertionError: add(2, 3) should be 5
```

The last two lines are the flow's own `print`s. Given a task that keeps the check green, such
as `"add a subtract function to calc.py"`, it prints `check passed: keeping the change` and
leaves the edit in your working tree.

### Check it worked

After the failed run, the agent's edit and its new `NOTES.md` are gone, and the snapshot is
still there to look at:

```sh
git status --short
git for-each-ref refs/hmz
git log --oneline -1 refs/hmz/snapshots/before-task
```

```text
?? .hmz/
bbb6915909f7716b82f3a408104593c20fe8928d commit	refs/hmz/snapshots/before-task
bbb6915 hmz: snapshot before-task
```

`.hmz/` is where your flows are, and a rewind never removes it. Files git ignores are
left alone too. A snapshot stays in the repository until something removes it: `git
update-ref -d refs/hmz/snapshots/before-task` does.

The fake workspace snapshots and rewinds in memory, so both branches of the flow are testable
without an agent or git:

```python
# tests/test_guarded.py
from hmz.sdk import fakes

ADDS = "def add(a, b):\n    return a + b\n"
MULTIPLIES = "def add(a, b):\n    return a * b\n"


def check(
    command: tuple[str, ...] | str, env: fakes.FakeEnvDriver
) -> tuple[int, str, str] | None:  # ①
    if command != ("python3", "check.py"):
        return None
    if env.text("calc.py") == ADDS:
        return 0, "ok\n", ""
    return 1, "", "AssertionError: add(2, 3) should be 5\n"


async def test_a_failed_check_is_rewound() -> None:
    here = fakes.FakeEnvDriver({"calc.py": ADDS}, run=check)

    async def breaks_it(prompt: str, **_: object) -> str:  # ②
        await here.write("calc.py", MULTIPLIES.encode())
        await here.write("NOTES.md", b"add multiplies now\n")
        return "done"

    kept = await fakes.run_fake(
        "guarded",
        "make add multiply",
        agents={"agent": fakes.FakeAgentDriver(reply=breaks_it)},
        local=here,
    )

    assert kept is False
    assert here.files == {"calc.py": ADDS.encode()}  # ③


async def test_a_passing_check_keeps_the_change() -> None:
    here = fakes.FakeEnvDriver({"calc.py": ADDS}, run=check)

    kept = await fakes.run_fake("guarded", "add subtract", local=here)  # ④

    assert kept is True
```

```text
..                                                                       [100%]
2 passed in 0.09s
```

1. **`check`** answers the workspace's `exec`: it passes while `calc.py` still adds, and fails
   the way `check.py` would once it does not. `None` leaves any other command to the fake's
   defaults.
2. **`breaks_it`** is the agent's turn: it edits `calc.py` and creates `NOTES.md` in the fake
   workspace, as a real agent did above.
3. **`here.files`** is the workdir after the flow. The edit and the new file are gone, which is
   what `rewind` promised.
4. **Left out, the agent answers `"ok"`** and changes nothing, so the check passes and the flow
   keeps the (empty) change.

## Worktrees

```python
tree = await workspace.derive_worktree()  # workdir's HEAD
fixed = await workspace.derive_worktree(ref="main")  # any ref git knows
named = await workspace.derive_worktree(ref="main", dir="../review")
```

A worktree is detached at `ref`, or at whatever the workdir has checked out if you give none.
`dir` says where, relative to the workdir or absolute. A workdir outside a repository, a ref
git does not know and a `dir` that is taken each raise `WorktreeError`.

## Temporary copies

```python
trial = await workspace.derive_temp_clone("try-1")
session = await agent.spawn(env=trial)
said = await agent.run("try the risky refactor here", session=session)
await workspace.destroy_temp_clone("try-1")  # or let the flow end
```

A copy of the workdir **as it is**, uncommitted changes and untracked files included, which a
worktree is not. It needs no git, unless the workdir is itself a linked worktree: that copy is
made a repository of its own with git.

An id names one copy. Asking again for the same id from the same environment gives you the
same copy. Asking for it from another environment raises `TempCloneBusy`, and that includes
the same environment handed to a flow you call, so two branches of a run never share a copy
that each thinks is its own. `destroy_temp_clone` removes the copy now and frees the id.
Removing one that is not there does nothing.

## Scratch directories

```python
notes = await workspace.derive_scratch("notes")
await notes.write("round-1.md", said.encode())  # needs FilesEnvMixin on the role
```

An empty directory beside the workdir, on the same machine: somewhere for the flow to keep what
it writes for itself, out of the repository. The same id is the same directory.
`destroy_scratch` removes it now. One that cannot be made or removed raises `ScratchError`.

## How long they last

A temporary copy or scratch directory is removed when the flow call that made it ends, and
every flow it called has ended too. It is never removed from under a branch still using it.

A run that [can be picked up](/user/resuming) keeps them instead. A run resumed with `--resume`
that asks for the same id finds the copy it left. In a flow that runs for days, destroy what you
are done with yourself.

Worktrees and snapshots are never removed by humanize. They are git's, and yours.

## Variations

**A snapshot per round.** In a [loop](/weaver/loops), take `snapshot(f"round-{n}")` after each
round the check passes, and rewind to the newest when one fails.
`await workspace.snapshots()` lists the refs kept, oldest first, and every worktree of the
repository shares them.

**Rewind to any ref.** `rewind` takes any ref git knows of a commit, such as `rewind("HEAD~1")`,
a branch or a tag. It then behaves as `git reset --hard` followed by `git clean` would, with the
branch checked out moved to that commit.

**Try in a copy instead.** Where the workdir is not a git repository, or should not be touched
at all while the attempt runs, derive a temporary copy and spawn the agent there.

**Write against the interface.** Code that only snapshots and rewinds can take a
`RewindableEnvMixin`, the interface `GitEnvMixin` implements. A role still declares
`GitEnvMixin`.

## On another machine

A role typed `LocalEnv` is always on this machine, and `hmz exec` fills it with the directory
you run it in. Type it `Env` instead and whoever runs the flow names it with `-e`, which may be
a directory on a host `ssh` reaches, or one a container of its own is given
(`-e workspace=docker@gpubox/srv/repo`):

```python
from hmz.flows import Env, GitWorktreeEnvMixin


class Workspace(Env, GitWorktreeEnvMixin): ...  # Env: named with -e
```

```sh
hmz exec -f parts -a agent=claude/claude-opus-5:high \
    -e workspace=ssh@gpu-box/home/me/repo -p budget.cost=20 "port the tokenizer"
```

Everything on this page works the same there. Worktrees, copies, scratch directories and
snapshots are made on that machine, `workdir` is a path on it, and an agent spawned in one
works on it. In a container, what is not under the workdir goes with the container when the
run ends. See [Remote execution](/user/remote-execution) and [Containers](/user/containers).

## Pitfalls

- **No git, no snapshots.** `GitEnvMixin` on a machine without `git` is refused before the run
  starts, with `CapabilityMissing`. That matters most for a container: `python:3.12-slim` has
  no git, and `python:3.12` does.
- **Not a repository.** Run in a directory that is not in a git worktree, `snapshot` raises
  `RewindError`, and so does `rewind` to a ref git does not know:

  ```text
  hmz.flows.errors.RewindError: could not snapshot /home/you/scratch: fatal: not a git repository (or any of the parent directories): .git
  ```

- **A rewind throws away commits too.** Anything the agent committed after the snapshot goes
  with it. Snapshot again once a change is worth keeping.
- **A session stays where it was spawned.** Deriving a worktree does not move a session that
  is already open. Spawn a new one there, or [fork](/weaver/branching#fork-into-another-directory)
  the conversation into it.
- **Worktrees pile up.** Nothing removes them, so a flow that makes one per round leaves one per
  round. Pass a fixed `dir=` and remove it yourself, or use a temporary copy.

## Next steps

- [Many turns at once](/weaver/async-flows), for a flow that awaits several things
- [Branching a conversation](/weaver/branching), for the conversation rather than the files
- [Loops](/weaver/loops), to snapshot every round
- [Many conversations at once](/user/conversations), for reading them at the prompt
- [Reference › Worktrees, copies and scratch
  directories](/reference/flows#worktrees-copies-and-scratch-directories) and [Snapshots and
  rewinding](/reference/flows#snapshots-and-rewinding)

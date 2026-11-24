---
title: Fan out agents across git worktrees
description: Write an async flow that runs several attempts at one task at once, each in its own git worktree, keeps the best one and removes the rest.
---

# Fan out agents across git worktrees

Write a flow that sends one task to three agent sessions at once. Each session works in its own git worktree so no attempt touches another's files. The flow runs your check in every worktree, copies the smallest passing change into your project, and removes the worktrees.

![One task goes to three worktrees at once, a check runs in each, and the smallest change that passed is kept](/diagrams/tutorials-parallel-worktrees-1.svg)

## What you need

- Humanize installed and one coding agent signed in ([Finish your first task in the terminal](/tutorials/first-task-terminal)).
- Experience writing a flow ([Write your first flow](/tutorials/first-flow)).
- A git repository with at least one commit and a test command. This tutorial uses `~/shop` and `python3 -m pytest -q`.
- `git` on your PATH.

## 1. Declare what the flow needs

Create `.hmz/flows/best_of/__init__.py` in your project and declare its roles and settings:

```python
import asyncio
import shlex
from datetime import timedelta
from typing import NamedTuple

from hmz.flows import (
    Agent,
    AgentCollection,
    Budget,
    BudgetExceeded,
    EnvCollection,
    FlowContext,
    FlowParams,
    GitWorktreeEnvMixin,
    LocalEnv,
    ShellEnvMixin,
    flow,
)


class Agents(AgentCollection):
    coder: Agent


class Workspace(LocalEnv, ShellEnvMixin, GitWorktreeEnvMixin):
    """The project. The flow may run programs in it and add worktrees of it."""


class Envs(EnvCollection):
    workspace: Workspace


class Params(FlowParams):
    count: int = 3
    minutes: float = 10
    check: str = "python3 -m pytest -q"


class Attempt(NamedTuple):
    number: int
    tree: Workspace
    passed: bool
    lines: int
```

`Workspace` represents your project. `LocalEnv` binds it to the starting directory so you do not need `-e`. `GitWorktreeEnvMixin` lets the flow create worktrees, and `ShellEnvMixin` lets it run commands. `Params` sets the attempt count, the per-turn time limit, and the check command.

## 2. Give each attempt a worktree and a turn

Add the `best_of` flow and the `attempt` helper below the classes:

```python
@flow(agents=Agents, envs=Envs, params=Params)
async def best_of(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> int | None:
    """Several attempts at one task, each in its own worktree. The best is kept."""
    coder, workspace = agents["coder"], envs["workspace"]
    trees: list[Workspace] = []

    async def attempt(number: int) -> Attempt | None:
        tree = await workspace.derive_worktree()
        trees.append(tree)
        try:
            await coder.run(
                f"{task}\n\nYou are attempt {number} of {params.count}.",
                session=await coder.spawn(),
                env=tree,
                budget=Budget(
                    duration=timedelta(minutes=params.minutes), graceful=False
                ),
            )
        except BudgetExceeded as error:
            if not error.own:
                raise  # the run's own budget is spent
            print(f"attempt {number}: out of time")
            return None
        await tree.exec(["git", "add", "-A"])
        status, _, _ = await tree.exec(shlex.split(params.check))
        _, stat, _ = await tree.exec(["git", "diff", "--cached", "--numstat"])
        lines = sum(
            int(n) for row in stat.splitlines() for n in row.split()[:2] if n.isdigit()
        )
        verdict = "passed" if status == 0 else "failed"
        print(f"attempt {number}: check {verdict}, {lines} lines changed")
        return Attempt(number, tree, status == 0, lines)
```

Each call to `attempt` runs six steps:

1. `derive_worktree()` creates a worktree under `~/.local/state/humanize/envs/` checked out at your project's current commit, excluding uncommitted changes, and returns it as an environment.
2. `coder.spawn()` opens a dedicated session so the turns can run in parallel.
3. `env=tree` runs the turn inside the worktree instead of your project.
4. `budget=` caps the turn on top of the run budget, and `graceful=False` stops the agent the moment the minutes are up.
5. `BudgetExceeded` with `own` set drops the timed-out attempt and continues; without `own`, the whole run's budget is spent and the flow re-raises the error.
6. The three `exec` calls stage the worktree's changes, run your check, and count the changed lines.

## 3. Run them at once, keep the best, clean up

Finish `best_of` after `attempt`:

```python
    try:
        done = await asyncio.gather(*(attempt(n) for n in range(1, params.count + 1)))
        passed = [one for one in done if one and one.passed]
        if not passed:
            print("no attempt passed the check: nothing kept")
            return None
        best = min(passed, key=lambda one: one.lines)
        _, kept, _ = await best.tree.exec(["git", "write-tree"])
        await workspace.exec(
            ["git", "restore", f"--source={kept.strip()}", "--worktree", "--", "."]
        )
        print(f"kept attempt {best.number}")
        return best.number
    finally:
        for tree in trees:
            await workspace.exec(
                ["git", "worktree", "remove", "--force", str(tree.workdir)]
            )
```

`asyncio.gather` runs every attempt in parallel and waits for them to finish. The flow picks the passing attempt with the fewest changed lines, then runs `git write-tree` in that worktree and `git restore` in your project to copy the files over without committing them. Because Humanize never removes worktrees on its own, the `finally` block runs `git worktree remove` on each one even if an attempt raises.

## 4. Test it without an agent

Save this test as `tests/test_best_of.py` to run the flow against an in-memory fake agent and project with `run_fake`:

```python
import asyncio

from hmz.sdk import fakes

CHANGED = {"1": 40, "2": 9, "3": 12}  # lines each attempt changes
FAILS = "2"  # the attempt whose check fails


def test_the_smallest_passing_attempt_is_kept() -> None:
    attempts: dict[str, str] = {}  # worktree -> attempt number

    async def reply(prompt: str, *, session: fakes.FakeSession, **_: object) -> str:
        number = prompt.split("attempt ")[1][0]
        attempts[str(session.placement.workdir)] = number
        await asyncio.sleep(0.01)  # long enough for the turns to overlap
        return "done"

    def run(command: tuple[str, ...], env: fakes.FakeEnvDriver) -> tuple[int, str, str]:
        number = attempts.get(str(env.workdir), "")
        if command == ("python3", "-m", "pytest", "-q"):
            return int(number == FAILS), "", ""
        if command == ("git", "diff", "--cached", "--numstat"):
            return 0, f"{CHANGED[number]}\t0\tshop/checkout.py\n", ""
        return 0, "", ""

    project = fakes.FakeEnvDriver({"shop/checkout.py": b""}, run=run)
    coder = fakes.FakeAgentDriver(reply=reply)

    kept = asyncio.run(
        fakes.run_fake(
            "best_of", "add a discount code", agents={"coder": coder}, local=project
        )
    )

    assert kept == 3  # attempt 2 is smaller, but its check failed
    assert coder.peak == 3  # three turns at once
    removed = sum(one[:3] == ("git", "worktree", "remove") for one in project.commands)
    assert removed == 3  # every worktree is gone
```

The `run` function intercepts the flow's `exec` calls so attempt 2 fails the check and each attempt reports its own line count. Run the test from your project folder, where `run_fake` finds the flow by name, in a Python environment with `hmz` and `pytest` installed:

```sh
python3 -m pytest -q tests/test_best_of.py
```

![The test passes](/shots/tutorials-parallel-worktrees-test.svg)

## 5. Run it on a task

Commit your work, then run the flow. `budget.duration` limits the whole run, while `minutes` limits each turn:

```sh
hmz exec -f @local/best_of -a coder=claude/claude-haiku-4-5 -p budget.duration=30m "Add a discount code to checkout"
```

Three turns start at once. When they finish, the flow prints the result of each attempt and which one it kept.

![hmz exec starts three turns at once, then prints each attempt's check and the attempt it kept](/shots/tutorials-parallel-worktrees-exec.svg)

Inspect the kept change in your uncommitted working tree:

```sh
git diff
```

![git diff shows the kept attempt's change to checkout.py](/shots/tutorials-parallel-worktrees-diff.svg)

Confirm the worktrees are gone and only your main checkout remains:

```sh
git worktree list
```

![git worktree list shows one line: the project itself](/shots/tutorials-parallel-worktrees-cleaned.svg)

Pass `-p` to override any setting: `-p count=5` runs five attempts, `-p minutes=5` gives each turn five minutes, and `-p check="npm test"` changes the check command.

## 6. Watch the sessions

Open Humanize Desktop while the flow runs and select the epic under your project in the sidebar. The graph shows the `coder` agent with three parallel session lanes, and the **Environments** list on the right shows each session's worktree.

![The epic in Humanize Desktop: one agent with three sessions working, and a worktree listed for each](/shots/tutorials-parallel-worktrees-app.svg)

To run and watch the flow in the terminal interface instead, open `hmz` and run `/flow @local/best_of` once to pick an agent for `coder` and set a budget (see [Finish your first task in the terminal](/tutorials/first-task-terminal)). Then start the task:

```text
/flow @local/best_of Add a discount code to checkout
```

Press <kbd>←</kbd> on the empty prompt to open the monitor, press <kbd>space</kbd> on the agent to list its sessions and worktrees, and press <kbd>enter</kbd> on a session to read its transcript.

![The terminal interface: three turns start, the monitor opens, and the agent's three sessions are listed](/shots/tutorials-parallel-worktrees-monitor.svg)

## What you did

- Declared a project role that creates git worktrees and runs shell commands.
- Ran three parallel agent sessions with `asyncio.gather` under per-turn time limits.
- Kept the smallest change that passed your check.
- Cleaned up the worktrees.
- Verified the flow with fakes and in the UI.

## Next

- [Worktrees, clones and scratch](/builder/worktrees): other isolated environments a flow can create.
- [Concurrent turns](/builder/async): more patterns for running turns in parallel.
- [Budgets in a flow](/builder/budgets): limits for a run, a call, and a turn.
- [Test a flow](/builder/testing): full reference for testing with fakes.

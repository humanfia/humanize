# Loops

A loop gives an agent the task again and again until something ends it. Writing one comes down
to three choices: what the next turn remembers, what ends the loop, and what a failed turn does
to it.

## What the next turn remembers

A **Ralph loop** starts every round from nothing: a new session — a new conversation — for
every turn, so the agent works from the task and the repository alone.

```python
while True:
    session = await agent.spawn(env=workspace)
    await agent.run(task, session=session)
```

Move one line and it is the opposite loop, one conversation that remembers every round:

```python
session = await agent.spawn(env=workspace)  # [!code ++]
while True:
    session = await agent.spawn(env=workspace)  # [!code --]
    await agent.run(task, session=session)
```

| | `spawn` inside the loop | `spawn` before it |
| --- | --- | --- |
| The official flow | [`ralph_loop`](/flows/ralph-loop) | [`stateful_ralph`](/flows/stateful-ralph) |
| Each turn starts from | the task and the repository | everything said and done so far |
| Reach for it when | earlier attempts would mislead the next one | each round builds on what the last one learned |

The agent is the same either way. The flow decides what it remembers.

## The real `ralph_loop`

This is `ralph_loop` as the official flowverse ships it, less its module docstring:

```python
import asyncio

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    HarnessError,
    LocalEnv,
    flow,
)

STALLED = 3
PAUSE = 5.0


class Agents(AgentCollection):
    agent: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, resumable=True)  # [!code highlight]
async def ralph_loop(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """The task again and again, a fresh session every round."""
    state = ctx.state
    assert state is not None
    agent = agents["agent"]
    stalled = 0
    while True:
        state["rounds"] = rounds = (state["rounds"] if "rounds" in state else 0) + 1  # [!code highlight]
        print(f"round {rounds}")
        session = await agent.spawn(env=envs["workspace"])
        try:
            answered = await agent.run(task, session=session)
        except HarnessError as error:  # [!code highlight]
            print(f"round {rounds} failed: {error}")
            answered = ""
        stalled = 0 if answered else stalled + 1  # [!code highlight]
        if stalled >= STALLED:  # [!code highlight]
            print(f"stopping: {stalled} rounds in a row answered with nothing")
            return
        await asyncio.sleep(PAUSE)
```

Besides a pause of `PAUSE` seconds between rounds, four things surround the two lines of the
loop:

1. **It keeps its place.** `resumable=True` hands the flow `ctx.state`, a dictionary that is
   saved as it is written. Stop the run, pick it up with `hmz exec --resume` or `/resume`, and
   it counts on from the round it reached. See [Picking a run up](/user/resuming).
2. **A failed turn is a round answered with nothing.** `HarnessError` is what a turn raises
   when the CLI could not take it: it died mid-turn, the provider throttled it, the connection
   broke. Catching it keeps one bad turn from ending a run meant to go on for hours.
3. **Three empty rounds in a row end it.** `run` answers with what the agent said, and an agent
   with nothing left to say, or a CLI failing every time, is a loop with nothing more to do.
4. **Otherwise, the budget ends it.** Every run is given [a budget](/features/allowances). The
   turn that finds it spent raises `BudgetExceeded`, which is not a `HarnessError`, so it goes
   straight past the `except` and ends the run.

::: warning Catch `HarnessError`, not `Exception`
`except HarnessError` lets a spent budget and a stop go through. `except Exception` does not:
once the run's `cost` is spent, every turn raises `BudgetExceeded` again, and a loop that
catches it spins on without end.
:::

## Give it a finish line

A loop can end on a check of your own. Keep the task in a file with boxes to tick, and stop
when they are ticked and the tests pass:

```sh
cat > TASK.md <<'EOF'
Make `calc.py` a real calculator:

- [ ] add, subtract, multiply, divide
- [ ] divide by zero raises ValueError
- [ ] a test file `test_calc.py` covering all four
- [ ] `python -m pytest -q` passes

Tick each box in this file as you finish it.
EOF
```

A workspace whose type carries `ShellEnvMixin` may run programs, and one with `FilesEnvMixin`
may read and write files:

```python
from hmz.flows import FilesEnvMixin, LocalEnv, ShellEnvMixin


class Workspace(LocalEnv, ShellEnvMixin, FilesEnvMixin):
    """The directory the run was started in."""


class Envs(EnvCollection):
    workspace: Workspace


async def finished(workspace: Workspace) -> bool:
    code, _, _ = await workspace.exec(["python", "-m", "pytest", "-q"])
    return code == 0 and b"- [ ]" not in await workspace.read("TASK.md")
```

```python
    while True:
        session = await agent.spawn(env=workspace)
        await agent.run(task, session=session)
        if await finished(workspace):  # [!code ++]
            return  # [!code ++]
```

Run it on `"Work through TASK.md."` and the task file is also how you steer it: add a box while
it runs, and the next round starts from a file that says so.

## Two agents, taking turns

[`flame_chase`](/flows/flame-chase) is the smallest loop over two agents. The heart of it is
whose turn it is, kept in `ctx.state` so a resumed run goes on with the right one:

```python
chasers = (agents["first_chaser"], agents["second_chaser"])
at = (state["turn"] if "turn" in state else 0) % len(chasers)
while True:
    session = await chasers[at].spawn(env=envs["workspace"])
    await chasers[at].run(task, session=session)
    at = (at + 1) % len(chasers)
    state["turn"] = at
```

The official flowverse has the other shapes:

| Flow | Each round |
| --- | --- |
| [`ralph_loop`](/flows/ralph-loop) | a fresh session, the task again |
| [`stateful_ralph`](/flows/stateful-ralph) | the same session, the task again |
| [`continue_loop`](/flows/continue-loop) | the same session, the task once and then `continue` |
| [`flame_chase`](/flows/flame-chase) | two agents in turn, a fresh session each |
| [`goal`](/flows/goal) | no loop of its own: the task becomes the CLI's own [goal](/weaver/goals) |

To start from one of them, fork it into `.humanize/flows/` and change the copy. See
[Flowverses](/weaver/flowverses).

## Running one

A loop runs like any other flow. [Watching it](/user/monitor), [typing into a
turn](/user/steering), [stopping it](/user/stopping) and [picking it up](/user/resuming) are in
the User Guide.

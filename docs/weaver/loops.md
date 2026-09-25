# Loops

A **Ralph loop** keeps one agent working until you stop it, starting fresh from the task and
the repository every turn. Reach for it when you want a task worked through with nothing
carrying over from one turn to the next.

## What a Ralph loop is

```python
while True:
    session = await agent.spawn(env=workspace)
    await agent.run(task, session=session)
```

That is the whole of it. `spawn` opens a **session** — a conversation the agent holds — and
each round opens a new one, so nothing of the last turn carries over.

The opposite is `stateful_ralph`, which holds one session for the whole run:

```python
session = await agent.spawn(env=workspace)
while True:
    await agent.run(task, session=session)
```

The agent is the same; the behaviour is opposite. **The flow decides, not the agent** — the
most important choice a weaver makes. See [Concepts › Session](/user/concepts#session).

The whole flow, as the flowverse keeps it, is not much longer. Its one agent is the role
`agent`, it works in `workspace`, the directory the run was started in, and it [can be picked
up](/user/resuming), so it keeps the round it reached in `ctx.state`:

```python
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


class Agents(AgentCollection):
    agent: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, resumable=True)
async def ralph_loop(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """A fresh session every turn, so nothing carries over."""
    agent, workspace, state = agents["agent"], envs["workspace"], ctx.state
    assert state is not None  # a resumable flow always has one
    while True:
        state["rounds"] = (state["rounds"] if "rounds" in state else 0) + 1
        session = await agent.spawn(env=workspace)
        try:
            await agent.run(task, session=session)
        except HarnessError:
            continue                        # a turn that failed: go round again
```

There is no way out of the `while True`, and that is deliberate: the run's
[budget](/features/budgets) is what stops it. A turn taken once it is spent raises
`BudgetExceeded`, which is not a `HarnessError`, so the `except` above lets it through and the
loop ends there.

## Write a task the loop can finish

A Ralph loop wants a task with a finish line it can check for itself.

```sh
cat > TASK.md <<'EOF'
# Task

Make `calc.py` a real calculator:

- [ ] add, subtract, multiply, divide
- [ ] divide by zero raises ValueError
- [ ] a test file `test_calc.py` covering all four
- [ ] `python -m pytest -q` passes

Tick each box in this file as you finish it. Stop when all four are ticked.
EOF
git add -A && git commit -qm "the task"
```

## Choose the flow

In `hmz`:

```
/flow
```

The flows appear one place at a time, one list each. **←** and **→** step between the places,
**s** narrows by name, and enter takes `ralph_loop`. Or say it outright:

```
/flow ralph_loop
```

Opening it asks what its one role, `agent`, runs — a CLI, a model, an effort — and what the
run may spend. `workspace` is not asked about: it is this directory.

There are **no flows to choose from while a flow is running**: `/flow` opens inside the agents
of the one that is going, and `/flow ralph_loop` is refused outright. Looking and leaving
without choosing changes nothing.

::: details What these three flows are
| Flow | Roles | |
| --- | --- | --- |
| `chat` | `assistant`, and you as `human` | one session; every line you type is a turn of it. What the interface opens on. |
| `ralph_loop` | `agent` | a fresh session every turn |
| `stateful_ralph` | `agent` | one session, re-sent the task every turn |

Both loops say they [can be picked up](/user/resuming). They keep which round they are on, so
carrying one on in this directory says round 41 rather than round 1.
:::

From a command line it is the same three answers, as flags:

```sh
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b duration=6h,cost=50 \
    "Work through TASK.md."
```

## Start the loop

Say what you want done:

```
Work through TASK.md.
```

It keeps going until you stop it, or until what you let it spend is spent.

## Watch the run

```
/monitor
```

It shows three things: who is working, every handover between agents with how often it
happened, and what each model has cost. On a one-agent flow the graph is dull. On
[two agents taking turns](/user/tutorials/take-home) it is the shape of the run.

Above the editor, continuously, is the agent with a turn open, by the role the flow gave it,
and what its model has cost over a recent window — so a flow that has stopped reads as
stopped. **tab** steps between the agents that are working, which matters on a flow that
drives several. See [Cost and rate](/user/tally).

## Steer the loop without restarting

A Ralph loop re-reads the repository every turn, so **the fastest way to steer it is to edit
the task file**. In another terminal:

```sh
echo '- [ ] and a --help flag' >> TASK.md
```

The next turn starts from a file that says so. Nothing had to be told.

You can also type at it; that goes into the turn that is running. See [Talking to a running
turn](/user/steering).

## Stop the loop

**ctrl+c**, twice.

The loop never ends by itself; it is a `while True`. A stop cancels the flow where it is
waiting — the turn under way is interrupted, and the `CancelledError` goes up through the
flow's own code. `except HarnessError` deliberately does not catch it, and neither should any
`except` you write around a turn: a loop that carried on past a stop would never end. See
[Stopping](/user/stopping).

It also stops without you. Every run has a [budget](/features/budgets) — `-b` on a command
line, the budget row of `/flow` at the prompt — and `hmz exec` refuses to start a flow without
one. A flow says nothing about it: the loop above has no default of its own, and what it may
spend is whoever runs it to say.

Stopping is not losing your place. `ralph_loop` [can be picked up](/user/resuming): `hmz exec
--resume` with the same flow, or `/resume` at the prompt, goes on from the round it reached.
`/epics` is where every run of it is.

## Other shapes

The two loops above are the two ends of one question — what the next turn remembers — and the
flowverse keeps the shapes between them:

| Flow | Each round | |
| --- | --- | --- |
| [`ralph_loop`](/flows/ralph-loop) | a fresh session | nothing carries over but the repository |
| [`stateful_ralph`](/flows/stateful-ralph) | the same session, the task again | everything carries over |
| [`continue_loop`](/flows/continue-loop) | the same session, `continue` | the task is sent once, and nudged after |
| [`flame_chase`](/flows/flame-chase) | two agents, `first_chaser` and `second_chaser`, in turn | each reads what the other left |
| [`goal`](/flows/goal) | the task as the agent's own [goal](/weaver/goals) | the model says when it is done |

`flame_chase` is the smallest loop over two agents, and the whole of it is whose turn it is:

```python
chasers = [agents["first_chaser"], agents["second_chaser"]]
at = state["turn"] if "turn" in state else 0
while True:
    session = await chasers[at].spawn(env=workspace)
    await chasers[at].run(task, session=session)
    at = (at + 1) % 2
    state["turn"] = at                 # two turns in a row is the one thing it must not do
```

## Try this

**Hold the conversation instead of dropping it.** `/flow stateful_ralph`, same task. Compare
how often it re-reads files it has already read.

**Move the effort.** Open the flow in `/flow`, choose the agent, find the `effort` row,
and press **←/→** or **space**. A Ralph loop of `low` turns is a different animal from one of
`max` turns. See [Efforts](/user/efforts).

**Make it read-only.** What an agent is allowed to touch is the flow's to say, declared on the
role — so this one is a fork rather than something you type. Press **f** on `ralph_loop` in
`/flow`, which copies the whole flow into `.humanize/flows/ralph_loop/`, and give its one role a
type of its own:

```python
# .humanize/flows/ralph_loop/__init__.py
from hmz.flows import Permission, PermissionKind


class Reader(Agent):
    _permission = Permission(local=PermissionKind.READ)


class Agents(AgentCollection):
    agent: Reader
```

`local/ralph_loop` now looks at the repository and changes nothing, whichever CLI fills the
role, which is how you use a loop to *review* rather than to build. See
[Permissions](/user/permissions).

## See also

- [Concepts › Session](/user/concepts#session)
- [Stopping](/user/stopping)
- [Cost and rate](/user/tally)
- [Efforts](/user/efforts)
- [Beat a benchmark](/user/tutorials/take-home)

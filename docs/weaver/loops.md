# Loops

In this guide you write `checklist`: a loop that hands an agent the same task round after
round, each round in a fresh conversation, until a check of your own says the work is done.
Along the way it survives a failed turn, keeps count across a stop, and gives up after a fixed
number of rounds.

Reach for a loop when one turn is not enough and you can say, in code, what "done" looks like:
a test suite that passes, a checklist that is ticked, a file that exists.

::: info Before you start
- A flow of your own running: [Your first flow](/weaver/writing-a-flow).
- A git repository with `calc.py` in it, as that page makes, and `python -m pytest` working on
  your machine.
:::

## How a loop works

A loop is an ordinary Python `while` or `for` around `spawn` and `run`. Writing one comes down
to three choices.

**What the next turn remembers.** Where `spawn` sits decides it. Inside the loop, every round
is a new session, a new conversation, so the agent works from the task and the repository
alone. This is a **Ralph loop**. Before the loop, every round is one more turn of the same
conversation:

```python
session = await agent.spawn()  # [!code ++]
while True:
    session = await agent.spawn()  # [!code --]
    await agent.run(task, session=session, env=workspace)
```

| | `spawn` inside the loop | `spawn` before it |
| --- | --- | --- |
| The official flow | [`ralph_loop`](/flows/ralph-loop) | [`stateful_ralph`](/flows/stateful-ralph) |
| Each turn starts from | the task and the repository | everything said and done so far |
| Reach for it when | earlier attempts would mislead the next one | each round builds on what the last one learned |

**What ends it.** Four things can, and a good loop has more than one:

| Ends the loop | How |
| --- | --- |
| a check of yours | `return` when your code says the work is done |
| a round limit | `for` over a `range`, or a counter |
| a stall | the agent answering with nothing, round after round |
| the run's budget | always there: the turn that finds it spent raises `BudgetExceeded` |

**What a failed turn does.** `run` raises `HarnessError` when the CLI could not take the turn:
it died mid-turn, the provider throttled it, the connection broke. Uncaught, that ends the run.
A loop meant to go on for hours catches it and carries on.

A fourth choice matters once a loop runs long: whether a stopped run can be **picked up**.
`@flow(…, resumable=True)` hands the flow `ctx.state`, a dictionary saved as it is written, so
a resumed run counts on from where it stopped.

## Example: a loop with a finish line

`checklist` keeps the task in a file with boxes to tick, and stops once every box is ticked and
the tests pass. Put the task in the repository:

```sh
cat > TASK.md <<'EOF'
Make `calc.py` a small calculator:

- [ ] add `subtract`, `multiply` and `divide` beside `add`
- [ ] `divide` raises `ValueError` when the divisor is zero
- [ ] `test_calc.py` covers all four
- [ ] `python -m pytest -q` passes

Tick each box in this file as you finish it.
EOF
mkdir -p .hmz/flows/checklist
```

```python
# .hmz/flows/checklist/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FilesEnvMixin,
    FlowContext,
    FlowParams,
    HarnessError,
    LocalEnv,
    ShellEnvMixin,
    flow,
)

ROUNDS = 6  # ①


class Agents(AgentCollection):
    agent: Agent


class Workspace(LocalEnv, ShellEnvMixin, FilesEnvMixin):  # ②
    """The directory the run was started in."""


class Envs(EnvCollection):
    workspace: Workspace


async def finished(workspace: Workspace) -> bool:  # ③
    """Whether every box in TASK.md is ticked and the tests pass."""
    if b"- [ ]" in await workspace.read("TASK.md"):
        return False
    code, _, _ = await workspace.exec(["python", "-m", "pytest", "-q"])
    return code == 0


@flow(agents=Agents, envs=Envs, params=FlowParams, resumable=True)  # ④
async def checklist(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> bool:
    """Work through a checklist, a fresh session a round, until every box is ticked."""
    agent, workspace = agents["agent"], envs["workspace"]
    state = ctx.state  # ⑤
    assert state is not None
    rounds = state["rounds"] if "rounds" in state else 0
    while rounds < ROUNDS:
        rounds += 1
        state["rounds"] = rounds  # ⑥
        print(f"round {rounds}")
        session = await agent.spawn()  # ⑦
        try:
            await agent.run(task, session=session, env=workspace)
        except HarnessError as error:  # ⑧
            print(f"round {rounds} failed: {error}")
            continue
        if await finished(workspace):  # ⑨
            print(f"done in {rounds} rounds")
            return True
    print(f"gave up after {ROUNDS} rounds")
    return False  # ⑩
```

### What each part does

1. **`ROUNDS`** caps the loop. The budget would end it anyway, but a cap ends a loop that is
   going nowhere before it has spent the budget. To let whoever runs the flow set it, make it a
   [param](/weaver/flow-settings).
2. **`Workspace(LocalEnv, ShellEnvMixin, FilesEnvMixin)`** is still the directory the run was
   started in, now granted two things the flow itself will do there: run programs
   (`ShellEnvMixin` gives it `exec`) and read files (`FilesEnvMixin` gives it `read` and
   `write`). Without a mixin, the method raises `CapabilityNotGranted`.
3. **`finished`** is the finish line, as a plain function. `read` returns the file's bytes, so
   the test is on `b"- [ ]"`. `exec` runs one program, with no shell between, and returns its
   exit status, stdout and stderr. Checking the file before the tests saves running them while
   boxes are still open.
4. **`resumable=True`** is what makes `ctx.state` exist. Without it, `ctx.state` is `None`.
5. **`ctx.state`** is a dictionary that outlives the run. A new run starts it empty; a run
   picked up with `hmz exec --resume` or `/resume` finds what was written before it stopped.
   The `assert` tells a type checker it is not `None` here.
6. **`state["rounds"] = rounds`** saves the count as soon as it moves. A picked-up run starts
   its count from here, so `ROUNDS` caps the whole job and not each run of it. A value must be
   JSON-serializable, or the write raises `StateNotSerializable`.
7. **`spawn` inside the loop** makes this a Ralph loop: every round is a stranger to the last,
   and learns what was done from `TASK.md` and the code. Move it above the `while` to keep one
   conversation.
8. **`except HarnessError`** turns a failed turn into a wasted round rather than the end of the
   run. A spent budget raises `BudgetExceeded`, which is not a `HarnessError`, so it goes past
   this and ends the run, as it should.
9. **`if await finished(...)`** runs your check after every turn. The agent saying "done" is
   not the check: the file and the exit status are.
10. **The return value** is what a [calling flow](/weaver/calling-flows) gets back, and what
    a test's `run_fake` returns: `True` if the list was finished.

## Run it

The task points at the file, so the file is also how you steer the loop: add a box while it
runs, and the next round starts from a file that says so.

::: code-group

```text [At the prompt]
$@local/checklist Work through TASK.md.
```

```sh [Claude Code]
hmz exec -f checklist -a agent=claude/claude-sonnet-5-5:high -p budget.cost=1 "Work through TASK.md."
```

:::

A real run, abridged:

```text
● agent is working
● Read(/home/you/calc/TASK.md)
● Bash(cd /home/you/calc && ls -la && git ls-files)
● Read(/home/you/calc/calc.py)
● Write(/home/you/calc/calc.py)
● Write(/home/you/calc/test_calc.py)
● Bash(cd /home/you/calc && python -m pytest -q 2>&1 | tail -15)
● Write(/home/you/calc/TASK.md)
● All four items in TASK.md are done and ticked.
  …
✻ input 12 · output 1.1k · cache_read 97.8k · cache_write 7.0k · $0.05 · claude-sonnet-5-5 · agent
round 1
All four items in TASK.md are done and ticked.
…
✻ Worked for 11s · agent
done in 1 rounds
```

- **`round 1`** and **`done in 1 rounds`** are the flow's own `print`s. Whatever a flow prints
  lands in the run's output beside what its agents say, though not always on the line you
  might expect: the turn's lines are drawn as they stream in.
- **The agent ran the tests itself and ticked the boxes**, but that is its account. The flow
  then read `TASK.md` and ran `python -m pytest -q` on its own, and only that ended the loop.
- **One round was enough.** Had a box been left open, `round 2` would have followed, with a
  new `● agent is working` in a new session.

## Check it worked

The file is ticked and the suite is green:

```sh
cat TASK.md && python -m pytest -q
```

```text
Make `calc.py` a small calculator:

- [x] add `subtract`, `multiply` and `divide` beside `add`
- [x] `divide` raises `ValueError` when the divisor is zero
- [x] `test_calc.py` covers all four
- [x] `python -m pytest -q` passes

Tick each box in this file as you finish it.
.....                                                                    [100%]
5 passed in 0.00s
```

The loop's logic is where it goes wrong, so test that on fakes, where the agent answers from a
script and the workspace is a dictionary:

```python
# tests/test_checklist.py
from hmz.sdk import fakes

GREEN = {("python", "-m", "pytest", "-q"): (0, "4 passed", "")}  # ①


async def test_it_stops_once_the_boxes_are_ticked() -> None:
    here = fakes.FakeEnvDriver({"TASK.md": "- [ ] divide"}, run=GREEN)  # ②

    async def ticks(prompt: str, **_: object) -> str:  # ③
        await here.write("TASK.md", b"- [x] divide")
        return "ticked"

    agent = fakes.FakeAgentDriver(reply=ticks)
    done = await fakes.run_fake(
        "checklist", "Work through TASK.md.", agents={"agent": agent}, local=here
    )
    assert done is True  # ④
    assert len(agent.sessions) == 1


async def test_it_gives_up_after_six_fresh_rounds() -> None:
    here = fakes.FakeEnvDriver({"TASK.md": "- [ ] divide"}, run=GREEN)
    agent = fakes.FakeAgentDriver()
    done = await fakes.run_fake("checklist", "x", agents={"agent": agent}, local=here)
    assert done is False
    assert len(agent.sessions) == 6  # ⑤
    assert here.commands == []  # ⑥
```

```sh
uvx --with 'hmz @ git+https://github.com/humanfia/humanize.git' \
    --with pytest-asyncio pytest -q -o asyncio_mode=auto
```

```text
..                                                                       [100%]
2 passed in 0.09s
```

1. **`GREEN`** scripts the workspace's `exec`: this argv exits `0` with `4 passed`. Any
   other command exits `127`, bar a few the fake answers itself (`true`, `echo`, `cat`, `ls`
   and the like), so a flow that runs something unexpected says so.
2. **`FakeEnvDriver({...})`** is a working directory held in memory, starting with one open
   box. `local=here` makes it the `LocalEnv` workspace.
3. **A reply function** stands in for the agent's work: it ticks the box, as the real agent
   would edit the file.
4. **`done is True` and one session**: the loop checked, found the work finished, and stopped.
5. **Six sessions** for six rounds proves `spawn` is inside the loop: each round was fresh.
6. **No commands** proves the order in `finished`: with a box still open, pytest never ran.

[Testing a flow](/weaver/testing-flows) shows how to stop a fake run and pick it
up, which tests what `ctx.state` keeps.

## Read a real one: `ralph_loop`

This is `ralph_loop` as humanize ships it, trimmed of its module and class docstrings and its
lint comments. It has no finish line of its own: it runs until the agent has nothing more to
say, or the budget is spent.

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


@flow(agents=Agents, envs=Envs, params=FlowParams, resumable=True)
async def ralph_loop(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """The task again and again, a fresh session every round."""
    state = ctx.state
    assert state is not None
    agent = agents["agent"]
    stalled = 0
    while True:  # ①
        state["rounds"] = rounds = (state["rounds"] if "rounds" in state else 0) + 1  # ②
        print(f"round {rounds}")
        session = await agent.spawn()
        try:
            answered = await agent.run(task, session=session, env=envs["workspace"])
        except HarnessError as error:
            print(f"round {rounds} failed: {error}")
            answered = ""  # ③
        stalled = 0 if answered else stalled + 1  # ④
        if stalled >= STALLED:
            print(f"stopping: {stalled} rounds in a row answered with nothing")
            return
        await asyncio.sleep(PAUSE)  # ⑤
```

1. **`while True`** has no round limit: the budget is the limit. Run it with a budget you
   would be content to spend in full.
2. **The round count** lives in `ctx.state`, as in `checklist`, so `--resume` counts on.
3. **A failed turn is a round answered with nothing**, rather than a skipped one, so a CLI that
   fails every time counts towards the stall.
4. **Three empty rounds in a row end it.** `run` returns what the agent said, and an agent with
   nothing left to say, or a CLI failing every time, is a loop with nothing more to do.
5. **`asyncio.sleep(PAUSE)`** waits five seconds between rounds, which gives a throttled
   provider room and you a moment to steer.

## Variations

**One conversation instead of fresh ones.** Move `spawn` above the loop, as in the diff at the
top. The agent then remembers every round, which helps when a round builds on what the last one
learned, and costs more as the conversation grows.

**Two agents taking turns.** [`flame_chase`](/flows/flame-chase) alternates two agents on the
same task. The heart of it is whose turn it is, kept in `ctx.state` so a resumed run goes on
with the right one. Abridged:

```python
chasers = (agents["first_chaser"], agents["second_chaser"])
at = (state["turn"] if "turn" in state else 0) % len(chasers)
while True:
    session = await chasers[at].spawn()
    await chasers[at].run(task, session=session, env=envs["workspace"])
    at = (at + 1) % len(chasers)
    state["turn"] = at
```

**Start from a built-in loop.** Copy one into your project with **Copy here** in `/flow`, and
change the copy. See [Flowverses](/weaver/flowverses#managing-flowverses).

| Flow | Each round |
| --- | --- |
| [`ralph_loop`](/flows/ralph-loop) | a fresh session, the task again |
| [`stateful_ralph`](/flows/stateful-ralph) | the same session, the task again |
| [`continue_loop`](/flows/continue-loop) | the same session, the task once and then `continue` |
| [`flame_chase`](/flows/flame-chase) | two agents in turn, a fresh session each |
| [`goal`](/flows/goal) | no loop of its own: the task becomes the CLI's own [goal](/weaver/goals) |

## Pitfalls

::: warning Catch `HarnessError`, not `Exception`
`except HarnessError` lets a spent budget and a stop go through. `except Exception` does not:
once the run's `cost` is spent, every turn raises `BudgetExceeded` again, and a loop that
catches it spins on without end.
:::

- **A counter in a local variable restarts at zero** when the run is picked up. Keep whatever
  must survive a stop in `ctx.state`.
- **`ctx.state` is `None`** unless the flow says `resumable=True`.
- **State takes JSON only.** A set, a pydantic model or a session raises `StateNotSerializable`
  when written. Store a list, a dict of plain values, or `model.model_dump()`.
- **Trust your check, not the agent.** An agent can tick a box it did not finish. Put what you
  can in code: the exit status of the suite is harder to talk round than a checkbox.

## Next steps

- [Params of its own](/weaver/flow-settings): make `ROUNDS` a `-p rounds=…`.
- [Build under test](/weaver/tutorials/build-under-test): a loop with a second agent as the
  finish line.
- [Testing a flow](/weaver/testing-flows): scripted agents, workspaces and resuming.
- Running a loop: [watching it](/user/monitor), [typing into a turn](/user/steering),
  [stopping it](/user/stopping) and [picking it up](/user/resuming).
- Reference: [`FlowState`](/reference/flows#flowstate),
  [resumable flows](/reference/flows#a-flow-that-can-be-picked-up),
  [`ShellEnvMixin` and `FilesEnvMixin`](/reference/flows#what-an-environment-can-do),
  [errors](/reference/flows#when-something-goes-wrong).

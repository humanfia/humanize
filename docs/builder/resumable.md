---
title: Resumable flows
description: Write a flow that saves its progress as it runs, so a stopped or killed epic is picked up where it left off.
---

# Resumable flows

A resumable flow saves its progress while it runs. When an epic stops, runs out of budget, or is killed, a new epic picks up from the saved state instead of starting over.

![The first epic saves each state write to its journal and stops after round 2; the epic that resumes it starts from a copy of that journal and goes on at round 3](/diagrams/builder-resumable-1.svg)

## Make a flow resumable

Pass `resumable=True` to `@flow`. Your flow receives `ctx.state`, a mapping saved to disk. Read `ctx.state` at the start to find where to continue, and write to it after each step you do not want to repeat.

This flow runs for four rounds, saving the round count and the conversation after each turn.

```python
# .hmz/flows/in_rounds/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


class Params(FlowParams):
    rounds: int = 4


@flow(agents=Agents, envs=Envs, params=Params, resumable=True)
async def in_rounds(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> int:
    """Work on the task in rounds, picking up at the round it stopped in."""
    coder, workspace = agents["coder"], envs["workspace"]
    state = ctx.state
    assert state is not None  # a resumable flow always has one
    done = state["done"] if "done" in state else 0
    session = state["session"] if "session" in state else await coder.spawn()
    for n in range(done + 1, params.rounds + 1):
        prompt = f"{task}\n\nThis is round {n} of {params.rounds}."
        await coder.run(prompt, session=session, env=workspace)
        state["session"] = session  # the conversation as it stands now
        state["done"] = n  # on disk before this line returns
    return params.rounds
```

Humanize saves only what you write to `ctx.state`. On a first run, `ctx.state` is empty. On a resumed run, it holds what the earlier epic saved, and `ctx.resumed` is `True`.

| Operation | What it does |
| --- | --- |
| `key in state` | Checks whether `key` is saved. |
| `state[key]` | Returns the saved value, or raises `KeyError`. |
| `state[key] = value` | Saves `value` to disk before the line returns. |
| `del state[key]` | Removes `key`, or raises `KeyError`. |

Keys must be strings. Values must be JSON-serializable or sessions; anything else raises `StateNotSerializable` and leaves the state unchanged.

## Resume a run

### In the app

Click **Resume** in the app or run `/resume` in the terminal. These controls appear only when an epic can be resumed. See [Resume a run](/user/resuming).

### From the command line

1. Run the flow. Here, a small budget stops the epic after two rounds:

```sh
hmz exec -f @local/in_rounds -a coder=claude/claude-haiku-4-5 \
    -p budget.output_tokens=160 "Add a discount code to checkout"
```

![hmz exec runs rounds 1 and 2, then stops because the budget's output tokens are spent](/shots/builder-resumable-stopped.svg)

2. Run it again with `--resume`. A new epic starts from the saved state and continues at round 3:

```sh
hmz exec -f @local/in_rounds --resume -a coder=claude/claude-haiku-4-5 \
    -p budget.output_tokens=20000 "Add a discount code to checkout"
```

![hmz exec --resume runs rounds 3 and 4 only](/shots/builder-resumable-resumed.svg)

`--resume` picks up the newest epic of this flow in the current directory that saved progress and is not running. If the flow is not resumable, the command fails with `<flow> does not support resuming, so there is no run to resume`.

## Save a conversation

Write a session to `ctx.state`—alone or inside a list or dict—to save the conversation at that moment. Reading the key back returns a new session that continues the conversation, so the agent remembers earlier turns. Any session not saved in `ctx.state` starts fresh.

In `in_rounds`, `state["session"] = session` saves the coder's conversation. In the resumed epic, the session holds all four rounds: two carried over and two new.

![Humanize Desktop with the resumed epic open on the coder's session: rounds 1 and 2 carried over from the first epic, then rounds 3 and 4](/shots/builder-resumable-thread.svg)

*The resumed epic's one session: 4 turns, two of them from the epic it picked up.*

Writing a session raises `StateNotSerializable` if the session:

- has taken no turn, is in the middle of a turn, or is closed;
- belongs to another flow call, or to an outworlder;
- runs on a harness that cannot fork a conversation, or that stores conversations in a database (`opencode`, `mimo`);
- took its last turn with the harness running on another machine: on a [runtime](/user/runtimes) whose **Harness runs on** is **Inside the environment** or another runtime.

Keep the same harness for the role when you resume. Running the first turn of a saved session on a different harness raises `UnsupportedOperation`.

## Inspect the journal

Humanize writes state changes to `resume.jsonl` in the epic's directory, with one JSON line per flow call and its end, state write or delete, session, and temporary directory.

![The journal of the first epic printed with cat: a call line, a session line, and a set line for each write of session and done](/shots/builder-resumable-journal.svg)

A resumed epic starts with a compacted copy of the journal and appends to it. The original journal is never modified, so you can resume the same epic multiple times. See [Files on disk](/reference/files).

## Resume subflows

The flow at the top always picks up the earlier epic's state, even if you change the task, agents, or params on resume. When a resumed flow [calls another flow](/builder/calling-flows), Humanize matches the call to one from the earlier epic. Two calls match when they have the identical caller, flow, task, agents (same harness, account, model, effort, permission, and skills), environments (derived the same way from the same place), and params. Multiple identical calls are matched in the order they were made. Unmatched calls start with an empty state.

Each flow call has its own state, and a subflow must set `resumable=True` to use it.

Humanize keeps the temporary clones and scratch directories of a resumable epic when it ends. Deriving one with the same id in the resumed epic returns the same directory. See [Worktrees, clones and scratch](/builder/worktrees).

## Resume from Python

Pass `resume=True` to `Hmz().run` to pick up the newest epic, or pass an epic's directory to pick up a specific one. Use `Hmz().epics` to inspect saved state without running the flow.

```python
# carry_on.py
from hmz.sdk import Hmz

hmz = Hmz()
epic = hmz.epics.resumed("@local/in_rounds")
print("picks up:", epic.name)
print("rounds done:", hmz.epics.state(epic)["done"])

run = hmz.run(
    "@local/in_rounds",
    "Add a discount code to checkout",
    agents={"coder": "claude/claude-haiku-4-5"},
    budget={"output_tokens": 20000},
    resume=True,
)
print("returned:", run.run())
```

![The program's output: the name of the epic it picks up, rounds done: 2, returned: 4](/shots/builder-resumable-python.svg)

| Call | Returns |
| --- | --- |
| `hmz.flows.resumes(name)` | Whether the flow is resumable. |
| `hmz.epics.resumed(flow)` | The epic `--resume` would pick up, or `None`. |
| `hmz.epics.picks_up(epic)` | Whether that epic can be picked up. |
| `hmz.epics.state(epic)` | The state the epic's flow kept, as a dict. |

See [The Python SDK](/builder/sdk).

## Test a resumable flow

Pass a `journal` path and `resume` to `run_fake`. Run the flow once so it fails partway through, then run it again with `resume=True` on the same journal.

```python
# test_in_rounds.py
from pathlib import Path

import pytest

from hmz.sdk import fakes


async def test_in_rounds_picks_up_at_round_three(tmp_path: Path) -> None:
    asked: list[str] = []

    def coder(prompt: str, **_: object) -> str:
        asked.append(prompt.splitlines()[-1])
        if len(asked) == 3:
            raise RuntimeError("killed")  # the first run dies in round 3
        return "ok"

    async def run(*, resume: bool) -> int:
        return await fakes.run_fake(
            "./.hmz/flows/in_rounds",
            "add a coupon",
            agents={"coder": coder},
            journal=tmp_path / "resume.jsonl",
            resume=resume,
        )

    with pytest.raises(RuntimeError):
        await run(resume=False)
    assert await run(resume=True) == 4
    assert asked[3:] == ["This is round 3 of 4.", "This is round 4 of 4."]
```

An `async def` test needs pytest-asyncio. See [Test a flow](/builder/testing).

## Good to know

- A resumed epic is a new epic with its own name, budget, and sessions. Spend from the earlier epic does not carry over.
- State writes are on disk when the line returns. Write after a step completes, not before, so a crash in between does not skip the step.
- Reading a key returns a copy. Mutating a list or dict in place does not update the state; assign it back to the key.
- Values round-trip through JSON on both first and resumed runs: tuples become lists, and dict keys become strings.
- Each session write copies the conversation into the epic. In a long loop, write the session only when needed.
- Finished epics can also be resumed. If a completed flow should start over instead, delete its keys before returning.
- In a non-resumable flow, `ctx.state` is `None`.
- If the top-level flow is not resumable, any resumable subflow it calls keeps its state in memory for that epic only.
- A resumed epic runs the current flow code on disk. Keep old state keys compatible when you edit a flow.

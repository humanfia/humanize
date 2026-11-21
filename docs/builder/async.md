---
title: Concurrent turns
description: Take several agent turns at the same time in one flow, cap how many run at once, handle one failing, and read a concurrent run in the monitor.
---

# Concurrent turns

A flow is an `async def` function, so you run several turns at once with standard `asyncio`. Give each concurrent turn its own session.

![Three sessions take a turn at the same time. gather returns when the last one ends, and a fourth session then sums up.](/diagrams/builder-async-1.svg)

## Take several turns at once

Open a session per turn with `spawn()` and pass the coroutines to `asyncio.gather`. This flow has one reviewer read three files at the same time, then sum up the reviews in a fourth turn.

```python
# .hmz/flows/review_parts/__init__.py
import asyncio

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)

PARTS = ("catalogue", "cart", "checkout")


class Agents(AgentCollection):
    reviewer: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def review_parts(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """One reviewer reads three files at once, then sums up."""
    reviewer, workspace = agents["reviewer"], envs["workspace"]

    async def review(part: str) -> str:
        session = await reviewer.spawn()  # one session per concurrent turn
        return await reviewer.run(
            f"{task}\n\nLook only at shop/{part}.py.", session=session, env=workspace
        )

    notes = await asyncio.gather(*(review(part) for part in PARTS))
    return await reviewer.run(
        "Sum up these reviews:\n\n" + "\n\n".join(notes),
        session=await reviewer.spawn(),
        env=workspace,
    )
```

`asyncio.gather` starts the three turns together and returns their answers in the order of `PARTS`, whichever turn finishes first.

One session takes one turn at a time; calling `run` on a busy session raises `SessionError`. Different sessions of the same agent can run at the same time, so call `spawn()` for each concurrent turn.

Sharing a folder works here because the turns only read files. When concurrent turns write files, give each its own git worktree: see [Worktrees, clones and scratch](/builder/worktrees).

## Choose how to wait

Use standard `asyncio` primitives to control how turns run and finish.

| Tool | What it does with turns |
| --- | --- |
| `asyncio.gather` | Waits for every turn. Answers come back in the order given. |
| `asyncio.TaskGroup` | Waits for every turn. When one fails, cancels the others. |
| `asyncio.wait` | Returns when the first turn ends, or when all have. |
| `asyncio.timeout` | Cancels the turns inside it after a time. |
| `asyncio.Semaphore` | Lets only so many turns run at once. |

Cancelling a task that awaits a turn interrupts that turn's agent and raises `asyncio.CancelledError` from `run`.

## Limit how many run at once

Wrap your turn in an `asyncio.Semaphore` to cap concurrency. Humanize sets no cap of its own.

```python
    gate = asyncio.Semaphore(2)

    async def review(part: str) -> str:
        async with gate:  # at most two turns at a time
            return await reviewer.run(
                f"{task}\n\nLook only at shop/{part}.py.",
                session=await reviewer.spawn(),
                env=workspace,
            )

    notes = await asyncio.gather(*(review(part) for part in PARTS))
```

A cap helps avoid rate-limit and lock errors. Running too many turns at once can raise `HarnessThrottled` when the provider refuses excess requests, or `HarnessContended` when two turns hit the same local CLI store at once.

All concurrent turns draw from the flow's budget. Pass `budget=` to `run` to cap a single turn: see [Budgets in a flow](/builder/budgets).

## Handle a turn that fails

Use `asyncio.TaskGroup` to cancel sibling turns when one fails. In `asyncio.gather`, the first error raises in the flow while the remaining turns keep running. With `asyncio.TaskGroup`, the first error cancels the other turns and reaches `except*` with its original class:

```python
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(review(part)) for part in PARTS]
    except* HarnessError as failed:
        print(f"{len(failed.exceptions)} review failed; the others were cancelled")
    else:
        notes = [one.result() for one in tasks]
```

Import `HarnessError` from `hmz.flows`. Calls to subflows work the same way: their exceptions arrive in `except*` with their own class.

## Keep the first answer

Wait with `FIRST_COMPLETED` and cancel the pending tasks to keep the first answer and stop the rest.

```python
    tasks = [asyncio.create_task(review(part)) for part in PARTS]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()  # interrupts that turn's agent
    await asyncio.gather(*pending, return_exceptions=True)
    first = done.pop().result()
```

Wrap a turn in `asyncio.timeout` and catch `TimeoutError` to give up after a set time.

## Watch concurrent turns run

### In the app

Start the flow from **New epic**. The agent's node in the graph draws one bar per session under **every session**, and the sidebar lists each session under the agent. The **Epic** pane shows each session's environment.

![The epic page in Humanize Desktop: one agent node with three session bars running at once](/shots/builder-async-app.svg)

### In the terminal

Run the flow in `hmz`. The transcript announces each turn as it starts: `conversation 2 of 3`. Press <kbd>left</kbd> to open the monitor, then <kbd>space</kbd> on the agent's node to list its sessions.

![The terminal interface: three turns start, the monitor shows one agent working, and space lists its three sessions](/shots/builder-async-monitor.svg)

### From the command line

Run the flow with `hmz exec`. Output lines from concurrent turns interleave as they arrive, and the status line shows `3 turns working`.

```sh
hmz exec -f @local/review_parts -a reviewer=claude/claude-haiku-4-5 \
    -p budget.output_tokens=20000 "Review the shop for bugs"
```

![hmz exec runs the flow: three conversations start together, each reads its file, and a fourth sums up](/shots/builder-async-exec.svg)

## Test that turns overlap

Check `peak` on `FakeAgentDriver` to verify the maximum number of sessions open at once. Add a short sleep to the fake reply so the turns overlap.

```python
import asyncio

from hmz.sdk import fakes


def test_three_reviews_run_at_once() -> None:
    async def reply(prompt: str, **_: object) -> str:
        await asyncio.sleep(0.01)  # long enough for the turns to overlap
        return "fine"

    reviewer = fakes.FakeAgentDriver(reply=reply)
    asyncio.run(fakes.run_fake("review_parts", "Review", agents={"reviewer": reviewer}))
    assert reviewer.peak == 3
```

See [Test a flow](/builder/testing) for more on fakes.

## Good to know

- `spawn()` does not start a process. Each agent's CLI starts on its session's first turn, so three concurrent first turns start three CLI processes.
- Stopping an epic cancels the flow at its current `await`, which interrupts every turn under way, and closes every session: see [Context, errors and cleanup](/builder/context).
- Calls to other flows run concurrently the same way: see [Call another flow](/builder/calling-flows).
- To run concurrent turns from a shared conversation history, fork the session first: see [Branch a conversation](/builder/branching).
- When the flow's time limit passes, the turns under way finish first unless the budget is not graceful, then the flow is cancelled at its `await` and its caller gets `DurationExceeded`. A turn or called flow that runs out of its own time raises `DurationExceeded` in your flow. It is a subclass of `TimeoutError`, so catch it before `TimeoutError` if you also use `asyncio.timeout`.

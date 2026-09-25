# Stopping

A flow ends when its function returns. Most interesting flows never return, and a Ralph loop is
a `while True`, so you end them from outside — or its budget does. You reach for stopping when a flow is running and
you want it to end now.

## Try it

Press **ctrl+c** twice in the interface while a flow is running. Twice, because a day's work is
behind a key that is also pressed by mistake: the first press says `press ctrl+c again to stop
the flow`, and the second one does it.

Or type **`/stop`** and send it, which is the same stop asked once.

## The three ways to stop

| | |
| --- | --- |
| **ctrl+c** twice, in the interface | Stops the flow — the whole flow, not just the turn. Clears what is half-typed first, if anything is. |
| **`/stop`**, at the prompt | The same, asked once. |
| **ctrl+c**, on a `hmz exec` command line | The same. |

**`/stop` is not asked twice.** The key is, because a finger lands on it by mistake; nothing is
typed by mistake, so writing the command out and sending it is the deliberation the second
press stands in for. It says so where there is nothing to stop, which the key never does —
with nothing running the key is the one that leaves, and what it says is about leaving.

It also leaves no half-made gesture behind it. A ctrl+c pressed before a `/stop` and one
pressed after it are not two presses of one gesture: the command came between them, so the
press after it starts again from the beginning — the third press below while the flow is still
unwinding, and otherwise the first of a fresh one.

**A third press does not wait for it.** A flow told to stop unwinds in its own time — a loop
sleeps off its round, a server is given its seconds — and the press after the one that stopped
it closes every conversation still open under whatever turn it is in. That is the backend's
process going, and nothing is left reading as a run in progress. It is the last thing a key can do about a
run.

**esc does not stop anything.** It is pressed to dismiss whatever is on the screen everywhere
else in the interface, so it is not the key that ends a day's work: it opens
[`/monitor`](/reference/tui#watching-the-run) instead. With nothing running at all, two
presses of **ctrl+c** leave the interface.

## What a stop does to the turn under way

The turn is **cut off** — the CLI is interrupted and stops spending — and the flow is
cancelled where it is waiting: every flow call of the run, however deep, unwinds from the `await`
it was at, and one that tries anything more raises `FlowCancelled`.

A stop leaves the turn where it got to. It does not wait for the turn, because a stop that
waited would not read as a stop. A model can think for minutes, and a key that took four of
them to have an effect is a key nobody trusts.

A file the agent had half-written stays half-written. What ends is the agent's part in it,
which includes the CLI process the turn was running in and whatever that process had started:
a stop that left the agent still writing would not be a stop.

To end one turn without ending the run, a flow gives that turn a
[budget](/features/budgets) of its own — `await agent.run(prompt, session=…,
budget=Budget(duration=timedelta(minutes=10), graceful=False))` — or cancels the task awaiting
it, which interrupts the CLI.

To have a run stop itself rather than wait for a key, it has a [budget](/features/allowances):
a duration, a cost, a count of output tokens — `-b`, which every run but `chat` must have. A run
that reaches the end of it raises the `BudgetExceeded` leaf for what ran out — turns left where
they got to, state kept, and the run worth picking up.

## After a stop

A stop is what makes a run worth picking up. Where the flow says it [can be picked
up](/user/resuming), **`/resume`** at the prompt — or the same `hmz exec` line with
`--resume` — carries the run on from where it stopped: its own flow, its own agents, its own
task, and whatever it had written down by the time the key was pressed. Nothing carries on by itself: stopped means stopped, and the run that
carries on is a run somebody asked for.

Wait for it to go, though. A flow told to stop unwinds in its own time and writes down where it
got to as it goes, so `/resume` in that window is refused with `no picking a run up while the
flow is still stopping` — picked up from a journal still being written, the next run would
do a round the stopped one had already recorded. A flow that will not unwind at all is what the
third press is for: it leaves nothing reading as a run in progress, and `/resume` is answerable
again. A second `/stop` in that window is no help either — it says the flow is already stopping
rather than telling it again.

## What stopping is not

**Not `/clear`.** That clears the screen and nothing else. It clears the conversation being
read, not the others, and nothing that is running.

**Not choosing another flow.** `/flow` is refused while one is running, with `no choosing a
flow while a flow is running: ctrl+c twice stops it first`. A run holds the agents and
environments it was started on until it ends. Stop it first, then choose. Looking at
`/flow` and leaving without choosing changes nothing.

**Not a question ending.** A question still up when the flow ends or is stopped ends with it.
Stopping is never blocked on one.

## Why catching a failed turn does not catch a stop

The other side of that key press is the loop a [weaver wrote](/weaver/writing-a-flow), which has
to let it out. A failed turn raises a `HarnessError`, and a loop that goes round again catches
that:

```python
while True:
    session = await agent.spawn(env=workspace)
    try:
        await agent.run(task, session=session)   # ← a stop comes out of here, and the flow unwinds
    except HarnessError:
        continue                                # a turn that failed; the loop goes round again
```

A stop is a cancellation — `asyncio.CancelledError`, which is not an `Exception` at all — so
nothing that catches a failed turn catches it by accident, and neither does a bare
`except Exception`. A spent budget is `BudgetExceeded`, which is not a `HarnessError` either.
Let both propagate. The [epic](/user/tracing#what-a-run-writes-down) then records the run as
**stopped by hand** rather than as one that finished — the difference between "it decided it was
done" and "somebody stopped it", and the only place that distinction is written down.

There is one `HarnessError` a loop should think twice about catching, for the same reason.
`HarnessUnrecoverable` is a turn that failed for a reason no other try could come out
differently on — a conversation longer than the model's context window, a session id the backend
will not answer under. A `while True` that swallowed one would go round on the same failure until
the budget ran out.

A hook runs as the flow the agent belongs to, and what it raises fails the turn it arrived in —
so a hook that catches nothing lets a stop out as the flow's own code does.

## See also

- [Picking a run up](/user/resuming) — carrying on from where a stop left it
- [Talking to a running turn](/user/steering) — when a steer is enough
- [Being away](/user/afk)
- [Flows › Stopping](/reference/flows#stopping)

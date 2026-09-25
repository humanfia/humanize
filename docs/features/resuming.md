---
pageClass: hmz-feature
---

# Picked up where it stopped

A loop meant to run for a week is a loop that will be stopped: somebody presses escape, a
machine goes down, a turn takes the process with it. A flow that says it can be picked up —
`@flow(..., resumable=True)` — keeps a journal as it goes, and running it again with
`--resume` carries it on from where it stood.

<HmzResume />

## What a flow keeps is its own handful of things

A resumable flow's `ctx.state` is a mapping of JSON values: which round it is on, which files it
has been through, what it has decided so far. Deliberately not a second copy of the transcript,
which the backends already keep and whose sessions the journal already names. A flow that is not
resumable has no state at all — `ctx.state` is `None` — so what survives a stop is always
something a flow said it wanted to survive.

```python
state = ctx.state
assert state is not None  # a resumable flow always has one
state["round"] = (state["round"] if "round" in state else 0) + 1
```

A picked-up run starts the flow's function again from the top, with the state it last wrote.
The flow decides what progress means and where to continue, and it runs the current version of
its code: saved state is an input to today's function, not a frozen copy of yesterday's.

## Saved as it is written, not when the run ends

Setting a key writes it to the journal there and then. That is the whole design decision, and it
follows from what resuming is for: **a run worth picking up is one that was stopped or killed**,
and state saved only at the end is state such a run has none of.

What is kept is a copy, as JSON would give it back — a tuple comes back a list — so a fresh run
and a resumed one read the same thing. Changing a list after it was written changes nothing
kept: write it again. A value JSON has no shape for is refused where it is written, with
`StateNotSerializable`, rather than turned into something else the flow will not recognise when
it reads it back.

## One journal per run, one entry per call

The journal is a file of JSON lines, appended to while the run goes: every flow call, what it
was called with, the state it wrote, the sessions it opened, the temporary directories it made,
and how it ended. A run of ten thousand calls is not ten thousand writes — only a state write is
flushed as it is made; the rest is batched within a tenth of a second.

A [flow that calls another](/features/flows) is two calls, each keeping its own state and
neither writing the other's. When the run is picked up, the flow at the top resumes
unconditionally, and **a called flow resumes where it is called again with exactly the same
task, agents, environments and params** — the same flow, asked the same thing of the same
agents; the fifth identical call picks up the fifth. A call that differs starts afresh, since
what it kept was an answer to another question. A flow that is not resumable passes resumption
through to the flows it calls.

## Picking one up

`hmz exec --resume` picks up **the newest resumable run of that flow in this workspace**, on the
agents, environments and params this command line names. Without `--resume`, every run starts
fresh — running a flow again is not, by itself, carrying one on.

Temporary copies and scratch directories a resumable run made are kept rather than removed when
it stops, so the run that picks it up finds them where they were. A run that is not resumable
removes its own as each flow that made them ends.

## What does not come back

The conversation. A resumed flow spawns sessions rather than reconstructing them. A stateful
loop stopped on its fortieth round says round 41 when it starts again — and remembers nothing
else about the forty unless the flow wrote it down.

Which is the argument for keeping little: the repository is the memory, and the handful of
things the flow tracks is what has to survive.

## Where the detail is

- [Picking a run up](/user/resuming) — running it again, and where the journal lives
- [Flows › A flow that can be picked up](/reference/flows#a-flow-that-can-be-picked-up) — the
  contract in full
- [Tracing](/user/tracing) — what else a run writes down
- [Stopping](/user/stopping) — what escape does to a turn

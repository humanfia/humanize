---
pageClass: hmz-feature
---

# Many turns at once

Turns are sequential inside **one conversation** and nowhere else. So a flow that needs two
hundred files fixed at the same time opens two hundred conversations, and one agent holds all
of them.

<HmzTurns />

## Two turns at once means two sessions

Two turns run on one session go one after the other: a second `run` on a session whose turn is
still going is refused with `SessionError` rather than queued behind it. A conversation is a
conversation, and nothing about awaiting one changes that — which is the rule the switch above is
there to make concrete.

```python
async def fix(path: str) -> str:
    session = await agent.spawn(env=workspace)
    return await agent.run(f"Fix the tests in {path}", session=session)

said = await asyncio.gather(*(fix(path) for path in paths))
```

## A conversation is rooted at a directory

Where a session works is the environment it is spawned in, because that is what it is to these
backends: a conversation is opened at a directory and every turn of it runs there. It cannot be
moved once the session is open — a [fork](/weaver/branching) into another environment is another
session.

Which is exactly what makes one agent working in several places at once a **session apiece** — a
worktree per task, a copy per shard, a subdirectory per package — with their turns going
together. And either way it is one agent: one role, one CLI and model, holding several
conversations.

## A session costs nothing until a turn lands in one

Ten thousand conversations opened up front are a list, not a bill.

## How many of them go at once is the CLI's answer, not this library's

Nothing here caps a fan-out. What does is the coding agent underneath it, and the shape it comes
in: one held open for the life of a session pays for starting once, and one run again for every
turn pays for starting on every turn. So the number of conversations that still go at speed on a
given machine is a fact about the backend rather than about this library, and it is measured
rather than guessed: the concurrency benchmark reports, per backend, how many conversations
still run at **half the speed each of them runs alone** — every turn still doing its own real
work, with its own files changed, its own command executed and its own thread of the
conversation recalled.

That benchmark is not carried in this repository. Its harness and the per-turn evidence it
retains change on every run and outweigh the source they measure, so **they stay on disk where
they are run**, and what is written down here is what they established rather than the readings
themselves.

What they establish is a width per backend, and **not a global maximum**. Those are four CPUs
against a **loopback model that answers instantly**, so what they measure is the CLI's own
overhead rather than how many conversations a real provider will keep fed; the real-provider
record is separate, and blocked in places by access rather than by concurrency. The width moves
with how those four cores are fenced — a quota shared with a neighbour and four cores held
exclusively are different questions, and so is a container asked for four of them — so a figure
means nothing apart from the conditions it was taken under, which is why the record keeps the
two together.

One of those ceilings is not about speed at all. **opencode keeps every conversation of every
workspace in one database**, and several of its processes opening one at the same moment can
collide on it and fail before the model is ever asked. humanize leaves that database where the
CLI put it — a conversation belongs to the CLI you can open it in, not to humanize — so that
ceiling is opencode's own, and the way past it is opencode's own `OPENCODE_DB`.

## Every flow is a coroutine

A flow is an `async def`, and every turn is awaited. The turn itself runs on a thread of its own
and the loop is handed straight back — so a flow can hold as many turns as it likes without any
one of them stopping the rest, and a flow that awaits one turn at a time is a flow that runs one
turn at a time, which is what most of them want.

`asyncio.gather` and `asyncio.TaskGroup` are the whole of the vocabulary. A task group that loses
one branch cancels the rest — cancelling a turn cuts it off, so the CLI stops spending — and a
flow may catch what the branches raised with `except*`, since every leaf of a failure is raised
as the class it is.

## Whole flows go at once too

`load` gives you a flow to call, and calling it is awaiting it — so a flow gathers whole flows
exactly as it gathers turns, as deep as it likes and as wide.

- **Each gathered call is a branch of the run in its own right**: its own context, its own
  budget under what remains of its caller's, its own state if it is resumable, its own sessions
  and hooks. Neither of two siblings is under the other, and neither can see the other.
- **A run of flows calling flows is a tree**, and reads back as the tree it ran as.
- **Each branch is handed an agent of its own.** What a called flow is given for a role is its
  own view of that agent: the sessions it spawns are its own, the hooks it hangs are heard by
  nobody else's sessions, and nothing it does touches the caller's. Handing the same agent to
  ten gathered calls is ten flows each driving it as theirs.
- **A chain of calls has a bottom**, at 64, so that a recursion with no base case is named
  where it went wrong — `FlowDepthExceeded` — rather than becoming a `RecursionError` somewhere
  else entirely.
- **What a branch spends counts against every flow above it**, from whichever thread its turn
  reported it, and a deadline above it stops every branch under it.

## Where each of them lands

The same fan-out, aimed anywhere:

| | |
| --- | --- |
| **this machine** | every session spawned in the workspace the run was started in |
| **a worktree apiece** | `derive_worktree`: one agent, several checkouts, all of them going |
| **a copy apiece** | `derive_temp_clone`: a throwaway copy of the workdir, removed when the flow that made it ends |
| **an ssh target** | an environment `-e` points at another machine: the agent stays here; its commands land there — [the anchor](/features/anchor) |

**What moves is where the commands land, not the agent:** it goes on running here, with its own
credentials and its own trajectory, and only what it does reaches the other machine.

## Reading two hundred conversations

Above the editor you see one agent and `1 of 200`. Stepping moves between the conversations
that are **working** — not all two hundred, only the ones thinking right now. The screen keeps
the last eight and the last two thousand lines of each; the rest of it is in the trace, which
is where a fan-out is meant to be read.

## Where the detail is

- [Many turns at once](/weaver/async-flows) — writing the coroutine, and gathering
- [Worktrees, copies and scratch](/weaver/worktrees) · [Remote
  execution](/user/remote-execution)
- [Many conversations at once](/user/conversations) — the editor view

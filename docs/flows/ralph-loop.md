---
pageClass: hmz-feature
---

# ralph_loop

A fresh session every round, so nothing carries over but the repository: the agent starts from
the task each time, and what the round before it did is whatever it left in the working
directory. The oldest trick in unattended agent work, and still the one that survives the
longest runs — a loop that cannot poison itself with its own context.

```sh
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b duration=6h,cost=50 "$(cat TASK.md)"
```

One role, `agent`, working in the directory the run was started in — the `workspace`, which
nobody names with `-e`.

<HmzFlowShape flow="ralph_loop" />

## Why it holds up

A session that runs for a day accumulates every wrong turn it took. A round that starts clean
reads the repository as it is — the tests the last round broke, the file it left half-written —
with no memory of the reasoning that got it there.

The cost is real: an agent that forgets will re-derive things, and sometimes undo a decision it
made an hour ago because nothing in the tree records that it was a decision. Write the
decisions into the repository, and the loop reads them back.
[`stateful_ralph`](/flows/stateful-ralph) is the same loop with the opposite trade.

## What ends it

The run's [budget](/features/allowances) — `-b duration=…,cost=…,output_tokens=…` — which is
humanize's rather than this flow's: it is held to at every turn of every session, so a round
taken once it is spent raises rather than answering and the loop needs no exit of its own. The
flow itself takes no params at all, and declares no budget of its own: `hmz exec` refuses to
start it without a `-b`.

## What it keeps

`rounds`, in its [state](/features/resuming). A loop left going for days will be stopped — esc,
a machine that goes down, a turn that takes the process with it — so running it again with
`--resume` goes on from the round it reached rather than back at one.

A run stopped by its budget is one to **pick up**, not one that is over. The budget is that
run's and the next run is given one of its own, so what was kept is left exactly where it is
rather than cleared. See [Picking a run up](/user/resuming).

## What else ends it

**Three rounds in a row that came to nothing.** A loop whose every turn fails or comes back
empty — an account the backend refused, a model that account may not run — spends nothing, so
it would go round on the same failure for as long as its budget's duration let it; three stalled
rounds end it sooner. What it kept
is left alone here too: a loop that stalled is one to fix and carry on from, not one that is
over.

## See also

- [stateful_ralph](/flows/stateful-ralph) — one session instead, re-sent the task each round
- [goal](/flows/goal) — this loop's task, set as the agent's own goal
- [Loops](/weaver/loops) — writing one of these yourself

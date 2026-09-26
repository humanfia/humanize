---
pageClass: hmz-feature
---

# Every run has a budget

A run is given a **budget** — how long it may take, how much it may cost, how many output
tokens its agents may write — and when one of them is spent, the run stops. `hmz exec` will not
start without one:

```sh
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high \
    -b duration=6h,cost=50,output_tokens=10m "$(cat TASK.md)"
```

Whichever limit is reached first is the one that stops it, and a budget names at least one. A
command line that names none is a usage error before any agent starts; the one exception is
[`chat`](/flows/chat), a conversation that ends when you stop typing, which runs under
`Budget(cost=inf)`.

| `-b` | What it limits | Written as |
| --- | --- | --- |
| `duration` | wall clock, from when the run starts | `90s`, `1h30m`, `2d`, `PT1H30M`, `01:30:00`, or seconds |
| `cost` | USD | `50`, `$50`, `inf` |
| `output_tokens` | tokens the agents write | `200000`, `200k`, `1.5m` |
| `graceful` | whether the turn under way may finish when a limit is reached | `true` (the default) or `false` |

`-b` repeats and takes a comma list, as every flag of `hmz exec` does: `-b duration=6h -b cost=50`
is the same budget as `-b duration=6h,cost=50`.

## Why these three

**Duration** is the only one that moves whether or not anything is being spent. That is what
makes it the one that stops a loop whose every turn is failing: a turn that could not run spends
no tokens and costs no money, so a refused account would go round on the same failure for as
long as it was left.

**Output tokens** are what the work is. The input of a turn is the conversation so far, sent
again at every request and mostly served from a cache; what the agent writes is what a run is
paying for.

**Cost** is what you actually pay, priced from what each turn's CLI reports. It is the one that
cannot always be read: a model nobody lists a price for is counted at nothing, so a cost limit on
such a model never bites. Put a duration or a token limit beside it.

## It is not a flow's to implement

A flow has no budget of its own to offer: whoever runs it says what the run may spend. What a flow sees of it is
`ctx.budget` — what this call may still spend, every budget above it taken together — and
`ctx.usage`, what it and every call under it have spent so far.

It is held to by the runtime, at every turn of every session of every agent, whatever harness is
behind it. No driver cooperates and none can opt out; a hook is the *flow's* seam, and a budget
the person set must not be defeatable by a flow hanging one.

## A flow that calls a flow

A called flow may be given a budget of its own:

```python
verdict = await review(task, agents=..., envs=..., params=..., budget=Budget(cost=2))
```

and runs under **the tighter of its own and what remains of its caller's**. So a flow can hold a
step to two dollars, and a run that has one dollar left holds it to one.

- **Cost and output tokens roll up.** What a turn spends counts against the call it was taken in
  and every call above it, from whichever thread the CLI reported it on. A fan-out of ten
  reviews spends ten reviews' worth of the run's budget.
- **Duration is a deadline.** A call's `duration` is counted from when that call started and is
  not summed over its children: ten reviews gathered at once under a one-hour deadline have an
  hour between them, not ten.
- **A spent budget stays spent.** Once a call's budget runs out, every later turn under it —
  its own, and those of every flow it calls — is refused rather than spending more.

`run` takes a `budget=` too, for one turn on top of the call's: see
[A turn can be cut off](/features/budgets).

## What "stopped" means

The next turn under a spent budget raises the leaf of `BudgetExceeded` for the limit that ran
out — `DurationExceeded` (which is also a `TimeoutError`), `CostExceeded`,
`OutputTokensExceeded` — and a flow that does not catch it ends with it, as the run does.

**What happens to the turn under way is `graceful`'s to say.** A graceful budget — the default —
lets the turn that spends the last of it run to its end and answer with what it said: its edits
are on disk and its conversation is open, so it is a round that ended rather than a round that
failed. The turn after it is refused. A deadline that passes while turns are running waits for
them to finish, then stops the call.

A budget with `graceful=false` cuts the turn off the moment a limit is reached — the CLI stops
spending — and that turn raises instead of answering. Which is what a budget has to be where a
turn that overruns is worse than a turn that stops mid-sentence.

A call whose deadline passes is stopped where it stands — everything under it, awaited or
gathered — and raises `DurationExceeded` there. A run cancelled from outside is still a cancel,
not a spent budget.

## Per run, not across runs

The budget is this run's. A run [picked up](/features/resuming) with `--resume` is a new run
with the budget its own command line gave it; what it kept is left exactly where it was, which
is what makes a run stopped by its budget a run to pick up rather than one that is over.

## Setting one

From a command line, `-b`, as above. From the interface, `/flow` asks for the budget with the
rest of the run — its roles, its environments, its params — and remembers it per flow, so a flow
run every morning is not a budget to type every morning.

See [A turn can be cut off](/features/budgets) for the limit on one turn rather than on the run,
[Cost and rate](/user/tally) for what the readings are made of, and
[Stopping](/user/stopping) for ending a run by hand.

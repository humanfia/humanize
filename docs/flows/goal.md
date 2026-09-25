---
pageClass: hmz-feature
---

# goal

The task, set once as the agent's own [goal](/features/goals): a turn that would have ended
starts another instead, until the model itself says the objective is met.

```sh
hmz exec -f goal -a worker=claude/claude-opus-5:max -b duration=4h,cost=40 "$(cat TASK.md)"
```

<HmzFlowShape flow="goal" />

## Two things decide, and only one of them is your code

The ticks inside one box above are turns the *backend* started. `/goal <task>` hands the
objective to the backend's own goal feature; what comes back is one `run`, with as many turns of
the model inside it as it thought the objective needed.

That is why you reach for this rather than [`ralph_loop`](/flows/ralph-loop): "is this done?"
is asked by something that has just read the work, every turn, rather than by a `while True`
that cannot tell. The cost is that it is asked by the same thing that did the work, which
[`rlar`](/flows/rlar) fixes by asking somebody else.

The `worker` role is declared with `GoalCommandAgentMixin`, so a harness without a goal feature
cannot fill it, and is refused before the first turn rather than an hour in.
[Which backends have one](/weaver/goals).

## What ends it

The model saying the objective is met — and, under that, the run's
[budget](/features/allowances): `-b duration=…,cost=…,output_tokens=…`. It counts **every turn of
the model the goal took**, not one per call: the backend started them, and the driver counted
them all as they were reported. A budget with `graceful=false` cuts the goal off where it stands
once it is spent; a graceful one lets it finish and refuses what comes after. The flow itself
takes no params and declares no budget of its own, so `hmz exec` refuses to start it without a
`-b`.

## What it keeps

Nothing. The goal is pursued in one session, and a run is one goal: running it again starts from
the task and the repository exactly as the first run did.

## See also

- [It decides when it is done](/features/goals) — what a goal is
- [ralph_loop](/flows/ralph-loop) — the same task, with your code deciding a turn is over
- [rlar](/flows/rlar) — somebody other than the worker deciding

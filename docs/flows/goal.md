---
pageClass: hmz-feature
---

# goal

Hand the task to the agent as its own [goal](/features/goals): the model keeps working, turn
after turn, until it says the goal is met. One call, one session, and the model decides when
it is done.

<Badge type="warning" text="worker: claude · codex · dsh · kimi · zcode" />

::: code-group

```text [at the prompt]
❯ $goal get the benchmark under 200 ms without changing its output
```

```sh [hmz exec]
hmz exec -f goal -a worker=claude/claude-opus-5:max \
    -b duration=4h,cost=40 "$(cat TASK.md)"
```

:::

<HmzFlowShape flow="goal" />

## When to use it

In [ralph_loop](/flows/ralph-loop), a loop that cannot read the work decides when a round is
over. Here the model that has just done the work decides, every turn. The catch is that it is
judging its own work; [rlar](/flows/rlar) asks a separate reviewer instead.

The flow sends `/goal <task>` to a backend that has a goal feature of its own. Only `claude`,
`codex`, `dsh`, `kimi` and `zcode` do, and any other backend is refused before the first turn.
[Which backends have one](/weaver/goals).

## Roles and params

| Role | |
| --- | --- |
| `worker` | Pursues the goal, in one session. |

No params.

## What ends it

- **The model says the goal is met.**
- **The [budget](/features/allowances).** It counts every turn the goal took, not one per call.

::: warning The whole goal is one turn
A budget lets the turn under way finish by default, and here that turn is the whole goal. If
the budget is a hard ceiling, pass `-b graceful=false`, which cuts the goal off the moment a
limit is reached.
:::

## Picking it up

`goal` keeps nothing for `--resume`: running it again starts from the task and the repository,
as the first run did.

## See also

- [It decides when it is done](/features/goals): what a goal is
- [rlar](/flows/rlar): a reviewer, rather than the worker, decides

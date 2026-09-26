---
pageClass: hmz-feature
---

# stateful_ralph

Leave one agent on a task it has to remember. One session holds the whole run and is sent the
task again every round, so the agent keeps every approach it has already ruled out.

::: code-group

```text [at the prompt]
❯ $stateful_ralph find why the parser leaks memory, and fix it
```

```sh [hmz exec]
hmz exec -f stateful_ralph -a agent=kimi/kimi-code/k3:high \
    -b duration=6h "$(cat TASK.md)"
```

:::

<HmzFlowShape flow="stateful_ralph" />

## When to use it

Reach for it when the work is exploratory, and *what has already been tried* is the expensive
thing to find out again. The opposite trade is [ralph_loop](/flows/ralph-loop), which is the
better choice when the work is simply long.

What grows is the conversation. Six hours in, the backend is compacting or summarising it, or
refusing to take more. That limit is the backend's, not the budget's.

## Roles and params

| Role | |
| --- | --- |
| `agent` | Takes every round, in the one session the run holds. |

No params. The loop pauses 5 seconds between rounds.

## What ends it

- **The [budget](/features/allowances).** Whichever limit of `-b` runs out first.
- **Three rounds in a row that answer nothing.** A round whose turn fails counts as one that
  answered nothing, as in [ralph_loop](/flows/ralph-loop#what-ends-it).

## Picking it up

`--resume` carries on the round count, and nothing else: the session is not picked up. The
resumed run opens a new conversation that starts from the task and the repository, with none
of the earlier rounds in it. A loop stopped on round 40 says round 41 when it starts again, and
remembers nothing of the forty. See [Picking a run up](/user/resuming).

## See also

- [continue_loop](/flows/continue-loop): one session too, told "continue" instead of the task
- [ralph_loop](/flows/ralph-loop): a fresh session every round

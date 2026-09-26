---
pageClass: hmz-feature
---

# continue_loop

Send the task once, then keep saying "continue" to the same session, which is what a person at
a prompt would type. The agent keeps its whole conversation, and every round it is told to
carry on rather than told the task again.

::: code-group

```text [at the prompt]
❯ $continue_loop port the test suite from unittest to pytest
```

```sh [hmz exec]
hmz exec -f continue_loop -a agent=kimi/kimi-code/k3:high \
    -b duration=6h "$(cat TASK.md)"
```

:::

<HmzFlowShape flow="continue_loop" />

## When to use it

Like [stateful_ralph](/flows/stateful-ralph), it holds one session, so the agent remembers
what it tried. The difference is the prompt: `stateful_ralph` repeats the task, which pulls the
agent back to it every round, while "continue" lets it follow its own plan.

"Continue" only makes sense to a session that heard the task. Until a turn has answered, the
flow sends the task again rather than "continue".

## Roles and params

| Role | |
| --- | --- |
| `agent` | Takes every round, in the one session the run holds. |

No params. The loop pauses 5 seconds between rounds.

## What ends it

- **The [budget](/features/allowances).** However much the agent says it is done, it is told
  to continue, so this is the usual end.
- **Three failed turns in a row.** The run ends with the last failure. A turn that answers with
  nothing is not a failure; it is simply sent again.

## Picking it up

`--resume` carries on the round count. The session is not picked up: the resumed run opens a
new one, which has heard nothing, so it is sent the task first, exactly as the first run was.
See [Picking a run up](/user/resuming).

## See also

- [stateful_ralph](/flows/stateful-ralph): the same session, sent the task every round
- [goal](/flows/goal): the backend's own way of not stopping

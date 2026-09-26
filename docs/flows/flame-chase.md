---
pageClass: hmz-feature
---

# flame_chase

Put two agents on one task and let them take turns. Each turn is a fresh session that starts
from the task and the repository; neither agent is told what the other said, so the working
tree is all that passes between them.

::: code-group

```text [at the prompt]
❯ $flame_chase make the importer handle every file in samples/
```

```sh [hmz exec]
hmz exec -f flame_chase \
    -a first_chaser=claude/claude-opus-5:max -a second_chaser=codex/gpt-5.6-sol:max \
    -b duration=8h,cost=100 "$(cat TASK.md)"
```

:::

<HmzFlowShape flow="flame_chase" />

## When to use it

Two different models fail differently. A loop over one agent compounds that agent's blind
spots; a loop that alternates hands every turn to an agent that did not write what it is
looking at. Give both roles the same model and they are still two agents, which a
[trace](/user/tracing) shows as two sets of sessions.

If one of the two should judge rather than work, use [rlar](/flows/rlar).

## Roles and params

| Role | |
| --- | --- |
| `first_chaser` | Takes the odd turns, each in a fresh session. |
| `second_chaser` | Takes the even turns, each in a fresh session. |

No params. The loop pauses 5 seconds between turns.

## What ends it

- **The [budget](/features/allowances).** The two spend one budget between them, not one each.
- **Three failed turns in a row.** The run ends with the last failure. A turn that fails passes
  to the other chaser, so three in a row means both have failed.

## Picking it up

`--resume` carries on with whichever chaser was next, so neither takes two turns in a row, and
it keeps counting rounds: a round is one turn each. See [Picking a run up](/user/resuming).

## See also

- [flame_chase_agent_cleanup](/flows/agent-cleanup): this loop, with a cleaner between turns
- [parallel_flame_chase](/flows/parallel-flame-chase): three of these at once, in three lanes

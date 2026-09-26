---
pageClass: hmz-feature
---

# rlar

Have every round of work reviewed, and stop when the reviewer agrees it is done. An actor works
in one session that remembers; a fresh reviewer reads the repository after each round, and its
review is the actor's next prompt, word for word.

::: code-group

```text [at the prompt]
❯ $rlar add undo and redo to the editor
```

```sh [hmz exec]
hmz exec -f rlar \
    -a actor=claude/claude-opus-5:high -a reviewer=codex/gpt-5.6-sol:high \
    -b duration=6h,cost=60 "$(cat TASK.md)"
```

:::

<HmzFlowShape flow="rlar" />

## When to use it

When "is it done?" should not be answered by the agent that did the work. Every review comes
from a session that has just started: it reads the repository itself and knows nothing of how
the work was arrived at. Give both roles the same model if you like; that asymmetry is still
the point.

Each review answers in a fixed [shape](/features/shapes), so the flow reads a field rather than
hunting for a phrase:

| Field | What the reviewer says |
| --- | --- |
| `done` | `true` only if everything asked for is implemented, works, and nothing was faked, stubbed or special-cased to pass |
| `notes` | The review itself, written to the actor: what is wrong or missing and what to do next, citing files and lines |

The reviewer is told to be skeptical, and to treat reward hacking, such as weakened tests or
stubbed-out work, as the thing it is there to catch. How it reads a round and writes its notes
is the flow's own [skill](/user/skills), `review-notes`, carried by every review session.

## Roles and params

| Role | |
| --- | --- |
| `actor` | Does the work, in one session held for the whole run. |
| `reviewer` | Reads the repository after each round, in a fresh session every time. |

No params. The loop pauses 5 seconds between rounds.

## What ends it

- **The reviewer says `done`.** Its notes are the last thing the run prints.
- **The [budget](/features/allowances).** The ceiling, not the usual end.
- **Three failures in a row.** A failed turn, or a review that does not fit the shape, is taken
  again next round; the third in a row ends the run with that failure.

## Picking it up

`--resume` carries on the round count and the last review nobody has acted on. The actor's
session is not picked up, so the resumed actor is sent both: the task, and under it that
review, marked as a reading of work this session did not do.

That review may even be of another task: `--resume` picks up the newest run of `rlar` in this
directory, whatever it was asked. A run the reviewer agreed with keeps nothing. See
[Picking a run up](/user/resuming).

## See also

- [humanize1](/flows/humanize1): the same actor-and-reviewer idea, with a plan agreed first
- [flame_chase](/flows/flame-chase): two agents both working, rather than one reviewing

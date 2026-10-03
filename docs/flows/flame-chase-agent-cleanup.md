---
pageClass: hmz-feature
---

# flame_chase_agent_cleanup

Keep a long relay's workspace tidy. [flame_chase](/flows/flame-chase), with a `cleaner` that
steps in every few turns between the two chasers: it keeps the work, deletes what strayed,
writes down what is next, and the repository's history becomes one commit of what survived.
The same cleaner behind one agent is [ralph_loop_agent_cleanup](/flows/ralph-loop-agent-cleanup).

<Badge type="warning" text="every role: claude · codex · kimi · pi" />

::: code-group

```text [at the prompt]
❯ $flame_chase_agent_cleanup make every test in tests/ pass
```

```sh [hmz exec]
hmz exec -f flame_chase_agent_cleanup \
    -a first_chaser=claude/claude-opus-5:high -a second_chaser=codex/gpt-5.6-sol:high \
    -a cleaner=claude/claude-opus-5:high \
    -p work_paths=src -p budget.duration=12h,budget.cost=100 "$(cat TASK.md)"
```

:::

<HmzFlow flow="flame_chase_agent_cleanup" />

::: danger Each cleaning rewrites your git history
Every cleaning replaces the repository's history with a single commit, `epoch N: distilled
tree`. The history it replaces is archived outside the repository, never deleted; the flow's
[README](https://github.com/humanfia/flowverse/blob/main/flows/flame_chase_agent_cleanup/_flame_chase_agent_cleanup/README.md#history-archive)
says how to read it back. Run this on a clone you are willing to have rewritten.
:::

## When to use it

On a relay long enough that the tree fills up with scratch files, dead ends and notes nobody
reads again. Each chaser's fresh session then starts from a tree that holds only the work under
`work_paths` and a short `NEXT.md` saying what to do next.

The chasers alternate straight across a cleaning: after an odd number of turns, the other
chaser opens the next stretch. Unlike plain `flame_chase`, a turn that comes to nothing is
taken again by the same chaser rather than passed to the other.

## Roles and params

| Role | |
| --- | --- |
| `first_chaser` · `second_chaser` | The coding turns, alternating, each in a fresh session. |
| `cleaner` | One cleaning at a time, in a fresh session that it keeps through its repairs. |
| `human` | You, filled in by humanize. Asked only whether to start on a very large workspace. |

Every role must be a backend the flow can speak to mid-turn, because a turn that runs too long
is told to wrap up: `claude`, `codex`, `kimi` or `pi`. Any other is refused before the first
turn.

`work_paths` is required, and the other params and their defaults are those of
[ralph_loop_agent_cleanup](/flows/ralph-loop-agent-cleanup#roles-and-params): `cleanup_turns`
(`3`), `next_lines`, `comment_lines`, `repairs`, `check_command`, the three turn timeouts,
`max_tracked_file_mb` and `confirm_large_workspace_copies`.

## What ends it

- **The [budget](/features/allowances).** A cleaning it interrupts puts the tree back first.
- **Three turns in a row that come to nothing.** A turn that answered nothing, or whose backend
  failed, is taken again by the same chaser; the third in a row stops the run.

## Picking it up

`--resume` carries on the turn count, and so whose turn is next, and the cleanings done so far,
so the next cleaning comes when it would have. See [Picking a run up](/user/resuming).

## See also

- [flame_chase](/flows/flame-chase): the relay, without the cleaning
- [ralph_loop_agent_cleanup](/flows/ralph-loop-agent-cleanup): the same cleaning, behind one
  agent
- [Talking to a running turn](/user/steering): what telling a turn to wrap up is

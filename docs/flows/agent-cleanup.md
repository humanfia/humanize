---
pageClass: hmz-feature
---

# ralph_loop_agent_cleanup · flame_chase_agent_cleanup

Keep a long run's workspace tidy. [ralph_loop](/flows/ralph-loop) and
[flame_chase](/flows/flame-chase), with a `cleaner` that steps in every few turns: it keeps the
work, deletes what strayed, writes down what is next, and the repository's history becomes one
commit of what survived.

<Badge type="warning" text="every role: claude · codex · kimi · pi" />

::: code-group

```text [at the prompt]
❯ $ralph_loop_agent_cleanup make every test in tests/ pass
❯ $flame_chase_agent_cleanup make every test in tests/ pass
```

```sh [hmz exec]
hmz exec -f ralph_loop_agent_cleanup \
    -a agent=claude/claude-opus-5:high -a cleaner=claude/claude-opus-5:high \
    -p work_paths=src -b duration=12h,cost=100 "$(cat TASK.md)"
hmz exec -f flame_chase_agent_cleanup \
    -a first_chaser=claude/claude-opus-5:high -a second_chaser=codex/gpt-5.6-sol:high \
    -a cleaner=claude/claude-opus-5:high \
    -p work_paths=src -b duration=12h,cost=100 "$(cat TASK.md)"
```

:::

<HmzFlowShape pick="ralph_loop_agent_cleanup,flame_chase_agent_cleanup" />

::: danger Each cleaning rewrites your git history
Every cleaning replaces the repository's history with a single commit, `epoch N: distilled
tree`. The history it replaces is archived outside the repository, never deleted; the flow's
[README](https://github.com/humanfia/flowverse/blob/main/flows/ralph_loop_agent_cleanup/_ralph_loop_agent_cleanup/README.md#history-archive)
says how to read it back. Run these on a clone you are willing to have rewritten.
:::

## When to use it

On a run long enough that the tree fills up with scratch files, dead ends and notes nobody
reads again. Each fresh session then starts from a tree that holds only the work under
`work_paths` and a short `NEXT.md` saying what to do next.

## Roles and params

| Role | |
| --- | --- |
| `agent`, or `first_chaser` and `second_chaser` | The coding turns, each in a fresh session. The chasers alternate. |
| `cleaner` | One cleaning at a time, in a fresh session that it keeps through its repairs. |
| `human` | You, filled in by humanize. Asked only whether to start on a very large workspace. |

Every role must be a backend the flow can speak to mid-turn, because a turn that runs too long
is told to wrap up: `claude`, `codex`, `kimi` or `pi`. Any other is refused before the first
turn.

`work_paths` is required: the paths, relative to the repository, where agents may create or
change the work, as `-p work_paths=src,include` or a JSON list. The rest have defaults:

| Param | Default | |
| --- | --- | --- |
| `cleanup_turns` | `3` | Coding turns between cleanings. `0` never cleans. |
| `next_lines` | `10` | The most lines `NEXT.md` may hold. |
| `comment_lines` | `30` | Comment lines allowed across `work_paths`. Going over is reported, never cut. |
| `repairs` | `2` | Times a cleaning that left too much is handed back to the cleaner, before the flow cuts it down itself. |
| `check_command` | blank | A check to run after each cleaning, such as your test command. If it fails, the cleaning is undone. Blank skips it. |
| `session_timeout_minutes` | `240` | Minutes before a coding turn is told to wrap up. `0` for never. |
| `stop_grace_minutes` | `10` | Minutes after that before the turn is cut off. |
| `idle_timeout_minutes` | `20` | Minutes of a turn spending nothing before it gets a reminder. `0` for never. |
| `max_tracked_file_mb` | `10` | Files larger than this are never committed. |
| `confirm_large_workspace_copies` | `true` | Ask before starting on a workspace over 5,000 files or 1 GiB. Under `hmz exec` nobody answers, so the run does not start; set it to `false` to only warn. |

## What ends it

- **The [budget](/features/allowances).** A cleaning it interrupts puts the tree back first.
- **Three turns in a row that come to nothing.** A turn that answered nothing, or whose backend
  failed, is taken again by the same agent; the third in a row stops the run.

## Picking it up

`--resume` carries on the turn count and the cleanings done so far, so the next cleaning comes
when it would have. See [Picking a run up](/user/resuming).

## See also

- [ralph_loop](/flows/ralph-loop) · [flame_chase](/flows/flame-chase): the loops, without the
  cleaning
- [Talking to a running turn](/user/steering): what telling a turn to wrap up is

---
pageClass: hmz-feature
---

# ralph_loop_agent_cleanup · flame_chase_agent_cleanup

[`ralph_loop`](/flows/ralph-loop) and [`flame_chase`](/flows/flame-chase), with a third agent
that cleans the workspace every few turns: it distills the work, deletes what strayed, writes
down what is next, and the repository's history is replaced by one commit of what survived. Two
flows, one implementation, kept identical by design.

```sh
hmz exec -f ralph_loop_agent_cleanup \
    -a agent=claude/claude-opus-5:high -a cleaner=claude/claude-opus-5:high \
    -p work_paths=src -b duration=12h,cost=100 "$(cat TASK.md)"
hmz exec -f flame_chase_agent_cleanup \
    -a first_chaser=claude/claude-opus-5:high -a second_chaser=codex/gpt-5.6-sol:high \
    -a cleaner=claude/claude-opus-5:high \
    -p work_paths=src -b duration=12h,cost=100 "$(cat TASK.md)"
```

## Roles

| | |
| --- | --- |
| `agent` — or `first_chaser` and `second_chaser`, alternating | The coding turns, a fresh session each |
| `cleaner` | One cleaning epoch at a time, keeping one session through its repairs |
| `human` | You — the [outworlder](/features/human), filled in by the runtime and never by `-a` |

Every agent role is declared with `SteeringAgentMixin`: a turn is steered to wrap up when its
clock runs out, so each takes a harness that can be told something mid-turn — Claude Code,
Codex, Kimi Code or pi — and any other is refused before the first turn. The workspace is the
directory the run was started in, worked in through its shell.

## A turn, and an epoch

Every coding turn is a fresh session. After `session_timeout_minutes` it is steered to wrap up,
and `stop_grace_minutes` later it is cut off; a reminder is steered in when it has gone
`idle_timeout_minutes` without spending anything. A turn that answered nothing, or whose harness
failed, is taken again on the same seat, and three of those in a row end the run.

Every `cleanup_turns` turns, between turns, the tree is saved aside and a cleaner session
distills the `work_paths`, deletes strays outside them and writes `NEXT.md`. What survived is
measured, and handed back up to `repairs` times; `check_command`, where there is one, is run on
the result, and a failure restores the tree. Then the history is archived and replaced by one
commit, `epoch N: distilled tree`. An epoch that is stopped, out of budget or failed restores the
tree before the run ends. The replaced history is never deleted: every epoch's is kept in the
workspace's `history.git` under humanize's home, `~/.humanize/<flow>/<workspace-key>/`.

## What it takes

`work_paths` is required — the paths, relative to the repository, where agents may create or
revise task work: `-p work_paths=src,include`, or a JSON list. The rest have defaults:

| | |
| --- | --- |
| `cleanup_turns` | Coding turns between epochs; `3`, and `0` never cleans |
| `next_lines` · `comment_lines` | The most lines `NEXT.md` may hold, `10`, and the comment-line cap under the work paths, `30` |
| `repairs` | Over-measures handed back to the cleaner; `2` |
| `check_command` | A correctness check after cleaning; `""` skips it |
| `session_timeout_minutes` · `stop_grace_minutes` · `idle_timeout_minutes` | `240`, `10` and `20`; `0` disables either timeout |
| `max_tracked_file_mb` | Files larger than this, `10`, are never committed |
| `confirm_large_workspace_copies` | Ask before cleaning a workspace past 5,000 files or 1 GiB; `true` — and under `hmz exec`, where nobody answers, the run does not start |

## What ends it

The run's [budget](/features/allowances): whichever limit of `-b` is reached first stops it, and
an epoch it stops is put back first. Three turns in a row that came to nothing end it sooner. It
can be picked up with `--resume`, which carries on the run's turn count and epochs.

## See also

- [ralph_loop](/flows/ralph-loop) · [flame_chase](/flows/flame-chase) — the loops, without the
  cleaning
- [A line typed mid-turn](/features/steering) — what steering a turn is

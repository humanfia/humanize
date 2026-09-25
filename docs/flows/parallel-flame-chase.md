---
pageClass: hmz-feature
---

# parallel_flame_chase

Seven agents, three lanes, one working directory. A coordinator plans them once and does not
come back; six actors alternate in fresh sessions and coordinate through durable reports.
**Lane 1 alone owns the original source** — lanes 2 and 3 work in private snapshots and publish
artifacts rather than writing to your tree.

```sh
hmz exec -f parallel_flame_chase \
    -a coordinator=codex/gpt-5.6-sol:max \
    -a lane_1_actor_a=claude/claude-opus-5:max,lane_1_actor_b=codex/gpt-5.6-sol:max \
    -a lane_2_actor_a=claude/claude-opus-5:max,lane_2_actor_b=codex/gpt-5.6-sol:max \
    -a lane_3_actor_a=claude/claude-opus-5:max,lane_3_actor_b=codex/gpt-5.6-sol:max \
    -b duration=12h,cost=500 "$(cat TASK.md)"
```

<HmzFlowShape flow="parallel_flame_chase" />

## Seven agents, by name

Each `-a` names the role it fills, and the interface asks for them by the same names. The
eighth role, `human`, is you — the [outworlder](/features/human), filled in by the runtime and
never by `-a`:

| | |
| --- | --- |
| `coordinator` | Plans the three lanes, once, and leaves the run |
| `lane_1_actor_a` · `lane_1_actor_b` | Lane 1, alternating — the only writers of the original source |
| `lane_2_actor_a` · `lane_2_actor_b` | Lane 2, alternating, in a snapshot of its own |
| `lane_3_actor_a` · `lane_3_actor_b` | Lane 3, alternating, in a snapshot of its own |

None of the seven is declared with the [goal](/features/goals) mixin, because a lane's turn
ends where the lane protocol says it ends rather than where a model decides it has met the
objective. The flow declares it, so it holds for whichever agents the run is given: a `/goal`
through any of them is refused.

## One writer, and two that cannot write

A per-source advisory lock permits only one lane 1 owner; lanes 2 and 3 are confined to
snapshots, and the runtime's control paths reject links and replacements. What they produce
reaches lane 1 as a **report** and a hashed, reconstructable artifact package, and reports are
redelivered until the receiving lane completes a valid turn and acknowledges them, so a lane
that fell over does not lose what it was told.

Durable data lives under `~/.humanize/parallel_flame_chase/<workspace-key>/<run-id>/`. The flow
coordinates local work only: there is no release, deployment, submission, messaging or purchase
executor in it.

## What it takes

Its params, each a `-p`:

| | |
| --- | --- |
| `rest_seconds` | what the single-writer scheduler rests between control passes; `1.0` |
| `resume_mode` | `auto`, or `fresh` to deliberately start another run |
| `confirm_large_workspace_copies` | whether to ask before copying a very large workspace; `false` |
| `workspace_file_warning_threshold` · `workspace_copy_warning_threshold_bytes` | what counts as very large |

The [skill](/user/skills) it brings, `parallel-flame-chase`, is the actor, report, artifact,
checkpoint and resume protocol — carried by every session the flow opens.

Its lanes are scheduled again for as long as it runs, so the run's
[budget](/features/allowances) is the only end there is: give `-b` a duration.

## What it keeps

The plan, the snapshots, each lane's A/B alternation and its lane-local failure state, for a
run picked up with `--resume`. The same
substantive task resumes compatible state; a bare `continue` reads `TASK.md` when there is one,
and replans against a fresh source snapshot where the objective has changed. A different one
starts a fresh run.

## See also

- [parallel_flame_chase_git_pr](/flows/parallel-flame-chase-git-pr) — the same lanes, each
  with a clone and pull requests
- [flame_chase](/flows/flame-chase) — one lane of this, and the flow it is named after
- [Worktrees, copies and scratch](/weaver/worktrees) — humanize's own way of giving an agent a
  tree of its own

---
pageClass: hmz-feature
---

# parallel_flame_chase_git_pr

The same three lanes as [`parallel_flame_chase`](/flows/parallel-flame-chase), run the way a
team runs a repository: **every lane owns a clone and has equal pull-request rights**, and what
reaches `main` is decided by a measurement rather than by a reviewer. It is the fixed
configuration that did best in a twelve-hour Git PR Lite experiment, and nothing else.

```sh
hmz exec -f parallel_flame_chase_git_pr \
    -a orchestrateor=codex/gpt-5.6-sol:max \
    -a lane_1_actor_a=codex/gpt-5.6-sol:max,lane_1_actor_b=claude/claude-opus-5:max \
    -a lane_2_actor_a=claude/claude-opus-5:max,lane_2_actor_b=codex/gpt-5.6-sol:max \
    -a lane_3_actor_a=claude/claude-opus-5:max,lane_3_actor_b=codex/gpt-5.6-sol:max \
    -b duration=12h,cost=500 "$(cat TASK.md)"
```

<HmzFlowShape flow="parallel_flame_chase_git_pr" />

## Seven agents, by name

| | |
| --- | --- |
| `orchestrateor` | Plans the three lanes, once |
| `lane_1_actor_a` · `lane_1_actor_b` | Lane 1, alternating in fresh turns, in a clone of its own |
| `lane_2_actor_a` · `lane_2_actor_b` | Lane 2, the same |
| `lane_3_actor_a` · `lane_3_actor_b` | Lane 3, the same |

The eighth role, `human`, is you — the [outworlder](/features/human), filled in by the runtime
and never by `-a`. There is no reviewer role: nothing here asks a model whether a change is good.

## A pull request is merged by a measurement

The runtime keeps a bare central repository and an integration clone of its own. A lane may
keep many drafts, but only one ready pull request at a time; a ready head is frozen, and a newer
candidate from the same lane supersedes its older one.

`pfc evaluate -- <command>` is how a lane measures: it runs the official evaluator on a clean
tree, keeps what it wrote outside git, and leaves an immutable receipt. The runtime picks the
candidate with the best receipt and publishes its exact tested tree only when it improves `main`
— and the repository's own hook accepts `main` only for a commit with the tested head's tree,
its receipt, and an allowed-path diff. No model review and no second evaluation run on this
path, which is what makes it fast and what makes it honest.

What passes between lanes is **Report Share** — each lane's durable reports — and the system's
own reports of what was merged and what was rejected. The flow's other mechanisms — global
knowledge, experiment memory, the token-efficient and main-monitor variants — are switched off
and cannot be switched back on: they are fixed as literals in its params, so a launch cannot
turn the measured workflow into a different one by accident.

## What it takes

The base flow's params — `rest_seconds`, `resume_mode`, the large-workspace thresholds — each a
`-p`. Before it makes its copies it measures the source, and warns where the planning tree, the
three lane clones, the integration clone and the git objects between them come to more than the
thresholds; `-p confirm_large_workspace_copies=true` makes it ask first instead.

The [skill](/user/skills) it brings, `parallel-flame-chase-git-pr`, is the lane, pull-request and
receipt protocol, carried by every session the flow opens.

Like the base flow, its lanes go on for as long as it runs, so the run's
[budget](/features/allowances) is its end: give `-b` a duration.

## What it keeps

The central repository's refs, the receipts, the artifacts, the report archive and the official
ledger, for a run picked up with `--resume`. The original source is assumed not to change
outside the flow while it holds the source lock.

## See also

- [parallel_flame_chase](/flows/parallel-flame-chase) — the same lanes, with one writer and two
  snapshots
- [flame_chase](/flows/flame-chase) — one lane of this, and the flow it is named after
- [Many turns at once](/features/concurrency) — why seven agents are not seven queues

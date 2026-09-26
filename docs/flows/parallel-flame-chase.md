---
pageClass: hmz-feature
---

# parallel_flame_chase

Chase three leads at once. A coordinator plans three lanes and leaves; in each lane two actors
take turns in fresh sessions, and the lanes keep each other informed by report. **Only lane 1
writes your tree**: lanes 2 and 3 work on private copies, and what they find reaches lane 1 as
a report and an artifact.

::: code-group

```text [at the prompt]
❯ $parallel_flame_chase get the solver under 10 s on every benchmark in bench/
```

```sh [hmz exec]
hmz exec -f parallel_flame_chase \
    -a coordinator=codex/gpt-5.6-sol:max \
    -a lane_1_actor_a=claude/claude-opus-5:max,lane_1_actor_b=codex/gpt-5.6-sol:max \
    -a lane_2_actor_a=claude/claude-opus-5:max,lane_2_actor_b=codex/gpt-5.6-sol:max \
    -a lane_3_actor_a=claude/claude-opus-5:max,lane_3_actor_b=codex/gpt-5.6-sol:max \
    -b duration=12h,cost=500 "$(cat TASK.md)"
```

:::

<HmzFlowShape flow="parallel_flame_chase" />

## When to use it

When the task is open enough that three approaches are worth trying side by side, and you have
the budget for seven agents. It is [flame_chase](/flows/flame-chase) three times over, with a
plan up front and one lane in charge of the tree. If every lane should get a clone and compete
through pull requests instead, use
[parallel_flame_chase_git_pr](/flows/parallel-flame-chase-git-pr).

It coordinates local work only: nothing in it releases, deploys, submits or sends anything.

## Roles and params

| Role | |
| --- | --- |
| `coordinator` | Plans the three lanes, once, and leaves the run. |
| `lane_1_actor_a` · `lane_1_actor_b` | Lane 1, taking turns. The only ones that write your tree. |
| `lane_2_actor_a` · `lane_2_actor_b` | Lane 2, taking turns, on a private copy. |
| `lane_3_actor_a` · `lane_3_actor_b` | Lane 3, taking turns, on a private copy. |
| `human` | You, filled in by humanize. Asked only to confirm copying a very large workspace. |

Every role may write anywhere its user can and use the web: lanes run your builds, tests and
evaluators, and publish what they make beside the workspace. Any backend can fill any role, and
none of them is run as a `/goal`.

| Param | Default | |
| --- | --- | --- |
| `rest_seconds` | `1.0` | Seconds the scheduler rests between passes, 0.05 to 60. |
| `resume_mode` | `auto` | `auto` picks up a compatible earlier run; `fresh` starts another. |
| `confirm_large_workspace_copies` | `false` | Ask before copying a very large workspace. Under `hmz exec` nobody answers, so the run stops before copying. |
| `workspace_file_warning_threshold` | `5000` | Files that make a workspace very large. |
| `workspace_copy_warning_threshold_bytes` | `1073741824` | Bytes of copies that make it very large (1 GiB). |

## What ends it

**The [budget](/features/allowances), or you.** The lanes are scheduled again for as long as
the run goes, so give `-b` a duration. When it runs out, the turns under way finish and are
recorded, and the run stops.

A lane whose two turns in a row fail is held until the objective is replanned; the others go
on.

## Picking it up

`--resume` picks up the plan, the copies, the reports and whose turn each lane is on. Given the
same task, it carries on where it stopped. Given `continue`, it reads `TASK.md` if there is
one. Given a changed objective, it plans again against a fresh copy of your tree, in the same
run. See [Picking a run up](/user/resuming).

Only one run may hold a source tree at a time, whether of this flow or of
`parallel_flame_chase_git_pr`: a second one refuses to start.

## See also

- [parallel_flame_chase_git_pr](/flows/parallel-flame-chase-git-pr): the same lanes, each with
  a clone and pull requests
- [flame_chase](/flows/flame-chase): one lane of this, on its own

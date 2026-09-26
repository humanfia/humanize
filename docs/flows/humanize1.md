---
pageClass: hmz-feature
---

# humanize1

Plan first, then build under review. [PolyArch/humanize](https://github.com/PolyArch/humanize),
the Claude Code plugin humanize grew out of, as three flows you run one after another:
`gen-idea` opens a loose idea into a draft, `gen-plan` turns the draft into a plan two agents
agreed on, and `rlcr` builds that plan under review until nothing is left to say.

<Badge type="warning" text="rlcr builder: claude · codex · kimi · zcode" />
<Badge type="info" text="rlcr needs a git repository" />

::: code-group

```text [at the prompt]
❯ $humanize1:gen-idea add undo and redo to the editor
❯ $humanize1:gen-plan add undo and redo to the editor
❯ $humanize1:rlcr build the plan
```

```sh [hmz exec]
hmz exec -f humanize1:gen-idea -a drafter=claude/claude-opus-5:max \
    -b cost=10 "add undo and redo to the editor"
hmz exec -f humanize1:gen-plan \
    -a planner=claude/claude-opus-5:max -a analyst=codex/gpt-5.6-sol:max \
    -b cost=30 "add undo and redo to the editor"
hmz exec -f humanize1:rlcr \
    -a builder=claude/claude-opus-5:max -a reviewer=codex/gpt-5.6-sol:max \
    -b duration=2d,cost=300 -p max=20 "build the plan"
```

:::

Name the phase: a bare `humanize1` is refused. Each phase is a run of its own, and what passes
from one to the next is a file, the draft and then the plan. Read and edit each before you
start the next, and put each phase on whichever models suit it.

## 1 · gen-idea {#gen-idea}

<HmzFlowShape flow="humanize1-gen-idea" />

One `drafter` picks `n` different directions for the idea, explores each against this
repository, and writes a draft with one main direction and the rest as alternatives. It writes
no code. The run ends when the draft is written.

| Param | Default | |
| --- | --- | --- |
| `n` | `6` | Directions to explore, 2 to 10. |
| `output` | blank | Where the draft goes. Blank writes a new file under `.humanize/ideas/`; a file that already exists is refused. |

## 2 · gen-plan {#gen-plan}

<HmzFlowShape flow="humanize1-gen-plan" />

The `analyst` first checks the draft is about this repository and lists its risks. The
`planner` writes the plan in one session; the analyst reviews it, fresh each time, for up to
three rounds, stopping early once they agree or after two revisions that change nothing
material. The run ends when the plan is written.

A decision the two left `PENDING` fails the run once the plan is written: answer it in the
file, or run `gen-plan` again with somebody at the prompt to be asked.

| Param | Default | |
| --- | --- | --- |
| `input` | blank | The draft to plan from. Blank takes the newest in `.humanize/ideas/`. |
| `output` | blank | Where the plan goes. Blank is `docs/plan.md`, which must not exist yet. |
| `mode` | `discussion` | `discussion` reviews and revises; `direct` writes the plan once. |
| `auto_start_rlcr_if_converged` | `false` | Once the two have agreed, do not put open decisions to you. |
| `alternative_plan_language` | blank | Also write the plan translated: `zh`, `ko`, `ja`, `es`, `fr`, `de`, `pt`, `ru` or `ar`. |
| `turn_timeout` | `3600` | Seconds one planning turn may take; `0` for no limit. |
| `total_timeout` | `14400` | Seconds all of the planning may take; `0` for no limit. |
| `turn_retries` | `1` | Retries of a failed or empty turn, 0 to 3. |

## 3 · rlcr {#rlcr}

<HmzFlowShape flow="humanize1-rlcr" />

The `builder` works in one session until it believes the whole plan is done. The round's checks
run, then a fresh `reviewer` reviews what landed, and its findings are what the builder hears
next. When the reviewer finds nothing left, a code review of the whole change runs, and the
loop ends once that is clean too. `rlcr` builds the plan in `docs/plan.md`; the task on the
line is not read.

- **You are quizzed on the plan first,** if you are at the prompt: two questions the reviewer
  writes, to check you have read what is about to be built. Under `hmz exec` or `/afk` it is
  skipped.
- **The builder must be `claude`, `codex`, `kimi` or `zcode`.** The loop's guards, which keep
  the builder from editing the plan or its own state, work by answering its permission
  requests, and only those backends ask.
- **It needs a git repository.** Every review reads the work since the commit the plan was
  fixed in.

| Param | Default | |
| --- | --- | --- |
| `max` | `42` | Rounds before the loop stops. |
| `plan_file` | blank | The plan to build. Blank is `docs/plan.md`. |
| `base_branch` | blank | What the code review compares against. Blank tries the remote's default branch, then `main`, then `master`. |
| `full_review_round` | `5` | Rounds between full checks of the work against the plan; at least 2. |
| `codex_timeout` | `5400` | Seconds one review may take. A review that runs over counts as failed. |
| `skip_code_review` | `false` | Finish when the build is done, without the final code review. |
| `skip_impl` | `false` | Skip the build and go straight to the code review. |
| `skip_quiz` | `false` | Do not quiz you on the plan. |
| `claude_answer_codex` | `false` | The builder settles the reviewer's open questions itself, instead of asking you. |
| `yolo` | `false` | `skip_quiz` and `claude_answer_codex` together. |
| `track_plan_file` | `false` | The plan is tracked in git, and must stay unchanged. |
| `push_every_round` | `false` | Push after every round. Needs a remote. |
| `agent_teams` | `false` | The builder leads a team of agents. Needs the variable below. |
| `privacy` | `false` | No methodology analysis when the loop ends. |
| `require_bitlesson_entry_for_none` | `false` | Every round must record a lesson. |

`agent_teams` needs `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` set where you start the run.

## What ends it

`gen-idea` and `gen-plan` end when their file is written. `rlcr` ends on the first of:

- **`complete`**: the reviewer finds nothing left, and the code review is clean;
- **`maxiter`**: `max` rounds have run;
- **`stop`**: the reviewer calls a halt, or the loop sees it going round in circles;
- **the [budget](/features/allowances)**, as for every phase.

## Picking it up

Only `rlcr` can be picked up. `--resume` carries on the same loop, from the round it reached,
with a new builder session sent that round's prompt. If the new run's params differ from the
loop's, it says which one, and starts a loop of its own instead. The agents may change: `-a` is
yours to choose on every run.

`gen-idea` and `gen-plan` keep nothing: running one again writes another file.

::: details Coming from the plugin
Every flag the plugin takes is a param of the phase it belongs to, under the plugin's own name.
A run writes what the plugin writes, where the plugin writes it: `.humanize/rlcr/<timestamp>/`
in your repository, with `state.md`, `goal-tracker.md`, and a prompt, summary and review per
round. `humanize monitor rlcr` reads a run of this.

Four things work differently:

| In the plugin | Here |
| --- | --- |
| `codex review --base <ref>` | The reviewer is whichever agent you chose, so the code review is asked for in a prompt that asks for the same `[P0-9]` findings. |
| `--codex-timeout` | A review that runs past it is treated as a failed review, which is where the plugin's own timeout leaves the round. |
| `/humanize:ask-codex` | The builder cannot reach the reviewer mid-round, so it puts the question in its round summary, where the reviewer answers it. |
| The plan quiz | Put to you only when you are at the prompt. With nobody there, it is skipped, and no reviewer turn is spent on it. |
:::

## See also

- [rlar](/flows/rlar): the same actor-and-reviewer loop, without a plan
- [recursive_lean_prover](/flows/recursive-lean-prover): built out of `gen-plan` and `rlcr`
- [A flow that calls a flow](/weaver/calling-flows): running a phase from inside another flow

---
pageClass: hmz-feature
---

# humanize1

[PolyArch/humanize](https://github.com/PolyArch/humanize) — the Claude Code plugin humanize
grew out of — as three flows, each set up on its own agents and stopping on its own. `gen-idea`
opens a loose idea into a repo-grounded draft, `gen-plan` turns that draft into a plan both
sides have converged on, and `rlcr` builds the plan under review until nothing is left to say.

```sh
hmz exec -f humanize1:gen-idea -a drafter=claude/claude-opus-5:max -b cost=10 \
    "add undo/redo to the editor"
hmz exec -f humanize1:gen-plan \
    -a planner=claude/claude-opus-5:max -a analyst=codex/gpt-5.6-sol:max \
    -b cost=30 "add undo/redo to the editor"
hmz exec -f humanize1:rlcr \
    -a builder=claude/claude-opus-5:max -a reviewer=codex/gpt-5.6-sol:max \
    -b duration=2d,cost=300 -p max=20 "build it"
```

`humanize1` has no flow of the directory's own name, so a bare `-f humanize1` is refused,
listing the three: name a phase, `humanize1:<phase>`. All three work in `workspace`, the
directory the run was started in, and `rlcr`'s third role, `human`, is you — the
[outworlder](/features/human), filled in by the runtime rather than by `-a`.

Three rather than one because each is set up on its own agents, and what passes between them is
a file, as it is in the plugin — the draft, then the plan. So an idea may be opened on one
model, planned on another and built on a third, with whatever reading and editing you like in
between. [Three flows in one file](/reference/flows#several-flows-in-one-file).

Run it in a git repository: the work is anchored to the commit the plan was fixed in, and every
review reads what came after it.

## 1 · `gen-idea`

<HmzFlowShape flow="humanize1-gen-idea" />

One agent, `n` directions explored at once, one draft written out. `n` and `output` are the two
params, under the names the plugin gives them: `-p n=5,output=IDEA.md`. `n` is 6 unless it is
given, from 2 to 10; an `output` left blank writes `.humanize/ideas/<slug>-<stamp>.md`, and one
that already exists is refused.

## 2 · `gen-plan`

<HmzFlowShape flow="humanize1-gen-plan" />

The planner holds one session for the whole of the planning; the analyst arrives fresh each
time and reads the plan against the repository. They converge — up to three review rounds,
stopping after two in which nothing material changed. `input` names the draft to plan from (the
newest `.humanize/ideas/*.md` where it is blank), `output` the plan to write (`docs/plan.md`,
which must not exist yet), `mode` is `discussion` or `direct`, `alternative_plan_language`
writes a translated plan beside the plan, and `turn_timeout`, `total_timeout` (3600 and 14400
seconds, `0` for none) and `turn_retries` (1) bound the agents' turns. A decision the two left
`PENDING` fails the run once the plan is written.

## 3 · `rlcr`

<HmzFlowShape flow="humanize1-rlcr" />

The loop is the plugin's: the builder works a round until it believes the whole plan is done,
the round's gates are run, and the round is put to the reviewer — and what the reviewer says is
what the builder hears next instead of stopping. The plugin blocks Claude's exit to do that;
here it is the flow's own loop, builder, gates and reviewer, which reads the same on every
harness. The plugin's tool validators are hooks, as they are there: an
[`on_permission_request` hook](/features/hooks) on the builder, which is why the builder's role
is declared with `PermissionRequestHookAgentMixin` and has to be a harness that asks — Claude
Code, Codex, Kimi Code or ZCode — beside an `on_pre_tool_use` hook that watches what it reads
and its task list, and an `on_user_prompt_submit` hook on its opening prompt.

Every flag the plugin takes is a field on that phase's own params, under the plugin's own name
for it: `max` (42), `full_review_round` (5), `codex_timeout` (5400 seconds), `skip_code_review`,
`plan_file` (`docs/plan.md` where it is blank), `base_branch` (`origin/HEAD`, then `main`, then
`master` where it is blank), `skip_quiz`, `yolo`, and the rest. `-p` sets any of them, and the
params form in `/flow` is all of them. The task on the line is not read: the plan is the task.

It writes what the plugin writes, where the plugin writes it: `.humanize/rlcr/<timestamp>/`
with `state.md`, `goal-tracker.md`, and a prompt, summary, contract and review per round — so
`humanize monitor rlcr` reads a run of this.

## Four things done another way

The plugin's mechanism, where humanize's is not the same mechanism:

| | |
| --- | --- |
| `codex review --base <ref>` | Takes no prompt and is a Codex feature. Here the reviewer is whichever agent was chosen, so the code review is **asked for**, in a prompt that asks for exactly the `[P0-9]` output the loop then reads the same way. |
| `--codex-timeout` | A review that runs past it is treated as a review that failed, which is the state the plugin's own timeout leaves the round in. |
| `/humanize:ask-codex` | A task the plan tags `analyze` is a shell script the builder runs there. Here the builder has no way to reach the reviewer mid-round, so it is told to put the question in its round summary, where the reviewer answers it. |
| The plan quiz | Put to `human`, the outworlder, only when somebody is there: the reviewer writes the questions and you pick an answer to each. With nobody at the prompt — `hmz exec`, `/afk` — it is skipped, and no reviewer turn is spent on it. |

## What it keeps

`rlcr` is meant to run for days, so a run of it can be picked up with `--resume`: it keeps
**which** `.humanize/rlcr/` directory the loop is in and the round it reached, reads `state.md`
back as it stands rather than stamping a new directory beside a week of rounds, and sends the
round's saved prompt to a new builder session. It ends `complete` — the reviewer saying so and a
clean code review — `maxiter` on its `max` rounds, `stop` where the reviewer or the drift breaker
says to, or `unexpected`. Everything else is
already in that directory in the plugin's own format, and a second copy here would be a second
place for it to be wrong.

A loop carries on with the params it was set up with. A run set up differently is neither
quietly overridden nor quietly ignored: it says which param it disagrees with the loop about,
and starts a loop of its own. The agents are the one thing that is not a param — `-a` chooses
them per run, and the state file is brought up to date to say who is reading the rounds.

`gen-idea` and `gen-plan` keep nothing: each writes one file, running one again is meant to
write another, and between their turns there is nothing to carry on from.

## See also

- [The moments of a turn](/features/hooks) — what a permission-request hook is, and the others
- [rlar](/flows/rlar) — the same actor-and-reviewer shape, without the plugin's format
- [A flow that calls a flow](/weaver/calling-flows) — running one of these three from inside another flow

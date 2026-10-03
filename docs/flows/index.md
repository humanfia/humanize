---
pageClass: hmz-feature
---

# Flows

A **flow** is a loop around coding agents: which agents it drives, what each is asked, and when
it stops. Pick the one that fits your job, give each of its roles an agent, and set a budget.

<HmzFlows />

## Reading the diagrams

Every flow's page plays a simulated run of it, and every one is drawn with the same few marks.
A mark means one thing, in every diagram:

<HmzFlowLegend />

The camera follows the run: it closes in on each turn as it starts, cranes up while lanes run
at once, drops a level where the work splits, and pulls back for the loop and the finish. Pause
it, step a moment at a time, or drag the bar. With reduced motion set, the whole run is drawn at
rest instead.

## The loops, side by side

Most of these flows differ in one thing: what an agent has in front of it when a round starts.
Play them one after another and watch for the spark of a new session against the thread of a
held one:

<HmzFlow pick="ralph_loop,stateful_ralph,continue_loop,goal,flame_chase,rlar" />

These six are the loops [FlowBench](https://humanfia.ai/projects/flowbench) scores, under the
same names, so a result there tells you which flow to reach for here.

## Running one

At the prompt, `$` and a flow's name start it on the rest of the line. On the command line, the
same run is `hmz exec`:

::: code-group

```text [at the prompt]
❯ $rlar add undo and redo to the editor
```

```sh [hmz exec]
hmz exec -f rlar \
    -a actor=claude/claude-opus-5:high -a reviewer=codex/gpt-5.6-sol:high \
    -p budget.duration=6h,budget.cost=60 "$(cat TASK.md)"
```

:::

The first time you start a flow at the prompt, it asks for an agent for each role, the flow's
params and a budget, then remembers them for this project. `/flow` changes them later.

| On the command line | What it says |
| --- | --- |
| `-f rlar` | the flow, by the name on its card |
| `-a actor=claude/claude-opus-5:high` | the agent for one role: `role=CLI/MODEL:EFFORT`, once per role |
| `-p max=20` | a param, for a flow that takes some |
| `-p budget.duration=6h,budget.cost=60` | the [budget](/features/allowances). Every flow but `chat` needs one |
| `--resume` | pick up this flow's newest run in this directory |

Two things never take a flag: the `human` role, which is you, and the directory the agents work
in, which is wherever you start the run. Every flag is in the [CLI reference](/reference/cli).

::: tip On a fresh install, open `hmz` once first
Every flow but `chat` comes from humanize's own flowverse, which `hmz` fetches in the
background as it opens. Until then, `hmz exec` refuses the flow and tells you to open
the Flowverses page of `/settings`, open `official` and choose `fetch`.
:::

::: warning Agents act without asking
No flow puts an agent's command or edit to you for approval. Each role may do what its flow
declares, which for most is: change the working directory, run commands, commit. Run a flow
only where you would accept that, and read [Security](/user/security) first.
:::

## What ends a run

- **The budget.** Whichever of `duration`, `cost` and `output_tokens` runs out first stops the
  run, and `hmz exec` exits 0. See [Every run has a budget](/features/allowances).
- **The flow itself.** Most flows also end on their own: a reviewer agrees, a goal is met, or
  three rounds in a row fail or come back empty. Each card says when.
- **You.** `/stop` at the prompt, or <kbd>ctrl+c</kbd> under `hmz exec`. See
  [Stopping a run](/user/stopping).

A flow whose card says what `--resume` keeps carries on from there, under a fresh budget. See
[Picking a run up](/user/resuming).

## Where flows come from

| You type | The flow is |
| --- | --- |
| `ralph_loop` | one of humanize's own: `chat` ships with humanize, and the rest are in [humanfia/flowverse](https://github.com/humanfia/flowverse) |
| `local/scheduler` | one of this project's, in `.humanize/flows/` |
| `user/scheduler` | one of yours, in `~/.humanize/flows/` |
| `theirs/rlar` | one from a flowverse you added in `/settings` |

A **flowverse** is any git repository with a `flows/` directory. [Writing a
flow](/weaver/writing-a-flow) is how to make your own, and [Flowverses](/weaver/flowverses) is
how to publish one.

::: danger Adding a flowverse trusts that repository with this machine
A flow is Python, and listing what a flowverse holds runs every flow file in it. Add only the
ones you would clone and run.
:::

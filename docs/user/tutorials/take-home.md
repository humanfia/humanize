# Beat a benchmark

In this tutorial you point two agents at Anthropic's open performance take-home and let them
take turns on it for hours, while you check their progress against a number that cannot lie.

::: info At a glance
- **You will learn** how to write a task a long loop can work from, how to start a flow from
  the command line with `hmz exec`, how to check an agent's claims yourself, and how to find
  the turn that mattered in a run's trace.
- **You will end with** the three things in the table below.
- **Time:** about an hour of your attention and a few hours of the machine's.
- **You need** humanize and one signed-in coding agent CLI. Two different ones do better.
:::

| You end with | Where |
| --- | --- |
| a kernel taken from 147,734 simulated cycles down past 1,790, with its tests passing | `perf_takehome.py` |
| the agents' lab notebook: what they tried, and what it measured | `NOTES.md` |
| every turn on one timeline, showing which one moved the number | `/epics`, in `hmz` |

## Before you start

- **Install humanize and sign in to a coding agent CLI.** See
  [Installation](/user/installation). One signed-in backend is enough, since it can fill both
  roles.
- **Make one run first.** [Your first run](/user/first-run), or the
  [quickstart on the home page](/#run-a-flow), shows you a flow working in a scratch
  repository. This tutorial assumes you have seen that.
- **Open `hmz` once.** `flame_chase` comes from the official
  [flowverse](/weaver/flowverses), a git repository of flows, and opening `hmz` in any directory
  is what fetches it. `hmz exec` does not fetch it for you. Leave with `/exit`.
- **Have Python 3 and git.** The benchmark is a Python script.
- **Set aside a budget.** The command below allows up to eight hours and $100. Lower `cost=` if
  your account is billed by the token and you want to spend less.

## Step 1: Get the problem

```sh
git clone https://github.com/anthropics/original_performance_takehome
cd original_performance_takehome
python tests/submission_tests.py
```

Among the eight failures it reports, you should see:

```console
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  147734
Speedup over baseline:  1.0
```

**What just happened.** You optimise a kernel for a simulated VLIW SIMD machine.
`perf_takehome.py` is the kernel you may change, and `tests/submission_tests.py` measures it.
`CYCLES` is the number of simulated clock cycles the kernel takes: lower is better.

Eight of the nine tests fail, and each failing test is a threshold somebody has already
reached:

| Cycles | Reached by |
| ---: | --- |
| 18,532 | where the two-hour version of the take-home starts you |
| 2,164 | Claude Opus 4, many hours in a test-time compute harness |
| 1,790 | Claude Opus 4.5 in an ordinary Claude Code session, about the best human result in two hours <Badge type="tip" text="this run" /> |
| 1,579 | Claude Opus 4.5, two hours in the harness |
| 1,548 | Claude Sonnet 4.5, many more than two hours |
| 1,487 | Claude Opus 4.5, 11.5 hours |
| 1,363 | Claude Opus 4.5, an improved harness |

::: tip Checkpoint
`CYCLES:  147734`. That is the number the rest of this tutorial drives down.
:::

## Step 2: Write the task down

The loop runs the same prompt for hours, so it is worth more care than a chat message. Put it
in a file and commit it:

```sh{7-13,17-20}
cat > TASK.md <<'EOF'
Make `perf_takehome.py` run the kernel in as few simulated clock cycles as
possible, without breaking it.

The rules, from the repository's own Readme:

- Do not touch anything under `tests/`. `git diff origin/main tests/` must stay
  empty. A solution that edits the tests is not a solution.
- Do not fake a speedup. Multicore is disabled on purpose; `N_CORES` stays 1.
  Nothing may be stubbed, special-cased for the test inputs, or made to skip
  work the kernel is supposed to do.
- `python tests/submission_tests.py` is the only measurement that counts. It
  prints CYCLES and the thresholds passed.

Where you are starting from: 147734 cycles.

Each turn: measure first, make one substantial optimisation, measure again, and
commit it only if the cycle count went down and the tests still pass. Write
what you tried and what it measured into NOTES.md, and commit that too, so
whoever takes the next turn does not repeat it.
EOF
git add -A && git commit -qm "the task"
```

**What just happened.** The highlighted lines do the work:

1. **The rules against cheating.** The Readme warns that none of the sub-1,300
   submissions on the first day were valid, because in each one a model had edited the tests.
   An agent that is never asked anything will find that shortcut, so name it, together with the
   command that proves nobody took it.
2. **Measure, change, measure, commit.** Without the measuring, a turn can end believing it
   made things faster. Without the commit, a turn that backs out its own failed attempt with
   `git checkout` backs out every earlier turn's work with it, since none of it was committed.
   In a run of this tutorial without it, the second chaser's third turn did just that, and
   took the kernel from 1,641 cycles back to 147,734.
3. **`NOTES.md`.** Each turn starts from nothing, so anything worth carrying has
   to be written to a file.

Committing the task means `git log` later shows the agents' work and nothing of yours.

::: tip Checkpoint
`git log --oneline -1` shows `the task`, and `git status` is clean.
:::

## Step 3: Start the loop

The flow is [`flame_chase`](/flows/flame-chase). It gives two agents the task in turn, and
every turn opens a fresh **session**, a conversation with the model that has seen nothing
before. What passes from one turn to the next is the repository and `NOTES.md`, not a
transcript.

<HmzFlow flow="flame_chase" />

Start it. Pick the tab for the backends you have:

::: code-group

```sh [Claude Code + Codex]
hmz exec -f flame_chase \
    -a first_chaser=claude/claude-opus-5-5:high \
    -a second_chaser=codex/gpt-5.6-sol:high \
    -b duration=8h,cost=100 \
    "$(cat TASK.md)"
```

```sh [Claude Code only]
hmz exec -f flame_chase \
    -a first_chaser=claude/claude-opus-5-5:high \
    -a second_chaser=claude/claude-opus-5-5:high \
    -b duration=8h,cost=100 \
    "$(cat TASK.md)"
```

```sh [Codex only]
hmz exec -f flame_chase \
    -a first_chaser=codex/gpt-5.6-sol:high \
    -a second_chaser=codex/gpt-5.6-sol:high \
    -b duration=8h,cost=100 \
    "$(cat TASK.md)"
```

:::

The first turn starts at once, and closes with what it spent:

```console
● first_chaser is working
  …
✻ input 84.2k · output 12.9k · $3.41 · claude-opus-5 · first_chaser
✻ Worked for 734s · first_chaser
● second_chaser is working
```

**What just happened.** Each part of the command:

1. **`hmz exec`** runs a flow in this directory with nobody at a prompt. It prints what the
   agents say, and returns when the flow ends. See [Run it unattended](/user/unattended).
2. **`-f flame_chase`** names the flow.
3. **`-a first_chaser=…` and `-a second_chaser=…`** give each of the flow's two roles an
   agent, written `CLI/MODEL:EFFORT`. Any other backend fills a role the same way.
4. **`-b duration=8h,cost=100`** is the budget: the run stops at eight hours or a hundred
   dollars, whichever comes first.
5. **`"$(cat TASK.md)"`** is the task, the file you wrote, given whole.

In the output, `● first_chaser is working` opens a turn, and the `✻` lines close it with the
tokens and dollars it spent and how long it took. Then the other chaser starts.

::: warning `flame_chase` never stops itself
"As few cycles as possible" has no end, so the budget is what stops it. To stop sooner, press
<kbd>ctrl+c</kbd>.
:::

::: tip Checkpoint
You see `● first_chaser is working`. If the run is refused instead, see
[Troubleshooting](#troubleshooting).
:::

## Step 4: Watch the number

Leave the run going. In another terminal, measure:

```sh
cd original_performance_takehome
python tests/submission_tests.py 2>&1 | grep -E "CYCLES|Speedup" | tail -2
```

In the run this page was written from, after about half an hour and several turns each:

```console
CYCLES:  1770
Speedup over baseline:  83.46553672316384
```

**What just happened.** The transcript tells you what an agent *believes*. The test tells you
what is true. Measuring from your own terminal is how you keep the two apart.

Now read what the agents wrote for each other:

```sh
head -30 NOTES.md
```

```console
# Optimization notes for perf_takehome.py

## Machine model (from problem.py)
- VLIW bundle = `{engine: [slots]}`. All slots in a bundle run in the SAME cycle.
  Writes take effect at END of cycle (reads see old values). A bundle with any
  non-debug slot costs 1 cycle. Debug-only bundles cost 0.
- Slot limits/cycle: alu 12, valu 6, load 2, store 2, flow 1, debug 64.
…
## Bottleneck analysis
- Total gathers (node_val) = rounds*batch = 16*256 = 4096 scalar loads. At 2
  loads/cycle that's a HARD floor of ~2048 cycles for the naive per-lane gather.
```

That file did not exist when the run started. The loop has no memory besides it, and it is why
turn twelve does not start over like turn one.

::: tip Checkpoint
The number falls turn by turn. If no number comes out, you have probably caught a turn halfway
through a rewrite, so measure again a minute later.
:::

## Step 5: Check that it did not cheat

When the curve flattens, stop the run with <kbd>ctrl+c</kbd>. Before you believe the number:

```sh
git diff origin/main tests/
```

This should print nothing, which means the tests are exactly as they shipped. If it prints a
diff, the number is worthless. Throw it away, state the rule more bluntly in `TASK.md`, and
start again.

```sh
python tests/submission_tests.py
```

`test_kernel_correctness` must pass. A fast kernel that computes the wrong thing is not a
result.

::: tip Checkpoint
An empty `git diff origin/main tests/`, and `test_kernel_correctness` passing. Only then is
`CYCLES` a result.
:::

## Step 6: See which turn moved the number

```sh
hmz
```

Type `/epics`. It lists every run in this directory, newest first. Press <kbd>enter</kbd> on
the top one, the loop you just stopped:

```
2026-08-17 14:02 · flame_chase
/home/you/.hmz/epics/…/20260817T140233.512Z-4c1e9a
It stopped with 2 agents in 12 sessions.

❯ 1. resume run
  2. export run
```

Choose **export run**. The line under the list says where the archive went, in this project's
`.hmz/`. The trace is also at `traces/export.trace.json` inside the directory named under
the screen's title. Drag it into [ui.perfetto.dev](https://ui.perfetto.dev):

```
process   first_chaser · claude-opus-5-5 · high · 6 sessions
  track     main ──▶ ▓▓▓▓▓     ▓▓▓▓▓▓     ▓▓▓▓     ▓▓▓▓▓▓
process   second_chaser · gpt-5.6-sol · high · 6 sessions
  track     main ──▶      ▓▓▓▓▓      ▓▓▓▓▓     ▓▓▓▓▓
```

**What just happened.**

1. **`/epics`** is every run humanize wrote down in this directory. An **epic** is one run of
   one flow.
2. **`It stopped with 2 agents in 12 sessions`**: two chasers, and a fresh session for every
   turn. `stopped`, not finished, because you stopped it.
3. **The trace** has one row per agent. The slices alternate because the two take turns. Click
   a slice to see the prompt, the reasoning and the tool call behind it.

Put the trace next to `NOTES.md` and you can find the turn that took the big step, and the
turns after it that only confirmed it. [Tracing](/user/tracing) says more.

::: tip Checkpoint
Perfetto shows two processes, `first_chaser` and `second_chaser`, with alternating slices.
:::

## Troubleshooting

### It says the official flowverse has not been fetched yet

```console
hmz exec: error: flame_chase: the official flowverse has not been fetched yet -- open the flowverses page of /settings and fetch it from its own sheet
```

`hmz` fetches flowverses in the background each time it opens, and `hmz exec` does not. Run
`hmz`, wait a moment, and run the line again. If it is still refused, type
`/settings flowverses` in `hmz`, open `official`, and choose `fetch`.

### The number does not move for several turns

Read the last few entries of `NOTES.md`. If the agents keep trying the same idea, name it in
`TASK.md` as tried, commit, and start again. Raising the effort to `:max` helps once the easy
wins are gone; see [Efforts](/user/efforts).

### It stopped on its own after three failed turns

Three failed turns in a row end `flame_chase` with the last failure, which the run prints.
It is often an account out of quota or signed out. See
[Troubleshooting](/user/troubleshooting), then pick the run up as in
[Next steps](#next-steps).

## What you learned

- A long loop is only as good as its task file: say what counts, what is forbidden, and how to
  prove neither happened.
- `hmz exec -f … -a … -b …` starts a flow with one agent per role and a budget that stops it.
- A fresh session per turn means the repository and a notes file are the loop's only memory.
- The test, not the transcript, says what is true; and `git diff` says whether the test is
  still the test.
- `/epics` and the exported trace show which turn did what.

## Next steps

- **Carry on from where it stopped.** `flame_chase` can be picked up. Run the same line with
  `--resume` and a fresh `-b`, and it carries on with whichever chaser was next. See
  [Picking a run up](/user/resuming).
- **Ratchet the target.** Put the new floor in `TASK.md` and start again.
- **Mix the models.** Two models that go wrong in different ways beat two copies of the
  stronger one, because each turn inherits the other's blind spots rather than its own.
- **Raise the effort on the last stretch.** `:max` costs more per turn and pays off once the
  easy wins are gone. See [Efforts](/user/efforts).
- **Next tutorial:** [Port a project](/user/tutorials/port-a-project), where one agent keeps
  its whole conversation and a reviewer keeps none.

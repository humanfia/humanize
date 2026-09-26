# Beat a benchmark

**About an hour of your attention, and a few hours of the machine's.** You point two agents at
Anthropic's open performance take-home and let them take turns on it. At the end you have:

| You end with | Where |
| --- | --- |
| a kernel taken from 147,734 simulated cycles down past 1,790, with its tests passing | `perf_takehome.py` |
| the agents' lab notebook: what they tried, and what it measured | `NOTES.md` |
| every turn on one timeline, showing which one moved the number | `/epics`, in `hmz` |

::: tip Before you start
Do the [quickstart on the home page](/#run-a-flow) first. One signed-in backend is enough,
since it can fill both roles. Two different ones do better.
:::

## Step 1: get the problem

```sh
git clone https://github.com/anthropics/original_performance_takehome
cd original_performance_takehome
python tests/submission_tests.py
```

You optimise a kernel for a simulated VLIW SIMD machine. `perf_takehome.py` is the kernel you
may change, and `tests/submission_tests.py` measures it:

```console
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  147734
Speedup over baseline:  1.0
```

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
`CYCLES:  147734`. That is the number the rest of this page drives down.
:::

## Step 2: write the task down

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
keep it only if the cycle count went down and the tests still pass. Write what
you tried and what it measured into NOTES.md, so whoever takes the next turn
does not repeat it.
EOF
git add -A && git commit -qm "the task"
```

The highlighted lines do the work:

- **The rules against cheating.** The Readme warns that none of the sub-1,300 submissions on
  the first day were valid, because in each one a model had edited the tests. An agent that is
  never asked anything will find that shortcut, so name it, together with the command that
  proves nobody took it.
- **Measure, change, measure.** Without it, a turn can end believing it made things faster.
- **`NOTES.md`.** Each turn starts from nothing, so anything worth carrying has to be written
  to a file.

## Step 3: start the loop

The flow is [`flame_chase`](/flows/flame-chase). It gives two agents the task in turn, and
every turn opens a fresh **session**, a conversation with the model that has seen nothing
before. What passes from one turn to the next is the repository and `NOTES.md`, not a
transcript.

<HmzFlowShape flow="flame_chase" />

Start it. Pick the tab for the backends you have:

::: code-group

```sh [Claude Code + Codex]
hmz exec -f flame_chase \
    -a first_chaser=claude/claude-opus-5:high \
    -a second_chaser=codex/gpt-5.6-sol:high \
    -b duration=8h,cost=100 \
    "$(cat TASK.md)"
```

```sh [Claude Code only]
hmz exec -f flame_chase \
    -a first_chaser=claude/claude-opus-5:high \
    -a second_chaser=claude/claude-opus-5:high \
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

There is one `-a` for each role the flow declares, `first_chaser` and `second_chaser`, and any
other backend fills a role the way the quickstart spells it. `-b` is what the run may spend,
and it stops at eight hours or a hundred dollars, whichever comes first.

The first turn starts at once, and closes with what it spent:

```console
● first_chaser is working
  …
✻ input 84.2k · output 12.9k · $3.41 · claude-opus-5 · first_chaser
✻ Worked for 734s · first_chaser
● second_chaser is working
```

::: warning `flame_chase` never stops itself
"As few cycles as possible" has no end, so the budget is what stops it. To stop sooner, press
<kbd>ctrl+c</kbd>.
:::

::: details It says the official flowverse has not been fetched yet
`flame_chase` comes from the official [flowverse](/weaver/flowverses), a git repository of
flows. `hmz` fetches flowverses in the background each time it opens. If one has not landed
yet, the run is refused:

```console
hmz exec: error: flame_chase: the official flowverse has not been fetched yet -- open /flowverses and press r on it
```

Run `hmz`, type `/flowverses`, press <kbd>r</kbd> on `official`, then run the line again.
:::

## Step 4: watch the number

Leave the run going. In another terminal, measure:

```sh
cd original_performance_takehome
python tests/submission_tests.py 2>&1 | grep -E "CYCLES|Speedup" | tail -2
```

The transcript tells you what an agent *believes*. The test tells you what is true. In the run
this page was written from, after about half an hour and several turns each:

```console
CYCLES:  1770
Speedup over baseline:  83.46553672316384
```

::: tip Checkpoint
The number falls turn by turn. If `test_kernel_correctness` fails, you have probably caught a
turn halfway through a rewrite, so measure again a minute later.
:::

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

## Step 5: check that it did not cheat

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

## Step 6: see which turn moved the number

```sh
hmz
```

Type `/epics`. It lists every run in this directory, newest first. Press <kbd>enter</kbd> on
the top one, the loop you just stopped:

```
2026-08-17 14:02 · flame_chase
/home/you/.humanize/epics/…/20260817T140233.512Z-4c1e9a
It was stopped, driving 2 agents through 12 sessions.

❯ 1. resume this run
  2. export it
```

Choose **export it**. The line under the list says where the archive went. The trace is also at
`traces/export.trace.json` inside the directory named at the top of that screen. Drag it into
[ui.perfetto.dev](https://ui.perfetto.dev):

```
process   first_chaser · 6 sessions
  track     main ──▶ ▓▓▓▓▓     ▓▓▓▓▓▓     ▓▓▓▓     ▓▓▓▓▓▓
process   second_chaser · 6 sessions
  track     main ──▶      ▓▓▓▓▓      ▓▓▓▓▓     ▓▓▓▓▓
```

Each agent is one row, and their slices alternate because the two take turns. Click a slice to
see the prompt, the reasoning and the tool call behind it. Put that next to `NOTES.md` and you
can find the turn that took the big step, and the turns after it that only confirmed it.

## Where next

- **Carry on from where it stopped.** `flame_chase` can be picked up. Run the same line with
  `--resume` and a fresh `-b`, and it carries on with whichever chaser was next. See
  [Resuming](/user/resuming).
- **Ratchet the target.** Put the new floor in `TASK.md` and start again.
- **Mix the models.** Two models that go wrong in different ways beat two copies of the
  stronger one, because each turn inherits the other's blind spots rather than its own.
- **Raise the effort on the last stretch.** `:max` costs more per turn and pays off once the
  easy wins are gone. See [Efforts](/user/efforts).
- **Next tutorial:** [Port a project](/user/tutorials/port-a-project), where one agent keeps
  its whole conversation and a reviewer keeps none.

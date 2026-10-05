<script setup>
import SpecReader from '../.vitepress/theme/components/user-after/SpecReader.vue'
</script>

# Run it unattended

Run a flow from one shell line, with nobody at the prompt: from a script, a cron entry or a CI
job. By the end of this page you can write that line, check it before you schedule it, read
what it prints, and act on how it ended. Reach for it whenever a run should start without you,
or when another program wants to read the run as it happens.

## Try it

```sh
hmz exec -f ralph_loop \
    -a agent=claude/claude-opus-5:high \
    -p budget.duration=2h,budget.cost=10 \
    "$(cat TASK.md)"
```

The run is drawn in your terminal as it happens, and the command returns when the flow does:
here, when two hours or ten dollars are spent, whichever comes first.

::: warning Nobody approves anything
A flow's agents run with approvals bypassed: nothing asks before an agent edits a file or runs
a command. What each agent may touch is set by the flow. See [Permissions](/user/permissions).
:::

## Before you start

- **humanize installed**, so `hmz` is on your `PATH`. See [Installation](/user/installation).
- **A coding agent CLI, installed and signed in** on this machine. `hmz exec` runs it as it is
  signed in, unless you name an [account](/user/settings#accounts).
- **The flow within reach.** `ralph_loop` ships with humanize. A flow you install from a
  [flowverse](/weaver/flowverses) is there once it is installed; on a machine where it is not,
  name the flow by its repository instead, as [in CI](/user/ci#a-flow-from-a-flowverse).
- **A task**, as text. Keeping it in a file such as `TASK.md` lets the line stay short and the
  task be reviewed like any other file.

## How a line is read

`hmz exec` asks the same questions the `/flow` sheet asks at the prompt, and the line is every
answer at once:

| Part | Answers | Needed |
| --- | --- | --- |
| `-f` | which flow: the name `/flow` offers it under, a path, or a `git+…#flow` ref | always |
| `-a` | which CLI, account, model and effort fills each agent role | one per role |
| `-p budget.…` | what the run may spend | every flow but `chat` |
| `-p` | the flow's own [params](/weaver/flow-settings), where you want other than the defaults | when you want them |
| `-e` | where an environment role is, for a flow that works on [another machine](/user/remote-execution) | when the flow has one |
| `--profile` | sample the programs the agents start, so the run's trace shows what each turn spent its time on | no |
| `--resume` | carry on the last run of this flow here, rather than start over | no |
| `--json` | write the run to stdout as one JSON object per line | no |
| the task | what the flow is to do | always |

`hmz exec` checks all of it before the first turn. Anything it cannot use is refused in a
second, with nothing started. `hmz exec` does not read what the interface was set up with in
this directory: the line is the whole setup.

### Name an agent for each role

```
<role>=<cli>[@<account>]/<model>[:<effort>]
```

- **role** is the name the flow gives the agent: `agent` for [ralph_loop](https://humanfia.ai/flows/ralph-loop),
  `actor` and `reviewer` for [rlar](https://humanfia.ai/flows/rlar). Each flow's page lists its roles.
- **cli** is one of `agy`, `claude`, `codex`, `cursor-agent`, `dsh`, `grok`, `kimi`, `mcode`,
  `mimo`, `opencode`, `pi`, `qwen`, or a CLI you added on [the Accounts page of
  `/settings`](/user/settings#accounts).
- **@account** runs the turns as an [account](/user/settings#accounts) you made. Leave it off
  to run the CLI as this machine is signed in.
- **model** goes to the CLI as written. humanize does not check it against a list.
- **effort** must be on that CLI's [ladder](/user/efforts); a CLI you added takes any word.
  Leave it off, or write `auto`, for none. A `:` in the model stays the model's unless a word
  follows it, so `mcode/custom_provider:gateway/m` needs no effort; a model whose name ends in
  `:<word>`, as `qwen3:latest`, is written with its effort after it: `qwen3:latest:auto`.
  `auto` asks for none.

The CLI is read up to the first `/` and the effort after the last `:`, so a model with slashes
in it needs no quoting. Several agents go in one `-a`, comma-separated, or in one `-a` each.
Type one below, or pick an example:

<SpecReader />

You never name the person or the working directory. humanize fills those roles itself.

### Set the budget {#say-what-the-run-may-spend}

A loop runs until something stops it, so every flow but `chat` needs a budget, given as
`-p budget.<key>=`:

| Key | Written as |
| --- | --- |
| `budget.duration` | wall clock: `90s`, `1h30m`, `2d`, or ISO `PT6H` |
| `budget.cost` | US dollars: `50` or `$50` |
| `budget.output_tokens` | tokens the agents may write: `200k`, `10m` |
| `budget.graceful` | `false` cuts off the turn under way when a limit is reached. By default it finishes. |

Give at least one limit. When one is reached, the run stops, `hmz exec: stopped -- …` names the
limit on stderr, and the exit status is still 0: for a loop, that is the ordinary way to end.
A flow that calls another shares the budget with it. See [Every run has a
budget](/features/allowances).

::: tip A cost limit needs a priced model
`cost` can only stop a model humanize has a price for. For any other, `hmz exec` says so before
the first turn, and runs anyway:

```text
hmz exec: nobody lists a price for claude-haiku-4-5-20251001, so cost=0.05 cannot stop what it spends
```

A run with a `cost` limit fetches the price list before its first turn when the copy kept is
missing or more than a day old, so a machine that has never opened the interface prices a run
too. The fetch waits at most 20 s; offline, or with `HUMANIZE_PRICES=off`, the run goes on
with whatever list is kept. Add a `duration` or `output_tokens` limit whenever a run must
stop.
:::

## Example: fix a failing test, stopped by its budget

A project with one bug: `add()` in `calc.py` subtracts, and `test_calc.py` says so. `TASK.md`
holds `Fix add() in calc.py so test_calc.py passes. Keep it minimal.` Give a Ralph loop three
cents of a small model and let it go:

```sh
hmz exec -f ralph_loop \
    -a agent=claude/claude-haiku-4-5-20251001:low \
    -p budget.cost=0.03 \
    "$(cat TASK.md)"
```

Points 1 to 4 below are the four parts of that line. What it drew is next, shortened (`…`),
with the model's thinking aloud left out, and ⑤ to ⑨ marked on it:

```text
round 1                                                                        ⑤
● agent is working
● I'll read the test file and the calc.py file to see what needs fixing.
…
● Read(/home/me/calc/test_calc.py)                                             ⑥
● Read(/home/me/calc/calc.py)
● The issue is simple: `add()` is using subtraction instead of addition. I'll fix it.
● Edit(/home/me/calc/calc.py)
● Bash(cd /home/me/calc && python -m pytest test_calc.py -v)
● Done. Changed line 2 of calc.py from `return a - b` to `return a + b`. Test passes.
✻ input 50 · output 762 · cache_read 120.6k · cache_write 8.5k · $0.03 · claude-haiku-4-5-20251001 · agent   ⑦
✻ Worked for 11s · agent
round 2
● agent is working
…
● The test already passes! The `add()` function in calc.py is working correctly.
✻ input 26 · output 643 · cache_read 62.7k · cache_write 848 · $0.01 · claude-haiku-4-5-20251001 · agent
✻ Worked for 9s · agent
round 3
hmz exec: stopped -- ralph_loop:ralph_loop: its budget's cost is spent             ⑧
```

```console
$ echo $?
0                                                                              ⑨
```

### What each part means

1. **`-f ralph_loop`** is the flow. A [Ralph loop](https://humanfia.ai/flows/ralph-loop) gives the same task to a
   fresh session every round, so each round reads the project as the last one left it.
2. **`-a agent=claude/claude-haiku-4-5-20251001:low`** fills the loop's one role, `agent`, with
   Claude Code on a small model at a low effort. A small model and a low effort are the cheap
   way to try a line; raise both for real work.
3. **`-p budget.cost=0.03`** is the budget: three US cents. Use a `duration` too for anything
   you leave running, as the tip above says.
4. **`"$(cat TASK.md)"`** is the task, read from the file by your shell. The quotes keep it one
   argument, however many lines it has.
5. **`round 1`** is the flow's own line, not an agent's. What the flow prints goes to stdout.
6. **`● Read(…)`**, **`● Edit(…)`**, **`● Bash(…)`**: each tool the agent reached for, as it
   reached for it. Lines in dim italic between them, cut here, are the model thinking aloud.
7. **`✻ input 50 · output 762 · … · $0.03`** closes each turn: the tokens it spent by kind,
   what they come to at list price, the model and the role. See [Cost and rate](/user/tally).
8. **`hmz exec: stopped -- … its budget's cost is spent`** is the budget ending the run. The
   turn under way when it filled was let finish; `graceful=false` would have cut it off.
9. **Exit status `0`.** A budget reached is how a loop ends, not a failure. Round 2 found
   nothing left to do, which a Ralph loop does not notice: that is what the budget is for.

### Check that it worked

- **The change is in your files**, where the run left it: `git diff`, or here
  `python -m pytest test_calc.py`.
- **The run is kept.** Open `hmz` in the same directory and type
  [`/epics`](/user/tracing#what-a-run-writes-down): the run is listed as **stopped**, and can
  be traced or [exported](/user/export).
- **The exit status** says how it ended: see [Script on the exit
  status](#script-on-the-exit-status).

## Example: keep the answer apart from the run

The run goes to **stderr**. What each turn answered, and whatever the flow prints, goes to
**stdout**, so a script can take one without the other:

```sh
hmz exec -f chat -a assistant=claude/claude-haiku-4-5-20251001:low \
    "Summarise in one line: humanize runs coding agents in loops." \
    > summary.txt 2> run.log
```

```console
$ cat summary.txt
**Humanize is a system for orchestrating coding agents to iteratively solve tasks in continuous loops.**
$ tail -2 run.log
✻ input 26 · output 596 · cache_read 59.7k · cache_write 4.8k · $0.01 · claude-haiku-4-5-20251001 · assistant
✻ Worked for 9s · assistant
```

1. **`> summary.txt`** takes the answer alone. [`chat`](https://humanfia.ai/flows/chat) needs no budget, and with
   nobody at a prompt it answers once and returns.
2. **`2> run.log`** keeps the run: every tool call, every turn's cost, and any
   `hmz exec: …` line. Redirected, the lines come out without colour or the ticking clock.

At a terminal the same lines are drawn in colour, with a clock at the foot while a turn thinks:
`⠹ agent is working · 12s`. `NO_COLOR` turns colour off. `FORCE_COLOR=1` turns it on for a log
viewer that renders it.

## Check the line before you schedule it

`hmz exec` checks everything it can before the first turn: a line it can't read, a missing
role or budget, an effort off the CLI's ladder, a flow that isn't there. Each is refused in a
second, with exit status 2, before any agent starts. So try the line by hand once:

<HmzCast name="checks" alt="hmz exec refusing a run with no budget, a flow whose role was left unfilled, and a flow that is not there" />

```console
$ hmz exec -f ralph_loop -a agent=claude/claude-haiku-4-5-20251001:low "x"
hmz exec: error: ralph_loop requires a budget: specify with -p budget.cost=...,budget.duration=...,budget.output_tokens=...
$ hmz exec -f chat -a assistant=claude/claude-haiku-4-5-20251001:ultra "x"
hmz exec: error: assistant=claude/claude-haiku-4-5-20251001:ultra: claude cannot be asked to think at 'ultra'; expected one of ultracode, max, xhigh, high, medium, low
```

What is only known once a machine is reached, such as an [environment](/user/remote-execution)
that cannot be, is refused the same way, still before the flow runs. Every message is in
[Troubleshooting](/user/troubleshooting#starting-a-flow).

## Script on the exit status

| Status | Means |
| --- | --- |
| `0` | The flow returned, or its budget stopped it. |
| `1` | The run failed: the flow raised an error it did not handle. The traceback on stderr says which. |
| `2` | Refused before any agent started. The line after `hmz exec: error:` says why. |
| `130` | Interrupted with <kbd>ctrl+c</kbd>, once the run has let go of everything it started. A second <kbd>ctrl+c</kbd> ends it at once, without waiting. |
| `143` | Stopped by a terminate signal, such as `kill` or a cancelled CI job, once the run has let go of everything it started. |

```sh
if ! hmz exec -f goal -a worker=claude/claude-opus-5:max -p budget.duration=4h "$(cat TASK.md)"; then
    echo "the loop did not finish" >&2
    exit 1
fi
```

## Read it with a program

`--json` writes the run to stdout as [NDJSON](https://github.com/ndjson/ndjson-spec): one
object per thing an agent says, flushed as it is said. Nothing else reaches stdout: the flow's
own lines, such as `round 1`, move to stderr with the rest, so the stream always parses.

```sh
hmz exec -f chat -a assistant=claude/claude-haiku-4-5-20251001:low --json "say hello" \
    | jq -c 'select(.kind == "result")'
```

That object, spread out here:

```json
{
  "at": 1790747303.0952988,
  "agent": "assistant",
  "cli": "claude",
  "model": "claude-haiku-4-5-20251001",
  "session": "0a7264b6-8180-406e-bcc0-c1feb14a1964",
  "kind": "result",
  "text": "Hello! 👋 How can I help you today?",
  "whose": "",
  "tokens": {"claude-haiku-4-5-20251001": 20829},
  "spent": {"input": 10.0, "cache_write": 6885.0, "cache_read": 13874.0, "output": 60.0}
}
```

Every object carries every key. `kind` is one of:

| `kind` | The agent… |
| --- | --- |
| `begins`, `ends` | starts and finishes a turn |
| `text`, `reasoning` | says something, or thinks aloud |
| `tool` | uses a tool; `text` names it and what it was given, as `Read /home/me/calc/calc.py` |
| `subagent`, `subagent-ends` | starts an agent of its own, which later finishes |
| `asks` | stops to ask a question |
| `took` | has a line steered into the turn in front of it, and says which |
| `notice` | is waiting out a rate limit, moved to another account, or cut off (humanize says this, not the agent) |
| `failed` | failed the turn |
| `result` | gives the answer the turn ends on. Only this one carries `tokens` (by model) and `spent` (by kind of token). |

The full list of keys is in the [CLI reference](/reference/cli).

## Variations

### Pass params and environments

A flow with [params of its own](/weaver/flow-settings) takes each one you want to change with
`-p`. The flow checks the whole set before the first turn:

```sh
hmz exec -f humanize1:rlcr -p max=9,plan_file=docs/plan.md \
    -a builder=claude/claude-opus-5:max \
    -a reviewer=codex/gpt-5.6-sol:xhigh \
    -p budget.duration=12h,budget.cost=100 "add undo"
```

A flow that works on another machine takes it with `-e`, as `role=local/abs/path`,
`role=ssh@<host>/path` for a host saved under that name, `role=ssh@[user@host:port]/path` for
one nobody saved, or `role=docker@<daemon>/path`; where each agent's CLI runs while it works
there is the [affinity](/user/remote-execution#where-the-agent-runs) of the host or daemon
saved under that name. Most flows have no such role. See [Remote
execution](/user/remote-execution).

### Stop it, and pick it up again

<kbd>ctrl+c</kbd> stops the run: the turn under way ends and its work stays where it got to.
[`/epics`](/user/tracing#what-a-run-writes-down) lists the run as stopped. A flow that can be
[picked up](/user/resuming), such as `ralph_loop`, carries on from there when you run the same
line with `--resume`: a Ralph loop stopped in round 12 starts again at round 13.

```sh
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -p budget.duration=2h \
    --resume "$(cat TASK.md)"
```

### When nobody answers

With nobody at a prompt, the run behaves as if you were [away](/user/afk) the whole time:

- A flow that talks to you is answered with nothing, so `chat` does the one thing it was given
  and returns.
- An agent that stops to ask a question is told nobody answered, and carries on. The question
  is still printed, and with `--json` it is an object of kind `asks`.
- A flow that needs an answer it has no default for fails, and says so.

### A task that starts with a dash

Put `--` before it, so it is read as the task rather than a flag:

```sh
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -p budget.cost=5 \
    -- "--force is not a flag here"
```

## Pitfalls

- **`not installed -- install it from /flow`, or `the official flowverse has not been
  fetched yet`.** The flow is one a flowverse lists, and this machine has not installed it.
  Install it from `/flow`, or name the release by its repository, as
  [in CI](/user/ci#a-flow-from-a-flowverse).
- **A `cost` limit that never stops the run.** The model has no price, and the line said so
  before the first turn. Add `duration` or `output_tokens`.
- **The CLI is not signed in.** Nothing catches it before the run: each turn fails, and a loop
  goes on past failed turns. Run the line by hand once and read what it prints.
- **A script that waits for ever on `chat`.** It will not: with nobody at a prompt, `chat`
  answers once and returns.

More in [Troubleshooting](/user/troubleshooting).

## Next steps

- [humanize in CI](/user/ci): the same line in a scheduled job that opens a pull request
- [Picking a run up](/user/resuming): `--resume`, and what carries over
- [Tracing a run](/user/tracing): what the run did, as a timeline
- [Remote execution](/user/remote-execution): `-e`, and where the agent runs
- [CLI reference](/reference/cli): every flag of `hmz exec`, and every refusal

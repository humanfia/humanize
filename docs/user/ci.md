# humanize in CI

Run a flow from a scheduled job, open a pull request with what it changed, and keep a trace of
what each agent did. By the end of this page you have a nightly GitHub Actions workflow that
does all three, and know what each step is for so you can move it to another CI. Reach for it
when a loop should work on your repository while nobody is at a terminal.

## Try it

Commit a `TASK.md` saying what the loop should work on, add a repository secret your agent's
CLI signs in with, and run the same line CI will run, on your own machine first:

```sh
hmz exec \
    -f 'git+https://github.com/humanfia/flowverse@main#ralph_loop' \
    -a agent=claude/claude-opus-5:high \
    -b duration=45m,cost=20 \
    "$(cat TASK.md)"
```

When that does what you want, put it in the [workflow
below](#example-a-nightly-loop-that-opens-a-pull-request). The line is explained in [Run it
unattended](/user/unattended); this page is the job around it.

::: warning The agents run unsupervised, with the job's access
A flow's agents run with approvals bypassed, and on a runner they can reach whatever the job
can: its token, its secrets, the network. Give the job only the `permissions` and secrets it
needs. See [Permissions](/user/permissions).
:::

## Before you start

- **A line that works by hand.** Everything CI does wrong, it does slowly. Try the `hmz exec`
  line at a terminal first: see [Run it unattended](/user/unattended).
- **A way to sign the agent's CLI in without a browser**, stored as a repository secret: a
  token from `claude setup-token` for Claude Code, an API key for Codex. See [Sign the agent's
  CLI in](#sign-the-agent-s-cli-in).
- **Permission for the job to push a branch and open a pull request**: `contents: write` and
  `pull-requests: write`, and, on GitHub, *Allow GitHub Actions to create and approve pull
  requests* switched on in the repository's settings.

## What a runner is missing

A CI runner starts empty every time. That shapes the whole job:

| At your desk | On a fresh runner | So the job… |
| --- | --- | --- |
| `hmz` and the agent's CLI are installed | nothing is | installs both, every run |
| the CLI is signed in | it is not | signs it in from a secret |
| the official flowverse is fetched | nothing is | names the flow by its repository |
| `hmz` keeps a price list for `cost` | there is none | fetches it before the first turn |
| `/epics` reads a run back | there is no prompt | traces the run from a script |
| a stopped run can be picked up | nothing of a last run is kept | never uses `--resume` |

`hmz exec` does not open on what the interface was set up with in any directory. It uses what
the machine holds: the flowverses it has fetched, its [accounts](/user/settings#accounts), its
[fallbacks](/user/settings#fallback), any CLI added on the Accounts page of `/settings`, whether
[reporting](/user/reporting) was answered yes, and whether this directory's runs are
[profiled](/user/tracing#profiling-a-run). A fresh runner holds none of these, so on a runner
the line is the whole setup.

## Example: a nightly loop that opens a pull request

Commit this as `.github/workflows/nightly.yml`, with `TASK.md` and the
[`ci/trace.py`](#keep-a-trace) script beside it:

```yaml
name: nightly

on:
  schedule:
    - cron: "0 2 * * *"                             # ①
  workflow_dispatch:

permissions:                                        # ②
  contents: write
  pull-requests: write

jobs:
  loop:
    runs-on: ubuntu-latest
    timeout-minutes: 60                             # ③
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.0.1

      # For Kimi Code or DeepSeek Harness, install 'hmz[all]' instead.
      - name: Install the agent's CLI and humanize   # ④
        run: |
          npm install -g @anthropic-ai/claude-code
          uv venv --python 3.12 "$RUNNER_TEMP/hmz"
          uv pip install --python "$RUNNER_TEMP/hmz/bin/python" hmz
          echo "$RUNNER_TEMP/hmz/bin" >> "$GITHUB_PATH"

      - name: Run the loop                          # ⑤
        env:
          CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
        run: |
          hmz exec \
            -f 'git+https://github.com/humanfia/flowverse@main#ralph_loop' \
            -a agent=claude/claude-opus-5:high \
            -b duration=45m,cost=20 \
            "$(cat TASK.md)"

      - name: Trace the run                         # ⑥
        if: always()
        continue-on-error: true
        run: python ci/trace.py "$RUNNER_TEMP/trace.json"

      - uses: actions/upload-artifact@v5            # ⑦
        if: always()
        continue-on-error: true
        with:
          name: trace
          path: ${{ runner.temp }}/trace.json

      - uses: peter-evans/create-pull-request@v7    # ⑧
        with:
          branch: nightly/${{ github.run_id }}
          title: "nightly: what the loop did"
```

### What each part means

1. **`cron: "0 2 * * *"`** runs it at 02:00 UTC every night. `workflow_dispatch` adds a *Run
   workflow* button, which is how you try it the first time.
2. **`permissions`** gives the job's token exactly what the last step needs: to push a branch
   and open a pull request. The agents can reach this token too, so give it nothing more.
3. **`timeout-minutes: 60`** is GitHub's limit, not humanize's. Keep it well above the run's
   `duration`: the installs count against it, and the turn under way when the budget runs out
   is let finish unless the budget says `graceful=false`.
4. **Install the agent's CLI and humanize.** The CLI from npm, and humanize into an
   environment of its own whose `bin` is put on the `PATH`. Kimi Code and DeepSeek Harness
   also need the `hmz[all]` extra: see [Installation](/user/installation).
5. **Run the loop.** The same `hmz exec` line you ran by hand, with the CLI signed in from a
   secret. `-b duration=45m,cost=20` stops it at 45 minutes or $20, whichever comes first,
   and the step still exits 0: a [Ralph loop](/flows/ralph-loop) usually ends this way. A
   fresh runner has no price list, so a run with a `cost` limit fetches one before its first
   turn (at most 20 s). The `duration` still bounds the run if the model has no price.
6. **Trace the run.** `if: always()` traces a run that failed too, which is the one you most
   want to read. `continue-on-error` keeps a failed trace from failing the job.
7. **Upload the trace** as an artifact named `trace`, kept with the job.
8. **Open the pull request** with whatever the loop changed. It runs only when the loop
   succeeded, so a failed run opens nothing.

### Check that it worked

Run it once from the *Actions* tab with *Run workflow*, and read the log before you leave it to
the schedule. The *Run the loop* step shows the run as it happens, in plain lines since a job
log is not a terminal. Here is the same line run with a small model on a one-bug project,
output redirected the way a job's is, shortened:

```text
● agent is working
● Read(/home/runner/work/app/app/calc.py)
● Edit(/home/runner/work/app/app/calc.py)
● Bash(cd /home/runner/work/app/app && python -m pytest test_calc.py -v)
● Done. Changed `a - b` to `a + b` in the `add()` function, and the test passes.
✻ input 42 · output 760 · cache_read 99.0k · cache_write 8.3k · claude-haiku-4-5-20251001 · agent
✻ Worked for 10s · agent
…
hmz exec: stopped -- ralph_loop:ralph_loop: its budget's duration is spent
```

- **`● …` lines** are what the agent did, **`✻` lines** close each turn with what it spent.
- **`hmz exec: stopped -- … duration is spent`** is the budget ending the run, with the step
  green.
- **The *Trace the run* step** prints how the run ended, `the run ended: stopped`, and the
  `trace` artifact is on the run's summary page.
- **A pull request** named `nightly: what the loop did` is open, on a branch named after the
  workflow run, `nightly/<run id>`.

A run that went wrong before any agent started fails the step in seconds with exit status 2
and `hmz exec: error: …` naming why.

## Sign the agent's CLI in

humanize holds no credentials. An agent with no `@account` runs its CLI as the runner has
signed it in, so sign it in the way that CLI supports without a browser:

::: code-group

```yaml [Claude Code]
# a token from `claude setup-token`, stored as a repository secret
- name: Run the loop
  env:
    CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
  run: hmz exec -f … -a agent=claude/claude-opus-5:high …
```

```yaml [Codex]
# install @openai/codex rather than claude-code, then hand Codex's own login an API key
- name: Sign Codex in
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  run: printenv OPENAI_API_KEY | codex login --with-api-key
- name: Run the loop
  run: hmz exec -f … -a agent=codex/gpt-5.6-sol:high …
```

:::

To run agents as named [accounts](/user/settings#accounts) on the runner instead, make them from
Python with `Hmz().accounts` before the run. See the [SDK reference](/reference/sdk).

## Name the flow by its repository

A fresh runner has fetched no flowverse, so a bare `-f ralph_loop` is refused there with
`the official flowverse has not been fetched yet`. Name the flow by its repository instead, as
the workflow does:

```sh
-f 'git+https://github.com/humanfia/flowverse@main#ralph_loop'
```

Replace `main` with a commit to pin the flow, so a change upstream cannot change what runs at
night. A flow of your own needs none of this: commit it to `.humanize/flows/` and name it with
`-f <name>`.

## Keep a trace

At a terminal you get a trace from [`/epics`](/user/tracing). A runner has no prompt, so the
workflow calls the same thing from Python, with the Python humanize was installed with:

```python
# ci/trace.py
"""Trace the run that just happened, and say how it ended."""

import sys

from hmz.sdk import Hmz

epics = Hmz().epics
if runs := epics.all():  # every run in this directory, oldest first
    run = runs[-1]
    epics.traced(run, output=sys.argv[1])
    ran = epics.read(run)
    print("the run ended:", ran.how if ran and ran.how else "unfinished")
```

Run after a loop its budget stopped, it prints:

```console
$ python ci/trace.py "$RUNNER_TEMP/trace.json"
the run ended: stopped
```

`how` is `done`, `failed` or `stopped`. The trace is written outside the checkout so the pull
request does not pick it up. Download the `trace` artifact and drop it into
[ui.perfetto.dev](https://ui.perfetto.dev): a process per agent, a slice per thing it did. See
[Tracing a run](/user/tracing).

## Variations

### Read the run with a program

For a step that reads the run rather than shows it, add `--json`. `shell: bash` adds
`pipefail`, so the step fails when `hmz exec` does:

```yaml
- name: Run the loop
  shell: bash
  run: |
    hmz exec … --json "$(cat TASK.md)" \
      | tee "$RUNNER_TEMP/run.ndjson" \
      | jq -r 'select(.kind == "tool") | .text'
```

The job log then holds one line per tool call:

```text
Read /home/runner/work/app/app/calc.py
Read /home/runner/work/app/app/test_calc.py
Edit /home/runner/work/app/app/calc.py
Bash cd /home/runner/work/app/app && python -m pytest test_calc.py -v
```

```sh
# output tokens across the whole run
jq -s 'map(.spent.output // 0) | add' "$RUNNER_TEMP/run.ndjson"
```

The objects are described in [Run it unattended › Read it with a
program](/user/unattended#read-it-with-a-program).

### Colour in the job log

A job log is not a terminal, so the lines come out plain. Set `FORCE_COLOR: "1"` on the step
for colour a log viewer renders.

### Keep the line in the repository

Put the `hmz exec` line in a script, such as `ci/nightly.sh`, and call that from the workflow.
Then you can run exactly what CI runs on your own machine, and a change to the line is reviewed
like any other change.

### Another CI

Nothing but the workflow file is GitHub's. On any CI that runs a shell, the job is the same
five steps: install, sign in, `hmz exec`, `python ci/trace.py`, and keep the trace.

## Act on the exit status

| Status | Means |
| --- | --- |
| `0` | The flow returned, or its budget stopped it. |
| `1` | The run failed: the flow raised an error it did not handle. |
| `2` | Refused before any agent started: an `-a` it can't read, a role left unfilled, no `-b`, a flow that isn't there. |
| anything else | The job was cancelled: `143` for a terminate signal, `130` for an interrupt, once the run has let go of what it started. |

A `2` fails the job in seconds rather than after forty minutes.

## Pitfalls

- **Every turn fails, and the step is still green.** The CLI is not signed in. Nothing catches
  that before the run, and a loop such as Ralph loop goes on past failed turns and can still
  exit 0. Read the log of the first run by hand.
- **`nobody lists a price for …, so cost=… cannot stop what it spends`.** The model is not on
  the price list, or the runner could not fetch the list (no network, or `HUMANIZE_PRICES=off`),
  so the `cost` limit never fills. Keep a `duration` or `output_tokens` limit beside it, as the
  workflow does.
- **`--resume` is refused with status 2.** The runs a flow picks up from are kept on the
  machine that ran them, and a runner starts empty every night. Leave `--resume` off in CI.
- **The job is killed before the loop ends.** `timeout-minutes` is below the run's
  `duration` plus the installs. Raise it.
- **No pull request appears.** The loop failed, so the step was skipped; or the repository
  does not allow GitHub Actions to create pull requests.

More in [Troubleshooting](/user/troubleshooting).

## Next steps

- [Run it unattended](/user/unattended): every part of the `hmz exec` line
- [Tracing a run](/user/tracing): reading the trace the job keeps
- [Accounts](/user/settings#accounts): running an agent as a named account
- [Permissions](/user/permissions): what the agents may touch on the runner
- [CLI reference](/reference/cli) and [SDK reference](/reference/sdk)

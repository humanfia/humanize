# humanize in CI

Run a flow from a scheduled job, open a pull request with what it changed, and keep a trace of
what each agent did. The workflow below is GitHub Actions; everything else on this page works
on any CI that can run a shell.

## Try it

Commit a `TASK.md` saying what the loop should work on and the [`ci/trace.py`](#keep-a-trace)
script below, add the secret your agent's CLI signs in with, and add this workflow:

```yaml{30-38}
# .github/workflows/nightly.yml
name: nightly

on:
  schedule:
    - cron: "0 2 * * *"
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  loop:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.0.1

      # For Kimi Code or DeepSeek Harness, install 'hmz[all] @ git+https://…' instead.
      - name: Install the agent's CLI and humanize
        run: |
          npm install -g @anthropic-ai/claude-code
          uv venv --python 3.12 "$RUNNER_TEMP/hmz"
          uv pip install --python "$RUNNER_TEMP/hmz/bin/python" \
            git+https://github.com/humanfia/humanize.git
          echo "$RUNNER_TEMP/hmz/bin" >> "$GITHUB_PATH"

      - name: Run the loop
        env:
          CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
        run: |
          hmz exec \
            -f 'git+https://github.com/humanfia/flowverse@main#ralph_loop' \
            -a agent=claude/claude-opus-5:high \
            -b duration=45m,cost=10 \
            "$(cat TASK.md)"

      - name: Trace the run
        if: always()
        continue-on-error: true
        run: python ci/trace.py "$RUNNER_TEMP/trace.json"

      - uses: actions/upload-artifact@v5
        if: always()
        continue-on-error: true
        with:
          name: trace
          path: ${{ runner.temp }}/trace.json

      - uses: peter-evans/create-pull-request@v7
        with:
          branch: nightly/${{ github.run_id }}
          title: "nightly: what the loop did"
```

The highlighted step is the run itself: the same `hmz exec` line you would type at a terminal,
explained in [Run it unattended](/user/unattended). The rest of this page goes through the
steps around it.

::: warning The agents run unsupervised, with the job's access
A flow's agents run with approvals bypassed, and on a runner they can reach whatever the job
can: its token, its secrets, the network. Give the job only the `permissions` and secrets it
needs. See [Permissions](/user/permissions).
:::

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

A CLI that is not signed in is not caught before the run: each turn fails, and a loop such as
Ralph loop goes on past failed turns and can still exit 0. Run the job by hand once and read
its log before you leave it to the schedule.

To run agents as named [accounts](/user/providers) on the runner instead, make them from
Python with `Hmz().accounts` before the run. See the [SDK reference](/reference/sdk).

## Name the flow by its repository

A fresh runner has fetched no flowverse, so a bare `-f ralph_loop` is refused there. Name the
flow by its repository instead, as the workflow does:

```sh
-f 'git+https://github.com/humanfia/flowverse@main#ralph_loop'
```

Replace `main` with a commit to pin the flow, so a change upstream cannot change what runs at
night. A flow of your own needs none of this: commit it to `.humanize/flows/` and name it with
`-f <name>`.

::: tip The line is the whole setup
`hmz exec` does not open on what the interface was set up with in this directory. It still uses
what the machine holds: the flowverses it has fetched, its [accounts](/user/providers), its
[fallbacks](/user/fallback) and any CLI added at `/providers`, and it reads whether
[reporting](/user/reporting) was answered yes and whether this directory's runs are
[profiled](/user/tracing#profiling-a-run). A fresh runner holds none of these.
:::

## Bound the run twice

`-b duration=45m,cost=10` is humanize's limit: whichever is reached first stops the run, and
the step still exits 0. A [Ralph loop](/flows/ralph-loop) usually ends this way.
`timeout-minutes` is GitHub's. Keep it well above the duration: the installs count against it,
and the turn under way when the budget runs out is let finish unless the budget says
`graceful=false`.

## Read the job log

The job log shows the run as it happens: which agent is working, what it says, the tools it
runs, and what each turn cost. A job log is not a terminal, so the lines come out plain. Set
`FORCE_COLOR: "1"` on the step for colour a log viewer renders.

For a step that reads the run rather than shows it, add `--json`:

```yaml
- name: Run the loop
  shell: bash # adds pipefail: the step fails when hmz exec does
  run: |
    hmz exec … --json "$(cat TASK.md)" \
      | tee "$RUNNER_TEMP/run.ndjson" \
      | jq -r 'select(.kind == "tool") | .text'
```

```sh
# output tokens across the whole run
jq -s 'map(.spent.output // 0) | add' "$RUNNER_TEMP/run.ndjson"
```

The objects are described in [Run it unattended › Read it with a
program](/user/unattended#read-it-with-a-program).

## Keep a trace

At a terminal you get a trace from [`/epics`](/user/tracing). A runner has no prompt, so the
workflow calls the same thing from Python:

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

The workflow runs it with the Python humanize was installed with, and writes the trace outside
the checkout so the pull request does not pick it up. Download the `trace` artifact and drop it
into [ui.perfetto.dev](https://ui.perfetto.dev): a process per agent, a slice per thing it
did. See [Tracing a run](/user/tracing).

## Act on the exit status

| Status | Means |
| --- | --- |
| `0` | The flow returned, or its budget stopped it. |
| `1` | The run failed: the flow raised an error it did not handle. |
| `2` | Refused before any agent started: an `-a` it can't read, a role left unfilled, no `-b`, a flow that isn't there. |
| `130` | Interrupted. |

A `2` fails the job in seconds rather than after forty minutes. The pull request step runs only
when the loop succeeded, so a failed run opens nothing.

::: tip Keep the line in the repository
Put the `hmz exec` line in a script, such as `ci/nightly.sh`, and call that from the workflow.
Then you can run exactly what CI runs on your own machine, and a change to the line is reviewed
like any other change.
:::

::: details `--resume` on a fresh runner
The runs a flow picks up from are kept on the machine that ran them, so on a runner that starts
empty every night, `--resume` has nothing to pick up and the line is refused with status 2.
Leave it off in CI.
:::

## See also

- [Run it unattended](/user/unattended)
- [Tracing a run](/user/tracing)
- [Providers](/user/providers)
- [Permissions](/user/permissions)

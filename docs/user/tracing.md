<script setup>
import TraceMock from '../.vitepress/theme/components/user-after/TraceMock.vue'
</script>

# Tracing a run

A trace draws one run as a timeline you open in [Perfetto](https://ui.perfetto.dev): each
agent's sessions in rows, a slice per thing it did, with the prompts and tool output attached.
Reach for it after a long run, to see what each agent did and where the time went.

## Try it

1. In the project you ran in, type `/epics`. Every run here is listed, newest first.
2. Move to the run with <kbd>↑</kbd> <kbd>↓</kbd>, or press <kbd>s</kbd> to search what each
   run was asked to do, and press <kbd>enter</kbd>.
3. Choose **export it**. humanize gathers the trace and packs the run into an archive, then
   says what it wrote under the list.
4. Open [ui.perfetto.dev](https://ui.perfetto.dev) and drop in `traces/export.trace.json` from
   the run's directory, which is the path at the top of the run's sheet. Nothing is uploaded:
   Perfetto reads the file in your browser.

![/epics listing two runs, going into the newest, and exporting it: the archive's path, its
size, and 1 session, 10 slices, 3 programs](/demo/epics.gif)

The line under the list reads like this:

```text
/home/you/code/.humanize/20260809T014455.212Z-9f21ab.epic.tar.gz · 812 kB · 3 sessions, 412 slices
```

That is the archive, its size, and what went into the trace. The same trace is inside the
archive, so whoever you [send it to](/user/export) can open it too. `chrome://tracing`, or
anything else that reads a Chrome JSON trace, opens it as well.

## What you see

<TraceMock />

| Part | Is |
| --- | --- |
| a **process** | one agent of the run, named after its role, with how many [sessions](/user/concepts#session) it opened |
| a **track** | a row of that agent's sessions: `main` for its own, `subagent` for agents its turns started, with their kind after it when the row holds one kind. Sessions that never overlap share a row. |
| a **slice** | one thing the agent did: a tool call, a message, time spent reasoning |

Click a slice to see its arguments: the prompt, the reasoning, the tool's input and output, as
much as the CLI logged.

On a first trace, look for:

- **A gap on every track.** No agent was working: the flow was between turns.
- **One very wide slice.** A single tool call that took minutes, usually a test suite.
- **A reviewer that only starts when the actor stops.** The loop taking turns, as designed.
- **Slices back to back on one `main` track.** A Ralph loop: a fresh session every round.

A trace shows what the agents did, not what it cost. For tokens and money, see
[Cost and rate](/user/tally).

## Every run is kept {#what-a-run-writes-down}

humanize keeps a record of every run of a flow, called an **epic**, whether the run finished or
not. `/epics` lists them for the directory you are in: when each ran, which flow, what it was
asked to do, how many sessions it opened, and how it ended if it did not finish.

A run ends one of three ways: **done**, **failed**, or **stopped**, which covers a
[stop by hand](/user/stopping), <kbd>ctrl+c</kbd>, and a spent budget. **Enter** goes into a
run, where you can [export it](/user/export) or, for a flow that can be picked up, [resume
it](/user/resuming). Carrying a run on starts a new run, with its own sessions and trace.

::: details Read one session's own log
Each session a run opened is linked from the `sessions/` folder in the run's directory, under a
name that says whose it was, which CLI took its turns and which account they ran as. The link
points at the log the CLI itself wrote:

![ls of one run's directory, then of its sessions/ folder, holding a link named
fixer-claude@local-… to Claude Code's own log](/demo/run-linked.png)

The links only work on this machine. To send a run elsewhere, [export it](/user/export).
:::

## Profile the programs too {#profiling-a-run}

An agent's turn is mostly other programs: the tests, the build, the greps. A CLI logs the tool
call, not the processes it started. Turn on **profile** on the second page of
[`/settings`](/user/settings) and every run in this directory also records each program its
agents ran, what started it, and how long it took.

![the /settings page for this directory, with the profile row switched on beside workspace,
flow and forget](/demo/profiling.png)

A trace of a profiled run shows each program as a process of its own, on the same clock as the
sessions, and its summary counts them: `3 sessions, 412 slices, 61 programs`.

<TraceMock profiled />

It is off until you turn it on, it holds from the next run, and it covers runs `hmz exec`
starts in this directory too.

## Which CLIs a trace can read

A trace reads each CLI's own logs, so it holds the sessions of every built-in CLI but one:

| CLI | In a trace |
| --- | --- |
| Claude Code, Codex, Antigravity, DeepSeek Harness, Grok Build, Kimi Code, pi, Qwen Code, opencode, mimocode, ZCode | <Badge type="tip" text="yes" /> |
| Cursor Agent | <Badge type="warning" text="no" /> Watch it live on [`/monitor`](/user/monitor) instead. |

::: details `0 sessions, 0 slices`
The run opened no session before it ended, its agents ran on Cursor Agent, or the CLI's logs
have been moved or deleted since. See [Troubleshooting](/user/troubleshooting).
:::

::: details Trace sessions no run opened
Your own sessions with a coding agent, outside any flow, are not in `/epics`. Trace them by id
from Python:

```python
from hmz.sdk import Hmz

Hmz().epics.trace(
    sessions=["0a1b2c3d"],  # the start of an id is enough
    output="trace.json",
    start="3 days ago",     # anything dateparser understands
)
```

See [SDK reference](/reference/sdk) and the [Tracing reference](/reference/tracing).
:::

## See also

- [Exporting a run](/user/export): the whole run as one archive, to send to someone else
- [Picking a run up](/user/resuming)
- [`/monitor`](/user/monitor): the same shape, live, while the run goes
- [Tracing reference](/reference/tracing)

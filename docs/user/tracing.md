<script setup>
import TraceMock from '../.vitepress/theme/components/user-after/TraceMock.vue'
</script>

# Tracing a run

Open one run as a timeline in [Perfetto](https://ui.perfetto.dev): each agent's sessions in
rows, a slice for every thing it did, with the prompts and tool output attached. Use this
after a long run, to see what each agent did, in what order, and where the time went. By the
end of this page you will have found a run, exported its trace and read it.

## Try it

1. In the project you ran in, type `/epics`. Every run here is listed, newest first.
2. Move to the run with <kbd>↑</kbd> <kbd>↓</kbd> and press <kbd>enter</kbd>. In a long list,
   press <kbd>/</kbd> first (or the **Search…** button) and type part of the run's flow, task
   or name to narrow it.
3. Choose **export run**. humanize gathers the trace and packs the run into an archive, then
   says what it wrote under the list.
4. Open [ui.perfetto.dev](https://ui.perfetto.dev) and drop in `traces/export.trace.json` from
   the archive. Nothing is uploaded: Perfetto reads the file in your browser.

<HmzCast name="epics" alt="/epics listing two runs, going into the newest, and exporting it: the archive's path, its size, and 1 session, 10 slices, 3 programs" />

## Before you start

- A run of a flow in this directory. `/epics` lists the runs of the directory `hmz` was
  started in, finished or not.
- A browser, for Perfetto. `chrome://tracing`, or anything else that reads a Chrome JSON
  trace, opens it as well.
- Agents on a CLI whose logs a trace can read: every built-in CLI but Cursor Agent (see
  [Which CLIs a trace can read](#which-clis-a-trace-can-read)).

## Every run is kept {#what-a-run-writes-down}

humanize keeps a record of every run of a flow, called an **epic**, whether the run finished or
not. `/epics` lists them for the directory you are in: when each ran, which flow, what it was
asked to do, how many sessions it opened, and how it ended if it did not finish.

A run ends one of three ways: **done**, **failed**, or **stopped**, which covers a
[stop by hand](/user/stopping), <kbd>ctrl+c</kbd>, and a spent budget. <kbd>enter</kbd> goes
into a run, where you can [export it](/user/export) or, for a flow that can be picked up,
[resume it](/user/resuming). Carrying a run on starts a new run, with its own sessions and
trace.

A **trace** is built from that record and from each agent's own log of its sessions. It is
gathered when you export, so it covers the run as it stands then.

## Example: read the trace of a Ralph loop

A [Ralph loop](/flows/ralph-loop) ran three rounds on a small project, each round a fresh
session of Claude Code. Its `/epics` list:

```text
  hmz › Epics
  Every run of a flow in this directory, newest first: task, status, and
  session count.

  ╭──────────────────────────────────────────────────────────────────────────╮
  │ 2026-09-30 05:38 · ralph_loop Make the tests in test_slug.py pass. Change│
  │                               slug.py only. · 1 session · stopped ·      │
  │                               resumable                                  │
  │ 2026-09-30 05:37 · ralph_loop Make the tests in test_slug.py pass. Change│
  │                               slug.py only. · 3 sessions · stopped ·     │  ①
  │                               resumable                                  │
  ╰──────────────────────────────────────────────────────────────────────────╯

  Search…                                                                       ②

  enter open   / search   tab actions   esc close
```

<kbd>↓</kbd> to the second run, <kbd>enter</kbd>, **export run**, and say where it goes
([Exporting a run](/user/export)):

```text
   /tmp/hmzdocs-C/app/issues/20260930T053725.504Z-a3d685.epic.tar.gz · 162 kB · 3 sessions, 53 slices
                                                                                    ③           ④
```

Unpack the archive and drop its `traces/export.trace.json` into Perfetto. Laid out the way
Perfetto lays out a trace, it looks like this:

<TraceMock />

### What each part means

1. **`3 sessions · stopped`**: three rounds of a Ralph loop are three sessions, and the run was
   stopped by its budget. The row ends in `resumable` when the flow can be picked up.
2. **Search…** narrows the list as you type, by flow, task or run name, for a directory with a
   long history. <kbd>/</kbd> opens it too, and <kbd>esc</kbd> clears it.
3. **`3 sessions`**: every session the run opened and a trace could read. The same figure as
   the list, unless an agent ran on a CLI a trace cannot read.
4. **`53 slices`**: the things the agents did, across those sessions.

And in Perfetto:

| Part | Is |
| --- | --- |
| a **process** | one agent of the run: its role, its model (and its effort, where the CLI logs one) and how many [sessions](/user/concepts#session) it opened, as `agent · claude-haiku-4-5-20251001 · 3 sessions` |
| a **track** | a row of that agent's sessions: `main` for its own, `subagent` for agents its turns started, with their kind after it when the row holds one kind. Sessions that never overlap share a row. |
| a **slice** | one thing the agent did: its session and each turn, and inside a turn a tool call (`Read: …/test_slug.py`, `Bash: python -m pytest test_slug.py -v`), a message (`say: …`), time spent reasoning (`think: …`) or waiting on the model (`generate`) |

Click a slice to see its arguments: the prompt, the reasoning, the tool's input and output, as
much as the CLI logged.

## Check that it worked

- **The summary line has sessions in it.** `0 sessions, 0 slices` means the trace is empty;
  see [If it goes wrong](#if-it-goes-wrong).
- **Perfetto shows one process per agent**, each named after its role and model, with as
  many sessions as `/epics` counted.
- **The slices read like the transcript.** The first tool calls of the first session are the
  first things the agent did in the run.

## What to look for

On a first trace, look for:

- **A gap on every track.** No agent was working: the flow was between turns.
- **One very wide slice.** A single tool call that took minutes, usually a test suite.
- **A reviewer that only starts when the actor stops.** The loop taking turns, as designed.
- **Slices back to back on one `main` track.** A Ralph loop: a fresh session every round.

A trace shows what the agents did, not what it cost. For tokens and money, see
[Cost and rate](/user/tally).

## Profile the programs too {#profiling-a-run}

An agent's turn is mostly other programs: the tests, the build, the greps. A CLI logs the tool
call, not the processes it started. Profile a run and it also records each program its agents
ran, what started it, and how long it took. Like the budget, it is a choice about a run, made
where the budget is:

```text
  hmz › /flow › Installed › ralph_loop                            ● unsaved changes
  Configure each role: an agent (CLI, account, model and effort) or an environment;
  then what the flow takes and what a run may spend.

  ╭──────────────────────────────────────────────────────────────────────────────╮
  │ agent                                           claude/claude-opus-5-5:high ▸ │
  │   agent                                                                      │
  │──────────────────────────────────────────────────────────────────────────────│
  │ budget                                                                 set ▸ │
  │   what a run may spend: stops at 20m, $0.50                                  │
  │──────────────────────────────────────────────────────────────────────────────│
  │ profiling                                                             ● on ▾ │  ①
  │   samples the programs agents start                                          │
  ╰──────────────────────────────────────────────────────────────────────────────╯

                                                                          Save  ②

  enter choose   tab actions   esc back
```

1. **`profiling`**, just under `budget` on [`/flow`](/reference/tui#roles-page): a switch.
   <kbd>enter</kbd> drops `on` and `off` under it, the cursor already on the other one, so
   <kbd>enter</kbd> twice turns it round. It is off until you turn it on.
2. **Save**: kept with the rest of the flow's setup in this directory, so the next run of the
   flow here is profiled too until you turn it off.

From the command line, add `--profile` to [`hmz exec`](/reference/cli#exec-profile); from
Python, `profile=True` to [`Hmz().run`](/reference/sdk#hmz-run).

A trace of a profiled run shows each program as a process of its own, on the same clock as the
sessions, and its summary counts them. The same Ralph loop, resumed once profiling was on:

```text
/tmp/hmzdocs-C/app/issues/20260930T054014.242Z-bdae4a.epic.tar.gz · 59 kB · 1 session, 13 slices, 7 programs
```

<TraceMock profiled />

A run already going is not profiled halfway through, and `/resume` profiles the run it picks
up exactly as the run it goes on from was. An `hmz exec` line is profiled only when it says
`--profile`.

## Which CLIs a trace can read

A trace reads each CLI's own logs, where the run kept them, so it holds the sessions of every
built-in CLI but one:

| CLI | In a trace |
| --- | --- |
| Claude Code, Codex, Antigravity, DeepSeek Harness, Grok Build, Kimi Code, MiniMax Code, pi, Qwen Code, opencode, mimocode | <Badge type="tip" text="yes" /> |
| Cursor Agent | <Badge type="warning" text="no" /> Watch it live on [the monitor](/user/monitor) instead. |

## Variations

::: details Read one session's own log
Each session a run opened is kept in the `sessions/` folder in the run's directory, a folder
per CLI laid out as that CLI lays out its home: Claude Code's are under
`sessions/claude/projects/`. It is the only copy -- the CLI wrote it there, not into its own
home, and resumes it from there -- so the run is the one place to look, and nothing a run did
shows up among the conversations you had with the CLI yourself.

![ls of one run's directory, then every file under its sessions/ folder: one Claude Code
transcript, under sessions/claude/projects/](/demo/run-kept.png)

To send a run elsewhere, [export it](/user/export).
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

## If it goes wrong

- **`… · 0 sessions, 0 slices`.** The run opened no session before it ended, its agents ran
  on Cursor Agent, or the CLI's logs have been moved or deleted since. See
  [Troubleshooting](/user/troubleshooting#_0-sessions-0-slices).
- **Fewer sessions in the trace than `/epics` counted.** Some agents ran on Cursor Agent,
  which a trace cannot read. Everything else is still there.
- **No programs in a profiled trace.** The run was started before profiling was turned on, or
  by an `hmz exec` line without `--profile`. Run the flow again with it on.

## Next steps

- [Exporting a run](/user/export): the whole run as one archive, to send to someone else
- [Picking a run up](/user/resuming)
- [The monitor](/user/monitor): the same shape, live, while the run goes
- [Tracing reference](/reference/tracing)

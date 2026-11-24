---
title: Trace a run with Exomyth
description: Profile an epic, then read where its time and tokens went on a timeline, a flame graph and a table.
---

# Trace a run with Exomyth

Exomyth is the trace viewer for an epic. It draws every flow call, session, turn, model call and tool call on one timeline, and sums them in a flame graph and a table.

![Exomyth in Humanize Desktop: the timeline of an epic with a tool call picked and its arguments in the side panel](/shots/user-tracing-timeline.svg)

## What a trace holds

Every epic records a trace by default. Flow calls come from the epic record, and turns, model calls and tool calls come from the coding agents' session logs.

Two profiling switches add sampling data to the trace:

| Switch | Flag of `hmz exec` | What it adds |
| --- | --- | --- |
| Profile flow | `--profile-flow` | Call stacks of the flow's Python code, sampled every 1 ms. Shows as a `python` process under the flow. |
| Profile environment | `--profile-environment` | Programs the agents start, sampled every 50 ms. Each program shows as a process with one row per thread. |

![The epic record and the session logs are always in a trace; the flow profile and the environment profile only when switched on; Exomyth and a Chrome trace file are made from them](/diagrams/user-tracing-1.svg)

Profiling only samples. It cannot stop or fail an epic.

## Turn profiling on

Set the profiling switches when you [start an epic](/user/epics). They apply to that epic alone.

### In the app {#profile-in-the-app}

On **New epic**, tick **Profile flow**, **Profile environment** or both, then start the epic.

![The New epic page with Profile flow and Profile environment ticked under the budget](/shots/user-tracing-switches.svg)

### In the terminal {#profile-in-the-terminal}

1. Type `/flow` followed by the flow's name.
2. Select `profile flow` or `profile environment` and press <kbd>enter</kbd> twice to set it to `On`. A switch that is off reads `traced only`.
3. Choose **Save**.

![The page of a flow in the terminal with both profiling rows on](/shots/user-tracing-terminal-switches.svg)

### From the command line {#profile-from-the-command-line}

Pass `--profile-flow` or `--profile-environment` to `hmz exec`:

```sh
hmz exec -f rlar \
  -a actor=claude/claude-haiku-4-5 -a reviewer=claude/claude-haiku-4-5 \
  -p budget.output_tokens=20000 \
  --profile-flow --profile-environment \
  "Add a discount code to checkout"
```

![The output of hmz exec for a run started with both profiling flags](/shots/user-tracing-exec.svg)

The terminal output does not change. The profiles are saved in the epic for you to read in Exomyth.

## Read a trace in the app {#in-the-app}

Open an epic and click the **Exomyth** icon in the top bar, or open the epic's menu in the sidebar and choose **Exomyth**. If the epic is still running, the page refreshes every 2 seconds.

![An ended epic in Humanize Desktop with the pointer on the Exomyth icon of its top bar](/shots/user-tracing-open.svg)

The top bar shows the epic's state, process count, span count and duration. Below it are the **Timeline** and **Flame** tabs. Click **Copy link** to copy the address of the current view.

### The timeline

Each process is a block of rows. The flow sits at the top, followed by `python` if you profiled the flow, then each session under the process that started it, and finally any profiled programs. Each span is a bar coloured by category: `flow`, `session`, `turn`, `llm`, `tool`, `message`, `event` or `process`. A profiled flow adds `sample` spans: the Python frames it was sampled in.

| To do this | Do this |
| --- | --- |
| See a span in brief | Point at it. |
| Pick a span or a process | Click the span, or the process's name. |
| Zoom in and out | <kbd>w</kbd> and <kbd>s</kbd>, <kbd>ctrl</kbd> or <kbd>cmd</kbd> and the wheel, or pinch. |
| Pan | <kbd>a</kbd> and <kbd>d</kbd>, <kbd>shift</kbd> and the wheel, or a sideways wheel. |
| Scroll through the processes | The wheel. |
| Zoom to what is picked | <kbd>f</kbd>, or double-click a span. |
| Show the whole epic | <kbd>0</kbd>, <kbd>home</kbd> or **Reset**. |
| Fold one process | Click the caret beside its name, or double-click the name's column. |
| Fold or unfold every process | **Collapse** and **Expand**. |
| Pick a stretch of time | Drag across the chart. |
| Let go of what is picked | <kbd>esc</kbd>. |

Right-click the chart for **Zoom**, **Pick**, **Expand**, **Collapse** and **Reset**.

### The details panel

The right-hand panel describes your selection.

| Picked | What the panel shows |
| --- | --- |
| Nothing | The epic's name, state, start time, duration, spans and processes, followed by a breakdown by category (spans, time, tokens in and out) and the process list. Click a process in the list to pick it. |
| A process | Its kind, agent, role, backend, model, parent, start and duration. |
| A span | Its category, start, duration, model, tokens, process and track. **Arguments** shows the call payload, such as a tool's input and output. |
| A stretch of time | Start, end, duration, the spans and tokens inside it, and the breakdown by category. |

Click **Zoom** to fit the chart to your selection. Click **Clear** to drop a stretch of time.

![A stretch of time dragged across the reviewer's turn, summed by category in the side panel](/shots/user-tracing-range.svg)

*Drag across the chart to sum a stretch of time.*

### Find a span

Press <kbd>/</kbd> or click **Find** and type part of a span name. The counter shows the match position, such as `1/2`. On the **Flame** tab it shows a percentage instead: the share of the graph the matching frames hold. Press <kbd>enter</kbd> in the box, <kbd>n</kbd> outside it, or click **Next** for the next match. Press <kbd>shift+enter</kbd> in the box, <kbd>shift+n</kbd> outside it, or click **Previous** for the previous one. On the timeline, each match is selected and scrolled into view; on the **Flame** tab the matching frames are only lit. Press <kbd>esc</kbd> to clear the search, and press <kbd>esc</kbd> again to leave the box.

### The flame graph and the slices

Click **Flame** to sum the whole epic or the stretch of time selected on the timeline. Stacks nest from the epic to the agent, flow or program, and then through its spans.

![The Flame tab: a flame graph of the whole epic over the Slices table](/shots/user-tracing-flame.svg)

| Control | What it does |
| --- | --- |
| **Time**, **Tokens in**, **Tokens out**, **Count** | Sets what frame width measures. |
| **Merge sessions** | Groups all sessions of an agent into one frame when on (the default), or keeps each session separate when off. |
| **Bottom up** | Places the root at the bottom of the graph. |

Click a frame to zoom in. Click the trail above the graph or press <kbd>esc</kbd> to zoom out. Point at a frame to see its total, self value, share of the graph and span count.

The **Slices** table below lists up to 200 span names with their Name, Category, Count, Total, Self, Avg, P50, P95, Max, In and Out. Click a column heading to sort. Click a row and then **Show in timeline** to jump to the timeline with that name in **Find**.

## Read a trace in the terminal {#in-the-terminal}

Type `/epics`, press <kbd>enter</kbd> on an epic and choose `Exomyth`; the epic's `Graph` page has an `Exomyth` button too. On the monitor of a running epic, press <kbd>ctrl+e</kbd> or click `Exomyth`; the trace refreshes every 3 seconds.

![Exomyth in the terminal: the timeline with a tool call under the cursor and its pane open](/shots/user-tracing-terminal.svg)

Press <kbd>tab</kbd> and <kbd>shift+tab</kbd> to cycle through the three views: timeline, flame and slices.

![The three views of Exomyth in the terminal in turn: the timeline, the flame view and the slices table](/shots/user-tracing-terminal-views.svg)

| View | Key | What it does |
| --- | --- | --- |
| Timeline | <kbd>↑</kbd> <kbd>↓</kbd> | Move one row. <kbd>pageup</kbd> and <kbd>pagedown</kbd> move ten. |
| Timeline | <kbd>←</kbd> <kbd>→</kbd> | Move to the previous or next span. |
| Timeline | <kbd>w</kbd> <kbd>+</kbd> <kbd>=</kbd> and <kbd>s</kbd> <kbd>-</kbd> | Zoom in and out around the cursor. |
| Timeline | <kbd>a</kbd> <kbd>shift+←</kbd> and <kbd>d</kbd> <kbd>shift+→</kbd> | Pan. |
| Timeline | <kbd>enter</kbd> | Open the span pane (name, process, timing, tokens and arguments). |
| Timeline | <kbd>p</kbd> | Open the process pane. |
| Timeline | <kbd>v</kbd> | Start a time stretch at this span, move the cursor to extend it, press <kbd>v</kbd> to hold it, and press <kbd>v</kbd> again to drop it. The pane sums the stretch by category. |
| Timeline | <kbd>f</kbd> | Fit the view to the stretch or span. |
| Timeline | <kbd>0</kbd> | Show the whole epic. |
| Timeline | <kbd>space</kbd> | Fold or unfold the process. |
| Timeline | <kbd>/</kbd> | Search for a span by name. <kbd>n</kbd> and <kbd>N</kbd> jump to the next and previous match. |
| Flame | <kbd>↑</kbd> <kbd>↓</kbd> | Move through the stacks. |
| Flame | <kbd>t</kbd> | Cycle the weight: time, tokens in, tokens out, count. |
| Flame | <kbd>m</kbd> | Toggle merging sessions. |
| Slices | <kbd>↑</kbd> <kbd>↓</kbd> | Move through the slices. |
| Slices | <kbd>o</kbd> and <kbd>O</kbd> | Sort by the next column, or reverse the sort order. |
| Slices | <kbd>enter</kbd> | Jump to that slice's spans on the timeline. |
| All | <kbd>r</kbd> | Reload the epic. |
| All | <kbd>esc</kbd> | Close the search box, stretch, pane or Exomyth, in that order. |

The flame view and slices table measure the selected stretch of time, or the visible timeline when no stretch is selected.

## Read a trace from the command line {#from-the-command-line}

`hmz runs timeline NAME` prints what Exomyth draws: one line per process, and under it one line per track with its span count. `NAME` is the epic's name, as `hmz runs list` prints it.

```console
$ hmz runs timeline 20261012T091500.123Z-1a2b3c --spans
$ hmz runs span 20261012T091500.123Z-1a2b3c 42
```

| Command | What it does |
| --- | --- |
| `hmz runs timeline NAME` | Prints the processes and tracks, with start and end in seconds. |
| `--spans` | Also prints every span under its track: id, start, duration, category, name. |
| `hmz runs span NAME ID` | Prints one span whole, with what it carried: a model call's prompt and answer, a tool call's input and output. |
| `hmz runs trace NAME` | Prints each session and its actions in order, without the layout. |

Span ids hold for one layout of the timeline. While an epic runs, it is laid out again on each read; pass `--layout` with the `layout` of the timeline you read the id from, and the daemon refuses if it has changed. Add `--json` for the whole document. See [The hmz command](/reference/cli#hmz-runs).

## Export a Chrome trace

You can export a trace as a Chrome JSON file to open in Perfetto or `chrome://tracing`.

In the terminal, type `/epics`, press <kbd>enter</kbd> on an epic and choose `Export`. Humanize writes the trace to `traces/export.trace.json` inside the epic and packs it into the archive. See [Export and import a run](/user/export).

In Python, gather the trace of the latest epic in the current folder:

```python
from hmz.sdk import Hmz

epics = Hmz().epics
where, trace = epics.traced(epics.all()[-1])
print(where)
```

Each call writes a timestamped file under `traces/` in the epic, keeping earlier exports intact. See [The Python SDK](/builder/sdk).

In the app, **Export** packs only the trace files the epic already has. It does not gather a new one.

## Supported coding agents

Traces read session logs from `agy`, `claude`, `codex`, `dsh`, `grok`, `kimi`, `litellm`, `mcode`, `mimo`, `omp`, `opencode`, `pi` and `qwen`. Because `cursor-agent` does not write a readable log, its sessions do not appear. See [Coding agents](/user/agents).

## Good to know

- Only epics have Exomyth. Chats do not.
- The app and terminal remember the two profiling switches per flow and folder. `hmz exec` ignores those saved settings and profiles only when you pass the flags.
- The flow profile is written when the epic ends. The environment profile is written as each program runs.
- The environment profile holds only programs started after the epic began. A program already running when the epic starts, and anything that program starts later, is left out.
- An unreadable agent log omits that agent without failing the trace.
- In the terminal, the span pane shows at most 12 arguments, the flame view draws 6 levels and 400 stacks, and the slices table lists at most 400 rows.
- See [Trace formats](/reference/tracing) for file formats, and [Terminal commands and keys](/reference/tui) and [Page addresses and shortcuts](/reference/web) for all shortcuts.

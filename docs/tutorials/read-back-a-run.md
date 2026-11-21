---
title: Read back, export and share a run
description: Open a finished epic, read what each agent did, inspect its trace and cost, then export it as a file and back it up to a git repository.
---

# Read back, export and share a run

An epic records one full run of a flow. In this tutorial you open a finished epic, read what its agents did, inspect its trace and cost, export and import it as a file, and back it up to a git repository.

![A finished epic open in Humanize Desktop: the flow graph in the middle, figures on the right](/shots/tutorials-read-back-a-run-epic.svg)

## What you need

- Humanize Desktop, or the browser page from `hmz web`.
- One finished epic. If you have none, complete [Finish your first task in Humanize Desktop](/tutorials/first-task-desktop) first.
- An empty private git repository that your local `git` can push to, for the last two steps.

## 1. Open the epic and read a session

1. Click the epic under its folder in the sidebar. Each row shows the task, outcome, and flow. The flow graph opens with one box per agent and its sessions below. The right panel shows what the epic spent and how long it took.
2. Click a session row in an agent box. The transcript opens and shows every prompt, tool call, and answer.
3. Click the task in the top bar to return to the graph.

![Reel: the epic is clicked in the sidebar, then a session in the graph, and its transcript opens](/shots/tutorials-read-back-a-run-session.svg)

*From the sidebar to one session's transcript.*

## 2. Open the trace

Exomyth is the epic trace viewer. It draws the flow, every session, and every tool call on one time axis.

1. Click the **Exomyth** chart icon in the epic bar.
2. On the **Timeline** tab, click a span. The right panel shows its category, start, duration, and arguments.
3. Drag across the chart to pick a time range. Press <kbd>0</kbd> to reset the view, or <kbd>/</kbd> to search for a span by name.

![The Exomyth timeline with a tool call picked: its duration and arguments are in the panel on the right](/shots/tutorials-read-back-a-run-trace.svg)

*Each row is a process: the flow first, then one per session.*

## 3. See where the time and tokens went

1. Click the **Flame** tab. The flame graph stacks the epic, each agent, its turns, model calls, and tools. Width represents time.
2. Change the weight to **Tokens in**, **Tokens out**, or **Count** to resize spans by that metric.
3. Read the **Slices** table below the graph. Each row lists a span name with its count, total, average, and maximum. Click a column header to sort.

![The Flame tab: a flame graph of the whole epic, and the Slices table under it](/shots/tutorials-read-back-a-run-flame.svg)

## 4. Check usage

The epic's right panel shows its own cost. To view total spending across runs:

1. Click the **Settings** gear icon at the bottom of the sidebar.
2. Open **Usage**.
3. Pick a range: `7d`, `30d`, `90d`, or `365d`. Pick one workdir, or keep **All workdirs**.

**Cost by day** charts daily spending. **By flow** lists the epics, cost, output tokens, and time for each flow.

![The Usage page of the settings: totals for the range, cost by day, and a table by flow](/shots/tutorials-read-back-a-run-usage.svg)

*The model in this picture has no list price, so nothing is charted.*

## 5. Export the epic

Click the **Export** download icon in the epic bar.

![The bar of an epic with the pointer on the Export icon](/shots/tutorials-read-back-a-run-export.svg)

Humanize creates a file named after the epic ending in `.hmzepic`. Humanize Desktop saves and reveals it in your Downloads folder; a browser downloads it directly.

The archive contains the epic record and every session log, which is what the graph and the trace are drawn from. Humanize replaces recognized credentials with `[redacted]`, but keeps all prompts and answers. Review the contents before sharing the file.

::: tip
**Export** appears only when the epic is no longer running.
:::

## 6. Import it on another machine

Copy the file to another machine and open Humanize.

1. Click **Search** in the sidebar.
2. Under **Actions**, click **Import** and pick the `.hmzepic` file.

You can also drop the file onto the window. Where Humanize Desktop is installed, double-clicking the file imports it too.

The epic opens and appears in the sidebar. Read its sessions and trace as you did in steps 1 to 3.

![Reel: Search is opened, Import is clicked, and the imported epic opens with its graph](/shots/tutorials-read-back-a-run-import.svg)

*An imported epic is an epic like any other.*

## 7. Back it up to a git repository

A backup target is a git repository where Humanize pushes epics and chats using your system `git` credentials.

1. Open **Settings**, select **Backup**, and click **Add target**.
2. Enter a **Name** (for example `epics`) and the **Repository** URL. Keep **Branch** as `main`.
3. Under **When**, tick **On epic end** to back up every epic automatically when it finishes. Leave it unticked to back up only by hand.
4. Click **Save**, then tick **Default** on the new row so new epics use this target.

![Reel: a target named epics is added with a repository URL, set to back up on epic end, and made the default](/shots/tutorials-read-back-a-run-target.svg)

Open your existing epic and click the **Upload** up arrow in its bar. A notice shows which targets receive the upload.

![The epic after Upload was clicked: a notice reads Uploading to epics](/shots/tutorials-read-back-a-run-upload.svg)

List the contents of the backup repository in a terminal:

```sh
hmz backup --list
```

![Terminal: hmz backup --list prints the target, then one line for the epic with its machine, workdir, name, ending and task](/shots/tutorials-read-back-a-run-backup-list.svg)

On another machine configured with the same target, open **Settings**, **Backup**, **Download**, and pick the epic. Or run:

```sh
hmz backup --pull <epic>
```

## What you did

- Opened a finished epic and read a session transcript.
- Inspected its trace as a timeline and a flame graph.
- Checked usage costs by day and by flow.
- Exported the epic as a `.hmzepic` file and imported it.
- Added a git backup target and uploaded the epic.

## Next

- [History and search](/user/history): find past epics in the app and terminal.
- [Trace a run with Exomyth](/user/tracing): use every control in the trace viewer.
- [Export and import a run](/user/export): see what the archive holds and what gets scrubbed.
- [Back up to git](/user/backups): configure policies, per-epic targets, and downloads.

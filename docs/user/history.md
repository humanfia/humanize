---
title: History and search
description: Find an earlier epic or chat, open it, and read what each agent did in each session.
---

# History and search

Humanize records every epic as it runs and keeps it after it ends. You can list earlier epics, filter and search them, and read any session of any agent.

![An epic in the sidebar is opened into its agents and sessions, and one session is read](/shots/user-history-sidebar.svg)

## In the app

Humanize Desktop and the web page work the same way.

### Browse the sidebar

Click a row in the sidebar to open that epic. The sidebar lists the active daemon's chats and epics and updates while they run. Each epic row shows the first line of its task, its state (`Running`, `Asking`, `Waiting`, `Stopping`, `Done`, `Failed`, `Refused`, `Crashed`, `Stopped`, `Budget spent`, `Unfinished` or `Unknown`), its flow, and `live` or when it started. Point at a row to see the full task and start time.

Each group shows 20 rows, followed by a `Show N more` button. To pin, regroup or sort rows, see [Organise chats](/user/manage-chats).

### Expand agents and sessions

Click the chevron (**Expand**) on an epic row to see its agents and the sessions each agent opened.

- Click an agent to open the epic with that agent selected. Right-click it for **Show on graph**, **Open log** and **Copy agent**.
- Click a session to read it. Right-click it for **Open**, **Copy link** and **Copy session ID**.

See [Watch a run](/user/watch-a-run) for what an open epic shows.

### Use an epic's menu

Click **More options** at the end of a row, or right-click the row.

![The More options button of an epic's row opens its menu](/shots/user-history-menu.svg)

| Item | What it does |
| --- | --- |
| **Open** | Opens the epic. |
| **Pin** / **Unpin** | Keeps the row first, under **Pinned**. |
| **Mark as unread** / **Mark as read** | Adds or removes the unread dot on the row. |
| **Exomyth** | Opens the epic's trace. See [Trace a run with Exomyth](/user/tracing). |
| **Resume** | Opens the **Resume epic** form, which starts a new epic from where this one stopped. Shown for a resumable epic that is not running and did not end as `Done`. See [Resume a run](/user/resuming). |
| **New epic like it** | Opens **New epic** with the same flow and folder. |
| **Copy link**, **Copy task**, **Copy name** | Copies that value to the clipboard. |
| **Export** | Saves the epic as a `.hmzepic` file. Hidden while the epic runs. See [Export and import a run](/user/export). |
| **Upload** | Backs the epic up to its backup targets now. See [Back up to git](/user/backups). |
| **Stop** | Stops the epic. Shown while the daemon holds the running epic. See [Stop a run](/user/stopping). |

### Search chats and epics

Click **Search** in the sidebar, or press <kbd>cmd+k</kbd> (<kbd>ctrl+k</kbd> on Windows and Linux). Search lists the current daemon's chats and epics, newest first, 50 per page; **Newer** and **Older** turn the page.

![Search is opened, turned to Epics, and filtered to the epics that failed](/shots/user-history-search.svg)

- Type to match an epic by task, flow or name, or a chat by title, first message or name.
- Switch between **All**, **Chats** and **Epics** to choose what is listed.
- Click **Filters** to show three filters: how it went (`All`, `Running`, `Done`, `Failed`, `Stopped`, `Unfinished`, each with a count), the folder (**All folders** until you pick one) and the flow (**All flows**). The **Chats** tab shows only the folder filter.
- Point at a result or select it with the arrow keys to see its folder, flow, agents, spend, duration, sessions and `Resumable` above the footer.
- Below the results, click **New chat** to start a chat or **Import** to load a `.hmzepic` file.

When nothing matches, Search says `Nothing is like that.` and offers **Clear filters**. It empties the search box and resets all three filters; the tab stays as it is. With nothing typed or filtered, an empty list offers **New chat** or **New epic** instead.

![Search finds no failed epic like refund, and offers Clear filters](/shots/user-history-search-none.svg)

| Key | What it does |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Move through the results |
| <kbd>enter</kbd> | Open the result |
| <kbd>←</kbd> <kbd>→</kbd> | Change tab (when the search box is empty) |
| <kbd>/</kbd> | Show or hide the filters (when the search box is empty) |
| <kbd>alt+enter</kbd> (<kbd>option+enter</kbd> on macOS), <kbd>shift+F10</kbd> or right-click | Open the result's menu |
| <kbd>esc</kbd> | Close |

To search a single folder, right-click the folder heading in the sidebar and choose **Search here**.

### Switch to another daemon

Click the daemon bar at the bottom of the sidebar and pick another machine. The sidebar and Search switch to that daemon's chats and epics. See [Connect to other machines](/user/daemons).

## In the terminal

### List epics

Run `/epics` in `hmz` to list the current directory's epics, newest first. You can open `/epics` even while an epic is running.

Each row shows the start time, flow, task, agents, spend, output tokens, duration and session count, and `backed up to` with the backup targets that hold it. If an epic did not finish normally, the row shows `failed`, `stopped`, `was left unfinished` or `is still going`. It shows `resumable` when you can pick it up, and `●` when you were notified about it and have not opened it yet.

![/epics lists four epics of this directory](/shots/user-history-epics.svg)

| Key or button | What it does |
| --- | --- |
| <kbd>enter</kbd>, <kbd>→</kbd>, <kbd>m</kbd> or click | Open the epic's menu |
| <kbd>ctrl+t</kbd> or **This machine** | Toggle between this directory and all directories on this machine. `hmz` remembers your choice. |
| `status`, `flow` rows | Filter by outcome or flow, with a count for each value. When listing all directories, a `workspace` row filters by directory. |
| <kbd>/</kbd> or **Search…** | Search by flow, task and epic name, and by directory when listing all directories |
| <kbd>i</kbd> or **Import…** | Import a `.hmzepic` file. See [Export and import a run](/user/export). |
| **Daemon…** | List another daemon's epics |
| **Newer**, **Older** | Turn the page when more than 50 epics match |

### Open an epic's menu

Press <kbd>enter</kbd> on an epic. The top of the menu shows its path on disk, how it ended, and the status of each backup.

| Row | What it does |
| --- | --- |
| `resume epic` | Picks the epic up. Shown when its flow is resumable. An imported epic whose workspace or commit is not on this machine has no such row, and the menu says why. Refused if the epic ran in another directory or another flow is running here. See [Resume a run](/user/resuming). |
| `graph` | Shows its agents, called flows and sessions |
| `export epic` | Saves it as a `.hmzepic` file, including its trace |
| `Exomyth` | Opens its trace. See [Trace a run with Exomyth](/user/tracing). |
| `upload` | Backs it up now. Shown when a backup target exists. |
| `copy name`, `copy task`, `copy path` | Copies that value to the clipboard |

### Read the graph and sessions

Choose `graph` from the epic's menu. Each agent appears as a box showing what it ran, its turns and its sessions, with arrows counting handovers between agents. Under each agent, each session row shows its harness, account and action count. If the epic called other flows, they appear as a tree under `called flows`. Choose **Exomyth** from the graph to open the trace.

Press <kbd>enter</kbd> on a session to read it from oldest action to newest: each `turn` with its prompt, each `model` call with its thinking, each tool call with input and output, and what the agent `said`. A tool call that failed is marked `✕ failed`.

![/epics, then one epic's menu, its graph, and one session read whole](/shots/user-history-read.svg)

Items longer than 6 lines or 400 characters are truncated; press <kbd>enter</kbd> on an item to expand it, and again to fold it. Press <kbd>/</kbd> to search the session and <kbd>esc</kbd> to go back.

![One session read back: a turn, model calls, three tool calls and what the agent said](/shots/user-history-session.svg)

### Browse another daemon

Run `/epics @<name>` with a daemon name from your Daemons page, or open `/epics` and choose **Daemon…**. `/epics` stays on that daemon until you pick another; run `/epics @local` to return to this machine.

![/epics @server lists two epics held by the daemon named server](/shots/user-history-remote.svg)

The list shows each epic's workspace on that machine, plus any active chat there as a row named `chat`. A chat or epic started without a folder shows `no folder` in place of the path. If the daemon cannot be reached, the list shows the reason. Press <kbd>enter</kbd> or <kbd>m</kbd> on a row:

| Row | What it does |
| --- | --- |
| `follow` | Attaches to a running epic or chat so you can steer it like a local one. Shown only while it runs there. Press <kbd>esc</kbd> to return to the list and leave it running. |
| `export` | Downloads the epic here as a `.hmzepic` file. Unavailable while it runs. |
| `upload` | Backs the epic up on that machine |
| `copy name`, `copy task`, `copy workspace` | Copies that value to the clipboard |

A chat row has only `follow` and `copy id`. Press <kbd>n</kbd> or choose **New epic…** to start and follow an epic on that machine. Choose **Refresh** to reload the list. To add a daemon, see [Connect to other machines](/user/daemons).

## Good to know

- `/epics` does not list local chats. Run `/resume` inside a chat instead. See [Organise chats](/user/manage-chats).
- Search excludes archived chats and [sessions from other CLIs](/user/harness-sessions).
- Setting a flow or outcome filter makes the **All** tab list epics only, because chats have neither.
- The app or browser stores pins, unread marks and expanded sidebar rows locally, not on the daemon.

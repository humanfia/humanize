---
title: The terminal interface
description: "Find your way around `hmz`, the full-screen terminal interface: its prompt, commands, views, status line and menus."
---

# The terminal interface

Run `hmz` in a project folder to open the terminal interface. It opens on a new chat with the folder's last agent. You do everything from one prompt: type a line to talk, or type a `/` command to open a menu.

![The terminal interface as it opens: the banner, an agent line above the prompt, and the status line with its key hints](/shots/user-terminal-home.svg)

## Read the screen

From top to bottom:

| Part | What it shows |
| --- | --- |
| Opening box | The banner and the version. |
| Transcript | What you and the agents said. Agent lines start with a green bullet; yours start with `❯`. |
| Lines above the prompt | On the right, one line per agent role: its name, role, harness, model and effort. While an epic runs, one line per outworlder and what you spent. On the left, lines you sent that an agent has not taken yet. |
| Prompt `❯` | The editor. It always has focus and grows to 10 rows. |
| Status line | The state on the left, the active keys on the right. |

## Use the prompt

| Key | What it does |
| --- | --- |
| <kbd>enter</kbd> | Send the line. Blank lines are not sent. |
| <kbd>shift+enter</kbd> or <kbd>ctrl+j</kbd> | Start a new line. <kbd>ctrl+j</kbd> works in every terminal; <kbd>shift+enter</kbd> works where the terminal reports it. |
| <kbd>ctrl+c</kbd> | Clear what you typed. On an empty prompt, see [Stop a run](/user/stopping). |
| <kbd>↑</kbd> on the first row, <kbd>↓</kbd> on the last | Walk the prompt history. |
| <kbd>←</kbd> on an empty prompt | Open the monitor (outside a chat). See [Watch a run](/user/watch-a-run). |
| <kbd>shift+tab</kbd>, <kbd>tab</kbd> | Switch to the next or previous view. |
| <kbd>ctrl+q</kbd> | Quit, same as `/exit`. |

### How input is routed

Humanize checks each line you send in this order and applies the first rule that matches:

![The order in which a sent line is read: a side question in btw mode, a Humanize command, the chat harness's own input, a flow start, an unknown command, or words said to the agent](/diagrams/user-terminal-1.svg)

1. In btw mode, a line without a leading `/` asks a side question. See [Ask a side question](/user/side-questions).
2. A `/` line that names a Humanize command runs that command.
3. In a chat, a line starting with `$`, `/`, `!` or `@` goes to the chat's harness. See [Commands, skills and files in a chat](/user/chat-input).
4. `$<flow> <task>` starts that flow on the task, such as `$ralph_loop fix the build`. If the flow is not set up here yet, `/flow` opens on it first, holding the task. See [Start an epic](/user/epics). If a question is waiting, the line answers it instead.
5. Any other `/` line fails with `hmz: no such command: /<name>`.
6. Anything else goes to the agent: it starts or continues the chat, steers the running flow, or answers a waiting question. See [Chat with an agent](/user/chat), [Talk to a running flow](/user/steering) and [Answer a flow's questions](/user/questions).

If a command does not work in your current view, Humanize tells you where it works. Command arguments split like shell words, so quote arguments that contain spaces.

### Recall prompt history

Humanize saves every line you send to `~/.local/state/humanize/history.jsonl` with its folder. Press <kbd>↑</kbd> and <kbd>↓</kbd> to walk the lines sent in the current folder, or lines from all folders if you have not sent any here yet. Walk past the newest line to return to the draft you were typing. Consecutive duplicate lines are saved once.

## Run commands

Type `/` to list the commands that work right now, along with their arguments and descriptions. Keep typing to filter the list.

![A reel: typing / lists the commands, /se narrows to /settings, tab completes it and offers its pages, and enter opens the Notifications page](/shots/user-terminal-commands.svg)

| Key | In the list |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Move the highlight. |
| <kbd>tab</kbd> or <kbd>enter</kbd> | Accept the highlighted option. It replaces the word and adds a space without sending the line. |
| <kbd>esc</kbd> | Hide the list until you type again. |

The list also completes arguments: flows after `/flow` and `$`, the nine pages after `/settings`, and `native` or `flow` after `/prefer`. When a command is complete, one row shows its arguments and <kbd>enter</kbd> runs it.

| Command | What it does | More |
| --- | --- | --- |
| `/flow [flow] [task]` | Set up a flow, or start one on a task. | [Find and install flows](/user/flows), [Start an epic](/user/epics) |
| `/epics [@daemon]` | View and manage epics here or on another daemon. | [History and search](/user/history) |
| `/resume` | Resume the last epic here; in a chat, pick an earlier chat. | [Resume a run](/user/resuming), [Organise chats](/user/manage-chats) |
| `/stop` | Stop the flow or the chat's turn. | [Stop a run](/user/stopping) |
| `/exit`, `/quit` | Quit. You can leave a running flow running. | [Leave it running and come back](/user/leaving) |
| `/clear` | Clear the current view; in a chat, start a new chat. | [Chat with an agent](/user/chat) |
| `/chat` | Return to the chat after a flow takes the screen. | [Chat with an agent](/user/chat) |
| `/prefer [native\|flow]` | Choose what `$<name>` runs in a chat when it matches both a skill and a flow. | [Skills](/user/skills) |
| `/btw [question]` | Ask side questions of the current session. | [Ask a side question](/user/side-questions) |
| `/ai` | Talk to Ai-chan. | [Ai-chan](/user/ai-chan) |
| `/env [role]` | Inspect files, changes and a shell in the run's environments. | [Files, changes and terminal](/user/environment-panels) |
| `/afk [on\|off]` | Set whether an agent may ask you questions. | [Answer a flow's questions](/user/questions) |
| `/claim [on\|off]` | Answer for one outworlder alone. | [Answer a flow's questions](/user/questions) |
| `/settings [page]` | Open the settings. | [Settings](/user/settings) |

The list shows only commands that apply right now: `/claim` appears only on an outworlder's view, and outside a chat `/resume` appears only when there is an epic to resume. For every key in every view, see [Terminal commands and keys](/reference/tui).

## Switch views

While an epic runs, the interface keeps a separate transcript for each agent, session and outworlder. You read one view at a time.

![A reel: shift+tab steps from the agent's view to the outworlder's view and back; the lines above the prompt mark which one is being read](/shots/user-terminal-views.svg)

Press <kbd>shift+tab</kbd> for the next view and <kbd>tab</kbd> for the previous one. The cycle includes each session with an open turn, followed by each outworlder. The lines above the prompt mark your current view as `reading`, and mark any other view as `unread` when new lines arrive. Ended sessions leave the cycle; open the monitor to read them. A chat has only one view, so both keys do nothing.

The interface keeps the last 2000 lines of up to 32 transcripts.

## Read the status line

The left side shows the current state: `starting…`, the active agents and their elapsed time (in a chat, `running…` then `done`), `waiting for you`, or, when idle, the agent (outside a chat, the flow that is set up) and the folder. Prefixes mark active modes: `afk` when agents may not ask you, `details` when tool calls are visible, `btw` in btw mode, and `2 flow updates` when installed flows have newer releases. After you copy text, it shows `copied` for two seconds.

Two prefixes mark what the terminal follows. When you open an epic or chat on another daemon with `follow` from `/epics @<name>`, you see `@<daemon> · <folder>` and the transcript shows `following <path> on <daemon>; esc comes back`. Press <kbd>esc</kbd> at the prompt to return to that daemon's list. A new Ai-chan conversation shows `Ai-chan · new · <scope>` until your first line; a conversation you follow shows `Ai-chan#<n> · <scope>`. See [History and search](/user/history) and [Ai-chan](/user/ai-chan).

The right side lists only the keys that work right now, such as `enter send`, `shift+tab switch view`, `/ commands`, `← monitor` and what the next <kbd>ctrl+c</kbd> does. In a narrow terminal, hints drop from the left of the key list; the state on the left side is never cut.

## Use menus

`/flow`, `/epics`, `/settings` and `/ai` open full-screen menus. Every menu shares the same layout and keys.

![The Notifications page of /settings: the way there across the top, the list with the cursor row filled, switches at the right, the Save button and the keys that work](/shots/user-terminal-menu.svg)

| Key | What it does |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Move the cursor. |
| <kbd>enter</kbd> | Open or select the row. |
| <kbd>→</kbd> | Enter what the row opens. |
| <kbd>←</kbd> or <kbd>backspace</kbd> | Go up a level. |
| <kbd>esc</kbd> | Revert a row you are editing, clear the search, or leave the menu. |
| <kbd>tab</kbd>, <kbd>shift+tab</kbd> | Move between the search box, the list and the buttons. |
| `/` | Search the list, when searchable. |
| `m` | Open the row's menu, when available. |

You can also click any row, button or breadcrumb across the top.

- **Rows.** A value ending in `▸` opens a sheet. A value ending in `▾` drops a list of options with `✔` on the active one. A switch reads `● on ▾` or `○ off ▾`; its list opens on the opposite value, so pressing <kbd>enter</kbd> twice flips it.
- **Forms.** Type on a form row to start editing it. Press <kbd>enter</kbd> to keep the value and move to the next unanswered row, or <kbd>esc</kbd> to revert it. On path rows, press <kbd>tab</kbd> to complete paths as in a shell.
- **Buttons.** The primary action button sits last on the right in green. Destructive buttons are red.

### Save or discard changes

Menus hold your edits until you save. While you have unsaved edits, the top line shows `● Unsaved`. Press **Save**, or leave the menu to open a `Save?` prompt with **Save** and **Discard** (<kbd>esc</kbd> returns to the menu).

![A reel: enter on a switch drops its values, picking off marks the page as unsaved, and leaving the settings opens the Save? box](/shots/user-terminal-save.svg)

Actions that install, fetch, import, export or upload take effect immediately.

## Select and copy text

Drag across the transcript to copy from press to release. Double-click to copy a word, or triple-click to copy the whole line. Humanize copies the unwrapped text and sends it through the terminal to your local clipboard, so copying works over SSH. In most terminals, hold <kbd>shift</kbd> while dragging to use the terminal's own selection instead. The transcript follows new lines until you scroll up, and follows again once you scroll back to the bottom.

## Change colours

By default, the interface uses the web page's colours: dark, or light where your terminal reports a white background in `COLORFGBG`. Set `TEXTUAL_THEME` to use another theme instead:

```sh
TEXTUAL_THEME=nord hmz
```

`TEXTUAL_THEME=terminal` uses your terminal's own 16 colours and background. Unknown theme names are ignored. Set `NO_COLOR=1` for the terminal's own colours too. See [Themes and language](/user/themes).

## Panes beside the log

Press <kbd>f1</kbd> to open Keys to the right of the log, or <kbd>f3</kbd> for Ai-chan's conversations. A pane takes no room until you open it. The bottom line lists the keys that work where you are. Press <kbd>esc</kbd> to go back to the prompt, and the pane's own key again to close it.

## Find a chat or an epic

The navigator on the left lists every chat and epic on this machine. It is open from the start on a wide terminal; press <kbd>ctrl+b</kbd> to go to it, and again to close it.

1. Press <kbd>ctrl+b</kbd>.
2. Move with <kbd>↑</kbd> and <kbd>↓</kbd>. What waits on you is at the top, in pink.
3. Press <kbd>enter</kbd> to open the row. The prompt takes the keys back.

Press <kbd>p</kbd> to pin a row, <kbd>u</kbd> to mark it unread, <kbd>g</kbd> to group by folder, date or as one list, and <kbd>.</kbd> for everything else you can do with it.

To search instead, press <kbd>ctrl+k</kbd> and type. <kbd>tab</kbd> switches between all, chats and epics; <kbd>enter</kbd> opens the row; <kbd>esc</kbd> closes Search. See [the key tables](/reference/tui#navigator).

## Flows page

Press <kbd>ctrl+l</kbd> to open the Flows page over the whole screen. **Installed** lists the flows you can run, with any that has a newer release first and marked `↑`. **Flowverses** lists the indexes more flows are installed from, with when each was fetched. <kbd>tab</kbd> turns from one to the other, the bottom line lists the keys of the list you are in, and <kbd>esc</kbd> goes back one list and then closes the page. See [Find and install flows](/user/flows#the-flows-page).

The Download, Import and Export pages move epics between machines. A transfer goes on when you close its page with <kbd>esc</kbd>; open any of the three again to see where it stands. See [Export and import a run](/user/export) and [Back up to git](/user/backups).
Press <kbd>f5</kbd>, <kbd>f6</kbd> or <kbd>f7</kbd> to open the Files, Changes or Terminal of the environment you are working in beside the log, and <kbd>ctrl+w</kbd> inside one to widen it. The pane stays open while you type at the prompt. See [Files, changes and terminal](/user/environment-panels#keep-a-pane-open-beside-the-chat).
Press <kbd>ctrl+g</kbd> for **Details** of the open chat: its model, effort, permissions and environment, each changed with <kbd>enter</kbd>, its usage, and **Rename…**, **Fork**, **Archive** and **Delete chat**.

## Pages over the log

Press <kbd>ctrl+n</kbd> for the New chat page: the first message, and above it the chips **Folder**, **Environment**, **Model**, **Effort** and **Permissions** showing what the chat starts with. A page covers the log until you press <kbd>esc</kbd>. See [Chat with an agent](/user/chat) and [Continue sessions from other CLIs](/user/harness-sessions).

### Start an epic from one page

Press <kbd>ctrl+e</kbd> at the log to open **New epic**. The page is one form, read top to bottom: Flow, Folder, Task, an agent for each role, the flow's parameters, Budget, Backup, the profiling switches and Resume. It opens with what this folder last set the flow up with, so starting the same flow again is typing the task and pressing <kbd>ctrl+s</kbd>.

- Type on a row to write it, and press <kbd>enter</kbd> on a row marked `▾` to pick from a list. `More options` at the end of an agent's or an environment's list opens the full sheet, with accounts, efforts and machines.
- Leave **Folder** empty to start the epic in a temporary directory of its own. An epic started in another folder, or in none, is listed under `/epics`; one started in this folder runs in front of you.
- <kbd>ctrl+s</kbd> starts the epic. Anything missing or refused is shown in red under the row it is about.
- <kbd>esc</kbd> closes the page and keeps what you typed for next time.

### Read the epic beside its log

Press <kbd>ctrl+o</kbd> to open the **Epic** pane to the right of the log. It has the app's four tabs: **Details**, **Board**, **People** and **Side questions**. Press <kbd>←</kbd> <kbd>→</kbd> or <kbd>1</kbd>–<kbd>4</kbd> to switch tabs; the bottom line lists what the open tab's keys do. The pane reopens on the tab and row you left.

### The monitor and Exomyth

Two pages draw a run rather than list it, and both use the colours of the app. The monitor (<kbd>←</kbd> on an empty prompt) draws each agent as a flat block in a heavy square frame with a stripe in the agent's lane colour down its left side, and marks each handover between two blocks with `╱`. Exomyth (<kbd>ctrl+e</kbd> on the monitor) draws each span of the trace as a heavy block in the lane colour of its category. On both, cyan is where the cursor is or what you can open, and pink is the one thing picked: the node of a person the flow is asking, or the span under the cursor. Their key lines use the app's words, such as **Open**, **Back**, **Graph**, **List** and **Details**.

See [Watch a run](/user/watch-a-run) and [Trace a run with Exomyth](/user/tracing).

## Good to know

- The interface draws without waiting for the network. In the background, it refreshes model lists, flowverse indexes and prices, and checks for new releases.
- When a new release is out, the transcript prints ``hmz <version> is out: run `hmz update` to update`` once. See [Install and update](/user/install).
- When installed flows have updates, the transcript prints `updates available: …; update from /flow`.
- On first start, Humanize asks `Report errors to Humanize?`. See [Report a problem](/user/reporting).
- When a background run finishes or asks a question, a card appears in the corner. See [Notifications](/user/notifications).
- Type `/` for all commands.

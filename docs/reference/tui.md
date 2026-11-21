---
title: Terminal commands and keys
description: Look up every slash command of the terminal interface and every key of every view and menu.
---

# Terminal commands and keys

Look up every command you can type at the `hmz` prompt and every key each screen accepts. See [The terminal interface](/user/terminal) for how the screens fit together.

![The list of commands that opens when you type a slash at the prompt](/shots/reference-tui-commands.svg)

*Type `/` to list the commands that work right now.*

## What a typed line becomes

Press <kbd>enter</kbd> to send a line. `hmz` reads the line in this order and takes the first match.

| Line | Becomes |
| --- | --- |
| Any line not starting with `/`, in btw mode | A side question |
| `/` plus one of the commands below | That command |
| A line starting with `$`, `/`, `!` or `@`, in a chat | Input for the chat's coding agent. See [Commands, skills and files in a chat](/user/chat-input) |
| `$<flow> <task>` | Starts an epic of that flow, unless a question is waiting for your answer |
| Any other `/` line | Refused: `hmz: no such command: /<name>` |
| Anything else | An answer to the waiting question, else a line said to the agent or chat on screen |

`hmz` splits command arguments the way a shell splits words and refuses unbalanced quotes.

Write a flow name in a `$` line as `<flow>`, `<user>/<flow>`, `@<flowverse>/<flow>` or `@<flowverse>/<user>/<flow>`. Add `:<name>` to pick one flow of a file that holds several. If the flow is not set up here yet, the flow menu opens holding the task.

## Slash commands

Type `/` to see the commands that work in the current view and state. If you run one of the fifteen commands where it does not apply, `hmz` refuses it and tells you why.

| Command | Argument | What it does |
| --- | --- | --- |
| `/flow` | flow name or path, then a task | Alone, opens the flow menu. With a flow, opens that flow's roles. With a flow and a task, starts an epic if the flow is set up here. While a flow runs, it only opens the running flow's roles. |
| `/epics` | `@<daemon>` | Opens the list of epics, here or on a named daemon. |
| `/resume` | none | Outside a chat, resumes the newest resumable epic of this directory. In a chat, opens the list of earlier chats here. Refused while a flow runs. |
| `/chat` | none | Puts the chat back on screen after a flow was on it. |
| `/clear` | none | Clears the view on screen. In a chat, starts a new chat; the old one stays in `/resume`. |
| `/stop` | none | Stops the running epic for everyone, without asking. In a chat, stops only the open turn. |
| `/exit` | none | Leaves. With an epic running, asks whether to stop it or detach. |
| `/quit` | none | Same as `/exit`. |
| `/btw` | a question | Enters btw mode on the session on screen, or asks one side question. Alone in btw mode, leaves it. Works only on one agent's or session's view. |
| `/ai` | none | Opens the Ai-chan conversations menu. |
| `/afk` | `on` or `off` | Marks you away, so agents that ask are told nobody is here. Alone, toggles. On an outworlder's view it affects that role only. |
| `/claim` | `on` or `off` | On an outworlder's view, makes this terminal the only one that answers for the role. Alone, toggles. |
| `/env` | a role, a chain of roles or an environment's id | Opens the environments of the run or chat on screen, or the one named. |
| `/settings` | a page | Opens settings, or one page of it. |
| `/prefer` | `native` or `flow` | In a chat, sets what `$<name>` runs when it names both a skill and a flow. Alone, says the current choice. |

`/settings` takes `general`, `notifications`, `daemons`, `accounts`, `nous`, `runtimes`, `backup`, `workspace` or `usage`. The older names `settings`, `everywhere`, `directory` and `environments` also work. `/settings flowverses` opens `/flow` on the Flowverses page.

## Keys

### Anywhere

| Key | Action |
| --- | --- |
| <kbd>ctrl+c</kbd> | Takes back the nearest thing. See the next table. |
| <kbd>ctrl+q</kbd> | Same as `/exit`. |

What <kbd>ctrl+c</kbd> does depends on the state. Press it a second time within 3 seconds to confirm.

| State | <kbd>ctrl+c</kbd> |
| --- | --- |
| Text in the prompt | Clears the prompt. |
| An epic is running | First press warns, second press stops the epic. |
| An epic is stopping | Forces the stop: open sessions are closed mid-turn. |
| Idle, or in a chat | First press warns, second press exits. |

### Prompt

| Key | Action |
| --- | --- |
| <kbd>enter</kbd> | Sends the line. On an empty prompt, opens the form of a waiting question. |
| <kbd>shift+enter</kbd> | New line, where the terminal reports the key. |
| <kbd>ctrl+j</kbd> | New line, in every terminal. |
| <kbd>↑</kbd> on the first row | Older line of the prompt history. |
| <kbd>↓</kbd> on the last row | Newer line of the prompt history. |
| <kbd>esc</kbd> | Leaves btw mode. When following an epic on another daemon, goes back to that daemon's list. |

### Offer list

Type `/`, `$`, or (in a chat) `@` to open the offer list above the prompt.

| Key | Action |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Move the highlight. |
| <kbd>tab</kbd> or <kbd>enter</kbd> | Take the highlighted offer. The line is not sent. |
| <kbd>esc</kbd> | Hide the list until the text changes. |

### Views

Use these keys on the log screen while an epic runs. They do nothing in a chat.

| Key | Action |
| --- | --- |
| <kbd>shift+tab</kbd> | Next view: each session with an open turn, then each outworlder. |
| <kbd>tab</kbd> | Previous view, while the offer list is closed. |
| <kbd>←</kbd> on an empty prompt | Opens the monitor. |

### Monitor

Use these keys in the monitor, graph or list, while its prompt is empty. See [Watch a run](/user/watch-a-run).

| Key | Action |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Previous or next node. |
| <kbd>enter</kbd> | Reads an agent, session or outworlder. Opens an environment or the epic row as a page. Edits a board line. |
| <kbd>space</kbd> | Opens an agent out to its sessions, or shuts it. |
| <kbd>→</kbd> | Back to the view last read. |
| <kbd>ctrl+t</kbd> | Switches between graph and list. Works while typing too. |
| <kbd>ctrl+e</kbd> | Opens the running epic in Exomyth. Not in a chat. |
| <kbd>esc</kbd>, <kbd>←</kbd> or <kbd>backspace</kbd> | On an environment page or the epic page, back to the monitor. |

To edit a board entry, type the name, press <kbd>enter</kbd>, type the value, and press <kbd>enter</kbd> to save. Save an empty value to remove the entry.

### Menus

`/flow`, `/epics`, `/settings`, `/ai`, `/env` and every sheet they open share these keys. The bottom line of each menu lists the keys active right now.

![The Daemons page of settings in the terminal: a list, a row of buttons and the key line at the bottom](/shots/reference-tui-menu.svg)

| Where | Key | Action |
| --- | --- | --- |
| List | <kbd>↑</kbd> <kbd>↓</kbd> | Previous or next row, wrapping. |
| List | <kbd>enter</kbd> | Opens or takes the row, drops its values, or begins and keeps a written row. |
| List | <kbd>→</kbd> | Goes into what the row opens. |
| List | <kbd>←</kbd> or <kbd>backspace</kbd> | Goes up to the menu above. |
| List | <kbd>m</kbd> | Opens the row's own menu, where it has one. |
| List | <kbd>/</kbd> | Opens the search box, where the list is searchable. |
| Menu | <kbd>esc</kbd> | Puts back a row being written, else clears the search, else leaves. |
| Menu | <kbd>tab</kbd> <kbd>shift+tab</kbd> | Next or previous of search box, list and buttons. |
| Search box | <kbd>enter</kbd> or <kbd>↓</kbd> | Goes to the list, keeping the filter. |
| Buttons | <kbd>←</kbd> <kbd>→</kbd> | Previous or next button, wrapping. |
| Buttons | <kbd>↑</kbd> | Back to the list. |
| Buttons | <kbd>enter</kbd> | Presses the button. |
| Dropdown | <kbd>↑</kbd> <kbd>↓</kbd> | Move. |
| Dropdown | <kbd>enter</kbd> | Picks the value. |
| Dropdown | <kbd>esc</kbd> | Picks nothing. |
| Box | arrows, <kbd>tab</kbd>, <kbd>shift+tab</kbd> | Next or previous button. |
| Box | <kbd>enter</kbd> | Presses the button. |
| Box | <kbd>esc</kbd> | Answers nothing. |

If you leave a menu with unsaved changes, `Save?` opens with **Save** and **Discard**.

### Forms

| Key | Action |
| --- | --- |
| Typing or paste | Begins writing the row. The first character replaces the old value. |
| <kbd>enter</kbd> | Keeps the row and moves to the next unanswered one. |
| <kbd>esc</kbd> | Puts the row back. |
| <kbd>shift+enter</kbd> or <kbd>ctrl+j</kbd> | New line, on a multi-line row. |
| <kbd>tab</kbd> | Completes a path, on a row that takes one. |

### Row menus

<kbd>m</kbd> on a row opens these. A menu lists only what applies to the row.

| List | Row menu |
| --- | --- |
| `/flow`, Installed | `open`, `update`, `uninstall`, `copy here`, `copy name` |
| `/flow`, Flowverses | `open`, `fetch` or `fetch again`, `remove`, `copy URL` |
| `/resume` in a chat | `rename`, `fork`, `archive`, `upload`, `delete`, `copy id` |
| `/ai` | `forget` |
| `/settings daemons` | `connect`, `edit…`, `remove`, `copy name`, and on a daemon that is up `pair a device…` and `devices…`. `Local` has only the last two. |
| `/epics` on another daemon | An epic: `follow`, `export`, `upload`, `copy name`, `copy task`, `copy workspace`. A chat: `follow`, `copy id`. |

<kbd>enter</kbd> or <kbd>m</kbd> on an epic of `/epics` opens its rows: `resume epic`, `graph`, `export epic`, `Exomyth`, `upload`, `copy name`, `copy task`, `copy path`. See [History and search](/user/history).

### Epics list

| Key | Action |
| --- | --- |
| <kbd>ctrl+t</kbd> | Switches between this directory and every directory on this machine. |
| <kbd>i</kbd> | Imports an epic from a `.hmzepic` file. |
| <kbd>n</kbd> | On another daemon's list, starts a new epic there. |
| <kbd>enter</kbd> | On a session of an epic's graph, reads the session. In the session reader, shows a row whole. |

### Question form

Press <kbd>enter</kbd> on an empty prompt to open a waiting question's form along the bottom. See [Answer a flow's questions](/user/questions).

| Key | Action |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Previous or next field. |
| <kbd>1</kbd> to <kbd>9</kbd> | Pick the choice with that number. |
| <kbd>←</kbd> <kbd>→</kbd> | Move along a row of choices. |
| Typing | Writes the field. |
| <kbd>pgup</kbd> <kbd>pgdn</kbd> | Scroll the transcript above the form. |
| <kbd>esc</kbd> | Closes the form and keeps the draft. |

Send a bare number at the prompt to pick that numbered answer directly.

### Environment panels

Run `/env` to open an environment's panels. Press <kbd>tab</kbd> and <kbd>shift+tab</kbd> to switch panels, or <kbd>esc</kbd> to go back. See [Files, changes and terminal](/user/environment-panels).

| Panel | Key | Action |
| --- | --- | --- |
| Files | <kbd>enter</kbd> | Opens the folder, or the file in the built-in editor. |
| Files | <kbd>backspace</kbd> | Goes to the folder above. |
| Files | <kbd>n</kbd> | New file. |
| Files | <kbd>N</kbd> | New folder. |
| Files | <kbd>r</kbd> | Rename. |
| Files | <kbd>d</kbd> | Delete, after a box. |
| Files | <kbd>e</kbd> | Opens the file in `$VISUAL`, else `$EDITOR`, else `vi`. |
| Files | <kbd>ctrl+p</kbd> | Quick open by file name. |
| Files | <kbd>?</kbd> or <kbd>ctrl+shift+f</kbd> | Find text in files. |
| Editor | <kbd>ctrl+s</kbd> | Save. |
| Editor | <kbd>esc</kbd> | Save and close. |
| Changes | <kbd>enter</kbd> | Shows the file's diff. <kbd>esc</kbd> or <kbd>q</kbd> closes it. |
| Changes | <kbd>s</kbd> | Stage. |
| Changes | <kbd>u</kbd> | Unstage. |
| Changes | <kbd>x</kbd> | Discard, after a box. |
| Changes | <kbd>c</kbd> | Commit. |
| Changes | <kbd>r</kbd> | Refresh. |
| Shell | `~.` at the start of a line | Leaves the shell running and returns to `hmz`. |
| Shell | `~~` at the start of a line | Sends one `~`. |
| Snapshots | <kbd>enter</kbd> | Rewinds to the snapshot, after a box. |

Letter shortcuts in Files and Changes are disabled while the search box is open.

### Exomyth

Exomyth has three views: Timeline, Flame and Slices. See [Trace a run with Exomyth](/user/tracing).

| View | Key | Action |
| --- | --- | --- |
| All | <kbd>tab</kbd> <kbd>shift+tab</kbd> | Next or previous view. |
| All | <kbd>↑</kbd> <kbd>↓</kbd> | Row above or below. |
| All | <kbd>r</kbd> | Read the epic again. |
| All | <kbd>esc</kbd> | Leaves the search, then the range, then the pane, then Exomyth. |
| Timeline | <kbd>pgup</kbd> <kbd>pgdn</kbd> | Ten rows up or down. |
| Timeline | <kbd>←</kbd> <kbd>→</kbd> | Previous or next span. |
| Timeline | <kbd>w</kbd>, <kbd>+</kbd> or <kbd>=</kbd> | Zoom in. |
| Timeline | <kbd>s</kbd> or <kbd>-</kbd> | Zoom out. |
| Timeline | <kbd>a</kbd> or <kbd>shift+←</kbd> | Pan back. |
| Timeline | <kbd>d</kbd> or <kbd>shift+→</kbd> | Pan on. |
| Timeline | <kbd>enter</kbd> | Opens or shuts the pane of the span. |
| Timeline | <kbd>p</kbd> | Opens or shuts the pane of the process. |
| Timeline | <kbd>v</kbd> | Begins a range, then holds it, then drops it. |
| Timeline | <kbd>f</kbd> | Fits the range, or the span. |
| Timeline | <kbd>0</kbd> | Shows the whole epic. |
| Timeline | <kbd>space</kbd> | Folds or opens the process. |
| Timeline | <kbd>/</kbd> | Searches spans by name. <kbd>enter</kbd> finds. |
| Timeline | <kbd>n</kbd> <kbd>N</kbd> | Next or previous span found. |
| Flame | <kbd>t</kbd> | Next weight: time, tokens in, tokens out, count. |
| Flame | <kbd>m</kbd> | Sessions merged or apart. |
| Slices | <kbd>o</kbd> | Sorts by the next column. |
| Slices | <kbd>O</kbd> | Reverses the order. |
| Slices | <kbd>enter</kbd> | Goes to that slice on the timeline. |

### Mouse

| Action | Result |
| --- | --- |
| Click a row, button, value or breadcrumb step | Same as <kbd>enter</kbd> on it. |
| Click outside a box or dropdown | Answers nothing. |
| Drag in the transcript or the prompt | Copies the text dragged over. |
| Double click | Copies the word. In the monitor, reads the node. |
| Triple click | Copies the whole line. |
| <kbd>shift</kbd> and drag | Uses the terminal's own selection. |

Copied text goes to the clipboard of the machine running the terminal.

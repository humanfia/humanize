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

`/settings` takes `themes`, `daemons`, `notifications`, `language`, `general`, `accounts`, `nous`, `runtimes`, `backup`, `usage` or `workspace`. <kbd>F2</kbd> opens it from anywhere. The older names `settings`, `everywhere`, `directory` and `environments` also work. `/settings flowverses` opens `/flow` on the Flowverses page.

## Keys

### Anywhere

| Key | Action |
| --- | --- |
| <kbd>ctrl+c</kbd> | Takes back the nearest thing. See the next table. |
| <kbd>ctrl+q</kbd> | Same as `/exit`. |
| <kbd>f1</kbd> | Opens Keys beside the log. Pressed from elsewhere it goes to Keys; pressed inside Keys it closes it. |
| <kbd>ctrl+b</kbd> | Opens the navigator to the left of the log. Pressed from elsewhere it goes to it; pressed inside it closes it. |
| <kbd>ctrl+k</kbd> | Opens Search over the screen, and closes it. |
| <kbd>ctrl+n</kbd> | Opens the New chat page. Pressed on the page it closes it. |
| <kbd>ctrl+g</kbd> | Opens Details of the open chat beside the log. Pressed inside Details it closes it. |
| <kbd>ctrl+e</kbd> | Opens the New epic page from the log; closes it from the page. Over the monitor or a menu the key is theirs. |
| <kbd>ctrl+o</kbd> | Opens the Epic pane beside the log: Details, Board, People, Side questions. |
| <kbd>f3</kbd> | Opens Ai-chan's conversations beside the log, in the same way. |
| <kbd>esc</kbd> | In a pane beside the log, gives the keys back to the prompt and leaves the pane open. |

The bottom line of the screen lists the keys that work where you are, then the key of each pane.

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

### Navigator

The navigator lists every chat, epic and harness session of this machine's daemon. It is open from the start on a terminal at least 110 columns wide. `Waiting for you` is always the first group, then `Pinned`, then the rest by folder, by date, or as one list.

| Key | Action |
| --- | --- |
| <kbd>↑</kbd> / <kbd>↓</kbd> | Move along the list. |
| <kbd>enter</kbd> | On a chat: puts it on the log, as `/resume` does. On an epic: attaches the log to it while a host of this folder runs it, otherwise opens the epic's sheet from `/epics`. On a heading: folds or unfolds the group. |
| <kbd>n</kbd> | New chat. |
| <kbd>N</kbd> | New epic. |
| <kbd>p</kbd> | Pin or unpin the row. |
| <kbd>u</kbd> | Mark the row unread or read. |
| <kbd>.</kbd> | Open the menu of the row or folder. |
| <kbd>g</kbd> | Next grouping: `Folder`, `Date`, `None`. |
| <kbd>esc</kbd> | Back to the prompt. The navigator stays open. |

| Row | Menu |
| --- | --- |
| Chat | `Open`, `Pin`, `Mark as unread`, `Rename`, `Fork`, `Copy ID`, `Upload`, `Archive`, `Delete` |
| Epic | `Open`, `Pin`, `Mark as unread`, `Copy task`, `Copy name`, `Upload`, `Stop` while a host runs it |
| Harness session | `Open`, `Pin`, `Mark as unread`, `Copy session ID` |
| Folder | `New chat here`, `New epic here`, `Search here`, `Copy path`, `Collapse`, `Forget` for an empty folder |

`Delete` and `Forget` ask first. `Resume`, `Export`, `Exomyth` and `Copy path` of an epic are on the sheet that `Open` goes to. A chat of another folder is listed but not opened: run `hmz` in that folder.

| Mark | Meaning |
| --- | --- |
| Pink `■` | Waits on you: a chat awaiting input, an epic asking or waiting. |
| Cyan `■` | Running or stopping. |
| Green `■` | An epic that is done. |
| Red `■` | Failed, refused or crashed. |
| Cyan `●` | Unread. |
| `▸` beside the mark | Pinned. |
| Cyan title | The chat or epic on the log. |

While the keys are in the navigator, rows keep their places: changes are drawn where each row stands, and the order settles when you leave. Pins, unread marks, the grouping and folded groups are kept in `navigator.json` in Humanize's state directory.

### Search

| Key | Action |
| --- | --- |
| Typing | Narrows the list, 0.2 seconds after the last key. |
| <kbd>↑</kbd> / <kbd>↓</kbd> | Move along what was found. |
| <kbd>enter</kbd> | Close Search and open the row, as the navigator opens it. |
| <kbd>tab</kbd> / <kbd>shift+tab</kbd> | Next or previous tab: `All`, `Chats`, `Epics`. |
| <kbd>f2</kbd> | Next value of `How it went`. Applies to epics. |
| <kbd>f3</kbd> | Next folder. |
| <kbd>f4</kbd> | Next flow. Applies to epics. |
| <kbd>f5</kbd> | Clear the text and the filters. |
| <kbd>pgdn</kbd> / <kbd>pgup</kbd> | Older or newer page of 50 rows. |
| <kbd>esc</kbd> or <kbd>ctrl+k</kbd> | Close Search. |

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

If you leave a menu with unsaved changes, `Save changes?` opens with **Save** and **Discard**.

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
| `/resume` in a chat | `Rename`, `Fork`, `Archive`, `Upload`, `Delete`, `Copy ID` |
| `/ai` | `Rename`, `Pin` or `Unpin`, `Mark as read` or `Mark as unread`, `Delete` |
| `/settings daemons` | `Connect`, `Edit`, `Remove`, `Copy name`, and on a daemon that is up `Pair a device` and `Devices`. `Local` has only the last two. |
| `/epics` on another daemon | An epic: `Follow`, `Export`, `Upload`, `Copy name`, `Copy task`, `Copy workspace`. A chat: `Follow`, `Copy ID`. |

When an SSH machine has no hmz, a box asks `hmz is not installed on <name>. Install it?` over whatever is on screen, with `Install` and `Not now`. <kbd>esc</kbd> answers `Not now`, which leaves the daemon `failed` with `hmz is not installed on <name>.` until you pick `Connect` again. After `Install`, that daemon is not asked about again while the interface runs and its routes stay the same.

<kbd>enter</kbd> or <kbd>m</kbd> on an epic of `/epics` opens its rows: `Resume epic`, `Graph`, `Export`, `Exomyth`, `Upload`, `Copy name`, `Copy task`, `Copy path`. See [History and search](/user/history).

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

#### Panes beside the log

Press <kbd>f5</kbd>, <kbd>f6</kbd> or <kbd>f7</kbd> to open Files, Changes or Terminal to the right of the log, for the environment of the chat or epic you are in. The same key closes the pane; <kbd>esc</kbd> returns to the prompt and leaves it open. Each pane lists its keys at its foot.

| Pane | Key | Action |
| --- | --- | --- |
| All | <kbd>ctrl+w</kbd> | Widens the pane: 48 columns, half the screen, four fifths, then 48 again. |
| All | <kbd>tab</kbd> | Turns to the next environment, when there are several. |
| Files | <kbd>enter</kbd> | Opens or shuts the folder, or shows the file read-only in the pane. |
| Files | <kbd>backspace</kbd> | Back from the file to the tree. |
| Files | <kbd>e</kbd> | Opens the file in the built-in editor. |
| Files | <kbd>n</kbd> | New file. |
| Files | <kbd>shift+n</kbd> | New folder. |
| Files | <kbd>r</kbd> | Rename. |
| Files | <kbd>d</kbd> | Delete, after a box. |
| Files | <kbd>ctrl+p</kbd> | Go to file by name. |
| Files | <kbd>/</kbd> | Search in files. |
| Changes | <kbd>↑</kbd> <kbd>↓</kbd> | Moves the cursor; the diff under the list follows it. |
| Changes | <kbd>enter</kbd> | Gives the keys to the diff, to scroll it. <kbd>backspace</kbd> returns to the list. |
| Changes | <kbd>s</kbd> | Stage. |
| Changes | <kbd>u</kbd> | Unstage. |
| Changes | <kbd>x</kbd> | Discard, after a box. |
| Changes | <kbd>shift+s</kbd> | Stage all changes. |
| Changes | <kbd>shift+u</kbd> | Unstage all changes. |
| Changes | <kbd>c</kbd> | Commit, or amend the last commit. |
| Changes | <kbd>l</kbd> | Lists the commits. <kbd>backspace</kbd> returns to the changes. |
| Changes | <kbd>p</kbd> | Lists the snapshots. <kbd>enter</kbd> rewinds to one, after a box. |
| Changes | <kbd>r</kbd> | Refresh. |
| Terminal, tabs | <kbd>enter</kbd> | Gives the keys to the terminal shown. |
| Terminal, tabs | <kbd>←</kbd> <kbd>→</kbd> | Previous or next terminal. |
| Terminal, tabs | <kbd>n</kbd> | New terminal. |
| Terminal, tabs | <kbd>x</kbd> | Closes the terminal, after a box. |
| Terminal, typing | `~.` at the start of a line | Returns the keys to the tabs and leaves the terminal running. |
| Terminal, typing | `~~` at the start of a line | Sends one `~`. |
| Terminal, typing | Any other key | Goes to the terminal, <kbd>esc</kbd> included. |

<kbd>ctrl+c</kbd>, <kbd>ctrl+q</kbd> and the keys that open panes stay with `hmz` while you type in a terminal pane.

### Ai-chan pane

<kbd>f3</kbd> opens it. Pinned conversations come first, then the latest said in; a square marks a pinned one and a dot an unread one. Pins and unread marks are kept by this terminal only.

| Key | Does |
| --- | --- |
| <kbd>enter</kbd> | Follows the conversation in the log. On **New conversation**, opens `/ai`. |
| <kbd>n</kbd> | Opens `/ai` to start a new conversation. |
| <kbd>r</kbd> | Renames the conversation. |
| <kbd>p</kbd> | Pins or unpins it. |
| <kbd>u</kbd> | Marks it unread, or read. |
| <kbd>delete</kbd> | Deletes it, after a box whose first answer is **Cancel**. |
| <kbd>esc</kbd> | Goes back to the prompt and leaves the pane open. |

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

### Flows page

<kbd>ctrl+l</kbd> opens the Flows page from anywhere, and closes it. Its bottom line lists the keys of the list that is open.

| Where | Key | Action |
| --- | --- | --- |
| Either tab | <kbd>tab</kbd> | Turns to the other tab: **Installed** or **Flowverses**. |
| Installed | <kbd>enter</kbd> | Opens the flow: what it says of itself, its agents, environments and params. |
| Installed, or a flow opened | <kbd>n</kbd> | Starts a new epic of the flow. |
| Installed, or a flow opened | <kbd>u</kbd> | Updates to the newest release its flowverse lists. |
| Installed, or a flow opened | <kbd>s</kbd> | Lists its releases; <kbd>enter</kbd> installs or switches to one. |
| Installed, or a flow opened | <kbd>x</kbd> | Uninstalls it, after asking. |
| Flowverses | <kbd>enter</kbd> | Lists the flows the flowverse lists. |
| Flowverses | <kbd>a</kbd> | Adds a flowverse: a URL or `owner/repo`, and an optional name. |
| Flowverses, or its flows | <kbd>f</kbd> | Fetches its index. |
| Flowverses | <kbd>x</kbd> | Removes it and every flow installed out of it, after asking. |
| A flowverse's flows | <kbd>i</kbd> | Installs the newest release of the flow. |
| A flowverse's flows | <kbd>enter</kbd> | Lists the flow's releases. |
| A flowverse's flows, releases | <kbd>x</kbd> | Uninstalls the flow, after asking. |
| Releases | <kbd>enter</kbd> | Installs the release, or switches to it. |
| Anywhere on the page | <kbd>esc</kbd> | Goes back one list, then closes the page. |

Nothing is installed, updated or uninstalled while an epic is going; the page says so.

### Download, Import and Export pages

These three pages have no key of their own. Each lists the transfers under way and finished; a transfer goes on when its page is closed.

| Page | Key | Action |
| --- | --- | --- |
| Download | <kbd>enter</kbd> | Downloads the epic or chat under the cursor. |
| Download | <kbd>f</kbd> | Fetches the backup target again. |
| Download | <kbd>t</kbd> | Turns to the next backup target, where there is more than one. |
| Import | <kbd>enter</kbd> | Asks for the `.hmzepic` to import; <kbd>tab</kbd> finishes the path. |
| Export | <kbd>enter</kbd> | Asks where the epic under the cursor goes, and writes its archive there. |
| Any | <kbd>esc</kbd> | Closes the page. |

### New chat page

| Where | Key | Action |
| --- | --- | --- |
| Page | <kbd>tab</kbd> <kbd>shift+tab</kbd> | Next or previous of the chips, the message and the list. |
| Chip | <kbd>enter</kbd> | Drops the list its value is picked from: **Folder**, **Environment**, **Model**, **Effort**, **Permissions**. |
| Message | <kbd>enter</kbd> | Starts the chat with what the chips say. |
| List | <kbd>↑</kbd> <kbd>↓</kbd> | Previous or next chat or harness session. |
| List | <kbd>enter</kbd> | Opens the waiting chat, or reads the harness session. |
| Page | <kbd>esc</kbd> | Closes the page. |

### Details of a chat

| Key | Action |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Previous or next chip or action. |
| <kbd>enter</kbd> | Changes **Model**, **Effort**, **Permissions**, **Skill or flow** or **Environment**, or runs **Rename…**, **Fork**, **Archive** or **Delete chat**. |
| <kbd>esc</kbd> | Gives the keys back to the prompt. |

### Harness session page

| Key | Action |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> <kbd>pageup</kbd> <kbd>pagedown</kbd> | Scroll what was said. |
| <kbd>enter</kbd> | **Continue in chat**, for a session that can be continued. |
| <kbd>esc</kbd> | Closes the page. |

### New epic page

One form with everything an epic starts with: Flow, Folder, Task, an agent and an environment per role, the flow's parameters, Budget, Backup, the profiling switches and Resume. It opens holding what the folder last set the flow up with.

| Key | Action |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Previous or next row. |
| typing | Writes the row under the cursor; <kbd>enter</kbd> keeps it and moves to the next row still to answer, or to Start. |
| <kbd>enter</kbd> | On a row with `▾`, drops its values. `More options` opens the full agent or environment sheet. |
| <kbd>tab</kbd> | Completes a path in Folder. |
| <kbd>ctrl+s</kbd> | Start. The daemon checks the set-up first; what it refuses is shown under the row it is about. |
| <kbd>esc</kbd>, <kbd>ctrl+e</kbd> | Closes the page. What you typed is kept until the terminal closes. |

### Epic pane

| Key | Where | Action |
| --- | --- | --- |
| <kbd>←</kbd> <kbd>→</kbd>, <kbd>1</kbd>–<kbd>4</kbd> | Any tab | Previous or next tab; the tab of that number. |
| <kbd>↑</kbd> <kbd>↓</kbd> | Any tab | Previous or next row. |
| <kbd>enter</kbd> | Board | Edits the line. |
| <kbd>a</kbd> | Board | Adds a line. |
| <kbd>d</kbd> | Board | Removes the line, after asking. |
| <kbd>enter</kbd> | People | Claim, Take over or Release the role. |
| <kbd>w</kbd> | People | Away or Back for the role. |
| <kbd>shift+w</kbd> | People | Away or Back for all roles. |
| <kbd>enter</kbd> | Side questions | Asks in the side conversation under the cursor. |
| <kbd>a</kbd> | Side questions | Asks in a new side conversation. |
| <kbd>d</kbd> | Side questions | Closes the side conversation, after asking. |

The pane reopens on the tab and row you left it on.

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

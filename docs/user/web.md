# In a browser (`hmz web`)

`hmz web` opens every epic on this machine in a browser on it -- of every directory, as the
[daemon](/features/daemon) holds every directory's runs: each epic going as it happens, every
epic written down, starting one in any directory, what they spent, and what Humanize remembers.
It is one more window onto the runs `hmz` shows, not a copy of them. Start an epic in the
terminal and answer it in the browser, or the other way round. The same page reaches the epics of
[other machines](#daemons) -- over ssh, by a pairing code, or peer to peer -- one at a time, and
[tells you](#notifications) when an epic on any of them ends or asks you something.

::: info At a glance
- **You will** watch, steer and start epics in any directory from a browser, on this machine or
  another, read an epic written down, see what they spent, and be told when one needs you.
- **Use it when** a picture of a run reads better than a transcript: its agents and who handed
  to whom, each session's turns laid out over time, a week's spend by flow.
- **You need** Humanize installed as in [Installation](/user/installation), and a browser on the
  machine `hmz` runs on, or an ssh tunnel to it.
:::

## Try it

```sh
cd ~/tmp/humanize-demo
hmz web
```

It prints the address it listens at, opens your browser on it, and serves the page until you
press <kbd>ctrl+c</kbd>:

```console
$ hmz web
hmz web: http://127.0.0.1:43017/?key=Xq1rB0…
```

## How it works

The page is a client of this machine's [daemon](/features/daemon), as `hmz` is: `hmz web`
serves its files and carries it to the daemon, and the page asks the daemon everything itself.
It reaches a directory's runs through the same host as `hmz` opened there, so what one
window does, every other window sees: a line said in the browser is in the terminal's transcript marked `· by browser`, and a
question answered in the terminal stops waiting in the browser.

That has three consequences:

- **The run does not live in the page.** Closing the tab, or stopping `hmz web`, leaves the run
  going, as closing a terminal does. See [Leaving it running](/user/leaving).
- **One page for the machine.** Start `hmz web` anywhere: it serves every directory, and the one
  it was started in is only the one a new epic is offered first. It listens on the same port as
  the last time, so a kept address, and what the page keeps in your browser, still hold. A directory is reached only
  while the page shows it or acts on it, so a host with nothing to do still goes.
- **It only listens on this machine.** The address is `127.0.0.1` (`localhost` works too, over
  IPv4 or IPv6), and it carries a key made
  afresh each time `hmz web` starts. Opening the address hands your browser that key as a
  cookie, and only a browser holding it is answered. See [What it refuses](#what-it-refuses).

## The page {#the-page}

The page is laid out as a desktop chat app is. In it, every run of a flow is an **epic**, the
way every conversation of an agent is a session: the sidebar lists your epics as a chat app
lists its chats, and an epic opens out into its agents and the sessions each opened -- but a
[chat](/user/chat), which is its one conversation and opens into nothing.

| Where | What it shows | What you can do there |
| --- | --- | --- |
| **Sidebar** | A title row -- the mark, **Hide sidebar**, **Back**, **Forward** and the bell; in Humanize Desktop on macOS it stands beside the window's traffic lights, the mark before the bell -- then **New chat**, **New epic**, **Search**, **Flows**, then a quiet heading per directory -- every one an epic ran in or that was opened here -- with its chats and epics under it, the last updated first. Every row is its title and, straight after it in the same line, how it stands in quiet words. A [chat](/user/chat) is that one line and nothing else, as a chat app lists a conversation: **Running** while its agent answers, **Awaiting input** while it asks, **Failed** where it failed, and nothing once it rests; when it began is said where you point at it, and drawn at the row's end on a touch screen. A flow's epic is a row of two lines: its arrow, task and state -- `Running`, `Asking` (blinking while it asks a person something nobody has looked at here yet) and `Waiting` once you have, `Stopping`, `Done`, `Failed`, `Stopped`, `Budget spent`, `Unfinished` -- then its flow's name, and `live` where a host goes with it; `Running` without `live` is one another process goes with, read as it writes itself down. A directory shows its first 20 rows and ends with **Show N more**; the list reads 60 chats and epics at first, and ends with **Show more** while the daemon holds more and nothing else would bring them | Open a chat or an epic; press an epic's arrow to open it out into its agents, and each agent into its sessions; press a directory's name to fold it away; point at a heading for **Group and sort** and **+**, which starts a chat there, and right-click it for a chat or an epic there; point at a row for **More options**, the menu a right click on it opens. See [The list](#the-list) |
| **New chat**, **New epic** | Two forms, each opened from the sidebar; the page opens on **New chat**. A plain heading at the top, the chats that wait on you listed in the middle, and at the foot a box for the first message or the task, with where it runs under it at the left and, for an epic, the flow picked beside the heading | Start it; a chat's model and what it may touch are picked from the chips under the box at its right, and **Options** under an epic's box sets the rest up. See [Starting an epic](#starting-an-epic) |
| **An epic** | Its graph: who handed to whom -- a chat is only its conversation | Read it, steer it while it goes, export it, pick it up. See [An epic](#an-epic) |
| **A session** | Its thread, as the terminal draws it | Say a line into it, or answer what it asks, while the epic goes |
| **Flows** | **Installed**: a card for each flow on offer in the directory picked, its release and any newer one, and what one declares. **Flowverses**: a card for each index flows are installed from, and, one chosen, every release it lists | Start one, update, uninstall or copy it into the directory; install, switch or uninstall a release; add, fetch or remove a flowverse |
| **Search** (<kbd>⌘K</kbd>, or <kbd>Ctrl+K</kbd> off a Mac) | A box over the middle of the window: the field, the tabs **All**, **Chats** and **Epics**, then every chat and epic a line apiece, newest first, each saying how it stands in the words its row in the sidebar says it in -- a chat that rests says nothing -- and under them **Actions**, which stay in sight however many were found. Once you move to one, by key or pointer, a line over the foot says the rest of it: its folder, flow, agents, what it spent and how long it took; on a phone or a touch screen that stands under each | Type a word of the task; <kbd>↑</kbd> <kbd>↓</kbd> move, <kbd>Enter</kbd> opens (what you typed, even before it is listed), <kbd>Alt</kbd> <kbd>Enter</kbd> (<kbd>⌥</kbd> on a Mac) or the menu key opens the menu of the one you are on, <kbd>Esc</kbd> closes, and gives the keys back to where they were -- the box you were typing into; <kbd>Tab</kbd> stays within it; <kbd>←</kbd> <kbd>→</kbd> change the tab and <kbd>/</kbd> opens **Filters** -- how it went, folder, and, off **Chats**, flow -- while the field is empty; **New chat** or **Import** under **Actions**. Search leaves no step behind: **Back** after it is closed goes to what was open before, and from a chat it opened to the view it was opened over. See [Importing an epic](#importing-an-epic) |
| **Settings** | What Humanize remembers, and what the epics here spent | Change it, as [`/settings`](/user/settings) does |

The foot of the sidebar is one row: the [daemon bar](#daemon-bar) and, beside it, a gear that
opens **Settings**. The bar names the daemon the page shows,
its host and whether it is reached, and says how many epics are going on it. Its menu holds
**Daemon**, which opens a list of the daemons beside it to switch to, then **Settings** and
**Usage**. Where a newer Humanize is out, the bar is marked ↑ and its menu offers
**Update**, which copies `hmz update` to run in a terminal. The bell at the end of the sidebar's
title row opens your [notifications](#notifications); **Back** and **Forward** there step through
where the page has been, as a browser's do. <kbd>⇧⌘O</kbd> opens a new chat and <kbd>⌘.</kbd> folds the sidebar away;
off a Mac, as on Windows, they are <kbd>Ctrl+Shift+O</kbd> and <kbd>Ctrl+.</kbd>. Drag the
sidebar's right edge to size it -- the arrow keys do the same once it holds the focus, and a
double click makes it 275 pixels wide again, as it starts; the browser keeps the width. On a phone
the sidebar is a drawer behind the button in the corner: open, it holds the keys, and
<kbd>Esc</kbd> closes it.

### The list {#the-list}

**Group and sort**, on any heading of the list, arranges it; the browser keeps what you chose.
A heading is always there to hold it: with nothing to show, a group says **Nothing here yet**.

| Choice | What it does |
| --- | --- |
| **Group by** | **Folder** (as it starts): a heading per directory, and **No folder** last for what has none. **Date**: **Today**, **Yesterday**, **Last 7 days**, **Last 30 days**, **Older**. **None**: one list. By date or as one list, the directories stand last under **Folders**, a row each: click one for a new chat there, and right-click it, or press **More options**, for what a directory's heading offers |
| **Sort by** | **Last updated** (as it starts): what is going first, then by when each ended. **Created**: by when each began |
| **Show** | **Chats** and **Epics**, each on or off: off, the list leaves them out |
| **Reset to defaults** | By folder, last updated first, chats and epics both |

A row's menu -- **More options** at its end, or a right click -- starts with **Open**, **Pin**
and **Mark as unread**. A pinned chat or epic stands first, under **Pinned**, however the list is
grouped, until you **Unpin** it. **Mark as unread** puts the square of an unread notification
beside it until you open it or choose **Mark as read**, which also reads its notifications. Both
are kept by this browser.

Every view is an address: copy it, keep it, or open it in another tab. The address names the
daemon it shows, `#/@devbox/epics/…`, so a kept address opens on the same machine; one with no
`@` is Local's.

**Right-click** anything for what can be done to it: a folder in the sidebar (new chat here, new epic here, its
flows, search it, copy its path, settings), an epic (open, pin, mark as unread, its Exomyth, resume, a new
epic like it, copy its link, task or name, export, upload, stop), a chat (open, pin, mark as unread, a new chat
like it, copy its link, first message or ID, upload), an agent or a session, a node on the graph, a flow or flowverse card, a search
result, a line of a thread (copy it, or the whole thread). Only text to read or write -- a thread,
a task, a path, an error -- is selected as on a web page, and keeps the browser's own menu; the
page's buttons, tabs, labels and headings are not. What a menu sends off -- stopping or uploading an
epic, forgetting a folder, connecting a daemon -- says `Stopping…`, `Uploading…` and the like at
the foot of the page until the daemon answers. **Hover** over anything cut short -- a folder's name,
a task, a path -- to read it in full.

**Paths** are browsed for rather than typed: the folder button beside a path opens a list of
what is in a folder; click your way in, and press **Choose** (or click a file, where a file is
wanted). Typing still works, and completes as you go.

### An epic {#an-epic}

An epic opens as a graph, drawn from what the host tells the page, as the terminal interface's
monitor is:

- **Agents.** A node per agent, in a frame for the flow it worked in, saying what it runs,
  whether it is working or idle and for how long, and its tokens. A person the flow has is a
  dashed node. Click an agent to pick it out; the panel beside says the rest of it.
- **Handovers.** An arrow from one agent to the next each way the epic handed over, with how
  many times it did. The last handover is the red arrow, and the agent working now is lit.
- **Sessions.** On each node, a lane per session it opened, with a mark for each turn it took
  over the epic. A turn still open is lit. Click a session to read its thread.

The graph's paper has no edge: drag anywhere on it, a node included, or slide two fingers over a
trackpad to move it; pinch, or turn a mouse's wheel, to zoom about the pointer. **Recenter**, at the bottom left beside the zoom,
brings the graph back to the middle of the view.

The panel beside it (the button at the top right shows and hides it) holds:

- **Epic.** How long it has been going, what it has spent and how fast, a meter for each limit of
  its [budget](/features/allowances), the task, who handed to whom in words, **Spending** by
  model and kind of token (`≥` marks a figure that is only a floor), **Environments** -- where
  each session works and where its harness went, each a link into that environment's files, shell
  and changes while the epic is held (see [Into its environments](/features/environments)) -- the
  **Frontends** reading it, the flows going or the flows it called, and how it was set up and
  where it is written down. A chat calls this **Details**; its panes are picked on its bar, not
  by tabs (see [A session](#a-session)).
- **Aside.** A side question, as [`/btw`](/user/btw) asks it, of one session's side copy -- any
  epic's session, an earlier one forked from where that epic kept it, so it answers with that
  session's own history. Keep as many asides as you like: each is a side conversation of its
  own, on a tab named by the session it asks (`btw · <agent>/<n>`), and **New aside** opens
  another. A new aside's **Ask** chip, above its box, picks the session: each agent with the
  role it fills, opening onto its conversations, newest first; type in its box to narrow it. Its
  first question fixes the session it asks -- to ask another, open another aside. While one
  answers it says `… is thinking…`, and a pulsing dot marks its tab. The epic never sees any of
  it. Every question after the first goes on in the same side conversation until you press its
  **Close**, or a new epic starts. A question about the whole epic, or several, is
  [Ai-chan's](#ai-chan).
- **Board.** For an epic that holds one: edit, remove and add its lines. See
  [The mission board](/user/board).
- **People.** Each person the flow has: **Answer it here** holds the role for this browser,
  **Take it** takes it from another window, **Let go** gives it back; **Away** answers its
  questions with nothing, as [`/afk`](/user/afk) does.

And under the graph, while it goes:

- **Waiting for you.** A question the epic put to a person, as a card: the prompt, then what
  the flow handed you to read -- a diff file by file, a table, text, code, a picture, a chart,
  each long one folded behind a line that sums it up -- then how to answer. A question asking
  for text has its offered answers as buttons and a field for your own; one asking for a shape
  is one whole form, its suggested answers already picked, and **Send answer** saying what is
  left. A flow may draw a question with a [face](/weaver/faces) of its own instead, which
  **Plain form** swaps for the form. What you type is kept in this browser until it is sent,
  and a sent card folds to `You answered: …`. A question another window holds says `Waiting
  for <name> to answer`.
  A chat waiting for your next line puts nothing here, and what its agent asks is asked in its
  conversation. See [Questions](/user/questions#in-the-browser).
- **Say something.** <kbd>Enter</kbd> sends a line to the epic as a line typed in `hmz` goes
  (`the next turn`), to a role, to one session (marked `working` while it has a turn open), or
  to a person the flow has; <kbd>Shift</kbd>+<kbd>Enter</kbd> starts a new line. In a session's
  thread it goes into that session, or answers what that session's open turn asks. See
  [Talking to a running turn](/user/steering).
- **Stop.** Asks first, then stops the epic for everybody reading it. While it unwinds,
  **Force** closes every session under its turn. See [Stopping](/user/stopping).

### A session {#a-session}

A session opens as its thread, drawn as the terminal draws it: an agent's words on a dot, your
lines set apart on the right, a tool on a mark of its own, and `✻ Worked for …` closing a turn.

A [chat](/user/chat) is only its conversation, as a chat app's is, wherever it is opened: your
first message, then
each reply and each line you typed under it, on the right. The box under it is how you answer --
between turns it is your next turn, and while the agent asks something mid-turn it answers
that, the answers it offers buttons at the end of the conversation. It has no graph, no agents
or sessions under its row in the sidebar, no **Exomyth**, **Log** or **People**, and nothing
that ends it: it is `running` while its agent answers and `stopped` once the turn ends -- asking,
blinking, until you have looked at it, even once it has folded away. A chat is no epic: it is
kept as a record of its own, listed beside the epics, and its address is `#/chats/<id>`. Every
chat is its own, beside every other chat and flow of its directory: a new chat, or a new epic,
leaves the last one going, as a chat app's new chat does. A chat nobody has looked at for a
minute between turns folds away; say something in it and it carries on, the same chat, with what
was said before still above and an agent that remembers it. A turn that could not be taken
says so in the conversation, with why, and the chat waits for your next line. Where the
conversation itself cannot be carried on, the chat says why and answers what you said in a
new one. A chat an earlier Humanize wrote down as an epic is listed among the epics, its flow
said as `chat`: it is read as any epic written down, and nothing is said in it.

The box under a chat holds only **+**, what you type and the button that sends; what else
there is to pick is a row of quiet chips under it, at its right. The first says the model that
answers the chat, and its effort where one is set. Its menu says the rest of the chat's agent -- its CLI and its account -- and
**New chat** opens a new one in the same directory, where every part is picked. Where the
chat's CLI has a `/model` or an `/effort` of its own (Claude Code, Codex), the menu also lists
the other models its account runs, a box for one it does not list, and the efforts its model
takes: picking one says that line in the chat, which [goes on with the new model or
effort](/user/chat#the-chats-agent).

The box under a chat takes what the agent's CLI takes at its own prompt, as `hmz` does in a
chat: typing `/`, `$` or `@` offers the CLI's own commands, skills and files, the names
Humanize keeps, and the flows, each tagged with where it comes from, and each line is
[served](/user/chat#what-a-line-means) as its CLI would serve it. A `!` line and what it printed
are drawn as a shell draws them. The box itself says only **Reply…**; **+** at its left
offers what else it takes -- **Add files** types `@`, **Slash commands** `/`, **Skills and
flows** `$` and **Run a shell command** `!` -- and what it offers as you type is grouped as **Commands** and
**Skills** (the CLI's own), **Humanize** (the names Humanize keeps), **Flows**, and for `@`
**Files** (the folder's paths) and **Mentions** (what else the CLI takes after `@`).

A chat reads as a chat app's session. Its bar holds its title and, right after it, one
**More options** menu (`⋯`); at the far right, a button each for **Details**, **Terminal**,
**Changes** and **Files**, then **View options**. Each button opens its pane beside the
conversation and shuts it again -- the bar runs over the pane too, so the button stays where
you pressed it: **Details** is what the chat is, and the other three are the
terminal, the changes and the files of the [environment](/features/environments) it works in, there
while a host holds the chat; one that cannot open says why where you point at it. **View
options** holds **Side questions**, **Board** while the chat keeps one, and **Ai-chan**, which
opens [her drawer](#ai-chan). The pane open is headed by its name and has no tabs of its own:
the bar picks it. No pane is open until you open one. How the chat stands is said in a quiet line over its box, only while there is
something to say: who **is responding** while a turn is open, that it is waiting for you, or
that it failed. While a turn is open the button that sends is **Stop**: it stops that turn, and
the chat stays, waiting for your next line; what you type and send with <kbd>Enter</kbd>
meanwhile is still delivered to that turn. The menu holds what a right click on the chat offers
-- a new chat like it, copying its link, **Upload** -- with **Environment** while a host
holds it, and **Skill or flow**: whether a `$` name that is both a skill and a flow uses the
skill or starts the flow, with a mark on the one in force and whether that comes from the
settings or from this chat. Picking the other sets this chat's own
[preference](/user/chat#a-name-that-is-both), as `/prefer` does.

The pane beside a chat has **Details** in place of **Epic** -- its usage, its first
message, where it works, and under **About this chat** its ID, where it is saved, its
folder, when it started, its model, options, limits and sessions -- and **Side questions**
in place of **Aside**, which works the same.

The next chip under the box names what the chat's agent may touch -- **Read only**, **Edit
this folder** or **Full access** -- and opens a menu of the three, the one in force checked.
Picking another sets the chat's [permission](/user/chat#permission) from your next message; on
a chat that has folded away, it is what the chat is carried on with. The last is **Usage**, a
ring with, once there is something to say, what the chat has spent or the tokens it has written
beside it: click it for **Details**.

Each node's **log** row is that agent's transcript across its sessions, and a person's node
opens what they were asked and answered, and what the flow showed them without asking. A line typed under one goes to whose it is. There is
no log of every session at once: under an epic in the sidebar are its agents and their
sessions.

**List**, at the top right of the graph, draws the agents as a list instead, the working first;
your choice is kept in this browser.

### An epic written down

An epic that has ended keeps its graph and its panel. Opened later, it says how it was set up
-- its agents, environments, params and budget -- the flows it called, its sessions, what it
spent, and how long it took, with how much of that was spent working.

- **Read its turns** reads who handed to whom, and each session's turns, out of the logs it
  kept, as [tracing](/user/tracing) does. It takes a moment on a long epic. Opening a session
  reads its thread the same way.
- **Export** (the arrow at the top) downloads the epic as one archive, struck of credentials;
  a chat is not exported. See [Exporting a run](/user/export).
- **Upload** (the up arrow at the top, or in the epic's menu; in a chat's **More** menu) backs it up now to the targets it
  was started with, else the defaults, and says which at once; hover it for how its last
  backup to each target went. See [Backing epics up](/user/backups).
- **Pick it up** opens a new epic on it, where its flow can be picked up. See
  [Picking a run up](/user/resuming).

### Exomyth {#exomyth}

**Exomyth** (the chart at the top of an epic, or its menu) lays the epic out over time, as
[Perfetto](https://ui.perfetto.dev) lays out a trace -- but with **every session its own
process**, under the session or the flow that started it. It reads the epic's
[timeline](/reference/tracing#timeline) out of the logs its agents kept; an epic still going is
read again every two seconds while the tab is shown.

- **Timeline.** The epic's flows, each session and each program a [profiled](/user/tracing)
  epic ran, a row each, with a track per lane of its spans: sessions, turns, model calls,
  tools, messages and events, each category in its colour. The triangle by a name folds a
  process to one row; **Expand** and **Collapse** do every one.
- **Flame.** The same spans as a flame graph, over the stretch picked on the Timeline or the
  whole epic: under the epic, each agent (its role) with its sessions merged -- **Merge
  sessions** off puts each session apart -- or each flow or program, then its turns and what
  they did, by name. Weigh it by **Time**, **Tokens in**, **Tokens out** or **Count**; **Bottom
  up** turns it into a flame. Under it, **Slices** sums every name: count, total and own time,
  average, p50, p95 and longest, and tokens.

| Do (Timeline) | To |
| --- | --- |
| <kbd>W</kbd> / <kbd>S</kbd>, or <kbd>Ctrl</kbd>+wheel, or a pinch | Zoom in and out where the pointer is |
| <kbd>A</kbd> / <kbd>D</kbd>, or a sideways or <kbd>Shift</kbd>+wheel | Pan |
| Wheel | Scroll through the processes |
| Click a span | Pick it: the panel says what it is and what it carried |
| Double-click a span, or <kbd>F</kbd> | Zoom to the span or process picked |
| Drag across the chart or the ruler | Pick a stretch of time: how long, and the spans and tokens in it by category |
| <kbd>/</kbd> | Find spans by their name; <kbd>Enter</kbd> or <kbd>N</kbd> goes to the next, <kbd>Shift</kbd>+<kbd>Enter</kbd> or <kbd>Shift</kbd>+<kbd>N</kbd> the one before |
| <kbd>0</kbd> or <kbd>Home</kbd> | Show the whole epic |
| <kbd>Esc</kbd> | Let go of what is picked |

| Do (Flame) | To |
| --- | --- |
| Point at a frame | Its total, its own, its share of the whole and how many spans |
| Click a frame | Zoom to it; click one above it, or a name in the crumbs, to zoom back out |
| <kbd>Esc</kbd> | Zoom out a level |
| <kbd>/</kbd> | Light the frames whose name holds the words, and say what share of the whole they hold |
| Click a column's heading | Sort the slices by it; again, the other way |
| Click a slice | Light its frames; **Show in timeline** finds it on the Timeline |

With nothing picked, the panel says the epic's figures, each category's spans, time and
tokens, and every process -- click one to pick it.

### Importing an epic {#importing-an-epic}

Somebody sent you a `.hmzepic`? Press **Import** under **Actions** in **Search**, or right-click between the epics in
the sidebar, and pick the file --
or drop it anywhere on the window. It is read back in on the daemon the page shows, under the
directory it ran in, and opens
once it is in. One you already have is refused, with **Open** to go to it.

An imported epic is read as any other. It is picked up only where the directory it ran in is
here at the same path, holding the commit its archive says; otherwise it says why under it,
`Imported · not resumable here: …`, and offers no **Resume**. A `.hmzepic` already on this
machine is imported by its address too, `#/epics/import?path=<file>`, once you press **Import**
under its path, and opens on its [Exomyth](#exomyth) -- as [Humanize Desktop](/user/desktop#opening-a-hmzepic)
opens one you double-click. Where `hmz` runs in WSL, a Windows path, `C:\…` or `\\wsl$\…`, is
read as WSL names it. See [Exporting a run](/user/export#importing-a-run).

### Starting an epic {#starting-an-epic}

A new chat and a new epic of a flow are two forms, each opened from the sidebar, in one
frame: a plain heading at the top, and the box you type into docked at the foot of the page.
Both keep where they run under that box, at its left, as two quiet chips. **Environment** names
the [daemon](#daemons) the page shows -- **Local**, or a remote one -- and picks another,
as the daemon bar at the foot of the sidebar does; **New environment** opens the daemons'
settings. The folder chip names the directory: click it to pick another by its name -- point at
one for its whole path -- **Open folder…**, or **No folder**.

A new chat starts a [chat](/user/chat): pick the directory, or **No folder**, from the folder chip; the
model, from the chip under the box at its right; and type the first
message. <kbd>Enter</kbd> starts the chat, and the page goes to its conversation. There is no
flow, budget or params to set. **+** in the box offers **Add files**, which types `@` and
completes the folder's files -- with **No folder** picked there are none to name, and it says
**Pick a folder first**; what else a line can start with is offered [under a
chat](#a-session), once there is one.

The middle of the page is empty, but for the chats of this daemon that wait on you, each a row
saying **Asked a question** that opens its chat. **✕** in a row takes it off the list, in this
browser, until that chat asks something else.

The chip says the model that will answer, and its effort where one is set, starting from the
agent that directory last chatted with. It opens a menu:

- The models the CLI runs as the account chosen, one a row, the one chosen marked; point at one
  for the name its CLI knows it by.
- **Effort**, one row saying the effort chosen, opens the efforts the model chosen takes, where
  it takes any; **Default** leaves it to the model.
- **More**, one row, opens the rest: **Other model**, where a model the CLI does not list is
  typed; the **CLI** that runs the chat; the **Account** it runs as (**Local** is this machine's
  own sign-in; **Add account…** opens Settings); and **Refresh models**, which asks the CLI what
  it runs again. A CLI never asked what it runs is asked the first time it is picked, which
  takes a few seconds.

What is picked is an agent as `-a` spells one, `cli[@account]/model[:effort]`; resting the
pointer on the chip says it in full.

The chip after it, **Edit this folder** to begin with, is what the agent may touch: its
[permission](/user/chat#permission). The ring that ends the row is **Usage**: it opens what the
folder picked has used, in Settings.

**New epic** opens on the directory `hmz web` started in, or the folder whose **New epic here** was
picked from its right-click menu -- its **+** opens a chat there -- and on the flow that directory
last ran; pick another flow beside the **New epic** heading, and another directory from the folder chip under the box.
**+** in the box offers **Add files**, as on a new chat.
A chat is not among the flows. Where no flow is installed -- Humanize ships none -- the middle
of the page says so, and **Open Flows** there, as in the flow's menu, goes to
**Flows** to install one; until then nothing starts. **Open folder…**
takes any directory by its path, completed as you type, and keeps it in the sidebar. **No
folder** works in none of yours: each epic started so gets a new directory of its own in the
temporary directory, made as it starts, and set up as the directory `hmz web` started in is; the
epic then shows in the sidebar under that directory. Type the
task and press <kbd>Enter</kbd>. **Options**, under the box at its right, opens what the flow is set up with, as that
directory last set it up:

- **Agents.** Per role: the **CLI** (installed ones that can fill it), the **Account** it runs
  as (**Local** is this machine's own sign-in; **Add account…** opens Settings), the **Model**
  and the **Effort**. A CLI never asked what it runs is asked the first time it is picked, which
  can take a while; the refresh button asks again. Where it cannot say, pick **Other…** and type
  the model.
- **Environments.** Per role: the **Backend**, the **Runtime** of it (or **Add runtime…**, or
  for ssh **Other host…**), and the **Directory**, completed as you type on this machine.
- **Parameters**, the **Budget**, **Backup** -- the [targets](/user/backups) the epic is backed
  up to, the defaults ticked until a choice is saved -- and **Profile flow** and **Profile environment**. **Save** keeps them all for that directory
  without starting an epic, as saving `/flow` does; starting keeps it too. The chips beside **Options** say what is set, where the window has the room: on a phone **Options** alone does, once opened. Every flow
needs at least one limit. The page goes to the epic once it starts.

### Ai-chan {#ai-chan}

Ai-chan is an agent you operate Humanize through by talking to her. Her avatar, at the right of
every view's bar, opens and closes her drawer beside the view -- a chat's bar ends as a chat
app's does, and offers her as **Ai-chan** under **View options** instead; it stays open as you go from view
to view, until you close it. What you type in it stays in it: a new chat or a new epic that
finishes opening beside it meanwhile does not take the keys. On a phone it covers the view:
close it with its button or <kbd>Escape</kbd>.

The drawer lists every conversation with her on the daemon shown, newest first: its title, what
it reaches, its nous, its preset, whether its network is on, and whether she is **Answering**,
**Waiting** for you, or has **Folded away**. **Forget** forgets one, once you confirm. The
drawer is the only place her conversations are listed: none is in the sidebar, nor counted among
a workspace's epics, while it lasts or once forgotten.

**New** asks what the conversation is fixed to:

- **Scope.** **Daemon** -- every workspace and epic --, **Workspace** -- one workspace and its
  epics --, or **Epic** -- one epic. It starts on the epic the view shows, else the workspace,
  else the daemon.
- **Nous.** Starts on the one **Settings › General** names for her; with none named there,
  pick one.
- **Preset.** `read-only`, the default, or `danger-full-access`; and **Network**, off by default.
- **Title**, from the task where left empty.

Type the task and press <kbd>Enter</kbd>: the conversation opens as a chat, her answers beside
her avatar and each tool she calls a line to open. While she answers, **Stop** stops her turn and
leaves the conversation waiting for your next line. One that folded away is carried on by opening
it and saying something.

### Settings {#settings}

Settings has two groups. **App** is the page's own: how it is drawn, the daemons it reaches and
what it tells you of them. It is the same whichever daemon is on screen. **Daemon** is the same
pages as [`/settings`](/user/settings), in the same order, and what the epics spent, all of one
daemon:

| Page | What is there |
| --- | --- |
| **Themes** | The [themes](#themes) of this browser, and which two **Auto** follows your system with |
| **General** | Whether a turn's working is shown, **Ai-chan** -- the nous a new [Ai-chan](#ai-chan) conversation starts with, none until one is picked -- and [error reports](/user/reporting) |
| **Accounts** | Every [account](/user/settings#accounts) by its CLI, way in and the names of what it sets: ask what it runs again, **Edit** it (what you leave blank stays as it was), copy it to another CLI, remove it, or make one |
| **Nous** | Every [nous](/user/settings#nous): how a failed turn is tried again and where it goes next, and each virtual nous's graph, edited node by node |
| **Runtimes** | Every runtime: add one from its backend's fields, change, check or remove it, or bring hosts in from your ssh config |
| **Backup** | Every [backup target](/user/backups): its repository and branch, when an epic goes to it (**On session close**, **Every N minutes**, **On epic end**, or none: by hand only), and whether it is a **Default**; add, edit or remove one; **Download** an epic a target holds, as in [Downloading an epic](/user/backups#downloading-an-epic). A URL is shown with nothing signed into it |
| **Workspace** | What a directory was last set up with, and forgetting it -- which also takes it out of the sidebar where no epic ran there |
| **Usage** | What the epics spent, of every directory or of one, by day and by flow, looking back 7, 30, 90 or 365 days |
| **Daemons** | **Local**, always there, and every remote daemon with its kind and state (up, connecting, installing, failed or idle): add or **Edit** one as [Adding one](#adding-a-daemon) says, **Connect** or **Remove** one, asked first; **Pair a device** and **Devices** for each that is up; the STUN and TURN servers WebRTC uses |
| **Notifications** | Which notifications appear, of every daemon: **Done**, **Failed**, **Stopped**, **Questions** and **Waiting**, and whether the **System** shows them too. In a browser, **Allow** asks it for permission; the desktop app needs nothing more. Kept in this browser, never per daemon |

Above the **Daemon** pages, **Daemon** picks which daemon they read and write: the one on screen
until another is picked. It goes into the address as `?daemon=<name>`, so a daemon's page can be
kept and opened again. Picking one changes nothing else on screen.

**Batch apply**, on **General**, **Fallback**, **Runtimes** and **Backup**, copies what the page
holds to other daemons at once. Tick the daemons, or **All**, then **Apply**. Each daemon then
says **Applied** or why it refused. **General** sends the form as it stands, saved or not.
**Backup** sends every target and default, in place of the daemon's own. A target signed into its URL
is refused there, since the URL is never shown whole. **Nous** and
**Runtimes** send each nous or runtime, written over the one of the same name there, or added.
Nothing a daemon already has is taken away. **Accounts** cannot be copied, since their secrets
are never shown (**Secrets stay put**). **Workspace** and **Usage** are of one daemon's
directories, and have no **Batch apply**.

While a page is read, it says **Reading…**. What a page already shows -- a range or a workdir
picked on **Usage** or **Workspace**, a directory gone into in a path's browser -- stays, faded,
until what replaces it is read.

An account is never shown by its values: a page lists the names of the variables it sets, and
nothing else. A way in that runs a CLI's own sign-in, such as `login`, needs a terminal: it is
offered as `(at a terminal)` and made from `/settings` in `hmz`.

### Themes {#themes}

The page is drawn in a theme. Humanize comes with **presets**, each a pair of a light theme and a
dark one: its own, **Humanize Green**, and **Temperate Gold**, **Concordant Scarlet**,
**Restrained Crimson**, **Critical Teal**, **Desirous Indigo**, **Peaceful Lilac**,
**Hateful Silver**, **Devoted Pink**, **Self-Negating Plum**, **Dominant Azure**,
**Surviving Jade** and **Lamenting Orchid**.

A theme is picked only under **Settings → Themes**. **Auto**, the default, follows your system
with a pair: under **Auto** pick a **Pair** -- or any theme for the system's **Light** and any
for its **Dark**, your own included. Click a preset's light or dark
swatch to use that one theme whatever the system is.

**New** makes a theme from the one showing, and **New pair** a pair of your own -- a light theme
and a dark one, which Auto can follow your system with as it does a preset -- from the pair
showing. **Duplicate** copies any theme, or a whole pair. **Edit** opens one of yours:

- **Name**, and the **Base** it is made on, Light or Dark, whose colour any you leave blank is.
  In a pair, the name is both themes', and **Side** switches between its light and its dark.
- Every colour, by what it colours: **Backgrounds** (page, sidebar, surface, raised),
  **Text**, **Controls** (button, its text, primary button, its text, field, edge), **Lines**,
  **Accents** and the **Graph**'s lanes. Pick one or type any CSS colour, such as
  `#102030` or `rgba(255, 255, 255, 0.1)`; × gives back the base's.
- **Pictures** behind the **Page**, **Sidebar**, **Panel** and **Dialog**: a PNG, JPEG, GIF,
  WebP, AVIF or SVG -- an animated SVG moves -- each to **Cover**, **Fit** or **Tile** its plane.
  Where your system asks for reduced motion, a moving picture is held still.

The page shows a theme as you change it, and keeps every change at once. **Export** saves a
theme, or a pair with both its themes, pictures and all, as a `.hmztheme` file; **Import** reads
one back, here or in any other browser. Themes are kept by the browser, as the rest of what the page remembers is, so another
browser -- or [the app](/user/desktop) -- has its own until you import them there.

A `.hmztheme` file is JSON:

```json
{
  "hmztheme": 1,
  "name": "Night",
  "base": "dark",
  "colors": { "paper": "#102030", "primary": "#ec6fa3" },
  "images": { "page": { "fit": "cover", "data": "data:image/svg+xml;base64,…" } }
}
```

A pair holds both its themes, each with its `colors` and `images`, in place of a `base`:

```json
{
  "hmztheme": 1,
  "name": "Dusk",
  "light": { "colors": { "paper": "#fff8e0" }, "images": {} },
  "dark": { "colors": { "paper": "#201008" }, "images": {} }
}
```

`colors` is keyed by the page's colour tokens (`paper`, `side`, `surface`, `raised`, `ink`,
`ink-2`, `ink-3`, `on-ink`, `on-fill`, `link`, `control`, `control-ink`, `primary`,
`on-primary`, `field`, `edge`, `line`, `line-strong`, `hover`, `scrim`, `green`, `cyan`,
`cyan-ink`, `pink`, `pink-ink`, `lavender`, `gold`, `done`, `fail`, `lane-1` to `lane-6`), and
`images` by plane (`page`, `sidebar`, `panel`, `dialog`). Importing keeps what a theme can hold
and drops the rest: an unknown token, a value that is not a colour, a picture that is not an image.

## Example: start a chat in the browser, answer it in the terminal

Start `hmz web` in a project, which opens on **New chat**:

1. Pick a model from the chip under the box, such as **Haiku 4.5**, type a first
   message and press <kbd>Enter</kbd>. The page goes to the chat, `#/chats/<id>`.
2. When the agent has answered, the chat waits for your next line, typed in the box under it.
3. In a terminal in the same directory, run `hmz`, which opens on a new chat of its own. Type
   `/resume` and press <kbd>enter</kbd> on the chat you started: it is still
   going, so it is read where it is, waiting for you to say what next.
4. Answer it in the terminal. In the browser, your answer is a line of yours in the
   conversation, and the agent's reply follows it.
5. Type `/clear` in the terminal. A chat is never ended: `/clear` starts another, and the
   first goes on in the browser until nobody reads it, when it folds away.

### Check it worked

- The terminal's transcript shows the task you typed in the browser, marked `· by browser`.
- The sidebar lists the chat, with nothing beside it: a chat says **Running** only while its
  agent answers;
  **Search** shows what it spent.

## Daemons {#daemons}

Each machine whose epics the page reaches is a **daemon**: the [daemon](/features/daemon) there
holds its runs. **Local** is this machine, always there and never removed -- where `hmz` runs in
WSL, as with Humanize Desktop on Windows, the WSL distribution, its host shown as `Debian (WSL)`. Every other
is a remote daemon, of one of three kinds: **SSH**, an ssh host reached the way `ssh` reaches
it, with your keys and your ssh config; **P2P**, a machine reached [over EasyTier](#over-easytier)
with a secret you both know; or **Paired**, a machine whose daemon made a pairing code you
claimed here.

The page shows one daemon at a time: the sidebar's folders and epics, a new epic, search,
flows and the Daemon pages of Settings are all that daemon's. To see another's, switch to it.
The daemon is part of every address, `#/@<name>/…`, so a tab can stay on one while another tab
shows a second.

### The daemon bar {#daemon-bar}

The foot of the sidebar names, on one line, the daemon showing, its host, a dot for whether it
is reached, and how many epics are going on it. Click it for its menu:

- **Daemon**, which opens beside it every daemon, with whether it is reached; pick one to switch
  to it. A remote daemon is connected to when you pick it. **Connect** on one that failed tries it
  again, and **Manage** opens **Settings → Daemons**.
- **Settings** and **Usage**, and **Update** where a newer Humanize is out.

A daemon is in one of these states:

| State | What it means |
| --- | --- |
| `not connected` | Not connected to yet. |
| `connecting` | A route is being opened: `ssh` reaching the host, EasyTier joining the network, a relay joining, TLS and hello. |
| `installing` | The host has no `hmz`, or another version, and it is being installed (see [What happens on connect](#on-connect)); or, for a P2P daemon, `Downloading EasyTier <version>` here. |
| `up` | Reached: its epics are on the page. The bar says `N live` while epics are going on it, and `idle` while none is. |
| `failed` | It could not be reached; the menu says why, and **Connect** tries again. |

### Adding one {#adding-a-daemon}

**Settings → Daemons** lists Local and every remote daemon, each with its kind -- and mode, as
`SSH · SSH Config`, `SSH · Custom` or `P2P · EasyTier` -- what reaches it, and its state.
**New daemon** asks you to pick a kind, **Code**, **SSH** or **P2P**, and a mode under it; then
the **name** the page calls it -- letters, digits, `.`, `_` and `-`; `local` is Local's and
cannot be taken -- and how to reach it:

| Kind | Mode | What you give |
| --- | --- | --- |
| **Code** | | A pairing code, `hmz-pair:…`, made on that machine by `hmz daemon pair` or by **Pair a device** on a page that reaches it. It is claimed at once, over the routes it carries, and the daemon is kept only once the claim succeeds -- held to that machine's id from then on; otherwise the form says why. |
| **SSH** | **SSH Config** | A `Host` of your `~/.ssh/config` not yet added, picked from a list; picking one fills in the name. Nothing here writes to the config. It is resolved through your config every time, so editing the config edits the daemon. |
| **SSH** | **Custom** | The host, user, port, identity file, proxy jump and options, a part at a time, as for an [ssh runtime](/user/settings#an-ssh-host). **Import from SSH config**: pick one of its hosts and **Import** fills them in from what your config says of it; they are kept by the page, and the config is not read again. |
| **P2P** | **EasyTier** | The secret that machine's EasyTier entry holds: at least 16 bytes in UTF-8, shown masked. And the [**Nodes**](#easytier-nodes) both machines meet on, at least one: tick any of the EasyTier community's shared nodes, each listed with whether it is up and how much of the last 24 hours it was, or type one in as `tcp://host:port` (or `udp`, `ws`, `wss`, `quic`, `wg`) and **Add node**. Where the community list cannot be read, the page says why, and you type the nodes in. |

**SSH** and **P2P** are offered only where the page can open their routes: in a browser,
through `hmz web`; in [Humanize Desktop](/user/desktop), through the app.

Edit a daemon, connect to it to check it, or remove it, which asks first. Editing opens the form
in the daemon's own kind and mode, with every route it is reached by, in the order they are
tried, to add to, take from or reorder; a P2P daemon's secret is never shown again, and leaving
it empty keeps it. Removing one forgets how to reach it, and nothing on the host: its epics,
its `hmz` and its pairing of this machine stay there.

The daemons are kept by this browser, in its IndexedDB: each its name, the daemon id pinned,
and its [routes](/reference/settings#settings-yaml). Another browser, Humanize Desktop, and `hmz`
in a terminal each keep their own.

Below the form, **Devices** has, for each daemon that is up, **Pair a device**, which makes a
pairing code for another machine or browser to claim -- shown with when it expires, and a
button that copies it -- and the devices paired with that daemon, each with when it was last
seen; **Revoke** one, asked first, and it can reach that daemon no more.

### What happens on connect {#on-connect}

Connecting races the daemon's routes, in the order they are kept, each a quarter of a second
after the one before. In a browser, Local is reached through `hmz web`, and every other route
but a WebRTC one through `hmz web` too, which opens it from this machine: over `ssh`, it runs
`hmz daemon connect --stdio` on the host through a login shell, whose standard streams carry the
session -- what the login shell's profile prints goes to standard error, and the session begins
after the line `hmz-stdio/1` that command prints first, so what the shell `ssh` itself starts
prints (a `~/.bashrc` that echoes) is skipped too; over a TCP
port, a relay or EasyTier, it opens mutual TLS held to the daemon's id, which pairing gave it.
The first to say hello as that daemon wins, and the others are closed. A daemon first reached
over `ssh` has the id it answered pinned, and one that later answers as another fails with
`<name> is not the daemon it was paired with.`

- **It brings the host the same Humanize.** Before it starts anything over `ssh`, it asks the host's
  `hmz --version`, through a login shell with `~/.local/bin` on its `PATH`. Where there is none,
  or one of another version, it runs `uv tool install --force --python '>=3.12' 'hmz==<version>'`
  on the host, at this machine's version, installing uv there first where the host has none.
  The daemon says `installing` meanwhile.
- **It never replaces an `hmz` holding running epics.** Where the host's daemon has epics
  running, or it cannot tell, the `hmz` there is left as it is, and the daemon says why.
- **It keeps reaching it.** A session that drops is tried again after a second, the wait
  doubling after each further failure up to a minute.
- **The epics outlive it.** Closing the page, or stopping `hmz web` here, closes every session,
  and every `ssh` and EasyTier it started; the epics there keep going, held by that host's
  daemon. See [Leaving it running](/user/leaving).

### Over EasyTier (P2P) {#over-easytier}

Where you cannot `ssh` to a machine -- it is behind a NAT, or you only reach it out -- its
daemon can listen on an EasyTier network instead. On that machine, give its `~/.hmz/settings.yaml`
an EasyTier entry -- a secret of at least 16 bytes and the node both machines are to meet
through, one of your own or a public one -- and a listener on it:

```yaml
easytier:
  home:
    secret: "<at least 16 bytes>"
    nodes: ["tcp://node.example:11010"]
listen: ["easytier:home"]
```

and make a pairing code there, `hmz daemon pair`. Then, on your own machine, add a **P2P** ›
**EasyTier** daemon of the same name, with the same secret and at least one of the same nodes:
it writes the EasyTier entry of that name here, which the route `easytier:home` opens with; in
[Humanize Desktop](/user/desktop), it writes it to the app as well, which opens the route itself. A
route over EasyTier is held to the daemon's id, which only pairing gives: claim that machine's
code under **Code**, and the daemon it adds is reached over EasyTier. Until it is paired, a P2P
daemon fails with `easytier:home needs the id of the daemon it reaches.`

- <span id="easytier-nodes"></span>**The two ends meet through a shared node.** EasyTier runs no public node
  of its own, so you name one or more each side: a URL such as `tcp://host:11010` (or `udp`,
  `ws`, `wss`, `quic`, `wg`). The form lists the nodes EasyTier's community shares, as the
  status page EasyTier's own apps read says, each with whether it is up and how much of the last
  day it was; check those you want and type any others. Where that list cannot be read from
  your network, the form says so and takes typed nodes alone. The two ends reach each other
  directly where they can, and are relayed by the node where they cannot; a node never learns
  the secret. [`HUMANIZE_EASYTIER_NODES`](/reference/environment#humanize-easytier-nodes) reads
  the list from another status page.
- **Nothing to install there but Humanize.** Both sides download
  [EasyTier](https://easytier.cn)'s `easytier-core` from its GitHub release into
  `~/.hmz/easytier/<version>/` the first time, checked against the checksum Humanize pins, and
  reuse it after. It runs without root and without a network device.
- **The secret stays with you.** The EasyTier network's name and password are each derived from
  the secret; the secret itself is never sent, nor put on a command line, and the page is never
  handed it back once written. Anyone with the secret can reach that machine's daemon port, but
  is still held to mutual TLS and pairing there; keep it as you keep a password all the same.
- **The same Humanize.** Nothing is installed on that machine from here: update it there with
  `hmz update`.
- **The epics outlive it.** Taking `easytier:home` out of `listen` stops its EasyTier, never an
  epic.

## Notifications {#notifications}

The page tells you when something happens that you may want to look at, on **every** daemon,
not only the one showing:

| Kind | When |
| --- | --- |
| **done** | An epic ended, done, or a [chat](/user/chat) finished a turn. |
| **failed** | An epic failed, crashed, ran out of its budget, or was refused. |
| **stopped** | An epic was stopped. Never a chat: leaving one is no news. |
| **asked** | A flow put a question to a person: the outworlder. See [Questions](/user/questions). |
| **listening** | A flow waits for what to say next. A chat that finished a turn is **done**, never this. |

Each says which daemon, which directory and which epic or chat it came from, and what was asked
or how it ended.

- **The bell**, at the top of the sidebar, counts the ones you have not read. Click it for the
  **menu**: the latest notifications of every daemon, newest first, each labelled with its
  daemon. Click one to open its epic or its chat, switching to its daemon; mark them all read, or clear
  them. This browser keeps the newest 200.
- **Toasts.** A new notification also shows as a card in the corner of the page for a few
  seconds.
- **System notifications.** While the page is hidden or not focused, a notification is also
  one of your system's: the browser's, or, in [Humanize Desktop](/user/desktop#notifications), a
  macOS one. Clicking it brings the page back on what it is about.
- **Sidebar marks.** An epic or a chat with a notification unread has a square beside it in the
  sidebar, and so does its workspace while folded. Opening it reads them, as does
  **Mark as read** in its menu.

None is shown of the epic or chat you are looking at -- a question or a chat turn there included: it is
read as it comes.

The page asks each daemon for its notices itself, while it is reached: Local always, a remote
daemon once it is `up`. It takes up again after the last it heard of each, so what happened while
the page was closed, or a daemon out of reach, is told once it is back.

**Settings → Notifications** switches each kind on or off, and system notifications as a whole.
A browser shows system notifications only once you allow it: press the button on that page,
which asks the browser. A kind switched off is not shown, kept or counted. These are App
settings: they are kept by this browser, with the notifications themselves, and hold for every
daemon, never one daemon apart. `hmz` has its own, on its
[Notifications page](/user/settings#notifications).

## From another machine {#over-ssh}

`hmz web` only listens on the machine it runs on. To use it from your laptop while `hmz` runs on
a server, the simplest way is to add the server as a [daemon](#daemons) of the page on your
laptop. To serve the page from the server itself instead, forward a port over ssh:

```sh
ssh -L 8765:127.0.0.1:8765 you@devbox
```

Then, in that ssh session:

```sh
cd ~/src/api
hmz web --port 8765 --no-open
```

Open the printed address in your laptop's browser. A port forwarded to another number on your
side works too: change the port in the address and keep the key. So does any name the port is
reached by -- a forwarded port in VS Code or Codespaces, or a reverse proxy on the server such
as `tailscale serve` -- as long as the proxy runs on the same machine as `hmz web`: change the
start of the address and keep `/?key=…`.

## What it refuses {#what-it-refuses}

Anything that can reach a port on this machine could otherwise drive your runs, so the page is
answered only where it was meant to be:

- **Only this machine.** It listens on the loopback alone, and answers only connections from
  this machine -- whatever name they used, so a port forwarded or proxied from here works. A web
  page elsewhere that points a name of its own at your machine still reads nothing: your browser
  never hands that name the key's cookie.
- **Only the browser it was opened in.** The key in the address becomes a cookie that scripts
  cannot read and other sites cannot send. A browser without it is told it is not let in.
- **Only its own page.** The page reaches a daemon only over the WebSockets `hmz web` opens for
  its own address: a page elsewhere -- even one served from another port of this machine --
  cannot open them, and a form on another site cannot post to it.
- **The key on no command line.** The browser `hmz web` opens is opened on a page only you can
  read, which sends it on to the address: another account on a shared machine cannot read the
  key off the browser's command line.
- **No secret on the page.** Accounts are shown by the names of what they set, never by a
  value.
- **A flow's face fenced in.** A [face](/weaver/faces) a flow brings runs in a sandboxed frame
  of its own origin, with no cookies, no network and no way to the daemon. All it can do is
  answer the question it was handed, and that answer is checked as any other is.

The key changes every time `hmz web` starts, so an address from an earlier one lets nobody in.

## Variations

- **A port of your own.** `hmz web --port 8765` listens on that port. Without it, `hmz web`
  listens on the port it listened on last time, kept in `~/.hmz/web-port`, or any free one where
  that is taken or none is kept; `--port 0` picks any free one.
- **No browser.** `hmz web --no-open` only prints the address, for a browser of your choosing.
  On a machine without a desktop -- one reached over ssh -- it opens none anyway.
- **Stopped by what started it.** `hmz web --attached` stops once its standard input closes,
  so a program that starts it -- a desktop app, a script -- takes it down by exiting, even by
  crashing.

## Troubleshooting

### `This browser is not let in.`

The browser has no key, or the key of an `hmz web` that has since stopped. Open the address the
running `hmz web` printed, key and all.

### `hmz: the web interface cannot be served: … Address already in use`

Something already listens on the `--port` you gave: another `hmz web`, perhaps. Pick another,
or leave it out.

### `hmz: … older Humanize …`

This machine's daemon is one an older Humanize started, and `hmz web` serves nothing over it.
Stop it with that version, as the message says, and start `hmz web` again.

### The sidebar says why the host let it go

The host holding the runs went: it was closed, or it let this window go. The page reaches the
runs again by itself a moment later, starting a host where none is, and the daemon bar
says `idle` or how many are `live` again once it has.

### A daemon says `failed`

`ssh` could not reach the host, or `hmz` could not be installed or started there; the daemon bar's menu, and
**Settings → Daemons**, say what it said. Check that `ssh <host>` works from a terminal here
without asking for anything -- a password or a host key to accept cannot be answered from the
page -- then press **Connect**.

### A P2P daemon says `failed`

EasyTier could not be downloaded here, or that machine's daemon could not be reached on its
network. Check that its `listen` names `easytier:<name>` with the very same secret, that both
machines can reach a node both entries name, and that this machine is paired with it -- one
that says it `needs the id of the daemon it reaches` is not; then press **Connect**.

### A daemon will not update its `hmz`

The host's daemon has epics running, or the page could not tell whether it has, so its `hmz` is
left as it is. Once they have ended, press **Connect** again; or update it on the host yourself,
`uv tool install --force 'hmz==<version>'`.

### No system notifications

They come only while the page is hidden or not focused, and in a browser only once it is
allowed: press the button in **Settings → Notifications**, and check that the browser's site
settings, and your system's, let it notify. Check too that **Settings → Notifications** has the
kind, and system notifications, switched on.

### A way in is marked `(at a terminal)`

It runs the CLI's own sign-in, which needs a terminal. Make that account from `/settings` in
`hmz`.

## Next steps

- [Watching a run (the monitor)](/user/monitor): the same run, drawn in the terminal.
- [Leaving it running](/user/leaving): how a run outlives every window onto it.
- [Humanize Desktop](/user/desktop): the same page in a window of its own, on macOS and Windows.
- [Web reference](/reference/web): the command line, what `hmz web` serves, and what the page keeps.

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
| **Sidebar** | A title row -- the mark, **Hide sidebar**, **Back** and **Forward**; in Humanize Desktop on macOS it stands beside the window's traffic lights, the mark at its far end -- then **New chat**, **New epic**, **Search**, **Flows**, then a quiet heading per directory -- every one an epic ran in or that was opened here -- with its chats and epics under it, the last updated first. Every row is its title and, straight after it in the same line, how it stands in quiet words. A [chat](/user/chat) is that one line and nothing else, as a chat app lists a conversation: **Running** while its agent answers, **Failed** where it failed, a small dot -- the one an unread row has, said as `Awaiting input` where you point at it -- while it waits on you, and nothing once it rests; when it began is said where you point at it, and drawn at the row's end on a touch screen. A flow's epic is a row of two lines: its arrow, task and state -- `Running`, `Asking` (blinking while it asks a person something nobody has looked at here yet) and `Waiting` once you have, `Stopping`, `Done`, `Failed`, `Stopped`, `Budget spent`, `Unfinished` -- then its flow's name, and `live` where a host goes with it; `Running` without `live` is one another process goes with, read as it writes itself down. A directory shows its first 20 rows and ends with **Show N more**; the list reads 60 chats and epics at first, and ends with **Show more** while the daemon holds more and nothing else would bring them | Open a chat or an epic; press an epic's arrow to open it out into its agents, and each agent into its sessions; press a directory's name to fold it away; point at a heading for **Group and sort** and **+**, which starts a chat there, and right-click it for a chat or an epic there; point at a row for **More options**, the menu a right click on it opens. See [The list](#the-list) |
| **New chat**, **New epic** | Two forms, each opened from the sidebar; the page opens on **New chat**. A plain heading at the top, the chats that wait on you listed in the middle, and at the foot a box for the first message or the task. A chat keeps where it runs under the box at the left, on one chip, **Environment**; an epic has the flow picked beside the heading and everything it is set up with in the middle of the page, its **Environment** first | Start it; a chat's model and what it may touch are picked from the chips under the box at its right, and an epic's set-up is in sight over its box. See [Starting an epic](#starting-an-epic) |
| **An epic** | Its graph: who handed to whom -- a chat is only its conversation | Read it, steer it while it goes, export it, pick it up. See [An epic](#an-epic) |
| **A session** | Its thread, as the terminal draws it | Say a line into it, or answer what it asks, while the epic goes |
| **Flows** | **Installed**: a card for each flow on offer -- those installed from a flowverse and your own, whatever the directory -- its release and any newer one, and, one chosen, what it declares under the cards. The page is the daemon's and no folder's: it lists no folder's own flows, which [a new epic](#starting-an-epic) in that folder offers. Where none is installed yet it says so, with **Browse Flowverses**. **Flowverses**: a tab for each index flows are installed from, **Official** first and open at once, showing where it is fetched from and every release it lists | Start one, update or uninstall it; install, switch or uninstall a release; fetch a flowverse again with the arrow after its name, add one with **+** after the tabs, or remove one. A row of tabs is one stop of <kbd>Tab</kbd>: <kbd>←</kbd> <kbd>→</kbd>, <kbd>Home</kbd> and <kbd>End</kbd> move among its tabs, <kbd>Enter</kbd> picks |
| **Search** (<kbd>⌘K</kbd>, or <kbd>Ctrl+K</kbd> off a Mac) | A box over the middle of the window: the field, the tabs **All**, **Chats** and **Epics**, then every chat and epic a line apiece, newest first, each saying how it stands in the words its row in the sidebar says it in -- a chat that rests says nothing -- and under them **Actions**, which stay in sight however many were found. Once you move to one, by key or pointer, a line over the foot says the rest of it: its folder, flow, agents, what it spent and how long it took; on a phone or a touch screen that stands under each | Type a word of the task; <kbd>↑</kbd> <kbd>↓</kbd> move, <kbd>Enter</kbd> opens (what you typed, even before it is listed), <kbd>Alt</kbd> <kbd>Enter</kbd> (<kbd>⌥</kbd> on a Mac) or the menu key opens the menu of the one you are on, <kbd>Esc</kbd> closes, and gives the keys back to where they were -- the box you were typing into; <kbd>Tab</kbd> stays within it; <kbd>←</kbd> <kbd>→</kbd> change the tab and <kbd>/</kbd> opens **Filters** -- how it went, folder, and, off **Chats**, flow -- while the field is empty; **New chat** or **Import** under **Actions**. Search leaves no step behind: **Back** after it is closed goes to what was open before, and from a chat it opened to the view it was opened over. See [Importing an epic](#importing-an-epic) |
| **Settings** | What Humanize remembers, and what the epics here spent | Change it, as [`/settings`](/user/settings) does |

The foot of the sidebar is one row: the [daemon bar](#daemon-bar) and, beside it, a gear that
opens **Settings**. The bar names the daemon the page shows,
its host and whether it is reached, and says how many epics are going on it. Its menu holds
**Daemon**, which opens a list of the daemons beside it to switch to, then **Settings** and
**Usage**. Where a newer Humanize is out, the bar is marked ↑ and its menu offers
**Update**, which copies `hmz update` to run in a terminal. **Back** and **Forward** in the
sidebar's title row step through
where the page has been, as a browser's do. <kbd>⇧⌘O</kbd> opens a new chat and <kbd>⌘.</kbd> folds the sidebar away;
off a Mac, as on Windows, they are <kbd>Ctrl+Shift+O</kbd> and <kbd>Ctrl+.</kbd>. **New chat** and
**Search** say their keys at the end of their rows, except on a touch screen and, off a Mac, in a
sidebar too narrow for them. Drag the
sidebar's right edge to size it -- the arrow keys do the same once it holds the focus, and a
double click makes it 275 pixels wide again, as it starts; the browser keeps the width. On a phone
the sidebar is a drawer behind the button in the corner: open, it holds the keys, and
<kbd>Esc</kbd> closes it. There the drawer, the panel beside a view and
[Ai-chan's drawer](#ai-chan) each cover the view, so one is open at a time: opening one closes
the others, and going to another view closes the sidebar's.

A list with nothing in it yet says so where the list would be, with a button that gets something
there: **Browse Flowverses** where no flow is installed, **Fetch** or **Add flowverse** on a
flowverse that lists none, **New chat** or **New epic** in **Search**, and in **Settings**
**Add target**, **New nous**, **Add runtime** and **Add account**, each of which goes to the form
under the list. In **Search**, where nothing matches what you typed or filtered for, the button is
**Clear filters**. None of them writes anything by itself.

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
grouped, until you **Unpin** it. **Mark as unread** puts the square a
[notification](#notifications) marks a row with beside it until you open it or choose
**Mark as read**. Both are kept by this browser.

With **Harness sessions** on in [Settings › General](#settings), a folder also lists, after its
chats and epics, the [sessions each CLI had of its own](/user/chat#harness-sessions) there: quieter
rows that end in the CLI's name. One opens to be read, with **Continue in chat** under it, which
copies it into a chat of that folder and opens the chat; the CLI's own session is never changed.
A session of a CLI [that carries none on](/user/chat#harness-sessions) is read all the same, and
says under it that it cannot be continued in a chat.
They count among the rows a folder shows before **Show N more**, are listed only while the list is
grouped by folder, and are not among what **Search** finds.

Every view is an address: copy it, keep it, or open it in another tab. The address names the
daemon it shows, `#/@devbox/epics/…`, so a kept address opens on the same machine; one with no
`@` is Local's.

**Right-click** anything for what can be done to it: a folder in the sidebar (new chat here, new epic here, its
flows, search it, copy its path, settings -- one whose directory was deleted says **missing** after its name, offers nothing that starts there, and is listed only while it still holds a chat or an epic), an epic (open, pin, mark as unread, its Exomyth, resume, a new
epic like it, copy its link, task or name, export, upload, stop), a chat (open, pin, mark as unread, rename, a new chat
like it, fork, copy its link, first message or ID, upload, archive, delete -- see [Managing a chat](#managing-a-chat)), an agent or a session, a node on the graph, a flow's card or a flowverse's tab, a search
result, a line of a thread (copy it, or the whole thread; by the keys, <kbd>Tab</kbd> to the thread,
<kbd>↑</kbd> <kbd>↓</kbd> to a line, then <kbd>Alt</kbd> <kbd>Enter</kbd> or the menu key). Only text to read or write -- a thread,
a task, a path, an error -- is selected as on a web page, and keeps the browser's own menu; the
page's buttons, tabs, labels and headings are not. What a menu sends off -- stopping or uploading an
epic, forgetting a folder, connecting a daemon -- says `Stopping…`, `Uploading…` and the like at
the top right of the page, under its bar, where toasts are, until the daemon
answers. **Hover** over anything cut short -- a folder's name,
a task, a path -- to read it in full.

**Menus**, and whatever else floats over the page for a moment -- the list a choice opens beside
its menu, a form a button opens to be typed into -- are open one at a time:
opening one closes the others, save the one it was opened from. A menu opens on the choice in
force, or its first; <kbd>↑</kbd> <kbd>↓</kbd> move through its choices and go round at its ends,
<kbd>Home</kbd> and <kbd>End</kbd> go to the first and the last, <kbd>→</kbd> opens the list
beside a choice and <kbd>←</kbd> closes it. <kbd>Esc</kbd> closes the topmost alone -- the list
beside a menu, then the menu, then the dialog they were opened in -- and gives the keys back to
what opened it. A press anywhere else closes them all, and still does what it was pressed on:
the button of another menu opens that one in the same click. They also close when the button
that opened one is pressed again, when the keys move out of them, when what one stands by is
scrolled away, when a dialog opens, the sidebar is folded or the page goes to another view, and,
for a menu, when the window is sized or left; a form being typed into stays through those two.
A menu opened from a chip under the box you type in opens over that chip, its foot just above
it; **+** in the box opens clear of the box.
Nothing on the page casts a shadow: what floats is set off by its own surface and a line a pixel
thick around it, and a dialog by the dimmed page behind it.

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
brings the graph back as it opened: in the middle of the view, as wide as it, and never so small
it cannot be read -- one too tall for that opens on its top, to drag down through. Only in the short
strip a waiting question leaves it is it drawn smaller, two agents side by side, with every frame of
it in sight. Until you move or zoom it, it is fitted again as the view grows or shrinks.

The panel beside it (the button at the top right shows and hides it; where the window has no
room for it and [Ai-chan's drawer](#ai-chan) both, with 480 pixels left to the view, opening one
closes the other) holds:

- **Epic.** How long it has been going, what it has spent and how fast, a meter for each limit of
  its [budget](/features/allowances), the task, who handed to whom in words, **Spending** by
  model and kind of token (each model's name over its figures; a count is cut short, as `18.0k`,
  and said exactly where you point at it; `≥` marks a figure that is only a floor),
  **Environments** -- what each session works in, with its path under it, and where its harness
  went, each a link into that environment's files, shell
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

A session opens as its thread, on what was said last, drawn as the terminal draws it: an agent's
words on a dot, your lines set apart on the right, a tool on a mark of its own, and
`✻ Worked for …` closing a turn.

A [chat](/user/chat) is only its conversation, as a chat app's is, wherever it is opened: your
first message, then
each reply and each line you typed under it, on the right. The box under it is how you answer --
between turns it is your next turn, and while the agent asks something mid-turn it answers
that, the answers it offers buttons under its question, at the end of the conversation. It has no graph, no agents
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
new one. A chat an earlier Humanize wrote down as an epic is
[a chat as any other](/user/chat#earlier-chats) once the daemon has started: it is listed
among the chats, and an address that named the epic opens the chat.

The conversation names nobody: a turn of the agent's draws nothing as it begins, and ends on
`Worked for <time>`.

The box under a chat holds only **+**, what you type and the button that sends; what else
there is to pick is a row of quiet chips under it, at its right. The first says the nous that
answers the chat: its harness, its model and its effort, as on [a new chat](#starting-an-epic). Its menu says the rest of the chat's agent -- its account -- and
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

A chat reads as a chat app's session. Its bar holds its title -- a button: press it to
[rename the chat](#managing-a-chat) where it stands -- and, right after it, one
**More options** menu (`⋯`); at the far right, a button each for **Details**, **Terminal**,
**Changes** and **Files**, then **View options**. Each button opens its pane beside the
conversation and shuts it again -- the bar runs over the pane too, so the button stays where
you pressed it: **Details** is what the chat is, and the other three are the
terminal, the changes and the files of the [environment](/features/environments) it works in, there
while a host holds the chat; one that cannot open says why where you point at it. **View
options** holds **Side questions**, **Board** while the chat keeps one, and **Ai-chan**, which
opens [her drawer](#ai-chan). The pane open is headed by its name and has no tabs of its own:
the bar picks it. No pane is open until you open one. **Details** says what the chat has
used, its first message, where it works and what it is; it counts no sessions and names none.
**Side questions** asks about the chat as it stands, with nothing to pick first, and each
side conversation goes by the first question asked in it. Nothing is said over the chat's box
of how it stands but that it failed. While a turn is open the button that sends is **Stop**: it stops that turn, and
the chat stays, waiting for your next line; what you type and send with <kbd>Enter</kbd>
meanwhile is still delivered to that turn. The menu holds what a right click on the chat offers
-- **Rename**, a new chat like it, **Fork**, copying its link, **Upload**, **Archive** and
**Delete** -- with **Environment** while a host
holds it, and **Skill or flow**: whether a `$` name that is both a skill and a flow uses the
skill or starts the flow, with a mark on the one in force and whether that comes from the
settings or from this chat. Picking the other sets this chat's own
[preference](/user/chat#a-name-that-is-both), as `/prefer` does.

The pane beside a chat has **Details** in place of **Epic** -- its usage, its first
message, where it works, and under **About this chat** its ID, where it is saved, its
folder, **Works in** where it works in [a worktree](/user/chat#worktree) rather than in its
folder, when it started, its nous, options, limits and sessions -- and **Side questions**
in place of **Aside**, which works the same.

#### Managing a chat {#managing-a-chat}

What a chat can be besides talked in -- [renamed, forked, archived and
deleted](/user/chat#managing) -- is in its menu: **More options** on its row in the sidebar or
a right click on it, and the `⋯` menu of its bar.

| | What it does |
| --- | --- |
| **Rename** | Turns the title into a field, where it stands: on the chat's bar -- pressing the title there does the same -- or in its row of the sidebar. <kbd>Enter</kbd>, or clicking away, saves it; <kbd>Esc</kbd> leaves it as it was. The bar and the row both follow |
| **Fork** | Makes a new chat from a copy of the conversation so far and opens it; it rests until you say something in it. Refused while a turn is open, in the daemon's own words |
| **Archive** | Takes the chat off the sidebar and out of Search, and changes nothing else of it. Still open, or opened again by its address, it reads as before, with **Unarchive** on its bar (in a narrow window, in its menu alone) and in its menu. The archived chats of a directory are listed in [Settings](#settings) under **Workspace**, each with **Unarchive** and **Delete** |
| **Delete** | Asks first, in a dialog: deleting permanently removes the chat's record and the sessions kept with it, cannot be undone, and leaves a worktree the chat worked in on disk. **Cancel**, <kbd>Esc</kbd> or **Delete**. A chat still going -- a host holds it, between turns included -- is refused, in the daemon's own words: delete it once it has folded away. Deleted from its own view, the page opens a new chat |

The next chip under the box names what the chat's agent may touch -- **Read only**, **Edit
this folder** or **Full access** -- and opens a menu of the three, the one in force checked.
Picking another sets the chat's [permission](/user/chat#permission) from your next message; on
a chat that has folded away, it is what the chat is carried on with. The last is **Usage**, a
ring with no figure beside it: click it for a small popup by the ring -- what this chat has spent, its tokens and
how long it has run, with a bar for each kind of token while it runs; what the chat's folder
has spent today and over the last 7 days, with the output tokens written, over how many chats
and epics; and **Usage settings**, which opens the
[Usage](#settings) page on that folder.

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

- Who handed to whom, and each session's turns, are read out of the logs it kept as soon as
  the epic is shown, as [tracing](/user/tracing) does. It takes a moment on a long epic, and
  the page says so while it reads; if the reading fails, **Read turns** tries again. Opening
  a session reads its thread the same way.
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
Both say where they run as an **Environment**: the [daemon](#daemons) and, on it, the folder.

A new chat keeps it under the box, at its left, on one quiet chip that reads the daemon and
then the folder, as `Local · project`. Its menu has both. **Runs on** lists **Local** and every
remote daemon, and picks another as the daemon bar at the foot of the sidebar does; **New
environment** opens the daemons' settings. **Folder** lists the directories: pick another by its
name -- point at one for its whole path -- **Open folder…**, or **No folder**. The last row is
**Worktree**.

A new epic has nothing under its box. **Environment** is the first part of what it is set up
with, in the middle of the page: a row **Runs on** with the daemon, a row **Folder** with the
directory, each picked from its own chip, and under them a row for each environment the flow
asks you to place.

The forms follow which directories still exist, and keep looking while they are open. They open
on the directory `hmz web` was started in while it is there, else on the one worked in last that
is, else on your home; the menu lists only directories that are there. A directory that
is deleted while it is picked -- or named by an address you kept -- stays picked: the chip reads
`<name> (missing)`, and over the box the form says **The folder `<name>` is no longer on this
machine. Pick another folder.** Nothing is started there; put the directory back and the form
reads it again by itself.

A new chat starts a [chat](/user/chat): pick the directory, or **No folder**, from **Environment**; the
nous -- a harness and a model -- from the chip under the box at its right; and type the first
message. Tick **Worktree**, the last row of **Environment**'s menu, to start it in [a git worktree of its
own](/user/chat#worktree): it cannot be ticked with **No folder**, nor in a directory that is in
no git repository, and says which where you point at it. <kbd>Enter</kbd> starts the chat, and the page goes to its conversation. There is no
flow, budget or params to set. **+** in the box offers **Add files**, which types `@` and
completes the folder's files -- with **No folder** picked there are none to name, and it says
**Pick a folder first**; what else a line can start with is offered [under a
chat](#a-session), once there is one.

The middle of the page is empty, but for the chats of this daemon that wait on you, each a row
saying **Asked a question** that opens its chat. **✕** in a row takes it off the list, in this
browser, until that chat asks something else.

The chip says the nous that will answer -- its harness, its model and its effort, each in its
own shade, as **Claude Code Haiku 4.5 Default**; **Default** is no effort set -- starting from
the agent that directory last chatted with. It opens a menu:

- Every nous the harnesses installed here run, one a row naming the harness and then the model,
  as **Codex - GPT-6.2 Sol**, a harness after another, the one chosen marked; point at one for
  what `-a` spells it. A harness never asked what it runs is one row, **Not asked yet**: picking
  it asks it, which takes a few seconds, and lists what it answers. Where a harness lists one
  model by several routes, each row says who routes it after the model, as **LiteLLM - Opus 4.5
  (azure_ai)**. With more than ten rows, **Find a nous** stays over the list and narrows it as
  you type -- on a row as well as in the field -- and says **No nous matches** where nothing
  does; only the rows scroll, so **Effort** and **More** stay in reach under them.
- **Effort**, one row saying the effort chosen, opens the efforts the model chosen takes, where
  it takes any; **Default** leaves it to the model.
- **More**, one row, opens the rest: **Other model**, where a model the harness chosen does not
  list is typed; the **Account** it runs as (**Local** is this machine's own sign-in; **Add
  account…** opens Settings); and **Refresh models**, which asks that harness what it runs again.

Harnesses, models and efforts are named everywhere on the page as their vendors name them --
`claude` is **Claude Code**, `claude-haiku-4-5` is **Haiku 4.5**, `xhigh` is **Extra high** --
and one the page has no name for is shown as it is written.

What is picked is an agent as `-a` spells one, `cli[@account]/model[:effort]`; resting the
pointer on the chip says it in full.

The chip after it, **Edit this folder** to begin with, is what the agent may touch: its
[permission](/user/chat#permission). The ring that ends the row is **Usage**: it opens a small
popup of what the folder picked has used today and over the last 7 days -- every folder's where
none is picked -- with **Usage settings** for the whole page.

**New epic** opens on the directory `hmz web` started in, or the folder whose **New epic here** was
picked from its right-click menu -- its **+** opens a chat there -- and on the flow that directory
last ran; pick another flow beside the **New epic** heading, and another directory from **Folder**, under **Environment**.
**+** in the box offers **Add files**, as on a new chat.
A chat is not among the flows. Where no flow is installed -- Humanize ships none -- the middle
of the page says so, and **Open Flows** there, as in the flow's menu, goes to
**Flows**, on its flowverses, to install one; until then nothing starts. **Open folder…**
takes any directory by its path, completed as you type, and keeps it in the sidebar. **No
folder** works in none of yours: each epic started so gets a new directory of its own in the
temporary directory, made as it starts, and set up as the directory `hmz web` started in is; the
epic then shows in the sidebar under that directory. Type the
task and press <kbd>Enter</kbd>. What the flow is set up with is in the middle of the page, under what the
flow is for, always in sight -- nothing opens or hides it -- as that directory last started it:

- **Environment.** **Runs on** and **Folder**, as above; then, per environment role, the
  **Backend**, the **Runtime** of it (or **Add runtime…**, or for ssh **Other host…**), and the
  **Directory**, completed as you type on this machine. A directory left blank is the folder
  picked, which the field says while it is empty.
- **Agents.** A row per role: its name, and beside it a chip that says the nous filling it --
  harness, model and effort. The chip opens the menu a new chat's does, holding only the
  harnesses installed that can fill that role: pick a row, an **Effort**, or under **More** a
  typed model, the **Account** it runs as (**Local** is this machine's own sign-in; **Add
  account…** opens Settings) and **Refresh models**. A harness never asked what it runs is
  asked the first time it is picked, which can take a while. Point at a role's name for what
  it is held to.
- **Parameters**, the **Budget**, **Backup** -- the [targets](/user/backups) the epic is backed
  up to, the defaults ticked until you start with another choice -- and **Profile flow** and
  **Profile environment**.

There is nothing to save: starting the epic keeps the whole set-up for that directory, and the
next new epic of that flow there opens on it. Every flow needs at least one limit, and each
required role an agent; started without one, the form says so and puts you where it is set.
The page goes to the epic once it starts.

### Ai-chan {#ai-chan}

Ai-chan is an agent you operate Humanize through by talking to her. Her avatar, at the right of
every view's bar, opens and closes her drawer beside the view -- a chat's bar ends as a chat
app's does, and offers her as **Ai-chan** under **View options** instead; it stays open as you go from view
to view, until you close it. What you type in it stays in it: a new chat or a new epic that
finishes opening beside it meanwhile does not take the keys. Where opening it would leave the
view under 480 pixels beside a panel already open, that panel closes for it, as hers does for a
panel opened after. On a phone it covers the view:
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

Settings has two groups. **App** is the page's own: how it is drawn, the daemons it reaches,
what it tells you of them and the [language](#language) it is written in. It is the same
whichever daemon is on screen. **Daemon** is the same
pages as [`/settings`](/user/settings), in the same order, and what the epics spent, all of one
daemon:

| Page | What is there |
| --- | --- |
| **Themes** | The [themes](#themes) of this browser, and which one is in use |
| **General** | Whether a turn's working is shown, **Harness sessions** -- whether the sidebar lists the [sessions each CLI had of its own](/user/chat#harness-sessions), off until set -- and [error reports](/user/reporting) |
| **Accounts** | Every [account](/user/settings#accounts) by its CLI, way in and the names of what it sets: **Edit** it (what you leave blank stays as it was), or make one; under **More options** at the end of its row, or on a right click of it, ask what it runs again (**Refresh models**), copy it to another CLI, or remove it, which asks first in the row |
| **Nous** | Every [nous](/user/settings#nous): how a failed turn is tried again and where it goes next, and each virtual nous's graph, edited node by node. A concrete nous is listed by its names -- **Claude Code - Opus 4.1 · High** -- with what `-a` spells where you point at it; typed into a graph, it is typed as `-a` spells it |
| **Runtimes** | Every runtime: add one from its backend's fields, change, check or remove it, or bring hosts in from your ssh config |
| **Backup** | Every [backup target](/user/backups): its repository and branch, when an epic goes to it (**On session close**, **Every N minutes**, **On epic end**, or none: by hand only), and whether it is a **Default**; add, edit or remove one; **Download** an epic a target holds, as in [Downloading an epic](/user/backups#downloading-an-epic). A URL is shown with nothing signed into it |
| **Workspace** | What a directory was last set up with, and forgetting it -- which also takes it out of the sidebar where no epic ran there; a directory that was deleted is marked `(missing)` in the list, and can still be forgotten; and under **Archived chats**, the chats of that directory that were [archived](#managing-a-chat), each with **Unarchive** and **Delete** |
| **Usage** | What the epics spent, of every directory or of one -- one since deleted too, as **Search** filters by one -- by day and by flow, looking back 7, 30, 90 or 365 days |
| **Daemons** | **Local**, always there, and every remote daemon with its kind and state (up, connecting, installing, failed or idle): add or **Edit** one as [Adding one](#adding-a-daemon) says, **Connect** or **Remove** one, asked first; under each, its **Devices** and **Pair a device** once it is up, and a remote daemon's own **WebRTC servers** |
| **Notifications** | Which notifications appear, of every daemon: **Done**, **Failed**, **Stopped**, **Questions** and **Waiting**, and whether the **System** shows them. In a browser, **Allow** asks it for permission; the desktop app needs nothing more. Kept in this browser, never per daemon |
| **Language** | The [language](#language) the page is written in: **System**, **English**, **简体中文** or **繁體中文**. Kept in this browser, never per daemon |

Above the **Daemon** pages, **Daemon** picks which daemon they read and write: the one on screen
until another is picked. It goes into the address as `?daemon=<name>`, so a daemon's page can be
kept and opened again. Picking one changes nothing else on screen.

**Download**, opened from **Backup**, and **Delete**, opened from **Workspace**, are dialogs of
their own. Closed -- by **Close**, <kbd>Esc</kbd> or a press beside it -- either goes back to the
Settings page it was opened from; opened by its own address, it closes to the view under it.

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

The page is drawn in a theme. A theme always has two sides, a light one and a dark one, under
one name; your system says which is shown, the light where it is light and the dark where it is
dark, and the page follows it as it changes. Humanize comes with **presets**: its own,
**Humanize Green**, and **Temperate Gold**, **Concordant Scarlet**,
**Restrained Crimson**, **Critical Teal**, **Desirous Indigo**, **Peaceful Lilac**,
**Hateful Silver**, **Devoted Pink**, **Self-Negating Plum**, **Dominant Azure**,
**Surviving Jade** and **Lamenting Orchid**.

A theme is picked only under **Settings → Themes**: **Use** beside one chooses it, both sides at
once. Humanize Green is in use until you choose another. Nothing there picks light or dark:
change your system's appearance for that.

Under **Custom** are the themes of your own. **New** makes one from the theme in use, copying
both its sides -- to start from a preset, use it first -- and **Import** reads one from a file.
**Edit** opens one of yours, **Delete** forgets it:

- **Name**, which both sides have, and **Side**, which switches between its light and its dark.
  Each side has its own colours and pictures; a colour you leave blank is Humanize Green's for
  that side.
- Every colour, by what it colours: **Backgrounds** (page, sidebar, surface, raised),
  **Text**, **Controls** (button, its text, primary button, its text, field, edge), **Lines**
  (line, strong line, hover, scrim), **Accents** and the **Graph**'s lanes. **Edge** is the line
  around a button, the strong line where you leave it blank. **Hover** is the fill under what
  the pointer is on, in every preset a faint tint of the text's colour and never an accent's;
  what is selected or pressed is a stronger tint of the text's colour, worked out from it, and
  no colour of its own. The **strong line** is around what floats and what is typed into, the
  **line** between everything else, and the **scrim** dims the page behind a dialog. Pick one or type any CSS colour, such as
  `#102030` or `rgba(255, 255, 255, 0.1)`; × gives back Humanize Green's.
- **Pictures** behind the **Page**, **Sidebar**, **Panel** and **Dialog**: a PNG, JPEG, GIF,
  WebP, AVIF or SVG -- an animated SVG moves -- each to **Cover**, **Fit** or **Tile** its plane.
  Where your system asks for reduced motion, a moving picture is held still.

The page shows a theme as you change it, and keeps every change at once. **Export**, beside
**Done** where a theme of yours is edited, saves it with both its sides, pictures and all, as a
`.hmztheme` file; **Import** reads one back, here or in any other browser. Themes are kept by the
browser, as the rest of what the page remembers is, so another browser -- or
[the app](/user/desktop) -- has its own until you import them there.

A `.hmztheme` file is JSON, holding both sides, each with its `colors` and `images`:

```json
{
  "hmztheme": 1,
  "name": "Dusk",
  "light": { "colors": { "paper": "#fff8e0" }, "images": {} },
  "dark": {
    "colors": { "paper": "#201008", "primary": "#ec6fa3" },
    "images": { "page": { "fit": "cover", "data": "data:image/svg+xml;base64,…" } }
  }
}
```

An earlier Humanize let a theme have one side alone, and let a light and a dark be picked apart.
What it kept in your browser is kept: a theme of one side gets the other, plain, and two sides
picked apart become one theme of your own, called **Custom**, which stays in use. A file it
wrote for one side -- `"base": "dark"` with `colors` and `images`, in place of `light` and
`dark` -- is still imported, as a theme whose other side is plain.

`colors` is keyed by the page's colour tokens (`paper`, `side`, `surface`, `raised`, `ink`,
`ink-2`, `ink-3`, `on-ink`, `on-fill`, `link`, `control`, `control-ink`, `primary`,
`on-primary`, `field`, `edge`, `line`, `line-strong`, `hover`, `scrim`, `green`, `cyan`,
`cyan-ink`, `pink`, `pink-ink`, `lavender`, `gold`, `done`, `fail`, `lane-1` to `lane-6`), and
`images` by plane (`page`, `sidebar`, `panel`, `dialog`). Importing keeps what a theme can hold
and drops the rest: an unknown token, a value that is not a colour, a picture that is not an image.

## Example: start a chat in the browser, answer it in the terminal

Start `hmz web` in a project, which opens on **New chat**:

1. Pick a nous from the chip under the box, such as **Claude Code - Haiku 4.5**, type a first
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
cannot be taken -- and how to reach it. Beside the form, the page says what the kind you picked
is and what the other machine needs for it, and each field says under it what it is for:

| Kind | Mode | What you give |
| --- | --- | --- |
| **Code** | | A pairing code, `hmz-pair:…`, made on that machine by `hmz daemon pair` or by **Pair a device** on a page that reaches it. It is claimed at once, over the routes it carries, and the daemon is kept only once the claim succeeds -- held to that machine's id from then on; otherwise the form says why. **Advanced** holds the [STUN and TURN servers](#webrtc-servers) to claim it with, and opens by itself for a code that is reached over WebRTC. |
| **SSH** | **SSH Config** | A `Host` of your `~/.ssh/config` not yet added, picked from a list; picking one fills in the name. Nothing here writes to the config. It is resolved through your config every time, so editing the config edits the daemon. |
| **SSH** | **Custom** | The host, user, port, identity file, proxy jump and options, a part at a time, as for an [ssh runtime](/user/settings#an-ssh-host). **Import from SSH config**: pick one of its hosts and **Import** fills them in from what your config says of it; they are kept by the page, and the config is not read again. |
| **P2P** | **EasyTier** | The secret that machine's EasyTier entry holds: at least 16 bytes in UTF-8, shown masked. And the [**Nodes**](#easytier-nodes) both machines meet on, at least one: tick any of the EasyTier community's shared nodes, each listed with whether it is up and how much of the last 24 hours it was, or type one in as `tcp://host:port` (or `udp`, `ws`, `wss`, `quic`, `wg`) and **Add node**. Where the community list cannot be read, the page says why, and you type the nodes in. For a new daemon, also that machine's pairing code: it is claimed at once over EasyTier, and the daemon is kept, held to that machine's id, only once the claim succeeds. |

**SSH** and **P2P** are offered only where the page can open their routes: in a browser,
through `hmz web`; in [Humanize Desktop](/user/desktop), through the app.

Edit a daemon, connect to it to check it, or remove it, which asks first. Editing opens the form
in the daemon's own kind and mode, with every route it is reached by, in the order they are
tried, to add to, take from or reorder; a P2P daemon's secret is never shown again, and leaving
it empty keeps it. Removing one forgets how to reach it, and nothing on the host: its epics,
its `hmz` and its pairing of this machine stay there.
A daemon removed can be added again from a new pairing code: this machine is not
paired a second time, and keeps the name it was paired under.

The daemons are kept by this browser, in its IndexedDB: each its name, the daemon id pinned,
its [routes](/reference/settings#settings-yaml) and its own STUN and TURN servers. Another
browser, Humanize Desktop, and `hmz` in a terminal each keep their own.

### Devices {#devices}

A daemon's **devices** are the browsers and machines paired with it: the ones that may reach
it. They are the other way round from **New daemon**, which is about the machines this page
reaches. Under each daemon's line in the list, once it is up, **Devices** has **Pair a
device**, which makes a one-time pairing code for another machine or browser to claim -- under
**New daemon → Code** there -- shown with when it expires, and a button that copies it; and
the devices paired with that daemon, each with when it was last seen. **Revoke** one, asked
first, and it can reach that daemon no more. A daemon that is not up says so there instead:
**Connect** to it first.

### WebRTC servers {#webrtc-servers}

A browser reaches a daemon behind a [relay](/user/relay) over WebRTC, by a `webrtc:` route.
The two then look for a direct path between them: a **STUN** server tells each its address as
the other sees it, and a **TURN** server carries the traffic where no direct path exists. On a
simple network neither is needed.

Each remote daemon has its own, under its line in the list: **WebRTC servers**, folded away
unless one of its routes is a `webrtc:` route. Write one server a line -- its URL, as
`stun:host:port` or `turn:host:port`, then for a TURN server its username and its credential
-- and **Save**. A credential is shown as `••••` from then on, and is kept where you leave it
so. They are used for that daemon's `webrtc:` routes only; a daemon reached another way never
uses them. For a new **Code** daemon they are asked under **Advanced**, before the code is
claimed.

They are this browser's side. The daemon's own side is the
`ice_servers` setting of its machine, which its [listeners](/reference/daemon#listeners) answer WebRTC with.

An earlier version kept one list of servers for every daemon: it is moved, the first time the
page is opened, onto each daemon that has a `webrtc:` route.

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
**EasyTier** daemon with the same secret, at least one of the same nodes, and that pairing code:
it writes the EasyTier entry of the name you give here, which the route `easytier:<name>` opens
with; in [Humanize Desktop](/user/desktop), it writes it to the app as well, which opens the route
itself. A route over EasyTier is held to the daemon's id, which only pairing gives, so the form
claims the code at once over that route -- then over the code's other routes, if it carries any
-- and keeps the daemon only once the claim succeeds, saying why otherwise. A P2P daemon kept
without an id by an earlier release fails with `easytier:home needs the id of the daemon it
reaches.`: remove it and add it again with a pairing code.

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

- **System notifications.** Each is one of your system's: the browser's, or, in
  [Humanize Desktop](/user/desktop#notifications), a macOS or Windows one, labelled with its
  kind and its daemon. Clicking it brings the page back on what it is about -- its epic or its
  chat, switching to its daemon. The page draws none of its own: no bell, no list, no card.
- **Sidebar marks.** An epic or a chat a notification came of has a square beside it in the
  sidebar, and so does its workspace while folded. Opening it takes the square away, as does
  **Mark as read** in its menu.

None is shown of the epic or chat you are looking at -- a question or a chat turn there
included -- and its row is not marked. Look away from the page, or at another window, and it is
shown.

The page asks each daemon for its notices itself, while it is reached: Local always, a remote
daemon once it is `up`. It takes up again after the last it heard of each, so what happened while
the page was closed, or a daemon out of reach, marks its rows once it is back; only what happened
in the last ten minutes is also shown by the system, so a night's worth does not arrive at once.

**Settings → Notifications** switches each kind on or off, and system notifications as a whole.
A browser shows system notifications only once you allow it: press the button on that page,
which asks the browser. Where the browser has blocked them, or shows none at all, the page says
so there: a blocked one is allowed again in the browser's own settings for the site. A kind switched off is neither shown nor marked. These are App
settings: they are kept by this browser and hold for every
daemon, never one daemon apart. `hmz` has its own, on its
[Notifications page](/user/settings#notifications).

## Language {#language}

The page is written in English, Simplified Chinese or Traditional Chinese. **Settings →
Language** chooses which:

| Choice | The page is written in |
| --- | --- |
| **System** | What your browser asks for, and the default: Traditional Chinese for `zh-TW`, `zh-HK`, `zh-MO` and anything tagged `Hant`, Simplified Chinese for any other Chinese, English for everything else |
| **English** | English |
| **简体中文** | Simplified Chinese |
| **繁體中文** | Traditional Chinese, in Taiwan's words |

A choice takes effect at once: the page opens again where it was, written in that language, and
so does every other tab of it. Dates and times follow the language too. It is an App setting,
kept by this browser and the same for every daemon; another browser starts on **System**.

Some things stay as they were written, whatever the language:

- **Names.** Humanize, Ai-chan, Nous, Epic, Flow, Flowverse, Harness, Daemon, Exomyth, Agent and
  Worktree, and the names of harnesses and models, are written in Latin script.
- **What the page did not write.** Tasks, what agents answer, a flow's own description and
  options, paths, and what a daemon refuses with are shown as they are.
- **A text not translated yet** is shown in English.

`hmz` in the terminal, and the desktop app's own menu and update windows, are in English.

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

None comes of the chat or epic you are looking at, nor of what happened more than ten minutes
before the page heard of it; and in a browser they come only once it is
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

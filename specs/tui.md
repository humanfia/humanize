# `tui`

The terminal interface `hmz` opens with no command: one prompt over everything humanize does,
drawn as a transcript, a multi-line editor and a status line. It runs flows and reads them
back; it defines no flows, drives no agents and keeps no store of its own.

## API

```python
# __init__.py
class Humanize(App[None]):
    def __init__(
        self,
        flow: str = "",
        agents: Mapping[str, Runs] | None = None,  # by role
        params: BaseModel | None = None,  # the flow's params
        link: Link | None = None,  # the runs a host holds; None holds them in this process
    ) -> None: ...
    def action_quit(self) -> None: ...
```

Textual's `run()` opens it; `action_quit` stops what is running and leaves.

## Requirements

- MUST open ready to talk to one agent, so that a typed line is enough to start — on what this
  workspace last ran where it has run anything, and as its arguments say where it was given one.
- MUST draw in the terminal's own colours, asking it nothing; failures in red, warnings in yellow.
- MUST stay responsive throughout — asking backends what they run, fetching, exporting — and MUST
  NOT start a CLI or reach the network on a sheet's drawing path.
- MUST fetch every flowverse's index as it starts, in the background and silently -- the
  official one included where it has never been fetched, one written into here excluded -- and
  install nothing by it; MUST then say once in the transcript which installed flows have a newer
  release, by SemVer, and that they are updated from `/flow`, and keep how many on the status
  line until none has. MUST NOT install, update or
  uninstall a flow while one runs.
- MUST ask `coganchor.releases` which release of humanize is newest as it starts, in the
  background, and MUST then say once in the transcript where it is newer than the one running,
  and that `hmz update` updates to it.
- MUST say why a flow will not load: not installed, a flowverse unfetched, a module missing, a
  file broken, no flow named in it.
- MUST read `/name` as a command, `$name [prompt]` as a flow and what to say to it -- `name`
  being what `-f` takes, `@<flowverse>/` and all -- and any other line as said to the
  conversation being read, reaching a turn already under way.
- MUST run a `$` line at once where that flow is already set up here, otherwise open the flow
  menu inside it holding the line and run it once saved, saying nothing was started if that menu
  is walked out of.
- MUST treat `$` as prose where no flow-shaped name follows it and while an agent waits on an
  answer, and MUST refuse it while a flow runs, leaving that run untouched.
- MUST offer a half-typed command or flow what it could become, reconsidered as the cursor moves
  as well as the text, offer nothing against a whole word, and keep focus in the editor.
- MUST keep what was typed for walking back to, per directory, and fixed for the session.
- MUST keep one transcript per agent, one per conversation, one per outworlder and one of its
  own, and none every agent appears on -- open on its own, return to it when a run starts and
  land on the agent of the run's first conversation as that opens, and bound what is kept
  without dropping its own or the one read.
- MUST round the conversations with a turn open and the outworlders of a running flow, forward
  on `shift+tab` and back on `tab`, a conversation that has ended leaving the round while
  staying readable from the monitor.
- MUST read a `chat` as Claude Code reads its one conversation: one transcript of your lines and
  the assistant's under the prompt, with no monitor, no views to round, no outworlder above the
  prompt and no Exomyth for its epic; its status line `running` while the assistant answers and
  `done` once it waits for you; never stopped -- no `/stop`, nothing about stopping on
  `ctrl+c` -- `/clear` ending it so that the next line starts another, and `/exit`, `ctrl+q`
  or `ctrl+c` twice leaving without asking, where a host holds it leaving it held.
- MUST call every agent of a run by its own name -- its transcript, each of its conversations
  as `<agent>/<n>`, its node on the monitor, the line saying it is working -- from the moment the
  run says it, before it has opened any, the role it fills only ever after that name.
- MUST show which agent is read, how many conversations it holds, whether it is working and
  whether it has something unread, and
  each outworlder of a running flow, whether it is asking, away, read or unread.
- MUST send a typed line that answers nothing to the conversation being read, or to whichever
  of the agent's has a turn open, holding it for the next turn otherwise, and keep it against
  the agent that took it.
- MUST name what is running as the flow started and whatever it called, innermost last.
- MUST offer exactly these commands, each doing what it says: `/flow`, `/btw`, `/epics`,
  `/resume`, `/settings`, `/clear`, `/afk`, `/claim`, `/stop`, `/exit`. `/btw [question]` MUST enter btw
  mode, marked on the status line, in which every typed line is one more turn of one side
  conversation until `/btw` or esc leaves it and closes it; MUST NOT ask the flow's own sessions;
  MUST answer in cyan in the current view. In a session's view, ended ones included with no flow
  running, MUST ask a read-only, skill-less fork of that session where its CLI forks, else a
  read-only, skill-less session of the same agent seeded from a snapshot. On its own transcript
  or the monitor MUST ask the btw agent (the one set on `/settings`, else the flow's first) at NONE
  permission with no skills, seeded with a snapshot and the sessions, which reaches a session's
  side conversation by `@ask <session>: <question>`, at most 4 per question.
- MUST carry the last run of this directory of a flow that can be picked up on for `/resume` —
  its flow, roles, params, budget, whether its flow and its environment were profiled and task, picking up its journal, saying which — say why there
  is none to carry on, and refuse it, as it refuses picking any run up, while a flow is running
  or stopping.
- MUST let a flow's agents be set up whatever is happening, but offer a flow choice only when idle.
- MUST make `/flow` a menu of pages, as `/settings` is, its first screen two pages -- what is
  installed, and the flowverses -- opening on what is installed, or inside a flow named to it.
- MUST list as installed only the flows humanize ships, the ones installed out of a flowverse
  and this project's and yours, under where each came from and by the name `-f` takes, each
  installed one with its release and with the newer one its index lists, the flow in force
  marked; and MUST offer updating, uninstalling and copying the one under the cursor here whole
  and under its name.
- MUST list per flowverse whether its index is fetched or written into, the flows it lists by
  what it lists each as -- `<flow>`, `<user>/<flow>` -- at their newest release with what of
  each is installed, and per flow every release newest first,
  prereleases marked and the installed one ticked; MUST install, update to or switch to the
  release chosen, with what it needs, and uninstall, fetch, add and remove a flowverse --
  removing what was installed out of it, asked first -- each at once and said under the list
  and in the transcript, with any credential in a URL hidden, and name any manifest skipped.
- MUST set a flow up by its roles: one row per agent role and one per environment role the flow
  declares, leaving out the ones the runtime fills -- an `Outworlder`, a `LocalEnv` -- then its
  params, asked with the flow's own params model as it is chosen and from a row of their own,
  what a run may spend, whether its flow and its environment are each profiled, and the backup targets an epic goes to -- the
  defaults until others are switched on there and saved, then remembered with the budget per
  flow, "none" where there are no targets. A saved menu MUST take
  effect from the next run, and MUST refuse to save a flow whose agent role names no model, or --
  for every flow but `chat` -- one that has no budget.
- MUST let what a run may spend -- a duration, a cost, output tokens, and whether a turn is let
  finish -- be set and read on the page its roles are on, and whether a run profiles its flow's
  own Python and whether it profiles the programs its agents start each be switched and read
  beside it, as two switches, off until switched on, and remembered with the budget per flow;
  a run started MUST be profiled exactly where those say so.
- MUST say where an agent's harness went as its first session on another machine opens: here,
  on its environment's machine, or on the runtime its affinity sent it to.
- MUST make an agent a CLI -- or litellm, a model called directly -- an account, a model and an
  effort and nothing else, offering only CLIs installed here whose harness is the one the role names and serves what the role asks,
  this machine's own account as `as local`, models known runnable as the chosen account, and
  efforts that model takes -- and letting an account be made where one is asked for. An
  environment role MUST be set by its backend -- every one `-e` takes -- then, for a backend
  that has them, a runtime of it saved on the runtimes page, one made there and then, or
  for ssh a host not saved, then its directory, starting from the one that runtime is saved
  with; MUST come to what `-e` spells, refused as `-e` refuses it; and MUST take that spelling
  typed whole as well.
- MUST be whoever is outside a run, once per outworlder: a question one puts MUST be shown on
  its transcript and the one being read and answered with the next line typed on either -- the
  oldest of that outworlder's on its own, of any on the monitor or the interface's own
  transcript, and of any part of no conversation on the agent's it was shown on -- an offered
  answer taken by its number as well. One part of a conversation MUST be shown and answered in
  that conversation instead, the answer with it: what its agent stopped mid-turn to ask, with
  what it offers, and a conversation's answer said back to ask what next, shown as that answer
  alone and answered with the next line typed reading that conversation; `/afk` MUST make the
  outworlder read away, or every one elsewhere that this frontend may answer for, leaving the
  ones another holds as they were, and MUST outlive it.
- MUST be one frontend of the runs it reads, whole and on its own: MUST ask for everything it
  does to a run through its `link` -- starting, saying, answering, stopping, `/afk`, `/claim`,
  the board, `/btw` -- and MUST draw a run from what it is told alone, reading one it arrives
  late to from the top.
- MUST let `/claim [on|off]` on an outworlder's transcript hold that outworlder for this
  frontend alone, or give it back; MUST show beside each outworlder -- above the prompt, on the
  monitor and under what it asks -- whether it is yours or whose it is; and MUST refuse a line
  typed at an outworlder another frontend holds, saying whose it is.
- MUST say who said, answered or started what another frontend did (`· by <name>`), and MUST
  list on the monitor every frontend reading the runs.
- `/exit` MUST let go of this frontend alone, offering to leave a running flow running where a
  host holds it; `/stop` MUST stop it for every frontend. Once closed, `hmz` MUST give the
  backups this process queued at most 15 seconds to finish, saying so where it waits and where
  one was left.
- MUST offer and run a command only where it works -- `/claim` only on an outworlder's
  transcript -- and refuse it elsewhere, saying where it works.
- MUST offer and run a command only while it would do something -- `/stop` while a flow but a
  chat runs and is not stopping, `/resume` while none is going and there is a run here to carry on,
  `/btw` while there is somebody to ask, `/claim` and `/afk` not on an outworlder another
  frontend holds, a flow to choose while none runs -- and refuse it otherwise, saying why; MUST
  say what a command does, and which keys work, as things stand, and reconsider both the moment
  the run or the view changes.
- MUST list on the runtimes page of `/settings` every runtime under its
  backend -- ssh hosts, docker daemons with what each may hand out, docker swarms with where
  their tasks may be placed and what they may reserve all told, this Mac's Apple containers
  with what they may hand out, and Slurm clusters with the partition, account and limits their
  jobs are submitted under -- and offer making each on one
  form wherever one is asked for, importing the hosts an ssh config names -- the user's
  own or another file, switched on per host and saved already or not, never writing to it --
  and per runtime correcting it, checking it and taking it away, its affinity -- where the
  harness of work on it runs, in order -- written on its form as `self`, `local` and
  `<backend>:<name>`, and the saved runtimes it falls back to, in order; MUST ask one what it
  has when it is made or corrected on that page and when it is checked, an import asking none -- an ssh
  host its home, CPUs, memory and GPUs, a docker daemon its CPUs, memory, GPUs and OCI runtimes,
  a swarm which of its nodes may take a task and what those have all told, Apple's containers
  the CPUs and memory their system counts, a Slurm cluster which nodes of its partition may
  take a job and what those have all told, and each what it is
  saved to hand out that it has not got -- off the drawing path, saying why where it
  cannot be reached; MUST apply all of it at once, so that the page holds nothing; and MUST NOT
  read a key it names.
- MUST list on the daemons page of `/settings` this machine's daemon, `Local`, and every daemon
  of another machine the web interface keeps, the same list through `daemon`, each with what
  reaches it and how it stands, drawn again as that changes; MUST offer adding one and
  correcting it on one form, importing hosts of the ssh config not added yet, reaching it now
  and taking it away, each written at once, and MUST reach one as the web interface does; and
  MUST offer batch apply there: this machine's settings of the pages picked -- never the
  accounts, which only a secret sets -- written to each daemon picked as the web interface's
  `Batch apply` writes them, saying how each went.
- MUST let `/epics @<name>` list the epics of the daemon named, and a button of the list turn
  it to another's, keeping to that daemon until turned back; another machine's MUST be read
  through its own web interface reached over ssh, off the drawing path, each offering its
  archive brought here, a backup there and copying what it is, and saying why where it cannot
  be reached; MUST start a new epic there -- a directory there, a flow, a task and its agents,
  set up otherwise as that directory last ran the flow -- and follow it, and follow one going
  there from its menu: what was asked, what each agent said, what the flow asks and how it
  stands, as that machine's web page reads them, a line typed said to the run or answering
  what it asks, leaving it going there on `esc`.
- MUST offer, with `m` on a row of a list of epics, flows, flowverses or daemons, that row's
  menu: what the web page's menu on a click with the other button offers of it, where it can
  be done here and now -- a run of `/epics` being its own sheet, as `enter` opens it.
- MUST list on the accounts page of `/settings` every account under its CLI and offer
  correcting, re-signing and taking it away, never drawing a secret back
  onto the screen, a secret left blank while correcting keeping the one it has.
- MUST make an account on one form -- its CLI, its way in, a name no account is already called,
  what that way asks, and which other CLIs to write it down for -- wherever one is asked for,
  and then ask what it runs without holding up the page it was made from, saying so while it
  asks and saying how that went, why included, once it has; MUST list the ways in through the
  local LiteLLM gateway after the CLI's own, under one heading, and where the `litellm` extra is
  missing for a CLI the gateway can speak to, the line that adds it under that heading instead.
- MUST answer falling back on the fallback page of `/settings` — which places take over from
  which, a chain written on one form of the place that fails, the places it falls back to in the
  order they are tried, added, taken off and put in another order there, and how it is tried
  again — refusing a chain that names the place that fails or one place twice, and offering
  nothing about falling back on the accounts page.
- MUST list on the backup page of `/settings` every backup target -- its name, its URL with any
  credential hidden, its branch, when it is used, and whether it is a default -- and offer
  adding, correcting and removing one on one form: its name, URL and branch, `On session close`,
  `Every N minutes` (off, or how many), `On epic end` -- none switched on is manual only -- and
  `Default`; refusing a name that is not one short word or is another target's, or no URL; and
  offer `download` from the saved targets: every epic one holds, the target picked where there
  is more than one, fetched afresh off the drawing path, by machine and then by directory,
  newest first, those already here marked, one downloaded as an import lands it, saying where
  and, where it cannot be resumed here, why.
- MUST offer on the usage page of `/settings` what the epics spent by day and by flow -- of this
  directory or of every one on this machine, looking back 7, 30, 90 or 365 days -- read off the
  drawing path, holding nothing.
- MUST list the runs of this directory newest first with when each began, its flow, its task, its
  agents, what it spent and how long it took where it said, the targets it is backed up to, how
  it went and how many sessions it opened, marking which can be picked up, readable while one runs;
  and, turned by `ctrl+t` or a button and remembered for this machine, those of every directory
  on this machine instead, each with its directory, read without holding the screen up; found as
  the web finds them -- by how each went, its flow, its directory and its task -- a page at a time.
- MUST refuse to carry on a run of another directory, saying where it ran.
- MUST tell, of every epic on this machine, what the web interface tells of it -- each notice
  `runtime/watching` works out of the hosts' status, never attaching -- as a card that goes
  after a while and, unless the system is turned off, the terminal's bell and a system
  notification; never of the epic on the screen, this directory's while its log or the
  monitor is up; and MUST dot each epic told of on `/epics` until it is opened there.
- MUST offer on the notifications page of `/settings` the kinds the web interface's offers,
  each turned on or off, and whether the system is told too, kept with that page's.
- MUST import an epic from a `.hmzepic`, by a key or a button, asking which file as a path,
  starting from the downloads directory and taking a file dropped onto the terminal as its
  path, read without holding the screen up, and put the cursor on it -- listing this machine's where
  it is of another directory -- or on the one already here that it would be; MUST refuse a file
  that is not one in plain words, and say on an imported epic that cannot go on here why not.
- MUST offer per run where it is written down, carrying it on where its flow says so, and
  exporting it; an export MUST ask where it goes, a file or a directory to put it in,
  offering the downloads directory, and land nowhere else, MUST carry a trace of that run's own sessions and no transcript, say where it
  landed and how big it is, and replace that run's last export rather than pile up; and, where
  there is a backup target, `upload` it -- to the targets it was started with, else the
  defaults -- without holding anything up, saying where it goes, with how its last backup to
  each target went said on it.
- MUST offer per run, finished or going, its graph, read as it stands without holding the screen up:
  a box per agent as the monitor draws one, with its turns and the handovers between neighbours read
  back out of its logs, its sessions under it, and the tree of flows it called; and each session
  read whole, what it did in order -- turns, model calls, tools with what went in and came out, what
  it said -- searchable, each cut to a few lines until opened.
- MUST open a run in Exomyth from its sheet and its graph, and the run going from the monitor by
  `ctrl+e` or a click above its graph, never a chat's, which has no timeline: every session a
  process under the one that started it, foldable, each lane of any process a row of its spans
  cut to the eighth of a cell and coloured by category in the theme's colours under a ruler of
  time; zoomed and panned around the span under the cursor, which moves between spans and rows,
  is searched to by name, opens a pane of the span or its process whole, and picks a stretch of
  time from one span to another, summed by category in the pane; and, a tab away each, a flame
  of where the stretch picked or the time on screen went -- each agent its stack, its sessions
  merged or apart, then its spans as they nest -- weighed by time, tokens in or out or count,
  and every slice name of it summed in a table sorted by any column, a slice picked found on the
  timeline. Read without holding the screen up and again every few seconds while the run goes,
  drawing only the rows on screen, responsive at fifty thousand spans.
- MUST make the monitor the parent screen and the log its child: a full-screen graph of the run
  over the log's own prompt, where every command works, with a graph status line in place of the
  log's; reached by `←` on an empty prompt outside a chat and never by `esc` or a command, and left by `→` on an
  empty prompt for the log last read.
- MUST draw the run on the monitor as a graph — a box per agent in the flow's order with the
  handovers between them, each opened out to its sessions and shut again by `space` or a click
  on its edge or on it already picked — or, by `ctrl+t` or a click on the switch above it, as a
  list of the same nodes without the handovers, the working ones first and the rest in order —
  only nodes that have taken a turn, marked as working or as having something unread — never
  refused while a flow runs, redrawn as the run moves, every clock stopping where the run stopped.
- MUST show the environment each session works in under that session, as a node that opens to a
  page of its own — its kind, where it is, what the flow declared of it, where the run put each of
  its sessions' harnesses and the sessions working in it, live — from which a session is read.
- MUST lead the monitor with a node for the epic, which says how far the run has got and opens
  the epic's page once there is an epic, and reads no log, then a node per outworlder, the node
  read or its agent selected when it opens, and read any node — working or ended — with enter
  or a click, two on an agent, the arrows moving between nodes while nothing is typed.
- MUST open the epic from its node to a page of it, live: its figures -- time, spend, tokens --
  its budget against what has gone of it limit by limit, what it was set up with -- flow, task,
  agents, environments, params, whether profiled -- and the flows it called; and, for every
  flow but `chat`, offer stopping it there while it runs and forcing it once it is stopping, each
  asked first.
- MUST report spend per model, by kind of token and never as one total over the kinds, in an
  order that does not change, money beside tokens where known and tokens alone where not, marking
  a figure that is only a floor, and the rate as output tokens a second.
- MUST draw the board a flow and a person share under the diagram, its lines nodes like any
  other, applying changes at once while the flow runs, taking a line away when it is saved empty,
  and refusing, where enter was pressed, to edit a line the flow owns.
- MUST make `/settings [page]` the one menu of every setting, a screen of its own in nine
  pages, eight from the broadest to the nearest -- general for this machine (details, the btw
  agent where there is one, and reporting, each under a heading of what it is about),
  notifications, daemons, accounts, fallback, runtimes, backup, and workspace for this
  directory, which it names across its top -- then usage, opening on those pages alone and
  going into one on `enter` or a click and back out on `esc`, or straight into the one named
  `general`, `notifications`, `daemons`, `accounts`, `fallback`, `runtimes`, `backup`,
  `workspace` or `usage`,
  offered as it is typed, or by its old name `settings`, `everywhere`, `directory` or
  `environments`, opening `/flow` on its flowverses for `flowverses` and saying they moved
  there, refusing any other; forget this directory alone; keep what
  each page last said while another is read; and remember whether details are shown.
- MUST apply each saved setting at once where it can, and otherwise say beside its row and in
  the transcript when it lands: accounts from the next agent session, forgetting from the next
  launch.
- MUST ask once, at a first start and only with somebody there, whether humanize may report its
  own failures — what would be sent and what never would — unanswered if it is walked away from.
- MUST hold what a menu changes until it is saved from its save button or saving is confirmed
  on the way out, asking on the way out of one holding changes; anything that runs an external
  command or writes to the board MUST apply at once instead, and a page that holds nothing MUST
  have no save button.
- MUST answer a sheet once however many times its key is pressed.
- MUST draw every menu as `/settings` is drawn, on a screen of its own -- or, for a question that
  arrives rather than is walked to, a box in the middle of the screen answered by its buttons:
  the way there across its top, each step a way back to it, a menu of pages -- `/settings`,
  `/flow` -- a step per page it is inside of; its question and what it is for; its list, the row
  under the cursor filled; whatever it does about that list rather than to one row of it --
  search, add, install, fetch or ask again, copy, take away what the menu is about, answer a
  form, save -- as a button under the list, the one that answers the menu last and apart; and
  its keys under that, said in one place, for where the focus is.
- MUST give every menu the same keys and only these: `↑`/`↓`, `←`/`→`, `enter`, `esc`,
  `tab`/`shift+tab`, `backspace`, `/` where its list can be searched, `m` on a row with a menu,
  typing on a form, and `shift+enter`/`ctrl+j` on a written row that takes several lines. A
  row changed where it stands MUST change only between an `enter` -- or, on a form's written
  row, a letter -- that begins it and an `enter` that keeps it, `esc` putting it back, and
  keeping one on a form MUST move on to what is still to be answered and then to the button
  that answers it, `done`, which says what answering does; a value a menu changes from a fixed
  few MUST instead be picked, with the keys or a click, from every value it can take dropped
  under its row, `esc` or a click off it picking none, and never stepped with `←`/`→` or turned
  over in place; and a search MUST be asked for, with `/` or its button, into a box above the
  list.
- MUST complete a path written on a form as it is typed, as a shell does: `~` the home it names,
  every file and directory it could become said under the list while it is being written, and
  `tab` finishing as much of it as all of those share or, where that adds nothing, taking each
  of them in turn.
- MUST make every row, button, value and step of the way across the top of a menu reachable by
  the keys and by the mouse alike: a click choosing, opening or pressing it, the pointer marking
  what a click would take, and a click off a box or a dropped list answering nothing.
- MUST give a selection back as the text written rather than the rows it was drawn on, let one go
  when what it was made against changes, and never scroll the transcript out from under a reader.

## Keys

| Key | Where | What it does |
| --- | --- | --- |
| `enter` | editor, sheets | send the line or take the offer; open the row under the cursor, drop its values or take one, begin and keep writing it, or press the button with the focus |
| typing | forms | on a written row, begin writing it |
| `tab` | forms | on a path being written, finish it, or take the next thing it could become |
| `shift+enter`, `ctrl+j` | editor, sheets | break the line |
| `shift+tab`, `tab` | app | round the views forward and back, but in a chat |
| `tab`, `shift+tab` | sheets | between the list, its search and the buttons under it |
| `/` | sheets | search the list, where it can be searched |
| `m` | sheets | the menu of the row under the cursor, where it has one |
| `esc` | sheets | one step back, out of a change or a search first; on a page of `/settings` or `/flow`, out to the page above it |
| `backspace` | sheets | up to the menu this one was opened from, but the row's own on a written row; on a page of `/settings` or `/flow`, out to the page above it |
| `←`, `→` | log, monitor | on an empty prompt outside a chat: up to the monitor; back to the log last read |
| `↑`, `↓`, `enter` | monitor | on an empty prompt: the node before or after; read it |
| `space` | monitor | on an empty prompt: open an agent out to its sessions, or shut it |
| `ctrl+t` | monitor | the graph or the list |
| `ctrl+e` | monitor | on an empty prompt: the epic going in Exomyth |
| `w`/`s`, `a`/`d`, `←`/`→`, `↑`/`↓`, `enter`, `p`, `v`, `f`, `0`, `space`, `/`, `n`/`N`, `tab`/`shift+tab`, `t`, `m`, `o`/`O`, `r` | Exomyth | zoom, pan, the span before or after, the row above or below, the span's pane, its process's, begin, hold or drop a range, fit it, the whole run, fold, search, the next found, the next view or the one before, the flame's weight, sessions merged or apart, the slices' column and order, read again |
| `ctrl+c` | app | clear the line; on an empty one, twice stops the flow, or in a chat or with nothing running exits |
| `ctrl+q` | app | what `/exit` does |
| `↑`, `↓` | sheets | walk the rows, round the ends, keeping the row being written; back to the list from its search or its buttons; in a box, between its buttons |
| `←`, `→` | sheets | along the buttons, round the ends; on the list, into what the row under the cursor opens and back up out of the menu, but not off a written row -- in `/settings` and `/flow`, into a page and back out |

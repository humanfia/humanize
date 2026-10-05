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
  release, by SemVer, and that they are updated from `/flow`. MUST NOT install, update or
  uninstall a flow while one runs.
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
- MUST keep one transcript per agent, one per conversation, one per outworlder and one more
  they all appear on -- every agent's lines and all that every outworlder asks and is answered
  -- open on the last and return to it when a run starts, and bound what is kept without
  dropping it or the one read.
- MUST round the shared transcript, the conversations with a turn open and the outworlders of
  a running flow, forward on `shift+tab` and back on `tab`, a conversation that has ended
  leaving the round while staying readable from the monitor.
- MUST show which agent is read, how many conversations it holds, whether it is working and
  whether it has something unread — nothing unread while the shared transcript is read — and
  each outworlder of a running flow, whether it is asking, away, read or unread.
- MUST send a typed line to the conversation being read, or to whichever of the agent's has a
  turn open, holding it for the next turn otherwise, and keep it against the agent that took it.
- MUST name what is running as the flow started and whatever it called, innermost last.
- MUST offer exactly these commands, each doing what it says: `/flow`, `/btw`, `/epics`,
  `/resume`, `/settings`, `/clear`, `/afk`, `/claim`, `/stop`, `/exit`. `/btw [question]` MUST enter btw
  mode, marked on the status line, in which every typed line is one more turn of one side
  conversation until `/btw` or esc leaves it and closes it; MUST NOT ask the flow's own sessions;
  MUST answer in cyan in the current view. In a session's view, ended ones included with no flow
  running, MUST ask a read-only, skill-less fork of that session where its CLI forks, else a
  read-only, skill-less session of the same agent seeded from a snapshot. In the aggregate or
  monitor MUST ask the btw agent (the one set on `/settings`, else the flow's first) at NONE
  permission with no skills, seeded with a snapshot and the sessions, which reaches a session's
  side conversation by `@ask <session>: <question>`, at most 4 per question.
- MUST carry the last run of this directory of a flow that can be picked up on for `/resume` —
  its flow, roles, params, budget, whether it was profiled and task, picking up its journal, saying which — say why there
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
  what a run may spend and whether it is profiled. A saved menu MUST take
  effect from the next run, and MUST refuse to save a flow whose agent role names no model, or --
  for every flow but `chat` -- one that has no budget.
- MUST let what a run may spend -- a duration, a cost, output tokens, and whether a turn is let
  finish -- be set and read on the page its roles are on, and whether a run is profiled as well
  as traced be switched and read beside it, off until it is switched on, and remembered with
  the budget per flow; a run started MUST be profiled exactly where that says so.
- MUST say where a role's harness went as its first session on another machine opens: here,
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
  its transcript and the shared one and answered with the next line typed on either -- the
  oldest of that outworlder's, or of any on the shared one -- an offered answer taken by its
  number as well; `/afk` MUST make the outworlder read away, or every one elsewhere that this
  frontend may answer for, leaving the ones another holds as they were, and MUST outlive it.
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
  host holds it; `/stop` MUST stop it for every frontend.
- MUST offer and run a command only where it works -- `/afk` anywhere but one agent's
  transcript, `/claim` only on an outworlder's, `/stop` only on the monitor and the shared
  transcript -- and refuse it elsewhere, saying where it works.
- MUST offer and run a command only while it would do something -- `/stop` while a flow runs
  and is not stopping, `/resume` while none is going and there is a run here to carry on,
  `/btw` while there is somebody to ask, `/claim` and `/afk` not on an outworlder another
  frontend holds, a flow to choose while none runs -- and refuse it otherwise, saying why; MUST
  say what a command does, and which keys work, as things stand, and reconsider both the moment
  the run or the view changes.
- MUST list on the runtimes page of `/settings` every runtime under its
  backend -- ssh hosts, docker daemons with what each may hand out, docker swarms with where
  their tasks may be placed and what they may reserve all told, and this Mac's Apple containers
  with what they may hand out -- and offer making each on one
  form wherever one is asked for, importing the hosts an ssh config names -- the user's
  own or another file, switched on per host and saved already or not, never writing to it --
  and per runtime correcting it, checking it and taking it away, its affinity -- where the
  harness of work on it runs, in order -- written on its form as `self`, `local` and
  `<backend>:<name>`, and the saved runtimes it falls back to, in order; MUST ask one what it
  has when it is made or corrected on that page and when it is checked, an import asking none -- an ssh
  host its home, CPUs, memory and GPUs, a docker daemon its CPUs, memory, GPUs and OCI runtimes,
  a swarm which of its nodes may take a task and what those have all told, Apple's containers
  the CPUs and memory their system counts, and each what it is
  saved to hand out that it has not got -- off the drawing path, saying why where it
  cannot be reached; MUST apply all of it at once, so that the page holds nothing; and MUST NOT
  read a key it names.
- MUST list on the accounts page of `/settings` every account under its CLI and offer
  correcting, re-signing and taking it away, never drawing a secret back
  onto the screen, a secret left blank while correcting keeping the one it has.
- MUST make an account on one form -- its CLI, its way in, a name no account is already called,
  what that way asks, and which other CLIs to write it down for -- wherever one is asked for,
  and then ask what it runs without holding up the page it was made from, saying so while it
  asks and saying how that went, why included, once it has.
- MUST answer falling back on the fallback page of `/settings` — which places take over from
  which, a chain written on one form of the place that fails, the places it falls back to in the
  order they are tried, added, taken off and put in another order there, and how it is tried
  again — refusing a chain that names the place that fails or one place twice, and offering
  nothing about falling back on the accounts page.
- MUST list the runs of this directory newest first with when each began, its flow, its task, how
  it went and how many sessions it opened, marking which can be picked up, readable while one runs.
- MUST offer per run where it is written down, carrying it on where its flow says so, and
  exporting it; an export MUST ask where it goes, a file or a directory to put it in, and land
  nowhere else, MUST carry a trace of that run's own sessions and no transcript, say where it
  landed and how big it is, and replace that run's last export rather than pile up.
- MUST make the monitor the parent screen and the log its child: a full-screen graph of the run
  over the log's own prompt, where every command works, with a graph status line in place of the
  log's; reached by `←` on an empty prompt and never by `esc` or a command, and left by `→` on an
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
- MUST lead the monitor with a node for every agent's log, selected when it opens, then a node per
  outworlder, and read any node — working or ended — with enter or a click, two on an agent, the
  arrows moving between nodes while nothing is typed.
- MUST report spend per model, by kind of token and never as one total over the kinds, in an
  order that does not change, money beside tokens where known and tokens alone where not, marking
  a figure that is only a floor, and the rate as output tokens a second.
- MUST draw the board a flow and a person share under the diagram, its lines nodes like any
  other, applying changes at once while the flow runs, taking a line away when it is saved empty,
  and refusing, where enter was pressed, to edit a line the flow owns.
- MUST make `/settings [page]` the one menu of every setting, a screen of its own in five pages
  from the broadest to the nearest -- general for this machine (details, the btw agent where
  there is one, and reporting, each under a heading of what it is about), accounts, fallback,
  runtimes, and workspace for this directory, which it names across its top --
  opening on those pages alone and going into one on `enter` or a click and back out on `esc`,
  or straight into the one named `general`, `accounts`, `fallback`, `runtimes` or `workspace`,
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
  `tab`/`shift+tab`, `backspace`, `/` where its list can be searched, typing on a form, and
  `shift+enter`/`ctrl+j` on a written row that takes several lines. A
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
| `shift+tab`, `tab` | app | round the views forward and back |
| `tab`, `shift+tab` | sheets | between the list, its search and the buttons under it |
| `/` | sheets | search the list, where it can be searched |
| `esc` | sheets | one step back, out of a change or a search first; on a page of `/settings` or `/flow`, out to the page above it |
| `backspace` | sheets | up to the menu this one was opened from, but the row's own on a written row; on a page of `/settings` or `/flow`, out to the page above it |
| `←`, `→` | log, monitor | on an empty prompt: up to the monitor; back to the log last read |
| `↑`, `↓`, `enter` | monitor | on an empty prompt: the node before or after; read it |
| `space` | monitor | on an empty prompt: open an agent out to its sessions, or shut it |
| `ctrl+t` | monitor | the graph or the list |
| `ctrl+c` | app | take back the nearest thing; twice stops the flow |
| `ctrl+q` | app | what `/exit` does |
| `↑`, `↓` | sheets | walk the rows, round the ends, keeping the row being written; back to the list from its search or its buttons; in a box, between its buttons |
| `←`, `→` | sheets | along the buttons, round the ends; on the list, into what the row under the cursor opens and back up out of the menu, but not off a written row -- in `/settings` and `/flow`, into a page and back out |

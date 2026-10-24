# Web

## 1. Scope

This document specifies the behaviour of the page that `hmz web` serves: how the user reaches it,
how it lays out the workspaces and epics of a daemon, how the user reads, steers, starts, imports
and backs up epics through it, its settings pages, how it reaches the daemons of other machines, how
it notifies the user, and the interaction rules it follows. It specifies only what the user sees and
does on the page.

Out of scope:

- The command line of `hmz web` and its exit statuses: `api/cli.md`.
- Every HTTP endpoint, header, refusal status and event stream the page uses: `api/http.md`.
- The daemon, hosts, attaching and the lifetime of epics: `features/daemons.md` and `api/daemon.md`.
- What a chat is and how it folds away: `features/chat.md`.
- What a side question is, and the btw agent: `features/btw.md`.
- What an epic records, its figures and its timeline: `features/epics.md` and
  `features/monitoring.md`.
- Backup targets and their policies: `features/backups.md`.
- Release checks and `hmz update`: `features/updates.md`.
- Agents, accounts, placements and environments: `features/agents.md`, `features/accounts.md`,
  `features/placements.md` and `features/environments.md`.
- The terminal interface: `features/tui.md`.
- The macOS app that shows the page in a window: `features/desktop.md`.
- The files the settings and notifications are kept in: `api/settings.md` and `api/files/home.md`.

## 2. Definitions

**2.1** The **page** is the single web page `hmz web` serves, together with every view and dialog
drawn in it.

**2.2** **Local** is the daemon of this machine as the page names it. Local is always present on the
page. Where hmz runs in WSL, Local's host is the WSL distribution, shown as `<distro> (WSL)`.

**2.3** An **SSH daemon** is the daemon of another machine that the user has added to the page, and
that the page reaches over ssh as `features/daemons.md` §8 specifies.

**2.4** The **daemon shown** is the daemon whose workspaces, epics, flows and settings the page
draws at a given moment.

**2.5** The **daemon bar** is the area at the foot of the sidebar that names the daemon shown.

**2.6** A **view** is what the page draws beside the sidebar: a new epic, an epic, a session, a log,
an Exomyth, or the flows. A **dialog** is what the page draws over a view: search, download, or
settings.

**2.7** An **address** is the part of the page's URL that names one view or dialog, of one daemon.

**2.8** A **notice** is a record that one epic on one machine ended, asked a person a question, or
waits for what to say next, as §15 specifies. A **notification** is a notice as the page presents it
to the user, with the daemon it came from and whether the user has read it.

**2.9** The **Exomyth** of an epic is the page's view of that epic's timeline and flame graph.

**2.10** A **theme** is a set of colours and pictures the page is drawn in. A **pair** is a light
theme and a dark theme kept together under one name. A **preset** is a pair that comes with hmz.

**2.11** **App settings** are the settings pages that belong to the page and to Local alone.
**Daemon settings** are the settings pages that each daemon keeps for itself.

**2.12** A **flowverse** is an index of installable flows, as `api/flows.md` defines it.

## 3. Reaching the page

**3.1** `hmz web` MUST print the address of the page once it listens, and MUST open a browser on
that address unless the user asked it not to or this machine has no desktop, as `api/cli.md`
specifies.

**3.2** The page MUST be reachable only from this machine, and only by a browser that opened the
printed address, as `api/http.md` specifies.

**3.3** A browser that has not opened the printed address of the running `hmz web` MUST be shown
`This browser is not let in.` in place of every view, with the instruction to open the address `hmz
web` printed.

**3.4** The page MUST serve every workspace of the daemon shown, wherever `hmz web` was started.

**3.5** The page MUST offer the workspace `hmz web` was started in first wherever it offers a
workspace for a new epic.

**3.6** The page MUST NOT show a secret: an account MUST be shown by its harness, its name, its way
in and the names of the variables it sets, and never by a value.

**3.7** The page MUST NOT show a URL with credentials signed into it; it MUST show such a URL with
the credentials removed.

**3.8** Stopping `hmz web`, or closing the page, MUST NOT stop any epic.

## 4. Layout and navigation

### 4.1 Layout

**4.1.1** The page MUST consist of a sidebar and, beside it, the current view.

**4.1.2** The sidebar MUST show, from top to bottom: the Humanize mark, the notification bell, a
control that hides the sidebar, the entries `New epic`, `Search epics` and `Flows`, the workspaces
of the daemon shown as §5 specifies, and the daemon bar.

**4.1.3** The `Flows` entry MUST show how many installed flows have a newer release, where at least
one has.

**4.1.4** On a screen as narrow as a phone's, the sidebar MUST be a drawer opened by a button, and
every view MUST be usable without horizontal scrolling of the page.

**4.1.5** The page title MUST name the machine of the daemon shown.

### 4.2 Addresses

**4.2.1** Every view and every dialog MUST have an address that the user can keep and open again,
and opening that address MUST draw the same view or dialog.

**4.2.2** Every address MUST name the daemon it belongs to; an address that names no daemon MUST
belong to Local.

**4.2.3** Every link the page draws MUST keep the daemon of the address the page is on.

**4.2.4** Opening an address of another daemon MUST draw the sidebar and the view again, of that
daemon, and MUST stop drawing anything of the previous daemon.

**4.2.5** An address of an epic's log of every session MUST open that epic.

> Informative: the address forms are listed in `api/http.md`.

### 4.3 Keyboard

**4.3.1** Cmd+K, or Ctrl+K, MUST open `Search epics`.

**4.3.2** Cmd+Shift+O, or Ctrl+Shift+O, MUST open a new epic.

**4.3.3** Cmd+., or Ctrl+., MUST hide or show the sidebar.

**4.3.4** Escape MUST close the dialog that is open, and MUST close the menu or picker that is open.

**4.3.5** In every box that sends text, Enter MUST send the text and Shift+Enter MUST start a new
line; Enter MUST NOT send while an input method is composing.

**4.3.6** Every control on the page MUST be reachable and operable by keyboard.

### 4.4 Menus, labels and text

**4.4.1** A right click on a thing the page draws MUST open a menu of the page's own listing what
the user can do to that thing.

**4.4.2** A right click MUST open the browser's own menu, in place of the page's, only where there
is text to read or to write under it.

**4.4.3** The page MUST offer such a menu on at least: a workspace in the sidebar, an epic, an
agent, a session, a node of an epic's graph, a flow, a flowverse, a search result, and a line of a
transcript; and between the epics of the sidebar, where it MUST offer `Import`.

**4.4.4** The text that names the page's own parts MUST NOT be selectable as text.

**4.4.5** Every label the page draws -- a button, a tab, a menu item, a heading, a field label --
MUST be a word or a short phrase, and MUST NOT be a sentence.

**4.4.6** The page MUST call one execution of a flow an epic, and MUST NOT call it a run.

**4.4.7** Wherever the page shortens a text -- a path above all -- it MUST show the whole text on
hover, without delay.

**4.4.8** The page MUST offer to copy every path, link, task and identifier that it shows in a menu.

**4.4.9** The page MUST say every refusal and every failure where it happened, in one sentence, and
MUST NOT hide it.

**4.4.10** The page MUST NOT draw over what the user is typing while what the user is typing about
still stands.

### 4.5 Paths

**4.5.1** Every field that takes a path on this machine MUST offer a browser of directories, opened
from a button beside the field, that lists one directory at a time and lets the user choose a
directory, or a file where a file is wanted.

**4.5.2** Every field that takes a path MUST also accept a typed path, and MUST complete it as it is
typed.

**4.5.3** The page MUST NOT accept a path that is not a directory as a workspace.

## 5. Workspaces and the epics list

**5.1** The sidebar MUST show every workspace of the daemon shown as a folder: each workspace an
epic ran in, each workspace written down in the settings, and each workspace the user opened by its
path.

**5.2** A workspace the user opens by its path MUST be written down in the settings, and MUST stay
in the sidebar from then on.

**5.3** The sidebar MUST order the workspaces with those that have an epic going first, then by
their latest epic, newest first.

**5.4** Each folder MUST list its epics newest first, and MUST say `No epics` where it has none.

**5.5** The user MUST be able to fold a folder away and open it again; the page MUST remember which
folders are folded in this browser.

**5.6** Each folder MUST offer `+`, which opens a new epic in that workspace.

**5.7** The menu of a folder MUST offer: a new epic there, its flows, searching it, copying its
path, folding or opening it, its workspace settings, its usage, and, where no epic ran there,
forgetting it.

**5.8** Each epic in the sidebar MUST show a mark of how it ended or that it is going, its task's
first line, and either `live`, where a host is going with it, or how long ago it began.

**5.9** An epic that another process is going with, outside any host, MUST be marked as going and
MUST NOT be marked `live`.

**5.10** A chat MUST be marked `running` while its agent answers and `done` otherwise, short of
failing, and MUST NOT be marked `live`.

**5.11** An epic other than a chat MUST be expandable into its agents, and each agent into the
sessions it opened; a chat MUST NOT be expandable. The page MUST remember in this browser which
epics are expanded.

**5.12** The menu of an epic MUST offer: open it, its Exomyth (not for a chat), resume it where it
can be resumed, a new epic like it, copying its link, its task and its name, exporting it once it is
no longer going, uploading it, and stopping it while a host is going with it (not for a chat).

**5.13** The sidebar MUST list a bounded number of epics at first and MUST offer `Show more` while
more exist.

**5.14** The sidebar MUST show the epics of the daemon shown as they change, without the user
asking.

## 6. An epic

### 6.1 Common rules

**6.1.1** An epic MUST be drawn from what its host tells the page while it is going, and from what
was written down once it has ended, as `features/epics.md` specifies.

**6.1.2** The page MUST name every agent by its own name: its node, its sessions `<agent>/<n>`, its
log, its address and what is said to it. The role the agent fills MUST be shown only after the name.

**6.1.3** The page MUST name a person by the role the person answers.

**6.1.4** While an epic goes, the page MUST offer every action a frontend can take on it, as
`features/daemons.md` §6 lists them.

### 6.2 Graph and list

**6.2.1** An epic other than a chat MUST open as a graph: one node per agent, in a frame for the
flow it worked in, each saying what it runs, whether it is working or idle and for how long, and its
tokens; one node per person, drawn apart from agents; one arrow for each direction in which the epic
handed over from one agent to another, with how many times; the last handover and the working agent
marked.

**6.2.2** Each node MUST show one lane per session the agent opened, with a mark for each turn over
the epic's time, and MUST mark a turn still open.

**6.2.3** The user MUST be able to move the graph by dragging anywhere on it, to zoom it by a pinch
or a wheel about the pointer, and to bring it back to the middle with `Recenter`.

**6.2.4** The user MUST be able to switch the graph to a list of the agents, the working agents
first; the page MUST remember the choice in this browser.

**6.2.5** Choosing an agent MUST mark it on the graph and give it its own address.

### 6.3 The panel

**6.3.1** Beside the graph, the page MUST offer a panel that the user can hide and show, with the
tabs `Epic`, `Aside`, `Board` where the epic has a board, and `People` where its flow has a person.

**6.3.2** `Epic` MUST show: how long the epic has gone, what it has spent and how fast, one meter
for each limit of its budget, its task, who handed to whom, its spending by model and by kind of
token, each session's environment and where its harness went, the frontends reading it, the flows
going or that it called, how it was set up, and where it is written down.

**6.3.3** The spending MUST NOT be summed over kinds of token into one figure, and a figure that is
only a lower bound MUST be marked as one.

**6.3.4** `Aside` MUST let the user ask a side question as `features/btw.md` specifies: of The
Epic, or of one session of the epic, including an epic its host no longer holds and its sessions,
of which The Epic MUST be told that epic.

**6.3.5** `Aside` MUST hold several side conversations, as `features/btw.md` §8 states, each
picking whom it asks at its start with the control of `features/btw.md` §8 -- `The Epic`, then the
epic's agents, each opening its sessions -- above the box its question is typed in, and MUST NOT
offer a choice of any agent.

**6.3.6** `Aside` MUST keep each side conversation, the side questions asked in it and their
answers for the page opened again, MUST show while each is answering and whom The Epic asks on
the way, MUST let the user close each, and MUST say that side questions never reach the epic.

**6.3.7** `Board` MUST let the user edit, remove and add lines of the epic's board, and MUST NOT
offer to change a line the flow owns.

**6.3.8** `People` MUST, for each person the flow has, let the user claim the role for this browser,
take it over from another frontend, release it, and set it away or back.

### 6.4 Steering an epic that is going

**6.4.1** Under the graph, while the epic waits on a person, the page MUST show each question with
its offered answers as buttons and a field for an answer of the user's own.

**6.4.2** A question that another frontend holds MUST say whose it is.

**6.4.3** The page MUST offer a box that sends a line to the epic, to one agent, to one session or
to one person, as `features/daemons.md` §6 specifies; a session MUST be marked as working while it
has a turn open.

**6.4.4** The page MUST offer `Stop`, which asks for confirmation and then stops the epic for every
frontend; while the epic unwinds, the page MUST offer to force it, which closes every session under
its open turn.

### 6.5 Sessions and logs

**6.5.1** A session MUST open as its transcript, drawn as the terminal interface draws it.

**6.5.2** A line typed under a session MUST go into that session, or MUST answer what that session's
open turn asks.

**6.5.3** The page MUST offer one log per agent, across its sessions, and one log per person, of
what the person was asked and answered; a line typed under one MUST go to whose it is.

**6.5.4** The page MUST NOT offer a log of every session at once.

### 6.6 A chat

**6.6.1** A chat MUST be drawn as its conversation alone, wherever it is opened, as
`features/chat.md` specifies: the task and each line of the user's on one side, each answer of the
agent's on the other.

**6.6.2** The box under a chat MUST send the user's next turn between turns, and MUST answer what
the agent asks while a turn is open, with the offered answers as buttons at the end of the
conversation.

**6.6.3** The page MUST NOT draw what a chat waits for between turns as a question.

**6.6.4** The page MUST NOT offer, for a chat, a graph, its agents or sessions, its Exomyth, its
people, or a way to stop it.

**6.6.5** Each chat MUST be an epic of its own, beside every other chat and every flow of its
workspace; starting a chat or an epic MUST NOT end another.

**6.6.6** A chat that has folded away MUST be carried on, in the same epic, when the user says
something in it, with what was said before drawn above.

### 6.7 An epic written down

**6.7.1** An epic that has ended MUST show how it was set up -- its agents, environments, parameters
and budget -- the tree of flows it called, its sessions, what it spent and how long it took.

**6.7.2** The page MUST offer `Read turns`, which reads the epic's handovers and each session's
turns back out of the logs it kept.

**6.7.3** The page MUST offer `Export`, which downloads the epic as one archive, as
`features/epics.md` specifies.

**6.7.4** The page MUST offer `Upload` on every epic, which backs it up at once to the targets it
was started with, else to the default targets, and MUST answer at once with the targets it was
queued for, without waiting for the push.

**6.7.5** The page MUST say, on hover of `Upload`, how the last backup of the epic to each target
went.

**6.7.6** The page MUST offer `Resume` only where the epic's flow can resume it, and MUST then open
a new epic set up as that epic was started, in that epic's workspace.

### 6.8 Importing

**6.8.1** The page MUST let the user import an exported epic by picking the file, by dropping it
anywhere on the window, or by opening the import address that names its path on this machine;
where hmz runs in WSL, that path MAY be a Windows path, read as WSL names it.

**6.8.2** In a browser, the import address MUST import only once the user presses `Import`.

**6.8.3** An imported epic MUST be imported into the daemon shown, under the workspace it ran in,
and MUST then open on its Exomyth.

**6.8.4** An epic already present MUST be refused, naming it, and the page MUST offer `Open` to go
to it.

**6.8.5** An imported epic that cannot be resumed on this machine MUST say why, and the page MUST
NOT offer to resume it.

## 7. Exomyth

**7.1** The page MUST offer the Exomyth of every epic other than a chat, going or written down.

**7.2** The Exomyth MUST have a `Timeline` tab and a `Flame` tab.

**7.3** The timeline MUST draw each process of the epic's timeline -- each flow, each session, and
each program a profiled epic ran -- as a row of its tracks under a ruler of time, each process under
the process that started it, and MUST draw no arrow between processes.

**7.4** The user MUST be able to fold and open each process, and to fold or open all of them with
`Collapse` and `Expand`.

**7.5** The timeline MUST respond to these inputs:

| Input | Effect |
| --- | --- |
| W, S, Ctrl+wheel, or a pinch | Zoom in or out about the pointer |
| A, D, a sideways wheel, or Shift+wheel | Pan |
| Wheel | Scroll through the processes |
| Click on a span | Pick the span and show it whole with what it carried |
| Double-click on a span, or F | Zoom to the span or process picked |
| Drag across the chart or ruler | Pick a stretch of time; sum its spans and tokens by category |
| / | Find spans by their words; Enter or N the next, Shift+Enter or Shift+N the previous |
| 0 or Home | Show the whole epic |
| Escape | Let go of what is picked |

**7.6** Pointing at a span MUST show it in brief.

**7.7** The flame graph MUST cover the stretch picked on the timeline, or the whole epic where none
is picked: each agent a stack, its sessions merged or apart as the user chooses, then its spans as
they nest.

**7.8** The flame graph MUST be weighable by `Time`, `Tokens in`, `Tokens out` or `Count`, MUST be
invertible bottom up, and MUST zoom to a frame on a click.

**7.9** Under the flame graph, the page MUST show every slice name summed in a table -- count, total
and own time, average, median, 95th percentile, longest, and tokens -- sortable by any column.

**7.10** The Exomyth MUST draw in the theme shown, and MUST stay responsive with an epic of fifty
thousand spans.

**7.11** The Exomyth of an epic still going MUST be read again while it is shown.

## 8. A new epic

**8.1** `New epic` MUST open on the workspace `hmz web` was started in, or on the workspace whose
`+` the user pressed, and on the flow that workspace last ran.

**8.2** The user MUST be able to pick any workspace the daemon shown serves, or to open one by its
path with completion as it is typed, or to pick `No workspace`.

**8.2.1** With `No workspace` picked, the form MUST offer the flows and the set-up of the
workspace `hmz web` was started in, and starting MUST start the epic in a new directory made for it
alone in the system's temporary directory.

**8.3** The user MUST be able to pick any flow on offer in that workspace.

**8.4** The form MUST offer a box for the task; Enter in it MUST start the epic.

**8.5** `Options` MUST hold what the flow is set up with, as that workspace last set it up: for each
agent role an agent, for each environment role an environment, the parameters, the budget, the
backup targets, `Profile flow` and `Profile environment`.

**8.6** The form MUST show beside `Options` what is set.

**8.7** An agent MUST be set up a part at a time, as `features/agents.md` specifies: a harness
installed here that can fill the role; the account it runs as, this machine's own or one made, with
a way to make one; a model known runnable as that account, asking the harness where none is known
yet and accepting a typed model where it cannot say; and an effort that model takes.

**8.8** An environment MUST be set up a part at a time, as `features/environments.md` specifies: its
backend, a runtime of that backend saved or made there, and its directory, completed as it is typed
where it is on this machine.

**8.9** Each agent and each environment set up on the form MUST come to what `-a` and `-e` spell, as
`api/cli.md` specifies.

**8.10** The backup targets MUST default to the default targets until a choice is saved.

**8.11** `Save` MUST write down what the form holds for that workspace without starting an epic.

**8.12** Starting an epic MUST write down what the form holds for that workspace, as `Save` does.

**8.13** The form MUST refuse to save or start where a role has no agent, or where, for every flow
but chat, no limit bounds what the epic spends.

**8.14** Once the epic starts, the page MUST go to it; for a chat, to its conversation.

**8.15** Resuming an epic MUST open the form set up as that epic was started, in that epic's
workspace.

## 9. Flows

**9.1** `Flows` MUST have an `Installed` tab and a `Flowverses` tab.

**9.2** `Installed` MUST list each flow on offer in the workspace picked, with what it declares,
and, for one installed from a flowverse, its release and any newer release its flowverse lists.

**9.3** `Installed` MUST let the user start, update and uninstall a flow, and copy it whole into the
workspace.

**9.4** `Flowverses` MUST list every flowverse except the project's and the user's own, and MUST
show nothing of one until the user opens it or chooses to add one.

**9.5** A flowverse opened MUST show whether its index is fetched or written into, the flows it
lists, and every release of each, newest first, with prereleases and the installed release marked,
and MUST name every manifest it skipped.

**9.6** `Flowverses` MUST let the user install, switch to and uninstall a release, and add, fetch
and remove a flowverse; removing a flowverse MUST remove what was installed from it, and MUST ask
for confirmation first.

**9.7** The page MUST fetch every flowverse's index once as `hmz web` starts, without telling the
user.

**9.8** The page MUST refuse to install, update or uninstall a flow while an epic runs on the
machine.

## 10. Search

**10.1** `Search epics` MUST list every epic of the daemon shown, a page at a time, with its
workspace, flow, agents, what it spent, how long it took, how many sessions it opened, whether it
can be resumed and where it is written down.

**10.2** `Search epics` MUST let the user filter epics by how they went, by workspace, by flow and
by words of their task.

**10.3** `Search epics` MUST offer `Import`.

## 11. Settings

### 11.1 Structure

**11.1.1** Settings MUST be a dialog with two groups of pages: `App` and `Daemon`.

**11.1.2** `App` MUST hold `Themes`, `Daemons` and `Notifications`, and MUST be the same whichever
daemon is shown.

**11.1.3** `Daemon` MUST hold `General`, `Accounts`, `Fallback`, `Runtimes`, `Backup`, `Workspace`
and `Usage`, each of the daemon picked above them.

**11.1.4** The daemon picked for the `Daemon` pages MUST be the daemon shown until the user picks
another, MUST be part of the address, and picking it MUST change nothing else on the page.

### 11.2 Daemon pages

**11.2.1** `General` MUST let the user set whether a turn's working is shown, the agent that
answers The Epic (none until one is picked), and whether errors are reported, as
`features/btw.md` and `features/telemetry.md` specify.

**11.2.2** `Accounts` MUST list every account by its harness, way in and the names of the variables
it sets, and MUST let the user ask again what it runs, correct it, copy it to another harness,
remove it, and make one, as `features/accounts.md` specifies.

**11.2.3** Correcting an account MUST keep every value the user leaves blank, and MUST NOT show any
value.

**11.2.4** A way in that runs a harness's own sign-in MUST be shown as needing a terminal, and MUST
NOT be run from the page.

**11.2.5** The ways in through the local LiteLLM gateway MUST be grouped as the terminal interface
groups them, with the command that adds the `litellm` extra where it is missing.

**11.2.6** `Fallback` MUST let the user set, for each step, where a turn goes when a place cannot
take it and how it is tried again, and MUST let the user clear a step, as `features/placements.md`
specifies.

**11.2.7** `Runtimes` MUST list every runtime, and MUST let the user add one from its backend's
fields, change it, check it, remove it after confirmation, and import hosts from the ssh config, as
`features/environments.md` specifies.

**11.2.8** The runtime form MUST offer one field for each setting the backend's runtime takes,
including a docker or swarm runtime's `Name prefix`, each labelled with the setting's name in words.

**11.2.9** `Backup` MUST list every backup target with its repository, branch, policies and whether
it is a default, and MUST let the user add, edit and remove one, as `features/backups.md` specifies.

**11.2.10** `Backup` MUST offer `Download`, which lists every epic a target holds -- by machine and
then by workspace, those already present marked -- with the target picked where there is more than
one, and downloads the epic picked as an import does, opening it.

**11.2.11** `Workspace` MUST show what a workspace was last set up with, for any workspace the
daemon serves, and MUST let the user forget it; forgetting a workspace where no epic ran MUST remove
it from the sidebar.

**11.2.12** `Usage` MUST show what the epics spent by day and by flow, of every workspace or of one,
looking back 7, 30, 90 or 365 days.

**11.2.13** `General`, `Fallback`, `Runtimes` and `Backup` MUST each offer `Batch apply`, which
writes what that page holds to every daemon the user ticks, and MUST say of each daemon whether it
applied or why it refused.

**11.2.14** `Batch apply` MUST NOT remove anything a daemon already has but what the page replaces
whole, and MUST NOT carry a value that only a secret sets; the page MUST say where such a value is
left out.

**11.2.15** `Accounts`, `Workspace` and `Usage` MUST NOT offer `Batch apply`.

### 11.3 App pages

**11.3.1** `Themes` MUST let the user choose a theme as §12 specifies.

**11.3.2** `Daemons` MUST list Local and every SSH daemon with its state, and MUST let the user add,
edit, import, connect and remove SSH daemons as §13 specifies.

**11.3.3** `Notifications` MUST let the user switch each kind of notification on and off -- `Done`,
`Failed`, `Stopped`, `Questions` and `Chat turns` -- and switch system notifications on and off.

**11.3.4** In a browser, `Notifications` MUST offer `Allow`, and the page MUST ask the browser for
leave to show system notifications only when the user presses it.

**11.3.5** The App settings MUST be kept in Local's settings alone, and MUST NOT be kept in any
other daemon's.

## 12. Themes

**12.1** The page MUST be drawn in Humanize's own typeface and in a theme.

**12.2** The page MUST offer the presets: Humanize's own, `Humanize Green`, `Temperate Gold`,
`Concordant Scarlet`, `Restrained Crimson`, `Critical Teal`, `Desirous Indigo`, `Peaceful Lilac`,
`Hateful Silver`, `Devoted Pink`, `Self-Negating Plum`, `Dominant Azure`, `Surviving Jade` and
`Lamenting Orchid`.

**12.3** Under `Auto`, the default, the page MUST follow the browser's light or dark preference with
a pair, or with one theme picked for light and one picked for dark.

**12.4** The user MUST be able to pick one theme to use whatever the browser's preference is.

**12.5** The user MUST be able to make a theme on `Light` or `Dark`, or a pair of the user's own, to
duplicate any theme or pair, and to edit any of the user's own.

**12.6** Editing a theme MUST let the user set its name, its base, each of its colours, and a
picture -- still or moving -- behind the page, the sidebar, the panel and dialogs, each to cover,
fit or tile its plane; a colour left blank MUST be the base's.

**12.7** The page MUST show a theme as it is changed, and MUST keep each change at once.

**12.8** The user MUST be able to export a theme, or a pair with both its themes, as a `.hmztheme`
file, and to import one, as §12.13 specifies the file.

**12.9** The page MUST keep themes in the browser, per browser.

**12.10** A theme MUST be chosen only in `Settings`, in a browser and in the desktop app alike.

**12.11** Where the system asks for reduced motion, the page MUST hold every moving picture still.

**12.12** The page MUST be usable in every theme it offers, including on a screen as narrow as a
phone's.

**12.13** A `.hmztheme` file MUST be one JSON object holding `"hmztheme": 1` and `name`, and either
`base` (`light` or `dark`) with `colors` and `images` for one theme, or `light` and `dark`, each
holding `colors` and `images`, for a pair. `colors` MUST be keyed by the page's colour tokens:
`paper`, `side`, `surface`, `raised`, `ink`, `ink-2`, `ink-3`, `on-ink`, `on-fill`, `link`,
`control`, `control-ink`, `primary`, `on-primary`, `field`, `edge`, `line`, `line-strong`, `hover`,
`scrim`, `green`, `cyan`, `cyan-ink`, `pink`, `pink-ink`, `lavender`, `gold`, `done`, `fail`, and
`lane-1` to `lane-6`. `images` MUST be keyed by plane -- `page`, `sidebar`, `panel`, `dialog` --
each holding `fit` (`cover`, `fit` or `tile`) and `data`, the picture as a data URL.

**12.14** Importing a `.hmztheme` file MUST keep what a theme can hold and MUST drop an unknown
token, a value that is not a colour, and a picture that is not an image.

## 13. Remote daemons

**13.1** The page MUST keep the SSH daemons in Local's settings, as `api/settings.md` specifies.

**13.2** Local MUST NOT be removable or renamable, and no SSH daemon MUST be named `local`.

**13.3** The name of an SSH daemon MUST start with a letter or a digit and MUST consist of letters,
digits, `.`, `_` and `-`.

**13.4** The user MUST be able to add an SSH daemon a part at a time -- its name, host, user, port,
identity file, proxy jump and ssh options -- as an ssh runtime is set up.

**13.5** The user MUST be able to import hosts from the ssh config, each added under its `Host` and
resolved through the ssh config each time it is reached; hosts already added MUST be skipped. The
page MUST NOT write to the ssh config.

**13.6** Removing an SSH daemon MUST ask for confirmation, and MUST forget only how to reach it,
leaving everything on that machine as it is.

**13.7** The page MUST show one daemon at a time: the sidebar, a new epic, search, flows and the
`Daemon` settings pages MUST be of the daemon shown.

**13.8** The daemon bar MUST show the daemon shown, its host, whether it is reached, and how many
epics are going on it.

**13.9** A click on the daemon bar MUST open its menu: `Daemon`, which opens beside it every daemon
and its state; then `Settings` and `Usage`; and `Update` where a newer release of hmz is out.

**13.10** Picking a daemon in that menu MUST switch the page to it and, for an SSH daemon, MUST
reach it; the menu MUST offer `Connect` on an SSH daemon that failed and `Manage`, which opens
`Settings` › `Daemons`.

**13.11** The page MUST show each SSH daemon's state as one of `idle`, `connecting`, `installing`,
`up` and `failed`, with what was said last, as `features/daemons.md` §8 specifies.

**13.12** An SSH daemon that is not `up` MUST be said to be unavailable where the page asks it
something, with its state.

**13.13** The page MUST NOT ask the user for a password or a host key; an SSH daemon that needs one
MUST fail.

## 14. Release notice

**14.1** Where a newer release of hmz is out than the one serving the page, as `features/updates.md`
specifies, the page MUST mark the daemon bar and MUST offer `Update` in its menu.

**14.2** `Update` MUST copy the command `hmz update` for the user to run in a terminal, and MUST NOT
update anything itself.

## 15. Notifications

### 15.1 Notices

**15.1.1** `hmz web` MUST make a notice of each of these, for every epic of its own machine:

| Kind | When |
| --- | --- |
| `done` | An epic ended done; or a chat finished a turn |
| `failed` | An epic failed, crashed, ran out of budget or was refused |
| `stopped` | An epic other than a chat was stopped |
| `asked` | A flow asked a person a question |
| `listening` | A flow other than a chat waits for what to say next |

**15.1.2** `hmz web` MUST NOT make a notice of anything that already stood when it started.

**15.1.3** Watching for notices MUST NOT keep any host from going.

**15.1.4** Each notice MUST name its workspace, its epic, its flow and its task, and, where it is a
question, the role asking and the question.

### 15.2 The notifications list

**15.2.1** The page served by Local MUST gather the notices of Local and of every SSH daemon while
it is `up` into one list of notifications, each naming its daemon and whether it is read.

**15.2.2** The list MUST keep the newest 200 notifications.

**15.2.3** A notice of a kind the user switched off MUST NOT be kept, counted or shown.

**15.2.4** The bell MUST show how many notifications are unread, whichever daemon is shown.

**15.2.5** A click on the bell MUST open the list, newest first; a click on a notification MUST open
its epic on its daemon; the user MUST be able to mark one or all read and to clear the list.

**15.2.6** Each new notification MUST also show as a card in a corner of the page that goes away
after a few seconds.

**15.2.7** The sidebar MUST mark each epic that has an unread notification, and each folded
workspace that holds such an epic.

**15.2.8** Every notification of the epic the page is on MUST be read while the user is on it, and a
new one of that epic MUST be read as it comes, without a card and without a system notification.

### 15.3 System notifications

**15.3.1** While the page is hidden or not focused, and unless the user switched system
notifications off, the page MUST show each new notification as a system notification: in a browser
through the browser, once the browser allows it, and in the desktop app as `features/desktop.md` §9
specifies.

**15.3.2** A click on a system notification MUST bring the page forward on the epic it is about.

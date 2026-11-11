# The Humanize Protocol: Web Interface

## Abstract

This document specifies the web interface of hmz: the page a browser shows and what a user does on
it, and the HTTP interface the page and other programs are served.

## Status of This Document

This document is one of the documents of the Humanize Protocol, which Section 2.2.4 of [CORE] lists.
It is normative. It is cited by the tag [WEB].

## Table of Contents

- [1. Introduction](#1-introduction)
- [2. Conventions and Terminology](#2-conventions-and-terminology)
- [3. The Page](#3-the-page)
  - [3.1. Scope](#31-scope)
  - [3.2. Terminology](#32-terminology)
  - [3.3. Reaching the page](#33-reaching-the-page)
  - [3.4. Layout and navigation](#34-layout-and-navigation)
  - [3.5. Workspaces and the epics list](#35-workspaces-and-the-epics-list)
  - [3.6. An epic](#36-an-epic)
  - [3.7. Exomyth](#37-exomyth)
  - [3.8. A new epic](#38-a-new-epic)
  - [3.9. Flows](#39-flows)
  - [3.10. Search](#310-search)
  - [3.11. Settings](#311-settings)
  - [3.12. Themes](#312-themes)
  - [3.13. Remote daemons](#313-remote-daemons)
  - [3.14. Release notice](#314-release-notice)
  - [3.15. Notifications](#315-notifications)
- [4. HTTP Interface](#4-http-interface)
  - [4.1. Scope](#41-scope)
  - [4.2. Terminology](#42-terminology)
  - [4.3. Listening](#43-listening)
  - [4.4. Admission](#44-admission)
  - [4.5. Requests and answers](#45-requests-and-answers)
  - [4.6. Streams](#46-streams)
  - [4.7. Workspaces and slots](#47-workspaces-and-slots)
  - [4.8. The epics held](#48-the-epics-held)
  - [4.9. Side questions](#49-side-questions)
  - [4.10. Epics written down](#410-epics-written-down)
  - [4.11. Flows](#411-flows)
  - [4.12. Paths](#412-paths)
  - [4.13. Settings](#413-settings)
  - [4.14. Daemons](#414-daemons)
  - [4.15. Notices and notifications](#415-notices-and-notifications)
- [5. Security Considerations](#5-security-considerations)
- [6. References](#6-references)
  - [6.1. Normative References](#61-normative-references)

## 1. Introduction

This document specifies the web interface of hmz: the page a browser shows and what a user does on
it, and the HTTP interface the page and other programs are served.

This document is organised as follows:

- Section 3: The Page.
- Section 4: HTTP Interface.

## 2. Conventions and Terminology

The key words "MUST", "MUST NOT" and "MAY" in this document are to be interpreted as described in
BCP 14 [RFC2119] [RFC8174] when, and only when, they appear in all capitals, as shown here.

The conventions for numbering and citation, and every term of the shared glossary, are those of
Section 2 of [CORE].

## 3. The Page

### 3.1. Scope

Section 3 specifies the behaviour of the page that `hmz web` serves: how the user reaches it,
how it lays out the workspaces and epics of a daemon, how the user reads, steers, starts, imports
and backs up epics through it, its settings pages, how it reaches the daemons of other machines, how
it notifies the user, and the interaction rules it follows. It specifies only what the user sees and
does on the page.

Out of scope:

- The command line of `hmz web` and its exit statuses: [CLI].
- Every HTTP endpoint, header, refusal status and event stream the page uses: Section 4.
- The daemon, hosts, attaching and the lifetime of epics: Section 3 of [DAEMON] and Section 4 of
  [DAEMON].
- What a chat is and how it folds away: Section 8 of [CORE].
- What a side question is, and the btw agent: Section 9 of [CORE].
- What an epic records, its figures and its timeline: Section 3 of [CORE] and Section 10 of [CORE].
- Backup targets and their policies: Section 11 of [CORE].
- Release checks and `hmz update`: Section 13 of [CORE].
- Agents, accounts, placements and environments: Section 4 of [CORE], Section 5 of [CORE], Section 6
  of [CORE] and Section 7 of [CORE].
- The terminal interface: [TUI].
- The macOS app that shows the page in a window: Section 3 of [DESKTOP].
- The files the settings and notifications are kept in: Section 3 of [FILES] and Section 4 of
  [FILES].

### 3.2. Terminology

**3.2.1** The **page** is the single web page `hmz web` serves, together with every view and dialog
drawn in it.

**3.2.2** **Local** is the daemon of this machine as the page names it. Local is always present on
the page. Where hmz runs in WSL, Local's host is the WSL distribution, shown as `<distro> (WSL)`.

**3.2.3** An **SSH daemon** is the daemon of another machine that the user has added to the page,
and that the page reaches over ssh as Section 3.8 of [DAEMON] specifies.

**3.2.4** The **daemon shown** is the daemon whose workspaces, epics, flows and settings the page
draws at a given moment.

**3.2.5** The **daemon bar** is the area at the foot of the sidebar that names the daemon shown.

**3.2.6** A **view** is what the page draws beside the sidebar: a new epic, an epic, a session, a
log, an Exomyth, or the flows. A **dialog** is what the page draws over a view: search, download, or
settings.

**3.2.7** An **address** is the part of the page's URL that names one view or dialog, of one daemon.

**3.2.8** A **notice** is a record that one epic on one machine ended, asked a person a question, or
waits for what to say next, as Section 3.15 specifies. A **notification** is a notice as the page
presents it to the user, with the daemon it came from and whether the user has read it.

**3.2.9** The **Exomyth** of an epic is the page's view of that epic's timeline and flame graph.

**3.2.10** A **theme** is a set of colours and pictures the page is drawn in. A **pair** is a light
theme and a dark theme kept together under one name. A **preset** is a pair that comes with hmz.

**3.2.11** **App settings** are the settings pages that belong to the page and to Local alone.
**Daemon settings** are the settings pages that each daemon keeps for itself.

**3.2.12** A **flowverse** is an index of installable flows, as Section 3 of [PYTHON] defines it.

### 3.3. Reaching the page

**3.3.1** `hmz web` MUST print the address of the page once it listens, and MUST open a browser on
that address unless the user asked it not to or this machine has no desktop, as [CLI] specifies.

**3.3.2** The page MUST be reachable only from this machine, and only by a browser that opened the
printed address, as Section 4 specifies.

**3.3.3** A browser that has not opened the printed address of the running `hmz web` MUST be shown
`This browser is not let in.` in place of every view, with the instruction to open the address `hmz
web` printed.

**3.3.4** The page MUST serve every workspace of the daemon shown, wherever `hmz web` was started.

**3.3.5** The page MUST offer the workspace `hmz web` was started in first wherever it offers a
workspace for a new epic.

**3.3.6** The page MUST NOT show a secret: an account MUST be shown by its harness, its name, its
way in and the names of the variables it sets, and never by a value.

**3.3.7** The page MUST NOT show a URL with credentials signed into it; it MUST show such a URL with
the credentials removed.

**3.3.8** Stopping `hmz web`, or closing the page, MUST NOT stop any epic.

### 3.4. Layout and navigation

#### 3.4.1. Layout

**3.4.1.1** The page MUST consist of a sidebar and, beside it, the current view.

**3.4.1.2** The sidebar MUST show, from top to bottom: the Humanize mark, the notification bell, a
control that hides the sidebar, the entries `New epic`, `Search epics` and `Flows`, the workspaces
of the daemon shown as Section 3.5 specifies, and the daemon bar.

**3.4.1.3** The `Flows` entry MUST show how many installed flows have a newer release, where at
least one has.

**3.4.1.4** On a screen as narrow as a phone's, the sidebar MUST be a drawer opened by a button, and
every view MUST be usable without horizontal scrolling of the page.

**3.4.1.5** The page title MUST name the machine of the daemon shown.

#### 3.4.2. Addresses

**3.4.2.1** Every view and every dialog MUST have an address that the user can keep and open again,
and opening that address MUST draw the same view or dialog.

**3.4.2.2** Every address MUST name the daemon it belongs to; an address that names no daemon MUST
belong to Local.

**3.4.2.3** Every link the page draws MUST keep the daemon of the address the page is on.

**3.4.2.4** Opening an address of another daemon MUST draw the sidebar and the view again, of that
daemon, and MUST stop drawing anything of the previous daemon.

**3.4.2.5** An address of an epic's log of every session MUST open that epic.

> Informative: the address forms are listed in Section 4.

#### 3.4.3. Keyboard

**3.4.3.1** Cmd+K, or Ctrl+K, MUST open `Search epics`.

**3.4.3.2** Cmd+Shift+O, or Ctrl+Shift+O, MUST open a new epic.

**3.4.3.3** Cmd+., or Ctrl+., MUST hide or show the sidebar.

**3.4.3.4** Escape MUST close the dialog that is open, and MUST close the menu or picker that is
open.

**3.4.3.5** In every box that sends text, Enter MUST send the text and Shift+Enter MUST start a new
line; Enter MUST NOT send while an input method is composing.

**3.4.3.6** Every control on the page MUST be reachable and operable by keyboard.

#### 3.4.4. Menus, labels and text

**3.4.4.1** A right click on a thing the page draws MUST open a menu of the page's own listing what
the user can do to that thing.

**3.4.4.2** A right click MUST open the browser's own menu, in place of the page's, only where there
is text to read or to write under it.

**3.4.4.3** The page MUST offer such a menu on at least: a workspace in the sidebar, an epic, an
agent, a session, a node of an epic's graph, a flow, a flowverse, a search result, and a line of a
transcript; and between the epics of the sidebar, where it MUST offer `Import`.

**3.4.4.4** The text that names the page's own parts MUST NOT be selectable as text.

**3.4.4.5** Every label the page draws -- a button, a tab, a menu item, a heading, a field label --
MUST be a word or a short phrase, and MUST NOT be a sentence.

**3.4.4.6** The page MUST call one execution of a flow an epic, and MUST NOT call it a run.

**3.4.4.7** Wherever the page shortens a text -- a path above all -- it MUST show the whole text on
hover, without delay.

**3.4.4.8** The page MUST offer to copy every path, link, task and identifier that it shows in a
menu.

**3.4.4.9** The page MUST say every refusal and every failure where it happened, in one sentence,
and MUST NOT hide it.

**3.4.4.10** The page MUST NOT draw over what the user is typing while what the user is typing about
still stands.

#### 3.4.5. Paths

**3.4.5.1** Every field that takes a path on this machine MUST offer a browser of directories,
opened from a button beside the field, that lists one directory at a time and lets the user choose a
directory, or a file where a file is wanted.

**3.4.5.2** Every field that takes a path MUST also accept a typed path, and MUST complete it as it
is typed.

**3.4.5.3** The page MUST NOT accept a path that is not a directory as a workspace.

### 3.5. Workspaces and the epics list

**3.5.1** The sidebar MUST show every workspace of the daemon shown as a folder: each workspace an
epic ran in, each workspace written down in the settings, and each workspace the user opened by its
path.

**3.5.2** A workspace the user opens by its path MUST be written down in the settings, and MUST stay
in the sidebar from then on.

**3.5.3** The sidebar MUST order the workspaces with those that have an epic going first, then by
their latest epic, newest first.

**3.5.4** Each folder MUST list its epics newest first, and MUST say `No epics` where it has none.

**3.5.5** The user MUST be able to fold a folder away and open it again; the page MUST remember
which folders are folded in this browser.

**3.5.6** Each folder MUST offer `+`, which opens a new epic in that workspace.

**3.5.7** The menu of a folder MUST offer: a new epic there, its flows, searching it, copying its
path, folding or opening it, its workspace settings, its usage, and, where no epic ran there,
forgetting it.

**3.5.8** Each epic in the sidebar MUST show a mark of its state, its task's first line, and either
`live`, where a host is going with it, or how long ago it began; the header of its own page MUST
show the same mark. The mark MUST be the first of these that holds:

1. `asking`, while its host waits on a question to a person that this browser has not seen;
2. `waiting`, while its host waits on a question and this browser has seen every one, for an epic
   other than a chat;
3. `stopping`, while its host is stopping it;
4. `running`, while it is going;
5. `done`, `failed` (failed, refused or crashed) or `stopped` (stopped, or its budget spent), as it
   ended;
6. `unfinished`, where its process went before it ended.

**3.5.9** The `asking` mark MUST blink, and every other mark MUST NOT blink. The page MUST treat a
question as seen once, while the question waits, the page of its epic, `#/epics/<name>`, or of its
host, `#/live?workspace=…&slot=…`, is shown, visible and focused; the page MUST remember in this
browser which questions were seen.

**3.5.10** An epic that another process is going with, outside any host, MUST be marked as going and
MUST NOT be marked `live`. A chat MUST be marked only `running` while a turn is open, `asking`,
`failed`, or otherwise `stopped`, and MUST NOT be marked `live`. A chat that folds away while this
browser has not seen what it last waited on MUST stay `asking` until that is seen, and the page MUST
remember in this browser what each chat last waited on until a turn of it opens.

**3.5.11** An epic other than a chat MUST be expandable into its agents, and each agent into the
sessions it opened; a chat MUST NOT be expandable. The page MUST remember in this browser which
epics are expanded.

**3.5.12** The menu of an epic MUST offer: open it, its Exomyth (not for a chat), resume it where it
can be resumed, a new epic like it, copying its link, its task and its name, exporting it once it is
no longer going, uploading it, and stopping it while a host is going with it (not for a chat).

**3.5.13** The sidebar MUST list a bounded number of epics at first and MUST offer `Show more` while
more exist.

**3.5.14** The sidebar MUST show the epics of the daemon shown as they change, without the user
asking.

### 3.6. An epic

#### 3.6.1. Common rules

**3.6.1.1** An epic MUST be drawn from what its host tells the page while it is going, and from what
was written down once it has ended, as Section 3 of [CORE] specifies.

**3.6.1.2** The page MUST name every agent by its own name: its node, its sessions `<agent>/<n>`,
its log, its address and what is said to it. The role the agent fills MUST be shown only after the
name.

**3.6.1.3** The page MUST name a person by the role the person answers.

**3.6.1.4** While an epic goes, the page MUST offer every action a frontend can take on it, as
Section 3.6 of [DAEMON] lists them.

#### 3.6.2. Graph and list

**3.6.2.1** An epic other than a chat MUST open as a graph: one node per agent, in a frame for the
flow it worked in, each saying what it runs, whether it is working or idle and for how long, and its
tokens; one node per person, drawn apart from agents; one arrow for each direction in which the epic
handed over from one agent to another, with how many times; the last handover and the working agent
marked.

**3.6.2.2** Each node MUST show one lane per session the agent opened, with a mark for each turn
over the epic's time, and MUST mark a turn still open.

**3.6.2.3** The user MUST be able to move the graph by dragging anywhere on it, to zoom it by a
pinch or a wheel about the pointer, and to bring it back to the middle with `Recenter`.

**3.6.2.4** The user MUST be able to switch the graph to a list of the agents, the working agents
first; the page MUST remember the choice in this browser.

**3.6.2.5** Choosing an agent MUST mark it on the graph and give it its own address.

#### 3.6.3. The panel

**3.6.3.1** Beside the graph, the page MUST offer a panel that the user can hide and show, with the
tabs `Epic`, `Aside`, `Board` where the epic has a board, and `People` where its flow has a person.

**3.6.3.2** `Epic` MUST show: how long the epic has gone, what it has spent and how fast, one meter
for each limit of its budget, its task, who handed to whom, its spending by model and by kind of
token, each session's environment and where its harness went, the frontends reading it, the flows
going or that it called, how it was set up, and where it is written down.

**3.6.3.3** The spending MUST NOT be summed over kinds of token into one figure, and a figure that
is only a lower bound MUST be marked as one.

**3.6.3.4** `Aside` MUST let the user ask a side question as Section 9 of [CORE] specifies: of The
Epic, or of one session of the epic. `Aside` MUST offer this also for an epic its host no longer
holds and for that epic's sessions, and The Epic MUST then be told that epic, as Section 4.9.3.3
specifies.

**3.6.3.5** `Aside` MUST hold several side conversations, as Section 9.8 of [CORE] states, each
picking whom it asks at its start with the control of Section 9.8 of [CORE] -- `The Epic`, then the
epic's agents, each opening its sessions -- above the box its question is typed in, and MUST NOT
offer a choice of any agent.

**3.6.3.6** `Aside` MUST keep each side conversation, the side questions asked in it and their
answers for the page opened again, MUST show while each is answering and whom The Epic asks on the
way, MUST let the user close each, and MUST say that side questions never reach the epic.

**3.6.3.7** `Board` MUST let the user edit, remove and add lines of the epic's board, and MUST NOT
offer to change a line the flow owns.

**3.6.3.8** `People` MUST, for each person the flow has, let the user claim the role for this
browser, take it over from another frontend, release it, and set it away or back.

#### 3.6.4. Steering an epic that is going

**3.6.4.1** Under the graph, while the epic waits on a person, the page MUST show each question with
its offered answers as buttons and a field for an answer of the user's own.

**3.6.4.2** A question that another frontend holds MUST say whose it is.

**3.6.4.3** The page MUST offer a box that sends a line to the epic, to one agent, to one session or
to one person, as Section 3.6 of [DAEMON] specifies; a session MUST be marked as working while it
has a turn open.

**3.6.4.4** The page MUST offer `Stop`, which asks for confirmation and then stops the epic for
every frontend; while the epic unwinds, the page MUST offer to force it, which closes every session
under its open turn.

#### 3.6.5. Sessions and logs

**3.6.5.1** A session MUST open as its transcript, drawn as the terminal interface draws it.

**3.6.5.2** A line typed under a session MUST go into that session, or MUST answer what that
session's open turn asks.

**3.6.5.3** The page MUST offer one log per agent, across its sessions, and one log per person, of
what the person was asked and answered; a line typed under one MUST go to whose it is.

**3.6.5.4** The page MUST NOT offer a log of every session at once.

#### 3.6.6. A chat

**3.6.6.1** A chat MUST be drawn as its conversation alone, wherever it is opened, as Section 8 of
[CORE] specifies: the task and each line of the user's on one side, each answer of the agent's on
the other.

**3.6.6.2** The box under a chat MUST send the user's next turn between turns, and MUST answer what
the agent asks while a turn is open, with the offered answers as buttons at the end of the
conversation.

**3.6.6.3** The page MUST NOT draw what a chat waits for between turns as a question.

**3.6.6.4** The page MUST NOT offer, for a chat, a graph, its agents or sessions, its Exomyth, its
people, or a way to stop it.

**3.6.6.5** Each chat MUST be an epic of its own, beside every other chat and every flow of its
workspace; starting a chat or an epic MUST NOT end another.

**3.6.6.6** A chat that has folded away MUST be carried on, in the same epic, when the user says
something in it, with what was said before drawn above.

#### 3.6.7. An epic written down

**3.6.7.1** An epic that has ended MUST show how it was set up -- its agents, environments,
parameters and budget -- the tree of flows it called, its sessions, what it spent and how long it
took.

**3.6.7.2** The page MUST offer `Read turns`, which reads the epic's handovers and each session's
turns back out of the logs it kept.

**3.6.7.3** The page MUST offer `Export`, which downloads the epic as one archive, as Section 3 of
[CORE] specifies.

**3.6.7.4** The page MUST offer `Upload` on every epic, which backs it up at once to the targets it
was started with, else to the default targets, and MUST answer at once with the targets it was
queued for, without waiting for the push.

**3.6.7.5** The page MUST say, on hover of `Upload`, how the last backup of the epic to each target
went.

**3.6.7.6** The page MUST offer `Resume` only where the epic's flow can resume it, and MUST then
open a new epic set up as that epic was started, in that epic's workspace.

#### 3.6.8. Importing

**3.6.8.1** The page MUST let the user import an exported epic by picking the file, by dropping it
anywhere on the window, or by opening the import address that names its path on this machine; where
hmz runs in WSL, that path MAY be a Windows path, read as WSL names it.

**3.6.8.2** In a browser, the import address MUST import only once the user presses `Import`.

**3.6.8.3** An imported epic MUST be imported into the daemon shown, under the workspace it ran in,
and MUST then open on its Exomyth.

**3.6.8.4** An epic already present MUST be refused, naming it, and the page MUST offer `Open` to go
to it.

**3.6.8.5** An imported epic that cannot be resumed on this machine MUST say why, and the page MUST
NOT offer to resume it.

### 3.7. Exomyth

**3.7.1** The page MUST offer the Exomyth of every epic other than a chat, going or written down.

**3.7.2** The Exomyth MUST have a `Timeline` tab and a `Flame` tab.

**3.7.3** The timeline MUST draw each process of the epic's timeline -- each flow, each session, and
each program a profiled epic ran -- as a row of its tracks under a ruler of time, each process under
the process that started it, and MUST NOT draw an arrow between processes.

**3.7.4** The user MUST be able to fold and open each process, and to fold or open all of them with
`Collapse` and `Expand`.

**3.7.5** The timeline MUST respond to these inputs:

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

**3.7.6** Pointing at a span MUST show it in brief.

**3.7.7** The flame graph MUST cover the stretch picked on the timeline, or the whole epic where
none is picked: each agent a stack, its sessions merged or apart as the user chooses, then its spans
as they nest.

**3.7.8** The flame graph MUST be weighable by `Time`, `Tokens in`, `Tokens out` or `Count`, MUST be
invertible bottom up, and MUST zoom to a frame on a click.

**3.7.9** Under the flame graph, the page MUST show every slice name summed in a table -- count,
total and own time, average, median, 95th percentile, longest, and tokens -- sortable by any column.

**3.7.10** The Exomyth MUST draw in the theme shown, and MUST stay responsive with an epic of fifty
thousand spans.

**3.7.11** The Exomyth of an epic still going MUST be read again while it is shown.

### 3.8. A new epic

**3.8.1** `New epic` MUST open on the workspace `hmz web` was started in, or on the workspace whose
`+` the user pressed, and on the flow that workspace last ran.

**3.8.2** The user MUST be able to pick any workspace the daemon shown serves, or to open one by its
path with completion as it is typed, or to pick `No workspace`.

**3.8.3** With `No workspace` picked, the form MUST offer the flows and the set-up of the
workspace `hmz web` was started in, and starting MUST start the epic in a new directory made for it
alone in the system's temporary directory.

**3.8.4** The user MUST be able to pick any flow on offer in that workspace.

**3.8.5** The form MUST offer a box for the task; Enter in it MUST start the epic.

**3.8.6** `Options` MUST hold what the flow is set up with, as that workspace last set it up: for
each agent role an agent, for each environment role an environment, the parameters, the budget, the
backup targets, `Profile flow` and `Profile environment`.

**3.8.7** The form MUST show beside `Options` what is set.

**3.8.8** An agent MUST be set up a part at a time, as Section 4 of [CORE] specifies: a harness
installed here that can fill the role; the account it runs as, this machine's own or one made, with
a way to make one; a model known runnable as that account, asking the harness where none is known
yet and accepting a typed model where it cannot say; and an effort that model takes.

**3.8.9** An environment MUST be set up a part at a time, as Section 7 of [CORE] specifies: its
backend, a runtime of that backend saved or made there, and its directory, completed as it is typed
where it is on this machine.

**3.8.10** Each agent and each environment set up on the form MUST come to what `-a` and `-e` spell,
as [CLI] specifies.

**3.8.11** The backup targets MUST default to the default targets until a choice is saved.

**3.8.12** `Save` MUST write down what the form holds for that workspace without starting an epic.

**3.8.13** Starting an epic MUST write down what the form holds for that workspace, as `Save` does.

**3.8.14** The form MUST refuse to save or start where a role has no agent, or where, for every flow
but chat, no limit bounds what the epic spends.

**3.8.15** Once the epic starts, the page MUST go to it; for a chat, to its conversation.

**3.8.16** Resuming an epic MUST open the form set up as that epic was started, in that epic's
workspace.

### 3.9. Flows

**3.9.1** `Flows` MUST have an `Installed` tab and a `Flowverses` tab.

**3.9.2** `Installed` MUST list each flow on offer in the workspace picked, with what it declares,
and, for one installed from a flowverse, its release and any newer release its flowverse lists.

**3.9.3** `Installed` MUST let the user start, update and uninstall a flow, and copy it whole into
the workspace.

**3.9.4** `Flowverses` MUST list every flowverse except the project's and the user's own, and MUST
show nothing of one until the user opens it or chooses to add one.

**3.9.5** A flowverse opened MUST show whether its index is fetched or written into, the flows it
lists, and every release of each, newest first, with prereleases and the installed release marked,
and MUST name every manifest it skipped.

**3.9.6** `Flowverses` MUST let the user install, switch to and uninstall a release, and add, fetch
and remove a flowverse; removing a flowverse MUST remove what was installed from it, and MUST ask
for confirmation first.

**3.9.7** The page MUST fetch every flowverse's index once as `hmz web` starts, without telling the
user.

**3.9.8** The page MUST refuse to install, update or uninstall a flow while an epic runs on the
machine.

### 3.10. Search

**3.10.1** `Search epics` MUST list every epic of the daemon shown, a page at a time, with its
workspace, flow, agents, what it spent, how long it took, how many sessions it opened, whether it
can be resumed and where it is written down.

**3.10.2** `Search epics` MUST let the user filter epics by how they went, by workspace, by flow and
by words of their task.

**3.10.3** `Search epics` MUST offer `Import`.

### 3.11. Settings

#### 3.11.1. Structure

**3.11.1.1** Settings MUST be a dialog with two groups of pages: `App` and `Daemon`.

**3.11.1.2** `App` MUST hold `Themes`, `Daemons` and `Notifications`, and MUST be the same whichever
daemon is shown.

**3.11.1.3** `Daemon` MUST hold `General`, `Accounts`, `Fallback`, `Runtimes`, `Backup`, `Workspace`
and `Usage`, each of the daemon picked above them.

**3.11.1.4** The daemon picked for the `Daemon` pages MUST be the daemon shown until the user picks
another, MUST be part of the address, and picking it MUST change nothing else on the page.

#### 3.11.2. Daemon pages

**3.11.2.1** `General` MUST let the user set whether a turn's working is shown, the agent that
answers The Epic (none until one is picked), and whether errors are reported, as Section 9 of [CORE]
and Section 12 of [CORE] specify.

**3.11.2.2** `Accounts` MUST list every account by its harness, way in and the names of the
variables it sets, and MUST let the user ask again what it runs, correct it, copy it to another
harness, remove it, and make one, as Section 5 of [CORE] specifies.

**3.11.2.3** Correcting an account MUST keep every value the user leaves blank, and MUST NOT show
any value.

**3.11.2.4** A way in that runs a harness's own sign-in MUST be shown as needing a terminal, and
MUST NOT be run from the page.

**3.11.2.5** The ways in through the local LiteLLM gateway MUST be grouped as the terminal interface
groups them, with the command that adds the `litellm` extra where it is missing.

**3.11.2.6** `Fallback` MUST let the user set, for each step, where a turn goes when a place cannot
take it and how it is tried again, and MUST let the user clear a step, as Section 6 of [CORE]
specifies.

**3.11.2.7** `Runtimes` MUST list every runtime, and MUST let the user add one from its backend's
fields, change it, check it, remove it after confirmation, and import hosts from the ssh config, as
Section 7 of [CORE] specifies.

**3.11.2.8** The runtime form MUST offer one field for each setting the backend's runtime takes,
including a docker or swarm runtime's `Name prefix`, each labelled with the setting's name in words.

**3.11.2.9** `Backup` MUST list every backup target with its repository, branch, policies and
whether it is a default, and MUST let the user add, edit and remove one, as Section 11 of [CORE]
specifies.

**3.11.2.10** `Backup` MUST offer `Download`, which lists every epic a target holds -- by machine
and then by workspace, those already present marked -- with the target picked where there is more
than one, and downloads the epic picked as an import does, opening it.

**3.11.2.11** `Workspace` MUST show what a workspace was last set up with, for any workspace the
daemon serves, and MUST let the user forget it; forgetting a workspace where no epic ran MUST remove
it from the sidebar.

**3.11.2.12** `Usage` MUST show what the epics spent by day and by flow, of every workspace or of
one, looking back 7, 30, 90 or 365 days.

**3.11.2.13** `General`, `Fallback`, `Runtimes` and `Backup` MUST each offer `Batch apply`, which
writes what that page holds to every daemon the user ticks, and MUST say of each daemon whether it
applied or why it refused.

**3.11.2.14** `Batch apply` MUST NOT remove anything a daemon already has but what the page replaces
whole, and MUST NOT carry a value that only a secret sets; the page MUST say where such a value is
left out.

**3.11.2.15** `Accounts`, `Workspace` and `Usage` MUST NOT offer `Batch apply`.

#### 3.11.3. App pages

**3.11.3.1** `Themes` MUST let the user choose a theme as Section 3.12 specifies.

**3.11.3.2** `Daemons` MUST list Local and every SSH daemon with its state, and MUST let the user
add, edit, connect and remove SSH daemons as Section 3.13 specifies.

**3.11.3.3** `Notifications` MUST let the user switch each kind of notification on and off --
`Done`, `Failed`, `Stopped`, `Questions` and `Chat turns` -- and switch system notifications on and
off.

**3.11.3.4** In a browser, `Notifications` MUST offer `Allow`, and the page MUST ask the browser for
leave to show system notifications only when the user presses it.

**3.11.3.5** The App settings MUST be kept in Local's settings alone, and MUST NOT be kept in any
other daemon's.

### 3.12. Themes

**3.12.1** The page MUST be drawn in Humanize's own typeface and in a theme.

**3.12.2** The page MUST offer the presets: Humanize's own, `Humanize Green`, `Temperate Gold`,
`Concordant Scarlet`, `Restrained Crimson`, `Critical Teal`, `Desirous Indigo`, `Peaceful Lilac`,
`Hateful Silver`, `Devoted Pink`, `Self-Negating Plum`, `Dominant Azure`, `Surviving Jade` and
`Lamenting Orchid`.

**3.12.3** Under `Auto`, the default, the page MUST follow the browser's light or dark preference
with a pair, or with one theme picked for light and one picked for dark.

**3.12.4** The user MUST be able to pick one theme to use whatever the browser's preference is.

**3.12.5** The user MUST be able to make a theme on `Light` or `Dark`, or a pair of the user's own,
to duplicate any theme or pair, and to edit any of the user's own.

**3.12.6** Editing a theme MUST let the user set its name, its base, each of its colours, and a
picture -- still or moving -- behind the page, the sidebar, the panel and dialogs, each to cover,
fit or tile its plane; a colour left blank MUST be the base's.

**3.12.7** The page MUST show a theme as it is changed, and MUST keep each change at once.

**3.12.8** The user MUST be able to export a theme, or a pair with both its themes, as a `.hmztheme`
file, and to import one, as Section 3.12.13 specifies the file.

**3.12.9** The page MUST keep themes in the browser, per browser.

**3.12.10** A theme MUST be chosen only in `Settings`, in a browser and in the desktop app alike.

**3.12.11** Where the system asks for reduced motion, the page MUST hold every moving picture still.

**3.12.12** The page MUST be usable in every theme it offers, including on a screen as narrow as a
phone's.

**3.12.13** A `.hmztheme` file MUST be one JSON object holding `"hmztheme": 1` and `name`, and
either `base` (`light` or `dark`) with `colors` and `images` for one theme, or `light` and `dark`,
each holding `colors` and `images`, for a pair. `colors` MUST be keyed by the page's colour tokens:
`paper`, `side`, `surface`, `raised`, `ink`, `ink-2`, `ink-3`, `on-ink`, `on-fill`, `link`,
`control`, `control-ink`, `primary`, `on-primary`, `field`, `edge`, `line`, `line-strong`, `hover`,
`scrim`, `green`, `cyan`, `cyan-ink`, `pink`, `pink-ink`, `lavender`, `gold`, `done`, `fail`, and
`lane-1` to `lane-6`. `images` MUST be keyed by plane -- `page`, `sidebar`, `panel`, `dialog` --
each holding `fit` (`cover`, `fit` or `tile`) and `data`, the picture as a data URL.

**3.12.14** Importing a `.hmztheme` file MUST keep what a theme can hold and MUST drop an unknown
token, a value that is not a colour, and a picture that is not an image.

### 3.13. Remote daemons

**3.13.1** The page MUST keep the SSH daemons in Local's settings, as Section 3 of [FILES]
specifies.

**3.13.2** Local MUST NOT be removable or renamable, and an SSH daemon MUST NOT be named `local`.

**3.13.3** The name of an SSH daemon MUST start with a letter or a digit and MUST consist of
letters, digits, `.`, `_` and `-`.

**3.13.4** The user MUST be able to add an SSH daemon a part at a time -- its name, host, user,
port, identity file, proxy jump and ssh options -- as an ssh runtime is set up.

**3.13.5** The user MUST be able to add a host of the ssh config under its `Host`, resolved through
the ssh config each time it is reached; hosts already added MUST NOT be offered. The page MUST NOT
write to the ssh config.

**3.13.6** Removing an SSH daemon MUST ask for confirmation, and MUST forget only how to reach it,
leaving everything on that machine as it is.

**3.13.7** The page MUST show one daemon at a time: the sidebar, a new epic, search, flows and the
`Daemon` settings pages MUST be of the daemon shown.

**3.13.8** The daemon bar MUST show the daemon shown, its host, whether it is reached, and how many
epics are going on it.

**3.13.9** A click on the daemon bar MUST open its menu: `Daemon`, which opens beside it every
daemon and its state; then `Settings` and `Usage`; and `Update` where a newer release of hmz is out.

**3.13.10** Picking a daemon in that menu MUST switch the page to it and, for an SSH daemon, MUST
reach it; the menu MUST offer `Connect` on an SSH daemon that failed and `Manage`, which opens
`Settings` › `Daemons`.

**3.13.11** The page MUST show each SSH daemon's state as one of `idle`, `connecting`, `installing`,
`up` and `failed`, with what was said last, as Section 3.8 of [DAEMON] specifies.

**3.13.12** An SSH daemon that is not `up` MUST be said to be unavailable where the page asks it
something, with its state.

**3.13.13** The page MUST NOT ask the user for a password or a host key; an SSH daemon that needs
one MUST fail.

**3.13.14** The `New daemon` form MUST offer two kinds, `SSH` and `P2P`, and under `SSH` two modes:
`SSH Config`, which offers only a dropdown of the hosts of the ssh config and writes the daemon
under its `Host` (Section 3.13.5), and `Custom`, which is the form of Section 3.13.4.

**3.13.15** `Custom` MUST let the user import a host of the ssh config into its form, filling its
fields from what the ssh config resolves for that host; the daemon MUST be written from those
fields, not under the `Host`.

**3.13.16** `P2P` MUST offer `EasyTier` alone, and MUST ask its name, its secret and its nodes, the
secret masked; a secret shorter than 16 bytes in UTF-8 MUST be refused with `A secret must be at
least 16 bytes.`

**3.13.17** The page MUST NOT be given a secret once written; editing a P2P daemon with its secret
left empty MUST keep the secret written.

**3.13.18** Editing a daemon MUST open the form in the kind and mode the daemon is in.

**3.13.19** Wherever the page names a remote daemon's kind, it MUST say `SSH` or `P2P`; Section
3.13.1 to Section 3.13.13 MUST hold of P2P daemons as of SSH daemons, but for the ssh config, a
password and a host key.

**3.13.20** `EasyTier` MUST offer the community's shared nodes (Section 3.8.5.11 of [DAEMON]) to be
checked, each with its name, whether it is up and its uptime, and MUST let the user type further
nodes; where that list cannot be read, the form MUST say so with the reason and take typed nodes
alone. A form in which no node is checked or typed MUST be refused with `An EasyTier daemon needs at
least one node.`

### 3.14. Release notice

**3.14.1** Where a newer release of hmz is out than the one serving the page, as Section 13 of
[CORE] specifies, the page MUST mark the daemon bar and MUST offer `Update` in its menu.

**3.14.2** `Update` MUST copy the command `hmz update` for the user to run in a terminal, and MUST
NOT update anything itself.

### 3.15. Notifications

#### 3.15.1. Notices

**3.15.1.1** `hmz web` MUST make a notice of each of these, for every epic of its own machine:

| Kind | When |
| --- | --- |
| `done` | An epic ended done; or a chat finished a turn |
| `failed` | An epic failed, crashed, ran out of budget or was refused |
| `stopped` | An epic other than a chat was stopped |
| `asked` | A flow asked a person a question |
| `listening` | A flow other than a chat waits for what to say next |

**3.15.1.2** `hmz web` MUST NOT make a notice of anything that already stood when it started.

**3.15.1.3** Watching for notices MUST NOT keep any host from going.

**3.15.1.4** Each notice MUST name its workspace, its epic, its flow and its task, and, where it is
a question, the role asking and the question.

#### 3.15.2. The notifications list

**3.15.2.1** The page served by Local MUST gather the notices of Local and of every SSH daemon while
it is `up` into one list of notifications, each naming its daemon and whether it is read.

**3.15.2.2** The list MUST keep the newest 200 notifications.

**3.15.2.3** A notice of a kind the user switched off MUST NOT be kept, counted or shown.

**3.15.2.4** The bell MUST show how many notifications are unread, whichever daemon is shown.

**3.15.2.5** A click on the bell MUST open the list, newest first; a click on a notification MUST
open its epic on its daemon; the user MUST be able to mark one or all read and to clear the list.

**3.15.2.6** Each new notification MUST also show as a card in a corner of the page that goes away
after a few seconds.

**3.15.2.7** The sidebar MUST mark each epic that has an unread notification, and each folded
workspace that holds such an epic.

**3.15.2.8** Every notification of the epic the page is on MUST be read while the user is on it, and
a new one of that epic MUST be read as it comes, without a card and without a system notification.

#### 3.15.3. System notifications

**3.15.3.1** While the page is hidden or not focused, and unless the user switched system
notifications off, the page MUST show each new notification as a system notification: in a browser
through the browser, once the browser allows it, and in the desktop app as Section 3.9 of [DESKTOP]
specifies.

**3.15.3.2** A click on a system notification MUST bring the page forward on the epic it is about.

## 4. HTTP Interface

### 4.1. Scope

Section 4 governs the HTTP server `hmz web` runs: where it listens, how a browser is admitted,
the form of every request and answer, every endpoint it serves under `/api/`, the event streams, and
the paths `/d/<name>/api/...` through which it serves the API of a **daemon** of another
**machine**. Every endpoint is listed in Section 4.8 to Section 4.15; a method and path not listed
there is not served.

Out of scope:

- The `hmz web` command line, its options and exit statuses: [CLI].
- The page itself, its views and what it draws: Section 3.
- The daemon protocol the server speaks to hosts: Section 4 of [DAEMON].
- The Python objects behind the answers: Section 4 of [PYTHON].
- The settings files the settings endpoints read and write: Section 3 of [FILES].
- Reaching the daemons of other machines over ssh, and installing `hmz` there: Section 3 of
  [DAEMON].
- What a notice is and when one is made: Section 10 of [CORE].

### 4.2. Terminology

**4.2.1** Every term of Section 2 of [CORE] MUST carry the meaning given there.

**4.2.2** **Server**: one process of `hmz web` answering HTTP.

**4.2.3** **Key**: the secret text the server makes when it starts and prints in its address.

**4.2.4** **Address**: the text `http://127.0.0.1:<port>/?key=<key>` the server prints.

**4.2.5** **Admission cookie**: the cookie named `hmz-<port>` whose value is the key.

**4.2.6** **API request**: a request whose path starts with `/api/`.

**4.2.7** **Write**: a `POST` request.

**4.2.8** **Refusal**: an answer whose status is 400 or above, whose body is a JSON object carrying
`error`, one sentence saying why.

**4.2.9** **Stream**: an answer of media type `text/event-stream` (Section 4.6).

**4.2.10** **Workspace parameter**: the field `workspace` of a request: the query parameter of a
`GET`, or the body field of a `POST`, naming a **workspace** by an absolute path, `~` expanded.

**4.2.11** **Slot parameter**: the field `slot` of a request, read as the workspace parameter is,
naming a host of the workspace as Section 4.2.6 of [DAEMON] defines a slot.

**4.2.12** **Daemon name**: `local` for this machine's daemon, or the name of an ssh daemon written
in the `daemons` list of Section 3 of [FILES].

**4.2.13** An epic name (Section 3.2.1 of [CORE]) MUST be written as Section 6.2.2 of [FILES]
states.

**4.2.14** **Epic row**: the JSON object Section 4.10.2 defines.

**4.2.15** **Notice**: the JSON object Section 4.15.1 defines.

### 4.3. Listening

**4.3.1** The server MUST listen on `127.0.0.1` and, where this machine has IPv6, on `::1`, on the
same port, and on no other address.

**4.3.2** Where the port asked for is `0`, the server MUST pick a port free on both loopback
addresses.

**4.3.3** The server MUST make a fresh key of 32 random bytes, URL-safe base64 encoded, each time it
starts, and MUST NOT write the key anywhere but in the address it prints and in the page of Section
4.3.4.

**4.3.4** Where the server opens a browser, it MUST open it on a file readable only by the current
user that forwards the browser to the address, and MUST NOT pass the key on any command line.

**4.3.5** The server MUST close a connection that sends nothing for 60 seconds.

### 4.4. Admission

**4.4.1** The server MUST check every request in the order of this section and MUST answer the first
check failed with the refusal stated.

**4.4.2** A request whose connection does not come from a loopback address MUST be refused 403,
`Open the address hmz web printed, on the machine it runs on.`

**4.4.3** The server MUST NOT check the `Host` the request names: a request that reaches the server
through a port forwarded or proxied from this machine MUST be admitted as any other is.

**4.4.4** `GET /?key=<key>` with the server's key MUST be answered 303 to `/` setting the cookie
`hmz-<port>=<key>; HttpOnly; SameSite=Strict; Path=/`; with any other key it MUST be refused 403,
`That key is not this server's: open the address hmz web printed.`

**4.4.5** An API request without the admission cookie MUST be refused 401, `Open the address hmz web
printed to let this browser in.`

**4.4.6** An API request MUST be refused 403, `Use this server's own page to make this request.`,
where it carries `Sec-Fetch-Site` with a value other than `same-origin` or `none`, or carries no
`Sec-Fetch-Site` and an `Origin` whose host and port differ from its `Host`.

**4.4.7** A write MUST be refused 403, `Use this server's own page to make this request.`, unless it
carries `Sec-Fetch-Site: same-origin`, or carries no `Sec-Fetch-Site` and an `Origin` of scheme
`http` or `https` whose host and port equal its `Host`.

**4.4.8** A request outside `/api/` and `/d/` whose method is not `GET` MUST be refused 405, `Only
the page's own files are here.`

**4.4.9** The page's own files MUST be served without the admission cookie.

### 4.5. Requests and answers

#### 4.5.1. Request bodies

**4.5.1.1** A write MUST send a JSON object with `Content-Type: application/json`, `{}` where it
sends nothing, except where Section 4.10.6 permits a file.

**4.5.1.2** A write of any other `Content-Type` MUST be refused 415, `Send JSON.`

**4.5.1.3** A write whose `Content-Length` is not a whole number of zero or more MUST be refused
411, `Say how long what is sent is.`

**4.5.1.4** A JSON body over 1 MiB, or a file over 2 GiB, MUST be refused 413, `That is more than a
request here may send.`

**4.5.1.5** A body that is not JSON MUST be refused 400, `Send JSON.`, and JSON that is not an
object 400, `Send a JSON object.`

**4.5.1.6** A query parameter given twice MUST be read as its last value.

#### 4.5.2. Routing

**4.5.2.1** An API request whose path matches no endpoint MUST be refused 404, and one whose path
matches an endpoint of the other method 405, both `There is nothing here by that name.`

**4.5.2.2** A path segment written `{name}` in this document MUST match one or more characters other
than `/`.

#### 4.5.3. Answers

**4.5.3.1** Every answer MUST carry `X-Content-Type-Options: nosniff`, `Referrer-Policy:
no-referrer` and `X-Frame-Options: DENY`.

**4.5.3.2** A JSON answer MUST be `application/json; charset=utf-8`, encoded without escaping
non-ASCII characters, with `Cache-Control: no-cache` and a weak `ETag`; a `GET` carrying
`If-None-Match` equal to that tag MUST be answered 304 without a body.

**4.5.3.3** An endpoint this document says answers `201` MUST answer 201 Created with its JSON;
every other successful JSON answer MUST be 200.

**4.5.3.4** A download MUST be answered 200 with `Content-Disposition: attachment;
filename*=UTF-8''<name>`, `Cache-Control: no-store`, and the file's length.

**4.5.3.5** A refusal MUST carry `{"error": "<sentence>"}` and any further fields its endpoint
states.

**4.5.3.6** A failure an endpoint does not anticipate MUST be refused 500, `Something went wrong
here: <why>`, and its traceback written to the server's standard error.

**4.5.3.7** After refusing a write, the server MUST close the connection.

#### 4.5.4. The page's files

**4.5.4.1** `GET /` MUST serve `index.html`, and `GET /<path>` the file of that path among the
page's files, with the media type of its extension (`.html`, `.js`, `.css`, `.svg`, `.json`).

**4.5.4.2** A path whose components are not each one or more letters, digits, `_` or `-`, whose last
component lacks one extension of lowercase letters or digits, or that is longer than 200 characters,
MUST be refused 404, as MUST a path naming no file.

**4.5.4.3** An HTML file MUST be served with `Content-Security-Policy: default-src 'self'; img-src
'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none';
base-uri 'none'; form-action 'self'`.

### 4.6. Streams

**4.6.1** A stream MUST be answered 200 with `Content-Type: text/event-stream; charset=utf-8` and
`Cache-Control: no-store`, MUST begin with `retry: 2000`, and MUST end where the connection ends.

**4.6.2** Each event MUST be written as an optional `id: <id>` line, an `event: <name>` line and one
`data: <JSON>` line, followed by a blank line.

**4.6.3** A stream MUST write the comment `: quiet` after 15 seconds without an event.

**4.6.4** A stream MUST resume after the event whose id the request names in `Last-Event-ID`, or,
where that header is absent, in the query parameter `last`.

**4.6.5** Every stream MUST end when the server stops.

### 4.7. Workspaces and slots

**4.7.1** A workspace parameter absent or `""` MUST mean the directory the server started in.

**4.7.2** A workspace parameter that is not absolute after expanding `~` MUST be refused 400, `Say
the workspace as a whole path, not <workspace>.`; one naming no directory MUST be refused 404,
`There is no directory <path>.`, except where an endpoint states it reads an epic of a workspace
since removed.

**4.7.3** A slot parameter absent or `""` MUST mean the workspace's own host; one that is not a slot
MUST be refused 400.

**4.7.4** The server MUST attach to a host, as a frontend named `browser` of kind `web`, only while
a page follows its stream or a request asks something of it, and MUST let go of it once neither has
happened for 60 seconds and its epics are idle, or its chat is between turns.

**4.7.5** Where a workspace's own host lets the server go while it is followed, the server MUST
attach to it again after 2 seconds; it MUST NOT attach again to a chat's host.

**4.7.6** The server MUST NOT attach to a host held by an older **hmz**, and MUST refuse the request
409 with the text of Section 4.12.3 of [DAEMON]; a host the server cannot reach MUST be refused 503,
`The epics of <workspace> could not be reached: <why>`.

### 4.8. The epics held

#### 4.8.1. `GET /api/held`

**4.8.1.1** `GET /api/held` MUST answer `machine` (this machine's host name up to its first `.`),
`wsl` (the WSL distribution the server runs in, as `WSL_DISTRO_NAME` names it, or `null` where it
names none), `here` (the directory the server started in), `version` (the server's `hmz` version),
`newer` (a newer release of `hmz`, as Section 13 of [CORE] defines it, or `""`) and `running`.

**4.8.1.2** `running` MUST hold, for every host of this machine whose epic is going or stopping, its
`run` snapshot (Section 4.9.3 of [DAEMON]) where the server follows it, else `state`, `run`, `flow`,
`epic`, `task` and, of a chat, `turn` from its status; each with `workspace`, `slot` and `asking`
(the questions it waits on, each `<run>:<question>`).

**4.8.1.3** `GET /api/held` MUST NOT start any host.

#### 4.8.2. `GET /api/held/stream`

**4.8.2.1** `GET /api/held/stream` MUST take the workspace and slot parameters and MUST answer a
stream of that host's epics, attaching to it, and starting the workspace's own host where none is.

**4.8.2.2** `GET /api/held/stream` for a chat's slot whose host has gone MUST be refused 409, `This
chat has folded away.`

**4.8.2.3** The stream's events MUST be those of the following table.

| Event | `id` | Data |
| --- | --- | --- |
| `hello` | none | `epoch` (the current attachment's id), `me` (the server's client id) |
| `record` | `<epoch>:<seq>` | One history record of Section 4.9.2 of [DAEMON] |
| `standing` | none | One snapshot of Section 4.9.3 of [DAEMON] |
| `figures` | none | What the epic has done and spent, Section 4.8.2.6 |
| `gone` | none | `why`: the host let the server go; the stream then ends |
| `again` | none | `{}`: the attachment changed or the server is stopping; the stream then ends |

**4.8.2.4** A stream MUST begin with `hello`, then every record kept after the one the request names
where that names the current epoch, else every record kept, then every snapshot, then each record
and changed snapshot as it comes.

**4.8.2.5** The server MUST keep at most the latest 20 000 records, and at most about 32 MiB of
them, per host.

**4.8.2.6** `figures` MUST be sent at most once a second and MUST hold `run`, `elapsed`, `lasting`,
`ended`, `agents` and `sessions` (each `name`, `turns`, `working`, `since`, `lasting`, `used`,
`tokens`, `under`), `handovers` (`[{from, to, count}]`), `latest`, `spending` (each `model`,
`tokens`, `rate`, `dollars`, `money`, `kinds`), `reckoning` (each `kind`, `tokens`, `whole`) and
`tally`.

#### 4.8.3. `POST /api/held/{do}`

**4.8.3.1** `{do}` MUST be one of `start`, `say`, `answer`, `stop`, `force`, `afk`, `claim`,
`release` and `board`; any other MUST be refused 404, `There is no <do> to ask of an epic.`

**4.8.3.2** The body MUST carry the workspace and slot parameters and exactly the fields the request
of that name takes in Section 4.8 of [DAEMON]; a further field MUST be refused 400, `<do> takes no
<fields>.`, and a field of another type 400, `<do> takes <field> as <type>.`

**4.8.3.3** The server MUST send the request down its attachment to the host, and MUST answer with
the host's answer: its fields, with `ok` `true`.

**4.8.3.4** A request the host refuses MUST be refused 409 with the host's sentence; one the host
cannot be asked MUST be refused 503, `The epics could not be asked: <why>`.

**4.8.3.5** `start` MUST first write what the flow is started with as the workspace's set-up of that
flow, as Section 4.11.4 does, and MUST answer with `slot`, the host it started on, and `workspace`,
the absolute path of the workspace it started in, beside the host's answer.

**4.8.3.6** `start` MUST take `scratch`, a bool, `false` where it is not sent; `true` MUST start
the epic in a new directory made for it alone in the system's temporary directory, in place of the
workspace parameter.

**4.8.3.7** `start` of the built-in `chat` flow without a slot parameter MUST start on a new chat
slot, starting its host; `start` on a chat slot MUST start that slot's host where none is.

### 4.9. Side questions

#### 4.9.1. General

**4.9.1.1** A side question MUST be asked as Section 9 of [CORE] defines it, through side
conversations the workspace's own host opens (Section 4.8.8 of [DAEMON]), and MUST NOT reach the
epic.

**4.9.1.2** The **btw** agent MUST be chosen as Section 9.7 of [CORE] states: the `btw` setting of
Section 3 of [FILES], and no other.

#### 4.9.2. `GET /api/btw`

**4.9.2.1** `GET /api/btw` MUST take the workspace parameter and `epic` (an epic name, `""` for the
epic in view on the workspace's own host).

**4.9.2.2** `GET /api/btw` MUST answer `asides` (each side conversation open about `epic`, in the
order opened) and `default` (the `btw` setting of Section 3 of [FILES], `""` for none, where a
question to the btw agent is refused as Section 9.5.9 of [CORE] states).

**4.9.2.3** Each of `asides` MUST say `aside` (its name, Section 4.9.3.1), `to` (whom it asks, as
Section 4.9.3.1), `question` (the question it is answering, `""` for none), `asked` (`[{to,
question}]`, each session the btw agent has asked on the way to that answer so far) and `said` (each
side question answered in it, oldest first, as Section 4.9.3 answers it, the latest 200).

**4.9.2.4** `GET /api/btw` MUST NOT attach to any host; where the server follows no host of the
workspace, `asides` MUST be `[]`.

#### 4.9.3. `POST /api/btw`

**4.9.3.1** `POST /api/btw` MUST take the workspace parameter, `question` (text, required), `aside`
(text, required: the side conversation, named by the page), `to` (`""` for the btw agent, or
`<agent>/<n>`) and `epic` (the epic it is about, `""` for none).

**4.9.3.2** The first question to an `aside` MUST open a side conversation on `to`, about `epic`,
and every later question to it MUST go on in that side conversation, of that `to` and `epic`
whatever the question sends, until it is left.

**4.9.3.3** Where `epic` names an epic the host (Section 3.2.1 of [DAEMON]) no longer holds, or
`epic` and `to` a session it no longer holds, the server MUST tell the side conversation that epic
rather than the epic going, and MUST carry each of its sessions asked on from where that epic kept
it; a session that epic did not open, or whose agent it did not write, MUST be refused 404.

**4.9.3.4** `POST /api/btw` MUST answer `aside`, `to`, `question`, `answer`, and `asked` (`[{to,
question}]`, each session the btw agent asked on the way to its answer).

**4.9.3.5** A question to a side conversation still answering MUST be refused 409, `btw is still
answering the last question asked of it.`; a question closed by a new epic starting 409, `A new epic
started, which closed what was asked.`; an empty answer 502, `The agent returned no answer.`

#### 4.9.4. `POST /api/btw/leave`

**4.9.4.1** `POST /api/btw/leave` MUST take the workspace parameter and `aside` (a side
conversation, or absent for every one), MUST close the side conversations named, and MUST answer
`{"ok": true}`.

**4.9.4.2** An `aside` that is not text MUST be refused 400.

**4.9.4.3** A side conversation about the epic going on a host MUST be closed when another epic
starts on that host, and one about an epic the host no longer holds MUST NOT be closed by that.

### 4.10. Epics written down

#### 4.10.1. `GET /api/runs`

**4.10.1.1** `GET /api/runs` MUST take `workspace` (only that workspace's epics; every workspace's
where absent), `status` (an ending of Section 3 of [CORE], `running` or `unfinished`), `flow`, `q`
(text found in the task, flow or epic name), `offset` (default `0`) and `limit` (default `50`, at
most `200`).

**4.10.1.2** `GET /api/runs` MUST answer `runs` (epic rows, newest first), `total`, `offset`,
`limit`, `counts` (`{ending: n}` over every epic) and `flows` (every flow, sorted); `offset` and
`limit` that are not whole numbers MUST be refused 400.

#### 4.10.2. Epic rows

**4.10.2.1** An epic row MUST hold `name`, `workspace`, `flow`, `task` (its first line, cut at 240
characters with `…`), `began`, `ended`, `how` (its ending, `running` while going, `unfinished` where
its process went before it ended; of a chat, as Section 8.5 of [CORE] says it), `agents` (`[{name,
role, runs}]`), `sessions` (a count), `resumable`, `spent`, `held` (whether a host is going with
it), `slot` (that host's), `asking` (the questions that host waits on, each `<run>:<question>`, `[]`
where none waits or no host is going with it), `backup` (the targets it was started with) and
`backed` (`{target: {at, ok, error, why}}`).

#### 4.10.3. `GET /api/runs/{name}`

**4.10.3.1** `GET /api/runs/{name}` MUST answer the epic row of the epic, of whichever workspace,
with `at`, the whole `task`, `ref`, `agents` (each `name`, `role`, `runs`, `backend`, `model`,
`effort`, `provider`),
`sessions` (each `agent`, `backend`, `provider`, `ident`, `name`, `at`, `flow`, `parent`,
`harness`), `envs`, `used`, `params`, `budget`, `picked_up`, `earlier` (of a chat carried on, how
many of its sessions it opened before it last was), `profile_flow`, `profile_environment`,
`picks_up`, `foreign` and `calls` (its tree of flow calls, each `flow`, `task`, `began`, `ended`,
`how`, `calls`).

**4.10.3.2** A `{name}` that names no epic MUST be refused 404, `There is no epic <name>.`, on `GET
/api/runs/{name}` and on every endpoint under `/api/runs/{name}`.

#### 4.10.4. Traces and timelines

**4.10.4.1** `GET /api/runs/{name}/trace` MUST answer `sessions`, as `Epics.transcripts` of Section
4.12.15 of [PYTHON] returns them.

**4.10.4.2** `GET /api/runs/{name}/timeline` MUST answer the epic's Exomyth timeline as Section 10
of [CORE] defines it, laid out afresh on every request while the epic is going.

**4.10.4.3** `GET /api/runs/{name}/timeline/span/{id}` MUST take `layout` and answer one span of the
last timeline laid out of the epic, whole; an id it lacks MUST be refused 404, `Epic <name> has no
span <id>.`, and a `layout` other than that timeline's 409, `Epic <name> has been laid out again;
read it again.`

**4.10.4.4** `GET /api/runs/{name}/bundle` MUST answer the epic's `.hmzepic` (Section 4.12.17 of
[PYTHON]) as a download of type `application/vnd.hmz.epic+gzip`.

#### 4.10.5. `POST /api/runs/{name}/backup`

**4.10.5.1** `POST /api/runs/{name}/backup` MUST take `to` (a list of target names, or absent) and
MUST back the epic up as `Backups.push` of Section 4.13.2 of [PYTHON] does, answering `queued` at
once without waiting for the push.

**4.10.5.2** A `to` that is not a list of text, or names no target, MUST be refused 400; where there
is no target at all the request MUST be refused 409, `There is no backup target: add one in
Settings.`

#### 4.10.6. `POST /api/runs/import`

**4.10.6.1** `POST /api/runs/import` MUST take either a body of `Content-Type`
`application/vnd.hmz.epic+gzip` or `application/octet-stream`, the archive's bytes, with
`X-Hmz-Filename` its file name percent-encoded; or JSON `{"path": "<absolute path of a .hmzepic on
this machine>"}`.

**4.10.6.2** `POST /api/runs/import` MUST import the archive as `Epics.imported` of Section 4.12.18
of [PYTHON] does and answer 201 with `name`, `workspace`, `resumable` and `why`.

**4.10.6.3** A file sent MUST be kept on this machine only until the request is answered.

**4.10.6.4** A missing or unsafe `X-Hmz-Filename` MUST be refused 400; a `path` that is not absolute
400, `Say path as a whole path on this machine.`; an archive that cannot be imported 400 with the
sentence of the error `Epics.imported` raises (Section 4.12.19 of [PYTHON]); and an epic already
present 409 with that error's sentence and `name`, that epic's name.

**4.10.6.5** Where the server runs in WSL, a `path` that is a Windows path (`C:\…`, `\\wsl$\…`,
`\\wsl.localhost\…`) MUST be read as `wslpath -u` translates it, before the check of Section
4.10.6.4 that `path` is absolute.

#### 4.10.7. Backup targets

**4.10.7.1** `GET /api/backups/{target}/epics` MUST fetch the target afresh and answer `epics`,
newest first, each `key` (`<machine>/<workspace>/<epic>`), `machine`, `workspace`, `epic`, `flow`,
`task`, `began`, `ended`, `how`, `head`, and `here` (whether this machine holds that epic).

**4.10.7.2** `POST /api/backups/{target}/pull` MUST take `key`, download that epic as
`Backups.pulled` of Section 4.13.7 of [PYTHON] does, and answer `name`.

**4.10.7.3** `GET /api/backups/{target}/epics` and `POST /api/backups/{target}/pull` MUST each
refuse 400 for an unknown target or what `Backups` raises `ValueError` for, and 502 where the
repository cannot be reached; a refusal MUST NOT carry credentials of a URL.

#### 4.10.8. `GET /api/usage`

**4.10.8.1** `GET /api/usage` MUST take `days` (1 to 365, default 30) and `workspace` (only its
epics), and MUST answer `days_back`, `days` (per UTC day, oldest first), `flows` (costliest first),
`ended` (`{ending: n}`) and `whole`, each but `ended` holding `runs`, `cost`, `output_tokens`,
`seconds`, `money`, `tokens` and `worked`.

**4.10.8.2** A `days` that is not a whole number MUST be refused 400.

### 4.11. Flows

#### 4.11.1. `GET /api/flows`

**4.11.1.1** `GET /api/flows` MUST take the workspace parameter and answer `flows` (`[{whose, name,
about}]`), `flow` (the flow that workspace opens on) and `running` (`[{ref, name, depth, since,
task}]`).

#### 4.11.2. `GET /api/flow`

**4.11.2.1** `GET /api/flow` MUST take `name` and the workspace parameter, and MUST answer what the
flow declares: `name`, `ref`, `description`, `resumable`, `resumes`, `agents` (each `name`,
`required`, `auto`, `harness`, `permission`, `skills`, and `clis`: the CLIs installed here that can
fill it), `envs` (each `name`, `required`, `auto`, `cpu`, `memory`, `gpu`, `image`), `params` (its
JSON schema) and `remembered` (`agents`, `envs`, `params`, `budget`, `profile_flow`,
`profile_environment`, `backup`, as the workspace last set the flow up).

**4.11.2.2** A missing `name` MUST be refused 400; a name that is not one of `GET /api/flows` 404,
`<name> is not a flow on offer here.`; a flow that will not load 404.

**4.11.2.3** The server MUST NOT load a flow named by a path or a repository.

#### 4.11.3. `GET /api/backends`

**4.11.3.1** `GET /api/backends` MUST answer `clis` (`{cli: {accounts: [{name, models: [{name,
efforts}], asked}]}}` for each CLI installed, this machine's own sign-in first as `""`),
`installable` (`{cli: [{name, efforts}]}`) and `envs` (`Runtimes.kinds()` of Section 4.10.2 of
[PYTHON]).

#### 4.11.4. `POST /api/flows/setup`

**4.11.4.1** `POST /api/flows/setup` MUST take the workspace parameter, `flow`, and, as `start` of
Section 4.8.3 takes them, `agents`, `envs`, `params`, `budget`, `profile_flow`,
`profile_environment` and `backup`.

**4.11.4.2** `POST /api/flows/setup` MUST write what the workspace runs the flow with, as Section 3
of [FILES] defines it, and answer as `GET /api/flow` does.

**4.11.4.3** `POST /api/flows/setup` MUST be refused 404 for a flow not on offer or that will not
load; 400 for an agent that is not an agent spec, a role left without an agent, a flow other than
`chat` with no budget limit, and a `backup` naming an unknown target.

#### 4.11.5. Workspaces

**4.11.5.1** `GET /api/workspaces` MUST answer `here` and `workspaces`, each `path`, `name`, `epics`
(a count), `last` (when the latest began), `running`, `here` and `there` (whether the directory
exists): where the server started first, then those going, then those where epics ran, newest first,
then those only written in the settings.

**4.11.5.2** `POST /api/workspaces` MUST take `workspace`, write it in the settings, and answer
`kept` (its absolute path) beside what `GET /api/workspaces` answers.

**4.11.5.3** `POST /api/workspaces/forget` MUST take `workspace`, forget what it was set up with,
and answer as `GET /api/workspaces` does.

#### 4.11.6. Flowverses

**4.11.6.1** `GET /api/flowverses` MUST answer `verses` (each `name`, `url` without credentials,
`fetched`, `fixed`, `edited`, `installed`), `installed` (each `flow`, `verse`, `listed`, `version`,
`repo`, `ref`) and `updates` (each `flow`, `from`, `to`).

**4.11.6.2** `GET /api/flowverses/{name}` MUST answer `name`, `url`, `fetched`, `fixed`, `edited`,
`flows` (each `listed`, `flow` as `install` takes it, `installed`, and `releases` newest first, each
`version`, `description`, `prerelease`, `license`, `repo`, `dependencies`) and `skipped` (each `at`,
`why`); an unknown name MUST be refused 404, `There is no flowverse <name>.`

**4.11.6.3** `POST /api/flowverses` (`url`, `name`), `POST /api/flowverses/fetch` (`name`), `POST
/api/flowverses/remove` (`name`), `POST /api/flowverses/install` (`flow`, `version`) and `POST
/api/flowverses/uninstall` (`flow`) MUST do what `Flowverses.add`, `fetch`, `remove`, `install` and
`uninstall` of Section 4.8 of [PYTHON] do, and answer `said` (what was done, in words) beside what
`GET /api/flowverses` answers; what those raise MUST be refused 400.

**4.11.6.4** Install, uninstall and remove MUST be refused 409, `An epic is running: flows change
once none is.`, while an epic is going on this machine.

**4.11.6.5** `POST /api/flows/fork` MUST take `flow` and the workspace parameter, copy the flow as
`Flows.fork` of Section 4.7.7 of [PYTHON] does, and answer `said` and `at`; what that raises MUST be
refused 400.

### 4.12. Paths

**4.12.1** `GET /api/files` MUST take `at` (a directory, `~` expanded, the home directory where
absent), `files` (`1` to list files) and `hidden` (`1` to list names starting with `.`), and MUST
answer `at` (spelled from `~` where under the home directory), `whole`, `up` (the parent, `""` at
the root), `entries` (each `name`, `dir`, directories first, at most 500) and `more` (how many were
left out); a directory that cannot be read MUST be refused 404.

**4.12.2** `GET /api/paths` MUST take `typed` and answer `paths`: at most 50 directories the text
typed could become, sorted, spelled as typed, each ending in `/`, names starting with `.` only where
a `.` was typed.

### 4.13. Settings

#### 4.13.1. General settings

**4.13.1.1** `GET /api/settings` MUST take the workspace parameter, for a workspace that need not
exist, and answer `workspace`, `flow`, `btw`, `details`, `reports` (`null` where never answered),
`flows` (the flows set up there) and `backup` (`targets`, each `name`, `url` without credentials,
`branch`, `policies`, `every`; and `defaults`).

**4.13.1.2** `POST /api/settings` MUST take the workspace parameter and any of `btw` (text),
`details` (boolean), `reports` (boolean) and `backup` (`{targets, defaults}`, every target).

**4.13.1.3** `POST /api/settings` MUST write `btw`, `details` and `backup` as Section 3 of [FILES]
defines them.

**4.13.1.4** `POST /api/settings` MUST write `reports` as the key `enable_sentry` of Section 3 of
[FILES].

**4.13.1.5** `POST /api/settings` MUST answer as `GET /api/settings` does.

**4.13.1.6** A target whose `url` equals the credential-free URL `GET /api/settings` answered MUST
keep the URL written; a `url` still holding `***@` otherwise MUST be refused 400.

**4.13.1.7** Any other field, or a value of another type, MUST be refused 400 and nothing written.

**4.13.1.8** `POST /api/settings/forget` MUST take the workspace parameter, forget what that
workspace was set up with, and answer `forgot` (whether there was anything) beside what `GET
/api/settings` answers.

#### 4.13.2. Accounts

**4.13.2.1** `GET /api/accounts` MUST answer `gateway` (`"LiteLLM"`), `accounts` (each `cli`,
`name`, `way`, `sets` (the names of the variables it sets), `made`, `models`, `asked`, `serves`) and
`backends` (each `cli`, `ways`, each `name`, `about`, `group`, `terminal`, `asks` (each `env`,
`about`, `secret`, `fixed`); and `wants`).

**4.13.2.2** An answer of the server MUST NOT carry the value of any variable an account sets.

**4.13.2.3** `POST /api/accounts` MUST take `cli`, `name`, `way` and `answers` (`{variable:
value}`), and make the account; it MUST be refused 400 for an unknown way, a way whose `terminal` is
true, a variable left unanswered or an invalid name, and 409 for a name taken.

**4.13.2.4** `POST /api/accounts/correct` MUST take `cli`, `name` and `answers`, write the account
again keeping every variable not answered, and be refused 400 for a variable the way does not ask
and for a way whose `terminal` is true.

**4.13.2.5** `POST /api/accounts/remove` (`cli`, `name`), `POST /api/accounts/models` (`cli`,
`name`, `""` for this machine's own) and `POST /api/accounts/copy` (`cli`, `name`, `into`) MUST
remove the account, ask the CLI what it runs as that account, and copy the account to the CLI
`into`; an unknown account MUST be refused 404 and a CLI that will not answer 502.

**4.13.2.6** Every write of Section 4.13.2 MUST answer as `GET /api/accounts` does.

#### 4.13.3. Fallbacks

**4.13.3.1** `GET /api/fallbacks` MUST answer `steps` (each `spec`, `to`, `tries`, `policy`,
`timeout`), `policies`, `default` and `places`.

**4.13.3.2** `POST /api/fallbacks` MUST take `spec` (a place), `to` (places, in order), `tries`
(default `0`), `policy` (default `exponential-jitter`) and `timeout` (seconds, `0` for none), write
the step, and answer as `GET /api/fallbacks` does; a value `Fallbacks` of Section 4.11 of [PYTHON]
refuses MUST be refused 400.

**4.13.3.3** `POST /api/fallbacks/clear` MUST take `spec`, remove its step, and answer as `GET
/api/fallbacks` does; a place with no step MUST be refused 404.

#### 4.13.4. Runtimes

**4.13.4.1** `GET /api/runtimes` MUST answer `runtimes` (each as the runtime's `held()` of Section
4.20.6.1 of [PYTHON] gives it) and `blanks` (each backend's fields as a new runtime holds them).

**4.13.4.2** `POST /api/runtimes` MUST take `backend`, `name`, `fields` and `replace` (boolean), and
write the runtime; `backend` or `name` among `fields`, or an invalid runtime, MUST be refused 400.

**4.13.4.3** `POST /api/runtimes/remove` (`backend`, `name`) MUST remove the runtime, and `POST
/api/runtimes/check` (`backend`, `name`) MUST answer what `Runtimes.check` of Section 4.10.12 of
[PYTHON] returns, each field by name; an unknown runtime MUST be refused 404.

**4.13.4.4** `GET /api/runtimes/hosts` MUST answer `hosts`, each `alias`, `host`, `user`, `port`,
`identity_files`, `proxy_jump` and `saved`; an unreadable ssh config MUST be refused 503.

**4.13.4.5** `POST /api/runtimes/import` MUST take `names` (a list) and `update` (boolean), save an
ssh runtime per name, and answer as `GET /api/runtimes` does; an empty list or unknown host MUST be
refused 400.

**4.13.4.6** `POST /api/runtimes` and `POST /api/runtimes/remove` MUST answer as `GET /api/runtimes`
does.

### 4.14. Daemons

#### 4.14.1. The daemon list

**4.14.1.1** `GET /api/daemons` MUST answer `daemons`: first `local` (label `Local`, state `up`, the
server's version), then each daemon written, each `name`, `label`, `via` (`ssh` or `easytier`),
`state`, `detail` and `version`; an ssh daemon also `host`, `user`, `port`, `identity_file`,
`proxy_jump`, `options` (`[keyword, value]` pairs), `alias` and `config`, and an EasyTier daemon
`secret`, `true` where one is written, and `peers`.

**4.14.1.2** `POST /api/daemons` MUST take `name`, `fields` and `replace` (boolean), and write the
daemon as Section 4.14.3 of [PYTHON] does; a further field or an invalid daemon MUST be refused 400,
a name taken without `replace` 409, and a failed write 500.

**4.14.1.3** `POST /api/daemons/remove` MUST take `name`; `local` MUST be refused 400 and an unknown
name 404.

**4.14.1.4** `GET /api/daemons/hosts` MUST answer `hosts`, each `Host` of the ssh config not yet a
daemon (`alias`, `name`, `host`, `user`, `port`, `identity_files`, `proxy_jump`); an unreadable
config MUST be refused 503.

**4.14.1.5** `POST /api/daemons/import` MUST take `aliases`, add a daemon per alias, skipping those
present, and answer `added` beside what `GET /api/daemons` answers; an invalid list MUST be refused
400 and an alias the config lacks 404.

**4.14.1.6** `POST /api/daemons` and `POST /api/daemons/remove` MUST answer as `GET /api/daemons`
does.

**4.14.1.7** An answer of the server MUST NOT hold a daemon's secret; `POST /api/daemons` with
`replace` and `fields` of an EasyTier daemon without `secret` MUST keep the secret written.

**4.14.1.8** `GET /api/daemons/easytier/nodes` MUST answer `nodes`, the community's shared EasyTier
nodes (Section 3.8.5.11 of [DAEMON]), each `url`, `name`, `version`, `up` (boolean, or null where
unknown) and `uptime` (from 0 to 1 over 24 hours, or null where unknown); a list that cannot be read
MUST be refused 503, `The community nodes could not be read: <why>`.

#### 4.14.2. Reaching a daemon

**4.14.2.1** `GET /api/daemons/{name}/state` MUST answer `state` (`idle`, `connecting`,
`installing`, `up` or `failed`), `detail` and `version`; `local` MUST answer `up` at the server's
version; an unknown daemon MUST be refused 404, `There is no daemon by that name.`

**4.14.2.2** `POST /api/daemons/{name}/connect` MUST start reaching the daemon, or reach it again
where it failed, and answer as `GET /api/daemons/{name}/state` does; for `local` the server MUST
answer as `GET /api/daemons/{name}/state` does and reach nothing; the request MUST be refused 404
for an unknown daemon and 503 while the server is stopping.

#### 4.14.3. `/d/{name}/api/...`

**4.14.3.1** A request to `/d/local/api/<rest>` MUST be answered exactly as `/api/<rest>`.

**4.14.3.2** A daemon name of characters other than letters, digits, `.`, `_` and `-`, or a path not
continuing `/api/`, MUST be refused 404, `There is nothing here by that name.`

**4.14.3.3** A request to `/d/<name>/api/<rest>` for a remote daemon MUST be admitted as Section 4.4
states for API requests and writes, and MUST then be sent to that daemon's `hmz web` at
`/api/<rest>` with its query, admitted there with that server's own key, and answered with that
server's status, headers and body as they arrive, streams and file bodies included.

**4.14.3.4** The server MUST forward only the request headers `Accept`, `Content-Type`,
`Content-Length`, `If-None-Match`, `Last-Event-ID` and `X-Hmz-Filename`, and MUST NOT pass back
`Set-Cookie`, nor any header holding a line break.

**4.14.3.5** The server MUST NOT send the other server's key or cookie to any page.

**4.14.3.6** An unknown daemon MUST be refused 404; a daemon not up 503 with `state`, `detail` and
`version` beside `error`; and a daemon whose server does not answer 502, `The daemon did not
answer.`

**4.14.3.7** `/api/daemons...` and `/api/notifications...` MUST be asked of the server a page is
open on, never through `/d/`.

### 4.15. Notices and notifications

#### 4.15.1. Notices

**4.15.1.1** A notice MUST hold `id` (an integer greater than every earlier one, across restarts of
the server on this machine), `kind` (`done`, `failed`, `stopped`, `asked` or `listening`),
`workspace`, `slot`, `epic`, `flow`, `task`, `role`, `text` and `at` (Unix seconds), as Section 10
of [CORE] defines them.

**4.15.1.2** The server MUST work notices out of each host's status without attaching to any host.

**4.15.1.3** `GET /api/notices` MUST take `after` (an id, default `0`) and answer `notices` (those
kept after it, oldest first, the latest 200) and `last` (the newest id, `0` for none); an `after`
that is not a whole number MUST be refused 400, `Say after as a whole number.`

**4.15.1.4** `GET /api/notices/stream` MUST answer a stream of `notice` events, each `id` the
notice's id, from after the id the request names, or from now where it names none.

#### 4.15.2. Notifications

**4.15.2.1** A notification MUST be a notice of this machine or of an ssh daemon reached, with `id`
(text of an integer counted from 1 each time the server starts), `daemon` (a daemon name) and
`read`; the server MUST keep the latest 200, and MUST keep them only until it stops.

**4.15.2.2** The server MUST follow the `GET /api/notices/stream` of each ssh daemon while it is up,
from the last notice heard of it.

**4.15.2.3** A notice of a kind turned off in the settings of Section 3 of [FILES] MUST NOT be kept
nor sent; the server MUST read that setting afresh for every notice.

**4.15.2.4** `GET /api/notifications` MUST answer `items` (newest first) and `unread`.

**4.15.2.5** `GET /api/notifications/stream` MUST answer a stream of `notification` events, each
`id` its id, every one kept after the id named, every one kept where the id named exceeds every id
here, and from now where none is named.

**4.15.2.6** `POST /api/notifications/read` MUST take `ids` (a list) or `all` (`true`), mark them
read, and answer as `GET /api/notifications` does; any other body MUST be refused 400, `Say ids as a
list, or all as true.`

**4.15.2.7** `POST /api/notifications/clear` MUST forget every notification and answer as `GET
/api/notifications` does.

**4.15.2.8** `GET /api/notifications/settings` MUST answer `kinds` (`{done, failed, stopped, asked,
listening}`, each a boolean) and `system` (boolean), as Section 3 of [FILES] holds them.

**4.15.2.9** `POST /api/notifications/settings` MUST take any of `kinds` and `system`, write them,
and answer as `GET /api/notifications/settings` does; any other field, kind or type MUST be refused
400 and nothing written, and a failed write 409.

## 5. Security Considerations

This section summarises the security-relevant properties this document states. It adds no
requirement.

- **Where the server listens.** The server listens on the loopback addresses alone (Section 4.3.1)
  and refuses a connection that does not come from one (Section 4.4.2). It does not check the `Host`
  a request names, so whatever forwards or proxies a port to it from this machine is admitted as a
  local browser is (Section 4.4.3); what then guards the API is the key.
- **The key and the admission cookie.** The key is 32 random bytes made afresh at each start,
  appears only in the printed address and in a file readable only by the current user, and is never
  passed on a command line (Section 4.3.3 and Section 4.3.4). A browser exchanges it for an
  `HttpOnly`, `SameSite=Strict` cookie (Section 4.4.4), without which every API request is refused
  (Section 4.4.5). The page's own files are served without the cookie (Section 4.4.9). A page
  without the cookie shows no view (Section 3.3.3).
- **Origin checks.** An API request from another site is refused, and a write is accepted only where
  the browser states that it comes from the server's own page (Section 4.4.6 and Section 4.4.7).
  Writes are JSON alone, but for an imported archive, and bounded in size (Section 4.5.1). Every
  answer forbids framing and content sniffing, and the page's HTML carries a content security policy
  that admits only the server's own scripts, styles and connections (Section 4.5.3.1 and Section
  4.5.4.3).
- **Secrets.** The settings endpoints name the variables an account sets and never answer a value
  (Section 4.13.2.1 and Section 4.13.2.2); correcting an account keeps what is left blank (Section
  4.13.2.4). A backup target's or flowverse's URL is answered without its credentials, and a refusal
  carries none (Section 4.10.7.3, Section 4.11.6.1, Section 4.13.1.1 and Section 4.13.1.6). A P2P
  daemon's secret is answered only as whether one is written (Section 4.14.1.1 and Section
  4.14.1.7). The page follows the same rules (Section 3.3.6, Section 3.3.7, Section 3.11.2.3 and
  Section 3.13.17), and never asks for a password or a host key (Section 3.13.13).
- **Paths on this machine.** An admitted browser can list any directory the server's user can read
  and complete any path (Section 4.12), name any directory as a workspace (Section 4.7 and Section
  4.11.5), import an archive from any absolute path (Section 4.10.6), and start epics (Section
  4.8.3). Admission is therefore equivalent to acting as the user who runs `hmz web`. The page's own
  files are served only by names of a restricted form (Section 4.5.4.2), and a flow is never loaded
  from a path or a repository a request names (Section 4.11.2.3).
- **Other daemons.** A request through `/d/<name>/api/...` is admitted by the server the page is
  open on and then admitted to the remote server with that server's own key, which no page receives;
  only a fixed set of request headers is forwarded and `Set-Cookie` is never passed back (Section
  4.14.3.3 to Section 4.14.3.5). Whoever is admitted to one server thereby acts on every daemon it
  has reached.
- **Failures.** An unanticipated failure is answered with its reason in one sentence and its
  traceback goes to the server's standard error, not into the answer (Section 4.5.3.6).

## 6. References

### 6.1. Normative References

- **[RFC2119]** Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels", BCP 14, RFC
  2119, March 1997, <https://www.rfc-editor.org/info/rfc2119>.
- **[RFC8174]** Leiba, B., "Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words", BCP 14, RFC
  8174, May 2017, <https://www.rfc-editor.org/info/rfc8174>.
- **[CORE]** "The Humanize Protocol: Core Concepts and Functional Behaviour", [`core.md`](core.md).
- **[CLI]** "The Humanize Protocol: Command-Line Interface", [`cli.md`](cli.md).
- **[TUI]** "The Humanize Protocol: Terminal Interface", [`tui.md`](tui.md).
- **[DAEMON]** "The Humanize Protocol: Daemon", [`daemon.md`](daemon.md).
- **[DESKTOP]** "The Humanize Protocol: Desktop Application", [`desktop.md`](desktop.md).
- **[PYTHON]** "The Humanize Protocol: Python Interfaces", [`python.md`](python.md).
- **[FILES]** "The Humanize Protocol: Settings, Environment Variables and Files", [`files.md`](files.md).

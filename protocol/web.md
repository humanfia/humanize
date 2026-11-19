# The Humanize Protocol: Web Interface

## Abstract

This document specifies the web interface of hmz: the page a browser shows and what a user does on
it, and the server `hmz web` that serves the page, bridges it to the daemon of this machine and
opens for it the carriers to daemons of other machines.

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
  - [3.16. Ai-chan](#316-ai-chan)
  - [3.17. Environments](#317-environments)
- [4. The Server](#4-the-server)
  - [4.1. Scope](#41-scope)
  - [4.2. Terminology](#42-terminology)
  - [4.3. Listening](#43-listening)
  - [4.4. Admission](#44-admission)
  - [4.5. Answers and the page's files](#45-answers-and-the-pages-files)
  - [4.6. `/here`](#46-here)
  - [4.7. `/rpc`](#47-rpc)
  - [4.8. `/dial`](#48-dial)
  - [4.9. Pipe providers](#49-pipe-providers)
- [5. Security Considerations](#5-security-considerations)
- [6. References](#6-references)
  - [6.1. Normative References](#61-normative-references)

## 1. Introduction

This document specifies the web interface of hmz: the page a browser shows and what a user does on
it, and the server `hmz web` that serves the page, bridges it to the daemon of this machine and
opens for it the carriers to daemons of other machines. The page is a client of every daemon it
shows, over [WIRE], and calls the methods of Section 4 of [DAEMON].

This document is organised as follows:

- Section 3: The Page.
- Section 4: The Server.

## 2. Conventions and Terminology

The key words "MUST", "MUST NOT" and "MAY" in this document are to be interpreted as described in
BCP 14 [RFC2119] [RFC8174] when, and only when, they appear in all capitals, as shown here.

The conventions for numbering and citation, and every term of the shared glossary, are those of
Section 2 of [CORE].

## 3. The Page

### 3.1. Scope

Section 3 specifies the behaviour of the page that `hmz web` serves: how the user reaches it,
how it lays out the workspaces and epics of a daemon, how the user reads, steers, starts, imports
and backs up epics through it, how the user works in an epic's environments, its settings pages, how
it reaches the daemons of other machines, how it notifies the user, and the interaction rules it
follows. It specifies only what the user sees and
does on the page.

Out of scope:

- The command line of `hmz web` and its exit statuses: [CLI].
- The server, its bridge and its dialing: Section 4.
- Every method the page calls, its results and refusals: Section 4 of [DAEMON].
- The daemon, hosts, attaching and the lifetime of epics: Section 3 of [DAEMON] and Section 4 of
  [DAEMON].
- What a chat is and how it folds away: Section 8 of [CORE].
- What a side question is: Section 9 of [CORE].
- What Ai-chan is and does: Section 14 of [CORE].
- What an epic records, its figures and its timeline: Section 3 of [CORE] and Section 10 of [CORE].
- Backup targets and their policies: Section 11 of [CORE].
- Release checks and `hmz update`: Section 13 of [CORE].
- Agents, accounts, placements and environments: Section 4 of [CORE], Section 5 of [CORE], Section 6
  of [CORE] and Section 7 of [CORE].
- The terminal interface: [TUI].
- The app that shows the page in a window: Section 3 of [DESKTOP].
- The files the daemon's settings are kept in: Section 3 of [FILES] and Section 4 of [FILES].

### 3.2. Terminology

**3.2.1** The **page** is the single web page `hmz web` serves, together with every view and dialog
drawn in it.

**3.2.2** **Local** is, as the page names it, the daemon of the machine `hmz web` runs on, or, in
the desktop app, the daemon Section 3.5 of [DESKTOP] names. Local is present on the page wherever
there is one. Where the daemon runs in WSL, Local's host is the WSL distribution, shown as `<distro>
(WSL)`.

**3.2.3** A **remote daemon** is the daemon of another machine that the user has added to the page,
and that the page reaches over its routes as Section 3.8 of [DAEMON] specifies.

**3.2.4** The **daemon shown** is the daemon whose workspaces, epics, flows and settings the page
draws at a given moment.

**3.2.5** The **daemon bar** is the area at the foot of the sidebar that names the daemon shown.

**3.2.6** A **view** is what the page draws beside the sidebar: a new epic, an epic, a session, a
log, an Exomyth, the flows, or the Environments view of an epic (Section 3.17). A **dialog** is what the page draws over a view: search, download,
settings, or the deleting of a chat.

**3.2.7** An **address** is the part of the page's URL that names one view or dialog, of one daemon.

**3.2.8** A **notice** is a record that one epic or one chat on one machine ended, asked a person a
question, or waits for what to say next, as Section 3.15 specifies. A **notification** is a notice as the page
presents it to the user, with the daemon it came from and whether the user has read it.

**3.2.9** The **Exomyth** of an epic is the page's view of that epic's timeline and flame graph.

**3.2.10** A **theme** is a set of colours and pictures the page is drawn in. A **pair** is a light
theme and a dark theme kept together under one name. A **preset** is a pair that comes with hmz.

**3.2.11** **App settings** are the settings pages that belong to the page in this browser alone.
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

**3.3.5** The page MUST offer the workspace `hmz web` was started in (`/here`, Section 4.6) first
wherever it offers a workspace of Local for a new epic.

**3.3.6** The page MUST NOT show a secret: an account MUST be shown by its harness, its name, its
way in and the names of the variables it sets, and never by a value.

**3.3.7** The page MUST NOT show a URL with credentials signed into it; it MUST show such a URL with
the credentials removed.

**3.3.8** Stopping `hmz web`, or closing the page, MUST NOT stop any epic.

### 3.4. Layout and navigation

#### 3.4.1. Layout

**3.4.1.1** The page MUST consist of a sidebar and, beside it, the current view.

**3.4.1.2** The sidebar MUST show, from top to bottom: a title row (3.4.1.6), the entries
`New chat`, `New epic`, `Search` and `Flows`, the chats and epics of the daemon shown as Section 3.5
specifies, and a foot (3.4.1.8).

**3.4.1.2.1** `New chat` MUST open a new chat (Section 3.8.18) and `New epic` a new epic of a flow
(Section 3.8.1); the two MUST be separate entries, `New chat` the first. The Humanize mark MUST open
a new chat.

**3.4.1.3** The `Flows` entry MUST show how many installed flows have a newer release, where at
least one has.

**3.4.1.4** On a screen as narrow as a phone's, the sidebar MUST be a drawer opened by a button, and
every view MUST be usable without horizontal scrolling of the page.

**3.4.1.4.1** While that drawer is open the focus MUST be in it and the view under it MUST NOT be
reached by keyboard; Escape MUST close it, and closed so, or by `Hide sidebar`, the focus MUST be
the button's that opens it.

**3.4.1.5** The page title MUST name the machine of the daemon shown.

**3.4.1.6** The title row MUST hold, in this order: the Humanize mark, `Hide sidebar`, `Back` and
`Forward`, and, at its far end, the notification bell. `Back` and `Forward` MUST step back and
forward through the addresses the page was on, as the browser's own do. In Humanize Desktop's window
on macOS, outside full screen, the row MUST stand beside the window's traffic lights, `Hide sidebar`
straight after them, and the mark MUST stand before the bell instead.

**3.4.1.7** The four entries MUST be drawn alike, one row each; the entry of the view shown MUST be
marked, and no entry MUST be drawn heavier than another otherwise.

**3.4.1.8** The foot MUST be one row: the daemon bar (Section 3.13) and, after it, `Settings`, which
MUST open the settings (Section 3.11).

**3.4.1.9** On a screen wider than a phone's, the sidebar MUST be 275 CSS pixels wide until the user
sizes it, and its right edge MUST be a splitter, `Resize sidebar`, that sizes it between 200 and 480
CSS pixels where it is dragged or moved with the arrow keys, and makes it 275 wide again where it is
double-clicked. Dragged, it MUST move by as far as the pointer went, and a press that moves nowhere
MUST NOT size the sidebar. The page MUST remember the width in this browser.

#### 3.4.2. Addresses

**3.4.2.1** Every view and every dialog MUST have an address that the user can keep and open again,
and opening that address MUST draw the same view or dialog.

**3.4.2.1.1** An address that names no view MUST open a new chat (Section 3.8.18).

**3.4.2.2** Every address MUST name the daemon it belongs to; an address that names no daemon MUST
belong to Local.

**3.4.2.3** Every link the page draws MUST keep the daemon of the address the page is on.

**3.4.2.4** Opening an address of another daemon MUST draw the sidebar and the view again, of that
daemon, and MUST stop drawing anything of the previous daemon.

**3.4.2.5** An address of an epic's log of every session MUST open that epic.

**3.4.2.6** A dialog opened over a view and closed again MUST leave the addresses the page steps
back through as they were before it was opened, so that `Back` then goes to what was open before
that view and MUST NOT open the dialog again; and a view opened from a dialog MUST take the
dialog's place among them. Closing a dialog MUST leave the page on the address of the view under
it as that view stands, the chat or epic it shows marked in the sidebar.

> Informative: an address is held in the fragment of the page's URL, as `#/epics/<name>` is.

#### 3.4.3. Keyboard

**3.4.3.1** Cmd+K, or Ctrl+K, MUST open `Search`.

**3.4.3.2** Cmd+Shift+O, or Ctrl+Shift+O, MUST open a new chat.

**3.4.3.3** Cmd+., or Ctrl+., MUST hide or show the sidebar.

**3.4.3.4** Escape MUST close the dialog that is open, and MUST close the menu or picker that is
open.

**3.4.3.4.1** A dialog MUST keep Tab within itself while it is open, and opening one MUST close
the menu that is open. A dialog closed over the view it was opened over MUST give the focus back
to what held it as the dialog opened, where that still stands.

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

**3.5.1** While its list is grouped by folder (3.5.17), the sidebar MUST show every workspace of
the daemon shown as a folder: each workspace an epic ran in, each workspace written down in the
settings, and each workspace the user opened by its path. A folder, as any other group of the list,
MUST be drawn as a heading over its epics, saying its name, and MUST NOT be drawn as one of the rows
under it.

**3.5.1.1** While its list is grouped otherwise, the sidebar MUST show the same workspaces as the
rows of a last group, `Folders`: each row MUST open a new chat in its workspace and MUST offer the
menu of a folder (3.5.7), bar folding it, by a right click and by `More options` at its end.

**3.5.1.2** The epics of no workspace MUST be listed as the last folder, `No folder`, which has no
menu of a folder. Grouped by `Folder`, a list with no workspace and no epic to show MUST keep that
heading, so that `Group and sort` (3.5.6) is always offered.

**3.5.2** A workspace the user opens by its path MUST be written down in the settings, and MUST stay
in the sidebar from then on.

**3.5.3** The sidebar MUST order the workspaces with those that have an epic going first, then by
their latest epic, newest first, as the list is sorted (3.5.17).

**3.5.4** Each group MUST list its epics in the order the list is sorted in (3.5.17), chats among the
others, and MUST say `Nothing here yet` where it has none.

**3.5.5** The user MUST be able to fold a group away and open it again by its heading; the page MUST
remember which groups are folded in this browser.

**3.5.6** The heading of each group MUST offer, at its end, `Group and sort` (3.5.17) and `+`, which
opens a new chat: in that workspace, for a folder. The two MUST be shown where the heading is
pointed at or holds the focus, and always where the device has nothing to point with.

**3.5.7** The menu of a folder MUST offer: a new chat there, a new epic there, its flows, searching
it, copying its
path, folding or opening it, its workspace settings, its usage, and, where no epic ran there,
forgetting it.

**3.5.8** Each epic in the sidebar other than a chat MUST show its task's first line, the mark of
its state said as a word (`Running`, `Asking`, `Waiting`, `Stopping`, `Done`, `Failed`, `Refused`,
`Crashed`, `Stopped`, `Budget spent`, `Unfinished`), the name of its flow, and either `live`, where a
host is going with it, or how long ago it began; the header of an epic's own page MUST show the mark
of its state. The mark MUST be the first of these that holds:

1. `asking`, while its host waits on a question to a person that this browser has not seen;
2. `waiting`, while its host waits on a question and this browser has seen every one, for an epic
   other than a chat;
3. `stopping`, while its host is stopping it;
4. `running`, while it is going;
5. `done`, `failed` (failed, refused or crashed) or `stopped` (stopped, or its budget spent), as it
   ended;
6. `unfinished`, where its process went before it ended.

**3.5.9** The `asking` mark MUST blink, as MUST the word a row of the sidebar says it in (3.5.8),
and every other mark MUST NOT blink; what a chat's row says (3.5.15) MUST NOT blink. The page MUST
treat a
question as seen once, while the question waits, the page of its epic, `#/epics/<name>`, of its
chat, `#/chats/<id>`, or of its host, `#/live?workspace=…&slot=…`, is shown, visible and focused; the page MUST remember in this
browser which questions were seen.

**3.5.10** An epic that another process is going with, outside any host, MUST be marked as going and
MUST NOT be marked `live`. A chat MUST be marked only `running` while a turn is open, `asking`,
`failed`, or otherwise `stopped`, and MUST NOT be marked `live`. A chat that folds away while this
browser has not seen what it last waited on MUST stay `asking` until that is seen, and the page MUST
remember in this browser what each chat last waited on until a turn of it opens.

**3.5.11** An epic other than a chat MUST be expandable into its agents, and each agent into the
sessions it opened; a chat MUST NOT be expandable. The page MUST remember in this browser which
epics are expanded.

**3.5.12** The menu of an epic MUST offer, in this order: open it, `Pin` or `Unpin` (3.5.18),
`Mark as unread` or `Mark as read` (3.5.19), its Exomyth (not for a chat), resume it where it
can be resumed, a new epic like it, copying its link, its task and its name, exporting it once it is
no longer going (not for a chat), uploading it, and stopping it while a host is going with it (not
for a chat). The menu of a chat MUST offer a new chat like it in place of a new epic, MUST call its
task its first message and its name its ID, MUST upload it with `chat.backup`, and MUST NOT say
`epic`, `flow` or `task`.

**3.5.12.1** The menu of a chat MUST also offer, in the order of Section 3.5.12: `Rename` after
`Mark as unread` or `Mark as read`, where the chat's title is drawn where the menu was opened
(Section 3.6.6.23); `Fork` after a new chat like it (Section 3.6.6.24); and last, `Archive` -- or
`Unarchive`, for an archived chat -- and then `Delete` (Sections 3.6.6.25 and 3.6.6.26).

**3.5.13** Each group MUST show a bounded number of its epics at first, and with them the epic the
page is on, and MUST end with `Show N more`, `N` the number of its epics read and not shown, while
there is one; pressed, it MUST show them, and every epic listed in that group from then on. The
sidebar MUST read a bounded number of epics at first, and MUST read more only where the user asks:
where `Show N more` is pressed while the daemon holds more, and where `Show more` is, with which the
list MUST end while the daemon holds more and every epic read is shown. `Show N more` MUST be
described, to assistive technology, by the name of its group.

**3.5.14** The sidebar MUST show the epics of the daemon shown as they change, without the user
asking.

**3.5.15** A chat in the sidebar MUST be drawn as a row of another kind than any other epic: its
task's first line alone, with no mark or glyph of a state, no name of a flow and nothing that opens
it out. After that line, in the same line, its row MUST say `Running` while its mark (3.5.10) is
`running`, `Awaiting input` while it is `asking`, `Failed` where it is `failed`, and nothing where it
is `stopped`. What the row says when pointed at MUST say when the chat began, and the row MUST show
how long ago it began where the device has nothing to point with. The row, and what it says when
pointed at, MUST NOT say `epic` or `flow`.

**3.5.16** The first line of every epic's row, a chat's or another's, MUST be 32 CSS pixels tall, its
task's first line at the left, cut short where the line has no room for all of it, and the words for
its state straight after it. Each row MUST offer
`More options` at its far end, shown where the row is pointed at or holds the focus, and always
where the device has nothing to point with; it MUST open the menu of that epic (3.5.12), the one a
right click on the row opens. `More options` MUST say whether its menu is open, MUST close the menu
where it is pressed again, and MUST hold the focus once Escape or a choice closes the menu.

**3.5.16.1** Where the sidebar draws its list again, what held the focus in it MUST hold it still;
after a choice in `Group and sort`, `Group and sort` MUST.

**3.5.17** `Group and sort` MUST open a menu of: `Group by`, one of `Folder`, `Date` and `None`;
`Sort by`, one of `Last updated` and `Created`; `Show`, `Chats` and `Epics`, each on or off; and
`Reset to defaults`. Until the user says otherwise the list MUST be grouped by `Folder`, sorted by
`Last updated`, and show both. The page MUST remember what was chosen in this browser.

**3.5.17.1** Grouped by `Date`, the list MUST show its epics under `Today`, `Yesterday`,
`Last 7 days`, `Last 30 days` and `Older`, by the moment they are sorted by, and no group that is
empty, bar `Today` where it has no epic to show; grouped by `None`, it MUST show them as one group.

**3.5.17.2** Sorted by `Last updated`, an epic going MUST stand before one that is not, and the rest
by when each ended, or began where it has not ended, newest first; sorted by `Created`, each by when
it began, newest first.

**3.5.17.3** The list MUST leave out every chat while `Chats` is off, and every other epic while
`Epics` is off.

**3.5.18** `Pin` MUST pin an epic and `Unpin` unpin it. The epics pinned MUST be listed first, under
`Pinned`, and in no other group, however the list is grouped. The page MUST remember which epics are
pinned in this browser.

**3.5.19** `Mark as unread` MUST mark an epic as a notification unread of it does (Section 3.15),
until the page next comes to that epic or `Mark as read` is chosen. `Mark as read` MUST also read
every notification of that epic. The page MUST remember which epics are marked in this browser.

**3.5.20** A chat is no epic (Section 8 of [CORE]). The sidebar MUST read the chats of the daemon
shown with `chat.list` and its epics with `runs.list` (Sections 4.25 and 4.16 of [DAEMON]), and
MUST list both as one list: what Section 3.5 states of an epic of the list, it states of a chat
too, unless it says otherwise. The page MUST NOT ask `runs.*` for a chat.

**3.5.20.1** A chat MUST be named by its id and told by its title, and its address MUST be
`#/chats/<id>`. Every link the page makes to a chat MUST be that address, and MUST NOT be an
epic's.

**3.5.20.2** A chat's row MUST be marked (3.5.10) from its `state`: a turn open while it is `turn`
or `asking`, between turns while it is `going`, `failed` where it is `failed`, and `stopped`
otherwise. What a chat a host holds waits on MUST be read from `hosts.running`, by the chat's id,
so that what it waits on between turns is marked `asking` until this browser has seen it. Sorted
by `Last updated` (3.5.17.2), a chat that rests MUST stand by its `updated`.

**3.5.20.3** An epic an earlier hmz recorded for a chat (`kind` `chat`, Section 4.16.2.1 of
[DAEMON]) MUST be listed, found and drawn as any other epic, at `#/epics/<name>`, with its flow
said as `chat`. The page MUST NOT draw it as a chat, and MUST NOT offer to resume it, to start a
new epic like it, or to say anything in it.

**3.5.20.4** The sidebar MUST leave out every archived chat (Section 8.10.3 of [CORE]), a pinned
one included.

**3.5.21** While the setting `harness_sessions` is `true` (Section 3.4.14 of [FILES]), and only
then, the sidebar, grouped by folder, MUST list in each workspace's group, after its chats and
epics, the harness sessions of that workspace (Section 8.11 of [CORE]) as `chat.harness.list`
answers them (Section 4.25.8 of [DAEMON]), newest first, at most 50 of a workspace. Grouped
otherwise, the sidebar MUST NOT list them.

**3.5.21.1** A harness session's row MUST be told by its title, or by its id where it has none,
MUST name its harness, MUST be drawn apart from a chat's -- quieter -- and MUST count among the
rows its group shows before `Show N more` (3.5.17). It MUST NOT be pinned, marked unread, renamed,
archived or deleted, and MUST NOT be among what Search finds.

**3.5.21.2** A harness session's address MUST be `#/harness/<harness>/<id>?workspace=<path>`. Its
view MUST draw what was said in it, read with `chat.harness.get` and `trace`, MUST say that it is
only read, MUST NOT offer anything to type in, and MUST offer `Continue in chat`, which MUST call
`chat.harness.adopt` and open the chat it answers.

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

**3.6.3.4** `Aside` MUST let the user ask a side question of one session of the epic as Section 9
of [CORE] specifies. `Aside` MUST offer this also for an epic its host no longer holds and for that
epic's sessions, as Section 4.15.3.3 of [DAEMON] specifies.

**3.6.3.5** `Aside` MUST hold several side conversations, as Section 9.6 of [CORE] states, each
picking the session it asks at its start with the control of Section 9.6 of [CORE] -- the epic's
agents, each opening its sessions -- above the box its question is typed in, and MUST NOT offer a
choice of any agent.

**3.6.3.6** `Aside` MUST keep each side conversation, the side questions asked in it and their
answers for the page opened again, MUST show while each is answering, MUST let the user close each,
and MUST say that side questions never reach the epic.

**3.6.3.7** `Board` MUST let the user edit, remove and add lines of the epic's board, and MUST NOT
offer to change a line the flow owns.

**3.6.3.8** `People` MUST, for each person the flow has, let the user claim the role for this
browser, take it over from another frontend, release it, and set it away or back.

**3.6.3.9** While a host holds the epic, `Epic` MUST link each environment it shows to that env in
the Environments view (Section 3.17).

#### 3.6.4. Steering an epic that is going

**3.6.4.1** Under the graph, while the epic waits on a person, the page MUST show each question as
Section 3.6.9 states.

**3.6.4.2** A question that another frontend holds MUST say whose it is (Section 3.6.9.2).

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
what the person was asked, was shown and answered; a line typed under one MUST go to whose it is.

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
people, or a way to end it; its open turn is stopped as Section 3.6.6.21 states. It MUST offer, beside the conversation of a chat a host holds, a side
panel `Environment` that the user can hide and show, holding the Environments view of the chat's
envs (Section 3.17) and a link to that view on its own.

**3.6.6.5** Each chat MUST go on a host of its own, beside every other chat and every flow of its
workspace; starting a chat or an epic MUST NOT end another.

**3.6.6.6** A chat that has folded away MUST be carried on, the same chat, when the user says
something in it -- by `chat.start` with `resume` the chat's id -- with what was said before drawn
above.

**3.6.6.7** The box under a chat MUST complete `/`, `$` and `@` from the chat's catalogue, the names
hmz keeps and the flows (`chat.commands`, Section 4 of [DAEMON]), each tagged with where it comes
from, and MUST serve each line as Section 8.9 of [CORE] states.

**3.6.6.8** The page MUST draw a `!` line of a chat and its output in the style of a shell.

**3.6.6.9** The page MUST offer, for each chat, in the menu of the chat's bar (Section 3.6.6.10),
the choice of its preference between `native` and `flow`, worded as what a `$` name that is both a
skill and a flow does -- `Use the skill` or `Start the flow` -- with a mark on the one in force,
showing whether it comes from the settings file or the chat (`chat.set`, Section 4 of [DAEMON]).
The page MUST NOT draw that choice on the bar itself.

**3.6.6.10** The bar of a chat MUST hold, at its left, the chat's title as a button that renames
the chat (Section 3.6.6.23), and right after it one menu, `More options`; and at its far right the buttons
of Section 3.6.6.19, with which the bar MUST end (Section 3.16.1). The menu MUST offer what the
chat's right-click menu offers (Section 3.4.4.1), the chat's `Environment` (Section 3.6.6.4) where
its host has one, and the choice of Section 3.6.6.9. The bar MUST NOT say how the chat stands
(Section 3.6.6.18).

**3.6.6.11** The panel beside a chat MUST show one pane at a time, picked on the chat's bar
(Section 3.6.6.19) and headed by its name, and MUST NOT draw a row of tabs to pick it by, nor the
tabs of the Environments view over the chat's `Environment`. It MUST call `Details` and `Side
questions` what Section 3.6.3 calls `Epic` and `Aside`, MUST show under `Details` everything `Epic`
shows that a chat has, each named in plain words, and MUST say that side questions never reach the
chat.

**3.6.6.12** The page MUST NOT call a chat an epic or a run, nor a choice of the chat's `native`,
in the bar, the menu, the tabs, the headings, the labels and the box of a chat's view. The box
under a chat MUST say, while it is empty, no more than that it takes a reply, MUST offer what `/`,
`$`, `@` and `!` start there in its `Add` menu (Section 3.6.6.16), and MUST name what it completes
by what each is: the
commands, the skills and the mentions of the chat's CLI, the names hmz keeps, the flows, and the
files.

**3.6.6.13** The box under a chat MUST say, on a chip in the row under it (Section 3.6.6.15), the
model the chat's agent runs and then its effort where one is set. The chip MUST open a menu saying the agent's
model, effort, harness and account, and offering a new chat in the chat's workspace. Where the
chat's catalogue holds the harness's own `/model` or `/effort` as `call` (Section 8.9.5 of [CORE]),
the menu MUST offer the models known runnable as the agent's account, accepting a typed model, or
the efforts its model takes, and picking one MUST say that line to the chat. The page MUST NOT
offer to change the agent of a chat that has begun any other way.

**3.6.6.14** The row under the box of a chat (Section 3.6.6.15) MUST hold a permission chip that
names the chat's permission
(Section 8.3.9 of [CORE]) and opens a menu of the three, each with one line saying what it lets the
assistant do, the one in force checked: `Read only` for `read-only`, `Edit this folder` for
`workspace-write` and `Full access` for `danger-full-access`. Picking one MUST set it (`chat.set`,
Section 4 of [DAEMON]) for a chat a host holds, and MUST be what a chat that has folded away is
carried on with. The page MUST NOT offer a permission that puts the assistant's actions to the
user's approval, which no chat has (Section 8.3.9 of [CORE]), and MUST NOT draw the chip for an
Ai-chan conversation.

**3.6.6.15** The box a chat is typed into -- under a chat, and on the form of a new chat -- MUST
hold, inside it, only an `Add` button at its left, what is typed, and at its right the button that
sends. Every other control of the box MUST be a chip in one row under it, no taller than 24 CSS
pixels and set in from the edges of the box: at the left of that row where the chat runs, and at
its right how it runs. A menu opened from the box or from a chip of that row MUST draw a choice of
one line as a row 28 CSS pixels high, and MUST open with the focus on the choice in force where it
marks one. A chip that picks something MUST be named, to assistive technology, by what it picks
and then what is picked, as `Model: Haiku 4.5`.

**3.6.6.16** Under a chat, `Add` MUST open a menu of `Add files`, `Slash commands`, `Skills and
flows` and `Run a shell command`, which MUST type `@`, `/`, `$` and `!` into the box -- `@` where
the caret is, the others at the start of the line -- and the box MUST then offer what it completes
there (Section 3.6.6.7). On a form, where no chat's host says what the others start, `Add` MUST
offer `Add files` alone, which MUST complete the paths of the workspace picked and MUST be disabled
while none is picked, `No folder` (Section 3.8.2) among it, saying `Pick a folder first`. Each of
the four typed by hand MUST do what it did.

**3.6.6.17** The row under the box of a chat that has begun MUST hold, at its right and in this
order, the chip of Section 3.6.6.13, the chip of Section 3.6.6.14 and a chip `Usage`, which MUST
say what the chat has spent or written where the page knows it and MUST open the chat's `Details`.
That row MUST NOT hold where the chat runs.

**3.6.6.18** While a turn of a chat is open, the page MUST say over the chat's box who is
responding, by the model the chat's agent runs; it MUST say there, besides, that the chat waits on
the user or has failed, and MUST say nothing there otherwise.

**3.6.6.19** The bar of a chat MUST hold, at its far right and in this order, a button each for
`Details`, `Terminal`, `Changes` and `Files`, each 28 CSS pixels square, and then a menu `View
options` holding `Side questions`, `Board` while the chat keeps one (Section 3.6.3), and `Ai-chan`
(Section 3.16.1), each marked while it is the one shown. `Details`, `Side questions` and `Board`
MUST open the panel beside the chat on that pane (Section 3.6.6.11); `Terminal`, `Changes` and
`Files` MUST open it on the chat's
`Environment` (Section 3.6.6.4) at that panel (Section 3.17), and MUST be disabled while the chat
has no such panel, saying whether that is for want of a host or of such a panel in its
environment. A button MUST say whether its pane is the one open, and pressing the one open MUST
shut the panel. Where the panel stands beside the chat, the bar MUST run over both, so that a
button stays where it is as its pane opens and shuts.

**3.6.6.20** The panel beside a chat MUST be shut until the user opens a pane of it, and MUST then
be open or shut as this browser last left a chat's. The page MUST NOT draw the panel before it
knows whether a chat or an epic of a flow is in front.

**3.6.6.21** While a turn of a chat is open -- its host says its turn is `running`, the agent
answering or asking mid-turn -- the button that sends MUST be `Stop` in its place: pressed, it MUST
stop that turn with `chat.stop` of the chat's workspace and slot (Section 4.25 of [DAEMON]), and
the chat MUST stay, between turns. A refusal MUST be said over the box in the daemon's own
sentence. Between turns the button MUST send. What is typed and sent by <kbd>Enter</kbd> while a
turn is open MUST still be delivered as Section 8.4.4 of [CORE] states. The page MUST NOT offer
any other way to stop a chat.

**3.6.6.22** The page MUST read a chat with `chat.get`, by its id, and what was said before it was
last carried on with `chat.get` and `trace`; it MUST NOT read a chat with `runs.get` or
`runs.trace`. The bar of a chat MUST say the chat's title. The address of a chat MUST be
`#/chats/<id>` and MUST name none of its sessions; the address of a chat's host,
`#/live?workspace=…&slot=…`, MUST become `#/chats/<id>` once the host names the chat. A side
question about a chat (Section 3.6.3.4) MUST name it to `btw.list` and `btw.ask` as `chat`.

**3.6.6.23** Renaming a chat MUST put, in place of its title -- on the chat's bar, or in its row of
the sidebar where `Rename` was chosen from that row's menu -- a field holding the title.
<kbd>Enter</kbd> in the field, and leaving it, MUST record what it holds as the chat's title
(`chat.rename`, Section 4.25.7 of [DAEMON]), unless that is the title it had or white space alone;
<kbd>Escape</kbd> MUST leave the title as it was. The chat's bar and its row MUST then say the new
title. The sidebar MUST NOT draw over the field while it is open.

**3.6.6.24** `Fork` MUST fork the chat (`chat.fork`) and MUST then open the new chat. A refusal of
`chat.fork`, of `chat.rename`, of `chat.archive` or of `chat.unarchive` MUST be said in the
daemon's own sentence, and MUST leave the page where it was.

**3.6.6.25** `Archive` MUST archive the chat (`chat.archive`) and `Unarchive` put it back
(`chat.unarchive`). An archived chat MUST still open at its address and be read there, and its bar
MUST then hold `Unarchive`, before the buttons of Section 3.6.6.19.

**3.6.6.26** `Delete` MUST open a dialog (Section 3.4.2.1) that names the chat by its title, says
that deleting it permanently removes the chat's record and the sessions kept with it, that this
cannot be undone, and that a worktree the chat worked in is left on disk, and offers `Cancel` and
`Delete`, the focus on `Cancel`. `Delete` there MUST delete the chat (`chat.delete`) and close the
dialog; where the chat deleted is the one in view, the page MUST then open a new chat in its place.
A refusal MUST be said in the dialog in the daemon's own sentence, and the dialog MUST stay open.
`Cancel`, <kbd>Escape</kbd> and a deletion done MUST go back to what the dialog was opened over,
another dialog included.

**3.6.6.27** `Details` MUST say where a chat's assistant works (`workdir`), beside the chat's
workspace, where the two differ (Section 8.3.13 of [CORE]).

#### 3.6.7. An epic written down

**3.6.7.1** An epic that has ended MUST show how it was set up -- its agents, environments,
parameters and budget -- the tree of flows it called, its sessions, what it spent and how long it
took.

**3.6.7.2** The page MUST offer `Read turns`, which reads the epic's handovers and each session's
turns back out of the logs it kept.

**3.6.7.3** The page MUST offer `Export`, which downloads the epic as one archive, as Section 3 of
[CORE] specifies, reading it in chunks (`runs.bundle` and `files.read`, Section 4.16.4.4 of
[DAEMON]).

**3.6.7.4** The page MUST offer `Upload` on every epic, which backs it up at once to the targets it
was started with, else to the default targets, and MUST answer at once with the targets it was
queued for, without waiting for the push.

**3.6.7.5** The page MUST say, on hover of `Upload`, how the last backup of the epic to each target
went.

**3.6.7.6** The page MUST offer `Resume` only where the epic's flow can resume it, and MUST then
open a new epic set up as that epic was started, in that epic's workspace.

#### 3.6.8. Importing

**3.6.8.1** The page MUST let the user import an exported epic by picking the file or dropping it
anywhere on the window, sending it in chunks (`files.create`, `files.write` and `runs.import`,
Section 4.16.6 of [DAEMON]), or by opening the import address that names its path on Local's
machine; where Local runs in WSL, that path MAY be a Windows path, read as WSL names it.

**3.6.8.2** In a browser, the import address MUST import only once the user presses `Import`.

**3.6.8.3** An imported epic MUST be imported into the daemon shown, under the workspace it ran in,
and MUST then open on its Exomyth.

**3.6.8.4** An epic already present MUST be refused, naming it, and the page MUST offer `Open` to go
to it.

**3.6.8.5** An imported epic that cannot be resumed on this machine MUST say why, and the page MUST
NOT offer to resume it.

#### 3.6.9. Questions

**3.6.9.1** A question MUST be drawn as one card, in reading order: the question's `text` as its
headline; its context blocks beneath (Section 3.6.10); and the means to answer it last.

**3.6.9.2** A question that another frontend holds MUST be drawn read-only, its form or options
drawn but not to be filled, with `Waiting for <name> to answer: that frontend holds <role>.`,
`<name>` being that frontend's name.

**3.6.9.3** A question without a schema MUST offer its options as buttons, each numbered `1` to `9`
in order, and a field for an answer of the user's own; a button MUST send its option's text, and
the field what is typed, as `text` of `epic.answer`.

**3.6.9.4** A question with a schema MUST be answered by one form drawn from the whole schema, sent
whole as `value` of `epic.answer` (Section 4.8.4 of [DAEMON]); the page MUST NOT ask it a field at a
time.

**3.6.9.5** The form MUST draw each field of the schema by its type as follows, and MUST draw one
type, and word it, alike wherever it draws it:

| Field | Drawn as |
| --- | --- |
| `enum` or `const` choice of at most 5 values | one row of large buttons, one per value |
| `enum` choice of more than 5 values | a list to pick from, which the user can search |
| `boolean` | two buttons, each worded from the field's `description` (as `Yes, write tests` and `No tests`), else `Yes` and `No`; never a lone checkbox |
| `integer`, `number` | a number field held to the field's bounds |
| `string` | a text field that grows as its text does; with `format` `date`, `date-time`, `email` or `uri`, the browser's own field of that kind |
| `string` with `hmz:widget` `markdown` | a text field with a preview of the Markdown |
| `string` with `hmz:widget` `code` | a text field in a monospaced face that keeps its indentation |
| `string` with `hmz:widget` `secret` | a field that hides what is typed |
| `object` | its fields, grouped under its title |
| `array` | its items, each removable, and `Add` |
| anything else | a text field taking JSON |

**3.6.9.6** Each field MUST be named by its `title`, else its name, with its `description` as a
hint beneath it.

**3.6.9.7** The form MUST put the required fields first, then the optional fields without a
default, then those with one, each in the schema's order. A field with a default MUST be filled
with it and marked `suggested`. Where an object has more than 3 fields and not every one has a
default and is optional, its optional fields with defaults MUST be folded under `More options
(<n>)`, `<n>` being how many, opened where one of them holds other than its default or a problem.

**3.6.9.8** The button that sends the form MUST say `<n> required left` while `<n>` required fields
are empty, and `Send answer` otherwise. A form every field of which has a default MUST be sendable
at once with that button or `Enter`.

**3.6.9.9** Where the focus is not in a text field, the digits `1` to `9` MUST pick the option, or
the value of the choice of the form holding the focus, else of its first, of that number; within a
choice, the arrow keys MUST move the pick. `Cmd+Enter`, or `Ctrl+Enter`, MUST send the answer. The
order of `Tab` MUST be the order of reading.

**3.6.9.10** The page MUST check a field when it loses the focus and when the form is sent, and MUST
NOT check it at each key. What is wrong MUST be said in plain words beside its field.

**3.6.9.11** Where `epic.answer` is refused as an answer that does not fit, the page MUST put each
of the refusal's `errors` beside the field its `path` names, or the nearest field holding it, else
above the button, and MUST move the focus to the first.

**3.6.9.12** The page MUST keep what the user has typed into a question in this browser, keyed by
the question's host, run and number, until the question is answered or withdrawn or for 14 days,
and MUST restore it when the page is opened again; a `secret` field MUST NOT be kept.

**3.6.9.13** A question withdrawn MUST fold, in its place, to one line saying why: `Withdrawn:
<role> went away` for `away`, `Withdrawn: the run ended` for `over`.

**3.6.9.14** A question answered MUST fold to one line of the answer, `You answered: <answer>`, or
`<name> answered: <answer>` where another frontend answered it: the values of a form in the order
asked joined by ` · `, a choice as it is, text in quotes, and a `yes`, `no` or number after its
field's label, as `approve · ‘LGTM’ · tests: no`; a `secret` value MUST be written `***`. A folded
question MUST be dismissable.

**3.6.9.15** A new question MUST be marked by the page's marks of Section 3.5 and Section 3.15 and
one quiet highlight that fades by itself, and by nothing that moves or plays by itself; the page
MUST honour `prefers-reduced-motion`.

**3.6.9.16** Each field MUST have a label of its own; its hint and what is wrong with it MUST be
tied to it for assistive technology; the focus MUST be visible; and the colours MUST keep their
contrast in every theme.

#### 3.6.10. Context blocks

**3.6.10.1** The page MUST draw each context block (Section 3.10.5 of [PYTHON]) of a question in
the order given, under its `title`, as follows:

| Kind | Drawn as |
| --- | --- |
| `markdown` | Markdown, made safe and drawn by `vendor/markdown.js`; where that cannot be loaded, the text as written |
| `code` | the text in a monospaced face, with its language |
| `diff` | each file's changes, the lines added and removed marked, as `Changes` draws a change (Section 3.17.4) |
| `table` | a table under its columns |
| `image` | the image, with `alt` as its text alternative |
| `json` | a tree whose branches fold |
| `chart` | the chart, drawn by `vendor/vega.js`; where that cannot be loaded, a table of the `values` of its `data` |

**3.6.10.2** The first block MUST be open. Every other block MUST be folded behind one line saying
what it holds, as `+12 −3 in 2 files` for a diff and `table · 40 rows` for a table, and MUST open
when the user picks that line.

**3.6.10.3** A block of a kind the page does not know MUST be drawn as its `title` and its JSON.

**3.6.10.4** Blocks shown with no question (`shown`, Section 4.9.2.4 of [DAEMON]) MUST be drawn in
the person's log (Section 3.6.5.3), where they came, with no means to answer.

#### 3.6.11. Faces

**3.6.11.1** A question naming a face (Section 3.10.7 of [PYTHON]) MUST be drawn by that face, in
place of its context blocks and its form; its `text` MUST stay its headline.

**3.6.11.2** The page MUST read a face's HTML with `epic.face`, once per hash.

**3.6.11.3** A face MUST run in an `<iframe sandbox="allow-scripts allow-forms">` loading
`faces/frame.html`, and the sandbox MUST NOT allow the same origin: a face has an opaque origin, no
cookie and no `/rpc`.

**3.6.11.4** The page and a face MUST talk only over a `MessageChannel`, one port of which the page
hands the frame once, as it loads, with a token made afresh for each frame. The page MUST ignore
every other message from the frame, and every message that does not come from it.

**3.6.11.5** The page MUST give the face, as `window.hmz`, exactly:

| Call | What it does |
| --- | --- |
| `hmz.on("ask", ({prompt, context, schema, errors}) => ...)` | Hands the face each new question of its session, and the `errors` of its answer last refused, `[]` for none |
| `hmz.on("show", (context) => ...)` | Hands the face the blocks its session is shown (Section 3.10.6 of [PYTHON]) |
| `hmz.on("theme", (tokens) => ...)` | Hands the face the CSS variables of the page's theme, whenever the theme changes |
| `hmz.submit(value)` | Answers the question the face holds with `value`, and resolves to `{ok: true}`, or to `{ok: false, errors}` where it is refused |
| `hmz.resize(height)` | Makes the frame `height` pixels high |

**3.6.11.6** `hmz.submit(value)` MUST send `epic.answer` with `value` (Section 4.8.4 of [DAEMON]):
`errors` MUST be the refusal's, for an answer that does not fit, and otherwise one error of `path`
`[]` whose `message` is the refusal's.

**3.6.11.7** The CSS variables of the page's theme MUST be set on the face's `:root` before the face
loads.

**3.6.11.8** The page MUST mount one frame for each outworlder session (`session`), MUST keep it,
and what the face holds, across that session's questions, MUST hand it each of them with `ask`,
and MUST hand it, with `show`, the context of every `shown` record of that session. The page MAY
let go of the frames of all but the 8 sessions it drew last.

**3.6.11.9** A face that fails to load, that throws before it calls `hmz.on("ask", ...)`, or that
has not called it within 5 seconds of its frame being loaded, MUST give way to the form, as for a
question naming no face, under a note saying why the face could not be shown, beside `Try again`,
which loads the frame afresh and, where the face then calls `hmz.on("ask", ...)`, shows it again.

**3.6.11.10** The page MUST draw, beside every face it shows, one switch: `Plain form`, which shows
the form in place of the face, and, while the form is shown, `Back to <title>`, the face's `title`,
else `the custom view`, which shows the face again as the person left it.

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
path with completion as it is typed, or to pick no workspace, `No folder`.

**3.8.2.1** The form MUST offer that choice under the box of Section 3.8.5, at its left, as a
control naming the workspace picked, and MUST NOT offer it in the bar over the form.

**3.8.2.2** The menu of that control MUST list the workspaces the daemon shown serves, each one
row named by the last part of its path and saying its path where it is pointed at, and after them
`Open folder…` and `No folder`.

**3.8.3** With `No folder` picked, the form MUST offer the flows and the set-up of the
workspace `hmz web` was started in, and starting MUST start the epic in a new directory made for it
alone in the system's temporary directory.

**3.8.4** The user MUST be able to pick any flow on offer in that workspace.

**3.8.4.1** Where no flow is on offer there, the form MUST say so in the middle of the page, with
`Open Flows`, which opens the flows of that workspace (Section 3.9); what picks the flow MUST
offer the same, `Options` MUST be disabled, and starting MUST be refused saying that a flow is
installed first.

**3.8.5** The form MUST offer a box for the task; Enter in it MUST start the epic.

**3.8.6** `Options` MUST hold what the flow is set up with, as that workspace last set it up: for
each agent role an agent, for each environment role an environment, the parameters, the budget, the
backup targets, `Profile flow` and `Profile environment`.

**3.8.7** The form MUST show beside `Options` what is set, bar on a screen as narrow as a phone's,
where `Options` alone says it once opened.

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

**3.8.14** The form MUST refuse to save or start where a role has no agent, or where no limit bounds
what the epic spends.

**3.8.15** Once the epic starts, the page MUST go to it; for a chat, to its conversation.

**3.8.16** Resuming an epic MUST open the form set up as that epic was started, in that epic's
workspace.

**3.8.17** A new chat and a new epic of a flow MUST each be a form of its own, at an address of its
own, and neither form MUST offer a control that goes to the other; Section 3.8.1 to Section 3.8.16
state the form of a new epic of a flow, which MUST NOT offer a chat among its flows.

**3.8.18** The form of a new chat MUST take a workspace, or `No folder`, as Section 3.8.2 and
Section 3.8.3 state; the assistant's agent, picked as Section 3.8.19 states, starting from the
chat agent that workspace remembers (Section 8.3.8 of [CORE]); and the first message, Enter in its
box starting the chat (`chat.start`, Section 4 of [DAEMON]) and the page going to its conversation.

**3.8.18.1** The bar over the form of a new chat MUST NOT hold a control of the form's own.

**3.8.19** The form of a new chat MUST offer the assistant's agent as one chip under the box, at
its right (Section 3.8.22), saying the model chosen and then its effort where one is set. The chip MUST open a
menu holding, under no heading: the models known runnable by the harness chosen as the account
chosen, each one row naming it as a person reads it, with the one chosen marked, asking the harness
where none is known yet; `Effort`, one row saying the effort chosen and opening the efforts the
model chosen takes; and `More`, one row opening a typed model, the harness, the account it runs as
with a way to make one, and a way to ask the harness for its models again. What is picked MUST
come to what `-a` spells, as Section 3.8.10 states.

**3.8.20** The form of a new chat MUST hold the permission chip of Section 3.6.6.14 under the box,
at its right after the chip of Section 3.8.19, on `Edit this folder` until the user picks another,
and the chat MUST be started with the one picked. Its menu MUST be 308 CSS pixels wide where the
window has the room, and MUST hold the three and what it says of them under no heading.

**3.8.21** The form of a new chat MUST be drawn as a new session of a chat app is: a bar 44 CSS
pixels high holding the heading `New chat` at its left; the box of Section 3.6.6.15 docked at the
foot of the page, in the column a conversation is read in; and between them nothing but the list
of Section 3.8.23. It MUST NOT draw a greeting, a mark, or a box in the middle of the page.

**3.8.22** The row under the box of the form of a new chat MUST hold, at its left, `Environment`,
then the workspace control of Section 3.8.2.1 and then `Worktree` (Section 3.8.22.1), and at its
right the chips of Section 3.8.19 and
Section 3.8.20 and then `Usage`, drawn as the chip of Section 3.6.6.17 is, which MUST open what the
workspace picked has used (Section 3.11). `Environment` MUST name the daemon the page shows and MUST open a menu of Local and
every remote daemon this browser keeps, with the one shown marked, and `New environment`, which
opens the daemons' settings (Section 3.13); picking another daemon MUST switch the page to it
(Section 3.4.2.4), on the same form.

**3.8.22.1** `Worktree` MUST be a checkbox, clear until the user ticks it; ticked, the chat MUST be
started with `worktree` `true` (Section 4.25.1.8 of [DAEMON]). It MUST be disabled, clear, and say
why, under `No folder` and where `paths.list` finds `.git` neither in the workspace picked nor in
any directory over it; where that cannot be told it MUST stay enabled, and a refusal of the start
MUST be said as any other is (Section 3.4.4.9).

**3.8.23** The form of a new chat MUST list, in the middle of the page, in a list named `Next
steps` under no heading, each chat marked `asking` (Section 3.5.10) among the 200 newest chats of
the daemon shown (`chat.list`), in rows 32 CSS pixels high and at most 320 wide: a row MUST say `Asked a
question` after the chat's title, MUST open its chat, and MUST hold, inside it at its right, a
button that dismisses it from the list in this browser until that chat asks something else,
whether or not a host still holds the chat. Where no chat is listed the page MUST NOT draw the
list.

**3.8.24** The form of a new epic of a flow MUST be drawn in the frame of Section 3.8.21: the
heading `New epic`, or `Resume epic`, in the bar with the flow of Section 3.8.4 beside it; what the
flow is for and `Options` (Section 3.8.6) in the middle of the page; and the box of Section 3.8.5
docked at the foot, holding only the `Add` button of Section 3.6.6.16, what is typed and the button
that sends. The row under that box
MUST hold, at its left, `Environment` (Section 3.8.22) and the workspace control of Section
3.8.2.1, and at its right what is set (Section 3.8.7) and the button that opens `Options`.

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

**3.9.7** The page MUST NOT fetch a flowverse's index unasked: each daemon fetches every index once
as it starts (Section 3.9.8 of [DAEMON]).

**3.9.8** The page MUST refuse to install, update or uninstall a flow while an epic runs on the
machine.

### 3.10. Search

**3.10.1** `Search` MUST list every chat and every epic of the daemon shown, a page at a time, the
chats read with `chat.list` and the epics with `runs.list`, as one list, newest first; a chat found
MUST open at `#/chats/<id>`. Of a chat found it MUST say its workspace, its agent and what it
spent, and of an epic found MUST say its workspace, flow, agents, what it spent, how long it took, how many
sessions it opened, whether it can be resumed and where it is written down: of the one a key or the
pointer has moved to (Section 3.10.8), in a line between what was found and the foot, which MUST NOT
be drawn until then; and of each, under its own line, in a window the dialog fills or one whose
pointer cannot hover. Neither MUST cut it short.

**3.10.2** `Search` MUST let the user filter epics by how they went, by workspace, by flow and
by words of their task.

**3.10.3** `Search` MUST offer `Import`.

**3.10.4** `Search` MUST be a dialog over the middle of a wide window, 672 pixels wide and 584
tall where the window has the room, laid out top to bottom as: the search field with `Close` at its
right; a row of tabs; what was found; a foot. A window too narrow for that it MUST fill.

**3.10.5** The tabs MUST be `All`, `Chats` and `Epics`, in that order, each 29 pixels tall: `Chats`
MUST list only chats (`chat.list`) and `Epics` only epics (`runs.list`, which takes no `kind`). A
chat MUST NOT be listed under `Epics`, nor named an epic.

**3.10.6** The filters by how it went, by workspace and by flow MUST be one row under the tabs,
opened and closed by `Filters` at the right of the tabs, and open as `Search` opens where one of
them is set. `Chats` MUST NOT offer the filter by flow nor the filter by how it went, and MUST
drop the flow and the ending chosen, pressed or named by the address: a chat has neither. With
either set, `All` MUST list epics alone. The counts by how it went MUST be of the epics (Section
4.16.1.2 of [DAEMON]).

**3.10.7** Each epic found MUST be one line: its task, then quietly how it stands, its workspace and
when it began. How it stands MUST be said in the words its row in the sidebar says it in (Section
3.5.15 for a chat, which says nothing while it rests), there and wherever else `Search` says it.
What was found MUST stand under a quiet heading, `Recents` where nothing narrows the list and
`Results` otherwise, with which of how many are listed; under it MUST stand `Actions`: `New chat`
and `Import`, which MUST stay in sight however many were found.

**3.10.8** One line of what was found or of `Actions` MUST be the one moved to: the first as the
list is drawn, and the same one while the list is read again. <kbd>↑</kbd> and <kbd>↓</kbd> MUST
move it, going round at either end, wherever in the dialog they are pressed but in a menu of
choices; <kbd>Enter</kbd> in the field or on a tab MUST open it; the pointer over a line MUST move
to it. <kbd>←</kbd> and <kbd>→</kbd> MUST change the tab, and <kbd>/</kbd> open or close the
filters, while the field is empty.

**3.10.9** The foot MUST say what the keys do -- `Close`, `Change type`, `Filters`, `Actions`,
`Move`, `Open` -- and, at its right, offer the page before and after where there is more than one
page. A window the dialog fills MAY leave the keys unsaid, and a key the pages leave no room for
MUST be left unsaid whole, the last first.

**3.10.10** <kbd>Alt</kbd> and <kbd>Enter</kbd>, and the menu key, MUST open under the epic moved
to the menu of what can be done with it, the one a secondary click on its line opens, and the focus
MUST be the field's again as that menu closes.

**3.10.11** A tab, a filter by how it went, or a page turned with the pointer MUST leave the focus
where it was, so that the keys go on moving and opening.

**3.10.12** <kbd>Enter</kbd> pressed before what was typed has been listed MUST open the first of
what it finds, once listed, and MUST NOT open a line of what was listed before.

**3.10.13** The field MUST be named `Search`. It MUST name the one moved to to assistive technology
as a combobox names the option of its list, and that list MUST hold nothing but what can be moved
to and the groups it stands in.

**3.10.14** `Search` MUST NOT list an archived chat.

### 3.11. Settings

#### 3.11.1. Structure

**3.11.1.1** Settings MUST be a dialog with two groups of pages: `App` and `Daemon`.

**3.11.1.2** `App` MUST hold `Themes`, `Daemons` and `Notifications`, and MUST be the same whichever
daemon is shown.

**3.11.1.3** `Daemon` MUST hold `General`, `Accounts`, `Nous`, `Runtimes`, `Backup`, `Workspace`
and `Usage`, each of the daemon picked above them.

**3.11.1.4** The daemon picked for the `Daemon` pages MUST be the daemon shown until the user picks
another, MUST be part of the address, and picking it MUST change nothing else on the page.

#### 3.11.2. Daemon pages

**3.11.2.1** `General` MUST let the user set whether a turn's working is shown, `Harness
sessions`, whether the sidebar lists them (Section 3.5.21; off until set), `Ai-chan`, the nous a new
Ai-chan conversation defaults to (none until one is picked), and whether errors are reported, as
Section 14.3.2 of [CORE] and Section 12 of [CORE] specify.

**3.11.2.2** `Accounts` MUST list every account by its harness, way in and the names of the
variables it sets, and MUST let the user ask again what it runs, correct it, copy it to another
harness, remove it, and make one, as Section 5 of [CORE] specifies.

**3.11.2.3** Correcting an account MUST keep every value the user leaves blank, and MUST NOT show
any value.

**3.11.2.4** A way in that runs a harness's own sign-in MUST be shown as needing a terminal, and
MUST NOT be run from the page.

**3.11.2.5** The ways in through the local LiteLLM gateway MUST be grouped as the terminal interface
groups them, with the command that adds the `litellm` extra where it is missing.

**3.11.2.6** `Nous` MUST list every nous as Section 19.8.1 of [TUI] lists it, and MUST let the
user make, change, rename and remove one -- its name, tries, wait policy and limit, a virtual nous's
graph and every nous's `then` -- editing a graph's nodes, start node and edges as Section 19.8.3 of
[TUI] states, and refusing as Section 19.8.4 of [TUI] refuses, as Section 4.11.4 of [CORE]
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

**3.11.2.11.1** `Workspace` MUST list, under `Archived chats`, the archived chats of the workspace
picked (`chat.list` with `archived`), newest first, each by its title and when it was last
written, with `Unarchive`, which MUST put it back among the others (`chat.unarchive`) and take it
off this list, and `Delete`, which MUST open the dialog of Section 3.6.6.26. It MUST say so where
there is none.

**3.11.2.12** `Usage` MUST show what the epics spent by day and by flow, of every workspace or of
one, looking back 7, 30, 90 or 365 days.

**3.11.2.13** `General`, `Nous`, `Runtimes` and `Backup` MUST each offer `Batch apply`, which
writes what that page holds to every daemon the user ticks, and MUST say of each daemon whether it
applied or why it refused.

**3.11.2.14** `Batch apply` MUST NOT remove anything a daemon already has but what the page replaces
whole, and MUST NOT carry a value that only a secret sets; the page MUST say where such a value is
left out.

**3.11.2.15** `Accounts`, `Workspace` and `Usage` MUST NOT offer `Batch apply`.

#### 3.11.3. App pages

**3.11.3.1** `Themes` MUST let the user choose a theme as Section 3.12 specifies.

**3.11.3.2** `Daemons` MUST list Local and every remote daemon with its state, and MUST let the
user add, edit, connect and remove remote daemons, pair devices and revoke them, as Section 3.13
specifies.

**3.11.3.3** `Notifications` MUST let the user switch each kind of notification on and off --
`Done`, `Failed`, `Stopped`, `Questions` and `Waiting` -- and switch system notifications on and
off.

**3.11.3.4** In a browser, `Notifications` MUST offer `Allow`, and the page MUST ask the browser for
leave to show system notifications only when the user presses it.

**3.11.3.5** The App settings MUST be kept in the browser's storage alone, and MUST NOT be kept in
any daemon's settings.

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

**3.13.1** The page MUST keep the remote daemons in the browser's IndexedDB, each as Section 3.8.1
of [DAEMON] states -- its name, the daemon id it pins and its routes in order -- together with the
STUN and TURN servers it uses for WebRTC, and MUST NOT keep them in any daemon's settings.

**3.13.2** Local MUST NOT be removable or renamable, and a remote daemon MUST NOT be named `local`.

**3.13.3** The name of a remote daemon MUST start with a letter or a digit and MUST consist of
letters, digits, `.`, `_` and `-`.

**3.13.4** The `New daemon` form MUST offer three kinds: `Code`, `SSH` and `P2P`. `Code` MUST ask a
name and a pairing code, MUST claim the code at once over its routes as Section 4.5.7 of [WIRE]
states, and MUST keep the daemon only where the claim succeeds, saying why otherwise.

**3.13.5** `SSH` MUST offer two modes: `SSH Config`, which offers only a dropdown of the hosts of
Local's ssh config (`runtimes.hosts`, Section 4.18.4.4 of [DAEMON]) not yet added and writes the
daemon with the route `stdio:ssh://<Host>`; and `Custom`, which asks its name, host, user, port,
identity file, proxy jump and ssh options, as an ssh runtime is set up, and writes them as one
`stdio:ssh` route. `Custom` MUST let the user import a host of the ssh config into its fields,
filling them from what the ssh config resolves for that host. The page MUST NOT write to the ssh
config.

**3.13.6** `P2P` MUST offer `EasyTier` alone, and MUST ask its name, its secret, the secret masked,
and its nodes: the community's shared nodes (Section 3.8.5.8 of [DAEMON]), each with its name,
whether it is up and its uptime, to be checked, and nodes the user types; where that list cannot be
read, the form MUST say so with the reason and take typed nodes alone. It MUST write the EasyTier
entry of that name to Local (`easytier.set`, Section 4.18.5 of [DAEMON]) and keep the daemon with
the route `easytier:<name>`. For a new daemon it MUST also ask a pairing code, MUST refuse one that
is not a pairing code before it writes the entry, and MUST claim it at once as `Code` does (Section
3.13.4), over `easytier:<name>` and then the code's routes that are not `easytier:` routes, keeping
the daemon with the code's id and those routes, and only where the claim succeeds.

**3.13.7** A secret shorter than 16 bytes in UTF-8 MUST be refused with `A secret must be at least
16 bytes.`, and a form in which no node is checked or typed with `An EasyTier daemon needs at least
one node.`

**3.13.8** Editing a daemon MUST open the form in the kind and mode the daemon is in, and the page
MUST let the user edit the routes of any remote daemon, and their order.

**3.13.9** The page MUST NOT be given a secret once written; editing a P2P daemon with its secret
left empty MUST keep the secret written.

**3.13.10** Removing a remote daemon MUST ask for confirmation, and MUST forget only how to reach
it, leaving everything on that machine as it is.

**3.13.11** The page MUST NOT ask the user for a password or a host key; a remote daemon that needs
one MUST fail.

**3.13.12** The page MUST show one daemon at a time: the sidebar, a new epic, search, flows and the
`Daemon` settings pages MUST be of the daemon shown.

**3.13.13** The daemon bar MUST show the daemon shown, its host, whether it is reached, and how many
chats and epics are going on it, an Ai-chan conversation (Section 14 of [CORE]) not counted.

**3.13.14** A click on the daemon bar MUST open its menu: `Daemon`, which opens beside it every
daemon and its state; then `Settings` and `Usage`; and `Update` where a newer release of hmz is out.

**3.13.15** Picking a daemon in that menu MUST switch the page to it and, for a remote daemon, MUST
reach it; the menu MUST offer `Connect` on a remote daemon that failed and `Manage`, which opens
`Settings` › `Daemons`.

**3.13.16** The page MUST show each remote daemon's state as one of `idle`, `connecting`,
`installing`, `up` and `failed`, with what was said last, as Section 3.8.2 of [DAEMON] specifies.

**3.13.17** A remote daemon that is not `up` MUST be said to be unavailable where the page asks it
something, with its state.

**3.13.18** Wherever the page names a remote daemon's kind, it MUST say `SSH`, `P2P` or `Paired`
(Section 3.2.6 of [DAEMON]).

**3.13.19** The page MUST offer `SSH` and `P2P` only where its pipe provider can open their routes
(Section 4.9).

**3.13.20** `Settings` › `Daemons` MUST offer, for each daemon that is `up`, `Pair a device`, which
makes a pairing code (`pair.create`, Section 4.14.2 of [DAEMON]) and shows it with when it expires,
offering to copy it; and `Devices`, which lists the devices paired with that daemon and revokes one
after confirmation (`devices.*`, Section 4.14.3 of [DAEMON]).

### 3.14. Release notice

**3.14.1** Where a newer release of hmz is out than the one serving the page, as Section 13 of
[CORE] specifies, the page MUST mark the daemon bar and MUST offer `Update` in its menu.

**3.14.2** `Update` MUST copy the command `hmz update` for the user to run in a terminal, and MUST
NOT update anything itself.

### 3.15. Notifications

#### 3.15.1. Notices

**3.15.1.1** The page MUST follow the notices of Local and of every remote daemon while it is `up`,
as each daemon makes them (Section 4.19 of [DAEMON]), through `notices.subscribe`, resuming after
the last notice heard of that daemon: with `after` the `id` of that notice, which grows with each
notice (Section 4.19.1.2 of [DAEMON]), or, where none was heard, the `last` the first
`notices.subscribe` of that daemon answered.

**3.15.1.2** Each notice MUST name its workspace, its epic or -- of a chat, whose `epic` is empty --
its chat, its flow and its task, and, where it is a question, the role asking and the question.

#### 3.15.2. The notifications list

**3.15.2.1** The page MUST gather the notices of every daemon it follows into one list of
notifications kept in the browser's IndexedDB, each naming its daemon and whether it is read.

**3.15.2.2** The list MUST keep the newest 200 notifications.

**3.15.2.3** A notice of a kind the user switched off MUST NOT be kept, counted or shown; the page
MUST read that choice afresh for every notice.

**3.15.2.4** The bell MUST show how many notifications are unread, whichever daemon is shown.

**3.15.2.5** A click on the bell MUST open the list, newest first; a click on a notification MUST
open its epic on its daemon, or its chat, at `#/chats/<id>`; the user MUST be able to mark one or all read and to clear the list.

**3.15.2.6** Each new notification MUST also show as a card in a corner of the page that goes away
after a few seconds.

**3.15.2.7** The sidebar MUST mark each epic and each chat that has an unread notification, and each
folded workspace that holds one.

**3.15.2.8** Every notification of the epic or chat the page is on MUST be read while the user is on
it, and a new one of it MUST be read as it comes, without a card and without a system notification.

#### 3.15.3. System notifications

**3.15.3.1** While the page is hidden or not focused, and unless the user switched system
notifications off, the page MUST show each new notification as a system notification: in a browser
through the browser, once the browser allows it, and in the desktop app as Section 3.9 of [DESKTOP]
specifies.

**3.15.3.2** A click on a system notification MUST bring the page forward on the epic or chat it is
about.

### 3.16. Ai-chan

**3.16.1** Every view of the page MUST offer a button, drawn as Ai-chan's avatar, the file
`ai-chan/avatar.png` among the page's files (Section 4.5.3), that opens and closes the **Ai-chan
drawer** beside the view; the view of a chat MUST offer it as `Ai-chan` in `View options` (Section
3.6.6.19) in place of that button. The drawer MUST stay open, as it was, while the user goes from
view to view of one daemon, until it is closed.

**3.16.2** The drawer MUST list every Ai-chan conversation of the daemon shown (Section 4.22.3 of
[DAEMON]), newest first, each with its title, its scope, its nous, its preset, whether its network
is on, and whether a turn is open, it is between turns or it has folded away; and MUST offer `New`
and, on each conversation, `Forget`, which asks for confirmation and then calls `aichan.forget`.

**3.16.3** `New` MUST open a form in the drawer that asks for the scope -- `Daemon`, `Workspace` or
`Epic`, defaulting as Section 14.3.4 of [CORE] states to the epic, else the workspace, the view
shows --, the workspace and the epic the scope names, the nous (defaulting to the `ai_chan`
setting), the preset (`read-only` or `danger-full-access`, defaulting to `read-only`), `Network`
(off by default) and the task; Enter in the box for the task MUST make the conversation by
`aichan.create` and open it.

**3.16.4** Opening a conversation MUST draw it in the drawer as a chat (Section 8.8 of [CORE]),
attached to its slot by `epic.attach`, carrying it on where it has folded away (Section 14.8.5 of
[CORE]), with Ai-chan's answers beside her avatar and a box that says the next line to her.

**3.16.5** The drawer MUST show each tool Ai-chan calls, with the method and how it was answered,
on one line the user can open (Section 14.7.3 of [CORE]).

**3.16.6** While Ai-chan's turn is open, the drawer MUST offer `Stop`, which stops that turn
without asking for confirmation (Section 14.8.3 of [CORE]).

**3.16.7** On a screen as narrow as a phone's, the drawer MUST cover the view, and Escape and a
button MUST close it.

### 3.17. Environments

#### 3.17.1. The view

**3.17.1.1** The page MUST offer, for every epic a host holds, the Environments view of its envs, as
Section 7.13 of [CORE] specifies, at the address of the epic's host, `#/live?workspace=…&slot=…`,
with `envs/` before `live` and the query parameters `env`, the `id` of the env shown (Section
4.24.2 of [DAEMON]), and `tab`, the panel shown: `files`, `terminal` or `changes`.

**3.17.1.2** The view MUST list the envs of the snapshot `envs` as a tree: grouped by role, each
derived env under the env it was derived from, each named by its chain and marked where it is
closed or cannot be reached; choosing one MUST show it and put it in the address.

**3.17.1.3** Above the panels, the view MUST show the env's kind, provider, workdir and what its
probe found of its CPUs, memory and GPUs.

**3.17.1.4** The view MUST offer the panel `Files` where the env's `caps` holds `files`, `Terminal`
where it holds `shell`, and `Changes` where it holds `git` or `git_worktree`, and no other; it MUST
open on the panel of the address, else the first of `Files`, `Terminal` and `Changes`, in that
order, whose capability the env's `declared` also holds, else `Files`.

**3.17.1.5** The view MUST load a panel only when it is first shown; a panel that cannot be loaded
MUST say it is unavailable, and MUST NOT keep the others from working.

**3.17.1.6** The user MUST be able to resize the tree against the panels by dragging the border
between them; on a screen as narrow as a phone's, the tree MUST fold into a picker above the panels.

**3.17.1.7** An env that closes MUST stay shown with what was last read of it, MUST say it has
closed, and MUST offer nothing that changes it.

**3.17.1.8** The page MUST draw each `env_used` record (Section 4.9.2.4 of [DAEMON]) where it
draws the epic's history, as one dim line naming the frontend, what it did and the path.

#### 3.17.2. `Files`

**3.17.2.1** `Files` MUST show the env's workdir as a tree of its files that reads each directory
only when it is opened, and MUST mark in it the file being edited.

**3.17.2.2** The tree MUST let the user make a file or a directory, rename or move one, and delete
one after confirmation, from the menu of each entry (Section 3.4.4.1), which MUST also offer to copy
its path.

**3.17.2.3** Opening a file MUST show it in an editor tab that highlights its syntax by its name.
A file opened from the tree with a single click MUST replace the previous tab so opened while that
tab is unchanged and was not opened to keep; editing it, or opening it with a double click, MUST
keep it. A tab with changes not yet written MUST be marked.

**3.17.2.4** The editor MUST write a tab's changes to the env 800 milliseconds after the user stops
typing, when the editor loses focus, and when the user switches tab, each time as `env.write` with
`if_match` the `etag` last read or written; the user MUST NOT be asked to save.

**3.17.2.5** A write refused because the file changed MUST keep the user's text, and MUST show above
the editor a banner offering `Compare`, which shows both texts side by side, `Keep mine`, which
writes the user's text over the file, and `Reload`, which throws the user's text away and reads the
file.

**3.17.2.6** While the view is visible, the page MUST look at each open file at most every 5 seconds,
MUST read again, without saying so, a file changed in the env whose tab holds no changes, and MUST
show the banner of Section 3.17.2.5 for one whose tab does.

**3.17.2.7** Cmd+P, or Ctrl+P, MUST open a picker of the env's files (`env.find`) narrowed by a fuzzy
match of what is typed; Cmd+Shift+F, or Ctrl+Shift+F, MUST open a search of the env's files
(`env.search`) whose results open the file at the line found.

**3.17.2.8** The editor MUST offer find and replace within the file and going to a line, and a
status bar saying the line and column, the language, and whether the tab is written.

**3.17.2.9** An image MUST be shown as one; a binary file, and a file larger than 5 MiB, MUST open
read-only, saying why.

#### 3.17.3. `Terminal`

**3.17.3.1** `Terminal` MUST offer several terminals of the env, each in a tab, and MUST let the
user open a new one (`env.term.open`) and close one, which kills it (`env.term.close`).

**3.17.3.2** Shown, `Terminal` MUST attach again to every terminal of the env still alive
(`env.term.list`), drawing what each kept before what it prints next; and so MUST it once the page's
session is up again after it dropped.

**3.17.3.3** A terminal MUST fill its panel, MUST be resized with it (`env.term.resize`), MUST be
drawn in the colours of the page's theme, and MUST offer search within what it shows, links that
open, and copying and pasting.

**3.17.3.4** The page MUST acknowledge a terminal's output (`env.term.ack`) only once it has drawn
it, at least every 64 KiB drawn.

**3.17.3.5** A terminal that ended MUST say so with its exit status, and MUST take no more input.

#### 3.17.4. `Changes`

**3.17.4.1** `Changes` MUST show the env's git status (`env.git.status`) in the groups `Merge
Changes` (conflicts), `Staged Changes`, `Changes` and `Untracked`, each with how many files it holds,
and MUST show the branch and how far it is ahead of and behind its upstream.

**3.17.4.2** Each file MUST offer to stage it, unstage it, discard its changes after confirmation,
and open it in `Files`; each group MUST offer to stage or unstage all of it.

**3.17.4.3** `Changes` MUST offer a box for a commit message, which Cmd+Enter, or Ctrl+Enter,
commits (`env.git.commit`), and a choice to amend the last commit.

**3.17.4.4** Choosing a file MUST show its change (`env.git.diff`), read-only, side by side or
inline as the user chooses, with a way to go to the next and the previous change.

**3.17.4.5** `Changes` MUST list the latest commits (`env.git.log`).

**3.17.4.6** Where the env's `caps` holds `rewind`, `Changes` MUST list its snapshots
(`env.git.snapshots`), and MUST offer to rewind to each after confirmation (`env.git.rewind`).

**3.17.4.7** `Changes` MUST read the status again on an `env_used` record of its env, when a turn of
a session ends, when the page regains focus, and every 5 seconds while it is visible.

## 4. The Server

### 4.1. Scope

Section 4 governs the HTTP server `hmz web` runs: where it listens, how a browser is admitted, the
page's files it serves, `/here`, the WebSocket bridge `/rpc` to the daemon of this machine, and the
WebSocket `/dial` through which the page reaches the daemons of other machines over carriers a
browser cannot open; and how the page chooses among them. Every path the server serves is listed in
this section; a method and path not listed here is not served.

Out of scope:

- The `hmz web` command line, its options and exit statuses: [CLI].
- The page itself, its views and what it draws: Section 3.
- Carriers, routes, sessions, frames and the RPC session the page speaks over `/rpc` and `/dial`:
  [WIRE].
- Every method the page calls, its parameters, results and refusals: Section 4 of [DAEMON].
- Installing hmz on the machine of a `stdio:ssh` route: Section 3.8.3 of [DAEMON].

### 4.2. Terminology

**4.2.1** Every term of Section 2 of [CORE] and of [WIRE] MUST carry the meaning given there.

**4.2.2** **Server**: one process of `hmz web` answering HTTP.

**4.2.3** **Key**: the secret text the server makes when it starts and prints in its address.

**4.2.4** **Address**: the text `http://127.0.0.1:<port>/?key=<key>` the server prints.

**4.2.5** **Admission cookie**: the cookie named `hmz-<port>` whose value is the key.

**4.2.6** **Admitted request**: a request to `/here`, `/rpc` or `/dial`.

**4.2.7** **Pipe provider**: what gives the page a carrier to one daemon: the server's `/rpc` or
`/dial`, the browser's WebRTC, or the pipes of the desktop application (Section 3.12 of [DESKTOP]).

**4.2.8** **Refusal**: an answer whose status is 400 or above, whose body is a JSON object carrying
`error`, one sentence saying why.

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

**4.3.5** The server MUST close an HTTP connection that sends nothing for 60 seconds, and MUST NOT
close a WebSocket of `/rpc` or `/dial` for being quiet.

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

**4.4.5** An admitted request without the admission cookie MUST be refused 401, `Open the address
hmz web printed to let this browser in.`

**4.4.6** An admitted request MUST be refused 403, `Use this server's own page to make this
request.`, where it carries `Sec-Fetch-Site` with a value other than `same-origin`, or carries no
`Sec-Fetch-Site` and an `Origin` whose scheme is not `http` or whose host and port differ from its
`Host`.

**4.4.7** A request whose method is not `GET` MUST be refused 405, `Only the page's own files are
here.`

**4.4.8** The page's own files MUST be served without the admission cookie.

**4.4.9** A request to `/rpc` or `/dial` that is not a WebSocket upgrade [RFC6455] MUST be refused
400, `Open this as a WebSocket.`

### 4.5. Answers and the page's files

**4.5.1** Every answer MUST carry `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`
and `X-Frame-Options: DENY`, but `faces/frame.html`, which MUST carry `X-Frame-Options: SAMEORIGIN`
(Section 4.5.8).

**4.5.2** A refusal MUST carry `{"error": "<sentence>"}`, `application/json; charset=utf-8`.

**4.5.3** `GET /` MUST serve `index.html`, and `GET /<path>` the file of that path among the page's
files, with the media type of its extension (`.html`, `.js`, `.css`, `.svg`, `.png`, `.json`).

**4.5.4** A path whose components are not each one or more letters, digits, `_` or `-`, whose last
component lacks one extension of lowercase letters or digits, or that is longer than 200 characters,
MUST be refused 404, as MUST a path naming no file.

**4.5.5** An HTML file but `faces/frame.html` MUST be served with `Content-Security-Policy:
default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self';
connect-src 'self' ws: wss:; frame-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action
'self'`, and with `Cache-Control: no-cache`: `'self'` lets the page reach the server's own `/rpc`
and `/dial`, and frame `faces/frame.html`, `ws:` and `wss:` the relay of any `webrtc:` route, whose
host the server cannot know, and `'unsafe-inline'` in `style-src` the editor and the terminal of
Section 3.17 style what they draw.

**4.5.6** A failure the server does not anticipate MUST be refused 500, `Something went wrong here:
<why>`, and its traceback written to the server's standard error.

**4.5.7** The page's files MUST include, under `vendor/`, `codemirror.js`, the editor of Section
3.17.2; `xterm.js` with `xterm_css.css`, the terminal of Section 3.17.3; `markdown.js`, exporting
`render(markdown)`, which answers the HTML of the Markdown made safe to put into the page; and
`vega.js`, exporting `embed(element, spec, {theme})`, which draws a Vega-Lite chart into `element`
interpreting its expressions without `eval`: each built from pinned releases of those libraries into
one file the page imports, served as every other file is, and reaching nothing beyond the page's
files.

**4.5.8** `faces/frame.html`, the document a face runs in (Section 3.6.11), MUST be served with
`Content-Security-Policy: default-src 'none'; script-src 'unsafe-inline' 'self'; style-src
'unsafe-inline' 'self'; img-src data: blob:; font-src data:; connect-src 'none'; frame-ancestors
'self'`, and with `Cache-Control: no-cache`: a face reaches no network, and `'self'` lets it load
`faces/bridge.js` and import the page's files under `vendor/`. The file MUST also say that policy,
but `frame-ancestors`, in a `<meta http-equiv="Content-Security-Policy">` of its own, for a server
that gives every page one policy (Section 3.12.9 of [DESKTOP]).

**4.5.9** A file under `vendor/` asked for with `Origin: null` MUST be served with
`Access-Control-Allow-Origin: null`, so that a face, whose origin is opaque, can import it; those
files hold nothing of the user's. No other answer MUST carry `Access-Control-Allow-Origin`.

### 4.6. `/here`

**4.6.1** `GET /here` MUST answer `{"here": "<the directory the server started in>"}`, with
`Cache-Control: no-store`.

### 4.7. `/rpc`

**4.7.1** `GET /rpc` MUST open a WebSocket and a connection to the socket of this machine's daemon,
starting it where none runs (Section 3.4 of [DAEMON]), and MUST carry every binary message of the
WebSocket to the socket as bytes, and every byte of the socket to the WebSocket in binary messages,
unchanged and in order.

**4.7.2** The WebSocket and the connection MUST each be closed when the other closes; a text message
on the WebSocket MUST close both.

**4.7.3** The session over `/rpc` MUST be trusted, as one over the socket is (Section 3.5 of
[WIRE]).

**4.7.4** Where the daemon cannot be reached, the server MUST close the WebSocket with the code 1011
and the reason `The daemon cannot be reached: <why>`, cut to 120 bytes.

### 4.8. `/dial`

**4.8.1** `GET /dial` MUST take the query parameters `route`, a route of [WIRE], and `id`, the
daemon id the page pins, and MUST open a WebSocket.

**4.8.2** The server MUST refuse, by closing the WebSocket with the code 1008 and a reason of one
sentence, a `route` that is not a route, a `unix:`, `stdio:local` or `webrtc:` route, and an
untrusted route without `id`, the last with `<route> needs the id of the daemon it reaches.`
(Section 3.5.6 of [WIRE]).

**4.8.3** The server MUST open the carrier the route names as Section 3.4 of [WIRE] states, and,
where it is untrusted, MUST open mutual TLS over it as this machine's device (Section 4.4 of
[WIRE]), pinning `id`.

**4.8.4** Until the carrier is open, the server MUST send the page text messages
`{"state": <state>, "detail": <what was said last>}`, `state` one of `connecting`, `installing`,
`up` and `failed` of Section 3.8.2.2 of [DAEMON], `up` once the carrier is open and `failed` before
it closes the WebSocket for a carrier that did not open.

**4.8.5** From `up` on, the server MUST carry every binary message of the WebSocket to the carrier
as bytes, inside its mutual TLS where there is one, and every byte the carrier carries back to the
WebSocket in binary messages, unchanged and in order; the WebSocket and the carrier MUST each be
closed when the other closes, and a text message from the page MUST close both.

**4.8.6** The server MUST stop the `ssh`, `wsl.exe` and EasyTier processes it started for a
`/dial` once that WebSocket has closed and no other `/dial` of the same route is open.

**4.8.7** An `easytier:` route MUST be opened with the EasyTier entry of that name in the settings
of this machine (Section 3.4.10 of [FILES]), which the page writes through Local's `easytier.set`.

### 4.9. Pipe providers

**4.9.1** The page served by the server MUST keep Local as the route `unix:` and reach it through
`/rpc`, the routes `stdio:ssh`, `stdio:wsl`, `tcp`, `ws`, `wss`, `easytier` and `relay` through
`/dial`, and `webrtc` through the browser's own WebRTC (Section 4.7 of [WIRE]).

**4.9.2** The page shown by the desktop application MUST reach every daemon through the
application's pipes (Section 3.12 of [DESKTOP]), and `webrtc` routes through the web view's own
WebRTC; it MUST keep Local as the route `stdio:local` on macOS and `stdio:wsl` on Windows (Section
3.5 of [DESKTOP]).

**4.9.3** The page MUST speak one RPC session per daemon it reaches, over whichever pipe provider,
as [WIRE] states: racing the routes, pinning the daemon id, saying `session.hello` with `kind` `web`
or `desktop`, and attaching again with `since` after a reconnection; it MUST say a route it has no
provider for as Section 3.3.2 of [WIRE] states, a route not open in time as Section 3.4.9 of [WIRE]
states, and a daemon with no route as Section 3.6.3 of [WIRE] states.

**4.9.4** The page MUST check that the `daemon_id` `session.hello` answers over `/dial` is the id it
pins, and MUST close the session where it is not.

## 5. Security Considerations

This section summarises the security-relevant properties this document states. It adds no
requirement.

- **Where the server listens.** The server listens on the loopback addresses alone (Section 4.3.1)
  and refuses a connection that does not come from one (Section 4.4.2). It does not check the `Host`
  a request names, so whatever forwards or proxies a port to it from this machine is admitted as a
  local browser is (Section 4.4.3); what then guards it is the key.
- **The key and the admission cookie.** The key is 32 random bytes made afresh at each start,
  appears only in the printed address and in a file readable only by the current user, and is never
  passed on a command line (Section 4.3.3 and Section 4.3.4). A browser exchanges it for an
  `HttpOnly`, `SameSite=Strict` cookie (Section 4.4.4), without which `/here`, `/rpc` and `/dial`
  are refused (Section 4.4.5). The page's own files are served without the cookie (Section 4.4.8).
  A page without the cookie shows no view (Section 3.3.3).
- **Origin checks.** A WebSocket or a request from another site is refused: the server admits only
  what the browser states comes from the server's own page (Section 4.4.6), which keeps another
  site from opening `/rpc` with the cookie the browser holds. Every answer forbids framing and
  content sniffing, and the page's HTML carries a content security policy that admits only the
  server's own scripts, styles and connections, and inline styles, which the editor and the terminal
  need and which run no script (Section 4.5.1 and Section 4.5.5); those libraries are the page's own
  files, so nothing is loaded from elsewhere (Section 4.5.7).
- **Faces.** A face is HTML a flow wrote, run in a sandboxed frame of an opaque origin that holds no
  cookie, reaches neither `/rpc` nor any network, and talks to the page only over one channel,
  through which it is handed its session's questions and blocks and can do no more than answer the
  question it holds (Section 3.6.11 and Section 4.5.8).
  What a face submits is validated by the host as any other answer is (Section 4.8.4 of
  [DAEMON]). Markdown is made safe before it is drawn, and a chart runs no `eval` (Section 4.5.7).
- **Environments.** The page reads and writes the files of an epic's envs and opens terminals in
  them as the daemon's user (Section 3.17); every change and every terminal opened is written in the
  epic's history (Section 4.24.1.8 of [DAEMON]).
- **The bridge.** `/rpc` is the daemon's own socket carried to the page, and is trusted as the
  socket is (Section 4.7.3): admission to the server is therefore equivalent to acting as the user
  who runs `hmz web` on this machine, with every method of [DAEMON], as it was before this version.
- **Dialing.** `/dial` opens ssh, WSL, TCP, WebSocket, EasyTier and relay carriers from this machine
  for the page (Section 4.8.3), runs `ssh` and EasyTier as this user, and secures untrusted carriers
  with this machine's device certificate, pinning the id the page gives (Section 4.8.3). It refuses
  `unix:` and `stdio:local`, which `/rpc` covers (Section 4.8.2). Whoever is admitted thereby acts
  as this machine's device on every daemon that device is paired with.
- **Secrets.** The page shows no secret: accounts by their names, URLs without credentials, and an
  EasyTier secret only as whether one is written (Section 3.3.6, Section 3.3.7, Section 3.11.2.3 and
  Section 3.13.9); the daemon answers none (Section 5 of [DAEMON]). The page never asks for a
  password or a host key (Section 3.13.11). A pairing code is a secret until it is claimed, and the
  page claims it at once (Section 3.13.4).
- **Browser storage.** The remote daemons, the notifications and the page's own settings are kept in
  the browser's storage for the server's origin (Section 3.13.1 and Section 3.15.2.1), which any
  page of that origin can read; the page's WebRTC certificate is kept there too (Section 4.7.2 of
  [WIRE]), so that whoever can read that storage can act as this browser on the daemons it paired
  with.
- **Failures.** An unanticipated failure is answered with its reason in one sentence and its
  traceback goes to the server's standard error, not into the answer (Section 4.5.6).

## 6. References

### 6.1. Normative References

- **[RFC2119]** Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels", BCP 14, RFC
  2119, March 1997, <https://www.rfc-editor.org/info/rfc2119>.
- **[RFC8174]** Leiba, B., "Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words", BCP 14, RFC
  8174, May 2017, <https://www.rfc-editor.org/info/rfc8174>.
- **[RFC6455]** Fette, I. and A. Melnikov, "The WebSocket Protocol", RFC 6455, December 2011,
  <https://www.rfc-editor.org/info/rfc6455>.
- **[CORE]** "The Humanize Protocol: Core Concepts and Functional Behaviour", [`core.md`](core.md).
- **[CLI]** "The Humanize Protocol: Command-Line Interface", [`cli.md`](cli.md).
- **[TUI]** "The Humanize Protocol: Terminal Interface", [`tui.md`](tui.md).
- **[DAEMON]** "The Humanize Protocol: Daemon", [`daemon.md`](daemon.md).
- **[WIRE]** "The Humanize Protocol: Carriers, Sessions and RPC", [`wire.md`](wire.md).
- **[DESKTOP]** "The Humanize Protocol: Desktop Application", [`desktop.md`](desktop.md).
- **[PYTHON]** "The Humanize Protocol: Python Interfaces", [`python.md`](python.md).
- **[FILES]** "The Humanize Protocol: Settings, Environment Variables and Files", [`files.md`](files.md).

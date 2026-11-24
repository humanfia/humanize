# The Humanize Protocol: Terminal Interface

## Abstract

This document specifies the terminal interface of hmz: what it draws, every command and key it
accepts, and what each of them does.

## Status of This Document

This document is one of the documents of the Humanize Protocol, which Section 2.2.4 of [CORE] lists.
It is normative. It is cited by the tag [TUI].

## Table of Contents

- [1. Introduction](#1-introduction)
- [2. Terminology](#2-terminology)
- [3. Launch](#3-launch)
- [4. The log screen](#4-the-log-screen)
- [5. Views](#5-views)
- [6. Input](#6-input)
- [7. Commands](#7-commands)
  - [7.9. `/flow [flow] [task]`](#79-flow-flow-task)
  - [7.10. `/btw [question]`](#710-btw-question)
  - [7.11. `/epics [@daemon]`](#711-epics-daemon)
  - [7.12. `/resume`](#712-resume)
  - [7.13. `/settings [page]`](#713-settings-page)
  - [7.14. `/clear`](#714-clear)
  - [7.15. `/afk [on|off]`](#715-afk-onoff)
  - [7.16. `/claim [on|off]`](#716-claim-onoff)
  - [7.17. `/stop`](#717-stop)
  - [7.18. `/exit`](#718-exit)
  - [7.19. `/ai`](#719-ai)
  - [7.20. `/env [role]`](#720-env-role)
  - [7.21. `/chat`](#721-chat)
  - [7.22. `/prefer [native|flow]`](#722-prefer-nativeflow)
- [8. `$` lines](#8--lines)
- [9. Saying something](#9-saying-something)
- [10. Questions](#10-questions)
- [11. Chat](#11-chat)
- [12. Btw mode](#12-btw-mode)
- [13. Status line](#13-status-line)
- [14. `ctrl+c` and `ctrl+q`](#14-ctrlc-and-ctrlq)
- [15. Menus](#15-menus)
  - [15.1. Layout](#151-layout)
  - [15.2. Keys and mouse](#152-keys-and-mouse)
  - [15.3. Held changes](#153-held-changes)
  - [15.4. Paths](#154-paths)
- [16. `/flow`](#16-flow)
  - [16.1. Pages](#161-pages)
  - [16.2. Installed](#162-installed)
  - [16.3. Flowverses](#163-flowverses)
  - [16.4. Roles](#164-roles)
  - [16.5. Agent sheet](#165-agent-sheet)
  - [16.6. Environment form](#166-environment-form)
  - [16.7. Params and budget](#167-params-and-budget)
- [17. `/epics`](#17-epics)
  - [17.1. The list](#171-the-list)
  - [17.2. One epic](#172-one-epic)
  - [17.3. Another daemon's epics](#173-another-daemons-epics)
- [18. `/resume`](#18-resume)
- [19. `/settings`](#19-settings)
  - [19.1. Landing screen](#191-landing-screen)
  - [19.2. General](#192-general)
  - [19.3. Details](#193-details)
  - [19.4. Notifications](#194-notifications)
  - [19.5. Daemons](#195-daemons)
  - [19.6. Accounts](#196-accounts)
  - [19.7. Account form](#197-account-form)
  - [19.8. Nous](#198-nous)
  - [19.9. Runtimes](#199-runtimes)
  - [19.10. Backup](#1910-backup)
  - [19.11. Workspace](#1911-workspace)
  - [19.12. Usage](#1912-usage)
  - [19.13. First start](#1913-first-start)
- [20. Monitor](#20-monitor)
  - [20.1. Reaching it](#201-reaching-it)
  - [20.2. Nodes](#202-nodes)
  - [20.3. Epic page](#203-epic-page)
  - [20.4. Board](#204-board)
  - [20.5. Exomyth from the monitor](#205-exomyth-from-the-monitor)
- [21. Exomyth](#21-exomyth)
- [22. Completion and history](#22-completion-and-history)
- [23. Selecting and copying](#23-selecting-and-copying)
- [24. Keys](#24-keys)
- [25. Zones and views](#25-zones-and-views)
  - [25.1. Zones](#251-zones)
  - [25.2. The hint line](#252-the-hint-line)
  - [25.3. Colour and drawing](#253-colour-and-drawing)
  - [25.4. Order and removal](#254-order-and-removal)
  - [25.5. Texts](#255-texts)
- [26. Keys view](#26-keys-view)
- [27. Navigator and Search](#27-navigator-and-search)
- [28. New chat and the chat's chips](#28-new-chat-and-the-chats-chips)
  - [28.1. Chips](#281-chips)
  - [28.2. New chat](#282-new-chat)
  - [28.3. Details](#283-details)
  - [28.4. Harness session](#284-harness-session)
- [29. New epic and the epic's context](#29-new-epic-and-the-epics-context)
- [30. Environment panes](#30-environment-panes)
  - [30.1. The panes](#301-the-panes)
  - [30.2. Files](#302-files)
  - [30.3. Changes](#303-changes)
  - [30.4. Terminal](#304-terminal)
- [31. Flows page and transfers](#31-flows-page-and-transfers)
- [32. Settings: App and Daemon](#32-settings-app-and-daemon)
  - [32.1. Groups](#321-groups)
  - [32.2. Themes](#322-themes)
  - [32.3. Language](#323-language)
  - [32.4. Telling the system](#324-telling-the-system)
  - [32.5. What is kept](#325-what-is-kept)
- [33. Monitor, Exomyth and sheets in humanfia](#33-monitor-exomyth-and-sheets-in-humanfia)
- [34. Security Considerations](#34-security-considerations)
- [35. References](#35-references)
  - [35.1. Normative References](#351-normative-references)

## 1. Introduction

This document defines the terminal interface: the **frontend** that `hmz` opens when it is run with
no command. It states every screen, the prompt, every `/` command, `$` lines, the menus and sheets,
the monitor, the settings pages, the update notices and every key, as the **user** sees and uses
them. The terminal interface runs **flows** and reads **epics** back; it defines no flow and drives
no **agent** itself.

This document does not define the following, each of which the document cited defines:

- The command line that opens the interface and where its epics are held: Section 6 of [CLI].
- What each setting means and where it is stored: Section 3 of [FILES].
- A chat's behaviour common to every frontend, its native input included: Section 8 of [CORE].
- Side questions' behaviour common to every frontend: Section 9 of [CORE].
- Ai-chan's behaviour common to every frontend: Section 14 of [CORE].
- Agents, harnesses, models and efforts: Section 4 of [CORE].
- Accounts and nous: Sections 4 and 5 of [CORE].
- Placements and runtimes: Section 6 of [CORE].
- Environments: Section 7 of [CORE].
- Epics, export, import and resuming: Section 3 of [CORE].
- Monitoring figures, notices and Exomyth's layout: Section 10 of [CORE].
- Backups: Section 11 of [CORE].
- Error reporting: Section 12 of [CORE].
- Update checks for hmz and flows: Section 13 of [CORE].
- Daemons of other machines: Section 3 of [DAEMON].
- The web interface: Section 3 of [WEB].

The key words "MUST", "MUST NOT" and "MAY" in this document are to be interpreted as described in
BCP 14 [RFC2119] [RFC8174] when, and only when, they appear in all capitals, as shown here.

The conventions for numbering and citation, and every term of the shared glossary, are those of
Section 2 of [CORE].

## 2. Terminology

**2.1** **Interface**: the terminal interface.

**2.2** **Log screen**: the interface's main screen: the opening box, the transcript, the lines
above the editor, the editor and the status line.

**2.3** **Transcript**: the scrolling record of lines that the log screen shows for one view.

**2.4** **View**: one transcript the interface keeps: the **home view**, an **agent view**, a
**session view**, or an **outworlder view**.

**2.5** **Home view**: the interface's own transcript, which holds the opening box, commands and
their answers, and no line of any agent.

**2.6** **Agent view**: the transcript of every **session** of one agent of the epic.

**2.7** **Session view**: the transcript of one session, named `<agent>/<n>`, where `<agent>` is the
agent's own name and `<n>` counts that agent's sessions from 1 in opening order.

**2.8** **Outworlder view**: the transcript of what the flow asks through one outworlder role and
the answers given.

**2.9** **Outworlder**: a role of a flow that the user fills (Section 3 of [PYTHON]).

**2.10** **Round**: the ordered set of views that `shift+tab` and `tab` step through.

**2.11** **Editor**: the multi-line input at the bottom of the log screen and of the monitor, headed
by the prompt `❯`.

**2.12** **Offer list**: the list of completions drawn above the editor.

**2.13** **Status line**: the line under the editor.

**2.14** **Monitor**: the screen that draws the epic going as a graph or a list of nodes, over an
editor of its own.

**2.15** **Menu**: a screen of its own drawn as Section 15 states: `/flow`, `/epics`, `/settings`,
`/ai`, every sheet opened from them, and every page opened from the monitor.

**2.16** **Sheet**: a menu that sets up one thing: an agent, an environment, params, a budget, a
form.

**2.17** **Form**: a sheet whose rows are questions answered in order, closed by a **Done** button.

**2.18** **Box**: a question drawn in the middle of the screen over what is there, answered by its
buttons.

**2.19** **Row**: one selectable line of a menu's list.

**2.20** **Written row**: a row whose value the user types.

**2.21** **Dropdown**: the list of every value a row takes, dropped under that row.

**2.22** **Held change**: a change a menu keeps without applying it until it is saved.

**2.23** **Frontend name**: the name by which other frontends see this interface: the value of
`HUMANIZE_NAME`, else the login name, else `somebody`, followed by `@tui`, and followed by `#2`,
`#3` and onward where another frontend of the same epic has the same name.

**2.24** **Idle**: the state in which no epic is going or stopping on the host this interface
follows.

**2.25** **Chat**: a chat (Section 8 of [CORE]), which is not an epic; its **id** is the name the
daemon lists it by (`chat.list`, Section 4.25 of [DAEMON]). The interface MUST NOT call a chat an
epic.

**2.26** **In the background**: said of work the interface does while it goes on drawing and
taking input, neither of which waits for that work.

## 3. Launch

**3.1** The interface MUST open on a new chat, its assistant the chat agent remembered for the
working directory (Section 8.3.8 of [CORE]) or, where none is remembered, as Section 16.5.4 fills
it.

**3.2** The interface MUST open set up, so that a line typed is enough to start the chat, and with
the flow remembered for the working directory set up for `/flow` and `$` lines, each agent role as
remembered for the flow or, where nothing is remembered, as Section 16.5.4 fills it.

**3.3** The interface MUST draw in the first of these themes that applies: the one `TEXTUAL_THEME`
names, where it names an available one; `terminal`, where `NO_COLOR` is set and non-empty; the one
kept by Settings (Section 32); `humanfia-light`, where `COLORFGBG` says the terminal's background is
white; `humanfia-dark` (Section 25.3). It MUST NOT query the terminal for its colours, and MUST draw
failures in red and warnings in yellow or gold.

**3.4** The interface MUST offer no command palette other than the views of Section 25 and the
Search page of Section 27.

**3.5** As it opens, the interface MUST, in the background and without delaying input:

1. ask the harness machine's own sign-in of each installed harness for its models, where that model
   list was never fetched or is older than 7 days, reporting a failure only in its log;
2. fetch every flowverse index that has a URL and no local edits, one at a time, the `official` one
   included where it was never fetched, installing nothing;
3. look for an epic of this directory that `/resume` can pick up;
4. refresh the price list where it is older than 24 hours, at most once an hour;
5. ask which release of hmz is newest, where the answer kept is older than 24 hours;
6. ask the error-reporting question of Section 19.13 where it is unanswered.

**3.6** Where the flowverse indexes list a newer release of any installed flow, the interface MUST
say once in the transcript, dim, which flows have a newer release and that they are updated from
`/flow`, and MUST show the count of such flows at the front of the status line until none is left.

**3.7** Where a newer release of hmz exists than the one running, the interface MUST say once in the
transcript, dim, which release it is and that `hmz update` updates to it.

**3.8** The interface MUST NOT wait for a harness or for the network before it draws a screen, and
MUST go on drawing and taking input while it asks harnesses, fetches, imports or exports.

**3.9** The interface MUST NOT install, update or uninstall a flow while an epic is going.

## 4. The log screen

**4.1** The log screen MUST show, from top to bottom: an opening box naming hmz and its version; the
transcript of the view read; the lines waiting to be delivered at the left and the agent lines,
outworlder lines and cost readout at the right; the editor between two rules; the status line.

**4.2** The transcript MUST follow its end until the user scrolls up, and MUST follow it again once
the user scrolls back to the bottom.

**4.3** The editor MUST hold the focus on the log screen at all times, and MUST grow to at most 10
rows.

**4.4** The interface MUST show one agent line per agent role, right-aligned above the editor: the
agent's name, its harness, model and effort, its account where it is not the local one, how many
sessions it holds with a mark where one has a turn open, and `reading` where it is the view read or
`unread` where it has unread lines.

**4.5** While an epic is going, the interface MUST show one outworlder line per outworlder role: its
role, whose it is where it is claimed, whether it is away, whether it is asking, and `reading` or
`unread`.

**4.6** Where no agent role can be set up, the interface MUST say `no agent available` in place of
the agent lines.

**4.7** Once the epic has spent any tokens, the interface MUST show a cost readout of two lines: the
tokens of each kind, in a fixed order, each figure that is only a floor marked `+`; then the money
spent where any model is priced, marked `+` where some models are not priced, and the output tokens
per second over the last 300 seconds.

**4.8** The interface MUST NOT show the tokens of an epic as one total over the kinds where the
kinds are known.

**4.9** Each line of a turn MUST be drawn as follows: what the agent says with a green bullet; that
an agent is working, dim; a notice or a question with a yellow bullet; a failed turn in red; the
time a turn took, dim; and, only where details are on (Section 19.3), each tool call, the thinking,
each sub-agent started or done, and the harness's output.

**4.10** The interface MUST say once per agent per epic where that agent's harness runs: here, on
its environment's machine, or on a named runtime (Section 6 of [CORE]).

**4.11** The interface MUST say when an epic ends: done, failed with why, stopped by its budget with
why, or stopped by the user, naming the frontend that stopped it where another did.

**4.12** Before the first turn of an epic whose cost limit no agent's price can enforce, the
interface MUST warn, in yellow, which models no price list prices.

**4.13** The interface MUST call every agent by its own name, from the moment the epic names it, and
MUST say the role it fills only after that name.

## 5. Views

**5.1** The interface MUST keep one view per agent, one per session, one per outworlder and the home
view, and MUST NOT keep a view that every agent's lines appear on.

**5.2** A session's line MUST be written to its session view and its agent view.

**5.3** An outworlder's line MUST be written to its outworlder view, and also to the view read where
the line is part of no session.

**5.4** A line the interface itself writes MUST be written to the view read only.

**5.5** Switching view MUST redraw the transcript from its first kept line under a header naming the
view.

**5.6** When an epic starts, the interface MUST read the home view, and MUST say the previous view's
epic has gone where another view was read.

**5.7** When the epic opens its first session while the home view is read, the interface MUST read
that session's agent view.

**5.8** A view other than the one read MUST be marked unread when a line is written to it.

**5.9** The interface MUST keep at most 32 transcripts of at most 2 000 lines each, dropping the
oldest first, session views before others, and MUST NOT drop the home view, the view read or the
view just opened.

**5.10** A new epic MUST discard every session view of the previous epic.

**5.11** The round MUST hold every session with a turn open, in the order first seen, then every
outworlder of the epic going.

**5.12** `shift+tab` MUST read the next view of the round and `tab` the previous one, wrapping at
the ends.

**5.13** Outside an epic going, the round MUST be empty and `shift+tab` and `tab` MUST do nothing.

**5.14** A session that has ended MUST leave the round and MUST stay readable from the monitor.

## 6. Input

**6.1** The interface MUST strip a sent line, record it in the history (Section 22), and dispatch it
in this order:

1. a line not starting with `/` while btw mode is on is a side question (Section 12);
2. a line starting with `/` that names a command of Section 7.1 is that command (Section 7);
3. in a chat on the screen, a line starting with `$`, `/`, `!` or `@` is served as Section 8.9 of
   [CORE] states, a `$` line that names a flow starting it as Section 8 states;
4. a `$` line (Section 8) while no question is answerable here starts a flow;
5. any other line starting with `/` is a command (Section 7);
6. any other line is said (Section 9), to the chat where the chat is on the screen.

**6.2** A blank line MUST NOT be sent.

## 7. Commands

**7.1** The interface MUST offer exactly these commands: `/flow`, `/btw`, `/epics`, `/resume`,
`/settings`, `/clear`, `/afk`, `/claim`, `/stop`, `/exit`, `/quit`, `/ai`, `/env`, `/chat`, `/prefer`.

**7.2** The interface MUST echo a command line as typed, MUST split its arguments as a POSIX shell
splits words, and MUST refuse a line it cannot split, saying why.

**7.3** The interface MUST refuse an unknown command, naming it.

**7.4** The interface MUST refuse a command in a view where it does not work, naming the views where
it works.

**7.5** The interface MUST refuse a command in a state where it would do nothing, saying why.

**7.6** The interface MUST offer in the offer list only the commands that work in the view read and
are not refused now, alphabetically, each with what it does now.

**7.7** Which commands the interface offers and refuses, and what each says it does, MUST follow
every change of the view, of the epic and of the question waiting.

**7.8** A refused command and `/stop` MUST reset the `ctrl+c` count (Section 14).

### 7.9. `/flow [flow] [task]`

**7.9.1** `/flow` MUST open the flow menu (Section 16) on its Installed page.

**7.9.2** `/flow <flow>` MUST open the flow menu on the roles of the flow named, by any name the
offer list offers or by a path.

**7.9.3** While an epic is going, `/flow` MUST open on the roles of the running flow and offer
nothing else, and saving it MUST say that the epic going keeps its setup and the change applies to
the next epic.

**7.9.4** While an epic is going, `/flow <flow>` MUST be refused, saying a flow cannot be chosen
while one is running.

**7.9.5** `/flow <flow> <task>` MUST start an epic of that flow with that task at once where the
flow is set up here (Section 8.8), and MUST otherwise open the flow menu on its roles holding the
task, as Section 8.7 states for a `$` line.

**7.9.6** The flow menu MUST NOT offer a chat, which is not a flow; the chat's agent is set on the
Workspace page of `/settings` (Section 19.11) or by `/model` and `/effort` in the chat (Section
8.9.5 of [CORE]).

### 7.10. `/btw [question]`

**7.10.1** `/btw` MUST enter btw mode (Section 12), asking `[question]` where one is given.

**7.10.2** In btw mode, `/btw` alone MUST leave btw mode, and `/btw <question>` MUST ask one more
question.

**7.10.3** `/btw` MUST work only in a session view and an agent view (Section 9.5.3 of [CORE]); in
any other view it MUST be refused as Section 7.4 states, adding that `/ai` asks Ai-chan about the
epic.

**7.10.4** `/btw` MUST be refused where the session read no longer exists (Section 9.5.8 of
[CORE]).

### 7.11. `/epics [@daemon]`

**7.11.1** `/epics` MUST open the epics menu (Section 17) on the daemon it last listed, this
machine's until another is chosen.

**7.11.2** `/epics @<name>` MUST open the epics menu on the daemon named, one of those on the
Daemons page, and MUST keep to that daemon until another is chosen.

**7.11.3** `/epics` with an argument that is not `@` followed by a daemon's name MUST be refused,
naming the daemons it takes.

### 7.12. `/resume`

**7.12.1** Outside a chat, `/resume` MUST pick up the newest epic of this directory whose flow can
be picked up, as Section 18 states.

**7.12.2** `/resume` with any argument MUST be refused, saying `/epics` chooses another epic.

**7.12.3** `/resume` MUST be refused while an epic is going or stopping.

**7.12.4** `/resume` MUST NOT be offered while the last background look found nothing to pick up,
and MUST look again for itself when typed.

**7.12.5** In a chat, `/resume` MUST open a pick list of the earlier chats of this directory, newest
first, and MUST carry on the one picked (Section 8.9.8 of [CORE]).

**7.12.5.1** The pick list MUST be the chats of this directory that are not archived, as this
machine's daemon lists them (`chat.list` with `workspace`, Section 4.25 of [DAEMON]), each by its
title, the chat of this frontend among them as the choice in force (Section 15.1.6); picking that
one MUST leave it on the screen.

**7.12.5.2** A chat picked that a host holds (the `slot` of its row) MUST be put on the screen as it
stands, by attaching to that host; any other MUST be carried on by the next line said (`chat.start`
with `resume` the chat's id), the interface saying so.

**7.12.5.3** `/resume` MUST list and carry on a chat an earlier Humanize recorded as an epic as any
other chat, once the daemon has moved it among the chats (Section 8.7.10 of [CORE]), and MUST NOT
list or carry on one not yet moved (Section 17.2.3).

**7.12.5.4** While the setting `harness_sessions` is `true` (Section 3.4.14 of [FILES]), and only
then, the pick list MUST hold, after the chats, the harness sessions of this directory (Section
8.11 of [CORE]) as this machine's daemon lists them (`chat.harness.list`, Section 4.25.8 of
[DAEMON]), each by its title, or by its id where it has none, with a line that names its harness
and says it is read-only and, where its row is not `continuable`, that it cannot be continued in a
chat. Picking one MUST continue it as a chat (`chat.harness.adopt`) and MUST then go to that chat
as Section 7.12.5.2 states for a chat no host holds; a refusal MUST be said, and MUST be all that
picking a session that is not `continuable` does.

**7.12.5.5** `m` on a chat of the pick list MUST open its menu (Section 15.2.7) with these rows,
each done by this machine's daemon (Section 4.25.7 of [DAEMON]): `rename`, which asks for a title
on a form that opens on the chat's own (`chat.rename`); `fork` (`chat.fork`), which closes the list
and goes on with the new chat as Section 7.12.5.2 states for a chat no host holds; `archive`
(`chat.archive`); `upload`, offered where a backup target exists, which queues a backup of the chat
to the targets it was started with, else the defaults, without waiting for it (`chat.backup`);
`delete`, which asks in a box saying that the deletion is permanent, whose first answer keeps the
chat, and deletes on the other (`chat.delete`); and `copy id`. The row of a harness session
(Section 7.12.5.4) MUST have no menu.

**7.12.5.6** A chat archived or deleted MUST leave the pick list at once, and the list's message
line MUST say what became of each thing done from a menu, what the daemon refused included. Where
the chat of this frontend was archived or deleted, closing the list MUST start a new chat as
`/clear` does (Section 7.14.2).

### 7.13. `/settings [page]`

**7.13.1** `/settings` MUST open the settings menu (Section 19) on its landing screen.

**7.13.2** `/settings <page>` MUST open inside the page named: `general`, `notifications`,
`daemons`, `accounts`, `nous`, `runtimes`, `backup`, `workspace` or `usage`, compared without
regard to case.

**7.13.3** `/settings` MUST take `settings` and `everywhere` as `general`, `directory` as
`workspace`, and `environments` as `runtimes`, and MUST NOT offer those names in the offer list.

**7.13.4** `/settings flowverses` MUST say the flowverses are on `/flow` and open `/flow` on its
Flowverses page.

**7.13.5** `/settings` MUST refuse any other page, naming the pages it takes.

### 7.14. `/clear`

**7.14.1** `/clear` MUST clear the view read, and only that view, and redraw the opening box.

**7.14.2** In a chat, `/clear` MUST start a new chat and leave the previous one going on its own
host (Section 8.8.4 of [CORE]), the next line typed starting the new one.

### 7.15. `/afk [on|off]`

**7.15.1** `/afk on` MUST mark as away the outworlder whose view is read, or, in any other view,
every outworlder this frontend answers for; `/afk off` MUST mark them here; `/afk` alone MUST
toggle.

**7.15.2** In a view other than an outworlder's, `/afk` alone MUST read the current state as away
only where every outworlder is away.

**7.15.3** `/afk` MUST NOT change an outworlder that another frontend holds, and MUST be refused on
the view of such an outworlder.

**7.15.4** `/afk` MUST refuse an argument other than `on` or `off`.

**7.15.5** Away MUST be held by the host and MUST outlive the interface.

**7.15.6** While an outworlder is away, each question it is asked MUST be answered at once with
nothing, and a question pending when away is set MUST be withdrawn.

### 7.16. `/claim [on|off]`

**7.16.1** `/claim` MUST work only on an outworlder view.

**7.16.2** `/claim on` MUST hold the outworlder for this frontend alone; `/claim off` MUST give it
back; `/claim` alone MUST toggle.

**7.16.3** `/claim off` MUST be refused where this frontend does not hold the outworlder.

**7.16.4** `/claim` MUST be refused on an outworlder another frontend holds, naming it.

**7.16.5** The interface MUST say when this frontend loses a claim, and to whom.

### 7.17. `/stop`

**7.17.1** `/stop` MUST stop the epic going for every frontend: the open turn is interrupted and the
flow unwinds.

**7.17.2** Outside a chat, `/stop` MUST be refused where no epic is going and where the epic is
already stopping; in a chat, Section 11.5 states it.

**7.17.3** The interface MUST say that the flow is stopping, naming the frontend that stopped it
where another did.

### 7.18. `/exit`

**7.18.1** `/exit` MUST do what `ctrl+q` does.

**7.18.2** Where no epic is going, `/exit` MUST leave at once.

**7.18.3** Where an epic is stopping and a daemon holds it, `/exit` MUST force it and leave at once.

**7.18.4** Where an epic other than a chat is going, `/exit` MUST open a box offering to stop the
flow and leave, and, where a daemon holds the epic, to detach and leave, and otherwise to cancel.

**7.18.5** Stopping and leaving MUST stop the epic for every frontend, waiting at most 10 seconds
for it to stop.

**7.18.6** Detaching and leaving MUST leave the epic going, release this frontend's claims and keep
away as it is; `hmz` run again in the directory MUST read that epic from its start.

**7.18.7** In a chat, `/exit` MUST leave without asking (Section 8.8.6 of [CORE]).

**7.18.8** Once the interface has closed, `hmz` MUST give the backups this process queued at most 15
seconds to finish, saying so where it waits and where one was left unfinished.

**7.18.9** `/quit` MUST do what `/exit` does.

### 7.19. `/ai`

**7.19.1** `/ai` MUST open a menu (Section 15) listing, under an entry **New**, every Ai-chan
conversation of the daemon (Section 4.22.3 of [DAEMON]), newest first, each with its title, its
scope, its nous, its preset, and whether a turn is open, it is between turns or it has folded away.

**7.19.2** Choosing a conversation MUST follow its host in the log screen, carrying it on where it
has folded away (Section 14.8.5 of [CORE]), and MUST draw it as Section 7.19.6 states.

**7.19.3** **New** MUST open a form (Section 2.17) asking, in order: the scope, `daemon`, `workspace`
or `epic`, defaulting to `epic`, of the epic going or last on the host this interface follows, where
there is one, and otherwise to `workspace`, of this directory; the nous, offering every nous
`nous.list` answers and defaulting to the nous last used, the `ai_chan` setting (Section 14.3.2 of
[CORE]); and the preset, `read-only` or `danger-full-access`, defaulting to `read-only`.

**7.19.4** **Done** on the form of Section 7.19.3 MUST leave the menu with the log screen waiting
on a new conversation, and the first line said MUST make it by `aichan.create`, that line being its
task, and MUST then follow its host as Section 7.19.2 states.

**7.19.5** The menu MUST offer **Forget** on a conversation, which asks for confirmation and then
forgets it by `aichan.forget`.

**7.19.6** While the log screen follows an Ai-chan conversation, the interface MUST draw it as a
chat (Section 11), naming it `Ai-chan#<n>` on the status line with its scope, and MUST show each
tool Ai-chan calls as a tool line of a turn is shown (Section 14.7.3 of [CORE]).

**7.19.7** While the log screen follows an Ai-chan conversation, a line said MUST be its next turn,
`/stop` MUST stop Ai-chan's open turn (Section 14.8.3 of [CORE]), refused in her own words where
she is not answering, and `/btw` MUST be refused as Section 7.10.3 states.

**7.19.8** `/clear` while the log screen follows an Ai-chan conversation MUST leave that
conversation to its host and follow this directory's own host again.

### 7.20. `/env [role]`

**7.20.1** `/env` MUST open a sheet of the envs of the epic going, or of the last one, of the host
this interface follows -- a chat's workspace among them -- as the snapshot `envs` holds them
(Section 4.24.2 of [DAEMON]), each derived env under the env it was derived from, each named by its
chain and marked where it is closed; `/env <role>` MUST open the first env of that role, and MUST be
refused, naming the roles it takes, for a role that has none.

**7.20.2** `/env` MUST be refused while the host holds no env, except for a chat to be carried on
that no host holds (Section 7.12.5.2): `/env` MUST then carry that chat on with nothing said
(`chat.start` with `resume` the chat's id and an empty `task`, Section 4.25.1.9 of [DAEMON]) and
MUST open once its host lists its envs.

**7.20.3** An env MUST open on its pages as Section 7.13.3 of [CORE] chooses them: `Files` where it
serves files, `Changes` where it serves git, and `Shell` where it serves a shell; it MUST open on
the first of them whose capability its role declares, else `Files`, and `tab` and `shift+tab` MUST
step through them.

**7.20.4** `Files` MUST list one directory of the env at a time (`env.list`), directories first;
`enter` MUST open a directory, and `backspace` the directory above.

**7.20.5** `enter` on a file MUST open it in an editor of the interface's own that highlights its
syntax by its name, and MUST write the file 1 second after the user stops typing and on leaving the
editor, each time as `env.write` with `if_match` the `etag` last read or written. A write refused
because the file changed MUST keep the user's text and MUST open a box offering to keep the user's
text, which writes it over the file, or to read the file again. A binary file, and a file larger
than 5 MiB, MUST NOT open in that editor.

**7.20.6** `e` on a file MUST open a copy of it in the editor `VISUAL` names, else `EDITOR`, else
`vi`, handing it the terminal until it exits, and MUST then write the copy back as Section 7.20.5
writes, where it changed.

**7.20.7** `Changes` MUST list the env's git status (`env.git.status`) in the groups of Section
3.17.4.1 of [WEB], and MUST show the change of the file selected (`env.git.diff`) highlighted as a
diff; it MUST let the user stage, unstage and, after a box, discard a file, and commit with a
message (`env.git.commit`).

**7.20.8** `Shell` MUST open a terminal in the env (`env.term.open`), or attach again to one this
interface opened that is still alive, and MUST hand it the whole terminal: every key typed goes to
it (`env.term.input`), what it prints is drawn as it comes and acknowledged as drawn
(`env.term.ack`), and a change of the terminal's size is passed on (`env.term.resize`).

**7.20.9** In `Shell`, `~.` typed at the start of a line MUST give the terminal back to the
interface and leave the terminal running; the terminal ending MUST give it back too, saying its exit
status.

### 7.21. `/chat`

**7.21.1** `/chat` MUST put back on the screen the chat of this frontend, which went on on its own
host while a flow was on the screen; a chat that has folded away meanwhile MUST be drawn as Section
8.7.4 of [CORE] states, and carried on when the next line is said.

**7.21.2** `/chat` MUST be refused where the chat is already on the screen, and with any argument.

### 7.22. `/prefer [native|flow]`

**7.22.1** `/prefer` MUST work only in a chat.

**7.22.2** `/prefer` alone MUST say the chat's preference (Section 8.9.10 of [CORE]) and whether it
comes from the settings file or from this chat.

**7.22.3** `/prefer native` and `/prefer flow` MUST set this chat's override, and `/prefer` MUST
refuse any other argument, naming those it takes.

## 8. `$` lines

**8.1** A line of the form `$<name>[ <task>]` MUST be a `$` line, where `<name>` is a flow as the
offer list names it: a bare name starting with a letter, `<user>/<flow>` for a GitHub user,
`@<flowverse>/[<user>/]<flow>`, or any of these followed by `:<flow>` for another flow of the same
module; and where `<name>` is followed by whitespace or the end of the line.

**8.2** A line starting with `$` that is not a `$` line MUST be treated as prose.

**8.3** A `$` line MUST be treated as prose while a question is answerable here, and MUST be a side
question while btw mode is on.

**8.4** A `$` line naming a flow not offered MUST be refused, naming it.

**8.5** A `$` line MUST be refused while an epic of a flow is going, leaving that epic untouched.

**8.6** A `$` line naming a flow that is set up here MUST choose that flow and, with a task, start
an epic of it at once; without a task, the interface MUST ask for one.

**8.7** A `$` line naming a flow that is not set up here MUST open `/flow` on that flow's roles,
holding the task, and MUST start the epic when the menu is saved; leaving the menu unsaved MUST say
that the flow was not set up and nothing was started.

**8.8** A flow MUST count as set up here where every agent role it declares has a remembered agent,
every environment role it requires has a remembered environment, its remembered params are valid,
and it has a budget.

**8.9** In a chat, a line starting with `$` MUST first be resolved as Section 8.9.9 of [CORE]
states: a `$<name>` that names a native skill MUST be served by the chat, and one that names a flow
MUST be a `$` line of this section.

## 9. Saying something

**9.1** A line said while a question is answerable here MUST answer that question (Section 10).

**9.2** A line said on an outworlder view MUST be refused where another frontend holds that
outworlder, and where that outworlder asks nothing.

**9.3** A line said while an epic is going MUST be sent to the session read, or to whichever session
of the agent read has a turn open, and MUST otherwise be held for that agent's next turn.

**9.4** A line said while no epic of a flow is going MUST be said to the chat of this frontend,
putting it on the screen: as its task where it has not started, and as its next turn otherwise,
carrying it on where it has folded away.

**9.5** The interface MUST pin each line said and not yet taken at the left above the editor, the
ones put into a turn first, then the held ones oldest first, each with the agent it is with and the
frontend that said it where another did, at most 5, followed by how many more wait.

**9.6** A line taken MUST move from the pins into the transcript.

**9.7** A line the harness refuses mid-turn MUST be shown with the harness's reason in red and MUST
return to the head of the held lines.

**9.8** A line delivered to a turn that ended without taking it MUST be shown as sent and not
acknowledged, and discarded.

**9.9** When an epic ends, every line not taken MUST be shown as never sent or as not acknowledged,
with whether the flow stopped or ended.

**9.10** The interface MUST attribute each line, answer and epic started by another frontend to that
frontend by its frontend name.

## 10. Questions

**10.1** A question an outworlder is asked MUST be shown on its outworlder view and, where it is
part of a session, in that session's view, and otherwise on the view read.

**10.2** A question MUST be shown with its offered answers numbered, and with whose it is to answer.

**10.3** The answerable question MUST be: on the home view or the monitor, the oldest pending
question of any outworlder; on an outworlder view, the oldest of that outworlder; on a session view,
the oldest that is part of that session, or of no session and shown on that view.

**10.4** A question MUST be answerable here only where it is unclaimed or claimed by this frontend,
and is not already being answered.

**10.5** The next line typed MUST answer the answerable question, a bare number that is not itself
an offered answer picking the offered answer of that number.

**10.6** A question the agent asks mid-turn MUST be shown in its session with what it offers, and
its answer MUST be shown there too.

**10.7** A flow's wait for what to say next after a session's answer MUST NOT be drawn as a
question; the next line typed reading that session MUST answer it.

**10.8** An answer that another frontend gave first MUST refuse this one, naming that frontend.

**10.9** Every question pending MUST be withdrawn when its epic ends, stops, is forced or its host
closes.

**10.10** The monitor MUST list every frontend reading the epic where there is more than one.

**10.11** A question with a schema MUST be shown on its outworlder view and on the view read, as
the first line of its text, the rest of its text as Markdown, its context blocks (Section 10.15),
then the line `form · <n> fields — press Enter to open`, or `Waiting for <name>` where another
frontend, `<name>`, holds its role; it MUST NOT take the focus from the editor while a line is being
typed.

**10.12** Where a question with a schema is the answerable question, `enter` with nothing typed MUST
open its sheet. A line typed that is a JSON object, or any JSON value for a schema that is not an
object, MUST be sent as `value` (Section 4.8.4 of [DAEMON]); any other line MUST open the sheet with
the line put where it fits: in the first unanswered choice one of whose values it names, by its
words or its number, else in the first empty text field, a required one first, else said on the
message line as answering none of the fields.

**10.13** The sheet MUST be a form of Section 15 laid along the bottom of the screen over the view
it was opened from, which stays readable above it and which `pageup` and `pagedown` MUST scroll. It
MUST be headed with the first line of the question's text, and MUST hold one row per field of the
whole schema, named by its `title`, else its name, with its `description` beneath: the required
fields first, in the schema's order, then the others, filled with their defaults, marked `suggested`
while they hold them, and folded under one row, `More options (<n>)`, `<n>` being how many, where
there are both. Beside the keys of Section 15.2.1, and in place of Section 15.2.4, a choice of at
most 5 values and a boolean MUST show their values side by side in their row, the one picked marked,
the digits `1` to `9` picking the value of that number and `←` and `→` moving the pick, a boolean's
values being `Yes, <description>` where its `description` is one line of at most 40 characters, else
`Yes`, and `No`; a choice of more values MUST be picked from a list under its row, by `1` to `9` as
well, on a row of a choice. A `string` with `hmz:widget` `secret` MUST be hidden as it is typed; one
with `hmz:widget` `markdown` or `code`, or `format` `textarea`, MUST take several lines; an array of
strings, integers or numbers MUST take one value a line; and anything else -- an object, any other
array, a union of several types -- MUST take JSON. Its button MUST say `answer`, and `answer · <n>
required left` while `<n>` required fields are empty, and MUST send the whole form as `value`, or,
where a field cannot be read, say what is wrong beside it and put the cursor on the first.

**10.14** Where an answer is refused as one that does not fit, the sheet MUST stay open and put each
of the refusal's `errors` beside the row of the first key of its `path`, the rest of the path
before its message, else on the message line, the cursor on the first. `esc` MUST close the sheet
and keep what it holds for the next time it is opened, until the question is answered or
withdrawn; a question withdrawn while its sheet is open MUST close it, saying why.

**10.15** Context blocks (Section 3.10.5 of [PYTHON]) MUST be written under their `title`:
`markdown` as Markdown, `code` and `diff` highlighted as their language and as a diff, `table` as a
table, `json` indented, and `image` and `chart` as one line naming the block and saying that the web
page shows it, with the address of the epic's page where it is known: where this machine runs the
epic and `<state>/web-port` (Section 4.15 of [FILES]) holds a port. The first block MUST show at
most 40 lines, and each after it at most 12, and a table at most 10 rows, followed by how many
more there are and, where it is known, that address.

**10.16** Blocks shown with no question (`shown`) MUST be written to the outworlder view of their
role, under a line saying `<role> was shown`, with no means to answer.

**10.17** A question naming a face MUST say that a richer view of it is in the web page, with that
address where it is known, and MUST be answered here by the sheet.

**10.18** A question with a schema answered MUST be shown under it as one line of the answer, `❯
<answer>`, `<answer>` being the values given joined by ` · `, a choice as its words, text quoted
the rest as JSON and a `secret` value as `***`, followed by ` · by <name>` where another frontend, `<name>`, answered it; one
withdrawn MUST be shown as `withdrawn: <why>`, `<why>` the record's (Section 4.9.2.4 of
[DAEMON]).

## 11. Chat

**11.1** The interface MUST hold one chat of its own at a time, and MUST treat as a chat the chat
on the screen.

**11.2** In a chat, the interface MUST read the chat's session alone, with no header naming the
view, no round, no outworlder line, and no `reading` or `unread` mark on the agent line.

**11.3** In a chat, `←` MUST NOT open the monitor.

**11.4** In a chat, the status line MUST say `running` while a turn is open and `done` while the
chat is between turns.

**11.5** In a chat, `/stop` MUST interrupt the open turn (`chat.stop`, Section 4.25 of [DAEMON]),
leaving the chat between turns on its host, and MUST be refused where no turn is open, saying `no
turn is open, so there is nothing to stop`. The interface MUST NOT offer a way to end a chat or to
force its turn to stop.

**11.6** In a chat, `ctrl+c` MUST NOT stop anything (Section 14.3).

**11.7** A flow MUST be startable and `/resume` MUST work while a chat goes on its own host.

**11.8** `/epics` MUST NOT list a chat of this machine, which is no epic; a chat MUST be gone back
to with `/resume` in a chat (Section 7.12.5) and with `/chat` (Section 7.21), by its id.

**11.8.1** The interface MUST read which chat a host holds from `chat` of that host's status, of its
`run` snapshot and of the answer of `chat.start`, where `epic` is empty for a chat (Section 4.6 and
Section 4.25 of [DAEMON]).

**11.9** Starting a flow from the chat MUST put the flow on the screen and leave the chat going on
its own host; `/chat` MUST bring it back (Section 7.19).

**11.10** In a chat, completion MUST offer, for the sigil typed, the entries of the chat's
catalogue and the names Section 8.9.7 of [CORE] keeps, and, for `$`, the native skills and the
flows grouped apart, each tagged with where it comes from; where a `$` name is both, it MUST say
which one the preference picks and that `/flow <name>` starts the flow.

**11.11** In a chat, a `!` line and its output MUST be drawn dim, in the style of a shell.

## 12. Btw mode

**12.1** Entering btw mode MUST say who answers, `btw · <agent>/<n>`, and that each line is a
question and `/btw` or `esc` leaves.

**12.2** While btw mode is on, the status line MUST begin with `btw · ` and who answers, in cyan.

**12.3** While btw mode is on, every line typed that does not start with `/` MUST be one more
question of the same side conversation.

**12.4** Who answers MUST be as Section 9.5 of [CORE] states, the view read deciding: a session view
or an agent view its session side copy.

**12.5** Each answer MUST be shown in the view read: a cyan bullet, `btw · ` and the question, dim,
then the answer in cyan.

**12.6** Btw mode MUST offer no key or list that picks the agent that answers (Section 9.5.9 of
[CORE]).

**12.7** `/btw` alone or `esc` MUST leave btw mode, say `btw: exited`, and close every side
conversation btw mode opened.

**12.8** An epic starting MUST leave btw mode, saying that a new flow started.

**12.9** A side question asked while the side conversation is answering an earlier one MUST be
refused, showing `hmz: btw is still answering the last question` in red.

**12.10** A failure of a side question MUST be shown in red, prefixed `hmz: /btw:`.

## 13. Status line

**13.1** The left of the status line MUST show, in order and where each holds: btw mode; `afk` where
every outworlder is away, or `afk` and the roles away where some are, in yellow; `details` where
details are on; the state; and ` · copied` for 2 seconds after a copy.

**13.2** The state MUST be the first of these that holds:

1. from a start being asked for until the epic or chat has started or the start has failed, a
   spinner and `starting…`;
2. in a chat, `done` while between turns, and otherwise `running` with a spinner and the seconds
   since the turn began;
3. with an epic going, no turn open and a question waiting for an answer, `waiting for` and `you`,
   or the name of the frontend that holds it, and that `ctrl+c` twice stops it;
4. with a turn open or an epic going, a spinner, the agents working (or the flows running, innermost
   last, where no agent works), the seconds since the oldest open turn began (or since the epic
   began), and that `ctrl+c` twice stops it;
5. otherwise, the chat's agent and the working directory, the home directory written `~`.

**13.3** The right of the status line MUST show, joined by ` · `, the hints that hold now: what
`enter` does; `shift+tab switch view` where the round holds another view; `/ commands`; `shift+enter
newline`; `← monitor` on an empty editor outside a chat; and what the next `ctrl+c` does.

**13.4** While the offer list is open, the right of the status line MUST show only how to move, take
and cancel an offer.

**13.5** Where the hints are wider than the room left, the interface MUST drop hints from the front
until they fit or one remains, and MUST NOT cut the left side.

**13.6** The status line MUST be redrawn at least every 0.5 seconds.

## 14. `ctrl+c` and `ctrl+q`

**14.1** `ctrl+c` with text in the editor in front MUST clear it and reset the count.

**14.2** `ctrl+c` on an empty editor MUST count presses, the count starting again at 1 where the
last press was more than 3 seconds ago.

**14.3** In a chat, the first press MUST say to press again to leave, and the second MUST leave as
`/exit` does.

**14.4** With an epic going, the first press MUST say to press again to stop, and the second MUST
stop the epic as `/stop` does.

**14.5** With an epic stopping, any press MUST force it, closing its sessions mid-turn and saying
how many were closed.

**14.6** Idle, the first press MUST say to press again to leave, and the second MUST leave at once
without a box.

**14.7** `ctrl+c` MUST work over every screen and menu.

**14.8** `ctrl+q` MUST do what `/exit` does, over every screen and menu.

## 15. Menus

### 15.1. Layout

**15.1.1** Every menu MUST be a screen of its own drawn the same way: the way there across its top;
its title and what it is for; its list; one message line; its buttons; and the keys that work where
its focus is.

**15.1.2** The way there MUST start with `hmz`, or with `monitor` for a menu opened from the
monitor, followed by each menu it was opened from and each page it is inside, then its title, ` › `
between steps, every step but the title being a click back to it.

**15.1.3** While a menu holds a change, its top line MUST say `● unsaved changes` at the right, in
yellow.

**15.1.4** What a menu is for MUST NOT name a key.

**15.1.5** The list MUST fill the row under the cursor, MUST step over headings and rules, and MUST
scroll.

**15.1.6** A pick row MUST show its name, a green `✔` where it is the choice in force, and what it
is; a pick list MUST open with the cursor on the choice in force.

**15.1.7** A setting row MUST show its name at the left, its value at the right and what it is under
both; a value ending `▸` MUST open a sheet, a value ending `▾` MUST drop a dropdown, and a switch
MUST read `● on ▾` or `○ off ▾`.

**15.1.8** The message line MUST say what became of the last thing done, a refusal in red, or, while
a button has the focus, what that button does.

**15.1.9** The buttons MUST be what the menu does about its list rather than to one row, in the
menu's order; the button that answers the menu MUST be last and apart at the right, in green; a
button that removes MUST be red; a button that cannot be pressed now MUST be dim; every button MUST
have a tooltip saying what it does.

**15.1.10** The keys line MUST say each key that works where the focus is, and only those.

**15.1.11** A box MUST be at most 66 columns wide, in the middle of the screen with what was there
still drawn, and MUST hold only its question, what it is about where there is any, its buttons with
the first focused, and its keys.

### 15.2. Keys and mouse

**15.2.1** Every menu MUST take the same keys, and only these: `↑`, `↓`, `←`, `→`, `enter`, `esc`,
`tab`, `shift+tab`, `backspace`, `/` where its list is searchable, `m` on a row with a menu, typing
on a form, and `shift+enter` or `ctrl+j` on a written row that takes several lines; the keys of each
are those of Section 24.

**15.2.2** A written row MUST change only between an `enter`, or on a form a typed character, that
begins it and an `enter` that keeps it; `esc` MUST put it back.

**15.2.3** Keeping a row on a form MUST move the cursor to the next row still unanswered, and after
the last to the button that answers the form.

**15.2.4** A value taken from a fixed few MUST be picked from a dropdown of every value it takes,
and MUST NOT be stepped with `←` or `→` or turned over in place.

**15.2.5** A dropdown MUST be titled with the row's name, MUST show at most 12 values at once, each
with what it means and `✔` on the one in force, and an on/off dropdown MUST open on the value not in
force.

**15.2.6** A search MUST be asked for with `/` or a **Search…** button, into a box above the list,
MUST narrow the list as it is typed without regard to case, and `esc` MUST clear and hide it.

**15.2.7** `m` on a row with a menu MUST open that row's menu: what the web interface's menu on a
right click (Section 3.4.4 of [WEB]) offers of it, limited to what is possible here and now.

**15.2.8** Every row, button, value and step of the way across the top MUST be reachable by the keys
and by the mouse: a click chooses, opens or presses it; the pointer marks what a click would take; a
click off a box or a dropdown answers nothing.

**15.2.9** A menu MUST act once on a key however many times the key is pressed while it opens.

### 15.3. Held changes

**15.3.1** A menu MUST hold what it changes until it is saved by its saving button or by saving on
the way out.

**15.3.2** Leaving a menu that holds changes, by `esc`, `←`, `backspace` or a step of the way across
the top, MUST open the box `Save?` offering **Save** and **Discard**, `esc` going back to the menu
with what it held; a walk back across the top MUST stop at that box.

**15.3.3** Whatever runs an external command, installs, fetches, imports, exports, uploads or writes
to the board MUST apply at once.

**15.3.4** A menu that holds nothing MUST have no saving button.

### 15.4. Paths

**15.4.1** A written row that takes a path MUST complete as it is typed, as a shell does: `~` alone
becoming the home directory, the files and directories the path could become listed under the list
(the first 8, then how many more), dot-files only once a `.` is typed.

**15.4.2** `tab` on a path being written MUST complete it to what every candidate shares, or, where
that adds nothing, to each candidate in turn.

## 16. `/flow`

### 16.1. Pages

**16.1.1** `/flow` MUST be a menu of pages whose first screen holds two cards, Installed and
Flowverses, and MUST open on Installed.

**16.1.2** `/flow` MUST hold the flow chosen and its roles, params, budget, profiling switches and
backup targets until **Save**, and MUST apply installing, updating, uninstalling, fetching, adding
and removing at once.

**16.1.3** One install, update, uninstall, fetch or removal MUST run at a time, saying under the
list what is under way, refusing another until it is done, and saying the result under the list and,
once the menu closes, in the transcript.

### 16.2. Installed

**16.2.1** The Installed page MUST list every flow that can run here: the flows installed from each
flowverse, then this project's, then the user's, each under a heading of where it came from and by
the name `-f` takes.

**16.2.2** Each installed flow MUST show its release and, where its index lists a newer one, that
newer release; the flow in force MUST be marked `✔`.

**16.2.3** The Installed page MUST offer **Browse Flowverses**, **Update** where an update is listed,
**Uninstall** for an installed flow, **Copy here** for a flow not of this project, and **Search…**.

**16.2.4** **Uninstall** MUST be refused while another installed flow needs the flow.

**16.2.5** **Copy here** MUST copy the flow, what it imports and its skills into this project, and
the flow's name MUST then name the copy.

**16.2.6** `enter` on a flow MUST load what is remembered for it, ask its params where it declares
any, and open its roles.

**16.2.7** A flow that fails to load MUST be said in red with the first line of why.

### 16.3. Flowverses

**16.3.1** The Flowverses page MUST list each flowverse with a URL, `official` first, and each
directory under the flowverses home that is not a clone, each with whether it is fetched, not
fetched, edited, or has no origin, its URL with any credential hidden, how many flows it lists, how
many are installed and how many have updates.

**16.3.2** The Flowverses page MUST offer **Add flowverse**, a form taking a repository and an
optional name; **Fetch**; **Remove**, except for `official`, asked first in a box
that says how many installed flows go with it; and **Search…**.

**16.3.3** One flowverse's page MUST list each flow its index lists at its newest release, with what
of it is installed, and MUST name each manifest it skipped and why.

**16.3.4** One flowverse's page MUST offer installing, updating to or switching to the newest
release of the flow under the cursor, with what it needs, and uninstalling it.

**16.3.5** A flow's releases page MUST list every release newest first, prereleases marked and the
installed one ticked, and MUST install or switch to the release chosen.

### 16.4. Roles

**16.4.1** The roles page MUST list one row per agent role and one per environment role the flow
declares, omitting outworlder roles and roles the runtime fills; then `params` where the flow takes
any; then `budget`; then `profile flow`; then `profile environment`; then `backup`.

**16.4.2** While an epic is going, and when opened by `/flow <flow>` or a `$` line, the roles page
MUST open alone, with no page of `/flow` across the top, and MUST NOT ask params.

**16.4.3** `profile flow` and `profile environment` MUST each be a switch, off until switched on,
remembered per flow; an epic started from the interface MUST profile its flow's own Python exactly
where `profile flow` is on, and the programs its agents start exactly where `profile environment`
is on (Section 10 of [CORE]).

**16.4.4** `backup` MUST open a switch per backup target, and MUST show the defaults until other
targets are switched on and saved.

**16.4.5** **Save** MUST be refused for a flow with an agent role that names no harness or model, or
a required environment role unset, naming those roles.

**16.4.6** **Save** MUST be refused for a flow that has no budget.

**16.4.7** A saved setup MUST take effect from the next epic.

### 16.5. Agent sheet

**16.5.1** The agent sheet MUST set an agent by four rows: `cli`, `account`, `model` and `effort`,
and, for a model that runs as a swarm, `swarm`.

**16.5.2** `cli` MUST offer only harnesses installed here whose kind is the one the role names and
that serve every capability the role requires, and MUST say how to install a harness whose program
is present but whose extra is missing.

**16.5.3** `account` MUST offer this machine's own sign-in first, as `as local`, then each saved
account of the harness, and MUST offer adding an account (Section 19.7); `model` MUST offer the
models last reported for that account and checking again; `effort` MUST offer the efforts that model
takes, hardest first.

**16.5.4** An agent role with nothing remembered MUST start on the first installed harness that has
reported models and serves the role: its first model, at effort `high` where the model takes it,
else its easiest effort.

**16.5.5** Changing `cli` MUST clear `account`, `model` and `effort`; changing `model` MUST keep the
effort where the new model takes it.

**16.5.6** Choosing an account never asked for its models MUST ask it, in the background, saying
so while it asks.

### 16.6. Environment form

**16.6.1** The environment form MUST set an environment role by its backend, then, for a backend
that has them, a runtime saved on the Runtimes page, one added there and then, or for ssh a host not
saved, then its working directory, starting from the one the runtime is saved with.

**16.6.2** The environment form MUST compose what `-e` spells, MUST take that spelling typed whole,
and MUST refuse what `-e` refuses in `-e`'s words (Section 7 of [CORE]).

### 16.7. Params and budget

**16.7.1** The params sheet MUST list each param of the flow by its own model, under the sections
the flow declares, a boolean or a choice of literals picked from a dropdown and any other value
typed, and **Set** MUST refuse what the flow's model refuses with its first error.

**16.7.2** The budget sheet MUST take a duration, a cost in US dollars, output tokens, and, for each
of the three, whether the last turn finishes when it is reached, and **Set** MUST refuse a budget
with no limit set.

**16.7.3** On a typed row of the params or budget sheets, `enter` MUST begin writing with the whole
value selected, so that the first character typed replaces it.

## 17. `/epics`

### 17.1. The list

**17.1.1** `/epics` MUST list the epics of this directory, newest first, each with when it began,
its flow, its task, its agents, what it spent, how long it took, the targets it is backed up to, how
many sessions it opened, how it went or that it is going, and whether it can be picked up.

**17.1.2** `ctrl+t` or a button MUST turn the list to the epics of every directory on this machine,
each with its directory, and back; the choice MUST be remembered for this machine.

**17.1.3** `/epics` MUST offer filters by status, flow and, on this machine, directory, each value
with how many epics have it; **Search…** by flow, task, epic name and directory; and pages of 50
epics where more are found.

**17.1.4** `/epics` MUST mark with `●` each epic a notice was given of (Section 19.4) until it is
opened there; a notice of a chat marks nothing.

**17.1.5** `i` or **Import…** MUST open a form taking the path of a `.hmzepic`, starting from the
downloads directory, taking a file dropped onto the terminal as its path, and MUST import it in the
background and put the cursor on it, or refuse the file in plain words.

**17.1.6** `/epics` MUST offer **Daemon…**, a pick list of this machine's daemon and every daemon on
the Daemons page with how it stands, turning the list to the one picked.

**17.1.7** The list MUST be readable while an epic is going.

### 17.2. One epic

**17.2.1** `enter`, `→` or a click on an epic MUST open its menu with these rows, each where
offered: `resume epic`; `graph`; `export epic`; `Exomyth`; `upload`; `copy name`, `copy task`, `copy
path`.

**17.2.2** `resume epic` MUST pick the epic up as `/resume` does, and MUST be refused for an epic of
another directory, saying where it ran; while an epic is going; and for an epic whose flow is not
resumable or that cannot be resumed here, saying why.

**17.2.3** An epic an earlier Humanize recorded for a chat (kind `chat`) that the daemon has not
yet moved among the chats (Section 8.7.10 of [CORE]) MUST be listed as an epic,
named `chat` where another names its flow, MUST be read as any other, and MUST NOT be offered
`resume epic` or any way to carry it on, saying that it cannot be carried on.

**17.2.4** `graph` MUST open the epic's graph, read in the background: one box per agent with its
turns and the handovers between neighbours, its sessions under it, and the tree of flows it called.

**17.2.5** `enter` on a session of the graph MUST read the session whole: each turn, model call,
tool call with what went in and came out, and what was said, in order, each cut to 6 lines until
opened, searchable.

**17.2.6** `export epic` MUST ask where the archive goes, a file or a directory, starting from the
downloads directory, and MUST say where it landed, how big it is and what it holds.

**17.2.7** `upload` MUST be offered where a backup target exists, and MUST queue a backup to the
targets the epic was started with, else the defaults, without waiting for it.

**17.2.8** `Exomyth` MUST open the epic in Exomyth (Section 21), and MUST NOT be offered for an
epic of kind `chat`.

**17.2.9** `copy name`, `copy task` and `copy path` MUST copy that to the clipboard and say so.

### 17.3. Another daemon's epics

**17.3.1** On a daemon of another machine, `/epics` MUST list the epics that daemon holds, read
over a session to it (Section 3.8 of [DAEMON]) in the background, and MUST say why where it cannot
be reached.

**17.3.1.1** A row of that list whose workspace is folderless (the `folderless` of its row, Section
4.16.2 and Section 4.25.5.2 of [DAEMON]) MUST say `no folder` in place of its workspace.

**17.3.2** `enter`, `m` or a click on such an epic MUST offer `follow` for one a host there holds,
`export` for one not going, `upload`, `copy name`, `copy task` and `copy workspace`.

**17.3.2.1** The list of a daemon of another machine MUST also hold each chat a host there holds
(`chat.list`, the rows with a `slot`), named `chat` and never an epic, with its title and how it
stands; such a row MUST offer `follow` and `copy id` and nothing else.

**17.3.3** `n` or **New epic…** MUST start an epic there from a directory, a flow, a task and its
agents, set up otherwise as that directory last ran the flow, and MUST follow it.

**17.3.4** Following an epic there MUST attach to its host there and show it as an epic of Local
is shown, with every command that steers it (Section 3.8.4 of [DAEMON]); `esc` MUST go back to the
list, leaving the epic going there.

## 18. `/resume`

**18.1** `/resume` MUST look at the epics of this directory newest first, and MUST pick up the first
whose flow is resumable, with its flow, agents, environments, params, budget counted from zero,
profiling switches and task, saying which epic it resumes.

**18.2** `/resume` MUST say why there is nothing to resume: no epic here, none of a resumable flow,
an epic that cannot be read, a flow that will not load, a flow that is not resumable, or an epic
with no saved state.

**18.3** Outside a chat, `/resume` MUST NOT pick up a chat (Section 7.12.5), nor an epic an earlier
Humanize recorded for one (Section 17.2.3).

## 19. `/settings`

### 19.1. Landing screen

**19.1.1** `/settings` MUST be one menu of eleven pages in three groups, in this order: under
**App**, Themes, Daemons, Notifications, Language; under **Daemon**, General, Accounts, Nous,
Runtimes, Backup, Usage; under **Workspace**, Workspace (Section 32.1).

**19.1.2** The landing screen MUST show each group's name over its pages, one card per page with a
summary of it, and `■ Unsaved` on each card whose page holds a change.

**19.1.3** `enter` or a click on a card MUST open its page; `esc`, `←` or `backspace` on a page MUST
return to the landing screen with the cursor on that page's card.

**19.1.4** Each page MUST keep its message and cursor while another page is read.

**19.1.5** **Save** on the landing screen or a page MUST apply what every page holds.

**19.1.6** Each saved setting MUST take effect at once where it can; otherwise the interface MUST
say beside its row while held and in the transcript when it lands: account changes from the next
agent session, forgetting a directory from the next launch.

**19.1.7** Leaving `/settings` MUST write one dim line per change into the transcript.

### 19.2. General

**19.2.1** The General page MUST hold, for this machine: **Details**, whether turns show tool calls,
thinking and harness output; **Chat prefers for `$`**, `native` or `flow`, the preference of every chat
whose own is not overridden (Section 8.9.10 of [CORE]); **Harness sessions**, whether `/resume` in a
chat lists them (Section 7.12.5.4); **Error reports**, on or off; and **What is sent**, which says
what error reports include and exclude.

**19.2.2** Once answered, **Error reports** MUST NOT return to unanswered.

**19.2.3** Where `HUMANIZE_SENTRY` overrides error reporting, the General page MUST say so.

### 19.3. Details

**19.3.1** Details on MUST show every tool call, the thinking, sub-agents and harness output in the
transcript; details off MUST show the agents' answers only.

### 19.4. Notifications

**19.4.1** The Notifications page MUST offer, each on or off, the kinds Done, Failed, Stopped,
Questions and Waiting, and **System**, whether the system is told of a notice too (Section 32.4),
kept in the settings file (Section 3.4.5 of [FILES]); the page keeps its own (Section 3.15 of
[WEB]).

**19.4.2** For every epic and every chat of Local and of every remote daemon that is `up`, the
interface MUST show each notice of a kind turned on (Section 10 of [CORE]) as a card that goes after
a while, and, with **System** on, MUST tell the system as Section 32.4 specifies.

**19.4.3** The interface MUST NOT give a notice of an epic of this directory while its log or the
monitor is on the screen, nor of the chat on the screen, which a notice names by `chat` where
`epic` is empty.

**19.4.4** The interface MUST be told notices by each daemon (`notices.subscribe`, Section 4.19 of
[DAEMON]), resuming after the last notice heard of it.

### 19.5. Daemons

**19.5.1** The Daemons page MUST list this machine's daemon, `Local`, and every daemon of another
machine kept in the settings file (Section 3.4.6 of [FILES]), each with its routes and how it stands
(Section 3.8.2 of [DAEMON]), redrawn as that changes.

**19.5.2** The Daemons page MUST offer **Add daemon** and **edit…** on one form, which takes a name
and either a pairing code, claimed at once (Section 4.5.7 of [WIRE]), or routes in order;
**Import…** of the hosts of the ssh config not added yet, each as a `stdio:ssh` route; per daemon
**connect**, **remove** and **copy name**; and, for each daemon that is `up`, **Pair a device…**,
which shows a pairing code of it, and **Devices…**, which lists the devices paired with it and
revokes one after confirmation; each written at once.

**19.5.3** The Daemons page MUST offer **Batch apply…**: this machine's settings of the pages
picked, the accounts excluded, written to each daemon picked as the web interface's `Batch apply`
writes them (Section 3.11.2.13 of [WEB] to Section 3.11.2.15 of [WEB]), saying how each went.

**19.5.4** While a daemon of another machine is `asking` (Section 3.8.3.7 of [DAEMON]), the
interface MUST ask, over whatever is on the screen, `hmz is not installed on <name>. Install it?`,
offering **install** and **not now**, and MUST give that daemon the answer chosen (Section 3.8.3.8
of [DAEMON]); `esc` MUST answer **not now**, and the question MUST go once the daemon is no longer
`asking`. **connect** (Section 19.5.2) MUST reach again a daemon that failed so (Section 3.8.3.9 of
[DAEMON]).

### 19.6. Accounts

**19.6.1** The Accounts page MUST list every account under its harness, then `as local`, and MUST
NOT draw a secret onto the screen.

**19.6.2** Each account MUST offer **edit settings**, held until saved, a secret left blank keeping
the one it has; **sign in again**, at once; and **Remove**, held until saved.

**19.6.3** `as local` MUST offer nothing to edit, sign in or remove.

**19.6.4** The Accounts page MUST offer **Add an account** and **Add a custom CLI**, each applied at
once.

### 19.7. Account form

**19.7.1** The account form MUST ask, in order, the harness, the way in, a name no account of that
harness has, what that way asks, and which other harnesses to write the account for, and MUST be
offered wherever an account is asked for.

**19.7.2** The account form MUST list the ways in through the local LiteLLM gateway after the
harness's own, under one heading, and where the `litellm` extra is missing, the line that installs
it in their place.

**19.7.3** After an account is made, the interface MUST ask what it runs without holding up the
menu, saying so while it asks and how that went.

### 19.8. Nous

**19.8.1** The Nous page MUST list each nous by its name, marked virtual or concrete, with its
retries, its wait policy, its limit, and its graph and `then`, each shown as its nodes in order from
the start, a use node as its nous and a balance node as its strategy and its nous with their weights.

**19.8.2** The nous form MUST take the name -- for a concrete nous, one the daemon's accounts and
installed harnesses run, or one typed, with an effort; for a virtual nous, a name -- the number of
tries, the wait policy and the limit, and MUST offer editing a virtual nous's graph and every nous's
`then` with the graph form.

**19.8.3** The graph form MUST let the user add, change and remove nodes -- a use node naming one
nous, concrete or virtual; a balance node naming a strategy, its nous each with a weight, and its
spread -- choose the start node, and set each node's edges, by fault class or `*`, to another node.

**19.8.4** The interface MUST refuse a nous or a graph that Section 4.11.4.9 of [CORE] or Section
3.6.2 of [FILES] refuses, saying why, MUST let the user rename a virtual nous, and MUST refuse
removing one that another nous names, saying which.

### 19.9. Runtimes

**19.9.1** The Runtimes page MUST list every runtime under its backend: ssh hosts, docker hosts,
docker swarms, Apple containers and Slurm clusters, each with what it is saved with.

**19.9.2** The Runtimes page MUST offer adding each kind on one form wherever one is asked for,
importing the hosts an ssh config names without writing to that config, and per runtime `edit`,
`check` and **Remove**, all applied at once.

**19.9.3** Each runtime form MUST take where the harness of work on it runs, in order, written as
`self`, `local` and `<backend>:<name>`, and the saved runtimes it falls back to, in order.

**19.9.4** The interface MUST ask a runtime what it has when it is added, edited or checked, in the
background, saying what it has, what it is saved to hand out that it has not got, and why where it
cannot be reached; an import MUST ask nothing.

**19.9.5** The interface MUST NOT read a key file a runtime names.

### 19.10. Backup

**19.10.1** The Backup page MUST list every backup target by its name, its URL with any credential
hidden, its branch, when it is used, and whether it is a default.

**19.10.2** The target form MUST take a name of one short word no other target has, a URL, a branch,
`On session close`, `Every N minutes`, `On epic end` and `Default`.

**19.10.3** **Download…** MUST list every epic a saved target holds, fetched in the background,
by machine and then by directory, newest first, the ones already here marked, and `enter` MUST
download one as an import does, saying where it landed and, where it cannot be resumed here, why.

**19.10.4** **Download…** MUST list the chats a saved target holds among its epics, each named
`chat` where an epic names its flow, and `enter` on one MUST download it into this machine's chats
(Section 8.3.14 of [CORE]), saying that it is carried on with `/resume` in a chat.

### 19.11. Workspace

**19.11.1** The Workspace page MUST name this directory, show the flow last set up in it, offer
**Chat agent**, the chat agent it remembers (Section 8.3.8 of [CORE]), set on the agent sheet, and
offer **Forget**, which on save clears what this directory remembers from the next launch.

**19.11.2** The Workspace page MUST offer **Archived chats**, which opens a pick list of the
archived chats of this directory, newest first, each by its title (`chat.list` with `workspace` and
`archived`, Section 4.25 of [DAEMON]). `enter` on one MUST put it back among the others at once
(`chat.unarchive`), not held for the save, MUST say so, and the chat MUST leave the list.

### 19.12. Usage

**19.12.1** The Usage page MUST show what the epics spent by day and by flow, of this directory or
of every directory on this machine, over 7, 30, 90 or 365 days, read in the background, and MUST
hold nothing.

### 19.13. First start

**19.13.1** Where error reporting is unanswered, the interface MUST ask once in a box whether hmz
can report its own failures, saying what would be sent and what never would, and MUST leave it
unanswered, to ask at the next start, where the box is left by `esc` or a click outside it.

## 20. Monitor

### 20.1. Reaching it

**20.1.1** `←` on an empty editor, with the offer list closed and outside a chat, MUST open the
monitor; `esc` and commands MUST NOT open it.

**20.1.2** `→` on the monitor's empty editor MUST return to the view last read; reading a node MUST
return to that node's view.

**20.1.3** Every command MUST work from the monitor's editor as from the home view, `/claim`
excepted.

**20.1.4** Opening the monitor MUST NOT be refused; the monitor MUST be redrawn at least every 0.5
seconds while the epic goes, and MUST stop every clock where the epic stopped.

**20.1.5** The monitor's status line MUST say it is the monitor and whether it is the graph or the
list, and MUST show the keys that work.

### 20.2. Nodes

**20.2.1** The monitor MUST lead with a node for the epic, saying how it stands, how many agents
work, how many turns were taken, how long it has gone and each budget limit against what is spent of
it.

**20.2.2** The monitor MUST then show one node per outworlder, saying whose it is and whether it is
read.

**20.2.3** The monitor MUST then draw the agents as a graph: one box per agent that is working or
has taken a turn, in the flow's order, each saying whether it works, its clock, its harness, model
and effort, its turns, sessions and tokens, `reading` or `unread`, and the environments of its
sessions; with the handovers between neighbouring boxes above each, the latest marked.

**20.2.4** `ctrl+t` or a click on the switch MUST turn the graph into a list of the same nodes
without the handovers, the working nodes first, and back.

**20.2.5** `space` or a click on its edge MUST open an agent out to its sessions, each with its
turns, tokens, clock and environment, and shut it again.

**20.2.6** Under each agent, or each session of an opened agent, the monitor MUST show the
sub-agents started, the first 4 and how many more.

**20.2.7** The monitor MUST then show the flows running, innermost last; the params not at their
default; the frontends reading where more than one; the handovers between boxes that are not
neighbours; the tokens and money per model in the order first spent; and the tokens per kind, floors
marked.

**20.2.8** `↑` and `↓` MUST move between nodes, and `enter`, a click, or a double click on an agent
MUST read the node: an agent's view, a session's view, an outworlder's view.

**20.2.9** The epic node MUST open the epic page once an epic has started.

**20.2.10** An environment node MUST open the environment page: its kind, where it is, what the flow
declared of it, where each of its sessions' harnesses went, and its sessions, each readable.

### 20.3. Epic page

**20.3.1** The epic page MUST show, live, the epic's time, spend and tokens; its budget against what
is spent of each limit; how it was set up; and the flows it called.

**20.3.2** For an epic that is not a chat, the epic page MUST offer **Stop** while it runs and
**Force stop** while it stops, each asked first in a box.

### 20.4. Board

**20.4.1** Where the epic keeps a board, the monitor MUST show each line of it as a node and a node
to add one.

**20.4.2** Editing a board line MUST ask its name then its value, MUST apply at once, and MUST
remove the line when it is saved empty.

**20.4.3** A board line that the flow owns MUST be refused for editing, saying the flow owns it.

### 20.5. Exomyth from the monitor

**20.5.1** `ctrl+e` or a click on `Exomyth` above the graph MUST open the epic going in Exomyth, and
MUST NOT be offered for a chat.

## 21. Exomyth

**21.1** Exomyth MUST draw an epic as a timeline of its processes, each session a process under the
one that started it, foldable, each lane a row of its spans drawn to an eighth of a cell and
coloured by category in the theme's colours, under a ruler of time.

**21.2** Exomyth MUST offer zooming and panning around the span under the cursor; moving between
spans and rows; searching spans by name; a pane of the span or its process; and picking a range from
one span to another, summed by category in the pane.

**21.3** Exomyth MUST offer, a `tab` away each, a flame graph of where the range or the time on
screen went, weighed by time, tokens in, tokens out or count, each agent's sessions merged or apart;
and a table of every slice name, sorted by any column, a slice picked found on the timeline.

**21.4** Exomyth MUST read the epic in the background, MUST read it again every 3 seconds while
the epic goes, keeping what is on screen, and MUST stay responsive at fifty thousand spans.

**21.5** `esc` MUST leave the search, then the range, then the pane, then Exomyth.

## 22. Completion and history

**22.1** The offer list MUST offer, for a `/` and part of one word, the commands available now whose
name starts with it; for `/flow ` and a part, the flows; for `/settings ` and a part, the nine pages
in order; for `$` and a part, `$` and each flow; in a chat, also what Section 11.10 states; and
nothing for three or more words.

**22.2** The offer list MUST offer nothing for a word that is already whole, MUST be reconsidered as
the cursor moves as well as the text, and MUST keep the focus in the editor.

**22.3** Where nothing is offered and the first word is a command available now, the offer list MUST
show one hint row saying what it takes and does.

**22.4** Taking an offer MUST replace the last word and add a space, and MUST NOT send the line.

**22.5** The interface MUST record every line sent in the history, skipping blank lines and a line
equal to the one before, each with the directory it was sent in.

**22.6** `↑` on the editor's first row and `↓` on its last MUST walk the history, of this directory
alone where it has any, and walking off the newest end MUST restore the draft.

## 23. Selecting and copying

**23.1** A drag MUST copy the text from press to release, a double click the word, and a triple
click the whole logical line, as the text was written rather than as it was wrapped.

**23.2** The interface MUST copy through the terminal to the clipboard of the machine the terminal
runs on.

**23.3** A selection MUST be dropped when its view is cleared or switched and when the width
changes.

**23.4** The interface MUST NOT scroll the transcript out from under a reader.

## 24. Keys

**24.1** The interface MUST bind exactly the keys of the following table, each doing what its row
states where its row's context holds.

| No. | Context | Key | Action |
| --- | --- | --- | --- |
| 24.1.1 | app | `ctrl+c` | Section 14 |
| 24.1.2 | app | `ctrl+q` | `/exit` |
| 24.1.3 | log | `shift+tab` | next view of the round; nothing in a chat |
| 24.1.4 | log, offers closed | `tab` | previous view of the round; nothing in a chat |
| 24.1.5 | log, empty editor, offers closed, not a chat | `←` | open the monitor |
| 24.1.6 | editor, offer highlighted | `enter` | take the offer |
| 24.1.7 | editor | `enter` | send the line |
| 24.1.8 | editor | `shift+enter`, `ctrl+j` | break the line |
| 24.1.9 | editor, first or last row | `↑`, `↓` | older or newer history entry |
| 24.1.10 | editor, btw mode, offers closed | `esc` | leave btw mode |
| 24.1.11 | offers open | `↑`, `↓` | move the highlight |
| 24.1.12 | offers open | `tab` | take the highlight |
| 24.1.13 | offers open | `esc` | hide offers until the text changes |
| 24.1.14 | menu list | `↑`, `↓` | previous or next row, wrapping |
| 24.1.15 | menu list | `enter`, click | open, take, drop values, or begin and keep a written row |
| 24.1.16 | menu list | `→` | into what the row opens |
| 24.1.17 | menu list | `←`, `backspace` | up to the menu this one was opened from |
| 24.1.18 | menu list, row with a menu | `m` | the row's menu |
| 24.1.19 | menu list, searchable | `/` | open the search box |
| 24.1.20 | menu | `esc` | put back the row written, else clear the search, else leave |
| 24.1.21 | menu | `tab`, `shift+tab` | next or previous of search box, list, buttons |
| 24.1.22 | menu search box | `enter`, `↓` | to the list, keeping the filter |
| 24.1.23 | menu button | `←`, `→` | previous or next button, wrapping |
| 24.1.24 | menu button | `↑` | to the list |
| 24.1.25 | menu button | `enter`, click | press it |
| 24.1.26 | form, written row | typing, paste | begin writing; first character replaces |
| 24.1.27 | form, writing | `enter` | keep and move to the next unanswered row |
| 24.1.28 | form, writing | `esc` | put the row back |
| 24.1.29 | form, writing a multi-line row | `shift+enter`, `ctrl+j` | break the line |
| 24.1.30 | form, writing a path | `tab` | complete the path |
| 24.1.31 | dropdown | `↑`, `↓` | move |
| 24.1.32 | dropdown | `enter`, click | pick the value |
| 24.1.33 | dropdown | `esc`, click outside | pick nothing |
| 24.1.34 | box | arrows, `tab`, `shift+tab` | next or previous button, wrapping |
| 24.1.35 | box | `enter`, click | press the button |
| 24.1.36 | box | `esc`, click outside | answer nothing |
| 24.1.37 | `/settings`, `/flow` page | `←`, `backspace`, `esc` | out to the page above |
| 24.1.38 | `/epics` | `ctrl+t` | this directory or this machine |
| 24.1.39 | `/epics` | `i` | import an epic |
| 24.1.40 | `/epics` of another daemon | `n` | new epic there |
| 24.1.41 | following an epic there | `esc` | back to the list |
| 24.1.42 | monitor, empty editor, offers closed | `↑`, `↓` | previous or next node |
| 24.1.43 | monitor, empty editor | `enter`, click | read or open the node |
| 24.1.44 | monitor, empty editor | `space` | open or shut an agent |
| 24.1.45 | monitor, empty editor, offers closed | `→` | back to the view last read |
| 24.1.46 | monitor | `ctrl+t` | graph or list |
| 24.1.47 | monitor, empty editor, not a chat | `ctrl+e` | the epic going in Exomyth |
| 24.1.48 | environment or epic page | `esc`, `←`, `backspace` | back to the monitor |
| 24.1.49 | board entry | typing, `backspace` | write, delete |
| 24.1.50 | board entry | `enter` | on to the value, then save |
| 24.1.51 | Exomyth | `w`, `+`, `=` / `s`, `-` | zoom in / out |
| 24.1.52 | Exomyth | `a`, `shift+←` / `d`, `shift+→` | pan back / on |
| 24.1.53 | Exomyth | `↑`, `↓`, `pageup`, `pagedown` | row above or below |
| 24.1.54 | Exomyth | `←`, `→` | span before or after |
| 24.1.55 | Exomyth | `enter` | pane of the span, or shut it |
| 24.1.56 | Exomyth | `p` | pane of the process, or shut it |
| 24.1.57 | Exomyth | `v` | begin, hold or drop a range |
| 24.1.58 | Exomyth | `f` | fit the range or the span |
| 24.1.59 | Exomyth | `0` | the whole epic |
| 24.1.60 | Exomyth | `space` | fold or open the process |
| 24.1.61 | Exomyth | `/` | search spans by name |
| 24.1.62 | Exomyth | `n`, `N` | next or previous found |
| 24.1.63 | Exomyth | `tab`, `shift+tab` | next or previous of timeline, flame, slices |
| 24.1.64 | Exomyth flame | `t` | next weight |
| 24.1.65 | Exomyth flame | `m` | sessions merged or apart |
| 24.1.66 | Exomyth slices | `o`, `O` | next sort column, reverse order |
| 24.1.67 | Exomyth | `r` | read again |
| 24.1.68 | Exomyth | `esc` | out of search, range, pane, then back |
| 24.1.69 | anywhere | drag, double click, triple click | copy (Section 23) |
| 24.1.70 | editor, empty, the answerable question has a schema | `enter` | open its sheet (Section 10.12) |
| 24.1.71 | question sheet, a row of values side by side | `←`, `→` | previous or next value (Section 10.13) |
| 24.1.72 | app | the key of a view | Section 25.1.4 |
| 24.1.73 | app | `ctrl+b` | the navigator (Section 27.1) |
| 24.1.74 | app | `ctrl+k` | Search (Section 27.5) |
| 24.1.75 | navigator | `↑`, `↓` | move along the list |
| 24.1.76 | navigator, a chat, an epic or a session | `enter` | open it (Section 27.3) |
| 24.1.77 | navigator, a heading | `enter` | fold or unfold the group |
| 24.1.78 | navigator | `n`, `N` | a new chat, a new epic (Section 27.4.1) |
| 24.1.79 | navigator, a row | `p` | pin or unpin |
| 24.1.80 | navigator, a row | `u` | mark unread or read |
| 24.1.81 | navigator, a row or a folder | `.` | its menu (Sections 27.4.3 and 27.4.4) |
| 24.1.82 | navigator | `g` | the next grouping (Section 27.2.3) |
| 24.1.83 | Search | `↑`, `↓` | move along what was found, round the ends |
| 24.1.84 | Search | `enter` | open the one moved to (Section 27.3) |
| 24.1.85 | Search | `tab`, `shift+tab` | next or previous tab |
| 24.1.86 | Search | `f2`, `f3`, `f4` | next of how it went, of the folders, of the flows |
| 24.1.87 | Search | `f5` | clear what was typed and the filters |
| 24.1.88 | Search | `pgdn`, `pgup` | an older page, a newer page |
| 24.1.89 | Search | `esc` | close Search |
| 24.1.90 | Flows page | `tab` | the other tab (Section 31.1.1) |
| 24.1.91 | Flows page, installed flow | `enter`, `n`, `u`, `s`, `x` | open, new epic, update, switch release, uninstall (Section 31.1.3) |
| 24.1.92 | Flows page, flowverse | `enter`, `a`, `f`, `x` | open, add, fetch, remove (Section 31.1.4) |
| 24.1.93 | Flows page, flow of a flowverse | `enter`, `i`, `x`, `f` | releases, install, uninstall, fetch (Section 31.1.5) |
| 24.1.94 | Flows page, release | `enter`, `x` | install or switch to, uninstall (Section 31.1.5) |
| 24.1.95 | Download page | `enter`, `f`, `t` | download, fetch again, next target (Section 31.2.3) |
| 24.1.96 | Import page | `enter` | ask for the file (Section 31.2.4) |
| 24.1.97 | Export page | `enter` | export the epic (Section 31.2.5) |
| 24.1.98 | a page | `esc` | back one list, then close (Section 25.1.5) |
| 24.1.99 | environment pane | `ctrl+w` | widen the context (Section 30.1.7) |
| 24.1.100 | environment pane, several envs | `tab` | turn to the next env (Section 30.1.3) |
| 24.1.101 | Files pane, tree | `enter` | open or shut the directory, or show the file |
| 24.1.102 | Files pane | `e` | open the file in the editor (Section 30.2.3) |
| 24.1.103 | Files pane, tree | `n`, `shift+n` | new file, new directory |
| 24.1.104 | Files pane, tree | `r`, `d` | rename, delete after a box |
| 24.1.105 | Files pane | `ctrl+p`, `/` | show a file by name, search in files |
| 24.1.106 | Files pane, file shown | `backspace` | back to the tree |
| 24.1.107 | Changes pane, changes | `enter` | the keys to the diff |
| 24.1.108 | Changes pane, changes | `s`, `u`, `x` | stage, unstage, discard after a box |
| 24.1.109 | Changes pane, changes | `shift+s`, `shift+u` | stage all, unstage all |
| 24.1.110 | Changes pane, changes | `c`, `l`, `p` | commit, the commits, the snapshots |
| 24.1.111 | Changes pane | `r` | read again |
| 24.1.112 | Changes pane, snapshots | `enter` | rewind after a box |
| 24.1.113 | Changes pane, diff, commits or snapshots | `backspace` | back to the changes |
| 24.1.114 | Terminal pane, tabs | `enter` | the keys to the terminal |
| 24.1.115 | Terminal pane, tabs | `left`, `right` | previous or next terminal |
| 24.1.116 | Terminal pane, tabs | `n`, `x` | new terminal, close after a box |
| 24.1.117 | Terminal pane, terminal | `~.` at the start of a line | the keys to the tabs |
| 24.1.118 | Terminal pane, terminal | any other key | typed into the terminal |
| 24.1.119 | New chat page | `tab`, `shift+tab` | next or previous of chips, box, list (Section 28.2.5) |
| 24.1.120 | New chat page, chip | `enter`, click | drop the list its value is picked from |
| 24.1.121 | New chat page, box | `enter` | start the chat (Section 28.2.6) |
| 24.1.122 | New chat page, list | `↑`, `↓`, `enter` | move; open the chat or the harness session |
| 24.1.123 | Details view | `↑`, `↓` | previous or next chip or action |
| 24.1.124 | Details view | `enter`, click | change the chip, or do the action (Section 28.3) |
| 24.1.125 | Harness session page | `↑`, `↓`, `pageup`, `pagedown` | scroll what was said |
| 24.1.126 | Harness session page | `enter` | `Continue in chat` (Section 28.4.2) |
| 24.1.127 | New chat or Harness session page | `esc` | close the page |
| 24.1.128 | log screen | `ctrl+e` | open the New epic page (Section 29.1) |
| 24.1.129 | New epic page | `ctrl+e` | close the page, keeping what it holds |
| 24.1.130 | New epic page | `ctrl+s` | Start (Section 29.4) |
| 24.1.131 | log screen | `ctrl+o` | the Epic view (Section 29.5) |
| 24.1.132 | Epic view | `←`, `→`, `1`–`4` | previous or next tab, wrapping; the tab of that number |
| 24.1.133 | Epic view | `↑`, `↓` | row above or below |
| 24.1.134 | Epic view, Board, a line | `enter` | change what the line says |
| 24.1.135 | Epic view, Board | `a` | add a line |
| 24.1.136 | Epic view, Board, a line | `d` | remove the line, once asked |
| 24.1.137 | Epic view, People, a role | `enter` | claim, take over or release the role |
| 24.1.138 | Epic view, People, a role | `w` | away or back for the role |
| 24.1.139 | Epic view, People | `shift+w` | away or back for every role |
| 24.1.140 | Epic view, Side questions, a side conversation | `enter` | ask in it |
| 24.1.141 | Epic view, Side questions | `a` | ask in a new side conversation |
| 24.1.142 | Epic view, Side questions, a side conversation | `d` | close it, once asked |

**24.2** `esc` MUST NOT open the monitor, and `←` MUST NOT stop anything.

**24.3** `shift+enter` MUST break the line where the terminal reports it; `ctrl+j` MUST break the
line in every terminal.

## 25. Zones and views

### 25.1. Zones

**25.1.1** The log screen MUST have three zones side by side: the _navigator_ on the left, the log
of Section 4 in the middle, and the _context_ on the right. A zone other than the log MUST take no
column until a view is open in it.

**25.1.2** A _view_ is one thing opened in the navigator, in the context, or over the whole screen
as a _page_. A view MUST open only in the place it is specified for, and opening a view MUST NOT
move or close what is open in another zone.

**25.1.3** A zone with a view open MUST show the view's title in capitals over a heavy rule, in the
colour of what has the keys while the keys are in it and dim otherwise.

**25.1.4** A view with a key MUST, on that key: open with the keys where it is not open; take the
keys where it is open and they are elsewhere; and close, the keys going to the editor, where the
keys are in it. That key MUST do so whatever has the keys.

**25.1.5** `esc` in a zone MUST give the keys to the editor and leave the zone open; `esc` on a
page MUST close the page.

**25.1.6** A view open as the interface opens MUST NOT take the keys from the editor.

### 25.2. The hint line

**25.2.1** Under the status line the interface MUST draw one _hint line_: every key the view with
the keys takes, each with what it does, then `esc` with `Back` where a view has the keys, then the
key of every other view that has one with what it opens. The hint line MUST NOT be drawn where it
would be empty.

**25.2.2** A view MUST NOT act on a key the hint line does not show while that view has the keys.

### 25.3. Colour and drawing

**25.3.1** The interface MUST have the themes `humanfia-dark` and `humanfia-light`, whose colours
are those of the web interface's dark and light palettes (Section 3.12 of [WEB]), and the theme
`terminal`, which names only the terminal's own sixteen colours and its own background.

**25.3.2** In a humanfia theme: what can be followed, and what has the keys, MUST be cyan; what is
picked out, and the one thing to press, MUST be pink, and a screen MUST NOT draw more than one such
thing in pink apart from the row under the cursor; green MUST be drawn only in the mark and beside
cyan, never beside pink; failures MUST be red and warnings gold.

**25.3.3** What the interface draws of its own MUST be drawn with flat planes, heavy rules and
square corners, and MUST NOT be drawn with rounded corners or shading.

**25.3.4** The box the interface opens with MUST show the mark -- two stems, one diagonal between
them, and a dot, the dot green -- and the name beside it where the terminal is wide enough.

### 25.4. Order and removal

**25.4.1** In every list a view draws, what waits on the person MUST come first.

**25.4.2** A view MUST ask before it removes anything, naming what is removed.

### 25.5. Texts

**25.5.1** Every text a view draws that is not data MUST be a text the web interface writes ([WEB])
wherever that interface has a text saying the same thing, word for word in its English, and MUST
otherwise be a text kept with hmz for that purpose. A view MUST NOT compose such a text where it is
drawn.

**25.5.2** The texts of a view MUST be drawn in the language of Section 32 where they have a
translation in it, and in English otherwise.

## 26. Keys view

**26.1** `f1` MUST be the key of the _Keys_ view, which opens in the context and whose hint is
`keys`.

**26.2** The Keys view MUST list the key of every view that has one with what it opens, then `esc`
with `Back`, the keys in cyan.

## 27. Navigator and Search

### 27.1. The navigator

**27.1.1** `ctrl+b` MUST be the key of the _navigator_ view, which opens in the navigator zone,
whose title is `Sidebar` and whose hint is `Sidebar`.

**27.1.2** The navigator MUST be open as the interface opens where the terminal is at least 110
columns wide, and closed otherwise.

**27.1.3** The navigator MUST list what the sidebar of the web interface lists (Section 3.5 of
[WEB]) of this machine's daemon: every chat `chat.list` answers, every epic `runs.list` answers,
and, where `settings.get` answers `harness_sessions` true, the sessions `chat.harness.list` answers
of each folder not folded, after that folder's chats and epics. It MUST give every workspace
`workspaces.list` answers a heading, and MUST read nothing off the files of a chat or an epic.

**27.1.4** The navigator MUST read the list again when the interface hears a notice of an epic or
a chat, and otherwise every 5 seconds, and MUST ask the daemon off the thread that draws.

### 27.2. Groups, marks and order

**27.2.1** The first group MUST be `Waiting for you`, holding every chat that is asking and every
epic that is asking or waiting, and MUST be left out where there is none. Its heading, the marks of
its rows and the words that say how they stand MUST be the only pink the navigator draws.

**27.2.2** After it MUST come `Pinned`, holding the rows pinned that do not wait, left out where
there is none; then the rest, as Section 27.2.3 groups it. Within a group, rows MUST stand newest
first by when each was last heard of, an epic that is going standing as heard of now.

**27.2.3** The rest MUST be grouped by `Folder`, by `Date` or as `None`, `g` stepping through them
in that order. By folder: one group a workspace, named by the last part of its path, those an epic
is going in first, then by their latest row, and the rows of no folder last under `No folder`; a
folder whose directory is gone MUST say `missing`, and one that is gone and holds nothing MUST NOT
be listed. By date: `Today`, `Yesterday`, `Last 7 days`, `Last 30 days`, `Older`. As none: one
group, `All`. Grouped other than by folder, the folders MUST stand last as a group `Folders`, each
with how many rows it has.

**27.2.4** A group MUST show at most 20 rows and then a row `Show {n} more`, on which `enter` shows
them all.

**27.2.5** A row MUST show a mark, its title on one line, and at its end how it stands in the word
the web interface's list says it in (`Running`, `Asking`, `Waiting`, `Stopping`; of a chat
`Running`, `Awaiting input`; of a harness session `Read-only`) or, of one at rest, how long ago it
was heard of in the web interface's texts (`just now`, `{n}m ago`, `{n}h ago`, else the month and
day). The mark MUST be pink where it waits on the person, cyan where it is going, the colour of
success where an epic is done, the colour of failure where it failed, was refused or crashed, and
dim otherwise.

**27.2.6** A row marked unread MUST show `●` in cyan beside its mark, and a row pinned `▸`. The row
on the log MUST have its title in cyan. A folded group that holds an unread row MUST show `●` in
its heading. The row under the cursor MUST be a cyan plane while the keys are in the navigator.

**27.2.7** While the keys are in the navigator, a list read again MUST be drawn without moving any
row already listed: a row that changed is redrawn where it stands, a row that left is taken out,
and a new row is put in after the row it would follow. The order of Sections 27.2.1 to 27.2.3 MUST
be restored when the keys leave, and at once after a change the person made with a key of the
navigator, the cursor staying on the row it was on.

**27.2.8** What is pinned, what is unread, the grouping and which groups are folded MUST be kept
in `navigator.json` of the state directory, MUST be read as the navigator opens, and MUST NOT be
asked of or told to a daemon. A notice of a chat or an epic that is not on the log MUST mark it
unread, and opening a row MUST mark it read.

### 27.3. Opening a row

**27.3.1** Opening a chat of the workspace the interface is of MUST do what choosing it on
`/resume` in a chat does, and MUST then give the keys to the editor.

**27.3.2** Opening an epic that a host of the workspace the interface is of goes with MUST attach
the log to that host. Opening any other epic of this machine MUST open the sheet `/epics` opens on
entering it, wherever it ran; `esc` on that sheet with nothing said MUST return to where the epic
was opened from.

**27.3.3** Opening a harness session of the workspace the interface is of whose harness carries a
copy on MUST adopt it (`chat.harness.adopt`) and open the chat made; one that does not MUST say
`Read-only. A session of {harness} cannot be continued in a chat.`

**27.3.4** Opening a chat or a harness session of another workspace MUST open nothing and MUST
say, in the transcript, that it is in that folder and that `hmz` run there opens it; one of no
folder MUST say that it has none and that the web interface opens it.

**27.3.5** Opening the chat already on the log MUST change nothing but where the keys are. A chat
the list says no host holds MUST be opened by asking the hosts which holds it, not by taking the
list's word.

### 27.4. The navigator's keys

**27.4.1** `n` MUST open the view `newchat` where there is one and otherwise do what `/chat` does;
`N` MUST open the view `newepic` where there is one and otherwise do what `/flow` does.

**27.4.2** `enter` on a heading MUST fold or unfold its group.

**27.4.3** `.` on a row MUST open its menu, in the web interface's words: `Open`; `Pin` or `Unpin`;
`Mark as read` or `Mark as unread`; of a chat `Rename`, `Fork` (a chat of this workspace), `Copy
ID`, `Upload`, `Archive` and `Delete`; of an epic `Copy task`, `Copy name`, `Upload` and, where a
host goes with it, `Stop`; of a harness session `Copy session ID`. `Rename`, `Fork`, `Archive` and
`Delete` MUST ask the daemon what the same row of `/resume` asks it, `Delete` asking the person
first; `Upload` MUST ask `chat.backup` or `runs.backup`; `Stop` MUST ask the epic's host to stop
it.

**27.4.4** `.` on a folder MUST open its menu: `New chat here` and `New epic here` (the workspace
the interface is of only), `Search here`, `Copy path`, `Collapse` or `Expand`, and, for a folder
in which `workspaces.list` counts no chat and no epic and says nothing is going, and of which no
row is listed, `Forget`, which MUST ask first, naming the folder, and then ask `workspaces.forget`.

**27.4.5** What a menu's action came to MUST be said in one line under the list, a refusal in the
colour of failure.

### 27.5. Search

**27.5.1** `ctrl+k` MUST be the key of the _Search_ view, a page whose title and hint are
`Search`. It MUST open over whatever has the keys, the editor included, and the same key MUST
close it.

**27.5.2** Search MUST show, top to bottom: one field; the tabs `All`, `Chats` and `Epics`, the
chosen one in cyan; the filters `How it went`, `Folder` and `Flow` with what each is set to; a
heading, `Recents` where nothing narrows the list and `Results` otherwise; what was found, a line
apiece as Section 27.2.5 draws a row, with its folder and its flow before how it stands; which rows
are shown of how many; and its keys. The keys MUST stay in the field.

**27.5.3** Search MUST ask this machine's daemon as Section 3.10 of [WEB] states: on `Chats`,
`chat.list`; on `Epics`, or on `All` with how it went or a flow chosen, `runs.list`; otherwise
both, read from their first row and cut to the page as one list, newest first. Each call MUST carry
what was typed as `q`, the folder as `workspace`, and of `runs.list` how it went as `status` and
the flow as `flow`; a page is 50 rows. Where both are asked, Search MUST NOT turn to a page that
ends past the 200th row.

**27.5.4** What is typed MUST narrow the list once nothing has been typed for 0.2 seconds, asked
off the thread that draws; an answer to what is no longer chosen MUST be dropped.

**27.5.5** `tab` and `shift+tab` MUST change the tab, stopping at either end; choosing `Chats` MUST
clear how it went and the flow, and choosing either of those on `Chats` MUST change the tab to
`Epics`. `f2`, `f3` and `f4` MUST step how it went (`All`, `Running`, `Done`, `Failed`, `Stopped`,
`Unfinished`), the folder and the flow, each coming back to all after its last. `f5` MUST clear
what was typed and the filters and keep the tab.

**27.5.6** `enter` MUST close Search and open the row moved to as Section 27.3 states; `esc` MUST
close it.

**27.5.7** Where nothing was found, Search MUST say so in the web interface's texts: `Nothing is
like that.` with what clearing does where something was typed or filtered for, and otherwise that
there is none yet of the tab's kind.

**27.5.8** `Search here` (Section 27.4.4) MUST open Search with that folder chosen.

## 28. New chat and the chat's chips

### 28.1. Chips

**28.1.1** A _chip_ is one thing a chat starts or goes on with, named and showing the value in
force: `Folder`, `Environment`, `Model`, `Effort`, `Permissions`. `enter` on a chip MUST drop the
list its value is picked from (Section 15), the value in force ticked, and picking nothing MUST
leave the value as it was.

**28.1.2** `Model` MUST offer the models each harness installed on the daemon's machine lists, as
`flows.backends` answers them, a group a harness, and MUST answer with an agent spec. A harness
nobody has asked what it runs MUST be offered as one row which, picked, asks it (`accounts.models`)
and offers the list again; a harness that lists none MUST say so in a row that cannot be picked. A
model picked MUST keep the effort in force where that model takes it, and MUST otherwise have none.

**28.1.3** `Effort` MUST offer `Default`, the model's own, then the efforts the model in force
takes.

**28.1.4** `Permissions` MUST offer the three permissions of Section 8.3.9 of [CORE], narrowest
first, as `Read only`, `Edit this folder` and `Full access`, each with the line the web interface
gives it.

**28.1.5** `Environment` MUST offer `This computer`, then each runtime `runtimes.list` answers
under `Runtimes`. A runtime picked MUST then offer the directories of its machine (`paths.list`
with `env`) to pick one from; picking none, or a machine whose directories cannot be listed, MUST
come to the runtime named alone.

**28.1.6** `Folder` MUST offer the workspaces `workspaces.list` answers whose directory exists,
then `Open folder…`, which MUST walk the directories of the daemon's machine (`paths.list`) and
answer with the one `Use this directory` is picked in.

### 28.2. New chat

**28.2.1** `ctrl+n` MUST be the key of the _New chat_ view, a page whose hint is `New chat`. On
that key while the page is open, the page MUST close.

**28.2.2** The page MUST draw, from the top: the five chips of Section 28.1, each showing the value
a chat started now would have; the box the first message is typed into; and a list. The page MUST
open with the keys in the box.

**28.2.3** The chips MUST open on: the directory the interface was opened in; `This computer`; the
chat agent that folder remembers (`settings.get`), else the first model `flows.backends` lists;
that agent's effort; and `Edit this folder`. Picking another folder MUST read what that folder
remembers, and MUST put the environment back to `This computer`.

**28.2.4** On the page `Environment` MUST also offer `New worktree`, which MUST NOT be pickable,
saying `This folder is not a git repository`, where neither the folder nor a directory over it
holds `.git`.

**28.2.5** `tab` and `shift+tab` MUST move the keys to the next and the previous of the chips, the
box and the list, wrapping; a list with no row MUST be passed over.

**28.2.6** `enter` in the box with nothing typed MUST do nothing. With something typed it MUST start
a chat (`chat.start`) with that as `task`, the agent of `Model` and `Effort` as `agent`, the
permission picked, `worktree` where `New worktree` is picked, `env` where a runtime is, and
`remember` `true`; where no model is in force it MUST instead say `Pick a nous for the chat.` and
drop the list of `Model`.

**28.2.7** A chat of the directory the interface was opened in MUST be started on a new chat host
which the log screen then follows (Section 11), and the page MUST close at once. A chat of another
folder MUST be started with that folder as `workspace`; once it has started the page MUST close and
the log MUST say that it was started there and is read by opening hmz in that folder, and a start
refused MUST be said on the page, which MUST stay open.

**28.2.8** The list MUST hold, first, under `Waiting for you`, each chat of the directory the
interface was opened in whose state is `asking` (`chat.list`), each saying `Asked a question`; then,
under `Harness sessions`, where the setting `harness_sessions` is on, the harness sessions of that
directory (`chat.harness.list`), each naming its harness. The list MUST be read again every 4
seconds. `enter` on a chat MUST close the page and put that chat on the log screen; `enter` on a
harness session MUST open it as Section 28.4 states.

**28.2.9** On the page the start action, drawn at the end of the box, MUST be the one thing drawn
pink; a chip with the keys MUST be cyan.

### 28.3. Details

**28.3.1** `ctrl+g` MUST be the key of the _Details_ view, which opens in the context and whose
hint is `Details`. It MUST be about the chat on the log screen, read by `chat.get` as it opens and
every 4 seconds after, and MUST say `No chat here` where the log screen shows none.

**28.3.2** The view MUST draw the chat's title; that it waits on its person or that it failed,
where it does; `Harness` and `Account`, which cannot be changed; the chips `Model`, `Effort`,
`Permissions`, `Skill or flow` and `Environment`; the directory it works in; under `Usage`, what
the chat has spent, its output tokens and the time it has worked, or `Nothing used yet`, and what
its folder spent over the last 7 days (`runs.usage`); and under `Actions`, `Rename…`, `Fork`,
`Archive` and `Delete chat`. `↑` and `↓` MUST move between the chips and the actions.

**28.3.3** `Model` MUST offer only the models of the chat's own harness and account, and `Model`
and `Effort` picked MUST be asked as `chat.agent`.

**28.3.4** `Permissions` and `Skill or flow` -- `Use the skill` or `Start the flow`, the chat's
preference of Section 8.9.10 of [CORE] -- picked MUST be asked as `chat.set`, and `Environment`
picked as `chat.move`, `This computer` being the chat's folder. Where no host holds the chat, the
view MUST first carry the chat on with nothing said (`chat.start` with `resume` and an empty
`task`), MUST put the log screen on the host that answers, and MUST ask that host.

**28.3.5** `Rename…` MUST ask for the title on the form of Section 18 and ask `chat.rename`; `Fork`
MUST ask `chat.fork` and put the fork on the log screen; `Archive` MUST ask `chat.archive` and
`Delete chat` MUST ask `chat.delete`, each then leaving the log screen on a new chat as `/clear`
does. `Delete chat` MUST first ask, in a box naming the chat by its title, whether to delete it,
and MUST delete nothing unless that is answered yes.

**28.3.6** While a chip is being changed, that chip MUST be the one thing of the view drawn pink.
A refusal MUST be said in the view, in the daemon's words, and MUST change nothing else.

### 28.4. Harness session

**28.4.1** The _Harness session_ view MUST be a page with no key, opened for one harness session
of one workspace. It MUST read the session by `chat.harness.get` with `trace` `true` and draw what
was said in it in the order it was said: each line the user said behind the mark of Section 9, what
the harness said, and the name of whatever else it did, dim. A session whose logs hold nothing MUST
say `Its logs held nothing said.` Opened for no session, it MUST read the workspace's newest.

**28.4.2** The page MUST change nothing of the session. For a session whose row says `continuable`
it MUST draw `Continue in chat`, the one thing on the page drawn pink, and `enter` MUST ask
`chat.harness.adopt`, close the page, and put the chat that answers on the log screen; where that
was opened from the New chat page, that page MUST close too. For any other session it MUST say that
a session of that harness cannot be continued in a chat, and `enter` MUST do nothing.

**28.4.3** `↑`, `↓`, `pageup` and `pagedown` MUST scroll what was said, and `esc` MUST close the
page.

## 29. New epic and the epic's context

### 29.1. The New epic page

**29.1.1** `ctrl+e` MUST be the key of the _New epic_ page, whose hint is `new epic`. From the log
screen it MUST open the page; on the page it MUST close it; and while any other screen is over the
log -- a menu, the monitor, an environment page -- the key MUST be that screen's, as though the page
had no key (Section 24.1.47 stands).

**29.1.2** The page MUST be one form (Section 15), every row of it on one list in this order, each
group under its heading in capitals over a heavy rule: `Flow`; under `Environment`, `Folder` and
one row per environment role the flow does not fill itself; `Task`; under `Agents`, one row per
agent role the flow does not fill itself; under `Parameters`, one row per property of the flow's
params schema; under `Budget`, `Cost, $`, `Time, min`, `Output tokens`, then `Cost graceful`, `Time
graceful` and `Tokens graceful`; under `Backup`, one switch per backup target, where there is one;
under `Options`, `Profile flow` and `Profile environment`; and `Resume`, for a flow that can be
picked up. No row MUST be reached through another, and a group with no row MUST NOT be drawn.

**29.1.3** A row MUST be drawn on one line, its value at the far end, and what the row under the
cursor is for MUST be said under the list.

**29.1.4** The page MUST read what it offers of the daemon and, but for the sheets `More options`
opens (Section 16), MUST NOT load a flow itself: the
flows of the folder and the one it last set up (`flows.list`), what the flow declares and what the
folder last set it up with (`flows.get`), the harnesses and their models (`flows.backends`), every
virtual nous (`nous.list`), the runtimes (`runtimes.list`), and the backup targets and their
defaults (`settings.get`).

**29.1.5** The page MUST open on the folder the interface is open in, on the flow that folder last
set up -- else the first on offer -- with every row holding what `remembered` of `flows.get` holds
for it: the agents, the environments, the params, the limits of the budget with the time in whole
minutes, each grace, each profiling switch, and the backup targets, those being the defaults where
none was remembered. The task MUST open empty, with the cursor on it.

**29.1.6** Where no flow is on offer the page MUST say `No flow installed yet.` under the list,
and Start MUST be refused on the `Flow` row with `Install a flow first, from Flows.`

### 29.2. Rows

**29.2.1** `Flow` MUST drop every flow on offer under the heading of whose it is, each with what it
is for; picking one MUST set every row below as Section 29.1.5 states for that flow.

**29.2.2** `Folder` MUST be written as a path, completed as Section 15 completes one. Kept, it MUST
read the page again for that folder as Section 29.1.4 and 29.1.5 state. Left empty it MUST read `No
folder`, and the epic MUST start in a folderless workspace (Section 4.7.1.3 of [DAEMON]).

**29.2.3** An agent role's row MUST drop, in this order: what it holds, where the list has it not;
every virtual nous under `Virtual`; under each harness that can fill the role, up to six models of
that machine's own sign-in, each as `<cli>/<model>:auto`; and `More options`, which MUST open the
agent sheet of Section 16 on what the row holds and hold what it is saved with. A role nothing
installed can fill MUST say `No harness installed here can fill it.` An empty row MUST read `Pick
a nous`.

**29.2.4** A harness that can fill a role and has never been asked what it runs MUST be asked
(`accounts.models`) once the page has drawn, without the page waiting for it.

**29.2.5** An environment role's row MUST drop `Folder`, which is the row left empty; each runtime
saved, as `<backend>@<name>`; and `More options`, which MUST open the environment sheet of Section
16 and hold what it answers.

**29.2.6** A param MUST be asked as the form of Section 10 asks a field of that schema: a choice
dropped under its row, a list or JSON written over several lines, a secret drawn as bullets, a
default written as it opens.

**29.2.7** A switch MUST be `on` or `off`, dropped under its row as Section 15 drops one.

**29.2.8** `Resume` MUST drop `None` and up to twelve of the folder's latest epics of the flow that
can be picked up and are not going. Picking one MUST set the rows as that epic ran (`runs.get`),
put its task in an empty `Task`, and have Start pick it up.

### 29.3. Leaving

**29.3.1** `esc` MUST close the page without asking. What the page held MUST be kept for as long as
the interface is open, and the page opened again MUST hold it where the same flow is picked.

### 29.4. Start

**29.4.1** The page MUST have one button, `Start`, apart at the far end of its bar, and `ctrl+s`
MUST press it from any row. `enter` keeping a written row MUST move to the next row still to be
answered, and to `Start` where none is.

**29.4.2** Start MUST first be refused, with no call of the daemon, for: no flow (`Pick a flow
first.`), an empty task (`Describe the task`), a required agent role with nothing picked (`Pick an
agent for <role>.`), a param the form of Section 10 refuses, a limit that is not a number, and no
limit at all (`Set at least one limit of the budget.`). Each MUST be said in red under the row it
is about, and the cursor MUST go to the first of them.

**29.4.3** Start MUST then have the daemon check the set-up (`flows.check`) and MUST start nothing
it refuses. A refusal that names a role, a param, the budget or the epic picked up MUST be said
under that row, the cursor going to it; any other MUST be said under the list.

**29.4.4** In the folder the interface is open in, Start MUST start the epic as saving `/flow` and
a `$` line do (Sections 16 and 8): the set-up written down for the folder, and the epic followed on
the log screen. It MUST be refused under the list while an epic is going there, and while an epic
of another daemon is followed.

**29.4.5** In any other folder, and in none, Start MUST start the epic on that folder's own host
(`epic.attach`, `epic.start` with `remember`), let go of it, and say in the transcript where it
started and that `/epics` lists it.

**29.4.6** `backup` MUST be sent absent while the folder remembered none and no switch was moved,
so that the epic follows the defaults; `graceful` MUST be one flag where the three agree.

### 29.5. The Epic view

**29.5.1** `ctrl+o` MUST be the key of the _Epic_ view, which opens in the context and whose hint
is `epic panel`. While a screen is over the log the key MUST do nothing.

**29.5.2** The view MUST have four tabs, `Details`, `Board`, `People` and `Side questions`, drawn
across its top each after its number, the open one in the colour of what has the keys. `←` and `→`
MUST turn to the tab before and after, wrapping, and `1` to `4` to the tab of that number.

**29.5.3** The tab open and the row each tab's cursor is on MUST be kept for as long as the
interface is open: the view closed and opened again MUST be on that tab and that row.

**29.5.4** While the view has the keys the hint line MUST show, in place of Section 25.2.1's keys
of the view: `←/→` `tab`, `↑/↓` `move`, then every key the open tab takes on the row under the
cursor, each with the web interface's word for what it does there now.

**29.5.5** With no epic on the log screen -- none started, or a chat -- every tab MUST say `No epic
is going here.`

**29.5.6** `Details` MUST say `Running`, `Stopping` or `Ended` with the epic's name, then what
the epic page of Section 20 says under `Figures`, `Budget`, `Setup` and `Flows`, read again at
least every second.

**29.5.7** `Board` MUST list each line of the board with what it says, and under it what it is for,
who wrote it and whose it is. `enter` MUST open the board entry of Section 20 on the line and `a`
on a new one; `d` MUST remove the line. Removing a line -- by `d`, or by saving it empty -- MUST
first ask `Remove <key>?`. A line the flow owns MUST NOT be changed or removed, and MUST say `Only
the flow changes this line`. An epic with no board MUST say `This flow keeps no board.`, and an
empty board `Nothing is on the board yet.`

**29.5.8** `People` MUST list each role a person fills with who holds it -- `You`, the name of the
frontend holding it, or `Anyone` -- and `Away` where nobody is there for it. `enter` MUST claim a
role nobody holds, take over one another frontend holds, and release one this interface holds
(`epic.claim`, `epic.release`); `w` MUST set the role away or back and `shift+w` every role
(`epic.afk`). An epic with no such role MUST say `This flow has no role for a person.`

**29.5.9** `Side questions` MUST list each side conversation the daemon holds about the epic
(`btw.list` of the epic by name, read again at least every two seconds while the tab is open) as
`btw · <agent>/<n>`,
with each question asked in it and its answer, and `Answering…` under one not answered yet.

**29.5.10** `a` MUST ask in a new side conversation and `enter` in the one under the cursor
(`btw.ask`): on a form of two rows, `Ask it of` -- every session of the epic, newest first, absent
for a side conversation already open -- and `Side question`. A refusal MUST be said under the
list. `d` MUST close the side conversation under the cursor (`btw.leave`), first asking.

**29.5.11** A side question asked here MUST NOT enter btw mode (Section 12), and MUST NOT reach
the epic.

### 29.6. Faces

**29.6.1** The line of Section 10.17 MUST read `The custom view is in the web page<where>; Enter
answers here with the plain form`, `<where>` being `: <address>` where the address is known and
` (hmz web)` otherwise.

## 30. Environment panes

### 30.1. The panes

**30.1.1** `f5`, `f6` and `f7` MUST be the keys of the views _Files_, _Changes_ and _Terminal_, each
an _environment pane_ that opens in the context (Section 25.1.4), whose hints are `Files`,
`Changes` and `Terminal`. Opening one MUST NOT take the editor's text, close what the log shows or
stop a turn; `/env` (Section 7.20) MUST go on opening its sheets as it did.

**30.1.2** A pane MUST show one env of those `/env` would list (Section 7.20.1): one that is open
and has the pane's capability -- files for Files, git for Changes, a shell for Terminal (Section
7.20.3). It MUST show the env the panes of that chat or epic were last turned to (Section 30.1.3)
where that env still is one of them, and otherwise the first of them in the order `/env` lists
them.

**30.1.3** Where more than one env has the pane's capability, the pane's first row MUST name the
env shown and its place among them, and `tab` MUST turn the pane to the next of them. The env
turned to MUST be remembered for that chat or epic, for all three panes, for as long as the
interface runs.

**30.1.4** A pane MUST say `No environment is open here yet.` where the host lists no env, and
that this environment has no files, changes or terminal where envs are open and none has the
pane's capability, and MUST then ask the host nothing.

**30.1.5** A pane MUST read what it shows again when the host says an env was used or a turn
ended, and when the envs the host lists change.

**30.1.6** A pane MUST draw, on a line of its own at its foot, every key it takes where the keys
are now with what each does, in the texts of Section 25.5; that line is part of the hint line for
Section 25.2.2. `esc` MUST give the keys to the editor and leave the pane as it is (Section
25.1.5), except in a terminal that has the keys (Section 30.4.3).

**30.1.7** `ctrl+w` in a pane MUST make the context one step wider: from the 48 columns it opens
at, to half the screen, to four fifths of it, and back to 48. The width MUST stay until it is
changed again.

**30.1.8** A pane MUST ask, in a box that names what goes, before it deletes a file or a folder,
discards a change, rewinds an env or closes a terminal that is running.

### 30.2. Files

**30.2.1** Files MUST draw the env's workdir as a tree (`env.list`), directories first: `enter` on
a directory MUST open it under its row, a step in, or shut it; `enter` on a symbolic link MUST do
what it would to what the link leads to.

**30.2.2** `enter` on a file MUST show it in the pane in place of the tree, read-only, with line
numbers and its syntax highlighted by its name, and `backspace` MUST put the tree back. A file
over 1 MiB MUST NOT be shown, and the pane MUST say so; a file that is not UTF-8 text MUST be shown
with what cannot be read replaced, and the pane MUST say it is not UTF-8 text. Reading a file MUST
NOT write it.

**30.2.3** `e` on a file, in the tree or shown, MUST open it in the editor of Section 7.20.5, over
the screen, which writes as that section states; leaving the editor MUST return to the pane, which
MUST then show the file as written.

**30.2.4** In the tree, `n` MUST ask for a name and make an empty file of it (`env.write` with
`if_match` `""`) and open it in the editor; `shift+n` MUST ask for a name and make a directory
(`env.mkdir`); each in the open directory under the cursor, else beside the row under it. `r` MUST
ask for a new name of the row under the cursor (`env.rename`), and `d` MUST delete it
(`env.remove`) after the box of Section 30.1.8.

**30.2.5** `ctrl+p` MUST list the env's files (`env.find`) to be narrowed by typing and MUST show
the one picked; `/` MUST ask for a text, list the lines that hold it (`env.search`), and show the
file of the one picked at that line.

### 30.3. Changes

**30.3.1** Changes MUST say where the repository stands -- its branch, or its commit where none is
checked out, and its upstream with how far ahead and behind -- and MUST list the env's git status
(`env.git.status`) in the groups of Section 7.20.7, each headed by its name and count.

**30.3.2** Under the list the pane MUST draw the change of the file under the cursor
(`env.git.diff`, `staged` for one under Staged Changes) highlighted as a diff, following the
cursor, and MUST say so in place of a diff for a binary file and for a change that is empty.
`enter` MUST give the keys to the diff, to scroll it, and `backspace` MUST give them back to the
list.

**30.3.3** `s` MUST stage the file under the cursor and `u` unstage it, a renamed file with the
path it was renamed from; `shift+s` MUST stage every change and `shift+u` unstage every one
staged; `x` MUST discard the file under the cursor (`env.git.discard`) after the box of Section
30.1.8. After each the list MUST be read again, the cursor staying with the file.

**30.3.4** `c` MUST open the form of Section 7.20.7, with a message and whether to amend the last
commit, and MUST commit as it is answered (`env.git.commit`); a refusal MUST be said in the pane
in the host's words.

**30.3.5** `l` MUST list the commits (`env.git.log`), newest first, each by its short hash,
subject, author and date; `p` MUST list the env's snapshots (`env.git.snapshots`), where `enter`
MUST rewind the env to the one under the cursor (`env.git.rewind`) after the box of Section 30.1.8.
`backspace` MUST return from either to the changes, and `r` MUST read again whichever is listed.

### 30.4. Terminal

**30.4.1** Terminal MUST show the terminals alive in the env (`env.term.list`) as a row of tabs,
each by its place and title, the one shown marked. Opening the pane where none is alive MUST
start one (`env.term.open`).

**30.4.2** The terminal shown MUST be drawn in the pane as its screen is: what it prints
(`term`), read as a terminal reads it -- cursor movement, colours, erasing -- at the size of the
pane, which MUST be passed on when it changes (`env.term.resize`); what is drawn MUST be
acknowledged (`env.term.ack`). A terminal come back to MUST first be drawn with what it kept
(`replay`). A terminal MUST go on being drawn while the keys are elsewhere.

**30.4.3** While a terminal has the keys, every key the interface is given, `esc` among them, MUST
be typed into it (`env.term.input`), in order, and MUST do nothing else -- except the keys bound
over everything (Section 24.1.1, 24.1.2 and 24.1.72), and `~.` typed at the start of a line,
which MUST give the keys to the row of tabs and leave the terminal running; `~~` there MUST type
one `~` (Section 7.20.9).

**30.4.4** On the row of tabs, `enter` MUST give the keys to the terminal shown; `left` and
`right` MUST show the terminal before and after it; `n` MUST start another and give it the keys;
`x` MUST close the one shown (`env.term.close`) after the box of Section 30.1.8, and without one
where it has ended.

**30.4.5** A terminal that ends MUST say `[exited]`, with its status where the host gave one, where
it would have printed and on its tab, and MUST give the keys to the row of tabs where it had them.
A terminal that cannot be opened, and input that is refused, MUST be said there in the host's
words.

**30.4.6** Closing the pane MUST leave its terminals running (Section 4.24.4.9 of [DAEMON]).

## 31. Flows page and transfers

### 31.1. The Flows page

**31.1.1** `ctrl+l` MUST be the key of the _Flows_ view, a page whose hint is `Flows`. The page MUST
be headed `FLOWS` over a heavy rule and MUST have two tabs, `Installed` and `Flowverses`, the open
one cyan, and MUST open on `Installed`. `tab` MUST turn from one tab to the other.

**31.1.2** `Installed` MUST list every flow there is to run here -- those installed from a
flowverse and the user's own -- each with its release, and MUST list first, marked, each flow whose
flowverse lists a newer release, with that release. Above the list it MUST say how many flows there
are and, where any has a newer release, how many do: the count of Section 3.6.

**31.1.3** On an installed flow: `enter` MUST open what it says of itself and what it declares --
its agent roles, its environment roles and its params; `n` MUST start a new epic of it, on the New
epic page (Section 29) where there is one and otherwise as `/flow <flow>` does (Section 7.9.2), the
page closing; `u` MUST install the newest release its flowverse lists; `s` MUST list its releases,
of which `enter` installs or switches to one; `x` MUST uninstall it.

**31.1.4** `Flowverses` MUST list every flowverse except the project's and the user's own, each
with when its index was fetched or that it is not, where it is fetched from with any credential
hidden, and how many flows it lists, has installed and has updates for. `a` MUST ask for a
repository and an optional name and add it; `f` MUST fetch the one under the cursor; `x` MUST
remove it; `enter` MUST list the flows it lists, each at its newest release with what of it is
installed, naming each manifest it skipped and why.

**31.1.5** On a flow a flowverse lists: `i` MUST install its newest release; `enter` MUST list its
releases newest first, the installed one and prereleases marked, of which `enter` installs or
switches to one; `x` MUST uninstall it.

**31.1.6** The page MUST ask before it uninstalls a flow, naming the flow, and before it removes a
flowverse, naming it and saying how many installed flows go with it (Section 25.4.2).

**31.1.7** While an epic is going the page MUST say that flows are installed, updated and
uninstalled once it ends, and MUST refuse to install, update or uninstall one, or to remove a
flowverse a flow is installed from, saying so again where it was asked (Section 3.9).

**31.1.8** One install, uninstall, fetch, add or removal MUST run at a time, without stopping the
page from drawing or taking keys; the page MUST say what is under way, refuse another until it is
done, and say what came of it under the list and in the transcript. The page MUST NOT fetch an
index unasked.

**31.1.9** `esc` MUST go back one list, and from a tab MUST close the page. The page MUST show its
own hint line, saying exactly the keys the list open takes (Section 25.2.2).

**31.1.10** What the page lists and what it says of what was done MUST be what `/flow` lists and
says (Section 16), and `/flow` MUST go on working as Section 16 states.

### 31.2. Transfers

**31.2.1** _Download_, _Import_ and _Export_ MUST each be a page view, named `download`, `import`
and `export`, with no key of its own, headed by its name in capitals over a heavy rule.

**31.2.2** A _transfer_ is one download, import or export. A transfer MUST run without stopping
the interface from drawing or taking keys, and MUST go on when its page is closed. Each of the
three pages MUST list the transfers of the interface, newest first: one still going with what it is
moving, a bar that moves and how long it has taken, saying that it goes on when the page is closed;
one ended with what came of it, a failure in red. What came of a transfer MUST also be said in the
transcript.

**31.2.3** Download MUST list what one backup target holds as Section 19.10.3 and 19.10.4 state,
fetched without delaying input, and MUST open on the first target; `enter` MUST download the epic
or chat under the cursor, `f` MUST fetch the target again, and `t`, where there is more than one
target, MUST turn to the next. What is here already MUST be marked `Here` and MUST NOT be
downloaded again, saying how it is opened. Where there is no target the page MUST say so and where
one is added.

**31.2.4** Import MUST ask for a `.hmzepic` by path, finished as it is typed (Section 15.4), as it
opens where no import is listed and on `enter`, and MUST read the file in as Section 17.1.5 states
for an import, saying the folder it was imported into.

**31.2.5** Export MUST list every epic recorded on this machine, newest first, each with when it
began, its flow or `chat`, its task, how it ended and the folder it ran in; `enter` MUST ask where
the archive goes as Section 17.2.6 states for an export and write it there, saying where it landed
and how big it is. Opened for one epic, it MUST ask where that epic goes at once.

## 32. Settings: App and Daemon

### 32.1. Groups

**32.1.1** The pages of `/settings` MUST stand in the groups the web interface's Settings has them
in (Section 3.11 of [WEB]): **App**, what is kept on this machine for the person at it; **Daemon**,
what the daemon keeps; and **Workspace**, the page of the directory `hmz` was started in.

**32.1.2** A group's name MUST be a heading the cursor steps over, drawn in capitals and ruled to
the far edge.

**32.1.3** `/settings <page>` (Section 7.13.2) MUST also take `themes` and `language`.

**32.1.4** `f2` MUST be the key of the _Settings_ view, a page (Section 25.1.2) that is `/settings`
on its landing screen and whose hint is `settings`. `f2` pressed while `/settings` is open, or
anything opened from it is, MUST NOT open it again.

**32.1.5** The Themes and Language pages MUST hold nothing: what is chosen on them MUST be kept at
once, MUST NOT mark a card `■ Unsaved`, and MUST NOT be asked about on leaving.

### 32.2. Themes

**32.2.1** The Themes page MUST list, under **Appearance**, Auto, Light, Dark and Terminal, and
under **Presets**, every preset of the web interface (Section 3.12 of [WEB]) by the name it has
there, each with a sample of it in its own colours, and MUST mark the appearance and the preset in
use.

**32.2.2** The interface MUST have, for every preset, a light theme and a dark theme named
`<preset>-light` and `<preset>-dark`, whose colours are the ones the web interface draws that
preset in, and which obey Section 25.3.2 with the preset's accent for cyan, its highlight for pink
and its brand colour for green; the preset Humanize Green MUST be `humanfia-light` and
`humanfia-dark`.

**32.2.3** Auto MUST draw the light side of the preset in use where `COLORFGBG` says the terminal's
background is light and its dark side otherwise; Light and Dark MUST draw that side; Terminal MUST
draw the theme `terminal` whatever the preset in use.

**32.2.4** While the cursor is on a row of the Themes page, the whole interface MUST be drawn as
it would be were that row chosen. `enter` on the row MUST keep it; leaving the page or the menu
MUST draw the interface as kept. Opening the page MUST put the cursor on the preset in use, or
on Terminal where that is the appearance in use.

**32.2.5** Choosing a preset while Terminal is the appearance in use MUST set the appearance to
Auto.

**32.2.6** Where `TEXTUAL_THEME` names a theme, and otherwise where `NO_COLOR` is set, that
variable MUST decide the theme (Section 3): the page MUST say which variable is set, MUST NOT
redraw the interface as the cursor moves, and MUST still keep what is chosen.

### 32.3. Language

**32.3.1** The Language page MUST list System, and English, 简体中文 and 繁體中文, each by the name
it calls itself, and MUST mark the one in use.

**32.3.2** System MUST be the language of the first of `LC_ALL`, `LC_MESSAGES` and `LANG` that is
set: Traditional Chinese for a Chinese locale of Taiwan, Hong Kong or Macao or one naming `Hant`,
Simplified Chinese for any other Chinese locale, and English otherwise.

**32.3.3** While the cursor is on a row of the Language page, the menu MUST be drawn in that row's
language; `enter` MUST keep it; leaving the page or the menu MUST go back to the language kept.

**32.3.4** The language kept MUST be in effect before the interface first draws, and for every
view and menu drawn after it is chosen (Section 25.5.2). What a daemon, a flow or an agent wrote
MUST stay as written.

### 32.4. Telling the system

**32.4.1** With **System** on (Section 19.4.1), the interface MUST tell the system of each notice it
shows a card for, by writing to the terminal: OSC 777 (`notify`, a title and a body) to a terminal
that takes it -- one that sets `VTE_VERSION`, or whose `TERM` starts with `rxvt` or `foot`; OSC 9 to
a terminal known to show it as a system notification -- iTerm2, Ghostty, WezTerm, kitty, Warp and
Windows Terminal; and to any other terminal, and to any inside tmux or screen (`TMUX` or `STY`
set, or a `TERM` starting with `tmux` or `screen`), the bell followed by OSC 9.

**32.4.2** The interface MUST NOT write more than one of OSC 777 and OSC 9 for one notice.

**32.4.3** Where the terminal has reported whether it has the focus, the interface MUST NOT tell
the system of a notice while the terminal has it. A terminal that has reported nothing MUST be
told every notice.

**32.4.4** Every control character of what is written between the sequence's introducer and its
terminator MUST be replaced by a space.

### 32.5. What is kept

**32.5.1** The preset, the appearance and the language MUST be kept under `tui` in the settings
file, as `theme` (a preset's key, `humanize` by default), `appearance` (`auto`, `light`, `dark` or
`terminal`; `auto` by default) and `language` (`en`, `zh-Hans`, `zh-Hant`, or empty for System, the
default), which every other key of that file, and of `tui`, is left beside (Section 3.3.2.4 of [FILES]).

**32.5.2** A value of any of the three that is none of those MUST be read as its default.

**32.5.3** Where the settings file cannot be written, the interface MUST keep what was chosen for
as long as it runs and MUST NOT report an error.

## 33. Monitor, Exomyth and sheets in humanfia

This section states how the menus and boxes of Section 15, the monitor of Section 20 and Exomyth of
Section 21 are drawn to Section 25.3, the view of Ai-chan's conversations, and what the texts
other sections quote literally are now. Where this section and an earlier one disagree about how
something is drawn or what a text says, this section governs.

### 33.1. Menus and boxes

**33.1.1** The list of a menu MUST be drawn in a square frame ruled heavily, the menu's title in
capitals in the frame's top rule. The frame and its title MUST be the colour of what has the keys
while the list has them, and dim otherwise.

**33.1.2** A box (Section 15.1.11) MUST be drawn in a square frame ruled heavily, in the colour of
what has the keys, headed `QUESTION` in the frame's top rule. A dropdown MUST be drawn the same
way, headed by its row's name in capitals.

**33.1.3** The row under the cursor of a list that has the keys MUST be filled pink. A button MUST
be a flat plane without a border: the button that has the keys in the colour of what has the keys;
the button that answers a menu, and a button that removes, in pink whether or not it has the keys;
any other dim. Section 15.1.9's green and red do not apply.

**33.1.4** The box that asks before a chat or an Ai-chan conversation is deleted MUST have the
button that keeps it first, so that `enter` alone deletes nothing.

**33.1.5** The keys line of a menu, of a box and of Exomyth MUST draw each key in the colour of what
can be followed, in bold, and what it does quietly, as the hint line of Section 25.2 does.

**33.1.6** A menu, a box, a dropdown, the monitor and Exomyth MUST take every colour they draw from
the theme in force, and MUST stay legible in the theme `terminal` and in a theme that defines none
of humanfia's own colours.

### 33.2. Monitor

**33.2.1** The box of an agent (Section 20.2.3) MUST be drawn as a block ruled heavily with square
corners, a plane down its left side in the agent's lane colour. Lane colours MUST be given out in
the flow's order, six of them and then again from the first, as the web interface gives them out
(Section 3.12 of [WEB]).

**33.2.2** The frame of the box under the cursor MUST be pink, and every other frame dim.

**33.2.3** A node that works MUST be named in cyan with its clock in cyan, and any other in the
text colour. `unread` MUST be pink and `reading` cyan.

**33.2.4** The handovers between two boxes MUST be drawn on a heavy spine, each direction cut off it
by one diagonal: `┃ ╱ ↓ <n> ╱ ↑ <n>`, in cyan where the latest handover went that way and dim
otherwise; between two agents never handed between the spine MUST be dotted.

**33.2.5** An outworlder's node MUST be marked in pink while the flow waits on that role for an
answer, and in cyan otherwise.

### 33.3. Exomyth

**33.3.1** Exomyth MUST colour a span by its category: a turn in the first lane colour, a tool call
in the fourth, a message in the fifth, a session or a process in the third, a flow in the third
ink, a model call in the mark's green, and anything else in the sixth lane colour.

**33.3.2** The span under the cursor MUST be filled pink, its name in bold. No category is drawn in
pink.

**33.3.3** The lists of the Flame and Slices views MUST be framed as Section 33.1.1 frames a menu's
list.

### 33.4. Ai-chan's conversations

**33.4.1** `f3` MUST be the key of the _Ai-chan_ view, which opens in the context and whose hint is
`Ai-chan`.

**33.4.2** The view MUST list `New conversation` and under it every Ai-chan conversation of the
daemon (`aichan.list`): those pinned first, then by when each was last said in, the latest first.
Each MUST show `Ai-chan#<n>`, its title, its scope, its preset, `typing…` while a turn of hers is
open, a square where it is pinned and a dot where it is unread.

**33.4.3** A conversation is _unread_ where it was marked so, or where it was said in after it was
last read in this interface. Following a conversation MUST read it. What is pinned and what is
unread MUST be kept by this interface alone and MUST NOT be sent to the daemon.

**33.4.4** In the view: `enter` on a conversation MUST follow it as Section 7.19.2 states and give
the keys to the editor; `enter` on `New conversation`, and `n`, MUST open `/ai`; `r` MUST ask for a
title and rename the conversation by `aichan.rename`; `p` MUST pin it or let it go; `u` MUST mark it
read or unread; `delete` MUST ask as Section 33.4.6 states and then forget it by `aichan.forget`.

**33.4.5** The menu of a conversation in `/ai` (Section 7.19.5) MUST offer **Rename**, **Pin** or
**Unpin**, **Mark as read** or **Mark as unread**, and **Delete**, each doing what its key of
Section 33.4.4 does, and `/ai` MUST list and mark the conversations as Section 33.4.2 states.

**33.4.6** Deleting a conversation MUST ask in a box `Delete this conversation?`, naming it, whose
first button is **Cancel** and whose second is **Delete**.

### 33.5. Texts

**33.5.1** What a key does, on a keys line, MUST be said in the words of Section 25.5: `Open`,
`Back`, `Close`, `Choose`, `Search`, `Actions`, `Menu` and so on. A sentence of this document that
quotes such a word in lower case is to be read with the word as it is here.

**33.5.2** The texts below, which other sections quote, MUST be as the right column has them.

| Section | Was | Is |
| ------- | --- | --- |
| 7.12 | `/resume`'s menu: `rename`, `fork`, `archive`, `upload`, `delete`, `copy id` | **Rename**, **Fork**, **Archive**, **Upload**, **Delete**, **Copy ID** |
| 7.12 | the title `Resume a chat` | `Resume chat` |
| 7.12 | a box saying that the deletion is permanent | the box `Delete <title>?`, saying what the web interface says of deleting a chat, **Cancel** first and **Delete** second |
| 7.19.1 | the entry **New** | **New conversation** |
| 7.19.3 | the rows `scope`, `nous`, `preset` | `Scope`, `Nous`, `Permissions` |
| 7.19.5 | **Forget** | **Delete**, with the rest of Section 33.4.5 |
| 10 | the button `answer`, and `answer · <n> required left` | `Answer`, and `Answer · <n> required left` |
| 10 | `this is needed`, `this needs a number`, `this needs a whole number` | `This needs an answer.`, `This needs a number.`, `This needs a whole number.` |
| 15.1.3 | `● unsaved changes` | `● Unsaved` |
| 15.3 | the box `Save?` offering **Save** and **Discard** | the box `Save changes?` offering **Save** and **Discard** |
| 14 | the box `A flow is running.` offering `stop the flow and exit`, and `detach and exit` or `cancel` | the same box offering **Stop the flow and quit**, and **Detach and quit** or **Cancel** |
| 19.13 | the box `Report errors to Humanize?` offering `yes` and `no` | the box `Send error reports to Humanize?` offering **Yes** and **No** |
| 15.2 | the search button `search…` and the placeholder `type to filter` | **Search** and `Type to filter` |
| 7.20.3, 7.20.8, 7.20.9 | the page `Shell` | `Terminal` |
| 7.20.5 | a box offering to keep the user's text or to read the file again | the box `<path> changed in the environment since you opened it.` offering **Reload**, **Keep mine** and **Show the diff** |
| 7.20.5 | the editor's states `● edited`, `conflict: changed on disk`, `not saved: <why>` | `● Unsaved`, `Conflict`, `Not saved: <why>` |
| 7.20.7 | the buttons `stage all`, `unstage all`, `commit…` | **Stage All Changes**, **Unstage All Changes**, **Commit** |
| 20 | the board's sheet `Board entry`, its buttons `next` and `save`, and the row `add entry` | `Board line`, **Next** and **Save**, and `new entry` |
| 20 | the switch and the keys line saying `graph` and `list` | **Graph** and **List**; the status line keeps `monitor · graph` and `monitor · list` |
| 20 | the epic's sheet saying `Running.`, `Stopping.`, `Over.` | `Running`, `Stopping`, `Ended` |
| 21 | the keys `merge` and `apart`, and `range`, `hold`, `drop` | **Merge sessions** and **Split sessions**, and **Mark range**, **Hold range**, **Clear range** |
| 24.1.49 | write, delete | **Write**, **Delete** |
| 24.1.50 | on to the value, then save | **Type value**, then **Save or remove** |
| 24.1.109 | stage all, unstage all | **Stage All Changes**, **Unstage All Changes** |

## 34. Security Considerations

This section is informative. It states no requirement; it gathers the properties stated elsewhere
in this document that bear on security.

- **What a typed line can start.** A line typed into the editor can start an epic, whose agents then
  act in the working directory and in the flow's environments: a line said while no epic is going
  starts the flow set up (Section 9.4), and a `$` line chooses a flow and starts it (Section 8.6 and
  Section 8.7). A `$` line names a flow and is not a shell command; a `$` line naming a flow not
  offered is refused (Section 8.4), one typed while an epic is going leaves that epic untouched
  (Section 8.5), and a flow that is not set up starts only once its menu is saved (Section 8.7).
  Agents and environments are defined by Section 4 of [CORE] and Section 7 of [CORE].
- **Secrets on the screen.** The Accounts page draws no secret (Section 19.6.1), and a secret left
  blank on an edit keeps the one saved (Section 19.6.2). The URL of a flowverse and of a backup
  target is shown with any credential hidden (Section 16.3.1 and Section 19.10.1). The interface
  does not read a key file that a runtime names (Section 19.9.5). Batch apply excludes the accounts
  (Section 19.5.3).
- **Clipboard.** Copying goes through the terminal to the clipboard of the machine the terminal
  runs on, which need not be the machine hmz runs on (Section 23.2). What is copied
  is text already on the screen (Section 23.1) or an epic's name, task or path (Section 17.2.9 and
  Section 17.3.2).
- **Network contact without a command.** As it opens, the interface asks installed harnesses for
  their models, fetches flowverse indexes, refreshes the price list and asks for the newest release
  of hmz (Section 3.5). Those fetches install nothing (Section 3.5), and a flow is installed,
  updated or uninstalled only from `/flow` (Section 16.1.2) and not while an epic is going
  (Section 3.9).
- **Other machines.** The epics of another machine's daemon are read over a session to it, over
  ssh or over mutual TLS with a paired device (Section 17.3.1), an epic can be started and steered
  there (Section 17.3.3 and Section 17.3.4), and a device can be paired with a daemon or revoked
  from it (Section 19.5.2).
  Importing the hosts of an ssh config does not write to that config (Section 19.9.2).
- **Files taken in and written out.** Importing takes a `.hmzepic` at a path the user gives or
  drops onto the terminal and refuses a file it cannot import (Section 17.1.5); **Download…**
  brings in an epic from a saved backup target (Section 19.10.3). Exporting writes an archive of an
  epic where the user says (Section 17.2.6), and `upload` queues a backup of it to its targets
  (Section 17.2.7).
- **Several frontends.** A frontend is named from `HUMANIZE_NAME`, else the login name (Section
  2.23), and lines, answers and epics of another frontend are attributed by that name (Section
  9.10). `/claim` holds an outworlder for one frontend (Section 7.16), `/afk` does not change an
  outworlder another frontend holds (Section 7.15.3), and `/stop` and stopping on the way out stop
  the epic for every frontend (Section 7.17.1 and Section 7.18.5).
- **Environments.** `/env` writes the files of an epic's envs and opens a shell in them, as the
  user the daemon runs as (Section 7.20); every change and every shell opened is written in the
  epic's history (Section 4.24.1.8 of [DAEMON]).
- **Error reports.** The interface asks once whether hmz can report its own failures, saying what
  would be sent and what would not, and leaving the box leaves the question unanswered (Section
  19.13.1); the General page holds the answer and says where `HUMANIZE_SENTRY` overrides it
  (Section 19.2.1 and Section 19.2.3).

## 35. References

### 35.1. Normative References

- **[RFC2119]** Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels", BCP 14, RFC
  2119, March 1997, <https://www.rfc-editor.org/info/rfc2119>.
- **[RFC8174]** Leiba, B., "Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words", BCP 14, RFC
  8174, May 2017, <https://www.rfc-editor.org/info/rfc8174>.
- **[CORE]** "The Humanize Protocol: Core Concepts and Functional Behaviour", [`core.md`](core.md).
- **[CLI]** "The Humanize Protocol: Command-Line Interface", [`cli.md`](cli.md).
- **[DAEMON]** "The Humanize Protocol: Daemon", [`daemon.md`](daemon.md).
- **[WIRE]** "The Humanize Protocol: Carriers, Sessions and RPC", [`wire.md`](wire.md).
- **[WEB]** "The Humanize Protocol: Web Interface", [`web.md`](web.md).
- **[PYTHON]** "The Humanize Protocol: Python Interfaces", [`python.md`](python.md).
- **[FILES]** "The Humanize Protocol: Settings, Environment Variables and Files", [`files.md`](files.md).

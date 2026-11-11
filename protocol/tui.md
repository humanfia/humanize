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
  - [7.9. `/flow [flow]`](#79-flow-flow)
  - [7.10. `/btw [question]`](#710-btw-question)
  - [7.11. `/epics [@daemon]`](#711-epics-daemon)
  - [7.12. `/resume`](#712-resume)
  - [7.13. `/settings [page]`](#713-settings-page)
  - [7.14. `/clear`](#714-clear)
  - [7.15. `/afk [on|off]`](#715-afk-onoff)
  - [7.16. `/claim [on|off]`](#716-claim-onoff)
  - [7.17. `/stop`](#717-stop)
  - [7.18. `/exit`](#718-exit)
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
  - [19.8. Fallback](#198-fallback)
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
- [25. Security Considerations](#25-security-considerations)
- [26. References](#26-references)
  - [26.1. Normative References](#261-normative-references)

## 1. Introduction

This document defines the terminal interface: the **frontend** that `hmz` opens when it is run with
no command. It states every screen, the prompt, every `/` command, `$` lines, the menus and sheets,
the monitor, the settings pages, the update notices and every key, as the **user** sees and uses
them. The terminal interface runs **flows** and reads **epics** back; it defines no flow and drives
no **agent** itself.

This document does not define the following, each of which the document cited defines:

- The command line that opens the interface and where its epics are held: Section 6 of [CLI].
- What each setting means and where it is stored: Section 3 of [FILES].
- The chat flow's behaviour common to every frontend: Section 8 of [CORE].
- Side questions' behaviour common to every frontend: Section 9 of [CORE].
- Agents, harnesses, models and efforts: Section 4 of [CORE].
- Accounts and fallback: Section 5 of [CORE].
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
every sheet opened from them, and every page opened from the monitor.

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

**2.25** **Chat**: an epic of the flow `chat` (Section 8 of [CORE]).

**2.26** **In the background**: said of work the interface does while it goes on drawing and
taking input, neither of which waits for that work.

## 3. Launch

**3.1** The interface MUST open on the flow remembered for the working directory, or on `chat` where
none is remembered, unless its arguments name a flow.

**3.2** The interface MUST open set up, so that a line typed is enough to start an epic, with each
agent role as remembered for the flow or, where nothing is remembered, as Section 16.5.4 fills it.

**3.3** The interface MUST draw in the terminal's own palette, MUST NOT query the terminal for its
colours, MUST draw failures in red and warnings in yellow, MUST use the theme named by
`TEXTUAL_THEME` where it names an available one, and MUST honour `NO_COLOR`.

**3.4** The interface MUST offer no command palette.

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
2. a `$` line (Section 8) while no question is answerable here starts a flow;
3. a line not starting with `/` is said (Section 9);
4. a line starting with `/` is a command (Section 7).

**6.2** A blank line MUST NOT be sent.

## 7. Commands

**7.1** The interface MUST offer exactly these commands: `/flow`, `/btw`, `/epics`, `/resume`,
`/settings`, `/clear`, `/afk`, `/claim`, `/stop`, `/exit`.

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

### 7.9. `/flow [flow]`

**7.9.1** `/flow` MUST open the flow menu (Section 16) on its Installed page.

**7.9.2** `/flow <flow>` MUST open the flow menu on the roles of the flow named, by any name the
offer list offers or by a path.

**7.9.3** While an epic is going, `/flow` MUST open on the roles of the running flow and offer
nothing else, and saving it MUST say that the epic going keeps its setup and the change applies to
the next epic.

**7.9.4** While an epic is going, `/flow <flow>` MUST be refused, saying a flow cannot be chosen
while one is running.

### 7.10. `/btw [question]`

**7.10.1** `/btw` MUST enter btw mode (Section 12), asking `[question]` where one is given.

**7.10.2** In btw mode, `/btw` alone MUST leave btw mode, and `/btw <question>` MUST ask one more
question.

**7.10.3** `/btw` MUST be refused where there is nobody to ask (Section 9.5.8 of [CORE], Section
9.5.9 of [CORE]).

### 7.11. `/epics [@daemon]`

**7.11.1** `/epics` MUST open the epics menu (Section 17) on the daemon it last listed, this
machine's until another is chosen.

**7.11.2** `/epics @<name>` MUST open the epics menu on the daemon named, one of those on the
Daemons page, and MUST keep to that daemon until another is chosen.

**7.11.3** `/epics` with an argument that is not `@` followed by a daemon's name MUST be refused,
naming the daemons it takes.

### 7.12. `/resume`

**7.12.1** `/resume` MUST pick up the newest epic of this directory whose flow can be picked up, as
Section 18 states.

**7.12.2** `/resume` with any argument MUST be refused, saying `/epics` chooses another epic.

**7.12.3** `/resume` MUST be refused while an epic is going or stopping.

**7.12.4** `/resume` MUST NOT be offered while the last background look found nothing to pick up,
and MUST look again for itself when typed.

### 7.13. `/settings [page]`

**7.13.1** `/settings` MUST open the settings menu (Section 19) on its landing screen.

**7.13.2** `/settings <page>` MUST open inside the page named: `general`, `notifications`,
`daemons`, `accounts`, `fallback`, `runtimes`, `backup`, `workspace` or `usage`, compared without
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

**7.17.2** `/stop` MUST be refused where no epic is going, where the epic going is a chat, and where
the epic is already stopping.

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

## 8. `$` lines

**8.1** A line of the form `$<name>[ <task>]` MUST be a `$` line, where `<name>` is a flow as the
offer list names it: a bare name starting with a letter, `<user>/<flow>` for a GitHub user,
`@<flowverse>/[<user>/]<flow>`, or any of these followed by `:<flow>` for another flow of the same
module; and where `<name>` is followed by whitespace or the end of the line.

**8.2** A line starting with `$` that is not a `$` line MUST be treated as prose.

**8.3** A `$` line MUST be treated as prose while a question is answerable here, and MUST be a side
question while btw mode is on.

**8.4** A `$` line naming a flow not offered MUST be refused, naming it.

**8.5** A `$` line MUST be refused while an epic is going, leaving that epic untouched.

**8.6** A `$` line naming a flow that is set up here MUST choose that flow and, with a task, start
an epic of it at once; without a task, the interface MUST ask for one.

**8.7** A `$` line naming a flow that is not set up here MUST open `/flow` on that flow's roles,
holding the task, and MUST start the epic when the menu is saved; leaving the menu unsaved MUST say
that the flow was not set up and nothing was started.

**8.8** A flow MUST count as set up here where every agent role it declares has a remembered agent,
every environment role it requires has a remembered environment, its remembered params are valid,
and it has a budget unless it is `chat`.

## 9. Saying something

**9.1** A line said while a question is answerable here MUST answer that question (Section 10).

**9.2** A line said on an outworlder view MUST be refused where another frontend holds that
outworlder, and where that outworlder asks nothing.

**9.3** A line said while an epic is going MUST be sent to the session read, or to whichever session
of the agent read has a turn open, and MUST otherwise be held for that agent's next turn.

**9.4** A line said while no epic is going MUST start the flow set up, with the line as its task.

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

## 11. Chat

**11.1** The interface MUST treat as a chat an epic of `chat` going, and, with none going, the flow
`chat` set up.

**11.2** In a chat, the interface MUST read the chat's session alone, with no header naming the
view, no round, no outworlder line, and no `reading` or `unread` mark on the agent line.

**11.3** In a chat, `←` MUST NOT open the monitor.

**11.4** In a chat, the status line MUST say `running` while a turn is open and `done` while the
chat is between turns.

**11.5** In a chat, `/stop` MUST be refused, saying that a chat is not stopped and that `/clear`
starts another.

**11.6** In a chat, `ctrl+c` MUST NOT stop anything (Section 14.3).

**11.7** A flow MUST be startable and `/resume` MUST work while a chat goes on its own host.

**11.8** `/epics` MUST offer `continue` on a chat's epic in place of resuming it (Section 8.7 of
[CORE]).

## 12. Btw mode

**12.1** Entering btw mode MUST say who answers, `btw · <agent>/<n>` or `btw · The Epic`, and that
each line is a question and `/btw` or `esc` leaves.

**12.2** While btw mode is on, the status line MUST begin with `btw · ` and who answers, in cyan.

**12.3** While btw mode is on, every line typed that does not start with `/` MUST be one more
question of the same side conversation.

**12.4** Who answers MUST be as Section 9.5 of [CORE] states, the view read deciding: a session view
or an agent view its session side copy, any other view The Epic, which is the btw agent.

**12.5** Each answer MUST be shown in the view read: a cyan bullet, `btw · ` and the question, dim,
then the answer in cyan.

**12.6** Each ask line the btw agent sends MUST be shown, dim, as `btw · asking <agent>/<n>:` and
its question.

**12.7** Btw mode MUST offer no key or list that picks the btw agent, which is the `btw` setting
alone (Section 9.7.5 of [CORE]).

**12.8** `/btw` alone or `esc` MUST leave btw mode, say `btw: exited`, and close every side
conversation btw mode opened.

**12.9** An epic starting MUST leave btw mode, saying that a new flow started.

**12.10** A side question asked while the side conversation is answering an earlier one MUST be
refused, showing `hmz: btw is still answering the last question` in red.

**12.11** A failure of a side question MUST be shown in red, prefixed `hmz: /btw:`.

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
5. otherwise, the flow set up and the working directory, the home directory written `~`.

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

**16.2.1** The Installed page MUST list every flow that can run here: the built-in flows first, then
the flows installed from each flowverse, then this project's, then the user's, each under a heading
of where it came from and by the name `-f` takes.

**16.2.2** Each installed flow MUST show its release and, where its index lists a newer one, that
newer release; the flow in force MUST be marked `✔`.

**16.2.3** The Installed page MUST offer **Install more…**, **Update** where an update is listed,
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

**16.3.2** The Flowverses page MUST offer **Add flowverse…**, a form taking a repository and an
optional name; **Fetch** or **Fetch again**; **Remove**, except for `official`, asked first in a box
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

**16.4.6** **Save** MUST be refused for a flow other than `chat` that has no budget.

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
opened there.

**17.1.5** `i` or **Import…** MUST open a form taking the path of a `.hmzepic`, starting from the
downloads directory, taking a file dropped onto the terminal as its path, and MUST import it in the
background and put the cursor on it, or refuse the file in plain words.

**17.1.6** `/epics` MUST offer **Daemon…**, a pick list of this machine's daemon and every daemon on
the Daemons page with how it stands, turning the list to the one picked.

**17.1.7** The list MUST be readable while an epic is going.

### 17.2. One epic

**17.2.1** `enter`, `→` or a click on an epic MUST open its menu with these rows, each where
offered: `resume epic` or, for a chat, `continue`; `graph`; `export epic`; `Exomyth`; `upload`;
`copy name`, `copy task`, `copy path`.

**17.2.2** `resume epic` MUST pick the epic up as `/resume` does, and MUST be refused for an epic of
another directory, saying where it ran; while an epic is going; and for an epic whose flow is not
resumable or that cannot be resumed here, saying why.

**17.2.3** `continue` MUST carry the chat on as Section 8.7 of [CORE] states.

**17.2.4** `graph` MUST open the epic's graph, read in the background: one box per agent with its
turns and the handovers between neighbours, its sessions under it, and the tree of flows it called.

**17.2.5** `enter` on a session of the graph MUST read the session whole: each turn, model call,
tool call with what went in and came out, and what was said, in order, each cut to 6 lines until
opened, searchable.

**17.2.6** `export epic` MUST ask where the archive goes, a file or a directory, starting from the
downloads directory, and MUST say where it landed, how big it is and what it holds.

**17.2.7** `upload` MUST be offered where a backup target exists, and MUST queue a backup to the
targets the epic was started with, else the defaults, without waiting for it.

**17.2.8** `Exomyth` MUST open the epic in Exomyth (Section 21), and MUST NOT be offered for a chat.

**17.2.9** `copy name`, `copy task` and `copy path` MUST copy that to the clipboard and say so.

### 17.3. Another daemon's epics

**17.3.1** On a daemon of another machine, `/epics` MUST list the epics that daemon holds, read
through its own web interface reached over ssh in the background, and MUST say why where it
cannot be reached.

**17.3.2** `enter`, `m` or a click on such an epic MUST offer `follow` for one a host there holds,
`export` for one not going, `upload`, `copy name`, `copy task` and `copy workspace`.

**17.3.3** `n` or **New epic…** MUST start an epic there from a directory, a flow, a task and its
agents, set up otherwise as that directory last ran the flow, and MUST follow it.

**17.3.4** Following an epic there MUST show what was asked, what each agent said, what the flow
asks and how it stands; a line typed MUST answer what it asks, or otherwise be said to it; `esc`
MUST go back to the list, leaving the epic going there.

## 18. `/resume`

**18.1** `/resume` MUST look at the epics of this directory newest first, and MUST pick up the first
whose flow is resumable, with its flow, agents, environments, params, budget counted from zero,
profiling switches and task, saying which epic it resumes.

**18.2** `/resume` MUST say why there is nothing to resume: no epic here, none of a resumable flow,
an epic that cannot be read, a flow that will not load, a flow that is not resumable, or an epic
with no saved state.

**18.3** `/resume` MUST NOT pick up a chat.

## 19. `/settings`

### 19.1. Landing screen

**19.1.1** `/settings` MUST be one menu of nine pages, in this order: General, Notifications,
Daemons, Accounts, Fallback, Runtimes, Backup, Workspace, Usage.

**19.1.2** The landing screen MUST show one card per page with a summary of it, and `● unsaved` on
each card whose page holds a change.

**19.1.3** `enter` or a click on a card MUST open its page; `esc`, `←` or `backspace` on a page MUST
return to the landing screen with the cursor on that page's card.

**19.1.4** Each page MUST keep its message and cursor while another page is read.

**19.1.5** **Save** on the landing screen or a page MUST apply what every page holds.

**19.1.6** Each saved setting MUST take effect at once where it can; otherwise the interface MUST
say beside its row while held and in the transcript when it lands: account changes from the next
agent session, forgetting a directory from the next launch, the btw agent from the next side
conversation of the btw agent.

**19.1.7** Leaving `/settings` MUST write one dim line per change into the transcript.

### 19.2. General

**19.2.1** The General page MUST hold, for this machine: **Details**, whether turns show tool calls,
thinking and harness output; **/btw The Epic**, the agent that answers side questions asked of The
Epic: `none`, the current one, or another set up on the agent sheet titled `Set up The Epic's
agent`; **Error reports**, on or off; and **What is sent**, which says what error reports include
and exclude.

**19.2.2** Once answered, **Error reports** MUST NOT return to unanswered.

**19.2.3** Where `HUMANIZE_SENTRY` overrides error reporting, the General page MUST say so.

### 19.3. Details

**19.3.1** Details on MUST show every tool call, the thinking, sub-agents and harness output in the
transcript; details off MUST show the agents' answers only.

### 19.4. Notifications

**19.4.1** The Notifications page MUST offer, each on or off, the kinds Done, Failed, Stopped,
Questions and Chat turns, and **System**, whether the terminal's bell rings and a system
notification is shown too; these MUST be the same settings as the web interface's.

**19.4.2** For every epic on this machine, the interface MUST show each notice of a kind turned on
(Section 10 of [CORE]) as a card that goes after a while, and, with **System** on, MUST ring the
bell and show a system notification.

**19.4.3** The interface MUST NOT give a notice of an epic of this directory while its log or the
monitor is on the screen.

**19.4.4** The interface MUST work out notices from each host's status, without attaching to it.

### 19.5. Daemons

**19.5.1** The Daemons page MUST list this machine's daemon, `Local`, and every daemon of another
machine the web interface keeps (Section 3.13 of [WEB]), the same list, each with what reaches it
and how it stands, redrawn as that changes.

**19.5.2** The Daemons page MUST offer **Add daemon** and **edit…** on one form; **Import…** of the
hosts of the ssh config not added yet; and per daemon **connect**, **remove** and **copy name**;
each written at once.

**19.5.3** The Daemons page MUST offer **Batch apply…**: this machine's settings of the pages
picked, the accounts excluded, written to each daemon picked as the web interface's `Batch apply`
writes them (Section 3.11.2.13 of [WEB] to Section 3.11.2.15 of [WEB]), saying how each went.

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

### 19.8. Fallback

**19.8.1** The Fallback page MUST list each rule by the place that fails, its retries, its wait
policy, its limit and the chain of places it falls back to, in order.

**19.8.2** The rule form MUST take the place that fails, the chain of places, each added, taken off
and reordered there, the number of tries, the wait policy and the limit, and MUST refuse a chain
that names the place that fails or one place twice (Section 5 of [CORE]).

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

### 19.11. Workspace

**19.11.1** The Workspace page MUST name this directory, show the flow it opens on, and offer
**Forget**, which on save clears what this directory remembers from the next launch.

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
in order; for `$` and a part, `$` and each flow; and nothing for three or more words.

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

**24.2** `esc` MUST NOT open the monitor, and `←` MUST NOT stop anything.

**24.3** `shift+enter` MUST break the line where the terminal reports it; `ctrl+j` MUST break the
line in every terminal.

## 25. Security Considerations

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
- **Other machines.** The epics of another machine's daemon are read through that daemon's web
  interface reached over ssh (Section 17.3.1), and an epic can be started there (Section 17.3.3).
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
- **Error reports.** The interface asks once whether hmz can report its own failures, saying what
  would be sent and what would not, and leaving the box leaves the question unanswered (Section
  19.13.1); the General page holds the answer and says where `HUMANIZE_SENTRY` overrides it
  (Section 19.2.1 and Section 19.2.3).

## 26. References

### 26.1. Normative References

- **[RFC2119]** Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels", BCP 14, RFC
  2119, March 1997, <https://www.rfc-editor.org/info/rfc2119>.
- **[RFC8174]** Leiba, B., "Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words", BCP 14, RFC
  8174, May 2017, <https://www.rfc-editor.org/info/rfc8174>.
- **[CORE]** "The Humanize Protocol: Core Concepts and Functional Behaviour", [`core.md`](core.md).
- **[CLI]** "The Humanize Protocol: Command-Line Interface", [`cli.md`](cli.md).
- **[DAEMON]** "The Humanize Protocol: Daemon", [`daemon.md`](daemon.md).
- **[WEB]** "The Humanize Protocol: Web Interface", [`web.md`](web.md).
- **[PYTHON]** "The Humanize Protocol: Python Interfaces", [`python.md`](python.md).
- **[FILES]** "The Humanize Protocol: Settings, Environment Variables and Files", [`files.md`](files.md).

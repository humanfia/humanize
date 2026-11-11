# The Humanize Protocol: Core Concepts and Functional Behaviour

## Abstract

This document is the base document of the Humanize Protocol. It states the conventions every
document of the protocol follows, defines the terms they share, and specifies the behaviour of hmz
that is common to every interface: epics, agents, accounts, placements, environments, chats, side
questions, monitoring, backups, telemetry and updates.

## Status of This Document

This document is one of the documents of the Humanize Protocol, which Section 2.2.4 lists. It is
normative. It is cited by the tag [CORE].

## Table of Contents

- [1. Introduction](#1-introduction)
- [2. Conventions and Terminology](#2-conventions-and-terminology)
  - [2.1. Requirements Language](#21-requirements-language)
  - [2.2. Numbering and Citation](#22-numbering-and-citation)
  - [2.3. Parties and places](#23-parties-and-places)
  - [2.4. Flows and epics](#24-flows-and-epics)
  - [2.5. Agents and where they run](#25-agents-and-where-they-run)
  - [2.6. Processes and frontends](#26-processes-and-frontends)
- [3. Epics](#3-epics)
  - [3.1. Scope](#31-scope)
  - [3.2. Terminology](#32-terminology)
  - [3.3. Lifecycle](#33-lifecycle)
  - [3.4. Workspaces](#34-workspaces)
- [4. Agents](#4-agents)
  - [4.1. Scope](#41-scope)
  - [4.2. Terminology](#42-terminology)
  - [4.3. Harnesses](#43-harnesses)
  - [4.4. Agent specs, models and efforts](#44-agent-specs-models-and-efforts)
  - [4.5. Configuration levels](#45-configuration-levels)
  - [4.6. Permissions and confinement](#46-permissions-and-confinement)
  - [4.7. Sessions and turns](#47-sessions-and-turns)
  - [4.8. Usage and cost](#48-usage-and-cost)
  - [4.9. Hooks](#49-hooks)
  - [4.10. Fake tools and fake command lines](#410-fake-tools-and-fake-command-lines)
  - [4.11. Failures, retries and fallbacks](#411-failures-retries-and-fallbacks)
  - [4.12. Watchdog](#412-watchdog)
  - [4.13. LiteLLM](#413-litellm)
  - [4.14. ACP harnesses](#414-acp-harnesses)
  - [4.15. The human agent](#415-the-human-agent)
- [5. Accounts](#5-accounts)
  - [5.1. Scope](#51-scope)
  - [5.2. Terminology](#52-terminology)
  - [5.3. Identity](#53-identity)
  - [5.4. Storage](#54-storage)
  - [5.5. Ways in](#55-ways-in)
  - [5.6. A turn under an account](#56-a-turn-under-an-account)
  - [5.7. Which machine's credentials a harness reads](#57-which-machines-credentials-a-harness-reads)
  - [5.8. Model catalogues](#58-model-catalogues)
  - [5.9. Expired and refused credentials](#59-expired-and-refused-credentials)
  - [5.10. One account, several harness kinds](#510-one-account-several-harness-kinds)
  - [5.11. Secrecy](#511-secrecy)
- [6. Placements](#6-placements)
  - [6.1. Scope](#61-scope)
  - [6.2. Terminology](#62-terminology)
  - [6.3. Env location and harness location](#63-env-location-and-harness-location)
  - [6.4. Settling the harness location](#64-settling-the-harness-location)
  - [6.5. What runs where](#65-what-runs-where)
  - [6.6. Mirrors](#66-mirrors)
  - [6.7. Workspace configuration across machines](#67-workspace-configuration-across-machines)
  - [6.8. Moving, forking, keeping and carrying on](#68-moving-forking-keeping-and-carrying-on)
  - [6.9. Targets](#69-targets)
  - [6.10. Serving a target](#610-serving-a-target)
- [7. Environments](#7-environments)
  - [7.1. Scope](#71-scope)
  - [7.2. Terminology](#72-terminology)
  - [7.3. Requirements common to every kind](#73-requirements-common-to-every-kind)
  - [7.4. Runtimes](#74-runtimes)
  - [7.5. `local`](#75-local)
  - [7.6. `ssh`](#76-ssh)
  - [7.7. `docker`](#77-docker)
  - [7.8. `swarm`](#78-swarm)
  - [7.9. `apple-container`](#79-apple-container)
  - [7.10. `slurm`](#710-slurm)
  - [7.11. Falling back](#711-falling-back)
  - [7.12. Leftovers](#712-leftovers)
- [8. Chat](#8-chat)
  - [8.1. Scope](#81-scope)
  - [8.2. Terminology](#82-terminology)
  - [8.3. The flow](#83-the-flow)
  - [8.4. Turns](#84-turns)
  - [8.5. Status](#85-status)
  - [8.6. Many chats](#86-many-chats)
  - [8.7. Folding away and carrying on](#87-folding-away-and-carrying-on)
  - [8.8. Drawing a chat](#88-drawing-a-chat)
- [9. Side Questions](#9-side-questions)
  - [9.1. Scope](#91-scope)
  - [9.2. Terminology](#92-terminology)
  - [9.3. Guarantees](#93-guarantees)
  - [9.4. What a side conversation is told](#94-what-a-side-conversation-is-told)
  - [9.5. Who answers](#95-who-answers)
  - [9.6. The btw agent asking sessions](#96-the-btw-agent-asking-sessions)
  - [9.7. Choosing the btw agent](#97-choosing-the-btw-agent)
  - [9.8. Whom a side question is asked of](#98-whom-a-side-question-is-asked-of)
  - [9.9. Lifetime of side conversations and asides](#99-lifetime-of-side-conversations-and-asides)
- [10. Monitoring](#10-monitoring)
  - [10.1. Scope](#101-scope)
  - [10.2. Terminology](#102-terminology)
  - [10.3. Live figures](#103-live-figures)
  - [10.4. Notices](#104-notices)
  - [10.5. Traces and profiles](#105-traces-and-profiles)
  - [10.6. Exomyth timeline](#106-exomyth-timeline)
- [11. Backups](#11-backups)
  - [11.1. Scope](#111-scope)
  - [11.2. Terminology](#112-terminology)
  - [11.3. Backups](#113-backups)
  - [11.4. Export and import](#114-export-and-import)
- [12. Telemetry](#12-telemetry)
  - [12.1. Scope](#121-scope)
  - [12.2. Terminology](#122-terminology)
  - [12.3. Consent](#123-consent)
  - [12.4. Content](#124-content)
  - [12.5. Destination](#125-destination)
- [13. Updates](#13-updates)
  - [13.1. Scope](#131-scope)
  - [13.2. Terminology](#132-terminology)
  - [13.3. Learning the newest release](#133-learning-the-newest-release)
  - [13.4. `hmz update`](#134-hmz-update)
- [14. Security Considerations](#14-security-considerations)
- [15. References](#15-references)
  - [15.1. Normative References](#151-normative-references)

## 1. Introduction

This document is the base document of the Humanize Protocol. It states the conventions every
document of the protocol follows, defines the terms they share, and specifies the behaviour of hmz
that is common to every interface: epics, agents, accounts, placements, environments, chats, side
questions, monitoring, backups, telemetry and updates.

This document is organised as follows:

- Section 3: Epics.
- Section 4: Agents.
- Section 5: Accounts.
- Section 6: Placements.
- Section 7: Environments.
- Section 8: Chat.
- Section 9: Side Questions.
- Section 10: Monitoring.
- Section 11: Backups.
- Section 12: Telemetry.
- Section 13: Updates.

## 2. Conventions and Terminology

### 2.1. Requirements Language

**2.1.1** The key words "MUST", "MUST NOT" and "MAY" in this document are to be interpreted as
described in BCP 14 [RFC2119] [RFC8174] when, and only when, they appear in all capitals, as shown
here.

**2.1.2** MUST states an absolute requirement on the subject of its paragraph, and MUST NOT an
absolute prohibition.

**2.1.3** MAY states a permission: the subject of the paragraph is free to do the thing or not,
and every other party MUST accept either.

**2.1.4** A block that begins with the marker `> Informative:` states no requirement.

**2.1.5** Every quoted identifier, string and message is reproduced exactly as hmz emits or
accepts it.

**2.1.6** A grammar is given in ABNF [RFC5234] [RFC7405] in a fenced `abnf` block, or in a
notation the document defines before its first use.

### 2.2. Numbering and Citation

**2.2.1** Every normative paragraph of the protocol carries a number, written in bold at its
start, that continues the number of the section or subsection it stands in.

**2.2.2** A paragraph is cited as a section is: `Section 4.6.2.1` names the first paragraph of
Section 4.6.2.

**2.2.3** A citation without a document tag names a section or paragraph of the document it
appears in; a citation of another document of the protocol gives that document's tag, as
`Section 7.4 of [CLI]`.

**2.2.4** The documents of the protocol and their tags are:

| Tag | Document | Subject |
| --- | --- | --- |
| [CORE] | [`core.md`](core.md) | Conventions, shared terms, and the behaviour common to every interface |
| [CLI] | [`cli.md`](cli.md) | Every `hmz` command, its options, output and exit statuses |
| [TUI] | [`tui.md`](tui.md) | The terminal interface |
| [DAEMON] | [`daemon.md`](daemon.md) | The daemon and the protocol a client speaks to it |
| [WEB] | [`web.md`](web.md) | The web page and the HTTP interface |
| [DESKTOP] | [`desktop.md`](desktop.md) | The desktop application for macOS and Windows |
| [PYTHON] | [`python.md`](python.md) | The flow API `hmz.flows` and the software development kit `hmz.sdk` |
| [FILES] | [`files.md`](files.md) | The settings file, environment variables, and files on disk |

**2.2.5** The protocol states every externally observable behaviour of hmz: a public Python name
and its signature, a command, a flag or another command-line token, an HTTP method and path, a
file path or file format, an environment variable, an exit status, a stream's content, a message
the user sees, and a process hmz starts and its arguments.

**2.2.6** The protocol constrains nothing that is not externally observable; an implementation is
free in everything the protocol does not state.

**2.2.7** Where an implementation and the protocol disagree, the protocol states the intended
behaviour.

**2.2.8** The protocol never calls an epic a run; the word run appears as a name only inside a
quoted identifier, string or message.

**2.2.9** The underscore-prefixed class attributes that Section 3 of [PYTHON] lists
(`_permission`, `_skills`, `_tools`, `_clis`, `_cpu_count`, `_memory`, `_gpu_count`,
`_gpu_memory` and `_image`) are public names of the flow API.

### 2.3. Parties and places

**2.3.1** **hmz** is the software the Humanize Protocol describes, and the program of the same name
that it installs.

**2.3.2** A **user** is the person who operates hmz through a frontend or the software development
kit.

**2.3.3** A **machine** is one running operating-system instance, on which processes run and which
has its own file systems and its own temporary directory.

**2.3.4** **This machine** is the machine on which the hmz process being described runs.

**2.3.5** The **home** is the directory named by the environment variable `HUMANIZE_HOME` where that
variable is set and non-empty, and the directory `.hmz` in the user's home directory otherwise.

**2.3.6** A **workspace** is a directory of a machine in which epics are run, identified by its
absolute path with every symbolic link resolved.

**2.3.7** A distribution of the Windows Subsystem for Linux (WSL) is a machine apart from the
Windows that runs it.

**2.3.8** For the desktop application on Windows, which runs hmz in WSL, this machine is the WSL
distribution in which it runs hmz, and not the Windows that runs the application.

### 2.4. Flows and epics

**2.4.1** A **flow** is a Python function, declared through the flow API (Section 3 of [PYTHON]),
that directs agents and envs to carry out a task.

**2.4.2** A **flow author** is a person who writes a flow.

**2.4.3** A **flowverse** is a named collection of flows from which hmz resolves a flow's name.

**2.4.4** An **epic** is one execution of one flow, from its start to its end, together with the
record hmz keeps of it.

**2.4.5** A **role** is a named place that a flow declares and that an agent or an env fills for one
epic.

**2.4.6** A **turn** is one message given to a session together with everything the harness does
until it answers that message.

**2.4.7** A **side question**, also called **btw**, is a question about an epic that the user asks a
separate agent, outside every session of the epic.

### 2.5. Agents and where they run

**2.5.1** A **harness** is a coding-agent command-line program that hmz drives to take an agent's
turns.

**2.5.2** An **agent** is one harness, run as one account or as the harness machine's own login, on
one model at one effort, that fills one agent role of an epic.

**2.5.3** A **session** is one conversation between an agent and its harness, which keeps its
history from one turn to the next.

**2.5.4** A **provider**, also called an **account**, is a named set of credentials and settings for
one harness, kept by hmz, under which that harness's turns run.

**2.5.5** The **harness machine** of a session is the machine on which its harness process runs.

**2.5.6** An **env** is the place where an agent's commands act and its files are read and written:
one directory of one machine, filling one env role of an epic.

**2.5.7** The **env machine** of a session is the machine of the env in which its commands act.

**2.5.8** The **placement** of a session is two settings: its **env location**, which is **local**
where the env machine is this machine and **standalone** otherwise; and its **harness location**,
which is **local** where the harness machine is this machine, **env** where the harness is the
program installed on a standalone env machine and runs there without a mirror, and **standalone**
where the harness machine is the machine of a runtime other than this machine, the env machine
included, and the harness works in a mirror there.

**2.5.9** A **mirror** is a directory on a harness machine that reproduces an env's workspace,
filled on demand, in which a harness works whose location is standalone, or local with the env
standalone.

**2.5.10** A **runtime** is a named description, written in the settings file, of an ssh host, a
docker daemon, a docker swarm, the Apple containers of a Mac, or a Slurm cluster on which envs are
put.

### 2.6. Processes and frontends

**2.6.1** The **daemon** is the hmz process of one user on one machine that holds that machine's
epics apart from every frontend.

**2.6.2** A **frontend** is a way for a user to start, watch and steer epics: the command line, the
terminal interface (TUI), the web interface, or the desktop application for macOS or for Windows.

**2.6.3** The **settings file** is the file `settings.yaml` in the home (Section 3 of [FILES]).

## 3. Epics

### 3.1. Scope

This section defines how **hmz** starts, identifies, limits, stops, ends, records and picks up
an **epic**: the loading of the **flow** the epic executes, the parameters and budget the epic is
given, the setup a **workspace** remembers between epics, the states in which an epic ends, and how
many epics execute at once in one workspace.

Out of scope:

- The grammar of flow references, of agent and environment specifications and of the budget flags
  ([CLI], Section 3 of [PYTHON]).
- The layout and record format of an epic directory (Section 6 of [FILES]).
- The settings file in which remembered setup is kept (Section 3 of [FILES]).
- Where an agent's harness and an environment are placed, and fallback between runtimes (Section 6,
  Section 7).
- Which agents and accounts exist and how a turn is taken (Section 4, Section 5).
- The `chat` flow and its conversation semantics (Section 8).
- Live figures, traces, profiles and notices of an epic (Section 10).
- Backups, export and import of an epic (Section 11).

### 3.2. Terminology

**3.2.1** **Epic name**: the identifier by which hmz names one epic.

**3.2.2** **Budget**: the set of limits under which an epic or a flow call executes, consisting of
one or more of a **cost limit** (US dollars), an **output-token limit** (tokens written by agents)
and a **duration limit** (wall-clock time), together with a **graceful** flag for each limit.

**3.2.3** **Spent**: the cost, output tokens and seconds that the budget of an epic counted when the
epic ended.

**3.2.4** **Resumable flow**: a flow whose declaration states that an epic of it can be picked up
(Section 3 of [PYTHON]).

**3.2.5** **Flow state**: the values a resumable flow writes for itself while an epic of it executes
(Section 3 of [PYTHON]).

**3.2.6** **Picking up**: starting a new epic of a resumable flow from the flow state an earlier
epic of that flow left; the earlier epic is the **origin** of the new one.

**3.2.7** **Stopping**: a request, made by a **user** through a **frontend** or by a signal, that an
executing epic end before its flow returns.

**3.2.8** **Forcing**: a request, made while an epic is stopping, that every **session** of the epic
still in a turn be closed without waiting for the flow to unwind.

**3.2.9** **Remembered setup**: what a workspace keeps, per flow, of how that flow was last set up
through a frontend.

**3.2.10** **Ending**: the state in which an epic is read back, as Section 3.3.6 defines.

**3.2.11** **Host slot**: the slot (Section 4.2.6 of [DAEMON]) naming one host (Section 3.2.1 of
[DAEMON]) of a workspace on **this machine**: the workspace host's, or one chat host's.

**3.2.12** **Price list**: the list of per-token model prices kept on this machine (Section 10.3.3).

### 3.3. Lifecycle

#### 3.3.1. Starting

**3.3.1.1** hmz MUST start an epic only when a user or a program asks for one through `hmz exec`
([CLI]), a frontend ([TUI], Section 3 of [WEB]) or the SDK (Section 4 of [PYTHON]).

**3.3.1.2** hmz MUST refuse to start an epic whose flow cannot be found or loaded (Section 3.3.2).

**3.3.1.3** hmz MUST refuse to start an epic that is given a **role** the flow does not declare.

**3.3.1.4** hmz MUST refuse to start an epic that is given one role more than once.

**3.3.1.5** hmz MUST refuse to start an epic that leaves out a required role which hmz does not fill
itself.

**3.3.1.6** hmz MUST refuse to start an epic that is given a role which hmz fills itself: an
outworlder role or a local-environment role (Section 3 of [PYTHON]).

**3.3.1.7** hmz MUST refuse to start an epic that is given an **agent** whose **harness** differs
from the harness its role names, or whose harness does not serve the capabilities its role declares.

**3.3.1.8** hmz MUST refuse to start an epic that is given an agent or environment specification
that cannot be read, or that names a **runtime** which is not saved.

**3.3.1.9** hmz MUST refuse to start an epic that is given a parameter the flow does not declare, or
a parameter value that cannot be read as the declared type.

**3.3.1.10** hmz MUST refuse to start an epic that is given no budget, unless its flow is `chat`
(Section 3.3.4.2).

**3.3.1.11** hmz MUST refuse to start an epic that names a backup target which does not exist
(Section 11.3.2).

**3.3.1.12** hmz MUST refuse to start an epic that asks to pick up where Section 3.3.7.5 forbids it.

**3.3.1.13** hmz MUST make every refusal under Section 3.3.1.2 to Section 3.3.1.12 before any agent
starts and before any session opens, MUST state the reason, and MUST NOT create an epic directory
for the refused request.

**3.3.1.14** `hmz exec` MUST exit with status 2 for every refusal under Section 3.3.1.2 to Section
3.3.1.12.

**3.3.1.15** hmz MUST probe every **env** of the epic before the flow is called; where an env cannot
be reached or cannot hold what its role declares, and no fallback runtime holds it (Section 7), hmz
MUST refuse the epic with the reason before the flow is called.

**3.3.1.16** hmz MUST create exactly one epic for each request that passes Section 3.3.1.2 to
Section 3.3.1.12, and MUST record in it the flow's canonical reference, the task, the workspace,
each role's agent and env as given, the env actually used for each role where it differs from the
env given, the parameters, the budget, the profiling switches, the backup targets and, where it
picks up, its origin (Section 6 of [FILES]).

**3.3.1.17** hmz MUST call the flow with the task, every given agent and env, the workspace for
every local-environment role left out, and the epic's outworlder for every outworlder role left out.

**3.3.1.18** An epic started by `hmz exec` MUST have an outworlder that is away, so that every
question its flow asks a person is answered as Section 3 of [PYTHON] defines for an away outworlder.

**3.3.1.19** Starting an epic through `hmz exec` or the SDK MUST NOT change the remembered setup of
any workspace.

#### 3.3.2. Loading the flow

**3.3.2.1** hmz MUST resolve the flow reference of an epic as Section 3 of [PYTHON] defines, before
the epic is created.

**3.3.2.2** Where a flow reference resolves to nothing, hmz MUST state which of the following holds:
an index lists the flow but it is not installed; the reference uses a spelling no longer accepted,
together with the accepted spelling; a path lacks its leading `./`; an index that could hold the
flow has not been fetched.

**3.3.2.3** Where a flow fails while it is imported, hmz MUST refuse the epic and state the
failure's reason.

**3.3.2.4** hmz MUST load a flow as its files are when the epic starts; a change to those files
after the epic started MUST NOT affect that epic, and MUST take effect for the next epic that loads
the flow while no other epic of this process uses it.

**3.3.2.5** A flow named by a version-control reference MUST be fixed, for the whole epic, to the
commit the reference resolved to when the epic first fetched it.

#### 3.3.3. Parameters

**3.3.3.1** hmz MUST hand the flow every parameter given, validated against the type the flow
declares for it, and the declared default for every parameter not given.

**3.3.3.2** hmz MUST reserve the parameter name `budget` for the budget, and MUST refuse a flow that
declares a parameter of that name.

#### 3.3.4. Budget

**3.3.4.1** Every epic MUST execute under a budget that sets at least one limit, and a limit MUST
NOT be negative.

**3.3.4.2** An epic of the `chat` flow that is given no budget MUST execute under a budget whose
cost limit is unbounded.

**3.3.4.3** The graceful flag of each limit of a budget MUST be true unless it is given as false,
for that limit or for every limit.

**3.3.4.4** The cost and output tokens of every turn taken anywhere in an epic MUST count against
the budget of the epic and against the budget of every flow call above that turn.

**3.3.4.5** A duration limit MUST be a deadline counted from the start of the epic or flow call
whose budget it is, and MUST NOT be a sum over concurrent turns.

**3.3.4.6** The budget in force for a flow call MUST be the tighter, limit by limit, of the call's
own budget and what remains of every budget above it.

**3.3.4.7** The cost of a turn taken by a model that the price list does not price MUST count as
zero against a cost limit.

**3.3.4.8** Where an epic has a finite cost limit and an agent of the epic runs a model that the
price list does not price, hmz MUST state, before the first turn and without asking, that the cost
limit cannot stop what that model spends.

**3.3.4.9** Where an epic has a finite cost limit and the price list is missing or stale (Section
10.3.3), hmz MUST attempt to refresh the price list before the first turn, MUST wait no longer than
that fetch's own timeout, and MUST stop waiting once the epic is stopped.

**3.3.4.10** Where an epic has no finite cost limit and the price list is missing or stale, hmz MUST
refresh it without delaying the epic.

**3.3.4.11** Once a limit of a budget is reached, hmz MUST refuse every later turn under that budget
and MUST end the flow call that owns that budget.

**3.3.4.12** Where the graceful flag of a limit is true, hmz MUST let a turn under way when that
limit is reached finish before the owning flow call is ended.

**3.3.4.13** Where the graceful flag of a limit is false, hmz MUST interrupt a turn under way at the
moment that limit is reached.

**3.3.4.14** hmz MUST record an epic ended because a limit of its own budget was reached as
`stopped`, and MUST NOT record it as `failed`.

**3.3.4.15** `hmz exec` MUST state on standard error, in one line naming the limit, that its epic
was stopped by its budget, and MUST exit with status 0 in that case.

**3.3.4.16** hmz MUST record the spent figures of an epic when the epic ends.

**3.3.4.17** hmz MUST read back no spent figures for an epic that is executing or that ended without
recording them.

**3.3.4.18** Where pricing fails (Section 4.8.2.7) once the price list has been asked for under
Section 3.3.4.9 or Section 3.3.4.10, hmz MUST refuse the epic before its first turn, whatever its
budget, as a line refused (`hmz exec` exits with status 2).

**3.3.4.19** A turn whose pricing fails MUST count as an infinite cost; and where what an epic or
flow call has spent is not a finite number, hmz MUST refuse every later turn under it with
`CostExceeded`, whatever its budget.

#### 3.3.5. Stopping and forcing

**3.3.5.1** Any frontend attached to the host slot of an executing epic MAY stop it.

**3.3.5.2** `hmz exec` MUST stop its epic on an interrupt, a terminate or a hangup signal.

**3.3.5.3** Stopping MUST interrupt every turn under way and MUST cancel the flow, which then
unwinds.

**3.3.5.4** As a stopped flow unwinds, hmz MUST close every session and env, and remove every
temporary directory, that the flow opened and has not handed to flow state.

**3.3.5.5** hmz MUST leave a file that an agent was writing when its turn was interrupted as it was
at the moment of interruption.

**3.3.5.6** Any frontend attached to the host slot of a stopping epic MAY force it.

**3.3.5.7** Forcing MUST close every session of the epic still in a turn, and MUST state how many
sessions it closed.

**3.3.5.8** `hmz exec` MUST exit with status 128 plus the number of the signal that stopped its
epic, and MUST exit only after the epic has closed everything it opened.

**3.3.5.9** hmz MUST record an epic ended by stopping or forcing as `stopped`.

**3.3.5.10** A frontend MUST NOT offer a stop for an epic of the `chat` flow; how a chat ends is
defined in Section 8.

#### 3.3.6. Ending states

**3.3.6.1** hmz MUST read back every epic in exactly one of the endings `running`, `done`, `failed`,
`stopped` and `unfinished`.

**3.3.6.2** An epic MUST read back as `running` while it has recorded no end and a process on this
machine holds it.

**3.3.6.3** An epic MUST read back as `done` where its flow returned.

**3.3.6.4** An epic MUST read back as `failed` where its flow, or hmz on its behalf, raised an error
other than a stop or a budget exhaustion.

**3.3.6.5** An epic MUST read back as `stopped` where Section 3.3.4.14 or Section 3.3.5.9 applies.

**3.3.6.6** An epic MUST read back as `unfinished` while it has recorded no end and no process on
this machine holds it.

**3.3.6.7** hmz MUST NOT reopen an epic that has recorded an end, except as Section 3.3.7.10
provides.

**3.3.6.8** Where a frontend reports how the last epic of a host slot ended, it MUST distinguish an
epic refused before its flow was called, an epic ended by its budget, an error the flow raised and
an error inside hmz, and MUST state the reason for each.

**3.3.6.9** hmz MUST record, for every flow call within an epic, the task it was called with, when
it began, when it ended and how it ended, so that the epic reads back as the tree of flow calls it
made, however deep and however many executed concurrently.

**3.3.6.10** hmz MUST read back a flow call that ended by a cancellation from outside it, or by a
budget, as `stopped`.

**3.3.6.11** hmz MUST record, for every session an epic opened, which agent opened it, which flow
call opened it, the account and model its turns ran as, the identifier its harness gave it, the
session it was forked from where there is one, and where it is kept (Section 6 of [FILES]).

#### 3.3.7. Picking up

**3.3.7.1** Picking up MUST be available only for an epic of a resumable flow that recorded flow
state.

**3.3.7.2** hmz MUST keep the flow state of an epic inside that epic as the flow writes it, so that
the flow state is available to a later epic even where the process of the earlier epic was killed.

**3.3.7.3** An epic that picks up MUST be a new epic with its own epic name, MUST record its origin,
and MUST start from a copy of the origin's flow state.

**3.3.7.4** Picking up MUST NOT change the origin.

**3.3.7.5** hmz MUST refuse to pick up, stating the reason, where the flow is not resumable as it is
now, where no epic of the flow in the workspace recorded flow state, or where the origin was
imported and Section 3.3.7.11 forbids it.

**3.3.7.6** `hmz exec --resume` MUST pick up the newest epic of the named flow in the current
workspace that can be picked up, and MUST use the agents, envs, parameters and budget given on its
own command line.

**3.3.7.7** On picking up, the top-level flow call MUST continue from the flow state; a nested flow
call MUST continue from the earlier call that had the same callee, task, agents, envs and
parameters, and MUST start afresh where there is none.

**3.3.7.8** A session written into flow state MUST be carried on, in the epic that picks up, from
its conversation as it was when it was written, subject to the conditions Section 3 of [PYTHON]
defines; every other session MUST start fresh.

**3.3.7.9** What the origin spent MUST NOT count against the budget of the epic that picks up.

**3.3.7.10** An epic of the `chat` flow that is carried on MUST continue in the same epic rather
than a new one; that epic MUST record that it was opened again, MUST read back as `running` until it
ends again, and MUST read back as having spent the sum of what each opening spent.

**3.3.7.11** hmz MUST refuse to pick up an imported epic unless the workspace it executed in exists
on this machine at the same absolute path and, where that workspace is a git repository and the epic
recorded a commit, the repository holds that commit; the refusal MUST state which condition failed.

### 3.4. Workspaces

#### 3.4.1. Remembered setup

**3.4.1.1** A workspace MUST remember, per flow, the last setup saved for that flow through a
frontend: each agent role's agent, each env role's env, the parameters, the budget, the two
profiling switches and the backup targets.

**3.4.1.2** A workspace MUST remember which flow was last set up in it.

**3.4.1.3** A frontend MUST offer the remembered setup of a flow the next time that flow is set up
in the same workspace.

**3.4.1.4** Saving one part of a flow's setup MUST NOT erase the other parts of that flow's
remembered setup that the save does not give.

**3.4.1.5** A remembered empty list of backup targets MUST mean no targets, and no remembered backup
targets MUST mean the default targets.

**3.4.1.6** A remembered agent MUST consist of a harness, an account, a model and an effort, and
nothing else; a remembered entry that is not one MUST be read as nothing remembered.

**3.4.1.7** Remembered setup MUST NOT turn on either profiling switch for an epic started by `hmz
exec` or the SDK.

**3.4.1.8** Two frontends saving setup for one workspace MUST NOT overwrite each other's writes to
different entries.

#### 3.4.2. Identity

**3.4.2.1** hmz MUST give every epic an epic name consisting of the UTC moment the epic was created,
to the millisecond, followed by a random suffix, such that epic names sort in the order their epics
were created.

**3.4.2.2** hmz MUST keep every epic under the workspace in which it executed (Section 6 of
[FILES]).

**3.4.2.3** hmz MUST list the epics of a workspace in the order they were created.

**3.4.2.4** A frontend MUST address an executing epic by its epic name once the epic has one.

**3.4.2.5** hmz MUST read a directory among a workspace's epics that holds no epic record as no
epic, and MUST NOT fail to list the other epics because of it.

#### 3.4.3. Concurrency

**3.4.3.1** At most one epic of a flow other than `chat` MUST execute at a time in a workspace's own
host slot.

**3.4.3.2** hmz MUST refuse a request to start an epic in a workspace's own host slot while another
epic executes or stops there.

**3.4.3.3** Any number of `chat` epics MAY execute in one workspace, each in a host slot of its own,
concurrently with the epic of the workspace's own host slot.

**3.4.3.4** An epic started by `hmz exec` MUST execute in the process of that command, and MUST NOT
be refused because another epic executes in the same workspace.

**3.4.3.5** Epics of different workspaces MUST execute independently of one another.

**3.4.3.6** hmz MUST report whether an epic is held by a process on this machine, whichever process
holds it.

> Informative: a frontend's request to start an epic goes to a host slot, held in a **daemon**
> where one runs (Section 3 of [DAEMON]); attaching and detaching a frontend does not affect the
> epic.

## 4. Agents

### 4.1. Scope

This section governs how **hmz** drives a **harness** as an **agent**: which harnesses exist
and how an agent is named, which models and efforts an agent runs at, the configuration a harness is
launched with, what an agent is permitted to touch and how each harness is confined, the turns,
sessions, forks, steering, goals and schemas a harness serves, the hooks a flow hangs on an agent,
the tools and command lines a flow hands an agent, what happens when a turn fails, the watchdog,
token usage and cost, the LiteLLM gateway, harnesses added by the user over the Agent Client
Protocol, and the person at the prompt acting as an agent.

Out of scope:

- The accounts an agent runs as, their storage and their credentials: Section 5.
- Where a harness runs relative to the env it works on, and the rule for configuration that crosses
  machines: Section 6.
- What an env is and how it is opened: Section 7.
- The flow-facing API through which a flow declares roles, permissions, hooks, tools and budgets:
  Section 3 of [PYTHON].
- The `-a` command-line option and exit statuses: [CLI].
- The `fallbacks` and `clis` keys of `settings.yaml`: Section 3 of [FILES].
- Where an epic keeps the sessions of its agents: Section 3.
- How usage and cost are displayed while an epic runs: Section 10.

### 4.2. Terminology

**4.2.1** **Harness kind**: the name by which hmz identifies one harness, as listed in Section
4.3.1.

**4.2.2** **Agent spec**: the text `<harness>[@<account>]/<model>[:<effort>]` that names an agent,
read as Section 7.4 of [CLI] states.

**4.2.3** **Place**: the text `<harness>[@<account>]/<model>`, identifying a harness kind, an
account and a model, without an effort.

**4.2.4** **Effort**: how hard the model is asked to think, in the words of the harness's effort
ladder (Section 4.4.3).

**4.2.5** **Effort ladder**: the ordered list of efforts a harness kind accepts.

**4.2.6** **Rung**: one of the four permission levels `read-only`, `workspace-write`, `auto` and
`bypass`, ordered from tightest to loosest.

**4.2.7** **Grant**: the four scopes `local`, `user`, `system` and `online` that a flow declares for
a role, each `NONE`, `READ` or `ALL`, as Section 3 of [PYTHON] defines them.

**4.2.8** **Confinement**: the restriction hmz places around the harness process and every process
it starts, so that the agent touches no more than its grant allows.

**4.2.9** **Managed item**: an item hmz supplies to a harness at launch that the user did not
configure: a flow skill, a flow-declared subagent, a flow-declared command, the hmz tool server, a
hook hmz hangs, a model declaration hmz adds for a flow or for an account, or an execpolicy rule hmz
adds for a fake command line on `codex`.

**4.2.10** **System level**: the harness machine's system-wide configuration of a harness.

**4.2.11** **User level**: the harness machine's per-user configuration of a harness, together with
the managed items of the agent.

**4.2.12** **Project level**: the configuration of a harness found in the env's workspace.

**4.2.13** **Fault class**: the classification hmz assigns to a failed turn, one of `contended`,
`spent`, `throttled`, `refused`, `unlisted`, `retired`, `missing`, `sandboxed`, `unmirrored`,
`fenced`, `killed` and `dropped`, or unclassified.

**4.2.14** **Fallback chain**: the ordered list of places to which a turn is carried once its own
place has no retries left.

**4.2.15** **Stand-in**: an agent at the next place of a fallback chain that takes a turn its
original agent could not.

**4.2.16** **Fake tool**: a tool a flow declares whose calls run in the flow's process.

**4.2.17** **Fake command line**: a program a flow declares that appears on the agent's `PATH` and
whose runs are answered in the flow's process.

**4.2.18** **Gateway**: a LiteLLM proxy that hmz runs on this machine's loopback interface to carry
an account the harness has no way in for of its own.

**4.2.19** **ACP harness**: a harness the user adds by command line, driven over the Agent Client
Protocol.

**4.2.20** **Human agent**: the agent whose turns are answered by the user at the prompt.

**4.2.21** **Watchdog window**: the time a turn is permitted to pass without any output from its
harness before the watchdog acts (Section 4.12).

### 4.3. Harnesses

#### 4.3.1. Harness kinds

**4.3.1.1** hmz MUST drive exactly the following built-in harness kinds, and MUST accept each under
every alias listed for it:

| Kind | Aliases | Product |
| --- | --- | --- |
| `agy` | `antigravity` | Antigravity CLI |
| `claude` | `claude-code` | Claude Code |
| `codex` | — | Codex |
| `cursor-agent` | `cursor-cli` | Cursor Agent |
| `dsh` | `deepseek-harness` | DeepSeek Harness (Python SDK, no CLI) |
| `grok` | `grok-build`, `grokbuild` | Grok Build |
| `kimi` | `kimi-code` | Kimi Code |
| `litellm` | — | a model called directly through LiteLLM (no CLI) |
| `mcode` | `minimax`, `minimax-code` | MiniMax Code |
| `mimo` | `mimocode`, `mimo-code` | mimocode |
| `omp` | `oh-my-pi` | Oh My Pi |
| `opencode` | — | opencode |
| `pi` | — | pi |
| `qwen` | `qwen-code` | Qwen Code |

**4.3.1.2** hmz MUST additionally drive, as an ACP harness, every command line the user has added
under its name (Section 4.14).

**4.3.1.3** hmz MUST record a harness kind by its kind name and MUST NOT record an alias.

**4.3.1.4** hmz MUST refuse a harness kind that is neither built in nor added, where the agent spec
naming it is read.

#### 4.3.2. Installation

**4.3.2.1** Other than under harness location env, hmz MUST locate a harness's program on the `PATH`
of the harness machine, and, where it is not on the `PATH`, in `~/.local/bin`, `/usr/local/bin`,
`/opt/homebrew/bin`, `/usr/bin` and `/bin`, in that order.

**4.3.2.2** Under harness location env, hmz MUST locate a harness's program as Section 6.3.2.3
states.

**4.3.2.3** A session whose harness is not installed on the harness machine MUST be refused before
its first turn with `HarnessNotInstalled`, whose message MUST name the harness and the command that
installs it.

**4.3.2.4** The install command named under Section 4.3.2.3 MUST be the following, and for a harness
with no install command the message MUST say `install <cli> and put it on PATH`:

| Kind | Install command |
| --- | --- |
| `claude` | `npm i -g @anthropic-ai/claude-code` |
| `codex` | `npm i -g @openai/codex` |
| `cursor-agent` | `curl https://cursor.com/install -fsS \| bash` |
| `dsh` | `pip install` of the DeepSeek Harness SDK and `python-dotenv` |
| `grok` | `npm i -g @xai-official/grok` |
| `kimi` | `npm i -g @moonshot-ai/kimi-code` |
| `litellm` | `pip install` of LiteLLM |
| `mcode` | `npm i -g @minimax-ai/code` |
| `mimo` | `npm i -g @mimo-ai/cli` |
| `omp` | `curl -fsSL https://omp.sh/install \| sh` |
| `opencode` | `npm i -g opencode-ai` |
| `pi` | `npm i -g @earendil-works/pi-coding-agent` |
| `qwen` | `npm i -g @qwen-code/qwen-code` |

**4.3.2.5** A turn whose harness program cannot be started MUST fail with the fault class `missing`.

#### 4.3.3. Capabilities served to flows

**4.3.3.1** Each harness kind MUST serve to a flow exactly the capabilities marked in the following
table, where Tools is fake tools (Section 4.10.1), Goal is `/goal` (Section 4.7.6), Loop is `/loop`
(Section 4.7.7), Steer is steering a running turn (Section 4.7.5), Perm is the permission-request
hook, Sub is the subagent start and stop hooks, and Ask is the ask-user hook (Section 4.9):

| Kind | Tools | Goal | Loop | Steer | Perm | Sub | Ask |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| `claude` | yes | yes | yes | yes | yes | yes | yes |
| `codex` | yes | yes | — | yes | yes | yes | yes |
| `kimi` | — | yes | — | yes | yes | — | yes |
| `pi`, `omp` | yes | — | — | yes | — | — | yes |
| `dsh` | yes | yes | — | — | — | — | — |
| `cursor-agent`, `mcode` | — | — | — | — | — | yes | — |
| `agy`, `grok`, `mimo`, `opencode`, `qwen` | yes | — | — | — | — | — | — |
| `litellm`, an ACP harness | — | — | — | — | — | — | — |

**4.3.3.2** hmz MUST refuse, before its first turn, a role whose declared type requires a capability
that the harness filling it does not serve.

### 4.4. Agent specs, models and efforts

#### 4.4.1. Agent specs

**4.4.1.1** hmz MUST read an agent spec, and an `-a` item, as Section 7.4 of [CLI] states.

**4.4.1.2** An absent `<account>` MUST mean the harness machine's own sign-in of that harness, as
Section 5 defines it.

**4.4.1.3** An absent `<effort>`, an empty `<effort>`, and the effort `auto` MUST each mean that no
effort is said to the harness.

**4.4.1.4** An agent spec naming an account that does not exist MUST be refused as Section 5.3.2.2
states.

**4.4.1.5** An effort not on the harness's ladder for that model MUST be refused before the epic
starts where the agent spec is given to start the epic (Section 7.7 of [CLI] for `-a`), and
otherwise before the agent's first turn with `HarnessUnrecoverable` naming the agent spec and the
reason.

**4.4.1.6** A setting the harness cannot express MUST be refused before the agent's first turn with
`HarnessUnrecoverable` naming the agent spec and the reason.

#### 4.4.2. Models

**4.4.2.1** hmz MUST pass the model to the harness in the harness's own spelling and MUST NOT
translate it, except as Section 4.4.2.2, Section 4.13 and Section 5 state for gateway accounts.

**4.4.2.2** For `cursor-agent`, hmz MUST pass the model with the effort and the service tier written
into the model id as `<model>-<effort>[-fast]`, where that id appears in the account's model
catalogue; a model id that already carries an effort MUST be passed unchanged.

**4.4.2.3** For an ACP harness, the model MUST be `as configured`, and hmz MUST say no model to the
harness.

**4.4.2.4** hmz MUST keep, per harness kind and per account, a catalogue of the models the account
runs and the efforts each takes, as Section 5 states.

**4.4.2.5** Where Claude Code reports that it runs a model other than the one asked for, and the
model asked for is neither a Claude Code alias nor a dated form of the model reported, hmz MUST emit
one notice per session naming both models, and MUST let the turn continue.

#### 4.4.3. Efforts

**4.4.3.1** Each harness kind MUST accept exactly the following effort ladder, hardest first, and
`auto`:

| Kind | Effort ladder |
| --- | --- |
| `agy` | `high`, `medium`, `low` |
| `claude` | `ultracode`, `max`, `xhigh`, `high`, `medium`, `low` |
| `codex` | `ultra`, `max`, `xhigh`, `high`, `medium`, `low` |
| `cursor-agent` | `max`, `xhigh`, `extra-high`, `high`, `medium`, `low`, `minimal`, `none` |
| `dsh` | `max`, `high`, `low`, `off` |
| `grok` | `xhigh`, `high`, `medium`, `low` |
| `kimi` | `max`, `high`, `medium`, `low`, and each prefixed with `swarm` |
| `litellm` | `high`, `medium`, `low`, `minimal`, `none` |
| `mcode` | `max`, `xhigh`, `high`, `medium`, `low` |
| `mimo`, `opencode` | `xhigh`, `high`, `medium`, `low`, `minimal` |
| `omp`, `pi` | `max`, `xhigh`, `high`, `medium`, `low`, `minimal`, `off` |
| `qwen` | `max`, `xhigh`, `high`, `medium`, `low`, `none` |
| an ACP harness | `as configured` |

**4.4.3.2** A model's ladder MUST be the harness's ladder narrowed to the efforts the account's
model catalogue lists for that model, in ladder order, and MUST be the whole ladder where the
catalogue lists none.

**4.4.3.3** The `claude` effort `ultracode` MUST be accepted and MUST NOT be listed in a model's
ladder; it MUST run as `xhigh` with Claude Code opted into orchestrating a fleet of subagents.

**4.4.3.4** The `omp` effort `off` MUST remain on every model's ladder whatever the catalogue lists.

**4.4.3.5** A `kimi` effort prefixed with `swarm` MUST run at the unprefixed effort as a fleet of
subagents.

**4.4.3.6** An ACP harness MUST accept every effort and MUST be told none.

**4.4.3.7** A change of effort made while a turn runs MUST take effect from the session's next turn
and MUST NOT change the effort of the running turn.

**4.4.3.8** A changed effort MUST be checked against the model's ladder as a configured effort is.

#### 4.4.4. Service tier

**4.4.4.1** An agent MUST be permitted the service tier `default` or `fast`.

**4.4.4.2** The tier `fast` MUST be served by `claude` (Claude Code's fast mode), `codex` (the
`priority` tier) and `cursor-agent` (the `-fast` model id the account lists), and MUST be refused on
every other harness kind and on `cursor-agent` where the account lists no `-fast` id.

### 4.5. Configuration levels

#### 4.5.1. Levels

**4.5.1.1** hmz MUST launch every harness with its configuration drawn from three levels: the system
level, the user level and the project level.

**4.5.1.2** hmz MUST NOT replace, override, write or hide the system level of any harness.

**4.5.1.3** The user level MUST be the harness machine's user configuration of the harness, merged
at launch with the agent's managed items.

**4.5.1.4** Where a managed item and an item of the user's configuration have the same name, the
managed item MUST take effect for that launch.

**4.5.1.5** The project level MUST be the env's workspace, read by the harness as the harness reads
a workspace when the user runs it by hand.

**4.5.1.6** hmz MUST NOT place any managed item into the workspace.

**4.5.1.7** hmz MUST NOT switch on or off any skill, subagent, command, hook or tool server that the
user configured for the harness.

**4.5.1.8** Program-running configuration in the workspace MUST be honoured or refused as Section
6.7 states.

**4.5.1.9** No permission field governs whether workspace configuration is honoured; a grant MUST
NOT be read as such a field.

#### 4.5.2. Virtual config home

**4.5.2.1** hmz MUST launch each of the harnesses `claude`, `codex` and `qwen` with a virtual config
home (Section 8.2.5 of [FILES]).

> Informative: each of these harnesses rewrites its own configuration while running: `claude`
> rewrites `.claude.json`, `codex` records project trust in `config.toml`, and `qwen` migrates its
> settings.

**4.5.2.2** hmz MUST launch each of the harnesses `grok`, `pi`, `omp`, `mcode`, `agy`,
`cursor-agent` and `kimi` with a virtual config home wherever hmz adds a managed item to it.

> Informative: these harnesses offer no flag or environment variable through which user-level
> configuration is added.

**4.5.2.3** hmz MUST build a virtual config home on the harness machine, for one harness process,
from the user's configuration of that harness on that machine merged with the agent's managed items,
before that process starts.

**4.5.2.4** Two harness processes MUST NOT share one virtual config home.

**4.5.2.5** Every change the harness makes to a configuration file copied into its virtual config
home MUST be discarded when the process exits.

**4.5.2.6** Every other write the harness makes inside its virtual config home MUST reach the real
harness home (Section 8.6.8 of [FILES]), except the session records kept in an epic as Section 8.5
of [FILES] states.

**4.5.2.7** Where the harness replaces an entry that its virtual config home links to the real
harness home, other than a configuration file copied under Section 4.5.2.5, hmz MUST write the
replacement to the entry the link named, or to the account's file where the agent runs as an
account, when the process exits, unless that entry is at least as new as the replacement.

**4.5.2.8** hmz MUST NOT write any file of the user's real configuration of a harness, on any
machine, in building, using or discarding a virtual config home.

**4.5.2.9** Credential files read through a virtual config home MUST be the user's real credential
files, or the account's files where the agent runs as an account, and MUST NOT be copied into it, so
that a credential the harness refreshes during the process persists after it exits.

**4.5.2.10** A change the user makes to the real configuration while a harness process runs MUST
take effect no later than that harness's next launch.

#### 4.5.3. Managed items through flags and environment

**4.5.3.1** Each of the harnesses `opencode`, `mimo`, `dsh` and every ACP harness MUST receive its
managed items through command-line flags or environment variables at launch.

**4.5.3.2** A harness listed in Section 4.5.3.1 MUST be launched with its configuration home as the
user left it.

**4.5.3.3** A managed item that a harness has no means of receiving at the user level MUST NOT be
delivered to it by any other means, and a flow skill that cannot be delivered MUST be omitted from
that harness's sessions without failing the turn.

**4.5.3.4** `litellm` MUST read no configuration home and MUST receive no managed item.

#### 4.5.4. Flow skills

**4.5.4.1** A session MUST carry every skill the flow brings for its role unless the flow selects a
subset for that session, in which case it MUST carry exactly that subset.

**4.5.4.2** A skill name the flow selects that the flow does not bring MUST be ignored and MUST NOT
be refused.

**4.5.4.3** A change of the skills a session carries MUST take effect from the session's next turn.

**4.5.4.4** Where a skill the user configured and a flow skill have the same name, the workspace's
skill of that name MUST take precedence over both, and the flow skill MUST take precedence over the
user's.

#### 4.5.5. Program-running configuration

**4.5.5.1** For each harness, program-running configuration MUST be exactly the entries of the table
below: a file, at the path given relative to the session directory or any directory above it up to
the workspace, holding a non-empty value at any of the key paths given, where `*` stands for any one
key of a table or any one item of a list; or a directory, written with a trailing `/`, holding any
entry.

**4.5.5.2** A file of the table that hmz cannot read or cannot parse MUST count as holding
program-running configuration.

**4.5.5.3** The harnesses `dsh` and `litellm` MUST have no program-running configuration.

| Harness | Path | Key paths |
| --- | --- | --- |
| `agy` | `.agents/mcp_config.json` | `mcpServers.*.command` |
| `agy` | `.agents/hooks.json` | `*.*.*.hooks.*.command` |
| `agy` | `.agents/plugins/` | any entry |
| `claude` | `.claude/settings.json` | `hooks.*.*.hooks.*.command`, `statusLine`, `subagentStatusLine`, `fileSuggestion`, `apiKeyHelper`, `awsAuthRefresh`, `awsCredentialExport`, `gcpAuthRefresh`, `otelHeadersHelper`, `enabledPlugins.*`, `extraKnownMarketplaces` |
| `claude` | `.claude/settings.local.json` | `hooks.*.*.hooks.*.command`, `statusLine`, `subagentStatusLine`, `fileSuggestion`, `apiKeyHelper`, `awsAuthRefresh`, `awsCredentialExport`, `gcpAuthRefresh`, `otelHeadersHelper`, `enabledPlugins.*`, `extraKnownMarketplaces` |
| `claude` | `.mcp.json` | `mcpServers.*.command`, `mcpServers.*.headersHelper` |
| `codex` | `.codex/config.toml` | `mcp_servers.*.command`, `mcp_servers.*.http_headers_helper`, `hooks` |
| `codex` | `.codex/hooks.json` | `hooks.*.*.hooks.*.command` |
| `cursor-agent` | `.cursor/hooks.json` | `hooks.*.*.command` |
| `cursor-agent` | `.cursor/mcp.json` | `mcpServers.*.command` |
| `grok` | `.grok/config.toml` | `mcp_servers.*.command`, `plugins` |
| `grok` | `.grok/hooks/` | any entry |
| `grok` | `.claude/settings.json` | `hooks.*.*.hooks.*.command` |
| `grok` | `.claude/settings.local.json` | `hooks.*.*.hooks.*.command` |
| `kimi` | `.kimi-code/mcp.json` | `mcpServers.*.command` |
| `mcode` | `.mcp.json` | `mcpServers.*.command`, `mcpServers.*.headersHelper` |
| `mimo` | `mimocode.json` | `mcp.*.command`, `plugin`, `formatter.*.command`, `lsp.*.command` |
| `mimo` | `mimocode.jsonc` | `mcp.*.command`, `plugin`, `formatter.*.command`, `lsp.*.command` |
| `mimo` | `.mimocode/mimocode.json` | `mcp.*.command`, `plugin`, `formatter.*.command`, `lsp.*.command` |
| `mimo` | `.mimocode/mimocode.jsonc` | `mcp.*.command`, `plugin`, `formatter.*.command`, `lsp.*.command` |
| `mimo` | `.mimocode/plugins/` | any entry |
| `mimo` | `.mimocode/plugin/` | any entry |
| `omp` | `.omp/settings.json` | `extensions` |
| `omp` | `.omp/config.yml` | `extensions` |
| `omp` | `.omp/mcp.json` | `mcpServers.*.command` |
| `omp` | `.omp/.mcp.json` | `mcpServers.*.command` |
| `omp` | `mcp.json` | `mcpServers.*.command` |
| `omp` | `.mcp.json` | `mcpServers.*.command`, `mcpServers.*.headersHelper` |
| `omp` | `.omp/hooks/` | any entry |
| `omp` | `.omp/tools/` | any entry |
| `omp` | `.claude/hooks/` | any entry |
| `omp` | `.claude/tools/` | any entry |
| `omp` | `.codex/hooks/` | any entry |
| `omp` | `.codex/tools/` | any entry |
| `omp` | `.gemini/hooks/` | any entry |
| `omp` | `.gemini/tools/` | any entry |
| `omp` | `.omp/extensions/` | any entry |
| `opencode` | `opencode.json` | `mcp.*.command`, `plugin`, `formatter.*.command`, `lsp.*.command` |
| `opencode` | `opencode.jsonc` | `mcp.*.command`, `plugin`, `formatter.*.command`, `lsp.*.command` |
| `opencode` | `.opencode/opencode.json` | `mcp.*.command`, `plugin`, `formatter.*.command`, `lsp.*.command` |
| `opencode` | `.opencode/opencode.jsonc` | `mcp.*.command`, `plugin`, `formatter.*.command`, `lsp.*.command` |
| `opencode` | `.opencode/plugins/` | any entry |
| `opencode` | `.opencode/plugin/` | any entry |
| `pi` | `.pi/settings.json` | `extensions`, `packages`, `npmCommand` |
| `pi` | `.pi/mcp.json` | `mcpServers.*.command` |
| `pi` | `.pi/extensions/` | any entry |
| `qwen` | `.qwen/settings.json` | `hooks.*.*.hooks.*.command`, `mcpServers.*.command`, `tools.discoveryCommand`, `tools.callCommand`, `ui.statusLine.command` |

### 4.6. Permissions and confinement

#### 4.6.1. Approvals

**4.6.1.1** hmz MUST NOT put any action of an agent to any person or model for approval, except
where a flow hangs a permission-request hook (Section 4.9.3) or an ask-user hook (Section 4.9.4).

**4.6.1.2** What limits an agent MUST be its grant and the hooks its flow hangs.

#### 4.6.2. Rungs

**4.6.2.1** hmz MUST derive a rung from a role's grant as follows: `local` of `NONE` or `READ` gives
`read-only`; `local` of `ALL` gives `bypass`.

**4.6.2.2** On `kimi`, a rung other than `read-only` MUST become `auto` while a permission-request
hook or an ask-user hook is hung on the agent.

**4.6.2.3** A rung a harness does not accept MUST become `bypass`; `dsh` and every ACP harness
accept only `bypass`, and `mcode` does not accept `read-only`.

**4.6.2.4** Each rung MUST launch each harness as the following table states:

| Kind | `read-only` | `workspace-write` | `auto` | `bypass` |
| --- | --- | --- | --- | --- |
| `agy` | plan mode, read tools only | accept-edits mode | skip permissions | skip permissions |
| `claude` | `plan` | `acceptEdits` | `auto` | `bypassPermissions` |
| `codex` | sandbox `read-only` | sandbox `workspace-write` | `on-request` | `danger-full-access` |
| `cursor-agent` | `--mode plan` | sandbox on | `--auto-review` | sandbox off |
| `grok` | read tools only | web search off | every tool | every tool |
| `kimi` | `manual`, plan mode | `auto` | `yolo` | `auto` |
| `mcode` | refused | `full` | `smart` | `full` |
| `mimo`, `opencode` | edit, bash denied | web tools denied | nothing denied | nothing denied |
| `omp` | every approval denied | `yolo` | `yolo` | `yolo` |
| `pi` | write tools withheld | nothing withheld | nothing withheld | nothing withheld |
| `qwen` | write tools withheld | `web_fetch` withheld | nothing withheld | nothing withheld |
| `dsh`, ACP | refused | refused | refused | every request granted |
| `litellm` | nothing said | nothing said | nothing said | nothing said |

**4.6.2.5** Where Claude Code refuses `bypassPermissions` for the account or because it runs as
root, hmz MUST run that agent at `acceptEdits` with every request granted, and MUST say so once per
agent.

**4.6.2.6** Where Codex refuses `danger-full-access` on the harness machine, hmz MUST run that agent
at `auto` with every request granted, and MUST say so once per agent.

**4.6.2.7** Codex's approval policy MUST be `never` at every rung but `auto`.

**4.6.2.8** hmz MUST NOT write a rung into any configuration file of the user.

**4.6.2.9** A fake command line ruled out of Codex's sandbox (Section 4.10.2.8) MUST NOT widen the
sandbox of any other command, its network included: at `read-only` the network MUST stay cut unless
confinement (Section 4.6.4) permits it.

#### 4.6.3. Web search

**4.6.3.1** A grant whose `online` is `ALL` MUST switch the harness's own web search on, and one
whose `online` is `NONE` MUST switch it off, on every harness that can be told.

**4.6.3.2** `cursor-agent`, `mcode`, `omp`, `pi` and every ACP harness cannot be told, and on them
hmz MUST say nothing of web search.

**4.6.3.3** Switching web search off MUST NOT be read as cutting the network; only confinement
(Section 4.6.4) cuts it.

#### 4.6.4. Confinement

**4.6.4.1** hmz MUST confine every harness except `litellm`, and every process the harness starts,
to the grant of its role.

**4.6.4.2** Confinement MUST permit reading what any program needs to start (system programs,
libraries, certificates and name-resolution files), and writing the device files, the harness's own
configuration and sign-in files, the agent's session records, and a temporary directory of the
agent's own.

**4.6.4.3** A `local` of `ALL` MUST also permit writing `/tmp`, `/var/tmp` and the directory
`TMPDIR` names.

**4.6.4.4** A `user` of `ALL` MUST permit writing whatever the user's file permissions permit, and
for the root user MUST permit writing the home directory, the temporary directories and
`/run/user/0`.

**4.6.4.5** A grant whose `online` is `NONE` MUST cut the network for the harness and its processes,
except connections to the hosts the harness and its account need to reach its model and its sign-in,
which MUST pass through a proxy on loopback.

**4.6.4.6** On Linux, confinement MUST require Landlock (kernel 5.13 or later, enabled), and
confinement that cuts the network MUST additionally require Landlock ABI 4 (kernel 6.7 or later) and
seccomp user notification; where either is absent, the session MUST be refused with
`HarnessSandboxed` naming the requirement.

**4.6.4.7** On macOS, confinement MUST use the Seatbelt sandbox, and where hmz itself runs inside a
sandbox that prevents applying one, the session MUST be refused with `HarnessSandboxed`.

**4.6.4.8** A grant whose `online` is `NONE` MUST be refused with `HarnessSandboxed` for
`cursor-agent` and for `mcode`.

> Informative: the web search of these two harnesses runs on their vendors' servers through the
> same hosts as their models.

**4.6.4.9** A grant whose `online` is `NONE` MUST be refused with `HarnessSandboxed` for an ACP
harness that declares no hosts, and the message MUST name what to declare.

**4.6.4.10** hmz MUST NOT rely on a rung's own sandbox inside a harness to hold the grant;
confinement MUST hold the grant whatever the harness enforces.

**4.6.4.11** A turn kept off a host by confinement MUST fail with the fault class `fenced`.

### 4.7. Sessions and turns

#### 4.7.1. Sessions

**4.7.1.1** A session MUST take one turn at a time; turns asked of one session concurrently MUST run
one after the other.

**4.7.1.2** A session MUST open its conversation with the harness on its first turn and MUST resume
that conversation by the harness's own session id on every later turn.

**4.7.1.3** A session whose first turn failed MUST remain unopened, and its next turn MUST open a
new conversation.

**4.7.1.4** Every turn MUST end in exactly one answer or exactly one failure.

**4.7.1.5** A session MUST run every turn in the directory it was opened in, and a directory that
does not exist MUST be refused before the turn.

**4.7.1.6** Where hmz restarts a harness process between turns of one session, the session MUST
continue the same conversation by its id, except on `dsh`, which cannot resume: a `dsh` session that
has taken a turn and would need a new process MUST refuse that turn with `HarnessUnrecoverable`.

#### 4.7.2. Schemas

**4.7.2.1** A turn asked for an answer in a schema MUST answer with an object of that schema or fail
with `OutputSchemaError`.

**4.7.2.2** `claude`, `agy`, `grok`, `qwen`, `mcode`, `codex` and `litellm` MUST be held to the
schema by the harness itself; every other harness MUST be asked for the schema in the prompt and its
answer validated afterwards.

**4.7.2.3** The schema MUST NOT appear in what hooks and watchers are shown of the prompt.

#### 4.7.3. Forks

**4.7.3.1** The following harnesses MUST fork a conversation: `claude`, `codex`, `kimi`, `grok`,
`opencode`, `mimo`, `pi`, `omp`, `qwen`, and an ACP harness that advertises forking.

**4.7.3.2** `claude`, `codex` and `kimi` MUST additionally fork a conversation into another
directory of the same machine.

**4.7.3.3** Forking on `agy`, `cursor-agent`, `dsh`, `mcode`, `litellm` and an ACP harness that does
not advertise it MUST be refused with `UnsupportedOperation`.

**4.7.3.4** A fork MUST carry the conversation's history as of the fork, its effort, its skills and
its fake tools, and MUST have a session id of its own.

**4.7.3.5** Forking a session that has not taken a turn MUST be refused.

**4.7.3.6** A fork onto another machine MUST be refused with `UnsupportedOperation`.

#### 4.7.4. Interrupting

**4.7.4.1** Interrupting a turn MUST end that turn and every process it started, and MUST leave the
conversation able to take the next turn.

**4.7.4.2** An interrupted turn MUST still end in exactly one answer, carrying what the agent had
said before the interruption.

**4.7.4.3** An interrupted turn MUST NOT be retried.

#### 4.7.5. Steering

**4.7.5.1** Steering MUST put the user's or flow's words into the turn already running, and MUST NOT
queue them as another turn.

**4.7.5.2** `claude`, `codex`, `kimi`, `pi` and `omp` MUST serve steering; every other harness MUST
refuse it with `UnsupportedOperation`.

**4.7.5.3** Steering a session with no turn running MUST be refused with `SessionError`, except on
`claude`, `pi` and `omp` while their process is up.

**4.7.5.4** hmz MUST report when steered words reach the model.

#### 4.7.6. Goals

**4.7.6.1** A turn whose prompt is `/goal <objective>` MUST run the harness's own goal feature,
continuing until the agent judges the objective met, and MUST answer with the last turn's answer.

**4.7.6.2** `claude`, `codex`, `kimi` and `dsh` MUST serve goals; every other harness MUST refuse
`/goal` and MUST NOT emulate a goal in the prompt.

**4.7.6.3** A per-turn budget and an interruption MUST NOT end a goal; stopping the agent MUST end
it.

#### 4.7.7. Loops

**4.7.7.1** A prompt `/loop <interval> <task>` MUST be passed to `claude` unchanged, and `claude`
alone MUST serve it.

#### 4.7.8. Per-turn budgets

**4.7.8.1** A per-turn budget MUST cap the output tokens and the wall-clock seconds of one turn, and
a cap of zero MUST cap nothing.

**4.7.8.2** A cap of seconds MUST take effect whether or not the harness is producing output.

**4.7.8.3** On `agy`, `grok`, `qwen` and every ACP harness, which report usage only when a turn
ends, a cap of output tokens MUST NOT take effect mid-turn.

**4.7.8.4** A turn ended by its budget MUST keep its changes and MUST NOT be retried.

**4.7.8.5** A budget's cut-off MUST prevail over a stop hook that would send the agent on.

### 4.8. Usage and cost

#### 4.8.1. Token usage

**4.8.1.1** hmz MUST count the tokens of every turn in the kinds `input`, `output`, `cache_read`,
`cache_write` and `reasoning`, omitting a kind the harness does not report.

**4.8.1.2** An ACP harness reports no usage, and hmz MUST count none for it.

**4.8.1.3** hmz MUST count each model request once, including where the harness's log repeats one
request's usage across several records.

**4.8.1.4** Where hmz reads usage both from the harness's answers and from its logs, the figure
shown per model MUST be the higher of the two and MUST NOT be their sum.

**4.8.1.5** Usage of a conversation carried on from an earlier epic or forked from another session
MUST count only records made after the current epic opened that session.

#### 4.8.2. Prices and cost

**4.8.2.1** hmz MUST price usage per model and per token kind from the price list at
`https://openllmprices.com/data/prices.json`, cached on this machine and refreshed when older than
24 hours.

**4.8.2.2** The environment variable `HUMANIZE_PRICES` MUST, where set to a URL or a path, replace
that source, and MUST, where set to `off`, `0`, `no`, `none` or the empty string, disable fetching.

**4.8.2.3** Pricing MUST read only the cached list and MUST NOT wait on the network.

**4.8.2.4** A model the price list does not name exactly MUST be priced as unknown and MUST NOT be
priced at zero.

**4.8.2.5** A cost that includes any unpriced model MUST be shown as a lower bound.

**4.8.2.6** A failed fetch MUST leave the cached list unchanged.

**4.8.2.7** A price list that gives any model a price that is not a finite number (`NaN`, an
infinity, or a number too large to be finite) MUST be refused: fetched, it MUST NOT be cached and
MUST count as a failed fetch for Section 4.8.2.6; and while the list last fetched from the source in
force, or the cached list, is such a list, pricing any model MUST fail rather than answer.

### 4.9. Hooks

#### 4.9.1. Moments

**4.9.1.1** Every harness except the human agent MUST serve the hooks session start, prompt submit,
pre-tool-use, notification, stop and session end.

**4.9.1.2** On `litellm`, which reaches for no tool, the pre-tool-use hook MUST never fire.

**4.9.1.3** The permission-request hook MUST be served by `claude`, `codex`, `kimi` and `grok`, and
by no other harness.

**4.9.1.4** The subagent start and subagent stop hooks MUST be served by `claude`, `codex`,
`cursor-agent` and `mcode`, and by no other harness.

**4.9.1.5** The ask-user hook MUST be served by `claude`, `codex`, `kimi`, `pi` and `omp`, and by no
other harness.

**4.9.1.6** The human agent MUST serve no hook.

**4.9.1.7** Hanging a hook on a moment the harness does not serve MUST be refused before the agent's
first turn.

#### 4.9.2. Pre-tool-use

**4.9.2.1** On `claude` and `qwen`, a pre-tool-use hook that refuses MUST prevent the tool from
running.

**4.9.2.2** On every other harness, the pre-tool-use hook MUST be told of the tool after the harness
announced it, and its refusal MUST NOT prevent the tool from running.

**4.9.2.3** On `kimi`, `pi`, `qwen` and `mimo`, while a pre-tool-use hook is hung, hmz MUST also
report the programs the harness starts, the files it reads and writes, and the connections it opens,
as additional pre-tool-use occasions, on which a hook's refusal MUST have no effect.

**4.9.2.4** The reports of Section 4.9.2.3 MUST NOT be made for a harness running on a machine other
than this machine.

#### 4.9.3. Permission requests

**4.9.3.1** A permission request that no hook refuses MUST be granted, except on `claude` at
`read-only`, on `codex` and `grok` with no rung said, and on `kimi` at `read-only` or with no rung
said, where it MUST be denied.

**4.9.3.2** A hook MUST be able to turn a grant into a denial and MUST NOT be able to turn a denial
into a grant.

**4.9.3.3** While a permission-request hook is hung, `claude` at `bypass` MUST run in its manual
permission mode, so that every tool that changes something reaches the hook, and `codex` MUST run
with the approval policy `untrusted`; each MUST take effect from the session's next turn.

#### 4.9.4. Questions

**4.9.4.1** Where the agent stops mid-turn to ask its user a question, hmz MUST deliver the question
to the role's ask-user hook where one is hung.

**4.9.4.2** Where no ask-user hook is hung, hmz MUST tell the harness that nobody answered.

**4.9.4.3** While an ask-user hook is hung on `codex`, Codex MUST be launched able to ask its user
outside plan mode.

#### 4.9.5. Timing

**4.9.5.1** A hook other than the ask-user hook MUST be waited for at most 900 seconds, after which
the moment MUST proceed as though no hook were hung.

**4.9.5.2** The ask-user hook MUST be waited for without limit.

**4.9.5.3** A hook that raises MUST be treated as having said nothing.

### 4.10. Fake tools and fake command lines

#### 4.10.1. Fake tools

**4.10.1.1** Fake tools MUST be offered only to `claude`, `codex`, `qwen`, `opencode`, `mimo`,
`agy`, `grok`, `pi`, `omp`, `dsh` and ACP harnesses, and offering them to any other harness MUST be
refused.

**4.10.1.2** hmz MUST serve fake tools through the hmz tool server, a managed item at the user level
(Section 4.5), and MUST NOT require the flow to run a server.

**4.10.1.3** A fake tool's return value MUST reach the agent as text, and a fake tool that raises
MUST reach the agent as a failed tool call.

**4.10.1.4** On `grok`, a turn that `grok` can take only in print mode (a schema, the first turn of
a fork, web search off, or a rung that withholds tools) MUST be refused with `HarnessUnrecoverable`
while any fake tool is offered.

**4.10.1.5** Fake tools MUST be refused to a harness running on a machine other than this machine,
except `omp`.

#### 4.10.2. Fake command lines

**4.10.2.1** Fake command lines MUST be put first on the `PATH` of every process of an agent whose
harness has a shell, which is every harness except `litellm` and the human agent, and MUST be
refused to those two.

**4.10.2.2** A fake command line MUST answer `--help` and `<command> --help` with its help on
standard output and exit status 0.

**4.10.2.3** A fake command line given arguments its command's options refuse MUST print the usage
and the error on standard error and exit with status 2.

**4.10.2.4** A fake command whose handler returns text MUST print it followed by a newline and exit
with status 0; one that returns nothing MUST print nothing and exit with status 0; one that returns
any other value MUST print it as indented JSON and exit with status 0.

**4.10.2.5** A fake command whose handler raises `SystemExit(n)` MUST exit with `n`; one whose
handler raises any other exception MUST print `NAME: <type>: <message>` on standard error and exit
with status 1.

**4.10.2.6** A fake command line run after the flow withdrew it MUST print `NAME: command not found`
on standard error and exit with status 127.

**4.10.2.7** Fake command lines MUST be refused to a harness running on a machine other than this
machine.

**4.10.2.8** On `codex`, a fake command line the agent's config names as unsandboxed MUST run
outside Codex's sandbox, by an execpolicy rule `prefix_rule(pattern=["<name>"], decision="allow")`
in `rules/hmz.rules` of its virtual config home, beside links to the user's own rule files; the rule
MUST be written only for a name the agent shelves, and every other command MUST stay in the sandbox
the rung puts it in.

### 4.11. Failures, retries and fallbacks

#### 4.11.1. Fault classes

**4.11.1.1** hmz MUST classify a failed turn by what the harness wrote on its output streams, and
for `agy` also by its log, reading the harness's own signs first and the shared signs after, in the
order of the following table, the first match deciding:

| Order | Fault class | Signs |
| --- | --- | --- |
| 1 | `unmirrored` | hmz could not keep this machine's copy of the work at its path |
| 2 | `fenced` | confinement kept the harness off a host |
| 3 | `contended` | a local store is locked; a refreshing sign-in is in use the other way |
| 4 | `spent` | a quota or balance is used up |
| 5 | `throttled` | status 429 or 529, rate limit, resource exhausted, overloaded, usage limit |
| 6 | `sandboxed` | the harness could not start its own sandbox |
| 7 | `unlisted` | the account is not entitled to the model |
| 8 | `refused` | status 401 or 403, an invalid, expired or revoked credential, not signed in |
| 9 | `retired` | status 404, model not found, unknown model |
| 10 | `killed` | a signal, out of memory, a segmentation fault |
| 11 | `dropped` | a connection reset or refused, a broken pipe, status 502, 503 or 504, a timeout |

**4.11.1.2** A harness program that exits with status 126 or 127 MUST be classified `missing`.

**4.11.1.3** On `codex`, a response stream that broke before completion, reported as `stream
disconnected before completion` or `responseStreamDisconnected`, MUST be classified `dropped`,
unless the same output carries a sign of a class earlier in Section 4.11.1.1, which MUST prevail.

**4.11.1.4** A Codex stream that disconnected because of a content filter MUST NOT be classified
`dropped`.

**4.11.1.5** A turn that no retry can change (a context window exceeded, a session id the harness
will not resume, a budget cut-off configured to fail) MUST fail with `HarnessUnrecoverable` and MUST
NOT be retried or carried to a stand-in.

#### 4.11.2. What the flow sees

**4.11.2.1** A turn that fails after its retries and fallbacks are exhausted MUST raise in the flow
the error the following table names for its fault class:

| Fault class | Error |
| --- | --- |
| `contended` | `HarnessContended` |
| `spent`, `throttled` | `HarnessThrottled` |
| `refused` | `HarnessRefused` |
| `unlisted`, `retired` | `ModelUnavailable` |
| `missing` | `HarnessNotInstalled` for exit status 127, `HarnessMissing` otherwise |
| `sandboxed` | `HarnessSandboxed` |
| `killed` | `HarnessKilled` |
| `dropped` | `HarnessDropped` |
| `fenced`, `unmirrored`, unclassified | `HarnessUnrecoverable` |

**4.11.2.2** The error's message MUST carry what the harness said and, for a classified failure, the
fault class and what the user can do about it.

#### 4.11.3. Retries at one place

**4.11.3.1** A failed turn MUST first be retried at its own place, in the same session, before it is
carried to a stand-in.

**4.11.3.2** The number of retries at a place MUST be the larger of the place's configured retries
and the floor the fault class sets in the following table, except that a fault class marked "none"
MUST receive no retry whatever the place configures:

| Fault class | Floor | Shortest wait | Harness process restarted |
| --- | --- | --- | --- |
| `throttled`, `spent` | 1 | 30 seconds | no |
| `contended` | 3 | 1 second, constant | no |
| `dropped` | 1 | the place's | yes |
| `killed` | 1 | 1 second, constant | yes |
| `refused`, `unlisted`, `retired` | none | — | — |
| `missing`, `sandboxed`, `unmirrored`, `fenced` | none | — | — |
| unclassified | 0 | the place's | no |

**4.11.3.3** A place with no configured retries MUST have zero configured retries.

**4.11.3.4** The wait before each retry MUST be the longest of the place's policy wait, the fault
class's own wait and the fault class's shortest wait, each policy wait capped at 60 seconds.

**4.11.3.5** A place's retry policy MUST be one of `none`, `constant`, `linear`, `exponential`,
`exponential-jitter` and `fibonacci`, with a base of 1 second, and MUST be `exponential-jitter`
where the place names none.

**4.11.3.6** Where a place configures a timeout, a retry whose wait would end after that timeout,
counted from the turn's first attempt, MUST NOT be taken.

**4.11.3.7** A retry of a fault class whose harness process the table of Section 4.11.3.2 marks as
restarted MUST end the harness process and resume the
same conversation by its id in a new process.

**4.11.3.8** hmz MUST report each retry, with its fault class, wait and attempt number, as a notice
to the flow's watchers, and on standard error where nothing watches.

#### 4.11.4. Fallback chains

**4.11.4.1** Once a place has no retries left, the turn MUST be taken at the next place of the
fallback chain configured for the original place, in a new session, by a stand-in configured as the
original agent was (effort, grant, skills, fake tools), and its answer MUST be returned through the
original session.

**4.11.4.2** A place with no configured chain MUST have none, and nothing MUST be carried to a
stand-in by default.

**4.11.4.3** A stand-in MUST be retried as its own place's retries state, and MUST carry on along
the chain it was reached by and MUST NOT read a chain of its own place.

**4.11.4.4** A chain MUST NOT contain its own place, and MUST NOT contain one place twice.

**4.11.4.5** An account MUST NOT name another account to carry on under; another account of the same
harness MUST be reached only as a place on a chain.

**4.11.4.6** A setting that measured the original model MUST be dropped when a stand-in runs another
model, and a setting the stand-in's harness cannot express MUST make that place no stand-in.

**4.11.4.7** A stopped agent MUST NOT be carried to a stand-in.

**4.11.4.8** Stand-ins MUST spend from the same epic budget as the original agent.

### 4.12. Watchdog

#### 4.12.1. Silence

**4.12.1.1** hmz MUST watch every turn for silence, restarting the watchdog window whenever the
harness produces any output.

**4.12.1.2** The watchdog window MUST be 900 seconds, and 360 seconds for `dsh`.

**4.12.1.3** The environment variable `HUMANIZE_WATCHDOG` MUST, where set to a positive number of
seconds, replace the window, MUST, where set to zero or less, disable the watchdog, and MUST be
ignored where it is not a number.

**4.12.1.4** The watchdog MUST be paused while the turn waits on a person: a permission request, a
question, or a hook that pauses.

**4.12.1.5** When a window expires, hmz MUST grant a harness process or descendant visibly consuming
CPU up to 4 further windows, and MUST grant none to a process that is suspended or defunct.

**4.12.1.6** When the granted windows are exhausted, hmz MUST, in order: interrupt the turn; then
end the harness process and its descendants, saying first where that ends other turns sharing the
process; then kill what remains.

**4.12.1.7** hmz MUST report each step of Section 4.12.1.6 as a notice naming the harness.

**4.12.1.8** A turn ended by the watchdog MUST fail as a classified failure is, and MUST be retried
as Section 4.11.3 states, in the same conversation.

### 4.13. LiteLLM

#### 4.13.1. The `litellm` harness

**4.13.1.1** A turn of `litellm` MUST be one streamed chat completion over the session's history and
the prompt, made from this machine, with no tool, file system access or hook of its own.

**4.13.1.2** A `litellm` turn MUST take no env, and a turn given one MUST be refused with
`UnsupportedOperation`.

**4.13.1.3** A `litellm` agent with no account MUST read its credentials from this process's
environment; one with an account MUST be given the account's credentials on the call.

**4.13.1.4** A parameter the provider does not accept, an effort among them, MUST be dropped from
the call and MUST NOT fail the turn.

**4.13.1.5** A context window exceeded MUST fail with `HarnessUnrecoverable`.

#### 4.13.2. The gateway

**4.13.2.1** Where LiteLLM and its proxy are installed, hmz MUST offer every harness that supports
it the accounts `litellm` has a way in for, through a gateway, as Section 5.6.4 states.

**4.13.2.2** hmz MUST start the gateway on this machine's loopback interface the first time a turn
needs it, one per agent, and MUST start another for another account or once it has exited.

**4.13.2.3** The harness MUST be given the gateway's URL and the gateway's own key, and MUST NOT be
given any of the account's variables.

**4.13.2.4** The gateway's configuration and key MUST be kept in a file only the user can read, MUST
NOT appear on any command line, and MUST be removed with the gateway.

**4.13.2.5** hmz MUST stop the gateway, and every process it started, when the agent stops.

**4.13.2.6** A harness running on a machine other than this machine MUST be refused an account a
gateway holds, where the agent is configured.

**4.13.2.7** A failure to start the gateway MUST report the proxy's last output with every secret
removed.

### 4.14. ACP harnesses

#### 4.14.1. Adding and driving

**4.14.1.1** The user MUST be able to add as a harness any command that speaks the Agent Client
Protocol, under the name of the program it runs, and hmz MUST record it under `clis` in
`settings.yaml`, as Section 3 of [FILES] states.

**4.14.1.2** hmz MUST refuse to add a command whose program is a built-in harness under any alias, a
command that is empty, and a name other than the program's own.

**4.14.1.3** An added harness MUST be available in every workspace from the next prompt.

**4.14.1.4** hmz MUST say no model, effort or mode to an ACP harness.

**4.14.1.5** hmz MUST grant every permission request an ACP harness makes, subject to confinement.

**4.14.1.6** An ACP harness MUST NOT be steered, MUST serve no goal, and MUST report no usage.

**4.14.1.7** An ACP harness MUST continue a conversation by whichever of resuming and loading it
advertises, and MUST fork only where it advertises forking.

**4.14.1.8** The hosts an ACP harness declares MUST be reachable under a grant whose `online` is
`NONE`, and the state paths it declares MUST be writable whatever the grant's `user` scope.

### 4.15. The human agent

#### 4.15.1. Answers

**4.15.1.1** The human agent MUST answer each turn with what the user types at the prompt.

**4.15.1.2** The human agent MUST run no model, MUST spend nothing, and MUST be outside every
budget.

**4.15.1.3** Where a turn of the human agent asks for a schema, hmz MUST ask the user one question
per field, offering a field's literal values or `yes` and `no` for a boolean as options, and
offering `-` to take a field's default.

**4.15.1.4** A value the schema refuses MUST be asked again a bounded number of times.

**4.15.1.5** Where nobody is at the prompt, the human agent MUST answer with nothing rather than
leave a flow waiting.

## 5. Accounts

### 5.1. Scope

This section governs **accounts**: named sets of credentials for one harness kind, kept by
**hmz** apart from the harness's own sign-in, so that two agents of one harness can run as two
accounts at once. It states how an account is named, stored, made, signed in and removed, which ways
in each harness kind offers, what a turn under an account is launched with, which machine's
credentials a harness reads, how a sign-in that refreshes itself is protected, what happens when a
credential is expired or refused, how an account's model catalogue is kept, and how one account
serves several harness kinds.

Out of scope:

- The harness kinds, agent specs, retries and fallback chains: Section 4.
- The LiteLLM gateway's lifecycle: Section 4.13.2.
- The layout of `<home>/providers/` and of the machine cache as files: Section 4 of [FILES] and
  Section 7 of [FILES].
- Where a harness runs relative to its env: Section 6.
- The account pages of the terminal and web frontends: [TUI] and Section 3 of [WEB].

### 5.2. Terminology

**5.2.1** **Account name**: a name of one or more letters, digits, dots, dashes and underscores,
starting with a letter or a digit.

**5.2.2** **Harness machine's own sign-in**: for each harness kind, the harness as the user has
signed it in on the harness machine, under no account and with the empty account name.

**5.2.3** **Way in**: one kind of account a harness kind offers, defined by the command it runs, the
variables it asks for, the variables it sets, and the arguments it appends to every turn.

**5.2.4** **Account variable**: a variable a harness reads an account, a credential or a model
endpoint from: every variable any way in of that harness kind asks for or sets, every other name by
which the harness reads the same credential (Section 5.6.1.4), and every other variable that harness
reads its sign-in or endpoint from.

**5.2.5** **Credential file**: a file the harness's own login writes its credentials to (Section
5.6.2.1).

**5.2.6** **Refreshing sign-in**: a credential file holding a refresh token that the vendor replaces
on each refresh and treats as stolen if presented again after replacement.

**5.2.7** **Gateway account**: an account that points a harness at an endpoint, other than the
vendor's own, that speaks that harness's protocol.

**5.2.8** **Routed account**: an account of a harness kind whose turns pass through a gateway, as
Section 4.13.2 defines it.

**5.2.9** **Model catalogue**: the list of models an account runs and the efforts each takes.

### 5.3. Identity

#### 5.3.1. Naming

**5.3.1.1** An account MUST be identified by its harness kind and its account name, written
`<cli>/<name>`.

**5.3.1.2** hmz MUST accept every alias of a harness kind where an account is named, and MUST record
the account under the kind's name.

**5.3.1.3** hmz MUST refuse a name given for an account that is not an account name per Section
5.2.1, wherever that name is given, with a message stating the permitted characters.

**5.3.1.4** hmz MUST refuse an account of a harness kind that is neither built in nor added.

**5.3.1.5** Accounts MUST be available for every built-in harness kind and for every ACP harness.

#### 5.3.2. Choosing an account

**5.3.2.1** An agent MUST run as the account its agent spec names after `@`, and as the harness
machine's own sign-in where its agent spec names none, except as Section 5.7.1.2 states for harness
location standalone.

**5.3.2.2** An agent spec naming an account that does not exist MUST be refused before the epic
starts where it is given to `-a`, and otherwise before the agent's first turn, with a message naming
the agent, the harness kind and the account.

**5.3.2.3** hmz MUST NOT fall back to the harness machine's own sign-in for an agent whose account
does not exist.

#### 5.3.3. The harness machine's own sign-in

**5.3.3.1** The harness machine's own sign-in MUST be offered for every harness kind, and MUST NOT
be listed among the accounts hmz made.

**5.3.3.2** hmz MUST hold no credentials for the harness machine's own sign-in, and MUST NOT make,
sign in, change or remove it.

**5.3.3.3** A turn under the harness machine's own sign-in MUST run with its environment as hmz
found it, with no account variable added or removed and no credential file substituted.

### 5.4. Storage

#### 5.4.1. Layout

**5.4.1.1** Each account MUST be one directory `<home>/providers/<cli>/<name>/`, as Section 4 of
[FILES] states.

**5.4.1.2** The account's directory MUST hold a file `provider.json` stating the harness kind, the
account name, the way in it was made by, the variables a turn under it is given, the arguments
appended to its turns, and when it was made, and MUST hold the credential files the harness's own
login wrote under it.

**5.4.1.3** The directory, not the contents of `provider.json`, MUST decide which harness kind and
name an account has.

**5.4.1.4** A directory whose `provider.json` is missing or is not a JSON object MUST NOT be listed
as an account.

**5.4.1.5** A `fallback` key in `provider.json` MUST be ignored, and MUST be removed the next time
the account is written.

#### 5.4.2. Protection

**5.4.2.1** Every directory hmz creates on the way to an account's directory and to each credential
file's parent MUST be readable and writable only by the user from the moment it exists.

**5.4.2.2** Every file hmz writes into an account MUST be readable and writable only by the user
from the moment it exists, and MUST be replaced whole and MUST NOT be left partly written.

**5.4.2.3** Removing an account MUST delete its directory, credential files included, and its model
catalogue.

### 5.5. Ways in

#### 5.5.1. General

**5.5.1.1** hmz MUST offer, for each harness kind, its own ways in, in the order Section 5.5.2 lists
them; then, where LiteLLM's proxy can be started on this machine and the harness kind supports a
gateway, every way in of `litellm` as a routed way named `litellm-<way>`; then the way `env`, except
for `dsh` and `litellm`.

**5.5.1.2** Where the harness kind supports a gateway and LiteLLM is not installed, hmz MUST show,
in place of the routed ways, the command that installs it.

**5.5.1.3** A way in that runs a command MUST run the harness's own login command on the user's
terminal, with the account's credential files in place of the harness's own (Section 5.6.2), so that
what the login writes lands in the account.

**5.5.1.4** A way in that asks for a secret MUST NOT show the secret back, and a secret a login
command takes on standard input MUST be written to its standard input and MUST NOT appear on any
command line.

**5.5.1.5** A question with a default MUST take that default where the user leaves it blank.

**5.5.1.6** Making an account MUST replace the account's way, variables and arguments with those
given, and MUST leave credential files already in the account unchanged.

**5.5.1.7** A login command that exits non-zero MUST be reported with its exit status, and a login
command whose harness is not installed MUST be reported as not installed.

#### 5.5.2. Ways by harness kind

**5.5.2.1** `claude` MUST offer: `login` (runs `claude auth login`); `console` (runs `claude auth
login --console`); `token` (asks `CLAUDE_CODE_OAUTH_TOKEN`); `key` (asks `ANTHROPIC_API_KEY`); `wif`
(workload identity federation); `anthropic-gateway`, `bedrock-gateway` and `vertex-gateway` (a base
URL and `ANTHROPIC_AUTH_TOKEN`); `bedrock`, `bedrock-key`, `mantle`, `vertex`, `foundry`, `aws` and
`google-cloud` (the cloud's own credentials and region).

**5.5.2.2** `agy` MUST offer: `login` (runs `agy`); `key` (asks `GEMINI_API_KEY`); `gemini-gateway`
and `openai-gateway` (its enterprise LLM gateway's URL and key); and `adc` (asks
`GOOGLE_APPLICATION_CREDENTIALS`).

**5.5.2.3** `codex` MUST offer: `login` (runs `codex login`); `device` (runs `codex login
--device-auth`); `key` and `token` (run `codex login` with the key or token on standard input);
`workload` (workload identity federation); `openai-gateway` (asks `CODEX_PROVIDER_URL` and
`CODEX_PROVIDER_KEY`); `azure`; `bedrock`; `bedrock-key`; `ollama`; and `lmstudio`.

**5.5.2.4** `cursor-agent` MUST offer: `login` (runs `cursor-agent login`); `key` (asks
`CURSOR_API_KEY`); and `cursor-gateway` (asks `CURSOR_API_ENDPOINT` and `CURSOR_API_KEY`).

**5.5.2.5** `dsh` MUST offer: `key` (asks `DEEPSEEK_API_KEY`); and `openai-gateway`,
`anthropic-gateway` and `gemini-gateway` (ask `DEEPSEEK_BASE_URL` and `DEEPSEEK_API_KEY`).

**5.5.2.6** `litellm` MUST offer: `openai-key`, `anthropic-key`, `gemini-key`, `xai-key`,
`openrouter-key`, `deepseek-key`, `groq-key` and `mistral-key` (each the vendor's own key variable);
`openai-gateway` and `anthropic-gateway` (ask `LITELLM_GATEWAY_URL` and `LITELLM_GATEWAY_KEY`);
`bedrock`; `vertex`; and `azure`.

**5.5.2.7** `grok` MUST offer: `login` (runs `grok login`); `device` (runs `grok login
--device-auth`); `oidc`; `provider-command`; `key` (asks `XAI_API_KEY`); and `openai-gateway` and
`anthropic-gateway` (ask `GROK_XAI_API_BASE_URL` and `XAI_API_KEY`).

**5.5.2.8** `kimi` MUST offer: `login` (runs `kimi login` for the region asked); `kimi-key`; and
`openai-gateway`, `anthropic-gateway` and `gemini-gateway` (ask `KIMI_MODEL_BASE_URL`,
`KIMI_MODEL_API_KEY` and `KIMI_MODEL_NAME`).

**5.5.2.9** `mcode` MUST offer: `login` (runs `mcode login` for the region asked); `key` (runs
`mcode provider set-minimax-key`); and `openai-gateway` and `anthropic-gateway` (run `mcode provider
add` for the gateway asked).

**5.5.2.10** `mimo` MUST offer: `login` (runs `mimo auth login`); `key` (asks `XIAOMI_API_KEY`);
`anthropic-key`, `openai-key`, `gemini-key`, `xai-key`, `openrouter-key` and `deepseek-key`;
`openai-gateway`, `anthropic-gateway` and `gemini-gateway` (ask `MIMO_GATEWAY_URL`,
`MIMO_GATEWAY_KEY` and `MIMO_GATEWAY_MODEL`); `vertex`; `bedrock`; and `azure`.

**5.5.2.11** `omp` MUST offer: `anthropic-key`, `anthropic-token`, `openai-key`, `gemini-key`,
`xai-key`, `openrouter-key`, `deepseek-key`, `groq-key` and `mistral-key`; `bedrock`; and `vertex`.

**5.5.2.12** `omp` MUST offer no `login`.

**5.5.2.13** `opencode` MUST offer: `login` (runs `opencode auth login`); `wellknown`; `zen` (asks
`OPENCODE_API_KEY`); `anthropic-key`, `openai-key`, `gemini-key`, `xai-key`, `openrouter-key`,
`deepseek-key` and `mistral-key`; `openai-gateway`, `anthropic-gateway` and `gemini-gateway` (ask
`OPENCODE_GATEWAY_URL`, `OPENCODE_GATEWAY_KEY` and `OPENCODE_GATEWAY_MODEL`); `bedrock`; `vertex`;
and `azure`.

**5.5.2.14** `pi` MUST offer: `login` (runs `pi` for its `/login`); `anthropic-key`,
`anthropic-token`, `openai-key`, `gemini-key`, `xai-key`, `openrouter-key`, `deepseek-key`,
`groq-key` and `mistral-key`; `openai-gateway`, `anthropic-gateway` and `gemini-gateway` (ask
`PI_GATEWAY_URL`, `PI_GATEWAY_KEY` and `PI_GATEWAY_MODEL`); `bedrock`; `vertex`; and `azure`.

**5.5.2.15** `qwen` MUST offer: `coding-plan` and `token-plan` (ask `OPENAI_BASE_URL` and
`OPENAI_API_KEY`); `gemini-key`; `openai-gateway`; `anthropic-gateway`; `gemini-gateway`; `vertex`;
and `vertex-key`.

**5.5.2.16** `qwen` MUST offer no `login`.

**5.5.2.17** An ACP harness MUST offer only `env`.

> Informative: this document names, for each way, only the variables and commands given above. The
> full list of the variables each way asks for, their defaults and the arguments each appends is
> published in the provider reference of hmz's user documentation.

#### 5.5.3. The `env` way

**5.5.3.1** The `env` way MUST read `NAME=VALUE` lines, stripping surrounding whitespace, skipping
blank lines and lines starting with `#`, and permitting `=` within a value.

**5.5.3.2** A non-empty line with no `=`, or with an empty name, MUST be refused with a message
naming the line.

**5.5.3.3** The `env` way MUST keep every variable given, whatever its name.

### 5.6. A turn under an account

#### 5.6.1. Variables and arguments

**5.6.1.1** A turn under an account MUST run with the account's variables added to its environment.

**5.6.1.2** A turn under an account MUST run without every account variable of its harness kind that
the account does not set.

**5.6.1.3** A turn under an account MUST have the account's arguments appended to the harness's
command line.

**5.6.1.4** The following names MUST be treated as one credential each, so that setting any one
removes the others: `CLAUDE_CODE_OAUTH_TOKEN` and `ANTHROPIC_OAUTH_TOKEN`; `GEMINI_API_KEY` and
`GOOGLE_API_KEY`; `MOONSHOT_API_KEY` and `KIMI_API_KEY`; `OPENAI_BASE_URL` and `OPENAI_API_BASE`;
`XAI_API_KEY` and `GROK_CODE_XAI_API_KEY`.

**5.6.1.5** An account's variables MUST reach the harness as its environment and MUST NOT be written
on any command line.

**5.6.1.6** On `litellm`, hmz MUST pass the account to each model call of a turn under it.

**5.6.1.7** On `litellm`, hmz MUST NOT remove any variable from this process's environment for an
account.

#### 5.6.2. Credential files

**5.6.2.1** The credential files of each harness kind MUST be those Section 8.4.5 of [FILES] lists,
and an ACP harness MUST have none.

**5.6.2.2** A turn under an account MUST read and write the account's copy of each credential file
wherever the harness reads or writes its own, and MUST NOT read or write the harness's own.

**5.6.2.3** A credential file the harness writes during a turn under an account MUST be written to
the account, so that a refreshed credential persists.

**5.6.2.4** A credential path hmz cannot substitute MUST fail the harness's access to it, and MUST
NOT fall through to the harness's own file.

**5.6.2.5** A turn that needs credential files substituted on a machine where hmz cannot substitute
them MUST be refused rather than run with the harness's own credentials.

**5.6.2.6** A copy of a credential file that hmz makes for a harness to read MUST be used for reads
alone, as Section 8.4 of [FILES] states, and MUST be removed when the turn ends, whatever became of
it.

**5.6.2.7** A credential that is not a file (a system keychain entry) and a credential stored in the
same database as the harness's sessions MUST NOT be held by an account.

**5.6.2.8** Where a harness is launched with a virtual config home (Section 4.5.2), its credential
files MUST be the account's, or for the harness machine's own sign-in the user's real ones, and MUST
NOT be copies discarded at exit.

#### 5.6.3. Gateway accounts

**5.6.3.1** A gateway account MUST point the harness at its endpoint by the harness's own variables
or arguments, and hmz MUST NOT write the endpoint or its key into any configuration file of the
user.

**5.6.3.2** Where an endpoint's key is needed by a harness that reads it from configuration, the
configuration MUST name the variable holding the key, and the key itself MUST NOT be written to any
file or command line.

**5.6.3.3** A gateway account MUST run the models its endpoint serves, under the model ids the
endpoint lists.

#### 5.6.4. Routed accounts

**5.6.4.1** A routed way MUST ask for and set what `litellm`'s way of the same name asks for and
sets.

**5.6.4.2** A turn under a routed account MUST be launched as Section 4.13.2 states, with the
account's own variables withheld from the harness.

**5.6.4.3** The models of a routed account MUST be those behind the gateway, and MUST NOT be those
the harness lists of its own.

**5.6.4.4** `claude`, `agy`, `codex`, `dsh`, `grok`, `kimi`, `pi`, `qwen`, `opencode`, `mimo` and
`mcode` MUST support routed accounts.

**5.6.4.5** Every harness kind not listed in Section 5.6.4.4 MUST NOT offer routed accounts.

### 5.7. Which machine's credentials a harness reads

#### 5.7.1. The harness machine

**5.7.1.1** An agent with no account MUST run as the harness's own sign-in on the harness machine,
and hmz MUST NOT carry any sign-in of this machine to another machine for it.

**5.7.1.2** An agent with an account MUST run as that account wherever its harness runs, with the
account's variables and credential files made available to the harness on the harness machine for
each turn, except under harness location standalone, where the agent MUST run as the harness
machine's own sign-in (Section 6.5.3.3).

**5.7.1.3** Where a harness runs under harness location env, the account's credential files MUST be
placed there in a directory only the harness machine's user can enter, unreadable by anyone else
from the moment it exists, and MUST be removed when the turn ends, whatever became of it.

**5.7.1.4** Where a harness under harness location env has no way of reading credential files from a
location hmz names, a turn needing them MUST be refused.

**5.7.1.5** Commands the agent runs on an env machine other than the harness machine MUST NOT
receive the account's variables.

#### 5.7.2. Refreshing sign-ins

**5.7.2.1** hmz MUST treat a credential file holding `refresh_token`, `refreshToken` or a `refresh`
key as a refreshing sign-in.

**5.7.2.2** A refreshing sign-in MUST NOT be refreshed in two places independently.

**5.7.2.3** Turns whose harness runs on this machine MUST use a refreshing sign-in in place, and any
number of them MUST be permitted to do so at once.

**5.7.2.4** A turn whose harness runs under harness location env MUST be lent a copy of a refreshing
sign-in only while no other turn uses it, and the sign-in MUST NOT be used by any other turn until
the copy is returned.

**5.7.2.5** A turn that Section 5.7.2.4 keeps from a refreshing sign-in — a turn under harness
location env while another turn uses the sign-in, or any turn while a copy of it is lent — MUST be
refused at once with the fault class `contended`, and MUST NOT wait for the sign-in.

**5.7.2.6** When a lent turn ends, hmz MUST write the refreshed copy back over the account's file,
unless the account's file changed meanwhile, in which case hmz MUST say so and MUST NOT write over
it.

**5.7.2.7** Where the file system of an account's directory does not let hmz hold a refreshing
sign-in against other processes, hmz MUST log that it cannot hold the sign-in.

**5.7.2.8** Where Section 5.7.2.7 applies, hmz MUST run the turn without holding the sign-in.

### 5.8. Model catalogues

#### 5.8.1. Keeping and asking

**5.8.1.1** hmz MUST keep each account's model catalogue in this machine's cache, as Section 7 of
[FILES] states, and MUST NOT keep it in the home.

**5.8.1.2** The catalogue of the harness machine's own sign-in MUST be kept under a name no account
can take.

**5.8.1.3** hmz MUST ask for a catalogue when the user asks for it.

**5.8.1.4** A frontend MUST ask for an account's catalogue when the user picks an account whose
catalogue was never asked for.

**5.8.1.5** The terminal frontend MUST ask again at start-up, without blocking, for the catalogue of
the harness machine's own sign-in of each installed harness kind where that catalogue is missing or
stale.

**5.8.1.6** A catalogue asked for more than 7 days ago, or never asked for, MUST be stale.

**5.8.1.7** Where the account sets its harness's endpoint variable, the catalogue MUST be the
endpoint's model list, asked under the account's secret; hmz MUST follow a redirect of that request
only to the same host and MUST NOT follow one from `https` to `http`. Otherwise the catalogue MUST
be what the harness lists when asked under the account.

**5.8.1.8** An endpoint that does not answer MUST leave a catalogue already read from it in place.

**5.8.1.9** Reading a catalogue MUST read this machine's cache alone and MUST NOT contact the
network; a catalogue never asked for MUST read as empty and MUST NOT be guessed.

### 5.9. Expired and refused credentials

#### 5.9.1. Refusal

**5.9.1.1** A turn whose credential the provider refuses (expired, revoked, invalid, or not signed
in) MUST fail with the fault class `refused`, MUST NOT be retried at its place, and MUST be carried
to the next place of its fallback chain where one is configured, as Section 4.11 states.

**5.9.1.2** A turn that fails as `refused` after its fallback chain is exhausted MUST raise
`HarnessRefused` in the flow, whose message MUST say that the account needs signing in again.

**5.9.1.3** hmz MUST NOT attempt to sign an account in again without the user.

**5.9.1.4** hmz MUST let the user sign an account in again from the account pages of the frontends.

**5.9.1.5** Signing an account in again MUST run the account's way in again over the same account.

**5.9.1.6** A turn refused because a model is not the account's to run MUST fail with the fault
class `unlisted` and MUST NOT be reported as a credential failure.

### 5.10. One account, several harness kinds

#### 5.10.1. Copying

**5.10.1.1** hmz MUST offer to copy an account of one harness kind to every other harness kind that
reads every one of its variables under the same or an equivalent name (Section 5.6.1.4).

**5.10.1.2** An account whose credentials are files and not variables MUST NOT be offered for
copying.

**5.10.1.3** A copy MUST rename each variable to the name the target harness kind reads, MUST be
recorded under the first way in of the target that asks for and sets exactly those variables and
runs no command, else under `env`, and MUST replace an account of the same name there.

**5.10.1.4** Copying an account to a harness kind that cannot run as it MUST be refused, naming the
account and the harness kind.

### 5.11. Secrecy

#### 5.11.1. Secrets

**5.11.1.1** hmz MUST NOT print, display or log the value of any account variable; where an account
is shown, hmz MUST show its harness kind, its name, its way in and the names of its variables.

**5.11.1.2** hmz MUST NOT send any account's credentials to a frontend page.

**5.11.1.3** A turn under one account MUST NOT read or write the credentials of another account.

## 6. Placements

### 6.1. Scope

This section specifies where the parts of a **session** run once the **env** it works in is known:
the two settings that say so, the **env location** and the **harness location**; how **hmz** settles
them for each session; what runs on which **machine** under each; the semantics and consistency
guarantees of a **mirror**; the rule for **workspace** configuration that makes a **harness** run
programs when the harness machine is not the env machine; which sessions may be kept and carried on;
and the target spellings by which a machine is named.

Out of scope:

- What each env kind is, how it is started, sized, labelled and cleaned up: Section 7.
- The settings keys that hold a runtime's harness setting and fields: Section 3.3 of [FILES].
- The per-harness list of configuration files and keys, accounts and fences of a harness: Section 4,
  Section 5.
- The files hmz writes on a target machine and under the **home**: Section 9 of [FILES], Section 4
  of [FILES].
- How a flow declares envs and opens sessions: Section 3 of [PYTHON].
- The `-e` command-line grammar: [CLI].

### 6.2. Terminology

**6.2.1** **Session directory**: the directory on the env machine in which a session is opened: the
env's workdir, or a directory under it that the session names.

**6.2.2** **Target**: a string that names an env machine and the way hmz reaches it, as Section 6.9
defines.

**6.2.3** **Serving half**: the program hmz starts on, or connects to on, a target to carry out the
file operations, commands and outbound connections that a harness elsewhere asks for.

**6.2.4** **Env location**: where a session's env machine is, as Section 6.3.1 defines: `local` or
`standalone`.

**6.2.5** **Harness location**: where a session's harness runs, as Section 6.3.1 defines: `local`,
`env` or `standalone`.

**6.2.6** **Harness runtime**: a runtime that a harness setting `<backend>:<name>` names, opened to
hold harnesses rather than to be worked in.

**6.2.7** **Harness setting**: the one value saved with a **runtime** that says where the harness of
a session whose env is on that runtime runs: `local`, `env`, or `<backend>:<name>`, where
`<backend>` is one of `ssh`, `docker`, `swarm`, `apple-container`, `slurm` and `<name>` names a
saved runtime of that backend.

**6.2.8** **Gating hook**: a hook hung on a flow agent at the `PreToolUse` or `PermissionRequest`
moment (Section 3 of [PYTHON]). A hook at the `AskUser` moment is not a gating hook.

**6.2.9** **Program-running configuration**: the files and keys that Section 4.5.5.1 lists for a
harness, found from the session directory.

**6.2.10** **Keep**: writing a session into a flow's state, which copies the session's conversation
(Section 3 of [PYTHON]).

**6.2.11** **Carry on**: opening a session whose first turn continues a kept conversation.

**6.2.12** **Fork-in-place harness**: a harness that can fork a conversation only in the directory
in which that conversation was held (Section 4).

**6.2.13** **Mirrored session**: a session whose harness location is `standalone`, or whose harness
location is `local` and env location `standalone`.

### 6.3. Env location and harness location

#### 6.3.1. Definition of each

**6.3.1.1** A session MUST have exactly one env location and exactly one harness location at any
time.

**6.3.1.2** A session MUST have env location **local** where its env machine is this machine, and
env location **standalone** otherwise. A session with env location local MUST have harness location
local, and hmz MUST NOT make a mirror for it.

**6.3.1.3** A session MUST have harness location **local** where its harness program runs on this
machine. Where its env location is standalone, the harness MUST work in a mirror on this machine.

**6.3.1.4** A session MUST have harness location **env** where its harness is the harness program
installed on its env machine, that machine is not this machine, and no harness runtime holds the
harness. hmz MUST NOT make a mirror for it.

**6.3.1.5** A session MUST have harness location **standalone** where its harness machine is the
machine of a harness runtime and is not this machine, whether or not it is the env machine. The
harness MUST work in a mirror on the harness machine.

**6.3.1.6** A session of a harness that starts no program of its own MUST have env location local.

> Informative: summary of Section 6.3.1 and Section 6.5.
>
> | Harness location / env location | local / local | local / standalone | env / standalone | standalone / either |
> | --- | --- | --- | --- | --- |
> | Harness program runs on | this machine | this machine | env machine | harness runtime |
> | Mirror | none | this machine | none | harness machine |
> | Commands the agent runs | this machine | env machine | env machine | env machine |
> | Harness's connections | this machine | this machine | env machine | harness machine |
> | Account used on | this machine | this machine | env machine | harness machine |

#### 6.3.2. Platform requirements

**6.3.2.1** A mirrored session MUST be refused at the start of its first turn, with an error that
names the platforms on which it can run, where its harness machine is not Linux on x86-64 or
aarch64.

**6.3.2.2** An env machine of a session with env location standalone MUST provide a POSIX `/bin/sh`
and a Python of version 3.12 or later. hmz MUST NOT require root, a compiler, a kernel module or an
installed package on that machine.

**6.3.2.3** A session with harness location env MUST require the harness program to be installed on
the env machine and found on the `PATH` of the login hmz reaches it as, without looking in any other
directory.

### 6.4. Settling the harness location

#### 6.4.1. General

**6.4.1.1** hmz MUST settle the harness location of a session when the session is opened, before its
harness is started.

**6.4.1.2** A session with env location standalone MUST have the harness location its harness
setting names: `local` gives harness location local, `env` gives harness location env, and
`<backend>:<name>` gives harness location standalone on the harness runtime it names.

**6.4.1.3** The harness setting that applies to a session MUST be that of the runtime its env was
actually opened on, which is the runtime the env fell back to where the env fell back (Section
7.11). A runtime saved without a harness setting, and an env on no saved runtime, MUST have the
harness setting `env`.

**6.4.1.4** The harness setting and the fallback list saved with a runtime MUST have no effect
where that runtime is opened as a harness runtime.

#### 6.4.2. Refusals

**6.4.2.1** Where the harness location that Section 6.4.1.2 gives cannot hold the harness, hmz MUST
refuse the session, and MUST NOT put the harness anywhere else.

**6.4.2.2** The harness setting `env` MUST be refused with `HarnessNotInstalled` where the env
machine has not got the harness program, with `HarnessSandboxed` where it cannot hold the session's
fence, with `HarnessUnrecoverable` where it cannot be asked either of those two questions, and with
`UnsupportedOperation` where a gating hook is hung on the session.

**6.4.2.3** A harness setting `<backend>:<name>` MUST be refused where that runtime is not saved,
cannot be opened or reached (`EnvUnavailable`, `EnvConnectionError`), has no share left to give
(`ResourceUnmet`), or where the role's permission fences anything at all (`HarnessSandboxed`).

**6.4.2.4** The message of a refusal MUST begin `<where>: <cli>'s harness cannot run where its
harness setting (<setting>) says: `, where `<where>` spells the env as `<backend>[@<provider>]`.

**6.4.2.5** hmz MUST ask an env machine whether it has the harness program over the same connection,
`PATH` and login that a turn with harness location env there uses, and MUST treat a machine that
does not answer within 300 seconds as one that cannot be asked.

**6.4.2.6** hmz MUST ask each machine each question of Section 6.4.2.2 at most once per role and
epic, and MUST ask whether a fence can be held only for a session held to a fence that is not open.

#### 6.4.3. Harness runtimes

**6.4.3.1** hmz MUST open a harness runtime at most once per epic and MUST share it among every role
whose harness setting names it.

**6.4.3.2** hmz MUST open a harness runtime as an env with no role and no resources asked, in the
runtime's saved workdir; without one, in the login's home for an `ssh` runtime, and in an empty
directory of this machine's for a `docker` runtime whose daemon is on this machine or for an
`apple-container` runtime. A runtime of any other kind saved without a workdir MUST be refused under
Section 6.4.2.3.

**6.4.3.3** hmz MUST start a container or swarm task opened as a harness runtime with the
`SYS_PTRACE` capability added.

**6.4.3.4** hmz MUST close every harness runtime it opened when the epic's envs are closed.

#### 6.4.4. Settling harness locations before the flow runs

**6.4.4.1** Before calling the flow, hmz MUST settle the harness location of every env of the epic
for every agent role, the workspace included, under the role's declared permission, opening and
probing every harness runtime that a harness setting so applied names.

**6.4.4.2** Where that settling refuses some role, hmz MUST refuse the epic before the flow is
called; `hmz exec` MUST print `hmz exec: error: <message>` and exit with status 2.

**6.4.4.3** A session opened later MUST be given the harness location settled under Section 6.4.4.1,
and MUST still be refused when it opens where Section 6.4.2 refuses it.

#### 6.4.5. Recording

**6.4.5.1** hmz MUST record with each session with env location standalone where its harness went:
`local`, `env`, or the `<backend>:<name>` of the harness runtime (Section 6 of [FILES]).

**6.4.5.2** hmz MUST record the empty string for a session with env location local.

### 6.5. What runs where

#### 6.5.1. Programs and files

**6.5.1.1** In a mirrored session, every program the agent starts MUST run on the env machine, in
the env machine's counterpart of the agent's working directory, except the programs of Section
6.5.1.3.

**6.5.1.2** In a mirrored session, every path the agent names inside the session's workspace on the
env machine MUST be answered from the env machine through the mirror, except the paths of Section
6.5.1.3; every path outside it MUST be answered by the harness machine.

**6.5.1.3** The following MUST stay on the harness machine: the harness program and the programs
beside it in its own package, the interpreter it is started by, the harness's state directories
(Section 4), hmz's own directories under the user's home, and the program that carries the flow's
callbacks and command lines.

**6.5.1.4** A program the agent starts on the env machine MUST behave as a local child: it MUST
receive the agent's descriptors, its exit status MUST reach the agent, and its parent MUST be
released as soon as it starts.

**6.5.1.5** A command the agent starts MUST NOT report a success it did not achieve, and a command
started by an agent that is not a shell MUST receive an empty standard input on the env machine.

**6.5.1.6** The common signals, `SIGINT` and `SIGTERM` among them, MUST travel both ways between the
agent and the commands it runs on the env machine.

**6.5.1.7** A program that hmz started for a session MUST NOT outlive the session, unless it left
the session while the session ran: a program whose parent, or one of its parent's parents below the
harness program, exited before the harness program did MAY outlive the session.

**6.5.1.8** Under harness location env the harness program, every program it starts and every file
it touches MUST be the env machine's.

#### 6.5.2. Network

**6.5.2.1** The harness's own network connections MUST leave from the harness machine.

**6.5.2.2** The network connections of a command the agent runs MUST leave from the machine the
command runs on.

#### 6.5.3. Accounts and credentials

**6.5.3.1** Under harness location local, the account's variables and credential files MUST be used
on this machine, and MUST NOT be passed to the commands the agent runs on the env machine.

**6.5.3.2** Under harness location env, the account's variables MUST be given to the harness program
as the turn's environment and MUST NOT be written on a command line, and the account's credential
files MUST be put in a directory on the env machine that only the target's own user can enter, for
the turn alone, as Section 5.7.1.3 states.

**6.5.3.3** Under harness location standalone, the harness MUST run as the harness machine's
sign-in; hmz MUST NOT send the account's variables or credential files to the harness machine.

#### 6.5.4. The flow's callbacks

**6.5.4.1** A turn with harness location env MUST be refused where it is offered the flow's own tool
callbacks or command lines, unless its harness receives each callback over the channel hmz drives it
through.

#### 6.5.5. Variables the agent is given

**6.5.5.1** Under env location standalone and harness location local or env, hmz MUST set `HUMANIZE`
to hmz's version, `HUMANIZE_TARGET` to the target, and `HUMANIZE_WORKSPACE` to the absolute
workspace path as the env machine names it, in the harness's environment.

#### 6.5.6. Fences

**6.5.6.1** Under harness location local and env location standalone, a fence MUST be held on both
machines: around the agent on the harness machine, and around every command the agent runs on the
env machine.

**6.5.6.2** Under harness location env, a fence MUST be held around the harness program on the env
machine.

**6.5.6.3** Under harness location standalone, a session held to any fence that is not open MUST be
refused with `HarnessSandboxed`.

### 6.6. Mirrors

#### 6.6.1. Location

**6.6.1.1** For an `ssh` env and harness location local, the mirror MUST be at the path of the env's
workdir on this machine.

**6.6.1.2** For a `docker`, `swarm`, `apple-container` or `slurm` env and harness location local,
the mirror MUST be under the home, in a directory of that container, service or job (Section 4 of
[FILES]), and MUST be removed when the env is closed.

**6.6.1.3** Under harness location standalone the mirror MUST be under the harness machine's own
cache directory, under a name derived from the workspace and the target, and MUST be kept between
turns (Section 9 of [FILES]).

#### 6.6.2. What the agent sees

**6.6.2.1** The agent of a mirrored session MUST start in the session directory, named as the env
machine names it.

**6.6.2.2** The agent of a mirrored session MUST see in the mirror the same names, contents, sizes,
modes and modification times at the same paths as the env machine has in the workspace.

**6.6.2.3** A failed operation on a path in the workspace MUST fail with the env machine's own
error.

**6.6.2.4** Every spelling the env machine has for a path MUST reach the same file.

**6.6.2.5** A file's contents MUST be fetched to the mirror no later than the first time the agent
opens it for reading.

#### 6.6.3. Propagation and consistency

**6.6.3.1** Creating, removing, renaming and linking a file, and changing its mode, MUST take effect
on the env machine before the agent's call returns; the env machine's error MUST be the agent's
error.

**6.6.3.2** A file that a turn modified MUST reach the env machine before any command runs there and
again when the turn ends.

**6.6.3.3** The mirror MUST follow the env machine's contents: a file the env machine lacks MUST be
removed from the mirror, except a file written in the mirror and not yet sent, which MUST be sent
before anything the env machine says of that file is applied.

**6.6.3.4** A change made in the workspace on the env machine by anything other than the agent's own
operations MUST become visible in the mirror no later than the completion of the next command the
turn runs on the env machine.

**6.6.3.5** Several turns working in one mirror at once MUST each see the files the others have
written, fetched, renamed and removed; a file one turn wrote MUST be sent by whichever turn next
sends, and MUST NOT be removed as one the env machine lacks.

**6.6.3.6** hmz MUST NOT refuse a turn because another turn is working in the same mirror.

**6.6.3.7** Where turns cannot share what they know of one mirror, each turn MUST work alone and hmz
MUST log `<mirror> cannot be shared with other turns working in it, which may then lose what this
one writes: <reason>`.

**6.6.3.8** Losing the connection to the env machine MUST NOT stop the agent: work that needs the
env machine MUST fail, files already in the mirror MUST stay readable, and the agent MUST exit with
its own status.

**6.6.3.9** A request to the env machine that receives no answer MUST be abandoned on the harness
machine.

> Informative: an abandoned request can still take effect on the env machine.

#### 6.6.4. Limits

**6.6.4.1** hmz MUST carry file contents, file modes and file modification times between the mirror
and the env machine; hmz MAY leave ownership, device nodes, extended attributes and a directory's
own mode and times uncarried.

**6.6.4.2** Where another writer changes on the env machine a file that a turn writes, hmz MAY leave
either change in place; Section 6.6.3 makes no guarantee for such a file.

**6.6.4.3** A 32-bit process started under the agent of a mirrored session MAY run against the
mirror with nothing it does carried to the env machine.

**6.6.4.4** Renaming or linking between a path in the workspace and a path kept on the harness
machine MUST fail.

#### 6.6.5. Guarding a mirror directory

**6.6.5.1** hmz MUST refuse, with `FileExistsError`, to use as a mirror a directory that holds files
and was never a mirror, and one that was last a mirror of another target, unless the caller forces
it.

**6.6.5.2** hmz MUST refuse, with an `OSError` whose message begins `cannot keep the local copy of
the work at <path>`, a mirror path that is not a directory or cannot be created.

### 6.7. Workspace configuration across machines

**6.7.1** A harness MUST read project-level configuration from the env's workspace, as found from
the session directory, in every harness location.

**6.7.2** A harness MUST read system-level and user-level configuration from the harness machine, in
every harness location.

**6.7.3** In a session that is not mirrored, hmz MUST let the harness honour program-running
configuration found in the env's workspace.

**6.7.4** In a mirrored session, opening a session, forking a session into a session directory, and
carrying on a kept conversation in a session directory MUST raise `UnsupportedOperation` where the
env's workspace holds program-running configuration that the harness would read as project-level.

**6.7.5** The error of Section 6.7.4 MUST name each file that holds such configuration and each key
in it, and MUST be raised before the harness is started.

**6.7.6** In a mirrored session, hmz MUST make the check of Section 6.7.4 again before every turn,
and MUST refuse the turn with `UnsupportedOperation` where it finds such configuration.

**6.7.7** A session with harness location standalone whose harness machine is the env machine MUST
be treated under Section 6.7.3 as a session that is not mirrored.

**6.7.8** Where the env machine cannot be reached for the check of Section 6.7.4, hmz MUST raise
`HarnessDropped`.

**6.7.9** The files and keys that count as program-running configuration for each harness MUST be
those listed in Section 4.5.5.

### 6.8. Moving, forking, keeping and carrying on

#### 6.8.1. Moving and forking

**6.8.1.1** A turn of a session working on another machine than the session's previous turn MUST be
refused with `UnsupportedOperation` on every harness, and the session MUST stay where it was.

**6.8.1.2** A turn of a session working in another workdir on the same machine MUST be refused with
`UnsupportedOperation`, except on a harness that forks into another directory, where the
conversation MUST continue as a fork of itself with a harness location settled for the new place
under Section 6.4.

**6.8.1.3** A fork of a session onto another machine MUST be refused with `UnsupportedOperation:
<cli> cannot fork a session onto another machine`.

#### 6.8.2. Keeping and carrying on

**6.8.2.1** A session with harness location local MUST be keepable, its conversation kept on this
machine.

**6.8.2.2** Keeping a session with harness location env or standalone MUST be refused with
`StateNotSerializable` before anything is written.

**6.8.2.3** Carrying on a kept conversation MUST be refused with `UnsupportedOperation` before the
harness is started where the turn's harness location is env or standalone.

**6.8.2.4** Carrying on a kept conversation on a fork-in-place harness MUST be refused with
`UnsupportedOperation` where the turn's harness location is local and env location standalone, in a
mirror at a path other than the workdir's own (Section 6.6.1.2).

**6.8.2.5** Carrying on a conversation kept by another harness MUST be refused with
`UnsupportedOperation`.

**6.8.2.6** The conversation of a session with harness location env or standalone MUST stay where
that session's harness keeps it, on its harness machine; hmz MUST copy what the session logs into
the epic as it goes and whole as it closes (Section 3).

### 6.9. Targets

#### 6.9.1. Spellings

**6.9.1.1** A target MUST be one of the spellings of this section; any other MUST be refused with
`ValueError` naming every accepted spelling.

**6.9.1.2** `local` and `local:DIR` MUST name this machine, the latter with `DIR` standing in for
the env machine's copy of the workspace.

**6.9.1.3** `ssh://[USER@]HOST[:PORT][?KEYWORD=VALUE&...]` MUST name a host reached with the system
`ssh`. Each option MUST reach every `ssh` to that host as `-o KEYWORD=VALUE`, and the option `F` as
`-F VALUE`, ahead of hmz's own options. `KEYWORD` MUST match `[A-Za-z][A-Za-z0-9]*`, and `VALUE`
MUST be non-empty and MUST NOT hold a newline, carriage return, NUL or `"`.

**6.9.1.4** Two `ssh://` targets at one host with different options MUST NOT share a connection.

**6.9.1.5** `docker://CONTAINER[?OPTIONS][@ENDPOINT]` MUST name a running container on the docker
daemon `ENDPOINT` names, docker's default when it names none or `local`. Every `docker` command for
a container on another endpoint MUST name that endpoint on its own command line and MUST run without
the variables that would send it elsewhere.

**6.9.1.6** The options of a `docker://` target MUST be only `user=UID[:GID]` (numeric, at most
once), `env=NAME=VALUE` (`NAME` matching `[A-Za-z_][A-Za-z0-9_]*`), and `exec=WORD` (non-empty),
`&`-separated and URL-quoted; any other MUST be refused with `ValueError`.

**6.9.1.7** Every command hmz runs in a `docker://` target's container MUST run as the `user` given,
with the `env` variables given, and under the `exec` words given in the order written, where the
words name a program that runs the command following them with the same streams and exits with its
status.

**6.9.1.8** A `docker://` target naming a `user` MUST keep hmz's files in that container in
directories named for that user, and MUST refuse one that is not a directory owned by that user
before anything is put in or run from it.

**6.9.1.9** `apple-container://CONTAINER` MUST name a running container of Apple's `container` on
this machine.

**6.9.1.10** `slurm://JOBID[?python=PATH]` MUST name the node of a running Slurm job of this user's.
Every command on it MUST be a step of that job sharing its allocation on its one node, MUST receive
nothing of this process's environment but `HOME` and `USER`, and MUST try the Python at `PATH`,
absolute or under `~/`, before any other.

**6.9.1.11** `tcp://HOST:PORT` MUST name a serving half listening at that address.

**6.9.1.12** `peer://TICKET@HOST:PORT` MUST name a serving half waiting at the broker at `HOST:PORT`
under `TICKET`.

**6.9.1.13** A `peer://` target given together with a harness machine other than this machine MUST
be refused with `ValueError`.

> Informative: hmz writes `peer://` targets itself when it puts a harness on a harness runtime;
> a user has no reason to write one.

#### 6.9.2. Endpoints

**6.9.2.1** A docker endpoint MUST be one of `local`, `unix:///PATH`, `tcp://HOST:PORT[?tls=DIR]`,
`ssh://[USER@]HOST[:PORT][?KEYWORD=VALUE&...]` and `context:NAME`; any other MUST be refused with
`ValueError` naming every accepted spelling.

**6.9.2.2** A daemon reached by `local` where `DOCKER_HOST` names no non-`unix://` host, or by
`unix:///PATH`, MUST be treated as on this machine; every other MUST be treated as on another.

### 6.10. Serving a target

**6.10.1** A serving half MUST refuse a request naming a path outside every directory it was told to
export, and every request before a handshake it accepted.

**6.10.2** A serving half MUST refuse, and close the connection to, a peer speaking another protocol
version or presenting a token other than the one it was started with.

**6.10.3** A serving half MUST end every process and tunnel it started when its connection ends.

**6.10.4** An export MUST bound only which paths a request names: a serving half MAY run any
command a request asks for, and MAY follow a symbolic link that leads out of the exported tree.

**6.10.5** A serving half listening on a non-loopback address without a token MUST be refused.

**6.10.6** A token MUST NOT appear on any command line; a process hmz starts with a token MUST be
given it as the name of a file that holds the token and that only the user can read.

**6.10.7** A broker ticket MUST be unguessable, MUST be the whole of what authenticates a peer at
the broker, and MUST pair only the two halves presenting it.

## 7. Environments

### 7.1. Scope

This section specifies the kinds of **env** hmz gives a **flow**'s env roles — `local`, `ssh`,
`docker`, `swarm`, `apple-container` and `slurm` — and the **runtimes** that name a machine an env
is put on: what each kind is, where its workdir is, how the resources a role declares are checked or
handed out, the names and labels hmz gives what it starts, the lifecycle of starting, closing and
cleaning up, falling back from one runtime to another, and the errors raised.

Out of scope:

- Where the **harness** of a session working in an env runs, mirrors, and target spellings: Section
  6.
- The settings keys under which runtimes are saved, and their types: Section 3.3 of [FILES].
- The `-e` command-line grammar and its parse errors: [CLI].
- The env protocol and mixins a flow writes against: Section 3 of [PYTHON].
- The files hmz writes under the **home** and on a target machine: Section 4 of [FILES], Section 9
  of [FILES].

### 7.2. Terminology

**7.2.1** **Kind**: one of `local`, `ssh`, `docker`, `swarm`, `apple-container`, `slurm`; the
backend an env is of.

**7.2.2** **Provider**: the name of the saved runtime an env is put on, or the empty string for an
env put on no saved runtime.

**7.2.3** **Default provider**: the machine an env of a kind with no provider is put on: this
machine for `local`; docker's default daemon on this machine for `docker`; the swarm this machine
manages for `swarm`; this machine's Apple containers for `apple-container`; the Slurm cluster this
machine submits to, with its defaults, for `slurm`. A label naming a default provider MUST name it
`local`.

**7.2.4** **Workdir**: the directory, as the env machine names it, that an env works in.

**7.2.5** **Declared resources**: the CPU count, memory, GPU count, GPU memory and image that an env
role declares through its mixins (Section 3 of [PYTHON]).

**7.2.6** **Brought-up env**: an env of kind `docker`, `swarm`, `apple-container` or `slurm`, for
which hmz starts a container, a service or a job of its own.

**7.2.7** **Allocation**: the share of a runtime's resources that a brought-up env holds.

**7.2.8** **Derived env**: an env made from another one by a flow — a subdirectory, a temporary
copy, a scratch directory or a worktree (Section 3 of [PYTHON]).

**7.2.9** **Owning process**: the hmz process that brought up a container, service or job.

**7.2.10** **Leftover**: a container, service or job whose labels name this user and this host and
whose owning process no longer exists.

### 7.3. Requirements common to every kind

#### 7.3.1. Opening and probing

**7.3.1.1** hmz MUST NOT connect to an env machine, start a container or service, or submit a job
when it makes an env; it MUST do so when it first probes the env.

**7.3.1.2** hmz MUST probe every env of an epic, and every harness runtime its harness settings name
(Section 6.4.4), before any agent starts.

**7.3.1.3** hmz MUST bring up every env of an epic concurrently; the first refusal MUST stop the
rest, and where several are refused hmz MUST raise the refusal of the role that comes first in
declaration order.

**7.3.1.4** A probe MUST learn the env machine's home, its CPU count, its memory, its GPUs (as
`CUDA_VISIBLE_DEVICES` narrows them) and the smallest GPU's memory, and whether `git` and `bash` are
on the `PATH`.

#### 7.3.2. Resources and capabilities

**7.3.2.1** For an env that is not a brought-up env, hmz MUST refuse a role whose declared resources
exceed what the probe found, with `ResourceUnmet: <flow>: '<role>' needs <n> <unit>, and the
environment given has <m>`, `<unit>` being `CPUs`, `bytes of memory`, `GPUs` or `bytes of memory per
GPU`.

**7.3.2.2** For a brought-up env, hmz MUST size or ask for the env by the declared resources as the
section of its kind says, and MUST refuse it with `ResourceUnmet` only where the runtime cannot hand
them out.

**7.3.2.3** An env MUST serve `GitEnvMixin` and `GitWorktreeEnvMixin` only where its probe found
`git` on the `PATH`, and `BashEnvMixin` only where it found `bash`; a role declaring a mixin its env
does not serve MUST be refused with `CapabilityMissing` before anything runs, naming the missing
program where `git` is the cause.

**7.3.2.4** An env MUST serve every other env mixin.

**7.3.2.5** An image a role declares MUST be ignored by every kind but `docker`, `swarm` and
`apple-container`, and by a `docker` env working in a running container (Section 7.7.3.4).

#### 7.3.3. Commands

**7.3.3.1** Every command an env runs MUST run in a process group of its own with standard input
closed.

**7.3.3.2** A command that passes its timeout MUST be killed with its whole process group and MUST
raise `EnvCommandTimeout: <command> ran past its timeout of <n>s in <workdir>, and was killed`.

**7.3.3.3** A command still running when its env is closed MUST be killed and MUST raise `EnvError:
<command> was killed: its environment was closed`.

#### 7.3.4. Derived envs

**7.3.4.1** A derived env MUST be on the same machine as the env it was derived from, and MUST share
that env's connection.

**7.3.4.2** A derived env of a `local` or `ssh` env, and of a `slurm` env, MUST live under hmz's
home on the env machine (Section 4 of [FILES], Section 9 of [FILES]).

**7.3.4.3** A derived env of a `docker`, `swarm` or `apple-container` env MUST live inside that
env's container and MUST go with it.

#### 7.3.5. Errors

**7.3.5.1** hmz MUST raise `EnvUnavailable` where an env machine or its workdir is not there or
cannot be brought up.

**7.3.5.2** hmz MUST raise `EnvConnectionError` where an env machine cannot be reached or the
connection to it breaks.

**7.3.5.3** hmz MUST raise `EnvFileNotFound` and `EnvPermissionDenied` where a path in an env is
missing or refused.

**7.3.5.4** hmz MUST raise `EnvError` for every other failure of an env.

**7.3.5.5** An error about an env on a saved runtime MUST name it `<kind>@<provider>`, and one about
an env on a default provider MUST name it `<kind>` alone.

### 7.4. Runtimes

#### 7.4.1. What a runtime is

**7.4.1.1** A runtime MUST be a machine saved under a name — an ssh host, a docker daemon, a docker
swarm, this machine's Apple containers, or the Slurm cluster this machine submits to — on which hmz
puts an env when the env names it.

**7.4.1.2** A runtime MUST NOT be visible to a flow: an env put on a runtime MUST offer the flow the
same env protocol whatever runtime it is on.

**7.4.1.3** A runtime MUST be saved in the settings file (Section 3.3 of [FILES]); its kind and its
name MUST be taken from where it is saved, whatever its entry says.

**7.4.1.4** A runtime's name MUST match `[A-Za-z0-9][A-Za-z0-9._-]*`.

#### 7.4.2. Saving and reading

**7.4.2.1** hmz MUST refuse a runtime with `ValueError` when it is saved, and MUST NOT leave that
refusal until the runtime is used, where any field fails its rule in this document or in Section 3.3
of [FILES].

**7.4.2.2** hmz MUST refuse to save a runtime under a name its kind already has, unless the save
replaces it.

**7.4.2.3** hmz MUST NOT list a runtime that cannot be read, and MUST refuse an env naming one with
`EnvUnavailable: the <kind label> '<name>' cannot be read; fix or remove it: runtimes.<kind>.<name>
in <settings file>`.

**7.4.2.4** A harness setting or fallback entry naming a runtime nobody saved MUST be accepted when
saved, and MUST be refused, or count as unable to hold the env, when used.

#### 7.4.3. Harness and fallback fields

**7.4.3.1** A runtime of every kind MUST accept a harness setting, whose meaning is Section 6.4. hmz
MUST refuse a harness setting that is none of `local`, `env` and `<backend>:<name>`, and one naming
the runtime itself.

**7.4.3.2** A runtime of every kind MUST accept a fallback list of `<backend>:<name>` entries, whose
meaning is Section 7.11. hmz MUST refuse an entry of another shape, one given twice, and one naming
the runtime itself.

#### 7.4.4. Checking a runtime

**7.4.4.1** Checking a runtime MUST NOT raise: the check MUST answer whether the runtime was
reached, why not, and what it has — CPUs, memory, GPUs, the GPUs that answer, OCI runtimes and
version where the kind has them — and every way in which the runtime cannot hand out what it is
saved to hand out.

**7.4.4.2** Checking an ssh runtime MUST fail rather than wait where the host asks for a password.

### 7.5. `local`

**7.5.1** A `local` env MUST be a directory on this machine, which MUST exist when the env is made;
otherwise hmz MUST raise `EnvUnavailable: there is no directory <path> on this machine`.

**7.5.2** A `local` env MUST take no provider and no harness setting, and its sessions MUST have env
location local (Section 6.3.1.2).

**7.5.3** A `LocalEnv` role MUST be filled with the workspace the epic was started in; a `LocalEnv`
role given an env on another machine MUST be refused with `CapabilityMissing`.

### 7.6. `ssh`

**7.6.1** An `ssh` env MUST be a directory on a host reached with the system `ssh`, named either by
a saved ssh runtime or by a host nobody saved.

**7.6.2** An `ssh` env's workdir MUST be absolute, or under `~`, which MUST be the login's home.

**7.6.3** Every field of a saved ssh runtime that is set MUST reach every `ssh` to its host ahead of
hmz's own options; the host and port MUST form the destination, and the user, identity file, jump
host, configuration file and every other option MUST be passed as `ssh` options.

**7.6.4** hmz MUST NOT read or print what an identity file holds.

**7.6.5** An ssh runtime imported from an ssh configuration MUST name the configuration's `Host`
alias and MUST NOT name what the alias resolved to; re-importing the runtime MUST keep its workdir,
harness setting and fallback list, and MUST NOT overwrite a runtime that was typed rather than
imported.

**7.6.6** An ssh runtime with neither a host nor an alias, with an option that has a field of its
own, or with a value holding a newline or `"` MUST be refused when saved.

### 7.7. `docker`

#### 7.7.1. A container of its own

**7.7.1.1** A `docker` env whose runtime names no running container MUST be one container of its own
on the daemon its runtime names, started when the env is probed.

**7.7.1.2** The container MUST be started from the role's declared image, else the runtime's image,
else `python:3.12-slim`, and MUST need nothing in the image but `/bin/sh` and a Python of version
3.12 or later.

**7.7.1.3** The workdir MUST be a directory of the daemon's host, mounted into the container at its
own path; hmz MUST refuse with `EnvUnavailable` a workdir the daemon's host has not got, and MUST
refuse a workdir under `~` on a daemon not on this machine.

**7.7.1.4** The container MUST run as this user on a daemon on this machine, as root inside a
rootless daemon on this machine, and as the owner of the workdir on the daemon's host otherwise.

**7.7.1.5** The container MUST have `HOME=/tmp` set, and MUST see no GPU unless it was given GPUs.

**7.7.1.6** The container MUST be given exactly the CPUs, memory and GPUs its role declares as hard
limits, no limit on a resource the role does not declare, and no GPU where the role declares none.

**7.7.1.7** The container MUST be started with the runtime's OCI runtime and run arguments.

**7.7.1.8** The container MUST be named `<name_prefix>-<role>-<8 hex digits>` where the runtime sets
a name prefix, and `humanize-<provider>-<role>-<8 hex digits>` otherwise, `<provider>` being `local`
for a default provider; `-<role>` MUST be left out for an env of no role.

**7.7.1.9** The container MUST carry the labels `humanize=<uid>`, `humanize.cpus`,
`humanize.memory`, `humanize.gpus` (what it was given), `humanize.provider`, `humanize.role`,
`humanize.host` (this host's name) and `humanize.pid` (the owning process); hmz MUST NOT take any of
these from a label the caller gives.

**7.7.1.10** The container MUST be removed when the env is closed.

#### 7.7.2. Allocation

**7.7.2.1** Before any agent starts, hmz MUST hold what the role asks against what the runtime is
saved to hand out — its saved CPUs, memory and GPUs, each the daemon's own where saved as zero or
empty, its GPU memory and its container limit — less what the runtime's running containers hold,
read off their labels.

**7.7.2.2** hmz MUST hand out GPUs as the first GPUs that no running container holds among those of
the daemon's host that answer when asked, each by the CDI name it answered under, else by its UUID;
where nothing can be asked, hmz MUST treat every GPU listed as answering.

**7.7.2.3** Two epics on this machine allocating from one runtime at once MUST NOT both be given the
same share.

**7.7.2.4** A shortage MUST raise `ResourceUnmet`, every shortage joined by `; `, each saying how
much of what is free and which container holds the rest.

> Informative: allocations made from different machines against one daemon are counted from
> the labels each finds, and can exceed the runtime's limits when made at the same moment.

#### 7.7.3. A running container

**7.7.3.1** A `docker` env whose runtime names a running container MUST work in that container,
which hmz MUST NOT start, stop, remove, label or count against any limit.

**7.7.3.2** A runtime naming a running container MUST be refused when saved where it also sets an
image, an OCI runtime, run arguments, a name prefix, CPUs, memory, GPUs, GPU memory or a container
limit.

**7.7.3.3** A runtime naming a container that does not exist or is not running MUST raise
`EnvUnavailable: docker@<provider>: cannot work in the container <container>: <reason>`.

**7.7.3.4** The env's resources MUST be what the probe inside the container finds, and the role's
declared image MUST be ignored.

**7.7.3.5** The workdir MUST be a path inside the container, which hmz MUST NOT mount.

**7.7.3.6** Several envs and epics MUST be able to work in one running container at once, each with
mirrors of its own; closing an env MUST remove its own mirrors and nothing else.

#### 7.7.4. Running as a user, with variables, under a wrapper

**7.7.4.1** Where a docker runtime sets an exec user `UID[:GID]`, exec variables `NAME=VALUE` or
exec wrapper words, every command hmz runs in an env's container on that runtime — the serving half,
a native harness CLI and every command an agent runs there — MUST run as that user, with those
variables, under those words.

**7.7.4.2** An exec user that is not `UID[:GID]`, an exec variable that is not `NAME=VALUE`, and an
exec wrapper word that is empty or spans lines MUST be refused when saved.

#### 7.7.5. Runtime fields

**7.7.5.1** A docker runtime's endpoint MUST be one of `local`, `unix:///PATH`, `tcp://HOST:PORT`,
`ssh://[USER@]HOST[:PORT]`, `ssh:<name>` of a saved ssh runtime, and `context:<name>`; an
`ssh:<name>` endpoint MUST be dialled with every option of that ssh runtime.

**7.7.5.2** TLS certificates MUST be accepted only for a `tcp://` endpoint.

**7.7.5.3** A name prefix of a docker or swarm runtime MUST consist of letters, digits, `-` and `_`,
MUST start and end with a letter or a digit, and MUST be at most 54 characters; any other MUST be
refused when saved.

**7.7.5.4** Negative amounts of CPUs, memory, GPU memory or containers MUST be refused when saved.

#### 7.7.6. Errors

**7.7.6.1** No `docker` on this machine MUST raise `EnvUnavailable: <where>: docker was not found on
this machine`.

**7.7.6.2** A daemon that does not answer MUST raise `EnvConnectionError: could not connect to
<where>: <reason>`.

**7.7.6.3** A container that does not start MUST raise `EnvUnavailable: <where>: could not start a
container of <image> on <endpoint>: <reason>`.

### 7.8. `swarm`

**7.8.1** A `swarm` env MUST be the one task of a service of its own, created on the swarm manager
its runtime names when the env is probed, and removed when the env is closed; the task MUST NOT be
restarted.

**7.8.2** The service MUST be created from the image a `docker` env's container would be (Section
7.7.1.2), with the workdir mounted at its own path on whichever node the task lands on; every node
the task can land on MUST have the workdir at that path.

**7.8.3** The task MUST run as this user where the manager is on this machine, and as the owner of
the workdir on the manager's host otherwise.

**7.8.4** The service MUST reserve exactly the CPUs and memory its role declares and be limited to
them, and MUST reserve as many of the runtime's GPU generic resource as the role declares GPUs; a
role declaring GPUs of a runtime naming no GPU resource MUST be refused with `ResourceUnmet`.

**7.8.5** The service MUST be placed under the runtime's constraints, created with its run
arguments, and named and labelled as Section 7.7.1.8 and Section 7.7.1.9 name and label a container.

**7.8.6** Before any agent starts, hmz MUST hold what the role asks against the runtime's task
limit, and its CPUs and memory where saved, less what the runtime's services hold; a shortage MUST
raise `ResourceUnmet` as Section 7.7.2.4 says, and Section 7.7.2.3 MUST hold.

**7.8.7** A task no node takes for want of room MUST raise `ResourceUnmet` with the scheduler's
words: at once where no node able to take a task could ever hold it, and after 30 seconds otherwise.
The service MUST be removed first.

**7.8.8** A task that fails, or does not run within 600 seconds of being placed, MUST raise
`EnvUnavailable`, and its service MUST be removed.

**7.8.9** A manager that manages no active swarm, or is only a worker of one, and a node without the
workdir MUST raise `EnvUnavailable`.

**7.8.10** hmz MUST reach the task's container through the daemon the runtime names for that node's
host, else through the manager where the task landed on the manager, else over ssh to the node's
address.

**7.8.11** A swarm constraint MUST compare an attribute with `==` or `!=`; a GPU resource MUST be
one word; a node MUST be named by a saved ssh runtime or by `[user@]host[:port]`. Any other MUST be
refused when saved.

### 7.9. `apple-container`

**7.9.1** An `apple-container` env MUST be one container of Apple's `container` of its own on this
machine, started when the env is probed and deleted when it is closed.

**7.9.2** No `container` command on this machine MUST raise `EnvUnavailable`, and a container system
that does not answer or is not running MUST raise `EnvConnectionError`.

**7.9.3** The container MUST be started from the image a `docker` env's container would be (Section
7.7.1.2), MUST run as this user, and MUST mount the workdir, a directory of this machine, at its own
path and at the other name macOS gives it under `/private` where it has one. A workdir holding a
comma MUST be refused.

**7.9.4** The container MUST be sized with the CPUs and memory its role declares, memory rounded up
to a whole MiB, and with `container`'s own size where the role declares none.

**7.9.5** A role declaring GPUs MUST be refused with `ResourceUnmet`.

**7.9.6** The container MUST be named as Section 7.7.1.8 says, with a name prefix never set, and
labelled as Section 7.7.1.9 says without `humanize.gpus`.

**7.9.7** Before any agent starts, hmz MUST hold what the role asks against the runtime's CPUs and
memory (this machine's where saved as zero) and its container limit, less the size of every running
container of the runtime; a shortage MUST raise `ResourceUnmet`, and Section 7.7.2.3 MUST hold.

> Informative: a mirrored session cannot run on macOS (Section 6.3.2.1), so a
> session in an Apple container needs the harness setting `env` with an image holding the CLI,
> or a harness runtime.

### 7.10. `slurm`

**7.10.1** A `slurm` env MUST be one job of its own of one task on one node, submitted with `sbatch`
from this machine when the env is probed and cancelled when the env is closed.

**7.10.2** The job MUST be submitted under the runtime's partition, account, quality of service,
time, constraint and run arguments, each where set, and MUST ask for exactly the CPUs, memory
(rounded up to a whole MiB) and GPUs its role declares, nothing where the role declares none.

**7.10.3** The job MUST receive nothing of this process's environment but `HOME` and `USER`.

**7.10.4** The workdir MUST be the same path on this machine and on every node the job can land on;
hmz MUST NOT mount or copy it, and the role's declared image MUST be ignored.

**7.10.5** The job MUST be named as Section 7.7.1.8 says, and MUST carry in its comment the labels
of Section 7.7.1.9 and `humanize.name`.

**7.10.6** hmz MUST reach the job's node by a step of the job per connection where the runtime's way
in is `srun`, and by a connection per session to a serving half that the job itself runs, presenting
a secret the job was given on no command line, where it is `tcp`; the runtime's Python MUST be tried
before any other on the node.

**7.10.7** Before any agent starts, hmz MUST hold what the role asks against the runtime's job
limit, and its CPUs and memory where saved, less what the runtime's jobs hold, waiting or running; a
shortage MUST raise `ResourceUnmet` as Section 7.7.2.4 says. Section 7.7.2.3 MUST hold until the job
is submitted and MUST NOT hold while the job waits for a node.

**7.10.8** A job still waiting once the runtime's maximum wait is over MUST be cancelled and MUST
raise `ResourceUnmet: <where>: job <id> was not given a node within <n>s: it is pending for
<reason>`; a maximum wait of zero MUST wait without limit.

**7.10.9** No `sbatch` on this machine, a job refused or ended before it ran, a `tcp` serving half
that does not say it is listening within 60 seconds, and a node without the workdir MUST raise
`EnvUnavailable`; a node that cannot be reached MUST raise `EnvConnectionError`.

**7.10.10** A partition, account or quality of service of more than one name, a time Slurm's
`--time` does not take, a constraint of more than one word, a Python neither absolute nor under
`~/`, and a way in other than `srun` and `tcp` MUST be refused when saved.

### 7.11. Falling back

**7.11.1** Where an env names a saved runtime that cannot hold it — opening is refused, probing
fails with `EnvUnavailable` or `EnvConnectionError`, or the runtime or its machine cannot give what
the role declares (`ResourceUnmet`) — hmz MUST try the runtimes of that runtime's fallback list in
order, until one holds the env.

**7.11.2** hmz MUST close every env refused on the way.

**7.11.3** hmz MUST NOT walk the fallback list of a runtime it fell back to.

**7.11.4** An env that names no saved runtime MUST have no fallback.

**7.11.5** An env moved to a fallback runtime MUST use that runtime's saved workdir, else the
workdir the env named.

**7.11.6** hmz MUST tell the user, on standard error under `hmz exec` and as a notice in a
**frontend**, `<kind>:<from> cannot hold '<role>': <reason>; using <kind>:<to>`.

**7.11.7** Where every runtime refuses, hmz MUST raise an error of the kind of the last refusal,
naming every runtime tried and why.

**7.11.8** hmz MUST record in the epic the env as named and, where they differ, the runtime each
role was put on (Section 6 of [FILES]); an epic picked up again MUST be given the env as named.

### 7.12. Leftovers

**7.12.1** The next epic on this machine that allocates from a `docker`, `swarm`, `apple-container`
or `slurm` runtime MUST remove every leftover of that runtime, with its mirrors, before it
allocates.

**7.12.2** hmz MUST NOT remove a container, service or job whose labels name another user or another
host.

**7.12.3** hmz MUST NOT remove a running container that a docker runtime names, nor the mirrors of
an epic that worked in it and was killed.

## 8. Chat

### 8.1. Scope

This section defines the chat: the built-in **flow** named `chat`, in which the **user** talks to
one **agent**, one turn at a time, in one conversation. It states how a chat starts, takes turns,
reports its status, runs beside other **epics**, folds away, is carried on and ends, and what every
**frontend** draws and refuses for it.

Out of scope:

- The flow API that `chat` is written against: Section 3 of [PYTHON].
- How hosts are started, linked and let go: Section 3 of [DAEMON], Section 4 of [DAEMON].
- The terminal interface's layout outside a chat: [TUI].
- The web interface's layout outside a chat: Section 3 of [WEB].
- Side questions asked about a chat: Section 9.
- Notices of chat turns: Section 10.
- What an epic records: Section 3, Section 6 of [FILES].

### 8.2. Terminology

**8.2.1** **Chat**: an epic of the flow `chat`, where a flow is `chat` when its name is `chat` or
when it is named by a path or reference whose last part is `chat`.

**8.2.2** **Assistant**: the one agent **role** of `chat`, and the agent that fills it.

**8.2.3** **Conversation**: the one **session** of the assistant in a chat.

**8.2.4** **Turn**: the assistant's answer to one message from the user, from the moment the message
is delivered to the moment the answer is complete.

**8.2.5** **Between turns**: the state of a chat whose assistant has completed a turn and waits for
the user's next message.

**8.2.6** **Folding away**: the end of the **host** that holds a chat, while the chat is between
turns, leaving its epic recorded so that it can be carried on.

**8.2.7** **Carrying on**: resuming a chat in its own epic with its own conversation.

### 8.3. The flow

**8.3.1** `chat` MUST declare exactly one agent role, `assistant`, one outworlder role, `human`,
which is the user, and one environment role, `workspace`, which is the **workspace** on this
machine.

**8.3.2** `chat` MUST take no params.

**8.3.3** `chat` MUST NOT require a budget, and a chat MUST run with no limit on its spending.

**8.3.4** The assistant MUST have every capability that its **harness** offers, the web included.

**8.3.5** `chat` MUST be resumable.

**8.3.6** `chat` MUST be the flow the terminal interface opens on in a workspace for which no flow
is remembered.

### 8.4. Turns

**8.4.1** The task of a chat MUST be the first message of its conversation.

**8.4.2** Each answer of the assistant MUST be shown to the user as the assistant's line of the
conversation.

**8.4.3** The next message the user says in a chat that is between turns MUST be the next turn of
the same conversation.

**8.4.4** A message the user says while a turn is open MUST be delivered to that turn where the
harness accepts a message mid-turn, and MUST otherwise be held for the next turn.

**8.4.5** A frontend MUST NOT draw the chat's wait for the next message as a question to the user.

**8.4.6** A question the assistant asks the user mid-turn MUST be shown in the conversation with the
options it offers, and the user's next message MUST answer it.

**8.4.7** An empty next message MUST end the chat.

**8.4.8** Where the **outworlder** `human` is away, the chat MUST take its first turn and then end,
the next message being empty.

**8.4.9** Where the first turn of a chat that is not carried on fails, the epic MUST end failed with
what the harness said.

**8.4.10** Where a later turn fails, the chat MUST say in the conversation that the turn could not
be taken and why, and MUST go on between turns.

### 8.5. Status

**8.5.1** A chat MUST be reported as `running` while a turn is open.

**8.5.2** A chat MUST be reported as `stopped` while it is between turns; the status line of the
terminal interface says where its turn is instead (Section 11.4 of [TUI]).

**8.5.3** A chat that has ended MUST be reported as `stopped`, or as `failed` where Section 8.4.9
applies; a chat MUST NOT be reported as `done`. A frontend MAY mark a chat as asking, in place of
`running` or `stopped`, while it waits on a question a person has not yet seen, as Section 3.5.8 of
[WEB] does.

**8.5.4** A frontend MUST NOT offer a way to stop a chat or to force it to stop.

**8.5.5** A frontend MUST refuse a request to stop a chat, saying that a chat is not stopped.

### 8.6. Many chats

**8.6.1** Each chat MUST be an epic of its own on a host of its own.

**8.6.2** Any number of chats MUST be able to run in one workspace at once, beside the workspace's
own flow.

**8.6.3** Starting a chat MUST NOT end, stop or wait on any other chat or any flow.

**8.6.4** Starting or resuming a flow in a workspace MUST NOT end, stop or wait on any chat of that
workspace.

**8.6.5** A frontend MUST list every chat among the epics of its workspace, with its status as
Section 8.5 states it.

### 8.7. Folding away and carrying on

**8.7.1** A chat MUST fold away once it is between turns and no frontend has followed it for the
period Section 3 of [DAEMON] states.

**8.7.2** A chat MUST NOT fold away while a turn is open.

**8.7.3** A chat that a host holds MUST, when opened from a list of epics, be followed where it is,
its conversation drawn from its first message.

**8.7.4** A chat that has folded away MUST, when opened from a list of epics, be drawn with what was
said in it, and the next message the user says in it MUST carry it on.

**8.7.5** Carrying on a chat MUST continue the same epic, MUST continue the same conversation, and
MUST take the message that carried it on as the next turn.

**8.7.6** Where the conversation of a chat cannot be carried on, the chat MUST say so in the
conversation with the reason, MUST start a new conversation in the same epic, and MUST answer the
message that carried it on in that new conversation.

**8.7.7** A chat of another workspace, or one that cannot be carried on here, MUST be refused,
saying that the chat cannot be continued here.

**8.7.8** A chat MUST NOT be carried on by `/resume` or by resuming the workspace's last epic; it
MUST be carried on only from a list of epics or by saying something in it.

### 8.8. Drawing a chat

**8.8.1** Every frontend MUST draw a chat as its conversation alone: the user's messages and the
assistant's answers, in order.

**8.8.2** A frontend MUST NOT draw for a chat a monitor, a graph or list of agents, a tree of agents
or sessions, a transcript of several sessions, a list of outworlders or a timeline in Exomyth.

**8.8.3** A frontend MUST NOT offer for a chat a way to stop it, to force it, or to round its views.

**8.8.4** The terminal interface MUST end the chat on the screen by `/clear`, which starts a new
chat and leaves the previous one going on its own host ([TUI]).

**8.8.5** The web interface MUST end the chat on the screen by starting a new epic, which leaves the
previous chat going on its own host (Section 3 of [WEB]).

**8.8.6** Leaving a frontend while a chat is on the screen MUST NOT ask the user anything, and MUST
leave a chat that a host holds to that host.

**8.8.7** Every behaviour of a chat that the web interface offers MUST be offered by the terminal
interface by keys and commands, and every behaviour of a chat that the terminal interface offers
MUST be offered by the web interface.

## 9. Side Questions

### 9.1. Scope

This section defines side questions: questions the **user** asks about an **epic** without the
question reaching the **flow** of that epic. It states who answers a side question, what the
answerer is told, what the answerer is permitted to do, how the **btw** agent is chosen, how the
user picks whom a side question is asked of, and how long a side conversation lasts, in every
**frontend** that offers side questions.

Out of scope:

- The layout of btw mode in the terminal interface: [TUI].
- The layout of the btw panel in the web interface: Section 3 of [WEB].
- The `btw` key of `settings.yaml`: Section 3 of [FILES].
- The requests a frontend sends to ask a side question: Section 4 of [DAEMON], Section 4 of [WEB].
- What an epic records and how its figures are worked out: Section 3, Section 10.

### 9.2. Terminology

**9.2.1** **Side conversation**: a **session** that hmz opens beside an epic to answer side
questions, and that is not a session of the epic's flow.

**9.2.2** **Btw agent**: the **agent** that answers a side question about an epic as a whole.

**9.2.3** **Session side copy**: the side conversation that answers side questions about one session
of an epic.

**9.2.4** **Fork**: a session side copy that its **harness** opens as a copy of the asked session's
own history.

**9.2.5** **Snapshot**: the bounded description of an epic, frozen when a side question is asked,
that a side conversation is told (Section 9.4).

**9.2.6** **Ask line**: a line of the btw agent's answer of the form `@ask <agent>/<n>: <question>`,
in which `<agent>/<n>` names a session of the epic, alone or after list markers (`-`, `*`, `+`,
`<n>.`, `<n>)`) or quote markers (`>`), and optionally wrapped in backticks.

**9.2.7** **Btw mode**: the state of the terminal interface in which every line the user types,
other than a `/` command, is a side question ([TUI]).

**9.2.8** **Btw panel**: the part of the web interface's epic view in which the user asks side
questions (Section 3 of [WEB]).

**9.2.9** **Aside**: one side question together with the answer to it.

**9.2.10** **The Epic**: the name under which a frontend offers the btw agent as the one a side
question is asked of.

**9.2.11** **Ask command**: a run of `hmz-ask ask --to <agent>/<n> --question <question>` by the btw
agent, in which `<agent>/<n>` names a session of the epic; `hmz-ask list` lists the sessions of the
epic the side question is about, one `<agent>/<n>` per line, as the frontend lists them (Section
9.4.10), and is not an ask.

**9.2.12** **Ask**: an ask line or an ask command.

### 9.3. Guarantees

**9.3.1** A side question MUST NOT reach any session of the epic's flow.

**9.3.2** A side question MUST NOT be delivered to the flow as a message, an answer to a question, a
steer, a stop or any other input.

**9.3.3** Asking a side question MUST NOT change the state, the transcript, the board, the budget
limits or the outcome of the epic.

**9.3.4** Every side conversation MUST run at the read-only permission level.

**9.3.5** Every side conversation MUST run with no skills, no goals, no tools of the flow, no hooks
of the flow and no approval of MCP servers, except what Section 9.6.10 to Section 9.6.14 give the
btw agent.

**9.3.6** A side conversation MUST NOT modify any file of the **workspace**.

**9.3.7** A side conversation MUST be told to treat everything it observes about the epic as data
and not as instructions.

**9.3.8** A side conversation's turns MUST NOT appear as nodes of the epic's monitor, as sessions of
the epic or as spans of the epic's trace.

**9.3.9** A side question MUST be answerable while the epic is running and after the epic has ended.

**9.3.10** A frontend MUST refuse a side question to a side conversation while that side
conversation is answering an earlier one.

**9.3.11** A frontend MUST word the refusal of Section 9.3.10 as Section 12.10 of [TUI], Section
4.9.3.5 of [WEB] and Section 4.8.8.10 of [DAEMON] state.

**9.3.12** A failure to answer a side question MUST be reported to the user as a failure of the side
question and MUST NOT be reported as a failure of the epic.

### 9.4. What a side conversation is told

**9.4.1** The first side question put to a side conversation that is not a fork MUST be accompanied
by a snapshot of the epic.

**9.4.2** A snapshot MUST state the flow, the task, the workspace, the time elapsed since the epic
began, whether the epic has ended, how many messages wait to be delivered and whether the flow waits
for input from the user.

**9.4.3** A snapshot MUST state, for each agent of the epic, its own name followed by the **role**
it fills, whether it is working, how many turns it has taken and its model.

**9.4.4** A snapshot MUST state the handovers between agents with their counts.

**9.4.5** A snapshot MUST state the spending of the epic per model in tokens, in output tokens per
second and, only where the model is priced, in money.

**9.4.6** A snapshot MUST NOT state a missing price as zero money.

**9.4.7** A snapshot MUST state the tokens of each kind spent over the whole epic and MUST mark each
figure that is only a floor as a floor.

**9.4.8** A snapshot MUST state at most the 32 most recent observations of the epic: what its agents
said and did and what its flow printed, each cut to at most 600 characters.

**9.4.9** A snapshot MUST NOT contain any agent's thinking.

**9.4.10** Every side question put to the btw agent, the first and every later one, MUST list the
sessions of the epic by `<agent>/<n>`, saying where none is open yet, and MUST state that the btw
agent can ask them by ask commands, and by ask lines where it cannot run a command (Section 9.6).

**9.4.11** A snapshot told to a session side copy MUST contain only the observations of the asked
session's agent and of the flow, and MUST NOT list the sessions of the epic.

**9.4.12** A fork MUST be told which session it is a copy of, and MUST be told not to carry on that
session's task.

**9.4.13** Every question after the first in one side conversation MUST be put to that side
conversation without a further snapshot, and, to the btw agent, with only what Section 9.4.10
states.

**9.4.14** A snapshot MUST be of the epic the side question is about alone, and MUST NOT contain
observations of any other epic.

### 9.5. Who answers

**9.5.1** A side question asked while the user reads one session of an epic MUST be answered by the
session side copy of that session.

**9.5.2** A side question asked while the user reads an agent's transcript MUST be answered by the
session side copy of that agent's newest session.

**9.5.3** A side question asked anywhere else MUST be answered by the btw agent.

**9.5.4** Where the harness of the asked session can fork a session, the session side copy MUST be a
fork.

**9.5.5** Where the harness of the asked session cannot fork a session, or the fork does not open,
or the fork returns no answer, the session side copy MUST be a new session of the same agent told a
snapshot (Section 9.4.11).

**9.5.6** A session that has ended MUST be askable as Section 9.5.1 to Section 9.5.5 state.

**9.5.7** In the web interface, a session of an epic that no host (Section 3.2.1 of [DAEMON]) holds
any longer MUST be askable, its session side copy being carried on from where that epic kept the
session.

**9.5.8** Where the session the user reads no longer exists, a frontend MUST refuse the side
question, naming that session.

**9.5.9** Where there is no btw agent (Section 9.7) and the user does not read a session, a frontend
MUST refuse the side question, saying that the agent that answers The Epic is set in the settings.

### 9.6. The btw agent asking sessions

**9.6.1** The btw agent MAY run ask commands during its turn, and MAY answer with one or more ask
lines instead of an answer to the user.

**9.6.2** hmz MUST put each ask's question to the session side copy of the session it names, opening
that side copy as Section 9.5.4 and Section 9.5.5 state where it is not open.

**9.6.3** hmz MUST return each session side copy's answer to the btw agent, attributed to the
session it came from.

**9.6.4** hmz MUST carry out at most 4 asks, ask commands and ask lines together, per side question
that the user asks.

**9.6.5** Once 4 asks have been carried out for one side question, hmz MUST answer every further ask
command with `No more asks this question: answer the user with what you have.`, MUST tell the btw
agent so after ask lines, and MUST take its next answer as the answer to the user.

**9.6.6** An ask that names no session of the epic MUST be answered back to the btw agent as a
session not found, naming the sessions of the epic.

**9.6.7** An ask whose session side copy fails or answers nothing MUST be answered back to the btw
agent as that failure or as no answer.

**9.6.8** A frontend MUST show the user each ask as it is carried out, naming the session and the
question, once per ask.

**9.6.9** The answer shown to the user MUST NOT contain ask lines.

**9.6.10** The btw agent's side conversation MUST carry the skill `ask-conversation`, which states
the ask command and `hmz-ask list`, and says to ask a session rather than guess what it did or
knows; a session side copy MUST NOT carry it.

**9.6.11** hmz MUST carry out an ask command on the host that runs the btw agent, while the btw
agent's turn waits on it, and MUST carry out one ask command run twice with the same session and
question in one turn once.

**9.6.12** hmz MUST hang a pre-tool-use hook on the btw agent that carries out an ask command the
btw agent reaches for. On a harness on which a refusal prevents the tool (Section 4.9.2.1), the hook
MUST refuse the tool with the ask command's output as the reason.

**9.6.13** On a harness that has a shell (Section 4.10.2.1), `hmz-ask` MUST be a fake command line
that prints the ask command's output. On `codex`, `hmz-ask` alone MUST run outside Codex's sandbox
(Section 4.10.2.8), and the sandbox MUST otherwise stay as the read-only rung puts it, its network
cut.

**9.6.14** Where the answer to an ask command reached the btw agent neither as a refusal (Section
9.6.12) nor as output (Section 9.6.13), hmz MUST, when the btw agent's turn would stop, send it on
with every such answer as Section 9.6.3 states, at most 4 times per turn.

**9.6.15** A btw agent whose harness serves no pre-tool-use hook that fires (`litellm`) MUST ask by
ask lines alone.

### 9.7. Choosing the btw agent

**9.7.1** The btw agent MUST be the agent named by the `btw` setting of `settings.yaml`, for every
epic alike.

**9.7.2** Where the `btw` setting names no agent, there MUST be no btw agent, and an agent of the
epic, of its flow or of its sessions MUST NOT stand in for it.

**9.7.3** The `btw` setting MUST be an agent spec (Section 3.4.3.1 of [FILES]).

**9.7.4** A change of the `btw` setting MUST take effect from the next side conversation the btw
agent opens, and MUST NOT change a side conversation already open.

**9.7.5** A frontend MUST NOT offer a choice of the btw agent other than the `btw` setting, and MUST
NOT offer a choice of the agent of a session side copy, which is the asked session's own (Section
9.5.4, Section 9.5.5).

**9.7.6** A side question whose side conversation would run on a harness that has no read-only rung
(`mcode`, `dsh`, every ACP harness) MUST be refused, saying that harness has no read-only rung.

### 9.8. Whom a side question is asked of

**9.8.1** The btw panel MUST hold any number of side conversations at once, each asking one of The
Epic or one session of the epic, MUST let the user open a new one, and MUST show one at a time,
offering the others to switch to.

**9.8.2** A side conversation of the btw panel MUST be asked of whom the user picked before its
first question, and MUST NOT be asked of anyone else after; to ask another, the user opens another
side conversation.

**9.8.3** The btw panel MUST offer, until a side conversation is opened by its first question, one
control that picks whom that side conversation asks, outside the box its question is typed in, and
MUST NOT offer that control once the side conversation is open.

**9.8.4** That control MUST name the btw agent as `The Epic`, and MUST NOT name it otherwise.

**9.8.5** That control MUST lay the sessions out as a hierarchy: one entry per agent of the epic,
naming the agent and the role it fills, under which are that agent's sessions, newest first.

**9.8.6** That control MUST let the user narrow what it offers by typing part of an agent's name, a
role or a session.

**9.8.7** That control MUST show which one is picked, and MUST keep the pick while the epic is
redrawn, falling back to The Epic only where the session picked is no longer of the epic.

**9.8.8** The btw panel MUST name each side conversation by whom it asks, as `btw · The Epic` or
`btw · <agent>/<n>`.

**9.8.9** While a side conversation of the btw panel is answering, the panel MUST show that it is,
on that side conversation and where it is offered to switch to, MUST show each ask (Section 9.6.8)
as it is carried out, and MUST NOT let the user send that side conversation another question.

**9.8.10** Btw mode MUST pick whom it asks by the view read, as Section 9.5 states ([TUI]).

### 9.9. Lifetime of side conversations and asides

**9.9.1** Every side question after the first, in one btw mode or one side conversation of the btw
panel, MUST go on in the same side conversation as the first, so that a question can refer to an
earlier one.

**9.9.2** Leaving btw mode (Section 12.8 of [TUI]) MUST close every side conversation that btw mode
opened.

**9.9.3** Closing a side conversation in the btw panel MUST close it, and no other.

**9.9.4** A new epic starting on the host the frontend follows MUST close every side conversation
opened about the epic it replaces (Section 12.9 of [TUI]).

**9.9.5** A frontend going away MUST close every side conversation it opened.

**9.9.6** A side conversation that opens after its btw mode was left, or after it was closed in the
btw panel, MUST be closed at once, and its answer MUST NOT be shown.

**9.9.7** The web interface MUST keep, per workspace, which side conversations are open, about which
epic, whom each asks, the question each is answering and its ask lines so far, and the last 200
asides of each, so that a page opened again shows them.

**9.9.8** The terminal interface MUST show each aside in the transcript the user reads, and MUST NOT
keep asides after the transcript is cleared or the interface closes.

**9.9.9** A frontend MUST show an answer to a side question distinguishably from every line of the
epic's own (Section 12.5 of [TUI]).

## 10. Monitoring

### 10.1. Scope

This section defines what **hmz** works out about an **epic** while it executes and after it
ends: the live figures every **frontend** draws (who is working, handovers, turns, tokens, money,
rate), the price list money is computed from, the notices hmz raises about the epics of **this
machine**, the Chrome traces and profiles hmz gathers of an epic, and the Exomyth timeline of an
epic.

Out of scope:

- How a frontend draws these figures, its keys and screens ([TUI], Section 3 of [WEB], Section 3 of
  [DESKTOP]).
- Side questions asked about an executing epic (Section 9).
- The wire format in which a frontend receives records and notices (Section 4 of [DAEMON], Section 4
  of [WEB]).
- Where traces and profiles are stored inside an epic (Section 6 of [FILES]) and where the price
  list is stored (Section 7 of [FILES]).
- Budgets and how a budget stops an epic (Section 3.3.4).

### 10.2. Terminology

**10.2.1** **Monitor**: the live model of one epic defined in Section 10.3.1.

**10.2.2** **Turn**: one prompt given to a **session** and the work its **agent** does until it
answers.

**10.2.3** **Handover**: the event in which an agent begins a turn after a different agent was the
last to finish one in the same epic.

**10.2.4** **Sub-agent**: an agent that a session's own CLI starts during a turn, without the
**flow** asking for it.

**10.2.5** **Token kind**: one of `input`, `output`, `cache_read`, `cache_write` and `reasoning`.

**10.2.6** **Floor**: a figure that is known to be lower than the true figure because some agent of
the epic does not report what the figure counts.

**10.2.7** **Rate**: the output tokens written in an epic per second over the last five minutes of
wall-clock time.

**10.2.8** **Price list**: the per-token model prices hmz keeps on this machine.

**10.2.9** **Notice**: one record, defined in Section 10.4.2, that something happened to an epic of
this machine that a **user** would want to be told.

**10.2.10** **Chrome trace**: a JSON document in the Chrome Trace Event format, readable by Perfetto
and `chrome://tracing`, describing the sessions of an epic on one timeline.

**10.2.11** **Environment profile**: the record, made while an epic executes, of every program its
agents started and of the threads of each.

**10.2.12** **Flow profile**: the record, made by sampling while an epic executes, of the call
stacks of the flow's own Python code.

**10.2.13** **Exomyth timeline**: the document, defined in Section 10.6, that lays one epic out as
processes, tracks and spans for a frontend to draw.

### 10.3. Live figures

#### 10.3.1. Monitor

**10.3.1.1** hmz MUST work out one monitor per epic, and every frontend MUST draw the figures of an
epic as that monitor reports them, unaltered.

**10.3.1.2** hmz MUST work out the monitor only from the records the **host slot** of the epic sends
to frontends and from the logs the agents' CLIs keep, and MUST NOT ask anything else.

**10.3.1.3** The monitor MUST count each turn against the agent and the session that took it.

**10.3.1.4** The monitor MUST report, for each agent, whether it is working, how many turns it has
taken, how many sessions it has opened, the tokens it has spent, and how long it has been at what it
is doing now.

**10.3.1.5** The monitor MUST report each sub-agent under the agent whose turn started it, with what
it was started about and whether it is still working.

**10.3.1.6** The monitor MUST count each handover from the agent that last finished a turn to the
agent that next began one, separately for each direction, and MUST identify the most recent
handover.

**10.3.1.7** The monitor MUST report, for the epic, how many agents are working, the turns taken,
the time since the epic began and, once the epic ends, the time at which it ended.

**10.3.1.8** The monitor MUST name each agent by its own name, with the **role** it fills shown
after it.

#### 10.3.2. Cost tally

**10.3.2.1** hmz MUST read what a session spends from the log its CLI keeps, as the turn proceeds,
and MUST read it once more when the epic ends.

**10.3.2.2** For a session whose CLI ran on another **machine**, hmz MUST read the copy of its log
kept in the epic.

**10.3.2.3** hmz MUST report, per model, the tokens spent, the rate, and the money spent where the
price list prices that model.

**10.3.2.4** hmz MUST report the money of a model the price list does not price as absent, and MUST
NOT report it as zero.

**10.3.2.5** hmz MUST report, over the whole epic, the tokens spent of each token kind.

**10.3.2.6** hmz MUST mark a per-kind total as a floor where an agent of the epic runs a CLI that
does not report that kind, and MUST mark every per-kind total as a floor where a CLI reports tokens
without their kind.

**10.3.2.7** hmz MUST mark the epic's money as a floor where at least one model of the epic is
priced and at least one is not, and MUST report no money where no model of the epic is priced.

**10.3.2.8** hmz MUST divide a turn that names two or more models between those models in proportion
to what each took, and MUST NOT drop that turn.

**10.3.2.9** An epic that is stopped and still unwinding while a newer epic executes in the same
host slot MUST continue to be counted until it ends, against its own agents only.

**10.3.2.10** hmz MUST work the figures out again at least every five seconds and whenever an agent
reports anything.

**10.3.2.11** hmz MUST report the figures of a turn when that turn ends, in the epic's records, so
that `hmz exec` prints and `hmz exec --json` emits them per turn ([CLI]).

#### 10.3.3. Price list

**10.3.3.1** hmz MUST compute money from the price list, at list price, in US dollars.

**10.3.3.2** hmz MUST fetch the price list from OpenLLMPrices unless the environment variable
`HUMANIZE_PRICES` names another URL or file, and MUST fetch nothing where `HUMANIZE_PRICES` is
`off`, `0`, `no`, `none` or empty.

**10.3.3.3** hmz MUST treat the price list as stale once it is older than 24 hours.

**10.3.3.4** A frontend MUST refresh a stale price list in the background, and MUST NOT delay any
input or drawing while it does.

**10.3.3.5** hmz MUST keep the price list for this machine alone (Section 7 of [FILES]).

**10.3.3.6** hmz MUST price a model by matching its name against the price list once both names are
stripped of a leading account or provider and a trailing release date.

#### 10.3.4. Formats

**10.3.4.1** Every frontend MUST state a duration of the monitor or the cost tally as whole seconds
below one minute (`42s`), as minutes and two-digit seconds below one hour (`3m07s`), and as hours
and two-digit minutes from one hour (`2h05m`), truncating rather than rounding.

**10.3.4.2** Every frontend MUST state a token count of the monitor or the cost tally below 1,000 as
a whole number, below 1,000,000 in thousands with one decimal and the suffix `k`, and otherwise in
millions with two decimals and the suffix `M`.

**10.3.4.3** Every frontend MUST mark a floor of the cost tally by a `+` immediately after the
figure.

### 10.4. Notices

#### 10.4.1. Following

**10.4.1.1** A frontend attached to a host slot MUST follow every epic of that slot from the records
the slot sends, and MUST derive the monitor and the cost tally of those epics as Section 10.3
defines.

**10.4.1.2** A frontend that attaches to a host slot MUST receive the records of the executing or
last epic of that slot from the beginning, unless it asks for none, before records as they happen.

#### 10.4.2. Notices

**10.4.2.1** The web interface and the terminal interface MUST each work out the notices of the
epics of this machine by the rules of this section, from the status each host slot reports, and MUST
NOT attach to a host slot to do so.

**10.4.2.2** hmz MUST raise a notice of kind `done` when an epic ends `done`.

**10.4.2.3** hmz MUST raise a notice of kind `stopped` when an epic ends `stopped` by stopping or
forcing.

**10.4.2.4** hmz MUST raise a notice of kind `failed` when an epic fails, fails inside hmz, is ended
by its budget, or is refused by hmz after a frontend asked to start it.

**10.4.2.5** hmz MUST raise a notice of kind `asked` when a flow asks a person a question.

**10.4.2.6** hmz MUST raise a notice of kind `listening` when a flow other than `chat` waits for the
next thing a person says.

**10.4.2.7** For a `chat` epic, hmz MUST raise a notice of kind `done` when a turn of its agent is
done, MUST raise a notice of its end only where it failed or ended during a turn not yet noticed,
and MUST NOT raise a notice of kind `stopped`.

**10.4.2.8** hmz MUST NOT raise a notice for anything that stood before hmz began working notices
out, and MUST NOT raise a second notice for a question already noticed.

**10.4.2.9** Every notice MUST carry an identifier, its kind, the workspace, the host slot, the epic
name, the flow, the task, the role where it concerns a question, a one-line text, and the moment it
was raised.

**10.4.2.10** hmz MUST number notices in the order they are raised, each identifier greater than
every identifier this machine raised before, including before hmz was last restarted.

**10.4.2.11** hmz MUST keep at least the 200 most recent notices, and MUST serve every kept notice
after a given identifier, and each new notice as it is raised, resuming after the last identifier a
frontend heard (Section 4 of [WEB]).

#### 10.4.3. Notification preferences

**10.4.3.1** hmz MUST keep, as one setting of the **home** shared by every frontend, whether each
notice kind is told to the user and whether the operating system is also told (Section 3 of
[FILES]).

**10.4.3.2** Every notice kind, and telling the operating system, MUST be on unless the user turned
it off.

**10.4.3.3** A frontend MUST NOT tell the user of a notice whose kind is turned off.

> Informative: how each frontend shows a notice is defined in [TUI] and
> Section 3 of [WEB].

### 10.5. Traces and profiles

#### 10.5.1. Chrome traces

**10.5.1.1** hmz MUST gather a Chrome trace of an epic from the epic's own records and from the logs
its sessions' CLIs wrote, selecting sessions by the identifiers the epic recorded and not by the
directory the epic executed in.

**10.5.1.2** A Chrome trace MUST place every session, every action of each session, and every
sub-agent on one timeline, grouped by agent.

**10.5.1.3** Where the epic has an environment profile, the Chrome trace MUST show each program as a
process on the same timeline and scale as the sessions; where the epic has a flow profile, the
Chrome trace MUST show it as one further process named `python`.

**10.5.1.4** A Chrome trace MUST record a summary of the agents, backends, sessions, slices, tracks
and time span it covers, and the number of programs where it shows any.

**10.5.1.5** Unless a path is given, hmz MUST write a Chrome trace of an epic inside that epic,
named after the UTC moment it was gathered, so that gathering twice keeps both (Section 6 of
[FILES]).

**10.5.1.6** hmz MAY gather a Chrome trace of sessions named by identifier, whole or as a prefix,
without an epic (Section 4 of [PYTHON]); naming no session MUST NOT be read as naming every session.

**10.5.1.7** hmz MUST accept a start and an end bounding a trace in any natural-language wording of
a time, MUST default them to the earliest and latest record, and MUST cut every session, program and
profile to that window.

**10.5.1.8** hmz MUST refuse, with an error, a trace bound it cannot read and an empty session
identifier.

**10.5.1.9** hmz MUST NOT fail a whole trace because the logs of one CLI are absent or unreadable.

**10.5.1.10** Two slices on one track of a Chrome trace at one depth MUST NOT overlap.

> Informative: Cursor Agent keeps no log a trace can read; its sessions are absent from traces.

#### 10.5.2. Profiling switches

**10.5.2.1** hmz MUST record an environment profile of an epic only where the epic was started with
`profile_environment` on (`--profile-environment` on `hmz exec`).

**10.5.2.2** hmz MUST record a flow profile of an epic only where the epic was started with
`profile_flow` on (`--profile-flow` on `hmz exec`).

**10.5.2.3** Each profiling switch MUST be an option of one epic, given as its budget is given; a
setting of a workspace MUST NOT turn either on for an epic started by `hmz exec` or the SDK.

**10.5.2.4** An epic MUST record which profiling switches it was started with, and an epic that
records neither MUST read back as profiled in neither way.

#### 10.5.3. Profiles

**10.5.3.1** Profiling MUST sample rather than intercept, and MUST NOT be able to stop or fail an
epic: a program that cannot be read, or a profile that cannot be written, MUST leave the epic as it
would otherwise have been.

**10.5.3.2** hmz MUST append an environment profile as each program is seen, and MUST NOT hold it
until the epic ends.

**10.5.3.3** hmz MUST time every profile against the same clock as the rest of the epic's trace.

**10.5.3.4** An environment profile MUST record, for each program, its process identifier, its
parent's process identifier, its name, its arguments, when it began, when it ended, and each of its
threads with when it began, when it ended and the CPU time it used.

**10.5.3.5** A flow profile MUST record the call stacks of the flow's own Python code from the
thread and task it executes in, leaving out the frames shared with where the epic was started, each
stack with its start time and duration, a frame being named by its function, file and line,
outermost first.

**10.5.3.6** A flow profile MUST merge consecutive samples of one stack into one record.

### 10.6. Exomyth timeline

#### 10.6.1. Content

**10.6.1.1** hmz MUST lay out an Exomyth timeline for any epic, executing or ended, from exactly
what a Chrome trace of that epic is gathered from, together with the epic's tree of flow calls and
its profiles.

**10.6.1.2** hmz MUST NOT write an Exomyth timeline to disk.

**10.6.1.3** An Exomyth timeline MUST hold one process of kind `flow` for the epic, first; then one
process of kind `flow` named `python` where the epic has a flow profile; then one process of kind
`session` per session that did anything, in order of start; then one process of kind `os` per
program of an environment profile, in order of start and then of process identifier.

**10.6.1.4** The epic's `flow` process MUST hold one span for the epic and one span for every flow
call, each inside the span of its caller.

**10.6.1.5** A flow call that has not returned, and an epic that has not ended, MUST be laid out as
ending at the last moment anything in the timeline did.

**10.6.1.6** A `session` process MUST hold one `session` span covering everything the session did,
and one span per action of the session under it, in the action's own category.

**10.6.1.7** An `os` process MUST hold one `process` span per thread; the `python` process MUST hold
one `sample` span per merged frame of the flow profile, named as the frame is.

**10.6.1.8** The parent of a sub-agent's process MUST be the session that started it; the parent of
a session the epic opened, of a sub-agent whose starter did nothing, and of the `python` process
MUST be the epic's `flow` process; the parent of a program's process MUST be the program that held
its parent process identifier when it started, where that program was profiled.

**10.6.1.9** A session process MUST name the role its agent filled, read from the epic's agents by
the agent's name, and MUST name no role where no agent of the epic has that name.

**10.6.1.10** An Exomyth timeline MUST hold one spawn edge from each action that started a session
to that session's process, and one from the flow call that opened each other session, or from the
epic's span where no flow call opened it, to that session's process.

#### 10.6.2. Document

**10.6.2.1** hmz MUST serve an Exomyth timeline as one JSON document holding exactly the keys
`version`, `layout`, `epic`, `origin`, `live`, `strings`, `processes`, `tracks`, `spawns` and
`summary` (Section 4 of [WEB]).

**10.6.2.2** `origin` MUST be the epoch seconds of the earliest moment of anything in the document,
and every time in the document MUST be whole microseconds since `origin`; every duration MUST be
whole microseconds and MUST NOT be negative.

**10.6.2.3** `live` MUST be true exactly while the epic has not ended.

**10.6.2.4** `strings` MUST hold every text the document states, each once, with the empty string at
index 0, and every other text field except a process's `kind` MUST be an index into `strings`.

**10.6.2.5** Every process MUST carry `id`, `kind`, `name`, `key`, `pid` (0 except for a program),
`start`, `end`, `parent` (a process `id`, or -1), `tracks`, `agent`, `role`, `backend`, `model`,
`label` and `record`.

**10.6.2.6** `tracks` MUST hold one track per lane of a process's spans, named after the process's
lane, with ` ~<n>` appended for the n-th further lane, each track carrying `process`, `name`,
`first`, `count`, `depths` and `spans`.

**10.6.2.7** `spans` of a track MUST be columns `start`, `dur`, `depth`, `cat`, `name`, `model`,
`in` and `out`, each `count` long and sorted by start; `in` and `out` MUST be the input and output
tokens a span reports, and 0 where it reports none.

**10.6.2.8** Two spans on one track at one depth MUST NOT overlap; where two spans start and end
together, a `session` span MUST hold a `turn` span and a `turn` span MUST hold every other span.

**10.6.2.9** A span's identifier MUST be its track's `first` plus its index in the track, numbering
every span of the document from 0 in track order with no gaps.

**10.6.2.10** `layout` MUST differ between two documents of one epic where a span identifier names a
span of a different process, track, start or category, and MUST be equal while spans only grow
longer.

**10.6.2.11** `spawns` MUST be columns `span` and `process`, sorted.

**10.6.2.12** `summary` MUST carry `start` (0), `end`, the counts of `processes`, `tracks` and
`spans`, and per category its `count`, its summed `time`, and its `in` and `out` tokens.

#### 10.6.3. Span details

**10.6.3.1** The document MUST NOT carry what each span carries beyond Section 10.6.2.7; hmz MUST
answer a span by identifier with its `id`, `process`, `track`, `start`, `dur`, `depth`, `cat`,
`name`, `at` (ISO 8601, UTC) and `args`.

**10.6.3.2** hmz MUST answer a span identifier from the last timeline laid out of that epic, and
MUST refuse an identifier that timeline does not have.

> Informative: the timeline is laid out fast enough that an epic of fifty thousand spans is
> drawn without a perceptible wait.

## 11. Backups

### 11.1. Scope

This section defines how **hmz** copies an **epic** off **this machine** and back: backing an
epic up to git repositories, by policy and by hand; listing and downloading the epics a backup
target holds; exporting an epic as one `.hmzepic` archive; and importing such an archive or a
downloaded epic as an epic of this machine.

Out of scope:

- The command-line syntax of `hmz backup`, `hmz exec --backup` and their exit statuses beyond what
  is stated here ([CLI]).
- The settings keys under which backup targets are kept (Section 3 of [FILES]).
- The layout of an epic directory and of the git clones hmz keeps (Section 6 of [FILES], Section 7
  of [FILES]).
- How a frontend offers export, import, backup and download ([TUI], Section 3 of [WEB]).
- Whether an imported epic can be picked up (Section 3.3.7.11).

### 11.2. Terminology

**11.2.1** **Backup target**: a git repository, named in this machine's settings, to which epics are
backed up; it has a **name**, a **URL**, a **branch**, zero or more **policies** and an **interval**
in minutes.

**11.2.2** **Default targets**: the backup targets settings names as those an epic is backed up to
where it names none.

**11.2.3** **Policy**: one of `session`, `interval` and `end`, each a condition under which an epic
is backed up without anyone asking (Section 11.3.3).

**11.2.4** **Backup**: one commit, pushed to a backup target's branch, holding one epic as files.

**11.2.5** **Epic key**: the path `<machine>/<workspace>/<epic>` at which a backup target holds one
epic, where `<machine>` is this machine's host name up to its first dot, every character outside
`A-Z`, `a-z`, `0-9`, `.`, `_` and `-` replaced by `-`, `<workspace>` is the name of the directory
under which hmz keeps the epics of the workspace, and `<epic>` is the epic name.

**11.2.6** **Bundle**: a gzip-compressed tar archive that holds exactly one epic as files, named
`<epic>.hmzepic` unless the user names the file otherwise.

**11.2.7** **Manifest**: the file `manifest.json` that a bundle and a backup hold beside the epic's
records, stating what the epic was (Section 11.4.2).

**11.2.8** **Credential scrubbing**: the replacement, by the literal text `[redacted]`, of every
credential Section 11.4.3 lists in every byte hmz writes into a bundle or a backup.

**11.2.9** **Import**: placing an epic read from a bundle or from a backup target among the epics of
this machine.

### 11.3. Backups

#### 11.3.1. Targets

**11.3.1.1** hmz MUST keep backup targets, and the default targets among them, as settings of the
**home** and not of any workspace.

**11.3.1.2** A backup target's name MUST be one to 32 characters of `A-Z`, `a-z`, `0-9`, `_` and
`-`, starting with a letter or digit.

**11.3.1.3** A backup target MUST have a non-empty URL.

**11.3.1.4** A backup target's branch MUST be `main` unless another is given.

**11.3.1.5** A backup target's interval MUST be a whole number of minutes of at least 1, and MUST be
30 unless another is given.

**11.3.1.6** A backup target with no policy MUST be backed up to by hand only.

**11.3.1.7** Writing backup targets MUST refuse, writing nothing, a target that violates Section
11.3.1.2 to Section 11.3.1.5, a policy other than those of Section 11.2.3, two targets of one name,
and a default target naming no target; writing them MUST leave every other setting unchanged.

**11.3.1.8** Reading backup targets MUST read an entry that is not a valid target as no target, and
a default naming no target as no default.

#### 11.3.2. Choosing targets

**11.3.2.1** An epic MUST be backed up to the targets it was started with: the default targets where
it was started with none named, and no target where it was started with an empty list (`--backup
none`).

**11.3.2.2** hmz MUST refuse to start an epic naming a backup target that settings does not hold.

**11.3.2.3** An epic MUST record the backup targets it was started with.

#### 11.3.3. Policies

**11.3.3.1** Under `session`, hmz MUST back an epic up each time one of its sessions closes.

**11.3.3.2** Under `interval`, hmz MUST back an epic up every interval of the target while the epic
executes.

**11.3.3.3** Under `end`, hmz MUST back an epic up once when it ends, whatever its ending.

**11.3.3.4** hmz MUST apply each policy whichever way the epic was started.

#### 11.3.4. Backing up by hand

**11.3.4.1** A backup by hand MUST go to the targets named, else to the targets the epic was started
with, else to the default targets.

**11.3.4.2** A backup by hand MUST be refused for a target settings does not hold, and for an epic
with no target to go to.

**11.3.4.3** `hmz backup <epic>` MUST wait for the backup to finish, MUST state for each target
whether it succeeded, naming the target's URL with any credential removed where it succeeded and the
error where it failed, and MUST exit 0 where every target succeeded, 1 where any failed, and 2 for
an epic or a target that does not exist or where there is no target.

**11.3.4.4** A frontend offering a backup by hand MUST return at once, and MUST then show how the
backup went as the epic records it.

**11.3.4.5** While `hmz backup` waits on a target -- backing up to it, listing it, or downloading
from it -- and standard error is a terminal and escapes are allowed (Section 4.2 of [CLI]), it MUST
draw a transient spinner there saying what it is doing and to which target, and MUST take it down
before it states how that went.

#### 11.3.5. Content and delivery

**11.3.5.1** A backup MUST hold exactly the files a bundle of the epic holds (Section 11.4.1),
scrubbed as a bundle is, under the epic key on the target's branch, laid out as files rather than as
an archive.

**11.3.5.2** A backup MUST be one commit whose message names the epic and the reason it was made:
`session`, `interval`, `end` or `manual`.

**11.3.5.3** A backup MUST start from what the remote branch holds, MUST create the branch where the
remote has none, and MUST try once more where the push is refused.

**11.3.5.4** hmz MUST NOT make a commit where nothing but the manifest of the epic changed since the
last backup.

**11.3.5.5** A backup MUST NOT carry the epic's own record of how its earlier backups went.

**11.3.5.6** hmz MUST reach a backup target only with this machine's own git and the credentials git
already uses, MUST NOT prompt anyone for anything, and MUST bound every git command by a timeout.

**11.3.5.7** Where git has no author identity configured, hmz MUST commit as `hmz <hmz@localhost>`.

**11.3.5.8** A backup MUST NOT delay the epic, any frontend or any other backup: each backup MUST be
queued and executed in the background, backups to one target MUST execute one at a time, and an epic
already queued for a target MUST NOT be queued for it a second time.

**11.3.5.9** Two processes on this machine MUST NOT back up to one target at the same time.

**11.3.5.10** A failed backup MUST be recorded in the epic and MUST NOT be raised to the epic or the
frontend.

**11.3.5.11** hmz MUST record in the epic, for each target, when its last backup was made, whether
it succeeded, why it failed with any credential removed, and why it was made, and MUST read this
back for every frontend.

**11.3.5.12** Once its epic has ended, `hmz exec` MUST wait at most 60 seconds for that epic's
queued backups, MUST state that it is waiting, and MUST state that a backup was left unfinished
where one was, without changing its exit status.

#### 11.3.6. Listing and downloading

**11.3.6.1** hmz MUST list the epics a backup target holds by fetching the target's branch, under
the same exclusion (Section 11.3.5.9), timeouts and absence of prompts (Section 11.3.5.6) as a
backup, and MUST read the list from the manifests there alone.

**11.3.6.2** A listed epic MUST state its epic key, its machine, the workspace it states it executed
in, its epic name, its flow, its task, when it began, when it ended, how it ended (empty where it
had not ended when backed up) and the commit its manifest states (Section 11.4.2.3).

**11.3.6.3** `hmz backup --list` MUST state, for each target named, else for every target, each epic
it holds on one line: machine, workspace, epic name, ending (`unfinished` where none) and task.

**11.3.6.4** Downloading an epic MUST import it exactly as importing a bundle does (Section 11.4.5),
with the same refusals, an epic this machine backed up and still holds counting as an epic already
here.

**11.3.6.5** A downloaded epic MUST record that it was imported from its epic key on its target,
naming the target's URL with any credential removed.

**11.3.6.6** hmz MUST refuse to download an epic key that is not three non-empty path segments, none
starting with `.` and none containing `\`.

**11.3.6.7** `hmz backup --pull <epic>` MUST download the epic, named by epic name or epic key, from
the first target named, else from the first target, that holds it, and MUST print where it now is.

**11.3.6.8** `hmz backup --pull` MUST state every target that cannot be reached, and MUST exit 1
unless the epic was downloaded from another target; an epic already here MUST exit 1.

**11.3.6.9** `hmz backup --pull` MUST be a usage error where every target answered and none holds
the epic, or where a target holds epics of that name from more than one machine.

### 11.4. Export and import

#### 11.4.1. Bundle content

**11.4.1.1** A bundle MUST hold, under one directory named after the epic, every record the epic
wrote, its flow state, its environment and flow profiles, and every trace gathered of it, each only
where the epic wrote one.

**11.4.1.2** A bundle MUST hold every log file of every session of the epic, under
`sessions/<session>/`, whether the epic keeps it or the CLI kept it elsewhere on this machine.

**11.4.1.3** A bundle MUST hold the screen transcript a frontend hands it, as `transcript.md`, and
none where none is handed.

**11.4.1.4** A bundle MUST hold a manifest.

**11.4.1.5** hmz MUST refuse to export a directory that holds no epic.

#### 11.4.2. Manifest

**11.4.2.1** The manifest MUST state the version of hmz, when the bundle was made, the version of
Python, the operating system and architecture, and the epic name.

**11.4.2.2** The manifest MUST state the epic's flow, task, beginning, end, ending (`left
unfinished` where none) and whether it is resumable.

**11.4.2.3** The manifest MUST state the workspace the epic executed in and, where that workspace is
a git repository, the commit it is on when the bundle or backup is made.

**11.4.2.4** The manifest MUST state each agent role's agent, model, effort and account, each env as
given and as used, and the tree of flow calls.

**11.4.2.5** The manifest MUST state, for each session, its agent, backend, account, identifier,
flow call and log files, and MUST state of a session whose CLI keeps no log files that there are
none to hold.

**11.4.2.6** The manifest MUST state, for each backend the epic used, its command, the executable
found, its version and the SHA-256 hash of that executable, each empty where it cannot be found.

**11.4.2.7** The manifest MUST list every file the bundle holds and the credential classes that were
scrubbed (Section 11.4.3).

#### 11.4.3. Credential scrubbing

**11.4.3.1** hmz MUST scrub every value of eight or more characters that any account on this machine
sets as an environment variable, except a value equal to the flow, or to a CLI, model, effort,
account or agent name, that the epic records it executed with.

**11.4.3.2** hmz MUST scrub keys in the formats vendors issue them, including those prefixed `sk-`,
`pk-`, `ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`, `github_pat_`, `glpat-`, `xai-`, `xoxb-`, `xoxp-`,
`hf_` and `AIza`, JSON Web Tokens and bearer tokens.

**11.4.3.3** hmz MUST scrub a user and password written into a URL, and the value of a URL query
parameter whose name denotes a token, key, secret, signature, password or credential.

**11.4.3.4** hmz MUST scrub the value of any JSON field or `name=value` pair whose name denotes a
token, secret, API key, password or credential.

**11.4.3.5** hmz MUST NOT scrub token counts, costs or model names.

#### 11.4.4. Writing a bundle

**11.4.4.1** hmz MUST write a bundle only to the path given: a file, or a directory into which it is
written as `<epic>.hmzepic`.

**11.4.4.2** hmz MUST write a bundle whole or not at all, and MUST leave nothing behind where
writing fails.

**11.4.4.3** A bundle MUST be readable and writable by the user who exported it alone.

**11.4.4.4** Exporting one epic again to the same path MUST replace the earlier bundle.

#### 11.4.5. Importing

**11.4.5.1** hmz MUST import only a file whose name ends in `.hmzepic`, that is a gzip-compressed
tar archive, and that holds exactly one top-level directory containing the epic's record and a
manifest.

**11.4.5.2** hmz MUST refuse a bundle holding anything but plain files and directories, a member
that would land outside the epic, an epic whose name is empty or starts with `.`, and an epic that
states no absolute workspace.

**11.4.5.3** hmz MUST refuse to import an epic already present on this machine.

**11.4.5.4** hmz MUST place an imported epic among the epics of the workspace it states it executed
in, whether or not that workspace exists on this machine.

**11.4.5.5** hmz MUST place each session's logs where the session states it is kept; a session that
was kept in another machine's CLI home MUST be placed in the epic, and its record MUST be rewritten
to state so.

**11.4.5.6** An imported epic MUST record that it was imported, from which file or epic key, and the
commit its manifest states.

**11.4.5.7** hmz MUST import whole or not at all, and MUST leave nothing behind where importing
fails.

## 12. Telemetry

### 12.1. Scope

This section defines the error reports **hmz** sends about itself: whether any report is sent,
when the **user** is asked, which events are reported, what a report holds, what a report never
holds, where reports go, and how reporting is turned on and off.

Out of scope:

- Exporting or backing up an epic, which the user does on purpose and which carries the epic's
  content (Section 11).
- Fetching the newest release and the price list, which send no data about the user (Section 13,
  Section 10.3.3).
- The settings key holding the answer (Section 3 of [FILES]).

### 12.2. Terminology

**12.2.1** **Report**: one message hmz sends to the reporting destination (Section 12.2.4).

**12.2.2** **Crash report**: a report of an error raised inside hmz.

**12.2.3** **Halt report**: a report that an epic executing in the reporting process went the halt
time (Section 12.2.9) without any event from any of its agents.

**12.2.4** **Reporting destination**: the Sentry project of the hmz maintainers, reached at
`o4511914126344192.ingest.us.sentry.io`.

**12.2.5** **Answer**: the user's reply to the question whether hmz reports errors: **yes**, **no**,
or **unanswered**.

**12.2.6** **Override**: the environment variable `HUMANIZE_SENTRY`.

**12.2.7** **Sent list**: the six statements of Section 12.4.1, in the wording given there.

**12.2.8** **Never-sent list**: the four statements of Section 12.4.2, in the wording given there.

**12.2.9** **Halt time**: 300 seconds.

### 12.3. Consent

#### 12.3.1. The answer

**12.3.1.1** hmz MUST keep the answer as a setting of the **home**, shared by every workspace, and
MUST read an absent setting as unanswered.

**12.3.1.2** hmz MUST NOT send any report while the effective answer is no or unanswered.

**12.3.1.3** Where the override is `on`, `1`, `true` or `yes`, ignoring case and surrounding space,
the effective answer MUST be yes for that process alone; where it is `off`, `0`, `false` or `no`, it
MUST be no for that process alone; the override MUST NOT write any setting.

**12.3.1.4** Where the override is absent or holds another value, the effective answer MUST be the
answer kept in settings.

#### 12.3.2. Asking

**12.3.2.1** The terminal interface MUST ask the question when it starts and the kept answer is
unanswered and no override applies, and MUST show the sent list and the never-sent list in the
question.

**12.3.2.2** Dismissing the question without choosing MUST leave the answer unanswered, so that the
question is asked again at the next start.

**12.3.2.3** Choosing yes or no MUST be kept as the answer and MUST start or stop reporting in that
process at once.

**12.3.2.4** `hmz exec`, the **daemon**, `hmz web` and SDK programs MUST NOT ask the question.

**12.3.2.5** The terminal interface and the web interface MUST each let the user change the answer
in their settings, and the terminal interface MUST show there the sent list and the never-sent list.

**12.3.2.6** Changing the answer to no in the terminal interface MUST stop reporting in that process
at once.

> Informative: reports already handed to the network can still arrive.

#### 12.3.3. Where reporting runs

**12.3.3.1** The terminal interface, `hmz exec` and the daemon MUST start reporting when they start,
where the effective answer is yes.

**12.3.3.2** Any other hmz process, an SDK program included, MUST start reporting no earlier than
the first report it makes or the moment the program asks for reporting (Section 4 of [PYTHON]), and
only where the effective answer is yes.

**12.3.3.3** A reporter that cannot start, information that cannot be gathered, and a report that
cannot be sent MUST each leave hmz and every epic behaving as they would without reporting.

#### 12.3.4. What is reported

**12.3.4.1** hmz MUST send a crash report for an error that ends an epic or `hmz exec`, and for an
error that nothing in hmz catches.

**12.3.4.2** hmz MUST NOT send a crash report for an error of the same type raised at the same line
of the same file as one already reported by that process.

**12.3.4.3** Where something in the reporting process is told the events of an epic's agents
(Section 4.5.3 of [PYTHON]), hmz MUST send a halt report once that epic has gone the halt time with
no such event, not counting time spent waiting on the **outworlder**, and MUST send at most one halt
report per epic.

**12.3.4.4** hmz MUST NOT send any report other than a crash report or a halt report: no report of a
logged message, no timing data, and no profiles.

### 12.4. Content

#### 12.4.1. What is sent

**12.4.1.1** A report MUST hold nothing beyond what the following list states, which hmz MUST show
in these words: "the error and where in Humanize it occurred"; "which flow was running, and what
each agent was configured to run"; "which coding agents are installed, and account names"; "which
skills and flowverses are active, by name"; "that a run went five minutes without any sign of
progress"; "the version of Humanize, of Python, and the operating system and architecture".

**12.4.1.2** A crash report MUST hold the error's type, its message after Section 12.4.3, and its
stack, each frame named as Section 12.4.4 defines.

**12.4.1.3** A crash report MUST hold what hmz was doing, `a flow` or `hmz exec`.

**12.4.1.4** A report MUST hold, where an **epic** is executing in the reporting process, the flows
executing with their depth, caller and seconds executed, and, for each **agent** role, the flow,
role, CLI, model, effort, account name, permission scopes and skill names.

**12.4.1.5** A report from the terminal interface MUST hold the Python version, the operating
system, the installed CLIs by name, each account by CLI, name and sign-in method, the skill names
each CLI would load, and each flowverse by name with whether it has been fetched.

**12.4.1.6** A halt report MUST hold how many seconds the epic went without an event, and what hmz
was doing, `a flow`.

**12.4.1.7** A report MUST hold the release of hmz that sent it.

#### 12.4.2. What is never sent

**12.4.2.1** hmz MUST show the following list in these words, and MUST NOT send anything it names:
"nothing you typed: no task, prompt, or command"; "no agent output, and nothing from any transcript
or session log"; "no files, directory names, or paths outside Humanize itself"; "no keys, tokens, or
account credentials -- not even environment variable names".

**12.4.2.2** A report MUST NOT hold the command line of the reporting process.

**12.4.2.3** A report MUST NOT hold the values of any variable of any stack frame, nor source lines
around a frame.

**12.4.2.4** A report MUST NOT hold the host name, the user's identity, the network address, logs,
breadcrumbs, the list of installed modules, or the working directory.

**12.4.2.5** A report MUST NOT hold the content of any account, nor the names of the environment
variables an account sets.

#### 12.4.3. Scrubbing

**12.4.3.1** In every string a report holds, hmz MUST replace a home-directory path prefix under
`/home/`, `/homes/` or `/Users/` by `~`.

**12.4.3.2** In every string a report holds, hmz MUST replace a user or password written into a URL
by `…`.

**12.4.3.3** In every string a report holds, hmz MUST replace by `…` every word that starts with
`sk`, `pk`, `ghp`, `gho`, `github_pat`, `xai`, `sk-ant` or `sk-proj`, followed by `-` or `_` and at
least eight further letters, digits, `_` or `-`.

**12.4.3.4** In every string a report holds, hmz MUST replace the command line a failed command
states of itself by `A command `.

**12.4.3.5** hmz MUST cut every string a report holds to 500 characters, followed by `…` where cut.

#### 12.4.4. Stack frames

**12.4.4.1** A frame in hmz's own package or in a library installed beside it MUST be named by its
path relative to that installation root, with its line number.

**12.4.4.2** A frame in any other file MUST be named `<not Humanize>` with its line number, and MUST
NOT state its file, module or function.

### 12.5. Destination

#### 12.5.1. Destination

**12.5.1.1** hmz MUST send reports to the reporting destination alone, and MUST NOT let any setting
change the destination.

**12.5.1.2** hmz MUST NOT send any report, or any part of one, to any other destination.

## 13. Updates

### 13.1. Scope

This section defines how **hmz** learns which release of itself is newest, how the terminal
and web interfaces tell the **user** that a newer release exists, and how `hmz update` moves the
installation of hmz to the newest release.

Out of scope:

- Updating installed flows from a flowverse ([TUI], Section 3 of [WEB]).
- The desktop app's own update (Section 3 of [DESKTOP]).
- The location of the kept release record (Section 7 of [FILES]).
- The command-line syntax of `hmz update` ([CLI]).

### 13.2. Terminology

**13.2.1** **Running version**: the version of hmz executing in the current process.

**13.2.2** **Newest release**: the newest release of the `hmz` package on PyPI that is not a
pre-release, as the `info.version` field of `https://pypi.org/pypi/hmz/json` states.

**13.2.3** **Release source**: where hmz asks for the newest release: the URL of Section 13.2.2, or
the URL or file named by the environment variable `HUMANIZE_RELEASES`.

**13.2.4** **Kept release**: the newest release as hmz last fetched it, kept for **this machine**.

**13.2.5** **Stale**: the state of the kept release when it is absent or was written more than 24
hours ago.

**13.2.6** **Newer release**: the kept release where it is greater than the running version by
version ordering; a running version of `0.0.0` or `unknown` has no newer release.

**13.2.7** **Installer**: the program that installed hmz: `uv tool`, `pipx`, `pip`, or uv's `pip`.

### 13.3. Learning the newest release

#### 13.3.1. Fetching

**13.3.1.1** hmz MUST fetch the newest release from the release source, and MUST NOT fetch it where
`HUMANIZE_RELEASES` is `off`, `0`, `no`, `none` or empty, ignoring case.

**13.3.1.2** A fetch MUST send no data about the user, the machine or any workspace beyond what an
HTTP request to the release source requires.

**13.3.1.3** A fetch MUST give up after 10 seconds, and MUST treat a source that does not answer, or
answers with no valid version, as having no newest release.

**13.3.1.4** A successful fetch MUST replace the kept release.

**13.3.1.5** A failed fetch MUST leave the kept release unchanged and MUST NOT raise an error to any
interface.

#### 13.3.2. Interfaces

**13.3.2.1** The terminal interface MUST, when it starts, fetch the newest release where the kept
release is stale, without delaying any input or drawing.

**13.3.2.2** The terminal interface MUST then state once in its transcript, where there is a newer
release, that the newer release is out and that `hmz update` updates to it.

**13.3.2.3** `hmz web` MUST, when it starts, fetch the newest release in the background where the
kept release is stale.

**13.3.2.4** The web interface MUST, while there is a newer release, mark this machine as having one
and offer `Update` in its menu, which copies `hmz update` for the user to run.

**13.3.2.5** An interface MUST NOT fetch the newest release more than once in 24 hours while the
previous fetch succeeded.

**13.3.2.6** An interface MUST NOT install a release itself.

### 13.4. `hmz update`

#### 13.4.1. Choosing the installer

**13.4.1.1** `hmz update` MUST choose the installer, and make the refusals of Section 13.4.2.1 to
Section 13.4.2.3, before it asks for the newest release.

**13.4.1.2** `hmz update` MUST then fetch the newest release, whether or not the kept release is
stale. While it fetches, where standard error is a terminal and escapes are allowed (Section 4.2 of
[CLI]), it MUST draw a transient spinner there saying that PyPI is being asked, and MUST take it
down once PyPI answers or cannot be asked.

**13.4.1.3** Where hmz was installed by `uv tool`, `hmz update` MUST run `uv tool upgrade hmz`.

**13.4.1.4** Where hmz was installed by `pipx`, `hmz update` MUST run `pipx upgrade hmz`.

**13.4.1.5** Where hmz was installed otherwise, `hmz update` MUST run `pip install --upgrade` with
the Python executing hmz, or uv's `pip install --upgrade` against that Python where pip is not
installed in it, naming `hmz` with every extra whose packages are all installed.

**13.4.1.6** `hmz update` MUST keep the extras hmz was installed with.

#### 13.4.2. Refusals

**13.4.2.1** `hmz update` MUST NOT run any installer, MUST state why, and MUST exit 1 where hmz is
not installed as a package.

**13.4.2.2** `hmz update` MUST NOT run any installer, MUST state why naming the source, and MUST
exit 1 where hmz was installed from a checkout or a URL rather than from PyPI.

**13.4.2.3** `hmz update` MUST NOT run any installer, MUST state why, and MUST exit 1 where the
installer Section 13.4.1 chose is `uv` or `pipx` and is not on `PATH`.

**13.4.2.4** `hmz update` MUST NOT run any installer, MUST state why, and MUST exit 1 where the
release source cannot be asked.

#### 13.4.3. Outcome

**13.4.3.1** Where the running version is already the newest release or newer, `hmz update` MUST
state so, MUST run nothing, and MUST exit 0.

**13.4.3.2** Before it runs the installer, `hmz update` MUST state the running version, the newest
release and the command it runs.

**13.4.3.3** Where the installer exits with a non-zero status, `hmz update` MUST state so and MUST
exit 1.

**13.4.3.4** Where the installer leaves a version other than the newest release installed, `hmz
update` MUST state the version left and MUST exit 1.

**13.4.3.5** Where the newest release is installed, `hmz update` MUST state so and MUST exit 0.

#### 13.4.4. Running processes

**13.4.4.1** `hmz update` MUST NOT stop, restart or signal any running hmz process, including a
**daemon**.

**13.4.4.2** Where a daemon holds the epics of this machine, `hmz update` MUST state, after a
successful update, that those epics run the release the daemon started under until the daemon stops.

> Informative: a process keeps executing the code it loaded; the new release takes effect in
> processes started after the update.

## 14. Security Considerations

This section states no requirement of its own. It names the properties stated elsewhere in this
document on which the security of a user's machine, credentials and work depends.

- hmz confines every harness except `litellm`, and every process the harness starts, to the grant
  of its role, and holds that grant whatever sandbox the harness itself enforces (Section 4.6.4.1
  and Section 4.6.4.10).
- A grant whose `online` is `NONE` cuts the network for the harness and its processes, except the
  hosts the harness and its account need for its model and its sign-in, which pass through a proxy
  on loopback; a session whose machine lacks the operating-system facility confinement needs is
  refused with `HarnessSandboxed` (Section 4.6.4.5 to Section 4.6.4.9).
- hmz puts no action of an agent to a person or model for approval unless a flow hangs a
  permission-request or ask-user hook, and a hook turns a grant into a denial but never a denial
  into a grant (Section 4.6.1.1 and Section 4.9.3.2).
- hmz never writes the system level of a harness, the user's real configuration of a harness, a
  managed item into the workspace, or a rung into a configuration file of the user (Section
  4.5.1.2, Section 4.5.1.6, Section 4.5.2.8 and Section 4.6.2.8).
- Credential files read through a virtual config home are the user's or the account's real files
  and are never copied into it (Section 4.5.2.9).
- Configuration in a workspace that runs a program is enumerated per harness, an unreadable or
  unparsable file of that enumeration counts as holding it, and it is honoured or refused as
  Section 6.7 states (Section 4.5.1.8 and Section 4.5.5).
- A harness that runs through a gateway is given the gateway's URL and own key and none of the
  account's variables, and the gateway's configuration and key are kept in a file only the user
  can read, never appear on a command line, and are removed with the gateway (Section 4.13.2.3
  and Section 4.13.2.4).
- On `codex`, a fake command line that runs outside Codex's sandbox does so only by a rule for its
  own name, and widens the sandbox of no other command (Section 4.6.2.9 and Section 4.10.2.8).
- The value of an account variable is never printed, displayed, logged or sent to a frontend page,
  and a secret typed at a way in is neither shown back nor placed on a command line (Section
  5.5.1.4, Section 5.11.1.1 and Section 5.11.1.2).
- Account directories and every file in them are readable and writable by the user alone from the
  moment they exist, and removing an account deletes its credential files (Section 5.4.2).
- A turn under an account reads and writes that account's credential files alone, is refused where
  they cannot be substituted, and never falls back to the harness's own sign-in or to another
  account's credentials (Section 5.3.2.3, Section 5.6.2.4, Section 5.6.2.5 and Section 5.11.1.3).
- A gateway's endpoint key reaches a harness only through a variable; it is written to no
  configuration file and no command line (Section 5.6.3.1 and Section 5.6.3.2).
- An account's credentials cross to another machine only under harness location env, where its
  variables travel as the turn's environment and its credential files sit in a directory only that
  machine's user can enter and are removed when the turn ends; under harness location standalone
  nothing of the account is sent, and commands an agent runs on an env machine never receive the
  account's variables (Section 5.7.1.3, Section 5.7.1.5 and Section 6.5.3).
- A refreshing sign-in is never refreshed in two places independently, and a turn that would do so
  is refused as `contended` (Section 5.7.2).
- A serving half is not a sandbox: it refuses paths outside its exports, unauthenticated peers and
  a token-less non-loopback listener, but confines neither the commands a request runs nor symbolic
  links leaving the exported tree; its token appears on no command line and a broker ticket is the
  whole of a peer's authentication (Section 6.10).
- What hmz starts on other machines carries labels naming the user, host and owning process, and
  hmz removes as leftovers only what names this user and this host; mirrors under harness location
  standalone remain in the harness machine's cache between turns (Section 6.6.1.3, Section 7.7.1.9
  and Section 7.12).
- A side question never reaches a session of the epic's flow, and every side conversation runs at
  the read-only permission level, modifies no file of the workspace, and is told to treat what it
  observes about the epic as data and not as instructions (Section 9.3).
- The btw agent reaches the sessions of an epic only through at most 4 asks per side question, and
  on `codex` only `hmz-ask` runs outside the sandbox, whose network stays cut (Section 9.6.4 and
  Section 9.6.13).
- A backup and a bundle hold the epic's records, profiles, traces and every session log, with the
  credentials of Section 11.4.3 replaced by `[redacted]`, and a bundle is readable and writable by
  the exporting user alone (Section 11.3.5.1, Section 11.4.1 and Section 11.4.4.3).
- A backup target is reached only with this machine's own git and the credentials git already
  uses, without prompting, and a credential in a target's URL is removed from what is stated and
  recorded (Section 11.3.5.6, Section 11.3.4.3 and Section 11.3.5.11).
- An import refuses a bundle holding anything but plain files and directories or a member that
  would land outside the epic, and a download refuses a malformed epic key (Section 11.4.5.2 and
  Section 11.3.6.6).
- No error report is sent unless the effective answer is yes, and reports go to the one reporting
  destination that no setting changes (Section 12.3.1.2 and Section 12.5.1).
- A report never holds what the user typed, agent output, transcripts, files or paths outside
  Humanize, credentials, environment variable names, the command line, frame variables, the host
  name or the user's identity, and its strings are scrubbed and cut (Section 12.4.2 and Section
  12.4.3).
- Fetching the newest release and the price list sends no data about the user, each is turned off
  by its environment variable, and no interface installs a release: `hmz update` runs only the
  installer that installed hmz (Section 13.3.1, Section 10.3.3.2, Section 13.3.2.6 and Section
  13.4.1).

## 15. References

### 15.1. Normative References

- **[RFC2119]** Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels", BCP 14, RFC
  2119, March 1997, <https://www.rfc-editor.org/info/rfc2119>.
- **[RFC5234]** Crocker, D., Ed., and P. Overell, "Augmented BNF for Syntax Specifications: ABNF",
  STD 68, RFC 5234, January 2008, <https://www.rfc-editor.org/info/rfc5234>.
- **[RFC7405]** Kyzivat, P., "Case-Sensitive String Support in ABNF", RFC 7405, December 2014,
  <https://www.rfc-editor.org/info/rfc7405>.
- **[RFC8174]** Leiba, B., "Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words", BCP 14, RFC
  8174, May 2017, <https://www.rfc-editor.org/info/rfc8174>.
- **[CLI]** "The Humanize Protocol: Command-Line Interface", [`cli.md`](cli.md).
- **[TUI]** "The Humanize Protocol: Terminal Interface", [`tui.md`](tui.md).
- **[DAEMON]** "The Humanize Protocol: Daemon", [`daemon.md`](daemon.md).
- **[WEB]** "The Humanize Protocol: Web Interface", [`web.md`](web.md).
- **[DESKTOP]** "The Humanize Protocol: Desktop Application", [`desktop.md`](desktop.md).
- **[PYTHON]** "The Humanize Protocol: Python Interfaces", [`python.md`](python.md).
- **[FILES]** "The Humanize Protocol: Settings, Environment Variables and Files", [`files.md`](files.md).

# Epics

## 1. Scope

This specification defines how **hmz** starts, identifies, limits, stops, ends, records and picks
up an **epic**: the loading of the **flow** the epic executes, the parameters and budget the epic
is given, the setup a **workspace** remembers between epics, the states in which an epic ends,
and how many epics execute at once in one workspace.

Out of scope:

- The grammar of flow references, of agent and environment specifications and of the budget
  flags (`api/cli.md`, `api/flows.md`).
- The layout and record format of an epic directory (`api/files/epics.md`).
- The settings file in which remembered setup is kept (`api/settings.md`).
- Where an agent's harness and an environment are placed, and fallback between runtimes
  (`features/placements.md`, `features/environments.md`).
- Which agents and accounts exist and how a turn is taken (`features/agents.md`,
  `features/accounts.md`).
- The `chat` flow and its conversation semantics (`features/chat.md`).
- Live figures, traces, profiles and notices of an epic (`features/monitoring.md`).
- Backups, export and import of an epic (`features/backups.md`).

## 2. Definitions

**2.1** **Epic name**: the identifier by which hmz names one epic.

**2.2** **Budget**: the set of limits under which an epic or a flow call executes, consisting of
one or more of a **cost limit** (US dollars), an **output-token limit** (tokens written by
agents) and a **duration limit** (wall-clock time), together with a **graceful** flag for each
limit.

**2.3** **Spent**: the cost, output tokens and seconds that the budget of an epic counted when
the epic ended.

**2.4** **Resumable flow**: a flow whose declaration states that an epic of it can be picked up
(`api/flows.md`).

**2.5** **Flow state**: the values a resumable flow writes for itself while an epic of it
executes (`api/flows.md`).

**2.6** **Picking up**: starting a new epic of a resumable flow from the flow state an earlier
epic of that flow left; the earlier epic is the **origin** of the new one.

**2.7** **Stopping**: a request, made by a **user** through a **frontend** or by a signal, that
an executing epic end before its flow returns.

**2.8** **Forcing**: a request, made while an epic is stopping, that every **session** of the
epic still in a turn be closed without waiting for the flow to unwind.

**2.9** **Remembered setup**: what a workspace keeps, per flow, of how that flow was last set up
through a frontend.

**2.10** **Ending**: the state in which an epic is read back, as §3.6 defines.

**2.11** **Host slot**: the slot (`api/daemon.md` §2.6) naming one host (`features/daemons.md` §2.1)
of a workspace on **this machine**: the workspace host's, or one chat host's.

**2.12** **Price list**: the list of per-token model prices kept on this machine
(`features/monitoring.md` §3.3).

## 3. Lifecycle

### 3.1 Starting

**3.1.1** hmz MUST start an epic only when a user or a program asks for one through `hmz exec`
(`api/cli.md`), a frontend (`features/tui.md`, `features/web.md`) or the SDK (`api/sdk.md`).

**3.1.2** hmz MUST refuse to start an epic whose flow cannot be found or loaded (§3.2).

**3.1.3** hmz MUST refuse to start an epic that is given a **role** the flow does not declare.

**3.1.4** hmz MUST refuse to start an epic that is given one role more than once.

**3.1.5** hmz MUST refuse to start an epic that leaves out a required role which hmz does not
fill itself.

**3.1.6** hmz MUST refuse to start an epic that is given a role which hmz fills itself: an
outworlder role or a local-environment role (`api/flows.md`).

**3.1.7** hmz MUST refuse to start an epic that is given an **agent** whose **harness** differs
from the harness its role names, or whose harness does not serve the capabilities its role
declares.

**3.1.8** hmz MUST refuse to start an epic that is given an agent or environment specification
that cannot be read, or that names a **runtime** which is not saved.

**3.1.9** hmz MUST refuse to start an epic that is given a parameter the flow does not declare,
or a parameter value that cannot be read as the declared type.

**3.1.10** hmz MUST refuse to start an epic that is given no budget, unless its flow is `chat`
(§3.4.2).

**3.1.11** hmz MUST refuse to start an epic that names a backup target which does not exist
(`features/backups.md` §3.2).

**3.1.12** hmz MUST refuse to start an epic that asks to pick up where §3.7.5 forbids it.

**3.1.13** hmz MUST make every refusal under §3.1.2 to §3.1.12 before any agent starts and
before any session opens, MUST state the reason, and MUST NOT create an epic directory for the
refused request.

**3.1.14** `hmz exec` MUST exit with status 2 for every refusal under §3.1.2 to §3.1.12.

**3.1.15** hmz MUST probe every **env** of the epic before the flow is called; where an env
cannot be reached or cannot hold what its role declares, and no fallback runtime holds it
(`features/environments.md`), hmz MUST refuse the epic with the reason before the flow is
called.

**3.1.16** hmz MUST create exactly one epic for each request that passes §3.1.2 to §3.1.12,
and MUST record in it the flow's canonical reference, the task, the workspace, each role's agent
and env as given, the env actually used for each role where it differs from the env given, the
parameters, the budget, the profiling switches, the backup targets and, where it picks up, its
origin (`api/files/epics.md`).

**3.1.17** hmz MUST call the flow with the task, every given agent and env, the workspace for
every local-environment role left out, and the epic's outworlder for every outworlder role left
out.

**3.1.18** An epic started by `hmz exec` MUST have an outworlder that is away, so that every
question its flow asks a person is answered as `api/flows.md` defines for an away outworlder.

**3.1.19** Starting an epic through `hmz exec` or the SDK MUST NOT change the remembered setup of
any workspace.

### 3.2 Loading the flow

**3.2.1** hmz MUST resolve the flow reference of an epic as `api/flows.md` defines, before the
epic is created.

**3.2.2** Where a flow reference resolves to nothing, hmz MUST state which of the following
holds: an index lists the flow but it is not installed; the reference uses a spelling no longer
accepted, together with the accepted spelling; a path lacks its leading `./`; an index that
could hold the flow has not been fetched.

**3.2.3** Where a flow fails while it is imported, hmz MUST refuse the epic and state the
failure's reason.

**3.2.4** hmz MUST load a flow as its files are when the epic starts; a change to those files
after the epic started MUST NOT affect that epic, and MUST take effect for the next epic that
loads the flow while no other epic of this process uses it.

**3.2.5** A flow named by a version-control reference MUST be fixed, for the whole epic, to the
commit the reference resolved to when the epic first fetched it.

### 3.3 Parameters

**3.3.1** hmz MUST hand the flow every parameter given, validated against the type the flow
declares for it, and the declared default for every parameter not given.

**3.3.2** hmz MUST reserve the parameter name `budget` for the budget, and MUST refuse a flow that
declares a parameter of that name.

### 3.4 Budget

**3.4.1** Every epic MUST execute under a budget that sets at least one limit, and a limit MUST NOT
be negative.

**3.4.2** An epic of the `chat` flow that is given no budget MUST execute under a budget whose
cost limit is unbounded.

**3.4.3** The graceful flag of each limit of a budget MUST be true unless it is given as false,
for that limit or for every limit.

**3.4.4** The cost and output tokens of every turn taken anywhere in an epic MUST count against
the budget of the epic and against the budget of every flow call above that turn.

**3.4.5** A duration limit MUST be a deadline counted from the start of the epic or flow call
whose budget it is, and MUST NOT be a sum over concurrent turns.

**3.4.6** The budget in force for a flow call MUST be the tighter, limit by limit, of the call's
own budget and what remains of every budget above it.

**3.4.7** The cost of a turn taken by a model that the price list does not price MUST count as
zero against a cost limit.

**3.4.8** Where an epic has a finite cost limit and an agent of the epic runs a model that the
price list does not price, hmz MUST state, before the first turn and without asking, that the
cost limit cannot stop what that model spends.

**3.4.9** Where an epic has a finite cost limit and the price list is missing or stale
(`features/monitoring.md` §3.3), hmz MUST attempt to refresh the price list before the first
turn, MUST wait no longer than that fetch's own timeout, and MUST stop waiting once the epic is
stopped.

**3.4.10** Where an epic has no finite cost limit and the price list is missing or stale, hmz
MUST refresh it without delaying the epic.

**3.4.11** Once a limit of a budget is reached, hmz MUST refuse every later turn under that
budget and MUST end the flow call that owns that budget.

**3.4.12** Where the graceful flag of a limit is true, hmz MUST let a turn under way when that limit
is reached finish before the owning flow call is ended.

**3.4.13** Where the graceful flag of a limit is false, hmz MUST interrupt a turn under way at the
moment that limit is reached.

**3.4.14** hmz MUST record an epic ended because a limit of its own budget was reached as
`stopped`, and MUST NOT record it as `failed`.

**3.4.15** `hmz exec` MUST state on standard error, in one line naming the limit, that its epic
was stopped by its budget, and MUST exit with status 0 in that case.

**3.4.16** hmz MUST record the spent figures of an epic when the epic ends.

**3.4.17** hmz MUST read back no spent figures for an epic that is executing or that ended
without recording them.

**3.4.18** Where pricing fails (`features/agents.md` §8.2.7) once the price list has been asked
for under §3.4.9 or §3.4.10, hmz MUST refuse the epic before its first turn, whatever its
budget, as a line refused (`hmz exec` exits with status 2).

**3.4.19** A turn whose pricing fails MUST count as an infinite cost; and where what an epic or
flow call has spent is not a finite number, hmz MUST refuse every later turn under it with
`CostExceeded`, whatever its budget.

### 3.5 Stopping and forcing

**3.5.1** Any frontend attached to the host slot of an executing epic MAY stop it.

**3.5.2** `hmz exec` MUST stop its epic on an interrupt, a terminate or a hangup signal.

**3.5.3** Stopping MUST interrupt every turn under way and MUST cancel the flow, which then
unwinds.

**3.5.4** As a stopped flow unwinds, hmz MUST close every session and env, and remove every
temporary directory, that the flow opened and has not handed to flow state.

**3.5.5** hmz MUST leave a file that an agent was writing when its turn was interrupted as it was
at the moment of interruption.

**3.5.6** Any frontend attached to the host slot of a stopping epic MAY force it.

**3.5.7** Forcing MUST close every session of the epic still in a turn, and MUST state how many
sessions it closed.

**3.5.8** `hmz exec` MUST exit with status 128 plus the number of the signal that stopped its
epic, and MUST exit only after the epic has closed everything it opened.

**3.5.9** hmz MUST record an epic ended by stopping or forcing as `stopped`.

**3.5.10** A frontend MUST NOT offer a stop for an epic of the `chat` flow; how a chat ends is
defined in `features/chat.md`.

### 3.6 Ending states

**3.6.1** hmz MUST read back every epic in exactly one of the endings `running`, `done`,
`failed`, `stopped` and `unfinished`.

**3.6.2** An epic MUST read back as `running` while it has recorded no end and a process on this
machine holds it.

**3.6.3** An epic MUST read back as `done` where its flow returned.

**3.6.4** An epic MUST read back as `failed` where its flow, or hmz on its behalf, raised an
error other than a stop or a budget exhaustion.

**3.6.5** An epic MUST read back as `stopped` where §3.4.14 or §3.5.9 applies.

**3.6.6** An epic MUST read back as `unfinished` while it has recorded no end and no process on
this machine holds it.

**3.6.7** hmz MUST NOT reopen an epic that has recorded an end, except as §3.7.9 provides.

**3.6.8** Where a frontend reports how the last epic of a host slot ended, it MUST distinguish an
epic refused before its flow was called, an epic ended by its budget, an error the flow raised
and an error inside hmz, and MUST state the reason for each.

**3.6.9** hmz MUST record, for every flow call within an epic, the task it was called with, when
it began, when it ended and how it ended, so that the epic reads back as the tree of flow calls
it made, however deep and however many executed concurrently.

**3.6.10** hmz MUST read back a flow call that ended by a cancellation from outside it, or by a
budget, as `stopped`.

**3.6.11** hmz MUST record, for every session an epic opened, which agent opened it, which flow
call opened it, the account and model its turns ran as, the identifier its harness gave it, the
session it was forked from where there is one, and where it is kept (`api/files/epics.md`).

### 3.7 Picking up

**3.7.1** Picking up MUST be available only for an epic of a resumable flow that recorded flow
state.

**3.7.2** hmz MUST keep the flow state of an epic inside that epic as the flow writes it, so that
the flow state is available to a later epic even where the process of the earlier epic was
killed.

**3.7.3** An epic that picks up MUST be a new epic with its own epic name, MUST record its
origin, and MUST start from a copy of the origin's flow state.

**3.7.4** Picking up MUST NOT change the origin.

**3.7.5** hmz MUST refuse to pick up, stating the reason, where the flow is not resumable as it
is now, where no epic of the flow in the workspace recorded flow state, or where the origin was
imported and §3.7.10 forbids it.

**3.7.6** `hmz exec --resume` MUST pick up the newest epic of the named flow in the current
workspace that can be picked up, and MUST use the agents, envs, parameters and budget given on
its own command line.

**3.7.7** On picking up, the top-level flow call MUST continue from the flow state; a nested flow
call MUST continue from the earlier call that had the same callee, task, agents, envs and
parameters, and MUST start afresh where there is none.

**3.7.8** A session written into flow state MUST be carried on, in the epic that picks up, from
its conversation as it was when it was written, subject to the conditions `api/flows.md` defines;
every other session MUST start fresh.

**3.7.9** What the origin spent MUST NOT count against the budget of the epic that picks up.

**3.7.10** An epic of the `chat` flow that is carried on MUST continue in the same epic rather
than a new one; that epic MUST record that it was opened again, MUST read back as `running`
until it ends again, and MUST read back as having spent the sum of what each opening spent.

**3.7.11** hmz MUST refuse to pick up an imported epic unless the workspace it executed in exists
on this machine at the same absolute path and, where that workspace is a git repository and the
epic recorded a commit, the repository holds that commit; the refusal MUST state which
condition failed.

## 4. Workspaces

### 4.1 Remembered setup

**4.1.1** A workspace MUST remember, per flow, the last setup saved for that flow through a
frontend: each agent role's agent, each env role's env, the parameters, the budget, the two
profiling switches and the backup targets.

**4.1.2** A workspace MUST remember which flow was last set up in it.

**4.1.3** A frontend MUST offer the remembered setup of a flow the next time that flow is set up
in the same workspace.

**4.1.4** Saving one part of a flow's setup MUST NOT erase the other parts of that flow's
remembered setup that the save does not give.

**4.1.5** A remembered empty list of backup targets MUST mean no targets, and no remembered
backup targets MUST mean the default targets.

**4.1.6** A remembered agent MUST consist of a harness, an account, a model and an effort, and
nothing else; a remembered entry that is not one MUST be read as nothing remembered.

**4.1.7** Remembered setup MUST NOT turn on either profiling switch for an epic started by
`hmz exec` or the SDK.

**4.1.8** Two frontends saving setup for one workspace MUST NOT overwrite each other's writes to
different entries.

### 4.2 Identity

**4.2.1** hmz MUST give every epic an epic name consisting of the UTC moment the epic was
created, to the millisecond, followed by a random suffix, such that epic names sort in the order
their epics were created.

**4.2.2** hmz MUST keep every epic under the workspace in which it executed
(`api/files/epics.md`).

**4.2.3** hmz MUST list the epics of a workspace in the order they were created.

**4.2.4** A frontend MUST address an executing epic by its epic name once the epic has one.

**4.2.5** hmz MUST read a directory among a workspace's epics that holds no epic record as no
epic, and MUST NOT fail to list the other epics because of it.

### 4.3 Concurrency

**4.3.1** At most one epic of a flow other than `chat` MUST execute at a time in a workspace's own
host slot.

**4.3.2** hmz MUST refuse a request to start an epic in a workspace's own host slot while another
epic executes or stops there.

**4.3.3** Any number of `chat` epics MAY execute in one workspace, each in a host slot of its own,
concurrently with the epic of the workspace's own host slot.

**4.3.4** An epic started by `hmz exec` MUST execute in the process of that command, and MUST NOT
be refused because another epic executes in the same workspace.

**4.3.5** Epics of different workspaces MUST execute independently of one another.

**4.3.6** hmz MUST report whether an epic is held by a process on this machine, whichever process
holds it.

> Informative: a frontend's request to start an epic goes to a host slot, held in a **daemon**
> where one runs (`features/daemons.md`); attaching and detaching a frontend does not affect the
> epic.

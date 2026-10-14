# Epics

## 1. Scope

This specification defines how **hmz** starts, identifies, limits, stops, ends, records and picks
up an **epic**: the loading of the **flow** the epic executes, the parameters and budget the epic
is given, the setup a **workspace** remembers between epics, the states in which an epic ends,
and the number of epics that MAY execute at once in one workspace.

Out of scope:

- The grammar of flow references, of agent and environment specifications and of the budget
  flags (`api/cli.md`, `api/flows.md`).
- The layout and record format of an epic directory (`api/files/epics.md`).
- Where an agent's harness and an environment are placed, and fallback between runtimes
  (`features/placements.md`, `features/environments.md`).
- Which agents and accounts exist and how a turn is taken (`features/agents.md`,
  `features/accounts.md`).
- The `chat` flow and its conversation semantics (`features/chat.md`).
- Live figures, traces and notices of an epic (`features/monitoring.md`).
- Backups, export and import of an epic (`features/backups.md`).

## 2. Definitions

**2.1** **Epic name**: the identifier by which hmz names one epic, unique within the
workspace in which the epic executed.

**2.2** **Budget**: the set of limits under which an epic executes, consisting of zero or more of
a **cost limit** (US dollars), an **output-token limit** (tokens written by agents) and a
**duration limit** (wall-clock time), together with a **graceful** flag.

**2.3** **Spent**: the cost, output tokens and seconds that the budget of an epic counted when
the epic ended.

**2.4** **Resumable flow**: a flow whose declaration states that an epic of it can be picked up.

**2.5** **Flow state**: the values a resumable flow writes for itself while an epic of it
executes, as defined in `api/flows.md`.

**2.6** **Picking up**: starting a new epic of a resumable flow from the flow state an earlier
epic of that flow left; the earlier epic is the **origin** of the new one.

**2.7** **Stopping**: a request, from a **user** or a **frontend**, that an executing epic end
before its flow returns.

**2.8** **Forcing**: a request, made while an epic is stopping, that every session of the epic
still in a turn be closed without waiting for the flow to unwind.

**2.9** **Remembered setup**: what a workspace keeps, per flow, of how the last epic of that flow
was set up through a frontend.

**2.10** **Ending**: the state in which an epic is read back once it is no longer executing, as
defined in §8.

**2.11** **Host slot**: one place on this **machine** where epics of one workspace execute on
behalf of frontends: the workspace's own slot, or one slot per chat.

## 3. Starting an epic

**3.1** hmz MUST start an epic when, and only when, a user or a program asks for one through
`hmz exec` (`api/cli.md`), a frontend (`features/tui.md`, `features/web.md`), or the SDK
(`api/sdk.md`).

**3.2** hmz MUST refuse a request to start an epic, before any agent starts and before any
session opens, where any of the following holds:

**3.2.1** The flow named cannot be found or cannot be loaded (§4).

**3.2.2** A role is given that the flow does not declare.

**3.2.3** A role is given more than once.

**3.2.4** A required role that hmz does not fill itself is not given.

**3.2.5** A role that hmz fills itself (an outworlder role or a local-environment role) is given.

**3.2.6** An agent is given whose harness differs from the harness its role names, or whose
harness does not serve the capabilities its role declares.

**3.2.7** An agent or environment specification cannot be read or names a runtime that is not
saved.

**3.2.8** A parameter is given that the flow does not declare, or whose value cannot be read as
the declared type.

**3.2.9** No budget limit is given, unless the flow is `chat` (§6.2).

**3.2.10** A backup target is named that does not exist (`features/backups.md`).

**3.2.11** Picking up is requested and §9.5 forbids it.

**3.3** Where a request is refused under §3.2, hmz MUST state the reason, and MUST NOT create an
epic directory.

**3.4** hmz MUST probe every environment of the epic before the flow is called; where an
environment cannot be reached or cannot hold what its role declares, and no fallback runtime
holds it (`features/environments.md`), hmz MUST refuse the epic with the reason before the flow
is called.

**3.5** Once the checks of §3.2 and §3.4 pass, hmz MUST create exactly one epic, MUST record in
it the flow's canonical reference, the task, the workspace, each role's agent and environment as
given, the environment actually used for each role where it differs, the parameters, the
budget, the profiling switches, the backup targets and, where picked up, the origin
(`api/files/epics.md`).

**3.6** hmz MUST call the flow with the task, with every given agent and environment, with the
workspace for every local-environment role, and with the epic's outworlder for every
outworlder role.

**3.7** An epic started by `hmz exec` MUST have an outworlder that is away, so that every
question the flow asks a person is answered as `api/flows.md` defines for an away outworlder.

**3.8** Starting an epic MUST NOT change the remembered setup of any workspace, unless the epic
is started through a frontend that saves the setup (§10.2).

## 4. Loading the flow

**4.1** hmz MUST resolve the flow reference of an epic as `api/flows.md` defines, before the
epic is created.

**4.2** Where a reference names nothing, hmz MUST state which of the following holds: the flow
is not installed although an index lists it; the reference uses a spelling that is no longer
accepted, together with the current spelling; a path lacks its leading `./`; an index that could
hold the flow has not been fetched.

**4.3** Where a flow fails while it is imported, hmz MUST refuse the epic with the failure's
reason.

**4.4** hmz MUST load the flow as it is on disk when the epic starts; a change to the flow's
files after an epic started MUST NOT change that epic, and MUST take effect for the next epic
that loads it.

**4.5** A flow fetched from a version-control reference MUST be fixed, for the whole epic, to
the commit the reference resolved to when it was first fetched in that epic.

## 5. Parameters

**5.1** hmz MUST hand the flow exactly the parameters given, each validated against the type the
flow declares for it, and the declared default for each parameter not given.

**5.2** `budget` MUST NOT be accepted as the name of a flow parameter; it is reserved for the
budget (§6).

## 6. Budget

**6.1** Every epic MUST execute under a budget that sets at least one of a cost limit, an
output-token limit and a duration limit, and no limit MUST be negative.

**6.2** An epic of the `chat` flow MUST execute under a budget whose cost limit is unbounded
where no budget is given.

**6.3** The graceful flag MUST default to true.

**6.4** The cost and output tokens of every turn taken anywhere in an epic MUST count against
the budget of the epic and against the budget of every flow call above that turn.

**6.5** A duration limit MUST be a deadline measured from the start of the epic or flow call it
belongs to, and MUST NOT be a sum over concurrent turns.

**6.6** The budget in force for a flow call MUST be the tighter of its own budget and what remains
of every budget above it.

**6.7** A cost incurred by a model for which no price is known MUST count as zero against a cost
limit.

**6.8** Where the epic has a finite cost limit and any agent of the epic runs a model for which
no price is known, hmz MUST state, before the first turn and without asking, that the cost limit
cannot stop what that model spends.

**6.9** Where the epic has a finite cost limit and the price list kept on this machine is missing
or older than one day, hmz MUST attempt to refresh it before the first turn, MUST NOT wait longer
than the fetch's own timeout, and MUST stop waiting once the epic is stopped; for any other epic
hmz MUST refresh a stale price list without delaying the epic (`features/monitoring.md` §5).

**6.10** Once a limit of a budget is reached, every later turn under that budget MUST be refused,
and the flow call that owns the budget MUST be ended.

**6.11** Where the graceful flag is true, a turn under way when its budget is spent MUST be
allowed to finish before the flow call is ended; where it is false, that turn MUST be interrupted
at once.

**6.12** An epic ended because a limit of its own budget was reached MUST be recorded as
`stopped`, and MUST NOT be recorded as `failed`.

**6.13** `hmz exec` MUST state, on standard error and as one line naming the limit, that its
epic was stopped by its budget, and MUST exit with status zero in that case.

**6.14** hmz MUST record the spent figures of an epic when it ends, and MUST read back no spent
figures for an epic that is still executing or that ended without recording them.

## 7. Stopping and forcing

**7.1** Any frontend attached to the host slot of an executing epic MAY stop it; `hmz exec` MUST
stop its epic on an interrupt, a terminate or a hangup signal.

**7.2** Stopping MUST interrupt every turn under way and MUST cancel the flow, which then unwinds;
sessions, environments and temporary directories the flow opened MUST be closed or removed as the
flow unwinds.

**7.3** A file an agent was writing when its turn was interrupted MUST be left as it was at the
moment of interruption.

**7.4** Any frontend attached to the host slot of a stopping epic MAY force it; forcing MUST
close every session still in a turn and MUST state how many sessions it closed.

**7.5** `hmz exec` MUST exit with status 128 plus the number of the signal that stopped it, and
only after the epic has closed everything it opened.

**7.6** An epic ended by stopping or forcing MUST be recorded as `stopped`.

**7.7** An epic of the `chat` flow MUST NOT be offered a stop by any frontend; how a chat ends
is defined in `features/chat.md`.

## 8. Ending states

**8.1** Every epic MUST be read back in exactly one of the following endings:

**8.1.1** `running`: the epic has recorded no end and a process on this machine holds it.

**8.1.2** `done`: the flow returned.

**8.1.3** `failed`: the flow raised an error other than a stop or a budget exhaustion.

**8.1.4** `stopped`: the epic was stopped or forced, or was ended by its budget.

**8.1.5** `unfinished`: the epic has recorded no end and no process holds it.

**8.2** Once an epic has recorded an end, hmz MUST NOT reopen it, except as §9.9 provides for
`chat`.

**8.3** A frontend reporting how an epic ended MUST additionally distinguish, among endings
other than `done` and `stopped`, an epic refused before its flow was called, an epic ended by
its budget, a failure the flow raised, and a failure inside hmz itself, and MUST state the reason
for each.

**8.4** hmz MUST record, for every flow call within an epic, the task it was called with, when
it began, when it ended, and how it ended, so that the epic reads back as the tree of flow calls
it made, however deep and however many executed concurrently.

**8.5** A flow call ended by a cancellation from outside it or by its budget MUST be read back
as `stopped`.

## 9. Picking up

**9.1** Picking up MUST be available only for an epic of a resumable flow that recorded flow
state.

**9.2** hmz MUST keep the flow state of a resumable epic inside that epic as it is written, so
that it is available to a later epic even where the earlier epic's process was killed.

**9.3** An epic that picks up MUST be a new epic with a new epic name, MUST record its origin,
and MUST start from a copy of the origin's flow state; the origin MUST NOT be changed.

**9.4** `hmz exec --resume` MUST pick up the newest epic of the named flow in the current
workspace that can be picked up, and MUST use the agents, environments, parameters and budget
given on its own command line.

**9.5** hmz MUST refuse to pick up, with the reason, where the flow is not resumable, where no
epic of the flow in this workspace recorded flow state, or where the origin was imported and
§9.10 forbids it.

**9.6** On picking up, the top-level flow call MUST continue from the flow state; a nested flow
call MUST continue from the earlier call with the same callee, task, agents, environments and
parameters, and MUST start afresh otherwise.

**9.7** A session written into flow state MUST be carried on, in the epic that picks up, from
the conversation as it was when it was written; every other session MUST start fresh. The
conditions under which such a session cannot be carried on are defined in `api/flows.md`.

**9.8** What the origin spent MUST NOT count against the budget of the epic that picks up.

**9.9** An epic of the `chat` flow MUST be carried on in the same epic rather than in a new one;
that epic MUST record that it was opened again, MUST read back as `running` until it ends again,
and MUST read back as having spent the sum of what each opening spent.

**9.10** hmz MUST refuse to pick up an imported epic unless the workspace it executed in exists
on this machine at the same absolute path and, where that workspace is a git repository and the
epic recorded a commit, that repository holds that commit; the refusal MUST state which
condition failed.

## 10. Remembered setup

**10.1** A workspace MUST remember, per flow, the last setup saved for that flow through a
frontend: the flow, each agent role's agent, each environment role's environment, the
parameters, the budget, the two profiling switches and the backup targets.

**10.2** A frontend MUST save the setup of a flow when its user saves that flow's setup, and
MUST offer the saved setup the next time that flow is set up in that workspace.

**10.3** Saving the agents of a flow MUST NOT erase its remembered environments, parameters,
budget, profiling switches or backup targets where those are not given in the same save.

**10.4** For backup targets, an empty list remembered MUST mean no targets, and nothing
remembered MUST mean the default targets.

**10.5** A remembered agent MUST consist of a CLI, an account, a model and an effort, and
nothing else; a remembered entry that is not one MUST be read as nothing remembered.

**10.6** The remembered setup MUST NOT turn on either profiling switch for an epic started by
`hmz exec` or the SDK; profiling MUST be an option of each epic (`features/monitoring.md` §7).

**10.7** Two frontends saving setup for one workspace MUST NOT overwrite what the other saved
for a different key.

## 11. Identity

**11.1** Every epic MUST have an epic name that encodes the UTC moment it was created, to the
millisecond, followed by a random suffix, such that epic names sort in the order the epics were
created.

**11.2** hmz MUST keep every epic under the workspace in which it executed (`api/files/epics.md`),
and MUST list a workspace's epics in the order they were created.

**11.3** A frontend MUST address an executing epic by its epic name once the epic has one.

**11.4** A directory under a workspace's epics that holds no epic record MUST be read as no epic,
and MUST NOT cause listing to fail.

## 12. Concurrency

**12.1** At most one epic of a flow other than `chat` MUST execute at a time in the workspace's
own host slot; a request to start a second MUST be refused while the first executes or stops.

**12.2** Any number of `chat` epics MAY execute in one workspace, each in a host slot of its own,
concurrently with the epic of the workspace's own host slot.

**12.3** An epic started by `hmz exec` without a daemon MUST execute in its own process and MUST
NOT be refused because another epic executes in the same workspace.

**12.4** Epics of different workspaces MUST execute independently of one another.

**12.5** hmz MUST report whether an epic is held by a process on this machine, whichever process
holds it.

> Informative: a frontend's request to start an epic goes to the host slot, held in a daemon
> where one runs (`features/daemons.md`); attaching and detaching a frontend does not affect the
> epic.

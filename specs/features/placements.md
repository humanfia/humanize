# Placements

## 1. Scope

This document specifies where the parts of a **session** run once the **env** it works in is
known: the four **placements** (local, supervised, native, afar), how **hmz** chooses one for
each session, what runs on which **machine** under each, the semantics and consistency
guarantees of a **mirror**, the rule for **workspace** configuration that makes a **harness**
run programs when the harness machine is not the env machine, which placements allow a
session to be kept and carried on, and the target spellings by which a machine is named.

Out of scope:

- What each env kind is, how it is started, sized, labelled and cleaned up:
  `features/environments.md`.
- The settings keys that hold a runtime's affinity and fields: `api/settings.md §3`.
- The per-harness list of configuration files and keys, accounts and fences of a harness:
  `features/agents.md`, `features/accounts.md`.
- The files hmz writes on a target machine and under the **home**: `api/files/targets.md`,
  `api/files/home.md`.
- How a flow declares envs and opens sessions: `api/flows.md`.
- The `-e` command-line grammar: `api/cli.md`.

## 2. Definitions

**2.1** **Session directory**: the directory on the env machine in which a session is opened:
the env's workdir, or a directory under it that the session names.

**2.2** **Target**: a string that names an env machine and the way hmz reaches it, as §9
defines.

**2.3** **Serving half**: the program hmz starts on, or connects to on, a target to carry out
the file operations, commands and outbound connections that a harness elsewhere asks for.

**2.4** **Affinity**: the ordered list of affinity entries saved with a **runtime**, which says
where the harness of a session whose env is on that runtime runs.

**2.5** **Affinity entry**: one of `local`, `self`, or `<backend>:<name>`, where `<backend>`
is one of `ssh`, `docker`, `swarm`, `apple-container`, `slurm` and `<name>` names a saved
runtime of that backend.

**2.6** **Harness runtime**: a runtime that an affinity entry `<backend>:<name>` names, opened
to hold harnesses rather than to be worked in.

**2.7** **Room**: the condition, defined per affinity entry in §4.2, under which an entry can
hold the harness of a session.

**2.8** **Gating hook**: a hook hung on a flow agent at the `PreToolUse` or
`PermissionRequest` moment (`api/flows.md`). A hook at the `AskUser` moment is not a gating
hook.

**2.9** **Program-running configuration**: the files and keys that `features/agents.md` §5.5.1
lists for a harness, found from the session directory.

**2.10** **Keep**: writing a session into a flow's state, which copies the session's
conversation (`api/flows.md`).

**2.11** **Carry on**: opening a session whose first turn continues a kept conversation.

**2.12** **Fork-in-place harness**: a harness that can fork a conversation only in the
directory in which that conversation was held (`features/agents.md`).

## 3. The four placements

### 3.1 Definition of each placement

**3.1.1** A session MUST have exactly one placement at any time.

**3.1.2** A session MUST have placement **local** where its env machine is this machine. Under
local placement the harness machine MUST be this machine, and hmz MUST NOT make a mirror.

**3.1.3** A session MUST have placement **supervised** where its env machine is not this
machine and its harness machine is this machine. Under supervised placement the harness MUST
work in a mirror on this machine.

**3.1.4** A session MUST have placement **native** where its harness is the harness program
installed on its env machine, that machine is not this machine, and no harness runtime holds the
harness. Under native placement hmz MUST NOT make a mirror.

**3.1.5** A session MUST have placement **afar** where its harness machine is the machine of a
harness runtime and is not this machine, whether or not it is the env machine. Under afar
placement the harness MUST work in a mirror on the harness machine.

**3.1.6** A session of a harness that starts no program of its own MUST have placement local.

> Informative: summary of §3.1 and §5.
>
> | | local | supervised | native | afar |
> | --- | --- | --- | --- | --- |
> | Harness program runs on | this machine | this machine | env machine | harness runtime |
> | Mirror | none | this machine | none | harness machine |
> | Commands the agent runs | this machine | env machine | env machine | env machine |
> | Harness's connections | this machine | this machine | env machine | harness machine |
> | Account used on | this machine | this machine | env machine | harness machine |

### 3.2 Platform requirements

**3.2.1** A supervised or afar session MUST be refused at the start of its first turn, with an
error that names the platforms on which it can run, where its harness machine is not Linux on
x86-64 or aarch64.

**3.2.2** An env machine of a supervised, native or afar session MUST provide a POSIX
`/bin/sh` and a Python of version 3.12 or later. hmz MUST NOT require root, a compiler, a
kernel module or an installed package on that machine.

**3.2.3** A native session MUST require the harness program to be installed on the env machine
and found on the `PATH` of the login hmz reaches it as, without
looking in any other directory.

## 4. Choosing a placement

### 4.1 General

**4.1.1** hmz MUST choose the placement of a session when the session is opened, before its
harness is started.

**4.1.2** hmz MUST choose one harness location per role and env machine: every session of one
role whose env is on one machine MUST get the same placement within one epic, except where
§4.3.1 distinguishes sessions by their gating hooks.

**4.1.3** A session whose env machine is this machine MUST have placement local, whatever
affinity applies.

**4.1.4** The affinity that applies to a session MUST be the affinity of the runtime its env
was actually opened on, which is the runtime the env fell back to where the env fell back
(`features/environments.md §11`). A session whose env is on no saved runtime MUST have no
affinity.

**4.1.5** hmz MUST walk only the affinity of §4.1.4. hmz MUST NOT walk the affinity, nor the
fallback list, of a harness runtime.

### 4.2 Walking an affinity

**4.2.1** hmz MUST try the entries of an affinity in their saved order, and MUST try an entry
only where every entry before it has no room.

**4.2.2** The entry `local` MUST always have room, and MUST give placement supervised.

**4.2.3** The entry `self` MUST give placement native, and MUST have no room where the env
machine has not got the harness program (`HarnessNotInstalled`) or cannot hold the session's
fence (`HarnessSandboxed`).

**4.2.4** An entry `<backend>:<name>` MUST give placement afar on the harness runtime it
names, and MUST have no room where that runtime is not saved, cannot be opened or reached
(`EnvUnavailable`, `EnvConnectionError`), has no share left to give (`ResourceUnmet`), or
where the role's permission fences anything at all (`HarnessSandboxed`).

**4.2.5** Where no entry has room, hmz MUST raise an error of the kind of the last refusal,
with the message `<where>: nowhere its affinity (<entries>) names has room for <cli>'s
harness; the last: <refusal>`, where `<where>` spells the env as `<backend>[@<provider>]`.

**4.2.6** Where an env machine cannot be asked whether it has the harness program or can hold a
fence, hmz MUST raise `HarnessUnrecoverable` at once and MUST NOT try the next entry.

**4.2.7** An affinity with no entries MUST be treated as no affinity (§4.3).

### 4.3 No affinity

**4.3.1** A session on another machine with no affinity that has a gating hook hung MUST have
placement supervised.

**4.3.2** A session on another machine with no affinity and no gating hook MUST have placement
native where the env machine has the harness program and can hold the session's fence, and
placement supervised otherwise.

**4.3.3** hmz MUST ask an env machine whether it has the harness program over the same connection,
`PATH` and login that a native turn there uses, and MUST treat a machine that does not answer
within 300 seconds as one that cannot be asked.

**4.3.4** hmz MUST ask each machine each question of §4.3.2 at most once per role and epic,
and MUST ask whether a fence can be held only for a session held to a fence that is not open.

### 4.4 Harness runtimes

**4.4.1** hmz MUST open a harness runtime at most once per epic and MUST share it among every
role whose affinity names it.

**4.4.2** hmz MUST open a harness runtime as an env with no role and no resources asked, in the
runtime's saved workdir; without one, in the login's home for an `ssh` runtime, and in an empty
directory of this machine's for a `docker` runtime whose daemon is on this machine or for an
`apple-container` runtime. A runtime of any other kind saved without a workdir MUST have no
room.

**4.4.3** hmz MUST start a container or swarm task opened as a harness runtime with the
`SYS_PTRACE` capability added.

**4.4.4** hmz MUST close every harness runtime it opened when the epic's envs are closed.

### 4.5 Settling placements before the flow runs

**4.5.1** Before calling the flow, hmz MUST walk the affinity of every env of the epic for
every agent role, the workspace included, under the role's declared permission, opening and
probing every harness runtime the walk reaches.

**4.5.2** Where that walk finds no room for some role, hmz MUST refuse the epic before the
flow is called; `hmz exec` MUST print `hmz exec: error: <message>` and exit with status 2.

**4.5.3** A session opened later MUST be given the placement settled under §4.5.1, and MUST
still be refused when it opens where its placement has no room.

### 4.6 Recording

**4.6.1** hmz MUST record with each session whose env is not on this machine where its harness
went: `local`, `self`, or the `<backend>:<name>` of the harness runtime (`api/files/epics.md`).

**4.6.2** hmz MUST record the empty string for a session whose env is on this machine.

## 5. What runs where

### 5.1 Programs and files

**5.1.1** Under supervised and afar placement, every program the agent starts MUST run on the
env machine, in the env machine's counterpart of the agent's working directory, except the
programs of §5.1.3.

**5.1.2** Under supervised and afar placement, every path the agent names inside the session's
workspace on the env machine MUST be answered from the env machine through the mirror, except
the paths of §5.1.3; every path outside it MUST be answered by the harness machine.

**5.1.3** The following MUST stay on the harness machine: the harness program and the
programs beside it in its own package, the interpreter it is started by, the harness's state
directories (`features/agents.md`), hmz's own directories under the user's home, and the
program that carries the flow's callbacks and command lines.

**5.1.4** A program the agent starts on the env machine MUST behave as a local child: it MUST
receive the agent's descriptors, its exit status MUST reach the agent, and its parent MUST be
released as soon as it starts.

**5.1.5** A command the agent starts MUST NOT report a success it did not achieve, and a
command started by an agent that is not a shell MUST receive an empty standard input on the
env machine.

**5.1.6** The common signals, `SIGINT` and `SIGTERM` among them, MUST travel both ways between
the agent and the commands it runs on the env machine.

**5.1.7** A program that hmz started for a session MUST NOT outlive the session.

**5.1.8** Under native placement the harness program, every program it starts and every file it
touches MUST be the env machine's.

### 5.2 Network

**5.2.1** The harness's own network connections MUST leave from the harness machine.

**5.2.2** The network connections of a command the agent runs MUST leave from the machine the
command runs on.

### 5.3 Accounts and credentials

**5.3.1** Under local and supervised placement, the account's variables and credential files
MUST be used on this machine, and MUST NOT be passed to the commands the agent runs on the env
machine.

**5.3.2** Under native placement, the account's variables MUST be given to the harness program as
the turn's environment, never on a command line, and the account's credential files MUST be put in a
directory on the env machine that only the target's own user can enter, for the turn alone, as
`features/accounts.md` specifies.

**5.3.3** Under afar placement, the harness MUST run as the harness machine's sign-in; hmz
MUST NOT send the account's variables or credential files to the harness machine.

### 5.4 The flow's callbacks

**5.4.1** A native turn whose env machine is not this machine MUST be refused where it is
offered the flow's own tool callbacks or command lines, unless its harness receives each
callback over the channel hmz drives it through.

### 5.5 Variables the agent is given

**5.5.1** Under supervised and native placement, hmz MUST set `HUMANIZE` to hmz's version,
`HUMANIZE_TARGET` to the target, and `HUMANIZE_WORKSPACE` to the absolute workspace path as
the env machine names it, in the harness's environment.

### 5.6 Fences

**5.6.1** Under supervised placement, a fence MUST be held on both machines: around the agent
on the harness machine, and around every command the agent runs on the env machine.

**5.6.2** Under native placement, a fence MUST be held around the harness program on the env
machine.

**5.6.3** Under afar placement, a session held to any fence that is not open MUST be refused
with `HarnessSandboxed`.

## 6. Mirrors

### 6.1 Location

**6.1.1** For an `ssh` env with placement supervised, the mirror MUST be at the path of the
env's workdir on this machine.

**6.1.2** For a `docker`, `swarm`, `apple-container` or `slurm` env with placement supervised,
the mirror MUST be under the home, in a directory of that container, service or job
(`api/files/home.md`), and MUST be removed when the env is closed.

**6.1.3** Under afar placement the mirror MUST be under the harness machine's own cache
directory, under a name derived from the workspace and the target, and MUST be kept between
turns (`api/files/targets.md`).

### 6.2 What the agent sees

**6.2.1** A supervised or afar agent MUST start in the session directory, named as the env
machine names it.

**6.2.2** A supervised or afar agent MUST see in the mirror the same names, contents, sizes,
modes and modification times at the same paths as the env machine has in the workspace.

**6.2.3** A failed operation on a path in the workspace MUST fail with the env machine's own
error.

**6.2.4** Every spelling the env machine has for a path MUST reach the same file.

**6.2.5** A file's contents MUST be fetched to the mirror no later than the first time the
agent opens it for reading.

### 6.3 Propagation and consistency

**6.3.1** Creating, removing, renaming and linking a file, and changing its mode, MUST take
effect on the env machine before the agent's call returns; the env machine's error MUST be the
agent's error.

**6.3.2** A file that a turn modified MUST reach the env machine before any command runs there
and again when the turn ends.

**6.3.3** The mirror MUST be authoritative for the env machine's contents: a file the env
machine lacks MUST be removed from the mirror, except a file written in the mirror and not yet
sent, which MUST be sent before anything the env machine says of it is applied.

**6.3.4** A change made in the workspace on the env machine by anything other than the agent's
own operations MUST become visible in the mirror no later than the completion of the next
command the turn runs on the env machine.

**6.3.5** Several turns working in one mirror at once MUST each see the files the others have
written, fetched, renamed and removed; a file one turn wrote MUST be sent by whichever turn
next sends, and MUST NOT be removed as one the env machine lacks.

**6.3.6** hmz MUST NOT refuse a turn because another turn is working in the same mirror.

**6.3.7** Where turns cannot share what they know of one mirror, each turn MUST work alone and
hmz MUST log `<mirror> cannot be shared with other turns working in it, which may then lose
what this one writes: <reason>`.

**6.3.8** Losing the connection to the env machine MUST NOT stop the agent: work that needs the
env machine MUST fail, files already in the mirror MUST stay readable, and the agent MUST exit
with its own status.

**6.3.9** A request to the env machine that receives no answer MUST be abandoned on the harness
machine.

> Informative: an abandoned request can still take effect on the env machine.

### 6.4 Limits

**6.4.1** hmz MUST carry file contents, file modes and file modification times between the
mirror and the env machine; hmz MAY leave ownership, device nodes, extended attributes and a
directory's own mode and times uncarried.

**6.4.2** Where another writer changes on the env machine a file that a turn writes, hmz MAY
leave either change in place; §6.3 makes no guarantee for such a file.

**6.4.3** A 32-bit process started under a supervised or afar agent MAY run against the mirror
with nothing it does carried to the env machine.

**6.4.4** Renaming or linking between a path in the workspace and a path kept on the harness
machine MUST fail.

### 6.5 Guarding a mirror directory

**6.5.1** hmz MUST refuse, with `FileExistsError`, to use as a mirror a directory that holds
files and was never a mirror, and one that was last a mirror of another target, unless the
caller forces it.

**6.5.2** hmz MUST refuse, with an `OSError` whose message begins `cannot keep the local copy
of the work at <path>`, a mirror path that is not a directory or cannot be created.

## 7. Workspace configuration across machines

**7.1** A harness MUST read project-level configuration from the env's workspace, as found from
the session directory, in every placement.

**7.2** A harness MUST read system-level and user-level configuration from the harness machine,
in every placement.

**7.3** Under local and native placement, hmz MUST let the harness honour program-running
configuration found in the env's workspace.

**7.4** Under supervised and afar placement, opening a session, forking a session into a
session directory, and carrying on a kept conversation in a session directory MUST raise
`UnsupportedOperation` where the env's workspace holds program-running configuration that the
harness would read as project-level.

**7.5** The error of §7.4 MUST name each file that holds such configuration and each key in it,
and MUST be raised before the harness is started.

**7.6** Under supervised and afar placement, hmz MUST make the check of §7.4 again before every
turn, and MUST refuse the turn with `UnsupportedOperation` where it finds such configuration.

**7.7** An afar placement whose harness machine is the env machine MUST be treated as local and
native are under §7.3.

**7.8** Where the env machine cannot be reached for the check of §7.4, hmz MUST raise
`HarnessDropped`.

**7.9** The files and keys that count as program-running configuration for each harness MUST be
those listed in `features/agents.md` §5.5.

## 8. Moving, forking, keeping and carrying on

### 8.1 Moving and forking

**8.1.1** A turn of a session working on another machine than the session's previous turn MUST
be refused with `UnsupportedOperation` on every harness, and the session MUST stay where it was.

**8.1.2** A turn of a session working in another workdir on the same machine MUST be refused
with `UnsupportedOperation`, except on a harness that forks into another directory, where the
conversation MUST continue as a fork of itself with a placement chosen for the new place under
§4.

**8.1.3** A fork of a session onto another machine MUST be refused with `UnsupportedOperation:
<cli> cannot fork a session onto another machine`.

### 8.2 Keeping and carrying on

**8.2.1** A session with placement local or supervised MUST be keepable, its conversation kept
on this machine.

**8.2.2** Keeping a session with placement native or afar MUST be refused with
`StateNotSerializable` before anything is written.

**8.2.3** Carrying on a kept conversation MUST be refused with `UnsupportedOperation` before the
harness is started where the turn's placement is native or afar.

**8.2.4** Carrying on a kept conversation on a fork-in-place harness MUST be refused with
`UnsupportedOperation` where the turn's placement is supervised in a mirror at a path other
than the workdir's own (§6.1.2).

**8.2.5** Carrying on a conversation kept by another harness MUST be refused with
`UnsupportedOperation`.

**8.2.6** A native or afar session's conversation MUST stay where that session's harness keeps it,
on its harness machine; hmz MUST copy what the session logs into the epic as it goes and whole
as it closes (`features/epics.md`).

## 9. Targets

### 9.1 Spellings

**9.1.1** A target MUST be one of the spellings of this section; any other MUST be refused with
`ValueError` naming every accepted spelling.

**9.1.2** `local` and `local:DIR` MUST name this machine, the latter with `DIR` standing in for
the env machine's copy of the workspace.

**9.1.3** `ssh://[USER@]HOST[:PORT][?KEYWORD=VALUE&...]` MUST name a host reached with the
system `ssh`. Each option MUST reach every `ssh` to that host as `-o KEYWORD=VALUE`, and the
option `F` as `-F VALUE`, ahead of hmz's own options. `KEYWORD` MUST match
`[A-Za-z][A-Za-z0-9]*`, and `VALUE` MUST be non-empty and MUST NOT hold a newline, carriage
return, NUL or `"`.

**9.1.4** Two `ssh://` targets at one host with different options MUST NOT share a connection.

**9.1.5** `docker://CONTAINER[?OPTIONS][@ENDPOINT]` MUST name a running container on the docker
daemon `ENDPOINT` names, docker's default when it names none or `local`. Every `docker` command
for a container on another endpoint MUST name that endpoint on its own command line and MUST
run without the variables that would send it elsewhere.

**9.1.6** The options of a `docker://` target MUST be only `user=UID[:GID]` (numeric, at most
once), `env=NAME=VALUE` (`NAME` matching `[A-Za-z_][A-Za-z0-9_]*`), and `exec=WORD` (non-empty),
`&`-separated and URL-quoted; any other MUST be refused with `ValueError`.

**9.1.7** Every command hmz runs in a `docker://` target's container MUST run as the `user`
given, with the `env` variables given, and under the `exec` words given in the order written,
where the words name a program that runs the command following them with the same streams and
exits with its status.

**9.1.8** A `docker://` target naming a `user` MUST keep hmz's files in that container in
directories named for that user, and MUST refuse one that is not a directory owned by that user
before anything is put in or run from it.

**9.1.9** `apple-container://CONTAINER` MUST name a running container of Apple's `container` on
this machine.

**9.1.10** `slurm://JOBID[?python=PATH]` MUST name the node of a running Slurm job of this
user's. Every command on it MUST be a step of that job sharing its allocation on its one node,
MUST receive nothing of this process's environment but `HOME` and `USER`, and MUST try the
Python at `PATH`, absolute or under `~/`, before any other.

**9.1.11** `tcp://HOST:PORT` MUST name a serving half listening at that address.

**9.1.12** `peer://TICKET@HOST:PORT` MUST name a serving half waiting at the broker at
`HOST:PORT` under `TICKET`.

**9.1.13** A `peer://` target given together with a harness machine other than this machine
MUST be refused with `ValueError`.

> Informative: hmz writes `peer://` targets itself when it places a harness afar; a user has no
> reason to write one.

### 9.2 Endpoints

**9.2.1** A docker endpoint MUST be one of `local`, `unix:///PATH`, `tcp://HOST:PORT[?tls=DIR]`,
`ssh://[USER@]HOST[:PORT][?KEYWORD=VALUE&...]` and `context:NAME`; any other MUST be refused with
`ValueError` naming every accepted spelling.

**9.2.2** A daemon reached by `local` where `DOCKER_HOST` names no non-`unix://` host, or by
`unix:///PATH`, MUST be treated as on this machine; every other MUST be treated as on another.

## 10. Serving a target

**10.1** A serving half MUST refuse a request naming a path outside every directory it was told
to export, and every request before a handshake it accepted.

**10.2** A serving half MUST refuse, and close the connection to, a peer speaking another
protocol version or presenting a token other than the one it was started with.

**10.3** A serving half MUST end every process and tunnel it started when its connection ends.

**10.4** A serving half MUST NOT be relied on as a sandbox: an export bounds which paths a
request names, and confines neither the commands a request runs nor a symbolic link out of the
exported tree.

**10.5** A serving half listening on a non-loopback address without a token MUST be refused.

**10.6** A token MUST NOT appear on any command line; a process hmz spawns with one MUST name a
file that only the user can read.

**10.7** A broker ticket MUST be unguessable, MUST be the whole of what authenticates a peer at
the broker, and MUST pair only the two halves presenting it.

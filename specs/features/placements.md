# Placements

## 1. Scope

This document specifies where the parts of a **session** run once the **env** it works in is
known: the two settings that say so, the **env location** and the **harness location**; how
**hmz** settles them for each session; what runs on which **machine** under each; the semantics
and consistency guarantees of a **mirror**; the rule for **workspace** configuration that makes
a **harness** run programs when the harness machine is not the env machine; which sessions may
be kept and carried on; and the target spellings by which a machine is named.

Out of scope:

- What each env kind is, how it is started, sized, labelled and cleaned up:
  `features/environments.md`.
- The settings keys that hold a runtime's harness setting and fields: `api/settings.md §3`.
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

**2.4** **Env location**: where a session's env machine is, as §3.1 defines: `local` or
`standalone`.

**2.5** **Harness location**: where a session's harness runs, as §3.1 defines: `local`, `env`
or `standalone`.

**2.6** **Harness runtime**: a runtime that a harness setting `<backend>:<name>` names, opened
to hold harnesses rather than to be worked in.

**2.7** **Harness setting**: the one value saved with a **runtime** that says where the harness
of a session whose env is on that runtime runs: `local`, `env`, or `<backend>:<name>`, where
`<backend>` is one of `ssh`, `docker`, `swarm`, `apple-container`, `slurm` and `<name>` names a
saved runtime of that backend.

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

**2.13** **Mirrored session**: a session whose harness location is `standalone`, or whose
harness location is `local` and env location `standalone`.

## 3. Env location and harness location

### 3.1 Definition of each

**3.1.1** A session MUST have exactly one env location and exactly one harness location at any
time.

**3.1.2** A session MUST have env location **local** where its env machine is this machine, and
env location **standalone** otherwise. A session with env location local MUST have harness
location local, and hmz MUST NOT make a mirror for it.

**3.1.3** A session MUST have harness location **local** where its harness program runs on this
machine. Where its env location is standalone, the harness MUST work in a mirror on this
machine.

**3.1.4** A session MUST have harness location **env** where its harness is the harness program
installed on its env machine, that machine is not this machine, and no harness runtime holds the
harness. hmz MUST NOT make a mirror for it.

**3.1.5** A session MUST have harness location **standalone** where its harness machine is the
machine of a harness runtime and is not this machine, whether or not it is the env machine. The
harness MUST work in a mirror on the harness machine.

**3.1.6** A session of a harness that starts no program of its own MUST have env location local.

> Informative: summary of §3.1 and §5.
>
> | Harness location / env location | local / local | local / standalone | env / standalone | standalone / either |
> | --- | --- | --- | --- | --- |
> | Harness program runs on | this machine | this machine | env machine | harness runtime |
> | Mirror | none | this machine | none | harness machine |
> | Commands the agent runs | this machine | env machine | env machine | env machine |
> | Harness's connections | this machine | this machine | env machine | harness machine |
> | Account used on | this machine | this machine | env machine | harness machine |

### 3.2 Platform requirements

**3.2.1** A mirrored session MUST be refused at the start of its first turn, with an error that
names the platforms on which it can run, where its harness machine is not Linux on x86-64 or
aarch64.

**3.2.2** An env machine of a session with env location standalone MUST provide a POSIX
`/bin/sh` and a Python of version 3.12 or later. hmz MUST NOT require root, a compiler, a
kernel module or an installed package on that machine.

**3.2.3** A session with harness location env MUST require the harness program to be installed
on the env machine and found on the `PATH` of the login hmz reaches it as, without looking in
any other directory.

## 4. Settling the harness location

### 4.1 General

**4.1.1** hmz MUST settle the harness location of a session when the session is opened, before
its harness is started.

**4.1.2** A session with env location standalone MUST have the harness location its harness
setting names: `local` gives harness location local, `env` gives harness location env, and
`<backend>:<name>` gives harness location standalone on the harness runtime it names.

**4.1.3** The harness setting that applies to a session MUST be that of the runtime its env was
actually opened on, which is the runtime the env fell back to where the env fell back
(`features/environments.md §11`). A runtime saved without a harness setting, and an env on no
saved runtime, MUST have the harness setting `env`.

**4.1.4** hmz MUST NOT read the harness setting, nor the fallback list, of a harness runtime.

### 4.2 Refusals

**4.2.1** Where the harness location that §4.1.2 gives cannot hold the harness, hmz MUST refuse
the session, and MUST NOT put the harness anywhere else.

**4.2.2** The harness setting `env` MUST be refused with `HarnessNotInstalled` where the env
machine has not got the harness program, with `HarnessSandboxed` where it cannot hold the
session's fence, with `HarnessUnrecoverable` where it cannot be asked either, and with
`UnsupportedOperation` where a gating hook is hung on the session.

**4.2.3** A harness setting `<backend>:<name>` MUST be refused where that runtime is not saved,
cannot be opened or reached (`EnvUnavailable`, `EnvConnectionError`), has no share left to give
(`ResourceUnmet`), or where the role's permission fences anything at all (`HarnessSandboxed`).

**4.2.4** The message of a refusal MUST begin `<where>: <cli>'s harness cannot run where its
harness setting (<setting>) says: `, where `<where>` spells the env as `<backend>[@<provider>]`.

**4.2.5** hmz MUST ask an env machine whether it has the harness program over the same
connection, `PATH` and login that a turn with harness location env there uses, and MUST treat a
machine that does not answer within 300 seconds as one that cannot be asked.

**4.2.6** hmz MUST ask each machine each question of §4.2.2 at most once per role and epic,
and MUST ask whether a fence can be held only for a session held to a fence that is not open.

### 4.3 Harness runtimes

**4.3.1** hmz MUST open a harness runtime at most once per epic and MUST share it among every
role whose harness setting names it.

**4.3.2** hmz MUST open a harness runtime as an env with no role and no resources asked, in the
runtime's saved workdir; without one, in the login's home for an `ssh` runtime, and in an empty
directory of this machine's for a `docker` runtime whose daemon is on this machine or for an
`apple-container` runtime. A runtime of any other kind saved without a workdir MUST be refused
under §4.2.3.

**4.3.3** hmz MUST start a container or swarm task opened as a harness runtime with the
`SYS_PTRACE` capability added.

**4.3.4** hmz MUST close every harness runtime it opened when the epic's envs are closed.

### 4.4 Settling harness locations before the flow runs

**4.4.1** Before calling the flow, hmz MUST settle the harness location of every env of the
epic for every agent role, the workspace included, under the role's declared permission,
opening and probing every harness runtime it names.

**4.4.2** Where that settling refuses some role, hmz MUST refuse the epic before the flow is
called; `hmz exec` MUST print `hmz exec: error: <message>` and exit with status 2.

**4.4.3** A session opened later MUST be given the harness location settled under §4.4.1, and
MUST still be refused when it opens where §4.2 refuses it.

### 4.5 Recording

**4.5.1** hmz MUST record with each session with env location standalone where its harness
went: `local`, `env`, or the `<backend>:<name>` of the harness runtime (`api/files/epics.md`).

**4.5.2** hmz MUST record the empty string for a session with env location local.

## 5. What runs where

### 5.1 Programs and files

**5.1.1** In a mirrored session, every program the agent starts MUST run on the
env machine, in the env machine's counterpart of the agent's working directory, except the
programs of §5.1.3.

**5.1.2** In a mirrored session, every path the agent names inside the session's
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

**5.1.7** A program that hmz started for a session MUST NOT outlive the session, unless it left
the session while the session ran: a program whose parent, or one of its parent's parents below
the harness program, exited before the harness program did MAY outlive the session.

**5.1.8** Under harness location env the harness program, every program it starts and every file
it touches MUST be the env machine's.

### 5.2 Network

**5.2.1** The harness's own network connections MUST leave from the harness machine.

**5.2.2** The network connections of a command the agent runs MUST leave from the machine the
command runs on.

### 5.3 Accounts and credentials

**5.3.1** Under harness location local, the account's variables and credential files
MUST be used on this machine, and MUST NOT be passed to the commands the agent runs on the env
machine.

**5.3.2** Under harness location env, the account's variables MUST be given to the harness
program as the turn's environment, never on a command line, and the account's credential files
MUST be put in a directory on the env machine that only the target's own user can enter, for the
turn alone, as `features/accounts.md` specifies.

**5.3.3** Under harness location standalone, the harness MUST run as the harness machine's
sign-in; hmz MUST NOT send the account's variables or credential files to the harness machine.

### 5.4 The flow's callbacks

**5.4.1** A turn with harness location env MUST be refused where it is
offered the flow's own tool callbacks or command lines, unless its harness receives each
callback over the channel hmz drives it through.

### 5.5 Variables the agent is given

**5.5.1** Under env location standalone and harness location local or env, hmz MUST set
`HUMANIZE` to hmz's version, `HUMANIZE_TARGET` to the target, and `HUMANIZE_WORKSPACE` to the
absolute workspace path as the env machine names it, in the harness's environment.

### 5.6 Fences

**5.6.1** Under harness location local and env location standalone, a fence MUST be held on both
machines: around the agent on the harness machine, and around every command the agent runs on
the env machine.

**5.6.2** Under harness location env, a fence MUST be held around the harness program on the env
machine.

**5.6.3** Under harness location standalone, a session held to any fence that is not open MUST
be refused with `HarnessSandboxed`.

## 6. Mirrors

### 6.1 Location

**6.1.1** For an `ssh` env and harness location local, the mirror MUST be at the path of the
env's workdir on this machine.

**6.1.2** For a `docker`, `swarm`, `apple-container` or `slurm` env and harness location local,
the mirror MUST be under the home, in a directory of that container, service or job
(`api/files/home.md`), and MUST be removed when the env is closed.

**6.1.3** Under harness location standalone the mirror MUST be under the harness machine's own
cache directory, under a name derived from the workspace and the target, and MUST be kept
between turns (`api/files/targets.md`).

### 6.2 What the agent sees

**6.2.1** The agent of a mirrored session MUST start in the session directory, named as the env
machine names it.

**6.2.2** The agent of a mirrored session MUST see in the mirror the same names, contents,
sizes, modes and modification times at the same paths as the env machine has in the workspace.

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

**6.4.3** A 32-bit process started under the agent of a mirrored session MAY run against the
mirror with nothing it does carried to the env machine.

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
the session directory, in every harness location.

**7.2** A harness MUST read system-level and user-level configuration from the harness machine,
in every harness location.

**7.3** In a session that is not mirrored, hmz MUST let the harness honour program-running
configuration found in the env's workspace.

**7.4** In a mirrored session, opening a session, forking a session into a
session directory, and carrying on a kept conversation in a session directory MUST raise
`UnsupportedOperation` where the env's workspace holds program-running configuration that the
harness would read as project-level.

**7.5** The error of §7.4 MUST name each file that holds such configuration and each key in it,
and MUST be raised before the harness is started.

**7.6** In a mirrored session, hmz MUST make the check of §7.4 again before every
turn, and MUST refuse the turn with `UnsupportedOperation` where it finds such configuration.

**7.7** A session with harness location standalone whose harness machine is the env machine
MUST be treated under §7.3 as a session that is not mirrored.

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
conversation MUST continue as a fork of itself with a harness location settled for the new place
under §4.

**8.1.3** A fork of a session onto another machine MUST be refused with `UnsupportedOperation:
<cli> cannot fork a session onto another machine`.

### 8.2 Keeping and carrying on

**8.2.1** A session with harness location local MUST be keepable, its conversation kept
on this machine.

**8.2.2** Keeping a session with harness location env or standalone MUST be refused with
`StateNotSerializable` before anything is written.

**8.2.3** Carrying on a kept conversation MUST be refused with `UnsupportedOperation` before the
harness is started where the turn's harness location is env or standalone.

**8.2.4** Carrying on a kept conversation on a fork-in-place harness MUST be refused with
`UnsupportedOperation` where the turn's harness location is local and env location standalone,
in a mirror at a path other than the workdir's own (§6.1.2).

**8.2.5** Carrying on a conversation kept by another harness MUST be refused with
`UnsupportedOperation`.

**8.2.6** The conversation of a session with harness location env or standalone MUST stay where
that session's harness keeps it, on its harness machine; hmz MUST copy what the session logs
into the epic as it goes and whole as it closes (`features/epics.md`).

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

> Informative: hmz writes `peer://` targets itself when it puts a harness on a harness runtime;
> a user has no reason to write one.

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

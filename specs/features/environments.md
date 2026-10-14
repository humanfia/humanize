# Environments

## 1. Scope

This document specifies the kinds of **env** hmz gives a **flow**'s env roles — `local`,
`ssh`, `docker`, `swarm`, `apple-container` and `slurm` — and the **runtimes** that name a
machine an env is put on: what each kind is, where its workdir is, how the resources a role
declares are checked or handed out, the names and labels hmz gives what it starts, the
lifecycle of starting, closing and cleaning up, falling back from one runtime to another, and
the errors raised.

Out of scope:

- Where the **harness** of a session working in an env runs, mirrors, and target spellings:
  `features/placements.md`.
- The settings keys under which runtimes are saved, and their types: `api/settings.md §3`.
- The `-e` command-line grammar and its parse errors: `api/cli.md`.
- The env protocol and mixins a flow writes against: `api/flows.md`.
- The files hmz writes under the **home** and on a target machine: `api/files/home.md`,
  `api/files/targets.md`.

## 2. Definitions

**2.1** **Kind**: one of `local`, `ssh`, `docker`, `swarm`, `apple-container`, `slurm`; the
backend an env is of.

**2.2** **Provider**: the name of the saved runtime an env is put on, or the empty string for
an env put on no saved runtime.

**2.3** **Default provider**: the machine an env of a kind with no provider is put on: this
machine for `local`; docker's default daemon on this machine for `docker`; the swarm this
machine manages for `swarm`; this machine's Apple containers for `apple-container`; the Slurm
cluster this machine submits to, with its defaults, for `slurm`. A label naming a default
provider MUST name it `local`.

**2.4** **Workdir**: the directory, as the env machine names it, that an env works in.

**2.5** **Declared resources**: the CPU count, memory, GPU count, GPU memory and image that an
env role declares through its mixins (`api/flows.md`).

**2.6** **Brought-up env**: an env of kind `docker`, `swarm`, `apple-container` or `slurm`,
for which hmz starts a container, a service or a job of its own.

**2.7** **Allocation**: the share of a runtime's resources that a brought-up env holds.

**2.8** **Derived env**: an env made from another one by a flow — a subdirectory, a temporary
copy, a scratch directory or a worktree (`api/flows.md`).

**2.9** **Owning process**: the hmz process that brought up a container, service or job.

**2.10** **Leftover**: a container, service or job whose labels name this user and this host
and whose owning process no longer exists.

## 3. Requirements common to every kind

### 3.1 Opening and probing

**3.1.1** hmz MUST NOT connect to an env machine, start a container or service, or submit a
job when it makes an env; it MUST do so when it first probes the env.

**3.1.2** hmz MUST probe every env of an epic, and every harness runtime its affinities reach
(`features/placements.md §4.4`), before any agent starts.

**3.1.3** hmz MUST bring up every env of an epic concurrently; the first refusal MUST stop the
rest, and where several are refused hmz MUST raise the refusal of the role that comes first in
declaration order.

**3.1.4** A probe MUST learn the env machine's home, its CPU count, its memory, its GPUs (as
`CUDA_VISIBLE_DEVICES` narrows them) and the smallest GPU's memory, and whether `git` and
`bash` are on the `PATH`.

### 3.2 Resources and capabilities

**3.2.1** For an env that is not a brought-up env, hmz MUST refuse a role whose declared
resources exceed what the probe found, with `ResourceUnmet: <flow>: '<role>' needs <n> <unit>,
and the environment given has <m>`, `<unit>` being `CPUs`, `bytes of memory`, `GPUs` or `bytes
of memory per GPU`.

**3.2.2** For a brought-up env, hmz MUST size or ask for the env by the declared resources as
the section of its kind says, and MUST refuse it with `ResourceUnmet` only where the runtime
cannot hand them out.

**3.2.3** An env MUST serve `GitEnvMixin` and `GitWorktreeEnvMixin` only where its probe found
`git` on the `PATH`, and `BashEnvMixin` only where it found `bash`; a role declaring a mixin its
env does not serve MUST be refused with `CapabilityMissing` before anything runs, naming the
missing program where `git` is the cause.

**3.2.4** An env MUST serve every other env mixin.

**3.2.5** An image a role declares MUST be ignored by every kind but `docker`, `swarm` and
`apple-container`, and by a `docker` env working in a running container (§7.3.4).

### 3.3 Commands

**3.3.1** Every command an env runs MUST run in a process group of its own with standard input
closed.

**3.3.2** A command that passes its timeout MUST be killed with its whole process group and
MUST raise `EnvCommandTimeout: <command> ran past its timeout of <n>s in <workdir>, and was
killed`.

**3.3.3** A command still running when its env is closed MUST be killed and MUST raise
`EnvError: <command> was killed: its environment was closed`.

### 3.4 Derived envs

**3.4.1** A derived env MUST be on the same machine as the env it was derived from, and MUST
share that env's connection.

**3.4.2** A derived env of a `local` or `ssh` env, and of a `slurm` env, MUST live under hmz's
home on the env machine (`api/files/home.md`, `api/files/targets.md`).

**3.4.3** A derived env of a `docker`, `swarm` or `apple-container` env MUST live inside that
env's container and MUST go with it.

### 3.5 Errors

**3.5.1** hmz MUST raise `EnvUnavailable` where an env machine or its workdir is not there or
cannot be brought up.

**3.5.2** hmz MUST raise `EnvConnectionError` where an env machine cannot be reached or the
connection to it breaks.

**3.5.3** hmz MUST raise `EnvFileNotFound` and `EnvPermissionDenied` where a path in an env is
missing or refused.

**3.5.4** hmz MUST raise `EnvError` for every other failure of an env.

**3.5.5** An error about an env on a saved runtime MUST name it `<kind>@<provider>`, and one
about an env on a default provider MUST name it `<kind>` alone.

## 4. Runtimes

### 4.1 What a runtime is

**4.1.1** A runtime MUST be a machine saved under a name — an ssh host, a docker daemon, a
docker swarm, this machine's Apple containers, or the Slurm cluster this machine submits to —
on which hmz puts an env when the env names it.

**4.1.2** A runtime MUST NOT be visible to a flow: an env put on a runtime MUST be the same env
protocol whatever runtime it is on.

**4.1.3** A runtime MUST be saved in the settings file (`api/settings.md §3`); its kind and its
name MUST be taken from where it is saved, whatever its entry says.

**4.1.4** A runtime's name MUST match `[A-Za-z0-9][A-Za-z0-9._-]*`.

### 4.2 Saving and reading

**4.2.1** hmz MUST refuse a runtime with `ValueError` when it is saved, never when it is used,
where any field fails its rule in this document or in `api/settings.md §3`.

**4.2.2** hmz MUST refuse to save a runtime under a name its kind already has, unless the save
replaces it.

**4.2.3** hmz MUST NOT list a runtime that cannot be read, and MUST refuse an env naming one
with `EnvUnavailable: the <kind label> '<name>' cannot be read; fix or remove it:
runtimes.<kind>.<name> in <settings file>`.

**4.2.4** An affinity entry or fallback entry naming a runtime nobody saved MUST be accepted when
saved, and MUST count as having no room, or as unable to hold the env, when used.

### 4.3 Affinity and fallback fields

**4.3.1** A runtime of every kind MUST accept an affinity, whose meaning is
`features/placements.md §4`. hmz MUST refuse an affinity entry that is none of `self`, `local`
and `<backend>:<name>`, one given twice, and one naming the runtime itself.

**4.3.2** A runtime of every kind MUST accept a fallback list of `<backend>:<name>` entries,
whose meaning is §11. hmz MUST refuse an entry of another shape, one given twice, and one
naming the runtime itself.

### 4.4 Checking a runtime

**4.4.1** Checking a runtime MUST never raise: it MUST answer whether the runtime was reached,
why not, and what it has — CPUs, memory, GPUs, the GPUs that answer, OCI runtimes and version
where the kind has them — and every way in which the runtime cannot hand out what it is saved
to hand out.

**4.4.2** Checking an ssh runtime MUST fail rather than wait where the host asks for a
password.

## 5. `local`

**5.1** A `local` env MUST be a directory on this machine, which MUST exist when the env is made;
otherwise hmz MUST raise `EnvUnavailable: there is no directory <path> on this machine`.

**5.2** A `local` env MUST take no provider and no affinity, and its sessions MUST have placement
local (`features/placements.md §3.1.2`).

**5.3** A `LocalEnv` role MUST be filled with the workspace the epic was started in; a `LocalEnv`
role given an env on another machine MUST be refused with `CapabilityMissing`.

## 6. `ssh`

**6.1** An `ssh` env MUST be a directory on a host reached with the system `ssh`, named either by
a saved ssh runtime or by a host nobody saved.

**6.2** An `ssh` env's workdir MUST be absolute, or under `~`, which MUST be the login's home.

**6.3** Every field of a saved ssh runtime that is set MUST reach every `ssh` to its host ahead
of hmz's own options; the host and port MUST form the destination, and the user, identity
file, jump host, configuration file and every other option MUST be passed as `ssh` options.

**6.4** hmz MUST NOT read or print what an identity file holds.

**6.5** An ssh runtime imported from an ssh configuration MUST name the configuration's `Host`
alias, never what it resolved to; re-importing it MUST keep its workdir, affinity and fallback
list, and MUST NOT overwrite a runtime that was typed rather than imported.

**6.6** An ssh runtime with neither a host nor an alias, with an option that has a field of its
own, or with a value holding a newline or `"` MUST be refused when saved.

## 7. `docker`

### 7.1 A container of its own

**7.1.1** A `docker` env whose runtime names no running container MUST be one container of its
own on the daemon its runtime names, started when the env is probed.

**7.1.2** The container MUST be started from the role's declared image, else the runtime's
image, else `python:3.12-slim`, and MUST need nothing in the image but `/bin/sh` and a Python
of version 3.12 or later.

**7.1.3** The workdir MUST be a directory of the daemon's host, mounted into the container at
its own path; hmz MUST refuse with `EnvUnavailable` a workdir the daemon's host has not got,
and MUST refuse a workdir under `~` on a daemon not on this machine.

**7.1.4** The container MUST run as this user on a daemon on this machine, as root inside a
rootless daemon on this machine, and as the owner of the workdir on the daemon's host
otherwise.

**7.1.5** The container MUST have `HOME=/tmp` set, and MUST see no GPU unless it was given
GPUs.

**7.1.6** The container MUST be given exactly the CPUs, memory and GPUs its role declares as
hard limits, no limit on a resource the role does not declare, and no GPU where the role
declares none.

**7.1.7** The container MUST be started with the runtime's OCI runtime and run arguments.

**7.1.8** The container MUST be named `<name_prefix>-<role>-<8 hex digits>` where the runtime
sets a name prefix, and `humanize-<provider>-<role>-<8 hex digits>` otherwise, `<provider>`
being `local` for a default provider; `-<role>` MUST be left out for an env of no role.

**7.1.9** The container MUST carry the labels `humanize=<uid>`, `humanize.cpus`,
`humanize.memory`, `humanize.gpus` (what it was given), `humanize.provider`, `humanize.role`,
`humanize.host` (this host's name) and `humanize.pid` (the owning process); hmz MUST NOT take
any of these from a label the caller gives.

**7.1.10** The container MUST be removed when the env is closed.

### 7.2 Allocation

**7.2.1** Before any agent starts, hmz MUST hold what the role asks against what the runtime is
saved to hand out — its saved CPUs, memory and GPUs, each the daemon's own where saved as zero
or empty, its GPU memory and its container limit — less what the runtime's running containers
hold, read off their labels.

**7.2.2** hmz MUST hand out GPUs as the first GPUs that no running container holds among those
of the daemon's host that answer when asked, each by the CDI name it answered under, else by
its UUID; where nothing can be asked, hmz MUST treat every GPU listed as answering.

**7.2.3** Two epics on this machine allocating from one runtime at once MUST NOT both be given
the same share.

**7.2.4** A shortage MUST raise `ResourceUnmet`, every shortage joined by `; `, each saying how
much of what is free and which container holds the rest.

> Informative: allocations made from different machines against one daemon are counted from
> the labels each finds, and can exceed the runtime's limits when made at the same moment.

### 7.3 A running container

**7.3.1** A `docker` env whose runtime names a running container MUST work in that container,
which hmz MUST NOT start, stop, remove, label or count against any limit.

**7.3.2** A runtime naming a running container MUST be refused when saved where it also sets an
image, an OCI runtime, run arguments, a name prefix, CPUs, memory, GPUs, GPU memory or a
container limit.

**7.3.3** A runtime naming a container that does not exist or is not running MUST raise
`EnvUnavailable: docker@<provider>: cannot work in the container <container>: <reason>`.

**7.3.4** The env's resources MUST be what the probe inside the container finds, and the role's
declared image MUST be ignored.

**7.3.5** The workdir MUST be a path inside the container, which hmz MUST NOT mount.

**7.3.6** Several envs and epics MUST be able to work in one running container at once, each
with mirrors of its own; closing an env MUST remove its own mirrors and nothing else.

### 7.4 Running as a user, with variables, under a wrapper

**7.4.1** Where a docker runtime sets an exec user `UID[:GID]`, exec variables `NAME=VALUE` or
exec wrapper words, every command hmz runs in an env's container on that runtime — the serving
half, a native harness CLI and every command an agent runs there — MUST run as that user, with
those variables, under those words.

**7.4.2** An exec user that is not `UID[:GID]`, an exec variable that is not `NAME=VALUE`, and
an exec wrapper word that is empty or spans lines MUST be refused when saved.

### 7.5 Runtime fields

**7.5.1** A docker runtime's endpoint MUST be one of `local`, `unix:///PATH`, `tcp://HOST:PORT`,
`ssh://[USER@]HOST[:PORT]`, `ssh:<name>` of a saved ssh runtime, and `context:<name>`; an
`ssh:<name>` endpoint MUST be dialled with every option of that ssh runtime.

**7.5.2** TLS certificates MUST be accepted only for a `tcp://` endpoint.

**7.5.3** A name prefix of a docker or swarm runtime MUST consist of letters, digits, `-` and
`_`, MUST start and end with a letter or a digit, and MUST be at most 54 characters; any other
MUST be refused when saved.

**7.5.4** Negative amounts of CPUs, memory, GPU memory or containers MUST be refused when saved.

### 7.6 Errors

**7.6.1** No `docker` on this machine MUST raise `EnvUnavailable: <where>: docker was not found
on this machine`.

**7.6.2** A daemon that does not answer MUST raise `EnvConnectionError: could not connect to
<where>: <reason>`.

**7.6.3** A container that does not start MUST raise `EnvUnavailable: <where>: could not start a
container of <image> on <endpoint>: <reason>`.

## 8. `swarm`

**8.1** A `swarm` env MUST be the one task of a service of its own, created on the swarm manager
its runtime names when the env is probed, never restarted, and removed when the env is closed.

**8.2** The service MUST be created from the image a `docker` env's container would be (§7.1.2),
with the workdir mounted at its own path on whichever node the task lands on; every node the
task can land on MUST have the workdir at that path.

**8.3** The task MUST run as this user where the manager is on this machine, and as the owner
of the workdir on the manager's host otherwise.

**8.4** The service MUST reserve exactly the CPUs and memory its role declares and be limited
to them, and MUST reserve as many of the runtime's GPU generic resource as the role declares
GPUs; a role declaring GPUs of a runtime naming no GPU resource MUST be refused with
`ResourceUnmet`.

**8.5** The service MUST be placed under the runtime's constraints, created with its run
arguments, and named and labelled as §7.1.8 and §7.1.9 name and label a container.

**8.6** Before any agent starts, hmz MUST hold what the role asks against the runtime's task
limit, and its CPUs and memory where saved, less what the runtime's services hold; a shortage
MUST raise `ResourceUnmet` as §7.2.4 says, and §7.2.3 MUST hold.

**8.7** A task no node takes for want of room MUST raise `ResourceUnmet` with the scheduler's
words: at once where no node able to take a task could ever hold it, and after 30 seconds
otherwise. The service MUST be removed first.

**8.8** A task that fails, or does not run within 600 seconds of being placed, MUST raise
`EnvUnavailable`, and its service MUST be removed.

**8.9** A manager that manages no active swarm, or is only a worker of one, and a node without
the workdir MUST raise `EnvUnavailable`.

**8.10** hmz MUST reach the task's container through the daemon the runtime names for that
node's host, else through the manager where the task landed on the manager, else over ssh to
the node's address.

**8.11** A swarm constraint MUST compare an attribute with `==` or `!=`; a GPU resource MUST be
one word; a node MUST be named by a saved ssh runtime or by `[user@]host[:port]`. Any other MUST
be refused when saved.

## 9. `apple-container`

**9.1** An `apple-container` env MUST be one container of Apple's `container` of its own on this
machine, started when the env is probed and deleted when it is closed.

**9.2** No `container` command on this machine MUST raise `EnvUnavailable`, and a container
system that does not answer or is not running MUST raise `EnvConnectionError`.

**9.3** The container MUST be started from the image a `docker` env's container would be
(§7.1.2), MUST run as this user, and MUST mount the workdir, a directory of this machine, at its
own path and at the other name macOS gives it under `/private` where it has one. A workdir
holding a comma MUST be refused.

**9.4** The container MUST be sized with the CPUs and memory its role declares, memory rounded up
to a whole MiB, and with `container`'s own size where the role declares none.

**9.5** A role declaring GPUs MUST be refused with `ResourceUnmet`.

**9.6** The container MUST be named as §7.1.8 says, with a name prefix never set, and labelled as
§7.1.9 says without `humanize.gpus`.

**9.7** Before any agent starts, hmz MUST hold what the role asks against the runtime's CPUs and
memory (this machine's where saved as zero) and its container limit, less the size of every
running container of the runtime; a shortage MUST raise `ResourceUnmet`, and §7.2.3 MUST hold.

> Informative: a harness cannot be supervised on macOS (`features/placements.md §3.2.1`), so a
> session in an Apple container needs `self` with an image holding the CLI, or a harness
> runtime, in the runtime's affinity.

## 10. `slurm`

**10.1** A `slurm` env MUST be one job of its own of one task on one node, submitted with
`sbatch` from this machine when the env is probed and cancelled when the env is closed.

**10.2** The job MUST be submitted under the runtime's partition, account, quality of service,
time, constraint and run arguments, each where set, and MUST ask for exactly the CPUs, memory
(rounded up to a whole MiB) and GPUs its role declares, nothing where the role declares none.

**10.3** The job MUST receive nothing of this process's environment but `HOME` and `USER`.

**10.4** The workdir MUST be the same path on this machine and on every node the job can land
on; hmz MUST NOT mount or copy it, and the role's declared image MUST be ignored.

**10.5** The job MUST be named as §7.1.8 says, and MUST carry in its comment the labels of §7.1.9
and `humanize.name`.

**10.6** hmz MUST reach the job's node by a step of the job per connection where the runtime's
way in is `srun`, and by a connection per session to a serving half that the job itself runs,
presenting a secret the job was given on no command line, where it is `tcp`; the runtime's
Python MUST be tried before any other on the node.

**10.7** Before any agent starts, hmz MUST hold what the role asks against the runtime's job
limit, and its CPUs and memory where saved, less what the runtime's jobs hold, waiting or
running; a shortage MUST raise `ResourceUnmet` as §7.2.4 says. §7.2.3 MUST hold until the job is
submitted and MUST NOT hold while the job waits for a node.

**10.8** A job still waiting once the runtime's maximum wait is over MUST be cancelled and MUST
raise `ResourceUnmet: <where>: job <id> was not given a node within <n>s: it is pending for
<reason>`; a maximum wait of zero MUST wait without limit.

**10.9** No `sbatch` on this machine, a job refused or ended before it ran, a `tcp` serving half
that does not say it is listening within 60 seconds, and a node without the workdir MUST raise
`EnvUnavailable`; a node that cannot be reached MUST raise `EnvConnectionError`.

**10.10** A partition, account or quality of service of more than one name, a time Slurm's
`--time` does not take, a constraint of more than one word, a Python neither absolute nor under
`~/`, and a way in other than `srun` and `tcp` MUST be refused when saved.

## 11. Falling back

**11.1** Where an env names a saved runtime that cannot hold it — opening is refused, probing
fails with `EnvUnavailable` or `EnvConnectionError`, or the runtime or its machine cannot give
what the role declares (`ResourceUnmet`) — hmz MUST try the runtimes of that runtime's fallback
list in order, until one holds the env.

**11.2** hmz MUST close every env refused on the way.

**11.3** hmz MUST NOT walk the fallback list of a runtime it fell back to.

**11.4** An env that names no saved runtime MUST have no fallback.

**11.5** An env moved to a fallback runtime MUST use that runtime's saved workdir, else the
workdir the env named.

**11.6** hmz MUST tell the user, on standard error under `hmz exec` and as a notice in a
**frontend**, `<kind>:<from> cannot hold '<role>': <reason>; using <kind>:<to>`.

**11.7** Where every runtime refuses, hmz MUST raise an error of the kind of the last refusal,
naming every runtime tried and why.

**11.8** hmz MUST record in the epic the env as named and, where they differ, the runtime each
role was put on (`api/files/epics.md`); an epic picked up again MUST be given the env as named.

## 12. Leftovers

**12.1** The next epic on this machine that allocates from a `docker`, `swarm`,
`apple-container` or `slurm` runtime MUST remove every leftover of that runtime, with its
mirrors, before it allocates.

**12.2** hmz MUST NOT remove a container, service or job whose labels name another user or
another host.

**12.3** hmz MUST NOT remove a running container that a docker runtime names, nor the mirrors of
an epic that worked in it and was killed.

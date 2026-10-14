# Target Files

## 1. Scope

This document specifies everything **hmz** creates on a **machine** that an **env** or a
**harness** is placed on, including **this machine** where an **env** runs on it: the state
directory, the directories derived from the working directory of an **env**, the bundle of
**hmz**, the **mirrors**, the containers, swarm services and Slurm jobs with their names and
labels, and the per-turn directories; and it states when each is removed.

Out of scope:

- The definitions and rules common to `api/files/`: `api/files/home.md` §2 and §3, and
  `api/files/machine.md` §2.
- How a **placement** chooses a **machine** and a **runtime**: `features/placements.md`.
- What an **env** offers a **flow**: `features/environments.md` and `api/flows.md`.
- The process-private temporary directories of a **harness** process:
  `api/files/harness-homes.md` §7.
- The **workspace** itself and its **repository**: `api/files/workspace.md`.

## 2. Definitions

**2.1** **Target**: a **machine** on which **hmz** places an **env** or a **harness**: an ssh
host, a docker or Apple container, a swarm service, a Slurm job, a server reached over TCP, or
**this machine**.

**2.2** **State directory** (`<state>`): on **this machine**, `<home>`; on an ssh host or a Slurm
node, `${HUMANIZE_HOME:-$HOME/.hmz}` as the login shell of the **user** there expands it, a
relative value taken under `$HOME`.

**2.3** **Bundle cache** (`<cache>`): the directory on a **target** that holds the bundle of
**hmz**: `$HOME/.cache/humanize` on an ssh host and on a Slurm node; `/tmp/humanize` in a
container; `/tmp/humanize-<user>` in a docker container whose **runtime** names the user
`<user>` to execute as.

**2.4** **Mirror root** (`<mirrors>`): the directory on a **harness machine** other than **this
machine** that holds **mirrors**: `$HOME/.cache/humanize-mirrors` on an ssh host and on a Slurm
node; `/tmp/humanize-mirrors` in a container; `/tmp/humanize-mirrors-<user>` in a docker
container whose **runtime** names the user `<user>`.

**2.5** **Workdir digest**: lowercase hexadecimal digits of a BLAKE2b digest of the absolute
path of a working directory.

## 3. The state directory

**3.1** `hmz` MUST create on a **target** only the entries this document and
`api/files/harness-homes.md` specify, besides the files the **agents** and the **flow** write as
their work.

**3.2** Where `HUMANIZE_HOME` is not set on an ssh host, `$HOME/.hmz` does not exist there and
`$HOME/.humanize` is a directory there, `hmz` MUST rename `$HOME/.humanize` to `$HOME/.hmz` when
it first probes that host.

**3.3** `hmz` MUST NOT create on a **target** other than **this machine** any entry of `<state>`
other than `envs/`.

**3.4** Where **hmz** writes a file on a **target** other than **this machine**, it MUST write it
into `<file>.humanize-<pid>-<n>.tmp` beside it, where `<pid>` is the serving process and `<n>` a
sequence number, and rename that file over it; a killed writer MAY leave such a file, and the
**user** MAY delete it at any time.

## 4. Directories derived from a working directory

**4.1** `<state>/envs/<name>-<digest>/`, where `<name>` is the last component of the working
directory of an **env**, truncated to 32 characters, and `<digest>` its workdir digest, MUST hold
everything **hmz** derives from that working directory on that **target**.

**4.2** `<state>/envs/<name>-<digest>/clones/<id>-<digest>/` MUST be a temporary copy of the
working directory, where `<id>` is the identifier the **flow** gives the copy, truncated to 40
characters, and `<digest>` a digest of that identifier.

**4.3** `hmz` MUST make a temporary copy in `<copy>.part.<pid>/` and rename it into place, and
MUST remove a `<copy>.part.<pid>/` whose `<pid>` no longer runs before it makes another copy in
the same directory.

**4.4** `hmz` MUST remove a temporary copy when the **flow** destroys it or the call that made it
ends, and MUST keep it where the **epic** is resumable and has not ended.

**4.5** `hmz` MUST remove a directory by renaming it to `<path>.part.gone.<random>.<pid>` and then
removing that.

**4.6** On **this machine**, `<copy>.lock` MUST be a file of mode `0644` on which the process
holding the temporary copy holds an exclusive advisory lock; `hmz` MUST remove it when the copy
is destroyed.

**4.7** `<state>/envs/<name>-<digest>/scratch/<id>-<digest>/` MUST be a scratch directory a
**flow** asks for, with the lifetime of clause 4.4.

**4.8** `<state>/envs/<name>-<digest>/worktrees/<ref>-<8 hexadecimal digits>/` MUST be a `git`
worktree a **flow** adds without naming its directory, where `<ref>` is the reference checked
out, truncated to 32 characters, or `head`; `hmz` MUST NOT remove it.

**4.9** The **user** MAY delete `<state>/envs/` while no **epic** uses it.

## 5. The bundle

**5.1** `<cache>/humanize-<digest>.pyz` MUST be the bundle of **hmz** of `api/files/machine.md` §5,
copied to the **target**.

**5.2** `hmz` MUST create `<cache>` where it is missing; in a docker container whose **runtime**
names the user to execute as, `hmz` MUST give `<cache>` mode `0700` and refuse a `<cache>` that
is a symbolic link or not owned by that user.

**5.3** `hmz` MUST write a bundle into `<path>.<pid>` and rename it into place, and MUST NOT
rewrite a bundle whose content matches its `<digest>`.

**5.4** `hmz` MUST update the modification time of the bundle each time it runs it.

**5.5** `hmz` MUST remove, each time it copies a bundle to a `<cache>`, every other entry of that
`<cache>` whose name begins with `humanize-` and contains `.pyz` and whose modification time is
more than 14 days ago.

**5.6** The **user** MAY delete `<cache>` while **hmz** is not running on that **target**.

## 6. Mirrors

**6.1** For an **env** in a container, a swarm service or a Slurm job, `hmz` MUST keep the
**mirror** of its working directory on **this machine** at
`<home>/envs/mirrors/<unit>/<workdir digest>/`, where `<unit>` is the name of the container,
service or job.

**6.2** `hmz` MUST remove `<home>/envs/mirrors/<unit>/` when it removes the container, service or
job, and when it finds the container, service or job of a process of the **user** on the same
host that no longer runs.

**6.3** For a **harness** whose **harness machine** is not **this machine**, `hmz` MUST keep the
**mirror** of the **workspace** at `<mirrors>/<sha16>/` on the **harness machine**, where
`<sha16>` is 16 lowercase hexadecimal digits of a SHA-256 digest of the **workspace**, the path
on the **env machine** and the **env machine**, and MUST name it to the **harness** process in
`HUMANIZE_SHADOW`.

**6.4** `hmz` MUST NOT remove a **mirror** of clause 6.3; the **user** MAY delete it while no
**harness** uses it.

**6.5** On every **harness machine** that holds a **mirror**, `hmz` MUST write the mirror records
of `api/files/machine.md` §9.

**6.6** A **mirror** MUST hold the files of the working directory it mirrors, and MAY hold, while
the content of a file is being fetched, a file `<file>.humanize-fetch`; `hmz` MUST NOT write any
other file of its own into a **mirror**.

**6.7** `hmz` MUST refuse to use as a **mirror** a directory that holds files and is not recorded
as a **mirror**, and a directory recorded as the **mirror** of another **machine**, unless the
**user** forces it.

## 7. Containers, services and jobs

**7.1** The name of a container, swarm service or Slurm job **hmz** creates for an **env** MUST
be `<name_prefix>-<role>-<8 hexadecimal digits>` where the docker or swarm **runtime** sets
`name_prefix`, and `humanize-<runtime>-<role>-<8 hexadecimal digits>` otherwise, where
`<runtime>` is the name of the **runtime** and `<role>` the **role** of the **env**.

**7.2** Each container, swarm service and Slurm job **hmz** creates MUST carry the labels
`humanize=<uid>`, `humanize.provider=<runtime>`, `humanize.role=<role>`,
`humanize.host=<host name of this machine>` and `humanize.pid=<process identifier>`, and
`humanize.cpus`, `humanize.memory` and `humanize.gpus` where the **env** sets them;
an Apple container MUST NOT carry `humanize.gpus`.

**7.3** A Slurm job MUST carry its labels, and `humanize.name=<job name>`, URL-encoded in its
comment.

**7.4** A docker container **hmz** creates for an **env** MUST mount only the working directory
of the **env**, at the same path, and MUST run with `HOME=/tmp`, and with
`NVIDIA_VISIBLE_DEVICES=void` where no GPU is handed to it.

**7.5** `hmz` MUST remove a container, swarm service or Slurm job it created when the **env** it
serves closes, and when it finds that the process named by its `humanize.pid` on the host named
by its `humanize.host` no longer runs.

**7.6** `hmz` MUST create a container named `humanize-gpus-<8 hexadecimal digits>` and a container
probing the owner of the working directory only with automatic removal on exit, each labelled
`humanize=<uid>`.

**7.7** A Slurm job submitted for an **env** reached over TCP MUST write its output to
`/tmp/humanize-slurm-<job id>.out` on its node; `hmz` MUST NOT remove that file.

**7.8** `hmz` MUST NOT write a batch script file for a Slurm job.

## 8. Per-turn directories

**8.1** For each turn of a **harness** that runs natively on a **target** other than **this
machine** under an **account** whose credential files are in its harness home, `hmz` MUST create
on that **target**, with umask `077`, a directory by `mktemp -d` in the temporary directory of
the **target**, and MUST give it mode `0700`.

**8.2** The directory of clause 8.1 MUST hold each credential file of the **account** at
`<variable>/<path>`, where `<variable>` is the lowercase name of the harness home variable and
`<path>` the path of the file under that home, each with mode `0600`; `hmz` MUST name the
directory to the **harness** in that variable and in `XDG_CONFIG_HOME`.

**8.3** `hmz` MUST remove the directory of clause 8.1 when the turn ends, and MAY leave it where
the connection to the **target** is lost.

**8.4** For a fenced **harness** process on a **target** other than **this machine**, `hmz` MUST
create its temporary directory at the path of `api/files/harness-homes.md` clause 7.8 on the
**target**, with mode `0700`, and MUST NOT remove it.

**8.5** For a fenced **harness** process, `hmz` MUST create, with mode `0700`, each missing
directory of the home directory of the **user** that the fence lets the process write and whose
name has no `.`, and MUST NOT remove it.

## 9. Lifetimes after an epic

**9.1** `hmz` MUST NOT leave, after an **epic** ends, any container, swarm service or Slurm job
it created for that **epic**, any `<home>/envs/mirrors/<unit>/` of it, or any per-turn directory
of §8.1, except as clauses 6.2 and 8.3 permit.

**9.2** After an **epic** ends, `hmz` MUST leave on a **target** only these entries of its own:

- the temporary copies and scratch directories of a resumable **epic** (clauses 4.2 and 4.7);
- the worktrees of clause 4.8;
- `<cache>` and the bundles in it (§5);
- the **mirrors** of clause 6.3 and their records;
- the Slurm output files of clause 7.7;
- the directories of clauses 8.4 and 8.5;
- the residue files of clause 3.4.

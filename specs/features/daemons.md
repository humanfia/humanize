# Daemons

## 1. Scope

This document specifies the daemon as the user experiences it: one daemon per machine and user,
holding the epics of every workspace on that machine apart from any terminal; how it starts and
goes; how frontends attach to and detach from the epics it holds; how epics outlive the frontend
that started them; how a daemon of one release meets a frontend of another; and how a frontend
reaches the daemon of another machine over ssh.

Out of scope:

- The protocol between frontends and the daemon, its messages and its requests: `api/daemon.md`.
- The files the daemon keeps on this machine: `api/files/machine.md`.
- The settings the remote daemons are kept in: `api/settings.md`.
- What a chat is, and how a chat folds away: `features/chat.md`.
- How the page of `hmz web` presents daemons: `features/web.md` §13.
- How the terminal interface presents daemons and `/exit`: `features/tui.md`.
- The release check and `hmz update`: `features/updates.md`.

## 2. Definitions

**2.1** A **host** is what holds the epics of one workspace, or of one chat of a workspace, for
every frontend attached to them. A host held by the daemon is held apart from every frontend.

**2.2** The **workspace host** of a workspace is the host that runs that workspace's flows. A **chat
host** is a host that runs one chat of a workspace, beside the workspace host.

**2.3** A frontend **attaches** to a host when it starts reading and steering the epics that host
holds, and **detaches** when it stops, without stopping them.

**2.4** A host is **idle** when no frontend is attached to it, no epic is going, starting or
stopping on it, and it keeps no ended epic for the next frontend under §5.5.

**2.5** A daemon is **older** than a frontend when it speaks a protocol of an earlier release of
hmz than the frontend, and **newer** when it speaks a protocol of a later one.

**2.6** A **remote daemon** is the daemon of another machine, reached from this machine over ssh. A
remote daemon is called an SSH daemon on the page of `hmz web`.

**2.7** **Local** is the daemon of this machine, as the frontends that switch between daemons name
it.

## 3. One daemon per machine and user

**3.1** There MUST be at most one daemon per machine and user.

**3.2** The daemon MUST hold the epics of every workspace of its machine and user.

**3.3** The daemon MUST hold one workspace host per workspace, and one chat host per chat beside it;
each host MUST run in a process of its own, standing in its workspace.

**3.4** A chat host and the workspace host of one workspace MUST NOT wait on each other; how many
epics each runs at a time is stated in `features/epics.md` §4.3.

**3.5** Two spellings of one directory MUST name one workspace, and two directories MUST name two
workspaces.

**3.6** The daemon MUST belong to the machine it runs on, and MUST NOT be shared between machines
that mount one home.

**3.7** Two frontends racing to start the daemon, or a host of one workspace, MUST end with one
daemon, or one host, which both use.

## 4. Starting

**4.1** The daemon MUST start when the first frontend that holds epics apart from itself needs it,
and MUST NOT need to be started by the user.

**4.2** The terminal interface MUST hold epics apart from itself only where both its standard input
and its standard output are a terminal and `HUMANIZE_DAEMON` is not `off`, `0` or `no`; otherwise it
MUST hold them in its own process, and closing it MUST end them.

**4.3** `hmz web` MUST hold epics apart from itself unless `HUMANIZE_DAEMON` is `off`, `0` or `no`;
otherwise it MUST hold them in its own process, and stopping it MUST end them.

**4.4** Where the daemon or a host cannot be started, the terminal interface MUST say `hmz: runs
cannot be detached from the terminal (<why>), so they will run in this process instead` on standard
error and MUST hold the epics in its own process.

**4.5** A frontend MUST be told whether the daemon and the host came up, and MUST be told a failure
to start with its reason, without waiting out a timeout.

**4.6** Asking the daemon which epics are going MUST NOT start a daemon or a host.

**4.7** `HUMANIZE_DAEMON` MUST read as `off`, `0` or `no` in §4.2 and §4.3 where it is one of them
after surrounding white space is removed and letters are lower-cased.

## 5. Epics outlive their frontends

**5.1** The daemon and every host MUST outlive the terminal and the frontend that started them.

**5.2** A hangup, a closed terminal or a frontend exiting MUST NOT end the daemon or a host.

**5.3** A frontend, or the failure of a frontend, MUST NOT end an epic other than by a request to
stop it.

**5.4** A host MUST go once it is idle, provided a frontend has attached to it at least once or 60
seconds have passed since it started.

**5.5** A host MUST keep an epic that ended while no frontend was attached, and that nobody stopped,
until a frontend attaches; it MUST NOT keep a chat that folded away.

**5.6** A chat host MUST fold its chat away as `features/chat.md` specifies, and MUST then go once
it is idle.

**5.7** The daemon MUST go once it holds no host, and MUST go 60 seconds after it started where no
host ever came.

**5.8** A host MUST go, telling every attached frontend why, when it is stopped, when the daemon
goes, and when any frontend asks it to quit; every epic on it MUST be closed as a stop closes it.

**5.9** A host that goes MUST wait at most 15 seconds for the epics it held to release what they
made.

**5.10** A host that goes MUST then wait at most 15 seconds for the backups of those epics to
finish.

**5.11** What fails in the daemon or a host MUST be written down where the user can read it
afterwards: what belongs to an epic into that epic, and what belongs to none beside the daemon, as
`api/files/machine.md` specifies.

## 6. Frontends

**6.1** hmz MUST let any number of frontends -- the terminal interface, `hmz web`, and programs
using the SDK -- attach to one host at once, each whole and each its own.

**6.2** A frontend that attaches MUST be told everything kept of the epic going or the last one,
from its start, then how everything stands, then everything as it happens.

**6.3** What one frontend does to an epic MUST be seen by every frontend attached to it, with the
name of the frontend that did it.

**6.4** Each frontend MUST be named by the user and the kind of frontend; two frontends of one name
MUST be told apart by a number.

**6.5** hmz MUST let any attached frontend: start an epic; resume an epic; say a line to the
epic, to one agent, to one session or to one person; answer a question; stop an epic; force a
stopping epic, closing every session under its open turn; set a role away or back; claim a role,
take it over and release it; change the board; and ask a side question.

**6.6** A frontend that detaches, closes or is lost MUST leave the epics going, MUST release the
roles it claimed, and MUST leave every role it set away as it set it.

**6.7** A question MUST stay asked while no frontend is attached, and MUST be offered to every
frontend once the frontend that claimed its role detaches.

**6.8** A frontend that falls too far behind what it is told MUST be told so and detached, and MUST
NOT hold up the epic or another frontend.

**6.9** The terminal interface MUST offer, on leaving while a flow other than a chat is going, to
stop the flow or to detach, as `features/tui.md` specifies.

**6.10** Running the terminal interface again in the same workspace MUST attach it to that
workspace's host, and MUST show the epic from its start.

## 7. Versions

**7.1** A daemon MUST hold its epics under the release of hmz it started with, until it goes.

**7.2** Installing another release of hmz, by `hmz update` or otherwise, MUST NOT stop the daemon or
any epic it holds.

**7.3** Once a daemon of an earlier release than the one installed has gone, the next frontend that
needs a daemon MUST start one of the release installed.

**7.4** A frontend MUST NOT reach a daemon or host that is older than it, and MUST NOT start a
daemon or host beside one.

**7.5** A frontend that finds the epics of a workspace held by an older daemon MUST refuse them,
saying `the runs in <workspace> are held by an older Humanize (pid <pid>); stop it with that
version`, or `on this machine` in place of `in <workspace>` where the daemon itself is older.

**7.6** The terminal interface and `hmz web` MUST say that refusal on standard error and exit 1
where they cannot serve without those epics; the page of `hmz web` MUST say it where the page asks
for that workspace's epics, and MUST serve every other workspace.

**7.7** A daemon or host MUST tell a frontend that is older than it ``held for frontends by a newer
Humanize; `hmz` of it reads it``, and MUST then detach it.

## 8. Remote daemons

### 8.1 Keeping them

**8.1.1** The remote daemons MUST be kept in the settings of this machine, as `api/settings.md`
specifies, and MUST be shared by every frontend of this machine that switches between daemons.

**8.1.2** Local MUST always be present, and MUST NOT be removed, renamed or written to the settings.

**8.1.3** The name of a remote daemon MUST start with a letter or a digit, MUST consist of letters,
digits, `.`, `_` and `-`, and MUST NOT be `local`.

**8.1.4** A remote daemon MUST be reached as `ssh` reaches its host, with the user's keys and ssh
config, from what the user set: host, user, port, identity file, proxy jump and ssh options, or a
host of the ssh config resolved each time it is reached.

**8.1.5** Removing a remote daemon MUST forget only how to reach it; the epics and the hmz on its
machine MUST stay as they are.

### 8.2 Reaching one

**8.2.1** A remote daemon MUST be reached when a frontend first asks for it or the user asks to
connect to it.

**8.2.2** Reaching a remote daemon MUST start `hmz web` on its machine over ssh, listening on that
machine's loopback alone.

**8.2.3** Reaching a remote daemon MUST forward a port of this machine's loopback to that `hmz web`.

**8.2.4** hmz MUST NOT listen on the remote machine beyond its loopback.

**8.2.5** Whatever a frontend asks of a remote daemon MUST be asked of that `hmz web`, which holds
its own key, its own epics and its own refusals; the key MUST NOT be shown to the user or to the
page.

**8.2.6** A remote daemon MUST be in exactly one of these states:

| State | Meaning |
| --- | --- |
| `idle` | Not reached yet |
| `connecting` | ssh is reaching the host and starting `hmz web` there |
| `installing` | hmz is being installed on the host |
| `up` | Reached |
| `failed` | Not reached, with the reason |

**8.2.7** Each state MUST carry what was said last, including the last line of an install.

**8.2.8** A connection to a remote daemon that drops or fails MUST be tried again after 1 second,
the wait doubling after each further failure up to at most 60 seconds, and starting again at
1 second once the remote daemon is `up`.

**8.2.9** The frontend that reached a remote daemon going MUST stop the `hmz web` and the ssh
connections it started there; the epics on that machine MUST keep going, held by its daemon.

**8.2.10** Reaching a remote daemon MUST NOT ask the user for a password or to accept a host key; a
host that needs either MUST fail with what ssh said.

### 8.3 The hmz on a remote machine

**8.3.1** Before starting `hmz web` on a remote machine, the frontend MUST find the hmz there as a
login shell finds it, with `~/.local/bin` included, and MUST learn its version.

**8.3.2** Where no hmz is there, or one of another release, the frontend MUST install hmz of its own
release there as a uv tool, installing uv there first where none is, and MUST be `installing` while
it does.

**8.3.3** The frontend MUST NOT replace an hmz there while that machine's daemon holds running
epics, and MUST NOT replace it where it cannot tell; it MUST then use the hmz there and say `hmz
<there> there holds running epics; hmz <wanted> waits`, or `Whether hmz <there> there runs epics is
unknown; not replaced`.

**8.3.4** An install that fails MUST leave the remote daemon `failed` with the last line uv said, or
`hmz <wanted> could not be installed.`; an install after which another version answers MUST leave it
`failed` with `hmz <wanted> was installed, and hmz <there> answers.`

**8.3.5** A development build of hmz, version `0.0.0`, MUST install nothing on a remote machine and
MUST use the hmz there; where none is there, the remote daemon MUST be `failed` with `hmz is not
installed on <name>.`

### 8.4 Using one

**8.4.1** A frontend that switches between daemons MUST show one daemon at a time, and MUST show of
a remote daemon everything it shows of Local: its workspaces, its epics, starting and steering epics
there, its flows, and its daemon settings.

**8.4.2** hmz MUST let a frontend attach to the epics of a workspace on a remote daemon as it
attaches on Local, as `features/web.md` and `features/tui.md` specify.

**8.4.3** A frontend MUST say a remote daemon that is not `up` is unavailable, with its state,
wherever it asks it something.

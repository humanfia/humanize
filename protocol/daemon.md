# The Humanize Protocol: Daemon

## Abstract

This document specifies the hmz daemon: the behaviour a user observes of the process that holds a
machine's epics apart from every frontend, and the wire protocol a client speaks to it.

## Status of This Document

This document is one of the documents of the Humanize Protocol, which Section 2.2.4 of [CORE] lists.
It is normative. It is cited by the tag [DAEMON].

## Table of Contents

- [1. Introduction](#1-introduction)
- [2. Conventions and Terminology](#2-conventions-and-terminology)
- [3. Daemon Behaviour](#3-daemon-behaviour)
  - [3.1. Scope](#31-scope)
  - [3.2. Terminology](#32-terminology)
  - [3.3. One daemon per machine and user](#33-one-daemon-per-machine-and-user)
  - [3.4. Starting](#34-starting)
  - [3.5. Epics outlive their frontends](#35-epics-outlive-their-frontends)
  - [3.6. Frontends](#36-frontends)
  - [3.7. Versions](#37-versions)
  - [3.8. Remote daemons](#38-remote-daemons)
- [4. Wire Protocol](#4-wire-protocol)
  - [4.1. Scope](#41-scope)
  - [4.2. Terminology](#42-terminology)
  - [4.3. The daemon directory](#43-the-daemon-directory)
  - [4.4. Finding the daemon and a host](#44-finding-the-daemon-and-a-host)
  - [4.5. Frames](#45-frames)
  - [4.6. Control requests](#46-control-requests)
  - [4.7. Frontend connections](#47-frontend-connections)
  - [4.8. Requests](#48-requests)
  - [4.9. Messages](#49-messages)
  - [4.10. Semantics a frontend observes](#410-semantics-a-frontend-observes)
  - [4.11. Limits](#411-limits)
  - [4.12. Protocol versions](#412-protocol-versions)
  - [4.13. Lifecycle](#413-lifecycle)
- [5. Security Considerations](#5-security-considerations)
- [6. References](#6-references)
  - [6.1. Normative References](#61-normative-references)

## 1. Introduction

This document specifies the hmz daemon: the behaviour a user observes of the process that holds a
machine's epics apart from every frontend, and the wire protocol a client speaks to it.

This document is organised as follows:

- Section 3: Daemon Behaviour.
- Section 4: Wire Protocol.

## 2. Conventions and Terminology

The key words "MUST", "MUST NOT" and "MAY" in this document are to be interpreted as described in
BCP 14 [RFC2119] [RFC8174] when, and only when, they appear in all capitals, as shown here.

The conventions for numbering and citation, and every term of the shared glossary, are those of
Section 2 of [CORE].

## 3. Daemon Behaviour

### 3.1. Scope

Section 3 specifies the daemon as the user experiences it: one daemon per machine and user,
holding the epics of every workspace on that machine apart from any terminal; how it starts and
goes; how frontends attach to and detach from the epics it holds; how epics outlive the frontend
that started them; how a daemon of one release meets a frontend of another; and how a frontend
reaches the daemon of another machine over ssh or over EasyTier.

Out of scope:

- The protocol between frontends and the daemon, its messages and its requests: Section 4.
- The files the daemon keeps on this machine: Section 7 of [FILES].
- The settings the remote daemons are kept in: Section 3 of [FILES].
- What a chat is, and how a chat folds away: Section 8 of [CORE].
- How the page of `hmz web` presents daemons: Section 3.13 of [WEB].
- How the terminal interface presents daemons and `/exit`: [TUI].
- The release check and `hmz update`: Section 13 of [CORE].
- The command line of `hmz server`: Section 13 of [CLI].

### 3.2. Terminology

**3.2.1** A **host** is what holds the epics of one workspace, or of one chat of a workspace, for
every frontend attached to them. A host held by the daemon is held apart from every frontend.

**3.2.2** The **workspace host** of a workspace is the host that runs that workspace's flows. A
**chat host** is a host that runs one chat of a workspace, beside the workspace host.

**3.2.3** A frontend **attaches** to a host when it starts reading and steering the epics that host
holds, and **detaches** when it stops, without stopping them.

**3.2.4** A host is **idle** when no frontend is attached to it, no epic is going, starting or
stopping on it, and it keeps no ended epic for the next frontend under Section 3.5.5.

**3.2.5** A daemon is **older** than a frontend when it speaks a protocol of an earlier release of
hmz than the frontend, and **newer** when it speaks a protocol of a later one.

**3.2.6** A **remote daemon** is the daemon of another machine, reached from this machine over ssh
or over EasyTier. A remote daemon reached over ssh is an **SSH daemon**, and one reached over
EasyTier a **P2P daemon**, as the page of `hmz web` names them.

**3.2.7** **Local** is the daemon of this machine, as the frontends that switch between daemons name
it.

**3.2.8** **EasyTier** is the peer-to-peer virtual network of that name; a **server** is an `hmz
server` that keeps the daemon of its machine reachable over it (Section 3.8.5).

### 3.3. One daemon per machine and user

**3.3.1** There MUST be at most one daemon per machine and user.

**3.3.2** The daemon MUST hold the epics of every workspace of its machine and user.

**3.3.3** The daemon MUST hold one workspace host per workspace, and one chat host per chat beside
it; each host MUST run in a process of its own, standing in its workspace.

**3.3.4** A chat host and the workspace host of one workspace MUST NOT wait on each other; how many
epics each runs at a time is stated in Section 3.4.3 of [CORE].

**3.3.5** Two spellings of one directory MUST name one workspace, and two directories MUST name two
workspaces.

**3.3.6** The daemon MUST belong to the machine it runs on, and MUST NOT be shared between machines
that mount one home.

**3.3.7** Two frontends racing to start the daemon, or a host of one workspace, MUST end with one
daemon, or one host, which both use.

### 3.4. Starting

**3.4.1** The daemon MUST start when the first frontend that holds epics apart from itself needs it,
and MUST NOT need to be started by the user.

**3.4.2** The terminal interface MUST hold epics apart from itself only where both its standard
input and its standard output are a terminal and `HUMANIZE_DAEMON` is not `off`, `0` or `no`;
otherwise it MUST hold them in its own process, and closing it MUST end them.

**3.4.3** `hmz web` MUST hold epics apart from itself unless `HUMANIZE_DAEMON` is `off`, `0` or
`no`; otherwise it MUST hold them in its own process, and stopping it MUST end them.

**3.4.4** Where the daemon or a host cannot be started, the terminal interface MUST say `hmz: runs
cannot be detached from the terminal (<why>), so they will run in this process instead` on standard
error and MUST hold the epics in its own process.

**3.4.5** A frontend MUST be told whether the daemon and the host came up, and MUST be told a
failure to start with its reason, without waiting out a timeout.

**3.4.6** Asking the daemon which epics are going MUST NOT start a daemon or a host.

**3.4.7** `HUMANIZE_DAEMON` MUST read as `off`, `0` or `no` in Section 3.4.2 and Section 3.4.3 where
it is one of them after surrounding white space is removed and letters are lower-cased.

### 3.5. Epics outlive their frontends

**3.5.1** The daemon and every host MUST outlive the terminal and the frontend that started them.

**3.5.2** A hangup, a closed terminal or a frontend exiting MUST NOT end the daemon or a host.

**3.5.3** A frontend, or the failure of a frontend, MUST NOT end an epic other than by a request to
stop it.

**3.5.4** A host MUST go once it is idle, provided a frontend has attached to it at least once or 60
seconds have passed since it started.

**3.5.5** A host MUST keep an epic that ended while no frontend was attached, and that nobody
stopped, until a frontend attaches; it MUST NOT keep a chat that folded away.

**3.5.6** A chat host MUST fold its chat away as Section 8 of [CORE] specifies, and MUST then go
once it is idle.

**3.5.7** The daemon MUST go once it holds no host, and MUST go 60 seconds after it started where no
host ever came.

**3.5.8** A host MUST go, telling every attached frontend why, when it is stopped, when the daemon
goes, and when any frontend asks it to quit; every epic on it MUST be closed as a stop closes it.

**3.5.9** A host that goes MUST wait at most 15 seconds for the epics it held to release what they
made.

**3.5.10** A host that goes MUST then wait at most 15 seconds for the backups of those epics to
finish.

**3.5.11** What fails in the daemon or a host MUST be written down where the user can read it
afterwards: what belongs to an epic into that epic, and what belongs to none beside the daemon, as
Section 7 of [FILES] specifies.

### 3.6. Frontends

**3.6.1** hmz MUST let any number of frontends -- the terminal interface, `hmz web`, and programs
using the SDK -- attach to one host at once, each whole and each its own.

**3.6.2** A frontend that attaches MUST be told everything kept of the epic going or the last one,
from its start, then how everything stands, then everything as it happens.

**3.6.3** What one frontend does to an epic MUST be seen by every frontend attached to it, with the
name of the frontend that did it.

**3.6.4** Each frontend MUST be named by the user and the kind of frontend; two frontends of one
name MUST be told apart by a number.

**3.6.5** hmz MUST let any attached frontend: start an epic; resume an epic; say a line to the epic,
to one agent, to one session or to one person; answer a question; stop an epic; force a stopping
epic, closing every session under its open turn; set a role away or back; claim a role, take it over
and release it; change the board; and ask a side question.

**3.6.6** A frontend that detaches, closes or is lost MUST leave the epics going, MUST release the
roles it claimed, and MUST leave every role it set away as it set it.

**3.6.7** A question MUST stay asked while no frontend is attached, and MUST be offered to every
frontend once the frontend that claimed its role detaches.

**3.6.8** A frontend that falls too far behind what it is told MUST be told so and detached, and
MUST NOT hold up the epic or another frontend.

**3.6.9** The terminal interface MUST offer, on leaving while a flow other than a chat is going, to
stop the flow or to detach, as [TUI] specifies.

**3.6.10** Running the terminal interface again in the same workspace MUST attach it to that
workspace's host, and MUST show the epic from its start.

### 3.7. Versions

**3.7.1** A daemon MUST hold its epics under the release of hmz it started with, until it goes.

**3.7.2** Installing another release of hmz, by `hmz update` or otherwise, MUST NOT stop the daemon
or any epic it holds.

**3.7.3** Once a daemon of an earlier release than the one installed has gone, the next frontend
that needs a daemon MUST start one of the release installed.

**3.7.4** A frontend MUST NOT reach a daemon or host that is older than it, and MUST NOT start a
daemon or host beside one.

**3.7.5** A frontend that finds the epics of a workspace held by an older daemon MUST refuse them,
saying `the runs in <workspace> are held by an older Humanize (pid <pid>); stop it with that
version`, or `on this machine` in place of `in <workspace>` where the daemon itself is older.

**3.7.6** The terminal interface and `hmz web` MUST say that refusal on standard error and exit 1
where they cannot serve without those epics; the page of `hmz web` MUST say it where the page asks
for that workspace's epics, and MUST serve every other workspace.

**3.7.7** A daemon or host MUST tell a frontend that is older than it ``held for frontends by a
newer Humanize; `hmz` of it reads it``, and MUST then detach it.

### 3.8. Remote daemons

#### 3.8.1. Keeping them

**3.8.1.1** The remote daemons MUST be kept in the settings of this machine, as Section 3 of [FILES]
specifies, and MUST be shared by every frontend of this machine that switches between daemons.

**3.8.1.2** Local MUST always be present, and MUST NOT be removed, renamed or written to the
settings.

**3.8.1.3** The name of a remote daemon MUST start with a letter or a digit, MUST consist of
letters, digits, `.`, `_` and `-`, and MUST NOT be `local`.

**3.8.1.4** An SSH daemon MUST be reached as `ssh` reaches its host, with the user's keys and ssh
config, from what the user set: host, user, port, identity file, proxy jump and ssh options, or a
host of the ssh config resolved each time it is reached.

**3.8.1.5** Removing a remote daemon MUST forget only how to reach it; the epics and the hmz on its
machine MUST stay as they are.

#### 3.8.2. Reaching one

**3.8.2.1** A remote daemon MUST be reached when a frontend first asks for it or the user asks to
connect to it.

**3.8.2.2** Reaching an SSH daemon MUST start `hmz web` on its machine over ssh, listening on that
machine's loopback alone.

**3.8.2.3** Reaching an SSH daemon MUST forward a port of this machine's loopback to that `hmz web`.

**3.8.2.4** hmz MUST NOT listen on the remote machine beyond its loopback.

**3.8.2.5** Whatever a frontend asks of a remote daemon MUST be asked of that `hmz web`, which holds
its own key, its own epics and its own refusals; the key MUST NOT be shown to the user or to the
page.

**3.8.2.6** A remote daemon MUST be in exactly one of these states:

| State | Meaning |
| --- | --- |
| `idle` | Not reached yet |
| `connecting` | ssh is reaching the host and starting `hmz web` there, or EasyTier is joining |
| `installing` | hmz is being installed on the host, or EasyTier on this machine |
| `up` | Reached |
| `failed` | Not reached, with the reason |

**3.8.2.7** Each state MUST carry what was said last, including the last line of an install.

**3.8.2.8** A connection to a remote daemon that drops or fails MUST be tried again after 1 second,
the wait doubling after each further failure up to at most 60 seconds, and starting again at 1
second once the remote daemon is `up`.

**3.8.2.9** The frontend that reached a remote daemon going MUST stop the `hmz web`, the ssh
connections and the EasyTier processes it started for it; the epics on that machine MUST keep going,
held by its daemon.

**3.8.2.10** Reaching an SSH daemon MUST NOT ask the user for a password or to accept a host key; a
host that needs either MUST fail with what ssh said.

#### 3.8.3. The hmz on a remote machine

**3.8.3.1** Before starting `hmz web` on the machine of an SSH daemon, the frontend MUST find the
hmz there as a login shell finds it, with `~/.local/bin` included, and MUST learn its version.

**3.8.3.2** Where no hmz is there, or one of another release, the frontend MUST install hmz of its
own release there as a uv tool, installing uv there first where none is, and MUST be `installing`
while it does.

**3.8.3.3** The frontend MUST NOT replace an hmz there while that machine's daemon holds running
epics, and MUST NOT replace it where it cannot tell; it MUST then use the hmz there and say `hmz
<there> there holds running epics; hmz <wanted> waits`, or `Whether hmz <there> there runs epics is
unknown; not replaced`.

**3.8.3.4** An install that fails MUST leave the remote daemon `failed` with the last line uv said,
or `hmz <wanted> could not be installed.`; an install after which another version answers MUST leave
it `failed` with `hmz <wanted> was installed, and hmz <there> answers.`

**3.8.3.5** A development build of hmz, version `0.0.0`, MUST install nothing on a remote machine
and MUST use the hmz there; where none is there, the remote daemon MUST be `failed` with `hmz is not
installed on <name>.`

#### 3.8.4. Using one

**3.8.4.1** A frontend that switches between daemons MUST show one daemon at a time, and MUST show
of a remote daemon everything it shows of Local: its workspaces, its epics, starting and steering
epics there, its flows, and its daemon settings.

**3.8.4.2** hmz MUST let a frontend attach to the epics of a workspace on a remote daemon as it
attaches on Local, as Section 3 of [WEB] and [TUI] specify.

**3.8.4.3** A frontend MUST say a remote daemon that is not `up` is unavailable, with its state,
wherever it asks it something.

#### 3.8.5. P2P daemons

**3.8.5.1** A P2P daemon MUST be kept as its name and a secret of at least 16 bytes in UTF-8, the
secret its server was started with; a shorter secret MUST be refused with `A secret must be at least
16 bytes.`

**3.8.5.2** The name and the secret of the EasyTier network MUST be derived from the secret by
SHA-256, and the key of the server's `hmz web` by HMAC-SHA256, each under a label of its own; the
secret itself MUST NOT leave the machine it is set on, nor be passed on any command line.

**3.8.5.3** A server MUST serve `hmz web` on its machine's loopback alone, at a port fixed by hmz,
with the key derived from its secret, holding the epics through its machine's daemon, and MUST make
that port reachable over the EasyTier network of its secret, through the shared EasyTier nodes it
was started with (Section 3.8.5.10).

**3.8.5.4** Reaching a P2P daemon MUST join the EasyTier network of its secret and expose that `hmz
web` on a port of this machine's loopback, MUST wait until it answers, and MUST then ask it as
Section 3.8.2.5 states, with the key derived from the secret.

**3.8.5.5** EasyTier MUST run without root and without a virtual network device, on either side.

**3.8.5.6** hmz MUST download the official release of EasyTier of the version it pins, for this
machine's system and architecture, into its home, MUST check it against the SHA-256 it pins, and
MUST reuse it once there; a P2P daemon MUST be `installing` while it downloads, saying `Downloading
EasyTier <version>`, and `failed` with the reason where the download or the check fails.
`HUMANIZE_EASYTIER` naming an existing binary MUST be used in its place.

**3.8.5.7** Reaching a P2P daemon MUST install nothing on its machine; a server older than the
frontend MUST be refused as Section 3.7.4 states.

**3.8.5.8** A P2P daemon MUST be in the states of Section 3.8.2.6, with what was said last, and MUST
be tried again as Section 3.8.2.8 states.

**3.8.5.9** Stopping a server MUST stop its `hmz web` and EasyTier, and MUST NOT stop any epic its
daemon holds.

**3.8.5.10** A P2P daemon and a server MUST each name at least one shared EasyTier node, as a URL
`<protocol>://<host>:<port>` with protocol `tcp`, `udp`, `ws`, `wss`, `quic` or `wg`, and MUST meet
the other end only through the nodes they name; hmz MUST NOT name a node of its own, and a P2P
daemon reaches its server only where both name a node in common. A P2P daemon or a server that
names no node MUST be refused with `An EasyTier daemon needs at least one node.`

**3.8.5.11** hmz MUST offer the shared nodes of EasyTier's community, as the status page EasyTier's
own apps read lists them, each with its URL, its name, its version, whether it is up and its uptime
over the last 24 hours; a list that cannot be read MUST be said to be unreadable with the reason,
and nodes the user types MUST be taken all the same.

## 4. Wire Protocol

### 4.1. Scope

Section 4 governs the **daemon** as a client sees it: where a client finds the one daemon of
**this machine** for the current user, how it connects, the frames carried on a connection, every
request a client sends and every message and answer it receives, how protocol versions are told
apart, and every obligation of the daemon and its hosts that a client observes over a connection. A
client is a **frontend** (`hmz`, `hmz web`, a program using Section 4 of [PYTHON]) or a program
asking a single question. The internal structure of the daemon and of its host processes is not
governed by this document.

Out of scope:

- The Python objects that speak this protocol (`Daemon`, `Link`, `Host`): Section 4 of [PYTHON].
- The files of the daemon directory as files on disk, and their cleanup: Section 7 of [FILES].
- The files an **epic** writes, `host.log` among them: Section 6 of [FILES].
- When `hmz` and `hmz web` use a daemon rather than holding epics in their own process, and the
  daemons of other machines: Section 3.
- What a flow, a chat and a side question do beyond what is carried here: Section 3 of [CORE],
  Section 8 of [CORE], Section 9 of [CORE].

### 4.2. Terminology

**4.2.1** Every term of Section 2 of [CORE] MUST carry the meaning given there.

**4.2.2** **Daemon directory**: the machine directory `<mdir>` of Section 7.2.2 of [FILES].

**4.2.3** **Socket**: the Unix stream socket `daemon.sock` in the daemon directory.

**4.2.4** **Daemon record**: the file `daemon.json` in the daemon directory.

**4.2.5** **Workspace path**: a workspace directory as an absolute path with every symbolic link
followed. Two spellings of one directory are one workspace path.

**4.2.6** **Slot**: the text naming one host of a workspace: `""` for the workspace's own host, or
`chat:` followed by 1 to 32 lowercase hexadecimal digits for the host of one chat.

**4.2.7** The term host MUST carry the meaning Section 3.2.1 gives it; each slot of a workspace
names one host, which a client reaches only through the daemon.

**4.2.8** **Frame**: one unit carried on a connection, as Section 4.5 defines it.

**4.2.9** **Control request**: one JSON object carried in a `CONTROL` frame, as Section 4.6 defines
it.

**4.2.10** **Request**: one JSON object a frontend sends in a `MESSAGE` frame, naming what it asks
in its field `do`.

**4.2.11** **Reply**: the message a host sends in answer to one request, with `type` `reply`.

**4.2.12** **Message**: one JSON object a host sends in a `MESSAGE` frame, naming its kind in its
field `type`.

**4.2.13** **Client id**: the text `c<n>` a host gives one attached frontend, `n` counting from 1
per host and never reused.

**4.2.14** **History record**: a message that carries the field `seq` (Section 4.9.2).

**4.2.15** **Snapshot**: a message without `seq` that says how one thing stands now (Section 4.9.3).

**4.2.16** **Epic number**: the number a host gives each epic it starts, counting from 1 per host.

### 4.3. The daemon directory

**4.3.1** The daemon directory MUST NOT be under the **home** directory.

**4.3.2** The daemon directory, the socket and the daemon record MUST be created, refused and
removed as Section 7.3 of [FILES] and Section 7.6 of [FILES] state.

**4.3.3** Where the full path of the socket exceeds 100 bytes, a client MUST still connect to the
socket, and MUST have the current directory it had before once it has connected.

### 4.4. Finding the daemon and a host

**4.4.1** A client MUST read a daemon as present only where the daemon record parses as a JSON
object whose `pid` is an integer naming an existing process, and the socket accepts a connection
within 1 second.

**4.4.2** A client MUST count a process that exists but that it cannot signal as existing.

**4.4.3** A client MUST NOT read a daemon as present on the strength of the socket file alone.

**4.4.4** Where the daemon record's `protocol` is absent or differs from the client's protocol
version, the client MUST NOT send any other frame to the socket and MUST report that an older
**hmz** holds the epics (Section 4.12.3).

**4.4.5** A client finds the hosts of the daemon with the control request `list` (Section 4.6.2); a
client MUST read a listed host as live only where its `pid` names an existing process.

**4.4.6** A client MUST name a workspace to the daemon by its workspace path.

**4.4.7** A client that starts the daemon or a host MUST wait at most 10 seconds for it to come up.

**4.4.8** A client that starts the daemon or a host MUST report a failure the started process
reports as soon as it is reported, without waiting out the bound of Section 4.4.7.

**4.4.9** Where two clients start the daemon at once, exactly one daemon MUST come up, and both
clients MUST use it.

**4.4.10** Where two clients start a host of one slot of one workspace at once, exactly one host
MUST be taken on, and both clients MUST use it.

### 4.5. Frames

**4.5.1** Every byte on a connection MUST belong to a frame of the form: one byte of kind, then the
payload length as an unsigned 32-bit big-endian integer, then the payload.

**4.5.2** The kinds MUST be: `M` (`MESSAGE`), a payload of one UTF-8 JSON object, a request from a
frontend or a message from a host; `C` (`CONTROL`), a payload of one UTF-8 JSON object, a control
request or its answer; and `X` (`GONE`), a payload of UTF-8 text saying why the reader is let go.

**4.5.3** A reader MUST accept a payload of at most 4 194 304 bytes; a length above it MUST be
treated as a connection not carrying this protocol, which the reader closes.

**4.5.4** A host MUST NOT send a frame whose length with its 5-byte header exceeds 4 194 303 bytes;
a message that would MUST be dropped and recorded in the host's log, and replies are exempt.

**4.5.5** A host MUST encode JSON without escaping non-ASCII characters and MUST encode every value
that is not JSON-native as its text.

**4.5.6** A JSON payload that is not an object MUST be read as an empty object.

**4.5.7** A reader MUST hand out each whole frame exactly once, in the order received.

**4.5.8** On receiving a frame of a kind it does not know, the daemon and a host MUST answer with
one `GONE` frame carrying ``held for frontends by a newer Humanize; `hmz` of it reads it`` and close
the connection.

### 4.6. Control requests

#### 4.6.1. General

**4.6.1.1** A control request MUST be the first and only frame a client sends on its connection.

**4.6.1.2** A control request MUST carry `do` and MUST be answered with exactly one `CONTROL` frame,
after which the connection MUST be closed.

**4.6.1.3** A client MUST NOT send a control request whose `do` is `serve`; that request is reserved
for the host processes of **hmz**.

#### 4.6.2. Control requests to the daemon

**4.6.2.1** A control request without `workspace` MUST be answered by the daemon itself.

**4.6.2.2** `do: "list"` MUST be answered `{"ok": true, "held": [...]}`, one entry per host taken
on, in the order taken on, each with `pid`, `workspace`, `started` and `slot`.

**4.6.2.3** Any other `do` MUST be answered `{"ok": false, "why": "no such request: <repr>"}`,
`<repr>` being the `do` given written as a Python literal: text in single quotes, a number as
written, `True`, `False` or `None` for `true`, `false` or `null`, and a list or object in brackets
or braces with each item so written.

#### 4.6.3. Control requests to a host

**4.6.3.1** A control request with `workspace` and, for a host other than the workspace's own,
`slot` MUST be answered by that host.

**4.6.3.2** Where no host holds that workspace and slot, the daemon MUST answer `{"ok": false,
"why": "no runs are held in <workspace>"}`, with ` for <slot>` appended where `slot` is not `""`.

**4.6.3.3** `do: "status"` MUST be answered `{"ok": true}` with the host's own `pid`, `workspace`,
`slot`, `started`, `kind` (`"host"`) and `protocol`, and every key of Section 4.6.4.

**4.6.3.4** `do: "detach"` MUST let every attached frontend go with `gone` `let go`, leave every
epic running, and be answered `{"ok": true, "let go": <n>}`, `n` the number let go.

**4.6.3.5** `do: "stop"` MUST be answered `{"ok": true}` before anything else happens, and the host
MUST then close as Section 4.13.6 states.

**4.6.3.6** Any other `do` MUST be answered `{"ok": false, "why": "no such request: <repr>"}`.

**4.6.3.7** A connection carrying a control request MUST NOT count as a frontend attached to the
host.

#### 4.6.4. Status

**4.6.4.1** The status of a host MUST carry the keys of the following list, and a client MUST read
an absent `turn` as the host not holding a chat.

- `attached`: Integer: the frontends attached.
- `clients`: `[{client, name, kind}]`, one per frontend attached.
- `slot`: The host's slot.
- `state`: `running`, `stopping` or `idle`.
- `run`: The epic number of the epic going, else stopping, else the last; `0` for none.
- `flow`: That epic's flow as named, or `""`.
- `epic`: That epic's directory name, `""` before it has one.
- `task`: That epic's task, or `""`.
- `pending`: `[{question, role, text, mode}]`: every question waiting on a person.
- `ended`: How the last epic to end on this host ended, `{how, why, epic, at, run, flow, task}`,
  `at` in Unix seconds; `null` before one has ended.
- `turn`: Of a chat only: `running` while its agent answers, `done` between turns and once it is
  over.
- `budget`, `usage`: The epic going's budget and spending as JSON, an infinite limit as the text
  `"Infinity"`; `null` while stopping or idle.
- `flows`: The canonical refs of the flow calls in progress.
- `calls`: `[{ref, name, depth, seconds, id, parent}]`, oldest first; `seconds` rounded to 0.001;
  `parent` the index of the calling entry, or `null`.

**4.6.4.2** The host-process keys are `pid`, `workspace`, `started`, `kind` and `protocol`.

**4.6.4.3** A client MUST read a host that does not answer a control request `status` as having the
host-process keys of its `list` entry, `attached` `0`, `flows` `[]` and `calls` `[]`.

### 4.7. Frontend connections

#### 4.7.1. Attaching

**4.7.1.1** A frontend MUST send `hello` as the first request on its connection.

**4.7.1.2** `hello` MUST carry `workspace` (a workspace path) and, for a host other than the
workspace's own, `slot`; the host of that workspace and slot MUST answer it, and MUST read every
later frame of that connection.

**4.7.1.3** Where no host holds that workspace and slot, the daemon MUST answer with a reply whose
`to` is the request's `id`, `ok` `false` and `why` `no runs are held in <workspace>`, with ` for
<slot>` appended where `slot` is not `""`, and close the connection.

**4.7.1.4** `hello` MUST take `name` (text, default `""`), `kind` (text, default `"sdk"`) and
`replay` (default `true`; only the JSON value `false` disables it).

**4.7.1.5** A host MUST name a frontend by `name` where it is not `""`, else `<user>@<kind>`,
`<user>` being `HUMANIZE_NAME` where set, else the login name, else `somebody`; a name already
attached MUST become `<name>#2`, `<name>#3` and on.

**4.7.1.6** `hello` MUST be answered with `client`, the frontend's client id.

**4.7.1.7** `hello` MUST be refused with `this frontend has already said hello` when sent twice,
`the frontend went while it was saying hello` where the connection closed meanwhile, and `this host
has closed` once the host is closed.

**4.7.1.8** Every request sent before `hello` MUST be refused with `a frontend says hello first`.

#### 4.7.2. Replies

**4.7.2.1** A request MAY carry `id`; every request MUST be answered with exactly one reply on the
connection it came in on, whose `to` is that `id`, or `""` where it carried none.

**4.7.2.2** A reply MUST carry `ok`; a reply with `ok` `true` MUST carry the fields of the answer,
and one with `ok` `false` MUST carry `why`, one sentence.

**4.7.2.3** A request whose `do` names no request MUST be refused with `no such request: <repr>`.

**4.7.2.4** A request from a frontend no longer attached MUST be refused with `this frontend is not
attached`.

**4.7.2.5** A request that fails for any other reason MUST be refused with the text of the failure,
or the name of its type where the text is empty.

**4.7.2.6** A host MUST give every frontend the same answer and the same refusal, in the same words,
to the same request in the same state.

#### 4.7.3. Order

**4.7.3.1** A host MUST carry out the requests of one frontend in the order sent, except `aside`,
which MUST be carried out apart from that order so that no other request waits on it.

**4.7.3.2** A host MUST NOT let a request of one frontend delay the requests or messages of another.

#### 4.7.4. Leaving

**4.7.4.1** A frontend leaves by closing its connection, or by the request `detach`; the host MUST
then send it `gone` `let go`, MUST release every role it claimed, and MUST close every aside it
opened.

**4.7.4.2** A frontend leaving MUST NOT stop any epic.

### 4.8. Requests

#### 4.8.1. General

**4.8.1.1** Each request MUST take exactly the fields its subsection lists, with the stated types
and defaults; a field not sent MUST take its default.

#### 4.8.2. `start`

**4.8.2.1** `start` MUST take `flow` (text, required: a flow name of [CLI]), `task` (text, `""`),
`agents` (object of role to agent spec, `{}`), `envs` (object of role to environment spec, `{}`),
`params` (object, `null` for the flow's defaults), `budget` (a `Budget` as JSON, `null`),
`profile_flow` (boolean, `false`), `profile_environment` (boolean, `false`), `resume` (`false`,
`true`, or the text of an epic directory, `false`) and `backup` (list of target names, `null` for
the defaults).

**4.8.2.2** `start` MUST start the epic as `Hmz.run` of Section 4.4.5 of [PYTHON] does and MUST be
answered with `run`, its epic number.

**4.8.2.3** `start` MUST be refused with `a flow to start is named` for a missing `flow`; `backup is
a list of backup target names` for a `backup` that is not one; `this host has closed`; `a flow is
already running` while an epic is going; `a flow is already starting` while another `start` is under
way; `this chat has folded away; carry it on from its epic` on a chat host that has folded (Section
4.13.8); and with the `Refused` message of Section 4.6 of [PYTHON] for everything `Hmz.run` refuses.

**4.8.2.4** An epic that is stopping MUST NOT prevent `start`.

#### 4.8.3. `say`

**4.8.3.1** `say` MUST take `text` (text, required, not empty) and `to` (text, `""`), and MUST route
the line as Section 4.10.1 states.

**4.8.3.2** `say` MUST be refused with `a line says something` for an empty `text`; `no flow is
running to say it to` while no epic is going, a stopping epic included; and `<role> is <name>'s`
where `to` is `outworlder:<role>` and another frontend claims `role`.

#### 4.8.4. `answer`

**4.8.4.1** `answer` MUST take `question` (text, a question id) and `text` (text, required, not
empty).

**4.8.4.2** Where `text`, stripped, is a decimal number `n` from 1 to the number of the question's
options and is not itself an option, the answer MUST be the `n`-th option; otherwise it MUST be
`text`.

**4.8.4.3** `answer` MUST be refused with `an answer says something`; `already answered by <name>`
for a question answered; `no question <id> is waiting`; and `<role> is <name>'s` where another
frontend claims the question's role.

#### 4.8.5. `stop` and `force`

**4.8.5.1** `stop` MUST take no field, MUST interrupt the turn under way and let the flow unwind,
and MUST be refused with `the flow is already stopping: it is closing out the turn it was in` while
one is stopping and `no flow is running, so there is nothing to stop` while none is going.

**4.8.5.2** `force` MUST take no field, MUST stop the epic going where there is one, MUST close
every session of the stopping epic that has a turn open, and MUST be answered with `closed`, the
number of sessions closed; it MUST be refused with `no flow is running, so there is nothing to stop`
where no epic is going or stopping.

#### 4.8.6. `afk`, `claim` and `release`

**4.8.6.1** `afk` MUST take `on` (boolean, required) and `role` (text, `""` for every role), MUST
set away as Section 4.10.3 states, and MUST be refused with `afk is on or off` for an `on` that is
not a boolean and `<role> is <name>'s` for a role another frontend claims.

**4.8.6.2** `claim` MUST take `role` (text, required) and `take` (boolean, `false`), MUST claim the
role for this frontend as Section 4.10.2 states, and MUST be refused with `a role to claim is named`
and, without `take`, `<role> is <name>'s` for a role another frontend claims.

**4.8.6.3** `release` MUST take `role` (text) and MUST be refused with `<role> is not yours to
release` for a role this frontend does not claim.

**4.8.6.4** `afk`, `claim` and `release` MUST NOT require an epic to be going, and `claim` MUST NOT
check the role against the flow.

#### 4.8.7. `board`

**4.8.7.1** `board` MUST take `key` (text) and `value` (text, `""`), and MUST write the line `key`
of the last epic's board as the user, or remove it where `value` is `""`.

**4.8.7.2** `board` MUST be refused with `this run has no board`, `<key> is not on the board`, and
the board's own refusal where the line is not the user's to change.

#### 4.8.8. `aside` and `unaside`

**4.8.8.1** `aside` without `side` MUST open a side conversation and be answered with `side`
(`s<n>`) and `forked` (boolean: whether it carries the history of a session).

**4.8.8.2** `aside` with `key` (`<agent>/<n>`, a session of the last epic) and `fork` (boolean) MUST
open the side conversation on that session: a fork of it where `fork` is `true` and its harness
forks, otherwise a new session of a copy of its agent.

**4.8.8.3** `aside` with `runs` (an agent spec) MUST open a new session of that agent in the
workspace; with `runs` and `recall` (the harness's id of a session an earlier epic kept), `kept`
(where that epic kept it) and `cwd`, it MUST open a fork of that session where `fork` is `true` and
its harness forks it, otherwise a new session of that agent. With `runs` and `asks` (`true`), the
side conversation MUST be The Epic's, asking as Section 9.6.10 of [CORE] to Section 9.6.14 of [CORE]
state.

**4.8.8.4** `aside` with a `key` that names no session MUST be refused with `<key> has no
conversation to ask`.

**4.8.8.5** `aside` with a `runs` that names no agent this host makes MUST be refused with `<runs>
is not an agent that can be made here`.

**4.8.8.6** `aside` that names neither `key` nor `runs` MUST be refused with `an aside is about a
conversation, or asks an agent`.

**4.8.8.7** `aside` from a frontend that has gone MUST be refused with `this frontend has gone`.

**4.8.8.8** `aside` with `side` and `prompt` MUST take one turn of that side conversation and be
answered with `answer`, its text stripped; for The Epic's, a turn that runs an ask command MUST
instead be answered with `ask` (`to` and `question`) while the turn waits, and one that runs
`hmz-ask list` with `ask` whose `to` is empty.

**4.8.8.9** `aside` with a `side` this frontend has not open MUST be refused with `no aside <side>
is open`.

**4.8.8.10** `aside` with a `side` that is taking a turn MUST be refused with `the aside is still
answering the last question`.

**4.8.8.11** `unaside` MUST take `side`, MUST close that side conversation, and MUST be refused with
`no aside <side> is open`.

**4.8.8.12** Every side conversation MUST be read-only, MUST carry no skills but The Epic's
`ask-conversation` (Section 9.6.10 of [CORE]), MUST NOT be seen by the epic, MUST be answered only
to the frontend that opened it, and MUST NOT write where any epic keeps its sessions nor into the
harness's own home.

**4.8.8.13** A side conversation MUST be closed by `unaside`, when its frontend leaves, when an epic
starts on the host, and when the host closes; no message announces side conversations.

**4.8.8.14** `aside` with `side` and `answered` MUST give The Epic's waiting ask command that
answer, and MUST be answered as `aside` with `prompt` is; where nothing waits, it MUST be refused
with `aside <side> asked nothing`.

#### 4.8.9. `status`, `detach` and `quit`

**4.8.9.1** `status` MUST be answered with every key of Section 4.6.4.1.

**4.8.9.2** `detach` MUST let this frontend go as Section 4.7.4 states.

**4.8.9.3** `quit` MUST close the host as Section 4.13.6 states.

### 4.9. Messages

#### 4.9.1. Attaching

**4.9.1.1** On `hello`, a host MUST send the new frontend, before any other message and with no
other message between them: `welcome`; every history record kept, oldest first, unless `replay` is
`false`; every snapshot, in the order `clients`, `claims`, `away`, `run`, `sessions`, `calls`,
`waiting`, `pending`, `usage`, `board`; and `live`.

**4.9.1.2** After `live`, a host MUST send each history record and each changed snapshot as it
happens.

**4.9.1.3** `welcome` MUST carry `client`, `name`, `kind`, `workspace`, `slot`, `pid` (the host's
process) and `protocol`.

**4.9.1.4** `live` MUST carry `seq`, the `seq` of the last history record, and `elided`, the number
of history records dropped from the front.

#### 4.9.2. History records

**4.9.2.1** Every history record MUST carry `seq`, an integer that increases by one with each record
across the host's life.

**4.9.2.2** A host MUST keep the history records of the epic going or the last, starting afresh with
each `start`, up to 32 MiB of JSON, dropping the oldest whole records first and counting them in
`elided`.

**4.9.2.3** Every history record other than `printed` MUST carry `run`, its epic number.

**4.9.2.4** The history records MUST be those of the following list, with those fields.

- `started`: `flow`, `ref`, `task`, `by`, `client`, `roles` (agent roles not filled by the runtime),
  `names` (`{role: agent name}`), `outworlders`, `agents`, `envs` (`{role: spec}`), `params`,
  `budget`, `profile_flow`, `profile_environment`, `backup`, `resume` (`""`, or the text given),
  `began` (host monotonic seconds), `at` (Unix seconds).
- `opened`: `role`, `key` (`<agent>/<n>`), `agent`, `cli`, `model`, `counts` (token kinds the
  backend reports, sorted), `forks`, `person`, `kept` (directory of the session's logs, `""` for a
  person or the harness's own home), `env`, `harness`, `mono`, `wall`.
- `event`: `key`, `session`, `agent`, `cli`, `model`, `ident`, `kind`, `text`, `whose`, `tokens`,
  `spent`, `at`, `mono`: the record `hmz exec --json` writes ([CLI]).
- `asked`: `question` (`q<n>`), `role`, `text`, `options`, `mode` (`ask` or `listen`), `key`.
- `answered`: `question`, `role`, `by`, `client`, `text`.
- `withdrawn`: `question`, `why` (`away` or `over`).
- `said`: `text`, `key`, `by`, `client`.
- `refused`: `agent`, `text`, `because`.
- `unheld`: `agent`, `texts`.
- `dropped`: `given` (`[{agent, text, by, client}]`), `queued` (`[{text, by, client, to}]`),
  `because` (`stopped` or `ended`).
- `printed`: `text`: one line printed in the host process.
- `notice`: `text`: a notice of **hmz** about the epic, as Section 3 of [CORE] defines notices.
- `stopping`: `by`, `client`.
- `ended`: `how` (`done`, `stopped`, `budget`, `refused`, `failed` or `crashed`), `why`, `mono`.

**4.9.2.5** A conversation MUST be keyed `<agent>/<n>`, `<agent>` the agent's own name and `n` the
count of sessions that agent opened in the epic, assigned once as the session opens.

**4.9.2.6** `opened.env` MUST be `null` where the session has no **placement**, and otherwise
`{role, kind, target, workdir, anchored}` as Section 6 of [CORE] defines them; `opened.harness` MUST
be `""`, `local`, `self` or `<backend>:<name>` as Section 6 of [CORE] defines them.

**4.9.2.7** `ended.why` MUST be `""` for `done` and `stopped`, the limit reached for `budget`, the
`Refused` message for `refused`, `<ExceptionType>: <message>` for `failed`, and a traceback for
`crashed`.

**4.9.2.8** `ended.how` MUST be read as the endings of Section 3.3.6 of [CORE]: `done` as `done`,
`stopped` and `budget` as `stopped`, `failed` and `crashed` as `failed`, and `refused` as an epic
refused before it was created, which has no ending.

#### 4.9.3. Snapshots

**4.9.3.1** A host MUST keep the latest of each snapshot, MUST send every snapshot on attach, and
MUST send a snapshot to every frontend whenever it changes.

**4.9.3.2** The snapshots MUST be those of the following list, with those fields and initial values.

- `clients`: `clients`: `[{client, name, kind}]`; initially `[]`.
- `claims`: `claims`: `{role: client}`; initially `{}`.
- `away`: `all` (boolean), `of` (`{role: boolean}`); initially `false`, `{}`.
- `run`: `state`, the `started` fields of the epic going or the last (`run` `0` for none),
  `stopping` (epic number or `null`), `epic` (`""` before it has one), `slot`, and of a chat `turn`;
  initially `idle`.
- `sessions`: `run`, `open` (keys still open), `working` (keys with a turn open); initially `0`,
  `[]`, `[]`.
- `calls`: `calls`: `[{ref, name, depth, since, id, parent}]`; initially `[]`.
- `waiting`: `queued` (`[{text, by, client, to}]`), `given` (`[{agent, text, by, client}]`);
  initially `[]`, `[]`.
- `pending`: `pending`: `[{question, run, role, text, options, mode, key, owner}]`; initially `[]`.
- `usage`: `run`, `usage`, `budget`; sent at most once a second; initially `0`, `null`, `null`.
- `board`: `items`: `[{key, value, about, whose, by, at}]`, or `null` for an epic with no board;
  initially `null`.

#### 4.9.4. `gone`

**4.9.4.1** `gone` MUST be the last message a host sends a frontend, carrying `why`.

**4.9.4.2** `why` MUST be `let go` where the frontend left; `the host was closed` where the host
closed; `fell too far behind; open it again` or `too far behind; attach again` where the frontend
fell behind (Section 4.11.1).

**4.9.4.3** After `gone`, a host MUST send that frontend no message other than replies, and MUST
give the connection at most 5 seconds to take what it is owed before closing it.

**4.9.4.4** A client MUST read the end of the connection, a failed read, or a frame of no valid
length, without a preceding `gone`, as `gone` with `why` `the host went away`, and a `GONE` frame as
`gone` with its text as `why`.

### 4.10. Semantics a frontend observes

#### 4.10.1. Lines

**4.10.1.1** A line said with `to` `""` MUST answer a waiting `listen` question this frontend is
permitted to answer, else go into the first session with a turn open, in the order the epic opened
them.

**4.10.1.2** A line said with `to` an agent's name MUST go into that agent's newest session with a
turn open; a line said with `to` `<agent>/<n>` MUST go into that session.

**4.10.1.3** In a chat, a line said to an agent or session with no turn open MUST answer the waiting
`listen` question this frontend is permitted to answer, and MUST go into no turn.

**4.10.1.4** A line said with `to` `outworlder:<role>` MUST only answer that role's waiting `listen`
question and MUST NOT go into any turn.

**4.10.1.5** A line MUST go into a session only while a turn is open there, one line per agent at a
time until the agent acknowledges it; a line that cannot go in MUST wait, and the next turn to start
for its target MUST take the oldest such line into its prompt.

**4.10.1.6** A line a session takes MUST be recorded with `said`; a line the backend refuses MUST be
recorded with `refused` and return to the head of the queue; lines a turn ended holding MUST be
recorded with `unheld`; lines still waiting when an epic stops or ends MUST be recorded with
`dropped`.

**4.10.1.7** Claims MUST NOT restrict a line said to an agent or session.

#### 4.10.2. Claims and questions

**4.10.2.1** A claimed `Outworlder` role MUST be answered, spoken to as `outworlder:<role>`, and set
away only by the frontend claiming it; `take` MUST move a claim from another frontend.

**4.10.2.2** A claim MUST be released when its frontend leaves, and the `owner` of its questions
MUST become `null`.

**4.10.2.3** A question MUST be recorded only while its epic is going, the host is open, and its
role is not away; otherwise the flow MUST receive no answer at once.

**4.10.2.4** A question MUST be answerable by its role's claimant, or by any frontend where the role
is unclaimed, the first answer winning; it MUST stay waiting with no frontend attached.

**4.10.2.5** A question MUST be `ask` where it has options or a turn is open, else `listen`; a
question asked while exactly one session has a turn open MUST carry that session's key.

**4.10.2.6** A question MUST be withdrawn with `away` when its role goes away, and with `over` when
its epic stops or ends, is forced, or the host closes.

#### 4.10.3. Away

**4.10.3.1** Away MUST be held per role by the host and MUST outlive the frontend that set it.

**4.10.3.2** `afk` with a role MUST set that role; `afk` without a role MUST, where no role is
claimed, set every role and clear every per-role value, and, where roles are claimed, leave the
value of every role another frontend claims unchanged.

### 4.11. Limits

**4.11.1** A host MUST NOT wait on a slow frontend: where more than 64 MiB of messages wait for one
frontend, the host MUST let it go with `gone`, sent after the frame in progress.

**4.11.2** Every text longer than 262 144 characters in a history record or a snapshot MUST be cut
to that length followed by `… (<n> more characters)`, `n` the characters cut.

### 4.12. Protocol versions

**4.12.1** The protocol version this document defines MUST be `2`.

**4.12.2** The daemon MUST write its protocol version in the daemon record (Section 7.6.2 of
[FILES]), and a host MUST send it in `welcome`.

**4.12.3** A client finding a daemon of another protocol version, or of none, MUST NOT reach it and
MUST NOT start a daemon beside it, and MUST report `the runs in <workspace> are held by an older
Humanize (pid <pid>); stop it with that version`, with `on this machine` in place of `in
<workspace>` where no workspace is concerned.

**4.12.4** The daemon and a host MUST answer a reader that speaks another protocol, by a frame kind
they do not know, with `GONE` as Section 4.5.8 states.

### 4.13. Lifecycle

#### 4.13.1. The daemon

**4.13.1.1** There MUST be at most one daemon per machine and user, and it MUST hold the hosts of
every workspace.

**4.13.1.2** The daemon MUST have no controlling terminal and MUST ignore `SIGHUP`.

**4.13.1.3** The daemon MUST refuse a second host of one slot of one workspace while the first is
alive.

**4.13.1.4** The daemon MUST exit once it has held no host for 2 seconds, or 60 seconds after it
started where no host was ever taken on, and on `SIGTERM`.

#### 4.13.2. Hosts

**4.13.2.1** Each host MUST run in a process of its own whose current directory is its workspace.

**4.13.2.2** The hosts of a workspace MUST run its epics as Section 3.3 states.

**4.13.2.3** A host MUST send every line its process prints on its standard output or standard error
to every frontend as a `printed` record, one line per record.

**4.13.2.4** A host MUST ignore `SIGINT`.

#### 4.13.3. Idle hosts

**4.13.3.1** A host MUST close once it is idle and either a frontend has ever said `hello` to it or
60 seconds have passed since it started.

**4.13.3.2** A host MUST read as idle where no frontend is attached, no epic is going, starting or
stopping, and no epic awaits a frontend.

**4.13.3.3** An epic that ended while no frontend was attached, and that no frontend stopped, MUST
await a frontend until one attaches, except a chat that folded.

#### 4.13.4. Hosts losing the daemon

**4.13.4.1** A host whose daemon has gone MUST close as Section 4.13.6 states.

#### 4.13.5. Killing

**4.13.5.1** `SIGTERM` to a host process MUST close the host as Section 4.13.6 states and MUST leave
the daemon and every other host running.

#### 4.13.6. Closing a host

**4.13.6.1** Closing a host MUST withdraw every waiting question, drop every waiting line, stop
every epic, let every frontend go with `gone` `the host was closed`, and close every side
conversation.

**4.13.6.2** Closing a host MUST wait at most 15 seconds, from the first close, for its epics to
release what they made, and the host process MUST then exit.

**4.13.6.3** A connection arriving at a closed host MUST be closed at once.

#### 4.13.7. Failures

**4.13.7.1** Whatever a frontend sends, other than `stop`, `force` and `quit`, MUST NOT end an
epic.

**4.13.7.2** A failure that belongs to an epic MUST be written to that epic's `host.log` (Section 6
of [FILES]), and one that belongs to none to `daemon.log` in the daemon directory (Section 7 of
[FILES]).

#### 4.13.8. Folding a chat

**4.13.8.1** A chat's host MUST fold its chat once the chat has waited between turns with no
frontend attached for 60 seconds; folding MUST set every role away, MUST answer the waiting
question with nothing, and MUST end the chat `done`.

**4.13.8.2** A folded chat host MUST refuse `start` (Section 4.8.2.3); a folded chat is carried on
by starting the `chat` flow on a new slot with `resume` its epic directory, which continues in that
same epic.

## 5. Security Considerations

Who can connect. The daemon is reached only through the Unix stream socket `daemon.sock` in the
daemon directory (Section 4.2.2 and Section 4.2.3). That directory is created with mode `0700` and
is refused where it is not owned by the user or is writable by its group or by others (Section 4.3.2
of this document, Section 7.3.1 of [FILES] and Section 7.3.2 of [FILES]); the socket and the daemon
record have mode `0600` (Section 7.6.1 of [FILES] and Section 7.6.2 of [FILES]). The wire protocol
of Section 4 carries no credential of its own: the file modes are what confine the socket to the
one user of the one machine (Section 3.3.1 and Section 3.3.6). Every frontend that connects is
whole (Section 3.6.1): it is able to start, steer, stop and force epics, to take over a role another
frontend claims, and to close the host (Section 3.6.5, Section 4.8.6.2 and Section 4.8.9.3). The
name a frontend gives in `hello` is taken as given and is not verified (Section 4.7.1.5).

What a client trusts. A client reads a daemon as present only where the daemon record names an
existing process and the socket accepts a connection, never on the strength of the socket file alone
(Section 4.4.1 and Section 4.4.3). A reader closes a connection that announces a payload above
4 194 304 bytes (Section 4.5.3), and a host lets go a frontend for which more than 64 MiB of
messages wait (Section 4.11.1), so that one slow or misbehaving peer does not hold up an epic or
another frontend (Section 3.6.8 and Section 4.7.3.2).

Version mismatch. A client that finds a daemon record of another protocol version, or of none, sends
no further frame to the socket, starts no daemon beside it and reports the refusal of Section 4.12.3
(Section 3.7.4, Section 3.7.5 and Section 4.4.4). The daemon and a host answer a frame kind they do
not know with one `GONE` frame and close the connection (Section 4.5.8 and Section 4.12.4).
Installing another release does not stop a daemon or its epics (Section 3.7.2).

Remote daemons. A connection to an SSH daemon is carried by `ssh` with the user's own keys and ssh
config, and never asks for a password or the acceptance of a host key (Section 3.8.1.4 and Section
3.8.2.10). The `hmz web` started on the remote machine listens on that machine's loopback alone, and
is reached through a port forwarded from this machine's loopback (Section 3.8.2.2 to Section
3.8.2.4); it holds its own key, which is not shown to the user or to the page (Section 3.8.2.5).
Reaching an SSH daemon can install hmz, and uv, on the remote machine (Section 3.8.3.2), and does
not replace an hmz there whose daemon holds running epics (Section 3.8.3.3).

P2P daemons. A P2P daemon is kept as a secret of at least 16 bytes (Section 3.8.5.1). The EasyTier
network name, the network secret and the key of the server's `hmz web` are derived from that secret,
which itself does not leave the machine it is set on and is not passed on any command line (Section
3.8.5.2). Whoever holds the secret reaches the server's `hmz web`, and through it the epics of that
machine's daemon (Section 3.8.5.3 and Section 3.8.5.4). The two ends meet only through the shared
EasyTier nodes they name (Section 3.8.5.10). EasyTier runs without root and without a virtual
network device (Section 3.8.5.5), and the EasyTier binary hmz downloads is checked against a pinned
SHA-256 unless `HUMANIZE_EASYTIER` names another binary (Section 3.8.5.6).

## 6. References

### 6.1. Normative References

- **[RFC2119]** Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels", BCP 14, RFC
  2119, March 1997, <https://www.rfc-editor.org/info/rfc2119>.
- **[RFC8174]** Leiba, B., "Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words", BCP 14, RFC
  8174, May 2017, <https://www.rfc-editor.org/info/rfc8174>.
- **[CORE]** "The Humanize Protocol: Core Concepts and Functional Behaviour", [`core.md`](core.md).
- **[CLI]** "The Humanize Protocol: Command-Line Interface", [`cli.md`](cli.md).
- **[TUI]** "The Humanize Protocol: Terminal Interface", [`tui.md`](tui.md).
- **[WEB]** "The Humanize Protocol: Web Interface", [`web.md`](web.md).
- **[PYTHON]** "The Humanize Protocol: Python Interfaces", [`python.md`](python.md).
- **[FILES]** "The Humanize Protocol: Settings, Environment Variables and Files", [`files.md`](files.md).

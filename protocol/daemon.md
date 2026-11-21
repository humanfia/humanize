# The Humanize Protocol: Daemon

## Abstract

This document specifies the hmz daemon: the behaviour a user observes of the process that holds a
machine's epics apart from every frontend, how it is reached from this machine and from others, and
every RPC method it serves to its clients.

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
  - [3.9. Listeners, pairing and services](#39-listeners-pairing-and-services)
- [4. RPC Methods](#4-rpc-methods)
  - [4.1. Scope](#41-scope)
  - [4.2. Terminology](#42-terminology)
  - [4.3. The daemon directory](#43-the-daemon-directory)
  - [4.4. Finding the daemon](#44-finding-the-daemon)
  - [4.5. Parameters common to many methods](#45-parameters-common-to-many-methods)
  - [4.6. Hosts](#46-hosts)
  - [4.7. Attaching to a host](#47-attaching-to-a-host)
  - [4.8. Calls to an epic](#48-calls-to-an-epic)
  - [4.9. Messages](#49-messages)
  - [4.10. Semantics a frontend observes](#410-semantics-a-frontend-observes)
  - [4.11. Limits](#411-limits)
  - [4.12. Protocol versions](#412-protocol-versions)
  - [4.13. Lifecycle](#413-lifecycle)
  - [4.14. Sessions, pairing and devices](#414-sessions-pairing-and-devices)
  - [4.15. Side questions](#415-side-questions)
  - [4.16. Epics written down](#416-epics-written-down)
  - [4.17. Flows, workspaces and paths](#417-flows-workspaces-and-paths)
  - [4.18. Settings](#418-settings)
  - [4.19. Notices](#419-notices)
  - [4.20. Methods and the interfaces they replace](#420-methods-and-the-interfaces-they-replace)
  - [4.21. Reach](#421-reach)
  - [4.22. Ai-chan conversations](#422-ai-chan-conversations)
  - [4.23. Envs of an epic](#423-envs-of-an-epic)
  - [4.24. Environments](#424-environments)
  - [4.25. Chats](#425-chats)
- [5. Security Considerations](#5-security-considerations)
- [6. References](#6-references)
  - [6.1. Normative References](#61-normative-references)

## 1. Introduction

This document specifies the hmz daemon: the behaviour a user observes of the process that holds a
machine's epics apart from every frontend, how it is reached from this machine and from others, and
every RPC method it serves to its clients. Every frontend is a client of a daemon, over the
carriers, sessions and frames of [WIRE].

This document is organised as follows:

- Section 3: Daemon Behaviour.
- Section 4: RPC Methods.

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
that started them; how a daemon of one release meets a frontend of another; how a frontend reaches
the daemon of another machine; and how a daemon listens beyond its socket, pairs devices and runs
as a service.

Out of scope:

- Carriers, routes, device identity, pairing codes, the relay and the frames of a session: [WIRE].
- The methods a client calls, their parameters, results and refusals: Section 4.
- The files the daemon keeps on this machine: Section 7 of [FILES] and Section 4.14 of [FILES].
- The settings the remote daemons and the listeners are kept in: Section 3 of [FILES].
- What a chat is, and how a chat folds away: Section 8 of [CORE].
- What Ai-chan is and what she can do: Section 14 of [CORE].
- How the page presents daemons: Section 3.13 of [WEB].
- How the terminal interface presents daemons and `/exit`: [TUI].
- The release check and `hmz update`: Section 13 of [CORE].
- The command lines of `hmz daemon` and `hmz relay`: Section 13 of [CLI] and Section 14 of [CLI].

### 3.2. Terminology

**3.2.1** A **host** is what holds the epics of one workspace, of one chat of a workspace, of one
Ai-chan conversation, or of one epic `hmz exec` started, for every frontend attached to them. A host
held by the daemon is held apart from every frontend.

**3.2.2** The **workspace host** of a workspace is the host that runs that workspace's flows. A
**chat host** is a host that runs one chat of a workspace, an **Ai-chan host** one that runs one
Ai-chan conversation (Section 14 of [CORE]), and an **exec host** one that runs the one epic of one
`hmz exec`, each beside the workspace host.

**3.2.3** A frontend **attaches** to a host when it starts reading and steering the epics that host
holds, and **detaches** when it stops, without stopping them.

**3.2.4** A host is **idle** when no frontend is attached to it, no epic is going, starting or
stopping on it, and it keeps no ended epic for the next frontend under Section 3.5.5.

**3.2.5** A daemon is **older** than a frontend when it speaks a protocol of an earlier version than
the frontend, and **newer** when it speaks a protocol of a later one (Section 6.5 of [WIRE]).

**3.2.6** A **remote daemon** is the daemon of another machine, reached from this machine over a
route of [WIRE]. A remote daemon whose first route is `stdio:ssh` is an **SSH daemon**, one whose
first route is `easytier:` a **P2P daemon**, and any other a **paired daemon**, as the frontends
that switch between daemons name them.

**3.2.7** **Local** is the daemon of this machine, as the frontends that switch between daemons name
it.

**3.2.8** **EasyTier** is the peer-to-peer virtual network of that name.

**3.2.9** A **listener** is a carrier end the daemon offers beside its socket (Section 3.9).

### 3.3. One daemon per machine and user

**3.3.1** There MUST be at most one daemon per machine and user.

**3.3.2** The daemon MUST hold the epics of every workspace of its machine and user.

**3.3.3** The daemon MUST hold one workspace host per workspace, one chat host per chat, one Ai-chan
host per Ai-chan conversation a host holds and one exec host per `hmz exec` beside it; each host
MUST run in a process of its own, standing in its workspace.

**3.3.4** A chat host, an Ai-chan host, an exec host and the workspace host of one workspace MUST
NOT wait on each other; how many epics each runs at a time is stated in Section 3.4.3 of [CORE] and
Section 8.6 of [CORE].

**3.3.5** Two spellings of one directory MUST name one workspace, and two directories MUST name two
workspaces.

**3.3.6** The daemon MUST belong to the machine it runs on, and MUST NOT be shared between machines
that mount one home.

**3.3.7** Two clients racing to start the daemon, or a host of one slot of one workspace, MUST end
with one daemon, or one host, which both use.

**3.3.8** A frontend MUST NOT hold an epic in its own process: the terminal interface, `hmz exec`,
the page, the desktop application and every program using the SDK MUST each run and hold every epic
through a daemon -- this machine's, or, for a program's tests on fakes, a private daemon of that
program (Section 4.19 of [PYTHON]).

### 3.4. Starting

**3.4.1** The daemon of this machine MUST start when the first client on this machine needs it --
over `unix:` or `stdio:local`, or by `hmz daemon connect --stdio` run over `ssh` or WSL -- and MUST
NOT need to be started by the user.

**3.4.2** `hmz daemon serve` and the service `hmz daemon install` writes (Section 3.9.6) MUST start
the daemon in the foreground of their process, where none runs.

**3.4.3** Where the daemon cannot be started or reached, the terminal interface, `hmz exec` and `hmz
web` MUST say `hmz: the daemon cannot be reached: <why>` on standard error and exit with status 1,
and MUST NOT hold the epics in their own process.

**3.4.4** A frontend MUST be told whether the daemon and the host came up, and MUST be told a
failure to start with its reason, without waiting out a timeout.

**3.4.5** Asking the daemon which epics are going MUST NOT start a host.

**3.4.6** A daemon `hmz daemon serve` starts with no terminal, as the service of Section 3.9.6 does,
MUST take, once as it starts, the environment its user's login shell gives, MUST keep its own where
that shell does not answer within 5 seconds, and MUST append to `PATH` each of `~/.local/bin`,
`$UV_TOOL_BIN_DIR`, `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin` and `/bin` that it lacks; any
other daemon MUST keep the environment it was started with.

**3.4.7** Every host MUST take the daemon's environment; a changed environment MUST NOT reach a
daemon that is running, and reaches its hosts once the daemon is started again.

### 3.5. Epics outlive their frontends

**3.5.1** The daemon and every host MUST outlive the terminal and the frontend that started them.

**3.5.2** A hangup, a closed terminal or a frontend exiting MUST NOT end the daemon or a host.

**3.5.3** A frontend, or the failure of a frontend, MUST NOT end an epic other than by a request to
stop it.

**3.5.4** A host MUST go once it is idle, provided a frontend has attached to it at least once or 60
seconds have passed since it started.

**3.5.5** A host MUST keep an epic that ended while no frontend was attached, and that nobody
stopped, until a frontend attaches; it MUST NOT keep a chat or an Ai-chan conversation that folded
away, nor the epic of an exec host.

**3.5.6** A chat host MUST fold its chat away as Section 8 of [CORE] specifies, and an Ai-chan host
its conversation as Section 14.8 of [CORE] specifies, and each MUST then go once it is idle.

**3.5.7** The daemon MUST go once it holds no host and no session is open, and MUST go 60 seconds
after it started where no host ever came and no session is open, except as Section 3.9.4 states.

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

**3.6.1** hmz MUST let any number of frontends -- the terminal interface, `hmz exec`, the page,
the desktop application and programs using the SDK -- attach to one host at once, each whole and
each its own, over any session of [WIRE].

**3.6.2** A frontend that attaches MUST be told everything kept of the epic going or the last one,
from its start, then how everything stands, then everything as it happens.

**3.6.3** What one frontend does to an epic MUST be seen by every frontend attached to it, with the
name of the frontend that did it.

**3.6.4** Each frontend MUST be named by the user and the kind of frontend, and Ai-chan as Section
14.7.1 of [CORE] names her; two frontends of one name MUST be told apart by a number.

**3.6.5** hmz MUST let any attached frontend: start an epic; resume an epic; say a line to the epic,
to one agent, to one session or to one person; answer a question; stop an epic; force a stopping
epic, closing every session under its open turn; set a role away or back; claim a role, take it over
and release it; change the board; ask a side question; and use the environments of the epic as
Section 7.13 of [CORE] states.

**3.6.6** A frontend that detaches, closes or is lost MUST leave the epics going, MUST release the
roles it claimed, and MUST leave every role it set away as it set it.

**3.6.7** A question MUST stay asked while no frontend is attached, and MUST be offered to every
frontend once the frontend that claimed its role detaches.

**3.6.8** A frontend that falls too far behind what it is told MUST be told so and detached, and
MUST NOT hold up the epic or another frontend.

**3.6.9** The terminal interface MUST offer, on leaving while a flow is going, to stop the flow or
to detach, as [TUI] specifies.

**3.6.10** Running the terminal interface again in the same workspace MUST attach it to that
workspace's host, and MUST show the epic from its start.

**3.6.11** A frontend whose session drops MUST attach again once a session is up again, as Section
3.6 of [WIRE] states, and MUST be told only what it has not been told where its host still keeps it
(Section 6.8.4 of [WIRE]).

### 3.7. Versions

**3.7.1** A daemon MUST hold its epics under the release of hmz it started with, until it goes.

**3.7.2** Installing another release of hmz, by `hmz update` or otherwise, MUST NOT stop the daemon
or any epic it holds.

**3.7.3** Once a daemon of an earlier release than the one installed has gone, the next client that
needs a daemon MUST start one of the release installed.

**3.7.4** A client MUST NOT use a daemon that refuses its protocol (Section 6.5.5 of [WIRE]), and
MUST NOT start a daemon beside one.

**3.7.5** A frontend that finds this machine's epics held by an older daemon MUST refuse them,
saying `the runs on this machine are held by an older Humanize (pid <pid>); stop it with that
version`.

**3.7.6** The terminal interface, `hmz exec` and `hmz web` MUST say that refusal on standard error
and exit with status 1; the page MUST say it of a remote daemon that answers it, and MUST serve
every other daemon.

**3.7.7** A daemon MUST tell a client that is older than it ``held for frontends by a newer
Humanize; `hmz` of it reads it``, as Section 6.5.6 of [WIRE] states.

### 3.8. Remote daemons

#### 3.8.1. Keeping them

**3.8.1.1** The remote daemons MUST be kept by each client for itself: by the terminal interface,
`hmz exec` and the SDK in the settings of this machine (Section 3.4.6 of [FILES]), and by the page
and the desktop application in the page's own storage (Section 3.13 of [WEB]).

**3.8.1.2** Each remote daemon MUST be kept as its name, the daemon id the client pins (Section
4.4.7 of [WIRE]), `""` until it is first reached over a trusted carrier, and its routes, in the
order they are tried.

**3.8.1.3** Local MUST always be present, and MUST NOT be removed, renamed or written among the
remote daemons.

**3.8.1.4** The name of a remote daemon MUST start with a letter or a digit, MUST consist of
letters, digits, `.`, `_` and `-`, and MUST NOT be `local`.

**3.8.1.5** A remote daemon MUST be added from a pairing code (Section 4.5 of [WIRE]), taking its id
and routes, or from routes alone where its first route is trusted.

**3.8.1.6** Removing a remote daemon MUST forget only how to reach it; the epics and the hmz on its
machine, and its pairing of this device, MUST stay as they are.

#### 3.8.2. Reaching one

**3.8.2.1** A remote daemon MUST be reached when a frontend first asks for it or the user asks to
connect to it, by racing its routes as Section 3.6 of [WIRE] states.

**3.8.2.2** A remote daemon MUST be in exactly one of these states:

| State | Meaning |
| --- | --- |
| `idle` | Not reached yet |
| `connecting` | A route is being opened: ssh reaching the host, EasyTier joining, a relay joining |
| `installing` | hmz is being installed on the host, or EasyTier on this machine |
| `up` | A session is up |
| `failed` | Not reached, with the reason |

**3.8.2.3** Each state MUST carry what was said last, including the last line of an install.

**3.8.2.4** A session to a remote daemon that drops or fails MUST be tried again as Section 3.6.4 of
[WIRE] states.

**3.8.2.5** The client that reached a remote daemon going MUST close its sessions and stop the
`ssh`, `wsl.exe` and EasyTier processes it started for it; the epics on that machine MUST keep
going, held by its daemon.

**3.8.2.6** Reaching a remote daemon MUST NOT ask the user for a password or to accept a host key; a
host that needs either MUST fail with what ssh said.

**3.8.2.7** A remote daemon whose id is pinned and which answers with another id MUST be `failed`
with `<name> is not the daemon it was paired with.`; one first reached over a trusted carrier MUST
have the id it answered pinned.

#### 3.8.3. The hmz on a remote machine

**3.8.3.1** Before running `hmz daemon connect --stdio` over a `stdio:ssh` route, the client MUST
find the hmz there as a login shell finds it, with `~/.local/bin` included, and MUST learn its
version.

**3.8.3.2** Where no hmz is there, or one of another release, the client MUST install hmz of its
own release there as a uv tool, installing uv there first where none is, and MUST be `installing`
while it does.

**3.8.3.3** The client MUST NOT replace an hmz there while that machine's daemon holds running
epics, and MUST NOT replace it where it cannot tell; it MUST then use the hmz there and say `hmz
<there> there holds running epics; hmz <wanted> waits`, or `Whether hmz <there> there runs epics is
unknown; not replaced`.

**3.8.3.4** An install that fails MUST leave the remote daemon `failed` with the last line uv said,
or `hmz <wanted> could not be installed.`; an install after which another version answers MUST leave
it `failed` with `hmz <wanted> was installed, and hmz <there> answers.`

**3.8.3.5** A development build of hmz, version `0.0.0`, MUST install nothing on a remote machine
and MUST use the hmz there; where none is there, the remote daemon MUST be `failed` with `hmz is not
installed on <name>.`

**3.8.3.6** A client MUST install nothing on the machine of a route other than `stdio:ssh`.

#### 3.8.4. Using one

**3.8.4.1** A frontend that switches between daemons MUST show one daemon at a time, and MUST show
of a remote daemon everything it shows of Local: its workspaces, its epics, attaching to, starting
and steering epics there, its flows, and its daemon settings.

**3.8.4.2** A frontend MUST say a remote daemon that is not `up` is unavailable, with its state,
wherever it asks it something.

#### 3.8.5. EasyTier

**3.8.5.1** An EasyTier network MUST be kept, on each side, as an EasyTier entry of a name and a
secret of at least 16 bytes in UTF-8, and the shared EasyTier nodes it meets through (Section 3.4.10
of [FILES]); a shorter secret MUST be refused with `A secret must be at least 16 bytes.`

**3.8.5.2** The name and the secret of the EasyTier network MUST be derived from the secret by
SHA-256, each under a label of its own: the name the SHA-256 of the UTF-8 of `hmz-easytier-name`, a
NUL and the secret, and the network's secret that of `hmz-easytier-secret`, a NUL and the secret,
each in lowercase hexadecimal; the secret itself MUST NOT leave the machine it is set on, nor be
passed on any command line.

**3.8.5.3** A daemon whose `listen` names `easytier:<name>` MUST join the network of that entry and
make a TCP listener of its own, on its machine's loopback alone and at the port 41817, reachable
over that network at the virtual address `10.144.144.1`, which it MUST take, and at that port
alone, carrying mutual TLS as any `tcp` listener does.

**3.8.5.4** A client opening `easytier:<name>` MUST join the network of its own entry of that name,
expose the daemon's port, `10.144.144.1:41817`, on a port of this machine's loopback, wait until it
answers, and then open mutual TLS over it as Section 4.4 of [WIRE] states.

**3.8.5.5** EasyTier MUST run without root and without a virtual network device, on either side.

**3.8.5.6** hmz MUST download the official release of EasyTier of the version it pins, for this
machine's system and architecture, into its home, MUST check it against the SHA-256 it pins, and
MUST reuse it once there; a P2P daemon MUST be `installing` while it downloads, saying `Downloading
EasyTier <version>`, and `failed` with the reason where the download or the check fails.
`HUMANIZE_EASYTIER` naming an existing binary MUST be used in its place.

**3.8.5.7** An EasyTier entry MUST name at least one shared EasyTier node, as a URL
`<protocol>://<host>:<port>` with protocol `tcp`, `udp`, `ws`, `wss`, `quic` or `wg`, and the two
sides MUST meet only through the nodes they name; hmz MUST NOT name a node of its own, and a client
reaches a daemon only where both name a node in common. An entry that names no node MUST be refused
with `An EasyTier daemon needs at least one node.`

**3.8.5.8** hmz MUST offer the shared nodes of EasyTier's community, as the status page EasyTier's
own apps read lists them, each with its URL, its name, its version, whether it is up and its uptime
over the last 24 hours; a list that cannot be read MUST be said to be unreadable with the reason,
and nodes the user types MUST be taken all the same.

**3.8.5.9** Removing a daemon's `easytier:` listener MUST stop its EasyTier, and MUST NOT stop any
epic it holds.

### 3.9. Listeners, pairing and services

**3.9.1** The daemon MUST always accept sessions on its socket, and MUST also listen on each
listener the setting `listen` names (Section 3.4.8 of [FILES]) and each `--listen` of `hmz daemon
serve`.

**3.9.2** A listener spec MUST be one of: `tcp://<address>:<port>`, a TCP listener carrying mutual
TLS; `ws://<address>:<port>`, a WebSocket listener carrying mutual TLS in its binary messages, which
answers every other request 404; `relay:<ws-url>`, a registration with that relay (Section 5.4 of
[WIRE]) accepting native joins; `webrtc:<ws-url>`, a registration with that relay answering WebRTC
joins (Section 4.7 of [WIRE]); and `easytier:<name>` (Section 3.8.5.3). A port `0` MUST mean any
free port.

**3.9.3** The route of a listener, as a pairing code carries it, MUST be the listener spec, with an
unspecified address (`0.0.0.0` or `::`) replaced by this machine's host name and a port `0` by the
port taken.

**3.9.4** A daemon with any listener, or started by `hmz daemon serve` or its service, MUST NOT go
for want of hosts or sessions, and MUST go on `SIGTERM` alone.

**3.9.5** A listener that cannot be opened, or a relay that cannot be reached, MUST be written to
`daemon.log` and tried again as Section 3.6.4 of [WIRE] states, and MUST NOT keep the daemon from
serving its socket and its other listeners.

**3.9.6** `hmz daemon install` MUST write, enable and start a service that runs `<hmz> daemon serve`
(`<hmz>` the absolute path of the hmz that ran it) for the user at login and keeps it running: on
macOS the launchd agent `~/Library/LaunchAgents/ai.humanfia.hmz.daemon.plist`, loaded with
`launchctl bootstrap gui/<uid>`; on Linux the systemd user unit
`~/.config/systemd/user/hmz-daemon.service`, enabled with `systemctl --user enable --now`. `hmz
daemon uninstall` MUST stop, disable and remove it.

**3.9.7** A daemon MUST pair devices and revoke them as Section 4.5 of [WIRE] and Section 4.6 of
[WIRE] state; every session of any carrier MUST then be as whole as a session over its socket, but
for terminals (Section 4.24.4.10).

**3.9.8** A daemon MUST fetch the newest release of hmz as Section 13.3 of [CORE] states, and every
flowverse's index once as it starts, without telling any client.

**3.9.8.1** A daemon MUST, as it starts, begin a scan (Section 4.18.3.6) of every installed harness,
as each account it runs as, that was never asked what it runs or was last asked more than 7 days
ago. The scan MUST run apart from everything the daemon serves, asking one harness at a time: it
MUST NOT delay the daemon's listening or the answer to any call, and a harness that does not answer
MUST be left as it was. `HUMANIZE_SCAN` (Section 3.11.2.8.1 of [FILES]) MUST turn it off.

## 4. RPC Methods

### 4.1. Scope

Section 4 governs every method the daemon serves and every notification it sends, as a client sees
them over a session of [WIRE]: where a client finds the one daemon of **this machine**, the methods
of each namespace, their parameters, results and refusals, the messages of an epic subscription, and
every obligation of the daemon and its hosts that a client observes. [OPENRPC] lists the same
methods with the JSON Schema of each. The internal structure of the daemon, of its host processes
and of the links between them is not governed by this document.

Out of scope:

- Carriers, session security, frames, `session.hello`, error codes, idempotency, subscriptions and
  file chunks as such: [WIRE].
- The Python objects that speak this protocol: Section 4 of [PYTHON].
- The files of the daemon directory as files on disk, and their cleanup: Section 7 of [FILES].
- The files an **epic** writes, `host.log` among them: Section 6 of [FILES].
- What a flow, a chat and a side question do beyond what is carried here: Section 3 of [CORE],
  Section 8 of [CORE], Section 9 of [CORE].

### 4.2. Terminology

**4.2.1** Every term of Section 2 of [CORE] and of [WIRE] MUST carry the meaning given there.

**4.2.2** **Daemon directory**: the machine directory `<mdir>` of Section 7.2.2 of [FILES].

**4.2.3** **Socket**: the Unix stream socket `daemon.sock` in the daemon directory.

**4.2.4** **Daemon record**: the file `daemon.json` in the daemon directory.

**4.2.5** **Workspace path**: a workspace directory as an absolute path with every symbolic link
followed. Two spellings of one directory are one workspace path.

**4.2.6** **Slot**: the text naming one host of a workspace: `""` for the workspace's own host,
`chat:` followed by 1 to 32 lowercase hexadecimal digits for the host of one chat, `ai:` followed by
1 to 32 lowercase hexadecimal digits for the host of one Ai-chan conversation, or `exec:` followed by
1 to 32 lowercase hexadecimal digits for the host of one `hmz exec`.

**4.2.7** The term host MUST carry the meaning Section 3.2.1 gives it; each slot of a workspace
names one host, which a client reaches only through the daemon.

**4.2.8** **Epic subscription**: the subscription `epic.attach` opens (Section 6.8 of [WIRE]); one
epic subscription is one attached frontend.

**4.2.9** **Call to an epic**: a method of Section 4.8, which names an epic subscription in `sub`.

**4.2.10** **Reply**: what a host answers one call to an epic: its fields where it carries it out,
or `why`, one sentence, where it refuses it.

**4.2.11** **Message**: one JSON object an epic subscription carries, naming its kind in its field
`type`.

**4.2.12** **Client id**: the text `c<n>` a host gives one attached frontend, `n` counting from 1
per host and never reused.

**4.2.13** **History record**: a message that carries the field `seq` (Section 4.9.2).

**4.2.14** **Snapshot**: a message without `seq` that says how one thing stands now (Section 4.9.3).

**4.2.15** **Epic number**: the number a host gives each epic it starts, counting from 1 per host.

**4.2.16** An epic name (Section 3.2.1 of [CORE]) MUST be written as Section 6.2.2 of [FILES]
states.

**4.2.17** **Epic row**: the JSON object Section 4.16.2 defines.

**4.2.18** **Notice**: the JSON object Section 4.19.1 defines.

**4.2.19** **Reach**: the reach of an Ai-chan conversation (Section 14.2.5 of [CORE]) that a session
carries (Section 4.21).

**4.2.20** **Scoped link**: the socket on which the daemon admits the session of one Ai-chan
conversation, held to its reach (Section 4.22.6).

### 4.3. The daemon directory

**4.3.1** The daemon directory MUST NOT be under the **home** directory.

**4.3.2** The daemon directory, the socket and the daemon record MUST be created, refused and
removed as Section 7.3 of [FILES] and Section 7.6 of [FILES] state.

**4.3.3** Where the full path of the socket exceeds 100 bytes, a client MUST still connect to the
socket, and MUST have the current directory it had before once it has connected.

### 4.4. Finding the daemon

**4.4.1** A client on this machine MUST read a daemon as present only where the daemon record parses
as a JSON object whose `pid` is an integer naming an existing process, and the socket accepts a
connection within 1 second.

**4.4.2** A client MUST count a process that exists but that it cannot signal as existing.

**4.4.3** A client MUST NOT read a daemon as present on the strength of the socket file alone.

**4.4.4** Where the daemon record's `protocol` is absent, is not text, or names another major
version than the client's, the client MUST NOT connect to the socket and MUST refuse as Section
3.7.5 states.

**4.4.5** A client that starts the daemon MUST wait at most 10 seconds for it to come up, and MUST
report a failure the started process reports as soon as it is reported.

**4.4.6** Where two clients start the daemon at once, exactly one daemon MUST come up, and both
clients MUST use it.

**4.4.7** The daemon MUST start the hosts; where two calls need a host of one slot of one workspace
at once, exactly one host MUST be taken on, and both MUST use it.

### 4.5. Parameters common to many methods

**4.5.1** A method MUST take exactly the parameters its paragraph and [OPENRPC] list, with the
stated types and defaults; a parameter not sent MUST take its default, and one sent that the method
does not take MUST be refused as Section 6.6.3 of [WIRE] states.

**4.5.2** `workspace` MUST name a **workspace** by an absolute path of the daemon's machine, `~`
expanded there; one that is not absolute after that MUST be refused 400, `Say the workspace as a
whole path, not <workspace>.`, and one naming no directory 404, `There is no directory <path>.`,
except where a method states the workspace need not exist or that it reads an epic of a workspace
since removed. A method that names a host by `workspace` and `slot` and MUST NOT start one -- those
of Section 4.6 but `hosts.open`, of Section 4.23, `btw.list`, `btw.leave`, `chat.say`,
`chat.commands`, `chat.set` and `chat.stop` -- MUST NOT refuse a `workspace` for naming no
directory: it MUST answer as it does for the host that holds it, or for none. Nor MUST
`epic.attach` refuse one where a host of that `workspace` and `slot` is held already.

**4.5.3** `slot` absent or `""` MUST mean the workspace's own host; one that is not a slot, nor
`chat:` or `exec:` alone where Section 4.7.1.2 or Section 4.25.1.1 permits it, MUST be refused 400,
`<slot> is not a slot.`

**4.5.4** `idem` MUST be taken by every write as Section 6.7 of [WIRE] states.

**4.5.5** `here` MUST be a directory a client calls its own -- the directory `hmz web` or the
terminal interface started in -- which a method that takes it orders first; it MUST NOT be read as a
workspace written down.

### 4.6. Hosts

#### 4.6.1. General

**4.6.1.1** The methods of Section 4.6 but `hosts.open` MUST NOT start a host, and a call that names
a workspace and slot no host holds MUST be refused 404, `no runs are held in <workspace>`, with `
for <slot>` appended where `slot` is not `""`.

**4.6.1.2** A call of Section 4.6 MUST NOT count as a frontend attached to the host.

#### 4.6.2. `hosts.list`, `hosts.running` and `hosts.open`

**4.6.2.1** `hosts.list` MUST be answered `{"held": [...]}`, one entry per host taken on, in the
order taken on, each with `pid`, `workspace`, `started` and `slot`.

**4.6.2.2** `hosts.running` MUST answer `running`, holding, for every host whose epic or chat is
going or stopping, `state`, `run`, `kind`, `flow`, `epic`, `chat`, `task` and, of a chat or an
Ai-chan conversation, `turn` from its status, each with `workspace`, `slot` and `asking` (the
questions it waits on, each `<run>:<question>`).

**4.6.2.3** `hosts.open` `{workspace, slot}` MUST start the host of that workspace and slot where
none is, as `epic.attach` does (Section 4.7.1.2 to Section 4.7.1.4), MUST NOT attach to it, and MUST
be answered with its host-process keys (Section 4.6.4.2) and `slot`.

#### 4.6.3. `hosts.status`, `hosts.detach` and `hosts.stop`

**4.6.3.1** `hosts.status` `{workspace, slot}` MUST be answered with the host's own `pid`,
`workspace`, `slot`, `started`, `kind` (`"host"`) and `protocol`, and every key of Section 4.6.4.

**4.6.3.2** `hosts.detach` `{workspace, slot}` MUST let every attached frontend go with `gone` `let
go`, leave every epic running, and be answered `{"let_go": <n>}`, `n` the number let go.

**4.6.3.3** `hosts.stop` `{workspace, slot}` MUST be a write, MUST be answered `{}` before anything
else happens, and the host MUST then close as Section 4.13.6 states.

#### 4.6.4. Status

**4.6.4.1** The status of a host MUST carry the keys of the following list, and a client MUST read
an absent `turn` as the host holding neither a chat nor an Ai-chan conversation.

- `attached`: Integer: the frontends attached.
- `clients`: `[{client, name, kind}]`, one per frontend attached.
- `slot`: The host's slot.
- `state`: `running`, `stopping` or `idle`.
- `run`: The epic number of the epic going, else stopping, else the last; `0` for none. A chat
  on a host is numbered as an epic is.
- `epic_kind`: What that is: `flow` for an epic, `chat` for a chat (Section 8 of [CORE]), or `""`
  for none; `hosts.running` answers it as `kind`.
- `flow`: That epic's flow as named, or `""`, as it is for a chat.
- `epic`: That epic's directory name, `""` before it has one and for a chat.
- `chat`: That chat's name (Section 8.2.12 of [CORE]), `""` before it has one and for an epic.
- `task`: That epic's task or that chat's first message, or `""`.
- `pending`: `[{question, role, text, mode}]`: every question waiting on a person.
- `ended`: How the last epic or chat to end on this host ended, `{how, why, epic, chat, at, run,
  flow, task}`, `at` in Unix seconds; `null` before one has ended.
- `turn`: Of a chat or an Ai-chan conversation only: `running` while its agent answers, `done`
  between turns and once it is over.
- `budget`, `usage`: The epic going's budget and spending as JSON, an infinite limit as the text
  `"Infinity"`; `null` while stopping or idle.
- `flows`: The canonical refs of the flow calls in progress.
- `calls`: `[{ref, name, depth, seconds, id, parent}]`, oldest first; `seconds` rounded to 0.001;
  `parent` the index of the calling entry, or `null`.

**4.6.4.2** The host-process keys are `pid`, `workspace`, `started`, `kind` and `protocol`.

**4.6.4.3** Where a host does not answer for its status, the daemon MUST answer with the
host-process keys of its `hosts.list` entry, `attached` `0`, `flows` `[]` and `calls` `[]`.

### 4.7. Attaching to a host

#### 4.7.1. `epic.attach`

**4.7.1.1** `epic.attach` MUST take `workspace`, `slot`, `replay` (default `true`), `since`
(`{epoch, seq}` or `null`), `figures` (default `false`) and `scratch` (default `false`), MUST attach
the session to that host as one frontend, and MUST be answered with `sub`, `client` (the frontend's
client id), `workspace` and `slot`.

**4.7.1.2** `epic.attach` MUST start the workspace's own host where none is; with `slot` `chat:` or
`exec:` alone it MUST make a new slot of that kind, start its host and attach to it.

**4.7.1.3** `epic.attach` with `scratch` `true` MUST, in place of `workspace`, make a new directory
for the epic alone in the system's temporary directory, and attach to its own host.

**4.7.1.4** `epic.attach` naming a chat or exec slot whose host has gone MUST be refused 409, `This
chat has folded away.` for a chat and `This epic has ended.` for an exec slot; one naming an `ai:`
slot MUST be as Section 4.22.5.2 states.

**4.7.1.5** A host MUST name a frontend by the `name` of `session.hello` where it is not `""`, else
`<user>@<kind>`, `<user>` being `HUMANIZE_NAME` where set on the client's side, else the login name,
else `somebody`; a name already attached MUST become `<name>#2`, `<name>#3` and on. The frontend's
kind MUST be the `kind` of `session.hello`.

**4.7.1.6** `epic.attach` MUST be refused 409 with `the frontend went while it was saying hello`
where the session closed meanwhile, and `this host has closed` once the host is closed.

**4.7.1.7** One session MAY hold several epic subscriptions, of one host or of several.

#### 4.7.2. Replies

**4.7.2.1** Every call to an epic MUST be answered with exactly one reply, as a result where the
host carries it out and as the error 409 with its `why` where it refuses it, but where its paragraph
states another code.

**4.7.2.2** A call to an epic that fails for any other reason MUST be refused with the text of the
failure, or the name of its type where the text is empty.

**4.7.2.3** A host MUST give every frontend the same answer and the same refusal, in the same words,
to the same call in the same state.

**4.7.2.4** A call naming a subscription that has ended MUST be refused 410.

#### 4.7.3. Order

**4.7.3.1** A host MUST carry out the calls of one frontend in the order sent, except `epic.aside`
and the calls to an environment (Section 4.24), which MUST be carried out apart from that order so
that no other call waits on them.

**4.7.3.2** A host MUST NOT let a call of one frontend delay the calls or messages of another.

#### 4.7.4. Leaving

**4.7.4.1** A frontend leaves by `epic.detach` `{sub}`, or by its session closing; the host MUST
then send it `gone` `let go` where its session is open, MUST release every role it claimed, and MUST
close every aside it opened.

**4.7.4.2** A frontend leaving MUST NOT stop any epic.

### 4.8. Calls to an epic

#### 4.8.1. General

**4.8.1.1** Each call to an epic MUST take `sub` and exactly the fields its subsection lists, with
the stated types and defaults; a field not sent MUST take its default.

**4.8.1.2** `epic.start`, `epic.say`, `epic.answer`, `epic.stop`, `epic.force`, `epic.afk`,
`epic.claim`, `epic.release`, `epic.board` and `epic.quit` MUST be writes. `epic.face` MUST be a
read.

#### 4.8.2. `epic.start`

**4.8.2.1** `epic.start` MUST take `flow` (text, required: a flow name of [CLI]), `task` (text,
`""`), `agents` (object of role to agent spec, `{}`), `envs` (object of role to environment spec,
`{}`), `params` (object, `null` for the flow's defaults), `budget` (a `Budget` as JSON, `null`),
`profile_flow` (boolean, `false`), `profile_environment` (boolean, `false`), `resume` (`false`,
`true`, or the text of an epic directory, `false`), `backup` (list of target names, `null` for the
defaults) and `remember` (boolean, `false`).

**4.8.2.2** `epic.start` MUST check the epic as `flows.check` does (Section 4.17.8), then start it
in the host's workspace, and MUST be answered with `run`, its epic number, `slot` and `workspace`;
`params` text values MUST be read as `-p` reads them ([CLI]).

**4.8.2.3** `epic.start` with `remember` `true` MUST first check what the flow is started with as
`flows.setup` checks it (Section 4.17.4), before the host is asked, and MUST write it as the
workspace's set-up of that flow, as `flows.setup` does, only once the host has taken the start; a
refused start MUST leave the set-up as it was.

**4.8.2.4** `epic.start` MUST be refused with `a flow to start is named` for a missing `flow`;
`backup is a list of backup target names` for a `backup` that is not one; `this host has closed`; `a
flow is already running` while an epic is going; `a flow is already starting` while another start is
under way; `a chat is started with chat.start` on a chat host (Section 4.25.1); `an exec host runs
one epic` on an exec host that has started one; `an Ai-chan host runs its own conversation` on an
Ai-chan host; and with the `Refused` message of Section 4.6 of [PYTHON] for everything
`flows.check` refuses.

**4.8.2.5** An epic that is stopping MUST NOT prevent `epic.start`.

#### 4.8.3. `epic.say`

**4.8.3.1** `epic.say` MUST take `text` (text, required, not empty) and `to` (text, `""`), and MUST
route the line as Section 4.10.1 states.

**4.8.3.2** `epic.say` MUST be refused with `a line says something` for an empty `text`; `no flow is
running to say it to` while no epic is going, a stopping epic included; and `<role> is <name>'s`
where `to` is `outworlder:<role>` and another frontend claims `role`.

#### 4.8.4. `epic.answer`

**4.8.4.1** `epic.answer` MUST take `question` (text, a question id) and exactly one of `text`
(text, not empty) and `value` (any JSON value); a `value` of `null` MUST be read as not sent.

**4.8.4.2** Where the question has options and `text`, stripped, is a decimal number `n` from 1 to
the number of its options and is not itself an option, the answer MUST be the `n`-th option;
otherwise it MUST be `text`.

**4.8.4.3** Where the question has a `schema`, the answer MUST be `value`, or `text` read as JSON,
and MUST be taken only where it fits the schema, as the flow validates it (Section 3.10.4.3 of
[PYTHON]); `answered.text` MUST then be the value taken, as JSON text, with the value of every
field its schema marks `"hmz:widget": "secret"` written `***`.

**4.8.4.4** Where the question has no `schema`, a `value` that is text MUST be read as `text`, and
any other `value` MUST NOT fit.

**4.8.4.5** An answer that does not fit -- a value the schema refuses, `text` that is not JSON, or a
`value` that is not text where text is asked -- MUST be refused 400 with `the answer does not fit:
<message>`, `<message>` being the `message` of its first error, and with `data` `{"errors":
[{"path": [...], "message": ...}]}`: one entry per error, `path` the keys and indexes from the
value's root to what is wrong, `[]` for the whole value. The question MUST stay waiting.

**4.8.4.6** `epic.answer` MUST be refused with the first of these that holds: `an answer says
something` where neither `text` nor `value` is sent, or `text` is empty; `an answer is text or a
value, not both`; `already answered by <name>` for a question answered; `no question <id> is
waiting`; `<role> is <name>'s` where another frontend claims the question's role; and an answer
that does not fit (Section 4.8.4.5).

#### 4.8.5. `epic.stop` and `epic.force`

**4.8.5.1** `epic.stop` MUST take no field, MUST interrupt the turn under way and let the flow
unwind, and MUST be refused with `the flow is already stopping: it is closing out the turn it was
in` while one is stopping and `no flow is running, so there is nothing to stop` while none is going.

**4.8.5.2** `epic.force` MUST take no field, MUST stop the epic going where there is one, MUST close
every session of the stopping epic that has a turn open, and MUST be answered with `closed`, the
number of sessions closed; it MUST be refused with `no flow is running, so there is nothing to stop`
where no epic is going or stopping.

#### 4.8.6. `epic.afk`, `epic.claim` and `epic.release`

**4.8.6.1** `epic.afk` MUST take `on` (boolean, required) and `role` (text, `""` for every role),
MUST set away as Section 4.10.3 states, and MUST be refused with `afk is on or off` for an `on` that
is not a boolean and `<role> is <name>'s` for a role another frontend claims.

**4.8.6.2** `epic.claim` MUST take `role` (text, required) and `take` (boolean, `false`), MUST claim
the role for this frontend as Section 4.10.2 states, and MUST be refused with `a role to claim is
named` and, without `take`, `<role> is <name>'s` for a role another frontend claims.

**4.8.6.3** `epic.release` MUST take `role` (text) and MUST be refused with `<role> is not yours to
release` for a role this frontend does not claim.

**4.8.6.4** `epic.afk`, `epic.claim` and `epic.release` MUST NOT require an epic to be going, and
`epic.claim` MUST NOT check the role against the flow.

#### 4.8.7. `epic.board`

**4.8.7.1** `epic.board` MUST take `key` (text) and `value` (text, `""`), and MUST write the line
`key` of the last epic's board as the user, or remove it where `value` is `""`.

**4.8.7.2** `epic.board` MUST be refused with `this run has no board`, `<key> is not on the board`,
and the board's own refusal where the line is not the user's to change.

#### 4.8.8. `epic.aside` and `epic.unaside`

**4.8.8.1** `epic.aside` without `side` MUST open a side conversation and be answered with `side`
(`s<n>`) and `forked` (boolean: whether it carries the history of a session).

**4.8.8.2** `epic.aside` with `key` (`<agent>/<n>`, a session of the last epic) and `fork` (boolean)
MUST open the side conversation on that session: a fork of it where `fork` is `true` and its harness
forks, otherwise a new session of a copy of its agent.

**4.8.8.3** `epic.aside` with `runs` (the agent spec of a session an earlier epic kept) MUST open a
new session of that agent in the workspace, as the session side copy of Section 9.5.5 of [CORE];
with `runs` and `recall` (the harness's id of that session), `kept` (where that epic kept it) and
`cwd`, it MUST open a fork of that session where `fork` is `true` and its harness forks it,
otherwise a new session of that agent.

**4.8.8.4** `epic.aside` with a `key` that names no session MUST be refused with `<key> has no
conversation to ask`.

**4.8.8.5** `epic.aside` with a `runs` that names no agent this host makes MUST be refused with
`<runs> is not an agent that can be made here`.

**4.8.8.6** `epic.aside` that names neither `key` nor `runs` MUST be refused with `an aside is about
a conversation, or asks an agent`.

**4.8.8.7** `epic.aside` from a frontend that has gone MUST be refused with `this frontend has
gone`.

**4.8.8.8** `epic.aside` with `side` and `prompt` MUST take one turn of that side conversation and
be answered with `answer`, its text stripped.

**4.8.8.9** `epic.aside` with a `side` this frontend has not open MUST be refused with `no aside
<side> is open`.

**4.8.8.10** `epic.aside` with a `side` that is taking a turn MUST be refused with `the aside is
still answering the last question`.

**4.8.8.11** `epic.unaside` MUST take `side`, MUST close that side conversation, and MUST be refused
with `no aside <side> is open`.

**4.8.8.12** Every side conversation MUST run inside a confinement of its own that writes nothing
(Section 9.3.4 of [CORE]), MUST carry no skills (Section 9.3.5 of [CORE]), MUST NOT be seen by the
epic, MUST be answered only to the frontend that opened it, and MUST NOT write where any epic keeps
its sessions nor into the harness's own home.

**4.8.8.13** A side conversation MUST be closed by `epic.unaside`, when its frontend leaves, when an
epic starts on the host, and when the host closes; no message announces side conversations.

#### 4.8.9. `epic.status`, `epic.detach` and `epic.quit`

**4.8.9.1** `epic.status` MUST be answered with every key of Section 4.6.4.1.

**4.8.9.2** `epic.detach` MUST let this frontend go as Section 4.7.4 states, and MUST be answered
`{}`.

**4.8.9.3** `epic.quit` MUST close the host as Section 4.13.6 states.

#### 4.8.10. `epic.face`

**4.8.10.1** `epic.face` MUST take `hash` (text, required) and MUST be answered with `html` and
`title`, the face (Section 3.10.7 of [PYTHON]) of the epic going or the last one whose hash is
`hash`.

**4.8.10.2** A host MUST keep every face the flow made known to it for as long as it keeps the
history records of that epic (Section 4.9.2.2).

**4.8.10.3** `epic.face` MUST be refused 404 with `no face <hash>` where the host keeps no face of
that hash.

### 4.9. Messages

#### 4.9.1. Attaching

**4.9.1.1** On `epic.attach`, a host MUST send the new frontend, before any other message and with
no other message between them: `welcome`; every history record kept, oldest first, unless `replay`
is `false`, or those Section 6.8.4 of [WIRE] states where `since` is given; every snapshot, in the
order `clients`, `claims`, `away`, `run`, `sessions`, `calls`, `waiting`, `pending`, `usage`,
`board`, `envs`; and `live`.

**4.9.1.2** After `live`, a host MUST send each history record and each changed snapshot as it
happens.

**4.9.1.3** `welcome` MUST carry `client`, `name`, `kind`, `workspace`, `slot`, `pid` (the host's
process), `protocol` and `epoch`, a text naming this life of the host, made afresh each time a host
starts.

**4.9.1.4** `live` MUST carry `seq`, the `seq` of the last history record, and `elided`, the number
of history records dropped from the front.

**4.9.1.5** An epic subscription opened with `figures` `true` MUST also be sent the message
`figures`, after `live` and then at most once a second while it changes, holding `run`, `elapsed`,
`lasting`, `ended`, `agents` and `sessions` (each `name`, `turns`, `working`, `since`, `lasting`,
`used`, `tokens`, `under`), `handovers` (`[{from, to, count}]`), `latest`, `spending` (each `model`,
`tokens`, `rate`, `dollars`, `money`, `kinds`), `reckoning` (each `kind`, `tokens`, `whole`) and
`tally`: what the epic has done and spent, worked out of its history records.

#### 4.9.2. History records

**4.9.2.1** Every history record MUST carry `seq`, an integer that increases by one with each record
across the host's life.

**4.9.2.2** A host MUST keep the history records of the epic going or the last, starting afresh with
each `epic.start` and `chat.start`, up to 32 MiB of JSON, dropping the oldest whole records first
and counting them in `elided`.

**4.9.2.3** Every history record other than `printed` MUST carry `run`, its epic number.

**4.9.2.4** The history records MUST be those of the following list, with those fields.

- `started`: `kind` (`flow` or `chat`; of a chat, `flow` and `ref` are `""` and `params` and
  `budget` `null`), `flow`, `ref`, `task`, `by`, `client`, `roles` (agent roles not filled by the
  runtime), `names` (`{role: agent name}`), `outworlders`, `agents`, `envs` (`{role: spec}`),
  `params`, `budget`, `profile_flow`, `profile_environment`, `backup`, `resume` (`""`, or the text
  given; of a chat, the name of the chat carried on, or `null`), `began` (host monotonic seconds),
  `at` (Unix seconds).
- `opened`: `role`, `key` (`<agent>/<n>`), `agent`, `cli`, `model`, `counts` (token kinds the
  backend reports, sorted), `forks`, `person`, `kept` (directory of the session's logs, `""` for a
  person or the harness's own home), `env`, `harness`, `mono`, `wall`.
- `event`: `key`, `session`, `agent`, `cli`, `model`, `ident`, `kind`, `text`, `whose`, `tokens`,
  `spent`, `at`, `mono`: the record `hmz exec --json` writes ([CLI]).
- `asked`: `question` (`q<n>`), `role`, `text`, `options` (`[]` for a question with a schema),
  `mode` (`ask` or `listen`), `key`, `schema` (the JSON Schema of the answer, or `null` for text),
  `context` (the blocks put beneath the question, each in the JSON form of Section 3.10.5.2 of
  [PYTHON], `[]` for none), `face` (`{hash, title}`, or `null` for none) and `session` (the
  outworlder session asking, `<role>/<n>`, `""` for none).
- `answered`: `question`, `role`, `by`, `client`, `text`.
- `withdrawn`: `question`, `why` (`away` or `over`).
- `shown`: `role`, `session`, `context`: blocks an outworlder session was shown with no question
  (Section 3.10.6 of [PYTHON]), as `asked` carries them.
- `said`: `text`, `key`, `by`, `client`.
- `refused`: `agent`, `text`, `because`.
- `unheld`: `agent`, `texts`.
- `dropped`: `given` (`[{agent, text, by, client}]`), `queued` (`[{text, by, client, to}]`),
  `because` (`stopped` or `ended`).
- `shell`: `key`, `command`, `out`, `err`, `status`: a `!` command a chat ran for its user
  (Section 8.9.6 of [CORE]).
- `printed`: `text`: one line printed in the host process.
- `notice`: `text`: a notice of **hmz** about the epic, as Section 3 of [CORE] defines notices.
- `stopping`: `by`, `client`.
- `ended`: `how` (`done`, `stopped`, `budget`, `refused`, `failed` or `crashed`), `why`, `mono`,
  `result`.
- `env_used`: `env` (an `id` of `envs`), `by` (the name of the frontend), `what` (`wrote`, `made`,
  `renamed`, `removed`, `opened a terminal`, `staged`, `unstaged`, `discarded`, `committed` or
  `rewound`) and, where the call named one, `path`: one change a frontend made to an environment
  (Section 4.24.1.8).

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

**4.9.2.9** `ended.result` MUST be what the flow returned, as JSON, every value that is not
JSON-native as its text, for `done`, and `null` otherwise.

#### 4.9.3. Snapshots

**4.9.3.1** A host MUST keep the latest of each snapshot, MUST send every snapshot on attach, and
MUST send a snapshot to every frontend whenever it changes.

**4.9.3.2** The snapshots MUST be those of the following list, with those fields and initial values.

- `clients`: `clients`: `[{client, name, kind}]`; initially `[]`.
- `claims`: `claims`: `{role: client}`; initially `{}`.
- `away`: `all` (boolean), `of` (`{role: boolean}`); initially `false`, `{}`.
- `run`: `state`, the `started` fields of the epic going or the last (`run` `0` for none),
  `stopping` (epic number or `null`), `epic` and `chat` (as the status says them, Section 4.6.4.1),
  `slot`, and of a chat `turn`;
  initially `idle`.
- `sessions`: `run`, `open` (keys still open), `working` (keys with a turn open); initially `0`,
  `[]`, `[]`.
- `calls`: `calls`: `[{ref, name, depth, since, id, parent}]`; initially `[]`.
- `waiting`: `queued` (`[{text, by, client, to}]`), `given` (`[{agent, text, by, client}]`);
  initially `[]`, `[]`.
- `pending`: `pending`: `[{question, run, role, text, options, mode, key, schema, context, face,
  session, owner}]`, each as its `asked` record says it; initially `[]`.
- `usage`: `run`, `usage`, `budget`; sent at most once a second; initially `0`, `null`, `null`.
- `board`: `items`: `[{key, value, about, whose, by, at}]`, or `null` for an epic with no board;
  initially `null`.
- `envs`: `envs`: the environments of Section 4.24.2; initially `[]`.

#### 4.9.4. `gone`

**4.9.4.1** `gone` MUST be the last message a host sends a frontend, carrying `why`, and its epic
subscription MUST end with it.

**4.9.4.2** `why` MUST be `let go` where the frontend left; `the host was closed` where the host
closed; `too far behind; attach again` where the frontend fell behind (Section 4.11.1); and `the
host went away` where the host process ended without closing.

**4.9.4.3** A client MUST read the end of its session, without a preceding `gone`, as the end of
every epic subscription of it, and MUST attach again as Section 3.6.11 states.

#### 4.9.5. Messages to one frontend

**4.9.5.1** `term` and `term_exit` (Section 4.24.4) MUST be sent only to the frontends that section
names, MUST NOT carry `seq`, MUST NOT be kept, and MUST NOT be sent on attach.

### 4.10. Semantics a frontend observes

#### 4.10.1. Lines

**4.10.1.1** A line said with `to` `""` MUST answer a waiting `listen` question this frontend is
permitted to answer, else go into the first session with a turn open, in the order the epic opened
them.

**4.10.1.2** A line said with `to` an agent's name MUST go into that agent's newest session with a
turn open; a line said with `to` `<agent>/<n>` MUST go into that session.

**4.10.1.3** On a chat host, `epic.say` and `epic.answer` MUST be refused with `say it to the chat
with chat.say`; every line of a chat, an answer to what its assistant asks included, is said by
`chat.say` (Section 4.25.2).

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

**4.10.2.5** A question MUST be `ask` where it has options or a schema or a turn is open, else
`listen`; a question asked while exactly one session has a turn open MUST carry that session's key.

**4.10.2.6** A question MUST be withdrawn with `away` when its role goes away, and with `over` when
its epic stops or ends, is forced, or the host closes.

**4.10.2.7** `shown` MUST be recorded only where a question of its role would be (Section
4.10.2.3), MUST NOT wait on any frontend, and MUST make no notice.

#### 4.10.3. Away

**4.10.3.1** Away MUST be held per role by the host and MUST outlive the frontend that set it.

**4.10.3.2** `epic.afk` with a role MUST set that role; `epic.afk` without a role MUST, where no
role is claimed, set every role and clear every per-role value, and, where roles are claimed, leave
the value of every role another frontend claims unchanged.

### 4.11. Limits

**4.11.1** A host MUST NOT wait on a slow frontend: a session that falls behind MUST be let go as
Section 6.10.1 of [WIRE] states.

**4.11.2** Every text longer than 262 144 characters in a history record or a snapshot MUST be cut
to that length followed by `… (<n> more characters)`, `n` the characters cut, but the texts of
`schema` and `context`, which MUST be sent whole (Section 3.10.5.3 of [PYTHON]).

### 4.12. Protocol versions

**4.12.1** The protocol version of the daemon MUST be that of Section 6.5.1 of [WIRE].

**4.12.2** The daemon MUST write its protocol version in the daemon record (Section 7.6.2 of
[FILES]), and a host MUST send it in `welcome`.

**4.12.3** A client finding a daemon record of another major version, or of none, MUST NOT reach it,
MUST NOT start a daemon beside it, and MUST report the refusal of Section 3.7.5.

### 4.13. Lifecycle

#### 4.13.1. The daemon

**4.13.1.1** There MUST be at most one daemon per machine and user, and it MUST hold the hosts of
every workspace.

**4.13.1.2** The daemon MUST have no controlling terminal and MUST ignore `SIGHUP`.

**4.13.1.3** The daemon MUST refuse a second host of one slot of one workspace while the first is
alive.

**4.13.1.4** The daemon MUST exit once it has held no host and no session for 2 seconds, or 60
seconds after it started where no host was ever taken on and no session is open, except as Section
3.9.4 states, and on `SIGTERM`.

#### 4.13.2. Hosts

**4.13.2.1** Each host MUST run in a process of its own whose current directory is its workspace.

**4.13.2.2** The hosts of a workspace MUST run its epics as Section 3.3 states.

**4.13.2.3** A host MUST send every line its process prints on its standard output or standard error
to every frontend as a `printed` record, one line per record.

**4.13.2.4** A host MUST ignore `SIGINT`.

#### 4.13.3. Idle hosts

**4.13.3.1** A host MUST close once it is idle and either a frontend has ever attached to it or 60
seconds have passed since it started.

**4.13.3.2** A host MUST read as idle where no frontend is attached, no epic is going, starting or
stopping, and no epic awaits a frontend.

**4.13.3.3** An epic that ended while no frontend was attached, and that no frontend stopped, MUST
await a frontend until one attaches, except a chat that folded and the epic of an exec host.

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

**4.13.6.3** A frontend attaching to a closed host MUST be refused as Section 4.7.1.6 states.

#### 4.13.7. Failures

**4.13.7.1** Whatever a frontend sends, other than `epic.stop`, `epic.force`, `epic.quit`,
`hosts.stop` and an empty `chat.say`, MUST NOT end an epic or a chat; `epic.stop` on a host that
holds a chat MUST NOT end the chat, and MUST do what `chat.stop` does (Section 4.25.6).

**4.13.7.2** A failure that belongs to an epic MUST be written to that epic's `host.log` (Section 6
of [FILES]), and one that belongs to none to `daemon.log` in the daemon directory (Section 7 of
[FILES]).

#### 4.13.8. Folding a chat

**4.13.8.1** A chat's host MUST fold its chat once the chat has waited between turns with no
frontend attached for 60 seconds; folding MUST end the chat as an empty next message does (Section
8.4.7 of [CORE]), keeping its conversation to be carried on.

**4.13.8.2** A folded chat host MUST refuse `chat.say` (Section 4.25.2); a folded chat is carried on
by `chat.start` on a new slot with `resume` its name, which continues that same chat.

**4.13.8.3** An Ai-chan host MUST fold its conversation as Section 4.13.8.1 states for a chat; a
folded conversation is carried on as Section 4.22.5.2 states.

### 4.14. Sessions, pairing and devices

#### 4.14.1. `session.*` and `rpc.discover`

**4.14.1.1** `session.hello` and `session.cancel` MUST be as Section 6.5 of [WIRE] and Section 6.4.7
of [WIRE] state.

**4.14.1.2** `rpc.discover` MUST answer as Section 6.11.4 of [WIRE] states.

#### 4.14.2. `pair.*`

**4.14.2.1** `pair.create` MUST take `routes` (a list of routes, default the routes of the
listeners) and `seconds` (60 to 86 400, default 600), MUST make a pairing code as Section 4.5 of
[WIRE] states, and MUST be answered with `code` and `expires`; `seconds` out of bounds MUST be
refused 400, `A code lives 60 to 86400 seconds.`, and no route at all 409, `There is no route to
pair over: give one, or listen.`

**4.14.2.2** `pair.claim` MUST take `token` and `name` (the device's name, of the grammar of Section
3.8.1.4), MUST pair the session's device as Section 4.5.8 of [WIRE] states, and MUST be answered
with `daemon_id` and `device`, the name the device was paired under; a `name` not of that grammar
MUST be refused 400, `A device's name begins with a letter or a digit, holds letters, digits, '.',
'_' and '-', and is not local.`

**4.14.2.3** `pair.claim` on a paired session MUST add and rename no device: where the token is one
the daemon holds and has not expired, the daemon MUST forget it and MUST answer `daemon_id` and, as
`device`, the name the session is paired under; any other token MUST be refused as Section 4.5.9 of
[WIRE] states.

**4.14.2.4** `pair.create` MUST be a write, and `pair.claim` MUST NOT be one.

#### 4.14.3. `devices.*`

**4.14.3.1** `devices.list` MUST answer `devices`, each `name`, `fingerprint`, `added`, `seen` and
`live` (how many sessions of it are open), in the order paired.

**4.14.3.2** `devices.revoke` MUST take `name`, MUST revoke that device as Section 4.6.3 of [WIRE]
states, and MUST be answered with `dropped`, the number of sessions closed; `local` MUST be refused
400, `local cannot be revoked.` (Section 4.6.4 of [WIRE]), and an unknown name 404, `There is no
device <name>.`

**4.14.3.3** `devices.revoke` MUST be a write.

### 4.15. Side questions

#### 4.15.1. General

**4.15.1.1** A side question of `btw.*` MUST be asked as Section 9 of [CORE] defines it, through
side conversations opened (Section 4.8.8) by the host whose slot holds the session asked: the
workspace's own host for its epic, the `chat:<hex>` host for a chat; and MUST NOT reach the epic
or the chat.

**4.15.1.2** The daemon MUST open those side conversations as a frontend of its own, of kind `btw`,
attached to that host only while a `btw.*` call asks something of it or it holds an open side
conversation there, and MUST let go of it once neither has happened for 60 seconds.

**4.15.1.3** Every side conversation of `btw.*` MUST be a session side copy (Section 9.5 of [CORE]),
and `btw.*` MUST NOT open a side conversation of any other agent.

**4.15.1.4** The side conversations of `btw.*` MUST be kept by the daemon per workspace and per
`aside` name, the same for every session.

#### 4.15.2. `btw.list`

**4.15.2.1** `btw.list` MUST take `workspace` and `epic` (an epic name, `""` for the epic in view on
the workspace's own host), or, in place of `epic`, `chat` (a chat's name) for the side
conversations open about that chat.

**4.15.2.2** `btw.list` MUST answer `asides`, each side conversation open about `epic`, in the order
opened.

**4.15.2.3** Each of `asides` MUST say `aside` (its name, Section 4.15.3.1), `to` (the session it
asks, as Section 4.15.3.1), `question` (the question it is answering, `""` for none) and `said`
(each side question answered in it, oldest first, as Section 4.15.3 answers it, the latest 200).

**4.15.2.4** `btw.list` MUST NOT attach to any host; where the daemon holds no side conversation of
the workspace, `asides` MUST be `[]`.

#### 4.15.3. `btw.ask`

**4.15.3.1** `btw.ask` MUST take `workspace`, `question` (text, required), `aside` (text, required:
the side conversation, named by the client), `to` (text, required: `<agent>/<n>`, the session
asked) and `epic` (the epic it is about, `""` for the epic in view on the workspace's own host),
or, in place of `epic`, `chat` (the name of the chat it is about).

**4.15.3.2** The first question to an `aside` MUST open a side conversation on `to`, about `epic`,
and every later question to it MUST go on in that side conversation, of that `to` and `epic`
whatever the question sends, until it is left.

**4.15.3.3** Where `epic` names an epic the host no longer holds, or `epic` and `to` a session it no
longer holds, the daemon MUST tell the side conversation that epic rather than the epic going, and
MUST carry each of its sessions asked on from where that epic kept it; a session that epic did not
open, or whose agent it did not write, MUST be refused 404.

**4.15.3.4** `btw.ask` MUST answer `aside`, `to`, `question` and `answer`.

**4.15.3.5** A `to` that is not of the form `<agent>/<n>` MUST be refused 400, `A side question is
asked of a session, as <agent>/<n>.`

**4.15.3.6** A question to a side conversation still answering MUST be refused 409, `btw is still
answering the last question asked of it.`; a question closed by a new epic starting 409, `A new epic
started, which closed what was asked.`; an empty answer 502, `The agent returned no answer.`

#### 4.15.4. `btw.leave`

**4.15.4.1** `btw.leave` MUST take `workspace` and `aside` (a side conversation, or absent for every
one), MUST close the side conversations named, and MUST answer `{}`.

**4.15.4.2** A side conversation about the epic going on a host MUST be closed when another epic
starts on that host, and one about an epic the host no longer holds MUST NOT be closed by that.

### 4.16. Epics written down

#### 4.16.1. `runs.list`

**4.16.1.1** `runs.list` MUST take `workspace` (only that workspace's epics, reading the epics of a
workspace since removed; every workspace's where absent), `status` (an ending of Section 3 of
[CORE], `running` or `unfinished`), `flow`, `q` (text found in the task, flow or epic name),
`offset` (default `0`) and `limit` (default `50`, at most `200`).

**4.16.1.2** `runs.list` MUST answer `runs` (epic rows, newest first), `total`, `offset`, `limit`,
`counts` (`{ending: n}` over every epic) and `flows` (every flow, sorted).

**4.16.1.3** `runs.list` MUST leave out, whatever session calls it, the epic recorded for an
Ai-chan conversation, kept or forgotten (Section 14.7.4 of [CORE], Section 4.16.6 of
[FILES]), and the epic the host of an `ai:` slot holds.

**4.16.1.4** No method of Section 4.16 but `runs.usage` and `backups.*` MUST answer anything of a
chat (Section 8 of [CORE]): a chat is no epic, and is read by `chat.*` (Section 4.25). An epic an
earlier hmz recorded for a chat (Section 6.5.19 of [FILES]) is a chat once the daemon has moved it
(Section 4.16.1.5); one not yet moved MUST be answered by no method of Section 4.16 and none of
Section 4.25: every list MUST leave it out, and a method that names it MUST be refused 404 as
naming none.

**4.16.1.5** The daemon MUST, each time it starts and before it accepts a session, move the epics
an earlier hmz recorded for chats among the chats, as Section 8.7.10 of [CORE] and Section 6.12.14
of [FILES] state, and MUST log how many it moved and each one it left, with why. A failure to move
them MUST NOT keep the daemon from starting. `runs.import` and `backups.pull` of such an epic MUST
place it among the chats, and answer its name; `backups.epics` MUST answer it with `chat` true and
`flow` `""`.

#### 4.16.2. Epic rows

**4.16.2.1** An epic row MUST hold `name`, `workspace`, `kind` (`flow`), `flow`, `task` (its first line,
cut at 240 characters with `…`), `began`, `ended`, `how` (its ending, `running` while going,
`unfinished` where its process went before it ended), `agents` (`[{name, role, runs}]`), `sessions`
(a count), `resumable`, `spent`, `held` (whether a host is going with it), `slot` (that host's),
`asking` (the questions that host waits on, each `<run>:<question>`, `[]`
where none waits or no host is going with it), `backup` (the targets it was started with) and
`backed` (`{target: {at, ok, error, why}}`).

#### 4.16.3. `runs.get`

**4.16.3.1** `runs.get` `{name}` MUST answer the epic row of the epic, of whichever workspace, with
`at`, the whole `task`, `ref`, `agents` (each `name`, `role`, `runs`, `backend`, `model`, `effort`,
`provider`), `sessions` (each `agent`, `backend`, `provider`, `ident`, `name`, `at`, `flow`,
`parent`, `harness`), `envs`, `used`, `params`, `budget`, `picked_up`, `profile_flow`,
`profile_environment`, `picks_up`, `foreign` and `calls` (its tree of flow calls, each `flow`,
`task`, `began`, `ended`, `how`, `calls`).
`backed` MUST be among what it answers, as the epic row defines it (Section 4.16.2.1), and a
backup of the epic to a target MUST count as finished once `backed` holds that target with an `at`
no earlier than the epic's `ended`.

**4.16.3.2** A `name` that names no epic MUST be refused 404, `There is no epic <name>.`, by every
method of Section 4.16 that takes `name`.

#### 4.16.4. Traces, timelines and bundles

**4.16.4.1** `runs.trace` `{name}` MUST answer `sessions`, as `Epics.transcripts` of Section 4.12.15
of [PYTHON] returns them.

**4.16.4.2** `runs.timeline` `{name}` MUST answer the epic's Exomyth timeline as Section 10 of
[CORE] defines it, laid out afresh on every call while the epic is going.

**4.16.4.3** `runs.span` `{name, id, layout}` MUST answer one span of the last timeline laid out of
the epic, whole; an id it lacks MUST be refused 404, `Epic <name> has no span <id>.`, and a `layout`
other than that timeline's 409, `Epic <name> has been laid out again; read it again.`

**4.16.4.4** `runs.bundle` `{name}` MUST write the epic's `.hmzepic` (Section 4.12.17 of [PYTHON])
and answer `handle` (a read handle of it, Section 6.9 of [WIRE]), `filename` (`<name>.hmzepic`),
`size` and `type` (`application/vnd.hmz.epic+gzip`).

#### 4.16.5. `runs.backup`

**4.16.5.1** `runs.backup` `{name, to}` MUST take `to` (a list of target names, or absent) and MUST
back the epic up as `Backups.push` of Section 4.13.2 of [PYTHON] does, answering `queued` at once
without waiting for the push, and MUST be a write.

**4.16.5.2** A `to` that names no target MUST be refused 400; where there is no target at all the
call MUST be refused 409, `There is no backup target: add one in Settings.`

#### 4.16.6. `runs.import`

**4.16.6.1** `runs.import` MUST take either `handle`, a write handle of `files.create` (Section 6.9
of [WIRE]) holding the archive's bytes, or `path`, the absolute path of a `.hmzepic` on the daemon's
machine, and MUST be a write.

**4.16.6.2** `runs.import` MUST import the archive as `Epics.imported` of Section 4.12.18 of
[PYTHON] does and answer `name`, `workspace`, `resumable` and `why`.

**4.16.6.3** A handle given MUST be taken (Section 6.9.4 of [WIRE]) once the call is answered.

**4.16.6.4** A handle whose file name, as `files.create` gave it, holds `/`, `\` or a NUL, or is
longer than 255 bytes, MUST be refused 400, `That is not a file name.`; a `path` that is not
absolute 400, `Say path as a whole path on this machine.`; a handle whose bytes are fewer than the
size declared 409, `The file is not whole yet.`; an archive that cannot be imported 400 with the
sentence of the error `Epics.imported` raises (Section 4.12.19 of [PYTHON]); and an epic already
present 409 with that error's sentence and, in `data`, `name`, that epic's name.

**4.16.6.5** Where the daemon runs in WSL, a `path` that is a Windows path (`C:\…`, `\\wsl$\…`,
`\\wsl.localhost\…`) MUST be read as `wslpath -u` translates it, before the check of Section
4.16.6.4 that `path` is absolute.

#### 4.16.7. `files.*`

**4.16.7.1** `files.create`, `files.write`, `files.read` and `files.close` MUST be as Section 6.9 of
[WIRE] states.

#### 4.16.8. `backups.*`

**4.16.8.1** `backups.epics` `{target}` MUST fetch the target afresh and answer `epics`, newest
first, each `key` (`<machine>/<workspace>/<epic>`), `machine`, `workspace`, `epic`, `flow`, `task`,
`began`, `ended`, `how`, `head`, `chat` (whether it is a chat the target holds, Section 8.3.14 of
[CORE], its `epic` being the chat's name and its `flow` `""`) and `here` (whether this machine holds
that epic, or that chat).

**4.16.8.2** `backups.pull` `{target, key}` MUST download that epic as `Backups.pulled` of Section
4.13.7 of [PYTHON] does, a chat among this machine's chats, answer `name`, and be a write.

**4.16.8.3** `backups.epics` and `backups.pull` MUST each refuse 400 for an unknown target or what
`Backups` raises `ValueError` for, and 502 where the repository cannot be reached; a refusal MUST
NOT carry credentials of a URL.

#### 4.16.9. `runs.usage`

**4.16.9.1** `runs.usage` MUST take `days` (1 to 365, default 30) and `workspace` (only its epics,
reading the epics of a workspace since removed), and MUST answer `days_back`, `days` (per UTC day,
oldest first), `flows` (costliest first), `ended` (`{ending: n}`) and `whole`, each but `ended`
holding `runs`, `cost`, `output_tokens`, `seconds`, `money`, `tokens` and `worked`.

**4.16.9.2** `runs.usage` MUST count each chat (Section 8 of [CORE]) as it counts an epic, under
the flow `chat`.

### 4.17. Flows, workspaces and paths

#### 4.17.1. `flows.list`

**4.17.1.1** `flows.list` MUST take `workspace`, which MAY be absent and need not exist, and answer
`flows` (`[{whose, name, about}]`), `flow` (the flow last set up in that workspace, or `""`) and
`running` (`[{ref, name, depth, since, task}]`). Absent, it MUST leave out the flows of a project
(`local`), and `flow` MUST be the one last set up in the user's home; one naming no directory MUST
be answered as a workspace with no flows of its own.

#### 4.17.2. `flows.get`

**4.17.2.1** `flows.get` MUST take `name` and `workspace`, which MAY be absent and need not exist
as Section 4.17.1.1 states, and MUST answer what the flow declares:
`name`, `ref`, `description`, `resumable`, `resumes`, `agents` (each `name`, `required`, `auto`,
`harness`, `permission` (`{preset, network, granular: [{path, access}]}`), `skills`, and `clis`: the
CLIs installed on the daemon's machine that can fill it), `envs` (each `name`, `required`, `auto`,
`cpu`, `memory`, `gpu`, `image`), `params` (its JSON schema) and `remembered` (`agents`, `envs`, `params`, `budget`, `profile_flow`,
`profile_environment`, `backup`, as the workspace last set the flow up).

**4.17.2.2** A name that is not one of `flows.list` MUST be refused 404, `<name> is not a flow on
offer here.`, and a flow that will not load 404.

**4.17.2.3** The daemon MUST NOT load a flow named by a path or a repository for `flows.get`.

#### 4.17.3. `flows.backends`

**4.17.3.1** `flows.backends` MUST answer `clis` (`{cli: {accounts: [{name, models: [{name,
efforts}], asked}]}}` for each CLI installed, this machine's own sign-in first as `""`),
`installable` (`{cli: [{name, efforts}]}`) and `envs` (`Runtimes.kinds()` of Section 4.10.2 of
[PYTHON]).

#### 4.17.4. `flows.setup` and `flows.fork`

**4.17.4.1** `flows.setup` MUST take `workspace`, `flow`, and, as `epic.start` takes them, `agents`,
`envs`, `params`, `budget`, `profile_flow`, `profile_environment` and `backup`, MUST write what the
workspace runs the flow with, as Section 3 of [FILES] defines it, and MUST answer as `flows.get`
does.

**4.17.4.2** `flows.setup` MUST be refused 404 for a flow not on offer or that will not load; 400
for an agent that is not an agent spec, a role left without an agent, a flow with no budget limit,
and a `backup` naming an unknown target.

**4.17.4.3** `flows.fork` MUST take `flow` and `workspace`, copy the flow as `Flows.fork` of Section
4.7.7 of [PYTHON] does, and answer `said` and `at`; what that raises MUST be refused 400.

**4.17.4.4** `flows.setup` and `flows.fork` MUST be writes.

#### 4.17.5. `workspaces.*`

**4.17.5.1** `workspaces.list` MUST take `here`, and answer `here` and `workspaces`, each `path`,
`name`, `epics` and `chats` (a count of each), `last` (when the latest epic or chat began),
`running`, `here` and `there` (whether the directory exists): `here` first, then those going, then
those where epics ran or chats were had, newest first, then those only written in the settings.

**4.17.5.2** `workspaces.add` MUST take `workspace` and `here`, write the workspace in the settings,
and answer `kept` (its absolute path) beside what `workspaces.list` answers.

**4.17.5.3** `workspaces.forget` MUST take `workspace` and `here`, forget what it was set up with,
and answer as `workspaces.list` does.

**4.17.5.4** `workspaces.add` and `workspaces.forget` MUST be writes.

**4.17.5.5** `workspaces.list` MUST answer as though no Ai-chan conversation, kept or forgotten, had
an epic, and no `ai:` slot a host (Section 14.7.4 of [CORE]): neither counted in `epics`, `last` or
`running`, nor a reason to list a directory.

#### 4.17.6. `flowverses.*`

**4.17.6.1** `flowverses.list` MUST answer `verses` (each `name`, `url` without credentials,
`fetched`, `fixed`, `edited`, `installed`), `installed` (each `flow`, `verse`, `listed`, `version`,
`repo`, `ref`) and `updates` (each `flow`, `from`, `to`).

**4.17.6.2** `flowverses.get` `{name}` MUST answer `name`, `url`, `fetched`, `fixed`, `edited`,
`flows` (each `listed`, `flow` as `flowverses.install` takes it, `installed`, and `releases` newest
first, each `version`, `description`, `prerelease`, `license`, `repo`, `dependencies`) and `skipped`
(each `at`, `why`); an unknown name MUST be refused 404, `There is no flowverse <name>.`

**4.17.6.3** `flowverses.add` (`url`, `name`), `flowverses.fetch` (`name`), `flowverses.remove`
(`name`), `flowverses.install` (`flow`, `version`) and `flowverses.uninstall` (`flow`) MUST do what
`Flowverses.add`, `fetch`, `remove`, `install` and `uninstall` of Section 4.8 of [PYTHON] do, MUST
be writes, and MUST answer `said` (what was done, in words) beside what `flowverses.list` answers;
what those raise MUST be refused 400.

**4.17.6.4** Install, uninstall and remove MUST be refused 409, `An epic is running: flows change
once none is.`, while an epic is going on the daemon's machine.

#### 4.17.7. `paths.*`

**4.17.7.1** `paths.list` MUST take `at` (a directory, `~` expanded, the home directory where
absent), `files` (boolean, to list files) and `hidden` (boolean, to list names starting with `.`),
and MUST answer `at` (spelled from `~` where under the home directory), `whole`, `up` (the parent,
`""` at the root), `entries` (each `name`, `dir`, directories first, at most 500) and `more` (how
many were left out); a directory that cannot be read MUST be refused 404.

**4.17.7.2** `paths.complete` MUST take `typed` and answer `paths`: at most 50 directories the text
typed could become, sorted, spelled as typed, each ending in `/`, names starting with `.` only where
a `.` was typed.

#### 4.17.8. `flows.check`

**4.17.8.1** `flows.check` MUST take `workspace`, `flow`, and, as `epic.start` takes them, `agents`,
`envs`, `params`, `budget`, `profile_flow`, `profile_environment`, `resume` and `backup`, and MUST
check everything `hmz exec` checks before an epic starts (Section 7.7 of [CLI]) but whether an env
can be reached, without starting the epic, any agent CLI or any env, and without reaching another
machine.

**4.17.8.2** `flows.check` MUST answer `flow` (as named), `ref`, `declared` (as `flows.get`
answers), `names` (`{role: agent name}`), `budget`, `backup` (the targets it would go to) and
`unreadable` (every limit of the budget nothing the epic drives can enforce, in words, or `""`).

**4.17.8.3** `flows.check` MUST refuse 400 with the `Refused` message of Section 4.6 of [PYTHON],
the one `hmz exec` prints after `hmz exec: error: `, for everything it finds.

### 4.18. Settings

#### 4.18.1. `settings.*`

**4.18.1.1** `settings.get` MUST take `workspace`, for a workspace that need not exist, and answer
`workspace`, `flow`, `chat` (the chat agent remembered there, or `""`), `prefer` (`native` or
`flow`, Section 3.4.13 of [FILES]), `ai_chan`, `details`, `harness_sessions`, `reports` (`null`
where never answered),
`flows` (the flows set up there), `backup` (`targets`, each `name`, `url` without credentials,
`branch`, `policies`, `every`; and `defaults`), `listen` and `ice_servers`.

**4.18.1.2** `settings.set` MUST take `workspace` and any of `chat` (an agent spec), `prefer`
(`native` or `flow`), `details` (boolean), `harness_sessions` (boolean),
`reports` (boolean), `backup` (`{targets, defaults}`, every target), `listen` (a list of listener
specs) and `ice_servers` (a list of `{urls, username, credential}`), MUST be a write, and MUST
answer as `settings.get` does.

**4.18.1.3** `settings.set` MUST write `chat` as `chat.agent` of the workspace, `prefer` as
`chat.prefer`, and `details`, `harness_sessions`, `backup`, `listen` and `ice_servers`
as Section 3 of [FILES] defines them, and `reports` as the key `enable_sentry` of Section 3 of
[FILES];
a change of `listen` MUST open and close listeners at once.

**4.18.1.4** A target whose `url` equals the credential-free URL `settings.get` answered MUST keep
the URL written; a `url` still holding `***@` otherwise MUST be refused 400.

**4.18.1.5** A value of another type, or a listener spec that is not one, MUST be refused 400 and
nothing written.

**4.18.1.6** `settings.forget` MUST take `workspace`, for a workspace that need not exist, forget
what that workspace was set up with, be a write, and answer `forgot` (whether there was anything)
beside what `settings.get` answers.

**4.18.1.7** `settings.get` MUST answer an `ice_servers` entry with its `credential` replaced by
`true` where one is written, and `settings.set` given an entry whose `credential` is `true` MUST
keep the one written.

#### 4.18.2. `accounts.*`

**4.18.2.1** `accounts.list` MUST answer `gateway` (`"LiteLLM"`), `accounts` (each `cli`, `name`,
`way`, `sets` (the names of the variables it sets), `made`, `models`, `asked`, `serves`) and
`backends` (each `cli`, `ways`, each `name`, `about`, `group`, `terminal`, `asks` (each `env`,
`about`, `secret`, `fixed`); and `wants`).

**4.18.2.2** An answer of the daemon MUST NOT carry the value of any variable an account sets.

**4.18.2.3** `accounts.create` MUST take `cli`, `name`, `way` and `answers` (`{variable: value}`),
and make the account; it MUST be refused 400 for an unknown way, a way whose `terminal` is true, a
variable left unanswered or an invalid name, and 409 for a name taken.

**4.18.2.4** `accounts.correct` MUST take `cli`, `name` and `answers`, write the account again
keeping every variable not answered, and be refused 400 for a variable the way does not ask and for
a way whose `terminal` is true.

**4.18.2.5** `accounts.remove` (`cli`, `name`), `accounts.models` (`cli`, `name`, `""` for the
daemon's machine's own) and `accounts.copy` (`cli`, `name`, `into`) MUST remove the account, ask the
CLI what it runs as that account, and copy the account to the CLI `into`; an unknown account MUST be
refused 404 and a CLI that will not answer 502.

**4.18.2.6** Every method of Section 4.18.2 but `accounts.list` MUST be a write and MUST answer as
`accounts.list` does.

#### 4.18.3. `nous.*`

**4.18.3.1** `nous.list` MUST answer `nous` (each `name`, `virtual`, `tries`, `policy`, `timeout`,
`graph` and `then`, each graph `null` or `start` and `nodes`, each node `id`, `use`, `balance`,
`among` (each `nous` and `weight`), `spread` and `on`), `policies`, `default`, `strategies`,
`faults` (every fault class and `*`), `concrete` (every concrete nous the daemon's accounts and
installed harnesses run, without an effort) and `scanning` (whether a scan of Section 4.18.3.6 is
going on). `concrete` MUST be answered from what each harness last said it runs, which the daemon
keeps: `nous.list` MUST NOT ask a harness.

**4.18.3.2** `nous.set` MUST take `name`, `tries` (default `0`), `policy` (default
`exponential-jitter`), `timeout` (seconds, `0` for none), `graph` and `then`, each graph in a shape
`NousBook.graph` of Section 4.11 of [PYTHON] reads, or `null`, write the nous whole, and answer as
`nous.list` does; a value `NousBook` refuses MUST be refused 400.

**4.18.3.3** `nous.rename` MUST take `name` and `to`, rename the virtual nous, and answer as
`nous.list` does; a rename `NousBook` refuses MUST be refused 400.

**4.18.3.4** `nous.clear` MUST take `name`, remove its nous, and answer as `nous.list` does; a nous
with nothing written MUST be refused 404, and one another nous names 400.

**4.18.3.5** `nous.set`, `nous.rename`, `nous.clear` and `nous.scan` MUST be writes.

**4.18.3.6** `nous.scan` MUST ask every installed harness what it runs, as the daemon's machine's
own sign-in and as each account made for it, keep each answer as `accounts.models` keeps it, and
answer as `nous.list` does with `failed`: each `cli` and `account` that would not answer, and
`why`. A harness that does not answer MUST NOT fail the call. One scan MUST go on at a time: a
`nous.scan` called while one is going MUST wait for that one and answer what it found.

#### 4.18.4. `runtimes.*`

**4.18.4.1** `runtimes.list` MUST answer `runtimes` (each as the runtime's `held()` of Section
4.20.6.1 of [PYTHON] gives it) and `blanks` (each backend's fields as a new runtime holds them).

**4.18.4.1.1** `runtimes.list` MUST also answer `local`, the daemon's own machine, where work runs
that names no runtime: its `host` (the host name), `system` and `machine` (as `uname -s` and
`uname -m` say them), `cpus` and `memory` (bytes). It is no runtime: it MUST NOT be among
`runtimes`, and no method writes or removes it.

**4.18.4.2** `runtimes.set` MUST take `backend`, `name`, `fields` and `replace` (boolean), and write
the runtime; `backend` or `name` among `fields`, or an invalid runtime, MUST be refused 400.

**4.18.4.3** `runtimes.remove` (`backend`, `name`) MUST remove the runtime, and `runtimes.check`
(`backend`, `name`) MUST answer what `Runtimes.check` of Section 4.10.12 of [PYTHON] returns, each
field by name; an unknown runtime MUST be refused 404.

**4.18.4.4** `runtimes.hosts` MUST answer `hosts`, each `alias`, `host`, `user`, `port`,
`identity_files`, `proxy_jump` and `saved`, every `Host` of the ssh configuration of the daemon's
machine; an unreadable ssh config MUST be refused 503.

**4.18.4.5** `runtimes.import` MUST take `names` (a list) and `update` (boolean), save an ssh
runtime per name, and answer as `runtimes.list` does; an empty list or unknown host MUST be refused
400.

**4.18.4.6** `runtimes.set`, `runtimes.remove` and `runtimes.import` MUST be writes and MUST answer
as `runtimes.list` does.

#### 4.18.5. `easytier.*`

**4.18.5.1** `easytier.list` MUST answer `networks`, each EasyTier entry of the daemon's machine
(Section 3.4.10 of [FILES]) as `name`, `nodes` and `secret`, `true` where one is written.

**4.18.5.2** `easytier.set` MUST take `name`, `secret` and `nodes`, write the entry, keeping the
secret written where `secret` is absent, be a write, and answer as `easytier.list` does; a secret
shorter than 16 bytes and an entry without nodes MUST be refused 400 with the sentences of Section
3.8.5.1 and Section 3.8.5.7.

**4.18.5.3** `easytier.remove` MUST take `name`, remove the entry, be a write and answer as
`easytier.list` does; an unknown name MUST be refused 404 and one a listener names 409, `<name> is
listened on.`

**4.18.5.4** `easytier.nodes` MUST answer `nodes`, the community's shared EasyTier nodes (Section
3.8.5.8), each `url`, `name`, `version`, `up` (boolean, or `null` where unknown) and `uptime` (from
0 to 1 over 24 hours, or `null` where unknown); a list that cannot be read MUST be refused 503, `The
community nodes could not be read: <why>`.

**4.18.5.5** An answer of the daemon MUST NOT hold an EasyTier secret.

### 4.19. Notices

#### 4.19.1. Notices

**4.19.1.1** The daemon MUST make a notice of each of these, for every epic it holds:

| Kind | When |
| --- | --- |
| `done` | An epic of a flow ended done; or a chat finished a turn |
| `failed` | An epic or a chat failed, crashed, ran out of budget or was refused |
| `stopped` | An epic of a flow was stopped |
| `asked` | A flow asked a person a question |
| `listening` | A flow waits for what to say next |

**4.19.1.2** A notice MUST hold `id` (an integer greater than every earlier one, across restarts of
the daemon), `kind`, `workspace`, `slot`, `epic`, `chat`, `flow`, `task`, `role`, `text` and `at`
(Unix seconds), as Section 10 of [CORE] defines them; of a chat's notice `epic` MUST be `""` and
`chat` the chat's name, and of any other `chat` MUST be `""`.

**4.19.1.3** The daemon MUST work notices out of each host's status without attaching to any host,
and MUST NOT make a notice of anything that already stood when it started; watching for notices MUST
NOT keep any host from going.

**4.19.1.4** The daemon MUST NOT filter notices by kind: which a user is told of is the client's
choice (Section 10.4.3 of [CORE]).

#### 4.19.2. `notices.*`

**4.19.2.1** `notices.list` MUST take `after` (an id, default `0`) and answer `notices` (those kept
after it, oldest first, the latest 200) and `last` (the newest id, `0` for none).

**4.19.2.2** `notices.subscribe` MUST take `after` (an id, or absent for from now), MUST open a
notices subscription as Section 6.8 of [WIRE] states, and MUST be answered with `sub` and `last`.

**4.19.2.3** `notices.unsubscribe` MUST take `sub`, end that subscription and answer `{}`.

### 4.20. Methods and the interfaces they replace

**4.20.1** The methods MUST serve everything the requests of protocol version 2 and the endpoints of
the HTTP interface of `hmz web` served before this version, as the following table maps them; `…`
stands for the path or method name of the row before.

| Before | Method |
| --- | --- |
| Control `list`, `status`, `detach`, `stop` | `hosts.list`, `.status`, `.detach`, `.stop` |
| `hello` | `epic.attach` |
| `start`, `say`, `answer`, `stop`, `force` | `epic.start`, `.say`, `.answer`, `.stop`, `.force` |
| `afk`, `claim`, `release`, `board` | `epic.afk`, `.claim`, `.release`, `.board` |
| `aside`, `unaside` | `epic.aside`, `epic.unaside` |
| `status`, `detach`, `quit` | `epic.status`, `epic.detach`, `epic.quit` |
| `GET /api/held` | `session.hello` and `hosts.running` |
| `GET /api/held/stream` | `epic.attach` with `figures` |
| `POST /api/held/{do}` | `epic.<do>` |
| `GET /api/btw`, `POST /api/btw`, `POST …/leave` | `btw.list`, `btw.ask`, `btw.leave` |
| `GET /api/runs`, `GET …/{name}` | `runs.list`, `runs.get` |
| `GET …/{name}/trace`, `…/timeline`, `…/timeline/span/{id}` | `runs.trace`, `.timeline`, `.span` |
| `GET …/{name}/bundle` | `runs.bundle` and `files.read` |
| `POST …/{name}/backup` | `runs.backup` |
| `POST /api/runs/import` | `files.create`, `files.write` and `runs.import` |
| `GET /api/backups/{target}/epics`, `POST …/pull` | `backups.epics`, `backups.pull` |
| `GET /api/usage` | `runs.usage` |
| `GET /api/flows`, `GET /api/flow`, `GET /api/backends` | `flows.list`, `.get`, `.backends` |
| `POST /api/flows/setup`, `POST …/fork` | `flows.setup`, `flows.fork` |
| `GET`, `POST /api/workspaces`, `POST …/forget` | `workspaces.list`, `.add`, `.forget` |
| `GET /api/flowverses`, `GET …/{name}` | `flowverses.list`, `flowverses.get` |
| `POST /api/flowverses`, `POST …/fetch` | `flowverses.add`, `flowverses.fetch` |
| `POST …/remove`, `…/install`, `…/uninstall` | `flowverses.remove`, `.install`, `.uninstall` |
| `GET /api/files`, `GET /api/paths` | `paths.list`, `paths.complete` |
| `GET`, `POST /api/settings`, `POST …/forget` | `settings.get`, `.set`, `.forget` |
| `GET`, `POST /api/accounts` | `accounts.list`, `accounts.create` |
| `POST …/correct`, `…/remove` | `accounts.correct`, `accounts.remove` |
| `POST …/models`, `…/copy` | `accounts.models`, `accounts.copy` |
| `GET`, `POST /api/fallbacks`, `POST …/clear` | `nous.list`, `.set`, `.clear` |
| `GET`, `POST /api/runtimes` | `runtimes.list`, `runtimes.set` |
| `POST …/remove`, `…/check` | `runtimes.remove`, `runtimes.check` |
| `GET /api/runtimes/hosts`, `POST …/import` | `runtimes.hosts`, `runtimes.import` |
| `GET /api/daemons/easytier/nodes` | `easytier.nodes` |
| `GET /api/notices`, `GET …/stream` | `notices.list`, `notices.subscribe` |

**4.20.2** The remote-daemon registry -- `GET` and `POST /api/daemons`, `POST /api/daemons/remove`,
`GET /api/daemons/hosts`, `POST /api/daemons/import`, `GET /api/daemons/{name}/state`, `POST
/api/daemons/{name}/connect` and `/d/{name}/api/...` -- MUST NOT be methods: each client keeps it
for itself (Section 3.8.1 of [WEB]), and reaches each daemon itself.

### 4.21. Reach

#### 4.21.1. General

**4.21.1.1** A session admitted on a scoped link (Section 4.22.6) MUST carry the reach of that
link's Ai-chan conversation: its `scope`, `workspace`, `epic`, `preset` and `network` (Section 14.2
of [CORE]). Every other session MUST carry none, and Section 4.21 MUST NOT hold it.

**4.21.1.2** The daemon MUST hold every call of a session that carries a reach to that reach, by the
extensions of Section 4.21.2, before the call is carried out and before its `idem` is looked up.

**4.21.1.3** A reach MUST reach a workspace where its scope is `daemon`, or where its scope is
`workspace` and the workspace is its own; the scope `epic` MUST NOT reach a workspace.

**4.21.1.4** A reach MUST reach an epic where its scope is `daemon`; where its scope is `workspace`
and the epic was run in its workspace; and where its scope is `epic` and the epic is its epic. No
reach MUST reach the epic of an Ai-chan conversation. A reach MUST reach a chat (Section 8 of
[CORE]) as it reaches an epic, by the chat's name in place of the epic's, and the scope `epic`
MUST reach the chat its `epic` names where that names a chat.

**4.21.1.5** A reach MUST reach a host where its scope is `daemon`; where its scope is `workspace`
and the host stands in its workspace; and where its scope is `epic` and the epic going, stopping or
last on that host (`epic` of Section 4.6.4.1, or `chat` for a chat) is its epic. A host that holds
no epic yet, a host of a new slot (Section 4.7.1.2) among them, MUST NOT be reached by the scope
`epic`.

**4.21.1.6** A reach MUST NOT reach a host of an `ai:` slot, whatever its scope (Section 4.21.5).

#### 4.21.2. Annotations

**4.21.2.1** Every method of [OPENRPC] MUST carry the extension `x-hmz-reach`, an object holding
`scope` and, for each of `workspace`, `slot`, `epic` and `sub` by which the method names what it acts
on, a key of that name whose value is the name of the parameter that carries it.

**4.21.2.2** Every method of [OPENRPC] MUST carry the extension `x-hmz-writes`, `true` for a method
that changes what the daemon, a host, an epic, a workspace or the settings hold, and `false` for
one that only reads; every write of Section 4.5.4 MUST carry `true`.

**4.21.2.3** The `scope` of `x-hmz-reach` MUST be one of the following, and a reach MUST reach the
method as its row states:

| `scope` | What the method acts on | Reached |
| --- | --- | --- |
| `any` | Nothing of one workspace; or what its answer lists, filtered as Section 4.21.4 states | always |
| `daemon` | The daemon, its machine, or every workspace | by the scope `daemon` alone |
| `workspace` | The workspace its parameters name | where the reach reaches that workspace |
| `epic` | The epic or host its parameters name | where the reach reaches that epic or host |
| `never` | Pairing, devices, credentials, the network's secrets, or Ai-chan conversations | never |

**4.21.2.4** The daemon MUST work out what a call acts on from the parameters `x-hmz-reach` names:
the workspace of a `workspace` parameter (Section 4.5.2); the host of a `workspace` and a `slot`, an
absent `slot` read as `""`; the epic an `epic` parameter names by its epic name, `""` read as the
epic in view on the workspace's own host where the method reads it so, the chat a `chat` parameter
of `btw.list` or `btw.ask` names being read in its place; and the host of the epic subscription a
`sub` parameter names, with that host's workspace.

**4.21.2.5** A call whose `workspace` parameter is absent where `x-hmz-reach` names one -- the call
then acting on every workspace, or on the machine alone -- MUST be held as a method whose `scope` is
`daemon`.

**4.21.2.6** `epic.attach` with `scratch` `true` MUST be held as a method whose `scope` is `daemon`,
and `epic.attach` with `slot` `chat:` or `exec:` alone, which makes a host, as one whose
`x-hmz-writes` is `true`.

**4.21.2.7** `epic.aside` with `runs`, `recall`, `kept` or `cwd` (Section 4.8.8.3) MUST be held as a
method whose `scope` is `never`: the session it opens is of an agent and in a directory the call
chooses, which no reach confines.

#### 4.21.3. Refusals

**4.21.3.1** A call of a session carrying a reach MUST be refused 403, by the first of the following
that holds, and MUST then have no effect:

1. `x-hmz-reach` `scope` is `never`: `Ai-chan cannot call <method>.`;
2. the call names a host of an `ai:` slot, by `slot` or by `sub`: `Ai-chan cannot reach an Ai-chan
   conversation.`;
3. the reach does not reach what the call acts on: `<method> is out of Ai-chan's scope: <what>.`,
   `<what>` being `the daemon`, `the workspace <workspace>`, `the epic <epic>`, `the host <slot>
   of <workspace>`, or `the host of <workspace>` for the slot `""`;
4. `x-hmz-writes` is `true` and the reach's preset is `read-only`: `Ai-chan is read-only, and
   <method> changes things.`

**4.21.3.2** A call to an epic (`sub`) MUST be held against the host as it stands when the call
comes.

**4.21.3.3** An epic subscription of a session whose reach has the scope `epic` MUST be ended with
`gone` `out of Ai-chan's scope` once an epic other than the reach's epic starts on its host.

#### 4.21.4. Answers filtered

**4.21.4.1** To a session carrying a reach, the daemon MUST leave out of each of the following
answers every entry that the reach does not reach, and every entry of an `ai:` slot, and MUST answer
as though the entries kept were all there are, counts and totals included:

- `hosts.list` (`held`) and `hosts.running` (`running`): each host;
- `workspaces.list`: each workspace;
- `runs.list` (`runs`, `total`, `counts`, `flows`): each epic;
- `chat.list` (`chats`, `total`): each chat;
- `notices.list`, `notices.subscribe` and `notices.event`: each notice, by the host it names.

#### 4.21.5. Ai-chan conversations

**4.21.5.1** `aichan.create`, `aichan.list`, `aichan.rename` and `aichan.forget` MUST carry the
`scope` `never`, and no reach MUST reach a host of an `ai:` slot (Section 4.21.1.6): Ai-chan neither
makes, lists, renames, watches, talks to nor forgets an Ai-chan conversation, her own included.

### 4.22. Ai-chan conversations

#### 4.22.1. General

**4.22.1.1** The daemon MUST hold each Ai-chan conversation (Section 14 of [CORE]) from
`aichan.create` until `aichan.forget`, across its own restarts, recorded as Section 4.16 of [FILES]
states.

**4.22.1.2** Each conversation MUST have an `id`, an integer one greater than the greatest `id`
recorded, `1` for the first; and a slot `ai:<hex>` of its own, of the workspace of its host: the
workspace of its scope, or, for the scope `daemon`, `<home>/ai/<machine>` (Section 4.16.1 of
[FILES]).

**4.22.1.3** Every host MUST name the session of a conversation's scoped link `Ai-chan#<id>`,
whatever name its `session.hello` says (Section 4.7.1.5).

#### 4.22.2. `aichan.create`

**4.22.2.1** `aichan.create` MUST take `scope` (text, required: `daemon`, `workspace` or `epic`),
`workspace` (required for the scopes `workspace` and `epic`, and absent for `daemon`), `epic` (an
epic name, required for the scope `epic`, and absent otherwise), `nous` (text, default `""` for the
nous the last conversation was made with, the `ai_chan` setting), `preset` (default `read-only`)
and `task` (text, required, not empty), and MUST be a write. The conversation's title MUST be the
first line of `task`, cut at 80 characters, until `aichan.rename` gives it another.

**4.22.2.2** `aichan.create` MUST record the conversation, make its scratch directory (Section 4.16.3
of [FILES]), start its host as Section 4.22.5.1 states, and, once that host has taken the start,
write its `nous` as the `ai_chan` setting (Section 3.4.3 of [FILES]) and be answered with `id`,
`workspace` (the workspace of its host) and `slot`. A conversation refused MUST NOT change that
setting.

**4.22.2.3** `aichan.create` MUST be refused 400 with `An Ai-chan's scope is daemon, workspace or
epic.` for another `scope`; `A <scope> scope names its workspace.` for a `workspace` missing; `A
daemon scope names no workspace and no epic.` and `A workspace scope names no epic.` for a parameter
given that the scope does not take; `An epic scope names its epic.` for an `epic` missing; `An
Ai-chan's preset is read-only or danger-full-access.` for another `preset`; `Name Ai-chan's nous:
the ai_chan setting names none.` for a `nous` of `""` where that setting names none; `<nous> is not
a nous or an agent spec.` for a `nous` that names no agent (Section 7.4 of [CLI]); and `Tell Ai-chan
something to start with.` for an empty `task`. It MUST be refused as Section 4.5.2 states for a
`workspace` that names no directory, 404 `There is no epic <epic> in <workspace>.` for an `epic` not
run in that workspace, and 409 with the host's `why` where its host refuses the start.

#### 4.22.3. `aichan.list`

**4.22.3.1** `aichan.list` MUST take no parameter and MUST answer `conversations`, one per
conversation, newest first, each with `id`, `title`, `scope`, `workspace` (the workspace of its
host), `epic` (the epic name of an `epic` scope, else `""`), `nous`, `preset`, `slot`, `state`,
`created` (`YYYY-MM-DDTHH:MM:SSZ`, in UTC), `latest` and `updated`.

**4.22.3.1.1** `latest` MUST be what was last said in the conversation as its entry keeps it
(Section 4.16.2 of [FILES]): the `task` it was made with until Ai-chan has answered, and from then
on her last answer, in either case with every run of whitespace made one space and cut at 120
characters; and `updated` MUST be when that was said, as `created` is written.

**4.22.3.1.2** While a host holds a conversation, the daemon MUST write its `latest` and its
`updated` down each time Ai-chan ends a turn on another answer. For a conversation whose entry
keeps no `latest`, one an earlier hmz made, `aichan.list` MUST read the last thing its chat's
assistant said out of its record, else its task, else `""`, and MUST write that down as its
`latest`, with its `created` as its `updated`; where it names a record that cannot be read, one
not yet moved among the chats (Section 8.7.10 of [CORE]), `aichan.list` MUST answer `""` and its
`created`, and MUST write neither down.

**4.22.3.2** `state` MUST be `running` while a host holds the conversation and its turn is open,
`waiting` while a host holds it between turns, and `folded` while no host holds it.

**4.22.3.3** `aichan.list` MUST NOT start a host.

#### 4.22.4. `aichan.forget`

**4.22.4.1** `aichan.forget` MUST take `id` (integer, required), MUST be a write, MUST close the
conversation's host where one holds it (Section 4.13.6), MUST forget it as Section 4.16.4 of
[FILES] states, and MUST answer `{}`.

**4.22.4.2** An `id` of no conversation MUST be refused 404, `There is no Ai-chan #<id>.`

#### 4.22.5. Ai-chan hosts

**4.22.5.1** The host of an `ai:` slot MUST, as it starts, have its conversation's chat (Section
14.4 of [CORE]), with what Section 14.4.2 of [CORE] names from the conversation's record, its
assistant the conversation's `nous`, and `HUMANIZE_AICHAN_LINK` naming the socket of its scoped link
(Section 3.11.2.17 of [FILES]): anew, with the task of `aichan.create` as the first message, the
first time; and carrying on its recorded chat, waiting between turns, every later time.

**4.22.5.2** `epic.attach` naming the `ai:` slot of a conversation whose host has gone, or is going
as it is attached to, MUST start that host as Section 4.22.5.1 states and attach to it; `epic.attach` and `hosts.open` naming an
`ai:` slot of no conversation MUST be refused 404, `There is no Ai-chan conversation <slot>.`

**4.22.5.3** `epic.stop` and `chat.stop` on an Ai-chan host MUST interrupt Ai-chan's open turn and
leave the conversation between turns (Section 14.8.3 of [CORE]); while no turn is open each MUST be
refused with `Ai-chan is not answering, so there is nothing to stop`.

**4.22.5.4** An Ai-chan host MUST fold its conversation as Section 4.13.8.3 states, and MUST then go
once it is idle.

#### 4.22.6. Scoped links

**4.22.6.1** Before it starts the host of an Ai-chan conversation, the daemon MUST listen on that
conversation's scoped link, the socket of Section 7.6.9 of [FILES], and MUST admit each session
over it as one over a trusted carrier is admitted (Section 3.5.4 of [WIRE]), holding it to the
conversation's reach (Section 4.21).

**4.22.6.2** On a scoped link, a `session.hello` whose kind is not `ai-chan` MUST be refused 403,
`This link is Ai-chan's.`; over any other carrier, a `session.hello` whose kind is `ai-chan` MUST be
refused 403, `Only Ai-chan says hello as ai-chan.`

**4.22.6.3** The daemon MUST stop listening on a scoped link, and close every session over it, when
the host of its conversation goes.

#### 4.22.7. `aichan.rename`

**4.22.7.1** `aichan.rename` MUST take `id` (integer, required) and `title` (text, 1 to 240
characters), MUST be a write, MUST record `title` as the conversation's title with its white space
runs collapsed to single spaces, whether or not a host holds the conversation, and MUST answer
`{}`.

**4.22.7.2** A `title` of white space alone MUST be refused 400, `A conversation's title says
something.`, and an `id` of no conversation 404, `There is no Ai-chan #<id>.`

### 4.23. Envs of an epic

#### 4.23.1. General

**4.23.1.1** Each method of Section 4.23 MUST take `workspace` and `slot`, naming a host; each but
`hosts.env.list` MUST also take `env` (text, required), the name of an env role of the epic going on
that host. Each MUST be carried out by that host, on that env, as the epic's flow would carry it out
through the env (Section 7 of [CORE]), without attaching to the host and without telling the epic.

**4.23.1.2** A `path` MUST be read relative to the env's workdir; a `path` that leaves the workdir,
by `..`, as an absolute path outside it or through a symbolic link, MUST be refused 400, `<path> is
outside the env <env>.`

**4.23.1.3** A host with no epic going MUST refuse 409, `no flow is running, so no env is open`; an
`env` naming no env role of that epic MUST be refused 404, `The epic has no env <env>.`; and an env
that cannot do what is asked MUST be refused 409, `The env <env> cannot <what>.`, `<what>` being
`read files`, `write files`, `run commands` or `search files`.

**4.23.1.4** `hosts.env.write` and `hosts.env.exec` MUST be writes, and `hosts.env.list`,
`hosts.env.read` and `hosts.env.grep` MUST NOT.

#### 4.23.2. `hosts.env.list`

**4.23.2.1** `hosts.env.list` MUST answer `envs`, one per env role of the epic going on the host,
each with `name` (the role), `kind` (the env's kind, Section 7 of [CORE]), `workdir` (its workdir on
its machine) and `can` (those of `read`, `write`, `exec` and `grep` the env offers).

#### 4.23.3. `hosts.env.read`

**4.23.3.1** `hosts.env.read` MUST take `path` (text, required), `offset` (default `0`) and `length`
(default and at most `1048576`), and MUST answer `text` (the bytes of the file from `offset`, at
most `length` of them, read as UTF-8, each byte that is not of valid UTF-8 replaced by U+FFFD),
`size` (the file's length in bytes) and `eof` (whether they reach its end).

**4.23.3.2** A `path` that names no file MUST be refused 404, `There is no file <path> in <env>.`

#### 4.23.4. `hosts.env.write`

**4.23.4.1** `hosts.env.write` MUST take `path` (text, required) and `text` (text, required), MUST
write `text` as UTF-8 as the whole of that file, making the directories it lies in, and MUST answer
`size`, the bytes written.

#### 4.23.5. `hosts.env.exec`

**4.23.5.1** `hosts.env.exec` MUST take `argv` (a list of text, required, not empty) and `seconds`
(1 to 3600, default `120`), MUST run `argv` in the env's workdir, and MUST answer `code` (its exit
status, or `null` where it was killed once `seconds` had passed), `stdout` and `stderr` (each the
last 1048576 bytes it wrote there, read as `hosts.env.read` reads them).

**4.23.5.2** An empty `argv` MUST be refused 400, `hosts.env.exec runs a command: give argv.`

#### 4.23.6. `hosts.env.grep`

**4.23.6.1** `hosts.env.grep` MUST take `pattern` (text, required, an extended regular expression of
POSIX), `path` (default `.`) and `limit` (1 to 2000, default `200`), MUST search every file under
`path`, and MUST answer `matches`, at most `limit` of them, each `path` (relative to the workdir),
`line` (from 1) and `text` (the line, cut at 400 characters), and `more` (whether there were more).

### 4.24. Environments

#### 4.24.1. General

**4.24.1.1** A **call to an environment** is a method of Section 4.24. Each MUST take `sub`, an epic
subscription, as a call to an epic does (Section 4.8.1.1), and exactly the fields its paragraph
lists; every one but `env.term.input`, `env.term.resize`, `env.term.ack` and `env.term.close` MUST
take `env`, the `id` of one entry of the snapshot `envs` (Section 4.24.2).

**4.24.1.2** The host the subscription is attached to MUST carry out a call to an environment, and
the call MUST be answered as Section 4.7.2 states, with the refusals of this section as `why`.

**4.24.1.3** A call to an environment MUST be carried out apart from the order of Section 4.7.3.1,
so that no other call waits on it.

**4.24.1.4** `env.write`, `env.mkdir`, `env.rename`, `env.remove`, `env.git.stage`,
`env.git.unstage`, `env.git.discard`, `env.git.commit` and `env.git.rewind` MUST be writes.

**4.24.1.5** A `path` MUST name a path of the env machine: relative to the env's workdir, or an
absolute POSIX path. Bytes -- `data`, `replay`, `old` and `new` -- MUST be base64 [RFC4648].

**4.24.1.6** A call to an environment MUST reach only what the env serves, as Section 7.13 of
[CORE] states, whatever its role declares.

**4.24.1.7** A call to an environment MUST be refused with the first of these that holds:

| Where | `why` |
| --- | --- |
| `env` names no entry of `envs` | `There is no environment <id>.` |
| The env has closed, or its epic is over | `That environment has closed.` |
| The env does not serve what the call needs | `<role>: this environment has no <what>.` |
| `term` names no terminal of the host | `There is no terminal <term>.` |
| `path` names nothing | `No such file: <path>` |

`<what>` MUST be `files` for the calls of Section 4.24.3, `shell` for those of Section 4.24.4, and
`git` for those of Section 4.24.5.

**4.24.1.8** Each write of Section 4.24, and `env.term.open` opening a terminal, MUST be recorded
with `env_used` (Section 4.9.2.4) once it is carried out, `what` being, in the order of Section
4.24.1.4, `wrote`, `made`, `renamed`, `removed`, `staged`, `unstaged`, `discarded`, `committed` and
`rewound`, and `opened a terminal`; `path` MUST be the `path` the call named, where it named one.
What is typed into a terminal and what a terminal prints MUST NOT be recorded.

#### 4.24.2. The snapshot `envs`

**4.24.2.1** `envs` MUST hold one entry per environment of the epic going, or of the last one, of
its host -- every root env of its roles, and of a chat its workspace, and every derived env -- each
root env in the order of its roles, and each derived env after the env it was derived from.

**4.24.2.2** Each entry MUST carry: `id`, text a client MUST NOT read anything into, the same for one
env for the life of its host; `role`, the env role; `chain`, the env's label, its role followed by
each derivation that made it (Section 3.11 of [PYTHON]); `parent`, the `id` of the env it was
derived from, or `null`; `run`, its epic number; `backend`, its kind (Section 7.2.1 of [CORE]);
`provider` (Section 7.2.2 of [CORE]); `workdir` (Section 7.2.4 of [CORE]); `available`, whether the
calls of Section 4.24 reach it at all; `open`, whether it is open; `caps`; `declared`; and `facts`,
`{cpu, memory, gpu_count, gpu_memory}` as its probe found them (Section 7.3.1.4 of [CORE]), each
`null` where not found.

**4.24.2.3** `caps` and `declared` MUST each be a list of the names `files`, `shell`, `bash`, `git`,
`git_worktree`, `rewind`, `scratch` and `temp_clone`, which stand for `FilesEnvMixin`,
`ShellEnvMixin`, `BashEnvMixin`, `GitEnvMixin`, `GitWorktreeEnvMixin`, `RewindableEnvMixin`,
`ScratchDirEnvMixin` and `TemporaryClonedDirEnvMixin` (Section 3.11 of [PYTHON]): `caps` those the
env serves (Section 7.3.2.3 of [CORE] and Section 7.3.2.4 of [CORE]), `declared` those its role
declares.

**4.24.2.4** A host MUST send `envs` again whenever an env is opened, derived, destroyed or closed,
and when an epic starts.

#### 4.24.3. Files

**4.24.3.1** `env.list` MUST take `path`, and MUST answer `path`, that directory as an absolute
path, and `entries`, one per entry of it, directories first and then by name, each `name`, `kind`
(`file`, `dir`, `link` or `other`), `size` (bytes), `mtime` (Unix seconds, with a fraction) and, of
a link, `target`.

**4.24.3.2** `env.stat` MUST take `path`, and MUST answer that path as an entry of `env.list` is
answered, with `path` as an absolute path.

**4.24.3.3** `env.read` MUST take `path`, `offset` (integer, `0`) and `length` (integer, 1 048 576,
and at most that), and MUST answer `data`, at most `length` bytes of the file from `offset`; `size`
and `mtime`, of the whole file; `etag`, the SHA-256 of the whole file in lowercase hexadecimal; and
`eof`, whether `data` reaches the end of the file.

**4.24.3.4** `env.find` MUST take `limit` (integer, 20 000), and MUST answer `paths`, at most `limit`
files of the env's workdir relative to it, and `truncated`, whether there were more: in a git
repository the files `git ls-files -co --exclude-standard` lists, and elsewhere every file but those
under a directory named `.git` or `node_modules`.

**4.24.3.5** `env.search` MUST take `query` (text, required, not empty), `regex` (boolean, `false`:
whether `query` is a regular expression rather than literal text), `case` (boolean, `false`:
whether case counts), `glob` (text, `""`: where not empty, the glob a file's path MUST match) and
`limit` (integer, 2 000), and MUST answer `matches`, at most `limit`, each `path` (relative to the
workdir), `line` and `column` (each counting from 1) and `text` (the line), and `truncated`, whether
there were more. It MUST search the files `env.find` would list, with `rg` where it is on the env
machine's `PATH`, else with `grep`, skipping binary files.

**4.24.3.6** `env.write` MUST take `path`, `data` (required) and `if_match` (text or `null`, `null`),
MUST make the file hold exactly `data`, and MUST answer the file's new `etag`, `size` and `mtime`.
With `if_match` `null` it MUST write whatever the file holds; with `if_match` `""` it MUST write only
where there is no file at `path`; with any other `if_match` it MUST write only where the file's
`etag` is `if_match`. A write refused for `if_match` MUST be refused with `<path> changed since you
read it.` and MUST leave the file as it was.

**4.24.3.7** `env.mkdir` MUST take `path`, and MUST make that directory and every missing directory
above it; `env.rename` MUST take `path` and `to`, and MUST move `path` to `to`; `env.remove` MUST
take `path`, and MUST remove it and everything under it. Each MUST answer `{}`.

#### 4.24.4. Terminals

**4.24.4.1** A **terminal** is a process a frontend runs in an env under a pseudo-terminal, as
Section 7.13 of [CORE] states. A host MUST give each terminal an id, text that names no other
terminal of the host. A frontend **views** a terminal from when it opens it or attaches to it again
with `env.term.open` until the terminal ends, it closes it, or it leaves (Section 4.7.4).

**4.24.4.2** `env.term.open` MUST take `cols` and `rows` (integers, required, at least 1) and `term`
(text). Without `term` it MUST start a terminal of that size in the env's workdir, and MUST answer
`term`, its id; `shell`, the command it runs as a list of words, or `null` where it runs the login
shell of Section 7.13.4 of [CORE]; and `replay`, `""`. With `term`, a terminal of that env, it MUST
start no terminal, MUST resize that one to `cols` and `rows`, and MUST answer as without, `replay`
being what that terminal kept (Section 7.13.6 of [CORE]).

**4.24.4.3** What a terminal prints MUST be sent to every frontend that views it, and to no other,
as the message `term`, carrying `term` and `data`: at most 64 KiB each, of what the terminal printed
over about 16 milliseconds, in order. When a terminal ends, every frontend that views it MUST be
sent `term_exit`, carrying `term` and `status`, its exit status, `128 + n` where signal `n` ended
it. Neither is a history record nor a snapshot (Section 4.9.5).

**4.24.4.4** `env.term.input` MUST take `term` and `data` (required), and MUST type `data` into the
terminal; `env.term.resize` MUST take `term`, `cols` and `rows` (as `env.term.open` takes them), and
MUST resize the terminal; each MUST answer `{}`.

**4.24.4.5** `env.term.ack` MUST take `term` and `bytes` (integer, required), the bytes of `data` of
that terminal this frontend has drawn since its last `env.term.ack`, and MUST answer `{}`.

**4.24.4.6** A host MUST NOT send a frontend more of a terminal's output while more than 1 MiB of
what it sent that frontend of that terminal is not acknowledged, and MUST stop reading the terminal
while every frontend that views it is so far behind, so that what the terminal prints waits in the
terminal rather than in the host or the daemon (Section 6.10 of [WIRE]).

**4.24.4.7** `env.term.close` MUST take `term`, MUST kill that terminal as Section 7.13.5 of [CORE]
states, and MUST answer `{}`.

**4.24.4.8** `env.term.list` MUST answer `terms`, every terminal of that env that is alive or that
a frontend still views, each `term`, `env`, `title` (a name for the user), `cols`, `rows` and
`alive`.

**4.24.4.9** A terminal MUST outlive every frontend that views it, as Section 7.13.5 of [CORE]
states; several frontends MAY view it at once, and each MAY type into it.

**4.24.4.10** `env.term.open` and `env.term.input` on a session over an untrusted carrier (Section
3.5 of [WIRE]) MUST be refused with `Terminals are off for paired devices; turn on
envs.paired_terminals.` unless the setting `envs.paired_terminals` of the daemon's machine is `true`
(Section 3.4.12 of [FILES]), read at each call.

#### 4.24.5. Git

**4.24.5.1** The calls of Section 4.24.5 MUST work the git repository the env's workdir is in, with
git's optional locks off (`--no-optional-locks` and `GIT_OPTIONAL_LOCKS=0`), no pager
(`GIT_PAGER=cat`) and paths unquoted (`core.quotepath=off`), and MUST be refused with `<role>: this
environment has no git.` where the env serves neither `GitEnvMixin` nor `GitWorktreeEnvMixin`, or
its workdir is in no repository.

**4.24.5.2** `env.git.status` MUST answer `root`, the repository's top directory; `branch`, the
branch checked out, or `null` where none is; `head`, the commit checked out, or `null` before the
first; `upstream`, the branch's upstream, or `null`; `ahead` and `behind`, the commits the branch is
ahead of and behind its upstream; and `files`, each `path` (relative to `root`), `orig` (where it was
renamed or copied from, only where it was), `index` and `worktree` (the `X` and `Y` characters of
`git status --porcelain=v2`, `.` for unchanged and `?` for untracked) and `state` (`conflict` for an
unmerged path, `untracked` for an untracked one, `changed` otherwise).

**4.24.5.3** `env.git.diff` MUST take `path` and `staged` (boolean, `false`), and MUST answer `old`
and `new`, the two sides of that file's change -- the index and the worktree, or with `staged` the
commit checked out and the index -- each `null` where that side has no such file, and `binary`,
whether git reads either side as binary.

**4.24.5.4** `env.git.log` MUST take `limit` (integer, 50), and MUST answer `commits`, at most
`limit` commits from the one checked out, newest first, each `hash`, `parents`, `author`, `date`
(ISO 8601) and `subject`.

**4.24.5.5** `env.git.stage`, `env.git.unstage` and `env.git.discard` MUST each take `paths`
(required, not empty): `env.git.stage` MUST add those paths to the index, removals included;
`env.git.unstage` MUST make the index of those paths that of the commit checked out; and
`env.git.discard` MUST make the worktree of those paths that of the index, and remove those that are
untracked. Each MUST answer `{}`.

**4.24.5.6** `env.git.commit` MUST take `message` (text, required, not empty) and `amend` (boolean,
`false`), MUST commit the index with that message, amending the commit checked out where `amend` is
`true`, and MUST answer `head`, the new commit.

**4.24.5.7** `env.git.snapshots` MUST answer `snapshots`, the snapshot refs of the env as
`snapshots` answers them (Section 3.11.7 of [PYTHON]); `env.git.rewind` MUST take `ref`, one of
them, MUST rewind the env to it as `rewind` does, and MUST answer `{}`.

**4.24.5.8** `env.git.rewind` MUST be refused with `<role> is working here; stop it first`, `<role>`
the role of the session, while a session working in that env has a turn open.

### 4.25. Chats

#### 4.25.1. `chat.start`

**4.25.1.1** `chat.start` MUST take `workspace`, `slot` (a chat slot, or `chat:` alone for a new
one, `chat:`), `agent` (an agent spec, as `epic.start` takes one for a role), `task` (text,
required; not empty but with `resume`), `resume` (the name of a chat of the workspace, `null`), `prefer` (`native`,
`flow` or `null`), `permission` (`read-only`, `workspace-write`, `danger-full-access` or `null`),
`worktree` (boolean, `false`) and `remember` (boolean, `false`), and MUST be a write.

**4.25.1.2** `chat.start` MUST start the host of that slot as `epic.attach` does (Section 4.7.1.2),
without attaching to it, MUST start a chat there (Section 8 of [CORE]) with `agent` as its assistant
and `task` as its first message, and MUST be answered with `slot` and `chat`, the chat's name
(Section 8.2.12 of [CORE]).

**4.25.1.3** With `resume`, `chat.start` MUST carry on the chat of that name (Section 8.7 of
[CORE]), `task` being its next turn, with `agent` where given and the chat's own agent otherwise.

**4.25.1.4** With `prefer`, `chat.start` MUST record it as the chat's override (Section 8.9.10 of
[CORE]).

**4.25.1.5** With `remember` `true`, `chat.start` MUST write `agent` as the chat agent of the
workspace (Section 3.5.1.9 of [FILES]) once the host has taken the start; a refused start MUST
leave it as it was.

**4.25.1.6** `chat.start` MUST be refused 400 with `a chat starts with something said` for an empty
`task` without `resume`, `<slot> is not a chat slot.` for a slot that is not one, `an agent for the chat is named`
for a missing `agent` without `resume`, `permission is read-only, workspace-write or
danger-full-access` for a `permission` that is none of them, and the reason of Section 8.3.7 of
[CORE] for an agent it refuses; 404 with `<resume> is not a chat of <workspace>.` for a `resume`
that names none, an epic an earlier hmz recorded for a chat that the daemon has not yet moved
among them (Section 8.7.10 of [CORE]);
and 409 with `a chat is already going on <slot>` for a slot whose host holds one.

**4.25.1.7** With `permission`, `chat.start` MUST start the chat with that permission (Section
8.3.9 of [CORE]); without it, with `workspace-write`, or, with `resume`, with the permission the
chat records (Section 8.3.11 of [CORE]).

**4.25.1.8** With `worktree` `true`, `chat.start` MUST start the chat in a new git worktree of the
workspace (Section 8.3.13 of [CORE]); it MUST be refused 400 with `a chat carried on works where it
worked` where `resume` is given too, and with what git said where no worktree can be added, no
chat being recorded.

**4.25.1.9** With `resume` and an empty `task`, `chat.start` MUST carry the chat on with nothing
said (Section 8.7.4 of [CORE]): its host MUST hold the chat's workspace open (Section 4.24.2.1)
and wait between turns, and what `chat.say` then says MUST be the turn that carries it on. Where
a host already holds that chat, `chat.start` MUST start nothing and MUST be answered with that
host's `slot` and the chat's name. With `resume` and a `task` that is not empty, where a host
holds that chat and nothing has been said to it since it was so carried on, `chat.start` MUST
start nothing, MUST set the `prefer` and the `permission` it gives, MUST say `task` to that host
as `chat.say` says it (Section 4.25.2), which carries the chat on, and MUST be answered with that
host's `slot` and the chat's name; where `agent` names another agent than that host's, the daemon
MUST instead first end the chat there as an empty `chat.say` does and start it as though no host
had held it. Where a host holds that chat and something has been said to it, `chat.start` with a
`task` that is not empty MUST be refused 400 with `<resume> is going on already`. Calls with one
`resume` made at once MUST be answered as though made one after another.

#### 4.25.2. `chat.say`

**4.25.2.1** `chat.say` MUST take `workspace`, `slot` and `text` (text, required), MUST be a write,
and MUST be answered `{}`.

**4.25.2.2** `chat.say` MUST serve `text` as Section 8.9 of [CORE] states, and MUST otherwise say
it to the chat: as the next turn between turns, into the open turn where its harness accepts a
message mid-turn, and held for the next turn otherwise (Section 8.4 of [CORE]); an empty `text`
MUST end the chat (Section 8.4.7 of [CORE]).

**4.25.2.3** A line `chat.say` delivers, holds, has refused or drops MUST be recorded as Section
4.10.1.6 states for `epic.say`.

**4.25.2.4** `chat.say` MUST be refused 400, naming the line, for a `$` line that names a flow and
for a name Section 8.9.7 of [CORE] keeps, which the frontend serves; 404 as Section 4.6.1.1 states
where no host holds the slot; and 409 with `this chat has folded away; carry it on with
chat.start` on a chat host that has folded (Section 4.13.8).

#### 4.25.3. `chat.commands`

**4.25.3.1** `chat.commands` MUST take `workspace` and `slot`, and MUST answer `entries`,
`prefer`, `prefer_from`, `permission` and `listed`.

**4.25.3.2** `entries` MUST hold the catalogue of the chat's conversation (Section 8.9.2 of [CORE]),
or, before it has opened, what the catalogue of its harness holds without one, each `sigil`,
`name`, `about`, `how` and `source` `native`; then each name Section 8.9.7 of [CORE] keeps, with
`source` `hmz` and `how` `""`; then each flow on offer in the workspace, with sigil `$`, `source`
`flow` and `how` `""`.

**4.25.3.3** `prefer` MUST be the chat's preference, `native` or `flow`, and `prefer_from` MUST be
`chat` where the chat overrides it and `settings` otherwise.

**4.25.3.4** `listed` MUST be whether the catalogue is all its harness lists, which it is once the
chat's conversation has taken a turn (Section 8.9.13 of [CORE]).

**4.25.3.5** `permission` MUST be the chat's permission as it was last set (Section 8.3.9 of
[CORE]), or `null` for an Ai-chan conversation.

#### 4.25.4. `chat.set`

**4.25.4.1** `chat.set` MUST take `workspace`, `slot` and either or both of `prefer` (`native` or
`flow`) and `permission` (`read-only`, `workspace-write` or `danger-full-access`), MUST be a write,
and MUST be answered `{}`. It MUST record `prefer` as the chat's override (Section 8.9.10 of
[CORE]), and MUST set `permission` as the chat's permission, which holds from its next turn (Section
8.3.10 of [CORE]).

**4.25.4.2** `chat.set` MUST be refused 400 for a `prefer` that is neither, with `permission is
read-only, workspace-write or danger-full-access` for a `permission` that is none of them, and with
`chat.set takes prefer or permission` where it is given neither; 409 with `an Ai-chan conversation
keeps its permission` for a `permission` on a host of hers; and as `chat.say` is for a slot no host
holds or a chat that has folded.

#### 4.25.5. `chat.list` and `chat.get`

**4.25.5.1** `chat.list` MUST take `workspace` (only that workspace's chats, reading the chats of a
workspace since removed; every workspace's where absent), `archived` (boolean, `false`: `true` for
the archived chats alone, otherwise those not archived alone), `q` (text found in the title, the
first message or the name), `offset` (default `0`) and `limit` (default `50`, at most `200`), and
MUST answer `chats` (chat rows, newest begun first), `total`, `offset` and `limit`.

**4.25.5.2** A chat row MUST hold `id` (the chat's name), `title` (Section 8.10.1 of [CORE], cut at
240 characters), `workspace`, `workdir` (where its assistant works: the workspace, or the worktree
of Section 8.3.13 of [CORE]), `agent` (its assistant as an agent spec), `model`, `began`, `updated`
(when its record was last written), `state`, `slot` (the slot of the host holding it, `""` for
none), `asking` (the questions its assistant asked mid-turn and waits on, each `<run>:<question>`),
`permission` (Section 8.3.9 of [CORE]), `archived` (boolean) and `spent` (as an epic row's, Section
4.16.2.1).

**4.25.5.3** `state` MUST be the first of these that holds: `asking`, where a host holds the chat
and its assistant waits on an answer mid-turn; `turn`, where a host holds it and its turn is open;
`going`, where a host holds it between turns, or another process holds it; `failed`, where it ended
failed (Section 8.4.9 of [CORE]); and `resting` otherwise.

**4.25.5.4** `chat.get` `{chat, trace}` MUST answer the chat row of the chat of that name, of
whichever workspace, with `at` (its directory), `task` (its first message, whole), `prefer` (its
override, `""` for none), `forked` (the name of the chat it was forked from, `""` for none),
`adopted` (the harness session it was made from, `<harness>:<id>`, `""` for none),
`agents` and `sessions` (as `runs.get` answers them, Section 4.16.3.1), `earlier` (how many of its
sessions it opened before it was last carried on), `backup` and `backed` (as an epic row's); and,
with `trace` `true`, `trace`, what `runs.trace` answers as `sessions` for an epic (Section 4.16.4),
read of the chat's sessions.

**4.25.5.5** A `chat` that names no chat MUST be refused 404, `There is no chat <name>.`, by every
method of Section 4.25 that takes `chat`.

**4.25.5.6** `chat.list` MUST leave out every Ai-chan conversation, kept or forgotten, and the one
the host of an `ai:` slot holds (Section 14.7.4 of [CORE]); every method of Section 4.25.7 MUST
refuse one as Section 4.25.5.5 states; and `chat.get` MUST answer one.

#### 4.25.6. `chat.stop`

**4.25.6.1** `chat.stop` MUST take `workspace` and `slot`, MUST be a write, and MUST be answered
`{}`. It MUST interrupt the chat's open turn and leave the chat between turns, as Section 8.5.4 of
[CORE] states; it MUST NOT end the chat.

**4.25.6.2** `chat.stop` MUST be refused 409 with `no turn is open, so there is nothing to stop`
while no turn is open, and as `chat.say` is for a slot no host holds or a chat that has folded
(Section 4.25.2.4).

#### 4.25.7. `chat.rename`, `chat.fork`, `chat.archive`, `chat.unarchive`, `chat.backup` and `chat.delete`

**4.25.7.1** Each method of this section MUST take `chat` (a chat's name, required) and MUST be a
write; each MUST act on the chat whether or not a host holds it, except as stated.

**4.25.7.2** `chat.rename` MUST take `title` (text, 1 to 240 characters), MUST record it as the
chat's title with its white space runs collapsed to single spaces (Section 8.10.1 of [CORE]), and
MUST be answered with the chat row; a `title` of white space alone MUST be refused 400.

**4.25.7.3** `chat.fork` MUST make the fork of Section 8.10.2 of [CORE] and MUST be answered with
`chat`, the new chat's name. It MUST be refused 409, saying why, while the chat's turn is open,
while a process that is no host holds the chat, and where the chat's conversation is not kept in
the chat's directory.

**4.25.7.4** `chat.archive` and `chat.unarchive` MUST record the chat as archived or as not
(Section 8.10.3 of [CORE]) and MUST be answered with the chat row.

**4.25.7.5** `chat.backup` MUST take `to` (target names; absent for the targets the chat was
started with), MUST back the chat up as `runs.backup` backs up an epic (Section 4.16.5), and MUST be
answered and refused as `runs.backup` is.

**4.25.7.6** `chat.delete` MUST remove the chat's directory (Section 8.10.4 of [CORE]) and MUST be
answered `{}`. Where a host holds the chat between turns, the daemon MUST first end the chat there
as an empty `chat.say` does (Section 4.25.2). It MUST be refused 409 with `Chat <name> has a turn
open; delete it once it is done.` while the chat's turn is open or a process that is no host
holds the chat.

#### 4.25.8. `chat.harness.list`, `chat.harness.get` and `chat.harness.adopt`

**4.25.8.1** `chat.harness.list` MUST take `workspace` (required), `offset` (default `0`) and
`limit` (default `50`, at most `200`), and MUST answer `sessions` (harness session rows, last
written first), `total`, `offset` and `limit`. It MUST answer whatever the setting
`harness_sessions` holds: that setting governs what a frontend lists (Section 8.11.3 of [CORE]),
not what the daemon answers.

**4.25.8.2** The harness sessions of a workspace (Section 8.11.1 of [CORE]) MUST be the sessions
that each of the harnesses `claude`, `codex`, `grok`, `pi`, `omp`, `qwen`, `kimi`, `mcode`, `dsh`,
`opencode`, `mimo` and `agy` installed on the daemon's machine keeps in its own home, that worked
in the directory of that workspace, that no other session started or was forked into, and that no
chat and no epic of the machine records as opened (`opened`, Section 6.5.4 of [FILES]) by that
harness under that session id. A harness whose home is within `<home>`, or cannot be read, MUST
list none and MUST NOT fail the call.

**4.25.8.2.1** Where a session worked MUST be read, for `kimi`, from `workDir` of the `state.json`
of the session's directory; for `mcode`, from `workspaceDir` of the session's record in
`v2/sqlite/runtime-state.sqlite`; for `opencode` and `mimo`, from `directory` of the session's row
of the table `session` of `opencode.db` and `mimocode.db`; and for `agy`, from `workspace_uris` of
the conversation's row of the table `conversation_summaries` of `conversation_summaries.db`. A
`dsh` session whose log is compressed MUST NOT be listed.

**4.25.8.3** A harness session row MUST hold `id` (the id its harness gave the session), `harness`,
`title` (the first line the user said in it, cut at 240 characters, `""` where the head of its log
gives none; for `opencode`, `mimo` and `agy`, the first line of the title the harness keeps for it,
and for an `agy` conversation that has none, of its `preview`, cut alike), `workspace`, `model` (the
model it last ran on, `""` where its log gives none, and for `agy`), `began`, `updated` (when its
log was last written; for `opencode` and `mimo`, when its row says it was last updated) and
`continuable` (boolean: `true` for a session of `claude`, `codex`, `grok`, `pi`, `omp` or `qwen`,
`false` for any other).

**4.25.8.4** To list harness sessions the daemon MUST read no more of a session's log than its
first 128 KiB and its last 128 KiB, and of a database that holds every session of a harness no more
than the rows that say its sessions: no row of what was said in one.

**4.25.8.5** `chat.harness.get` MUST take `workspace`, `harness` and `session` (each required) and
`trace` (boolean), and MUST answer the harness session row of that session; with `trace` `true`,
with `trace` as `chat.get` answers it (Section 4.25.5.4), read of that session and of the sessions
it started. A session that is no harness session of the workspace MUST be refused 404, `There is no
<harness> session <session> of <workspace>.`, by `chat.harness.get` and by `chat.harness.adopt`.

**4.25.8.6** `chat.harness.adopt` MUST take `workspace`, `harness` and `session` (each required)
and `agent` (an agent spec of that harness), MUST be a write, MUST make the chat of Section 8.11.4
of [CORE], recorded as Section 6.12.12 of [FILES] states, and MUST be answered with `chat`, the new
chat's name. It MUST be refused 409 with `A session of <harness> cannot be continued in a chat.`
for a harness whose sessions are not continuable (Section 4.25.8.3), and 409, saying why, for an
`agent` of another harness, for a session that gives no model where `agent` is absent, and where
the session's files cannot be copied.

## 5. Security Considerations

Who can connect. Over its socket the daemon is reached only by the user of its machine: the daemon
directory is created with mode `0700` and refused where it is not owned by the user or is writable
by its group or by others, and the socket and the daemon record have mode `0600` (Section 4.3.2 of
this document, Section 7.3.1 of [FILES], Section 7.3.2 of [FILES], Section 7.6.1 of [FILES] and
Section 7.6.2 of [FILES]). `ssh` and WSL admit a client as the user before `hmz daemon connect
--stdio` relays it to that socket (Section 3.5.1 of [WIRE]). Over a listener, a client is admitted
only by mutual TLS or pinned WebRTC, and only a paired device can call more than `session.hello`,
`pair.claim` and `rpc.discover` (Section 3.9 of this document, Section 4.4 of [WIRE], Section 4.5.10
of [WIRE] and Section 4.7 of [WIRE]). A daemon listens beyond its socket only where `listen` or `hmz
daemon serve` asks it to (Section 3.9.1).

What a client can do. Every paired session but Ai-chan's is whole (Section 3.6.1, Section 3.9.7 and
Section 4.21): it is able to start, steer, stop and force epics, to take over a role another
frontend claims, to close a host, to read and write the settings, accounts, runtimes and flows of
the daemon's machine, to list any directory the daemon's user can read, to import an archive from
any path, to make pairing codes and to revoke other devices (Section 3.6.5, Section 4.8, Section
4.14, Section 4.16.6, Section 4.17.7 and Section 4.18). Pairing a device is therefore equivalent to
giving it the daemon's user's account on that machine. The name a frontend gives in `session.hello`
is taken as given and is not verified (Section 4.7.1.5); the device name of a paired session is the
one it claimed under (Section 4.14.2).

Environments. A paired session reads and writes the files of every environment of every epic its
daemon holds, and works their git repositories, as the daemon's user (Section 4.24.3 and Section
4.24.5). A terminal is a shell on the env machine; a session over an untrusted carrier opens one, or
types into one, only where the setting `envs.paired_terminals` of the daemon's machine is on
(Section 4.24.4.10). Every change a frontend makes to an environment, and every terminal it opens,
is written in the epic's history with the frontend's name; what a terminal is told and prints never
is (Section 4.24.1.8).

Answers and faces. An answer to a question with a schema is taken only where the host finds it fits
that schema, whichever frontend or face gave it (Section 4.8.4.3). A face is HTML the flow made;
`epic.face` hands it over as text and the daemon runs none of it (Section 4.8.10).

Secrets. The daemon answers no value of an account's variables, no EasyTier secret, no TURN
credential and no credential of a URL (Section 4.18.1.1, Section 4.18.1.7, Section 4.18.2.2, Section
4.18.5.5 and Section 4.16.8.3). A pairing code's token lives in the daemon's memory alone (Section
4.5.6 of [WIRE]).

What a client trusts. A client on this machine reads a daemon as present only where the daemon
record names an existing process and the socket accepts a connection, never on the strength of the
socket file alone (Section 4.4.1 and Section 4.4.3). A client pins a remote daemon's id and fails a
daemon that answers with another (Section 3.8.2.7). Limits on frames and on queued notifications
keep one slow or misbehaving peer from holding up an epic or another frontend (Section 4.11 and
Section 6.10 of [WIRE]).

Version mismatch. A client that finds a daemon of another major version starts no daemon beside it
and reports the refusal of Section 3.7.5 (Section 3.7.4 and Section 4.12.3). Installing another
release does not stop a daemon or its epics (Section 3.7.2).

Remote daemons. A `stdio:ssh` route is carried by `ssh` with the user's own keys and ssh config, in
batch mode, and never asks for a password or the acceptance of a host key (Section 3.8.2.6 and
Section 3.4.3 of [WIRE]). Reaching an SSH daemon can install hmz, and uv, on the remote machine
(Section 3.8.3.2), and does not replace an hmz there whose daemon holds running epics (Section
3.8.3.3). An EasyTier network is derived from a secret of at least 16 bytes that does not leave the
machine it is set on and is not passed on any command line (Section 3.8.5.1 and Section 3.8.5.2);
EasyTier runs without root and without a virtual network device (Section 3.8.5.5), and the binary
hmz downloads is checked against a pinned SHA-256 unless `HUMANIZE_EASYTIER` names another binary
(Section 3.8.5.6). Whoever holds the secret reaches the daemon's port over the network, but is still
held to mutual TLS and pairing there (Section 3.8.5.3).

Services. `hmz daemon install` makes the daemon run at login and keeps it running, with every
listener `listen` names, until `hmz daemon uninstall` (Section 3.9.6).

Ai-chan. The one session of an Ai-chan conversation is not whole: it comes over a scoped link of its
own, and every call of it is held to the conversation's reach before it is carried out -- what lies
outside its scope, every write under `read-only`, pairing, devices, the methods that carry
credentials or EasyTier secrets, and every Ai-chan conversation are refused, and lists are cut to
the scope (Section 4.21 and Section 4.22.6). No other session can say it is Ai-chan, and Ai-chan's
session cannot say it is another (Section 4.22.6.2). What Ai-chan does to an epic is seen by every
frontend under her name (Section 4.22.1.3). A conversation of the scope `daemon` under
`danger-full-access` reaches what a paired device reaches. `hosts.env.exec` and `hosts.env.write`
run commands and write files in an epic's envs as its flow would, and are writes (Section 4.23).

## 6. References

### 6.1. Normative References

- **[RFC2119]** Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels", BCP 14, RFC
  2119, March 1997, <https://www.rfc-editor.org/info/rfc2119>.
- **[RFC8174]** Leiba, B., "Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words", BCP 14, RFC
  8174, May 2017, <https://www.rfc-editor.org/info/rfc8174>.
- **[RFC4648]** Josefsson, S., "The Base16, Base32, and Base64 Data Encodings", RFC 4648, October
  2006, <https://www.rfc-editor.org/info/rfc4648>.
- **[CORE]** "The Humanize Protocol: Core Concepts and Functional Behaviour", [`core.md`](core.md).
- **[CLI]** "The Humanize Protocol: Command-Line Interface", [`cli.md`](cli.md).
- **[TUI]** "The Humanize Protocol: Terminal Interface", [`tui.md`](tui.md).
- **[WIRE]** "The Humanize Protocol: Carriers, Sessions and RPC", [`wire.md`](wire.md).
- **[OPENRPC]** "The Humanize Protocol: OpenRPC Document", [`openrpc.json`](openrpc.json).
- **[WEB]** "The Humanize Protocol: Web Interface", [`web.md`](web.md).
- **[PYTHON]** "The Humanize Protocol: Python Interfaces", [`python.md`](python.md).
- **[FILES]** "The Humanize Protocol: Settings, Environment Variables and Files", [`files.md`](files.md).

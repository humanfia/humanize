# Remote execution

`hmz internal anchor` runs a coding agent on this machine whose work lands on another one. The agent
needs no plugin, no configuration and no cooperation: it is told none of this and takes part in
none of it.

## The model

Two questions, answered separately. **How** a turn is reached — supervised, or the CLI the
target already has — is the first, and there are two arrangements of it; which one a session
uses is a setting rather than a fact about the target. **Where the harness runs** is the
second, and is [below](#where-the-harness-runs): the supervisor and the agent process can be
put on the machine the work lands on, or on a third machine again.

Everything that is not marked otherwise is about the first arrangement, with the harness here.

An agent runs on this machine, unchanged. Everything it *does* — reading and writing project
files, running commands, reaching the network from those commands — happens on the target.

The workspace the agent works in is a **local mirror** of the target's copy. It reads and writes
the mirror at local speed; humanize keeps the two in step. The mirror lives at the workspace's
own path by default, so the paths the agent sees are the target's own.

```
     this machine                              the target
┌────────────────────┐                   ┌────────────────────┐
│  claude / codex …  │                   │                    │
│        ↓ syscalls  │                   │  hmz internal      │
│  ┌──────────────┐  │   one channel     │    anchor serve    │
│  │  supervisor  │──┼──────────────────▶│         ↓          │
│  └──────────────┘  │  ssh / docker /   │  files, processes, │
│   local mirror     │  tcp / a pipe     │  the network       │
└────────────────────┘                   └────────────────────┘
     credentials,                             the work
   the model provider
```

### The other arrangement: `--native`

The CLI already installed **on the target** is the one that runs, and it runs there. Nothing is
mirrored, nothing is traced, and nothing of humanize is below the agent: this side starts it on
the target in the target's own copy of the workspace, carries its three streams byte for byte,
sends it the signals aimed here, and exits with its own status.

```
     this machine                              the target
┌────────────────────┐                   ┌────────────────────┐
│  hmz internal      │   one channel     │  claude / codex …  │
│    anchor --native │──────────────────▶│         ↕          │
│    ↕ three streams │  ssh / docker /   │  files, processes, │
│                    │  tcp / a pipe     │  the network       │
└────────────────────┘                   └────────────────────┘
    the flow driving                       the work, and
      the turn                            the account too
```

Which makes running a turn elsewhere an argument change for every backend that already speaks a
framed protocol to a process humanize spawns — the frames cross a machine boundary and neither
end is told.

```sh
hmz internal anchor --native --target docker://build-container --remote-path /srv/project claude
```

Three things do not follow the CLI across on their own, so the anchor carries each:

- **The account.** What a provider sets is sent as the turn's environment; what it *hushes* is
  taken off on the target with `--hush`, where the environment is composed. A variable merely
  left out of what is sent survives in the target's own shell profile.
- **Its credential files.** `--project NAME=DIR` writes them into a directory on the target that
  only the target's user may enter, names them to the CLI by the variable that moves the
  directory they belong in, and removes them when the turn is over. **The account leaves this
  machine**, which is the trade this arrangement is: a machine that should not be trusted with
  it is a machine to reach the other way. A credential the CLI reads out of `~/…` is the one
  that does not cross — nothing but `HOME` points a CLI at one, and a replaced home takes the
  target's git identity, its ssh keys and the CLI's own transcripts with it. An account kept
  *only* there is refused rather than quietly run as the target's own.
- **The skills the flow carries.** `--carry DIR=PATH` puts them in the target's copy of the
  workspace for the length of the turn. Nothing already there is written over, and only what
  was made is removed.

And one thing cannot: a flow's own [callbacks](/weaver/tools). The bridge carrying them is a
program on this machine speaking to a socket in this process, so a turn offering them to a CLI
on another machine is refused rather than taken without them. A `local` target is the exception,
the CLI there being here.

Two more things follow from there being no supervisor. **The agent's own connections are the
target's** — there is no `--net` here, so a provider pointed at `127.0.0.1` is a turn dialling
the *target's* loopback; a gateway a native turn is to use has to be reachable under a name the
target resolves. And **everything crosses every turn**: each turn is a process of its own, so
the credentials and the skills are written again each time.

## Where the harness runs

The **harness** is the agent process and the supervisor tracing it. By default it is here and
the work is over there, which is every diagram above. `--harness` moves it, and there are
three answers.

| `--harness` | |
| --- | --- |
| `local` *(default)* | Here. The agent's credentials, its state directory and its link to its model provider stay on this machine, and every path it names is a round trip to the target. |
| `same` | On whichever machine `--target` names. The supervisor is beside its work: a file the agent opens is that machine's disk rather than a wire, and what crosses to here is the agent's three streams and nothing else. |
| a target spelling | On a machine of its own, with the work landing on another. humanize is on neither and introduces the two. |

```
     this machine                 the harness              the work
┌────────────────────┐      ┌────────────────────┐   ┌──────────────────┐
│  hmz internal      │ ssh/ │  claude / codex …  │   │  hmz internal    │
│    anchor          │─────▶│        ↓ syscalls  │   │    anchor serve  │
│    ↕ three streams │docker│  ┌──────────────┐  │   │        ↓         │
│                    │      │  │  supervisor  │──┼──▶│ files, processes │
│  ┌──────────────┐  │      │  └──────────────┘  │ ▲ │  the network     │
│  │  rendezvous  │◀─┼──────┼── local mirror ────┼─┘ └──────────────────┘
│  └──────────────┘  │      └────────────────────┘
└────────────────────┘        introduced here, then out of the way
```

### Being introduced

Two machines humanize started are not two machines that can reach each other. So humanize holds
a **rendezvous**: a ticket names one meeting, each half dials the broker with it, and three
things are tried in order.

1. **Each half is told what it looks like from outside.** The address a connection arrives from
   is the one the world has for whoever opened it, which is the one thing a machine behind a NAT
   cannot learn by asking itself. That is what a STUN server does, and it is one line of JSON
   here because it is one attribute of an accepted socket.
2. **The two are started at each other at once.** Both open outward from the port they dialled
   the broker from and both listen on it. Where a NAT is address-independent — which the common
   ones are — each side's attempt opens the hole the other's arrives through, and the session
   runs machine to machine with humanize no longer in the path.
3. **And humanize carries the bytes where they cannot.** Two symmetric NATs, a firewall that
   drops what it did not see leave, no route at all: the window closes, both halves say so, and
   the connections they are *already holding to the broker* are spliced together. The fallback
   costs one message, because the relay is the socket the introduction was made over.

Which of the three a session got is not something it is told: the channel is a socket either
way and the protocol above it is the same protocol. A broker that had to carry a pair remembers
it, so the next session between those two machines is carried without spending the window again
— and disbelieves itself every sixteenth time, because a firewall rule is the kind of thing that
changes.

`--broker HOST` says where the halves should dial, for a machine they reach humanize by some
other name at; by default humanize offers whichever of its own addresses faces outward. A broker
can also be run on its own with
[`hmz internal anchor rendezvous`](/reference/cli#hmz-internal-anchor-rendezvous).

### What moving it costs and buys

- **A turn stops paying per syscall.** Under `local`, every path the agent names crosses a
  link. Beside its work, none of them do.
- **The account moves with the harness.** Under `local` the credentials, the state directory
  and the connection to the model provider are here, which is what the supervised arrangement is
  built to keep. A harness elsewhere is a harness holding them there — the same trade `--native`
  makes, and the same answer: **a machine that should not be trusted with the account is a
  machine to reach with the harness here.**
- **The mirror is kept between turns.** A harness elsewhere that was given no `--shadow` works
  in one under that machine's own cache, named for what it mirrors rather than for the turn, so
  the second turn against a workspace starts with its files already there.
- **`anchor:afar` is what it answers to.** A flow that must not have the agent's own process
  sent away can [ask](/features/capabilities), and be refused before anything starts.

## Quick start

```sh
hmz internal anchor --target ssh://build-box claude
hmz internal anchor --target ssh://gpu-01 codex exec "run the test suite"
```

Everything after the agent's name is the agent's own. Before running anything, ask the target
what it is:

```console
$ hmz internal anchor --check --target ssh://build-box
target      ssh://build-box
hostname    build-box
python      3.12.3 (pid 41207)
export      /home/me/code/myproject -> /home/me/code/myproject
workspace   /home/me/code/myproject (184 entries)
```

Every flag is in the [CLI reference](/reference/cli#hmz-internal-anchor).

## Targets

| `--target` | |
| --- | --- |
| `ssh://HOST` or `ssh://HOST:PORT` | Bootstraps the target half over ssh and speaks to it on that connection's pipes. Uses your ssh config, agent and keys. |
| `docker://CONTAINER` | Runs the target half inside a running container over `docker exec`, as whoever that container runs as. No port and no secret. |
| `tcp://HOST:PORT` | Connects to a target [left listening](#serving-a-target). Cheap to reconnect, which matters for a loop of short turns. |
| `peer://TICKET@HOST:PORT` | Meets a serving half at a rendezvous rather than dialling it. humanize writes this one for a harness it has placed on another machine; it is not a spelling to type. |
| `local` or `local:DIR` | Another directory on this machine, standing in for a remote one. Used for testing, and by the container machines. |

The target half is a zipapp humanize ships to the target and caches there by digest. It needs no
installation, and the two halves refuse to run against each other if their versions disagree.

## What the agent observes

Inside the workspace it sees the target: the same file names, contents, sizes, modes and
timestamps, at the same paths. A failure answers with the target's own error, not a local
approximation of it.

Where the target spells a path more than one way, every spelling reaches the same file. A Mac
reaches `/tmp`, `/var` and `/etc` through `/private`, and ignores case unless it was formatted
not to, so a path a command there hands back — `pwd` in a temporary directory answers
`/private/var/folders/...` — is understood as the workspace path it names. A path outside the
workspace is left exactly as the agent named it: it belongs to this machine, and one that is
not here is reported missing rather than claimed for the target.

Every program it spawns behaves like an ordinary local child — the same descriptors, the same
output, the same exit status — and its parent is released as soon as it starts, so commands run
concurrently and a long-lived one can be talked to while it runs.

Signals travel both ways: one aimed at a running command reaches the real process on the target,
and a command killed there kills its local counterpart the same way.

A command never reports a success it did not achieve: one that cannot be started, or that
humanize loses track of, fails visibly. What a command changes on the target becomes visible to
the agent once it exits, and when the session ends nothing it started is left running.

## What reaches the target

- **File contents.** A file the agent modifies is pushed in full before any command runs on the
  target, and again when the session ends.
- **Structural changes.** Creating, removing, renaming, linking and changing permissions are
  replayed on the target first, so the target's error is what the agent sees.
- **Commands.** Everything the agent spawns, including bundled work helpers such as ripgrep, in
  the target's copy of the working directory.
- **Network.** Whatever those commands reach.

However the agent spells the path. Most of these CLIs write a file the atomic way — open the
directory, create a temporary beneath it, rename it over the real name — and several of them,
Claude Code among them, name "beneath it" as `/proc/self/fd/<n>/name`, through a descriptor
they already hold, rather than as a path under the workspace. The kernel reaches the same file
either way, and so does humanize: those names are followed back to the file before anything is
matched, mirrored or replayed. The same goes for `/proc/<pid>/fd/<n>`, and for `/proc/self/cwd`,
`/proc/self/root` and `/proc/self/exe` — the last of which is how a runtime re-execs itself. A
link that cannot be read back fails the call rather than passing through it, because a path
nobody can resolve is a path nobody can place.

## What stays on this machine

- The agent's own runtime executables and re-execs. For any CLI installed by npm that includes
  the interpreter its `#!/usr/bin/env` line names, at every path on `PATH` the search for it may
  reach; for Codex, the native CLI and its code-mode host besides.
- Its state directory, and anything the agent runs from inside it — Grok Build keeps its native
  binary
  under `~/.grok/bin` and re-execs it. All twelve known CLIs are known by name — `agy`, `claude`,
  `codex`, `cursor-agent`, `dsh`, `grok`, `kimi`, `mimo`, `opencode`, `pi`, `qwen`, `zcode` — as is
  humanize's own `~/.humanize`; any other agent keeping state inside the workspace has to be
  named with `--local-path`.
- Anything named as a local path (`--local-path`) or a local program (`--local-exec`).
- The agent's own network connections, so that it can still reach its model provider. `--net
  remote` sends them to the target instead, and `--net-allow HOST[:PORT]` keeps named hosts
  local anyway.

Commands the agent spawns always use the target's network, whatever `--net` says.

## Anchoring a flow

Give an agent's config an anchored [machine](/reference/machines) and its turns land there, without any
other change to the [flow](/reference/flows):

```python
from hmz.coganchor.agents import ClaudeCodeAgentConfig
from hmz.coganchor import AnchorConfig
from hmz.coganchor.machines import AnchoredConfig

config = ClaudeCodeAgentConfig(
    model="claude-opus-4-8",
    effort="high",
    machine=AnchoredConfig(
        anchor=AnchorConfig(target="ssh://build-box", workspace="/srv/project")
    ),
)
```

Every option of `hmz internal anchor` is a field of `AnchorConfig` and every field is an option,
so the two spellings mean exactly the same thing — a flow spawns what an operator would have typed.
Settings no session could run under are refused where they are *written* rather than where they
are used, so a flow that misspells a target hears about it as it configures its agents, not
hours into the loop.

**How often the target is reached depends on the backend.** A turn that runs as its own process
is anchored on its own, so a loop of short turns reaches the target once per turn — a `tcp://`
target makes that a socket rather than an ssh session to bootstrap. A backend that holds one
process across turns is anchored once for the agent instead.

There is a trade-off worth knowing: an anchored **Claude** ends its process with each turn, so
the turn's work reaches the target before the turn says it landed — at the cost of not being
able to hear you *during* a turn. An anchored **Codex** keeps one app server for the life of the
agent and can be steered throughout, at the cost of that guarantee: its work reaches the target
whenever a command runs there, which for a coding agent is constantly, rather than at the end of
every turn.

## Serving a target

Instead of bootstrapping over ssh each time, a target can be left listening:

```sh
# on the target
hmz internal anchor serve --listen 0.0.0.0:7777 --export /srv/project --token "$SECRET"

# on this machine
HUMANIZE_TOKEN=$SECRET hmz internal anchor --target tcp://build-box:7777 --workspace /srv/project claude
```

`--export VIRTUAL[:REAL]` says which directory to expose, and under what path the agent believes
it is using. Repeat it for more than one.

Listening on anything but loopback **without** `--token` is refused. Read
[Security](#security) before opening one.

The same program serves both ends — the bundle shipped to a target runs `hmz internal anchor serve
--stdio`, which is one session over a pipe, or `--peer TICKET@HOST:PORT`, which is one session
to whoever is met at that [rendezvous](#being-introduced).

The archive is built once per source tree and cached on each target by its digest, and one
`ssh` to a host is reused by every command after it, so a second turn against a machine pays
for none of the bootstrapping the first one did.

## From Python

```python
from hmz.coganchor import AnchorConfig, check, connect

config = AnchorConfig(target="ssh://build-box", workspace="/srv/project")

found = check(config)              # what the target says about itself; runs nothing there
status = connect(["claude", "--print"], config)   # the agent's own exit status
```

`connect` returns once the agent has exited and everything it wrote has been pushed.

`AnchorConfig` fields map one-to-one onto the flags in the
[CLI reference](/reference/cli#hmz-internal-anchor): `target`, `harness`, `broker`, `workspace`,
`chdir`, `remote_path`, `shadow`, `local_paths`, `local_execs`, `redirects`, `private`, `net`,
`net_allow`, `token`, `force`.

```python
# the harness beside its work, so a file the agent opens is that machine's disk
AnchorConfig(harness="same", target="ssh://build-box", workspace="/srv/project")

# the harness on one machine, its work on another, introduced through humanize
AnchorConfig(harness="ssh://runner", target="ssh://build-box", workspace="/srv/project")
```

## Requirements

**Running an agent** needs Linux on x86-64 or aarch64 and a recent Python. Any other
architecture is refused at start-up, and told where it can run instead. That is a requirement
of whichever machine the harness runs on, so `--harness` moves it too: this machine needs none
of it to place a harness somewhere that has it.

**Serving** needs only a POSIX system with a Python of the same vintage — no root, no compiler,
no kernel module, nothing installed.

## What is not guaranteed

Each of these is deliberate, and each looks like a defect if you meet it cold.

- **Serving is not a sandbox.** An export bounds which files a request may name. It does not
  confine the commands that request can run, and it does not stop a symlink pointing out of the
  tree from being followed. A listening port is equivalent to a shell on that machine.
- **Mirrored directories are the mirror's, not the target's.** A directory in the mirror carries
  this machine's permissions and the time the mirror was made.
- **Only file contents are pushed.** A permission change made through an already-open descriptor
  never reaches the target, and ownership, device nodes and extended attributes never leave the
  mirror.
- **A request that goes unanswered is abandoned here, not there.** It may still take effect on
  the target after the agent has been told it failed.
- **Losing the connection does not stop the agent.** Work needing the target fails,
  already-mirrored files still read, and the agent exits with its own status.
- **Only the common signals are reproduced faithfully.** A repeat of a signal already delivered,
  and the rarer signals, do not reach the command.
- **The mirror is authoritative.** Anything in it the target does not have is deleted. humanize
  refuses a mirror directory holding unrelated files, or one last used against a different
  target, unless `--force` says otherwise. When what it is deleting was written here and never
  carried across, it says so out loud, so a turn that failed to deliver does not look like one
  that succeeded — but it is still deleted.
- **A path is settled by its characters.** `.` and `..` are collapsed as text, so an ordinary
  symlink in the middle of a name is not walked; only `/proc`'s own links, which are how the
  CLIs name a file through a descriptor, are followed. A path is also read at the moment the
  call is stopped, so a descriptor another thread replaces in between is resolved as it was.

## Limits

- **Whole files.** A file crosses in full, in both directions.
- **One writer.** The target's workspace must not be edited by anyone else at the same time.
- **No privilege escalation.** `sudo` does not work below the agent on this machine. Commands
  run on the target, where it is unaffected.
- **No crossing.** Renaming or linking between the workspace and a path kept on this machine
  fails.
- **64-bit only.** A 32-bit process below the agent is not intercepted and runs against the
  mirror with nothing replayed.
- **Names resolve here** and are dialled from the target, so split-horizon DNS can disagree.
- **A rendezvous is IPv4.** A hole is punched from one port to one address, and a candidate the
  other half cannot open a matching socket for only spends the window. A machine reachable only
  over IPv6 is carried, which is the answer this already has for every unreachable pair.
- **A relayed session pays this machine's bandwidth and latency for every byte.** Nothing warns
  you: neither end of a connection can honestly say whether it is being relayed.

## Security

**An `hmz internal anchor` port is equivalent to a shell on that machine.** Give `--token` a
real secret, and prefer `ssh://` or `docker://`, which need no open port at all.

**A rendezvous port is not.** Placing a harness on a machine other than the one its work lands
on opens one here, on every interface, for as long as the run lasts. Nothing on the other side
of it is a shell: what it offers is to be paired with whoever presents the same ticket, and a
ticket is a 128-bit secret humanize mints per session and tells exactly two machines. A
stranger who dials it can be introduced to nobody but themselves. `HUMANIZE_RENDEZVOUS_PORT`
pins the port for a firewall that has to be told one in advance.

**A harness elsewhere holds the account.** The supervised arrangement keeps the credentials,
the state directory and the model provider connection on this machine; `--harness` moves all
three to wherever it sends the harness. That is the same trade `--native` makes, and it has the
same answer: a machine you would not trust with the account is a machine to reach with the
harness here.

The full statement, including what running any agent under humanize means, is in
[Security](/user/security).

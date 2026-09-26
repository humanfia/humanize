# Remote execution

`hmz internal anchor` runs a coding agent whose work lands on another machine. The agent needs
no plugin and no configuration, and is told none of this.

Every turn whose work lands elsewhere is spawned as this line. A flow gets there through its
[environments](#anchoring-a-flow), an agent config through [`machine=`](/reference/machines),
and you can type it yourself. Every flag is in the
[CLI reference](/reference/cli#hmz-internal-anchor).

## Quick start

Ask the target what it is, without running anything there:

```console
$ hmz internal anchor --check --target ssh://build-box
target      ssh://build-box
hostname    build-box
python      3.12.3 (pid 41207)
export      /home/me/code/myproject -> /home/me/code/myproject
workspace   /home/me/code/myproject (184 entries)
```

Then run an agent against it. Everything after the agent's name is the agent's own:

```sh
hmz internal anchor --target ssh://build-box claude
hmz internal anchor --target ssh://gpu-01 codex exec "run the tests"
```

## Anchoring a flow

A [flow](/reference/flows) is anchored by its environments, not its agents. Point an
environment role at a host with ssh:

```sh
hmz exec -f mine -a coder=claude/claude-opus-5:high \
    -e repo=ssh@build-box/srv/project -b cost=20 "fix the build"
```

Every session the flow spawns in `repo` is anchored at `ssh://build-box` with the workspace
`/srv/project`, and the flow's own `await repo.exec([...])` runs there too. See
[Machines › Where a flow's agents work](/reference/machines#where-a-flow-s-agents-work).

**How often the target is reached depends on the backend.** A backend that runs a process per
turn is anchored once per turn; a `tcp://` target makes that a socket rather than an ssh
bootstrap. A backend that holds one process across turns is anchored once for the agent.

| Anchored | Work reaches the target | Can be steered |
| --- | --- | --- |
| **Claude** | before the turn says it is done: its process ends with every turn | during a turn, not between turns: there is no process to hear you |
| **Codex** | whenever a command runs there, which is constantly, and when the session ends | throughout: one app server for the life of the agent |

## The arrangements

Two settings decide how a turn is reached: `native`, and `harness`.

| Arrangement | The agent, its CLI, the mirror and the account | What crosses the link | Capabilities |
| --- | --- | --- | --- |
| **Supervised** *(default)* | here, under a supervisor | every path the agent names, a round trip each | `anchor:supervised` |
| [`harness="same"`](#where-the-harness-runs) | on the target. The mirror is kept between turns. | the agent's three streams | `anchor:supervised`, `anchor:afar` |
| [`harness=<target>`](#where-the-harness-runs) | on a third machine. The mirror is kept between turns, and a [rendezvous](#being-introduced) port opens here. | three streams to here; file work between the other two | `anchor:supervised`, `anchor:afar` |
| [`native=True`](#native-the-target-s-own-cli) | on the target, as its own CLI, with no supervisor and no mirror. The account is sent there. | three streams, signals and the exit status | `anchor:native-cli` |

`native` and a `harness` on another machine ask for opposite things, and are refused together.

## Targets

| `--target` | Reached by | Needs |
| --- | --- | --- |
| `ssh://[USER@]HOST[:PORT]` | Ships the target half over ssh and speaks to it on that connection's pipes. Uses your ssh config, agent and keys. | ssh access, Python ≥ 3.12 there |
| `docker://CONTAINER` | Runs the target half in a running container over `docker exec -i`, as whoever the container runs as. | `docker` here, Python ≥ 3.12 in the container |
| `tcp://HOST:PORT` | Dials a target [left listening](#serving-a-target). Cheap to reconnect. | a served target, and its `--token` |
| `peer://TICKET@HOST:PORT` | Meets a serving half at a [rendezvous](#being-introduced). humanize writes this one for a harness it places; you do not type it. | — |
| `local` or `local:DIR` | Another directory on this machine standing in for a remote one. Used by tests, and by a harness placed beside its work, which reaches the work this way. | — |

The target half is a zipapp humanize builds once per source tree and caches on the target by
its digest: under `$HOME/.cache/humanize` over ssh, and `/tmp/humanize` in a container. Nothing
is installed. It is started with the first Python ≥ 3.12 it finds: `python3`, then
`python3.14` down to `python3.12`, then well-known install paths. The two halves refuse each
other if their protocol versions differ.

One `ssh` connection to a host is shared by the commands after it, and stays open for 120
seconds after the last one. Set `HUMANIZE_SSH_REUSE=0` for an sshd that refuses multiplexing.

## `AnchorConfig`

Every option of `hmz internal anchor` is a field of `AnchorConfig`, and every field is an
option, so the two spellings mean the same thing:

::: code-group

```sh [hmz internal anchor]
hmz internal anchor --target ssh://build-box --workspace /srv/project \
    --net remote --net-allow api.anthropic.com claude
```

```python [AnchorConfig]
from hmz.coganchor import AnchorConfig, connect

config = AnchorConfig(
    target="ssh://build-box",
    workspace="/srv/project",
    net="remote",
    net_allow=("api.anthropic.com",),
)
connect(["claude"], config)
```

:::

| Field | Flag | Default | |
| --- | --- | --- | --- |
| `target` | `--target URL` | `"local"` | Where the work lands. See [Targets](#targets). |
| `harness` | `--harness WHERE` | `"local"` | Where the agent process and its supervisor run: `local`, `same`, or an `ssh://` or `docker://` target. See [Where the harness runs](#where-the-harness-runs). |
| `broker` | `--broker HOST` | `""` | The address two halves dial to be introduced. Empty means `$HUMANIZE_RENDEZVOUS`, else this machine's outward-facing address. |
| `workspace` | `--workspace PATH` | `None` | The project directory as the target has it. `None` is the current directory. |
| `chdir` | `--chdir PATH` | `None` | Where inside the workspace the agent starts, as the target names it. `None` is the workspace. |
| `remote_path` | `--remote-path PATH` | `None` | Where the workspace really lives on the target, if not at `workspace`. |
| `shadow` | `--shadow PATH` | `None` | The mirror, on the harness's machine. `None` is `workspace`, so the agent sees the target's own paths. |
| `local_paths` | `--local-path PATH`, repeated | `()` | Paths kept here even inside the workspace. |
| `local_execs` | `--local-exec PATH`, repeated | `()` | Programs under these paths run here, not on the target. |
| `private` | `--private NAME`, repeated | `()` | Variables of the agent's own kept out of what its commands run with on the target. |
| `redirects` | `--redirect FROM=TO`, repeated | `()` | Paths answered with others, kept here. A directory covers everything inside it. How a [provider](/reference/providers)'s credentials are answered. |
| `net` | `--net {local,remote}` | `"local"` | Where the agent's *own* connections go. Commands it spawns always use the target's network. |
| `net_allow` | `--net-allow HOST[:PORT]`, repeated | `()` | With `net="remote"`, hosts kept local anyway. |
| `token` | `--token TOKEN` | `None` | The secret a `tcp://` target expects. |
| `force` | `--force` | `False` | Use a mirror that holds unrelated files, or was last used against another target. |
| `native` | `--native` | `False` | Run the CLI already on the target. See [`native`](#native-the-target-s-own-cli). |
| `hushes` | `--hush NAME`, repeated | `()` | With `native`: variables the CLI runs without on the target. |
| `projects` | `--project NAME=DIR`, repeated | `()` | With `native`: credential directories put on the target for the turn, with `NAME` set to where each landed. |
| `carries` | `--carry DIR=PATH`, repeated | `()` | With `native`: directories put in the target's workspace at `PATH` for the turn. |
| `installs` | `--installs LINE` | `""` | With `native`: the install line to show when the target has no CLI. |

`--check` and `--log-level` belong to the command line only. On the command line, `--target`,
`--harness`, `--shadow`, `--token` and `--log-level` default to `$HUMANIZE_TARGET`,
`$HUMANIZE_HARNESS`, `$HUMANIZE_SHADOW`, `$HUMANIZE_TOKEN` and `$HUMANIZE_LOG`. A spawned turn
is that command line, so it reads them too. `check()` and `connect()` called in your own
process do not: pass `token` and `shadow` there yourself.

A setting no session could run under is refused where it is **written**, so a misspelled target
fails as the agent is configured, not hours into a loop. On the command line it exits `2`.

| Refused | Because |
| --- | --- |
| A target that cannot be read | It must be one of the five spellings above. |
| `native` with a `harness` on another machine | The CLI on the target is what runs; there is no harness to place. |
| A `peer://` target with any `harness` but `local` | humanize books that meeting itself. |
| `net` other than `local` or `remote` | |
| A redirect that is not two absolute paths | |
| A hush that is empty or holds `=` | |
| A projection that is not `NAME` and an absolute path | |
| A carry whose source is not absolute, or whose `PATH` is absolute or holds `..` | What is carried goes inside the workspace. |

One is not caught until the first turn: a `harness` on a `tcp://` or `peer://` machine, or
`same` with such a target. Nothing can be started on the far side of either, so the turn fails
there.

## Supervised: the default

The agent runs here, unchanged. Everything it *does* happens on the target: reading and writing
project files, running commands, and reaching the network from those commands.

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

The agent works in a **local mirror** of the target's workspace and reads and writes it at
local speed; humanize keeps the two in step. The mirror sits at the workspace's own path by
default, so the paths the agent sees are the target's.

The supervisor is a seccomp-filtered ptrace tracer. It stops only syscalls that name a path,
start a program or open a connection: 34 on x86-64, and 20 on aarch64, which has only the `*at`
forms. `read`, `write`, `mmap`, `futex` and the rest run at native speed.

### What the agent observes

Inside the workspace it sees the target: the same names, contents, sizes, modes and timestamps
at the same paths. A failure answers with the target's own error, not a local imitation.

Where the target spells a path more than one way, every spelling reaches the same file. A Mac
reaches `/tmp`, `/var` and `/etc` through `/private`, and ignores case unless formatted not to,
so `/private/var/folders/...` from `pwd` is read as the workspace path it names. A path outside
the workspace is left as named: it belongs to this machine, and one that is not here is
reported missing.

Every program the agent spawns behaves like an ordinary local child: the same descriptors, the
same output, the same exit status. Its parent is released as soon as it starts, so commands run
concurrently and a long-lived one can be talked to while it runs. Signals travel both ways.

A command never reports a success it did not achieve. One that cannot be started, or that
humanize loses track of, fails visibly. What a command changes on the target is visible to the
agent once it exits, and nothing it started is left running when the session ends.

### What reaches the target

| | |
| --- | --- |
| **File contents** | A file the agent modifies is pushed in full before any command runs on the target, and again when the session ends. |
| **Structural changes** | Creating, removing, renaming, linking and changing modes are replayed on the target first, so the target's error is what the agent sees. |
| **Commands** | Everything the agent spawns, bundled work helpers such as ripgrep included, in the target's copy of the working directory. |
| **Network** | Whatever those commands reach. |

However the agent spells the path. Several CLIs, Claude Code among them, write a file by
creating a temporary under `/proc/self/fd/<n>/` and renaming it over the real name. Those
names, `/proc/<pid>/fd/<n>`, and `/proc/self/cwd`, `/proc/self/root` and `/proc/self/exe` are
followed back to the file before anything is matched, mirrored or replayed. A link that cannot
be read back fails the call.

### What stays on this machine

- **The agent's own programs.** The CLI, the interpreter its `#!` line names at every `PATH`
  entry the search may reach, and for Codex its native binary and code-mode host.
- **Its state directory**, and anything it runs from there, such as Grok Build's native binary
  under `~/.grok/bin`. All twelve CLIs are known by name: `agy`, `claude`, `codex`,
  `cursor-agent`, `dsh`, `grok`, `kimi`, `mimo`, `opencode`, `pi`, `qwen`, `zcode`. So are
  `~/.humanize`, `~/.cache/humanize` and `~/.config/humanize`. Any other agent keeping state
  inside the workspace must be named with `--local-path`.
- **Anything named** with `--local-path` or `--local-exec`, and every `--redirect` answer.
- **The agent's own network connections**, so it can still reach its model provider.
  `--net remote` sends them to the target instead, and `--net-allow HOST[:PORT]` keeps named
  hosts local anyway.
- **Variables named `--private`**, which the agent has and its commands on the target do not.

## `native`: the target's own CLI {#native-the-target-s-own-cli}

The CLI installed **on the target** runs there. Nothing is mirrored, nothing is traced, and
nothing of humanize sits below the agent. This side starts it in the target's copy of the
workspace, carries its three streams byte for byte, forwards the signals aimed here, and exits
with its status.

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

```sh
hmz internal anchor --native --target docker://build-container \
    --remote-path /srv/project claude
```

Any backend that already speaks a framed protocol to a process humanize spawns can run a turn
elsewhere this way, with only an argument changed.

Three things do not follow the CLI on their own, so the anchor carries each, every turn:

| | How it crosses |
| --- | --- |
| **The account's variables** | Sent as the turn's environment. What the provider [takes away](/reference/providers#variables-taken-away) is removed on the target with `--hush`, where the environment is put together: a variable merely left out would survive from the target's shell profile. |
| **Its credential files** | `--project NAME=DIR` writes them, through the command's stdin and never its argv, into a directory only the target's user can enter. `NAME` is set to where they landed, and they are removed when the turn ends. |
| **The flow's skills** | `--carry DIR=PATH` puts them in the target's workspace for the turn. Nothing already there is overwritten, and only what was made is removed. |

Which credential files can cross depends on whether a variable moves the directory they belong
in:

| Crosses, by | Stays here |
| --- | --- |
| the backend's home, for `claude` (`CLAUDE_CONFIG_DIR`), `codex` (`CODEX_HOME`), `cursor-agent` (`CURSOR_CONFIG_DIR`), `grok` (`GROK_HOME`), `kimi` (`KIMI_CODE_HOME`), `pi` (`PI_CODING_AGENT_DIR`) and `qwen` (`QWEN_HOME`) | files under the homes of `agy`, `zcode`, `opencode` and `mimo`, which humanize has no variable of the backend's own to point at |
| `$XDG_CONFIG_HOME`, for files under `config/`, such as Claude's `anthropic/` | files under your home (`~/`), such as Claude's `~/.claude.json`: only `HOME` points a CLI there, and replacing it takes the target's git identity, ssh keys and transcripts with it |

An account whose credentials all stay here, and that has no variables, is refused rather than
run as whatever account the target is signed into.

A missing CLI exits **127**, with the `--installs` line in the message.

**What cannot cross.** A flow's own [callbacks](/weaver/tools): the bridge carrying them is a
program here speaking to a socket in this process, so a native turn offering them is refused. A
`local` target is the exception, since the CLI there is here.

**The agent's connections are the target's.** There is no `--net`, so a provider pointed at
`127.0.0.1` dials the *target's* loopback. A gateway for a native turn must be reachable under
a name the target resolves.

## Where the harness runs

The **harness** is the agent process and the supervisor tracing it. `--harness` moves it:

| `--harness` | |
| --- | --- |
| `local` *(default)* | Here. Every path the agent names is a round trip to the target. |
| `same` | On whichever machine `--target` names. A file the agent opens is that machine's disk, and only the agent's three streams cross to here. |
| `ssh://…` or `docker://…` | On a machine of its own, with the work on another. humanize is on neither, and introduces the two. |

```
    this machine               the harness              the work
┌──────────────────┐      ┌────────────────────┐   ┌──────────────────┐
│ hmz internal     │ ssh/ │  claude / codex …  │   │  hmz internal    │
│   anchor         │─────▶│        ↓ syscalls  │   │    anchor serve  │
│  ↕ three streams │docker│  ┌──────────────┐  │   │        ↓         │
│                  │      │  │  supervisor  │──┼──▶│ files, processes │
│ ┌──────────────┐ │      │  └──────────────┘  │ ▲ │  the network     │
│ │  rendezvous  │◀┼──────┼── local mirror ────┼─┘ └──────────────────┘
│ └──────────────┘ │      └────────────────────┘
└──────────────────┘        introduced here, then out of the way
```

humanize ships its own bundle to the harness machine. The CLI must already be installed there.

| What moving it does | |
| --- | --- |
| **A turn stops paying per syscall** | Beside its work, no path the agent names crosses a link. |
| **The account moves with it** | The CLI's state directory and its model-provider connection are on the harness machine, and a provider is not carried there. See [Where the account lives](#where-the-account-lives). |
| **The mirror is kept between turns** | Without `--shadow`, the mirror lives under that machine's `$HOME/.cache/humanize-mirrors` (`/tmp/humanize-mirrors` in a container), named for what it mirrors, so the second turn starts with its files there. |
| **It says `anchor:afar`** | Alongside `anchor:supervised`, in the anchor's [capabilities](/reference/machines#capabilities), so a place with the harness elsewhere can be told apart without connecting. |

### Being introduced

Two machines humanize started cannot necessarily reach each other. When the harness and the
work are on different machines, humanize holds a **rendezvous**. A ticket names one meeting,
each half dials the broker with it, and three things are tried in order:

1. **Each half is told what it looks like from outside:** the address its connection arrived
   from, which a machine behind a NAT cannot learn by asking itself.
2. **The two are started at each other at once.** Both open outward from the port they dialled
   the broker from and listen on it. Through the common address-independent NATs, each side's
   attempt opens the hole the other's arrives through, and the session runs machine to machine.
   They get 4 seconds.
3. **Otherwise humanize carries the bytes.** Two symmetric NATs, or a firewall that drops what
   it did not see leave: both halves say so, and the connections they already hold to the
   broker are spliced together.

The session cannot tell which it got: the channel is a socket either way. A broker that failed
to introduce a pair three times carries their later sessions at once, and still tries the
direct route every sixteenth time.

`--broker HOST` names the address the halves should dial, for a machine they know by another
name. The broker can also run on its own, with
[`hmz internal anchor rendezvous`](/reference/cli#hmz-internal-anchor-rendezvous).

## Where the account lives

| Arrangement | Credentials, state directory, model-provider connection |
| --- | --- |
| Supervised, harness here | **here**. A provider's files never cross, and its variables are `private`. |
| `harness="same"` or elsewhere | **on the harness machine**. A provider is not carried there: its variables are not sent, and its credential paths are answered with this machine's paths, which that machine does not have. |
| `native=True` | **on the target**, for the length of each turn. A provider's variables and credential files are sent there. |

A machine you would not trust with the account is a machine to reach supervised, with the
harness here.

## Serving a target

A target can be left listening instead of bootstrapped over ssh each time:

```sh
# on the target
hmz internal anchor serve --listen 0.0.0.0:7777 \
    --export /srv/project --token "$SECRET"

# on this machine
export HUMANIZE_TOKEN=$SECRET
hmz internal anchor --target tcp://build-box:7777 \
    --workspace /srv/project claude
```

`--export VIRTUAL[:REAL]` exposes a directory, under the path the agent believes it is using.
Repeat it for more than one. A bare `--listen PORT` listens on `127.0.0.1`.

::: danger A listening port is equivalent to a shell on that machine
Listening on anything but loopback **without** `--token` is refused. Give `--token` a real
secret, or prefer `ssh://` and `docker://`, which open no port at all.
:::

The same program serves every target. A bootstrapped target runs
`hmz internal anchor serve --stdio`, one session over a pipe. A target met at a rendezvous runs
`--peer TICKET@HOST:PORT`, one session to whoever presents that ticket. See
[CLI › hmz internal anchor serve](/reference/cli#hmz-internal-anchor-serve).

## From Python

```python
from hmz.coganchor import AnchorConfig, check, connect, drive

config = AnchorConfig(target="ssh://build-box", workspace="/srv")

found = check(config)   # what the target says; runs nothing there
status = connect(["claude", "--print"], config)   # the agent's status
```

| | |
| --- | --- |
| `check(config)` | Reaches the target and returns what it says of itself: `hostname`, `python`, `pid`, `exports`, plus the `target`, the `workspace` and its number of `entries`. Raises `OSError` for a target it cannot reach or a workspace that is not there. |
| `connect(command, config)` | Runs the agent. Returns once it has exited and everything it wrote has been pushed. With `native=True` it calls `drive`. |
| `drive(command, config)` | Runs the target's own CLI and carries its streams. Returns its status, or 128 plus the signal that killed it. Raises `NotInstalled` for a CLI the target has not got. |
| `AnchorConfig.capabilities` | The `anchor:` names above, without connecting. |

Two harness placements, as settings:

```python
# the harness beside its work: a file it opens is that machine's disk
AnchorConfig(harness="same", target="ssh://build-box")

# the harness on one machine, the work on another
AnchorConfig(harness="ssh://runner", target="ssh://build-box")
```

## Requirements

| Where | Needs |
| --- | --- |
| **The harness's machine**: here, unless `harness` moves it | Linux on x86-64 or aarch64, and Python ≥ 3.12. Any other architecture is refused at start-up, with where it can run instead. Here needs none of it to place a harness somewhere that has it. |
| **The target** | A POSIX system with Python ≥ 3.12. No root, no compiler, no kernel module, nothing installed. |
| **A `native` target** | The CLI installed there. Nothing here is traced, so this machine needs no Linux. |
| **A harness elsewhere** | An `ssh://` or `docker://` machine meeting the first row, with the CLI installed. |

## What is not guaranteed

Each of these is deliberate.

- **Serving is not a sandbox.** An export bounds which files a request may name. It does not
  confine what the commands it runs can do, and a symlink pointing out of the tree is followed.
- **Mirrored directories are the mirror's.** A directory in the mirror carries this machine's
  permissions and the time the mirror was made.
- **Only file contents are pushed.** A mode change made through an already-open descriptor
  never reaches the target. Ownership, device nodes and extended attributes never leave the
  mirror.
- **A request that goes unanswered is abandoned here, not there.** It may still take effect on
  the target after the agent was told it failed.
- **Losing the connection does not stop the agent.** Work needing the target fails, mirrored
  files still read, and the agent exits with its own status.
- **Only the common signals are reproduced faithfully.** A repeat of a signal already
  delivered, and the rarer signals, do not reach the command.
- **The mirror is authoritative.** Anything in it the target does not have is deleted. humanize
  refuses a mirror holding unrelated files, or one last used against another target, unless
  `--force` says otherwise. When it deletes something written here and never carried across, it
  says so out loud, but it still deletes it.
- **A path is settled by its characters.** `.` and `..` are collapsed as text, so an ordinary
  symlink in the middle of a name is not walked; only `/proc`'s own links are followed. A path
  is read when the call stops, so a descriptor another thread replaces in between resolves as
  it was.

## Limits

- **Whole files.** A file crosses in full, in both directions.
- **One writer.** Nobody else may edit the target's workspace at the same time.
- **No privilege escalation.** `sudo` does not work below the agent here. Commands run on the
  target, where it is unaffected.
- **No crossing.** Renaming or linking between the workspace and a path kept here fails.
- **64-bit only.** A 32-bit process below the agent is not intercepted, and runs against the
  mirror with nothing replayed.
- **Names resolve here** and are dialled from the target, so split-horizon DNS can disagree.
- **A rendezvous is IPv4.** A machine reachable only over IPv6 is carried by the broker.
- **A relayed session pays this machine's bandwidth and latency for every byte**, and nothing
  says it is being relayed.

## Security

::: danger An `hmz internal anchor serve` port is a shell on that machine
Give `--token` a real secret, or use `ssh://` or `docker://`, which need no open port.
:::

::: warning A harness on a third machine opens a rendezvous port here, on every interface
It stays open for as long as this process runs. What it offers is pairing with whoever presents
the same ticket, and a ticket is a 128-bit secret minted per session and told to exactly two
machines. It is not a shell. Set `HUMANIZE_RENDEZVOUS_PORT` to pin the port for a firewall.
:::

::: warning `native` and a harness elsewhere move the account off this machine
Supervised with the harness here, the credentials, the state directory and the model-provider
connection stay here. `--harness` puts all three on the harness machine, and `--native` sends
a provider's account to the target. See [Where the account lives](#where-the-account-lives).
:::

What running any agent under humanize means is in [Security](/user/security).

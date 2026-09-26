# Machines

Where an agent's turns land. It is one setting on the agent's config, `machine=`, with three
answers. An agent a [flow](/reference/flows) drives needs no setting: the environment each
session is spawned in decides.

The files the agent works on and the commands it runs are the machine's. The agent process
stays here, with its credentials, its state directory and its connection to its model provider,
unless the anchor sends it elsewhere with [`native` or `harness`](/reference/remote-execution).

## The three answers

::: code-group

```python [This machine]
from hmz.coganchor.agents import ClaudeCodeAgentConfig

# machine=None, the default
config = ClaudeCodeAgentConfig(model="claude-opus-5", effort="high")
```

```python [Already running]
from hmz.coganchor import AnchorConfig
from hmz.coganchor.agents import ClaudeCodeAgentConfig
from hmz.coganchor.machines import AnchoredConfig

config = ClaudeCodeAgentConfig(
    model="claude-opus-5",
    effort="high",
    machine=AnchoredConfig(
        anchor=AnchorConfig(
            target="ssh://build-box", workspace="/srv/project"
        )
    ),
)
```

```python [A container of its own]
from hmz.coganchor.agents import ClaudeCodeAgentConfig
from hmz.coganchor.machines import DockerConfig

config = ClaudeCodeAgentConfig(
    model="claude-opus-5",
    effort="high",
    machine=DockerConfig(
        image="python:3.12", workspace="/path/to/project"
    ),
)
```

:::

| | This machine | Already running | A container |
| --- | --- | --- | --- |
| **Setting** | `None` | `AnchoredConfig` | `DockerConfig` |
| **Turns land** | here, as ordinary processes | at the anchor's target | in a new container of the image |
| **Brought up** | — | never: it is already up | on the agent's first turn |
| **Taken down** | — | never: it is somebody else's | when the agent is collected |
| **`agent.anchor`** | `None` | the anchor as written | a `docker://` anchor |
| **[Capabilities](#capabilities)** | none | `remote`, plus the anchor's | `remote`, `isolated`, `managed`, `linux`, plus the anchor's |
| **Needs** | nothing | [the anchor's needs](/reference/remote-execution#requirements) | the same, plus `docker` and a daemon |

## Where a flow's agents work

A flow never sets `machine=`. It declares [environments](/reference/flows), one role each, and
opens every session in one: `await agent.spawn(env=repo)`. The environment decides where that
session's turns land.

| The environment | Where the session's turns land |
| --- | --- |
| a `LocalEnv` role, or `-e repo=local@/srv/project` | this machine, in that directory: `machine=None` |
| `-e repo=ssh@build-box/srv/project` | an `AnchoredConfig` whose anchor has `target="ssh://build-box"` and `workspace="/srv/project"` |
| `-e repo=ssh@build-box/~/project` | the same, with `~` resolved to the login's home once the host is reached |

One agent can have sessions on two machines, each working where it was spawned. The flow's own
code reaches an environment the same way: `await repo.exec(["make", "test"])` and
`await repo.read("NOTES.md")` run on that machine, in that directory.

There is no container environment. A run whose work belongs in a container is started inside
one, or pointed at a container reached as an ssh host.

## `AnchoredConfig`

A machine that is already running: an ssh host, a container somebody else started, a target
left listening on a port, or another directory on this machine standing in for one.

| Field | Default | |
| --- | --- | --- |
| `anchor` | required | An [`AnchorConfig`](/reference/remote-execution#anchorconfig): the target, the workspace as the target names it, what stays here, and every other detail. |

Nothing is brought up and nothing is taken down. `start()` returns the anchor as written.

`anchored(target)` builds one from a target spelling, with every other anchor field at its
default. It returns `None` for `""`:

```python
from hmz.coganchor.agents import anchored

anchored("ssh://build-box")
# AnchoredConfig(anchor=AnchorConfig(target="ssh://build-box"))
anchored("")   # None: this machine
```

## `DockerConfig`

A container of the image you name, holding the project directory at the path it already has,
and running as you. The work it leaves is yours, in your own workspace. Everything else is the
image's.

| Field | Default | |
| --- | --- | --- |
| `image` | `python:3.12` | The image to run. It needs `/bin/sh` and Python ≥ 3.12 for the target half, plus whatever the agent will reach for. |
| `workspace` | the current directory | The project directory. The directory **itself** is mounted, not a copy, so the work outlives the container. It must exist. |

What `start()` runs, one argument per line:

```text{3-4,6}
docker run --detach
    --name humanize-<random>
    --label humanize=<your uid>
    --user <your uid>:<your gid>
    --workdir <workspace>
    --env HOME=/tmp
    --volume <workspace>:<workspace>
    <image>
    /bin/sh -c '<exec the first Python ≥ 3.12 it finds>' humanize
    -c 'import time; time.sleep(2**31)'
```

| | Why |
| --- | --- |
| `--user` uid:gid | Files it writes are yours. |
| `HOME=/tmp` | No account in the image has your uid, and caches stay out of the workspace. |
| `--label humanize=<uid>` | Lets you clean up after a killed flow without reaching past your own containers. |
| the idle Python | Keeps the container up, in the interpreter the target half will use. It tries `python3`, then `python3.14` down to `python3.12`, then well-known install paths, on `PATH` or off it. An image with none is refused as the machine starts, not a turn later. |

The container is reached as a `docker://humanize-<random>`
[target](/reference/remote-execution#targets): no port and no secret. The mirror the agent
works in is a temporary directory here, removed with the container. After starting, the machine
is [observed](#capabilities), so a container that is not Linux or cannot see the workspace
fails to start.

::: tip Cleaning up after a flow that was killed outright
```sh
docker rm -f $(docker ps -q --filter label=humanize=$(id -u))
```
The label carries your uid, so this cannot reach another user's containers on a shared machine.
:::

## When the machine comes up, and when it goes

The same for every kind:

- **Brought up on the agent's first turn**, when `agent.anchor` is first read. Configuring an
  agent pulls no image and starts no container, so a flow that configures more agents than it
  drives pays only for the ones it drives.
- **Shared by every session that agent opens.** They must find the workspace as the last turn
  left it.
- **One machine per agent.** Two agents built from one config get a machine each. The config is
  a setting, not the machine.
- **Taken down when the agent is collected**, or at exit for one held to the end. Only what was
  started here is stopped.
- **The workspace is left behind** either way.

## The workspace as your own code reaches it

An agent under a machine has its files and commands answered from that machine. Your own code
is this process, so a file it opens is this machine's. `Mapped` reaches the machine's workspace
over the same connection an anchored turn uses:

```python
from hmz.coganchor.machines import Mapped

# nothing connects until something is asked
with Mapped(agent.anchor) as held:
    held.workspace          # the project directory, as named there
    held.read_text("pyproject.toml")
    held.write_text("notes.md", "…")
    said = held.run(["python", "-m", "pytest", "-q"])
    said.ok, said.status, said.output
```

| Member | |
| --- | --- |
| `workspace` | The project directory, as the machine names it. |
| `read_text(path, encoding="utf-8")`, `read_bytes(path)` | A file's contents. |
| `write_text(path, said, encoding="utf-8", mode=None)`, `write_bytes(path, said, mode=None)` | Writes a file, replacing what was there. `mode=None` keeps the permissions it has. |
| `listdir(path="")` | Names in a directory. Iterating a `Mapped` lists the workspace. |
| `exists(path)` | Whether it is there. Raises `OSError` when the machine cannot be reached at all. |
| `mkdir(path, *, parents=True)`, `remove(path)` | Makes a directory; removes a file. |
| `run(argv, *, cwd="", env=None)` | Runs a command there and waits. `argv` is a list, or one line split the way a shell splits it. `env` is added to the machine's environment; this process's is not passed on. Returns `Ran`. |
| `close()` | Lets go of the connection. Safe to call twice. |

`Ran` has `argv`, `status`, `output` (both streams, in the order they arrived) and `ok`
(`status == 0`). A command killed by a signal reads as 128 plus the signal, and one whose end
was never reported reads as `1`: neither is success.

Every path may be absolute as the machine names it, or relative to the workspace. A flow has no
need of `Mapped`: its environments already reach the workspace wherever it is.

## Capabilities

Each setting says what a machine of it comes to, **without starting anything**, so a flow's
requirement can be refused before an image is pulled:

```python
anchor = AnchorConfig(target="ssh://build-box")

AnchoredConfig(anchor=anchor).capabilities
# {"remote", "anchor:supervised"}
DockerConfig(image="python:3.12").capabilities
# {"remote", "isolated", "managed", "linux", "anchor:supervised"}
```

| Name | Means | Said by |
| --- | --- | --- |
| `remote` | The work lands through an anchor, not as an ordinary process here. A `local:` target counts: it stands in for a machine of its own. | both |
| `isolated` | The tools a command finds are the image's, not this machine's. | `DockerConfig` |
| `managed` | Started for the agent and taken down with it. A machine that was already running never is. | `DockerConfig` |
| `linux`, `darwin` | The platform. A container promises `linux`; a machine already running says which once reached. | `DockerConfig`, or the handshake |
| `anchor:supervised` | The agent runs under a supervisor and every file and command is answered from the target. | the anchor |
| `anchor:native-cli` | The CLI already on the target runs there, and its streams are carried. | the anchor, with `native=True` |
| `anchor:afar` | Supervised, with the supervisor and the agent on a machine other than this one. Always said with `anchor:supervised`. | the anchor, with `harness` elsewhere |

The `anchor:` names describe how a turn reaches the machine, so they come from the anchor:

```python
AnchorConfig(target="ssh://build-box").capabilities
# {"anchor:supervised"}
AnchorConfig(target="ssh://build-box", native=True).capabilities
# {"anchor:native-cli"}
AnchorConfig(target="ssh://build-box", harness="same").capabilities
# {"anchor:supervised", "anchor:afar"}
```

The platform of a machine that was already running is unknown until something connects. The
*machine* joins the setting's answer with what the handshake says:

```python
machine = AnchoredConfig(anchor=anchor).create()
machine.capabilities              # nothing asked yet:
# {"remote", "anchor:supervised"}
machine.observe(machine.start())  # and the handshake says linux:
# {"remote", "anchor:supervised", "linux"}
```

`observe` asks what [`check`](/reference/remote-execution#from-python) asks: the handshake,
then the workspace. It raises `OSError` for a machine that cannot be reached or lacks the
workspace. It raises `RuntimeError` for one that contradicts a platform its setting promised,
such as `the machine at docker://humanize-4f2a cannot serve linux: it says it is darwin`.

## Choosing between them

| You want | Use |
| --- | --- |
| The agent to work in this checkout, as you | **this machine** |
| The work on a bigger box, a GPU host, or a machine with the right toolchain | **already running**, `ssh://`. In a flow: `-e <role>=ssh@<host>/<workdir>` |
| Cheap reconnects across a long loop of short turns | **already running**, `tcp://` to a [target left listening](/reference/remote-execution#serving-a-target) |
| A toolchain that is not yours, without giving up your workspace | **a container of its own** |
| To limit what the agent may *do* | none of these |

::: warning Isolation here is about environment, not permission
A container gives the agent a different toolchain and filesystem, and mounts your workspace
into it. It does not stop the agent editing that workspace. A served target's `--export` bounds
which files a request may name, not what the commands it runs can do. See
[Security](/user/security).
:::

## Writing a machine of your own

Two classes: the setting, and the machine it brings up.

```python
from dataclasses import dataclass

from hmz.coganchor import AnchorConfig
from hmz.coganchor.machines import MachineBase, MachineConfig

@dataclass(frozen=True, kw_only=True)
class PodmanConfig(MachineConfig):
    image: str = "python:3.12"

    @property
    def capabilities(self) -> frozenset[str]:
        places = frozenset({"remote", "isolated", "managed", "linux"})
        return places | AnchorConfig().capabilities

    def create(self) -> "Podman":
        return Podman(self)

class Podman(MachineBase):
    _config: PodmanConfig

    def start(self) -> AnchorConfig:
        anchor = ...  # bring it up; the anchor that reaches it
        try:
            self.observe(anchor)  # confirm the platform declared above
        except BaseException:
            self.stop()  # a refusal must not strand what it started
            raise
        return anchor

    def stop(self) -> None:
        ...  # take down what start() brought up; keep the workspace
```

| | Contract |
| --- | --- |
| `MachineConfig` | Frozen. `capabilities` defaults to the empty set, and uses only the words above. `create()` gives each caller a machine of its own. |
| `start()` | Leaves the machine ready for turns and returns the anchor. Takes down whatever it created if it cannot finish. |
| `stop()` | Called once per machine that was started, never for one that was not. Leaves the workspace. Does nothing by default, which is what `AnchoredConfig` uses. |
| `observe(anchor)` | On `MachineBase`, for every machine with an anchor to ask. |

The contract is `specs/coganchor/machines.md`.

## API summary

```python
from hmz.coganchor.machines import (
    MachineConfig, MachineBase, AnchoredConfig, Anchored,
    DockerConfig, Docker, Mapped, Ran,
)
from hmz.coganchor.agents import anchored
```

| Name | |
| --- | --- |
| `MachineConfig` | The setting: `.capabilities`, `.create() -> MachineBase`. |
| `MachineBase` | The machine: `.start() -> AnchorConfig`, `.stop()`, `.capabilities`, `.observe(anchor)`. |
| `AnchoredConfig`, `Anchored` | A machine that is already running. |
| `DockerConfig`, `Docker` | A container started for the agent. |
| `Mapped` | The machine's workspace, as your own code reaches it. |
| `Ran` | What one command there came to: `.argv`, `.status`, `.output`, `.ok`. |
| `anchored(target)` | An `AnchoredConfig` from a target spelling, or `None` for `""`. |
| `agent.anchor` | `AnchorConfig \| None`: where the agent's turns land, bringing the machine up if it must. |

# Machines

Where an agent's turns land. One setting on the agent's config, with three answers — and, for an
agent a [flow](/reference/flows) drives, one nobody sets: the environment the flow spawned the
session in is where its turns land.

The agent process always stays on **this** machine, whichever answer you give — keeping its
credentials, its state directory and its link to its model provider. What moves is the project
it reads and the commands it runs.

## The three answers

```python
from hmz.coganchor.agents import ClaudeCodeAgentConfig
from hmz.coganchor import AnchorConfig
from hmz.coganchor.machines import AnchoredConfig, DockerConfig

here    = ClaudeCodeAgentConfig(model=…, effort=…)
there   = ClaudeCodeAgentConfig(model=…, effort=…, machine=AnchoredConfig(
              anchor=AnchorConfig(target="ssh://build-box", workspace="/srv/project")))
its_own = ClaudeCodeAgentConfig(model=…, effort=…, machine=DockerConfig(image="python:3.12"))
```

It is **one** setting because it is one question. A machine that is already running and a
machine started for the agent are both answers to "where does this work land", and an agent has
one answer to that.

## Where a flow's agents work

A flow never says `machine=`, and nobody says it for one. It declares the
[environments](/reference/flows#where-each-agent-works) it works in, one role apiece, and opens
every session in one of them — `await agent.spawn(env=repo)` — and the environment is what
decides where that session's turns land:

| The environment | Where the session's turns land |
| --- | --- |
| a `LocalEnv` role — the directory the run was started in — or `-e repo=local@/srv/project` | this machine, in that directory: no `machine` at all |
| `-e repo=ssh@build-box/srv/project` | that host, as [a machine that is already running](#a-machine-that-is-already-running): an anchored `ssh://build-box` target whose workspace is `/srv/project` |

The harness driver makes the agent a session runs as with that answer, so one agent of a flow
may have sessions on two machines, each working where it was spawned. The flow's own code
reaches an environment the same way its agent does: `await repo.exec(["make", "test"])` and
`await repo.read("NOTES.md")` run on that machine, in that directory.

A container is not among them. The flow API's environments are this machine and hosts reached
with ssh; a run whose work belongs in a container is a run started inside one, or pointed at a
host that is one.

## This machine

The default, and nothing to configure. `machine=None`, `agent.anchor` is `None`, turns run as
ordinary local processes in the directory the session was opened at.

Nothing below is needed for this.

## A machine that is already running

An ssh host, a container someone else started, a machine left listening on a port, or another
directory on this machine standing in for one.

```python
from hmz.coganchor import AnchorConfig
from hmz.coganchor.machines import AnchoredConfig

machine = AnchoredConfig(
    anchor=AnchorConfig(target="ssh://build-box", workspace="/srv/project")
)
```

`AnchorConfig` is where every detail lives — the target, the workspace as the target has it,
what to keep local, where the agent's own network connections go. All of it, and what does and
does not cross, is in [Remote execution](/reference/remote-execution).

Nothing is brought up and nothing is taken down: the machine is somebody else's, and all this
says is that the agent's turns land there rather than here.

**Requirements:** Linux on x86-64 or aarch64 here; a POSIX system with a recent `python3`
there. No root, no compiler, no kernel module, nothing installed on the far end.

## A container of the agent's own

A container of the image you name, holding this project directory at the path it already has
and running as you — so the work it leaves behind is yours, in your own workspace, and
everything else is the image's.

```python
from hmz.coganchor.machines import DockerConfig

machine = DockerConfig(image="python:3.12", workspace="/path/to/project")
```

| Field | Default | |
| --- | --- | --- |
| `image` | `python:3.12` | The image to run. Needs a `python3` for the target half, plus whatever the agent is expected to reach for. |
| `workspace` | this directory | The project directory to give it. The directory **itself**, mounted — not a copy — so the work outlives the container. |

The container:

- runs as your uid and gid, so files it writes are yours;
- has `HOME=/tmp`, away from the workspace, so what a command caches is not the project's;
- is reached as a `docker://` [target](/reference/remote-execution#targets), and needs no port and no
  secret;
- is labelled `humanize=<your uid>`.

An image with no Python the target half can use is refused where the machine is set up, rather
than a turn later; where the image keeps one does not matter, since it is looked for off the
`PATH` as well as on it.

This is an agent's own setting, made from Python; the flow API has no environment that is a
container.

**Requirements:** everything the answer above needs, plus the `docker` command and a daemon to
reach.

**Cleaning up after a flow that was killed outright:**

```sh
docker rm -f $(docker ps -q --filter label=humanize=$(id -u))
```

The label carries your uid, so this cannot reach past you on a machine several people share.

## When the machine comes up, and when it goes

The same for every kind:

- **Brought up on the agent's first turn**, not when the agent is constructed. Configuring an
  agent pulls no image and starts no container, so a flow that configures more agents than it
  drives pays only for the ones it drives.
- **Shared by every session that agent opens.** Its sessions are turns of one conversation each
  and must find the workspace as the last turn left it.
- **One machine per agent.** Two agents built from the same config get one machine each — the
  config is a setting, not the machine.
- **Taken down when the agent is collected**, or at exit for one held to the end. A machine
  that was already running is left running; only what was started here is stopped.
- **The workspace is left behind** either way.

## The workspace as your own code reaches it

An agent under a machine is answered for without being told. Code driving it is not — it is this
process, running Python — so a file it opens is this machine's file and a command it runs is
this machine's command. `Mapped` is that workspace as the machine has it, over the connection an
anchored turn opens:

```python
from hmz.coganchor.machines import Mapped

held = Mapped(agent.anchor)      # nothing is connected until something is asked
held.workspace                   # the project directory, as the machine names it
held.read_text("pyproject.toml")
held.write_text("notes.md", "…")
held.listdir("src")
held.exists("src/hmz")
held.mkdir("build")
held.remove("build/stale")
said = held.run(["python", "-m", "pytest", "-q"])
said.ok, said.status, said.output
```

Every path may be given as the machine names it or relative to the workspace. A flow has no need
of it: its environments are the workspace as the flow reaches it, wherever they are.

## What a machine comes to

Each setting says what a machine of it would come to, in capability names — and says it
**without starting anything**, so a requirement can be refused before the first turn rather
than after an image has been pulled:

```python
AnchoredConfig(anchor=…).capabilities          # {"remote"}
DockerConfig(image="python:3.12").capabilities # {"remote", "isolated", "managed", "linux"}
```

| Name | Means |
| --- | --- |
| `remote` | The work lands through an anchor rather than as an ordinary process here. A `local:` target answers to it too — it stands in for a machine of its own, and a turn reaches it down the same road. |
| `isolated` | The tools a command finds there are the image's, not this machine's. |
| `managed` | Started for the agent, and taken down with it. A machine that was already running is never `managed` — nobody here brought it up, so nobody here may take it down. |
| `linux` / `darwin` | The platform it runs. |

One of those is not the setting's to promise. The platform of a machine that was **already
running** is whatever it turns out to be, and nothing knows it until something has connected —
so it is read from the handshake instead, and the *machine* is where the two answers meet:

```python
machine = AnchoredConfig(anchor=anchor).create()
machine.capabilities              # {"remote"} -- nothing has been asked yet
machine.observe(machine.start())  # {"remote", "linux"} -- and the machine said the second
```

`observe` asks what `hmz.coganchor.check` asks — the handshake, and then the workspace — so it
raises `OSError` for a machine that cannot be reached *or* has not got the directory the anchor
names, which is the same bar `start` is held to.

A machine whose handshake contradicts what its setting promised **fails to start**, naming the
capability it could not serve:

```text
the machine at docker://humanize-4f2a cannot serve linux: it says it is darwin
```

And the anchor answers the other half of the question — not where the work lands but how a
turn reaches it, which is a fact about the road rather than about the machine:

```python
AnchorConfig(target="ssh://build-box").capabilities               # {"anchor:supervised"}
AnchorConfig(target="ssh://build-box", native=True).capabilities  # {"anchor:native-cli"}
AnchorConfig(target="ssh://build-box", harness="same").capabilities
#                                       {"anchor:supervised", "anchor:afar"}
```

The same machine reached two ways is two different sets of things a turn may be asked to do.
`anchor:supervised` runs the agent here and answers everything it does from the target;
`anchor:native-cli` runs the CLI the target already has and carries its streams. The second
needs that CLI installed there and sends the account across to it; the first needs neither.

`anchor:afar` is the third, and it is said *alongside* `anchor:supervised` rather than instead
of it: the turn is supervised, and what the name adds is that the supervisor and the agent
process are not on this machine — which matters to anything that must keep the agent's own
process here, because the account is here or because it reaches a provider only this machine
can. Read [Remote execution](/reference/remote-execution#where-the-harness-runs).

## Choosing between them

| You want | Use |
| --- | --- |
| The agent to work in this checkout, as you | **this machine** |
| The work to happen on a bigger box, a GPU host, or a machine with the right toolchain | **already running**, `ssh://` — for a flow, `-e <role>=ssh@<host>/<workdir>` |
| To keep reconnecting cheap across a long loop of short turns | **already running**, `tcp://` with a listening target |
| The agent confined to a toolchain that is not yours, without giving up your workspace | **a container of its own** |
| To confine what the agent may *do* | none of these — see below |

**Isolation here is about environment, not permission.** A container gives the agent a
different toolchain and a different filesystem, and mounts your workspace into it. It does not
stop the agent editing that workspace, and an `hmz internal anchor` export bounds which files a
request may name but does not confine the commands that request can run. Read
[Security](/user/security).

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
        return frozenset({"remote", "isolated", "managed", "linux"})

    def create(self) -> "Podman":
        return Podman(self)

class Podman(MachineBase):
    _config: PodmanConfig

    def start(self) -> AnchorConfig:
        anchor = ...  # bring it up, and answer with the anchor that reaches it
        try:
            self.observe(anchor)  # have it confirm the platform declared above
        except BaseException:
            self.stop()  # a refusal must not strand what start() just brought up
            raise
        return anchor

    def stop(self) -> None:
        ...  # take down what start() brought up; leave the workspace behind
```

They are two classes because one config drives as many agents as it is given to, and each of
them gets a machine of its own. `start` must take down whatever it created if it cannot finish;
`stop` is called once per machine that was started and never for one that was not, so it only
has to answer for what `start` got as far as creating. `stop` has a do-nothing default, which is
what `AnchoredConfig` uses. `capabilities` has a default too — the empty set, so a machine that
says nothing comes to nothing rather than to everything it never denied — and `observe` is on
`MachineBase` for every machine that has an anchor to ask.

The contract is `specs/coganchor/machines.md`.

## API summary

```python
from hmz.coganchor.machines import (
    MachineConfig,   # the setting: .capabilities, .create() -> MachineBase
    MachineBase,     # the machine: .start() -> AnchorConfig, .stop() -> None,
                     #              .capabilities, .observe(anchor)
    AnchoredConfig,  # a machine that is already running
    Anchored,
    DockerConfig,    # a container started for the agent
    Docker,
    Mapped,          # the workspace on that machine, as your own code reaches it
    Ran,             # what one command run there came to: .status, .output, .ok
)
```

And on the agent side:

```python
agent.anchor   # AnchorConfig | None -- where its turns land, bringing the machine up if it must
```

And the two shorthands that build the settings above:

```python
from hmz.coganchor.agents import (
    anchored,   # anchored("ssh://build-box") -> AnchoredConfig, from a target as it is written
    isolated,   # isolated("python:3.12") -> DockerConfig
)
```

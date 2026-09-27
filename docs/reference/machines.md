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

```python [A container on a GPU box]
from hmz.coganchor.agents import ClaudeCodeAgentConfig
from hmz.coganchor.machines import DockerConfig

config = ClaudeCodeAgentConfig(
    model="claude-opus-5",
    effort="high",
    machine=DockerConfig(
        image="ghcr.io/me/cuda-dev:latest",
        endpoint="ssh://me@gpu-box",
        workspace="/srv/project",   # a path on gpu-box
        cpus=8,
        memory=32 << 30,
        gpus=("0",),
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
| **Needs** | nothing | [the anchor's needs](/reference/remote-execution#requirements) | the same, plus `docker` here and a daemon it can reach |

## Where a flow's agents work

A flow never sets `machine=`. It declares [environments](/reference/flows), one role each, and
opens every session in one: `await agent.spawn(env=repo)`. The environment decides where that
session's turns land.

| The environment | Where the session's turns land |
| --- | --- |
| a `LocalEnv` role, or `-e repo=local@/srv/project` | this machine, in that directory: `machine=None` |
| `-e repo=ssh@build-box/srv/project` | an `AnchoredConfig` whose anchor has `target="ssh://build-box"` and `workspace="/srv/project"` |
| `-e repo=ssh@build-box/~/project` | the same, with `~` resolved to the login's home once the host is reached |
| `-e repo=ssh@gpu/srv/project`, `gpu` a saved [environment provider](#environment-providers) | an `AnchoredConfig` whose target carries everything `gpu` says: `ssh://me@10.0.0.2:2222?IdentityFile=~/.ssh/gpu` |
| `-e repo=ssh@gpu` | the same, in the workdir `gpu` was saved with |
| `-e repo=docker@gpubox/srv/project`, `gpubox` a saved [docker provider](#a-docker-daemon) | an `AnchoredConfig` whose anchor has `target="docker://humanize-gpubox-repo-<hex>[@<endpoint>]"`, `workspace="/srv/project"`, and a mirror of its own under `~/.humanize/envs/mirrors/<container>` |
| `-e repo=docker@local/srv/project` | the same, on docker's default here, with no provider saved |
| `-e repo=docker@gpubox` | the same, in the workdir `gpubox` was saved with |

One agent can have sessions on two machines, each working where it was spawned. The flow's own
code reaches an environment the same way: `await repo.exec(["make", "test"])` and
`await repo.read("NOTES.md")` run on that machine, in that directory.

### A container per environment {#docker-environments}

`-e role=docker@<provider>/<workdir>` gives the role a container of its own, on the daemon the
provider names. It is started when the run first reaches its environments, before any agent
starts, and removed when the run closes it. The workdir is a directory of the daemon's host,
mounted at its own path, so what the agents write there outlives the container.

| | |
| --- | --- |
| **Image** | the role's [`_image`](/reference/flows#what-a-machine-must-have), else the provider's `image`, else `python:3.12-slim`. It needs `/bin/sh` and Python ≥ 3.12, and no sshd. |
| **Limits** | exactly the CPUs, memory and GPUs the role declares, as hard limits. What it declares none of has no limit; no GPU without `GPUEnvMixin`. The provider's `runtime` and `run_args` are passed too. |
| **Labels** | `humanize.provider`, `humanize.role`, `humanize.host` and `humanize.pid` beside `humanize` and what it holds (`humanize.cpus`, `humanize.memory`, `humanize.gpus`). |
| **Derived environments** | a subdirectory, a worktree, a temporary copy or a scratch directory is in the same container. What is not under the workdir is the container's own, and goes with it. |
| **Agents** | run here, supervised, in a mirror of their own; every command they run lands in the container through `docker exec`. |

Before the container starts, what the role asks is held against what the provider may still
hand out: what it was saved with, or the daemon's own where that is `0`, less what its running
containers hold, read off their labels by [`allocations`](#what-a-daemon-has-given-out). A
provider with `max_containers` runs no more than that at once, and GPUs are the first ids
nobody holds. Where something is short the run is refused, saying what is free and who holds
the rest:

```text
docker@gpubox has 0 of 2 GPUs free, and 'box' asks for 1 (GPU 0 held by
humanize-gpubox-box-1a2b3c4d, pid 4242 on gpubox; GPU 1 held by humanize-gpubox-box-5e6f7a8b,
pid 4250 on gpubox)
```

Two runs on this machine never work that out for one provider at once: each holds
`~/.humanize/env-providers/docker/.<name>.lock` until its container is up and labelled. A run
killed outright leaves its container behind; the next run on that provider removes any whose
`humanize.pid` on this host is gone.

## Environment providers {#environment-providers}

A machine an environment may be put on, saved under a name so that `-e` can name it: an ssh
host with everything `ssh` needs to be told to reach it, or a docker daemon with what it may
hand out. Each is a directory of its own, `~/.humanize/env-providers/<backend>/<name>/`, holding
`provider.json`; every level is yours alone (`0700`, the file `0600`). A name is letters,
digits, `.`, `-` and `_`, starting with a letter or a digit.

::: code-group

```python [ssh, typed]
from hmz.sdk import Hmz

envs = Hmz().environments
envs.add(envs.new(
    "ssh", "gpu",
    host="10.0.0.2", user="me", port=2222,
    identity_file="~/.ssh/gpu", proxy_jump="me@bastion",
    options={"ServerAliveInterval": "15"},
    workdir="~/project",
))
```

```python [ssh, from your ssh config]
from hmz.sdk import Hmz

envs = Hmz().environments
for host in envs.hosts():           # what `ssh -G` makes of each Host
    print(host.alias, host.user, host.host, host.port)
envs.import_ssh()                   # one provider per Host, named after it
envs.import_ssh("~/work/ssh_config", ["gpu"], update=True)
```

```python [docker]
from hmz.sdk import Hmz

envs = Hmz().environments
envs.add(envs.new(
    "docker", "gpu-docker",
    endpoint="ssh:gpu",             # the daemon on the host saved as `gpu`
    image="python:3.12", runtime="nvidia",
    cpus=32, memory=256 << 30, gpus=["0", "1"],
))
print(envs.check(envs.find("docker", "gpu-docker")))
```

:::

### An ssh host

| Field | |
| --- | --- |
| `host` | The machine: a host name or an address. With `alias` too, what the alias is pointed at instead (`HostName`). |
| `user`, `port` | Who to log in as, and the port. Unset, your ssh config's or ssh's own. |
| `identity_file` | The key, by path. humanize never reads what is in it. |
| `proxy_jump` | The host or hosts it is reached through (`ProxyJump`). |
| `options` | Anything else, each passed as `-o KEYWORD=VALUE`. A setting with a field of its own is refused here. |
| `alias`, `config` | Set by an import: the `Host` it came from, and the config file where that is not your own. |
| `workdir` | Where `-e role=ssh@<name>` works when the line names no workdir. |

Every field that is set is passed to `ssh`, **ahead of** humanize's own options and of your ssh
config, so what the provider says wins. An imported provider keeps the alias rather than what
it resolved to: `ssh` resolves it through the config every time, so editing the config edits the
provider. `import_ssh` follows `Include` and skips patterns (`Host *`, `web-?`, `!x`); a provider
already saved under a name is left alone unless `update=True`, which keeps its workdir.

Two providers at one host told different things get a connection each: the ssh control socket
is named for what the provider says as well as for the host, port and login.

### A docker daemon

| Field | |
| --- | --- |
| `endpoint` | `local` (whatever `docker` here reaches), `unix:///path.sock`, `tcp://host:port`, `ssh://[user@]host[:port]`, `ssh:<name>` for the daemon on a saved ssh host, or `context:<name>` for a docker context. |
| `tls_dir` | For `tcp://`: the directory holding `ca.pem`, `cert.pem` and `key.pem`. |
| `image`, `runtime`, `run_args` | The image a container starts from when the flow names none, the runtime (`nvidia`), and anything else `docker run` is told. |
| `cpus`, `memory`, `gpus`, `gpu_memory`, `max_containers` | What it may hand out: CPUs, bytes, GPU device ids, bytes per GPU, containers at once. `0` or empty is all it has. |
| `workdir` | Where `-e role=docker@<name>` works when the line names no workdir. |

`provider.daemon()` is the daemon as a [`hmz.coganchor.transport.Endpoint`](#endpoints), whose `.docker(*argv)` is the
one place an endpoint becomes a `docker` command line: `daemon.docker("info")` is
`["env", "-u", "DOCKER_HOST", …, "docker", "--host", "unix:///var/run/docker.sock", "info"]`.
`tls_dir` becomes `?tls=<dir>`. `ssh:<name>` becomes `ssh://[user@]host[:port]?KEYWORD=VALUE&…`,
carrying everything the saved host says. Docker dials that host with its own `ssh`, which it can
only tell the login, the port and the host, so the options go in an `ssh` of their own, written
once under `~/.humanize/docker-ssh/<digest>/ssh` and put first on the `PATH` of every `docker`
sent there.

### Checking one

`envs.check(provider, seconds=30)` asks it what it has and never raises:

| | ssh host | docker daemon |
| --- | --- | --- |
| **Asks** | what a run asks when it first reaches the host, down the same road, with `BatchMode=yes` | `docker info` |
| **Answers** | `home`, `cpus`, `memory`, `gpus`, `gpu_memory` | `cpus`, `memory`, `gpus` (by CDI device), `runtimes` (default first), `version` |
| **Also** | | `short`: what it was saved as handing out and has not got |

`reached` is `False` with `said` saying why where it did not answer in time, wanted a
password, or was not there.

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
image's. The daemon may be this machine's or another's, and the container may be given a share
of that daemon's CPUs, memory and GPUs.

| Field | Default | |
| --- | --- | --- |
| `image` | `python:3.12` | The image to run. It needs `/bin/sh` and Python ≥ 3.12 for the target half, plus whatever the agent will reach for. No sshd: turns reach it through `docker exec`. |
| `workspace` | the current directory | The project directory, as the daemon's host names it. The directory **itself** is mounted, not a copy, so the work outlives the container. It must exist there. |
| `endpoint` | `local` | The daemon to run it on. See [Endpoints](#endpoints). |
| `name` | `humanize-<random>` | The container's name. A name somebody else's container already has is refused, and their container is left alone. A config with a `name` brings up one container at a time, so give it to one agent. |
| `cpus` | no limit | How many CPUs it may use, e.g. `1.5`. |
| `memory` | no limit | How many bytes of memory it may use. |
| `shm_size` | docker's | How large its `/dev/shm` is, in bytes. |
| `gpus` | `()`: none | The GPUs it is given, by the ids `nvidia-smi` lists, or `"all"`. |
| `runtime` | the daemon's | The OCI runtime to run it under, e.g. `runc` or `nvidia`. |
| `network` | the daemon's | The network to put it on. |
| `run_args` | `()` | Anything else `docker run` is told, ahead of the image and of humanize's own limits. |
| `env` | `{}` | Variables to set in it. |
| `labels` | `{}` | Labels to put on it, e.g. which provider it was allocated from. `humanize`, `humanize.cpus`, `humanize.memory` and `humanize.gpus` are humanize's own and are not taken from here. |

A setting docker would refuse, such as `cpus=0` or an endpoint it cannot read, is refused when
the `DockerConfig` is built.

What `start()` runs, one argument per line:

```text{4-6,9-10}
docker [endpoint] run --detach
    --cidfile <mirror>/container
    --name humanize-<random>
    --label humanize=<your uid>
    --label humanize.cpus=… --label humanize.memory=… --label humanize.gpus=…
    --user <your uid>:<your gid>
    --workdir <workspace>
    --env HOME=/tmp
    --env NVIDIA_VISIBLE_DEVICES=void
    --mount type=bind,source=<workspace>,target=<workspace>
    <run_args>
    --cpus … --memory … --shm-size … --runtime … --network …
    --device nvidia.com/gpu=<id>
    <image>
    /bin/sh -c '<exec the first Python ≥ 3.12 it finds>' humanize
    -c 'import time; time.sleep(2**31)'
```

Only what the setting names is passed: no `--cpus` without `cpus`, no GPU flag without `gpus`.

| | Why |
| --- | --- |
| `--user` uid:gid | Files it writes are yours. `0:0` on a rootless daemon, whose root is you. On a daemon elsewhere, whoever owns the workspace there. |
| `HOME=/tmp` | No account in the image has your uid, and caches stay out of the workspace. |
| `NVIDIA_VISIBLE_DEVICES=void` | Unless GPUs are handed out by `--gpus`, which sets it itself. A daemon whose default runtime is NVIDIA's gives an image asking for every GPU every GPU; this makes it none beyond the ones named. |
| `--mount` | A workspace missing on the daemon's host is refused, not created there owned by root. |
| `--label`s | Whose it is, for cleaning up, and what it holds, for [`allocations`](#what-a-daemon-has-given-out). |
| `--cidfile` | What `stop()` removes is the container docker says it made, by its id, and nothing else. |
| the idle Python | Keeps the container up, in the interpreter the target half will use. It tries `python3`, then `python3.14` down to `python3.12`, then well-known install paths, on `PATH` or off it. An image with none is refused as the machine starts, not a turn later. |

The container is reached as a `docker://humanize-<random>`
[target](/reference/remote-execution#targets), or `docker://humanize-<random>@<endpoint>` on
any daemon but the default: no port and no secret. The mirror the agent works in is a temporary
directory here, removed with the container. After starting, the machine is
[observed](#capabilities), so a container that is not Linux or cannot see the workspace fails
to start.

### Endpoints

| `endpoint` | The daemon | Needs |
| --- | --- | --- |
| `local` | docker's default here, as `DOCKER_HOST`, `DOCKER_CONTEXT` and the current context leave it | a daemon here |
| `unix:///PATH` | the one listening on that socket, e.g. a rootless one | the socket |
| `tcp://HOST:PORT` | one listening on a port, in plain TCP | a daemon told to listen there |
| `tcp://HOST:PORT?tls=DIR` | the same, over TLS verified with `DIR/ca.pem`, `DIR/cert.pem` and `DIR/key.pem` | the certificates |
| `ssh://[USER@]HOST[:PORT]` | the one on that host, through docker's own ssh transport | ssh access to the host as your `ssh` config has it, and `docker` there. The container needs no sshd. |
| `ssh://[USER@]HOST[:PORT]?KEYWORD=VALUE&…` | the same, with `ssh` told each option first (`F=<file>` for a config of its own) | the same |
| `context:NAME` | the one a docker context names | the context, in `DOCKER_CONFIG` or `~/.docker` |

Every `docker` command for the container, from `run` to the `exec` each turn rides and the
final `rm`, is sent to that daemon. Any endpoint but `local` is said on the command line, with
`DOCKER_HOST`, `DOCKER_CONTEXT` and the TLS variables taken off, so nothing in the environment
can send one of them elsewhere.

`unix://` daemons, and `local` unless `DOCKER_HOST` sends it elsewhere, are taken to be this
machine's: the workspace is checked here, and the container runs as you, or as its own root on
a rootless daemon, which is you on the host. Any other is taken to be elsewhere. There the
workspace is a path on *that* host: it is asked for by a throwaway container of the same image
given the same directory, which is refused when the host has no such directory, and the
container runs as whoever owns it there.

### GPUs

`gpus=("0",)` gives the container GPU 0 and no other; `gpus="all"` gives it every one.
Where the daemon lists its devices by [CDI](https://github.com/cncf-tags/container-device-interface)
name and lists every one asked for, each is passed as `--device nvidia.com/gpu=<id>`. Otherwise
`--gpus "device=<ids>"` or `--gpus all` is, which needs the NVIDIA container toolkit. With
`gpus=()` the container sees no GPU, even from an image, like CUDA's own, that asks for all of
them.

### What a daemon has given out

`allocations(endpoint="local", labels=None)` lists humanize's running containers on one daemon,
whoever started them, with what each was given:

```python
from hmz.coganchor.machines import allocations

for held in allocations("ssh://me@gpu-box", {"humanize.provider": "gpu-box"}):
    held.name, held.cpus, held.memory, held.gpus, held.labels
# ("humanize-4f2a", 8.0, 34359738368, ("0",), {...})
```

`cpus` and `memory` are `None` for a container given no limit, and `gpus` is `()` for one given
none. `labels` narrows the list to containers carrying every label given. A daemon that cannot
be asked raises `OSError` rather than reading as one with nothing on it.

::: tip Cleaning up after a flow that was killed outright
```sh
docker rm -f $(docker ps -q --filter label=humanize=$(id -u))
```
The label carries your uid, so this cannot reach another user's containers on a shared machine.
Add `--host` or `--context` for a daemon elsewhere, but there the uid is the one on the machine
that started each container, and several machines sharing that daemon can have users with the
same one: check what it lists before removing it.
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
| A flow's environment in a container of its own, sized by what its role declares | `-e <role>=docker@<provider>/<workdir>`: [a container per environment](#docker-environments) |
| Cheap reconnects across a long loop of short turns | **already running**, `tcp://` to a [target left listening](/reference/remote-execution#serving-a-target) |
| A toolchain that is not yours, without giving up your workspace | **a container of its own** |
| A share of a GPU box's CPUs, memory and GPUs, in an image of your choosing | **a container of its own**, with `endpoint`, `cpus`, `memory` and `gpus` |
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
    DockerConfig, Docker, Allocation, allocations, Mapped, Ran,
)
from hmz.coganchor.machines.store import SSHProvider, DockerProvider, daemon_of
from hmz.coganchor.agents import anchored
```

| Name | |
| --- | --- |
| `MachineConfig` | The setting: `.capabilities`, `.create() -> MachineBase`. |
| `MachineBase` | The machine: `.start() -> AnchorConfig`, `.stop()`, `.capabilities`, `.observe(anchor)`. |
| `AnchoredConfig`, `Anchored` | A machine that is already running. |
| `DockerConfig`, `Docker` | A container started for the agent, on a daemon here or elsewhere. |
| `allocations(endpoint, labels)` | humanize's running containers on a daemon, each an `Allocation`: `.name`, `.cpus`, `.memory`, `.gpus`, `.labels`. |
| `Mapped` | The machine's workspace, as your own code reaches it. |
| `Ran` | What one command there came to: `.argv`, `.status`, `.output`, `.ok`. |
| `anchored(target)` | An `AnchoredConfig` from a target spelling, or `None` for `""`. |
| `SSHProvider`, `DockerProvider` | A saved [environment provider](#environment-providers). `Hmz().environments` is how to reach them. |
| `daemon_of(endpoint, tls_dir="")` | The daemon an endpoint as a provider spells it names, as an `Endpoint`: `.docker(*argv)`, `.here`. |
| `agent.anchor` | `AnchorConfig \| None`: where the agent's turns land, bringing the machine up if it must. |

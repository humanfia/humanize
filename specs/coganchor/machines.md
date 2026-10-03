# `coganchor/machines`

Where an agent's turns land -- a machine already running, or one brought up for the agent,
and what of its host it holds -- the workspace on it as a flow's own Python reaches it, and the
runtimes: the machines an environment may be put on, written down under names. It does not say
how a turn travels to a machine, which is the anchor's, and it runs no turns itself.

## API

```python
# base.py
@dataclass(frozen=True, kw_only=True)
class MachineConfig(ABC):
    @property
    def capabilities(self) -> frozenset[str]: ...  # empty here
    @abstractmethod
    def create(self) -> MachineBase: ...

class MachineBase(ABC):
    def __init__(self, config: MachineConfig) -> None: ...
    @property
    def capabilities(self) -> frozenset[str]: ...
    def observe(self, anchor: AnchorConfig) -> frozenset[str]: ...
    @abstractmethod
    def start(self) -> AnchorConfig: ...
    def stop(self) -> None: ...

# anchored.py -- a machine that was already running
@dataclass(frozen=True, kw_only=True)
class AnchoredConfig(MachineConfig):
    anchor: AnchorConfig
    @property
    def capabilities(self) -> frozenset[str]: ...
    def create(self) -> Anchored: ...

class Anchored(MachineBase):
    def start(self) -> AnchorConfig: ...

# docker.py -- a container brought up for the agent, on a daemon here or elsewhere
CPUS: str      # the labels a container carries what it was given of its host under
MEMORY: str
GPUS: str
CDI: str       # the kind of device a GPU is handed out as by name: `nvidia.com/gpu`

@dataclass(frozen=True, kw_only=True)
class DockerConfig(MachineConfig):
    image: str = "python:3.12"
    workspace: str | None = None
    endpoint: str = "local"     # as `transport.Endpoint.parse` reads one
    name: str | None = None
    cpus: float | None = None
    memory: int | None = None   # bytes
    shm_size: int | None = None # bytes
    gpus: tuple[str, ...] | Literal["all"] = ()
    runtime: str | None = None
    network: str | None = None
    run_args: tuple[str, ...] = ()  # what else `docker run` is told, ahead of the image
    env: Mapping[str, str] = field(default_factory=dict[str, str])
    labels: Mapping[str, str] = field(default_factory=dict[str, str])
    @property
    def capabilities(self) -> frozenset[str]: ...
    def create(self) -> Docker: ...

class Docker(MachineBase):
    def __init__(self, config: DockerConfig) -> None: ...
    def start(self) -> AnchorConfig: ...
    def stop(self) -> None: ...

@dataclass(frozen=True, slots=True)
class Allocation:
    name: str
    cpus: float | None
    memory: int | None
    gpus: tuple[str, ...] | Literal["all"]
    labels: Mapping[str, str]

def allocations(
    endpoint: str = "local",
    labels: Mapping[str, str] | None = None,
    *,
    seconds: float | None = None,
) -> list[Allocation]: ...
def info(endpoint: str = "local", seconds: float | None = None) -> dict[str, Any]: ...
def gpus_listed(devices: Sequence[Any], kind: str = "") -> tuple[str, ...]: ...
USABLE_FOR: float  # how long one daemon's answer is kept, in seconds
def gpus_usable(
    endpoint: str,
    image: str,
    devices: Sequence[Any],
    *,
    seconds: float | None = None,
    fresh: bool = False,  # ask even where an answer is kept
) -> tuple[tuple[str, str], ...] | None: ...  # (name, uuid) of each GPU that answers
def whose(
    endpoint: Endpoint, image: str, workspace: str, told: Callable[[], Mapping[str, Any]]
) -> str: ...  # uid:gid a container given the workspace runs as
def bound(workspace: str) -> str: ...  # the `--mount` giving it at its own path

# swarm.py -- a container as the one task of a service, on whichever node of a swarm
class Unplaced(RuntimeError): ...  # no node took the task; the scheduler's words

@dataclass(frozen=True, kw_only=True)
class SwarmConfig(MachineConfig):
    image: str = "python:3.12"
    workspace: str              # absolute, as every node it may land on names it
    endpoint: str = "local"     # a manager, as `transport.Endpoint.parse` reads one
    name: str | None = None     # of the service
    user: str | None = None     # uid:gid, or None for the workspace's owner
    cpus: float | None = None   # reserved, and the limit
    memory: int | None = None   # bytes, likewise
    generic: tuple[tuple[str, int], ...] = ()  # generic resources reserved: (kind, count)
    constraints: tuple[str, ...] = ()           # each as `--constraint` takes it
    nodes: Mapping[str, str] = field(default_factory=dict[str, str])  # host name -> endpoint
    traced: bool = False        # CAP_SYS_PTRACE
    run_args: tuple[str, ...] = ()  # what else `docker service create` is told
    env: Mapping[str, str] = field(default_factory=dict[str, str])
    labels: Mapping[str, str] = field(default_factory=dict[str, str])
    placing: float = 30.0       # seconds a task may wait for a node with room
    starting: float = 600.0     # seconds it may take to run once it has one
    @property
    def capabilities(self) -> frozenset[str]: ...
    def create(self) -> Swarm: ...

@dataclass(frozen=True, slots=True)
class Node:
    id: str
    hostname: str
    address: str
    ready: bool       # ready, and neither drained nor paused
    cpus: float
    memory: int
    resources: Mapping[str, int]  # generic resources it advertises, by kind

@dataclass(frozen=True, slots=True)
class Placed:
    node: Node
    container: str
    daemon: Endpoint  # the daemon holding the container, as this machine reaches it

class Swarm(MachineBase):
    placed: Placed | None
    def __init__(self, config: SwarmConfig) -> None: ...
    def start(self) -> AnchorConfig: ...
    def stop(self) -> None: ...

def swarm_of(told: Mapping[str, Any], where: str) -> str: ...  # the manager's node id
def nodes(endpoint: str = "local", seconds: float | None = None) -> list[Node]: ...
def services(
    endpoint: str = "local",
    labels: Mapping[str, str] | None = None,
    *,
    seconds: float | None = None,
) -> list[Allocation]: ...

# mapped.py -- the workspace on that machine, as a flow's own Python reaches it
@dataclass(frozen=True, slots=True)
class Ran:
    argv: tuple[str, ...]
    status: int
    output: str
    @property
    def ok(self) -> bool: ...
    def __str__(self) -> str: ...

class Mapped:
    def __init__(self, anchor: AnchorConfig) -> None: ...
    @property
    def workspace(self) -> str: ...
    def read_text(self, path: str, encoding: str = "utf-8") -> str: ...
    def read_bytes(self, path: str) -> bytes: ...
    def write_text(
        self, path: str, said: str, encoding: str = "utf-8", mode: int | None = None
    ) -> None: ...
    def write_bytes(self, path: str, said: bytes, mode: int | None = None) -> None: ...
    def listdir(self, path: str = "") -> list[str]: ...
    def exists(self, path: str) -> bool: ...
    def mkdir(self, path: str, *, parents: bool = True) -> None: ...
    def remove(self, path: str) -> None: ...
    def run(
        self,
        argv: Sequence[str] | str,
        *,
        cwd: str = "",
        env: Mapping[str, str] | None = None,
    ) -> Ran: ...
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, *_why: object) -> None: ...
    def __iter__(self) -> Iterator[str]: ...  # iterating one lists the workspace

# store.py -- the runtimes: the machines an environment may be put on, under names
SSH = "ssh"
DOCKER = "docker"
SWARM = "swarm"
BACKENDS = (SSH, DOCKER, SWARM)
SELF = "self"  # an affinity's entry for a harness natively on the runtime's own machine
HERE = "local"  # and for one on this machine, anchored to it
TYPED = "typed"
IMPORTED = "imported"

@dataclass(frozen=True, slots=True, kw_only=True)
class SSHRuntime:
    backend: ClassVar[str] = SSH
    name: str
    host: str = ""
    user: str = ""
    port: int = 0
    identity_file: str = ""
    proxy_jump: str = ""
    options: Mapping[str, str] = {}  # each `-o KEYWORD=VALUE`
    alias: str = ""  # the `Host` it was imported as
    config: str = ""  # the ssh config it was imported from, where not the user's own
    workdir: str = ""
    fallback: tuple[str, ...] = ()  # each `<backend>:<name>`, tried in order
    made: str = TYPED
    affinity: tuple[str, ...] = ()  # where a harness of work on it runs, in the order tried
    @property
    def at(self) -> Path: ...
    def destination(self) -> str: ...
    def settings(self) -> tuple[tuple[str, str], ...]: ...  # as `Target.options` holds them
    def target(self) -> str: ...  # ssh://[user@]dest[:port][?KEYWORD=VALUE&...]
    def held(self) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True, kw_only=True)
class DockerRuntime:
    backend: ClassVar[str] = DOCKER
    name: str
    endpoint: str = "local"  # unix:///PATH, tcp://HOST:PORT, ssh://[USER@]HOST[:PORT],
                             # ssh:<ssh runtime>, context:<docker context>
    tls_dir: str = ""
    image: str = ""
    runtime: str = ""
    run_args: tuple[str, ...] = ()
    cpus: float = 0.0  # what it may hand out; 0 for all it has
    memory: int = 0
    gpus: tuple[str, ...] = ()
    gpu_memory: int = 0
    max_containers: int = 0
    workdir: str = ""
    fallback: tuple[str, ...] = ()
    made: str = TYPED
    affinity: tuple[str, ...] = ()
    @property
    def at(self) -> Path: ...
    def daemon(self) -> Endpoint: ...
    def held(self) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True, kw_only=True)
class SwarmRuntime:
    backend: ClassVar[str] = SWARM
    name: str
    endpoint: str = "local"  # a manager, spelled as a docker runtime's endpoint is
    tls_dir: str = ""
    image: str = ""
    run_args: tuple[str, ...] = ()  # what else `docker service create` is told
    cpus: float = 0.0  # what its tasks may reserve all told; 0 for what the nodes have
    memory: int = 0
    gpu_resource: str = ""  # the generic resource its nodes advertise GPUs as
    constraints: tuple[str, ...] = ()  # <attribute>==<value> or <attribute>!=<value>
    max_tasks: int = 0
    nodes: Mapping[str, str] = {}  # node host name -> ssh runtime name or [user@]host[:port]
    workdir: str = ""
    fallback: tuple[str, ...] = ()
    made: str = TYPED
    affinity: tuple[str, ...] = ()
    @property
    def at(self) -> Path: ...
    def daemon(self) -> Endpoint: ...
    def held(self) -> dict[str, Any]: ...

type Runtime = SSHRuntime | DockerRuntime | SwarmRuntime

def affine(entry: str) -> tuple[str, str] | None: ...  # (backend, name), None for self/local
def daemon_of(endpoint: str, tls_dir: str = "") -> Endpoint: ...
def node_of(via: str) -> str: ...  # ssh:<name> for a saved ssh runtime, else ssh://<via>
def under() -> Path: ...
def where(backend: str, name: str) -> Path: ...
def new(backend: str, name: str, **fields: Any) -> Runtime: ...
def runtimes(backend: str = "") -> list[Runtime]: ...
def find(backend: str, name: str) -> Runtime | None: ...
def fallbacks(backend: str, name: str) -> tuple[tuple[str, str], ...]: ...
SPELLING = 2  # what is kept says it spells an -e as -e does now
def respelled(spec: str) -> str: ...  # an -e kept the old way, as -e spells it now
def add(runtime: Runtime) -> Runtime: ...
def write(runtime: Runtime) -> Runtime: ...
def remove(backend: str, name: str) -> bool: ...
def imports(
    config: str | os.PathLike[str] | None = None,
    names: Iterable[str] | None = None,
    *,
    update: bool = False,
) -> list[SSHRuntime]: ...

# sshconfig.py -- the hosts an ssh config names, as ssh resolves them
@dataclass(frozen=True, slots=True)
class SSHHost:
    alias: str
    host: str
    user: str
    port: int
    identity_files: tuple[str, ...] = ()
    proxy_jump: str = ""

def default() -> Path: ...
def aliases(config: str | os.PathLike[str] | None = None) -> list[str]: ...
def resolve(
    destination: str, flags: Sequence[str] = (), *, alias: str = "", seconds: float = ...
) -> SSHHost: ...
def hosts(
    config: str | os.PathLike[str] | None = None, *, seconds: float = ...
) -> list[SSHHost]: ...
```

## Requirements

- `MachineConfig.capabilities` MUST be answerable without starting or reaching anything, and
  MUST name only words from `hmz.coganchor.places`; `create` MUST give every caller a machine
  of its own.
- `start` MUST leave the machine ready for turns and MUST take down whatever it created if it
  cannot; `stop` MUST leave the workspace behind and MUST do nothing for a machine nobody here
  brought up.
- `observe` MUST raise `OSError` where the machine cannot be reached or has not got the
  anchor's workspace, and `RuntimeError` naming the capability where it contradicts a platform
  its settings promised; `MachineBase.capabilities` MUST then be the declared names together
  with the observed ones.
- A machine that was already running MUST come to `remote` plus whatever its anchor declares
  and nothing else; a container MUST come to `remote`, `isolated`, `managed` and `linux`, MUST
  be given the project directory itself rather than a copy, and MUST run as the calling user
  where its daemon is this machine's -- as the container's own root where that daemon runs
  rootless, which is the calling user on the host.
- The project directory MUST be the path it has on the daemon's host, and MUST be refused
  rather than created where that host has none. On a daemon that is not this machine's --
  anything but a `unix://` socket, or docker's default where `DOCKER_HOST` does not send it
  elsewhere -- it MUST be asked for there, and the container MUST run as whoever owns it there.
- Every `docker` command for a container MUST reach the daemon its endpoint names, whatever the
  environment of the process asking, and the anchor `start` answers with MUST name that daemon
  in its target; a container `start` made MUST be given the serving half afresh, whatever one
  of its name held before, and `stop` MUST remove only the container docker said it made.
- A container MUST be given no more of its host's CPUs, memory and GPUs than its setting says,
  and no GPU but those -- none where it says none -- even from an image asking the daemon's
  runtime for every one. GPUs MUST be handed out by their CDI names where the daemon lists every
  one asked for, and by `--gpus` otherwise.
- What a container was given MUST be written on it under `CPUS`, `MEMORY` and `GPUS`, and those
  and `humanize` MUST NOT be taken from the caller's labels. `allocations` MUST read them back
  for every running container of humanize's on a daemon, whoever started it, MUST raise
  `OSError` rather than answer for a daemon it could not ask or that did not answer within
  `seconds`, and MUST read a label holding no number as saying nothing. `info` MUST raise
  `OSError` the same way, saying what the daemon said.
- A swarm's task MUST be the one replica of a service that is never restarted, created on the
  manager its endpoint names -- refused with `OSError` where that daemon manages no active
  swarm -- with the image, the workspace mounted at its own path, the user, the variables and
  the labels a container of one daemon is given, and with what it reserves of its node as its
  limits too. It MUST run as the calling user where the manager is this machine's, and as
  whoever owns the workspace on the manager's host otherwise, unless its setting says who.
- `start` MUST wait for the task to run: a task pending for want of a node MUST raise
  `Unplaced` with the scheduler's words at once where no node that may take a task has as much
  as it reserves, and once `placing` is over otherwise; one its node refused for want of the
  workspace MUST raise `FileNotFoundError`, and one that failed, or did not run within
  `starting`, `RuntimeError`. Whatever it raises, its service MUST be removed.
- The container of a running task MUST be reached through the daemon its setting names for the
  node's host, else the manager's own where the task landed on the manager, else over
  `ssh://<the node's address>`; and the anchor `start` answers with MUST name that daemon and
  that container. `stop` MUST remove the service, and only the one it created.
- `services` MUST read the labels back for every one of humanize's services on a swarm, as
  `allocations` does for containers, and `nodes` MUST say every node, ready only where it may
  be given a task; both MUST raise `OSError` for a manager they could not ask.
- `Mapped` MUST reach the machine down the same road a turn takes, and MUST take a path either
  as the machine names it or relative to the workspace.
- `Mapped.run` MUST answer with the exit status and everything written on both streams, MUST
  NOT pass this process's environment on, and MUST NOT report a command that ended without
  saying how as having succeeded.
- `Mapped.exists` MUST raise `OSError` where the machine cannot be reached at all rather than
  answering about the path; `close` MUST be safe to call more than once.

### Runtimes

- A runtime is a machine saved under a name -- an ssh host, a docker daemon or a docker swarm --
  that a flow's
  environment is put on when an `-e` names it. It MUST NOT be anything a flow sees: a flow's
  environments stay `Env`s whatever runtime they were put on.
- One runtime MUST be one directory under `~/.humanize/runtimes/<backend>/<name>/`,
  holding `runtime.json`, this user's alone at every level and written whole. The backend and
  the name MUST be where it is kept, whatever the file says.
- What was written down as environment providers, under `~/.humanize/env-providers/` in
  `provider.json`, MUST still be found: where `runtimes/` is not there, the first look for it
  MUST move `env-providers/` there whole, in one rename; a `provider.json` MUST be read where
  there is no `runtime.json`, and MUST be gone once that runtime is written again.
- A name MUST be one path component of letters, digits, dot, dash and underscore; anything else
  MUST be refused where it is given and MUST NOT be listed. A runtime that cannot be read, or
  that no runtime could be, MUST NOT be listed either.
- A runtime MUST be refused where it is made, not where it is used: an ssh runtime with
  neither a host nor an alias, a word `ssh` would read as an option, a setting it has a field
  for given as an option, a value of more than one line; a docker runtime with an endpoint
  that is none of the kinds, certificates for one that is not `tcp://`, or a negative amount;
  a swarm runtime with the same, or a constraint that compares nothing, a generic resource of
  no single word, or a node reached by neither a runtime's name nor an ssh destination;
  and any of them with an affinity entry that is none of `self`, `local` and
  `<backend>:<name>`, one named twice, or one naming the runtime itself, which is `self`; or
  with a fallback entry that is not `<backend>:<name>` of a backend there is and a name a
  runtime may have, one named twice, or one naming the runtime itself. An entry of either
  naming a runtime nobody saved MUST NOT be refused there: it is one with no room, or one that
  cannot hold the role, where it is used.
  `add` and `write` MUST refuse a config file or certificates under a home there is none of,
  and one written down before its home went MUST still be listed.
- `add` MUST refuse a name already taken and `write` MUST replace what was there; `new` MUST
  write nothing, and a runtime made again from what `held` wrote MUST be itself.
- Every field of an ssh runtime that is set MUST reach `ssh`, ahead of what humanize itself
  tells it, and an imported one MUST name its alias rather than what the alias resolved to, so
  that the config goes on being what it says. Nothing here MUST read or print what an identity
  file holds.
- `daemon_of` MUST be the one place a runtime's endpoint becomes an `Endpoint`, whose `docker`
  is the one place it becomes a command line; a daemon behind a saved ssh runtime MUST be
  dialled with everything that runtime says. A swarm's node named in its `nodes` MUST be
  reached as the saved ssh runtime of that name says where there is one, and as an ssh
  destination otherwise.
- `aliases` MUST follow every `Include` as ssh does and MUST NOT list a pattern; what a host
  resolves to MUST be asked of `ssh -G`. `imports` MUST leave a runtime already there unless
  told to update it, and MUST keep the workdir, the fallback list and the affinity of one it
  updates.
- A runtime's fallback list MUST be the runtimes an environment an `-e` puts on it moves to,
  in order, where it cannot hold it -- of any backend, whether or not they exist when the
  list is written -- and `fallbacks` MUST answer with that runtime's own list and nothing
  further: a runtime fallen back to is never walked on down its own.

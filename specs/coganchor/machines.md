# `coganchor/machines`

Where an agent's turns land -- a machine already running, or one brought up for the agent,
and what of its host it holds -- the workspace on it as a flow's own Python reaches it, and the
machines an environment may be put on, written down under names. It does not say how a turn
travels to a machine, which is the anchor's, and it runs no turns itself.

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

# store.py -- the machines an environment may be put on, under names
SSH = "ssh"
DOCKER = "docker"
BACKENDS = (SSH, DOCKER)
TYPED = "typed"
IMPORTED = "imported"

@dataclass(frozen=True, slots=True, kw_only=True)
class SSHProvider:
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
    made: str = TYPED
    @property
    def at(self) -> Path: ...
    def destination(self) -> str: ...
    def settings(self) -> tuple[tuple[str, str], ...]: ...  # as `Target.options` holds them
    def target(self) -> str: ...  # ssh://[user@]dest[:port][?KEYWORD=VALUE&...]
    def held(self) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True, kw_only=True)
class DockerProvider:
    backend: ClassVar[str] = DOCKER
    name: str
    endpoint: str = "local"  # unix:///PATH, tcp://HOST:PORT, ssh://[USER@]HOST[:PORT],
                             # ssh:<ssh provider>, context:<docker context>
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
    made: str = TYPED
    @property
    def at(self) -> Path: ...
    def daemon(self) -> Endpoint: ...
    def held(self) -> dict[str, Any]: ...

type EnvProvider = SSHProvider | DockerProvider

def daemon_of(endpoint: str, tls_dir: str = "") -> Endpoint: ...
def under() -> Path: ...
def where(backend: str, name: str) -> Path: ...
def new(backend: str, name: str, **fields: Any) -> EnvProvider: ...
def providers(backend: str = "") -> list[EnvProvider]: ...
def find(backend: str, name: str) -> EnvProvider | None: ...
def add(provider: EnvProvider) -> EnvProvider: ...
def write(provider: EnvProvider) -> EnvProvider: ...
def remove(backend: str, name: str) -> bool: ...
def imports(
    config: str | os.PathLike[str] | None = None,
    names: Iterable[str] | None = None,
    *,
    update: bool = False,
) -> list[SSHProvider]: ...

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
- `Mapped` MUST reach the machine down the same road a turn takes, and MUST take a path either
  as the machine names it or relative to the workspace.
- `Mapped.run` MUST answer with the exit status and everything written on both streams, MUST
  NOT pass this process's environment on, and MUST NOT report a command that ended without
  saying how as having succeeded.
- `Mapped.exists` MUST raise `OSError` where the machine cannot be reached at all rather than
  answering about the path; `close` MUST be safe to call more than once.

### Environment providers

- One provider MUST be one directory under `~/.humanize/env-providers/<backend>/<name>/`,
  holding `provider.json`, this user's alone at every level and written whole. The backend and
  the name MUST be where it is kept, whatever the file says.
- A name MUST be one path component of letters, digits, dot, dash and underscore; anything else
  MUST be refused where it is given and MUST NOT be listed. A provider that cannot be read, or
  that no provider could be, MUST NOT be listed either.
- A provider MUST be refused where it is made, not where it is used: an ssh provider with
  neither a host nor an alias, a word `ssh` would read as an option, a setting it has a field
  for given as an option, a value of more than one line; a docker provider with an endpoint
  that is none of the kinds, certificates for one that is not `tcp://`, or a negative amount.
  `add` and `write` MUST refuse a config file or certificates under a home there is none of,
  and one written down before its home went MUST still be listed.
- `add` MUST refuse a name already taken and `write` MUST replace what was there; `new` MUST
  write nothing, and a provider made again from what `held` wrote MUST be itself.
- Every field of an ssh provider that is set MUST reach `ssh`, ahead of what humanize itself
  tells it, and an imported one MUST name its alias rather than what the alias resolved to, so
  that the config goes on being what it says. Nothing here MUST read or print what an identity
  file holds.
- `daemon_of` MUST be the one place a provider's endpoint becomes an `Endpoint`, whose `docker`
  is the one place it becomes a command line; a daemon behind a stored ssh provider MUST be
  dialled with everything that provider says.
- `aliases` MUST follow every `Include` as ssh does and MUST NOT list a pattern; what a host
  resolves to MUST be asked of `ssh -G`. `imports` MUST leave a provider already there unless
  told to update it, and MUST keep the workdir of one it updates.

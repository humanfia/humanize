# `coganchor/machines`

Where an agent's turns land -- a machine already running, or one brought up for the agent,
and what of its host it holds -- and the workspace on it as a flow's own Python reaches it. It does not say how a turn travels
to a machine, which is the anchor's, and it runs no turns itself.

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
    endpoint: str = "local", labels: Mapping[str, str] | None = None
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
  `OSError` rather than answer for a daemon it could not ask, and MUST read a label holding no
  number as saying nothing.
- `Mapped` MUST reach the machine down the same road a turn takes, and MUST take a path either
  as the machine names it or relative to the workspace.
- `Mapped.run` MUST answer with the exit status and everything written on both streams, MUST
  NOT pass this process's environment on, and MUST NOT report a command that ended without
  saying how as having succeeded.
- `Mapped.exists` MUST raise `OSError` where the machine cannot be reached at all rather than
  answering about the path; `close` MUST be safe to call more than once.

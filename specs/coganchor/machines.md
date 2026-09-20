# `coganchor/machines`

Where an agent's turns land -- a machine already running, or one brought up for the agent --
and the workspace on it as a flow's own Python reaches it. It does not say how a turn travels
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

# docker.py -- a container brought up for the agent
@dataclass(frozen=True, kw_only=True)
class DockerConfig(MachineConfig):
    image: str = "python:3.12"
    workspace: str | None = None
    @property
    def capabilities(self) -> frozenset[str]: ...
    def create(self) -> Docker: ...

class Docker(MachineBase):
    def __init__(self, config: DockerConfig) -> None: ...
    def start(self) -> AnchorConfig: ...
    def stop(self) -> None: ...

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
  be given the project directory itself rather than a copy, and MUST run as the calling user.
- `Mapped` MUST reach the machine down the same road a turn takes, and MUST take a path either
  as the machine names it or relative to the workspace.
- `Mapped.run` MUST answer with the exit status and everything written on both streams, MUST
  NOT pass this process's environment on, and MUST NOT report a command that ended without
  saying how as having succeeded.
- `Mapped.exists` MUST raise `OSError` where the machine cannot be reached at all rather than
  answering about the path; `close` MUST be safe to call more than once.

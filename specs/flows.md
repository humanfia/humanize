# `flows`

The whole of what a flow imports: the mark that makes a function a flow, the marks an atlas
declares its graph with, the interfaces a flow drives, and a hand-through of everything else a
flow legitimately names. It is not where a flow is found, read, compiled or run.

## API

```python
# __init__.py -- the mark, and the one door onto what other layers write down
__all__ = [
    # the mark and what a flow says about itself
    "Flow", "flow",
    # the graph marks, re-exported from `atlas.py`
    "Atlas", "Kind", "Marked", "Sub", "atlas", "logic", "mind", "sub",
    # what a flow drives, re-exported from `agent.py`
    "Agent", "Driven", "Person", "Session",
    # the vocabulary a turn is described in, handed through from `hmz.coganchor`
    "EVERYWHERE", "PERMISSIONS", "SWARM", "UNSAID", "WINDOW",
    "AgentConfig", "AgentDefaults", "Allowance", "Board", "Budget", "Event",
    "Failed", "Goal", "Hook", "Hooks", "HumanAgent", "Hung", "Isolated", "Item",
    "Model", "Moment", "Needs", "Occasion", "Profile", "Question", "Refused",
    "Remote", "Stopped", "Tool", "Unhooked", "Unrecoverable", "Usage", "Verdict",
    "backends", "home", "models",
    # handed through from `hmz.runtime.flowing`, fetched only when a flow asks
    "NotAFlow", "Running", "container", "load", "running",
]

@dataclass(frozen=True, slots=True)
class Flow:
    name: str = ""
    about: str = ""
    skills: tuple[str, ...] = ()
    resumable: bool = False
    selectable: bool = True
    budget: Allowance | None = None

def flow[**P, T](
    call: Callable[P, T] | None = None,
    /,
    *,
    name: str = "",
    about: str = "",
    skills: Iterable[str] = (),
    resumable: bool = False,
    selectable: bool = True,
    budget: Allowance | None = None,
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]: ...

def __getattr__(name: str) -> object: ...

# agent.py -- what a flow drives, as protocols the drivers answer to structurally
class Session(Protocol):
    shapes: ClassVar[bool]
    takes_tools: ClassVar[bool]
    steers: ClassVar[bool]
    narrates: ClassVar[bool]
    @property
    def forks(self) -> bool: ...
    @property
    def id(self) -> str: ...
    @property
    def named(self) -> str | None: ...
    @property
    def cwd(self) -> str: ...
    @property
    def skills(self) -> tuple[str, ...]: ...
    @property
    def tools(self) -> tuple[Tool, ...]: ...
    effort: str    # property, settable
    budget: Budget | None    # property, settable
    def __call__[T: BaseModel](
        self, prompt: str, *, suppress: bool = False, schema: type[T] | None = None
    ) -> str | T | None: ...
    async def aturn[T: BaseModel](
        self, prompt: str, *, suppress: bool = False, schema: type[T] | None = None
    ) -> str | T | None: ...
    def pursue(self, objective: str, *, suppress: bool = False) -> str: ...
    async def apursue(self, objective: str, *, suppress: bool = False) -> str: ...
    def stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]: ...
    def fork(self) -> Session: ...
    def close(self) -> None: ...
    def offers(self, tools: Iterable[Tool] | None) -> None: ...
    def loads(self, skills: Iterable[str] | None) -> None: ...
    def interrupt(self, *, why: str) -> None: ...
    def interject(self, text: str) -> None: ...
    def steering(self, text: str, ticket: str = "") -> str: ...
    def took(self, ticket: str) -> str | None: ...
    def unsteered(self, text: str) -> None: ...
    def spent(self) -> Usage: ...
    def rate(self, over: float = WINDOW) -> Usage: ...
    def juice(self, over: float = WINDOW) -> float: ...

class Agent(Protocol):
    moments: ClassVar[frozenset[Moment]]
    pursues: ClassVar[bool]
    epic: Journal | None
    @property
    def id(self) -> str: ...
    @property
    def backend(self) -> str: ...
    @property
    def config(self) -> AgentConfig: ...
    @property
    def hooks(self) -> Hooks: ...
    @property
    def sessions(self) -> Sequence[Session]: ...
    @property
    def opened(self) -> list[str]: ...
    @property
    def stopped(self) -> bool: ...
    @property
    def goals_enabled(self) -> bool: ...
    @property
    def loaded(self) -> tuple[Loaded, ...]: ...
    effort: str    # property, settable
    def new(self, cwd: str | os.PathLike[str] | None = None) -> Session: ...
    def batch_new(
        self, count: int, cwd: str | os.PathLike[str] | None = None
    ) -> Sequence[Session]: ...
    def __call__[T: BaseModel](
        self,
        prompt: str,
        *,
        suppress: bool = False,
        schema: type[T] | None = None,
        cwd: str | os.PathLike[str] | None = None,
    ) -> str | T | None: ...
    async def aturn[T: BaseModel](
        self,
        prompt: str,
        *,
        suppress: bool = False,
        schema: type[T] | None = None,
        cwd: str | os.PathLike[str] | None = None,
    ) -> str | T | None: ...
    def pursue(
        self,
        objective: str,
        *,
        suppress: bool = False,
        cwd: str | os.PathLike[str] | None = None,
    ) -> str: ...
    async def apursue(
        self,
        objective: str,
        *,
        suppress: bool = False,
        cwd: str | os.PathLike[str] | None = None,
    ) -> str: ...
    def batch[T: BaseModel](
        self,
        prompts: Sequence[str],
        *,
        suppress: bool = False,
        schema: type[T] | None = None,
        at_once: int = 0,
        cwd: str | os.PathLike[str] | None = None,
    ) -> list[Any]: ...
    async def abatch[T: BaseModel](
        self,
        prompts: Sequence[str],
        *,
        suppress: bool = False,
        schema: type[T] | None = None,
        at_once: int = 0,
        cwd: str | os.PathLike[str] | None = None,
    ) -> list[Any]: ...
    def clone(
        self,
        *,
        config: AgentConfig | None = None,
        name: str | None = None,
        skills: Iterable[Loaded] | None = None,
    ) -> Agent: ...
    def watch(
        self, listener: Callable[[Agent, Session | None, Event], None]
    ) -> None: ...
    def stop(self) -> None: ...
    def asked(self, question: Question) -> str | None: ...
    def prompted(self) -> str | None: ...
    def spent(self) -> Usage: ...
    def rate(self, over: float = WINDOW) -> Usage: ...
    def juice(self, over: float = WINDOW) -> float: ...

class Driven(Agent, Protocol):
    def rename(self, name: str) -> None: ...
    def runs_on(self, machine: MachineConfig | None) -> None: ...
    def reconfigure(self, config: AgentConfig) -> None: ...
    def loads(self, skills: Iterable[Loaded]) -> None: ...
    def disable_goals(self) -> None: ...

class Person(Agent, Protocol):
    @property
    def board(self) -> Board: ...

# atlas.py -- the marks an atlas declares its graph with
type Kind = Literal["mind", "logic", "atlas"]

@dataclass(frozen=True, slots=True)
class Atlas:
    name: str = ""

@dataclass(frozen=True, slots=True)
class Marked:
    kind: Kind
    rerun: bool = True

@dataclass(frozen=True, slots=True)
class Sub:
    named: str    # calling one raises TypeError

def atlas[**P, T](
    call: Callable[P, T] | None = None,
    /,
    *,
    name: str = "",
    about: str = "",
    skills: Iterable[str] = (),
    selectable: bool = True,
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]: ...

def mind[**P, T](
    call: Callable[P, T] | None = None, /, *, rerun: bool = True
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]: ...

def logic[**P, T](
    call: Callable[P, T] | None = None, /, *, rerun: bool = True
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]: ...

def sub(named: str) -> Sub: ...
```

## Requirements

- MUST be the whole of what a flow imports; a flow MUST NOT have to name another `hmz` module.
- MUST make a function a flow only by marking it, MUST mark rather than wrap, and MUST take the flow's
  name from the mark and never from the function: unnamed is the flow a module holds under its own
  name, named is `<flow>:<name>`, and of two marked alike the first wins. `about` MUST default to the
  first line of the function's docstring, or of the module's for a module that holds one flow.
- MUST hand a `resumable` flow a dict as its last argument holding what it wrote there last time, MUST
  NOT hand one to any other flow, and MUST keep a `selectable=False` flow callable by name and out of
  every listing and picker.
- MUST treat `budget` as a default whoever starts the run may override rather than a cap the flow
  enforces, and MUST distinguish three states: unsaid, an `Allowance` with something in it, and
  `Allowance()` as a flow claiming it means to run under nothing at all.
- MUST cost no more than reading a directory to import: what is handed through MUST be fetched on
  attribute access and MUST be the same object its own layer holds, and an unknown name MUST raise
  `AttributeError`.
- MUST offer `Agent`, `Driven`, `Session` and `Person` as protocols the drivers answer to structurally
  without importing this package, and MUST keep off `Agent` and on `Driven` everything whoever hands
  an agent over settles.
- `Agent.clone` MUST answer with a second agent taking from this one everything the call does not name
  and carrying nothing this one accumulated; `Session.fork` MUST answer with a conversation carrying
  this one's history and costing on its own from there.
- MUST let a flow read off the class, before any agent is made, which moments a backend runs and
  whether it shapes, takes tools, steers, narrates, pursues or forks; what a backend cannot do MUST be
  refused where it is asked rather than faked. One vocabulary MUST name them: `goal`, `steer`,
  `shape`, `tools`, `fork`, `search`, `swarm`, `resume`, `moment:<name>`; `remote`, `isolated`,
  `managed`, `linux`, `darwin`; `anchor:<how>`.
- A turn cut off by `interrupt` MUST still answer once with what the agent got as far as saying;
  stopping the agent MUST instead prevent its next turn.
- What a flow declares about a place MUST only ever tighten what the agent already carries, MUST hold
  for no longer than the call, and declaring nothing MUST leave the agent exactly as it came.
- `builtin/` MUST hold `chat` and nothing else, and MUST be resolved as part of `official`.
- An atlas MUST be a flow in every way an ordinary flow is, MUST always be resumable, MUST NOT be
  handed a state dict, and MUST reach another atlas by `sub` and an ordinary flow by nothing at all.
- A `mind` MUST have exactly one way out and MUST be handed the agent its call site names; a `logic`
  MUST be handed no agent and MAY have several ways out; `rerun=False` MUST answer with nothing.

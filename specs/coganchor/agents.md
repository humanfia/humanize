# `coganchor/agents`

Drives coding agent CLIs as agents and holds the conversations they keep: one contract every
backend satisfies, and what a caller may put around a turn -- configuration, accounts, budgets
and allowances, hooks, skills, flow-written tools, a watchdog, a board and a name. It knows
nothing of flows or of runs, and MUST NOT import `hmz.flows` or `hmz.runtime`.

## API

```python
# __init__.py -- re-exports everything below, and:
DRIVEN: dict[str, tuple[type[AgentBase], type[AgentConfig]]]

def driver(backend: str) -> tuple[type[AgentBase], type[AgentConfig]]: ...

# base.py -- the contract every backend satisfies
WINDOW = 300.0

class Journal(Protocol):
    def opened(self, agent: AgentBase, session: str, parent: str = "") -> None: ...

class Meter:
    def spend(self, usage: Usage, now: float | None = None, *, turn: bool = True) -> None: ...
    def spent(self) -> Usage: ...
    def rate(self, over: float = WINDOW, now: float | None = None) -> Usage: ...
    def juice(self, over: float = WINDOW, now: float | None = None) -> float: ...

class SessionBase(ABC):
    shapes: ClassVar[bool] = False
    takes_tools: ClassVar[bool] = False
    steers: ClassVar[bool] = False
    narrates: ClassVar[bool] = False
    def __init__(self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None) -> None: ...
    @property
    def id(self) -> str: ...
    @property
    def named(self) -> str | None: ...
    @property
    def cwd(self) -> str: ...
    @property
    def forks(self) -> bool: ...
    @property
    def skills(self) -> tuple[str, ...]: ...
    @property
    def tools(self) -> tuple[Tool, ...]: ...
    @property
    def effort(self) -> str: ...
    @effort.setter
    def effort(self, effort: str) -> None: ...
    @property
    def budget(self) -> Budget | None: ...
    @budget.setter
    def budget(self, budget: Budget | None) -> None: ...
    def elsewhere(self) -> bool: ...
    # Overloaded: `str` where no schema is given, `T | None` where one is.
    def __call__[T: BaseModel](
        self, prompt: str, *, suppress: bool = False, schema: type[T] | None = None
    ) -> str | T | None: ...
    async def aturn[T: BaseModel](
        self, prompt: str, *, suppress: bool = False, schema: type[T] | None = None
    ) -> str | T | None: ...
    def stream(self, prompt: str, *, schema: type[BaseModel] | None = None) -> Iterator[Event]: ...
    def pursue(self, objective: str, *, suppress: bool = False) -> str: ...
    async def apursue(self, objective: str, *, suppress: bool = False) -> str: ...
    def interrupt(self, *, why: str) -> None: ...
    def interject(self, text: str) -> None: ...
    def steering(self, text: str, ticket: str = "") -> str: ...
    def took(self, ticket: str) -> str | None: ...
    def unsteered(self, text: str) -> None: ...
    def fork(self) -> SessionBase: ...
    def close(self) -> None: ...
    def loads(self, skills: Iterable[str] | None) -> None: ...
    def offers(self, tools: Iterable[Tool] | None) -> None: ...
    def spent(self) -> Usage: ...
    def rate(self, over: float = WINDOW) -> Usage: ...
    def juice(self, over: float = WINDOW) -> float: ...
    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]: ...  # abstract
    def _pursue(self, objective: str) -> str: ...  # optional: raises NotImplementedError here
    def _lets_go(self) -> None: ...  # optional: puts the transport down for the watchdog

class CommandSessionBase(SessionBase):
    protocol: ClassVar[bool] = False
    def _turn(self, prompt: str) -> tuple[list[str], str | None]: ...  # abstract
    def _read_session_id(self, transcript: str) -> str: ...  # abstract

class StreamSessionBase(SessionBase):
    def __init__(self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None) -> None: ...
    def _command(self) -> list[str]: ...  # abstract
    def _write(self, text: str, ticket: str = "") -> str: ...  # abstract
    def _read(self, line: str) -> Iterable[Event]: ...  # abstract
    def _restarted(self) -> None: ...  # optional: told a new process is up
    def _stale(self) -> bool: ...  # optional: whether to end the process before this turn

def identifying(config: type[AgentConfig], backend: str) -> dict[str, Any]: ...

class AgentBase(ABC):
    moments: ClassVar[frozenset[Moment]] = EVERYWHERE
    pursues: ClassVar[bool] = False
    spends: ClassVar[bool] = True
    service_tiers: ClassVar[tuple[str, ...]] = ("default",)
    rungs: ClassVar[tuple[str, ...]] = PERMISSIONS
    counts: ClassVar[frozenset[str]] = frozenset()
    def __init__(self, config: AgentConfig, *, name: str | None = None) -> None: ...
    @property
    def id(self) -> str: ...
    @property
    def backend(self) -> str: ...
    @property
    def spec(self) -> str: ...
    @property
    def config(self) -> AgentConfig: ...
    @property
    def sessions(self) -> list[SessionBase]: ...
    @property
    def opened(self) -> list[str]: ...
    @property
    def anchor(self) -> AnchorConfig | None: ...
    @property
    def provider(self) -> Provider | None: ...
    @property
    def toolbox(self) -> Toolbox: ...
    @property
    def hooks(self) -> Hooks: ...
    @property
    def loaded(self) -> tuple[Loaded, ...]: ...
    @property
    def stopped(self) -> bool: ...
    @property
    def watched(self) -> bool: ...
    @property
    def goals_enabled(self) -> bool: ...
    @property
    def effort(self) -> str: ...
    @effort.setter
    def effort(self, effort: str) -> None: ...
    def node(self) -> Provider: ...
    def walks(self) -> tuple[Provider, ...]: ...
    def stands_in(self) -> AgentBase | None: ...
    def new(self, cwd: str | os.PathLike[str] | None = None) -> SessionBase: ...  # abstract
    # Overloaded, as on a session: `str` where no schema is given, `T | None` where one is.
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
    def batch_new(
        self, count: int, cwd: str | os.PathLike[str] | None = None
    ) -> list[SessionBase]: ...
    def clone(
        self,
        *,
        config: AgentConfig | None = None,
        name: str | None = None,
        skills: Iterable[Loaded] | None = None,
    ) -> Self: ...
    def reconfigure(self, config: AgentConfig) -> None: ...
    def rename(self, name: str) -> None: ...
    def runs_on(self, machine: MachineConfig | None) -> None: ...
    def loads(self, skills: Iterable[Loaded]) -> None: ...
    def disable_goals(self) -> None: ...
    def fall_back(self, provider: Provider) -> None: ...
    def moved(self) -> None: ...
    def stop(self) -> None: ...
    def watch(
        self, listener: Callable[[AgentBase, SessionBase | None, Event], None]
    ) -> None: ...
    def asked(self, question: Question) -> str | None: ...
    def prompted(self) -> str | None: ...
    def environment(self) -> Mapping[str, str]: ...
    def hushed(self) -> frozenset[str]: ...
    def spawned(self, argv: list[str], cwd: str = "") -> list[str]: ...
    def spent(self) -> Usage: ...
    def rate(self, over: float = WINDOW) -> Usage: ...
    def juice(self, over: float = WINDOW) -> float: ...

# config.py -- how an agent is set up
PERMISSIONS = ("read-only", "workspace-write", "auto", "bypass")
UNSAID = ""
SERVICE_TIERS = ("default", "fast")
CUTOFFS = ("next-response", "immediately")
OUTCOMES = ("end", "fail")

class Unserved(ValueError):
    def __init__(self, said: str, *settings: str) -> None: ...

@dataclass(frozen=True, kw_only=True)
class AgentConfig:
    of_model: ClassVar[tuple[str, ...]] = ()
    model: str
    effort: str
    service_tier: str = "default"
    machine: MachineConfig | None = None
    permission: str = UNSAID
    provider: str = ""
    goals: bool = True
    web_search: bool | None = None
    budget: Budget | None = None

@dataclass(frozen=True, slots=True, kw_only=True)
class Budget:
    output: float = 0.0
    seconds: float = 0.0
    when: str = "next-response"
    then: str = "end"
    @property
    def bounded(self) -> bool: ...
    def over(self, *, output: float = 0.0, seconds: float = 0.0) -> str: ...

@dataclass(frozen=True, slots=True, kw_only=True)
class AgentDefaults:
    permission: str = UNSAID
    goals: bool = True
    web_search: bool | None = None
    insist: bool = True

class Goal:
    ...

class Remote:
    ...

@dataclass(frozen=True, slots=True)
class Isolated:
    image: str = "python:3.12"

@dataclass(frozen=True, slots=True, init=False)
class Needs:
    of_agent: frozenset[str]
    where: frozenset[str]
    def __init__(self, *of_agent: str, where: Sequence[str] = ()) -> None: ...

def rung(permission: str) -> str: ...

def tightest(was: str, said: str) -> str: ...

def searching(was: bool | None, said: bool | None) -> bool | None: ...

def anchored(target: str) -> MachineConfig | None: ...

def isolated(image: str, workspace: str | None = None) -> MachineConfig: ...

# event.py -- what a turn says as it says it
KINDS = ("input", "output", "cache_read", "cache_write", "reasoning")

class Usage(Mapping[str, float]):
    def __init__(self, kinds: Mapping[str, float] | None = None, /, **named: float) -> None: ...
    @property
    def input(self) -> float: ...
    @property
    def output(self) -> float: ...
    @property
    def total(self) -> float: ...
    def __getitem__(self, kind: str) -> float: ...
    def __iter__(self) -> Iterator[str]: ...
    def __len__(self) -> int: ...
    def __add__(self, other: Mapping[str, float]) -> Usage: ...
    def __truediv__(self, over: float) -> Usage: ...

@dataclass(frozen=True, slots=True)
class Event:
    kind: str
    text: str
    whose: str = ""
    tokens: Mapping[str, int] = field(default_factory=dict)
    spent: Usage = field(default_factory=Usage)

@dataclass(frozen=True, slots=True)
class Question:
    text: str
    options: tuple[str, ...] = ()

class Failed(subprocess.CalledProcessError):
    def __init__(
        self,
        returncode: int,
        cmd: Sequence[str],
        output: str | bytes | None = None,
        stderr: str | bytes | None = None,
        *,
        fault: str = "",
        fix: str = "",
    ) -> None: ...
    def reads(self) -> str: ...

class Unrecoverable(Failed):
    ...

class Stopped(Exception):
    ...

class Saying:
    def delta(self, kind: str, text: str, whose: str = "") -> None: ...
    def whole(self, kind: str, text: str, whose: str = "") -> None: ...
    def upto(self, whose: str = "") -> list[Event]: ...
    def ended(self, whose: str = "") -> list[Event]: ...
    def rest(self) -> list[Event]: ...

def say(text: str, sink: IO[str], *, end: str = "\n") -> None: ...

# hooks.py -- where a caller gets a word in
class Moment(StrEnum):
    SESSION_START = "SessionStart"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    PRE_TOOL_USE = "PreToolUse"
    SUBAGENT_START = "SubagentStart"
    SUBAGENT_STOP = "SubagentStop"
    PERMISSION_REQUEST = "PermissionRequest"
    NOTIFICATION = "Notification"
    STOP = "Stop"
    SESSION_END = "SessionEnd"

EVERYWHERE: frozenset[Moment]  # every moment but the three a backend must say it reaches
SUBAGENTS: frozenset[Moment]  # SUBAGENT_START and SUBAGENT_STOP

type Hook = Callable[[Occasion], Verdict | None]

class Unhooked(ValueError):
    ...

@dataclass(frozen=True, slots=True)
class Occasion:
    moment: Moment
    agent: str
    session: str = ""
    prompt: str = ""
    tool: str = ""
    about: str = ""
    under: str = ""
    input: Mapping[str, Any] = field(default_factory=dict)
    said: str = ""
    again: int = 0

@dataclass(frozen=True, slots=True)
class Verdict:
    refused: bool = False
    because: str = ""
    adds: str = ""

class Hung:
    def off(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

class Hooks:
    def __init__(self, moments: frozenset[Moment], agent: str) -> None: ...
    @property
    def moments(self) -> frozenset[Moment]: ...
    def on(self, moment: Moment, hook: Hook, *, tool: str = "") -> Hung: ...
    def off(self, hung: Hung) -> None: ...
    def hooked(self, moment: Moment) -> bool: ...
    def gated(self, moment: Moment) -> bool: ...
    def gate(self) -> Gate: ...
    def fire(self, occasion: Occasion) -> Verdict: ...

class Gate:
    moments: ClassVar[frozenset[Moment]] = frozenset({Moment.PRE_TOOL_USE})
    def __init__(self, hooks: Hooks) -> None: ...
    def address(self) -> str: ...
    def command(self) -> list[str]: ...
    def table(self, wait: int) -> dict[str, Any]: ...
    @property
    def serving(self) -> bool: ...
    def close(self) -> None: ...

def about(called: Mapping[str, Any]) -> str: ...

def arriving(partial: str) -> str: ...

def answers(line: str, hooks: Hooks) -> str: ...

# allowance.py -- what a whole run may spend
MILLION = 1_000_000.0
KEY = "budget"
FIELDS = ("hours", "tokens", "dollars")

@dataclass(frozen=True, slots=True, kw_only=True)
class Allowance:
    hours: float = 0.0
    tokens: float = 0.0
    dollars: float = 0.0
    @property
    def bounded(self) -> bool: ...
    def over(
        self, *, seconds: float = 0.0, output: float = 0.0, dollars: float | None = None
    ) -> str: ...

DEFAULT: Allowance

@dataclass(frozen=True, slots=True, kw_only=True)
class Reading:
    seconds: float
    output: float
    dollars: float | None
    floor: bool
    blind: frozenset[str]

class Ledger:
    def __init__(self, allowance: Allowance, agents: Iterable[AgentBase] = ()) -> None: ...
    @property
    def allowance(self) -> Allowance: ...
    @property
    def began(self) -> float: ...
    @property
    def spent(self) -> bool: ...
    def enrol(self, agent: AgentBase) -> None: ...
    def agents(self) -> tuple[AgentBase, ...]: ...
    def reads(self) -> Reading: ...
    def over(self) -> str: ...
    def stops(self) -> None: ...

def written(said: object, where_: str = "") -> Allowance: ...

def allowed(
    given: Allowance | Mapping[str, object] | None, declared: Allowance | None
) -> Allowance: ...

def blinded(allowance: Allowance, models: Iterable[str], *, counting: bool) -> frozenset[str]: ...

def unreadable(blind: Iterable[str]) -> str: ...

def unwatched(
    effective: Allowance, declared: Allowance | None, blind: Iterable[str] = ()
) -> bool: ...

# board.py -- what a flow and the person at the prompt both write on
ANYONE = "both"
USER = "user"
FLOW = "flow"
WHOSE = (ANYONE, USER, FLOW)

class Refused(PermissionError):
    ...

@dataclass(frozen=True, slots=True)
class Item:
    key: str
    value: str = ""
    about: str = ""
    whose: str = ANYONE
    at: float = field(default_factory=time.monotonic)
    by: str = FLOW
    def writable(self, by: str) -> bool: ...

class Board:
    def __init__(self, items: Iterable[Item] = ()) -> None: ...
    def items(self) -> tuple[Item, ...]: ...
    def get(self, key: str, otherwise: str = "") -> str: ...
    def held(self, key: str) -> Item | None: ...
    def put(
        self,
        key: str,
        value: str,
        *,
        about: str | None = None,
        whose: str | None = None,
        by: str = FLOW,
    ) -> Item: ...
    def drop(self, key: str, *, by: str = FLOW) -> bool: ...
    def moves(self, key: str, *, to: str, by: str = FLOW) -> Item: ...
    def watch(self, listener: Callable[[Board], None]) -> None: ...

# skills.py -- what a flow brings, and where a backend reads it
SKILLS = "skills"
CARD = "SKILL.md"

@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    about: str
    whose: str

@dataclass(frozen=True, slots=True)
class Loaded:
    name: str
    at: Path
    whose: str = ""

@dataclass(frozen=True, slots=True)
class Mounted:
    at: tuple[Path, ...] = ()

def skills(backend: str, where: Path | str | None = None) -> list[Skill]: ...

def mount(backend: str, workspace: Path | str, loaded: Iterable[Loaded]) -> Mounted: ...

def carried(backend: str, loaded: Iterable[Loaded]) -> tuple[tuple[str, str], ...]: ...

def unmount(one: Mounted) -> None: ...

# tools.py -- tools the flow wrote, offered to a backend that takes them
PROTOCOL = "2025-06-18"

@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    about: str
    call: Callable[..., Any]
    takes: type[BaseModel] | None = None
    def schema(self) -> dict[str, Any]: ...
    def called(self, given: Mapping[str, Any]) -> str: ...

class Toolbox:
    def offers(self, whose: int, tools: Iterable[Tool]) -> None: ...
    def offered(self) -> tuple[Tool, ...]: ...
    def empty(self) -> bool: ...
    def address(self) -> str: ...
    def command(self) -> list[str]: ...
    def config(self, named: str = "humanize") -> dict[str, Any]: ...
    def close(self) -> None: ...

def serve(line: str, offered: Callable[[], tuple[Tool, ...]]) -> dict[str, Any] | None: ...

# watchdog.py -- a context manager round a blocking read
class Watchdog:
    def __init__(
        self,
        session: SessionBase,
        *,
        riding: Callable[[], subprocess.Popen[str] | None] | None = None,
        window: float | None = None,
    ) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...
    def saw(self) -> None: ...
    @contextlib.contextmanager
    def held(self) -> Generator[None]: ...
    def wedged(self) -> Failed | None: ...

def silence(backend: str) -> float: ...

@contextlib.contextmanager
def held(agent: AgentBase) -> Generator[None]: ...

# codenames.py -- what an agent nobody named is called
def codename() -> str: ...

# preload/ -- the CLI's own work, reported as a moment
RUNTIME = "runtime.cjs"

class Watch:
    def __init__(self, hooks: Hooks) -> None: ...
    def address(self) -> str: ...
    def tells(self, line: str) -> None: ...
    def close(self) -> None: ...

def runtime() -> str: ...

def preloaded(agent: AgentBase, added: Mapping[str, str]) -> dict[str, str]: ...

def reported(line: str) -> tuple[str, str] | None: ...

# human.py -- the person at the prompt
class HumanSession(SessionBase):
    def stream(self, prompt: str, *, schema: type[BaseModel] | None = None) -> Iterator[Event]: ...

class HumanAgent(AgentBase):
    moments: ClassVar[frozenset[Moment]] = frozenset()
    spends: ClassVar[bool] = False
    def __init__(self, *, name: str = "human") -> None: ...
    @property
    def board(self) -> Board: ...
    def new(self, cwd: str | os.PathLike[str] | None = None) -> HumanSession: ...

# acp.py -- a CLI somebody added, driven by the Agent Client Protocol and nothing else
@dataclass(frozen=True, slots=True)
class McpServer:
    name: str
    command: str
    args: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    def sent(self) -> dict[str, Any]: ...

@dataclass(frozen=True, kw_only=True)
class AcpAgentConfig(AgentConfig):
    cli: str = ""
    command: tuple[str, ...] = ()
    reads_files: bool = False
    writes_files: bool = False
    terminals: bool = False
    mcp_servers: tuple[McpServer, ...] = ()

class AcpSession(SessionBase):
    ...

class AcpAgent(AgentBase):
    def new(self, cwd: str | os.PathLike[str] | None = None) -> AcpSession: ...

# agy.py / claude.py / codex.py / cursor.py / dsh.py / grok.py / kimi.py / mimo.py /
# opencode.py / pi.py / qwen.py / zcode.py -- one backend apiece, each the same three
# classes under the CLI's own name and paired in `DRIVEN`: `ClaudeCodeAgentConfig`,
# `ClaudeCodeSession`, `ClaudeCodeAgent`.
@dataclass(frozen=True, kw_only=True)
class BackendAgentConfig(AgentConfig):
    ...

class BackendSession(CommandSessionBase):
    ...

class BackendAgent(AgentBase):
    moments: ClassVar[frozenset[Moment]]
    pursues: ClassVar[bool]
    spends: ClassVar[bool]
    service_tiers: ClassVar[tuple[str, ...]]
    rungs: ClassVar[tuple[str, ...]]
    counts: ClassVar[frozenset[str]]
    def new(self, cwd: str | os.PathLike[str] | None = None) -> BackendSession: ...
```

## Requirements

- `DRIVEN` MUST name every backend driven here under the name a command line calls it; `driver`
  MUST also answer for a CLI somebody added that speaks the Agent Client Protocol, and MUST
  raise `KeyError` for a name nothing drives.
- An `AgentConfig` MUST be frozen and MUST refuse a permission rung, service tier or budget word
  that has no name here; an agent MUST be refused a config its backend cannot express
  (`Unserved`) before its first turn rather than part way through one.
- What is true of a CLI rather than of driving it -- forking, resuming, web search, hook tables,
  preloads, bundle fingerprints -- MUST be read off `hmz.coganchor.backends`, not declared here.
- `AgentBase.id` MUST be the name given, else a codename nothing else in the process answers to;
  `rename` MUST take a name only for an agent that was not named where it was made.
- `new` MUST open a session rooted at the directory given, and every turn of it MUST run there;
  a directory that is not there, or one outside an anchored agent's workspace, MUST be refused
  before the turn.
- `__call__` and `pursue` MUST each be one turn in a session nothing keeps; every call that runs
  a turn MUST have an awaited twin, and `batch`/`abatch` MUST take a session apiece and answer in
  the order asked.
- `clone` MUST answer with a second agent of the same backend differing only in config, name and
  carried skills: it MUST have opened no conversation, spent nothing, be watched by nobody, have
  nothing hung on its moments, and MUST NOT be stopped for the original having been -- but it
  MUST spend out of the run's allowance.
- `reconfigure` MUST take hold from the next turn, MUST leave the turn under way as it started,
  and MUST NOT change which backend the agent is.
- `opened` MUST report the backend's id of every session this agent opened, oldest first,
  including ones nobody holds any more, and MUST NOT count one whose first turn failed.
- `anchor` MUST be where this agent's turns land, brought up at most once and only when first
  asked, taken down when the agent is collected or the process exits, and `None` for an agent
  given no machine.
- A watcher MUST be told which session said a thing, and `None` only for something the agent
  itself said; one that raises MUST NOT take the turn down and MUST NOT be swallowed in silence,
  and what is reported MUST name the kind lost without repeating what was said.
- `asked` MUST answer `None` where there is nobody to ask rather than leave the backend waiting;
  `prompted` MUST answer `None` once there will be nothing more, and MUST raise `Stopped` for an
  agent stopped while it waited.
- `stream` MUST be the one primitive and MUST end with exactly one `result` event; `__call__`
  MUST answer with what that event carries, so a turn read either way is the same turn.
- A turn that fails MUST raise `subprocess.CalledProcessError` whatever it ran through, carrying
  why: both streams where they differ, each clipped.
- `suppress` MUST catch a failed turn and nothing else -- not `Stopped`, not `Unrecoverable`, not
  a feature the backend has not got; a turn asked for a shape that answered in another MUST be
  caught by it and MUST answer `None` rather than `""`.
- A turn given a `schema` MUST answer with that model or not at all, MUST ask afresh on every turn
  of the model the call takes, and MUST keep the schema out of what hooks and watchers are shown.
- `interrupt` MUST end the turn now running and whatever it started, MUST say why, MUST NOT end
  the conversation, and MUST leave a session with no turn running alone. The turn MUST still end
  on exactly one `result` or one failure carrying what was said so far, and MUST NOT be taken
  again; a backend with nowhere to take the asking MUST raise `NotImplementedError`.
- `interject` MUST reach the turn already under way rather than queue another, MUST raise
  `NotImplementedError` where the backend takes its whole prompt up front and `RuntimeError` where
  no turn is running; `steers` MUST be true only where the word reaches the running turn.
- A session MUST run under its agent's budget unless told otherwise, MUST take being told while it
  is running, and MUST leave the turn under way on the budget it opened with. A budget MUST be
  held to off the live meter so a turn is cut off mid-turn, a cap on the clock MUST bite whether
  or not anything is being spent, and a cut-off MUST win over a hook that would send the agent on.
- Every session of every backend MUST be held to the run's allowance, with no way for a driver or
  a flow to opt out, read at both edges of a turn and again as the session closes. A turn asked
  for under a spent allowance MUST raise `Stopped` -- not wait, not answer with nothing, and ahead
  of any check on whether the agent was stopped -- and the turn that spends the last of it MUST
  still answer with what it said.
- A session MUST take one turn at a time, the moments it fires included.
- `fork` MUST be a second conversation carrying this one's history as of the call, with its own id,
  meter and place in `opened`, unopened with the backend until its first turn; it MUST raise
  `NotImplementedError` where the backend has no fork of its own and `RuntimeError` before any turn
  has landed, and MUST NOT hand back a second handle on one conversation.
- `pursue` MUST be the backend's own goal feature, followed across every turn it takes, and MUST
  raise `NotImplementedError` where there is none rather than asking in the prompt.
- `loads` MUST take hold from the next turn, a session told nothing MUST carry every skill the flow
  brought, and a name the flow does not bring MUST be ignored rather than refused.
- Every read a turn blocks on MUST be under a `Watchdog`, so a backend that stops answering without
  exiting fails rather than hangs; every step of a recovery MUST narrate itself as an event, and go
  on stderr where nothing is watching the agent.
- What a turn says MUST reach a watcher as whole utterances rather than as the fragments they
  arrived in, and MUST NOT be said twice.
- Every backend MUST provide an `AgentConfig` subclass, an `AgentBase` subclass whose `new` opens
  its session, and a session derived from `CommandSessionBase` where a turn is one run of a
  command, `StreamSessionBase` where one process is held open across a session's turns, or
  `SessionBase` where it is neither. It MUST declare truthfully what driving it comes to -- its
  moments, goal feature, service tiers, rungs, token kinds and whether it spends -- and MUST meet
  the whole session contract above or raise `NotImplementedError` for a feature its CLI lacks.
- A concrete backend MUST implement exactly the members marked `# abstract` above -- `_stream`
  on `SessionBase`, `_turn` and `_read_session_id` on `CommandSessionBase`, `_command`,
  `_write` and `_read` on `StreamSessionBase`, and `new` on `AgentBase` -- and MUST be asked
  for nothing else: everything else on the base classes is provided, the members marked
  `# optional` included, which a backend MAY override where its CLI needs it and otherwise
  leaves as they are.
- A command turn MUST tee both of the agent's streams as they arrive, and a sink that has gone away
  MUST NOT take the turn down or stop the reading; a held-open process MUST NOT outlive its
  session, and an anchored session MUST end its process each turn and resume on the turn after.
- A driver MUST NOT switch a skill of its CLI on or off and MUST NOT write the CLI's own settings;
  a reopened transport MUST resume the conversation by the id the backend gave it.
- A hook MUST be hangable on a moment and takeable off again, and a moment the agent does not reach
  MUST be refused (`Unhooked`) where the hook is hung; a refusal MUST stop the thing only where the
  backend asks first, and MUST be readable as a report where it does not.
- Tools the flow wrote MUST be offered only to a backend that takes them and MUST NOT require the
  caller to run a server of its own; skills MUST reach a session by being mounted where that
  backend reads them, settled as a turn opens rather than moved under a running turn.
- The board MUST never hold up a reader or a writer, MUST refuse a write by the side a line is not,
  MUST keep what a line is for across a change of value, MUST say when a line moves, and MUST
  answer a read with one whole copy.
- The preload MUST cost nothing where nothing is hung on the moment it feeds, MUST be off for a
  turn that lands on another machine, MUST fail open and never hold a turn up, and MUST report the
  CLI's own work and nothing else, as `PreToolUse` named for what the runtime did and not refusable.
- `codename` MUST NOT hand the same name out twice in one process, and MUST stay readable however
  many it has handed out.
- The person at the prompt MUST be outside every allowance and budget, MUST NOT be among the agents
  a flow is configured with, and MUST answer with nothing rather than leave a flow waiting where
  nobody is there.

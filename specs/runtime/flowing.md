# `runtime/flowing`

Everything humanize does *to* a flow: finding one and listing them all, loading one by its ref,
running it over drivers, and the drivers themselves. A flow never imports this; what a flow
writes against is `hmz.flows` (see [flows.md](../flows.md)), whose `flow`, `load` and
`Outworlder.new` hand their calls to the engine here. Nothing here drives a coding agent
itself: the harness drivers are written against `hmz.coganchor`.

## API

```python
# spi.py -- what a driver and the engine promise each other
AGENT_CAPABILITIES: frozenset[type]  # every agent mixin of hmz.flows
ENV_CAPABILITIES: frozenset[type]  # every behaviour mixin of an environment
HARNESS_CAPABILITIES: Mapping[HarnessKind, frozenset[type]]  # read off HARNESS_AGENTS
def capabilities_of(declared: type) -> frozenset[type]: ...
@dataclass(frozen=True, slots=True)
class Placement:
    backend: EnvBackendKind
    provider: str
    workdir: PurePosixPath
    machine: MachineConfig | None = None
@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    at: Path
@dataclass(frozen=True, slots=True)
class Limits:
    cost: float | None = None
    output_tokens: int | None = None
    deadline: float | None = None  # time.monotonic()
    graceful: bool = True
@dataclass(frozen=True, slots=True)
class TurnRequest:
    prompt: str
    output_schema: type[BaseModel] | None = None
    limits: Limits = Limits()
class UsageSink(Protocol):
    def add(self, *, cost: float, output_tokens: int, duration: float) -> None: ...
type BoundHook = Callable[[SessionHandle, dict[str, Any]], Awaitable[HookResult]]
def default_result(kind: HookKind) -> HookResult: ...
class HookTable:  # set / get / `in` / async fire(kind, handle, /, **fields)
class HookBridge:  # here() / call(make, *, default) / abandon() / close()
class SessionHandle(Protocol): ...  # id, usage, turn, steer, interrupt, close
class AgentDriver(Protocol): ...  # harness, model, effort, provider, capabilities, open, close
class EnvDriver(Protocol): ...  # backend, provider, workdir, capabilities, resources, exec,
                               # read, write, derive_*, destroy_*, placement, close
class OutworlderDriver(Protocol): ...  # away, run

# specs.py -- what -a, -e, -p and -b say
@dataclass(frozen=True, slots=True)
class AgentSpec: ...  # role, harness, provider, model, effort, cli
@dataclass(frozen=True, slots=True)
class EnvSpec: ...  # role, backend, provider, workdir
def parse_agents(values: Sequence[str]) -> list[AgentSpec]: ...
def parse_envs(values: Sequence[str]) -> list[EnvSpec]: ...
def parse_params(values: Sequence[str]) -> dict[str, str]: ...
def parse_budget(values: Sequence[str]) -> Budget: ...
def parse_duration(text: str) -> timedelta: ...

# engine.py -- defining, loading and running flows
DEPTH = 64
class FlowImpl:  # answers to hmz.flows.Flow
    fn: Callable[..., Coroutine]
    name: str
    description: str | None
    hidden: bool
    resumable: bool
    ref: str  # canonical: "<module>:<name>", the module a flow directory's own
    home: FlowModule | None
    def describe(self) -> Declaration: ...
    def declared(self) -> tuple[tuple[AgentRole, ...], tuple[EnvRole, ...]]: ...
    def params_of(self, params: object) -> FlowParams: ...
    async def __call__(self, task, *, agents, envs, params, budget=None) -> Any: ...
class Call:  # one flow call; answers to hmz.flows.FlowContext and is its `ctx`
    run: Run
    parent: Call | None
    impl: FlowImpl | None  # None for the run's own call above the top
    depth: int
    since: float
    deadline: float
    state: FlowStateImpl | None
@dataclass(frozen=True, slots=True)
class LiveCall:
    ref: str
    name: str
    depth: int
    since: float
    id: int  # its journal id, or 0
    parent: LiveCall | None
class Recorder(Protocol):
    def entered(self, call: LiveCall) -> None: ...
    def left(self, call: LiveCall, error: BaseException | None) -> None: ...
    def spawned(self, call: LiveCall, role: str, session: SessionHandle,
                driver: AgentDriver) -> None: ...
def define_flow(fn, *, agents, envs, params, name, description, hidden, resumable,
                caller_globals, caller_locals) -> Flow: ...
def load_flow(ref: str, *, caller_globals: Mapping[str, Any]) -> Flow: ...
def new_outworlder() -> Outworlder: ...
def full_view(flow: Flow) -> Flow: ...  # chat's: every capability of each harness
def running() -> tuple[LiveCall, ...]: ...
def current() -> Call | None: ...
async def run_flow(
    flow: Flow,
    task: str,
    *,
    agents: Mapping[str, AgentDriver],
    envs: Mapping[str, EnvDriver],
    params: FlowParams | Mapping[str, Any],
    budget: Budget,
    outworlder: OutworlderDriver | None = None,
    journal: Path | None = None,
    resume: bool = False,
    local: EnvDriver | None = None,  # fills LocalEnv roles; local_env(cwd) by default
    recorder: Recorder | None = None,
) -> Any: ...

# declaring.py -- what a flow declares, resolved
@dataclass(frozen=True, slots=True, eq=False)
class Grant:
    capabilities: frozenset[type]
    permission: Permission
    skills: tuple[str, ...]
@dataclass(frozen=True, slots=True, eq=False)
class AgentRole:
    name: str
    declared: type
    required: bool
    auto: bool  # an Outworlder
    harness: HarnessKind | None
    capabilities: frozenset[type]
    permission: Permission
    skills: tuple[str, ...]
    grant: Grant
@dataclass(frozen=True, slots=True, eq=False)
class EnvRole:
    name: str
    declared: type
    required: bool
    auto: bool  # a LocalEnv
    capabilities: frozenset[type]
    cpu_count: int
    memory: int
    gpu_count: int
    gpu_memory: int
    grant: Grant
    resources: bool
@dataclass(frozen=True, slots=True, eq=False)
class Declaration:
    name: str
    ref: str
    description: str | None
    hidden: bool
    resumable: bool
    agents: tuple[AgentRole, ...]
    envs: tuple[EnvRole, ...]
    params: type[FlowParams]
    def agent(self, name: str) -> AgentRole | None: ...
    def env(self, name: str) -> EnvRole | None: ...

# viewing.py -- what a flow is handed
CALLING: ContextVar[Call | None]
class AgentView: ...  # answers to Agent, every agent mixin and every harness protocol
class SessionView: ...  # answers to Session
class EnvView: ...  # answers to Env, LocalEnv and every environment mixin
class OutworlderView: ...  # answers to Outworlder

# journaling.py -- what a resumable run writes down
def digest(ref: str, task: str, roles: list[str], params: bytes) -> str: ...
class Journal:  # opened(path, loop, *, resume) -> (Journal, Past | None); close()
class Past: ...
class FlowStateImpl: ...  # answers to FlowState

# loading.py -- what a ref names
class Ref:
    url: str | None
    rev: str | None
    where: str
    sub: str
def parse(ref: str) -> Ref: ...
class FlowModule:
    at: Path
    entry: Path
    name: str
    module: ModuleType
    claims: tuple[str, ...]
    pins: int
    def flows(self) -> dict[str, FlowImpl]: ...
def module_of(entry: Path, run: Run | None) -> FlowModule: ...
def pick(module: FlowModule, sub: str, ref: str) -> FlowImpl: ...
class Remote: ...  # a flow of another flowverse, fetched when first called
def pinned(url: str, rev: str | None) -> Path: ...

# fakes.py -- in-memory drivers, for testing a flow
class FakeAgentDriver: ...  # (harness, *, reply, model, effort, provider, capabilities,
                            #  cost, output_tokens, seconds, forks)
class FakeSession: ...  # until_steered, tool, ask, notify, subagent
class FakeEnvDriver: ...  # (files, *, workdir, backend, provider, capabilities, cpu_count,
                          #  memory, gpu_count, gpu_memory, run, refs, repo)
class FakeOutworlder: ...  # (reply, *, away)
async def run_fake(flow: Flow | str, task: str = "", *, agents=None, envs=None,
                   params=None, budget=None, outworlder=None, local=None,
                   journal=None, resume=False, recorder=None) -> Any: ...

# verses.py -- where flows come from
OFFICIAL = "official"
LOCAL = "local"
USER = "user"
FLOWS = "flows"  # the directory a flowverse offers its flows under
MINE: dict[str, str]  # LOCAL and USER, by where each is kept
@dataclass(frozen=True, slots=True)
class Flowverse:
    name: str
    url: str
    at: Path
    fetched: bool  # whether it is a clone rather than a directory of this machine's own
    fixed: bool  # whether it is one of the three that cannot be removed
def flowverses() -> list[Flowverse]: ...  # the order they are offered in
def nearest() -> list[Flowverse]: ...  # the order a name is looked up in
def named(name: str) -> Flowverse | None: ...
def where(name: str) -> Path: ...
def under() -> Path: ...  # where the fetched ones are kept
def holds(one: Flowverse) -> tuple[Path, ...]: ...  # the directories its flows are in
def flows(one: Flowverse) -> list[str]: ...
def add(url: str, name: str = "") -> Flowverse: ...
def fetch(name: str) -> Flowverse: ...
def remove(name: str) -> bool: ...
def clone(url: str, at: Path) -> None: ...
def refresh(at: Path) -> None: ...
def edited(at: Path) -> bool: ...
def standing(at: Path) -> str: ...
def plain(url: str) -> str: ...  # a URL with whatever was signed into it taken out

# finding.py -- which flow a name means
BUILTIN_AT: Path  # where humanize's own flows are: hmz/flows/builtin
ENTRY = "__init__.py"  # what a flow's own directory is entered by
class Offer(NamedTuple):
    whose: str  # the flowverse it comes from
    name: str
    about: str = ""
def found() -> list[Offer]: ...
def offers(one: Flowverse) -> list[Offer]: ...
def offered(under: Path) -> list[str]: ...
def entry(under: Path, name: str) -> Path | None: ...
def within(one: Flowverse, name: str) -> Path | None: ...
def find(named_: str) -> str: ...  # what runs
def at(named_: str) -> str: ...  # its own directory, or ""
def inside(named_: str) -> str: ...  # which of the flows a module holds
def about(named_: str) -> str: ...
def resolved(named_: str) -> FlowImpl: ...  # the flow a way in runs, loaded
def builtin(flow: FlowImpl) -> bool: ...  # whether humanize ships it
def fork(named_: str, into: str | os.PathLike[str] | None = None) -> str: ...

# skills.py -- what a flow brings its agents; `CARD`, `SKILLS` and `Loaded` come from
# `hmz.coganchor.agents.skills` and are offered again here
def brought(at: Path | str, declared: Iterable[str] = ()) -> list[Loaded]: ...
def cached(url: str) -> Path: ...
def fetched(url: str) -> Path: ...
def under() -> Path: ...
```

## Requirements

### Defining a flow

- `define_flow` MUST refuse, with `FlowDefinitionError`, a function that is not `async`, one
  that cannot be called with a task and the keywords `agents`, `envs`, `params` and `ctx`,
  collections that are not `AgentCollection`/`EnvCollection` subclasses, params that are not
  a `FlowParams` subclass, and a name a ref could not name. A flow's name MUST default to the
  function's, and its description to the first line of its docstring.
- `define_flow` MUST NOT resolve a collection's annotations: they MUST be resolved the first
  time the flow is called or described, against the namespaces the decorator captured, so
  that collections and types declared inside a function, and annotations written as strings,
  resolve. `NotRequired`, `Required`, `ReadOnly` and `Annotated` MUST be read through, and
  `__extra_items__` MUST NOT be relied on.
- A role's type MUST be read once per type: its capabilities (a mixin's bases with it), its
  `_permission` and `_skills` for an agent, its resources for an environment, the harness a
  harness protocol names, and whether the runtime fills it -- an `Outworlder`, a `LocalEnv`.
  A type no agent or environment can be MUST raise `FlowDefinitionError`.

### Calling a flow

- A call MUST do no filesystem work, start no task, and add at most two frames to the stack.
  The flow MUST be awaited directly, and the call it runs under MUST be a context variable
  set and reset with a token.
- Flows MUST NOT be called more than `DEPTH` deep; the call that would be MUST raise
  `FlowDepthExceeded`, never a bare `RecursionError`. A flow called outside every run MUST
  raise `FlowRuntimeError`.
- Before the callee runs, a call MUST refuse what does not meet its declaration: a required
  role left out (`MissingRole`), an agent or environment lacking a declared mixin
  (`CapabilityMissing`), an agent holding a narrower permission (`PermissionTooNarrow`), a
  machine short of a declared resource (`ResourceUnmet`), and another harness for a role typed
  as one (`HarnessMismatch`). A refusal for one kind of agent MUST be worked out once.
- An `Outworlder` role left out MUST be the run's own outworlder, and one given `Outworlder.new()`
  that one. A `LocalEnv` role left out MUST be the run's workspace, and one given an
  environment on another machine MUST be refused with `CapabilityMissing`.
- Params MUST be taken as they are when they are the callee's own class, and validated
  otherwise -- from another model, or a mapping whose string values are read as the fields'
  types or as JSON -- raising `ParamsError` when they do not validate.
- Whatever the callee raises MUST reach the caller as it was raised.

### Views

- A flow MUST be handed views -- `AgentView`, `EnvView`, `OutworlderView`, `SessionView` --
  answering to every protocol and mixin of `hmz.flows` structurally, holding `__slots__`, and
  deriving from none of them. What a view grants MUST be exactly what its role declared: a
  `/goal` or `/loop` prompt, `steer`, a hook of a mixin, a script `exec`, files, worktrees,
  temporary copies and scratch directories MUST each raise `CapabilityNotGranted` without the
  mixin for them. Only a flow marked with `full_view` MUST be granted its harness's all.
- `derive` MUST only narrow: a permission the grant covers, skills the grant names. An agent
  derived from another MUST share its hooks and its sessions.
- A hook MUST be called with the context of the flow the agent belongs to and the session the
  moment arrived in, and MUST run as that flow. What it raises MUST fail the turn it arrived
  in. A callee's hooks MUST NOT be heard by its caller's sessions, nor the other way round.
- A session MUST take one turn at a time and belong to the agent that opened it. A turn
  cancelled MUST interrupt the session.
- An outworlder that is away MUST answer `""` for text, the schema built from its defaults
  where every field has one, and `OutworlderAway` otherwise. One made with `Outworlder.new()`
  MUST be away until a hook is hung on it with `on_outworlder_run`.

### Budgets and usage

- A call's budget MUST be the tighter of its own and what remains of every budget above it.
  Cost, output tokens and turn time MUST roll up to every call above as a driver reports them,
  from any thread, under one lock per run; `Usage` and `Budget` MUST be built only when read.
- A spent budget MUST stay spent: every later turn under it MUST raise the `BudgetExceeded`
  leaf for it. Each turn MUST be handed the `Limits` every budget over it leaves.
- `duration` MUST be a deadline per call, not a sum over concurrent children. A call whose own
  deadline passes MUST be stopped -- after the turns under way under it finish where its
  budget is graceful -- and MUST raise `DurationExceeded` where it is stopped; a cancel from
  outside MUST stay a cancel.

### Resuming

- A run MUST keep a journal only where its flow is resumable and it was given one: one file of
  JSON lines, appended to while the run goes, holding `call`, `set`, `del`, `end`, `session`
  and `tmp` records. A state write MUST be flushed as it is made; everything else MAY be
  batched, for no longer than a tenth of a second. The journal MUST be synced as the run ends.
- A call's digest MUST cover the callee's canonical ref, the task, each role's agent (harness,
  account, model, effort, permission, skills) or environment (how it was derived from what a
  command line named, never a path), and the params.
- Resuming MUST compact the journal first. The flow at the top MUST pick up unconditionally;
  a call under one that picked up MUST pick up the earlier call with its digest and the lowest
  `seq` not yet claimed, and start afresh otherwise. A flow that is not resumable MUST pass
  resumption through to its callees, and MUST have no state.
- `FlowState` MUST refuse what JSON cannot hold with `StateNotSerializable`, and MUST keep what
  JSON gives back, so that a fresh run and a resumed one read the same.

### Refs and loading

- `load` MUST take `:<sub>` relative to the flow asking, `<flow>` and `<flow>:<sub>` from the
  flowverse the flow asking is in, and `git+<url>[@<ref>]#<flow>[:<sub>]`; where no flow is
  asking, `<flowverse>/<flow>[:<sub>]`, a name nearest first, and a path. A relative ref with
  nothing to be relative to MUST raise `FlowRefError`, as MUST anything that is no ref.
- A bare `<flow>` MUST be the flow named after its directory, else the only visible flow of its
  module, and otherwise MUST raise `FlowNotFound` naming the flows there are. A module's flows
  MUST be only those defined inside its directory, and two of one name MUST raise
  `FlowDefinitionError`.
- A flow directory MUST be imported as a module named after it where that name is free, with
  its directory on `sys.path` so that what it keeps beside its entry point imports by a plain
  name. Nothing a run uses MAY be taken out of `sys.modules` while it goes; two checkouts
  claiming one name while a run uses one of them MUST raise `FlowLoadConflict`. A module whose
  files changed MUST be imported afresh by the next run nobody else is running it in, and a run
  MUST import a module at most once, however often it loads its flows.
- A VCS ref MUST be fetched once per URL and ref per run, on a thread, pinned to the commit it
  stands at, and cloned once per commit. What cannot be fetched MUST raise `FlowNotFound`.
- A role's skills MUST be found in its flow's own `skills/` or fetched, at the call, raising
  `FlowDefinitionError` for one that is not there.

### Cleanup and the running tree

- Sessions a call opened MUST be closed, and the temporary copies and scratch directories it
  made removed, when the call and every call it started are over; a resumable run that keeps a
  journal MUST keep its directories and write them down instead. Removing MUST be shielded from
  cancellation and limited in time. `run_flow` MUST close whatever it opened.
- A session MUST also be closed as soon as nothing can reach it -- where only a reference cycle
  holds it, as soon as a collection finds it -- however long its call goes on: the engine MUST
  hold a `SessionView` only weakly, so that a flow opening a fresh session a round holds a
  bounded number open however many rounds it runs, on fakes that never let the loop go on too.
  A session let go of MUST be closed on the run's loop, whichever thread let go of it, and
  exactly once however that races its call's end; the call's cleanup MUST wait for a close
  still under way. A hook arriving for a session let go of and not yet closed -- its
  `SESSION_END` among them -- MUST be handed a stand-in that is over, never the view that went.
  A fork MUST keep the session it was forked from open until its own first turn, which is
  where a harness cuts it.
- A call whose caller has ended MUST raise `FlowCancelled` at its next operation.
- `running` MUST answer with every call going now, and nothing of a call once it has ended.

### Fakes

- The fakes MUST keep every promise `spi` makes of a driver, and MUST be held to
  `tests/flows/contracts.py` like any other driver.

### Where flows come from

- Every flow MUST be listable under one name apiece -- humanize's own by a bare name, every
  other as `<flowverse>/<name>`; the flow a bare name means under its module's own name and
  every other visible flow of the module as `<name>:<inside>`, a hidden one not at all -- and
  a name MUST resolve nearest first: this project's flows, then yours, then the rest. A name
  qualified by a flowverse MUST NOT be stood in for, and a path MUST be taken outright. A
  module that will not import MUST still be listed, under its name.
- `resolved` MUST load what a way in names -- a name, `<flowverse>/<flow>`, either with
  `:<inside>`, a path, or a VCS ref, fetched on the calling thread -- MUST say so where a
  name nothing answers to could have come from a flowverse not fetched yet, and MUST mark the
  flows humanize ships with `full_view`; nothing else is.
- `brought` MUST bring the flow's own skills first and the ones it named after, the flow's own
  winning a shared name, and MUST raise where one cannot be fetched rather than at the turn.
- `fork` MUST copy the whole of a flow and MUST refuse a name already taken rather than write
  over it; forking, and adding, fetching or removing a flowverse, MUST leave nothing half-done
  behind when it fails, and `official`, `local` and `user` MUST NOT be removable.
- Every name above MUST be fetched only when it is named, so that listing flows costs nothing
  that reading or driving one does. Nothing here MAY be imported by `hmz.flows` at import, or
  drive an agent.

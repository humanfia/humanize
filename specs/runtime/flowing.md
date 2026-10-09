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
@dataclass(frozen=True, slots=True)
class Kept: ...  # harness, id, at: a conversation a session kept, copied
class SessionHandle(Protocol): ...  # id, usage, keep, turn, move, steer, interrupt, close
class AgentDriver(Protocol): ...  # harness, model, effort, provider, capabilities, open, close
class EnvDriver(Protocol): ...  # backend, provider, workdir, capabilities, resources, exec,
                               # read, write, derive_*, destroy_*, snapshot, rewind,
                               # snapshots, placement, close
class OutworlderDriver(Protocol): ...  # away_for(role), run(prompt, schema, role)

# specs.py -- what -a, -e and -p say, the budget among them
@dataclass(frozen=True, slots=True)
class AgentSpec: ...  # role, harness, provider, model, effort, cli
@dataclass(frozen=True, slots=True)
class EnvSpec: ...  # role, backend, provider (a saved runtime's name, an ssh host in
                    # brackets, or "" for this machine), workdir
BUDGET = "budget"   # the param a run's budget is given as, a limit apiece; no flow's
def parse_agents(values: Sequence[str]) -> list[AgentSpec]: ...
def parse_envs(values: Sequence[str]) -> list[EnvSpec]: ...
def fallbacks(spec: EnvSpec) -> list[EnvSpec]: ...  # what its saved runtime falls back to
def parse_params(values: Sequence[str]) -> dict[str, str]: ...  # the flow's, budget.* not
def parse_budget(values: Sequence[str]) -> Budget | None: ...  # every -p budget.<limit>=
def parse_duration(text: str) -> timedelta: ...
def where(backend: str, provider: str, workdir: str | PurePosixPath = "") -> str: ...  # as -e
def spelled(backend: str, provider: str, workdir: str | PurePosixPath = "") -> str: ...
    # where a driver is, as -e spells it: what its machine calls itself, respelled

# harnesses.py -- the agent drivers
def open_agent(spec: AgentSpec, harbors: Harbors | None = None) -> HarnessDriver: ...

# affinity.py -- where a harness runs
def affinity_of(runtime: Runtime | None) -> tuple[str, ...]: ...  # its own, () for none
class Harbors:  # one run's: affinity(placement), async machine(entry), async close()

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
    task: str = ""
    resumable: bool = False
class Recorder(Protocol):
    def began(self, spent: Callable[[], Usage]) -> None: ...  # the run's own reckoning
    def entered(self, call: LiveCall) -> None: ...
    def left(self, call: LiveCall, error: BaseException | None) -> None: ...
    def spawned(self, call: LiveCall, role: str, session: SessionHandle,
                driver: AgentDriver) -> None: ...
    def named(self, call: LiveCall, role: str, session: SessionHandle,
              driver: AgentDriver) -> None: ...  # a session its CLI named after it opened
    def closed(self, session: SessionHandle) -> None: ...
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
    image: str  # a container env's, or "" for its provider's
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
SESSIONS = "sessions"  # beside the journal: what sessions in state are kept beside

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
class Remote: ...  # a flow of a repository, fetched when first called
def pinned(url: str, rev: str | None) -> Path: ...  # machine()/pinned/<url>/<commit>

# fakes.py -- in-memory drivers, for testing a flow
class FakeAgentDriver: ...  # (harness, *, reply, model, effort, provider, capabilities,
                            #  cost, output_tokens, seconds, forks, names_late)
class FakeSession: ...  # until_steered, tool, ask, notify, subagent
class FakeEnvDriver: ...  # (files, *, workdir, backend, provider, capabilities, cpu_count,
                          #  memory, gpu_count, gpu_memory, run, refs, repo)
class FakeOutworlder: ...  # (reply, *, away)
async def run_fake(flow: Flow | str, task: str = "", *, agents=None, envs=None,
                   params=None, budget=None, outworlder=None, local=None,
                   journal=None, resume=False, recorder=None) -> Any: ...

# verses.py -- where flows come from: an index's clone, or a directory of your own
OFFICIAL = "official"
LOCAL = "local"
USER = "user"
FLOWS = "flows"  # the directory an index keeps `[<user>/]<flow>/<version>/flow.yaml` under
INDEX = "index"  # the clone of a flowverse's index, inside where(name)
INSTALLED = "installed"  # what was installed out of it, beside INDEX
MINE: dict[str, str]  # LOCAL and USER, by where each is kept
AT = "@"  # what a name of any flowverse's but official's starts with
OWNER: re.Pattern[str]  # a GitHub user, in lower case: what an index lists flows under
@dataclass(frozen=True, slots=True)
class Flowverse:
    name: str
    url: str
    at: Path  # the index's clone, where(name)/INDEX, or your own directory
    fetched: bool  # whether its index is cloned; true for a directory of this machine's own
    fixed: bool  # whether it is one of the three that cannot be removed
def flowverses() -> list[Flowverse]: ...  # the order they are offered in
def nearest() -> list[Flowverse]: ...  # the order a name is looked up in
def named(name: str) -> Flowverse | None: ...
def where(name: str) -> Path: ...  # under()/<name>: its index's clone, and what was installed
def under() -> Path: ...  # where every flowverse is kept
def holds(one: Flowverse) -> tuple[Path, ...]: ...  # the directories its flows are run from
def flows(one: Flowverse) -> list[str]: ...
def add(url: str, name: str = "") -> Flowverse: ...
def fetch(name: str) -> Flowverse: ...
def remove(name: str) -> bool: ...
def clone(url: str, at: Path) -> None: ...
def refresh(at: Path) -> None: ...
def edited(at: Path) -> bool: ...
def standing(at: Path) -> str: ...
def plain(url: str) -> str: ...  # a URL with whatever was signed into it taken out
def pathed(said: str) -> bool: ...  # whether it starts with `.`, `/` or `~`
def spelled(flow: str | os.PathLike[str]) -> str: ...  # as -f takes it; a PathLike always a path
def called(verse: str, flow: str) -> str: ...  # `aot`, `alice/kernel`, `@theirs/alice/kernel`
def split(name: str) -> tuple[str, str]: ...  # a name, to its flowverse and what that lists it as
def renamed(name: str) -> str: ...  # a name said as before the `@`, as it is said now

# index.py -- what an index lists, and the flows installed out of one
RELEASE = "flow.yaml"  # one release: flows/[<user>/]<flow>/<version>/flow.yaml
RECORD = ".installed.json"  # what an installed flow's directory says it was installed from
RESERVED: frozenset[str]  # the builtins' names, which nothing listed bare may take
OURS = "humanfia"  # whose flows official lists bare, and never a user
class Release(BaseModel):  # frozen; keys it does not know are let through unread
    name: str  # [a-z][a-z0-9_]*, the directory it is in
    version: str  # SemVer, the directory it is in
    description: str = ""
    repo: str  # owner/repo on GitHub, or a URL git fetches
    ref: str = ""  # what it was cut from, for the reader
    commit: str  # 40 hex: what is installed
    subdir: str = ""  # where in the repository the flow is; "" for its root
    license: str = ""
    dependencies: dict[str, str] = {}  # flows of the same index, as it lists them, to ranges
    owner: str = ""  # the user it is listed under, set by where it is; "" for one listed bare
    @property
    def listed(self) -> str: ...  # `<flow>`, or `<owner>/<flow>`
    @property
    def owned(self) -> str: ...  # who owns its repository on GitHub, or ""
    @property
    def semver(self) -> semver.Version: ...
    @property
    def url(self) -> str: ...
class Skipped(NamedTuple):
    at: Path
    why: str
class Index(NamedTuple):
    verse: str
    releases: tuple[Release, ...] = ()  # by what it lists each as, newest first
    skipped: tuple[Skipped, ...] = ()
    def flows(self) -> list[str]: ...  # `aot`, `alice/kernel`
    def versions(self, flow: str) -> list[Release]: ...
    def release(self, flow: str, version: str) -> Release | None: ...
    def newest(self, flow: str, spec: str = "") -> Release | None: ...
class Installed(BaseModel):
    verse: str
    name: str
    version: str
    commit: str
    repo: str
    ref: str = ""
    subdir: str = ""
    dependencies: dict[str, str] = {}
    skills: dict[str, list[str]] = {}  # each URL its roles name, to what was fetched into it
    owner: str = ""
    @property
    def listed(self) -> str: ...  # what its index lists it as
    @property
    def called(self) -> str: ...  # what it is offered under
    @property
    def at(self) -> Path: ...  # kept(verse)/[<owner>/]<name>
class Update(NamedTuple):
    installed: Installed
    version: str
def reserved() -> frozenset[str]: ...
def kept(verse: str) -> Path: ...  # where(verse)/INSTALLED
def satisfies(version: str, spec: str) -> bool: ...
def index(one: Flowverse | str) -> Index: ...
def installed(verse: str = "") -> list[Installed]: ...
def updates() -> list[Update]: ...
def plan(verse: str, flow: str, version: str = "") -> list[Release]: ...
def install(verse: str, flow: str, version: str = "") -> list[Installed]: ...
def uninstall(verse: str, flow: str) -> bool: ...

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
def privileged(flow: FlowImpl) -> bool: ...  # whether it is the package's own `chat`
def fork(named_: str, into: str | os.PathLike[str] | None = None) -> str: ...

# skills.py -- what a flow brings its agents; `CARD`, `SKILLS` and `Loaded` come from
# `hmz.coganchor.agents.skills` and are offered again here
def brought(at: Path | str, declared: Iterable[str] = ()) -> list[Loaded]: ...
def cached(url: str) -> Path: ...
def fetched(url: str) -> Path: ...
def named(at: Path) -> list[str]: ...  # the URLs a flow's source names skills by
def packed(at: Path) -> dict[str, list[str]]: ...  # those fetched into its own `skills/`
def remote(said: str) -> bool: ...  # whether a skill a role names is a URL
def under() -> Path: ...  # machine()/skills
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
  `_permission` and `_skills` for an agent, its resources and `_image` for an environment, the
  harness a
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
  (`CapabilityMissing`, which MUST say so where it is `GitEnvMixin` on a machine seen to have
  no `git` on its PATH), an agent holding a narrower permission (`PermissionTooNarrow`), a
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
  snapshots, temporary copies and scratch directories MUST each raise `CapabilityNotGranted`
  without the mixin for them -- `GitEnvMixin` for snapshots, `RewindableEnvMixin` granting
  nothing by itself. Only a flow marked with `full_view` MUST be granted its harness's all.
- `derive` MUST only narrow: a permission the grant covers, skills the grant names. An agent
  derived from another MUST share its hooks and its sessions.
- A hook MUST be called with the context of the flow the agent belongs to and the session the
  moment arrived in, and MUST run as that flow. What it raises MUST fail the turn it arrived
  in. A callee's hooks MUST NOT be heard by its caller's sessions, nor the other way round.
- A session MUST take one turn at a time and belong to the agent that opened it. A turn
  cancelled MUST interrupt the session.
- A session MUST be only its conversation: `spawn` and `fork` MUST take no environment and
  start no CLI, and each turn MUST work where `run` is given -- the run's own workspace where
  it is given None. A session's driver session MUST be opened as its first turn goes, there,
  and the engine MUST start holding it, and tell the recorder of it, only then; before each
  later turn it MUST be moved to where that turn works, and the recorder told of it again
  where the move made it a conversation of another id. A fork MUST be refused with
  `SessionError` when its session has taken no turn, and at its first turn when that session
  has taken one since.
- An outworlder that is away MUST answer `""` for text, the schema built from its defaults
  where every field has one, and `OutworlderAway` otherwise. One made with `Outworlder.new()`
  MUST be away until a hook is hung on it with `on_outworlder_run`.
- The run's own outworlder MUST be asked, and asked whether it is away, as the `Outworlder` role
  the run filled with it, which a flow handing it on under another name MUST NOT change.

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
  A `session` record MUST carry the id the CLI gave the session, written once the turn that
  named it reports what it spent, and no later than that turn's end.
- A call's digest MUST cover the callee's canonical ref, the task, each role's agent (harness,
  account, model, effort, permission, skills) or environment (how it was derived from what a
  command line named, never a path), and the params.
- Resuming MUST compact the journal first. The flow at the top MUST pick up unconditionally;
  a call under one that picked up MUST pick up the earlier call with its digest and the lowest
  `seq` not yet claimed, and start afresh otherwise. A flow that is not resumable MUST pass
  resumption through to its callees, and MUST have no state.
- `FlowState` MUST refuse what JSON cannot hold with `StateNotSerializable`, and MUST keep what
  JSON gives back, so that a fresh run and a resumed one read the same.
- A session written into a call's state MUST be one of that call's agents', and MUST have its
  conversation copied as the write is made -- by its driver, only that conversation's files,
  into a directory of its own under `sessions/<cli>/.kept/` beside the journal, or under a
  temporary directory removed with a run that keeps none -- and refused (`StateNotSerializable`) before
  anything is written down where it has taken no turn, a turn of it is under way, it is over,
  or its harness cannot fork, keeps it on another machine, or keeps it as no files. Each read
  of it MUST be a new session of the call's agent of its role, whose first turn opens it as a
  fork of that copy: refused there, before the harness is started or anything is copied, where
  the harness did not keep it, cannot fork, or the turn works on another machine, and where
  the copy is gone or the run holds a different copy of the conversation already; until a turn
  has named it, a move MUST cut it from that copy again. One read back and written again
  before a turn MUST be written down as what it carries on, copying nothing.

### Refs and loading

- `load` MUST take `:<sub>` relative to the flow asking, `<flow>` and `<flow>:<sub>` from the
  directory of flows the flow asking is in -- and, for a flow installed out of an index,
  `<flow>` and `<user>/<flow>` from the flows installed out of that index, as it lists them --
  and `git+<url>[@<rev>][#<subdir>][:<sub>]` -- the flow in `<subdir>` of the repository, its
  root where there is none, as an index's manifest says it; and else, as where no flow is
  asking, `[@<flowverse>/][<user>/]<flow>[:<sub>]` and a path, which MUST be what starts with
  `.`, `/` or `~` and nothing else. A relative ref with nothing to be relative to MUST raise
  `FlowRefError`, as MUST anything that is no ref -- a name of a part too many among them.
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
  stands at, and cloned once per commit into this machine's own directory rather than
  humanize's home. What cannot be fetched MUST raise `FlowNotFound`.
- A role's skills MUST be found in its flow's own `skills/` or fetched, at the call, raising
  `FlowDefinitionError` for one that is not there; a URL wanting one skill the flow has one of
  its own of MUST be given the flow's. An installed flow's MUST be read out of
  its own `skills/`, where installing it put the ones its roles name by a URL, and MUST NOT be
  fetched again; a flow that was never installed MUST fetch them into `machine()/skills/`, and
  nothing of a skill MAY be kept under humanize's home outside the flow it came with.

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

### Docker environments

- A `docker` environment MUST be a container of its own per environment a run is given, on the
  daemon its provider names -- `local` being docker's default here where no provider is written
  down under that name -- and everything derived from it MUST be in that container. It MUST be
  started from the role's `_image`, else the provider's, else `python:3.12-slim`, with the
  workdir -- a directory of the daemon's host -- mounted at its own path, and nothing needed in
  the image but `/bin/sh` and a Python of at least 3.12; an sshd MUST NOT be.
- It MUST be given exactly the CPUs, memory and GPUs its role declares as hard limits, no GPU
  where it declares none and no limit on what else it declares none of, and the provider's
  runtime and arguments; it MUST be labelled with its provider, role, host and process beside
  what it holds, and its driver MUST report what it was given.
- Before any agent starts, what the role asks MUST be held against what its provider may hand
  out -- what it was written down with, the daemon's own where that is 0 -- less what that
  provider's running containers hold, and its container limit; GPUs MUST be the first ids
  nobody holds of those its daemon's host says answer where it can be asked, handed out by
  the CDI name each answered under or else its UUID, and GPU memory the provider's where it
  says it. What is short MUST raise `ResourceUnmet` saying how much of what is free and which
  container holds the rest -- for GPUs, how many of those listed are usable --, and no two
  runs on this machine MUST work it out for one provider at once.
- An agent working in one MUST be anchored to its container, reaching it by `docker exec` alone,
  its harness put where the next section says: supervised on this machine in a mirror of its
  own, or the container's own CLI driven natively.
- Its container MUST be taken down when the environment is closed, and one whose process on
  this host has gone MUST be taken down by the next run on its provider.

### Swarm environments

- A `swarm` environment MUST be the one task of a service of its own per environment a run is
  given, on the swarm whose manager its provider names -- `local` being the swarm this machine
  manages where no provider is written down under that name -- never restarted, and everything
  derived from it MUST be in that task's container. It MUST be created from the role's
  `_image`, else the provider's, else `python:3.12-slim`, with the workdir -- a directory of
  whichever node it lands on, at the same path on every one it may -- mounted at its own path,
  and with nothing needed in the image but what a docker environment needs.
- It MUST reserve exactly the CPUs and memory its role declares and be limited to them, and as
  many of its provider's GPU generic resource as the role declares GPUs, none where it declares
  none; it MUST be placed under its provider's constraints and created with its arguments, and
  labelled as a docker environment's container is; its driver MUST report what it reserved.
- Before any agent starts, what the role asks MUST be held against what its provider may hand
  out -- its task limit, and the CPUs and memory it was written down with where it was -- less
  what that provider's services hold, and a role asking for GPUs of a provider naming no GPU
  resource MUST be refused; what is short MUST raise `ResourceUnmet` saying how much is free
  and which service holds the rest, and no two runs on this machine MUST work it out for one
  provider at once. A task no node takes for want of room MUST raise `ResourceUnmet` with the
  scheduler's words -- at once where no node that may take a task could ever hold it, and
  once a bounded wait is over otherwise -- and its service MUST be removed. A manager that
  manages no active swarm, and a node without the workdir, MUST raise `EnvUnavailable`.
- An agent working in one MUST be anchored to its container by `docker exec` against the daemon
  of the node it landed on: the one its provider names for that node's host where it names one,
  else the manager's own where it landed on the manager, else that node's over ssh to its
  address; everything downstream of that MUST be as it is for a docker environment.
- Its service MUST be removed when the environment is closed, and one whose process on this
  host has gone MUST be removed by the next run on its provider.

### Apple container environments

- An `apple-container` environment MUST be a container of Apple's `container` of its own per
  environment a run is given, on this Mac -- as the runtime its provider names shares it out,
  `local` being this Mac's with nothing written down under that name -- and everything derived
  from it MUST be in that container. It MUST be started from the role's `_image`, else the
  provider's, else `python:3.12-slim`, with the workdir -- a directory of this Mac -- mounted at
  its own path, and with nothing needed in the image but what a docker environment needs.
- It MUST be given exactly the CPUs and memory its role declares as its size, `container`'s
  own where it declares none, and the provider's arguments; it MUST be labelled as a docker
  environment's container is; its driver MUST report what it was given. A role declaring GPUs
  MUST raise `ResourceUnmet`, a container being given none.
- Before any agent starts, what the role asks MUST be held against what its provider may hand
  out -- what it was written down with, the Mac's own where that is 0 -- less what that
  provider's running containers hold, each its virtual machine's size, and its container
  limit; what is short MUST raise `ResourceUnmet` as for a docker environment, and no two runs on this machine MUST work it
  out for one provider at once. No `container` here MUST raise `EnvUnavailable`, and a
  container system that does not answer or is not running `EnvConnectionError`.
- An agent working in one MUST be anchored to its container by `container exec` alone, its
  harness put where the next section says.
- Its container MUST be deleted when the environment is closed, and one whose process on this
  host has gone MUST be deleted by the next run on its provider.

### Where the harness runs

- A driver MUST put each session's harness where the affinity of the runtime its work is on
  says, settled once per machine a role works on. The affinity MUST be the one of the runtime
  actually opened for the work, read off where the session is placed, and MUST be the only one
  walked: a runtime a harness is put on MUST NOT have its own affinity, nor anything it would
  fall back to, walked for it.
- Work on this machine MUST have its harness here. Work on a machine that is no saved runtime,
  or on one with no affinity, MUST have its harness natively on that machine where it has the
  CLI and can hold its fence and no hook that gates the CLI is hung, and here otherwise.
- An affinity's entries MUST be tried in order, the next only where the one before has no
  room: `local` here, anchored to the machine, which always has room; `self` natively on the
  runtime's own machine, without room where its CLI is not there (`HarnessNotInstalled`) or it
  cannot hold the session's fence (`HarnessSandboxed`); `<backend>:<name>` on that runtime,
  opened as an environment of its own -- in its workdir, else the login's home over ssh, else
  an empty directory in `hmz.machine()` for a daemon or Apple's containers on this machine --
  probed and closed with the run's, acting on the work through the anchor, and without room
  where it cannot be opened or reached, has no share left (`ResourceUnmet`), or the role is
  fenced at all, which a harness on another machine cannot be held to. Where no entry has room, the last refusal MUST be
  raised, naming the affinity; a machine that cannot be asked MUST raise as it is.
- Before the flow is called, the affinity of every machine of the run MUST be walked for every
  agent, opening and probing every runtime a harness goes to, and one with no room anywhere
  MUST refuse the run.
- A session's turn working on another machine than its last MUST be refused with
  `UnsupportedOperation` on every harness, and one working in another workdir there on every
  harness but those that fork into another workdir (Claude Code, Codex, Kimi Code), where the
  conversation MUST carry on as a fork of itself, from a harness of its own settled for the
  new place as a session's is, the one it leaves kept until the session closes. A refused move
  MUST leave the session where it was.
- The machine MUST be asked whether it has the CLI down the road a native turn takes, one
  question at a time, and a run stopped while it asks MUST take the asking down with it; where
  the harness went -- `local`, `self`, or `<backend>:<name>` -- MUST be written down with each
  session whose work is elsewhere.

### Fakes

- The fakes MUST keep every promise `spi` makes of a driver, and MUST be held to
  `tests/flows/contracts.py` like any other driver.

### Where flows come from

- A flowverse MUST be an index: a git repository of `flows/<flow>/<version>/flow.yaml` for a
  flow listed bare and `flows/<user>/<flow>/<version>/flow.yaml` for one listed under a user,
  read off its clone without importing anything. A directory of `flows/` holding a SemVer
  directory MUST be a flow and nothing else, and one holding none a user's flows, `<user>`
  being a GitHub user in lower case and never `humanfia`; one that is not MUST be skipped
  with why. A manifest MUST name the flow and release its directories do, by a lower-case
  identifier and SemVer, a repository as `owner/repo` or a URL, a 40-hex commit, a directory
  of it that does not climb out, and the flows of the same index it needs as the index lists
  them; one that does not, one listed bare that takes a builtin's name, one under a user whose
  repository on GitHub is somebody else's, and one `official` lists bare whose repository on
  GitHub is not humanfia's, MUST be skipped with why, and listing the rest MUST go on. Keys a
  manifest has that are not known MUST be ignored.
- Only the flows humanize ships, the ones installed out of an index, and your own two places
  MUST be listed or resolved -- never a flow an index only lists. Every one MUST be listable
  under one name apiece -- the builtins and what was installed out of `official` as the index
  lists it, `<flow>` or `<user>/<flow>`, every other after `@<flowverse>/`, `@local/<flow>` and
  `@user/<flow>` for your own; the flow a bare name means under its module's own name and every
  other visible flow of the module as `<name>:<inside>`, a hidden one not at all -- and a bare
  name MUST resolve nearest first: this project's flows, then yours, then the rest. A name
  qualified by a flowverse or a user MUST NOT be stood in for, and a path MUST be taken
  outright. A module that will not import MUST still be listed, under its name.
- Installing a release MUST copy its `subdir` at its `commit` into
  `installed/[<user>/]<flow>/` of its flowverse's own directory, beside the clone of its index,
  with a record of what it was installed from, written before one rename puts it in place over
  whatever release was there; what is at that place MUST be a whole release and its record at
  every moment. Every skill its roles name by a URL, as read off its source without importing
  it, MUST be fetched into its own `skills/` before that rename and named in its record, and one
  that cannot be fetched MUST fail the install, leaving nothing behind. It MUST install with it
  the newest release of each flow it needs that the range takes, unless one installed already
  does, and MUST refuse, saying why, a cycle, a range nothing listed takes, two ranges no one
  release satisfies, an install that would take away a release another installed flow needs,
  and a flow listed bare and a user of one name installed one inside the other. Uninstalling
  one another installed flow needs MUST be refused, and uninstalling a user's last flow MUST
  leave nothing of the user behind.
- An update MUST be the newest release an installed flow's index lists that is greater than
  the one installed, by SemVer, and a prerelease only for a flow that is on one; fetching an
  index MUST NOT change what is installed.
- `resolved` MUST load what a way in names -- a name, either with `:<inside>`, a path, or a VCS
  ref, fetched on the calling thread -- MUST say, of a name nothing answers to, that it is not
  installed where an index lists it, how it is said now where it was said as before the `@`,
  that a path starts with `./` where it is one without, or that an index it could be in is not
  fetched yet, and MUST mark the package's own `chat` with `full_view`; nothing else is, the
  other flows humanize ships included.
- `brought` MUST bring the flow's own skills first and the ones it named after, the flow's own
  winning a shared name, and MUST raise where one cannot be fetched rather than at the turn; what an
  installed flow's record says was fetched into it MUST be brought as the URL's, not the
  flow's own.
- `fork` MUST copy the whole of a flow and MUST refuse a name already taken rather than write
  over it, and MUST NOT carry an installed flow's record; forking, installing, and adding,
  fetching or removing a flowverse, MUST leave nothing half-done behind when it fails;
  removing one MUST take its whole directory, what was installed out of it too; and
  `official`, `local` and `user`
  MUST NOT be removable.
- Every name above MUST be fetched only when it is named, so that listing flows costs nothing
  that reading or driving one does. Nothing here MAY be imported by `hmz.flows` at import, or
  drive an agent.

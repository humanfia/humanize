# `runtime`

What a run is: finding the flow, handing it a driver for every role it declared, writing the
run down as it happens, remembering what a workspace was set up with, and reading the whole of
it back afterwards. It drives no coding agent itself. Its subpackages have specs of their own:
[doing](doing.md), [flowing](flowing.md), [tracing](tracing.md).

## API

```python
# __init__.py -- each name costs only the module it is written in, fetched when it is named
__all__ = ["Accounts", "Epics", "Fallbacks", "Flows", "Flowverses", "Hmz", "Refused", "Run"]
# doing.md, and `Refused` from runner.py

# settings.py -- what humanize remembers, per workspace and per machine
class Settings:
    def __init__(self, workspace: Path | None = None) -> None: ...
    @property
    def flow(self) -> str: ...
    @property
    def enable_sentry(self) -> bool | None: ...  # None while nobody has been asked
    @property
    def profiling(self) -> bool: ...
    def profiles(self, *, on: bool) -> None: ...
    def answers(self, *, enable_sentry: bool) -> None: ...
    def agents(self, flow: str) -> dict[str, Runs]: ...  # by role
    def envs(self, flow: str) -> dict[str, str]: ...  # by role, as `-e` spells one
    def flows(self) -> dict[str, Any]: ...
    def params(self, flow: str) -> dict[str, Any]: ...
    def budget(self, flow: str) -> dict[str, Any]: ...  # a Budget, as JSON
    def remember(
        self,
        flow: str,
        agents: Mapping[str, Runs],
        envs: Mapping[str, str] | None = None,
        params: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
    ) -> None: ...
    def forget(self, workspace: str = "") -> bool: ...

# telemetry.py -- humanize's own failures, where that has been answered yes
SENT: tuple[str, ...]  # what is sent, in the words the question is asked in
KEPT: tuple[str, ...]  # and what never is, in the same words
SAYS = "HUMANIZE_SENTRY"  # answers it for one process, writing nothing down
def enabled() -> bool | None: ...
def asked(*, enable_sentry: bool) -> None: ...
def again() -> None: ...
def start() -> bool: ...
def stop() -> None: ...
def about(name: str, said: Callable[[], object]) -> None: ...
def held() -> dict[str, object]: ...
def crash(why: BaseException, **said: object) -> None: ...
def snag(name: str, **said: object) -> None: ...

# kept.py -- one agent, written down: the word `-a` takes after `<role>=`
class Runs(NamedTuple):
    spec: str  # cli/model:effort
    provider: str = ""
def written(runs: Runs) -> str: ...  # cli[@provider]/model:effort
def read_back(said: object) -> Runs | None: ...

# epic.py -- one run, written down as it happens
JOURNAL = "epic.jsonl"  # the run's own record, inside the epic
RECORD = "epic.{flow}_{ident}.jsonl"  # the record of one flow the run called
RECORDS = "epic.*.jsonl"
RESUME = "resume.jsonl"  # the engine's journal of a resumable run, inside its epic
SESSIONS = "sessions"  # where each session's own logs are pointed at
TRACES = "traces"
LOCAL = "local"  # what a session that ran on this machine is anchored as
class Session(NamedTuple):
    agent: str
    backend: str
    provider: str
    ident: str
    name: str
    at: str = ""
    flow: str = ""
    parent: str = ""
    record: str = ""
class Drove(NamedTuple):  # one agent role, and what it was given
    agent: str
    backend: str
    model: str
    effort: str
    provider: str = ""
    @property
    def spec(self) -> str: ...
class Called(NamedTuple):
    flow: str
    task: str
    record: str
    began: str = ""
    ended: str = ""
    how: str = ""
    calls: tuple[Called, ...] = ()
class Ran(NamedTuple):
    at: Path
    flow: str = ""
    task: str = ""
    workspace: str = ""
    began: str = ""
    ended: str = ""
    how: str = ""
    agents: tuple[Drove, ...] = ()
    sessions: tuple[Session, ...] = ()
    called: tuple[Called, ...] = ()
    resumable: bool = False
    ref: str = ""  # the flow's canonical ref
    envs: tuple[str, ...] = ()  # each `role=spec`, as `-e` spells one
    params: dict[str, Any] = {}
    budget: dict[str, Any] | None = None
    picked_up: str = ""  # the epic it was picked up from
    @property
    def name(self) -> str: ...
class Epic:  # a context manager, closed however the run ends
    def __init__(
        self,
        flow: str,
        task: str,
        workspace: Path | None = None,
        *,
        ref: str = "",
        agents: Sequence[Drove] = (),
        envs: Sequence[str] = (),
        params: Mapping[str, Any] | None = None,
        budget: Mapping[str, Any] | None = None,
        resumable: bool = False,
        picked_up: Path | None = None,
        profile: bool = False,
    ) -> None: ...
    @property
    def path(self) -> Path: ...
    @property
    def journal(self) -> Path: ...
    @property
    def record(self) -> str: ...
    @property
    def workspace(self) -> Path: ...
    @property
    def resume(self) -> Path: ...  # where the engine keeps this run's journal
    def stopped(self) -> None: ...
    def opened(self, agent: AgentBase, session: str, parent: str = "") -> None: ...
    def session(
        self, agent: str, backend: str, provider: str, ident: str, parent: str = ""
    ) -> None: ...
    def links(self, only: str = "") -> None: ...
    def write(self, event: str, **said: Any) -> None: ...
    def called(self, flow: str, task: str = "", *, resumable: bool = False) -> Sub: ...
    def __enter__(self) -> Self: ...
    def __exit__(
        self, kind: type[BaseException] | None, why: object, traceback: object
    ) -> None: ...
class Sub(Epic):  # one flow another flow called, in a record beside that run's own
    def __init__(
        self,
        under: Epic,
        record: str,
        flow: str,
        task: str = "",
        *,
        resumable: bool = False,
    ) -> None: ...
    def ended(self, kind: type[BaseException] | None = None, how: str = "") -> None: ...
def called(agent: str, backend: str, provider: str, ident: str) -> str: ...
def under(workspace: Path | str | None = None) -> Path: ...
def epics(workspace: Path | str | None = None) -> list[Path]: ...
def records(epic: Path) -> list[Path]: ...
def read(epic: Path) -> Ran | None: ...
def tree(epic: Path) -> tuple[Called, ...]: ...
def sessions(epic: Path) -> list[Session]: ...
def opened(epic: Path) -> dict[str, list[str]]: ...
def linked(epic: Path) -> dict[str, list[str]]: ...
def where(epic: Path, session: Session) -> Path: ...
def picks_up(epic: Path) -> bool: ...
def state(epic: Path, flow: str = "") -> dict[str, Any]: ...  # flow by canonical ref
def resumed(flow: str, workspace: Path | str | None = None) -> Path | None: ...

# exporting.py -- one whole run as one archive
BUNDLE = "{epic}.epic.tar.gz"
MANIFEST = "manifest.json"
TRANSCRIPT = "transcript.md"
REDACTED = "[redacted]"
STRUCK: tuple[str, ...]  # what is taken out of every byte of it, in words
def bundle(
    epic: Path,
    at: str | os.PathLike[str] | None = None,
    *,
    transcript: str | None = None,
) -> tuple[Path, dict[str, Any]]: ...
def logged(epic: Path) -> dict[str, dict[str, Path]]: ...
def plain(said: str, struck: Sequence[str] = ()) -> str: ...
def sized(count: int) -> str: ...

# runner.py -- a flow loaded, handed a driver per role, and run under an epic
class Refused(ValueError): ...  # a run refused before anything of it ran
class Line(NamedTuple):  # an `hmz exec` line, read
    flow: str
    task: str
    agents: tuple[AgentSpec, ...] = ()
    envs: tuple[EnvSpec, ...] = ()
    params: dict[str, str] = {}
    budget: Budget | None = None
    resume: bool = False
    as_json: bool = False
def read_line(argv: list[str]) -> Line: ...
class Runner:
    def __init__(
        self,
        flow: str | os.PathLike[str],
        *,
        agents: Mapping[str, str | AgentDriver] | Iterable[AgentSpec] = (),
        envs: Mapping[str, str | EnvDriver] | Iterable[EnvSpec] = (),
        params: Mapping[str, Any] | FlowParams | None = None,
        budget: Budget | Mapping[str, Any] | None = None,
        resume: bool | str | os.PathLike[str] = False,
        workspace: str | os.PathLike[str] | None = None,
    ) -> None: ...
    flow: str; impl: FlowImpl; declaration: Declaration; agents: dict[str, AgentDriver]
    envs: dict[str, EnvDriver]; params: FlowParams; budget: Budget
    picked_up: Path | None; workspace: Path; recorder: Recorder | None  # properties
    def unreadable(self) -> str: ...
    def watch(self, listener: Listener) -> None: ...
    async def arun(
        self,
        task: str,
        *,
        outworlder: OutworlderDriver | None = None,
        opened: Callable[[str, AgentBase, SessionBase], None] | None = None,
        started: Callable[[Epic], None] | None = None,
    ) -> Any: ...
    def run(self, task: str, *, outworlder: OutworlderDriver | None = None) -> Any: ...
class Recorder:  # answers to runtime/flowing's Recorder, writing the epic
    started: bool
    def entered(self, call: LiveCall) -> None: ...
    def left(self, call: LiveCall, error: BaseException | None) -> None: ...
    def spawned(self, call: LiveCall, role: str, session: SessionHandle,
                driver: AgentDriver) -> None: ...
    def closed(self, session: SessionHandle) -> None: ...
    @property
    def sessions(self) -> tuple[SessionHandle, ...]: ...  # the ones still open
    def usage(self) -> Usage: ...
```

## Requirements

- MUST offer the whole of what humanize can be asked to do in a workspace as one object, and
  MUST drive no coding agent itself: every turn MUST be taken through `coganchor`.
- MUST NOT name `cli`, `daemon`, `tui` or `sdk`, MUST restate no rule the layers under it
  carry out, and MUST load nothing until it is named. `telemetry` MUST name nothing above it.
- `Settings` MUST answer what a workspace was last set up to run — the flow, what each of its
  agent and environment roles was given, its params, what a run may spend — and MUST answer
  what is not a workspace's at all.
- A setting that is a question somebody has to answer MUST have three answers — yes, no, and
  nobody asked — and reading one MUST NOT write it.
- Two holders of the settings MUST NOT put back what the other has written; remembering a
  flow's agents MUST leave its environments, params and budget alone where they are not handed
  in, an empty one MUST erase, and settings humanize did not write MUST read as nothing
  remembered.
- Nothing MUST be reported where the question has not been answered yes, a run with nobody at
  a terminal MUST NOT ask, and `SAYS` MUST answer it for one process alone.
- `SENT` and `KEPT` MUST be the whole of what is sent and what never is, in words, readable
  both where the question is asked and afterwards: nothing anybody typed, nothing an agent
  said, no file, no path outside humanize, no directory name and no credential MUST leave the
  machine, whatever carried it there.
- What goes with a report MUST be offered as a callable, asked only where a report is being
  made; what is not a failure MUST be reportable too, as counts and names. A reporter that
  will not start, a callable that raises and a report that cannot be sent MUST each leave the
  run as it was.
- An agent written down MUST be a CLI, an account and a model at an effort -- the word `-a`
  takes after its role -- and nothing else; what it may do is its role's, and where it works
  is its environment's. An entry that is not one MUST read back as nothing.
- One epic MUST be one run: opened when the flow starts, closed however the run stops, never
  reopened. Epics MUST read back in the order they were run, and anything else under them MUST
  read as no run rather than fail.
- A run MUST read back as the tree of flows it called, however deep and however many ran at
  once, each call saying how it ended and each session saying which call opened it.
- Every session a run opened MUST read back as whose it was, what took its turns, which
  account they ran as, what the backend called it and which conversation it was forked from,
  and its own logs MUST be reachable from the epic without humanize copying or moving them.
- A resumable run's journal MUST be kept inside its epic, MUST be there for a run picking it
  up even where this one was killed, and a run picking one up MUST be handed a copy of it in an
  epic of its own and MUST say which epic it came from.
- A bundle MUST be one archive readable on a machine that was not there: everything the run
  wrote, the session logs themselves, and a manifest saying what the run was down to each
  backend's version and the hash of the executable that took its turns.
- A bundle MUST say of a session it holds no log for that there is none to hold, MUST say what
  actually went into it, and MUST refuse a directory holding no run. No credential MUST ride
  in any byte of it, and what the run is read by — what a turn cost, which model took it —
  MUST NOT be struck out with them.
- A bundle MUST be written whole and leave nothing behind where it fails, MUST be readable by
  whoever exported it alone, MUST land where somebody is standing unless a path was named, and
  MUST replace the earlier archive when one run is exported twice.
- Constructing a `Runner` MUST raise `Refused`, before anything runs and before any agent
  starts, for a flow that cannot be loaded; a role given that the flow does not declare, that
  the runtime fills -- an `Outworlder`, a `LocalEnv` -- or that is given twice; a required
  role left out; an agent that is not the harness its role names or whose harness does not
  serve what its role asks; a spec no driver can be made for; params the flow does not take;
  no budget, except for a flow humanize ships, which runs under `Budget(cost=inf)`; and a
  run to pick up that is not there, or of a flow that is not resumable. What the flow itself
  raises as it is imported MUST be refused with its reason. `arun` MUST raise `Refused` too
  for an environment that cannot be reached and for anything the engine refuses before the
  flow is called.
- `arun` MUST probe every environment it was given before the flow is called, MUST run the
  flow over the drivers with the workspace as every `LocalEnv` role and whoever is outside
  the run as every `Outworlder` role -- nobody, away, where none was given -- MUST write the
  run down as it goes: each flow call a record under the one that made it, saying the task it
  was called with, each session in the record of the call that opened it and named for its
  role, and what the run spent -- holding no session past its close to count it; and
  MUST close every driver it was given however the run ends. A run stopped from outside, or
  by its budget, MUST be written down as stopped rather than failed.
- `read_line` MUST read the whole `hmz exec` line, MUST NOT load a flow to answer `--help`,
  MUST take every `-a`, `-e`, `-p` and `-b` as one list however they were broken up, and
  MUST refuse one that cannot be read as argparse refuses a line.

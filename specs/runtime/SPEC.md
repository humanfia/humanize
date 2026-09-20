# `runtime`

What a run is: finding the flow, handing it the agents it declared, writing the run down as it
happens, remembering what a workspace was set up with, and reading the whole of it back
afterwards. It drives no coding agent itself. Its subpackages have specs of their own:
[doing](doing.md), [flowing](flowing.md), [tracing](tracing.md).

## API

```python
# __init__.py -- each name costs only the module it is written in, fetched when it is named
__all__ = ["Accounts", "Epics", "Fallbacks", "Flows", "Flowverses", "Hmz", "Run"]  # doing.md

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
    def agents(
        self, flow: str, goal_defaults: Sequence[bool] | None = None
    ) -> list[Runs]: ...
    def flows(self) -> dict[str, Any]: ...
    def config(self, flow: str) -> dict[str, Any]: ...
    def budget(self, flow: str) -> dict[str, Any]: ...
    def remember(
        self,
        flow: str,
        names: tuple[str, ...],
        models: Sequence[Runs],
        config: dict[str, Any] | None = None,
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

# kept.py -- one agent, written down
class Runs(NamedTuple):
    spec: str
    anchor: str = ""
    permission: str = ""
    provider: str = ""
    goals: bool = True
    web_search: bool | None = None
def written(runs: Runs) -> dict[str, Any]: ...
def read_back(held: dict[str, Any], *, goals: bool = True) -> Runs | None: ...

# epic.py -- one run, written down as it happens
JOURNAL = "epic.jsonl"  # the run's own record, inside the epic
RECORD = "epic.{flow}_{ident}.jsonl"  # the record of one flow the run called
RECORDS = "epic.*.jsonl"
SESSIONS = "sessions"  # where each session's own logs are pointed at
STATE = "state.json"
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
class Drove(NamedTuple):
    agent: str
    backend: str
    model: str
    effort: str
    permission: str = ""
    provider: str = ""
    goals: bool = True
    person: bool = False
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
    @property
    def name(self) -> str: ...
class State(dict[str, Any]):  # what a resumable flow writes into, saved as it writes
    def __init__(
        self, at: Path, flow: str, held: Mapping[str, Any] | None = None
    ) -> None: ...
    def save(self) -> None: ...
class Epic:  # a context manager, closed however the run ends
    def __init__(
        self,
        flow: str,
        agents: Sequence[AgentBase],
        task: str,
        workspace: Path | None = None,
        *,
        resumable: bool = False,
        picked_up: str = "",
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
    def state(self, flow: str = "", held: Mapping[str, Any] | None = None) -> State: ...
    def opened(self, agent: AgentBase, session: str, parent: str = "") -> None: ...
    def links(self, only: str = "") -> None: ...
    def write(self, event: str, **said: Any) -> None: ...
    def called(
        self,
        flow: str,
        agents: Sequence[AgentBase],
        task: str,
        *,
        resumable: bool = False,
    ) -> Sub: ...
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
        agents: Sequence[AgentBase],
        task: str,
        *,
        resumable: bool = False,
    ) -> None: ...
    def ended(self, kind: type[BaseException] | None = None) -> None: ...
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
def state(epic: Path, flow: str = "") -> dict[str, Any]: ...
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

# runner.py -- a flow loaded and handed its agents
class Runner:
    def __init__(
        self,
        flow: str | os.PathLike[str],
        agents: Sequence[AgentBase],
        config: BaseModel | dict[str, Any] | None = None,
        resume: str | os.PathLike[str] | None = None,
        container: str = "",
        budget: Allowance | Mapping[str, Any] | None = None,
    ) -> None: ...
    @property
    def agents(self) -> tuple[AgentBase, ...]: ...
    @property
    def budget(self) -> Allowance: ...
    @property
    def unwatched(self) -> bool: ...
    def unreadable(self) -> str: ...
    def unserved(self) -> str: ...
    def run(self, task: str) -> None: ...
def read_agent(spec: str) -> tuple[str, Profile, str, str, str]: ...
def flow_and_agents(
    argv: list[str],
) -> tuple[str, list[AgentBase], str, dict[str, Any] | None, Allowance | None, bool]: ...
def set_up_from(
    said: str | os.PathLike[str],
) -> tuple[dict[str, Any] | None, Allowance | None]: ...
```

## Requirements

- MUST offer the whole of what humanize can be asked to do in a workspace as one object, and
  MUST drive no coding agent itself: every turn MUST be taken through `coganchor`.
- MUST NOT name `cli`, `daemon`, `tui` or `sdk`, MUST restate no rule the layers under it
  carry out, and MUST load nothing until it is named. `telemetry` MUST name nothing above it.
- `Settings` MUST answer what a workspace was last set up to run — the flow, each of its
  agents and where its work lands, the flow's setup, what a run may spend — and MUST answer
  what is not a workspace's at all.
- A setting that is a question somebody has to answer MUST have three answers — yes, no, and
  nobody asked — and reading one MUST NOT write it.
- Two holders of the settings MUST NOT put back what the other has written; remembering a
  flow's agents MUST leave its config and budget alone where neither is handed in, an empty
  one MUST erase, and settings humanize did not write MUST read as nothing remembered.
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
- An agent written down MUST be a CLI, an account, a model at an effort and the machine its
  work lands on, and nothing else. A field that says nothing MUST read back as that field's
  own silence, and an entry older than a setting MUST read as what every agent did then.
- One epic MUST be one run: opened when the flow starts, closed however the run stops, never
  reopened. Epics MUST read back in the order they were run, and anything else under them MUST
  read as no run rather than fail.
- A run MUST read back as the tree of flows it called, however deep and however many ran at
  once, each call saying how it ended and each session saying which call opened it.
- Every session a run opened MUST read back as whose it was, what took its turns, which
  account they ran as, what the backend called it and which conversation it was forked from,
  and its own logs MUST be reachable from the epic without humanize copying or moving them.
- What a resumable flow leaves MUST be kept under that flow's own name, MUST be there for the
  next run of it even where this one was killed, and MUST NOT be able to stop a run.
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
- Constructing a `Runner` MUST raise `NotAFlow`, before anything runs, for a file that is not
  a flow, a number of agents the flow does not drive, an agent that cannot run a moment or a
  goal the flow declared, a config the flow did not ask for, or a skill that cannot be
  fetched. Whatever the flow itself raises as it loads MUST be left alone.
- What the flow declared about each place MUST be settled onto its agent before the first turn
  and over whatever it was made with; what a lenient place gave up MUST be answerable in
  words, an agent the flow names MUST answer to that name from then on, and the person a flow
  talks to MUST be made here rather than given and MUST be among `agents`.
- `run` MUST drive the flow with the agents as it declared them until it returns, one written
  as a coroutine among them, MUST write the run down as it happens, and the run MUST be over
  when it returns. A run given a container MUST work in one throughout and take it down
  however it ends; one given none MUST start none.
- Every run MUST be held to one allowance across every agent of it; what the flow declared
  MUST be a default whoever started the run may override, and a run nothing will stop MUST be
  answerable as such before it starts. `set_up_from` MUST lift that allowance out of a `-c`
  file before the flow's own model sees it.
- A resumable flow MUST be handed what the run it picks up left behind — the last run of it in
  this workspace unless one was named — and what it writes MUST belong to the run writing it.
- `flow_and_agents` MUST read the whole `hmz exec` line, MUST NOT load a flow to answer
  `--help`, MUST split an `-a` naming several before reading any, MUST order agents that named
  a place as the flow does and refuse a name it has not got, and MUST hand the run's allowance
  back beside the flow's setup rather than folded into it.

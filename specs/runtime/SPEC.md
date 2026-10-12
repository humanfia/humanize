# `runtime`

What a run is: finding the flow, handing it a driver for every role it declared, writing the
run down as it happens, remembering what a workspace was set up with, and reading the whole of
it back afterwards. It drives no coding agent itself. Its subpackages have specs of their own:
[doing](doing.md), [flowing](flowing.md), [tracing](tracing.md), [watching](watching.md).

## API

```python
# __init__.py -- each name costs only the module it is written in, fetched when it is named
__all__ = ["Accounts", "Epics", "Fallbacks", "Flows", "Flowverses", "Hmz", "Host", "Refused",
           "Run", "Runtimes"]
# doing.md, and `Refused` from runner.py

# settings.py -- what humanize remembers, per workspace and per machine
class Settings:
    def __init__(self, workspace: Path | None = None) -> None: ...
    @property
    def flow(self) -> str: ...
    @property
    def enable_sentry(self) -> bool | None: ...  # None while nobody has been asked
    @property
    def details(self) -> bool: ...  # whether the interface shows each turn's working
    def detailing(self, *, on: bool) -> None: ...
    @property
    def btw(self) -> str: ...  # the agent `/btw` asks, "" for the flow's first
    @btw.setter
    def btw(self, spec: str) -> None: ...
    @property
    def every_epic(self) -> bool: ...  # whether `/epics` lists this machine's, not this directory's
    @every_epic.setter
    def every_epic(self, on: bool) -> None: ...
    def answers(self, *, enable_sentry: bool) -> None: ...
    def agents(self, flow: str) -> dict[str, Runs]: ...  # by role
    def envs(self, flow: str) -> dict[str, str]: ...  # by role, as `-e` spells one
    def flows(self) -> dict[str, Any]: ...
    def params(self, flow: str) -> dict[str, Any]: ...
    def budget(self, flow: str) -> dict[str, Any]: ...  # a Budget, as JSON
    def profile(self, flow: str) -> bool: ...  # whether a run of it is profiled
    def backup(self, flow: str) -> tuple[str, ...] | None: ...  # its targets; None: defaults
    def remember(
        self,
        flow: str,
        agents: Mapping[str, Runs],
        envs: Mapping[str, str] | None = None,
        params: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        *,
        profile: bool | None = None,
        backup: Sequence[str] | None = None,
    ) -> None: ...
    def forget(self, workspace: str = "") -> bool: ...
    def backups(self) -> tuple[tuple[Target, ...], tuple[str, ...]]: ...  # targets, defaults
    def back_up_to(
        self, targets: Iterable[Target | Mapping[str, Any]], defaults: Iterable[str] = ()
    ) -> None: ...  # ValueError for one that is not one, nothing written
POLICIES = ("session", "interval", "end")  # when an epic is backed up unasked; none: by hand
class Target(NamedTuple):  # one git repository epics are backed up to
    name: str  # one short word
    url: str
    branch: str = "main"
    policies: tuple[str, ...] = ()
    every: int = 30  # minutes apart, for `interval`

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
SESSIONS = "sessions"  # where the run keeps its sessions, a directory per CLI
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
    where: str = ""  # where it is kept: from the epic, or whole where it stayed at home
    harness: str = ""  # where its harness ran, for work elsewhere: local, self, <backend>:<name>
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
    used: tuple[str, ...] = ()  # where each was put, the same way: `envs` but for a fallback
    params: dict[str, Any] = {}
    budget: dict[str, Any] | None = None
    picked_up: str = ""  # the epic it was picked up from
    profile: bool = False  # whether it was profiled as well as traced
    spent: dict[str, Any] | None = None  # cost, output_tokens and seconds, as its budget counted
    backup: tuple[str, ...] = ()  # the targets it is backed up to
    backed: dict[str, dict[str, Any]] = {}  # each target's last backup: at, ok, error, why
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
        used: Sequence[str] | None = None,  # None for where each was given
        params: Mapping[str, Any] | None = None,
        budget: Mapping[str, Any] | None = None,
        resumable: bool = False,
        picked_up: Path | None = None,
        profile: bool = False,
        backup: Sequence[str] = (),
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
    @property
    def keeps(self) -> Path: ...  # where its agents keep the sessions they open
    def stopped(self) -> None: ...
    def opened(self, agent: AgentBase, session: str, parent: str = "") -> None: ...
    def session(
        self,
        agent: str,
        backend: str,
        provider: str,
        ident: str,
        parent: str = "",
        where: Path | None = None,
        *,
        harness: str = "",
    ) -> None: ...
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
def harbor(target: str, runtime: str) -> None: ...  # which runtime a harness machine is
def harnessed(machine: MachineConfig | None) -> str: ...  # local, self, <backend>:<name>
def under(workspace: Path | str | None = None) -> Path: ...
def epics(workspace: Path | str | None = None) -> list[Path]: ...
def every() -> list[Path]: ...  # of every workspace on this machine, oldest first
def records(epic: Path) -> list[Path]: ...
def read(epic: Path) -> Ran | None: ...
def tree(epic: Path) -> tuple[Called, ...]: ...
def sessions(epic: Path) -> list[Session]: ...
def opened(epic: Path) -> dict[str, list[str]]: ...
def where(epic: Path, session: Session) -> Path: ...
def logs(epic: Path, session: Session) -> dict[str, Path]: ...
def picks_up(epic: Path) -> bool: ...
def foreign(epic: Path) -> str: ...  # why an imported run cannot be picked up here, or ""
def state(epic: Path, flow: str = "") -> dict[str, Any]: ...  # flow by canonical ref
def resumed(flow: str, workspace: Path | str | None = None) -> Path | None: ...
BACKED = "backed"  # the line saying how one backup of an epic went
def note(epic: Path, event: str, **said: Any) -> None: ...  # a line from outside the run

# exporting.py -- one whole run as one archive, and back
BUNDLE = "{epic}.hmzepic"  # a gzipped tar
MANIFEST = "manifest.json"
TRANSCRIPT = "transcript.md"
REDACTED = "[redacted]"
STRUCK: tuple[str, ...]  # what is taken out of every byte of it, in words
def bundle(
    epic: Path,
    at: str | os.PathLike[str],
    *,
    transcript: str | None = None,
) -> tuple[Path, dict[str, Any]]: ...
def unpacked(epic: Path, into: Path) -> dict[str, Any]: ...  # what a bundle holds, as files
def unbundle(archive: str | os.PathLike[str]) -> Path: ...
def placed(epic: Path, origin: str) -> Path: ...  # an epic laid out as `unpacked` lays it out
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
    profile: bool = False
    resume: bool = False
    as_json: bool = False
    backup: tuple[str, ...] | None = None  # None for the defaults
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
        profile: bool = False,
        resume: bool | str | os.PathLike[str] = False,
        workspace: str | os.PathLike[str] | None = None,
        backup: Iterable[str] | None = None,  # None for the defaults
    ) -> None: ...
    flow: str; impl: FlowImpl; declaration: Declaration; agents: dict[str, AgentDriver]
    envs: dict[str, EnvDriver]; params: FlowParams; budget: Budget; profile: bool
    backup: tuple[str, ...]
    picked_up: Path | None; workspace: Path; recorder: Recorder | None  # properties
    used: dict[str, str]  # where each environment role was put, as `-e` spells it
    def unreadable(self) -> str: ...
    def watch(self, listener: Listener) -> None: ...
    async def arun(
        self,
        task: str,
        *,
        outworlder: OutworlderDriver | None = None,
        opened: Callable[[str, AgentBase, SessionBase], None] | None = None,
        started: Callable[[Epic], None] | None = None,
        noticed: Callable[[str], None] | None = None,
    ) -> Any: ...
    def run(self, task: str, *, outworlder: OutworlderDriver | None = None) -> Any: ...
class Recorder:  # answers to runtime/flowing's Recorder, writing the epic
    started: bool
    def began(self, spent: Callable[[], Usage]) -> None: ...
    def entered(self, call: LiveCall) -> None: ...
    def left(self, call: LiveCall, error: BaseException | None) -> None: ...
    def spawned(self, call: LiveCall, role: str, session: SessionHandle,
                driver: AgentDriver) -> None: ...
    def named(self, call: LiveCall, role: str, session: SessionHandle,
              driver: AgentDriver) -> None: ...
    def closed(self, session: SessionHandle) -> None: ...
    @property
    def sessions(self) -> tuple[SessionHandle, ...]: ...  # the ones still open
    def usage(self) -> Usage: ...  # the engine's reckoning of the run
    def finished(self) -> Usage: ...  # the same, kept once the run is over

# backing.py -- epics backed up to git repositories, behind everything else
def configured() -> tuple[tuple[Target, ...], tuple[str, ...]]: ...  # Settings().backups()
def chosen(names: Iterable[str] | None) -> tuple[str, ...]: ...  # None: the defaults
def where(epic: Path) -> str: ...  # <machine>/<workspace>/<epic>, in the repository
def push(epic: Path, names: Iterable[str], why: str) -> None: ...  # queued, never waited on
def wait(seconds: float | None = None) -> bool: ...  # whether none is left
class Stored(NamedTuple):  # one epic a target holds, as its manifest there says it
    key: str  # <machine>/<workspace>/<epic>, in the repository
    machine: str
    workspace: str  # where it says it ran
    epic: str
    flow: str
    task: str
    began: str
    ended: str  # "" for one not ended when it was backed up
    how: str  # done, failed, stopped; "" for one not ended
    head: str
def listed(name: str) -> list[Stored]: ...  # fetched afresh, oldest first
def pulled(name: str, key: str) -> Path: ...  # into this machine's epics, as an import
class Keeping:  # one epic's policies, as it runs
    def __init__(self, epic: Path, names: Sequence[str]) -> None: ...
    def closed(self) -> None: ...  # a session closed: `session`
    def ended(self) -> None: ...  # the epic ended: `end`, and `interval` stops
```

## Requirements

- MUST offer the whole of what humanize can be asked to do in a workspace as one object, and
  MUST drive no coding agent itself: every turn MUST be taken through `coganchor`.
- MUST NOT name `cli`, `daemon`, `tui`, `web` or `sdk`, MUST restate no rule the layers under it
  carry out, and MUST load nothing until it is named. `telemetry` MUST name nothing above it.
- `Settings` MUST answer what a workspace was last set up to run — the flow, what each of its
  agent and environment roles was given, its params, what a run may spend, whether a run is
  profiled and the backup targets a run goes to — and MUST answer what is not a workspace's at
  all.
- A setting that is a question somebody has to answer MUST have three answers — yes, no, and
  nobody asked — and reading one MUST NOT write it.
- Two holders of the settings MUST NOT put back what the other has written; remembering a
  flow's agents MUST leave its environments, params, budget, profiling and backup targets alone
  where they are not handed in, an empty one MUST erase -- but for backup targets, where empty
  MUST be none and nothing remembered MUST be the defaults -- and settings humanize did not
  write MUST read as nothing remembered.
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
  account they ran as, what the backend called it, which conversation it was forked from and
  where it is kept. A session a turn could keep MUST be kept in the epic as the only copy of it:
  under `sessions/<cli>/`, laid out as that CLI's home is, written, resumed and forked there, and
  never in the CLI's own home. One whose CLI ran on another machine -- the target's own, or under
  a harness elsewhere -- MUST be kept there and copied into the epic's `sessions/<cli>/`, laid
  out the same way: whole lines as they are logged while it is open, the whole of it as it
  closes, and read from that copy. One neither kept nor copied MUST be read where its CLI kept
  it, the epic saying where; an epic holding a link per session MUST still read back, and no
  epic MUST be given one.
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
  whoever exported it alone, MUST land only where a path names, a file or a directory to put it
  in, and MUST replace the earlier archive when one run is exported twice.
- Importing MUST take only a `.hmzepic` holding one epic directory with its `epic.jsonl` and
  manifest and nothing but plain files under it, MUST refuse any other archive, any member that
  would land outside it, and an epic already here, and MUST leave nothing behind where it
  fails. The epic MUST land whole under the workspace it says it ran in, each session's logs
  where that session says it is kept -- one kept in another machine's CLI home kept in the
  epic, its line saying so -- and MUST say it was imported, from which file and which commit.
- An imported run MUST NOT be picked up unless the workspace it ran in is here at that very
  path and, where that is a repository and a commit was said, holds that commit; resuming one
  that cannot MUST be refused saying why.
- Constructing a `Runner` MUST raise `Refused`, before anything runs and before any agent
  starts, for a flow that cannot be loaded; a role given that the flow does not declare, that
  the runtime fills -- an `Outworlder`, a `LocalEnv` -- or that is given twice; a required
  role left out; an agent that is not the harness its role names or whose harness does not
  serve what its role asks; a spec no driver can be made for, unless the runtime it names
  falls back to others; params the flow does not take;
  no budget, except for the package's own `chat`, which runs under `Budget(cost=inf)`; and a
  run to pick up that is not there, or of a flow that is not resumable. What the flow itself
  raises as it is imported MUST be refused with its reason. `arun` MUST raise `Refused` too
  for an environment that cannot be reached or whose provider cannot hold what its role asks
  -- nor any runtime that provider falls back to --, and for anything the engine refuses
  before the flow is called.
- `arun` MUST probe every environment it was given before the flow is called, all at once --
  a refusal stopping the rest, and the first role refused, in the order they are declared,
  being the one raised. Where an `-e`
  names a saved runtime with a fallback list and that runtime cannot hold the role -- it cannot
  be opened or reached or has not got the workdir, it has not got what the role asks left to
  hand out or is at its container limit, or its machine is short of a resource the role
  declares -- the
  environment MUST move to each runtime of that list in turn, in the runtime's own saved
  workdir where it has one and otherwise the one given, until one holds it, closing every
  driver refused on the way; where none does, the last refusal MUST be raised naming every
  runtime tried and why. Only the runtime the `-e` named MUST be walked: a runtime reached by
  falling back MUST NOT walk its own list, an `-e` naming no saved runtime falls back to
  nothing, and where an agent's harness is put MUST NOT be part of it. A move MUST be told to
  `noticed` -- the runtime that could not hold the role, why, and the one used -- and from
  then on the runtime that held it MUST be the role's: its driver in `envs`, its spec in
  `used`, and the epic's `used` where that differs from `envs`, which MUST stay as given. `arun`
  MUST run the
  flow over the drivers with the workspace as every `LocalEnv` role and whoever is outside
  the run as every `Outworlder` role -- nobody, away, where none was given -- MUST write the
  run down as it goes: each flow call a record under the one that made it, saying the task it
  was called with, each session in the record of the call that opened it and named for its
  role, and what the run spent -- holding no session past its close to count it; and
  MUST close every driver it was given however the run ends. A run stopped from outside, or
  by its budget, MUST be written down as stopped rather than failed.
- A run MUST read back what its budget counted as it ended -- what it cost, the output tokens
  and the seconds -- as `Ran.spent`, and nothing for a run still going or one killed before it
  could say.
- A run MUST be profiled as well as traced only where it was asked to be, as it is given its
  budget -- never by a setting of the workspace it runs in -- and its epic MUST say that it
  was, so that it reads back as `Ran.profile`; a record that does not say MUST read as not.
- A run under a finite cost cap MUST bring a missing or stale price list up to date before its
  first turn, waiting no longer than the fetch's own timeout nor once the run is stopped, and
  on the rules every fetch is held to; every other run MUST have it refreshed without waiting.
- `Settings` MUST answer the git repositories epics are backed up to -- this machine's, not a
  workspace's -- and the defaults among them, reading one that is not a target as none and a
  default naming none as nothing; writing them MUST refuse a target that is not one, two of one
  name and a default naming none, writing nothing, and MUST leave the rest of the file alone.
- A run MUST be backed up to the targets it was given -- the defaults where it was given none,
  nowhere where it was given an empty list -- and MUST be refused for a target settings has none
  of; its epic MUST say which, and MUST read back as `Ran.backup`. Each target MUST back it up as
  its policies say and only so: `session` as each of its sessions closes, `interval` every
  `every` minutes while it runs, `end` once it has ended however it ended -- whichever way in ran
  it; no policy MUST mean by hand only.
- A backup MUST commit the files `unpacked` writes -- struck of credentials exactly as a bundle
  is -- under `<machine>/<workspace>/<epic>/` of the target's branch, in one commit naming the
  epic and why, and push it; it MUST start from what the remote's branch holds, MUST make a
  branch the remote has not got, and MUST try once more where the push was refused. It MUST go
  through this machine's own git and whatever it signs in with, MUST ask nobody anything, MUST
  hold every git command to a timeout, and MUST keep its clone as a cache under
  `hmz.machine()`, held against every other process backing up to it.
- No backup MUST hold anything else up: each MUST be queued and done on a thread of its own,
  one queue per target, an epic already waiting MUST NOT be queued twice, and a failure MUST
  be written into the epic rather than raised. How each target's last backup went -- when,
  whether, why not with no credential in it, and why it was made -- MUST be written into the
  epic as `backed` and read back as `Ran.backed`.
- `listed` MUST fetch the target's branch into its clone as a backup does, under the same lock
  and timeouts and asking nobody anything, and MUST answer every epic it holds, of every machine
  and workspace, read off the files there alone. `pulled` MUST take one of them into this
  machine's epics exactly as importing a bundle does -- through `placed`, which `unbundle` reads
  an archive back through as well -- with the same refusals, an epic this machine backed up and
  still has being one already here, and MUST say it was imported from that key on that target,
  its URL with nothing signed into it. A key that is not three plain names MUST be refused.
- `read_line` MUST read the whole `hmz exec` line, MUST NOT load a flow to answer `--help`,
  MUST take every `-a`, `-e` and `-p` as one list however they were broken up -- the budget
  out of `-p budget.<limit>=` --, and
  MUST refuse one that cannot be read as argparse refuses a line.

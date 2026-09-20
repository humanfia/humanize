# `runtime/flowing`

Everything humanize does *to* a flow: finding one and listing them all, reading one without
running it, driving one, compiling an atlas into a prophecy and walking it, proving one against
stubs, and fetching the skills it named. A flow never imports this; what a flow writes against
is `hmz.flows`, and nothing here drives a coding agent itself.

## API

```python
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
BUILTIN_AT: Path  # where humanize's own flows are
ENTRY = "__init__.py"  # what a flow's own directory is entered by
PROPHECY = "prophecy.pkl"  # what a shipped prophecy is called beside it
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
def reading(named_: str) -> str: ...  # what a reading is pointed at
def foretold(named_: str) -> str: ...  # what a prophecy is compiled out of
def at(named_: str) -> str: ...  # its own directory, or ""
def inside(named_: str) -> str: ...  # which of the flows a file holds
def about(named_: str) -> str: ...
def held(where_: str | os.PathLike[str]) -> list[Flow]: ...  # `Flow` is `hmz.flows`'s mark
def loaded(where_: str | os.PathLike[str]) -> dict[str, Any]: ...
def fork(named_: str, into: str | os.PathLike[str] | None = None) -> str: ...

# checking.py -- reading a flow without running it
OF_AGENT = "of_agent"  # which half of `Needs` a capability is asked in
WHERE = "where"
class Finding(NamedTuple):
    code: str
    severity: Literal["error", "warning"]
    where: Path
    line: int
    said: str
class Capability(NamedTuple):
    name: str
    backends: frozenset[str]  # empty for one every backend serves
    said: str
    asked: str = OF_AGENT
def checked(flow: str | os.PathLike[str]) -> tuple[Finding, ...]: ...
def catalogue() -> tuple[Capability, ...]: ...
def briefed() -> str: ...  # the catalogue as a flow's author is shown it
def surface(protocol: type) -> frozenset[str]: ...
def offered() -> frozenset[str]: ...
def misplaced(names: Iterable[str], asked: str) -> frozenset[str]: ...

# driving.py -- what a flow declares, and one flow running another
type Entry = Callable[..., Awaitable[None] | None]
class NotAFlow(ValueError): ...
class Running(NamedTuple):
    flow: str
    since: float
    depth: int = 0
    under: Running | None = None
class Place(NamedTuple):
    name: str
    person: bool
    moments: frozenset[Moment]
    where: type[Remote] | Remote | Isolated | None = None
    goal: bool = False
    permission: str = ""
    goals: bool = True
    web_search: bool | None = None
    insist: bool = True
    needs: Needs | None = None
def drives(flow: str | os.PathLike[str]) -> tuple[str, ...]: ...
def wanted(flow: str | os.PathLike[str]) -> tuple[Place, ...]: ...
def configures(flow: str | os.PathLike[str]) -> type[BaseModel] | None: ...
def resumes(flow: str | os.PathLike[str]) -> bool: ...
def declared(flow: str | os.PathLike[str]) -> Allowance | None: ...
def load(flow: str | os.PathLike[str], *, inherit_skills: bool = False) -> Entry: ...
def running() -> tuple[Running, ...]: ...
def container() -> Mapped | None: ...
# And what whoever sets a run up drives it through. `Agent` and `Marked` are `hmz.flows`'s
# own -- what a flow is handed, and the mark that makes a function a flow.
def declares(
    flow: str | os.PathLike[str],
) -> tuple[
    Entry,
    tuple[Place, ...],
    Callable[..., tuple[Agent, ...]],
    type[BaseModel] | None,
    Marked,
]: ...
def readies(run: Entry) -> Entry: ...
def carries(flow: str | os.PathLike[str], agents: Sequence[Agent]) -> None: ...
def set_up(
    flow: str | os.PathLike[str],
    setting: type[BaseModel] | None,
    config: BaseModel | dict[str, Any],
) -> BaseModel: ...
def serves(flow: str | os.PathLike[str], agent: Agent, place: Place) -> None: ...
def lands(
    flow: str | os.PathLike[str],
    agent: Agent,
    place: Place,
    *,
    container: str = "",
) -> None: ...
def runs_at(
    flow: str | os.PathLike[str],
    agent: Agent,
    place: Place,
    *,
    dropped: list[str] | None = None,
) -> AgentConfig: ...
def comes_to(
    backend: str, *, catalogued: Sequence[Capability] | None = None
) -> frozenset[str]: ...
@contextlib.contextmanager
def contained(
    image: str, workspace: str = ""
) -> Generator[MachineConfig | None]: ...
def entered(flow: str, agents: Sequence[Agent] = ()) -> Running: ...
def left(one: Running) -> None: ...
def lands_in(agents: Sequence[Agent], where_: MachineConfig) -> None: ...

# prophecy.py -- the compiled graph an atlas is
AGENTS = "@agents"  # what a node reading the run's agents takes
INPUT = "@input"
CONFIG = "@config"
class Field(NamedTuple):
    name: str
    shape: str
    required: bool
class Shape(NamedTuple):
    name: str
    fields: tuple[Field, ...] = ()
class Reads(NamedTuple):
    reads: str
    field: str = ""
class When(NamedTuple):
    reads: str
    field: str
    truth: bool
class Node(NamedTuple):
    at: str
    kind: Kind  # `hmz.flows.atlas`'s own
    calls: str
    takes: tuple[Reads, ...] = ()
    binds: str = ""
    gives: str = ""
    rerun: bool = True
    under: str = ""
class Edge(NamedTuple):
    out_of: str
    into: str
    when: When | None = None
    answers: str = ""
class Prophecy(NamedTuple):
    name: str
    takes: str
    gives: str
    config: str
    agents: tuple[str, ...]
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    shapes: tuple[Shape, ...]
    prophecies: tuple[Prophecy, ...] = ()
    def node(self, at: str) -> Node | None: ...
    def out_of(self, at: str) -> tuple[Edge, ...]: ...
    def under(self, named: str) -> Prophecy | None: ...
class Shipped(NamedTuple):
    at: Path
    prophecy: Prophecy | None
def canonical(prophecy: Prophecy) -> str: ...
def digest(prophecy: Prophecy) -> str: ...
def kept(prophecy: Prophecy) -> bytes: ...
def told(said: bytes) -> Prophecy | None: ...
def shipped(under: str | os.PathLike[str]) -> Shipped | None: ...  # `foreshipped` above

# prophesying.py -- compiling an atlas
PLAIN = ("str", "int", "float", "bool")
NOTHING = "None"
ONE_AGENT = "@agent"
THE_AGENTS = "@agents"
class Prophesied(NamedTuple):
    findings: tuple[Finding, ...]
    prophecy: Prophecy | None
def prophesied(
    flow: str | os.PathLike[str],
    *,
    name: str = "",
    through: tuple[tuple[str, str], ...] = (),
) -> Prophesied: ...
def is_atlas(flow: str | os.PathLike[str]) -> bool: ...
def named_as(under: Path, inside_: str = "") -> str: ...

# stepping.py -- running one
def walking(
    flow: str | os.PathLike[str], inside: Mapping[str, Any], entry: Entry
) -> Entry: ...

# proving.py -- driving a flow against stubs
class Scenario(NamedTuple):
    name: str
    verdict: bool | None
    answer: str
    climb: float = 100_000.0
    turns: int = 200
    tick: float = 60.0
    seconds: float = 60.0
NEVER_DONE = Scenario("never-done", verdict=False, answer="did some of it")
ALWAYS_DONE = Scenario("always-done", verdict=True, answer="did it")
SILENT = Scenario("silent", verdict=None, answer="")
class Outcome(NamedTuple):
    scenario: str
    finished: bool
    turns: int
    said: str
class Proof(NamedTuple):
    findings: tuple[Finding, ...]
    outcomes: tuple[Outcome, ...]
def proved(
    flow: str | os.PathLike[str],
    *,
    name: str = "",
    config: Mapping[str, object] | None = None,
    scenarios: tuple[Scenario, ...] = (NEVER_DONE, ALWAYS_DONE),
) -> Proof: ...

# skills.py -- what a flow brings its agents; `CARD`, `SKILLS` and `Loaded` come from
# `hmz.coganchor.agents.skills` and are offered again here
def brought(at: Path | str, declared: Iterable[str] = ()) -> list[Loaded]: ...
def cached(url: str) -> Path: ...
def fetched(url: str) -> Path: ...
def under() -> Path: ...
```

## Requirements

- Every flow MUST be listable under one name apiece -- humanize's own by a bare name, every
  other as `<flowverse>/<name>`, a file holding several as `<name>:<inside>` -- and a name
  MUST resolve nearest first: this project's flows, then yours, then the rest. A name
  qualified by a flowverse MUST NOT be stood in for, and a path MUST be taken outright.
- A flow MUST be read as it is when it is asked for, never cached, and a file that will not
  read MUST be one line of a list rather than the end of it.
- `checked` MUST import and execute nothing of the flow it reads, MUST answer with findings
  rather than raise, and MUST keep `error` for a flow that cannot run, cannot be answered or
  cannot end. A flow with no error finding MUST be one `load` would take.
- What a flow declares -- the agents it drives, what each place takes, whether it resumes,
  what it may be set up with and spend -- MUST be readable before an agent is chosen, and MUST
  raise `NotAFlow` otherwise. An agent that cannot serve a place MUST be refused, saying why.
- `catalogue` MUST report what this installation serves at the moment it is asked.
- `load` MUST take the name `-f` takes and MUST refuse a name nothing answers to where the
  flow is asked for rather than where it is called. The called flow MUST run as a flow of its
  own, carry its own skills, and give the caller's agents back as they were however it ends.
- `running` MUST answer with the branch it is asked from inside a flow and with every flow of
  the run, oldest first, from outside; `container` MUST answer with the workspace as the
  machine a contained run works on has it, and with nothing for a run on this one.
- A prophecy MUST be canonical: two readings of one atlas, and a body reformatted or reordered
  where nothing depends on the order, MUST compile to the same bytes and digest. An atlas that
  does not compile MUST be refused before the run has chosen, opened or spent anything.
- A shipped prophecy MUST be what runs where one is shipped, bytes read back MUST build a
  prophecy or nothing else, and a run MUST be picked up only into the prophecy it was doing.
- `proved` MUST drive the flow in a process of its own, one per scenario, MUST end every
  proof, and MUST say whether the turns or the clock ended it.
- `brought` MUST bring the flow's own skills first and the ones it named after, the flow's own
  winning a shared name, and MUST raise where one cannot be fetched rather than at the turn.
- `fork` MUST copy the whole of a flow and MUST refuse a name already taken rather than write
  over it; forking, and adding, fetching or removing a flowverse, MUST leave nothing half-done
  behind when it fails, and `official`, `local` and `user` MUST NOT be removable.
- Every name above MUST be fetched only when it is named, so that listing flows costs nothing
  that reading or driving one does. Nothing here MAY be imported by `hmz.flows` or drive an agent.

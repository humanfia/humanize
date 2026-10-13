# `runtime/tracing`

Reads a run back off the logs the coding agent CLIs wrote for themselves and off the programs
those turns started, and renders both on one timeline as a Chrome trace, or lays one epic out
as an Exomyth timeline for a viewer of its own to draw. It drives nothing.

## API

```python
# tracing/__init__.py
def collect(
    workspace: str | os.PathLike[str] | None = None,
    *,
    sessions: str | Iterable[str] | None = None,
    agents: Mapping[str, Iterable[str]] | None = None,
    output: str | os.PathLike[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    profile: str | os.PathLike[str] | Iterable[Process] | None = None,
    kept: Iterable[str | os.PathLike[str]] | None = None,
) -> dict[str, Any]: ...

# tracing/collector.py
def gather(
    workspace: str | os.PathLike[str] | None = None,
    *,
    sessions: str | Iterable[str] | None = None,
    agents: Mapping[str, Iterable[str]] | None = None,
    start: str | None = None,
    end: str | None = None,
    kept: Iterable[str | os.PathLike[str]] | None = None,
) -> list[Session]: ...  # what `collect` draws, undrawn

# tracing/packing.py
def stacked(spans: Iterable[tuple[float, float]]) -> list[tuple[int, int]]: ...  # (lane, depth)

# tracing/timeline.py -- Exomyth
VERSION: int
class Opened(Protocol): ident: str; agent: str; record: str  # epic.Session is one
class Drove(Protocol): agent: str; name: str  # epic.Drove is one
class Call(Protocol):  # epic.Called is one
    flow: str; task: str; record: str; began: str; ended: str; how: str; calls: Sequence[Call]
class Epic(Protocol):  # epic.Ran is one
    name: str; flow: str; task: str; began: str; ended: str; how: str; sessions: Sequence[Opened]
    agents: Sequence[Drove]
@dataclass(frozen=True, slots=True)
class Timeline:
    document: dict[str, Any]
    details: Sequence[dict[str, Any]]  # each span's args, by span id
    def span(self, ident: int) -> dict[str, Any]: ...
def build(
    sessions: Iterable[Session],
    *,
    ran: Epic | None = None,
    calls: Sequence[Call] = (),
    profiled: Iterable[Process] = (),
) -> Timeline: ...

# tracing/profile.py
PROFILE: str  # what a run's profile is written to, inside the epic it was taken in
class Thread(NamedTuple): tid: int; began: float; ended: float; cpu: float = 0.0
class Process(NamedTuple):
    pid: int; ppid: int; name: str; argv: tuple[str, ...]; began: float; ended: float
    threads: tuple[Thread, ...] = (); seen: float = 0.0
class Profiler:
    def __init__(self, at: str | os.PathLike[str], every: float = EVERY, root: int | None = None) -> None: ...
    def start(self) -> None: ...
    def stop(self, seconds: float = 2.0) -> None: ...
def read(at: str | os.PathLike[str]) -> list[Process]: ...
```

## Requirements

- `collect` MUST return the trace document, and MUST write it only where an `output` is
  given, creating that file's directory.
- `workspace` MUST narrow the trace to the sessions recorded under it, and MUST default to
  the current working directory unless sessions are named by id alone.
- `sessions` MUST be a filter taken as a comma separated string or an iterable of ids, whole
  or shortened; naming none MUST NOT read as naming all, and each brings its sub-agents.
- `agents` MUST name what each agent of a flow opened; a session nobody claims MUST be
  gathered under the configuration it ran at rather than on its own.
- `start` and `end` MUST accept any wording `dateparser` understands, defaulting to the
  earliest and latest record.
- `profile` MUST accept the profile an epic holds or the records themselves, and each program
  MUST land on the same timeline as the turns, at the same scale.
- `collect` MUST raise `ValueError` for a time it cannot read or an empty session id, and
  MUST NOT fail a whole trace because one backend is absent or unreadable.
- Where a backend keeps its logs MUST be read from `hmz.coganchor`, and nothing here MAY
  require anything of what drives one. Every directory in `kept` MUST be read beside each
  backend's own home, as a directory per backend laid out as that home is.
- Profiling MUST sample rather than intercept and MUST NOT be able to stop a run: a process
  that cannot be read, or a profile that cannot be written, MUST leave the run as it was.
- A profile MUST be appended as each program goes rather than held to the end, and a start
  MUST be timed against the clock the rest of the trace is timed by.
- `gather` MUST select and name sessions exactly as `collect` does, and `collect` and the
  Exomyth timeline MUST both stack overlapping slices with `stacked`: a slice goes in the first
  lane where it nests in the one open on top, and two slices of one lane at one depth MUST NOT
  overlap.

### Exomyth timeline

- `build` MUST take the epic and its calls as what they say rather than as `runtime/epic`'s
  types, which this MUST NOT import.
- `build` MUST return a document of exactly these keys: `version` (`VERSION`), `layout`,
  `epic` (its name, or ""), `origin` (the epoch seconds every time in it counts from: the earliest moment
  of anything in it), `live` (whether the epic has not ended), `strings`, `processes`,
  `tracks`, `spawns` and `summary`. It MUST be plain JSON values throughout.
- `strings` MUST hold every piece of text the document says once, with `""` at index 0; every
  other text field MUST be an index into it, except a process's `kind`.
- Every time MUST be whole microseconds since `origin`, and every duration whole microseconds
  and never negative.
- `processes` MUST be one per session that did anything, of `kind` `session`; one `flow` for
  the epic where there is one, first; and one `os` per program of a profiled epic -- sessions
  ordered by start, programs by start then pid. Each MUST carry `id` (its index), `kind`,
  `name`, `key`, `pid` (0 but for a program), `start`, `end`, `parent` (a process id, or -1),
  `tracks` (track ids, in lane order), and `agent`, `role`, `backend`, `model`, `label` and
  `record`. A session's `role` MUST be the one its agent filled, read off the epic's agents by
  the agent's `name` -- or by the role, for an agent written down with none -- and "" for one
  no agent of the epic's names. A sub-agent's parent MUST be the session that started it, a
  session the epic opened -- and a sub-agent whose starter did nothing -- MUST hang from the
  `flow` process, and a program's MUST be the program that held its parent's pid when it
  started, where that was profiled.
- The `flow` process MUST hold a span for the epic and one for every flow it called, each
  inside its caller; a call that has not returned, and an epic that has not ended, MUST end at
  the last moment anything in the document did. A session's MUST hold a `session` span over
  everything it did and each of its actions under it, of the action's own category; a
  program's, a `process` span per thread.
- `tracks` MUST be one per lane of a process's spans, packed by `stacked` -- named after the
  process's lane (`main` or the session's label, `flows`, `threads`), with ` ~<n>` for the
  n-th lane -- each carrying `process`, `name`, `first` (the id of its first span), `count`,
  `depths` (how many depths it has) and `spans`: columns `start`, `dur`, `depth`, `cat`,
  `name`, `model` (string indices where text), `in` and `out` (tokens, 0 where the slice says
  none), each `count` long and sorted by start. Where two spans start and end together a
  `session` MUST hold a `turn` and a `turn` everything else.
- A span's id MUST be its track's `first` plus its index in the track, numbering every span of
  the document from 0 in track order with no gaps. `layout` MUST differ between two documents
  where an id names a span of another process, track, start or category, and MUST stay the
  same while spans only grow longer.
- `spawns` MUST be columns `span` and `process`, sorted: an edge from the action that started a
  session to that session's process, and to every other session's from the call that opened
  it, or from the epic's own span where no call did.
- `summary` MUST carry `start` (0), `end`, counts of `processes`, `tracks` and `spans`, and
  `categories`: per category, its `count`, `time` (durations summed), `in` and `out`.
- What each span carried MUST NOT be in the document; `Timeline.span` MUST answer it by id --
  its `id`, `process`, `track`, `start`, `dur`, `depth`, `cat` and `name` as text, `at` (ISO
  8601 UTC) and `args` -- and MUST raise `KeyError` for an id the document does not have.
- `build` MUST lay out fifty thousand spans in well under a second.

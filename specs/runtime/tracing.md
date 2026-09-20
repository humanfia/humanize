# `runtime/tracing`

Reads a run back off the logs the coding agent CLIs wrote for themselves and off the programs
those turns started, and renders both on one timeline as a Chrome trace. It drives nothing.

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
) -> dict[str, Any]: ...

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
  require anything of what drives one.
- Profiling MUST sample rather than intercept and MUST NOT be able to stop a run: a process
  that cannot be read, or a profile that cannot be written, MUST leave the run as it was.
- A profile MUST be appended as each program goes rather than held to the end, and a start
  MUST be timed against the clock the rest of the trace is timed by.

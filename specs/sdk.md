# `sdk`

How a tool that is not humanize reaches humanize: a workspace run straight at, and a run held
apart from a terminal. It is not a layer humanize is built out of, and it carries out none of
what it offers -- every answer is `hmz.runtime`'s or `hmz.daemon`'s.

## API

```python
# __init__.py -- both ways in, and every type either hands back
__all__ = ["Accounts", "Daemon", "Daemons", "Epics", "Fallbacks", "Flows", "Flowverses",
           "Held", "Hmz", "Refused", "Run", "Session", "fakes"]
def __getattr__(name: str) -> object: ...  # `fakes` is `hmz.runtime.flowing.fakes`, whole

# daemons.py -- the runs being held apart from a terminal
class Daemons:
    def here(self, workspace: str | os.PathLike[str] | None = None) -> Daemon | None: ...
    def all(self) -> list[Daemon]: ...
    def hold(self, opens: Callable[[Held], object],
             workspace: str | os.PathLike[str] | None = None,
             *, columns: int = 0, rows: int = 0) -> Daemon: ...
```

## Requirements

- MUST offer both ways to a run: `Hmz`, which is the runtime in the process that asked, and
  `Daemons`, which is a run held where a terminal closing cannot end it.
- MUST hand out the same objects humanize itself holds rather than copies or wrappers of
  them, so that a tool and humanize are talking about one class.
- MUST NOT restate or recompose what it hands through: every answer is given where it is
  carried out.
- MUST NOT be named by any layer of humanize; layering tests refuse it.
- MUST load nothing until it is asked for, so that naming one thing here costs the one module
  it is written in rather than every layer humanize has.
- MUST raise `AttributeError` for a name it does not offer, as any module does.
- MUST spell what it offers for somebody who does not know how humanize is laid out: a name
  offered here MUST go on working where the thing behind it moves.
- `Daemons.hold` MUST take what opens a run rather than what to run, so that a tool may hold
  a flow, an interface of its own, or anything else it has written.
- `Daemons.here` MUST answer with nothing for a workspace holding no live run, and
  `Daemons.hold` MUST raise `OSError` where the run could not be held.

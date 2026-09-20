# `daemon`

A run held where a terminal closing cannot end it, and the terminals that come and go from
it. How a run is opened is not this package's: what it holds is a callable that opens one and
returns when it is over.

## API

```python
# __init__.py -- finding, starting and asking after a held run
@dataclass(frozen=True, slots=True)
class Daemon:
    at: Path
    workspace: str
    pid: int
    started: str
    alive: bool    # property
    def attach(self) -> int: ...
    def status(self) -> dict[str, Any]: ...
    def detach(self) -> int: ...
    def stop(self, *, seconds: float = 20.0) -> bool: ...
    def kill(self, *, seconds: float = 20.0) -> bool: ...
    def asked(self, said: dict[str, Any]) -> dict[str, Any]: ...
def running(workspace: str | os.PathLike[str] | None = None) -> Daemon | None: ...
def daemons() -> list[Daemon]: ...
def start(opens: Callable[[Held], object],
          workspace: str | os.PathLike[str] | None = None,
          *, columns: int = 0, rows: int = 0, seconds: float = 10.0) -> Daemon: ...
def __getattr__(name: str) -> object: ...  # `Hmz`, handed through from `hmz.runtime`
# session.py -- a run outliving its terminal, as whatever draws it sees it
@runtime_checkable
class Session(Protocol):
    attached: int
    def detach(self) -> int: ...
# serve.py -- the run on its pseudoterminal, and the terminals reading it
class Held:  # answers to `Session`
    attached: int
    def detach(self) -> int: ...
    def redrawn(self, hook: Callable[[], None]) -> None: ...
    def stopping(self, hook: Callable[[], None]) -> None: ...
    def says(self, hook: Callable[[], dict[str, Any]]) -> None: ...
    def start(self) -> None: ...
    def close(self, why: str = "the run is over") -> None: ...
def hosts(opens: Callable[[Held], object], at: Path, *, columns: int = 80,
          rows: int = 24, telling: int | None = None) -> None: ...
# proto.py -- the framed protocol between a run and the terminals reading it
HELLO: bytes; INPUT: bytes; OUTPUT: bytes; RESIZE: bytes; GONE: bytes; CONTROL: bytes
def frame(kind: bytes, payload: bytes = b"") -> bytes: ...
def spoken(kind: bytes, said: dict[str, Any]) -> bytes: ...
def asked(payload: bytes) -> dict[str, Any]: ...
class Frames:
    def feed(self, data: bytes) -> list[tuple[bytes, bytes]]: ...
```

## Requirements

- MUST hold whatever `opens` opens and MUST know nothing about how a run is opened.
- MUST offer `Hmz` under this package, as the same object `hmz.runtime` holds and fetched when named;
  what is held MUST reach the runtime by that name rather than over the socket.
- MUST be one daemon per workspace, claimed against a race rather than by looking first, released
  however the process ends, and MUST read a workspace as holding nothing unless the process is there
  and something answers on its socket.
- MUST answer what is running out of the runtime in the holding process, and a run that cannot be
  asked MUST answer as one running nothing rather than as one that cannot be read.
- MUST outlive the terminal it was started from: no controlling terminal, unreachable by a hangup, and
  nothing left for whoever asked for it to wait on or reap. It MUST tell them whether it came up, and
  MUST report a failure to start rather than make them wait out a timeout.
- MUST let go of terminals without stopping the run; stopping MUST be a separate request.
- MUST draw for a terminal that has just arrived from the top, without holding up what the run is
  drawing meanwhile, and MUST keep for it what was drawn before anybody was reading -- dropped whole
  rather than in part once it is more than is worth keeping, and dropped outright once one has read.
- MUST let go of a terminal that will not take what it is sent within a bounded time, MUST NOT let any
  terminal, thread, hook or socket end the run -- what failed MUST be written down where it can be
  read afterwards -- and MUST refuse a reported size of nothing or less.
- MUST carry framed messages both ways so that a resize and a run letting go are said rather than
  inferred, MUST refuse a length no frame of this protocol has, MUST NOT hand the same frame out
  twice, and MUST answer a question about the run on the connection it was asked on and under this
  same protocol.
- MUST put this terminal back however a reading ended, and MUST say why only afterwards.
- `Session` MUST be the whole of what an interface has to know about being held: how many terminals
  are reading, and how to let go of them.

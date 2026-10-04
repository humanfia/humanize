# `daemon`

Every workspace's runs on a machine held where a terminal closing cannot end them, for the
frontends that come and go from them. What a run is is not this package's: what it holds is
`hmz.runtime.Host`.

## API

```python
# __init__.py -- finding, starting and asking after a held run
@dataclass(frozen=True, slots=True)
class Daemon:
    at: Path
    workspace: str
    pid: int
    started: str
    protocol: int = 0  # the frontends' protocol a host speaks; 0 for an older humanize's
    alive: bool    # property
    def link(self, name: str = "", kind: str = "sdk", *, replay: bool = True) -> Link: ...
    def status(self) -> dict[str, Any]: ...
    def detach(self) -> int: ...
    def stop(self, *, seconds: float = 20.0) -> bool: ...
    def kill(self, *, seconds: float = 20.0) -> bool: ...
    def asked(self, said: dict[str, Any]) -> dict[str, Any]: ...
def running(workspace: str | os.PathLike[str] | None = None) -> Daemon | None: ...
def daemons() -> list[Daemon]: ...
def host(workspace: str | os.PathLike[str] | None = None, *, seconds: float = 10.0) -> Daemon: ...
def older(daemon: Daemon) -> str: ...  # what to say of a daemon of an older humanize
def __getattr__(name: str) -> object: ...  # `Hmz` and `Host`, handed through from `hmz.runtime`
# link.py -- one frontend's end of a workspace's runs, through the daemon or in this process
class Link:  # a context manager; iterable of messages until a listener is set
    client: str
    def told(self, message: dict[str, Any]) -> None: ...  # what carries messages hands them to
    def heard(self, listener: Callable[[dict[str, Any]], None]) -> None: ...
    def asked(self, said: Mapping[str, Any], *, seconds: float | None = None) -> dict[str, Any]: ...
    def start(self, flow: str | os.PathLike[str], task: str, *, agents: Mapping[str, Any] | None = None,
              envs: Mapping[str, Any] | None = None, params: Any = None, budget: Any = None,
              profile: bool = False, resume: bool | str | os.PathLike[str] = False,
              harness: str = "") -> dict[str, Any]: ...
    def say(self, text: str, *, to: str = "") -> dict[str, Any]: ...
    def answer(self, question: str, text: str) -> dict[str, Any]: ...
    def stop(self) -> dict[str, Any]: ...
    def force(self) -> dict[str, Any]: ...
    def afk(self, *, on: bool, role: str = "") -> dict[str, Any]: ...
    def claim(self, role: str, *, take: bool = False) -> dict[str, Any]: ...
    def release(self, role: str) -> dict[str, Any]: ...
    def board(self, key: str, value: str) -> dict[str, Any]: ...
    def aside(self, **said: Any) -> dict[str, Any]: ...
    def close(self) -> None: ...
def linked(host: Host, name: str = "", kind: str = "tui", *, replay: bool = True) -> Link: ...
def reached(at: Path, workspace: str, name: str = "", kind: str = "sdk", *,
            replay: bool = True) -> Link: ...
# carrying.py -- a host's runs carried between it and the frontends the daemon hands it
HOST_LOG: str; TAKEN: bytes
class Carrier:
    def __init__(self, host: Host, handing: socket.socket, said: dict[str, Any]) -> None: ...
    def start(self) -> None: ...
    def wait(self, timeout: float | None = None) -> bool: ...
    def close(self) -> None: ...
class Printed(io.TextIOBase): ...  # what a host process prints, said to its frontends
def keeps(reading: int, host: Host) -> None: ...  # what a host process writes, into its run's epic
def serves(host: Host, workspace: str, telling: int | None = None) -> None: ...
def logged(about: str) -> None: ...
# routing.py -- the machine's one daemon, handing each frontend to its workspace's host
class Router:
    def __init__(self, listening: socket.socket, at: Path) -> None: ...
    def start(self) -> None: ...
    def wait(self, timeout: float | None = None) -> bool: ...
    def close(self) -> None: ...
def serves(telling: int | None = None) -> None: ...
# proto.py -- the framed protocol between the runs and whatever is reading them
GONE: bytes; CONTROL: bytes; MESSAGE: bytes; PROTOCOL: int
def frame(kind: bytes, payload: bytes = b"") -> bytes: ...
def spoken(kind: bytes, said: dict[str, Any]) -> bytes: ...
def asked(payload: bytes) -> dict[str, Any]: ...
class Frames:
    def feed(self, data: bytes) -> list[tuple[bytes, bytes]]: ...
```

## Requirements

- MUST hold `hmz.runtime.Host` and MUST know nothing about how a run is opened.
- MUST offer `Hmz` and `Host` under this package, as the same objects `hmz.runtime` holds and
  fetched when named; what is held MUST reach the runtime by that name rather than over the socket.
- MUST be one daemon per machine and user, kept in `hmz.machine()` and never under `hmz.home()`,
  claimed against a race rather than by looking first, released however the process ends; it MUST
  hold every workspace's runs there, each in a host process of its own standing in that workspace,
  one host per workspace, and MUST read a workspace as holding nothing unless its host is there
  and the daemon answers on its socket.
- MUST answer what is running out of the runtime in the holding process, and a run that cannot be
  asked MUST answer as one running nothing rather than as one that cannot be read.
- MUST outlive the terminal it was started from: no controlling terminal, unreachable by a hangup, and
  nothing left for whoever asked for it to wait on or reap. It MUST tell them whether it came up, and
  MUST report a failure to start rather than make them wait out a timeout.
- MUST let go of frontends without stopping the runs; stopping MUST be a separate request.
- MUST NOT let any frontend, thread or socket end the runs -- what failed MUST be written down
  where it can be read afterwards: what belongs to a run into that run's epic, and what belongs to
  none beside the daemon's socket.
- MUST carry framed messages both ways so that the runs letting go is said rather than inferred,
  MUST refuse a length no frame of this protocol has, MUST NOT hand the same frame out twice, and
  MUST answer a question about the runs on the connection it was asked on and under this same
  protocol.

### Hosting

- A daemon MUST write the protocol it speaks beside its socket (`protocol`), MUST answer a reader
  speaking any other with `GONE` rather than leaving it waiting, and MUST read a daemon that wrote
  none, or another, as one of an older humanize, which nothing here reaches.
- The daemon MUST hand each frontend to the host of the workspace its first frame names, without
  reading that frame off the socket, MUST say so where no host holds it, MUST refuse a second
  host of one workspace, and MUST go once it holds no workspace -- its hosts closing their runs
  as a stop does once it has gone.
- `host` MUST find the host already holding a workspace's runs before it starts one, MUST start
  the daemon and then one where none is, and MUST refuse a machine an older humanize's daemon
  holds and a workspace a host it left still holds. The
  host process MUST read nothing, MUST write its own descriptors into the epic of the run it
  holds, MUST say what is printed in it to its frontends a line at a time, MUST ignore an
  interrupt, MUST close its runs on a terminate and wait a while for them to let go of what they
  made, and MUST report its own failures where that has been answered yes. `kill` MUST end one
  workspace's host and no other.
- MUST carry one JSON object a `MESSAGE` frame each way, and MUST carry out every request off the
  thread carrying the bytes: a frontend's requests in the order it made them, an aside apart
  from the rest. Each request MUST be answered with one reply naming it, and a frontend MUST say
  hello before anything else it asks.
- MUST NOT wait on a frontend: what one has not taken MUST be kept against it up to a ceiling,
  and one further behind MUST be told so after the frame it is in and let go of.
- A host MUST go once nothing is running or stopping and nobody is reading -- keeping a run that
  ended with nobody there, and that nobody stopped, for the next frontend to read -- and MUST go
  when it is stopped, telling every frontend why; one nobody ever reached MUST NOT be kept.
- Any frontend MAY close the whole host with `quit`, which MUST close it as a stop does: every
  run closed and every frontend let go, told why.
- `Link` MUST be one frontend whether the runs are in this process or held by a host, MUST hand
  over what it is told in order on a thread of its own, MUST raise the runtime's `Refused` for a
  request refused, and MUST raise `OSError` where no host will take it.

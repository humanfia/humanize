# `coganchor`

Everything humanize knows about driving a coding agent CLI — what each one is, driving it, which
account it runs as, which machine its turns land on, where a turn goes when the place taking it
cannot, what its tokens cost — and the anchor it is named for: running an agent on one machine and
having it act on another. Sub-packages: [agents](agents.md), [linux](linux.md),
[machines](machines.md), [providers](providers.md), [serve](serve.md).

## API

```python
# __init__.py -- the front door; each name below is fetched from anchor.py when it is named
__version__: str

# anchor.py -- where a session is said in Python
class NotInstalled(FileNotFoundError): ...   # the CLI a native turn wanted is not on the target

@dataclass(frozen=True, kw_only=True, slots=True)
class AnchorConfig:
    target: str = "local"
    harness: str = "local"
    broker: str = ""
    workspace: str | None = None
    chdir: str | None = None
    remote_path: str | None = None
    shadow: str | None = None
    local_paths: tuple[str, ...] = ()
    local_execs: tuple[str, ...] = ()
    private: tuple[str, ...] = ()
    redirects: tuple[tuple[str, str], ...] = ()
    net: str = "local"
    net_allow: tuple[str, ...] = ()
    token: str | None = None
    force: bool = False
    native: bool = False
    hushes: tuple[str, ...] = ()
    projects: tuple[tuple[str, str], ...] = ()
    carries: tuple[tuple[str, str], ...] = ()
    installs: str = ""
    @property
    def capabilities(self) -> frozenset[str]: ...  # the `anchor:` words this session answers to
    def command(
        self,
        argv: Sequence[str],
        *,
        swaps: Sequence[tuple[str, str]] = (),
        private: Sequence[str] = (),
        chdir: str = "",
    ) -> list[str]: ...
    def mount(self) -> tuple[Target, str, str]: ...  # target, workspace here, "VIRTUAL[:REAL]"

def check(config: AnchorConfig | None = None) -> dict[str, Any]: ...
def connect(command: Sequence[str], config: AnchorConfig | None = None) -> int: ...
def drive(command: Sequence[str], config: AnchorConfig | None = None) -> int: ...

# places.py -- the words a place and a road are named by
REMOTE: str
ISOLATED: str
MANAGED: str
PLACES: frozenset[str]
NATIVE_CLI: str
SUPERVISED: str
AFAR: str
ROADS: tuple[str, ...]
HOOKED: str
PRELOADED: str
INSIDE: frozenset[str]

# argv.py -- the same settings, off a command line and back onto one
def parser() -> ArgumentParser: ...
def settings(args: Namespace) -> AnchorConfig: ...
def render(config: AnchorConfig, argv: Sequence[str]) -> list[str]: ...
def options(config: AnchorConfig) -> list[str]: ...

# elsewhere.py -- putting the harness on a machine that is not this one
def harnessed(where: str, target: str) -> Target: ...
def elsewhere(config: AnchorConfig) -> bool: ...
def afar(config: AnchorConfig, argv: Sequence[str]) -> list[str]: ...

# backends.py -- every fact about a coding agent CLI that is not code
@dataclass(frozen=True, slots=True)
class Asked:
    env: str
    about: str
    secret: bool = False
    keep: bool = True
    fixed: str = ""

@dataclass(frozen=True, slots=True)
class Way:
    name: str
    about: str
    argv: tuple[str, ...] = ()
    asks: tuple[Asked, ...] = ()
    sets: tuple[tuple[str, str], ...] = ()
    args: tuple[str, ...] = ()
    stdin: str = ""

@dataclass(frozen=True, slots=True)
class Sign:
    fault: str
    says: str

@dataclass(frozen=True, slots=True)
class Hooked:
    seam: Literal["flag", "env", "config"]
    name: str

@dataclass(frozen=True, slots=True)
class Bundled:
    path: str
    says: str
    digest: str = ""

@dataclass(frozen=True, slots=True)
class Model:
    name: str
    efforts: tuple[str, ...]
    swarms: bool = False

@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    aliases: tuple[str, ...]
    # and the rest of one CLI as data: where it keeps its home, logs, journal, config and
    # skills; which efforts it takes and how long it may go silent; whether it swarms,
    # searches, restarts, resumes, shares a session or forks one; which hooks, preloads and
    # bundles it has seams for; which variables and credentials an account of it is; the ways
    # it can be asked what it runs; its endpoint and what fronts it; and the signs by which a
    # failure of it is read.
    def runs(self) -> str: ...
    def takes(self, effort: str) -> bool: ...
    def tags(self) -> frozenset[str]: ...
    def directory(self, environment: Mapping[str, str] | None = None) -> Path: ...
    def accounts(self) -> frozenset[str]: ...
    def hushes(self) -> frozenset[str]: ...
    def credentials(self) -> tuple[tuple[str, str], ...]: ...
    @staticmethod
    def configuration() -> Path: ...

PROFILES: tuple[Profile, ...]
UNKNOWN: Profile                    # what a CLI no profile names is read as
SIGNS: tuple[Sign, ...]
FAULTS: tuple[str, ...]
ALIKE: tuple[tuple[str, ...], ...]  # variables one backend reads under more than one name
SWARM: str
AUTO: str
AS_CONFIGURED: str                  # the rung every backend takes, that says nothing
DSH_SDK: str

def named(backend: str) -> Profile | None: ...
def profiles() -> tuple[Profile, ...]: ...
def read(spec: str) -> tuple[str, Profile, str, str, str]: ...  # "CLI[@ACCOUNT]/MODEL:EFFORT"
def serves(env: Mapping[str, str], backend: str) -> dict[str, str] | None: ...
def alike(variable: str) -> tuple[str, ...]: ...
def written(effort: str) -> str: ...
def permitted(permission: str) -> str: ...
def speaking() -> dict[str, tuple[str, ...]]: ...
def remember(name: str, command: Sequence[str]) -> str: ...
def forget(name: str) -> bool: ...
def program(command: str) -> str | None: ...
def elsewhere(command: str) -> str | None: ...
def installing(backend: str) -> str: ...
def journalled(
    backend: str,
    environment: Mapping[str, str] | None = None,
    *,
    within: float = 300.0,
) -> str: ...
def trouble(
    backend: str, *said: str | bytes | None, status: int = 0, journal: str = ""
) -> str: ...

# models.py -- what each backend runs, asked of it and kept until it is asked again
WAITING: float   # how long `ask` gives a backend to answer

def where(cli: str, provider: str = "") -> Path: ...
def asked(cli: str, provider: str = "") -> str: ...
def offered(cli: str, provider: str = "") -> tuple[Model, ...]: ...
def ask(cli: str, provider: str = "", seconds: float = WAITING) -> tuple[Model, ...]: ...

# prices.py -- what a token costs
SOURCE: str

@dataclass(frozen=True, slots=True)
class Price:
    model: str
    provider: str
    per_million: Mapping[str, float]

def where() -> pathlib.Path: ...
def price(model: str) -> Price | None: ...
def cost(usage: Mapping[str, float], model: str) -> float | None: ...
def money(dollars: float) -> str: ...
def refresh(*, wait: bool = False) -> bool: ...

# fallbacks.py -- where a turn goes when the place taking it cannot, and how often it retries
BASE: float
CEILING: float
THROTTLED: float
DEFAULT: str      # the policy a step retries under unless it named one

@dataclass(frozen=True, slots=True)
class Policy:
    name: str
    about: str

@dataclass(frozen=True, slots=True)
class Answer:
    fault: str
    about: str
    tries: int = 0
    held: bool = False
    policy: str = ""
    least: float = 0.0
    accounts: bool = True
    reopen: bool = False
    fix: str = ""

@dataclass(frozen=True, slots=True)
class Falls:
    spec: str
    to: str = ""
    tries: int = 0
    policy: str = DEFAULT
    timeout: float = 0.0
    def says(self) -> bool: ...

POLICIES: tuple[Policy, ...]
ANSWERS: tuple[Answer, ...]

def spec(backend: str, model: str, provider: str = "") -> str: ...
def reads(said: str) -> str: ...
def falls() -> list[Falls]: ...
def tried(said: str) -> Falls: ...
def points(said: str, at: str) -> Falls: ...
def retrying(said: str, tries: int, policy: str, timeout: float) -> Falls: ...
def clear(said: str) -> bool: ...
def chain(said: str) -> list[str]: ...
def named(policy: str) -> Policy | None: ...
def answers(fault: str) -> Answer: ...
def waits(policy: str, attempt: int, base: float = BASE) -> float: ...

# proto.py -- the wire, and the only module of this package the serving half may name
PROTOCOL_VERSION: int
CHUNK_SIZE: int
PLATFORMS: frozenset[str]
CASE_INSENSITIVE: frozenset[str]

class Kind(enum.Enum):
    REQ = "q"
    RSP = "r"
    ERR = "e"
    CHUNK = "c"
    END = "z"

class Op(enum.Enum):
    HELLO = "hello"
    LISTDIR = "listdir"
    STAT = "stat"
    READ = "read"
    WRITE = "write"
    MKDIR = "mkdir"
    RMDIR = "rmdir"
    UNLINK = "unlink"
    RENAME = "rename"
    SYMLINK = "symlink"
    LINK = "link"
    READLINK = "readlink"
    CHMOD = "chmod"
    TRUNCATE = "truncate"
    UTIME = "utime"
    EXEC = "exec"
    SIGNAL = "signal"
    CONNECT = "connect"

class Stream(enum.IntEnum):
    STDIN = 0
    STDOUT = 1
    STDERR = 2
    DATA = 3

class ProtocolError(Exception): ...

class RemoteOSError(OSError):
    @classmethod
    def from_meta(cls, meta: dict[str, Any]) -> RemoteOSError: ...

@dataclass(slots=True)
class Frame:
    kind: Kind
    msg_id: int
    meta: dict[str, Any] = field(default_factory=dict[str, Any])
    body: bytes = b""
    @property
    def op(self) -> Op | None: ...
    @property
    def stream(self) -> Stream: ...
    def encode(self) -> bytes: ...
    @classmethod
    def request(cls, msg_id: int, op: Op, body: bytes = b"", **meta: Any) -> Frame: ...
    @classmethod
    def reply(cls, msg_id: int, body: bytes = b"", **meta: Any) -> Frame: ...
    @classmethod
    def error(cls, msg_id: int, exc: OSError) -> Frame: ...
    @classmethod
    def chunk(cls, msg_id: int, stream: Stream, body: bytes) -> Frame: ...
    @classmethod
    def end(cls, msg_id: int, stream: Stream = Stream.DATA) -> Frame: ...

class Channel:
    def __init__(self, reader: IO[bytes], writer: IO[bytes], owns: Any = None) -> None: ...
    @classmethod
    def from_socket(cls, sock: Any) -> Channel: ...
    def send(self, frame: Frame) -> None: ...
    def recv(self) -> Frame | None: ...
    def close(self) -> None: ...

def hello_capabilities(said: dict[str, Any]) -> frozenset[str]: ...
def path_key(path: str, *, fold_case: bool = False) -> str: ...
def path_spellings(path: str) -> tuple[str, ...]: ...
def spelled_twice(path: str) -> bool: ...
def path_within(path: str, root: str, *, fold_case: bool = False) -> str | None: ...
def rewrite_path_prefix(
    text: str, prefix: str, replacement: str, *, insensitive: bool = False
) -> str: ...

# transport.py -- reaching the target, and putting the serving half there
@dataclass(frozen=True, slots=True)
class Target:
    scheme: str
    host: str = ""
    port: int = 0
    path: str = ""
    @classmethod
    def parse(cls, spec: str) -> Target: ...
    def describe(self) -> str: ...
    @property
    def meeting(self) -> Meeting: ...

@dataclass(frozen=True, slots=True)
class Road:
    target: Target
    prefix: tuple[str, ...]
    quotes: bool
    cache: str
    mirrors: str
    @classmethod
    def to(cls, target: Target) -> Road: ...
    def line(self, argv: Sequence[str]) -> list[str]: ...
    def run(
        self, argv: Sequence[str], feeding: bytes = b""
    ) -> subprocess.CompletedProcess[bytes]: ...
    def mirror(self, named: str) -> str: ...
    def hmz(
        self, argv: Sequence[str], *, setting: Sequence[tuple[str, str]] = ()
    ) -> list[str]: ...
    def installed(self) -> str: ...

@dataclass(slots=True)
class Transport:
    channel: Channel
    process: subprocess.Popen[bytes] | None = None
    def close(self) -> None: ...

def connect(target: Target, exports: list[str], token: str | None = None) -> Transport: ...
def serve_line(
    target: Target, exports: list[str], *, meeting: Meeting | None = None
) -> list[str]: ...
def python_command(
    args: list[str], bundle: str = "", setting: Sequence[tuple[str, str]] = ()
) -> list[str]: ...
def bundled() -> tuple[Path, str]: ...
def build_bundle(destination: Path | None = None) -> Path: ...

# rendezvous.py -- introducing two halves that cannot dial each other
ANCHOR: str
SERVE: str
PAIRING: float    # how long a half waits for the other
PUNCHING: float   # how long it tries to reach it directly first

def ticket() -> str: ...

@dataclass(frozen=True, slots=True)
class Meeting:
    ticket: str
    host: str
    port: int
    @classmethod
    def parse(cls, spec: str) -> Meeting: ...
    def __str__(self) -> str: ...

class Broker:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 0,
        *,
        patience: float = PAIRING,
        punching: float = PUNCHING,
    ) -> None: ...
    @property
    def address(self) -> tuple[str, int]: ...
    @property
    def carried(self) -> int: ...
    def start(self) -> tuple[str, int]: ...
    def serve_forever(self) -> None: ...
    def close(self) -> None: ...

def shared(advertise: str = "") -> tuple[Broker, str, int]: ...
def dial(meeting: Meeting, role: str, *, timeout: float = PAIRING) -> socket.socket: ...
```

## Requirements

- MUST offer driving a coding agent CLI as one capability reached through this package alone, MUST
  cost none of the anchor to name, and MUST write every fact about a CLI that is not code in
  `backends`, which MUST import nothing but the standard library and MUST hold no model id.
- A session MUST say which road it is, under `anchor:supervised` or `anchor:native-cli`, with
  `anchor:afar` said alongside the first and never the second; either way what a layer above spawns
  MUST be one command whose streams and status are the agent's, run where that layer cannot see.
- Supervising a turn MUST require Linux on x86-64 or aarch64, refusing any other at start-up with
  where it can run instead, and MUST ask that only of the harness's machine — where the account
  goes too. `check` MUST answer what a target is without running anything on it.
- A supervised agent MUST start in the workspace, or the directory in it the session opened at,
  named as the target names it, and MUST see the target inside it: the same names, contents, sizes,
  modes and timestamps at the same paths, with failures answered by the target's own error.
- Every spelling the target has for a path MUST reach the same file; a path outside the workspace
  MUST be answered as this machine answers it; a redirected path MUST answer with what it was
  redirected to, a call that cannot be given it failing rather than reading the path it named.
- Every program it spawns MUST behave as an ordinary local child, its parent released as soon as the
  child starts and signals travelling both ways; a command MUST NOT report a success it did not
  achieve, and nothing coganchor started MUST outlive it.
- A file it modified MUST reach the target before any command runs there and again at the end, and
  creating, removing, renaming, linking and changing modes MUST reach it first; its executable,
  state directory, redirect answers, private variables and connections MUST stay with it.
- Losing the link MUST NOT stop the agent: work needing the target fails and it exits with its own
  status. A mirror holding unrelated files, or last used elsewhere, MUST be refused unless told to.
- Only file contents MUST be expected to cross — not ownership, device nodes, extended attributes or
  a directory's own modes and times; only the common signals MUST be expected to reach a command; a
  32-bit process MUST NOT be traced; an unanswered request MUST be abandoned here, though it MAY
  still take effect there.
- A native session MUST refuse a CLI the target has not got before it has put anything on that
  machine, saying what is missing and the line that installs it there.
- What a provider sets MUST reach the turn as its environment and MUST NOT be written into a command
  line; what it hushes MUST be taken off on the target; a credential the CLI reads out of the user's
  own home MUST NOT be projected, and a turn with nothing else to carry the account MUST be refused.
- What a provider keeps as files MUST be projected into a directory only the target's own user may
  enter, unreadable by anyone else from the instant it exists, named to the CLI by a variable and
  never by a path, and removed when the turn is over whatever became of it.
- A native session MUST refuse a turn asking for the flow's own callbacks and MUST ask nothing of
  this machine's kernel; the skills a flow carries MUST be put into the target's workspace for the
  turn and taken out again, writing over nothing and removing only what was made.
- A ticket MUST be unguessable, MUST be the whole of what authenticates a peer, and MUST pair only
  the two halves that presented the same one; exactly one connection MUST carry a session and both
  halves MUST agree on which; nothing of it MUST reach a half before it has been told how the
  session is joined; and which introduction it got MUST NOT be observable.
- A backend's name MUST be the command it registers, its longer names MUST be aliases read on the
  way in with nothing recorded under one, and there MUST be one word every backend takes for no rung
  at all, absent from every ladder, at which nothing is said about how hard to think.
- What a backend runs MUST be asked of that backend, or of the account's own endpoint where one is
  set, kept per account and gone when the account is, and empty rather than guessed at until asked
  for; reading what was kept MUST cost one file read and reach nothing, and the credential the
  endpoint is asked under MUST NOT follow a redirect off the host the account named.
- A model's efforts MUST be its backend's ladder narrowed to the rungs that backend said the model
  takes, in that order, and the whole ladder where it said nothing of it.
- `price` and `cost` MUST cost one file read and no network; fetching MUST be refusable by an
  environment variable and leave what was kept however it fails; a model no source lists MUST answer
  nothing rather than nothing spent, a near miss MUST be a miss, and every figure MUST be a floor
  read under a backend's own accounting of the turn.
- A place MUST be `CLI[@ACCOUNT]/MODEL` and no more; one naming a CLI no backend answers to MUST be
  refused where written; a step MUST NOT point at its own place; a chain MUST end at the second
  sight of a place and MUST answer with that place first; and nothing MUST be retried by default,
  `answers` answering for a fault nothing recognised.
- An account's chain MUST be walked to its end before this one; the turn that moves MUST be taken in
  a new session, MUST carry the skills the flow gave the agent it left, and MUST be answered back
  through the session that asked. A stand-in MUST be configured exactly as the agent that could not
  run was; a setting the CLI taking over cannot be told MUST make it no stand-in.

# `coganchor/providers`

Which account a coding agent runs as, kept apart from which CLI it is: a named set of
credentials for one backend, the chain of accounts a turn carries on under when one fails, and
running a CLI with its own credential paths answered by that account's -- and its session paths
by the directory humanize keeps its sessions in. It does not say how
many times a failed turn is tried before the chain moves on, which is `hmz.coganchor.fallbacks`.

## API

```python
# store.py -- an account, and the tree of them
LOCAL = ""  # the account this machine is already signed into
ENV: backends.Way  # variables of your own, which every backend accepts

@dataclass(frozen=True, slots=True)
class Provider:
    cli: str
    name: str
    way: str = ENV.name
    env: Mapping[str, str] = field(default_factory=dict)
    args: tuple[str, ...] = ()
    made: str = ""
    fallback: str = ""
    @property
    def at(self) -> Path: ...
    def swaps(self) -> tuple[tuple[str, str], ...]: ...
    def command(self, argv: list[str] | tuple[str, ...]) -> list[str]: ...
    def held(self) -> dict[str, Any]: ...

def ways(cli: str) -> tuple[backends.Way, ...]: ...

def where(cli: str, name: str) -> Path: ...

def providers(cli: str = "") -> list[Provider]: ...

def find(cli: str, name: str) -> Provider | None: ...

def add(
    cli: str,
    name: str,
    way: str = ENV.name,
    env: Mapping[str, str] | None = None,
    args: tuple[str, ...] = (),
) -> Provider: ...

def ready(provider: Provider) -> None: ...

def remove(cli: str, name: str) -> bool: ...

def serves(one: Provider) -> tuple[str, ...]: ...

def copies(one: Provider, cli: str, name: str = "") -> Provider: ...

def alone(cli: str) -> Path: ...

def chain(provider: Provider) -> list[Provider]: ...

def points(cli: str, name: str, at: str) -> bool: ...

def env_of(said: str) -> dict[str, str]: ...

def filled(said: str, answers: Mapping[str, str]) -> str: ...

def environ(provider: Provider | None) -> dict[str, str]: ...

# login.py -- making one, by running the CLI's own login
def way_of(cli: str, name: str) -> Way | None: ...

def asked(way: Way, given: Mapping[str, str]) -> list[str]: ...

def make(
    cli: str, name: str, way: Way, answers: Mapping[str, str] | None = None
) -> Provider: ...

def sign_in(
    provider: Provider, way: Way, answers: Mapping[str, str] | None = None
) -> int: ...

def again(cli: str, name: str) -> Provider | None: ...

# redirect.py -- running a CLI with its credential paths answered by an account's, and
# its session paths by where humanize keeps them
UNSWAPPABLE = errno.EIO

@dataclass(frozen=True, slots=True)
class Swaps:
    pairs: tuple[tuple[str, str], ...] = ()  # credentials
    kept: tuple[tuple[str, str], ...] = ()  # sessions
    @classmethod
    def of(
        cls, pairs: Iterable[tuple[str, str]], kept: Iterable[tuple[str, str]] = ()
    ) -> Swaps: ...
    def swap(self, path: str) -> str | None: ...
    def answer(self, path: str) -> tuple[str, bool] | None: ...  # and whether it is kept
    def __bool__(self) -> bool: ...

def head(named: str) -> str: ...
def answered(named: str, instead: str, path: str) -> str | None: ...

def read(said: Iterable[str], kept: Iterable[str] = ()) -> Swaps: ...

def supervises() -> bool: ...

def command(
    swaps: Iterable[tuple[str, str]],
    argv: Sequence[str] | list[str],
    kept: Iterable[tuple[str, str]] = (),
) -> list[str]: ...

def run(swaps: Swaps, argv: Sequence[str]) -> int: ...

def swept(pid: int) -> None: ...

def failed(status: int) -> int: ...
```

## Requirements

- One account MUST be one directory under `~/.humanize/providers/<cli>/<name>/`, this user's
  alone at every level, holding what it was made by and the credentials the CLI itself wrote.
- A name MUST be one path component of letters, digits, dot, dash and underscore; anything
  else MUST be refused where it is given and MUST NOT be listed as an account.
- The account this machine is already signed into MUST be an account here too, named `""`,
  answered by `find` for every backend, absent from `providers`, refused by `where`, and
  answering no swaps and no variables. What is written down about it MUST be kept outside the
  tree of accounts humanize made.
- `swaps` MUST answer only the paths `hmz.coganchor.backends` names as that backend's
  credentials -- never its sessions, settings or skills -- and MUST answer the same path with
  its links followed where that is a different spelling.
- `serves` MUST answer nothing for an account that cannot travel whole; `copies` MUST write
  under the same name, over one already there, and MUST raise `ValueError` where that backend
  could not be run as this account.
- Where a turn goes when an account fails MUST be said on the account; `chain` MUST start
  there, MUST end at an account that is not there or one already walked, and MUST never be
  empty. `points` MUST raise `ValueError` for a fallback naming itself or an account that is
  not there. A chain MAY begin at `LOCAL` and MUST NOT end there.
- `add` MUST replace what it holds rather than merge it, MUST keep the fallback an account
  already had, and MUST leave credentials a login left behind alone; `ready` MUST make every
  place a credential will land before anything writes one.
- A turn under an account MUST run with that account's variables and with the backend's own
  credential paths answered by the account's, and the CLI MUST NOT be asked to cooperate or be
  told any of it.
- A turn MUST keep the paths `hmz.coganchor.backends` names as its backend's sessions where
  its agent keeps them, whatever account it runs as, the one this machine is signed into
  included -- the same path under a directory per backend, made as the CLI writes into it --
  and never its settings, skills or credentials; a session MUST NOT be read as a copy.
- A turn that answers no path MUST cost no supervisor: `command` MUST then be the backend's
  own command line unchanged, and an anchored turn MUST hand what it answers to the anchor
  rather than be wrapped here.
- A path that is answered but cannot be rewritten MUST fail the syscall with `UNSWAPPABLE`,
  and a run that cannot be supervised at all MUST be refused rather than run unsupervised --
  but for sessions alone, which on a machine that cannot supervise one MUST stay where the CLI
  keeps them: refusing every turn there would be humanize refusing to run.
- A name written with a `*` MUST answer every path whose names match its own, and everything
  inside one, the same on both halves of a supervised turn; nothing else in a path MUST be read
  as a wildcard. `supervises` MUST answer whether this machine will supervise a turn by having
  it supervise one, and MUST ask again after a no.
- Whoever kills a supervisor MUST call `swept` once it has been waited on, so no copy of a
  credential outlives the turn it was made for.
- Nothing here MUST print or echo a secret: what is shown of an account MUST be the names of
  the variables it sets and never their values.

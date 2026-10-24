# SDK

## 1. Scope

This document governs the Python module `hmz.sdk`: every name it offers, the signature of every
public member of each, what each member does as observed by its caller, and what each raises. It
is the supported way for a program that is not **hmz** to drive **hmz** on **this machine**: one
**workspace** straight in the calling process (`Hmz`), and the **epics** held by the **daemon**
for every **frontend** (`Daemons`, `Daemon`, `Link`).

Out of scope:

- The flow API a **flow author** writes against, and the in-memory drivers of `fakes`:
  `api/flows.md`.
- The wire protocol between a frontend and the daemon: `api/daemon.md`.
- The HTTP API served by `hmz web`: `api/http.md`.
- The settings files and every other file on disk: `api/settings.md`, `api/files/home.md`,
  `api/files/epics.md`, `api/files/machine.md`.
- The `-a`, `-e`, `-f` and `-p` spellings and the `hmz exec` command line: `api/cli.md`.
- What an **agent**, **account**, **runtime**, **placement** and backup target are and how they
  behave: `features/agents.md`, `features/accounts.md`, `features/environments.md`,
  `features/placements.md`, `features/backups.md`.

## 2. Definitions

**2.1** Every term of `README.md` §5 MUST carry the meaning given there.

**2.2** **Offered name**: a name listed in `hmz.sdk.__all__`.

**2.3** **Returned type**: a type that is not an offered name and that a member of an offered
name returns, accepts, or exposes as an attribute.

**2.4** An agent spec MUST be as `features/agents.md` §2.2 defines it: the text an `-a` option
takes after `<role>=`.

**2.5** **Environment spec**: the text an `-e` option takes after `<role>=`, as `api/cli.md`
defines it.

**2.6** **Flow name**: the text an `-f` option takes, as `api/cli.md` defines it: a name a flow
is offered under, a ref, or a path.

**2.7** A place MUST be as `features/agents.md` §2.3 defines it.

**2.8** The term host MUST carry the meaning `features/daemons.md` §2.1 gives it.

**2.9** **Slot**: the text naming one of a workspace's hosts, as `api/daemon.md` §2.6 defines it:
`""` for the workspace's own host, `chat:<hex>` for one chat's.

**2.10** **Epic directory**: the directory one epic is written into, as `api/files/epics.md`
defines it. An epic is named by its epic directory's base name.

## 3. The module

```python
__all__ = ["Accounts", "Daemon", "Daemons", "Epics", "Fallbacks", "Flows", "Flowverses", "Hmz",
           "Host", "Link", "Refused", "Run", "Runtimes", "fakes"]
def __getattr__(name: str) -> object: ...
```

**3.1** `hmz.sdk.__all__` MUST be exactly the fourteen names listed above.

**3.2** Importing `hmz.sdk` MUST NOT import any other module of the `hmz` package.

**3.3** Accessing an offered name MUST import only the modules that name requires.

**3.4** For every offered name other than `Daemons` and `fakes`, `hmz.sdk.<name>` MUST be the
identical object (`is`) that `hmz.runtime.<name>` holds for `Accounts`, `Epics`, `Fallbacks`,
`Flows`, `Flowverses`, `Hmz`, `Host`, `Refused`, `Run` and `Runtimes`, and that `hmz.daemon.<name>`
holds for `Daemon` and `Link`.

**3.5** `hmz.sdk.fakes` MUST be the identical module object `hmz.runtime.flowing.fakes`.

**3.6** `from hmz.sdk import fakes` MUST succeed; `import hmz.sdk.fakes` MUST raise
`ModuleNotFoundError`.

**3.7** Accessing a name of `hmz.sdk` that is not an offered name MUST raise `AttributeError` with
the message `module 'hmz.sdk' has no attribute '<name>'`.

**3.8** An offered name MUST keep its meaning, its signature and the behaviour this document
states across releases until this document is changed.

**3.9** The fields and members of a returned type stated in §20 MUST hold as stated; members of a
returned type that this document does not state are not part of this API.

## 4. `Hmz`

```python
class Hmz:
    def __init__(self, workspace: str | os.PathLike[str] | None = None) -> None: ...
    workspace: Path      # property
    home: Path           # property
    settings: Settings   # property
    flows: Flows         # property
    verses: Flowverses   # property
    accounts: Accounts   # property
    runtimes: Runtimes   # property
    fallbacks: Fallbacks # property
    epics: Epics         # property
    backups: Backups     # property
    daemons: Registry    # property; the type of §14, not hmz.sdk.Daemons
    def backends(self) -> tuple[Profile, ...]: ...
    def installed(self) -> dict[str, tuple[Model, ...]]: ...
    def installable(self) -> dict[str, tuple[Model, ...]]: ...
    def adding(self, backend: str) -> str: ...
    def serves(self, backend: str, role: AgentRole | None) -> bool: ...
    def ready_to_open(self, backend: str) -> bool: ...
    def reports(self) -> bool: ...
    def carried(self, pages: Sequence[str]) -> list[tuple[str, dict[str, Any]]]: ...
    def read(self, argv: list[str]) -> Line: ...
    def runner(self, flow: str | os.PathLike[str], *,
               agents: Mapping[str, str | AgentDriver] | Iterable[AgentSpec] = (),
               envs: Mapping[str, str | EnvDriver] | Iterable[EnvSpec] = (),
               params: Mapping[str, Any] | FlowParams | None = None,
               budget: Budget | Mapping[str, Any] | None = None,
               profile_flow: bool = False, profile_environment: bool = False,
               resume: bool | str | os.PathLike[str] = False,
               backup: Iterable[str] | None = None) -> Runner: ...
    def run(self, flow: str | os.PathLike[str], task: str, *,
            agents: Mapping[str, str | AgentDriver] | Iterable[AgentSpec] = (),
            envs: Mapping[str, str | EnvDriver] | Iterable[EnvSpec] = (),
            params: Mapping[str, Any] | FlowParams | None = None,
            budget: Budget | Mapping[str, Any] | None = None,
            profile_flow: bool = False, profile_environment: bool = False,
            resume: bool | str | os.PathLike[str] = False,
            outworlder: OutworlderDriver | None = None,
            backup: Iterable[str] | None = None) -> Run: ...
    def exec(self, argv: list[str]) -> Any: ...
    def host(self, slot: str = "") -> Host: ...
```

### 4.1 Construction and properties

**4.1.1** `Hmz(workspace)` MUST read no file, start no process and import no flow.

**4.1.2** `Hmz.workspace` MUST be `Path(workspace)` as given, without expanding `~` and without
resolving links; where `workspace` is `None`, it MUST be the current directory at the moment the
property is read.

**4.1.3** `Hmz.home` MUST be the **home** directory as `api/files/home.md` locates it, and reading
it MUST NOT create it.

**4.1.4** `Hmz.settings` MUST read and write the settings of `api/settings.md` for this workspace
and this machine; members of its type are not part of this API.

**4.1.5** `Hmz.flows`, `Hmz.accounts`, `Hmz.runtimes`, `Hmz.fallbacks`, `Hmz.epics`,
`Hmz.backups` and `Hmz.daemons` MUST each return the same object on every access of one `Hmz`
instance.

**4.1.6** `Hmz.verses` MUST be the identical object `Hmz.flows.verses`.

**4.1.7** `Hmz.epics` MUST be the `Epics` of `Hmz.workspace`.

### 4.2 Backends

**4.2.1** `Hmz.backends()` MUST return one entry per coding-agent CLI **hmz** drives, installed or
not, each having at least the attributes `name: str`, `aliases: tuple[str, ...]` and
`efforts: tuple[str, ...]`.

**4.2.2** `Hmz.installed()` MUST map the name of every backend whose program, and whatever its
optional extra brings, is present on this machine to the models it last reported it runs; a
backend never asked MUST map to `()`.

**4.2.3** `Hmz.installable()` MUST map the name of every backend whose program is present and
whose Python extra is absent to the models it will offer once the extra is added.

**4.2.4** `Hmz.adding(backend)` MUST return the text naming what is missing for that backend and
the command that adds it.

**4.2.5** `Hmz.serves(backend, role)` MUST return `False` where the backend is not the harness
`role` names or cannot provide what `role` declares it requires, and `True` otherwise; `role`
`None` MUST be answered for an agent that fills no declared role.

**4.2.6** `Hmz.ready_to_open(backend)` MUST return whether the backend is permitted to be chosen
as a fallback agent without the user choosing it: never for `litellm`, and for `dsh` only once
its local account in this workspace is configured.

### 4.3 Reporting and settings carried to another daemon

**4.3.1** `Hmz.reports()` MUST start reporting **hmz**'s own failures where, and only where, the
user has answered yes to reporting or `HUMANIZE_SENTRY` is `on`, and MUST return whether
failures are being reported.

**4.3.2** `Hmz.reports()` MUST NOT ask the user anything.

**4.3.3** `Hmz.carried(pages)` MUST return, for each page named out of `general`, `fallback`,
`runtimes` and `backup`, the HTTP path and the JSON body that writes that page's settings of
this machine to another daemon's `hmz web`, as `api/http.md §13` defines those paths.

**4.3.4** `Hmz.carried(pages)` MUST NOT include any value that only a secret sets.

### 4.4 Reading a command line

**4.4.1** `Hmz.read(argv)` MUST parse `argv` as the arguments of `hmz exec` after `exec`, as
`api/cli.md` defines them, and return a `Line` (§20.1).

**4.4.2** `Hmz.read(argv)` MUST NOT import any flow.

**4.4.3** Where `argv` is not a valid `hmz exec` line, `Hmz.read(argv)` MUST write the usage and
the error to standard error and raise `SystemExit(2)`.

**4.4.4** Where `argv` asks for help, `Hmz.read(argv)` MUST write the help to standard output and
raise `SystemExit(0)`.

### 4.5 Making an epic

**4.5.1** `Hmz.runner(flow, ...)` MUST load the flow `flow` names, make a driver for every role
it declares, check everything `hmz exec` checks before an epic starts, and return a `Runner`
whose members are not part of this API.

**4.5.2** Making a driver in `Hmz.runner` MUST NOT start any agent CLI and MUST NOT reach any
other machine.

**4.5.3** `Hmz.run(flow, task, ...)` MUST return a `Run` equal in effect to
`Run(self.runner(flow, ...), task, outworlder=outworlder)` with every other argument passed
through unchanged.

**4.5.4** `Hmz.run` MUST NOT start the epic.

**4.5.5** The parameter `flow` MUST be read as a flow name.

**4.5.6** The parameter `agents` MUST accept a mapping from role name to an agent spec or an
`AgentDriver`, or an iterable of `AgentSpec`.

**4.5.7** The parameter `envs` MUST accept a mapping from role name to an environment spec or an
`EnvDriver`, or an iterable of `EnvSpec`.

**4.5.8** The parameter `params` MUST accept a mapping, whose text values are read as `-p` reads
them, or an instance of the flow's `FlowParams`; `None` MUST mean the flow's defaults.

**4.5.9** The parameter `budget` MUST accept a `Budget` or a mapping validated as `Budget`
validates one; `None` MUST mean an unlimited cost for the built-in `chat` flow and MUST be
refused for every other flow.

**4.5.10** `profile_flow` and `profile_environment` MUST mean what `--profile-flow` and
`--profile-environment` mean in `api/cli.md`.

**4.5.11** `resume=False` MUST start the flow from the beginning; `resume=True` MUST pick up the
newest epic of that flow in this workspace that can be picked up; a path MUST pick up the epic
in that epic directory.

**4.5.12** `outworlder` MUST fill every `Outworlder` role of the flow; `None` MUST fill each as
always away.

**4.5.13** `backup` MUST name the backup targets the epic is backed up to; `None` MUST mean the
default targets of `api/settings.md`.

**4.5.14** `Hmz.run` and `Hmz.runner` MUST raise `Refused` for everything `hmz exec` refuses
before an epic starts, with the same message `hmz exec` prints after `hmz exec: error: `.

**4.5.15** `Hmz.run` and `Hmz.runner` MUST raise `Refused` with the message `<flow>: duplicate
agent role '<role>'` for an agent role given twice, and `<flow>: duplicate environment role
'<role>'` for an environment role given twice.

**4.5.16** `Hmz.run` and `Hmz.runner` MUST raise `Refused` with a message starting `the budget is
invalid: ` for a budget mapping `Budget` does not validate.

**4.5.17** `Hmz.run` and `Hmz.runner` MUST raise `Refused` with the message `<epic> has no saved
progress to resume from` for a `resume` path whose epic holds no journal entry.

**4.5.18** A `Line` read by `Hmz.read` and passed field by field to `Hmz.run` MUST make an epic
identical in effect to the one `Hmz.exec` makes of the same `argv`.

**4.5.19** Where each agent's harness runs MUST NOT be a parameter of `Hmz.run`: it MUST follow
from the runtime the work is placed on, as `features/placements.md` states.

### 4.6 Executing a command line

**4.6.1** `Hmz.exec(argv)` MUST do `Hmz.read(argv)`, then `Hmz.run(...)` with every field of the
`Line`, then `Run.run()`, and return what the flow returned.

**4.6.2** `Hmz.exec(argv)` MUST draw nothing, MUST install no signal handler, and MUST raise
`Refused`, `BudgetExceeded` and what the flow raises unchanged rather than exit.

### 4.7 Hosts

**4.7.1** `Hmz.host(slot)` MUST return one `Host` per `Hmz` instance and slot, made on the first
call with that slot and returned unchanged on every later call.

**4.7.2** `Hmz.host(slot)` MUST raise `ValueError` for a slot that is neither `""` nor
`chat:<hex>`.

## 5. `Run`

```python
class Run:
    def __init__(self, runner: Runner, task: str, *,
                 outworlder: OutworlderDriver | None = None) -> None: ...
    flow: str; ref: str; chats: bool; task: str; declaration: Declaration
    budget: Budget; profile_flow: bool; profile_environment: bool
    backup: tuple[str, ...]; usage: Usage; agents: tuple[AgentBase, ...]
    names: dict[str, str]; epic: Path | None; running: bool
    raised: BaseException | None; result: Any                     # properties
    def unreadable(self) -> str: ...
    def watch(self, listener: Callable[[AgentBase, SessionBase | None, Event], None]) -> None: ...
    def opened(self, callback: Callable[[str, AgentBase, SessionBase, Placement | None], None]
               ) -> None: ...
    def noticed(self, callback: Callable[[str], None]) -> None: ...
    def run(self) -> Any: ...
    def start(self) -> None: ...
    def wait(self, timeout: float | None = None) -> bool: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...
```

One `Run` is one epic.

### 5.1 Properties

**5.1.1** Constructing a `Run` MUST NOT start the epic.

**5.1.2** `Run.flow` MUST be the flow as it was named; `Run.ref` MUST be its canonical ref.

**5.1.3** `Run.chats` MUST be `True` where, and only where, the flow is the built-in `chat`
flow, decided by where the flow is defined and not by its name.

**5.1.4** `Run.declaration` MUST be what the flow declares (§20.3).

**5.1.5** `Run.budget` MUST be the `Budget` the epic is held to; `Run.usage` MUST be what it has
spent so far, as `api/flows.md` defines `Usage`.

**5.1.6** `Run.backup` MUST be the names of the backup targets the epic goes to.

**5.1.7** `Run.agents` MUST be the agent behind each **session** still open, oldest first.

**5.1.8** `Run.names` MUST map each agent role to the name of the agent filling it.

**5.1.9** `Run.epic` MUST be the epic directory once the epic has started writing it, and
`None` before.

**5.1.10** `Run.running` MUST be `True` from `start()` until the flow has returned or raised.

**5.1.11** After an epic started with `start()` has ended, `Run.raised` MUST be what the flow
raised (`asyncio.CancelledError` after `stop()`), or `None`, and `Run.result` MUST be what the
flow returned.

### 5.2 Driving

**5.2.1** `Run.run()` MUST drive the flow to its end and return what it returned or raise what it
raised: on an event loop of its own in the calling thread, or, where the calling thread already
runs an event loop, on a new thread the call waits for.

**5.2.2** `Run.run()` MUST raise `Refused` before the flow is called where an environment cannot
be reached or cannot provide what its role declares.

**5.2.3** `Run.start()` MUST drive the flow on a new thread and return at once; a second
`start()` MUST raise `RuntimeError`.

**5.2.4** `Run.wait(timeout)` MUST block until the epic ends or `timeout` seconds pass, and
return whether it ended.

**5.2.5** `Run.stop()` MUST be callable from any thread, MUST interrupt the turn under way, MUST
make every flow call raise `asyncio.CancelledError` where it stands, and MUST return without
waiting for the flow to unwind.

**5.2.6** `Run.close()` MUST do what `stop()` does and then close every session and agent still
open without waiting.

### 5.3 Observing

**5.3.1** `Run.watch(listener)` MUST call `listener` once for every event of every session of
the epic, from the thread that read the event.

**5.3.2** While at least one listener is registered with `watch`, agent CLIs MUST NOT write
their own progress to the calling process's standard output or standard error.

**5.3.3** `Run.opened(callback)` MUST call `callback(role, agent, session, placement)` on the
epic's event loop as each session opens and before its first turn; `placement` MUST be `None`
where the driver reports none.

**5.3.4** `Run.noticed(callback)` MUST call `callback(text)` with every notice **hmz** gives
about the epic before the flow is called, as `features/epics.md` defines notices.

**5.3.5** `Run.unreadable()` MUST return, in words, every limit of the budget that nothing the
epic drives can enforce, or `""` where there is none.

**5.3.6** Where the budget has a finite `cost`, `Run.unreadable()` MUST first bring a missing or
stale price list up to date, waiting no longer than that fetch's own timeout and not at all once
the epic has been stopped.

## 6. `Refused`

```python
class Refused(ValueError): ...
```

**6.1** `Refused` MUST be raised for an epic, or a request to a host, refused before anything of
it ran.

**6.2** `str()` of a `Refused` MUST be the one sentence that says why, identical to what
`hmz exec` prints after `hmz exec: error: ` and to what a host answers every frontend.

**6.3** Where an underlying exception caused the refusal, it MUST be the `__cause__` of the
`Refused`.

## 7. `Flows`

```python
class Flows:
    def __init__(self, workspace: str | os.PathLike[str] | None = None) -> None: ...
    verses: Flowverses  # property
    def all(self) -> list[Offer]: ...
    def find(self, named: str) -> str: ...
    def about(self, named: str) -> str: ...
    def declared(self, named: str | os.PathLike[str]) -> Declaration: ...
    def resumes(self, named: str | os.PathLike[str]) -> bool: ...
    def fork(self, named: str, into: str | os.PathLike[str] | None = None) -> str: ...
    def running(self) -> tuple[LiveCall, ...]: ...
```

**7.1** `Flows.all()` MUST return every flow on offer in the workspace, in offer order, as
`Offer` values (§20.3).

**7.2** `Flows.find(named)` MUST return the file a flow name resolves to, or `""` where nothing
resolves; a text starting with `.`, `/` or `~` MUST be read as a path, and any other text as a
name, never as a file of that name in the current directory.

**7.3** `Flows.about(named)` MUST return the flow's one-line description, or `""`.

**7.4** `Flows.declared(named)` MUST import the flow and return what it declares as it is now;
a `str` MUST be read as `-f` reads it, and an `os.PathLike` always as a path.

**7.5** `Flows.declared(named)` MUST raise the `FlowException` of `api/flows.md` for a flow
that cannot be loaded.

**7.6** `Flows.resumes(named)` MUST import the flow and return whether an epic of it can be
picked up.

**7.7** `Flows.fork(named, into)` MUST copy the flow, every file it imports from its own
directory and its skills into `.hmz/flows/` of the workspace, or into `into`, MUST NOT copy an
installed flow's installation record, and MUST return the directory written.

**7.8** `Flows.fork` MUST raise `ValueError` where `named` is not a flow or is already a copy in
that place, and `OSError` where the copy fails.

**7.9** `Flows.running()` MUST return every flow call in progress in the calling process, oldest
first, as `LiveCall` values (§20.3).

## 8. `Flowverses`

```python
class Flowverses:
    def __init__(self, workspace: str | os.PathLike[str] | None = None) -> None: ...
    def all(self) -> list[Flowverse]: ...
    def nearest(self) -> list[Flowverse]: ...
    def find(self, name: str) -> Flowverse | None: ...
    def add(self, url: str, name: str = "") -> Flowverse: ...
    def fetch(self, name: str) -> Flowverse: ...
    def remove(self, name: str) -> bool: ...
    def holds(self, one: Flowverse) -> list[Offer]: ...
    def index(self, name: str) -> Index: ...
    def install(self, flow: str, version: str = "") -> list[Installed]: ...
    def uninstall(self, flow: str) -> bool: ...
    def installed(self) -> list[Installed]: ...
    def updates(self) -> list[Update]: ...
    def edited(self, one: Flowverse) -> bool: ...
    def standing(self, one: Flowverse) -> str: ...
    def where(self, name: str) -> Path: ...
    def plain(self, url: str) -> str: ...
    def whence(self, one: Flowverse, nowhere: str = "-") -> str: ...
```

**8.1** A `flow` argument of `install` and `uninstall` MUST be the name the flow is offered
under: `<flow>` or `<user>/<flow>` for one of `official`'s, `@<flowverse>/<flow>` or
`@<flowverse>/<user>/<flow>` for one of another flowverse's.

**8.2** `Flowverses.all()` MUST return every flowverse in offer order: `official`, then each
added one by name, then `local`, then `user`.

**8.3** `Flowverses.nearest()` MUST return every flowverse in the order a bare flow name is
looked up: `local`, `user`, `official`, then each added one.

**8.4** `Flowverses.find(name)` MUST return the flowverse of that name, or `None`.

**8.5** `Flowverses.add(url, name)` MUST clone the index at `url` (a URL, a path, or
`owner/repo` on GitHub) under `name`, or under the repository's name where `name` is `""`, and
MUST install nothing.

**8.6** `Flowverses.add` MUST raise `ValueError` for a name taken, reserved (`official`, `local`,
`user`) or not a valid directory name, and `OSError` where the clone fails.

**8.7** `Flowverses.fetch(name)` MUST fetch the index again, or for the first time, discarding
local changes to the clone, and MUST NOT change any installed flow.

**8.8** `Flowverses.fetch` MUST raise `ValueError` for an unknown name or for `local` or `user`,
and `OSError` where git fails.

**8.9** `Flowverses.remove(name)` MUST delete the index and every flow installed from it, and
MUST return whether the flowverse existed; it MUST raise `ValueError` for `official`, `local` and
`user`.

**8.10** `Flowverses.holds(one)` MUST return what the flowverse offers to run: the built-in and
installed flows for `official`, the installed flows for an added flowverse, and the flows in the
directory for `local` and `user`; it MUST import every flow it returns and MUST NOT return a flow
the index only lists.

**8.11** `Flowverses.index(name)` MUST return what the index lists as last fetched, reading
only the index files; it MUST return an empty `Index` for `local`, `user`, an unfetched
flowverse and an unknown name.

**8.12** `Flowverses.install(flow, version)` MUST install that release and every flow it
depends on, MUST switch an installed flow of another version to that one, and MUST return what is
now installed of every flow the install touched, the asked-for flow last.

**8.13** `version=""` MUST select the newest release that is not a prerelease, else the newest
prerelease.

**8.14** `Flowverses.install` MUST raise `ValueError` for an unknown flowverse, flow or release,
an unfetched index, a dependency cycle, a version range no release satisfies, and an install that
breaks the range another installed flow requires; and `OSError` where fetching or copying fails.

**8.15** `Flowverses.uninstall(flow)` MUST remove an installed flow and return whether it was
installed; it MUST raise `ValueError` where another installed flow depends on it and `OSError`
where it cannot be removed.

**8.16** `Flowverses.installed()` MUST return every installed flow, by flowverse and then by
name.

**8.17** `Flowverses.updates()` MUST return every installed flow whose index, as last fetched,
lists a newer release.

**8.18** `Flowverses.edited(one)` MUST return whether the clone holds changes a fetch would
discard, and `False` for a flowverse that is not a clone.

**8.19** `Flowverses.standing(one)` MUST return the commit the clone stands at, or `""`.

**8.20** `Flowverses.where(name)` MUST return the index's directory whether or not it has been
fetched.

**8.21** `Flowverses.plain(url)` MUST return `url` with any credentials removed.

**8.22** `Flowverses.whence(one, nowhere)` MUST return the flowverse's credential-free URL; for
`local`, the text `your own flows in .hmz/flows`; for `user`, the text
`your own flows in ~/.hmz/flows`; and `nowhere` for a directory with no readable origin.

## 9. `Accounts`

```python
class Accounts:
    GATEWAY: str  # "LiteLLM"
    def all(self, cli: str = "") -> list[Provider]: ...
    def ways(self, cli: str) -> tuple[Way, ...]: ...
    def wants(self, cli: str) -> str: ...
    def way(self, cli: str, name: str) -> Way | None: ...
    def find(self, cli: str, name: str) -> Provider | None: ...
    def where(self, cli: str, name: str) -> Path: ...
    def write(self, cli: str, name: str, way: str = "", env: Mapping[str, str] | None = None,
              args: tuple[str, ...] = ()) -> Provider: ...
    def make(self, cli: str, name: str, way: Way,
             answers: Mapping[str, str] | None = None) -> Provider: ...
    def sign_in(self, provider: Provider, way: Way,
                answers: Mapping[str, str] | None = None) -> int: ...
    def asks(self, way: Way, given: Mapping[str, str]) -> list[str]: ...
    def serves(self, one: Provider) -> tuple[str, ...]: ...
    def copies(self, one: Provider, cli: str, name: str = "") -> Provider: ...
    def remove(self, cli: str, name: str) -> bool: ...
    def env(self, said: str) -> dict[str, str]: ...
    def environ(self, provider: Provider | None) -> dict[str, str]: ...
    def models(self, cli: str, provider: str = "") -> tuple[Model, ...]: ...
    def asked(self, cli: str, provider: str = "") -> str: ...
    def stale(self, cli: str, provider: str = "") -> bool: ...
    def ask(self, cli: str, provider: str = "", seconds: float | None = None
            ) -> tuple[Model, ...]: ...
```

**9.1** Every `cli` argument MUST accept any name or alias of a backend; an account `name` of
`""` MUST mean this machine's own sign-in of that CLI.

**9.2** `Accounts.GATEWAY` MUST be `"LiteLLM"`, the name the ways in through the local LiteLLM
gateway are grouped under.

**9.3** `Accounts.all(cli)` MUST return every account, or every account of one backend, by
backend and then by name.

**9.4** `Accounts.ways(cli)` MUST return every way the backend can be signed into, in offer
order; `Accounts.way(cli, name)` MUST return one of them, or `None`.

**9.5** `Accounts.wants(cli)` MUST return the command that installs the `litellm` extra where the
backend has ways in through the gateway that are not offered for its absence, and `""` otherwise.

**9.6** `Accounts.find(cli, name)` MUST return the account, or `None`.

**9.7** `Accounts.where(cli, name)` MUST return the account's credentials directory, and MUST
raise `ValueError` for an unknown backend or an invalid name.

**9.8** `Accounts.write(...)` MUST write the account as given, replacing its `env` and `args`
and keeping its credentials; where `args` is empty and `way` names a way that adds arguments,
those arguments MUST be filled from `env`. It MUST raise `ValueError` for an invalid backend or
name and `OSError` where the write fails.

**9.9** `Accounts.make(cli, name, way, answers)` MUST write an account from a way's answers and
make its directory; it MUST raise `ValueError` for an invalid backend or name and `OSError` where
the write fails.

**9.10** `Accounts.sign_in(provider, way, answers)` MUST run the backend's own sign-in command
under the account's paths and return its exit status.

**9.11** `Accounts.asks(way, given)` MUST return the variables of the way still unanswered by
`given`.

**9.12** `Accounts.serves(one)` MUST return the other backends the account's credentials can
run.

**9.13** `Accounts.copies(one, cli, name)` MUST write the same account for another backend, and
MUST raise `ValueError` where that backend cannot use it.

**9.14** `Accounts.remove(cli, name)` MUST delete the account and its credentials and return
whether it existed; it MUST raise `ValueError` for `name` `""`.

**9.15** `Accounts.env(said)` MUST parse `NAME=VALUE` lines into a mapping.

**9.16** `Accounts.environ(provider)` MUST return the environment a turn run as that account
receives, and `{}` for `None`.

**9.17** `Accounts.models(cli, provider)` MUST return what the backend last reported it runs as
that account, and `()` where it was never asked; `Accounts.asked` MUST return when that was, or
`""`.

**9.18** `Accounts.stale(cli, provider)` MUST return `True` where the backend was never asked or
was last asked more than one week ago.

**9.19** `Accounts.ask(cli, provider, seconds)` MUST start the backend to list its models, keep
the answer, and return it, or `()` where the backend does not answer within `seconds`.

## 10. `Runtimes`

```python
class Runtimes:
    def kinds(self) -> list[str]: ...
    def all(self, backend: str = "") -> list[Runtime]: ...
    def find(self, backend: str, name: str) -> Runtime | None: ...
    def saved(self, backend: str, name: str) -> bool: ...
    def new(self, backend: str, name: str, **fields: Any) -> Runtime: ...
    def add(self, runtime: Runtime) -> Runtime: ...
    def write(self, runtime: Runtime) -> Runtime: ...
    def remove(self, backend: str, name: str) -> bool: ...
    def hosts(self, config: str | os.PathLike[str] | None = None) -> list[SSHHost]: ...
    def import_ssh(self, config: str | os.PathLike[str] | None = None,
                   names: Iterable[str] | None = None, *, update: bool = False
                   ) -> list[SSHRuntime]: ...
    def resolve(self, runtime: SSHRuntime) -> SSHHost: ...
    def check(self, runtime: Runtime, seconds: float = 30.0) -> Checked: ...
```

**10.1** A `backend` argument MUST be one of `ssh`, `docker`, `swarm`, `apple-container` and
`slurm`; the fields of a runtime of each backend are those `features/environments.md` defines.

**10.2** `Runtimes.kinds()` MUST return every backend an environment can be put on, as `-e`
spells it, `local` first.

**10.3** `Runtimes.all(backend)` MUST return every saved runtime, or every saved runtime of one
backend, by backend and then by name.

**10.4** `Runtimes.find(backend, name)` MUST return the runtime, or `None`.

**10.5** `Runtimes.saved(backend, name)` MUST return whether a runtime is written under that name,
whether or not it reads, and MUST raise `ValueError` for an unknown backend or a name no runtime
can have.

**10.6** `Runtimes.new(backend, name, **fields)` MUST build and validate a runtime without saving
it, and MUST raise `ValueError` for an unknown field or an invalid value; `new(**r.held())` MUST
equal `r` for every runtime `r`.

**10.7** `Runtimes.add(runtime)` MUST save a new runtime and MUST raise `ValueError` where the
name is taken; `Runtimes.write(runtime)` MUST save it, replacing any of that name. Both MUST
raise `OSError` where the write fails.

**10.8** `Runtimes.remove(backend, name)` MUST delete the runtime and return whether it existed.

**10.9** `Runtimes.hosts(config)` MUST return every `Host` of an ssh config, `~/.ssh/config` by
default, as `ssh -G` resolves it, and MUST raise `OSError` where `ssh` is absent or the config
cannot be read.

**10.10** `Runtimes.import_ssh(config, names, update=...)` MUST save one `ssh` runtime per
`Host` of the config, or per name in `names`, named after it, keeping each existing one unless
`update`; it MUST raise `ValueError` for a name the config does not hold.

**10.11** `Runtimes.resolve(runtime)` MUST return what `ssh -G` makes of an ssh runtime without
reaching it.

**10.12** `Runtimes.check(runtime, seconds)` MUST reach the runtime and report what it has:
an ssh host its home, CPUs, memory and GPUs, by the route an epic takes to it; a docker daemon its
`docker info`, compared with what the runtime is written as handing out; a docker runtime that
names a running container only whether that container is running; a swarm's manager its
`docker info`, whether it manages an active swarm, and the nodes that accept a task; Apple's
container system whether it runs, compared with the Mac; and a Slurm cluster its `sinfo`, the
nodes of its partition that accept a job.

**10.13** `Runtimes.check` MUST NOT wait longer than `seconds`, MUST NOT prompt for a password,
and MUST NOT raise: a runtime that does not answer MUST be reported as unreached, with why.

## 11. `Fallbacks`

```python
class Fallbacks:
    default: str  # property
    def all(self) -> list[Falls]: ...
    def policies(self) -> tuple[Policy, ...]: ...
    def named(self, policy: str) -> Policy | None: ...
    def reads(self, said: str) -> str: ...
    def spec(self, backend: str, model: str, provider: str = "") -> str: ...
    def tried(self, said: str) -> Falls: ...
    def chain(self, said: str) -> list[str]: ...
    def points(self, said: str, to: Sequence[str]) -> Falls: ...
    def retrying(self, said: str, tries: int, policy: str, timeout: float) -> Falls: ...
    def clear(self, said: str) -> bool: ...
```

**11.1** `Fallbacks.default` MUST be `"exponential-jitter"`.

**11.2** `Fallbacks.policies()` MUST return the wait policies `none`, `constant`, `linear`,
`exponential`, `exponential-jitter` and `fibonacci`; `Fallbacks.named(policy)` MUST return one of
them, or `None`.

**11.3** `Fallbacks.all()` MUST return every fallback step written, in the order written.

**11.4** `Fallbacks.reads(said)` MUST return the canonical spelling of a place, or `""` where
`said` is not one; `Fallbacks.spec(backend, model, provider)` MUST return the place
`<backend>[@<provider>]/<model>`.

**11.5** `Fallbacks.tried(said)` MUST return the step written against a place, or an empty
`Falls` where there is none.

**11.6** `Fallbacks.chain(said)` MUST return `[said, *to]` where a step is written against
`said`, and `[said]` otherwise; chains MUST NOT be joined.

**11.7** `Fallbacks.points(said, to)` MUST set the places `said` falls back to, in order, and
MUST raise `ValueError` for a text that is not a place, for `said` itself, and for a place named
twice.

**11.8** `Fallbacks.retrying(said, tries, policy, timeout)` MUST set the extra tries, the wait
policy and the total limit in seconds (`0` meaning none), and MUST raise `ValueError` for an
invalid value.

**11.9** `Fallbacks.clear(said)` MUST remove the step and return whether there was one.

## 12. `Epics`

```python
class Epics:
    def __init__(self, workspace: str | os.PathLike[str] | None = None) -> None: ...
    def under(self) -> Path: ...
    def all(self) -> list[Path]: ...
    def every(self) -> list[Path]: ...
    def read(self, epic: Path) -> Ran | None: ...
    def tree(self, epic: Path) -> tuple[Called, ...]: ...
    def sessions(self, epic: Path) -> list[Session]: ...
    def opened(self, epic: Path) -> dict[str, list[str]]: ...
    def resumed(self, flow: str) -> Path | None: ...
    def picks_up(self, epic: Path) -> bool: ...
    def foreign(self, epic: Path) -> str: ...
    def going(self, epic: Path) -> bool: ...
    def ending(self, ran: Ran) -> str: ...
    def state(self, epic: Path, flow: str = "") -> dict[str, Any]: ...
    def traced(self, epic: Path, *, output: str | os.PathLike[str] | None = None,
               start: str | None = None, end: str | None = None
               ) -> tuple[Path, dict[str, Any]]: ...
    def transcripts(self, epic: Path) -> list[dict[str, Any]]: ...
    def timeline(self, epic: Path) -> Timeline: ...
    def bundled(self, epic: Path, *, output: str | os.PathLike[str],
                transcript: str | None = None) -> tuple[Path, dict[str, Any]]: ...
    def imported(self, archive: str | os.PathLike[str]) -> Path: ...
    def trace(self, *, sessions: str | Iterable[str] | None = None,
              agents: Mapping[str, Iterable[str]] | None = None,
              output: str | os.PathLike[str] | None = None, start: str | None = None,
              end: str | None = None, profile: str | os.PathLike[str] | None = None,
              flow_profile: str | os.PathLike[str] | None = None,
              kept: Iterable[str | os.PathLike[str]] | None = None) -> dict[str, Any]: ...
```

Every `epic` argument is an epic directory.

**12.1** `Epics.under()` MUST return the directory this workspace's epics are written in, as
`api/files/epics.md` locates it.

**12.2** `Epics.all()` MUST return every epic of the workspace, oldest first; `Epics.every()`
MUST return every epic of every workspace on this machine, oldest first.

**12.3** `Epics.read(epic)` MUST return the epic as a `Ran` (§20.5), or `None` for a directory
holding no epic.

**12.4** `Epics.tree(epic)` MUST return every flow call of the epic as a tree of `Called`.

**12.5** `Epics.sessions(epic)` MUST return every session of the epic, across every record of
it; `Epics.opened(epic)` MUST map each agent's name to the ids of the sessions it opened.

**12.6** `Epics.resumed(flow)` MUST return the epic that `--resume` of that flow would pick up,
or `None`.

**12.7** `Epics.picks_up(epic)` MUST return `True` where, and only where, the epic holds a
journal entry, is not going, and `Epics.foreign(epic)` is `""`.

**12.8** `Epics.foreign(epic)` MUST return why an imported epic cannot be picked up on this
machine, or `""`.

**12.9** `Epics.going(epic)` MUST return whether the epic is still going, in any process.

**12.10** `Epics.ending(ran)` MUST return how the epic ended, as `features/epics.md` names
endings, and `running` while it is going.

**12.11** `Epics.state(epic, flow)` MUST return the `ctx.state` a resumable flow kept: the
epic's own flow's, or, where `flow` names a canonical ref, that flow's.

**12.12** `Epics.traced(epic, ...)` MUST gather the epic's own sessions into a trace as
`features/monitoring.md` defines it, written to `output`, or to the epic's `traces/` directory
under a name of the moment, and MUST return the path written and the trace's summary.

**12.13** `start` and `end` of `Epics.traced` and `Epics.trace` MUST accept any wording of a
moment that `dateparser` reads.

**12.14** `Epics.trace(...)` MUST gather a trace of any sessions: `sessions=None` every session
of the workspace, an empty iterable none; `kept=None` MUST read every place **hmz** keeps
sessions.

**12.15** `Epics.transcripts(epic)` MUST return what each session of the epic said and did, read
from its logs, and MUST write nothing.

**12.16** `Epics.timeline(epic)` MUST return the epic as an Exomyth timeline, as
`features/monitoring.md` defines it, and MUST write nothing.

**12.17** `Epics.bundled(epic, output=..., transcript=...)` MUST write one `.hmzepic` archive of
the whole epic, as `api/files/epics.md` defines it, with credentials struck out, to `output` or
into the directory `output` names, and MUST return its path and its manifest.

**12.18** `Epics.imported(archive)` MUST read a `.hmzepic` back as an epic of the workspace it
ran in, wherever that is, and return its epic directory.

**12.19** `Epics.imported` MUST raise `ValueError` for a file that is not a `.hmzepic`, for an
archive holding an unsafe member, and for an epic already present.

## 13. `Backups`

`Hmz.backups` returns a `Backups`; the class is a returned type.

```python
class Backups:
    def targets(self) -> tuple[Target, ...]: ...
    def defaults(self) -> tuple[str, ...]: ...
    def push(self, ran: Ran | Path, names: Iterable[str] | None = None) -> tuple[str, ...]: ...
    def state(self, ran: Ran | Path) -> dict[str, dict[str, Any]]: ...
    def where(self, ran: Ran | Path) -> str: ...
    def wait(self, seconds: float | None = None) -> bool: ...
    def listed(self, name: str) -> list[Stored]: ...
    def pulled(self, name: str, key: str) -> Path: ...
```

**13.1** `Backups.targets()` MUST return every backup target in the settings, in the order
written; `Backups.defaults()` MUST return the names of the default targets.

**13.2** `Backups.push(ran, names)` MUST back the epic up to the targets named, else to those it
was started with, else to the defaults, MUST return the names it queued at once without waiting
for any push, and MUST raise `ValueError` for a name no target has.

**13.3** `Backups.state(ran)` MUST map each target the epic was ever backed up to onto `at`,
`ok`, `error` and `why` of its last backup, read from the epic as it is now.

**13.4** `Backups.where(ran)` MUST return `<machine>/<workspace>/<epic>`, the place of the epic
in a target's repository.

**13.5** `Backups.wait(seconds)` MUST wait for every backup the calling process queued, at most
`seconds`, and return whether none is left.

**13.6** `Backups.listed(name)` MUST fetch the target afresh and return every epic it holds, of
every machine and workspace, oldest first; it MUST raise `ValueError` for an unknown target and
`OSError` where git fails or exceeds its timeout.

**13.7** `Backups.pulled(name, key)` MUST download the epic at `key` into this machine's epics
as an import does and return its epic directory; it MUST raise `ValueError` for an unknown
target, a key naming no epic, an epic not laid out as one, and an epic already present, and
`OSError` where git fails.

## 14. The daemon registry

`Hmz.daemons` returns the registry of the daemons of other machines; its class is a returned
type, distinct from `hmz.sdk.Daemons` (§16).

```python
class Registry:  # hmz.runtime.doing.daemons.Daemons
    CARRIED: ClassVar[tuple[str, ...]]  # ("general", "fallback", "runtimes", "backup")
    def all(self) -> list[dict[str, Any]]: ...
    def find(self, name: str) -> dict[str, Any] | None: ...
    def write(self, name: str, fields: dict[str, Any], *, replace: bool = False
              ) -> dict[str, Any]: ...
    def remove(self, name: str) -> None: ...
    def offered(self) -> dict[str, dict[str, Any]]: ...
    def imported(self, wanted: Sequence[str]) -> list[str]: ...
    def remotes(self, version: str | None = None) -> Remotes: ...
class Remotes:
    def state(self, name: str) -> dict[str, str]: ...
    def connect(self, name: str) -> dict[str, str]: ...
    def reached(self, name: str) -> tuple[int, str]: ...
    def asks(self, name: str) -> tuple[int, dict[str, str]]: ...
    def asked(self, name: str, path: str, body: dict[str, Any] | None = None, *,
              into: Path | None = None) -> Any: ...
    def followed(self, name: str, path: str, going: threading.Event
                 ) -> Iterator[tuple[str, Any]]: ...
    def close(self) -> None: ...
class Unreached(RuntimeError):
    seen: dict[str, str]
    status: int
```

**14.1** The registry MUST read and write the `daemons` list of `api/settings.md`; `local` MUST
name this machine's own daemon, which is never written there.

**14.2** `Registry.all()` MUST return every ssh daemon written, in order, leaving out an entry
that cannot be one; `Registry.find(name)` MUST return one of them, or `None`.

**14.3** `Registry.write(name, fields, replace=...)` MUST write the daemon, or overwrite the one
of that name where `replace`, and return it as written; it MUST raise `ValueError` where it
cannot be one, `FileExistsError` where the name is taken and `replace` is false, and `OSError`
where the write fails.

**14.4** `Registry.remove(name)` MUST remove the daemon; it MUST raise `ValueError` for `local`,
`LookupError` for an unknown name, and `OSError` where the write fails.

**14.5** `Registry.offered()` MUST map each `Host` of the ssh config not yet written to the
daemon it would be; `Registry.imported(wanted)` MUST write a daemon for each `Host` named,
skipping those already written, and return their names. `Registry.imported` MUST raise
`ValueError` for an empty list or a host that cannot be one, `LookupError` for a host the config
does not name, and `OSError` where the config cannot be read or the file written.

**14.6** `Registry.remotes(version)` MUST return a `Remotes` that reaches each daemon as it is
first asked for, installing `hmz` at `version`, or at the calling process's version where
`version` is `None`, as `features/daemons.md` defines reaching.

**14.7** `Remotes.state(name)` MUST return `{state, detail, version}`, `state` being one of
`idle`, `connecting`, `installing`, `up` and `failed`; `local` MUST be `up` at the calling
process's version.

**14.8** `Remotes.connect(name)` MUST start reaching the daemon, or reach it again at once where
it failed, and return its state; it MUST raise `LookupError` for an unknown name and `Unreached`
where the `Remotes` is closing.

**14.9** `Remotes.reached(name)` MUST return the port of this machine's loopback forwarded to
the daemon's `hmz web` and that server's key, reaching it first where needed;
`Remotes.asks(name)` MUST return that port and the headers a request carries to be admitted.
Both MUST raise `Unreached` where it is not up and `LookupError` for an unknown name.

**14.10** `Remotes.asked(name, path, body, into=...)` MUST send the request `path` (an
`api/http.md` path with its query) to the daemon's `hmz web`, as a `POST` of `body` where `body`
is not `None` and a `GET` otherwise, and MUST return its JSON answer, or, where `into` is given,
the number of bytes written there.

**14.11** `Remotes.followed(name, path, going)` MUST yield the name and JSON data of each
server-sent event the daemon's `hmz web` sends at `path`, until the stream ends or `going` is
set.

**14.12** `Remotes.asked` and `Remotes.followed` MUST raise `Unreached` where the daemon is not
up or its `hmz web` refused, with `Unreached.status` the HTTP status it refused with, or `503`
where it was not reached, and `Unreached.seen` its state where it is not up.

**14.13** `Remotes.close()` MUST stop reaching every daemon and stop every process started for
one.

## 15. `Host`

```python
class Host:
    def __init__(self, hmz: Hmz, slot: str = "") -> None: ...
    def attach(self, name: str, kind: str, heard: Callable[[dict[str, Any]], None], *,
               replay: bool = True) -> str: ...
    def detach(self, client: str) -> None: ...
    attached: int; idle: bool; closed: bool; epic: Path | None  # properties
    def away_for(self, role: str) -> bool: ...
    def printed(self, text: str) -> None: ...
    def asked(self, client: str, said: dict[str, Any]) -> dict[str, Any]: ...
    def status(self) -> dict[str, Any]: ...
    def close(self) -> None: ...
```

**15.1** A `Host` MUST behave, toward every frontend attached to it, exactly as `api/daemon.md`
states a host behaves: the same messages, in the same order, and the same answers and refusals
to the same requests.

**15.2** `Host.attach(name, kind, heard, replay=...)` MUST attach a frontend as the `hello`
request of `api/daemon.md §7` does, MUST call `heard` with every message for it, in order, on a
thread that is not the caller's, and MUST return its client id; it MUST raise `RuntimeError`
once the host is closed.

**15.3** `Host.detach(client)` MUST let the frontend go as `api/daemon.md §7.4` states.

**15.4** `Host.attached` MUST be the number of frontends attached.

**15.5** `Host.idle` MUST be `True` where, and only where, the host is open, no frontend is
attached, no epic is going, starting or stopping, and no epic that ended with nobody attached
awaits a frontend.

**15.6** `Host.closed` MUST be whether the host has been closed.

**15.7** `Host.epic` MUST be the epic directory of the epic going, else of the one stopping,
else of the last, or `None`.

**15.8** `Host.away_for(role)` MUST return what `afk` last set for that role, else for every
role.

**15.9** `Host.printed(text)` MUST send one `printed` record carrying `text` to every frontend.

**15.10** `Host.asked(client, said)` MUST carry out one request of `api/daemon.md §8` for that
frontend and return its answer without the `type` and `to` fields of a reply.

**15.11** `Host.status()` MUST return the keys of `api/daemon.md §6.4.1`.

**15.12** `Host.close()` MUST close every epic of the host and let every frontend go with `gone`,
and MUST wait at most 15 seconds, counted from the first call, for those epics to release what
they made.

## 16. `Daemons`

```python
class Daemons:
    def here(self, workspace: str | os.PathLike[str] | None = None) -> Daemon | None: ...
    def all(self) -> list[Daemon]: ...
    def host(self, workspace: str | os.PathLike[str] | None = None) -> Daemon: ...
```

**16.1** Every `workspace` argument MUST mean the directory named, with every link followed, or
the current directory where it is `None`.

**16.2** `Daemons.here(workspace)` MUST return the `Daemon` of the workspace's own host, as
`api/daemon.md §4` finds it, or `None` where the daemon holds no live host of it.

**16.3** Where this machine's daemon speaks another protocol version, `Daemons.here` MUST
return a `Daemon` describing that daemon, its `protocol` the version it wrote or `0`.

**16.4** `Daemons.all()` MUST return a `Daemon` for every live host of every workspace and slot
the daemon holds, oldest first; `[]` where no daemon answers; and only the daemon itself where it
speaks another protocol version.

**16.5** `Daemons.host(workspace)` MUST return the `Daemon` of the workspace's own host, starting
this machine's daemon and then that host where they are absent, and waiting at most 10 seconds
for each to come up.

**16.6** `Daemons.host` MUST raise `OSError` where this machine's daemon speaks another protocol
version, with the message of §17.9 prefixed by `[Errno <EADDRINUSE>] `, and where no host could be
started.

**16.7** `Daemons` MUST NOT consult `HUMANIZE_DAEMON`.

## 17. `Daemon`

```python
@dataclass(frozen=True, slots=True)
class Daemon:
    at: Path
    workspace: str
    pid: int
    started: str
    protocol: int = 0
    slot: str = ""
    alive: bool  # property
    def link(self, name: str = "", kind: str = "sdk", *, replay: bool = True) -> Link: ...
    def status(self) -> dict[str, Any]: ...
    def detach(self) -> int: ...
    def stop(self, *, seconds: float = 20.0) -> bool: ...
    def kill(self, *, seconds: float = 20.0) -> bool: ...
    def asked(self, said: dict[str, Any]) -> dict[str, Any]: ...
```

**17.1** `Daemon.at` MUST be this machine's daemon directory (`api/daemon.md §3`);
`Daemon.workspace` the workspace path, with every link followed; `Daemon.pid` the host's process;
`Daemon.started` when that process started, in UTC as `%Y-%m-%dT%H:%M:%SZ`; `Daemon.protocol` the
protocol version of `api/daemon.md §12` the daemon speaks, `0` for one that wrote none; and
`Daemon.slot` the host's slot.

**17.2** `Daemon.alive` MUST be whether a process of `pid` exists, counting a process the caller
cannot signal as existing.

**17.3** `Daemon.link(name, kind, replay=...)` MUST open a connection to the host, say `hello`
with `name`, `kind`, `replay`, the workspace and the slot, and return the attached `Link`.

**17.4** `Daemon.link` MUST raise `OSError` where nothing accepts the connection, or `hello` is
refused or not answered within 10 seconds.

**17.5** `Daemon.status()` MUST return the host's answer to the control request `status`; where
the host does not answer, it MUST return `pid`, `workspace`, `slot` (where not `""`), `started`,
`kind` `host` and `protocol` from the `Daemon` itself, with `attached` `0`, `flows` `[]` and
`calls` `[]`.

**17.6** `Daemon.detach()` MUST send the control request `detach` and return how many frontends
were let go, or `0` where the host did not answer.

**17.7** `Daemon.stop(seconds=...)` MUST send the control request `stop` and wait at most
`seconds` for the host process to exit, returning whether it exited; where the request is not
answered `ok`, it MUST return whether the process no longer exists.

**17.8** `Daemon.kill(seconds=...)` MUST send `SIGTERM` to the host process, then `SIGKILL` where
it has not exited after `seconds`, MUST leave the daemon and every other host running, and MUST
return whether the process exited.

**17.9** For a `Daemon` of another protocol version, the text describing it MUST be `the runs in
<workspace> are held by an older Humanize (pid <pid>); stop it with that version`, with `on this
machine` in place of `in <workspace>` where `workspace` is `""`.

**17.10** `Daemon.asked(said)` MUST send one control request with `workspace` and, where not
`""`, `slot` added, and return the answer, or `{}` where none came within 5 seconds.

## 18. `Link`

```python
class Link:
    client: str
    def told(self, message: dict[str, Any]) -> None: ...
    def heard(self, listener: Callable[[dict[str, Any]], None]) -> None: ...
    def __iter__(self) -> Iterator[dict[str, Any]]: ...
    def asked(self, said: Mapping[str, Any], *, seconds: float | None = None) -> dict[str, Any]: ...
    def start(self, flow: str | os.PathLike[str], task: str, *,
              agents: Mapping[str, Any] | None = None, envs: Mapping[str, Any] | None = None,
              params: Any = None, budget: Any = None, profile_flow: bool = False,
              profile_environment: bool = False, resume: bool | str | os.PathLike[str] = False,
              backup: Iterable[str] | None = None) -> dict[str, Any]: ...
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
    def __enter__(self) -> Self: ...
    def __exit__(self, kind, why, traceback) -> None: ...
```

### 18.1 Delivery

**18.1.1** A `Link` MUST be one frontend of one host, whether the host is in the calling process
or reached through the daemon, and MUST behave identically in both cases except as §18.4 states.

**18.1.2** `Link.client` MUST be the client id the host gave the frontend.

**18.1.3** `Link.told(message)` MUST queue one message for delivery; it is called by the
transport and is not for the caller.

**18.1.4** Iterating a `Link` MUST yield every message, in the order the host sent them, ending
after a `gone` message or after `close()`; iterating while a listener is set MUST raise
`RuntimeError`.

**18.1.5** `Link.heard(listener)` MUST deliver every message, those already queued first, to
`listener`, in order, on a thread of the link's own; an exception raised by `listener` MUST be
suppressed; a second call MUST raise `RuntimeError`.

### 18.2 Requests

**18.2.1** `Link.asked(said, seconds=...)` MUST send one request of `api/daemon.md §8` and return
its answer, without the `type` and `to` fields of the reply.

**18.2.2** `Link.asked` MUST raise `Refused` with the reply's `why` where the reply says `ok`
`false`, and `TimeoutError` with the message `no answer to '<do>' in <seconds>s` where no reply
came within `seconds`.

**18.2.3** `Link.start(...)` MUST send the request `start` with every argument, `agents` and
`envs` as mappings of role to agent spec and environment spec, `params` and `budget` as JSON
values of the mapping or model given, and `resume` as a boolean or the text of the path.

**18.2.4** `Link.say`, `Link.answer`, `Link.stop`, `Link.force`, `Link.afk`, `Link.claim`,
`Link.release`, `Link.board` and `Link.aside` MUST each send the request of the same name with
its arguments as that request's fields.

**18.2.5** Once the host has let the frontend go, every request MUST raise `Refused` with the
reason the `gone` message gave.

### 18.3 Closing

**18.3.1** `Link.close()` MUST let go of the host and MUST NOT stop any epic; a second call MUST
do nothing.

**18.3.2** Leaving a `with` block over a `Link` MUST call `close()`, however the block ended.

### 18.4 Transport differences

**18.4.1** A `Link` to a host in the calling process MUST ignore `seconds` and answer each
request on the calling thread.

**18.4.2** A `Link` through the daemon MUST answer a send failure with `Refused` carrying `the
host could not be reached: <error>`.

**18.4.3** A `Link` through the daemon MUST deliver a `gone` message with `why` `the host went
away` where the connection ends, fails or carries a frame of no valid length without a `gone`
message, and with `why` the text of a `GONE` frame where one arrives.

## 19. `fakes`

**19.1** `hmz.sdk.fakes` MUST offer exactly `run_fake`, `FakeAgentDriver`, `FakeSession`,
`FakeEnvDriver`, `FakeOutworlder`, `Answer`, `Command`, `Handler` and `Reply`, with the
signatures and behaviour `api/flows.md` states.

**19.2** `Hmz.run` MUST accept a `FakeAgentDriver` as an agent and a `FakeOutworlder` as the
outworlder, and an epic made with them MUST be written as any other epic is.

## 20. Returned types

Each type in this section is a returned type. Fields are listed in declaration order.

### 20.1 Lines and specs

**20.1.1** `Line` MUST be a named tuple with the fields `flow: str`, `task: str`,
`agents: tuple[AgentSpec, ...] = ()`, `envs: tuple[EnvSpec, ...] = ()`,
`params: dict[str, str] = {}`, `budget: Budget | None = None`, `profile_flow: bool = False`,
`profile_environment: bool = False`, `resume: bool = False`, `as_json: bool = False` and
`backup: tuple[str, ...] | None = None`, each read from the `hmz exec` option of `api/cli.md`
that sets it.

**20.1.2** `AgentSpec` MUST be a frozen dataclass with the fields `role`, `harness`, `provider`
(`""` for this machine's own sign-in), `model`, `effort` (`""` for automatic) and `cli`, and
`str()` of one MUST be the text `-a` takes.

**20.1.3** `EnvSpec` MUST be a frozen dataclass with the fields `role`, `backend`, `provider`
(`""` for this machine) and `workdir`, and `str()` of one MUST be the text `-e` takes.

### 20.2 Accounts and fallbacks

**20.2.1** `Provider` MUST have the fields `cli`, `name`, `way`, `env: Mapping[str, str]`,
`args: tuple[str, ...]` and `made`, and the property `at: Path`.

**20.2.2** `Way` MUST have the fields `name`, `about`, `argv` (its sign-in command, empty for
none), `asks`, `sets`, `args` and `stdin`.

**20.2.3** `Model` MUST have the fields `name`, `efforts: tuple[str, ...]` (hardest first) and
`swarms: bool`.

**20.2.4** `Falls` MUST have the fields `spec`, `to: tuple[str, ...]`, `tries: int`,
`policy: str` and `timeout: float`; `Policy` MUST have the fields `name` and `about`.

### 20.3 Flows

**20.3.1** `Offer` MUST have the fields `whose` (a flowverse, `local` or `user`), `name` (the
text `-f` takes) and `about`.

**20.3.2** `Declaration` MUST have the fields `name`, `ref`, `description`, `hidden`,
`resumable`, `agents: tuple[AgentRole, ...]`, `envs: tuple[EnvRole, ...]` and `params` (the
flow's `FlowParams` type), and the methods `agent(name)` and `env(name)` returning a role or
`None`.

**20.3.3** `AgentRole` MUST have the fields `name`, `declared`, `required`, `auto`, `harness`,
`capabilities`, `permission`, `skills` and `grant`; `EnvRole` MUST have the fields `name`,
`declared`, `required`, `auto`, `capabilities`, `cpu_count`, `memory`, `gpu_count`,
`gpu_memory`, `image`, `grant` and `resources`.

**20.3.4** `LiveCall` MUST have the fields `ref`, `name`, `depth` (`1` for the epic's flow),
`since` (monotonic seconds), `id` (`0` for none), `parent`, `task` and `resumable`.

**20.3.5** `Flowverse` MUST have the fields `name`, `url` (`""` for `local` and `user`), `at`,
`fetched` and `fixed`.

### 20.4 Flowverse indexes

**20.4.1** `Index` MUST be a named tuple of `verse`, `releases` and `skipped`, with the methods
`flows()`, `versions(flow)`, `release(flow, version)` and `newest(flow, spec="")`.

**20.4.2** `Release` MUST have the fields `name`, `version`, `description`, `repo`, `ref`,
`commit`, `subdir`, `license`, `dependencies` and `owner`, and the properties `listed`, `owned`,
`semver` and `url`.

**20.4.3** `Installed` MUST have the fields `verse`, `name`, `version`, `commit`, `repo`, `ref`,
`subdir`, `dependencies` and `owner`, and the properties `listed`, `called` and `at`; `Update`
MUST be a named tuple of `installed` and `version`; `Skipped` MUST be a named tuple of `at` and
`why`.

### 20.5 Epics

**20.5.1** `Ran` MUST be a named tuple with at least the fields `at`, `flow`, `task`,
`workspace`, `began`, `ended` (`""` while going or abandoned), `how`, `agents: tuple[Drove,
...]`, `sessions: tuple[Session, ...]`, `called: tuple[Called, ...]`, `resumable`, `ref`, `envs`,
`params`, `budget`, `picked_up`, `profile_flow` and `profile_environment`, and the property
`name`, each as the epic record of `api/files/epics.md` wrote it.

**20.5.2** `Drove` MUST have the fields `agent` (the role), `backend`, `model`, `effort`,
`provider` and `name` (the agent's name, `""` in an epic written before agents had names), and
the property `spec`, its agent spec.

**20.5.3** `Called` MUST have the fields `flow`, `task`, `record`, `began`, `ended`, `how` and
`calls`.

**20.5.4** `Session` MUST have the fields `agent`, `backend`, `provider`, `ident`, `name`, `at`,
`flow`, `parent`, `record`, `where` and `harness`.

### 20.6 Runtimes

**20.6.1** Each runtime type MUST carry the fields `features/environments.md` defines for its
backend, the property `at`, and the method `held()` returning its fields as a mapping.

**20.6.2** `SSHHost` MUST have the fields `alias`, `host`, `user`, `port`, `identity_files` and
`proxy_jump`.

**20.6.3** `Checked` MUST be a frozen dataclass with the fields `reached: bool`, `said: str`,
`home: str`, `cpus: float`, `memory: int`, `gpus: tuple[str, ...]`,
`usable: tuple[str, ...] | None`, `gpu_memory: int`, `runtimes: tuple[str, ...]`, `version: str`,
`short: tuple[str, ...]` and `nodes: tuple[str, ...]`.

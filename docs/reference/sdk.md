---
pageClass: hmz-ref
---

<script setup>
import '../.vitepress/theme/components/ref-cli/ref.css'
</script>

# SDK reference

`hmz.sdk`: the supported import path for programs that drive humanize. It defines nothing of
its own but `Daemons`; every other name is the object the runtime or the daemon layer holds,
handed through unchanged. Notation: [Conventions](/reference/#conventions).

```python
from hmz.sdk import Hmz, Daemons, Refused, fakes
```

## Module {#module}

```python
__all__ = ["Accounts", "Daemon", "Daemons", "Epics", "Fallbacks", "Flows", "Flowverses", "Hmz",
           "Host", "Link", "Refused", "Run", "Runtimes", "fakes"]
def __getattr__(name: str) -> object: ...
```

| Name | Kind | Defined in | Section |
| --- | --- | --- | --- |
| `Hmz` | class | `hmz.runtime` | [Hmz](#hmz) |
| `Run` | class | `hmz.runtime` | [Run](#run) |
| `Refused` | exception | `hmz.runtime` | [Refused](#refused) |
| `Flows` | class | `hmz.runtime` | [Flows](#flows) |
| `Flowverses` | class | `hmz.runtime` | [Flowverses](#flowverses) |
| `Accounts` | class | `hmz.runtime` | [Accounts](#accounts) |
| `Runtimes` | class | `hmz.runtime` | [Runtimes](#runtimes) |
| `Fallbacks` | class | `hmz.runtime` | [Fallbacks](#fallbacks) |
| `Epics` | class | `hmz.runtime` | [Epics](#epics) |
| `Host` | class | `hmz.runtime` | [Host](#host) |
| `Daemons` | class | `hmz.sdk.daemons` | [Daemons](#daemons) |
| `Daemon` | frozen dataclass | `hmz.daemon` | [Daemon](#daemon) |
| `Link` | class | `hmz.daemon` | [Link](#link) |
| `fakes` | module | `hmz.runtime.flowing.fakes` | [fakes](#fakes) |

| Rule | |
| --- | --- |
| Lazy | Each name is imported from its layer on first access (module `__getattr__`). `import hmz.sdk` imports nothing else. |
| Identity | `hmz.sdk.X is <layer>.X`: the same class, not a wrapper. |
| Unknown names | `AttributeError: module 'hmz.sdk' has no attribute '<name>'`. |
| `fakes` | A module attribute: `from hmz.sdk import fakes` works; `import hmz.sdk.fakes` raises `ModuleNotFoundError`. |
| Stability | Names in `__all__` are stable. Types they return that are not in `__all__` (`Line`, `Offer`, `Declaration`, `Provider`, …, listed under [Returned types](#returned-types)) are internal: their fields are documented as they are. |

## `Hmz` {#hmz}

```python
class Hmz:
    def __init__(self, workspace: str | os.PathLike[str] | None = None) -> None
```

One workspace and everything humanize can be asked to do in it. The constructor loads
nothing.

| Parameter | Type | Default | Meaning |
| --- | --- | --- | --- |
| `workspace` | `str \| PathLike \| None` | `None` | The project directory. `None`: the current directory, re-read at each use. Kept as given; `~` is not expanded. |

### Properties {#hmz-properties}

| Property | Type | Value |
| --- | --- | --- |
| `workspace` | `Path` | The project directory. |
| `home` | `Path` | `$HUMANIZE_HOME`, else `~/.hmz`. Not created. |
| `settings` | `hmz.runtime.settings.Settings` | What is remembered for this workspace and machine ([Settings](/reference/settings)). Internal type. |
| `flows` | [`Flows`](#flows) | |
| `verses` | [`Flowverses`](#flowverses) | The same object as `flows.verses`. |
| `accounts` | [`Accounts`](#accounts) | |
| `runtimes` | [`Runtimes`](#runtimes) | |
| `fallbacks` | [`Fallbacks`](#fallbacks) | |
| `epics` | [`Epics`](#epics) | Of this workspace. |

`workspace` and `home` are computed on each access; the others are created on first access and
cached on the instance.

### Methods {#hmz-methods}

| Method | Returns | Raises |
| --- | --- | --- |
| [`run(flow, task, *, …)`](#hmz-run) | [`Run`](#run) | `Refused` |
| [`runner(flow, *, …)`](#hmz-runner) | `Runner` | `Refused` |
| [`read(argv)`](#hmz-read) | [`Line`](#line) | `SystemExit` |
| [`exec(argv)`](#hmz-exec) | `Any` | `SystemExit`, `Refused`, what the flow raises |
| `host()` | [`Host`](#host) | — |
| `backends()` | `tuple[Profile, ...]` | — |
| `reports()` | `bool` | — |

- `host()`: this workspace's [`Host`](#host), created on first call and cached on the
  instance. Frontends attached to it share one run.
- `backends()`: every coding-agent CLI humanize drives, installed or not, as internal
  `hmz.coganchor.backends.Profile` objects (`.name`, `.aliases`, `.efforts`, `.installs`, …).
  `[p.name for p in Hmz().backends()]` is `['claude', 'agy', 'codex', 'dsh', 'grok', 'kimi',
  'pi', 'qwen', 'opencode', 'mimo', 'cursor-agent', 'mcode']`.
- `reports()`: starts [error reporting](/user/reporting) where it has been answered *yes*
  (or `HUMANIZE_SENTRY=on`). Returns whether anything is being reported. Never asks.

### `Hmz.run` {#hmz-run}

```python
def run(
    self,
    flow: str | os.PathLike[str],
    task: str,
    *,
    agents: Mapping[str, str | AgentDriver] | Iterable[AgentSpec] = (),
    envs: Mapping[str, str | EnvDriver] | Iterable[EnvSpec] = (),
    params: Mapping[str, Any] | FlowParams | None = None,
    budget: Budget | Mapping[str, Any] | None = None,
    profile: bool = False,
    resume: bool | str | os.PathLike[str] = False,
    outworlder: OutworlderDriver | None = None,
) -> Run
```

Equivalent to `Run(self.runner(flow, agents=…, envs=…, params=…, budget=…, profile=…, resume=…), task,
outworlder=outworlder)`. Nothing starts. Where each agent's harness runs is not a parameter:
it is the `affinity` of the [runtime](#runtimes) its work is on.

| Parameter | Accepts | Default |
| --- | --- | --- |
| `flow` | A [`-f` ref](/reference/cli#naming-a-flow) or a path. | — |
| `task` | The task text. | — |
| `agents` | `{role: spec}` where spec is an [`-a` spec](/reference/cli#writing-an-agent) without `<role>=` (`"claude@work/claude-opus-5:high"`) or an `AgentDriver` (e.g. `fakes.FakeAgentDriver`); or an iterable of `AgentSpec` (`Line.agents`). | `()` |
| `envs` | `{role: spec}` with an [`-e` spec](/reference/cli#writing-an-environment) without `<role>=`, or an `EnvDriver`; or an iterable of `EnvSpec`. | `()` |
| `params` | A mapping (strings read as `-p` reads them) or an instance of the flow's `FlowParams`. `None`: defaults. | `None` |
| `budget` | A [`Budget`](/reference/flows#what-a-run-may-spend), or a mapping validated by `Budget.model_validate` (`{"cost": 5}`, `{"duration": 3600}`, `{"duration": "PT1H"}`; `"1h"` is **not** accepted). `None`: `Budget(cost=inf)` for `chat`, else refused. | `None` |
| `profile` | Whether to [profile](/reference/tracing#profiling-a-run) the programs the run's agents start, as well as tracing them; as `--profile`. | `False` |
| `resume` | `False`: from the top. `True`: the newest resumable epic of this flow here. A path: that epic. | `False` |
| `outworlder` | The driver filling `Outworlder` roles (e.g. `fakes.FakeOutworlder`). `None`: always away, as under `hmz exec`. | `None` |

Raises [`Refused`](#refused) for everything [`hmz exec` refuses at stage
3](/reference/cli#processing-order), in the same words, plus:

| Condition | Message |
| --- | --- |
| a role given twice across a mapping and specs | `<flow>: duplicate agent role '<role>'` / `… environment role …` |
| an invalid budget mapping | `the budget is invalid: <pydantic error>` |
| a `resume` path with no journal entry | `<epic name> has no saved progress to resume from` |

```python
from hmz.sdk import Hmz, Refused

try:
    Hmz().run("goal", "fix the build", agents={"worker": "pi/gpt-5.5:high"}, budget={"cost": 5})
except Refused as why:
    print(why)   # goal: 'worker' needs GoalCommandAgentMixin, which pi does not support
```

### `Hmz.runner` {#hmz-runner}

```python
def runner(self, flow, *, agents=(), envs=(), params=None, budget=None, profile=False,
           resume=False) -> Runner
```

Parameters and refusals as [`run`](#hmz-run), without `task` and `outworlder`. Returns the
internal `hmz.runtime.runner.Runner`: the flow loaded (its module imported), a driver made for
every role, everything checked. Making a driver starts no CLI and reaches no machine.

### `Hmz.read` {#hmz-read}

```python
def read(self, argv: list[str]) -> Line
```

Parses an `hmz exec` argument list (without `exec`) to a [`Line`](#line). Loads no flow. A
line argparse rejects, or an `-a`/`-e`/`-p` that does not parse, prints usage and
the error to stderr and raises `SystemExit(2)`; `--help` prints help and raises
`SystemExit(0)`.

```python
hmz = Hmz()
line = hmz.read(["-f", "ralph_loop", "-a", "agent=claude/claude-opus-5:high",
                 "-p", "budget.duration=6h,budget.cost=50", "fix the build"])
run = hmz.run(line.flow, line.task, agents=line.agents, envs=line.envs,
              params=line.params, budget=line.budget, profile=line.profile,
              resume=line.resume)
```

### `Hmz.exec` {#hmz-exec}

```python
def exec(self, argv: list[str]) -> Any
```

`read(argv)`, then `run(…)`, then `Run.run()`. Returns what the flow returned. Unlike the
`hmz exec` command it draws nothing, installs no signal handlers and does not convert
`Refused` or `BudgetExceeded` into an exit status.

## `Run` {#run}

```python
class Run:
    def __init__(self, runner: Runner, task: str, *,
                 outworlder: OutworlderDriver | None = None) -> None
```

One run of one flow. Made by [`Hmz.run`](#hmz-run). Constructing one starts nothing.

### Properties {#run-properties}

| Property | Type | Value |
| --- | --- | --- |
| `flow` | `str` | The flow as named. |
| `ref` | `str` | Its canonical ref (`chat:chat`, `humanize1:rlcr`). |
| `task` | `str` | |
| `declaration` | [`Declaration`](#declaration) | What the flow declares. |
| `budget` | `Budget` | What the run may spend. |
| `profile` | `bool` | Whether the run is [profiled](/reference/tracing#profiling-a-run) as well as traced. |
| `usage` | `hmz.flows.Usage` | Spent so far: `duration: timedelta`, `cost: float`, `output_tokens: int`. |
| `agents` | `tuple[AgentBase, ...]` | The coganchor agent behind each **open** session, oldest first. Empty for fake drivers. |
| `epic` | `Path \| None` | The epic directory, once started. |
| `running` | `bool` | Whether a run started with `start()` (or `run()` from a thread already running an event loop) is still going. Always `False` for `run()` on a thread without a loop. |
| `raised` | `BaseException \| None` | For a run started with `start()` and over: what the flow raised (`asyncio.CancelledError` after `stop()`). |
| `result` | `Any` | For a run started with `start()` and over: what the flow returned. |

### Methods {#run-methods}

| Method | Returns | Behaviour |
| --- | --- | --- |
| `run()` | `Any` | Runs the flow on an event loop in this thread until it returns; returns its result or raises what it raised. From a thread already running an event loop, runs on a new thread and waits. Raises `Refused` before the flow is called if an environment cannot be reached or is too small. |
| `start()` | `None` | Runs it on a new thread and returns at once. `RuntimeError` if already started. |
| `wait(timeout: float \| None = None)` | `bool` | Blocks until the run ends or `timeout` seconds pass; returns whether it ended. |
| `stop()` | `None` | Interrupts the turn under way; every flow call raises `CancelledError` where it stands; sessions are closed and temporary directories removed as the flow unwinds. Thread-safe. Does not wait. |
| `close()` | `None` | `stop()`, then closes every open session and agent at once. The flow sees a failed turn. |
| `unreadable()` | `str` | The budget cap nothing driven can enforce, in words (the [`hmz exec` note](/reference/cli#writing-a-budget)), or `""`. A finite `cost` limit first brings a missing or stale price list up to date (at most 20 s), as `run` and `start` do. |
| `watch(listener)` | `None` | Registers `listener(agent: AgentBase, session: SessionBase \| None, event: Event)`, called for every event of every session from the thread that read it. Watching also stops CLIs writing their own progress to this process's streams. |
| `noticed(callback)` | `None` | Registers `callback(text: str)`, called on the run's loop with humanize's own word about the run before the flow is called: an environment moved down its runtime's [fallback list](/reference/machines#falling-back) (`docker:a cannot hold 'box': <why>; using docker:b`). |
| `opened(callback)` | `None` | Registers `callback(role: str, agent: AgentBase, session: SessionBase, where: Placement | None)` (`where` is `None` where the driver reports no placement), called on the run's loop as each session opens, before its first turn. |

`AgentBase`, `SessionBase` and `Event` are coganchor's ([Agents](/reference/agents)).

## `Refused` {#refused}

```python
class Refused(ValueError): ...
```

A run, or a request to a host, refused before anything of it ran. `str(error)` is the message
`hmz exec` prints after `hmz exec: error: `, and the reason a host gives every frontend.
`__cause__` is the underlying exception where there was one (`FlowException`, `SpecError`,
`pydantic.ValidationError`).

## `Flows` {#flows}

`Hmz().flows`. Constructor: `Flows()`.

| Member | Returns | Behaviour |
| --- | --- | --- |
| `verses` | [`Flowverses`](#flowverses) | Property. |
| `all()` | `list[Offer]` | Every runnable flow, in offer order. |
| `find(named: str)` | `str` | The resolved file of a flow. `named` itself where nothing resolves: a flow exists iff the result is a file. |
| `about(named: str)` | `str` | The flow's one-line description, or `""`. |
| `declared(named: str \| PathLike)` | [`Declaration`](#declaration) | Imports the flow. Raises the flow API's `FlowException` for a flow that cannot load. |
| `resumes(named: str \| PathLike)` | `bool` | Whether it is [resumable](/reference/flows#a-flow-that-can-be-picked-up). Imports the flow. |
| `fork(named: str, into: str \| PathLike \| None = None)` | `str` | Copies the flow, what it imports and its skills into `./.hmz/flows/` (or `into`), as **Copy here** does in `/flow`; not an installed flow's `.installed.json`. Returns the directory. `ValueError`: not a flow, or already a copy here. `OSError`: cannot copy. |
| `running()` | `tuple[LiveCall, ...]` | Every flow call in progress in this process, oldest first. |

```python
for offer in Hmz().flows.all():
    print(offer.name, "·", offer.about)
```

## `Flowverses` {#flowverses}

`Hmz().verses`: the store [`/flow`'s Flowverses page](/reference/tui#where-flows-come-from)
edits. `flow` arguments are `<flowverse>/<flow>`, or a bare `<flow>` for `official`. Semantics:
[Flows › Flowverses](/reference/flows#flowverses).

| Method | Returns | Behaviour |
| --- | --- | --- |
| `all()` | `list[Flowverse]` | Offer order: `official`, added ones alphabetically, `local`, `user`. |
| `nearest()` | `list[Flowverse]` | Lookup order for a bare name: `local`, `user`, `official`, added ones. |
| `find(name: str)` | `Flowverse \| None` | |
| `add(url: str, name: str = "")` | `Flowverse` | Clones the index at `url` (a URL, a path, or `owner/repo` on GitHub) under `name` (default: the repository's name). Installs nothing. `ValueError`: name taken, reserved (`official`, `local`, `user`) or not a valid directory name. `OSError`: clone failed. |
| `fetch(name: str)` | `Flowverse` | Fetches the index again, or for the first time; resets the clone to the remote. Installed flows are untouched. `ValueError`: no such name, or `local`/`user`. `OSError`: git failed. |
| `remove(name: str)` | `bool` | Deletes the index and every flow installed from it; whether there was one. `ValueError`: `official`, `local`, `user`. |
| `index(name: str)` | [`Index`](#flowverse-types) | What its index lists, as last fetched. Reads YAML only; empty for `local`, `user`, an unfetched one or an unknown name. |
| `install(flow: str, version: str = "")` | `list[Installed]` | Installs that release (`""`: the newest that is not a prerelease, else the newest prerelease) and what it needs. Returns what is now installed of every flow the install came to, the asked-for one last. Another version of an installed flow switches it. `ValueError`: no such flowverse, flow or release; unfetched; a cycle; a range nothing satisfies; breaking another installed flow's range. `OSError`: fetch or copy failed. |
| `uninstall(flow: str)` | `bool` | Removes an installed flow; whether there was one. `ValueError`: another installed flow needs it. `OSError`: it will not go. |
| `installed()` | `list[Installed]` | Every installed flow, by flowverse and then name. |
| `updates()` | `list[Update]` | Every installed flow whose index, as last fetched, lists a newer release. |
| `holds(one: Flowverse)` | `list[Offer]` | What it offers to run: built-in and installed flows for `official`, installed ones for another, the directory's for `local` and `user`. **Imports every flow in it.** Never a flow its index only lists. |
| `edited(one: Flowverse)` | `bool` | Whether the clone holds changes a fetch would discard. `False` for a non-clone. |
| `standing(one: Flowverse)` | `str` | The clone's commit, or `""`. |
| `where(name: str)` | `Path` | Its index's directory, fetched or not. |
| `plain(url: str)` | `str` | `url` with credentials removed. |
| `whence(one: Flowverse, nowhere: str = "-")` | `str` | Displayable origin: the credential-free URL; `your own flows in .hmz/flows` for `local`; `nowhere` for a directory with no readable origin. |

```python
from hmz.sdk import Hmz

verses = Hmz().verses
verses.fetch("official")
for release in verses.index("official").versions("parallel_flame_chase"):
    print(release.version, release.commit[:12])
verses.install("parallel_flame_chase")
for update in verses.updates():
    print(update.installed.called, update.installed.version, "->", update.version)
```

## `Accounts` {#accounts}

`Hmz().accounts`: [provider accounts](/reference/providers). `cli` accepts any name or alias of
a backend. An account `name` of `""` is the machine's own login (*as local*).

| Method | Returns | Behaviour |
| --- | --- | --- |
| `all(cli: str = "")` | `list[Provider]` | Every account, or one backend's; by backend, then name. |
| `find(cli: str, name: str)` | `Provider \| None` | |
| `ways(cli: str)` | `tuple[Way, ...]` | How the backend can be signed into, in offer order (for `claude`: `login`, `token`, `key`, `gateway`, `bedrock`, `vertex`, `env`). |
| `way(cli: str, name: str)` | `Way \| None` | |
| `asks(way: Way, given: Mapping[str, str])` | `list[str]` | Variables still unanswered. |
| `make(cli, name, way: Way, answers=None)` | `Provider` | Writes an account from a way's answers; makes its directory. `ValueError`: bad backend or name. `OSError`. |
| `sign_in(provider, way, answers=None)` | `int` | **Runs** the backend's sign-in command under the account's paths; its exit status. |
| `write(cli, name, way="", env=None, args=())` | `Provider` | Writes an account as given, replacing `env`/`args`, keeping credentials. With `args` empty, a named `way` that adds arguments (codex's `gateway`) has them filled from `env`. `ValueError`, `OSError`. |
| `where(cli, name)` | `Path` | Its credentials directory. `ValueError`: unknown backend or invalid name. |
| `serves(one: Provider)` | `tuple[str, ...]` | Other backends its credentials could run. |
| `copies(one, cli, name="")` | `Provider` | Writes the same account for another backend. `ValueError`: that backend cannot use it. |
| `remove(cli, name)` | `bool` | Deletes an account and its credentials. `ValueError` for `""`. |
| `env(said: str)` | `dict[str, str]` | Parses `NAME=VALUE` lines. |
| `environ(provider: Provider \| None)` | `dict[str, str]` | The environment a turn under it gets; `{}` for `None`. |
| `models(cli, provider="")` | `tuple[Model, ...]` | What the backend last reported it runs as this account; `()` if never asked. |
| `asked(cli, provider="")` | `str` | When that was, or `""`. |
| `stale(cli, provider="")` | `bool` | Never asked, or asked longer ago than `hmz.coganchor.models.STALE` (one week). |
| `ask(cli, provider="", seconds=None)` | `tuple[Model, ...]` | **Starts the backend** to list its models, and keeps the answer. `()` if it does not answer. |

## `Runtimes` {#runtimes}

`Hmz().runtimes`: saved [runtimes](/reference/machines#runtimes),
named by `-e <role>=ssh@<name>` and `-e <role>=docker@<name>`. `backend` is `"ssh"` or
`"docker"`.

| Method | Returns | Behaviour |
| --- | --- | --- |
| `all(backend: str = "")` | `list[Runtime]` | By backend, then name. |
| `find(backend, name)` | `Runtime \| None` | |
| `where(backend, name)` | `Path` | Where it is kept. `ValueError`: bad backend or name. |
| `new(backend, name, **fields)` | `Runtime` | Builds and validates one; saves nothing. `ValueError`: unknown field or bad value. `new(**p.held())` equals `p`. `affinity=["self", "docker:gpubox", "local"]` sets where the harness of work on it runs ([Remote execution › Affinity](/reference/remote-execution#affinity)). |
| `add(runtime)` | `Runtime` | Saves a new one. `ValueError`: name taken. `OSError`. |
| `write(runtime)` | `Runtime` | Saves, replacing any of that name. `OSError`. |
| `remove(backend, name)` | `bool` | `ValueError`: bad backend or name. |
| `hosts(config: str \| PathLike \| None = None)` | `list[SSHHost]` | Every `Host` in an ssh config (default `~/.ssh/config`), as `ssh -G` resolves it. `OSError`: no `ssh`, unreadable config. |
| `import_ssh(config=None, names=None, *, update=False)` | `list[SSHRuntime]` | Saves one ssh runtime per `Host` (or per name in `names`), named after it; existing ones kept unless `update`. `ValueError`: a name not in the config. |
| `resolve(runtime: SSHRuntime)` | `SSHHost` | What `ssh -G` makes of it; reaches nothing. |
| `check(runtime, seconds: float = 30.0)` | `Checked` | **Reaches** it: an ssh host for home, CPUs, memory, GPUs; a docker daemon via `docker info`. Never raises. |

## `Fallbacks` {#fallbacks}

`Hmz().fallbacks`: [fallback chains](/user/settings#fallback) between *places*, each spelled
`<cli>[@<account>]/<model>`. A chain is written against one place, its main, and lists the
places tried after it, in order.

| Member | Returns | Behaviour |
| --- | --- | --- |
| `default` | `str` | Property: `"exponential-jitter"`. |
| `policies()` | `tuple[Policy, ...]` | `none`, `constant`, `linear`, `exponential`, `exponential-jitter`, `fibonacci`. |
| `named(policy: str)` | `Policy \| None` | |
| `spec(backend, model, provider="")` | `str` | `spec("codex", "gpt-5.6-sol", "work")` → `"codex@work/gpt-5.6-sol"`. |
| `reads(said: str)` | `str` | The canonical spelling, or `""` for none. |
| `all()` | `list[Falls]` | Every step, in the order written. |
| `tried(said)` | `Falls` | The step for a place (empty `Falls` where none). |
| `chain(said)` | `list[str]` | `[said, *to]` where a rule is written against `said`, else `[said]`: a place only on somebody else's chain has none, and chains are never joined. |
| `points(said, to: Sequence[str])` | `Falls` | Sets the places `said` falls back to, in order (`[]` none; a single string is one place). `ValueError`: not a place, itself, or a place named twice. |
| `retrying(said, tries: int, policy: str, timeout: float)` | `Falls` | Sets extra tries (`0` none), the wait policy, and the total limit in seconds (`0` none). `ValueError`. |
| `clear(said)` | `bool` | Removes the step. |

## `Epics` {#epics}

`Hmz().epics`, or `Epics(workspace=None)`. A run is named by its epic directory.

| Method | Returns | Behaviour |
| --- | --- | --- |
| `under()` | `Path` | This workspace's epics directory. |
| `all()` | `list[Path]` | Every epic, oldest first. |
| `read(epic: Path)` | `Ran \| None` | `None` for a directory holding no run. |
| `sessions(epic)` | `list[Session]` | Every session, across every record of the epic. |
| `opened(epic)` | `dict[str, list[str]]` | Session ids per agent role. |
| `resumed(flow: str)` | `Path \| None` | The epic `--resume` would pick up. `flow`: canonical ref or name as run. |
| `picks_up(epic)` | `bool` | Whether its journal has an entry. |
| `state(epic, flow: str = "")` | `dict[str, Any]` | A resumable flow's kept `ctx.state`: the run's own flow, or another by canonical ref. |
| `traced(epic, *, output=None, start=None, end=None)` | `tuple[Path, dict]` | Gathers the run's own sessions into a Chrome trace. Default `output`: the epic's `traces/`, named for the moment. `start`/`end`: any wording `dateparser` reads. [Tracing](/reference/tracing#from-python). |
| `trace(*, sessions=None, agents=None, output=None, start=None, end=None, profile=None, kept=None)` | `dict` | The same collector for any sessions. `sessions=None`: every session of the workspace; empty iterable: none. `kept`: directories of kept sessions to read (default: everywhere humanize keeps them). |
| `bundled(epic, *, output=None, transcript=None)` | `tuple[Path, dict]` | One `.epic.tar.gz` of the whole run, credentials struck out. Default `output`: `./.hmz/`. Returns the path and its manifest. [Exporting a run](/user/export). |

## `Host` {#host}

```python
class Host:
    def __init__(self, hmz: Hmz) -> None
```

A workspace's runs as every attached frontend shares them. `Hmz().host()` holds one in this
process; a [daemon](/reference/daemon) holds one in its own. Frontends reach it through
[`Link`](#link) rather than calling it directly.

| Member | Returns | Behaviour |
| --- | --- | --- |
| `attach(name, kind, heard, *, replay=True)` | `str` | Attaches a frontend; returns its client id. `kind`: `tui`, `cli` or `sdk`. `name` `""`: login + `@kind`; duplicates get `#2`, `#3`. `heard(message)` is called on a thread of the host's. `RuntimeError` once closed. |
| `detach(client)` | `None` | Lets one frontend go: its claims are released and its asides closed. |
| `attached` | `int` | Property: frontends attached. |
| `idle` | `bool` | Property: nothing running or stopping, nobody attached, and no unread ended run. |
| `closed` | `bool` | Property. |
| `away_for(role)` | `bool` | What `afk` last said of that role, else of every role. |
| `printed(text)` | `None` | Sends one `printed` line to every frontend. |
| `asked(client, said)` | `dict` | Carries out one [request](/reference/daemon#requests); returns `{"ok": …, "why"?: …}`. |
| `status()` | `dict` | See [`Daemon.status`](/reference/daemon#status). |
| `close()` | `None` | Closes every run, tells every frontend `gone`, and waits a bounded time for runs to release what they made. |

## `Daemons` {#daemons}

```python
class Daemons:
    def here(self, workspace: str | os.PathLike[str] | None = None) -> Daemon | None
    def all(self) -> list[Daemon]
    def host(self, workspace: str | os.PathLike[str] | None = None) -> Daemon
```

| Method | Same as | Behaviour |
| --- | --- | --- |
| `here(workspace=None)` | `hmz.daemon.running` | The host holding that workspace's runs, or `None` (no daemon answers on this machine's socket, or it holds no host of that workspace). |
| `all()` | `hmz.daemon.daemons` | Every live workspace's host on this machine, oldest first. |
| `host(workspace=None)` | `hmz.daemon.host` | The host of the workspace, started where none is -- and this machine's daemon with it (10 s each to come up). `OSError`: an older humanize's daemon is running, or none came up. |

`workspace=None` is the current directory.

## `Daemon` {#daemon}

<span id="session"></span>

```python
@dataclass(frozen=True, slots=True)
class Daemon:
    at: Path            # this machine's daemon's directory (socket, daemon.json)
    workspace: str      # the project directory its host holds runs for
    pid: int            # the host process
    started: str        # UTC, ISO 8601
    protocol: int = 0   # the frontend protocol the daemon speaks; 0 = an older humanize's
```

| Member | Returns | Behaviour |
| --- | --- | --- |
| `alive` | `bool` | Property: the process exists. |
| `link(name="", kind="sdk", *, replay=True)` | [`Link`](#link) | Attaches a frontend. `OSError`: nothing accepts the connection, or `hello` is refused or not answered within 10 s. `protocol` is not checked here (`host()` and `hmz` check it). |
| `status()` | `dict` | [Status keys](/reference/daemon#status); from these fields for a host that does not answer. |
| `detach()` | `int` | Lets every frontend go; runs continue. Returns how many. |
| `stop(*, seconds=20.0)` | `bool` | Asks the host to close its runs and exit; waits up to `seconds`. Whether it has gone. |
| `kill(*, seconds=20.0)` | `bool` | `SIGTERM` to the host process, then `SIGKILL`; the daemon and other workspaces' hosts go on. Whether it has gone. |
| `asked(said: dict)` | `dict` | Sends one [control request](/reference/daemon#control-requests); `{}` where no answer came. |

## `Link` {#link}

```python
class Link:
    client: str
    def told(self, message: dict[str, Any]) -> None
    def heard(self, listener: Callable[[dict[str, Any]], None]) -> None
    def __iter__(self) -> Iterator[dict[str, Any]]
    def asked(self, said: Mapping[str, Any], *, seconds: float | None = None) -> dict[str, Any]
    def start(self, flow: str | os.PathLike[str], task: str, *,
              agents: Mapping[str, Any] | None = None, envs: Mapping[str, Any] | None = None,
              params: Any = None, budget: Any = None, profile: bool = False,
              resume: bool | str | os.PathLike[str] = False) -> dict[str, Any]
    def say(self, text: str, *, to: str = "") -> dict[str, Any]
    def answer(self, question: str, text: str) -> dict[str, Any]
    def stop(self) -> dict[str, Any]
    def force(self) -> dict[str, Any]
    def afk(self, *, on: bool, role: str = "") -> dict[str, Any]
    def claim(self, role: str, *, take: bool = False) -> dict[str, Any]
    def release(self, role: str) -> dict[str, Any]
    def board(self, key: str, value: str) -> dict[str, Any]
    def aside(self, **said: Any) -> dict[str, Any]
    def close(self) -> None
    def __enter__(self) -> Self
    def __exit__(self, *exc) -> None      # close()
```

One frontend of a [`Host`](#host), in this process or over a daemon's socket; the same class
either way. Obtained from [`Daemon.link`](#daemon), or `hmz.daemon.linked(host, …)` for a host
in this process.

| Member | Behaviour |
| --- | --- |
| `client` | This frontend's client id; `owner` and `client` fields in messages use it. |
| `told(message)` | Called by the transport to deliver a message. Not for callers. |
| `heard(listener)` | Delivers every message, already-queued ones first, to `listener` on a thread of the link's own, in order. `RuntimeError` if a listener is already set. |
| `__iter__` | Yields every message in order until `gone` or `close()`. `RuntimeError` if a listener is set. |
| `asked(said, *, seconds=None)` | Sends one [request](/reference/daemon#requests) and waits (`seconds=None`: indefinitely; ignored in process). Returns the reply (`ok: true`). Raises [`Refused`](#refused) with the reply's `why`, or `TimeoutError("no answer to '<do>' in <s>s")`. |
| `start(…)` | `start` request. `agents`/`envs`: specs as `-a`/`-e` after `<role>=`. `params`, `budget`: mappings or models (serialised). `profile`: whether the run is [profiled](/reference/tracing#profiling-a-run). Reply carries `run`. |
| `say`, `answer`, `stop`, `force`, `afk`, `claim`, `release`, `board`, `aside` | The request of the same name. |
| `close()` | Lets go of the host; runs continue. |

Every method that sends a request goes through `asked` and raises `Refused` when refused,
including after the host has gone (the reason is then the [`gone`](/reference/daemon#gone)
reason). `Link` has no helpers for the `unaside`, `status`, `detach` and `quit` requests: send
them with `asked({"do": …})`. Transport differences (socket or in process) are in
[Daemon › Link](/reference/daemon#link).

```python
from hmz.sdk import Daemons

with (Daemons().here() or Daemons().host()).link(name="ci", replay=False) as link:
    link.claim("reviewer")
    for said in link:
        if said["type"] == "pending":
            for asked in said["pending"]:
                if asked["owner"] == link.client:
                    link.answer(asked["question"], "looks good")
```

## `fakes` {#fakes}

`hmz.runtime.flowing.fakes`, whole. `__all__`:

| Name | Is |
| --- | --- |
| `run_fake(flow, task="", *, agents=None, envs=None, params=None, budget=None, outworlder=None, local=None, journal=None, resume=False, recorder=None)` | Runs a flow on fakes in memory. |
| `FakeAgentDriver(harness=HarnessKind.CLAUDE, *, reply=None, model="fake", effort="", provider="", capabilities=None, cost=0.0, output_tokens=1, seconds=0.0, forks=None, names_late=False)` | A scripted agent driver. Also accepted by `Hmz.run(agents=…)`, which then writes a real epic. |
| `FakeSession` | A session of a `FakeAgentDriver`. |
| `FakeEnvDriver(files=None, *, workdir="/work", backend=EnvBackendKind.LOCAL, provider="", capabilities=None, cpu_count=8, memory=64 GiB, gpu_count=0, gpu_memory=0, run=None, refs=("HEAD", "main"), repo=True)` | An in-memory environment. |
| `FakeOutworlder(reply=None, *, away=False)` | An outworlder answering from a script. |
| `Answer`, `Command`, `Handler`, `Reply` | Type aliases for the scripts above. |

Semantics: [Flows › Testing a flow](/reference/flows#testing-a-flow).

## Returned types {#returned-types}

Internal types returned by the classes above. Named tuples and frozen dataclasses; fields in
declaration order.

### `Line` {#line}

`hmz.runtime.runner.Line` (named tuple), from [`Hmz.read`](#hmz-read).

| Field | Type | Default | From |
| --- | --- | --- | --- |
| `flow` | `str` | — | `-f` |
| `task` | `str` | — | `task` |
| `agents` | `tuple[AgentSpec, ...]` | `()` | every `-a`, in order |
| `envs` | `tuple[EnvSpec, ...]` | `()` | every `-e`, in order |
| `params` | `dict[str, str]` | `{}` | every `-p` but `budget.*`, values unparsed |
| `budget` | `Budget \| None` | `None` | every `-p budget.<limit>=`, parsed |
| `profile` | `bool` | `False` | `--profile` |
| `resume` | `bool` | `False` | `--resume` |
| `as_json` | `bool` | `False` | `--json` |

### `AgentSpec`, `EnvSpec` {#specs}

`hmz.runtime.flowing.specs`, frozen dataclasses. `str()` writes each back as its flag takes it.

| Type | Fields |
| --- | --- |
| `AgentSpec` | `role: str`, `harness: HarnessKind` (`ACP` for an ACP CLI), `provider: str` (`""` = as local), `model: str`, `effort: str` (`""` = auto), `cli: str` |
| `EnvSpec` | `role: str`, `backend: EnvBackendKind`, `provider: str` (a saved runtime's name, an ssh host nobody saved in its brackets, `"[me@box:22]"`, or `""` for this machine), `workdir: PurePosixPath` (`~/…` relative to home) |

### Flow types {#flow-types}

| Type | Fields |
| --- | --- |
| `Offer` | `whose: str` (a flowverse, `local` or `user`), `name: str` (what `-f` takes), `about: str` |
| <span id="declaration"></span>`Declaration` | `name`, `ref`, `description: str \| None`, `hidden: bool`, `resumable: bool`, `agents: tuple[AgentRole, ...]`, `envs: tuple[EnvRole, ...]`, `params: type[FlowParams]`; methods `agent(name)`, `env(name)` → role or `None` |
| `AgentRole` | `name`, `declared: type`, `required: bool`, `auto: bool` (runtime-filled), `harness: HarnessKind \| None`, `capabilities: frozenset[type]`, `permission`, `skills: tuple[str, ...]`, `grant` |
| `EnvRole` | `name`, `declared: type`, `required`, `auto`, `capabilities`, `cpu_count: int`, `memory: int`, `gpu_count: int`, `gpu_memory: int`, `image: str`, `grant`, `resources: bool` |
| `LiveCall` | `ref`, `name`, `depth: int` (1 = the run's flow), `since: float` (monotonic), `id: int` (journal id, 0 = none), `parent: LiveCall \| None`, `task: str`, `resumable: bool` |
| `Flowverse` | `name`, `url` (`""` for `local`, `user`), `at: Path`, `fetched: bool`, `fixed: bool` (`official`, `local`, `user`) |

### Flowverse types {#flowverse-types}

`hmz.runtime.flowing.index`; all but `Skipped` are also exported from `hmz.runtime.flowing`.

| Type | Fields |
| --- | --- |
| `Index` (named tuple) | `verse: str`, `releases: tuple[Release, ...]` (by flow, newest first), `skipped: tuple[Skipped, ...]`; methods `flows()` (names, sorted), `versions(flow)` (newest first), `release(flow, version)` → `Release \| None`, `newest(flow, spec="")` → the newest in range that is not a prerelease, else the newest prerelease, else `None` |
| `Release` (pydantic, frozen) | `name`, `version`, `description`, `repo`, `ref`, `commit`, `subdir`, `license`, `dependencies: dict[str, str]`; properties `semver` (a `semver.Version`), `url` (what git fetches) |
| `Skipped` (named tuple) | `at: Path` (the manifest), `why: str` |
| `Installed` (pydantic, frozen) | `verse`, `name`, `version`, `commit`, `repo`, `ref`, `subdir`, `dependencies`; properties `called` (the name it is offered under), `at: Path` (its directory) |
| `Update` (named tuple) | `installed: Installed`, `version: str` (the newest after it) |

### Account types {#account-types}

| Type | Fields |
| --- | --- |
| `Provider` | `cli`, `name`, `way: str = "env"`, `env: Mapping[str, str]`, `args: tuple[str, ...]`, `made: str`; property `at: Path`; methods `held()`, `command(argv)`, `swaps()` |
| `Way` | `name`, `about`, `argv: tuple[str, ...]` (sign-in command), `asks: tuple[Asked, ...]`, `sets: tuple[tuple[str, str], ...]`, `args: tuple[str, ...]`, `stdin: str` |
| `Model` | `name`, `efforts: tuple[str, ...]` (hardest first), `swarms: bool = False` |
| `Falls` | `spec`, `to: tuple[str, ...]` (`()` = nowhere), `tries: int = 0`, `policy: str = "exponential-jitter"`, `timeout: float = 0.0`; method `says()` |
| `Policy` | `name`, `about` |

### Environment types {#environment-types}

| Type | Fields |
| --- | --- |
| `SSHRuntime` | `name`, `host`, `user`, `port: int = 0`, `identity_file`, `proxy_jump`, `options: Mapping[str, str]`, `alias`, `config`, `workdir`, `made: str = "typed"` (`typed`/`imported`); property `at`; methods `destination()`, `login()`, `settings()`, `target()` (coganchor target), `held()`; `backend == "ssh"` |
| `DockerRuntime` | `name`, `endpoint: str = "local"`, `tls_dir`, `image`, `runtime`, `run_args: tuple[str, ...]`, `cpus: float`, `memory: int` (bytes), `gpus: tuple[str, ...]`, `gpu_memory: int`, `max_containers: int` (0 = no limit), `workdir`, `made`; property `at`; methods `daemon()` → `Endpoint` ([Machines](/reference/machines#a-docker-daemon)), `held()`; `backend == "docker"` |
| `SSHHost` | `alias`, `host`, `user`, `port: int`, `identity_files: tuple[str, ...]`, `proxy_jump` |
| `Checked` | `reached: bool`, `said: str`, `home: str`, `cpus: float`, `memory: int`, `gpus: tuple[str, ...]`, `gpu_memory: int`, `runtimes: tuple[str, ...]`, `version: str`, `short: tuple[str, ...]` (what it is saved to hand out and has not got) |

### Epic types {#epic-types}

`hmz.runtime.epic`, named tuples. Values as the [epic record](/reference/tracing#epics) wrote
them.

| Type | Fields |
| --- | --- |
| `Ran` | `at: Path`, `flow`, `task`, `workspace`, `began`, `ended` (`""` while running or abandoned), `how` (`done`, `failed`, `stopped`, or `""`), `agents: tuple[Drove, ...]`, `sessions: tuple[Session, ...]`, `called: tuple[Called, ...]`, `resumable: bool`, `ref`, `envs: tuple[str, ...]` (as `-e` spells them, a run's kept in an older spelling included), `params: dict`, `budget: dict \| None`, `picked_up: str` (epic name or `""`), `profile: bool` (whether it was [profiled](/reference/tracing#profiling-a-run)); property `name` |
| `Drove` | `agent`, `backend`, `model`, `effort` (`""` = auto), `provider` (`""` = as local); property `spec` (`-a` spelling after `<role>=`) |
| `Called` | `flow`, `task`, `record` (file in the epic), `began`, `ended`, `how`, `calls: tuple[Called, ...]` |
| `Session` | `agent`, `backend`, `provider` (`local` = as local), `ident` (backend's id), `name`, `at`, `flow`, `parent` (forked-from id or `""`), `record`, `where` (kept-session path), `harness` (`local`, `self`, the `<backend>:<name>` of a runtime an affinity sent it to, or `""` for work on this machine) |

---
pageClass: hmz-ref
---

<script setup>
import '../.vitepress/theme/components/ref-cli/ref.css'
</script>

# SDK reference

`hmz.sdk`: the supported import path for programs that drive Humanize. It defines `Hmz`,
`Run`, `Client`, `Daemons` and `fakes`; every other name is the object the runtime or the
daemon layer holds, handed through unchanged. Its epics are run by a daemon, never in the
calling process. Notation: [Conventions](/reference/#conventions).

```python
from hmz.sdk import Hmz, Daemons, Refused, fakes
```

## Module {#module}

```python
__all__ = ["Accounts", "Ask", "Client", "Daemon", "Daemons", "Epics", "Flows", "Flowverses", "Hmz",
           "Link", "NousBook", "Refused", "Run", "Runtimes", "fakes"]
def __getattr__(name: str) -> object: ...
```

| Name | Kind | Defined in | Section |
| --- | --- | --- | --- |
| `Hmz` | class | `hmz.sdk.running` | [Hmz](#hmz) |
| `Run` | class | `hmz.sdk.running` | [Run](#run) |
| `Ask` | frozen dataclass | `hmz.runtime.flowing.spi` | [OutworlderDriver](#outworlderdriver) |
| `Refused` | exception | `hmz.runtime` | [Refused](#refused) |
| `Flows` | class | `hmz.runtime` | [Flows](#flows) |
| `Flowverses` | class | `hmz.runtime` | [Flowverses](#flowverses) |
| `Accounts` | class | `hmz.runtime` | [Accounts](#accounts) |
| `Runtimes` | class | `hmz.runtime` | [Runtimes](#runtimes) |
| `NousBook` | class | `hmz.runtime` | [NousBook](#nousbook) |
| `Epics` | class | `hmz.runtime` | [Epics](#epics) |
| `Client` | class | `hmz.sdk.client` | [Client](#client) |
| `Daemons` | class | `hmz.sdk.daemons` | [Daemons](#daemons) |
| `Daemon` | frozen dataclass | `hmz.daemon` | [Daemon](#daemon) |
| `Link` | class | `hmz.daemon` | [Link](#link) |
| `fakes` | module | `hmz.sdk.faking` | [fakes](#fakes) |

| Rule | |
| --- | --- |
| Lazy | Each name is imported from its layer on first access (module `__getattr__`). `import hmz.sdk` imports nothing else. |
| Identity | `hmz.sdk.X is <layer>.X`: the same class, not a wrapper. `hmz.sdk.Hmz` subclasses `hmz.runtime.Hmz`. |
| Unknown names | `AttributeError: module 'hmz.sdk' has no attribute '<name>'`. |
| `fakes` | A module attribute: `from hmz.sdk import fakes` works; `import hmz.sdk.fakes` raises `ModuleNotFoundError`. |
| Stability | Names in `__all__` are stable. Types they return that are not in `__all__` (`Line`, `Opened`, `Offer`, `Declaration`, `Provider`, …, listed under [Returned types](#returned-types)) are internal: their fields are documented as they are. |

## `Hmz` {#hmz}

```python
class Hmz:
    def __init__(self, workspace: str | os.PathLike[str] | None = None) -> None
```

One workspace and everything Humanize can be asked to do in it. The constructor loads
nothing.

| Parameter | Type | Default | Meaning |
| --- | --- | --- | --- |
| `workspace` | `str \| PathLike \| None` | `None` | The project directory. `None`: the current directory, re-read at each use. Kept as given; `~` is not expanded. |

### Properties {#hmz-properties}

| Property | Type | Value |
| --- | --- | --- |
| `workspace` | `Path` | The project directory. |
| `home` | `Path` | `$HUMANIZE_HOME`, else `~/.hmz` (a `~/.humanize` is moved there). Not created. |
| `settings` | `hmz.runtime.settings.Settings` | What is remembered for this workspace and machine ([Settings](/reference/settings)). Internal type. |
| `flows` | [`Flows`](#flows) | |
| `verses` | [`Flowverses`](#flowverses) | The same object as `flows.verses`. |
| `accounts` | [`Accounts`](#accounts) | |
| `runtimes` | [`Runtimes`](#runtimes) | |
| `nous` | [`NousBook`](#nousbook) | |
| `epics` | [`Epics`](#epics) | Of this workspace. |

`workspace` and `home` are computed on each access; the others are created on first access and
cached on the instance.

### Methods {#hmz-methods}

| Method | Returns | Raises |
| --- | --- | --- |
| [`run(flow, task, *, …)`](#hmz-run) | [`Run`](#run) | `Refused`, `OSError` |
| [`runner(flow, *, …)`](#hmz-runner) | `Runner` | `Refused`, `OSError` |
| [`read(argv)`](#hmz-read) | [`Line`](#line) | `SystemExit` |
| [`exec(argv)`](#hmz-exec) | `Any` | `SystemExit`, `Refused`, `OSError`, what the flow raised |
| `backends()` | `tuple[Profile, ...]` | — |
| `reports()` | `bool` | — |

- `backends()`: every coding-agent CLI Humanize drives, installed or not, as internal
  `hmz.coganchor.backends.Profile` objects (`.name`, `.aliases`, `.efforts`, `.installs`, …).
  `[p.name for p in Hmz().backends()]` is `['claude', 'agy', 'codex', 'dsh', 'grok', 'kimi',
  'pi', 'omp', 'qwen', 'opencode', 'mimo', 'cursor-agent', 'mcode', 'litellm']`.
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
    profile_flow: bool = False,
    profile_environment: bool = False,
    resume: bool | str | os.PathLike[str] = False,
    outworlder: OutworlderDriver | None = None,
    backup: Iterable[str] | None = None,
) -> Run
```

Equivalent to `Run(self.runner(flow, agents=…, envs=…, params=…, budget=…, profile_flow=…,
profile_environment=…, resume=…, backup=…), task, outworlder=outworlder)`. Nothing starts. Where each agent's harness runs is not a parameter:
it is the `harness` setting of the [runtime](#runtimes) its work is on.

The epic is held by this machine's [daemon](/reference/daemon), started where none runs, and
outlives the program that asked for it. Where any role is given a driver object (a
`fakes.FakeAgentDriver`, …), it is held instead by a private daemon of the calling program's
own, as [`run_fake`](#fakes) holds it.

| Parameter | Accepts | Default |
| --- | --- | --- |
| `flow` | A [`-f` ref](/reference/cli#naming-a-flow) or a path. | — |
| `task` | The task text. | — |
| `agents` | `{role: spec}` where spec is an [`-a` spec](/reference/cli#writing-an-agent) without `<role>=` (`"claude@work/claude-opus-5:high"`) or an `AgentDriver` (e.g. `fakes.FakeAgentDriver`); or an iterable of `AgentSpec` (`Line.agents`). | `()` |
| `envs` | `{role: spec}` with an [`-e` spec](/reference/cli#writing-an-environment) without `<role>=`, or an `EnvDriver`; or an iterable of `EnvSpec`. | `()` |
| `params` | A mapping (strings read as `-p` reads them) or an instance of the flow's `FlowParams`. `None`: defaults. | `None` |
| `budget` | A [`Budget`](/reference/flows#what-a-run-may-spend), or a mapping validated by `Budget.model_validate` (`{"cost": 5}`, `{"duration": 3600}`, `{"duration": "PT1H"}`; `"1h"` is **not** accepted). `None`: refused. | `None` |
| `profile_flow` | Whether to [profile](/reference/tracing#profiling-a-run) the flow's own Python, as well as tracing the run; as `--profile-flow`. | `False` |
| `profile_environment` | Whether to [profile](/reference/tracing#profiling-a-run) the programs the run's agents start, as well as tracing them; as `--profile-environment`. | `False` |
| `resume` | `False`: from the top. `True`: the newest resumable epic of this flow here. A path: that epic. | `False` |
| `outworlder` | The [driver](#outworlderdriver) answering `Outworlder` roles (e.g. `fakes.FakeOutworlder`), from this process: the run claims each such role, sets away those its `away_for` says, and answers each question with what its `run(ask, role)` returns. `None`: every role away, as under `hmz exec`. | `None` |
| `backup` | The names of the [backup targets](/reference/settings#backup) the epic is [backed up](/user/backups) to, as `--backup`; an empty iterable: nowhere. `None`: the settings' `backup.defaults`. | `None` |

Raises `OSError` where the daemon cannot be reached, and [`Refused`](#refused) for everything
[`hmz exec` refuses at stage 3](/reference/cli#processing-order), in the same words, plus:

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
def runner(self, flow, *, agents=(), envs=(), params=None, budget=None, profile_flow=False,
           profile_environment=False, resume=False, backup=None) -> Runner
```

Parameters and refusals as [`run`](#hmz-run), without `task` and `outworlder`. Asks the
daemon that is to hold the epic to check it (`flows.check`), and returns the internal
`hmz.sdk.running.Runner`: what `epic.start` will be called with, and what the check answered.
Nothing is started, and no CLI or machine is reached.

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
              params=line.params, budget=line.budget, profile_flow=line.profile_flow,
              profile_environment=line.profile_environment, resume=line.resume)
```

### `Hmz.exec` {#hmz-exec}

```python
def exec(self, argv: list[str]) -> Any
```

`read(argv)`, then `run(…)`, then `Run.run()`. Returns what the flow returned, as the
`ended` record says it. Raises `OSError` where the daemon cannot be reached. Unlike the
`hmz exec` command it draws nothing, installs no signal handlers and does not convert
`Refused` or `BudgetExceeded` into an exit status.

## `Run` {#run}

```python
class Run:
    def __init__(self, runner: Runner, task: str, *,
                 outworlder: OutworlderDriver | None = None) -> None
```

One epic, held by a daemon on a new exec slot (`exec:<hex>`) of the workspace and followed
by a subscription of a [`Client`](#client) of its own. Made by [`Hmz.run`](#hmz-run).
Constructing one starts nothing. If its session ends before the `ended` record, the run
attaches again where it left off; where it cannot, or where the host it attaches to is
another than the one it followed (a daemon started since holds no such epic), it ends with
`RuntimeError("the daemon went away")`. A host that lets go of it before the `ended` record
([`gone`](/reference/daemon#gone)) ends it with `RuntimeError(<why>)`, e.g. `the host went
away`; one that let go of it for falling behind (`too far behind; attach again`) does not: the
run then attaches again and claims its outworlder's roles again. Once the epic has ended it stays attached, on a thread
of its own, while `backed` of `runs.get` says a backup its end queued (to a target whose policies hold `end`) is not done, so that its host waits for
the backups too, for at most 60 seconds or until `close()`.

### Properties {#run-properties}

| Property | Type | Value |
| --- | --- | --- |
| `flow` | `str` | The flow as named. |
| `ref` | `str` | Its canonical ref (`rlar:rlar`, `humanize1:rlcr`). |
| `task` | `str` | |
| `declaration` | `dict` | What the flow declares: the `declared` mapping the daemon's check answered. |
| `budget` | `Budget` | What the run may spend. |
| `profile_flow`, `profile_environment` | `bool` | Whether the run's flow, and the programs its agents start, are [profiled](/reference/tracing#profiling-a-run) as well as traced. |
| `usage` | `hmz.flows.Usage` | Spent so far, as the latest `usage` record says: `duration: timedelta`, `cost: float`, `output_tokens: int`. |
| `agents` | `tuple[Opened, ...]` | Each **open** session, oldest first, as its `opened` record said it. |
| `epic` | `Path \| None` | The epic directory, once the daemon names it. |
| `running` | `bool` | Whether it is going: from `start()` until its `ended` record. |
| `raised` | `BaseException \| None` | Once over: `asyncio.CancelledError` (stopped), `BudgetExceeded` (budget), `Refused` (refused), `RuntimeError(why)` (failed or crashed), else `None`. On a private daemon, the very exception the flow raised. |
| `result` | `Any` | Once over: the `result` of the `ended` record (JSON). On a private daemon, the very object the flow returned. |

A flow named by a [`git+` ref](/reference/flows#refs) is loaded only once fetched, so no check
answers before the run starts: `declaration` is `{}` and `unreadable()` `""`; `budget` is the one
given, and `ref` is `""` until the `started` record comes, which says them both. With an
outworlder, the run claims the flow's `Outworlder` roles as that record names them, before it
answers any question.

### Methods {#run-methods}

| Method | Returns | Behaviour |
| --- | --- | --- |
| `run()` | `Any` | `start()`, then waits for the `ended` record; returns `result` or raises `raised`. |
| `start()` | `None` | Attaches to a new exec slot of the workspace, sets every role away (or, with an outworlder, claims its roles), and starts the epic (`epic.start`); returns at once. `Refused` if `epic.start` is refused; `OSError` if the daemon cannot be reached; `RuntimeError` if already started. |
| `wait(timeout: float \| None = None)` | `bool` | Blocks until the `ended` record comes or `timeout` seconds pass; returns whether it came. |
| `stop()` | `None` | Stops the epic (`epic.stop`); every flow call raises `CancelledError` where it stands. Thread-safe. Does not wait. |
| `close()` | `None` | `stop()`, then forces the epic (`epic.force`) where it has not ended, and lets go of the daemon. |
| `unreadable()` | `str` | The budget cap nothing driven can enforce, in words (the [`hmz exec` note](/reference/cli#writing-a-budget)), or `""`, as the daemon's check answered it. |
| `watch(listener)` | `None` | Registers `listener(agent: str, session: str \| None, event: dict)`, called with the agent's name, its session's key, and the `event` record, for every event of every session, from the client's thread. |
| `noticed(callback)` | `None` | Registers `callback(text: str)`, called with every `notice` record: Humanize's own word about the run, such as an environment moved down its runtime's [fallback list](/reference/machines#falling-back) (`docker:a cannot hold 'box': <why>; using docker:b`). |
| `printed(callback)` | `None` | Registers `callback(text: str)`, called with every line the host printed while it held the epic (`printed` records). |
| `opened(callback)` | `None` | Registers `callback(role: str, opened: Opened)`, called as each `opened` record comes, before any event of that session. |

`Opened` (`hmz.sdk.running`, frozen dataclass): `key` (`<agent>/<n>`), `role`, `agent`, `cli`,
`model`, `person: bool`, `env: dict \| None`, `harness`. Records: [Daemon](/reference/daemon).

## `OutworlderDriver` {#outworlderdriver}

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Ask:
    prompt: str
    schema: dict[str, Any] | None
    model: type[BaseModel] | None = None
    context: tuple[dict[str, Any], ...] = ()
    face: str = ""
    session: str = ""
    errors: tuple[dict[str, Any], ...] = ()

class OutworlderDriver(Protocol):
    def away_for(self, role: str) -> bool: ...
    async def run(self, ask: Ask, role: str) -> str | BaseModel | Mapping[str, Any]: ...
    # optional:
    # def show(self, context: tuple[dict[str, Any], ...], session: str, role: str) -> None: ...
```

What answers a run's `Outworlder` roles from a program, given to [`Hmz.run`](#hmz-run) or
[`Run`](#run) as `outworlder=`. It is handed each question exactly as a person's frontend is.
Guide: [The person as an agent › From a program](/weaver/human-agent#from-a-program).

| `Ask` field | Value |
| --- | --- |
| `prompt` | What the flow asked. |
| `schema` | The JSON Schema of the flow's `output_schema`, or `None` for a text question. |
| `model` | `None`: the pydantic model lives in the flow's process, and a `Run` has only its schema. |
| `context` | The question's [context blocks](/reference/flows#context-blocks), as JSON. |
| `face` | The hash of the session's [face](/reference/flows#face), or `""`. A driver draws no face, and is never handed one: its `mount`, if it has one, is not called. |
| `session` | `<role>/<n>`: the same for every question of one outworlder session. |
| `errors` | `()`, or, on a try after a refused answer, `[{path, message}]` saying why. |

| Member | Behaviour |
| --- | --- |
| `away_for(role)` | Whether that role is set away when the run starts. An away role is never asked. |
| `run(ask, role)` | The answer: a `str`, sent as `text` (JSON text is read as the value of a schema question); a mapping or a pydantic model for a schema question, sent as `value` (a model as `model_dump(mode="json")`). `""`, or raising, answers nothing, as an away person does. |
| `show(context, session, role)` | Optional. Called with what the flow [showed](/reference/flows#outworlder) the role; absent, it is not delivered. Its return is ignored. |

**A refused answer.** An answer that does not fit the schema is refused by the host. `run` is
called again with the same `Ask`, its `errors` set, up to twice more: three tries in all. Where
the third misfits too, the question is answered as an away person answers it: the role is set
away, and back again unless `away_for` now says it is away. An answer refused for any other
reason, answered elsewhere first say, is left at that.

```python
from typing import Any

from hmz.sdk import Ask, Hmz


class Approver:
    def away_for(self, role: str) -> bool:
        return False

    async def run(self, ask: Ask, role: str) -> str | dict[str, Any]:
        if ask.schema is None:
            return "looks good"
        return {"verdict": "approve", "notes": ""}


Hmz().run("gate", "add subtract", agents={"builder": "claude/claude-sonnet-5-5:low"},
          budget={"cost": 1}, outworlder=Approver()).run()
```

## `Refused` {#refused}

```python
class Refused(ValueError):
    def __init__(self, message: str, *, code: int = 0, data: dict | None = None) -> None
    code: int
    data: dict[str, Any]
```

A run, or a request to a daemon or host, refused before anything of it ran. `str(error)` is
the message `hmz exec` prints after `hmz exec: error: `, and the reason a host gives every
frontend. `code` is the daemon's error code (409 for a host's refusal, 503 once a
[`Client`](#client)'s session has ended, 0 for a refusal made in the calling process); `data`
is the error's further fields, or `{}`. `__cause__` is the underlying exception where there
was one (`FlowException`, `SpecError`, `pydantic.ValidationError`).

## `Flows` {#flows}

`Hmz().flows`. Constructor: `Flows()`.

| Member | Returns | Behaviour |
| --- | --- | --- |
| `verses` | [`Flowverses`](#flowverses) | Property. |
| `all()` | `list[Offer]` | Every runnable flow, in offer order. |
| `find(named: str)` | `str` | The resolved file of a flow, or `""` where nothing resolves. A path starts with `.`, `/` or `~`; anything else is a name, never a file of that name in the working directory. |
| `about(named: str)` | `str` | The flow's one-line description, or `""`. |
| `declared(named: str \| PathLike)` | [`Declaration`](#declaration) | A `str` as `-f` reads it; a `PathLike` always a path, `./`'d where it is relative. Imports the flow. Raises the flow API's `FlowException` for a flow that cannot load. |
| `resumes(named: str \| PathLike)` | `bool` | Whether it is [resumable](/reference/flows#a-flow-that-can-be-picked-up). Imports the flow. |
| `fork(named: str, into: str \| PathLike \| None = None)` | `str` | Copies the flow, what it imports and its skills into `./.hmz/flows/` (or `into`), as **Copy here** does in `/flow`; not an installed flow's `.installed.json`. Returns the directory. `ValueError`: not a flow, or already a copy here. `OSError`: cannot copy. |
| `running()` | `tuple[LiveCall, ...]` | Every flow call in progress in this process, oldest first. |

```python
for offer in Hmz().flows.all():
    print(offer.name, "·", offer.about)
```

## `Flowverses` {#flowverses}

`Hmz().verses`: the store [`/flow`'s Flowverses page](/reference/tui#where-flows-come-from)
edits. `flow` arguments are the name a flow is offered under: `<flow>` or `<user>/<flow>` for
`official`'s, `@<flowverse>/<flow>` or `@<flowverse>/<user>/<flow>` for another's. `index()`
takes a flowverse's bare name, and its methods a flow by index name (`<flow>`,
`<user>/<flow>`). Semantics: [Flows › Flowverses](/reference/flows#flowverses).

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
| `holds(one: Flowverse)` | `list[Offer]` | What it offers to run: installed flows for `official` and for another, the directory's for `local` and `user`. **Imports every flow in it.** Never a flow its index only lists. |
| `edited(one: Flowverse)` | `bool` | Whether the clone holds changes a fetch would discard. `False` for a non-clone. |
| `standing(one: Flowverse)` | `str` | The clone's commit, or `""`. |
| `where(name: str)` | `Path` | Its index's directory, fetched or not. |
| `plain(url: str)` | `str` | `url` with credentials removed. |
| `whence(one: Flowverse, nowhere: str = "-")` | `str` | Displayable origin: the credential-free URL; `your own flows in .hmz/flows` for `local`, `your own flows in ~/.hmz/flows` for `user`; `nowhere` for a directory with no readable origin. |

```python
from hmz.sdk import Hmz

verses = Hmz().verses
verses.fetch("official")
for release in verses.index("official").versions("flame_chasoid"):
    print(release.version, release.commit[:12])
verses.install("flame_chasoid")
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
| `ways(cli: str)` | `tuple[Way, ...]` | How the backend can be signed into, in offer order (for `claude`: `login`, `console`, `token`, `key`, `wif`, `anthropic-gateway`, `bedrock-gateway`, `vertex-gateway`, `bedrock`, `bedrock-key`, `mantle`, `vertex`, `foundry`, `aws`, `google-cloud`, `env`). |
| `way(cli: str, name: str)` | `Way \| None` | |
| `asks(way: Way, given: Mapping[str, str])` | `list[str]` | Variables still unanswered. |
| `make(cli, name, way: Way, answers=None)` | `Provider` | Writes an account from a way's answers; makes its directory. `ValueError`: bad backend or name. `OSError`. |
| `sign_in(provider, way, answers=None)` | `int` | **Runs** the backend's sign-in command under the account's paths; its exit status. |
| `write(cli, name, way="", env=None, args=())` | `Provider` | Writes an account as given, replacing `env`/`args`, keeping credentials. With `args` empty, a named `way` that adds arguments (codex's `openai-gateway`) has them filled from `env`. `ValueError`, `OSError`. |
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
| `new(backend, name, **fields)` | `Runtime` | Builds and validates one; saves nothing. `ValueError`: unknown field or bad value. `new(**p.held())` equals `p`. `harness="docker:gpubox"` (default `"env"`; also `"local"`) sets where the harness of work on it runs ([Remote execution › The harness setting](/reference/remote-execution#harness-setting)). |
| `add(runtime)` | `Runtime` | Saves a new one. `ValueError`: name taken. `OSError`. |
| `write(runtime)` | `Runtime` | Saves, replacing any of that name. `OSError`. |
| `remove(backend, name)` | `bool` | `ValueError`: bad backend or name. |
| `hosts(config: str \| PathLike \| None = None)` | `list[SSHHost]` | Every `Host` in an ssh config (default `~/.ssh/config`), as `ssh -G` resolves it. `OSError`: no `ssh`, unreadable config. |
| `import_ssh(config=None, names=None, *, update=False)` | `list[SSHRuntime]` | Saves one ssh runtime per `Host` (or per name in `names`), named after it; existing ones kept unless `update`. `ValueError`: a name not in the config. |
| `resolve(runtime: SSHRuntime)` | `SSHHost` | What `ssh -G` makes of it; reaches nothing. |
| `check(runtime, seconds: float = 30.0)` | `Checked` | **Reaches** it: an ssh host for home, CPUs, memory, GPUs; a docker daemon via `docker info`. Never raises. |

## `NousBook` {#nousbook}

`Hmz().nous`: every [nous](/user/settings#nous), concrete (`<cli>[@<account>]/<model>[:<effort>]`)
or virtual (a name standing for a graph). Each has `tries`, `policy`, `timeout` and a `then`
graph; a virtual one also has its `graph`. Values are `Nous(name, tries, policy, timeout, graph,
then)`, `Graph(start, nodes)` and `Node(id, use, balance, among, spread, on)` from
`hmz.coganchor.nous`.

| Member | Returns | Behaviour |
| --- | --- | --- |
| `default` | `str` | Property: `"exponential-jitter"`. |
| `policies()` | `tuple[Policy, ...]` | `none`, `constant`, `linear`, `exponential`, `exponential-jitter`, `fibonacci`. |
| `named(policy: str)` | `Policy \| None` | |
| `strategies()` | `tuple[Strategy, ...]` | `shuffle`, `round-robin`, `least-busy`, `latency`, `usage`, `cost`, then those added. |
| `strategy(name, about, picks)` | `Strategy` | Adds one for this process: `picks(members: Sequence[Member]) -> str`, each `Member` holding `name`, `weight`, `busy`, `latency`, `tokens`, `price`, `cooling`. `ValueError` for a built-in name. |
| `faults()` | `tuple[str, ...]` | What an edge may be named after: every fault class, then `*`. |
| `spec(backend, model, provider="", effort="")` | `str` | `spec("codex", "gpt-5.6-sol", "work", "high")` → `"codex@work/gpt-5.6-sol:high"`. No effort is left off, but written `:auto` after a model whose own name ends in `:<word>`: `spec("opencode", "ollama/qwen3:latest")` → `"opencode/ollama/qwen3:latest:auto"`. |
| `reads(said: str)` | `str` | The canonical spelling of a concrete nous, a virtual one's name, or `""`. |
| `all()` | `list[Nous]` | Every nous, in the order written. |
| `rule(said)` | `Nous` | What is written under `said`, else under `said` without its effort, else an empty `Nous`. |
| `graph(said)` | `Graph \| None` | Reads a nous, a list of nous, or `{start, nodes}` (`nodes` a mapping by id or a list of nodes with `id`). `TypeError` for anything else. |
| `shown(graph)` | `dict \| None` | The graph as `nous.list` carries it. |
| `write(name, *, tries=0, policy="", timeout=0.0, graph=None, then=None)` | `Nous` | Writes a nous whole; `graph` and `then` in any shape `graph()` reads. `ValueError`, `TypeError`. |
| `put(nous: Nous)` | `Nous` | The same, from a `Nous`. |
| `check(nous, among=None)` | `Nous` | What `put` would write beside `among` (default: every nous written), writing nothing. `ValueError` as `put`. |
| `checked(name, graph)` | `Graph` | The same for one graph of the nous `name`. |
| `then(said, to)` | `Nous` | Sets `then`: a `Graph`, a list of nous (a single string is one), or `None`. `ValueError`. |
| `retrying(said, tries, policy, timeout)` | `Nous` | Sets extra tries (`0` none), the wait policy, and the limit in seconds (`0` none). `ValueError`. |
| `renamed(said, name)` | `Nous` | Renames a virtual nous, in every graph naming it too. `ValueError`. |
| `entry(said)` | `str` | The concrete nous a walk of `said` starts at: where an agent at a virtual nous is built. |
| `clear(said)` | `bool` | Removes the nous. `ValueError` for a virtual one another nous names. |

## `Epics` {#epics}

`Hmz().epics`, or `Epics(workspace=None)`. A run is named by its epic directory.

| Method | Returns | Behaviour |
| --- | --- | --- |
| `under()` | `Path` | This workspace's epics directory. |
| `all()` | `list[Path]` | Every epic, oldest first. |
| `read(epic: Path)` | `Ran \| None` | `None` for a directory holding no run. |
| `sessions(epic)` | `list[Session]` | Every session, across every record of the epic. |
| `opened(epic)` | `dict[str, list[str]]` | Session ids per agent, by its name. |
| `resumed(flow: str)` | `Path \| None` | The epic `--resume` would pick up. `flow`: canonical ref or name as run. |
| `picks_up(epic)` | `bool` | Whether its journal has an entry, it is not going, and it is not `foreign`. |
| `foreign(epic)` | `str` | Why an imported run cannot be picked up here (its workspace is not at that path, or lacks the commit its bundle recorded), or `""`. |
| `state(epic, flow: str = "")` | `dict[str, Any]` | A resumable flow's kept `ctx.state`: the run's own flow, or another by canonical ref. |
| `traced(epic, *, output=None, start=None, end=None)` | `tuple[Path, dict]` | Gathers the run's own sessions into a Chrome trace. Default `output`: the epic's `traces/`, named for the moment. `start`/`end`: any wording `dateparser` reads. [Tracing](/reference/tracing#from-python). |
| `trace(*, sessions=None, agents=None, output=None, start=None, end=None, profile=None, flow_profile=None, kept=None)` | `dict` | The same collector for any sessions. `sessions=None`: every session of the workspace; empty iterable: none. `kept`: directories of kept sessions to read (default: everywhere Humanize keeps them). |
| `transcripts(epic)` | `list[dict]` | What each session of the run said and did, read back out of its logs: per session that did anything, `key` (`<cli>:<id>`), `agent` and `actions` -- each `category`, `name`, `at`, `start`, `seconds` and `args` -- in order. Writes nothing. |
| `timeline(epic)` | `Timeline` | The run as an [Exomyth timeline](/reference/tracing#timeline): `.document`, and `.span(id)` for one span whole. Writes nothing. |
| `bundled(epic, *, output, transcript=None)` | `tuple[Path, dict]` | One `.hmzepic` of the whole run, credentials struck out. `output` (required): a file, or a directory to put it in. Returns the path and its manifest. [Exporting a run](/user/export). |
| `imported(archive)` | `Path` | Reads a `.hmzepic` back in as an epic of the workspace it ran in, wherever that is. `ValueError` for anything else, an unsafe member, or an epic already here. [Importing a run](/user/export#importing-a-run). |

## `Client` {#client}

```python
class Client:
    @classmethod
    def local(cls, *, name: str = "", kind: str = "sdk") -> Client
    def call(self, method: str, params: Mapping[str, Any] | None = None, *,
             idem: str | None = None, seconds: float | None = None) -> Any
    def heard(self, listener: Callable[[str, dict[str, Any]], None]) -> None
    def close(self) -> None
    def __enter__(self) -> Self
    def __exit__(self, *exc) -> None      # close()
    daemon_id: str
    version: str
    protocol: str
    capabilities: tuple[str, ...]
    device: str
```

One session of the [wire protocol](/reference/daemon) with one daemon, for a program that
wants the methods themselves. What [`Run`](#run) follows its epic with.

| Member | Behaviour |
| --- | --- |
| `local(name="", kind="sdk")` | A session with this machine's daemon over its unix socket, the daemon started where none runs. `OSError`: it cannot be reached or started, or speaks another protocol. |
| `call(method, params=None, *, idem=None, seconds=None)` | Makes one call (a method `protocol/openrpc.json` lists) and waits for its result. `idem`, where given, is added to `params` as the write's idempotency key. Raises [`Refused`](#refused) with the error's message, `code` and `data`, or with code 503 (`the daemon went away`) once the session has ended; `TimeoutError("no answer to '<method>' in <s>s")`, the call then cancelled. |
| `heard(listener)` | Hands every notification, those already waiting first, to `listener(method, params)` on a thread of the client's own, in order; what it raises is let go. `RuntimeError` if a listener is already set. |
| `close()` | Ends the session and every subscription of it; every epic goes on. Idempotent. |
| `daemon_id`, `version`, `protocol`, `capabilities`, `device` | What `session.hello` answered. |

```python
from hmz.sdk import Client

with Client.local(name="ci") as client:
    print(client.call("hosts.list"))
```

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
| `host(workspace=None)` | `hmz.daemon.host` | The host of the workspace, started where none is -- and this machine's daemon with it (10 s each to come up). `OSError`: an older Humanize's daemon is running, or none came up. |

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
    protocol: str = ""  # the protocol version the daemon speaks ("3.0.0"); "" = an older Humanize's
    slot: str = ""      # which of the workspace's hosts: "" for its own, chat:<hex> for a chat's
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
              params: Any = None, budget: Any = None, profile_flow: bool = False,
              profile_environment: bool = False, resume: bool | str | os.PathLike[str] = False,
              backup: Iterable[str] | None = None) -> dict[str, Any]
    def say(self, text: str, *, to: str = "") -> dict[str, Any]
    def answer(self, question: str, text: str | None = None,
               value: Any = None) -> dict[str, Any]
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

One frontend of a workspace's host, over this machine's daemon. Obtained from
[`Daemon.link`](#daemon).

| Member | Behaviour |
| --- | --- |
| `client` | This frontend's client id; `owner` and `client` fields in messages use it. |
| `told(message)` | Called by the transport to deliver a message. Not for callers. |
| `heard(listener)` | Delivers every message, already-queued ones first, to `listener` on a thread of the link's own, in order. `RuntimeError` if a listener is already set. |
| `__iter__` | Yields every message in order until `gone` or `close()`. `RuntimeError` if a listener is set. |
| `asked(said, *, seconds=None)` | Sends one [request](/reference/daemon#requests) and waits (`seconds=None`: indefinitely). Returns the reply (`ok: true`). Raises [`Refused`](#refused) with the reply's `why`, or `TimeoutError("no answer to '<do>' in <s>s")`. |
| `start(…)` | `start` request. `agents`/`envs`: specs as `-a`/`-e` after `<role>=`. `params`, `budget`: mappings or models (serialised). `profile_flow`, `profile_environment`: whether the run's flow, and the programs its agents start, are [profiled](/reference/tracing#profiling-a-run). `backup`: the names of the backup targets the epic goes to; `None`: the settings' defaults. Reply carries `run`. |
| `answer(question, text=None, value=None)` | The [`answer`](/reference/daemon#answering) request, with exactly one of `text` or `value`: the line typed, or a JSON value for a question with a `schema`. A value that does not fit raises `Refused` with code 400, its `data["errors"]` the reasons. |
| `say`, `stop`, `force`, `afk`, `claim`, `release`, `board`, `aside` | The request of the same name. |
| `close()` | Lets go of the host; runs continue. |

Every method that sends a request goes through `asked` and raises `Refused` when refused,
including after the host has gone (the reason is then the [`gone`](/reference/daemon#gone)
reason). `Link` has no helpers for the `unaside`, `status`, `detach` and `quit` requests: send
them with `asked({"do": …})`. Transport behaviour is in [Daemon › Link](/reference/daemon#link).

```python
from hmz.sdk import Daemons

with (Daemons().here() or Daemons().host()).link(name="ci", replay=False) as link:
    link.claim("reviewer")
    for said in link:
        if said["type"] == "pending":
            for asked in said["pending"]:
                if asked["owner"] != link.client:
                    continue
                if asked["schema"] is None:
                    link.answer(asked["question"], "looks good")
                else:
                    link.answer(asked["question"], value={"verdict": "approve"})
```

## `fakes` {#fakes}

`hmz.sdk.faking`: the drivers of `hmz.runtime.flowing.fakes`, handed through, and `run_fake`. `__all__`:

| Name | Is |
| --- | --- |
| `run_fake(flow, task="", *, agents=None, envs=None, params=None, budget=None, outworlder=None, local=None, journal=None, resume=False)` | Runs a flow on fakes through a private daemon; returns or raises the very object the flow returned or raised, and raises the flow API's `RequirementError` or `ParamsError`, not `Refused`, for a run refused before the flow is called. |
| `FakeAgentDriver(harness=HarnessKind.CLAUDE, *, reply=None, model="fake", effort="", provider="", capabilities=None, cost=0.0, output_tokens=1, seconds=0.0, forks=None, names_late=False)` | A scripted agent driver. Also accepted by `Hmz.run(agents=…)`, which then runs the epic on a private daemon. |
| `FakeSession` | A session of a `FakeAgentDriver`. |
| `FakeEnvDriver(files=None, *, workdir="/work", backend=EnvBackendKind.LOCAL, provider="", capabilities=None, cpu_count=8, memory=64 GiB, gpu_count=0, gpu_memory=0, run=None, refs=("HEAD", "main"), repo=True)` | An in-memory environment. |
| `FakeOutworlder(reply=None, *, away=False)` | An outworlder answering from a script. |
| `Answer`, `Command`, `Handler`, `Reply` | Type aliases for the scripts above. |

Driver objects cannot be handed to another process, so an epic given any (`run_fake`, or
`Hmz.run` with a driver for a role) is held by a **private daemon** the calling program starts
in its own process, reached over a socket pair. Its hosts run in that process too, so a fake's
`prompts` and the rest are filled in; each driver is named to it as `fake:<key>`. It has a
temporary home and machine directory of its own (with a copy of the settings file; private
daemons going at once in one process share them, as the environment that names them is the
process's), never
touches this machine's daemon, and is torn down when `run_fake` returns or raises, or the
[`Run`](#run) has ended -- the epic written in its home with it, so `Hmz().epics` never lists a
run on fakes. The home and machine directory are named by the process's environment, so private
daemons running at once in one process (say, `asyncio.gather` over two `run_fake`) share them,
and they are removed when the last of those is torn down.

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
| `profile_flow` | `bool` | `False` | `--profile-flow` |
| `profile_environment` | `bool` | `False` | `--profile-environment` |
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
| `Offer` | `whose: str` (a flowverse, `local` or `user`), `name: str` (what `-f` takes: `aot`, `alice/kernel`, `@theirs/review`, `@local/x`), `about: str` |
| <span id="declaration"></span>`Declaration` | `name`, `ref`, `description: str \| None`, `hidden: bool`, `resumable: bool`, `agents: tuple[AgentRole, ...]`, `envs: tuple[EnvRole, ...]`, `params: type[FlowParams]`; methods `agent(name)`, `env(name)` → role or `None` |
| `AgentRole` | `name`, `declared: type`, `required: bool`, `auto: bool` (runtime-filled), `harness: HarnessKind \| None`, `capabilities: frozenset[type]`, `permission`, `skills: tuple[str, ...]`, `grant` |
| `EnvRole` | `name`, `declared: type`, `required`, `auto`, `capabilities`, `cpu_count: int`, `memory: int`, `gpu_count: int`, `gpu_memory: int`, `image: str`, `grant`, `resources: bool` |
| `LiveCall` | `ref`, `name`, `depth: int` (1 = the run's flow), `since: float` (monotonic), `id: int` (journal id, 0 = none), `parent: LiveCall \| None`, `task: str`, `resumable: bool` |
| `Flowverse` | `name`, `url` (`""` for `local`, `user`), `at: Path`, `fetched: bool`, `fixed: bool` (`official`, `local`, `user`) |

### Flowverse types {#flowverse-types}

`hmz.runtime.flowing.index`; all but `Skipped` are also exported from `hmz.runtime.flowing`.

| Type | Fields |
| --- | --- |
| `Index` (named tuple) | `verse: str`, `releases: tuple[Release, ...]` (by index name, newest first), `skipped: tuple[Skipped, ...]`; methods `flows()` (index names, `aot` and `alice/kernel`, sorted), `versions(flow)` (newest first), `release(flow, version)` → `Release \| None`, `newest(flow, spec="")` → the newest in range that is not a prerelease, else the newest prerelease, else `None` |
| `Release` (pydantic, frozen) | `name`, `version`, `description`, `repo`, `ref`, `commit`, `subdir`, `license`, `dependencies: dict[str, str]`, `owner` (the `<user>` it is listed under, `""` bare); properties `listed` (its index name), `owned` (its repository's GitHub owner, or `""`), `semver` (a `semver.Version`), `url` (what git fetches) |
| `Skipped` (named tuple) | `at: Path` (the manifest, or a `<user>` directory), `why: str` |
| `Installed` (pydantic, frozen) | `verse`, `name`, `version`, `commit`, `repo`, `ref`, `subdir`, `dependencies`, `owner`; properties `listed` (its index name), `called` (the name it is offered under), `at: Path` (its directory) |
| `Update` (named tuple) | `installed: Installed`, `version: str` (the newest after it) |

### Account types {#account-types}

| Type | Fields |
| --- | --- |
| `Provider` | `cli`, `name`, `way: str = "env"`, `env: Mapping[str, str]`, `args: tuple[str, ...]`, `made: str`; property `at: Path`; methods `held()`, `command(argv)`, `swaps()` |
| `Way` | `name`, `about`, `argv: tuple[str, ...]` (sign-in command), `asks: tuple[Asked, ...]`, `sets: tuple[tuple[str, str], ...]`, `args: tuple[str, ...]`, `stdin: str` |
| `Model` | `name`, `efforts: tuple[str, ...]` (hardest first), `swarms: bool = False` |
| `Policy` | `name`, `about` |

### Environment types {#environment-types}

| Type | Fields |
| --- | --- |
| `SSHRuntime` | `name`, `host`, `user`, `port: int = 0`, `identity_file`, `proxy_jump`, `options: Mapping[str, str]`, `alias`, `config`, `workdir`, `made: str = "typed"` (`typed`/`imported`); property `at`; methods `destination()`, `login()`, `settings()`, `target()` (coganchor target), `held()`; `backend == "ssh"` |
| `DockerRuntime` | `name`, `endpoint: str = "local"`, `tls_dir`, `container`, `exec_user`, `exec_env: tuple[str, ...]`, `exec_wrapper: tuple[str, ...]`, `image`, `runtime`, `run_args: tuple[str, ...]`, `name_prefix`, `cpus: float`, `memory: int` (bytes), `gpus: tuple[str, ...]`, `gpu_memory: int`, `max_containers: int` (0 = no limit), `workdir`, `made`; property `at`; methods `daemon()` → `Endpoint` ([Machines](/reference/machines#a-docker-daemon)), `exec_options()`, `held()`; `backend == "docker"` |
| `SSHHost` | `alias`, `host`, `user`, `port: int`, `identity_files: tuple[str, ...]`, `proxy_jump` |
| `Checked` | `reached: bool`, `said: str`, `home: str`, `cpus: float`, `memory: int`, `gpus: tuple[str, ...]`, `gpu_memory: int`, `runtimes: tuple[str, ...]`, `version: str`, `short: tuple[str, ...]` (what it is saved to hand out and has not got) |

### Epic types {#epic-types}

`hmz.runtime.epic`, named tuples. Values as the [epic record](/reference/tracing#epics) wrote
them.

| Type | Fields |
| --- | --- |
| `Ran` | `at: Path`, `flow`, `task`, `workspace`, `began`, `ended` (`""` while running or abandoned), `how` (`done`, `failed`, `stopped`, or `""`), `agents: tuple[Drove, ...]`, `sessions: tuple[Session, ...]`, `called: tuple[Called, ...]`, `resumable: bool`, `ref`, `envs: tuple[str, ...]` (as `-e` spells them, a run's kept in an older spelling included), `params: dict`, `budget: dict \| None`, `picked_up: str` (epic name or `""`), `profile_flow: bool`, `profile_environment: bool` (whether its flow, and the programs its agents started, were [profiled](/reference/tracing#profiling-a-run)); property `name` |
| `Drove` | `agent` (the role), `backend`, `model`, `effort` (`""` = auto), `provider` (`""` = as local), `name` (what the agent filling it is called; `""` in an epic written before agents had names); property `spec` (`-a` spelling after `<role>=`) |
| `Called` | `flow`, `task`, `record` (file in the epic), `began`, `ended`, `how`, `calls: tuple[Called, ...]` |
| `Session` | `agent`, `backend`, `provider` (`local` = as local), `ident` (backend's id), `name`, `at`, `flow`, `parent` (forked-from id or `""`), `record`, `where` (kept-session path), `harness` (`local`, `env`, the `<backend>:<name>` of a runtime a harness setting named, or `""` for work on this machine) |

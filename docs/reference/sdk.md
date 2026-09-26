# SDK

`hmz.sdk` is how a program that is not humanize drives humanize. It offers two ways into a
run: [`Hmz`](#hmz) runs one in your own process, and [`Daemons`](#daemons) holds one in a
process of its own, where a terminal closing cannot end it.

::: code-group

```python [run it here]
from hmz.sdk import Hmz

run = Hmz().run(
    "ralph_loop",
    "fix the build",
    agents={"agent": "claude/claude-opus-5:high"},
    budget={"cost": 5},
)
run.run()                        # returns when the flow does
```

```python [on a thread]
from hmz.sdk import Hmz

run = Hmz().run("ralph_loop", "fix the build",
                agents={"agent": "claude/claude-opus-5:high"}, budget={"cost": 5})
run.start()                      # returns at once
...
print(run.usage)                 # what it has spent so far
run.stop()                       # interrupts the turn under way, and unwinds
run.wait()
```

```python [held by a daemon]
import asyncio

from hmz.sdk import Daemons, Hmz


def opens(held):
    # Runs in the held process, and returns when the run is over.
    run = Hmz().run("ralph_loop", "fix the build",
                    agents={"agent": "claude/claude-opus-5:high"}, budget={"cost": 5})
    held.stopping(run.stop)      # what Daemon.stop() from outside does
    try:
        run.run()
    except asyncio.CancelledError:
        pass                     # stopped from outside, as meant


daemon = Daemons().hold(opens)   # returns once the daemon is listening
print(daemon.status())
daemon.stop()
```

:::

`Hmz().run(...)` is what `hmz exec` calls with a command line. A run refused before it starts
raises [`Refused`](#refused), with the message `hmz exec` prints.

## Every name

All of these import from `hmz.sdk`.

| Name | Is |
| --- | --- |
| [`Hmz`](#hmz) | One workspace, and everything humanize can do in it. |
| [`Run`](#run) | One run of one flow: start it, watch it, stop it. |
| [`Refused`](#refused) | A run refused before anything of it ran. |
| [`Flows`](#flows), [`Flowverses`](#flowverses) | The flows there are, and where they come from: `Hmz.flows` and `Hmz.verses`. |
| [`Accounts`](#accounts), [`Fallbacks`](#fallbacks) | The accounts an agent runs as, and where a turn goes when its place cannot take it: `Hmz.accounts` and `Hmz.fallbacks`. |
| [`Epics`](#epics) | The runs of a workspace that already happened: `Hmz.epics`. |
| [`Daemons`](#daemons), [`Daemon`](#session), [`Held`](#session), [`Session`](#session) | Runs held apart from any terminal. |
| [`fakes`](#fakes) | The in-memory kit a flow is tested on, as a module. |

::: tip Stable and internal
Import these from `hmz.sdk`. Each is fetched from the layer it is written in, only when it is
named: `Hmz`, `Run` and the objects `Hmz` hands out from `hmz.runtime`, and `Daemon`, `Held`
and `Session` from `hmz.daemon`. Those modules, and the types the methods below return
(`Offer`, `Declaration`, `Line`, `Provider` and the rest), are **internal**. Their fields are
listed here as they are today.

`fakes` is offered as a module: `from hmz.sdk import fakes`. `import hmz.sdk.fakes` and
`from hmz.sdk.fakes import …` raise `ModuleNotFoundError`.
:::

## `Hmz` {#hmz}

```python
class Hmz:
    def __init__(self, workspace: str | os.PathLike[str] | None = None) -> None: ...
```

| Parameter | |
| --- | --- |
| `workspace` | The project directory, or `None` for the current directory. Kept as given, `~` unexpanded: one nobody named follows a flow that changes directory. |

Nothing is loaded until it is asked for.

| Property | |
| --- | --- |
| `workspace: Path` | The project directory. |
| `home: Path` | Where humanize keeps what outlives a run: `~/.humanize`, or `$HUMANIZE_HOME`. |
| `settings` | What humanize remembers about this workspace and everywhere, as the internal `hmz.runtime.settings.Settings`. See [TUI](/reference/tui). |
| `flows` | [`Flows`](#flows): the flows there are. |
| `verses` | [`Flowverses`](#flowverses): where flows come from. The same object as `flows.verses`. |
| `accounts` | [`Accounts`](#accounts). |
| `fallbacks` | [`Fallbacks`](#fallbacks). |
| `epics` | [`Epics`](#epics) of this workspace. |

| Method | |
| --- | --- |
| [`run(flow, task, *, …)`](#hmz-run) | A [`Run`](#run) of a flow, checked and ready to start. |
| [`runner(flow, *, …)`](#hmz-runner) | The flow loaded and checked, with its drivers, and no task. |
| [`read(argv)`](#hmz-read) | An `hmz exec` line, read. |
| [`exec(argv)`](#hmz-exec) | The whole of `hmz exec`: read the line, run the flow, return what it returned. |
| `backends()` | Every coding agent CLI humanize drives, installed or not, as internal `Profile`s: `[p.name for p in Hmz().backends()]` is `['claude', 'agy', 'codex', …]`. |
| `reports()` | Starts [reporting humanize's own failures](/user/reporting), where that has been answered yes. Returns whether anything is being reported. |

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
    resume: bool | str | os.PathLike[str] = False,
    outworlder: OutworlderDriver | None = None,
) -> Run
```

| Parameter | |
| --- | --- |
| `flow` | The flow: the name it is listed under, a path, or a [ref](/reference/flows#refs). |
| `task` | What it is to do. |
| `agents` | By role: an `-a` spec without the `<role>=` (`"claude@work/claude-opus-5:high"`), or a driver such as a [`fakes.FakeAgentDriver`](/reference/flows#fakeagentdriver). Or `Line.agents`. |
| `envs` | By role: an `-e` spec without the `<role>=` (`"ssh@gpu-box/home/me/repo"`), or a driver. Or `Line.envs`. |
| `params` | A mapping (strings as `-p` gives them are read as the field's type) or an instance of the flow's `FlowParams`. `None` for its defaults. |
| `budget` | A [`Budget`](/reference/flows#budget), or a mapping validated into one: `{"cost": 5}`, `{"duration": 3600}` or `{"duration": "PT1H"}`. Unlike `-b`, a mapping does not read `"1h"`. Required for every flow but `chat`. |
| `resume` | `True` for the newest run of this flow here that can be picked up, or the epic directory to pick up. |
| `outworlder` | Who fills the flow's `Outworlder` roles, such as a [`fakes.FakeOutworlder`](/reference/flows#fakeoutworlder). `None` for nobody: always away, as under `hmz exec`. |

Returns a [`Run`](#run). Nothing has started.

Raises [`Refused`](#refused) for everything that can be checked without reaching an agent or a
machine: a flow that is not there; a role it does not declare, one the runtime fills, or one
given twice; a required role left out; a harness that is not the one a role names, or does not
serve what it asks; a spec no driver can be made for, such as an effort off the harness's
ladder; params the flow does not take; no budget; a run to pick up that is not there.

```python
from hmz.sdk import Hmz, Refused

try:
    Hmz().run("goal", "fix the build", agents={"worker": "pi/gpt-5.5:high"}, budget={"cost": 5})
except Refused as why:
    print(why)   # goal: 'worker' needs GoalCommandAgentMixin, which pi does not do
```

### `Hmz.runner` {#hmz-runner}

```python
def runner(self, flow, *, agents=(), envs=(), params=None, budget=None, resume=False) -> Runner
```

The same parameters and refusals as [`run`](#hmz-run), without the task: the flow loaded,
a driver opened for every role and everything checked, as the internal
`hmz.runtime.runner.Runner`. Opening a driver starts no CLI and reaches no machine. `run` is
`Run(self.runner(…), task, outworlder=…)`.

### `Hmz.read` {#hmz-read}

```python
def read(self, argv: list[str]) -> Line
```

Reads an `hmz exec` line, without loading the flow. A line argparse will not accept, or an
`-a`, `-e`, `-p` or `-b` that cannot be read, raises `SystemExit`.

| `Line` field | |
| --- | --- |
| `flow: str` | The flow, as the line named it. |
| `task: str` | What it is to do. |
| `agents`, `envs` | The `-a` and `-e` specs, in the order written. |
| `params: dict[str, str]` | Each `-p`, as written. |
| `budget: Budget \| None` | The `-b`, read, or `None`. |
| `resume: bool` | `--resume`. |
| `as_json: bool` | `--json`. |

```python
hmz = Hmz()
line = hmz.read(["-f", "ralph_loop", "-a", "agent=claude/claude-opus-5:high",
                 "-b", "duration=6h,cost=50", "fix the build"])
run = hmz.run(line.flow, line.task, agents=line.agents, envs=line.envs,
              params=line.params, budget=line.budget, resume=line.resume)
```

### `Hmz.exec` {#hmz-exec}

```python
def exec(self, argv: list[str]) -> Any
```

`read(argv)`, then `run(…)`, then `Run.run()`: runs the flow the line names to its return,
and returns what it returned. Raises `SystemExit` for a line that cannot be read, `Refused`
for one that was wrong before anything ran, and whatever the flow raised.

```python
Hmz().exec(["-f", "chat", "-a", "assistant=claude/claude-opus-5:high", "say hello"])
```

## `Run` {#run}

```python
class Run:
    def __init__(self, runner: Runner, task: str, *,
                 outworlder: OutworlderDriver | None = None) -> None: ...
```

One run of one flow. Made by [`Hmz.run`](#hmz-run). Making one starts nothing: `run()` runs it
here and `start()` on a thread.

| Property | |
| --- | --- |
| `flow: str` | The flow, as it was named. |
| `ref: str` | Its canonical ref: `rlar:rlar`, `humanize1:rlcr`. |
| `task: str` | What it was asked to do. |
| `declaration` | What the flow declares, as a [`Declaration`](#declaration). |
| `budget: Budget` | What the run may spend. |
| `usage: Usage` | What every session of the run has spent so far. |
| `agents` | The internal coganchor agent behind each session still open, oldest first. Empty for fake drivers. |
| `epic: Path \| None` | The [epic](/reference/tracing#epics) the run is written into, once it has started. |
| `running: bool` | Whether a run started on a thread is still going. |
| `raised: BaseException \| None` | What the flow raised, for a run started on a thread and over. `asyncio.CancelledError` after `stop()`. |
| `result: Any` | What the flow returned, likewise. |

| Method | |
| --- | --- |
| `run() -> Any` | Runs the flow here until it returns, and returns what it returned or raises what it raised. From a thread already running an event loop, it runs on a thread of its own and waits. Raises `Refused` if an environment cannot be reached, before the flow is called. |
| `start() -> None` | Runs it on a thread of its own and returns at once. `RuntimeError` if it has already been started. |
| `wait(timeout: float \| None = None) -> bool` | Waits for it to end. Returns whether it has. |
| `stop() -> None` | Interrupts the turn under way and unwinds the flow: every call raises where it stands, and every session and temporary directory is closed or removed, in its own time. From any thread. |
| `close() -> None` | `stop()`, and then interrupts every session and stops every agent at once, without waiting for the flow to unwind. The flow still sees `CancelledError`. |
| `unreadable() -> str` | Which cap of the budget nothing the run drives can read, in words, or `""`: a cost cap over a model nobody prices. `hmz exec` prints it before the run. |
| `watch(listener) -> None` | Has everything every session says reach `listener(agent, conversation, event)`, from whichever thread a CLI is read on. |
| `opened(callback) -> None` | Has each session told to `callback(role, agent, conversation)` as it opens, before its first turn. |

`agent`, `conversation` and `event` are coganchor's own objects. See
[Agents](/reference/agents).

## `Refused` {#refused}

```python
class Refused(ValueError): ...
```

A run refused before anything of it ran: a line or a setup to correct. Its message says what,
in the words `hmz exec: error:` prints, and its `__cause__` is the exception it was refused
for, where there was one.

## `Flows` {#flows}

`Hmz().flows`: the flows there are to run. [Flows](/reference/flows) is what a flow is.

| Method | |
| --- | --- |
| `all() -> list[Offer]` | Every flow there is to run, in the order they are offered. |
| `find(named: str) -> str` | The file a flow is written in, resolved. `named` itself where nothing answers to it, so whether a flow is there is whether what comes back is a file. |
| `about(named: str) -> str` | The line a flow says about itself, or `""`. |
| `declared(named) -> Declaration` | Everything it declares. Raises the flow API's own [exception](/reference/flows#when-something-goes-wrong) for a flow that cannot be loaded. |
| `resumes(named) -> bool` | Whether it [can be picked up](/reference/flows#a-flow-that-can-be-picked-up). |
| `fork(named: str, into=None) -> str` | Copies it into this project's `.humanize/flows/`, or `into`, whole. Returns the directory. `ValueError` for a flow that is not there, or a copy you already have. |
| `running() -> tuple[LiveCall, ...]` | Every flow call going in this process, oldest first. |
| `verses` | [`Flowverses`](#flowverses). |

`declared` and `resumes` import the flow, which runs its module.

| `Offer` field | |
| --- | --- |
| `whose` | Where it came from: a flowverse's name, or `local` or `user`. |
| `name` | What `-f` takes: `rlar`, `local/twice`, `humanize1:gen-plan`. |
| `about` | Its line, or `""`. |

<span id="declaration"></span>

| `Declaration` field | |
| --- | --- |
| `name`, `ref` | Its name in its module, and its canonical ref. |
| `description`, `hidden`, `resumable` | As [`@flow`](/reference/flows#flow) set them. |
| `agents`, `envs` | Its roles, in declaration order. Each has `name`, `required`, `auto` (filled by the runtime) and `capabilities` (the mixins). An agent role also has `harness` (or `None`), `permission` and `skills`; an environment role `cpu_count`, `memory`, `gpu_count` and `gpu_memory`. |
| `params` | Its `FlowParams` subclass. |
| `agent(name)`, `env(name)` | One role by name, or `None`. |

| `LiveCall` field | |
| --- | --- |
| `ref`, `name` | The flow's canonical ref, and its name in its module. |
| `depth` | How many flows deep: `1` for the flow the run started with. |
| `parent` | The call that made it, or `None`. |
| `task`, `resumable`, `since`, `id` | What it was called to do, whether it can be picked up, when it started on the monotonic clock, and its id in the run's journal (`0` for none). |

```python
from hmz.sdk import Hmz

flows = Hmz().flows
for offer in flows.all():
    print(offer.name, "·", offer.about)
print([role.name for role in flows.declared("rlar").agents])   # ['actor', 'reviewer']
```

## `Flowverses` {#flowverses}

`Hmz().verses`: where flows come from, the same store [`/flowverses`](/reference/tui) walks.

| Method | |
| --- | --- |
| `all() -> list[Flowverse]` | Every place, in the order their flows are offered: `official`, the ones you added (alphabetically), `local`, `user`. |
| `nearest() -> list[Flowverse]` | The same, in the order a name is looked up in: `local`, `user`, `official`, the ones you added. |
| `find(name) -> Flowverse \| None` | The one of that name. |
| `add(url, name="") -> Flowverse` | Fetches one (a URL, a path, or `owner/repo` on GitHub) and lists its flows under `name`, the repository's own by default. `ValueError` for a name taken or reserved; `OSError` if it cannot be cloned. |
| `fetch(name) -> Flowverse` | Fetches one again, or for the first time. |
| `remove(name) -> bool` | Takes one away, flows and all. Returns whether there was one. |
| `holds(one) -> list[Offer]` | What it holds. **Imports every flow in it.** |
| `edited(one) -> bool` | Whether its clone holds changes a fetch would undo. |
| `standing(one) -> str` | The commit its clone stands at, or `""` for one that is not a clone. |
| `where(name) -> Path` | The directory it is kept in, fetched or not. |
| `plain(url) -> str` | The URL with any credentials taken out. |
| `whence(one, nowhere="-") -> str` | Where it came from, fit to show: the URL without credentials, `your own flows in .humanize/flows` for `local`, or `nowhere`. |

`fetch` and `remove` refuse `local` and `user`, and `remove` refuses `official`, with
`ValueError`.

| `Flowverse` field | |
| --- | --- |
| `name` | What it is called, and what its flows are listed under. |
| `url` | Where it is fetched from, or `""` for `local` and `user`. |
| `at` | The directory it is kept in. |
| `fetched` | Whether it has been cloned. `official` is `False` until first fetched. |
| `fixed` | Whether it is always there: `official`, `local`, `user`. |

```python
verses = Hmz().verses
theirs = verses.add("acme/flows", name="acme")
print([offer.name for offer in verses.holds(theirs)])   # ['acme/review', …]
```

## `Accounts` {#accounts}

`Hmz().accounts`: [the accounts an agent may run as](/reference/providers), and what each
backend runs as one. `cli` is a backend by any name it answers to; an account `name` of `""`
is the one this machine is already signed into.

| Method | |
| --- | --- |
| `all(cli="") -> list[Provider]` | Every account made, or one backend's. |
| `find(cli, name) -> Provider \| None` | One account. |
| `ways(cli) -> tuple[Way, ...]` | How a backend can be signed into: for `claude`, `login`, `token`, `key`, `gateway`, `bedrock`, `vertex`, `env`. |
| `way(cli, name) -> Way \| None` | One of them. |
| `asks(way, given) -> list[str]` | What a way in still needs to be told. |
| `make(cli, name, way, answers=None) -> Provider` | Writes an account down from the answers to its way in. |
| `sign_in(provider, way, answers=None) -> int` | **Runs** the backend's own sign-in, under this account's paths. Returns its exit status. |
| `write(cli, name, way="", env=None, args=()) -> Provider` | Writes an account down as it stands, running nothing. Its chain and retries are kept. |
| `where(cli, name) -> Path` | Where it keeps its credentials, made or not. |
| `local(cli) -> Path` | Where the account this machine is signed into keeps its own. |
| `serves(one) -> tuple[str, ...]` | The other backends its credentials could run. |
| `copies(one, cli, name="") -> Provider` | Writes the same account down for another backend. |
| `chain(one) -> list[Provider]` | Every account a failing turn would carry on under, this one first. |
| `points(cli, name, at) -> bool` | Sets which account a turn under `name` carries on under, `""` for none. |
| `remove(cli, name) -> bool` | Takes one away, credentials and all. |
| `env(said) -> dict[str, str]` | Reads `NAME=VALUE` lines. |
| `environ(provider) -> dict[str, str]` | What a turn under this account is run with. |
| `models(cli, provider="") -> tuple[Model, ...]` | What the backend last said it runs as this account, each with its efforts. Empty if never asked. |
| `asked(cli, provider="") -> str` | When it was last asked, or `""`. |
| `ask(cli, provider="", seconds=None) -> tuple[Model, ...]` | **Starts the backend** to find out, and keeps the answer. |

`Provider` has `cli`, `name`, `way`, `env`, `args`, `made`, `fallback` and `at`, the directory
its credentials are kept in.

```python
accounts = Hmz().accounts
print([one.name for one in accounts.all("claude")])
print(accounts.env("ANTHROPIC_BASE_URL=https://gateway.example\nTIMEOUT=60"))
```

## `Fallbacks` {#fallbacks}

`Hmz().fallbacks`: [where a turn goes](/user/fallback) when the place taking it cannot take it
at all. A place is written `CLI[@ACCOUNT]/MODEL`.

| Member | |
| --- | --- |
| `default: str` | The wait a failed turn is retried with unless set: `exponential-jitter`. |
| `policies() -> tuple[Policy, ...]` | The waits there are: `none`, `constant`, `linear`, `exponential`, `exponential-jitter`, `fibonacci`. |
| `named(policy) -> Policy \| None` | One of them. |
| `spec(backend, model, provider="") -> str` | A place, spelled: `spec("codex", "gpt-5.6-sol", "work")` is `codex@work/gpt-5.6-sol`. |
| `reads(said) -> str` | A place as it is written down, or `""` for a spelling no place answers to. |
| `all() -> list[Falls]` | Every step written down. |
| `tried(said) -> Falls` | What is written against one place. |
| `chain(said) -> list[str]` | The places one turn would walk, starting at `said`. |
| `points(said, at) -> Falls` | Sets where `said`'s turns go when it cannot run. `ValueError` for a place that is not one, or a step to itself. |
| `retrying(said, tries, policy, timeout) -> Falls` | Sets how many more tries a failed turn gets at `said` first, the wait between them, and the longest they may take in seconds (`0` for no limit). |
| `clear(said) -> bool` | Takes a step away. |

`Falls` has `spec`, `to` (`""` for nowhere), `tries`, `policy` and `timeout`.

```python
fallbacks = Hmz().fallbacks
here = fallbacks.spec("claude", "claude-opus-5")
fallbacks.points(here, fallbacks.spec("codex", "gpt-5.6-sol", "work"))
fallbacks.retrying(here, 3, "exponential", 600)
print(fallbacks.chain(here))   # ['claude/claude-opus-5', 'codex@work/gpt-5.6-sol']
```

## `Epics` {#epics}

`Hmz().epics`: [the runs of this workspace](/reference/tracing#epics) that already happened. A
run is named by its directory, an `epic: Path`.

| Method | |
| --- | --- |
| `under() -> Path` | The directory this workspace's runs are kept in. |
| `all() -> list[Path]` | Every run, oldest first. |
| `read(epic) -> Ran \| None` | What one run was, or `None` for a directory holding no run. |
| `sessions(epic) -> list[Session]` | Every session it opened, in every flow it called. |
| `opened(epic) -> dict[str, list[str]]` | The session ids each agent role opened: `{"builder": ["0a1b…"]}`. |
| `resumed(flow) -> Path \| None` | The newest run of a flow here that can be picked up: what `--resume` picks up. |
| `picks_up(epic) -> bool` | Whether a run can be picked up from it. |
| `state(epic, flow="") -> dict[str, Any]` | What a resumable flow kept in its `ctx.state`: the run's own flow, or another by canonical ref. |
| [`traced(epic, *, output=None, start=None, end=None)`](/reference/tracing#from-python) | Gathers one run into a [trace](/reference/tracing). Returns where it went and the document. |
| [`trace(*, sessions=None, agents=None, output=None, start=None, end=None, profile=None)`](/reference/tracing#from-python) | The same collector, for any sessions you name. Returns the document. |
| `bundled(epic, *, output=None, transcript=None)` | Packs one whole run into one archive, credentials struck out. Returns where it went and its manifest. See [Exporting a run](/user/export). |

`Ran` has `at`, `name`, `flow`, `ref`, `task`, `workspace`, `began`, `ended`, `how` (`done`,
`failed` or `stopped`), `agents`, `envs`, `params`, `budget`, `sessions`, `called`, `resumable`
and `picked_up`, as the [epic's own record](/reference/tracing#epics) says them.

```python
runs = Hmz().epics
last = runs.all()[-1]
ran = runs.read(last)
print(ran.flow, ran.how, [agent.spec for agent in ran.agents])
where, document = runs.traced(last)
```

## `Daemons` {#daemons}

`Daemons()`: every run being held apart from a terminal, one per workspace. See
[Daemon](/reference/daemon) for what holding one means.

| Method | |
| --- | --- |
| `here(workspace=None) -> Daemon \| None` | The run held in one workspace, or `None`. |
| `all() -> list[Daemon]` | Every run held on this machine, oldest first. |
| `hold(opens, workspace=None, *, columns=0, rows=0) -> Daemon` | Starts a daemon and returns once it is listening. `opens(held)` is called in the held process with a [`Held`](#session), and returns when the run is over. `columns` and `rows` are the terminal size it draws for until one attaches; `0` for this terminal's. `OSError` if it could not start, or a run is already held there. |

The third tab at the [top of the page](#sdk) is `hold` holding a flow.

## `Daemon`, `Held` and `Session` {#session}

A **`Daemon`** is one held run, as a tool outside reaches it.

| Member | |
| --- | --- |
| `at`, `workspace`, `pid`, `started` | Its directory, its project, the process holding it, and when it started, in UTC. |
| `alive` | Whether that process is still there. |
| `status() -> dict` | What it says about itself: `pid`, `workspace`, `started`, `attached` (terminals reading it), `flows` and `calls` running. |
| `attach() -> int` | Reads it from this terminal until it ends or lets go. |
| `detach() -> int` | Lets go of every terminal reading it. Returns how many. |
| `stop(*, seconds=20.0) -> bool` | Asks the run to stop, as closing the interface does, and waits. Returns whether it has gone. The run only stops if its `opens` hung a `stopping` hook. |
| `kill(*, seconds=20.0) -> bool` | Ends the process, whatever it was doing. |

A **`Held`** is what `opens` is handed: a `Session`, plus the hooks the held process registers.

| Member | |
| --- | --- |
| `attached: int`, `detach() -> int` | As `Session`. |
| `redrawn(hook)` | What to call when a terminal arrives, which is to draw the screen again. |
| `stopping(hook)` | What to call when somebody asks the run to stop from outside. |
| `says(hook)` | What to add to `status()`. |

A **`Session`** is the `Protocol` whatever is drawing a held run sees: `attached`, how many
terminals are reading it, and `detach()`. An interface of your own that is handed one knows it
is held; one handed none is running in the terminal it was typed in.

## `fakes` {#fakes}

```python
from hmz.sdk import fakes
```

The in-memory kit a flow is tested on: `fakes.run_fake`, `fakes.FakeAgentDriver`,
`fakes.FakeSession`, `fakes.FakeEnvDriver` and `fakes.FakeOutworlder`. The drivers also stand
in for real ones in [`Hmz.run`](#hmz-run), which then writes a real epic of a run no agent
took. Every signature is in [Testing a flow](/reference/flows#testing-a-flow).

```python
run = Hmz().run("twice", "fix the build",
                agents={"builder": fakes.FakeAgentDriver(reply="done")}, budget={"cost": 5})
run.run()
print(run.epic)
```

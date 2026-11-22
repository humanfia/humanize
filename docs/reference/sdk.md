---
title: SDK
description: Look up every public name of hmz.sdk, with its signature, what it returns and what it raises.
---

# SDK

Import `hmz.sdk` to drive Humanize from Python. The module exports fifteen names. A daemon runs every epic you start, so epics outlive the calling process.

```python
from hmz.sdk import Hmz, Run, Ask, Refused, Client, Daemons, fakes
```

![Three ways in: Hmz.run gives a Run, Daemons gives a Link, Client gives a session; each goes through this machine's daemon to the workspace host that runs the epic](/diagrams/reference-sdk-1.svg)

For a walkthrough, read [The Python SDK](/builder/sdk) or [Drive Humanize from Python](/tutorials/drive-from-python).

## Exported names

| Name | Kind | What it is |
| --- | --- | --- |
| `Hmz` | class | One workspace and everything you can do in it. |
| `Run` | class | One epic held by a daemon and followed. |
| `Ask` | frozen dataclass | One question put to an `Outworlder` role. |
| `Refused` | exception | A run or request refused before anything ran. |
| `Flows` | class | Available flows. `Hmz().flows`. |
| `Flowverses` | class | Flow sources and installed flows. `Hmz().verses`. |
| `Accounts` | class | Accounts that agents run as. `Hmz().accounts`. |
| `Runtimes` | class | Saved runtimes. `Hmz().runtimes`. |
| `NousBook` | class | Every nous. `Hmz().nous`. |
| `Epics` | class | Past and running epics in a workspace. `Hmz().epics`. |
| `Client` | class | One session with one daemon. |
| `Daemons` | class | Hosts holding runs on this machine. |
| `Daemon` | frozen dataclass | One host of one workspace. |
| `Link` | class | One frontend attached to a host. |
| `fakes` | module | In-memory drivers and `run_fake`. |

Module rules:

- `import hmz.sdk` loads nothing else. Each name is imported from its layer on first access.
- Every name is the underlying layer object, not a wrapper. `hmz.sdk.Hmz` subclasses `hmz.runtime.Hmz`.
- Unknown names raise `AttributeError`.
- `fakes` is an attribute: `from hmz.sdk import fakes` works, while `import hmz.sdk.fakes` raises `ModuleNotFoundError`.
- Unlisted return types are internal. See [Returned types](#returned-types) for their fields.

## Hmz {#hmz}

```python
class Hmz:
    def __init__(self, workspace: str | os.PathLike[str] | None = None) -> None
```

`workspace` is the project directory. `None` uses the current directory, re-read on each access. The constructor loads nothing.

| Property | Type | Value |
| --- | --- | --- |
| `workspace` | `Path` | The project directory. |
| `home` | `Path` | `$HUMANIZE_HOME`, else `~/.hmz`. Not created. |
| `settings` | `Settings` | Saved settings for this workspace and machine. Internal type; see [settings.yaml](/reference/settings) for keys. |
| `flows` | `Flows` | [Flows](#flows). |
| `verses` | `Flowverses` | [Flowverses](#flowverses). Same object as `flows.verses`. |
| `accounts` | `Accounts` | [Accounts](#accounts). |
| `runtimes` | `Runtimes` | [Runtimes](#runtimes). |
| `nous` | `NousBook` | [NousBook](#nousbook). |
| `epics` | `Epics` | [Epics](#epics) of this workspace. |
| `backups` | `Backups` | [Backup targets](#backups). Internal type. |
| `daemons` | `hmz.runtime` `Daemons` | Recorded remote daemons: `all()`, `find(name)`, `write(name, fields, replace=False)`, `remove(name)`, `offered()`, `imported(wanted)`, `remotes(version=None, *, install=False)`. Where an SSH machine has no hmz, `install=False` installs nothing and the daemon is `failed` with `hmz is not installed on <name>.`, `True` installs it unasked, and `None` leaves the daemon `asking` until `answer(name, install)` on the returned object answers it. Internal type, distinct from the exported [`Daemons`](#daemons). |

`workspace` and `home` are computed on each access. The remaining properties are created on first access and cached.

| Method | Returns | What it does |
| --- | --- | --- |
| `run(flow, task, *, ...)` | `Run` | Has the daemon check an epic without starting it. See [Hmz.run](#hmz-run). |
| `runner(flow, *, ...)` | `Runner` | Runs the same check without `task` and `outworlder`. Returns the internal `Runner` with `workspace`, `started` (arguments to `epic.start`) and `checked` (response from `flows.check`). |
| `read(argv)` | `Line` | Parses an `hmz exec` argument list (without `exec`). Loads no flow. Raises `SystemExit(2)` if argparse rejects the line or an `-a`, `-e` or `-p` value cannot be read. |
| `exec(argv)` | what the flow returned | Calls `read(argv)`, `run(...)`, then `Run.run()`. Draws nothing and installs no signal handlers. |
| `backends()` | tuple of `Profile` | Every coding agent CLI Humanize drives, installed or not. |
| `installed()` | dict of name to tuple of `Model` | Installed backends mapped to their last reported models: an empty tuple for a backend never queried. |
| `installable()` | dict of name to tuple of `Model` | Optional backends with an installed binary but missing Python extra. |
| `adding(backend)` | `str` | What is missing for an optional backend and the command to add it. |
| `serves(backend, role)` | `bool` | Whether a backend can fill an agent role in a flow declaration. `role=None` checks a flowless agent. |
| `ready_to_open(backend)` | `bool` | Whether an installed backend can be auto-selected here. |
| `carried(pages)` | list of `(method, params)` | Daemon calls that copy this machine's settings to another daemon. `pages` are among `general`, `nous`, `runtimes`, `backup`. |
| `reports()` | `bool` | Starts error reporting if previously enabled. Returns whether reporting is active. Never prompts. |

### Hmz.run {#hmz-run}

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

This machine's daemon holds the epic, starting first if needed. If you pass a driver object to any role, an in-process private daemon holds the epic instead; see [fakes](#fakes).

| Parameter | Accepts |
| --- | --- |
| `flow` | A name as `-f` takes it, a path, or a ref. |
| `task` | The task text. |
| `agents` | Mapping of role to an `-a` spec without `<role>=` (such as `"claude/claude-haiku-4-5:low"`) or to a driver object, or the `AgentSpec` tuple of a `Line`. |
| `envs` | Mapping of role to `-e` specs or environment drivers, or an `EnvSpec` iterable. |
| `params` | Mapping or instance of the flow's `FlowParams`. `None` uses the defaults. |
| `budget` | `Budget` or valid mapping: `{"cost": 5}`, `{"output_tokens": 20000}`, `{"duration": 3600}`, `{"duration": "PT1H"}`. `"1h"` is rejected. `None` is refused because every epic requires a budget. |
| `profile_flow` | Sample the flow's Python code while running, like `--profile-flow`. |
| `profile_environment` | Profile programs started by agents, like `--profile-environment`. |
| `resume` | `False` starts fresh. `True` resumes the newest resumable epic of this flow here. A path resumes that specific epic. |
| `outworlder` | [Driver](#ask) that answers `Outworlder` roles. `None` marks all such roles away, as in `hmz exec`. |
| `backup` | Backup target names for the epic. Empty means none. `None` uses the settings defaults. |

Raises `OSError` if the daemon is unreachable. Raises `Refused` with the same message as `hmz exec` for pre-start refusals, plus:

| Condition | Message |
| --- | --- |
| A role given twice | `<flow>: duplicate agent role '<role>'` |
| A budget mapping that does not validate | `the budget is invalid: <why>` |
| No budget | `<flow> requires a budget: ...` |

```python
from hmz.sdk import Hmz

run = Hmz().run(
    "goal",
    "add a discount code to checkout",
    agents={"worker": "claude/claude-haiku-4-5"},
    budget={"output_tokens": 20000},
)
print(run.run())
```

## Run {#run}

```python
class Run:
    def __init__(self, runner: Runner, task: str, *,
                 outworlder: OutworlderDriver | None = None) -> None
```

Returned by `Hmz.run`. The constructor starts nothing. Once started, a new exec slot in the workspace holds the epic while the run's own `Client` follows it.

| Property | Type | Value |
| --- | --- | --- |
| `flow` | `str` | The flow name as given. |
| `ref` | `str` | Canonical ref, such as `goal:goal`. |
| `task` | `str` | The task. |
| `declaration` | `dict` | Flow declaration from the daemon's check. |
| `budget` | `Budget` | Allowed spend for the epic. |
| `profile_flow`, `profile_environment` | `bool` | Profiling switches. |
| `backup` | tuple of `str` | Backup targets for the epic. |
| `usage` | `Usage` | Spend so far (`duration`, `cost`, `output_tokens`). Live during the run. |
| `agents` | tuple of `Opened` | Open sessions, oldest first. |
| `names` | `dict` | Agent name filling each role, keyed by role. |
| `epic` | `Path` or `None` | Epic directory once assigned by the daemon. |
| `running` | `bool` | True from `start()` until the epic ends. |
| `raised` | exception or `None` | Exception set when the epic ends. See the endings table below. |
| `result` | any | JSON return value of the flow once ended. |

| Method | Returns | What it does |
| --- | --- | --- |
| `run()` | the result | Calls `start()`, then `wait()`. Returns `result` or raises `raised`. |
| `start()` | `None` | Attaches to a new exec slot, marks `Outworlder` roles away or claims them for the driver, and starts the epic. Returns once the daemon has loaded the flow and accepted the start, without waiting for the epic. Raises `Refused` if refused, `OSError` if the daemon is unreachable, `RuntimeError` if already started. |
| `wait(timeout=None)` | `bool` | Blocks until the epic ends or `timeout` seconds pass. Returns whether it ended. |
| `stop()` | `None` | Requests a stop without waiting for the epic to unwind. Thread-safe. |
| `close()` | `None` | Calls `stop()`, forces the epic if still running, and disconnects from the daemon. |
| `unreadable()` | `str` | The budget limits that nothing the epic drives can enforce, in words, else `""`. |
| `watch(listener)` | `None` | Calls `listener(agent, session, record)` for every session event. See [Events and records](/reference/events) for `record`. |
| `opened(callback)` | `None` | Calls `callback(role, opened)` when each session opens, before its events. |
| `noticed(callback)` | `None` | Calls `callback(text)` for each epic notice. |
| `printed(callback)` | `None` | Calls `callback(text)` for each line printed by the host during the epic. |

Register callbacks before `start()`. They run on a background thread.

How the epic ends determines `raised`:

| Ending | `raised` |
| --- | --- |
| Done | `None` |
| Stopped | `asyncio.CancelledError` |
| Budget spent | `hmz.flows.BudgetExceeded` |
| Refused by the host | `Refused`, code 409 |
| Failed | `RuntimeError` with the reason |
| The daemon was lost | `RuntimeError("the daemon went away")` |

Behavior notes:

- If the session drops before the epic ends, the run reconnects and resumes following.
- After the epic ends, the run stays attached for up to 60 seconds while queued backups finish.
- Flows given by `git+` ref are checked only after fetch, when the epic starts. For such a run `declaration` stays `{}` and `unreadable()` stays `""`, and `ref` is `""` until the epic starts.
- On a private daemon, `result` and `raised` are the exact Python objects the flow returned or raised.

## Ask and the outworlder driver {#ask}

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Ask:
    prompt: str
    schema: dict[str, Any] | None
    model: type[pydantic.BaseModel] | None = None
    context: tuple[dict[str, Any], ...] = ()
    face: str = ""
    session: str = ""
    errors: tuple[dict[str, Any], ...] = ()


class OutworlderDriver(Protocol):
    def away_for(self, role: str) -> bool: ...
    async def run(self, ask: Ask, role: str) -> str | pydantic.BaseModel | Mapping[str, Any]: ...
```

Pass any object with these two methods as `outworlder=` to `Hmz.run`. It receives questions just like a human frontend. The protocol class itself is not exported.

| `Ask` field | Value |
| --- | --- |
| `prompt` | The question text. |
| `schema` | JSON Schema for the answer, or `None` for plain text. |
| `model` | Always `None` in the SDK (only the schema is available). |
| `context` | Context blocks shown before the prompt, as JSON. |
| `face` | Face hash of the session, or `""`. |
| `session` | `<role>/<n>`, shared across all questions in one outworlder session. |
| `errors` | Empty on the first attempt. On retry, lists validation failures as `{"path": [...], "message": ...}`. |

| Member | What it does |
| --- | --- |
| `away_for(role)` | Returns whether the role is away. Away roles are not asked. |
| `run(ask, role)` | Returns the answer: a `str` for text questions, or a mapping or Pydantic model for schema questions. Returning `""` or raising treats the role as away for this question. |
| `show(context, session, role)` | Optional. Receives context pushed to the role. Return value is ignored. |

Answers that fail schema validation are refused and `run` is retried with `errors` populated, up to three total attempts. After three failures, the question resolves as if the role were away.

```python
from typing import Any

from hmz.sdk import Ask


class Approver:
    def away_for(self, role: str) -> bool:
        return False

    async def run(self, ask: Ask, role: str) -> str | dict[str, Any]:
        if ask.schema is None:
            return "looks good"
        return {"action": "ship", "notes": ""}
```

For the flow side, see [The person as an agent](/builder/outworlder).

## Refused {#refused}

```python
class Refused(ValueError):
    def __init__(self, message: str, *, code: int = 0, data: dict[str, Any] | None = None) -> None
    code: int
    data: dict[str, Any]
```

Raised when a run or a daemon/host request is refused before execution. `str(error)` matches the `hmz exec` message. `code` is 0 for a refusal made in this process, else the daemon's error code: 400 for a request that is wrong (such as a missing budget), 409 for host refusals, 503 after a `Client` session ends, and -32601 for an unknown method. `data` holds any extra error fields, or `{}`.

## Flows {#flows}

Access via `Hmz().flows` or `Flows(workspace=None)`.

| Member | Returns | What it does |
| --- | --- | --- |
| `verses` | `Flowverses` | Property. |
| `all()` | list of `Offer` | Every runnable flow, named as `-f` takes it. |
| `find(named)` | `str` | Path to the flow's file, or `""`. Values starting with `.`, `/` or `~` are treated as paths; all others as names. |
| `about(named)` | `str` | One-line description, or `""`. |
| `declared(named)` | `Declaration` | Imports the flow and returns its roles, params, and marks. Raises the flow API's `FlowException` on load failure. |
| `resumes(named)` | `bool` | Imports the flow and returns whether it is resumable. |
| `fork(named, into=None)` | `str` | Copies a flow and its local imports into the project's flows directory or `into`. Returns the directory path. Raises `ValueError` if not a flow or already present, `OSError` on copy failure. |
| `running()` | tuple of `LiveCall` | Active flow calls in this process, oldest first. |

```python
from hmz.sdk import Hmz

for offer in Hmz().flows.all():
    print(offer.name, "·", offer.about)
```

## Flowverses {#flowverses}

Access via `Hmz().verses`. Pass flow names as offered: `<flow>` or `<user>/<flow>` for `official`, or `@<flowverse>/<flow>` for others.

| Method | Returns | What it does |
| --- | --- | --- |
| `all()` | list of `Flowverse` | Listed in offer order: `official`, added flowverses alphabetically, `local`, `user`. |
| `nearest()` | list of `Flowverse` | Listed in name lookup order: `local`, `user`, then the rest. |
| `find(name)` | `Flowverse` or `None` | Flowverse with that name. |
| `add(url, name="")` | `Flowverse` | Clones the index from a URL, path, or GitHub `owner/repo` without installing flows. Raises `ValueError` for taken, reserved, or invalid names; `OSError` if cloning fails. |
| `fetch(name)` | `Flowverse` | Fetches or updates the index. Raises `ValueError` for unknown or unfetchable flowverses; `OSError` if git fails. |
| `remove(name)` | `bool` | Deletes the index and all flows installed from it. Raises `ValueError` for `official`, `local`, `user`. |
| `index(name)` | `Index` | Releases from the last fetched index, or empty if unfetched. |
| `install(flow, version="")` | list of `Installed` | Installs a release and its dependencies, or switches version if already installed. `""` selects the newest non-prerelease. The requested flow is last in the returned list. Raises `ValueError` for missing flows/releases, dependency cycles, or conflicts; `OSError` on fetch or copy failure. |
| `uninstall(flow)` | `bool` | Removes an installed flow. Raises `ValueError` if another installed flow depends on it. |
| `installed()` | list of `Installed` | Installed flows and their releases. |
| `updates()` | list of `Update` | Installed flows with a newer release in the index. |
| `holds(one)` | list of `Offer` | Imports every flow in the flowverse and returns what it offers. |
| `edited(one)` | `bool` | Whether the clone has local changes that a fetch would overwrite. |
| `standing(one)` | `str` | Current commit hash of the clone, or `""`. |
| `where(name)` | `Path` | Directory path of the flowverse, fetched or not. |
| `plain(url)` | `str` | URL with credentials stripped. |
| `whence(one, nowhere="-")` | `str` | Sanitized source URL or path, safe to display. |

## Accounts {#accounts}

Access via `Hmz().accounts`. `cli` accepts any backend name or alias. The account name `""` refers to the machine's default login.

| Member | Returns | What it does |
| --- | --- | --- |
| `all(cli="")` | list of `Provider` | All accounts, or those for one backend. |
| `find(cli, name)` | `Provider` or `None` | Looks up one account. |
| `ways(cli)` | tuple of `Way` | Sign-in methods for the backend, in offer order. |
| `way(cli, name)` | `Way` or `None` | Looks up one sign-in method. |
| `asks(way, given)` | list of `str` | Variables still required by `way`. |
| `make(cli, name, way, answers=None)` | `Provider` | Creates an account from `way` answers. Raises `ValueError` for invalid backend or name, or `OSError`. |
| `sign_in(provider, way, answers=None)` | `int` | Runs the backend's sign-in command using the account's paths and returns its exit code. |
| `write(cli, name, way="", env=None, args=())` | `Provider` | Overwrites an account's configuration while keeping its credentials. Runs nothing. |
| `where(cli, name)` | `Path` | Credentials directory. Raises `ValueError` for unknown backend or invalid name. |
| `serves(one)` | tuple of `str` | Other backends compatible with this account's credentials. |
| `copies(one, cli, name="")` | `Provider` | Copies the account to another compatible backend. Raises `ValueError` if incompatible. |
| `remove(cli, name)` | `bool` | Deletes an account and its credentials. Raises `ValueError` for `""`. |
| `env(said)` | `dict` | Parses `NAME=VALUE` lines. |
| `environ(provider)` | `dict` | Environment variables for a turn under this account, or `{}` for `None`. |
| `models(cli, provider="")` | tuple of `Model` | Models last reported for this account, or empty if never queried. |
| `asked(cli, provider="")` | `str` | Timestamp of the last model query, or `""`. |
| `stale(cli, provider="")` | `bool` | True if never queried or queried over seven days ago. |
| `ask(cli, provider="", seconds=None)` | tuple of `Model` | Queries the backend for available models and caches the result. |
| `wants(cli)` | `str` | Command that installs the LiteLLM extra for a backend that would gain sign-in ways from it, else `""`. |
| `GATEWAY` | `str` | `"LiteLLM"`. |

See [Agents and harnesses](/reference/agents) for each CLI's sign-in methods.

## Runtimes {#runtimes}

Access via `Hmz().runtimes`. `backend` is `ssh`, `docker`, `swarm`, `apple-container`, or `slurm`. See [Environments and runtimes](/reference/environments) for runtime fields.

| Method | Returns | What it does |
| --- | --- | --- |
| `kinds()` | list of `str` | Environment backends as spelled in `-e`, with `local` first. |
| `all(backend="")` | list of `Runtime` | Saved runtimes, sorted by backend then name. |
| `find(backend, name)` | `Runtime` or `None` | Looks up one runtime. |
| `saved(backend, name)` | `bool` | Whether a runtime with that name exists. Raises `ValueError` for invalid backend or name. |
| `new(backend, name, **fields)` | `Runtime` | Validates and constructs a runtime without saving. Raises `ValueError` for unknown fields or invalid values. |
| `add(runtime)` | `Runtime` | Saves a new runtime. Raises `ValueError` if the name is taken. |
| `write(runtime)` | `Runtime` | Saves a runtime, overwriting any existing entry with the same name. |
| `remove(backend, name)` | `bool` | Deletes a runtime and returns whether it existed. |
| `hosts(config=None)` | list of `SSHHost` | Hosts resolved from an SSH config via `ssh -G`. Raises `OSError` if `ssh` is missing or the config is unreadable. |
| `import_ssh(config=None, names=None, *, update=False)` | list of `SSHRuntime` | Saves an SSH runtime for each host, skipping existing ones unless `update` is true. Raises `ValueError` if a requested name is not in the config. |
| `resolve(runtime)` | `SSHHost` | Resolves an SSH runtime locally via `ssh` without connecting. |
| `check(runtime, seconds=30.0)` | `Checked` | Connects to the runtime and probes its resources. Never raises. |

## NousBook {#nousbook}

Access via `Hmz().nous`. A nous is either concrete (`<cli>[@<account>]/<model>[:<effort>]`) or virtual (a named graph). See [Nous: models, retries and fallback](/user/nous).

| Member | Returns | What it does |
| --- | --- | --- |
| `default` | `str` | Property. Default wait policy: `"exponential-jitter"`. |
| `policies()` | tuple of `Policy` | `none`, `constant`, `linear`, `exponential`, `exponential-jitter`, `fibonacci`. |
| `named(policy)` | `Policy` or `None` | Looks up one policy. |
| `strategies()` | tuple of `Strategy` | `shuffle`, `round-robin`, `least-busy`, `latency`, `usage`, `cost`, plus any custom strategies. |
| `strategy(name, about, picks)` | `Strategy` | Registers a custom strategy for this process. `picks` takes the members and returns a name. Raises `ValueError` if `name` is built-in. |
| `faults()` | tuple of `str` | Valid edge names: every fault class, then `*`. |
| `spec(backend, model, provider="", effort="")` | `str` | Formats a spec: `spec("codex", "gpt-5.6-sol", "work", "high")` returns `"codex@work/gpt-5.6-sol:high"`. |
| `reads(said)` | `str` | Canonical spelling of a nous, or `""`. |
| `all()` | list of `Nous` | Saved nous entries in order. |
| `rule(said)` | `Nous` | Entry for `said`, or an empty `Nous` if unset. |
| `graph(said)` | `Graph` or `None` | Parses a nous name, a list of nous to try in order, or a `start`/`nodes` mapping. Raises `TypeError` for other types. |
| `shown(graph)` | `dict` or `None` | Serializes a graph for daemon calls. |
| `write(name, *, tries=0, policy="", timeout=0.0, graph=None, then=None)` | `Nous` | Writes a complete nous entry. Raises `ValueError` or `TypeError` if invalid. |
| `put(nous)` | `Nous` | Writes a `Nous` instance. |
| `check(nous, among=None)` | `Nous` | Validates what `put` would write without saving. |
| `checked(name, graph)` | `Graph` | Validates a single graph without saving. |
| `then(said, to)` | `Nous` | Sets fallback after retries are exhausted: a graph, a list of nous, or `None`. |
| `retrying(said, tries, policy, timeout)` | `Nous` | Sets extra retries, wait policy, and timeout in seconds. |
| `renamed(said, name)` | `Nous` | Renames a virtual nous and updates all graphs referencing it. |
| `entry(said)` | `str` | First concrete nous reached when walking `said`. |
| `clear(said)` | `bool` | Removes a nous. Raises `ValueError` if another nous references it. |

## Epics {#epics}

Access via `Hmz().epics` or `Epics(workspace=None)`. Epics are identified by their directory path.

| Method | Returns | What it does |
| --- | --- | --- |
| `under()` | `Path` | Epics directory for this workspace. |
| `all()` | list of `Path` | Epics in this workspace, oldest first. |
| `every()` | list of `Path` | Epics across all workspaces on this machine. |
| `chats()` | list of `Path` | Chats in this workspace, oldest first. |
| `chat(said)` | `Path` or `None` | Looks up a chat by name. |
| `read(epic)` | `Ran` or `None` | Reads run metadata, or `None` if the directory holds no run. |
| `ending(ran)` | `str` | Outcome of the run, or `running` if still active. |
| `going(epic)` | `bool` | Whether the epic is currently running in any process. |
| `sessions(epic)` | list of `Session` | Sessions opened by the epic. |
| `opened(epic)` | `dict` | Session IDs grouped by agent name. |
| `tree(epic)` | tuple of `Called` | Call tree of flows invoked during the epic. |
| `resumed(flow)` | `Path` or `None` | Epic that `--resume` would select. |
| `picks_up(epic)` | `bool` | Whether the epic can be resumed. |
| `foreign(epic)` | `str` | Reason an imported run cannot be resumed here, or `""`. |
| `state(epic, flow="")` | `dict` | Saved state of a resumable flow. |
| `traced(epic, *, output=None, start=None, end=None)` | `(Path, dict)` | Writes a Chrome trace of the run (defaults to the epic's `traces/` directory). |
| `trace(*, sessions=None, agents=None, output=None, start=None, end=None, profile=None, flow_profile=None, kept=None)` | `dict` | Collects trace data for specific sessions, or all workspace sessions if `sessions=None`. |
| `transcripts(epic)` | list of `dict` | Transcripts for each session (`key`, `agent`, `actions`). Slow; writes nothing. |
| `timeline(epic)` | `Timeline` | Exomyth timeline (`document`, `details`, `span(id)`). Writes nothing. |
| `bundled(epic, *, output, transcript=None)` | `(Path, dict)` | Writes a `.hmzepic` archive with credentials redacted. Returns the archive path and manifest. |
| `imported(archive)` | `Path` | Imports a `.hmzepic` archive into its original workspace. Raises `ValueError` if invalid or already present. |

See [Trace formats](/reference/tracing) and [Export and import a run](/user/export).

### Backups {#backups}

Access via `Hmz().backups`. See [Back up to git](/user/backups).

| Method | Returns | What it does |
| --- | --- | --- |
| `targets()` | tuple of `Target` | Configured backup targets. |
| `defaults()` | tuple of `str` | Default target names for new epics. |
| `push(ran, names=None)` | tuple of `str` | Queues an epic backup and returns immediately. Raises `ValueError` for unknown targets. |
| `wait(seconds=None)` | `bool` | Waits for backups queued by this process to finish. |
| `state(ran)` | `dict` | Status of the last backup per target: `at`, `ok`, `error`, `why`. |
| `where(ran)` | `str` | Path in the target repository: `<machine>/<workspace>/<epic>`. |
| `listed(name)` | list of `Stored` | Fetches and lists all epics stored in a target. Blocks. |
| `pulled(name, key)` | `Path` | Downloads a stored epic into local storage. |

## Client {#client}

```python
class Client:
    @classmethod
    def local(cls, *, name: str = "", kind: str = "sdk") -> Client
    @classmethod
    def over(cls, pipe: Pipe, *, name: str = "", kind: str = "sdk") -> Self
    def call(self, method: str, params: Mapping[str, Any] | None = None, *,
             idem: str | None = None, seconds: float | None = None) -> Any
    def heard(self, listener: Callable[[str, dict[str, Any]], None]) -> None
    def wait(self, timeout: float | None = None) -> bool
    def close(self) -> None
    daemon_id: str
    version: str
    protocol: str
    capabilities: tuple[str, ...]
    device: str
```

Manages a direct RPC session with a daemon. A context manager. See [Daemon and wire](/reference/daemon) for available RPC methods.

| Member | What it does |
| --- | --- |
| `local(name="", kind="sdk")` | Connects to this machine's daemon over its Unix socket, starting it if needed. `kind` is `sdk`, `cli`, `tui`, or `ai-chan`. `ai-chan` connects over the scoped link named by [`HUMANIZE_AICHAN_LINK`](/reference/environment) instead and starts no daemon. Raises `OSError` if unreachable, unable to start, on a protocol mismatch, or, for `ai-chan`, if the variable names no link. |
| `over(pipe, name="", kind="sdk")` | Opens a session over an existing trusted pipe. |
| `call(method, params=None, *, idem=None, seconds=None)` | Calls an RPC method and returns the result. `idem` sets the idempotency key for writes. Raises `Refused` (with `code` and `data`) on error, or `TimeoutError` after `seconds`. |
| `heard(listener)` | Calls `listener(method, params)` in order on a background thread for each notification. Raises `RuntimeError` if already set. |
| `wait(timeout=None)` | Blocks until the session ends and returns whether it ended. |
| `close()` | Closes the session without stopping running epics. |
| `daemon_id`, `version`, `protocol`, `capabilities`, `device` | Handshake metadata from the daemon. |

```python
from hmz.sdk import Client

with Client.local(name="ci") as client:
    print(client.call("hosts.list"))
```

## Daemons {#daemons}

```python
class Daemons:
    def here(self, workspace: str | os.PathLike[str] | None = None) -> Daemon | None
    def all(self) -> list[Daemon]
    def host(self, workspace: str | os.PathLike[str] | None = None) -> Daemon
```

| Method | What it does |
| --- | --- |
| `here(workspace=None)` | Returns the host holding runs for `workspace`, or `None`. |
| `all()` | Lists all hosts on this machine, oldest first. |
| `host(workspace=None)` | Returns the host for `workspace`, starting both the daemon and host if needed. Raises `OSError` if held by an older Humanize version or if startup fails. |

`workspace=None` uses the current directory.

## Daemon {#daemon}

```python
@dataclass(frozen=True, slots=True)
class Daemon:
    at: Path            # this machine's daemon's directory
    workspace: str      # the project directory its host holds runs for
    pid: int            # the host process
    started: str        # UTC
    protocol: str = ""  # the protocol version the daemon speaks
    slot: str = ""      # "" for the workspace's own host, chat:<hex> for a chat's
```

| Member | Returns | What it does |
| --- | --- | --- |
| `alive` | `bool` | Property. Whether the host process is running. |
| `link(name="", kind="sdk", *, replay=True)` | `Link` | Attaches a frontend (`kind` is `tui`, `cli`, or `sdk`). `replay=False` skips past events. Raises `OSError` if unreachable or refused. |
| `status()` | `dict` | Host status, including attached frontends and active runs. |
| `detach()` | `int` | Detaches all frontends while leaving runs active. Returns the count detached. |
| `stop(*, seconds=20.0)` | `bool` | Stops active runs and waits for the host to exit. Returns whether it exited. |
| `kill(*, seconds=20.0)` | `bool` | Terminates the host process immediately without affecting the daemon or other hosts. |
| `asked(said)` | `dict` | Sends `hosts.<do>` (from `said["do"]`) to the daemon for this host. Returns `{}` if unanswered. |

## Link {#link}

A frontend connection to a host, returned by `Daemon.link`. A context manager. Request methods return the host's response `dict` or raise `Refused`.

| Member | What it does |
| --- | --- |
| `client` | Client ID for this frontend. |
| `heard(listener)` | Calls `listener(message)` on a background thread for each queued and incoming message. Raises `RuntimeError` if already set. |
| iteration | `for message in link` yields messages in order until disconnected or `close()` is called. Raises `RuntimeError` if a `heard` listener is set. |
| `asked(said, *, seconds=None)` | Sends a request `dict` containing `do` and waits for the reply. Raises `Refused` or `TimeoutError`. |
| `start(flow, task, *, agents=None, envs=None, params=None, budget=None, profile_flow=False, profile_environment=False, resume=False, backup=None)` | Starts a flow using string specs (same parameters as [Hmz.run](#hmz-run)). Response includes `run`. |
| `say(text, *, to="")` | Sends a message into the active turn on view `to`, or queues it for the next turn. |
| `answer(question, text=None, value=None)` | Answers a question by ID in text or as a schema value. Invalid values raise `Refused` (code 400, errors in `data["errors"]`). |
| `stop()` | Stops the active run. |
| `force()` | Force-closes all conversations in a stopping run. |
| `afk(*, on, role="")` | Sets away status for one `Outworlder` role, or for all roles. |
| `claim(role, *, take=False)` | Claims exclusive control of a role for this frontend. |
| `release(role)` | Releases a claimed role. |
| `board(key, value)` | Sets a key on the run's board, or deletes it if `value` is empty. |
| `aside(**said)` | Opens or continues a side conversation. |
| `chat(agent, task, *, resume=None, prefer=None, permission=None, remember=False, worktree=False, env="")` | Starts or resumes a chat on a chat host (`permission` is `read-only`, `workspace-write`, or `danger-full-access`). Response includes `slot` and `chat`. |
| `chat_say(text)` | Sends the next chat message or answer, or `""` to end the chat. |
| `chat_set(prefer=None, *, permission=None)` | Updates chat preference (`native` or `flow`) and/or permission. |
| `chat_move(env)` | Moves the chat to another environment between turns. |
| `chat_stop()` | Stops the current chat turn. |
| `chat_commands()` | Lists what a line of the chat can start with. |
| `close()` | Detaches from the host while leaving runs active. |
| `told(message)` | Internal transport hook. Do not call directly. |

Use `asked({"do": ...})` for any other host request. Incoming messages follow [Events and records](/reference/events).

```python
from hmz.sdk import Daemons

host = Daemons().here() or Daemons().host()
with host.link(name="ci") as link:
    link.start(
        "goal",
        "add a discount code to checkout",
        agents={"worker": "claude/claude-haiku-4-5"},
        budget={"output_tokens": 20000},
    )
    for message in link:
        if message["type"] == "ended":
            print(message["how"])
            break
```

## fakes {#fakes}

In-memory drivers for testing flows without real agents. See [Test a flow](/builder/testing).

```python
async def run_fake(
    flow: Flow | str,
    task: str = "",
    *,
    agents: Mapping[str, AgentDriver | OutworlderDriver | Reply] | None = None,
    envs: Mapping[str, EnvDriver | Mapping[str, bytes | str]] | None = None,
    params: FlowParams | Mapping[str, Any] | None = None,
    budget: Budget | None = None,
    outworlder: OutworlderDriver | None = None,
    local: EnvDriver | None = None,
    journal: Path | None = None,
    resume: bool = False,
) -> Any

FakeAgentDriver(harness=HarnessKind.CLAUDE, *, reply=None, model="fake", effort="",
                provider="", capabilities=None, cost=0.0, output_tokens=1, seconds=0.0,
                forks=None, names_late=False, name=None)

FakeEnvDriver(files=None, *, workdir="/work", backend=EnvBackendKind.LOCAL, provider="",
              capabilities=None, cpu_count=8, memory=64 * 2**30, gpu_count=0, gpu_memory=0,
              run=None, refs=("HEAD", "main"), repo=True)

FakeOutworlder(reply=None, *, away=False)
```

| Name | What it is |
| --- | --- |
| `run_fake` | Runs a flow with fake drivers and returns the exact Python object returned by the flow. Omitted roles default to a fake replying `ok`. Omitting `budget` means unlimited. Raises `RequirementError`, `ParamsError`, or whatever the flow raises. |
| `FakeAgentDriver` | Scripted agent. Records `sessions`, `prompts`, `live`, `peak`, `closed`. |
| `FakeSession` | Single session on a `FakeAgentDriver`: `prompts`, `requests`, `steered`, `tools`, `turns`, `placement`, `closed`. |
| `FakeEnvDriver` | In-memory working directory. Records `files`, `commands`, `machine`, `clones`, `scratches`, `closed`. |
| `FakeOutworlder` | Scripted or away human role. Records `asked`, `asks`, `shown`, `faces`. |
| `Reply`, `Answer`, `Command`, `Handler` | Type aliases for fake scripts. |

Driver objects cannot cross process boundaries. When you pass a driver to `run_fake` or `Hmz.run`, an in-process private daemon runs the epic in a temporary home directory without touching the machine's daemon. The temporary directory is deleted when the epic ends, so fake runs never appear in `Hmz().epics`.

In this example, `./once.py` is a flow file with one agent role, `worker`:

```python
import asyncio

from hmz.sdk import Hmz, fakes

print(asyncio.run(fakes.run_fake("./once.py", "say hi", agents={"worker": "hi"})))

worker = fakes.FakeAgentDriver(reply="done")
run = Hmz().run("./once.py", "say hi", agents={"worker": worker}, budget={"cost": 1})
print(run.run(), worker.prompts)
```

## Returned types {#returned-types}

Internal types returned by SDK methods, with fields listed in order. These types may change between releases.

| Type | Fields |
| --- | --- |
| `Line` | `flow`, `task`, `agents`, `envs`, `params`, `budget`, `profile_flow`, `profile_environment`, `resume`, `as_json`, `backup` |
| `AgentSpec` | `role`, `harness`, `provider`, `model`, `effort`, `cli`, `nous` |
| `EnvSpec` | `role`, `backend`, `provider`, `workdir` |
| `Opened` | `key` (`<agent>/<n>`), `role`, `agent`, `cli`, `model`, `person`, `env`, `harness` |
| `Offer` | `whose`, `name`, `about` |
| `Declaration` | `name`, `ref`, `description`, `hidden`, `resumable`, `agents`, `envs`, `params`; methods `agent(name)`, `env(name)` |
| `LiveCall` | `ref`, `name`, `depth`, `since`, `id`, `parent`, `task`, `resumable` |
| `Flowverse` | `name`, `url`, `at`, `fetched`, `fixed` |
| `Index` | `verse`, `releases`, `skipped`; methods `flows()`, `versions(flow)`, `release(flow, version)`, `newest(flow, spec="")` |
| `Release` | `name`, `version`, `description`, `repo`, `ref`, `commit`, `subdir`, `license`, `dependencies`, `owner`; properties `listed`, `owned`, `semver`, `url` |
| `Installed` | `verse`, `name`, `version`, `commit`, `repo`, `ref`, `subdir`, `dependencies`, `skills`, `owner`; properties `listed`, `called`, `at` |
| `Update` | `installed`, `version` |
| `Provider` | `cli`, `name`, `way`, `env`, `args`, `made`; property `at`; methods `held()`, `command(argv)`, `swaps()` |
| `Way` | `name`, `about`, `argv`, `asks`, `sets`, `args`, `stdin` |
| `Model` | `name`, `efforts`, `swarms` |
| `Checked` | `reached`, `said`, `home`, `cpus`, `memory`, `gpus`, `usable`, `gpu_memory`, `runtimes`, `version`, `short`, `nodes` |
| `SSHHost` | `alias`, `host`, `user`, `port`, `identity_files`, `proxy_jump` |
| `Nous` | `name`, `tries`, `policy`, `timeout`, `graph`, `then`; property `virtual` |
| `Graph` | `start`, `nodes`; methods `node(id)`, `names()`, `chained()` |
| `Node` | `id`, `use`, `balance`, `among`, `spread`, `on` |
| `Policy`, `Strategy` | `name`, `about` |
| `Ran` | `at`, `flow`, `task`, `workspace`, `began`, `ended`, `how`, `agents`, `sessions`, `called`, `resumable`, `ref`, `envs`, `used`, `params`, `budget`, `picked_up`, `reopened`, `profile_flow`, `profile_environment`, `spent`, `backup`, `backed`, `kind`, `prefer`, `permission`, `title`, `archived`, `workdir`, `env`, `forked`, `adopted`, `updated`; properties `name`, `chat` |
| `Drove` | `agent`, `backend`, `model`, `effort`, `provider`, `name`; property `spec` |
| `Called` | `flow`, `task`, `record`, `began`, `ended`, `how`, `calls` |
| `Session` | `agent`, `backend`, `provider`, `ident`, `name`, `at`, `flow`, `parent`, `record`, `where`, `harness` |
| `Target` | `name`, `url`, `branch`, `policies`, `every` |
| `Stored` | `key`, `machine`, `workspace`, `epic`, `flow`, `task`, `began`, `ended`, `how`, `head`, `chat` |

See the [Flow API](/reference/flows) for `Budget` and `Usage`.

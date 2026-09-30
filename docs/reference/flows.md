# Flows

The flow API: the module `hmz.flows`, the command-line specs that fill a flow's roles
(`-a`, `-e`, `-p`, `-b`, `-H`), how a flow is found, loaded, called, resumed and tested, and
every exception it raises. Guides: [Writing a flow](/weaver/writing-a-flow),
[Loops](/weaver/loops).

## Synopsis

```python
from hmz.flows import (
    Agent, AgentCollection, EnvCollection, FlowContext, FlowParams, LocalEnv, flow,
)


class Agents(AgentCollection):
    builder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def twice(task: str, *, agents: Agents, envs: Envs, params: FlowParams,
                ctx: FlowContext) -> None:
    """Two passes: do the work, then read it back and fix what is wrong."""
    builder = agents["builder"]
    session = await builder.spawn(env=envs["workspace"])
    await builder.run(task, session=session)
    await builder.run("Review what you did, and fix anything wrong.", session=session)
```

```sh
hmz exec -f twice -a builder=claude/claude-opus-5:high -b cost=5 "add a --dry-run flag"
```

## Stability

| Module | Status |
| --- | --- |
| `hmz.flows` | Stable. Importing it loads pydantic and no other part of humanize. |
| `hmz.sdk`, `hmz.sdk.fakes` (as `from hmz.sdk import fakes`) | Stable. See [SDK](/reference/sdk) and [Testing a flow](#testing-a-flow). |
| `hmz.runtime`, `hmz.runtime.flowing` | Internal. May change in any release. Named on this page only where a behaviour is defined there. |

Agents, environments, sessions, the context and the state are **protocols**. At run time a flow
is handed the runtime's own objects (views), which answer to these protocols structurally,
hold `__slots__`, and derive from none of them. A view grants exactly what its role declared:
anything else raises [`CapabilityNotGranted`](#capabilitynotgranted) whatever the harness or
machine underneath could do.

## Every name {#what-a-flow-drives}

Everything below is importable from `hmz.flows` and listed in `hmz.flows.__all__`.

| Group | Names |
| --- | --- |
| Defining a flow | [`flow`](#flow), [`Flow`](#flow-protocol), [`FlowFn`](#flowfn), [`load`](#load), [`FlowParams`](#flowparams), [`FlowContext`](#flowcontext), [`FlowState`](#flowstate) |
| Agents | [`AgentCollection`](#agentcollection), [`Agent`](#agent), [`Session`](#session), [`Outworlder`](#outworlder), [`HarnessKind`](#harnesskind), [`HARNESS_AGENTS`](#harness-agents) |
| Harness protocols | `ClaudeCodeAgent`, `CodexAgent`, `CursorAgent`, `OpenCodeAgent`, `MiMoCodeAgent`, `MiniMaxCodeAgent`, `QwenCodeAgent`, `KimiCodeAgent`, `GrokBuildAgent`, `PiAgent`, `AntigravityAgent`, `DeepSeekHarnessAgent` ([table](#what-each-harness-serves)) |
| Agent mixins | `GoalCommandAgentMixin`, `LoopCommandAgentMixin`, `SteeringAgentMixin`, `PermissionRequestHookAgentMixin`, `SubagentStartHookAgentMixin`, `SubagentStopHookAgentMixin`, `AskUserHookAgentMixin` ([table](#asking-for-an-agent-that-can-do-something)) |
| Permissions | [`Permission`](#permission), [`PermissionKind`](#permissionkind) |
| Budgets | [`Budget`](#budget), [`Usage`](#usage) |
| Environments | [`EnvCollection`](#envcollection), [`Env`](#env), [`LocalEnv`](#localenv), [`EnvBackendKind`](#envbackendkind), [`SequenceNotStr`](#sequencenotstr) |
| Environment mixins | `ShellEnvMixin`, `BashEnvMixin`, `FilesEnvMixin` ([table](#what-an-environment-can-do)); `GitWorktreeEnvMixin`, `TemporaryClonedDirEnvMixin`, `ScratchDirEnvMixin` ([table](#worktrees-copies-and-scratch-directories)); `RewindableEnvMixin`, `GitEnvMixin` ([table](#snapshots-and-rewinding)); `CPUEnvMixin`, `MemoryEnvMixin`, `GPUEnvMixin`, `ImageEnvMixin` ([table](#what-a-machine-must-have)) |
| Hooks | [`HookKind`](#hookkind), [`HookFn`](#hookfn), [`HookParams`, `HookResult`](#hookparams-and-hookresult), [`HOOK_TYPES`](#hook-types), and eleven `<Moment>HookParams`/`<Moment>HookResult` pairs ([table](#hook-fields)) |
| Errors | [`FlowException`](#when-something-goes-wrong) and the 45 classes under it |

## Defining a flow {#the-contract}

### `flow` {#flow}

```python
def flow(
    *,
    agents: type[AgentCollection],
    envs: type[EnvCollection],
    params: type[FlowParams],
    name: str | None = None,
    description: str | None = None,
    hidden: bool = False,
    resumable: bool = False,
) -> Callable[[FlowFn], Flow]
```

| Parameter | Type | Default | Meaning |
| --- | --- | --- | --- |
| `agents` | `type[AgentCollection]` | required | The agent roles, one key per role. See [`AgentCollection`](#agentcollection). |
| `envs` | `type[EnvCollection]` | required | The environment roles, one key per role. See [`EnvCollection`](#envcollection). |
| `params` | `type[FlowParams]` | required | The params model; `FlowParams` itself for none. |
| `name` | `str \| None` | the function's `__name__` | The flow's name in its module: the part of a [ref](#refs) after `:`. Must match `[A-Za-z0-9_][A-Za-z0-9_.-]*`. |
| `description` | `str \| None` | first line of the docstring, else `None` | One line, shown in lists of flows. |
| `hidden` | `bool` | `False` | Omit from every list and from `/flow`. The flow still runs and [loads](#load) by its ref. |
| `resumable` | `bool` | `False` | Keep a journal; gives the flow a [`ctx.state`](#flowstate). See [Resumable flows](#a-flow-that-can-be-picked-up). |

Returns a decorator. Applied to an `async def`, the decorator returns a [`Flow`](#flow-protocol)
(the runtime's `FlowImpl`). The decorator captures the global and local namespaces of the
code that applied it.

**Raised by the decorator** (`FlowDefinitionError`, message prefixed with the function's
qualified name):

| Condition | Message |
| --- | --- |
| not a coroutine function | ``a flow is an `async def` function`` |
| signature unreadable | `its signature cannot be read` |
| no positional first parameter | `a flow takes the task as its first argument` |
| `agents`, `envs`, `params` or `ctx` not accepted as keyword (and no `**kwargs`) | ``a flow takes `<name>` as a keyword argument`` |
| another parameter without a default | ``` `<param>` has no default, and a flow is called with a task, agents, envs, params and ctx alone``` |
| `agents` not an `AgentCollection` subclass | `agents=<value> is not an AgentCollection subclass` |
| `envs` not an `EnvCollection` subclass | `envs=<value> is not an EnvCollection subclass` |
| `params` not a `FlowParams` subclass | `params=<value> is not a FlowParams subclass` |
| name not matching the pattern | ``'<name>' is not a flow name: letters, digits, `_`, `.` and `-` `` |

**Raised later**, the first time the flow is called or described (listed, loaded by
`hmz exec`, opened in `/flow`), when the collections' annotations are resolved against the
captured namespaces (`FlowDefinitionError`; the first four rows are prefixed
`<Collection>.<role>`, the rest with the role type's `__qualname__`, e.g. `Builder: …`):

| Condition | Message |
| --- | --- |
| annotation is a string that does not resolve | `'<text>' cannot be resolved: <error>` |
| annotation is not a class | `<value> is not a class; a role is typed as one agent or environment type` |
| agent role type not an `Agent` | `<type> is not an Agent` |
| environment role type not an `Env` | `<type> is not an Env` |
| agent type carries an environment mixin | `an agent cannot be declared with an environment's mixins` |
| agent type derives from two harness protocols | `no agent is both <a> and <b>` |
| `Outworlder` type with a harness protocol or mixin | `an Outworlder is whoever is outside the run, and has no harness or mixins` |
| `_permission` not a `Permission` | `<Type>._permission is not a Permission` |
| `_skills` not a tuple/list of non-empty strings | `<Type>._skills is not a tuple of skill names` |
| environment type carries an agent mixin | `an environment cannot be declared with an agent's mixins` |
| `_cpu_count`, `_memory`, `_gpu_count`, `_gpu_memory` not an `int` ≥ 0 (a `bool` is refused) | `<Type>.<attr> is not a whole number of at least 0` |
| `_image` not a string without whitespace | `<Type>._image is not an image: <value>` |

`NotRequired`, `Required`, `ReadOnly` and `Annotated` wrappers are read through.
`from __future__ import annotations`, string annotations, and collections declared inside a
function all resolve. A role's type is read once per type and cached.

Two flows with one `name` defined in one module raise `FlowDefinitionError`
(`<module dir>: two flows are called '<name>'`) when the module's flows are enumerated. Two
functions of one Python name are one flow: the later binding replaces the earlier.

### `FlowFn` {#flowfn}

```python
class FlowFn[TAgents: AgentCollection, TEnvs: EnvCollection, TParams: FlowParams](Protocol):
    async def __call__(
        self, task: str, *, agents: TAgents, envs: TEnvs, params: TParams, ctx: FlowContext
    ) -> Any: ...
```

The decorated function. Its return value is the flow call's return value: what a calling flow
receives, [`Run.result`](/reference/sdk#run), and what [`run_fake`](#run-fake) returns.

| Argument | Value at run time |
| --- | --- |
| `task` | `str`, as given to `hmz exec`, `/flow`, `Hmz().run` or the caller |
| `agents` | a `dict[str, AgentView \| OutworlderView]`, one entry per role given or filled; a `NotRequired` role nobody gave is absent |
| `envs` | a `dict[str, EnvView]`, likewise |
| `params` | an instance of the `params` model |
| `ctx` | the call's [`FlowContext`](#flowcontext) |

### `Flow` {#flow-protocol}

What `@flow` and [`load`](#load) return.

| Member | Type | |
| --- | --- | --- |
| `description` | `str \| None` | Its one line. |
| `expected_agents` | `type[AgentCollection]` | The agent roles it declares. |
| `expected_envs` | `type[EnvCollection]` | The environment roles it declares. |
| `expected_params` | `type[FlowParams]` | Its params model. |
| `resumable` | `bool` | Whether a run of it can be picked up. |
| `await flow(task, *, agents, envs, params, budget=None)` | `Any` | Call it from inside a run. See [Calling a `Flow`](#calling-a-flow). |

A flow returned by `load` for a `git+` ref is fetched when any of these members is first read
or it is first called.

### `FlowParams` {#flowparams}

<span id="settings-of-the-flow-s-own"></span>

```python
class FlowParams(pydantic.BaseModel):
    model_config = ConfigDict(extra="forbid", ser_json_inf_nan="strings")
```

Subclassed with one pydantic field per param. The model is also the form `/flow` renders:
each field is a question, its type decides the input, its `description` is the help line.

| Rule | |
| --- | --- |
| Unknown keys | Refused (`extra="forbid"`). |
| Field without a default | Must be given (`-p`, `/flow`, or a caller). |
| Cross-field constraints | Belong in a `model_validator`, so they are refused before the run. |
| Infinity/NaN | Serialized as the strings `"Infinity"`/`"NaN"`. |

**How params are read** (`FlowImpl.params_of`), in order:

1. An instance of the flow's own model is used as is.
2. Any other `pydantic.BaseModel` is dumped and validated into the model.
3. A mapping is validated. If validation fails, each value whose field failed and which is a
   `str` is parsed as JSON (a string that is not JSON stays a string), and the mapping is
   validated again. This is how `-p` strings reach typed fields: `-p rounds=5` → `5`,
   `-p tags='["a","b"]'` → a list.
4. Anything else raises `ParamsError`: `<ref>: params=<value> is not a <Model> or a mapping`.

A validation failure raises `ParamsError` (`<ref>: <pydantic error>`); from `hmz exec` it is
refused before anything runs.

### `FlowContext` {#flowcontext}

<span id="the-context"></span>

```python
class FlowContext(Protocol):
    flow: Flow             # read-only properties
    budget: Budget
    usage: Usage
    state: FlowState | None
    resumed: bool
```

| Property | Type | Value |
| --- | --- | --- |
| `flow` | `Flow` | The flow being called. |
| `budget` | `Budget` | The effective budget of this call; see [Effective budget](#effective-budget). Built on each read. |
| `usage` | `Usage` | What this call and every call under it has spent. Built on each read. |
| `state` | `FlowState \| None` | The call's state for a resumable flow, `None` otherwise. |
| `resumed` | `bool` | `True` where this call picked up a call of an earlier run. |

Each call has its own context. A flow that calls another ten times holds ten contexts; the
spending of each is also counted in every context above it.

### `FlowState` {#flowstate}

```python
class FlowState(Protocol):
    def __getitem__(self, key: str) -> Any: ...
    def __setitem__(self, key: str, value: Any) -> None: ...
    def __delitem__(self, key: str) -> None: ...
    def __contains__(self, key: str) -> bool: ...
```

`ctx.state` of a resumable flow. The runtime's object also implements `__iter__`, `__len__`
and `get(key, default=None)`.

| Operation | Behaviour |
| --- | --- |
| `state[key] = value` | `key` must be a `str`, else `StateNotSerializable` (`a state key is a string, not <key>`). `value` is serialized with `json.dumps(..., allow_nan=True)`; a value it cannot serialize (or a recursion error) raises `StateNotSerializable` (also a `TypeError`): `<type> cannot be kept in a flow's state: <error>`. What is stored is the JSON round-trip of the value (a tuple becomes a list, dict keys become strings), so a fresh run and a resumed run read identical values. The write is appended to the journal and flushed before `__setitem__` returns. |
| `del state[key]` | Removes the key; `KeyError` if absent. Journaled and flushed. |
| `state[key]` | `KeyError` if absent. |
| Mutating a value in place | Not recorded. Assign the value again to record it. |

A resumable flow run without a journal (a resumable flow called from a non-resumable run, or
[`run_fake`](#run-fake) without `journal=`) gets a state held in memory only.

## Agent roles {#how-many-agents-and-what-they-are-for}

### `AgentCollection` {#agentcollection}

```python
class AgentCollection(TypedDict, extra_items=ReadOnly[Agent]): ...
```

Subclassed with one key per role. The key is the role's name in `-a <role>=…`, in `/flow`, in
the epic (`agents`, `opened.agent`), in the trace, and in the remembered settings.

| Role type | Filled by | Required |
| --- | --- | --- |
| `Agent`, a subclass with mixins, or a [harness protocol](#what-each-harness-serves) | `-a`, `/flow`, `Hmz().run(agents=…)`, or a caller | yes, unless `NotRequired[...]` |
| `Outworlder` | the runtime ([the person at the prompt](#the-person-at-the-prompt)); naming it with `-a` is refused | never given |

`"<role>" in agents` tests whether a `NotRequired` role was given.

### `Agent` {#agent}

```python
class Agent(Protocol):
    _permission: ClassVar[Permission] = Permission()
    _skills: ClassVar[tuple[str, ...]] = ()

    role: str                     # read-only properties
    harness: HarnessKind
    model: str
    effort: str
    provider: str

    async def spawn(self, *, env: Env) -> Session: ...
    async def run(self, prompt: str, *, session: Session,
                  output_schema: type[M] | None = None,
                  budget: Budget | None = None) -> str | M: ...
    async def fork(self, session: Session, *, env: Env) -> Session: ...
    def derive(self, *, permission: Permission | None = None,
               skills: tuple[str, ...] | None = None) -> Self: ...
    def on_session_start(self, fn: HookFn | None) -> None: ...
    def on_user_prompt_submit(self, fn: HookFn | None) -> None: ...
    def on_pre_tool_use(self, fn: HookFn | None) -> None: ...
    def on_notification(self, fn: HookFn | None) -> None: ...
    def on_stop(self, fn: HookFn | None) -> None: ...
    def on_session_end(self, fn: HookFn | None) -> None: ...
```

| Class attribute | Type | Default | Meaning |
| --- | --- | --- | --- |
| `_permission` | `Permission` | `Permission()` | What the role's sessions may touch; they run under exactly this. See [Permissions](#what-each-agent-may-do). |
| `_skills` | `tuple[str, ...]` | `()` | Skills mounted into the role's sessions. See [Skills](#the-skills-a-flow-brings). |

| Property | Type | Value |
| --- | --- | --- |
| `role` | `str` | The key it fills. |
| `harness` | `HarnessKind` | The CLI. |
| `model` | `str` | The model, as written in `-a`. |
| `effort` | `str` | The effort in the CLI's own words; `""` where `-a` said `auto`. |
| `provider` | `str` | The account its turns run as; `""` for the account this machine's CLI is signed into. |

| Method | Section |
| --- | --- |
| `spawn`, `run`, `fork` | [Sessions and turns](#sessions-and-turns) |
| `derive` | [`Agent.derive`](#derive) |
| `on_*` | [Hooks](#hooks-in-a-flow) |

### `HarnessKind` {#harnesskind}

`class HarnessKind(StrEnum)`: which CLI an agent is. The value is the name `-a` uses.

| Member | Value | CLI | Protocol (`HARNESS_AGENTS[kind]`) |
| --- | --- | --- | --- |
| `CLAUDE` | `claude` | Claude Code | `ClaudeCodeAgent` |
| `CODEX` | `codex` | Codex | `CodexAgent` |
| `CURSOR_AGENT` | `cursor-agent` | Cursor Agent | `CursorAgent` |
| `OPENCODE` | `opencode` | opencode | `OpenCodeAgent` |
| `MIMO` | `mimo` | MiMo Code | `MiMoCodeAgent` |
| `MCODE` | `mcode` | MiniMax Code | `MiniMaxCodeAgent` |
| `QWEN` | `qwen` | Qwen Code | `QwenCodeAgent` |
| `KIMI` | `kimi` | Kimi Code | `KimiCodeAgent` |
| `GROK` | `grok` | Grok Build | `GrokBuildAgent` |
| `PI` | `pi` | pi | `PiAgent` |
| `AGY` | `agy` | Antigravity | `AntigravityAgent` |
| `DSH` | `dsh` | DeepSeek Harness | `DeepSeekHarnessAgent` |
| `ACP` | `acp` | any CLI added on the Accounts page of `/settings`, driven over the Agent Client Protocol; `-a` names it by the name it was added under | `Agent` |

<span id="harness-agents"></span>`HARNESS_AGENTS: Mapping[HarnessKind, type]` (a read-only
mapping) maps each kind to its protocol. The capabilities the runtime's driver of a harness
serves are read off this protocol's bases, so the protocol and the driver cannot disagree.

### Agent mixins {#asking-for-an-agent-that-can-do-something}

A role declares what it needs beyond `Agent` by subclassing mixins. A mixin's own bases come
with it.

```python
class Builder(Agent, GoalCommandAgentMixin, PermissionRequestHookAgentMixin):
    _permission = Permission(system=PermissionKind.NONE)
```

| Mixin | Grants | Without it |
| --- | --- | --- |
| `GoalCommandAgentMixin` | `run` of a prompt that is `/goal` or starts `/goal` + whitespace: the harness's own goal command pursues the objective until the harness decides it is met. The driver strips the `/goal ` prefix and starts a goal. See [Goals](/weaver/goals). | `CapabilityNotGranted`: `<role>: /goal needs GoalCommandAgentMixin on the role` |
| `LoopCommandAgentMixin` | `run` of `/loop <interval> <task>`, passed to the CLI as typed: its own recurring task. | `<role>: /loop needs LoopCommandAgentMixin on the role` |
| `SteeringAgentMixin` | [`steer`](#steer). | `<role>: steer needs SteeringAgentMixin on the role` |
| `PermissionRequestHookAgentMixin` | `on_permission_request`. | `<role>: a permission_request hook needs PermissionRequestHookAgentMixin on the role` |
| `SubagentStartHookAgentMixin` | `on_subagent_start`. | `<role>: a subagent_start hook needs SubagentStartHookAgentMixin on the role` |
| `SubagentStopHookAgentMixin` | `on_subagent_stop`. | `<role>: a subagent_stop hook needs SubagentStopHookAgentMixin on the role` |
| `AskUserHookAgentMixin` | `on_ask_user`. | `<role>: a ask_user hook needs AskUserHookAgentMixin on the role` |

The prefix test is on the prompt with leading whitespace removed. Every prompt not starting
`/goal` or `/loop` goes to the CLI unchanged; other slash commands are not interpreted.

### What each harness serves {#what-each-harness-serves}

Generated from `hmz.runtime.flowing.spi.HARNESS_CAPABILITIES` and the harness profiles.

<div class="harness-matrix">

| `-a` | Goal | Loop | Steering | Permission request | Subagent start, stop | Ask user | [Fork](#fork) | Rungs |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | --- | --- |
| `claude` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | any workdir | read-only, workspace-write, auto, bypass |
| `codex` | ✓ | | ✓ | ✓ | ✓ | ✓ | any workdir | read-only, workspace-write, auto, bypass |
| `kimi` | ✓ | | ✓ | ✓ | | ✓ | any workdir | read-only, workspace-write, auto, bypass |
| `pi` | | | ✓ | | | ✓ | same workdir | read-only, workspace-write, auto, bypass |
| `dsh` | ✓ | | | | | | no | bypass |
| `cursor-agent` | | | | | ✓ | | no | read-only, workspace-write, auto, bypass |
| `mcode` | | | | | ✓ | | no | workspace-write, auto, bypass |
| `grok` `opencode` `mimo` `qwen` | | | | | | | same workdir | read-only, workspace-write, auto, bypass |
| `agy` | | | | | | | no | read-only, workspace-write, auto, bypass |
| `acp` | | | | | | | same workdir | set by the CLI |

</div>

A role typed as a harness protocol asks for **that harness** and every mixin in its row.
Given another harness it is refused: from `hmz exec` as
`<flow>: '<role>' requires <harness>, but got <other>` before anything runs, from a calling
flow as [`HarnessMismatch`](#harnessmismatch). A role declared by mixins alone may be filled by
any harness that serves them.

### Where capabilities are checked

| When | Check | Refusal |
| --- | --- | --- |
| Before a run (`hmz exec`, `Hmz().run`, `Runner`) | Each role's harness serves its mixins; a harness-protocol role gets that harness; required roles given; no role given that the flow does not declare or that the runtime fills. | `Refused` (a `ValueError`), exit status 2 from `hmz exec`; see [Command-line refusals](#command-line-refusals) |
| When `run_flow` starts the top call | The same, against the drivers. | `HarnessMismatch`, `CapabilityMissing`, `MissingRole`, `RequirementError` |
| When a flow calls another | What the caller hands over covers the callee's declaration. | [`RequirementError`](#requirementerror) leaves; see [What the called flow is handed](#what-the-called-flow-is-handed) |
| At every use | The view's grant contains the mixin for the operation. | [`CapabilityNotGranted`](#capabilitynotgranted) |

The flows humanize ships in the package (only [`chat`](#the-flow-in-the-package)) are marked
*full view*: each agent role is granted every mixin its harness serves, whatever it declares.

## Permissions {#what-each-agent-may-do}

::: danger Approvals are bypassed
Every harness runs in its no-approval mode. No session waits for a person to approve a tool,
and no model reviews another model's actions. An agent is limited by its `Permission` and by
the [hooks](#hooks-in-a-flow) the flow hangs on it.
:::

### `Permission` {#permission}

```python
@dataclass(frozen=True, slots=True)
class Permission:
    local: PermissionKind = PermissionKind.ALL
    user: PermissionKind = PermissionKind.READ
    system: PermissionKind = PermissionKind.READ
    online: PermissionKind = PermissionKind.ALL

    def covers(self, other: Permission) -> bool: ...
```

| Field | Scope | Default | Allowed |
| --- | --- | --- | --- |
| `local` | the workdir of the environment the session works in | `ALL` | `NONE`, `READ`, `ALL` |
| `user` | the rest of the home directory of the user the CLI runs as | `READ` | `NONE`, `READ`, `ALL`; ≤ `local` |
| `system` | everything else on the machine | `READ` | `NONE`, `READ`, `ALL`; ≤ `user` |
| `online` | the network, including the CLI's own web search and fetch | `ALL` | `NONE`, `ALL` |

Construction coerces each field with `PermissionKind(value)` and raises `ValueError`:

| Condition | Message |
| --- | --- |
| field not a permission kind | `<field>=<value> is not a permission kind` |
| `local >= user >= system` fails | `a wider scope may not be granted more than a narrower one: local=<k>, user=<k>, system=<k>` |
| `online` is `READ` | `online is all or nothing: NONE or ALL, not READ` |

`covers(other)` returns `True` iff each of the four fields is `>=` the same field of `other`.

### `PermissionKind` {#permissionkind}

`class PermissionKind(StrEnum)`: `NONE = "none"`, `READ = "read"`, `ALL = "all"`, totally
ordered `NONE < READ < ALL` (`<`, `<=`, `>`, `>=` defined; comparing with anything but these
three strings raises `TypeError`).

### Enforcement

A permission reaches a session twice: as a **fence** around the CLI's process tree, and as a
**rung** of the CLI's own approval ladder.

**The fence.** `system` is `/`, `user` is the home directory, `local` is the workdir. `READ`
allows reading a scope, `ALL` reading and writing, `NONE` neither. Independently of the scopes,
the CLI may:

- read `/usr`, `/bin`, `/lib*`, the files under `/etc` a resolver and TLS stack read, `/proc`,
  `/sys`, its own programs and install trees, and the Python running humanize;
- write the device nodes (`/dev/null`, `/dev/tty`, `/dev/pts`, `/dev/shm`, GPU nodes), its own
  state and sign-in directories, the directory its sessions are kept in, and a private scratch
  directory that is its `TMPDIR`. `XDG_CACHE_HOME`, `UV_CACHE_DIR`, `npm_config_cache`,
  `PIP_CACHE_DIR` and `GOCACHE` are pointed into that directory where the fence would not let
  them be written.

`online` `NONE` cuts the network except to the hosts the CLI's model and sign-in are at
(read under the session's account, so a gateway the account points at is included). The
default permission is a real fence: the workdir and the minimum above are writable, the rest
readable.

A CLI that can enforce part of the fence itself is configured to. The rest is enforced from
outside by `hmz internal fence`: Landlock for paths and TCP, a seccomp filter refusing every
other socket family, a second filter that lets a socket listen on loopback only, and a
loopback proxy passing only the listed hosts. A session is never run wider than its
permission. Where neither the CLI nor the machine can hold the fence, the session is refused
with [`HarnessSandboxed`](#harnesssandboxed) when it opens:

| Cause | Refused where |
| --- | --- |
| no Landlock (macOS; Linux < 5.13) | any fence other than all four scopes `ALL` with `online` `ALL` |
| Linux < 6.7 | `online` `NONE` |
| wrapper cannot trace its children (a container's default seccomp profile; Yama `ptrace_scope` 2 or 3) | `online` `NONE` |

Only `local`, `user`, `system` all `ALL` with `online` `ALL` fences nothing.

With the network cut, a program may listen on loopback only (`127.0.0.0/8`, `::1`, IPv4
loopback mapped into IPv6). A `bind` elsewhere, and a `listen` on a socket bound elsewhere,
fail with `EACCES`; the wrapper performs the `listen` itself on the socket it checked. A
process that makes itself undumpable (`ssh-agent`) cannot be checked and cannot listen.

Two gaps remain, both in the kernel: Landlock does not govern connecting to a Unix socket (a
docker daemon's or a session bus's is reachable), and with the network cut the proxy's port is
reachable by number on any address.

When the work is on another machine (a `docker` or `ssh` environment) the fence is held on
both: the CLI here inside this machine's Landlock with the environment's mirror as its
workdir, and every command on the target under `hmz internal fence` again, around the
target's own workdir, `$HOME` and minimum. With `online` `NONE` a command on the target
reaches no host. A CLI's own sandbox rung is not used there. A target that cannot hold the
fence refuses the session with `HarnessSandboxed` on its first turn; a container under
docker's default seccomp profile can hold `online` `ALL` but not `NONE`. See
[Remote execution](/reference/remote-execution#a-fence-on-both-machines).

| CLI | Filesystem | Network |
| --- | --- | --- |
| `claude` | external; its own sandbox covers only its Bash tool and is not used | external; `WebSearch`, `WebFetch` refused by rule |
| `codex` | external | external; web search and ChatGPT apps off natively; at `local` `READ` with `online` `ALL` its `read-only` sandbox is told to leave commands the network |
| `cursor-agent` | external; its own sandbox covers only shell commands and needs a user namespace | `NONE` refused: its web tools run on Cursor's servers |
| `mcode` | external; no sandbox of its own | `NONE` refused: its web search runs on MiniMax's service |
| `opencode`, `mimo` | external; file tools also refuse outside the fence | external; web tools removed offline |
| `qwen` | external | external; `web_search`, `web_fetch` withheld |
| `kimi` | external | external; its daemon may bind its one port |
| `grok` | external; its own sandbox writes `/tmp` | external; `--disable-web-search` offline |
| `pi` | external | external; started `--offline`; gateways its `models.json` declares stay reachable |
| `agy` | external; its `--sandbox` covers only commands | external; web tools removed offline (and always with `online` `NONE`) |
| `dsh` | external | external |
| `acp` | external, plus the `state` declared for it | external, to the `hosts` declared for it; `NONE` with none declared refused |

"External" is Landlock plus the loopback proxy.

**The rung.**

| `local` | every harness but `dsh`, `mcode`, `acp` | `dsh`, `mcode`, `acp` |
| --- | --- | --- |
| `READ` or `NONE` | `read-only` (Claude Code `plan`, Codex read-only sandbox, a tool list without writers) | `bypass` |
| `ALL` | `bypass` | `bypass` |

- `bypass` is the CLI's no-approval mode: Codex `danger-full-access` with approval `never`;
  Claude Code `manual` with humanize answering every request yes (a managed policy may forbid
  `bypassPermissions`).
- A hook only an asking CLI can deliver changes how it is started. Codex runs with approval
  policy `untrusted` while `on_permission_request` is hung, and enables its
  `default_mode_request_user_input` feature while `on_ask_user` is hung. Kimi Code runs at
  coganchor's `auto` rung (Kimi's `yolo`) while either is hung. humanize answers yes unless the
  hook says no.
- `online` also switches the CLI's own web tools (on for `ALL`, off for `NONE`) where the CLI
  can be told; where it cannot (`cursor-agent`, `mcode`, `pi`, `agy`, `acp`) the cut network
  stops them.

The rungs themselves are in [Agents](/reference/agents).

### `Agent.derive` {#derive}

```python
def derive(self, *, permission: Permission | None = None,
           skills: tuple[str, ...] | None = None) -> Self
```

| Parameter | Default | Meaning |
| --- | --- | --- |
| `permission` | this agent's | The derived agent's permission. Must be covered by this agent's. |
| `skills` | all of this agent's | Which of this agent's skills its sessions carry. Must be a subset. |

Returns a new view of the same driver with the narrower grant; the original is unchanged. The
derived agent shares the original's hooks and its sessions (a session of either may be used by
the other).

| Condition | Raises |
| --- | --- |
| `permission` not a `Permission` | `TypeError`: `permission=<value> is not a Permission` |
| `permission` wider | `CapabilityNotGranted`: `<role>: <permission> is wider than the <granted> this agent was granted` |
| a skill not granted | `CapabilityNotGranted`: `<role>: <names> is not among the skills this agent was granted` |

## Sessions and turns {#sessions-and-turns}

A session is one conversation of one agent in one environment. A turn is one prompt and its
answer.

### `Agent.spawn` {#spawn}

```python
async def spawn(self, *, env: Env) -> Session
```

Opens a session working in `env`'s workdir, on `env`'s machine. Starts no CLI: the CLI is
started by the first turn. Where the session's harness runs is settled here; see
[`-H`](#harness-placement).

| Condition | Raises |
| --- | --- |
| `env` not an environment the run handed out | `TypeError`: `<env> is not an environment this run handed out` |
| the call's caller or the run has ended | `FlowCancelled` |
| the agent's driver is closed | `SessionError`: `the agent's driver is closed` |
| a local workdir that is not a directory | `SessionError`: `<dir> is not a directory to open a session in` |
| CLI not installed where its harness runs | `HarnessNotInstalled` |
| the fence cannot be held | `HarnessSandboxed` |
| the CLI cannot be configured as the session asks | `HarnessUnrecoverable` |

### `Agent.run` {#run}

```python
async def run(self, prompt: str, *, session: Session,
              output_schema: type[M] | None = None,
              budget: Budget | None = None) -> str | M
```

| Parameter | Type | Meaning |
| --- | --- | --- |
| `prompt` | `str` | The prompt. `/goal …` and `/loop …` need their [mixins](#asking-for-an-agent-that-can-do-something). |
| `session` | `Session` | A session of this agent (or of an agent [derived](#derive) from it). |
| `output_schema` | `type[pydantic.BaseModel] \| None` | Return an instance of this model instead of text. |
| `budget` | `Budget \| None` | A limit on this one turn, applied with every budget above it. See [Budgets](#what-a-run-may-spend). |

Returns the text of the agent's last message, or an instance of `output_schema`.

**Order of events in one turn:**

1. Capability check for `/goal`, `/loop`; budget check (a spent budget raises its
   [`BudgetExceeded`](#budgetexceeded) leaf before anything is sent).
2. On the session's first turn only: `SESSION_START`. A non-empty `context` is prepended to
   the prompt, separated by a blank line.
3. `USER_PROMPT_SUBMIT` with the prompt as given. `block=True` raises `SessionError(reason)`
   (`a hook refused the prompt` for an empty reason). A non-empty `context` is appended after a
   blank line.
4. The CLI takes the turn. Steers queued before it starts are appended, each after a blank
   line.
5. If no steer is pending: `STOP` with `said` and `again`. `block=True` with a non-empty
   `reason` sends `reason` as the next prompt of the same turn and increments `again`. An
   empty `reason` does not block.
6. Steers that arrived during the CLI's turn are joined with blank lines and sent as the next
   prompt of the same turn.
7. With `output_schema`, the final text is parsed (below).

**Reading `output_schema`.** The model is validated with `model_validate_json` against, in
order: the whole answer stripped; each fenced code block (```` ```json ```` or ```` ``` ````);
the span from the first `{` to the last `}`. The first that validates is returned. If none
does: `OutputSchemaError: the answer is not a <Model>: <first 200 chars, JSON-quoted>`.

| Condition | Raises |
| --- | --- |
| `session` not this agent's | `SessionError`: `<role>: <session> is not one of this agent's` |
| a turn of the session is under way | `SessionError`: `<role>: a turn of this session is under way` |
| the session is closed | `SessionError`: `<role>: the session is over` |
| the turn was interrupted | `SessionError`: `the turn was interrupted` |
| a budget over the turn is spent | the `BudgetExceeded` leaf |
| a hard (non-graceful) limit reached mid-turn | the `BudgetExceeded` leaf; the CLI stops |
| the CLI failed the turn | the [`HarnessError`](#harnesserror) leaf |
| the task running `run` is cancelled | `asyncio.CancelledError`; the CLI is interrupted and waited on for up to 30 s |

One session takes one turn at a time; two sessions of one agent may take turns concurrently.

### `SteeringAgentMixin.steer` {#steer}

```python
async def steer(self, prompt: str, *, session: Session, queued: bool = True) -> None
```

| Parameter | Default | Meaning |
| --- | --- | --- |
| `prompt` | | Text put into the turn. |
| `session` | | The session taking the turn. |
| `queued` | `True` | `True`: the agent receives it at its next opportunity and continues. `False`: the CLI's current step is interrupted and the turn continues from this prompt (as <kbd>esc</kbd> then typing would). |

Raises `CapabilityNotGranted` without the mixin, `SessionError` for another agent's or a
closed session, and `SessionError` where the session has no turn under way.

### `Agent.fork` {#fork}

```python
async def fork(self, session: Session, *, env: Env) -> Session
```

Opens a new session that continues `session`'s conversation; `session` is unchanged.

| Condition | Raises |
| --- | --- |
| `session` not this agent's, or closed | `SessionError` (`<role>: the session to fork is over`) |
| `session` has taken no turn | `SessionError`: `the session to fork has taken no turn to carry on from` |
| harness does not fork (`cursor-agent`, `mcode`, `agy`, `dsh`) | `UnsupportedOperation`: `<harness> cannot fork a session` |
| `env` on another machine | `UnsupportedOperation`: `<harness> cannot fork a session onto another machine` |
| `env` another workdir, on a harness that forks only in place | `UnsupportedOperation`: `<harness> cannot fork a session into another workdir` |
| the CLI cannot cut the fork | `SessionError`: `the session cannot be forked: <reason>` |

A fork is cut when it takes its first turn. The parent is held open until then; if the parent
has taken another turn in between, the fork's first turn is refused. See
[Branching a conversation](/weaver/branching).

### `Session` {#session}

```python
class Session(Protocol):
    agent: Agent       # read-only properties
    env: Env
    usage: Usage
```

| Property | Value |
| --- | --- |
| `agent` | The agent whose conversation this is. |
| `env` | The environment it works in. |
| `usage` | What its turns have spent, current on every read. |

**Lifetime.** There is no `close`. A session is closed at the earlier of:

- the end of the flow call that opened it and of every call that call started; or
- the moment nothing references its view (the engine holds views weakly; a view held only by
  a reference cycle is closed when the cycle collector finds it).

Closing runs on the run's event loop exactly once and fires `SESSION_END`. A fork keeps its
parent open until the fork's first turn. A turn that is cancelled (a `TaskGroup` sibling
failing, a deadline, <kbd>ctrl+c</kbd>) interrupts the CLI.

## Hooks {#hooks-in-a-flow}

A hook is an `async` function from one moment's params to that moment's result, hung with the
agent's `on_<moment>` method.

```python
async def not_yet(hook: StopHookParams) -> StopHookResult:
    left = "- [ ]" in (await workspace.read("TASK.md")).decode()
    return StopHookResult(block=left and hook.again < 5, reason="TASK.md has unticked boxes.")

agent.on_stop(not_yet)
```

| Method | Moment | Needs | Delivered |
| --- | --- | --- | --- |
| `on_session_start` | a session's first turn is about to start | | by the driver, before the turn |
| `on_user_prompt_submit` | a prompt is about to be sent | | by the driver, before each turn |
| `on_pre_tool_use` | the agent reached for a tool | | from inside the CLI; see below |
| `on_notification` | the agent stopped to tell its user something | | from inside the CLI |
| `on_stop` | a CLI turn ended and the turn is about to end | | by the driver |
| `on_session_end` | the session is closing | | by the driver |
| `on_permission_request` | the harness asks whether a tool may run | `PermissionRequestHookAgentMixin` | from inside the CLI |
| `on_subagent_start` | the agent started a subagent | `SubagentStartHookAgentMixin` | from inside the CLI |
| `on_subagent_stop` | a subagent is about to finish | `SubagentStopHookAgentMixin` | from inside the CLI |
| `on_ask_user` | the agent asks its user a question mid-turn | `AskUserHookAgentMixin` | from inside the CLI |
| `on_outworlder_run` | an outworlder made with `Outworlder.new()` is asked to take a turn | an outworlder from `Outworlder.new()` | by the runtime |

### Hook fields {#hook-fields}

Every params class also carries `ctx: FlowContext` (the context of the flow the agent belongs
to) and `session: Session` (the session the moment arrived in). All params and results are
`@dataclass(frozen=True, slots=True, kw_only=True)`.

| `HookKind` | Params fields | Result fields (default) |
| --- | --- | --- |
| `SESSION_START` | | `context: str = ""` |
| `USER_PROMPT_SUBMIT` | `prompt: str` | `block: bool = False`, `reason: str = ""`, `context: str = ""` |
| `PRE_TOOL_USE` | `tool: str`, `input: Mapping[str, Any]` | `block: bool = False`, `reason: str = ""` |
| `PERMISSION_REQUEST` | `tool: str`, `input: Mapping[str, Any]` | `allow: bool = True`, `reason: str = ""` |
| `NOTIFICATION` | `message: str` | |
| `STOP` | `said: str`, `again: int = 0` | `block: bool = False`, `reason: str = ""` |
| `SESSION_END` | | |
| `SUBAGENT_START` | `subagent: str`, `task: str = ""` | `context: str = ""` |
| `SUBAGENT_STOP` | `subagent: str`, `said: str = ""` | `block: bool = False`, `reason: str = ""` |
| `ASK_USER` | `question: str`, `options: tuple[str, ...] = ()` | `answer: str \| None = None` |
| `OUTWORLDER_RUN` | `prompt: str`, `output_schema: type[BaseModel] \| None = None` | `output: str \| BaseModel` (required) |

The result classes are `<Moment>HookResult`, the params `<Moment>HookParams` (e.g.
`StopHookParams`, `StopHookResult`). A result constructed with no arguments changes nothing.

| Field | Meaning |
| --- | --- |
| `tool`, `input` | The tool as the harness names it and its arguments; `{}` where the harness gives none. A tool known only from the CLI's output stream carries `{"about": "<the transcript line>"}`. |
| `said`, `again` | The agent's last text, and how many times a `STOP` hook has already kept this turn going. |
| `subagent`, `task` | The harness's name for the subagent, and its task. |
| `question`, `options` | The question and the offered answers. `answer` need not be one of them; `None` leaves it unanswered and the agent continues without one. |
| `context` | Text added to the prompt (see [`run`](#run)). For `SUBAGENT_START` it is delivered to no CLI. |
| `block`, `reason` | See [`run`](#run) for `USER_PROMPT_SUBMIT` and `STOP`. A blocked `PRE_TOOL_USE` refuses the tool and tells the agent `reason` (`refused by a hook` if empty). `SUBAGENT_STOP` results are delivered to no CLI. |
| `allow`, `reason` | `allow=False` refuses the tool, overriding the bypassed approvals; the agent is told `reason` (on Codex, whose refusals carry no reason, as a steer into the turn). |
| `output` | What the outworlder's `run` returns: text, or an instance of `output_schema`. |

**Rules.**

- Hanging a hook replaces the one hung on that moment; `None` removes it.
- A hook covers every session of its agent, including sessions opened later and sessions of
  agents [derived](#derive) from it. A called flow's hooks are its own: they are not heard by
  its caller's sessions and vice versa.
- A hook runs on the flow's event loop as the flow its agent belongs to. An exception it raises
  fails the turn the moment arrived in; `run` raises it.
- `on_pre_tool_use` can refuse a tool only on CLIs that gate tools through their own hook table
  (Claude Code, Qwen Code). On the rest it observes a tool already reached for.
- A moment delivered from inside the CLI that waits more than **900 s** (`HOOK_TIMEOUT`) for
  its hook is answered as if no hook were hung. `on_ask_user` has no timeout.
- A hook hung mid-turn applies to that turn's later moments, except those that change how the
  CLI is started, which apply from the next turn: `on_pre_tool_use` on a gating CLI, and
  `on_permission_request` or `on_ask_user` on Codex (whose app server is restarted between
  turns for it) and Kimi Code.
- A session opened while any of `on_pre_tool_use`, `on_permission_request`, `on_ask_user` is
  hung keeps its harness on this machine under `-H adaptive`; see
  [Harness placement](#harness-placement).

### `HookKind` {#hookkind}

`class HookKind(StrEnum)`: `SESSION_START`, `USER_PROMPT_SUBMIT`, `PRE_TOOL_USE`,
`PERMISSION_REQUEST`, `NOTIFICATION`, `STOP`, `SESSION_END`, `SUBAGENT_START`,
`SUBAGENT_STOP`, `ASK_USER`, `OUTWORLDER_RUN`. Each value is the lowercase member name
(`HookKind.STOP == "stop"`).

### `HookFn` {#hookfn}

```python
class HookFn[TParams: HookParams, TResult](Protocol):
    async def __call__(self, params: TParams, /) -> TResult: ...
```

### `HookParams` and `HookResult` {#hookparams-and-hookresult}

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class HookParams:
    ctx: FlowContext
    session: Session

@dataclass(frozen=True, slots=True, kw_only=True)
class HookResult: ...
```

The bases of every `<Moment>HookParams` and `<Moment>HookResult`.

### `HOOK_TYPES` {#hook-types}

`HOOK_TYPES: Mapping[HookKind, tuple[type[HookParams], type[HookResult]]]`:
`HOOK_TYPES[HookKind.STOP] == (StopHookParams, StopHookResult)`.

## The person at the prompt {#the-person-at-the-prompt}

### `Outworlder` {#outworlder}

```python
class Outworlder(Agent, Protocol):
    away: bool                                     # read-only property

    @classmethod
    def new(cls) -> Self: ...
    def on_outworlder_run(self, fn: HookFn | None) -> None: ...
```

A role typed `Outworlder` is filled by the runtime. At the top of a run it is whoever started
the run; naming it with `-a` is refused
(`<flow>: '<role>' is assigned automatically by the runtime and cannot be set with -a`).

| Member | Behaviour |
| --- | --- |
| `spawn(env=…)` | Opens a session of the outworlder. |
| `run(prompt, session=…, output_schema=None)` | Asks the person and returns what they typed; with `output_schema`, asks one question per field and builds the model. |
| `away` | `True` under `hmz exec` (no one is at a prompt) and while [`/afk`](/user/afk) is on for the role. |
| `Outworlder.new()` | A new outworlder answered by the flow through `on_outworlder_run`. Away until a hook is hung. |
| `on_outworlder_run(fn)` | Only on an outworlder from `new()`; on any other raises `CapabilityNotGranted`: `<role>: only an outworlder made with Outworlder.new() is answered by a hook`. |
| `fork` | `UnsupportedOperation`: `an outworlder's session cannot be forked`. |
| `derive(skills=…)` | Non-empty skills raise `CapabilityNotGranted`: `<role>: an outworlder has no skills`. |

**While away**, `run` returns at once: `""` for text; the schema built from defaults where
every field has one; otherwise `OutworlderAway`:
`nobody is there to answer with a <Model>, and it has fields with no default`.

A caller may pass its own outworlder, one from `Outworlder.new()`, or omit the role (the
callee gets the run's). An outworlder may also be passed for a plain `Agent` role that
declares no mixin and no harness; a role that does raises `CapabilityMissing`
(`<ref>: '<role>' asks for what no outworlder can do`). The run's outworlder is asked, and
asked whether it is away, as the `Outworlder` role the run filled with it, whatever role name
a caller passes it under.

## Environment roles {#where-each-agent-works}

An environment is a working directory on a machine: this one, one reached with `ssh`, or a
container of its own on a docker daemon.

### `EnvCollection` {#envcollection}

```python
class EnvCollection(TypedDict, extra_items=ReadOnly[Env]): ...
```

One key per role, typed `Env`, `LocalEnv`, or a subclass carrying mixins. `NotRequired`
roles may be omitted. Every role but a `LocalEnv` one is filled with
[`-e`](#e-environments).

### `Env` {#env}

```python
class Env(Protocol):
    workdir: PurePosixPath      # read-only properties
    backend: EnvBackendKind
    provider: str
    available: bool
    role: str

    async def derive_subdir(self, *, subdir: PurePosixPath | str) -> Env: ...
```

| Member | Value |
| --- | --- |
| `workdir` | Where commands run and relative paths resolve: absolute, or `~/…` under the ssh login's home. For `docker`, a directory of the daemon's host, mounted at the same path in the container. |
| `backend` | `local`, `ssh` or `docker`. |
| `provider` | `""` for `local`; the ssh destination or stored provider name for `ssh`; the docker provider name (`local` for docker's default here) for `docker`. |
| `available` | Whether the machine was reachable and the workdir existed, as last probed. |
| `role` | The key it fills. |
| `derive_subdir(subdir=…)` | An environment at a directory under this workdir, created if missing, same role and grant. `ValueError` for an absolute `subdir` or one that climbs out; `EnvError` if it cannot be made. |

### `LocalEnv` {#localenv}

```python
class LocalEnv(Env, Protocol): ...
```

The workspace the run was started in (the directory `hmz` was started in, or the `Hmz`
workspace), filled by the runtime. A role typed `LocalEnv` or a subclass takes no `-e`
(`<flow>: '<role>' is the workspace the run started in and cannot be set with -e`). A caller
may omit it (the callee gets the run's workspace, granted what the callee declares) or pass an
environment on this machine; an environment on another machine raises `CapabilityMissing`:
`<ref>: '<role>' is a LocalEnv, and the environment given is <backend>@<provider><workdir>, which is not this machine`.

### `EnvBackendKind` {#envbackendkind}

`class EnvBackendKind(StrEnum)`: `LOCAL = "local"` (this machine), `SSH = "ssh"` (a host
`ssh` reaches), `DOCKER = "docker"` (a container of its own on a docker provider's daemon).

### What an environment can do {#what-an-environment-can-do}

| Mixin | Adds | Without it |
| --- | --- | --- |
| `ShellEnvMixin` | `async exec(argv: SequenceNotStr[str], *, timeout: float = 0) -> tuple[int, str, str]`: runs one program, no shell, in the workdir. Returns `(exit status, stdout, stderr)` decoded as UTF-8. `timeout` in seconds, `0` for none; past it the program is killed and `EnvCommandTimeout` raised. `EnvError` if it cannot start. | `<role>: exec needs ShellEnvMixin on the role` |
| `BashEnvMixin` | `exec(script: str, …)` too, run as `bash -c script` in the workdir, same timeout and results. Includes `ShellEnvMixin`. | `<role>: a script exec needs BashEnvMixin on the role` |
| `FilesEnvMixin` | `async read(path: str) -> bytes`, `async write(path: str, data: bytes) -> None`; `path` relative to the workdir or absolute. `write` replaces the file whole and creates parent directories. `EnvFileNotFound` for a missing file, `EnvPermissionDenied` for a refused one. | `<role>: read needs FilesEnvMixin on the role` (or `write`) |

`exec` takes exactly one command, positional or as `argv=`/`script=`; anything else raises
`TypeError: exec takes one command: an argv, or a script`.

<span id="sequencenotstr"></span>`SequenceNotStr[T]` is the type of an argv: a sequence that is
not a `str` (a `str`'s `__contains__` takes only `str`, which keeps it from matching). Lists
and tuples of strings match.

### What a machine must have {#what-a-machine-must-have}

| Mixin | Class attribute | Default | Meaning |
| --- | --- | --- | --- |
| `CPUEnvMixin` | `_cpu_count: int` | `1` | Minimum logical CPUs. |
| `MemoryEnvMixin` | `_memory: int` | `0` | Minimum memory, bytes. |
| `GPUEnvMixin` | `_gpu_count: int`, `_gpu_memory: int` | `1`, `0` | Minimum GPUs; minimum memory per GPU, bytes. |
| `ImageEnvMixin` | `_image: str` | `""` | Image a `docker` environment's container starts from: `""` for the provider's image, else `python:3.12-slim`. Needs `/bin/sh` and Python ≥ 3.12; no sshd. Ignored for `local` and `ssh`. |

An attribute is read only where its mixin is among the type's bases. For `local` and `ssh`, a
machine with less than declared is refused before anything runs with
[`ResourceUnmet`](#resourceunmet): `<ref>: '<role>' needs <n> CPUs, and the environment given has <m>`
(likewise `bytes of memory`, `GPUs`, `bytes of memory per GPU`).

For `docker` the amounts size the container: it gets exactly what the role declares as hard
limits, no limit on what it declares none of, and no GPU without `GPUEnvMixin`. Before any
agent starts, the request is held against what the provider may still hand out; where it
cannot, the run is refused with `ResourceUnmet`, naming what is free and which container holds
the rest ([how](/reference/machines#docker-environments)). Everything derived from a `docker`
environment is in the same container.

### Worktrees, copies and scratch directories {#worktrees-copies-and-scratch-directories}

| Mixin | Methods |
| --- | --- |
| `GitWorktreeEnvMixin` | `async derive_worktree(*, ref: str \| None = None, dir: PurePosixPath \| str \| None = None) -> Self` |
| `TemporaryClonedDirEnvMixin` | `async derive_temp_clone(id: str) -> Self`, `async destroy_temp_clone(id: str) -> None` |
| `ScratchDirEnvMixin` | `async derive_scratch(id: str) -> Self`, `async destroy_scratch(id: str) -> None` |

Each derived environment is on the same machine, fills the same role, and carries the same
grant.

| Method | Behaviour | Raises |
| --- | --- | --- |
| `derive_worktree` | `git worktree add` of the repository the workdir is in, `ref` checked out detached (default: what the workdir has checked out), at `dir` (relative to the workdir or absolute; default a fresh directory under `envs/…/worktrees/`). Not removed by humanize. | `WorktreeError`: not in a repository, unknown ref, directory taken |
| `derive_temp_clone(id)` | A copy of the workdir (a reflink where the filesystem supports it). Same `id` from the same environment → same copy, made once. | `TempCloneBusy` if another environment holds that id |
| `derive_scratch(id)` | An empty directory; same `id` → same directory. | `ScratchError` |
| `destroy_temp_clone(id)`, `destroy_scratch(id)` | Remove now; no-op if absent. | `ScratchError` (scratch) |

Copies and scratch directories are removed when the flow call that made them ends (after
every call it started), with at most 30 s allowed for cleanup, unless the run keeps a journal
(a [resumable](#a-flow-that-can-be-picked-up) run): then each is recorded in the journal and
kept for `--resume`. Locations are under `envs/` in humanize's home on the machine that holds
them; see [Files](/reference/files).

### Snapshots and rewinding {#snapshots-and-rewinding}

| Mixin | Methods |
| --- | --- |
| `RewindableEnvMixin` | `async snapshot(name: str \| None = None) -> str`, `async rewind(ref: str) -> None`, `async snapshots() -> list[str]` |
| `GitEnvMixin` | the same, implemented with git. Includes `RewindableEnvMixin`. |

`RewindableEnvMixin` is an interface: declared alone it grants nothing, and each method
raises `CapabilityNotGranted` (`<role>: snapshot needs GitEnvMixin on the role`). Type helpers
against it and declare `GitEnvMixin` on the role.

| Method | Behaviour |
| --- | --- |
| `snapshot(name)` | Records the git worktree containing the workdir — `HEAD`, the index, and every file not ignored (untracked included) — as a commit under `refs/hmz/snapshots/<name>`, touching none of them. Returns that ref. `name=None` uses `<UTC %Y%m%dT%H%M%S.%fZ>-<4 hex>`. An existing `name` is replaced. |
| `rewind(ref)` | Restores the worktree. A snapshot ref restores its commit, index and files (untracked as untracked). Any other ref git resolves to a commit is checked out with its files and a matching index. The checked-out branch (if any) is moved to the commit; files neither in it nor ignored are removed (nested repositories too); a merge, cherry-pick or revert in progress is abandoned. `HEAD` moves last. A `ref` that is empty or starts with `-` is refused. |
| `snapshots()` | The snapshot refs, oldest first by committer date (to the second; ties by name). Shared by every worktree of the repository. |

The whole worktree is affected, whatever subdirectory the workdir is. Ignored files and a
`.humanize/` at the worktree's top are neither recorded nor removed. Snapshots persist until
`git update-ref -d refs/hmz/snapshots/<name>`.

`RewindError` is raised for a workdir outside a git worktree, a ref git does not know, a name
git refuses as a ref, a snapshot taken before the first commit rewound on a detached `HEAD`,
or any other git failure (`could not <snapshot|rewind|list the snapshots of> <workdir>: <what git said>`).

A flow declaring `GitEnvMixin` for an environment whose machine has no `git` on its `PATH` is
refused before anything runs:

```
hmz exec: error: tries: 'repo' needs GitEnvMixin, which docker@local/srv/repo does not support: GitEnvMixin needs git on the machine's PATH, and it has none
```

## Budgets {#what-a-run-may-spend}

### `Budget` {#budget}

```python
class Budget(pydantic.BaseModel):   # frozen=True, extra="forbid", ser_json_inf_nan="strings"
    duration: timedelta | None = None     # >= 0
    cost: float | None = None             # >= 0, USD
    output_tokens: int | None = None      # >= 0
    graceful: bool = True
```

| Field | Limits |
| --- | --- |
| `duration` | Wall-clock time from the start of the call (or turn) the budget belongs to: a deadline. |
| `cost` | USD spent by turns under it. |
| `output_tokens` | Tokens written by agents under it. |
| `graceful` | `True`: a turn under way when a limit is reached may finish. `False`: it is cut off at once. |

At least one of `duration`, `cost`, `output_tokens` must be set
(`a budget sets at least one of duration, cost, output_tokens`), and none may be negative;
otherwise `pydantic.ValidationError`. `Budget(cost=math.inf)` means unlimited and serializes
as `{"cost": "Infinity"}`.

**Which runs need one.** Every run except of a flow shipped in the package: from `-b`
(see [`-b`](#b-budget)), `/flow`, or `budget=` in [Python](/reference/sdk). Without it:
`<flow> requires a budget: specify with -b duration=...,cost=...,output_tokens=...`. A flow
shipped in the package (`chat`) given none runs under `Budget(cost=math.inf)`.

### Effective budget

Every call and every turn may carry its own budget (`budget=` of [`Flow.__call__`](#calling-a-flow)
and [`Agent.run`](#run)). They nest:

- **Cost and output tokens** spent anywhere under a call count against it and every call above.
- **`duration`** is a deadline per call: a call's deadline is the earliest of its own
  (`start + duration`) and every one above. Ten concurrent calls with an hour each spend one
  hour of their caller's.
- **`ctx.budget`** reports, for each limit, the least over the chain of
  `limit − spent under that call + spent under this call` (the total this call may reach),
  `duration` as the time from this call's start to its deadline, and `graceful=False` if any
  budget in the chain is not graceful. `cost` is `None` where no budget limits it but another
  limit exists.
- **A turn** is held to the least remaining of each limit over every budget above it plus its
  own. Where two budgets leave the same amount, a hard (`graceful=False`) one wins. A turn's
  own budget lasts one turn: a graceful one only counts; use `graceful=False` to cut a turn
  short.

**Enforcement.**

| Situation | Result |
| --- | --- |
| Turn requested with a spent limit | The `BudgetExceeded` leaf, before anything is sent: `<ref>: its budget's duration is spent` / `cost is spent` / `output tokens are spent`. |
| Limit reached mid-turn, graceful | The turn completes and returns; the next turn raises. |
| Limit reached mid-turn, hard | The CLI is stopped; `run` raises the leaf. |
| A call's deadline passes | The call's task is cancelled after in-flight turns under it finish (graceful) or at once (hard); the cancellation surfaces from the call as `DurationExceeded`. A cancellation from anywhere else remains a `CancelledError`. |
| After any of the above | The budget stays spent: every later turn under it raises again. |

Spending is read as the CLI reports it (polled every 1 s while the CLI is silent) and priced
with humanize's price table ([Tally](/user/tally)); a model with no price costs `0`, so a cost
limit alone does not stop it.

### `Usage` {#usage}

```python
class Usage(pydantic.BaseModel):    # frozen=True, extra="forbid"
    duration: timedelta = timedelta(0)
    cost: float = 0.0
    output_tokens: int = 0
```

`duration` is the sum of the durations of every turn counted (concurrent turns each count).
`ctx.usage`, `Session.usage` and [`Run.usage`](/reference/sdk#run) are `Usage` values. The
run's total is written to the epic as the [`usage`](/reference/tracing#epic-jsonl) event.

## Concurrency {#a-flow-that-waits-for-more-than-one-thing}

A flow is a coroutine: `asyncio.gather`, `asyncio.TaskGroup`, `asyncio.timeout` and `except*`
behave as anywhere.

- Turns of one session are sequential; a second `run` while one is under way raises
  `SessionError`.
- Cancelling a task in a turn interrupts that CLI.
- A called flow's exception reaches `except*` with its own class.
- Concurrent calls form a tree of contexts, each with its own usage.

## Resumable flows {#a-flow-that-can-be-picked-up}

A flow with `resumable=True` keeps a journal while it runs. The newest run of it in a
workspace is picked up by `hmz exec --resume`, `/resume`, `Hmz().run(resume=True)`, or *resume
run* on `/epics` (a chosen epic).

| Refusal | Message |
| --- | --- |
| flow not resumable | `<flow> does not support resuming, so there is no run to resume` |
| no journal holding a flow call in this workspace | `<flow> has no run to resume here: none saved any progress` |
| a given epic without one | `<epic> has no saved progress to resume from` |

**A picked-up run is a new run** with its own epic, whose `began` event names the epic it was
`picked_up` from; the journal is copied into the new epic, compacted, and appended to.

### Journal {#journal}

`resume.jsonl` in the epic: JSON Lines, first line `{"t":"journal","v":1}`.

| `t` | Fields | Written |
| --- | --- | --- |
| `call` | `id` (int), `parent` (int, `0` for the top call), `digest` (hex), `seq` (int), `ref` (canonical ref) | when a call starts; batched |
| `set` | `id`, `key`, `value` | on each state write; flushed immediately |
| `del` | `id`, `key` | on each state delete; flushed immediately |
| `session` | `id`, `role`, `harness`, `model`, `session` (the CLI's id) | once the CLI names the session (at open or during the first turn); batched |
| `tmp` | `id`, `env` (role), `kind` (`temp_clone` \| `scratch`), `name` (the id), `chain`, `workdir` | when a copy or scratch directory is made; batched |
| `end` | `id`, `ok` (bool) | when the call ends; batched |

Batched records are written within 0.1 s or with the next state write. The file is synced on
close. A line that does not parse is skipped when read. On resume the journal is rewritten
once, compacted: each call, its final state, its sessions and temporary directories, its end.

### Matching calls {#digests}

A call's **digest** is `blake2b(digest_size=16)` over, `\0`-separated: the callee's canonical
ref, the task, one `role=spec` per agent role then per environment role (each group in
declaration order), and the params serialized as JSON.

| Role | Spec in the digest |
| --- | --- |
| agent | `<harness>@<provider>/<model>:<effort>\|<local>,<user>,<system>,<online>\|<skill,skill…>` |
| outworlder | `outworlder`, or `outworlder:new` for one from `Outworlder.new()` |
| environment | its derivation chain: `<backend>@<provider><workdir>` followed by `#subdir(<path>)`, `#worktree(<ref>,<dir>)`, `#temp_clone(<id>)`, `#scratch(<id>)` per derivation; never the path a copy landed at |

`seq` counts earlier calls under the same parent with the same digest.

| Call | On resume |
| --- | --- |
| the top call | Picks up the earlier top call unconditionally: `ctx.resumed` is `True`, state restored. |
| a call under a call that picked up | Picks up the earlier call with the same parent, digest and the lowest unclaimed `seq`; otherwise starts afresh with an empty state. |
| a call of a non-resumable flow | Has no state; still passes resumption to the calls it makes. |

Temporary copies and scratch directories recorded in the journal are kept, so the resumed run
finds them at the same deterministic paths.

## Calling another flow {#a-flow-that-calls-another-flow}

```python
plan = load("humanize1:gen-plan")
await plan(f"plan this first: {task}",
           agents={"planner": agents["builder"], "analyst": agents["reviewer"]},
           envs={}, params=plan.expected_params())
```

### `load` {#load}

```python
def load(ref: str) -> Flow
```

Returns the flow `ref` names. Inside a run, the same ref from the same module is resolved
once per run. A `git+` ref returns a flow that is fetched when first used.

| Raises | When |
| --- | --- |
| `FlowRefError` (a `ValueError`) | not a ref; `:<name>` with no flow asking (`':review' is relative to the flow asking, and no flow is asking`) |
| `FlowNotFound` | the ref names no flow; a `git+` repository cannot be fetched or has no such flow |
| `FlowLoadConflict` | importing the module would replace a module another flow of a running run uses |
| `FlowDefinitionError` | the named module or flow is written wrong, or its import raised (`importing the flow at <dir> failed: <error>`) |

### Refs {#refs}

| Form | Names | Resolved |
| --- | --- | --- |
| `:<name>` | a flow in the same module as the code calling `load` | only with a flow asking |
| `<flow>` | the flow a bare name means in module `<flow>` | in the asking flow's own directory of flows (its flowverse), else [nearest first](#where-flows-live), else as a path |
| `<flow>:<name>` | flow `<name>` of module `<flow>` | as above |
| `<flowverse>/<flow>[:<name>]` | a flow of that flowverse | that flowverse only (no stand-in) |
| a path | a flow directory, its `__init__.py`, or a `.py` file (`.py` may be omitted) | `~` expanded |
| `git+<url>[@<rev>]#<flow>[:<name>]` | a flow in another repository's `flows/` | fetched; see below |

Grammar rules:

- `<name>` and `<flow>` in a `git+` fragment match `[A-Za-z0-9_][A-Za-z0-9_.-]*`.
- A `:` is a sub-flow separator only where what follows contains no `/`; otherwise the whole
  string is a path.
- `git+` URLs: scheme `https`, `http`, `ssh`, `file` or `git`; a host is required except for
  `file`; `@<rev>` is the last `@` in the path; query and fragment of the URL are dropped.
  Errors: `'<ref>': a ref naming another flowverse is git+<url>[@<ref>]#<flow>[:<sub>]`,
  `'<ref>': '<url>' is not a URL git can fetch`, `'<ref>': '<url>' names no repository`,
  `'<ref>': #<fragment> is not <flow>[:<subflow>]`.
- A bare module name picks the flow named after the directory (or file stem); else the only
  non-hidden flow; else `FlowNotFound`
  (`<ref>: <dir> holds a, b and none is called '<stem>'; name one as <stem>:<flow>`, or
  `<ref>: <dir> defines no flow`). A named flow that is absent:
  `<ref>: <dir> holds no flow called '<name>'; it holds a, b`.

**`git+` fetching.** `<rev>` absent means the default branch. A 40-hex `<rev>` is used as a
commit; anything else is resolved with `git ls-remote`. The checkout is kept at
`~/.humanize/flowverses/.pinned/<blake2b-8(url)>/<sha>` and cloned once per commit; each run
fetches a given URL and revision at most once, on a worker thread, when the flow is first
called (`hmz exec -f git+…` fetches before the run starts). Each git command has 120 s.

**Module import rules.**

- A flow directory is imported as a module named after the directory where that top-level
  name is free (or already this directory's); otherwise as
  `_hmz_flow_<stem>_<blake2b-4(path)>`. The directory is put on `sys.path`, so modules and
  packages beside `__init__.py` import by plain name; those names are claimed by the flow.
- A run imports a module at most once. Nothing a running run uses is removed from
  `sys.modules`. A module whose `.py` files changed (mtime or size) is re-imported by the next
  run that is not sharing it with a running run.
- Two directories claiming one top-level name while a run uses one raise `FlowLoadConflict`
  (`<a> and <b> both import '<name>', and a run going now uses the second`); a name held in
  `sys.modules` by something that is not a flow raises
  `importing <dir> would replace the module '<name>' (<file>)`.
- A module's flows are the `@flow` objects defined in files inside its directory; one imported
  from elsewhere is not one of its flows.

### Calling a `Flow` {#calling-a-flow}

```python
async def __call__(self, task: str, *, agents: Mapping[str, Agent],
                   envs: Mapping[str, Env], params: FlowParams,
                   budget: Budget | None = None) -> Any
```

| Parameter | Meaning |
| --- | --- |
| `task` | The callee's task. |
| `agents` | One agent per callee role, keyed by the callee's role names. |
| `envs` | One environment per callee role. |
| `params` | An instance of the callee's model is used as is; another model or a mapping is validated ([rules](#flowparams)). |
| `budget` | A budget of the call's own, combined with the caller's remaining budget. Must be exactly a `Budget` (`TypeError` otherwise). |

Returns what the callee returns; what it raises reaches the caller unwrapped.

| Condition | Raises |
| --- | --- |
| called outside any run | `FlowRuntimeError`: `<ref>: a flow is called from inside a run; start one with run_flow` |
| the caller (or any call above, or the run) has ended | `FlowCancelled`: `<ref>: <caller ref \| the run> has ended` |
| depth would exceed 64 | `FlowDepthExceeded` (a `RecursionError`): `<ref>: flows are called 65 deep, and 64 is the most` |

#### What the called flow is handed {#what-the-called-flow-is-handed}

All checks run before the callee starts; a refusal means nothing of the callee ran and
nothing was spent. Refusals for one kind of agent grant are computed once per role.

| Given for a role | Requirement | Refusal |
| --- | --- | --- |
| nothing, required agent role | — | `MissingRole`: `<ref>: no agent was given for '<role>'` |
| nothing, required environment role | — | `MissingRole`: `<ref>: no environment was given for '<role>'` |
| nothing, `Outworlder` role | filled with the run's outworlder | — |
| nothing, `LocalEnv` role | filled with the run's workspace, granted the callee's declaration | `CapabilityMissing` if the workspace lacks a declared mixin |
| an agent | carries every mixin the role declares | `CapabilityMissing`: `<ref>: '<role>' needs <mixins>, which the agent given was not granted` |
| an agent | its permission covers the role's `_permission` | `PermissionTooNarrow`: `<ref>: '<role>' needs <p>, and the agent given holds <q>` |
| an agent, harness-protocol role | the same harness | `HarnessMismatch`: `<ref>: '<role>' is <harness>, and the agent given is <other>` |
| an agent, `Outworlder` role | — | `CapabilityMissing`: `<ref>: '<role>' is an Outworlder, and <agent> is an agent` |
| an environment | carries every mixin the role declares | `CapabilityMissing`: `<ref>: '<role>' needs <mixins>, which the environment given was not granted` |
| an environment | meets the role's resources | `ResourceUnmet` |
| an environment, `LocalEnv` role | on this machine | `CapabilityMissing` (see [`LocalEnv`](#localenv)) |
| anything not handed out by the run | — | `RequirementError`: `<ref>: '<role>' was given <value>, which is not an agent the run handed out` (or `environment`) |

The callee receives **exactly** its declaration: each agent re-granted the callee role's
mixins, `_permission` and `_skills`; each environment the callee role's mixins. Its hooks
and sessions are its own; a session the caller opened cannot be used by the callee.

`Hmz().flows.running()` lists every flow call currently running in this process (oldest
first), each with its ref, name, depth, start time, journal id, parent, task and whether it is
resumable ([SDK](/reference/sdk#flows)). A call adds no filesystem work, no task, and two stack
frames.

## Several flows in one module {#several-flows-in-one-file}

A module may define several `@flow`s with distinct `name`s; each is `<module>:<name>`.

```python
@flow(agents=Drafting, envs=Where, params=Idea, name="gen-idea")
async def gen_idea(task, *, agents, envs, params, ctx): ...

@flow(agents=Planning, envs=Where, params=Plan, name="gen-plan")
async def gen_plan(task, *, agents, envs, params, ctx): ...
```

- The bare module name means the flow named after the module; else the single non-hidden flow;
  else it is refused:

  ```console
  $ hmz exec -f humanize1 -b cost=5 "…"
  hmz exec: error: humanize1: ~/.humanize/flowverses/official/flows/humanize1 holds gen-idea, gen-plan, rlcr and none is called 'humanize1'; name one as humanize1:<flow>
  ```

- Lists show the flow a bare name means under the module name, and every other visible flow as
  `<module>:<name>`. `hidden=True` flows are not listed and still load by `<module>:<name>`.
- A module that fails to import is still listed, under its module name, with no description.
- The module docstring's first line is used as the description of the flow the bare name means
  when that flow has none.

## Where flows live {#where-flows-live}

A flow is either a **directory** with `__init__.py` or a **single `.py` file**. Where both
exist under one name, the directory wins. A single-file flow brings no skills.

```
my_loop/
├── __init__.py          the entry point
├── _prompts.py          imported by the entry point as `import _prompts`
└── skills/
    └── review-notes/
        └── SKILL.md
```

Names starting with `_`, and directories without `__init__.py`, are not flows.

**Resolution of `-f <name>` (and a bare `load` with no flow asking)**, first match wins:

| Order | Place | Directory |
| --- | --- | --- |
| 1 | `local` | `.humanize/flows/` under the current directory |
| 2 | `user` | `~/.humanize/flows/` (literally `~`, not `HUMANIZE_HOME`) |
| 3 | `official` | the package's `hmz/flows/builtin/`, then `~/.humanize/flowverses/official/flows/` |
| 4 | other flowverses | `~/.humanize/flowverses/<name>/flows/`, alphabetically |
| 5 | a path | `<name>/__init__.py`, `<name>`, `<name>.py` (`~` expanded) |

`<flowverse>/<flow>` looks in that flowverse only. A name nothing answers to raises
`FlowNotFound` (`<ref>: no flow is called '<name>', and it is not a path`); if an unfetched
flowverse could hold it, the message is
`<name>: the official flowverse has not been fetched yet -- open the flowverses page of /settings and fetch it from its own sheet`.

**Listed names.**

| Listed as | Is |
| --- | --- |
| `chat`, `rlar` | a flow of `official` (package or repository), bare |
| `theirs/rlar` | a flow of flowverse `theirs` |
| `local/chat` | this project's `.humanize/flows/chat` |
| `user/chat` | `~/.humanize/flows/chat` |

`-f` accepts either spelling; the TUI starts a flow by its listed name (`$local/twice`). What
`/flow` remembers is keyed by the listed name ([Settings](/reference/settings)).

**Forking.** `f` on a flow in `/flow`, and [`Hmz().flows.fork(name)`](/reference/sdk#flows),
copy the whole flow into `.humanize/flows/<name>` (or `into=`). A name already present in
either shape is refused (`ValueError`); a failed copy leaves nothing.

## Skills {#the-skills-a-flow-brings}

A flow directory's `skills/` holds one directory per skill, each with a `SKILL.md`. A role
names the skills its sessions carry in `_skills`.

```python
class Reviewer(Agent):
    _skills = ("review-notes", "https://github.com/humanfia/flowverse#writing-tests")
```

| Entry | Is |
| --- | --- |
| a name | `skills/<name>` in the flow's own directory |
| a string containing `#` or `://` | a git URL; `#<skill>` selects one skill from the repository's `skills/*`, without it every skill there |

- Skills are resolved once per run per role, when the flow is first called, before its first
  turn. Missing: `FlowDefinitionError`
  (`<ref>: '<role>' names the skill '<name>', and <dir>/skills has none of it`, or for a
  single-file flow `... and a flow that is one file has none of it`). Unfetchable, or no such
  skill in the repository:
  `<ref>: '<role>' names a skill that cannot be fetched: <reason>`.
- A repository is cloned into `~/.humanize/skills/<owner>-<repo>-<sha256(url)[:12]>` and
  fetched again (`fetch --depth 1` + `reset --hard`) the next time a run needs it; a failed
  re-fetch uses the existing copy.
- The flow's own skill wins a name also held by a repository.
- Skills are mounted where the harness reads a project's skills for the session's lifetime,
  then removed. Nothing is installed. A harness that reads no project skills carries none.
- [`derive(skills=…)`](#derive) narrows them for part of a flow.

## Flowverses {#flowverses}

A flowverse is a git repository with a `flows/` directory laid out as
[above](#where-flows-live). Nothing outside `flows/` is read.

| Flowverse | Location | Fetched | Removable |
| --- | --- | --- | --- |
| `official` | package `hmz/flows/builtin/` + clone of `https://github.com/humanfia/flowverse` at `~/.humanize/flowverses/official/` | clone on demand; in the background each time `hmz` starts | no |
| `local` | `.humanize/flows` (relative to the current directory) | never | no |
| `user` | `~/.humanize/flows` | never | no |
| any other | `~/.humanize/flowverses/<name>/` | clone on `add`; `fetch` refreshes | yes |

**Order.** Listed: `official`, others alphabetically, `local`, `user`. Looked up:
`local`, `user`, then the listed order.

| Operation | Behaviour | Errors |
| --- | --- | --- |
| add `<url>` [`<name>`] | `git clone --depth 1` into `.<name>.XXXXXXXX` beside the target, then renamed into place. `<url>` may be `owner/repo` (GitHub) unless a local path of that name exists. Name defaults to the repository name less `.git`. | `ValueError`: name not `[A-Za-z0-9][A-Za-z0-9._-]*`; `official`/`local`/`user`; already exists. `OSError`: git missing, clone failed (60 s timeout) |
| fetch `<name>` | Clone if never fetched; otherwise `git fetch --depth 1 origin HEAD` + `git reset --hard FETCH_HEAD` (local edits to tracked files are lost). | `ValueError`: unknown; `local`/`user`; a directory that is not a clone |
| remove `<name>` | Deletes the directory. | `ValueError` for the three fixed ones |

A stale half-clone `.<name>.*` older than 60 s is removed before the next clone of that name.
Where a flowverse came from is shown with any `user:password@` in its URL replaced by `***@`.
Managed on the [Flowverses page of `/settings`](/reference/tui#where-flows-come-from) and with
[`Hmz().verses`](/reference/sdk#flowverses).

::: warning A flowverse is code
Listing a flowverse imports the entry point of every flow in its `flows/`. Adding one trusts
that repository with this machine.
:::

### The flow in the package {#the-flow-in-the-package}

| Flow | Agent roles | Env roles | Budget | Grant |
| --- | --- | --- | --- | --- |
| [`chat`](/flows/chat) | `assistant: Agent`, `human: Outworlder` | `workspace: LocalEnv` | `Budget(cost=math.inf)` unless one is given | every mixin the harness serves |

`chat` opens one session and takes one turn per line the outworlder says; under `hmz exec`
(outworlder away) it takes the task as its one turn and returns. The first turn's failure ends
the run; later failures are reported and the conversation continues.

### The official flowverse {#the-official-flowverse}

[humanfia/flowverse](https://github.com/humanfia/flowverse), `flows/`. Every flow here also has
a `workspace: LocalEnv` role; `human` is an `Outworlder`. None declares a budget of its own.
Read [Security](/user/security) before running any.

| Flow | Agent roles | Roles need | Resumable |
| --- | --- | --- | :-: |
| [`ralph_loop`](/flows/ralph-loop) | `agent` | | ✓ |
| [`stateful_ralph`](/flows/stateful-ralph) | `agent` | | ✓ |
| [`continue_loop`](/flows/continue-loop) | `agent` | | ✓ |
| [`goal`](/flows/goal) | `worker` | `GoalCommandAgentMixin` | |
| [`flame_chase`](/flows/flame-chase) | `first_chaser`, `second_chaser` | | ✓ |
| [`rlar`](/flows/rlar) | `actor`, `reviewer` | | ✓ |
| [`humanize1:gen-idea`](/flows/humanize1) | `drafter` | | |
| [`humanize1:gen-plan`](/flows/humanize1) | `planner`, `analyst` | | |
| [`humanize1:rlcr`](/flows/humanize1) | `builder`, `reviewer`, `human` | `builder`: `PermissionRequestHookAgentMixin` | ✓ |
| [`parallel_flame_chase`](/flows/parallel-flame-chase) | `coordinator`, `lane_1_actor_a` … `lane_3_actor_b`, `human` | | ✓ |
| [`parallel_flame_chase_git_pr`](/flows/parallel-flame-chase-git-pr) | `orchestrator`, `lane_1_actor_a` … `lane_3_actor_b`, `human` | | ✓ |
| [`ralph_loop_agent_cleanup`](/flows/ralph-loop-agent-cleanup) | `agent`, `cleaner`, `human` | `SteeringAgentMixin` on both agents | ✓ |
| [`flame_chase_agent_cleanup`](/flows/flame-chase-agent-cleanup) | `first_chaser`, `second_chaser`, `cleaner`, `human` | `SteeringAgentMixin` on all three agents | ✓ |
| [`recursive_lean_prover`](/flows/recursive-lean-prover) | `worker`, `reviewer` | `worker`: `PermissionRequestHookAgentMixin` | ✓ |
| [`aot`](/flows/aot) | `writer`, `critic`, `human` | | |

## Command-line specs {#running-one}

```sh
hmz exec -f <flow> [-a <role>=<spec>[,…]]… [-e <role>=<spec>[,…]]… [-p <key>=<value>[,…]]…
         [-b <key>=<value>[,…]]… [-H <where>] [--resume] [--json] <task>
```

`-a`, `-e`, `-p` and `-b` may each be repeated; every occurrence is a comma list. A comma
separates items only where it is followed (after optional spaces) by `<key>=`, with `<key>`
matching `[A-Za-z_][\w-]*`; so `-p note=one,two` is one item. An empty item is refused
(`<flag> '<value>': an item is empty`). The same syntax is used by `/flow`, the settings
file, and `Hmz().run(agents={role: spec}, envs={role: spec})`. Every refusal below exits
`hmz exec` with status 2 before anything runs. Other flags: [CLI](/reference/cli#hmz-exec).

### `-a`: agents {#a-agents}

```
<role>=<cli>[@<provider>]/<model>:<effort>
```

| Part | Rule |
| --- | --- |
| `<role>` | A Python identifier; a role the flow declares that is not an `Outworlder`. |
| `<cli>` | A [`HarnessKind`](#harnesskind) value other than `acp`, or the name a CLI was added under on the Accounts page (then the harness is `acp`). |
| `<provider>` | An account of that CLI (see [Providers](/reference/providers)). Absent: the account the CLI is already signed into. |
| `<model>` | Everything between the first `/` and the last `:`; may contain `/` and `:`. Non-empty. |
| `<effort>` | After the last `:`. `auto` (or empty) means the CLI's default and is stored as `""`. The `:` is required. Valid words per CLI: [Agents](/reference/agents). |

| Input | Message |
| --- | --- |
| no `=`, or empty role | `-a '<item>': expected <role>=<harness>[@<provider>]/<model>:<effort>` |
| role not an identifier | ``-a '<item>': '<role>' is not a place a flow could declare: what is written before `=` is a field of the tuple of agents the flow declares, so it is a Python identifier`` |
| unknown CLI, empty model, or no `:` | `-a '<item>': expected [NAME=]CLI[@PROVIDER]/MODEL:EFFORT` |
| `@` with nothing after | `-a '<item>': expected an account after @, as in claude@deepseek/MODEL:EFFORT` |
| role twice | `-a: the role '<role>' is given twice` |
| role not declared | `<flow> has no agent role '<role>'; available roles are '<a>', '<b>'` |
| role is an `Outworlder` | `<flow>: '<role>' is assigned automatically by the runtime and cannot be set with -a` |
| harness lacks a declared mixin | `<flow>: '<role>' needs <Mixin>, which <harness> does not support` |
| role typed as another harness | `<flow>: '<role>' requires <harness>, but got <other>` |
| required role missing | `<flow> needs an agent for '<role>'; specify each with -a ROLE=CLI/MODEL:EFFORT` |
| effort, model or account the CLI cannot be configured at | `HarnessUnrecoverable`: `<spec>: <reason>` |
| an added CLI not added on this machine | `HarnessNotInstalled`: `<cli>: no such CLI has been added on this machine` |

### `-e`: environments {#e-environments}

```
<role>=<backend>[@<provider>][/<workdir>]
```

| Form | Is |
| --- | --- |
| `local@/abs/path` | a directory on this machine; `local` takes no provider |
| `ssh@<host>/abs/path` | a directory on a host: a stored environment provider's name, else a destination `ssh` resolves (`host`, `user@host`, an alias) |
| `ssh@<host>/~/path` | under the login's home there (the leading `/` before `~` is dropped) |
| `docker@<provider>/abs/path` | a container of its own on a stored docker provider's daemon (`local`: docker's default here); the path is on the daemon's host and is mounted at the same path |
| `ssh@<name>`, `docker@<name>` | the workdir the stored provider was saved with |

| Input | Message |
| --- | --- |
| no `/workdir` and no stored provider workdir, or not `<role>=…` | `-e '<item>': expected <role>=<backend>[@<provider>]/<workdir>` |
| role not an identifier | `-e '<item>': the role '<role>' is not an identifier` |
| unknown backend | `-e '<item>': '<backend>' is not a backend; one of local, ssh, docker` |
| `ssh` without host | `-e '<item>': ssh needs a host, as in ssh@host/workdir` |
| `docker` without provider | `-e '<item>': docker needs a host, as in docker@local/workdir` |
| `local` with provider | `-e '<item>': local takes no host, as in local@/workdir` |
| role twice | `-e: the role '<role>' is given twice` |
| role not declared | `<flow> has no environment role '<role>'; available roles are …` |
| role is a `LocalEnv` | `<flow>: '<role>' is the workspace the run started in and cannot be set with -e` |
| required role missing | `<flow> needs an environment for '<role>'; specify each with -e ROLE=BACKEND@PROVIDER/WORKDIR` |
| machine unreachable, workdir missing, mixin unsupported, resources short | refused when the run probes every environment, before the flow is called |

Machines and providers: [Machines](/reference/machines).

### `-p`: params {#p-params}

`<key>=<value>`; `<key>` matches `[A-Za-z_][\w-]*`; the value is the text after the first
`=`, unparsed until [validated](#flowparams).

| Input | Message |
| --- | --- |
| not `<key>=<value>` | `-p '<item>': expected <key>=<value>` |
| key twice | `-p: '<key>' is given twice` |
| does not validate | the `ParamsError` text |

### `-b`: budget {#b-budget}

Keys `duration`, `cost`, `output_tokens`, `graceful`, each at most once across all `-b`.

| Key | Accepted | Examples |
| --- | --- | --- |
| `duration` | seconds (`90`, `1.5`); units `w d h m s`, each at most once, decimals allowed (`1h30m`, `2d`, `1.5h`); ISO 8601 (`PT1H30M`); `HH:MM:SS`. Finite, ≥ 0. | `duration=6h` |
| `cost` | USD, optional leading `$`; `inf` for none; ≥ 0, not NaN | `cost=$20` |
| `output_tokens` | whole number, `_` ignored, suffix `k` (×1000) or `m` (×1 000 000), decimals allowed if the result is whole | `output_tokens=1.5m` |
| `graceful` | `1 true yes on` / `0 false no off` (case-insensitive) | `graceful=false` |

| Input | Message |
| --- | --- |
| unknown key | `-b '<item>': expected key=value where key is one of duration, cost, output_tokens, graceful` |
| key twice | `-b: duplicate key '<key>'` |
| bad duration | `-b duration: '<v>' is not a duration: use seconds, 1h30m, or ISO 8601 like PT1H30M`; `'<v>' names a unit twice`; `'<v>' is negative`; `'<v>' is not a valid duration: must be finite and not negative`; `duration '<v>' is too long` |
| bad cost | `-b cost: '<v>' is not a valid USD cost` |
| bad tokens | `-b output_tokens: '<v>' is not a valid token count: expected a number like 200000 or 200k`; `'<v>' must be a whole number of tokens` |
| bad graceful | `-b graceful: '<v>' must be true or false` |
| no limit set | `-b: Value error, a budget sets at least one of duration, cost, output_tokens` |
| no `-b` for a flow that needs one | `<flow> requires a budget: specify with -b duration=...,cost=...,output_tokens=...` |

### `-H`: harness placement {#harness-placement}

<span id="h-harness"></span>Where each agent's **harness** (its CLI and the process
supervising it) runs, relative to the machine its environment's work is on. Given once; the
last `-H` wins. Stored per flow in the [settings](/reference/settings) as written, `""` for
`adaptive`.

| Value | Harness of a session whose work is **here** | Harness of a session whose work is **on another machine** (`ssh`, `docker`) |
| --- | --- | --- |
| `adaptive` (default) | here | on the environment's machine, natively, if all hold: no `on_pre_tool_use`/`on_permission_request` hook hung when the session opens (an `on_ask_user` hook does not keep it here); the CLI is on that machine's `PATH`; for a fenced session, that machine can hold the fence. Otherwise here, anchored to the machine. |
| `local` | here | here, anchored to the machine (turns' tools land there) |
| `env` | here | on the environment's machine, natively; refused where the CLI is missing or the fence cannot be held |
| `standalone:<machine>` | on `<machine>`, acting on the work through the anchor | on `<machine>`, acting on the work through the anchor; only for a role whose permission is every scope `ALL` |

`<machine>` is written as `-e` writes a spec after `<role>=`: `ssh@gpu-box/~/scratch`,
`docker@gpubox/srv/scratch`, or the bare name of a stored environment provider (ssh first, then
docker). A missing workdir defaults to the provider's own, else `~` for `ssh`, else
`$HUMANIZE_HOME/harness` for `docker@local`. The standalone machine is opened as an
environment of its own, probed before the flow is called, and closed with the run.

**Probing.** Placement is settled once per agent role and machine. "The CLI is there" is
asked by running `/bin/sh -c 'command -v -- "$1" || command -v -- "$2" || exit 69'` with the
CLI's program and its basename down the same connection a native turn uses (300 s limit;
stopped with the run). Whether the machine can hold a fence is asked once per kind of fence
(network cut or not) in the anchor handshake.

| Condition | Refusal |
| --- | --- |
| `-H` not one of the four | `-H '<v>': expected adaptive, local, env or standalone:<backend>@<provider>[/<workdir>]` |
| `standalone:` naming this machine | `-H '<v>': a standalone harness runs on another machine; -H local runs it on this one` |
| `standalone:` spec invalid | `-H '<v>': <why>`, e.g. `'bogus' is not a backend; one of ssh, docker`, `no environment provider is saved as '<name>'; …` ([CLI](/reference/cli#choosing-where-the-harness-runs)) |
| `standalone`: role not granted everything | `HarnessSandboxed`: `<role>=<spec>: <AgentClass>: a fence cannot hold a harness that runs on another machine` |
| `env`: CLI missing | `HarnessNotInstalled`: `<cli> is not installed on <backend>@<provider>: <install hint> there, or run its harness here with -H local` |
| `env`: fence not holdable | `HarnessSandboxed`: `<backend>@<provider> cannot fence the agent to its permission: it needs Landlock; grant the agent everything, or run its harness here with -H local` |
| `env`: machine did not answer | `HarnessUnrecoverable`: `<backend>@<provider> did not say within 300s whether <cli> is there` (or `could not be asked whether <cli> is there: <reason>`) |

The `env` and `standalone` refusals are checked for every agent against every environment
(the workspace included) once the environments are probed, before the flow is called, so a
run refuses as a line to correct rather than failing at a session; a session opened later
(a callee's, under a narrower permission) is still refused as it opens. Under `adaptive`
those conditions fall back to "here" instead of refusing. Where each session's
harness went is recorded in the epic (`opened.harness`: `local`, `env`,
`standalone:<target>`), for sessions whose work was on another machine.

### Command-line refusals {#command-line-refusals}

The runner refuses, before any agent starts, with the messages in the tables above, and also:

| Condition | Message |
| --- | --- |
| duplicate role across forms | `<flow>: duplicate agent role '<role>'` / `duplicate environment role` |
| a flow that will not load | the `FlowNotFound` / `FlowRefError` / `FlowDefinitionError` / `FlowLoadConflict` text |
| `--resume` refusals | see [Resumable flows](#a-flow-that-can-be-picked-up) |

In the TUI, `/flow` asks the same questions and remembers the answers per workspace and flow
([Settings](/reference/settings)). From Python, [`Hmz().run`](/reference/sdk#hmz-run) takes the
same specs as mappings.

## Stopping {#stopping}

A run ends when the top flow returns or raises. From outside:

| Means | Effect |
| --- | --- |
| a budget | see [Enforcement](#effective-budget) |
| <kbd>ctrl+c</kbd> | once under `hmz exec`; twice in the TUI |
| [`Run.stop()`](/reference/sdk#run) | from any thread |

A stop cancels the flow at its current `await`: the turn under way is interrupted, `finally`
blocks run, `TaskGroup`s cancel their children. On the way out every session is closed and
every copy and scratch directory removed (kept, with the journal, for a resumable run). The
epic records `ended.how` = `stopped` for a stop from outside or a spent budget.

## Errors {#when-something-goes-wrong}

Every exception the flow API raises derives from `FlowException`, in three branches:

```
FlowException
├── FlowRuntimeError                  humanize refused something, or a budget ran out
│   ├── FlowNotFound · FlowRefError (ValueError) · FlowDefinitionError · FlowLoadConflict
│   ├── RequirementError              what was given does not meet the declaration; nothing ran
│   │   └── MissingRole · CapabilityMissing · PermissionTooNarrow · ResourceUnmet · HarnessMismatch
│   ├── CapabilityNotGranted          used what the role did not declare
│   ├── ParamsError (ValueError) · FlowDepthExceeded (RecursionError)
│   ├── BudgetExceeded
│   │   └── DurationExceeded (TimeoutError) · CostExceeded · OutputTokensExceeded
│   └── FlowCancelled · StateNotSerializable (TypeError) · OutworlderAway
├── HarnessError                      a coding agent CLI could not take the turn
│   └── HarnessNotInstalled · HarnessContended · HarnessThrottled · HarnessRefused
│       ModelUnavailable · HarnessMissing · HarnessSandboxed · HarnessKilled · HarnessDropped
│       HarnessUnrecoverable · OutputSchemaError (ValueError) · SessionError · UnsupportedOperation
└── EnvError                          an environment could not do what it was asked
    └── EnvUnavailable · EnvConnectionError (ConnectionError) · EnvCommandTimeout (TimeoutError)
        EnvFileNotFound (FileNotFoundError) · EnvPermissionDenied (PermissionError)
        WorktreeError · TempCloneBusy · ScratchError · RewindError
```

- Where a builtin names the failure the leaf also derives from it: `except TimeoutError`
  catches `EnvCommandTimeout` and `DurationExceeded`.
- Every class takes its message as its only argument, so each pickles and crosses a process
  boundary as itself. A called flow's exception is never wrapped.
- An exception from the flow's own code (a `KeyError`) is not converted.
- `HarnessThrottled` and `HarnessDropped` are transient; `BudgetExceeded`, `HarnessRefused`
  and `ModelUnavailable` recur on retry.

| Class | Bases | Raised when |
| --- | --- | --- |
| <code id="flowexception">FlowException</code> | `Exception` | root |
| <code id="flowruntimeerror">FlowRuntimeError</code> | `FlowException` | humanize refused something, or a limit ran out; also a flow called outside a run |
| <code id="flownotfound">FlowNotFound</code> | `FlowRuntimeError` | a ref names no flow; a `git+` repository cannot be fetched |
| <code id="flowreferror">FlowRefError</code> | `FlowRuntimeError`, `ValueError` | a ref is malformed, or relative with nothing to be relative to |
| <code id="flowdefinitionerror">FlowDefinitionError</code> | `FlowRuntimeError` | a flow is written wrong ([tables](#flow)); its module fails to import; a skill a role names is missing |
| <code id="flowloadconflict">FlowLoadConflict</code> | `FlowRuntimeError` | importing would replace a module a running run uses |
| <code id="requirementerror">RequirementError</code> | `FlowRuntimeError` | what was given does not meet the declaration; nothing ran. Raised directly for a role the flow does not declare, a runtime-filled role given, or an object the run did not hand out |
| <code id="missingrole">MissingRole</code> | `RequirementError` | a required role was not given |
| <code id="capabilitymissing">CapabilityMissing</code> | `RequirementError` | an agent or environment lacks a declared mixin (including `GitEnvMixin` on a machine without git), a `LocalEnv` given another machine, an outworlder given for a role it cannot fill |
| <code id="permissiontoonarrow">PermissionTooNarrow</code> | `RequirementError` | an agent's permission does not cover its role's |
| <code id="resourceunmet">ResourceUnmet</code> | `RequirementError` | a machine has fewer CPUs/GPUs or less memory than declared, or a docker provider has not that much left |
| <code id="harnessmismatch">HarnessMismatch</code> | `RequirementError` | a harness-protocol role got another harness |
| <code id="capabilitynotgranted">CapabilityNotGranted</code> | `FlowRuntimeError` | an operation the role did not declare; widening a grant with `derive`; `on_outworlder_run` on an outworlder not from `new()` |
| <code id="paramserror">ParamsError</code> | `FlowRuntimeError`, `ValueError` | params do not validate |
| <code id="flowdepthexceeded">FlowDepthExceeded</code> | `FlowRuntimeError`, `RecursionError` | a call would be 65 deep |
| <code id="budgetexceeded">BudgetExceeded</code> | `FlowRuntimeError` | a budget of this call or one above is spent; sticky |
| <code id="durationexceeded">DurationExceeded</code> | `BudgetExceeded`, `TimeoutError` | `duration` elapsed |
| <code id="costexceeded">CostExceeded</code> | `BudgetExceeded` | `cost` spent |
| <code id="outputtokensexceeded">OutputTokensExceeded</code> | `BudgetExceeded` | `output_tokens` spent |
| <code id="flowcancelled">FlowCancelled</code> | `FlowRuntimeError` | the run, or a caller above, has ended while this call still runs |
| <code id="statenotserializable">StateNotSerializable</code> | `FlowRuntimeError`, `TypeError` | a `ctx.state` key is not a `str`, or a value is not JSON-serializable |
| <code id="outworlderaway">OutworlderAway</code> | `FlowRuntimeError` | an away outworlder was asked for a schema with a field without default |
| <code id="harnesserror">HarnessError</code> | `FlowException` | a CLI could not take a turn or do what was asked |
| <code id="harnessnotinstalled">HarnessNotInstalled</code> | `HarnessError` | the CLI (or its SDK) is not installed where its harness runs; a command that exits 127 |
| <code id="harnesscontended">HarnessContended</code> | `HarnessError` | two turns reached one local store of the CLI at once, and this one lost |
| <code id="harnessthrottled">HarnessThrottled</code> | `HarnessError` | rate limit or spent quota |
| <code id="harnessrefused">HarnessRefused</code> | `HarnessError` | the provider refused the credential |
| <code id="modelunavailable">ModelUnavailable</code> | `HarnessError` | the model is not served to this account, retired, or unknown |
| <code id="harnessmissing">HarnessMissing</code> | `HarnessError` | the CLI would not start |
| <code id="harnesssandboxed">HarnessSandboxed</code> | `HarnessError` | the fence cannot be held (by the CLI or the machine) |
| <code id="harnesskilled">HarnessKilled</code> | `HarnessError` | the CLI died mid-turn (signal, OOM) |
| <code id="harnessdropped">HarnessDropped</code> | `HarnessError` | the connection to the CLI or provider broke mid-turn; any `OSError` from a turn |
| <code id="harnessunrecoverable">HarnessUnrecoverable</code> | `HarnessError` | any other failure no retry would change; a CLI that cannot be configured as asked |
| <code id="outputschemaerror">OutputSchemaError</code> | `HarnessError`, `ValueError` | the answer is not the `output_schema` |
| <code id="sessionerror">SessionError</code> | `HarnessError` | a session is closed, another agent's, busy, not taking a turn to steer, interrupted, not forkable yet, or its prompt was blocked by a hook |
| <code id="unsupportedoperation">UnsupportedOperation</code> | `HarnessError` | the harness cannot do this at all (fork; fork elsewhere; outworlder fork or steer) |
| <code id="enverror">EnvError</code> | `FlowException` | an environment could not do what it was asked |
| <code id="envunavailable">EnvUnavailable</code> | `EnvError` | the machine is gone or the workdir does not exist |
| <code id="envconnectionerror">EnvConnectionError</code> | `EnvError`, `ConnectionError` | the connection to a remote environment failed |
| <code id="envcommandtimeout">EnvCommandTimeout</code> | `EnvError`, `TimeoutError` | `exec` ran past its `timeout` and was killed |
| <code id="envfilenotfound">EnvFileNotFound</code> | `EnvError`, `FileNotFoundError` | `read` of a missing file |
| <code id="envpermissiondenied">EnvPermissionDenied</code> | `EnvError`, `PermissionError` | a read, write or command refused for want of permission |
| <code id="worktreeerror">WorktreeError</code> | `EnvError` | `derive_worktree` failed |
| <code id="tempclonebusy">TempCloneBusy</code> | `EnvError` | `derive_temp_clone` of an id another environment holds |
| <code id="scratcherror">ScratchError</code> | `EnvError` | a scratch directory could not be made or removed |
| <code id="rewinderror">RewindError</code> | `EnvError` | `snapshot`, `rewind` or `snapshots` failed |

How a failed CLI turn maps to a leaf: the fault coganchor classifies is mapped
`contended → HarnessContended`, `throttled → HarnessThrottled`, `refused → HarnessRefused`,
`unlisted`/`retired → ModelUnavailable`, `missing → HarnessMissing` (`HarnessNotInstalled` when
the exit status is 127), `sandboxed → HarnessSandboxed`, `killed → HarnessKilled`,
`dropped → HarnessDropped`, anything else (`unmirrored` among them) `HarnessUnrecoverable`. A turn stopped by the
driver is `SessionError`.

## Testing a flow {#testing-a-flow}

`hmz.sdk.fakes` (import as `from hmz.sdk import fakes`; the dotted `hmz.sdk.fakes` is not
importable) runs a flow through the real engine over in-memory drivers: no CLI, no machine, no
tokens, no waiting. Guide: [Testing a flow](/weaver/testing-flows).

```python
from hmz.flows import Budget, CostExceeded
from hmz.sdk import fakes

async def test_held_to_budget():
    agent = fakes.FakeAgentDriver(cost=1.0)
    with pytest.raises(CostExceeded):
        await fakes.run_fake("my_loop", "go", agents={"agent": agent}, budget=Budget(cost=2.5))
    assert len(agent.prompts) == 3
```

### `run_fake` {#run-fake}

```python
async def run_fake(
    flow: Flow | str, task: str = "", *,
    agents: Mapping[str, AgentDriver | OutworlderDriver | Reply] | None = None,
    envs: Mapping[str, EnvDriver | Mapping[str, bytes | str]] | None = None,
    params: FlowParams | Mapping[str, Any] | None = None,
    budget: Budget | None = None,
    outworlder: OutworlderDriver | None = None,
    local: EnvDriver | None = None,
    journal: Path | None = None,
    resume: bool = False,
    recorder: Recorder | None = None,
) -> Any
```

| Parameter | Default | Meaning |
| --- | --- | --- |
| `flow` | | A `Flow`, or a ref loaded relative to the caller as [`load`](#load) does. |
| `task` | `""` | The task. |
| `agents` | `None` | Per role: a driver, or a [`Reply`](#fakeagentdriver) for a `FakeAgentDriver`. An omitted required role gets a fake of the harness its type names (Claude Code otherwise) replying `"ok"`. A reply given for an `Outworlder` role makes the run's outworlder. |
| `envs` | `None` | Per role: a driver, or the initial files of a `FakeEnvDriver`. An omitted role gets an empty one large enough for its declared resources. |
| `params` | defaults | Params or a mapping. |
| `budget` | unlimited | The run's budget. |
| `outworlder` | an away one | Fills `Outworlder` roles. |
| `local` | `FakeEnvDriver(workdir="/here")` | Fills `LocalEnv` roles. |
| `journal` | `None` | Path of a resumable flow's journal. |
| `resume` | `False` | Pick up `journal`. |
| `recorder` | `None` | <Badge type="info" text="internal" /> Receives `entered(call)`, `left(call, error)`, `spawned(call, role, session, driver)`, optionally `began`, `named`, `closed`. |

Returns the flow's return value. A `NotRequired` role nobody gave is omitted. Fake turns report
the spending they are told to, so budgets, usage and sticky exhaustion behave as in a real run.

### `FakeAgentDriver` {#fakeagentdriver}

```python
FakeAgentDriver(harness: HarnessKind | str = "claude", *, reply: Reply = None,
                model: str = "fake", effort: str = "", provider: str = "",
                capabilities: Iterable[type] | None = None, cost: float = 0.0,
                output_tokens: int = 1, seconds: float = 0.0, forks: bool = True,
                names_late: bool = False)
```

| Parameter | Meaning |
| --- | --- |
| `harness` | Which harness; serves that harness's mixins unless `capabilities` is given. |
| `reply` | One answer for every turn; a list consumed one per turn; or a function `(prompt, *, output_schema, session)`, sync or async. An answer is text, a pydantic model, or a mapping or JSON text validated into the schema asked for. `None` or an exhausted list answers `"ok"` or the schema's defaults. |
| `model`, `effort`, `provider` | Reported identity. |
| `capabilities` | Mixins served, overriding the harness's. |
| `cost`, `output_tokens`, `seconds` | Reported per answer; nothing waits. |
| `forks` | Whether it can fork; unlike a real harness it also forks a session with no turn. |
| `names_late` | Sessions have no id until their first turn starts. |

| Attribute | |
| --- | --- |
| `prompts` | Every prompt any session was given, including hook context and `STOP` reasons. |
| `sessions` | Every [`FakeSession`](#fakesession), in order. |
| `live`, `peak` | Sessions open now; the most open at once. |
| `closed` | How many times the driver was closed. |

### `FakeSession` {#fakesession}

Passed to a reply function as `session=`. Each turn fires `SESSION_START` (first turn),
`USER_PROMPT_SUBMIT` and `STOP`; closing fires `SESSION_END`; a blocking `STOP` continues the
turn.

| Method | Fires |
| --- | --- |
| `await tool(name, input=None) -> bool` | `PRE_TOOL_USE`, then `PERMISSION_REQUEST` where served. Returns whether the tool would run. |
| `await ask(question, options=()) -> str \| None` | `ASK_USER`; returns the answer. `UnsupportedOperation` where `AskUserHookAgentMixin` is not served. |
| `await notify(message)` | `NOTIFICATION`. |
| `await subagent(name, task="", said="") -> str` | `SUBAGENT_START`, `SUBAGENT_STOP` where served. |
| `await until_steered() -> str` | Waits for a `steer` and returns it. |

Attributes: `prompts`, `requests`, `steered` (prompt, queued), `tools` (name, input, ran),
`forked_from`, `permission`, `skills`, `closed`, `id`, `usage`.

::: warning `until_steered()` waits indefinitely
Give such a test a hard deadline:
`budget=Budget(duration=timedelta(seconds=5), graceful=False)`.
:::

### `FakeEnvDriver` {#fakeenvdriver}

```python
FakeEnvDriver(files: Mapping[str, bytes | str] | None = None, *,
              workdir: str | PurePosixPath = "/work", backend: EnvBackendKind | str = "local",
              provider: str = "", capabilities: Iterable[type] | None = None,
              cpu_count: int = 8, memory: int = 64 << 30, gpu_count: int = 0,
              gpu_memory: int = 0, run: Handler = None,
              refs: Iterable[str] = ("HEAD", "main"), repo: bool = True)
```

| Parameter | Meaning |
| --- | --- |
| `files` | Initial workdir contents by relative path; text written as UTF-8. |
| `workdir`, `backend`, `provider` | Reported location. |
| `capabilities` | Mixins served; all by default. |
| `cpu_count`, `memory`, `gpu_count`, `gpu_memory` | Reported machine. |
| `run` | Answers `exec`: a table from command (argv tuple or script string) to `(status, stdout, stderr)`, or a function `(command, env)` (sync or async) returning a triple or `None` to fall through. |
| `refs` | Refs `derive_worktree` knows. |
| `repo` | Whether the workdir is a git repository. |

Defaults for unhandled commands: `true`, `false`, `echo`, `cat`, `ls`, `sleep N` and
`git rev-parse --is-inside-work-tree` behave as expected; any other program or script returns
status 127.

| Attribute | |
| --- | --- |
| `files` | Current workdir contents by relative path. |
| `text(path)` | One file as text. |
| `machine` | Every file on the fake machine by absolute path. |
| `commands` | Every command run in this workdir, in order. |
| `clones`, `scratches` | Ids of copies and scratch directories not yet removed. |

### `FakeOutworlder` {#fakeoutworlder}

```python
FakeOutworlder(reply: Reply = None, *, away: bool = False)
```

Answers like a `FakeAgentDriver` (a function receives `output_schema=`), or is away.
`asked` lists every prompt it was asked.

<style>
.harness-matrix table {
  font-size: 13px;
}
.harness-matrix th,
.harness-matrix td {
  padding: 6px 8px;
}
</style>

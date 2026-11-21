---
title: Flow API
description: Look up every public name of hmz.flows, with its signature and what it means.
---

# Flow API

Import everything a flow needs from `hmz.flows`. This page lists every public name in the package. To learn how to use them, start at [Anatomy of a flow](/builder/flow).

```python
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext
from hmz.flows import FlowParams, LocalEnv, ShellEnvMixin, flow


class Workspace(LocalEnv, ShellEnvMixin): ...


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    workspace: Workspace


class Params(FlowParams):
    rounds: int = 3


@flow(agents=Agents, envs=Envs, params=Params)
async def ralph(task, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext):
    coder, workspace = agents["coder"], envs["workspace"]
    session = await coder.spawn()
    for _ in range(params.rounds):
        await coder.run(task, session=session, env=workspace)
```

Most names here are type-checker protocols. At run time, the runtime passes objects that match these protocols. You get only what you declare: using an undeclared capability raises `CapabilityNotGranted`.

## Define a flow

Guides: [Anatomy of a flow](/builder/flow), [Params](/builder/params), [Call another flow](/builder/calling-flows), [Resumable flows](/builder/resumable).

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

def load(ref: str) -> Flow
```

| Name | Meaning |
| --- | --- |
| `flow` | Decorator that turns an async function into a flow. Raises `FlowDefinitionError` if the function or its declarations are invalid. |
| `load` | Returns the flow named by a ref, ready to call. Raises `FlowRefError`, `FlowNotFound`, `FlowLoadConflict` or `FlowDefinitionError`. |
| `FlowFn` | The function `flow` decorates: `async def fn(task, *, agents, envs, params, ctx)`. |
| `Flow` | A callable flow, returned by `flow` and `load`. |
| `FlowParams` | Pydantic base model for flow parameters. Subclass it with one field per parameter. Undeclared keys are refused. |
| `FlowContext` | Information about the current flow call, passed as `ctx`. |
| `FlowState` | State a resumable flow keeps across runs: a mapping of JSON-serializable values saved on every write. |

Arguments of `flow`:

| Argument | Default | Meaning |
| --- | --- | --- |
| `agents` | required | Required agents, as an `AgentCollection` subclass. |
| `envs` | required | Required environments, as an `EnvCollection` subclass. |
| `params` | required | Configuration parameters, as a `FlowParams` subclass. |
| `name` | `None` | Name in its module, used after the colon in a ref. `None` uses the function name. |
| `description` | `None` | One-line summary. `None` uses the first line of the docstring. |
| `hidden` | `False` | Hide from interactive flow lists. You can still run and load it by ref. |
| `resumable` | `False` | Allow resuming an interrupted run. Provides a `FlowState`. |

Refs that `load` takes:

| Ref | Names |
| --- | --- |
| `:<subflow>` | A flow in the caller's module. |
| `<flow>`, `<flow>:<subflow>` | A sibling flow. The bare form loads the flow named after the directory, or the single visible flow in it. |
| `<user>/<flow>`, `<user>/<flow>:<subflow>` | A flow under that GitHub user in the official flowverse (or in an installed flow's own flowverse). |
| `<pip-style-vcs-url>[#<subdir>][:<subflow>]` | A flow in a repository, at its root or in the directory after `#`. Example: `git+https://github.com/humanfia/humanize1-flow@v0.1.0#humanize1:rlcr`. |

### Flow

```python
class Flow(Protocol):
    description: str | None
    expected_agents: type[AgentCollection]
    expected_envs: type[EnvCollection]
    expected_params: type[FlowParams]
    resumable: bool

    async def __call__(
        self,
        task: str,
        *,
        agents: AgentCollection,
        envs: EnvCollection,
        params: FlowParams,
        budget: Budget | None = None,
    ) -> Any
```

| Member | Meaning |
| --- | --- |
| `description` | One-line summary, or `None`. |
| `expected_agents` | Declared agents. |
| `expected_envs` | Declared environments. |
| `expected_params` | Declared parameters. |
| `resumable` | Whether an interrupted run can resume. |
| `__call__` | Calls the flow from another flow and returns its result. `params` is an instance of its `FlowParams` subclass. `budget` adds a call-specific limit on top of the caller's remaining budget. |

Passed roles must cover what the flow declares. You may omit an `Outworlder` or `LocalEnv` role to pass the caller's own. The call raises `RequirementError` (before anything runs), `ParamsError`, `FlowDepthExceeded` (beyond 64 nested calls), or any exception the flow raises, unwrapped. When a resumable flow resumes, a flow it calls resumes too if called with the same task, agents, environments and params.

### FlowContext

| Property | Type | Meaning |
| --- | --- | --- |
| `budget` | `Budget` | Active budget for this call: the tighter of its own and its caller's. |
| `flow` | `Flow` | The flow being called. |
| `resumed` | `bool` | Whether this call resumes an earlier run. |
| `state` | `FlowState` or `None` | State kept across runs, or `None` if the flow is not resumable. |
| `usage` | `Usage` | Total usage of this call and its child calls so far. |

### FlowState

| Operation | Meaning |
| --- | --- |
| `state[key]` | Returns the value under `key`, or raises `KeyError`. |
| `state[key] = value` | Saves `value` under `key`. Raises `StateNotSerializable` if not JSON-serializable. |
| `del state[key]` | Deletes `key`, or raises `KeyError`. |
| `key in state` | Whether `key` exists in `state`. |

## Agents

Guides: [Agent roles](/builder/agents), [Sessions and turns](/builder/turns), [Branch a conversation](/builder/branching).

| Name | Meaning |
| --- | --- |
| `AgentCollection` | `TypedDict` base class for declaring agent roles. Mark optional roles `NotRequired`. |
| `Agent` | A coding agent passed to the flow. |
| `Session` | One conversation with one agent. Holds message history, not a working directory. |
| `Outworlder` | The human user as an agent role. See [The person](#the-person). |
| `HarnessKind` | String enum of coding agent CLIs. |
| `HARNESS_AGENTS` | Mapping from each `HarnessKind` to its harness-typed role class. |

### Agent

```python
class Agent(Protocol):
    _permission: ClassVar[Permission] = Permission()
    _skills: ClassVar[tuple[str, ...]] = ()
    _tools: ClassVar[tuple[FakeTool, ...]] = ()
    _clis: ClassVar[tuple[FakeCli, ...]] = ()

    effort: str
    harness: HarnessKind
    model: str
    role: str
    provider: str

    async def spawn(self) -> Session
    async def run(
        self,
        prompt: str,
        *,
        session: Session,
        env: Env | None = None,
        output_schema: type[BaseModel] = ...,
        budget: Budget | None = None,
    ) -> str | BaseModel
    async def fork(self, session: Session) -> Session
    def derive(
        self,
        *,
        permission: Permission | None = None,
        skills: tuple[str, ...] | None = None,
    ) -> Self

    def on_session_start(self, fn: HookFn | None) -> None
    def on_user_prompt_submit(self, fn: HookFn | None) -> None
    def on_pre_tool_use(self, fn: HookFn | None) -> None
    def on_notification(self, fn: HookFn | None) -> None
    def on_stop(self, fn: HookFn | None) -> None
    def on_session_end(self, fn: HookFn | None) -> None
```

Class attributes set on a role:

| Attribute | Meaning |
| --- | --- |
| `_permission` | Access required by the role. The supplied agent must grant at least this, and sessions run with this exact permission. |
| `_skills` | Skills given to the role's sessions: a skill name in the flow's `skills/` directory, or a git URL ending in `#<skill>`. |
| `_tools` | Flow functions exposed as tools (`FakeTool`). Requires `FakeToolAgentMixin`. |
| `_clis` | Flow CLIs (`FakeCli`) placed on the agent's PATH. Needs no mixin. Not supported on `litellm` agents. |

Properties and methods:

| Member | Meaning |
| --- | --- |
| `effort` | Thinking effort level, in the harness's terms. |
| `harness` | The agent's CLI kind. |
| `model` | The model name. |
| `role` | Role key in the flow's `AgentCollection`. |
| `provider` | Account the turns run under, or `""` for the local CLI login. |
| `spawn` | Opens a new session. The CLI process starts on the first turn. |
| `run` | Runs one turn in `session` and returns the agent's text response, or an `output_schema` instance if given. `env` sets the working environment (`None` uses the run workspace). `budget` caps this turn within the flow's budget. |
| `fork` | Returns a new session branched from `session`, leaving the original untouched. Raises `SessionError` if `session` belongs to another agent, has ended, or has no turns. |
| `derive` | Returns a copy of the agent narrowed to a stricter permission or a subset of skills. Raises `CapabilityNotGranted` if either widens the grant. |
| `on_session_start`, `on_user_prompt_submit`, `on_pre_tool_use`, `on_notification`, `on_stop`, `on_session_end` | Registers a hook for all sessions of this agent, replacing any previous hook for that event. Pass `None` to remove it. See [Hooks](#hooks). |

`run` raises `CapabilityNotGranted` if you use `/goal` or `/loop` without its mixin, `BudgetExceeded` when a budget runs out, `SessionError` if the session belongs to another agent or has ended, `UnsupportedOperation` if the harness cannot move the conversation to `env`, or `HarnessError` if the turn fails.

### Session

| Property | Type | Meaning |
| --- | --- | --- |
| `agent` | `Agent` | The agent that owns this session. |
| `usage` | `Usage` | Cumulative usage across this session's turns. |

Sessions close automatically when the flow call that opened them ends, or when garbage-collected.

### Agent mixins

Subclass these mixins on a role to request extra capabilities.

| Mixin | Grants |
| --- | --- |
| `FakeToolAgentMixin` | Setting `_tools` on the role. |
| `GoalCommandAgentMixin` | Passing `/goal <objective>` to `run`, letting the harness loop until it meets the goal. |
| `LoopCommandAgentMixin` | Passing `/loop <interval> <task>` to `run` for recurring harness tasks. |
| `SteeringAgentMixin` | Calling `steer` to inject a prompt into a running turn. |
| `PermissionRequestHookAgentMixin` | `on_permission_request`: approve or deny tool execution requests. |
| `SubagentStartHookAgentMixin` | `on_subagent_start`: observe subagent launches. |
| `SubagentStopHookAgentMixin` | `on_subagent_stop`: observe subagent completion and optionally continue it. |
| `AskUserHookAgentMixin` | `on_ask_user`: answer mid-turn questions from the agent. |

```python
async def steer(self, prompt: str, *, session: Session, queued: bool = True) -> None
```

With `queued=True`, the agent reads the prompt at its next check and continues. With `queued=False`, the turn interrupts immediately and resumes from the new prompt. Raises `SessionError` if `session` is not mid-turn.

### Harness-typed roles

Use a harness-typed role to require a specific CLI and all mixins in its row. Passing a different harness raises `HarnessMismatch`. Mixin names below omit the `AgentMixin` suffix.

| Type | `HarnessKind` | Value | Mixins |
| --- | --- | --- | --- |
| `ClaudeCodeAgent` | `CLAUDE` | `claude` | `FakeTool`, `GoalCommand`, `LoopCommand`, `Steering`, `PermissionRequestHook`, `SubagentStartHook`, `SubagentStopHook`, `AskUserHook` |
| `CodexAgent` | `CODEX` | `codex` | `FakeTool`, `GoalCommand`, `Steering`, `PermissionRequestHook`, `SubagentStartHook`, `SubagentStopHook`, `AskUserHook` |
| `CursorAgent` | `CURSOR_AGENT` | `cursor-agent` | `SubagentStartHook`, `SubagentStopHook` |
| `OpenCodeAgent` | `OPENCODE` | `opencode` | `FakeTool` |
| `MiMoCodeAgent` | `MIMO` | `mimo` | `FakeTool` |
| `MiniMaxCodeAgent` | `MCODE` | `mcode` | `SubagentStartHook`, `SubagentStopHook` |
| `QwenCodeAgent` | `QWEN` | `qwen` | `FakeTool` |
| `KimiCodeAgent` | `KIMI` | `kimi` | `GoalCommand`, `Steering`, `PermissionRequestHook`, `AskUserHook` |
| `GrokBuildAgent` | `GROK` | `grok` | `FakeTool` |
| `PiAgent` | `PI` | `pi` | `FakeTool`, `Steering`, `AskUserHook` |
| `OhMyPiAgent` | `OMP` | `omp` | `FakeTool`, `Steering`, `AskUserHook` |
| `AntigravityAgent` | `AGY` | `agy` | `FakeTool` |
| `DeepSeekHarnessAgent` | `DSH` | `dsh` | `FakeTool`, `GoalCommand` |
| `LiteLLMAgent` | `LITELLM` | `litellm` | None. Direct model call with no CLI or tools; `env` on turns must be `None`. |
| `Agent` | `ACP` | `acp` | None. Custom CLI driven over the Agent Client Protocol. |

When a `GrokBuildAgent` role declares `_tools`, using `output_schema`, taking the first turn of a fork, disabling web search, or using a permission that writes nothing raises `HarnessUnrecoverable`.

## Permissions

Guide: [Skills and permissions](/builder/skills).

```python
class Permission:
    preset: str = "workspace-write"
    network: bool = True
    granular: tuple[Rule, ...] = ()

    rules: tuple[Rule, ...]
    def access(self, path: str) -> Access
    def covers(self, other: Permission) -> bool

class Rule:
    path: str
    access: Access

def allow(path: str) -> Rule
def read_only(path: str) -> Rule
def deny(path: str) -> Rule
```

| Name | Meaning |
| --- | --- |
| `Permission` | Frozen filesystem and network policy: a preset, a network flag, and path rules. Defaults to writing the workdir, reading the machine, and allowing network access. |
| `PRESETS` | Valid preset names: `("read-only", "workspace-write", "danger-full-access")`. |
| `Rule` | Frozen access rule for a path and its subtree. |
| `Access` | String enum ordered `NONE < READ < WRITE` (`none`, `read`, `write`). |
| `allow` | Creates a read-write rule for `path`. |
| `read_only` | Creates a read-only rule for `path`. |
| `deny` | Creates a no-access rule for `path`. |

| Preset | Base rules |
| --- | --- |
| `read-only` | Read the whole machine. |
| `workspace-write` | Read the whole machine and write the workdir. |
| `danger-full-access` | Write everything. |

| Member of `Permission` | Meaning |
| --- | --- |
| `preset` | One of `PRESETS`, or raises `ValueError`. |
| `network` | Whether the agent may use the network, including built-in web search and fetch. |
| `granular` | Path rules applied after the preset, in order. |
| `rules` | Preset rules followed by `granular`. The last matching rule wins; unmatched paths get no access. |
| `access` | Returns the effective `Access` for `path`. |
| `covers` | Whether this permission grants at least what `other` grants across all paths and network. |

Rule paths must be `/abs`, `~`, `~/...`, `.` or `./...`, where `~` is the harness user's home directory and `.` is the session workdir. Globs, `..`, or unanchored paths raise `ValueError`, from `Rule` and from `Permission.access`. Write access to the workdir also grants write access to temporary directories.

## Budgets and usage

Guide: [Budgets in a flow](/builder/budgets).

```python
class Budget(BaseModel):
    duration: timedelta | None = None
    cost: float | None = None
    output_tokens: int | None = None
    graceful: bool | Graceful = True

    graces: Graceful

class Graceful(BaseModel):
    duration: bool = True
    cost: bool = True
    output_tokens: bool = True

class Usage(BaseModel):
    duration: timedelta = timedelta(0)
    cost: float = 0.0
    output_tokens: int = 0
```

| Name | Meaning |
| --- | --- |
| `Budget` | Frozen spending limits for a run, flow call, or turn. Must set at least one non-negative limit, or Pydantic raises `ValidationError`. |
| `Graceful` | Frozen flags controlling whether reaching a limit waits for the current turn to finish (`True`) or aborts it immediately (`False`). |
| `Usage` | Frozen record of resources spent so far. |

| Field | Meaning |
| --- | --- |
| `duration` | Wall-clock time limit in `Budget`; active agent turn time in `Usage`. |
| `cost` | Cost in USD. Use `Budget(cost=math.inf)` for unlimited. |
| `output_tokens` | Output tokens allowed or spent. |
| `graceful` | A single boolean for all limits, or a `Graceful` instance. |
| `graces` | `graceful` normalized to a `Graceful` instance. |

## Environments

Guides: [Environment roles](/builder/environments), [Worktrees, clones and scratch](/builder/worktrees), [Machines and moving sessions](/builder/machines).

| Name | Meaning |
| --- | --- |
| `EnvCollection` | `TypedDict` base class for declaring environment roles. Mark optional roles `NotRequired`. |
| `Env` | A working directory on a machine. |
| `LocalEnv` | An `Env` bound automatically to the run's starting workspace. Cannot be passed with `-e`. |
| `EnvBackendKind` | String enum of machine backends. |
| `SequenceNotStr` | A sequence of strings (excluding `str` itself) used for argument lists. |

### Env

```python
class Env(Protocol):
    available: bool
    backend: EnvBackendKind
    provider: str
    role: str
    workdir: PurePosixPath

    async def derive_subdir(self, *, subdir: PurePosixPath | str) -> Env
```

| Member | Meaning |
| --- | --- |
| `available` | Whether the machine was reachable and the workdir existed when last checked. |
| `backend` | Machine backend kind. |
| `provider` | Backend target: SSH host, container runtime, or `""` for local. |
| `role` | Role key in the flow's `EnvCollection`. |
| `workdir` | Working directory path (absolute or `~/...`). |
| `derive_subdir` | Returns an `Env` on the same machine at `subdir` inside `workdir`, creating the directory if needed. Raises `ValueError` if `subdir` is absolute or escapes `workdir`, or `EnvError` if creation fails. |

| `EnvBackendKind` | Value | Machine |
| --- | --- | --- |
| `LOCAL` | `local` | This machine. |
| `SSH` | `ssh` | Remote machine over SSH. |
| `DOCKER` | `docker` | Dedicated container on a Docker daemon. |
| `SWARM` | `swarm` | Dedicated container on a Docker Swarm. |
| `APPLE_CONTAINER` | `apple-container` | Dedicated container run by Apple's `container` on macOS. |
| `SLURM` | `slurm` | Dedicated job on a Slurm cluster. |

### Environment mixins that grant methods

```python
class ShellEnvMixin(Protocol):
    async def exec(self, argv: SequenceNotStr[str], *, timeout: float = 0) -> tuple[int, str, str]

class BashEnvMixin(ShellEnvMixin, Protocol):
    async def exec(self, script: str, *, timeout: float = 0) -> tuple[int, str, str]

class FilesEnvMixin(Protocol):
    async def read(self, path: str) -> bytes
    async def write(self, path: str, data: bytes) -> None

class GitWorktreeEnvMixin(Protocol):
    async def derive_worktree(
        self, *, ref: str | None = None, dir: PurePosixPath | str | None = None
    ) -> Self

class RewindableEnvMixin(Protocol):
    async def snapshot(self, name: str | None = None) -> str
    async def rewind(self, ref: str) -> None
    async def snapshots(self) -> list[str]

class GitEnvMixin(RewindableEnvMixin, Protocol): ...

class TemporaryClonedDirEnvMixin(Protocol):
    async def derive_temp_clone(self, id: str) -> Self
    async def destroy_temp_clone(self, id: str) -> None

class ScratchDirEnvMixin(Protocol):
    async def derive_scratch(self, id: str) -> Self
    async def destroy_scratch(self, id: str) -> None
```

| Mixin | Method | Meaning |
| --- | --- | --- |
| `ShellEnvMixin` | `exec` | Runs one program directly in `workdir` without a shell and returns exit status, stdout, and stderr. `timeout` is in seconds (`0` means no limit). Raises `EnvCommandTimeout` or `EnvError`. |
| `BashEnvMixin` | `exec` | Also accepts a script string to run via `bash -c`. Requires `bash` on the machine. A string `exec` on a role without this mixin raises `CapabilityNotGranted`. |
| `FilesEnvMixin` | `read` | Reads file bytes at a relative or absolute `path`. Raises `EnvFileNotFound` or `EnvPermissionDenied`. |
| `FilesEnvMixin` | `write` | Writes bytes to `path`, creating parent directories. Raises `EnvPermissionDenied`. |
| `GitWorktreeEnvMixin` | `derive_worktree` | Returns an environment in a new git worktree detached at `ref` (`None` uses current HEAD) in `dir` (`None` uses a fresh directory). Requires `git`. Raises `WorktreeError`. |
| `RewindableEnvMixin` | `snapshot`, `rewind`, `snapshots` | Interface implemented by `GitEnvMixin`. Declare `GitEnvMixin` on roles. |
| `GitEnvMixin` | `snapshot` | Saves the working tree (including untracked files) as a commit under `refs/hmz/snapshots/<name>` without changing HEAD, and returns the ref. Raises `RewindError`. |
| `GitEnvMixin` | `rewind` | Restores the working tree to match a snapshot or commit ref, as `git reset --hard` and `git clean` would. Raises `RewindError`. |
| `GitEnvMixin` | `snapshots` | Lists saved snapshot refs from oldest to newest, shared across all worktrees of the repo. |
| `TemporaryClonedDirEnvMixin` | `derive_temp_clone` | Returns an environment in a temporary copy of `workdir` keyed by `id`. Raises `TempCloneBusy` if another environment holds `id`. |
| `TemporaryClonedDirEnvMixin` | `destroy_temp_clone` | Deletes the temporary copy for `id` and frees the ID. |
| `ScratchDirEnvMixin` | `derive_scratch` | Returns an environment in an empty directory beside `workdir` keyed by `id`. Raises `ScratchError`. |
| `ScratchDirEnvMixin` | `destroy_scratch` | Deletes the scratch directory for `id`. Raises `ScratchError`. |

Temporary clones and scratch directories are deleted when the flow that created them ends, unless the flow is resumable. `GitEnvMixin` ignores git-ignored files and any top-level `.hmz/` directory. Declaring `BashEnvMixin`, `GitWorktreeEnvMixin`, or `GitEnvMixin` on a machine without the required binary raises `CapabilityMissing` before the flow starts.

### Environment mixins that declare requirements

Set these class attributes on a role. A machine with fewer CPUs, GPUs or less memory than declared raises `ResourceUnmet`.

| Mixin | Attribute | Default | Meaning |
| --- | --- | --- | --- |
| `CPUEnvMixin` | `_cpu_count` | `1` | Minimum logical CPUs. |
| `MemoryEnvMixin` | `_memory` | `0` | Minimum RAM in bytes. |
| `GPUEnvMixin` | `_gpu_count` | `1` | Minimum GPUs. |
| `GPUEnvMixin` | `_gpu_memory` | `0` | Minimum VRAM per GPU in bytes. |
| `ImageEnvMixin` | `_image` | `""` | Container image as taken by `docker run` (`""` uses the provider default, or `python:3.12-slim`). Must provide `/bin/sh` and Python 3.12+. Docker, Swarm, and Apple container environments only. |

## Hooks

Guide: [Hooks](/builder/hooks).

A hook is an async function that takes a moment's params and returns its result for every session of the agent. Returning a default-constructed result makes no changes. Raising an exception fails the flow.

| Name | Meaning |
| --- | --- |
| `HookFn` | Hook signature: `async def hook(params) -> result`. |
| `HookKind` | String enum of hook events (lowercase values like `pre_tool_use`). |
| `HookParams` | Base class for hook inputs. Always includes `ctx` (`FlowContext`) and `session` (`Session`). |
| `HookResult` | Base class for hook outputs. |
| `HOOK_TYPES` | Mapping from each `HookKind` to its params and result classes. |

All params and result classes are frozen, keyword-only dataclasses. Every params class includes `ctx` and `session`.

| `HookKind` | Hung with | Params class and fields | Result class and fields |
| --- | --- | --- | --- |
| `SESSION_START` | `Agent.on_session_start` | `SessionStartHookParams` | `SessionStartHookResult`: `context: str = ""` (prepended before the first prompt). |
| `USER_PROMPT_SUBMIT` | `Agent.on_user_prompt_submit` | `UserPromptSubmitHookParams`: `prompt: str` | `UserPromptSubmitHookResult`: `block: bool = False` (rejects the prompt and makes `run` raise `SessionError` with `reason: str = ""`), `context: str = ""` (appended to the prompt). |
| `PRE_TOOL_USE` | `Agent.on_pre_tool_use` | `PreToolUseHookParams`: `tool: str`, `input: Mapping[str, Any] = {}` | `PreToolUseHookResult`: `block: bool = False` (skips the tool and sends `reason: str = ""` to the agent). |
| `PERMISSION_REQUEST` | `on_permission_request` of `PermissionRequestHookAgentMixin` | `PermissionRequestHookParams`: `tool: str`, `input: Mapping[str, Any] = {}` | `PermissionRequestHookResult`: `allow: bool = True`, `reason: str = ""`. |
| `NOTIFICATION` | `Agent.on_notification` | `NotificationHookParams`: `message: str` | `NotificationHookResult`: no fields. |
| `STOP` | `Agent.on_stop` | `StopHookParams`: `said: str` (final message), `again: int = 0` (times a stop hook has already continued this turn). | `StopHookResult`: `block: bool = False` (continues the turn using `reason: str = ""` as the next prompt; an empty `reason` does not block). |
| `SESSION_END` | `Agent.on_session_end` | `SessionEndHookParams` | `SessionEndHookResult`: no fields. |
| `SUBAGENT_START` | `on_subagent_start` of `SubagentStartHookAgentMixin` | `SubagentStartHookParams`: `subagent: str`, `task: str = ""` | `SubagentStartHookResult`: `context: str = ""` (prepended to the subagent). |
| `SUBAGENT_STOP` | `on_subagent_stop` of `SubagentStopHookAgentMixin` | `SubagentStopHookParams`: `subagent: str`, `said: str = ""` | `SubagentStopHookResult`: `block: bool = False` (continues the subagent with `reason: str = ""` as its next prompt). |
| `ASK_USER` | `on_ask_user` of `AskUserHookAgentMixin` | `AskUserHookParams`: `question: str`, `options: tuple[str, ...] = ()` | `AskUserHookResult`: `answer: str \| None = None` (`None` leaves it unanswered). |
| `OUTWORLDER_RUN` | `Outworlder.on_outworlder_run` | `OutworlderRunHookParams`: `prompt: str`, `output_schema` (Pydantic model class, or `None` for text; default `None`), `context: tuple[Block, ...] = ()`, `face` (`Face`, or `None` for the form; default `None`) | `OutworlderRunHookResult`: `output` (required string or schema instance). |

## The person

Guides: [The person as an agent](/builder/outworlder), [Faces](/builder/faces).

```python
class Outworlder(Agent, Protocol):
    away: bool

    @classmethod
    def new(cls) -> Self
    async def spawn(self, *, face: Face | None = None) -> Session
    async def run(
        self,
        prompt: str,
        *,
        session: Session,
        env: Env | None = None,
        output_schema: type[BaseModel] = ...,
        budget: Budget | None = None,
        context: Sequence[Block] = (),
    ) -> str | BaseModel
    async def show(self, context: Sequence[Block], *, session: Session) -> None
    def on_outworlder_run(self, fn: HookFn | None) -> None
```

The runtime fills `Outworlder` roles automatically (never via `-a`). In a top-level flow, it represents the person who started the run.

| Member | Meaning |
| --- | --- |
| `away` | `True` when no one can answer (`/afk` is active or running under `hmz exec`). |
| `new` | Creates a virtual outworlder answered by the flow via `on_outworlder_run`. Starts `away` until a hook is set. |
| `spawn` | Opens a session. `face` sets a custom web UI page for questions (`None` renders a form from `output_schema`). |
| `run` | Asks the person a question alongside `context` and returns the text or `output_schema` response. |
| `show` | Displays `context` blocks without waiting for an answer. No-op when `away` or on a `new` outworlder. Raises `SessionError` if `session` is not one of this outworlder's. |
| `on_outworlder_run` | Registers the hook that answers `run` calls on a `new` outworlder. |

When `away`, `run` returns immediately: `""` for text prompts, a default-constructed model if every `output_schema` field has a default, or raises `OutworlderAway`.

### Context blocks

Every block is a frozen, keyword-only dataclass with `title: str = ""` and an `as_json()` serialization method. `Block` is the union of all seven types.

| Block | Fields | Shown as |
| --- | --- | --- |
| `Markdown` | `text: str` | Rendered Markdown. |
| `Code` | `text: str`, `language: str = ""` | Syntax-highlighted source code. |
| `Diff` | `patch: str` | Per-file unified diff. |
| `Table` | `columns: tuple[str, ...]`, `rows: tuple[tuple[Any, ...], ...]` | Table. Raises `ValueError` if a row length mismatches the columns. |
| `Image` | `data: bytes`, `mime: str`, `alt: str = ""` | Image up to 4 MiB where `mime` starts with `image/`, or raises `ValueError`. |
| `Json` | `value: Any` | Collapsible JSON tree. |
| `Chart` | `spec: Mapping[str, Any]` | Vega-Lite chart with inline `data.values`. |

### Face

```python
class Face:
    def __init__(self, html: str, title: str = "") -> None
    html: str
    title: str
    hash: str

    @classmethod
    def html(cls, text: str, /, *, title: str = "") -> Face
    @classmethod
    def file(cls, path: str | Path, *, title: str = "") -> Face
    @classmethod
    async def design(
        cls,
        agent: Agent,
        *,
        session: Session,
        about: str,
        output_schema: type[BaseModel] | None = None,
        env: Env | None = None,
    ) -> Face
```

| Name | Meaning |
| --- | --- |
| `Face` | Frozen, self-contained HTML page used to prompt an outworlder. |
| `Face.html` | Class method: builds a `Face` from an HTML string. Instance attribute: the HTML string. |
| `Face.file` | Reads an HTML file immediately (relative to the caller's module). Raises `OSError`. |
| `Face.design` | Runs one turn in `session` asking `agent` to build a face for `about` following `FACE_GUIDE`. Raises `ValueError` if no HTML is produced. |
| `title` | Page title, or `""`. |
| `hash` | Hex SHA-256 of its HTML. |
| `FACE_GUIDE` | Markdown specification for authoring faces, including the `window.hmz` bridge and an example. |

## Tools

Guide: [Tools the agent can call](/builder/tools).

```python
class FakeTool:
    name: str
    about: str
    call: Callable[..., Any]
    takes: type[BaseModel] | None = None

    def schema(self) -> dict[str, Any]
    def called(self, given: Mapping[str, Any]) -> str

class FakeCommand:
    name: str
    about: str
    call: Callable[..., Any]
    takes: type[BaseModel] | None = None

class FakeCli:
    name: str
    about: str
    commands: tuple[FakeCommand, ...]

    def run(self, argv: Sequence[str]) -> tuple[int, str, str]
```

| Name | Meaning |
| --- | --- |
| `FakeTool` | Flow function exposed as an agent tool via `_tools`. |
| `FakeCommand` | Subcommand of a `FakeCli`. |
| `FakeCli` | Flow-defined CLI placed on the agent's PATH via `_clis`. |

| Member | Meaning |
| --- | --- |
| `name` | Tool name, subcommand name, or executable filename (must be a plain filename for `FakeCli`, or raises `ValueError`). |
| `about` | One-sentence description shown to the model (for tools) or in `--help` (for CLIs). |
| `call` | Sync or async handler. Takes a `takes` instance, or no arguments if `takes` is `None`. |
| `takes` | Pydantic model for arguments, or `None`. In `FakeCommand`, fields become `--flag` options (required if no default; `--flag/--no-flag` for booleans). |
| `commands` | Non-empty tuple of uniquely named `FakeCommand` items, or raises `ValueError`. |
| `FakeTool.schema` | JSON Schema sent to the agent. |
| `FakeTool.called` | Validates the input, runs `call`, and formats the return value as a string. |
| `FakeCli.run` | Parses arguments, runs the matching subcommand, and returns exit status, stdout, and stderr. |

For a `FakeTool`, `call` returns strings as-is, `None` as `done`, and other values as JSON; exceptions report a tool error to the agent without stopping the turn. For a `FakeCommand`, strings print as-is, `None` prints nothing, and other values print as JSON; raising `SystemExit` uses its exit code, and other exceptions exit with `1`.

## Errors

Guide: [Context, errors and cleanup](/builder/context).

All flow exceptions inherit from `FlowException` and take a single message argument. Exceptions from child flows propagate unwrapped. Classes also inherit from matching Python builtins where applicable.

### Runtime errors

| Class | Base | Raised when |
| --- | --- | --- |
| `FlowException` | `Exception` | Base class for all flow API exceptions. |
| `FlowRuntimeError` | `FlowException` | Base class for runtime refusals and limit violations. |
| `FlowNotFound` | `FlowRuntimeError` | `load` could not find the target flow. |
| `FlowRefError` | `FlowRuntimeError`, `ValueError` | `load` received an invalid ref, or a relative ref outside a flow. |
| `FlowDefinitionError` | `FlowRuntimeError` | A flow definition is invalid. |
| `FlowLoadConflict` | `FlowRuntimeError` | `load` would overwrite a module already imported by another flow in the run. |
| `RequirementError` | `FlowRuntimeError` | Supplied agents or environments do not meet role declarations (raised before execution). |
| `MissingRole` | `RequirementError` | A required role was not supplied. |
| `CapabilityMissing` | `RequirementError` | A supplied agent or environment lacks a declared mixin. |
| `PermissionTooNarrow` | `RequirementError` | A supplied agent has a narrower `Permission` than the role declares. |
| `ResourceUnmet` | `RequirementError` | An environment has fewer CPUs, GPUs, or memory than declared. |
| `HarnessMismatch` | `RequirementError` | An agent's harness does not match its harness-typed role. |
| `CapabilityNotGranted` | `FlowRuntimeError` | The flow used a capability its role did not declare. |
| `ParamsError` | `FlowRuntimeError`, `ValueError` | Parameters failed validation against the `FlowParams` subclass. |
| `FlowDepthExceeded` | `FlowRuntimeError`, `RecursionError` | Nested flow calls exceeded the maximum depth. |
| `BudgetExceeded` | `FlowRuntimeError` | A turn or flow budget was exhausted. Once a flow's budget is spent, every later turn raises again. `own` is `True` if only the turn's own `budget` expired, allowing the flow to continue. |
| `DurationExceeded` | `BudgetExceeded`, `TimeoutError` | Budget `duration` elapsed. |
| `CostExceeded` | `BudgetExceeded` | Budget `cost` was spent. |
| `OutputTokensExceeded` | `BudgetExceeded` | Budget `output_tokens` were spent. |
| `FlowCancelled` | `FlowRuntimeError` | The run was cancelled externally. |
| `StateNotSerializable` | `FlowRuntimeError`, `TypeError` | A value assigned to `FlowState` is not JSON-serializable. |
| `OutworlderAway` | `FlowRuntimeError` | The outworlder is away and the prompt has no default answer. |

### Harness errors

| Class | Base | Raised when |
| --- | --- | --- |
| `HarnessError` | `FlowException` | Base class for coding agent CLI failures. |
| `HarnessNotInstalled` | `HarnessError` | The CLI or its SDK is missing on the target machine. |
| `HarnessContended` | `HarnessError` | Concurrent turns collided on the CLI's local state store. |
| `HarnessThrottled` | `HarnessError` | The provider rate-limited the request or exhausted quota. |
| `HarnessRefused` | `HarnessError` | Credentials are missing, expired, or revoked. |
| `ModelUnavailable` | `HarnessError` | The requested model does not exist, is retired, or is not available to the account. |
| `HarnessMissing` | `HarnessError` | The CLI process failed to start. |
| `HarnessSandboxed` | `HarnessError` | The CLI could not initialize its local sandbox. |
| `HarnessKilled` | `HarnessError` | The CLI process died mid-turn. |
| `HarnessDropped` | `HarnessError` | Connection to the CLI or provider dropped mid-turn. |
| `HarnessUnrecoverable` | `HarnessError` | The turn failed with a non-retryable error. |
| `OutputSchemaError` | `HarnessError`, `ValueError` | The agent's output did not match `output_schema`. |
| `SessionError` | `HarnessError` | The session is invalid, ended, or misused. |
| `UnsupportedOperation` | `HarnessError` | The harness does not support the requested operation. |

### Environment errors

| Class | Base | Raised when |
| --- | --- | --- |
| `EnvError` | `FlowException` | Base class for environment failures. |
| `EnvUnavailable` | `EnvError` | The machine is unreachable or `workdir` is missing. |
| `EnvConnectionError` | `EnvError`, `ConnectionError` | Connection to a remote environment failed or dropped. |
| `EnvCommandTimeout` | `EnvError`, `TimeoutError` | `exec` exceeded `timeout` and was killed. Partial output is on `stdout` and `stderr`. |
| `EnvFileNotFound` | `EnvError`, `FileNotFoundError` | `read` target does not exist. |
| `EnvPermissionDenied` | `EnvError`, `PermissionError` | The environment refused a read, a write or a command. |
| `WorktreeError` | `EnvError` | `derive_worktree` failed (not a git repo, bad ref, or target directory exists). |
| `TempCloneBusy` | `EnvError` | `derive_temp_clone` was called with an `id` already in use. |
| `ScratchError` | `EnvError` | Creating or removing a scratch directory failed. |
| `RewindError` | `EnvError` | `snapshot` or `rewind` failed. |

# Flows

`hmz.flows` is everything a flow imports: the decorator, the types its agents, environments
and params are declared with, the hook types, and every exception it can catch. This page is
every name in it, plus how humanize finds, runs and tests a flow.

::: code-group

```python [.humanize/flows/twice/__init__.py]
"""Two passes: do the work, then read it back and fix what is wrong."""

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)


class Agents(AgentCollection):
    builder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def twice(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Two passes: do the work, then read it back and fix what is wrong."""
    builder = agents["builder"]
    session = await builder.spawn(env=envs["workspace"])
    await builder.run(task, session=session)
    await builder.run(
        "Now review what you just did, and fix anything that is wrong.",
        session=session,
    )
```

```sh [run it]
hmz exec -f twice -a builder=claude/claude-opus-5:high -b cost=5 \
    "add a --dry-run flag to calc.py"
```

```python [test it]
from hmz.sdk import fakes


async def test_twice_reads_its_own_work_back():
    builder = fakes.FakeAgentDriver(reply="done")
    await fakes.run_fake("twice", "fix the build", agents={"builder": builder})
    assert builder.prompts == [
        "fix the build",
        "Now review what you just did, and fix anything that is wrong.",
    ]
```

:::

New to flows? Start with [Writing a flow](/weaver/writing-a-flow). The shapes a loop usually
takes are in [Loops](/weaver/loops).

## Every name {#what-a-flow-drives}

All of these import from `hmz.flows`.

| Group | Names |
| --- | --- |
| Defining a flow | [`flow`](#flow), [`Flow`](#flow-protocol), [`FlowFn`](#flowfn), [`load`](#load), [`FlowParams`](#flowparams), [`FlowContext`](#flowcontext), [`FlowState`](#flowstate) |
| Agents | [`AgentCollection`](#agentcollection), [`Agent`](#agent), [`Session`](#session), [`Outworlder`](#outworlder), [`HarnessKind`](#harnesskind), [`HARNESS_AGENTS`](#harness-agents) and the twelve harness protocols, from [`ClaudeCodeAgent`](#what-each-harness-serves) to `DeepSeekHarnessAgent` |
| Agent mixins | [`GoalCommandAgentMixin`, `LoopCommandAgentMixin`, `SteeringAgentMixin`, `PermissionRequestHookAgentMixin`, `SubagentStartHookAgentMixin`, `SubagentStopHookAgentMixin`, `AskUserHookAgentMixin`](#asking-for-an-agent-that-can-do-something) |
| Permissions | [`Permission`](#permission), [`PermissionKind`](#permissionkind) |
| Budgets | [`Budget`](#budget), [`Usage`](#usage) |
| Environments | [`EnvCollection`](#envcollection), [`Env`](#env), [`LocalEnv`](#localenv), [`EnvBackendKind`](#envbackendkind), [`SequenceNotStr`](#sequencenotstr) |
| Environment mixins | [`ShellEnvMixin`, `BashEnvMixin`, `FilesEnvMixin`](#what-an-environment-can-do), [`GitWorktreeEnvMixin`, `TemporaryClonedDirEnvMixin`, `ScratchDirEnvMixin`](#worktrees-copies-and-scratch-directories), [`CPUEnvMixin`, `MemoryEnvMixin`, `GPUEnvMixin`](#what-a-machine-must-have) |
| Hooks | [`HookKind`](#hookkind), [`HookFn`](#hookfn), [`HookParams`, `HookResult`](#hookparams-and-hookresult), [`HOOK_TYPES`](#hook-types), and a [`<Moment>HookParams` and `<Moment>HookResult`](#hooks-in-a-flow) pair per moment |
| Errors | [`FlowException`](#when-something-goes-wrong) and the 44 classes under it |

**Agents, environments, sessions and the context are protocols**, not base classes. At run
time a flow is handed the runtime's own object for each role, granted exactly what the role
declared. Anything else raises [`CapabilityNotGranted`](#capabilitynotgranted), whatever the
harness or machine underneath could do. A type checker catches most of those first, because
the protocol a role is typed as has no such method.

::: tip Stable and internal
`hmz.flows` and [`hmz.sdk`](/reference/sdk) are the stable surfaces. Everything under
`hmz.runtime` (the engine that finds, loads and runs flows, the drivers, the module the fakes
are written in) is **internal** and may change in any release. Importing `hmz.flows` costs
pydantic and nothing of humanize's own.
:::

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

| Parameter | |
| --- | --- |
| `agents` | The agent roles: an [`AgentCollection`](#agentcollection) subclass, one key per role. |
| `envs` | The environment roles: an [`EnvCollection`](#envcollection) subclass, one key per role. |
| `params` | A [`FlowParams`](#flowparams) subclass, or `FlowParams` itself for a flow that takes none. |
| `name` | What the flow is called in its module: the part of a [ref](#refs) after the colon. Letters, digits, `_`, `.` and `-`. The function's name by default. |
| `description` | One line, shown where flows are listed. The first line of the docstring by default. |
| `hidden` | Leave it out of every list and of `/flow`. It is still run and [loaded](#load) by its ref. |
| `resumable` | A run of it [can be picked up](#a-flow-that-can-be-picked-up) where it stopped, and it gets a `ctx.state`. |

Returns the decorator, which answers with a [`Flow`](#flow-protocol).

Raises `FlowDefinitionError` as the decorator runs, for:

- a function that is not `async def`: ``sync: a flow is an `async def` function``;
- one that does not take `task` and the keywords `agents`, `envs`, `params` and `ctx`;
- `agents` or `envs` that is not an `AgentCollection` or `EnvCollection` subclass, or `params`
  that is not a `FlowParams` subclass;
- a name no ref could spell:
  ``'a b' is not a flow name: letters, digits, `_`, `.` and `-` ``;
- two flows of one name in one module.

The collections' annotations are read the first time the flow is called or described, not
when the decorator runs. So `from __future__ import annotations`, string annotations and
collections declared inside a function all work, and a role typed as something no agent or
environment can be (`builder: int`) is refused only then. `NotRequired`, `Required`,
`ReadOnly` and `Annotated` are read through.

```python
@flow(agents=Planning, envs=Where, params=Plan, name="plan",
      description="Turns a draft into a plan.", resumable=True)
async def draft_to_plan(task, *, agents: Planning, envs: Where, params: Plan,
                        ctx: FlowContext):
    ...
```

### `FlowFn` {#flowfn}

```python
class FlowFn(Protocol):
    async def __call__(
        self, task: str, *, agents: TAgents, envs: TEnvs, params: TParams, ctx: FlowContext
    ) -> Any: ...
```

The function `flow` decorates. What it returns is what its caller gets back: a calling flow,
[`Run.result`](/reference/sdk#run), or [`run_fake`](#run-fake).

### `Flow` {#flow-protocol}

What `@flow` and [`load`](#load) answer: a flow, ready to be called.

| Member | |
| --- | --- |
| `description: str \| None` | The line it says about itself, or `None`. |
| `expected_agents: type[AgentCollection]` | The agent roles it declares. |
| `expected_envs: type[EnvCollection]` | The environment roles it declares. |
| `expected_params: type[FlowParams]` | Its params model. |
| `resumable: bool` | Whether a run of it can be picked up. |
| `await flow(task, *, agents, envs, params, budget=None)` | Runs it from inside another flow. See [Calling another flow](#calling-a-flow). |

```python
review = load(":review")
if review.resumable:
    ...
verdict = await review(task, agents={"reviewer": agents["coder"]}, envs={},
                       params=review.expected_params())
```

## Agent roles {#how-many-agents-and-what-they-are-for}

### `AgentCollection` {#agentcollection}

```python
class AgentCollection(TypedDict, extra_items=ReadOnly[Agent]): ...
```

Subclass it with one key per role, each typed as what that role must be able to do.

```python
from typing import NotRequired

from hmz.flows import Agent, AgentCollection, Outworlder


class Agents(AgentCollection):
    actor: Agent
    reviewer: Agent
    second_opinion: NotRequired[Agent]
    human: Outworlder
```

- **The key is the role's name everywhere.** `-a reviewer=…` fills it, `/flow` asks what *the
  reviewer* runs, a [trace](/reference/tracing) groups its sessions under `reviewer`, and what
  each role was set to run is remembered per role.
- **`NotRequired`** is a role whoever runs the flow may leave out. `"second_opinion" in
  agents` says whether it was given.
- **A required role left out** is refused before anything starts: `MissingRole` from a
  calling flow or `run_fake`, and from `hmz exec`
  `rlar needs an agent for 'reviewer'; give each with -a ROLE=CLI/MODEL:EFFORT`.
- **A role typed `Outworlder`** is [the person at the prompt](#the-person-at-the-prompt).
  The runtime fills it, and `-a` naming it is refused.

### `Agent` {#agent}

```python
class Agent(Protocol):
    _permission: ClassVar[Permission] = Permission()
    _skills: ClassVar[tuple[str, ...]] = ()

    role: str             # read-only properties
    harness: HarnessKind
    model: str
    effort: str
    provider: str

    async def spawn(self, *, env: Env) -> Session: ...
    async def run(self, prompt: str, *, session: Session,
                  output_schema: type[M] | None = None, budget: Budget | None = None) -> str | M: ...
    async def fork(self, session: Session, *, env: Env) -> Session: ...
    def derive(self, *, permission: Permission | None = None,
               skills: tuple[str, ...] | None = None) -> Self: ...
    def on_session_start(self, fn: HookFn | None) -> None: ...   # and five more on_*
```

What every harness can do. Subclass it, adding
[mixins](#asking-for-an-agent-that-can-do-something) for anything only some harnesses can do,
and setting the two class attributes to shape the role.

| Class attribute | |
| --- | --- |
| `_permission` | What the role's sessions may touch. See [Permissions](#what-each-agent-may-do). |
| `_skills` | Which skills its sessions carry. See [Skills](#the-skills-a-flow-brings). |

| Property | |
| --- | --- |
| `role` | The key it fills in the flow's `AgentCollection`. |
| `harness` | Which CLI it is, as a [`HarnessKind`](#harnesskind). |
| `model` | The model it runs. |
| `effort` | How hard the model is asked to think, in the harness's own words. |
| `provider` | The account its turns run as, or `""` for the one this machine's CLI is signed into. |

| Method | |
| --- | --- |
| [`spawn`](#spawn), [`run`](#run), [`fork`](#fork) | Open a session, take a turn in it, branch it. |
| [`derive`](#derive) | The same agent, narrowed. |
| `on_session_start`, `on_user_prompt_submit`, `on_pre_tool_use`, `on_notification`, `on_stop`, `on_session_end` | Hang a [hook](#hooks-in-a-flow) on every session of this agent. |

```python
from hmz.flows import Agent, Permission, PermissionKind


class Reviewer(Agent):
    """Reads, and writes nothing."""

    _permission = Permission(local=PermissionKind.READ)
    _skills = ("review-notes",)
```

### `HarnessKind` {#harnesskind}

`class HarnessKind(StrEnum)`: which CLI an agent is, by the name `-a` gives it.

| Value | CLI | | Value | CLI |
| --- | --- | --- | --- | --- |
| `claude` | Claude Code | | `kimi` | Kimi Code |
| `codex` | Codex | | `grok` | Grok Build |
| `cursor-agent` | Cursor Agent | | `pi` | pi |
| `opencode` | opencode | | `zcode` | ZCode |
| `mimo` | MiMo Code | | `agy` | Antigravity |
| `qwen` | Qwen Code | | `dsh` | DeepSeek Harness |
| `acp` | a CLI added at `/providers`, driven over the Agent Client Protocol | | | |

## Asking for an agent that can do something {#asking-for-an-agent-that-can-do-something}

A role that needs something only some harnesses can do says so by subclassing a mixin:

```python
from hmz.flows import Agent, AgentCollection, GoalCommandAgentMixin
from hmz.flows import PermissionRequestHookAgentMixin


class Builder(Agent, GoalCommandAgentMixin, PermissionRequestHookAgentMixin):
    """Pursues the task as its own goal, and has its tool requests put to the flow."""


class Agents(AgentCollection):
    builder: Builder
    reviewer: Agent
```

| Mixin | Lets the flow |
| --- | --- |
| `GoalCommandAgentMixin` | [`run`](#run) a prompt starting `/goal <objective>`: the harness's own goal feature keeps going until it decides the objective is met. See [Goals](/weaver/goals). |
| `LoopCommandAgentMixin` | `run` a prompt starting `/loop <interval> <task>`, the harness's own recurring task. |
| `SteeringAgentMixin` | [`steer`](#steer) a turn while it runs. |
| `PermissionRequestHookAgentMixin` | Hang `on_permission_request`: answer the harness asking whether a tool may run. |
| `SubagentStartHookAgentMixin` | Hang `on_subagent_start`: hear of the agent starting a subagent. |
| `SubagentStopHookAgentMixin` | Hang `on_subagent_stop`: hear of one about to finish. |
| `AskUserHookAgentMixin` | Hang `on_ask_user`: answer the agent stopping mid-turn to ask its user something. |

Each is checked twice.

**Before the run.** A harness that does not serve what its role declares is refused before
anything starts, so a flow built on a goal cannot be started on a harness with none and fail
an hour in. `/flow` offers only the harnesses that would do.

```console
$ hmz exec -f goal -a worker=pi/gpt-5.5:high -b cost=5 "fix the build"
hmz exec: error: goal: 'worker' needs GoalCommandAgentMixin, which pi does not do
```

A calling flow that passes an agent lacking a mixin gets `CapabilityMissing` instead.

**At every use.** Using what the role did not declare raises `CapabilityNotGranted`, whatever
the harness could do: a `/goal` or `/loop` prompt, `steer`, one of the four mixin hooks, a
script `exec`, files, worktrees, copies or scratch directories.

```
agent: steer needs SteeringAgentMixin on the role
```

### What each harness serves {#what-each-harness-serves}

<div class="harness-matrix">

| `-a` | Goal | Loop | Steering | Permission request | Subagent start, stop | Ask user | [Fork](#fork) |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | --- |
| `claude` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | any workdir |
| `codex` | ✓ | | ✓ | ✓ | ✓ | ✓ | any workdir |
| `kimi` | ✓ | | ✓ | ✓ | | ✓ | any workdir |
| `zcode` | ✓ | | | ✓ | | ✓ | any workdir |
| `pi` | | | ✓ | | | ✓ | same workdir |
| `dsh` | ✓ | | | | | | no |
| `cursor-agent` | | | | | ✓ | | no |
| `grok` `opencode` `mimo` `qwen` `acp` | | | | | | | same workdir |
| `agy` | | | | | | | no |

</div>

<span id="harness-agents"></span>Each harness also has a protocol of its own that declares
exactly that row: `ClaudeCodeAgent`, `CodexAgent`, `KimiCodeAgent`, `ZCodeAgent`, `PiAgent`,
`DeepSeekHarnessAgent`, `CursorAgent`, `GrokBuildAgent`, `OpenCodeAgent`, `MiMoCodeAgent`,
`QwenCodeAgent` and `AntigravityAgent`. `HARNESS_AGENTS` maps each `HarnessKind` to its
protocol, and `acp` to plain `Agent`.

A role typed as one of them asks for **that harness** and everything it serves. Any other
harness given for it is refused before anything starts: from `hmz exec` as
`twice: 'builder' is claude, and codex was given`, and from a calling flow as
`HarnessMismatch`. Use it only where the flow really is written for one CLI: a role declared
by its mixins is one more harnesses can fill.

```python
from hmz.flows import AgentCollection, ClaudeCodeAgent


class Agents(AgentCollection):
    builder: ClaudeCodeAgent  # Claude Code, and nothing else will do
```

The one flow granted everything its harness serves, whatever it declares, is
[`chat`](#the-flow-in-the-package).

## Permissions {#what-each-agent-may-do}

::: danger Approvals are bypassed
Every harness runs at its nothing-asked mode. No session waits for a person to approve a tool,
and no model reviews another's actions. What limits an agent is its `Permission` and the
[hooks](#hooks-in-a-flow) the flow hangs on it.
:::

### `Permission` {#permission}

```python
@dataclass(frozen=True, slots=True)
class Permission:
    local: PermissionKind = PermissionKind.ALL
    user: PermissionKind = PermissionKind.READ
    system: PermissionKind = PermissionKind.READ
    online: PermissionKind = PermissionKind.NONE

    def covers(self, other: Permission) -> bool: ...
```

| Field | Scope | Default |
| --- | --- | --- |
| `local` | the environment's workdir the session works in | `ALL` |
| `user` | the rest of the home directory of the user the agent runs as | `READ` |
| `system` | everything else on the machine | `READ` |
| `online` | the CLI's own web search and fetching | `NONE` |

- Scopes nest: `local >= user >= system`. `online` is `NONE` or `ALL`, never `READ`. A
  `Permission` that breaks either raises `ValueError` where it is made: `a wider scope may not
  be granted more than a narrower one: local=read, user=all, system=read`.
- `covers(other)` is `True` where no scope of this one is narrower than the same scope of
  `other`.
- A role's sessions run under exactly its `_permission`. An agent passed to a called flow must
  cover the callee's role, or the call is refused with `PermissionTooNarrow`.

```python
Permission(local=PermissionKind.READ, user=PermissionKind.NONE, system=PermissionKind.NONE)
Permission().covers(Permission(local=PermissionKind.READ))   # True
```

### `PermissionKind` {#permissionkind}

`class PermissionKind(StrEnum)`: `NONE`, `READ`, `ALL`, which compare in that order
(`PermissionKind.NONE < PermissionKind.READ`).

::: details How a permission reaches each CLI
| `local` | every harness but `dsh` and `acp` | `dsh`, `acp` |
| --- | --- | --- |
| `READ` or `NONE` | the CLI's read-only rung: Claude Code's `plan`, Codex's read-only sandbox, a tool list with nothing that writes | `bypass` |
| `ALL` | `bypass` | `bypass` |

- **`user` and `system` are not fenced.** A session that may write its workdir may write
  anywhere its user can. Codex's `workspace-write` and cursor-agent's `--sandbox enabled` could
  fence it, and neither is used: both are bubblewrap, which cannot start where it is given no
  user namespace, as in most containers.
- **`local` `READ` reads outside the workdir too**, which is wider than a `user` or `system` of
  `NONE`. `dsh` and `acp` can be held to nothing but `bypass`.
- **`online`** is on for `ALL` and off for `NONE` where the CLI can be told, and left as the
  CLI has it where it cannot (cursor-agent, pi, Antigravity, ACP). A shell command the agent
  runs reaches the network whatever this says.
- **Nothing-asked mode** is `danger-full-access` with approval `never` on Codex. On Claude
  Code, whose `bypassPermissions` a managed policy may forbid, it is `manual` with humanize
  answering every request yes.
- **A hook only an asking CLI reaches** starts the CLI so that it asks, and humanize answers
  yes unless the hook says no. Codex runs with approval policy `untrusted` while an
  `on_permission_request` hook is hung, and turns on its `default_mode_request_user_input`
  feature for an `on_ask_user` one. Kimi Code and ZCode run at their asking rung while either
  is hung.

[Agents](/reference/agents) has the rungs themselves.
:::

### `Agent.derive` {#derive}

```python
def derive(self, *, permission: Permission | None = None,
           skills: tuple[str, ...] | None = None) -> Self
```

| Parameter | |
| --- | --- |
| `permission` | What the derived agent may touch, or `None` for this one's. |
| `skills` | Which of this agent's skills its sessions carry, or `None` for all of them. |

Returns the same agent, narrowed for a stretch of the flow. The derived agent shares this
one's hooks and sessions; this one is unchanged. Widening either raises
`CapabilityNotGranted`.

```python
reading = agents["builder"].derive(
    permission=Permission(local=PermissionKind.READ, system=PermissionKind.NONE)
)
```

## Sessions and turns {#sessions-and-turns}

A session is one conversation of one agent in one environment. A turn is a prompt and the
answer to it.

### `Agent.spawn` {#spawn}

```python
async def spawn(self, *, env: Env) -> Session
```

Opens a new session working in `env`: its commands run in `env`'s workdir, on `env`'s
machine. An ssh environment is where that session's turns land. Raises `HarnessError` if the
harness cannot be started there.

### `Agent.run` {#run}

```python
async def run(self, prompt: str, *, session: Session,
              output_schema: type[M] | None = None, budget: Budget | None = None) -> str | M
```

| Parameter | |
| --- | --- |
| `prompt` | What to say. A prompt starting `/goal` hands the turn to the harness's own goal feature, and one starting `/loop` to its recurring task; each needs [its mixin](#asking-for-an-agent-that-can-do-something). Every other prompt goes to the agent as it is. |
| `session` | A session this agent opened. |
| `output_schema` | A pydantic model. The turn answers with an instance of it, and an answer that cannot be read as one raises `OutputSchemaError`. See [Answers in a shape](/weaver/shapes). |
| `budget` | A limit on this one turn, on top of the flow's own. See [Budgets](#what-a-run-may-spend). |

Returns what the agent said, or an instance of `output_schema`.

Raises `SessionError` for a session of another agent, one that is over, or one whose turn is
still under way; `CapabilityNotGranted` for `/goal` or `/loop` without the mixin;
`BudgetExceeded` once a budget is spent; and the [`HarnessError`](#harnesserror) a failed
turn came to.

```python
session = await coder.spawn(env=workspace)
said = await coder.run(task, session=session)                                    # str
verdict = await coder.run("Is it done?", session=session, output_schema=Verdict)  # Verdict
```

- **A session takes one turn at a time.** Two sessions of one agent may take turns at once.
- **A session belongs to the agent that opened it.** Handing it to another agent, or to the
  same agent as a called flow holds it, raises `SessionError`.

### `SteeringAgentMixin.steer` {#steer}

```python
async def steer(self, prompt: str, *, session: Session, queued: bool = True) -> None
```

| Parameter | |
| --- | --- |
| `prompt` | What to put into the turn. |
| `session` | The session whose turn it is. |
| `queued` | `True`: the agent takes it when it next looks, and carries on. `False`: the turn is interrupted and goes on from this prompt, as pressing <kbd>esc</kbd> before typing would. |

Raises `SessionError` if `session` has no turn under way. Only for a role declared with
`SteeringAgentMixin`.

```python
turn = asyncio.create_task(coder.run(task, session=session))
await asyncio.sleep(600)                                  # ten minutes in
if not turn.done():
    await coder.steer("Wrap up: commit what you have.", session=session)
said = await turn
```

### `Agent.fork` {#fork}

```python
async def fork(self, session: Session, *, env: Env) -> Session
```

Opens a second session that carries on from where `session` is, and leaves `session` as it
was. `env` is where the new one works: another workdir only on Claude Code, Codex, Kimi Code
and ZCode, the same workdir on every other harness that forks, and never another machine.
cursor-agent, Antigravity and dsh do not fork. Either refusal raises `UnsupportedOperation`.

A fork is cut where it takes its first turn, so it is refused then if the session it came from
has taken a turn since. See [Branching a conversation](/weaver/branching).

```python
tried = await coder.fork(session, env=workspace)
```

### `Session` {#session}

```python
class Session(Protocol):
    agent: Agent       # read-only properties
    env: Env
    usage: Usage
```

| Property | |
| --- | --- |
| `agent` | The agent whose conversation this is. |
| `env` | The environment it works in. |
| `usage` | What its turns have spent so far, up to date whenever it is read. |

There is no `close`. A session is closed when the flow call that opened it ends (after every
call it started has) **or** as soon as nothing holds it, whichever comes first. A loop that
opens a fresh session a round holds one or two open however long it runs; one kept in a
variable, list or dict stays open while it is kept. A fork keeps its parent open until its own
first turn. A turn that is cancelled (a `TaskGroup` sibling failing, a deadline,
<kbd>ctrl+c</kbd>) interrupts the CLI rather than leaving it running.

## Environment roles {#where-each-agent-works}

An environment is a working directory on a machine: this one, or one `ssh` reaches.

```python
from hmz.flows import BashEnvMixin, Env, EnvCollection, FilesEnvMixin, GPUEnvMixin
from hmz.flows import LocalEnv, ShellEnvMixin


class Workspace(LocalEnv, BashEnvMixin, FilesEnvMixin):
    """The directory the run was started in: scripts run there, and files are read."""


class Trainer(Env, ShellEnvMixin, GPUEnvMixin):
    _gpu_count = 8
    _gpu_memory = 80 * 1024**3


class Envs(EnvCollection):
    workspace: Workspace
    trainer: Trainer
```

```sh
hmz exec -f train -a coder=claude/claude-opus-5:high -e trainer=ssh@gpu-box/home/me/repo \
    -b duration=6h "get the loss under 2.1"
```

### `EnvCollection` {#envcollection}

```python
class EnvCollection(TypedDict, extra_items=ReadOnly[Env]): ...
```

One key per environment role, each typed as `Env`, `LocalEnv`, or a subclass carrying
mixins. `NotRequired` roles may be left out. Every role but a `LocalEnv` one is filled with
`-e <role>=<backend>@<provider>/<workdir>`: `local@/srv/data` on this machine,
`ssh@gpu-box/home/me/repo` on a host `ssh` reaches, `ssh@gpu-box/~/repo` under the home
directory there. Full syntax in the [CLI reference](/reference/cli).

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

| Member | |
| --- | --- |
| `workdir` | The directory commands run in and relative paths are under. Absolute, or `~/…` under the ssh login's home. |
| `backend` | `local` or `ssh`, an [`EnvBackendKind`](#envbackendkind). |
| `provider` | The ssh host, or `""` for this machine. |
| `available` | Whether the machine could be reached and the workdir exists, as last seen. |
| `role` | The key it fills in the flow's `EnvCollection`. |
| `derive_subdir(subdir=…)` | An environment at a directory under this one, made if missing, filling the same role with the same grant. Raises `ValueError` for a `subdir` that is absolute or climbs out. |

### `LocalEnv` {#localenv}

```python
class LocalEnv(Env, Protocol): ...
```

The workspace the run was started in, which the runtime fills. A role typed `LocalEnv`, or a
subclass of it with mixins, takes no `-e`, and `-e` naming it is refused.

A flow calling another may leave a `LocalEnv` role out, and the callee gets the run's
workspace, granted what the callee declares. Passing one of its own instead works only if that
one was granted as much. Passing an environment on another machine raises
`CapabilityMissing`:

```
review:review: 'workspace' is a LocalEnv, and the environment given is ssh@gpu-box/home/me/repo, which is not this machine
```

### `EnvBackendKind` {#envbackendkind}

`class EnvBackendKind(StrEnum)`: `LOCAL` (`"local"`, this machine) and `SSH` (`"ssh"`, a host
`ssh` itself resolves).

### What an environment can do {#what-an-environment-can-do}

| Mixin | Adds |
| --- | --- |
| `ShellEnvMixin` | `async exec(argv: SequenceNotStr[str], *, timeout: float = 0) -> tuple[int, str, str]`: one program with no shell between, run in the workdir. Answers its exit status, stdout and stderr. `timeout` is in seconds, `0` for none; past it the program is killed and `EnvCommandTimeout` raised. |
| `BashEnvMixin` | `exec` of a `str` as well, run as `bash -c` would: `await env.exec("make test 2>&1 \| tail -20")`. Includes `ShellEnvMixin`. |
| `FilesEnvMixin` | `async read(path: str) -> bytes` and `async write(path: str, data: bytes) -> None`, relative to the workdir or absolute. `write` makes the directories above. A missing file raises `EnvFileNotFound`, and a refused one `EnvPermissionDenied`. |

```python
code, out, err = await workspace.exec(["pytest", "-q"], timeout=600)
notes = (await workspace.read("NOTES.md")).decode()
```

<span id="sequencenotstr"></span>`SequenceNotStr[T]` is what an argv is typed as: a sequence
that is not a `str`, so a script passed where an argv was meant is a type error. Lists and
tuples of strings match.

### What a machine must have {#what-a-machine-must-have}

Three mixins are amounts rather than abilities. A machine that has less than the role declares
is refused before anything runs, with `ResourceUnmet`.

| Mixin | Class attributes |
| --- | --- |
| `CPUEnvMixin` | `_cpu_count: int = 1`, the fewest logical CPUs. |
| `MemoryEnvMixin` | `_memory: int = 0`, the least memory, in bytes. |
| `GPUEnvMixin` | `_gpu_count: int = 1` and `_gpu_memory: int = 0`, the fewest GPUs and the least memory each, in bytes. |

### Worktrees, copies and scratch directories {#worktrees-copies-and-scratch-directories}

Three mixins derive another environment on the same machine, filling the same role with the
same grant.

| Mixin | Methods |
| --- | --- |
| `GitWorktreeEnvMixin` | `async derive_worktree(*, ref: str \| None = None, dir: PurePosixPath \| str \| None = None) -> Self` |
| `TemporaryClonedDirEnvMixin` | `async derive_temp_clone(id: str) -> Self`, `async destroy_temp_clone(id: str) -> None` |
| `ScratchDirEnvMixin` | `async derive_scratch(id: str) -> Self`, `async destroy_scratch(id: str) -> None` |

```python
tree = await workspace.derive_worktree(ref="main")        # a git worktree, checked out detached
trial = await workspace.derive_temp_clone("attempt-1")    # a throwaway copy of the workdir
notes = await workspace.derive_scratch("notes")           # an empty directory beside it

session = await coder.spawn(env=tree)                     # an agent working in one
```

- **`derive_worktree`** adds a worktree of the repository the workdir is in: `ref` checked out
  detached, or what the workdir has checked out; at `dir`, or a fresh directory. A workdir
  outside a repository, a ref git does not know, or a taken directory raises `WorktreeError`.
- **`derive_temp_clone(id)`** is a copy of the workdir, a reflink where the filesystem can make
  one. The same id from the same environment is the same copy, made once. Asked for by another
  environment while this one holds it, it raises `TempCloneBusy`.
- **`derive_scratch(id)`** is an empty directory, the same one for the same id. It raises
  `ScratchError` if it cannot be made.
- **`destroy_*`** removes one now. Removing one that is not there does nothing.

Copies and scratch directories are **removed when the flow call that made them ends**, after
every call it started, unless the run is [resumable](#a-flow-that-can-be-picked-up): then they
are kept for `--resume` to find. A worktree is left where it is. All three live under
`~/.humanize/envs/` on that machine, named after the workdir and the id. See
[Worktrees, copies and scratch](/weaver/worktrees).

## Hooks {#hooks-in-a-flow}

A hook is an async function from one moment's params to that moment's result, hung on an
agent with the `on_*` method for that moment. This Ralph loop will not let a turn end while
`TASK.md` still has unticked boxes:

```python
from hmz.flows import StopHookParams, StopHookResult


class Workspace(LocalEnv, FilesEnvMixin): ...


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def unfinished(task, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext):
    agent, workspace = agents["agent"], envs["workspace"]

    async def not_yet(hook: StopHookParams) -> StopHookResult:
        left = "- [ ]" in (await workspace.read("TASK.md")).decode()
        return StopHookResult(block=left and hook.again < 5,
                              reason="TASK.md still has unticked boxes.")

    agent.on_stop(not_yet)  # [!code highlight]
    while "- [ ]" in (await workspace.read("TASK.md")).decode():
        session = await agent.spawn(env=workspace)
        await agent.run(task, session=session)
```

| Method | Called when | Params | Result |
| --- | --- | --- | --- |
| `on_session_start` | a session is about to take its first turn | | `context` |
| `on_user_prompt_submit` | a prompt is about to go to the agent | `prompt` | `block`, `reason`, `context` |
| `on_pre_tool_use` | the agent reached for a tool that has not run | `tool`, `input` | `block`, `reason` |
| `on_notification` | the agent stops to tell its user something | `message` | |
| `on_stop` | a turn is about to end | `said`, `again` | `block`, `reason` |
| `on_session_end` | a session is being closed | | |
| `on_permission_request` <Badge type="info" text="mixin" /> | the harness asks whether a tool may run | `tool`, `input` | `allow`, `reason` |
| `on_subagent_start` <Badge type="info" text="mixin" /> | the agent starts a subagent | `subagent`, `task` | `context` |
| `on_subagent_stop` <Badge type="info" text="mixin" /> | a subagent is about to finish | `subagent`, `said` | `block`, `reason` |
| `on_ask_user` <Badge type="info" text="mixin" /> | the agent stops mid-turn to ask its user | `question`, `options` | `answer` |
| `on_outworlder_run` | an [`Outworlder.new()`](#outworlder) is asked to take a turn | `prompt`, `output_schema` | `output` |

The first six are on every `Agent`. A hook marked **mixin** is hung only on a role declared
with the mixin named after it (`on_permission_request` needs
`PermissionRequestHookAgentMixin`, and so on); hanging it on any other raises
`CapabilityNotGranted`. `on_outworlder_run` is only for an outworlder made with
`Outworlder.new()`.

Each params class is `<Moment>HookParams` and each result `<Moment>HookResult`:
`StopHookParams`, `StopHookResult`, and so on. All are frozen, keyword-only dataclasses. Every
params class also carries `ctx` and `session`. A result built with no arguments changes
nothing, so a hook that only watches returns one.

| Params field | |
| --- | --- |
| `prompt` | The prompt about to go, or what the outworlder was asked. |
| `tool`, `input` | The tool as the harness names it, and what it was called with: a mapping, empty where the harness does not say. |
| `message` | What the agent said to its user. |
| `said`, `again` | What the agent said last, and how many times a hook has already kept this turn going. |
| `subagent`, `task` | What the harness calls the subagent, and what it was asked to do. |
| `question`, `options` | What the agent asked, and the answers it offered, as a tuple. An answer need not be one of them. |
| `output_schema` | The model the outworlder's answer must be, or `None` for text. |

| Result field | Default | |
| --- | --- | --- |
| `context` | `""` | Text put before the first prompt, or added to a prompt. |
| `block`, `reason` | `False`, `""` | A blocked prompt does not run, and `run` raises `SessionError` saying `reason`. A blocked tool does not run, and the agent is told `reason`. A blocked stop keeps the turn going with `reason` as the next prompt; an empty `reason` does not block. |
| `allow`, `reason` | `True`, `""` | Whether the tool may run, overriding the bypassed approvals, and what the agent is told of a refusal. |
| `answer` | `None` | What the agent is told. `None` leaves the question unanswered, and the agent carries on without one. |
| `output` | required | What the outworlder's `run` returns: text, or an instance of `output_schema`. |

- **Hanging one replaces** the hook hung there before, and `None` takes it down.
- **A hook covers every session of its agent**, including the fresh one a loop spawns every
  round, and of any agent [`derive`](#derive)d from it. It is the flow's own: a called flow's
  hooks are not heard by its caller's sessions, nor the other way round.
- **It runs as the flow its agent belongs to**, with that flow's `ctx`, on the flow's event
  loop. What it raises fails the turn the moment arrived in, and `run` raises it there.
- **What it answers is acted on where the CLI waits for it.** `on_pre_tool_use` refuses a
  tool on Claude Code and Qwen Code, which gate their tools with a hook table of their own,
  and on the rest hears of one already reached for. An `on_permission_request` refusal is the
  tool refused and its reason told to the agent (on Codex, as a steer into the turn).
  `on_subagent_start` and `on_subagent_stop` are told: no CLI waits on either, so what they
  answer changes nothing.
- **A hook that keeps a CLI waiting 15 minutes** is answered as if nothing were hung, and the
  turn goes on. `on_ask_user` is the exception: a question waits for its answer.
- **A hook hung mid-turn** reaches that turn's later moments, except the ones that decide how
  a CLI is started, which take hold from the next turn: `on_pre_tool_use` on a CLI that gates
  its tools, and `on_permission_request` or `on_ask_user` on Codex, Kimi Code and ZCode.

See [Hooks](/weaver/hooks) for the guide, and [The agent asking the flow](/weaver/tools) for
`on_ask_user`.

### `HookKind` {#hookkind}

`class HookKind(StrEnum)`, one value per moment: `SESSION_START`, `USER_PROMPT_SUBMIT`,
`PRE_TOOL_USE`, `PERMISSION_REQUEST`, `NOTIFICATION`, `STOP`, `SESSION_END`,
`SUBAGENT_START`, `SUBAGENT_STOP`, `ASK_USER`, `OUTWORLDER_RUN`. Each value is the lowercase
name: `HookKind.STOP == "stop"`.

### `HookFn` {#hookfn}

```python
class HookFn[TParams: HookParams, TResult](Protocol):
    async def __call__(self, params: TParams, /) -> TResult: ...
```

### `HookParams` and `HookResult` {#hookparams-and-hookresult}

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class HookParams:
    ctx: FlowContext      # the context of the flow the agent belongs to
    session: Session      # the session the moment arrived in

@dataclass(frozen=True, slots=True, kw_only=True)
class HookResult: ...
```

The bases every `<Moment>HookParams` and `<Moment>HookResult` extend.

### `HOOK_TYPES` {#hook-types}

`HOOK_TYPES: Mapping[HookKind, tuple[type[HookParams], type[HookResult]]]`, each moment's
params and result classes: `HOOK_TYPES[HookKind.STOP] == (StopHookParams, StopHookResult)`.

## The person at the prompt {#the-person-at-the-prompt}

### `Outworlder` {#outworlder}

```python
class Outworlder(Agent, Protocol):
    away: bool                                     # read-only property

    @classmethod
    def new(cls) -> Self: ...
    def on_outworlder_run(self, fn: HookFn | None) -> None: ...
```

Whoever is outside the run, taking turns as an agent of the flow rather than typing into one.
A role typed `Outworlder` is filled by the runtime: at the top of a run it is the person who
started it. `-a` naming one is refused.

```python
class Agents(AgentCollection):
    assistant: Agent
    human: Outworlder


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def talk(task, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext):
    assistant, human = agents["assistant"], agents["human"]
    talking = await assistant.spawn(env=envs["workspace"])
    listening = await human.spawn(env=envs["workspace"])
    said = task
    while said:
        answered = await assistant.run(said, session=talking)
        said = await human.run(answered, session=listening)
```

- **`run`** asks the person what to say next, and answers with what they typed. Asked for an
  `output_schema`, they are asked a question per field and the model is built from the
  answers.
- **`away`** is `True` under `hmz exec`, where nobody is at a prompt, and while
  [`/afk`](/user/afk) is on. While it is away, `run` answers at once: `""` for text, the
  schema built from its defaults where every field has one, and `OutworlderAway` otherwise.
  The loop above ends at once under `hmz exec`.
- **A calling flow** passes its own outworlder, or leaves the role out and the callee gets the
  run's, or makes one with `new()` and answers for it.
- **`Outworlder.new()`** makes an outworlder the flow answers for through
  `on_outworlder_run`. Until a hook is hung on it, it is away. `on_outworlder_run` on any other
  outworlder raises `CapabilityNotGranted`.
- An outworlder carries no skills and cannot be forked. It is not
  [steering](/user/steering): steering puts words into an agent's turn, and an outworlder
  takes turns of its own.

```python
from hmz.flows import Outworlder, OutworlderRunHookParams, OutworlderRunHookResult


async def approve(asked: OutworlderRunHookParams) -> OutworlderRunHookResult:
    if asked.output_schema is None:
        return OutworlderRunHookResult(output="Yes, go ahead.")
    return OutworlderRunHookResult(output=asked.output_schema())


rlcr = load("humanize1:rlcr")
stand_in = Outworlder.new()
stand_in.on_outworlder_run(approve)
await rlcr(task, agents={"builder": builder, "reviewer": reviewer, "human": stand_in},
           envs={}, params=rlcr.expected_params())
```

## Params {#settings-of-the-flow-s-own}

### `FlowParams` {#flowparams}

```python
class FlowParams(pydantic.BaseModel):
    model_config = ConfigDict(extra="forbid", ser_json_inf_nan="strings")
```

Subclass it with one field per setting, and pass the subclass as `@flow(params=…)`.

```python
from typing import Literal

from pydantic import Field

from hmz.flows import FlowParams


class Params(FlowParams):
    """What this flow takes."""

    rounds: int = Field(default=3, ge=1, le=9, description="how many times round")
    mode: Literal["fast", "slow"] = Field(default="fast", description="which way")
```

```sh
hmz exec -f loop -a agent=claude/claude-opus-5:high -p rounds=5,mode=slow -b cost=10 "…"
```

The model is the form: the fields are the questions `/flow` asks, their types say how each
is answered, `description` is the line beside each, and what `/flow` set is remembered per
flow.

- **`-p key=value`**, as many as there are or a comma list in one. A value is read as the
  field's type, or as JSON: `-p tags='["a","b"]'`. A comma splits two settings only where a
  `key=` follows it, so `-p note=one,two` is one setting.
- **A key the model does not declare is refused**, since `extra="forbid"`. Anything the model
  refuses raises `ParamsError` before anything starts.
- **A field with no default** must be given with `-p`.
- **Combinations the flow cannot run belong in the model**, as a `model_validator`, so they
  are refused where they were typed.

## The context {#the-context}

### `FlowContext` {#flowcontext}

```python
class FlowContext(Protocol):
    flow: Flow             # read-only properties
    budget: Budget
    usage: Usage
    state: FlowState | None
    resumed: bool
```

| Property | |
| --- | --- |
| `flow` | The flow being called. |
| `budget` | The budget this call runs under: the tighter of its own and what remains of every one above it. |
| `usage` | What this call, and every call under it, has spent so far. |
| `state` | What a [resumable](#a-flow-that-can-be-picked-up) flow keeps across runs, or `None`. |
| `resumed` | Whether this call picks up one an earlier run left off. |

Each call has its own: a flow that gathers ten calls of another holds ten contexts, each
counting its own spending, all of it counted in the caller's too.

```python
if ctx.budget.cost is not None and ctx.budget.cost - ctx.usage.cost < 1.0:
    return  # not enough left for another round
```

## Budgets {#what-a-run-may-spend}

### `Budget` {#budget}

```python
class Budget(pydantic.BaseModel):   # frozen, extra="forbid"
    duration: timedelta | None = None
    cost: float | None = None
    output_tokens: int | None = None
    graceful: bool = True
```

| Field | Limits |
| --- | --- |
| `duration` | How long, from when it started. A deadline. |
| `cost` | What it may cost, in USD. |
| `output_tokens` | How many tokens its agents may write. |
| `graceful` | `True`: the turn under way when a limit is reached may finish. `False`: it is cut off at once. |

At least one limit is set, and none is negative; otherwise `pydantic.ValidationError`.
`Budget(cost=math.inf)` is unlimited, which is what [`chat`](#the-flow-in-the-package) runs
under. Every other run needs one: `-b` on the command line (see the
[CLI reference](/reference/cli) for its syntax), or `budget=` in [Python](/reference/sdk).

```python
from datetime import timedelta

from hmz.flows import Budget

Budget(duration=timedelta(hours=6), cost=50.0, output_tokens=25_000_000)
```

**It is held at every turn, whatever harness is behind it.** A limit reached mid-turn lets the
turn finish where the budget is graceful, and cuts it where it is not. Either way the next turn
under that budget raises the `BudgetExceeded` leaf: `DurationExceeded` (also a
`TimeoutError`), `CostExceeded` or `OutputTokensExceeded`. **A spent budget stays spent**:
every later turn under it raises again. Past its deadline, a call is stopped where it is
(after the turns under way finish, where graceful) and raises `DurationExceeded` there.

**Budgets nest.** A call and a turn may each have one of their own:

```python
await load(":review")(task, agents=..., envs=..., params=..., budget=Budget(cost=2.0))
await agent.run(prompt, session=session, budget=Budget(output_tokens=50_000, graceful=False))
```

- Each runs under the tighter of its own and what remains of every budget above it.
- A turn's own budget is one turn long, so a graceful one only counts. One meant to cut the
  turn short says `graceful=False`.
- Cost and tokens spent anywhere under a flow count against every flow above it. `duration`
  is a deadline each call has of its own, so ten calls gathered for an hour spend one hour of
  their caller's, not ten.
- A turn's cost is priced with [humanize's price table](/user/tally). A model nobody prices
  costs nothing there, so a cost limit alone does not stop it: add `duration` or
  `output_tokens`.

### `Usage` {#usage}

```python
class Usage(pydantic.BaseModel):    # frozen
    duration: timedelta = timedelta(0)
    cost: float = 0.0
    output_tokens: int = 0
```

What has been spent: `duration` is the time the agents spent taking turns. `ctx.usage`,
`session.usage` and `Run.usage` are each one.

## Waiting for more than one thing {#a-flow-that-waits-for-more-than-one-thing}

A flow is a coroutine, so `asyncio.gather`, `asyncio.TaskGroup`, `asyncio.timeout` and
`except*` all work as they do anywhere. A fan-out is a session apiece:

```python
async def fix(path: str) -> str:
    session = await coder.spawn(env=workspace)
    return await coder.run(f"Fix the tests in {path}", session=session)

async with asyncio.TaskGroup() as group:
    fixing = [group.create_task(fix(path)) for path in paths]
said = [one.result() for one in fixing]
```

- Turns of **one** session are still a sequence: a second `run` while one is under way raises
  `SessionError`.
- A turn a `TaskGroup` cancels interrupts its CLI.
- A called flow's exception reaches `except*` with the class it was raised with.
- Gathered calls of other flows are a tree of contexts, each counting what it spends.

## Resumable flows {#a-flow-that-can-be-picked-up}

A flow declared `resumable=True` keeps a journal while it runs. `hmz exec --resume` and
`/resume` pick the newest run of it up where it stopped, and *resume this run* on `/epics` the
run under the cursor.

```python
@flow(agents=Agents, envs=Envs, params=FlowParams, resumable=True)
async def each_file(task, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext):
    """One pass per file, however often it is stopped."""
    agent, workspace, state = agents["agent"], envs["workspace"], ctx.state
    assert state is not None                       # a resumable flow always has one
    if "left" not in state:
        _, out, _ = await workspace.exec(["git", "ls-files", "*.py"])
        state["left"] = out.split()
    while state["left"]:
        session = await agent.spawn(env=workspace)
        await agent.run(f"{task}\n\nThis file: {state['left'][0]}", session=session)
        state["left"] = state["left"][1:]          # writing it is what saves it
```

### `FlowState` {#flowstate}

```python
class FlowState(Protocol):
    def __getitem__(self, key: str) -> Any: ...
    def __setitem__(self, key: str, value: Any) -> None: ...
    def __delitem__(self, key: str) -> None: ...
    def __contains__(self, key: str) -> bool: ...
```

`ctx.state`: a mapping of JSON values, `None` for a flow that is not resumable.

- **Each write is saved as it is made**, so a run that was killed can be picked up. A change
  made inside a value (a list appended to) is not a write: write the value back, as above.
- **A value JSON cannot hold** raises `StateNotSerializable` (also a `TypeError`) where it is
  written. What is read back is what JSON gives back, so a fresh run and a resumed one read
  the same.
- **Keep what the loop itself tracks**: the round, the files done, what it decided. The
  harnesses already keep the transcript, and the [epic](/reference/tracing#epics) already
  says which sessions were opened.

What a resumed run does:

- The flow at the top picks up unconditionally, with `ctx.resumed` true and its state as it
  was.
- **A flow it calls picks up too, where the call is the same one**: the same flow, task,
  agents (harness, account, model, effort, permission, skills), environments (how each was
  derived from what the command line named, never a path) and params. Identical calls match
  in the order they were made. A call that differs starts afresh, with an empty state.
- A flow that is not resumable has no state, and passes resumption through to the flows it
  calls.
- Temporary copies and scratch directories a resumable run made are kept, so the resumed run
  finds them.

See [Picking a run up](/user/resuming).

## Calling another flow {#a-flow-that-calls-another-flow}

```python
from hmz.flows import load


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def plan_then_build(task, *, agents: Agents, envs: Envs, params: FlowParams,
                          ctx: FlowContext):
    plan = load("humanize1:gen-plan")
    await plan(f"plan this first: {task}",
               agents={"planner": agents["builder"], "analyst": agents["reviewer"]},
               envs={},                          # its LocalEnv role: the run's workspace
               params=plan.expected_params())
    ...
```

### `load` {#load}

```python
def load(ref: str) -> Flow
```

| Parameter | |
| --- | --- |
| `ref` | Which flow. See [Refs](#refs). |

Returns the [`Flow`](#flow-protocol), ready to be called. A flow is called the same way
whichever of `@flow` or `load` it came from.

Raises `FlowRefError` (also a `ValueError`) for something that is not a ref, or a `:<name>`
with no flow asking; `FlowNotFound` for a ref that names no flow; `FlowLoadConflict` if
loading it would replace a module another flow of the run uses; `FlowDefinitionError` if what
it names is written wrong.

### Refs {#refs}

| Ref | Is |
| --- | --- |
| `:review` | a flow in the same module as the flow asking |
| `rlar` | a flow in the same flowverse as the flow asking, else looked up [nearest first](#where-flows-live) as `-f` looks one up, else a path |
| `humanize1:gen-plan` | a named flow of a module, found the same way |
| `git+https://github.com/humanfia/flowverse@main#humanize1:gen-plan` | a flow of another flowverse, at a revision |

- **A bare name** is the flow named after its directory; else the one flow of the module that
  is not hidden; else `FlowNotFound`, naming them. See
  [Several flows in one module](#several-flows-in-one-file).
- **`:<name>`** needs a flow asking. From anywhere else it raises
  `':review' is relative to the flow asking, and no flow is asking`.
- **A `git+` ref** is any URL pip would take, `@<rev>` optional and the default branch without
  it. It is fetched on a thread when the flow is first called, once per URL and revision per
  run, pinned to the commit it stands at, and cloned once per commit.
- **A run imports a flow's module once**, however often it loads its flows, and nothing a run
  uses leaves `sys.modules` while it goes. Two checkouts claiming one module name in one run,
  such as two flowverses each with a `humanize1`, raise `FlowLoadConflict`. A module whose
  files changed is imported afresh by the next run nobody else is running it in.

### Calling a `Flow` {#calling-a-flow}

```python
async def __call__(self, task: str, *, agents: AgentCollection, envs: EnvCollection,
                   params: FlowParams, budget: Budget | None = None) -> Any
```

| Parameter | |
| --- | --- |
| `task` | What to do. |
| `agents` | One agent per role, by the callee's role names. |
| `envs` | One environment per role. |
| `params` | An instance of the callee's `FlowParams` subclass, taken as it is. Another model or a mapping is validated into it, and refused with `ParamsError` where it does not validate. |
| `budget` | A budget of its own, run together with what remains of the caller's. `None` for the caller's alone. |

Returns what the callee returned. Only from inside a run: called anywhere else it raises
`FlowRuntimeError`.

#### What the called flow is handed {#what-the-called-flow-is-handed}

- **Hand it what it declares, no narrower.** Each agent must carry every mixin its role in the
  callee declares, at least its `_permission`, and the harness where the role is typed as one.
  Each environment must carry the mixins and resources its role declares. Anything short is
  refused before the callee runs, with `MissingRole`, `CapabilityMissing`,
  `PermissionTooNarrow`, `ResourceUnmet` or `HarnessMismatch` (all `RequirementError`):
  nothing of it has run, and nothing has been spent.
- **Only what the run handed out**: one of the caller's own agents or environments, or one
  derived from them.
- **It is handed exactly what it declared.** The callee sees each granted what its own role
  says, with its own permission and skills on its sessions. Its hooks are its own, and so are
  its sessions: a session the caller opened is not one the callee can take a turn in.
- **Roles the runtime fills may be left out.** An `Outworlder` role left out is the run's own
  outworlder, and a `LocalEnv` role left out is the run's workspace, granted what the callee
  declares. `NotRequired` roles may be left out too.
- **What it raises reaches the caller as it was raised**, never wrapped: `except CostExceeded`
  and `except* HarnessError` mean the same around a call as around a turn.
- **Calls may be gathered and may nest**: 64 deep at most. The call that would be the 65th
  raises `FlowDepthExceeded` (also a `RecursionError`). A call costs no filesystem work and no
  task, so a tree of ten thousand is cheap.
- **A call whose caller has ended** (cancelled, or failed, while something it started runs on)
  raises `FlowCancelled` at its next operation.
- [`Hmz().flows.running()`](/reference/sdk#flows) lists every flow call going in this process,
  each with its depth and the call that made it.

## Several flows in one module {#several-flows-in-one-file}

Give each `@flow` a `name`, and each is a flow of its own, `<module>:<name>`. The official
`humanize1` holds three:

```python
@flow(agents=Drafting, envs=Where, params=Idea, name="gen-idea")
async def gen_idea(task, *, agents, envs, params, ctx): ...

@flow(agents=Planning, envs=Where, params=Plan, name="gen-plan")
async def gen_plan(task, *, agents, envs, params, ctx): ...

@flow(agents=Building, envs=Where, params=Rlcr, name="rlcr",
      resumable=True)
async def rlcr(task, *, agents, envs, params, ctx): ...
```

```sh
hmz exec -f humanize1:gen-idea -a drafter=claude/claude-opus-5:max -b cost=5 \
    "add undo to the editor"
```

Each declares its own agents, environments and params, so `/flow` asks about the roles of the
one you picked. What passes between them is whatever they write, or what one returns to
another that [calls it](#a-flow-that-calls-another-flow).

**A bare name** is the flow named after the directory. Where there is none, it is the one
flow of the module that is not hidden. Where there are several, it is refused:

```console
$ hmz exec -f humanize1 -b cost=5 "…"
hmz exec: error: humanize1: ~/.humanize/flowverses/official/flows/humanize1 holds gen-idea, gen-plan, rlcr and none is called 'humanize1'; name one as humanize1:<flow>
```

- A module's flows are those defined inside its directory; a flow it imports from elsewhere is
  not one of them. Two of one name raise `FlowDefinitionError`.
- The lists show the flow a bare name means under the directory's name, and every other
  visible flow as `<module>:<name>`. A `hidden=True` flow is in no list and still loads as
  `<module>:<name>`.

## Errors {#when-something-goes-wrong}

Everything the flow API raises is one tree under `FlowException`, in three branches by whose
fault it was. Catch a leaf, a branch, or all of it:

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
        WorktreeError · TempCloneBusy · ScratchError
```

Where a builtin names the kind of failure, the leaf is that builtin too: `except
TimeoutError` catches a command that ran out of time and a budget whose duration did. A bug in
the flow's own code is still the `KeyError` it was. Every class is raised with its message as
its only argument, so each pickles as itself and crosses a process boundary intact.

```python
try:
    await agent.run(task, session=session)
except (HarnessThrottled, HarnessDropped):
    await asyncio.sleep(60)          # transient: go round again
```

A spent budget, `HarnessRefused` and `ModelUnavailable` are better left to end the run: the
next attempt fails the same way.

| Class | Raised when |
| --- | --- |
| <code id="flowexception">FlowException</code> | the root: anything a flow, its agents or its environments can fail with |
| <code id="flowruntimeerror">FlowRuntimeError</code> | humanize refused something, or something it holds a run to ran out |
| <code id="flownotfound">FlowNotFound</code> | a ref names no flow |
| <code id="flowreferror">FlowRefError</code> | a ref is not written as one, or `:<name>` has no flow asking |
| <code id="flowdefinitionerror">FlowDefinitionError</code> | a flow is written wrong, or a skill a role names is not there |
| <code id="flowloadconflict">FlowLoadConflict</code> | loading would replace a module another flow of the run uses |
| <code id="requirementerror">RequirementError</code> | what was given does not meet the declaration; nothing has run |
| <code id="missingrole">MissingRole</code> | a required role was not given |
| <code id="capabilitymissing">CapabilityMissing</code> | an agent or environment lacks a mixin its role declares |
| <code id="permissiontoonarrow">PermissionTooNarrow</code> | an agent holds a narrower `Permission` than its role declares |
| <code id="resourceunmet">ResourceUnmet</code> | a machine has fewer CPUs or GPUs, or less memory, than declared |
| <code id="harnessmismatch">HarnessMismatch</code> | a role typed as one harness was given another |
| <code id="capabilitynotgranted">CapabilityNotGranted</code> | the flow used something its role did not declare, or tried to widen a grant |
| <code id="paramserror">ParamsError</code> | params do not validate against the flow's model |
| <code id="flowdepthexceeded">FlowDepthExceeded</code> | flows called flows more than 64 deep |
| <code id="budgetexceeded">BudgetExceeded</code> | a budget of this flow or one above it is spent; sticky |
| <code id="durationexceeded">DurationExceeded</code> | its `duration` has elapsed |
| <code id="costexceeded">CostExceeded</code> | its `cost` is spent |
| <code id="outputtokensexceeded">OutputTokensExceeded</code> | its `output_tokens` are spent |
| <code id="flowcancelled">FlowCancelled</code> | the run was stopped from outside while this flow ran |
| <code id="statenotserializable">StateNotSerializable</code> | a value written to `ctx.state` is not JSON |
| <code id="outworlderaway">OutworlderAway</code> | an away outworlder was asked for a schema with a field that has no default |
| <code id="harnesserror">HarnessError</code> | a coding agent CLI could not take a turn, or do what it was asked |
| <code id="harnessnotinstalled">HarnessNotInstalled</code> | the CLI, or the SDK it is driven through, is not installed where the agent works |
| <code id="harnesscontended">HarnessContended</code> | two turns reached one local store of the CLI at once, and this one lost |
| <code id="harnessthrottled">HarnessThrottled</code> | the provider refused for too many requests, or a spent quota |
| <code id="harnessrefused">HarnessRefused</code> | the provider refused the credential: expired, revoked, or not signed in |
| <code id="modelunavailable">ModelUnavailable</code> | the model is not served to this account, is retired, or never was |
| <code id="harnessmissing">HarnessMissing</code> | the CLI would not start |
| <code id="harnesssandboxed">HarnessSandboxed</code> | the CLI could not set up its own sandbox on this machine |
| <code id="harnesskilled">HarnessKilled</code> | the CLI died mid-turn |
| <code id="harnessdropped">HarnessDropped</code> | the connection to the CLI or its provider broke mid-turn |
| <code id="harnessunrecoverable">HarnessUnrecoverable</code> | no retry could change it, for a reason none of the others name |
| <code id="outputschemaerror">OutputSchemaError</code> | an answer could not be read as the `output_schema` asked for |
| <code id="sessionerror">SessionError</code> | a session is over, another agent's, busy, not taking a turn to steer, interrupted, or its prompt was blocked by a hook |
| <code id="unsupportedoperation">UnsupportedOperation</code> | the harness cannot do this at all, such as fork |
| <code id="enverror">EnvError</code> | an environment could not do what it was asked |
| <code id="envunavailable">EnvUnavailable</code> | its machine is gone or its workdir does not exist |
| <code id="envconnectionerror">EnvConnectionError</code> | the connection to a remote environment could not be made, or broke |
| <code id="envcommandtimeout">EnvCommandTimeout</code> | a command ran past its `timeout`, and was killed |
| <code id="envfilenotfound">EnvFileNotFound</code> | a file read is not there |
| <code id="envpermissiondenied">EnvPermissionDenied</code> | a read, write or command was refused for want of permission |
| <code id="worktreeerror">WorktreeError</code> | `derive_worktree` failed: not a repository, an unknown ref, or a taken directory |
| <code id="tempclonebusy">TempCloneBusy</code> | `derive_temp_clone` asked for an id another environment holds |
| <code id="scratcherror">ScratchError</code> | a scratch directory could not be made or removed |

## Where flows live {#where-flows-live}

A flow is a **directory**, `__init__.py` its entry point, carrying whatever it imports and the
skills its agents work by:

```
my_loop/
├── __init__.py          the flow
├── _prompts.py          whatever it imports, which travels with it
└── skills/              what its agents are given
    └── review-notes/
        └── SKILL.md
```

**A single `.py` file is a flow too**: `.humanize/flows/twice.py` is `-f twice`, as a
directory of that name would be. It brings no skills. Where both exist under one name, the
directory wins.

`-f` takes a name or a path. A name is looked up nearest first:

| Place | Directory |
| --- | --- |
| `local` | `.humanize/flows/` in this project |
| `user` | `~/.humanize/flows/`, yours in every project |
| the rest | the flow humanize ships, then every [flowverse](#flowverses) |

A name no place answers to is taken as a path: `-f ./flows/mine`, `-f ./flows/mine.py` and
`-f ./flows/mine/` all work.

Nearest wins, so a flow of your own may stand in for one of humanize's by taking its name:
`.humanize/flows/chat/` is what `-f chat` runs in that project. What each flow is **listed
as** is another matter, so that yours sits beside humanize's rather than replacing it:

| Listed as | Is |
| --- | --- |
| `chat`, `rlar` | humanize's own, by a bare name |
| `theirs/rlar` | one another flowverse holds |
| `local/chat` | this project's own |
| `user/chat` | yours, in every project |

`-f` takes either spelling. At the prompt, a flow is started by the name it is listed as:
`$local/twice`. What each was [set up to run](/reference/tui) is remembered by that name, so
a flow of yours cannot inherit the agents or params of the one it shares a name with.

- **A file or directory whose name starts with `_` is not a flow.** It is something the flows
  beside it import, and is never listed. Nor is a directory with no `__init__.py`.
- **A flow imports what travels with it.** Its directory is imported as a module named after
  it, with the directory itself on `sys.path`, so `import _prompts` reaches the module beside
  the entry point. Those names are the flow's for as long as a run uses it.
- **`f` on a flow in `/flow`** copies it into `.humanize/flows/`, whole, and from then on the
  name means your copy. [`Hmz().flows.fork(name)`](/reference/sdk#flows) is the same. It
  refuses a name you already have a copy of, in either shape, and a copy that fails partway
  leaves nothing behind.

## The skills a flow brings {#the-skills-a-flow-brings}

The `skills/` inside a flow is laid out the way every one of these CLIs lays a skill out: a
directory apiece, each holding a `SKILL.md`. A role says which its sessions carry, with
`_skills`:

```python
class Reviewer(Agent):
    _skills = ("review-notes", "https://github.com/humanfia/flowverse#writing-tests")
```

- **A name** is a skill in the flow's own `skills/`.
- **A git URL anything can clone, with `#<skill>`**, is one of that repository's `skills/*`;
  without the `#`, every skill it holds. The repository is cloned under
  `~/.humanize/skills/` and fetched again the next time a run asks for it. The flow's own
  skill wins a name a repository also uses.
- **They are mounted onto every session of that role**: copied where that harness reads a
  project's own skills for as long as the session lives, then taken away. Nothing is
  installed, and nothing you installed is touched. A harness that reads no project skills
  carries none.
- **A skill that is not there stops the call before its first turn**, with
  `FlowDefinitionError`: one the flow's `skills/` does not hold, or a repository that cannot
  be fetched. One fetched before and unreachable now runs on the copy already here.
- **[`derive(skills=…)`](#derive)** gives a stretch of the flow fewer of them. In a module
  that holds [several flows](#several-flows-in-one-file), `skills/` is all of theirs and each
  role names the ones it carries.

## Flowverses {#flowverses}

A flowverse is a git repository with a `flows/` directory: one directory per flow, laid out as
[above](#where-flows-live). It is cloned into `~/.humanize/flowverses/<name>/`, and every flow
in its `flows/` is listed under that name. Nothing outside `flows/` is read, so the repository
may carry a README, a pyproject and tests of its own. A flow calls its siblings by their bare
name, and another flowverse's by a [`git+` ref](#refs).

Three are always there, and none can be removed:

| Flowverse | Is |
| --- | --- |
| `official` | humanize's own: [`chat`](#the-flow-in-the-package) in the package, and [humanfia/flowverse](https://github.com/humanfia/flowverse) for everything else, fetched from its default branch |
| `local` | `.humanize/flows` where humanize is being run |
| `user` | `~/.humanize/flows` |

`official` is listed before it has been fetched, and its flows are run by a bare name
whichever of its two places each is kept in; `official/rlar` also works. `local` and `user`
are directories rather than repositories: nothing fetches them, and `add`, `fetch` and
`remove` all refuse them.

`/flowverses` is where they are managed: <kbd>a</kbd> adds one, <kbd>r</kbd> fetches the one
under the cursor, and <kbd>enter</kbd> says what one holds.
[`Hmz().verses`](/reference/sdk#flowverses) is the same store from Python.

::: warning A flowverse is code
Listing what a flowverse holds imports the entry point of every flow in it. Adding one trusts
that repository with this machine, as installing a package does.
:::

Editing a flowverse's own clone does not keep: fetching it again takes what the repository
says. Fork a flow into `.humanize/flows/` to change it. See [Flowverses](/weaver/flowverses)
for publishing one.

### The flow in the package {#the-flow-in-the-package}

| Flow | Roles | What it does |
| --- | --- | --- |
| [`chat`](/flows/chat) | `assistant`, and `human` (you) | One agent, one session, and every line typed between turns is a turn of it. |

`chat` is the one flow the interface opens on, and so ships in the package rather than the
flowverse. It is special twice over: it is **granted everything its harness serves**,
whatever it declares, since it talks to any harness; and it **runs with no budget**, as
`Budget(cost=math.inf)`. No other flow is either.

### The official flowverse {#the-official-flowverse}

Everything else humanize offers is in
[humanfia/flowverse](https://github.com/humanfia/flowverse), fetched in the background each
time `hmz` starts, or with <kbd>r</kbd> at `/flowverses`. [Flows](/flows/) draws the shape of
each.

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
| [`ralph_loop_agent_cleanup`](/flows/agent-cleanup) | `agent`, `cleaner`, `human` | `SteeringAgentMixin` on both agents | ✓ |
| [`flame_chase_agent_cleanup`](/flows/agent-cleanup) | `first_chaser`, `second_chaser`, `cleaner`, `human` | `SteeringAgentMixin` on all three agents | ✓ |
| [`recursive_lean_prover`](/flows/recursive-lean-prover) | `worker`, `reviewer` | `worker`: `PermissionRequestHookAgentMixin` | ✓ |
| [`aot`](/flows/aot) | `writer`, `critic`, `human` | | |

A `human` role is [the person at the prompt](#the-person-at-the-prompt), and every one of these
has a `workspace` role that is the directory the run was started in; the runtime fills both.
None declares a budget of its own: the run's `-b` is what stops the ones that do not stop
themselves. Their source, in `~/.humanize/flowverses/official/flows/` once fetched, is the best
example of this API there is. Read [Security](/user/security) before starting any of them.

## Running one {#running-one}

```sh
hmz exec -f <flow> -a <role>=<harness>[@<account>]/<model>:<effort> [-a …] \
    [-e <role>=<backend>@<provider>/<workdir>] [-p <key>=<value>] \
    -b duration=…,cost=…,output_tokens=…[,graceful=…] [--resume] [--json] <task>
```

One `-a` per agent role and one `-e` per environment role, by name; `-p` for its params; `-b`
for its budget, required for every flow but `chat`. Each flag may be repeated and takes a
comma list. Roles the runtime fills (`Outworlder` and `LocalEnv`) are never named. Full
syntax in the [CLI reference](/reference/cli).

In the interface, `/flow` picks one by name, then asks for each role's agent, each
environment, its params and its budget.

From Python, [`Hmz().run`](/reference/sdk#hmz-run) is what `hmz exec` calls:

```python
from hmz.sdk import Hmz

run = Hmz().run(
    "rlar",
    "fix the build",
    agents={"actor": "claude/claude-opus-5:high", "reviewer": "codex/gpt-5.6-sol:high"},
    budget={"cost": 20},
)
run.run()
```

It checks everything before anything starts (the flow, every required role, each harness
against its role, the params, the budget), reaches every environment, writes the run into an
[epic](/reference/tracing#epics) as it goes, and closes every session and removes every copy
it made before it returns or raises.

## Stopping {#stopping}

A flow ends when it returns. Many never do, and are ended from outside:

- **its budget**, which every run but `chat` has;
- <kbd>ctrl+c</kbd>: once under `hmz exec`, twice in the interface;
- [`Run.stop()`](/reference/sdk#run) from Python.

A stop cancels the flow where it is waiting. The turn under way is interrupted (the CLI stops
spending) and the cancellation unwinds through the flow as through any coroutine: `finally`
runs and a `TaskGroup` cancels its siblings. Every session is closed on the way out, and every
copy and scratch directory removed, unless the run is resumable, which keeps them and its
journal for `--resume`. What the turn was doing is left where it got to.

## Testing a flow {#testing-a-flow}

A flow is tested the way it is run, through the engine and granted what it declared, with the
drivers underneath swapped for in-memory fakes: no coding agent, no machine, no tokens and no
time.

```python
import pytest

from hmz.flows import Budget, CostExceeded
from hmz.sdk import fakes


async def test_the_loop_is_held_to_its_budget():
    agent = fakes.FakeAgentDriver(cost=1.0)
    with pytest.raises(CostExceeded):
        await fakes.run_fake("my_loop", "go", agents={"agent": agent}, budget=Budget(cost=2.5))
    assert len(agent.prompts) == 3        # the third turn finished; the fourth was refused
```

`fakes` is imported from `hmz.sdk` as a module: `from hmz.sdk import fakes`. The dotted
`hmz.sdk.fakes` is not importable. See [Testing a flow](/weaver/testing-flows) for the guide.

### `run_fake` {#run-fake}

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
    recorder: Recorder | None = None,
) -> Any
```

| Parameter | |
| --- | --- |
| `flow` | The flow, or a ref loaded from where `run_fake` is called, as [`load`](#load) does. |
| `task` | What to do. |
| `agents` | By role: a driver, or what a `FakeAgentDriver` for the role [replies](#fakeagentdriver). A role left out gets a fake of the harness it asks for (Claude Code otherwise) replying `"ok"`. An `Outworlder` role given a reply is the run's outworlder. |
| `envs` | By role: a driver, or the files a `FakeEnvDriver` for it starts with. A role left out gets an empty one, large enough for what its role asks of a machine. |
| `params` | The params, or a mapping of them. The defaults where `None`. |
| `budget` | What the run may spend. Unlimited where `None`. |
| `outworlder` | Who fills `Outworlder` roles. An away one where `None`. |
| `local` | What fills `LocalEnv` roles. An empty `FakeEnvDriver(workdir="/here")` where `None`. |
| `journal` | Where a resumable flow's journal is written, or `None`. |
| `resume` | Pick up the run `journal` holds. Run twice on one journal to test [resuming](#a-flow-that-can-be-picked-up). |
| `recorder` | <Badge type="info" text="internal" /> An object hearing of every call and session: `entered(call)`, `left(call, error)`, `spawned(call, role, session, driver)`, and optionally `began`, `named`, `closed`. |

Returns what the flow returned. A `NotRequired` role nobody gave is left out, as on a command
line. A turn costs what its fake is told to, reported as a real one is, so budgets, usage and
sticky exhaustion behave as they would.

### `FakeAgentDriver` {#fakeagentdriver}

```python
FakeAgentDriver(
    harness: HarnessKind | str = "claude",
    *,
    reply: Reply = None,
    model: str = "fake",
    effort: str = "",
    provider: str = "",
    capabilities: Iterable[type] | None = None,
    cost: float = 0.0,
    output_tokens: int = 1,
    seconds: float = 0.0,
    forks: bool = True,
    names_late: bool = False,
)
```

| Parameter | |
| --- | --- |
| `harness` | Which harness it is. It serves that harness's mixins unless `capabilities` says otherwise. |
| `reply` | What it answers: one answer for every turn, a list taken one per turn, or a function `(prompt, *, output_schema, session)`, sync or async. An answer is text, a pydantic model, or a mapping or JSON text read into the schema asked for. `None`, or a list run out, answers `"ok"` or the schema's defaults. |
| `model`, `effort`, `provider` | What it says it runs. |
| `capabilities` | The mixins it serves, where not its harness's own. |
| `cost`, `output_tokens`, `seconds` | What each answer is reported to spend. Nothing actually waits. |
| `forks` | Whether it can fork a session. |
| `names_late` | Its sessions have no id until their first turn starts, as a real CLI's do. |

| Attribute | |
| --- | --- |
| `prompts` | Every prompt any of its sessions was given, hooks' context and blocking `STOP` reasons included. |
| `sessions` | Every [`FakeSession`](#fakesession) it opened, in order. |
| `live`, `peak` | How many sessions are open now, and the most that were at once. |
| `closed` | How many times it was closed. |

```python
async def reply(prompt, *, output_schema, session):
    if output_schema is Verdict:
        return {"done": True}
    return f"did: {prompt}"

coder = fakes.FakeAgentDriver("codex", reply=reply, cost=0.5)
```

### `FakeSession` {#fakesession}

One session of a `FakeAgentDriver`, handed to a reply function as `session=`. Every turn fires
`SESSION_START` (the first), `USER_PROMPT_SUBMIT` and `STOP`, and closing fires `SESSION_END`;
a `STOP` hook that blocks keeps the turn going. A reply reaches the other moments through it:

| Method | Fires |
| --- | --- |
| `await tool(name, input=None) -> bool` | `PRE_TOOL_USE`, then `PERMISSION_REQUEST` where served. Answers whether the tool would run. |
| `await ask(question, options=()) -> str \| None` | `ASK_USER`, where served. Answers the hook's answer. |
| `await notify(message)` | `NOTIFICATION`. |
| `await subagent(name, task="", said="") -> str` | `SUBAGENT_START` and `SUBAGENT_STOP`, where served. |
| `await until_steered() -> str` | Nothing: waits for a `steer`, and answers with it. |

Its attributes say what happened: `prompts`, `requests`, `steered` (each prompt, and whether it
was queued), `tools` (each name, input and whether it ran), `forked_from`, `permission`,
`skills`, `closed`, `id` and `usage`.

::: warning A reply that waits on `until_steered()` waits for good
If nothing steers it, the turn never ends. Give such a test a hard deadline, which cuts the
turn off with `DurationExceeded`:
`budget=Budget(duration=timedelta(seconds=5), graceful=False)`.
:::

### `FakeEnvDriver` {#fakeenvdriver}

```python
FakeEnvDriver(
    files: Mapping[str, bytes | str] | None = None,
    *,
    workdir: str | PurePosixPath = "/work",
    backend: EnvBackendKind | str = "local",
    provider: str = "",
    capabilities: Iterable[type] | None = None,
    cpu_count: int = 8,
    memory: int = 64 << 30,
    gpu_count: int = 0,
    gpu_memory: int = 0,
    run: Handler = None,
    refs: Iterable[str] = ("HEAD", "main"),
    repo: bool = True,
)
```

| Parameter | |
| --- | --- |
| `files` | What is in the workdir to start with, by path relative to it. Text is written as UTF-8. |
| `workdir`, `backend`, `provider` | Where it says it is. |
| `capabilities` | The mixins it serves; all of them by default. |
| `cpu_count`, `memory`, `gpu_count`, `gpu_memory` | What its machine reports. |
| `run` | What answers `exec`: a table of commands (an argv as a tuple, or a script) to `(status, stdout, stderr)`, or a function `(command, env)`, sync or async, answering `None` to fall through to the defaults. |
| `refs` | The git refs `derive_worktree` knows. |
| `repo` | Whether the workdir is a git repository. |

Commands `run` leaves are answered by default: `true`, `false`, `echo`, `cat`, `ls`,
`sleep N` and `git rev-parse --is-inside-work-tree` as you would expect, any other program
with status 127, and any other script with 127 (scripts are answered by `run=`, not
interpreted).

| Attribute | |
| --- | --- |
| `files` | What is under the workdir now, by relative path. |
| `text(path)` | One file, as text. |
| `machine` | Every file on the fake machine, copies and worktrees included, by absolute path. |
| `commands` | Every command run in this workdir, in order. |
| `clones`, `scratches` | The ids of the copies and scratch directories made here and not yet removed. |

```python
repo = fakes.FakeEnvDriver({"README.md": "hi"}, run={("make", "test"): (0, "ok\n", "")})
```

### `FakeOutworlder` {#fakeoutworlder}

```python
FakeOutworlder(reply: Reply = None, *, away: bool = False)
```

The person outside the run, answering from a script like a `FakeAgentDriver`'s (a function is
given `output_schema=`), or away. `asked` is every prompt they were asked.

```python
person = fakes.FakeOutworlder(["more", "done", ""])
await fakes.run_fake(talk, "hello", outworlder=person)
```

<style>
.harness-matrix table {
  font-size: 13px;
}
.harness-matrix th,
.harness-matrix td {
  padding: 6px 8px;
}
</style>

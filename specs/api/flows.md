# Flow API

## 1. Scope

This document governs the Python module `hmz.flows`: every name it exports, the signature and
behaviour of each, how a flow is declared, defined, loaded, called and resumed, what a flow
observes of its agents, sessions, turns, hooks and environments, the budget a flow runs under,
the grammar and resolution of a flow ref, the sources flows are found in, and every exception
the module defines.

Out of scope:

- The `hmz exec` command line, including the `-a`, `-e` and `-p` grammars, `--resume` and exit
  statuses: `api/cli.md`.
- The `hmz.sdk` package, including the in-memory fakes for testing a flow: `api/sdk.md`.
- The layout and format of files hmz writes, including the progress record of a resumable
  epic, kept conversations, flowverse clones and installed flows: `api/files/home.md`,
  `api/files/epics.md`, `api/files/machine.md`.
- How a permission is enforced on a harness (the fence and the harness's approval rung), the
  harness configuration layering, and each harness's accepted models and efforts:
  `features/agents.md`.
- Accounts a turn runs as: `features/accounts.md`.
- Where a session's harness runs (placements, harness settings, mirrors): `features/placements.md`.
- Environment backends, runtimes, and how resources size a container or job:
  `features/environments.md`.
- Which epic a resume picks up, and what an epic records: `features/epics.md`.
- The behaviour of the `chat` flow: `features/chat.md`.

## 2. Definitions

Terms defined in `README.md` (among them **hmz**, **user**, **machine**, **this machine**,
**home**, **workspace**, **flow**, **flow author**, **epic**, **role**, **agent**, **harness**,
**harness machine**, **env**, **env machine**, **placement**, **mirror**, **runtime**,
**account**, **session**, **side question**) are used with the meaning given there.

**2.1** **Flow function**: the `async` function to which the decorator returned by `flow`
(§4.1) is applied.

**2.2** **Flow object**: an object satisfying the `Flow` protocol (§4.3), as returned by `flow`
or by `load`.

**2.3** **Flow call**: one awaited invocation of a flow object. The **top call** of an epic is
the flow call hmz makes to start the epic; every other flow call is made by a flow function and
is a **nested call**. For a nested call, the flow call whose flow function made it is the
**caller** and the nested call is the **callee**.

**2.4** **Role type**: the class annotating one key of an `AgentCollection` or `EnvCollection`
subclass.

**2.5** **Mixin**: a class exported by `hmz.flows` whose name ends in `AgentMixin` or
`EnvMixin`. A role type **declares** a mixin when the mixin is among the role type's bases,
directly or through another mixin.

**2.6** **Harness protocol**: one of the classes that are values of `HARNESS_AGENTS` (§6.4)
other than `Agent`.

**2.7** **Runtime-filled role**: an agent role whose role type is `Outworlder` or a subclass of
it, or an environment role whose role type is `LocalEnv` or a subclass of it.

**2.8** **Handed object**: an object hmz passes to a flow function or hook as an agent, an
environment, a session, a flow context or a flow state. A handed object satisfies the
corresponding protocol of `hmz.flows` structurally and is not an instance of that protocol.

**2.9** **Grant**: the set of mixins, the `Permission`, the skills, the fake tools and the fake
command lines that a handed agent or environment allows a flow to use.

**2.10** **Turn**: one awaited call of `Agent.run` (§8.2), from the moment it is called until it
returns or raises.

**2.11** **Moment**: a point in a session at which a hook is called; one member of `HookKind`
(§9.1).

**2.12** **Hook**: an `async` callable that hmz calls at one moment of every session of one
agent.

**2.13** **Ref**: a string naming a flow, of the grammar in §13.2.

**2.14** **Flow source**: one place hmz finds flows in: `local`, `user`, `official`, or another
flowverse (§14).

**2.15** **Flowverse**: a named flow source. A flowverse other than `local` and `user` is backed
by an **index**: a git repository of release manifests (§14.4).

**2.16** **Resumable flow**: a flow defined with `resumable=True`.

**2.17** **Resumed call**: a flow call that picks up a flow call of an earlier epic (§5.4).

**2.18** **Kept session**: a session written into a flow state (§5.3).

**2.19** **Effective budget**: the limits a flow call or turn is held to, combining its own
budget with every budget above it (§12.2).

**2.20** **Away**: the state of an outworlder in which no person answers it (§10.2).

**2.21** **The epic's workspace environment**: the environment whose workdir is the workspace
the epic was started in, on this machine.

## 3. Module surface

### 3.1 Importing

**3.1.1** `hmz.flows` MUST be importable without importing any module of hmz other than
`hmz.flows`, its submodules and `hmz.coganchor.faking`.

**3.1.2** `hmz.flows.__all__` MUST list exactly the names in §3.2, and each MUST be importable
from `hmz.flows`.

**3.1.3** Every class of `hmz.flows` documented in this specification as a protocol MUST be a
`typing.Protocol`. A handed object MUST satisfy its protocol and every mixin of its grant
structurally.

**3.1.4** A handed agent or environment MUST allow exactly its grant. An operation that needs a
mixin absent from the grant MUST raise `CapabilityNotGranted`, whether or not the harness or
machine underneath supports the operation.

**3.1.5** The message of an exception raised by hmz is informative. No clause of this
specification constrains a message's wording unless the clause quotes it.

### 3.2 Exported names

**3.2.1** The exported names, grouped by the section that specifies them, MUST be:

| Group | Names | Section |
| --- | --- | --- |
| Defining | `flow`, `Flow`, `FlowFn`, `FlowParams`, `FlowContext`, `FlowState`, `load` | §4, §5, §13 |
| Agents | `AgentCollection`, `Agent`, `Session`, `Outworlder`, `HarnessKind`, `HARNESS_AGENTS` | §6, §8, §10 |
| Harness protocols | `ClaudeCodeAgent`, `CodexAgent`, `CursorAgent`, `OpenCodeAgent`, `MiMoCodeAgent`, `MiniMaxCodeAgent`, `QwenCodeAgent`, `KimiCodeAgent`, `GrokBuildAgent`, `PiAgent`, `OhMyPiAgent`, `AntigravityAgent`, `DeepSeekHarnessAgent`, `LiteLLMAgent` | §6.4 |
| Agent mixins | `FakeToolAgentMixin`, `GoalCommandAgentMixin`, `LoopCommandAgentMixin`, `SteeringAgentMixin`, `PermissionRequestHookAgentMixin`, `SubagentStartHookAgentMixin`, `SubagentStopHookAgentMixin`, `AskUserHookAgentMixin` | §6.5 |
| Fake tools and command lines | `FakeTool`, `FakeCli`, `FakeCommand` | §6.6 |
| Permissions | `Permission`, `PermissionKind` | §7 |
| Budgets | `Budget`, `Usage` | §12 |
| Environments | `EnvCollection`, `Env`, `LocalEnv`, `EnvBackendKind`, `SequenceNotStr` | §11 |
| Environment mixins | `ShellEnvMixin`, `BashEnvMixin`, `FilesEnvMixin`, `GitWorktreeEnvMixin`, `TemporaryClonedDirEnvMixin`, `ScratchDirEnvMixin`, `RewindableEnvMixin`, `GitEnvMixin`, `CPUEnvMixin`, `MemoryEnvMixin`, `GPUEnvMixin`, `ImageEnvMixin` | §11.5–§11.8 |
| Hooks | `HookKind`, `HookFn`, `HookParams`, `HookResult`, `HOOK_TYPES`, and `<Moment>HookParams`, `<Moment>HookResult` for each of the eleven moments | §9 |
| Exceptions | `FlowException` and every class under it | §15 |

**3.2.2** `FakeTool`, `FakeCli` and `FakeCommand` exported by `hmz.flows` MUST be the same class
objects as those exported by `hmz.coganchor.faking`.

## 4. Defining a flow

### 4.1 `flow`

```python
def flow[A: AgentCollection, E: EnvCollection, P: FlowParams](
    *,
    agents: type[A],
    envs: type[E],
    params: type[P],
    name: str | None = None,
    description: str | None = None,
    hidden: bool = False,
    resumable: bool = False,
) -> Callable[[FlowFn[A, E, P]], Flow]: ...
```

**4.1.1** `flow` MUST return a decorator. The decorator, applied to a flow function, MUST return
a flow object.

**4.1.2** `agents` declares the flow's agent roles, `envs` its environment roles, and `params`
its params model. A flow that takes no params MUST pass `FlowParams` itself.

**4.1.3** The flow's name MUST be `name` where `name` is not `None`, and the flow function's
`__name__` otherwise. The flow's name MUST match the regular expression
`[A-Za-z0-9_][A-Za-z0-9_.-]*`.

**4.1.4** The flow's description MUST be `description` where it is not `None`; otherwise the
first line of the flow function's docstring where the function has one; otherwise `None`.

**4.1.5** A flow defined with `hidden=True` MUST NOT be listed by any frontend's list of flows.
It MUST still be loadable by its ref and runnable.

**4.1.6** A flow defined with `resumable=True` MUST be given a flow state (§5.2) and MUST be
eligible for resumption (§5.4). A flow defined with `resumable=False` MUST NOT.

**4.1.7** The decorator MUST raise `FlowDefinitionError` when any of the following holds, and
MUST NOT return a flow object:

1. The function is not a coroutine function.
2. The function's signature cannot be read.
3. The function has no positional first parameter.
4. The function accepts any of `agents`, `envs`, `params`, `ctx` neither as a keyword
   parameter nor through `**kwargs`.
5. The function has a parameter other than the first positional one and the four of item 4
   that has no default.
6. `agents` is not a subclass of `AgentCollection`.
7. `envs` is not a subclass of `EnvCollection`.
8. `params` is not a subclass of `FlowParams`.
9. `params` declares a field or an alias named `budget`.
10. The flow's name does not match the expression of clause 4.1.3.

**4.1.8** hmz MUST resolve the role annotations of `agents` and `envs` no earlier than the first
time the flow is called or described, against the global and local namespaces in which `flow`
was called. Annotations written as strings, `from __future__ import annotations`, and
collections declared inside a function MUST resolve. `NotRequired`, `Required`, `ReadOnly` and
`Annotated` wrappers MUST be read through.

**4.1.9** On resolving the role annotations, hmz MUST raise `FlowDefinitionError` when any of the
following holds:

1. An annotation is a string that does not resolve.
2. An annotation is not a class.
3. An agent role type is not a subclass of `Agent`.
4. An environment role type is not a subclass of `Env`.
5. An agent role type declares an environment mixin, or an environment role type declares an
   agent mixin.
6. An agent role type derives from two distinct harness protocols.
7. An `Outworlder` role type derives from a harness protocol or declares a mixin.
8. An agent role type's `_permission` is not a `Permission`.
9. An agent role type's `_skills` is not a tuple or list of non-empty strings.
10. An agent role type's `_tools` is not a tuple or list of `FakeTool`, names two tools of one
    name, or is non-empty on a role type that does not declare `FakeToolAgentMixin`.
11. An agent role type's `_clis` is not a tuple or list of `FakeCli`, names two command lines
    of one name, or is non-empty on a role type that is `LiteLLMAgent`, a subclass of it, or
    an `Outworlder`.
12. An environment role type's `_cpu_count`, `_memory`, `_gpu_count` or `_gpu_memory`, where
    its mixin is declared, is not an `int` of at least 0, or is a `bool`.
13. An environment role type's `_image`, where `ImageEnvMixin` is declared, is not a string
    without whitespace.

**4.1.10** Where one module defines two flows of one name, hmz MUST raise `FlowDefinitionError`
when the module's flows are enumerated. Where two flow functions of one module bind one Python
name, the later binding MUST replace the earlier.

### 4.2 `FlowFn`

```python
class FlowFn[A: AgentCollection, E: EnvCollection, P: FlowParams](Protocol):
    async def __call__(
        self, task: str, *, agents: A, envs: E, params: P, ctx: FlowContext
    ) -> Any: ...
```

**4.2.1** hmz MUST call a flow function with the task as its first positional argument and
`agents`, `envs`, `params` and `ctx` as keyword arguments.

**4.2.2** `agents` MUST be a mapping from role name to handed agent, holding one entry per agent
role that was given or that hmz filled. `envs` MUST be the same for environment roles. A
`NotRequired` role that was neither given nor filled MUST be absent from the mapping.

**4.2.3** `params` MUST be an instance of the flow's params model. `ctx` MUST be the flow call's
`FlowContext`.

**4.2.4** The value the flow function returns MUST be the value of the flow call.

### 4.3 `Flow`

```python
class Flow(Protocol):
    @property
    def description(self) -> str | None: ...
    @property
    def expected_agents(self) -> type[AgentCollection]: ...
    @property
    def expected_envs(self) -> type[EnvCollection]: ...
    @property
    def expected_params(self) -> type[FlowParams]: ...
    @property
    def resumable(self) -> bool: ...
    async def __call__(
        self,
        task: str,
        *,
        agents: AgentCollection,
        envs: EnvCollection,
        params: FlowParams,
        budget: Budget | None = None,
    ) -> Any: ...
```

**4.3.1** `description` MUST be the flow's description (clause 4.1.4). `expected_agents`,
`expected_envs` and `expected_params` MUST be the classes passed to `flow` as `agents`, `envs`
and `params`. `resumable` MUST be the value passed to `flow` as `resumable`.

**4.3.2** Calling a flow object is specified in §13.4.

### 4.4 `FlowParams`

```python
class FlowParams(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid", ser_json_inf_nan="strings")
```

**4.4.1** A flow author MUST declare a flow's params as fields of a subclass of `FlowParams`.

**4.4.2** Validation of a params model MUST refuse a key the model does not declare.

**4.4.3** Serialization of a params model MUST write an infinite or NaN float as the string
`"Infinity"`, `"-Infinity"` or `"NaN"`.

**4.4.4** Where hmz is given params for a flow call, it MUST read them as follows, in order:

1. An instance of the flow's own params model MUST be used as it is.
2. An instance of another `pydantic.BaseModel` MUST be dumped and validated into the model.
3. A mapping MUST be validated into the model. Where validation fails, each value that is a
   `str` and whose field failed MUST be parsed as JSON where it is JSON, and the mapping MUST be
   validated once more.
4. Any other value MUST raise `ParamsError`.

**4.4.5** A params value that fails validation under clause 4.4.4 MUST raise `ParamsError`.

## 5. Flow context, state and resumption

### 5.1 `FlowContext`

```python
class FlowContext(Protocol):
    @property
    def budget(self) -> Budget: ...
    @property
    def flow(self) -> Flow: ...
    @property
    def resumed(self) -> bool: ...
    @property
    def state(self) -> FlowState | None: ...
    @property
    def usage(self) -> Usage: ...
```

**5.1.1** Each flow call MUST have a context of its own.

**5.1.2** `flow` MUST be the flow object being called.

**5.1.3** `budget` MUST be the flow call's effective budget (§12.2) as of the moment it is read.

**5.1.4** `usage` MUST be what the flow call and every flow call under it have spent, as of the
moment it is read.

**5.1.5** `state` MUST be the flow call's `FlowState` for a resumable flow, and `None` otherwise.

**5.1.6** `resumed` MUST be `True` where the flow call is a resumed call, and `False` otherwise.

### 5.2 `FlowState`

```python
class FlowState(Protocol):
    def __getitem__(self, key: str) -> Any: ...
    def __setitem__(self, key: str, value: Any) -> None: ...
    def __delitem__(self, key: str) -> None: ...
    def __contains__(self, key: str) -> bool: ...
```

**5.2.1** `state[key] = value` MUST raise `StateNotSerializable` where `key` is not a `str`, and
where `value` cannot be serialized as JSON with infinities and NaN allowed. A refused write
MUST leave the state unchanged.

**5.2.2** What `state[key]` returns after `state[key] = value` MUST be the JSON round trip of
`value`, so that a fresh epic and a resumed one read identical values.

**5.2.3** Every write and every deletion MUST be durable before `__setitem__` or `__delitem__`
returns, so that an epic stopped or killed afterwards and then resumed reads the state as it
was at that write.

**5.2.4** `state[key]` and `del state[key]` MUST raise `KeyError` where nothing is kept under
`key`. `key in state` MUST be `True` exactly where something is kept under `key`.

**5.2.5** Mutating a value read from the state MUST NOT change the state. A flow MUST assign the
value again for the change to be kept.

**5.2.6** A resumable flow called where no progress is recorded (a nested call under a top call
of a flow that is not resumable) MUST be given a state held only for the epic's lifetime.

### 5.3 Sessions in state

**5.3.1** A flow MUST be able to write a `Session` into its state, alone or anywhere inside a
value. Such a write MUST keep the session's conversation as it stands at the write, and MUST
NOT be affected by any turn the session takes afterwards.

**5.3.2** The write of clause 5.3.1 MUST raise `StateNotSerializable`, and MUST write nothing,
where any of the following holds:

1. The session has taken no turn.
2. A turn of the session is under way.
3. The session is closed.
4. The session belongs to an agent handed to a flow call other than the one whose state is
   written.
5. The session is an outworlder's.
6. The session's harness does not fork (§6.4).
7. The session's harness does not keep its conversations as files (`opencode`, `mimo`).
8. The session's last turn ran with harness location env or standalone.

**5.3.3** Every read of a key whose value holds a kept session MUST return a new session of the
reading call's agent of the same role. The first turn of that new session MUST carry the kept
conversation on, from where it stood when written, as a fork.

**5.3.4** A kept session MUST be readable, and carried on, in the epic that wrote it and in every
epic that resumes that epic. Several epics MUST be able to carry on one kept session, each
independently.

**5.3.5** The first turn of a session read back under clause 5.3.3 MUST raise
`UnsupportedOperation`, before its harness is started and before anything is copied, where any
of the following holds:

1. The role's agent is of a harness other than the one that kept the conversation.
2. The turn's harness location is env or standalone.
3. The turn's harness location is local and its env location standalone, its harness forks
   only in place (§6.4), and the turn's environment backend is `docker`, `swarm`, `slurm` or
   `apple-container`.

**5.3.6** The first turn of a session read back under clause 5.3.3 MUST raise `SessionError`
where the kept conversation no longer exists, or where the epic already holds a different copy
of that conversation that carrying this one on would replace.

**5.3.7** A session read back under clause 5.3.3 and written into the state again before it takes
a turn MUST be written as the kept conversation it carries on, without copying anything.

### 5.4 Resumption

**5.4.1** An epic MUST be resumable exactly where its top call is of a resumable flow. How a user
asks
for a resume, and which epic is picked up, is specified in `api/cli.md` and
`features/epics.md`.

**5.4.2** A resumed epic MUST be a new epic. The top call of a resumed epic MUST be a resumed call
of the earlier epic's top call, unconditionally.

**5.4.3** A nested call made under a resumed call MUST be a resumed call of the earlier epic's
nested call that has the same caller, the same callee ref, the same task, the same agents, the
same environments and the same params, taking such calls in the order they were made. Where
no earlier call remains unclaimed, the nested call MUST start afresh with an empty state.

**5.4.4** For clause 5.4.3, two agents MUST be the same where they have the same harness,
account, model, effort, permission and skills, and two environments MUST be the same where
they were derived by the same chain of derivations (§11.6) from the same backend, provider and
workdir. An outworlder made with `Outworlder.new()` MUST NOT be the same as the epic's own
outworlder.

**5.4.5** A resumed call of a resumable flow MUST see the state its earlier call had when that
epic ended. A flow that is not resumable MUST have no state, and its nested calls MUST still be
eligible for resumption.

**5.4.6** Temporary copies and scratch directories (§11.6) made by an epic whose top call is of a
resumable flow MUST be kept when the epic ends, and a resumed call that derives one by the same
id MUST be given the same directory.

## 6. Agents

### 6.1 `AgentCollection`

```python
class AgentCollection(TypedDict, extra_items=ReadOnly[Agent]): ...
```

**6.1.1** A flow author MUST declare a flow's agent roles as the keys of a subclass of
`AgentCollection`, each annotated with its role type.

**6.1.2** A role annotated `NotRequired[...]` MAY be left out by whoever runs or calls the flow.
Every other role that is not runtime-filled MUST be given.

**6.1.3** An `Outworlder` role MUST be filled by hmz (§10.1) and MUST NOT be given on the command
line.

### 6.2 `Agent`

```python
class Agent(Protocol):
    _permission: ClassVar[Permission] = Permission()
    _skills: ClassVar[tuple[str, ...]] = ()
    _tools: ClassVar[tuple[FakeTool, ...]] = ()
    _clis: ClassVar[tuple[FakeCli, ...]] = ()

    @property
    def effort(self) -> str: ...
    @property
    def harness(self) -> HarnessKind: ...
    @property
    def model(self) -> str: ...
    @property
    def role(self) -> str: ...
    @property
    def provider(self) -> str: ...

    def derive(
        self, *, permission: Permission | None = None, skills: tuple[str, ...] | None = None
    ) -> Self: ...
    async def spawn(self) -> Session: ...
    async def fork(self, session: Session) -> Session: ...
    @overload
    async def run(
        self, prompt: str, *, session: Session, env: Env | None = None,
        budget: Budget | None = None,
    ) -> str: ...
    @overload
    async def run[T: pydantic.BaseModel](
        self, prompt: str, *, session: Session, env: Env | None = None,
        output_schema: type[T], budget: Budget | None = None,
    ) -> T: ...
    # Each takes HookFn[<Moment>HookParams, <Moment>HookResult] | None for its moment (§9).
    def on_session_start(self, fn: HookFn[...] | None) -> None: ...
    def on_user_prompt_submit(self, fn: HookFn[...] | None) -> None: ...
    def on_pre_tool_use(self, fn: HookFn[...] | None) -> None: ...
    def on_notification(self, fn: HookFn[...] | None) -> None: ...
    def on_stop(self, fn: HookFn[...] | None) -> None: ...
    def on_session_end(self, fn: HookFn[...] | None) -> None: ...
```

**6.2.1** The class attributes `_permission`, `_skills`, `_tools` and `_clis` are part of the
public API: a flow author MUST set them on a role type to declare the role's permission
(§7), skills (§6.7), fake tools and fake command lines (§6.6).

**6.2.2** A handed agent's sessions MUST run under exactly its role type's `_permission`, MUST be
given exactly its role's skills, MUST offer exactly its role's `_tools`, and MUST put exactly
its role's `_clis` on the agent's `PATH`.

**6.2.3** `role` MUST be the key of the `AgentCollection` the agent fills.

**6.2.4** `harness` MUST be the agent's `HarnessKind`.

**6.2.5** `model` MUST be the model as it was given.

**6.2.6** `effort` MUST be the effort in the harness's own words, and `""` where none was given
or the effort given was `auto`.

**6.2.7** `provider` MUST be the name of the account the agent's turns run as, and `""` where
the turns run as the account the harness is already signed into on the harness machine.

**6.2.8** `spawn`, `fork` and `run` are specified in §8, `derive` in §7.3, and the `on_*` methods
in §9.

### 6.3 `HarnessKind`

```python
class HarnessKind(StrEnum):
    CLAUDE = "claude"
    CODEX = "codex"
    CURSOR_AGENT = "cursor-agent"
    OPENCODE = "opencode"
    MIMO = "mimo"
    MCODE = "mcode"
    QWEN = "qwen"
    KIMI = "kimi"
    GROK = "grok"
    PI = "pi"
    OMP = "omp"
    AGY = "agy"
    DSH = "dsh"
    LITELLM = "litellm"
    ACP = "acp"
```

**6.3.1** `HarnessKind` MUST have exactly the members above with exactly the values above. Each
value MUST be the name by which the command line names that harness.

**6.3.2** `LITELLM` MUST denote a model called directly, one chat completion per turn over the
session's history, with no tools, no shell and no filesystem.

**6.3.3** `ACP` MUST denote a harness that a user added by hand and that hmz drives over the Agent
Client Protocol.

### 6.4 Harness protocols and `HARNESS_AGENTS`

```python
HARNESS_AGENTS: Mapping[HarnessKind, type]
```

**6.4.1** `HARNESS_AGENTS` MUST be a read-only mapping from every `HarnessKind` to its harness
protocol, as in the table of clause 6.4.2, and MUST map `ACP` to `Agent`.

**6.4.2** Each harness protocol MUST derive from `Agent` and from exactly the mixins marked for it
below, and every harness MUST serve exactly the mixins marked for it:

| Kind | Protocol | Goal | Loop | Steer | Perm. request | Subagent start/stop | Ask user | Fake tools |
| --- | --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| `claude` | `ClaudeCodeAgent` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `codex` | `CodexAgent` | ✓ | | ✓ | ✓ | ✓ | ✓ | ✓ |
| `cursor-agent` | `CursorAgent` | | | | | ✓ | | |
| `opencode` | `OpenCodeAgent` | | | | | | | ✓ |
| `mimo` | `MiMoCodeAgent` | | | | | | | ✓ |
| `mcode` | `MiniMaxCodeAgent` | | | | | ✓ | | |
| `qwen` | `QwenCodeAgent` | | | | | | | ✓ |
| `kimi` | `KimiCodeAgent` | ✓ | | ✓ | ✓ | | ✓ | |
| `grok` | `GrokBuildAgent` | | | | | | | ✓ |
| `pi` | `PiAgent` | | | ✓ | | | ✓ | ✓ |
| `omp` | `OhMyPiAgent` | | | ✓ | | | ✓ | ✓ |
| `agy` | `AntigravityAgent` | | | | | | | ✓ |
| `dsh` | `DeepSeekHarnessAgent` | ✓ | | | | | | ✓ |
| `litellm` | `LiteLLMAgent` | | | | | | | |
| `acp` | `Agent` | | | | | | | |

The columns are, in order, `GoalCommandAgentMixin`, `LoopCommandAgentMixin`,
`SteeringAgentMixin`, `PermissionRequestHookAgentMixin`, `SubagentStartHookAgentMixin` together
with `SubagentStopHookAgentMixin`, `AskUserHookAgentMixin` and `FakeToolAgentMixin`.

**6.4.3** Each harness MUST fork sessions to the extent below:

| Fork extent | Harnesses |
| --- | --- |
| into any workdir on the same machine | `claude`, `codex`, `kimi`, `litellm` |
| only in place: into the same workdir | `pi`, `omp`, `grok`, `opencode`, `mimo`, `qwen`, `acp` |
| none | `cursor-agent`, `mcode`, `agy`, `dsh` |

**6.4.4** A role typed as a harness protocol asks for that harness and every mixin marked for it.
Where such a role is given an agent of another harness, hmz MUST refuse: before an epic starts
as specified in `api/cli.md`, and in a nested call with `HarnessMismatch`.

**6.4.5** A role typed as `Agent` with mixins MAY be filled by any harness that serves every
mixin it declares.

**6.4.6** On a `grok` agent whose role offers any fake tool, a turn that only `grok`'s one-shot
mode can take MUST raise `HarnessUnrecoverable`. Such turns are: a turn with an `output_schema`,
the first turn of a fork, a turn whose permission has `online` `NONE`, and a turn whose
permission has `local` `READ` or `NONE`.

### 6.5 Agent mixins

```python
class FakeToolAgentMixin(Protocol): ...
class GoalCommandAgentMixin(Protocol): ...
class LoopCommandAgentMixin(Protocol): ...

class SteeringAgentMixin(Protocol):
    async def steer(self, prompt: str, *, session: Session, queued: bool = True) -> None: ...

class PermissionRequestHookAgentMixin(Protocol):
    def on_permission_request(
        self, fn: HookFn[PermissionRequestHookParams, PermissionRequestHookResult] | None
    ) -> None: ...

class SubagentStartHookAgentMixin(Protocol):
    def on_subagent_start(
        self, fn: HookFn[SubagentStartHookParams, SubagentStartHookResult] | None
    ) -> None: ...

class SubagentStopHookAgentMixin(Protocol):
    def on_subagent_stop(
        self, fn: HookFn[SubagentStopHookParams, SubagentStopHookResult] | None
    ) -> None: ...

class AskUserHookAgentMixin(Protocol):
    def on_ask_user(self, fn: HookFn[AskUserHookParams, AskUserHookResult] | None) -> None: ...
```

**6.5.1** `GoalCommandAgentMixin` MUST grant `run` of a prompt that, with leading whitespace
removed, is `/goal` or starts with `/goal` followed by whitespace. Such a turn MUST hand the
objective to the harness's own goal command, which pursues it until the harness decides it is
met.

**6.5.2** `LoopCommandAgentMixin` MUST grant `run` of a prompt that, with leading whitespace
removed, starts with `/loop`. Such a prompt MUST be passed to the harness as written.

**6.5.3** `run` of a prompt of clause 6.5.1 or 6.5.2 on an agent whose grant lacks the mixin MUST
raise `CapabilityNotGranted` before anything is sent. hmz MUST pass every other prompt to the
harness unchanged and MUST NOT interpret any other slash command.

**6.5.4** `SteeringAgentMixin` MUST grant `steer` (§8.4).

**6.5.5** `PermissionRequestHookAgentMixin`, `SubagentStartHookAgentMixin`,
`SubagentStopHookAgentMixin` and `AskUserHookAgentMixin` MUST grant `on_permission_request`,
`on_subagent_start`, `on_subagent_stop` and `on_ask_user` respectively. Calling one of these on
an agent whose grant lacks its mixin MUST raise `CapabilityNotGranted`.

**6.5.6** `FakeToolAgentMixin` MUST permit a role type to declare a non-empty `_tools`.

### 6.6 Fake tools and fake command lines

```python
@dataclass(frozen=True, slots=True)
class FakeTool:
    name: str
    about: str
    call: Callable[..., Any]
    takes: type[pydantic.BaseModel] | None = None

@dataclass(frozen=True, slots=True)
class FakeCommand:
    name: str
    about: str
    call: Callable[..., Any]
    takes: type[pydantic.BaseModel] | None = None

@dataclass(frozen=True, slots=True)
class FakeCli:
    name: str
    about: str
    commands: tuple[FakeCommand, ...]
    def run(self, argv: Sequence[str]) -> tuple[int, str, str]: ...
```

**6.6.1** Every session of an agent MUST offer each `FakeTool` of its role's `_tools` to the
harness as a tool named `name`, described by `about`, taking the JSON Schema of `takes`, or no
arguments where `takes` is `None`.

**6.6.2** When the agent calls a fake tool, hmz MUST call `call` in the flow's process, on the
flow's event loop, as the flow, with an instance of `takes` built from the arguments, or with
no argument where `takes` is `None`. `call` MAY be synchronous or asynchronous. The turn MUST
wait for it.

**6.6.3** The agent MUST read back the value `call` returns as text: a `str` as it is, `None` as
`done`, and any other value as JSON.

**6.6.4** An exception `call` raises MUST be answered to the agent as the tool failing, and MUST
NOT fail the turn or the flow.

**6.6.5** Fake tools MUST be served only where the harness serves `FakeToolAgentMixin` and its
harness location is local. A turn whose harness location is env or standalone on an agent whose
role offers fake tools MUST raise `UnsupportedOperation`.

**6.6.6** `FakeCli(...)` MUST raise `ValueError` where `name` is empty, starts with `.` or `-`, or
holds a character other than ASCII letters, digits, `.`, `_` and `-`; where `commands` is
empty; or where two commands share a name.

**6.6.7** Every session of an agent MUST put each `FakeCli` of its role's `_clis` on the `PATH`
of every process of the harness, as a program called `name` taking a first argument naming one
of `commands`.

**6.6.8** Each `FakeCommand` MUST take one `--<field>` option per field of `takes`, whose help is
the field's description and which is required where the field has no default. A `bool` field
MUST be a `--<field>`/`--no-<field>` pair, a list field MUST take several words, and a
`Literal` or `Enum` field MUST take one of its values.

**6.6.9** The program MUST print help and exit 0 for `--help`; MUST print usage and an error to
stderr and exit 2 for a line its parser or `takes` refuses; and otherwise MUST call the
command's `call` as clause 6.6.2 specifies for a tool, printing a returned `str` as it is,
nothing for `None`, and any other value as JSON, then exit 0. A `SystemExit(n)` raised by
`call` MUST exit `n`. Any other exception raised by `call` MUST exit 1 with the error on
stderr.

**6.6.10** `FakeCli.run(argv)` MUST return the exit status, stdout and stderr the program
specified in clause 6.6.9 produces for `argv`, the words after the program's name.

**6.6.11** Every harness other than `litellm` MUST serve `_clis` without a mixin. A `run` of a
`litellm` agent whose grant includes any fake command line MUST raise `UnsupportedOperation`.

### 6.7 Skills

**6.7.1** Each entry of a role type's `_skills` MUST be either the name of a directory under the
flow directory's `skills/`, holding a `SKILL.md`, or a git URL, recognised by containing `#` or
`://`. A git URL followed by `#<skill>` MUST select the one skill `skills/<skill>` of the
repository; a git URL without `#` MUST select every skill under its `skills/`.

**6.7.2** hmz MUST resolve a role's skills once per epic and role, before the role's first turn.
A skill named and absent MUST raise `FlowDefinitionError`, as MUST a URL that cannot be fetched
or names no skill of its repository. A single-file flow MUST have no skills of its own.

**6.7.3** Where a flow's own `skills/` and a repository named in `_skills` hold a skill of one
name, the role MUST be given the flow's own.

**6.7.4** An installed flow's skills that its roles name by a URL written as a string literal MUST
be fetched at install and read from the installed flow at run time without fetching.

**6.7.5** hmz MUST make a session's skills available where its harness reads a project's skills,
for the session's lifetime only. hmz MUST NOT install a skill into any harness's user-level
configuration. A harness that reads no project skills MUST be given none.

## 7. Permissions and approval

### 7.1 `PermissionKind`

```python
class PermissionKind(StrEnum):
    NONE = "none"
    READ = "read"
    ALL = "all"
```

**7.1.1** `PermissionKind` MUST be totally ordered `NONE < READ < ALL` under `<`, `<=`, `>` and
`>=`. `NONE` MUST permit nothing, `READ` reading and not writing, and `ALL` reading and writing.

**7.1.2** Comparing a `PermissionKind` with a value that is not one of the three values MUST
raise `TypeError`.

### 7.2 `Permission`

```python
@dataclass(frozen=True, slots=True)
class Permission:
    local: PermissionKind = PermissionKind.ALL
    user: PermissionKind = PermissionKind.READ
    system: PermissionKind = PermissionKind.READ
    online: PermissionKind = PermissionKind.ALL

    def covers(self, other: Permission) -> bool: ...
```

**7.2.1** `Permission` MUST have exactly the four fields `local`, `user`, `system` and `online`,
with exactly the defaults above.

**7.2.2** `local` MUST govern the workdir of the environment a turn works in. `user` MUST govern
the rest of the home directory of the operating-system user the harness runs as. `system` MUST
govern everything else on the machine. `online` MUST govern the network, including the
harness's own web search and fetch tools.

**7.2.3** Construction MUST coerce each field with `PermissionKind(value)`. Construction MUST
raise `ValueError` where a field is not one of the three values, where `local >= user >=
system` does not hold, or where `online` is `READ`.

**7.2.4** `covers(other)` MUST return `True` exactly where each of the four fields is `>=` the
same field of `other`.

**7.2.5** hmz MUST NOT run a session with wider access than its permission. Where neither the
harness nor the machine can hold a session to its permission, opening the session MUST raise
`HarnessSandboxed`. How a permission is held is specified in `features/agents.md`.

### 7.3 `Agent.derive`

**7.3.1** `derive(permission=..., skills=...)` MUST return a new handed agent of the same agent
whose sessions run under `permission`, or under this agent's permission where `permission` is
`None`, and are given `skills`, or all of this agent's skills where `skills` is `None`. The
original agent MUST be unchanged.

**7.3.2** `derive` MUST raise `TypeError` where `permission` is neither `None` nor a
`Permission`. `derive` MUST raise `CapabilityNotGranted` where this agent's permission does not
cover `permission`, and where `skills` names a skill this agent was not granted.

**7.3.3** A derived agent MUST share the original's hooks and sessions: a session of either MUST
be usable by the other, and a hook hung on either MUST cover both.

**7.3.4** A derived agent MUST keep the original's fake tools and fake command lines.

### 7.4 Approval policy

**7.4.1** hmz MUST run every harness with approvals bypassed, so that no session waits for a
person to approve an action.

**7.4.2** hmz MUST NOT run any harness in a mode in which a model reviews or approves the agent's
actions.

**7.4.3** Where a managed policy of the harness forbids bypassing approvals, hmz MUST run the
harness in the most permissive mode that remains and in which no model reviews actions, and
hmz MUST approve every request the harness then makes, subject to clause 7.4.4.

**7.4.4** Where a `PERMISSION_REQUEST` hook is hung, its answer MUST decide the request, overriding
clauses 7.4.1 and 7.4.3.

**7.4.5** What limits an agent's actions MUST be its permission and the hooks the flow hangs on
it, and nothing else of the approval machinery of its harness.

## 8. Sessions and turns

### 8.1 `Agent.spawn` and `Session`

```python
class Session(Protocol):
    @property
    def agent(self) -> Agent: ...
    @property
    def usage(self) -> Usage: ...
```

**8.1.1** `spawn()` MUST return a new session of the agent that has taken no turn. `spawn` MUST
NOT start the harness and MUST NOT settle where the session works; the session's first turn
MUST do both.

**8.1.2** `spawn` MUST raise `FlowCancelled` where the flow call's caller or the epic has ended.

**8.1.3** A session MUST hold a conversation and no environment. Each turn of a session MUST name
the environment it works in.

**8.1.4** `Session.agent` MUST be the agent whose conversation the session is. `Session.usage`
MUST be what the session's turns have spent, as of the moment it is read.

**8.1.5** A session MUST be closed at the earlier of: the end of the flow call that opened it and
of every flow call that call started; and the moment no reference to it remains. A session
MUST be closed exactly once. Closing a session MUST fire `SESSION_END` (§9).

**8.1.6** A session MUST NOT offer a method to close it.

### 8.2 `Agent.run`

**8.2.1** `run(prompt, session=..., env=..., output_schema=..., budget=...)` MUST take one turn in
`session`, working in `env`, and MUST return the text of the agent's last message, or, where
`output_schema` is given, an instance of `output_schema`.

**8.2.2** `env=None` MUST mean the epic's workspace environment. A turn of a `litellm` agent
MUST be given `env=None`.

**8.2.3** `budget`, where given, MUST limit this turn alone, in addition to every budget above it
(§12.2).

**8.2.4** A turn MUST proceed in this order:

1. Where the prompt needs a mixin the grant lacks (§6.5), raise `CapabilityNotGranted`. Where a
   budget over the turn is spent, raise the `BudgetExceeded` subclass for the spent limit.
   Nothing is sent in either case.
2. On the session's first turn, start the harness for `env`. On a later turn whose `env`
   differs from the previous turn's, carry the session to `env` as clause 8.2.6 specifies.
3. On the session's first turn only, fire `SESSION_START`. A non-empty `context` in its result
   MUST be prepended to the prompt, separated by a blank line.
4. Fire `USER_PROMPT_SUBMIT` with the prompt. A result with `block=True` MUST raise
   `SessionError` and the turn MUST NOT run. A non-empty `context` MUST be appended to the
   prompt after a blank line.
5. Have the harness take the turn. Steers queued before it starts MUST be appended to the
   prompt, each after a blank line.
6. Where no steer is pending, fire `STOP`. A result with `block=True` and a non-empty `reason`
   MUST send `reason` as the next prompt of the same turn and MUST increment `again`. A result
   with an empty `reason` MUST NOT block.
7. Where steers arrived during the harness's turn, send them, joined by blank lines, as the next
   prompt of the same turn, and continue at item 6.
8. Where `output_schema` is given, read the final text as clause 8.2.5 specifies.

**8.2.5** hmz MUST validate `output_schema` with `model_validate_json` against, in order: the
whole final text with surrounding whitespace removed; each fenced code block of it; and the
span from its first `{` to its last `}`. The first that validates MUST be returned. Where none
validates, `run` MUST raise `OutputSchemaError`.

**8.2.6** A later turn whose `env` is another workdir on the machine of the previous turn MUST
carry the conversation there as a fork of the session cut by that turn, on a harness that forks
into any workdir (§6.4.3). Every other harness MUST raise `UnsupportedOperation` for such a
turn. Every harness MUST raise `UnsupportedOperation` for a later turn whose `env` is on
another machine than the previous turn's. A refused turn MUST leave the session where it was.

**8.2.7** `run` MUST raise:

1. `SessionError` where `session` is not a session of this agent or of an agent derived from
   it or from which it was derived.
2. `TypeError` where `env` is not an environment handed out in this epic.
3. `UnsupportedOperation` where `env` is not `None` on a `litellm` agent.
4. `SessionError` where a turn of `session` is under way.
5. `SessionError` where `session` is closed.
6. `FlowCancelled` where the flow call's caller or the epic has ended.
7. `SessionError` where `env` is on this machine and its workdir is not a directory.
8. `SessionError` on the first turn of a fork whose parent has taken a turn since the fork.
9. `SessionError` where the turn was interrupted.
10. The `BudgetExceeded` subclass for the limit, where a budget over the turn is spent before or
    during the turn (§12.3).
11. The `HarnessError` subclass of §15.3 the turn's failure maps to, where the harness failed
    the turn.
12. `asyncio.CancelledError` where the task awaiting `run` is cancelled; the harness MUST be
    interrupted.

**8.2.8** One session MUST take at most one turn at a time. Two sessions of one agent MAY take
turns concurrently.

**8.2.9** Where the harness has no means to do what a turn requires, `run` MUST raise
`UnsupportedOperation`.

### 8.3 Project configuration across machines

**8.3.1** Program-running configuration MUST be read as `features/placements.md` §2.9 defines
it, found from the session directory (`features/placements.md` §2.1) of the turn.

**8.3.2** Where a turn's session is mirrored and its harness machine is not its env machine,
opening a session, forking it into a workdir, carrying it on, and every later turn MUST raise
`UnsupportedOperation` where program-running configuration is present, as
`features/placements.md` §7 specifies.

**8.3.3** The message of the exception of clause 8.3.2 MUST name each file and key responsible.

**8.3.4** How project configuration is layered with hmz's own configuration is specified in
`features/agents.md` §5.

### 8.4 `SteeringAgentMixin.steer`

**8.4.1** `steer(prompt, session=..., queued=True)` MUST put `prompt` into the turn `session` is
taking, as typing at the agent would.

**8.4.2** With `queued=True`, the agent MUST receive the prompt at its next opportunity and
continue. With `queued=False`, the harness's current step MUST be interrupted and the turn MUST
continue from the prompt.

**8.4.3** `steer` MUST raise `CapabilityNotGranted` where the grant lacks `SteeringAgentMixin`,
`SessionError` where `session` is another agent's or closed, and `SessionError` where `session`
has no turn under way.

### 8.5 `Agent.fork`

**8.5.1** `fork(session)` MUST return a new session that continues `session`'s conversation.
`session` MUST be unchanged.

**8.5.2** The fork MUST be cut by its first turn, in that turn's `env`. `session` MUST be held
open until the fork's first turn.

**8.5.3** `fork` MUST raise `SessionError` where `session` is not this agent's, is closed, or has
taken no turn.

**8.5.4** The fork's first `run` MUST raise `UnsupportedOperation` where the harness does not fork,
where the turn's `env` is on another machine than `session`'s last turn, or where the turn's
`env` is another workdir on a harness that forks only in place. It MUST raise `SessionError`
where `session` has taken a turn since the fork, or where the harness could not cut the fork.

### 8.6 Retrying a dropped Codex turn

**8.6.1** Where the response stream of a `codex` turn breaks, hmz MUST retry the turn in the same
session at least once before `run` raises `HarnessDropped`.

## 9. Hooks

### 9.1 `HookKind`, `HookFn`, `HookParams`, `HookResult`, `HOOK_TYPES`

```python
class HookKind(StrEnum):
    SESSION_START = "session_start"
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    PRE_TOOL_USE = "pre_tool_use"
    PERMISSION_REQUEST = "permission_request"
    NOTIFICATION = "notification"
    STOP = "stop"
    SESSION_END = "session_end"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_STOP = "subagent_stop"
    ASK_USER = "ask_user"
    OUTWORLDER_RUN = "outworlder_run"

class HookFn[P: HookParams, R](Protocol):
    async def __call__(self, params: P, /) -> R: ...

@dataclass(frozen=True, slots=True, kw_only=True)
class HookParams:
    ctx: FlowContext
    session: Session

@dataclass(frozen=True, slots=True, kw_only=True)
class HookResult: ...

HOOK_TYPES: Mapping[HookKind, tuple[type[HookParams], type[HookResult]]]
```

**9.1.1** `HookKind` MUST have exactly the members above with exactly the values above.

**9.1.2** For each moment, `hmz.flows` MUST export a params class `<Moment>HookParams` deriving
from `HookParams` and a result class `<Moment>HookResult` deriving from `HookResult`, where
`<Moment>` is the member name in PascalCase (`SessionStart`, `UserPromptSubmit`, `PreToolUse`,
`PermissionRequest`, `Notification`, `Stop`, `SessionEnd`, `SubagentStart`, `SubagentStop`,
`AskUser`, `OutworlderRun`). Each MUST be a frozen, slotted, keyword-only dataclass.

**9.1.3** `HOOK_TYPES` MUST be a read-only mapping from each `HookKind` to the pair of its params
class and result class.

**9.1.4** `ctx` MUST be the context of the flow call the agent was handed to. `session` MUST be the
session the moment arrived in.

### 9.2 Fields

**9.2.1** The params fields beyond `ctx` and `session`, and the result fields with their defaults,
MUST be exactly:

| Moment | Params fields | Result fields |
| --- | --- | --- |
| `SESSION_START` | none | `context: str = ""` |
| `USER_PROMPT_SUBMIT` | `prompt: str` | `block: bool = False`, `reason: str = ""`, `context: str = ""` |
| `PRE_TOOL_USE` | `tool: str`, `input: Mapping[str, Any] = {}` | `block: bool = False`, `reason: str = ""` |
| `PERMISSION_REQUEST` | `tool: str`, `input: Mapping[str, Any] = {}` | `allow: bool = True`, `reason: str = ""` |
| `NOTIFICATION` | `message: str` | none |
| `STOP` | `said: str`, `again: int = 0` | `block: bool = False`, `reason: str = ""` |
| `SESSION_END` | none | none |
| `SUBAGENT_START` | `subagent: str`, `task: str = ""` | `context: str = ""` |
| `SUBAGENT_STOP` | `subagent: str`, `said: str = ""` | `block: bool = False`, `reason: str = ""` |
| `ASK_USER` | `question: str`, `options: tuple[str, ...] = ()` | `answer: str \| None = None` |
| `OUTWORLDER_RUN` | `prompt: str`, `output_schema: type[pydantic.BaseModel] \| None = None` | `output: str \| pydantic.BaseModel` (required) |

**9.2.2** A result built with no arguments MUST change nothing.

**9.2.3** `tool` MUST be the tool's name as the harness names it, and `input` its arguments, or an
empty mapping where the harness gives none.

**9.2.4** `said` of `STOP` MUST be the agent's last text, and `again` the number of times a `STOP`
hook has already kept this turn going.

**9.2.5** A `PRE_TOOL_USE` result with `block=True` MUST refuse the tool and tell the agent
`reason`, on a harness that gates tools through its own hooks (`claude`, `qwen`). On every
other harness, `PRE_TOOL_USE` MUST be fired for a tool already reached for and its result MUST
NOT refuse it.

**9.2.6** A `PERMISSION_REQUEST` result with `allow=False` MUST refuse the tool, overriding §7.4,
and the agent MUST be told `reason`.

**9.2.7** An `ASK_USER` result's `answer` MUST be told to the agent as the answer to its question.
hmz MUST accept an `answer` that is not one of `options`. `answer=None` MUST leave the question
unanswered and let
the agent continue without an answer.

**9.2.8** An `OUTWORLDER_RUN` result's `output` MUST be what the outworlder's `run` returns.

**9.2.9** hmz MUST fire `SUBAGENT_START` and `SUBAGENT_STOP` on every harness that serves their
mixins. The `context` of a `SUBAGENT_START` result and every field of a `SUBAGENT_STOP` result
MUST be delivered to no harness.

### 9.3 Hanging hooks

**9.3.1** Calling an `on_<moment>` method with a hook MUST replace the hook hung on that moment of
that agent. Calling it with `None` MUST remove the hook.

**9.3.2** A hook MUST cover every session of its agent, including sessions opened after it was
hung and sessions of agents derived from it.

**9.3.3** A callee's hooks MUST NOT be fired for its caller's sessions, and a caller's hooks MUST
NOT be fired for its callee's sessions.

**9.3.4** A hook MUST run on the flow's event loop, as the flow its agent was handed to. An
exception a hook raises MUST fail the turn the moment arrived in, and `run` MUST raise it.

**9.3.5** A moment delivered from inside the harness whose hook has not answered within 900
seconds MUST be answered as if no hook were hung. `ASK_USER` MUST have no such limit.

**9.3.6** A hook hung during a turn MUST apply to that turn's later moments, except where the hook
changes how the harness is started, in which case it MUST apply from the next turn. The hooks
that change how a harness is started are specified in `features/agents.md`.

**9.3.7** Which hooks refuse a session for where its harness runs is specified in
`features/placements.md`.

## 10. Outworlder

### 10.1 `Outworlder`

```python
class Outworlder(Agent, Protocol):
    @classmethod
    def new(cls) -> Self: ...
    @property
    def away(self) -> bool: ...
    def on_outworlder_run(
        self, fn: HookFn[OutworlderRunHookParams, OutworlderRunHookResult] | None
    ) -> None: ...
```

**10.1.1** In the top call, hmz MUST fill every `Outworlder` role with the epic's outworlder: the
person who started the epic, through the frontend they started it from.

**10.1.2** An outworlder MUST take turns as an agent of the flow. `run` on the epic's outworlder
MUST put `prompt` to the person and return what they answered. With `output_schema`, it MUST
ask one question per field and return the model built from the answers.

**10.1.3** `run` on an outworlder MUST accept an `env` and MUST otherwise ignore it.

**10.1.4** `fork` on an outworlder MUST raise `UnsupportedOperation`. `derive` with non-empty
`skills` on an outworlder MUST raise `CapabilityNotGranted`.

**10.1.5** `Outworlder.new()` MUST return a new outworlder whose every `run` is answered by the hook
hung with `on_outworlder_run`. Until such a hook is hung, it MUST be away.

**10.1.6** `on_outworlder_run` on an outworlder not made with `Outworlder.new()` MUST raise
`CapabilityNotGranted`.

### 10.2 Away

**10.2.1** `away` MUST be `True` where the epic was started by `hmz exec` and where `/afk` is on
for the role, and `False` otherwise.

**10.2.2** While an outworlder is away, `run` MUST return at once: `""` for text; the schema built
from its defaults where every field of `output_schema` has a default; and otherwise MUST raise
`OutworlderAway`.

### 10.3 Outworlders in nested calls

**10.3.1** A caller MAY pass its own outworlder, an outworlder made with `Outworlder.new()`, or
nothing, for a callee's `Outworlder` role. Where nothing is passed, the callee MUST be given the
epic's outworlder.

**10.3.2** A caller MAY pass an outworlder for a callee's agent role typed `Agent` that declares
no mixin and no harness. Passing one for a role that declares a mixin or a harness MUST raise
`CapabilityMissing`.

**10.3.3** The epic's outworlder MUST be asked, and MUST report `away`, as the `Outworlder` role the
top call filled with it, under whatever role name a caller passes it.

## 11. Environments

### 11.1 `EnvCollection`

```python
class EnvCollection(TypedDict, extra_items=ReadOnly[Env]): ...
```

**11.1.1** A flow author MUST declare a flow's environment roles as the keys of a subclass of
`EnvCollection`, each annotated with its role type.

**11.1.2** A role annotated `NotRequired[...]` MAY be left out. Every other role that is not
runtime-filled MUST be given.

### 11.2 `Env`

```python
class Env(Protocol):
    @property
    def available(self) -> bool: ...
    @property
    def backend(self) -> EnvBackendKind: ...
    @property
    def provider(self) -> str: ...
    @property
    def role(self) -> str: ...
    @property
    def workdir(self) -> pathlib.PurePosixPath: ...
    async def derive_subdir(self, *, subdir: pathlib.PurePosixPath | str) -> Env: ...
```

**11.2.1** `workdir` MUST be the directory, on the env machine, in which commands run and
relative paths resolve. It MUST be absolute, or start with `~/` for a directory under the home
of the user an `ssh` login lands as.

**11.2.2** `backend` MUST be the environment's `EnvBackendKind`.

**11.2.3** `provider` MUST be `""` for `local`, and otherwise the name of the runtime, or for
`ssh` the destination, the environment is on, as specified in `features/environments.md`.

**11.2.4** `available` MUST be whether the env machine was reachable and the workdir existed when
hmz last checked.

**11.2.5** `role` MUST be the key of the `EnvCollection` the environment fills.

**11.2.6** `derive_subdir(subdir=...)` MUST return an environment on the same machine, filling the
same role with the same grant, whose workdir is `subdir` under this workdir, creating the
directory where missing. It MUST raise `ValueError` where `subdir` is absolute or climbs out of
this workdir, and `EnvError` where the directory cannot be made.

### 11.3 `LocalEnv`

```python
class LocalEnv(Env, Protocol): ...
```

**11.3.1** In the top call, hmz MUST fill every `LocalEnv` role with the epic's workspace
environment, granted what the role declares. Such a role MUST NOT be given on the command line.

**11.3.2** A caller MAY pass, for a callee's `LocalEnv` role, nothing or an environment on this
machine. Where nothing is passed, the callee MUST be given the epic's workspace environment,
granted what the callee's role declares. Passing an environment on another machine MUST raise
`CapabilityMissing`.

### 11.4 `EnvBackendKind` and `SequenceNotStr`

```python
class EnvBackendKind(StrEnum):
    LOCAL = "local"
    SSH = "ssh"
    DOCKER = "docker"
    SWARM = "swarm"
    APPLE_CONTAINER = "apple-container"
    SLURM = "slurm"

class SequenceNotStr[T](Protocol): ...
```

**11.4.1** `EnvBackendKind` MUST have exactly the members above with exactly the values above.
Each backend is specified in `features/environments.md`.

**11.4.2** `SequenceNotStr[T]` MUST be satisfied by lists and tuples of `T` and MUST NOT be
satisfied by `str`.

### 11.5 Running commands and files

```python
class ShellEnvMixin(Protocol):
    async def exec(
        self, argv: SequenceNotStr[str], *, timeout: float = 0
    ) -> tuple[int, str, str]: ...

class BashEnvMixin(ShellEnvMixin, Protocol):
    @overload
    async def exec(
        self, argv: SequenceNotStr[str], *, timeout: float = 0
    ) -> tuple[int, str, str]: ...
    @overload
    async def exec(self, script: str, *, timeout: float = 0) -> tuple[int, str, str]: ...

class FilesEnvMixin(Protocol):
    async def read(self, path: str) -> bytes: ...
    async def write(self, path: str, data: bytes) -> None: ...
```

**11.5.1** `exec(argv)` MUST run one program, with its arguments as given and no shell between,
in the workdir, and MUST return its exit status, its stdout and its stderr, decoded as UTF-8.

**11.5.2** `timeout` MUST be in seconds, `0` meaning no limit. A program that runs past its
timeout MUST be killed and `exec` MUST raise `EnvCommandTimeout`. A program that cannot be
started MUST make `exec` raise `EnvError`.

**11.5.3** `exec(script)` with a `str` MUST run the script as `bash -c` would, in the workdir, with
the same timeout, return value and exceptions as clause 11.5.1 and 11.5.2. A string `exec` on an
environment whose grant lacks `BashEnvMixin` MUST raise `CapabilityNotGranted`.

**11.5.4** `exec` MUST raise `TypeError` unless given exactly one command, positionally or as
`argv=` or `script=`.

**11.5.5** `exec` on an environment whose grant lacks `ShellEnvMixin` MUST raise
`CapabilityNotGranted`.

**11.5.6** `read(path)` MUST return the bytes of the file at `path`, relative to the workdir or
absolute. It MUST raise `EnvFileNotFound` for a missing file and `EnvPermissionDenied` for one
that cannot be read.

**11.5.7** `write(path, data)` MUST replace the file at `path` whole with `data`, creating the
directories above it. It MUST raise `EnvPermissionDenied` for a file that cannot be written.

**11.5.8** `read` or `write` on an environment whose grant lacks `FilesEnvMixin` MUST raise
`CapabilityNotGranted`.

### 11.6 Worktrees, temporary copies and scratch directories

```python
class GitWorktreeEnvMixin(Protocol):
    async def derive_worktree(
        self, *, ref: str | None = None, dir: pathlib.PurePosixPath | str | None = None
    ) -> Self: ...

class TemporaryClonedDirEnvMixin(Protocol):
    async def derive_temp_clone(self, id: str) -> Self: ...
    async def destroy_temp_clone(self, id: str) -> None: ...

class ScratchDirEnvMixin(Protocol):
    async def derive_scratch(self, id: str) -> Self: ...
    async def destroy_scratch(self, id: str) -> None: ...
```

**11.6.1** Each environment derived by a method of this section MUST be on the same machine, fill
the same role and carry the same grant as the environment it was derived from.

**11.6.2** `derive_worktree` MUST add a git worktree of the repository the workdir is in, with
`ref` checked out detached, or what the workdir has checked out where `ref` is `None`, at `dir`,
relative to the workdir or absolute, or at a fresh directory hmz picks where `dir` is `None`.
hmz MUST NOT remove a worktree it added. `derive_worktree` MUST raise `WorktreeError` where the
workdir is not in a git repository, `ref` is unknown, or `dir` is taken.

**11.6.3** `derive_temp_clone(id)` MUST return an environment at a copy of the workdir. The same
`id` from the same environment MUST be the same copy, made once. It MUST raise `TempCloneBusy`
where another environment holds the copy under `id`, and `EnvError` where the copy fails.

**11.6.4** `derive_temp_clone` MUST need nothing on the env machine but `sh` and `cp`, except that
copying a workdir that is a linked git worktree MUST also need `git`; on a machine without
`git`, that copy MUST raise `EnvError`.

**11.6.5** `derive_scratch(id)` MUST return an environment at a directory beside the workdir on the
same machine, empty when first made. The same `id` MUST be the same directory. It MUST raise
`ScratchError` where the directory cannot be made.

**11.6.6** `destroy_temp_clone(id)` and `destroy_scratch(id)` MUST remove the directory at once
and free `id`. Removing a directory that does not exist MUST do nothing. `destroy_scratch` MUST
raise `ScratchError` where the directory cannot be removed.

**11.6.7** Temporary copies and scratch directories MUST be removed when the flow call that made
them and every flow call it started have ended, except as clause 5.4.6 specifies.

**11.6.8** A method of this section on an environment whose grant lacks its mixin MUST raise
`CapabilityNotGranted`.

### 11.7 Snapshots and rewinding

```python
class RewindableEnvMixin(Protocol):
    async def snapshot(self, name: str | None = None) -> str: ...
    async def rewind(self, ref: str) -> None: ...
    async def snapshots(self) -> list[str]: ...

class GitEnvMixin(RewindableEnvMixin, Protocol): ...
```

**11.7.1** `RewindableEnvMixin` MUST be an interface only. A role that declares it and not
`GitEnvMixin` MUST be granted none of its methods, and each MUST raise `CapabilityNotGranted`.

**11.7.2** Under `GitEnvMixin`, `snapshot(name)` MUST record the whole git worktree containing the
workdir, comprising the commit checked out, the index, and every file git does not ignore,
untracked files included, as a commit kept under `refs/hmz/snapshots/<name>`, and MUST return
that ref. It MUST NOT move what is checked out and MUST NOT change the index or any file. A
`name` already kept MUST be replaced. Where `name` is `None`, hmz MUST pick a name of the form
`<UTC timestamp>-<4 hex digits>`, whose order is the order of the snapshots taken.

**11.7.3** Under `GitEnvMixin`, `rewind(ref)` MUST restore the worktree as follows. A snapshot ref
MUST restore its commit, index and files, untracked files as untracked. Any other ref that git
resolves to a commit MUST be checked out with its files and a matching index. The branch
checked out, where there is one, MUST be moved to that commit. Files that are neither in the
commit nor ignored MUST be removed, nested repositories included. A merge, cherry-pick or
revert in progress MUST be abandoned. What is checked out MUST move last, so that a rewind git
refuses part way leaves it where it was. A `ref` that is empty or starts with `-` MUST be
refused.

**11.7.4** Under `GitEnvMixin`, `snapshots()` MUST return the snapshot refs kept in the repository,
oldest first by the second they were taken in, and by name within one second. Every worktree
of one repository MUST share them.

**11.7.5** Ignored files, and a `.hmz/` or `.humanize/` directory at the top of the worktree, MUST
be neither recorded by `snapshot` nor removed by `rewind`.

**11.7.6** Snapshots MUST be kept until something removes their refs.

**11.7.7** `snapshot`, `rewind` and `snapshots` MUST raise `RewindError` where the workdir is not in
a git worktree, where git knows no commit by `ref`, where `name` is not a name git can keep a
ref under, where `HEAD` is detached and the snapshot was taken before the first commit, and
where git refuses.

### 11.8 Machine requirements

```python
class CPUEnvMixin(Protocol):
    _cpu_count: ClassVar[int] = 1
class MemoryEnvMixin(Protocol):
    _memory: ClassVar[int] = 0
class GPUEnvMixin(Protocol):
    _gpu_count: ClassVar[int] = 1
    _gpu_memory: ClassVar[int] = 0
class ImageEnvMixin(Protocol):
    _image: ClassVar[str] = ""
```

**11.8.1** The class attributes above are part of the public API. A role type MUST set them to
declare what the env machine needs. Each attribute MUST be read only where its mixin is declared.

**11.8.2** `_cpu_count` MUST be the fewest logical CPUs, `_memory` the fewest bytes of memory,
`_gpu_count` the fewest GPUs, and `_gpu_memory` the fewest bytes of memory per GPU, that the env
machine is to have.

**11.8.3** `_image` MUST be the image a `docker`, `swarm` or `apple-container` environment's
container is started from, as `docker run` takes it, and `""` for the provider's own image, or
`python:3.12-slim` where the provider names none. `_image` MUST have no effect on `local`, `ssh`
and `slurm` environments.

**11.8.4** An environment given for a role that does not meet the role's declared resources MUST
be refused with `ResourceUnmet` before any agent of the epic starts. How resources size a
container or job is specified in `features/environments.md`.

**11.8.5** A flow that declares `GitEnvMixin` or `GitWorktreeEnvMixin` for an environment whose
machine has no `git` on its `PATH`, or `BashEnvMixin` for one with no `bash`, MUST be refused
with `CapabilityMissing` before any agent of the epic starts.

## 12. Budgets and usage

### 12.1 `Budget` and `Usage`

```python
class Budget(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, extra="forbid", ser_json_inf_nan="strings")
    duration: datetime.timedelta | None = None
    cost: float | None = None
    output_tokens: int | None = None
    graceful: bool = True

class Usage(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, extra="forbid", ser_json_inf_nan="strings")
    duration: datetime.timedelta = datetime.timedelta(0)
    cost: float = 0.0
    output_tokens: int = 0
```

**12.1.1** `Budget.duration` MUST limit wall-clock time from the start of the flow call or turn
the budget belongs to. `Budget.cost` MUST limit spending in US dollars. `Budget.output_tokens`
MUST limit the tokens agents write.

**12.1.2** `Budget.graceful=True` MUST let a turn under way when a limit is reached finish.
`Budget.graceful=False` MUST cut such a turn off at once.

**12.1.3** Constructing a `Budget` MUST raise `pydantic.ValidationError` where none of `duration`,
`cost` and `output_tokens` is set, or where any is negative.

**12.1.4** `Budget(cost=math.inf)` MUST denote an unlimited budget and MUST survive
`model_dump_json` and `model_validate_json`, the infinity written as `"Infinity"`.

**12.1.5** `Usage.duration` MUST be the sum of the durations of the turns counted, concurrent
turns each counting. `Usage.cost` MUST be in US dollars. `Usage.output_tokens` MUST be the tokens
agents wrote.

**12.1.6** hmz MUST require a budget for the top call of every epic except of the `chat` flow,
given as specified in `api/cli.md`. A top call of `chat` given none MUST run under
`Budget(cost=math.inf)`.

### 12.2 Effective budget

**12.2.1** Cost and output tokens spent anywhere under a flow call MUST count against that flow
call and every flow call above it.

**12.2.2** `duration` MUST be a deadline per flow call: a call's deadline MUST be the earliest of
its own start plus its own `duration` and the deadline of every call above it.

**12.2.3** `ctx.budget` MUST report, for each limit, the least over the chain of calls of what
the call in the chain allows minus what was spent under that call plus what was spent under
this call; `duration` as the time from this call's start to its deadline; and
`graceful=False` where any budget in the chain is not graceful.

**12.2.4** A turn MUST be held to the least remaining amount of each limit over every budget above
it and its own. Where two budgets leave the same amount, a non-graceful one MUST prevail. A
turn's own budget MUST apply to that turn alone.

### 12.3 Enforcement

**12.3.1** A turn requested while a limit over it is spent MUST raise, before anything is sent,
`DurationExceeded`, `CostExceeded` or `OutputTokensExceeded` for the spent limit.

**12.3.2** A limit reached during a turn under a graceful budget MUST let the turn complete and
return. The next turn under that budget MUST raise.

**12.3.3** A limit reached during a turn under a non-graceful budget MUST stop the harness, and
`run` MUST raise the subclass for the limit.

**12.3.4** When a flow call's deadline passes, hmz MUST cancel the call, after its turns under way
finish where its budget is graceful and at once otherwise, and the call MUST raise
`DurationExceeded`. A cancellation from anywhere else MUST remain `asyncio.CancelledError`.

**12.3.5** A budget once spent MUST remain spent: every later turn under it MUST raise again.

**12.3.6** hmz MUST price spending with its price table (`api/files/home.md`). A model absent from
the price table MUST cost 0.

## 13. Calling another flow

### 13.1 `load`

```python
def load(ref: str) -> Flow: ...
```

**13.1.1** `load(ref)` MUST return the flow object `ref` names, resolved relative to the module
that calls `load` (§13.3).

**13.1.2** Within one epic, one ref from one module MUST resolve to the same flow each time.

**13.1.3** `load` of a `git+` ref MUST return without fetching. The repository MUST be fetched
when a member of the flow object is first read or the flow is first called.

**13.1.4** `load` MUST raise:

1. `FlowRefError` where `ref` is not of the grammar of §13.2, or is a `:<name>` ref with no flow
   asking.
2. `FlowNotFound` where `ref` names no flow, or a `git+` repository cannot be fetched or holds no
   flow where `ref` says.
3. `FlowLoadConflict` where importing the flow's module would replace a module that a flow of an
   epic running in this process uses.
4. `FlowDefinitionError` where the named flow is written wrong, or importing its module raises.

### 13.2 Ref grammar

**13.2.1** A ref MUST be read after removing surrounding whitespace, by the following grammar, in
which `NAME` is the regular expression `[A-Za-z0-9_][A-Za-z0-9_.-]*` and `PART` is a non-empty
string holding no `/` and not starting with `.`:

```abnf
ref        = vcs-ref / relative / path-ref / name-ref
relative   = ":" NAME
name-ref   = flow-name [ ":" NAME ]
flow-name  = [ "@" verse "/" ] [ PART "/" ] PART
verse      = 1( ALPHA / DIGIT ) *( ALPHA / DIGIT / "." / "_" / "-" )
path-ref   = path [ ":" NAME ]
path       = ( "." / "/" / "~" ) *CHAR
vcs-ref    = "git+" url [ "@" rev ] [ "#" subdir [ ":" NAME ] ]
           / "git+" url [ "@" rev ] ":" NAME
subdir     = [ NAME *( "/" NAME ) ]
```

**13.2.2** A ref that contains `#` or starts with `git+` MUST be read as a `vcs-ref`, and MUST
raise `FlowRefError` where it does not start with `git+`.

**13.2.3** Outside a `vcs-ref`, the text after the last `:` MUST be read as a flow name only
where it contains no `/`; otherwise the whole ref MUST be read as `flow-name` or `path`.

**13.2.4** A ref MUST be a `path-ref` exactly where it starts with `.`, `/` or `~`. Every other ref
that is not a `vcs-ref` or `relative` MUST be a `name-ref`. A `name-ref` whose `flow-name` has a
part too many, an empty part, or a part starting with `.` MUST raise `FlowRefError`. Under
`@local/` and `@user/`, a `flow-name` MUST have exactly one `PART`.

**13.2.5** In a `vcs-ref`, `url` MUST have the scheme `https`, `http`, `ssh`, `file` or `git`, and
MUST have a host unless its scheme is `file`. `@rev` MUST be the text after the last `@` of the
URL's path. The URL's query and fragment MUST be dropped. A URL whose path names no repository
MUST raise `FlowRefError`.

**13.2.6** In a `vcs-ref` without `#`, a final `:NAME` MUST be read as a flow name where the text
before it holds a path after `://`, and as a port otherwise.

**13.2.7** A `subdir` with a part starting with `.` MUST raise `FlowRefError`.

### 13.3 Ref resolution

**13.3.1** `:NAME` MUST name the flow `NAME` of the module whose code calls `load`.

**13.3.2** A `name-ref` without `@` and with one `PART` MUST be resolved, for a flow asking, in the
directory of flows the asking flow is in, and, for an asking flow installed from a flowverse,
among the flows installed from that flowverse; and otherwise in the flow sources in lookup order
(§14.2).

**13.3.3** A `name-ref` without `@` and with two `PART`s (`<user>/<flow>`) MUST be resolved, for an
asking flow installed from a flowverse, among the flows installed from that flowverse; and
otherwise in the `official` flowverse only.

**13.3.4** A `name-ref` with `@<verse>/` MUST be resolved in flowverse `<verse>` only.

**13.3.5** A `path-ref` MUST be resolved, after expanding `~`, to the first file that exists of
`<path>/__init__.py`, `<path>`, `<path>.py`.

**13.3.6** A `vcs-ref` MUST be resolved to the module at `<subdir>/__init__.py` of the repository
checked out at `rev`, or at the repository root's `__init__.py` without `#`. An absent `rev` MUST
mean the repository's default branch. Each epic MUST fetch a given URL and `rev` at most once.

**13.3.7** Within the resolved module, a ref with `:NAME` MUST name the flow called `NAME`, and
MUST raise `FlowNotFound` where none is. A ref without `:NAME` MUST name the flow whose name is
the module's directory name or file stem; where there is none, the module's only flow that is
not hidden; and otherwise MUST raise `FlowNotFound`.

**13.3.8** A module's flows MUST be exactly the flow objects defined in files inside its
directory. A flow imported into the module from elsewhere MUST NOT be one of its flows.

**13.3.9** Files beside a flow's `__init__.py` MUST be importable from the flow by their plain
module names.

**13.3.10** A module whose files changed MUST be imported afresh by the next epic in which no
running epic shares it. An epic MUST import a module at most once.

**13.3.11** Two flow directories of one directory name MUST NOT both be loaded by one running
epic; the second MUST raise `FlowLoadConflict`.

### 13.4 Calling a `Flow`

**13.4.1** `await flow_object(task, agents=..., envs=..., params=..., budget=...)` MUST run the flow
as a nested call of the flow call whose code awaits it, and MUST return what the flow function
returns.

**13.4.2** `agents` and `envs` MUST be mappings keyed by the callee's role names. `params` MUST be
read as clause 4.4.4 specifies. `budget` MUST be `None` or exactly a `Budget`, and MUST raise
`TypeError` otherwise. A given `budget` MUST apply in addition to what remains of the caller's.

**13.4.3** An exception the callee raises MUST reach the caller with the class and message it was
raised with, without wrapping.

**13.4.4** A flow object awaited outside every epic MUST raise `FlowRuntimeError`.

**13.4.5** A nested call made after its caller, any call above it, or the epic has ended MUST raise
`FlowCancelled`.

**13.4.6** A nested call that would make flow calls nest more than 64 deep MUST raise
`FlowDepthExceeded`.

**13.4.7** hmz MUST check what a caller passes before the callee starts. A refusal MUST mean that
nothing of the callee ran and nothing was spent. hmz MUST raise:

1. `MissingRole` where a required agent or environment role that is not runtime-filled is not
   given.
2. `CapabilityMissing` where an agent or environment given lacks a mixin its role declares.
3. `PermissionTooNarrow` where an agent given holds a permission that does not cover its role's
   `_permission`.
4. `HarnessMismatch` where a role typed as a harness protocol is given an agent of another
   harness.
5. `CapabilityMissing` where a role typed `Outworlder` is given an agent that is not an
   outworlder.
6. `ResourceUnmet` where an environment given does not meet its role's declared resources.
7. `RequirementError` where a value given is not an agent or environment handed out in this
   epic, or where a role is given that the callee does not declare.

**13.4.8** A callee MUST be given exactly its declaration: each agent re-granted the callee role's
mixins, `_permission`, `_skills`, `_tools` and `_clis`, and each environment the callee role's
mixins.

**13.4.9** A callee's hooks and sessions MUST be its own. A session the caller opened MUST NOT be
usable by the callee.

### 13.5 Concurrency and cancellation

**13.5.1** A flow function MUST be able to use `asyncio.gather`, `asyncio.TaskGroup`,
`asyncio.timeout` and `except*` as in any coroutine. A callee's exception MUST reach `except*`
with its own class.

**13.5.2** Cancelling a task awaiting a turn MUST interrupt that turn's harness.

**13.5.3** When an epic is stopped, hmz MUST cancel the flow at its current `await`, MUST close
every session, and MUST remove every temporary copy and scratch directory except as clause 5.4.6
specifies. How an epic is stopped is specified in `api/cli.md` and `features/epics.md`.

## 14. Flow sources

### 14.1 Flow shapes

**14.1.1** A flow module MUST be either a directory holding `__init__.py`, or a single `.py`
file. Where both exist under one name, the directory MUST be used.

**14.1.2** A name starting with `_`, and a directory without `__init__.py`, MUST NOT be a flow
module.

### 14.2 Sources and lookup order

**14.2.1** hmz MUST offer the following flow sources:

| Source | Holds |
| --- | --- |
| `local` | `.hmz/flows/` under the current directory |
| `user` | `~/.hmz/flows/` |
| `official` | the flows shipped in the `hmz` package, then the flows installed from the official index |
| any other flowverse | the flows installed from its index |

The directories holding installed flows are specified in `api/files/home.md`.

**14.2.2** A bare flow name MUST be looked up in `local`, then `user`, then `official`, then every
other flowverse in alphabetical order, and the first match MUST be used.

**14.2.3** hmz MUST find only flows that are shipped, installed, or in `local` or `user`. A flow
that an index lists and that is not installed MUST NOT be found, and naming it MUST raise
`FlowNotFound`.

### 14.3 Flows in the package

**14.3.1** hmz MUST ship the following flows, each with an environment role `workspace: LocalEnv`:

| Flow | Agent roles | Role needs | Resumable |
| --- | --- | --- | :-: |
| `chat` | `assistant`, `human: Outworlder` | none | ✓ |
| `ralph_loop` | `agent` | none | |
| `stateful_ralph` | `agent` | none | ✓ |
| `continue_loop` | `agent` | none | |
| `goal` | `worker` | `GoalCommandAgentMixin` | |
| `flame_chase` | `first_chaser`, `second_chaser` | none | ✓ |
| `rlar` | `actor`, `reviewer` | none | ✓ |

**14.3.2** The agent roles of `chat` MUST each be granted every mixin its harness serves, whatever
the role declares. Every other flow MUST be granted exactly what its roles declare. The
behaviour of `chat` is specified in `features/chat.md`.

**14.3.3** Each flow of clause 14.3.1 other than `chat` MUST run until its budget is spent, `rlar`
also until its reviewer says the work is done, and MUST end the epic with the failure of any
turn that fails.

### 14.4 Flowverses

**14.4.1** A flowverse index MUST be a git repository of manifests. A flow listed bare MUST have
its manifests at `flows/<flow>/<version>/flow.yaml`; a flow listed under a GitHub user or
organisation `<user>` MUST have them at `flows/<user>/<flow>/<version>/flow.yaml`, `<user>`
matching `[a-z0-9][a-z0-9-]*`. In the `official` index, the flows of `humanfia` MUST be listed
bare.

**14.4.2** A manifest MUST be a YAML mapping with the keys below. hmz MUST ignore other keys.

| Key | Required | Value |
| --- | :-: | --- |
| `name` | ✓ | `[a-z][a-z0-9_]*`, equal to the `<flow>` directory, not the name of a shipped flow |
| `version` | ✓ | SemVer 2.0.0, equal to the `<version>` directory |
| `description` | | one line |
| `repo` | ✓ | `owner/repo` on GitHub, or a URL with scheme `https`, `http`, `ssh`, `git` or `file` |
| `ref` | | the tag or branch the release was cut from; informative |
| `commit` | ✓ | 40 hexadecimal digits; what is installed |
| `subdir` | | the directory of the repository holding the flow; `""` or `.` for the root |
| `license` | | an SPDX identifier |
| `dependencies` | | a mapping from index name to a version range of flows of the same flowverse |

**14.4.3** A manifest that cannot be read or breaks a rule of clause 14.4.2 MUST be skipped and
listed with the reason, and MUST NOT raise.

**14.4.4** Installing a flow MUST install the release named, or where none is named the newest
release that is not a prerelease, or the newest prerelease where every release is one, together
with every dependency at a release within its range. Installing MUST be refused with
`ValueError` where no such set of releases exists, where dependencies form a cycle, or where
the install would put another installed flow's dependency out of its range.

**14.4.5** Installing a flow MUST copy the flow's directory from the repository at `commit`, and
MUST NOT execute any of it.

**14.4.6** Uninstalling a flow MUST be refused with `ValueError` where another flow installed from
the same flowverse lists it among its `dependencies`.

**14.4.7** The `official`, `local` and `user` flowverses MUST NOT be removable. How flowverses are
added, fetched and removed by a user is specified in `api/cli.md` and `api/sdk.md`.

## 15. Exceptions

### 15.1 Hierarchy

**15.1.1** Every exception class of `hmz.flows` MUST derive from `FlowException`, with exactly the
bases given in §15.2 to §15.4, forming this tree:

```text
FlowException (Exception)
├── FlowRuntimeError
│   ├── FlowNotFound
│   ├── FlowRefError (ValueError)
│   ├── FlowDefinitionError
│   ├── FlowLoadConflict
│   ├── RequirementError
│   │   ├── MissingRole
│   │   ├── CapabilityMissing
│   │   ├── PermissionTooNarrow
│   │   ├── ResourceUnmet
│   │   └── HarnessMismatch
│   ├── CapabilityNotGranted
│   ├── ParamsError (ValueError)
│   ├── FlowDepthExceeded (RecursionError)
│   ├── BudgetExceeded
│   │   ├── DurationExceeded (TimeoutError)
│   │   ├── CostExceeded
│   │   └── OutputTokensExceeded
│   ├── FlowCancelled
│   ├── StateNotSerializable (TypeError)
│   └── OutworlderAway
├── HarnessError
│   ├── HarnessNotInstalled
│   ├── HarnessContended
│   ├── HarnessThrottled
│   ├── HarnessRefused
│   ├── ModelUnavailable
│   ├── HarnessMissing
│   ├── HarnessSandboxed
│   ├── HarnessKilled
│   ├── HarnessDropped
│   ├── HarnessUnrecoverable
│   ├── OutputSchemaError (ValueError)
│   ├── SessionError
│   └── UnsupportedOperation
└── EnvError
    ├── EnvUnavailable
    ├── EnvConnectionError (ConnectionError)
    ├── EnvCommandTimeout (TimeoutError)
    ├── EnvFileNotFound (FileNotFoundError)
    ├── EnvPermissionDenied (PermissionError)
    ├── WorktreeError
    ├── TempCloneBusy
    ├── ScratchError
    └── RewindError
```

**15.1.2** Every exception class of `hmz.flows` MUST be constructed with its message as its only
argument, and MUST pickle and copy as an instance of its own class.

**15.1.3** An exception raised by a flow's own code that is not of `hmz.flows` MUST NOT be
converted into a `FlowException`.

**15.1.4** `FlowException` MUST be raised by hmz only through one of its subclasses.

### 15.2 Runtime exceptions

**15.2.1** `FlowRuntimeError(FlowException)` MUST be raised where a flow object is awaited outside
every epic (clause 13.4.4), and is the base of every exception hmz raises for what it refused or
what ran out.

**15.2.2** `FlowNotFound(FlowRuntimeError)` MUST be raised where a ref names no flow (clauses
13.1.4, 13.3.7, 14.2.3).

**15.2.3** `FlowRefError(FlowRuntimeError, ValueError)` MUST be raised where a ref is not of the
grammar of §13.2, or is relative with no flow asking.

**15.2.4** `FlowDefinitionError(FlowRuntimeError)` MUST be raised where a flow is written wrong
(clauses 4.1.7, 4.1.9, 4.1.10), where importing a flow's module raises, and where a skill a role
names cannot be found (clause 6.7.2).

**15.2.5** `FlowLoadConflict(FlowRuntimeError)` MUST be raised where loading a flow would replace a
module that a running epic uses (clauses 13.1.4, 13.3.11).

**15.2.6** `RequirementError(FlowRuntimeError)` MUST be raised, as itself or a subclass, where what
a flow call is given does not meet its declaration, before anything of the callee runs (clause
13.4.7).

**15.2.7** `MissingRole(RequirementError)` MUST be raised where a required role is not given.

**15.2.8** `CapabilityMissing(RequirementError)` MUST be raised where an agent or environment given
lacks a declared mixin, including a mixin whose program the env machine lacks (clause 11.8.5);
where a `LocalEnv` role is given an environment on another machine; and where an outworlder is
given for a role it cannot fill, or an agent for an `Outworlder` role.

**15.2.9** `PermissionTooNarrow(RequirementError)` MUST be raised where an agent given holds a
permission that does not cover its role's.

**15.2.10** `ResourceUnmet(RequirementError)` MUST be raised where an environment given cannot
provide the resources its role declares.

**15.2.11** `HarnessMismatch(RequirementError)` MUST be raised where a role typed as a harness
protocol is given an agent of another harness.

**15.2.12** `CapabilityNotGranted(FlowRuntimeError)` MUST be raised where a flow uses an operation
outside the grant of the handed object (clause 3.1.4), where `derive` would widen a grant, and
where `on_outworlder_run` is called on an outworlder not made with `Outworlder.new()`.

**15.2.13** `ParamsError(FlowRuntimeError, ValueError)` MUST be raised where params do not
validate against the flow's params model (§4.4).

**15.2.14** `FlowDepthExceeded(FlowRuntimeError, RecursionError)` MUST be raised where a nested call
would nest more than 64 deep.

**15.2.15** `BudgetExceeded(FlowRuntimeError)` MUST be raised only through one of its subclasses,
where a budget of the flow call or turn, or of a flow call above it, is spent (§12.3).

**15.2.16** `DurationExceeded(BudgetExceeded, TimeoutError)` MUST be raised where `duration` is
spent. `CostExceeded(BudgetExceeded)` MUST be raised where `cost` is spent.
`OutputTokensExceeded(BudgetExceeded)` MUST be raised where `output_tokens` are spent.

**15.2.17** `FlowCancelled(FlowRuntimeError)` MUST be raised where an operation of a flow call is
attempted after its caller, a call above it, or the epic has ended.

**15.2.18** `StateNotSerializable(FlowRuntimeError, TypeError)` MUST be raised where a flow state
write is refused (clauses 5.2.1, 5.3.2).

**15.2.19** `OutworlderAway(FlowRuntimeError)` MUST be raised where an away outworlder is asked for
an `output_schema` that has a field without a default.

### 15.3 Harness exceptions

**15.3.1** `HarnessError(FlowException)` MUST be raised, as one of its subclasses, where a harness
could not take a turn or do what it was asked.

**15.3.2** `HarnessNotInstalled(HarnessError)` MUST be raised where the harness, or the SDK it is
driven through, is not installed on the harness machine, including where the command that
starts it exits with status 127.

**15.3.3** `HarnessContended(HarnessError)` MUST be raised where two turns reached one local store
of the harness at once and this turn lost.

**15.3.4** `HarnessThrottled(HarnessError)` MUST be raised where the provider refused for too many
requests or a spent quota.

**15.3.5** `HarnessRefused(HarnessError)` MUST be raised where the provider refused the credential:
expired, revoked, or not signed in.

**15.3.6** `ModelUnavailable(HarnessError)` MUST be raised where the model is not served to the
account, has been retired, or does not exist.

**15.3.7** `HarnessMissing(HarnessError)` MUST be raised where the harness would not start for a
reason other than not being installed.

**15.3.8** `HarnessSandboxed(HarnessError)` MUST be raised where a session cannot be held to its
permission by the harness or the machine (clause 7.2.5), including where the harness cannot set
up its own sandbox on the machine.

**15.3.9** `HarnessKilled(HarnessError)` MUST be raised where the harness died during a turn,
by a signal or an out-of-memory kill, rather than answering.

**15.3.10** `HarnessDropped(HarnessError)` MUST be raised where the connection to the harness or to
its provider broke during a turn, after the retry of clause 8.6.1 where it applies.

**15.3.11** `HarnessUnrecoverable(HarnessError)` MUST be raised where a turn failed in a way no
retry could change and no other subclass of `HarnessError` names, including where the harness
cannot be configured as the session requires (clause 6.4.6).

**15.3.12** `OutputSchemaError(HarnessError, ValueError)` MUST be raised where the agent's answer
cannot be read as the `output_schema` asked for (clause 8.2.5).

**15.3.13** `SessionError(HarnessError)` MUST be raised where a session cannot take a turn or is
used in a way it cannot be: closed, another agent's, busy, steered with no turn under way,
interrupted, a fork whose parent moved on, a prompt a hook refused, and the conditions of
clauses 5.3.6, 8.2.7 and 8.5.3.

**15.3.14** `UnsupportedOperation(HarnessError)` MUST be raised where the harness cannot do what was
asked at all: the conditions of clauses 5.3.5, 6.6.5, 6.6.11, 8.2.6, 8.2.7, 8.2.9, 8.3.3, 8.5.4
and 10.1.4.

**15.3.15** hmz MUST classify each failed turn into exactly one subclass of `HarnessError` by the
conditions of clauses 15.3.2 to 15.3.14.

### 15.4 Environment exceptions

**15.4.1** `EnvError(FlowException)` MUST be raised, as itself or one of its subclasses, where an
environment could not do what it was asked.

**15.4.2** `EnvUnavailable(EnvError)` MUST be raised where the env machine is gone or the workdir
does not exist.

**15.4.3** `EnvConnectionError(EnvError, ConnectionError)` MUST be raised where the connection to
an env machine other than this machine could not be made, or broke.

**15.4.4** `EnvCommandTimeout(EnvError, TimeoutError)` MUST be raised where `exec` ran past its
`timeout` (clause 11.5.2).

**15.4.5** `EnvFileNotFound(EnvError, FileNotFoundError)` MUST be raised where `read` names a
missing file.

**15.4.6** `EnvPermissionDenied(EnvError, PermissionError)` MUST be raised where the environment
refused a read, a write or a command for want of permission.

**15.4.7** `WorktreeError(EnvError)` MUST be raised where `derive_worktree` fails (clause 11.6.2).

**15.4.8** `TempCloneBusy(EnvError)` MUST be raised where `derive_temp_clone` asks for an id another
environment holds.

**15.4.9** `ScratchError(EnvError)` MUST be raised where a scratch directory cannot be made or
removed.

**15.4.10** `RewindError(EnvError)` MUST be raised where `snapshot`, `rewind` or `snapshots` fails
(clause 11.7.7).

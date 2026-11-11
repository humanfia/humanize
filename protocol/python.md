# The Humanize Protocol: Python Interfaces

## Abstract

This document specifies the two public Python interfaces of hmz: the flow API (`hmz.flows`), against
which a flow is written, and the software development kit (`hmz.sdk`), through which another program
drives hmz.

## Status of This Document

This document is one of the documents of the Humanize Protocol, which Section 2.2.4 of [CORE] lists.
It is normative. It is cited by the tag [PYTHON].

## Table of Contents

- [1. Introduction](#1-introduction)
- [2. Conventions and Terminology](#2-conventions-and-terminology)
- [3. Flow API (`hmz.flows`)](#3-flow-api-hmzflows)
  - [3.1. Scope](#31-scope)
  - [3.2. Terminology](#32-terminology)
  - [3.3. Module surface](#33-module-surface)
  - [3.4. Defining a flow](#34-defining-a-flow)
  - [3.5. Flow context, state and resumption](#35-flow-context-state-and-resumption)
  - [3.6. Agents](#36-agents)
  - [3.7. Permissions and approval](#37-permissions-and-approval)
  - [3.8. Sessions and turns](#38-sessions-and-turns)
  - [3.9. Hooks](#39-hooks)
  - [3.10. Outworlder](#310-outworlder)
  - [3.11. Environments](#311-environments)
  - [3.12. Budgets and usage](#312-budgets-and-usage)
  - [3.13. Calling another flow](#313-calling-another-flow)
  - [3.14. Flow sources](#314-flow-sources)
  - [3.15. Exceptions](#315-exceptions)
- [4. Software Development Kit (`hmz.sdk`)](#4-software-development-kit-hmzsdk)
  - [4.1. Scope](#41-scope)
  - [4.2. Terminology](#42-terminology)
  - [4.3. The module](#43-the-module)
  - [4.4. `Hmz`](#44-hmz)
  - [4.5. `Run`](#45-run)
  - [4.6. `Refused`](#46-refused)
  - [4.7. `Flows`](#47-flows)
  - [4.8. `Flowverses`](#48-flowverses)
  - [4.9. `Accounts`](#49-accounts)
  - [4.10. `Runtimes`](#410-runtimes)
  - [4.11. `Fallbacks`](#411-fallbacks)
  - [4.12. `Epics`](#412-epics)
  - [4.13. `Backups`](#413-backups)
  - [4.14. The daemon registry](#414-the-daemon-registry)
  - [4.15. `Host`](#415-host)
  - [4.16. `Daemons`](#416-daemons)
  - [4.17. `Daemon`](#417-daemon)
  - [4.18. `Link`](#418-link)
  - [4.19. `fakes`](#419-fakes)
  - [4.20. Returned types](#420-returned-types)
- [5. Security Considerations](#5-security-considerations)
- [6. References](#6-references)
  - [6.1. Normative References](#61-normative-references)

## 1. Introduction

This document specifies the two public Python interfaces of hmz: the flow API (`hmz.flows`), against
which a flow is written, and the software development kit (`hmz.sdk`), through which another program
drives hmz.

This document is organised as follows:

- Section 3: Flow API (`hmz.flows`).
- Section 4: Software Development Kit (`hmz.sdk`).

## 2. Conventions and Terminology

The key words "MUST", "MUST NOT" and "MAY" in this document are to be interpreted as described in
BCP 14 [RFC2119] [RFC8174] when, and only when, they appear in all capitals, as shown here.

The conventions for numbering and citation, and every term of the shared glossary, are those of
Section 2 of [CORE].

## 3. Flow API (`hmz.flows`)

### 3.1. Scope

Section 3 governs the Python module `hmz.flows`: every name it exports, the signature and
behaviour of each, how a flow is declared, defined, loaded, called and resumed, what a flow observes
of its agents, sessions, turns, hooks and environments, the budget a flow runs under, the grammar
and resolution of a flow ref, the sources flows are found in, and every exception the module
defines.

Out of scope:

- The `hmz exec` command line, including the `-a`, `-e` and `-p` grammars, `--resume` and exit
  statuses: [CLI].
- The `hmz.sdk` package, including the in-memory fakes for testing a flow: Section 4.
- The layout and format of files hmz writes, including the progress record of a resumable epic, kept
  conversations, flowverse clones and installed flows: Section 4 of [FILES], Section 6 of [FILES],
  Section 7 of [FILES].
- How a permission is enforced on a harness (the fence and the harness's approval rung), the harness
  configuration layering, and each harness's accepted models and efforts: Section 4 of [CORE].
- Accounts a turn runs as: Section 5 of [CORE].
- Where a session's harness runs (placements, harness settings, mirrors): Section 6 of [CORE].
- Environment backends, runtimes, and how resources size a container or job: Section 7 of [CORE].
- Which epic a resume picks up, and what an epic records: Section 3 of [CORE].
- The behaviour of the `chat` flow: Section 8 of [CORE].

### 3.2. Terminology

Terms defined in [CORE] (among them **hmz**, **user**, **machine**, **this machine**, **home**,
**workspace**, **flow**, **flow author**, **epic**, **role**, **agent**, **harness**, **harness
machine**, **env**, **env machine**, **placement**, **mirror**, **runtime**, **account**,
**session**, **side question**) are used with the meaning given there.

**3.2.1** **Flow function**: the `async` function to which the decorator returned by `flow` (Section
3.4.1) is applied.

**3.2.2** **Flow object**: an object satisfying the `Flow` protocol (Section 3.4.3), as returned by
`flow` or by `load`.

**3.2.3** **Flow call**: one awaited invocation of a flow object. The **top call** of an epic is the
flow call hmz makes to start the epic; every other flow call is made by a flow function and is a
**nested call**. For a nested call, the flow call whose flow function made it is the **caller** and
the nested call is the **callee**.

**3.2.4** **Role type**: the class annotating one key of an `AgentCollection` or `EnvCollection`
subclass.

**3.2.5** **Mixin**: a class exported by `hmz.flows` whose name ends in `AgentMixin` or `EnvMixin`.
A role type **declares** a mixin when the mixin is among the role type's bases, directly or through
another mixin.

**3.2.6** **Harness protocol**: one of the classes that are values of `HARNESS_AGENTS` (Section
3.6.4) other than `Agent`.

**3.2.7** **Runtime-filled role**: an agent role whose role type is `Outworlder` or a subclass of
it, or an environment role whose role type is `LocalEnv` or a subclass of it.

**3.2.8** **Handed object**: an object hmz passes to a flow function or hook as an agent, an
environment, a session, a flow context or a flow state. A handed object satisfies the corresponding
protocol of `hmz.flows` structurally and is not an instance of that protocol.

**3.2.9** **Grant**: the set of mixins, the `Permission`, the skills, the fake tools and the fake
command lines that a handed agent or environment allows a flow to use.

**3.2.10** **Turn**: one awaited call of `Agent.run` (Section 3.8.2), from the moment it is called
until it returns or raises.

**3.2.11** **Moment**: a point in a session at which a hook is called; one member of `HookKind`
(Section 3.9.1).

**3.2.12** **Hook**: an `async` callable that hmz calls at one moment of every session of one agent.

**3.2.13** **Ref**: a string naming a flow, of the grammar in Section 3.13.2.

**3.2.14** **Flow source**: one place hmz finds flows in: `local`, `user`, `official`, or another
flowverse (Section 3.14).

**3.2.15** **Flowverse**: a named flow source. A flowverse other than `local` and `user` is backed
by an **index**: a git repository of release manifests (Section 3.14.4).

**3.2.16** **Resumable flow**: a flow defined with `resumable=True`.

**3.2.17** **Resumed call**: a flow call that picks up a flow call of an earlier epic (Section
3.5.4).

**3.2.18** **Kept session**: a session written into a flow state (Section 3.5.3).

**3.2.19** **Effective budget**: the limits a flow call or turn is held to, combining its own budget
with every budget above it (Section 3.12.2).

**3.2.20** **Away**: the state of an outworlder in which no person answers it (Section 3.10.2).

**3.2.21** **The epic's workspace environment**: the environment whose workdir is the workspace the
epic was started in, on this machine.

### 3.3. Module surface

#### 3.3.1. Importing

**3.3.1.1** `hmz.flows` MUST be importable without importing any module of hmz other than
`hmz.flows`, its submodules and `hmz.coganchor.faking`.

**3.3.1.2** `hmz.flows.__all__` MUST list exactly the names in Section 3.3.2, and each MUST be
importable from `hmz.flows`.

**3.3.1.3** Every class of `hmz.flows` documented in this document as a protocol MUST be a
`typing.Protocol`. A handed object MUST satisfy its protocol and every mixin of its grant
structurally.

**3.3.1.4** A handed agent or environment MUST allow exactly its grant. An operation that needs a
mixin absent from the grant MUST raise `CapabilityNotGranted`, whether or not the harness or machine
underneath supports the operation.

**3.3.1.5** The message of an exception raised by hmz is informative. No paragraph of this
document constrains the wording of such a message unless the paragraph quotes the message.

#### 3.3.2. Exported names

**3.3.2.1** The exported names, grouped by the section that specifies them, MUST be:

| Group | Names | Section |
| --- | --- | --- |
| Defining | `flow`, `Flow`, `FlowFn`, `FlowParams`, `FlowContext`, `FlowState`, `load` | Section 3.4, Section 3.5, Section 3.13 |
| Agents | `AgentCollection`, `Agent`, `Session`, `Outworlder`, `HarnessKind`, `HARNESS_AGENTS` | Section 3.6, Section 3.8, Section 3.10 |
| Harness protocols | `ClaudeCodeAgent`, `CodexAgent`, `CursorAgent`, `OpenCodeAgent`, `MiMoCodeAgent`, `MiniMaxCodeAgent`, `QwenCodeAgent`, `KimiCodeAgent`, `GrokBuildAgent`, `PiAgent`, `OhMyPiAgent`, `AntigravityAgent`, `DeepSeekHarnessAgent`, `LiteLLMAgent` | Section 3.6.4 |
| Agent mixins | `FakeToolAgentMixin`, `GoalCommandAgentMixin`, `LoopCommandAgentMixin`, `SteeringAgentMixin`, `PermissionRequestHookAgentMixin`, `SubagentStartHookAgentMixin`, `SubagentStopHookAgentMixin`, `AskUserHookAgentMixin` | Section 3.6.5 |
| Fake tools and command lines | `FakeTool`, `FakeCli`, `FakeCommand` | Section 3.6.6 |
| Permissions | `Permission`, `PermissionKind` | Section 3.7 |
| Budgets | `Budget`, `Graceful`, `Usage` | Section 3.12 |
| Environments | `EnvCollection`, `Env`, `LocalEnv`, `EnvBackendKind`, `SequenceNotStr` | Section 3.11 |
| Environment mixins | `ShellEnvMixin`, `BashEnvMixin`, `FilesEnvMixin`, `GitWorktreeEnvMixin`, `TemporaryClonedDirEnvMixin`, `ScratchDirEnvMixin`, `RewindableEnvMixin`, `GitEnvMixin`, `CPUEnvMixin`, `MemoryEnvMixin`, `GPUEnvMixin`, `ImageEnvMixin` | Section 3.11.5 to Section 3.11.8 |
| Hooks | `HookKind`, `HookFn`, `HookParams`, `HookResult`, `HOOK_TYPES`, and `<Moment>HookParams`, `<Moment>HookResult` for each of the eleven moments | Section 3.9 |
| Exceptions | `FlowException` and every class under it | Section 3.15 |

**3.3.2.2** `FakeTool`, `FakeCli` and `FakeCommand` exported by `hmz.flows` MUST be the same class
objects as those exported by `hmz.coganchor.faking`.

### 3.4. Defining a flow

#### 3.4.1. `flow`

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

**3.4.1.1** `flow` MUST return a decorator. The decorator, applied to a flow function, MUST return a
flow object.

**3.4.1.2** `agents` declares the flow's agent roles, `envs` its environment roles, and `params` its
params model. A flow that takes no params MUST pass `FlowParams` itself.

**3.4.1.3** The flow's name MUST be `name` where `name` is not `None`, and the flow function's
`__name__` otherwise. The flow's name MUST match the regular expression
`[A-Za-z0-9_][A-Za-z0-9_.-]*`.

**3.4.1.4** The flow's description MUST be `description` where it is not `None`; otherwise the first
line of the flow function's docstring where the function has one; otherwise `None`.

**3.4.1.5** A flow defined with `hidden=True` MUST NOT be listed by any frontend's list of flows. It
MUST still be loadable by its ref and runnable.

**3.4.1.6** A flow defined with `resumable=True` MUST be given a flow state (Section 3.5.2) and MUST
be eligible for resumption (Section 3.5.4). A flow defined with `resumable=False` MUST NOT be given
a flow state and MUST NOT be eligible for resumption.

**3.4.1.7** The decorator MUST raise `FlowDefinitionError` when any of the following holds, and MUST
NOT return a flow object:

1. The function is not a coroutine function.
2. The function's signature cannot be read.
3. The function has no positional first parameter.
4. The function accepts any of `agents`, `envs`, `params`, `ctx` neither as a keyword parameter nor
   through `**kwargs`.
5. The function has a parameter other than the first positional one and the four of item 4 that has
   no default.
6. `agents` is not a subclass of `AgentCollection`.
7. `envs` is not a subclass of `EnvCollection`.
8. `params` is not a subclass of `FlowParams`.
9. `params` declares a field or an alias named `budget`.
10. The flow's name does not match the expression of Section 3.4.1.3.

**3.4.1.8** hmz MUST resolve the role annotations of `agents` and `envs` no earlier than the first
time the flow is called or described, against the global and local namespaces in which `flow` was
called. Annotations written as strings, `from __future__ import annotations`, and collections
declared inside a function MUST resolve. `NotRequired`, `Required`, `ReadOnly` and `Annotated`
wrappers MUST be read through.

**3.4.1.9** On resolving the role annotations, hmz MUST raise `FlowDefinitionError` when any of the
following holds:

1. An annotation is a string that does not resolve.
2. An annotation is not a class.
3. An agent role type is not a subclass of `Agent`.
4. An environment role type is not a subclass of `Env`.
5. An agent role type declares an environment mixin, or an environment role type declares an agent
   mixin.
6. An agent role type derives from two distinct harness protocols.
7. An `Outworlder` role type derives from a harness protocol or declares a mixin.
8. An agent role type's `_permission` is not a `Permission`.
9. An agent role type's `_skills` is not a tuple or list of non-empty strings.
10. An agent role type's `_tools` is not a tuple or list of `FakeTool`, names two tools of one name,
    or is non-empty on a role type that does not declare `FakeToolAgentMixin`.
11. An agent role type's `_clis` is not a tuple or list of `FakeCli`, names two command lines of one
    name, or is non-empty on a role type that is `LiteLLMAgent`, a subclass of it, or an
    `Outworlder`.
12. An environment role type's `_cpu_count`, `_memory`, `_gpu_count` or `_gpu_memory`, where its
    mixin is declared, is not an `int` of at least 0, or is a `bool`.
13. An environment role type's `_image`, where `ImageEnvMixin` is declared, is not a string without
    whitespace.

**3.4.1.10** Where one module defines two flows of one name, hmz MUST raise `FlowDefinitionError`
when the module's flows are enumerated. Where two flow functions of one module bind one Python name,
the later binding MUST replace the earlier.

#### 3.4.2. `FlowFn`

```python
class FlowFn[A: AgentCollection, E: EnvCollection, P: FlowParams](Protocol):
    async def __call__(
        self, task: str, *, agents: A, envs: E, params: P, ctx: FlowContext
    ) -> Any: ...
```

**3.4.2.1** hmz MUST call a flow function with the task as its first positional argument and
`agents`, `envs`, `params` and `ctx` as keyword arguments.

**3.4.2.2** `agents` MUST be a mapping from role name to handed agent, holding one entry per agent
role that was given or that hmz filled. `envs` MUST be the same for environment roles. A
`NotRequired` role that was neither given nor filled MUST be absent from the mapping.

**3.4.2.3** `params` MUST be an instance of the flow's params model. `ctx` MUST be the flow call's
`FlowContext`.

**3.4.2.4** The value the flow function returns MUST be the value of the flow call.

#### 3.4.3. `Flow`

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

**3.4.3.1** `description` MUST be the flow's description (Section 3.4.1.4). `expected_agents`,
`expected_envs` and `expected_params` MUST be the classes passed to `flow` as `agents`, `envs` and
`params`. `resumable` MUST be the value passed to `flow` as `resumable`.

**3.4.3.2** Calling a flow object is specified in Section 3.13.4.

#### 3.4.4. `FlowParams`

```python
class FlowParams(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid", ser_json_inf_nan="strings")
```

**3.4.4.1** A flow author MUST declare a flow's params as fields of a subclass of `FlowParams`.

**3.4.4.2** Validation of a params model MUST refuse a key the model does not declare.

**3.4.4.3** Serialization of a params model MUST write an infinite or NaN float as the string
`"Infinity"`, `"-Infinity"` or `"NaN"`.

**3.4.4.4** Where hmz is given params for a flow call, it MUST read them as follows, in order:

1. An instance of the flow's own params model MUST be used as it is.
2. An instance of another `pydantic.BaseModel` MUST be dumped and validated into the model.
3. A mapping MUST be validated into the model. Where validation fails, each value that is a `str`
   and whose field failed MUST be parsed as JSON where it is JSON, and the mapping MUST be validated
   once more.
4. Any other value MUST raise `ParamsError`.

**3.4.4.5** A params value that fails validation under Section 3.4.4.4 MUST raise `ParamsError`.

### 3.5. Flow context, state and resumption

#### 3.5.1. `FlowContext`

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

**3.5.1.1** Each flow call MUST have a context of its own.

**3.5.1.2** `flow` MUST be the flow object being called.

**3.5.1.3** `budget` MUST be the flow call's effective budget (Section 3.12.2) as of the moment it
is read.

**3.5.1.4** `usage` MUST be what the flow call and every flow call under it have spent, as of the
moment it is read.

**3.5.1.5** `state` MUST be the flow call's `FlowState` for a resumable flow, and `None` otherwise.

**3.5.1.6** `resumed` MUST be `True` where the flow call is a resumed call, and `False` otherwise.

#### 3.5.2. `FlowState`

```python
class FlowState(Protocol):
    def __getitem__(self, key: str) -> Any: ...
    def __setitem__(self, key: str, value: Any) -> None: ...
    def __delitem__(self, key: str) -> None: ...
    def __contains__(self, key: str) -> bool: ...
```

**3.5.2.1** `state[key] = value` MUST raise `StateNotSerializable` where `key` is not a `str`, and
where `value` cannot be serialized as JSON with infinities and NaN allowed. A refused write MUST
leave the state unchanged.

**3.5.2.2** What `state[key]` returns after `state[key] = value` MUST be the JSON round trip of
`value`, so that a fresh epic and a resumed one read identical values.

**3.5.2.3** Every write and every deletion MUST be durable before `__setitem__` or `__delitem__`
returns, so that an epic stopped or killed afterwards and then resumed reads the state as it was at
that write.

**3.5.2.4** `state[key]` and `del state[key]` MUST raise `KeyError` where nothing is kept under
`key`. `key in state` MUST be `True` exactly where something is kept under `key`.

**3.5.2.5** Mutating a value read from the state MUST NOT change the state. A flow MUST assign the
value again for the change to be kept.

**3.5.2.6** A resumable flow called where no progress is recorded (a nested call under a top call of
a flow that is not resumable) MUST be given a state held only for the epic's lifetime.

#### 3.5.3. Sessions in state

**3.5.3.1** A flow MUST be able to write a `Session` into its state, alone or anywhere inside a
value. Such a write MUST keep the session's conversation as it stands at the write, and MUST NOT be
affected by any turn the session takes afterwards.

**3.5.3.2** The write of Section 3.5.3.1 MUST raise `StateNotSerializable`, and MUST write nothing,
where any of the following holds:

1. The session has taken no turn.
2. A turn of the session is under way.
3. The session is closed.
4. The session belongs to an agent handed to a flow call other than the one whose state is written.
5. The session is an outworlder's.
6. The session's harness does not fork (Section 3.6.4).
7. The session's harness does not keep its conversations as files (`opencode`, `mimo`).
8. The session's last turn ran with harness location env or standalone.

**3.5.3.3** Every read of a key whose value holds a kept session MUST return a new session of the
reading call's agent of the same role. The first turn of that new session MUST carry the kept
conversation on, from where it stood when written, as a fork.

**3.5.3.4** A kept session MUST be readable, and carried on, in the epic that wrote it and in every
epic that resumes that epic. Several epics MUST be able to carry on one kept session, each
independently.

**3.5.3.5** The first turn of a session read back under Section 3.5.3.3 MUST raise
`UnsupportedOperation`, before its harness is started and before anything is copied, where any of
the following holds:

1. The role's agent is of a harness other than the one that kept the conversation.
2. The turn's harness location is env or standalone.
3. The turn's harness location is local and its env location standalone, its harness forks only in
   place (Section 3.6.4), and the turn's environment backend is `docker`, `swarm`, `slurm` or
   `apple-container`.

**3.5.3.6** The first turn of a session read back under Section 3.5.3.3 MUST raise `SessionError`
where the kept conversation no longer exists, or where the epic already holds a different copy of
that conversation that carrying this one on would replace.

**3.5.3.7** A session read back under Section 3.5.3.3 and written into the state again before it
takes a turn MUST be written as the kept conversation it carries on, without copying anything.

#### 3.5.4. Resumption

**3.5.4.1** An epic MUST be resumable exactly where its top call is of a resumable flow. How a user
asks for a resume, and which epic is picked up, is specified in [CLI] and Section 3 of [CORE].

**3.5.4.2** A resumed epic MUST be a new epic. The top call of a resumed epic MUST be a resumed call
of the earlier epic's top call, unconditionally.

**3.5.4.3** A nested call made under a resumed call MUST be a resumed call of the earlier epic's
nested call that has the same caller, the same callee ref, the same task, the same agents, the same
environments and the same params, taking such calls in the order they were made. Where no earlier
call remains unclaimed, the nested call MUST start afresh with an empty state.

**3.5.4.4** For Section 3.5.4.3, two agents MUST be the same where they have the same harness,
account, model, effort, permission and skills, and two environments MUST be the same where they were
derived by the same chain of derivations (Section 3.11.6) from the same backend, provider and
workdir. An outworlder made with `Outworlder.new()` MUST NOT be the same as the epic's own
outworlder.

**3.5.4.5** A resumed call of a resumable flow MUST see the state its earlier call had when that
epic ended. A flow that is not resumable MUST have no state, and its nested calls MUST still be
eligible for resumption.

**3.5.4.6** Temporary copies and scratch directories (Section 3.11.6) made by an epic whose top call
is of a resumable flow MUST be kept when the epic ends, and a resumed call that derives one by the
same id MUST be given the same directory.

### 3.6. Agents

#### 3.6.1. `AgentCollection`

```python
class AgentCollection(TypedDict, extra_items=ReadOnly[Agent]): ...
```

**3.6.1.1** A flow author MUST declare a flow's agent roles as the keys of a subclass of
`AgentCollection`, each annotated with its role type.

**3.6.1.2** A role annotated `NotRequired[...]` MAY be left out by whoever runs or calls the flow.
Every other role that is not runtime-filled MUST be given.

**3.6.1.3** An `Outworlder` role MUST be filled by hmz (Section 3.10.1) and MUST NOT be given on the
command line.

#### 3.6.2. `Agent`

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
    # Each takes HookFn[<Moment>HookParams, <Moment>HookResult] | None for its moment (Section 3.9).
    def on_session_start(self, fn: HookFn[...] | None) -> None: ...
    def on_user_prompt_submit(self, fn: HookFn[...] | None) -> None: ...
    def on_pre_tool_use(self, fn: HookFn[...] | None) -> None: ...
    def on_notification(self, fn: HookFn[...] | None) -> None: ...
    def on_stop(self, fn: HookFn[...] | None) -> None: ...
    def on_session_end(self, fn: HookFn[...] | None) -> None: ...
```

**3.6.2.1** The class attributes `_permission`, `_skills`, `_tools` and `_clis` are part of the
public API. A flow author MUST declare a role's permission (Section 3.7), skills (Section 3.6.7),
fake tools and fake command lines (Section 3.6.6) by setting these attributes on the role type.

**3.6.2.2** A handed agent's sessions MUST run under exactly its role type's `_permission`, MUST be
given exactly its role's skills, MUST offer exactly its role's `_tools`, and MUST put exactly its
role's `_clis` on the agent's `PATH`.

**3.6.2.3** `role` MUST be the key of the `AgentCollection` the agent fills.

**3.6.2.4** `harness` MUST be the agent's `HarnessKind`.

**3.6.2.5** `model` MUST be the model as it was given.

**3.6.2.6** `effort` MUST be the effort in the harness's own words, and `""` where none was given or
the effort given was `auto`.

**3.6.2.7** `provider` MUST be the name of the account the agent's turns run as, and `""` where the
turns run as the account the harness is already signed into on the harness machine.

**3.6.2.8** `spawn`, `fork` and `run` are specified in Section 3.8, `derive` in Section 3.7.3, and
the `on_*` methods in Section 3.9.

#### 3.6.3. `HarnessKind`

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

**3.6.3.1** `HarnessKind` MUST have exactly the members above with exactly the values above. Each
value MUST be the name by which the command line names that harness.

**3.6.3.2** `LITELLM` MUST denote a model called directly, one chat completion per turn over the
session's history, with no tools, no shell and no filesystem.

**3.6.3.3** `ACP` MUST denote a harness that a user added by hand and that hmz drives over the Agent
Client Protocol.

#### 3.6.4. Harness protocols and `HARNESS_AGENTS`

```python
HARNESS_AGENTS: Mapping[HarnessKind, type]
```

**3.6.4.1** `HARNESS_AGENTS` MUST be a read-only mapping from every `HarnessKind` to its harness
protocol, as in the table of Section 3.6.4.2, and MUST map `ACP` to `Agent`.

**3.6.4.2** Each harness protocol MUST derive from `Agent` and from exactly the mixins marked for it
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

The columns are, in order, `GoalCommandAgentMixin`, `LoopCommandAgentMixin`, `SteeringAgentMixin`,
`PermissionRequestHookAgentMixin`, `SubagentStartHookAgentMixin` together with
`SubagentStopHookAgentMixin`, `AskUserHookAgentMixin` and `FakeToolAgentMixin`.

**3.6.4.3** Each harness MUST fork sessions to the extent below:

| Fork extent | Harnesses |
| --- | --- |
| into any workdir on the same machine | `claude`, `codex`, `kimi`, `litellm` |
| only in place: into the same workdir | `pi`, `omp`, `grok`, `opencode`, `mimo`, `qwen`, `acp` |
| none | `cursor-agent`, `mcode`, `agy`, `dsh` |

**3.6.4.4** A role typed as a harness protocol asks for that harness and every mixin marked for it.
Where such a role is given an agent of another harness, hmz MUST refuse: before an epic starts as
specified in [CLI], and in a nested call with `HarnessMismatch`.

**3.6.4.5** A role typed as `Agent` with mixins MAY be filled by any harness that serves every mixin
it declares.

**3.6.4.6** On a `grok` agent whose role offers any fake tool, each of the following turns MUST
raise `HarnessUnrecoverable`: a turn with an `output_schema`, the first turn of a fork, a turn whose
permission has `online` `NONE`, and a turn whose permission has `local` `READ` or `NONE`.

#### 3.6.5. Agent mixins

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

**3.6.5.1** `GoalCommandAgentMixin` MUST grant `run` of a prompt that, with leading whitespace
removed, is `/goal` or starts with `/goal` followed by whitespace. Such a turn MUST hand the
objective to the harness's own goal command, which pursues it until the harness decides it is met.

**3.6.5.2** `LoopCommandAgentMixin` MUST grant `run` of a prompt that, with leading whitespace
removed, starts with `/loop`. Such a prompt MUST be passed to the harness as written.

**3.6.5.3** `run` of a prompt of Section 3.6.5.1 or Section 3.6.5.2 on an agent whose grant lacks
the mixin MUST raise `CapabilityNotGranted` before anything is sent. hmz MUST pass every other
prompt to the harness unchanged and MUST NOT interpret any other slash command.

**3.6.5.4** `SteeringAgentMixin` MUST grant `steer` (Section 3.8.4).

**3.6.5.5** `PermissionRequestHookAgentMixin`, `SubagentStartHookAgentMixin`,
`SubagentStopHookAgentMixin` and `AskUserHookAgentMixin` MUST grant `on_permission_request`,
`on_subagent_start`, `on_subagent_stop` and `on_ask_user` respectively. Calling one of these on an
agent whose grant lacks its mixin MUST raise `CapabilityNotGranted`.

**3.6.5.6** `FakeToolAgentMixin` MUST permit a role type to declare a non-empty `_tools`.

#### 3.6.6. Fake tools and fake command lines

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

**3.6.6.1** Every session of an agent MUST offer each `FakeTool` of its role's `_tools` to the
harness as a tool named `name`, described by `about`, taking the JSON Schema of `takes`, or no
arguments where `takes` is `None`.

**3.6.6.2** When the agent calls a fake tool, hmz MUST call `call` in the flow's process, on the
flow's event loop, as the flow, with an instance of `takes` built from the arguments, or with no
argument where `takes` is `None`. `call` MAY be synchronous or asynchronous. The turn MUST wait for
it.

**3.6.6.3** The agent MUST read back the value `call` returns as text: a `str` as it is, `None` as
`done`, and any other value as JSON.

**3.6.6.4** An exception `call` raises MUST be answered to the agent as the tool failing, and MUST
NOT fail the turn or the flow.

**3.6.6.5** Fake tools MUST be served only where the harness serves `FakeToolAgentMixin` and its
harness location is local. A turn whose harness location is env or standalone on an agent whose role
offers fake tools MUST raise `UnsupportedOperation`.

**3.6.6.6** `FakeCli(...)` MUST raise `ValueError` where `name` is empty, starts with `.` or `-`, or
holds a character other than ASCII letters, digits, `.`, `_` and `-`; where `commands` is empty; or
where two commands share a name.

**3.6.6.7** Every session of an agent MUST put each `FakeCli` of its role's `_clis` on the `PATH` of
every process of the harness, as a program called `name` taking a first argument naming one of
`commands`.

**3.6.6.8** Each `FakeCommand` MUST take one `--<field>` option per field of `takes`, whose help is
the field's description and which is required where the field has no default. A `bool` field MUST be
a `--<field>`/`--no-<field>` pair, a list field MUST take several words, and a `Literal` or `Enum`
field MUST take one of its values.

**3.6.6.9** The program MUST print help and exit 0 for `--help`; MUST print usage and an error to
stderr and exit 2 for arguments that the options of Section 3.6.6.8 or `takes` refuse; and otherwise
MUST call the command's `call` as Section 3.6.6.2 specifies for a tool, printing a returned `str` as
it is, nothing for `None`, and any other value as JSON, then exit 0. A `SystemExit(n)` raised by
`call` MUST exit `n`. Any other exception raised by `call` MUST exit 1 with the error on stderr.

**3.6.6.10** `FakeCli.run(argv)` MUST return the exit status, stdout and stderr the program
specified in Section 3.6.6.9 produces for `argv`, the words after the program's name.

**3.6.6.11** Every harness other than `litellm` MUST serve `_clis` without a mixin. A `run` of a
`litellm` agent whose grant includes any fake command line MUST raise `UnsupportedOperation`.

#### 3.6.7. Skills

**3.6.7.1** Each entry of a role type's `_skills` MUST be either the name of a directory under the
flow directory's `skills/`, holding a `SKILL.md`, or a git URL, recognised by containing `#` or
`://`. A git URL followed by `#<skill>` MUST select the one skill `skills/<skill>` of the
repository; a git URL without `#` MUST select every skill under its `skills/`.

**3.6.7.2** hmz MUST resolve a role's skills once per epic and role, before the role's first turn. A
skill named and absent MUST raise `FlowDefinitionError`, as MUST a URL that cannot be fetched or
names no skill of its repository. A single-file flow MUST have no skills of its own.

**3.6.7.3** Where a flow's own `skills/` and a repository named in `_skills` hold a skill of one
name, the role MUST be given the flow's own.

**3.6.7.4** An installed flow's skills that its roles name by a URL written as a string literal MUST
be fetched at install and read from the installed flow at run time without fetching.

**3.6.7.5** hmz MUST make a session's skills available where its harness reads a project's skills,
for the session's lifetime only. hmz MUST NOT install a skill into any harness's user-level
configuration. A harness that reads no project skills MUST be given none.

### 3.7. Permissions and approval

#### 3.7.1. `PermissionKind`

```python
class PermissionKind(StrEnum):
    NONE = "none"
    READ = "read"
    ALL = "all"
```

**3.7.1.1** `PermissionKind` MUST be totally ordered `NONE < READ < ALL` under `<`, `<=`, `>` and
`>=`. `NONE` MUST permit nothing, `READ` reading and not writing, and `ALL` reading and writing.

**3.7.1.2** Comparing a `PermissionKind` with a value that is not one of the three values MUST raise
`TypeError`.

#### 3.7.2. `Permission`

```python
@dataclass(frozen=True, slots=True)
class Permission:
    local: PermissionKind = PermissionKind.ALL
    user: PermissionKind = PermissionKind.READ
    system: PermissionKind = PermissionKind.READ
    online: PermissionKind = PermissionKind.ALL

    def covers(self, other: Permission) -> bool: ...
```

**3.7.2.1** `Permission` MUST have exactly the four fields `local`, `user`, `system` and `online`,
with exactly the defaults above.

**3.7.2.2** `local` MUST govern the workdir of the environment a turn works in. `user` MUST govern
the rest of the home directory of the operating-system user the harness runs as. `system` MUST
govern everything else on the machine. `online` MUST govern the network, including the harness's own
web search and fetch tools.

**3.7.2.3** Construction MUST coerce each field with `PermissionKind(value)`. Construction MUST
raise `ValueError` where a field is not one of the three values, where `local >= user >= system`
does not hold, or where `online` is `READ`.

**3.7.2.4** `covers(other)` MUST return `True` exactly where each of the four fields is `>=` the
same field of `other`.

**3.7.2.5** hmz MUST NOT run a session with wider access than its permission. Where neither the
harness nor the machine can hold a session to its permission, opening the session MUST raise
`HarnessSandboxed`. How a permission is held is specified in Section 4 of [CORE].

#### 3.7.3. `Agent.derive`

**3.7.3.1** `derive(permission=..., skills=...)` MUST return a new handed agent of the same agent
whose sessions run under `permission`, or under this agent's permission where `permission` is
`None`, and are given `skills`, or all of this agent's skills where `skills` is `None`. The original
agent MUST be unchanged.

**3.7.3.2** `derive` MUST raise `TypeError` where `permission` is neither `None` nor a `Permission`.
`derive` MUST raise `CapabilityNotGranted` where this agent's permission does not cover
`permission`, and where `skills` names a skill this agent was not granted.

**3.7.3.3** A derived agent MUST share the original's hooks and sessions: a session of either MUST
be usable by the other, and a hook hung on either MUST cover both.

**3.7.3.4** A derived agent MUST keep the original's fake tools and fake command lines.

#### 3.7.4. Approval policy

**3.7.4.1** hmz MUST run every harness with approvals bypassed, so that no session waits for a
person to approve an action.

**3.7.4.2** hmz MUST NOT run any harness in a mode in which a model reviews or approves the agent's
actions.

**3.7.4.3** Where a managed policy of the harness forbids bypassing approvals, hmz MUST run the
harness in the most permissive mode that remains and in which no model reviews actions, and hmz MUST
approve every request the harness then makes, subject to Section 3.7.4.4.

**3.7.4.4** Where a `PERMISSION_REQUEST` hook is hung, its answer MUST decide the request,
overriding Section 3.7.4.1 and Section 3.7.4.3.

**3.7.4.5** What limits an agent's actions MUST be its permission and the hooks the flow hangs on
it, and nothing else of the approval machinery of its harness.

### 3.8. Sessions and turns

#### 3.8.1. `Agent.spawn` and `Session`

```python
class Session(Protocol):
    @property
    def agent(self) -> Agent: ...
    @property
    def usage(self) -> Usage: ...
```

**3.8.1.1** `spawn()` MUST return a new session of the agent that has taken no turn. `spawn` MUST
NOT start the harness and MUST NOT settle where the session works; the session's first turn MUST do
both.

**3.8.1.2** `spawn` MUST raise `FlowCancelled` where the flow call's caller or the epic has ended.

**3.8.1.3** A session MUST hold a conversation and no environment. Each turn of a session MUST name
the environment it works in.

**3.8.1.4** `Session.agent` MUST be the agent whose conversation the session is. `Session.usage`
MUST be what the session's turns have spent, as of the moment it is read.

**3.8.1.5** A session MUST be closed at the earlier of: the end of the flow call that opened it and
of every flow call that call started; and the moment no reference to it remains. A session MUST be
closed exactly once. Closing a session MUST fire `SESSION_END` (Section 3.9).

**3.8.1.6** A session MUST NOT offer a method to close it.

#### 3.8.2. `Agent.run`

**3.8.2.1** `run(prompt, session=..., env=..., output_schema=..., budget=...)` MUST take one turn in
`session`, working in `env`, and MUST return the text of the agent's last message, or, where
`output_schema` is given, an instance of `output_schema`.

**3.8.2.2** `env=None` MUST mean the epic's workspace environment. A turn of a `litellm` agent MUST
be given `env=None`.

**3.8.2.3** `budget`, where given, MUST limit this turn alone, in addition to every budget above it
(Section 3.12.2).

**3.8.2.4** A turn MUST proceed in this order:

1. Where the prompt needs a mixin the grant lacks (Section 3.6.5), raise `CapabilityNotGranted`.
   Where a budget over the turn is spent, raise the `BudgetExceeded` subclass for the spent limit.
   Nothing is sent in either case.
2. On the session's first turn, start the harness for `env`. On a later turn whose `env` differs
   from the previous turn's, carry the session to `env` as Section 3.8.2.6 specifies.
3. On the session's first turn only, fire `SESSION_START`. A non-empty `context` in its result MUST
   be prepended to the prompt, separated by a blank line.
4. Fire `USER_PROMPT_SUBMIT` with the prompt. A result with `block=True` MUST raise `SessionError`
   and the turn MUST NOT run. A non-empty `context` MUST be appended to the prompt after a blank
   line.
5. Have the harness take the turn. Steers queued before it starts MUST be appended to the prompt,
   each after a blank line.
6. Where no steer is pending, fire `STOP`. A result with `block=True` and a non-empty `reason` MUST
   send `reason` as the next prompt of the same turn and MUST increment `again`. A result with an
   empty `reason` MUST NOT block.
7. Where steers arrived during the harness's turn, send them, joined by blank lines, as the next
   prompt of the same turn, and continue at item 6.
8. Where `output_schema` is given, read the final text as Section 3.8.2.5 specifies.

**3.8.2.5** hmz MUST validate `output_schema` with `model_validate_json` against, in order: the
whole final text with surrounding whitespace removed; each fenced code block of it; and the span
from its first `{` to its last `}`. The first that validates MUST be returned. Where none validates,
`run` MUST raise `OutputSchemaError`.

**3.8.2.6** A later turn whose `env` is another workdir on the machine of the previous turn MUST
carry the conversation there as a fork of the session cut by that turn, on a harness that forks into
any workdir (Section 3.6.4.3). Every other harness MUST raise `UnsupportedOperation` for such a
turn. Every harness MUST raise `UnsupportedOperation` for a later turn whose `env` is on another
machine than the previous turn's. A refused turn MUST leave the session where it was.

**3.8.2.7** `run` MUST raise:

1. `SessionError` where `session` is not a session of this agent or of an agent derived from it or
   from which it was derived.
2. `TypeError` where `env` is not an environment handed out in this epic.
3. `UnsupportedOperation` where `env` is not `None` on a `litellm` agent.
4. `SessionError` where a turn of `session` is under way.
5. `SessionError` where `session` is closed.
6. `FlowCancelled` where the flow call's caller or the epic has ended.
7. `SessionError` where `env` is on this machine and its workdir is not a directory.
8. `SessionError` on the first turn of a fork whose parent has taken a turn since the fork.
9. `SessionError` where the turn was interrupted.
10. The `BudgetExceeded` subclass for the limit, where a budget over the turn is spent before or
    during the turn (Section 3.12.3).
11. The `HarnessError` subclass of Section 3.15.3 the turn's failure maps to, where the harness
    failed the turn.
12. `asyncio.CancelledError` where the task awaiting `run` is cancelled; the harness MUST be
    interrupted.

**3.8.2.8** One session MUST take at most one turn at a time. Two sessions of one agent MAY take
turns concurrently.

**3.8.2.9** Where the harness has no means to do what a turn requires, `run` MUST raise
`UnsupportedOperation`.

#### 3.8.3. Project configuration across machines

**3.8.3.1** Program-running configuration MUST be read as Section 6.2.9 of [CORE] defines it, found
from the session directory (Section 6.2.1 of [CORE]) of the turn.

**3.8.3.2** Where a turn's session is mirrored and its harness machine is not its env machine,
opening a session, forking it into a workdir, carrying it on, and every later turn MUST raise
`UnsupportedOperation` where program-running configuration is present, as Section 6.7 of [CORE]
specifies.

**3.8.3.3** The message of the exception of Section 3.8.3.2 MUST name each file and key responsible.

**3.8.3.4** How project configuration is layered with hmz's own configuration is specified in
Section 4.5 of [CORE].

#### 3.8.4. `SteeringAgentMixin.steer`

**3.8.4.1** `steer(prompt, session=..., queued=True)` MUST put `prompt` into the turn `session` is
taking, as typing at the agent would.

**3.8.4.2** With `queued=True`, the agent MUST receive the prompt at its next opportunity and
continue. With `queued=False`, the harness's current step MUST be interrupted and the turn MUST
continue from the prompt.

**3.8.4.3** `steer` MUST raise `CapabilityNotGranted` where the grant lacks `SteeringAgentMixin`,
`SessionError` where `session` is another agent's or closed, and `SessionError` where `session` has
no turn under way.

#### 3.8.5. `Agent.fork`

**3.8.5.1** `fork(session)` MUST return a new session that continues `session`'s conversation.
`session` MUST be unchanged.

**3.8.5.2** The fork MUST be cut by its first turn, in that turn's `env`. `session` MUST be held
open until the fork's first turn.

**3.8.5.3** `fork` MUST raise `SessionError` where `session` is not this agent's, is closed, or has
taken no turn.

**3.8.5.4** The fork's first `run` MUST raise `UnsupportedOperation` where the harness does not
fork, where the turn's `env` is on another machine than `session`'s last turn, or where the turn's
`env` is another workdir on a harness that forks only in place. It MUST raise `SessionError` where
`session` has taken a turn since the fork, or where the harness could not cut the fork.

#### 3.8.6. Retrying a dropped Codex turn

**3.8.6.1** Where the response stream of a `codex` turn breaks, hmz MUST retry the turn in the same
session at least once before `run` raises `HarnessDropped`.

### 3.9. Hooks

#### 3.9.1. `HookKind`, `HookFn`, `HookParams`, `HookResult`, `HOOK_TYPES`

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

**3.9.1.1** `HookKind` MUST have exactly the members above with exactly the values above.

**3.9.1.2** For each moment, `hmz.flows` MUST export a params class `<Moment>HookParams` deriving
from `HookParams` and a result class `<Moment>HookResult` deriving from `HookResult`, where
`<Moment>` is the member name in PascalCase (`SessionStart`, `UserPromptSubmit`, `PreToolUse`,
`PermissionRequest`, `Notification`, `Stop`, `SessionEnd`, `SubagentStart`, `SubagentStop`,
`AskUser`, `OutworlderRun`). Each MUST be a frozen, slotted, keyword-only dataclass.

**3.9.1.3** `HOOK_TYPES` MUST be a read-only mapping from each `HookKind` to the pair of its params
class and result class.

**3.9.1.4** `ctx` MUST be the context of the flow call the agent was handed to. `session` MUST be
the session the moment arrived in.

#### 3.9.2. Fields

**3.9.2.1** The params fields beyond `ctx` and `session`, and the result fields with their defaults,
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

**3.9.2.2** A result built with no arguments MUST change nothing.

**3.9.2.3** `tool` MUST be the tool's name as the harness names it, and `input` its arguments, or an
empty mapping where the harness gives none.

**3.9.2.4** `said` of `STOP` MUST be the agent's last text, and `again` the number of times a `STOP`
hook has already kept this turn going.

**3.9.2.5** A `PRE_TOOL_USE` result with `block=True` MUST refuse the tool and tell the agent
`reason`, on a harness that gates tools through its own hooks (`claude`, `qwen`). On every other
harness, `PRE_TOOL_USE` MUST be fired for a tool already reached for and its result MUST NOT refuse
it.

**3.9.2.6** A `PERMISSION_REQUEST` result with `allow=False` MUST refuse the tool, overriding
Section 3.7.4, and the agent MUST be told `reason`.

**3.9.2.7** An `ASK_USER` result's `answer` MUST be told to the agent as the answer to its question.
hmz MUST accept an `answer` that is not one of `options`. `answer=None` MUST leave the question
unanswered and let the agent continue without an answer.

**3.9.2.8** An `OUTWORLDER_RUN` result's `output` MUST be what the outworlder's `run` returns.

**3.9.2.9** hmz MUST fire `SUBAGENT_START` and `SUBAGENT_STOP` on every harness that serves their
mixins. The `context` of a `SUBAGENT_START` result and every field of a `SUBAGENT_STOP` result MUST
be delivered to no harness.

#### 3.9.3. Hanging hooks

**3.9.3.1** Calling an `on_<moment>` method with a hook MUST replace the hook hung on that moment of
that agent. Calling it with `None` MUST remove the hook.

**3.9.3.2** A hook MUST cover every session of its agent, including sessions opened after it was
hung and sessions of agents derived from it.

**3.9.3.3** A callee's hooks MUST NOT be fired for its caller's sessions, and a caller's hooks MUST
NOT be fired for its callee's sessions.

**3.9.3.4** A hook MUST run on the flow's event loop, as the flow its agent was handed to. An
exception a hook raises MUST fail the turn the moment arrived in, and `run` MUST raise it.

**3.9.3.5** A moment delivered from inside the harness whose hook has not answered within 900
seconds MUST be answered as if no hook were hung. `ASK_USER` MUST have no such limit.

**3.9.3.6** A hook hung during a turn MUST apply to that turn's later moments, except where the hook
changes how the harness is started, in which case it MUST apply from the next turn. The hooks that
change how a harness is started are specified in Section 4 of [CORE].

**3.9.3.7** Which hooks refuse a session for where its harness runs is specified in Section 6 of
[CORE].

### 3.10. Outworlder

#### 3.10.1. `Outworlder`

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

**3.10.1.1** In the top call, hmz MUST fill every `Outworlder` role with the epic's outworlder: the
person who started the epic, through the frontend they started it from.

**3.10.1.2** An outworlder MUST take turns as an agent of the flow. `run` on the epic's outworlder
MUST put `prompt` to the person and return what they answered. With `output_schema`, it MUST ask one
question per field and return the model built from the answers.

**3.10.1.3** `run` on an outworlder MUST accept an `env` and MUST otherwise ignore it.

**3.10.1.4** `fork` on an outworlder MUST raise `UnsupportedOperation`. `derive` with non-empty
`skills` on an outworlder MUST raise `CapabilityNotGranted`.

**3.10.1.5** `Outworlder.new()` MUST return a new outworlder whose every `run` is answered by the
hook hung with `on_outworlder_run`. Until such a hook is hung, it MUST be away.

**3.10.1.6** `on_outworlder_run` on an outworlder not made with `Outworlder.new()` MUST raise
`CapabilityNotGranted`.

#### 3.10.2. Away

**3.10.2.1** `away` MUST be `True` where the epic was started by `hmz exec`, or where `/afk` is on
for the role, and `False` otherwise.

**3.10.2.2** While an outworlder is away, `run` MUST return at once: `""` for text; the schema built
from its defaults where every field of `output_schema` has a default; and otherwise MUST raise
`OutworlderAway`.

#### 3.10.3. Outworlders in nested calls

**3.10.3.1** A caller MAY pass its own outworlder, an outworlder made with `Outworlder.new()`, or
nothing, for a callee's `Outworlder` role. Where nothing is passed, the callee MUST be given the
epic's outworlder.

**3.10.3.2** A caller MAY pass an outworlder for a callee's agent role typed `Agent` that declares
no mixin and no harness. Passing one for a role that declares a mixin or a harness MUST raise
`CapabilityMissing`.

**3.10.3.3** The epic's outworlder MUST be asked, and MUST report `away`, as the `Outworlder` role
the top call filled with it, under whatever role name a caller passes it.

### 3.11. Environments

#### 3.11.1. `EnvCollection`

```python
class EnvCollection(TypedDict, extra_items=ReadOnly[Env]): ...
```

**3.11.1.1** A flow author MUST declare a flow's environment roles as the keys of a subclass of
`EnvCollection`, each annotated with its role type.

**3.11.1.2** A role annotated `NotRequired[...]` MAY be left out. Every other role that is not
runtime-filled MUST be given.

#### 3.11.2. `Env`

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

**3.11.2.1** `workdir` MUST be the directory, on the env machine, in which commands run and relative
paths resolve. It MUST be absolute, or start with `~/` for a directory under the home of the user an
`ssh` login lands as.

**3.11.2.2** `backend` MUST be the environment's `EnvBackendKind`.

**3.11.2.3** `provider` MUST be `""` for `local`, and otherwise the name of the runtime, or for
`ssh` the destination, the environment is on, as specified in Section 7 of [CORE].

**3.11.2.4** `available` MUST be whether the env machine was reachable and the workdir existed when
hmz last checked.

**3.11.2.5** `role` MUST be the key of the `EnvCollection` the environment fills.

**3.11.2.6** `derive_subdir(subdir=...)` MUST return an environment on the same machine, filling the
same role with the same grant, whose workdir is `subdir` under this workdir, creating the directory
where missing. It MUST raise `ValueError` where `subdir` is absolute or climbs out of this workdir,
and `EnvError` where the directory cannot be made.

#### 3.11.3. `LocalEnv`

```python
class LocalEnv(Env, Protocol): ...
```

**3.11.3.1** In the top call, hmz MUST fill every `LocalEnv` role with the epic's workspace
environment, granted what the role declares. Such a role MUST NOT be given on the command line.

**3.11.3.2** A caller MAY pass, for a callee's `LocalEnv` role, nothing or an environment on this
machine. Where nothing is passed, the callee MUST be given the epic's workspace environment, granted
what the callee's role declares. Passing an environment on another machine MUST raise
`CapabilityMissing`.

#### 3.11.4. `EnvBackendKind` and `SequenceNotStr`

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

**3.11.4.1** `EnvBackendKind` MUST have exactly the members above with exactly the values above.
Each backend is specified in Section 7 of [CORE].

**3.11.4.2** `SequenceNotStr[T]` MUST be satisfied by lists and tuples of `T` and MUST NOT be
satisfied by `str`.

#### 3.11.5. Running commands and files

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

**3.11.5.1** `exec(argv)` MUST run one program, with its arguments as given and no shell between, in
the workdir, and MUST return its exit status, its stdout and its stderr, decoded as UTF-8.

**3.11.5.2** `timeout` MUST be in seconds, `0` meaning no limit. A program that runs past its
timeout MUST be killed and `exec` MUST raise `EnvCommandTimeout`. A program that cannot be started
MUST make `exec` raise `EnvError`.

**3.11.5.3** `exec(script)` with a `str` MUST run the script as `bash -c` would, in the workdir,
with the same timeout, return value and exceptions as Section 3.11.5.1 and Section 3.11.5.2. A
string `exec` on an environment whose grant lacks `BashEnvMixin` MUST raise `CapabilityNotGranted`.

**3.11.5.4** `exec` MUST raise `TypeError` unless given exactly one command, positionally or as
`argv=` or `script=`.

**3.11.5.5** `exec` on an environment whose grant lacks `ShellEnvMixin` MUST raise
`CapabilityNotGranted`.

**3.11.5.6** `read(path)` MUST return the bytes of the file at `path`, relative to the workdir or
absolute. It MUST raise `EnvFileNotFound` for a missing file and `EnvPermissionDenied` for one that
cannot be read.

**3.11.5.7** `write(path, data)` MUST replace the file at `path` whole with `data`, creating the
directories above it. It MUST raise `EnvPermissionDenied` for a file that cannot be written.

**3.11.5.8** `read` or `write` on an environment whose grant lacks `FilesEnvMixin` MUST raise
`CapabilityNotGranted`.

#### 3.11.6. Worktrees, temporary copies and scratch directories

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

**3.11.6.1** Each environment derived by a method of this section MUST be on the same machine, fill
the same role and carry the same grant as the environment it was derived from.

**3.11.6.2** `derive_worktree` MUST add a git worktree of the repository the workdir is in, with
`ref` checked out detached, or what the workdir has checked out where `ref` is `None`, at `dir`,
relative to the workdir or absolute, or at a fresh directory hmz picks where `dir` is `None`. hmz
MUST NOT remove a worktree it added. `derive_worktree` MUST raise `WorktreeError` where the workdir
is not in a git repository, `ref` is unknown, or `dir` is taken.

**3.11.6.3** `derive_temp_clone(id)` MUST return an environment at a copy of the workdir. The same
`id` from the same environment MUST be the same copy, made once. It MUST raise `TempCloneBusy` where
another environment holds the copy under `id`, and `EnvError` where the copy fails.

**3.11.6.4** `derive_temp_clone` MUST need nothing on the env machine but `sh` and `cp`, except that
copying a workdir that is a linked git worktree MUST also need `git`; on a machine without `git`,
that copy MUST raise `EnvError`.

**3.11.6.5** `derive_scratch(id)` MUST return an environment at a directory beside the workdir on
the same machine, empty when first made. The same `id` MUST be the same directory. It MUST raise
`ScratchError` where the directory cannot be made.

**3.11.6.6** `destroy_temp_clone(id)` and `destroy_scratch(id)` MUST remove the directory at once
and free `id`. Removing a directory that does not exist MUST do nothing. `destroy_scratch` MUST
raise `ScratchError` where the directory cannot be removed.

**3.11.6.7** Temporary copies and scratch directories MUST be removed when the flow call that made
them and every flow call it started have ended, except as Section 3.5.4.6 specifies.

**3.11.6.8** A method of this section on an environment whose grant lacks its mixin MUST raise
`CapabilityNotGranted`.

#### 3.11.7. Snapshots and rewinding

```python
class RewindableEnvMixin(Protocol):
    async def snapshot(self, name: str | None = None) -> str: ...
    async def rewind(self, ref: str) -> None: ...
    async def snapshots(self) -> list[str]: ...

class GitEnvMixin(RewindableEnvMixin, Protocol): ...
```

**3.11.7.1** `RewindableEnvMixin` MUST be an interface only. A role that declares it and not
`GitEnvMixin` MUST be granted none of its methods, and each MUST raise `CapabilityNotGranted`.

**3.11.7.2** Under `GitEnvMixin`, `snapshot(name)` MUST record the whole git worktree containing the
workdir, comprising the commit checked out, the index, and every file git does not ignore, untracked
files included, as a commit kept under `refs/hmz/snapshots/<name>`, and MUST return that ref. It
MUST NOT move what is checked out and MUST NOT change the index or any file. A `name` already kept
MUST be replaced. Where `name` is `None`, hmz MUST pick a name of the form `<UTC timestamp>-<4 hex
digits>`, whose order is the order of the snapshots taken.

**3.11.7.3** Under `GitEnvMixin`, `rewind(ref)` MUST restore the worktree as follows. A snapshot ref
MUST restore its commit, index and files, untracked files as untracked. Any other ref that git
resolves to a commit MUST be checked out with its files and a matching index. The branch checked
out, where there is one, MUST be moved to that commit. Files that are neither in the commit nor
ignored MUST be removed, nested repositories included. A merge, cherry-pick or revert in progress
MUST be abandoned. A rewind that git refuses part way MUST leave what is checked out where it was.
A `ref` that is empty or starts with `-` MUST be refused.

**3.11.7.4** Under `GitEnvMixin`, `snapshots()` MUST return the snapshot refs kept in the
repository, oldest first by the second they were taken in, and by name within one second. Every
worktree of one repository MUST share them.

**3.11.7.5** Ignored files, and a `.hmz/` or `.humanize/` directory at the top of the worktree, MUST
be neither recorded by `snapshot` nor removed by `rewind`.

**3.11.7.6** hmz MUST NOT remove the ref of a snapshot, other than by replacing it as Section
3.11.7.2 specifies.

**3.11.7.7** `snapshot`, `rewind` and `snapshots` MUST raise `RewindError` where the workdir is not
in a git worktree, where git knows no commit by `ref`, where `name` is not a name git can keep a ref
under, where `HEAD` is detached and the snapshot was taken before the first commit, and where git
refuses.

#### 3.11.8. Machine requirements

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

**3.11.8.1** The class attributes above are part of the public API. A flow author MUST declare what
the env machine needs by setting them on a role type. hmz MUST read each attribute only where its
mixin is declared.

**3.11.8.2** `_cpu_count` MUST be the fewest logical CPUs, `_memory` the fewest bytes of memory,
`_gpu_count` the fewest GPUs, and `_gpu_memory` the fewest bytes of memory per GPU, that the env
machine is to have.

**3.11.8.3** `_image` MUST be the image a `docker`, `swarm` or `apple-container` environment's
container is started from, as `docker run` takes it, and `""` for the provider's own image, or
`python:3.12-slim` where the provider names none. `_image` MUST have no effect on `local`, `ssh` and
`slurm` environments.

**3.11.8.4** An environment given for a role that does not meet the role's declared resources MUST
be refused with `ResourceUnmet` before any agent of the epic starts. How resources size a container
or job is specified in Section 7 of [CORE].

**3.11.8.5** A flow that declares `GitEnvMixin` or `GitWorktreeEnvMixin` for an environment whose
machine has no `git` on its `PATH`, or `BashEnvMixin` for one with no `bash`, MUST be refused with
`CapabilityMissing` before any agent of the epic starts.

### 3.12. Budgets and usage

#### 3.12.1. `Budget`, `Graceful` and `Usage`

```python
class Graceful(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")
    duration: bool = True
    cost: bool = True
    output_tokens: bool = True

class Budget(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, extra="forbid", ser_json_inf_nan="strings")
    duration: datetime.timedelta | None = None
    cost: float | None = None
    output_tokens: int | None = None
    graceful: bool | Graceful = True

    @property
    def graces(self) -> Graceful: ...

class Usage(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, extra="forbid", ser_json_inf_nan="strings")
    duration: datetime.timedelta = datetime.timedelta(0)
    cost: float = 0.0
    output_tokens: int = 0
```

**3.12.1.1** `Budget.duration` MUST limit wall-clock time from the start of the flow call or turn
the budget belongs to. `Budget.cost` MUST limit spending in US dollars. `Budget.output_tokens` MUST
limit the tokens agents write.

**3.12.1.2** A limit is graceful where `Budget.graceful` is `True`, or is a `Graceful` whose field
of the same name is `True`. A graceful limit reached MUST let a turn under way finish. A limit that
is not graceful MUST cut such a turn off at once. Each limit MUST be graceful or not independently
of the others. A `Graceful` whose three fields agree MUST be read as the `bool` they agree on.
`Budget.graces` MUST be whether each limit is graceful, as a `Graceful`.

**3.12.1.3** Constructing a `Budget` MUST raise `pydantic.ValidationError` where none of `duration`,
`cost` and `output_tokens` is set, or where any is negative.

**3.12.1.4** `Budget(cost=math.inf)` MUST denote an unlimited budget and MUST survive
`model_dump_json` and `model_validate_json`, the infinity written as `"Infinity"`.

**3.12.1.5** `Usage.duration` MUST be the sum of the durations of the turns counted, concurrent
turns each counting. `Usage.cost` MUST be in US dollars. `Usage.output_tokens` MUST be the tokens
agents wrote.

**3.12.1.6** hmz MUST require a budget for the top call of every epic except of the `chat` flow,
given as specified in [CLI]. A top call of `chat` given none MUST run under `Budget(cost=math.inf)`.

#### 3.12.2. Effective budget

**3.12.2.1** Cost and output tokens spent anywhere under a flow call MUST count against that flow
call and every flow call above it.

**3.12.2.2** `duration` MUST be a deadline per flow call: a call's deadline MUST be the earliest of
its own start plus its own `duration` and the deadline of every call above it.

**3.12.2.3** `ctx.budget` MUST report, for each limit, the least over the chain of calls of what the
call in the chain allows minus what was spent under that call plus what was spent under this call;
`duration` as the time from this call's start to its deadline; and each limit as not graceful where
any budget in the chain that sets that limit is not graceful for it, `graceful` being a `bool` where
the three limits agree and a `Graceful` otherwise.

**3.12.2.4** A turn MUST be held to the least remaining amount of each limit over every budget above
it and its own, each limit graceful as the budget that leaves that amount says. Where two budgets
leave the same amount of a limit, one for which the limit is not graceful MUST prevail. A turn's own
budget MUST apply to that turn alone.

#### 3.12.3. Enforcement

**3.12.3.1** A turn requested while a limit over it is spent MUST raise, before anything is sent,
`DurationExceeded`, `CostExceeded` or `OutputTokensExceeded` for the spent limit.

**3.12.3.2** A graceful limit reached during a turn MUST let the turn complete and return. The next
turn under that budget MUST raise.

**3.12.3.3** A limit that is not graceful reached during a turn MUST stop the harness, and `run`
MUST raise the subclass for the limit.

**3.12.3.4** When a flow call's deadline passes, hmz MUST cancel the call, after its turns under way
finish where its budget's duration is graceful and at once otherwise, and the call MUST raise
`DurationExceeded`. A cancellation from anywhere else MUST remain `asyncio.CancelledError`.

**3.12.3.5** A budget once spent MUST remain spent: every later turn under it MUST raise again.

**3.12.3.6** hmz MUST price spending with its price table (Section 7.4 of [FILES]). A model absent
from the price table MUST cost 0.

### 3.13. Calling another flow

#### 3.13.1. `load`

```python
def load(ref: str) -> Flow: ...
```

**3.13.1.1** `load(ref)` MUST return the flow object `ref` names, resolved relative to the module
that calls `load` (Section 3.13.3).

**3.13.1.2** Within one epic, one ref from one module MUST resolve to the same flow each time.

**3.13.1.3** `load` of a `git+` ref MUST return without fetching. The repository MUST be fetched
when a member of the flow object is first read or the flow is first called.

**3.13.1.4** `load` MUST raise:

1. `FlowRefError` where `ref` is not of the grammar of Section 3.13.2, or is a `:<name>` ref with no
   flow asking.
2. `FlowNotFound` where `ref` names no flow, or a `git+` repository cannot be fetched or holds no
   flow where `ref` says.
3. `FlowLoadConflict` where importing the flow's module would replace a module that a flow of an
   epic running in this process uses.
4. `FlowDefinitionError` where the named flow is written wrong, or importing its module raises.

#### 3.13.2. Ref grammar

**3.13.2.1** A ref MUST be read after removing surrounding whitespace, by the following grammar, in
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

**3.13.2.2** A ref that contains `#` or starts with `git+` MUST be read as a `vcs-ref`, and MUST
raise `FlowRefError` where it does not start with `git+`.

**3.13.2.3** Outside a `vcs-ref`, the text after the last `:` MUST be read as a flow name only where
it contains no `/`; otherwise the whole ref MUST be read as `flow-name` or `path`.

**3.13.2.4** A ref MUST be a `path-ref` exactly where it starts with `.`, `/` or `~`. Every other
ref that is not a `vcs-ref` or `relative` MUST be a `name-ref`. A `name-ref` whose `flow-name` has a
part too many, an empty part, or a part starting with `.` MUST raise `FlowRefError`. Under `@local/`
and `@user/`, a `flow-name` MUST have exactly one `PART`.

**3.13.2.5** In a `vcs-ref`, `url` MUST have the scheme `https`, `http`, `ssh`, `file` or `git`, and
MUST have a host unless its scheme is `file`. `@rev` MUST be the text after the last `@` of the
URL's path. The URL's query and fragment MUST be dropped. A URL whose path names no repository MUST
raise `FlowRefError`.

**3.13.2.6** In a `vcs-ref` without `#`, a final `:NAME` MUST be read as a flow name where the text
before it holds a path after `://`, and as a port otherwise.

**3.13.2.7** A `subdir` with a part starting with `.` MUST raise `FlowRefError`.

#### 3.13.3. Ref resolution

**3.13.3.1** `:NAME` MUST name the flow `NAME` of the module whose code calls `load`.

**3.13.3.2** A `name-ref` without `@` and with one `PART` MUST be resolved, for a flow asking, in
the directory of flows the asking flow is in, and, for an asking flow installed from a flowverse,
among the flows installed from that flowverse; and otherwise in the flow sources in lookup order
(Section 3.14.2).

**3.13.3.3** A `name-ref` without `@` and with two `PART`s (`<user>/<flow>`) MUST be resolved, for
an asking flow installed from a flowverse, among the flows installed from that flowverse; and
otherwise in the `official` flowverse only.

**3.13.3.4** A `name-ref` with `@<verse>/` MUST be resolved in flowverse `<verse>` only.

**3.13.3.5** A `path-ref` MUST be resolved, after expanding `~`, to the first file that exists of
`<path>/__init__.py`, `<path>`, `<path>.py`.

**3.13.3.6** A `vcs-ref` MUST be resolved to the module at `<subdir>/__init__.py` of the repository
checked out at `rev`, or at the repository root's `__init__.py` without `#`. An absent `rev` MUST
mean the repository's default branch. Each epic MUST fetch a given URL and `rev` at most once.

**3.13.3.7** Within the resolved module, a ref with `:NAME` MUST name the flow called `NAME`, and
MUST raise `FlowNotFound` where none is. A ref without `:NAME` MUST name the flow whose name is the
module's directory name or file stem; where there is none, the module's only flow that is not
hidden; and otherwise MUST raise `FlowNotFound`.

**3.13.3.8** A module's flows MUST be exactly the flow objects defined in files inside its
directory. A flow imported into the module from elsewhere MUST NOT be one of its flows.

**3.13.3.9** Files beside a flow's `__init__.py` MUST be importable from the flow by their plain
module names.

**3.13.3.10** A module whose files changed MUST be imported afresh by the next epic in which no
running epic shares it. An epic MUST import a module at most once.

**3.13.3.11** Two flow directories of one directory name MUST NOT both be loaded by one running
epic; the second MUST raise `FlowLoadConflict`.

#### 3.13.4. Calling a `Flow`

**3.13.4.1** `await flow_object(task, agents=..., envs=..., params=..., budget=...)` MUST run the
flow as a nested call of the flow call whose code awaits it, and MUST return what the flow function
returns.

**3.13.4.2** `agents` and `envs` MUST be mappings keyed by the callee's role names. `params` MUST be
read as Section 3.4.4.4 specifies. `budget` MUST be `None` or exactly a `Budget`, and MUST raise
`TypeError` otherwise. A given `budget` MUST apply in addition to what remains of the caller's.

**3.13.4.3** An exception the callee raises MUST reach the caller with the class and message it was
raised with, without wrapping.

**3.13.4.4** A flow object awaited outside every epic MUST raise `FlowRuntimeError`.

**3.13.4.5** A nested call made after its caller, any call above it, or the epic has ended MUST
raise `FlowCancelled`.

**3.13.4.6** A nested call that would make flow calls nest more than 64 deep MUST raise
`FlowDepthExceeded`.

**3.13.4.7** hmz MUST check what a caller passes before the callee starts. A refusal MUST mean that
nothing of the callee ran and nothing was spent. hmz MUST raise:

1. `MissingRole` where a required agent or environment role that is not runtime-filled is not given.
2. `CapabilityMissing` where an agent or environment given lacks a mixin its role declares.
3. `PermissionTooNarrow` where an agent given holds a permission that does not cover its role's
   `_permission`.
4. `HarnessMismatch` where a role typed as a harness protocol is given an agent of another harness.
5. `CapabilityMissing` where a role typed `Outworlder` is given an agent that is not an outworlder.
6. `ResourceUnmet` where an environment given does not meet its role's declared resources.
7. `RequirementError` where a value given is not an agent or environment handed out in this epic, or
   where a role is given that the callee does not declare.

**3.13.4.8** A callee MUST be given exactly its declaration: each agent re-granted the callee role's
mixins, `_permission`, `_skills`, `_tools` and `_clis`, and each environment the callee role's
mixins.

**3.13.4.9** A callee's hooks and sessions MUST be its own. A session the caller opened MUST NOT be
usable by the callee.

#### 3.13.5. Concurrency and cancellation

**3.13.5.1** A flow function MUST be able to use `asyncio.gather`, `asyncio.TaskGroup`,
`asyncio.timeout` and `except*` as in any coroutine. A callee's exception MUST reach `except*` with
its own class.

**3.13.5.2** Cancelling a task awaiting a turn MUST interrupt that turn's harness.

**3.13.5.3** When an epic is stopped, hmz MUST cancel the flow at its current `await`, MUST close
every session, and MUST remove every temporary copy and scratch directory except as Section 3.5.4.6
specifies. How an epic is stopped is specified in [CLI] and Section 3 of [CORE].

### 3.14. Flow sources

#### 3.14.1. Flow shapes

**3.14.1.1** A flow module MUST be either a directory holding `__init__.py`, or a single `.py` file.
Where both exist under one name, the directory MUST be used.

**3.14.1.2** A name starting with `_`, and a directory without `__init__.py`, MUST NOT be a flow
module.

#### 3.14.2. Sources and lookup order

**3.14.2.1** hmz MUST offer the following flow sources:

| Source | Holds |
| --- | --- |
| `local` | `.hmz/flows/` under the current directory |
| `user` | `~/.hmz/flows/` |
| `official` | the flows shipped in the `hmz` package, then the flows installed from the official index |
| any other flowverse | the flows installed from its index |

The directories holding installed flows are specified in Section 4.8 of [FILES].

**3.14.2.2** A bare flow name MUST be looked up in `local`, then `user`, then `official`, then every
other flowverse in alphabetical order, and the first match MUST be used.

**3.14.2.3** hmz MUST find only flows that are shipped, installed, or in `local` or `user`. A flow
that an index lists and that is not installed MUST NOT be found, and naming it MUST raise
`FlowNotFound`.

#### 3.14.3. Flows in the package

**3.14.3.1** hmz MUST ship the following flows, each with an environment role `workspace: LocalEnv`:

| Flow | Agent roles | Role needs | Resumable |
| --- | --- | --- | :-: |
| `chat` | `assistant`, `human: Outworlder` | none | ✓ |
| `ralph_loop` | `agent` | none | |
| `stateful_ralph` | `agent` | none | ✓ |
| `continue_loop` | `agent` | none | |
| `goal` | `worker` | `GoalCommandAgentMixin` | |
| `flame_chase` | `first_chaser`, `second_chaser` | none | ✓ |
| `rlar` | `actor`, `reviewer` | none | ✓ |

**3.14.3.2** The agent roles of `chat` MUST each be granted every mixin its harness serves, whatever
the role declares. Every other flow MUST be granted exactly what its roles declare. The behaviour of
`chat` is specified in Section 8 of [CORE].

**3.14.3.3** Each flow of Section 3.14.3.1 other than `chat` MUST run until its budget is spent,
`rlar` also until its reviewer says the work is done, and MUST end the epic with the failure of any
turn that fails.

#### 3.14.4. Flowverses

**3.14.4.1** A flowverse index MUST be a git repository of manifests. A flow listed bare MUST have
its manifests at `flows/<flow>/<version>/flow.yaml`; a flow listed under a GitHub user or
organisation `<user>` MUST have them at `flows/<user>/<flow>/<version>/flow.yaml`, `<user>` matching
`[a-z0-9][a-z0-9-]*`. In the `official` index, the flows of `humanfia` MUST be listed bare.

**3.14.4.2** A manifest MUST be a YAML mapping with the keys below. hmz MUST ignore other keys.

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

**3.14.4.3** A manifest that cannot be read or breaks a rule of Section 3.14.4.2 MUST be skipped and
listed with the reason, and MUST NOT raise.

**3.14.4.4** Installing a flow MUST install the release named, or where none is named the newest
release that is not a prerelease, or the newest prerelease where every release is one, together with
every dependency at a release within its range. Installing MUST be refused with `ValueError` where
no such set of releases exists, where dependencies form a cycle, or where the install would put
another installed flow's dependency out of its range.

**3.14.4.5** Installing a flow MUST copy the flow's directory from the repository at `commit`, and
MUST NOT execute any of it.

**3.14.4.6** Uninstalling a flow MUST be refused with `ValueError` where another flow installed from
the same flowverse lists it among its `dependencies`.

**3.14.4.7** The `official`, `local` and `user` flowverses MUST NOT be removable. How flowverses are
added, fetched and removed by a user is specified in [CLI] and Section 4.

### 3.15. Exceptions

#### 3.15.1. Hierarchy

**3.15.1.1** Every exception class of `hmz.flows` MUST derive from `FlowException`, with exactly the
bases given in Section 3.15.2 to Section 3.15.4, forming this tree:

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

**3.15.1.2** Every exception class of `hmz.flows` MUST be constructed with its message as its only
argument, and MUST pickle and copy as an instance of its own class.

**3.15.1.3** An exception raised by a flow's own code that is not of `hmz.flows` MUST NOT be
converted into a `FlowException`.

**3.15.1.4** `FlowException` MUST be raised by hmz only through one of its subclasses.

#### 3.15.2. Runtime exceptions

**3.15.2.1** `FlowRuntimeError(FlowException)` MUST be raised where a flow object is awaited outside
every epic (Section 3.13.4.4), and is the base of every exception hmz raises for what it refused or
what ran out.

**3.15.2.2** `FlowNotFound(FlowRuntimeError)` MUST be raised where a ref names no flow (Section
3.13.1.4, Section 3.13.3.7, Section 3.14.2.3).

**3.15.2.3** `FlowRefError(FlowRuntimeError, ValueError)` MUST be raised where a ref is not of the
grammar of Section 3.13.2, or is relative with no flow asking.

**3.15.2.4** `FlowDefinitionError(FlowRuntimeError)` MUST be raised where a flow is written wrong
(Section 3.4.1.7, Section 3.4.1.9, Section 3.4.1.10), where importing a flow's module raises, and
where a skill a role names cannot be found (Section 3.6.7.2).

**3.15.2.5** `FlowLoadConflict(FlowRuntimeError)` MUST be raised where loading a flow would replace
a module that a running epic uses (Section 3.13.1.4, Section 3.13.3.11).

**3.15.2.6** `RequirementError(FlowRuntimeError)` MUST be raised, as itself or a subclass, where
what a flow call is given does not meet its declaration, before anything of the callee runs (Section
3.13.4.7).

**3.15.2.7** `MissingRole(RequirementError)` MUST be raised where a required role is not given.

**3.15.2.8** `CapabilityMissing(RequirementError)` MUST be raised where an agent or environment
given lacks a declared mixin, including a mixin whose program the env machine lacks (Section
3.11.8.5); where a `LocalEnv` role is given an environment on another machine; and where an
outworlder is given for a role it cannot fill, or an agent for an `Outworlder` role.

**3.15.2.9** `PermissionTooNarrow(RequirementError)` MUST be raised where an agent given holds a
permission that does not cover its role's.

**3.15.2.10** `ResourceUnmet(RequirementError)` MUST be raised where an environment given cannot
provide the resources its role declares.

**3.15.2.11** `HarnessMismatch(RequirementError)` MUST be raised where a role typed as a harness
protocol is given an agent of another harness.

**3.15.2.12** `CapabilityNotGranted(FlowRuntimeError)` MUST be raised where a flow uses an operation
outside the grant of the handed object (Section 3.3.1.4), where `derive` would widen a grant, and
where `on_outworlder_run` is called on an outworlder not made with `Outworlder.new()`.

**3.15.2.13** `ParamsError(FlowRuntimeError, ValueError)` MUST be raised where params do not
validate against the flow's params model (Section 3.4.4).

**3.15.2.14** `FlowDepthExceeded(FlowRuntimeError, RecursionError)` MUST be raised where a nested
call would nest more than 64 deep.

**3.15.2.15** `BudgetExceeded(FlowRuntimeError)` MUST be raised only through one of its subclasses,
where a budget of the flow call or turn, or of a flow call above it, is spent (Section 3.12.3).

**3.15.2.16** `DurationExceeded(BudgetExceeded, TimeoutError)` MUST be raised where `duration` is
spent. `CostExceeded(BudgetExceeded)` MUST be raised where `cost` is spent.
`OutputTokensExceeded(BudgetExceeded)` MUST be raised where `output_tokens` are spent.

**3.15.2.17** `FlowCancelled(FlowRuntimeError)` MUST be raised where an operation of a flow call is
attempted after its caller, a call above it, or the epic has ended.

**3.15.2.18** `StateNotSerializable(FlowRuntimeError, TypeError)` MUST be raised where a flow state
write is refused (Section 3.5.2.1, Section 3.5.3.2).

**3.15.2.19** `OutworlderAway(FlowRuntimeError)` MUST be raised where an away outworlder is asked
for an `output_schema` that has a field without a default.

#### 3.15.3. Harness exceptions

**3.15.3.1** `HarnessError(FlowException)` MUST be raised, as one of its subclasses, where a harness
could not take a turn or do what it was asked.

**3.15.3.2** `HarnessNotInstalled(HarnessError)` MUST be raised where the harness, or the SDK it is
driven through, is not installed on the harness machine, including where the command that starts it
exits with status 127.

**3.15.3.3** `HarnessContended(HarnessError)` MUST be raised where two turns reached one local store
of the harness at once and this turn lost.

**3.15.3.4** `HarnessThrottled(HarnessError)` MUST be raised where the provider refused for too many
requests or a spent quota.

**3.15.3.5** `HarnessRefused(HarnessError)` MUST be raised where the provider refused the
credential: expired, revoked, or not signed in.

**3.15.3.6** `ModelUnavailable(HarnessError)` MUST be raised where the model is not served to the
account, has been retired, or does not exist.

**3.15.3.7** `HarnessMissing(HarnessError)` MUST be raised where the harness would not start for a
reason other than not being installed.

**3.15.3.8** `HarnessSandboxed(HarnessError)` MUST be raised where a session cannot be held to its
permission by the harness or the machine (Section 3.7.2.5), including where the harness cannot set
up its own sandbox on the machine.

**3.15.3.9** `HarnessKilled(HarnessError)` MUST be raised where the harness died during a turn, by a
signal or an out-of-memory kill, rather than answering.

**3.15.3.10** `HarnessDropped(HarnessError)` MUST be raised where the connection to the harness or
to its provider broke during a turn, after the retry of Section 3.8.6.1 where it applies.

**3.15.3.11** `HarnessUnrecoverable(HarnessError)` MUST be raised where a turn failed in a way no
retry could change and no other subclass of `HarnessError` names, including where the harness cannot
be configured as the session requires (Section 3.6.4.6).

**3.15.3.12** `OutputSchemaError(HarnessError, ValueError)` MUST be raised where the agent's answer
cannot be read as the `output_schema` asked for (Section 3.8.2.5).

**3.15.3.13** `SessionError(HarnessError)` MUST be raised where a session cannot take a turn or is
used in a way it cannot be: closed, another agent's, busy, steered with no turn under way,
interrupted, a fork whose parent moved on, a prompt a hook refused, and the conditions of Section
3.5.3.6, Section 3.8.2.7 and Section 3.8.5.3.

**3.15.3.14** `UnsupportedOperation(HarnessError)` MUST be raised where the harness cannot do what
was asked at all: the conditions of Section 3.5.3.5, Section 3.6.6.5, Section 3.6.6.11, Section
3.8.2.6, Section 3.8.2.7, Section 3.8.2.9, Section 3.8.3.2, Section 3.8.5.4 and Section 3.10.1.4.

**3.15.3.15** hmz MUST classify each failed turn into exactly one subclass of `HarnessError` by the
conditions of Section 3.15.3.2 to Section 3.15.3.14.

#### 3.15.4. Environment exceptions

**3.15.4.1** `EnvError(FlowException)` MUST be raised, as itself or one of its subclasses, where an
environment could not do what it was asked.

**3.15.4.2** `EnvUnavailable(EnvError)` MUST be raised where the env machine is gone or the workdir
does not exist.

**3.15.4.3** `EnvConnectionError(EnvError, ConnectionError)` MUST be raised where the connection to
an env machine other than this machine could not be made, or broke.

**3.15.4.4** `EnvCommandTimeout(EnvError, TimeoutError)` MUST be raised where `exec` ran past its
`timeout` (Section 3.11.5.2).

**3.15.4.5** `EnvFileNotFound(EnvError, FileNotFoundError)` MUST be raised where `read` names a
missing file.

**3.15.4.6** `EnvPermissionDenied(EnvError, PermissionError)` MUST be raised where the environment
refused a read, a write or a command for want of permission.

**3.15.4.7** `WorktreeError(EnvError)` MUST be raised where `derive_worktree` fails (Section
3.11.6.2).

**3.15.4.8** `TempCloneBusy(EnvError)` MUST be raised where `derive_temp_clone` asks for an id
another environment holds.

**3.15.4.9** `ScratchError(EnvError)` MUST be raised where a scratch directory cannot be made or
removed.

**3.15.4.10** `RewindError(EnvError)` MUST be raised where `snapshot`, `rewind` or `snapshots` fails
(Section 3.11.7.7).

## 4. Software Development Kit (`hmz.sdk`)

### 4.1. Scope

Section 4 governs the Python module `hmz.sdk`: every name it offers, the signature of every public
member of each, what each member does as observed by its caller, and what each raises. The module is
the supported way for a program that is not **hmz** to drive **hmz** on **this machine**: one
**workspace** straight in the calling process (`Hmz`), and the **epics** held by the **daemon** for
every **frontend** (`Daemons`, `Daemon`, `Link`).

Out of scope:

- The flow API a **flow author** writes against, and the in-memory drivers of `fakes`: Section 3.
- The wire protocol between a frontend and the daemon: Section 4 of [DAEMON].
- The HTTP API served by `hmz web`: Section 4 of [WEB].
- The settings files and every other file on disk: Section 3 of [FILES], Section 4 of [FILES],
  Section 6 of [FILES], Section 7 of [FILES].
- The `-a`, `-e`, `-f` and `-p` spellings and the `hmz exec` command line: [CLI].
- What an **agent**, **account**, **runtime**, **placement** and backup target are and how they
  behave: Section 4 of [CORE], Section 5 of [CORE], Section 7 of [CORE], Section 6 of [CORE],
  Section 11 of [CORE].

### 4.2. Terminology

**4.2.1** Every term of Section 2 of [CORE] MUST carry the meaning given there.

**4.2.2** **Offered name**: a name listed in `hmz.sdk.__all__`.

**4.2.3** **Returned type**: a type that is not an offered name and that a member of an offered name
returns, accepts, or exposes as an attribute.

**4.2.4** An agent spec MUST be as Section 4.2.2 of [CORE] defines it: the text an `-a` option takes
after `<role>=`.

**4.2.5** **Environment spec**: the text an `-e` option takes after `<role>=`, as [CLI] defines it.

**4.2.6** **Flow name**: the text an `-f` option takes, as [CLI] defines it: a name a flow is
offered under, a ref, or a path.

**4.2.7** A place MUST be as Section 4.2.3 of [CORE] defines it.

**4.2.8** The term host MUST carry the meaning Section 3.2.1 of [DAEMON] gives it.

**4.2.9** **Slot**: the text naming one of a workspace's hosts, as Section 4.2.6 of [DAEMON] defines
it: `""` for the workspace's own host, `chat:<hex>` for one chat's.

**4.2.10** **Epic directory**: the directory one epic is written into, as Section 6 of [FILES]
defines it. An epic is named by its epic directory's base name.

### 4.3. The module

```python
__all__ = ["Accounts", "Daemon", "Daemons", "Epics", "Fallbacks", "Flows", "Flowverses", "Hmz",
           "Host", "Link", "Refused", "Run", "Runtimes", "fakes"]
def __getattr__(name: str) -> object: ...
```

**4.3.1** `hmz.sdk.__all__` MUST be exactly the fourteen names listed above.

**4.3.2** Importing `hmz.sdk` MUST NOT import any other module of the `hmz` package.

**4.3.3** Accessing an offered name MUST import only the modules that name requires.

**4.3.4** `hmz.sdk.fakes` MUST be a module object, and every access of `hmz.sdk.fakes` MUST return
the identical object (`is`).

**4.3.5** `from hmz.sdk import fakes` MUST succeed; `import hmz.sdk.fakes` MUST raise
`ModuleNotFoundError`.

**4.3.6** Accessing a name of `hmz.sdk` that is not an offered name MUST raise `AttributeError` with
the message `module 'hmz.sdk' has no attribute '<name>'`.

**4.3.7** An offered name MUST keep its meaning, its signature and the behaviour Section 4 states
across releases until this document is changed.

**4.3.8** The fields and members of a returned type stated in Section 4.20 MUST hold as stated;
members of a returned type that Section 4 does not state are not part of this API.

### 4.4. `Hmz`

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
    daemons: Registry    # property; the type of Section 4.14, not hmz.sdk.Daemons
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

#### 4.4.1. Construction and properties

**4.4.1.1** `Hmz(workspace)` MUST read no file, start no process and import no flow.

**4.4.1.2** `Hmz.workspace` MUST be `Path(workspace)` as given, without expanding `~` and without
resolving links; where `workspace` is `None`, it MUST be the current directory at the moment the
property is read.

**4.4.1.3** `Hmz.home` MUST be the **home** directory as Section 4 of [FILES] locates it, and
reading it MUST NOT create it.

**4.4.1.4** `Hmz.settings` MUST read and write the settings of Section 3 of [FILES] for this
workspace and this machine; members of its type are not part of this API.

**4.4.1.5** `Hmz.flows`, `Hmz.accounts`, `Hmz.runtimes`, `Hmz.fallbacks`, `Hmz.epics`, `Hmz.backups`
and `Hmz.daemons` MUST each return the same object on every access of one `Hmz` instance.

**4.4.1.6** `Hmz.verses` MUST be the identical object `Hmz.flows.verses`.

**4.4.1.7** `Hmz.epics` MUST be the `Epics` of `Hmz.workspace`.

#### 4.4.2. Backends

**4.4.2.1** `Hmz.backends()` MUST return one entry per coding-agent CLI **hmz** drives, installed or
not, each having at least the attributes `name: str`, `aliases: tuple[str, ...]` and `efforts:
tuple[str, ...]`.

**4.4.2.2** `Hmz.installed()` MUST map the name of every backend whose program, and whatever its
optional extra brings, is present on this machine to the models it last reported it runs; a backend
never asked MUST map to `()`.

**4.4.2.3** `Hmz.installable()` MUST map the name of every backend whose program is present and
whose Python extra is absent to the models it will offer once the extra is added.

**4.4.2.4** `Hmz.adding(backend)` MUST return the text naming what is missing for that backend and
the command that adds it.

**4.4.2.5** `Hmz.serves(backend, role)` MUST return `False` where the backend is not the harness
`role` names or cannot provide what `role` declares it requires, and `True` otherwise; `role` `None`
MUST be answered for an agent that fills no declared role.

**4.4.2.6** `Hmz.ready_to_open(backend)` MUST return whether the backend is permitted to be chosen
as a fallback agent without the user choosing it: never for `litellm`, and for `dsh` only once its
local account in this workspace is configured.

#### 4.4.3. Reporting and settings carried to another daemon

**4.4.3.1** `Hmz.reports()` MUST start reporting **hmz**'s own failures where, and only where, the
user has answered yes to reporting or `HUMANIZE_SENTRY` is `on`, and MUST return whether failures
are being reported.

**4.4.3.2** `Hmz.reports()` MUST NOT ask the user anything.

**4.4.3.3** `Hmz.carried(pages)` MUST return, for each page named out of `general`, `fallback`,
`runtimes` and `backup`, the HTTP path and the JSON body that writes that page's settings of this
machine to another daemon's `hmz web`, as Section 4.13 of [WEB] defines those paths.

**4.4.3.4** `Hmz.carried(pages)` MUST NOT include any value that only a secret sets.

#### 4.4.4. Reading a command line

**4.4.4.1** `Hmz.read(argv)` MUST parse `argv` as the arguments of `hmz exec` after `exec`, as [CLI]
defines them, and return a `Line` (Section 4.20.1).

**4.4.4.2** `Hmz.read(argv)` MUST NOT import any flow.

**4.4.4.3** Where `argv` is not a valid `hmz exec` line, `Hmz.read(argv)` MUST write the usage and
the error to standard error and raise `SystemExit(2)`.

**4.4.4.4** Where `argv` asks for help, `Hmz.read(argv)` MUST write the help to standard output and
raise `SystemExit(0)`.

#### 4.4.5. Making an epic

**4.4.5.1** `Hmz.runner(flow, ...)` MUST load the flow `flow` names, make a driver for every role it
declares, check everything `hmz exec` checks before an epic starts, and return a `Runner` whose
members are not part of this API.

**4.4.5.2** Making a driver in `Hmz.runner` MUST NOT start any agent CLI and MUST NOT reach any
other machine.

**4.4.5.3** `Hmz.run(flow, task, ...)` MUST return a `Run` equal in effect to `Run(self.runner(flow,
...), task, outworlder=outworlder)` with every other argument passed through unchanged.

**4.4.5.4** `Hmz.run` MUST NOT start the epic.

**4.4.5.5** The parameter `flow` MUST be read as a flow name.

**4.4.5.6** The parameter `agents` MUST accept a mapping from role name to an agent spec or an
`AgentDriver`, or an iterable of `AgentSpec`.

**4.4.5.7** The parameter `envs` MUST accept a mapping from role name to an environment spec or an
`EnvDriver`, or an iterable of `EnvSpec`.

**4.4.5.8** The parameter `params` MUST accept a mapping, whose text values are read as `-p` reads
them, or an instance of the flow's `FlowParams`; `None` MUST mean the flow's defaults.

**4.4.5.9** The parameter `budget` MUST accept a `Budget` or a mapping validated as `Budget`
validates one; `None` MUST mean an unlimited cost for the built-in `chat` flow and MUST be refused
for every other flow.

**4.4.5.10** `profile_flow` and `profile_environment` MUST mean what `--profile-flow` and
`--profile-environment` mean in [CLI].

**4.4.5.11** `resume=False` MUST start the flow from the beginning; `resume=True` MUST pick up the
newest epic of that flow in this workspace that can be picked up; a path MUST pick up the epic in
that epic directory.

**4.4.5.12** `outworlder` MUST fill every `Outworlder` role of the flow; `None` MUST fill each as
always away.

**4.4.5.13** `backup` MUST name the backup targets the epic is backed up to; `None` MUST mean the
default targets of Section 3 of [FILES].

**4.4.5.14** `Hmz.run` and `Hmz.runner` MUST raise `Refused` for everything `hmz exec` refuses
before an epic starts, with the same message `hmz exec` prints after `hmz exec: error: `.

**4.4.5.15** `Hmz.run` and `Hmz.runner` MUST raise `Refused` with the message `<flow>: duplicate
agent role '<role>'` for an agent role given twice, and `<flow>: duplicate environment role
'<role>'` for an environment role given twice.

**4.4.5.16** `Hmz.run` and `Hmz.runner` MUST raise `Refused` with a message starting `the budget is
invalid: ` for a budget mapping `Budget` does not validate.

**4.4.5.17** `Hmz.run` and `Hmz.runner` MUST raise `Refused` with the message `<epic> has no saved
progress to resume from` for a `resume` path whose epic holds no journal entry.

**4.4.5.18** A `Line` read by `Hmz.read` and passed field by field to `Hmz.run` MUST make an epic
identical in effect to the one `Hmz.exec` makes of the same `argv`.

**4.4.5.19** Where each agent's harness runs MUST NOT be a parameter of `Hmz.run`: it MUST follow
from the runtime the work is placed on, as Section 6 of [CORE] states.

#### 4.4.6. Executing a command line

**4.4.6.1** `Hmz.exec(argv)` MUST do `Hmz.read(argv)`, then `Hmz.run(...)` with every field of the
`Line`, then `Run.run()`, and return what the flow returned.

**4.4.6.2** `Hmz.exec(argv)` MUST draw nothing, MUST install no signal handler, and MUST raise
`Refused`, `BudgetExceeded` and what the flow raises unchanged rather than exit.

#### 4.4.7. Hosts

**4.4.7.1** `Hmz.host(slot)` MUST return one `Host` per `Hmz` instance and slot, made on the first
call with that slot and returned unchanged on every later call.

**4.4.7.2** `Hmz.host(slot)` MUST raise `ValueError` for a slot that is neither `""` nor
`chat:<hex>`.

### 4.5. `Run`

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

#### 4.5.1. Properties

**4.5.1.1** Constructing a `Run` MUST NOT start the epic.

**4.5.1.2** `Run.flow` MUST be the flow as it was named; `Run.ref` MUST be its canonical ref.

**4.5.1.3** `Run.chats` MUST be `True` where, and only where, the flow is the built-in `chat` flow,
decided by where the flow is defined and not by its name.

**4.5.1.4** `Run.declaration` MUST be what the flow declares (Section 4.20.3).

**4.5.1.5** `Run.budget` MUST be the `Budget` the epic is held to; `Run.usage` MUST be what it has
spent so far, as Section 3 defines `Usage`.

**4.5.1.6** `Run.backup` MUST be the names of the backup targets the epic goes to.

**4.5.1.7** `Run.agents` MUST be the agent behind each **session** still open, oldest first.

**4.5.1.8** `Run.names` MUST map each agent role to the name of the agent filling it.

**4.5.1.9** `Run.epic` MUST be the epic directory once the epic has started writing it, and `None`
before.

**4.5.1.10** `Run.running` MUST be `True` from `start()` until the flow has returned or raised.

**4.5.1.11** After an epic started with `start()` has ended, `Run.raised` MUST be what the flow
raised (`asyncio.CancelledError` after `stop()`), or `None`, and `Run.result` MUST be what the flow
returned.

#### 4.5.2. Driving

**4.5.2.1** `Run.run()` MUST drive the flow to its end and return what it returned or raise what it
raised: on an event loop of its own in the calling thread, or, where the calling thread already runs
an event loop, on a new thread the call waits for.

**4.5.2.2** `Run.run()` MUST raise `Refused` before the flow is called where an environment cannot
be reached or cannot provide what its role declares.

**4.5.2.3** `Run.start()` MUST drive the flow on a new thread and return at once; a second `start()`
MUST raise `RuntimeError`.

**4.5.2.4** `Run.wait(timeout)` MUST block until the epic ends or `timeout` seconds pass, and return
whether it ended.

**4.5.2.5** `Run.stop()` MUST be callable from any thread, MUST interrupt the turn under way, MUST
make every flow call raise `asyncio.CancelledError` where it stands, and MUST return without waiting
for the flow to unwind.

**4.5.2.6** `Run.close()` MUST do what `stop()` does and then close every session and agent still
open without waiting.

#### 4.5.3. Observing

**4.5.3.1** `Run.watch(listener)` MUST call `listener` once for every event of every session of the
epic; the call MAY come from any thread.

**4.5.3.2** While at least one listener is registered with `watch`, agent CLIs MUST NOT write their
own progress to the calling process's standard output or standard error.

**4.5.3.3** `Run.opened(callback)` MUST call `callback(role, agent, session, placement)` on the
epic's event loop as each session opens and before its first turn; `placement` MUST be `None` where
the driver reports none.

**4.5.3.4** `Run.noticed(callback)` MUST call `callback(text)` with every notice **hmz** gives about
the epic before the flow is called, as Section 3 of [CORE] defines notices.

**4.5.3.5** `Run.unreadable()` MUST return, in words, every limit of the budget that nothing the
epic drives can enforce, or `""` where there is none.

**4.5.3.6** Where the budget has a finite `cost`, `Run.unreadable()` MUST first bring a missing or
stale price list up to date, waiting no longer than that fetch's own timeout and not at all once the
epic has been stopped.

### 4.6. `Refused`

```python
class Refused(ValueError): ...
```

**4.6.1** `Refused` MUST be raised for an epic, or a request to a host, refused before anything of
it ran.

**4.6.2** `str()` of a `Refused` MUST be the one sentence that says why, identical to what `hmz
exec` prints after `hmz exec: error: ` and to what a host answers every frontend.

**4.6.3** Where an underlying exception caused the refusal, it MUST be the `__cause__` of the
`Refused`.

### 4.7. `Flows`

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

**4.7.1** `Flows.all()` MUST return every flow on offer in the workspace, in offer order, as `Offer`
values (Section 4.20.3).

**4.7.2** `Flows.find(named)` MUST return the file a flow name resolves to, or `""` where nothing
resolves; a text starting with `.`, `/` or `~` MUST be read as a path, and any other text as a name,
never as a file of that name in the current directory.

**4.7.3** `Flows.about(named)` MUST return the flow's one-line description, or `""`.

**4.7.4** `Flows.declared(named)` MUST import the flow and return what it declares as it is now; a
`str` MUST be read as `-f` reads it, and an `os.PathLike` always as a path.

**4.7.5** `Flows.declared(named)` MUST raise the `FlowException` of Section 3 for a flow that cannot
be loaded.

**4.7.6** `Flows.resumes(named)` MUST import the flow and return whether an epic of it can be picked
up.

**4.7.7** `Flows.fork(named, into)` MUST copy the flow, every file it imports from its own directory
and its skills into `.hmz/flows/` of the workspace, or into `into`, MUST NOT copy an installed
flow's installation record, and MUST return the directory written.

**4.7.8** `Flows.fork` MUST raise `ValueError` where `named` is not a flow or is already a copy in
that place, and `OSError` where the copy fails.

**4.7.9** `Flows.running()` MUST return every flow call in progress in the calling process, oldest
first, as `LiveCall` values (Section 4.20.3).

### 4.8. `Flowverses`

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

**4.8.1** A `flow` argument of `install` and `uninstall` MUST be the name the flow is offered under:
`<flow>` or `<user>/<flow>` for one of `official`'s, `@<flowverse>/<flow>` or
`@<flowverse>/<user>/<flow>` for one of another flowverse's.

**4.8.2** `Flowverses.all()` MUST return every flowverse in offer order: `official`, then each added
one by name, then `local`, then `user`.

**4.8.3** `Flowverses.nearest()` MUST return every flowverse in the order a bare flow name is looked
up: `local`, `user`, `official`, then each added one.

**4.8.4** `Flowverses.find(name)` MUST return the flowverse of that name, or `None`.

**4.8.5** `Flowverses.add(url, name)` MUST clone the index at `url` (a URL, a path, or `owner/repo`
on GitHub) under `name`, or under the repository's name where `name` is `""`, and MUST install
nothing.

**4.8.6** `Flowverses.add` MUST raise `ValueError` for a name taken, reserved (`official`, `local`,
`user`) or not a valid directory name, and `OSError` where the clone fails.

**4.8.7** `Flowverses.fetch(name)` MUST fetch the index again, or for the first time, discarding
local changes to the clone, and MUST NOT change any installed flow.

**4.8.8** `Flowverses.fetch` MUST raise `ValueError` for an unknown name or for `local` or `user`,
and `OSError` where git fails.

**4.8.9** `Flowverses.remove(name)` MUST delete the index and every flow installed from it, and MUST
return whether the flowverse existed; it MUST raise `ValueError` for `official`, `local` and `user`.

**4.8.10** `Flowverses.holds(one)` MUST return what the flowverse offers to run: the built-in and
installed flows for `official`, the installed flows for an added flowverse, and the flows in the
directory for `local` and `user`; it MUST import every flow it returns and MUST NOT return a flow
the index only lists.

**4.8.11** `Flowverses.index(name)` MUST return what the index lists as last fetched, reading only
the index files; it MUST return an empty `Index` for `local`, `user`, an unfetched flowverse and an
unknown name.

**4.8.12** `Flowverses.install(flow, version)` MUST install that release and every flow it depends
on, MUST switch an installed flow of another version to that one, and MUST return what is now
installed of every flow the install touched, the asked-for flow last.

**4.8.13** `version=""` MUST select the newest release that is not a prerelease, else the newest
prerelease.

**4.8.14** `Flowverses.install` MUST raise `ValueError` for an unknown flowverse, flow or release,
an unfetched index, a dependency cycle, a version range no release satisfies, and an install that
breaks the range another installed flow requires; and `OSError` where fetching or copying fails.

**4.8.15** `Flowverses.uninstall(flow)` MUST remove an installed flow and return whether it was
installed; it MUST raise `ValueError` where another installed flow depends on it and `OSError` where
it cannot be removed.

**4.8.16** `Flowverses.installed()` MUST return every installed flow, by flowverse and then by name.

**4.8.17** `Flowverses.updates()` MUST return every installed flow whose index, as last fetched,
lists a newer release.

**4.8.18** `Flowverses.edited(one)` MUST return whether the clone holds changes a fetch would
discard, and `False` for a flowverse that is not a clone.

**4.8.19** `Flowverses.standing(one)` MUST return the commit the clone stands at, or `""`.

**4.8.20** `Flowverses.where(name)` MUST return the index's directory whether or not it has been
fetched.

**4.8.21** `Flowverses.plain(url)` MUST return `url` with any credentials removed.

**4.8.22** `Flowverses.whence(one, nowhere)` MUST return the flowverse's credential-free URL; for
`local`, the text `your own flows in .hmz/flows`; for `user`, the text `your own flows in
~/.hmz/flows`; and `nowhere` for a directory with no readable origin.

### 4.9. `Accounts`

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

**4.9.1** Every `cli` argument MUST accept any name or alias of a backend; an account `name` of `""`
MUST mean this machine's own sign-in of that CLI.

**4.9.2** `Accounts.GATEWAY` MUST be `"LiteLLM"`, the name the ways in through the local LiteLLM
gateway are grouped under.

**4.9.3** `Accounts.all(cli)` MUST return every account, or every account of one backend, by backend
and then by name.

**4.9.4** `Accounts.ways(cli)` MUST return every way the backend can be signed into, in offer order;
`Accounts.way(cli, name)` MUST return one of them, or `None`.

**4.9.5** `Accounts.wants(cli)` MUST return the command that installs the `litellm` extra where the
backend has ways in through the gateway that are not offered because the `litellm` extra is absent,
and `""` otherwise.

**4.9.6** `Accounts.find(cli, name)` MUST return the account, or `None`.

**4.9.7** `Accounts.where(cli, name)` MUST return the account's credentials directory, and MUST
raise `ValueError` for an unknown backend or an invalid name.

**4.9.8** `Accounts.write(...)` MUST write the account as given, replacing its `env` and `args` and
keeping its credentials; where `args` is empty and `way` names a way that adds arguments, those
arguments MUST be filled from `env`. It MUST raise `ValueError` for an invalid backend or name and
`OSError` where the write fails.

**4.9.9** `Accounts.make(cli, name, way, answers)` MUST write an account from a way's answers and
make its directory; it MUST raise `ValueError` for an invalid backend or name and `OSError` where
the write fails.

**4.9.10** `Accounts.sign_in(provider, way, answers)` MUST run the backend's own sign-in command
under the account's paths and return its exit status.

**4.9.11** `Accounts.asks(way, given)` MUST return the variables of the way still unanswered by
`given`.

**4.9.12** `Accounts.serves(one)` MUST return the other backends the account's credentials can run.

**4.9.13** `Accounts.copies(one, cli, name)` MUST write the same account for another backend, and
MUST raise `ValueError` where that backend cannot use it.

**4.9.14** `Accounts.remove(cli, name)` MUST delete the account and its credentials and return
whether it existed; it MUST raise `ValueError` for `name` `""`.

**4.9.15** `Accounts.env(said)` MUST parse `NAME=VALUE` lines into a mapping.

**4.9.16** `Accounts.environ(provider)` MUST return the environment a turn run as that account
receives, and `{}` for `None`.

**4.9.17** `Accounts.models(cli, provider)` MUST return what the backend last reported it runs as
that account, and `()` where it was never asked; `Accounts.asked` MUST return when that was, or
`""`.

**4.9.18** `Accounts.stale(cli, provider)` MUST return `True` where the backend was never asked or
was last asked more than one week ago.

**4.9.19** `Accounts.ask(cli, provider, seconds)` MUST start the backend to list its models, keep
the answer, and return it, or `()` where the backend does not answer within `seconds`.

### 4.10. `Runtimes`

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

**4.10.1** A `backend` argument MUST be one of `ssh`, `docker`, `swarm`, `apple-container` and
`slurm`; the fields of a runtime of each backend are those Section 7 of [CORE] defines.

**4.10.2** `Runtimes.kinds()` MUST return every backend an environment can be put on, as `-e` spells
it, `local` first.

**4.10.3** `Runtimes.all(backend)` MUST return every saved runtime, or every saved runtime of one
backend, by backend and then by name.

**4.10.4** `Runtimes.find(backend, name)` MUST return the runtime, or `None`.

**4.10.5** `Runtimes.saved(backend, name)` MUST return whether a runtime is written under that name,
whether or not it reads, and MUST raise `ValueError` for an unknown backend or a name no runtime can
have.

**4.10.6** `Runtimes.new(backend, name, **fields)` MUST build and validate a runtime without saving
it, and MUST raise `ValueError` for an unknown field or an invalid value; `new(**r.held())` MUST
equal `r` for every runtime `r`.

**4.10.7** `Runtimes.add(runtime)` MUST save a new runtime and MUST raise `ValueError` where the
name is taken; `Runtimes.write(runtime)` MUST save it, replacing any of that name. Both MUST raise
`OSError` where the write fails.

**4.10.8** `Runtimes.remove(backend, name)` MUST delete the runtime and return whether it existed.

**4.10.9** `Runtimes.hosts(config)` MUST return every `Host` entry of an ssh config, `~/.ssh/config`
by default, as `ssh -G` resolves it, and MUST raise `OSError` where `ssh` is absent or the config
cannot be read.

**4.10.10** `Runtimes.import_ssh(config, names, update=...)` MUST save one `ssh` runtime per `Host`
entry of the config, or per name in `names`, named after it, keeping each existing one unless
`update`; it MUST raise `ValueError` for a name the config does not hold.

**4.10.11** `Runtimes.resolve(runtime)` MUST return what `ssh -G` makes of an ssh runtime without
reaching it.

**4.10.12** `Runtimes.check(runtime, seconds)` MUST reach the runtime and report what it has: an ssh
host its home, CPUs, memory and GPUs, by the route an epic takes to it; a docker daemon its `docker
info`, compared with what the runtime is written as handing out; a docker runtime that names a
running container only whether that container is running; a swarm's manager its `docker info`,
whether it manages an active swarm, and the nodes that accept a task; Apple's container system
whether it runs, compared with the Mac; and a Slurm cluster its `sinfo`, the nodes of its partition
that accept a job.

**4.10.13** `Runtimes.check` MUST NOT wait longer than `seconds`, MUST NOT prompt for a password,
and MUST NOT raise: a runtime that does not answer MUST be reported as unreached, with why.

### 4.11. `Fallbacks`

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

**4.11.1** `Fallbacks.default` MUST be `"exponential-jitter"`.

**4.11.2** `Fallbacks.policies()` MUST return the wait policies `none`, `constant`, `linear`,
`exponential`, `exponential-jitter` and `fibonacci`; `Fallbacks.named(policy)` MUST return one of
them, or `None`.

**4.11.3** `Fallbacks.all()` MUST return every fallback step written, in the order written.

**4.11.4** `Fallbacks.reads(said)` MUST return the canonical spelling of a place, or `""` where
`said` is not one; `Fallbacks.spec(backend, model, provider)` MUST return the place
`<backend>[@<provider>]/<model>`.

**4.11.5** `Fallbacks.tried(said)` MUST return the step written against a place, or an empty `Falls`
where there is none.

**4.11.6** `Fallbacks.chain(said)` MUST return `[said, *to]` where a step is written against `said`,
and `[said]` otherwise; chains MUST NOT be joined.

**4.11.7** `Fallbacks.points(said, to)` MUST set the places `said` falls back to, in order, and MUST
raise `ValueError` for a text that is not a place, for `said` itself, and for a place named twice.

**4.11.8** `Fallbacks.retrying(said, tries, policy, timeout)` MUST set the extra tries, the wait
policy and the total limit in seconds (`0` meaning none), and MUST raise `ValueError` for an invalid
value.

**4.11.9** `Fallbacks.clear(said)` MUST remove the step and return whether there was one.

### 4.12. `Epics`

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

**4.12.1** `Epics.under()` MUST return the directory this workspace's epics are written in, as
Section 6 of [FILES] locates it.

**4.12.2** `Epics.all()` MUST return every epic of the workspace, oldest first; `Epics.every()` MUST
return every epic of every workspace on this machine, oldest first.

**4.12.3** `Epics.read(epic)` MUST return the epic as a `Ran` (Section 4.20.5), or `None` for a
directory holding no epic.

**4.12.4** `Epics.tree(epic)` MUST return every flow call of the epic as a tree of `Called`.

**4.12.5** `Epics.sessions(epic)` MUST return every session of the epic, across every record of it;
`Epics.opened(epic)` MUST map each agent's name to the ids of the sessions it opened.

**4.12.6** `Epics.resumed(flow)` MUST return the epic that `--resume` of that flow would pick up, or
`None`.

**4.12.7** `Epics.picks_up(epic)` MUST return `True` where, and only where, the epic holds a journal
entry, is not going, and `Epics.foreign(epic)` is `""`.

**4.12.8** `Epics.foreign(epic)` MUST return why an imported epic cannot be picked up on this
machine, or `""`.

**4.12.9** `Epics.going(epic)` MUST return whether the epic is still going, in any process.

**4.12.10** `Epics.ending(ran)` MUST return how the epic ended, as Section 3 of [CORE] names
endings, and `running` while it is going.

**4.12.11** `Epics.state(epic, flow)` MUST return the `ctx.state` a resumable flow kept: the epic's
own flow's, or, where `flow` names a canonical ref, that flow's.

**4.12.12** `Epics.traced(epic, ...)` MUST gather the epic's own sessions into a trace as Section 10
of [CORE] defines it, written to `output`, or to the epic's `traces/` directory under a name of the
moment, and MUST return the path written and the trace's summary.

**4.12.13** `start` and `end` of `Epics.traced` and `Epics.trace` MUST accept any wording of a
moment that `dateparser` reads.

**4.12.14** `Epics.trace(...)` MUST gather a trace of any sessions: `sessions=None` every session of
the workspace, an empty iterable none; `kept=None` MUST read every place **hmz** keeps sessions.

**4.12.15** `Epics.transcripts(epic)` MUST return what each session of the epic said and did, read
from its logs, and MUST write nothing.

**4.12.16** `Epics.timeline(epic)` MUST return the epic as an Exomyth timeline, as Section 10 of
[CORE] defines it, and MUST write nothing.

**4.12.17** `Epics.bundled(epic, output=..., transcript=...)` MUST write one `.hmzepic` archive of
the whole epic, as Section 6 of [FILES] defines it, with credentials struck out, to `output` or into
the directory `output` names, and MUST return its path and its manifest.

**4.12.18** `Epics.imported(archive)` MUST read a `.hmzepic` back as an epic of the workspace it ran
in, wherever that is, and return its epic directory.

**4.12.19** `Epics.imported` MUST raise `ValueError` for a file that is not a `.hmzepic`, for an
archive holding an unsafe member, and for an epic already present.

### 4.13. `Backups`

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

**4.13.1** `Backups.targets()` MUST return every backup target in the settings, in the order
written; `Backups.defaults()` MUST return the names of the default targets.

**4.13.2** `Backups.push(ran, names)` MUST back the epic up to the targets named, else to those it
was started with, else to the defaults, MUST return the names it queued at once without waiting for
any push, and MUST raise `ValueError` for a name no target has.

**4.13.3** `Backups.state(ran)` MUST map each target the epic was ever backed up to onto `at`, `ok`,
`error` and `why` of its last backup, read from the epic as it is now.

**4.13.4** `Backups.where(ran)` MUST return `<machine>/<workspace>/<epic>`, the place of the epic in
a target's repository.

**4.13.5** `Backups.wait(seconds)` MUST wait for every backup the calling process queued, at most
`seconds`, and return whether none is left.

**4.13.6** `Backups.listed(name)` MUST fetch the target afresh and return every epic it holds, of
every machine and workspace, oldest first; it MUST raise `ValueError` for an unknown target and
`OSError` where git fails or exceeds its timeout.

**4.13.7** `Backups.pulled(name, key)` MUST download the epic at `key` into this machine's epics as
an import does and return its epic directory; it MUST raise `ValueError` for an unknown target, a
key naming no epic, an epic not laid out as one, and an epic already present, and `OSError` where
git fails.

### 4.14. The daemon registry

`Hmz.daemons` returns the registry of the daemons of other machines; its class is a returned type,
distinct from `hmz.sdk.Daemons` (Section 4.16).

```python
class Registry:  # the class's own name is Daemons
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

**4.14.1** The registry MUST read and write the `daemons` list of Section 3 of [FILES]; `local` MUST
name this machine's own daemon, which is never written there.

**4.14.2** `Registry.all()` MUST return every daemon written, ssh or EasyTier, in order, leaving out
an entry that cannot be one; `Registry.find(name)` MUST return one of them, or `None`.

**4.14.3** `Registry.write(name, fields, replace=...)` MUST write the daemon, or overwrite the one
of that name where `replace`, and return it as written; it MUST raise `ValueError` where it cannot
be one, `FileExistsError` where the name is taken and `replace` is false, and `OSError` where the
write fails. Where `replace` and `fields` are of an EasyTier daemon without `secret`, it MUST keep
the secret written; a secret shorter than 16 bytes MUST raise `ValueError`.

**4.14.4** `Registry.remove(name)` MUST remove the daemon; it MUST raise `ValueError` for `local`,
`LookupError` for an unknown name, and `OSError` where the write fails.

**4.14.5** `Registry.offered()` MUST map each `Host` entry of the ssh config not yet written to the
daemon it would be; `Registry.imported(wanted)` MUST write a daemon for each `Host` entry named,
skipping those already written, and return their names. `Registry.imported` MUST raise `ValueError`
for an empty list or a host that cannot be one, `LookupError` for a host the config does not name,
and `OSError` where the config cannot be read or the file written.

**4.14.6** `Registry.remotes(version)` MUST return a `Remotes` that reaches each daemon as it is
first asked for, installing `hmz` at `version` over ssh, or at the calling process's version where
`version` is `None`, as Section 3 of [DAEMON] defines reaching.

**4.14.7** `Remotes.state(name)` MUST return `{state, detail, version}`, `state` being one of
`idle`, `connecting`, `installing`, `up` and `failed`; `local` MUST be `up` at the calling process's
version.

**4.14.8** `Remotes.connect(name)` MUST start reaching the daemon, or reach it again at once where
it failed, and return its state; it MUST raise `LookupError` for an unknown name and `Unreached`
where the `Remotes` is closing.

**4.14.9** `Remotes.reached(name)` MUST return the port of this machine's loopback that leads to the
daemon's `hmz web`, over ssh or EasyTier, and that server's key, reaching it first where needed;
`Remotes.asks(name)` MUST return that port and the headers a request carries to be admitted. Both
MUST raise `Unreached` where it is not up and `LookupError` for an unknown name.

**4.14.10** `Remotes.asked(name, path, body, into=...)` MUST send the request `path` (a path of
Section 4 of [WEB], with its query) to the daemon's `hmz web`, as a `POST` of `body` where `body` is
not `None` and a `GET` otherwise, and MUST return its JSON answer, or, where `into` is given, the
number of bytes written there.

**4.14.11** `Remotes.followed(name, path, going)` MUST yield the name and JSON data of each
server-sent event the daemon's `hmz web` sends at `path`, until the stream ends or `going` is set.

**4.14.12** `Remotes.asked` and `Remotes.followed` MUST raise `Unreached` where the daemon is not up
or its `hmz web` refused, with `Unreached.status` the HTTP status it refused with, or `503` where it
was not reached, and `Unreached.seen` its state where it is not up.

**4.14.13** `Remotes.close()` MUST stop reaching every daemon and stop every process started for
one.

### 4.15. `Host`

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

**4.15.1** A `Host` MUST behave, toward every frontend attached to it, exactly as Section 4 of
[DAEMON] states a host behaves: the same messages, in the same order, and the same answers and
refusals to the same requests.

**4.15.2** `Host.attach(name, kind, heard, replay=...)` MUST attach a frontend as the `hello`
request of Section 4.7 of [DAEMON] does, MUST call `heard` with every message for it, in order, on a
thread that is not the caller's, and MUST return its client id; it MUST raise `RuntimeError` once
the host is closed.

**4.15.3** `Host.detach(client)` MUST let the frontend go as Section 4.7.4 of [DAEMON] states.

**4.15.4** `Host.attached` MUST be the number of frontends attached.

**4.15.5** `Host.idle` MUST be `True` where, and only where, the host is open, no frontend is
attached, no epic is going, starting or stopping, and no epic that ended with nobody attached awaits
a frontend.

**4.15.6** `Host.closed` MUST be whether the host has been closed.

**4.15.7** `Host.epic` MUST be the epic directory of the epic going, else of the one stopping, else
of the last, or `None`.

**4.15.8** `Host.away_for(role)` MUST return what `afk` last set for that role, else for every role.

**4.15.9** `Host.printed(text)` MUST send one `printed` record carrying `text` to every frontend.

**4.15.10** `Host.asked(client, said)` MUST carry out one request of Section 4.8 of [DAEMON] for
that frontend and return its answer without the `type` and `to` fields of a reply.

**4.15.11** `Host.status()` MUST return the keys of Section 4.6.4.1 of [DAEMON].

**4.15.12** `Host.close()` MUST close every epic of the host and let every frontend go with `gone`,
and MUST wait at most 15 seconds, counted from the first call, for those epics to release what they
made.

### 4.16. `Daemons`

```python
class Daemons:
    def here(self, workspace: str | os.PathLike[str] | None = None) -> Daemon | None: ...
    def all(self) -> list[Daemon]: ...
    def host(self, workspace: str | os.PathLike[str] | None = None) -> Daemon: ...
```

**4.16.1** Every `workspace` argument MUST mean the directory named, with every link followed, or
the current directory where it is `None`.

**4.16.2** `Daemons.here(workspace)` MUST return the `Daemon` of the workspace's own host, as
Section 4.4 of [DAEMON] finds it, or `None` where the daemon holds no live host of it.

**4.16.3** Where this machine's daemon speaks another protocol version, `Daemons.here` MUST return a
`Daemon` describing that daemon, its `protocol` the version it wrote or `0`.

**4.16.4** `Daemons.all()` MUST return a `Daemon` for every live host of every workspace and slot
the daemon holds, oldest first; `[]` where no daemon answers; and only the daemon itself where it
speaks another protocol version.

**4.16.5** `Daemons.host(workspace)` MUST return the `Daemon` of the workspace's own host, starting
this machine's daemon and then that host where they are absent, and waiting at most 10 seconds for
each to come up.

**4.16.6** `Daemons.host` MUST raise `OSError` where this machine's daemon speaks another protocol
version, with the message of Section 4.17.9 prefixed by `[Errno <EADDRINUSE>] `, and where no host
could be started.

**4.16.7** `Daemons` MUST NOT consult `HUMANIZE_DAEMON`.

### 4.17. `Daemon`

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

**4.17.1** `Daemon.at` MUST be this machine's daemon directory (Section 4.3 of [DAEMON]);
`Daemon.workspace` the workspace path, with every link followed; `Daemon.pid` the host's process;
`Daemon.started` when that process started, in UTC as `%Y-%m-%dT%H:%M:%SZ`; `Daemon.protocol` the
protocol version of Section 4.12 of [DAEMON] the daemon speaks, `0` for one that wrote none; and
`Daemon.slot` the host's slot.

**4.17.2** `Daemon.alive` MUST be whether a process of `pid` exists, counting a process the caller
cannot signal as existing.

**4.17.3** `Daemon.link(name, kind, replay=...)` MUST open a connection to the host, say `hello`
with `name`, `kind`, `replay`, the workspace and the slot, and return the attached `Link`.

**4.17.4** `Daemon.link` MUST raise `OSError` where nothing accepts the connection, or `hello` is
refused or not answered within 10 seconds.

**4.17.5** `Daemon.status()` MUST return the host's answer to the control request `status`; where
the host does not answer, it MUST return `pid`, `workspace`, `slot` (where not `""`), `started`,
`kind` `host` and `protocol` from the `Daemon` itself, with `attached` `0`, `flows` `[]` and `calls`
`[]`.

**4.17.6** `Daemon.detach()` MUST send the control request `detach` and return how many frontends
were let go, or `0` where the host did not answer.

**4.17.7** `Daemon.stop(seconds=...)` MUST send the control request `stop` and wait at most
`seconds` for the host process to exit, returning whether it exited; where the request is not
answered `ok`, it MUST return whether the process no longer exists.

**4.17.8** `Daemon.kill(seconds=...)` MUST send `SIGTERM` to the host process, then `SIGKILL` where
it has not exited after `seconds`, MUST leave the daemon and every other host running, and MUST
return whether the process exited.

**4.17.9** For a `Daemon` of another protocol version, the text describing it MUST be `the runs in
<workspace> are held by an older Humanize (pid <pid>); stop it with that version`, with `on this
machine` in place of `in <workspace>` where `workspace` is `""`.

**4.17.10** `Daemon.asked(said)` MUST send one control request with `workspace` and, where not `""`,
`slot` added, and return the answer, or `{}` where none came within 5 seconds.

### 4.18. `Link`

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

#### 4.18.1. Delivery

**4.18.1.1** A `Link` MUST be one frontend of one host, whether the host is in the calling process
or reached through the daemon, and MUST behave identically in both cases except as Section 4.18.4
states.

**4.18.1.2** `Link.client` MUST be the client id the host gave the frontend.

**4.18.1.3** `Link.told(message)` MUST queue one message for delivery; it is called by the transport
and is not for the caller.

**4.18.1.4** Iterating a `Link` MUST yield every message, in the order the host sent them, ending
after a `gone` message or after `close()`; iterating while a listener is set MUST raise
`RuntimeError`.

**4.18.1.5** `Link.heard(listener)` MUST deliver every message, those already queued first, to
`listener`, in order, on a thread of the link's own; an exception raised by `listener` MUST be
suppressed; a second call MUST raise `RuntimeError`.

#### 4.18.2. Requests

**4.18.2.1** `Link.asked(said, seconds=...)` MUST send one request of Section 4.8 of [DAEMON] and
return its answer, without the `type` and `to` fields of the reply.

**4.18.2.2** `Link.asked` MUST raise `Refused` with the reply's `why` where the reply says `ok`
`false`, and `TimeoutError` with the message `no answer to '<do>' in <seconds>s` where no reply came
within `seconds`.

**4.18.2.3** `Link.start(...)` MUST send the request `start` with every argument, `agents` and
`envs` as mappings of role to agent spec and environment spec, `params` and `budget` as JSON values
of the mapping or model given, and `resume` as a boolean or the text of the path.

**4.18.2.4** `Link.say`, `Link.answer`, `Link.stop`, `Link.force`, `Link.afk`, `Link.claim`,
`Link.release`, `Link.board` and `Link.aside` MUST each send the request of the same name with its
arguments as that request's fields.

**4.18.2.5** Once the host has let the frontend go, every request MUST raise `Refused` with the
reason the `gone` message gave.

#### 4.18.3. Closing

**4.18.3.1** `Link.close()` MUST let go of the host and MUST NOT stop any epic; a second call MUST
do nothing.

**4.18.3.2** Leaving a `with` block over a `Link` MUST call `close()`, however the block ended.

#### 4.18.4. Transport differences

**4.18.4.1** A `Link` to a host in the calling process MUST ignore `seconds` and answer each request
on the calling thread.

**4.18.4.2** A `Link` through the daemon MUST answer a send failure with `Refused` carrying `the
host could not be reached: <error>`.

**4.18.4.3** A `Link` through the daemon MUST deliver a `gone` message with `why` `the host went
away` where the connection ends, fails or carries a frame of no valid length without a `gone`
message, and with `why` the text of a `GONE` frame where one arrives.

### 4.19. `fakes`

**4.19.1** `hmz.sdk.fakes` MUST offer exactly `run_fake`, `FakeAgentDriver`, `FakeSession`,
`FakeEnvDriver`, `FakeOutworlder`, `Answer`, `Command`, `Handler` and `Reply`, with the signatures
and behaviour Section 3 states.

**4.19.2** `Hmz.run` MUST accept a `FakeAgentDriver` as an agent and a `FakeOutworlder` as the
outworlder, and an epic made with them MUST be written as any other epic is.

### 4.20. Returned types

Each type in this section is a returned type. Fields are listed in declaration order.

#### 4.20.1. Lines and specs

**4.20.1.1** `Line` MUST be a named tuple with the fields `flow: str`, `task: str`, `agents:
tuple[AgentSpec, ...] = ()`, `envs: tuple[EnvSpec, ...] = ()`, `params: dict[str, str] = {}`,
`budget: Budget | None = None`, `profile_flow: bool = False`, `profile_environment: bool = False`,
`resume: bool = False`, `as_json: bool = False` and `backup: tuple[str, ...] | None = None`, each
read from the `hmz exec` option of [CLI] that sets it.

**4.20.1.2** `AgentSpec` MUST be a frozen dataclass with the fields `role`, `harness`, `provider`
(`""` for this machine's own sign-in), `model`, `effort` (`""` for automatic) and `cli`, and `str()`
of one MUST be the text `-a` takes.

**4.20.1.3** `EnvSpec` MUST be a frozen dataclass with the fields `role`, `backend`, `provider`
(`""` for this machine) and `workdir`, and `str()` of one MUST be the text `-e` takes.

#### 4.20.2. Accounts and fallbacks

**4.20.2.1** `Provider` MUST have the fields `cli`, `name`, `way`, `env: Mapping[str, str]`, `args:
tuple[str, ...]` and `made`, and the property `at: Path`.

**4.20.2.2** `Way` MUST have the fields `name`, `about`, `argv` (its sign-in command, empty for
none), `asks`, `sets`, `args` and `stdin`.

**4.20.2.3** `Model` MUST have the fields `name`, `efforts: tuple[str, ...]` (hardest first) and
`swarms: bool`.

**4.20.2.4** `Falls` MUST have the fields `spec`, `to: tuple[str, ...]`, `tries: int`, `policy: str`
and `timeout: float`; `Policy` MUST have the fields `name` and `about`.

#### 4.20.3. Flows

**4.20.3.1** `Offer` MUST have the fields `whose` (a flowverse, `local` or `user`), `name` (the text
`-f` takes) and `about`.

**4.20.3.2** `Declaration` MUST have the fields `name`, `ref`, `description`, `hidden`, `resumable`,
`agents: tuple[AgentRole, ...]`, `envs: tuple[EnvRole, ...]` and `params` (the flow's `FlowParams`
type), and the methods `agent(name)` and `env(name)` returning a role or `None`.

**4.20.3.3** `AgentRole` MUST have the fields `name`, `declared`, `required`, `auto`, `harness`,
`capabilities`, `permission`, `skills` and `grant`; `EnvRole` MUST have the fields `name`,
`declared`, `required`, `auto`, `capabilities`, `cpu_count`, `memory`, `gpu_count`, `gpu_memory`,
`image`, `grant` and `resources`.

**4.20.3.4** `LiveCall` MUST have the fields `ref`, `name`, `depth` (`1` for the epic's flow),
`since` (monotonic seconds), `id` (`0` for none), `parent`, `task` and `resumable`.

**4.20.3.5** `Flowverse` MUST have the fields `name`, `url` (`""` for `local` and `user`), `at`,
`fetched` and `fixed`.

#### 4.20.4. Flowverse indexes

**4.20.4.1** `Index` MUST be a named tuple of `verse`, `releases` and `skipped`, with the methods
`flows()`, `versions(flow)`, `release(flow, version)` and `newest(flow, spec="")`.

**4.20.4.2** `Release` MUST have the fields `name`, `version`, `description`, `repo`, `ref`,
`commit`, `subdir`, `license`, `dependencies` and `owner`, and the properties `listed`, `owned`,
`semver` and `url`.

**4.20.4.3** `Installed` MUST have the fields `verse`, `name`, `version`, `commit`, `repo`, `ref`,
`subdir`, `dependencies` and `owner`, and the properties `listed`, `called` and `at`; `Update` MUST
be a named tuple of `installed` and `version`; `Skipped` MUST be a named tuple of `at` and `why`.

#### 4.20.5. Epics

**4.20.5.1** `Ran` MUST be a named tuple with at least the fields `at`, `flow`, `task`, `workspace`,
`began`, `ended` (`""` while going or abandoned), `how`, `agents: tuple[Drove, ...]`, `sessions:
tuple[Session, ...]`, `called: tuple[Called, ...]`, `resumable`, `ref`, `envs`, `params`, `budget`,
`picked_up`, `profile_flow` and `profile_environment`, and the property `name`, each as the epic
record of Section 6 of [FILES] wrote it.

**4.20.5.2** `Drove` MUST have the fields `agent` (the role), `backend`, `model`, `effort`,
`provider` and `name` (the agent's name, `""` in an epic written before agents had names), and the
property `spec`, its agent spec.

**4.20.5.3** `Called` MUST have the fields `flow`, `task`, `record`, `began`, `ended`, `how` and
`calls`.

**4.20.5.4** `Session` MUST have the fields `agent`, `backend`, `provider`, `ident`, `name`, `at`,
`flow`, `parent`, `record`, `where` and `harness`.

#### 4.20.6. Runtimes

**4.20.6.1** Each runtime type MUST carry the fields Section 7 of [CORE] defines for its backend,
the property `at`, and the method `held()` returning its fields as a mapping.

**4.20.6.2** `SSHHost` MUST have the fields `alias`, `host`, `user`, `port`, `identity_files` and
`proxy_jump`.

**4.20.6.3** `Checked` MUST be a frozen dataclass with the fields `reached: bool`, `said: str`,
`home: str`, `cpus: float`, `memory: int`, `gpus: tuple[str, ...]`, `usable: tuple[str, ...] |
None`, `gpu_memory: int`, `runtimes: tuple[str, ...]`, `version: str`, `short: tuple[str, ...]` and
`nodes: tuple[str, ...]`.

## 5. Security Considerations

This section states no requirement of its own. It names the properties stated elsewhere in this
document on which the security of a user's machine, credentials and work depends.

- A handed agent or environment allows a flow exactly its grant, an operation outside the grant
  raises `CapabilityNotGranted` whatever the harness or machine supports, and a callee is re-granted
  exactly what its own roles declare (Section 3.3.1.4 and Section 3.13.4.8).
- A session never runs with wider access than its role's `Permission`, and opening a session that
  neither the harness nor the machine can hold to its permission raises `HarnessSandboxed` (Section
  3.6.2.2 and Section 3.7.2.5).
- `Agent.derive` narrows and never widens: a permission the agent's own does not cover, or a skill
  the agent was not granted, raises `CapabilityNotGranted` (Section 3.7.3.2).
- A nested call given an agent whose permission does not cover the callee role's `_permission` is
  refused with `PermissionTooNarrow` before anything of the callee runs (Section 3.13.4.7).
- Every harness runs with approvals bypassed and with no model reviewing its actions, so an agent
  is limited only by its permission and by the hooks the flow hangs on it, and a
  `PERMISSION_REQUEST` hook that answers `allow=False` refuses the tool (Section 3.7.4 and Section
  3.9.2.6).
- A `PRE_TOOL_USE` hook refuses a tool only on `claude` and `qwen`, and on every other harness it
  is fired for a tool already reached for and refuses nothing (Section 3.9.2.5).
- When an agent calls a fake tool or a fake command line, its `call` runs in the flow's process, on
  the flow's event loop, as the flow (Section 3.6.6.2 and Section 3.6.6.9).
- Loading a flow imports and so executes its module, whether the ref names a local path, an
  installed flow or a `git+` repository fetched on first use, whereas installing a flow from a
  flowverse copies its directory at the manifest's `commit` and executes none of it (Section
  3.13.1.3, Section 3.13.3 and Section 3.14.4.5).
- `Hmz.carried` returns the settings of this machine for another daemon without any value that only
  a secret sets (Section 4.4.3.4).
- `Flowverses.plain` and `Flowverses.whence` return a flowverse's URL with its credentials removed
  (Section 4.8.21 and Section 4.8.22).
- `Accounts.environ` returns the environment a turn run as an account receives, and
  `Accounts.where` returns that account's credentials directory, so both hand account secrets or
  their location to the calling program (Section 4.9.7 and Section 4.9.16).
- `Runtimes.check` reaches a runtime without prompting for a password and reports a runtime that
  does not answer rather than raising (Section 4.10.13).
- `Epics.bundled` writes a `.hmzepic` archive with credentials struck out, and `Epics.imported`
  refuses an archive holding an unsafe member (Section 4.12.17 and Section 4.12.19).
- `Registry.write` keeps the written secret of an EasyTier daemon overwritten without one and
  refuses a secret shorter than 16 bytes (Section 4.14.3).
- `Remotes` reaches another machine's `hmz web` only through a port of this machine's loopback
  carried over ssh or EasyTier, installs `hmz` on that machine over ssh, and returns to the calling
  program the server's key and the headers that admit a request (Section 4.14.6 and
  Section 4.14.9).
- `Daemons` finds this machine's daemon without consulting `HUMANIZE_DAEMON`, and `Daemon.kill`
  signals only the one host process, leaving the daemon and every other host running
  (Section 4.16.7 and Section 4.17.8).

## 6. References

### 6.1. Normative References

- **[RFC2119]** Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels", BCP 14, RFC
  2119, March 1997, <https://www.rfc-editor.org/info/rfc2119>.
- **[RFC8174]** Leiba, B., "Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words", BCP 14, RFC
  8174, May 2017, <https://www.rfc-editor.org/info/rfc8174>.
- **[CORE]** "The Humanize Protocol: Core Concepts and Functional Behaviour", [`core.md`](core.md).
- **[CLI]** "The Humanize Protocol: Command-Line Interface", [`cli.md`](cli.md).
- **[DAEMON]** "The Humanize Protocol: Daemon", [`daemon.md`](daemon.md).
- **[WEB]** "The Humanize Protocol: Web Interface", [`web.md`](web.md).
- **[FILES]** "The Humanize Protocol: Settings, Environment Variables and Files", [`files.md`](files.md).

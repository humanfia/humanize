# Flows

Protocol classes here are pure protocols for type checking, with no implementation, and they are only used for type checking. During runtime, the real classes (also derived from these protocols) are passed to the flow function.

Mixin system is crucial to the flow system. It allows the flow to declare what it needs from the envs and agents, and the runtime will generate envs and agents satisfy those requirements. For example, if we only require an agent, it will not be able to run `/goal` command, even the underlying harness support it; if we require an agent with `GoalAgentMixin`, the underlying harness will be able to run `/goal` command. The same applies to envs.

## CLI

`hmz exec` should support these flags:

- `-a|--agents <role>=<harness>@<provider>/<model>:<effort>`: specifying an agent spec;
- `-e|--envs <role>=<backend>@<provider>/<workdir>`: specifying an env spec;
- `-p|--params <key>=<value>`: specifying a flow param.

All of the above supports comma-separated list and multiple flags. (e.g. `-a role1=... -a role2=...` or `-a role1=...,role2=...`)

- `-b|--budget duration=<duration>,cost=<cost>,output_tokens=<output_tokens>`: specifying a flow budget. Also supports multiple flags.

## Environments

```py
class EnvBackendKind(StrEnum):
    LOCAL = auto()
    SSH = auto()

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

    async def derive_subdir(
        self,
        *,
        subdir: pathlib.PurePosixPath | str,
    ) -> Env:
        ...

class LocalEnv(Env, Protocol): ...
    # Automatically added to the env collection if requested, and the user cannot override it.

class EnvCollection(TypedDict, extra_items=ReadOnly[Env]):
    pass
```

There are also various capability mixins for the envs, e.g.

```py
class CPUEnvMixin:
    _cpu_count: ClassVar[int] = 1

class MemoryEnvMixin:
    _memory: ClassVar[int] = 0

class ShellEnvMixin:
    async def exec(self, argv: Sequence[str], *, timeout: float = 0) -> tuple[int, str, str]: ...

class BashEnvMixin(ShellEnvMixin):
    @overload
    async def exec(self, script: str, *, timeout: float = 0) -> tuple[int, str, str]: ... 

class FilesEnvMixin:
    async def read(self, path: str) -> bytes: ...
    async def write(self, path: str, data: bytes) -> None: ...

class GPUEnvMixin:
    _gpu_count: ClassVar[int] = 1
    _gpu_memory: ClassVar[int] = 0

class GitWorktreeEnvMixin:
    async def derive_worktree(
        self,
        *,
        ref: str | None = None,
        dir: pathlib.PurePosixPath | str | None = None,
    ) -> Env:
        ...

class TemporaryClonedDirEnvMixin:
    async def derive_temp_clone(self, id: str) -> Env: ...
        # Derive an env at a temporary dir with the same content as the current env. The temporary dir will be automatically cleaned up when the flow ends and the flow is not resumable.

    async def destroy_temp_clone(self, id: str) -> None: ...
...
```

Here is an example of a flow's environment collection:

```py
class MyEnv(Env, CPUEnvMixin, MemoryEnvMixin):
    _cpu_count = 4
    _memory = 8 * 1024 * 1024 * 1024

class MyEnvCollection(EnvCollection):
    my_env: MyEnv
```

## Agents

```py
class HarnessKind(StrEnum):
    CLAUDE = "claude"
    CODEX = "codex"
    CURSOR_AGENT = "cursor-agent"
    ...

class PermissionKind(StrEnum):
    NONE = auto()
    READ = auto()
    ALL = auto()

@dataclass(frozen=True)
class Permission:
    local: PermissionKind = PermissionKind.ALL
    user: PermissionKind = PermissionKind.READ
    system: PermissionKind = PermissionKind.READ
    online: PermissionKind = PermissionKind.NONE # Can only be NONE or ALL.

    def __post_init__(self) -> None: ...
        # Ensure local >= user >= system.

class HookKind(StrEnum):
    SOME_HOOK = auto() # Just a placeholder for the example.
    ... # Including ALL possible hooks of all the harnesses.

@dataclass(frozen=True)
class HookParams:
    ctx: FlowContext
    session: Session

@dataclass(frozen=True)
class SomeHookHookParams(HookParams):
    ...

@dataclass(frozen=True)
class HookResult:
    ...

@dataclass(frozen=True)
class SomeHookHookResult(HookResult):
    ...

class HookFn[TParams: HookParams, TResult](Protocol):
    async def __call__(self, params: TParams) -> TResult: ...

class Budget(pydantic.BaseModel):
    duration: datetime.timedelta | None = None
    cost: float | None = None # In USD.
    output_tokens: int | None = None
    # Must ensure at least one of the above is not None.
    # For `chat` flow, we set cost as inf to make it unlimited.
    graceful: bool = True # If True, the run will try to finish the current turn before stopping. If False, the run will stop immediately.

class Usage(pydantic.BaseModel):
    duration: datetime.timedelta = datetime.timedelta(0)
    cost: float = 0.0 # In USD.
    output_tokens: int = 0

class Session(Protocol):
    @property
    def agent(self) -> Agent: ...

    @property
    def env(self) -> Env: ...

    @property
    def usage(self) -> Usage: ... # Live updated.

class Agent(Protocol):
    _permission: ClassVar[Permission]
    _skills: ClassVar[tuple[str, ...]]

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

    @overload
    def derive(
        self,
        *,
        permission: Permission | None = None,
        skills: tuple[str, ...] | None = None,
    ) -> Self: ...

    async def fork(
        self,
        session: Session,
        *,
        env: Env,
    ) -> Session: ...

    @overload
    def hook(
        self,
        kind: Literal[HookKind.SOME_HOOK],
        fn: HookFn[SomeHookHookParams, SomeHookHookResult] | None,
    ) -> None: ...

    ... # Should include all the common hooks of all the harnesses.

    @overload
    async def run(
        self,
        prompt: str,
        *,
        session: Session,
        budget: Budget | None = None,
    ) -> str: ...

    @overload
    async def run[TOutput: pydantic.BaseModel](
        self,
        prompt: str,
        *,
        session: Session,
        output_schema: Type[TOutput],
        budget: Budget | None = None,
    ) -> TOutput: ...

    async def spawn(
        self,
        *,
        env: Env,
    ) -> Session: ...

class Outworlder(Agent, Protocol): ...
    # Automatically added to the agent collection if requested, and the user cannot override it.
    # Note that this is not steering: steering is that the user can attach to a session and inject prompts, while this is that the user (or designated agent by the outside flow) can act as an agent in the flow.

    @classmethod
    def new(cls) -> Self: ...
        # Create a fake outworlder agent. This is used for the case where the callee wants to run the outworlder, and the caller can pre-configure this to act as an outworlder.

    @property
    def away(self) -> bool: ...
        # True if /afk is on.
        # When away, all runs will response default value (e.g. "" for str, and all values by default for pydantic.BaseModel).

    @overload
    def hook(
        self,
        kind: Literal[HookKind.OUTWORLDER_RUN],
        fn: HookFn[OutworlderRunHookParams, OutworlderRunHookResult] | None,
    ) -> None: ...
        # A fake hook to handle the case where the callee wants to run the outworlder. The caller can pre-configure this to act as an outworlder.

class ClaudeCodeAgent(Agent, ..., Protocol):
    pass
    # With all supported mixins. This is a useful type for flows to declare that they require exactly a Claude Code agent.

... # And all other harnesses.

class AgentCollection(TypedDict, extra_items=ReadOnly[Agent]):
    pass
```

There are also various capability mixins for the agents, e.g.

```py
class GoalCommandAgentMixin: ...
    # This will lead to `/goal <goal>` command being available in agent.run(...).

class LoopCommandAgentMixin: ...
    # This will lead to `/loop <interval> <task>` command being available in agent.run(...).

class SteeringAgentMixin:
    async def steer(
        self,
        prompt: str,
        *,
        session: Session,
        queued: bool = True, # Claude Code & Codex supports interrupting the current turn, or queueing the prompt to be executed after the current turn. (Just like pressing Esc or not after sending msg to a running agent.)
    ) -> None: ...
        # Used to steer.

class PermissionRequestHookAgentMixin:
    @overload
    def hook(
        self,
        kind: Literal[HookKind.PERMISSION_REQUEST],
        fn: HookFn[PermissionRequestHookParams, PermissionRequestHookResult] | None,
    ) -> None: ...

... # And ALL hooks of all the harnesses.

class AskUserHookAgentMixin: # A fake hook to handle the case where the harness want to ask the user something.
    @overload
    def hook(
        self,
        kind: Literal[HookKind.ASK_USER],
        fn: HookFn[AskUserHookParams, AskUserHookResult] | None,
    ) -> None: ...
```

The flow declares what an agent must be able to do by subclassing it:

```py
class MyAgent(Agent, GoalCommandAgentMixin, LoopCommandAgentMixin, PermissionRequestHookAgentMixin):
    _permission = Permission(
        local=PermissionKind.ALL,
        user=PermissionKind.READ,
        system=PermissionKind.NONE,
        online=PermissionKind.NONE,
    )
    _skills = ("review-notes",)

class MyAgentCollection(AgentCollection):
    my_agent: MyAgent
```

## Flows

```py
class FlowParams(pydantic.BaseModel): ...

class FlowState(Protocol):
    def __getitem__(self, key: str) -> Any: ...

    def __setitem__(self, key: str, value: Any) -> None: ...

    def __delitem__(self, key: str) -> None: ...

    def __contains__(self, key: str) -> bool: ...

class FlowContext(Protocol):
    @property
    def budget(self) -> Budget: ...

    @property
    def flow(self) -> Flow: ...

    @property
    def resumed(self) -> bool: ...

    @property
    def state(self) -> FlowState | None: ...
        # Only available if the flow is resumable.

    @property
    def usage(self) -> Usage: ...

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
        # The passed agents and envs must be not be more narrow than the flow's declared agents and envs.

def load(ref: str) -> Flow: ...
```

A flow ref can be either:

- (in a flow only) `:<subflow>`: another flow in the same flow module;
- (in a flow only) `<flow>:<subflow>`: a flow in the same flowverse;
- `<pip-style-vcs-url>#<flow>:<subflow>`: a flow in another flowverse.

If the parent flow is resumed, the subflows resumes as well if they are called with exactly the same task agents, envs, and params.

## Defining a flow

```py
class FlowFn[TAgentCollection: AgentCollection, TEnvCollection: EnvCollection, TFlowParams: FlowParams](Protocol):
    async def __call__(
        self,
        task: str,
        *,
        agents: TAgentCollection,
        envs: TEnvCollection,
        params: TFlowParams,
        ctx: FlowContext,
    ) -> Any: ...

def flow[TAgentCollection: AgentCollection, TEnvCollection: EnvCollection, TFlowParams: FlowParams](
    *,
    agents: type[TAgentCollection],
    envs: type[TEnvCollection],
    params: type[TFlowParams],
    description: str | None = None,
    hidden: bool = False,
    resumable: bool = False, # A flag to enable /resume.
) -> Callable[[FlowFn[TAgentCollection, TEnvCollection, TFlowParams]], Flow]: ...
    # The decorated function name is the flow name.
```

## Misc

Should have a very fine-grained and hierarchical exception system, so that the flow can catch specific exceptions and handle them, and the flow can also catch all exceptions and handle them.

```py
class FlowException(Exception): ...
    # Base class for all flow exceptions.

... # And ALL exceptions of all the harnesses.

... # And ALL exceptions of all the envs.

... # And ALL exceptions of Humanize flow runtime.
```

Some harnesses mix permission with approval policy. In our design, all approval are BYPASS (e.g. danger-full-access + never for Codex, or bypassPermissions for Claude Code). And we never use any auto review mode (where the model is responsible for reviewing the action). If the managed policy rejects BYPASS, they will be run in the most permissive-possible non-auto mode, and all their action requests will be always approved. For example, if BYPASS is disallowed in Claude Code, it will be run in acceptEdits mode, and all its action requests will be always approved. This is to ensure that the flow can always run without any human intervention, and the harnesses will never be able to reject any action request.

`chat` flow is a special flow. It will always use the harness specific agent (e.g. ClaudeCodeAgent) for the selected harness. Therefore, it will always has all the capabilities of the agent.

# Flows

Protocol classes here are pure protocols for type checking, with no implementation, and they are only used for type checking. During runtime, the real classes (also derived from these protocols) are passed to the flow function.

Mixin system is crucial to the flow system. It allows the flow to declare what it needs from the envs and agents, and the runtime will generate envs and agents satisfy those requirements. For example, if we only require an agent, it will not be able to run `/goal` command, even the underlying harness support it; if we require an agent with `GoalAgentMixin`, the underlying harness will be able to run `/goal` command. The same applies to envs.

## CLI

`hmz exec` should support these flags:

- `-a <role>=<harness>@<provider>/<model>:<effort>`: specifying an agent spec;
- `-e <role>=<backend>@<provider>/<workdir>`: specifying an env spec;
- `-p <key>=<value>`: specifying a flow param.

## Environments

```py
class EnvBackendKind(StrEnum):
    LOCAL = auto()
    SSH = auto()

class Env(Protocol):
    @property
    def backend(self) -> EnvBackendKind: ...

    @property
    def provider(self) -> str: ...

    @property
    def role(self) -> str: ...

    @property
    def workdir(self) -> pathlib.PurePosixPath: ...

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
    WRITE = auto()

@dataclass(frozen=True)
class Permission:
    local: PermissionKind = PermissionKind.READ
    user: PermissionKind = PermissionKind.NONE
    system: PermissionKind = PermissionKind.NONE
    online: PermissionKind = PermissionKind.NONE

    def __post_init__(self) -> None: ...
        # Ensure local >= user >= system.
        # Ensure online is either NONE or READ.

class HookKind(StrEnum):
    PRE_TOOL_USE = auto()
    ...

class HookFn[TParams: HookParams, TResult](Protocol):
    async def __call__(self, params: TParams) -> TResult: ...

class Session(Protocol):
    @property
    def agent(self) -> Agent: ...

    @property
    def env(self) -> Env: ...

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
        kind: Literal[HookKind.PRE_TOOL_USE],
        fn: HookFn[PreToolUseHookParams, PreToolUseHookResult] | None,
    ) -> Self: ...

    ... # Should include all the common hooks of all the harnesses.

    @overload
    async def run(
        self,
        prompt: str,
        *,
        session: Session,
    ) -> str: ...

    @overload
    async def run[TOutput: pydantic.BaseModel](
        self,
        prompt: str,
        *,
        session: Session,
        output_schema: Type[TOutput]
    ) -> TOutput: ...

    async def spawn(
        self,
        *,
        env: Env,
    ) -> Session: ...

class Outworlder(Agent, Protocol): ...
    # Automatically added to the agent collection if requested, and the user cannot override it.
    # Note that this is not steering: steering is that the user can attach to a session and inject prompts, while this is that the user (or designated agent by the outside flow) can act as an agent in the flow.

class AgentCollection(TypedDict, extra_items=ReadOnly[Agent]):
    pass
```

There are also various capability mixins for the agents, e.g.

```py
class GoalCommandAgentMixin: ...
    # This will lead to `/goal <goal>` command being available in agent.run(...).

class LoopCommandAgentMixin: ...
    # This will lead to `/loop <interval> <task>` command being available in agent.run(...).
```

The flow declares what an agent must be able to do by subclassing it:

```py
class MyAgent(Agent, GoalCommandAgentMixin, LoopCommandAgentMixin):
    _permission = Permission(
        local=PermissionKind.WRITE,
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
class Flow(Protocol):
    @property
    def description(self) -> str | None: ...

    @property
    def resumable(self) -> bool: ...

    async def __call__(
        self,
        task: str,
        *,
        agents: AgentCollection,
        envs: EnvCollection,
        params: pydantic.BaseModel,
        try_resume: bool = False,
    ) -> Any: ...

def load(ref: str) -> Flow: ...
```

A flow ref can be either:

- (in a flow only) `:<subflow>`: another flow in the same flow module;
- (in a flow only) `<flow>:<subflow>`: a flow in the same flowverse;
- `<pip-style-vcs-url>#<flow>:<subflow>`: a flow in another flowverse.

## Defining a flow

```py
class FlowFn[TAgentCollection: AgentCollection, TEnvCollection: EnvCollection, TFlowParams: pydantic.BaseModel](Protocol):
    async def __call__(
        self,
        task: str,
        *,
        agents: TAgentCollection,
        envs: TEnvCollection,
        params: TFlowParams,
        epic: Epic,
    ) -> Any: ...

def flow[TAgentCollection: AgentCollection, TEnvCollection: EnvCollection, TFlowParams: pydantic.BaseModel](
    *,
    agents: type[TAgentCollection],
    envs: type[TEnvCollection],
    params: type[TFlowParams],
    description: str | None = None,
    hidden: bool = False,
    resumable: bool = False,
) -> Callable[[FlowFn[TAgentCollection, TEnvCollection, TFlowParams]], Flow]: ...
    # The decorated function name is the flow name.
```
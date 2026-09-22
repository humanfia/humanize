# Flows

## Principles

The user can configure:

- agents: `-a name=harness@provider/model:effort,...`
- env sources: `-e name=backend@provider/workdir:capacity,...`
- flow params

The flow can enforce:

- agent capabilities (e.g. permission mode, goal, etc.)
- env requirements (e.g. container image, resource limits, etc.)

Both are declared as subclasses, read from the flow's collection annotations, and
checked at `-a`/`-e` parse time — before any session starts.

## Environments

```py
class EnvSource(Protocol):
    _cpu_count: ClassVar[int] = 0        # 0: no requirement
    _memory: ClassVar[int] = 0

    @property
    def backend(self) -> EnvBackendType: ...

    @property
    def capacity(self) -> int: ...

    @property
    def envs(self) -> Sequence[Env]: ...

    @property
    def name(self) -> str: ...

    @property
    def provider(self) -> str: ...

    @property
    def workdir(self) -> pathlib.Path: ...

    async def new(self) -> Env: ...      # one of `capacity`; the flow closes it

    @staticmethod
    async def new_local(workdir: pathlib.Path) -> LocalEnv: ...
```

```py
class EnvSourceCollection(TypedDict, extra_items=ReadOnly[EnvSource]):
    pass
```

```py
class Env(Protocol):
    @property
    def source(self) -> EnvSource: ...
```

The flow declares what a source must be able to give by subclassing it:

```py
class MySource(EnvSource, GPUSourceMixin, BashSourceMixin):
    _cpu_count = 4
    _memory = 8 * 1024 * 1024 * 1024

    _gpu_count = 1
    _gpu_memory = 8 * 1024 * 1024 * 1024

class MyEnvSourceCollection(EnvSourceCollection):
    my_source: MySource
```

## Agents

```py
class Agent(Protocol):
    _permission: ClassVar[PermissionType]
    _skills: ClassVar[tuple[str, ...]]

    @property
    def effort(self) -> str: ...

    @property
    def harness(self) -> HarnessType: ...

    @property
    def hooks(self) -> HookHub: ...

    @property
    def model(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def provider(self) -> str: ...

    @property
    def sessions(self) -> Sequence[Session]: ...

    def derive(
        self,
        *,
        name: str | None = None,                 # None: derived from self.name
        permission: PermissionType | None = None,
        skills: tuple[str, ...] | None = None,
    ) -> Self: ...                               # hooks are copied, not shared

    async def fork(
        self,
        session: Session,
        *,
        env: Env,
    ) -> Session: ...

    @overload
    async def run(
        self,
        prompt: str,
        *,
        session: Session,
    ) -> str: ...

    @overload
    async def run[TOutput: SessionOutput](
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

    async def stop(
        self,
        session: Session,
    ) -> None: ...
```

```py
class AgentCollection(TypedDict, extra_items=ReadOnly[Agent]):
    pass
```

The flow declares what an agent must be able to do by subclassing it:

```py
class MyAgent(Agent, GoalMixin):
    _permission = PermissionType.WORKSPACE_WRITE
    _skills = ("review-notes",)

class MyAgentCollection(AgentCollection):
    my_agent: MyAgent
```

### Outworlder

An `Outworlder` is an `Agent` that stands for whoever is outside the flow — the
TUI user, a parent flow, a test. It is not filled from `-a`; the runtime
constructs it. To the flow it is an ordinary agent: `run(prompt, session=)`
sends `prompt` out and returns what comes back (`""` when nobody is there).

```py
class Outworlder(Agent, Protocol):
    pass

class MyAgentCollection(AgentCollection):
    my_agent: MyAgent
    user: Outworlder
```

## Hooks

```py
class HookFn[TParams, TResult](Protocol):
    async def __call__(self, params: TParams) -> TResult: ...

class HookHub(Protocol):
    @property
    def pre_tool_use(self) -> HookFn[PreToolUseHookParams, PreToolUseHookResult] | None: ...

    @pre_tool_use.setter
    def pre_tool_use(self, hook: HookFn[PreToolUseHookParams, PreToolUseHookResult] | None) -> None: ...

    @pre_tool_use.deleter
    def pre_tool_use(self) -> None: ...

    ... # Should include the common hooks of all the harnesses.
```

Every hook's params carry the `session` the hook fired in. A change to an
agent's hooks takes effect on its next `run`.

## Sessions

```py
class SessionOutput(pydantic.BaseModel):
    pass

class Session(Protocol):
    @property
    def agent(self) -> Agent: ...

    @property
    def env(self) -> Env: ...
```

## Flows

```py
class Epic(Protocol):
    @property
    def flow(self) -> Flow: ...

    @property
    def state(self) -> object | None: ...

    @state.setter
    def state(self, value: object | None) -> None: ...   # persisted on write
```

```py
class Flow(Protocol):
    @classmethod
    async def load(cls, ref: str) -> Self: ...

    @property
    def description(self) -> str | None: ...

    @property
    def hidden(self) -> bool: ...

    @property
    def resumable(self) -> bool: ...

    async def run(
        self,
        task: str,
        *,
        epic: Epic,
    ) -> Any: ... # Or resume if epic.state is not None.

    async def spawn(
        self,
        *,
        agents: AgentCollection,
        envs: EnvSourceCollection,
        params: FlowParams,
    ) -> Epic: ...

    async def stop(
        self,
        epic: Epic,
    ) -> None: ...
```

`Epic` is to `Flow` what `Session` is to `Agent`: a passive record the flow is
run against. `run` may be called on the same epic more than once; `state` is
shared across those runs, and `resume` continues the last unfinished one.

This is the actual flow class that is run by the runtime. Developers should not
derive it directly; they define an entrypoint function and mark it with `@flow`,
which wraps it into a `Flow` instance.

## Defining a flow

```py
class FlowFn[TAgentCollection: AgentCollection, TEnvSourceCollection: EnvSourceCollection, TFlowParams: FlowParams](Protocol):
    async def __call__(
        self,
        task: str,
        *,
        agents: TAgentCollection,
        envs: TEnvSourceCollection,
        params: TFlowParams,
        epic: Epic,
    ) -> Any: ...

def flow[TAgentCollection: AgentCollection, TEnvSourceCollection: EnvSourceCollection, TFlowParams: FlowParams](
    *,
    description: str | None = None,
    hidden: bool = False,
    resumable: bool = False,
) -> Callable[[FlowFn[TAgentCollection, TEnvSourceCollection, TFlowParams]], Flow]: ...
```
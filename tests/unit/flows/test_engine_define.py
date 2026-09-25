"""Defining a flow: what the decorator refuses, what it defaults, and what a flow declares.

The decorator runs as a flow's module is imported, so it checks only what is cheap -- the
function, the three classes, the name -- and leaves the collections' annotations to be read
the first time the flow is called or described. What they declare is read here through
`describe()`, which is what the pickers and the command line read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NotRequired, Required, cast

import pytest
from typing_extensions import ReadOnly

from hmz.flows import (
    Agent,
    AgentCollection,
    BashEnvMixin,
    ClaudeCodeAgent,
    CodexAgent,
    CPUEnvMixin,
    Env,
    EnvCollection,
    FlowContext,
    FlowDefinitionError,
    FlowParams,
    GoalCommandAgentMixin,
    GPUEnvMixin,
    HarnessKind,
    LocalEnv,
    MemoryEnvMixin,
    Outworlder,
    Permission,
    PermissionKind,
    ShellEnvMixin,
    SteeringAgentMixin,
    flow,
)
from hmz.runtime.flowing.engine import FlowImpl, full_view
from hmz.runtime.flowing.spi import HARNESS_CAPABILITIES

if TYPE_CHECKING:
    from hmz.runtime.flowing.declaring import Declaration


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    repo: Env


class Params(FlowParams):
    rounds: int = 3


def _described(made: object) -> Declaration:
    assert type(made) is FlowImpl
    return made.describe()


# ------------------------------------------------------------------------ the decorator


def test_a_flow_is_named_after_its_function_and_described_by_its_docstring() -> None:
    @flow(agents=Agents, envs=Envs, params=Params)
    async def fix(
        task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
    ) -> None:
        """Fix the build.

        More that is not the description.
        """

    declared = _described(fix)
    assert (declared.name, declared.description) == ("fix", "Fix the build.")
    assert (declared.hidden, declared.resumable) == (False, False)
    assert declared.ref.endswith(":fix")
    assert fix.expected_agents is Agents
    assert fix.expected_envs is Envs
    assert fix.expected_params is Params
    assert fix.resumable is False
    assert fix.description == "Fix the build."


def test_what_a_flow_says_about_itself_wins() -> None:
    @flow(
        agents=Agents,
        envs=Envs,
        params=Params,
        name="gen-plan",
        description="plans",
        hidden=True,
        resumable=True,
    )
    async def whatever(
        task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
    ) -> None:
        """Not this."""

    declared = _described(whatever)
    assert (declared.name, declared.description) == ("gen-plan", "plans")
    assert (declared.hidden, declared.resumable) == (True, True)
    assert declared.params is Params


def test_a_flow_with_no_docstring_describes_nothing() -> None:
    @flow(agents=Agents, envs=Envs, params=Params)
    async def silent(
        task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
    ) -> None:
        pass

    assert silent.description is None


async def _sync_body(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> None:
    del task, agents, envs, params, ctx


def _not_async(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> None:
    del task, agents, envs, params, ctx


async def _no_ctx(task: str, *, agents: Agents, envs: Envs, params: Params) -> None:
    del task, agents, envs, params


async def _no_task(*, agents: Agents, envs: Envs, params: Params, ctx: Any) -> None:
    del agents, envs, params, ctx


async def _extra(
    task: str,
    *,
    agents: Agents,
    envs: Envs,
    params: Params,
    ctx: FlowContext,
    more: int,
) -> None:
    del task, agents, envs, params, ctx, more


async def _loose(task: str, **said: Any) -> None:
    del task, said


async def _defaulted(
    task: str,
    *,
    agents: Agents,
    envs: Envs,
    params: Params,
    ctx: FlowContext,
    more: int = 1,
) -> None:
    del task, agents, envs, params, ctx, more


@pytest.mark.parametrize(
    "fn", [_not_async, _no_ctx, _no_task, _extra], ids=lambda one: one.__name__
)
def test_a_function_that_is_no_flow_is_refused(fn: Any) -> None:
    with pytest.raises(FlowDefinitionError):
        flow(agents=Agents, envs=Envs, params=Params)(fn)


@pytest.mark.parametrize("fn", [_loose, _defaulted], ids=lambda one: one.__name__)
def test_a_function_taking_more_than_it_needs_is_a_flow(fn: Any) -> None:
    assert type(flow(agents=Agents, envs=Envs, params=Params)(fn)) is FlowImpl


class NotAgents(dict[str, Agent]):
    pass


@pytest.mark.parametrize(
    "said",
    [
        {"agents": NotAgents},
        {"agents": Envs},
        {"envs": Agents},
        {"envs": dict},
        {"params": dict},
        {"params": Params()},
        {"name": "has space"},
        {"name": "a:b"},
        {"name": "a#b"},
        {"name": ""},
        {"name": 3},
    ],
    ids=str,
)
def test_what_is_no_declaration_is_refused(said: dict[str, Any]) -> None:
    given: dict[str, Any] = {"agents": Agents, "envs": Envs, "params": Params} | said
    with pytest.raises(FlowDefinitionError):
        flow(**given)(_sync_body)


def test_the_bare_collections_declare_nothing() -> None:
    bare: Any = _sync_body
    declared = _described(
        flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)(bare)
    )
    assert (declared.agents, declared.envs) == ((), ())


# ------------------------------------------------------------------------ what it says


class Coder(Agent, GoalCommandAgentMixin, SteeringAgentMixin):
    _permission = Permission(system=PermissionKind.NONE, online=PermissionKind.ALL)
    _skills = ("review",)


class Here(LocalEnv, BashEnvMixin): ...


class Trainer(Env, ShellEnvMixin, CPUEnvMixin, MemoryEnvMixin, GPUEnvMixin):
    _cpu_count = 16
    _memory = 1 << 34
    _gpu_count = 8
    _gpu_memory = 80 << 30


class Declared(AgentCollection):
    coder: Coder
    claude: ClaudeCodeAgent
    human: Outworlder
    maybe: NotRequired[Agent]
    frozen: ReadOnly[Agent]


class Places(EnvCollection):
    here: Here
    trainer: Trainer
    extra: NotRequired[Env]


def test_every_role_is_read_off_its_type() -> None:
    @flow(agents=Declared, envs=Places, params=Params)
    async def declaring(
        task: str, *, agents: Declared, envs: Places, params: Params, ctx: FlowContext
    ) -> None:
        del task, agents, envs, params, ctx

    declared = _described(declaring)
    roles = {role.name: role for role in declared.agents}
    assert list(roles) == ["coder", "claude", "human", "maybe", "frozen"]
    coder = roles["coder"]
    assert coder.declared is Coder
    assert coder.capabilities == {GoalCommandAgentMixin, SteeringAgentMixin}
    assert coder.permission == Coder._permission
    assert coder.skills == ("review",)
    assert (coder.required, coder.auto, coder.harness) == (True, False, None)
    assert coder.grant.capabilities == coder.capabilities
    claude = roles["claude"]
    assert claude.harness is HarnessKind.CLAUDE
    assert claude.capabilities == HARNESS_CAPABILITIES[HarnessKind.CLAUDE]
    assert roles["human"].auto
    assert not roles["maybe"].required
    assert roles["frozen"].required
    places = {role.name: role for role in declared.envs}
    assert places["here"].auto
    assert places["here"].capabilities == {BashEnvMixin, ShellEnvMixin}
    trainer = places["trainer"]
    assert (
        trainer.cpu_count,
        trainer.memory,
        trainer.gpu_count,
        trainer.gpu_memory,
    ) == (16, 1 << 34, 8, 80 << 30)
    assert trainer.resources
    assert not places["here"].resources
    assert not places["extra"].required
    assert declared.agent("coder") is coder
    assert declared.agent("nobody") is None
    assert declared.env("trainer") is trainer
    assert declared.env("nobody") is None


def test_a_collection_and_its_types_may_be_declared_inside_a_function() -> None:
    class Local(Agent, GoalCommandAgentMixin): ...

    class Inner(AgentCollection):
        local: Local
        optional: NotRequired[Local]

    class More(Inner, total=False):
        extra: Agent
        forced: Required[Agent]

    @flow(agents=More, envs=Envs, params=Params)
    async def inner(
        task: str, *, agents: More, envs: Envs, params: Params, ctx: FlowContext
    ) -> None:
        del task, agents, envs, params, ctx

    roles = {role.name: role for role in _described(inner).agents}
    assert roles["local"].declared is Local
    assert roles["local"].required
    assert not roles["optional"].required
    assert not roles["extra"].required
    assert roles["forced"].required


def test_what_a_collection_names_is_resolved_only_when_asked_for() -> None:
    class Later(AgentCollection):
        agent: Unknown  # noqa: F821  # pyright: ignore[reportUndefinedVariable]

    @flow(agents=Later, envs=Envs, params=Params)
    async def later(
        task: str, *, agents: Later, envs: Envs, params: Params, ctx: FlowContext
    ) -> None:
        del task, agents, envs, params, ctx

    with pytest.raises(FlowDefinitionError, match="cannot be resolved"):
        _described(later)


class _Mixed(Agent, ShellEnvMixin): ...


class _Both(ClaudeCodeAgent, CodexAgent): ...


class _Mixin(Outworlder, GoalCommandAgentMixin): ...


class _BadPermission(Agent):
    _permission = "all"  # pyright: ignore[reportAssignmentType]


class _BadSkills(Agent):
    _skills = "review"  # pyright: ignore[reportAssignmentType]


class _EnvWithAgentMixin(Env, GoalCommandAgentMixin): ...


class _NegativeCPUs(Env, CPUEnvMixin):
    _cpu_count = -1


@pytest.mark.parametrize(
    ("agent", "env"),
    [
        (_Mixed, Env),
        (_Both, Env),
        (_Mixin, Env),
        (_BadPermission, Env),
        (_BadSkills, Env),
        (int, Env),
        (Agent | None, Env),
        (Agent, _EnvWithAgentMixin),
        (Agent, _NegativeCPUs),
        (Agent, Agent),
        (Env, Env),
    ],
    ids=repr,
)
def test_a_type_no_agent_or_environment_can_be_is_refused(agent: Any, env: Any) -> None:
    class BadAgents(AgentCollection):
        role: agent  # pyright: ignore[reportInvalidTypeForm]

    class BadEnvs(EnvCollection):
        place: env  # pyright: ignore[reportInvalidTypeForm]

    @flow(agents=BadAgents, envs=BadEnvs, params=Params)
    async def bad(
        task: str, *, agents: BadAgents, envs: BadEnvs, params: Params, ctx: FlowContext
    ) -> None:
        del task, agents, envs, params, ctx

    with pytest.raises(FlowDefinitionError):
        _described(bad)


def test_full_view_marks_a_flow_and_only_a_flow() -> None:
    made = flow(agents=Agents, envs=Envs, params=Params)(_sync_body)
    assert full_view(made) is made
    assert cast("Any", made)._full
    with pytest.raises(TypeError):
        full_view(object())  # pyright: ignore[reportArgumentType]


def test_a_flow_says_what_it_is() -> None:
    made = flow(agents=Agents, envs=Envs, params=Params, name="shown")(_sync_body)
    assert "shown" in repr(made)

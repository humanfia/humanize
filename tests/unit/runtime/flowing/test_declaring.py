"""What a flow declares, read off its collections: `declaring`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, NotRequired, Required

import pydantic
import pytest

from hmz.flows import (
    Agent,
    AgentCollection,
    ClaudeCodeAgent,
    CodexAgent,
    CPUEnvMixin,
    Env,
    EnvCollection,
    FilesEnvMixin,
    FlowDefinitionError,
    FlowParams,
    GoalCommandAgentMixin,
    GPUEnvMixin,
    HarnessKind,
    ImageEnvMixin,
    LocalEnv,
    MemoryEnvMixin,
    Outworlder,
    Permission,
    PermissionKind,
    ShellEnvMixin,
)
from hmz.runtime.flowing.declaring import (
    AgentRole,
    Declaration,
    EnvRole,
    Grant,
    agent_roles,
    checked_definition,
    env_roles,
)

if TYPE_CHECKING:
    from collections.abc import Callable

HERE: dict[str, Any] = globals()


def roles_of(collection: type) -> tuple[AgentRole, ...]:
    return agent_roles(collection, HERE, {})


def envs_of(collection: type) -> tuple[EnvRole, ...]:
    return env_roles(collection, HERE, {})


# ---------------------------------------------------------------------------- grants


def test_equal_grants_are_one_grant() -> None:
    caps = frozenset({GoalCommandAgentMixin})
    assert Grant.of(caps) is Grant.of(frozenset({GoalCommandAgentMixin}))
    assert Grant.of(caps, Permission(), ("s",)) is Grant.of(caps, Permission(), ("s",))
    assert Grant.of(caps) is not Grant.of(caps, skills=("s",))
    assert Grant.of(frozenset()).capabilities == frozenset()


# ---------------------------------------------------------------------- agent roles


class Goal(Agent, GoalCommandAgentMixin): ...


class Offline(Agent):
    _permission = Permission(online=PermissionKind.NONE)
    _skills = ("https://example.com/s#one",)


class Team(AgentCollection):
    coder: Goal
    reviewer: NotRequired[Offline]
    claude: ClaudeCodeAgent
    person: Outworlder
    plain: Annotated[Agent, "metadata"]
    sure: Required[Agent]


def test_agent_roles_read_each_key() -> None:
    coder, reviewer, claude, person, plain, sure = roles_of(Team)
    assert [one.name for one in (coder, reviewer, claude, person, plain, sure)] == [
        "coder",
        "reviewer",
        "claude",
        "person",
        "plain",
        "sure",
    ]
    assert coder.declared is Goal
    assert coder.capabilities == frozenset({GoalCommandAgentMixin})
    assert (coder.required, coder.auto, coder.harness) == (True, False, None)
    assert coder.grant is Grant.of(frozenset({GoalCommandAgentMixin}))
    assert reviewer.required is False
    assert reviewer.permission == Permission(online=PermissionKind.NONE)
    assert reviewer.skills == ("https://example.com/s#one",)
    assert reviewer.grant.skills == reviewer.skills
    assert claude.harness is HarnessKind.CLAUDE
    assert (person.auto, person.harness, person.capabilities) == (
        True,
        None,
        frozenset(),
    )
    assert plain.declared is Agent
    assert sure.required is True


def test_roles_declared_inside_a_function_resolve_against_its_locals() -> None:
    class Local(Agent): ...

    class Inside(AgentCollection):
        one: Local

    (role,) = agent_roles(Inside, HERE, {"Local": Local})
    assert role.declared is Local


class Wrong(AgentCollection):
    nothing: Missing  # noqa: F821  # pyright: ignore[reportUndefinedVariable]


class NotAnAgent(AgentCollection):  # pyright: ignore[reportIncompatibleVariableOverride]
    one: int


class NotAClass(AgentCollection):  # pyright: ignore[reportIncompatibleVariableOverride]
    one: list[Agent]


class Both(ClaudeCodeAgent, CodexAgent): ...


class TwoHarnesses(AgentCollection):
    one: Both


class EnvMixed(Agent, FilesEnvMixin): ...


class AgentWithEnvMixin(AgentCollection):
    one: EnvMixed


class Away(Outworlder, GoalCommandAgentMixin): ...


class OutworlderWithMixin(AgentCollection):
    one: Away


class BadPermission(Agent):
    _permission = "all"  # pyright: ignore[reportAssignmentType]


class WithBadPermission(AgentCollection):
    one: BadPermission


class BadSkills(Agent):
    _skills = ("ok", "")


class WithBadSkills(AgentCollection):
    one: BadSkills


class SkillsNotATuple(Agent):
    _skills = "one"  # pyright: ignore[reportAssignmentType]


class WithSkillsNotATuple(AgentCollection):
    one: SkillsNotATuple


class EnvAsAgent(AgentCollection):  # pyright: ignore[reportIncompatibleVariableOverride]
    one: Env


@pytest.mark.parametrize(
    ("collection", "says"),
    [
        (Wrong, "cannot be resolved"),
        (NotAnAgent, "is not an Agent"),
        (NotAClass, "is not a class"),
        (TwoHarnesses, "no agent is both"),
        (AgentWithEnvMixin, "environment's mixins"),
        (OutworlderWithMixin, "has no harness or mixins"),
        (WithBadPermission, "_permission is not a Permission"),
        (WithBadSkills, "_skills is not a tuple"),
        (WithSkillsNotATuple, "_skills is not a tuple"),
        (EnvAsAgent, "is not an Agent"),
    ],
)
def test_agent_roles_refuse(collection: type, says: str) -> None:
    with pytest.raises(FlowDefinitionError, match=says):
        roles_of(collection)


# ------------------------------------------------------------------------ env roles


class Big(Env, CPUEnvMixin, MemoryEnvMixin, GPUEnvMixin, ImageEnvMixin, ShellEnvMixin):
    _cpu_count = 16
    _memory = 1 << 30
    _gpu_count = 2
    _gpu_memory = 80 << 30
    _image = "python:3.13"


class Files(Env, FilesEnvMixin): ...


class OneCPU(Env, CPUEnvMixin):
    _cpu_count = 1


class Here(LocalEnv): ...


class Places(EnvCollection):
    big: Big
    files: NotRequired[Files]
    one: OneCPU
    here: Here
    plain: Env


def test_env_roles_read_each_key() -> None:
    big, files, one, here, plain = envs_of(Places)
    assert (big.cpu_count, big.memory, big.gpu_count, big.gpu_memory, big.image) == (
        16,
        1 << 30,
        2,
        80 << 30,
        "python:3.13",
    )
    assert big.resources is True
    assert ShellEnvMixin in big.capabilities
    assert big.grant is Grant.of(big.capabilities)
    assert (files.required, files.capabilities) == (False, frozenset({FilesEnvMixin}))
    assert files.resources is False
    assert (one.cpu_count, one.resources) == (1, False)
    assert here.auto is True
    assert (plain.auto, plain.image, plain.cpu_count) == (False, "", 0)


class NegativeCPU(Env, CPUEnvMixin):
    _cpu_count = -1


class BoolGPU(Env, GPUEnvMixin):
    _gpu_count = True


class SpacedImage(Env, ImageEnvMixin):
    _image = "two words"


class AgentMixed(Env, GoalCommandAgentMixin): ...


class WithNegativeCPU(EnvCollection):
    one: NegativeCPU


class WithBoolGPU(EnvCollection):
    one: BoolGPU


class WithSpacedImage(EnvCollection):
    one: SpacedImage


class WithAgentMixin(EnvCollection):
    one: AgentMixed


class AgentAsEnv(EnvCollection):  # pyright: ignore[reportIncompatibleVariableOverride]
    one: Agent


@pytest.mark.parametrize(
    ("collection", "says"),
    [
        (WithNegativeCPU, "_cpu_count is not a whole number"),
        (WithBoolGPU, "_gpu_count is not a whole number"),
        (WithSpacedImage, "_image is not an image"),
        (WithAgentMixin, "agent's mixins"),
        (AgentAsEnv, "is not an Env"),
    ],
)
def test_env_roles_refuse(collection: type, says: str) -> None:
    with pytest.raises(FlowDefinitionError, match=says):
        envs_of(collection)


# ---------------------------------------------------------------------- declaration


def test_a_declaration_finds_its_roles_by_name() -> None:
    roles, eroles = roles_of(Team), envs_of(Places)
    said = Declaration("f", "m:f", None, False, False, roles, eroles, FlowParams)
    assert said.agent("coder") is roles[0]
    assert said.env("files") is eroles[1]
    assert said.agent("nobody") is None
    assert said.env("nowhere") is None


# ---------------------------------------------------------------------- definition


class Nothing(FlowParams):
    pass


async def a_flow(task: str, *, agents: Any, envs: Any, params: Any, ctx: Any) -> None:
    """Does a thing.

    And more besides.
    """
    del task, agents, envs, params, ctx


async def loose(task: str, **rest: Any) -> None:
    del task, rest


async def undocumented(
    task: str, *, agents: Any, envs: Any, params: Any, ctx: Any
) -> None:
    del task, agents, envs, params, ctx


def check(fn: Callable[..., Any], **said: Any) -> tuple[str, str | None]:
    given: dict[str, Any] = {
        "agents": AgentCollection,
        "envs": EnvCollection,
        "params": Nothing,
        "name": None,
        "description": None,
    }
    given.update(said)
    return checked_definition(fn, **given)


def test_checked_definition_fills_in_the_name_and_description() -> None:
    assert check(a_flow) == ("a_flow", "Does a thing.")
    assert check(a_flow, name="x.y-z", description="") == ("x.y-z", None)
    assert check(a_flow, agents=Team, envs=Places) == ("a_flow", "Does a thing.")
    assert check(loose) == ("loose", None)
    assert check(undocumented, description="Said.") == ("undocumented", "Said.")


def sync(task: str, *, agents: Any, envs: Any, params: Any, ctx: Any) -> None:
    del task, agents, envs, params, ctx


async def no_task(*, agents: Any, envs: Any, params: Any, ctx: Any) -> None:
    del agents, envs, params, ctx


async def no_ctx(task: str, *, agents: Any, envs: Any, params: Any) -> None:
    del task, agents, envs, params


async def extra(
    task: str, *, agents: Any, envs: Any, params: Any, ctx: Any, more: int
) -> None:
    del task, agents, envs, params, ctx, more


class WithBudget(FlowParams):
    budget: int = 0


class WithBudgetAlias(FlowParams):
    spend: int = pydantic.Field(default=0, alias="budget")


class Unrelated(dict[str, Any]): ...


@pytest.mark.parametrize(
    ("fn", "said", "says"),
    [
        (sync, {}, "is an `async def`"),
        (no_task, {}, "takes the task"),
        (no_ctx, {}, "takes `ctx`"),
        (extra, {}, "`more` has no default"),
        (a_flow, {"agents": Unrelated}, "is not an AgentCollection"),
        (a_flow, {"agents": Places}, "is not an AgentCollection"),
        (a_flow, {"envs": Team}, "is not an EnvCollection"),
        (a_flow, {"params": dict}, "is not a FlowParams"),
        (a_flow, {"params": WithBudget}, "run's budget"),
        (a_flow, {"params": WithBudgetAlias}, "run's budget"),
        (a_flow, {"name": "a:b"}, "is not a flow name"),
        (a_flow, {"name": ""}, "is not a flow name"),
        (a_flow, {"name": 3}, "is not a flow name"),
    ],
)
def test_checked_definition_refuses(
    fn: Callable[..., Any], said: dict[str, Any], says: str
) -> None:
    with pytest.raises(FlowDefinitionError, match=says):
        check(fn, **said)

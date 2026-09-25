"""What a flow declares, read off its collections: one role apiece, and what each asks for.

A flow says what it needs by the types of its `AgentCollection` and `EnvCollection` keys, and
by the mixins, permission, skills and resources those types carry. That is read here, once
per collection and once per declared type, into :class:`AgentRole` and :class:`EnvRole` --
plain values the engine checks what a caller passes against, and the ways in draw pickers
from, without either of them touching an annotation again.

Nothing here resolves an annotation at import. The decorator runs as a flow's module is
imported, when the names its collections mention may not all exist yet, so a collection is
read the first time its flow is called or described, against the namespaces the decorator
captured -- which is also what lets a collection, and the types it names, be declared inside
a function.
"""

from __future__ import annotations

import inspect
import re
import sys
import typing
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ForwardRef

import typing_extensions

from hmz.flows import (
    HARNESS_AGENTS,
    Agent,
    AgentCollection,
    CPUEnvMixin,
    Env,
    EnvCollection,
    FlowDefinitionError,
    FlowParams,
    GPUEnvMixin,
    HarnessKind,
    LocalEnv,
    MemoryEnvMixin,
    Outworlder,
    Permission,
)

from .spi import AGENT_CAPABILITIES, ENV_CAPABILITIES, capabilities_of

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = [
    "AgentRole",
    "Declaration",
    "EnvRole",
    "Grant",
    "Refusal",
    "agent_roles",
    "checked_definition",
    "env_roles",
]

#: What a flow may be called: what a ref names it by after the colon, so nothing a ref
#: spells anything else with -- no `:`, `#`, `/`, `@` or whitespace.
NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\Z")

#: The permission an environment's grant carries, which nothing reads: environments are
#: granted capabilities and resources, and permission is an agent's.
_NO_PERMISSION = Permission()

#: The qualifiers a TypedDict key's annotation may be wrapped in, from either module.
_NOT_REQUIRED = {typing.NotRequired, typing_extensions.NotRequired}
_REQUIRED = {typing.Required, typing_extensions.Required}
_READ_ONLY = {typing_extensions.ReadOnly}
_ANNOTATED = {typing.Annotated, typing_extensions.Annotated}


@dataclass(frozen=True, slots=True, eq=False)
class Grant:
    """What a view of an agent or environment lets the flow holding it do.

    One per declared role type, shared by every view granted it, so that a view is a few
    pointers and a check that a caller holds what a callee asks is mostly an identity test.

    Attributes:
      capabilities: The mixins it may use.
      permission: What an agent's sessions run under; unused for an environment.
      skills: The skills an agent's sessions are given, as the role names them.
    """

    capabilities: frozenset[type]
    permission: Permission = _NO_PERMISSION
    skills: tuple[str, ...] = ()

    @classmethod
    def of(
        cls,
        capabilities: frozenset[type],
        permission: Permission = _NO_PERMISSION,
        skills: tuple[str, ...] = (),
    ) -> Grant:
        """The one grant of these capabilities, permission and skills.

        Grants are compared by identity where it counts -- a role remembers what it made of
        each grant it was offered -- so equal ones are the same object, and a run, a
        `derive` or a thousand of either make no new ones.
        """
        key = (capabilities, permission, skills)
        grant = _GRANTS.get(key)
        if grant is None:
            grant = _GRANTS[key] = cls(capabilities, permission, skills)
        return grant


#: Every grant made, by what it grants.
_GRANTS: dict[tuple[frozenset[type], Permission, tuple[str, ...]], Grant] = {}


#: Why a grant offered for a role does not meet it -- the exception to raise and what to
#: say -- or None where it does.
type Refusal = tuple[type[Exception], str] | None


@dataclass(frozen=True, slots=True, eq=False)
class AgentRole:
    """One agent role a flow declares.

    Attributes:
      name: The key in the flow's `AgentCollection`.
      declared: The type the key is annotated with.
      required: Whether the role must be filled; False for a `NotRequired` one.
      auto: Whether the runtime fills it: an `Outworlder`, which `-a` may not name.
      harness: The harness a role typed as one harness's own protocol asks for, or None.
      capabilities: The agent mixins it asks for.
      permission: What its sessions run under, and the least an agent given for it holds.
      skills: The skills its sessions are given, as it names them.
      grant: What a view of an agent filling it is granted.
    """

    name: str
    declared: type
    required: bool
    auto: bool
    harness: HarnessKind | None
    capabilities: frozenset[type]
    permission: Permission
    skills: tuple[str, ...]
    grant: Grant
    #: What a grant offered for this role came to, by the grant: None where it meets the
    #: role, else the refusal -- so that a caller passing the same kind of agent a
    #: thousand times is checked once.
    _seen: dict[Grant, Refusal] = field(
        default_factory=dict[Grant, "Refusal"], repr=False
    )


@dataclass(frozen=True, slots=True, eq=False)
class EnvRole:
    """One environment role a flow declares.

    Attributes:
      name: The key in the flow's `EnvCollection`.
      declared: The type the key is annotated with.
      required: Whether the role must be filled; False for a `NotRequired` one.
      auto: Whether the runtime fills it: a `LocalEnv`, which `-e` may not name.
      capabilities: The environment mixins it asks for.
      cpu_count: The fewest CPUs its machine may have; 0 for no requirement.
      memory: The least memory, in bytes; 0 for none.
      gpu_count: The fewest GPUs; 0 for none.
      gpu_memory: The least memory of each GPU, in bytes; 0 for none.
      grant: What a view of an environment filling it is granted.
      resources: Whether it asks anything of the machine beyond one CPU.
    """

    name: str
    declared: type
    required: bool
    auto: bool
    capabilities: frozenset[type]
    cpu_count: int
    memory: int
    gpu_count: int
    gpu_memory: int
    grant: Grant
    resources: bool
    _seen: dict[Grant, Refusal] = field(
        default_factory=dict[Grant, "Refusal"], repr=False
    )


@dataclass(frozen=True, slots=True, eq=False)
class Declaration:
    """Everything a flow declares, as a picker or a command line needs it.

    Attributes:
      name: What it is called in its module.
      ref: Its canonical ref, which is what a journal and a running tree name it by.
      description: One line saying what it does, or None.
      hidden: Whether it is left out of the lists a person picks from.
      resumable: Whether a run of it can be picked up where it left off.
      agents: Its agent roles, in the order the collection declares them.
      envs: Its environment roles, likewise.
      params: Its params model.
    """

    name: str
    ref: str
    description: str | None
    hidden: bool
    resumable: bool
    agents: tuple[AgentRole, ...]
    envs: tuple[EnvRole, ...]
    params: type[FlowParams]

    def agent(self, name: str) -> AgentRole | None:
        """The agent role of that name, or None."""
        return next((one for one in self.agents if one.name == name), None)

    def env(self, name: str) -> EnvRole | None:
        """The environment role of that name, or None."""
        return next((one for one in self.envs if one.name == name), None)


# ------------------------------------------------------------------------ at definition


def checked_definition(
    fn: Callable[..., Any],
    *,
    agents: object,
    envs: object,
    params: object,
    name: object,
    description: str | None,
) -> tuple[str, str | None]:
    """Refuses what is not a flow, cheaply enough to run as a module is imported.

    Args:
      fn: The decorated function.
      agents: What it declares as its agents.
      envs: What it declares as its environments.
      params: What it declares as its params.
      name: The name it was given, or None.
      description: The description it was given, or None.

    Returns:
      Its name and its description, defaults filled in.

    Raises:
      FlowDefinitionError: For a function that is not async or does not take what a flow
        is called with, collections that are not the flow API's, params that are not a
        `FlowParams`, and a name no ref could name.
    """
    called = getattr(fn, "__qualname__", repr(fn))
    if not inspect.iscoroutinefunction(fn):
        raise FlowDefinitionError(f"{called}: a flow is an `async def` function")
    _takes(fn, called)
    if not _derives(agents, AgentCollection):
        raise FlowDefinitionError(
            f"{called}: agents={agents!r} is not an AgentCollection subclass"
        )
    if not _derives(envs, EnvCollection):
        raise FlowDefinitionError(
            f"{called}: envs={envs!r} is not an EnvCollection subclass"
        )
    if not (isinstance(params, type) and issubclass(params, FlowParams)):
        raise FlowDefinitionError(
            f"{called}: params={params!r} is not a FlowParams subclass"
        )
    named = fn.__name__ if name is None else name
    if not isinstance(named, str) or not NAME.match(named):
        raise FlowDefinitionError(
            f"{called}: {named!r} is not a flow name: letters, digits, `_`, `.` and `-`"
        )
    if description is None:
        doc = inspect.getdoc(fn)
        description = doc.strip().splitlines()[0].strip() if doc else None
    return named, description or None


def _takes(fn: Callable[..., Any], called: str) -> None:
    """Refuses a function that cannot be called with a task and the four keywords."""
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError) as error:
        raise FlowDefinitionError(f"{called}: its signature cannot be read") from error
    kinds = inspect.Parameter
    listed = list(signature.parameters.values())
    loose = any(one.kind is kinds.VAR_KEYWORD for one in listed)
    positional = [
        one
        for one in listed
        if one.kind in (kinds.POSITIONAL_ONLY, kinds.POSITIONAL_OR_KEYWORD)
    ]
    if not positional and not any(one.kind is kinds.VAR_POSITIONAL for one in listed):
        raise FlowDefinitionError(
            f"{called}: a flow takes the task as its first argument"
        )
    by_name = {
        one.name
        for one in listed[1:]
        if one.kind in (kinds.POSITIONAL_OR_KEYWORD, kinds.KEYWORD_ONLY)
    }
    for keyword in _KEYWORDS:
        if keyword not in by_name and not loose:
            raise FlowDefinitionError(
                f"{called}: a flow takes `{keyword}` as a keyword argument"
            )
    for one in listed[1:]:
        if (
            one.kind not in (kinds.VAR_POSITIONAL, kinds.VAR_KEYWORD)
            and one.name not in _KEYWORDS
            and one.default is inspect.Parameter.empty
        ):
            raise FlowDefinitionError(
                f"{called}: `{one.name}` has no default, and a flow is called with "
                "a task, agents, envs, params and ctx alone"
            )


#: What a flow is called with, besides its task.
_KEYWORDS = ("agents", "envs", "params", "ctx")


def _derives(cls: object, base: type) -> bool:
    """Whether a class is `base` or a TypedDict declared as a subclass of it.

    A TypedDict's MRO is `dict`'s, whatever it was declared to derive from, so the
    declaration is read from `__orig_bases__` instead.
    """
    if cls is base:
        return True
    if not isinstance(cls, type) or not typing_extensions.is_typeddict(cls):
        return False
    return any(_derives(one, base) for one in getattr(cls, "__orig_bases__", ()))


# ------------------------------------------------------------------------- at first use


def agent_roles(
    collection: type, globals_: Mapping[str, Any], locals_: Mapping[str, Any]
) -> tuple[AgentRole, ...]:
    """The agent roles a collection declares.

    Raises:
      FlowDefinitionError: For a key whose annotation cannot be resolved or is not an
        `Agent`, or a type declaring what no agent can be.
    """
    roles: list[AgentRole] = []
    for name, declared, required in _keys(collection, globals_, locals_):
        if Agent not in declared.__mro__:
            raise FlowDefinitionError(
                f"{collection.__qualname__}.{name}: {declared!r} is not an Agent"
            )
        auto, harness, capabilities, permission, skills, grant = _agent_type(declared)
        roles.append(
            AgentRole(
                name=name,
                declared=declared,
                required=required,
                auto=auto,
                harness=harness,
                capabilities=capabilities,
                permission=permission,
                skills=skills,
                grant=grant,
            )
        )
    return tuple(roles)


def env_roles(
    collection: type, globals_: Mapping[str, Any], locals_: Mapping[str, Any]
) -> tuple[EnvRole, ...]:
    """The environment roles a collection declares.

    Raises:
      FlowDefinitionError: For a key whose annotation cannot be resolved or is not an
        `Env`, or a type declaring what no environment can be.
    """
    roles: list[EnvRole] = []
    for name, declared, required in _keys(collection, globals_, locals_):
        if Env not in declared.__mro__:
            raise FlowDefinitionError(
                f"{collection.__qualname__}.{name}: {declared!r} is not an Env"
            )
        auto, capabilities, cpus, memory, gpus, gpu_memory, grant = _env_type(declared)
        roles.append(
            EnvRole(
                name=name,
                declared=declared,
                required=required,
                auto=auto,
                capabilities=capabilities,
                cpu_count=cpus,
                memory=memory,
                gpu_count=gpus,
                gpu_memory=gpu_memory,
                grant=grant,
                resources=cpus > 1 or memory > 0 or gpus > 0 or gpu_memory > 0,
            )
        )
    return tuple(roles)


def _keys(
    collection: type, globals_: Mapping[str, Any], locals_: Mapping[str, Any]
) -> list[tuple[str, type, bool]]:
    """Each key of a TypedDict, the type it holds, and whether it is required.

    Read from the annotations rather than `__required_keys__` alone: under `from
    __future__ import annotations` a `NotRequired[...]` is a string the class could not
    look inside, and is only found by resolving it.
    """
    annotations: dict[str, Any] = dict(getattr(collection, "__annotations__", {}))
    required_keys: frozenset[str] = getattr(
        collection, "__required_keys__", frozenset()
    )
    keys: list[tuple[str, type, bool]] = []
    for name, said in annotations.items():
        required = name in required_keys
        declared: Any = said
        for _ in range(32):
            if isinstance(declared, (str, ForwardRef)):
                declared = _resolved(collection, name, declared, globals_, locals_)
                continue
            origin = typing.get_origin(declared)
            if origin in _NOT_REQUIRED:
                required = False
            elif origin in _REQUIRED:
                required = True
            elif origin not in _READ_ONLY and origin not in _ANNOTATED:
                break
            declared = (
                declared.__origin__
                if origin in _ANNOTATED
                else typing.get_args(declared)[0]
            )
        if not isinstance(declared, type):
            raise FlowDefinitionError(
                f"{collection.__qualname__}.{name}: {declared!r} is not a class; a role "
                "is typed as one agent or environment type"
            )
        keys.append((name, declared, required))
    return keys


def _resolved(
    collection: type,
    name: str,
    said: str | ForwardRef,
    globals_: Mapping[str, Any],
    locals_: Mapping[str, Any],
) -> Any:
    """What one annotation written as a string names.

    In the module the collection's annotation was written in, with the namespace the flow
    was decorated in in front of it -- which is where a collection declared inside a
    function finds the types declared beside it.
    """
    if isinstance(said, ForwardRef):
        text = said.__forward_arg__
        module = said.__forward_module__
    else:
        text, module = said, None
    owner = sys.modules.get(module or collection.__module__)
    namespace = dict(owner.__dict__) if owner is not None else {}
    namespace.update(globals_)
    try:
        return eval(text, namespace, dict(locals_))  # noqa: S307 -- an annotation is code
    except Exception as error:
        raise FlowDefinitionError(
            f"{collection.__qualname__}.{name}: {text!r} cannot be resolved: {error}"
        ) from error


#: What each declared agent type comes to, read once per type.
_AGENT_TYPES: dict[
    type,
    tuple[
        bool,
        HarnessKind | None,
        frozenset[type],
        Permission,
        tuple[str, ...],
        Grant,
    ],
] = {}

#: The same for environment types.
_ENV_TYPES: dict[type, tuple[bool, frozenset[type], int, int, int, int, Grant]] = {}

#: Each harness's own protocol, which a role typed as it asks for. `Agent` itself is the
#: protocol of a CLI added by hand, and asks for nothing.
_HARNESSES = {
    protocol: kind for kind, protocol in HARNESS_AGENTS.items() if protocol is not Agent
}


def _agent_type(
    declared: type,
) -> tuple[
    bool, HarnessKind | None, frozenset[type], Permission, tuple[str, ...], Grant
]:
    """What one agent type asks for, read off its bases and class attributes."""
    known = _AGENT_TYPES.get(declared)
    if known is not None:
        return known
    where = declared.__qualname__
    capabilities = capabilities_of(declared)
    if capabilities - AGENT_CAPABILITIES:
        raise FlowDefinitionError(
            f"{where}: an agent cannot be declared with an environment's mixins"
        )
    harnesses = [_HARNESSES[one] for one in declared.__mro__ if one in _HARNESSES]
    if len(harnesses) > 1:
        raise FlowDefinitionError(
            f"{where}: no agent is both {' and '.join(harnesses)}"
        )
    auto = Outworlder in declared.__mro__
    if auto and (harnesses or capabilities):
        raise FlowDefinitionError(
            f"{where}: an Outworlder is whoever is outside the run, and has no harness "
            "or mixins"
        )
    permission: object = getattr(declared, "_permission", Permission())
    if not isinstance(permission, Permission):
        raise FlowDefinitionError(f"{where}._permission is not a Permission")
    skills: object = getattr(declared, "_skills", ())
    if not isinstance(skills, (tuple, list)) or not all(
        isinstance(one, str) and one.strip()
        for one in skills  # pyright: ignore[reportUnknownVariableType]
    ):
        raise FlowDefinitionError(f"{where}._skills is not a tuple of skill names")
    named = tuple(str(one) for one in skills)  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    known = (
        auto,
        harnesses[0] if harnesses else None,
        capabilities,
        permission,
        named,
        Grant.of(capabilities, permission, named),
    )
    _AGENT_TYPES[declared] = known
    return known


def _env_type(
    declared: type,
) -> tuple[bool, frozenset[type], int, int, int, int, Grant]:
    """What one environment type asks for, read off its bases and class attributes."""
    known = _ENV_TYPES.get(declared)
    if known is not None:
        return known
    where = declared.__qualname__
    capabilities = capabilities_of(declared)
    if capabilities - ENV_CAPABILITIES:
        raise FlowDefinitionError(
            f"{where}: an environment cannot be declared with an agent's mixins"
        )
    mro = declared.__mro__
    amounts: list[int] = []
    for mixin, attributes in (
        (CPUEnvMixin, ("_cpu_count",)),
        (MemoryEnvMixin, ("_memory",)),
        (GPUEnvMixin, ("_gpu_count", "_gpu_memory")),
    ):
        for attribute in attributes:
            amount: object = getattr(declared, attribute, 0) if mixin in mro else 0
            if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
                raise FlowDefinitionError(
                    f"{where}.{attribute} is not a whole number of at least 0"
                )
            amounts.append(amount)
    cpus, memory, gpus, gpu_memory = amounts
    known = (
        LocalEnv in mro,
        capabilities,
        cpus,
        memory,
        gpus,
        gpu_memory,
        Grant.of(capabilities),
    )
    _ENV_TYPES[declared] = known
    return known

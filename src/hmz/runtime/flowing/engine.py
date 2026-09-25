"""The flow engine: what `flow`, `load` and `Outworlder.new` call, and what runs a flow.

A run is a tree of flow calls. :func:`run_flow` starts one over drivers; a flow calling
another -- `await load(":review")(task, agents=..., envs=..., params=...)` -- adds a call
under the one making it. Each call is a :class:`Call`, which is also the `ctx` its flow is
handed: what it spent, what it may spend, what it keeps if it is resumable.

What a call costs is the point of how this is written. A flow calling a flow is the inner loop
of every large flow there is, so a call does no filesystem work, starts no task, and adds two
frames to the stack -- :meth:`FlowImpl.__call__` and the flow itself, awaited directly. What
the callee declared is read once per flow, a caller handing on what it holds is checked once
per kind of agent, and whatever a call needs only sometimes -- a deadline of its own, things to
clean up, a journal -- it allocates only then. The current call is a context variable, so a
gather of calls is a tree of them, each branch in its own task.

What a call is handed is views: see :mod:`viewing`. What it may spend is a budget: its own,
if the caller gave it one, under what remains of every budget above it. Spending rolls up to
every call above as it is reported, from whichever thread reports it; `duration` is a
deadline, enforced by a timer that stops the calls under it, letting a turn under way finish
first where the budget is graceful. A run whose flow is resumable writes a journal (see
:mod:`journaling`), which is what a resumed run's calls pick their state back up from.
"""

from __future__ import annotations

# A call and the views it hands out are two halves of one object declared in two files --
# `viewing` for what a flow sees, this for what the engine keeps -- and each reaches into
# the other's underscored slots, which the underscore keeps from flows rather than from them.
# pyright: reportPrivateUsage=false
import asyncio
import datetime
import json
import logging
import math
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

import pydantic
import pydantic_core

from hmz.flows import (
    Budget,
    CapabilityMissing,
    CostExceeded,
    DurationExceeded,
    EnvBackendKind,
    FlowCancelled,
    FlowDefinitionError,
    FlowDepthExceeded,
    FlowParams,
    FlowRuntimeError,
    HarnessMismatch,
    MissingRole,
    OutputTokensExceeded,
    ParamsError,
    PermissionTooNarrow,
    RequirementError,
    ResourceUnmet,
    Usage,
)

from .declaring import (
    AgentRole,
    Declaration,
    EnvRole,
    Grant,
    Refusal,
    agent_roles,
    checked_definition,
    env_roles,
)
from .journaling import FlowStateImpl, Journal, Past, digest
from .viewing import (
    CALLING,
    AgentView,
    EnvView,
    Made,
    OutworlderView,
    Source,
    limits_of,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Reversible

    from hmz.flows import (
        AgentCollection,
        EnvCollection,
        Flow,
        FlowFn,
        Outworlder,
    )

    from .loading import FlowModule, Remote
    from .spi import (
        AgentDriver,
        EnvDriver,
        Limits,
        OutworlderDriver,
        SessionHandle,
        Skill,
    )
    from .viewing import Opened, Releasable

__all__ = [
    "DEPTH",
    "Call",
    "FlowImpl",
    "LiveCall",
    "Recorder",
    "Run",
    "current",
    "define_flow",
    "full_view",
    "load_flow",
    "new_outworlder",
    "run_flow",
    "running",
]

log = logging.getLogger(__name__)

#: How deep flows may call flows before a call is refused with `FlowDepthExceeded`.
DEPTH = 64

#: How long a call's cleanup -- closing sessions, removing temporary copies -- may take.
REAP = 30.0

_INF = math.inf

#: The backend a `LocalEnv` role may be given an environment on.
_LOCAL = EnvBackendKind.LOCAL

#: What a role's memo answers for a grant it has not been offered yet.
_UNSEEN: Any = object()

#: Every run going now, for :func:`running`.
_RUNS: set[Run] = set()


def current() -> Call | None:
    """The flow call running here, or None outside every run."""
    return CALLING.get()


# -------------------------------------------------------------------------------- flows


class FlowImpl:
    """A flow, as :func:`hmz.flows.flow` makes one: its function and what it declares.

    Answers to :class:`hmz.flows.Flow`. Beyond it, what the runtime reads: `name`, `hidden`,
    its canonical `ref`, and :meth:`describe`.

    Attributes:
      fn: The decorated function.
      name: What it is called in its module.
      description: One line saying what it does, or None.
      hidden: Whether it is left out of the lists a person picks from.
      resumable: Whether a run of it can be picked up where it left off.
      ref: What a journal and the running tree call it: `<module>:<name>`, the module being
        the flow's directory for a flow in a flowverse.
      globals: The namespace it was defined in.
      locals: The local namespace it was defined in, which is `globals` at a module's top.
      home: The flow module it was loaded as part of, or None.
    """

    __slots__ = (
        "_agents",
        "_envs",
        "_eroles",
        "_full",
        "_order",
        "_params",
        "_roles",
        "_skilled",
        "description",
        "fn",
        "globals",
        "hidden",
        "home",
        "locals",
        "name",
        "ref",
        "resumable",
    )

    def __init__(
        self,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        *,
        agents: type,
        envs: type,
        params: type[FlowParams],
        name: str,
        description: str | None,
        hidden: bool,
        resumable: bool,
        globals_: Mapping[str, Any],
        locals_: Mapping[str, Any],
    ) -> None:
        """A flow, checked by :func:`define_flow`."""
        self.fn = fn
        self._agents = agents
        self._envs = envs
        self._params = params
        self.name = name
        self.description = description
        self.hidden = hidden
        self.resumable = resumable
        self.globals = globals_
        self.locals = locals_
        self.ref = f"{globals_.get('__name__', '?')}:{name}"
        self.home: FlowModule | None = None
        self._full = False
        self._roles: tuple[AgentRole, ...] | None = None
        self._eroles: tuple[EnvRole, ...] = ()
        self._skilled: tuple[AgentRole, ...] = ()
        self._order: tuple[tuple[str, ...], tuple[str, ...]] = ((), ())

    def __repr__(self) -> str:
        return f"<flow {self.ref}>"

    @property
    def expected_agents(self) -> type[AgentCollection]:
        return self._agents

    @property
    def expected_envs(self) -> type[EnvCollection]:
        return self._envs

    @property
    def expected_params(self) -> type[FlowParams]:
        return self._params

    def describe(self) -> Declaration:
        """Everything it declares, resolved.

        Raises:
          FlowDefinitionError: If a collection names what is not an agent or environment.
        """
        roles, eroles = self.declared()
        return Declaration(
            name=self.name,
            ref=self.ref,
            description=self.description,
            hidden=self.hidden,
            resumable=self.resumable,
            agents=roles,
            envs=eroles,
            params=self._params,
        )

    def declared(self) -> tuple[tuple[AgentRole, ...], tuple[EnvRole, ...]]:
        """Its agent and environment roles, resolved the first time they are asked for.

        Raises:
          FlowDefinitionError: If a collection names what is not an agent or environment.
        """
        roles = self._roles
        if roles is None:
            eroles = env_roles(self._envs, self.globals, self.locals)
            roles = agent_roles(self._agents, self.globals, self.locals)
            self._eroles = eroles
            self._skilled = tuple(one for one in roles if one.skills and not one.auto)
            self._order = (
                tuple(sorted(one.name for one in roles)),
                tuple(sorted(one.name for one in eroles)),
            )
            self._roles = roles
        return roles, self._eroles

    def params_of(self, params: object) -> FlowParams:
        """Its params, from an instance, another model, or a mapping of values.

        A mapping's string values -- what `-p` gives -- are read as the fields' types, and
        as JSON where that is what reads them.

        Raises:
          ParamsError: If they do not validate.
        """
        model = self._params
        if isinstance(params, model):
            return params
        try:
            if isinstance(params, pydantic.BaseModel):
                return model.model_validate(params.model_dump())
            if isinstance(params, Mapping):
                said = dict(cast("Mapping[str, Any]", params))
                try:
                    return model.model_validate(said)
                except pydantic.ValidationError as first:
                    failed = {
                        str(one["loc"][0]) for one in first.errors() if one["loc"]
                    }
                    read = {
                        key: _json_or_text(value) if key in failed else value
                        for key, value in said.items()
                    }
                    if read == said:
                        raise
                    return model.model_validate(read)
        except pydantic.ValidationError as error:
            raise ParamsError(f"{self.ref}: {error}") from error
        raise ParamsError(
            f"{self.ref}: params={params!r} is not a {model.__name__} or a mapping"
        )

    async def __call__(
        self,
        task: str,
        *,
        agents: Mapping[str, Any],
        envs: Mapping[str, Any],
        params: FlowParams,
        budget: Budget | None = None,
    ) -> Any:
        parent = CALLING.get()
        if parent is None:
            raise FlowRuntimeError(
                f"{self.ref}: a flow is called from inside a run; start one with run_flow"
            )
        above: Call | None = parent
        while above is not None:
            if above.ended:
                raise FlowCancelled(
                    f"{self.ref}: {'the run' if above.impl is None else above.ref} "
                    "has ended"
                )
            above = above.parent
        depth = parent.depth + 1
        if depth > DEPTH:
            raise FlowDepthExceeded(
                f"{self.ref}: flows are called {depth} deep, and {DEPTH} is the most"
            )
        roles = self._roles
        if roles is None:
            roles = self.declared()[0]
        if type(params) is not self._params:
            params = self.params_of(params)
        if budget is not None and type(budget) is not Budget:
            raise TypeError(f"{self.ref}: budget={budget!r} is not a Budget")
        run = parent.run
        node = Call(run, parent, self, depth, budget, task)
        full = self._full
        # What follows is `_agent` and `_env` for the case every call in a large flow is: a
        # view the run handed out, of a kind already checked against this role -- written
        # out here, since a function call per role is a fifth of what a call costs.
        views: dict[str, Any] = {}
        for role in roles:
            name = role.name
            given = agents.get(name)
            if type(given) is AgentView and not role.auto and role.harness is None:
                grant = given._grant
                if grant is role.grant or role._seen.get(grant, _UNSEEN) is None:
                    views[name] = AgentView(
                        given._driver, grant if full else role.grant, node, name
                    )
                    continue
            if given is None:
                if role.auto:
                    views[name] = OutworlderView(run.person, node, name)
                elif role.required:
                    raise MissingRole(f"{self.ref}: no agent was given for {name!r}")
                continue
            views[name] = _agent(role, given, node, self, full=full)
        env_views: dict[str, EnvView] = {}
        for role in self._eroles:
            name = role.name
            given = envs.get(name)
            if (
                type(given) is EnvView
                and not role.resources
                and (not role.auto or given._driver.backend == _LOCAL)
            ):
                grant = given._grant
                if grant is role.grant or role._seen.get(grant, _UNSEEN) is None:
                    env_views[name] = EnvView(
                        given._driver, role.grant, node, name, given._chain
                    )
                    continue
            if given is None:
                if role.auto:
                    env_views[name] = run.here(role, node, self)
                elif role.required:
                    raise MissingRole(
                        f"{self.ref}: no environment was given for {name!r}"
                    )
                continue
            env_views[name] = _env(role, given, node, self)
        if self._skilled:
            await self._bring(run)
        if run.journal is not None:
            self._journaled(node, parent, task, views, env_views, params)
        elif self.resumable:
            node.state = FlowStateImpl({}, None, 0)
        if run.recorder is not None:
            run.recorder.entered(node.record())
        live = run.live
        live[node] = None
        parent.live += 1
        if budget is not None and budget.duration is not None:
            node.arm(budget)
        failed: BaseException | None = None
        token = CALLING.set(node)
        try:
            return await self.fn(
                task, agents=views, envs=env_views, params=params, ctx=node
            )
        except BaseException as error:
            failed = error
            clock = node.clock
            if clock is not None and type(error) is asyncio.CancelledError:
                expired = clock.settle()
                if expired is not None:
                    failed = expired
                    raise expired from None
            raise
        finally:
            CALLING.reset(token)
            node.ended = True
            del live[node]
            if node.clock is not None:
                node.clock.stop()
            if run.journal is not None:
                run.journal.end(node.jid, ok=failed is None)
            if run.recorder is not None:
                run.recorder.left(node.record(), failed)
            left = node.live - 1
            node.live = left
            if left == 0:
                if node.res is None:
                    left = parent.live - 1
                    parent.live = left
                    if left == 0 and parent.ended and parent.impl is not None:
                        await _finish(parent)
                else:
                    await _finish(node)

    async def _bring(self, run: Run) -> None:
        """Finds or fetches the skills its roles name, once per run."""
        for role in self._skilled:
            key = (self, role.name)
            if key in run.skills:
                continue
            bringing = run.bringing.get(key)
            if bringing is None:
                bringing = run.bringing[key] = asyncio.ensure_future(
                    asyncio.to_thread(_skills_for, self, role)
                )
            run.skills[key] = await asyncio.shield(bringing)

    def _journaled(
        self,
        node: Call,
        parent: Call,
        task: str,
        views: dict[str, Any],
        env_views: dict[str, EnvView],
        params: FlowParams,
    ) -> None:
        """Writes a call into the run's journal, picking up an earlier one it matches."""
        run = node.run
        journal = run.journal
        assert journal is not None  # noqa: S101 -- asked by the caller
        agent_order, env_order = self._order
        roles = [
            f"{name}={run.spec_of(views[name])}"
            for name in agent_order
            if name in views
        ]
        roles.extend(
            f"{name}={env_views[name].chain}" for name in env_order if name in env_views
        )
        said = digest(
            self.ref, task, roles, params.__pydantic_serializer__.to_json(params)
        )
        seqs = parent.seqs
        if seqs is None:
            seqs = parent.seqs = {}
        seq = seqs.get(said, 0)
        seqs[said] = seq + 1
        past = run.past
        kept = None
        if past is not None:
            if parent.impl is None:
                kept = past.calls.get(past.root) if past.root is not None else None
            elif parent.old:
                kept = past.claim(parent.old, said, seq)
        if kept is not None:
            node.jid = node.old = kept.id
            node.resumed = True
            held = dict(kept.state)
        else:
            run.ids += 1
            node.jid = run.ids
            held = {}
            journal.call(
                node.jid, parent.jid, said, seq, pydantic_core.to_json(self.ref)
            )
        if self.resumable:
            node.state = FlowStateImpl(held, journal, node.jid)


def _json_or_text(value: object) -> object:
    """A string that reads as JSON, read; anything else as it is."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except ValueError:
        return value


def _agent(
    role: AgentRole, given: object, node: Call, flow: FlowImpl, *, full: bool
) -> AgentView | OutworlderView:
    """The view of what a caller passed for an agent role, narrowed to what it declares.

    Raises:
      RequirementError: The leaf for what the agent given lacks.
    """
    kind = type(given)
    if kind is AgentView:
        view: AgentView = given  # pyright: ignore[reportAssignmentType]
        if role.auto:
            raise CapabilityMissing(
                f"{flow.ref}: {role.name!r} is an Outworlder, and {view!r} is an agent"
            )
        driver = view._driver
        if role.harness is not None and driver.harness != role.harness:
            raise HarnessMismatch(
                f"{flow.ref}: {role.name!r} is {role.harness}, and the agent given is "
                f"{driver.harness}"
            )
        grant = view._grant
        if grant is not role.grant:
            seen = role._seen
            refusal = seen.get(grant, _UNSEEN)
            if refusal is _UNSEEN:
                refusal = seen[grant] = _agent_refusal(role, grant)
            if refusal is not None:
                raise refusal[0](f"{flow.ref}: {role.name!r} {refusal[1]}")
        return AgentView(driver, grant if full else role.grant, node, role.name)
    if kind is OutworlderView:
        person: OutworlderView = given  # pyright: ignore[reportAssignmentType]
        if not role.auto and (role.capabilities or role.harness is not None):
            raise CapabilityMissing(
                f"{flow.ref}: {role.name!r} asks for what no outworlder can do"
            )
        return OutworlderView(person._source, node, role.name)
    raise RequirementError(
        f"{flow.ref}: {role.name!r} was given {given!r}, which is not an agent the run "
        "handed out"
    )


def _agent_refusal(role: AgentRole, grant: Grant) -> Refusal:
    lacking = role.capabilities - grant.capabilities
    if lacking:
        names = ", ".join(sorted(one.__name__ for one in lacking))
        return (
            CapabilityMissing,
            f"needs {names}, which the agent given was not granted",
        )
    if not grant.permission.covers(role.permission):
        return (
            PermissionTooNarrow,
            f"needs {role.permission}, and the agent given holds {grant.permission}",
        )
    return None


def _env(role: EnvRole, given: object, node: Call, flow: FlowImpl) -> EnvView:
    """The view of what a caller passed for an environment role, narrowed likewise.

    Raises:
      RequirementError: The leaf for what the environment given lacks.
    """
    if type(given) is not EnvView:
        raise RequirementError(
            f"{flow.ref}: {role.name!r} was given {given!r}, which is not an environment "
            "the run handed out"
        )
    driver = given._driver
    if role.auto and driver.backend != _LOCAL:
        raise CapabilityMissing(
            f"{flow.ref}: {role.name!r} is a LocalEnv, and the environment given is "
            f"{driver.backend}@{driver.provider}{driver.workdir}, which is not this machine"
        )
    return _narrowed(
        role,
        given._driver,
        given._grant,
        given._chain,
        node,
        flow,
    )


def _narrowed(
    role: EnvRole,
    driver: EnvDriver,
    grant: Grant,
    chain: str,
    node: Call,
    flow: FlowImpl,
) -> EnvView:
    """A view of an environment held under `grant`, for a role that declared less.

    Raises:
      RequirementError: The leaf for what the environment lacks.
    """
    if grant is not role.grant:
        seen = role._seen
        refusal = seen.get(grant, _UNSEEN)
        if refusal is _UNSEEN:
            lacking = role.capabilities - grant.capabilities
            refusal = seen[grant] = (
                (
                    CapabilityMissing,
                    "needs "
                    + ", ".join(sorted(one.__name__ for one in lacking))
                    + ", which the environment given was not granted",
                )
                if lacking
                else None
            )
        if refusal is not None:
            raise refusal[0](f"{flow.ref}: {role.name!r} {refusal[1]}")
    if role.resources:
        _meets(role, driver, flow)
    return EnvView(driver, role.grant, node, role.name, chain)


def _meets(role: EnvRole, driver: EnvDriver, flow: FlowImpl) -> None:
    """Refuses a machine smaller than a role asks for.

    Raises:
      ResourceUnmet: If it is.
    """
    for asked, has, what in (
        (role.cpu_count, driver.cpu_count, "CPUs"),
        (role.memory, driver.memory, "bytes of memory"),
        (role.gpu_count, driver.gpu_count, "GPUs"),
        (role.gpu_memory, driver.gpu_memory, "bytes of memory per GPU"),
    ):
        if has < asked:
            raise ResourceUnmet(
                f"{flow.ref}: {role.name!r} needs {asked} {what}, and the environment "
                f"given has {has}"
            )


def _skills_for(flow: FlowImpl, role: AgentRole) -> dict[str, tuple[Skill, ...]]:
    """The skills one role names, found in its flow's `skills/` or fetched.

    Returns:
      What each name the role gives came to: one skill for a name, and for a URL every
      skill it brought -- so that an agent derived with fewer of them gets just theirs.

    Raises:
      FlowDefinitionError: For a skill the flow does not have, or cannot fetch.
    """
    from .skills import brought
    from .spi import Skill

    root = _root_of(flow)
    urls = [one for one in role.skills if "#" in one or "://" in one]
    try:
        found = brought(root or "", urls)
    except OSError as error:
        raise FlowDefinitionError(
            f"{flow.ref}: {role.name!r} names a skill that cannot be fetched: {error}"
        ) from error
    own = {one.name: one for one in found if one.whose == "this flow"}
    skills: dict[str, tuple[Skill, ...]] = {}
    for said in role.skills:
        if said in urls:
            skills[said] = tuple(
                Skill(one.name, one.at) for one in found if one.whose == said
            )
            continue
        one = own.get(said)
        if one is None:
            raise FlowDefinitionError(
                f"{flow.ref}: {role.name!r} names the skill {said!r}, and "
                f"{root / 'skills' if root else 'a flow that is one file'} has none of it"
            )
        skills[said] = (Skill(one.name, one.at),)
    return skills


def _root_of(flow: FlowImpl) -> Path | None:
    """The directory a flow was defined in, which is where its `skills/` is."""
    from .loading import home_of

    home = flow.home or home_of(flow)
    if home is not None:
        return home.at if home.at.is_dir() else None
    made = Path(flow.fn.__code__.co_filename)
    return made.parent if made.name == "__init__.py" else None


# -------------------------------------------------------------------------------- calls


class _Clock:
    """A call's own deadline: the timer, and the task it stops when the timer goes.

    Stopping is cancelling the task the call runs in, which reaches every call under it
    that it is waiting on -- awaited, gathered, or in a task group -- and is turned back
    into `DurationExceeded` where it leaves the call, as `asyncio.timeout` does. A graceful
    budget lets the turns under way under the call finish first.
    """

    __slots__ = (
        "cancelling",
        "expired",
        "fired",
        "graceful",
        "handle",
        "inflight",
        "node",
        "task",
    )

    def __init__(
        self, node: Call, task: asyncio.Task[Any], delay: float, *, graceful: bool
    ) -> None:
        self.node = node
        self.task = task
        self.cancelling = task.cancelling()
        self.graceful = graceful
        self.inflight = 0
        self.expired = False
        self.fired = False
        self.handle: asyncio.Handle | None = asyncio.get_running_loop().call_later(
            max(delay, 0.0), self.expire
        )

    def expire(self) -> None:
        """The deadline has come: the call is stopped, after its turns if it is graceful."""
        self.handle = None
        if self.node.ended or self.expired:
            return
        self.expired = True
        if not self.graceful or self.inflight == 0:
            self._fire()

    def turned(self, delta: int) -> None:
        """A turn under the call started or ended."""
        self.inflight += delta
        if (
            self.expired
            and self.inflight == 0
            and not self.fired
            and self.handle is None
        ):
            # From the loop rather than from here: the turn that ended may be the call's
            # own, in its task, and a flow returning without awaiting again would carry a
            # cancel sent now out to whoever called it.
            self.handle = asyncio.get_running_loop().call_soon(self._fire)

    def _fire(self) -> None:
        self.handle = None
        if not self.node.ended:
            self.fired = True
            self.task.cancel(f"{self.node.ref}: its budget's duration is spent")

    def settle(self) -> DurationExceeded | None:
        """What a `CancelledError` leaving the call is: the deadline's, or somebody else's."""
        if not self.fired:
            return None
        self.fired = False
        if self.task.uncancel() > self.cancelling:
            return None
        return DurationExceeded(f"{self.node.ref}: its budget's duration is spent")

    def stop(self) -> None:
        """The call is over: the timer goes, and a cancel it sent that nobody saw is taken back."""
        if self.handle is not None:
            self.handle.cancel()
            self.handle = None
        if self.fired:
            self.fired = False
            self.task.uncancel()


class Call:
    """One flow call: its place in the run, what it spent, and what it keeps.

    Answers to :class:`hmz.flows.FlowContext`, and is the `ctx` its flow is handed.

    Attributes:
      run: The run it is part of.
      parent: The call that made it; for the call at the top of a run, the run's own.
      impl: The flow called; None for the run's own call above the top.
      depth: How many flows deep: 1 for the flow a run was started with.
      task: What it was called to do.
      since: When it started, on the monotonic clock.
      deadline: When its budget's duration is spent, its own or any above it.
      state: What it keeps, for a resumable flow.
    """

    __slots__ = (
        "_record",
        "clock",
        "cost",
        "deadline",
        "depth",
        "ended",
        "impl",
        "jid",
        "live",
        "old",
        "own",
        "parent",
        "res",
        "resumed",
        "run",
        "secs",
        "seqs",
        "since",
        "state",
        "task",
        "tokens",
    )

    def __init__(
        self,
        run: Run,
        parent: Call | None,
        flow: FlowImpl | None,
        depth: int,
        own: Budget | None,
        task: str = "",
    ) -> None:
        """A call about to start."""
        self.run = run
        self.parent = parent
        self.impl = flow
        self.depth = depth
        self.own = own
        self.task = task
        self.since = time.monotonic()
        self.deadline = _INF if parent is None else parent.deadline
        self.cost = 0.0
        self.tokens = 0
        self.secs = 0.0
        self.live = 1
        self.ended = False
        self.jid = 0
        self.old = 0
        self.resumed = False
        self.state: FlowStateImpl | None = None
        self.clock: _Clock | None = None
        self.res: dict[int, Releasable] | None = None
        self.seqs: dict[str, int] | None = None
        self._record: LiveCall | None = None

    def __repr__(self) -> str:
        return f"<call of {self.ref} at depth {self.depth}>"

    @property
    def ref(self) -> str:
        """The canonical ref of the flow called, or "" for a run's own call."""
        return "" if self.impl is None else self.impl.ref

    # ------------------------------------------------------------------ FlowContext

    @property
    def flow(self) -> FlowImpl:
        impl = self.impl
        if impl is None:
            raise FlowRuntimeError("the run's own call is no flow's")
        return impl

    @property
    def budget(self) -> Budget:
        cost = tokens = _INF
        graceful = True
        node: Call | None = self
        with self.run.lock:
            while node is not None:
                own = node.own
                if own is not None:
                    if own.cost is not None:
                        cost = min(cost, own.cost - node.cost + self.cost)
                    if own.output_tokens is not None:
                        tokens = min(
                            tokens, own.output_tokens - node.tokens + self.tokens
                        )
                    if not own.graceful:
                        graceful = False
                node = node.parent
        deadline = self.deadline
        duration = (
            None
            if deadline == _INF
            else datetime.timedelta(seconds=max(deadline - self.since, 0.0))
        )
        return Budget.model_construct(
            duration=duration,
            cost=None if cost == _INF and (tokens != _INF or duration) else cost,
            output_tokens=None if tokens == _INF else max(int(tokens), 0),
            graceful=graceful,
        )

    @property
    def usage(self) -> Usage:
        with self.run.lock:
            cost, tokens, secs = self.cost, self.tokens, self.secs
        return Usage.model_construct(
            duration=datetime.timedelta(seconds=secs), cost=cost, output_tokens=tokens
        )

    # --------------------------------------------------------------- what views ask

    def check(self) -> None:
        """Refuses anything more of a call whose caller -- or run -- is over.

        Raises:
          FlowCancelled: If it is.
        """
        node: Call | None = self
        while node is not None:
            if node.ended:
                raise FlowCancelled(
                    f"{self.ref}: {'the run' if node.impl is None else node.ref} "
                    "has ended"
                )
            node = node.parent

    def limits(self, budget: Budget | None) -> tuple[Limits, float | None]:
        """What a turn of this call may spend now, every budget over it taken together.

        Returns:
          The limits its driver is handed, and the deadline the engine holds the turn to
          itself -- a hard one due after the graceful deadline the limits carry, which lets
          the turn run on past it -- or None where the driver's limits do.

        Raises:
          FlowCancelled: If the call's caller, or the run, is over.
          BudgetExceeded: The leaf for a budget over it that is spent.
        """
        # Each limit is the least any budget over the turn leaves, and the turn is hard --
        # stopped mid-turn when a limit is reached -- where a budget that sets one of them
        # is: a hard budget stays hard under a graceful one, and the other way round.
        cost = tokens = until = cut = _INF
        cost_hard = tokens_hard = until_hard = False
        node: Call | None = self
        while node is not None:
            if node.ended:
                self.check()
            own = node.own
            if own is not None:
                hard = not own.graceful
                if own.cost is not None:
                    left = own.cost - node.cost
                    if left < cost or (hard and left == cost):
                        cost, cost_hard = left, hard
                if own.output_tokens is not None:
                    left = own.output_tokens - node.tokens
                    if left < tokens or (hard and left == tokens):
                        tokens, tokens_hard = left, hard
                if own.duration is not None:
                    ends = node.since + own.duration.total_seconds()
                    if ends < until or (hard and ends == until):
                        until, until_hard = ends, hard
                    if hard and ends < cut:
                        cut = ends
            node = node.parent
        now = time.monotonic()
        deadline = self.deadline
        if now >= deadline:
            raise DurationExceeded(f"{self.ref}: its budget's duration is spent")
        if cost <= 0:
            raise CostExceeded(f"{self.ref}: its budget's cost is spent")
        if tokens <= 0:
            raise OutputTokensExceeded(
                f"{self.ref}: its budget's output tokens are spent"
            )
        if budget is not None:
            hard = not budget.graceful
            if budget.cost is not None and budget.cost <= cost:
                cost, cost_hard = (
                    budget.cost,
                    hard or (cost_hard and budget.cost == cost),
                )
            if budget.output_tokens is not None and budget.output_tokens <= tokens:
                tokens, tokens_hard = (
                    budget.output_tokens,
                    hard or (tokens_hard and budget.output_tokens == tokens),
                )
            if budget.duration is not None:
                ends = now + budget.duration.total_seconds()
                if ends <= deadline:
                    deadline, until_hard = (
                        ends,
                        hard or (until_hard and ends == deadline),
                    )
                if hard and ends < cut:
                    cut = ends
        # `Limits` carry one deadline, and one `graceful` for every limit. A graceful soonest
        # deadline lets the turn run on past it, which a driver told a hard limit would not:
        # one held to a hard cost or token limit is told the hard deadline instead, if any,
        # and one held to none is held to the hard deadline by the engine.
        bites = (cost_hard and cost != _INF) or (tokens_hard and tokens != _INF)
        if deadline != _INF and not until_hard:
            if bites:
                return limits_of(cost, tokens, cut, graceful=False), None
            return (
                limits_of(cost, tokens, deadline, graceful=True),
                None if cut == _INF else cut,
            )
        return limits_of(
            cost, tokens, deadline, graceful=not (bites or deadline != _INF)
        ), None

    def turning(self, delta: int) -> None:
        """A turn of this call started (+1) or ended (-1), which a deadline waits on."""
        node: Call | None = self
        while node is not None:
            clock = node.clock
            if clock is not None:
                clock.turned(delta)
            node = node.parent

    def hold(self, resource: Releasable) -> None:
        """Keeps something the call made, to release when the call and its callees end.

        Kept by `id`, in the order it was made, so that a session closed before then -- its
        view let go of -- is let go of here too, however many the call opens.
        """
        res = self.res
        if res is None:
            self.res = {id(resource): resource}
            self.run.holding.add(self)
        else:
            res[id(resource)] = resource

    def made(self, view: EnvView, kind: str, name: str, derived: EnvView) -> None:
        """A temporary copy or scratch directory was made through one of this call's views.

        Removed when the call ends, unless the run is journaled -- then it is written down
        instead, and kept for the run to be picked up in.
        """
        run = self.run
        driver = view.driver
        if run.journal is not None:
            run.journal.note(
                {
                    "t": "tmp",
                    "id": self.jid,
                    "env": view.role,
                    "kind": kind,
                    "name": name,
                    "chain": derived.chain,
                    "workdir": str(derived.workdir),
                }
            )
            return
        for one in (self.res or {}).values():
            if (
                type(one) is Made
                and one.driver is driver
                and one.kind == kind
                and one.id == name
            ):
                return
        self.hold(Made(driver, kind, name))

    def unmade(self, driver: EnvDriver, kind: str, name: str) -> None:
        """A temporary copy or scratch directory was removed by the flow itself."""
        if self.res:
            self.res = {
                key: one
                for key, one in self.res.items()
                if not (
                    type(one) is Made
                    and one.driver is driver
                    and one.kind == kind
                    and one.id == name
                )
            }

    def arm(self, own: Budget) -> None:
        """Starts the call's own deadline, where it is sooner than the one above it."""
        assert own.duration is not None  # noqa: S101 -- asked by the caller
        deadline = self.since + own.duration.total_seconds()
        if deadline >= self.deadline:
            return
        self.deadline = deadline
        task = asyncio.current_task()
        if task is not None:
            self.clock = _Clock(
                self, task, deadline - time.monotonic(), graceful=own.graceful
            )

    def record(self) -> LiveCall:
        """The call as the running tree and a recorder see it."""
        record = self._record
        if record is None:
            parent = self.parent
            impl = self.impl
            record = self._record = LiveCall(
                ref=self.ref,
                name="" if impl is None else impl.name,
                depth=self.depth,
                since=self.since,
                id=self.jid,
                parent=None
                if parent is None or parent.impl is None
                else parent.record(),
                task=self.task,
                resumable=impl is not None and impl.resumable,
            )
        return record


async def _finish(node: Call) -> None:
    """Releases what a call made, now that it and every call under it are over.

    Then the same for the call above it, if that was only waiting for this one. All of it in
    a task of its own, which a cancel of the call waiting on it does not stop -- a call
    stopped halfway through releasing would never count itself out of the one above, which
    would then never release what it made -- and which the call waits on for so long only.
    """
    run = node.run
    reaping = asyncio.ensure_future(_cascade(node))
    run.reapers.add(reaping)
    reaping.add_done_callback(run.reapers.discard)
    try:
        await asyncio.wait_for(asyncio.shield(reaping), REAP)
    except TimeoutError:
        log.warning(
            "cleaning up after a flow took longer than %ss; left to go on", REAP
        )


async def _cascade(node: Call) -> None:
    while True:
        res = node.res
        if res is not None:
            node.res = None
            node.run.holding.discard(node)
            await _released(res.values())
        parent = node.parent
        if parent is None:
            return
        parent.live -= 1
        if parent.live or not parent.ended or parent.impl is None:
            return
        node = parent


async def _released(res: Reversible[Releasable]) -> None:
    """Releases what a call made, the last made first."""
    for one in reversed(res):
        try:
            await one.release()
        except Exception:
            log.exception("releasing %r failed", one)


# ---------------------------------------------------------------------------------- runs


class Recorder(Protocol):
    """What a way in hears of a run as it goes, to write it down."""

    def entered(self, call: LiveCall) -> None:
        """A flow call started."""
        ...

    def left(self, call: LiveCall, error: BaseException | None) -> None:
        """A flow call ended, with what it raised or None."""
        ...

    def spawned(
        self, call: LiveCall, role: str, session: SessionHandle, driver: AgentDriver
    ) -> None:
        """A flow call opened a session of an agent."""
        ...

    def closed(self, session: SessionHandle) -> None:
        """A session the run opened has closed, and will spend nothing more."""
        ...


@dataclass(frozen=True, slots=True)
class LiveCall:
    """One flow call, as the running tree and a recorder show it.

    Attributes:
      ref: The flow's canonical ref.
      name: Its name in its module.
      depth: How many flows deep: 1 for the flow the run was started with.
      since: When it started, on the monotonic clock.
      id: Its id in the run's journal, or 0 for a run that keeps none.
      parent: The call that made it, or None for the one the run was started with.
      task: What it was called to do.
      resumable: Whether its flow says it can be picked up again.
    """

    ref: str
    name: str
    depth: int
    since: float
    id: int
    parent: LiveCall | None
    task: str = ""
    resumable: bool = False


def running() -> tuple[LiveCall, ...]:
    """Every flow call going now, in every run of this process, oldest first."""
    calls = [node.record() for run in tuple(_RUNS) for node in tuple(run.live)]
    calls.sort(key=lambda one: one.since)
    return tuple(calls)


class Run:
    """One run: its calls, its drivers' views, and what it keeps until it ends."""

    __slots__ = (
        "bringing",
        "closing",
        "derived",
        "dropped",
        "due",
        "fetched",
        "here_chain",
        "here_driver",
        "here_grant",
        "holding",
        "ids",
        "journal",
        "live",
        "loads",
        "local",
        "lock",
        "loop",
        "opened",
        "past",
        "person",
        "pinned",
        "reapers",
        "recorder",
        "skills",
        "specs",
        "thread",
    )

    def __init__(
        self,
        *,
        person: Source,
        local: EnvDriver | None,
        recorder: Recorder | None,
    ) -> None:
        """A run about to start, on the loop running now.

        Raises:
          RuntimeError: If no loop is.
        """
        self.loop = asyncio.get_running_loop()
        self.thread = threading.get_ident()
        self.lock = threading.Lock()
        self.live: dict[Call, None] = {}
        self.person = person
        self.local = local
        self.opened = False
        self.here_driver: EnvDriver | None = None
        self.here_grant: Grant | None = None
        self.here_chain = ""
        self.recorder = recorder
        self.journal: Journal | None = None
        self.past: Past | None = None
        self.ids = 0
        self.loads: dict[tuple[int, str], Any] = {}
        self.pinned: set[FlowModule] = set()
        self.skills: dict[tuple[FlowImpl, str], dict[str, tuple[Skill, ...]]] = {}
        self.bringing: dict[
            tuple[FlowImpl, str], asyncio.Future[dict[str, tuple[Skill, ...]]]
        ] = {}
        self.holding: set[Call] = set()
        self.fetched: dict[tuple[str, str | None], asyncio.Future[Path]] = {}
        self.reapers: set[asyncio.Future[None]] = set()
        self.dropped: list[Opened] = []
        self.due = False
        self.closing: set[asyncio.Task[None]] = set()
        self.derived: dict[int, EnvDriver] = {}
        self.specs: dict[tuple[AgentDriver, Grant], str] = {}

    def here(self, role: EnvRole, node: Call, flow: FlowImpl) -> EnvView:
        """The run's own workspace, for a `LocalEnv` role nobody passed."""
        driver = self.here_driver
        if driver is None:
            driver = self.local
            if driver is None:
                from .environments import local_env

                driver = self.local = local_env(Path.cwd())
                self.opened = True
            self.here_driver = driver
            self.here_grant = Grant.of(frozenset(driver.capabilities))
            self.here_chain = f"{driver.backend}@{driver.provider}{driver.workdir}"
        grant = self.here_grant
        assert grant is not None  # noqa: S101 -- set with the driver
        return _narrowed(role, driver, grant, self.here_chain, node, flow)

    def spec_of(self, view: AgentView | OutworlderView) -> str:
        """What a journal knows an agent by."""
        if type(view) is OutworlderView:
            return "outworlder:new" if view._source.made else "outworlder"
        agent: AgentView = view  # pyright: ignore[reportAssignmentType]
        key = (agent.driver, agent.grant)
        said = self.specs.get(key)
        if said is None:
            driver, grant = key
            permission = grant.permission
            said = self.specs[key] = (
                f"{driver.harness}@{driver.provider}/{driver.model}:{driver.effort}"
                f"|{permission.local},{permission.user},{permission.system},"
                f"{permission.online}|{','.join(grant.skills)}"
            )
        return said

    def drain(self) -> None:
        """Starts closing every session whose view went since this was last done."""
        dropped = self.dropped
        if dropped:
            self.dropped = []
            for opened in dropped:
                opened.drop()

    def drain_soon(self) -> None:
        """Drains as soon as the loop gets to it, asked once however many views go first."""
        if not self.due:
            self.due = True
            self.loop.call_soon(self._drained)

    def _drained(self) -> None:
        self.due = False
        self.drain()

    def spawned(
        self, node: Call, role: str, handle: SessionHandle, driver: AgentDriver
    ) -> bool:
        """A session was opened: told, and written down if its CLI has named it yet.

        Returns:
          Whether it is still to be written down: a CLI names a session as its first turn
          goes, and the journal waits for the name -- see :meth:`named`.
        """
        if self.recorder is not None:
            self.recorder.spawned(node.record(), role, handle, driver)
        if self.journal is None:
            return False
        if handle.id is None:
            return True
        self.named(node, role, handle, driver)
        return False

    def named(
        self, node: Call, role: str, handle: SessionHandle, driver: AgentDriver
    ) -> None:
        """Writes down a session the call `node` opened, now that its CLI has named it."""
        if self.journal is not None:
            self.journal.note(
                {
                    "t": "session",
                    "id": node.jid,
                    "role": role,
                    "harness": str(driver.harness),
                    "model": driver.model,
                    "session": handle.id,
                }
            )

    async def close(self) -> None:
        """Lets go of everything the run made, however it ended."""
        from .loading import unpin

        try:
            self.drain()
            if self.reapers:
                await asyncio.wait(set(self.reapers), timeout=REAP)
            # What calls still going made -- ones a flow started and never waited for --
            # goes with the run, which is over whether they are or not.
            left: list[Releasable] = []
            for node in list(self.holding):
                left.extend((node.res or {}).values())
                node.res = None
            self.holding.clear()
            # With them, the sessions let go of whose close is still under way, which the
            # environments they are in outlive.
            waiting = set(self.closing)
            if left:
                releasing = asyncio.ensure_future(_released(left))
                self.reapers.add(releasing)
                releasing.add_done_callback(self.reapers.discard)
                waiting.add(releasing)
            if waiting:
                _, late = await asyncio.wait(waiting, timeout=REAP)
                if late:
                    log.warning("cleaning up after a run took longer than %ss", REAP)
            closing = list(reversed(self.derived.values()))
            if self.opened and self.local is not None:
                closing.append(self.local)
            for driver in closing:
                try:
                    await driver.close()
                except Exception:
                    log.exception("closing an environment the run opened failed")
        finally:
            if self.journal is not None:
                self.journal.close()
            unpin(self)
            _RUNS.discard(self)


# ------------------------------------------------------------------- the entry points


def define_flow[
    TAgentCollection: AgentCollection,
    TEnvCollection: EnvCollection,
    TFlowParams: FlowParams,
](
    fn: FlowFn[TAgentCollection, TEnvCollection, TFlowParams],
    *,
    agents: type[TAgentCollection],
    envs: type[TEnvCollection],
    params: type[TFlowParams],
    name: str | None,
    description: str | None,
    hidden: bool,
    resumable: bool,
    caller_globals: Mapping[str, Any],
    caller_locals: Mapping[str, Any],
) -> Flow:
    """Makes a decorated function a flow, which is what `hmz.flows.flow` answers with.

    Cheap, since it runs at import: the collections' annotations are resolved later, the
    first time the flow is called or described, against `caller_globals` and
    `caller_locals`.

    Args:
      fn: The decorated function.
      agents: Its `AgentCollection` subclass.
      envs: Its `EnvCollection` subclass.
      params: Its `FlowParams` subclass.
      name: What it is called in its module; None for `fn.__name__`.
      description: One line saying what it does; None for the first line of `fn`'s
        docstring, or None where it has none.
      hidden: Whether to leave it out of the lists a person picks from.
      resumable: Whether a run of it can be picked up where it left off.
      caller_globals: The globals of the module the decorator was written in.
      caller_locals: The locals where it was written, which are the globals at the top of
        a module.

    Returns:
      The flow, found by `load` in its module by `name`.

    Raises:
      FlowDefinitionError: If `fn` is not an async function taking what a flow takes, or
        what it declares is not a flow's collections and params.
    """
    named, described = checked_definition(
        fn, agents=agents, envs=envs, params=params, name=name, description=description
    )
    return FlowImpl(
        fn,
        agents=agents,
        envs=envs,
        params=params,
        name=named,
        description=described,
        hidden=bool(hidden),
        resumable=bool(resumable),
        globals_=caller_globals,
        locals_=caller_locals,
    )


def full_view(flow: Flow) -> Flow:
    """Hands a flow every capability of each agent's harness, whatever its roles declare.

    What `chat` is, and nothing else should be: a flow that talks to whichever harness it
    was given, and so declares nothing of any.

    Args:
      flow: The flow, as `flow()` made it.

    Returns:
      The same flow.
    """
    if type(flow) is not FlowImpl:
        raise TypeError(f"{flow!r} is not a flow the engine made")
    flow._full = True
    return flow


def load_flow(ref: str, *, caller_globals: Mapping[str, Any]) -> Flow:
    """Loads the flow a ref names, which is what `hmz.flows.load` answers with.

    Args:
      ref: The ref, as `hmz.flows.load` documents it.
      caller_globals: The globals of the module `load` was called from, which is the flow a
        relative ref -- `:sub`, `flow:sub` -- is relative to.

    Returns:
      The flow. Inside a run the same ref from the same module is looked up once.

    Raises:
      FlowRefError: If `ref` is not a ref, or is relative with nothing to be relative to.
      FlowNotFound: If it names no flow.
      FlowLoadConflict: If loading it would replace a module another flow of the run uses.
      FlowDefinitionError: If what it names is written wrong.
    """
    node = CALLING.get()
    if node is None:
        from .loading import load

        return load(ref, caller_globals)
    loads = node.run.loads
    key = (id(caller_globals), ref)
    found = loads.get(key)
    if found is not None:
        if type(found) is FlowImpl:
            return found
        remote: Remote = found
        if remote.flow is not None:
            loads[key] = remote.flow
            return remote.flow
        return remote
    from .loading import load

    found = loads[key] = load(ref, caller_globals)
    return found


def new_outworlder() -> Outworlder:
    """Makes an outworlder a flow answers for itself, which is what `Outworlder.new()` is.

    Returns:
      An outworlder that is away until a hook is hung on it with `on_outworlder_run`, and
      then answers every `run` with what the hook does.
    """
    return OutworlderView(Source(None, made=True, node=CALLING.get()), None, "")


async def run_flow(
    flow: Flow,
    task: str,
    *,
    agents: Mapping[str, AgentDriver],
    envs: Mapping[str, EnvDriver],
    params: FlowParams | Mapping[str, Any],
    budget: Budget,
    outworlder: OutworlderDriver | None = None,
    journal: Path | None = None,
    resume: bool = False,
    local: EnvDriver | None = None,
    recorder: Recorder | None = None,
) -> Any:
    """Runs a flow at the top of a run, over drivers: what every way in calls.

    Checks everything before anything starts -- every required role filled, each driver
    meeting its role's declaration, the params valid -- then calls the flow with views of
    the drivers granted exactly what each role declared, under `budget`, and closes every
    session it opened and removes every temporary copy and scratch directory a
    non-resumable run made before it returns or raises.

    Args:
      flow: The flow.
      task: What to do.
      agents: A driver per agent role, less the `Outworlder` roles the runtime fills.
      envs: A driver per environment role, less the `LocalEnv` roles the runtime fills.
      params: The params, or a mapping of them to validate -- string values from `-p`
        included.
      budget: What the run may spend.
      outworlder: Whoever fills `Outworlder` roles, or None for an outworlder that is
        always away.
      journal: Where to write down what a resumable flow does, as JSON lines, or None to
        write nothing. Unused for a flow that is not resumable.
      resume: Whether to pick up the run `journal` holds rather than start afresh.
      local: What fills `LocalEnv` roles, or None for the directory the process is in,
        opened when a role first needs it and closed with the run.
      recorder: What hears of every call and session as the run goes, or None.

    Returns:
      What the flow returned.

    Raises:
      RequirementError: If the drivers do not meet the declaration. Nothing has run.
      ParamsError: If the params do not validate.
      FlowException: Whatever the flow raised, as it raised it.
    """
    from .loading import Remote, home_of

    if isinstance(flow, Remote):
        flow = await flow.fetched()
    if type(flow) is not FlowImpl:
        raise TypeError(f"{flow!r} is not a flow the engine made")
    impl: FlowImpl = flow
    if not isinstance(budget, Budget):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError(f"budget={budget!r} is not a Budget")
    roles, eroles = impl.declared()
    _given(impl, roles, agents, "agent")
    _given(impl, eroles, envs, "environment")
    for role in roles:
        driver = agents.get(role.name)
        if driver is not None:
            _serves(impl, role, driver)
    for role in eroles:
        driver = envs.get(role.name)
        if driver is not None:
            lacking = role.capabilities - driver.capabilities
            if lacking:
                raise CapabilityMissing(
                    f"{impl.ref}: {role.name!r} needs "
                    f"{', '.join(sorted(one.__name__ for one in lacking))}, which "
                    f"{driver.backend}@{driver.provider}{driver.workdir} does not serve"
                )
            if role.resources:
                _meets(role, driver, impl)
    said = impl.params_of(params)
    loop = asyncio.get_running_loop()
    run = Run(
        person=Source(outworlder, made=False, node=None),
        local=local,
        recorder=recorder,
    )
    top = Call(run, None, None, 0, budget, task)
    if budget.duration is not None:
        top.deadline = top.since + budget.duration.total_seconds()
    views: dict[str, AgentView] = {}
    for role in roles:
        driver = agents.get(role.name)
        if driver is not None:
            grant = (
                Grant.of(frozenset(driver.capabilities), role.permission, role.skills)
                if impl._full
                else role.grant
            )
            views[role.name] = AgentView(driver, grant, top, role.name)
    env_views: dict[str, EnvView] = {}
    for role in eroles:
        driver = envs.get(role.name)
        if driver is not None:
            env_views[role.name] = EnvView(
                driver,
                role.grant,
                top,
                role.name,
                f"{driver.backend}@{driver.provider}{driver.workdir}",
            )
    _RUNS.add(run)
    try:
        home = impl.home or home_of(impl)
        if home is not None:
            from .loading import pin

            pin(home, run)
        if impl.resumable and journal is not None:
            run.journal, run.past = Journal.opened(Path(journal), loop, resume=resume)
            if run.past is not None:
                run.ids = run.past.next_id - 1
        running_task = asyncio.current_task()
        if top.deadline != _INF and running_task is not None:
            top.clock = _Clock(
                top,
                running_task,
                top.deadline - time.monotonic(),
                graceful=budget.graceful,
            )
        token = CALLING.set(top)
        try:
            return await impl(task, agents=views, envs=env_views, params=said)
        except asyncio.CancelledError:
            clock = top.clock
            expired = None if clock is None else clock.settle()
            if expired is not None:
                raise expired from None
            raise
        finally:
            CALLING.reset(token)
            top.ended = True
            if top.clock is not None:
                top.clock.stop()
    finally:
        await run.close()


def _given(
    flow: FlowImpl,
    roles: tuple[AgentRole, ...] | tuple[EnvRole, ...],
    given: Mapping[str, object],
    what: str,
) -> None:
    """Refuses a run given drivers for roles it cannot be given them for.

    Raises:
      MissingRole: For a required role nothing was given for.
      RequirementError: For a role the flow does not declare, or one the runtime fills.
    """
    declared = {role.name: role for role in roles}
    for name in given:
        role = declared.get(name)
        if role is None:
            raise RequirementError(f"{flow.ref} declares no {what} role {name!r}")
        if role.auto:
            raise RequirementError(
                f"{flow.ref}: the {what} role {name!r} is filled by the runtime, and "
                "cannot be given"
            )
    for role in roles:
        if role.required and not role.auto and role.name not in given:
            raise MissingRole(f"{flow.ref}: no {what} was given for {role.name!r}")


def _serves(flow: FlowImpl, role: AgentRole, driver: AgentDriver) -> None:
    """Refuses an agent driver that cannot fill a role.

    Raises:
      HarnessMismatch: For a role asking for another harness.
      CapabilityMissing: For a driver not serving a mixin the role asks for.
    """
    if role.harness is not None and driver.harness != role.harness:
        raise HarnessMismatch(
            f"{flow.ref}: {role.name!r} is {role.harness}, and {driver.harness} was given"
        )
    lacking = role.capabilities - driver.capabilities
    if lacking:
        raise CapabilityMissing(
            f"{flow.ref}: {role.name!r} needs "
            f"{', '.join(sorted(one.__name__ for one in lacking))}, which "
            f"{driver.harness} does not serve"
        )

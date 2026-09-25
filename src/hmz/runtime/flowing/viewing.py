"""What a flow is handed: views of the run's drivers, granted exactly what the flow declared.

A driver does anything its harness or machine can. A flow may do only what it declared, so it
is never handed a driver: it is handed a view -- :class:`AgentView`, :class:`EnvView`,
:class:`OutworlderView`, and the :class:`SessionView` they open -- holding the driver, the
:class:`~hmz.runtime.flowing.declaring.Grant` its role declared, and the flow call it belongs
to. Everything the flow API lets a flow do is a method here, and each checks the grant first:
a `/goal` or `/loop` prompt, `steer`, a hook only some harnesses reach, a script `exec`, files,
worktrees, temporary copies and scratch directories each raise
:class:`~hmz.flows.CapabilityNotGranted` without the mixin for them, whatever the driver could
do.

The views answer to the flow API's protocols structurally -- the tests hold them to every
member of every protocol and mixin -- without deriving from them: a flow's own `class
Coder(Agent, GoalCommandAgentMixin)` is a type for a type checker, and a view deriving from it
would carry the protocols' stub bodies, lose its `__slots__`, and make every `isinstance`
slower for nothing. A view is a handful of pointers, made per flow call.
"""

from __future__ import annotations

# A view and the session it opened, and a view and the engine's call it belongs to, are
# halves of one object, and reach into each other's underscored slots -- which the
# underscore keeps from flows rather than from them.
# pyright: reportPrivateUsage=false
import asyncio
import contextvars
import logging
from typing import TYPE_CHECKING, Any, ClassVar, Self, overload

import pydantic

from hmz.flows import (
    AskUserHookAgentMixin,
    AskUserHookParams,
    BashEnvMixin,
    CapabilityNotGranted,
    EnvBackendKind,
    FilesEnvMixin,
    GitWorktreeEnvMixin,
    GoalCommandAgentMixin,
    HarnessKind,
    HookKind,
    LoopCommandAgentMixin,
    NotificationHookParams,
    OutputSchemaError,
    OutworlderAway,
    OutworlderRunHookParams,
    Permission,
    PermissionRequestHookAgentMixin,
    PermissionRequestHookParams,
    PreToolUseHookParams,
    ScratchDirEnvMixin,
    SessionEndHookParams,
    SessionError,
    SessionStartHookParams,
    ShellEnvMixin,
    SteeringAgentMixin,
    StopHookParams,
    SubagentStartHookAgentMixin,
    SubagentStartHookParams,
    SubagentStopHookAgentMixin,
    SubagentStopHookParams,
    TemporaryClonedDirEnvMixin,
    UnsupportedOperation,
    Usage,
    UserPromptSubmitHookParams,
)

from .declaring import Grant
from .spi import HookTable, Limits, TurnRequest, default_result

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import PurePosixPath

    from hmz.flows import (
        AskUserHookResult,
        Budget,
        Env,
        HookFn,
        HookParams,
        HookResult,
        NotificationHookResult,
        OutworlderRunHookResult,
        PermissionRequestHookResult,
        PreToolUseHookResult,
        SequenceNotStr,
        Session,
        SessionEndHookResult,
        SessionStartHookResult,
        StopHookResult,
        SubagentStartHookResult,
        SubagentStopHookResult,
        UserPromptSubmitHookResult,
    )

    from .engine import Call
    from .spi import AgentDriver, EnvDriver, OutworlderDriver, SessionHandle, Skill

__all__ = [
    "CALLING",
    "AgentView",
    "EnvView",
    "OutworlderView",
    "SessionView",
    "away_answer",
]

log = logging.getLogger(__name__)

#: What a turn nobody took costs.
_NOTHING = Usage()

#: The flow call running in this context: a task's, so that each branch of a gather has its
#: own. The engine sets it around every call, and a hook runs under the call whose agent it
#: was hung on, whichever thread the moment arrived on.
CALLING: contextvars.ContextVar[Call | None] = contextvars.ContextVar(
    "hmz_flow_call", default=None
)


class _Line:
    """What an agent and every agent derived from it share: its hooks and its sessions."""

    __slots__ = ("hooks", "sessions")

    def __init__(self) -> None:
        self.hooks = HookTable()
        self.sessions: dict[int, SessionView] = {}


class _Sink:
    """Where one turn's spending goes: onto its flow and every flow above it, at once."""

    __slots__ = ("_lock", "_node")

    def __init__(self, node: Call) -> None:
        self._node = node
        self._lock = node.run.lock

    def add(self, *, cost: float, output_tokens: int, duration: float) -> None:
        with self._lock:
            node: Call | None = self._node
            while node is not None:
                node.cost += cost
                node.tokens += output_tokens
                node.secs += duration
                node = node.parent


def _command(prompt: str, word: str) -> bool:
    """Whether a prompt is one of the harness's own commands, as `/goal` or `/loop`."""
    return prompt.startswith(word) and (
        len(prompt) == len(word) or prompt[len(word)].isspace()
    )


# --------------------------------------------------------------------------------- agents


class AgentView:
    """An agent, as one flow is handed it: a driver, and what the role was granted.

    Answers to :class:`hmz.flows.Agent` and to every agent mixin, each of which raises
    `CapabilityNotGranted` unless the role declared it. `derive` narrows and never widens;
    an agent derived from this one shares its hooks and its sessions.
    """

    #: What the flow API's protocol declares; a view's own is its `grant`.
    _permission: ClassVar[Permission] = Permission()
    _skills: ClassVar[tuple[str, ...]] = ()

    __slots__ = ("_driver", "_grant", "_line", "_node", "_role")

    def __init__(
        self, driver: AgentDriver, grant: Grant, node: Call, role: str
    ) -> None:
        """A view of a driver for one role of one flow call."""
        self._driver = driver
        self._grant = grant
        self._node = node
        self._role = role
        self._line: _Line | None = None

    def __repr__(self) -> str:
        driver = self._driver
        return (
            f"<agent {self._role}: {driver.harness}/{driver.model}"
            f"{':' + driver.effort if driver.effort else ''}>"
        )

    # ----------------------------------------------------------------------- what it is

    @property
    def effort(self) -> str:
        return self._driver.effort

    @property
    def harness(self) -> HarnessKind:
        return self._driver.harness

    @property
    def model(self) -> str:
        return self._driver.model

    @property
    def provider(self) -> str:
        return self._driver.provider

    @property
    def role(self) -> str:
        return self._role

    @property
    def grant(self) -> Grant:
        """What this view lets the flow do: its capabilities, permission and skills."""
        return self._grant

    @property
    def driver(self) -> AgentDriver:
        """The driver underneath, for the runtime's own use."""
        return self._driver

    # -------------------------------------------------------------------- what it does

    def derive(
        self,
        *,
        permission: Permission | None = None,
        skills: tuple[str, ...] | None = None,
    ) -> Self:
        grant = self._grant
        if permission is None:
            permission = grant.permission
        elif not isinstance(permission, Permission):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(f"permission={permission!r} is not a Permission")
        elif not grant.permission.covers(permission):
            raise CapabilityNotGranted(
                f"{self._role}: {permission} is wider than the {grant.permission} "
                "this agent was granted"
            )
        if skills is None:
            skills = grant.skills
        else:
            skills = tuple(skills)
            wider = set(skills) - set(grant.skills)
            if wider:
                raise CapabilityNotGranted(
                    f"{self._role}: {', '.join(sorted(wider))} is not among the skills "
                    "this agent was granted"
                )
        narrowed = Grant.of(grant.capabilities, permission, skills)
        cls = type(self)
        view = cls.__new__(cls)
        view._driver = self._driver
        view._grant = narrowed
        view._node = self._node
        view._role = self._role
        view._line = self._lined()
        return view

    async def spawn(self, *, env: Env) -> SessionView:
        return await self._opened(env, None)

    async def fork(self, session: Session, *, env: Env) -> SessionView:
        forked = self._own(session)
        if forked._closed:
            raise SessionError(f"{self._role}: the session to fork is over")
        return await self._opened(env, forked)

    async def _opened(self, env: Env, fork_of: SessionView | None) -> SessionView:
        if type(env) is not EnvView:
            raise TypeError(f"{env!r} is not an environment this run handed out")
        node = self._node
        node.check()
        line = self._lined()
        run = node.run
        handle = await self._driver.open(
            env._driver.placement(),
            permission=self._grant.permission,
            skills=self._brought(),
            hooks=line.hooks,
            fork_of=None if fork_of is None else fork_of._handle,
        )
        session = SessionView(self, env, handle)
        line.sessions[id(handle)] = session
        node.hold(session)
        run.spawned(node, self._role, handle, self._driver)
        return session

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
        output_schema: type[TOutput],
        budget: Budget | None = None,
    ) -> TOutput: ...

    async def run(
        self,
        prompt: str,
        *,
        session: Session,
        output_schema: type[pydantic.BaseModel] | None = None,
        budget: Budget | None = None,
    ) -> str | pydantic.BaseModel:
        taken = self._own(session)
        command = prompt.lstrip()
        if command.startswith("/"):
            capabilities = self._grant.capabilities
            if _command(command, "/goal") and GoalCommandAgentMixin not in capabilities:
                raise CapabilityNotGranted(
                    f"{self._role}: /goal needs GoalCommandAgentMixin on the role"
                )
            if _command(command, "/loop") and LoopCommandAgentMixin not in capabilities:
                raise CapabilityNotGranted(
                    f"{self._role}: /loop needs LoopCommandAgentMixin on the role"
                )
        node = self._node
        limits = node.limits(budget)
        if taken._busy:
            raise SessionError(f"{self._role}: a turn of this session is under way")
        if taken._closed:
            raise SessionError(f"{self._role}: the session is over")
        handle = taken._handle
        taken._busy = True
        node.turning(1)
        try:
            said = await handle.turn(
                TurnRequest(prompt, output_schema, limits), _Sink(node)
            )
        except asyncio.CancelledError:
            handle.interrupt()
            raise
        except BaseException:
            failed = taken._error
            if failed is not None:
                taken._error = None
                raise failed from None
            raise
        finally:
            taken._busy = False
            node.turning(-1)
        failed = taken._error
        if failed is not None:
            taken._error = None
            raise failed
        if output_schema is not None and not isinstance(said, output_schema):
            raise OutputSchemaError(
                f"{self._role} answered {type(said).__name__}, not {output_schema.__name__}"
            )
        return said

    async def steer(
        self,
        prompt: str,
        *,
        session: Session,
        queued: bool = True,
    ) -> None:
        if SteeringAgentMixin not in self._grant.capabilities:
            raise CapabilityNotGranted(
                f"{self._role}: steer needs SteeringAgentMixin on the role"
            )
        taken = self._own(session)
        self._node.check()
        await taken._handle.steer(prompt, queued=queued)

    def _brought(self) -> tuple[Skill, ...]:
        """The skills this agent's sessions are given: what its grant names, as found."""
        names = self._grant.skills
        if not names:
            return ()
        node = self._node
        impl = node.impl
        found = None if impl is None else node.run.skills.get((impl, self._role))
        if found is None:
            return ()
        return tuple(skill for said in names for skill in found.get(said, ()))

    def _own(self, session: Session) -> SessionView:
        """The session, if it is one of this agent's; SessionError otherwise."""
        if (
            type(session) is not SessionView
            or session._line is None
            or session._line is not self._line
        ):
            raise SessionError(f"{self._role}: {session!r} is not one of this agent's")
        return session

    def _lined(self) -> _Line:
        line = self._line
        if line is None:
            line = self._line = _Line()
        return line

    # --------------------------------------------------------------------------- hooks

    def _hang(
        self,
        kind: HookKind,
        params: type[HookParams],
        fn: Callable[[Any], Awaitable[HookResult]] | None,
        mixin: type | None = None,
    ) -> None:
        if mixin is not None and mixin not in self._grant.capabilities:
            raise CapabilityNotGranted(
                f"{self._role}: a {kind} hook needs {mixin.__name__} on the role"
            )
        line = self._lined()
        if fn is None:
            line.hooks.set(kind, None)
            return
        node = self._node
        sessions = line.sessions

        async def bound(handle: SessionHandle, fields: dict[str, Any]) -> HookResult:
            session = sessions.get(id(handle))
            token = CALLING.set(node)
            try:
                return await fn(params(ctx=node, session=session, **fields))  # pyright: ignore[reportArgumentType]
            except Exception as error:
                # The flow's to raise, not the driver's: the turn it arrived in stops, and
                # raises it where the flow is waiting on that turn.
                if session is not None and not session._closed:
                    session._failed(error)
                else:
                    log.exception("a %s hook raised", kind)
                return default_result(kind)
            finally:
                CALLING.reset(token)

        line.hooks.set(kind, bound)

    def on_session_start(
        self, fn: HookFn[SessionStartHookParams, SessionStartHookResult] | None
    ) -> None:
        self._hang(HookKind.SESSION_START, SessionStartHookParams, fn)

    def on_user_prompt_submit(
        self, fn: HookFn[UserPromptSubmitHookParams, UserPromptSubmitHookResult] | None
    ) -> None:
        self._hang(HookKind.USER_PROMPT_SUBMIT, UserPromptSubmitHookParams, fn)

    def on_pre_tool_use(
        self, fn: HookFn[PreToolUseHookParams, PreToolUseHookResult] | None
    ) -> None:
        self._hang(HookKind.PRE_TOOL_USE, PreToolUseHookParams, fn)

    def on_notification(
        self, fn: HookFn[NotificationHookParams, NotificationHookResult] | None
    ) -> None:
        self._hang(HookKind.NOTIFICATION, NotificationHookParams, fn)

    def on_stop(self, fn: HookFn[StopHookParams, StopHookResult] | None) -> None:
        self._hang(HookKind.STOP, StopHookParams, fn)

    def on_session_end(
        self, fn: HookFn[SessionEndHookParams, SessionEndHookResult] | None
    ) -> None:
        self._hang(HookKind.SESSION_END, SessionEndHookParams, fn)

    def on_permission_request(
        self,
        fn: HookFn[PermissionRequestHookParams, PermissionRequestHookResult] | None,
    ) -> None:
        self._hang(
            HookKind.PERMISSION_REQUEST,
            PermissionRequestHookParams,
            fn,
            PermissionRequestHookAgentMixin,
        )

    def on_subagent_start(
        self, fn: HookFn[SubagentStartHookParams, SubagentStartHookResult] | None
    ) -> None:
        self._hang(
            HookKind.SUBAGENT_START,
            SubagentStartHookParams,
            fn,
            SubagentStartHookAgentMixin,
        )

    def on_subagent_stop(
        self, fn: HookFn[SubagentStopHookParams, SubagentStopHookResult] | None
    ) -> None:
        self._hang(
            HookKind.SUBAGENT_STOP,
            SubagentStopHookParams,
            fn,
            SubagentStopHookAgentMixin,
        )

    def on_ask_user(
        self, fn: HookFn[AskUserHookParams, AskUserHookResult] | None
    ) -> None:
        self._hang(HookKind.ASK_USER, AskUserHookParams, fn, AskUserHookAgentMixin)


class SessionView:
    """One session, as the flow that opened it holds it."""

    __slots__ = ("_agent", "_busy", "_closed", "_env", "_error", "_handle", "_line")

    def __init__(
        self,
        agent: AgentView | OutworlderView,
        env: EnvView,
        handle: SessionHandle,
    ) -> None:
        """A view of a handle one agent view opened in one environment view."""
        self._agent = agent
        self._env = env
        self._handle = handle
        self._line = agent._line if type(agent) is AgentView else None
        self._busy = False
        self._closed = False
        self._error: Exception | None = None

    def __repr__(self) -> str:
        return f"<session of {self._agent.role} in {self._env.workdir}>"

    @property
    def agent(self) -> AgentView | OutworlderView:
        return self._agent

    @property
    def env(self) -> EnvView:
        return self._env

    @property
    def usage(self) -> Usage:
        return self._handle.usage

    @property
    def id(self) -> str | None:
        """The CLI's own id for the conversation, or None before it has said one."""
        return self._handle.id

    def _failed(self, error: Exception) -> None:
        """A hook of this session raised: the turn under way stops, and raises it."""
        if self._error is None:
            self._error = error
        self._handle.interrupt()

    async def release(self) -> None:
        """Closes the session, which the flow call that opened it does as it ends."""
        if not self._closed:
            self._closed = True
            try:
                await self._handle.close()
            finally:
                if self._line is not None:
                    self._line.sessions.pop(id(self._handle), None)


# ------------------------------------------------------------------------- environments


class EnvView:
    """An environment, as one flow is handed it: a driver, and what the role was granted.

    Answers to :class:`hmz.flows.Env`, `LocalEnv` and every environment mixin, each of which
    raises `CapabilityNotGranted` unless the role declared it. What it derives is a view
    granted the same, filling the same role.
    """

    #: What the flow API's resource mixins declare; a view's machine is its driver's.
    _cpu_count: ClassVar[int] = 1
    _memory: ClassVar[int] = 0
    _gpu_count: ClassVar[int] = 1
    _gpu_memory: ClassVar[int] = 0

    __slots__ = ("_chain", "_driver", "_grant", "_node", "_role")

    def __init__(
        self, driver: EnvDriver, grant: Grant, node: Call, role: str, chain: str
    ) -> None:
        """A view of a driver for one role of one flow call.

        Args:
          driver: The driver.
          grant: What the role declared.
          node: The flow call it belongs to.
          role: The role.
          chain: How it was derived from what a command line named, which is what a
            journal knows it by.
        """
        self._driver = driver
        self._grant = grant
        self._node = node
        self._role = role
        self._chain = chain

    def __repr__(self) -> str:
        return f"<env {self._role}: {self._chain}>"

    @property
    def available(self) -> bool:
        return self._driver.available

    @property
    def backend(self) -> EnvBackendKind:
        return self._driver.backend

    @property
    def provider(self) -> str:
        return self._driver.provider

    @property
    def role(self) -> str:
        return self._role

    @property
    def workdir(self) -> PurePosixPath:
        return self._driver.workdir

    @property
    def grant(self) -> Grant:
        """What this view lets the flow do."""
        return self._grant

    @property
    def driver(self) -> EnvDriver:
        """The driver underneath, for the runtime's own use."""
        return self._driver

    @property
    def chain(self) -> str:
        """How it was derived from what a command line named, as a journal knows it."""
        return self._chain

    def _need(self, mixin: type, what: str) -> None:
        if mixin not in self._grant.capabilities:
            raise CapabilityNotGranted(
                f"{self._role}: {what} needs {mixin.__name__} on the role"
            )

    def _derived(self, driver: EnvDriver, step: str) -> Self:
        self._node.run.derived[id(driver)] = driver
        cls = type(self)
        view = cls.__new__(cls)
        view._driver = driver
        view._grant = self._grant
        view._node = self._node
        view._role = self._role
        view._chain = f"{self._chain}#{step}"
        return view

    async def derive_subdir(self, *, subdir: PurePosixPath | str) -> EnvView:
        self._node.check()
        return self._derived(
            await self._driver.derive_subdir(subdir), f"subdir({subdir})"
        )

    @overload
    async def exec(
        self,
        argv: SequenceNotStr[str],
        *,
        timeout: float = 0,  # noqa: ASYNC109 -- the flow API's
    ) -> tuple[int, str, str]: ...

    @overload
    async def exec(
        self,
        script: str,
        *,
        timeout: float = 0,  # noqa: ASYNC109 -- the flow API's
    ) -> tuple[int, str, str]: ...

    async def exec(
        self,
        *args: SequenceNotStr[str] | str,
        timeout: float = 0,  # noqa: ASYNC109 -- the flow API's
        **named: SequenceNotStr[str] | str,
    ) -> tuple[int, str, str]:
        if len(args) + len(named) != 1 or not set(named) <= {"argv", "script"}:
            raise TypeError("exec takes one command: an argv, or a script")
        command = args[0] if args else next(iter(named.values()))
        if isinstance(command, str):
            self._need(BashEnvMixin, "a script exec")
        else:
            self._need(ShellEnvMixin, "exec")
            command = list(command)
        self._node.check()
        return await self._driver.exec(command, timeout=timeout)

    async def read(self, path: str) -> bytes:
        self._need(FilesEnvMixin, "read")
        self._node.check()
        return await self._driver.read(path)

    async def write(self, path: str, data: bytes) -> None:
        self._need(FilesEnvMixin, "write")
        self._node.check()
        await self._driver.write(path, data)

    async def derive_worktree(
        self,
        *,
        ref: str | None = None,
        dir: PurePosixPath | str | None = None,  # noqa: A002 -- the flow API's
    ) -> Self:
        self._need(GitWorktreeEnvMixin, "derive_worktree")
        self._node.check()
        derived = await self._driver.derive_worktree(ref=ref, dir=dir)
        return self._derived(derived, f"worktree({ref or ''},{dir or ''})")

    async def derive_temp_clone(self, id: str) -> Self:  # noqa: A002 -- the flow API's
        self._need(TemporaryClonedDirEnvMixin, "derive_temp_clone")
        node = self._node
        node.check()
        derived = await self._driver.derive_temp_clone(id, holder=self)
        view = self._derived(derived, f"temp_clone({id})")
        node.made(self, "temp_clone", id, view)
        return view

    async def destroy_temp_clone(self, id: str) -> None:  # noqa: A002 -- the flow API's
        self._need(TemporaryClonedDirEnvMixin, "destroy_temp_clone")
        self._node.check()
        await self._driver.destroy_temp_clone(id)
        self._node.unmade(self._driver, "temp_clone", id)

    async def derive_scratch(self, id: str) -> Self:  # noqa: A002 -- the flow API's
        self._need(ScratchDirEnvMixin, "derive_scratch")
        node = self._node
        node.check()
        derived = await self._driver.derive_scratch(id)
        view = self._derived(derived, f"scratch({id})")
        node.made(self, "scratch", id, view)
        return view

    async def destroy_scratch(self, id: str) -> None:  # noqa: A002 -- the flow API's
        self._need(ScratchDirEnvMixin, "destroy_scratch")
        self._node.check()
        await self._driver.destroy_scratch(id)
        self._node.unmade(self._driver, "scratch", id)

    # The machine, as the runtime reads it; a flow declares what it needs instead.

    @property
    def cpu_count(self) -> int:
        """Logical CPUs of the machine."""
        return self._driver.cpu_count

    @property
    def memory(self) -> int:
        """Memory of the machine, in bytes."""
        return self._driver.memory

    @property
    def gpu_count(self) -> int:
        """GPUs of the machine."""
        return self._driver.gpu_count

    @property
    def gpu_memory(self) -> int:
        """Memory of its smallest GPU, in bytes."""
        return self._driver.gpu_memory


# -------------------------------------------------------------------------- outworlders


def away_answer(
    schema: type[pydantic.BaseModel] | None,
) -> str | pydantic.BaseModel:
    """What an outworlder that is away answers.

    Raises:
      OutworlderAway: For a schema not every field of which has a default.
    """
    if schema is None:
        return ""
    try:
        return schema()
    except pydantic.ValidationError:
        raise OutworlderAway(
            f"nobody is there to answer with a {schema.__name__}, and it has fields "
            "with no default"
        ) from None


def _answered(
    said: object, schema: type[pydantic.BaseModel] | None, who: str
) -> str | pydantic.BaseModel:
    """An outworlder's answer, as what was asked for."""
    if schema is None:
        if isinstance(said, str):
            return said
        raise OutputSchemaError(f"{who} answered {type(said).__name__}, not text")
    if isinstance(said, schema):
        return said
    try:
        return schema.model_validate(
            said.model_dump() if isinstance(said, pydantic.BaseModel) else said
        )
    except pydantic.ValidationError as error:
        raise OutputSchemaError(f"{who} did not answer a {schema.__name__}") from error


class Source:
    """Whoever an outworlder view answers for: the run's own, or one a flow made."""

    __slots__ = ("driver", "hook", "made", "node")

    def __init__(
        self, driver: OutworlderDriver | None, *, made: bool, node: Call | None
    ) -> None:
        """A source over a driver, or one a flow made with `Outworlder.new()`."""
        self.driver = driver
        self.made = made
        self.node = node
        self.hook: HookFn[OutworlderRunHookParams, OutworlderRunHookResult] | None = (
            None
        )

    @property
    def away(self) -> bool:
        if self.made:
            return self.hook is None
        return self.driver is None or self.driver.away


class _Person:
    """The session handle of an outworlder, who has no CLI to hold one of."""

    __slots__ = ("source",)

    def __init__(self, source: Source) -> None:
        self.source = source

    @property
    def id(self) -> str | None:
        return None

    @property
    def usage(self) -> Usage:
        return _NOTHING

    async def turn(self, request: TurnRequest, sink: object) -> str:
        del request, sink
        raise UnsupportedOperation("an outworlder's turns are taken through its agent")

    async def steer(self, prompt: str, *, queued: bool) -> None:
        del prompt, queued
        raise UnsupportedOperation("an outworlder is not steered")

    def interrupt(self) -> None:
        return

    async def close(self) -> None:
        return


class OutworlderView:
    """Whoever is outside the run, as one flow is handed them.

    Answers to :class:`hmz.flows.Outworlder`. The run's own answers through its
    :class:`~hmz.runtime.flowing.spi.OutworlderDriver`, and one a flow made with
    `Outworlder.new()` through the `on_outworlder_run` hook hung on it; either answers for
    itself while it is away.
    """

    _permission: ClassVar[Permission] = Permission()
    _skills: ClassVar[tuple[str, ...]] = ()

    __slots__ = ("_line", "_node", "_role", "_source")

    def __init__(self, source: Source, node: Call | None, role: str) -> None:
        """A view of an outworlder for one role of one flow call."""
        self._source = source
        self._node = node
        self._role = role
        self._line: _Line | None = None

    def __repr__(self) -> str:
        made = "made" if self._source.made else "the run's"
        return f"<outworlder {self._role or '(unassigned)'}: {made}>"

    @classmethod
    def new(cls) -> Self:
        return cls(Source(None, made=True, node=CALLING.get()), None, "")

    @property
    def node(self) -> Call | None:
        """The flow call it belongs to, or None for one made outside any."""
        return self._node

    @property
    def away(self) -> bool:
        return self._source.away

    @property
    def effort(self) -> str:
        return ""

    @property
    def harness(self) -> HarnessKind:
        return HarnessKind.ACP

    @property
    def model(self) -> str:
        return ""

    @property
    def provider(self) -> str:
        return ""

    @property
    def role(self) -> str:
        return self._role

    def derive(
        self,
        *,
        permission: Permission | None = None,
        skills: tuple[str, ...] | None = None,
    ) -> Self:
        if permission is not None and not isinstance(permission, Permission):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(f"permission={permission!r} is not a Permission")
        if skills:
            raise CapabilityNotGranted(f"{self._role}: an outworlder has no skills")
        return self

    async def spawn(self, *, env: Env) -> SessionView:
        if type(env) is not EnvView:
            raise TypeError(f"{env!r} is not an environment this run handed out")
        if self._node is not None:
            self._node.check()
        return SessionView(self, env, _Person(self._source))

    async def fork(self, session: Session, *, env: Env) -> SessionView:
        del session, env
        raise UnsupportedOperation("an outworlder's session cannot be forked")

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
        output_schema: type[TOutput],
        budget: Budget | None = None,
    ) -> TOutput: ...

    async def run(
        self,
        prompt: str,
        *,
        session: Session,
        output_schema: type[pydantic.BaseModel] | None = None,
        budget: Budget | None = None,
    ) -> str | pydantic.BaseModel:
        source = self._source
        if (
            type(session) is not SessionView
            or type(session._handle) is not _Person
            or session._handle.source is not source
        ):
            raise SessionError(
                f"{self._role}: {session!r} is not one of this outworlder's"
            )
        node = self._node
        if node is not None:
            node.limits(budget)
        if source.made:
            hook = source.hook
            if hook is None:
                return away_answer(output_schema)
            owner = source.node or node
            token = CALLING.set(owner)
            try:
                answered = await hook(
                    OutworlderRunHookParams(
                        ctx=owner,  # pyright: ignore[reportArgumentType]
                        session=session,
                        prompt=prompt,
                        output_schema=output_schema,
                    )
                )
            finally:
                CALLING.reset(token)
            return _answered(answered.output, output_schema, self._role or "outworlder")
        driver = source.driver
        if driver is None or driver.away:
            return away_answer(output_schema)
        try:
            said = await driver.run(prompt, output_schema)
        except OutworlderAway:
            return away_answer(output_schema)
        return _answered(said, output_schema, self._role or "outworlder")

    def on_outworlder_run(
        self, fn: HookFn[OutworlderRunHookParams, OutworlderRunHookResult] | None
    ) -> None:
        source = self._source
        if not source.made:
            raise CapabilityNotGranted(
                f"{self._role}: only an outworlder made with Outworlder.new() is answered "
                "by a hook"
            )
        if source.node is None:
            source.node = self._node
        source.hook = fn

    # An outworlder reaches none of a harness's moments, so a hook hung on one is never
    # heard; hanging one is not wrong, since every agent has these.

    def _hang(self, kind: HookKind, fn: object) -> None:
        del kind, fn

    def on_session_start(
        self, fn: HookFn[SessionStartHookParams, SessionStartHookResult] | None
    ) -> None:
        self._hang(HookKind.SESSION_START, fn)

    def on_user_prompt_submit(
        self, fn: HookFn[UserPromptSubmitHookParams, UserPromptSubmitHookResult] | None
    ) -> None:
        self._hang(HookKind.USER_PROMPT_SUBMIT, fn)

    def on_pre_tool_use(
        self, fn: HookFn[PreToolUseHookParams, PreToolUseHookResult] | None
    ) -> None:
        self._hang(HookKind.PRE_TOOL_USE, fn)

    def on_notification(
        self, fn: HookFn[NotificationHookParams, NotificationHookResult] | None
    ) -> None:
        self._hang(HookKind.NOTIFICATION, fn)

    def on_stop(self, fn: HookFn[StopHookParams, StopHookResult] | None) -> None:
        self._hang(HookKind.STOP, fn)

    def on_session_end(
        self, fn: HookFn[SessionEndHookParams, SessionEndHookResult] | None
    ) -> None:
        self._hang(HookKind.SESSION_END, fn)


#: Every resource a flow call made that goes when it does, by what makes one: a session
#: closes, a temporary copy or scratch directory is removed.
type Releasable = SessionView | Made


class Made:
    """A temporary copy or scratch directory a flow call made, to remove when it ends."""

    __slots__ = ("driver", "id", "kind")

    def __init__(self, driver: EnvDriver, kind: str, id: str) -> None:  # noqa: A002
        self.driver = driver
        self.kind = kind
        self.id = id

    async def release(self) -> None:
        """Removes it."""
        if self.kind == "temp_clone":
            await self.driver.destroy_temp_clone(self.id)
        else:
            await self.driver.destroy_scratch(self.id)


def limits_of(cost: float, tokens: float, deadline: float, *, graceful: bool) -> Limits:
    """What a turn may spend, with infinity written as no limit."""
    inf = float("inf")
    return Limits(
        cost=None if cost == inf else max(cost, 0.0),
        output_tokens=None if tokens == inf else max(int(tokens), 0),
        deadline=None if deadline == inf else deadline,
        graceful=graceful,
    )

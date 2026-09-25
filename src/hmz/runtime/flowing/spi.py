"""The seam between the flow engine and the drivers that do its work.

A flow is handed agents and environments that answer to :mod:`hmz.flows`. Behind each is a
driver: an :class:`AgentDriver` over one coding agent CLI, an :class:`EnvDriver` over one
working directory on one machine, an :class:`OutworlderDriver` over whoever is outside the
run. The engine holds the drivers and hands flows views of them -- one per role, granted
exactly what the role declared -- so a driver is written once, knows nothing of flows,
roles, grants or budgets beyond what it is told per call, and may assume the engine never
asks it for a capability it does not list.

What a driver promises, whoever implements it:

- It raises the leaves of :mod:`hmz.flows.errors` and nothing else for what goes wrong in
  its own work -- :class:`~hmz.flows.errors.HarnessError` leaves for an agent,
  :class:`~hmz.flows.errors.EnvError` leaves for an environment, and the
  :class:`~hmz.flows.errors.BudgetExceeded` leaves for a limit it enforced. A bug is still
  the bug it was.
- It is cancellation-safe. A coroutine of it that is cancelled stops what it started -- a
  turn stops spending, a command is killed -- before `CancelledError` leaves it.
- It is fast at rest: nothing here may block the event loop. Work that blocks runs on a
  thread, and everything a thread hands back to the loop goes through
  :class:`HookBridge` or the loop's own thread-safe calls.

:func:`~hmz.runtime.flowing.harnesses.open_agent` and
:func:`~hmz.runtime.flowing.environments.open_env` make drivers from what a command line
said; `tests/flows/contracts.py` holds every driver to this module's promises.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol

from hmz.flows import (
    HARNESS_AGENTS,
    HOOK_TYPES,
    AskUserHookAgentMixin,
    BashEnvMixin,
    FilesEnvMixin,
    GitWorktreeEnvMixin,
    GoalCommandAgentMixin,
    HookKind,
    LoopCommandAgentMixin,
    PermissionRequestHookAgentMixin,
    ScratchDirEnvMixin,
    ShellEnvMixin,
    SteeringAgentMixin,
    SubagentStartHookAgentMixin,
    SubagentStopHookAgentMixin,
    TemporaryClonedDirEnvMixin,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine, Mapping, Sequence
    from pathlib import Path, PurePosixPath

    import pydantic

    from hmz.coganchor.machines import MachineConfig
    from hmz.flows import (
        EnvBackendKind,
        HarnessKind,
        HookResult,
        Permission,
        Usage,
    )

__all__ = [
    "AGENT_CAPABILITIES",
    "ENV_CAPABILITIES",
    "HARNESS_CAPABILITIES",
    "AgentDriver",
    "BoundHook",
    "EnvDriver",
    "HookBridge",
    "HookTable",
    "Limits",
    "OutworlderDriver",
    "Placement",
    "SessionHandle",
    "Skill",
    "TurnRequest",
    "UsageSink",
    "capabilities_of",
    "default_result",
]

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- capabilities

#: Every mixin an agent role can be declared with, which is every capability an
#: :class:`AgentDriver` can list.
AGENT_CAPABILITIES: frozenset[type] = frozenset(
    {
        GoalCommandAgentMixin,
        LoopCommandAgentMixin,
        SteeringAgentMixin,
        PermissionRequestHookAgentMixin,
        SubagentStartHookAgentMixin,
        SubagentStopHookAgentMixin,
        AskUserHookAgentMixin,
    }
)

#: Every behaviour an environment role can be declared with, which is every capability an
#: :class:`EnvDriver` can list. The resource mixins -- CPUs, memory, GPUs -- are not among
#: them: those are amounts, compared against what a driver reports rather than listed.
ENV_CAPABILITIES: frozenset[type] = frozenset(
    {
        ShellEnvMixin,
        BashEnvMixin,
        FilesEnvMixin,
        GitWorktreeEnvMixin,
        TemporaryClonedDirEnvMixin,
        ScratchDirEnvMixin,
    }
)

_CAPABILITIES = AGENT_CAPABILITIES | ENV_CAPABILITIES


def capabilities_of(declared: type) -> frozenset[type]:
    """The capabilities a role's declared type asks for, read off its bases.

    Args:
      declared: The type a role is annotated with, such as `class Coder(Agent,
        SteeringAgentMixin)`, or a harness's own protocol.

    Returns:
      Every agent or environment capability among its bases. A mixin's own bases come with
      it: `BashEnvMixin` is `ShellEnvMixin` too.
    """
    return frozenset(one for one in declared.__mro__ if one in _CAPABILITIES)


#: What each harness's driver serves, which is exactly what its protocol in
#: :data:`hmz.flows.HARNESS_AGENTS` declares -- the one table both are read from.
HARNESS_CAPABILITIES: Mapping[HarnessKind, frozenset[type]] = MappingProxyType(
    {kind: capabilities_of(protocol) for kind, protocol in HARNESS_AGENTS.items()}
)

# ------------------------------------------------------------------------------ one turn


@dataclass(frozen=True, slots=True)
class Placement:
    """Where an agent's session works, which is the one thing an env tells an agent driver.

    Attributes:
      backend: Which kind of machine.
      provider: Which one of that kind: the ssh host, or "" for this machine.
      workdir: The directory on it the session works in; `~/...` is under the home of
        whoever ssh logs in as.
      machine: How coganchor reaches that machine for an agent whose turns land there, or
        None for this machine.
    """

    backend: EnvBackendKind
    provider: str
    workdir: PurePosixPath
    machine: MachineConfig | None = None


@dataclass(frozen=True, slots=True)
class Skill:
    """One skill a session is given.

    Attributes:
      name: What it is called, which is the directory its CLI finds it under.
      at: The directory on this machine holding its `SKILL.md`. The driver mounts or copies
        it wherever its CLI looks, on whichever machine the session works on.
    """

    name: str
    at: Path


@dataclass(frozen=True, slots=True)
class Limits:
    """What remains for one turn to spend, all budgets it runs under taken together.

    A driver maps these onto its CLI's own per-turn limits. When `graceful` is False and one
    is reached mid-turn, the driver stops the turn at once -- the CLI stops spending -- and
    raises the :class:`~hmz.flows.errors.BudgetExceeded` leaf for it. When `graceful` is
    True it lets the turn run to its end and answers as usual; the engine refuses the next.

    Attributes:
      cost: USD, or None for no limit.
      output_tokens: Tokens the agent may write, or None for no limit.
      deadline: When the turn must be over, on `time.monotonic()`'s clock, or None.
      graceful: Whether a limit reached mid-turn lets the turn finish.
    """

    cost: float | None = None
    output_tokens: int | None = None
    deadline: float | None = None
    graceful: bool = True


@dataclass(frozen=True, slots=True)
class TurnRequest:
    """One turn, as the engine asks a session for it.

    Attributes:
      prompt: What to say. One beginning `/goal ` or `/loop ` is the harness's own goal or
        loop command, which the driver carries out as its harness does; the engine sends
        one only to a driver that lists the mixin for it.
      output_schema: The model the answer must be an instance of, or None for text.
      limits: What the turn may spend.
    """

    prompt: str
    output_schema: type[pydantic.BaseModel] | None = None
    limits: Limits = Limits()


class UsageSink(Protocol):
    """Where a turn reports what it spends, as it spends it.

    The engine's: it rolls usage up to every flow above the turn and checks budgets against
    it. A driver may call `add` any number of times in a turn, from any thread, with what was
    spent since the last call; everything a session's `usage` counts must have been added
    through the sink of the turn that spent it, by the time that turn returns or raises.
    """

    def add(self, *, cost: float, output_tokens: int, duration: float) -> None:
        """Adds what was spent since the last call.

        Args:
          cost: USD.
          output_tokens: Tokens the agent wrote.
          duration: Seconds of the turn's wall time.
        """
        ...


# ---------------------------------------------------------------------------------- hooks

#: A hook as the engine hangs it for a driver: given the session the moment arrived in and
#: that moment's fields -- the params of :data:`hmz.flows.HOOK_TYPES` less `ctx` and
#: `session` -- and answering with the moment's result.
type BoundHook = Callable[[SessionHandle, dict[str, Any]], Awaitable[HookResult]]


def default_result(kind: HookKind) -> HookResult:
    """What a moment comes to with no hook on it, which changes nothing.

    Args:
      kind: The moment.

    Returns:
      Its result type, built with no arguments.

    Raises:
      ValueError: For `OUTWORLDER_RUN`, whose answer has no default.
    """
    if kind is HookKind.OUTWORLDER_RUN:
        raise ValueError("an outworlder's run has no answer to default to")
    return HOOK_TYPES[kind][1]()


class HookTable:
    """The hooks hung on one agent, as its driver reaches them.

    The engine makes one per agent a flow is handed, hangs and takes down hooks on it as the
    flow calls `on_*`, and hands it to every session it opens of that agent -- so a hook hung
    after a session opened reaches that session too. A driver asks `kind in table` from
    whichever thread its moment arrives on, skips the moment when nothing is hung, and
    otherwise calls :meth:`fire` on the engine's loop, through a :class:`HookBridge` when it
    is on a thread of its own.

    A driver fires only the moments its harness reaches and its capabilities list; the
    engine hangs nothing else.
    """

    __slots__ = ("_hung",)

    def __init__(self) -> None:
        """Initializes a table with nothing hung on it."""
        self._hung: dict[HookKind, BoundHook] = {}

    def set(self, kind: HookKind, hook: BoundHook | None) -> None:
        """Hangs a hook on a moment, replacing the one there, or takes it down with None."""
        if hook is None:
            self._hung.pop(kind, None)
        else:
            self._hung[kind] = hook

    def get(self, kind: HookKind) -> BoundHook | None:
        """The hook on a moment, or None."""
        return self._hung.get(kind)

    def __contains__(self, kind: object) -> bool:
        return kind in self._hung

    async def fire(
        self, kind: HookKind, handle: SessionHandle, /, **fields: Any
    ) -> HookResult:
        """Calls the hook on a moment, on the engine's loop.

        What a hook raises is the engine's to act on -- it fails the flow the agent belongs
        to -- and the engine's bound hook answers the default after it has; a driver can take
        whatever this returns as the answer.

        Args:
          kind: The moment.
          handle: The session it arrived in.
          **fields: The moment's own params: `tool` and `input` for `PRE_TOOL_USE`, `said`
            and `again` for `STOP`, and so on, as :data:`hmz.flows.HOOK_TYPES` names them.

        Returns:
          The hook's answer, or :func:`default_result` where nothing is hung.
        """
        hook = self._hung.get(kind)
        if hook is None:
            return default_result(kind)
        return await hook(handle, fields)


#: How often a wait on the engine's loop looks up to see whether the loop is still there.
_POLL = 0.25

#: Which threads are inside a bridged call right now, so that one never waits on itself.
_INSIDE = threading.local()


class HookBridge:
    """Carries a call from a driver's own thread onto the engine's loop, and waits for it.

    A coding agent CLI reaches a hook on whatever thread is reading it, and the hook is a
    coroutine of the flow's, on the engine's loop. This runs it there and blocks the calling
    thread until it answers -- or answers `default` instead, without waiting, whenever
    waiting would be wrong:

    - there is no loop, it is closed or stopped, or the bridge is closed;
    - the caller is the loop's own thread, where waiting would deadlock it, or a thread
      already inside a bridged call;
    - the call outlives `timeout`, or is abandoned by :meth:`abandon` or :meth:`close`;
    - the loop closes or stops while the call is waiting;
    - the coroutine raises, which is logged.

    A call that is given up on is cancelled on the loop. Thread-safe throughout.
    """

    __slots__ = ("_closed", "_flying", "_lock", "_loop", "timeout")

    def __init__(
        self, loop: asyncio.AbstractEventLoop | None, *, timeout: float | None = None
    ) -> None:
        """Initializes a bridge onto a loop.

        Args:
          loop: The engine's loop, or None for a bridge that answers every call with its
            default.
          timeout: How many seconds a call may wait, or None for as long as the loop runs.
        """
        self._loop = loop
        self.timeout = timeout
        self._closed = False
        self._flying: dict[concurrent.futures.Future[Any], threading.Event] = {}
        self._lock = threading.Lock()

    @classmethod
    def here(cls, *, timeout: float | None = None) -> HookBridge:
        """A bridge onto the loop running in this thread.

        Args:
          timeout: How many seconds a call may wait, or None for as long as the loop runs.

        Returns:
          The bridge.

        Raises:
          RuntimeError: If no loop is running here.
        """
        return cls(asyncio.get_running_loop(), timeout=timeout)

    def call[R](self, make: Callable[[], Coroutine[Any, Any, R]], *, default: R) -> R:
        """Runs a coroutine on the loop and answers with its result.

        Args:
          make: Makes the coroutine. Called only when it will be run, so that a call answered
            with its default leaves no coroutine unawaited behind it.
          default: The answer whenever the coroutine's cannot be had.

        Returns:
          The coroutine's result, or `default`.
        """
        loop = self._loop
        if (
            loop is None
            or self._closed
            or loop.is_closed()
            or not loop.is_running()
            or getattr(_INSIDE, "on", False)
            or _running() is loop
        ):
            return default
        # Set before `make` runs, so that a `make` which reaches for this bridge again is
        # answered its default rather than left waiting on the call it is part of.
        _INSIDE.on = True
        try:
            said = make()
            woke = threading.Event()
            with self._lock:
                if self._closed:
                    said.close()
                    return default
                try:
                    flying = asyncio.run_coroutine_threadsafe(said, loop)
                except RuntimeError:
                    said.close()
                    return default
                self._flying[flying] = woke
            flying.add_done_callback(lambda _: woke.set())
            try:
                return self._waited(loop, flying, woke, default)
            finally:
                with self._lock:
                    self._flying.pop(flying, None)
        finally:
            _INSIDE.on = False

    def _waited[R](
        self,
        loop: asyncio.AbstractEventLoop,
        flying: concurrent.futures.Future[R],
        woke: threading.Event,
        default: R,
    ) -> R:
        """Waits for a scheduled call, or for it to be given up on.

        `woke` is set when the call is done and when it is abandoned, and the loop is looked
        at every so often in between, so that a thread never outlives the loop it waits on.
        """
        deadline = None if self.timeout is None else time.monotonic() + self.timeout
        while not flying.done():
            if loop.is_closed():
                # Nothing will run it now, and cancelling it would reach for the closed loop.
                return default
            wait = (
                _POLL if deadline is None else min(_POLL, deadline - time.monotonic())
            )
            if wait <= 0 or woke.is_set() or not loop.is_running():
                flying.cancel()
                return default
            woke.wait(wait)
        try:
            raised = flying.exception()
        except concurrent.futures.CancelledError:
            return default
        if raised is not None:
            log.error("a hook bridged onto the engine's loop raised", exc_info=raised)
            return default
        return flying.result()

    def abandon(self) -> None:
        """Gives up on every call waiting now: each answers its default at once."""
        with self._lock:
            waking = list(self._flying.values())
        for woke in waking:
            woke.set()

    def close(self) -> None:
        """Abandons every waiting call, and answers every later one with its default."""
        with self._lock:
            self._closed = True
        self.abandon()


def _running() -> asyncio.AbstractEventLoop | None:
    """The loop running in this thread, if one is."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


# -------------------------------------------------------------------------------- drivers


class SessionHandle(Protocol):
    """One session of one agent driver: one conversation with its CLI.

    Every method may be called from the engine's loop; :meth:`interrupt` from any thread.
    """

    @property
    def id(self) -> str | None:
        """The CLI's own id for the conversation, or None before it has said one."""
        ...

    @property
    def usage(self) -> Usage:
        """Everything this session's turns have spent, up to the moment it is read."""
        ...

    async def turn(
        self, request: TurnRequest, sink: UsageSink
    ) -> str | pydantic.BaseModel:
        """Takes one turn.

        One at a time: the engine never overlaps two turns of one session.

        Args:
          request: The prompt, the schema and the limits.
          sink: Where to report what the turn spends, as it spends it.

        Returns:
          What the agent said, or an instance of `request.output_schema`.

        Raises:
          OutputSchemaError: If the answer could not be read as the schema.
          BudgetExceeded: The leaf for a limit reached when `limits.graceful` is False.
          SessionError: If the session is closed, or was interrupted mid-turn.
          HarnessError: The leaf for why the CLI could not take the turn.
          asyncio.CancelledError: If the awaiting task was cancelled. The CLI has stopped.
        """
        ...

    async def steer(self, prompt: str, *, queued: bool) -> None:
        """Puts a prompt into the turn in flight.

        Called only on a driver that lists `SteeringAgentMixin`.

        Args:
          prompt: What to say.
          queued: Whether the agent takes it when it next looks, or the turn is interrupted
            and goes on from it. Either way the turn in flight answers once, at its end.

        Raises:
          SessionError: If no turn is in flight.
        """
        ...

    def interrupt(self) -> None:
        """Stops the turn in flight, if any, from any thread.

        Idempotent, and a no-op with no turn in flight. The CLI stops spending before this
        returns or soon after; the interrupted `turn` raises `SessionError`. The session
        stays open for more turns.
        """
        ...

    async def close(self) -> None:
        """Ends the session, interrupting a turn in flight. Idempotent."""
        ...


class AgentDriver(Protocol):
    """One coding agent CLI -- harness, account, model, effort -- that sessions are opened of.

    `capabilities` is exactly what the harness serves, which is
    :data:`HARNESS_CAPABILITIES` for its harness.
    """

    @property
    def harness(self) -> HarnessKind: ...

    @property
    def model(self) -> str: ...

    @property
    def effort(self) -> str:
        """The effort, in the harness's own words; "" for the harness's default."""
        ...

    @property
    def provider(self) -> str:
        """The account turns run as, or "" for whoever this machine's CLI is logged in as."""
        ...

    @property
    def capabilities(self) -> frozenset[type]:
        """The agent mixins of :mod:`hmz.flows` this driver serves."""
        ...

    async def open(
        self,
        placement: Placement,
        *,
        permission: Permission,
        skills: tuple[Skill, ...],
        hooks: HookTable,
        fork_of: SessionHandle | None = None,
    ) -> SessionHandle:
        """Opens a session.

        Args:
          placement: Where it works.
          permission: What it may touch, mapped onto the CLI's own sandbox and approval
            settings. Approvals are always bypassed or answered yes -- never reviewed by a
            model -- and `online` maps onto the CLI's web access.
          skills: What skills it is given.
          hooks: What is hung on the agent, which the session reaches as its moments arrive.
          fork_of: A session of this driver to carry on from, or None for a fresh one.

        Returns:
          The session.

        Raises:
          UnsupportedOperation: If `fork_of` is given and the harness cannot fork, or not
            into `placement`.
          HarnessNotInstalled: If the CLI is not installed where `placement` is.
          HarnessError: The leaf for why the CLI could not be started.
        """
        ...

    async def close(self) -> None:
        """Closes every session still open and lets go of the CLI. Idempotent."""
        ...


class EnvDriver(Protocol):
    """One working directory on one machine.

    Paths given to it are relative to `workdir` unless absolute. Everything it derives is a
    driver of its own, on the same machine, with the same capabilities.
    """

    @property
    def backend(self) -> EnvBackendKind: ...

    @property
    def provider(self) -> str:
        """The ssh host, or "" for this machine."""
        ...

    @property
    def workdir(self) -> PurePosixPath:
        """Absolute, or `~/...` under the home of whoever ssh logs in as."""
        ...

    @property
    def capabilities(self) -> frozenset[type]:
        """The environment mixins of :mod:`hmz.flows` this driver serves.

        Closed under the mixins' own bases: a driver listing `BashEnvMixin` lists
        `ShellEnvMixin` too.
        """
        ...

    @property
    def cpu_count(self) -> int:
        """Logical CPUs of the machine."""
        ...

    @property
    def memory(self) -> int:
        """Memory of the machine, in bytes."""
        ...

    @property
    def gpu_count(self) -> int: ...

    @property
    def gpu_memory(self) -> int:
        """Memory of the smallest GPU, in bytes; 0 with no GPU."""
        ...

    @property
    def available(self) -> bool:
        """Whether the machine was reachable and the workdir there, as last seen. Never blocks."""
        ...

    def placement(self) -> Placement:
        """Where an agent session working here is put."""
        ...

    async def derive_subdir(self, subdir: PurePosixPath | str) -> EnvDriver:
        """A driver at a directory under this workdir, made if missing.

        Raises:
          ValueError: If `subdir` is absolute or climbs out of the workdir.
          EnvError: If it could not be made.
        """
        ...

    async def exec(
        self,
        argv: Sequence[str] | str,
        *,
        timeout: float,  # noqa: ASYNC109 -- the command's, enforced by killing it
    ) -> tuple[int, str, str]:
        """Runs a program, or a bash script given as a string, in the workdir.

        Args:
          argv: The program and its arguments, run with no shell; or a script, run by bash.
          timeout: Seconds it may take, or 0 for no limit.

        Returns:
          The exit status, stdout and stderr, decoded as UTF-8 with errors replaced.

        Raises:
          EnvCommandTimeout: If it ran past `timeout`. It and its children were killed.
          EnvError: The leaf for why it could not be started.
          asyncio.CancelledError: If the awaiting task was cancelled. It was killed.
        """
        ...

    async def read(self, path: str) -> bytes:
        """What a file holds.

        Raises:
          EnvFileNotFound: If it is not there.
          EnvPermissionDenied: If it may not be read.
        """
        ...

    async def write(self, path: str, data: bytes) -> None:
        """Writes a file whole, making the directories above it.

        Raises:
          EnvPermissionDenied: If it may not be written.
        """
        ...

    async def derive_worktree(
        self,
        *,
        ref: str | None,
        dir: PurePosixPath | str | None,  # noqa: A002 -- the flow API's name for it
    ) -> EnvDriver:
        """A driver at a new git worktree of the repository the workdir is in.

        Args:
          ref: What to check out, detached; None for the workdir's `HEAD`.
          dir: Where; None for a fresh directory the driver picks.

        Raises:
          WorktreeError: Not a repository, an unknown ref, or a directory that is taken.
        """
        ...

    async def derive_temp_clone(
        self,
        id: str,  # noqa: A002 -- the flow API's name for it
        *,
        holder: object,
    ) -> EnvDriver:
        """A driver at a temporary copy of the workdir.

        Ids are this driver's own. The first call for an id makes the copy and gives it to
        `holder`; later calls by an equal holder answer the same copy, and calls by any other
        raise. Copies are made cheaply where the filesystem can (reflinks).

        Raises:
          TempCloneBusy: If another holder holds the id.
          EnvError: If the copy could not be made.
        """
        ...

    async def destroy_temp_clone(self, id: str) -> None:  # noqa: A002 -- the flow API's
        """Removes a copy and frees its id, whoever holds it. A no-op for an unknown id."""
        ...

    async def derive_scratch(self, id: str) -> EnvDriver:  # noqa: A002 -- the flow API's
        """A driver at an empty directory on the same machine, the same one for the same id.

        Raises:
          ScratchError: If it could not be made.
        """
        ...

    async def destroy_scratch(self, id: str) -> None:  # noqa: A002 -- the flow API's
        """Removes a scratch directory. A no-op for an unknown id.

        Raises:
          ScratchError: If it could not be removed.
        """
        ...

    async def close(self) -> None:
        """Lets go of the machine: connections, and processes still running. Idempotent.

        Does not remove temporary copies or scratch directories; the engine does that.
        """
        ...


class OutworlderDriver(Protocol):
    """Whoever is outside the run, taking turns as an agent of it."""

    @property
    def away(self) -> bool:
        """Whether nobody is there to answer. It may change at any time."""
        ...

    async def run(
        self, prompt: str, output_schema: type[pydantic.BaseModel] | None
    ) -> str | pydantic.BaseModel:
        """Asks, and waits for the answer.

        The engine answers for an away outworlder itself and does not call this while it is
        away.

        Args:
          prompt: What to ask.
          output_schema: The model the answer is an instance of, or None for text.

        Returns:
          The answer.

        Raises:
          OutworlderAway: If it went away while this was waiting. The engine answers as an
            away outworlder would.
        """
        ...

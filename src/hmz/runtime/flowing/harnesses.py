"""The agent drivers: one :class:`~hmz.runtime.flowing.spi.AgentDriver` per coding agent CLI.

Each is coganchor's own driver for its CLI, held so that it keeps what
:mod:`hmz.runtime.flowing.spi` promises. What a harness can be asked for is
:data:`~hmz.runtime.flowing.spi.HARNESS_CAPABILITIES`; how a
:class:`~hmz.flows.Permission` reaches its CLI, and what a hook's answer does there, is
:mod:`hmz.runtime.flowing.harnessing`.

A session is a coganchor agent of its own and one conversation of it. The agent is what
coganchor settles everything a session runs by on -- the rung, the web, the skills, the
machine, the hooks and the person a question goes to -- and two sessions of one flow agent may
differ in every one of those, so each has its own; they share the CLI, the account and the
model, which is the driver.

A turn is a coganchor turn on a thread of its own, so the engine's loop is never held by one.
Around it, on the loop, the driver fires the hooks that bracket a turn -- SESSION_START before
the first, USER_PROMPT_SUBMIT before each, STOP after each, SESSION_END as the session closes
-- and takes the turn again where a STOP hook or a steer sends the agent on. The moments that
arrive from inside the CLI -- a tool, a permission, a notification, a subagent, a question --
come on coganchor's threads and reach the engine's hooks through a
:class:`~hmz.runtime.flowing.spi.HookBridge`, which answers as if nothing were hung once a
hook has kept one waiting for :data:`HOOK_TIMEOUT` -- a question excepted, which waits for a
person. A hook hung while a turn is running reaches the moments of that turn that come later,
except the few that decide how a CLI is started, which take hold from the next turn:
PRE_TOOL_USE on a CLI that gates its tools with a hook table of its own, and the hooks
:mod:`~hmz.runtime.flowing.harnessing` starts a CLI asking for -- Codex's `untrusted`
approvals and its asking feature, whose app server is started again between two turns for
it, and Kimi Code's and ZCode's asking rung.

What a hook answers is done where the CLI waits for it. A PRE_TOOL_USE hook refuses a tool on
a CLI that gates its tools (Claude Code, Qwen Code) and watches one already reached for on
the rest; a PERMISSION_REQUEST refusal is the tool refused, its reason told to the agent -- on
Codex, whose refusals carry none, as a steer into the turn; SUBAGENT_START and SUBAGENT_STOP
are told, no CLI waiting on either, so what their hooks answer changes nothing.

A prompt that is `/goal <objective>` is the harness's own goal, on a harness that has one; every
other prompt, `/loop` included, goes to the CLI as it is. A turn's
:class:`~hmz.runtime.flowing.spi.Limits` are held by the driver: what it spends is read as the
CLI reports it, priced with :func:`hmz.coganchor.prices.cost` -- a model nobody prices costs
nothing there. A graceful turn runs to its end and answers as usual, whatever it spends, the
engine refusing the next; one that is not graceful is cut off the moment a limit is reached --
the CLI stops spending -- and raises the :class:`~hmz.flows.errors.BudgetExceeded` leaf.

A fork is the CLI's own: Claude Code, Codex, Kimi Code and ZCode fork into another workdir,
every other harness that forks does so only into the workdir it is in, and cursor-agent,
Antigravity and dsh do not fork. A fork is cut where its first turn is taken, so it is refused
then if the session it came from has taken a turn since.

:func:`open_outworlder` is the driver for whoever is outside the run.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import datetime
import os
import threading
import time
from typing import TYPE_CHECKING, Any, Final

from hmz.flows import (
    AskUserHookAgentMixin,
    CostExceeded,
    DurationExceeded,
    GoalCommandAgentMixin,
    HarnessKind,
    HarnessNotInstalled,
    HarnessUnrecoverable,
    HookKind,
    OutputTokensExceeded,
    OutworlderAway,
    PermissionRequestHookAgentMixin,
    SessionError,
    SessionStartHookResult,
    SteeringAgentMixin,
    StopHookResult,
    SubagentStartHookAgentMixin,
    UnsupportedOperation,
    Usage,
    UserPromptSubmitHookResult,
)

from . import harnessing
from .spi import HARNESS_CAPABILITIES, HookBridge

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    import pydantic

    from hmz.coganchor.agents import (
        AgentBase,
        AgentConfig,
        Event,
        Hung,
        Occasion,
        Question,
        SessionBase,
        Verdict,
    )
    from hmz.coganchor.backends import Profile
    from hmz.coganchor.machines import MachineConfig
    from hmz.flows import BudgetExceeded, HookResult, Permission

    from .specs import AgentSpec
    from .spi import (
        HookTable,
        Limits,
        OutworlderDriver,
        Placement,
        SessionHandle,
        Skill,
        TurnRequest,
        UsageSink,
    )

__all__ = [
    "HarnessDriver",
    "HarnessSession",
    "HumanOutworlder",
    "Listener",
    "open_agent",
    "open_outworlder",
]

#: What is told everything a session's CLI says, as coganchor says it: the agent, the
#: conversation, and the event. How a way in shows a run.
type Listener = Callable[[AgentBase, SessionBase | None, Event], None]

#: The prefix of a prompt that is the harness's own goal.
_GOAL: Final = "/goal "

#: How often a turn's spending is read while nothing it says has been heard.
_POLL: Final = 1.0

#: How often a turn that was cut off is cut again while it has not ended.
_RECUT: Final = 1.0

#: How long a cancelled turn is waited for to end before `CancelledError` leaves it.
_DRAIN: Final = 30.0

#: The CLIs whose answer to a permission request carries no reason, which a refusal's reason
#: is steered into the turn for instead: Codex's approvals are a decision and nothing else.
_REASONLESS: Final = frozenset({HarnessKind.CODEX})

#: The moments whose hook decides whether a tool runs.
_GATES: Final = frozenset({HookKind.PRE_TOOL_USE, HookKind.PERMISSION_REQUEST})

#: The hooks whose being hung decides how a session's CLI is started or its rung.
_STARTING: Final = frozenset(
    {HookKind.PRE_TOOL_USE, HookKind.PERMISSION_REQUEST, HookKind.ASK_USER}
)

#: How long a moment from inside a CLI -- a tool, a permission, a notification, a subagent --
#: waits on the flow's hook before it is answered as if nothing were hung: as long as a CLI's
#: own hook table waits on one, so that a hook that never answers cannot hold a turn for
#: good. A question to the user waits for as long as the loop runs; a person is its answer.
HOOK_TIMEOUT: float = 900.0


def open_agent(spec: AgentSpec) -> HarnessDriver:
    """Makes the driver for one `-a`.

    Starts nothing and looks for nothing: the CLI is reached when the first session opens,
    which is also where one not installed where the session works is refused -- this does not
    know yet which machine that is.

    Args:
      spec: The agent.

    Returns:
      A driver of `spec.harness` whose capabilities are exactly that harness's in
      :data:`~hmz.runtime.flowing.spi.HARNESS_CAPABILITIES`.

    Raises:
      HarnessNotInstalled: For a CLI added by hand that nobody has added on this machine.
      HarnessUnrecoverable: For a model, effort or account the CLI cannot be configured at.
    """
    from hmz.coganchor import backends
    from hmz.coganchor.agents import driver
    from hmz.coganchor.agents.base import identifying

    try:
        kind, made = driver(spec.cli)
    except KeyError:
        raise HarnessNotInstalled(
            f"{spec.cli}: no such CLI has been added on this machine"
        ) from None
    profile = backends.named(spec.cli)
    try:
        config = made(
            model=spec.model,
            effort=spec.effort,
            provider=spec.provider,
            **identifying(made, spec.cli),
        )
        # Built once and let go, which is where coganchor refuses an effort, a rung or a
        # tier the CLI has no word for -- said here rather than at the first session.
        kind(config)
    except ValueError as refused:
        raise HarnessUnrecoverable(f"{spec}: {refused}") from refused
    return HarnessDriver(spec, kind, config, profile)


class HarnessDriver:
    """The driver of one CLI at one account, model and effort; see the module docstring."""

    __slots__ = (
        "_capabilities",
        "_closed",
        "_config",
        "_installed",
        "_kind",
        "_listeners",
        "_profile",
        "_sessions",
        "_spec",
    )

    def __init__(
        self,
        spec: AgentSpec,
        kind: type[AgentBase],
        config: AgentConfig,
        profile: Profile | None,
    ) -> None:
        """Initializes a driver that has opened nothing.

        Args:
          spec: The agent, as `-a` named it.
          kind: coganchor's agent class for the CLI.
          config: What every session's agent is configured with before its own settings.
          profile: What coganchor knows of the CLI, or None for one it knows nothing of.
        """
        self._spec = spec
        self._kind = kind
        self._config = config
        self._profile = profile
        self._capabilities = HARNESS_CAPABILITIES[spec.harness]
        self._listeners: list[Listener] = []
        self._sessions: set[HarnessSession] = set()
        self._closed = False
        self._installed = False

    @property
    def harness(self) -> HarnessKind:
        """Which CLI it is."""
        return self._spec.harness

    @property
    def model(self) -> str:
        """The model its sessions run."""
        return self._spec.model

    @property
    def effort(self) -> str:
        """The effort, in the harness's own words; "" for the harness's default."""
        return self._spec.effort

    @property
    def provider(self) -> str:
        """The account turns run as, or "" for whoever this machine's CLI is logged in as."""
        return self._spec.provider

    @property
    def capabilities(self) -> frozenset[type]:
        """The agent mixins of :mod:`hmz.flows` this driver serves."""
        return self._capabilities

    @property
    def spec(self) -> AgentSpec:
        """The agent, as `-a` named it."""
        return self._spec

    @property
    def tellable(self) -> bool:
        """Whether the CLI can be told whether its agent may use the web."""
        return self._profile is not None and self._profile.searches

    def watch(self, listener: Listener) -> None:
        """Has everything the CLI says in every session opened from now on reach `listener`.

        coganchor stops writing a watched agent's words to this process's own stdout and
        stderr, and every session here is watched for what it spends -- so a way in that
        shows a run shows it through this.

        Args:
          listener: What to tell, from whichever thread the CLI is read on.
        """
        self._listeners.append(listener)

    async def open(
        self,
        placement: Placement,
        *,
        permission: Permission,
        skills: tuple[Skill, ...],
        hooks: HookTable,
        fork_of: SessionHandle | None = None,
    ) -> HarnessSession:
        """Opens a session, which starts no CLI until its first turn.

        Args:
          placement: Where it works.
          permission: What it may touch, as :mod:`hmz.runtime.flowing.harnessing` maps it.
          skills: What skills it is given, mounted where its CLI reads them.
          hooks: What is hung on the agent.
          fork_of: A session of this driver to carry on from, or None for a fresh one.

        Returns:
          The session.

        Raises:
          SessionError: If the driver is closed, `fork_of` is not an open session of it that
            has taken a turn, or the workdir is not a directory here.
          UnsupportedOperation: If the harness cannot fork, or not into `placement`.
          HarnessNotInstalled: If the CLI is not installed on this machine and the session
            works here.
          HarnessUnrecoverable: If the CLI cannot be configured as the session asks.
        """
        if self._closed:
            raise SessionError("the agent's driver is closed")
        parent = self._parent(fork_of, placement)
        cwd = self._where(placement)
        if placement.machine is None:
            self._check_installed()
        hung = frozenset(kind for kind in _STARTING if kind in hooks)
        config = self._configured(permission, placement, hung)
        agent, session = await asyncio.to_thread(
            self._made, config, skills, parent, cwd
        )
        handle = HarnessSession(
            self,
            agent,
            session,
            hooks=hooks,
            placement=placement,
            permission=permission,
            bridge=HookBridge.here(timeout=HOOK_TIMEOUT),
        )
        if self._closed:
            # Closed while the session was being made, so it is closed with the rest.
            await handle.close()
            raise SessionError("the agent's driver is closed")
        self._sessions.add(handle)
        return handle

    def _parent(
        self, fork_of: SessionHandle | None, placement: Placement
    ) -> HarnessSession | None:
        """The session a fork is cut from, checked against where the fork is to work.

        Raises:
          SessionError: If it is not an open session of this driver that has taken a turn.
          UnsupportedOperation: If the harness cannot fork there.
        """
        if fork_of is None:
            return None
        if not isinstance(fork_of, HarnessSession) or fork_of.driver is not self:
            raise SessionError(
                "a session is forked only by the agent it is a session of"
            )
        if fork_of.closed:
            raise SessionError("the session to fork is closed")
        if fork_of.id is None:
            raise SessionError("the session to fork has taken no turn to carry on from")
        if self._profile is None or not self._profile.forks:
            raise UnsupportedOperation(f"{self.harness} cannot fork a session")
        was = fork_of.placement
        if was.machine != placement.machine:
            raise UnsupportedOperation(
                f"{self.harness} cannot fork a session onto another machine"
            )
        if (
            was.workdir != placement.workdir
            and not type(fork_of.coganchor).forks_elsewhere
        ):
            raise UnsupportedOperation(
                f"{self.harness} cannot fork a session into another workdir"
            )
        return fork_of

    @staticmethod
    def _where(placement: Placement) -> str | None:
        """The directory a session's conversation is opened at, as coganchor takes it.

        Raises:
          SessionError: If it is on this machine and is not a directory.
        """
        workdir = str(placement.workdir)
        if placement.machine is not None:
            # A remote workdir under the login's home is the anchor's own workspace, which is
            # where a session opened at no directory works.
            return workdir if placement.workdir.is_absolute() else None
        where = os.path.expanduser(workdir)  # noqa: PTH111 -- a string path, as coganchor takes
        if not os.path.isdir(where):  # noqa: PTH112
            raise SessionError(f"{where} is not a directory to open a session in")
        return where

    def _check_installed(self) -> None:
        """Refuses a CLI that is not installed on this machine, looked for once.

        Raises:
          HarnessNotInstalled: If it is not.
        """
        if self._installed:
            return
        from hmz.coganchor import backends

        command = self._profile.name if self._profile is not None else self._spec.cli
        if backends.program(command) is None:
            raise HarnessNotInstalled(
                f"{command} is not installed here: {backends.installing(self._spec.cli)}"
            )
        self._installed = True

    def _configured(
        self, permission: Permission, placement: Placement, hung: frozenset[HookKind]
    ) -> AgentConfig:
        """What a session's own agent is configured with.

        Raises:
          HarnessUnrecoverable: If the CLI cannot be configured so.
        """
        return settled(
            self._config,
            self.harness,
            self._kind,
            permission,
            hung,
            tellable=self.tellable,
            machine=placement.machine,
        )

    def _made(
        self,
        config: AgentConfig,
        skills: tuple[Skill, ...],
        parent: HarnessSession | None,
        cwd: str | None,
    ) -> tuple[AgentBase, SessionBase]:
        """Builds a session's own agent and its conversation, on a thread of its own.

        Raises:
          HarnessUnrecoverable: If the agent cannot be built as configured.
          UnsupportedOperation: If the CLI will not fork into `cwd`.
          SessionError: If the session to fork cannot be carried on from.
        """
        from hmz.coganchor.agents.skills import Loaded

        try:
            agent = self._kind(config)
        except ValueError as refused:
            raise HarnessUnrecoverable(f"{self._spec}: {refused}") from refused
        agent.loads(Loaded(name=one.name, at=one.at) for one in skills)
        for listener in self._listeners:
            agent.watch(listener)
        if parent is None:
            return agent, agent.new(cwd)
        try:
            return agent, parent.coganchor.fork(into=agent, cwd=cwd)
        except NotImplementedError as refused:
            raise UnsupportedOperation(str(refused)) from refused
        except (RuntimeError, ValueError, OSError) as refused:
            raise SessionError(f"the session cannot be forked: {refused}") from refused

    def forget(self, session: HarnessSession) -> None:
        """Drops a session that has closed from those the driver closes."""
        self._sessions.discard(session)

    async def close(self) -> None:
        """Closes every session still open, and opens no more. Idempotent."""
        self._closed = True
        sessions, self._sessions = list(self._sessions), set()
        await asyncio.gather(*(one.close() for one in sessions))


def settled(
    config: AgentConfig,
    harness: HarnessKind,
    kind: type[AgentBase],
    permission: Permission,
    hung: frozenset[HookKind],
    *,
    tellable: bool,
    machine: MachineConfig | None = None,
) -> AgentConfig:
    """A driver's config, set up for one session given the hooks hung on it now.

    Args:
      config: The driver's own config.
      harness: The CLI.
      kind: coganchor's agent class for it, whose rungs the rung is one of.
      permission: What the session may touch.
      hung: The hooks among :data:`_STARTING` hung on the agent.
      tellable: Whether the CLI can be told about the web.
      machine: The machine its turns land on, or None for this one.

    Returns:
      The config.

    Raises:
      HarnessUnrecoverable: If the CLI cannot be configured so.
    """
    from hmz.coganchor.agents import CodexAgentConfig

    changes: dict[str, Any] = {
        "permission": harnessing.rung(harness, permission, rungs=kind.rungs, hung=hung),
        "web_search": harnessing.searching(permission, tellable=tellable),
        "machine": machine,
    }
    if isinstance(config, CodexAgentConfig):
        feature = harnessing.ASKING_FEATURE
        rest = tuple(one for one in config.features if one[0] != feature)
        asks = ((feature, True),) if HookKind.ASK_USER in hung else ()
        changes["features"] = rest + asks
        changes["approvals"] = harnessing.approvals(harness, hung)
    try:
        return dataclasses.replace(config, **changes)
    except ValueError as refused:
        raise HarnessUnrecoverable(str(refused)) from refused


class HarnessSession:
    """One session of a :class:`HarnessDriver`: one conversation with its CLI.

    Every method may be called from the engine's loop, and :meth:`interrupt` from any thread.
    """

    __slots__ = (
        "_agent",
        "_asking",
        "_bridge",
        "_closed",
        "_cost",
        "_driver",
        "_duration",
        "_flying",
        "_hooks",
        "_hung",
        "_interrupted",
        "_last",
        "_limits",
        "_lock",
        "_loop",
        "_over",
        "_permission",
        "_placement",
        "_pre",
        "_returned",
        "_rose",
        "_running",
        "_seen",
        "_session",
        "_sink",
        "_started",
        "_steer_cut",
        "_steers",
        "_take",
        "_timers",
        "_tokens",
        "_turn_cost",
        "_turn_tokens",
        "_written",
    )

    def __init__(
        self,
        driver: HarnessDriver,
        agent: AgentBase,
        session: SessionBase,
        *,
        hooks: HookTable,
        placement: Placement,
        permission: Permission,
        bridge: HookBridge,
    ) -> None:
        """Initializes a session that has taken no turn.

        Args:
          driver: The driver it is a session of.
          agent: Its own coganchor agent.
          session: Its conversation.
          hooks: What is hung on the flow agent it belongs to.
          placement: Where it works.
          permission: What it may touch.
          bridge: What carries moments from the CLI's threads to the engine's loop.
        """
        self._driver = driver
        self._loop = asyncio.get_running_loop()
        self._agent = agent
        self._session = session
        self._hooks = hooks
        self._placement = placement
        self._permission = permission
        self._bridge = bridge
        # A question waits on a person, for as long as the loop runs.
        self._asking = HookBridge(self._loop, timeout=None)
        self._lock = threading.Lock()
        # What the session has spent, and what of the CLI's own count has been read.
        self._cost = 0.0
        self._tokens = 0
        self._duration = 0.0
        self._written = 0.0
        self._seen: dict[str, float] = {}
        #: What the meter rose by in the coganchor turn now running, against which what its
        #: answer says it spent is read.
        self._rose: dict[str, float] = {}
        # The turn in flight, if one is.
        self._flying = False
        self._sink: UsageSink | None = None
        self._limits: Limits | None = None
        self._last = 0.0
        self._turn_cost = 0.0
        self._turn_tokens = 0
        self._over: type[BudgetExceeded] | None = None
        self._timers: list[asyncio.TimerHandle] = []
        self._interrupted = False
        self._steers: list[str] = []
        self._steer_cut = False
        # The coganchor call the turn is taking, and whether it is running.
        self._take = 0
        self._running = False
        self._returned = threading.Event()
        self._started = False
        self._closed = False
        self._pre: Hung | None = None
        self._hung = frozenset(kind for kind in _STARTING if kind in hooks)
        self._listen()

    # ---------------------------------------------------------------------- what it is

    @property
    def id(self) -> str | None:
        """The CLI's own id for the conversation, or None before it has said one."""
        return self._session.named

    @property
    def usage(self) -> Usage:
        """Everything this session's turns have spent, up to the moment it is read."""
        with self._lock:
            return Usage(
                duration=datetime.timedelta(seconds=self._duration),
                cost=self._cost,
                output_tokens=self._tokens,
            )

    @property
    def driver(self) -> HarnessDriver:
        """The driver it is a session of."""
        return self._driver

    @property
    def placement(self) -> Placement:
        """Where it works."""
        return self._placement

    @property
    def closed(self) -> bool:
        """Whether it has been closed."""
        return self._closed

    @property
    def coganchor(self) -> SessionBase:
        """Its conversation, as coganchor holds it."""
        return self._session

    @property
    def agent(self) -> AgentBase:
        """Its own coganchor agent."""
        return self._agent

    # ------------------------------------------------------------------------- moments

    def _listen(self) -> None:
        """Hangs what reaches the engine's hooks on the moments the CLI fires itself."""
        capabilities = self._driver.capabilities
        allowed = {
            HookKind.NOTIFICATION,
            *(
                (HookKind.PERMISSION_REQUEST,)
                if PermissionRequestHookAgentMixin in capabilities
                else ()
            ),
            *(
                (HookKind.SUBAGENT_START, HookKind.SUBAGENT_STOP)
                if SubagentStartHookAgentMixin in capabilities
                else ()
            ),
        }
        hooks = self._agent.hooks
        for moment in hooks.moments:
            kind = harnessing.MOMENTS.get(moment.value)
            if kind in allowed:
                hooks.on(moment, self._moment)
        if AskUserHookAgentMixin in capabilities:
            self._agent.ask = self._ask
        self._agent.watch(self._heard)
        self._settle_pre_tool_use()

    def _settle_pre_tool_use(self) -> None:
        """Hangs PRE_TOOL_USE on the CLI only while a hook is hung on it.

        A CLI that gates its tools with a hook table of its own is started with one only
        while something is hung there, since the table is a program it runs before every tool.
        """
        from hmz.coganchor.agents import Moment

        wanted = HookKind.PRE_TOOL_USE in self._hooks
        if wanted and self._pre is None:
            self._pre = self._agent.hooks.on(Moment.PRE_TOOL_USE, self._moment)
        elif not wanted and self._pre is not None:
            self._pre.off()
            self._pre = None

    def _moment(self, occasion: Occasion) -> Verdict | None:
        """Carries a moment the CLI fired to the engine's hook for it, on the CLI's thread."""
        kind = harnessing.MOMENTS[occasion.moment.value]
        if kind not in self._hooks:
            return None
        fields = harnessing.fields(kind, occasion)
        result = self._bridge.call(
            lambda: self._hooks.fire(kind, self, **fields),
            default=_default(kind),
        )
        said = harnessing.verdict(kind, result)
        if said is None and kind in _GATES and (self._closed or self._cut_off()):
            # The hook was given up on because the turn is being cut off: its tool is not
            # to run meanwhile, whatever the hook would have said.
            from hmz.coganchor.agents import Verdict

            return Verdict(refused=True, because="the turn was cut off")
        if (
            said is not None
            and kind is HookKind.PERMISSION_REQUEST
            and self._driver.harness in _REASONLESS
        ):
            # The CLI takes a refusal with no reason, so the reason is put into the turn.
            with contextlib.suppress(Exception):
                self._session.interject(
                    f"Using {occasion.tool or 'that tool'} was refused: {said.because}"
                )
        return said

    def _ask(self, question: Question) -> str | None:
        """Carries a question the agent stopped to ask to the engine's ASK_USER hook."""
        if HookKind.ASK_USER not in self._hooks:
            return None
        result = self._asking.call(
            lambda: self._hooks.fire(
                HookKind.ASK_USER,
                self,
                question=question.text,
                options=question.options,
            ),
            default=_default(HookKind.ASK_USER),
        )
        return harnessing.answer(result)

    async def _fire(self, kind: HookKind, **fields: Any) -> HookResult | None:
        """Fires a moment the driver brackets a turn with, on the loop, where one is hung."""
        if kind not in self._hooks:
            return None
        return await self._hooks.fire(kind, self, **fields)

    # -------------------------------------------------------------------------- a turn

    async def turn(
        self, request: TurnRequest, sink: UsageSink
    ) -> str | pydantic.BaseModel:
        """Takes one turn; see :meth:`hmz.runtime.flowing.spi.SessionHandle.turn`."""
        self._check_open()
        with self._lock:
            if self._flying:
                raise SessionError("a turn is already in flight in this session")
        limits = request.limits
        _refuse_spent(limits)
        goal = (
            request.prompt.startswith(_GOAL)
            and GoalCommandAgentMixin in self._driver.capabilities
        )
        body = request.prompt.removeprefix(_GOAL) if goal else request.prompt
        self._begin(sink, limits)
        try:
            if not self._started:
                self._started = True
                started = await self._fire(HookKind.SESSION_START)
                if isinstance(started, SessionStartHookResult) and started.context:
                    body = f"{started.context}\n\n{body}"
            submitted = await self._fire(
                HookKind.USER_PROMPT_SUBMIT, prompt=request.prompt
            )
            if isinstance(submitted, UserPromptSubmitHookResult):
                if submitted.block:
                    raise SessionError(submitted.reason or "a hook refused the prompt")
                if submitted.context:
                    body = f"{body}\n\n{submitted.context}"
            again = 0
            while True:
                said = await self._taken(body, request.output_schema, goal=goal)
                if self._over is not None:
                    break
                if self._interrupted:
                    raise SessionError("the turn was interrupted")
                if not self._steers:
                    stopping = await self._fire(HookKind.STOP, said=said, again=again)
                    if (
                        isinstance(stopping, StopHookResult)
                        and stopping.block
                        and stopping.reason
                    ):
                        body, goal, again = stopping.reason, False, again + 1
                        continue
                with self._lock:
                    steered, self._steers = self._steers, []
                if steered:
                    body, goal = "\n\n".join(steered), False
                    continue
                break
        finally:
            self._end()
        if self._over is not None and not limits.graceful:
            raise self._exceeded(self._over, limits)
        if self._interrupted:
            # Interrupted between two of the CLI's turns -- while a STOP hook was deciding --
            # which is the turn interrupted all the same.
            raise SessionError("the turn was interrupted")
        if request.output_schema is not None:
            return harnessing.read_shape(said, request.output_schema)
        return said

    def _begin(self, sink: UsageSink, limits: Limits) -> None:
        """Starts counting a turn: its sink, its limits and its clocks."""
        with self._lock:
            self._flying = True
            self._sink = sink
            self._limits = limits
            self._last = time.monotonic()
            self._turn_cost = 0.0
            self._turn_tokens = 0
            self._over = None
            self._interrupted = False
            self._steers = []
            self._steer_cut = False
        loop = self._loop
        if limits.deadline is not None and not limits.graceful:
            self._timers.append(
                loop.call_at(
                    loop.time() + (limits.deadline - time.monotonic()), self._deadline
                )
            )
        self._timers.append(loop.call_later(_POLL, self._poll))

    def _end(self) -> None:
        """Stops counting a turn: its clocks, and the last of what it spent."""
        for timer in self._timers:
            timer.cancel()
        self._timers = []
        self._account()
        with self._lock:
            sink, self._sink = self._sink, None
            now = time.monotonic()
            duration = now - self._last
            self._last = now
            self._duration += duration
            self._flying = False
        if sink is not None:
            sink.add(cost=0.0, output_tokens=0, duration=duration)

    async def _taken(
        self, body: str, schema: type[pydantic.BaseModel] | None, *, goal: bool
    ) -> str:
        """Takes one coganchor turn or goal on a thread of its own, and answers with its text.

        Returns:
          What the agent said, or "" for a turn cut off by an interrupt, a limit or a steer.

        Raises:
          SessionError: If the session was interrupted before the turn began.
          HarnessError: The leaf for why the CLI could not take the turn.
          asyncio.CancelledError: If the awaiting task was cancelled; the CLI has stopped.
        """
        loop = self._loop
        landed: asyncio.Future[str] = loop.create_future()
        # Retrieved whatever happens to it, so that a turn given up on leaves no warning.
        landed.add_done_callback(_retrieved)
        settle = self._settling()
        with self._lock:
            if self._interrupted:
                raise SessionError("the turn was interrupted")
            if self._over is not None:
                return ""
            self._take += 1
            take = self._take
            self._steer_cut = False
            returned = self._returned = threading.Event()
            steered, self._steers = self._steers, []
        if steered:
            body = "\n\n".join([body, *steered])
        threading.Thread(
            target=self._call,
            args=(loop, landed, take, returned, settle, body, schema, goal),
            name=f"{self._agent.id}-turn",
            daemon=True,
        ).start()
        try:
            return await asyncio.shield(landed)
        except asyncio.CancelledError:
            self.interrupt()
            await asyncio.wait({landed}, timeout=_DRAIN)
            raise
        except Exception as error:
            if self._cut_off():
                return ""
            leaf = harnessing.harness_error(error, self._agent.backend)
            if leaf is None:
                raise
            raise leaf from error

    def _call(
        self,
        loop: asyncio.AbstractEventLoop,
        landed: asyncio.Future[str],
        take: int,
        returned: threading.Event,
        settle: Callable[[], None] | None,
        body: str,
        schema: type[pydantic.BaseModel] | None,
        goal: bool,  # noqa: FBT001 -- positional, as a thread's arguments are
    ) -> None:
        """The coganchor call one turn is, on the thread it runs on."""
        try:
            said = self._called(take, settle, body, schema, goal=goal)
        except BaseException as why:  # noqa: BLE001 -- carried to the loop, not handled
            _posted(loop, _failed, landed, why)
        else:
            _posted(loop, _landed, landed, said)
        finally:
            with self._lock:
                if self._take == take:
                    self._running = False
            returned.set()

    def _called(
        self,
        take: int,
        settle: Callable[[], None] | None,
        body: str,
        schema: type[pydantic.BaseModel] | None,
        *,
        goal: bool,
    ) -> str:
        """Takes the turn, unless it was cut off before it could begin."""
        if settle is not None:
            settle()
        with self._lock:
            if self._take != take or self._cutting():
                return ""
            self._running = True
            self._rose = {}
        if goal:
            return self._session.pursue(body)
        said = ""
        for event in self._session.stream(body, schema=schema):
            if event.kind == "result":
                said = event.text
        return said.strip()

    def _settling(self) -> Callable[[], None] | None:
        """What to change about the CLI before the next turn, given the hooks hung now.

        Returns:
          What sets it up again, run on the turn's thread, or None where nothing changes.
        """
        self._settle_pre_tool_use()
        hung = frozenset(kind for kind in _STARTING if kind in self._hooks)
        if hung == self._hung:
            return None
        driver = self._driver
        was = self._agent.config
        now = settled(
            was,
            driver.harness,
            type(self._agent),
            self._permission,
            hung,
            tellable=driver.tellable,
            machine=self._placement.machine,
        )
        if now == was:
            self._hung = hung
            return None
        restart = getattr(now, "features", ()) != getattr(was, "features", ())
        agent, session = self._agent, self._session

        def settle() -> None:
            if restart:
                # The feature is an argument of the server, which is put down to start again.
                # Between two turns of this session, whose agent holds no other: nothing is
                # in flight on the server, and the next turn picks the conversation back up
                # on the one it starts.
                session.cut(why="started again to be asked what it asks")
            agent.reconfigure(now)
            # Written down only once it has been done, so that a turn which never got as far
            # as this leaves the next one to do it.
            self._hung = hung

        return settle

    # --------------------------------------------------------------------- what it spends

    def _heard(
        self, agent: AgentBase, session: SessionBase | None, event: Event
    ) -> None:
        """Reads what the turn has spent whenever the CLI says anything."""
        del agent, session
        self._account(event.spent if event.kind == "result" else None)

    def _poll(self) -> None:
        """Reads what the turn has spent, and again in a while, while one is in flight."""
        if not self._flying:
            return
        self._account()
        self._timers.append(self._loop.call_later(_POLL, self._poll))

    def _account(self, answered: Mapping[str, float] | None = None) -> None:
        """Reports what the CLI has said was spent since the last time, and checks limits.

        Read off the conversation's meter, which most of coganchor's drivers feed as each
        request lands, and off the answer a turn ends on, which states the whole turn: what
        the answer states beyond what the meter rose by in that turn is counted then, which
        is all of it for a driver that feeds no meter and nothing for one that feeds it all.

        Args:
          answered: What the answer a turn just ended on says it spent, or None.
        """
        from hmz.coganchor import prices
        from hmz.coganchor.agents import Usage as Tokens

        spent = self._session.spent()
        with self._lock:
            sink, limits = self._sink, self._limits
            if sink is None or limits is None:
                return
            rose = {
                kind: tokens - self._seen.get(kind, 0.0)
                for kind, tokens in spent.items()
                if tokens > self._seen.get(kind, 0.0)
            }
            if rose:
                self._seen = dict(spent)
                for kind, tokens in rose.items():
                    self._rose[kind] = self._rose.get(kind, 0.0) + tokens
            if answered is not None:
                for kind, tokens in answered.items():
                    if (beyond := tokens - self._rose.get(kind, 0.0)) > 0:
                        rose[kind] = rose.get(kind, 0.0) + beyond
                self._rose = {}
            if not rose:
                return
            cost = prices.cost(Tokens(rose), self._agent.config.model) or 0.0
            written = (
                self._written + rose.get("output", 0.0) + rose.get("reasoning", 0.0)
            )
            tokens = int(written) - int(self._written)
            self._written = written
            now = time.monotonic()
            duration = now - self._last
            self._last = now
            self._cost += cost
            self._tokens += tokens
            self._duration += duration
            self._turn_cost += cost
            self._turn_tokens += tokens
            over: type[BudgetExceeded] | None = None
            if limits.graceful:
                pass  # the turn runs to its end, and the engine refuses the next one
            elif limits.cost is not None and self._turn_cost >= limits.cost:
                over = CostExceeded
            elif (
                limits.output_tokens is not None
                and self._turn_tokens >= limits.output_tokens
            ):
                over = OutputTokensExceeded
        sink.add(cost=cost, output_tokens=tokens, duration=duration)
        if over is not None:
            self._overrun(over)

    def _deadline(self) -> None:
        """The deadline of a turn that is not graceful, on the loop: ends it now."""
        if self._flying:
            self._overrun(DurationExceeded)

    def _overrun(self, kind: type[BudgetExceeded]) -> None:
        """Ends the turn for a limit it reached, from whichever thread noticed."""
        with self._lock:
            if self._over is not None or not self._flying:
                return
            self._over = kind
        self._cut("its budget is spent")

    def _exceeded(self, kind: type[BudgetExceeded], limits: Limits) -> BudgetExceeded:
        """The error for a limit the turn reached."""
        if kind is CostExceeded:
            return CostExceeded(
                f"the turn spent ${self._turn_cost:.4f} of ${limits.cost or 0.0:.4f}"
            )
        if kind is OutputTokensExceeded:
            return OutputTokensExceeded(
                f"the turn wrote {self._turn_tokens} of {limits.output_tokens or 0} "
                "output tokens"
            )
        return DurationExceeded("the turn ran past its deadline")

    # ------------------------------------------------------------ steering and stopping

    async def steer(self, prompt: str, *, queued: bool) -> None:
        """Puts a prompt into the turn in flight; see the SPI's `SessionHandle.steer`."""
        self._check_open()
        if SteeringAgentMixin not in self._driver.capabilities:
            raise UnsupportedOperation(f"{self._driver.harness} cannot be steered")
        with self._lock:
            if not self._flying:
                raise SessionError("no turn is in flight to steer")
            running = self._running
            if not (queued and running):
                self._steers.append(prompt)
                if not queued:
                    self._steer_cut = True
        if not queued:
            self._cut("steered")
            return
        if not running:
            return
        try:
            await asyncio.to_thread(self._session.interject, prompt)
        except Exception as missed:
            # No turn of the CLI's to put it into after all: it is taken as the next, while
            # this turn is still in flight to take one.
            with self._lock:
                if self._flying:
                    self._steers.append(prompt)
                    return
            raise SessionError("the turn ended before it could be steered") from missed

    def interrupt(self) -> None:
        """Stops the turn in flight, if any, from any thread. Idempotent."""
        with self._lock:
            if not self._flying or self._interrupted:
                return
            self._interrupted = True
        self._bridge.abandon()
        self._asking.abandon()
        self._cut("interrupted")

    def _cutting(self) -> bool:
        """Whether the coganchor call now starting is to be cut off. Held with the lock."""
        return self._interrupted or self._over is not None or self._steer_cut

    def _cut_off(self) -> bool:
        """Whether the coganchor call that just ended was cut off by the driver."""
        with self._lock:
            return self._cutting()

    def _cut(self, why: str) -> None:
        """Cuts the coganchor call off, and again until it has ended, from a thread."""
        with self._lock:
            if not self._running:
                return
            returned = self._returned
        threading.Thread(target=self._cutter, args=(returned, why), daemon=True).start()

    def _cutter(self, returned: threading.Event, why: str) -> None:
        """Cuts one coganchor call off until it has ended, which one cut may not do.

        Held to the call rather than to the turn: a call a cancelled turn stopped waiting for
        is cut again for as long as it runs, the turn after it having started behind it.
        """
        while True:
            with contextlib.suppress(Exception):
                self._session.cut(why=why)
            if returned.wait(_RECUT):
                return

    # ----------------------------------------------------------------------- closing

    def _check_open(self) -> None:
        """Refuses a session that has been closed.

        Raises:
          SessionError: If it has.
        """
        if self._closed:
            raise SessionError("the session is closed")

    async def close(self) -> None:
        """Ends the session, interrupting a turn in flight. Idempotent."""
        if self._closed:
            return
        self._closed = True
        self._driver.forget(self)
        self.interrupt()
        if self._started:
            with contextlib.suppress(Exception):
                await self._fire(HookKind.SESSION_END)
        self._bridge.close()
        self._asking.close()
        await asyncio.to_thread(self._shut)

    def _shut(self) -> None:
        """Lets go of the conversation and of the CLI serving it, on a thread."""
        with contextlib.suppress(Exception):
            self._session.close()
        with contextlib.suppress(Exception):
            self._agent.stop()


def _default(kind: HookKind) -> HookResult:
    """What a moment comes to with no hook answering it."""
    from .spi import default_result

    return default_result(kind)


def _refuse_spent(limits: Limits) -> None:
    """Refuses a turn given nothing to spend.

    Raises:
      BudgetExceeded: The leaf for a limit already reached.
    """
    if limits.deadline is not None and limits.deadline <= time.monotonic():
        raise DurationExceeded("the turn's deadline has passed")
    if limits.cost is not None and limits.cost <= 0:
        raise CostExceeded("the turn has no money left to spend")
    if limits.output_tokens is not None and limits.output_tokens <= 0:
        raise OutputTokensExceeded("the turn has no output tokens left to write")


def _posted(
    loop: asyncio.AbstractEventLoop, what: Callable[..., None], *said: Any
) -> None:
    """Calls something on the loop from a thread, unless the loop has gone."""
    with contextlib.suppress(RuntimeError):
        loop.call_soon_threadsafe(what, *said)


def _landed[T](landed: asyncio.Future[T], answered: T) -> None:
    """Hands a thread's answer to whoever awaits it, unless nobody does any more."""
    if not landed.done():
        landed.set_result(answered)


def _failed(landed: asyncio.Future[Any], why: BaseException) -> None:
    """Raises a thread's failure where it is awaited, unless nobody awaits it any more."""
    if not landed.done():
        landed.set_exception(why)


def _retrieved(landed: asyncio.Future[Any]) -> None:
    """Takes a finished future's exception, so that one nobody awaited says nothing."""
    if not landed.cancelled():
        landed.exception()


# ----------------------------------------------------------------------------- outworlder


def open_outworlder(
    *,
    ask: Callable[[Question], str | None] | None = None,
    away: Callable[[], bool] | None = None,
) -> HumanOutworlder:
    """Makes the driver for whoever is outside the run.

    Args:
      ask: Asks the person one question and waits for the answer, on a thread of its own:
        the question's text, and the answers it offers where it offers any. Answers None when
        nobody answered -- they walked away, or the interface closed. A text turn is one
        question; a turn asked for a schema is one question per field, as
        :class:`hmz.coganchor.agents.HumanAgent` asks them. None for nobody at all, which is
        `hmz exec`.
      away: Whether nobody is there now -- `/afk` -- asked whenever it matters. None for
        away exactly when there is nobody to `ask`.

    Returns:
      The driver.
    """
    return HumanOutworlder(ask=ask, away=away)


class HumanOutworlder:
    """Whoever is outside the run, asked through the person-shaped agent coganchor has.

    Implements :class:`~hmz.runtime.flowing.spi.OutworlderDriver`.
    """

    __slots__ = ("_ask", "_away", "_person")

    def __init__(
        self,
        *,
        ask: Callable[[Question], str | None] | None,
        away: Callable[[], bool] | None,
    ) -> None:
        """Initializes the driver; see :func:`open_outworlder`."""
        from hmz.coganchor.agents import HumanAgent

        self._ask = ask
        self._away = away
        self._person = HumanAgent(name="outworlder")
        self._person.ask = ask

    @property
    def away(self) -> bool:
        """Whether nobody is there to answer. It may change at any time."""
        if self._ask is None:
            return True
        return self._away() if self._away is not None else False

    async def run(
        self, prompt: str, output_schema: type[pydantic.BaseModel] | None
    ) -> str | pydantic.BaseModel:
        """Asks, and waits for the answer.

        Returns:
          The answer. An away outworlder answers at once: "" for text, and the schema built
          with no arguments where every field has a default.

        Raises:
          OutworlderAway: If it is away and the schema cannot be answered by default, or went
            away -- answered nothing -- while this was waiting.
        """
        if self.away:
            return away_answer(output_schema)
        said = await _threaded(lambda: self._asked(prompt, output_schema))
        if said is None:
            raise OutworlderAway("nobody answered")
        return said

    def _asked(
        self, prompt: str, output_schema: type[pydantic.BaseModel] | None
    ) -> str | pydantic.BaseModel | None:
        """Puts the prompt to the person, on a thread of its own."""
        from hmz.coganchor.agents import Question

        if output_schema is None:
            return self._person.asked(Question(text=prompt))
        return self._person.new()(prompt, suppress=True, schema=output_schema)


def away_answer(
    output_schema: type[pydantic.BaseModel] | None,
) -> str | pydantic.BaseModel:
    """What an outworlder that is away answers.

    Args:
      output_schema: The model asked for, or None for text.

    Returns:
      "" for text, and the model built with no arguments where every field has a default.

    Raises:
      OutworlderAway: For a model some field of which has no default.
    """
    if output_schema is None:
        return ""
    if any(field.is_required() for field in output_schema.model_fields.values()):
        raise OutworlderAway(
            f"nobody is there to answer a {output_schema.__name__}, and it has no default"
        )
    return output_schema()


async def _threaded[T](work: Callable[[], T]) -> T:
    """Runs blocking work on a thread of its own, and answers with its result."""
    loop = asyncio.get_running_loop()
    landed: asyncio.Future[T] = loop.create_future()
    landed.add_done_callback(_retrieved)

    def carry() -> None:
        try:
            answered = work()
        except BaseException as why:  # noqa: BLE001 -- carried to the loop, not handled
            _posted(loop, _failed, landed, why)
        else:
            _posted(loop, _landed, landed, answered)

    threading.Thread(target=carry, name="outworlder", daemon=True).start()
    return await landed


if TYPE_CHECKING:
    from .spi import AgentDriver

    _: type[AgentDriver] = HarnessDriver
    __: type[SessionHandle] = HarnessSession
    ___: type[OutworlderDriver] = HumanOutworlder

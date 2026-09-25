"""The agents a flow drives, what a flow may ask of each, and what a turn may spend.

An agent is one coding agent CLI -- a harness, a model and an effort -- that a flow opens
sessions of and takes turns in. A flow declares the agents it needs as an
:class:`AgentCollection`, one role apiece, and says what it will do with each by the mixins
the role's type carries::

    class Worker(Agent, GoalCommandAgentMixin, SteeringAgentMixin):
        _permission = Permission(system=PermissionKind.NONE)

    class Agents(AgentCollection):
        worker: Worker
        human: Outworlder

The flow is then handed an agent that can do exactly that and nothing more: `steer` on an
agent declared without :class:`SteeringAgentMixin`, or a `/goal` prompt without
:class:`GoalCommandAgentMixin`, raises :class:`~hmz.flows.errors.CapabilityNotGranted`
whatever the harness underneath could do. A role typed as one harness's own protocol --
:class:`ClaudeCodeAgent` and the rest -- asks for that harness and everything it can do.

Everything here but the enums, :class:`Permission`, :class:`Budget` and :class:`Usage` is a
protocol for a type checker. What a flow is handed at run time is the runtime's own object,
shaped however is fastest, and answers to these structurally.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import StrEnum, auto
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Protocol, Self, cast, overload

import pydantic
from typing_extensions import ReadOnly, TypedDict

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .envs import Env
    from .hooks import (
        AskUserHookParams,
        AskUserHookResult,
        HookFn,
        NotificationHookParams,
        NotificationHookResult,
        OutworlderRunHookParams,
        OutworlderRunHookResult,
        PermissionRequestHookParams,
        PermissionRequestHookResult,
        PreToolUseHookParams,
        PreToolUseHookResult,
        SessionEndHookParams,
        SessionEndHookResult,
        SessionStartHookParams,
        SessionStartHookResult,
        StopHookParams,
        StopHookResult,
        SubagentStartHookParams,
        SubagentStartHookResult,
        SubagentStopHookParams,
        SubagentStopHookResult,
        UserPromptSubmitHookParams,
        UserPromptSubmitHookResult,
    )

__all__ = [
    "HARNESS_AGENTS",
    "Agent",
    "AgentCollection",
    "AntigravityAgent",
    "AskUserHookAgentMixin",
    "Budget",
    "ClaudeCodeAgent",
    "CodexAgent",
    "CursorAgent",
    "DeepSeekHarnessAgent",
    "GoalCommandAgentMixin",
    "GrokBuildAgent",
    "HarnessKind",
    "KimiCodeAgent",
    "LoopCommandAgentMixin",
    "MiMoCodeAgent",
    "OpenCodeAgent",
    "Outworlder",
    "Permission",
    "PermissionKind",
    "PermissionRequestHookAgentMixin",
    "PiAgent",
    "QwenCodeAgent",
    "Session",
    "SteeringAgentMixin",
    "SubagentStartHookAgentMixin",
    "SubagentStopHookAgentMixin",
    "Usage",
    "ZCodeAgent",
]


class HarnessKind(StrEnum):
    """Which coding agent CLI an agent is, by the name `-a` gives it."""

    CLAUDE = "claude"
    CODEX = "codex"
    CURSOR_AGENT = "cursor-agent"
    OPENCODE = "opencode"
    MIMO = "mimo"
    QWEN = "qwen"
    KIMI = "kimi"
    GROK = "grok"
    PI = "pi"
    ZCODE = "zcode"
    AGY = "agy"
    DSH = "dsh"
    #: A CLI somebody added by hand, driven over the Agent Client Protocol.
    ACP = "acp"


#: How far each kind reaches, so that the kinds order the way they widen.
_RANKS = {"none": 0, "read": 1, "all": 2}


def _rank(kind: object) -> int:
    """Where one kind stands among the three, for ordering them.

    Raises:
      TypeError: For anything that is not one of them.
    """
    rank = _RANKS.get(kind) if isinstance(kind, str) else None
    if rank is None:
        raise TypeError(f"{kind!r} is not a permission kind")
    return rank


class PermissionKind(StrEnum):
    """How much of one scope an agent may touch, ordered `NONE < READ < ALL`."""

    #: Nothing at all.
    NONE = auto()
    #: Read, and not write.
    READ = auto()
    #: Read and write.
    ALL = auto()

    def __lt__(self, other: str, /) -> bool:
        return _rank(self) < _rank(other)

    def __le__(self, other: str, /) -> bool:
        return _rank(self) <= _rank(other)

    def __gt__(self, other: str, /) -> bool:
        return _rank(self) > _rank(other)

    def __ge__(self, other: str, /) -> bool:
        return _rank(self) >= _rank(other)


@dataclass(frozen=True, slots=True)
class Permission:
    """What an agent may touch, scope by scope.

    Scopes nest, and a wider one may never be granted more than a narrower one inside it:
    `local >= user >= system`. `online` is all or nothing.

    Whatever is granted, an agent's actions are never put to anybody for approval: every
    harness runs with approvals bypassed, or where a managed policy refuses that, in the most
    permissive mode short of the model reviewing itself, with every request approved. What
    limits an agent is this, and whatever hooks the flow hangs on it.

    Attributes:
      local: The environment's workdir the session runs in.
      user: The rest of the home directory of the user the agent runs as.
      system: Everything else on the machine.
      online: The network: web search and fetching.

    Raises:
      ValueError: If a field is not a permission kind, the scopes do not nest, or `online`
        is `READ`.
    """

    local: PermissionKind = PermissionKind.ALL
    user: PermissionKind = PermissionKind.READ
    system: PermissionKind = PermissionKind.READ
    online: PermissionKind = PermissionKind.NONE

    def __post_init__(self) -> None:
        for scope in ("local", "user", "system", "online"):
            said: object = getattr(self, scope)
            if not isinstance(said, str) or said not in _RANKS:
                raise ValueError(f"{scope}={said!r} is not a permission kind")
            object.__setattr__(self, scope, PermissionKind(said))
        if not self.local >= self.user >= self.system:
            raise ValueError(
                "a wider scope may not be granted more than a narrower one: "
                f"local={self.local}, user={self.user}, system={self.system}"
            )
        if self.online == PermissionKind.READ:
            raise ValueError("online is all or nothing: NONE or ALL, not READ")

    def covers(self, other: Permission) -> bool:
        """Whether this grants at least what `other` does, in every scope.

        Args:
          other: The permission asked for.

        Returns:
          True if no scope of this is narrower than the same scope of `other`.
        """
        return (
            self.local >= other.local
            and self.user >= other.user
            and self.system >= other.system
            and self.online >= other.online
        )


class Budget(pydantic.BaseModel):
    """How much a run, a flow call or one turn may spend before it is stopped.

    At least one limit is set. A flow's effective budget is the tighter of its own and what
    remains of its caller's: `duration` is a deadline shared by everything under it, while
    cost and tokens spent anywhere under a flow count against every flow above it.

    `Budget(cost=math.inf)` is what "unlimited" is written as -- the `chat` flow runs under
    it -- and survives `model_dump_json` and `model_validate_json`, infinity being written as
    the string `"Infinity"`.

    Attributes:
      duration: How long it may take, counted from when it started.
      cost: How much it may spend, in USD.
      output_tokens: How many tokens its agents may write.
      graceful: Whether the turn under way when the budget is spent is let finish before the
        flow is stopped, or is interrupted at once.

    Raises:
      pydantic.ValidationError: If no limit is set, or one is negative.
    """

    model_config = pydantic.ConfigDict(
        frozen=True, extra="forbid", ser_json_inf_nan="strings"
    )

    duration: datetime.timedelta | None = pydantic.Field(
        default=None, ge=datetime.timedelta(0)
    )
    cost: float | None = pydantic.Field(default=None, ge=0)
    output_tokens: int | None = pydantic.Field(default=None, ge=0)
    graceful: bool = True

    @pydantic.model_validator(mode="after")
    def _limits_something(self) -> Self:
        if self.duration is None and self.cost is None and self.output_tokens is None:
            raise ValueError(
                "a budget sets at least one of duration, cost, output_tokens"
            )
        return self


class Usage(pydantic.BaseModel):
    """What has been spent so far.

    Attributes:
      duration: How long the agents spent taking turns.
      cost: What the turns cost, in USD.
      output_tokens: How many tokens the agents wrote.
    """

    model_config = pydantic.ConfigDict(
        frozen=True, extra="forbid", ser_json_inf_nan="strings"
    )

    duration: datetime.timedelta = datetime.timedelta(0)
    cost: float = 0.0
    output_tokens: int = 0


class Session(Protocol):
    """One conversation of one agent, held in one environment."""

    @property
    def agent(self) -> Agent:
        """The agent whose conversation this is."""
        ...

    @property
    def env(self) -> Env:
        """The environment it works in."""
        ...

    @property
    def usage(self) -> Usage:
        """What its turns have spent so far, up to date whenever it is read."""
        ...


class Agent(Protocol):
    """A coding agent, as a flow is handed one.

    `run` takes one turn in a session and answers with what the agent said, or, given an
    `output_schema`, with an instance of it::

        text = await agent.run("fix the build", session=session)
        verdict = await agent.run("review it", session=session, output_schema=Verdict)

    A `budget` there limits that one turn, on top of the flow's own. A prompt starting
    `/goal` or `/loop` hands the turn to the harness's own goal or loop command, which the
    role must be declared with :class:`GoalCommandAgentMixin` or
    :class:`LoopCommandAgentMixin` to use. It raises
    :class:`~hmz.flows.errors.CapabilityNotGranted` for either without its mixin,
    :class:`~hmz.flows.errors.BudgetExceeded` once a budget is spent,
    :class:`~hmz.flows.errors.SessionError` for a session of another agent or one that is
    over, and the :class:`~hmz.flows.errors.HarnessError` a failed turn came to.

    The `on_*` methods hang a hook on one moment of every session of this agent, replacing
    the one hung there before; `None` takes it down. The moments here are the ones every
    harness reaches; the mixins add the rest.

    Attributes:
      _permission: What the role may touch. An agent given for it must hold at least this,
        and the flow's sessions run under exactly this.
      _skills: The skills the role's sessions are given: a skill in the flow's own `skills/`
        by name, or one elsewhere as a git URL with `#<skill>`.
    """

    _permission: ClassVar[Permission] = Permission()
    _skills: ClassVar[tuple[str, ...]] = ()

    @property
    def effort(self) -> str:
        """How hard the model is asked to think, in the harness's own words."""
        ...

    @property
    def harness(self) -> HarnessKind:
        """Which CLI it is."""
        ...

    @property
    def model(self) -> str:
        """Which model it runs."""
        ...

    @property
    def role(self) -> str:
        """The role it fills in the flow's `AgentCollection`."""
        ...

    @property
    def provider(self) -> str:
        """The account its turns run as, or "" for whoever this machine's CLI is logged in as."""
        ...

    def derive(
        self,
        *,
        permission: Permission | None = None,
        skills: tuple[str, ...] | None = None,
    ) -> Self:
        """The same agent, narrowed.

        Args:
          permission: What the derived agent may touch, or None for this one's.
          skills: Which of this one's skills it is given, or None for all of them.

        Returns:
          An agent whose sessions run under the narrower grant. This one is unchanged.

        Raises:
          CapabilityNotGranted: If either would widen what this agent was granted.
        """
        ...

    async def fork(
        self,
        session: Session,
        *,
        env: Env,
    ) -> Session:
        """A new session that carries on from where one of this agent's sessions is.

        Args:
          session: The conversation to branch. It carries on unchanged.
          env: Where the new one works.

        Returns:
          The new session.

        Raises:
          UnsupportedOperation: If the harness cannot fork a session, or not into `env`.
          SessionError: If `session` is not one of this agent's, or is over.
        """
        ...

    def on_session_start(
        self, fn: HookFn[SessionStartHookParams, SessionStartHookResult] | None
    ) -> None:
        """Hangs a hook on a session's first turn being about to start."""
        ...

    def on_user_prompt_submit(
        self, fn: HookFn[UserPromptSubmitHookParams, UserPromptSubmitHookResult] | None
    ) -> None:
        """Hangs a hook on a prompt being about to go to the agent."""
        ...

    def on_pre_tool_use(
        self, fn: HookFn[PreToolUseHookParams, PreToolUseHookResult] | None
    ) -> None:
        """Hangs a hook on the agent having reached for a tool."""
        ...

    def on_notification(
        self, fn: HookFn[NotificationHookParams, NotificationHookResult] | None
    ) -> None:
        """Hangs a hook on the agent stopping to tell its user something."""
        ...

    def on_stop(self, fn: HookFn[StopHookParams, StopHookResult] | None) -> None:
        """Hangs a hook on a turn being about to end."""
        ...

    def on_session_end(
        self, fn: HookFn[SessionEndHookParams, SessionEndHookResult] | None
    ) -> None:
        """Hangs a hook on a session being closed."""
        ...

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

    async def spawn(
        self,
        *,
        env: Env,
    ) -> Session:
        """Opens a new session of this agent.

        Args:
          env: Where it works: commands run in its workdir, on its machine.

        Returns:
          The session, with no turns taken yet.

        Raises:
          HarnessError: If the harness cannot be started there.
        """
        ...


class Outworlder(Agent, Protocol):
    """Whoever is outside the run -- the person at the prompt, or whatever stands in for one.

    A role typed as this is filled by the runtime and never by `-a`: at the top of a run it
    is the person who started it, and a flow calling another passes its own, or one made
    with :meth:`new`, or leaves the role out and the callee gets the run's. This is not
    steering: steering puts words into an agent's turn, while an outworlder takes turns of
    its own, as an agent of the flow.

    While it is `away`, `run` answers at once: `""` for text, the schema's defaults where
    every field has one, and :class:`~hmz.flows.errors.OutworlderAway` otherwise.
    """

    @classmethod
    def new(cls) -> Self:
        """An outworlder the caller stands in for, through :meth:`on_outworlder_run`.

        What a flow passes a callee that asks for an outworlder when it means to answer for
        it. Until a hook is hung on it, it is away.

        Returns:
          The outworlder.
        """
        from hmz.runtime.flowing.engine import new_outworlder

        return cast("Self", new_outworlder())

    @property
    def away(self) -> bool:
        """Whether nobody is there to answer: `/afk` is on, or the run is `hmz exec`."""
        ...

    def on_outworlder_run(
        self, fn: HookFn[OutworlderRunHookParams, OutworlderRunHookResult] | None
    ) -> None:
        """Hangs a hook that answers every `run` of an outworlder made with :meth:`new`."""
        ...


class AgentCollection(TypedDict, extra_items=ReadOnly[Agent]):
    """The agents a flow declares, one key per role.

    Subclassed to declare roles, each typed as `Agent` or a subclass carrying mixins::

        class Agents(AgentCollection):
            coder: Coder
            reviewer: NotRequired[Agent]

    A `NotRequired` role may be left out by whoever runs the flow.
    """


# ------------------------------------------------------------------------------ the mixins


class GoalCommandAgentMixin(Protocol):
    """Lets `run` take `/goal <objective>`: the harness keeps going until it decides it is met."""


class LoopCommandAgentMixin(Protocol):
    """Lets `run` take `/loop <interval> <task>`, the harness's own recurring task."""


class SteeringAgentMixin(Protocol):
    """Lets a flow put words into a turn while it runs."""

    async def steer(
        self,
        prompt: str,
        *,
        session: Session,
        queued: bool = True,
    ) -> None:
        """Puts a prompt into the turn a session is taking, as typing at the agent would.

        Args:
          prompt: What to say.
          session: The session whose turn it is.
          queued: Whether the agent takes it when it next looks, carrying on; or whether the
            turn is interrupted and goes on from this prompt, as pressing Esc first would.

        Raises:
          SessionError: If `session` is not taking a turn.
        """
        ...


class PermissionRequestHookAgentMixin(Protocol):
    """Lets a flow answer the harness asking whether a tool may run."""

    def on_permission_request(
        self,
        fn: HookFn[PermissionRequestHookParams, PermissionRequestHookResult] | None,
    ) -> None:
        """Hangs a hook on a tool asking to run. Its answer overrides bypassed approvals."""
        ...


class SubagentStartHookAgentMixin(Protocol):
    """Lets a flow hear of the agent starting subagents of its own."""

    def on_subagent_start(
        self, fn: HookFn[SubagentStartHookParams, SubagentStartHookResult] | None
    ) -> None:
        """Hangs a hook on a subagent starting."""
        ...


class SubagentStopHookAgentMixin(Protocol):
    """Lets a flow hear of, and hold on, the agent's subagents finishing."""

    def on_subagent_stop(
        self, fn: HookFn[SubagentStopHookParams, SubagentStopHookResult] | None
    ) -> None:
        """Hangs a hook on a subagent being about to finish."""
        ...


class AskUserHookAgentMixin(Protocol):
    """Lets a flow answer the agent stopping mid-turn to ask its user a question."""

    def on_ask_user(
        self, fn: HookFn[AskUserHookParams, AskUserHookResult] | None
    ) -> None:
        """Hangs a hook on the agent asking a question."""
        ...


# ---------------------------------------------------------------------- the harnesses


class ClaudeCodeAgent(
    Agent,
    GoalCommandAgentMixin,
    LoopCommandAgentMixin,
    SteeringAgentMixin,
    PermissionRequestHookAgentMixin,
    SubagentStartHookAgentMixin,
    SubagentStopHookAgentMixin,
    AskUserHookAgentMixin,
    Protocol,
):
    """Claude Code, with everything it can do."""


class CodexAgent(
    Agent,
    GoalCommandAgentMixin,
    SteeringAgentMixin,
    PermissionRequestHookAgentMixin,
    SubagentStartHookAgentMixin,
    SubagentStopHookAgentMixin,
    AskUserHookAgentMixin,
    Protocol,
):
    """Codex, with everything it can do."""


class CursorAgent(
    Agent, SubagentStartHookAgentMixin, SubagentStopHookAgentMixin, Protocol
):
    """Cursor Agent, with everything it can do."""


class OpenCodeAgent(Agent, Protocol):
    """opencode, with everything it can do."""


class MiMoCodeAgent(Agent, Protocol):
    """MiMo Code, with everything it can do."""


class QwenCodeAgent(Agent, Protocol):
    """Qwen Code, with everything it can do."""


class KimiCodeAgent(
    Agent,
    GoalCommandAgentMixin,
    SteeringAgentMixin,
    PermissionRequestHookAgentMixin,
    AskUserHookAgentMixin,
    Protocol,
):
    """Kimi Code, with everything it can do."""


class GrokBuildAgent(Agent, Protocol):
    """Grok Build, with everything it can do."""


class PiAgent(Agent, SteeringAgentMixin, AskUserHookAgentMixin, Protocol):
    """pi, with everything it can do."""


class ZCodeAgent(
    Agent,
    GoalCommandAgentMixin,
    PermissionRequestHookAgentMixin,
    AskUserHookAgentMixin,
    Protocol,
):
    """ZCode, with everything it can do."""


class AntigravityAgent(Agent, Protocol):
    """Antigravity, with everything it can do."""


class DeepSeekHarnessAgent(Agent, GoalCommandAgentMixin, Protocol):
    """DeepSeek Harness, with everything it can do."""


#: Each harness's own protocol, which is what a role typed as it asks for: that harness, and
#: every mixin it serves. A CLI added by hand is known by the protocol it speaks and nothing
#: else, so it is a plain `Agent`.
HARNESS_AGENTS: Mapping[HarnessKind, type] = MappingProxyType(
    {
        HarnessKind.CLAUDE: ClaudeCodeAgent,
        HarnessKind.CODEX: CodexAgent,
        HarnessKind.CURSOR_AGENT: CursorAgent,
        HarnessKind.OPENCODE: OpenCodeAgent,
        HarnessKind.MIMO: MiMoCodeAgent,
        HarnessKind.QWEN: QwenCodeAgent,
        HarnessKind.KIMI: KimiCodeAgent,
        HarnessKind.GROK: GrokBuildAgent,
        HarnessKind.PI: PiAgent,
        HarnessKind.ZCODE: ZCodeAgent,
        HarnessKind.AGY: AntigravityAgent,
        HarnessKind.DSH: DeepSeekHarnessAgent,
        HarnessKind.ACP: Agent,
    }
)

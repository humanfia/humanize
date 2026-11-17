"""The agents a flow drives, what a flow may ask of each, and what a turn may spend.

An agent is one coding agent CLI -- a harness, a model and an effort -- that a flow opens
sessions of and takes turns in. A flow declares the agents it needs as an
:class:`AgentCollection`, one role apiece, and says what it will do with each by the mixins
the role's type carries::

    class Worker(Agent, GoalCommandAgentMixin, SteeringAgentMixin):
        _permission = Permission(granular=(deny("~/.ssh"),))

    class Agents(AgentCollection):
        worker: Worker
        human: Outworlder

The flow is then handed an agent that can do exactly that and nothing more: `steer` on an
agent declared without :class:`SteeringAgentMixin`, or a `/goal` prompt without
:class:`GoalCommandAgentMixin`, raises :class:`~hmz.flows.errors.CapabilityNotGranted`
whatever the harness underneath could do. A role typed as one harness's own protocol --
:class:`ClaudeCodeAgent` and the rest -- asks for that harness and everything it can do.

Everything here but the enums, :class:`Rule` and its three makers, :class:`Permission`,
:class:`Budget`, :class:`Graceful` and :class:`Usage` is a protocol for a type checker. What a
flow is handed at run time is the runtime's own object, shaped however is fastest, and answers
to these structurally.
"""

from __future__ import annotations

import datetime
import functools
import itertools
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Protocol, Self, cast, overload

import pydantic
from typing_extensions import ReadOnly, TypedDict

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.coganchor.faking import FakeCli, FakeTool

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
    "PRESETS",
    "Access",
    "Agent",
    "AgentCollection",
    "AntigravityAgent",
    "AskUserHookAgentMixin",
    "Budget",
    "ClaudeCodeAgent",
    "CodexAgent",
    "CursorAgent",
    "DeepSeekHarnessAgent",
    "FakeToolAgentMixin",
    "GoalCommandAgentMixin",
    "Graceful",
    "GrokBuildAgent",
    "HarnessKind",
    "KimiCodeAgent",
    "LiteLLMAgent",
    "LoopCommandAgentMixin",
    "MiMoCodeAgent",
    "MiniMaxCodeAgent",
    "OhMyPiAgent",
    "OpenCodeAgent",
    "Outworlder",
    "Permission",
    "PermissionRequestHookAgentMixin",
    "PiAgent",
    "QwenCodeAgent",
    "Rule",
    "Session",
    "SteeringAgentMixin",
    "SubagentStartHookAgentMixin",
    "SubagentStopHookAgentMixin",
    "Usage",
    "allow",
    "deny",
    "read_only",
]


class HarnessKind(StrEnum):
    """Which coding agent CLI an agent is -- or `litellm`, a model -- by the name `-a` gives it."""

    CLAUDE = "claude"
    CODEX = "codex"
    CURSOR_AGENT = "cursor-agent"
    OPENCODE = "opencode"
    MIMO = "mimo"
    MCODE = "mcode"
    QWEN = "qwen"
    KIMI = "kimi"
    GROK = "grok"
    PI = "pi"
    OMP = "omp"
    AGY = "agy"
    DSH = "dsh"
    #: A model called directly, one chat completion a turn over the session's history: no
    #: CLI, no tools, no filesystem, and so no environment -- `env` on its turns is None.
    LITELLM = "litellm"
    #: A CLI somebody added by hand, driven over the Agent Client Protocol.
    ACP = "acp"


#: How far each access reaches, so that the three order the way they widen.
_RANKS = {"none": 0, "read": 1, "write": 2}


def _rank(access: object) -> int:
    """Where one access stands among the three, for ordering them.

    Raises:
      TypeError: For anything that is not one of them.
    """
    rank = _RANKS.get(access) if isinstance(access, str) else None
    if rank is None:
        raise TypeError(f"{access!r} is not an access")
    return rank


class Access(StrEnum):
    """How much of a path an agent may touch, ordered `NONE < READ < WRITE`."""

    #: Nothing at all.
    NONE = "none"
    #: Read, and not write.
    READ = "read"
    #: Read and write.
    WRITE = "write"

    def __lt__(self, other: str, /) -> bool:
        return _rank(self) < _rank(other)

    def __le__(self, other: str, /) -> bool:
        return _rank(self) <= _rank(other)

    def __gt__(self, other: str, /) -> bool:
        return _rank(self) > _rank(other)

    def __ge__(self, other: str, /) -> bool:
        return _rank(self) >= _rank(other)


#: What a rule's path may not hold: a glob would name paths a rule cannot be held to one by
#: one, and a NUL no path at all.
_UNSAID = frozenset("*?[\0")


def _normal(path: object) -> str:
    """A rule's path, tidied: its anchor, then its components, none empty and none `.`.

    Raises:
      ValueError: If it is not anchored at `/`, `~` or `.`, climbs out with `..`, or holds a
        glob or a NUL.
    """
    said = path if isinstance(path, str) else ""
    head, _, rest = said.partition("/")
    parts = [part for part in rest.split("/") if part not in ("", ".")]
    if (
        not said
        or head not in ("", "~", ".")
        or ".." in parts
        or not _UNSAID.isdisjoint(said)
    ):
        raise ValueError(
            "a rule's path is /..., ~, ~/..., . or ./..., with no '..' and no glob; "
            f"not {path!r}"
        )
    return "/" + "/".join(parts) if not head else "/".join((head, *parts))


def _under(rule: str, path: str) -> bool:
    """Whether a rule at `rule` matches `path`, component by component, unresolved."""
    return rule in ("/", path) or path.startswith(rule + "/")


@dataclass(frozen=True, slots=True)
class Rule:
    """How much of one path, and everything beneath it, an agent may touch.

    The path is anchored, and is not resolved until a session opens: an absolute path is
    where it says, `~` the home directory of the user the harness runs as, and `.` the
    workdir the session works in. It is kept tidied -- `~/a//b/` is `~/a/b`, `./` is `.` --
    and names a path exactly: no glob, and no `..` climbing out of its anchor.

    Attributes:
      path: The path, `/abs`, `~` or `~/...`, `.` or `./...`.
      access: How much of it may be touched.

    Raises:
      ValueError: If `path` is anchored nowhere, climbs out of its anchor or holds a glob or
        a NUL, or `access` is not an :class:`Access`.
    """

    path: str
    access: Access

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _normal(self.path))
        object.__setattr__(self, "access", Access(self.access))


def allow(path: str) -> Rule:
    """A rule that lets `path` be read and written."""
    return Rule(path, Access.WRITE)


def read_only(path: str) -> Rule:
    """A rule that lets `path` be read, and not written."""
    return Rule(path, Access.READ)


def deny(path: str) -> Rule:
    """A rule that keeps `path` from being touched at all."""
    return Rule(path, Access.NONE)


#: Where a permission starts from: each comes to rules said ahead of its own.
PRESETS = ("read-only", "workspace-write", "danger-full-access")

_EXPANSIONS: Mapping[str, tuple[Rule, ...]] = MappingProxyType(
    {
        "read-only": (read_only("/"),),
        "workspace-write": (read_only("/"), allow(".")),
        "danger-full-access": (allow("/"),),
    }
)

#: The temporary directories a session that may write its workdir may write too, `$TMPDIR`
#: standing for wherever that is.
_TMPDIR = "$TMPDIR"
_TEMPORARY = ("/tmp", "/var/tmp", _TMPDIR)  # noqa: S108 -- named, not written to

#: What a fresh directory is named by where :meth:`Permission.covers` lays the anchors out:
#: a NUL, which no rule's path holds, so that it is beneath no rule but those above it.
_FRESH = "\0"

#: A path laid out, component by component from the root.
type _Laid = tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Permission:
    """What an agent may touch: a preset, the network, and rules over them path by path.

    The preset is where the rules start -- `read-only` reads the whole machine,
    `workspace-write` writes the workdir besides, `danger-full-access` writes everything --
    and `granular` follows it. Each rule matches its path and everything beneath it, and the
    last that matches a path decides it; a path no rule matches is not touched at all. A
    session that may write its workdir may write the temporary directories as well, and
    whatever the rules say, a harness keeps its own state, its sign-in and its temporary
    files. `network` is the network, the harness's own web search and fetching included, and
    is independent of the rules. Left alone, an agent may change its workdir, read the rest
    of the machine, and go online.

    Whatever is granted, an agent's actions are never put to anybody for approval: every
    harness runs with approvals bypassed, or where a managed policy refuses that, in the most
    permissive mode short of the model reviewing itself, with every request approved. What
    limits an agent is this, and whatever hooks the flow hangs on it.

    Attributes:
      preset: One of :data:`PRESETS`.
      network: Whether the agent may reach the network.
      granular: Rules over the preset's, in the order they are said.

    Raises:
      ValueError: If `preset` is not one of :data:`PRESETS`.
      TypeError: If `network` is not a bool or a rule is not a :class:`Rule`.
    """

    preset: str = "workspace-write"
    network: bool = True
    granular: tuple[Rule, ...] = ()

    def __post_init__(self) -> None:
        if self.preset not in PRESETS:
            raise ValueError(
                f"preset is one of {', '.join(PRESETS)}, not {self.preset!r}"
            )
        if not isinstance(self.network, bool):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(f"network is a bool, not {self.network!r}")
        granular = tuple(self.granular)
        for rule in granular:
            if not isinstance(rule, Rule):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise TypeError(f"{rule!r} is not a Rule")
        object.__setattr__(self, "granular", granular)

    @property
    def rules(self) -> tuple[Rule, ...]:
        """The preset's rules, then :attr:`granular`: the last that matches a path decides it."""
        return _EXPANSIONS[self.preset] + self.granular

    def access(self, path: str) -> Access:
        """How much of a path this lets an agent touch, read without resolving `~` or `.`.

        Args:
          path: A path as a rule's is said: `/abs`, `~` or `~/...`, `.` or `./...`.

        Returns:
          The access of the last rule that matches it -- `/` matching every path -- or NONE
          where none does.

        Raises:
          ValueError: If `path` is not one a rule could name.
        """
        said = _normal(path)
        found = Access.NONE
        for rule in self.rules:
            if _under(rule.path, said):
                found = rule.access
        return found

    def covers(self, other: Permission) -> bool:
        """Whether this grants at least what `other` does, at every path and on the network.

        Wherever the home directory, the workdir and `$TMPDIR` turn out to be: the two are
        compared at every path a rule of either names, at each temporary directory and at a
        fresh child of each, with each anchor laid out at a fresh directory beneath nothing,
        or beneath any one of those paths not anchored at itself -- every way the rules of
        either could fall one beneath another once resolved.

        Args:
          other: The permission asked for.

        Returns:
          True if no path, and not the network, is granted `other` more than this.
        """
        return other.network <= self.network and (
            self.rules == other.rules or _covers(self, other)
        )


@functools.lru_cache(maxsize=1024)
def _covers(wide: Permission, narrow: Permission) -> bool:
    """:meth:`Permission.covers` on the paths alone, kept: a flow asks it of every call."""
    paths = {rule.path for rule in (*wide.rules, *narrow.rules)}
    # Where no rule says `~`, where the home lies changes nothing; and beneath `/` is
    # beneath nothing.
    anchors = [".", _TMPDIR, *(["~"] if any(p[0] == "~" for p in paths) else [])]
    parents = sorted({*paths, *_TEMPORARY[:2]} - {"/"})
    for chosen in itertools.product(
        *([None, *(p for p in parents if p.partition("/")[0] != a)] for a in anchors)
    ):
        where = _placed(dict(zip(anchors, chosen, strict=True)))
        if where is None:
            continue
        ours, theirs = _resolved(wide, where), _resolved(narrow, where)
        for laid in {_at(path, where) for path in (*paths, *_TEMPORARY)}:
            for at in (laid, (*laid, _FRESH)):
                if _held(*ours, at) < _held(*theirs, at):
                    return False
    return True


def _at(path: str, where: Mapping[str, _Laid]) -> _Laid:
    """A rule's path, or `$TMPDIR`, laid out where its anchor was put."""
    head, _, rest = path.partition("/")
    return (where[head] if head else ()) + (tuple(rest.split("/")) if rest else ())


def _placed(chosen: Mapping[str, str | None]) -> dict[str, _Laid] | None:
    """Each anchor at a fresh directory beneath what was chosen for it; None for a cycle."""
    where: dict[str, _Laid] = {}
    for _ in chosen:
        for anchor, parent in chosen.items():
            head = parent.partition("/")[0] if parent else ""
            if anchor not in where and (not head or head in where):
                laid = _at(parent, where) if parent else ()
                where[anchor] = (*laid, _FRESH + anchor)
    return where if len(where) == len(chosen) else None


def _resolved(
    permission: Permission, where: Mapping[str, _Laid]
) -> tuple[list[tuple[_Laid, Access]], list[_Laid]]:
    """A permission's rules laid out, and the temporary directories it writes besides."""
    rules = [(_at(rule.path, where), rule.access) for rule in permission.rules]
    writes = _held(rules, [], where["."]) is Access.WRITE
    return rules, [_at(path, where) for path in _TEMPORARY] if writes else []


def _held(
    rules: list[tuple[_Laid, Access]], granted: list[_Laid], path: _Laid
) -> Access:
    """How much of a laid-out path the rules and the grants allow: the deeper decides.

    The last rule that matches decides among the rules; a grant as deep as it or deeper
    writes the path all the same, so that a rule takes a temporary directory's grant away
    only beneath it.
    """
    depth, found = -1, Access.NONE
    for laid, access in rules:
        if path[: len(laid)] == laid:
            depth, found = len(laid), access
    if any(path[: len(one)] == one and len(one) >= depth for one in granted):
        return Access.WRITE
    return found


class Graceful(pydantic.BaseModel):
    """Which of a budget's limits let the turn under way when it is reached finish.

    Each limit is graceful on its own: a limit that is graceful lets the turn under way finish
    when it is reached, and one that is not cuts the turn off at once, whatever the others do.

    Attributes:
      duration: Whether reaching the duration lets the turn finish.
      cost: Whether reaching the cost lets the turn finish.
      output_tokens: Whether reaching the output tokens lets the turn finish.
    """

    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")

    duration: bool = True
    cost: bool = True
    output_tokens: bool = True


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
      graceful: Whether the turn under way when a limit is reached is let finish before the
        flow is stopped, or is interrupted at once: one flag for every limit, or a
        :class:`Graceful` with one apiece -- which, its three flags agreeing, is read as the
        one flag they agree on.

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
    graceful: bool | Graceful = True

    @pydantic.field_validator("graceful")
    @classmethod
    def _agreeing(
        cls,
        graceful: bool | Graceful,  # noqa: FBT001 -- the field, as pydantic hands it on
    ) -> bool | Graceful:
        if not isinstance(graceful, Graceful):
            return graceful
        flags = {graceful.duration, graceful.cost, graceful.output_tokens}
        return flags.pop() if len(flags) == 1 else graceful

    @pydantic.model_validator(mode="after")
    def _limits_something(self) -> Self:
        if self.duration is None and self.cost is None and self.output_tokens is None:
            raise ValueError(
                "a budget sets at least one of duration, cost, output_tokens"
            )
        return self

    @property
    def graces(self) -> Graceful:
        """`graceful` with one flag apiece for each limit, whichever way it was given."""
        graceful = self.graceful
        if isinstance(graceful, Graceful):
            return graceful
        return _GRACEFUL if graceful else _HARD


#: What `Budget.graces` is for a budget whose one flag says it for every limit.
_GRACEFUL = Graceful()
_HARD = Graceful(duration=False, cost=False, output_tokens=False)


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
    """One conversation of one agent: its history, and nothing of where it works.

    Where a turn works is the turn's to say -- `env` on :meth:`Agent.run` -- so one session
    may take its turns in different environments. A flow does not close one: it is closed
    when the flow call that opened it ends, or as soon as nothing holds it any more,
    whichever comes first. Keep it in a variable for as long as there are turns to take in
    it, and let go of it when there are not.
    """

    @property
    def agent(self) -> Agent:
        """The agent whose conversation this is."""
        ...

    @property
    def usage(self) -> Usage:
        """What its turns have spent so far, up to date whenever it is read."""
        ...


class Agent(Protocol):
    """A coding agent, as a flow is handed one.

    `run` takes one turn in a session, in an environment, and answers with what the agent
    said, or, given an `output_schema`, with an instance of it::

        session = await agent.spawn()
        text = await agent.run("fix the build", session=session, env=repo)
        verdict = await agent.run("review it", session=session, output_schema=Verdict)

    `env` is where that one turn works -- commands run in its workdir, on its machine -- and
    None is the run's own workspace. A session's turns may each work somewhere else: the
    conversation goes with it, where its harness can carry it there, and
    :class:`~hmz.flows.errors.UnsupportedOperation` is raised where it cannot. A `budget`
    there limits that one turn, on top of the flow's own. A prompt starting
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
      _tools: The flow's own functions the role's sessions offer the agent as tools, each
        :class:`~hmz.flows.FakeTool` of a name of its own. Declaring any takes
        :class:`FakeToolAgentMixin`.
      _clis: The flow's own command lines the role's sessions put on the agent's PATH, each
        :class:`~hmz.flows.FakeCli` of a name of its own. Every harness with a shell runs
        them, so declaring any takes no mixin; a role declaring any is not litellm's.
    """

    _permission: ClassVar[Permission] = Permission()
    _skills: ClassVar[tuple[str, ...]] = ()
    _tools: ClassVar[tuple[FakeTool, ...]] = ()
    _clis: ClassVar[tuple[FakeCli, ...]] = ()

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

    async def fork(self, session: Session) -> Session:
        """A new session that carries on from where one of this agent's sessions is.

        The fork is cut as its first turn goes, in the environment that turn works in.

        Args:
          session: The conversation to branch. It carries on unchanged.

        Returns:
          The new session.

        Raises:
          SessionError: If `session` is not one of this agent's, is over, or has taken no
            turn to carry on from.
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
        env: Env | None = None,
        budget: Budget | None = None,
    ) -> str: ...

    @overload
    async def run[TOutput: pydantic.BaseModel](
        self,
        prompt: str,
        *,
        session: Session,
        env: Env | None = None,
        output_schema: type[TOutput],
        budget: Budget | None = None,
    ) -> TOutput: ...

    async def spawn(self) -> Session:
        """Opens a new session of this agent, which works wherever its turns are taken.

        Its CLI is started as its first turn goes, which is where a harness that cannot be
        started there raises :class:`~hmz.flows.errors.HarnessError`.

        Returns:
          The session, with no turns taken yet.
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


class FakeToolAgentMixin(Protocol):
    """Lets a role declare `_tools`, which its sessions offer the agent as tools of its own."""


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
    FakeToolAgentMixin,
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
    FakeToolAgentMixin,
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


class OpenCodeAgent(Agent, FakeToolAgentMixin, Protocol):
    """opencode, with everything it can do."""


class MiMoCodeAgent(Agent, FakeToolAgentMixin, Protocol):
    """MiMo Code, with everything it can do."""


class MiniMaxCodeAgent(
    Agent, SubagentStartHookAgentMixin, SubagentStopHookAgentMixin, Protocol
):
    """MiniMax Code, with everything it can do."""


class QwenCodeAgent(Agent, FakeToolAgentMixin, Protocol):
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


class GrokBuildAgent(Agent, FakeToolAgentMixin, Protocol):
    """Grok Build, with everything it can do.

    Its `_tools` reach it over ACP, the one way grok is given a tool of the flow's, and a turn
    that only `grok -p` can take is refused while any are offered: an `output_schema`, the
    first turn of a fork, web search off, and a permission whose fence writes nothing each
    raise :class:`~hmz.flows.errors.HarnessUnrecoverable` there.
    """


class PiAgent(
    Agent, FakeToolAgentMixin, SteeringAgentMixin, AskUserHookAgentMixin, Protocol
):
    """pi, with everything it can do."""


class OhMyPiAgent(
    Agent, FakeToolAgentMixin, SteeringAgentMixin, AskUserHookAgentMixin, Protocol
):
    """Oh My Pi, with everything it can do."""


class AntigravityAgent(Agent, FakeToolAgentMixin, Protocol):
    """Antigravity, with everything it can do."""


class DeepSeekHarnessAgent(Agent, FakeToolAgentMixin, GoalCommandAgentMixin, Protocol):
    """DeepSeek Harness, with everything it can do."""


class LiteLLMAgent(Agent, Protocol):
    """A model called through litellm, with everything it can do: its turns take no `env`."""


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
        HarnessKind.MCODE: MiniMaxCodeAgent,
        HarnessKind.QWEN: QwenCodeAgent,
        HarnessKind.KIMI: KimiCodeAgent,
        HarnessKind.GROK: GrokBuildAgent,
        HarnessKind.PI: PiAgent,
        HarnessKind.OMP: OhMyPiAgent,
        HarnessKind.AGY: AntigravityAgent,
        HarnessKind.DSH: DeepSeekHarnessAgent,
        HarnessKind.LITELLM: LiteLLMAgent,
        HarnessKind.ACP: Agent,
    }
)

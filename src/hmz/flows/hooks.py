"""The moments of a session a flow can hang a hook on, and what a hook is told and answers.

A hook is an async function from one moment's params to that moment's result, hung on an
agent with the `on_*` method for the moment::

    async def no_force_push(params: PreToolUseHookParams) -> PreToolUseHookResult:
        pushing = "push --force" in str(params.input.get("command", ""))
        return PreToolUseHookResult(block=pushing, reason="no force pushes")

    agents["coder"].on_pre_tool_use(no_force_push)

It is called for every session of that agent, with the flow's context and the session the
moment arrived in, and whatever it answers is acted on before the session goes on. A result
built with no arguments changes nothing, so a hook that only watches returns one.

The moments every harness reaches are hung on with methods of `Agent`; the rest only on an
agent whose role is declared with the mixin for them, and `on_outworlder_run` only on an
`Outworlder`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum, auto
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

    import pydantic

    from .agents import Session
    from .defining import FlowContext

__all__ = [
    "HOOK_TYPES",
    "AskUserHookParams",
    "AskUserHookResult",
    "HookFn",
    "HookKind",
    "HookParams",
    "HookResult",
    "NotificationHookParams",
    "NotificationHookResult",
    "OutworlderRunHookParams",
    "OutworlderRunHookResult",
    "PermissionRequestHookParams",
    "PermissionRequestHookResult",
    "PreToolUseHookParams",
    "PreToolUseHookResult",
    "SessionEndHookParams",
    "SessionEndHookResult",
    "SessionStartHookParams",
    "SessionStartHookResult",
    "StopHookParams",
    "StopHookResult",
    "SubagentStartHookParams",
    "SubagentStartHookResult",
    "SubagentStopHookParams",
    "SubagentStopHookResult",
    "UserPromptSubmitHookParams",
    "UserPromptSubmitHookResult",
]


class HookKind(StrEnum):
    """Every moment a hook can be hung on, across every harness."""

    #: A session is about to take its first turn.
    SESSION_START = auto()
    #: A prompt is about to go to the agent.
    USER_PROMPT_SUBMIT = auto()
    #: The agent has reached for a tool, which has not run yet.
    PRE_TOOL_USE = auto()
    #: The harness is asking whether a tool may run.
    PERMISSION_REQUEST = auto()
    #: The agent has stopped to tell its user something.
    NOTIFICATION = auto()
    #: A turn is about to end.
    STOP = auto()
    #: A session is being closed.
    SESSION_END = auto()
    #: The agent has started a subagent of its own.
    SUBAGENT_START = auto()
    #: One of those is about to finish.
    SUBAGENT_STOP = auto()
    #: The agent has stopped mid-turn to ask its user a question.
    ASK_USER = auto()
    #: An outworlder made with `Outworlder.new()` has been asked to take a turn.
    OUTWORLDER_RUN = auto()


@dataclass(frozen=True, slots=True, kw_only=True)
class HookParams:
    """What every hook is told.

    Attributes:
      ctx: The context of the flow the agent belongs to.
      session: The session the moment arrived in.
    """

    ctx: FlowContext
    session: Session


@dataclass(frozen=True, slots=True, kw_only=True)
class HookResult:
    """What every hook answers. Built with no arguments, a result changes nothing."""


class HookFn[TParams: HookParams, TResult](Protocol):
    """A hook: an async function from one moment's params to that moment's result.

    Whatever it raises fails the flow the agent belongs to, as an exception in the flow's
    own code would.
    """

    async def __call__(self, params: TParams, /) -> TResult: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionStartHookParams(HookParams):
    """Told when a session is about to take its first turn."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionStartHookResult(HookResult):
    """What to start the session with.

    Attributes:
      context: Text to put in front of the agent before its first prompt, or "" for none.
    """

    context: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class UserPromptSubmitHookParams(HookParams):
    """Told when a prompt is about to go to the agent.

    Attributes:
      prompt: The prompt.
    """

    prompt: str


@dataclass(frozen=True, slots=True, kw_only=True)
class UserPromptSubmitHookResult(HookResult):
    """Whether the prompt goes, and with what.

    Attributes:
      block: Whether to refuse it: the turn does not run, and `run` raises
        :class:`~hmz.flows.errors.SessionError` saying `reason`.
      reason: Why.
      context: Text to add to the prompt, or "" for none.
    """

    block: bool = False
    reason: str = ""
    context: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class PreToolUseHookParams(HookParams):
    """Told when the agent has reached for a tool that has not run yet.

    Attributes:
      tool: The tool, as the harness names it.
      input: What it was called with, where the harness says; empty where it does not.
    """

    tool: str
    input: Mapping[str, Any] = field(default_factory=dict[str, Any])


@dataclass(frozen=True, slots=True, kw_only=True)
class PreToolUseHookResult(HookResult):
    """Whether the tool runs.

    Attributes:
      block: Whether to refuse it: the tool does not run, and the agent is told `reason`.
      reason: What the agent is told of the refusal.
    """

    block: bool = False
    reason: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionRequestHookParams(HookParams):
    """Told when the harness asks whether a tool may run.

    Attributes:
      tool: The tool, as the harness names it.
      input: What it was called with, where the harness says; empty where it does not.
    """

    tool: str
    input: Mapping[str, Any] = field(default_factory=dict[str, Any])


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionRequestHookResult(HookResult):
    """The answer to the request, which overrides the bypassed approvals it runs under.

    Attributes:
      allow: Whether the tool may run.
      reason: What the agent is told of a refusal.
    """

    allow: bool = True
    reason: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class NotificationHookParams(HookParams):
    """Told when the agent stops to tell its user something.

    Attributes:
      message: What it said.
    """

    message: str


@dataclass(frozen=True, slots=True, kw_only=True)
class NotificationHookResult(HookResult):
    """Nothing: a notification is heard, not answered."""


@dataclass(frozen=True, slots=True, kw_only=True)
class StopHookParams(HookParams):
    """Told when a turn is about to end.

    Attributes:
      said: What the agent said last, which is the answer the turn would end on.
      again: How many times a hook has already kept this turn going, so that one which keeps
        doing it can decide to stop.
    """

    said: str
    again: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class StopHookResult(HookResult):
    """Whether the turn ends.

    Attributes:
      block: Whether to keep the agent going instead, with `reason` as its next prompt.
      reason: That prompt. Blocking with nothing to say is not blocking.
    """

    block: bool = False
    reason: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionEndHookParams(HookParams):
    """Told when a session is being closed."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionEndHookResult(HookResult):
    """Nothing: a session that is ending ends."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SubagentStartHookParams(HookParams):
    """Told when the agent starts a subagent of its own.

    Attributes:
      subagent: What the harness calls the subagent.
      task: What it was asked to do.
    """

    subagent: str
    task: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class SubagentStartHookResult(HookResult):
    """What to start the subagent with.

    Attributes:
      context: Text to put in front of the subagent, or "" for none.
    """

    context: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class SubagentStopHookParams(HookParams):
    """Told when one of the agent's subagents is about to finish.

    Attributes:
      subagent: What the harness calls the subagent.
      said: What it said last, which is the answer it would finish on.
    """

    subagent: str
    said: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class SubagentStopHookResult(HookResult):
    """Whether the subagent finishes.

    Attributes:
      block: Whether to keep it going instead, with `reason` as its next prompt.
      reason: That prompt.
    """

    block: bool = False
    reason: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class AskUserHookParams(HookParams):
    """Told when the agent stops mid-turn to ask its user a question.

    Attributes:
      question: What it asked.
      options: The answers it offered, if any. An answer need not be one of them.
    """

    question: str
    options: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class AskUserHookResult(HookResult):
    """The answer.

    Attributes:
      answer: What the agent is told, or None to leave the question unanswered and let the
        agent carry on without one.
    """

    answer: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class OutworlderRunHookParams(HookParams):
    """Told when an outworlder made with `Outworlder.new()` is asked to take a turn.

    Attributes:
      prompt: What it was asked.
      output_schema: The schema its answer must be an instance of, or None for text.
    """

    prompt: str
    output_schema: type[pydantic.BaseModel] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class OutworlderRunHookResult(HookResult):
    """The outworlder's answer, which is what its `run` returns.

    Attributes:
      output: Text, or an instance of the `output_schema` it was asked for.
    """

    output: str | pydantic.BaseModel


#: Each moment's params and result, which is what the runtime builds a hook's call from.
HOOK_TYPES: Mapping[HookKind, tuple[type[HookParams], type[HookResult]]] = (
    MappingProxyType(
        {
            HookKind.SESSION_START: (SessionStartHookParams, SessionStartHookResult),
            HookKind.USER_PROMPT_SUBMIT: (
                UserPromptSubmitHookParams,
                UserPromptSubmitHookResult,
            ),
            HookKind.PRE_TOOL_USE: (PreToolUseHookParams, PreToolUseHookResult),
            HookKind.PERMISSION_REQUEST: (
                PermissionRequestHookParams,
                PermissionRequestHookResult,
            ),
            HookKind.NOTIFICATION: (NotificationHookParams, NotificationHookResult),
            HookKind.STOP: (StopHookParams, StopHookResult),
            HookKind.SESSION_END: (SessionEndHookParams, SessionEndHookResult),
            HookKind.SUBAGENT_START: (SubagentStartHookParams, SubagentStartHookResult),
            HookKind.SUBAGENT_STOP: (SubagentStopHookParams, SubagentStopHookResult),
            HookKind.ASK_USER: (AskUserHookParams, AskUserHookResult),
            HookKind.OUTWORLDER_RUN: (OutworlderRunHookParams, OutworlderRunHookResult),
        }
    )
)

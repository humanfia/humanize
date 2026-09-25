"""How the agent drivers read the flow API into coganchor's words, and coganchor's back.

Everything here is a table or a pure function, so that what a harness driver decides can be
read -- and tested -- without starting a CLI: which rung of coganchor's ladder a
:class:`~hmz.flows.Permission` comes to, what a hook's result tells a turn, and which
:class:`~hmz.flows.errors.HarnessError` a failed turn is. The drivers themselves are
:mod:`hmz.runtime.flowing.harnesses`.

**Permission.** A :class:`~hmz.flows.Permission` is four scopes, and coganchor has one
ladder of rungs -- `read-only`, `workspace-write`, `auto`, `bypass` -- that each of its
drivers maps onto its CLI's own sandbox and approval settings. Approvals are never put to
anybody: every session runs at its CLI's nothing-asked mode, which is what the flow API
calls BYPASS -- `danger-full-access` and `never` on Codex, and on Claude Code, whose
`bypassPermissions` a managed policy may forbid, `manual` with humanize answering every
request yes. `auto` is Claude Code's and cursor-agent's model-reviewed modes and is never
used for them; the one place it is used is the last column below, on the two CLIs where it
means the CLI asks and humanize answers.

| `local`      | every harness but dsh and acp | dsh, acp |
|--------------|-------------------------------|----------|
| READ or NONE | `read-only`                   | `bypass` |
| ALL          | `bypass`                      | `bypass` |

- `local` ALL fences nothing else. `user` and `system` are not held to READ or NONE: a
  session that may write its workdir may write anywhere its user can. Two of these CLIs
  have a sandbox that could fence it -- Codex's `workspace-write` and cursor-agent's
  `--sandbox enabled` -- and neither is used, for two reasons. The flow API's own word for
  Codex's BYPASS is `danger-full-access` with `never`. And the sandbox is bubblewrap, which
  cannot start on a machine that gives it no user namespace -- the one this was written on
  answers every command of a sandboxed Codex turn with `bwrap: loopback: Failed
  RTM_NEWADDR: Operation not permitted` -- so a fence here would be a flow that loses its
  shell wherever it runs in a container. Which harnesses fence is :data:`FENCED`, empty.
- `local` READ is the CLI's own read-only rung: Claude Code's `plan`, Codex's read-only
  sandbox, a tool list with nothing that writes on the rest. It reads outside the workdir
  too, which is wider than a `user` or `system` of NONE. `local` NONE is the same rung,
  which reads the workdir.
- dsh and ACP CLIs can be held to nothing but `bypass`, which is wider than asked for any
  permission below ALL.

While a hook is hung on a moment only asking reaches, three CLIs are started so that they
ask, and humanize answers every request yes unless the hook says no -- never a model:

- Codex, a PERMISSION_REQUEST hook: the rung's sandbox, and approval policy `untrusted`, so
  every command but a known-safe read is asked about. An ASK_USER hook switches on Codex's
  `default_mode_request_user_input` feature instead, without which its agent cannot ask its
  user anything outside plan mode.
- Kimi Code and ZCode, either hook: coganchor's `auto` -- Kimi's `yolo`, ZCode's `build` --
  which asks about what the CLI deems risky, and on Kimi is the mode where the agent may
  ask its user at all.

`online` is the CLI's own web tools: on for ALL, off for NONE where the CLI can be told, and
left as the CLI has it where it cannot (cursor-agent, pi, agy, acp), which may be wider. A
shell command the agent runs reaches the network whatever this says.
"""

from __future__ import annotations

import json
import re
import subprocess
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

import pydantic

from hmz.flows import (
    AskUserHookResult,
    HarnessContended,
    HarnessDropped,
    HarnessError,
    HarnessKilled,
    HarnessKind,
    HarnessMissing,
    HarnessNotInstalled,
    HarnessRefused,
    HarnessSandboxed,
    HarnessThrottled,
    HarnessUnrecoverable,
    HookKind,
    ModelUnavailable,
    OutputSchemaError,
    PermissionKind,
    PermissionRequestHookResult,
    PreToolUseHookResult,
    SessionError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.coganchor.agents import Occasion, Verdict
    from hmz.flows import HookResult, Permission

__all__ = [
    "ASKING",
    "ASKING_FEATURE",
    "ASKS",
    "BYPASS",
    "FAULTS",
    "FENCED",
    "MOMENTS",
    "READ_ONLY",
    "UNTRUSTED",
    "WORKSPACE_WRITE",
    "answer",
    "approvals",
    "asking",
    "fields",
    "harness_error",
    "read_shape",
    "rung",
    "searching",
    "verdict",
]

READ_ONLY: Final = "read-only"
WORKSPACE_WRITE: Final = "workspace-write"
#: coganchor's `auto`: the CLI asks, and what it asks is granted. Used for exactly the
#: harnesses in :data:`ASKS`, and only while a hook is hung that the asking is for.
ASKING: Final = "auto"
BYPASS: Final = "bypass"

#: The harnesses whose `workspace-write` would be used to fence writes to the workdir, which
#: is none of them: see the module docstring. Adding a CLI here puts a session whose `local`
#: is ALL and whose `user` is READ or NONE in that CLI's `workspace-write` rung instead.
FENCED: frozenset[HarnessKind] = frozenset()

#: The harnesses run at coganchor's `auto` while a hook is hung on the moments that come from
#: the asking, each with the moments it is for.
ASKS: Mapping[HarnessKind, frozenset[HookKind]] = MappingProxyType(
    {
        HarnessKind.KIMI: frozenset({HookKind.PERMISSION_REQUEST, HookKind.ASK_USER}),
        HarnessKind.ZCODE: frozenset({HookKind.PERMISSION_REQUEST, HookKind.ASK_USER}),
    }
)

#: Codex's approval policy while a PERMISSION_REQUEST hook is hung: everything but a
#: known-safe read is asked about, over whatever sandbox the rung puts it in.
UNTRUSTED: Final = "untrusted"

#: The feature Codex's agent needs to ask its user anything outside plan mode.
ASKING_FEATURE: Final = "default_mode_request_user_input"


def rung(
    harness: HarnessKind,
    permission: Permission,
    *,
    rungs: tuple[str, ...],
    hung: frozenset[HookKind] = frozenset(),
) -> str:
    """The rung of coganchor's ladder a session is run at, as the table above says.

    Args:
      harness: The CLI.
      permission: What the session may touch.
      rungs: The rungs the CLI's coganchor driver takes.
      hung: The hooks hung on the agent now.

    Returns:
      One of `read-only`, `workspace-write`, `auto` and `bypass`, and never a rung outside
      `rungs`.
    """
    if permission.local <= PermissionKind.READ:
        said = READ_ONLY
    elif harness in FENCED and permission.user <= PermissionKind.READ:
        said = WORKSPACE_WRITE
    else:
        said = BYPASS
    if said != READ_ONLY and asking(harness, hung):
        said = ASKING
    return said if said in rungs else BYPASS


def approvals(harness: HarnessKind, hung: frozenset[HookKind]) -> str:
    """The approval policy a Codex session is started with over its rung's, or "".

    Args:
      harness: The CLI.
      hung: The hooks hung on the agent now.

    Returns:
      :data:`UNTRUSTED` for Codex while a PERMISSION_REQUEST hook is hung, and "" otherwise.
    """
    if harness is HarnessKind.CODEX and HookKind.PERMISSION_REQUEST in hung:
        return UNTRUSTED
    return ""


def asking(harness: HarnessKind, hung: frozenset[HookKind]) -> bool:
    """Whether a harness is to be run at its asking rung, given the hooks hung on it.

    Args:
      harness: The CLI.
      hung: The hooks hung on the agent now.

    Returns:
      True where a hook is hung on a moment only that rung reaches.
    """
    wanted = ASKS.get(harness)
    return wanted is not None and not wanted.isdisjoint(hung)


def searching(permission: Permission, *, tellable: bool) -> bool | None:
    """Whether a session may use its CLI's web tools.

    Args:
      permission: What the session may touch.
      tellable: Whether the CLI can be told at all.

    Returns:
      True or False where the CLI can be told, and None -- the CLI's own default -- where it
      cannot.
    """
    if not tellable:
        return None
    return permission.online == PermissionKind.ALL


# ---------------------------------------------------------------------------------- hooks

#: The moments of a turn that coganchor fires from a thread of the CLI's, each with the hook
#: kind it is. The rest -- SESSION_START, USER_PROMPT_SUBMIT, STOP, SESSION_END -- the drivers
#: fire themselves, on the engine's loop, around the turns they take.
MOMENTS: Mapping[str, HookKind] = MappingProxyType(
    {
        "PreToolUse": HookKind.PRE_TOOL_USE,
        "PermissionRequest": HookKind.PERMISSION_REQUEST,
        "Notification": HookKind.NOTIFICATION,
        "SubagentStart": HookKind.SUBAGENT_START,
        "SubagentStop": HookKind.SUBAGENT_STOP,
    }
)


def fields(kind: HookKind, occasion: Occasion) -> dict[str, Any]:
    """What a hook of one kind is told of a moment coganchor fired.

    Args:
      kind: The hook kind the moment is.
      occasion: The moment, as coganchor says it.

    Returns:
      The params of the kind's :data:`hmz.flows.HOOK_TYPES` entry, less `ctx` and `session`.
      A tool read off a CLI's stream rather than asked about carries only the line a
      transcript shows of it; that line is the tool's `input` then, under `about`.
    """
    match kind:
        case HookKind.PRE_TOOL_USE | HookKind.PERMISSION_REQUEST:
            given = dict(occasion.input) or (
                {"about": occasion.about} if occasion.about else {}
            )
            return {"tool": occasion.tool, "input": given}
        case HookKind.NOTIFICATION:
            return {"message": occasion.said}
        case HookKind.SUBAGENT_START:
            return {"subagent": occasion.tool, "task": occasion.about}
        case HookKind.SUBAGENT_STOP:
            return {"subagent": occasion.tool, "said": occasion.said}
        case _:
            return {}


def verdict(kind: HookKind, result: HookResult) -> Verdict | None:
    """What a hook's result tells coganchor to do about the moment it was hung on.

    Only a tool reached for and a tool asking to run can be refused; the other moments
    coganchor fires are told, and what their hooks answer changes nothing there.

    Args:
      kind: The moment.
      result: What the hook answered.

    Returns:
      The verdict, or None to let the moment go on as it would have.
    """
    from hmz.coganchor.agents import Verdict

    if kind is HookKind.PRE_TOOL_USE and isinstance(result, PreToolUseHookResult):
        if result.block:
            return Verdict(refused=True, because=result.reason or "refused by a hook")
        return None
    if (
        kind is HookKind.PERMISSION_REQUEST
        and isinstance(result, PermissionRequestHookResult)
        and not result.allow
    ):
        return Verdict(refused=True, because=result.reason or "refused by a hook")
    return None


def answer(result: HookResult) -> str | None:
    """What an ASK_USER hook's result answers the agent with, or None for no answer."""
    return result.answer if isinstance(result, AskUserHookResult) else None


# --------------------------------------------------------------------------------- errors

#: Which harness error each kind of failure coganchor names is.
FAULTS: Mapping[str, type[HarnessError]] = MappingProxyType(
    {
        "contended": HarnessContended,
        "throttled": HarnessThrottled,
        "refused": HarnessRefused,
        "unlisted": ModelUnavailable,
        "retired": ModelUnavailable,
        "missing": HarnessMissing,
        "sandboxed": HarnessSandboxed,
        "killed": HarnessKilled,
        "dropped": HarnessDropped,
    }
)

#: What a shell exits with for a command it could not find, which is a CLI not installed.
_NOTHING_TO_RUN = 127


def harness_error(error: BaseException, backend: str) -> HarnessError | None:
    """The harness error a turn that failed in coganchor comes to.

    Args:
      error: What the turn raised.
      backend: The CLI, as coganchor names it, for reading a failure it did not classify.

    Returns:
      The leaf for it, carrying the failure's own words, or None for an exception that is
      not a turn failing -- a bug, which stays the bug it was.
    """
    from hmz.coganchor.agents import Failed, Stopped, Unrecoverable
    from hmz.coganchor.anchor import NotInstalled

    said = str(error) or type(error).__name__
    if isinstance(error, NotInstalled):
        return HarnessNotInstalled(said)
    if isinstance(error, Stopped):
        return SessionError(said)
    if isinstance(error, subprocess.CalledProcessError):
        fault = (
            error.fault if isinstance(error, Failed) else _classified(error, backend)
        )
        if fault == "missing" and error.returncode == _NOTHING_TO_RUN:
            return HarnessNotInstalled(said)
        if isinstance(error, Unrecoverable) and not fault:
            return HarnessUnrecoverable(said)
        return FAULTS.get(fault, HarnessUnrecoverable)(said)
    if isinstance(error, OSError):
        return HarnessDropped(said)
    if isinstance(error, RuntimeError):
        return SessionError(said)
    if isinstance(error, ValueError):
        return HarnessUnrecoverable(said)
    return None


def _classified(error: subprocess.CalledProcessError, backend: str) -> str:
    """Which kind of failure coganchor reads a failed process it did not classify as."""
    from hmz.coganchor import backends

    return backends.trouble(
        backend,
        _text(error.stderr),
        _text(error.output),
        status=error.returncode,
    )


def _text(said: object) -> str:
    """A stream a failed process wrote, as text."""
    if isinstance(said, bytes):
        return said.decode("utf-8", "replace")
    return said if isinstance(said, str) else ""


# -------------------------------------------------------------------------------- answers

#: A block of an answer fenced as code, which is where a model that talked as well as
#: answered puts the object it was asked for.
_FENCED_JSON = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def read_shape[T: pydantic.BaseModel](said: str, schema: type[T]) -> T:
    """Reads an answer as the model it was asked for.

    Tried as the whole answer, then as each fenced block in it, then as the span from its
    first brace to its last -- a CLI held to a schema answers with the object alone, and one
    asked for it in the prompt may talk around it.

    Args:
      said: The answer.
      schema: The model.

    Returns:
      The answer, as that model.

    Raises:
      OutputSchemaError: If no part of it is one.
    """
    held = said.strip()
    readings = [held, *(str(one).strip() for one in _FENCED_JSON.findall(held))]
    first, last = held.find("{"), held.rfind("}")
    if 0 <= first < last:
        readings.append(held[first : last + 1])
    refused: pydantic.ValidationError | None = None
    for reading in readings:
        try:
            return schema.model_validate_json(reading)
        except pydantic.ValidationError as why:
            refused = refused or why
    raise OutputSchemaError(
        f"the answer is not a {schema.__name__}: {json.dumps(held[:200])}"
    ) from refused

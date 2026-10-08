"""How the agent drivers read the flow API into coganchor's words, and coganchor's back.

Everything here is a table or a pure function, so that what a harness driver decides can be
read -- and tested -- without starting a CLI: which rung of coganchor's ladder a
:class:`~hmz.flows.Permission` comes to, what a hook's result tells a turn, and which
:class:`~hmz.flows.errors.HarnessError` a failed turn is. The drivers themselves are
:mod:`hmz.runtime.flowing.harnesses`.

**Permission.** A :class:`~hmz.flows.Permission` is four scopes, and it reaches a CLI two
ways at once: as a *fence* its process tree cannot get past, and as a *rung* its own tools
are run at.

The fence is :func:`fenced`: coganchor's :class:`~hmz.coganchor.fence.Fence`, set on every
session's agent as `AgentConfig.fence`. `system` is `/`, `user` the home directory and
`local` the workdir; READ lets a scope be read, ALL written, NONE neither. Whatever the scopes
say, a CLI may read what any program needs to run -- the system's programs and libraries,
the few files under `/etc` a resolver and a TLS stack read, `/proc`, `/sys` -- and its own
programs and the Python running humanize, and write the devices, `/dev/shm`, `/proc`, its own
state and a scratch directory of its own that is its `TMPDIR`, with the caches a build writes
pointed into it wherever the home cannot be written. `online` NONE cuts the network to the
hosts the CLI's model and sign-in are at (:func:`hmz.coganchor.backends.reachable`, read
under the account the session runs as); ALL leaves it alone. The default -- local ALL, user
and system READ, online ALL -- is a real fence: the workdir and that minimum may be written,
and nothing else.

A CLI that can enforce part of the fence itself is told to by its driver
(:meth:`~hmz.coganchor.agents.AgentBase.natively`), and the rest is put around it from outside
by ``hmz internal fence``: Landlock for the paths and TCP, a seccomp filter for every other
kind of socket, and a proxy on loopback that is the one way out. Nothing is ever run wider
than the permission: a session whose fence neither its CLI nor this machine can hold -- no
Landlock, a kernel too old to cut the network, work that lands on another machine -- is
refused with :class:`~hmz.flows.errors.HarnessSandboxed` as it opens. Which CLI enforces what
natively is in `docs/reference/flows.md`.

The rung is coganchor's ladder -- `read-only`, `workspace-write`, `auto`, `bypass` -- which
each of its drivers maps onto its CLI's own approval settings, and which the fence makes no
longer the thing that keeps a session inside its scopes. Approvals are never put to anybody:
every session runs at its CLI's nothing-asked mode, which is what the flow API calls BYPASS --
`danger-full-access` and `never` on Codex, `bypassPermissions` on Claude Code. Where a managed
policy forbids that, the CLI runs at the most permissive mode left that no model reviews --
the `workspace-write` sandbox with approval `on-request` on Codex, `acceptEdits` on Claude
Code -- and humanize answers every request yes. `auto` is
Claude Code's and cursor-agent's model-reviewed modes and is never used for them; the one
place it is used is the last column below, on the two CLIs where it means the CLI asks and
humanize answers.

| `local`      | every harness but dsh, mcode and acp | dsh, mcode, acp |
|--------------|--------------------------------------|-----------------|
| READ or NONE | `read-only`                          | `bypass`        |
| ALL          | `bypass`                             | `bypass`        |

- `local` READ is the CLI's own read-only rung as well as a fence that lets nothing but the
  minimum be written: Claude Code's `plan`, Codex's read-only sandbox, a tool list with
  nothing that writes on the rest. `local` NONE is the same rung, and a fence that does not
  let the workdir be read either.
- dsh and ACP CLIs can be held to no rung but `bypass`, and MiniMax Code to none that changes
  nothing; the fence holds them to the scopes.

While a hook is hung on a moment only asking reaches, three CLIs are started so that they
ask, and humanize answers every request yes unless the hook says no -- never a model:

- Claude Code, a PERMISSION_REQUEST hook: `manual` in place of `bypassPermissions`, so every
  tool that would change something is asked about.
- Codex, a PERMISSION_REQUEST hook: the rung's sandbox, and approval policy `untrusted`, so
  every command but a known-safe read is asked about. An ASK_USER hook switches on Codex's
  `default_mode_request_user_input` feature instead, without which its agent cannot ask its
  user anything outside plan mode.
- Kimi Code, either hook: coganchor's `auto` -- Kimi's `yolo` -- which asks about what the
  CLI deems risky, and is the mode where the agent may ask its user at all.

`online` is also the CLI's own web tools: on for ALL, off for NONE where the CLI can be told,
and left as the CLI has it where it cannot (cursor-agent, mcode, pi, agy, acp) -- where the
fence's cut network is what stops them, a search reaching no host but the model's.
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
    from hmz.coganchor.backends import Profile
    from hmz.coganchor.fence import Fence
    from hmz.flows import HookResult, Permission

__all__ = [
    "ASKING",
    "ASKING_FEATURE",
    "ASKS",
    "BYPASS",
    "FAULTS",
    "MOMENTS",
    "READ_ONLY",
    "UNTRUSTED",
    "WORKSPACE_WRITE",
    "answer",
    "approvals",
    "asking",
    "fenced",
    "fields",
    "harness_error",
    "prompting",
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

#: The harnesses run at coganchor's `auto` while a hook is hung on the moments that come from
#: the asking, each with the moments it is for.
ASKS: Mapping[HarnessKind, frozenset[HookKind]] = MappingProxyType(
    {
        HarnessKind.KIMI: frozenset({HookKind.PERMISSION_REQUEST, HookKind.ASK_USER}),
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
    said = READ_ONLY if permission.local <= PermissionKind.READ else BYPASS
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


def prompting(harness: HarnessKind, hung: frozenset[HookKind]) -> bool:
    """Whether a Claude Code session is started so that its `bypass` asks, for the hooks hung.

    Claude's `bypassPermissions` asks nothing, so a PERMISSION_REQUEST hook would never be
    reached at it: while one is hung, `bypass` runs at `manual` instead, and humanize answers
    every request yes unless the hook says no.

    Args:
      harness: The CLI.
      hung: The hooks hung on the agent now.

    Returns:
      True for Claude Code while a PERMISSION_REQUEST hook is hung.
    """
    return harness is HarnessKind.CLAUDE and HookKind.PERMISSION_REQUEST in hung


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


def fenced(
    permission: Permission,
    *,
    workdir: str,
    home: str,
    profile: Profile | None,
    environ: Mapping[str, str],
) -> Fence:
    """The fence a session's agent is held to, as the module docstring says.

    Args:
      permission: What the session may touch.
      workdir: The workdir it works in, on this machine.
      home: The home directory of the user its CLI runs as.
      profile: What coganchor knows of the CLI, or None for one it knows nothing of -- which
        the fence then lets reach no host at all while `online` is NONE.
      environ: The environment its turns run under, the account's included, which says
        where the account points the CLI's model.

    Returns:
      The fence, with the minimum every program needs to run; what the agent itself needs
      besides -- its state, its account, its programs -- coganchor adds where it spawns it.
    """
    from hmz.coganchor import backends
    from hmz.coganchor.fence import Fence

    return Fence.of(
        local=permission.local,
        user=permission.user,
        system=permission.system,
        online=permission.online == PermissionKind.ALL,
        workdir=workdir,
        home=home,
        hosts=backends.reachable(profile, environ) if profile is not None else (),
    )


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
        "spent": HarnessThrottled,
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
    from hmz.coganchor.agents import Failed, Stopped, Unfenced, Unrecoverable
    from hmz.coganchor.anchor import NotInstalled

    said = str(error) or type(error).__name__
    if isinstance(error, NotInstalled):
        return HarnessNotInstalled(said)
    if isinstance(error, Unfenced):
        return HarnessSandboxed(said)
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

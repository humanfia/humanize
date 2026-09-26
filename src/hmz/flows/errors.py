"""Everything a flow can catch, as one tree under :class:`FlowException`.

Three branches, by whose fault it was: :class:`FlowRuntimeError` for what humanize refused or
ran out of while running flows, :class:`HarnessError` for a coding agent CLI that could not
take a turn, and :class:`EnvError` for an environment that could not do what it was asked.
A flow that wants to handle one thing catches the leaf; one that wants to handle everything
catches `FlowException`.

Where a Python builtin already names the kind of failure, the leaf is that builtin too:
`except TimeoutError` catches both a command that ran out of time and a budget whose
duration ran out, and `except FileNotFoundError` catches a file an environment does not have.

Every class here is raised with its message as its only argument, so each one pickles and
copies as itself and crosses a process boundary intact. A child flow's exception is never
wrapped: it reaches the caller with the class it was raised with.
"""

from __future__ import annotations

__all__ = [
    "BudgetExceeded",
    "CapabilityMissing",
    "CapabilityNotGranted",
    "CostExceeded",
    "DurationExceeded",
    "EnvCommandTimeout",
    "EnvConnectionError",
    "EnvError",
    "EnvFileNotFound",
    "EnvPermissionDenied",
    "EnvUnavailable",
    "FlowCancelled",
    "FlowDefinitionError",
    "FlowDepthExceeded",
    "FlowException",
    "FlowLoadConflict",
    "FlowNotFound",
    "FlowRefError",
    "FlowRuntimeError",
    "HarnessContended",
    "HarnessDropped",
    "HarnessError",
    "HarnessKilled",
    "HarnessMismatch",
    "HarnessMissing",
    "HarnessNotInstalled",
    "HarnessRefused",
    "HarnessSandboxed",
    "HarnessThrottled",
    "HarnessUnrecoverable",
    "MissingRole",
    "ModelUnavailable",
    "OutputSchemaError",
    "OutputTokensExceeded",
    "OutworlderAway",
    "ParamsError",
    "PermissionTooNarrow",
    "RequirementError",
    "ResourceUnmet",
    "ScratchError",
    "SessionError",
    "StateNotSerializable",
    "TempCloneBusy",
    "UnsupportedOperation",
    "WorktreeError",
]


class FlowException(Exception):
    """The root of every exception the flow API raises.

    Catching it catches everything a flow, its agents or its environments can fail with,
    and nothing else: a bug in the flow's own code is still the `KeyError` it was.
    """


# ----------------------------------------------------------------------------- the runtime


class FlowRuntimeError(FlowException):
    """Humanize refused something, or something it holds a run to ran out."""


class FlowNotFound(FlowRuntimeError):
    """Raised by `load` for a ref that names no flow.

    The flowverse, the flow directory or the subflow is not there, or a bare ref matched no
    flow and no single visible one.
    """


class FlowRefError(FlowRuntimeError, ValueError):
    """Raised by `load` for a ref that is not written as a ref.

    Also for `:<subflow>` and `<flow>:<subflow>` asked for outside a flow, where there is no
    flow or flowverse for them to be relative to.
    """


class FlowDefinitionError(FlowRuntimeError):
    """Raised for a flow that is written wrong.

    A decorated function that is not an async function taking `task`, `agents`, `envs`,
    `params` and `ctx`; collections that are not `AgentCollection`/`EnvCollection` subclasses
    or whose values are not agents and environments; params that are not a `FlowParams`
    subclass; two flows under one name in one module.
    """


class FlowLoadConflict(FlowRuntimeError):
    """Raised by `load` when a flow cannot be imported without replacing another.

    Two flows of one run whose modules would sit in `sys.modules` under the same package name,
    from different directories.
    """


class RequirementError(FlowRuntimeError):
    """Raised before a flow starts when what it was given does not meet what it declared.

    Nothing of the callee has run when this is raised, and nothing has been spent.
    """


class MissingRole(RequirementError):
    """A role the flow requires was not given, and is not one the runtime fills itself."""


class CapabilityMissing(RequirementError):
    """An agent or environment given for a role lacks a mixin the role declares."""


class PermissionTooNarrow(RequirementError):
    """An agent given for a role holds a narrower `Permission` than the role declares."""


class ResourceUnmet(RequirementError):
    """An environment given for a role has fewer CPUs, GPUs or less memory than declared."""


class HarnessMismatch(RequirementError):
    """A role typed as one harness, such as `ClaudeCodeAgent`, was given another."""


class CapabilityNotGranted(FlowRuntimeError):
    """A flow used something its declaration did not ask for.

    A `/goal` or `/loop` prompt without the mixin, a hook method, `steer` or a script `exec`
    the role was not declared with. The underlying harness or environment may well support
    it; the flow gets exactly what it declared.
    """


class ParamsError(FlowRuntimeError, ValueError):
    """The params given do not validate against the flow's `FlowParams` subclass."""


class FlowDepthExceeded(FlowRuntimeError, RecursionError):
    """Flows called flows deeper than the runtime allows, usually through runaway recursion."""


class BudgetExceeded(FlowRuntimeError):
    """A flow's budget, or the budget of a flow above it, is spent.

    Sticky: once a flow's budget is spent, every later turn of that flow and its children
    raises again rather than spending more.
    """


class DurationExceeded(BudgetExceeded, TimeoutError):
    """The budget's `duration` has elapsed."""


class CostExceeded(BudgetExceeded):
    """The budget's `cost` has been spent."""


class OutputTokensExceeded(BudgetExceeded):
    """The budget's `output_tokens` have been spent."""


class FlowCancelled(FlowRuntimeError):
    """The run was stopped from outside -- by whoever started it -- while this flow ran."""


class StateNotSerializable(FlowRuntimeError, TypeError):
    """A value written to a resumable flow's `FlowState` cannot be written down as JSON."""


class OutworlderAway(FlowRuntimeError):
    """The outworlder is away and a run of it needs an answer nothing can default.

    An away outworlder answers `""` for text and the schema's defaults for a schema whose
    every field has one; any other schema raises this.
    """


# ---------------------------------------------------------------------------- the harnesses


class HarnessError(FlowException):
    """A coding agent CLI could not take a turn, or could not do what it was asked."""


class HarnessNotInstalled(HarnessError):
    """The CLI, or the SDK it is driven through, is not installed where the agent runs."""


class HarnessContended(HarnessError):
    """Two turns reached one local store of the CLI at once, and this one lost."""


class HarnessThrottled(HarnessError):
    """The provider refused for too many requests, or a spent quota."""


class HarnessRefused(HarnessError):
    """The provider refused the credential: expired, revoked, or not logged in."""


class ModelUnavailable(HarnessError):
    """The model is not served to this account, has been retired, or never existed."""


class HarnessMissing(HarnessError):
    """The CLI would not start, so there was nothing to take the turn."""


class HarnessSandboxed(HarnessError):
    """The CLI could not set up the sandbox it confines its own tools with on this machine."""


class HarnessKilled(HarnessError):
    """The CLI died mid-turn -- a signal, an out-of-memory kill -- rather than answering."""


class HarnessDropped(HarnessError):
    """The connection to the CLI or its provider broke mid-turn."""


class HarnessUnrecoverable(HarnessError):
    """The turn failed in a way no retry could change, for a reason none of the others name."""


class OutputSchemaError(HarnessError, ValueError):
    """The agent's answer could not be read as the `output_schema` a run asked for."""


class SessionError(HarnessError):
    """A session could not take a turn, or was used in a way it cannot be.

    Closed or ended already, used by an agent that did not open it, steered with no turn in
    flight, interrupted mid-turn, or handed a prompt a hook blocked.
    """


class UnsupportedOperation(HarnessError):
    """The harness cannot do this at all -- fork a session across machines, for instance."""


# --------------------------------------------------------------------------- the environments


class EnvError(FlowException):
    """An environment could not do what it was asked."""


class EnvUnavailable(EnvError):
    """The environment cannot be used: its machine is gone or its workdir does not exist."""


class EnvConnectionError(EnvError, ConnectionError):
    """The connection to a remote environment could not be made, or broke."""


class EnvCommandTimeout(EnvError, TimeoutError):
    """A command ran past the `timeout` it was given, and was killed."""


class EnvFileNotFound(EnvError, FileNotFoundError):
    """A file read from an environment is not there."""


class EnvPermissionDenied(EnvError, PermissionError):
    """The environment refused a read, a write or a command for want of permission."""


class WorktreeError(EnvError):
    """`derive_worktree` failed: not a git repository, an unknown ref, or a taken directory."""


class TempCloneBusy(EnvError):
    """`derive_temp_clone` asked for an id another environment holds."""


class ScratchError(EnvError):
    """A scratch directory could not be made or removed."""

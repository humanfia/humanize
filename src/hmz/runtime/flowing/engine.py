"""The flow engine: what `flow`, `load` and `Outworlder.new` call, and what runs a flow.

Not written yet. The signatures here are the contract the rest of humanize is written
against -- :mod:`hmz.flows` calls the first three, and every way in calls :func:`run_flow` --
and each says what it must do; until then each raises `NotImplementedError`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from hmz.flows import (
        AgentCollection,
        Budget,
        EnvCollection,
        Flow,
        FlowFn,
        FlowParams,
        Outworlder,
    )

    from .spi import AgentDriver, EnvDriver, OutworlderDriver

__all__ = ["define_flow", "load_flow", "new_outworlder", "run_flow"]

_UNWRITTEN = "the flow engine is not written yet"


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
    first time the flow is called or inspected, against `caller_globals` and
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
      The flow, registered under `name` in its module for `load` to find.

    Raises:
      FlowDefinitionError: If `fn` is not an async function taking what a flow takes, or
        what it declares is not a flow's collections and params.
    """
    raise NotImplementedError(_UNWRITTEN)


def load_flow(ref: str, *, caller_globals: Mapping[str, Any]) -> Flow:
    """Loads the flow a ref names, which is what `hmz.flows.load` answers with.

    Args:
      ref: The ref, as `hmz.flows.load` documents it.
      caller_globals: The globals of the module `load` was called from, which is the flow a
        relative ref -- `:sub`, `flow:sub` -- is relative to.

    Returns:
      The flow.

    Raises:
      FlowRefError: If `ref` is not a ref, or is relative with nothing to be relative to.
      FlowNotFound: If it names no flow.
      FlowLoadConflict: If loading it would replace a module another flow of the run uses.
      FlowDefinitionError: If what it names is written wrong.
    """
    raise NotImplementedError(_UNWRITTEN)


def new_outworlder() -> Outworlder:
    """Makes an outworlder a flow answers for itself, which is what `Outworlder.new()` is.

    Returns:
      An outworlder that is away until a hook is hung on it with `on_outworlder_run`, and
      then answers every `run` with what the hook does.
    """
    raise NotImplementedError(_UNWRITTEN)


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
) -> Any:
    """Runs a flow at the top of a run, over drivers: what every way in calls.

    Checks everything before anything starts -- every required role filled, each driver
    meeting its role's declaration, the params valid -- then calls the flow with views of
    the drivers granted exactly what each role declared, under `budget`, and closes every
    session it opened and removes every temporary copy and scratch directory a
    non-resumable flow made before it returns or raises.

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

    Returns:
      What the flow returned.

    Raises:
      RequirementError: If the drivers do not meet the declaration. Nothing has run.
      ParamsError: If the params do not validate.
      FlowException: Whatever the flow raised, as it raised it.
    """
    raise NotImplementedError(_UNWRITTEN)

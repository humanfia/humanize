"""What a flow is, how one is written, and how one flow calls another.

A flow is an async function decorated with :func:`flow`, which says what it needs::

    class Params(FlowParams):
        rounds: int = 3

    @flow(agents=Agents, envs=Envs, params=Params, description="fix until green")
    async def fix(task, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext):
        ...

What the decorator answers is a :class:`Flow`, which is also what :func:`load` answers for
another flow by its ref -- and a flow is called the same way whichever of the two it came
from::

    review = load(":review")
    verdict = await review(task, agents={"reviewer": agents["coder"]}, envs=envs, params=...)

Nothing here runs a flow. :func:`flow`, :func:`load` and `Outworlder.new` hand what they
are given to :mod:`hmz.runtime.flowing` when they are called, which is the one thing this
package names outside itself and never at import.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Protocol

import pydantic

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from .agents import AgentCollection, Budget, Usage
    from .envs import EnvCollection

__all__ = [
    "Flow",
    "FlowContext",
    "FlowFn",
    "FlowParams",
    "FlowState",
    "flow",
    "load",
]


class FlowParams(pydantic.BaseModel):
    """What a flow can be configured with: subclassed, one field per param.

    `-p key=value` is validated into it, as is whatever mapping a calling flow passes. A key
    it does not declare is refused rather than ignored.
    """

    model_config = pydantic.ConfigDict(extra="forbid", ser_json_inf_nan="strings")


class FlowState(Protocol):
    """What a resumable flow keeps across runs: a mapping of JSON-serializable values.

    Every write is saved as it is made, so a run that is stopped or killed and then resumed
    finds what was there when it stopped.
    """

    def __getitem__(self, key: str) -> Any:
        """The value kept under `key`.

        Raises:
          KeyError: If nothing is.
        """
        ...

    def __setitem__(self, key: str, value: Any) -> None:
        """Keeps `value` under `key`, replacing what was there.

        Raises:
          StateNotSerializable: If `value` cannot be written down as JSON.
        """
        ...

    def __delitem__(self, key: str) -> None:
        """Forgets `key`.

        Raises:
          KeyError: If nothing is kept under it.
        """
        ...

    def __contains__(self, key: str) -> bool:
        """Whether anything is kept under `key`."""
        ...


class FlowContext(Protocol):
    """What a flow knows about its own call."""

    @property
    def budget(self) -> Budget:
        """The budget this call runs under: the tighter of its own and its caller's."""
        ...

    @property
    def flow(self) -> Flow:
        """The flow being called."""
        ...

    @property
    def resumed(self) -> bool:
        """Whether this call picks up one an earlier run of it left off."""
        ...

    @property
    def state(self) -> FlowState | None:
        """What the flow keeps across runs, or None for a flow that is not resumable."""
        ...

    @property
    def usage(self) -> Usage:
        """What this call, and every call under it, has spent so far."""
        ...


class Flow(Protocol):
    """A flow, ready to be called."""

    @property
    def description(self) -> str | None:
        """One line saying what it does, or None where it says nothing."""
        ...

    @property
    def expected_agents(self) -> type[AgentCollection]:
        """The agents it declares."""
        ...

    @property
    def expected_envs(self) -> type[EnvCollection]:
        """The environments it declares."""
        ...

    @property
    def expected_params(self) -> type[FlowParams]:
        """The params it declares."""
        ...

    @property
    def resumable(self) -> bool:
        """Whether a run of it can be picked up where it left off."""
        ...

    async def __call__(
        self,
        task: str,
        *,
        agents: AgentCollection,
        envs: EnvCollection,
        params: FlowParams,
        budget: Budget | None = None,
    ) -> Any:
        """Runs it, from inside another flow, and answers with what it returned.

        What is passed must be no narrower than what the flow declares: each agent and
        environment carries every mixin its role asks for, at least the role's permission
        and resources, and the role's harness where it names one. The flow is then handed
        exactly what it declared. A role the runtime fills -- an `Outworlder`, a `LocalEnv`
        -- may be left out, and is the caller's own.

        Args:
          task: What to do.
          agents: One agent per role.
          envs: One environment per role.
          params: Its params, as an instance of its own `FlowParams` subclass.
          budget: A budget of its own, which it runs under together with what remains of
            the caller's. None for the caller's alone.

        Returns:
          What the flow returned.

        Raises:
          RequirementError: If what was passed does not meet the declaration. Nothing has
            run.
          ParamsError: If `params` is not the flow's own params.
          FlowDepthExceeded: If flows are nested too deep.
          FlowException: Whatever the flow raised, as it raised it.
        """
        ...


class FlowFn[
    TAgentCollection: AgentCollection,
    TEnvCollection: EnvCollection,
    TFlowParams: FlowParams,
](Protocol):
    """The function :func:`flow` decorates: async, with `task` and four keyword arguments."""

    async def __call__(
        self,
        task: str,
        *,
        agents: TAgentCollection,
        envs: TEnvCollection,
        params: TFlowParams,
        ctx: FlowContext,
    ) -> Any: ...


def _caller(depth: int) -> tuple[dict[str, Any], Mapping[str, Any]]:
    """The global and local namespaces of a frame up the stack from the one asking.

    Args:
      depth: How far above the function that calls this: 1 for its caller.

    Returns:
      The two namespaces, or two empty ones where the interpreter keeps no frames.
    """
    frame = inspect.currentframe()
    try:
        for _ in range(depth + 1):
            if frame is None:
                return {}, {}
            frame = frame.f_back
        if frame is None:
            return {}, {}
        return frame.f_globals, frame.f_locals
    finally:
        del frame


def flow[
    TAgentCollection: AgentCollection,
    TEnvCollection: EnvCollection,
    TFlowParams: FlowParams,
](
    *,
    agents: type[TAgentCollection],
    envs: type[TEnvCollection],
    params: type[TFlowParams],
    name: str | None = None,
    description: str | None = None,
    hidden: bool = False,
    resumable: bool = False,
) -> Callable[[FlowFn[TAgentCollection, TEnvCollection, TFlowParams]], Flow]:
    """Makes an async function a flow, saying what it needs.

    Args:
      agents: The agents it needs, as an `AgentCollection` subclass.
      envs: The environments it needs, as an `EnvCollection` subclass.
      params: What it can be configured with, as a `FlowParams` subclass.
      name: What it is called in its module, which a ref names it by after the colon.
        None for the function's own name.
      description: One line saying what it does. None for the first line of the function's
        docstring, if it has one.
      hidden: Whether to leave it out of the lists a person picks a flow from. It can still
        be run and loaded by its ref.
      resumable: Whether a run of it can be picked up where it left off, which is what gives
        it a `FlowState`.

    Returns:
      The decorator, which answers with the flow.

    Raises:
      FlowDefinitionError: From the decorator, if the function or what it declares is not
        a flow.
    """
    caller_globals, caller_locals = _caller(1)

    def define(
        fn: FlowFn[TAgentCollection, TEnvCollection, TFlowParams],
    ) -> Flow:
        from hmz.runtime.flowing.engine import define_flow

        return define_flow(
            fn,
            agents=agents,
            envs=envs,
            params=params,
            name=name,
            description=description,
            hidden=hidden,
            resumable=resumable,
            caller_globals=caller_globals,
            caller_locals=caller_locals,
        )

    return define


def load(ref: str) -> Flow:
    """The flow a ref names, ready to be called.

    A ref is one of:

    - `:<subflow>`, a flow in the same module as the flow asking;
    - `<flow>` or `<flow>:<subflow>`, a flow in the same flowverse -- the bare form being
      the flow named after the directory, else the one visible flow it holds;
    - `<pip-style-vcs-url>#<flow>:<subflow>`, a flow in another flowverse, such as
      `git+https://github.com/humanfia/flowverse@main#humanize1:rlcr`.

    A resumed flow's subflows resume too, where they are called with the same task, agents,
    environments and params as before.

    Args:
      ref: The ref.

    Returns:
      The flow.

    Raises:
      FlowRefError: If `ref` is not a ref, or is relative with no flow to be relative to.
      FlowNotFound: If it names no flow.
      FlowLoadConflict: If loading it would replace a module another flow of the run uses.
      FlowDefinitionError: If what it names is written wrong.
    """
    from hmz.runtime.flowing.engine import load_flow

    caller_globals, _ = _caller(1)
    return load_flow(ref, caller_globals=caller_globals)

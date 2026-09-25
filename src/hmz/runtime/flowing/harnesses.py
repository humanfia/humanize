"""The agent drivers: one :class:`~hmz.runtime.flowing.spi.AgentDriver` per coding agent CLI.

Not written yet. :func:`open_agent` is the contract the ways in are written against, and
says what it must do; until then it raises `NotImplementedError`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .specs import AgentSpec
    from .spi import AgentDriver

__all__ = ["open_agent"]


def open_agent(spec: AgentSpec) -> AgentDriver:
    """Makes the driver for one `-a`.

    Starts nothing: the CLI is reached when the first session opens.

    Args:
      spec: The agent.

    Returns:
      A driver of `spec.harness` whose capabilities are exactly that harness's in
      :data:`~hmz.runtime.flowing.spi.HARNESS_CAPABILITIES`.

    Raises:
      HarnessNotInstalled: If the CLI is known not to be installed here.
    """
    raise NotImplementedError("the agent drivers are not written yet")

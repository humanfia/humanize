"""The environment drivers: one :class:`~hmz.runtime.flowing.spi.EnvDriver` per backend.

Not written yet. :func:`open_env` and :func:`local_env` are the contract the ways in are
written against, and say what they must do; until then they raise `NotImplementedError`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from .specs import EnvSpec
    from .spi import EnvDriver

__all__ = ["local_env", "open_env"]


def open_env(spec: EnvSpec) -> EnvDriver:
    """Makes the driver for one `-e`.

    Connects lazily: nothing here blocks on the network, and an unreachable machine is a
    driver whose `available` is False.

    Args:
      spec: The environment.

    Returns:
      A driver serving every environment capability its backend can.

    Raises:
      EnvUnavailable: If the workdir is known not to exist.
    """
    raise NotImplementedError("the environment drivers are not written yet")


def local_env(workdir: Path) -> EnvDriver:
    """Makes the driver for a directory on this machine: what fills a `LocalEnv` role.

    Args:
      workdir: The directory, which is the workspace a run was started in.

    Returns:
      A driver serving every environment capability.
    """
    raise NotImplementedError("the environment drivers are not written yet")

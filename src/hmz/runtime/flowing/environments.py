"""The environment drivers: one :class:`~hmz.runtime.flowing.spi.EnvDriver` per backend.

:func:`open_env` makes the driver for an `-e`, and :func:`local_env` the one for the workspace
a run was started in, which is what fills a `LocalEnv` role. Both are
:class:`~hmz.runtime.flowing.environing.MachineEnvDriver`, over this machine or over a host
reached with ssh, and both serve every environment capability. Neither touches the network:
an ssh host is reached the first time something is asked of it, and :func:`probe` is how to
ask before anything else -- which the ways in do for every environment a run is given, so
that `available` and the resources an ssh host has are known before a flow's requirements
are checked against them.

What a driver derives lives under `envs/` in humanize's home on its machine;
:mod:`hmz.runtime.flowing.environing` says how, and why there.
"""

from __future__ import annotations

import posixpath
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from hmz.flows import EnvBackendKind, EnvUnavailable

from .environing import MachineEnvDriver, tidy_workdir

if TYPE_CHECKING:
    from .specs import EnvSpec
    from .spi import EnvDriver

__all__ = ["MachineEnvDriver", "local_env", "open_env", "probe"]


def open_env(spec: EnvSpec) -> EnvDriver:
    """Makes the driver for one `-e`.

    Connects lazily: nothing here blocks on the network, and an unreachable machine is a
    driver whose `available` is False.

    Args:
      spec: The environment: `local@/abs/path` for a directory here, `ssh@host/abs/path` or
        `ssh@host/~/path` for one on a host `ssh` reaches -- `[user@]host[:port]` or an alias
        of the ssh config.

    Returns:
      A driver serving every environment capability.

    Raises:
      EnvUnavailable: If the workdir is known not to exist -- which for this machine is
        looked at now -- or the host is no ssh destination.
    """
    if spec.backend is EnvBackendKind.SSH:
        from .environing_ssh import SSHMachine

        # One place, one name: what is derived from it is found by that name again.
        return MachineEnvDriver(SSHMachine(spec.provider), tidy_workdir(spec.workdir))
    return local_env(Path(spec.workdir).expanduser())


def local_env(workdir: Path) -> EnvDriver:
    """Makes the driver for a directory on this machine: what fills a `LocalEnv` role.

    Args:
      workdir: The directory, which is the workspace a run was started in; a relative one
        is taken from where this process is.

    Returns:
      A driver serving every environment capability.

    Raises:
      EnvUnavailable: If there is no directory there.
    """
    from .environing_local import LocalMachine

    # Lexically, as `os.path.abspath` does: a workspace reached through a link keeps the
    # name it was given, and is one place however many `..` it was written with.
    at = PurePosixPath(posixpath.normpath(workdir.expanduser().absolute()))
    if not Path(at).is_dir():
        raise EnvUnavailable(f"there is no directory {at} on this machine")
    return MachineEnvDriver(LocalMachine(), at, seen=True)


async def probe(driver: EnvDriver) -> None:
    """Reaches an environment's machine, learns what it has, and checks its workdir is there.

    For this machine that is asking for its GPUs off the loop; for an ssh host it is
    connecting, which is otherwise done by the first thing asked of it. Cheap after the first
    time. A driver that is not one of these is left as it is.

    Args:
      driver: The environment.

    Raises:
      EnvUnavailable: If there is no such machine, or no such workdir on it.
      EnvConnectionError: If the machine could not be reached.
    """
    if isinstance(driver, MachineEnvDriver):
        await driver.probe()

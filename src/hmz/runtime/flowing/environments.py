"""The environment drivers: one :class:`~hmz.runtime.flowing.spi.EnvDriver` per backend.

:func:`open_env` makes the driver for an `-e`, and :func:`local_env` the one for the workspace
a run was started in, which is what fills a `LocalEnv` role. Both are
:class:`~hmz.runtime.flowing.environing.MachineEnvDriver`, over this machine, over a host
reached with ssh, or over a container of its own on a docker daemon, and all serve every
environment capability. None touches the network: an ssh host is reached, and a container
started, the first time something is asked of it, and :func:`probe` is how to ask before
anything else -- which the ways in do for every environment a run is given, so that
`available` and the resources a machine has are known, and a container has taken its share of
its provider, before a flow's requirements are checked against them.

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
    from .declaring import EnvRole
    from .specs import EnvSpec
    from .spi import EnvDriver

__all__ = ["MachineEnvDriver", "local_env", "open_env", "probe"]


def open_env(spec: EnvSpec, role: EnvRole | None = None) -> EnvDriver:
    """Makes the driver for one `-e`.

    Connects lazily: nothing here blocks on the network, and an unreachable machine is a
    driver whose `available` is False.

    Args:
      spec: The environment: `local@/abs/path` for a directory here, `ssh@host/abs/path` or
        `ssh@host/~/path` for one on a host `ssh` reaches -- a stored ssh provider by its
        name, and otherwise `[user@]host[:port]` or an alias of the ssh config -- or
        `docker@provider/abs/path` for a container of its own on the daemon a stored docker
        provider names, `docker@local/...` on docker's default here.
      role: What the environment is for, as its flow declares it: a container is started
        from its image and given its resources. None asks for nothing.

    Returns:
      A driver serving every environment capability.

    Raises:
      EnvUnavailable: If the workdir is known not to exist -- which for this machine is
        looked at now -- the host is no ssh destination, or no docker provider is written
        down under that name.
    """
    if spec.backend is EnvBackendKind.DOCKER:
        return _docker_env(spec, role)
    if spec.backend is EnvBackendKind.SSH:
        from hmz.coganchor.machines import store

        from .environing_ssh import SSHMachine

        # A provider written down under that name is reached as it says; any other name is
        # the destination `ssh` is handed as it is.
        stored = store.find(store.SSH, spec.provider)
        if stored is None and _unreadable(spec.provider):
            raise EnvUnavailable(
                f"the ssh provider {spec.provider!r} cannot be read; correct it or take "
                f"it away: {store.where(store.SSH, spec.provider)}"
            )
        target = stored.target() if isinstance(stored, store.SSHProvider) else ""
        # One place, one name: what is derived from it is found by that name again.
        return MachineEnvDriver(
            SSHMachine(spec.provider, target), tidy_workdir(spec.workdir)
        )
    return local_env(Path(spec.workdir).expanduser())


def _docker_env(spec: EnvSpec, role: EnvRole | None) -> EnvDriver:
    """The driver for a container of its own on a docker provider's daemon.

    Raises:
      EnvUnavailable: If no docker provider is written down under that name -- `local` being
        docker's default here where none is -- or the workdir is not a path of its host.
    """
    from hmz.coganchor.machines import store

    from .environing_docker import LOCAL, DockerMachine

    stored = store.find(store.DOCKER, spec.provider)
    if stored is not None and not isinstance(stored, store.DockerProvider):
        stored = None
    if stored is None and spec.provider != LOCAL:
        if _unreadable(spec.provider, store.DOCKER):
            raise EnvUnavailable(
                f"the docker provider {spec.provider!r} cannot be read; correct it or "
                f"take it away: {store.where(store.DOCKER, spec.provider)}"
            )
        raise EnvUnavailable(
            f"there is no docker provider called {spec.provider!r}: write one down, or "
            f"name docker's default here as docker@{LOCAL}"
        )
    workdir = tidy_workdir(spec.workdir)
    if not workdir.is_absolute():
        # Under the home of this machine's user, where the daemon's host is this machine;
        # anywhere else, nobody here knows whose home it would be.
        from hmz.coganchor.transport import Endpoint

        try:
            here = (stored.daemon() if stored is not None else Endpoint()).here
        except ValueError:
            here = False
        if not here:
            raise EnvUnavailable(
                f"{workdir} is a directory of the docker daemon's host, which is not this "
                "machine, so it is written as an absolute path there"
            )
        workdir = PurePosixPath(Path(str(workdir)).expanduser())
    machine = DockerMachine(
        spec.provider, workdir, stored=stored, role=role, named=spec.role
    )
    return MachineEnvDriver(machine, workdir)


def _unreadable(name: str, backend: str = "ssh") -> bool:
    """Whether something is written down as the provider of that name, and cannot be read.

    Which is not a name to hand `ssh` instead: whatever it would reach is not what was written
    down, and a run on it would be a run somewhere nobody meant.
    """
    from hmz.coganchor.machines import store

    try:
        return store.where(backend, name).exists()
    except ValueError:
        return False  # a name no provider may have, which is a host


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

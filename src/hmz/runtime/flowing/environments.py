"""The environment drivers: one :class:`~hmz.runtime.flowing.spi.EnvDriver` per backend.

:func:`open_env` makes the driver for an `-e`, and :func:`local_env` the one for the workspace
a run was started in, which is what fills a `LocalEnv` role. Both are
:class:`~hmz.runtime.flowing.environing.MachineEnvDriver`, over this machine, over a host
reached with ssh, over a container of its own on a docker daemon, over one a docker swarm
placed on whichever of its nodes had room, or over an Apple container of its own on this Mac,
and all serve every environment capability. None touches the network: an ssh host is reached,
and a container started or a swarm's service created, the first time something is asked of
it, and :func:`probe` is how to ask before anything else -- which the ways in do for every
environment a run is given, so that `available` and the resources a machine has are known,
and a container has taken its share of its runtime, before a flow's requirements are checked
against them. :func:`settle` is that probe for an environment an `-e` named, moving it down
the fallback list of the runtime it named where that runtime cannot hold it.

What a driver derives lives under `envs/` in humanize's home on its machine;
:mod:`hmz.runtime.flowing.environing` says how, and why there.
"""

from __future__ import annotations

import asyncio
import contextlib
import posixpath
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from hmz.flows import EnvBackendKind, EnvError, EnvUnavailable, ResourceUnmet

from .environing import MachineEnvDriver, tidy_workdir

if TYPE_CHECKING:
    from collections.abc import Callable

    from .declaring import EnvRole
    from .specs import EnvSpec
    from .spi import EnvDriver

__all__ = ["MachineEnvDriver", "local_env", "open_env", "probe", "settle"]


def open_env(
    spec: EnvSpec, role: EnvRole | None = None, *, traced: bool = False
) -> EnvDriver:
    """Makes the driver for one `-e`.

    Connects lazily: nothing here blocks on the network, and an unreachable machine is a
    driver whose `available` is False.

    Args:
      spec: The environment: `local@/abs/path` for a directory here, `ssh@host/abs/path` or
        `ssh@host/~/path` for one on a host `ssh` reaches -- a saved ssh runtime by its
        name, and otherwise `[user@]host[:port]` or an alias of the ssh config -- or
        `docker@name/abs/path` for a container of its own on the daemon a saved docker
        runtime names, `docker@local/...` on docker's default here -- or `swarm@name/abs/path`
        for a task of its own on the swarm a saved swarm runtime names, `swarm@local/...` on
        the swarm this machine manages -- or `apple-container@name/abs/path` for an Apple
        container of its own on this Mac, as a saved runtime of that backend shares it out,
        `apple-container@local/...` with nothing saved.
      role: What the environment is for, as its flow declares it: a container is started
        from its image and given its resources. None asks for nothing.
      traced: Whether a harness is to run there, supervising its agent: a container is
        started able to borrow the agent's descriptors.

    Returns:
      A driver serving every environment capability.

    Raises:
      EnvUnavailable: If the workdir is known not to exist -- which for this machine is
        looked at now -- the host is no ssh destination, or no docker or swarm runtime is
        written down under that name.
    """
    if spec.backend is EnvBackendKind.DOCKER:
        return _docker_env(spec, role, traced=traced)
    if spec.backend is EnvBackendKind.SWARM:
        return _swarm_env(spec, role, traced=traced)
    if spec.backend is EnvBackendKind.APPLE_CONTAINER:
        return _apple_container_env(spec, role, traced=traced)
    if spec.backend is EnvBackendKind.SSH:
        from hmz.coganchor.machines import store

        from .environing_ssh import SSHMachine

        # A runtime written down under that name is reached as it says; any other name is
        # the destination `ssh` is handed as it is.
        stored = store.find(store.SSH, spec.provider)
        if stored is None and _unreadable(spec.provider):
            raise EnvUnavailable(
                f"the ssh host {spec.provider!r} cannot be read; fix or remove "
                f"it: {store.where(store.SSH, spec.provider)}"
            )
        target = stored.target() if isinstance(stored, store.SSHRuntime) else ""
        # One place, one name: what is derived from it is found by that name again.
        return MachineEnvDriver(
            SSHMachine(spec.provider, target), tidy_workdir(spec.workdir)
        )
    return local_env(Path(spec.workdir).expanduser())


def _docker_env(
    spec: EnvSpec, role: EnvRole | None, *, traced: bool = False
) -> EnvDriver:
    """The driver for a container of its own on a docker runtime's daemon.

    Raises:
      EnvUnavailable: If no docker runtime is written down under that name -- `local` being
        docker's default here where none is -- or the workdir is not a path of its host.
    """
    from hmz.coganchor.machines import store

    from .environing_docker import LOCAL, DockerMachine

    stored = store.find(store.DOCKER, spec.provider)
    if stored is not None and not isinstance(stored, store.DockerRuntime):
        stored = None
    if stored is None and spec.provider != LOCAL:
        if _unreadable(spec.provider, store.DOCKER):
            raise EnvUnavailable(
                f"the docker host {spec.provider!r} cannot be read; fix or "
                f"remove it: {store.where(store.DOCKER, spec.provider)}"
            )
        raise EnvUnavailable(
            f"docker host {spec.provider!r} not found: add one, or use the "
            f"default docker@{LOCAL}"
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
                f"{workdir} is on a remote docker host, so it must be an absolute path"
            )
        workdir = PurePosixPath(Path(str(workdir)).expanduser())
    machine = DockerMachine(
        spec.provider,
        workdir,
        stored=stored,
        role=role,
        named=spec.role,
        traced=traced,
    )
    return MachineEnvDriver(machine, workdir)


def _swarm_env(
    spec: EnvSpec, role: EnvRole | None, *, traced: bool = False
) -> EnvDriver:
    """The driver for a task of its own on a swarm runtime's swarm.

    Raises:
      EnvUnavailable: If no swarm runtime is written down under that name -- `local` being
        the swarm this machine manages where none is -- or the workdir is not absolute, or
        under the home of this machine's user where the manager is this machine.
    """
    from hmz.coganchor.machines import store

    from .environing_swarm import LOCAL, SwarmMachine

    stored = store.find(store.SWARM, spec.provider)
    if stored is not None and not isinstance(stored, store.SwarmRuntime):
        stored = None
    if stored is None and spec.provider != LOCAL:
        if _unreadable(spec.provider, store.SWARM):
            raise EnvUnavailable(
                f"the docker swarm {spec.provider!r} cannot be read; fix or "
                f"remove it: {store.where(store.SWARM, spec.provider)}"
            )
        raise EnvUnavailable(
            f"docker swarm {spec.provider!r} not found: add one, or use the "
            f"swarm this machine manages, swarm@{LOCAL}"
        )
    workdir = tidy_workdir(spec.workdir)
    if not workdir.is_absolute():
        # Under the home of this machine's user, where the manager is this machine -- whose
        # nodes are then taken to share it; anywhere else, nobody here knows whose it is.
        from hmz.coganchor.transport import Endpoint

        try:
            here = (stored.daemon() if stored is not None else Endpoint()).here
        except ValueError:
            here = False
        if not here:
            raise EnvUnavailable(
                f"{workdir} is on a remote docker swarm, so it must be an absolute path"
            )
        workdir = PurePosixPath(Path(str(workdir)).expanduser())
    machine = SwarmMachine(
        spec.provider,
        workdir,
        stored=stored,
        role=role,
        named=spec.role,
        traced=traced,
    )
    return MachineEnvDriver(machine, workdir)


def _apple_container_env(
    spec: EnvSpec, role: EnvRole | None, *, traced: bool = False
) -> EnvDriver:
    """The driver for an Apple container of its own on this Mac.

    Raises:
      EnvUnavailable: If no runtime of that backend is written down under that name --
        `local` being this Mac's containers with nothing saved where none is.
    """
    from hmz.coganchor.machines import store

    from .environing_apple_container import LOCAL, AppleContainerMachine

    stored = store.find(store.APPLE_CONTAINER, spec.provider)
    if stored is not None and not isinstance(stored, store.AppleContainerRuntime):
        stored = None
    if stored is None and spec.provider != LOCAL:
        if _unreadable(spec.provider, store.APPLE_CONTAINER):
            raise EnvUnavailable(
                f"the {spec.backend} host {spec.provider!r} cannot be read; fix or "
                f"remove it: {store.where(store.APPLE_CONTAINER, spec.provider)}"
            )
        raise EnvUnavailable(
            f"{spec.backend} host {spec.provider!r} not found: add one, or use the "
            f"default {spec.backend}@{LOCAL}"
        )
    # Under the home of this machine's user, which is the one the containers run on.
    workdir = PurePosixPath(Path(str(tidy_workdir(spec.workdir))).expanduser())
    machine = AppleContainerMachine(
        spec.provider,
        workdir,
        stored=stored,
        role=role,
        named=spec.role,
        traced=traced,
    )
    return MachineEnvDriver(machine, workdir)


def _unreadable(name: str, backend: str = "ssh") -> bool:
    """Whether something is written down as the runtime of that name, and cannot be read.

    Which is not a name to hand `ssh` instead: whatever it would reach is not what was written
    down, and a run on it would be a run somewhere nobody meant.
    """
    from hmz.coganchor.machines import store

    try:
        return store.where(backend, name).exists()
    except ValueError:
        return False  # a name no runtime may have, which is a host


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


def _fits(_driver: EnvDriver) -> None:
    """Holds every environment: what :func:`settle` asks where nobody said otherwise."""


async def settle(
    spec: EnvSpec,
    driver: EnvDriver | EnvError,
    role: EnvRole | None = None,
    *,
    fits: Callable[[EnvDriver], None] = _fits,
    moved: Callable[[str], None] | None = None,
) -> tuple[EnvSpec, EnvDriver]:
    """Probes the environment an `-e` named, falling back where its runtime cannot hold it.

    A runtime cannot hold an environment it cannot be reached for, whose workdir it has not
    got, or that it has not got what the role asks left to hand out for -- its container
    limit among that -- and one `fits` refuses. Where the runtime the `-e` named has a
    fallback list, the environment is moved to each runtime of it in turn until one holds it,
    every driver refused on the way being closed; a runtime fallen back to is never walked on
    down its own list.

    Args:
      spec: The environment, as `-e` gave it.
      driver: The driver :func:`open_env` made for it, not yet probed -- or why it could not
        make one, which is that runtime's refusal.
      role: What the environment is for, which a driver made for a runtime fallen back to is
        made for as well.
      fits: What else is asked of a driver once it is probed: the role's declared resources,
        held against what its machine has, raising `ResourceUnmet` for one short of them.
      moved: What is told, in a line, that the environment was moved and why -- once it has
        been, and never where the runtime named held it.

    Returns:
      The spec of the runtime that holds it and its driver, probed: `spec` and `driver`
      themselves where nothing moved.

    Raises:
      EnvError: Why the runtime named could not hold it, where it has no fallback list; and
        where every runtime of its list could not either, of the kind the last refusal was,
        naming every runtime tried and why.
      ResourceUnmet: Likewise.
    """
    from .specs import fallbacks

    onward = fallbacks(spec)
    refused: list[str] = []
    last: EnvError | ResourceUnmet | None = None
    for at, said in enumerate((spec, *onward)):
        opened: EnvDriver | None = None
        try:
            opened = open_env(said, role) if at else _driven(driver)
            await probe(opened)
            fits(opened)
        except (EnvError, ResourceUnmet) as why:
            if not onward:
                raise
            refused.append(f"{_runtime(said)} cannot hold {spec.role!r}: {why}")
            last = why
            if opened is not None:
                with contextlib.suppress(Exception):
                    await opened.close()
            continue
        except BaseException:
            # Stopped, or refused for what is no runtime's fault, partway down the list: a
            # driver fallen back to is nobody else's to close, since nobody else has it.
            if at and opened is not None:
                with contextlib.suppress(Exception):
                    await asyncio.shield(opened.close())
            raise
        if refused and moved is not None:
            moved(f"{'; '.join(refused)}; using {_runtime(said)}")
        return said, opened
    if last is None:  # pragma: no cover -- the loop tries `spec` at the least
        raise AssertionError(spec)
    raise type(last)("; ".join(refused)) from last


def _driven(driver: EnvDriver | EnvError) -> EnvDriver:
    """The driver an `-e` was opened as, or the refusal opening it was, raised."""
    if isinstance(driver, EnvError):
        raise driver
    return driver


def _runtime(spec: EnvSpec) -> str:
    """The runtime an environment is put on, as a fallback list names one."""
    return f"{spec.backend}:{spec.provider}"

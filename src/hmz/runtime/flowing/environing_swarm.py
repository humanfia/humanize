"""A task of its own on a docker swarm, as an environment driver does its work in it.

One service of one task per environment a run is given, created on the swarm a swarm runtime
names -- `local` being the swarm this machine manages where no runtime is written down under
that name -- from the image the role declares, else the runtime's, else :data:`IMAGE`. The
swarm's scheduler puts it on whichever node has room for the CPUs, memory and GPUs the role
declares, which it reserves and is limited to; the workdir is the path it has on that node.

Once it is running it is a container like any other, and reached the way
:mod:`.environing_docker` reaches one: coganchor's serving half put in it and started with
`docker exec` -- against the daemon of the node it landed on, which is the manager's own where
it landed on the manager, and the node's over ssh where it did not. Everything downstream of
that, the mirror an agent works in, the native harness, the files, is the container's and
cannot tell.

What the runtime may hand out -- how many tasks, how many CPUs and bytes all told -- is shared
between every run on this machine by a lock on the runtime, as a docker runtime's is, and read
off the labels of the services it already runs. Whether a node has room is the scheduler's to
say: a task it leaves pending for want of one is given up on, its service removed, and the run
told what the scheduler said. A run that died without taking its services down leaves them
labelled with its host and pid, and the next run on that runtime removes any whose process is
gone.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import math
import os
import secrets
import shutil
import socket
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hmz.flows import (
    EnvBackendKind,
    EnvConnectionError,
    EnvError,
    EnvUnavailable,
    ResourceUnmet,
)

from .environing import Resources
from .environing_docker import (
    HOST,
    IMAGE,
    PID,
    PROVIDER,
    ROLE,
    _by,  # pyright: ignore[reportPrivateUsage]
    _bytes,  # pyright: ignore[reportPrivateUsage]
    _held,  # pyright: ignore[reportPrivateUsage]
    _info,  # pyright: ignore[reportPrivateUsage]
    _mirrors,  # pyright: ignore[reportPrivateUsage]
    _stale,  # pyright: ignore[reportPrivateUsage]
)
from .environing_ssh import SSHMachine
from .spi import Placement

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import PurePosixPath

    from hmz.coganchor.machines import Allocation, Swarm
    from hmz.coganchor.machines.store import SwarmRuntime
    from hmz.coganchor.transport import Endpoint

    from .declaring import EnvRole

__all__ = ["LOCAL", "Share", "SwarmMachine", "shared"]

#: The runtime the swarm this machine manages is named by, where none is written down under it.
LOCAL = "local"

#: How long a manager is given to answer each question asked of it while its runtime is held.
_ASKING = 60.0


@dataclass(frozen=True, slots=True)
class Share:
    """What one task reserves of its node, which is what it may take of it.

    Attributes:
      cpus: CPUs, or None for none reserved and no limit.
      memory: Bytes of memory, likewise.
      gpus: GPUs: how many of the runtime's generic resource it reserves.
    """

    cpus: float | None
    memory: int | None
    gpus: int


def shared(
    stored: SwarmRuntime | None,
    asked: tuple[int, int, int],
    held: Sequence[Allocation],
    *,
    where: str,
    role: str,
) -> Share:
    """What a task for a role reserves out of what is left of a runtime, or why not.

    What is left of the runtime, and not of its nodes: whether a node has room is the
    scheduler's to say once the service is created.

    Args:
      stored: The runtime, or None for the swarm this machine manages, which may hand out
        whatever its nodes have room for.
      asked: What the role asks: CPUs, bytes of memory, GPUs.
      held: What each of the runtime's running services already holds.
      where: The runtime, as a message names it: `swarm@<name>`.
      role: The role, as a message names it.

    Raises:
      ResourceUnmet: Naming everything that is short, and who holds it.
    """
    cpus, memory, gpus = asked
    short: list[str] = []
    if stored is not None and stored.max_tasks and len(held) >= stored.max_tasks:
        short.append(
            f"{where} runs {len(held)} of the {stored.max_tasks} tasks it may"
            + _by(held, lambda _: "one")
        )
    if stored is not None and stored.cpus:
        holding = [one for one in held if one.cpus]
        free = stored.cpus - sum(one.cpus or 0 for one in holding)
        if cpus > free + 1e-9:
            short.append(
                f"{where} has {max(free, 0):g} of {stored.cpus:g} CPUs free, and "
                f"{role!r} asks for {cpus}"
                + _by(holding, lambda one: f"{one.cpus:g} CPUs")
            )
    if stored is not None and stored.memory:
        holding = [one for one in held if one.memory]
        left = stored.memory - sum(one.memory or 0 for one in holding)
        if memory > left:
            short.append(
                f"{where} has {_bytes(max(left, 0))} of {_bytes(stored.memory)} of "
                f"memory free, and {role!r} asks for {_bytes(memory)}"
                + _by(holding, lambda one: _bytes(one.memory or 0))
            )
    if gpus and (stored is None or not stored.gpu_resource):
        short.append(
            f"{where} hands out no GPUs, and {role!r} asks for {gpus}: say which generic "
            "resource its nodes advertise them as in the runtime's gpu_resource"
        )
    if short:
        raise ResourceUnmet("; ".join(short))
    return Share(float(cpus) if cpus else None, memory or None, gpus)


class SwarmMachine(SSHMachine):
    """A task of its own on a swarm, created the first time something is asked of it.

    Reached as a container of one daemon is, over coganchor's serving half with `docker exec`
    for the road there, once it is known which node's daemon that is: this adds creating the
    service first, what it reserved, where an agent working in it is put, and removing it.
    """

    backend = EnvBackendKind.SWARM

    over = "docker exec"

    def __init__(
        self,
        provider: str,
        workdir: PurePosixPath,
        *,
        stored: SwarmRuntime | None = None,
        role: EnvRole | None = None,
        named: str = "",
        traced: bool = False,
    ) -> None:
        """Initializes a machine whose service has not been created.

        Args:
          provider: The swarm runtime's name, or :data:`LOCAL` for the swarm this machine
            manages.
          workdir: The directory the task holds, absolute, as each node names it.
          stored: The runtime as it is written down, or None for the swarm here.
          role: What the task is for, whose image and resources it is created with; None
            asks for nothing.
          named: The role's name, where there is no role to read it off.
          traced: Whether a harness runs in it, which creates it with `CAP_SYS_PTRACE`.

        Raises:
          EnvUnavailable: If the runtime's manager cannot be reached as it is written.
        """
        from hmz.coganchor.transport import Endpoint, Target

        try:
            endpoint = stored.daemon() if stored is not None else Endpoint()
        except ValueError as error:
            raise EnvUnavailable(f"swarm@{provider}: {error}") from error
        role_name = role.name if role is not None else named
        name = "-".join(
            one
            for one in ("humanize", provider, role_name, secrets.token_hex(4))
            if one
        )
        # Where the task is, which is not known until it has landed: until then, the name
        # of its service on its manager, which is what tells it from every other.
        super().__init__(
            provider, Target.parse(f"docker://{name}@{endpoint}").describe()
        )
        self.identity = f"swarm:{name}@{endpoint}"
        self.endpoint = endpoint
        self.name = name
        self.workdir = workdir
        self.stored = stored
        self.role = role_name
        self.asked = (
            (role.cpu_count, role.memory, role.gpu_count)
            if role is not None
            else (0, 0, 0)
        )
        image = (role.image if role is not None else "") or (
            stored.image if stored is not None else ""
        )
        self.image = image or IMAGE
        self.traced = traced
        self._swarm: Swarm | None = None
        self._share: Share | None = None
        self._starting: asyncio.Future[tuple[Swarm, Share]] | None = None
        self._mirrors = _mirrors(name)

    # --- bringing it up

    def _brought_up(self) -> tuple[Swarm, Share]:
        """Works out its share and creates it, holding the runtime while it does.

        Raises:
          ResourceUnmet: If the runtime has not got what the role asks left, or no node of
            the swarm took the task.
          EnvUnavailable: If the manager manages no swarm, or the task could not run there.
          EnvConnectionError: If the manager, or the node the task landed on, cannot be asked.
        """
        from hmz.coganchor.machines import SwarmConfig, store
        from hmz.coganchor.machines.swarm import Unplaced, services, swarm_of

        where = f"swarm@{self.provider}"
        endpoint = self.endpoint
        stored = self.stored
        with _held(self.provider, store.SWARM):
            try:
                swarm_of(_info(endpoint, where), where)
            except OSError as error:
                raise EnvUnavailable(str(error)) from error
            try:
                held = services(
                    str(endpoint), {PROVIDER: self.provider}, seconds=_ASKING
                )
            except OSError as error:
                raise EnvConnectionError(
                    f"could not connect to {where}: {error}"
                ) from error
            live: list[Allocation] = []
            for one in held:
                if _stale(one):
                    with contextlib.suppress(OSError):
                        _removed(endpoint, one.name)
                    shutil.rmtree(_mirrors(one.name), ignore_errors=True)
                else:
                    live.append(one)
            share = shared(
                stored,
                self.asked,
                live,
                where=where,
                role=self.role or "the environment",
            )
            try:
                swarm = SwarmConfig(
                    image=self.image,
                    workspace=str(self.workdir),
                    endpoint=str(endpoint),
                    name=self.name,
                    cpus=share.cpus,
                    memory=share.memory,
                    generic=(
                        ((stored.gpu_resource, share.gpus),)
                        if share.gpus and stored is not None
                        else ()
                    ),
                    constraints=stored.constraints if stored is not None else (),
                    nodes=_nodes(stored),
                    traced=self.traced,
                    run_args=stored.run_args if stored is not None else (),
                    labels={
                        PROVIDER: self.provider,
                        ROLE: self.role,
                        HOST: socket.gethostname(),
                        PID: str(os.getpid()),
                    },
                ).create()
            except ValueError as error:
                raise EnvUnavailable(f"{where}: {error}") from error
            try:
                swarm.start()
            except Unplaced as error:
                raise ResourceUnmet(f"{where}: {error}") from error
            except FileNotFoundError as error:
                raise EnvUnavailable(
                    f"{where}: {error.strerror or error}"
                    + (f": {error.filename}" if error.filename else "")
                ) from error
            except (RuntimeError, ValueError) as error:
                raise EnvUnavailable(f"{where}: {error}") from error
            except OSError as error:
                raise EnvConnectionError(f"{where}: {error}") from error
        placed = swarm.placed
        if placed is not None:
            from hmz.coganchor.transport import Target

            self.target = Target.parse(
                f"docker://{placed.container}@{placed.daemon}"
            ).describe()
        return swarm, share

    async def _up(self) -> None:
        """Creates the service where it is not yet, once however many ask at once."""
        if self._swarm is not None:
            return
        if self.closed:
            raise EnvError(f"the swarm@{self.provider} task was stopped")
        starting = self._starting
        if starting is None:
            starting = asyncio.ensure_future(asyncio.to_thread(self._brought_up))
            self._starting = starting

            def landed(task: asyncio.Future[tuple[Swarm, Share]]) -> None:
                if task.cancelled() or task.exception() is not None:
                    if self._starting is task:
                        self._starting = None  # asked again, it is tried again
                    return
                self._swarm, self._share = task.result()

            starting.add_done_callback(landed)
        await asyncio.shield(starting)

    async def _connected(self) -> Any:
        await self._up()
        return await super()._connected()

    async def close(self) -> None:
        """Lets go of the connection and removes the service, leaving the workdir."""
        await super().close()
        starting = self._starting
        if starting is not None and not starting.done():
            await asyncio.wait({starting})
        swarm, self._swarm = self._swarm, None
        if (
            swarm is None
            and starting is not None
            and starting.done()
            and not starting.cancelled()
            and starting.exception() is None
        ):
            swarm = starting.result()[0]
        self._starting = None
        if swarm is not None:
            await asyncio.to_thread(swarm.stop)
        await asyncio.to_thread(shutil.rmtree, self._mirrors, ignore_errors=True)

    # --- what is known without asking

    def resources(self, *, gpus: bool) -> Resources:
        """What the task reserved, and what its container sees where it reserved nothing."""
        del gpus
        share, facts = self._share, self._facts
        if share is None or facts is None:
            return Resources()
        seen = facts.resources
        return Resources(
            cpu_count=max(1, math.floor(share.cpus)) if share.cpus else seen.cpu_count,
            memory=share.memory or seen.memory,
            gpu_count=share.gpus,
            gpu_memory=seen.gpu_memory if share.gpus else 0,
        )

    def placement(self, workdir: PurePosixPath) -> Placement:
        """An anchored machine at the task's container, whose workspace is the workdir in it.

        The agent itself runs on this machine, supervised, in a mirror of its own, and
        everything it runs lands in the container, on whichever node that is.
        """
        from hmz.coganchor import AnchorConfig
        from hmz.coganchor.machines import AnchoredConfig

        facts = self._facts
        there = workdir
        if not there.is_absolute() and facts is not None:
            there = facts.home.joinpath(*there.parts[1:])
        mirror = hashlib.blake2b(str(there).encode(), digest_size=6).hexdigest()
        anchor = AnchorConfig(
            target=self.target,
            workspace=str(there),
            shadow=str(self._mirrors / mirror),
        )
        return Placement(
            EnvBackendKind.SWARM, self.provider, workdir, AnchoredConfig(anchor=anchor)
        )


def _removed(endpoint: Endpoint, service: str) -> None:
    """Removes a service a run left behind, asking for so long at most.

    Raises:
      OSError: If it could not be asked.
    """
    import subprocess

    try:
        subprocess.run(
            endpoint.docker("service", "rm", service),
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=_ASKING,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise OSError(f"{service} was not removed within {_ASKING:g}s") from error


def _nodes(stored: SwarmRuntime | None) -> dict[str, str]:
    """The daemon of each node the runtime says how to reach, spelled as an endpoint is.

    Raises:
      EnvUnavailable: For one naming nothing that reaches it.
    """
    from hmz.coganchor.machines import store

    if stored is None:
        return {}
    reached: dict[str, str] = {}
    for node, via in stored.nodes.items():
        try:
            reached[node] = str(store.daemon_of(store.node_of(via)))
        except ValueError as error:
            raise EnvUnavailable(
                f"swarm@{stored.name}: node {node}: {error}"
            ) from error
    return reached

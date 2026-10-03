"""A container of its own on this Mac's Apple `container`, as an environment driver uses it.

What a docker environment is (:mod:`.environing_docker`), on the containers Apple's `container`
runs as small Linux virtual machines of this Mac: one container per environment a run is given,
brought up from the image the role declares -- else the runtime's, else :data:`IMAGE` --
holding the workdir at the path it has here, and given exactly the CPUs and memory the role
declares as its virtual machine's size. Everything derived from that environment is inside the
same container.

It is reached the way a docker container is, over coganchor's road: the serving half is put in
the container and started with `container exec`, which is all an image needs besides `/bin/sh`
and a Python -- no sshd.

What a runtime may hand out is shared between every run on this machine by a lock on the
runtime, as a docker runtime's is: what its running containers already hold is read off their
labels, what the role asks is checked against what is left, and the container that takes it
is running -- labelled with what it took -- before the next run is let ask. A run that died
without taking its containers down leaves them labelled with its host and pid, and the next run
on that runtime takes down any whose process is gone. There are no GPUs to share: a role asking
for one is refused.
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
import subprocess
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
    TRACING,
    Asked,
    Has,
    Share,
    _held,  # pyright: ignore[reportPrivateUsage]
    _mirrors,  # pyright: ignore[reportPrivateUsage]
    _stale,  # pyright: ignore[reportPrivateUsage]
    shared,
)
from .environing_ssh import SSHMachine
from .spi import Placement

if TYPE_CHECKING:
    from pathlib import PurePosixPath

    from hmz.coganchor.machines import Allocation, AppleContainer
    from hmz.coganchor.machines.store import AppleContainerRuntime

    from .declaring import EnvRole

__all__ = ["LOCAL", "AppleContainerMachine"]

#: The runtime this Mac's containers are named by, where none is written down under it.
LOCAL = "local"

#: How long `container` is given to answer each question asked of it while its runtime is held
#: against every other run: one that has stopped answering must not hold them all.
_ASKING = 60.0


class AppleContainerMachine(SSHMachine):
    """A container of its own on this Mac, started the first time something is asked of it.

    Reached as an ssh host is, over coganchor's serving half, with `container exec` for the
    road there: :class:`~.environing_ssh.SSHMachine` is all of that, and this adds bringing the
    container up first, what it was given, where an agent working in it is put, and taking it
    down again.
    """

    backend = EnvBackendKind.APPLE_CONTAINER

    over = "container exec"

    def __init__(
        self,
        provider: str,
        workdir: PurePosixPath,
        *,
        stored: AppleContainerRuntime | None = None,
        role: EnvRole | None = None,
        named: str = "",
        traced: bool = False,
    ) -> None:
        """Initializes a machine whose container has not been started.

        Args:
          provider: The runtime's name, or :data:`LOCAL` for this Mac's containers with
            nothing saved.
          workdir: The directory of this Mac the container holds, absolute.
          stored: The runtime as it is written down, or None for this Mac's with nothing
            saved, which may hand out all of it.
          role: What the container is for, whose image and resources it is started with;
            None asks for nothing.
          named: The role's name, where there is no role to read it off.
          traced: Whether a harness runs in it, which starts it with
            :data:`~.environing_docker.TRACING`.
        """
        from hmz.coganchor.transport import APPLE, Target

        role_name = role.name if role is not None else named
        name = "-".join(
            one
            for one in ("humanize", provider, role_name, secrets.token_hex(4))
            if one
        )
        super().__init__(provider, Target.parse(f"{APPLE}://{name}").describe())
        self.identity = self.target
        self.name = name
        self.workdir = workdir
        self.stored = stored
        self.role = role_name
        self.asked = (
            Asked(role.cpu_count, role.memory, role.gpu_count, role.gpu_memory)
            if role is not None
            else Asked()
        )
        image = (role.image if role is not None else "") or (
            stored.image if stored is not None else ""
        )
        self.image = image or IMAGE
        self.traced = traced
        self._container: AppleContainer | None = None
        self._share: Share | None = None
        self._starting: asyncio.Future[tuple[AppleContainer, Share]] | None = None
        self._mirrors = _mirrors(name)

    # --- bringing it up

    def _brought_up(self) -> tuple[AppleContainer, Share]:
        """Works out its share and starts it, holding the runtime while it does.

        Raises:
          ResourceUnmet: If the runtime has not got what the role asks left, or the role asks
            for a GPU.
          EnvUnavailable: If there is no `container` here, or the container cannot be started.
          EnvConnectionError: If Apple's container system cannot be asked.
        """
        from hmz.coganchor.machines import AppleContainerConfig, store
        from hmz.coganchor.machines.apple_container import (
            CONTAINER,
            allocations,
            capacity,
            status,
        )

        where = f"{self.backend}@{self.provider}"
        stored = self.stored
        with _held(self.provider, store.APPLE_CONTAINER):
            if shutil.which(CONTAINER) is None:
                raise EnvUnavailable(
                    f"{where}: Apple's container was not found on this machine"
                )
            try:
                has = capacity(status(_ASKING))
                running = allocations({PROVIDER: self.provider}, seconds=_ASKING)
            except OSError as error:
                raise EnvConnectionError(
                    f"could not connect to {where}: {error}"
                ) from error
            live: list[Allocation] = []
            for one in running:
                if _stale(one):
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        subprocess.run(
                            [CONTAINER, "delete", "--force", one.name],
                            capture_output=True,
                            stdin=subprocess.DEVNULL,
                            timeout=_ASKING,
                            check=False,
                        )
                    shutil.rmtree(_mirrors(one.name), ignore_errors=True)
                else:
                    live.append(one)
            role = self.role or "the environment"
            if self.asked.gpus:
                raise ResourceUnmet(
                    f"{where} has no GPU to hand out, Apple's containers being given "
                    f"none, and {role!r} asks for {self.asked.gpus}"
                )
            share = shared(
                self.asked,
                Has(
                    (stored.cpus if stored is not None else 0) or has[0],
                    (stored.memory if stored is not None else 0) or has[1],
                    (),
                    containers=stored.max_containers if stored is not None else 0,
                ),
                live,
                where=where,
                role=role,
            )
            container = AppleContainerConfig(
                image=self.image,
                workspace=str(self.workdir),
                name=self.name,
                cpus=math.ceil(share.cpus) if share.cpus else None,
                memory=share.memory,
                run_args=(
                    *(TRACING if self.traced else ()),
                    *(stored.run_args if stored is not None else ()),
                ),
                labels={
                    PROVIDER: self.provider,
                    ROLE: self.role,
                    HOST: socket.gethostname(),
                    PID: str(os.getpid()),
                },
            ).create()
            try:
                container.start()
            except FileNotFoundError as error:
                raise EnvUnavailable(
                    f"{where} has no {error.filename or CONTAINER} to run a "
                    f"container: {error.strerror or error}"
                ) from error
            except (RuntimeError, ValueError) as error:
                raise EnvUnavailable(f"{where}: {error}") from error
            except OSError as error:
                raise EnvConnectionError(f"{where}: {error}") from error
        return container, share

    async def _up(self) -> None:
        """Brings the container up where it is not yet, once however many ask at once."""
        if self._container is not None:
            return
        if self.closed:
            raise EnvError(f"the {self.backend}@{self.provider} container was stopped")
        starting = self._starting
        if starting is None:
            starting = asyncio.ensure_future(asyncio.to_thread(self._brought_up))
            self._starting = starting

            def landed(task: asyncio.Future[tuple[AppleContainer, Share]]) -> None:
                if task.cancelled() or task.exception() is not None:
                    if self._starting is task:
                        self._starting = None  # asked again, it is tried again
                    return
                self._container, self._share = task.result()

            starting.add_done_callback(landed)
        await asyncio.shield(starting)

    async def _connected(self) -> Any:
        await self._up()
        return await super()._connected()

    async def close(self) -> None:
        """Lets go of the connection and takes the container down, leaving the workdir."""
        await super().close()
        starting = self._starting
        if starting is not None and not starting.done():
            await asyncio.wait({starting})
        container, self._container = self._container, None
        if (
            container is None
            and starting is not None
            and starting.done()
            and not starting.cancelled()
            and starting.exception() is None
        ):
            container = starting.result()[0]
        self._starting = None
        if container is not None:
            await asyncio.to_thread(container.stop)
        await asyncio.to_thread(shutil.rmtree, self._mirrors, ignore_errors=True)

    # --- what is known without asking

    def resources(self, *, gpus: bool) -> Resources:
        """What the container was given, and what it sees where it was given nothing."""
        del gpus
        share, facts = self._share, self._facts
        if share is None or facts is None:
            return Resources()
        seen = facts.resources
        return Resources(
            cpu_count=max(1, math.floor(share.cpus)) if share.cpus else seen.cpu_count,
            memory=share.memory or seen.memory,
        )

    def placement(self, workdir: PurePosixPath) -> Placement:
        """An anchored machine at the container, whose workspace is the workdir in it.

        Where its harness then runs is the affinity's to say, as for a docker container: on
        this machine, supervised in a mirror of its own -- which needs this machine to be
        Linux, and a Mac is not -- or the container's own CLI, driven natively.
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
            self.backend, self.provider, workdir, AnchoredConfig(anchor=anchor)
        )

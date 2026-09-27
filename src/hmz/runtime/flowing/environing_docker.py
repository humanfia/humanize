"""A container of its own on a docker daemon, as an environment driver does its work in it.

One container per environment a run is given: brought up from the image the role declares --
else the provider's, else :data:`IMAGE` -- on the daemon a docker provider names, holding the
workdir at the path it has on the daemon's host, and given exactly the CPUs, memory and GPUs
the role declares as hard limits. Everything derived from that environment -- a subdirectory, a
worktree, a temporary copy, a scratch directory -- is inside the same container; what is not
under the workdir is the container's own, and goes with it.

It is reached the way an ssh host is (:mod:`.environing_ssh`), over coganchor's road: the
serving half is put in the container and started with `docker exec`, which is all an image
needs besides `/bin/sh` and a Python -- no sshd -- and an agent working here is anchored to the
same container, supervised on this machine with every command it runs landing in there.

What a provider may hand out is shared between every run on this machine by a lock on the
provider: what its running containers already hold is read off their labels, what the role
asks is checked against what is left, and the container that takes it is running -- labelled
with what it took -- before the next run is let ask. A run that died without taking its
containers down leaves them labelled with its host and pid, and the next run on that provider
takes down any whose process is gone.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import hashlib
import math
import os
import secrets
import shutil
import socket
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from hmz.flows import (
    EnvBackendKind,
    EnvConnectionError,
    EnvError,
    EnvUnavailable,
    ResourceUnmet,
)

from .environing import Resources
from .environing_ssh import SSHMachine
from .spi import Placement

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping, Sequence
    from pathlib import Path, PurePosixPath

    from hmz.coganchor import AnchorConfig
    from hmz.coganchor.machines import Allocation, Docker
    from hmz.coganchor.machines.store import DockerProvider
    from hmz.coganchor.transport import Endpoint

    from .declaring import EnvRole

__all__ = [
    "HOST",
    "IMAGE",
    "LOCAL",
    "PID",
    "PROVIDER",
    "ROLE",
    "Asked",
    "DockerMachine",
    "Has",
    "Share",
    "has_of",
    "shared",
]

#: What a container is started from where neither the role nor the provider says: small, and
#: holding the `/bin/sh` and the Python the serving half needs.
IMAGE = "python:3.12-slim"

#: The provider docker's default here is named by, where no provider is written down under it.
LOCAL = "local"

#: What a container is labelled with besides what it holds: the provider it was handed out
#: by, the role it is for, and the host and process that brought it up -- which is what tells
#: a container a run left behind when it died from one a run is still using.
PROVIDER = "humanize.provider"

#: How long a daemon is given to answer each question asked of it while its provider is held
#: against every other run: one that has stopped answering must not hold them all.
_ASKING = 60.0
ROLE = "humanize.role"
HOST = "humanize.host"
PID = "humanize.pid"


# ---------------------------------------------------------------------------- what is free


@dataclass(frozen=True, slots=True)
class Asked:
    """What a role asks of a container: each amount 0 where it asks for none.

    Attributes:
      cpus: CPUs.
      memory: Bytes of memory.
      gpus: GPUs.
      gpu_memory: Bytes of memory each of those GPUs has.
    """

    cpus: int = 0
    memory: int = 0
    gpus: int = 0
    gpu_memory: int = 0


@dataclass(frozen=True, slots=True)
class Has:
    """What a provider may hand out, all told.

    Attributes:
      cpus: CPUs.
      memory: Bytes of memory.
      gpus: GPUs, by id, in the order they are handed out.
      gpu_memory: Bytes of memory each GPU has, or 0 where nothing says.
      containers: How many containers may run at once, or 0 for no limit.
    """

    cpus: float
    memory: int
    gpus: tuple[str, ...]
    gpu_memory: int = 0
    containers: int = 0


@dataclass(frozen=True, slots=True)
class Share:
    """What one container is given: the hard limits it runs under.

    Attributes:
      cpus: CPUs, or None for no limit.
      memory: Bytes of memory, or None for no limit.
      gpus: The GPUs it is given, by id; none for none.
    """

    cpus: float | None
    memory: int | None
    gpus: tuple[str, ...]


def has_of(provider: DockerProvider | None, info: Mapping[str, Any]) -> Has:
    """What a provider may hand out: as written down, the daemon's own for what is 0.

    Args:
      provider: The provider, or None for docker's default here, which may hand out all of
        what its daemon has.
      info: What `docker info` said of the daemon.
    """
    from hmz.coganchor.machines.docker import CDI, gpus_listed

    cpus = float(info.get("NCPU") or 0)
    memory = int(info.get("MemTotal") or 0)
    # NVIDIA's alone, being the one kind a container is handed a GPU of.
    devices = cast("list[Any]", info.get("DiscoveredDevices") or [])
    gpus = gpus_listed(devices, CDI)
    if provider is None:
        return Has(cpus, memory, gpus)
    return Has(
        provider.cpus or cpus,
        provider.memory or memory,
        provider.gpus or gpus,
        provider.gpu_memory,
        provider.max_containers,
    )


def shared(
    asked: Asked,
    has: Has,
    held: Sequence[Allocation],
    *,
    where: str,
    role: str,
) -> Share:
    """What a container for a role is given out of what is left of a provider, or why not.

    Args:
      asked: What the role asks.
      has: What the provider may hand out, all told.
      held: What each of its running containers already holds.
      where: The provider, as a message names it: `docker@<name>`.
      role: The role, as a message names it.

    Returns:
      The share: exactly what was asked, and the first GPUs nobody holds.

    Raises:
      ResourceUnmet: Naming everything that is short, and who holds it.
    """
    short: list[str] = []
    if has.containers and len(held) >= has.containers:
        short.append(
            f"{where} runs {len(held)} of the {has.containers} containers it may"
            + _by(held, lambda _: "one")
        )
    holding = [one for one in held if one.cpus]
    free = has.cpus - sum(one.cpus or 0 for one in holding)
    if asked.cpus > free + 1e-9:
        short.append(
            f"{where} has {max(free, 0):g} of {has.cpus:g} CPUs free, and {role!r} asks "
            f"for {asked.cpus}" + _by(holding, lambda one: f"{one.cpus:g} CPUs")
        )
    holding = [one for one in held if one.memory]
    left = has.memory - sum(one.memory or 0 for one in holding)
    if asked.memory > left:
        short.append(
            f"{where} has {_bytes(max(left, 0))} of {_bytes(has.memory)} of memory free, "
            f"and {role!r} asks for {_bytes(asked.memory)}"
            + _by(holding, lambda one: _bytes(one.memory or 0))
        )
    taken: set[str] = set()
    holding = [one for one in held if one.gpus]
    for one in holding:
        taken.update(has.gpus if one.gpus == "all" else one.gpus)
    gpus = tuple(one for one in has.gpus if one not in taken)
    if asked.gpus > len(gpus):
        short.append(
            f"{where} has {len(gpus)} of {len(has.gpus)} GPUs free, and {role!r} asks "
            f"for {asked.gpus}"
            + (
                _by(holding, _gpus_of)
                if has.gpus
                else " (its daemon lists no GPU by name: say which in the provider's gpus)"
            )
        )
    if asked.gpus and asked.gpu_memory and 0 < has.gpu_memory < asked.gpu_memory:
        short.append(
            f"{where}'s GPUs have {_bytes(has.gpu_memory)} each, and {role!r} asks for "
            f"{_bytes(asked.gpu_memory)}"
        )
    if short:
        raise ResourceUnmet("; ".join(short))
    return Share(
        float(asked.cpus) if asked.cpus else None,
        asked.memory or None,
        gpus[: asked.gpus],
    )


def _gpus_of(one: Allocation) -> str:
    """The GPUs a container holds, in words."""
    return "every GPU" if one.gpus == "all" else f"GPU {', '.join(one.gpus)}"


def _by(held: Sequence[Allocation], what: Callable[[Allocation], str]) -> str:
    """Who holds what is short, for the end of a message: what each holds, and whose it is.

    Args:
      held: The containers holding it.
      what: What one of them holds of it, in words.
    """
    if not held:
        return ""
    said: list[str] = []
    for one in held:
        labels = one.labels
        run = (
            f", pid {labels[PID]} on {labels[HOST]}"
            if PID in labels and HOST in labels
            else ""
        )
        said.append(f"{what(one)} held by {one.name}{run}")
    return f" ({'; '.join(said)})"


def _bytes(amount: int) -> str:
    """An amount of memory, as a person reads one."""
    for unit, size in (("TiB", 1 << 40), ("GiB", 1 << 30), ("MiB", 1 << 20)):
        if amount >= size:
            return f"{amount / size:.3g} {unit}"
    return f"{amount} bytes"


# ------------------------------------------------------------------------ bringing one up


@contextlib.contextmanager
def _held(provider: str) -> Generator[None]:
    """Holds a provider against every other run on this machine asking it for a container.

    A lock file beside the providers, one per provider, held while what is free is worked out
    and the container that takes its share is started, and let go of by the kernel however
    the process holding it ends.
    """
    from hmz.coganchor.machines import store

    at = store.under() / store.DOCKER
    at.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (at / f".{provider}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _info(endpoint: Endpoint, where: str) -> dict[str, Any]:
    """What a daemon says of itself, asked for so long at most.

    Raises:
      EnvUnavailable: If there is no `docker` here.
      EnvConnectionError: If the daemon could not be asked, or did not answer in time.
    """
    from hmz.coganchor.machines import info

    if shutil.which("docker") is None:
        raise EnvUnavailable(f"{where}: there is no docker here to reach it with")
    try:
        return info(str(endpoint), _ASKING)
    except OSError as error:
        raise EnvConnectionError(f"could not reach {where}: {error}") from error


def _mirrors(name: str) -> Path:
    """Where the agents working in a container keep their mirrors of it, on this machine.

    Under humanize's home rather than the system's temporary directory, so that nobody else
    here can have made it first; nothing is made here, and it goes with the container.
    """
    from hmz import home

    from .environing import ENVS

    return home() / ENVS / "mirrors" / name


def _stale(one: Allocation) -> bool:
    """Whether a container was left by a process of this user's on this host that is gone."""
    said = one.labels
    if (
        said.get("humanize") != str(os.getuid())
        or said.get(HOST) != socket.gethostname()
    ):
        return False
    pid = said.get(PID, "")
    if not pid.isdigit():
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return False


class DockerMachine(SSHMachine):
    """A container of its own, started the first time something is asked of it.

    Reached as an ssh host is, over coganchor's serving half, with `docker exec` for the road
    there: :class:`~.environing_ssh.SSHMachine` is all of that, and this adds bringing the
    container up first, what it was given, where an agent working in it is put, and taking it
    down again.
    """

    backend = EnvBackendKind.DOCKER

    over = "docker exec"

    def __init__(
        self,
        provider: str,
        workdir: PurePosixPath,
        *,
        stored: DockerProvider | None = None,
        role: EnvRole | None = None,
        named: str = "",
    ) -> None:
        """Initializes a machine whose container has not been started.

        Args:
          provider: The docker provider's name, or :data:`LOCAL` for docker's default here.
          workdir: The directory of the daemon's host the container holds, absolute.
          stored: The provider as it is written down, or None for docker's default here.
          role: What the container is for, whose image and resources it is started with;
            None asks for nothing.
          named: The role's name, where there is no role to read it off.

        Raises:
          EnvUnavailable: If the provider's endpoint cannot be reached as it is written.
        """
        from hmz.coganchor.transport import Endpoint, Target

        try:
            endpoint = stored.daemon() if stored is not None else Endpoint()
        except ValueError as error:
            raise EnvUnavailable(f"docker@{provider}: {error}") from error
        role_name = role.name if role is not None else named
        name = "-".join(
            one
            for one in ("humanize", provider, role_name, secrets.token_hex(4))
            if one
        )
        super().__init__(
            provider, Target.parse(f"docker://{name}@{endpoint}").describe()
        )
        self.identity = self.target
        self.endpoint = endpoint
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
        self._docker: Docker | None = None
        self._share: Share | None = None
        self._starting: asyncio.Future[tuple[Docker, Share]] | None = None
        self._mirrors = _mirrors(name)

    # --- bringing it up

    def _brought_up(self) -> tuple[Docker, Share]:
        """Works out its share and starts it, holding the provider while it does.

        Raises:
          ResourceUnmet: If the provider has not got what the role asks left.
          EnvUnavailable: If the container cannot be started there.
          EnvConnectionError: If the daemon cannot be asked.
        """
        from hmz.coganchor.machines import DockerConfig, allocations

        where = f"docker@{self.provider}"
        endpoint = self.endpoint
        stored = self.stored
        with _held(self.provider):
            info = _info(endpoint, where)
            try:
                held = allocations(
                    str(endpoint), {PROVIDER: self.provider}, seconds=_ASKING
                )
            except OSError as error:
                raise EnvConnectionError(f"could not reach {where}: {error}") from error
            live: list[Allocation] = []
            for one in held:
                if _stale(one):
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        subprocess.run(
                            endpoint.docker("rm", "--force", one.name),
                            capture_output=True,
                            timeout=_ASKING,
                            check=False,
                        )
                    shutil.rmtree(_mirrors(one.name), ignore_errors=True)
                else:
                    live.append(one)
            share = shared(
                self.asked,
                has_of(stored, info),
                live,
                where=where,
                role=self.role or "the environment",
            )
            docker = DockerConfig(
                image=self.image,
                workspace=str(self.workdir),
                endpoint=str(endpoint),
                name=self.name,
                cpus=share.cpus,
                memory=share.memory,
                gpus=share.gpus,
                runtime=(stored.runtime if stored is not None else "") or None,
                run_args=stored.run_args if stored is not None else (),
                labels={
                    PROVIDER: self.provider,
                    ROLE: self.role,
                    HOST: socket.gethostname(),
                    PID: str(os.getpid()),
                },
            ).create()
            try:
                docker.start()
            except FileNotFoundError as error:
                raise EnvUnavailable(
                    f"{where} has no {error.filename or 'docker'} to give a container: "
                    f"{error.strerror or error}"
                ) from error
            except (RuntimeError, ValueError) as error:
                raise EnvUnavailable(f"{where}: {error}") from error
            except OSError as error:
                raise EnvConnectionError(f"{where}: {error}") from error
        return docker, share

    async def _up(self) -> None:
        """Brings the container up where it is not yet, once however many ask at once."""
        if self._docker is not None:
            return
        if self.closed:
            raise EnvError(f"the container of docker@{self.provider} was taken down")
        starting = self._starting
        if starting is None:
            starting = asyncio.ensure_future(asyncio.to_thread(self._brought_up))
            self._starting = starting

            def landed(task: asyncio.Future[tuple[Docker, Share]]) -> None:
                if task.cancelled() or task.exception() is not None:
                    if self._starting is task:
                        self._starting = None  # asked again, it is tried again
                    return
                self._docker, self._share = task.result()

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
        docker, self._docker = self._docker, None
        if (
            docker is None
            and starting is not None
            and starting.done()
            and not starting.cancelled()
            and starting.exception() is None
        ):
            docker = starting.result()[0]
        self._starting = None
        if docker is not None:
            await asyncio.to_thread(docker.stop)
        await asyncio.to_thread(shutil.rmtree, self._mirrors, ignore_errors=True)

    # --- what is known without asking

    def resources(self, *, gpus: bool) -> Resources:
        """What the container was given, and what it sees where it was given no limit."""
        del gpus
        share, facts = self._share, self._facts
        if share is None or facts is None:
            return Resources()
        seen = facts.resources
        memory = self.stored.gpu_memory if self.stored is not None else 0
        return Resources(
            cpu_count=max(1, math.floor(share.cpus)) if share.cpus else seen.cpu_count,
            memory=share.memory or seen.memory,
            gpu_count=len(share.gpus),
            gpu_memory=(memory or seen.gpu_memory) if share.gpus else 0,
        )

    def placement(self, workdir: PurePosixPath) -> Placement:
        """An anchored machine at the container, whose workspace is the workdir in it.

        The agent itself runs on this machine, supervised, in a mirror of the workdir of its
        own -- which is never the workdir, even where the daemon is this machine's and the
        two are one path -- and everything it runs lands in the container.
        """
        from hmz.coganchor import AnchorConfig
        from hmz.coganchor.machines import AnchoredConfig

        facts = self._facts
        there = workdir
        if not there.is_absolute() and facts is not None:
            there = facts.home.joinpath(*there.parts[1:])
        mirror = hashlib.blake2b(str(there).encode(), digest_size=6).hexdigest()
        anchor: AnchorConfig = AnchorConfig(
            target=self.target,
            workspace=str(there),
            shadow=str(self._mirrors / mirror),
        )
        return Placement(
            EnvBackendKind.DOCKER, self.provider, workdir, AnchoredConfig(anchor=anchor)
        )

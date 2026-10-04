"""A container of its own on a docker daemon, as an environment driver does its work in it.

One container per environment a run is given: brought up from the image the role declares --
else the runtime's, else :data:`IMAGE` -- on the daemon a docker runtime names, holding the
workdir at the path it has on the daemon's host, and given exactly the CPUs, memory and GPUs
the role declares as hard limits. Everything derived from that environment -- a subdirectory, a
worktree, a temporary copy, a scratch directory -- is inside the same container; what is not
under the workdir is the container's own, and goes with it.

It is reached the way an ssh host is (:mod:`.environing_ssh`), over coganchor's road: the
serving half is put in the container and started with `docker exec`, which is all an image
needs besides `/bin/sh` and a Python -- no sshd -- and an agent working here is anchored to the
same container, supervised on this machine with every command it runs landing in there.

What a runtime may hand out is shared between every run on this machine by a lock on the
runtime: what its running containers already hold is read off their labels, what the role
asks is checked against what is left, and the container that takes it is running -- labelled
with what it took -- before the next run is let ask. A run that died without taking its
containers down leaves them labelled with its host and pid, and the next run on that runtime
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
from dataclasses import dataclass, field
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
    from hmz.coganchor.machines.store import DockerRuntime
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

#: What a container is started from where neither the role nor the runtime says: small, and
#: holding the `/bin/sh` and the Python the serving half needs.
IMAGE = "python:3.12-slim"

#: The runtime docker's default here is named by, where no runtime is written down under it.
LOCAL = "local"

#: What a container a harness runs in is started with besides what its runtime says. The
#: supervisor there borrows each command's descriptors from the agent with `pidfd_getfd`,
#: which docker's default seccomp profile refuses a container not given `CAP_SYS_PTRACE`.
#: One opened again through `/proc` stands in for a pipe or a tty, but not for a socket --
#: which is what opencode and Claude Code hand theirs -- and a command whose output could
#: not be borrowed runs and says nothing. Within the container and nowhere else: its
#: processes are the harness's own.
TRACING = ("--cap-add", "SYS_PTRACE")

#: What a container is labelled with besides what it holds: the runtime it was handed out
#: by, the role it is for, and the host and process that brought it up -- which is what tells
#: a container a run left behind when it died from one a run is still using.
PROVIDER = "humanize.provider"

#: How long a daemon is given to answer each question asked of it while its runtime is held
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
    """What a runtime may hand out, all told.

    Attributes:
      cpus: CPUs.
      memory: Bytes of memory.
      gpus: GPUs, by id, in the order they are handed out: those that answer, where its
        daemon's host was asked which do.
      gpu_memory: Bytes of memory each GPU has, or 0 where nothing says.
      containers: How many containers may run at once, or 0 for no limit.
      listed: How many GPUs it lists, answering or not, or None for as many as `gpus`.
      known: Every other id a GPU of `gpus` is known by -- its index, its UUID -- mapped to
        the one it is handed out by, so that a container labelled with either holds it.
    """

    cpus: float
    memory: int
    gpus: tuple[str, ...]
    gpu_memory: int = 0
    containers: int = 0
    listed: int | None = None
    known: Mapping[str, str] = field(default_factory=dict[str, str])

    @property
    def bound(self) -> int:
        """How many GPUs it lists, answering or not."""
        return len(self.gpus) if self.listed is None else self.listed


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


def has_of(
    runtime: DockerRuntime | None,
    info: Mapping[str, Any],
    usable: Sequence[tuple[str, str]] | None = None,
) -> Has:
    """What a runtime may hand out: as written down, the daemon's own for what is 0.

    Args:
      runtime: The runtime, or None for docker's default here, which may hand out all of
        what its daemon has.
      info: What `docker info` said of the daemon.
      usable: The GPUs of its host that answer, as
        :func:`~hmz.coganchor.machines.gpus_usable` says them, or None where nobody asked --
        which leaves every GPU listed to be handed out.
    """
    from hmz.coganchor.machines.docker import CDI, gpus_listed

    cpus = float(info.get("NCPU") or 0)
    memory = int(info.get("MemTotal") or 0)
    # NVIDIA's alone, being the one kind a container is handed a GPU of.
    devices = cast("list[Any]", info.get("DiscoveredDevices") or [])
    named = runtime.gpus if runtime is not None and runtime.gpus else ()
    named = named or gpus_listed(devices, CDI)
    if usable is not None and not named:
        # A daemon that lists none by name, but hands a container every GPU it is asked
        # for: what answers there is what it has.
        named = tuple(name for name, _ in usable)
    gpus, known = (named, {}) if usable is None else _answering(named, usable, devices)
    listed = None if usable is None else len(named)
    if runtime is None:
        return Has(cpus, memory, gpus, listed=listed, known=known)
    return Has(
        runtime.cpus or cpus,
        runtime.memory or memory,
        gpus,
        runtime.gpu_memory,
        runtime.max_containers,
        listed=listed,
        known=known,
    )


def _answering(
    named: Sequence[str], usable: Sequence[tuple[str, str]], devices: Sequence[Any]
) -> tuple[tuple[str, ...], dict[str, str]]:
    """Which of the GPUs named answer, each by the id it is handed out by, and its aliases.

    A GPU that answered under a CDI name is handed out by that name, which a container was
    just given it by; one the daemon lists no name for is handed out by its UUID, the one id
    that is the same GPU however `nvidia-smi` numbers them by then.

    Args:
      named: The GPUs the runtime may hand out, by name or by UUID.
      usable: The GPUs that answer, as `(name, uuid)`.
      devices: `DiscoveredDevices`, as `docker info` says it.

    Returns:
      Those that answer, in the order named, and every id each is known by, mapped to the
      one it is handed out by.
    """
    from hmz.coganchor.machines.docker import CDI, gpus_listed

    listed = set(gpus_listed(devices, CDI))
    by_name = dict(usable)
    at = {uuid: name for name, uuid in usable}
    gpus: list[str] = []
    known: dict[str, str] = {}
    for one in named:
        uuid = one if one in at else by_name.get(one)
        if uuid is None or uuid in known:
            continue
        name = at[uuid]
        handed = name if name in listed else uuid
        gpus.append(handed)
        known.update({name: handed, uuid: handed, one: handed})
    return tuple(gpus), known


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
      has: What the runtime may hand out, all told.
      held: What each of its running containers already holds.
      where: The provider, as a message names it: `docker@<name>`, or `docker` here.
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
        taken.update(
            has.gpus
            if one.gpus == "all"
            else (has.known.get(id_, id_) for id_ in one.gpus)
        )
    gpus = tuple(one for one in has.gpus if one not in taken)
    if asked.gpus > len(gpus):
        failed = has.bound - len(has.gpus)
        short.append(
            f"{where} has {len(gpus)} of {len(has.gpus)} GPUs free, and {role!r} asks "
            f"for {asked.gpus}"
            + (
                f" ({len(has.gpus)} of the {has.bound} GPUs it lists are usable: {failed} "
                + ("is bound but does" if failed == 1 else "are bound but do")
                + " not answer)"
                if failed > 0
                else ""
            )
            + (
                _by(holding, _gpus_of)
                if has.bound
                else " (no GPU of its host answers)"
                if has.listed is not None
                else " (its daemon lists no GPU by name: say which in the runtime's gpus)"
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
def _held(provider: str, backend: str = "") -> Generator[None]:
    """Holds a runtime against every other run on this machine asking it for a container.

    A lock file among what is this machine's alone, one per runtime, held while what is free
    is worked out and the container that takes its share is started, and let go of by the
    kernel however the process holding it ends. A docker runtime's unless another backend is
    named: a swarm's is held the same way, while its service is created.
    """
    from hmz import machine
    from hmz.coganchor.machines import store

    at = machine() / f".{backend or store.DOCKER}.{provider}.lock"
    with at.open("a") as lock:
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
        raise EnvUnavailable(f"{where}: docker was not found on this machine")
    try:
        return info(str(endpoint), _ASKING)
    except OSError as error:
        raise EnvConnectionError(f"could not connect to {where}: {error}") from error


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
        stored: DockerRuntime | None = None,
        role: EnvRole | None = None,
        named: str = "",
        traced: bool = False,
    ) -> None:
        """Initializes a machine whose container has not been started.

        Args:
          provider: The docker runtime's name, or :data:`LOCAL` for docker's default here.
          workdir: The directory of the daemon's host the container holds, absolute.
          stored: The runtime as it is written down, or None for docker's default here.
          role: What the container is for, whose image and resources it is started with;
            None asks for nothing.
          named: The role's name, where there is no role to read it off.
          traced: Whether a harness runs in it, which starts it with :data:`TRACING`.

        Raises:
          EnvUnavailable: If the runtime's endpoint cannot be reached as it is written.
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
        #: What a message calls it, as `-e` names it: by the runtime's name, or by no
        #: name at all for docker's default here.
        self.spelled = f"docker@{provider}" if stored is not None else "docker"
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
        self._docker: Docker | None = None
        self._share: Share | None = None
        self._starting: asyncio.Future[tuple[Docker, Share]] | None = None
        self._mirrors = _mirrors(name)

    # --- bringing it up

    def _brought_up(self) -> tuple[Docker, Share]:
        """Works out its share and starts it, holding the runtime while it does.

        Raises:
          ResourceUnmet: If the runtime has not got what the role asks left.
          EnvUnavailable: If the container cannot be started there.
          EnvConnectionError: If the daemon cannot be asked.
        """
        from hmz.coganchor.machines import DockerConfig, allocations

        where = self.spelled
        endpoint = self.endpoint
        stored = self.stored
        with _held(self.provider):
            info = _info(endpoint, where)
            try:
                held = allocations(
                    str(endpoint), {PROVIDER: self.provider}, seconds=_ASKING
                )
            except OSError as error:
                raise EnvConnectionError(
                    f"could not connect to {where}: {error}"
                ) from error
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
                has_of(stored, info, self._usable(info) if self.asked.gpus else None),
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
                docker.start()
            except FileNotFoundError as error:
                raise EnvUnavailable(
                    f"{where} has no {error.filename or 'docker'} to run a "
                    f"container: {error.strerror or error}"
                ) from error
            except (RuntimeError, ValueError) as error:
                raise EnvUnavailable(f"{where}: {error}") from error
            except OSError as error:
                raise EnvConnectionError(f"{where}: {error}") from error
        return docker, share

    def _usable(self, info: Mapping[str, Any]) -> tuple[tuple[str, str], ...] | None:
        """The GPUs of the daemon's host that answer, or None where it could not be asked.

        Asked only for a role that asks for a GPU, and of a container of the image this one
        is started from, which is pulled for it anyway.
        """
        from hmz.coganchor.machines import gpus_usable

        devices = cast("list[Any]", info.get("DiscoveredDevices") or [])
        return gpus_usable(str(self.endpoint), self.image, devices, seconds=_ASKING)

    async def _up(self) -> None:
        """Brings the container up where it is not yet, once however many ask at once."""
        if self._docker is not None:
            return
        if self.closed:
            raise EnvError(f"the {self.spelled} container was stopped")
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

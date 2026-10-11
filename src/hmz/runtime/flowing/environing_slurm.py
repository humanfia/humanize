"""A job of its own on a Slurm cluster, as an environment driver does its work on its node.

One job per environment a run is given, submitted with `sbatch` from this machine as a Slurm
runtime asks for one -- its partition, account, quality of service, time and features, `local`
being the cluster's defaults where no runtime is written down under that name -- asking for the
CPUs, memory and GPUs the role declares, which the cluster confines it to. The cluster puts it
on whichever node has them; the workdir is the path it has there, which a cluster's shared
filesystem makes the path it has here too.

Once it runs it is reached over coganchor's road, by `srun --overlap` as a step of the job
itself -- or, where the runtime says so, over TCP to the serving half the job itself runs,
with the secret only this run was told --, with the Python the runtime names where the nodes'
own are too old. Everything
downstream of that, the mirror an agent works in, the files, is the node's and cannot tell.

What the runtime may hand out -- how many jobs, how many CPUs and bytes all told -- is shared
between every run on this machine by a lock on the runtime, as a docker runtime's is, and read
off the comments of the jobs it already has, waiting or running. The lock is held while that is
worked out and the job submitted, and not while it waits for a node: a cluster's queue is the
cluster's to keep, and a run waiting in it must not keep every other run here out of it. A job
that waits longer than the runtime lets it is cancelled and the run told why Slurm said it was
waiting. A run that died without cancelling its jobs leaves them labelled with its host and pid,
and the next run on that runtime cancels any whose process is gone.
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
    PID,
    PROVIDER,
    ROLE,
    _by,  # pyright: ignore[reportPrivateUsage]
    _bytes,  # pyright: ignore[reportPrivateUsage]
    _held,  # pyright: ignore[reportPrivateUsage]
    _mirrors,  # pyright: ignore[reportPrivateUsage]
    _stale,  # pyright: ignore[reportPrivateUsage]
)
from .environing_ssh import SSHMachine
from .spi import Placement

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import PurePosixPath

    from hmz.coganchor.machines import Allocation, Slurm
    from hmz.coganchor.machines.store import SlurmRuntime

    from .declaring import EnvRole

__all__ = ["LOCAL", "Share", "SlurmMachine", "shared"]

#: The runtime the cluster's own defaults are named by, where none is written down under it.
LOCAL = "local"

#: How long the cluster is given to answer each question asked of it while its runtime is held.
_ASKING = 60.0


@dataclass(frozen=True, slots=True)
class Share:
    """What one job asks of its node, which is what it may take of it.

    Attributes:
      cpus: CPUs, or None for the partition's default.
      memory: Bytes of memory, likewise.
      gpus: GPUs.
    """

    cpus: int | None
    memory: int | None
    gpus: int


def shared(
    stored: SlurmRuntime | None,
    asked: tuple[int, int, int],
    held: Sequence[Allocation],
    *,
    where: str,
    role: str,
) -> Share:
    """What a job for a role asks out of what is left of a runtime, or why not.

    What is left of the runtime, and not of the cluster: whether a node has room is the
    scheduler's to say once the job is submitted.

    Args:
      stored: The runtime, or None for the cluster's defaults, which may hand out whatever
        the cluster gives.
      asked: What the role asks: CPUs, bytes of memory, GPUs.
      held: What each of the runtime's jobs already holds, waiting or running.
      where: The runtime, as a message names it: `slurm@<name>`, or `slurm` here.
      role: The role, as a message names it.

    Raises:
      ResourceUnmet: Naming everything that is short, and who holds it.
    """
    cpus, memory, gpus = asked
    short: list[str] = []
    if stored is not None and stored.max_jobs and len(held) >= stored.max_jobs:
        short.append(
            f"{where} has {len(held)} of the {stored.max_jobs} jobs it may"
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
    if short:
        raise ResourceUnmet("; ".join(short))
    return Share(cpus or None, memory or None, gpus)


class SlurmMachine(SSHMachine):
    """A job of its own on a cluster, submitted the first time something is asked of it.

    Reached over coganchor's serving half with `srun` for the road there, once it is known
    which job that is: this adds submitting the job first, what it asked for, where an agent
    working on its node is put, and cancelling it.
    """

    backend = EnvBackendKind.SLURM

    over = "srun"

    def __init__(
        self,
        provider: str,
        workdir: PurePosixPath,
        *,
        stored: SlurmRuntime | None = None,
        role: EnvRole | None = None,
        named: str = "",
    ) -> None:
        """Initializes a machine whose job has not been submitted.

        Args:
          provider: The Slurm runtime's name, or :data:`LOCAL` for the cluster's defaults.
          workdir: The directory the job works in, absolute, as each node names it.
          stored: The runtime as it is written down, or None for the cluster's defaults.
          role: What the job is for, whose resources it asks for; None asks for nothing.
          named: The role's name, where there is no role to read it off.
        """
        role_name = role.name if role is not None else named
        name = "-".join(
            one
            for one in ("humanize", provider, role_name, secrets.token_hex(4))
            if one
        )
        # Where the job is, which is not known until it has been submitted: until then, none.
        super().__init__(provider, "slurm://0")
        self.identity = f"slurm:{name}"
        self.name = name
        self.workdir = workdir
        self.stored = stored
        #: What a message calls it, as `-e` names it: by the runtime's name, or by no name
        #: at all for the cluster's defaults.
        self.spelled = f"slurm@{provider}" if stored is not None else "slurm"
        self.role = role_name
        self.asked = (
            (role.cpu_count, role.memory, role.gpu_count)
            if role is not None
            else (0, 0, 0)
        )
        self._slurm: Slurm | None = None
        self._share: Share | None = None
        self._starting: asyncio.Future[tuple[Slurm, Share]] | None = None
        self._mirrors = _mirrors(name)

    # --- bringing it up

    def _brought_up(self) -> tuple[Slurm, Share]:
        """Works out its share and submits its job holding the runtime, then waits for it.

        Raises:
          ResourceUnmet: If the runtime has not got what the role asks left, or no node took
            the job within the runtime's wait.
          EnvUnavailable: If there is no Slurm here, or the job could not be submitted or
            ended before it ran.
          EnvConnectionError: If the cluster, or the job's node, cannot be asked.
        """
        from hmz.coganchor.machines import SlurmConfig, store
        from hmz.coganchor.machines.slurm import Unplaced, jobs

        where = self.spelled
        stored = self.stored
        if shutil.which("sbatch") is None:
            raise EnvUnavailable(f"{where}: sbatch was not found on this machine")
        with _held(self.provider, store.SLURM):
            try:
                held = jobs({PROVIDER: self.provider}, seconds=_ASKING)
            except OSError as error:
                raise EnvConnectionError(
                    f"could not connect to {where}: {error}"
                ) from error
            live: list[Allocation] = []
            for one in held:
                if _stale(one):
                    with contextlib.suppress(OSError):
                        _cancelled(one.name)
                    shutil.rmtree(_mirrors(_named(one)), ignore_errors=True)
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
                slurm = SlurmConfig(
                    workspace=str(self.workdir),
                    name=self.name,
                    partition=stored.partition if stored is not None else "",
                    account=stored.account if stored is not None else "",
                    qos=stored.qos if stored is not None else "",
                    time=stored.time if stored is not None else "",
                    cpus=share.cpus,
                    memory=share.memory,
                    gpus=share.gpus,
                    constraint=stored.constraint if stored is not None else "",
                    python=stored.python if stored is not None else "",
                    via=stored.via if stored is not None else "srun",
                    sbatch_args=stored.run_args if stored is not None else (),
                    labels={
                        PROVIDER: self.provider,
                        ROLE: self.role,
                        HOST: socket.gethostname(),
                        PID: str(os.getpid()),
                        _NAME: self.name,
                    },
                    placing=(
                        float(stored.max_wait)
                        if stored is not None and stored.max_wait
                        else None
                    ),
                ).create()
            except ValueError as error:
                raise EnvUnavailable(f"{where}: {error}") from error
            try:
                slurm.submit()
            except FileNotFoundError as error:
                raise EnvUnavailable(f"{where}: {error.strerror or error}") from error
            except RuntimeError as error:
                raise EnvUnavailable(f"{where}: {error}") from error
            except OSError as error:
                raise EnvConnectionError(f"{where}: {error}") from error
        try:
            anchor = slurm.start()
        except Unplaced as error:
            raise ResourceUnmet(f"{where}: {error}") from error
        except (RuntimeError, ValueError) as error:
            raise EnvUnavailable(f"{where}: {error}") from error
        except OSError as error:
            raise EnvConnectionError(f"{where}: {error}") from error
        self.target, self.token = anchor.target, anchor.token
        return slurm, share

    async def _up(self) -> None:
        """Submits the job where it is not yet, once however many ask at once."""
        if self._slurm is not None:
            return
        if self.closed:
            raise EnvError(f"the {self.spelled} job was cancelled")
        starting = self._starting
        if starting is None:
            starting = asyncio.ensure_future(asyncio.to_thread(self._brought_up))
            self._starting = starting

            def landed(task: asyncio.Future[tuple[Slurm, Share]]) -> None:
                if task.cancelled() or task.exception() is not None:
                    if self._starting is task:
                        self._starting = None  # asked again, it is tried again
                    return
                self._slurm, self._share = task.result()

            starting.add_done_callback(landed)
        await asyncio.shield(starting)

    async def _connected(self) -> Any:
        await self._up()
        return await super()._connected()

    async def close(self) -> None:
        """Lets go of the connection and cancels the job, leaving the workdir."""
        await super().close()
        starting = self._starting
        if starting is not None and not starting.done():
            await asyncio.wait({starting})
        slurm, self._slurm = self._slurm, None
        if (
            slurm is None
            and starting is not None
            and starting.done()
            and not starting.cancelled()
            and starting.exception() is None
        ):
            slurm = starting.result()[0]
        self._starting = None
        if slurm is not None:
            await asyncio.to_thread(slurm.stop)
        await asyncio.to_thread(shutil.rmtree, self._mirrors, ignore_errors=True)

    # --- what is known without asking

    def resources(self, *, gpus: bool) -> Resources:
        """What the job asked for, and what its node says where it asked for nothing."""
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
        """An anchored machine at the job's node, whose workspace is the workdir there.

        The agent itself runs on this machine, supervised, in a mirror of its own, and
        everything it runs lands on the job's node.
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
            token=self.token,
        )
        return Placement(
            EnvBackendKind.SLURM, self.provider, workdir, AnchoredConfig(anchor=anchor)
        )


#: The label a job carries its name under, which its mirrors here are kept by.
_NAME = "humanize.name"


def _named(one: Allocation) -> str:
    """The name a job of humanize's was submitted under, which its mirrors are kept by."""
    return one.labels.get(_NAME, "") or one.name


def _cancelled(job: str) -> None:
    """Cancels a job a run left behind, asking for so long at most.

    Raises:
      OSError: If it could not be asked.
    """
    import subprocess

    try:
        subprocess.run(
            ["scancel", job],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=_ASKING,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise OSError(f"job {job} was not cancelled within {_ASKING:g}s") from error

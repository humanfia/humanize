"""A job of a Slurm cluster held for the agent, on whichever node the cluster gave it.

What :mod:`.swarm` is for a docker swarm, this is for Slurm: the machine is not named but asked
of the scheduler, as a job of one task submitted with `sbatch` from this machine, and the
cluster puts it on whichever node has the CPUs, memory and GPUs it asks for. Where it landed is
only known once it runs, and from then on it is reached one of two ways.

`srun`, the way the cluster itself reaches a running job: `srun --jobid=<job> --overlap`, a step
of that job on its node, sharing what the job was given rather than asking for more. Every
command is a step of its own, and every step holds listening ports on this machine while it
runs -- which a cluster may give `srun` only a few dozen of, shared by everybody here.

Or `tcp`: the job's own batch step is coganchor's serving half, left listening on the node for
as many connections as there are, each presenting a secret only this machine was told. Nothing
holds a port here, and every command still runs inside the job -- its CPUs, its memory, its
end. `srun` is then only what puts the serving half's archive on the node and reads which port
it was given, each once.

Nothing is a container here. The workspace is the directory as the node names it, which is
whatever the node's filesystems say: a cluster's shared filesystem, in practice, at the same
path on every node a job may land on and on this one. What a turn runs runs as the user who
submitted the job, with the node's own tools -- and, since a cluster's nodes may have no Python
young enough for coganchor's serving half, with one the runtime names where they have not.

What a job asks for is what it is limited to: the cluster confines a job to its allocation.
The labels a container of :mod:`.docker` carries go in the job's comment, so that what a
cluster's jobs hold is read back the same way.
"""

from __future__ import annotations

import contextlib
import errno
import math
import os
import re
import secrets
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, quote, urlencode

from hmz.coganchor import AnchorConfig
from hmz.coganchor.places import MANAGED, REMOTE
from hmz.coganchor.transport import (
    REMOTE_CACHE,
    SLURM,
    Road,
    Target,
    bundled,
    python_command,
)

from .base import MachineBase, MachineConfig
from .docker import CPUS, GPUS, MEMORY, Allocation

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["SRUN", "TCP", "VIA", "Slurm", "SlurmConfig", "Unplaced", "jobs"]

#: The two ways a job's node is reached: a step of the job's own per command, by `srun`; or a
#: connection to the serving half the job itself runs, over TCP.
SRUN = "srun"
TCP = "tcp"
VIA = (SRUN, TCP)

#: Marks a job as one of ours, and whose: the label :mod:`.docker` marks a container with.
_LABEL = "humanize"

#: What the job does while the turns come and go, reached by `srun`: nothing, for as long as
#: it is let.
_IDLE = "exec sleep 2147483647"

#: The states a job has left for good, as Slurm names them -- or will have once it is out.
_OVER = frozenset(
    {
        "BOOT_FAIL",
        "CANCELLED",
        "COMPLETED",
        "COMPLETING",
        "DEADLINE",
        "FAILED",
        "NODE_FAIL",
        "OUT_OF_MEMORY",
        "PREEMPTED",
        "REVOKED",
        "SPECIAL_EXIT",
        "TIMEOUT",
    }
)

#: How often a job that has not yet started, or a serving half not yet listening, is asked
#: after.
_POLL = 1.0

#: And how long it may go between two questions at the most, once it has been waiting a while.
_POLL_MOST = 10.0

#: What `squeue` says of a job it no longer has, which is a job that has gone.
_GONE = "Invalid job id"

#: How long each question asked of the cluster may take.
_ASKING = 60.0

#: How long a job's serving half is given to be listening once the job runs and its archive
#: is on the node.
_LISTENING = 60.0

#: What `squeue` is asked to say of each job, one field apiece, and what separates them --
#: which neither a job id, a state, a reason, a comment written here nor a node can hold.
_FIELDS = "%i|%T|%r|%k|%N"

#: What the serving half says on its way up, once it is listening: the address and the port.
_LISTENING_ON = re.compile(r"hmz internal anchor serve listening \S+ (\d+)")


class Unplaced(RuntimeError):  # noqa: N818 -- named for what happened, as the rest are
    """No node of the cluster took the job in time: its message is the scheduler's reason."""


@dataclass(frozen=True, kw_only=True)
class SlurmConfig(MachineConfig):
    """What the job is submitted with, and how its node is reached once it runs.

    Attributes:
      workspace: The project directory, absolute, as every node the job may land on names
        it.
      name: What to call the job, or None for a name of its own.
      partition: The partition to submit to, or "" for the cluster's default.
      account: The account to charge, or "" for the user's default.
      qos: The quality of service, or "" for the default.
      time: How long the job may run, as `--time` takes it, or "" for the partition's
        default.
      cpus: How many CPUs it asks for, or None for the partition's default.
      memory: How many bytes of memory, or None for the default; asked in whole MiB.
      gpus: How many GPUs.
      constraint: The node features it needs, as `--constraint` takes them, or "".
      python: A Python of at least 3.12 on the job's node, for nodes whose own are older:
        absolute, or under `~/`; "" for whatever the node has.
      via: How the job's node is reached once it runs: :data:`SRUN`, a step of the job per
        command, or :data:`TCP`, a connection apiece to the serving half the job runs.
      sbatch_args: What else `sbatch` is told, ahead of what the job asks for.
      labels: Labels to write in the job's comment beside humanize's own.
      placing: How long, in seconds, the job may wait for a node before it is given up on,
        or None for as long as it waits.
    """

    workspace: str
    name: str | None = None
    partition: str = ""
    account: str = ""
    qos: str = ""
    time: str = ""
    cpus: int | None = None
    memory: int | None = None
    gpus: int = 0
    constraint: str = ""
    python: str = ""
    via: str = SRUN
    sbatch_args: tuple[str, ...] = ()
    labels: Mapping[str, str] = field(default_factory=dict[str, str], hash=False)
    placing: float | None = None

    def __post_init__(self) -> None:
        """Refuses what `sbatch` would refuse, where it is written rather than as it starts.

        Raises:
          ValueError: If the workspace or the Python is not absolute, an amount is not more
            than nothing, the node is reached some way there is not, or a label has no name.
        """
        if not self.workspace.startswith("/"):
            raise ValueError(
                f"a workspace on a Slurm cluster is a path on its nodes, so it has to be an "
                f"absolute one, not {self.workspace!r}"
            )
        if self.python and not self.python.startswith(("/", "~/")):
            raise ValueError(
                f"the Python on a node has to be absolute or under ~/, not {self.python!r}"
            )
        for what, amount in (("cpus", self.cpus), ("memory", self.memory)):
            if amount is not None and amount <= 0:
                raise ValueError(f"{what} must be more than nothing, not {amount!r}")
        if self.gpus < 0:
            raise ValueError(f"gpus cannot be negative, not {self.gpus!r}")
        if self.via not in VIA:
            raise ValueError(f"via must be one of {', '.join(VIA)}, not {self.via!r}")
        for key in self.labels:
            if not key or "=" in key:
                raise ValueError(f"unsupported name {key!r}; expected one without '='")
        object.__setattr__(self, "labels", dict(self.labels))

    @property
    def capabilities(self) -> frozenset[str]:
        """`remote`, `managed` and `linux`: a node somebody else's tools are on, held for us."""
        return frozenset({"linux", MANAGED, REMOTE}) | AnchorConfig().capabilities

    def create(self) -> Slurm:
        """Builds the machine, without submitting the job yet."""
        return Slurm(self)


def jobs(
    labels: Mapping[str, str] | None = None, *, seconds: float | None = None
) -> list[Allocation]:
    """What this user's jobs of humanize's on the cluster hold of it, waiting or running.

    Args:
      labels: Labels a job must also carry to be counted, such as its runtime's.
      seconds: How long asking may take, or None for as long as it does.

    Returns:
      One allocation per job, read off the labels it was submitted with, under its job id.

    Raises:
      OSError: If there is no `squeue` here, or it could not answer in time.
    """
    said = _asked(["squeue", "--me", "--noheader", "--format", _FIELDS], seconds)
    if said.returncode != 0:
        raise OSError(f"could not ask Slurm for its jobs: {said.stderr.strip()}")
    wanted = {_LABEL: "", **(labels or {})}
    held: list[Allocation] = []
    for line in said.stdout.splitlines():
        ident, state, _, comment, _ = (line.strip().split("|") + [""] * 5)[:5]
        found = _labels(comment)
        if not ident or state in _OVER or _LABEL not in found:
            continue
        if any(value and found.get(key) != value for key, value in wanted.items()):
            continue
        held.append(_allocation(ident, found))
    return held


def _labels(comment: str) -> dict[str, str]:
    """The labels a job's comment carries, or none where it is not one of ours."""
    try:
        return dict(parse_qsl(comment.strip(), strict_parsing=True))
    except ValueError:
        return {}


def _allocation(ident: str, said: Mapping[str, str]) -> Allocation:
    """What one job holds, as the labels it was submitted with say."""

    def number[N: (int, float)](label: str | None, kind: type[N]) -> N | None:
        try:
            return kind(label) if label is not None else None
        except ValueError:
            return None  # a comment is anybody's to write, and one written wrong counts nothing

    gpus = said.get(GPUS, "")
    return Allocation(
        name=ident,
        cpus=number(said.get(CPUS), float),
        memory=number(said.get(MEMORY), int),
        gpus=tuple(one for one in gpus.split(",") if one),
        labels=dict(said),
    )


def _asked(argv: list[str], seconds: float | None) -> subprocess.CompletedProcess[str]:
    """Runs one question for the cluster, with nothing on its stdin, for so long at most.

    Raises:
      OSError: If it could not be run, or did not answer in time.
    """
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise OSError(
            errno.ETIMEDOUT, f"{argv[0]} did not answer within {seconds:g}s"
        ) from error


class Slurm(MachineBase):
    """One job held on a cluster, and the mirror the agent works in while its turns land there.

    Attributes:
      job: The job's id once it is submitted, or "" before.
      token: The secret its serving half asks of every connection, where the node is reached
        over :data:`TCP`; None otherwise.
    """

    _config: SlurmConfig

    def __init__(self, config: SlurmConfig) -> None:
        """Initializes a machine holding no job.

        Args:
          config: The job's request, and the workspace on its node.
        """
        super().__init__(config)
        self._mirror: tempfile.TemporaryDirectory[str] | None = None
        self.job = ""
        self.token = secrets.token_urlsafe(32) if config.via == TCP else None

    def submit(self) -> str:
        """Submits the job, where it is not submitted yet, without waiting for it to run.

        Returns:
          The job's id.

        Raises:
          FileNotFoundError: If there is no `sbatch` here.
          RuntimeError: If it could not be submitted.
          OSError: If `sbatch` did not answer in time, or the serving half's archive cannot
            be built.
        """
        if self.job:
            return self.job
        config = self._config
        if shutil.which("sbatch") is None:
            raise FileNotFoundError(errno.ENOENT, "no sbatch command here", "sbatch")
        if self._mirror is None:
            self._mirror = tempfile.TemporaryDirectory(
                prefix="humanize-", ignore_cleanup_errors=True
            )
        name = config.name or Path(self._mirror.name).name
        made = _asked(
            [
                "sbatch",
                "--parsable",
                "--job-name",
                name,
                *self._output(),
                "--export",
                "HOME,USER",
                "--chdir",
                config.workspace,
                "--comment",
                self._labelled(),
                *config.sbatch_args,
                *self._asks(),
                "--wrap",
                self._script(),
            ],
            _ASKING,
        )
        job = (
            made.stdout.strip().splitlines()[-1].partition(";")[0]
            if made.stdout
            else ""
        )
        if made.returncode != 0 or not job.isdigit():
            raise RuntimeError(
                f"could not submit a job to Slurm: {made.stderr.strip() or made.stdout}"
            )
        self.job = job
        return job

    def start(self) -> AnchorConfig:
        """Submits the job where it is not yet, waits for it to run, and asks its node.

        Returns:
          The anchor that reaches it: the workspace by its path on the node, and the job by
          a target `srun` reaches it through, or its serving half's address and secret.

        Raises:
          FileNotFoundError: If there is no `sbatch` here.
          Unplaced: If no node took the job in time.
          RuntimeError: If it could not be submitted, or ended before it ran, or its serving
            half did not listen, or what came up is not the machine these settings promised.
          OSError: If the cluster could not be asked, or the node cannot serve the workspace.
        """
        config = self._config
        try:
            self.submit()
            node = self._running()
            stepped = Target.parse(
                f"{SLURM}://{self.job}"
                + (
                    f"?python={quote(config.python, safe='/~')}"
                    if config.python
                    else ""
                )
            )
            road = Road.to(stepped)
            road.forget()
            target = stepped
            if config.via == TCP:
                road.installed()
                target = Target.parse(f"tcp://{node}:{self._listening(road)}")
            assert self._mirror is not None  # noqa: S101 -- made as the job was submitted
            anchor = AnchorConfig(
                target=target.describe(),
                workspace=config.workspace,
                shadow=str(Path(self._mirror.name) / "shadow"),
                token=self.token,
            )
            self.observe(anchor)
        except BaseException:
            self.stop()
            raise
        return anchor

    def stop(self) -> None:
        """Cancels the job, and only the one it submitted, leaving the workspace as it was."""
        if self._mirror is None:
            return
        if self.job:
            with contextlib.suppress(OSError):
                _asked(["scancel", self.job], _ASKING)
            self.job = ""
        if self.token is not None:
            from hmz.coganchor.argv import forget

            forget(self.token)
        self._mirror.cleanup()
        self._mirror = None

    def _running(self) -> str:
        """Waits for the job to be running, and says on which node.

        Asked less and less often while it waits, up to :data:`_POLL_MOST` apart: a cluster's
        controller answers every run's every job, and a few dozen jobs asking each second is
        a load it may stop answering under. A question it did not answer, or answered with an
        error of its own, is asked again rather than taken for the job's end.

        Raises:
          Unplaced: If it was still waiting once :attr:`SlurmConfig.placing` was over.
          RuntimeError: If it ended, or went, before it ran.
        """
        placing = self._config.placing
        began = time.monotonic()
        state, reason, pause = "", "", _POLL
        while True:
            try:
                said = _asked(
                    ["squeue", "--noheader", "--jobs", self.job, "--format", _FIELDS],
                    _ASKING,
                )
            except OSError:
                said = None
            if said is not None and (said.returncode == 0 or _GONE in said.stderr):
                _, state, reason, _, node = [
                    *said.stdout.strip().split("|"),
                    *[""] * 5,
                ][:5]
                if state == "RUNNING":
                    return node.strip()
                if state in _OVER or not state:
                    raise RuntimeError(
                        f"job {self.job} is {state.lower() or 'gone'} before it ran"
                        + (f": {reason}" if reason and reason != "None" else "")
                    )
            if placing is not None and time.monotonic() - began > placing:
                raise Unplaced(
                    f"job {self.job} was not given a node within {placing:g}s: it is "
                    f"{state.lower() or 'waiting'} for {reason or 'no reason Slurm gave'}"
                )
            time.sleep(pause)
            pause = min(pause * 2, _POLL_MOST)

    def _listening(self, road: Road) -> int:
        """The port the job's serving half listens on, once it says it is listening.

        Raises:
          RuntimeError: If it did not say within :data:`_LISTENING`.
        """
        began = time.monotonic()
        said = ""
        while time.monotonic() - began < _LISTENING:
            ran = road.run(["/bin/cat", self._said()])
            said = ran.stdout.decode(errors="replace")
            found = _LISTENING_ON.search(said)
            if found:
                return int(found[1])
            time.sleep(_POLL)
        raise RuntimeError(
            f"job {self.job} did not say it was listening within {_LISTENING:g}s"
            + (f": {said.strip()[-400:]}" if said.strip() else "")
        )

    def _said(self) -> str:
        """Where on its node the job's batch step writes what its serving half says."""
        return f"/tmp/humanize-slurm-{self.job}.out"  # noqa: S108 -- the node's, and its own

    def _output(self) -> list[str]:
        """Where the job's batch step writes: nowhere, unless its serving half is to say."""
        if self._config.via == TCP:
            return ["--output", "/tmp/humanize-slurm-%j.out"]  # noqa: S108
        return ["--output", os.devnull]

    def _script(self) -> str:
        """What the job runs: nothing, or its serving half once its archive is on the node.

        The archive is put there by `srun` once the job runs, under a name only the archive
        built from this source has, so the job waits for that name to be there. The secret is
        set in the script rather than on a command line, which anybody on the node could read.
        """
        config = self._config
        if config.via != TCP:
            return _IDLE
        _, digest = bundled()
        archive = f"{REMOTE_CACHE}/humanize-{digest}.pyz"
        serving = python_command(
            ["internal", "anchor", "serve", "--listen", "0.0.0.0:0", "--export", "/"],
            bundle=archive,
            python=config.python,
        )
        return (
            f"HUMANIZE_TOKEN={shlex.quote(self.token or '')}; export HUMANIZE_TOKEN; "
            f'while [ ! -f "{archive}" ]; do sleep 1; done; exec {shlex.join(serving)}'
        )

    def _labelled(self) -> str:
        """The job's comment: the caller's labels, then whose it is and what it holds."""
        config = self._config
        said = {
            key: value
            for key, value in config.labels.items()
            if key not in (_LABEL, CPUS, MEMORY, GPUS)
        }
        said[_LABEL] = str(os.getuid())
        if config.cpus is not None:
            said[CPUS] = str(config.cpus)
        if config.memory is not None:
            said[MEMORY] = str(config.memory)
        if config.gpus:
            said[GPUS] = f"gpu={config.gpus}"
        return urlencode(said, quote_via=quote)

    def _asks(self) -> list[str]:
        """What the job asks of the cluster: where it goes, and what it holds there."""
        config = self._config
        said = ["--nodes", "1", "--ntasks", "1"]
        for flag, value in (
            ("--partition", config.partition),
            ("--account", config.account),
            ("--qos", config.qos),
            ("--time", config.time),
            ("--constraint", config.constraint),
        ):
            if value:
                said += [flag, value]
        if config.cpus is not None:
            said += ["--cpus-per-task", str(config.cpus)]
        if config.memory is not None:
            said += ["--mem", f"{math.ceil(config.memory / (1 << 20))}M"]
        if config.gpus:
            said += ["--gpus", str(config.gpus)]
        return said

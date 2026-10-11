"""A job of its own on a Slurm cluster, with the cluster and coganchor stood in for."""

from __future__ import annotations

import shutil
from pathlib import PurePosixPath
from typing import Any

import pytest

from hmz.coganchor import AnchorConfig, machines
from hmz.coganchor.machines import AnchoredConfig
from hmz.coganchor.machines import slurm as coganchor_slurm
from hmz.flows import (
    CPUEnvMixin,
    Env,
    EnvBackendKind,
    EnvCollection,
    EnvConnectionError,
    EnvUnavailable,
    GPUEnvMixin,
    MemoryEnvMixin,
    ResourceUnmet,
)
from hmz.runtime.flowing.declaring import EnvRole, env_roles
from hmz.runtime.flowing.environing import MachineEnvDriver, Resources
from hmz.runtime.flowing.environing_docker import HOST, PID, PROVIDER, ROLE
from hmz.runtime.flowing.environing_slurm import LOCAL, Share, SlurmMachine, shared
from tests.unit.runtime.flowing.doubles_u11 import (
    Held,
    Runtime,
    held,
    reach,
    returning,
    runtime,
)


class Worker(Env, CPUEnvMixin, MemoryEnvMixin, GPUEnvMixin):
    _cpu_count = 4
    _memory = 8 << 30
    _gpu_count = 1


class Envs(EnvCollection):
    worker: Worker


def _worker() -> EnvRole:
    (worker,) = env_roles(Envs, globals(), {})
    return worker


# ------------------------------------------------------------------------- what is shared


def test_the_clusters_defaults_hand_out_whatever_it_gives() -> None:
    share = shared(
        None, (64, 1 << 40, 8), held(Held("1", cpus=99)), where="slurm", role="r"
    )

    assert share == Share(64, 1 << 40, 8)
    assert shared(None, (0, 0, 0), held(), where="slurm", role="r") == Share(
        None, None, 0
    )


def test_a_runtime_hands_out_what_is_left_of_what_it_says() -> None:
    stored = runtime(Runtime(cpus=8, memory=16 << 30, max_jobs=3))

    share = shared(
        stored, (4, 8 << 30, 2), held(Held("1", cpus=4)), where="slurm@c", role="r"
    )

    assert share == Share(4, 8 << 30, 2)


def test_what_is_short_is_named_with_who_holds_it() -> None:
    stored = runtime(Runtime(cpus=8, memory=16 << 30, max_jobs=1))

    with pytest.raises(ResourceUnmet) as raised:
        shared(
            stored,
            (6, 12 << 30, 0),
            held(Held("1234", cpus=4, memory=8 << 30)),
            where="slurm@c",
            role="worker",
        )

    said = str(raised.value)
    assert (
        "slurm@c has 1 of the 1 jobs it may (one held by 1234, pid 42 on gpubox)"
        in said
    )
    assert "4 of 8 CPUs free, and 'worker' asks for 6" in said
    assert "8 GiB of 16 GiB of memory free" in said


# ------------------------------------------------------------------------ before it is up


def test_a_job_is_named_for_its_runtime_and_role() -> None:
    machine = SlurmMachine(
        "c", PurePosixPath("/srv/x"), stored=runtime(Runtime(name="c")), role=_worker()
    )
    default = SlurmMachine(LOCAL, PurePosixPath("/srv/x"), named="w")

    assert machine.backend is EnvBackendKind.SLURM
    assert machine.name.startswith("humanize-c-worker-")
    assert machine.identity == f"slurm:{machine.name}"
    assert machine.asked == (4, 8 << 30, 1)
    assert machine.spelled == "slurm@c"
    assert (default.spelled, default.asked) == ("slurm", (0, 0, 0))
    assert default.name.startswith("humanize-local-w-")
    assert machine.resources(gpus=True) == Resources()


def test_an_agent_on_a_job_is_anchored_to_it_in_a_mirror_with_its_secret() -> None:
    machine = SlurmMachine(LOCAL, PurePosixPath("/srv/x"))
    machine.target, machine.token = "tcp://n1:4000", "s3cret"

    placement = machine.placement(PurePosixPath("/srv/x"))

    assert (placement.backend, placement.provider) == (EnvBackendKind.SLURM, LOCAL)
    assert isinstance(placement.machine, AnchoredConfig)
    anchor = placement.machine.anchor
    assert (anchor.target, anchor.token, anchor.workspace) == (
        "tcp://n1:4000",
        "s3cret",
        "/srv/x",
    )
    assert anchor.shadow is not None


# ------------------------------------------------------------------------ bringing it up


class _Config:
    made: list[dict[str, Any]]
    stopped: int
    submitted: int
    fails: BaseException | None = None
    refused: BaseException | None = None

    def __init__(self, **said: Any) -> None:
        type(self).made.append(said)
        self.job = ""

    def create(self) -> _Config:
        return self

    def submit(self) -> str:
        if self.refused is not None:
            raise self.refused
        type(self).submitted += 1
        self.job = "77"
        return self.job

    def start(self) -> AnchorConfig:
        if self.fails is not None:
            raise self.fails
        return AnchorConfig(target="tcp://n9:4000", workspace="/srv/x", token="tok")

    def stop(self) -> None:
        type(self).stopped += 1


@pytest.fixture
def cluster(monkeypatch: pytest.MonkeyPatch) -> type[_Config]:
    """A cluster this machine submits to, running one job of 2 CPUs of the runtime's."""

    class Config(_Config):
        made: list[dict[str, Any]] = []  # noqa: RUF012 -- one list per test
        stopped = 0
        submitted = 0

    def which(name: str, *_: Any, **__: Any) -> str | None:
        return f"/usr/bin/{name}" if name == "sbatch" else None

    monkeypatch.setattr(shutil, "which", which)
    monkeypatch.setattr(coganchor_slurm, "jobs", returning([Held("5", cpus=2)]))
    monkeypatch.setattr(machines, "SlurmConfig", Config)
    reach(monkeypatch)
    return Config


async def test_a_job_is_submitted_with_its_share_and_reached_where_it_landed(
    cluster: type[_Config],
) -> None:
    stored = Runtime(
        name="c",
        cpus=8,
        partition="cpu",
        account="team",
        qos="high",
        time="4:00:00",
        constraint="a100",
        python="/opt/py",
        via="tcp",
        max_wait=600,
        run_args=("--exclusive",),
    )
    machine = SlurmMachine(
        "c", PurePosixPath("/srv/x"), stored=runtime(stored), role=_worker()
    )
    driver = MachineEnvDriver(machine, PurePosixPath("/work"))

    await driver.probe()

    (made,) = cluster.made
    assert (made["cpus"], made["memory"], made["gpus"]) == (4, 8 << 30, 1)
    assert (made["partition"], made["account"], made["qos"], made["time"]) == (
        "cpu",
        "team",
        "high",
        "4:00:00",
    )
    assert (made["constraint"], made["python"], made["via"]) == (
        "a100",
        "/opt/py",
        "tcp",
    )
    assert (made["sbatch_args"], made["placing"]) == (("--exclusive",), 600.0)
    assert (made["labels"][PROVIDER], made["labels"][ROLE]) == ("c", "worker")
    assert {HOST, PID} <= set(made["labels"])
    assert cluster.submitted == 1
    assert (machine.target, machine.token) == ("tcp://n9:4000", "tok")
    assert machine.resources(gpus=True) == Resources(4, 8 << 30, 1, 16384 << 20)
    assert driver.available

    await driver.close()
    assert cluster.stopped == 1


async def test_the_clusters_defaults_ask_for_nothing_but_the_role(
    cluster: type[_Config],
) -> None:
    await SlurmMachine(LOCAL, PurePosixPath("/x")).probe()

    (made,) = cluster.made
    assert (made["partition"], made["via"], made["placing"]) == ("", "srun", None)
    assert (made["cpus"], made["memory"], made["gpus"]) == (None, None, 0)


async def test_a_job_left_by_a_run_that_is_gone_is_cancelled(
    cluster: type[_Config], monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    import socket

    gone = Held(
        "13",
        cpus=4,
        labels={
            "humanize": str(os.getuid()),
            HOST: socket.gethostname(),
            PID: "999999999",
        },
    )
    monkeypatch.setattr(coganchor_slurm, "jobs", returning([gone]))
    cancelled: list[list[str]] = []

    def run(argv: list[str], **_: Any) -> Any:
        cancelled.append(argv)

    import subprocess

    monkeypatch.setattr(subprocess, "run", run)
    stored = runtime(Runtime(name="c", max_jobs=1))

    await SlurmMachine("c", PurePosixPath("/x"), stored=stored).probe()

    assert cancelled == [["scancel", "13"]]
    assert cluster.submitted == 1


async def test_a_job_no_node_took_is_a_resource_unmet(cluster: type[_Config]) -> None:
    cluster.fails = coganchor_slurm.Unplaced("pending for Resources")

    with pytest.raises(ResourceUnmet, match="slurm: pending for Resources"):
        await SlurmMachine(LOCAL, PurePosixPath("/x")).probe()


@pytest.mark.parametrize(
    ("refused", "fails", "kind"),
    [
        (RuntimeError("Invalid account"), None, EnvUnavailable),
        (OSError("sbatch did not answer"), None, EnvConnectionError),
        (None, RuntimeError("job 77 is failed before it ran"), EnvUnavailable),
        (None, OSError("node unreachable"), EnvConnectionError),
    ],
    ids=["refused", "silent", "failed", "gone"],
)
async def test_a_job_that_would_not_run_says_why(
    cluster: type[_Config],
    refused: BaseException | None,
    fails: BaseException | None,
    kind: type[Exception],
) -> None:
    cluster.refused, cluster.fails = refused, fails

    with pytest.raises(kind):
        await SlurmMachine(LOCAL, PurePosixPath("/x")).probe()


async def test_no_sbatch_here_is_unavailable(
    cluster: type[_Config], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", returning(None))

    with pytest.raises(EnvUnavailable, match="sbatch was not found"):
        await SlurmMachine(LOCAL, PurePosixPath("/x")).probe()
    assert cluster.made == []


async def test_a_cluster_that_cannot_be_asked_is_a_connection_error(
    cluster: type[_Config], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(*_: Any, **__: Any) -> Any:
        raise OSError("slurm_load_jobs error")

    monkeypatch.setattr(coganchor_slurm, "jobs", refused)

    with pytest.raises(EnvConnectionError, match="slurm_load_jobs"):
        await SlurmMachine(LOCAL, PurePosixPath("/x")).probe()
    assert cluster.made == []

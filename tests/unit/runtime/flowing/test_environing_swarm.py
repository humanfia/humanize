"""A task of its own on a docker swarm, with the swarm and coganchor stood in for."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import pytest

from hmz.coganchor import machines
from hmz.coganchor.machines import AnchoredConfig, store
from hmz.coganchor.machines import swarm as coganchor_swarm
from hmz.coganchor.transport import Endpoint
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
from hmz.runtime.flowing.environing_docker import IMAGE, PROVIDER, ROLE
from hmz.runtime.flowing.environing_swarm import LOCAL, Share, SwarmMachine, shared
from tests.unit.runtime.flowing.doubles_u11 import (
    Held,
    Runtime,
    held,
    reach,
    returning,
    runtime,
    same_path,
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


def test_the_swarm_here_hands_out_whatever_its_nodes_have_room_for() -> None:
    share = shared(
        None, (64, 1 << 40, 0), held(Held("x", cpus=99)), where="swarm", role="r"
    )

    assert share == Share(64.0, 1 << 40, 0)
    assert shared(None, (0, 0, 0), held(), where="swarm", role="r") == Share(
        None, None, 0
    )


def test_a_runtime_hands_out_what_is_left_of_what_it_says() -> None:
    stored = runtime(
        Runtime(cpus=8, memory=16 << 30, max_tasks=3, gpu_resource="NVIDIA-GPU")
    )

    share = shared(
        stored, (4, 8 << 30, 2), held(Held("x", cpus=4)), where="swarm@c", role="r"
    )

    assert share == Share(4.0, 8 << 30, 2)


def test_what_is_short_is_named_with_who_holds_it() -> None:
    stored = runtime(Runtime(cpus=8, memory=16 << 30, max_tasks=1))

    with pytest.raises(ResourceUnmet) as raised:
        shared(
            stored,
            (6, 12 << 30, 1),
            held(Held("hog", cpus=4, memory=8 << 30)),
            where="swarm@c",
            role="worker",
        )

    said = str(raised.value)
    assert (
        "swarm@c runs 1 of the 1 tasks it may (one held by hog, pid 42 on gpubox)"
        in said
    )
    assert "4 of 8 CPUs free, and 'worker' asks for 6" in said
    assert "8 GiB of 16 GiB of memory free" in said
    assert "hands out no GPUs, and 'worker' asks for 1" in said


def test_the_swarm_here_hands_out_no_gpus() -> None:
    with pytest.raises(ResourceUnmet, match="gpu_resource"):
        shared(None, (0, 0, 1), held(), where="swarm", role="r")


# ------------------------------------------------------------------------ before it is up


def test_a_task_is_named_for_its_runtime_and_role() -> None:
    stored = runtime(
        Runtime(name="c", endpoint="tcp://manager:2376", image="debian:13")
    )

    machine = SwarmMachine("c", PurePosixPath("/srv/x"), stored=stored, role=_worker())
    default = SwarmMachine(LOCAL, PurePosixPath("/srv/x"), named="w")

    assert machine.backend is EnvBackendKind.SWARM
    assert machine.name.startswith("humanize-c-worker-")
    assert machine.endpoint == Endpoint(host="tcp://manager:2376")
    assert machine.identity == f"swarm:{machine.name}@tcp://manager:2376"
    assert machine.asked == (4, 8 << 30, 1)
    assert (machine.image, machine.spelled) == ("debian:13", "swarm@c")
    assert (default.image, default.spelled, default.asked) == (
        IMAGE,
        "swarm",
        (0, 0, 0),
    )
    assert default.name.startswith("humanize-local-w-")
    assert machine.resources(gpus=True) == Resources()


def test_a_runtime_whose_manager_cannot_be_reached_as_written_is_unavailable() -> None:
    with pytest.raises(EnvUnavailable, match="swarm@c"):
        SwarmMachine(
            "c", PurePosixPath("/x"), stored=runtime(Runtime(endpoint="broken"))
        )


def test_an_agent_in_a_task_is_anchored_to_its_container_in_a_mirror() -> None:
    machine = SwarmMachine(LOCAL, PurePosixPath("/srv/x"))

    placement = machine.placement(PurePosixPath("/srv/x"))

    assert (placement.backend, placement.provider) == (EnvBackendKind.SWARM, LOCAL)
    assert isinstance(placement.machine, AnchoredConfig)
    assert placement.machine.anchor.workspace == "/srv/x"
    assert placement.machine.anchor.shadow is not None


# ------------------------------------------------------------------------ bringing it up


@dataclass(frozen=True)
class _Placed:
    container: str
    daemon: str


class _Config:
    made: list[dict[str, Any]]
    stopped: int
    fails: BaseException | None = None

    def __init__(self, **said: Any) -> None:
        type(self).made.append(said)
        self.placed: _Placed | None = None

    def create(self) -> _Config:
        return self

    def start(self) -> None:
        if self.fails is not None:
            raise self.fails
        self.placed = _Placed("task.1.abc", "ssh://node-2")

    def stop(self) -> None:
        type(self).stopped += 1


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> type[_Config]:
    """A swarm manager running one service of 2 CPUs."""

    class Config(_Config):
        made: list[dict[str, Any]] = []  # noqa: RUF012 -- one list per test
        stopped = 0

    def which(name: str, *_: Any, **__: Any) -> str | None:
        return f"/usr/bin/{name}" if name == "docker" else None

    monkeypatch.setattr(shutil, "which", which)
    monkeypatch.setattr(machines, "info", returning({"Swarm": {}}))
    monkeypatch.setattr(coganchor_swarm, "swarm_of", returning("node-1"))
    monkeypatch.setattr(
        coganchor_swarm,
        "services",
        returning([Held("other", cpus=2)]),
    )
    monkeypatch.setattr(machines, "SwarmConfig", Config)
    monkeypatch.setattr(store, "node_of", same_path)

    def daemon_of(via: str) -> Endpoint:
        return Endpoint.parse(f"tcp://{via}:2376")

    monkeypatch.setattr(store, "daemon_of", daemon_of)
    reach(monkeypatch)
    return Config


async def test_a_task_is_created_with_its_share_and_reached_where_it_landed(
    manager: type[_Config],
) -> None:
    stored = Runtime(
        name="c",
        cpus=8,
        gpu_resource="NVIDIA-GPU",
        constraints=("node.labels.gpu==1",),
        nodes={"node-2": "node-2.lan"},
        run_args=("--init",),
    )
    machine = SwarmMachine(
        "c",
        PurePosixPath("/srv/x"),
        stored=runtime(stored),
        role=_worker(),
        traced=True,
    )
    driver = MachineEnvDriver(machine, PurePosixPath("/work"))

    await driver.probe()

    (made,) = manager.made
    assert (made["cpus"], made["memory"], made["generic"]) == (
        4.0,
        8 << 30,
        (("NVIDIA-GPU", 1),),
    )
    assert made["constraints"] == ("node.labels.gpu==1",)
    assert made["nodes"] == {"node-2": "tcp://node-2.lan:2376"}
    assert (made["traced"], made["run_args"]) == (True, ("--init",))
    assert (made["labels"][PROVIDER], made["labels"][ROLE]) == ("c", "worker")
    assert machine.target.startswith("docker://task.1.abc@")
    assert machine.resources(gpus=True) == Resources(4, 8 << 30, 1, 16384 << 20)
    assert driver.available

    await driver.close()
    assert manager.stopped == 1


async def test_a_task_no_node_took_is_a_resource_unmet(manager: type[_Config]) -> None:
    manager.fails = coganchor_swarm.Unplaced(
        "no suitable node (insufficient resources)"
    )

    with pytest.raises(ResourceUnmet, match="swarm: no suitable node"):
        await SwarmMachine(LOCAL, PurePosixPath("/x")).probe()


@pytest.mark.parametrize(
    ("fails", "kind"),
    [
        (FileNotFoundError(2, "No such file", "docker"), EnvUnavailable),
        (RuntimeError("image not found"), EnvUnavailable),
        (OSError("node unreachable"), EnvConnectionError),
    ],
    ids=["no-program", "refused", "gone"],
)
async def test_a_task_that_would_not_run_says_why(
    manager: type[_Config], fails: BaseException, kind: type[Exception]
) -> None:
    manager.fails = fails

    with pytest.raises(kind):
        await SwarmMachine(LOCAL, PurePosixPath("/x")).probe()


async def test_a_manager_that_manages_no_swarm_is_unavailable(
    manager: type[_Config], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(told: Any, where: str) -> str:
        raise OSError(f"{where} manages no swarm")

    monkeypatch.setattr(coganchor_swarm, "swarm_of", refused)

    with pytest.raises(EnvUnavailable, match="manages no swarm"):
        await SwarmMachine(LOCAL, PurePosixPath("/x")).probe()
    assert manager.made == []


async def test_a_node_the_runtime_cannot_say_how_to_reach_is_unavailable(
    manager: type[_Config], monkeypatch: pytest.MonkeyPatch
) -> None:
    def nowhere(via: str) -> str:
        raise ValueError("names nothing")

    monkeypatch.setattr(store, "node_of", nowhere)
    stored = runtime(Runtime(name="c", nodes={"n": "?"}))

    with pytest.raises(EnvUnavailable, match="node n: names nothing"):
        await SwarmMachine("c", PurePosixPath("/x"), stored=stored).probe()

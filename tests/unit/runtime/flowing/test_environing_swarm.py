"""A task of its own on a docker swarm, with the swarm and coganchor stood in for."""

from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import pytest

from hmz import machine as machine_dir
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
from hmz.runtime.flowing.environing_docker import HOST, IMAGE, PID, PROVIDER, ROLE
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


def test_a_runtime_naming_a_prefix_names_its_services_after_it() -> None:
    stored = runtime(
        Runtime(name="c", endpoint="tcp://manager:2376", name_prefix="team-a")
    )

    machine = SwarmMachine("c", PurePosixPath("/srv/x"), stored=stored, role=_worker())

    assert re.fullmatch(r"team-a-worker-[0-9a-f]{8}", machine.name)
    assert machine.identity == f"swarm:{machine.name}@tcp://manager:2376"
    assert machine.target.startswith(f"docker://{machine.name}@")
    there = machine.placement(PurePosixPath("/srv/x")).machine
    assert isinstance(there, AnchoredConfig)
    assert there.anchor.shadow is not None
    assert f"/mirrors/{machine.name}/" in there.anchor.shadow


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


def _free(provider: str) -> bool:
    """Whether the runtime is free for another run to ask it now: its lock is not held."""
    with (machine_dir() / f".swarm.{provider}.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(lock, fcntl.LOCK_UN)
        return True


class _Config:
    made: list[dict[str, Any]]
    stopped: int
    fails: BaseException | None = None
    refuses: BaseException | None = None
    #: What was done, and whether the runtime was free for another run as it was.
    done: list[tuple[str, bool]]

    def __init__(self, **said: Any) -> None:
        type(self).made.append(said)
        self.placed: _Placed | None = None
        self.provider = said["labels"][PROVIDER]

    def create(self) -> _Config:
        return self

    def submit(self) -> str:
        type(self).done.append(("submit", _free(self.provider)))
        if self.refuses is not None:
            raise self.refuses
        return "svc"

    def start(self) -> None:
        type(self).done.append(("start", _free(self.provider)))
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
        done: list[tuple[str, bool]] = []  # noqa: RUF012 -- one list per test

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


async def test_a_service_is_created_under_the_name_its_runtime_prefixes(
    manager: type[_Config],
) -> None:
    stored = runtime(Runtime(name="c", name_prefix="team-a"))
    machine = SwarmMachine("c", PurePosixPath("/srv/x"), stored=stored, named="w")

    await machine.probe()

    (made,) = manager.made
    assert made["name"] == machine.name
    assert re.fullmatch(r"team-a-w-[0-9a-f]{8}", made["name"])
    await machine.close()


async def test_a_task_is_waited_for_with_its_runtime_let_go_of(
    manager: type[_Config],
) -> None:
    machine = SwarmMachine(LOCAL, PurePosixPath("/x"))

    await machine.probe()

    assert manager.done == [("submit", False), ("start", True)]
    await machine.close()


async def test_a_service_that_would_not_be_created_is_never_waited_for(
    manager: type[_Config],
) -> None:
    manager.refuses = RuntimeError("could not create a service of img")

    with pytest.raises(EnvUnavailable, match="swarm: could not create a service"):
        await SwarmMachine(LOCAL, PurePosixPath("/x")).probe()
    assert manager.done == [("submit", False)]


@pytest.mark.parametrize(
    ("host", "removed"),
    [("", True), ("elsewhere", False)],
    ids=["ours", "another-host"],
)
async def test_a_manager_that_does_not_create_in_time_is_given_up_on_and_its_make_undone(
    manager: type[_Config],
    monkeypatch: pytest.MonkeyPatch,
    host: str,
    removed: bool,
) -> None:
    manager.refuses = TimeoutError(errno.ETIMEDOUT, "docker did not answer within 600s")
    machine = SwarmMachine(LOCAL, PurePosixPath("/x"))
    labels = {
        "humanize": str(os.getuid()),
        HOST: host or socket.gethostname(),
        PID: str(os.getpid()),
    }
    found = [{"ID": "svc-1", "Spec": {"Name": machine.name, "Labels": labels}}]
    calls: list[list[str]] = []

    def run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append([str(one) for one in argv])
        out = json.dumps(found) if "inspect" in argv else ""
        return subprocess.CompletedProcess(argv, 0, out, "")

    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(
        EnvConnectionError, match=r"could not connect to swarm: .*within 600s"
    ):
        await machine.probe()

    assert calls[0][-3:] == ["service", "inspect", machine.name]
    assert [one[-3:] for one in calls[1:]] == (
        [["service", "rm", "svc-1"]] if removed else []
    )
    assert manager.done == [("submit", False)]


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

"""A container of its own on a docker daemon, with docker and coganchor stood in for."""

from __future__ import annotations

import shutil
from pathlib import PurePosixPath
from typing import Any

import pytest

from hmz.coganchor import machines
from hmz.coganchor.machines import AnchoredConfig, docker
from hmz.coganchor.transport import Endpoint
from hmz.flows import (
    CPUEnvMixin,
    Env,
    EnvBackendKind,
    EnvCollection,
    EnvConnectionError,
    EnvError,
    EnvUnavailable,
    GPUEnvMixin,
    ImageEnvMixin,
    MemoryEnvMixin,
    ResourceUnmet,
    ShellEnvMixin,
)
from hmz.runtime.flowing.declaring import EnvRole, env_roles
from hmz.runtime.flowing.environing import MachineEnvDriver, Resources
from hmz.runtime.flowing.environing_docker import (
    HOST,
    IMAGE,
    LOCAL,
    PID,
    PROVIDER,
    ROLE,
    TRACING,
    Asked,
    DockerMachine,
    Has,
    Share,
    has_of,
    shared,
)
from tests.unit.runtime.flowing.doubles_u11 import (
    Held,
    Runtime,
    held,
    reach,
    returning,
    runtime,
)


class Trainer(
    Env, ShellEnvMixin, CPUEnvMixin, MemoryEnvMixin, GPUEnvMixin, ImageEnvMixin
):
    _image = "nvcr.io/nvidia/pytorch:25.01-py3"
    _cpu_count = 8
    _memory = 32 << 30
    _gpu_count = 2
    _gpu_memory = 40 << 30


class Plain(Env, ShellEnvMixin): ...


class Envs(EnvCollection):
    trainer: Trainer
    plain: Plain


def _roles() -> tuple[EnvRole, EnvRole]:
    trainer, plain = env_roles(Envs, globals(), {})
    return trainer, plain


BOX = Has(cpus=16, memory=64 << 30, gpus=("0", "1", "2", "3"))


# --------------------------------------------------------------------------- what is had


def _listing(devices: Any, kind: str = "") -> tuple[str, ...]:
    return tuple(str(one) for one in devices)


@pytest.fixture
def listed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Has a daemon's devices be the GPUs it lists, by name."""
    monkeypatch.setattr(docker, "gpus_listed", _listing)


def test_docker_here_may_hand_out_all_its_daemon_has(listed: None) -> None:
    has = has_of(
        None, {"NCPU": 8, "MemTotal": 1 << 30, "DiscoveredDevices": ["0", "1"]}
    )

    assert has == Has(8.0, 1 << 30, ("0", "1"))
    assert has.bound == 2


def test_a_runtime_hands_out_what_it_says_and_its_daemons_for_what_is_zero(
    listed: None,
) -> None:
    stored = Runtime(cpus=4, gpus=("1",), gpu_memory=1 << 34, max_containers=3)

    has = has_of(
        runtime(stored), {"NCPU": 8, "MemTotal": 1 << 30, "DiscoveredDevices": []}
    )

    assert has == Has(4, 1 << 30, ("1",), 1 << 34, 3)


def test_only_a_gpu_that_answers_is_handed_out_by_the_name_it_answered_under(
    listed: None,
) -> None:
    info = {"NCPU": 8, "MemTotal": 1, "DiscoveredDevices": ["0", "1", "2"]}
    usable = [("0", "GPU-a"), ("2", "GPU-c")]

    has = has_of(None, info, usable)

    assert has.gpus == ("0", "2")
    assert has.bound == 3, "the one that does not answer is still listed"
    assert dict(has.known) == {"0": "0", "GPU-a": "0", "2": "2", "GPU-c": "2"}


def test_a_daemon_listing_no_gpu_hands_out_those_that_answer_by_uuid(
    listed: None,
) -> None:
    has = has_of(None, {"DiscoveredDevices": []}, [("0", "GPU-a")])

    assert has.gpus == ("GPU-a",)
    assert has.known["0"] == "GPU-a"


# ------------------------------------------------------------------------- what is shared


def test_a_share_is_exactly_what_was_asked_and_the_first_gpus_nobody_holds() -> None:
    share = shared(
        Asked(cpus=2, memory=1 << 30, gpus=2),
        BOX,
        held(Held("other", cpus=4, gpus=("0",)), Held("all-of-it", gpus=("2",))),
        where="docker@box",
        role="trainer",
    )

    assert share == Share(2.0, 1 << 30, ("1", "3"))


def test_a_role_asking_nothing_is_given_no_limit_and_no_gpu() -> None:
    assert shared(Asked(), BOX, held(), where="docker", role="x") == Share(
        None, None, ()
    )


def test_what_is_short_is_named_with_who_holds_it() -> None:
    with pytest.raises(ResourceUnmet) as raised:
        shared(
            Asked(cpus=10, memory=60 << 30, gpus=4),
            BOX,
            held(Held("hog", cpus=8, memory=8 << 30, gpus=("0",))),
            where="docker@box",
            role="trainer",
        )

    said = str(raised.value)
    assert "docker@box has 8 of 16 CPUs free, and 'trainer' asks for 10" in said
    assert "56 GiB of 64 GiB of memory free" in said
    assert "3 of 4 GPUs free" in said
    assert "held by hog, pid 42 on gpubox" in said


def test_a_container_holding_every_gpu_leaves_none() -> None:
    with pytest.raises(ResourceUnmet, match="0 of 4 GPUs free"):
        shared(
            Asked(gpus=1), BOX, held(Held("x", gpus="all")), where="docker", role="r"
        )


def test_a_gpu_held_by_another_of_its_names_is_held() -> None:
    has = Has(16, 1 << 30, ("0", "1"), known={"GPU-a": "0"})

    share = shared(
        Asked(gpus=1), has, held(Held("x", gpus=("GPU-a",))), where="d", role="r"
    )

    assert share.gpus == ("1",)


def test_no_more_containers_than_the_runtime_may_run() -> None:
    has = Has(16, 1 << 30, (), containers=1)

    with pytest.raises(ResourceUnmet, match="runs 1 of the 1 containers it may"):
        shared(Asked(), has, held(Held("x")), where="docker@box", role="r")


def test_gpus_too_small_for_the_role_are_refused_where_their_size_is_known() -> None:
    small = Has(16, 1 << 30, ("0",), gpu_memory=8 << 30)
    unknown = Has(16, 1 << 30, ("0",))
    asked = Asked(gpus=1, gpu_memory=16 << 30)

    with pytest.raises(ResourceUnmet, match="have 8 GiB each"):
        shared(asked, small, held(), where="d", role="r")
    assert shared(asked, unknown, held(), where="d", role="r").gpus == ("0",)


@pytest.mark.parametrize(
    ("has", "why"),
    [
        (
            Has(1, 1, ("0",), listed=3),
            "1 of the 3 GPUs it lists are usable: 2 are bound",
        ),
        (Has(1, 1, (), listed=0), "no GPU of its host answers"),
        (Has(1, 1, ()), "its daemon lists no GPU by name"),
    ],
    ids=["some-do-not-answer", "none-answers", "none-listed"],
)
def test_too_few_gpus_say_why_there_are_so_few(has: Has, why: str) -> None:
    with pytest.raises(ResourceUnmet, match=why):
        shared(Asked(gpus=2), has, held(), where="d", role="r")


# ------------------------------------------------------------------------ before it is up


def test_a_container_is_named_for_its_runtime_and_role_and_started_from_its_image() -> (
    None
):
    trainer, plain = _roles()
    stored = Runtime(name="gpubox", endpoint="ssh://me@gpubox:2222", image="debian:13")
    workdir = PurePosixPath("/srv/x")

    machine = DockerMachine("gpubox", workdir, stored=runtime(stored), role=trainer)
    bare = DockerMachine("gpubox", workdir, stored=runtime(stored), role=plain)
    default = DockerMachine(LOCAL, workdir, named="box")

    assert machine.image == "nvcr.io/nvidia/pytorch:25.01-py3"
    assert machine.asked == Asked(8, 32 << 30, 2, 40 << 30)
    assert machine.endpoint == Endpoint(host="ssh://me@gpubox:2222")
    assert machine.name.startswith("humanize-gpubox-trainer-")
    assert machine.spelled == "docker@gpubox"
    assert machine.identity == machine.target
    assert machine.target.startswith(f"docker://{machine.name}@")
    assert bare.image == "debian:13"
    assert (default.image, default.asked, default.spelled) == (IMAGE, Asked(), "docker")
    assert default.name.startswith("humanize-local-box-")
    assert machine.name != DockerMachine("gpubox", workdir, role=trainer).name
    assert machine.resources(gpus=True) == Resources()


def test_a_runtime_whose_daemon_cannot_be_reached_as_written_is_unavailable() -> None:
    with pytest.raises(EnvUnavailable, match="docker@box"):
        DockerMachine(
            "box", PurePosixPath("/x"), stored=runtime(Runtime(endpoint="broken"))
        )


def test_an_agent_in_a_container_is_anchored_to_it_in_a_mirror_of_its_own() -> None:
    machine = DockerMachine(LOCAL, PurePosixPath("/srv/x"), named="box")
    driver = MachineEnvDriver(machine, PurePosixPath("/srv/x"))

    placement = driver.placement()

    assert (placement.backend, placement.provider, placement.workdir) == (
        EnvBackendKind.DOCKER,
        LOCAL,
        PurePosixPath("/srv/x"),
    )
    assert isinstance(placement.machine, AnchoredConfig)
    anchor = placement.machine.anchor
    assert anchor.target == machine.target
    assert anchor.workspace == "/srv/x"
    assert anchor.shadow is not None
    assert not anchor.shadow.startswith("/srv/x")
    assert driver.placement() == placement
    other = machine.placement(PurePosixPath("/srv/y")).machine
    assert isinstance(other, AnchoredConfig)
    assert other.anchor.shadow != anchor.shadow


# ------------------------------------------------------------------------ bringing it up


class _Config:
    """docker's container, as coganchor would be told to bring one up."""

    made: list[dict[str, Any]]
    started: int
    stopped: int
    fails: BaseException | None = None

    def __init__(self, **said: Any) -> None:
        type(self).made.append(said)

    def create(self) -> _Config:
        return self

    def start(self) -> None:
        if self.fails is not None:
            raise self.fails
        type(self).started += 1

    def stop(self) -> None:
        type(self).stopped += 1


@pytest.fixture
def daemon(monkeypatch: pytest.MonkeyPatch) -> type[_Config]:
    """A docker daemon with 16 CPUs, 64 GiB and four GPUs, running one container of 4 CPUs."""

    class Config(_Config):
        made: list[dict[str, Any]] = []  # noqa: RUF012 -- one list per test
        started = 0
        stopped = 0

    def which(name: str, *_: Any, **__: Any) -> str | None:
        return f"/usr/bin/{name}" if name == "docker" else None

    def info(endpoint: str, seconds: float) -> dict[str, Any]:
        return {
            "NCPU": 16,
            "MemTotal": 64 << 30,
            "DiscoveredDevices": ["0", "1", "2", "3"],
        }

    def allocations(endpoint: str, labels: Any, *, seconds: float) -> list[Held]:
        return [Held("other", cpus=4)]

    def usable(endpoint: str, image: str, devices: Any, *, seconds: float) -> Any:
        return tuple((one, f"GPU-{one}") for one in devices)

    monkeypatch.setattr(shutil, "which", which)
    monkeypatch.setattr(machines, "info", info)
    monkeypatch.setattr(machines, "allocations", allocations)
    monkeypatch.setattr(machines, "gpus_usable", usable)
    monkeypatch.setattr(machines, "DockerConfig", Config)
    monkeypatch.setattr(docker, "gpus_listed", _listing)
    reach(monkeypatch)
    return Config


async def test_a_container_is_brought_up_with_its_share_and_labelled_with_it(
    daemon: type[_Config],
) -> None:
    trainer, _ = _roles()
    stored = Runtime(name="gpubox", runtime="nvidia", run_args=("--shm-size", "1g"))
    machine = DockerMachine(
        "gpubox", PurePosixPath("/srv/x"), stored=runtime(stored), role=trainer
    )
    driver = MachineEnvDriver(machine, PurePosixPath("/work"))

    await driver.probe()
    await driver.probe()

    (made,) = daemon.made
    assert made["image"] == trainer.image
    assert (made["cpus"], made["memory"], made["gpus"]) == (8.0, 32 << 30, ("0", "1"))
    assert (made["workspace"], made["name"], made["runtime"]) == (
        "/srv/x",
        machine.name,
        "nvidia",
    )
    assert made["run_args"] == ("--shm-size", "1g")
    assert made["labels"][PROVIDER] == "gpubox"
    assert made["labels"][ROLE] == "trainer"
    assert {HOST, PID} <= set(made["labels"])
    assert daemon.started == 1
    assert (driver.cpu_count, driver.memory, driver.gpu_count) == (8, 32 << 30, 2)
    assert driver.available


async def test_a_container_given_no_limit_has_what_it_sees(
    daemon: type[_Config],
) -> None:
    machine = DockerMachine(LOCAL, PurePosixPath("/srv/x"), named="box")

    await machine.probe()

    assert daemon.made[0]["cpus"] is None
    assert machine.resources(gpus=True) == Resources(16, 1 << 30, 0, 0)


async def test_a_container_holding_a_harness_may_borrow_its_agents_descriptors(
    daemon: type[_Config],
) -> None:
    stored = runtime(Runtime(run_args=("--shm-size", "1g")))

    await DockerMachine("box", PurePosixPath("/x"), stored=stored, traced=True).probe()
    await DockerMachine("box", PurePosixPath("/x"), stored=stored).probe()

    assert [one["run_args"] for one in daemon.made] == [
        (*TRACING, "--shm-size", "1g"),
        ("--shm-size", "1g"),
    ]


async def test_a_role_asking_more_than_is_left_is_refused_and_starts_nothing(
    daemon: type[_Config],
) -> None:
    trainer, _ = _roles()
    small = runtime(Runtime(cpus=10))
    machine = DockerMachine("box", PurePosixPath("/x"), stored=small, role=trainer)

    with pytest.raises(ResourceUnmet, match="6 of 10 CPUs free"):
        await machine.probe()
    assert daemon.made == []


async def test_no_docker_here_is_said_before_anything_is_asked(
    daemon: type[_Config], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", returning(None))

    with pytest.raises(EnvUnavailable, match="docker was not found"):
        await DockerMachine(LOCAL, PurePosixPath("/x")).probe()


@pytest.mark.parametrize(
    ("fails", "kind"),
    [
        (FileNotFoundError(2, "No such file", "docker"), EnvUnavailable),
        (RuntimeError("no such image"), EnvUnavailable),
        (OSError("daemon gone"), EnvConnectionError),
    ],
    ids=["no-program", "refused", "gone"],
)
async def test_a_container_that_would_not_start_says_why(
    daemon: type[_Config], fails: BaseException, kind: type[Exception]
) -> None:
    daemon.fails = fails

    with pytest.raises(kind):
        await DockerMachine(LOCAL, PurePosixPath("/x")).probe()


async def test_a_daemon_that_cannot_be_asked_is_a_connection_error(
    daemon: type[_Config], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(*_: Any, **__: Any) -> Any:
        raise OSError("connection refused")

    monkeypatch.setattr(machines, "info", refused)

    with pytest.raises(EnvConnectionError, match="could not connect to docker"):
        await DockerMachine(LOCAL, PurePosixPath("/x")).probe()


async def test_closing_takes_the_container_down_and_nothing_brings_it_up_again(
    daemon: type[_Config],
) -> None:
    driver = MachineEnvDriver(
        DockerMachine(LOCAL, PurePosixPath("/x")), PurePosixPath("/work")
    )
    await driver.probe()

    await driver.close()

    assert daemon.stopped == 1
    assert not driver.available
    with pytest.raises(EnvError, match="closed"):
        await driver.probe()
    with pytest.raises(EnvError, match="closed"):
        await driver.exec(["true"], timeout=0)
    assert len(daemon.made) == 1

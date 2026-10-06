"""An Apple container of its own on this Mac, with `container` and coganchor stood in for."""

from __future__ import annotations

import shutil
from pathlib import PurePosixPath
from typing import Any

import pytest

from hmz.coganchor import machines
from hmz.coganchor.machines import AnchoredConfig
from hmz.coganchor.machines import apple_container as coganchor_apple
from hmz.flows import (
    CPUEnvMixin,
    Env,
    EnvBackendKind,
    EnvCollection,
    EnvConnectionError,
    EnvUnavailable,
    GPUEnvMixin,
    ImageEnvMixin,
    MemoryEnvMixin,
    ResourceUnmet,
)
from hmz.runtime.flowing.declaring import EnvRole, env_roles
from hmz.runtime.flowing.environing import MachineEnvDriver, Resources
from hmz.runtime.flowing.environing_apple_container import LOCAL, AppleContainerMachine
from hmz.runtime.flowing.environing_docker import IMAGE, PROVIDER, ROLE, TRACING, Asked
from tests.unit.runtime.flowing.doubles_u11 import (
    Held,
    Runtime,
    reach,
    returning,
    runtime,
)


class Builder(Env, CPUEnvMixin, MemoryEnvMixin, ImageEnvMixin):
    _image = "debian:13"
    _cpu_count = 3
    _memory = 4 << 30


class Trainer(Env, GPUEnvMixin):
    _gpu_count = 1


class Envs(EnvCollection):
    builder: Builder
    trainer: Trainer


def _roles() -> tuple[EnvRole, EnvRole]:
    builder, trainer = env_roles(Envs, globals(), {})
    return builder, trainer


WORK = PurePosixPath("/Users/me/repo")


# ------------------------------------------------------------------------ before it is up


def test_a_container_is_named_for_its_runtime_and_role_and_started_from_its_image() -> (
    None
):
    builder, _ = _roles()
    stored = runtime(Runtime(name="mac", image="alpine:3"))

    machine = AppleContainerMachine("mac", WORK, stored=stored, role=builder)
    bare = AppleContainerMachine("mac", WORK, stored=stored, named="plain")
    default = AppleContainerMachine(LOCAL, WORK)

    assert machine.backend is EnvBackendKind.APPLE_CONTAINER
    assert machine.name.startswith("humanize-mac-builder-")
    assert machine.identity == machine.target
    assert (machine.image, machine.asked) == ("debian:13", Asked(3, 4 << 30))
    assert machine.spelled == "apple-container@mac"
    assert bare.image == "alpine:3"
    assert (default.image, default.spelled, default.asked) == (
        IMAGE,
        "apple-container",
        Asked(),
    )
    assert machine.resources(gpus=True) == Resources()


def test_an_agent_in_a_container_is_anchored_to_it_in_a_mirror_of_its_own() -> None:
    machine = AppleContainerMachine(LOCAL, WORK, named="box")

    placement = machine.placement(WORK)

    assert (placement.backend, placement.provider, placement.workdir) == (
        EnvBackendKind.APPLE_CONTAINER,
        LOCAL,
        WORK,
    )
    assert isinstance(placement.machine, AnchoredConfig)
    assert placement.machine.anchor.target == machine.target
    assert placement.machine.anchor.workspace == str(WORK)
    assert placement.machine.anchor.shadow is not None


# ------------------------------------------------------------------------ bringing it up


class _Config:
    made: list[dict[str, Any]]
    stopped: int
    fails: BaseException | None = None

    def __init__(self, **said: Any) -> None:
        type(self).made.append(said)

    def create(self) -> _Config:
        return self

    def start(self) -> None:
        if self.fails is not None:
            raise self.fails

    def stop(self) -> None:
        type(self).stopped += 1


@pytest.fixture
def mac(monkeypatch: pytest.MonkeyPatch) -> type[_Config]:
    """A Mac with 10 CPUs and 32 GiB for its containers, running one of 2 CPUs."""

    class Config(_Config):
        made: list[dict[str, Any]] = []  # noqa: RUF012 -- one list per test
        stopped = 0

    def which(name: str, *_: Any, **__: Any) -> str | None:
        return f"/usr/local/bin/{name}" if name == coganchor_apple.CONTAINER else None

    monkeypatch.setattr(shutil, "which", which)
    monkeypatch.setattr(coganchor_apple, "status", returning({"running": True}))
    monkeypatch.setattr(coganchor_apple, "capacity", returning((10.0, 32 << 30)))
    monkeypatch.setattr(
        coganchor_apple,
        "allocations",
        returning([Held("other", cpus=2, memory=4 << 30)]),
    )
    monkeypatch.setattr(machines, "AppleContainerConfig", Config)
    reach(monkeypatch)
    return Config


async def test_a_container_is_brought_up_with_its_share_as_its_size(
    mac: type[_Config],
) -> None:
    builder, _ = _roles()
    stored = runtime(Runtime(name="mac", run_args=("--dns", "1.1.1.1")))
    machine = AppleContainerMachine(
        "mac", WORK, stored=stored, role=builder, traced=True
    )
    driver = MachineEnvDriver(machine, PurePosixPath("/work"))

    await driver.probe()

    (made,) = mac.made
    assert (made["image"], made["workspace"], made["name"]) == (
        "debian:13",
        str(WORK),
        machine.name,
    )
    assert (made["cpus"], made["memory"]) == (3, 4 << 30)
    assert made["run_args"] == (*TRACING, "--dns", "1.1.1.1")
    assert (made["labels"][PROVIDER], made["labels"][ROLE]) == ("mac", "builder")
    assert machine.resources(gpus=True) == Resources(3, 4 << 30, 0, 0)
    assert driver.available

    await driver.close()
    assert mac.stopped == 1


async def test_a_role_asking_for_a_gpu_is_refused_there_being_none(
    mac: type[_Config],
) -> None:
    _, trainer = _roles()

    with pytest.raises(ResourceUnmet, match="no GPU to hand out"):
        await AppleContainerMachine(LOCAL, WORK, role=trainer).probe()
    assert mac.made == []


async def test_a_role_asking_more_than_is_left_is_refused_saying_who_holds_it(
    mac: type[_Config],
) -> None:
    builder, _ = _roles()
    small = runtime(Runtime(name="mac", cpus=4, max_containers=1))

    with pytest.raises(ResourceUnmet) as raised:
        await AppleContainerMachine("mac", WORK, stored=small, role=builder).probe()

    said = str(raised.value)
    assert "runs 1 of the 1 containers it may" in said
    assert "2 of 4 CPUs free" in said
    assert "held by other" in said


async def test_no_container_command_here_is_said_before_anything_is_asked(
    mac: type[_Config], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", returning(None))

    with pytest.raises(EnvUnavailable, match="Apple's container was not found"):
        await AppleContainerMachine(LOCAL, WORK).probe()


async def test_a_container_system_that_cannot_be_asked_is_a_connection_error(
    mac: type[_Config], monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(seconds: float) -> Any:
        raise OSError("XPC connection error")

    monkeypatch.setattr(coganchor_apple, "status", down)

    with pytest.raises(EnvConnectionError, match="XPC"):
        await AppleContainerMachine(LOCAL, WORK).probe()


@pytest.mark.parametrize(
    ("fails", "kind"),
    [
        (FileNotFoundError(2, "No such file", "container"), EnvUnavailable),
        (ValueError("bad image"), EnvUnavailable),
        (OSError("apiserver gone"), EnvConnectionError),
    ],
    ids=["no-program", "refused", "gone"],
)
async def test_a_container_that_would_not_start_says_why(
    mac: type[_Config], fails: BaseException, kind: type[Exception]
) -> None:
    mac.fails = fails

    with pytest.raises(kind):
        await AppleContainerMachine(LOCAL, WORK).probe()

"""Where an agent's harness runs: `harbors`, with coganchor's store and the env drivers mocked."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from types import SimpleNamespace
from typing import Any

import pytest

from hmz import machine
from hmz.coganchor.machines import store
from hmz.flows import EnvBackendKind, EnvUnavailable, ResourceUnmet
from hmz.runtime.flowing import environments
from hmz.runtime.flowing.fakes import FakeEnvDriver
from hmz.runtime.flowing.harbors import Harbors, harness_of
from hmz.runtime.flowing.specs import EnvSpec
from hmz.runtime.flowing.spi import Placement


@dataclass
class Docker:
    """A docker runtime as the store keeps one: its workdir, and whether its daemon is here."""

    workdir: str = ""
    here: bool | None = True
    harness: str = "env"

    def daemon(self) -> Any:
        if self.here is None:
            raise ValueError("no such ssh runtime")
        return SimpleNamespace(here=self.here)


@dataclass
class Apple:
    workdir: str = ""
    harness: str = "env"


@dataclass
class Other:
    workdir: str = ""
    harness: str = "env"


@dataclass
class World:
    """What the store holds, what `open_env` was asked for, and how probing goes."""

    runtimes: dict[tuple[str, str], Any] = field(
        default_factory=dict[tuple[str, str], Any]
    )
    opened: list[tuple[EnvSpec, bool]] = field(
        default_factory=list[tuple[EnvSpec, bool]]
    )
    drivers: list[FakeEnvDriver] = field(default_factory=list[FakeEnvDriver])
    finds: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    refuse: Exception | None = None


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    held = World()

    def find(backend: str, name: str) -> Any:
        held.finds.append((backend, name))
        return held.runtimes.get((backend, name))

    def affine(entry: str) -> tuple[str, str] | None:
        backend, colon, name = entry.partition(":")
        return (backend, name) if colon else None

    def open_env(spec: EnvSpec, role: object = None, *, traced: bool = False) -> Any:
        del role
        held.opened.append((spec, traced))
        driver = FakeEnvDriver(
            workdir=spec.workdir, backend=spec.backend, provider=spec.provider
        )
        held.drivers.append(driver)
        return driver

    async def probe(driver: Any) -> None:
        del driver
        if held.refuse is not None:
            raise held.refuse

    monkeypatch.setattr(store, "find", find)
    monkeypatch.setattr(store, "affine", affine)
    monkeypatch.setattr(store, "DockerRuntime", Docker)
    monkeypatch.setattr(store, "AppleContainerRuntime", Apple)
    monkeypatch.setattr(environments, "open_env", open_env)
    monkeypatch.setattr(environments, "probe", probe)
    return held


def test_the_harness_setting_of_a_runtime_is_its_own_and_env_for_none() -> None:
    runtime: Any = Other(harness="local")
    assert harness_of(runtime) == "local"
    assert harness_of(None) == "env"


def test_harbors_read_a_harness_setting_once_per_place(world: World) -> None:
    world.runtimes["ssh", "gpu"] = Other(harness="docker:box")
    harbors = Harbors()
    placement = Placement(EnvBackendKind.SSH, "gpu", PurePosixPath("/w"))
    assert harbors.setting(placement) == "docker:box"
    assert harbors.setting(placement) == "docker:box"
    nowhere = Placement(EnvBackendKind.LOCAL, "", PurePosixPath("/w"))
    assert harbors.setting(nowhere) == "env"
    assert world.finds == [("ssh", "gpu"), ("local", "")]


async def test_a_machine_is_opened_traced_once_and_closed_with_the_run(
    world: World,
) -> None:
    world.runtimes["ssh", "gpu"] = Other(workdir="/srv")
    harbors = Harbors()
    first = await harbors.machine("ssh:gpu")
    assert await harbors.machine("ssh:gpu") is first
    assert world.opened == [
        (EnvSpec("harness", EnvBackendKind.SSH, "gpu", PurePosixPath("/srv")), True)
    ]
    await harbors.close()
    await harbors.close()
    assert world.drivers[0].closed == 1


@pytest.mark.parametrize(
    ("entry", "runtime", "workdir"),
    [
        ("ssh:gpu", Other(), "~"),
        ("apple-container:mac", Apple(), "harness"),
        ("docker:box", Docker(here=True), "harness"),
    ],
)
async def test_a_runtime_with_no_workdir_is_given_one(
    world: World, entry: str, runtime: Any, workdir: str
) -> None:
    backend, _, name = entry.partition(":")
    world.runtimes[backend, name] = runtime
    driver = await Harbors().machine(entry)
    assert not isinstance(driver, Exception)
    spec, _ = world.opened[0]
    kept = PurePosixPath(machine() / workdir) if workdir == "harness" else workdir
    assert spec.workdir == PurePosixPath(kept)


@pytest.mark.parametrize(
    ("entry", "runtime", "says"),
    [
        ("env", None, "is not a runtime"),
        ("ssh:gone", None, "no ssh runtime is saved as 'gone'"),
        ("docker:far", Docker(here=False), "not on this machine"),
        ("docker:odd", Docker(here=None), "not on this machine"),
        ("swarm:s", Other(), "no workdir of its own"),
    ],
)
async def test_a_runtime_that_cannot_be_opened_is_refused(
    world: World, entry: str, runtime: Any, says: str
) -> None:
    backend, _, name = entry.partition(":")
    if runtime is not None:
        world.runtimes[backend, name] = runtime
    harbors = Harbors()
    refused = await harbors.machine(entry)
    assert isinstance(refused, EnvUnavailable)
    assert says in str(refused)
    assert await harbors.machine(entry) is refused
    assert world.opened == []


@pytest.mark.parametrize(
    "why", [EnvUnavailable("unreachable"), ResourceUnmet("no share left")]
)
async def test_a_runtime_that_fails_its_probe_is_closed_and_not_asked_again(
    world: World, why: Exception
) -> None:
    world.runtimes["ssh", "gpu"] = Other(workdir="/srv")
    world.refuse = why
    harbors = Harbors()
    assert await harbors.machine("ssh:gpu") is why
    assert await harbors.machine("ssh:gpu") is why
    assert len(world.opened) == 1
    assert world.drivers[0].closed == 1


async def test_a_probe_that_breaks_otherwise_closes_and_raises(world: World) -> None:
    world.runtimes["ssh", "gpu"] = Other(workdir="/srv")
    world.refuse = RuntimeError("boom")
    with pytest.raises(RuntimeError, match="boom"):
        await Harbors().machine("ssh:gpu")
    assert world.drivers[0].closed == 1

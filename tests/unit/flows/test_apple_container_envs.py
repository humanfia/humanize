"""An Apple container environment as it is named, shared out and placed -- nothing started.

`-e role=apple-container[@<provider>]/<workdir>` names a runtime written down or, naming none,
this Mac's containers with nothing saved; what a runtime may hand out is worked out against what its
running containers already hold, with what `container` says stood in for; and an agent working
in one is anchored to the container. Starting one is the integration tier's against a stand-in
and the system tier's against Apple's own.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, cast

import pytest

from hmz.coganchor.machines import AnchoredConfig, apple_container, store
from hmz.coganchor.machines.docker import Allocation
from hmz.coganchor.transport import Target
from hmz.flows import (
    CPUEnvMixin,
    Env,
    EnvBackendKind,
    EnvCollection,
    EnvUnavailable,
    GPUEnvMixin,
    ImageEnvMixin,
    MemoryEnvMixin,
    ResourceUnmet,
    ShellEnvMixin,
)
from hmz.runtime.flowing import affinity
from hmz.runtime.flowing.declaring import env_roles
from hmz.runtime.flowing.environing import MachineEnvDriver
from hmz.runtime.flowing.environing_apple_container import AppleContainerMachine
from hmz.runtime.flowing.environing_docker import IMAGE, TRACING, Asked
from hmz.runtime.flowing.environments import open_env
from hmz.runtime.flowing.specs import EnvSpec, EnvSpecError, parse_envs


class Builder(Env, ShellEnvMixin, CPUEnvMixin, MemoryEnvMixin, ImageEnvMixin):
    _image = "debian:13"
    _cpu_count = 2
    _memory = 1 << 30


class Trainer(Env, ShellEnvMixin, GPUEnvMixin):
    _gpu_count = 1


class Plain(Env, ShellEnvMixin): ...


class Envs(EnvCollection):
    builder: Builder
    trainer: Trainer
    plain: Plain


def _roles() -> dict[str, Any]:
    return {one.name: one for one in env_roles(Envs, globals(), {})}


def _machine(driver: object) -> AppleContainerMachine:
    assert isinstance(driver, MachineEnvDriver)
    machine = driver._machine
    assert isinstance(machine, AppleContainerMachine)
    return machine


# ---------------------------------------------------------------------------- what -e names


def test_an_e_names_a_runtime_written_down_or_this_macs_with_nothing_saved(
    tmp_path: Path,
) -> None:
    store.add(store.AppleContainerRuntime(name="mac", workdir=str(tmp_path)))

    (named,) = parse_envs(["box=apple-container@mac"])
    (spelled,) = parse_envs([f"box=apple-container{tmp_path}"])

    assert named.backend is EnvBackendKind.APPLE_CONTAINER
    assert (named.provider, named.workdir) == ("mac", PurePosixPath(tmp_path))
    assert (spelled.provider, spelled.workdir) == ("", PurePosixPath(tmp_path))
    assert _machine(open_env(named)).stored == store.find("apple-container", "mac")
    assert _machine(open_env(spelled)).stored is None


@pytest.mark.parametrize(
    ("said", "why"),
    [
        (
            "box=apple-container@local/srv/x",
            "names no provider; write box=apple-container/srv/x",
        ),
        ("box=apple-container@[mac]/srv/x", "only ssh takes a host nobody saved"),
        ("box=apple-container@/srv/x", "an @ is written only before a provider"),
    ],
)
def test_an_e_is_refused_where_dockers_would_be(said: str, why: str) -> None:
    with pytest.raises(EnvSpecError, match=why):
        parse_envs([said])


def test_a_runtime_nobody_wrote_down_is_refused() -> None:
    with pytest.raises(
        EnvSpecError, match="no apple-container runtime is saved as 'nowhere'"
    ):
        parse_envs(["box=apple-container@nowhere/srv/x"])
    spec = EnvSpec(
        "box", EnvBackendKind.APPLE_CONTAINER, "nowhere", PurePosixPath("/srv/x")
    )

    with pytest.raises(
        EnvUnavailable,
        match="apple-container host 'nowhere' not found: add one, or name none for "
        "this Mac's own, as apple-container/<workdir>",
    ):
        open_env(spec)


def test_a_runtime_that_cannot_be_read_says_so() -> None:
    at = store.where("apple-container", "broken")
    at.mkdir(parents=True)
    (at / "runtime.json").write_text("{")
    (spec,) = parse_envs(["box=apple-container@broken/srv/x"])

    with pytest.raises(EnvUnavailable, match="cannot be read"):
        open_env(spec)


def test_a_workdir_under_home_is_under_this_users_home() -> None:
    (spec,) = parse_envs(["box=apple-container/~/x"])

    assert open_env(spec).workdir == PurePosixPath(Path.home() / "x")


# -------------------------------------------------------------------- what it is started as


def test_a_container_is_started_as_its_role_says_and_named_for_it() -> None:
    store.add(store.AppleContainerRuntime(name="mac", image="alpine:3"))
    roles = _roles()

    driver = open_env(
        parse_envs(["builder=apple-container@mac/srv/x"])[0], roles["builder"]
    )
    bare = open_env(parse_envs(["plain=apple-container@mac/srv/x"])[0], roles["plain"])
    default = open_env(parse_envs(["plain=apple-container/srv/x"])[0], roles["plain"])

    machine = _machine(driver)
    assert machine.image == "debian:13"
    assert machine.asked == Asked(2, 1 << 30)
    assert machine.name.startswith("humanize-mac-builder-")
    assert machine.target == f"apple-container://{machine.name}"
    assert Target.parse(machine.target).host == machine.name
    assert _machine(bare).image == "alpine:3"
    assert _machine(default).image == IMAGE
    assert (driver.backend, driver.provider) == (EnvBackendKind.APPLE_CONTAINER, "mac")
    # Nothing is started until something is asked of it, and what it has is the least.
    assert not driver.available
    assert (driver.cpu_count, driver.gpu_count) == (1, 0)


def test_an_agent_in_a_container_is_anchored_to_it_in_a_mirror_of_its_own() -> None:
    (spec,) = parse_envs(["box=apple-container/srv/x"])
    driver = open_env(spec)

    placement = driver.placement()

    assert (placement.backend, placement.provider, placement.workdir) == (
        EnvBackendKind.APPLE_CONTAINER,
        "local",
        PurePosixPath("/srv/x"),
    )
    assert isinstance(placement.machine, AnchoredConfig)
    anchor = placement.machine.anchor
    assert anchor.target.startswith("apple-container://humanize-local-box-")
    assert anchor.workspace == "/srv/x"
    assert anchor.shadow is not None
    assert not anchor.shadow.startswith("/srv/x")
    assert driver.placement() == placement


# ------------------------------------------------------------------- what it is handed out


class _Started:
    """What `AppleContainerConfig` was made with, standing in for starting it."""

    def __init__(self) -> None:
        self.made: list[dict[str, Any]] = []

    def __call__(self, **said: Any) -> _Started:
        self.made.append(said)
        return self

    def create(self) -> _Started:
        return self

    def start(self) -> None:
        return None


@pytest.fixture
def mac(monkeypatch: pytest.MonkeyPatch) -> tuple[_Started, list[Allocation]]:
    """A Mac of four CPUs and 8 GiB, nothing of humanize's running on it yet.

    Returns:
      What containers were started with, and what is running -- for the test to add to.
    """
    from hmz.coganchor import machines

    started = _Started()
    running: list[Allocation] = []

    def status(seconds: float | None = None) -> dict[str, Any]:
        del seconds
        return {"status": "running", "host": {"cpus": 4}}

    def capacity(said: dict[str, Any]) -> tuple[float, int]:
        return float(said["host"]["cpus"]), 8 << 30

    def allocations(
        labels: dict[str, str] | None = None, *, seconds: float | None = None
    ) -> list[Allocation]:
        del labels, seconds
        return running

    def which(name: str) -> str:
        return f"/usr/local/bin/{name}"

    monkeypatch.setattr(apple_container, "status", status)
    monkeypatch.setattr(apple_container, "capacity", capacity)
    monkeypatch.setattr(apple_container, "allocations", allocations)
    monkeypatch.setattr(machines, "AppleContainerConfig", started)
    monkeypatch.setattr(
        "hmz.runtime.flowing.environing_apple_container.shutil.which", which
    )
    return started, running


def test_a_container_is_given_exactly_what_its_role_asks_and_labelled_for_it(
    mac: tuple[_Started, list[Allocation]],
) -> None:
    started, _ = mac
    store.add(store.AppleContainerRuntime(name="mac", run_args=("--dns", "1.1.1.1")))
    roles = _roles()
    (spec,) = parse_envs(["builder=apple-container@mac/srv/x"])

    _machine(open_env(spec, roles["builder"]))._brought_up()
    _machine(open_env(spec, roles["plain"]))._brought_up()

    builder, plain = started.made
    assert (builder["cpus"], builder["memory"], builder["image"]) == (
        2,
        1 << 30,
        "debian:13",
    )
    assert builder["workspace"] == "/srv/x"
    assert builder["run_args"] == ("--dns", "1.1.1.1")
    labels = cast("dict[str, str]", builder["labels"])
    assert (labels["humanize.provider"], labels["humanize.role"]) == ("mac", "builder")
    assert {"humanize.host", "humanize.pid"} <= set(labels)
    # A role asking nothing is given `container`'s own default.
    assert (plain["cpus"], plain["memory"]) == (None, None)


def test_a_container_holding_a_harness_may_borrow_its_agents_descriptors(
    mac: tuple[_Started, list[Allocation]],
) -> None:
    started, _ = mac
    (spec,) = parse_envs(["harness=apple-container/srv/x"])

    _machine(open_env(spec, traced=True))._brought_up()
    _machine(open_env(spec))._brought_up()

    assert [one["run_args"] for one in started.made] == [TRACING, ()]


def test_a_role_asking_more_than_is_left_is_refused_saying_who_holds_it(
    mac: tuple[_Started, list[Allocation]],
) -> None:
    started, running = mac
    store.add(store.AppleContainerRuntime(name="mac", cpus=3, max_containers=1))
    running.append(
        Allocation(
            "busy",
            2.0,
            None,
            (),
            {"humanize.pid": "4242", "humanize.host": "elsewhere"},
        )
    )
    (spec,) = parse_envs(["builder=apple-container@mac/srv/x"])

    with pytest.raises(ResourceUnmet) as refused:
        _machine(open_env(spec, _roles()["builder"]))._brought_up()

    assert str(refused.value) == (
        "apple-container@mac runs 1 of the 1 containers it may (one held by busy, pid "
        "4242 on elsewhere); apple-container@mac has 1 of 3 CPUs free, and 'builder' "
        "asks for 2 (2 CPUs held by busy, pid 4242 on elsewhere)"
    )
    assert started.made == []


def test_a_role_asking_for_a_gpu_is_refused_there_being_none(
    mac: tuple[_Started, list[Allocation]],
) -> None:
    started, _ = mac
    (spec,) = parse_envs(["trainer=apple-container/srv/x"])

    with pytest.raises(ResourceUnmet, match=r"^apple-container has no GPU to hand out"):
        _machine(open_env(spec, _roles()["trainer"]))._brought_up()

    assert started.made == []


def test_no_container_command_here_is_said_before_anything_is_asked(
    mac: tuple[_Started, list[Allocation]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def nowhere(name: str) -> None:
        del name

    monkeypatch.setattr(
        "hmz.runtime.flowing.environing_apple_container.shutil.which", nowhere
    )
    (spec,) = parse_envs(["box=apple-container/srv/x"])

    with pytest.raises(EnvUnavailable, match="Apple's container was not found"):
        _machine(open_env(spec))._brought_up()
    assert mac[0].made == []


# ----------------------------------------------------------------------- a harness's place


def test_a_runtime_of_apple_containers_with_no_workdir_holds_a_harness_here() -> None:
    from hmz import home

    store.add(store.AppleContainerRuntime(name="mac"))

    driver = affinity._opened("apple-container:mac")

    machine = _machine(driver)
    assert machine.traced
    assert driver.workdir == PurePosixPath(home() / "harness")

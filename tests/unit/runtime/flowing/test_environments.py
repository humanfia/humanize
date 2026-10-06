"""Which driver an `-e` comes to, and where it falls back to, with saved runtimes stood in for."""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import settings
from hmz.coganchor.machines import AnchoredConfig, store
from hmz.flows import (
    EnvBackendKind,
    EnvConnectionError,
    EnvError,
    EnvUnavailable,
    ResourceUnmet,
)
from hmz.runtime.flowing import specs
from hmz.runtime.flowing.environing import MachineEnvDriver
from hmz.runtime.flowing.environments import local_env, open_env, probe, settle
from hmz.runtime.flowing.fakes import FakeEnvDriver
from hmz.runtime.flowing.specs import EnvSpec
from tests.unit.runtime.flowing.doubles_u11 import Runtime, returning

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.runtime.flowing.spi import EnvDriver


def _spec(
    backend: EnvBackendKind, provider: str = "", workdir: str = "/srv/x"
) -> EnvSpec:
    return EnvSpec("box", backend, provider, PurePosixPath(workdir))


@pytest.fixture
def saved(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, str], Runtime]:
    """The runtimes written down, by backend and name; one named `broken` cannot be read."""
    found: dict[tuple[str, str], Runtime] = {}

    def find(backend: str, name: str) -> Runtime | None:
        return found.get((backend, name))

    def is_saved(backend: str, name: str) -> bool:
        if name.startswith("["):
            raise ValueError("no runtime has that name")
        return name == "broken" or (backend, name) in found

    for kind in (
        "SSHRuntime",
        "DockerRuntime",
        "SwarmRuntime",
        "AppleContainerRuntime",
    ):
        monkeypatch.setattr(store, kind, Runtime)
    monkeypatch.setattr(store, "find", find)
    monkeypatch.setattr(store, "saved", is_saved)
    monkeypatch.setattr(settings, "where", lambda: Path("/settings.yaml"))
    return found


@pytest.fixture(autouse=True)
def _no_nvidia_smi(monkeypatch: pytest.MonkeyPatch) -> None:
    """A machine with no `nvidia-smi`, so that probing this one runs nothing."""
    which = shutil.which

    def found(name: str, *args: Any, **kwargs: Any) -> str | None:
        return None if name == "nvidia-smi" else which(name, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", found)


# ---------------------------------------------------------------------------- this machine


def test_a_directory_here_is_a_local_driver_named_lexically(tmp_path: Path) -> None:
    (tmp_path / "repo").mkdir()

    driver = local_env(tmp_path / "repo" / ".." / "repo")

    assert isinstance(driver, MachineEnvDriver)
    assert (driver.backend, driver.provider) == (EnvBackendKind.LOCAL, "")
    assert driver.workdir == PurePosixPath(tmp_path / "repo")
    assert driver.available


def test_a_relative_directory_is_taken_from_where_this_process_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "rel").mkdir()

    assert local_env(Path("rel")).workdir == PurePosixPath(Path.cwd() / "rel")


def test_no_directory_here_is_unavailable(tmp_path: Path) -> None:
    (tmp_path / "file").write_text("x")

    for nothing in (tmp_path / "gone", tmp_path / "file"):
        with pytest.raises(EnvUnavailable, match="no directory"):
            local_env(nothing)


def test_a_local_e_is_a_directory_here(tmp_path: Path) -> None:
    driver = open_env(_spec(EnvBackendKind.LOCAL, workdir=str(tmp_path)))

    assert (driver.backend, driver.workdir) == (
        EnvBackendKind.LOCAL,
        PurePosixPath(tmp_path),
    )


async def test_probing_learns_what_a_machine_has_and_leaves_any_other_driver_alone(
    tmp_path: Path,
) -> None:
    here = local_env(tmp_path)
    fake = FakeEnvDriver()

    await probe(here)
    await probe(fake)

    assert here.available
    assert here.cpu_count >= 1
    assert fake.available


# ------------------------------------------------------------------------------- over ssh


def test_a_saved_ssh_host_is_reached_as_it_says_by_its_own_name(
    saved: dict[tuple[str, str], Runtime],
) -> None:
    saved[store.SSH, "gpu"] = Runtime(name="gpu", ssh_target="ssh://me@gpu.lan:2222")

    driver = open_env(_spec(EnvBackendKind.SSH, "gpu", "~/repo/./x/.."))

    assert (driver.backend, driver.provider, driver.workdir) == (
        EnvBackendKind.SSH,
        "gpu",
        PurePosixPath("~/repo"),
    )
    assert not driver.available, "nothing is reached until something is asked"
    placement = driver.placement()
    assert placement.machine is not None


def test_a_host_in_brackets_is_handed_to_ssh_as_it_is(
    saved: dict[tuple[str, str], Runtime],
) -> None:
    saved[store.SSH, "me@box:22"] = Runtime(ssh_target="ssh://elsewhere")

    driver = open_env(_spec(EnvBackendKind.SSH, "[me@box:22]", "/srv/x"))

    assert driver.provider == "me@box:22"
    machine = driver.placement().machine
    assert isinstance(machine, AnchoredConfig)
    assert machine.anchor.target == "ssh://me@box:22", "not the runtime saved under it"


@pytest.mark.parametrize(
    ("provider", "why"),
    [
        ("nobody", "no ssh host is saved as 'nobody'"),
        (
            "broken",
            r"cannot be read; fix or remove it: runtimes\.ssh\.broken in /settings",
        ),
        ("[not a host]", "not an ssh host"),
    ],
)
def test_an_ssh_host_nobody_can_reach_is_unavailable(
    saved: dict[tuple[str, str], Runtime], provider: str, why: str
) -> None:
    with pytest.raises(EnvUnavailable, match=why):
        open_env(_spec(EnvBackendKind.SSH, provider))


@pytest.mark.parametrize("workdir", ["relative", "~/../x"])
def test_an_ssh_workdir_neither_absolute_nor_under_home_is_unavailable(
    saved: dict[tuple[str, str], Runtime], workdir: str
) -> None:
    saved[store.SSH, "gpu"] = Runtime()

    with pytest.raises(EnvUnavailable):
        open_env(_spec(EnvBackendKind.SSH, "gpu", workdir))


# --------------------------------------------------------------------- docker, swarm, Apple


_RUNTIMES = [
    (EnvBackendKind.DOCKER, store.DOCKER, "docker host"),
    (EnvBackendKind.SWARM, store.SWARM, "docker swarm"),
    (EnvBackendKind.APPLE_CONTAINER, store.APPLE_CONTAINER, "apple-container host"),
]


@pytest.mark.parametrize(("backend", "kind", "called"), _RUNTIMES)
def test_a_runtime_e_names_one_saved_or_the_default_here(
    saved: dict[tuple[str, str], Runtime],
    backend: EnvBackendKind,
    kind: str,
    called: str,
) -> None:
    saved[kind, "box"] = Runtime(image="debian:13")

    named = open_env(_spec(backend, "box"))
    default = open_env(_spec(backend))

    assert (named.backend, named.provider, named.workdir) == (
        backend,
        "box",
        PurePosixPath("/srv/x"),
    )
    assert (default.backend, default.provider) == (backend, "local")
    assert not named.available


@pytest.mark.parametrize(("backend", "kind", "called"), _RUNTIMES)
def test_a_runtime_nobody_saved_or_that_cannot_be_read_is_unavailable(
    saved: dict[tuple[str, str], Runtime],
    backend: EnvBackendKind,
    kind: str,
    called: str,
) -> None:
    with pytest.raises(EnvUnavailable, match=f"{called} 'nobody' not found"):
        open_env(_spec(backend, "nobody"))
    with pytest.raises(EnvUnavailable, match=rf"runtimes\.{kind}\.broken"):
        open_env(_spec(backend, "broken"))


@pytest.mark.parametrize(
    ("backend", "kind"),
    [(EnvBackendKind.DOCKER, store.DOCKER), (EnvBackendKind.SWARM, store.SWARM)],
)
def test_a_home_workdir_is_only_for_a_daemon_on_this_machine(
    saved: dict[tuple[str, str], Runtime], backend: EnvBackendKind, kind: str
) -> None:
    saved[kind, "remote"] = Runtime(endpoint="tcp://elsewhere:2376")
    saved[kind, "broken-endpoint"] = Runtime(endpoint="broken")

    here = open_env(_spec(backend, workdir="~/repo"))

    assert here.workdir == PurePosixPath(Path.home() / "repo")
    for name in ("remote", "broken-endpoint"):
        with pytest.raises(EnvUnavailable, match="must be an absolute path"):
            open_env(_spec(backend, name, "~/repo"))


def test_an_apple_container_workdir_under_home_is_this_users() -> None:
    driver = open_env(_spec(EnvBackendKind.APPLE_CONTAINER, workdir="~/repo"))

    assert driver.workdir == PurePosixPath(Path.home() / "repo")


# ------------------------------------------------------------------------------ settling


def _fallbacks(monkeypatch: pytest.MonkeyPatch, onward: list[EnvSpec]) -> None:
    monkeypatch.setattr(specs, "fallbacks", returning(onward))


def _refusing(*names: str) -> Callable[[EnvDriver], None]:
    def fits(driver: EnvDriver) -> None:
        if driver.workdir.name in names:
            raise ResourceUnmet(f"{driver.workdir.name} is too small")

    return fits


async def test_an_environment_its_runtime_holds_stays_there(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fallbacks(monkeypatch, [_spec(EnvBackendKind.LOCAL, workdir=str(tmp_path))])
    spec = _spec(EnvBackendKind.LOCAL, workdir=str(tmp_path))
    driver = FakeEnvDriver()
    told: list[str] = []

    said = await settle(spec, driver, moved=told.append)

    assert said == (spec, driver)
    assert told == []


async def test_an_environment_moves_down_the_list_until_a_runtime_holds_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name in ("small", "big"):
        (tmp_path / name).mkdir()
    small = _spec(EnvBackendKind.LOCAL, workdir=str(tmp_path / "small"))
    big = _spec(EnvBackendKind.LOCAL, workdir=str(tmp_path / "big"))
    _fallbacks(monkeypatch, [small, big])
    first = FakeEnvDriver(workdir="/first")
    told: list[str] = []

    spec, driver = await settle(
        _spec(EnvBackendKind.SSH, "gpu"),
        first,
        fits=_refusing("first", "small"),
        moved=told.append,
    )

    assert spec == big
    assert driver.workdir == PurePosixPath(tmp_path / "big")
    assert driver.available
    assert first.closed == 1, "a driver refused on the way is closed"
    (line,) = told
    assert "ssh:gpu cannot hold 'box': first is too small" in line
    assert "local: cannot hold 'box': small is too small" in line
    assert line.endswith("using local:")


async def test_a_runtime_that_could_not_open_falls_back_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    onward = _spec(EnvBackendKind.LOCAL, workdir=str(tmp_path))
    _fallbacks(monkeypatch, [onward])

    spec, _ = await settle(
        _spec(EnvBackendKind.SSH, "gpu"), EnvUnavailable("no such host")
    )

    assert spec == onward


async def test_nowhere_on_the_list_holding_it_raises_what_the_last_refusal_was(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fallbacks(
        monkeypatch, [_spec(EnvBackendKind.LOCAL, workdir=str(tmp_path / "gone"))]
    )

    with pytest.raises(EnvUnavailable) as raised:
        await settle(
            _spec(EnvBackendKind.SSH, "gpu"), EnvConnectionError("unreachable")
        )

    said = str(raised.value)
    assert "ssh:gpu cannot hold 'box': unreachable" in said
    assert "no directory" in said


@pytest.mark.parametrize(
    "refusal", [EnvConnectionError("unreachable"), ResourceUnmet("too small")]
)
async def test_with_no_list_the_runtimes_own_refusal_is_raised(
    monkeypatch: pytest.MonkeyPatch, refusal: EnvError | ResourceUnmet
) -> None:
    _fallbacks(monkeypatch, [])

    def fits(driver: EnvDriver) -> None:
        if isinstance(refusal, ResourceUnmet):
            raise refusal

    given: EnvDriver | EnvError = (
        refusal if isinstance(refusal, EnvError) else FakeEnvDriver()
    )
    with pytest.raises(type(refusal)) as raised:
        await settle(_spec(EnvBackendKind.SSH, "gpu"), given, fits=fits)
    assert raised.value is refusal

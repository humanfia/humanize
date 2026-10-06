"""Environment drivers, as an `-e` opens them, doing their work on the machine they name.

A directory here is the real thing. An ssh host, a docker container, a swarm task and an
Apple container are reached through the fakes in `doubles_anchor`, which run what they are
sent on this machine: so commands, files and subdirectories go over coganchor's road for
real. A container must say it is linux, which a fake one on a Mac cannot -- there, what is
checked is that the environment is refused and its container taken down.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.machines import AnchoredConfig
from hmz.flows import (
    EnvBackendKind,
    EnvCommandTimeout,
    EnvConnectionError,
    EnvError,
    EnvFileNotFound,
    EnvUnavailable,
)
from hmz.runtime.flowing.environing import MachineEnvDriver
from hmz.runtime.flowing.environing_docker import HOST, PID, PROVIDER
from hmz.runtime.flowing.environments import local_env, open_env, probe
from hmz.runtime.flowing.specs import parse_envs
from tests.integration.doubles_anchor import Fakes, fakes

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from hmz.runtime.flowing.spi import EnvDriver

PATIENCE = 60.0

linux = pytest.mark.skipif(
    sys.platform != "linux",
    reason="a fake container is this machine, which says it is not the linux one promised",
)
not_linux = pytest.mark.skipif(
    sys.platform == "linux",
    reason="a fake container on linux says linux, as promised, so it is not refused",
)


def _opened(item: str) -> MachineEnvDriver:
    """The driver one `-e` opens."""
    (spec,) = parse_envs([item])
    driver = open_env(spec)
    assert isinstance(driver, MachineEnvDriver)
    return driver


@pytest.fixture
def far(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fakes:
    made = fakes(tmp_path, monkeypatch)
    made.answer(
        "info",
        json.dumps({"ServerVersion": "27.0", "NCPU": 8, "MemTotal": 16 << 30}),
    )
    return made


@pytest.fixture
def work(tmp_path: Path) -> Path:
    held = tmp_path / "work"
    held.mkdir()
    (held / "seed.txt").write_text("seeded\n")
    return held.resolve()


async def _uses(driver: EnvDriver, work: Path) -> None:
    """What every driver does, checked against the directory it does it in."""
    status, out, err = await driver.exec(
        ["/bin/sh", "-c", "cat seed.txt; echo oops >&2; exit 3"], timeout=PATIENCE
    )
    assert (status, out, err) == (3, "seeded\n", "oops\n")
    await driver.write("made/deep.txt", b"written")
    assert (work / "made" / "deep.txt").read_bytes() == b"written"
    assert await driver.read("seed.txt") == b"seeded\n"
    sub = await driver.derive_subdir("sub")
    assert sub.workdir == driver.workdir / "sub"
    assert (work / "sub").is_dir()
    status, out, _ = await sub.exec(["/bin/sh", "-c", "pwd -P"], timeout=PATIENCE)
    assert status == 0
    assert out.strip() == str(work / "sub")
    with pytest.raises(EnvFileNotFound):
        await driver.read("missing")


@pytest.fixture
async def here(work: Path) -> AsyncIterator[EnvDriver]:
    driver = local_env(work)
    yield driver
    await driver.close()


async def test_a_directory_here_does_the_work_in_place(
    here: EnvDriver, work: Path
) -> None:
    assert here.backend is EnvBackendKind.LOCAL
    assert here.available

    await _uses(here, work)


async def test_a_local_command_timed_out_is_killed_with_its_children(
    here: EnvDriver, work: Path
) -> None:
    with pytest.raises(EnvCommandTimeout):
        await here.exec("sleep 30 & echo $! > child; wait", timeout=1.0)

    child = int((work / "child").read_text())
    for _ in range(100):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("a timed-out command's child outlived it")


async def test_a_local_program_that_is_not_there_is_not_found(here: EnvDriver) -> None:
    with pytest.raises(EnvFileNotFound):
        await here.exec(["no-such-program-anywhere"], timeout=PATIENCE)


def test_a_local_directory_that_is_not_there_is_unavailable(tmp_path: Path) -> None:
    with pytest.raises(EnvUnavailable, match="no directory"):
        local_env(tmp_path / "missing")


def _host(tmp_path: Path, prefix: str = "box") -> str:
    """A host name of the test's own: a host is bootstrapped once per process and name."""
    return f"{prefix}-{tmp_path.name}"


async def test_an_ssh_host_is_reached_only_once_asked(
    far: Fakes, work: Path, tmp_path: Path
) -> None:
    host = _host(tmp_path)
    driver = _opened(f"work=ssh@[{host}]{work}")
    try:
        assert driver.backend is EnvBackendKind.SSH
        assert driver.provider == host
        assert not driver.available
        placement = driver.placement()
        assert isinstance(placement.machine, AnchoredConfig)
        assert placement.machine.anchor.target == f"ssh://{host}"
        assert not far.calls("ssh")

        await probe(driver)

        assert driver.available
        assert driver.cpu_count >= 1
        await _uses(driver, work)
        assert far.calls("ssh")
    finally:
        await driver.close()


async def test_a_closed_ssh_driver_refuses_more_work(
    far: Fakes, work: Path, tmp_path: Path
) -> None:
    driver = _opened(f"work=ssh@[{_host(tmp_path)}]{work}")
    await probe(driver)

    await driver.close()

    assert not driver.available
    with pytest.raises(EnvError, match="closed"):
        await driver.exec(["true"], timeout=PATIENCE)


async def test_an_ssh_host_that_refuses_is_a_connection_error(
    far: Fakes, work: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    far.fail(monkeypatch, "ssh", "ssh: connect to host box port 22: Connection refused")
    driver = _opened(f"work=ssh@[{_host(tmp_path)}]{work}")

    with pytest.raises(EnvConnectionError, match="Connection refused"):
        await probe(driver)
    assert not driver.available
    await driver.close()


async def test_an_ssh_workdir_that_is_not_there_is_unavailable(
    far: Fakes, tmp_path: Path
) -> None:
    driver = _opened(f"work=ssh@[{_host(tmp_path)}]{tmp_path / 'missing'}")
    try:
        with pytest.raises(EnvUnavailable, match="not there"):
            await probe(driver)
        assert not driver.available
    finally:
        await driver.close()


def _run_of(far: Fakes, tool: str = "docker") -> list[str]:
    (argv,) = [
        one for one in far.calls(tool) if one[:1] == ["run"] and "--detach" in one
    ]
    return argv


def _labels(argv: list[str]) -> set[str]:
    return {argv[at + 1] for at, word in enumerate(argv) if word == "--label"}


@linux
async def test_a_docker_environment_works_in_a_container_of_its_own(
    far: Fakes, work: Path
) -> None:
    driver = _opened(f"work=docker{work}")
    try:
        await probe(driver)
        assert driver.available
        await _uses(driver, work)
    finally:
        await driver.close()

    run = _run_of(far)
    assert {f"{PROVIDER}=local", f"{PID}={os.getpid()}"} <= _labels(run)
    assert any(one[:2] == ["rm", "--force"] for one in far.calls("docker"))


@not_linux
async def test_a_docker_environment_that_is_not_linux_is_refused_and_removed(
    far: Fakes, work: Path
) -> None:
    driver = _opened(f"work=docker{work}")
    try:
        with pytest.raises(EnvUnavailable, match="cannot serve linux"):
            await probe(driver)
    finally:
        await driver.close()

    _run_of(far)
    assert any(one[:2] == ["rm", "--force"] for one in far.calls("docker"))


async def test_a_container_a_dead_run_left_is_taken_down_by_the_next(
    far: Fakes, work: Path
) -> None:
    dead = os.getpid() + 1_000_000
    far.answer("ps", "stale\n")
    far.answer(
        "inspect",
        json.dumps(
            [
                {
                    "Name": "/humanize-local-gone",
                    "Config": {
                        "Labels": {
                            "humanize": str(os.getuid()),
                            PROVIDER: "local",
                            HOST: socket.gethostname(),
                            PID: str(dead),
                        }
                    },
                }
            ]
        ),
    )
    driver = _opened(f"work=docker{work}")
    try:
        if sys.platform == "linux":
            await probe(driver)
        else:
            with pytest.raises(EnvUnavailable):
                await probe(driver)
    finally:
        await driver.close()

    assert ["rm", "--force", "humanize-local-gone"] in far.calls("docker")


async def test_a_docker_daemon_that_cannot_be_asked_is_a_connection_error(
    far: Fakes, work: Path
) -> None:
    far.answer("info", stderr="Cannot connect to the Docker daemon", status=1)
    driver = _opened(f"work=docker{work}")
    try:
        with pytest.raises(EnvConnectionError, match="Cannot connect"):
            await probe(driver)
    finally:
        await driver.close()
    assert not [one for one in far.calls("docker") if one[:1] == ["run"]]


def _swarm(far: Fakes) -> None:
    far.answer(
        "info",
        json.dumps(
            {
                "ServerVersion": "27.0",
                "NCPU": 8,
                "MemTotal": 16 << 30,
                "Swarm": {
                    "LocalNodeState": "active",
                    "ControlAvailable": True,
                    "NodeID": "n1",
                },
            }
        ),
    )
    far.answer("service create", "svc-1\n")
    far.answer("service ps", "task-1\n")
    far.answer(
        "inspect",
        json.dumps(
            [
                {
                    "NodeID": "n1",
                    "Status": {
                        "State": "running",
                        "ContainerStatus": {"ContainerID": "c1"},
                    },
                }
            ]
        ),
    )
    far.answer(
        "node inspect",
        json.dumps(
            [
                {
                    "ID": "n1",
                    "Spec": {"Availability": "active"},
                    "Description": {"Hostname": "alpha", "Resources": {}},
                    "Status": {"State": "ready", "Addr": "10.0.0.7"},
                }
            ]
        ),
    )


@linux
async def test_a_swarm_environment_works_in_a_task_of_its_own(
    far: Fakes, work: Path
) -> None:
    _swarm(far)
    driver = _opened(f"work=swarm{work}")
    try:
        await probe(driver)
        await _uses(driver, work)
    finally:
        await driver.close()

    assert ["service", "rm", "svc-1"] in far.calls("docker")


@not_linux
async def test_a_swarm_environment_that_is_not_linux_is_refused_and_removed(
    far: Fakes, work: Path
) -> None:
    _swarm(far)
    driver = _opened(f"work=swarm{work}")
    try:
        with pytest.raises(EnvUnavailable, match="cannot serve linux"):
            await probe(driver)
    finally:
        await driver.close()

    assert ["service", "rm", "svc-1"] in far.calls("docker")


def _apple(far: Fakes) -> None:
    far.answer("system", json.dumps({"status": "running"}))
    far.answer("list", "[]")


@linux
async def test_an_apple_container_environment_works_in_a_container_of_its_own(
    far: Fakes, work: Path
) -> None:
    _apple(far)
    driver = _opened(f"work=apple-container{work}")
    try:
        await probe(driver)
        await _uses(driver, work)
    finally:
        await driver.close()

    _run_of(far, "container")
    assert any(one[:2] == ["delete", "--force"] for one in far.calls("container"))


@not_linux
async def test_an_apple_container_environment_that_is_not_linux_is_refused(
    far: Fakes, work: Path
) -> None:
    _apple(far)
    driver = _opened(f"work=apple-container{work}")
    try:
        with pytest.raises(EnvUnavailable, match="cannot serve linux"):
            await probe(driver)
    finally:
        await driver.close()

    assert any(one[:2] == ["delete", "--force"] for one in far.calls("container"))


async def test_an_apple_container_system_not_running_refuses_the_environment(
    far: Fakes, work: Path
) -> None:
    far.answer("system", json.dumps({"status": "stopped"}))
    driver = _opened(f"work=apple-container{work}")
    try:
        with pytest.raises(EnvError):
            await probe(driver)
    finally:
        await driver.close()
    assert not [one for one in far.calls("container") if one[:1] == ["run"]]


def test_a_placement_anchors_the_agent_to_the_machine_it_names(
    far: Fakes, work: Path
) -> None:
    driver = _opened(f"work=docker{work}")

    placement = driver.placement()

    assert placement.workdir == PurePosixPath(work)
    assert isinstance(placement.machine, AnchoredConfig)
    assert placement.machine.anchor.target.startswith("docker://humanize-local-work-")
    assert placement.machine.anchor.workspace == str(work)
    assert not far.calls("docker")

"""Environment drivers, as an `-e` opens them, doing their work on the machine they name.

A directory here is the real thing. An ssh host, a docker container, a swarm task, an Apple
container and a Slurm job are reached through the fakes in `doubles_anchor`, which run what they are
sent on this machine: so commands, files and subdirectories go over coganchor's road for
real. A container must say it is linux, which a fake one on a Mac cannot -- there, what is
checked is that the environment is refused and its container taken down.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import sys
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.machines import AnchoredConfig, store
from hmz.flows import (
    EnvBackendKind,
    EnvCommandTimeout,
    EnvConnectionError,
    EnvError,
    EnvFileNotFound,
    EnvUnavailable,
    ResourceUnmet,
)
from hmz.runtime.flowing.environing import MachineEnvDriver
from hmz.runtime.flowing.environing_docker import HOST, PID, PROVIDER
from hmz.runtime.flowing.environments import local_env, open_env, probe
from hmz.runtime.flowing.specs import parse_envs
from tests.integration.doubles_anchor import Fakes, fakes, slurm

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


@linux
async def test_a_docker_environment_works_in_a_running_container_and_leaves_it_running(
    far: Fakes, work: Path
) -> None:
    far.answer("inspect", "true\n")
    user = f"{os.getuid()}:{os.getgid()}"
    store.write(
        store.new(
            store.DOCKER,
            "kept",
            container="kept-box",
            exec_user=user,
            exec_env=["HZ_PROBE=a b"],
        )
    )
    driver = _opened(f"work=docker@kept{work}")
    try:
        await probe(driver)
        assert driver.available
        await _uses(driver, work)
    finally:
        await driver.close()

    calls = far.calls("docker")
    assert [
        "inspect",
        "--type",
        "container",
        "--format",
        "{{.State.Running}}",
        "kept-box",
    ] in calls
    assert not [one for one in calls if one[:1] in (["run"], ["rm"], ["stop"], ["ps"])]
    execs = [one for one in calls if one[:1] == ["exec"]]
    assert execs
    for one in execs:
        assert one[:7] == ["exec", "-i", "-u", user, "-e", "HZ_PROBE=a b", "kept-box"]
    assert list((far.root / "tmp" / f"humanize-{os.getuid()}").glob("humanize-*.pyz"))


async def test_a_running_container_a_runtime_names_that_is_not_is_unavailable(
    far: Fakes, work: Path
) -> None:
    far.answer("inspect", "false\n")
    store.write(store.new(store.DOCKER, "kept", container="kept-box"))
    driver = _opened(f"work=docker@kept{work}")
    try:
        with pytest.raises(
            EnvUnavailable,
            match="cannot work in the container kept-box: it is not running",
        ):
            await probe(driver)
    finally:
        await driver.close()

    assert not [
        one
        for one in far.calls("docker")
        if one[:1] in (["exec"], ["run"], ["rm"], ["stop"])
    ]


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


def _name_of(argv: list[str]) -> str:
    """The name a `docker run` or a `docker service create` was told to give it."""
    return argv[argv.index("--name") + 1]


async def _probed(driver: MachineEnvDriver) -> None:
    """Probes it: a fake container here, which is not linux off linux, is then refused."""
    try:
        if sys.platform == "linux":
            await probe(driver)
        else:
            with pytest.raises(EnvUnavailable):
                await probe(driver)
    finally:
        await driver.close()


async def test_a_docker_runtime_naming_a_prefix_starts_its_containers_under_it(
    far: Fakes, work: Path
) -> None:
    store.write(store.new(store.DOCKER, "team", name_prefix="team-a"))

    await _probed(_opened(f"work=docker@team{work}"))

    assert re.fullmatch(r"team-a-work-[0-9a-f]{8}", _name_of(_run_of(far)))


async def test_a_swarm_runtime_naming_a_prefix_creates_its_services_under_it(
    far: Fakes, work: Path
) -> None:
    _swarm(far)
    store.write(store.new(store.SWARM, "team", name_prefix="team-a"))

    await _probed(_opened(f"work=swarm@team{work}"))

    (created,) = [
        one for one in far.calls("docker") if one[:2] == ["service", "create"]
    ]
    assert re.fullmatch(r"team-a-work-[0-9a-f]{8}", _name_of(created))


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


@pytest.fixture
def cluster(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fakes:
    """A cluster of one node, this machine, saved as `hpc` with this interpreter on it."""
    made = slurm(tmp_path, monkeypatch)
    store.write(store.new(store.SLURM, "hpc", python=sys.executable, max_jobs=2))
    return made


@linux
@pytest.mark.parametrize("via", ["srun", "tcp"])
async def test_a_slurm_environment_works_on_a_job_of_its_own(
    cluster: Fakes, work: Path, via: str
) -> None:
    store.write(store.new(store.SLURM, "hpc", python=sys.executable, via=via))
    driver = _opened(f"work=slurm@hpc{work}")
    try:
        await probe(driver)
        assert driver.available
        await _uses(driver, work)
        placed = driver.placement().machine
        assert isinstance(placed, AnchoredConfig)
        assert placed.anchor.target.startswith("tcp://" if via == "tcp" else "slurm://")
        assert (placed.anchor.token is None) == (via == "srun")
    finally:
        await driver.close()

    (submitted,) = cluster.calls("sbatch")
    comment = submitted[submitted.index("--comment") + 1]
    assert f"{PROVIDER}=hpc" in comment
    assert f"{PID}={os.getpid()}" in comment
    assert len(cluster.calls("scancel")) == 1


@linux
async def test_slurm_environments_past_their_runtimes_job_limit_are_refused(
    cluster: Fakes, work: Path
) -> None:
    first, second, third = (_opened(f"w{one}=slurm@hpc{work}") for one in range(3))
    try:
        await asyncio.gather(probe(first), probe(second))
        with pytest.raises(ResourceUnmet, match="has 2 of the 2 jobs it may"):
            await probe(third)
    finally:
        for one in (first, second, third):
            await one.close()

    assert len(cluster.calls("sbatch")) == 2


def _submitted(host: str, pid: str) -> str:
    """A job a run on `host` as `pid` submitted to the cluster, and left there."""
    import subprocess

    said = (
        f"humanize={os.getuid()}",
        f"{PROVIDER}=hpc",
        f"{HOST}={host}",
        f"{PID}={pid}",
    )
    return subprocess.run(
        ["sbatch", "--wrap", "exec sleep 600", "--comment", "&".join(said)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@linux
async def test_a_job_a_dead_run_left_is_cancelled_by_the_next(
    cluster: Fakes, work: Path
) -> None:
    left = await asyncio.to_thread(_submitted, socket.gethostname(), "999999999")
    driver = _opened(f"work=slurm@hpc{work}")
    try:
        await probe(driver)
    finally:
        await driver.close()

    assert [left] in cluster.calls("scancel")

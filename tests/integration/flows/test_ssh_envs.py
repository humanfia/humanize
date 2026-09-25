"""The driver for a directory on a host reached with ssh, less the network.

A stand-in `ssh` on `PATH` is the one thing not real here: it skips ssh's options and runs
the line it was handed with this machine's `sh`, in a home of the test's own, which is what a
real `ssh` does on the far side. Everything else is the road a real host is reached by --
coganchor's zipapp bootstrapped into that home, its serving half speaking the wire protocol
over the pipe, and every command, file and copy going through it -- so the whole contract
runs, and so does what only this backend has: reaching nothing until asked, a home-relative
workdir, what a host that is not there or will not answer comes to, and a connection that
drops. `tests/system/flows/test_ssh_envs.py` runs the contract over a real `ssh localhost`.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path, PurePosixPath

import psutil
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
from hmz.runtime.flowing.environing_ssh import SSHMachine
from hmz.runtime.flowing.environments import open_env, probe
from hmz.runtime.flowing.specs import parse_envs
from tests.flows.contracts import check_env_driver

#: How long a command that is to be timed out is given first, so that it has started
#: everything it starts on however loaded a machine: what it started is what is checked.
_SETTLED = 3.0

#: What stands in for `ssh`: every host is this machine, except the two a test names to be
#: refused. Options are skipped the way ssh reads them, and every line it is asked to run is
#: logged, so that a test can see what reached the network and what did not.
_SSH = r"""#!/bin/sh
printf '%s\n' "$*" >> "$STANDIN_SSH_LOG"
while [ $# -gt 0 ]; do
  case $1 in
    -[bcDEeFIiJLlmOoPpQRSWw]) shift 2 ;;
    -*) shift ;;
    *) break ;;
  esac
done
host=$1; shift
case $host in
  nowhere*) echo "ssh: Could not resolve hostname $host: Name or service not known" >&2
            exit 255 ;;
  refusing*) echo "ssh: connect to host $host port 22: Connection refused" >&2
             exit 255 ;;
esac
HOME=$STANDIN_SSH_HOME
export HOME
exec /bin/sh -c "$*"
"""


@pytest.fixture
def far(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The home directory on the far side of the stand-in `ssh`, which it puts on `PATH`."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    ssh = bin_ / "ssh"
    ssh.write_text(_SSH)
    ssh.chmod(0o755)
    home = tmp_path / "far home"
    home.mkdir()
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("STANDIN_SSH_HOME", str(home))
    monkeypatch.setenv("STANDIN_SSH_LOG", str(tmp_path / "ssh.log"))
    return home


@pytest.fixture
def host(tmp_path: Path) -> str:
    """A host name of the test's own.

    coganchor bootstraps a host once per process and name, and each test's far side is a
    home of its own, so each test reaches a host of its own.
    """
    return f"standin-{tmp_path.name}"


def _open(host: str, workdir: Path | str) -> MachineEnvDriver:
    (spec,) = parse_envs([f"work=ssh@{host}/{str(workdir).lstrip('/')}"])
    driver = open_env(spec)
    assert isinstance(driver, MachineEnvDriver)
    return driver


def _mem_total() -> int:
    """The memory this machine's kernel says it has, as `/proc/meminfo` counts it."""
    meminfo = Path("/proc/meminfo").read_text().splitlines()
    (total,) = [line.split()[1] for line in meminfo if line.startswith("MemTotal:")]
    return int(total) * 1024


def _text(path: Path) -> str:
    """What a file holds, or "" while there is none."""
    try:
        return path.read_text()
    except FileNotFoundError:
        return ""


async def _pid_in(path: Path, within: float = 30.0) -> int:
    """The process id a command writes to a file, once it has."""
    for _ in range(int(within / 0.05)):
        if said := _text(path).strip():
            return int(said)
        await asyncio.sleep(0.05)
    pytest.fail(f"nothing was written to {path}")


def _reached(tmp_path: Path) -> list[str]:
    log = tmp_path / "ssh.log"
    return log.read_text().splitlines() if log.exists() else []


def _git(cwd: Path, *argv: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=tester@example.com",
            "-c",
            "user.name=tester",
            "-c",
            "commit.gpgsign=false",
            *argv,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.mark.timeout(120)
async def test_the_ssh_driver_keeps_the_contract(
    far: Path, host: str, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "file.txt").write_text("x\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "first")
    await check_env_driver(_open(host, repo), repo=True)


async def test_opening_one_reaches_nothing(
    far: Path, host: str, tmp_path: Path
) -> None:
    driver = _open(host, "/anywhere/at/all")
    assert driver.backend is EnvBackendKind.SSH
    assert driver.provider == host
    assert driver.workdir == PurePosixPath("/anywhere/at/all")
    assert not driver.available
    assert (driver.cpu_count, driver.memory, driver.gpu_count, driver.gpu_memory) == (
        1,
        0,
        0,
        0,
    )
    placement = driver.placement()
    assert isinstance(placement.machine, AnchoredConfig)
    assert placement.machine.anchor.target == f"ssh://{host}"
    assert placement.machine.anchor.workspace == "/anywhere/at/all"
    await driver.close()
    assert _reached(tmp_path) == []


@pytest.mark.timeout(120)
async def test_what_a_host_has_is_learned_when_it_is_probed(
    far: Path, host: str, tmp_path: Path
) -> None:
    driver = _open(host, tmp_path)
    try:
        await probe(driver)
        assert driver.available
        assert driver.cpu_count == len(os.sched_getaffinity(0))
        assert driver.memory == _mem_total()
        assert abs(driver.memory - psutil.virtual_memory().total) < 1024 * 1024
        assert driver.gpu_count >= 0
    finally:
        await driver.close()


@pytest.mark.timeout(120)
async def test_a_workdir_under_home_is_found_where_home_is_there(
    far: Path, host: str
) -> None:
    (far / "work").mkdir()
    driver = _open(host, "~/work")
    try:
        assert driver.workdir == PurePosixPath("~/work")
        before = driver.placement().machine
        assert isinstance(before, AnchoredConfig)
        assert before.anchor.remote_path == "~/work"
        await probe(driver)
        assert await driver.exec(["pwd"], timeout=30) == (0, f"{far}/work\n", "")
        await driver.write("made.txt", b"made")
        assert (far / "work/made.txt").read_bytes() == b"made"
        assert await driver.read("~/work/made.txt") == b"made"
        sub = await driver.derive_subdir("sub")
        assert sub.workdir == PurePosixPath("~/work/sub")
        assert (far / "work/sub").is_dir()
        after = driver.placement()
        assert after.workdir == PurePosixPath("~/work")
        assert isinstance(after.machine, AnchoredConfig)
        assert after.machine.anchor.workspace == f"{far}/work"
    finally:
        await driver.close()


@pytest.mark.timeout(120)
async def test_a_host_nothing_resolves_is_unavailable(
    far: Path, tmp_path: Path
) -> None:
    driver = _open(f"nowhere-{tmp_path.name}", "/tmp")
    with pytest.raises(EnvUnavailable, match="no ssh host"):
        await probe(driver)
    assert not driver.available
    with pytest.raises(EnvUnavailable):
        await driver.exec(["true"], timeout=10)


@pytest.mark.timeout(120)
async def test_a_host_that_will_not_answer_is_a_connection_error(
    far: Path, tmp_path: Path
) -> None:
    driver = _open(f"refusing-{tmp_path.name}", "/tmp")
    with pytest.raises(EnvConnectionError, match="Connection refused") as raised:
        await probe(driver)
    assert isinstance(raised.value, ConnectionError)
    assert not driver.available


def test_what_is_no_ssh_host_is_refused_where_it_is_named() -> None:
    for provider in ("-oProxyCommand=true", "a b", "host;true", ""):
        with pytest.raises(EnvUnavailable, match="not an ssh host"):
            SSHMachine(provider)


@pytest.mark.timeout(120)
async def test_a_workdir_that_is_not_there_is_unavailable(
    far: Path, host: str, tmp_path: Path
) -> None:
    driver = _open(host, tmp_path / "missing")
    try:
        with pytest.raises(EnvUnavailable, match="not there"):
            await probe(driver)
        assert not driver.available
        with pytest.raises(EnvUnavailable):
            await driver.exec(["true"], timeout=10)
    finally:
        await driver.close()


async def _gone(pid: int) -> bool:
    """Whether a process is gone, waiting a while for it to be."""
    for _ in range(200):
        try:
            if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                return True
        except psutil.NoSuchProcess:
            return True
        await asyncio.sleep(0.05)
    return False


@pytest.mark.timeout(120)
@pytest.mark.parametrize(
    "script",
    [
        pytest.param("sleep 30 & echo $! > child; wait", id="waiting-for-its-child"),
        pytest.param("sleep 30 & echo $! > child", id="gone-before-its-child"),
    ],
)
async def test_a_timeout_kills_everything_the_command_started_there(
    far: Path, host: str, tmp_path: Path, script: str
) -> None:
    driver = _open(host, tmp_path)
    try:
        with pytest.raises(EnvCommandTimeout):
            await driver.exec(script, timeout=_SETTLED)
        child = await _pid_in(tmp_path / "child")
        assert await _gone(child), "a command's child outlived its timeout"
    finally:
        await driver.close()


@pytest.mark.timeout(120)
async def test_what_cannot_be_read_there_says_why(
    far: Path, host: str, tmp_path: Path
) -> None:
    driver = _open(host, tmp_path)
    (tmp_path / "dir").mkdir()
    try:
        with pytest.raises(EnvFileNotFound):
            await driver.read("missing")
        with pytest.raises(EnvError) as raised:
            await driver.read("dir")
        assert not isinstance(raised.value, FileNotFoundError)
        with pytest.raises(EnvFileNotFound):
            await driver.exec(["no-such-program-anywhere"], timeout=10)
    finally:
        await driver.close()


@pytest.mark.timeout(120)
async def test_closing_the_root_kills_what_runs_there(
    far: Path, host: str, tmp_path: Path
) -> None:
    driver = _open(host, tmp_path)
    running = asyncio.create_task(
        driver.exec("sleep 30 & echo $! > child; wait", timeout=0)
    )
    child = await _pid_in(tmp_path / "child")
    await driver.close()
    with pytest.raises(EnvError, match="closed"):
        await running
    for _ in range(200):
        if not psutil.pid_exists(child) or (
            psutil.Process(child).status() == psutil.STATUS_ZOMBIE
        ):
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("a command outlived the driver it ran under")
    with pytest.raises(EnvError, match="is closed"):
        await driver.exec(["echo", "again"], timeout=30)
    assert not driver.available
    await driver.close()


@pytest.mark.timeout(120)
async def test_a_dropped_connection_is_made_again(
    far: Path, host: str, tmp_path: Path
) -> None:
    driver = _open(host, tmp_path)
    try:
        await probe(driver)
        machine = driver._machine
        assert isinstance(machine, SSHMachine)
        link = machine._link
        assert link is not None
        assert link.process is not None
        running = asyncio.create_task(driver.exec(["sleep", "30"], timeout=0))
        for _ in range(1000):
            if machine.running:
                break
            await asyncio.sleep(0.01)
        link.process.kill()
        with pytest.raises(EnvConnectionError):
            await running
        assert await driver.exec(["echo", "back"], timeout=30) == (0, "back\n", "")
        assert driver.available
    finally:
        await driver.close()

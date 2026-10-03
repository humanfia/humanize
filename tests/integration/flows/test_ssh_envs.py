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
from typing import TYPE_CHECKING, cast

import psutil
import pytest

from hmz.coganchor.machines import AnchoredConfig, store
from hmz.coganchor.machines.store import SSHRuntime
from hmz.coganchor.proto import path_key
from hmz.flows import (
    EnvBackendKind,
    EnvCommandTimeout,
    EnvConnectionError,
    EnvError,
    EnvFileNotFound,
    EnvUnavailable,
)
from hmz.runtime.flowing.environing import MachineEnvDriver
from hmz.runtime.flowing.environing_ssh import PROBE_SCRIPT, SSHMachine, facts_of
from hmz.runtime.flowing.environments import open_env, probe
from hmz.runtime.flowing.specs import parse_envs
from tests.flows.contracts import check_env_driver
from tests.stubs import CPUS

if TYPE_CHECKING:
    from hmz.runtime.flowing.spi import EnvDriver

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
    """The driver an `-e` naming `host` -- a saved runtime, or a host in brackets -- opens."""
    (spec,) = parse_envs([f"work=ssh@{host}/{str(workdir).lstrip('/')}"])
    driver = open_env(spec)
    assert isinstance(driver, MachineEnvDriver)
    return driver


def _mem_total() -> int:
    """The memory this machine's kernel says it has, as `/proc/meminfo` counts it.

    Or as `sysctl hw.memsize` does where there is no `/proc` (macOS), which is psutil's count.
    """
    if not Path("/proc/meminfo").exists():
        return int(psutil.virtual_memory().total)
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
    await check_env_driver(_open(f"[{host}]", repo), repo=True)


async def test_opening_one_reaches_nothing(
    far: Path, host: str, tmp_path: Path
) -> None:
    driver = _open(f"[{host}]", "/anywhere/at/all")
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
    driver = _open(f"[{host}]", tmp_path)
    try:
        await probe(driver)
        assert driver.available
        assert driver.cpu_count == CPUS
        assert driver.memory == _mem_total()
        assert abs(driver.memory - psutil.virtual_memory().total) < 1024 * 1024
        assert driver.gpu_count >= 0
    finally:
        await driver.close()


def _probed(home: Path, **env: str) -> PurePosixPath:
    """Where the probe, run by `sh` in a home of the test's own, says humanize's home is."""
    said = subprocess.run(
        ["/bin/sh", "-c", PROBE_SCRIPT],
        env={"PATH": os.environ["PATH"], "HOME": str(home), **env},
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout
    return facts_of(said).state


def test_the_probe_moves_a_home_kept_under_the_old_name(tmp_path: Path) -> None:
    (tmp_path / ".humanize" / "envs").mkdir(parents=True)

    assert _probed(tmp_path) == PurePosixPath(tmp_path / ".hmz")

    assert not (tmp_path / ".humanize").exists()
    assert (tmp_path / ".hmz" / "envs").is_dir()


def test_the_probe_leaves_both_where_both_are(tmp_path: Path) -> None:
    (tmp_path / ".humanize" / "old").mkdir(parents=True)
    (tmp_path / ".hmz" / "new").mkdir(parents=True)

    assert _probed(tmp_path) == PurePosixPath(tmp_path / ".hmz")

    assert (tmp_path / ".humanize" / "old").is_dir()
    assert sorted(one.name for one in (tmp_path / ".hmz").iterdir()) == ["new"]


def test_the_probe_moves_nothing_where_humanize_home_is_set_there(
    tmp_path: Path,
) -> None:
    (tmp_path / ".humanize").mkdir()

    state = _probed(tmp_path, HUMANIZE_HOME=str(tmp_path / "elsewhere"))

    assert state == PurePosixPath(tmp_path / "elsewhere")
    assert (tmp_path / ".humanize").is_dir()
    assert not (tmp_path / ".hmz").exists()


def test_the_probe_answers_where_the_old_home_cannot_be_moved(tmp_path: Path) -> None:
    """A home nobody may write in: the old directory stays, and the new one is the answer."""
    if os.geteuid() == 0:
        pytest.skip("root may write in a directory nobody may write in")
    (tmp_path / ".humanize").mkdir()
    tmp_path.chmod(0o555)
    try:
        assert _probed(tmp_path) == PurePosixPath(tmp_path / ".hmz")
        assert (tmp_path / ".humanize").is_dir()
    finally:
        tmp_path.chmod(0o755)


@pytest.mark.timeout(120)
async def test_a_workdir_under_home_is_found_where_home_is_there(
    far: Path, host: str
) -> None:
    (far / "work").mkdir()
    driver = _open(f"[{host}]", "~/work")
    try:
        assert driver.workdir == PurePosixPath("~/work")
        before = driver.placement().machine
        assert isinstance(before, AnchoredConfig)
        assert before.anchor.remote_path == "~/work"
        await probe(driver)
        # Whichever name for it the host's `pwd` prints: a Mac's says `/var` for `/private/var`.
        status, out, err = await driver.exec(["pwd"], timeout=30)
        assert (status, err) == (0, "")
        assert path_key(out.strip()) == path_key(f"{far}/work")
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
    driver = _open(f"[nowhere-{tmp_path.name}]", "/tmp")
    with pytest.raises(EnvUnavailable, match="no ssh host"):
        await probe(driver)
    assert not driver.available
    with pytest.raises(EnvUnavailable):
        await driver.exec(["true"], timeout=10)


@pytest.mark.timeout(120)
async def test_a_host_that_will_not_answer_is_a_connection_error(
    far: Path, tmp_path: Path
) -> None:
    driver = _open(f"[refusing-{tmp_path.name}]", "/tmp")
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
    driver = _open(f"[{host}]", tmp_path / "missing")
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
    driver = _open(f"[{host}]", tmp_path)
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
    driver = _open(f"[{host}]", tmp_path)
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
    driver = _open(f"[{host}]", tmp_path)
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
    driver = _open(f"[{host}]", tmp_path)
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


# ------------------------------------------------------------ a runtime written down


#: A flow whose one role is a machine it runs a command on, which writes a file there.
_WRITES = """
from hmz.flows import AgentCollection, Env, EnvCollection, FlowParams, ShellEnvMixin, flow


class Box(Env, ShellEnvMixin): ...


class Envs(EnvCollection):
    box: Box


@flow(agents=AgentCollection, envs=Envs, params=FlowParams)
async def writes(task, *, agents, envs, params, ctx):
    status, _, err = await envs["box"].exec(["sh", "-c", f"echo {task} > made.txt"])
    assert status == 0, err
"""


def _stored(host: str, name: str = "stored", **fields: object) -> SSHRuntime:
    """A runtime for the host of the test's own, told everything a runtime can say."""
    said: dict[str, object] = {
        "host": host,
        "user": "me",
        "port": 2222,
        "identity_file": "/keys/the key",
        "proxy_jump": "jump@bastion",
        "options": {"LogLevel": "ERROR"},
        **fields,
    }
    return cast("SSHRuntime", store.add(store.new("ssh", name, **said)))


@pytest.mark.timeout(120)
async def test_a_stored_runtime_is_reached_with_exactly_what_it_says(
    far: Path, host: str, tmp_path: Path
) -> None:
    _stored(host)
    driver = _open("stored", tmp_path)
    try:
        await probe(driver)
        assert await driver.exec(["echo", "there"], timeout=30) == (0, "there\n", "")
    finally:
        await driver.close()

    reached = _reached(tmp_path)
    assert reached
    for line in reached:
        assert line.startswith(
            '-o IdentityFile="/keys/the key" -o ProxyJump=jump@bastion -o LogLevel=ERROR '
            "-T -o BatchMode=no -o ServerAliveInterval=30 "
        ), line
        assert f" -p 2222 me@{host} " in line, line


def test_two_runtimes_at_one_host_do_not_ride_one_connection(host: str) -> None:
    from hmz.coganchor.transport import Road, Target

    told = (
        _stored(host),
        _stored(host, "other", identity_file="/keys/another"),
        SSHRuntime(name="plain", host=host, user="me", port=2222),
    )

    paths = {
        flag
        for provider in told
        for flag in Road.to(Target.parse(provider.target())).prefix
        if flag.startswith("ControlPath=")
    }

    assert len(paths) in (0, len(told)), (
        paths
    )  # none where reuse is off, else one apiece


@pytest.mark.timeout(180)
def test_a_flow_runs_on_a_stored_runtime_an_e_names(
    far: Path, host: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.cli import main
    from tests.stubs import written

    _stored(host)
    workdir = tmp_path / "there"
    workdir.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    flow = written(tmp_path / "flows", "writes", _WRITES)

    main(
        [
            "exec",
            "-f",
            str(flow),
            "-e",
            f"box=ssh@stored{workdir}",
            "-p",
            "budget.cost=1",
            "hello",
        ]
    )

    assert (workdir / "made.txt").read_text() == "hello\n"
    assert any(f"-p 2222 me@{host}" in line for line in _reached(tmp_path))


# ------------------------------------------------------------------------- falling back


def _exec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: str) -> Path:
    """Runs the flow that writes its task down, given `env`, from a project of its own.

    Returns:
      The project, which the run's epic is kept under.
    """
    from hmz.cli import main
    from tests.stubs import written

    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    monkeypatch.chdir(project)
    flow = written(tmp_path / "flows", "writes", _WRITES)
    main(["exec", "-f", str(flow), "-e", env, "-p", "budget.cost=1", "hello"])
    return project


@pytest.mark.timeout(180)
def test_a_run_falls_back_from_a_runtime_that_cannot_be_reached(
    far: Path,
    host: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hmz.runtime.epic import epics, read

    store.add(SSHRuntime(name="dead", host="nowhere-x", fallback=("ssh:alive",)))
    store.add(SSHRuntime(name="alive", host=host))
    workdir = tmp_path / "there"
    workdir.mkdir()

    project = _exec(tmp_path, monkeypatch, f"box=ssh@dead{workdir}")

    assert (workdir / "made.txt").read_text() == "hello\n"
    said = capsys.readouterr().err
    assert "ssh:dead cannot hold 'box'" in said, said
    assert "using ssh:alive" in said, said
    (ran,) = [read(one) for one in epics(project)]
    assert ran is not None
    assert ran.envs == (f"box=ssh@dead{workdir}",)
    assert ran.used == (f"box=ssh@alive{workdir}",)


@pytest.mark.timeout(180)
def test_a_runtime_fallen_back_to_does_not_fall_back_in_turn(
    far: Path,
    host: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store.add(SSHRuntime(name="first", host="nowhere-1", fallback=("ssh:second",)))
    store.add(SSHRuntime(name="second", host="nowhere-2", fallback=("ssh:alive",)))
    store.add(SSHRuntime(name="alive", host=host))
    workdir = tmp_path / "there"
    workdir.mkdir()

    with pytest.raises(SystemExit) as refused:
        _exec(tmp_path, monkeypatch, f"box=ssh@first{workdir}")

    assert refused.value.code == 2
    said = capsys.readouterr().err
    assert "ssh:first cannot hold 'box'" in said, said
    assert "ssh:second cannot hold 'box'" in said, said
    assert "alive" not in said, said
    assert not (workdir / "made.txt").exists()


@pytest.mark.timeout(180)
def test_an_e_naming_a_runtime_only_listed_as_a_fallback_walks_nothing(
    far: Path,
    host: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store.add(SSHRuntime(name="main", host=host, fallback=("ssh:spare",)))
    store.add(SSHRuntime(name="spare", host="nowhere-x"))
    workdir = tmp_path / "there"
    workdir.mkdir()

    with pytest.raises(SystemExit):
        _exec(tmp_path, monkeypatch, f"box=ssh@spare{workdir}")

    said = capsys.readouterr().err
    assert "cannot hold" not in said, said
    assert not (workdir / "made.txt").exists()


@pytest.mark.timeout(120)
async def test_a_runtime_short_of_what_a_role_asks_falls_back_into_the_next_ones_workdir(
    far: Path, host: str, tmp_path: Path
) -> None:
    from hmz.flows import ResourceUnmet
    from hmz.runtime.flowing.environments import settle

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    store.add(SSHRuntime(name="small", host=host, fallback=("ssh:big",)))
    store.add(SSHRuntime(name="big", host=host, workdir=str(elsewhere)))
    (spec,) = parse_envs([f"box=ssh@small{tmp_path}"])
    first = open_env(spec)
    told: list[str] = []

    def fits(driver: EnvDriver) -> None:
        if driver.provider == "small":
            raise ResourceUnmet("'box' needs 64 CPUs")

    held, driver = await settle(spec, first, fits=fits, moved=told.append)
    try:
        assert (held.provider, held.workdir) == ("big", PurePosixPath(elsewhere))
        # What an affinity is read off: the runtime that held it, not the one it left.
        assert (driver.backend, driver.provider) == (EnvBackendKind.SSH, "big")
        assert driver.available
        assert not first.available  # closed, once it could not hold the role
        assert told == [
            "ssh:small cannot hold 'box': 'box' needs 64 CPUs; using ssh:big"
        ]
    finally:
        await driver.close()


@pytest.mark.timeout(120)
async def test_a_runtime_with_no_fallback_list_refuses_as_it_always_has(
    far: Path, tmp_path: Path
) -> None:
    from hmz.runtime.flowing.environments import settle

    store.add(SSHRuntime(name="dead", host="nowhere-x"))
    (spec,) = parse_envs([f"box=ssh@dead{tmp_path}"])
    driver = open_env(spec)
    try:
        with pytest.raises(EnvError) as refused:
            await settle(spec, driver)
    finally:
        await driver.close()

    assert "cannot hold" not in str(refused.value)


@pytest.mark.timeout(180)
def test_a_runtime_that_refuses_the_workdir_as_it_is_opened_falls_back_too(
    far: Path,
    host: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store.add(
        store.DockerRuntime(
            name="remote", endpoint="tcp://10.0.0.3:2376", fallback=("ssh:alive",)
        )
    )
    store.add(SSHRuntime(name="alive", host=host))
    (far / "there").mkdir()

    _exec(tmp_path, monkeypatch, "box=docker@remote/~/there")

    assert (far / "there" / "made.txt").read_text() == "hello\n"
    said = capsys.readouterr().err
    assert "docker:remote cannot hold 'box'" in said, said
    assert "must be an absolute path" in said, said

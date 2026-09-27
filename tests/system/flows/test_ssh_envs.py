"""The ssh environment driver over a real `ssh`, to a real `sshd` on this machine.

`tests/integration/flows/test_ssh_envs.py` runs the whole driver against a stand-in `ssh`,
which is everything but ssh itself and the connection it makes. This is those two: coganchor's
zipapp bootstrapped over a real ssh connection, its serving half started through it, and the
driver contract run through what that opens -- with the master connection `ssh` keeps and
every command riding it, as a host far away would have it.

The host is `localhost` where ssh answers there without a password. Where it does not, it is
an `sshd` of the test's own, started on a loopback port with keys made for it and reached
through an `ssh` that is told about them -- nothing of the user's `~/.ssh` is read or written.
It skips, saying why, on a machine with neither.

What the contract derives lands in humanize's home on the far side, which for `localhost` is
the real `~/.humanize/envs` -- ssh carries none of this process's environment there -- so the
test removes what it made when it is done. The sshd of its own is told to take the test's
`HUMANIZE_HOME` instead.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import psutil
import pytest

from hmz import home
from hmz.runtime import Hmz
from hmz.runtime.flowing.environing import MachineEnvDriver, home_of
from hmz.runtime.flowing.environing_ssh import SSHMachine
from hmz.runtime.flowing.environments import open_env, probe
from hmz.runtime.flowing.specs import parse_envs
from tests.flows.contracts import check_env_driver

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The name the sshd of the test's own is reached by.
_ALIAS = "hmz-sshd-test"


def _unreachable() -> str | None:
    """Why `ssh localhost` does not answer without a password, or None when it does."""
    try:
        said = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                "localhost",
                "true",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"`ssh localhost` could not be run: {error}"
    if said.returncode:
        why = said.stderr.strip() or f"exit {said.returncode}"
        return f"passwordless ssh to localhost is not available ({why})"
    return None


def _free_port() -> int:
    with socket.socket() as probing:
        probing.bind(("127.0.0.1", 0))
        return int(probing.getsockname()[1])


def _keyed(at: Path) -> Path:
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(at)],
        check=True,
        capture_output=True,
    )
    return at


@pytest.fixture
def ssh_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A host a real `ssh` reaches without a password: localhost, or an sshd of our own."""
    why = _unreachable()
    if why is None:
        yield "localhost"
        return
    sshd = shutil.which("sshd") or shutil.which(
        "sshd", path="/usr/sbin:/usr/local/sbin"
    )
    if sshd is None or shutil.which("ssh-keygen") is None:
        pytest.skip(f"{why}, and there is no sshd here to start one of the test's own")
    at = tmp_path / "sshd"
    at.mkdir()
    host_key, client_key = _keyed(at / "host_key"), _keyed(at / "client_key")
    shutil.copy(f"{client_key}.pub", at / "authorized_keys")
    port = _free_port()
    (at / "sshd_config").write_text(
        f"Port {port}\nListenAddress 127.0.0.1\nHostKey {host_key}\n"
        f"AuthorizedKeysFile {at / 'authorized_keys'}\nPidFile {at / 'sshd.pid'}\n"
        "UsePAM no\nStrictModes no\nPasswordAuthentication no\n"
        "KbdInteractiveAuthentication no\nPubkeyAuthentication yes\n"
        "AcceptEnv HUMANIZE_HOME\n"
    )
    (at / "ssh_config").write_text(
        f"Host {_ALIAS}\n  HostName 127.0.0.1\n  Port {port}\n"
        f"  IdentityFile {client_key}\n  IdentitiesOnly yes\n"
        f"  UserKnownHostsFile {at / 'known_hosts'}\n  StrictHostKeyChecking no\n"
        f"  SetEnv HUMANIZE_HOME={home()}\n  LogLevel ERROR\n"
    )
    ssh = shutil.which("ssh")
    assert ssh is not None
    wrapper = at / "bin" / "ssh"
    wrapper.parent.mkdir()
    wrapper.write_text(f'#!/bin/sh\nexec {ssh} -F {at / "ssh_config"} "$@"\n')
    wrapper.chmod(0o755)
    server = subprocess.Popen(
        [sshd, "-D", "-e", "-f", str(at / "sshd_config")],
        stdout=subprocess.DEVNULL,
        stderr=(at / "sshd.log").open("w"),
    )
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                break
            except OSError:
                if server.poll() is not None or time.monotonic() > deadline:
                    said = (at / "sshd.log").read_text().strip()
                    pytest.skip(
                        f"{why}, and an sshd of the test's own would not start: {said}"
                    )
                time.sleep(0.1)
        monkeypatch.setenv("PATH", f"{wrapper.parent}{os.pathsep}{os.environ['PATH']}")
        yield _ALIAS
    finally:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


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


@pytest.mark.timeout(300)
async def test_the_ssh_driver_keeps_the_contract_over_real_ssh(
    ssh_host: str, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "file.txt").write_text("x\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "first")
    (spec,) = parse_envs([f"repo=ssh@{ssh_host}{repo}"])
    driver = open_env(spec)
    assert isinstance(driver, MachineEnvDriver)
    machine = driver._machine
    assert isinstance(machine, SSHMachine)
    try:
        await probe(driver)
        assert driver.available
        assert driver.cpu_count == len(os.sched_getaffinity(0))
        assert abs(driver.memory - psutil.virtual_memory().total) < 1 << 20
        await check_env_driver(driver, repo=True)
    finally:
        facts = machine._facts
        if facts is not None:
            shutil.rmtree(home_of(facts.state, PurePosixPath(repo)), ignore_errors=True)


@pytest.mark.timeout(300)
async def test_a_home_relative_workdir_over_real_ssh(ssh_host: str) -> None:
    (spec,) = parse_envs([f"home=ssh@{ssh_host}/~"])
    driver = open_env(spec)
    try:
        await probe(driver)
        status, out, _ = await driver.exec(["pwd"], timeout=60)
        assert (status, out.strip()) == (0, str(Path.home()))
        scratch = await driver.derive_scratch("real ssh")
        assert await scratch.exec("pwd", timeout=60) == (0, f"{scratch.workdir}\n", "")
        await driver.destroy_scratch("real ssh")
        gone = await driver.exec(["test", "-e", str(scratch.workdir)], timeout=60)
        assert gone[0] == 1, "a scratch directory outlived its removal"
    finally:
        await driver.close()


# ------------------------------------------------------------ a provider written down


@pytest.fixture
def ssh_config(ssh_host: str, tmp_path: Path) -> Path:
    """An ssh config naming the host, which is never the user's own.

    The sshd of the test's own already has one. `localhost` gets one of its own, pointing an
    alias at it and saying nothing else, so that what reaches it is ssh's defaults.
    """
    own = tmp_path / "sshd" / "ssh_config"
    if ssh_host == _ALIAS:
        return own
    written = tmp_path / "ssh_config"
    written.write_text(f"Host {_ALIAS}\n  HostName localhost\n")
    return written


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


@pytest.mark.timeout(120)
def test_an_ssh_config_is_imported_and_what_it_names_is_checked(
    ssh_config: Path,
) -> None:
    envs = Hmz().environments

    (resolved,) = envs.hosts(ssh_config)
    (imported,) = envs.import_ssh(ssh_config)
    checked = envs.check(imported, seconds=60)

    assert resolved.alias == _ALIAS
    assert resolved.host in ("127.0.0.1", "localhost")
    assert imported == envs.find("ssh", _ALIAS)
    assert (imported.alias, imported.config) == (_ALIAS, str(ssh_config))
    assert envs.resolve(imported).port == resolved.port
    assert checked.reached, checked.said
    assert checked.home == str(Path.home())
    assert checked.cpus == len(os.sched_getaffinity(0))
    assert abs(checked.memory - psutil.virtual_memory().total) < 1 << 20


@pytest.mark.timeout(300)
def test_a_flow_runs_end_to_end_on_a_provider_imported_from_a_config(
    ssh_config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.cli import main
    from tests.stubs import written

    Hmz().environments.import_ssh(ssh_config)
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
            f"box=ssh@{_ALIAS}{workdir}",
            "-b",
            "cost=1",
            "hello",
        ]
    )

    assert (workdir / "made.txt").read_text() == "hello\n"


@pytest.mark.timeout(180)
def test_a_docker_daemon_behind_an_imported_host_is_dialled_through_it(
    ssh_config: Path,
) -> None:
    """Docker's own ssh, told what the provider says by the `ssh` kept with it."""
    if shutil.which("docker") is None:
        pytest.skip("needs docker on the far side, which is this machine")
    envs = Hmz().environments
    envs.import_ssh(ssh_config)
    here = envs.check(envs.new("docker", "here"))
    if not here.reached:
        pytest.skip(f"needs a docker daemon: {here.said}")

    far = envs.check(envs.new("docker", "far", endpoint=f"ssh:{_ALIAS}"), seconds=90)

    assert far.reached, far.said
    assert (far.version, far.cpus, far.memory) == (here.version, here.cpus, here.memory)


#: An agent that starts a command as it comes up, leaving its stdin to it, and then reads its
#: first request -- as codex's app-server does, probing its sandbox before it reads a line.
_READS_AFTER_A_PROBE = (
    "import subprocess, sys\n"
    "subprocess.run(['/bin/true'])\n"
    "print('got', sys.stdin.readline().strip())\n"
)


@pytest.mark.timeout(120)
def test_an_agent_anchored_over_real_ssh_keeps_its_own_stdin(
    ssh_host: str, tmp_path: Path
) -> None:
    import sys

    from hmz.coganchor import AnchorConfig
    from tests.supervising import WITHOUT

    if WITHOUT:
        pytest.skip(WITHOUT)
    work = tmp_path / "work"
    work.mkdir()
    config = AnchorConfig(
        target=f"ssh://{ssh_host}", workspace=str(work), shadow=str(tmp_path / "mirror")
    )

    result = subprocess.run(
        [*config.command(["python3", "-c", _READS_AFTER_A_PROBE])],
        input="the first request\n",
        capture_output=True,
        text=True,
        timeout=90,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "got the first request"

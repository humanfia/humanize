"""The ssh environment driver over a real `ssh`, to a real `sshd` on this machine.

`tests/integration/flows/test_ssh_envs.py` runs the whole driver against a stand-in `ssh`,
which is everything but ssh itself and the connection it makes. This is those two: coganchor's
zipapp bootstrapped over a real ssh connection, its serving half started through it, and the
driver contract run through what that opens -- with the master connection `ssh` keeps and
every command riding it, as a host far away would have it.

The host is `tests.flows.sshd.ssh_host`: `localhost` where ssh answers there without a
password, and otherwise an `sshd` of the test's own, started on a loopback port with keys
made for it -- nothing of the user's `~/.ssh` is read or written. It skips, saying why, on a
machine with neither. The regression matrix runs a real agent's turn on the same host, which
is why the fixture is a helper both take back by name rather than a function written here.

What the contract derives lands in humanize's home on the far side, which for `localhost` is
the real `~/.humanize/envs` -- ssh carries none of this process's environment there -- so the
test removes what it made when it is done. The sshd of its own is told to take the test's
`HUMANIZE_HOME` instead.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path, PurePosixPath

import psutil
import pytest

from hmz.runtime.flowing.environing import MachineEnvDriver, home_of
from hmz.runtime.flowing.environing_ssh import SSHMachine
from hmz.runtime.flowing.environments import open_env, probe
from hmz.runtime.flowing.specs import parse_envs
from tests.flows.contracts import check_env_driver


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

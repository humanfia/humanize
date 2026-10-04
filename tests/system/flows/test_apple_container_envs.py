"""A flow's Apple container environment against Apple's own `container`: a Linux VM of its own.

`tests/integration/flows/test_apple_container_envs.py` runs the driver against a stand-in
`container`, which is everything but the virtual machine. This is that too. The image is
`python:3.12-slim`, which has no sshd: everything reaches into the container over `container
exec`. What is checked is where only the container could have answered -- that it is Linux on
this Mac, its own hostname, the size `container` says its virtual machine was given -- that the
workdir it was given is this user's directory, written as this user's files, and that the
container is gone once the environment is closed. And what a runtime shares out: what its
running containers hold, read back off `container list`, and one a run that died left behind,
taken down by the next.

Skipped on a machine where `container system status` does not answer, or that has not got the
image pulled: `container image pull python:3.12-slim`.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.machines import apple_container, store
from hmz.flows import (
    CPUEnvMixin,
    Env,
    EnvCollection,
    ImageEnvMixin,
    MemoryEnvMixin,
    ShellEnvMixin,
)
from hmz.runtime.flowing.declaring import env_roles
from hmz.runtime.flowing.environing_docker import PID, PROVIDER
from hmz.runtime.flowing.environments import open_env, probe
from hmz.runtime.flowing.specs import parse_envs
from tests.flows.contracts import check_env_driver
from tests.machines.fixtures import IMAGE

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from hmz.runtime.flowing.declaring import EnvRole
    from hmz.runtime.flowing.spi import EnvDriver


class Slim(Env, ShellEnvMixin, ImageEnvMixin):
    _image = IMAGE


class Limited(Env, ShellEnvMixin, CPUEnvMixin, MemoryEnvMixin, ImageEnvMixin):
    _image = IMAGE
    _cpu_count = 2
    _memory = 1 << 30


class Envs(EnvCollection):
    slim: Slim
    limited: Limited


def _role(name: str) -> EnvRole:
    (role,) = [one for one in env_roles(Envs, globals(), {}) if one.name == name]
    return role


def _listed() -> list[dict[str, Any]]:
    """Every container `container` has, running or not."""
    said = subprocess.run(
        ["container", "list", "--all", "--format", "json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(said.stdout or "[]")


def _labels(one: dict[str, Any]) -> dict[str, str]:
    return one["configuration"].get("labels") or {}


def _ours() -> list[str]:
    """Every container this process started that `container` still has, running or not."""
    return [
        one["configuration"]["id"]
        for one in _listed()
        if _labels(one).get(PID) == str(os.getpid())
    ]


@pytest.fixture(autouse=True)
def _leaves_no_container(apple: None) -> Iterator[None]:
    """Every test here takes down what it started: nothing of this process is left running."""
    del apple
    yield
    left = _ours()
    if left:
        subprocess.run(
            ["container", "delete", "--force", *left], capture_output=True, check=False
        )
    assert not left, f"containers left behind: {left}"


def _opened(spec: str, role: str) -> EnvDriver:
    (said,) = parse_envs([spec])
    return open_env(said, _role(role))


@pytest.mark.timeout(300)
async def test_the_contract_holds_in_an_apple_container_with_no_sshd(
    tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    driver = _opened(f"slim=apple-container@local{work}", "slim")

    await probe(driver)
    status, out, err = await driver.exec(
        ["sh", "-c", "uname -s; hostname; id -u; command -v sshd || echo no-sshd"],
        timeout=60,
    )
    await check_env_driver(driver)

    assert status == 0, err
    system, hostname, uid, sshd = out.split()
    assert sshd == "no-sshd", "the image has an sshd, and the test would prove nothing"
    assert (system, uid) == ("Linux", str(os.getuid()))
    assert hostname != platform.node()
    # Written in the container, through the mount, as this user's own file here.
    written = work / "contract" / "deep" / "a.bin"
    assert written.read_bytes() == b"bytes \x00\xff\n"
    assert written.stat().st_uid == os.getuid()
    assert _ours() == []


@pytest.mark.timeout(300)
async def test_what_a_role_declares_is_its_virtual_machines_size_and_is_counted(
    tmp_path: Path,
) -> None:
    driver = _opened(f"limited=apple-container@local{tmp_path}", "limited")
    try:
        await probe(driver)
        (mine,) = [one for one in _listed() if one["configuration"]["id"] in _ours()]
        held = apple_container.allocations({PROVIDER: "local"})
    finally:
        await driver.close()

    assert mine["configuration"]["resources"]["cpus"] == 2
    assert mine["configuration"]["resources"]["memoryInBytes"] == 1 << 30
    (counted,) = [one for one in held if one.name == mine["configuration"]["id"]]
    assert (counted.cpus, counted.memory) == (2.0, 1 << 30)
    assert (driver.cpu_count, driver.memory, driver.gpu_count) == (2, 1 << 30, 0)
    assert _ours() == []


def _left_behind(provider: str) -> str:
    """A container as a run of this user's on this host that has since died left it.

    Returns:
      Its name.
    """
    gone = subprocess.Popen(["true"])
    gone.wait()
    left = f"humanize-{provider}-stale"
    subprocess.run(
        [
            "container",
            "run",
            "--detach",
            "--progress",
            "none",
            "--name",
            left,
            "--label",
            f"humanize={os.getuid()}",
            "--label",
            f"{PROVIDER}={provider}",
            "--label",
            f"{PID}={gone.pid}",
            "--label",
            f"humanize.host={socket.gethostname()}",
            IMAGE,
            "sleep",
            "600",
        ],
        capture_output=True,
        check=True,
    )
    return left


def _deleted(name: str) -> None:
    subprocess.run(
        ["container", "delete", "--force", name], capture_output=True, check=False
    )


@pytest.mark.timeout(300)
async def test_a_container_a_run_that_died_left_behind_is_taken_down_by_the_next(
    tmp_path: Path,
) -> None:
    provider = f"left-{os.getpid()}"
    store.write(store.AppleContainerRuntime(name=provider))
    left = _left_behind(provider)
    driver = _opened(f"slim=apple-container@{provider}{tmp_path}", "slim")
    try:
        await probe(driver)
        names = [one["configuration"]["id"] for one in _listed()]
    finally:
        await driver.close()
        _deleted(left)

    assert left not in names
    assert _ours() == []

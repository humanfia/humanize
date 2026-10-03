"""A flow's swarm environment against a real swarm: a task of its own, wherever it landed.

`tests/integration/flows/test_swarm_envs.py` runs the driver against a stand-in `docker`, which
is everything but the swarm, its scheduler and the container. This is those. The image is
`python:3.12-slim`, and what is checked is where only a container the swarm placed could have
answered: `/.dockerenv`, the cgroup limits the service reserved, the service gone once the
environment is closed, and the scheduler's own refusal of a task no node has room for.

The swarm is the one this machine manages, so it needs to be a manager of an active one. A swarm
of more than this one node may put a task anywhere, where the test's workdir is not: there the
runtime called `local` is written down pinned to this node, which is what a swarm whose nodes do
not share a filesystem asks of its runtime anyway.

Reached as a manager elsewhere would be -- over ssh, through an ssh runtime written down with
everything an sshd of the test's own needs -- and with the node reached over ssh instead of
through the manager, by the runtime's `nodes`. Both are this machine, so the workdir is one path
on every side.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.machines import AnchoredConfig, store
from hmz.coganchor.transport import Target
from hmz.flows import (
    CPUEnvMixin,
    EnvBackendKind,
    EnvCollection,
    EnvUnavailable,
    FilesEnvMixin,
    ImageEnvMixin,
    MemoryEnvMixin,
    ResourceUnmet,
    ShellEnvMixin,
)
from hmz.flows import Env as _Env
from hmz.runtime.doing.runtimes import Runtimes
from hmz.runtime.flowing.declaring import env_roles
from hmz.runtime.flowing.environments import open_env, probe
from hmz.runtime.flowing.specs import parse_envs
from tests.flows.contracts import check_env_driver
from tests.machines.fixtures import IMAGE

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from hmz.runtime.flowing.declaring import EnvRole
    from hmz.runtime.flowing.spi import EnvDriver


class Slim(_Env, ShellEnvMixin, FilesEnvMixin, ImageEnvMixin):
    _image = IMAGE


class Limited(_Env, ShellEnvMixin, CPUEnvMixin, MemoryEnvMixin, ImageEnvMixin):
    _image = IMAGE
    _cpu_count = 2
    _memory = 1 << 30


class Huge(_Env, ShellEnvMixin, CPUEnvMixin, ImageEnvMixin):
    _image = IMAGE
    _cpu_count = 1000


class Envs(EnvCollection):
    slim: Slim
    limited: Limited
    huge: Huge


def _role(name: str) -> EnvRole:
    (role,) = [one for one in env_roles(Envs, globals(), {}) if one.name == name]
    return role


def _opened(spec: str, role: str) -> EnvDriver:
    (said,) = parse_envs([spec])
    return open_env(said, _role(role))


def _docker(*argv: str) -> str:
    return subprocess.run(
        ["docker", *argv], capture_output=True, text=True, check=False
    ).stdout


def _ours() -> list[str]:
    """Every service this process created that the swarm still has."""
    return _docker(
        "service",
        "ls",
        "--quiet",
        "--filter",
        "label=humanize",
        "--filter",
        f"label=humanize.pid={os.getpid()}",
    ).split()


@pytest.fixture
def swarm(daemon: None) -> str:
    """The constraint keeping a task on this node, the manager of an active swarm, or a skip."""
    said = json.loads(_docker("info", "--format", "{{json .Swarm}}") or "{}")
    if said.get("LocalNodeState") != "active" or not said.get("ControlAvailable"):
        pytest.skip("needs this machine to be a manager of an active docker swarm")
    return f"node.id=={said['NodeID']}"


@pytest.fixture
def local(swarm: str) -> Iterator[str]:
    """The swarm here as `-e` names it: `swarm`, or `swarm@local` pinned to this node.

    Pinned where the swarm has other nodes, by a runtime saved as `local`.
    """
    here = "swarm"
    if len(_docker("node", "ls", "--quiet").split()) > 1:
        store.write(store.SwarmRuntime(name="local", constraints=(swarm,)))
        here = "swarm@local"
    yield here
    left = _ours()
    if left:
        subprocess.run(
            ["docker", "service", "rm", *left], capture_output=True, check=False
        )
    assert not left, f"services left behind: {left}"


@pytest.mark.timeout(300)
async def test_the_contract_holds_in_a_task_the_swarm_placed(
    local: str, tmp_path: Path
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    driver = _opened(f"slim={local}{work}", "slim")

    await probe(driver)
    (service,) = _ours()
    status, out, _ = await driver.exec(
        ["sh", "-c", "id -u; test -f /.dockerenv && echo inside; pwd"], timeout=60
    )
    await check_env_driver(driver)

    assert status == 0
    assert out.split() == [str(os.getuid()), "inside", str(work)]
    assert driver.backend is EnvBackendKind.SWARM
    assert (work / "contract" / "deep" / "a.bin").read_bytes() == b"bytes \x00\xff\n"
    # Closed by the contract, and its service with it.
    assert _ours() == []
    assert service


@pytest.mark.timeout(300)
async def test_what_a_role_declares_is_reserved_and_is_the_limit(
    local: str, tmp_path: Path
) -> None:
    driver = _opened(f"limited={local}{tmp_path}", "limited")
    try:
        await probe(driver)
        (service,) = _ours()
        resources = json.loads(
            _docker(
                "service",
                "inspect",
                service,
                "--format",
                "{{json .Spec.TaskTemplate.Resources}}",
            )
        )
        status, out, err = await driver.exec(
            ["cat", "/sys/fs/cgroup/cpu.max", "/sys/fs/cgroup/memory.max"], timeout=60
        )
    finally:
        await driver.close()

    assert status == 0, err
    assert out.split() == ["200000", "100000", str(1 << 30)]
    for held in (resources["Reservations"], resources["Limits"]):
        assert (held["NanoCPUs"], held["MemoryBytes"]) == (2 * 10**9, 1 << 30)
    assert (driver.cpu_count, driver.memory, driver.gpu_count) == (2, 1 << 30, 0)
    assert _ours() == []


@pytest.mark.timeout(120)
async def test_a_task_no_node_has_room_for_is_refused_and_its_service_removed(
    local: str, tmp_path: Path
) -> None:
    driver = _opened(f"huge={local}{tmp_path}", "huge")
    began = time.monotonic()
    try:
        with pytest.raises(ResourceUnmet, match="no node of the swarm has 1000 CPUs"):
            await probe(driver)
    finally:
        await driver.close()

    # At once, rather than once the wait for a node is over: no node could ever hold it.
    assert time.monotonic() - began < 30
    assert _ours() == []


@pytest.mark.timeout(300)
async def test_a_runtime_running_all_the_tasks_it_may_refuses_another(
    swarm: str, local: str, tmp_path: Path
) -> None:
    store.write(store.SwarmRuntime(name="one", constraints=(swarm,), max_tasks=1))
    first = _opened(f"slim=swarm@one{tmp_path}", "slim")
    second = _opened(f"slim=swarm@one{tmp_path}", "slim")
    try:
        await probe(first)
        with pytest.raises(ResourceUnmet, match="runs 1 of the 1 tasks it may"):
            await probe(second)
    finally:
        await second.close()
        await first.close()
    assert _ours() == []


@pytest.mark.timeout(120)
async def test_a_workdir_the_node_has_not_got_is_refused(
    local: str, tmp_path: Path
) -> None:
    driver = _opened(f"slim={local}{tmp_path / 'nowhere'}", "slim")
    try:
        with pytest.raises(EnvUnavailable):
            await probe(driver)
    finally:
        await driver.close()
    assert _ours() == []


# ------------------------------------------------------------------------ swarms elsewhere


@pytest.mark.timeout(300)
@pytest.mark.parametrize("road", ["manager", "node"])
async def test_a_swarm_reached_over_ssh_holds_the_task(
    road: str, swarm: str, local: str, ssh_runtime: str, tmp_path: Path
) -> None:
    """The manager reached over ssh, or the node the task landed on reached over ssh."""
    name = f"far-{road}"
    store.write(
        store.SwarmRuntime(name=name, endpoint=ssh_runtime, constraints=(swarm,))
        if road == "manager"
        else store.SwarmRuntime(
            name=name,
            constraints=(swarm,),
            nodes={socket.gethostname(): ssh_runtime.removeprefix("ssh:")},
        )
    )
    work = tmp_path / "work"
    work.mkdir()
    driver = _opened(f"slim=swarm@{name}{work}", "slim")
    try:
        await probe(driver)
        placed = driver.placement().machine
        status, out, err = await driver.exec(
            ["sh", "-c", "id -u; test -f /.dockerenv && echo inside"], timeout=120
        )
        await driver.write("there.txt", b"written in a task elsewhere\n")
    finally:
        await driver.close()

    assert status == 0, err
    assert out.split() == [str(os.getuid()), "inside"]
    assert (work / "there.txt").read_text() == "written in a task elsewhere\n"
    assert isinstance(placed, AnchoredConfig)
    target = Target.parse(placed.anchor.target)
    assert str(target.endpoint).startswith("ssh://")
    assert _ours() == []


def test_a_check_says_the_swarm_and_its_nodes(swarm: str) -> None:
    del swarm
    said = Runtimes().check(store.SwarmRuntime(name="here"))

    assert said.reached, said.said
    assert said.version
    assert socket.gethostname() in said.nodes
    assert said.cpus >= 1
    assert said.memory > 0

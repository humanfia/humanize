"""The driver for a task of its own on a docker swarm, less the swarm.

A stand-in `docker` on `PATH`, written here, is the one thing not real: it writes down every
command line it is handed, answers a manager's questions -- `info`, `node ls`, `node inspect`,
`service ls`, `service inspect`, `service ps`, `inspect --type task` -- from what the test left
for it, and runs what `docker exec` would run on this machine instead of in a container. So the
whole driver contract runs through it, and so does what only this backend has: the service
created with what the role reserves, the node's daemon its container is reached through, a task
no node took refused as `ResourceUnmet`, a runtime's quota read off its services' labels, and
what a run that died left behind removed. `tests/system/flows/test_swarm_envs.py` runs it all
against a real swarm.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import transport
from hmz.coganchor.machines import store
from hmz.coganchor.transport import Endpoint
from hmz.flows import (
    CPUEnvMixin,
    Env,
    EnvBackendKind,
    EnvCollection,
    EnvUnavailable,
    FilesEnvMixin,
    GPUEnvMixin,
    ImageEnvMixin,
    MemoryEnvMixin,
    ResourceUnmet,
    ShellEnvMixin,
)
from hmz.runtime.flowing.declaring import env_roles
from hmz.runtime.flowing.environments import open_env, probe
from hmz.runtime.flowing.specs import parse_envs
from hmz.sdk import Hmz
from tests.flows.contracts import check_env_driver
from tests.machines.fixtures import containered

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.runtime.flowing.declaring import EnvRole
    from hmz.runtime.flowing.spi import EnvDriver


class Slim(Env, ShellEnvMixin, FilesEnvMixin, ImageEnvMixin):
    _image = "python:3.12-slim"


class Limited(Env, ShellEnvMixin, CPUEnvMixin, MemoryEnvMixin, GPUEnvMixin):
    _cpu_count = 2
    _memory = 1 << 30
    _gpu_count = 1


class Envs(EnvCollection):
    slim: Slim
    limited: Limited


#: The stand-in. Global flags are skipped the way docker's parser reads them -- every one of
#: them takes a value but `--tlsverify` -- so the subcommand is found wherever it is.
_STANDIN = """\
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["STANDIN_LOG"], "a") as log:
    log.write(json.dumps(argv) + "\\n")
at = 0
while argv[at].startswith("-"):
    at += 1 if argv[at] == "--tlsverify" else 2
command, rest = argv[at], argv[at + 1 :]
said = lambda name, default: os.environ.get(name, default)
if command == "info":
    print(json.dumps({
        "ServerVersion": "stand-in",
        "NCPU": 8,
        "MemTotal": 16 << 30,
        "Swarm": {
            "LocalNodeState": said("STANDIN_STATE", "active"),
            "ControlAvailable": said("STANDIN_CONTROL", "1") == "1",
            "NodeID": "mgr",
        },
    }))
elif command == "node" and rest[0] == "ls":
    print("\\n".join(one["ID"] for one in json.loads(said("STANDIN_NODES", "[]"))))
elif command == "node" and rest[0] == "inspect":
    nodes = json.loads(said("STANDIN_NODES", "[]"))
    print(json.dumps([one for one in nodes if one["ID"] in rest[1:]]))
elif command == "service" and rest[0] == "create":
    if "STANDIN_REFUSE" in os.environ:
        sys.exit("Error response from daemon: rpc error: no such image")
    print("svc0")
elif command == "service" and rest[0] == "ps":
    print("task0")
elif command == "inspect" and "task" in rest:
    print(json.dumps([json.loads(said("STANDIN_TASK", "{}"))]))
elif command == "service" and rest[0] == "ls":
    print(said("STANDIN_SERVICES", ""))
elif command == "service" and rest[0] == "inspect":
    print(said("STANDIN_INSPECT", "[]"))
elif command == "run" and "--rm" in rest:
    print(said("STANDIN_OWNER", "4242 4343"))
elif command == "exec":
    os.environ["PATH"] = os.environ["STANDIN_CONTAINER"] + os.pathsep + os.environ["PATH"]
    moved = os.environ["STANDIN_ROOT"]
    words = [word.replace("/tmp/humanize", moved) for word in rest[2:]]
    os.execvp(words[0], words)
"""


def _node(
    id_: str, hostname: str, address: str, cpus: int = 8, gpus: int = 0
) -> dict[str, Any]:
    """A node as `docker node inspect` says one."""
    generic = (
        [{"DiscreteResourceSpec": {"Kind": "NVIDIA-GPU", "Value": gpus}}]
        if gpus
        else []
    )
    return {
        "ID": id_,
        "Spec": {"Availability": "active", "Role": "worker"},
        "Description": {
            "Hostname": hostname,
            "Resources": {
                "NanoCPUs": cpus * 10**9,
                "MemoryBytes": 16 << 30,
                "GenericResources": generic,
            },
        },
        "Status": {"State": "ready", "Addr": address},
    }


def _running(node: str) -> str:
    """A task that is running on a node, as `docker inspect --type task` says one."""
    return json.dumps(
        {
            "NodeID": node,
            "Status": {
                "State": "running",
                "ContainerStatus": {"ContainerID": "c0ffee"},
            },
        }
    )


class _Swarm:
    """The stand-in on `PATH`, and what it was asked."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.log = tmp_path / "docker.log"
        self.monkeypatch = monkeypatch

    def set(self, name: str, value: str) -> None:
        self.monkeypatch.setenv(name, value)

    def asked(self) -> list[list[str]]:
        """Every call so far, each its words after `docker` and its global flags."""
        if not self.log.exists():
            return []
        found: list[list[str]] = []
        for line in self.log.read_text().splitlines():
            argv: list[str] = json.loads(line)
            at = 0
            while argv[at].startswith("-"):
                at += 1 if argv[at] == "--tlsverify" else 2
            found.append(argv[at:])
        return found

    def hosts(self, command: str) -> list[str]:
        """The `--host` each call of one subcommand was given, or "" for none."""
        said: list[str] = []
        for line in self.log.read_text().splitlines():
            argv: list[str] = json.loads(line)
            at = 0
            while argv[at].startswith("-"):
                at += 1 if argv[at] == "--tlsverify" else 2
            if argv[at] == command:
                said.append(argv[argv.index("--host") + 1] if "--host" in argv else "")
        return said


@pytest.fixture
def swarm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Swarm:
    """A `docker` standing in for a swarm's manager, first on `PATH`, its task on the manager."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    docker = bin_ / "docker"
    docker.write_text(f"#!{sys.executable}\n{_STANDIN}")
    docker.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("STANDIN_LOG", str(tmp_path / "docker.log"))
    monkeypatch.setenv("STANDIN_ROOT", str(tmp_path / "container-tmp"))
    containered(tmp_path / "container-bin", monkeypatch)
    monkeypatch.setenv(
        "STANDIN_NODES",
        json.dumps(
            [
                _node("mgr", "manager", "10.0.0.1"),
                _node("w1", "worker1", "10.0.0.2", gpus=2),
            ]
        ),
    )
    monkeypatch.setenv("STANDIN_TASK", _running("mgr"))
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.setattr(transport, "_PUSHED", set[tuple[str, str]]())
    return _Swarm(tmp_path, monkeypatch)


def _role(name: str) -> EnvRole:
    (role,) = [one for one in env_roles(Envs, globals(), {}) if one.name == name]
    return role


def _opened(spec: str, role: str) -> EnvDriver:
    (said,) = parse_envs([spec])
    return open_env(said, _role(role))


def _value(argv: list[str], flag: str) -> list[str]:
    """Every value `flag` was given in one argv."""
    return [argv[at + 1] for at, word in enumerate(argv[:-1]) if word == flag]


def _created(swarm: _Swarm) -> list[str]:
    (made,) = [one for one in swarm.asked() if one[:2] == ["service", "create"]]
    return made


async def test_the_contract_holds_in_a_task_on_the_manager(
    swarm: _Swarm, tmp_path: Path
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    driver = _opened(f"slim=swarm{work}", "slim")

    await probe(driver)
    await check_env_driver(driver)

    assert driver.backend is EnvBackendKind.SWARM
    made = _created(swarm)
    assert _value(made, "--mount") == [f"type=bind,source={work},target={work}"]
    assert _value(made, "--user") == [f"{os.getuid()}:{os.getgid()}"]
    assert _value(made, "--restart-condition") == ["none"]
    assert _value(made, "--replicas") == ["1"]
    assert "--cap-add" not in made
    labels = dict(one.split("=", 1) for one in _value(made, "--label"))
    assert labels["humanize.provider"] == "local"
    assert labels["humanize.role"] == "slim"
    assert labels["humanize.pid"] == str(os.getpid())
    assert labels["humanize.host"] == socket.gethostname()
    # Reached through the manager's own daemon, the task having landed on the manager.
    assert set(swarm.hosts("exec")) == {""}
    assert swarm.asked()[-1] == ["service", "rm", "svc0"]


async def test_what_a_role_declares_is_reserved_limited_and_constrained(
    swarm: _Swarm, tmp_path: Path
) -> None:
    store.write(
        store.SwarmRuntime(
            name="cluster",
            gpu_resource="NVIDIA-GPU",
            constraints=("node.labels.gpu==true",),
            run_args=("--no-resolve-image",),
        )
    )
    driver = _opened(f"limited=swarm@cluster{tmp_path}", "limited")
    try:
        await probe(driver)
        had = (driver.cpu_count, driver.memory, driver.gpu_count)
    finally:
        await driver.close()

    made = _created(swarm)
    assert _value(made, "--reserve-cpu") == _value(made, "--limit-cpu") == ["2"]
    assert _value(made, "--reserve-memory") == [str(1 << 30)]
    assert _value(made, "--limit-memory") == [str(1 << 30)]
    assert _value(made, "--generic-resource") == ["NVIDIA-GPU=1"]
    assert _value(made, "--constraint") == ["node.labels.gpu==true"]
    assert "--no-resolve-image" in made
    assert had == (2, 1 << 30, 1)


@pytest.mark.parametrize(
    ("nodes", "host"),
    [
        ({}, "ssh://10.0.0.2"),
        ({"worker1": "me@w1.example:2222"}, "ssh://me@w1.example:2222"),
    ],
)
async def test_a_task_on_another_node_is_reached_over_ssh_to_that_node(
    swarm: _Swarm, tmp_path: Path, nodes: dict[str, str], host: str
) -> None:
    store.write(store.SwarmRuntime(name="cluster", nodes=nodes))
    swarm.set("STANDIN_TASK", _running("w1"))
    driver = _opened(f"slim=swarm@cluster{tmp_path}", "slim")
    try:
        await probe(driver)
        status, out, _ = await driver.exec(["echo", "there"], timeout=60)
    finally:
        await driver.close()

    assert (status, out) == (0, "there\n")
    # Created on the manager, and reached on the node.
    assert set(swarm.hosts("service")) == {""}
    assert set(swarm.hosts("exec")) == {host}


async def test_a_node_named_after_a_saved_ssh_host_is_dialled_as_it_says(
    swarm: _Swarm, tmp_path: Path
) -> None:
    store.write(store.SSHRuntime(name="w1", host="w1.example", user="me"))
    store.write(store.SwarmRuntime(name="cluster", nodes={"worker1": "w1"}))
    swarm.set("STANDIN_TASK", _running("w1"))
    driver = _opened(f"slim=swarm@cluster{tmp_path}", "slim")
    try:
        await probe(driver)
    finally:
        await driver.close()

    assert set(swarm.hosts("exec")) == {"ssh://me@w1.example"}


#: A task the scheduler has found no node for.
_PENDING = json.dumps(
    {
        "Status": {
            "State": "pending",
            "Err": "no suitable node (insufficient resources on 2 nodes)",
        }
    }
)


async def test_a_task_no_node_can_ever_take_is_refused_at_once(
    swarm: _Swarm, tmp_path: Path
) -> None:
    swarm.set("STANDIN_TASK", _PENDING)
    # No node advertises a GPU, so none could ever take a task reserving one.
    swarm.set("STANDIN_NODES", json.dumps([_node("mgr", "manager", "10.0.0.1")]))
    store.write(store.SwarmRuntime(name="cluster", gpu_resource="NVIDIA-GPU"))
    driver = _opened(f"limited=swarm@cluster{tmp_path}", "limited")
    try:
        with pytest.raises(ResourceUnmet) as refused:
            await probe(driver)
    finally:
        await driver.close()

    said = str(refused.value)
    assert said.startswith("swarm@cluster: no node of the swarm has 2 CPUs and ")
    assert "1 NVIDIA-GPU" in said
    assert "(no suitable node (insufficient resources on 2 nodes))" in said
    assert swarm.asked()[-1] == ["service", "rm", "svc0"]


def test_a_task_left_pending_is_given_up_on_once_its_wait_is_over(
    swarm: _Swarm, tmp_path: Path
) -> None:
    from hmz.coganchor.machines import SwarmConfig
    from hmz.coganchor.machines.swarm import Unplaced

    swarm.set("STANDIN_TASK", _PENDING)
    machine = SwarmConfig(workspace=str(tmp_path), cpus=2, placing=0.5).create()

    with pytest.raises(Unplaced, match=r"no node took it within 0.5s: no suitable"):
        machine.start()
    assert swarm.asked()[-1] == ["service", "rm", "svc0"]


async def test_a_workdir_the_node_has_not_got_is_unavailable(
    swarm: _Swarm, tmp_path: Path
) -> None:
    swarm.set(
        "STANDIN_TASK",
        json.dumps(
            {
                "NodeID": "w1",
                "Status": {
                    "State": "rejected",
                    "Err": 'invalid mount config for type "bind": bind source path '
                    "does not exist: /srv/repo",
                },
            }
        ),
    )
    driver = _opened(f"slim=swarm{tmp_path}", "slim")
    try:
        with pytest.raises(EnvUnavailable, match="no directory to give the task"):
            await probe(driver)
    finally:
        await driver.close()
    assert swarm.asked()[-1] == ["service", "rm", "svc0"]


@pytest.mark.parametrize(
    ("state", "control", "said"),
    [("inactive", "1", "in no active swarm"), ("active", "0", "is a worker")],
)
async def test_a_daemon_that_manages_no_swarm_is_unavailable(
    swarm: _Swarm, tmp_path: Path, state: str, control: str, said: str
) -> None:
    swarm.set("STANDIN_STATE", state)
    swarm.set("STANDIN_CONTROL", control)
    driver = _opened(f"slim=swarm{tmp_path}", "slim")
    try:
        with pytest.raises(EnvUnavailable, match=said):
            await probe(driver)
    finally:
        await driver.close()
    assert not any(one[:2] == ["service", "create"] for one in swarm.asked())


def _service(name: str, pid: int, cpus: str = "") -> dict[str, Any]:
    labels = {
        "humanize": str(os.getuid()),
        "humanize.provider": "cluster",
        "humanize.role": "slim",
        "humanize.host": socket.gethostname(),
        "humanize.pid": str(pid),
    }
    if cpus:
        labels["humanize.cpus"] = cpus
    return {"ID": name, "Spec": {"Name": name, "Labels": labels}}


async def test_a_runtime_short_of_what_a_role_asks_refuses_it_naming_who_holds_it(
    swarm: _Swarm, tmp_path: Path
) -> None:
    store.write(
        store.SwarmRuntime(name="cluster", cpus=3, max_tasks=1, gpu_resource="")
    )
    swarm.set("STANDIN_SERVICES", "held")
    swarm.set("STANDIN_INSPECT", json.dumps([_service("held", os.getpid(), "2")]))
    driver = _opened(f"limited=swarm@cluster{tmp_path}", "limited")
    try:
        with pytest.raises(ResourceUnmet) as refused:
            await probe(driver)
    finally:
        await driver.close()

    said = str(refused.value)
    assert "runs 1 of the 1 tasks it may" in said
    assert "has 1 of 3 CPUs free, and 'limited' asks for 2" in said
    assert "2 CPUs held by held" in said
    assert "hands out no GPUs" in said
    assert not any(one[:2] == ["service", "create"] for one in swarm.asked())


async def test_a_service_whose_run_is_gone_is_removed_by_the_next(
    swarm: _Swarm, tmp_path: Path
) -> None:
    store.write(store.SwarmRuntime(name="cluster", max_tasks=1))
    gone = 2**22 + 12345  # no pid this machine hands out
    swarm.set("STANDIN_SERVICES", "left")
    swarm.set("STANDIN_INSPECT", json.dumps([_service("left", gone)]))
    driver = _opened(f"slim=swarm@cluster{tmp_path}", "slim")
    try:
        await probe(driver)
    finally:
        await driver.close()

    asked = swarm.asked()
    assert ["service", "rm", "left"] in asked
    assert any(one[:2] == ["service", "create"] for one in asked)


def test_a_swarm_checked_says_its_nodes_and_what_they_have(swarm: _Swarm) -> None:
    del swarm
    checked = Hmz().runtimes.check(
        store.SwarmRuntime(name="cluster", cpus=64, gpu_resource="TPU")
    )

    assert checked.reached, checked.said
    assert checked.version == "stand-in"
    assert checked.nodes == ("manager", "worker1")
    assert (checked.cpus, checked.memory) == (16.0, 32 << 30)
    assert checked.short == (
        "it is to hand out 64 CPUs and has 16",
        "no node advertises TPU",
    )


def test_a_daemon_in_no_swarm_is_checked_as_not_reached(swarm: _Swarm) -> None:
    swarm.set("STANDIN_STATE", "inactive")
    checked = Hmz().runtimes.check(store.SwarmRuntime(name="cluster"))

    assert not checked.reached
    assert "in no active swarm" in checked.said


def test_an_endpoint_elsewhere_names_the_manager_every_time(swarm: _Swarm) -> None:
    checked = Hmz().runtimes.check(
        store.SwarmRuntime(name="cluster", endpoint="tcp://10.0.0.1:2376")
    )

    assert checked.reached, checked.said
    assert set(swarm.hosts("info")) | set(swarm.hosts("node")) == {
        str(Endpoint.parse("tcp://10.0.0.1:2376"))
    }

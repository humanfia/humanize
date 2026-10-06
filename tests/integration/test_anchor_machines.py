"""Machines started for an agent -- a docker container, a swarm task, an Apple container.

Against the fake `docker` and `container` in `doubles_anchor`: what they are asked is written
down, what the drivers read back is answered, and a container's `exec` runs here. So a
machine that comes up is reached for real, over coganchor's road, and asked what it is --
which is where a fake container on a Mac says `darwin` where a container must say `linux`.
That one refusal is checked on a Mac, and the machine coming up on Linux.
"""

from __future__ import annotations

import json
import os
import sys
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.machines import (
    AppleContainerConfig,
    DockerConfig,
    SwarmConfig,
    allocations,
    info,
)
from hmz.coganchor.machines import apple_container as apple
from hmz.coganchor.machines.docker import CPUS, GPUS, MEMORY, whose
from hmz.coganchor.machines.swarm import Unplaced, nodes, services
from hmz.coganchor.transport import Endpoint
from tests.integration.doubles_anchor import Fakes, fakes

if TYPE_CHECKING:
    from pathlib import Path

#: A fake container is this machine, so it says this machine's platform when it is asked.
linux = pytest.mark.skipif(
    sys.platform != "linux",
    reason="a fake container is this machine, which says it is not the linux one promised",
)
not_linux = pytest.mark.skipif(
    sys.platform == "linux",
    reason="a fake container on linux says linux, as promised, so it is not refused",
)


@pytest.fixture
def far(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fakes:
    """Fake `docker` and `container` on `PATH`, with a daemon that says it is one."""
    made = fakes(tmp_path, monkeypatch)
    made.answer("info", json.dumps({"ServerVersion": "27.0", "NCPU": 8}))
    return made


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    held = tmp_path / "project"
    held.mkdir()
    (held / "a.txt").write_text("a")
    return held


def _flag(argv: list[str], flag: str) -> list[str]:
    """Every value `flag` was given in `argv`."""
    return [argv[at + 1] for at, word in enumerate(argv) if word == flag]


def _run_of(far: Fakes, tool: str = "docker") -> list[str]:
    (argv,) = [
        one for one in far.calls(tool) if one[:1] == ["run"] and "--detach" in one
    ]
    return argv


def test_a_daemon_says_what_it_has(far: Fakes) -> None:
    assert info()["ServerVersion"] == "27.0"


def test_a_daemon_reporting_errors_is_one_that_could_not_be_asked(far: Fakes) -> None:
    far.answer("info", json.dumps({"ServerErrors": ["daemon is not running"]}))

    with pytest.raises(OSError, match="daemon is not running"):
        info()


def test_what_humanizes_containers_hold_is_read_off_their_labels(far: Fakes) -> None:
    far.answer("ps", "c1\nc2\n")
    far.answer(
        "inspect",
        json.dumps(
            [
                {
                    "Name": "/one",
                    "Config": {
                        "Labels": {
                            "humanize": "501",
                            CPUS: "2",
                            MEMORY: "1024",
                            GPUS: "0,1",
                        }
                    },
                },
                {
                    "Name": "/two",
                    "Config": {"Labels": {"humanize": "501", GPUS: "all"}},
                },
            ]
        ),
    )

    held = allocations("tcp://10.0.0.5:2376", {"humanize.provider": "box"})

    assert [(one.name, one.cpus, one.memory, one.gpus) for one in held] == [
        ("one", 2.0, 1024, ("0", "1")),
        ("two", None, None, "all"),
    ]
    (ps,) = [one for one in far.calls("docker") if "ps" in one]
    assert ps[:2] == ["--host", "tcp://10.0.0.5:2376"]
    assert _flag(ps, "--filter") == ["label=humanize", "label=humanize.provider=box"]


def test_a_daemon_running_none_of_ours_holds_nothing(far: Fakes) -> None:
    assert allocations() == []
    assert not [one for one in far.calls("docker") if one[:1] == ["inspect"]]


def test_a_daemon_that_cannot_list_is_said_so(far: Fakes) -> None:
    far.answer("ps", stderr="permission denied", status=1)

    with pytest.raises(OSError, match="permission denied"):
        allocations()


def test_whose_a_remote_workspace_is_is_asked_of_a_container_given_it(
    far: Fakes, workspace: Path
) -> None:
    held = workspace.stat()

    said = whose(Endpoint.parse("tcp://10.0.0.5:2376"), "img:1", str(workspace), dict)

    assert said == f"{held.st_uid}:{held.st_gid}"
    (asked,) = [one for one in far.calls("docker") if "run" in one]
    assert "--rm" in asked
    assert _flag(asked, "--network") == ["none"]
    assert _flag(asked, "--mount") == [
        f"type=bind,source={workspace},target={workspace}"
    ]


def test_a_remote_workspace_its_host_lacks_is_not_found(far: Fakes) -> None:
    far.answer(
        "run",
        stderr="invalid mount config: bind source path does not exist: /nope",
        status=125,
    )

    with pytest.raises(FileNotFoundError):
        whose(Endpoint.parse("tcp://10.0.0.5:2376"), "img:1", "/nope", dict)


def test_a_container_that_will_not_start_says_what_docker_said(
    far: Fakes, workspace: Path
) -> None:
    far.answer("run", stderr="pull access denied for nonesuch", status=125)
    machine = DockerConfig(image="nonesuch", workspace=str(workspace)).create()

    with pytest.raises(RuntimeError, match="pull access denied for nonesuch"):
        machine.start()

    assert not [one for one in far.calls("docker") if one[:1] == ["rm"]]


def test_a_container_needs_a_workspace_to_hold(far: Fakes, tmp_path: Path) -> None:
    machine = DockerConfig(workspace=str(tmp_path / "missing")).create()

    with pytest.raises(FileNotFoundError):
        machine.start()
    assert not far.calls("docker")


def test_a_container_needs_a_docker_to_run_it(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "/nonexistent")

    with pytest.raises(FileNotFoundError, match="docker"):
        DockerConfig(workspace=str(workspace)).create().start()


def _docker(workspace: Path, **settings: Any) -> DockerConfig:
    return DockerConfig(
        image="img:1",
        workspace=str(workspace),
        name="held",
        cpus=1.5,
        memory=1 << 30,
        labels={"team": "a", "humanize": "forged"},
        env={"FOO": "bar"},
        **settings,
    )


def _started_with(far: Fakes, workspace: Path) -> None:
    argv = _run_of(far)
    assert _flag(argv, "--name") == ["held"]
    labels = _flag(argv, "--label")
    assert f"humanize={os.getuid()}" in labels
    assert "humanize=forged" not in labels
    assert {"team=a", f"{CPUS}=1.5", f"{MEMORY}={1 << 30}"} <= set(labels)
    assert _flag(argv, "--cpus") == ["1.5"]
    assert _flag(argv, "--memory") == [str(1 << 30)]
    assert _flag(argv, "--workdir") == [str(workspace)]
    assert "FOO=bar" in _flag(argv, "--env")
    assert "img:1" in argv


@linux
def test_a_container_is_started_reached_and_removed(
    far: Fakes, workspace: Path
) -> None:
    machine = _docker(workspace).create()

    anchor = machine.start()
    try:
        assert anchor.target == "docker://held"
        assert anchor.workspace == str(workspace)
        assert "linux" in machine.capabilities
        _started_with(far, workspace)
        assert ["exec", "-i", "held"] in [one[:3] for one in far.calls("docker")]
    finally:
        machine.stop()

    assert ["rm", "--force", "cid-held"] in far.calls("docker")


@not_linux
def test_a_container_that_is_not_linux_is_refused_and_removed(
    far: Fakes, workspace: Path
) -> None:
    machine = _docker(workspace).create()

    with pytest.raises(RuntimeError, match="cannot serve linux"):
        machine.start()

    _started_with(far, workspace)
    assert ["rm", "--force", "cid-held"] in far.calls("docker")


def _node(node_id: str, hostname: str, **status: Any) -> dict[str, Any]:
    return {
        "ID": node_id,
        "Spec": {"Availability": "active"},
        "Description": {
            "Hostname": hostname,
            "Resources": {
                "NanoCPUs": 4_000_000_000,
                "MemoryBytes": 8 << 30,
                "GenericResources": [
                    {"DiscreteResourceSpec": {"Kind": "gpu", "Value": 2}}
                ],
            },
        },
        "Status": {"State": "ready", "Addr": "10.0.0.7", **status},
    }


def test_a_swarms_nodes_are_read_off_its_manager(far: Fakes) -> None:
    far.answer("node ls", "n1\nn2\n")
    far.answer(
        "node inspect",
        json.dumps([_node("n1", "alpha"), _node("n2", "beta", State="down")]),
    )

    found = nodes()

    assert [(one.hostname, one.ready, one.cpus, one.memory) for one in found] == [
        ("alpha", True, 4.0, 8 << 30),
        ("beta", False, 4.0, 8 << 30),
    ]
    assert found[0].resources == {"gpu": 2}
    assert found[0].address == "10.0.0.7"


def test_what_humanizes_services_hold_is_read_off_their_labels(far: Fakes) -> None:
    far.answer("service ls", "s1\n")
    far.answer(
        "service inspect",
        json.dumps(
            [
                {
                    "Spec": {
                        "Name": "svc",
                        "Labels": {"humanize": "1", CPUS: "2", GPUS: "gpu=1"},
                    }
                }
            ]
        ),
    )

    (held,) = services()

    assert (held.name, held.cpus, held.gpus) == ("svc", 2.0, ("gpu=1",))


def _swarm(far: Fakes, state: str = "running", err: str = "") -> None:
    """A swarm this machine manages, whose one task is in `state`."""
    far.answer(
        "info",
        json.dumps(
            {
                "ServerVersion": "27.0",
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
                        "State": state,
                        "Err": err,
                        "ContainerStatus": {"ContainerID": "box-1"},
                    },
                }
            ]
        ),
    )
    far.answer("node inspect", json.dumps([_node("n1", "alpha")]))
    far.answer("node ls", "n1\n")


def _swarm_config(
    workspace: Path, *, cpus: float = 1.0, traced: bool = False
) -> SwarmConfig:
    return SwarmConfig(
        image="img:1",
        workspace=str(workspace),
        name="svc",
        user="1:1",
        cpus=cpus,
        constraints=("node.labels.gpu==yes",),
        traced=traced,
    )


@linux
def test_a_swarm_task_is_created_reached_on_its_node_and_removed(
    far: Fakes, workspace: Path
) -> None:
    _swarm(far)
    machine = _swarm_config(workspace, traced=True).create()

    anchor = machine.start()
    try:
        assert anchor.target == "docker://box-1"
        assert machine.placed is not None
        assert machine.placed.node.hostname == "alpha"
    finally:
        machine.stop()

    (created,) = [
        one for one in far.calls("docker") if one[:2] == ["service", "create"]
    ]
    assert _flag(created, "--constraint") == ["node.labels.gpu==yes"]
    assert _flag(created, "--cap-add") == ["SYS_PTRACE"]
    assert _flag(created, "--reserve-cpu") == ["1"]
    assert ["service", "rm", "svc-1"] in far.calls("docker")


@not_linux
def test_a_swarm_task_that_is_not_linux_is_refused_and_removed(
    far: Fakes, workspace: Path
) -> None:
    _swarm(far)

    with pytest.raises(RuntimeError, match="cannot serve linux"):
        _swarm_config(workspace).create().start()

    assert ["service", "rm", "svc-1"] in far.calls("docker")


def test_a_swarm_task_that_failed_is_said_so_and_removed(
    far: Fakes, workspace: Path
) -> None:
    _swarm(far, state="failed", err="starting container failed: oops")

    with pytest.raises(RuntimeError, match="is failed: starting container failed"):
        _swarm_config(workspace).create().start()

    assert ["service", "rm", "svc-1"] in far.calls("docker")


def test_a_swarm_task_no_node_could_ever_take_is_unplaced_at_once(
    far: Fakes, workspace: Path
) -> None:
    _swarm(far, state="pending", err="no suitable node (insufficient resources)")

    with pytest.raises(Unplaced, match="no node of the swarm has 64 CPUs"):
        _swarm_config(workspace, cpus=64.0).create().start()


def test_a_daemon_in_no_swarm_cannot_place_a_task(far: Fakes, workspace: Path) -> None:
    far.answer(
        "info",
        json.dumps({"ServerVersion": "27.0", "Swarm": {"LocalNodeState": "inactive"}}),
    )

    with pytest.raises(OSError, match="in no active swarm"):
        _swarm_config(workspace).create().start()
    assert not [one for one in far.calls("docker") if one[:1] == ["service"]]


def test_what_humanizes_apple_containers_hold_is_read_off_the_list(far: Fakes) -> None:
    far.answer(
        "list",
        json.dumps(
            [
                {
                    "configuration": {
                        "id": "mine",
                        "labels": {"humanize": "501", "humanize.provider": "mac"},
                        "resources": {"cpus": 4, "memoryInBytes": 2048},
                    }
                },
                {"configuration": {"id": "theirs", "labels": {}}},
                {
                    "configuration": {
                        "id": "other",
                        "labels": {"humanize": "501", "humanize.provider": "elsewhere"},
                    }
                },
            ]
        ),
    )

    (held,) = apple.allocations({"humanize.provider": "mac"})

    assert (held.name, held.cpus, held.memory, held.gpus) == ("mine", 4.0, 2048, ())


def test_an_apple_container_system_not_running_is_said_so(far: Fakes) -> None:
    far.answer("system", json.dumps({"status": "stopped"}))

    with pytest.raises(OSError, match="could not ask Apple's container system"):
        apple.status()


def _apple(workspace: Path) -> AppleContainerConfig:
    return AppleContainerConfig(
        image="img:1", workspace=str(workspace), name="mac-box", cpus=2, memory=1000
    )


def _apple_started_with(far: Fakes, workspace: Path) -> None:
    argv = _run_of(far, "container")
    assert _flag(argv, "--name") == ["mac-box"]
    assert _flag(argv, "--cpus") == ["2"]
    assert f"type=bind,source={workspace},target={workspace}" in _flag(argv, "--mount")


@linux
def test_an_apple_container_is_started_reached_and_deleted(
    far: Fakes, workspace: Path
) -> None:
    machine = _apple(workspace).create()

    anchor = machine.start()
    machine.stop()

    assert anchor.target == "apple-container://mac-box"
    _apple_started_with(far, workspace)
    assert ["delete", "--force", "cid-mac-box"] in far.calls("container")
    assert not far.calls("docker")


@not_linux
def test_an_apple_container_that_is_not_linux_is_refused_and_deleted(
    far: Fakes, workspace: Path
) -> None:
    with pytest.raises(RuntimeError, match="cannot serve linux"):
        _apple(workspace).create().start()

    _apple_started_with(far, workspace)
    assert ["delete", "--force", "cid-mac-box"] in far.calls("container")


def test_an_apple_container_cannot_mount_a_path_holding_a_comma(
    far: Fakes, tmp_path: Path
) -> None:
    odd = tmp_path / "a,b"
    odd.mkdir()

    with pytest.raises(ValueError, match="comma"):
        AppleContainerConfig(workspace=str(odd)).create().start()
    assert not far.calls("container")

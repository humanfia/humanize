from __future__ import annotations

import json
import os
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.machines import Allocation, Swarm, SwarmConfig
from hmz.coganchor.machines.docker import CPUS, GPUS, MEMORY, bound
from hmz.coganchor.machines.swarm import Node, Unplaced, nodes, services, swarm_of
from hmz.coganchor.places import ISOLATED, MANAGED, REMOTE, SUPERVISED
from hmz.coganchor.transport import Endpoint

if TYPE_CHECKING:
    from tests.unit.coganchor.machines.conftest import Handshake, Runs

ME = f"{os.getuid()}:{os.getgid()}"


def after(argv: list[str], flag: str) -> list[str]:
    return [argv[at + 1] for at, one in enumerate(argv[:-1]) if one == flag]


def node(
    ident: str,
    hostname: str = "",
    address: str = "10.0.0.1",
    *,
    state: str = "ready",
    availability: str = "active",
    cpus: float = 4,
    memory: int = 8 << 30,
    generic: list[dict[str, Any]] | None = None,
    manager: str = "",
) -> dict[str, Any]:
    return {
        "ID": ident,
        "Spec": {"Availability": availability},
        "Description": {
            "Hostname": hostname or ident,
            "Resources": {
                "NanoCPUs": int(cpus * 1e9),
                "MemoryBytes": memory,
                "GenericResources": generic or [],
            },
        },
        "Status": {"State": state, "Addr": address},
        **({"ManagerStatus": {"Addr": manager}} if manager else {}),
    }


MANAGER = json.dumps(
    {
        "ServerVersion": "27.0",
        "Swarm": {
            "LocalNodeState": "active",
            "ControlAvailable": True,
            "NodeID": "mgr",
        },
    }
)


def task(state: str, *, err: str = "", container: str = "c1", on: str = "mgr") -> str:
    return json.dumps(
        [
            {
                "NodeID": on,
                "Status": {
                    "State": state,
                    "Err": err,
                    "ContainerStatus": {"ContainerID": container},
                },
            }
        ]
    )


def a_swarm(runs: Runs, *tasks: str, landed_on: dict[str, Any] | None = None) -> None:
    """A manager here, a service made as `svc`, and its task going through `tasks`."""
    runs.on("info", out=MANAGER)
    runs.on("service", "create", out="svc\n")
    runs.on("service", "ps", out="t1\n")
    rule = runs.on("inspect", "--type", "task")
    rule.answers = [(0, one, "") for one in tasks]
    runs.on("node", "inspect", out=json.dumps([landed_on or node("mgr")]))


# ------------------------------------------------------------------------------ config


def test_a_task_is_remote_isolated_managed_linux_and_supervised() -> None:
    assert SwarmConfig(workspace="/w").capabilities == {
        REMOTE,
        ISOLATED,
        MANAGED,
        "linux",
        SUPERVISED,
    }


@pytest.mark.parametrize(
    "said",
    [
        {"workspace": "relative"},
        {"workspace": "/w", "endpoint": "nowhere"},
        {"workspace": "/w", "nodes": {"n1": "nowhere"}},
        {"workspace": "/w", "cpus": 0},
        {"workspace": "/w", "memory": -5},
        {"workspace": "/w", "generic": (("", 1),)},
        {"workspace": "/w", "generic": (("GPU", 0),)},
        {"workspace": "/w", "env": {"a=b": "1"}},
        {"workspace": "/w", "labels": {"": "1"}},
    ],
)
def test_what_the_swarm_would_refuse_is_refused_where_it_is_written(
    said: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match=r"absolute|unsupported|must be"):
        SwarmConfig(**said)


def test_a_setting_builds_a_machine_holding_no_service(runs: Runs) -> None:
    machine = SwarmConfig(workspace="/w").create()

    assert isinstance(machine, Swarm)
    assert machine.placed is None
    machine.stop()
    assert runs.calls == []


# ---------------------------------------------------------------------------- swarm_of


def test_a_manager_of_an_active_swarm_says_which_node_it_is() -> None:
    told = json.loads(MANAGER)

    assert swarm_of(told, "local") == "mgr"


@pytest.mark.parametrize(
    ("swarm", "why"),
    [
        ({}, "no active swarm: its swarm is inactive"),
        ({"LocalNodeState": "pending"}, "its swarm is pending"),
        ({"LocalNodeState": "active"}, "is a worker"),
    ],
)
def test_a_daemon_that_cannot_manage_a_swarm_is_refused(
    swarm: dict[str, Any], why: str
) -> None:
    with pytest.raises(OSError, match=why):
        swarm_of({"Swarm": swarm}, "local")


# ------------------------------------------------------------------------------- nodes


def test_a_swarm_with_no_nodes_lists_none(runs: Runs) -> None:
    assert nodes() == []
    assert runs.calls == [["docker", "node", "ls", "--quiet"]]


def test_every_node_is_read_as_its_manager_says_it(runs: Runs) -> None:
    runs.on("node", "ls", out="n1 n2")
    runs.on(
        "node",
        "inspect",
        out=json.dumps(
            [
                node(
                    "n1",
                    "gpu-box",
                    generic=[
                        {"DiscreteResourceSpec": {"Kind": "GPU", "Value": 2}},
                        {"NamedResourceSpec": {"Kind": "FPGA", "Value": "a"}},
                        {"NamedResourceSpec": {"Kind": "FPGA", "Value": "b"}},
                    ],
                ),
                node("n2", address="0.0.0.0", manager="10.0.0.9:2377", state="down"),  # noqa: S104
            ]
        ),
    )

    found = nodes()

    assert found == [
        Node(
            id="n1",
            hostname="gpu-box",
            address="10.0.0.1",
            ready=True,
            cpus=4.0,
            memory=8 << 30,
            resources={"GPU": 2, "FPGA": 2},
        ),
        Node(
            id="n2",
            hostname="n2",
            address="10.0.0.9",
            ready=False,
            cpus=4.0,
            memory=8 << 30,
        ),
    ]


def test_a_drained_node_may_not_be_given_a_task(runs: Runs) -> None:
    runs.on("node", "ls", out="n1")
    runs.on("node", "inspect", out=json.dumps([node("n1", availability="drain")]))

    assert not nodes()[0].ready


@pytest.mark.parametrize(
    ("words", "status", "err"),
    [(("node", "ls"), 1, "not a manager"), (("node", "inspect"), 1, "denied")],
)
def test_a_manager_that_could_not_be_asked_for_its_nodes_is_an_error(
    runs: Runs, words: tuple[str, ...], status: int, err: str
) -> None:
    runs.on("node", "ls", out="n1")
    runs.on(*words, status=status, err=err)

    with pytest.raises(OSError, match=err):
        nodes()


# ---------------------------------------------------------------------------- services


def test_a_swarm_running_nothing_of_ours_holds_nothing(runs: Runs) -> None:
    assert services(labels={"runtime": "r"}) == []
    (asked,) = runs.calls
    assert after(asked, "--filter") == ["label=humanize", "label=runtime=r"]


def test_what_each_service_holds_is_read_off_its_labels(runs: Runs) -> None:
    runs.on("service", "ls", out="s1 s2")
    runs.on(
        "service",
        "inspect",
        out=json.dumps(
            [
                {
                    "ID": "s1",
                    "Spec": {
                        "Name": "one",
                        "Labels": {CPUS: "2", MEMORY: "100", GPUS: "GPU=2"},
                    },
                },
                {"ID": "s2", "Spec": {"Labels": {CPUS: "x"}}},
            ]
        ),
    )

    assert services() == [
        Allocation(
            name="one",
            cpus=2.0,
            memory=100,
            gpus=("GPU=2",),
            labels={CPUS: "2", MEMORY: "100", GPUS: "GPU=2"},
        ),
        Allocation(name="s2", cpus=None, memory=None, gpus=(), labels={CPUS: "x"}),
    ]


def test_a_swarm_that_could_not_be_asked_what_it_runs_is_an_error(runs: Runs) -> None:
    runs.on("service", "ls", status=1, err="boom")

    with pytest.raises(OSError, match="boom"):
        services()


# ------------------------------------------------------------------------------- start


def test_a_service_of_one_task_is_created_and_reached_where_it_landed(
    runs: Runs, handshake: Handshake
) -> None:
    a_swarm(runs, task("running", container="c9"))
    config = SwarmConfig(
        image="img:1",
        workspace="/srv/w",
        name="svc-name",
        cpus=2,
        memory=1024,
        generic=(("GPU", 1),),
        constraints=("node.role!=manager",),
        traced=True,
        env={"A": "1"},
        labels={"team": "a", GPUS: "spoofed"},
    )
    machine = config.create()

    anchor = machine.start()

    (made,) = runs.called("service", "create")
    assert after(made, "--name") == ["svc-name"]
    assert after(made, "--user") == [ME]
    assert after(made, "--workdir") == ["/srv/w"]
    assert after(made, "--mount") == [bound("/srv/w")]
    assert after(made, "--cap-add") == ["SYS_PTRACE"]
    assert after(made, "--label") == [
        "team=a",
        f"humanize={os.getuid()}",
        f"{CPUS}=2",
        f"{MEMORY}=1024",
        f"{GPUS}=GPU=1",
    ]
    assert after(made, "--env") == ["HOME=/tmp", "A=1"]
    assert after(made, "--reserve-cpu") == after(made, "--limit-cpu") == ["2"]
    assert after(made, "--reserve-memory") == ["1024"]
    assert after(made, "--generic-resource") == ["GPU=1"]
    assert after(made, "--constraint") == ["node.role!=manager"]
    assert anchor.target == "docker://c9"
    assert anchor.workspace == "/srv/w"
    assert machine.placed is not None
    assert machine.placed.container == "c9"
    assert machine.placed.daemon == Endpoint()
    assert handshake.asked == [anchor]


def test_a_task_with_no_gpus_is_handed_none_by_the_runtime(
    runs: Runs, handshake: Handshake
) -> None:
    a_swarm(runs, task("running"))

    SwarmConfig(workspace="/w", user="5:5").create().start()

    (made,) = runs.called("service", "create")
    assert after(made, "--env") == ["HOME=/tmp", "NVIDIA_VISIBLE_DEVICES=void"]
    assert after(made, "--user") == ["5:5"]
    assert "--cap-add" not in made


def test_a_task_waits_through_the_states_before_running(
    runs: Runs, handshake: Handshake, monkeypatch: pytest.MonkeyPatch
) -> None:
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", slept.append)
    a_swarm(runs, task("new"), task("preparing"), task("running"))

    SwarmConfig(workspace="/w").create().start()

    assert len(slept) == 2


@pytest.mark.parametrize(
    ("landed", "nodes_said", "daemon"),
    [
        (node("n1", "box"), {"box": "tcp://box:2376"}, "tcp://box:2376"),
        (node("n1", "box", "10.1.1.1"), {}, "ssh://10.1.1.1"),
    ],
)
def test_a_task_on_another_node_is_reached_through_that_nodes_daemon(
    runs: Runs,
    handshake: Handshake,
    landed: dict[str, Any],
    nodes_said: dict[str, str],
    daemon: str,
) -> None:
    a_swarm(runs, task("running", on="n1"), landed_on=landed)
    machine = SwarmConfig(workspace="/w", nodes=nodes_said).create()

    anchor = machine.start()

    assert machine.placed is not None
    assert str(machine.placed.daemon) == daemon
    assert anchor.target == f"docker://c1@{daemon}"


def test_a_node_with_no_address_must_be_named(runs: Runs, handshake: Handshake) -> None:
    a_swarm(runs, task("running", on="n1"), landed_on=node("n1", "box", ""))

    with pytest.raises(RuntimeError, match="name it in the runtime's nodes"):
        SwarmConfig(workspace="/w").create().start()
    assert runs.called("service", "rm", "svc")


def test_a_task_naming_no_container_is_an_error(
    runs: Runs, handshake: Handshake
) -> None:
    a_swarm(runs, task("running", container=""))

    with pytest.raises(RuntimeError, match="names no container"):
        SwarmConfig(workspace="/w").create().start()


@pytest.mark.parametrize(
    ("err", "raised"),
    [
        (
            "invalid mount config: bind source path does not exist: /w",
            FileNotFoundError,
        ),
        ("image not found", RuntimeError),
    ],
)
def test_a_task_that_ended_without_running_is_an_error_and_its_service_goes(
    runs: Runs, handshake: Handshake, err: str, raised: type[Exception]
) -> None:
    a_swarm(runs, task("rejected", err=err))
    machine = SwarmConfig(workspace="/w").create()

    with pytest.raises(raised):
        machine.start()
    assert runs.called("service", "rm", "svc")
    assert handshake.asked == []


def test_a_task_no_node_could_ever_hold_is_given_up_at_once(
    runs: Runs, handshake: Handshake
) -> None:
    a_swarm(runs, task("pending", err="no suitable node (insufficient resources)"))
    runs.on("node", "ls", out="n1")
    runs.on("node", "inspect", out=json.dumps([node("n1", cpus=2)]))

    with pytest.raises(Unplaced, match="no node of the swarm has 8 CPUs"):
        SwarmConfig(workspace="/w", cpus=8).create().start()


def test_a_task_no_node_took_in_time_is_unplaced(
    runs: Runs, handshake: Handshake, monkeypatch: pytest.MonkeyPatch
) -> None:
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", slept.append)
    a_swarm(runs, task("pending", err="no suitable node (constraints)"))
    runs.on("node", "ls", out="n1")
    runs.on("node", "inspect", out=json.dumps([node("n1")]))

    with pytest.raises(Unplaced, match="no node took it within 0s"):
        SwarmConfig(workspace="/w", placing=0).create().start()
    assert runs.called("service", "rm", "svc")


def test_a_service_that_could_not_be_created_says_why(
    runs: Runs, handshake: Handshake
) -> None:
    runs.on("info", out=MANAGER)
    runs.on("service", "create", status=1, err="bad option")

    with pytest.raises(RuntimeError, match="bad option"):
        SwarmConfig(workspace="/w").create().start()
    assert runs.called("service", "rm") == []


def test_a_daemon_in_no_swarm_creates_nothing(runs: Runs) -> None:
    runs.on("info", out=json.dumps({"ServerVersion": "27.0"}))

    with pytest.raises(OSError, match="no active swarm"):
        SwarmConfig(workspace="/w").create().start()
    assert runs.called("service") == []


def test_a_task_that_is_not_what_was_promised_is_taken_down(
    runs: Runs, handshake: Handshake
) -> None:
    a_swarm(runs, task("running"))
    handshake.platform = "darwin"
    machine = SwarmConfig(workspace="/w").create()

    with pytest.raises(RuntimeError, match="cannot serve linux"):
        machine.start()
    assert runs.called("service", "rm", "svc")


def test_stopping_removes_the_service_once(runs: Runs, handshake: Handshake) -> None:
    a_swarm(runs, task("running"))
    machine = SwarmConfig(workspace="/w").create()
    machine.start()

    machine.stop()
    machine.stop()

    assert len(runs.called("service", "rm", "svc")) == 1

from __future__ import annotations

import json
import os
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import rendezvous
from hmz.coganchor.machines import Allocation, Swarm, SwarmConfig
from hmz.coganchor.machines import swarm as swarm_module
from hmz.coganchor.machines.docker import CPUS, GPUS, MEMORY, bound
from hmz.coganchor.machines.swarm import (
    Node,
    Unplaced,
    kept,
    nodes,
    services,
    swarm_of,
)
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


def test_a_manager_that_does_not_create_the_service_in_time_is_given_up_on(
    runs: Runs, handshake: Handshake
) -> None:
    runs.on("info", out=MANAGER)
    runs.on("service", "create", timeout=True)
    machine = SwarmConfig(workspace="/w").create()

    with pytest.raises(TimeoutError, match="did not answer within 600s"):
        machine.start()
    assert len(runs.called("service", "create")) == 1
    assert runs.called("service", "rm") == []  # no id came back to remove it by
    assert handshake.asked == []


def test_a_manager_that_does_not_say_what_it_is_in_time_creates_nothing(
    runs: Runs,
) -> None:
    runs.on("info", timeout=True)

    with pytest.raises(TimeoutError, match="did not answer within 60s"):
        SwarmConfig(workspace="/w").create().submit()
    assert runs.called("service") == []


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


def test_a_service_submitted_alone_is_not_waited_for_and_is_created_once(
    runs: Runs, handshake: Handshake
) -> None:
    a_swarm(runs, task("running"))
    machine = SwarmConfig(workspace="/w").create()

    assert machine.submit() == "svc"
    assert machine.submit() == "svc"
    assert runs.called("service", "ps") == []
    machine.start()

    assert len(runs.called("service", "create")) == 1
    assert handshake.asked


def test_a_task_stopped_and_started_again_is_a_service_of_its_own(
    runs: Runs, handshake: Handshake
) -> None:
    a_swarm(runs, task("running"))
    machine = SwarmConfig(workspace="/w").create()
    first = machine.start()
    machine.stop()

    second = machine.start()

    assert len(runs.called("service", "create")) == 2
    assert first.shadow != second.shadow
    machine.stop()


def test_stopping_removes_the_service_once(runs: Runs, handshake: Handshake) -> None:
    a_swarm(runs, task("running"))
    machine = SwarmConfig(workspace="/w").create()
    machine.start()

    machine.stop()
    machine.stop()

    assert len(runs.called("service", "rm", "svc")) == 1


# -------------------------------------------------------------------------- dialling back

#: The tickets every meeting is booked under, here: the serving half's, and the anchor's.
SERVING, ANCHORING = "5e5e5e5e5e5e5e5e", "a0a0a0a0a0a0a0a0"

#: Where this process's broker keeps its key and certificate, here.
SEALED = "/run/user/me/rendezvous-x"


@dataclass
class Booking:
    """This process's broker, faked: where it was asked for, and what it booked and withdrew."""

    asked: list[str] = field(default_factory=list[str])
    withdrawn: list[str] = field(default_factory=list[str])
    tls: str = SEALED

    def stand(self) -> tuple[str, str]:
        return SERVING, ANCHORING

    def withdraw(self, serving: str) -> None:
        self.withdrawn.append(serving)


@pytest.fixture
def broker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Booking:
    """This process's broker for booked meetings, and an archive, faked."""
    booking = Booking()
    archive = tmp_path / "humanize-abc.pyz"
    with archive.open("wb") as writing:
        writing.write(b"#!/usr/bin/env python3\n")
        with zipfile.ZipFile(writing, "w") as stored:
            stored.writestr("__main__.py", "print('served')\n" * 2000)

    def standing(address: str) -> tuple[Booking, int]:
        booking.asked.append(address)
        return booking, 4242

    monkeypatch.setattr(rendezvous, "standing", standing)
    monkeypatch.setattr(swarm_module, "bundled", lambda: (archive, "abc"))
    return booking


def test_a_task_that_dials_back_is_met_at_a_booked_meeting_its_ticket_kept_secret(
    runs: Runs, handshake: Handshake, broker: Booking
) -> None:
    a_swarm(runs, task("running", on="n1"), landed_on=node("n1", "box"))
    machine = SwarmConfig(
        image="img:1",
        workspace="/w",
        name="svc",
        dial_back="192.0.2.213",
        run_args=("--label", "owner=me", "--label=team=t", "--env", "A=1", "--label"),
    ).create()

    anchor = machine.start()

    assert broker.asked == ["192.0.2.213"]
    # The anchor comes with a ticket of its own, and the key beside the broker's certificate;
    # the task is handed only the serving half's ticket, and the certificate alone.
    assert anchor.target == f"peer://{ANCHORING}@192.0.2.213:4242?tls={SEALED}"
    assert handshake.asked == [anchor]
    (secret,) = runs.called("secret", "create")
    assert secret[-2:] == ["svc-peer", "-"]
    assert (
        runs.given[runs.calls.index(secret)]
        == f"{SERVING}@192.0.2.213:4242?tls=/humanize-tls"
    )
    certified, config = runs.called("config", "create")
    assert certified[-2:] == ["svc-tls", f"{SEALED}/cert.pem"]
    # Deflated, for a config holds at most 1000 KiB.
    assert config[-2] == "svc-hmz"
    assert Path(config[-1]).name == "humanize-abc.deflated.pyz"
    for one in (secret, certified, config):
        labels = after(one, "--label")
        assert {f"humanize={os.getuid()}", "owner=me", "team=t"} <= set(labels)
    assert not [one for one in runs.calls if any("key.pem" in word for word in one)]
    (made,) = runs.called("service", "create")
    assert f"{swarm_module.DIALLING}=1" in after(made, "--label")
    # A last `--label` with nothing after it gives the secret and configs no empty label.
    for one in (secret, certified, config):
        assert "" not in after(one, "--label")
    assert after(made, "--secret") == ["source=svc-peer,target=humanize-peer"]
    assert after(made, "--config") == [
        "source=svc-hmz,target=/svc-hmz.pyz",
        "source=svc-tls,target=/humanize-tls/cert.pem",
    ]
    command = made[made.index("img:1") + 1 :]
    assert command[:2] == ["/bin/sh", "-c"]
    assert '"/svc-hmz.pyz"' in command[2]
    assert command[4:] == [
        *("internal", "anchor", "serve"),
        *("--peer-file", "/run/secrets/humanize-peer", "--export", "/"),
    ]
    for ticket in (SERVING, ANCHORING):
        assert not [one for one in runs.calls if any(ticket in word for word in one)]

    machine.stop()

    assert runs.called("service", "rm", "svc")
    assert runs.called("secret", "rm", "svc-peer")
    assert runs.called("config", "rm", "svc-hmz")
    assert runs.called("config", "rm", "svc-tls")
    assert broker.withdrawn == [SERVING]


def test_a_task_that_dials_back_is_met_only_once_it_is_started(
    runs: Runs, handshake: Handshake, broker: Booking
) -> None:
    a_swarm(runs, task("running"))
    machine = SwarmConfig(workspace="/w", name="svc", dial_back="h").create()

    machine.submit()

    assert broker.asked == ["h"]
    assert len(runs.called("secret", "create")) == 1
    assert runs.called("service", "ps") == []
    assert handshake.asked == []

    anchor = machine.start()

    assert anchor.target == f"peer://{ANCHORING}@h:4242?tls={SEALED}"
    assert handshake.asked == [anchor]
    assert len(runs.called("service", "create")) == 1
    machine.stop()


@pytest.mark.parametrize("nodes_said", [{}, {"box": "tcp://box:2376"}])
def test_a_task_that_dials_back_is_reached_through_no_nodes_daemon(
    runs: Runs, handshake: Handshake, broker: Booking, nodes_said: dict[str, str]
) -> None:
    # A node with no address to reach it at, and one the runtime names a daemon for.
    a_swarm(runs, task("running", on="n1"), landed_on=node("n1", "box", ""))
    machine = SwarmConfig(
        workspace="/w", name="svc", dial_back="h", nodes=nodes_said
    ).create()

    anchor = machine.start()

    assert anchor.target == f"peer://{ANCHORING}@h:4242?tls={SEALED}"
    assert machine.placed is not None
    assert machine.placed.node.hostname == "box"
    assert machine.placed.daemon == Endpoint()
    assert not [one for one in runs.calls if "tcp://box:2376" in one]
    machine.stop()


def test_a_dialling_tasks_serving_half_is_handed_over_deflated_and_made_once(
    runs: Runs, handshake: Handshake, broker: Booking, tmp_path: Path
) -> None:
    a_swarm(runs, task("running"))
    for name in ("one", "two"):
        machine = SwarmConfig(workspace="/w", name=name, dial_back="h").create()
        machine.submit()
        machine.stop()

    handed = {
        Path(one[-1])
        for one in runs.called("config", "create")
        if one[-2].endswith("-hmz")
    }

    # Made once, beside the archive, and handed to every task after.
    (deflated,) = handed
    stored = tmp_path / "humanize-abc.pyz"
    assert deflated.parent == stored.parent
    # Its `#!` line first, as the archive has one, and its members deflated.
    assert deflated.read_bytes().startswith(b"#!/usr/bin/env python3\nPK")
    assert deflated.stat().st_size < stored.stat().st_size // 10
    with zipfile.ZipFile(deflated) as archive:
        assert {one.compress_type for one in archive.infolist()} == {
            zipfile.ZIP_DEFLATED
        }


def test_a_task_is_not_created_where_the_archive_is_more_than_a_config_holds(
    runs: Runs, broker: Booking, monkeypatch: pytest.MonkeyPatch
) -> None:
    a_swarm(runs, task("running", on="n1"), landed_on=node("n1", "box"))
    monkeypatch.setattr(swarm_module, "_CONFIG_MOST", 10)
    machine = SwarmConfig(
        image="img:1", workspace="/w", name="svc", dial_back="192.0.2.213"
    ).create()

    with pytest.raises(OSError, match="more than the 10 a docker config holds"):
        machine.start()

    assert not runs.called("service", "create")


def test_what_a_service_dialling_back_is_created_with_is_named_after_it() -> None:
    assert kept("svc") == (
        ("secret", "svc-peer"),
        ("config", "svc-hmz"),
        ("config", "svc-tls"),
    )


@pytest.mark.parametrize(
    ("kind", "made"), [("secret", "svc-peer"), ("config", "svc-tls")]
)
def test_a_task_whose_meeting_the_manager_does_not_take_in_time_is_not_created(
    runs: Runs, handshake: Handshake, broker: Booking, kind: str, made: str
) -> None:
    a_swarm(runs, task("running"))
    runs.on(kind, "create", timeout=True)
    machine = SwarmConfig(workspace="/w", name="svc", dial_back="h").create()

    with pytest.raises(OSError, match="did not answer within 60s"):
        machine.start()
    assert runs.called("service", "create") == []
    # What the manager may yet make, given up on, goes as what it did make goes.
    assert runs.called(kind, "rm", made)
    assert broker.withdrawn == [SERVING]


@pytest.mark.parametrize("kind", ["secret", "config"])
def test_a_task_whose_meeting_or_serving_half_is_refused_is_not_created(
    runs: Runs, handshake: Handshake, broker: Booking, kind: str
) -> None:
    a_swarm(runs, task("running"))
    runs.on(kind, "create", status=1, err="permission denied")
    machine = SwarmConfig(workspace="/w", name="svc", dial_back="h").create()

    with pytest.raises(RuntimeError, match=f"could not create a {kind}.*denied"):
        machine.start()
    assert runs.called("service", "create") == []
    assert len(runs.called("secret", "rm", "svc-peer")) == (kind == "config")
    assert runs.called("config", "rm") == []
    assert broker.withdrawn == [SERVING]

"""The machines environments are put on: the store, and asking one what it has."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.coganchor import machines, transport
from hmz.coganchor.machines import apple_container, sshconfig, store, swarm
from hmz.flows import EnvConnectionError
from hmz.runtime import Runtimes
from hmz.runtime.doing.runtimes import Checked
from hmz.runtime.flowing import environing_ssh

if TYPE_CHECKING:
    from tests.unit.runtime.doubles_u12 import Stands

ONE = cast("Any", object())


@pytest.mark.parametrize(
    ("method", "args", "kwargs", "module", "name", "forwarded", "forwarded_kw"),
    [
        ("all", (), {}, store, "runtimes", ("",), {}),
        ("all", ("ssh",), {}, store, "runtimes", ("ssh",), {}),
        ("find", ("ssh", "gpu"), {}, store, "find", ("ssh", "gpu"), {}),
        ("saved", ("ssh", "gpu"), {}, store, "saved", ("ssh", "gpu"), {}),
        (
            "new",
            ("docker", "d"),
            {"cpus": 2},
            store,
            "new",
            ("docker", "d"),
            {"cpus": 2},
        ),
        ("add", (ONE,), {}, store, "add", (ONE,), {}),
        ("write", (ONE,), {}, store, "write", (ONE,), {}),
        ("remove", ("ssh", "gpu"), {}, store, "remove", ("ssh", "gpu"), {}),
        ("hosts", (), {}, sshconfig, "hosts", (None,), {}),
        ("hosts", ("~/.ssh/x",), {}, sshconfig, "hosts", ("~/.ssh/x",), {}),
        ("import_ssh", (), {}, store, "imports", (None, None), {"update": False}),
        (
            "import_ssh",
            ("cfg", ["a"]),
            {"update": True},
            store,
            "imports",
            ("cfg", ["a"]),
            {"update": True},
        ),
    ],
)
def test_each_question_about_the_store_is_asked_of_it(
    method: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    module: object,
    name: str,
    forwarded: tuple[Any, ...],
    forwarded_kw: dict[str, Any],
    stand: Stands,
) -> None:
    asked = stand(module, name)

    said = getattr(Runtimes(), method)(*args, **kwargs)

    assert said is asked.returns
    assert asked.calls == [(forwarded, forwarded_kw)]


# ------------------------------------------------------------------ the kinds


@dataclass
class SSH:
    name: str = "gpu"
    port: int = 0

    def target(self) -> str:
        return "ssh://me@gpu"

    def login(self) -> str:
        return "me@gpu"

    def settings(self) -> dict[str, str]:
        return {"IdentityFile": "~/.ssh/k"}


@dataclass
class Daemon:
    def docker(self, *args: str) -> list[str]:
        return ["docker", *args]

    def __str__(self) -> str:
        return "unix:///docker.sock"


@dataclass
class Docker:
    cpus: float = 0.0
    memory: int = 0
    gpus: tuple[str, ...] = ()
    runtime: str = ""
    image: str = ""

    def daemon(self) -> Daemon:
        return Daemon()


@dataclass
class Swarm:
    cpus: float = 0.0
    memory: int = 0
    gpu_resource: str = ""

    def daemon(self) -> Daemon:
        return Daemon()


@dataclass
class Apple:
    cpus: float = 0.0
    memory: int = 0


@dataclass
class Machine:
    """What `subprocess.run` answers with: one answer per program, by its first argument."""

    said: dict[str, tuple[int, str, str]] = field(
        default_factory=dict[str, tuple[int, str, str]]
    )
    raises: BaseException | None = None
    asked: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])

    def run(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.asked.append({"argv": argv, **kwargs})
        if self.raises is not None:
            raise self.raises
        status, out, err = self.said.get(argv[0], (0, "", ""))
        return subprocess.CompletedProcess(argv, status, out, err)


@pytest.fixture
def machine(monkeypatch: pytest.MonkeyPatch) -> Machine:
    made = Machine()
    monkeypatch.setattr(subprocess, "run", made.run)
    monkeypatch.setattr(store, "SSHRuntime", SSH)
    monkeypatch.setattr(store, "SwarmRuntime", Swarm)
    monkeypatch.setattr(store, "AppleContainerRuntime", Apple)
    return made


def _check(runtime: object, seconds: float | None = None) -> Checked:
    if seconds is None:
        return Runtimes().check(cast("Any", runtime))
    return Runtimes().check(cast("Any", runtime), seconds)


# ------------------------------------------------------------------ ssh


@dataclass
class Road:
    target: str

    def line(self, argv: list[str]) -> list[str]:
        return ["ssh", self.target, *argv]

    @classmethod
    def to(cls, target: str) -> Road:
        return cls(target)


@dataclass
class Resources:
    cpu_count: int = 8
    memory: int = 1 << 34
    gpu_count: int = 2
    gpu_memory: int = 1 << 33


@dataclass
class Facts:
    home: str = "/home/me"
    resources: Resources = field(default_factory=Resources)


@pytest.fixture
def ssh(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    read: list[str] = []
    monkeypatch.setattr(transport, "Road", Road)
    monkeypatch.setattr(transport.Target, "parse", str)

    def facts_of(out: str) -> Facts:
        read.append(out)
        if out == "garbled":
            raise EnvConnectionError("could not read what it said")
        return Facts()

    monkeypatch.setattr(environing_ssh, "facts_of", facts_of)
    return read


def test_an_ssh_host_is_asked_what_a_run_asks_it(
    machine: Machine, ssh: list[str]
) -> None:
    machine.said["ssh"] = (0, "facts", "")

    said = _check(SSH(), 5.0)

    assert said == Checked(
        reached=True,
        home="/home/me",
        cpus=8.0,
        memory=1 << 34,
        gpus=("0", "1"),
        gpu_memory=1 << 33,
    )
    (asked,) = machine.asked
    assert asked["argv"][:2] == ["ssh", "ssh://me@gpu"]
    assert asked["timeout"] == 5.0
    assert asked["stdin"] is subprocess.DEVNULL
    assert asked["start_new_session"] is True
    assert asked["env"]["SSH_ASKPASS_REQUIRE"] == "never"
    assert ssh == ["facts"]


@pytest.mark.parametrize(
    ("answer", "why"),
    [
        ((255, "", "Permission denied\n\n"), "Permission denied"),
        ((255, "", ""), "exit status 255"),
        ((0, "garbled", ""), "could not read what it said"),
    ],
)
def test_an_ssh_host_that_does_not_answer_says_why(
    answer: tuple[int, str, str], why: str, machine: Machine, ssh: list[str]
) -> None:
    machine.said["ssh"] = answer

    assert _check(SSH()) == Checked(reached=False, said=why)


@pytest.mark.parametrize(
    ("raised", "why"),
    [
        (subprocess.TimeoutExpired("ssh", 2.0), "it did not answer within 2s"),
        (FileNotFoundError("no ssh here"), "no ssh here"),
    ],
)
def test_an_ssh_host_that_cannot_be_asked_says_why(
    raised: BaseException, why: str, machine: Machine, ssh: list[str]
) -> None:
    machine.raises = raised

    assert _check(SSH(), 2.0) == Checked(reached=False, said=why)


def test_what_ssh_makes_of_a_runtime_is_asked_of_ssh_reaching_nothing(
    stand: Stands, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolved = stand(sshconfig, "resolve")

    def ssh_flags(settings: dict[str, str]) -> tuple[str, ...]:
        return tuple(f"-o{key}={value}" for key, value in settings.items())

    monkeypatch.setattr(transport, "ssh_flags", ssh_flags)
    runtimes = Runtimes()

    assert runtimes.resolve(cast("Any", SSH())) is resolved.returns
    runtimes.resolve(cast("Any", SSH(port=2222)))

    assert resolved.calls == [
        (("me@gpu", ("-oIdentityFile=~/.ssh/k",)), {"alias": "gpu"}),
        (("me@gpu", ("-oIdentityFile=~/.ssh/k", "-p", "2222")), {"alias": "gpu"}),
    ]


# ------------------------------------------------------------------ docker


def _info(**more: Any) -> str:
    return json.dumps(
        {
            "ServerVersion": "27.0",
            "NCPU": 8,
            "MemTotal": 1000,
            "Runtimes": {"runc": {}, "nvidia": {}},
            "DefaultRuntime": "nvidia",
            **more,
        }
    )


@pytest.fixture
def gpus(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    asked: list[dict[str, Any]] = []

    def listed(devices: list[Any]) -> tuple[str, ...]:
        return tuple(str(one["ID"]) for one in devices)

    def usable(
        daemon: str, image: str, devices: list[Any], *, seconds: float, fresh: bool
    ) -> tuple[tuple[str, str], ...]:
        asked.append({"daemon": daemon, "image": image, "fresh": fresh})
        return (("gpu0", "GPU-uuid-0"),)

    monkeypatch.setattr(machines, "gpus_listed", listed)
    monkeypatch.setattr(machines, "gpus_usable", usable)
    return asked


def test_a_docker_daemon_is_held_up_against_what_it_hands_out(
    machine: Machine, gpus: list[dict[str, Any]]
) -> None:
    machine.said["docker"] = (
        0,
        _info(DiscoveredDevices=[{"ID": "gpu0"}, {"ID": "gpu1"}]),
        "",
    )
    saved = Docker(
        cpus=16, memory=2000, gpus=("gpu0", "gpu1", "gpu9"), runtime="kata", image="img"
    )

    said = _check(saved)

    assert said.reached is True
    assert (said.cpus, said.memory, said.version) == (8.0, 1000, "27.0")
    assert said.runtimes == ("nvidia", "runc")
    assert said.gpus == ("gpu0", "gpu1")
    assert said.usable == ("gpu0",)
    assert said.short == (
        "it is to hand out 16 CPUs and has 8",
        "it is to hand out 2000 bytes and has 1000",
        "it has no GPU gpu9",
        "GPU gpu1 does not answer",
        "it has no OCI runtime kata",
    )
    assert gpus == [{"daemon": "unix:///docker.sock", "image": "img", "fresh": True}]
    assert machine.asked[0]["argv"] == ["docker", "info", "--format", "{{json .}}"]


def test_a_docker_daemon_with_room_and_no_gpus_is_short_of_nothing(
    machine: Machine, gpus: list[dict[str, Any]]
) -> None:
    machine.said["docker"] = (0, _info(), "")

    said = _check(Docker(cpus=2, memory=10))

    assert said.short == ()
    assert said.gpus == ()
    assert said.usable is None
    assert gpus == []


@pytest.mark.parametrize(
    ("answer", "why"),
    [
        (
            (1, "", "Cannot connect to the Docker daemon\n"),
            "Cannot connect to the Docker daemon",
        ),
        ((0, json.dumps({"ServerErrors": ["a", "b"]}), ""), "a; b"),
        ((0, "not json", ""), "exit status 0"),
        ((0, "[1, 2]", ""), "exit status 0"),
    ],
)
def test_a_docker_daemon_that_does_not_answer_says_why(
    answer: tuple[int, str, str], why: str, machine: Machine
) -> None:
    machine.said["docker"] = answer

    assert _check(Docker()) == Checked(reached=False, said=why)


# ------------------------------------------------------------------ swarm


@dataclass
class Node:
    hostname: str
    ready: bool = True
    cpus: float = 4.0
    memory: int = 100
    resources: tuple[str, ...] = ()


@pytest.fixture
def nodes(monkeypatch: pytest.MonkeyPatch) -> list[Node]:
    held: list[Node] = []

    def swarm_of(info: dict[str, Any], daemon: str) -> None:
        if info.get("Swarm") != "active":
            raise OSError("it manages no swarm")

    def listed(daemon: str, seconds: float) -> list[Node]:
        return held

    monkeypatch.setattr(swarm, "swarm_of", swarm_of)
    monkeypatch.setattr(swarm, "nodes", listed)
    return held


def test_a_swarm_is_held_up_against_the_nodes_that_take_a_task(
    machine: Machine, nodes: list[Node]
) -> None:
    machine.said["docker"] = (0, _info(Swarm="active"), "")
    nodes += [Node("a", resources=("gpu",)), Node("b"), Node("c", ready=False)]

    said = _check(Swarm(cpus=4, memory=100, gpu_resource="gpu"))

    assert said == Checked(
        reached=True, cpus=8.0, memory=200, version="27.0", nodes=("a", "b")
    )


def test_a_swarm_short_of_everything_says_all_of_it(
    machine: Machine, nodes: list[Node]
) -> None:
    machine.said["docker"] = (0, _info(Swarm="active"), "")

    said = _check(Swarm(cpus=1, memory=1, gpu_resource="gpu"))

    assert said.short == (
        "none of its nodes may take a task",
        "it is to hand out 1 CPUs and has 0",
        "it is to hand out 1 bytes and has 0",
        "no node advertises gpu",
    )


def test_a_daemon_managing_no_swarm_is_not_one(
    machine: Machine, nodes: list[Node]
) -> None:
    machine.said["docker"] = (0, _info(), "")

    assert _check(Swarm()) == Checked(reached=False, said="it manages no swarm")


def test_a_swarm_that_does_not_answer_says_why(
    machine: Machine, nodes: list[Node]
) -> None:
    machine.said["docker"] = (1, "", "refused")

    assert _check(Swarm()) == Checked(reached=False, said="refused")


def test_a_swarm_with_no_time_left_to_list_its_nodes_did_not_answer(
    machine: Machine, nodes: list[Node]
) -> None:
    machine.said["docker"] = (0, _info(Swarm="active"), "")

    assert _check(Swarm(), 0.0) == Checked(
        reached=False, said="it did not answer within 0s"
    )


# ------------------------------------------------------------------ apple


def test_apple_containers_are_held_up_against_the_mac(
    machine: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def status(seconds: float) -> dict[str, Any]:
        return {"server": {"version": "0.5"}}

    def capacity(said: dict[str, Any]) -> tuple[float, int]:
        return 10.0, 64

    monkeypatch.setattr(apple_container, "status", status)
    monkeypatch.setattr(apple_container, "capacity", capacity)

    assert _check(Apple(cpus=4, memory=32)) == Checked(
        reached=True, cpus=10.0, memory=64, version="0.5"
    )
    assert _check(Apple(cpus=12, memory=128)).short == (
        "it is to hand out 12 CPUs and has 10",
        "it is to hand out 128 bytes and has 64",
    )


def test_apple_containers_that_are_not_running_say_why(
    machine: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def status(seconds: float) -> dict[str, Any]:
        raise OSError("the container system is not running")

    monkeypatch.setattr(apple_container, "status", status)

    assert _check(Apple()) == Checked(
        reached=False, said="the container system is not running"
    )

"""A docker environment as it is declared, named, shared out and placed -- nothing started.

What a role declares of a container -- its image, beside the resources every environment may
declare -- is read once per type; `-e role=docker@<provider>/<workdir>` names a runtime written
down or docker's default here; what a runtime may hand out is worked out against what its
running containers already hold, arithmetic alone; and an agent working in one is anchored to
the container rather than put on this machine. Starting a container, and what docker says of it,
is the integration tier's against a stand-in and the system tier's against a daemon.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import cast

import pytest

from hmz.coganchor.machines import AnchoredConfig, gpus_listed, store
from hmz.coganchor.machines.docker import CDI, Allocation
from hmz.coganchor.transport import Endpoint, Target
from hmz.flows import (
    CPUEnvMixin,
    Env,
    EnvBackendKind,
    EnvCollection,
    EnvUnavailable,
    FlowDefinitionError,
    GPUEnvMixin,
    ImageEnvMixin,
    MemoryEnvMixin,
    ResourceUnmet,
    ShellEnvMixin,
)
from hmz.runtime.flowing.declaring import env_roles
from hmz.runtime.flowing.environing import MachineEnvDriver
from hmz.runtime.flowing.environing_docker import (
    IMAGE,
    TRACING,
    Asked,
    DockerMachine,
    Has,
    Share,
    has_of,
    shared,
)
from hmz.runtime.flowing.environments import open_env
from hmz.runtime.flowing.specs import parse_envs


class Trainer(
    Env, ShellEnvMixin, CPUEnvMixin, MemoryEnvMixin, GPUEnvMixin, ImageEnvMixin
):
    _image = "nvcr.io/nvidia/pytorch:25.01-py3"
    _cpu_count = 8
    _memory = 32 << 30
    _gpu_count = 2
    _gpu_memory = 40 << 30


class Plain(Env, ShellEnvMixin): ...


class Envs(EnvCollection):
    trainer: Trainer
    plain: Plain


def _roles() -> dict[str, object]:
    return {one.name: one for one in env_roles(Envs, globals(), {})}


# ------------------------------------------------------------------------ what is declared


def test_an_image_is_read_off_the_role_with_its_resources() -> None:
    trainer, plain = env_roles(Envs, globals(), {})

    assert (trainer.image, trainer.cpu_count, trainer.memory) == (
        "nvcr.io/nvidia/pytorch:25.01-py3",
        8,
        32 << 30,
    )
    assert (trainer.gpu_count, trainer.gpu_memory) == (2, 40 << 30)
    assert ImageEnvMixin not in trainer.capabilities, (
        "an image is a value, not a behaviour"
    )
    assert (plain.image, plain.cpu_count, plain.gpu_count) == ("", 0, 0)


def test_an_image_without_its_mixin_says_nothing() -> None:
    class Stray(Env):
        _image = "ubuntu"

    class Strays(EnvCollection):
        stray: Stray

    (stray,) = env_roles(Strays, {}, {"Stray": Stray})
    assert stray.image == ""


@pytest.mark.parametrize("image", [3, "two words", None])
def test_what_is_no_image_is_refused_where_the_flow_is_read(image: object) -> None:
    class Broken(Env, ImageEnvMixin):
        _image = image  # pyright: ignore[reportAssignmentType]

    class Broke(EnvCollection):
        broken: Broken

    with pytest.raises(FlowDefinitionError, match="_image"):
        env_roles(Broke, {}, {"Broken": Broken})


# --------------------------------------------------------------------------- what is shared


def _held(
    name: str,
    *,
    cpus: float | None = None,
    memory: int | None = None,
    gpus: tuple[str, ...] | str = (),
) -> Allocation:
    return Allocation(
        name=name,
        cpus=cpus,
        memory=memory,
        gpus=gpus,  # pyright: ignore[reportArgumentType]
        labels={"humanize.pid": "42", "humanize.host": "gpubox"},
    )


_BOX = Has(cpus=16, memory=64 << 30, gpus=("0", "1", "2", "3"))


def test_a_share_is_exactly_what_was_asked_and_the_first_gpus_nobody_holds() -> None:
    share = shared(
        Asked(cpus=2, memory=1 << 30, gpus=2),
        _BOX,
        [_held("a", gpus=("0",)), _held("b", gpus=("2",))],
        where="docker@gpubox",
        role="box",
    )

    assert share == Share(cpus=2.0, memory=1 << 30, gpus=("1", "3"))


def test_a_role_asking_nothing_is_given_no_limit_and_no_gpu() -> None:
    held = [_held("a", cpus=16, memory=64 << 30, gpus="all")]

    assert shared(Asked(), _BOX, held, where="docker@gpubox", role="box") == Share(
        None, None, ()
    )


def test_what_is_short_is_named_with_who_holds_it() -> None:
    held = [
        _held("humanize-gpubox-a-1", cpus=10, gpus=("0", "1")),
        _held("humanize-gpubox-b-2", memory=60 << 30, gpus=("2",)),
    ]

    with pytest.raises(ResourceUnmet) as refused:
        shared(
            Asked(cpus=8, memory=8 << 30, gpus=2),
            _BOX,
            held,
            where="docker@gpubox",
            role="box",
        )

    said = str(refused.value)
    assert "docker@gpubox has 6 of 16 CPUs free, and 'box' asks for 8" in said
    assert "10 CPUs held by humanize-gpubox-a-1, pid 42 on gpubox" in said
    assert "has 4 GiB of 64 GiB of memory free, and 'box' asks for 8 GiB" in said
    assert "has 1 of 4 GPUs free, and 'box' asks for 2" in said
    assert "GPU 0, 1 held by humanize-gpubox-a-1" in said
    assert "GPU 2 held by humanize-gpubox-b-2" in said


def test_a_container_holding_every_gpu_leaves_none() -> None:
    with pytest.raises(ResourceUnmet, match=r"0 of 4 GPUs free.*every GPU held by a"):
        shared(
            Asked(gpus=1), _BOX, [_held("a", gpus="all")], where="docker@x", role="r"
        )


def test_no_more_containers_than_the_runtime_may_run() -> None:
    few = Has(cpus=16, memory=0, gpus=(), containers=2)

    shared(Asked(), few, [_held("a")], where="docker@x", role="r")
    with pytest.raises(ResourceUnmet, match="runs 2 of the 2 containers it may"):
        shared(Asked(), few, [_held("a"), _held("b")], where="docker@x", role="r")


def test_gpus_too_small_for_the_role_are_refused_where_the_runtime_says_their_size() -> (
    None
):
    small = Has(cpus=16, memory=0, gpus=("0",), gpu_memory=24 << 30)
    asked = Asked(gpus=1, gpu_memory=40 << 30)

    with pytest.raises(ResourceUnmet, match="GPUs have 24 GiB each"):
        shared(asked, small, [], where="docker@x", role="r")
    # Where nothing says how large they are, the container is asked once it is up.
    unsaid = Has(cpus=16, memory=0, gpus=("0",))
    assert shared(asked, unsaid, [], where="docker@x", role="r").gpus == ("0",)


def test_a_runtime_left_at_zero_hands_out_what_its_daemon_has() -> None:
    info = {
        "NCPU": 64,
        "MemTotal": 256 << 30,
        "DiscoveredDevices": [
            {"Source": "cdi", "ID": "nvidia.com/gpu=all"},
            {"Source": "cdi", "ID": "nvidia.com/gpu=1"},
            {"Source": "cdi", "ID": "nvidia.com/gpu=0"},
            {"Source": "cdi", "ID": "nvidia.com/gpu=GPU-1ac8"},
        ],
    }
    everything = store.DockerRuntime(name="box")
    capped = store.DockerRuntime(
        name="box", cpus=8, memory=16 << 30, gpus=("1",), gpu_memory=1, max_containers=3
    )

    assert has_of(everything, info) == Has(64.0, 256 << 30, ("0", "1"))
    assert has_of(None, info) == Has(64.0, 256 << 30, ("0", "1"))
    assert has_of(capped, info) == Has(8.0, 16 << 30, ("1",), 1, 3)
    assert gpus_listed([{"ID": "k8s.io/gpu=GPU-a"}]) == ("GPU-a",)


def test_a_gpu_listed_under_every_name_and_vendor_is_one_gpu() -> None:
    # As the NVIDIA container toolkit and its k8s device plugin list two GPUs between them:
    # each by index and by UUID, again by UUID under the plugin, and `all` under two vendors.
    devices = [
        {"Source": "cdi", "ID": "k8s.device-plugin.nvidia.com/gpu=GPU-1ac8"},
        {"Source": "cdi", "ID": "k8s.device-plugin.nvidia.com/gpu=GPU-b2f7"},
        {"Source": "cdi", "ID": "management.nvidia.com/gpu=all"},
        {"Source": "cdi", "ID": "nvidia.com/gpu=0"},
        {"Source": "cdi", "ID": "nvidia.com/gpu=1"},
        {"Source": "cdi", "ID": "nvidia.com/gpu=GPU-1ac8"},
        {"Source": "cdi", "ID": "nvidia.com/gpu=GPU-b2f7"},
        {"Source": "cdi", "ID": "nvidia.com/gpu=all"},
    ]

    assert gpus_listed(devices) == ("0", "1")
    assert gpus_listed(devices, CDI) == ("0", "1")
    assert gpus_listed(devices[:3]) == ("GPU-1ac8", "GPU-b2f7")


#: This machine's daemon, as it lists its GPUs: two bound to the driver, by index and by UUID,
#: of which only the first answers -- the second failed after its CDI specs were written.
_HERE = {
    "NCPU": 64,
    "MemTotal": 256 << 30,
    "DiscoveredDevices": [
        {"Source": "cdi", "ID": "k8s.device-plugin.nvidia.com/gpu=GPU-1ac8"},
        {"Source": "cdi", "ID": "k8s.device-plugin.nvidia.com/gpu=GPU-b2f7"},
        {"Source": "cdi", "ID": "management.nvidia.com/gpu=all"},
        {"Source": "cdi", "ID": "nvidia.com/gpu=0"},
        {"Source": "cdi", "ID": "nvidia.com/gpu=1"},
        {"Source": "cdi", "ID": "nvidia.com/gpu=GPU-1ac8"},
        {"Source": "cdi", "ID": "nvidia.com/gpu=GPU-b2f7"},
        {"Source": "cdi", "ID": "nvidia.com/gpu=all"},
    ],
}
_ANSWERING = (("0", "GPU-1ac8"),)


def test_only_a_gpu_that_answers_is_handed_out() -> None:
    has = has_of(None, _HERE, _ANSWERING)

    assert has.gpus == ("0",)
    assert has.bound == 2
    one = shared(Asked(gpus=1), has, [], where="docker@local", role="box")
    assert one.gpus == ("0",)
    with pytest.raises(
        ResourceUnmet,
        match=r"docker@local has 1 of 1 GPUs free, and 'box' asks for 2 "
        r"\(1 of the 2 GPUs it lists are usable: 1 is bound but does not answer\)",
    ):
        shared(Asked(gpus=2), has, [], where="docker@local", role="box")


def test_a_runtime_naming_a_gpu_that_does_not_answer_has_not_got_it() -> None:
    both = store.DockerRuntime(name="box", gpus=("0", "1"))
    second = store.DockerRuntime(name="box", gpus=("1",))
    by_uuid = store.DockerRuntime(name="box", gpus=("GPU-1ac8", "GPU-b2f7"))

    assert has_of(both, _HERE, _ANSWERING).gpus == ("0",)
    assert has_of(by_uuid, _HERE, _ANSWERING).gpus == ("0",)
    nothing = has_of(second, _HERE, _ANSWERING)
    assert (nothing.gpus, nothing.bound) == ((), 1)
    with pytest.raises(ResourceUnmet, match="1 is bound but does not answer"):
        shared(Asked(gpus=1), nothing, [], where="docker@box", role="r")
    # And nobody asked is nothing known to have failed: every GPU named is handed out.
    assert has_of(both, _HERE).gpus == ("0", "1")


def test_a_gpu_held_by_its_uuid_is_held_by_its_name_too() -> None:
    has = has_of(None, _HERE, (("0", "GPU-1ac8"), ("1", "GPU-b2f7")))

    assert has.gpus == ("0", "1")
    share = shared(
        Asked(gpus=1),
        has,
        [_held("old", gpus=("GPU-1ac8",))],
        where="docker@x",
        role="r",
    )
    assert share.gpus == ("1",)


def test_a_gpu_failing_keeps_the_names_of_those_after_it() -> None:
    """`nvidia-smi` numbers what answers; the specs keep the names they were written with."""
    by_index = {
        "DiscoveredDevices": [
            {"Source": "cdi", "ID": "nvidia.com/gpu=0"},
            {"Source": "cdi", "ID": "nvidia.com/gpu=1"},
            {"Source": "cdi", "ID": "nvidia.com/gpu=all"},
        ]
    }
    # The first failed: the container given `nvidia.com/gpu=1` is the one that answered.
    second = (("1", "GPU-b2f7"),)

    has = has_of(None, by_index, second)
    assert has.gpus == ("1",)
    # A container labelled with the second before the first failed holds it still.
    with pytest.raises(ResourceUnmet, match="GPU 1 held by old"):
        shared(Asked(gpus=1), has, [_held("old", gpus=("1",))], where="x", role="r")
    first = store.DockerRuntime(name="box", gpus=("0",))
    assert has_of(first, by_index, second).gpus == ()


def test_a_daemon_listing_no_gpu_hands_out_those_that_answer_by_uuid() -> None:
    has = has_of(None, {"NCPU": 4}, (("0", "GPU-1ac8"),))

    assert (has.gpus, has.bound) == (("GPU-1ac8",), 1)
    assert has.known["0"] == "GPU-1ac8"
    none = has_of(None, {"NCPU": 4}, ())
    with pytest.raises(ResourceUnmet, match=r"\(no GPU of its host answers\)"):
        shared(Asked(gpus=1), none, [], where="docker@x", role="r")


def _answering_as(
    monkeypatch: pytest.MonkeyPatch,
    answers: dict[str, tuple[int, str] | None],
) -> list[list[str]]:
    """Every container asked, answering for each GPU it is given as `answers` says."""
    import subprocess

    from hmz.coganchor.machines import docker

    asked: list[list[str]] = []

    def run(argv: list[str], _: float | None) -> subprocess.CompletedProcess[str]:
        asked.append(argv)
        if "rm" in argv:
            return subprocess.CompletedProcess(argv, 0, "", "")
        given = argv[argv.index("--device" if "--device" in argv else "--gpus") + 1]
        said = answers[given]
        if said is None:
            raise OSError(110, "docker did not answer within 60s")
        return subprocess.CompletedProcess(argv, said[0], said[1], "")

    monkeypatch.setattr(docker, "_asked", run)
    monkeypatch.setattr(docker, "_USABLE", {})
    return asked


def test_each_gpu_a_daemon_lists_is_asked_whether_it_answers_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hmz.coganchor.machines import docker

    asked = _answering_as(
        monkeypatch,
        {
            "nvidia.com/gpu=0": (0, "0, GPU-1ac8\n"),
            "nvidia.com/gpu=1": (6, "No devices were found\n"),
        },
    )
    devices = cast("list[object]", _HERE["DiscoveredDevices"])

    assert docker.gpus_usable("local", "img", devices) == (("0", "GPU-1ac8"),)
    assert docker.gpus_usable("local", "img", devices) == (("0", "GPU-1ac8"),)
    assert len(asked) == 2  # one container per GPU, and once
    for argv in asked:
        assert argv[argv.index("--entrypoint") + 1 : argv.index("img")] == [
            "nvidia-smi"
        ]
        # Given the one GPU named and no other the runtime might add of its own.
        assert argv[argv.index("--env") + 1] == "NVIDIA_VISIBLE_DEVICES=void"
    # Somebody checking asks afresh, whatever is kept.
    assert docker.gpus_usable("local", "img", devices, fresh=True) == (
        ("0", "GPU-1ac8"),
    )
    assert len(asked) == 4


def test_a_container_seeing_more_than_its_gpu_says_nothing_and_is_asked_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hmz.coganchor.machines import docker

    every = (0, "0, GPU-1ac8\n1, GPU-b2f7\n")
    asked = _answering_as(
        monkeypatch, {"nvidia.com/gpu=0": every, "nvidia.com/gpu=1": every}
    )
    devices = cast("list[object]", _HERE["DiscoveredDevices"])

    assert docker.gpus_usable("local", "img", devices) is None
    assert docker.gpus_usable("local", "img", devices) is None
    assert len(asked) == 4


def test_a_gpu_that_hangs_is_one_that_does_not_answer_and_its_container_goes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hmz.coganchor.machines import docker

    asked = _answering_as(
        monkeypatch,
        {"nvidia.com/gpu=0": (0, "0, GPU-1ac8\n"), "nvidia.com/gpu=1": None},
    )
    devices = cast("list[object]", _HERE["DiscoveredDevices"])

    assert docker.gpus_usable("local", "img", devices) == (("0", "GPU-1ac8"),)
    (hung,) = [argv for argv in asked if "--force" in argv]
    started = [argv for argv in asked if "run" in argv]
    names = {argv[argv.index("--name") + 1] for argv in started}
    assert hung[-1] in names


@pytest.mark.parametrize(
    ("answer", "usable"),
    [
        ((0, "0, GPU-1ac8\n1, GPU-b2f7\n"), (("0", "GPU-1ac8"), ("1", "GPU-b2f7"))),
        ((6, "No devices were found\n"), ()),
        ((127, "exec: nvidia-smi: not found\n"), None),
        ((125, "could not select device driver with capabilities: [[gpu]]\n"), None),
        ((0, "something else entirely\n"), None),
        (None, None),
    ],
)
def test_a_daemon_listing_none_is_asked_of_every_gpu_at_once(
    monkeypatch: pytest.MonkeyPatch,
    answer: tuple[int, str] | None,
    usable: tuple[tuple[str, str], ...] | None,
) -> None:
    from hmz.coganchor.machines import docker

    _answering_as(monkeypatch, {"all": answer})

    assert docker.gpus_usable("local", "img", []) == usable


# ---------------------------------------------------------------------------- what -e names


def test_a_docker_environment_names_a_runtime_written_down(tmp_path: Path) -> None:
    store.add(store.DockerRuntime(name="gpubox", workdir=str(tmp_path)))

    (named,) = parse_envs(["box=docker@gpubox"])
    (spelled,) = parse_envs([f"box=docker@local{tmp_path}"])

    assert named.backend is EnvBackendKind.DOCKER
    assert (named.provider, named.workdir) == ("gpubox", PurePosixPath(tmp_path))
    assert (spelled.provider, spelled.workdir) == ("local", PurePosixPath(tmp_path))


def test_a_docker_runtime_nobody_wrote_down_is_refused() -> None:
    (spec,) = parse_envs(["box=docker@nowhere/srv/x"])

    with pytest.raises(EnvUnavailable, match="docker host 'nowhere' not found"):
        open_env(spec)


def test_a_docker_runtime_that_cannot_be_read_says_so() -> None:
    at = store.where("docker", "broken")
    at.mkdir(parents=True)
    (at / "runtime.json").write_text("{")
    (spec,) = parse_envs(["box=docker@broken/srv/x"])

    with pytest.raises(EnvUnavailable, match="cannot be read"):
        open_env(spec)


def test_a_workdir_under_home_is_only_this_machines() -> None:
    store.add(store.DockerRuntime(name="far", endpoint="tcp://10.0.0.5:2375"))
    (far,) = parse_envs(["box=docker@far/~/x"])
    (near,) = parse_envs(["box=docker@local/~/x"])

    with pytest.raises(
        EnvUnavailable, match="remote docker host, so it must be an absolute path"
    ):
        open_env(far)
    assert open_env(near).workdir == PurePosixPath(Path.home() / "x")


def _machine(driver: object) -> DockerMachine:
    assert isinstance(driver, MachineEnvDriver)
    machine = driver._machine
    assert isinstance(machine, DockerMachine)
    return machine


def test_a_container_is_started_as_its_role_says_and_named_for_it() -> None:
    store.add(
        store.DockerRuntime(
            name="gpubox", endpoint="ssh://me@gpubox:2222", image="debian:13"
        )
    )
    trainer, plain = env_roles(Envs, globals(), {})
    (spec,) = parse_envs(["trainer=docker@gpubox/srv/x"])

    driver = open_env(spec, trainer)
    bare = open_env(parse_envs(["plain=docker@gpubox/srv/x"])[0], plain)
    default = open_env(parse_envs(["plain=docker@local/srv/x"])[0], plain)

    machine = _machine(driver)
    assert machine.image == "nvcr.io/nvidia/pytorch:25.01-py3"
    assert machine.asked == Asked(8, 32 << 30, 2, 40 << 30)
    assert machine.endpoint == Endpoint(host="ssh://me@gpubox:2222")
    assert machine.name.startswith("humanize-gpubox-trainer-")
    assert Target.parse(machine.target).endpoint == machine.endpoint
    assert _machine(bare).image == "debian:13"
    assert _machine(default).image == IMAGE
    assert (driver.backend, driver.provider) == (EnvBackendKind.DOCKER, "gpubox")
    # Nothing is started until something is asked of it, and what it has is the least.
    assert not driver.available
    assert (driver.cpu_count, driver.gpu_count) == (1, 0)


def test_an_agent_in_a_container_is_anchored_to_it_in_a_mirror_of_its_own() -> None:
    (spec,) = parse_envs(["box=docker@local/srv/x"])
    driver = open_env(spec)

    placement = driver.placement()

    assert (placement.backend, placement.provider, placement.workdir) == (
        EnvBackendKind.DOCKER,
        "local",
        PurePosixPath("/srv/x"),
    )
    assert isinstance(placement.machine, AnchoredConfig)
    anchor = placement.machine.anchor
    assert anchor.target.startswith("docker://humanize-local-box-")
    assert anchor.workspace == "/srv/x"
    assert anchor.shadow is not None
    assert not anchor.shadow.startswith("/srv/x")
    # The same workdir is the same machine, which is what a fork asks.
    assert driver.placement() == placement


def test_a_container_holding_a_harness_may_borrow_its_agents_descriptors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A harness runtime's container is started with `CAP_SYS_PTRACE`, and no other is.

    Its supervisor borrows each command's descriptors from the agent, which docker's default
    seccomp profile refuses a container without it; a socket cannot be opened again through
    `/proc` instead, so a CLI handing its commands one would see them say nothing.
    """
    from hmz.coganchor import machines
    from hmz.runtime.flowing import environing_docker

    started: list[tuple[str, ...]] = []

    class Config:
        def __init__(self, **said: object) -> None:
            started.append(tuple(cast("tuple[str, ...]", said["run_args"])))

        def create(self) -> Config:
            return self

        def start(self) -> None:
            return None

    def said(*_: object) -> dict[str, object]:
        return {}

    def has(*_: object) -> Has:
        return Has(1.0, 1 << 30, (), 0, 0)

    def held(*_: object, **__: object) -> list[Allocation]:
        return []

    monkeypatch.setattr(environing_docker, "_info", said)
    monkeypatch.setattr(environing_docker, "has_of", has)
    monkeypatch.setattr(machines, "allocations", held)
    monkeypatch.setattr(machines, "DockerConfig", Config)
    store.add(store.DockerRuntime(name="box", run_args=("--shm-size", "1g")))
    (spec,) = parse_envs(["harness=docker@box/srv/x"])

    _machine(open_env(spec, traced=True))._brought_up()
    _machine(open_env(spec))._brought_up()

    assert started == [
        (*TRACING, "--shm-size", "1g"),
        ("--shm-size", "1g"),
    ]

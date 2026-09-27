"""What a container is given of its daemon's host, as the daemon and the container both see it.

CPUs and memory are limits the kernel enforces, so they are read back twice: from what docker
recorded, and from the cgroup the container's own processes are in. GPUs are devices, so what
is checked is which of them a command inside can see -- exactly the ones asked for, by either
of the two ways a daemon hands them out, and none at all when none were asked for, even from an
image that asks the NVIDIA runtime for every one it has.

And the labels a container carries, which is how whoever shares a daemon out reads back what is
already taken: :func:`~hmz.coganchor.machines.allocations` is checked against containers this
test started.

Needs a docker daemon holding `python:3.12-slim`; the GPU tests also need an NVIDIA GPU the
daemon can hand out, and say so when there is none.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.machines import Docker, DockerConfig, Mapped, allocations
from hmz.coganchor.transport import Target
from tests.machines.fixtures import IMAGE

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _inspect(container: str) -> dict[str, Any]:
    said = subprocess.run(
        ["docker", "inspect", container], capture_output=True, text=True, check=True
    )
    return json.loads(said.stdout)[0]


def _gpus_here() -> list[str]:
    """What `nvidia-smi -L` lists on this machine, one line per GPU."""
    try:
        said = subprocess.run(
            ["nvidia-smi", "-L"], capture_output=True, text=True, check=False
        )
    except OSError:
        return []
    return [line for line in said.stdout.splitlines() if line.startswith("GPU ")]


@pytest.fixture
def gpu(daemon: None) -> str:
    """The first GPU's line as `nvidia-smi` lists it here, or a skip."""
    listed = _gpus_here()
    if not listed:
        pytest.skip("needs an NVIDIA GPU and nvidia-smi on this machine")
    return listed[0]


@pytest.fixture
def asking_for_every_gpu(daemon: None) -> Iterator[str]:
    """An image that asks the NVIDIA runtime for every GPU, as CUDA's own images do."""
    tag = f"hmz-test-every-gpu:{uuid.uuid4().hex[:8]}"
    held = f"hmz-test-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        ["docker", "create", "--name", held, "--label", "humanize=test", IMAGE],
        capture_output=True,
        check=True,
    )
    try:
        subprocess.run(
            [
                "docker",
                "commit",
                "--change",
                "ENV NVIDIA_VISIBLE_DEVICES=all",
                held,
                tag,
            ],
            capture_output=True,
            check=True,
        )
    finally:
        subprocess.run(
            ["docker", "rm", "--force", held], capture_output=True, check=False
        )
    try:
        yield tag
    finally:
        subprocess.run(
            ["docker", "rmi", "--force", tag], capture_output=True, check=False
        )


@pytest.mark.timeout(120)
def test_cpu_and_memory_limits_are_the_kernels_and_are_labelled(
    daemon: None, tmp_path: Path
) -> None:
    # A provider of this test's own, so another run sharing the daemon is not counted.
    ours = {"humanize.provider": f"test-{uuid.uuid4().hex[:8]}"}
    machine = DockerConfig(
        image=IMAGE,
        workspace=str(tmp_path),
        cpus=1.5,
        memory=256 << 20,
        shm_size=64 << 20,
        labels=ours,
    ).create()
    anchor = machine.start()
    name = Target.parse(anchor.target).host
    try:
        host = _inspect(name)["HostConfig"]
        assert host["NanoCpus"] == 1_500_000_000
        assert host["Memory"] == 256 << 20
        assert host["ShmSize"] == 64 << 20

        with Mapped(anchor) as held:
            said = held.run(
                [
                    "python3",
                    "-c",
                    (
                        "import os; s = os.statvfs('/dev/shm'); "
                        "print(open('/sys/fs/cgroup/cpu.max').read().strip()); "
                        "print(open('/sys/fs/cgroup/memory.max').read().strip()); "
                        "print(s.f_blocks * s.f_frsize)"
                    ),
                ]
            )
        assert said.ok, said.output
        assert said.output.splitlines() == [
            "150000 100000",
            str(256 << 20),
            str(64 << 20),
        ]

        (held_now,) = allocations(labels=ours)
        assert held_now.name == name
        assert held_now.cpus == 1.5
        assert held_now.memory == 256 << 20
        assert held_now.gpus == ()
    finally:
        machine.stop()
    assert allocations(labels=ours) == []


def _lists_nothing(_machine: Docker) -> set[str]:
    """A daemon that lists no device by name, as one without CDI does."""
    return set()


@pytest.mark.timeout(120)
@pytest.mark.parametrize("by", ["device", "gpus"])
def test_a_container_given_one_gpu_sees_that_one_and_no_other(
    by: str,
    gpu: str,
    asking_for_every_gpu: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """By CDI name where the daemon lists its devices, and by `--gpus` where it does not.

    From an image asking the runtime for every GPU, as CUDA's own do: one named is still one.
    """
    if by == "gpus":
        monkeypatch.setattr(Docker, "_devices", _lists_nothing)
    machine = DockerConfig(
        image=asking_for_every_gpu, workspace=str(tmp_path), gpus=("0",)
    ).create()
    anchor = machine.start()
    name = Target.parse(anchor.target).host
    try:
        with Mapped(anchor) as held:
            said = held.run(["nvidia-smi", "-L"])
        assert said.ok, said.output
        (seen,) = [line for line in said.output.splitlines() if line.startswith("GPU ")]
        assert seen.partition("(UUID: ")[2] == gpu.partition("(UUID: ")[2]
        assert _inspect(name)["Config"]["Labels"]["humanize.gpus"] == "0"
        (held_now,) = [one for one in allocations() if one.name == name]
        assert held_now.gpus == ("0",)
    finally:
        machine.stop()


@pytest.mark.timeout(120)
def test_a_container_given_no_gpu_sees_none_even_when_its_image_asks_for_all(
    gpu: str, asking_for_every_gpu: str, tmp_path: Path
) -> None:
    # The image run by hand, which is what it gets on a daemon whose default runtime reads
    # what it asks for; where that is not so, there is nothing here to hold back.
    by_hand = subprocess.run(
        [
            *("docker", "run", "--rm", "--label", "humanize=test"),
            *(
                asking_for_every_gpu,
                "/bin/sh",
                "-c",
                "ls /dev | grep -c '^nvidia[0-9]'",
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if by_hand.stdout.strip() in ("", "0"):
        pytest.skip("this daemon's default runtime hands an image no GPU it asks for")
    machine = DockerConfig(image=asking_for_every_gpu, workspace=str(tmp_path)).create()
    anchor = machine.start()
    try:
        with Mapped(anchor) as held:
            said = held.run(["/bin/sh", "-c", "ls /dev | grep -c '^nvidia[0-9]'"])
            assert said.output.strip() == "0"
            assert not held.run(["/bin/sh", "-c", "command -v nvidia-smi"]).ok
    finally:
        machine.stop()

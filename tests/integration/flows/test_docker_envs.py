"""The driver for a container of its own on a docker daemon, less the daemon.

A stand-in `docker` on `PATH` (`tests/machines/fixtures.py`) is the one thing not real here:
it writes down every command line it is handed and runs what `docker exec` would run on this
machine instead of in a container. Everything else is what a real container is reached by --
coganchor's zipapp put where the container keeps it, its serving half speaking the wire
protocol over `docker exec`'s pipe -- so the whole driver contract runs through it, and so does
what only this backend has: what a provider's running containers already hold, read off their
labels; a role asking for more than is left, refused before any agent starts; what a run that
died left behind, taken down; and the container taken down when the environment closes.
`tests/system/flows/test_docker_envs.py` runs all of it against a real daemon.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.machines import store
from hmz.flows import EnvBackendKind
from hmz.runtime import Refused
from hmz.runtime.flowing import FakeAgentDriver
from hmz.runtime.flowing.environments import open_env, probe
from hmz.runtime.flowing.specs import parse_envs
from hmz.runtime.runner import Runner
from tests.flows.contracts import check_env_driver
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

    from tests.machines.fixtures import Standin

#: A flow whose one environment is a container asking for a GPU, two CPUs and a GiB, with an
#: agent that would work in it -- and which is never reached where the provider cannot hold it.
_GPU = """
from hmz.flows import (
    Agent, AgentCollection, CPUEnvMixin, Env, EnvCollection, FlowParams, GPUEnvMixin,
    ImageEnvMixin, MemoryEnvMixin, ShellEnvMixin, flow,
)


class Box(Env, ShellEnvMixin, CPUEnvMixin, MemoryEnvMixin, GPUEnvMixin, ImageEnvMixin):
    _image = "python:3.12-slim"
    _cpu_count = 2
    _memory = 1 << 30
    _gpu_count = GPUS


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    box: Box


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def gpu(task, *, agents, envs, params, ctx):
    status, out, _ = await envs["box"].exec(["sh", "-c", "echo $0", "inside"])
    session = await agents["coder"].spawn(env=envs["box"])
    await agents["coder"].run(task, session=session)
    return out.strip()
"""


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


def _started(standin: Standin) -> list[list[str]]:
    """Every `docker run --detach` the stand-in was handed: every container started."""
    return [
        one["argv"] for one in standin.said() if one["argv"][:2] == ["run", "--detach"]
    ]


def _labels(argv: list[str]) -> dict[str, str]:
    said = [argv[at + 1] for at, word in enumerate(argv[:-1]) if word == "--label"]
    labels: dict[str, str] = {}
    for one in said:
        key, _, value = one.partition("=")
        labels[key] = value
    return labels


def _held(name: str, **labels: str) -> dict[str, Any]:
    """A running container of humanize's, as `docker inspect` says one."""
    return {"Name": f"/{name}", "Config": {"Labels": {"humanize": "0", **labels}}}


@pytest.fixture
def gpubox(standin: Standin) -> None:
    """A provider handing out two GPUs, eight CPUs and 16 GiB of a daemon that lists them."""
    standin.set(
        "STANDIN_DEVICES",
        json.dumps(
            [
                {"Source": "cdi", "ID": "nvidia.com/gpu=0"},
                {"Source": "cdi", "ID": "nvidia.com/gpu=1"},
            ]
        ),
    )
    store.add(store.DockerProvider(name="gpubox", gpus=("0", "1")))


@pytest.mark.timeout(120)
async def test_the_docker_driver_keeps_the_contract(
    standin: Standin, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "file.txt").write_text("x\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "first")
    (spec,) = parse_envs([f"repo=docker@local{repo}"])
    driver = open_env(spec)

    await probe(driver)
    assert driver.backend is EnvBackendKind.DOCKER
    await check_env_driver(driver, repo=True)

    (started,) = _started(standin)
    assert started[started.index("--mount") + 1] == (
        f"type=bind,source={repo},target={repo}"
    )
    assert "python:3.12-slim" in started
    assert _labels(started)["humanize.provider"] == "local"
    # Closed, it is taken down by the id docker gave it, and nothing else is.
    assert standin.said()[-1]["argv"] == ["rm", "--force", "c0ffee"]


@pytest.mark.timeout(120)
async def test_a_container_is_given_what_its_role_asks_and_labelled_with_it(
    standin: Standin, gpubox: None, tmp_path: Path
) -> None:
    # GPU 0 is held by a container of a run still going on this host.
    standin.set("STANDIN_PS", "busy")
    standin.set(
        "STANDIN_INSPECT",
        json.dumps(
            [
                _held(
                    "busy",
                    **{
                        "humanize.gpus": "0",
                        "humanize.provider": "gpubox",
                        "humanize.pid": str(os.getpid()),
                        "humanize.host": socket.gethostname(),
                    },
                )
            ]
        ),
    )
    flow = written(tmp_path / "flows", "gpu", _GPU.replace("GPUS", "1"))
    work = tmp_path / "work"
    work.mkdir()
    agent = FakeAgentDriver("claude", reply="done")
    runner = Runner(
        flow,
        agents={"coder": agent},
        envs={"box": f"docker@gpubox{work}"},
        budget={"cost": 1},
        workspace=tmp_path,
    )

    said = await runner.arun("go")

    assert said == "inside"
    (started,) = _started(standin)
    labels = _labels(started)
    assert {key: labels[key] for key in labels if key != "humanize"} == {
        "humanize.provider": "gpubox",
        "humanize.role": "box",
        "humanize.host": socket.gethostname(),
        "humanize.pid": str(os.getpid()),
        "humanize.cpus": "2",
        "humanize.memory": str(1 << 30),
        "humanize.gpus": "1",
    }
    assert started[started.index("--cpus") + 1] == "2"
    assert started[started.index("--memory") + 1] == str(1 << 30)
    assert started[started.index("--device") + 1] == "nvidia.com/gpu=1"
    # The agent was put in the container, reached by the daemon's own `docker exec`.
    (session,) = agent.sessions
    assert session.placement.backend is EnvBackendKind.DOCKER
    assert session.placement.machine is not None
    assert standin.said()[-1]["argv"] == ["rm", "--force", "c0ffee"]


@pytest.mark.timeout(120)
def test_a_role_asking_more_than_is_left_is_refused_before_any_agent_starts(
    standin: Standin, gpubox: None, tmp_path: Path
) -> None:
    standin.set("STANDIN_PS", "busy")
    standin.set(
        "STANDIN_INSPECT",
        json.dumps(
            [
                _held(
                    "busy",
                    **{
                        "humanize.gpus": "0",
                        "humanize.pid": "4242",
                        "humanize.host": "elsewhere",
                    },
                )
            ]
        ),
    )
    flow = written(tmp_path / "flows", "gpu", _GPU.replace("GPUS", "2"))
    work = tmp_path / "work"
    work.mkdir()
    agent = FakeAgentDriver("claude", reply="done")
    runner = Runner(
        flow,
        agents={"coder": agent},
        envs={"box": f"docker@gpubox{work}"},
        budget={"cost": 1},
        workspace=tmp_path,
    )

    with pytest.raises(Refused) as refused:
        runner.run("go")

    assert str(refused.value) == (
        "docker@gpubox has 1 of 2 GPUs free, and 'box' asks for 2 "
        "(GPU 0 held by busy, pid 4242 on elsewhere)"
    )
    assert _started(standin) == []
    assert agent.sessions == []
    ps = [one["argv"] for one in standin.said() if one["argv"][0] == "ps"]
    assert ps == [
        [
            "ps",
            "--quiet",
            "--no-trunc",
            "--filter",
            "label=humanize",
            "--filter",
            "label=humanize.provider=gpubox",
        ]
    ]


@pytest.mark.timeout(120)
def test_what_a_run_that_died_left_behind_is_taken_down(
    standin: Standin, gpubox: None, tmp_path: Path
) -> None:
    gone = subprocess.Popen(["true"])
    gone.wait()
    standin.set("STANDIN_PS", "left")
    standin.set(
        "STANDIN_INSPECT",
        json.dumps(
            [
                _held(
                    "left",
                    **{
                        "humanize": str(os.getuid()),
                        "humanize.gpus": "0,1",
                        "humanize.pid": str(gone.pid),
                        "humanize.host": socket.gethostname(),
                    },
                )
            ]
        ),
    )
    work = tmp_path / "work"
    work.mkdir()
    flow = written(tmp_path / "flows", "gpu", _GPU.replace("GPUS", "2"))
    runner = Runner(
        flow,
        agents={"coder": FakeAgentDriver("claude", reply="done")},
        envs={"box": f"docker@gpubox{work}"},
        budget={"cost": 1},
        workspace=tmp_path,
    )

    runner.run("go")

    asked = [one["argv"] for one in standin.said()]
    assert ["rm", "--force", "left"] in asked
    (started,) = _started(standin)
    assert _labels(started)["humanize.gpus"] == "0,1"


def test_a_lock_per_provider_is_held_beside_the_providers(
    standin: Standin, gpubox: None, tmp_path: Path
) -> None:
    del standin
    work = tmp_path / "work"
    work.mkdir()
    flow = written(tmp_path / "flows", "gpu", _GPU.replace("GPUS", "1"))
    Runner(
        flow,
        agents={"coder": FakeAgentDriver("claude", reply="done")},
        envs={"box": f"docker@gpubox{work}"},
        budget={"cost": 1},
        workspace=tmp_path,
    ).run("go")

    assert (store.under() / "docker" / ".gpubox.lock").is_file()
    assert [one.name for one in store.providers("docker")] == ["gpubox"]


#: A flow holding its container until it is ended from outside: it says it has one, and waits.
_WAITS = """
from hmz.flows import AgentCollection, Env, EnvCollection, FilesEnvMixin, FlowParams
from hmz.flows import ImageEnvMixin, ShellEnvMixin, flow


class Box(Env, ShellEnvMixin, FilesEnvMixin, ImageEnvMixin):
    _image = "python:3.12-slim"


class Envs(EnvCollection):
    box: Box


@flow(agents=AgentCollection, envs=Envs, params=FlowParams)
async def waits(task, *, agents, envs, params, ctx):
    await envs["box"].write("up.txt", b"up")
    await envs["box"].exec(["sleep", "240"], timeout=300)
"""


@pytest.mark.timeout(120)
@pytest.mark.parametrize("ending", [signal.SIGTERM, signal.SIGHUP])
def test_a_run_ended_by_a_terminate_or_a_hangup_takes_its_container_down(
    standin: Standin, tmp_path: Path, ending: signal.Signals
) -> None:
    """Rather than leave it running until the next run on its provider finds it."""
    work = tmp_path / "work"
    work.mkdir()
    flow = written(tmp_path / "flows", "waits", _WAITS)
    run = subprocess.Popen(
        [
            *(sys.executable, "-m", "hmz", "exec", "-f", str(flow)),
            *("-e", f"box=docker@local{work}", "-b", "cost=1", "go"),
        ],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 60
        while not (work / "up.txt").exists():
            assert run.poll() is None, run.communicate()
            assert time.monotonic() < deadline, "the run never had its container"
            time.sleep(0.1)
        run.send_signal(ending)
        _, err = run.communicate(timeout=60)
    finally:
        if run.poll() is None:
            run.kill()

    assert run.returncode == 128 + ending, err
    assert "Traceback" not in err, err
    assert ["rm", "--force", "c0ffee"] in [one["argv"] for one in standin.said()]


@pytest.mark.timeout(120)
def test_a_hangup_somebody_chose_to_ignore_is_still_ignored(
    standin: Standin, tmp_path: Path
) -> None:
    """A run started under `nohup` goes on when its terminal goes, and a terminate ends it."""
    work = tmp_path / "work"
    work.mkdir()
    flow = written(tmp_path / "flows", "waits", _WAITS)
    run = subprocess.Popen(
        [
            *("nohup", sys.executable, "-m", "hmz", "exec", "-f", str(flow)),
            *("-e", f"box=docker@local{work}", "-b", "cost=1", "go"),
        ],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 60
        while not (work / "up.txt").exists():
            assert run.poll() is None, run.communicate()
            assert time.monotonic() < deadline, "the run never had its container"
            time.sleep(0.1)
        run.send_signal(signal.SIGHUP)
        with pytest.raises(subprocess.TimeoutExpired):
            run.wait(timeout=3)
        run.send_signal(signal.SIGTERM)
        _, err = run.communicate(timeout=60)
    finally:
        if run.poll() is None:
            run.kill()

    assert run.returncode == 128 + signal.SIGTERM, err
    assert ["rm", "--force", "c0ffee"] in [one["argv"] for one in standin.said()]

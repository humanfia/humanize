"""The driver for an Apple container of its own on this Mac, less the virtual machines.

A stand-in `container` on `PATH` (`tests/machines/fixtures.py`) is the one thing not real here:
it writes down every command line it is handed and runs what `container exec` would run on this
machine instead of in a container. Everything else is what a real container is reached by --
coganchor's zipapp put where the container keeps it, its serving half speaking the wire
protocol over `container exec`'s pipe -- so the whole driver contract runs through it, and so
does what a runtime shares out: what its running containers already hold, read off their
labels; a role asking for more than is left, refused before any agent starts; what a run that
died left behind, taken down; and the container taken down when the environment closes.
`tests/system/flows/test_apple_container_envs.py` runs it against Apple's own.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
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
from tests.machines.fixtures import listed
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

    from tests.machines.fixtures import Standin

#: A flow whose one environment is a container asking for two CPUs and a GiB, with an agent
#: that would work in it -- and which is never reached where the runtime cannot hold it.
_BOX = """
from hmz.flows import (
    Agent, AgentCollection, CPUEnvMixin, Env, EnvCollection, FlowParams, ImageEnvMixin,
    MemoryEnvMixin, ShellEnvMixin, flow,
)


class Box(Env, ShellEnvMixin, CPUEnvMixin, MemoryEnvMixin, ImageEnvMixin):
    _image = "python:3.12-slim"
    _cpu_count = CPUS
    _memory = 1 << 30


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    box: Box


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def box(task, *, agents, envs, params, ctx):
    status, out, _ = await envs["box"].exec(["sh", "-c", "echo $0", "inside"], timeout=60)
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
    """Every `container run --detach` the stand-in was handed: every container started."""
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


def _running(standin: Standin, *held: dict[str, Any]) -> None:
    """What `container list` says is running."""
    standin.set("STANDIN_LIST", json.dumps(list(held)))


def _run(tmp_path: Path, envs: str, cpus: int = 2) -> tuple[Runner, FakeAgentDriver]:
    flow = written(tmp_path / "flows", "box", _BOX.replace("CPUS", str(cpus)))
    agent = FakeAgentDriver("claude", reply="done")
    return Runner(
        flow,
        agents={"coder": agent},
        envs={"box": envs},
        budget={"cost": 1},
        workspace=tmp_path,
    ), agent


@pytest.mark.timeout(120)
async def test_the_apple_container_driver_keeps_the_contract(
    apple_standin: Standin, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "file.txt").write_text("x\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "first")
    (spec,) = parse_envs([f"repo=apple-container@local{repo}"])
    driver = open_env(spec)

    await probe(driver)
    assert driver.backend is EnvBackendKind.APPLE_CONTAINER
    await check_env_driver(driver, repo=True)

    (started,) = _started(apple_standin)
    assert started[started.index("--mount") + 1] == (
        f"type=bind,source={repo},target={repo}"
    )
    assert started[started.index("--user") + 1] == f"{os.getuid()}:{os.getgid()}"
    assert "python:3.12-slim" in started
    name = started[started.index("--name") + 1]
    assert _labels(started)["humanize.provider"] == "local"
    # Closed, it is taken down by the id `container` gave it, and nothing else is.
    assert apple_standin.said()[-1]["argv"] == ["delete", "--force", name]


@pytest.mark.timeout(120)
async def test_a_container_is_given_what_its_role_asks_and_labelled_with_it(
    apple_standin: Standin, tmp_path: Path
) -> None:
    store.add(store.AppleContainerRuntime(name="mac", run_args=("--dns", "1.1.1.1")))
    work = tmp_path / "work"
    work.mkdir()
    runner, agent = _run(tmp_path, f"apple-container@mac{work}")

    said = await runner.arun("go")

    assert said == "inside"
    (started,) = _started(apple_standin)
    labels = _labels(started)
    assert {key: labels[key] for key in labels if key != "humanize"} == {
        "humanize.provider": "mac",
        "humanize.role": "box",
        "humanize.host": socket.gethostname(),
        "humanize.pid": str(os.getpid()),
        "humanize.cpus": "2",
        "humanize.memory": str(1 << 30),
    }
    assert started[started.index("--cpus") + 1] == "2"
    assert started[started.index("--memory") + 1] == str(1 << 30)
    # What else the runtime says is said before humanize's own, which a later flag outranks.
    assert started.index("--dns") < started.index("--cpus")
    # The agent was put in the container, reached by `container exec`.
    (session,) = agent.sessions
    assert session.placement.backend is EnvBackendKind.APPLE_CONTAINER
    assert session.placement.machine is not None
    assert apple_standin.said()[-1]["argv"][:2] == ["delete", "--force"]


@pytest.mark.timeout(120)
def test_a_role_asking_more_than_is_left_is_refused_before_any_agent_starts(
    apple_standin: Standin, tmp_path: Path
) -> None:
    apple_standin.set("STANDIN_NCPU", "8")
    _running(
        apple_standin,
        listed(
            "busy",
            {
                "humanize": "0",
                "humanize.provider": "local",
                "humanize.cpus": "3",
                "humanize.pid": "4242",
                "humanize.host": "elsewhere",
            },
            cpus=3,
        ),
        # Started with no size of its own, and holding `container`'s default even so.
        listed(
            "unsized",
            {
                "humanize": "0",
                "humanize.provider": "local",
                "humanize.pid": "4343",
                "humanize.host": "elsewhere",
            },
        ),
        listed("other", {"humanize": "0", "humanize.provider": "mac"}),
    )
    work = tmp_path / "work"
    work.mkdir()
    runner, agent = _run(tmp_path, f"apple-container@local{work}")

    with pytest.raises(Refused) as refused:
        runner.run("go")

    assert str(refused.value) == (
        "apple-container@local has 1 of 8 CPUs free, and 'box' asks for 2 "
        "(3 CPUs held by busy, pid 4242 on elsewhere; 4 CPUs held by unsized, pid 4343 "
        "on elsewhere)"
    )
    assert _started(apple_standin) == []
    assert agent.sessions == []


@pytest.mark.timeout(120)
def test_what_a_run_that_died_left_behind_is_taken_down(
    apple_standin: Standin, tmp_path: Path
) -> None:
    gone = subprocess.Popen(["true"])
    gone.wait()
    apple_standin.set("STANDIN_NCPU", "2")
    _running(
        apple_standin,
        listed(
            "left",
            {
                "humanize": str(os.getuid()),
                "humanize.provider": "local",
                "humanize.cpus": "2",
                "humanize.pid": str(gone.pid),
                "humanize.host": socket.gethostname(),
            },
        ),
    )
    work = tmp_path / "work"
    work.mkdir()
    runner, _ = _run(tmp_path, f"apple-container@local{work}")

    runner.run("go")

    asked = [one["argv"] for one in apple_standin.said()]
    assert ["delete", "--force", "left"] in asked
    assert len(_started(apple_standin)) == 1


def test_a_lock_per_runtime_is_held_beside_the_runtimes(
    apple_standin: Standin, tmp_path: Path
) -> None:
    del apple_standin
    store.add(store.AppleContainerRuntime(name="mac"))
    work = tmp_path / "work"
    work.mkdir()
    runner, _ = _run(tmp_path, f"apple-container@mac{work}")

    runner.run("go")

    assert (store.under() / "apple-container" / ".mac.lock").is_file()
    assert [one.name for one in store.runtimes("apple-container")] == ["mac"]


def test_a_container_system_that_is_not_running_refuses_the_run(
    apple_standin: Standin, tmp_path: Path
) -> None:
    apple_standin.set("STANDIN_DOWN", "1")
    work = tmp_path / "work"
    work.mkdir()
    runner, agent = _run(tmp_path, f"apple-container@local{work}")

    with pytest.raises(Refused, match="could not connect to apple-container@local"):
        runner.run("go")

    assert _started(apple_standin) == []
    assert agent.sessions == []

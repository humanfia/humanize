"""A docker runtime that cannot hold a role falls back to the next one, against a real daemon.

`tests/integration/flows/test_ssh_envs.py` walks fallback lists over a stand-in `ssh`. This is
the one refusal only a real daemon gives: a runtime saved as handing out less memory than the
role asks, which `docker info` and the containers already running there are weighed against.
Both runtimes are docker's default here, so what tells them apart is the workdir each was saved
with, and the `.dockerenv` docker puts in every container and on no host.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from hmz.coganchor.machines import store
from hmz.runtime.epic import epics, read
from tests.machines.fixtures import IMAGE
from tests.stubs import written

_LANDS = f"""
from hmz.flows import AgentCollection, Env, EnvCollection, FlowParams, ImageEnvMixin
from hmz.flows import MemoryEnvMixin, ShellEnvMixin, flow


class Box(Env, ShellEnvMixin, MemoryEnvMixin, ImageEnvMixin):
    _image = "{IMAGE}"
    _memory = 1 << 30


class Envs(EnvCollection):
    box: Box


@flow(agents=AgentCollection, envs=Envs, params=FlowParams)
async def lands(task, *, agents, envs, params, ctx):
    status, _, err = await envs["box"].exec(
        ["sh", "-c", "test -f /.dockerenv && echo inside > landed.txt"]
    )
    assert status == 0, err
"""

#: Less memory than the role asks for, which no daemon is short of.
_SMALL = 64 << 20


def _left(provider: str) -> list[str]:
    """Every container of a runtime docker still has, running or not."""
    said = subprocess.run(
        [
            "docker",
            "ps",
            "--all",
            "--quiet",
            "--filter",
            f"label=humanize.provider={provider}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return said.stdout.split()


def _exec(flow: Path, spec: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-Pm", "hmz", "exec", "-f", str(flow), "-e", spec]
        + ["-b", "cost=1", "go"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
        env=os.environ,
    )


@pytest.mark.timeout(300)
def test_a_runtime_short_of_memory_falls_back_into_the_next_ones_container(
    daemon: None, tmp_path: Path
) -> None:
    del daemon
    given, saved = tmp_path / "given", tmp_path / "saved"
    given.mkdir()
    saved.mkdir()
    store.write(
        store.DockerRuntime(name="fa", memory=_SMALL, fallback=("docker:fb",))
    )
    store.write(store.DockerRuntime(name="fb", workdir=str(saved)))
    flow = written(tmp_path / "flows", "lands", _LANDS)
    project = tmp_path / "project"
    project.mkdir()

    ran = _exec(flow, f"box=docker@fa{given}", project)

    assert ran.returncode == 0, ran.stderr
    assert "docker:fa cannot hold 'box'" in ran.stderr, ran.stderr
    assert "using docker:fb" in ran.stderr, ran.stderr
    assert (saved / "landed.txt").read_text() == "inside\n"
    assert not (given / "landed.txt").exists()
    (epic,) = [read(one) for one in epics(project)]
    assert epic is not None
    assert epic.envs == (f"box=docker@fa{given}",)
    assert epic.used == (f"box=docker@fb{saved}",)
    assert _left("fa") == []
    assert _left("fb") == []


@pytest.mark.timeout(300)
def test_a_runtime_with_no_list_of_its_own_walks_nothing_though_it_is_a_fallback(
    daemon: None, tmp_path: Path
) -> None:
    del daemon
    work = tmp_path / "work"
    work.mkdir()
    store.write(store.DockerRuntime(name="fa", fallback=("docker:fb",)))
    store.write(store.DockerRuntime(name="fb", memory=_SMALL))
    flow = written(tmp_path / "flows", "lands", _LANDS)
    project = tmp_path / "project"
    project.mkdir()

    ran = _exec(flow, f"box=docker@fb{work}", project)

    assert ran.returncode == 2, ran.stderr
    assert "docker@fb has" in ran.stderr, ran.stderr
    assert "cannot hold" not in ran.stderr, ran.stderr
    assert not (work / "landed.txt").exists()

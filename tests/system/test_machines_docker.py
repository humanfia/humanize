"""The coding task, its agent working in a container on docker, or in a task on a swarm.

The daemon is docker's default here, written down as a runtime of the test's own; the swarm is
the one this machine manages, its task pinned to this node, where the workspace is. Each skips,
saying why, without a daemon running, a swarm, or the image holding the CLIs built.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz.runtime.flowing.environing_docker import PID
from tests.system.doubles_machines import answers, built, contained, done, hmz, run

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.timeout(1800)


def _docker(*argv: str) -> str:
    return subprocess.run(
        ["docker", *argv], capture_output=True, text=True, timeout=60, check=True
    ).stdout


@pytest.fixture
def daemon() -> None:
    """A docker daemon holding the image, or a skip."""
    if why := answers("docker", "info"):
        pytest.skip(f"needs a docker daemon running: {why}")
    built("docker")


@pytest.fixture
def node(daemon: None) -> str:
    """This node, a manager of the active swarm it is in, or a skip."""
    swarm = json.loads(_docker("info", "--format", "{{json .Swarm}}") or "{}")
    if swarm.get("LocalNodeState") != "active" or not swarm.get("ControlAvailable"):
        pytest.skip("needs this machine to manage an active docker swarm")
    return str(swarm["NodeID"])


def _left(*argv: str) -> list[str]:
    """What docker still has of this process's, listed by `argv`."""
    return _docker(*argv, "--quiet", "--filter", f"label={PID}={os.getpid()}").split()


def test_an_agent_codes_in_a_docker_container(
    daemon: None, workspace: Path, tmp_path: Path
) -> None:
    runtimes = hmz(tmp_path / "here").runtimes
    runtimes.add(runtimes.new("docker", "box"))

    seen = run(tmp_path, workspace, f"docker@box{workspace}")

    done(workspace)
    contained(seen)
    assert _left("ps", "--all") == [], "the container was left behind"


def test_an_agent_codes_in_a_swarm_task(
    node: str, workspace: Path, tmp_path: Path
) -> None:
    runtimes = hmz(tmp_path / "here").runtimes
    runtimes.add(runtimes.new("swarm", "hive", constraints=[f"node.id=={node}"]))

    seen = run(tmp_path, workspace, f"swarm@hive{workspace}")

    done(workspace)
    contained(seen)
    assert _left("service", "ls") == [], "the service was left behind"

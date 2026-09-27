"""A docker environment provider checked against the docker daemon on this machine.

`tests/integration/machines/test_env_providers.py` reads what a stand-in `docker` says; this is
the real one, reached the two ways a provider on this machine names it -- as whatever `docker`
here reaches, and at its socket -- and skipped, saying why, where there is no daemon to ask.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from hmz.coganchor.machines.store import DockerProvider
from hmz.runtime import Hmz

#: Where a daemon on this machine ordinarily listens.
_SOCKET = "/var/run/docker.sock"


@pytest.fixture
def docker_here() -> None:
    """A docker daemon answering here, or a skip."""
    try:
        said = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as reason:
        pytest.skip(f"needs a docker daemon: {reason}")
    if said.returncode or not said.stdout.strip():
        pytest.skip(f"needs a docker daemon: {said.stderr.strip()}")


def _gpus() -> int:
    """How many GPUs `nvidia-smi` sees here, or 0 where there is none to ask."""
    if shutil.which("nvidia-smi") is None:
        return 0
    said = subprocess.run(
        ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        check=False,
    )
    return len(said.stdout.split()) if said.returncode == 0 else 0


@pytest.mark.timeout(120)
@pytest.mark.parametrize("endpoint", ["local", f"unix://{_SOCKET}"])
@pytest.mark.usefixtures("docker_here")
def test_the_daemon_here_says_what_it_has(endpoint: str) -> None:
    if endpoint != "local" and not Path(_SOCKET).exists():
        pytest.skip(f"the daemon here does not listen at {_SOCKET}")

    checked = Hmz().environments.check(DockerProvider(name="here", endpoint=endpoint))

    assert checked.reached, checked.said
    assert checked.version
    assert checked.cpus >= 1
    assert checked.memory > 0
    assert checked.runtimes
    assert checked.short == ()
    if checked.gpus:  # a daemon naming its GPUs names the ones nvidia-smi sees
        assert len(checked.gpus) == _gpus()


@pytest.mark.timeout(120)
@pytest.mark.usefixtures("docker_here")
def test_what_the_daemon_has_not_got_is_said() -> None:
    envs = Hmz().environments
    here = envs.check(envs.new("docker", "here"))

    checked = envs.check(
        envs.new("docker", "greedy", cpus=here.cpus + 1, runtime="no-such-runtime")
    )

    assert checked.reached, checked.said
    assert checked.short == (
        f"it is to hand out {here.cpus + 1:g} CPUs and has {here.cpus:g}",
        "it has no runtime no-such-runtime",
    )

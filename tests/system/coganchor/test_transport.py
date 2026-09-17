"""Reaching a target the ways that need the machine underneath to cooperate.

Split from `tests/integration/coganchor/test_transport.py`, which keeps everything about
reaching a target that a stand-in can stand in for: parsing a target spelling, building the
zipapp, and the line ssh carries. What is here is the rest -- a real `ssh` to localhost that
answers without a password, and a real seccomp filter with a real ptrace supervisor under
it. Neither is something this repo could fake, and neither is something CI can be relied on
to have, which is why they are a tier apart rather than a skip inside one.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.coganchor.conftest import REPO_ROOT, Anchorage

#: What the suite keeps out of the home directory of whoever is running it, and off
#: anybody's network. Named rather than passed wholesale: the point of the environment
#: below is what is missing from it.
_GUARDS = (
    "HUMANIZE_HOME",
    "HUMANIZE_SENTRY",
    "HUMANIZE_SHADOWS",
    "HUMANIZE_DAEMON",
    "HUMANIZE_PRICES",
)


def _bare() -> dict[str, str]:
    """The environment the anchored run below gets, which is the one the probe must use.

    Deliberately small -- a `PATH`, the source tree, and a home to read an ssh config out of
    -- so that what reaches the far side is what humanize puts there rather than whatever the
    suite happened to be started with. `SSH_AUTH_SOCK` is the one that matters: an agent
    forwarded into the terminal running the tests would let a probe in and leave the run
    itself outside, which is a skip that never happens in front of a failure that always
    does.

    Small, but not empty of what the suite sets on itself: what is started over there is a
    whole `hmz`, and one that inherits none of :data:`_GUARDS` writes its record of this
    temporary mirror into the real `~/.cache/humanize`, reads the real `~/.humanize` back,
    and reports a crash a test provoked on purpose. `tests/conftest.py` sets each of them
    for the process running the suite; this carries them into the process the suite starts.
    """
    return {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "HOME": str(Path.home()),
        **{name: os.environ[name] for name in _GUARDS if name in os.environ},
    }


def _ssh_to_localhost_works() -> bool:
    try:
        probe = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=no",
                "localhost",
                "true",
            ],
            capture_output=True,
            timeout=20,
            env=_bare(),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


@pytest.mark.timeout(180)
def test_ssh_transport_bootstraps_and_runs(tmp_path: Path) -> None:
    """The full ssh path: build a zipapp, ship it, and work through the pipe."""
    if not _ssh_to_localhost_works():
        pytest.skip("passwordless ssh to localhost is not available")

    target = tmp_path / "target"
    mirror = tmp_path / "mirror"
    target.mkdir()
    mirror.mkdir()
    (target / "shipped.txt").write_text("arrived over ssh\n")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hmz",
            "internal",
            "anchor",
            "--target",
            "ssh://localhost",
            "--workspace",
            "/coganchor-project",
            "--remote-path",
            str(target),
            "--shadow",
            str(mirror),
            "bash",
            "-c",
            "cat shipped.txt; echo written-back > reply.txt",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=_bare(),
        timeout=150,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "arrived over ssh" in result.stdout
    assert (target / "reply.txt").read_text() == "written-back\n"


# What a session refuses before it has started one. Here rather than a tier down because
# `anchorage` is a real seccomp filter and a real ptrace supervisor: what is being checked is
# a refusal, but what is being asked for is a session, and a machine that cannot trace cannot
# have one.


def test_running_without_an_agent_is_an_error(anchorage: Anchorage) -> None:
    result = anchorage.run()
    assert result.returncode == 2
    assert "no agent given" in result.stderr


def test_unknown_agent_is_reported_clearly(anchorage: Anchorage) -> None:
    result = anchorage.run("definitely-not-installed-xyz")
    assert result.returncode == 1
    assert "not found on PATH" in result.stderr

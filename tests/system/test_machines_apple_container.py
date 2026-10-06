"""The coding task, its agent working in an Apple container on this Mac.

The runtime is written down as one of the test's own. Skips, saying why, where Apple's
`container` is not running or the image holding the CLIs cannot be built.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime.flowing.environing_docker import PID
from tests.system.doubles_machines import answers, built, contained, done, hmz, run

if TYPE_CHECKING:
    from pathlib import Path


def _left() -> list[str]:
    """Every container of this process's that Apple's `container` still has, running or not."""
    said = subprocess.run(
        ["container", "list", "--all", "--format", "json"],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    listed: list[dict[str, Any]] = json.loads(said.stdout or "[]")
    return [
        one["configuration"]["id"]
        for one in listed
        if one["configuration"].get("labels", {}).get(PID) == str(os.getpid())
    ]


@pytest.mark.timeout(1800)
def test_an_agent_codes_in_an_apple_container(workspace: Path, tmp_path: Path) -> None:
    if why := answers("container", "system", "status"):
        pytest.skip(f"needs Apple's container running: {why}")
    built("container")
    runtimes = hmz(tmp_path / "here").runtimes
    runtimes.add(runtimes.new("apple-container", "mac"))

    seen = run(tmp_path, workspace, f"apple-container@mac{workspace}")

    done(workspace)
    contained(seen)
    assert _left() == [], "the container was left behind"

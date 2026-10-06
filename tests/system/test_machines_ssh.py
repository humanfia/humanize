"""The coding task, its agent working on `localhost` reached over a real ssh.

Named in brackets, as a host nobody saved, by user and port. Skips, saying why, where ssh to
localhost does not answer without a password (on a Mac: Remote Login on, and a key of your own
in `~/.ssh/authorized_keys`).
"""

from __future__ import annotations

import getpass
from typing import TYPE_CHECKING

import pytest

from tests.system.doubles_machines import answers, done, run

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.timeout(1800)
def test_an_agent_codes_on_localhost_over_ssh(workspace: Path, tmp_path: Path) -> None:
    host = f"{getpass.getuser()}@localhost"
    ssh = ("ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-p", "22", host)
    if why := answers(*ssh, "true"):
        pytest.skip(f"needs passwordless ssh to localhost: {why}")

    seen = run(tmp_path, workspace, f"ssh@[{host}:22]{workspace}")

    done(workspace)
    assert seen.ssh, "the machine was not reached over ssh"

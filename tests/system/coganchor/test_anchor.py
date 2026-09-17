"""Reaching a target without a command line, which takes a real supervisor to prove.

:func:`connect` is the API the flows call, and what it starts is a seccomp-filtered ptrace
supervisor -- so nothing here is answered by reading argv back. Each test below spawns a
process, or asks a machine that cannot trace to skip.

The other half of this file is `tests/unit/coganchor/test_anchor.py`: the round trip between
:class:`AnchorConfig` and the parser, which needs no kernel at all and runs everywhere.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from hmz import cli
from hmz.coganchor import AnchorConfig, check, connect
from tests.coganchor.fixtures import DEFAULT_TIMEOUT, REPO_ROOT
from tests.supervising import traced

if TYPE_CHECKING:
    from tests.coganchor.fixtures import Anchorage


def test_connect_runs_the_agent_without_a_command_line(anchorage: Anchorage) -> None:
    """The API the flows use, in a process of its own because the supervisor takes over signals."""
    anchorage.seed({"greeting.txt": "hello from the target\n"})
    config = AnchorConfig(
        target=f"local:{anchorage.target}",
        workspace=anchorage.workspace,
        shadow=str(anchorage.mirror),
    )
    program = (
        "from hmz.coganchor import AnchorConfig, connect\n"
        "raise SystemExit(connect(['bash', '-c', 'cat greeting.txt; echo back > answer.txt'],"
        f" {config!r}))\n"  # a config reads back as itself, which is how it crosses
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        timeout=DEFAULT_TIMEOUT,
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "hello from the target" in result.stdout
    assert anchorage.target_text("answer.txt") == "back\n"


def test_checking_reports_the_target_without_running_anything(
    anchorage: Anchorage, capsys: pytest.CaptureFixture[str]
) -> None:
    """What `--check` prints is what the call returns, and neither starts an agent."""
    anchorage.seed({"one.txt": "1", "two.txt": "2"})
    config = AnchorConfig(
        target=f"local:{anchorage.target}", workspace=anchorage.workspace
    )

    found = check(config)

    assert found["target"] == f"local:{anchorage.target}"
    assert found["workspace"] == anchorage.workspace
    assert found["entries"] == 2
    assert found["exports"] == [
        {"virtual": anchorage.workspace, "real": str(anchorage.target)}
    ]

    assert cli.main([*config.command(())[3:], "--check"]) == 0
    printed = capsys.readouterr().out
    assert found["target"] in printed
    assert f"{anchorage.workspace} (2 entries)" in printed


@traced
def test_connect_refuses_to_run_nothing() -> None:
    """Refused before a mirror is prepared or a target dialled, so nothing is left half done."""
    with pytest.raises(ValueError, match="no agent"):
        connect([])

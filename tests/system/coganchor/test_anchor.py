"""Reaching a target without a command line, which takes a real supervisor to prove.

:func:`connect` is the API the flows call, and what it starts is a seccomp-filtered ptrace
supervisor -- so nothing here is answered by reading argv back. Each test below spawns a
process, or asks a machine that cannot trace to skip.

The other half of this file is `tests/unit/coganchor/test_anchor.py`: the round trip between
:class:`AnchorConfig` and the parser, which needs no kernel at all and runs everywhere.
"""

from __future__ import annotations

import dataclasses
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
    from pathlib import Path

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


def test_a_command_starts_in_the_workdir_through_a_mirror_reached_by_a_symlink(
    anchorage: Anchorage, tmp_path: Path
) -> None:
    """A mirror named through a symlink, as `~/.cache` is on many machines, is the workdir.

    Where a process is, is read back by the name the kernel has for it, and a mirror matched
    only by the name it was given sent every command started in it to the target's home.
    """
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "linked").symlink_to(real)
    linked = dataclasses.replace(anchorage, mirror=tmp_path / "linked" / "mirror")

    # And a command naming the mirror by the name it was given, as a CLI told to work there
    # writes it: that name is the workdir's too.
    result = linked.shell(f"/bin/pwd; /bin/sh -c 'cd {linked.mirror} && /bin/pwd'")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [str(anchorage.target)] * 2


def test_a_command_starts_in_the_workdir_of_a_mirror_kept_inside_a_local_path(
    anchorage: Anchorage, tmp_path: Path
) -> None:
    """A mirror inside a directory kept on this machine -- humanize's home -- is the workdir.

    A container's mirrors are kept under `~/.humanize`, which never reaches a target, and a
    hole taken to cover the mirror it holds sent every command to the target's home.
    """
    kept = tmp_path / "kept"
    kept.mkdir()
    inside = dataclasses.replace(anchorage, mirror=kept / "mirror")

    result = inside.run("bash", "-c", "/bin/pwd", local_paths=(str(kept),))

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(anchorage.target)

"""Running an agent with its credentials pointed elsewhere, as far as that goes without ptrace.

`hmz internal cred` is spawned as `redirect.command` renders it. Answering the paths is a
ptrace supervisor's, which is a system test's to check; what is checked here is the line,
the refusal of a machine that cannot supervise, and the arguments the command takes.
"""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.providers import redirect

if TYPE_CHECKING:
    from pathlib import Path

PATIENCE = 60


def _run(line: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        line, capture_output=True, text=True, timeout=PATIENCE, check=False
    )


def test_a_turn_with_nothing_to_point_elsewhere_runs_as_itself(tmp_path: Path) -> None:
    marker = tmp_path / "ran"
    line = redirect.command([], ["/bin/sh", "-c", f": > {marker}"])

    assert line == ["/bin/sh", "-c", f": > {marker}"]
    assert _run(line).returncode == 0
    assert marker.exists()


def test_swaps_are_named_on_the_line_the_turn_is_spawned_as() -> None:
    line = redirect.command(
        [("/home/me/.claude/.credentials.json", "/p/creds.json")],
        ["claude", "--print"],
        kept=[("/home/me/.claude/projects", "/runs/r1/projects")],
    )

    assert line[1:5] == ["-Pm", "hmz", "internal", "cred"]
    assert "--map=/home/me/.claude/.credentials.json=/p/creds.json" in line
    assert "--keep=/home/me/.claude/projects=/runs/r1/projects" in line
    assert line[-3:] == ["--", "claude", "--print"]


@pytest.mark.skipif(
    sys.platform == "linux" and redirect.supervises(),
    reason="this machine can supervise, so the turn would run redirected",
)
def test_a_machine_that_cannot_supervise_refuses_the_turn_rather_than_run_it_unswapped(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "ran"
    line = redirect.command(
        [(str(tmp_path / "theirs.json"), str(tmp_path / "mine.json"))],
        ["/bin/sh", "-c", f": > {marker}"],
    )

    said = _run(line)

    assert said.returncode != 0
    assert "hmz internal cred" in said.stderr
    assert not marker.exists()


@pytest.mark.parametrize(
    "argv",
    [
        ["--", "true"],
        ["--map=relative=/abs", "--", "true"],
        ["--map=/abs/only", "--", "true"],
        ["--map=/a=/b"],
    ],
)
def test_a_cred_line_that_names_nothing_usable_is_a_usage_error(
    argv: list[str],
) -> None:
    said = _run([sys.executable, "-Pm", "hmz", "internal", "cred", *argv])

    assert said.returncode == 2
    assert "usage: hmz internal cred" in said.stderr

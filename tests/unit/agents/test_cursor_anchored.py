"""Where a Cursor Agent whose work is on another machine is told it works."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from hmz.coganchor import AnchorConfig
from hmz.coganchor.agents import CursorAgent, CursorAgentConfig
from hmz.coganchor.machines import AnchoredConfig

if TYPE_CHECKING:
    from pathlib import Path


def _cwd(argv: list[str]) -> str:
    """What `--workspace` was said to be, as the directory it names."""
    return os.path.normpath(argv[argv.index("--workspace") + 1])


def test_a_harness_here_is_told_its_copy_of_the_work_and_not_the_far_path(
    tmp_path: Path,
) -> None:
    """`--workspace` names a directory on the machine `cursor-agent` runs on, which is this one.

    As `mcode`'s was, found by the regression matrix (`docker_env_remote[mcode]`): a docker
    runtime on a daemon elsewhere puts the work at a path only that machine has, and the
    harness here works in its copy of it.
    """
    far = "/work/far-away"
    mirror = tmp_path / "mirror"
    anchor = AnchorConfig(target="docker://box", workspace=far, shadow=str(mirror))
    agent = CursorAgent(
        CursorAgentConfig(model="m", effort="", machine=AnchoredConfig(anchor=anchor))
    )

    argv, _prompt = agent.new(f"{far}/src")._turn("hi")

    assert _cwd(argv) == str(mirror / "src")


def test_the_target_s_own_mcode_is_told_the_path_it_has() -> None:
    """Run natively on the target, there is no copy: the far path is the one it has."""
    far = "/work/far-away"
    anchor = AnchorConfig(target="ssh://box", workspace=far, native=True)
    agent = CursorAgent(
        CursorAgentConfig(model="m", effort="", machine=AnchoredConfig(anchor=anchor))
    )

    argv, _prompt = agent.new(far)._turn("hi")

    assert _cwd(argv) == far

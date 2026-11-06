"""What a fence writes, reached and checked where it is put up again.

An agent writes the directory its scratch is in -- the temporary directory a workdir it writes
brings with it, or as here, a state directory of its own -- and so may put its scratch aside
in one turn and leave a link out of the wall at its name. Each test runs the agent for real,
under `hmz internal fence` or walled in by the supervisor that traces it, for two turns of the
same fence: the second is where a grant made by name would follow that link.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.fence import NONE, READ, Fence, enforceable, landlocked
from hmz.coganchor.providers import redirect

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.skipif(
    not enforceable(net=False), reason="this machine has nothing to fence with"
)


def _turn(
    put_up: str, fence: Fence, work: Path, script: str
) -> subprocess.CompletedProcess[str]:
    """One turn of an agent that is this Python running `script`, inside the fence."""
    if put_up == "wrapper":
        around = ["internal", "fence", f"--policy={fence.dumps()}", "--"]
    else:
        around = [
            "internal",
            "anchor",
            "--target",
            "local",
            "--workspace",
            str(work),
            f"--fence={fence.dumps()}",
        ]
    return subprocess.run(
        [sys.executable, "-Pm", "hmz", *around, sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=work,
    )


@pytest.mark.parametrize(
    "put_up",
    [
        "wrapper",
        pytest.param(
            "supervisor",
            marks=pytest.mark.skipif(
                not landlocked(net=False) or not redirect.supervises(),
                reason="this machine supervises nothing",
            ),
        ),
    ],
)
def test_a_scratch_swapped_for_a_link_out_is_refused_where_the_fence_is_put_up_again(
    tmp_path: Path, put_up: str
) -> None:
    tmp_path = tmp_path.resolve()
    home, work, state = tmp_path / "home", tmp_path / "work", tmp_path / "state"
    for one in (home, work, state):
        one.mkdir()
    scratch = state / "scratch"
    # The workdir read, the home kept out, and written only what the agent keeps of its own:
    # its state, and its scratch in it.
    fence = dataclasses.replace(
        Fence.of(
            local=READ, user=NONE, system=NONE, online=True, workdir=work, home=home
        ).granting(write=[state]),
        tmp=str(scratch),
    )
    swapped = _turn(
        put_up,
        fence,
        work,
        f"import os; os.rename({str(scratch)!r}, {str(state / 'aside')!r}); "
        f"os.symlink({str(home)!r}, {str(scratch)!r})",
    )
    assert swapped.returncode == 0, swapped.stderr

    # The next turn's fence reaches its scratch through no link a fenced program could have
    # made: refused before anything runs, and nothing written into the home.
    said = _turn(put_up, fence, work, f"open({str(scratch / 'x')!r}, 'w').write('x')")

    assert said.returncode != 0
    assert "a link where a fenced program could have made one" in said.stderr
    assert not (home / "x").exists()

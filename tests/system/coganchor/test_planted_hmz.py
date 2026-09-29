"""A package called `hmz` planted in the workdir is not the humanize a fenced turn runs.

Every turn is spawned in its workdir, which a fenced agent may write, and the first thing
started there is humanize itself -- the fence's wrapper, before its wall is up. A Python that
looked in its working directory first would run whatever `hmz` the agent left there instead.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from hmz.coganchor.fence import ALL, Fence, wrapper

if TYPE_CHECKING:
    from pathlib import Path


def test_the_wrapper_runs_the_installed_humanize_not_one_in_its_workdir(
    tmp_path: Path,
) -> None:
    planted = tmp_path / "hmz"
    planted.mkdir()
    (planted / "__init__.py").write_text("")
    (planted / "__main__.py").write_text("print('PLANTED')\n")
    fence = Fence.of(
        local=ALL, user=ALL, system=ALL, online=True, workdir=tmp_path, home=tmp_path
    )

    said = subprocess.run(
        [*wrapper(fence), "true"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert "PLANTED" not in said.stdout

"""What `Fence.explain` says a path is, checked against a program held to that fence."""

from __future__ import annotations

import shlex
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.fence import Fence, enforceable

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.skipif(
    not enforceable(net=False), reason="this machine has nothing to fence with"
)


def test_explain_agrees_with_a_program_held_to_the_fence(tmp_path: Path) -> None:
    work = tmp_path / "work"
    outside = tmp_path / "outside"
    readonly = tmp_path / "readonly"
    for made in (work, outside, readonly):
        made.mkdir()
    (readonly / "file").write_text("read\n")
    (work / "file").write_text("write\n")
    (outside / "file").write_text("denied\n")

    fence = Fence(
        read=("/",),
        write=(str(work),),
        deny=(str(outside),),
    )
    script = "; ".join(
        [
            f"read line < {shlex.quote(str(readonly / 'file'))} && echo read",
            f"echo written > {shlex.quote(str(work / 'file'))} && echo write",
            f"echo written > {shlex.quote(str(outside / 'file'))} || echo denied",
            f"read line < {shlex.quote(str(outside / 'file'))} || echo unreadable",
        ]
    )
    done = subprocess.run(
        [
            sys.executable,
            "-Pm",
            "hmz",
            "internal",
            "fence",
            f"--policy={fence.dumps()}",
            "--",
            "/bin/sh",
            "-c",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=work,
    )

    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == ["read", "write", "denied", "unreadable"]
    assert fence.explain(str(readonly / "file"))[0] == "read"
    assert fence.explain(str(work / "file"))[0] == "write"
    assert fence.explain(str(outside / "file"))[0] == "none"

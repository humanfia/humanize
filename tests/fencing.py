"""A stand-in for `hmz internal fence`, for the tiers that must not put up a real one.

A fence is Landlock and seccomp applied by the kernel, which is what `tests/system` is for: a
stand-in CLI run under a real one in `tests/integration` would be a system test CI runs, on a
runner whose kernel nobody chose. So there, :func:`standing_in` has every fenced turn spawned
under this file instead. It writes the policy it was given down -- one JSON line per turn, to
the file `HMZ_TEST_FENCE_LOG` names, where a test named one -- and becomes the program, which
then runs exactly as it would have unfenced. What a test reads back is what the turn *would*
have been held to, which is the question a driver's wiring answers.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest

#: The variable naming the file each fenced turn's policy is written to.
LOG = "HMZ_TEST_FENCE_LOG"

#: This file, which is the program the stand-in wrapper runs.
HERE = str(Path(__file__).resolve())


def _able(*, net: bool) -> bool:
    del net
    return True


def standing_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """Has every fenced turn of this process spawned under this stand-in, on any machine."""

    def wrapper(fence: Any) -> list[str]:
        return [sys.executable, HERE, f"--policy={fence.dumps()}", "--"]

    monkeypatch.setattr("hmz.coganchor.fence.wrapper", wrapper)
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", _able)


def policies(log: Path) -> list[dict[str, Any]]:
    """Every policy a fenced turn was spawned with, oldest first."""
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def _main(argv: list[str]) -> None:
    policy = argv[0].removeprefix("--policy=")
    rest = argv[2:] if argv[1:2] == ["--"] else argv[1:]
    if at := os.environ.get(LOG):
        with Path(at).open("a", encoding="utf-8") as log:
            log.write(policy + "\n")
    os.execvp(rest[0], rest)  # noqa: S606 -- becoming the program is the stand-in's errand


if __name__ == "__main__":
    _main(sys.argv[1:])

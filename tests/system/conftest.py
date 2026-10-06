"""Real agents on real tasks: optional, slow (5-30 min a test) and paid for in tokens.

Never in CI and left out of a plain `uv run pytest`; run one by naming it, e.g.
`uv run pytest tests/system/test_flows_ralph.py`. A test skips, saying why, where what it
needs -- a CLI, its sign-in, docker, ssh -- is not on this machine.

The root conftest still keeps each test's humanize home, daemon and temp dir its own; the
CLIs' own sign-ins are used in place, never copied.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from tests.system.real import SAMPLE

if TYPE_CHECKING:
    from pathlib import Path

#: The sample project the tasks are set on, not itself a test.
collect_ignore = ["sample"]


@pytest.fixture(autouse=True)
def _no_real_agents() -> None:
    """Overrides the root's: the agents installed here are what these tests run."""


@pytest.fixture(autouse=True)
def _asks_its_cli(asking: None) -> None:
    """A real run may ask its CLI what models it serves."""


@pytest.fixture(autouse=True)
def _priced(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fetches the price list, so a run's `budget.cost` can stop what it spends."""
    monkeypatch.delenv("HUMANIZE_PRICES")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A fresh git repository holding the sample project, committed once.

    `tests/test_stats.py` in it fails until `median` and `mode` are written: a task's
    outcome is checked by running `python -m pytest` there afterwards.
    """
    at = tmp_path / "stats"
    shutil.copytree(SAMPLE, at)
    for argv in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "add", "-A"],
        [
            "git",
            "-c",
            "user.name=hmz",
            "-c",
            "user.email=hmz@example.invalid",
            "commit",
            "-q",
            "-m",
            "init",
        ],
    ):
        subprocess.run(argv, cwd=at, check=True)
    return at

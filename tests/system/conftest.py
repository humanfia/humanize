"""Real agents on real tasks: optional, slow (5-30 min a test) and paid for in tokens.

Never in CI and left out of a plain `uv run pytest`; run one by naming it, e.g.
`uv run pytest tests/system/test_flows_ralph.py`. A test skips, saying why, where what it
needs -- a CLI, its sign-in, docker, ssh -- is not on this machine.

The root conftest still keeps each test's Humanize home, daemon and temp dir its own; the
CLIs' own sign-ins are used in place, never copied. Humanize ships no flow, so the loops the
tests run are installed into that home out of the real official index, as anybody's are.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from tests.conftest import as_them
from tests.system.real import SAMPLE

if TYPE_CHECKING:
    from pathlib import Path

#: The sample project the tasks are set on, not itself a test.
collect_ignore = ["sample"]

#: The loops the tests run, each a flow the official index lists.
LOOPS = ("goal", "ralph_loop", "rlar", "stateful_ralph")


@pytest.fixture(autouse=True)
def _no_real_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    """Overrides the root's: the agents installed here are what these tests run.

    As whoever runs the suite, whose `HOME` and `PATH` the suite's own stand in for between
    tests.
    """
    as_them(monkeypatch)


@pytest.fixture(autouse=True, scope="session")
def _clones_nothing_elsewhere() -> None:
    """Overrides the root's: the loops are cloned from where the official index says."""


@pytest.fixture(autouse=True)
def _loops_installed(
    _humanize_home: None, _no_real_agents: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fetches the official index and installs the loops out of it, into the test's home."""
    from hmz.runtime.flowing.index import install
    from hmz.runtime.flowing.verses import OFFICIAL, fetch

    # What the root sets to make every clone from GitHub fail at once.
    for name in ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0"):
        monkeypatch.delenv(name)
    fetch(OFFICIAL)
    for flow in LOOPS:
        install(OFFICIAL, flow)


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

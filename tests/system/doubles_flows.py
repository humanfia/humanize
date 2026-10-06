"""Running a builtin flow with `hmz exec` on a real harness, and reading what it left.

Each flow test runs the real command line in a child process, in the `workspace` repository,
on the cheapest model of whichever signed-in CLI is here -- Claude Code first, else Codex --
and then judges the run by its outcome: the sample's own tests pass, the change is in git,
the tests were left alone, and the run's record says how it ended.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime.epic import Ran, epics, read
from tests.system.real import needs

if TYPE_CHECKING:
    from pathlib import Path

#: Each harness this tries, in order, with the cheapest model it takes, at the least effort.
CHEAPEST = (("claude", "claude-haiku-4-5:low"), ("codex", "gpt-5.6-sol:low"))

#: How the sign-in of each harness is asked after, without starting a turn.
SIGNED_IN = {
    "claude": ("auth", "status"),
    "codex": ("login", "status"),
}

#: What a run may spend: a ceiling on the bill, and minutes on the clock.
COST = 1.0
MINUTES = 20

#: The task: the sample's tests describe it, and checking them is its outcome.
TASK = (
    "In this repository, implement `median` and `mode` in stats.py so that "
    "`python -m pytest` passes. Do not change anything under tests/. "
    "Keep the change small, then stop."
)


def _signed_in(cli: str, path: str) -> bool:
    """Whether `cli` says it is signed in, which costs no turn."""
    try:
        said = subprocess.run(
            [path, *SIGNED_IN[cli]],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if said.returncode != 0:
        return False
    if cli == "claude":
        try:
            return bool(json.loads(said.stdout).get("loggedIn"))
        except ValueError:
            return False
    return True


def harness(*only: str) -> str:
    """An `-a` spec for the first signed-in harness here, of `only` if given; else skips."""
    missing: list[str] = []
    for cli, model in CHEAPEST:
        if only and cli not in only:
            continue
        try:
            path = needs(cli)
        except pytest.skip.Exception:
            missing.append(f"{cli} is not installed")
            continue
        if _signed_in(cli, path):
            return f"{cli}/{model}"
        missing.append(f"{cli} is not signed in")
    pytest.skip("; ".join(missing))


def run(
    workspace: Path,
    flow: str,
    agents: dict[str, str],
    *,
    minutes: int = MINUTES,
) -> list[dict[str, Any]]:
    """Runs `flow` on `TASK` in `workspace` with `hmz exec --json`, and returns its events.

    Fails the test where the command line does not exit 0.
    """
    argv = [sys.executable, "-m", "hmz", "exec", "--json", "-f", flow]
    for role, spec in agents.items():
        argv += ["-a", f"{role}={spec}"]
    argv += [
        "-p",
        f"budget.cost={COST},budget.duration={minutes * 60}",
        TASK,
    ]
    # Its progress goes to stderr as it happens, seen with `-s`; its events are stdout.
    ran = subprocess.run(
        argv,
        cwd=workspace,
        stdout=subprocess.PIPE,
        text=True,
        # Past the budget's own clock, so the budget is what stops it, not this.
        timeout=(minutes + 5) * 60,
        check=False,
    )
    assert ran.returncode == 0, ran.stdout[-4000:]
    return [json.loads(line) for line in ran.stdout.splitlines() if line.strip()]


def ran(workspace: Path) -> Ran:
    """The record of the one run in `workspace`."""
    (epic,) = epics(workspace)
    found = read(epic)
    assert found is not None
    return found


def _git(workspace: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", *argv], cwd=workspace, capture_output=True, text=True, check=True
    ).stdout


def assert_done(workspace: Path) -> None:
    """The sample's tests pass, `stats.py` changed since the first commit, the tests did not."""
    tested = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert tested.returncode == 0, tested.stdout[-4000:]
    (root,) = _git(workspace, "rev-list", "--max-parents=0", "HEAD").split()
    changed = _git(workspace, "diff", "--name-only", root).split()
    changed += _git(workspace, "ls-files", "--others", "--exclude-standard").split()
    assert "stats.py" in changed
    touched = [
        one for one in changed if one.startswith("tests/") and "__pycache__" not in one
    ]
    assert not touched, touched

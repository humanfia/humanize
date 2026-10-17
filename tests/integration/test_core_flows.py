"""Flows named by a `git+` ref, fetched by the git on this machine out of a repository on it.

Each repository here is one in the test's own directory, reached by a `file://` URL as any
remote is; each run is a real `hmz exec`, or the runtime in this process where something has
to happen at a given moment of its fetch.
"""

from __future__ import annotations

import errno
import os
import subprocess
from pathlib import Path

import pytest

from hmz import machine
from hmz.runtime import Hmz, Refused
from tests.integration.doubles_core import hmz_exec, install, write_flow

#: A flow that needs no agent, and adds the task it was given to a list in the workspace.
FETCHED = """
from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def fetched(task, *, agents, envs, params, ctx):
    with open("fetched.txt", "a") as tasks:
        tasks.write(task + "\\n")
    return task
"""


@pytest.fixture(autouse=True)
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return install(tmp_path, monkeypatch)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """A repository holding the flow `fetched` in `fetched/`, with one commit."""
    at = tmp_path / "flows.git"
    write_flow(at, "fetched", FETCHED)
    git = ["git", "-C", str(at), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "fetched"], check=True)
    return at


def _commit(repository: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_two_runs_fetching_one_git_flow_at_once_both_get_it(
    repository: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = f"git+file://{repository}#fetched"
    renames = os.rename
    first: list[subprocess.CompletedProcess[str]] = []

    def second_to_land(
        old: str | os.PathLike[str], new: str | os.PathLike[str], **fds: int | None
    ) -> None:
        # The window two processes cloning one commit race in: this run has looked for a
        # checkout of it, found none, and is about to rename its own clone into place. The
        # other run, started here, lands its checkout first.
        clone = Path(old)
        cloned = clone.name.startswith(".") and clone.parent.parent.name == "pinned"
        if cloned and not first:
            first.append(hmz_exec("-f", ref, "-p", "budget.cost=1", "first"))
        renames(old, new, **fds)

    monkeypatch.setattr(os, "rename", second_to_land)

    said = Hmz(project).exec(["-f", ref, "-p", "budget.cost=1", "second"])

    (ran,) = first
    assert ran.returncode == 0, ran.stderr
    assert said == "second"
    assert (project / "fetched.txt").read_text() == "first\nsecond\n"
    # One checkout of the commit, the first run's, and no clone left beside it.
    (kept,) = (machine() / "pinned").iterdir()
    assert [one.name for one in kept.iterdir()] == [_commit(repository)]


@pytest.mark.parametrize(
    ("failing", "there"),
    [(errno.ENOTEMPTY, "unrelated"), (errno.EACCES, ".git")],
    ids=["no-checkout-landed", "another-error"],
)
def test_a_clone_that_cannot_be_renamed_into_place_is_not_fetched(
    repository: Path,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing: int,
    there: str,
) -> None:
    ref = f"git+file://{repository}#fetched"
    renames = os.rename

    def refused(
        old: str | os.PathLike[str], new: str | os.PathLike[str], **fds: int | None
    ) -> None:
        # Something other than a checkout of the commit in the way of this run's clone; or,
        # where there is one, the rename failing for another reason.
        clone = Path(old)
        if clone.name.startswith(".") and clone.parent.parent.name == "pinned":
            (Path(new) / there).mkdir(parents=True)
            raise OSError(failing, os.strerror(failing), str(new))
        renames(old, new, **fds)

    monkeypatch.setattr(os, "rename", refused)

    with pytest.raises(Refused, match=rf"could not be fetched: \[Errno {failing}\]"):
        Hmz(project).exec(["-f", ref, "-p", "budget.cost=1", "go"])

    assert not (project / "fetched.txt").exists()
    # This run's clone is removed all the same.
    (kept,) = (machine() / "pinned").iterdir()
    assert [one.name for one in kept.iterdir()] == [_commit(repository)]

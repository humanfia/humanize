"""Humanize's state directory on another machine, as its own `/bin/sh` finds and fills it.

The probe of a host and a Slurm job's batch step run here under a home of the test's own,
holding what each released Humanize left there.
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.transport import REMOTE_STATE
from hmz.runtime.flowing.environing_ssh import PROBE_SCRIPT, facts_of

if TYPE_CHECKING:
    from pathlib import Path


def _ran(script: str, home: Path, **environ: str) -> str:
    """What `script` printed, run by `/bin/sh` with `home` as its home and nothing else set."""
    return subprocess.run(
        ["/bin/sh", "-c", script],
        env={"HOME": str(home), "PATH": os.environ["PATH"], **environ},
        cwd="/",
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _seeded(at: Path) -> Path:
    """A `envs/` under `at` holding one file, which is returned."""
    kept = at / "envs" / "x-0123" / "file"
    kept.parent.mkdir(parents=True)
    kept.write_text("kept")
    return kept


@pytest.mark.parametrize("old", [".hmz", ".humanize"])
def test_a_host_s_old_envs_are_moved_into_its_xdg_state_directory(
    tmp_path: Path, old: str
) -> None:
    _seeded(tmp_path / old)

    facts = facts_of(_ran(PROBE_SCRIPT, tmp_path))

    assert facts.state == tmp_path / ".local" / "state" / "humanize"
    assert (tmp_path / ".local/state/humanize/envs/x-0123/file").read_text() == "kept"
    assert not (tmp_path / old).exists()


def test_the_state_directory_follows_an_absolute_xdg_state_home_only(
    tmp_path: Path,
) -> None:
    _seeded(tmp_path / ".hmz")

    said = _ran(PROBE_SCRIPT, tmp_path, XDG_STATE_HOME=f"{tmp_path}/st")

    assert facts_of(said).state == tmp_path / "st" / "humanize"
    assert (tmp_path / "st" / "humanize" / "envs" / "x-0123" / "file").is_file()
    said = _ran(PROBE_SCRIPT, tmp_path, XDG_STATE_HOME="st")
    assert facts_of(said).state == tmp_path / ".local" / "state" / "humanize"


@pytest.mark.parametrize("named", ["elsewhere", "{home}/elsewhere"])
def test_envs_under_a_humanize_home_that_was_set_are_moved_too(
    tmp_path: Path, named: str
) -> None:
    _seeded(tmp_path / "elsewhere")
    _seeded(tmp_path / ".hmz")

    _ran(PROBE_SCRIPT, tmp_path, HUMANIZE_HOME=named.format(home=tmp_path))

    assert (tmp_path / ".local/state/humanize/envs/x-0123/file").is_file()
    assert not (tmp_path / "elsewhere").exists()
    assert (tmp_path / ".hmz" / "envs").is_dir()


def test_envs_already_in_the_state_directory_are_never_merged_into(
    tmp_path: Path,
) -> None:
    old = _seeded(tmp_path / ".hmz")
    _seeded(tmp_path / ".local" / "state" / "humanize").write_text("new")

    _ran(PROBE_SCRIPT, tmp_path)

    assert old.read_text() == "kept"
    assert (tmp_path / ".local/state/humanize/envs/x-0123/file").read_text() == "new"
    assert sorted(
        p.name for p in (tmp_path / ".local/state/humanize/envs").iterdir()
    ) == ["x-0123"]


def test_an_old_home_holding_more_than_envs_is_kept(tmp_path: Path) -> None:
    _seeded(tmp_path / ".hmz")
    (tmp_path / ".hmz" / "settings.yaml").write_text("")

    _ran(PROBE_SCRIPT, tmp_path)

    assert (tmp_path / ".local/state/humanize/envs/x-0123/file").is_file()
    assert sorted(p.name for p in (tmp_path / ".hmz").iterdir()) == ["settings.yaml"]


def test_a_slurm_job_moves_and_names_the_same_directory(tmp_path: Path) -> None:
    _seeded(tmp_path / ".hmz")

    said = _ran(f'{REMOTE_STATE}printf "%s\\n" "$s/envs"', tmp_path)

    assert said == f"{tmp_path}/.local/state/humanize/envs\n"
    assert (tmp_path / ".local/state/humanize/envs/x-0123/file").is_file()


def test_a_worktree_that_was_moved_is_still_its_repository_s(tmp_path: Path) -> None:
    repo, old = (
        tmp_path / "repo",
        tmp_path / ".hmz" / "envs" / "p-0123" / "worktrees" / "w",
    )
    for argv in (
        ["init", "-q", str(repo)],
        ["-C", str(repo), "commit", "-q", "--allow-empty", "-m", "first"],
        ["-C", str(repo), "worktree", "add", "-q", "--detach", str(old)],
    ):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *argv], check=True
        )

    _ran(PROBE_SCRIPT, tmp_path)

    listed = subprocess.run(
        ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    moved = tmp_path / ".local/state/humanize/envs/p-0123/worktrees/w"
    assert f"worktree {moved.resolve()}\n" in listed
    assert "prunable" not in listed

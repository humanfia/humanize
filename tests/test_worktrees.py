"""Parallel writer jobs in Git worktrees: leases, isolation, reckoning, integration, publish.

Every writer here is a small Python script rather than a real agent: what the coordinator
promises is about processes, worktrees and commits, so a script that writes files -- and
waits, and exits how it is told -- proves all of it without a token being spent.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from hmz import runner

#: The identity the tests themselves commit as, pinned the same way the coordinator pins
#: its own, so no machine's Git configuration is consulted.
AS_TEST = (
    "-c",
    "user.name=Someone",
    "-c",
    "user.email=someone@example.com",
    "-c",
    "commit.gpgsign=false",
)

#: What every fake writer script starts with: a way to wait for a file another writer
#: makes -- with a deadline, so a broken rendezvous fails a test instead of hanging it --
#: and a way to run Git as itself.
PROLOGUE = """\
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def wait_for(path):
    deadline = time.monotonic() + 30
    while not Path(path).exists():
        if time.monotonic() > deadline:
            sys.exit(9)
        time.sleep(0.01)


def git(*args):
    return subprocess.run(
        ["git", "-c", "user.name=w", "-c", "user.email=w@example.com",
         "-c", "commit.gpgsign=false", *args],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
"""


def _git(cwd: Path, *args: str) -> str:
    """Runs Git for the test's own setup and reading back, failing loudly."""
    done = subprocess.run(
        ["git", *AS_TEST, *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def _writer(tmp_path: Path, name: str, body: str) -> tuple[str, ...]:
    """A writer job's argv: a Python script that is the whole of the job."""
    script = tmp_path / f"{name}_writer.py"
    script.write_text(PROLOGUE + body)
    return (sys.executable, str(script))


def _job(tmp_path: Path, name: str, body: str) -> runner.WorktreeJob:
    """A writer job made of such a script, under the name its results answer to."""
    return runner.WorktreeJob(name=name, argv=_writer(tmp_path, name, body))


def _managed() -> Path:
    """Where a run keeps its worktrees, as the conftest home pins it."""
    return Path(os.environ["HUMANIZE_HOME"]) / "worktrees"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A clean repository on `main` with one commit, and the test standing inside it."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "--initial-branch=main")
    (root / ".gitignore").write_text("junk/\n")
    (root / "base.txt").write_text("baseline\n")
    (root / "second.txt").write_text("second\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "baseline")
    monkeypatch.chdir(root)
    return root


def test_a_run_pins_the_repository_branch_and_base_it_started_from(
    repo: Path, tmp_path: Path
) -> None:
    base = _git(repo, "rev-parse", "HEAD")

    result = runner.run_worktrees(
        [_job(tmp_path, "one", "Path('made.txt').write_text('made')\n")]
    )

    assert result.status == "published"
    assert Path(result.repo_root).resolve() == repo.resolve()
    assert result.target_branch == "main"
    assert result.base_sha == base  # as pinned, though the branch has since moved
    assert result.published_sha == _git(repo, "rev-parse", "HEAD")
    assert result.published_sha != base
    assert result.error is None
    assert (repo / "made.txt").read_text() == "made"

    (job,) = result.jobs
    assert job.name == "one"
    assert job.status == "committed"
    assert job.returncode == 0
    assert job.changed_paths == ("made.txt",)
    assert job.source_commit is not None
    assert job.integrated_commit == result.published_sha
    assert job.error is None


def test_a_run_is_refused_outside_a_git_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "plain"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    with pytest.raises(ValueError, match="repository"):
        runner.run_worktrees([runner.WorktreeJob(name="one", argv=("true",))])

    assert not _managed().exists()


def test_a_run_is_refused_when_git_cannot_be_run(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))

    with pytest.raises(ValueError, match="git"):
        runner.run_worktrees([runner.WorktreeJob(name="one", argv=("true",))])

    assert not _managed().exists()


def test_a_run_is_refused_on_a_detached_head(repo: Path, tmp_path: Path) -> None:
    _git(repo, "checkout", "--detach")

    with pytest.raises(ValueError, match="detached"):
        runner.run_worktrees([runner.WorktreeJob(name="one", argv=("true",))])

    assert not _managed().exists()


def test_a_run_is_refused_before_the_first_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unborn = tmp_path / "unborn"
    unborn.mkdir()
    _git(unborn, "init", "--initial-branch=main")
    monkeypatch.chdir(unborn)

    with pytest.raises(ValueError, match="HEAD"):
        runner.run_worktrees([runner.WorktreeJob(name="one", argv=("true",))])

    assert not _managed().exists()


@pytest.mark.parametrize("left", ["staged", "unstaged", "untracked"])
def test_a_run_is_refused_while_the_working_tree_is_not_clean(
    repo: Path, tmp_path: Path, left: str
) -> None:
    if left == "untracked":
        (repo / "stray.txt").write_text("stray\n")
    else:
        (repo / "base.txt").write_text("edited\n")
        if left == "staged":
            _git(repo, "add", "base.txt")

    with pytest.raises(ValueError, match="clean"):
        runner.run_worktrees([runner.WorktreeJob(name="one", argv=("true",))])

    assert not _managed().exists()


@pytest.mark.parametrize(
    ("jobs", "checks", "at_once", "complaint"),
    [
        ((), (), 0, "at least one job"),
        ((("", ("true",)),), (), 0, "name"),
        ((("twin", ("true",)), ("twin", ("true",))), (), 0, "unique"),
        ((("one", ()),), (), 0, "command"),
        ((("one", ("true",)),), ((),), 0, "check"),
        ((("one", ("true",)),), (), -1, "at_once"),
    ],
)
def test_arguments_nothing_should_be_built_from_are_refused_first(
    repo: Path,
    jobs: tuple[tuple[str, tuple[str, ...]], ...],
    checks: tuple[tuple[str, ...], ...],
    at_once: int,
    complaint: str,
) -> None:
    made = [runner.WorktreeJob(name=name, argv=argv) for name, argv in jobs]

    with pytest.raises(ValueError, match=complaint):
        runner.run_worktrees(made, checks=checks, at_once=at_once)

    assert not _managed().exists()


def test_worktrees_are_refused_a_home_inside_the_repository(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_HOME", str(repo / ".humanize"))

    with pytest.raises(ValueError, match="inside the repository"):
        runner.run_worktrees([runner.WorktreeJob(name="one", argv=("true",))])

    assert not (repo / ".humanize").exists()


def test_two_writers_share_a_base_and_nothing_else(repo: Path, tmp_path: Path) -> None:
    """The same relative path, two different contents, and each writer reads only its own."""
    base = _git(repo, "rev-parse", "HEAD")
    seen = tmp_path / "seen"
    seen.mkdir()

    def sharing(name: str, other: str) -> str:
        return f"""
seen = {{
    "cwd": os.getcwd(),
    "head": git("rev-parse", "HEAD"),
    "base": Path("base.txt").read_text(),
}}
Path("shared.txt").write_text({name!r})
Path({str(seen)!r}, {name!r} + ".wrote").write_text("")
wait_for(Path({str(seen)!r}, {other!r} + ".wrote"))
seen["shared"] = Path("shared.txt").read_text()
Path({str(seen)!r}, {name!r} + ".json").write_text(json.dumps(seen))
"""

    result = runner.run_worktrees(
        [
            _job(tmp_path, "left", sharing("left", "right")),
            _job(tmp_path, "right", sharing("right", "left")),
        ]
    )

    told = {
        name: json.loads((seen / f"{name}.json").read_text())
        for name in ("left", "right")
    }
    # Each writer worked in the worktree assigned to it, leased at the shared base.
    for index, name in enumerate(("left", "right")):
        path = result.jobs[index].worktree_path
        assert path is not None
        assert Path(told[name]["cwd"]).resolve() == Path(path).resolve()
        assert told[name]["head"] == base
        assert told[name]["base"] == "baseline\n"
        assert told[name]["shared"] == name  # never the other's, however overlapped
    assert told["left"]["cwd"] != told["right"]["cwd"]

    # Both snapshots were vouched for; only their integration collided.
    assert [job.status for job in result.jobs] == ["committed", "committed"]
    assert result.status == "failed"
    assert result.error is not None
    assert "integrating right" in result.error
    assert result.jobs[0].integrated_commit is not None
    assert result.jobs[1].integrated_commit is None

    # The main worktree never saw either writer's file, and the branch never moved.
    assert not (repo / "shared.txt").exists()
    assert _git(repo, "rev-parse", "HEAD") == base

    # The whole scene is kept: both writers, and the conflict as Git stopped in it.
    assert len(result.kept_paths) == 3
    integration = Path(result.kept_paths[-1])
    assert integration.name == "integration"
    trace = _git(integration, "rev-parse", "--git-path", "CHERRY_PICK_HEAD")
    assert (integration / trace).exists()  # nothing ran `cherry-pick --abort`


def test_a_job_can_be_the_hmz_exec_line_it_already_was(
    repo: Path, tmp_path: Path
) -> None:
    """The coordinator hands the argv a worktree for a cwd, and everything else stands."""
    flow = tmp_path / "flow.py"
    flow.write_text(
        "from pathlib import Path\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n"
        "\n"
        "\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    Path('flowed.txt').write_text(task)\n"
    )

    result = runner.run_worktrees(
        [
            runner.WorktreeJob(
                name="flowed",
                argv=(
                    sys.executable,
                    "-m",
                    "hmz",
                    "exec",
                    "-f",
                    str(flow),
                    "-a",
                    "claude/m:high",
                    "what the flow was told",
                ),
            )
        ]
    )

    assert result.status == "published"
    assert (repo / "flowed.txt").read_text() == "what the flow was told"


def test_writers_run_at_most_at_once_at_a_time(repo: Path, tmp_path: Path) -> None:
    seen = tmp_path / "seen"
    seen.mkdir()
    first = _job(
        tmp_path,
        "first",
        f"""
told = {{"second_had_started": Path({str(seen)!r}, "second.start").exists()}}
Path("first.txt").write_text("first")
Path({str(seen)!r}, "first.json").write_text(json.dumps(told))
Path({str(seen)!r}, "first.done").write_text("")
""",
    )
    second = _job(
        tmp_path,
        "second",
        f"""
Path({str(seen)!r}, "second.start").write_text("")
told = {{"first_was_done": Path({str(seen)!r}, "first.done").exists()}}
Path("second.txt").write_text("second")
Path({str(seen)!r}, "second.json").write_text(json.dumps(told))
""",
    )

    result = runner.run_worktrees([first, second], at_once=1)

    assert result.status == "published"
    assert json.loads((seen / "first.json").read_text()) == {
        "second_had_started": False
    }
    assert json.loads((seen / "second.json").read_text()) == {"first_was_done": True}


def test_results_keep_the_order_the_jobs_were_given(repo: Path, tmp_path: Path) -> None:
    """Input order, not finishing order: `early` is held until `late` is already done."""
    base = _git(repo, "rev-parse", "HEAD")
    seen = tmp_path / "seen"
    seen.mkdir()
    early = _job(
        tmp_path,
        "early",
        f"""
wait_for(Path({str(seen)!r}, "late.done"))
Path("early.txt").write_text("early")
""",
    )
    late = _job(
        tmp_path,
        "late",
        f"""
Path("late.txt").write_text("late")
Path({str(seen)!r}, "late.done").write_text("")
""",
    )

    result = runner.run_worktrees([early, late])

    assert result.status == "published"
    assert [job.name for job in result.jobs] == ["early", "late"]
    # And integration went in that same order: early's commit sits under late's.
    listed = _git(repo, "log", "--reverse", "--format=%s", f"{base}..HEAD")
    assert listed.splitlines() == [
        "humanize worktree: early",
        "humanize worktree: late",
    ]
    assert result.jobs[1].integrated_commit == result.published_sha
    assert (
        _git(repo, "rev-parse", f"{result.published_sha}^")
        == result.jobs[0].integrated_commit
    )


def test_one_failing_writer_keeps_every_result_out_of_the_target_branch(
    repo: Path, tmp_path: Path
) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    ok = _job(tmp_path, "ok", "Path('ok.txt').write_text('ok')\n")
    bad = _job(tmp_path, "bad", "Path('bad.txt').write_text('bad')\nsys.exit(5)\n")

    result = runner.run_worktrees([ok, bad])

    assert result.status == "failed"
    assert [job.returncode for job in result.jobs] == [0, 5]
    assert [job.status for job in result.jobs] == ["finished", "failed"]
    assert result.jobs[1].error is not None
    assert "exited 5" in result.jobs[1].error
    assert _git(repo, "rev-parse", "HEAD") == base

    # The ok writer was waited to its end and its scene kept exactly as it left it:
    # its file on disk, nothing committed, nothing staged by anybody else.
    ok_path = result.jobs[0].worktree_path
    assert ok_path is not None
    assert (Path(ok_path) / "ok.txt").read_text() == "ok"
    assert _git(Path(ok_path), "rev-parse", "HEAD") == base
    assert result.kept_paths == tuple(str(job.worktree_path) for job in result.jobs)
    assert not (Path(ok_path).parent / "integration").exists()


def test_a_writer_that_cannot_start_is_a_failure_that_keeps_the_scene(
    repo: Path, tmp_path: Path
) -> None:
    base = _git(repo, "rev-parse", "HEAD")

    result = runner.run_worktrees(
        [runner.WorktreeJob(name="nowhere", argv=(str(tmp_path / "no-such-binary"),))]
    )

    assert result.status == "failed"
    (job,) = result.jobs
    assert job.status == "failed"
    assert job.returncode is None
    assert job.error is not None
    assert "cannot start" in job.error
    assert job.worktree_path is not None
    assert Path(job.worktree_path).is_dir()
    assert _git(repo, "rev-parse", "HEAD") == base


def test_a_writer_ended_by_a_signal_is_a_failure(repo: Path, tmp_path: Path) -> None:
    result = runner.run_worktrees([_job(tmp_path, "cut", "os.kill(os.getpid(), 9)\n")])

    assert result.status == "failed"
    (job,) = result.jobs
    assert job.status == "failed"
    assert job.returncode == -signal.SIGKILL
    assert job.error is not None
    assert "signal" in job.error


def test_a_worktree_that_cannot_be_leased_stops_the_run_before_any_writer(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = tmp_path / "seen"
    seen.mkdir()
    jobs = [
        _job(tmp_path, name, f"Path({str(seen)!r}, {name!r}).write_text('ran')\n")
        for name in ("one", "two")
    ]
    real = runner._git
    leased: list[str] = []

    def failing(cwd: Path, *args: str, action: str) -> str:
        if args[:2] == ("worktree", "add"):
            leased.append(args[3])
            if len(leased) == 2:
                raise runner._GitError(action, cwd, 128, "no room")
        return real(cwd, *args, action=action)

    monkeypatch.setattr(runner, "_git", failing)

    result = runner.run_worktrees(jobs)

    assert result.status == "failed"
    assert result.error is not None
    assert "leasing a worktree for two" in result.error
    assert [job.status for job in result.jobs] == ["not_started", "not_started"]
    one, two = result.jobs
    assert one.worktree_path is not None
    assert Path(one.worktree_path).is_dir()  # the first lease is kept for a look
    assert result.kept_paths == (one.worktree_path,)
    assert two.worktree_path is None
    assert list(seen.iterdir()) == []  # no writer ever ran


def test_an_interrupt_ends_the_writers_and_keeps_what_was_made(
    repo: Path, tmp_path: Path
) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    seen = tmp_path / "seen"
    seen.mkdir()
    jobs = [
        _job(
            tmp_path,
            name,
            f"""
Path({str(seen)!r}, {name!r} + ".pid").write_text(str(os.getpid()))
time.sleep(60)
""",
        )
        for name in ("one", "two")
    ]

    def interrupt_once_started() -> None:
        deadline = time.monotonic() + 20
        while not all((seen / f"{name}.pid").exists() for name in ("one", "two")):
            assert time.monotonic() < deadline, "the writers never started"
            time.sleep(0.01)
        os.kill(os.getpid(), signal.SIGINT)

    interrupter = threading.Thread(target=interrupt_once_started)
    interrupter.start()
    try:
        with pytest.raises(KeyboardInterrupt):
            runner.run_worktrees(jobs)
    finally:
        interrupter.join()

    # Both writers were terminated and waited for, not left running into whatever ran next.
    for name in ("one", "two"):
        pid = int((seen / f"{name}.pid").read_text())
        deadline = time.monotonic() + 10
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            assert time.monotonic() < deadline, f"writer {name} is still running"
            time.sleep(0.01)

    # No Git closing happened: the worktrees stand at the base, and nothing integrated.
    (run_dir,) = _managed().iterdir()
    kept = sorted(path.name for path in run_dir.iterdir())
    assert kept == ["writer-0", "writer-1"]
    for name in kept:
        assert _git(run_dir / name, "rev-parse", "HEAD") == base
    assert _git(repo, "rev-parse", "HEAD") == base


def test_everything_a_writer_leaves_becomes_one_commit_on_the_base(
    repo: Path, tmp_path: Path
) -> None:
    """Staged, unstaged and deleted alike: the snapshot is the worktree, not the index."""
    base = _git(repo, "rev-parse", "HEAD")
    job = _job(
        tmp_path,
        "mixed",
        """
Path("base.txt").write_text("edited\\n")
Path("new.txt").write_text("new\\n")
git("add", "new.txt")
Path("second.txt").unlink()
""",
    )

    result = runner.run_worktrees([job])

    assert result.status == "published"
    (job_result,) = result.jobs
    assert sorted(job_result.changed_paths) == ["base.txt", "new.txt", "second.txt"]
    # One commit, with the base for its one parent.
    assert _git(repo, "rev-list", "--parents", "-n", "1", "HEAD").split() == [
        result.published_sha,
        base,
    ]
    assert (repo / "base.txt").read_text() == "edited\n"
    assert (repo / "new.txt").read_text() == "new\n"
    assert not (repo / "second.txt").exists()


def test_a_writers_own_commits_are_flattened_into_the_one_result(
    repo: Path, tmp_path: Path
) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    job = _job(
        tmp_path,
        "chatty",
        """
Path("a.txt").write_text("a")
git("add", "-A")
git("commit", "-m", "first of mine")
Path("b.txt").write_text("b")
git("add", "-A")
git("commit", "-m", "second of mine")
Path("c.txt").write_text("c")
""",
    )

    result = runner.run_worktrees([job])

    assert result.status == "published"
    assert _git(repo, "rev-list", "--count", f"{base}..HEAD") == "1"
    assert _git(repo, "log", "-1", "--format=%s") == "humanize worktree: chatty"
    for made in ("a.txt", "b.txt", "c.txt"):
        assert (repo / made).is_file()
    assert sorted(result.jobs[0].changed_paths) == ["a.txt", "b.txt", "c.txt"]


def test_the_result_commit_is_made_as_humanize_and_nobody_else(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pinned identity per command, and no reading or writing of anybody's config."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Not the author")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "not-author@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Not the committer")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "not-committer@example.com")

    result = runner.run_worktrees(
        [_job(tmp_path, "one", "Path('made.txt').write_text('made')\n")]
    )

    assert result.status == "published"
    assert _git(repo, "log", "-1", "--format=%an %ae %cn %ce") == (
        "humanize humanize@localhost humanize humanize@localhost"
    )
    # And no configuration was written to make that so.
    unset = subprocess.run(
        ["git", "config", "--local", "user.name"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert unset.returncode == 1


def test_a_writer_that_changed_nothing_is_no_change_and_no_empty_commit(
    repo: Path, tmp_path: Path
) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    idle = _job(tmp_path, "idle", "pass\n")
    busy = _job(tmp_path, "busy", "Path('busy.txt').write_text('busy')\n")

    result = runner.run_worktrees([idle, busy])

    assert result.status == "published"
    quiet, worked = result.jobs
    assert quiet.status == "no_change"
    assert quiet.source_commit is None
    assert quiet.integrated_commit is None
    assert quiet.changed_paths == ()
    assert worked.status == "committed"
    # The idle job was skipped, not committed empty: one commit stands over the base.
    assert _git(repo, "rev-list", "--count", f"{base}..HEAD") == "1"


def test_a_run_of_only_no_change_jobs_is_unchanged_after_its_checks(
    repo: Path, tmp_path: Path
) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    checked_in = tmp_path / "checked_in.txt"

    result = runner.run_worktrees(
        [_job(tmp_path, "idle", "pass\n")],
        checks=[
            (
                sys.executable,
                "-c",
                (
                    "import os, sys, pathlib; pathlib.Path(sys.argv[1])"
                    ".write_text(os.getcwd())"
                ),
                str(checked_in),
            )
        ],
    )

    assert result.status == "unchanged"
    assert result.published_sha is None
    assert _git(repo, "rev-parse", "HEAD") == base
    # The checks still ran, from the base, in the integration worktree.
    assert Path(checked_in.read_text()).name == "integration"
    assert [check.returncode for check in result.checks] == [0]
    # A fully successful run cleans up after itself, unchanged or not.
    assert result.kept_paths == ()
    assert result.cleanup_errors == ()
    assert not _managed().exists() or not any(_managed().iterdir())


def test_a_writer_that_moved_onto_a_branch_is_refused(
    repo: Path, tmp_path: Path
) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    job = _job(
        tmp_path,
        "escapee",
        """
git("checkout", "-b", "mine")
Path("x.txt").write_text("x")
""",
    )

    result = runner.run_worktrees([job])

    assert result.status == "failed"
    (job_result,) = result.jobs
    assert job_result.status == "failed"
    assert job_result.error is not None
    assert "branch 'mine'" in job_result.error
    # The scene is exactly as the writer left it: still on its branch, file untouched,
    # nothing reset and nothing committed by anybody else.
    assert job_result.worktree_path is not None
    kept = Path(job_result.worktree_path)
    assert _git(kept, "symbolic-ref", "--short", "HEAD") == "mine"
    assert (kept / "x.txt").read_text() == "x"
    assert _git(repo, "rev-parse", "HEAD") == base


def test_a_writer_whose_head_left_the_bases_line_is_refused(
    repo: Path, tmp_path: Path
) -> None:
    (repo / "grown.txt").write_text("grown\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "growth")
    job = _job(
        tmp_path,
        "adrift",
        """
git("reset", "--hard", "HEAD~1")
Path("x.txt").write_text("x")
""",
    )

    result = runner.run_worktrees([job])

    assert result.status == "failed"
    (job_result,) = result.jobs
    assert job_result.status == "failed"
    assert job_result.error is not None
    assert "descend" in job_result.error


def test_a_writer_left_mid_cherry_pick_is_refused(repo: Path, tmp_path: Path) -> None:
    _git(repo, "checkout", "-b", "side")
    (repo / "base.txt").write_text("the side's line\n")
    _git(repo, "commit", "-am", "the side's edit")
    _git(repo, "checkout", "main")
    job = _job(
        tmp_path,
        "tangled",
        """
Path("base.txt").write_text("my line\\n")
git("commit", "-am", "my edit")
git("cherry-pick", "side")
""",
    )

    result = runner.run_worktrees([job])

    assert result.status == "failed"
    (job_result,) = result.jobs
    assert job_result.status == "failed"
    assert job_result.error is not None
    assert "CHERRY_PICK_HEAD" in job_result.error
    # And the half-done operation still stands in the worktree for whoever comes to look.
    assert job_result.worktree_path is not None
    kept = Path(job_result.worktree_path)
    trace = _git(kept, "rev-parse", "--git-path", "CHERRY_PICK_HEAD")
    assert (kept / trace).exists()


def test_checks_run_in_order_in_the_integration_worktree(
    repo: Path, tmp_path: Path
) -> None:
    """Each check sees the integrated work, from the integration worktree, in turn."""
    log = tmp_path / "checks.log"
    note = (
        "import os, sys, pathlib; f = open(sys.argv[1], 'a');"
        " f.write(sys.argv[2] + ' ' + os.getcwd() + chr(10)); f.close();"
        " sys.exit(0 if pathlib.Path('made.txt').is_file() else 1)"
    )
    first = (sys.executable, "-c", note, str(log), "first")
    second = (sys.executable, "-c", note, str(log), "second")

    result = runner.run_worktrees(
        [_job(tmp_path, "one", "Path('made.txt').write_text('made')\n")],
        checks=[first, second],
    )

    assert result.status == "published"
    assert [check.argv for check in result.checks] == [first, second]
    assert [check.returncode for check in result.checks] == [0, 0]
    assert all(check.error is None for check in result.checks)
    lines = log.read_text().splitlines()
    assert [line.split()[0] for line in lines] == ["first", "second"]
    ran_in = {Path(line.split(maxsplit=1)[1]) for line in lines}
    assert len(ran_in) == 1
    assert next(iter(ran_in)).name == "integration"


def test_a_failing_check_stops_the_run_before_the_next_check(
    repo: Path, tmp_path: Path
) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    log = tmp_path / "checks.log"
    result = runner.run_worktrees(
        [_job(tmp_path, "one", "Path('made.txt').write_text('made')\n")],
        checks=[
            (sys.executable, "-c", "import sys; sys.exit(3)"),
            (
                sys.executable,
                "-c",
                "import sys, pathlib; pathlib.Path(sys.argv[1]).write_text('ran')",
                str(log),
            ),
        ],
    )

    assert result.status == "failed"
    assert result.published_sha is None
    assert result.error is not None
    assert "exited 3" in result.error
    # Only the check that ran has a result; the one after it never started.
    (failed,) = result.checks
    assert failed.returncode == 3
    assert not log.exists()
    # Nothing was published, and the whole scene stands for whoever comes to look.
    assert _git(repo, "rev-parse", "HEAD") == base
    assert len(result.kept_paths) == 2


def test_a_check_that_cannot_start_fails_the_run(repo: Path, tmp_path: Path) -> None:
    nowhere = str(tmp_path / "no-such-check")
    result = runner.run_worktrees(
        [_job(tmp_path, "one", "Path('made.txt').write_text('made')\n")],
        checks=[(nowhere,)],
    )

    assert result.status == "failed"
    (check,) = result.checks
    assert check.returncode is None
    assert check.error is not None
    assert "cannot start" in check.error


def test_a_check_that_dirties_the_integration_worktree_blocks_publishing(
    repo: Path, tmp_path: Path
) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    result = runner.run_worktrees(
        [_job(tmp_path, "one", "Path('made.txt').write_text('made')\n")],
        checks=[
            (
                sys.executable,
                "-c",
                "import pathlib; pathlib.Path('litter.txt').write_text('litter')",
            )
        ],
    )

    assert result.status == "failed"
    assert result.error is not None
    assert "left the integration worktree dirty" in result.error
    assert "litter.txt" in result.error
    assert _git(repo, "rev-parse", "HEAD") == base


def test_publishing_is_refused_when_the_branch_moved_during_the_run(
    repo: Path, tmp_path: Path
) -> None:
    """A concurrent commit on the target branch is theirs to keep, not ours to fight."""
    # The mover: a check that commits to the main repository while the run is underway,
    # which is exactly the window between integration and publishing.
    moved = (
        "git",
        *AS_TEST,
        "-C",
        str(repo),
        "commit",
        "--allow-empty",
        "-m",
        "raced ahead",
    )

    result = runner.run_worktrees(
        [_job(tmp_path, "one", "Path('made.txt').write_text('made')\n")],
        checks=[moved],
    )

    assert result.status == "failed"
    assert result.error is not None
    assert "moved while the run was underway" in result.error
    assert result.published_sha is None
    # No rollback: the concurrent commit stands, and the writer's work is kept aside.
    assert _git(repo, "log", "-1", "--format=%s") == "raced ahead"
    assert not (repo / "made.txt").exists()
    assert len(result.kept_paths) == 2


def test_publishing_is_refused_when_the_main_workspace_turned_dirty(
    repo: Path, tmp_path: Path
) -> None:
    stray = (
        sys.executable,
        "-c",
        "import pathlib, sys; pathlib.Path(sys.argv[1]).write_text('stray')",
        str(repo / "stray.txt"),
    )

    result = runner.run_worktrees(
        [_job(tmp_path, "one", "Path('made.txt').write_text('made')\n")],
        checks=[stray],
    )

    assert result.status == "failed"
    assert result.error is not None
    assert "changed while the run was underway" in result.error
    assert "stray.txt" in result.error
    # The stray file is the caller's business: left exactly where it was put.
    assert (repo / "stray.txt").read_text() == "stray"
    assert not (repo / "made.txt").exists()


def test_an_unchanged_run_is_refused_when_the_branch_moved_during_its_checks(
    repo: Path, tmp_path: Path
) -> None:
    moved = (
        "git",
        *AS_TEST,
        "-C",
        str(repo),
        "commit",
        "--allow-empty",
        "-m",
        "raced ahead",
    )

    result = runner.run_worktrees([_job(tmp_path, "idle", "pass\n")], checks=[moved])

    assert result.status == "failed"
    assert result.error is not None
    assert "moved while the run was underway" in result.error
    assert result.published_sha is None
    assert _git(repo, "log", "-1", "--format=%s") == "raced ahead"
    assert len(result.kept_paths) == 2


def test_a_published_run_clears_its_worktrees_even_of_ignored_leavings(
    repo: Path, tmp_path: Path
) -> None:
    """Build caches and the like are ignored files; `remove --force` may clear those."""
    job = _job(
        tmp_path,
        "builder",
        """
Path("made.txt").write_text("made")
Path("junk").mkdir()
Path("junk", "cache.bin").write_bytes(b"x" * 64)
""",
    )

    result = runner.run_worktrees([job])

    assert result.status == "published"
    assert result.kept_paths == ()
    assert result.cleanup_errors == ()
    # The repository is the only worktree left standing, and the run left no directory.
    listed = _git(repo, "worktree", "list", "--porcelain")
    assert [line for line in listed.splitlines() if line.startswith("worktree ")] == [
        f"worktree {repo.resolve()}"
    ]
    assert not _managed().exists() or not any(_managed().iterdir())


def test_a_cleanup_failure_does_not_take_back_a_published_run(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = runner._git

    def stubborn(cwd: Path, *args: str, action: str) -> str:
        if args[:2] == ("worktree", "remove") and args[-1].endswith("writer-0"):
            raise runner._GitError(action, cwd, 1, "would not go")
        return real(cwd, *args, action=action)

    monkeypatch.setattr(runner, "_git", stubborn)

    result = runner.run_worktrees(
        [_job(tmp_path, "one", "Path('made.txt').write_text('made')\n")]
    )

    assert result.status == "published"  # the business result stands
    assert (repo / "made.txt").read_text() == "made"
    (kept,) = result.kept_paths
    assert kept.endswith("writer-0")
    (complaint,) = result.cleanup_errors
    assert "would not go" in complaint


def test_a_worktree_that_no_longer_matches_its_record_is_not_removed(
    repo: Path, tmp_path: Path
) -> None:
    """Cleanup checks each path against what the run knows before removing anything."""
    # A check meddles with the writer's worktree after its commit was taken -- so at
    # cleanup, the worktree is no longer clean, and removal must be refused.
    meddle = (
        sys.executable,
        "-c",
        (
            "import pathlib, sys;"
            " [p.joinpath('meddled.txt').write_text('x')"
            " for p in pathlib.Path(sys.argv[1]).glob('*/writer-0')]"
        ),
        str(_managed()),
    )

    result = runner.run_worktrees(
        [_job(tmp_path, "one", "Path('made.txt').write_text('made')\n")],
        checks=[meddle],
    )

    assert result.status == "published"
    (kept,) = result.kept_paths
    assert kept.endswith("writer-0")
    assert (Path(kept) / "meddled.txt").exists()  # untouched, for whoever comes to look
    (complaint,) = result.cleanup_errors
    assert "not clean" in complaint


def test_a_check_that_commits_in_the_integration_worktree_blocks_publishing(
    repo: Path, tmp_path: Path
) -> None:
    """A committing check leaves the worktree clean -- but not the tree the checks passed."""
    base = _git(repo, "rev-parse", "HEAD")
    tidier = (
        sys.executable,
        "-c",
        (
            "import pathlib, subprocess;"
            " pathlib.Path('made.txt').write_text('tidied');"
            " subprocess.run(['git', '-c', 'user.name=t', '-c',"
            " 'user.email=t@example.com', '-c', 'commit.gpgsign=false',"
            " 'commit', '-am', 'tidied'], check=True)"
        ),
    )

    result = runner.run_worktrees(
        [_job(tmp_path, "one", "Path('made.txt').write_text('made')\n")],
        checks=[tidier],
    )

    assert result.status == "failed"
    assert result.error is not None
    assert "integration" in result.error
    # Nothing landed on the target branch, least of all a tip the checks never saw.
    assert _git(repo, "rev-parse", "HEAD") == base
    assert not (repo / "made.txt").exists()


def test_a_committing_check_cannot_turn_a_no_change_run_into_an_unchanged_result(
    repo: Path, tmp_path: Path
) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    committing = (
        "git",
        *AS_TEST,
        "commit",
        "--allow-empty",
        "-m",
        "a check's commit",
    )

    result = runner.run_worktrees(
        [_job(tmp_path, "idle", "pass\n")], checks=[committing]
    )

    assert result.status == "failed"
    assert result.error is not None
    assert "integration worktree moved" in result.error
    assert result.published_sha is None
    assert _git(repo, "rev-parse", "HEAD") == base
    assert len(result.kept_paths) == 2


def test_a_branch_switched_under_the_fast_forward_is_seen_and_the_run_failed(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The window between the last look and the merge is real; crossed, it must be seen."""
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "branch", "dev")
    real = runner._git

    def switched(cwd: Path, *args: str, action: str) -> str:
        if action.startswith("fast-forwarding"):
            _git(repo, "checkout", "dev")
        return real(cwd, *args, action=action)

    monkeypatch.setattr(runner, "_git", switched)

    result = runner.run_worktrees(
        [_job(tmp_path, "one", "Path('made.txt').write_text('made')\n")]
    )

    assert result.status == "failed"
    assert result.published_sha is None
    assert result.error is not None
    assert "'main'" in result.error
    # The target branch itself never moved, and the run does not claim otherwise.
    assert _git(repo, "rev-parse", "refs/heads/main") == base


def test_a_job_argv_no_process_can_be_given_is_a_structured_failure(
    repo: Path, tmp_path: Path
) -> None:
    """An argv the OS cannot even receive fails the one job, not the caller's process."""
    base = _git(repo, "rev-parse", "HEAD")
    sound = _job(tmp_path, "sound", "Path('made.txt').write_text('made')\n")
    unsound = runner.WorktreeJob(name="unsound", argv=("true", "a\x00b"))

    result = runner.run_worktrees([sound, unsound])

    assert result.status == "failed"
    ok, bad = result.jobs
    assert ok.status == "finished"
    assert bad.status == "failed"
    assert bad.error is not None
    assert "cannot start" in bad.error
    assert _git(repo, "rev-parse", "HEAD") == base
    assert len(result.kept_paths) == 2


def test_a_check_argv_no_process_can_be_given_fails_the_run(
    repo: Path, tmp_path: Path
) -> None:
    result = runner.run_worktrees(
        [_job(tmp_path, "one", "Path('made.txt').write_text('made')\n")],
        checks=[("true", "a\x00b")],
    )

    assert result.status == "failed"
    (check,) = result.checks
    assert check.returncode is None
    assert check.error is not None
    assert "cannot start" in check.error


def test_an_interrupt_outlasts_a_writer_that_shrugs_off_being_told_to_stop(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Terminating is an offer; a writer that declines it is killed, not waited on."""
    monkeypatch.setattr(runner, "_PATIENCE", 0.2)
    seen = tmp_path / "seen"
    seen.mkdir()
    job = _job(
        tmp_path,
        "deaf",
        f"""
import signal
signal.signal(signal.SIGTERM, signal.SIG_IGN)
Path({str(seen)!r}, "deaf.pid").write_text(str(os.getpid()))
time.sleep(60)
""",
    )

    def interrupt_once_started() -> None:
        deadline = time.monotonic() + 20
        while not (seen / "deaf.pid").exists():
            assert time.monotonic() < deadline, "the writer never started"
            time.sleep(0.01)
        os.kill(os.getpid(), signal.SIGINT)

    interrupter = threading.Thread(target=interrupt_once_started)
    interrupter.start()
    try:
        with pytest.raises(KeyboardInterrupt):
            runner.run_worktrees([job])
    finally:
        interrupter.join()

    pid = int((seen / "deaf.pid").read_text())
    deadline = time.monotonic() + 10
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        assert time.monotonic() < deadline, "the writer outlived the interrupt"
        time.sleep(0.01)

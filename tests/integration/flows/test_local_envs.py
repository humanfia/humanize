"""The driver for a directory on this machine, against real processes, files and git.

`tests/flows/contracts.py` holds every environment driver to what the SPI promises, and the
first tests here run it against :func:`local_env` in a temporary repository. The rest is what
the contract cannot see from outside: that a timeout kills everything a command started and
not just the command, that a write is atomic, where a worktree and a copy land and what is in
them, that a copy of a linked worktree cannot move the original's branch, that one copy is
made however many ask for it at once, that another process's hold is honoured, and that a
resumed run finds the copy it left.
"""

from __future__ import annotations

import asyncio
import fcntl
import os
import stat
import subprocess
import time
from pathlib import Path, PurePosixPath

import psutil
import pytest

from hmz import home
from hmz.flows import (
    EnvBackendKind,
    EnvCommandTimeout,
    EnvError,
    EnvFileNotFound,
    EnvPermissionDenied,
    EnvUnavailable,
    TempCloneBusy,
    WorktreeError,
)
from hmz.runtime.flowing.environing import ENVS, MachineEnvDriver, clone_dir
from hmz.runtime.flowing.environments import local_env, open_env, probe
from hmz.runtime.flowing.specs import parse_envs
from hmz.runtime.flowing.spi import ENV_CAPABILITIES, Placement
from tests.flows.contracts import check_env_driver

#: Whether this process may read and write whatever it likes, which makes a permission test
#: a test of nothing.
_ROOT = os.geteuid() == 0

#: How long a command that is to be timed out is given first, so that it has started
#: everything it starts on however loaded a machine: what it started is what is checked.
_SETTLED = 3.0


def _git(cwd: Path, *argv: str) -> str:
    """Runs git as a test's own user, whoever is running the suite."""
    return subprocess.run(
        [
            "git",
            "-c",
            "user.email=tester@example.com",
            "-c",
            "user.name=tester",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "init.defaultBranch=main",
            *argv,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository with two commits, the first tagged, and a file of each kind in it."""
    at = tmp_path / "repo"
    at.mkdir()
    _git(at, "init", "-q")
    (at / ".gitignore").write_text("ignored.txt\n")
    (at / "tracked.txt").write_text("first\n")
    _git(at, "add", ".")
    _git(at, "commit", "-q", "-m", "first")
    _git(at, "tag", "first")
    (at / "tracked.txt").write_text("second\n")
    _git(at, "commit", "-qam", "second")
    (at / "untracked.txt").write_text("untracked\n")
    (at / "ignored.txt").write_text("ignored\n")
    return at


def _driver(at: Path) -> MachineEnvDriver:
    made = local_env(at)
    assert isinstance(made, MachineEnvDriver)
    return made


def _there(path: Path | PurePosixPath) -> bool:
    """Whether something is at a path, asked from a test on the loop."""
    return Path(path).exists()


def _made(path: Path) -> None:
    """Makes a directory and those above it."""
    path.mkdir(parents=True)


def _listed(path: Path | PurePosixPath) -> list[str]:
    """What is in a directory, by name."""
    return sorted(one.name for one in Path(path).iterdir())


def _text(path: Path | PurePosixPath) -> str:
    """What a file holds, or "" while there is none."""
    try:
        return Path(path).read_text()
    except FileNotFoundError:
        return ""


async def _pid_in(path: Path, within: float = 10.0) -> int:
    """The process id a command writes to a file, once it has."""
    deadline = time.monotonic() + within
    while not (said := _text(path).strip()):
        assert time.monotonic() < deadline, f"nothing was written to {path}"
        await asyncio.sleep(0.02)
    return int(said)


async def _gone(pid: int, within: float = 10.0) -> bool:
    """Whether a process is gone, waiting a while for it to be."""
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        try:
            if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                return True
        except psutil.NoSuchProcess:
            return True
        await asyncio.sleep(0.05)
    return False


# ---------------------------------------------------------------------------- the contract


async def test_the_workspace_driver_keeps_the_contract(repo: Path) -> None:
    await check_env_driver(local_env(repo), repo=True)


async def test_the_driver_an_e_flag_names_keeps_the_contract(tmp_path: Path) -> None:
    # Beside humanize's home rather than around it, which is where copies of it are made.
    (tmp_path / "work").mkdir()
    (spec,) = parse_envs([f"work=local@{tmp_path / 'work'}"])
    await check_env_driver(open_env(spec))


async def test_a_driver_says_what_it_is(repo: Path) -> None:
    driver = _driver(repo)
    try:
        assert driver.backend is EnvBackendKind.LOCAL
        assert driver.provider == ""
        assert driver.workdir == PurePosixPath(repo)
        assert driver.capabilities == ENV_CAPABILITIES
        assert driver.placement() == Placement(
            EnvBackendKind.LOCAL, "", PurePosixPath(repo), None
        )
        assert driver.available
    finally:
        await driver.close()


async def test_a_workspace_named_with_dots_is_one_place(repo: Path) -> None:
    driver = _driver(repo / "sub" / "..")
    assert driver.workdir == PurePosixPath(repo)


def test_a_directory_that_is_not_there_is_unavailable(tmp_path: Path) -> None:
    with pytest.raises(EnvUnavailable):
        local_env(tmp_path / "missing")
    (spec,) = parse_envs([f"work=local@{tmp_path / 'missing'}"])
    with pytest.raises(EnvUnavailable):
        open_env(spec)


async def test_what_the_machine_has_is_what_the_kernel_says(tmp_path: Path) -> None:
    driver = _driver(tmp_path)
    await probe(driver)
    assert driver.cpu_count == len(os.sched_getaffinity(0))
    assert driver.memory == psutil.virtual_memory().total
    assert driver.gpu_count >= 0
    assert driver.gpu_memory >= 0
    assert (driver.gpu_count == 0) == (driver.gpu_memory == 0)


async def test_a_workdir_removed_under_a_driver_makes_it_unavailable(
    tmp_path: Path,
) -> None:
    gone = tmp_path / "gone"
    gone.mkdir()
    driver = _driver(gone)
    gone.rmdir()
    assert not driver.available
    with pytest.raises(EnvUnavailable):
        await driver.exec(["true"], timeout=10)
    with pytest.raises(EnvUnavailable):
        await probe(driver)


# -------------------------------------------------------------------------------- commands


async def test_a_command_runs_in_the_workdir_and_its_status_is_answered(
    tmp_path: Path,
) -> None:
    driver = _driver(tmp_path)
    assert await driver.exec(["pwd"], timeout=10) == (0, f"{tmp_path}\n", "")
    assert await driver.exec("pwd; exit 7", timeout=10) == (7, f"{tmp_path}\n", "")
    assert await driver.exec(["sh", "-c", "kill -TERM $$"], timeout=10) == (143, "", "")


async def test_what_a_command_says_is_decoded_with_errors_replaced(
    tmp_path: Path,
) -> None:
    driver = _driver(tmp_path)
    status, out, err = await driver.exec("printf '\\377ok'; printf 'é' >&2", timeout=10)
    assert (status, out, err) == (0, "�ok", "é")


async def test_a_command_reads_nothing_on_its_stdin(tmp_path: Path) -> None:
    assert await _driver(tmp_path).exec(["cat"], timeout=10) == (0, "", "")


async def test_a_command_writing_a_lot_to_both_streams_is_heard_whole(
    tmp_path: Path,
) -> None:
    status, out, err = await _driver(tmp_path).exec(
        "head -c 3000000 /dev/zero; head -c 2000000 /dev/zero >&2", timeout=60
    )
    assert (status, len(out), len(err)) == (0, 3_000_000, 2_000_000)


async def test_a_timeout_kills_everything_the_command_started(tmp_path: Path) -> None:
    driver = _driver(tmp_path)
    with pytest.raises(EnvCommandTimeout, match="timeout"):
        await driver.exec("sleep 30 & echo $! > child; wait", timeout=_SETTLED)
    child = int((tmp_path / "child").read_text())
    assert await _gone(child), "a command's child outlived its timeout"


async def test_a_cancelled_command_is_killed_with_its_children(tmp_path: Path) -> None:
    driver = _driver(tmp_path)
    running = asyncio.create_task(
        driver.exec("sleep 30 & echo $! > child; wait", timeout=0)
    )
    child = await _pid_in(tmp_path / "child")
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert await _gone(child), "a cancelled command's child outlived it"


async def test_a_timeout_kills_what_outlived_the_command_in_its_group(
    tmp_path: Path,
) -> None:
    driver = _driver(tmp_path)
    with pytest.raises(EnvCommandTimeout):
        await driver.exec("sleep 30 & echo $! > child", timeout=_SETTLED)
    child = await _pid_in(tmp_path / "child")
    assert await _gone(child), "what the command left holding its output outlived it"


#: A daemon that leaves the command's group and session, and keeps its output open.
_DAEMON = "setsid sh -c 'echo $$ > daemon; exec sleep 30' & echo started"


async def test_a_daemon_holding_a_command_s_output_does_not_hold_its_timeout(
    tmp_path: Path,
) -> None:
    driver = _driver(tmp_path)
    started = time.monotonic()
    try:
        with pytest.raises(EnvCommandTimeout):
            await driver.exec(_DAEMON, timeout=_SETTLED)
        assert time.monotonic() - started < 20
    finally:
        os.kill(await _pid_in(tmp_path / "daemon"), 9)


async def test_closing_lets_go_of_a_command_a_daemon_holds_open(tmp_path: Path) -> None:
    driver = _driver(tmp_path)
    running = asyncio.create_task(driver.exec(_DAEMON, timeout=0))
    daemon = await _pid_in(tmp_path / "daemon")
    try:
        await asyncio.sleep(0.3)
        assert not running.done()
        started = time.monotonic()
        await driver.close()
        with pytest.raises(EnvError, match="closed"):
            await running
        assert time.monotonic() - started < 20
    finally:
        os.kill(daemon, 9)


async def test_a_program_that_is_not_there_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(EnvFileNotFound, match="no-such-program"):
        await _driver(tmp_path).exec(["no-such-program-anywhere"], timeout=10)


@pytest.mark.skipif(_ROOT, reason="root may run what it likes")
async def test_a_program_that_may_not_be_run_is_refused(tmp_path: Path) -> None:
    script = tmp_path / "script"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o644)
    with pytest.raises(EnvPermissionDenied):
        await _driver(tmp_path).exec([str(script)], timeout=10)


async def test_what_is_no_command_is_refused(tmp_path: Path) -> None:
    driver = _driver(tmp_path)
    with pytest.raises(ValueError, match="program"):
        await driver.exec([], timeout=10)
    with pytest.raises(ValueError, match="timeout"):
        await driver.exec(["true"], timeout=-1)


async def test_many_commands_run_at_once(tmp_path: Path) -> None:
    driver = _driver(tmp_path)
    said = await asyncio.gather(
        *(driver.exec(["echo", str(number)], timeout=30) for number in range(64))
    )
    assert said == [(0, f"{number}\n", "") for number in range(64)]


async def test_closing_the_root_kills_every_command_under_it(tmp_path: Path) -> None:
    driver = _driver(tmp_path)
    sub = await driver.derive_subdir("sub")
    running = [
        asyncio.create_task(driver.exec(["sleep", "30"], timeout=0)),
        asyncio.create_task(sub.exec(["sleep", "30"], timeout=0)),
    ]
    await asyncio.sleep(0.3)
    started = time.monotonic()
    await driver.close()
    for task in running:
        with pytest.raises(EnvError, match="closed"):
            await task
    assert time.monotonic() - started < 10


async def test_closing_a_derived_driver_kills_its_commands_alone(
    tmp_path: Path,
) -> None:
    driver = _driver(tmp_path)
    sub = await driver.derive_subdir("sub")
    mine = asyncio.create_task(sub.exec(["sleep", "30"], timeout=0))
    theirs = asyncio.create_task(driver.exec(["sleep", "1"], timeout=0))
    for _ in range(1000):
        if len(driver._machine.running) == 2:
            break
        await asyncio.sleep(0.01)
    await sub.close()
    with pytest.raises(EnvError, match="closed"):
        await mine
    assert await theirs == (0, "", "")
    await driver.close()


# ----------------------------------------------------------------------------------- files


async def test_files_are_read_and_written_where_they_are_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    driver = _driver(tmp_path)
    await driver.write("a/b/c.txt", b"relative")
    assert (tmp_path / "a/b/c.txt").read_bytes() == b"relative"
    await driver.write(str(tmp_path / "abs.txt"), b"absolute")
    assert await driver.read("abs.txt") == b"absolute"
    await driver.write("~/at-home.txt", b"home")
    assert (tmp_path / "home/at-home.txt").read_bytes() == b"home"
    assert await driver.read("~/at-home.txt") == b"home"


async def test_a_write_replaces_a_file_whole_and_keeps_its_mode(tmp_path: Path) -> None:
    driver = _driver(tmp_path)
    kept = tmp_path / "kept.sh"
    kept.write_text("old, and longer than what replaces it\n")
    kept.chmod(0o751)
    await driver.write("kept.sh", b"new\n")
    assert kept.read_bytes() == b"new\n"
    assert stat.S_IMODE(kept.stat().st_mode) == 0o751
    assert _listed(tmp_path) == ["kept.sh"]


async def test_a_new_file_is_made_as_the_umask_says(tmp_path: Path) -> None:
    await _driver(tmp_path).write("new.txt", b"x")
    umask = os.umask(0)
    os.umask(umask)
    assert stat.S_IMODE((tmp_path / "new.txt").stat().st_mode) == 0o666 & ~umask


async def test_a_write_through_a_link_writes_what_it_points_to(tmp_path: Path) -> None:
    (tmp_path / "real.txt").write_text("old")
    (tmp_path / "link.txt").symlink_to("real.txt")
    await _driver(tmp_path).write("link.txt", b"new")
    assert (tmp_path / "link.txt").is_symlink()
    assert (tmp_path / "real.txt").read_bytes() == b"new"


async def test_what_cannot_be_read_or_written_says_why(tmp_path: Path) -> None:
    driver = _driver(tmp_path)
    (tmp_path / "file").write_text("x")
    (tmp_path / "dir").mkdir()
    with pytest.raises(EnvFileNotFound):
        await driver.read("missing")
    with pytest.raises(EnvFileNotFound):
        await driver.read("file/under-a-file")
    with pytest.raises(EnvError) as raised:
        await driver.read("dir")
    assert not isinstance(raised.value, FileNotFoundError)
    with pytest.raises(EnvError):
        await driver.write("dir", b"x")
    with pytest.raises(EnvError):
        await driver.write("file/under-a-file", b"x")


@pytest.mark.skipif(_ROOT, reason="root may read and write what it likes")
async def test_what_may_not_be_touched_is_refused(tmp_path: Path) -> None:
    driver = _driver(tmp_path)
    secret = tmp_path / "secret"
    secret.write_text("x")
    secret.chmod(0)
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        with pytest.raises(EnvPermissionDenied) as raised:
            await driver.read("secret")
        assert isinstance(raised.value, PermissionError)
        with pytest.raises(EnvPermissionDenied):
            await driver.write("locked/x", b"x")
    finally:
        locked.chmod(0o700)


# ---------------------------------------------------------------------------- subdirectories


async def test_a_subdirectory_is_made_and_named_plainly(tmp_path: Path) -> None:
    driver = _driver(tmp_path)
    sub = await driver.derive_subdir("a/./b/../c")
    assert sub.workdir == PurePosixPath(tmp_path) / "a/c"
    assert (tmp_path / "a/c").is_dir()
    assert sub.available
    again = await sub.derive_subdir(PurePosixPath("d"))
    assert again.workdir == PurePosixPath(tmp_path) / "a/c/d"
    same = await driver.derive_subdir(".")
    assert same.workdir == driver.workdir


async def test_a_subdirectory_outside_the_workdir_is_refused(tmp_path: Path) -> None:
    driver = _driver(tmp_path)
    for outside in ("..", "../x", "a/../../x", "/x", str(tmp_path)):
        with pytest.raises(ValueError, match="not a directory under"):
            await driver.derive_subdir(outside)


async def test_a_subdirectory_where_a_file_is_cannot_be_made(tmp_path: Path) -> None:
    (tmp_path / "file").write_text("x")
    with pytest.raises(EnvError):
        await _driver(tmp_path).derive_subdir("file")


# -------------------------------------------------------------------------------- worktrees


async def test_a_worktree_lands_under_humanize_home_detached_at_head(
    repo: Path,
) -> None:
    driver = _driver(repo)
    tree = await driver.derive_worktree(ref=None, dir=None)
    at = Path(tree.workdir)
    assert at.is_relative_to(home() / ENVS)
    assert (at / "tracked.txt").read_text() == "second\n"
    assert not (at / "untracked.txt").exists()
    said = await tree.exec(["git", "rev-parse", "--abbrev-ref", "HEAD"], timeout=30)
    assert said[1] == "HEAD\n", "a worktree is detached"
    assert _git(at, "rev-parse", "HEAD") == _git(repo, "rev-parse", "HEAD")
    other = await driver.derive_worktree(ref=None, dir=None)
    assert other.workdir != tree.workdir


async def test_a_worktree_checks_out_the_ref_it_is_given(repo: Path) -> None:
    tree = await _driver(repo).derive_worktree(ref="first", dir=None)
    assert (Path(tree.workdir) / "tracked.txt").read_text() == "first\n"


async def test_a_worktree_goes_where_it_is_told(repo: Path, tmp_path: Path) -> None:
    driver = _driver(repo)
    beside = await driver.derive_worktree(ref="main", dir="../beside")
    assert beside.workdir == PurePosixPath(tmp_path / "beside")
    assert (tmp_path / "beside/tracked.txt").read_text() == "second\n"
    away = await driver.derive_worktree(ref=None, dir=PurePosixPath(tmp_path / "a/b"))
    assert away.workdir == PurePosixPath(tmp_path / "a/b")
    assert (tmp_path / "a/b/tracked.txt").exists()


async def test_a_worktree_git_will_not_make_says_what_git_said(
    repo: Path, tmp_path: Path
) -> None:
    driver = _driver(repo)
    with pytest.raises(WorktreeError, match="invalid reference"):
        await driver.derive_worktree(ref="no-such-ref", dir=None)
    taken = tmp_path / "taken"
    taken.mkdir()
    (taken / "file").write_text("x")
    with pytest.raises(WorktreeError, match="already exists"):
        await driver.derive_worktree(ref=None, dir=str(taken))
    for option in ("--force", "-b", " "):
        with pytest.raises(WorktreeError, match="not a ref"):
            await driver.derive_worktree(ref=option, dir=None)
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(WorktreeError, match="not a git repository"):
        await _driver(plain).derive_worktree(ref=None, dir=None)


# ---------------------------------------------------------------------- temporary copies


async def test_a_copy_holds_everything_the_workdir_does(repo: Path) -> None:
    driver = _driver(repo)
    copy = await driver.derive_temp_clone("work", holder="me")
    at = Path(copy.workdir)
    assert at.is_relative_to(home() / ENVS)
    for name, said in [
        ("tracked.txt", "second\n"),
        ("untracked.txt", "untracked\n"),
        ("ignored.txt", "ignored\n"),
    ]:
        assert (at / name).read_text() == said
    assert _git(at, "status", "--porcelain") == "?? untracked.txt\n"
    assert not list(at.parent.glob("*.part.*")), "a copy left its making behind"


async def test_a_copy_is_a_repository_of_its_own(repo: Path) -> None:
    driver = _driver(repo)
    _git(repo, "worktree", "add", "-q", "../linked")
    copy = await driver.derive_temp_clone("work", holder="me")
    at = Path(copy.workdir)
    _git(at, "commit", "-q", "--allow-empty", "-m", "in the copy")
    assert _git(repo, "log", "--format=%s", "-1") == "second\n"
    assert _git(at, "worktree", "list").count("\n") == 1, (
        "the copy names the original's"
    )
    assert "in the copy" in _git(at, "log", "--format=%s", "-1")


async def test_a_copy_of_a_linked_worktree_cannot_move_the_original(
    repo: Path, tmp_path: Path
) -> None:
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", "-q", "-b", "feature", str(linked))
    (linked / "tracked.txt").write_text("staged\n")
    _git(linked, "add", "tracked.txt")
    before = _git(repo, "rev-parse", "feature")
    copy = await _driver(linked).derive_temp_clone("work", holder="me")
    at = Path(copy.workdir)
    assert (at / ".git").is_dir()
    assert _git(at, "symbolic-ref", "HEAD") == "refs/heads/feature\n"
    assert _git(at, "status", "--porcelain") == "M  tracked.txt\n", (
        "the index came along"
    )
    _git(at, "commit", "-q", "-m", "in the copy")
    assert _git(repo, "rev-parse", "feature") == before
    assert _git(linked, "status", "--porcelain") == "M  tracked.txt\n"


async def test_worktrees_kept_inside_a_copy_are_the_copy_s_own(
    repo: Path, tmp_path: Path
) -> None:
    inside = repo / ".claude" / "worktrees" / "agent"
    _git(repo, "worktree", "add", "-q", "-b", "agent", str(inside))
    _git(repo, "worktree", "add", "-q", "-b", "outside", str(tmp_path / "outside"))
    before = {name: _git(repo, "rev-parse", name) for name in ("agent", "outside")}
    copy = await _driver(repo).derive_temp_clone("work", holder="me")
    at = Path(copy.workdir)
    nested = at / ".claude" / "worktrees" / "agent"
    assert _git(nested, "rev-parse", "--show-toplevel") == f"{nested}\n"
    _git(nested, "commit", "-q", "--allow-empty", "-m", "in the copy's worktree")
    assert {name: _git(repo, "rev-parse", name) for name in before} == before, (
        "a commit in the copy moved the original's branch"
    )
    listed = _git(at, "worktree", "list", "--porcelain")
    assert f"worktree {nested}\n" in listed
    assert str(tmp_path / "outside") not in listed, "the copy names the original's"
    assert str(inside) not in listed
    assert _git(inside, "log", "--format=%s", "-1") == "second\n"


async def test_a_nested_worktree_of_a_linked_worktree_is_cut_loose(
    repo: Path, tmp_path: Path
) -> None:
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", "-q", "-b", "linked", str(linked))
    nested = linked / "nested"
    _git(repo, "worktree", "add", "-q", "-b", "nested", str(nested))
    before = _git(repo, "rev-parse", "nested")
    copy = await _driver(linked).derive_temp_clone("work", holder="me")
    at = Path(copy.workdir)
    assert not (at / "nested" / ".git").exists()
    assert _git(at / "nested", "rev-parse", "--show-toplevel") == f"{at}\n"
    _git(at, "commit", "-q", "--allow-empty", "-m", "in the copy")
    assert _git(repo, "rev-parse", "nested") == before


async def test_one_holder_holds_one_copy_under_an_id(repo: Path) -> None:
    driver = _driver(repo)
    mine, theirs = object(), object()
    copy = await driver.derive_temp_clone("work", holder=mine)
    (Path(copy.workdir) / "made.txt").write_text("in the copy")
    again = await driver.derive_temp_clone("work", holder=mine)
    assert again.workdir == copy.workdir
    assert _there(again.workdir / "made.txt"), "the copy was made twice"
    with pytest.raises(TempCloneBusy):
        await driver.derive_temp_clone("work", holder=theirs)
    other = await driver.derive_temp_clone("other", holder=theirs)
    assert other.workdir != copy.workdir
    await driver.destroy_temp_clone("work")
    assert not _there(copy.workdir)
    assert not [one for one in _listed(copy.workdir.parent) if "work" in one], (
        "the hold outlived it"
    )
    taken = await driver.destroy_temp_clone("work")
    assert taken is None
    fresh = await driver.derive_temp_clone("work", holder=theirs)
    assert fresh.workdir == copy.workdir
    assert not _there(fresh.workdir / "made.txt")
    await driver.destroy_temp_clone("never-made")


#: A process number no machine hands out, being past the largest any kernel allows.
_NOBODY = 1 << 23


async def test_what_a_copy_left_half_made_or_half_removed_is_swept(repo: Path) -> None:
    driver = _driver(repo)
    target = clone_dir(PurePosixPath(home()), PurePosixPath(repo), "work")
    for junk in (f"{target}.part.{_NOBODY}", f"{target}.part.gone.{_NOBODY + 1}"):
        _made(Path(junk, "inside"))
    making = f"{target.name}.part.{os.getpid()}"
    _made(Path(target.parent, making, "inside"))
    copy = await driver.derive_temp_clone("work", holder="me")
    assert copy.workdir == target
    assert _listed(target.parent) == [target.name, f"{target.name}.lock", making], (
        "what a live process is making was swept, or what a dead one left was not"
    )
    await driver.destroy_temp_clone("work")
    assert _listed(target.parent) == [making]


async def test_worktrees_inside_a_workdir_reached_through_a_link_stay_worktrees(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real"
    (real / "repo").mkdir(parents=True)
    _git(real / "repo", "init", "-q")
    _git(real / "repo", "commit", "-q", "--allow-empty", "-m", "first")
    _git(real / "repo", "worktree", "add", "-q", "-b", "inside", "wt")
    (tmp_path / "link").symlink_to(real)
    copy = await _driver(tmp_path / "link" / "repo").derive_temp_clone("w", holder="me")
    nested = Path(copy.workdir) / "wt"
    assert _text(nested / ".git").startswith(f"gitdir: {copy.workdir}/.git/worktrees/")
    assert _git(nested, "rev-parse", "--show-toplevel") == f"{nested}\n"


async def test_gitfiles_leading_out_of_a_copy_are_cut_loose_and_those_inside_kept(
    repo: Path, tmp_path: Path
) -> None:
    (repo / ".git" / "modules" / "inside").mkdir(parents=True)
    for name, said in [
        ("inside", "gitdir: ../.git/modules/inside\n"),
        ("relative-out", "gitdir: ../../elsewhere\n"),
        ("absolute-out", f"gitdir: {tmp_path}/elsewhere\n"),
    ]:
        (repo / name).mkdir()
        (repo / name / ".git").write_text(said)
    (tmp_path / "elsewhere").mkdir()
    # And one beside where the copy lands, which the relative one would lead to from there.
    target = clone_dir(PurePosixPath(home()), PurePosixPath(repo), "work")
    _made(Path(target.parent, "elsewhere"))
    copy = await _driver(repo).derive_temp_clone("work", holder="me")
    at = Path(copy.workdir)
    assert _text(at / "inside" / ".git") == "gitdir: ../.git/modules/inside\n"
    assert not _there(at / "relative-out" / ".git")
    assert not _there(at / "absolute-out" / ".git")


async def test_many_asking_at_once_share_one_copy(repo: Path) -> None:
    driver = _driver(repo)
    holder = object()
    copies = await asyncio.gather(
        *(driver.derive_temp_clone("work", holder=holder) for _ in range(20))
    )
    assert len({copy.workdir for copy in copies}) == 1
    clones = Path(copies[0].workdir).parent
    assert sorted(one.name for one in clones.iterdir()) == [
        Path(copies[0].workdir).name,
        f"{Path(copies[0].workdir).name}.lock",
    ]


async def test_many_holders_asking_at_once_leave_one_holding(repo: Path) -> None:
    driver = _driver(repo)
    said = await asyncio.gather(
        *(driver.derive_temp_clone("work", holder=number) for number in range(10)),
        return_exceptions=True,
    )
    held = [one for one in said if isinstance(one, MachineEnvDriver)]
    busy = [one for one in said if isinstance(one, TempCloneBusy)]
    assert (len(held), len(busy)) == (1, 9), said


async def test_a_resumed_run_finds_the_copy_it_left(repo: Path) -> None:
    first = _driver(repo)
    copy = await first.derive_temp_clone("work", holder="the first run")
    (Path(copy.workdir) / "progress.txt").write_text("half done")
    await first.close()

    resumed = _driver(repo)
    again = await resumed.derive_temp_clone("work", holder="the resumed run")
    assert again.workdir == copy.workdir
    assert (Path(again.workdir) / "progress.txt").read_text() == "half done"
    await resumed.destroy_temp_clone("work")
    await resumed.close()


async def test_a_copy_another_process_holds_is_left_to_it(repo: Path) -> None:
    driver = _driver(repo)
    copy = await driver.derive_temp_clone("work", holder="me")
    await driver.close()
    lock = Path(f"{copy.workdir}.lock")
    fd = os.open(lock, os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        other = _driver(repo)
        with pytest.raises(TempCloneBusy, match="another process"):
            await other.derive_temp_clone("work", holder="me")
        await other.destroy_temp_clone("work")
        assert _there(copy.workdir), "a copy another process holds was removed"
    finally:
        os.close(fd)
    await other.destroy_temp_clone("work")
    assert not _there(copy.workdir)


async def test_a_copy_of_a_workdir_holding_humanize_home_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / ".humanize"))
    with pytest.raises(EnvError, match="inside it"):
        await _driver(tmp_path).derive_temp_clone("work", holder="me")


@pytest.mark.skipif(_ROOT, reason="root may read what it likes")
async def test_a_copy_that_cannot_be_made_is_held_by_nobody(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    secret = work / "secret"
    secret.write_text("x")
    secret.chmod(0)
    driver = _driver(work)
    with pytest.raises(EnvError, match="could not copy"):
        await driver.derive_temp_clone("work", holder="me")
    secret.chmod(0o600)
    copy = await driver.derive_temp_clone("work", holder="somebody else")
    assert _text(copy.workdir / "secret") == "x"


async def test_copies_of_copies_are_copies_too(repo: Path) -> None:
    driver = _driver(repo)
    copy = await driver.derive_temp_clone("work", holder="me")
    deeper = await copy.derive_temp_clone("work", holder="me")
    assert deeper.workdir not in {copy.workdir, driver.workdir}
    assert _text(deeper.workdir / "tracked.txt") == "second\n"


# ------------------------------------------------------------------------------- scratch


async def test_a_scratch_directory_is_empty_kept_and_removed(repo: Path) -> None:
    driver = _driver(repo)
    scratch = await driver.derive_scratch("notes")
    at = Path(scratch.workdir)
    assert at.is_relative_to(home() / ENVS)
    assert _listed(at) == []
    await scratch.write("kept.txt", b"kept")
    same = await driver.derive_scratch("notes")
    assert await same.read("kept.txt") == b"kept"
    other = await driver.derive_scratch("other notes/with a slash")
    assert other.workdir not in {scratch.workdir, driver.workdir}
    await driver.destroy_scratch("notes")
    assert not _there(at)
    await driver.destroy_scratch("notes")
    fresh = await driver.derive_scratch("notes")
    assert _listed(fresh.workdir) == []


async def test_a_removal_that_fails_leaves_what_the_next_copy_sweeps(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = _driver(repo)
    copy = await driver.derive_temp_clone("work", holder="me")

    def fails(path: object) -> None:
        raise OSError(5, "Input/output error", str(path))

    monkeypatch.setattr("hmz.runtime.flowing.environing_local.shutil.rmtree", fails)
    with pytest.raises(EnvError, match="could not remove"):
        await driver.destroy_temp_clone("work")
    monkeypatch.undo()
    (left,) = [one for one in _listed(copy.workdir.parent) if ".part.gone." in one]
    assert left.rsplit(".", 1)[1] == str(os.getpid()), (
        "what a failed removal left is not named for the process that left it"
    )
    assert not _there(copy.workdir), "a copy half removed is still where it was"


async def test_a_scratch_directory_nobody_may_write_into_is_removed_all_the_same(
    tmp_path: Path,
) -> None:
    driver = _driver(tmp_path)
    scratch = await driver.derive_scratch("cache")
    stuck = Path(scratch.workdir) / "module" / "pinned"
    stuck.mkdir(parents=True)
    (stuck / "file").write_text("x")
    shut = Path(scratch.workdir) / "shut" / "deeper"
    shut.mkdir(parents=True)
    (shut / "file").write_text("x")
    for one, mode in [
        (stuck, 0o500),
        (stuck.parent, 0o500),
        (shut, 0),
        (shut.parent, 0),
    ]:
        one.chmod(mode)
    await driver.destroy_scratch("cache")
    assert not _there(scratch.workdir)
    assert _listed(scratch.workdir.parent) == [], "a removal left itself behind"

"""The environment driver every backend shares, over a machine kept in memory."""

from __future__ import annotations

import asyncio
import errno
import re
from pathlib import PurePosixPath

import pytest

from hmz.flows import (
    BashEnvMixin,
    EnvBackendKind,
    EnvCommandTimeout,
    EnvConnectionError,
    EnvError,
    EnvFileNotFound,
    EnvPermissionDenied,
    EnvUnavailable,
    GitEnvMixin,
    GitWorktreeEnvMixin,
    RewindError,
    ScratchError,
    ShellEnvMixin,
    TempCloneBusy,
    WorktreeError,
)
from hmz.runtime.flowing.environing import (
    ENVS,
    REWIND_SCRIPT,
    SNAPSHOT_SCRIPT,
    SNAPSHOTS_SCRIPT,
    MachineEnvDriver,
    Resources,
    clone_dir,
    env_error,
    exit_status,
    gpus_of,
    home_of,
    scratch_dir,
    started_error,
    tidy_workdir,
    worktree_dir,
)
from hmz.runtime.flowing.spi import ENV_CAPABILITIES, Placement
from tests.unit.runtime.flowing.doubles_u11 import (
    MemoryMachine,
    Said,
    same_path,
    until,
)

WORK = PurePosixPath("/work")
STATE = PurePosixPath("/home/me/.hmz")


def _driver(
    machine: MemoryMachine | None = None, workdir: str = "/work"
) -> MachineEnvDriver:
    return MachineEnvDriver(machine or MemoryMachine(), PurePosixPath(workdir))


# ------------------------------------------------------------------------------ resources


@pytest.mark.parametrize(
    ("said", "visible", "seen"),
    [
        ([], None, (0, 0)),
        (["0, GPU-a, 1024", "1, GPU-b, 512"], None, (2, 512 << 20)),
        (["0, GPU-a, 1024", "1, GPU-b, 512"], "1", (1, 512 << 20)),
        (["0, GPU-a, 1024", "1, GPU-b, 512"], "GPU-a", (1, 1024 << 20)),
        (["0, GPU-a, 1024", "1, GPU-b, 512"], "", (0, 0)),
        (["0, GPU-a, 1024", "1, GPU-b, 512"], "0,bogus,1", (1, 1024 << 20)),
        (["0, GPU-a, 1024", "1, GPU-b, 512"], "7,0", (0, 0)),
        (["0, GPU-a, 1024", "1, GPU-b, 512"], "0,0", (1, 1024 << 20)),
        (["0, GPU-a, [N/A]"], None, (1, 0)),
        (["garbage", "x, GPU-a, 10", "0, GPU-a"], None, (0, 0)),
    ],
    ids=[
        "none",
        "every",
        "by-index",
        "by-uuid-prefix",
        "empty-means-none",
        "stops-at-an-unknown-token",
        "stops-at-a-missing-index",
        "one-gpu-once",
        "memory-unknown",
        "unreadable-lines",
    ],
)
def test_gpus_are_counted_as_cuda_sees_them(
    said: list[str], visible: str | None, seen: tuple[int, int]
) -> None:
    assert gpus_of(said, visible) == seen


def test_a_machine_has_one_cpu_and_nothing_else_until_told_otherwise() -> None:
    assert Resources() == Resources(cpu_count=1, memory=0, gpu_count=0, gpu_memory=0)


# --------------------------------------------------------------------------------- errors


@pytest.mark.parametrize(
    ("error", "missing", "reported", "kind"),
    [
        (OSError(errno.EPIPE, "Broken pipe"), False, False, EnvConnectionError),
        (
            ConnectionResetError(errno.ECONNRESET, "reset"),
            False,
            False,
            EnvConnectionError,
        ),
        (OSError(errno.ENOTCONN, "stale mount"), False, True, EnvError),
        (OSError(errno.ENOENT, "missing"), False, False, EnvFileNotFound),
        (OSError(errno.ENOTDIR, "not a directory"), True, False, EnvFileNotFound),
        (OSError(errno.ENOTDIR, "not a directory"), False, False, EnvError),
        (PermissionError(errno.EACCES, "denied"), False, False, EnvPermissionDenied),
        (OSError(errno.EROFS, "read-only"), False, False, EnvPermissionDenied),
        (OSError(errno.EISDIR, "is a directory"), False, False, EnvError),
    ],
    ids=[
        "broken-pipe",
        "reset",
        "reported-stale-mount",
        "missing",
        "through-a-file-reading",
        "through-a-file-writing",
        "refused",
        "read-only",
        "anything-else",
    ],
)
def test_an_os_error_comes_to_the_environment_error_it_is(
    error: OSError, missing: bool, reported: bool, kind: type[EnvError]
) -> None:
    said = env_error(error, "reading x", missing=missing, reported=reported)

    assert type(said) is kind
    assert str(said).startswith("reading x: ")


def test_a_program_that_could_not_start_in_a_missing_workdir_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hmz.coganchor import proto

    monkeypatch.setattr(proto, "path_key", same_path)
    gone = OSError(errno.ENOENT, "No such file or directory", "/work")
    elsewhere = OSError(errno.ENOENT, "No such file or directory", "/usr/bin/nope")

    assert type(started_error(gone, ["make"], "/work")) is EnvUnavailable
    missing = started_error(elsewhere, ["nope"], "/work")
    assert type(missing) is EnvFileNotFound
    assert "could not run 'nope' in /work" in str(missing)


@pytest.mark.parametrize(
    ("returncode", "status"), [(0, 0), (3, 3), (-9, 137), (-15, 143)]
)
def test_an_exit_status_is_what_a_shell_says(returncode: int, status: int) -> None:
    assert exit_status(returncode) == status


# ------------------------------------------------------------------------------ the layout


def test_everything_derived_lives_under_envs_named_for_its_workdir() -> None:
    home = home_of(STATE, PurePosixPath("/srv/my repo"))

    assert home.parent == STATE / ENVS
    assert re.fullmatch(r"my-repo-[0-9a-f]{12}", home.name)
    assert home_of(STATE, PurePosixPath("/srv/my repo")) == home
    assert home_of(STATE, PurePosixPath("/elsewhere/my repo")) != home
    assert home_of(STATE, PurePosixPath("/")).name.startswith("root-")


def test_a_copy_and_a_scratch_directory_are_named_for_their_id() -> None:
    clone = clone_dir(STATE, WORK, "try/one")
    scratch = scratch_dir(STATE, WORK, "try/one")

    assert clone.parent == home_of(STATE, WORK) / "clones"
    assert scratch.parent == home_of(STATE, WORK) / "scratch"
    assert clone.name == scratch.name
    assert clone.name.startswith("try-one-")
    assert clone_dir(STATE, WORK, "try-one") != clone, "two ids are two places"


def test_a_worktree_with_no_place_of_its_own_gets_a_fresh_one() -> None:
    one = worktree_dir(STATE, WORK, "feature/x")
    other = worktree_dir(STATE, WORK, "feature/x")

    assert one.parent == home_of(STATE, WORK) / "worktrees"
    assert one.name.startswith("feature-x-")
    assert one != other
    assert worktree_dir(STATE, WORK, None).name.startswith("head-")


@pytest.mark.parametrize(
    ("workdir", "tidy"),
    [
        ("/srv/./x/../y", "/srv/y"),
        ("/srv/x/", "/srv/x"),
        ("~", "~"),
        ("~/x/..", "~"),
        ("~/a/./b", "~/a/b"),
    ],
)
def test_one_place_has_one_name(workdir: str, tidy: str) -> None:
    assert tidy_workdir(PurePosixPath(workdir)) == PurePosixPath(tidy)


@pytest.mark.parametrize("workdir", ["relative/x", "~/..", "~/x/../../y"])
def test_a_workdir_neither_absolute_nor_under_home_is_unavailable(workdir: str) -> None:
    with pytest.raises(EnvUnavailable):
        tidy_workdir(PurePosixPath(workdir))


# ------------------------------------------------------------------- what a driver says


def test_a_driver_says_what_its_machine_is_and_has() -> None:
    machine = MemoryMachine(backend=EnvBackendKind.SSH, provider="box")
    driver = _driver(machine)

    assert (driver.backend, driver.provider, driver.workdir) == (
        EnvBackendKind.SSH,
        "box",
        WORK,
    )
    assert (driver.cpu_count, driver.memory) == (4, 8 << 30)
    assert (driver.gpu_count, driver.gpu_memory) == (2, 16 << 30)
    assert driver.placement() == Placement(EnvBackendKind.SSH, "box", WORK)
    assert "box" in repr(driver)


@pytest.mark.parametrize(
    ("tools", "lacking"),
    [
        ({}, set[type]()),
        ({"git": True, "bash": True}, set[type]()),
        ({"git": False}, {GitEnvMixin, GitWorktreeEnvMixin}),
        ({"bash": False}, {BashEnvMixin}),
    ],
    ids=["never-looked", "has-both", "no-git", "no-bash"],
)
def test_a_driver_serves_every_capability_but_those_its_machine_lacks(
    tools: dict[str, bool], lacking: set[type]
) -> None:
    machine = MemoryMachine()
    machine.tools = tools

    capabilities = _driver(machine).capabilities

    assert capabilities == ENV_CAPABILITIES - lacking
    assert ShellEnvMixin in capabilities


async def test_a_probed_driver_is_available_and_one_with_no_workdir_is_not() -> None:
    machine = MemoryMachine()
    here = _driver(machine)
    gone = _driver(machine, "/gone")

    assert not here.available, "nothing has been seen yet"
    await here.probe()
    with pytest.raises(EnvUnavailable, match="/gone"):
        await gone.probe()

    assert here.available
    assert not gone.available
    assert machine.probed == 2


# -------------------------------------------------------------------------------- commands


async def test_an_argv_is_run_as_it_is_and_a_script_by_bash_in_the_workdir() -> None:
    machine = MemoryMachine()
    machine.answer = lambda argv, cwd: (0, "out é\n", "err\n")
    driver = _driver(machine, "~/repo")
    machine.dirs.add(PurePosixPath("/home/me/repo"))

    said = await driver.exec(["make", "test"], timeout=0)
    await driver.exec("echo $HOME", timeout=5)

    assert said == (0, "out é\n", "err\n")
    assert machine.started == [
        (("make", "test"), PurePosixPath("/home/me/repo")),
        (("bash", "-c", "echo $HOME"), PurePosixPath("/home/me/repo")),
    ]
    assert [run.released for run in machine.runs] == [1, 1]
    assert driver.available, "a command that ran is a workdir that is there"


@pytest.mark.parametrize(
    ("argv", "limit"),
    [([], 0), (["true"], -1), (["true"], float("nan"))],
    ids=["no-program", "negative", "nan"],
)
async def test_what_is_no_command_or_no_timeout_is_refused(
    argv: list[str], limit: float
) -> None:
    machine = MemoryMachine()

    with pytest.raises(ValueError):  # noqa: PT011 -- either is the message
        await _driver(machine).exec(argv, timeout=limit)
    assert machine.started == []


async def test_a_command_past_its_timeout_is_killed_and_says_so() -> None:
    machine = MemoryMachine()
    machine.answer = lambda argv, cwd: None

    with pytest.raises(EnvCommandTimeout, match="ran past its timeout"):
        await _driver(machine).exec(["sleep", "1000"], timeout=0.01)

    (run,) = machine.runs
    assert run.killed
    assert run.released == 1


async def test_a_cancelled_command_is_killed() -> None:
    machine = MemoryMachine()
    machine.answer = lambda argv, cwd: None
    running = asyncio.ensure_future(_driver(machine).exec(["serve"], timeout=0))
    await until(lambda: bool(machine.runs))

    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert machine.runs[0].killed


async def test_a_workdir_found_gone_leaves_the_driver_unavailable() -> None:
    machine = MemoryMachine()
    driver = _driver(machine)
    await driver.probe()
    machine.dirs.discard(WORK)

    with pytest.raises(EnvUnavailable):
        await driver.exec(["true"], timeout=0)

    assert not driver.available


async def test_closing_the_root_kills_every_command_and_closes_everything() -> None:
    machine = MemoryMachine()
    machine.answer = lambda argv, cwd: None
    root = _driver(machine)
    derived = await root.derive_subdir("sub")
    running = [
        asyncio.ensure_future(root.exec(["a"], timeout=0)),
        asyncio.ensure_future(derived.exec(["b"], timeout=0)),
    ]
    await until(lambda: len(machine.runs) == 2)

    await root.close()

    for one in running:
        with pytest.raises(EnvError, match="its environment was closed"):
            await one
    assert all(run.killed for run in machine.runs)
    assert machine.shut == 1
    await root.close()
    assert not root.available
    assert not derived.available
    for driver in (root, derived):
        with pytest.raises(EnvError, match="closed"):
            await driver.read("x")


async def test_closing_a_derived_driver_stops_its_own_commands_alone() -> None:
    machine = MemoryMachine()
    machine.answer = lambda argv, cwd: None
    root = _driver(machine)
    derived = await root.derive_subdir("sub")
    mine = asyncio.ensure_future(derived.exec(["mine"], timeout=0))
    theirs = asyncio.ensure_future(root.exec(["theirs"], timeout=0))
    await until(lambda: len(machine.runs) == 2)

    await derived.close()

    with pytest.raises(EnvError, match="closed"):
        await mine
    assert not theirs.done()
    assert machine.shut == 0
    await root.close()
    with pytest.raises(EnvError):
        await theirs


# ----------------------------------------------------------------------------------- files


async def test_a_path_is_the_workdirs_unless_absolute_or_under_home() -> None:
    machine = MemoryMachine()
    driver = _driver(machine)

    await driver.write("a/b.txt", b"one")
    await driver.write("/etc/x", b"two")
    await driver.write("~/y", b"three")

    assert machine.files == {
        PurePosixPath("/work/a/b.txt"): b"one",
        PurePosixPath("/etc/x"): b"two",
        PurePosixPath("/home/me/y"): b"three",
    }
    assert await driver.read("a/b.txt") == b"one"
    assert await driver.read("~/y") == b"three"
    with pytest.raises(EnvFileNotFound):
        await driver.read("nope")


# -------------------------------------------------------------------------------- deriving


async def test_a_subdirectory_is_made_under_the_workdir_as_written() -> None:
    machine = MemoryMachine()
    driver = _driver(machine)

    sub = await driver.derive_subdir("a/./b/../c")

    assert sub.workdir == PurePosixPath("/work/a/c")
    assert PurePosixPath("/work/a/c") in machine.dirs
    assert sub.available
    assert (sub.backend, sub.provider) == (driver.backend, driver.provider)


async def test_a_subdirectory_of_a_home_workdir_stays_under_home() -> None:
    machine = MemoryMachine(dirs=("/home/me/repo",))

    sub = await _driver(machine, "~/repo").derive_subdir("x")

    assert sub.workdir == PurePosixPath("~/repo/x")
    assert PurePosixPath("/home/me/repo/x") in machine.dirs


@pytest.mark.parametrize("subdir", ["/abs", "..", "../x", "a/../../x"])
async def test_a_subdirectory_outside_the_workdir_is_refused(subdir: str) -> None:
    with pytest.raises(ValueError, match="not a directory under"):
        await _driver().derive_subdir(subdir)


def _git(argv: tuple[str, ...], cwd: PurePosixPath) -> Said:
    return (0, "", "") if argv[:1] == ("git",) else (1, "", "nope")


async def test_a_worktree_goes_where_it_is_told_or_under_humanize_home() -> None:
    machine = MemoryMachine()
    machine.answer = _git
    driver = _driver(machine)

    told = await driver.derive_worktree(ref="main", dir="trees/../tree")
    fresh = await driver.derive_worktree(ref=None, dir=None)

    assert told.workdir == PurePosixPath("/work/tree")
    assert fresh.workdir.parent == home_of(STATE, WORK) / "worktrees"
    assert [argv for argv, _ in machine.started] == [
        (
            "git",
            "-C",
            "/work",
            "worktree",
            "add",
            "--quiet",
            "--detach",
            "/work/tree",
            "main",
        ),
        (
            "git",
            "-C",
            "/work",
            "worktree",
            "add",
            "--quiet",
            "--detach",
            str(fresh.workdir),
        ),
    ]


@pytest.mark.parametrize("ref", ["", "  ", "-b", "--orphan"])
async def test_a_ref_that_is_none_or_reads_as_an_option_is_refused_before_git(
    ref: str,
) -> None:
    machine = MemoryMachine()

    with pytest.raises(WorktreeError, match="not a ref"):
        await _driver(machine).derive_worktree(ref=ref, dir=None)
    assert machine.started == []


async def test_what_git_said_no_to_is_a_worktree_error_saying_why() -> None:
    machine = MemoryMachine()
    machine.answer = lambda argv, cwd: (128, "", "fatal: invalid reference: nope\n")

    with pytest.raises(WorktreeError, match="invalid reference: nope"):
        await _driver(machine).derive_worktree(ref="nope", dir=None)


async def test_a_machine_without_git_cannot_add_a_worktree() -> None:
    machine = MemoryMachine()
    machine.broken = EnvFileNotFound("no git")

    with pytest.raises(WorktreeError, match="git is not installed"):
        await _driver(machine).derive_worktree(ref=None, dir="/elsewhere")


# ------------------------------------------------------------------------------ snapshots


async def test_a_snapshot_is_kept_under_its_name_or_one_for_when_it_was_taken() -> None:
    machine = MemoryMachine()

    def git(argv: tuple[str, ...], cwd: PurePosixPath) -> Said:
        return 0, f"refs/hmz/snapshots/{argv[4]}\n", ""

    machine.answer = git
    driver = _driver(machine)

    named = await driver.snapshot("before")
    fresh = await driver.snapshot(None)

    assert named == "refs/hmz/snapshots/before"
    assert re.fullmatch(r"refs/hmz/snapshots/\d{8}T\d{6}\.\d{6}Z-[0-9a-f]{4}", fresh)
    assert [argv[2] for argv, _ in machine.started] == [SNAPSHOT_SCRIPT] * 2
    assert {cwd for _, cwd in machine.started} == {WORK}


async def test_a_rewind_and_the_list_of_snapshots_run_their_scripts() -> None:
    machine = MemoryMachine()
    machine.answer = lambda argv, cwd: (
        0,
        "refs/hmz/snapshots/a\n\nrefs/hmz/snapshots/b\n",
        "",
    )
    driver = _driver(machine)

    await driver.rewind("refs/hmz/snapshots/a")
    listed = await driver.snapshots()

    assert listed == ["refs/hmz/snapshots/a", "refs/hmz/snapshots/b"]
    assert [argv[2:] for argv, _ in machine.started] == [
        (REWIND_SCRIPT, "humanize", "refs/hmz/snapshots/a"),
        (SNAPSHOTS_SCRIPT, "humanize", ""),
    ]


@pytest.mark.parametrize("ref", ["", "-x"])
async def test_a_rewind_to_no_ref_is_refused_before_git(ref: str) -> None:
    machine = MemoryMachine()

    with pytest.raises(RewindError, match="not a ref"):
        await _driver(machine).rewind(ref)
    assert machine.started == []


async def test_what_git_would_not_do_is_a_rewind_error_saying_why() -> None:
    machine = MemoryMachine()
    machine.answer = lambda argv, cwd: (3, "", "not a git worktree\nsecond line\n")
    driver = _driver(machine)

    with pytest.raises(RewindError, match="not a git worktree second line"):
        await driver.snapshot("x")
    machine.answer = lambda argv, cwd: (1, "", "")
    with pytest.raises(RewindError, match="exit 1"):
        await driver.snapshots()


# ------------------------------------------------------------------------ temporary copies


async def test_one_holder_holds_one_copy_and_nobody_else_gets_it() -> None:
    machine = MemoryMachine()
    machine.files[WORK / "f"] = b"data"
    driver = _driver(machine)

    copy = await driver.derive_temp_clone("a", holder="me")
    again = await driver.derive_temp_clone("a", holder="me")
    with pytest.raises(TempCloneBusy):
        await driver.derive_temp_clone("a", holder="you")

    assert copy.workdir == again.workdir == clone_dir(STATE, WORK, "a")
    assert machine.files[copy.workdir / "f"] == b"data"
    assert copy.available


async def test_one_copy_is_made_however_many_ask_at_once() -> None:
    machine = MemoryMachine()
    driver = _driver(machine)

    copies = await asyncio.gather(
        *(driver.derive_temp_clone("a", holder="me") for _ in range(5))
    )

    assert len({one.workdir for one in copies}) == 1
    assert len(machine.started) == 1


async def test_a_copy_that_could_not_be_made_is_held_by_nobody() -> None:
    machine = MemoryMachine(claims=True)
    driver = _driver(machine, "/missing")

    with pytest.raises(EnvError, match="could not copy"):
        await driver.derive_temp_clone("a", holder="me")
    machine.dirs.add(PurePosixPath("/missing"))
    copy = await driver.derive_temp_clone("a", holder="you")

    assert copy.workdir == clone_dir(STATE, PurePosixPath("/missing"), "a")
    assert machine.claims == [(copy.workdir, False)], "the failed one's hold was let go"


async def test_a_copy_another_process_holds_is_refused() -> None:
    machine = MemoryMachine(claims=True)
    driver = _driver(machine)
    machine.busy.add(clone_dir(STATE, WORK, "a"))

    with pytest.raises(TempCloneBusy):
        await driver.derive_temp_clone("a", holder="me")
    await driver.destroy_temp_clone("a")

    assert machine.started == [], "nothing was copied, nor removed"


async def test_destroying_a_copy_removes_it_and_frees_its_id() -> None:
    machine = MemoryMachine(claims=True)
    driver = _driver(machine)
    copy = await driver.derive_temp_clone("a", holder="me")

    await driver.destroy_temp_clone("a")
    await driver.destroy_temp_clone("a")
    await driver.destroy_temp_clone("never")

    assert copy.workdir not in machine.dirs
    assert machine.claims == [(copy.workdir, True)]
    again = await driver.derive_temp_clone("a", holder="you")
    assert again.workdir == copy.workdir


async def test_a_copy_left_by_another_run_is_removed_under_a_hold_of_its_own() -> None:
    machine = MemoryMachine(claims=True)
    target = clone_dir(STATE, WORK, "left")
    machine.dirs.add(target)

    await _driver(machine).destroy_temp_clone("left")

    assert target not in machine.dirs
    assert machine.claims == [(target, True)]


async def test_closing_the_root_lets_a_resumed_run_hold_what_it_left() -> None:
    machine = MemoryMachine(claims=True)
    first = _driver(machine)
    copy = await first.derive_temp_clone("a", holder="first run")
    await first.close()

    again = MemoryMachine(claims=True)
    again.identity, again.dirs = machine.identity, machine.dirs
    resumed = _driver(again)
    taken = await resumed.derive_temp_clone("a", holder="resumed run")

    assert taken.workdir == copy.workdir
    assert machine.claims == [(copy.workdir, False)]


async def test_ids_are_each_machines_own() -> None:
    one, other = _driver(), _driver()

    await one.derive_temp_clone("a", holder="me")
    await other.derive_temp_clone("a", holder="you")


async def test_a_copy_inside_what_it_copies_is_refused() -> None:
    machine = MemoryMachine(state="/work/.hmz")

    with pytest.raises(EnvError, match="inside it"):
        await _driver(machine).derive_temp_clone("a", holder="me")


# ------------------------------------------------------------------------------- scratch


async def test_a_scratch_directory_is_one_per_id_until_it_is_removed() -> None:
    machine = MemoryMachine()
    driver = _driver(machine)

    one = await driver.derive_scratch("s")
    again = await driver.derive_scratch("s")
    other = await driver.derive_scratch("t")

    assert one.workdir == again.workdir == scratch_dir(STATE, WORK, "s")
    assert other.workdir != one.workdir
    assert one.workdir in machine.dirs
    await driver.destroy_scratch("s")
    assert one.workdir not in machine.dirs


async def test_a_scratch_directory_that_cannot_be_made_is_a_scratch_error() -> None:
    machine = MemoryMachine()
    machine.broken = EnvPermissionDenied("read-only")
    driver = _driver(machine)

    with pytest.raises(ScratchError, match="could not make"):
        await driver.derive_scratch("s")
    with pytest.raises(ScratchError, match="could not remove"):
        await driver.destroy_scratch("s")


async def test_a_lost_connection_is_not_taken_for_a_scratch_error() -> None:
    machine = MemoryMachine()
    machine.broken = EnvConnectionError("gone")

    with pytest.raises(EnvConnectionError):
        await _driver(machine).derive_scratch("s")

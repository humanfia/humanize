"""The environment driver's own logic, over a machine that is a dictionary.

:class:`~hmz.runtime.flowing.environing.MachineEnvDriver` is written against a
:class:`~hmz.runtime.flowing.environing.Machine`, and everything it decides for itself --
where a path given to it points, what a subdirectory may be, who holds a temporary copy and
when they stop, what a timeout, a cancellation or a close does to a command, what an error
becomes -- is decided above the machine. So it is held here to the whole driver contract over
a machine kept in memory, with commands that answer what the contract asks and wait to be
killed, and then to the rest of what it promises, none of it spawning anything. What the two
real machines do underneath is `tests/integration/flows/test_{local,ssh}_envs.py`.
"""

from __future__ import annotations

import asyncio
import errno
import itertools
import pickle
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.machines import AnchoredConfig
from hmz.flows import (
    EnvBackendKind,
    EnvCommandTimeout,
    EnvConnectionError,
    EnvError,
    EnvFileNotFound,
    EnvPermissionDenied,
    EnvUnavailable,
    ScratchError,
    TempCloneBusy,
    WorktreeError,
)
from hmz.runtime.flowing.environing import (
    ENVS,
    Machine,
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
from hmz.runtime.flowing.environing_ssh import PROBE_SCRIPT, SSHMachine, facts_of
from hmz.runtime.flowing.environments import open_env, probe
from hmz.runtime.flowing.specs import parse_envs
from hmz.runtime.flowing.spi import ENV_CAPABILITIES, Placement
from tests.flows.contracts import ANSWERS, SLOW_ARGV, SLOW_SCRIPT, check_env_driver

if TYPE_CHECKING:
    from collections.abc import Sequence

#: Where the machine in memory keeps humanize's home, its user's home, and a workdir.
STATE = PurePosixPath("/state")
HOME = PurePosixPath("/home/me")
WORK = PurePosixPath("/work")

#: What each command the contract runs answers, as the driver hands it to a machine.
_SAID = {
    **{
        (("bash", "-c", command) if isinstance(command, str) else command): answer
        for command, answer in ANSWERS.items()
    },
    ("git", "rev-parse", "--is-inside-work-tree"): (0, "true\n", ""),
    ("true",): (0, "", ""),
}

#: What waits to be killed.
_SLOW = {SLOW_ARGV, ("bash", "-c", SLOW_SCRIPT)}

#: Numbers the machines a test makes.
_MACHINES = itertools.count()


class Scripted:
    """A command in memory: it answers at once, or waits until it is killed."""

    def __init__(self, argv: Sequence[str]) -> None:
        self.argv = tuple(argv)
        self.killed = asyncio.Event()
        self.released = False

    async def finished(self) -> tuple[int, bytes, bytes]:
        if self.argv in _SLOW:
            await self.killed.wait()
            return 137, b"", b""
        status, out, err = _SAID.get(self.argv, (0, "", ""))
        return status, out.encode(), err.encode()

    async def kill(self) -> None:
        self.killed.set()

    def release(self) -> None:
        self.released = True


class MemoryMachine(Machine):
    """A machine whose filesystem is two dictionaries and whose commands are scripted."""

    backend = EnvBackendKind.LOCAL
    provider = ""

    def __init__(self, identity: str = "", *, lazy: bool = False) -> None:
        super().__init__()
        # A machine of its own unless a test says otherwise: who holds what is kept for the
        # whole process, and one test's holds are not another's business.
        self.identity = identity or f"memory-{next(_MACHINES)}"
        self.lazy = lazy
        self.files: dict[PurePosixPath, bytes] = {}
        self.dirs: set[PurePosixPath] = {PurePosixPath("/"), STATE, HOME, WORK}
        self.started: list[Scripted] = []
        self.copies = 0
        self.failing: set[PurePosixPath] = set()
        self.let_go = 0

    def resources(self, *, gpus: bool) -> Resources:
        return Resources(8, 16 << 30, 2 if gpus else 0, (24 << 30) if gpus else 0)

    def available(self, workdir: PurePosixPath, *, seen: bool | None) -> bool:
        return seen is True if self.lazy else workdir in self.dirs

    def placement(self, workdir: PurePosixPath) -> Placement:
        return Placement(self.backend, self.provider, workdir, None)

    async def probe(self) -> None:
        return

    async def absolute(self, path: PurePosixPath) -> PurePosixPath:
        return HOME.joinpath(*path.parts[1:]) if path.parts[:1] == ("~",) else path

    async def state(self) -> PurePosixPath:
        return STATE

    async def start(self, argv: Sequence[str], cwd: PurePosixPath) -> Scripted:
        if cwd not in self.dirs:
            raise EnvUnavailable(f"the workdir {cwd} is not there")
        if argv[0] == "no-such-program":
            raise EnvFileNotFound(f"could not run {argv[0]!r}")
        running = Scripted(argv)
        self.started.append(running)
        return running

    async def read(self, path: PurePosixPath) -> bytes:
        if path in self.dirs:
            raise EnvError(f"could not read {path}: Is a directory")
        if path not in self.files:
            raise EnvFileNotFound(f"could not read {path}")
        return self.files[path]

    async def write(self, path: PurePosixPath, data: bytes) -> None:
        await self.mkdir(path.parent)
        self.files[path] = data

    async def mkdir(self, path: PurePosixPath) -> None:
        for one in (path, *path.parents):
            if one in self.files:
                raise EnvError(f"could not make the directory {path}: File exists")
            self.dirs.add(one)

    async def is_dir(self, path: PurePosixPath) -> bool:
        return path in self.dirs

    async def remove(self, path: PurePosixPath) -> None:
        self.dirs = {one for one in self.dirs if not one.is_relative_to(path)}
        self.files = {k: v for k, v in self.files.items() if not k.is_relative_to(path)}

    async def clone(self, source: PurePosixPath, target: PurePosixPath) -> None:
        if target in self.dirs:
            return
        await asyncio.sleep(0.01)
        if source in self.failing:
            raise EnvError(f"could not copy {source} to {target}")
        self.copies += 1
        self._copy(source, target)

    async def worktree(
        self, source: PurePosixPath, target: PurePosixPath, ref: str | None
    ) -> None:
        if ref == "no-such-ref-anywhere":
            raise WorktreeError(f"git worktree add {target}: invalid reference: {ref}")
        if target in self.dirs:
            raise WorktreeError(f"git worktree add {target}: '{target}' already exists")
        self._copy(source, target)

    def _copy(self, source: PurePosixPath, target: PurePosixPath) -> None:
        self.dirs |= {
            target / one.relative_to(source)
            for one in self.dirs
            if one.is_relative_to(source)
        }
        self.dirs |= set(target.parents)
        for path, data in list(self.files.items()):
            if path.is_relative_to(source):
                self.files[target / path.relative_to(source)] = data

    async def close(self) -> None:
        self.let_go += 1


def _driver(
    machine: MemoryMachine | None = None,
) -> tuple[MachineEnvDriver, MemoryMachine]:
    machine = machine or MemoryMachine()
    return MachineEnvDriver(machine, WORK, seen=True), machine


# ---------------------------------------------------------------------------- the contract


async def test_the_driver_keeps_the_contract_over_any_machine() -> None:
    driver, machine = _driver()
    await check_env_driver(driver, repo=True, settle=0.05)
    assert machine.let_go >= 1, "closing the root did not let go of the machine"
    assert all(one.released for one in machine.started), "a command was not let go of"


async def test_a_driver_that_has_seen_nothing_is_available_once_it_has_been_used() -> (
    None
):
    machine = MemoryMachine(lazy=True)
    driver = MachineEnvDriver(machine, WORK)
    assert not driver.available
    await check_env_driver(driver, repo=True, settle=0.05)


async def test_a_driver_says_what_it_is() -> None:
    driver, _ = _driver()
    assert driver.capabilities == ENV_CAPABILITIES
    assert (driver.cpu_count, driver.memory) == (8, 16 << 30)
    assert (driver.gpu_count, driver.gpu_memory) == (2, 24 << 30)
    assert driver.placement() == Placement(EnvBackendKind.LOCAL, "", WORK, None)
    assert "/work" in repr(driver)


# -------------------------------------------------------------------------------- paths


async def test_a_path_is_the_workdir_s_unless_it_is_absolute_or_under_home() -> None:
    driver, machine = _driver()
    await driver.write("a/b.txt", b"relative")
    await driver.write("/elsewhere/c.txt", b"absolute")
    await driver.write("~/d.txt", b"home")
    assert machine.files == {
        WORK / "a/b.txt": b"relative",
        PurePosixPath("/elsewhere/c.txt"): b"absolute",
        HOME / "d.txt": b"home",
    }
    assert await driver.read("~/d.txt") == b"home"
    with pytest.raises(EnvFileNotFound):
        await driver.read("missing")


async def test_a_subdirectory_is_under_the_workdir_as_written() -> None:
    driver, machine = _driver()
    sub = await driver.derive_subdir("a/./b/../c")
    assert sub.workdir == WORK / "a/c"
    assert WORK / "a/c" in machine.dirs
    assert sub.available
    for outside in ("..", "../x", "a/../../x", "/x", PurePosixPath("/work/x")):
        with pytest.raises(ValueError, match="not a directory under"):
            await driver.derive_subdir(outside)


async def test_a_subdirectory_of_a_home_relative_workdir_stays_home_relative() -> None:
    machine = MemoryMachine()
    driver = MachineEnvDriver(machine, PurePosixPath("~/repo"))
    sub = await driver.derive_subdir("x")
    assert sub.workdir == PurePosixPath("~/repo/x")
    assert HOME / "repo/x" in machine.dirs


async def test_a_worktree_goes_where_it_is_told_or_under_humanize_home() -> None:
    driver, _ = _driver()
    fresh = await driver.derive_worktree(ref=None, dir=None)
    assert fresh.workdir.is_relative_to(home_of(STATE, WORK) / "worktrees")
    named = await driver.derive_worktree(ref="v1.0/rc", dir=None)
    assert named.workdir.name.startswith("v1.0-rc-")
    beside = await driver.derive_worktree(ref=None, dir="../beside/./tree")
    assert beside.workdir == PurePosixPath("/beside/tree")
    at_home = await driver.derive_worktree(ref=None, dir="~/trees/one")
    assert at_home.workdir == HOME / "trees/one"
    away = await driver.derive_worktree(ref=None, dir=PurePosixPath("/away"))
    assert away.workdir == PurePosixPath("/away")


async def test_a_ref_that_would_be_read_as_an_option_is_refused_before_git_is() -> None:
    driver, machine = _driver()
    for ref in ("--force", "-b", "", "  "):
        with pytest.raises(WorktreeError, match="not a ref"):
            await driver.derive_worktree(ref=ref, dir=None)
    assert machine.started == []


# ------------------------------------------------------------------------------- commands


async def test_a_script_is_run_by_bash_and_an_argv_as_it_is() -> None:
    driver, machine = _driver()
    await driver.exec("echo hi", timeout=0)
    await driver.exec(("echo", "hi"), timeout=0)
    assert [one.argv for one in machine.started] == [
        ("bash", "-c", "echo hi"),
        ("echo", "hi"),
    ]


async def test_what_is_no_command_is_refused() -> None:
    driver, _ = _driver()
    with pytest.raises(ValueError, match="program"):
        await driver.exec([], timeout=0)
    for timeout in (-1, float("nan")):
        with pytest.raises(ValueError, match="timeout"):
            await driver.exec(["true"], timeout=timeout)
    assert await driver.exec(["true"], timeout=float("inf")) == (0, "", "")


async def test_a_command_past_its_timeout_is_killed_and_says_so() -> None:
    driver, machine = _driver()
    with pytest.raises(EnvCommandTimeout, match=r"timeout of 0\.05s") as raised:
        await driver.exec(list(SLOW_ARGV), timeout=0.05)
    assert isinstance(raised.value, TimeoutError)
    assert machine.started[-1].killed.is_set()
    assert machine.started[-1].released
    assert machine.running == set()


async def test_a_cancelled_command_is_killed() -> None:
    driver, machine = _driver()
    running = asyncio.create_task(driver.exec(list(SLOW_ARGV), timeout=0))
    await asyncio.sleep(0.05)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert machine.started[-1].killed.is_set()
    assert machine.running == set()


async def test_closing_the_root_stops_every_command_and_lets_go() -> None:
    driver, machine = _driver()
    sub = await driver.derive_subdir("sub")
    running = [
        asyncio.create_task(driver.exec(list(SLOW_ARGV), timeout=0)),
        asyncio.create_task(sub.exec(SLOW_SCRIPT, timeout=0)),
    ]
    await asyncio.sleep(0.05)
    await driver.close()
    for task in running:
        with pytest.raises(EnvError, match="its environment was closed"):
            await task
    assert (machine.closed, machine.let_go) == (True, 1)


async def test_closing_a_derived_driver_stops_its_own_commands_alone() -> None:
    driver, machine = _driver()
    sub = await driver.derive_subdir("sub")
    mine = asyncio.create_task(sub.exec(list(SLOW_ARGV), timeout=0))
    theirs = asyncio.create_task(driver.exec(list(SLOW_ARGV), timeout=0))
    await asyncio.sleep(0.05)
    await sub.close()
    with pytest.raises(EnvError, match="closed"):
        await mine
    assert not theirs.done()
    assert (machine.closed, machine.let_go) == (False, 0)
    theirs.cancel()
    with pytest.raises(asyncio.CancelledError):
        await theirs


async def test_a_workdir_found_gone_leaves_the_driver_unavailable() -> None:
    machine = MemoryMachine(lazy=True)
    driver = MachineEnvDriver(machine, PurePosixPath("/gone"))
    with pytest.raises(EnvUnavailable):
        await driver.exec(["true"], timeout=0)
    assert not driver.available
    with pytest.raises(EnvUnavailable):
        await probe(driver)
    machine.dirs.add(PurePosixPath("/gone"))
    await probe(driver)
    assert driver.available


# --------------------------------------------------------------------- temporary copies


async def test_one_holder_holds_one_copy_and_nobody_else_gets_it() -> None:
    driver, machine = _driver()
    await driver.write("file.txt", b"x")
    copy = await driver.derive_temp_clone("work", holder="me")
    assert copy.workdir == clone_dir(STATE, WORK, "work")
    assert await copy.read("file.txt") == b"x"
    again = await driver.derive_temp_clone("work", holder="me")
    assert again.workdir == copy.workdir
    with pytest.raises(TempCloneBusy, match="another env"):
        await driver.derive_temp_clone("work", holder="you")
    assert machine.copies == 1
    await driver.destroy_temp_clone("work")
    assert copy.workdir not in machine.dirs
    taken = await driver.derive_temp_clone("work", holder="you")
    assert taken.workdir == copy.workdir
    assert machine.copies == 2


async def test_holders_are_told_apart_by_equality() -> None:
    driver, _ = _driver()
    await driver.derive_temp_clone("work", holder=("flow", 1))
    same = await driver.derive_temp_clone("work", holder=("flow", 1))
    assert same.workdir == clone_dir(STATE, WORK, "work")
    with pytest.raises(TempCloneBusy):
        await driver.derive_temp_clone("work", holder=("flow", 2))


async def test_one_copy_is_made_however_many_ask_at_once() -> None:
    driver, machine = _driver()
    holder = object()
    copies = await asyncio.gather(
        *(driver.derive_temp_clone("work", holder=holder) for _ in range(50))
    )
    assert {copy.workdir for copy in copies} == {clone_dir(STATE, WORK, "work")}
    assert machine.copies == 1


async def test_one_of_many_holders_asking_at_once_gets_it() -> None:
    driver, machine = _driver()
    said = await asyncio.gather(
        *(driver.derive_temp_clone("work", holder=number) for number in range(50)),
        return_exceptions=True,
    )
    assert sum(isinstance(one, MachineEnvDriver) for one in said) == 1
    assert sum(isinstance(one, TempCloneBusy) for one in said) == 49
    assert machine.copies == 1


async def test_a_copy_that_could_not_be_made_is_held_by_nobody() -> None:
    driver, machine = _driver()
    machine.failing.add(WORK)
    with pytest.raises(EnvError, match="could not copy"):
        await driver.derive_temp_clone("work", holder="me")
    machine.failing.clear()
    copy = await driver.derive_temp_clone("work", holder="you")
    assert copy.workdir == clone_dir(STATE, WORK, "work")
    assert machine.holding == {(machine.identity, str(copy.workdir))}


async def test_a_copy_whose_making_was_cancelled_is_held_by_nobody() -> None:
    driver, _ = _driver()
    making = asyncio.create_task(driver.derive_temp_clone("work", holder="me"))
    await asyncio.sleep(0)
    making.cancel()
    with pytest.raises(asyncio.CancelledError):
        await making
    copy = await driver.derive_temp_clone("work", holder="you")
    assert copy.workdir == clone_dir(STATE, WORK, "work")


async def test_every_driver_on_a_machine_shares_who_holds_what() -> None:
    first, _ = _driver(MemoryMachine("shared"))
    second, _ = _driver(MemoryMachine("shared"))
    await first.derive_temp_clone("work", holder="first")
    with pytest.raises(TempCloneBusy):
        await second.derive_temp_clone("work", holder="second")
    await second.destroy_temp_clone("work")
    await second.derive_temp_clone("work", holder="second")
    elsewhere, _ = _driver(MemoryMachine("elsewhere"))
    await elsewhere.derive_temp_clone("work", holder="third")


async def test_closing_the_root_lets_a_resumed_run_hold_what_it_left() -> None:
    first, machine = _driver(MemoryMachine("resumed"))
    copy = await first.derive_temp_clone("work", holder="the first run")
    await copy.write("progress.txt", b"half")
    await first.close()
    assert machine.holding == set()
    # The resumed run's own root, on the same machine and its same disk.
    again_there = MemoryMachine("resumed")
    again_there.files, again_there.dirs = machine.files, machine.dirs
    resumed, _ = _driver(again_there)
    again = await resumed.derive_temp_clone("work", holder="the resumed run")
    assert again.workdir == copy.workdir
    assert await again.read("progress.txt") == b"half"
    assert again_there.copies == 0, "a resumed run copied again over what it left"


async def test_a_closed_root_is_closed_for_everything_derived_from_it() -> None:
    driver, _ = _driver()
    sub = await driver.derive_subdir("sub")
    await driver.close()
    assert not driver.available
    assert not sub.available
    for one in (driver, sub):
        for asked in (
            one.exec(["true"], timeout=0),
            one.read("x"),
            one.write("x", b"x"),
            one.derive_subdir("y"),
            one.derive_worktree(ref=None, dir=None),
            one.derive_temp_clone("z", holder="me"),
            one.destroy_temp_clone("z"),
            one.derive_scratch("z"),
            one.destroy_scratch("z"),
            one.probe(),
        ):
            with pytest.raises(EnvError, match="is closed"):
                await asked
    await driver.close()
    await sub.close()


class GatedMachine(MemoryMachine):
    """A machine whose commands take until a test says to start."""

    def __init__(self) -> None:
        super().__init__()
        self.gate = asyncio.Event()

    async def start(self, argv: Sequence[str], cwd: PurePosixPath) -> Scripted:
        await self.gate.wait()
        return await super().start(argv, cwd)


async def test_a_command_still_starting_when_the_root_closes_is_killed() -> None:
    machine = GatedMachine()
    driver, _ = _driver(machine)
    running = asyncio.create_task(driver.exec(list(SLOW_ARGV), timeout=0))
    copying = asyncio.create_task(machine.run(list(SLOW_ARGV), WORK))
    await asyncio.sleep(0.05)
    await driver.close()
    machine.gate.set()
    for task in (running, copying):
        with pytest.raises(EnvError, match="its environment was closed"):
            await asyncio.wait_for(task, 5)
    assert all(one.killed.is_set() for one in machine.started)
    assert machine.running == set()


async def test_a_copy_waiting_its_turn_when_the_root_closes_holds_nothing() -> None:
    driver, machine = _driver()
    first = asyncio.create_task(driver.derive_temp_clone("work", holder="me"))
    waiting = asyncio.create_task(driver.derive_temp_clone("work", holder="me"))
    await asyncio.sleep(0)
    await driver.close()
    await first
    with pytest.raises(EnvError, match="is closed"):
        await waiting
    assert machine.holding == set()
    again, _ = _driver(MemoryMachine(machine.identity))
    await again.derive_temp_clone("work", holder="somebody else")


async def test_closing_the_root_stops_what_the_machine_runs_for_itself() -> None:
    driver, machine = _driver()
    copying = asyncio.create_task(machine.run(list(SLOW_ARGV), WORK))
    await asyncio.sleep(0.05)
    await driver.close()
    with pytest.raises(EnvError, match="its environment was closed"):
        await copying
    assert machine.running == set()


async def test_closing_one_root_leaves_another_s_holds_alone() -> None:
    mine, _ = _driver(MemoryMachine("two roots"))
    theirs, _ = _driver(MemoryMachine("two roots"))
    await theirs.derive_temp_clone("theirs", holder="them")
    await mine.derive_temp_clone("mine", holder="me")
    await mine.close()
    again, _ = _driver(MemoryMachine("two roots"))
    with pytest.raises(TempCloneBusy):
        await again.derive_temp_clone("theirs", holder="me")
    await again.derive_temp_clone("mine", holder="me again")


async def test_ids_are_the_driver_s_own() -> None:
    driver, _ = _driver()
    sub = await driver.derive_subdir("sub")
    ours = await driver.derive_temp_clone("work", holder="me")
    theirs = await sub.derive_temp_clone("work", holder="you")
    assert ours.workdir != theirs.workdir


async def test_a_copy_inside_what_it_copies_is_refused() -> None:
    machine = MemoryMachine()
    driver = MachineEnvDriver(machine, PurePosixPath("/"), seen=True)
    with pytest.raises(EnvError, match="inside it"):
        await driver.derive_temp_clone("work", holder="me")
    assert machine.holding == set()


# ------------------------------------------------------------------------------- scratch


async def test_a_scratch_directory_is_one_per_id_until_it_is_removed() -> None:
    driver, machine = _driver()
    scratch = await driver.derive_scratch("notes")
    assert scratch.workdir == scratch_dir(STATE, WORK, "notes")
    await scratch.write("kept.txt", b"kept")
    same = await driver.derive_scratch("notes")
    assert await same.read("kept.txt") == b"kept"
    await driver.destroy_scratch("notes")
    await driver.destroy_scratch("notes")
    assert scratch.workdir not in machine.dirs
    assert (await driver.derive_scratch("notes")).workdir == scratch.workdir


async def test_a_scratch_directory_that_cannot_be_made_is_a_scratch_error() -> None:
    driver, machine = _driver()
    machine.files[scratch_dir(STATE, WORK, "notes")] = b"a file in the way"
    with pytest.raises(ScratchError):
        await driver.derive_scratch("notes")


# -------------------------------------------------------------------------------- layout


def test_everything_derived_lives_under_humanize_home_by_name() -> None:
    root = home_of(STATE, WORK)
    assert root.parent == STATE / ENVS
    assert root.name.startswith("work-")
    assert home_of(STATE, PurePosixPath("/")).name.startswith("root-")
    assert home_of(STATE, PurePosixPath("/a/work")) != root
    assert clone_dir(STATE, WORK, "x") == clone_dir(STATE, WORK, "x")
    assert clone_dir(STATE, WORK, "x").parent == root / "clones"
    assert scratch_dir(STATE, WORK, "x").parent == root / "scratch"
    assert clone_dir(STATE, WORK, "a/b") != clone_dir(STATE, WORK, "a-b")
    for id_ in ("", "..", "/", "a b/../c", "é" * 200):
        named = clone_dir(STATE, WORK, id_)
        assert named.parent == root / "clones", id_
        assert len(named.name) < 64, id_
    assert worktree_dir(STATE, WORK, None) != worktree_dir(STATE, WORK, None)


# ------------------------------------------------------------------------------- errors


def test_what_an_os_error_comes_to() -> None:
    cases: list[tuple[OSError, bool, type[EnvError]]] = [
        (FileNotFoundError(errno.ENOENT, "gone"), False, EnvFileNotFound),
        (NotADirectoryError(errno.ENOTDIR, "file"), True, EnvFileNotFound),
        (NotADirectoryError(errno.ENOTDIR, "file"), False, EnvError),
        (PermissionError(errno.EACCES, "no"), False, EnvPermissionDenied),
        (OSError(errno.EROFS, "read-only"), False, EnvPermissionDenied),
        (ConnectionResetError(errno.EPIPE, "closed"), False, EnvConnectionError),
        (TimeoutError(errno.ETIMEDOUT, "late"), False, EnvConnectionError),
        (OSError(errno.EISDIR, "a directory"), True, EnvError),
    ]
    for error, missing, expected in cases:
        made = env_error(error, "doing it", missing=missing)
        assert type(made) is expected, (error, made)
        assert str(made).startswith("doing it: ")
        again = pickle.loads(pickle.dumps(made))  # noqa: S301 -- our own bytes
        assert (type(again), str(again)) == (type(made), str(made))


def test_a_program_that_could_not_start_where_it_was_to_run_is_unavailable() -> None:
    gone = FileNotFoundError(errno.ENOENT, "No such file or directory", "/work")
    assert isinstance(started_error(gone, ["ls"], "/work"), EnvUnavailable)
    missing = FileNotFoundError(errno.ENOENT, "No such file or directory", "nope")
    assert type(started_error(missing, ["nope"], "/work")) is EnvFileNotFound


def test_an_exit_status_is_what_a_shell_says() -> None:
    assert [exit_status(n) for n in (0, 3, -9, -15)] == [0, 3, 137, 143]


# --------------------------------------------------------------------------- resources


def test_gpus_are_counted_as_cuda_would_see_them() -> None:
    said = [
        "0, GPU-aaaa1111, 81920",
        "1, GPU-bbbb2222, 40960",
        "2, GPU-cccc3333, [N/A]",
        "garbage",
    ]
    gib = 1024 * 1024
    assert gpus_of(said, None) == (3, 0)
    assert gpus_of(said[:2], None) == (2, 40960 * gib)
    assert gpus_of(said, "0") == (1, 81920 * gib)
    assert gpus_of(said, "1,0") == (2, 40960 * gib)
    assert gpus_of(said, "GPU-bbbb") == (1, 40960 * gib)
    assert gpus_of(said, "0,7,1") == (1, 81920 * gib), "CUDA stops at the first unknown"
    assert gpus_of(said, "0,0") == (1, 81920 * gib)
    assert gpus_of(said, "") == (0, 0)
    assert gpus_of(said, "-1") == (0, 0)
    assert gpus_of([], None) == (0, 0)


def test_what_a_host_says_about_itself_is_read() -> None:
    facts = facts_of(
        "home=/home/me\nstate=/home/me/.humanize\ncpus=64\nmemkb=1024\n"
        "cuda=1\ngpu=0, GPU-a, 100\ngpu=1, GPU-b, 200\n"
    )
    assert facts.home == PurePosixPath("/home/me")
    assert facts.state == PurePosixPath("/home/me/.humanize")
    assert facts.resources == Resources(64, 1024 * 1024, 1, 200 * 1024 * 1024)
    darwin = facts_of("home=/Users/me\nstate=rel/state\ncpus=\nmemory=4096\n")
    assert darwin.state == PurePosixPath("/Users/me/rel/state")
    assert darwin.resources == Resources(1, 4096, 0, 0)
    with pytest.raises(EnvConnectionError, match="home"):
        facts_of("cpus=4\n")


def test_the_probe_asks_for_everything_facts_are_read_from() -> None:
    for key in ("home=", "state=", "cpus=", "memkb=", "memory=", "cuda=", "gpu="):
        assert key in PROBE_SCRIPT, key


# ---------------------------------------------------------------------------------- ssh


async def test_an_ssh_environment_is_made_without_reaching_the_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused(*_: object, **__: object) -> None:
        raise AssertionError("the host was reached")

    monkeypatch.setattr("hmz.coganchor.transport.connect", refused)
    (spec,) = parse_envs(["gpu=ssh@me@gpu-box:2222/~/repo"])
    driver = open_env(spec)
    assert isinstance(driver, MachineEnvDriver)
    assert (driver.backend, driver.provider) == (EnvBackendKind.SSH, "me@gpu-box:2222")
    assert driver.workdir == PurePosixPath("~/repo")
    assert not driver.available
    assert (driver.cpu_count, driver.memory, driver.gpu_count) == (1, 0, 0)
    placement = driver.placement()
    assert (placement.backend, placement.provider, placement.workdir) == (
        EnvBackendKind.SSH,
        "me@gpu-box:2222",
        PurePosixPath("~/repo"),
    )
    assert isinstance(placement.machine, AnchoredConfig)
    assert placement.machine.anchor.target == "ssh://me@gpu-box:2222"
    assert placement.machine.anchor.remote_path == "~/repo"
    await driver.close()


def test_an_absolute_ssh_workdir_is_the_anchor_s_workspace() -> None:
    (spec,) = parse_envs(["gpu=ssh@gpu-box/srv/repo"])
    placement = open_env(spec).placement()
    assert isinstance(placement.machine, AnchoredConfig)
    assert placement.machine.anchor.workspace == "/srv/repo"
    assert placement.machine.anchor.remote_path is None


def test_a_workdir_is_one_name_for_one_place() -> None:
    cases = {
        "~/proj/.": "~/proj",
        "~/proj/./a/../b": "~/proj/b",
        "~/x/..": "~",
        "~": "~",
        "/a/./b/..": "/a",
        "/": "/",
    }
    for written, tidied in cases.items():
        assert tidy_workdir(PurePosixPath(written)) == PurePosixPath(tidied), written
    for refused in ("~/..", "~/../x", "relative/path"):
        with pytest.raises(EnvUnavailable):
            tidy_workdir(PurePosixPath(refused))
    (spec,) = parse_envs(["w=ssh@host/~/proj/."])
    assert open_env(spec).workdir == PurePosixPath("~/proj")


def test_only_a_broken_connection_is_taken_for_one() -> None:
    from hmz.coganchor.proto import RemoteOSError

    machine = SSHMachine("host")
    stale = RemoteOSError(errno.ENOTCONN, "Transport endpoint is not connected")
    said = machine._failed(stale, "could not read /mnt/nfs/x")
    assert type(said) is EnvError
    assert not machine._broken, "a stale mount there was taken for the link breaking"
    missing = RemoteOSError(errno.ENOENT, "No such file or directory")
    assert type(machine._failed(missing, "read", missing=True)) is EnvFileNotFound
    late = TimeoutError(errno.ETIMEDOUT, "the target did not reply within 120s")
    assert type(machine._failed(late, "could not look at /mnt/hung")) is EnvError
    assert not machine._broken, "one slow ask was taken for the link breaking"
    gone = ConnectionResetError(errno.EPIPE, "the target disconnected")
    assert type(machine._failed(gone, "could not read x")) is EnvConnectionError
    assert machine._broken


def test_what_is_no_ssh_host_is_refused() -> None:
    for provider in ("-oProxyCommand=evil", "host name", "host;rm", "", "@host"):
        with pytest.raises(EnvUnavailable, match="not an ssh host"):
            SSHMachine(provider)
    for provider in ("host", "user@host", "host:22", "u.s-er@h.o_st-1:65535", "alias"):
        assert SSHMachine(provider).identity == f"ssh:{provider}"

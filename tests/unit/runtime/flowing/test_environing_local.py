"""This machine, as an environment driver does its work on it: files, holds and what it has.

Its commands are subprocesses, which unit tests do not start; the integration tests run them.
"""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from hmz import home
from hmz.flows import (
    EnvBackendKind,
    EnvError,
    EnvFileNotFound,
    EnvPermissionDenied,
    TempCloneBusy,
)
from hmz.runtime.flowing.environing_local import LocalMachine
from hmz.runtime.flowing.spi import Placement


def _at(path: Path) -> PurePosixPath:
    return PurePosixPath(path)


@pytest.fixture(autouse=True)
def _no_nvidia_smi(monkeypatch: pytest.MonkeyPatch) -> None:
    """A machine with no `nvidia-smi`, so that nothing is run to ask for its GPUs."""
    which = shutil.which

    def found(name: str, *args: Any, **kwargs: Any) -> str | None:
        return None if name == "nvidia-smi" else which(name, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", found)


# ------------------------------------------------------------------------ what it says


def test_this_machine_is_local_and_named_by_nothing() -> None:
    machine = LocalMachine()

    assert (machine.backend, machine.provider, machine.identity) == (
        EnvBackendKind.LOCAL,
        "",
        "local",
    )
    assert machine.placement(PurePosixPath("/w")) == Placement(
        EnvBackendKind.LOCAL, "", PurePosixPath("/w"), None
    )


async def test_it_has_at_least_one_cpu_and_some_memory() -> None:
    machine = LocalMachine()
    await machine.probe()

    said = machine.resources(gpus=False)

    assert said.cpu_count >= 1
    assert said.memory > 0
    assert (said.gpu_count, said.gpu_memory) == (0, 0)
    assert machine.resources(gpus=True).cpu_count == said.cpu_count


def test_a_program_is_looked_for_on_its_path_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    machine = LocalMachine()
    asked: list[str] = []

    def which(name: str, *_: Any, **__: Any) -> str | None:
        asked.append(name)
        return "/usr/bin/git" if name == "git" else None

    monkeypatch.setattr(shutil, "which", which)

    assert (machine.has("git"), machine.has("git"), machine.has("bash")) == (
        True,
        True,
        False,
    )
    assert asked == ["git", "bash"]


def test_a_workdir_is_available_while_it_is_a_directory_here(tmp_path: Path) -> None:
    machine = LocalMachine()
    (tmp_path / "file").write_text("x")

    assert machine.available(_at(tmp_path), seen=False)
    assert not machine.available(_at(tmp_path / "gone"), seen=True)
    assert not machine.available(_at(tmp_path / "file"), seen=True)


async def test_home_is_this_users_and_state_is_humanizes_own() -> None:
    machine = LocalMachine()

    assert await machine.absolute(PurePosixPath("~/x")) == PurePosixPath(
        Path.home(), "x"
    )
    assert await machine.absolute(PurePosixPath("/x")) == PurePosixPath("/x")
    assert await machine.state() == PurePosixPath(home().absolute())


# ------------------------------------------------------------------------------- files


async def test_a_file_is_written_whole_and_read_back(tmp_path: Path) -> None:
    machine = LocalMachine()
    path = tmp_path / "a" / "b" / "c.txt"

    await machine.write(_at(path), b"one")
    path.chmod(0o640)
    await machine.write(_at(path), b"two")

    assert await machine.read(_at(path)) == b"two"
    assert stat.S_IMODE(path.stat().st_mode) == 0o640, "its mode is kept"
    assert sorted(one.name for one in path.parent.iterdir()) == ["c.txt"]


async def test_a_file_written_through_a_link_is_written_where_it_points(
    tmp_path: Path,
) -> None:
    machine = LocalMachine()
    real = tmp_path / "real.txt"
    real.write_bytes(b"old")
    (tmp_path / "link.txt").symlink_to(real)

    await machine.write(_at(tmp_path / "link.txt"), b"new")

    assert (tmp_path / "link.txt").is_symlink()
    assert real.read_bytes() == b"new"


async def test_what_cannot_be_read_says_why(tmp_path: Path) -> None:
    machine = LocalMachine()
    (tmp_path / "file").write_text("x")

    with pytest.raises(EnvFileNotFound):
        await machine.read(_at(tmp_path / "missing"))
    with pytest.raises(EnvFileNotFound):
        await machine.read(_at(tmp_path / "file" / "under"))
    with pytest.raises(EnvError):
        await machine.read(_at(tmp_path))


@pytest.mark.skipif(os.geteuid() == 0, reason="root may write anywhere")
async def test_what_may_not_be_written_is_permission_denied(tmp_path: Path) -> None:
    machine = LocalMachine()
    locked = tmp_path / "locked"
    locked.mkdir(mode=0o500)
    try:
        with pytest.raises(EnvPermissionDenied):
            await machine.write(_at(locked / "x"), b"")
    finally:
        locked.chmod(0o700)


async def test_a_directory_is_made_with_those_above_it(tmp_path: Path) -> None:
    machine = LocalMachine()
    (tmp_path / "file").write_text("x")

    await machine.mkdir(_at(tmp_path / "a" / "b"))
    await machine.mkdir(_at(tmp_path / "a" / "b"))

    assert await machine.is_dir(_at(tmp_path / "a" / "b"))
    assert not await machine.is_dir(_at(tmp_path / "file"))
    with pytest.raises(EnvError):
        await machine.mkdir(_at(tmp_path / "file" / "under"))


async def test_a_tree_is_removed_even_where_nobody_may_write_in_it(
    tmp_path: Path,
) -> None:
    machine = LocalMachine()
    tree = tmp_path / "tree"
    (tree / "cache").mkdir(parents=True)
    (tree / "cache" / "module.py").write_text("x")
    (tree / "cache").chmod(0o500)
    (tmp_path / "file").write_text("x")

    await machine.remove(_at(tree))
    await machine.remove(_at(tmp_path / "file"))
    await machine.remove(_at(tmp_path / "never"))

    assert not await machine.is_dir(_at(tree))
    with pytest.raises(EnvFileNotFound):
        await machine.read(_at(tmp_path / "file"))


# ------------------------------------------------------------------------------- holds


async def test_a_copy_is_held_against_every_other_holder_until_let_go(
    tmp_path: Path,
) -> None:
    copy = _at(tmp_path / "clones" / "a")
    lock = tmp_path / "clones" / "a.lock"

    held = await LocalMachine().claim(copy)
    with pytest.raises(TempCloneBusy):
        await LocalMachine().claim(copy)
    held.release(forget=False)
    again = await LocalMachine().claim(copy)

    assert lock.exists()
    again.release(forget=True)
    again.release(forget=True)
    assert not lock.exists()
    (await LocalMachine().claim(copy)).release(forget=False)


async def test_a_hold_that_cannot_be_taken_is_an_env_error(tmp_path: Path) -> None:
    (tmp_path / "file").write_text("x")

    with pytest.raises(EnvError, match="could not hold"):
        await LocalMachine().claim(_at(tmp_path / "file" / "a"))

"""What a trapped syscall is answered with, the tracee's memory read from a dict.

Linux only: the dispatcher is written against that kernel's syscall numbers and register map.
"""

from __future__ import annotations

import errno
import sys
from dataclasses import dataclass, field
from typing import Any

import pytest

if sys.platform != "linux":
    pytest.skip("the syscall layer is Linux's alone", allow_module_level=True)

from hmz.coganchor.handlers import (
    ALLOW,
    AT_FDCWD,
    AT_REMOVEDIR,
    O_CREAT,
    O_DIRECTORY,
    O_TRUNC,
    O_WRONLY,
    STALL,
    Action,
    SyscallDispatcher,
    fails,
)
from hmz.coganchor.linux import procfs, ptrace
from hmz.coganchor.linux.syscalls import NR
from hmz.coganchor.supervisor import Tracee


def test_the_three_answers() -> None:
    assert Action("allow") == ALLOW
    assert Action("stall") == STALL
    assert fails(errno.EEXIST) == Action("errno", errno.EEXIST)
    assert fails(0) == Action("errno", errno.EIO)


@dataclass
class Router:
    """Everything under `/m` is the target's `/v`."""

    redirects: tuple[tuple[str, str], ...] = ()
    settles: bool = False

    def is_remote_path(self, path: str) -> bool:
        return path == "/m" or path.startswith("/m/")

    def canonical(self, path: str) -> str:
        return path

    def swap(self, path: str) -> str | None:
        return None

    def to_virtual(self, path: str) -> str:
        return "/v" + path[len("/m") :]


@dataclass
class Recorder:
    """Records every call made of it, and raises `fails` for the names in it."""

    calls: list[tuple[str, tuple[Any, ...]]] = field(
        default_factory=list[tuple[str, tuple[Any, ...]]]
    )
    fails: dict[str, OSError] = field(default_factory=dict[str, OSError])

    def __getattr__(self, name: str) -> Any:
        def call(*args: Any) -> None:
            self.calls.append((name, args))
            if name in self.fails:
                raise self.fails[name]

        return call

    def named(self) -> list[str]:
        return [name for name, _ in self.calls]


@dataclass
class Supervisor:
    router: Router = field(default_factory=Router)
    shadow: Recorder = field(default_factory=Recorder)
    client: Recorder = field(default_factory=Recorder)


@pytest.fixture
def memory(monkeypatch: pytest.MonkeyPatch) -> dict[int, str]:
    """The tracee's strings, by address; its working directory is `/m/cwd`."""
    held: dict[int, str] = {}

    def read_cstring(pid: int, address: int, limit: int = 0) -> str | None:
        return held.get(address)

    def resolve_magic(pid: int, path: str) -> str:
        return path

    def working_directory(pid: int) -> str:
        return "/m/cwd"

    monkeypatch.setattr(procfs, "read_cstring", read_cstring)
    monkeypatch.setattr(procfs, "resolve_magic", resolve_magic)
    monkeypatch.setattr(procfs, "working_directory", working_directory)
    return held


def stopped(number: int, *args: int) -> ptrace.Registers:
    registers = ptrace.blank()
    registers.syscall_number = number
    for at, value in enumerate(args):
        registers.set_arg(at, value)
    return registers


def dispatch(supervisor: Supervisor, registers: ptrace.Registers) -> Action:
    return SyscallDispatcher(supervisor).dispatch(Tracee(pid=77), registers)  # pyright: ignore[reportArgumentType]


def test_a_syscall_nothing_handles_is_allowed(memory: dict[int, str]) -> None:
    supervisor = Supervisor()
    assert dispatch(supervisor, stopped(0xFFFF)) is ALLOW
    assert supervisor.client.calls == []


def test_a_directory_made_in_the_workspace_is_made_on_the_target_first(
    memory: dict[int, str],
) -> None:
    memory[1] = "/m/new"
    supervisor = Supervisor()
    assert dispatch(supervisor, stopped(NR.MKDIRAT, AT_FDCWD, 1, 0o40755)) == ALLOW
    assert supervisor.client.calls == [("mkdir", ("/v/new", 0o755))]
    assert "ensure_path" in supervisor.shadow.named()


def test_the_targets_error_is_the_syscalls(memory: dict[int, str]) -> None:
    memory[1] = "/m/there"
    supervisor = Supervisor()
    supervisor.client.fails["mkdir"] = FileExistsError(errno.EEXIST, "exists")
    assert dispatch(supervisor, stopped(NR.MKDIRAT, AT_FDCWD, 1, 0o755)) == fails(
        errno.EEXIST
    )


def test_a_relative_path_is_read_against_the_working_directory(
    memory: dict[int, str],
) -> None:
    memory[1] = "sub/../d"
    supervisor = Supervisor()
    dispatch(supervisor, stopped(NR.MKDIRAT, AT_FDCWD, 1, 0o700))
    assert supervisor.client.calls == [("mkdir", ("/v/cwd/d", 0o700))]


def test_a_path_outside_the_workspace_runs_here(memory: dict[int, str]) -> None:
    memory[1] = "/tmp/x"
    supervisor = Supervisor()
    assert dispatch(supervisor, stopped(NR.MKDIRAT, AT_FDCWD, 1, 0o755)) is ALLOW
    assert dispatch(supervisor, stopped(NR.UNLINKAT, AT_FDCWD, 1, 0)) is ALLOW
    assert supervisor.client.calls == []


@pytest.mark.parametrize(("flags", "removes"), [(0, "unlink"), (AT_REMOVEDIR, "rmdir")])
def test_a_removal_is_made_on_the_target_and_forgotten_here(
    memory: dict[int, str], flags: int, removes: str
) -> None:
    memory[1] = "/m/gone"
    supervisor = Supervisor()
    assert dispatch(supervisor, stopped(NR.UNLINKAT, AT_FDCWD, 1, flags)) is ALLOW
    assert supervisor.client.calls == [(removes, ("/v/gone",))]
    assert ("forget", ("/m/gone",)) in supervisor.shadow.calls


def test_a_removal_the_target_refuses_is_not_forgotten(memory: dict[int, str]) -> None:
    memory[1] = "/m/kept"
    supervisor = Supervisor()
    supervisor.client.fails["unlink"] = PermissionError(errno.EACCES, "no")
    assert dispatch(supervisor, stopped(NR.UNLINKAT, AT_FDCWD, 1, 0)) == fails(
        errno.EACCES
    )
    assert "forget" not in supervisor.shadow.named()


@pytest.mark.parametrize(
    ("flags", "asked"),
    [
        (0, ["ensure_path", "ensure_content"]),
        (O_WRONLY | O_CREAT, ["ensure_path", "ensure_content", "note_write"]),
        (O_WRONLY | O_TRUNC, ["ensure_path", "note_write"]),
        (O_DIRECTORY, ["ensure_path", "ensure_directory"]),
    ],
)
def test_an_open_makes_the_mirror_tell_the_truth_first(
    memory: dict[int, str], flags: int, asked: list[str]
) -> None:
    memory[1] = "/m/f"
    supervisor = Supervisor()
    assert dispatch(supervisor, stopped(NR.OPENAT, AT_FDCWD, 1, flags)) is ALLOW
    assert supervisor.shadow.named() == asked
    assert supervisor.client.calls == []


def test_a_null_path_is_left_to_the_kernel(memory: dict[int, str]) -> None:
    supervisor = Supervisor()
    assert dispatch(supervisor, stopped(NR.OPENAT, AT_FDCWD, 0, 0)) is ALLOW
    assert supervisor.shadow.calls == []


def test_a_tracee_gone_mid_call_is_let_go(
    memory: dict[int, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def gone(pid: int, address: int, limit: int = 0) -> str:
        raise procfs.TraceeGoneError(errno.ESRCH, "gone")

    monkeypatch.setattr(procfs, "read_cstring", gone)
    assert dispatch(Supervisor(), stopped(NR.MKDIRAT, AT_FDCWD, 1, 0)) is ALLOW

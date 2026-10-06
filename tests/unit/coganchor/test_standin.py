"""Parking a stopped `execve` as a stand-in: what is asked of the tracee, and when it is given up.

The tracee is a stand-in too: ptrace, the tracee's memory, waiting and killing are replaced by
a script of what the kernel answers. Linux only: the register map loads on Linux alone.
"""

from __future__ import annotations

import errno
import os
import signal
import sys
from dataclasses import dataclass, field

import pytest

if sys.platform != "linux":
    pytest.skip("ptrace is Linux's", allow_module_level=True)

from typing import TYPE_CHECKING

from hmz.coganchor.linux import procfs, ptrace
from hmz.coganchor.linux.syscalls import ARCH, NR
from hmz.coganchor.standin import STUB_PROGRAM, park

if TYPE_CHECKING:
    from hmz.coganchor.linux.ptrace import Registers

PID = 4242
STACK = 0x7FFF_0000
BLOB = STUB_PROGRAM.encode() + b"\0"

#: Wait statuses, as `waitpid` reports them for a traced process.
EXEC_EVENT = (ptrace.EVENT_EXEC << 16) | (signal.SIGTRAP << 8) | 0x7F
SECCOMP_EVENT = (ptrace.EVENT_SECCOMP << 16) | (signal.SIGTRAP << 8) | 0x7F
SYSCALL_STOP = ((signal.SIGTRAP | ptrace.SYSCALL_STOP_SIG) << 8) | 0x7F
SIGNAL_STOP = (signal.SIGCHLD << 8) | 0x7F
EXITED = 0


@dataclass
class Tracee:
    """What the kernel answers about one stopped process, and what was asked of it."""

    statuses: list[int] = field(default_factory=lambda: [EXEC_EVENT, SYSCALL_STOP])
    kinds: list[int | None] = field(default_factory=lambda: [ptrace.SYSCALL_STOP_ENTRY])
    memory: dict[int, bytes] = field(default_factory=dict[int, bytes])
    echo: bool = True
    writable: bool = True
    settable: bool = True
    result: int = 0
    set: list[tuple[int, ...]] = field(default_factory=list[tuple[int, ...]])
    asked: list[str] = field(default_factory=list[str])
    killed: list[tuple[int, int]] = field(default_factory=list[tuple[int, int]])

    def write_bytes(self, pid: int, address: int, data: bytes) -> int:
        if not self.writable:
            raise OSError(errno.EFAULT, "bad address")
        self.memory[address] = data
        return len(data)

    def read_bytes(self, pid: int, address: int, size: int) -> bytes:
        said = self.memory.get(address, b"")
        return said if self.echo else said[::-1]

    def setregs(self, pid: int, registers: Registers) -> None:
        if not self.settable:
            raise OSError(errno.ESRCH, "gone")
        self.asked.append("setregs")
        self.set.append(tuple(registers.arg(index) for index in range(6)))

    def cont(self, pid: int, signal: int = 0) -> None:
        self.asked.append("cont")

    def syscall(self, pid: int, signal: int = 0) -> None:
        self.asked.append("syscall")

    def waitpid(self, pid: int, options: int) -> tuple[int, int]:
        assert pid == PID
        assert options == ptrace.WALL
        return pid, self.statuses.pop(0)

    def syscall_stop_kind(self, pid: int) -> int | None:
        return self.kinds.pop(0) if len(self.kinds) > 1 else self.kinds[0]

    def getregs(self, pid: int, into: Registers | None = None) -> Registers:
        registers = ptrace.blank()
        registers.result = self.result
        return registers

    def kill(self, pid: int, signal: int) -> None:
        self.killed.append((pid, signal))


@pytest.fixture
def tracee(monkeypatch: pytest.MonkeyPatch) -> Tracee:
    held = Tracee()
    for name in ("setregs", "cont", "syscall", "syscall_stop_kind", "getregs"):
        monkeypatch.setattr(ptrace, name, getattr(held, name))
    monkeypatch.setattr(procfs, "write_bytes", held.write_bytes)
    monkeypatch.setattr(procfs, "read_bytes", held.read_bytes)
    monkeypatch.setattr(os, "waitpid", held.waitpid)
    monkeypatch.setattr(os, "kill", held.kill)
    return held


def stopped(number: int) -> Registers:
    registers = ptrace.blank()
    registers.buffer[ARCH.stack_index] = STACK
    registers.buffer[ARCH.number_index] = number
    return registers


def test_the_stub_is_a_program_the_kernel_can_load() -> None:
    assert os.access(STUB_PROGRAM, os.X_OK)


def test_an_execve_is_pointed_at_the_stub_and_caught_after_it(tracee: Tracee) -> None:
    registers = stopped(NR.EXECVE)
    where = registers.scratch(len(BLOB))

    assert park(PID, registers)

    assert tracee.memory == {where: BLOB}
    assert tracee.set == [(where, 0, 0, 0, 0, 0)]
    assert tracee.asked == ["setregs", "cont", "syscall"]
    assert tracee.killed == []


def test_an_execveat_is_pointed_at_the_stub_from_the_working_directory(
    tracee: Tracee,
) -> None:
    registers = stopped(NR.EXECVEAT)
    where = registers.scratch(len(BLOB))

    assert park(PID, registers)

    assert tracee.set == [((-100) % (1 << 64), where, 0, 0, 0, 0)]


@pytest.mark.parametrize(
    "kind", [ptrace.SYSCALL_STOP_ENTRY, ptrace.SYSCALL_STOP_SECCOMP]
)
def test_it_steps_past_an_exit_stop_to_the_next_entry(
    tracee: Tracee, kind: int
) -> None:
    tracee.statuses = [EXEC_EVENT, SYSCALL_STOP, SECCOMP_EVENT]
    tracee.kinds = [ptrace.SYSCALL_STOP_EXIT, kind]

    assert park(PID, stopped(NR.EXECVE))

    assert tracee.asked == ["setregs", "cont", "syscall", "syscall"]


@pytest.mark.parametrize("writable", [False, True])
def test_no_room_for_the_stub_leaves_the_process_where_it_was(
    tracee: Tracee, writable: bool
) -> None:
    tracee.writable = writable
    tracee.echo = False

    assert not park(PID, stopped(NR.EXECVE))

    assert tracee.asked == []
    assert tracee.killed == []


@pytest.mark.parametrize(
    ("statuses", "kinds"),
    [
        ([EXITED], [ptrace.SYSCALL_STOP_ENTRY]),
        ([SIGNAL_STOP], [ptrace.SYSCALL_STOP_ENTRY]),
        ([EXEC_EVENT, EXITED], [ptrace.SYSCALL_STOP_ENTRY]),
        ([EXEC_EVENT, SIGNAL_STOP], [ptrace.SYSCALL_STOP_ENTRY]),
        ([EXEC_EVENT, *[SYSCALL_STOP] * 4], [ptrace.SYSCALL_STOP_EXIT]),
    ],
)
def test_a_stand_in_lost_after_the_exec_is_killed(
    tracee: Tracee, statuses: list[int], kinds: list[int | None]
) -> None:
    tracee.statuses = statuses
    tracee.kinds = kinds

    assert not park(PID, stopped(NR.EXECVE))

    assert tracee.killed == [(PID, signal.SIGKILL)]


def test_a_tracee_gone_before_the_exec_is_killed_too(tracee: Tracee) -> None:
    tracee.settable = False

    assert not park(PID, stopped(NR.EXECVE))

    assert tracee.killed == [(PID, signal.SIGKILL)]


@pytest.mark.skipif(
    not ARCH.entry_plants_enosys, reason="this architecture parks no -ENOSYS"
)
@pytest.mark.parametrize(("result", "parked"), [(-errno.ENOSYS, True), (0, False)])
def test_an_old_kernel_is_read_by_the_enosys_it_parks(
    tracee: Tracee, result: int, parked: bool
) -> None:
    tracee.kinds = [None]
    tracee.result = result
    tracee.statuses = [EXEC_EVENT, *[SYSCALL_STOP] * 4]

    assert park(PID, stopped(NR.EXECVE)) is parked

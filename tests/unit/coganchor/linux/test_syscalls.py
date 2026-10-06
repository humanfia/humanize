"""The syscall tables and register maps the tracer and the filters are built from.

Linux only: collected there and nowhere else (see `conftest.py`).
"""

from __future__ import annotations

import dataclasses
import platform

import pytest

from hmz.coganchor.linux.syscalls import (
    ARCH,
    NR,
    SUPPORTED_MACHINES,
    TRAPPED_SYSCALLS,
    Arch,
    syscall_name,
)

ARCHES = sorted(SUPPORTED_MACHINES.values(), key=lambda arch: arch.name)


def numbers(arch: Arch) -> dict[str, int]:
    return {
        field.name: getattr(arch.numbers, field.name)
        for field in dataclasses.fields(arch.numbers)
    }


def test_this_host_is_the_architecture_it_reports() -> None:
    assert SUPPORTED_MACHINES[platform.machine()] is ARCH
    assert NR is ARCH.numbers


def test_the_trap_set_is_this_hosts_and_has_nothing_absent() -> None:
    assert NR.trapped() == TRAPPED_SYSCALLS
    assert all(number >= 0 for number in TRAPPED_SYSCALLS)


@pytest.mark.parametrize(
    "name", ["EXECVE", "EXECVEAT", "OPENAT", "NEWFSTATAT", "RENAMEAT2", "CONNECT"]
)
def test_the_cold_calls_are_trapped(name: str) -> None:
    assert getattr(NR, name) in TRAPPED_SYSCALLS


@pytest.mark.parametrize(
    "name", ["EXIT_GROUP", "SOCKET", "BIND", "LISTEN", "SECCOMP", "PIDFD_GETFD"]
)
def test_the_rest_run_untouched(name: str) -> None:
    assert getattr(NR, name) not in TRAPPED_SYSCALLS


@pytest.mark.parametrize("arch", ARCHES, ids=lambda arch: arch.name)
def test_every_call_has_a_number_of_its_own(arch: Arch) -> None:
    said = list(numbers(arch).values())

    assert len(set(said)) == len(said)
    assert all(number >= 0 or number <= -1000 for number in said)


@pytest.mark.parametrize("arch", ARCHES, ids=lambda arch: arch.name)
def test_a_call_an_architecture_lacks_is_never_trapped(arch: Arch) -> None:
    trapped = arch.numbers.trapped()

    assert all(number >= 0 for number in trapped)
    assert arch.numbers.EXECVE in trapped


@pytest.mark.parametrize("arch", ARCHES, ids=lambda arch: arch.name)
def test_the_register_map_fits_the_register_set(arch: Arch) -> None:
    indices = [
        arch.number_index,
        arch.result_index,
        arch.stack_index,
        *arch.arg_indices,
    ]

    assert len(arch.arg_indices) == len(set(arch.arg_indices)) == 6
    assert all(0 <= one < arch.register_count for one in indices)


@pytest.mark.parametrize(
    ("machine", "openat", "execve", "has_open"),
    [("x86_64", 257, 59, True), ("aarch64", 56, 221, False)],
)
def test_the_tables_are_the_kernels(
    machine: str, openat: int, execve: int, has_open: bool
) -> None:
    table = SUPPORTED_MACHINES[machine].numbers

    assert openat == table.OPENAT
    assert execve == table.EXECVE
    assert (table.OPEN >= 0) is has_open


def test_aarch64_renumbers_through_a_regset_of_its_own() -> None:
    assert SUPPORTED_MACHINES["x86_64"].number_regset is None
    assert SUPPORTED_MACHINES["aarch64"].number_regset is not None
    assert SUPPORTED_MACHINES["x86_64"].red_zone == 128
    assert SUPPORTED_MACHINES["aarch64"].red_zone == 0


@pytest.mark.parametrize(
    ("number", "name"),
    [
        (NR.OPENAT, "openat"),
        (NR.EXECVE, "execve"),
        (-1, "syscall_-1"),
        (99999, "syscall_99999"),
    ],
)
def test_syscall_name(number: int, name: str) -> None:
    assert syscall_name(number) == name

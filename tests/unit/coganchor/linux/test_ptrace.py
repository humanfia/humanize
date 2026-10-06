"""A register set as the tracer reads and rewrites it, with no tracee behind it.

Linux only: collected there and nowhere else (see `conftest.py`).
"""

from __future__ import annotations

import pytest

from hmz.coganchor.linux.ptrace import Registers, blank
from hmz.coganchor.linux.syscalls import ARCH, NR

WORD = 1 << 64


@pytest.fixture
def registers() -> Registers:
    return blank()


def test_a_blank_set_is_this_architectures_shape_and_clean(
    registers: Registers,
) -> None:
    assert len(registers.buffer) == ARCH.register_count
    assert all(word == 0 for word in registers.buffer)
    assert not registers.dirty
    assert not registers.renumbered
    assert registers.vector != registers.number_vector


def test_a_new_syscall_number_reads_back_and_dirties(registers: Registers) -> None:
    registers.syscall_number = NR.OPENAT

    assert registers.syscall_number == NR.OPENAT
    assert registers.dirty
    assert registers.renumbered is (ARCH.number_regset is not None)


def test_a_cancelled_syscall_reads_back_as_the_register_would_hold_it(
    registers: Registers,
) -> None:
    registers.syscall_number = -1

    assert registers.syscall_number == WORD - 1


def test_settled_forgets_what_was_written(registers: Registers) -> None:
    registers.syscall_number = NR.OPENAT
    registers.set_arg(0, 1)

    registers.settled()

    assert not registers.dirty
    assert not registers.renumbered


def test_the_syscall_number_is_read_from_its_register(registers: Registers) -> None:
    registers.buffer[ARCH.number_index] = NR.EXECVE

    assert registers.syscall_number == NR.EXECVE
    assert not registers.dirty


@pytest.mark.parametrize("value", [0, 3, -2, -4095])
def test_the_result_is_signed(registers: Registers, value: int) -> None:
    registers.result = value

    assert registers.result == value
    assert registers.buffer[ARCH.result_index] == value % WORD
    assert registers.dirty


@pytest.mark.parametrize("index", range(6))
def test_each_argument_is_its_own_register(registers: Registers, index: int) -> None:
    registers.set_arg(index, -100)

    assert registers.arg(index) == WORD - 100
    assert registers.signed_arg(index) == -100
    assert registers.buffer[ARCH.arg_indices[index]] == WORD - 100
    assert all(registers.arg(other) == 0 for other in range(6) if other != index)
    assert registers.dirty


@pytest.mark.parametrize(
    ("word", "signed"), [(0xFFFFFFFF, -1), (0x1_0000_0005, 5), (0x7FFFFFFF, 0x7FFFFFFF)]
)
def test_a_signed_argument_is_its_low_c_int(
    registers: Registers, word: int, signed: int
) -> None:
    registers.buffer[ARCH.arg_indices[0]] = word

    assert registers.signed_arg(0) == signed


def test_scratch_is_below_the_stack_clear_of_the_red_zone(registers: Registers) -> None:
    registers.buffer[ARCH.stack_index] = 0x7FFF_0000

    assert registers.stack_pointer == 0x7FFF_0000
    assert registers.scratch(16) == 0x7FFF_0000 - ARCH.red_zone - 16
    assert registers.scratch(1) - registers.scratch(16) == 15

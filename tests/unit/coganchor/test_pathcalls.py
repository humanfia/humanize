"""The one table of which syscalls name a path, and in which arguments.

Linux only: the table is keyed by this host's syscall numbers, which load on Linux alone.
"""

from __future__ import annotations

import sys

import pytest

if sys.platform != "linux":
    pytest.skip("syscall numbers are Linux's", allow_module_level=True)

from hmz.coganchor.linux.syscalls import NR, TRAPPED_SYSCALLS
from hmz.coganchor.pathcalls import LOOKS, MAKES, PATHS


def test_every_call_that_looks_or_makes_names_a_path() -> None:
    assert PATHS.keys() >= LOOKS
    assert PATHS.keys() >= MAKES
    assert not LOOKS & MAKES


def test_every_call_that_names_a_path_is_trapped_where_this_host_has_it() -> None:
    assert {one for one in PATHS if one >= 0} <= TRAPPED_SYSCALLS


def test_what_a_process_becomes_is_not_a_path_call() -> None:
    assert NR.EXECVE not in PATHS
    assert NR.EXECVEAT not in PATHS


def test_each_path_follows_the_descriptor_it_resolves_against() -> None:
    for pairs in PATHS.values():
        assert pairs
        for descriptor, path in pairs:
            assert 0 <= path < 6
            assert descriptor is None or descriptor == path - 1


@pytest.mark.parametrize(
    ("name", "pairs"),
    [
        ("OPENAT", ((0, 1),)),
        ("STATX", ((0, 1),)),
        ("RENAMEAT2", ((0, 1), (2, 3))),
        ("LINKAT", ((0, 1), (2, 3))),
        ("SYMLINKAT", ((1, 2),)),
        ("FANOTIFY_MARK", ((3, 4),)),
        ("INOTIFY_ADD_WATCH", ((None, 1),)),
        ("MKDIRAT", ((0, 1),)),
        ("UNLINKAT", ((0, 1),)),
    ],
)
def test_where_each_call_keeps_its_paths(
    name: str, pairs: tuple[tuple[int | None, int], ...]
) -> None:
    assert PATHS[getattr(NR, name)] == pairs


@pytest.mark.parametrize("name", ["NEWFSTATAT", "STATX", "READLINKAT", "FACCESSAT"])
def test_lookups_only_look(name: str) -> None:
    assert getattr(NR, name) in LOOKS
    assert getattr(NR, name) not in MAKES


@pytest.mark.parametrize(
    "name", ["MKDIRAT", "SYMLINKAT", "LINKAT", "RENAMEAT2", "MKNODAT"]
)
def test_calls_that_make_something_make(name: str) -> None:
    assert getattr(NR, name) in MAKES


@pytest.mark.parametrize("name", ["OPENAT", "UNLINKAT", "FCHMODAT", "UTIMENSAT"])
def test_other_calls_neither_only_look_nor_make(name: str) -> None:
    assert getattr(NR, name) not in LOOKS | MAKES

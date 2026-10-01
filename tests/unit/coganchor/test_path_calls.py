"""Which syscalls the supervisor stops for a path, and where each keeps the paths it names.

Whether every one of them really reaches the mirror by a name only the target has is
`tests/system/coganchor/test_spellings.py`, which makes each call under a real supervisor.
Here are the tables that decides from: a call left out of either is a call whose path is run
exactly as the agent named it.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from tests.supervising import WITHOUT_BINDINGS

if WITHOUT_BINDINGS:
    pytest.skip(WITHOUT_BINDINGS, allow_module_level=True)

from hmz.coganchor.handlers import _REDIRECTABLE, SyscallDispatcher
from hmz.coganchor.linux.syscalls import NR, TRAPPED_SYSCALLS

#: The calls the supervisor stops that name a path but are not answered from the table: what a
#: process becomes is the exec bridge's to settle, and a socket's address is not a path here.
NOT_TABLED = {NR.EXECVE, NR.EXECVEAT, NR.CONNECT}


def test_every_call_that_is_stopped_has_a_handler() -> None:
    dispatcher = SyscallDispatcher(cast("Any", None))
    assert {number for number in dispatcher._table if number >= 0} == TRAPPED_SYSCALLS


def test_every_call_that_is_stopped_says_where_its_paths_are() -> None:
    """So that a spelling of the mirror only the target has is settled for every one of them."""
    tabled = {number for number in _REDIRECTABLE if number >= 0}
    assert tabled == TRAPPED_SYSCALLS - NOT_TABLED


@pytest.mark.parametrize(
    "name",
    [
        "STATFS", "INOTIFY_ADD_WATCH", "FANOTIFY_MARK", "GETXATTR", "LGETXATTR",
        "LISTXATTR", "LLISTXATTR", "SETXATTR", "LSETXATTR", "REMOVEXATTR", "LREMOVEXATTR",
        "NAME_TO_HANDLE_AT", "OPEN_TREE", "STATX", "NEWFSTATAT", "UTIMENSAT", "FUTIMESAT",
        "UTIME", "UTIMES", "READLINK", "READLINKAT", "CHDIR", "FCHOWNAT", "CHOWN", "LCHOWN",
        "MKNOD", "MKNODAT", "FCHMODAT2", "EXECVE", "EXECVEAT",
    ],
)  # fmt: skip
def test_a_call_that_names_a_path_is_stopped_where_this_machine_has_it(
    name: str,
) -> None:
    number = getattr(NR, name)
    assert number < 0 or number in TRAPPED_SYSCALLS


@pytest.mark.parametrize(
    ("name", "where"),
    [
        # The watch's descriptor first, then a path resolved against the process's directory.
        ("INOTIFY_ADD_WATCH", ((None, 1),)),
        # The group's descriptor, its flags and its mask, and then a directory and a path.
        ("FANOTIFY_MARK", ((3, 4),)),
        ("STATFS", ((None, 0),)),
        ("GETXATTR", ((None, 0),)),
        ("NAME_TO_HANDLE_AT", ((0, 1),)),
        ("FCHOWNAT", ((0, 1),)),
        ("FUTIMESAT", ((0, 1),)),
    ],
)
def test_a_call_s_path_is_read_from_the_argument_its_manual_page_puts_it_in(
    name: str, where: tuple[tuple[int | None, int], ...]
) -> None:
    number = getattr(NR, name)
    if number < 0:
        pytest.skip(f"{name.lower()} is not a call this architecture has")
    assert _REDIRECTABLE[number] == where

"""Reading a process's memory, descriptors and `/proc` links, with this process as the tracee.

A process may read and write its own memory and look up its own descriptors without tracing
anything, which is all the bindings need to be seen working. Linux only: collected there and
nowhere else (see `conftest.py`).
"""

from __future__ import annotations

import ctypes
import errno
import os
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.linux.procfs import (
    MAX_ARG_STRLEN,
    PATH_MAX,
    Peek,
    TraceeGoneError,
    UnresolvedPathError,
    fd_target,
    parent_of,
    read_bytes,
    read_cstring,
    read_string_array,
    resolve_magic,
    steal_fd,
    working_directory,
    write_bytes,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

ME = os.getpid()
#: A pid no process has: above every `pid_max` a kernel allows.
NOBODY = 0x7FFF_FFF0


def at(buffer: ctypes.Array[ctypes.c_char]) -> int:
    return ctypes.addressof(buffer)


def test_the_ceilings() -> None:
    assert PATH_MAX == 4096
    assert 32 * os.sysconf("SC_PAGESIZE") == MAX_ARG_STRLEN


def test_bytes_written_are_the_bytes_read() -> None:
    buffer = ctypes.create_string_buffer(16)

    assert write_bytes(ME, at(buffer), b"hello") == 5
    assert read_bytes(ME, at(buffer), 5) == b"hello"
    assert buffer.raw[:5] == b"hello"


def test_nothing_is_read_or_written_for_nothing() -> None:
    assert read_bytes(ME, 0, 0) == b""
    assert read_bytes(ME, 0, -1) == b""
    assert write_bytes(ME, 0, b"") == 0


def test_a_process_that_is_gone_is_said_to_be() -> None:
    buffer = ctypes.create_string_buffer(8)

    with pytest.raises(TraceeGoneError) as gone:
        read_bytes(NOBODY, at(buffer), 8)
    assert gone.value.errno == errno.ESRCH
    with pytest.raises(OSError, match="process_vm_writev"):
        write_bytes(NOBODY, at(buffer), b"x")


def test_read_cstring_stops_at_the_terminator() -> None:
    buffer = ctypes.create_string_buffer(b"hello\0world")

    assert read_cstring(ME, at(buffer)) == "hello"
    assert read_cstring(ME, at(buffer), limit=3) == "hel"
    assert read_cstring(ME, 0) is None


def test_read_cstring_reads_across_pages() -> None:
    long = b"x" * (3 * os.sysconf("SC_PAGESIZE"))
    buffer = ctypes.create_string_buffer(long)

    assert read_cstring(ME, at(buffer), limit=len(long) + 1) == long.decode()


def test_read_cstring_keeps_bytes_that_are_not_utf8() -> None:
    buffer = ctypes.create_string_buffer(b"caf\xe9")

    said = read_cstring(ME, at(buffer))

    assert said is not None
    assert os.fsencode(said) == b"caf\xe9"


def test_peek_reads_the_bytes_before_the_terminator() -> None:
    first = ctypes.create_string_buffer(b"/a/long/path\0tail")
    second = ctypes.create_string_buffer(b"/b")
    peek = Peek()

    assert peek.cstring(ME, at(first)) == b"/a/long/path"
    assert peek.cstring(ME, at(second)) == b"/b"
    assert peek.cstring(ME, 0) is None


def test_peek_reads_no_more_than_its_window() -> None:
    buffer = ctypes.create_string_buffer(b"abcdefgh")

    assert Peek(size=3).cstring(ME, at(buffer)) == b"abc"


def test_read_string_array_reads_up_to_the_null_pointer() -> None:
    strings = [ctypes.create_string_buffer(one) for one in (b"prog", b"", b"--flag")]
    array = (ctypes.c_void_p * 4)(*(at(one) for one in strings), None)
    where = ctypes.addressof(array)

    assert read_string_array(ME, where) == ["prog", "", "--flag"]
    assert read_string_array(ME, where, limit=2) == ["prog", ""]
    assert read_string_array(ME, 0) == []


def test_the_working_directory_is_the_kernels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert working_directory(ME) == str(tmp_path.resolve())


@pytest.fixture
def directory(tmp_path: Path) -> Iterator[int]:
    """A descriptor open on a directory of the test's own."""
    held = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        yield held
    finally:
        os.close(held)


def test_fd_target_is_what_a_descriptor_is_open_on(
    tmp_path: Path, directory: int
) -> None:
    assert fd_target(ME, directory) == str(tmp_path.resolve())


def test_fd_target_of_a_closed_descriptor_is_gone() -> None:
    held = os.open(os.devnull, os.O_RDONLY)
    os.close(held)

    with pytest.raises(TraceeGoneError):
        fd_target(ME, held)


def test_parent_of() -> None:
    assert parent_of(ME) == os.getppid()
    assert parent_of(NOBODY) == 0


@pytest.mark.parametrize(
    ("path", "resolved"),
    [
        ("/srv/./plain//path/", "/srv/./plain//path/"),
        ("/home/me/proc/self/fd/3", "/home/me/proc/self/fd/3"),
        ("/proc/self/stat", "/proc/self/stat"),
        ("/proc/sys/./kernel//x", "/proc/sys/kernel/x"),
        ("/proc/self/fd", "/proc/self/fd"),
    ],
)
def test_a_path_with_no_link_in_it_names_what_it_did(path: str, resolved: str) -> None:
    assert resolve_magic(ME, path) == resolved


def test_two_leading_separators_are_one() -> None:
    assert resolve_magic(ME, "//srv/project/x") == "/srv/project/x"


@pytest.mark.parametrize(
    "spelling",
    [
        "/proc/self/fd/{fd}/name",
        "/proc/thread-self/fd/{fd}/name",
        "/proc/{pid}/fd/{fd}/name",
        "/proc/{pid}/task/{pid}/fd/{fd}/name",
        "/proc/self/fd/{fd}/./sub/../name",
    ],
)
def test_a_descriptors_link_is_followed(
    tmp_path: Path, directory: int, spelling: str
) -> None:
    path = spelling.format(fd=directory, pid=ME)

    assert resolve_magic(ME, path) == str(tmp_path.resolve() / "name")


def test_dot_dot_is_taken_after_the_link_is_followed(
    tmp_path: Path, directory: int
) -> None:
    resolved = resolve_magic(ME, f"/proc/self/fd/{directory}/../beside")

    assert resolved == str(tmp_path.resolve().parent / "beside")


def test_the_working_directory_link_is_followed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert resolve_magic(ME, "/proc/self/cwd/a") == str(tmp_path.resolve() / "a")


def test_a_link_to_what_is_not_a_file_leaves_the_path_alone() -> None:
    read, write = os.pipe()
    try:
        path = f"/proc/self/fd/{read}"
        assert resolve_magic(ME, path) == path
    finally:
        os.close(read)
        os.close(write)


def test_a_link_to_an_unlinked_file_leaves_the_path_alone(tmp_path: Path) -> None:
    doomed = tmp_path / "doomed"
    doomed.write_text("")
    held = os.open(doomed, os.O_RDONLY)
    try:
        doomed.unlink()
        path = f"/proc/self/fd/{held}"
        assert resolve_magic(ME, path) == path
    finally:
        os.close(held)


def test_a_descriptor_that_is_not_there_is_unresolved() -> None:
    held = os.open(os.devnull, os.O_RDONLY)
    os.close(held)

    with pytest.raises(UnresolvedPathError) as unresolved:
        resolve_magic(ME, f"/proc/self/fd/{held}/x")
    assert unresolved.value.errno == errno.ENOENT


def test_self_of_a_tracee_that_is_gone_is_unresolved() -> None:
    with pytest.raises(UnresolvedPathError):
        resolve_magic(NOBODY, "/proc/self/fd/0")


def test_both_errors_are_os_errors() -> None:
    assert issubclass(TraceeGoneError, OSError)
    assert issubclass(UnresolvedPathError, OSError)


def test_steal_fd_hands_over_the_same_file(tmp_path: Path) -> None:
    file = tmp_path / "file"
    file.write_text("x")
    held = os.open(file, os.O_WRONLY)
    try:
        stolen = steal_fd(ME, held)
        try:
            assert stolen != held
            assert os.fstat(stolen).st_ino == os.fstat(held).st_ino
        finally:
            os.close(stolen)
    finally:
        os.close(held)


def test_steal_fd_of_a_process_that_is_gone_fails() -> None:
    with pytest.raises(OSError):  # noqa: PT011 -- whichever way failed last
        steal_fd(NOBODY, 1)

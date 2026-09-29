"""The masks a Landlock ruleset is built from, and the rulesets it refuses to build.

Everything that reaches the kernel is `tests/system/coganchor/test_landlock.py`. What is here
is what is decided before a syscall is made: which rights an ABI version can govern, which of
them a read or a write grant carries, what a file can take that a directory can, and the
requests that are turned away with nothing restricted -- which is every test below that calls
`restrict_self`, on this process, and is safe to only because it raises first.
"""

from __future__ import annotations

import pytest

from hmz.coganchor.linux import landlock

EXECUTE, WRITE_FILE, READ_FILE, READ_DIR = 1 << 0, 1 << 1, 1 << 2, 1 << 3
REFER, TRUNCATE, IOCTL_DEV = 1 << 13, 1 << 14, 1 << 15


@pytest.mark.parametrize(
    ("version", "mask"),
    [
        (0, 0),
        (1, (1 << 13) - 1),
        (2, (1 << 14) - 1),
        (3, (1 << 15) - 1),
        (4, (1 << 15) - 1),
        (5, (1 << 16) - 1),
        (6, (1 << 16) - 1),
    ],
)
def test_each_abi_handles_the_filesystem_rights_it_was_given(
    version: int, mask: int
) -> None:
    assert landlock.handled_fs(version) == mask


def test_reading_is_opening_listing_and_running() -> None:
    rights = landlock.fs_rights(5, write=False, directory=True)

    assert rights == EXECUTE | READ_FILE | READ_DIR


def test_writing_is_every_right_the_abi_has() -> None:
    for version in range(1, 7):
        rights = landlock.fs_rights(version, write=True, directory=True)
        assert rights == landlock.handled_fs(version)


def test_a_file_takes_only_the_rights_of_a_file() -> None:
    assert landlock.fs_rights(5, write=False, directory=False) == EXECUTE | READ_FILE
    assert landlock.fs_rights(5, write=True, directory=False) == (
        EXECUTE | WRITE_FILE | READ_FILE | TRUNCATE | IOCTL_DEV
    )
    assert landlock.fs_rights(1, write=True, directory=False) == (
        EXECUTE | WRITE_FILE | READ_FILE
    )


def test_an_older_abi_drops_the_filesystem_rights_it_does_not_know() -> None:
    rights = landlock.fs_rights(1, write=True, directory=True)

    assert not rights & (REFER | TRUNCATE | IOCTL_DEV)


def test_there_is_no_landlock_off_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(landlock.sys, "platform", "darwin")

    assert landlock.abi.__wrapped__() == 0


@pytest.mark.parametrize(
    ("version", "net", "expected"),
    [(0, False, False), (1, False, True), (3, True, False), (4, True, True)],
)
def test_available_asks_for_the_abi_the_ruleset_needs(
    monkeypatch: pytest.MonkeyPatch, version: int, net: bool, expected: bool
) -> None:
    monkeypatch.setattr(landlock, "abi", lambda: version)

    assert landlock.available(net=net) is expected


def test_a_ruleset_asked_to_govern_tcp_is_refused_where_the_kernel_cannot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never a filesystem-only ruleset in its place: that would leave the network open."""
    monkeypatch.setattr(landlock, "abi", lambda: 3)

    with pytest.raises(RuntimeError, match="ABI 4"):
        landlock.Ruleset(read=["/"], connect_ports=[443], net=True).restrict_self()


def test_a_kernel_without_landlock_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(landlock, "abi", lambda: 0)

    with pytest.raises(RuntimeError, match="needs Landlock"):
        landlock.Ruleset(read=["/"]).restrict_self()


def test_ports_without_governing_tcp_are_a_mistake() -> None:
    with pytest.raises(ValueError, match="does not govern TCP"):
        landlock.Ruleset(connect_ports=[443]).restrict_self()


def test_a_port_out_of_range_is_refused() -> None:
    with pytest.raises(ValueError, match="out of range"):
        landlock.Ruleset(bind_ports=[70000], net=True).restrict_self()

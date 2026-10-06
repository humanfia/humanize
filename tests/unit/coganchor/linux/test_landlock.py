"""The Landlock rights a path is granted, and the rulesets refused before anything is restricted.

Run on every host: the module is importable anywhere. Nothing here restricts this process --
every ruleset built is one refused before the kernel is asked to apply it.
"""

from __future__ import annotations

import sys

import pytest

from hmz.coganchor.linux import landlock
from hmz.coganchor.linux.landlock import Ruleset, abi, available, fs_rights, handled_fs

# `LANDLOCK_ACCESS_FS_*`, from <linux/landlock.h>.
EXECUTE = 1 << 0
WRITE_FILE = 1 << 1
READ_FILE = 1 << 2
READ_DIR = 1 << 3
REFER = 1 << 13
TRUNCATE = 1 << 14
IOCTL_DEV = 1 << 15
ABI1 = (1 << 13) - 1


@pytest.mark.parametrize(
    ("version", "mask"),
    [
        (0, 0),
        (1, ABI1),
        (2, ABI1 | REFER),
        (3, ABI1 | REFER | TRUNCATE),
        (4, ABI1 | REFER | TRUNCATE),
        (5, ABI1 | REFER | TRUNCATE | IOCTL_DEV),
        (6, ABI1 | REFER | TRUNCATE | IOCTL_DEV),
    ],
)
def test_handled_fs_grows_with_the_abi(version: int, mask: int) -> None:
    assert handled_fs(version) == mask


@pytest.mark.parametrize("version", range(1, 7))
def test_reading_is_opening_listing_and_running(version: int) -> None:
    assert (
        fs_rights(version, write=False, directory=True)
        == EXECUTE | READ_FILE | READ_DIR
    )
    assert fs_rights(version, write=False, directory=False) == EXECUTE | READ_FILE


@pytest.mark.parametrize("version", range(1, 7))
def test_writing_a_directory_is_every_right_the_abi_has(version: int) -> None:
    assert fs_rights(version, write=True, directory=True) == handled_fs(version)


@pytest.mark.parametrize("version", range(1, 7))
def test_a_file_takes_only_the_rights_of_a_file(version: int) -> None:
    rights = fs_rights(version, write=True, directory=False)

    assert rights == handled_fs(version) & (
        EXECUTE | WRITE_FILE | READ_FILE | TRUNCATE | IOCTL_DEV
    )
    assert not rights & READ_DIR


def test_no_abi_grants_nothing() -> None:
    assert fs_rights(0, write=True, directory=True) == 0


@pytest.mark.skipif(sys.platform == "linux", reason="Linux may have Landlock")
def test_no_host_but_linux_has_landlock() -> None:
    assert abi() == 0
    assert not available()
    assert not available(net=True)


@pytest.mark.parametrize(
    ("version", "files", "tcp"),
    [
        (0, False, False),
        (1, True, False),
        (3, True, False),
        (4, True, True),
        (6, True, True),
    ],
)
def test_available_is_the_abi_each_part_needs(
    monkeypatch: pytest.MonkeyPatch, version: int, files: bool, tcp: bool
) -> None:
    monkeypatch.setattr(landlock, "abi", lambda: version)

    assert available() is files
    assert available(net=True) is tcp


@pytest.mark.parametrize(
    ("ruleset", "match"),
    [
        (Ruleset(connect_ports=(443,)), "does not govern TCP"),
        (Ruleset(bind_ports=(0,)), "does not govern TCP"),
        (Ruleset(connect_ports=(65536,), net=True), "out of range"),
        (Ruleset(bind_ports=(-1,), net=True), "out of range"),
    ],
)
def test_restrict_self_refuses_ports_it_cannot_govern(
    monkeypatch: pytest.MonkeyPatch, ruleset: Ruleset, match: str
) -> None:
    monkeypatch.setattr(landlock, "abi", lambda: 0)

    with pytest.raises(ValueError, match=match):
        ruleset.restrict_self()


@pytest.mark.parametrize(
    ("version", "net", "match"),
    [(0, False, "needs Landlock"), (0, True, "ABI 4"), (3, True, "ABI 4")],
)
def test_restrict_self_refuses_a_kernel_too_old(
    monkeypatch: pytest.MonkeyPatch, version: int, net: bool, match: str
) -> None:
    monkeypatch.setattr(landlock, "abi", lambda: version)

    with pytest.raises(RuntimeError, match=match):
        Ruleset(read=("/usr",), net=net).restrict_self()

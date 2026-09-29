"""Landlock and the socket filter, enforced by this kernel on a child that asks for them.

Both confine the process that installs them for the rest of its life, so none of it is done
here: each test starts a Python child, which imports what it will need, restricts itself as
told and then tries things, reporting the errno each attempt came to. A system test rather
than an integration one because the other side is the real kernel's Landlock and seccomp, which
`tests/tiers.py` puts in this tree; a kernel too old for what a test needs skips it aloud.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.supervising import WITHOUT_BINDINGS

if WITHOUT_BINDINGS:
    pytest.skip(WITHOUT_BINDINGS, allow_module_level=True)

from hmz.coganchor.linux import landlock

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.skipif(
    not landlock.available(), reason="this kernel has no Landlock"
)
networked = pytest.mark.skipif(
    not landlock.available(net=True),
    reason=f"this kernel speaks Landlock ABI {landlock.abi()}; TCP rules need 4",
)

#: What every child may read: the interpreter, its libraries, and a shell to run.
SYSTEM = ["/usr", "/bin", "/lib", "/lib64", "/etc", sys.prefix, sys.base_prefix]

#: The child. It is handed a ruleset, whether to install the socket filter, and a list of
#: attempts, and prints the errno each came to -- 0 for one that worked.
CHILD = r"""
import errno, json, os, socket, subprocess, sys
from hmz.coganchor.linux import landlock, seccomp

spec = json.loads(sys.argv[1])
if spec["ruleset"] is not None:
    landlock.Ruleset(**spec["ruleset"]).restrict_self()
if spec["sockets"]:
    seccomp.install_socket_filter()

def attempt(kind, *args):
    try:
        if kind == "write":
            with open(args[0], "w") as handle:
                handle.write("x")
        elif kind == "read":
            with open(args[0]) as handle:
                handle.read()
        elif kind == "list":
            os.listdir(args[0])
        elif kind == "exec":
            return subprocess.run(args, check=False).returncode
        elif kind == "connect":
            with socket.create_connection(("127.0.0.1", args[0]), timeout=5):
                pass
        elif kind == "socket":
            socket.socket(args[0], args[1]).close()
    except OSError as why:
        return why.errno
    return 0

print(json.dumps([attempt(*each) for each in spec["attempts"]]))
"""


def confined(
    attempts: list[list[object]],
    *,
    ruleset: dict[str, object] | None = None,
    sockets: bool = False,
) -> list[int]:
    """Run the attempts in a child restricted as told.

    Args:
      attempts: Each a kind and its arguments, as `CHILD` spells them.
      ruleset: The keyword arguments of a `landlock.Ruleset`, or None for none.
      sockets: Whether to install the socket filter too.

    Returns:
      The errno of each attempt, in order, and 0 for one that worked.
    """
    spec = {"ruleset": ruleset, "sockets": sockets, "attempts": attempts}
    done = subprocess.run(
        [sys.executable, "-c", CHILD, json.dumps(spec)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture
def rooms(tmp_path: Path) -> tuple[Path, Path]:
    """A directory the child may write, and one it is given nothing in."""
    granted, other = tmp_path / "granted", tmp_path / "other"
    granted.mkdir()
    other.mkdir()
    (other / "secret").write_text("not for the child")
    return granted, other


@pytest.fixture
def listeners() -> Iterator[tuple[int, int]]:
    """Two loopback listeners: the port the child may connect to, and one it may not."""
    opened = [socket.create_server(("127.0.0.1", 0)) for _ in range(2)]
    try:
        yield opened[0].getsockname()[1], opened[1].getsockname()[1]
    finally:
        for each in opened:
            each.close()


def test_a_write_outside_the_granted_paths_is_refused(
    rooms: tuple[Path, Path],
) -> None:
    granted, other = rooms

    results = confined(
        [["write", str(other / "new")], ["write", str(other / "secret")]],
        ruleset={"read": SYSTEM, "write": [str(granted)]},
    )

    assert results == [13, 13]
    assert not (other / "new").exists()


def test_a_read_outside_the_granted_paths_is_refused(
    rooms: tuple[Path, Path],
) -> None:
    granted, other = rooms

    results = confined(
        [["read", str(other / "secret")], ["list", str(other)]],
        ruleset={"read": SYSTEM, "write": [str(granted)]},
    )

    assert results == [13, 13]


def test_a_write_inside_the_granted_paths_works(rooms: tuple[Path, Path]) -> None:
    granted, _ = rooms

    results = confined(
        [["write", str(granted / "new")], ["read", str(granted / "new")]],
        ruleset={"read": SYSTEM, "write": [str(granted)]},
    )

    assert results == [0, 0]
    assert (granted / "new").read_text() == "x"


def test_a_path_granted_only_for_reading_cannot_be_written(
    rooms: tuple[Path, Path],
) -> None:
    _, other = rooms

    results = confined(
        [["read", str(other / "secret")], ["write", str(other / "secret")]],
        ruleset={"read": [*SYSTEM, str(other)]},
    )

    assert results == [0, 13]


def test_a_single_file_can_be_granted_and_a_missing_path_is_skipped(
    rooms: tuple[Path, Path],
) -> None:
    """A file takes only a file's rights, which the kernel would otherwise refuse."""
    granted, other = rooms

    results = confined(
        [["write", str(other / "secret")], ["read", str(other / "secret")]],
        ruleset={
            "read": [*SYSTEM, str(granted / "never-made")],
            "write": [str(other / "secret")],
        },
    )

    assert results == [0, 0]


def test_a_program_under_a_read_root_can_be_run(rooms: tuple[Path, Path]) -> None:
    granted, other = rooms
    script = other / "run.sh"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)

    results = confined(
        [["exec", "/bin/sh", "-c", "exit 7"], ["exec", str(script)]],
        ruleset={"read": SYSTEM, "write": [str(granted)]},
    )

    assert results == [7, 13]


@networked
def test_tcp_reaches_only_the_granted_port(
    rooms: tuple[Path, Path], listeners: tuple[int, int]
) -> None:
    granted, _ = rooms
    allowed, refused = listeners

    results = confined(
        [["connect", allowed], ["connect", refused]],
        ruleset={
            "read": SYSTEM,
            "write": [str(granted)],
            "connect_ports": [allowed],
            "net": True,
        },
    )

    assert results == [0, 13]


def test_a_udp_or_raw_socket_is_refused_and_tcp_is_not() -> None:
    results = confined(
        [
            ["socket", socket.AF_INET, socket.SOCK_DGRAM],
            ["socket", socket.AF_INET6, socket.SOCK_DGRAM],
            ["socket", socket.AF_INET, socket.SOCK_RAW],
            ["socket", socket.AF_INET, socket.SOCK_STREAM],
            ["socket", socket.AF_UNIX, socket.SOCK_DGRAM],
        ],
        sockets=True,
    )

    assert results == [13, 13, 13, 0, 0]


@networked
def test_the_two_together_leave_only_the_granted_tcp_port(
    rooms: tuple[Path, Path], listeners: tuple[int, int]
) -> None:
    granted, other = rooms
    allowed, refused = listeners

    results = confined(
        [
            ["connect", allowed],
            ["connect", refused],
            ["socket", socket.AF_INET, socket.SOCK_DGRAM],
            ["write", str(other / "new")],
            ["write", str(granted / "new")],
        ],
        ruleset={
            "read": SYSTEM,
            "write": [str(granted)],
            "connect_ports": [allowed],
            "net": True,
        },
        sockets=True,
    )

    assert results == [0, 13, 13, 13, 0]


def test_the_landlock_numbers_are_the_kernel_s_own() -> None:
    """Written down once for every architecture, so read back from the generic table."""
    try:
        text = Path("/usr/include/linux/landlock.h").read_text(encoding="utf-8")
        table = Path("/usr/include/asm-generic/unistd.h").read_text(encoding="utf-8")
    except OSError:
        pytest.skip("the kernel headers are not installed here")
    numbers = dict(re.findall(r"#define __NR_(landlock_\w+) (\d+)", table))
    rights = dict(
        re.findall(r"#define LANDLOCK_ACCESS_(\w+)\s+\(1ULL << (\d+)\)", text)
    )

    assert int(numbers["landlock_create_ruleset"]) == landlock._NR_CREATE_RULESET
    assert int(numbers["landlock_add_rule"]) == landlock._NR_ADD_RULE
    assert int(numbers["landlock_restrict_self"]) == landlock._NR_RESTRICT_SELF
    assert int(rights["FS_REFER"]) == 13
    assert int(rights["FS_TRUNCATE"]) == 14
    assert int(rights["NET_CONNECT_TCP"]) == 1

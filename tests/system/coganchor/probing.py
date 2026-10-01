"""Running `_spellings_probe.py` and reading what it says, for every suite that hands it a path.

Not a test module. The probe names one directory with every syscall that names a path, and is
run by two suites: `test_spellings.py`, where the directory is the mirror named the way only the
target names it, and `tests/system/providers/test_redirect_calls.py`, where it is a CLI's
credentials, answered with a provider's. What each needs to say what was there and to read the
answer back is here, once.

Imports the syscall table, so it is imported only by a module that has asked
`tests.supervising.WITHOUT_BINDINGS` first.
"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

from hmz.coganchor.linux.syscalls import NR

__all__ = ["CALLS", "NUMBERS", "PROBE", "check", "said", "seed"]

#: The program, handed to `python3 -c`.
PROBE = (Path(__file__).parent / "_spellings_probe.py").read_text()

#: This machine's number for every call the probe makes, by the name it is printed under.
NUMBERS = json.dumps(
    {field.name.lower(): getattr(NR, field.name) for field in fields(NR)}
)

#: Every call this architecture has that the probe makes, each of which has to come back `ok`.
CALLS = sorted(
    name
    for name in (
        "stat", "lstat", "newfstatat", "statx", "access", "faccessat", "faccessat2",
        "statfs", "getxattr", "lgetxattr", "listxattr", "llistxattr", "setxattr",
        "lsetxattr", "removexattr", "lremovexattr", "name_to_handle_at", "open_tree",
        "chown", "lchown", "fchownat", "chmod", "fchmodat", "fchmodat2", "utime", "utimes",
        "futimesat", "utimensat", "mknod", "mknodat", "readlink", "readlinkat",
        "inotify_add_watch", "chdir",
    )
    if name == "chdir" or getattr(NR, name.upper()) >= 0
)  # fmt: skip


def seed(directory: Path) -> None:
    """What the probe expects: a file, a link to it, and a program for each machine to run."""
    (directory / "seed.txt").write_text("seeded\n")
    (directory / "link").symlink_to("seed.txt")
    here = directory / "tool.sh"
    # Builtins only, and a redirect, which the shell opens itself: a program run here that
    # started another would have that one run on the target.
    here.write_text("#!/bin/sh\nread name < /etc/hostname\necho TOOL-RAN-ON-$name\n")
    there = directory / "remote.sh"
    there.write_text("#!/bin/sh\necho REMOTE-RAN-ON-$(cat /etc/hostname)\n")
    here.chmod(0o755)
    there.chmod(0o755)


def said(output: str) -> dict[str, str]:
    """The probe's lines, by the call each one is about."""
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


def check(output: str, here: str | None = None, there: str | None = None) -> None:
    """Every call reached the file, and each program ran on the machine it belongs to.

    Args:
      output: What the probe printed.
      here: The host a program run from the directory here has to say it ran on, or None
        for a probe told `--no-programs`.
      there: The same, for one run on the target.
    """
    heard = said(output)
    assert {name: heard.get(name) for name in CALLS} == dict.fromkeys(CALLS, "ok"), (
        output
    )
    assert heard.get("fanotify_mark", "").startswith(("ok", "unavailable")), output
    if here is not None:
        assert heard.get("execve-here") == f"TOOL-RAN-ON-{here}", output
    if there is not None:
        assert heard.get("execve-there") == f"REMOTE-RAN-ON-{there}", output

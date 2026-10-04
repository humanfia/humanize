"""humanize: flows of coding agents, and the runs of them."""

from __future__ import annotations

import contextlib
import os
import pathlib
import stat
import tempfile

__all__ = ["home", "machine"]


def home() -> pathlib.Path:
    """Where humanize keeps what outlives one run of one flow.

    Under your home directory, unless `HUMANIZE_HOME` says otherwise -- which is what a test
    says, and what a machine holding more than one of these would.

    Returns:
      The directory. It is not made here: it is made by whatever writes into it.
    """
    return pathlib.Path(
        os.environ.get("HUMANIZE_HOME") or pathlib.Path.home() / ".humanize"
    )


def machine() -> pathlib.Path:
    """Where humanize keeps what is this machine's alone, made private where it is not yet.

    A home directory is shared by every machine that mounts it, and what is this machine's --
    a process running here, an archive built here -- is nothing another machine can use: one
    reading it would find a pid of somebody else's kernel, and take it for a run of its own
    or a stale one. The temporary directory is the machine's, and one directory in it per
    user, named for the user, is nobody else's. Not `XDG_RUNTIME_DIR`, which is the login
    session's: it goes when the last session does, and what is kept here outlives the
    terminal that started it.

    Returns:
      The directory.

    Raises:
      PermissionError: If what is there under its name is not a directory of this user's
        that nobody else can write. In a temporary directory everybody shares, that is
        somebody else's way of handing this user a file to trust as their own.
    """
    mine = pathlib.Path(tempfile.gettempdir()) / f"humanize-{os.getuid()}"
    with contextlib.suppress(FileExistsError):
        mine.mkdir(mode=0o700)
    found = mine.lstat()
    if (
        not stat.S_ISDIR(found.st_mode)
        or found.st_uid != os.getuid()
        or found.st_mode & 0o022
    ):
        raise PermissionError(
            f"{mine} is not a directory only this user can write; remove it"
        )
    return mine

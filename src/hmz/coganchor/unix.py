"""Where a Unix socket goes, so that its path is short enough to be bound.

A socket is bound and reached by a path of 104 bytes on macOS and 108 on Linux, each counting
the NUL that ends it. A Mac's temporary directory spends 49 of them and a fenced process's more,
so a socket under one that does not fit goes under `/tmp` instead, short on every Unix.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

__all__ = ["LONGEST", "reached", "sockets"]

#: The longest path a Unix socket is bound or reached by, in bytes: macOS's, the shorter, so
#: that a Humanize which works on one works on the other.
LONGEST = 103

#: Where a socket goes whose directory would be too long a way to it.
_SHORT = "/tmp"  # noqa: S108 -- what is made under it is checked to be this user's alone


def sockets(room: int, under: str = "") -> Path:
    """Where a directory holding a Unix socket goes, so that the socket's path fits.

    Args:
      room: How many bytes the socket's path spends after the directory, its separator
        included.
      under: The directory to prefer to the temporary directory, where there is one.

    Returns:
      `under` or the temporary directory where the socket fits under it, and `/tmp`
      otherwise -- or the first again where `/tmp` is not this user's to write in either, so
      that what goes wrong is what would have gone wrong without this.
    """
    at = under or tempfile.gettempdir()
    if len(at.encode()) + room <= LONGEST or not os.access(_SHORT, os.W_OK | os.X_OK):
        return Path(at)
    return Path(_SHORT)


@contextlib.contextmanager
def reached(path: str | os.PathLike[str]) -> Generator[str]:
    """A socket whose place is fixed, spelled short enough to be bound or connected.

    A socket that must be where it is, however long the way there, is reached through a link
    to its directory, made in a directory of this user's alone under `/tmp` and removed once
    the socket has been reached. Nothing of the process is changed, so this is safe in one of
    many threads, which standing in the socket's directory is not.

    Args:
      path: The socket, whole.

    Yields:
      The socket, as it is to be bound or connected: `path` where that fits, or where `/tmp`
      is not this user's to write in, and a shorter way to the same file otherwise.

    Raises:
      OSError: If the directory or the link cannot be made.
    """
    whole = Path(path).absolute()
    if len(os.fsencode(whole)) <= LONGEST or not os.access(_SHORT, os.W_OK | os.X_OK):
        yield str(whole)
        return
    held = Path(tempfile.mkdtemp(prefix="hmz-", dir=_SHORT))
    try:
        (held / "at").symlink_to(whole.parent)
        yield str(held / "at" / whole.name)
    finally:
        shutil.rmtree(held, ignore_errors=True)

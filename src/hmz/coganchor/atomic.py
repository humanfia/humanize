"""Writing a file whole: beside it under a name of its own, then moved over it.

Every file coganchor keeps is read by whoever opens it next, and two `hmz` at once -- a menu
saving while a script runs, two interfaces on one home -- both write the same ones. So each is
written beside itself and moved into place, which makes a reader find the old one or the new
one and never half of each; and beside it under a name nothing else will pick, because two
writers of one fixed `.new` are one of them finding its own file already moved away.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import stat
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

__all__ = ["writes"]


def writes(
    at: Path, said: str | bytes | Iterable[bytes], *, mode: int | None = None
) -> None:
    """Replaces a file with what is given, whole, and on disk before it is moved into place.

    Args:
      at: The file. The directory it is in must already be there.
      said: What it is to hold: text, written as UTF-8, bytes, or bytes a piece at a time
        for a file too big to be worth holding whole first.
      mode: The permissions it is to have. None keeps the ones it has, and gives one that
        is not there yet what the umask leaves of `0666`, as opening it would have. A mode
        is set on the file before anything is written into it, so that a key kept `0600` is
        never readable by anybody else, not even for a moment.

    Raises:
      OSError: If it cannot be written, with nothing of the attempt left beside it.
    """
    keeps = mode
    if keeps is None:
        with contextlib.suppress(FileNotFoundError):
            keeps = stat.S_IMODE(at.stat().st_mode)
    beside, handle = _opened(at, 0o666 if keeps is None else 0o600)
    try:
        with os.fdopen(handle, "wb") as writing:
            if keeps is not None:
                os.fchmod(handle, keeps)  # exactly, which is more than the umask allows
            if isinstance(said, str):
                writing.write(said.encode("utf-8"))
            elif isinstance(said, bytes):
                writing.write(said)
            else:
                writing.writelines(said)
            writing.flush()
            os.fsync(handle)
        beside.replace(at)
    except BaseException:
        beside.unlink(missing_ok=True)
        raise


def _opened(at: Path, mode: int) -> tuple[Path, int]:
    """Makes a file beside another under a name nothing else has, and opens it to write.

    Made rather than `mkstemp`'d because `mkstemp` is always `0600`, and a file with no mode
    of its own to keep is to get what the umask says -- which the kernel applies here, and
    which cannot be asked for without setting it for every thread of the process.

    Args:
      at: The file it is to replace.
      mode: What it is made with, before the umask.

    Returns:
      Where it is, and a descriptor open on it for writing.
    """
    while True:
        beside = at.with_name(f".{at.name}.{secrets.token_hex(8)}.new")
        try:
            return beside, os.open(
                beside, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, mode
            )
        except FileExistsError:
            continue

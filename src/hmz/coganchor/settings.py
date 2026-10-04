"""humanize's one settings file: everything `/settings` can set, in `settings.yaml`.

One file under humanize's own home, keyed by what each part of it is: what each workspace was
set up to run, the handful of settings that are this machine's, the chains a failed turn falls
back along (`fallbacks`), the CLIs somebody added by hand (`clis`) and the machines an
environment may be put on (`runtimes`). One file rather than one per setting, because a person
reading what humanize was told is reading one thing, and a file per part was a directory of
them to find it in -- and because whoever writes one part has to leave every other part as it
was, which is one lock and one file to keep it on.

Here rather than above, because the parts `coganchor` keeps are written by `coganchor`: the
interface and a command line write the workspaces through :mod:`hmz.runtime.settings`, which
writes through this.
"""

from __future__ import annotations

import contextlib
import os
import time
from typing import TYPE_CHECKING, Any, cast

import yaml

from hmz import home
from hmz.coganchor import atomic

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

__all__ = ["changes", "read", "reading", "where"]

#: How long, in seconds, a write waits for another writer to be done before going ahead
#: without it. A write takes milliseconds, and seconds on a disk busy enough that fsync
#: queues; this is for a writer that has stopped, not for one that is slow.
_PATIENCE = 30.0


def where() -> Path:
    """The file, whether or not anything has been written to it."""
    return home() / "settings.yaml"


def reading() -> dict[str, Any] | None:
    """Everything the file holds, and None where there is one that cannot be read as one.

    Told apart from a file that is not there, which holds nothing, because a write makes
    its change to what the file holds: one somebody left half-edited is not a reason to
    write it back as nothing but that change.
    """
    try:
        said = where().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError:
        return None
    try:
        held = yaml.safe_load(said)
    except yaml.YAMLError:
        return None
    if held is None:
        return {}
    return cast("dict[str, Any]", held) if isinstance(held, dict) else None


def read() -> dict[str, Any]:
    """Everything the file holds, which is nothing at all when it cannot be read.

    A settings file that is missing, unreadable, or not what this writes is a machine with
    nothing set -- never a reason not to start.
    """
    held = reading()
    return {} if held is None else held


def changes(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Makes one change to the file, and to nothing else in it.

    Two writers are alive at once wherever a menu writes a setting while the interface goes
    on remembering flows, and wherever two `hmz` share a home -- so nothing a writer read
    earlier is written back. The file is read again under a lock, the change is made to what
    it holds now, and that is what goes back: a part some other writer changed since is still
    there afterwards.

    The lock is a `flock` on a file beside it, which the kernel lets go of however the
    process ends. Whole and then moved into place, as every other file humanize writes is:
    one read while it is being written is the old one or the new one and never half of each.
    A new file is this user's alone, and one already there keeps the mode it has.

    One there that cannot be read is never written over: it is most likely somebody halfway
    through correcting it by hand, and what any writer holds of it is older than what they
    have typed since.

    Args:
      change: What to do to a reading of the file, in place.

    Returns:
      What the file holds now.

    Raises:
      OSError: If it cannot be read, or written.
      yaml.YAMLError: If the change left something YAML cannot hold.
    """
    at = where()
    with _locked(at):
        held = reading()
        if held is None:
            raise OSError(f"{at} cannot be read as YAML: correct or remove it")
        change(held)
        said = yaml.safe_dump(held, sort_keys=False, allow_unicode=True)
        atomic.writes(at, said, mode=None if at.exists() else 0o600)
    return held


@contextlib.contextmanager
def _locked(at: Path) -> Generator[None]:
    """Holds the lock every writer of the file takes, for as long as the block runs.

    Where it cannot be had the block runs anyway, which is a write that might meet another
    rather than one that never happens: a home that cannot be written, a lock file somebody
    else made that this cannot open, a filesystem that has no `flock`, or a writer that has
    held it for longer than anybody at an interface should wait -- one stopped with ctrl-z
    halfway through a write is holding it for as long as it is stopped.
    """
    import fcntl

    try:
        at.parent.mkdir(parents=True, exist_ok=True)
        # Read-only, which `flock` needs no more than, so that one another user made is still
        # one this can take.
        fd = os.open(
            at.with_name(f".{at.name}.lock"),
            os.O_CREAT | os.O_RDONLY | os.O_CLOEXEC,
            0o600,
        )
    except OSError:
        yield
        return
    try:
        waited = time.monotonic() + _PATIENCE
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                if time.monotonic() < waited:
                    time.sleep(0.01)
                    continue
            except OSError:
                pass
            break
        yield
    finally:
        os.close(fd)  # which lets go of the lock too

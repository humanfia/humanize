"""A sign-in that refreshes itself, held by one machine's turns at a time.

Some logins keep a refresh token in their credential file: Codex signed in with ChatGPT, Claude
Code with a subscription, and the OAuth logins of most of the others. Each refresh writes a new
refresh token and spends the one it replaced, which makes the file one family of tokens rather
than a value: a spent one presented again is read by the vendor as a stolen one, and the whole
family is revoked -- every copy of it, the original included, signed out at once.

So such a file is never in two places that refresh apart. A turn on this machine never copies
it -- a write is always answered with the account's own file -- and every turn here shares it,
which is one holder. A turn whose CLI runs on another machine has to be sent a copy, which is a
second holder; that one is let out only while no other turn holds the file at all, and is
brought back before anybody else may. Both are said with a lock on the directory the file is
in: shared by the turns here, exclusive for the one copy out. A lock rather than a note, so a
turn killed outright gives it up with its process.

Neither waits for the other. The holder of the lock is a CLI's process, which a flow may keep
open until the run ends, so a turn that waited for it could wait for the run it is part of.
"""

from __future__ import annotations

import contextlib
import errno
import logging
import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

__all__ = ["REFRESHES", "lent", "refreshes", "refreshing"]

log = logging.getLogger(__name__)

#: What a credential that refreshes itself holds, in each spelling these CLIs write one in:
#: Codex's, Qwen's and Kimi's `refresh_token`, Claude Code's and Cursor's `refreshToken`, the
#: `"refresh":` of opencode's and pi's. What an API key, a gateway's address or a CLI's settings
#: never hold.
REFRESHES = re.compile(rb"""refresh[_-]?token|["']refresh["']\s*:""", re.IGNORECASE)

#: How much of a file is read to ask whether it is one of those. A sign-in is a few kilobytes,
#: and a file this big is not one.
_AT_MOST = 1 << 20

#: What every refusal here says, which is also what a failed turn is known by
#: (:data:`hmz.coganchor.backends.SIGNS`).
SAID = "signs in with a token that refreshes itself"


def refreshes(path: str) -> bool:
    """Whether a file is a sign-in that refreshes itself.

    Args:
      path: The file.

    Returns:
      Whether it holds a refresh token, in any spelling :data:`REFRESHES` knows.
    """
    try:
        with open(path, "rb") as reading:  # noqa: PTH123
            return bool(REFRESHES.search(reading.read(_AT_MOST)))
    except OSError:
        return False


def refreshing(roots: Iterable[str], *, inside: bool = True) -> frozenset[str]:
    """The sign-ins that refresh themselves among some credential paths.

    Args:
      roots: The paths, each a file or a directory of them. One that is not there is nothing.
      inside: Whether to look inside a directory. Not where a directory may be a CLI's
        sessions rather than its credentials -- those are thousands of files, and a
        transcript may well mention a refresh token.

    Returns:
      The files, by path.
    """
    found: set[str] = set()
    for root in map(os.path.normpath, roots):
        if os.path.isfile(root):  # noqa: PTH113
            if refreshes(root):
                found.add(root)
            continue
        if not inside:
            continue
        for at, _, names in os.walk(root):
            found.update(
                path
                for name in names
                if refreshes(path := os.path.join(at, name))  # noqa: PTH118
            )
    return frozenset(found)


@contextlib.contextmanager
def lent(files: Iterable[str], *, away: bool) -> Generator[None]:
    """Holds some sign-ins that refresh themselves for as long as the block runs.

    Args:
      files: The sign-ins, as :func:`refreshing` found them.
      away: Whether they are about to be copied to another machine, which takes them whole;
        otherwise they are used where they are, beside every other turn here doing the same.

    Raises:
      OSError: With `EBUSY`, if they are held the other way already: a copy is out on another
        machine, or -- for one about to be copied -- a turn is using them already.
    """
    import fcntl

    how = fcntl.LOCK_EX if away else fcntl.LOCK_SH
    with contextlib.ExitStack() as holding:
        for directory in sorted({os.path.dirname(one) for one in files}):  # noqa: PTH120
            try:
                held = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            except OSError:
                continue  # gone already, which is nothing left to hold
            holding.callback(os.close, held)
            try:
                fcntl.flock(held, how | fcntl.LOCK_NB)
            except BlockingIOError:
                raise OSError(
                    errno.EBUSY,
                    (
                        f"this account {SAID}, and another turn is using it, so no copy "
                        "of it can go to another machine now -- two copies refreshing apart "
                        "get the sign-in revoked; run this turn on this machine, or give "
                        "it an account signed in with a key"
                    )
                    if away
                    else (
                        f"this account {SAID}, and a copy of it is out on another machine "
                        "for a turn there -- two copies refreshing apart get the sign-in "
                        "revoked; this turn can run once that one is over"
                    ),
                    directory,
                ) from None
            except OSError as why:
                # A filesystem that cannot lock a directory -- NFS emulates these with locks
                # an fd opened to read cannot take exclusively. Said, and the turn taken
                # unheld: refusing every turn of the account there would be refusing to run.
                log.warning("cannot hold %s for this turn: %s", directory, why)
        yield

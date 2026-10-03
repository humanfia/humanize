"""humanize: flows of coding agents, and the runs of them."""

from __future__ import annotations

import contextlib
import functools
import os
import pathlib

__all__ = ["here", "home"]

#: What humanize's own directories are called, and what they were called before.
_NAME = ".hmz"
_WAS = ".humanize"


def home() -> pathlib.Path:
    """Where humanize keeps what outlives one run of one flow.

    Under your home directory, unless `HUMANIZE_HOME` says otherwise -- which is what a test
    says, and what a machine holding more than one of these would. One kept under the name it
    had before is moved to this one the first time it is asked for.

    Returns:
      The directory. It is not made here: it is made by whatever writes into it.
    """
    said = os.environ.get("HUMANIZE_HOME")
    if said:
        return pathlib.Path(said)
    return _moved(pathlib.Path.home() / _NAME)


def here() -> pathlib.Path:
    """Where humanize keeps what is this project's own: its flows, and the runs exported here.

    `.hmz` in the directory humanize is being run in. One kept under the name it had before is
    moved to it the first time it is asked for -- unless that is a home rather than this
    project's: `~/.humanize`, which :func:`home` moves or leaves by its own rules, or the
    directory `HUMANIZE_HOME` names.

    Returns:
      The directory, relative to the one being run in: kept unresolved, so that a directory
      since removed is one holding nothing rather than a reason to fail. It is not made here.
    """
    at = pathlib.Path(_NAME)
    # Run in a directory since removed: there is nothing there to move.
    with contextlib.suppress(OSError):
        _project(at.absolute(), home())
    return at


@functools.cache
def _project(at: pathlib.Path, kept: pathlib.Path) -> None:
    """Moves a project's own directory where what was there before is not a home.

    Args:
      at: The project's directory, whole.
      kept: Humanize's home as it is now, which was asked for first so that, run from your
        home directory, the one there is moved by the rules for a home.
    """
    was = at.with_name(_WAS).resolve()
    # With `os.path`, which leaves a `~` with no home behind it as it is where `Path` raises:
    # a machine with no home directory has no home there for a project to be mistaken for.
    yours = pathlib.Path(os.path.expanduser("~/" + _WAS))  # noqa: PTH111
    if was not in (yours.resolve(), kept.resolve()):
        _moved(at)


@functools.cache
def _moved(at: pathlib.Path) -> pathlib.Path:
    """One of humanize's directories, with the one it was before moved to it where need be.

    Moved in one rename, and only while nothing is at the new place: where both are there the
    new one is the one in use, and the old one is left as it was rather than merged into it.
    Once per place and process, being on the way to every path under it.

    Args:
      at: Where the directory is now, beside where it was.

    Returns:
      `at`, whether or not anything was moved.
    """
    # Nothing to move, or nowhere it could go -- a parent nobody may write, another device:
    # either way the old one is left out of use rather than humanize left unable to start.
    with contextlib.suppress(OSError):
        if not at.exists():
            at.with_name(_WAS).rename(at)
    return at

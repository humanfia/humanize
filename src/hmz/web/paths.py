"""The directories of this machine a path being typed could become, as a shell completes one.

What a page offers under a directory being written -- an environment's own on this machine, or
where a run is to work: every directory whose path starts with what was typed, `~` the home it
names. Names and nothing more: no file is read, and nothing is listed that is not a directory.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .routing import Refusal, routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["ROUTES", "completed", "listed"]

#: The most a page is offered at once: past it, typing more says which.
_MOST = 50


def completed(typed: str) -> list[str]:
    """Every directory the path typed could become, written as it was typed.

    Args:
      typed: A path being written, `~` and all; "" for the home directory's own.

    Returns:
      Each directory it could become, sorted, those starting with a dot only where a dot was
      typed, at most the first fifty -- each spelled as it was typed, a `~` kept a `~`, and
      ending in the separator it would go on with.
    """
    said = typed or "~/"
    spelled, name = os.path.split(said)
    under = Path(spelled or ".").expanduser()
    try:
        found = sorted(
            one.name
            for one in os.scandir(under)
            if one.name.startswith(name)
            and (name.startswith(".") or not one.name.startswith("."))
            and one.is_dir()
        )
    except OSError:
        return []
    lead = spelled if not spelled or spelled.endswith(os.sep) else spelled + os.sep
    return [f"{lead}{one}{os.sep}" for one in found[:_MOST]]


def _completed(asked: Asked) -> dict[str, Any]:
    return {"paths": completed(asked.query.get("typed", ""))}


#: The most entries of one directory a page is handed.
_LISTED = 500


def listed(at: str, *, files: bool, hidden: bool) -> dict[str, Any]:
    """What is in one directory, as a page's file browser lists it.

    Args:
      at: The directory, `~` and all; "" for the home directory.
      files: Whether files are listed beside directories.
      hidden: Whether what starts with a dot is listed.

    Returns:
      The directory as it is shown, `~` for the home directory, and whole; the one above it,
      or "" at the top; and what is in it, directories first, each by name and whether it is
      a directory -- at most five hundred.

    Raises:
      Refusal: If it is not a directory there is.
    """
    home = Path.home()
    whole = Path(at or "~").expanduser()
    if not whole.is_absolute():
        whole = home / whole
    try:
        whole = whole.resolve()
        found = list(os.scandir(whole))
    except OSError as why:
        raise Refusal(
            f"{at or '~'} cannot be read: {why.strerror or why}", 404
        ) from why
    kept = sorted(
        (
            (one.name, _directory(one))
            for one in found
            if hidden or not one.name.startswith(".")
        ),
        key=lambda one: (not one[1], one[0].casefold()),
    )
    entries = [{"name": name, "dir": directory} for name, directory in kept]
    if not files:
        entries = [one for one in entries if one["dir"]]
    return {
        "at": _spelled(whole, home),
        "whole": str(whole),
        "up": _spelled(whole.parent, home) if whole.parent != whole else "",
        "entries": entries[:_LISTED],
        "more": max(0, len(entries) - _LISTED),
    }


def _directory(one: os.DirEntry[str]) -> bool:
    try:
        return one.is_dir()
    except OSError:
        return False


def _spelled(at: Path, home: Path) -> str:
    """A directory as a person writes it: under the home directory, from `~`."""
    if at == home:
        return "~"
    if at.is_relative_to(home):
        return f"~/{at.relative_to(home).as_posix()}"
    return str(at)


def _listed(asked: Asked) -> dict[str, Any]:
    query = asked.query
    return listed(
        query.get("at", ""),
        files=query.get("files") == "1",
        hidden=query.get("hidden") == "1",
    )


#: What a page asks of this machine's directories.
ROUTES = routes(("GET", "/api/paths", _completed), ("GET", "/api/files", _listed))

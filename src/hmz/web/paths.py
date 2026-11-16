"""The directories of this machine a path being typed could become, as a shell completes one.

What a page offers under a directory being written -- an environment's own on this machine, or
where a run is to work. The daemon's `paths.*` (:mod:`hmz.daemon.api.paths`), served over HTTP
until the page calls them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .routing import answered, routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["ROUTES", "completed", "listed"]


def completed(typed: str) -> list[str]:
    """Every directory the path typed could become, as `paths.complete` answers."""
    from hmz.daemon.api import paths

    return paths.completed(typed)


def listed(at: str, *, files: bool, hidden: bool) -> dict[str, Any]:
    """What is in one directory, as `paths.list` answers.

    Raises:
      Refusal: If it is not a directory there is.
    """
    from hmz.daemon.api import paths

    with answered():
        return paths.listed(at, files=files, hidden=hidden)


def _completed(asked: Asked) -> dict[str, Any]:
    return {"paths": completed(asked.query.get("typed", ""))}


def _listed(asked: Asked) -> dict[str, Any]:
    query = asked.query
    return listed(
        query.get("at", ""),
        files=query.get("files") == "1",
        hidden=query.get("hidden") == "1",
    )


#: What a page asks of this machine's directories.
ROUTES = routes(("GET", "/api/paths", _completed), ("GET", "/api/files", _listed))

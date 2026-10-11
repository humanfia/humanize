"""The directories of this machine a path being typed could become, as a shell completes one.

What a page offers under a directory being written -- an environment's own on this machine, or
where a run is to work: every directory whose path starts with what was typed, `~` the home it
names. Names and nothing more: no file is read, and nothing is listed that is not a directory.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .routing import routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["ROUTES", "completed"]

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


#: What a page asks of this machine's directories.
ROUTES = routes(("GET", "/api/paths", _completed))

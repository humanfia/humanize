"""Daemons on other machines, reached over ssh and answered through this interface.

Reaching one is the runtime's (`Hmz.daemons.remotes`), which the terminal interface reaches
them by as well: what is reached there is that machine's own web interface, which a page asks
through this one -- the remote interface keeps its own key, its own runs and its own refusals,
and nothing of it is served to anything but this page. This is how a page reads how one
stands, and has it reached again.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .routing import Refusal, routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["ROUTES"]


def _remotes(asked: Asked) -> Any:
    """The daemons on other machines, where the interface reaches any by the name asked."""
    from .daemons import found

    if asked.site.remotes is None or found(asked.matched["name"]) is None:
        raise Refusal("There is no daemon by that name.", 404)
    return asked.site.remotes


def _state(asked: Asked) -> dict[str, str]:
    name = asked.matched["name"]
    if name == "local":
        from hmz.coganchor import __version__

        return {"state": "up", "detail": "", "version": __version__}
    return _remotes(asked).state(name)


def _connect(asked: Asked) -> dict[str, str]:
    if asked.matched["name"] == "local":
        return _state(asked)
    try:
        return _remotes(asked).connect(asked.matched["name"])
    except LookupError as why:
        raise Refusal(str(why), 404) from why
    except RuntimeError as why:
        raise Refusal(str(why), 503) from why


#: How a page reads how a daemon stands, and has it reached.
ROUTES = routes(
    ("GET", "/api/daemons/{name}/state", _state),
    ("POST", "/api/daemons/{name}/connect", _connect),
)

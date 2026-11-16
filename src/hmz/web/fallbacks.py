"""Where a turn goes when the place taking it cannot take it: every step, written and cleared.

The routes of `fallbacks.*` (`hmz.daemon.api.fallbacks`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hmz.daemon.api import fallbacks
from hmz.daemon.api.fallbacks import listed

from .routing import refused, routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["ROUTES", "listed"]


def _write(asked: Asked) -> dict[str, Any]:
    spec, to, said = asked.text("spec"), asked.texts("to"), asked.body
    with refused():
        return fallbacks.write(
            asked.site.hmz,
            spec,
            to,
            said.get("tries", 0),
            said.get("policy", ""),
            said.get("timeout", 0),
        )


def _clear(asked: Asked) -> dict[str, Any]:
    spec = asked.text("spec")
    with refused():
        return fallbacks.clear(asked.site.hmz, spec)


#: What a page reads of the fallbacks, and does to them.
ROUTES = routes(
    ("GET", "/api/fallbacks", lambda asked: listed(asked.site.hmz)),
    ("POST", "/api/fallbacks", _write),
    ("POST", "/api/fallbacks/clear", _clear),
)

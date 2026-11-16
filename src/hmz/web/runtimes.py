"""The runtimes -- the machines a flow's environments may be put on: listed, written, asked.

The routes of `runtimes.*` (`hmz.daemon.api.runtimes`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hmz.daemon.api import runtimes
from hmz.daemon.api.runtimes import listed

from .routing import refused, routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["ROUTES", "listed"]


def _write(asked: Asked) -> dict[str, Any]:
    backend, name, fields = (
        asked.text("backend"),
        asked.text("name"),
        asked.named("fields"),
    )
    with refused():
        return runtimes.write(
            asked.site.hmz,
            backend,
            name,
            fields,
            replace=asked.body.get("replace") is True,
        )


def _remove(asked: Asked) -> dict[str, Any]:
    backend, name = asked.text("backend"), asked.text("name")
    with refused():
        return runtimes.remove(asked.site.hmz, backend, name)


def _check(asked: Asked) -> dict[str, Any]:
    backend, name = asked.text("backend"), asked.text("name")
    with refused():
        return runtimes.check(asked.site.hmz, backend, name)


def _hosts(asked: Asked) -> dict[str, Any]:
    with refused():
        return runtimes.hosts(asked.site.hmz)


def _imports(asked: Asked) -> dict[str, Any]:
    names = asked.texts("names")
    with refused():
        return runtimes.imports(
            asked.site.hmz, names, update=asked.body.get("update") is True
        )


#: What a page reads of the runtimes, and does to them.
ROUTES = routes(
    ("GET", "/api/runtimes", lambda asked: listed(asked.site.hmz)),
    ("POST", "/api/runtimes", _write),
    ("POST", "/api/runtimes/remove", _remove),
    ("POST", "/api/runtimes/check", _check),
    ("GET", "/api/runtimes/hosts", _hosts),
    ("POST", "/api/runtimes/import", _imports),
)

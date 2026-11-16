"""What Humanize remembers, as a page reads it and changes it.

The routes of `settings.*` (`hmz.daemon.api.settings`), for the workspace a page names or
where the interface started.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hmz.daemon.api import settings

from .routing import Refusal, refused, routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["ROUTES"]

#: What a page may send to `/api/settings`.
_TAKEN = {"btw", "details", "reports", "backup", "listen", "ice_servers", "workspace"}


def _hmz(asked: Asked) -> Any:
    """Humanize, for the workspace a request names, or where the interface started."""
    said = asked.body.get("workspace") if "workspace" in asked.body else None
    workspace = said if isinstance(said, str) else asked.query.get("workspace", "")
    from hmz import daemon

    # Afresh, as what a workspace remembers is written by its runs as well as by this.
    return daemon.Hmz(asked.site.places.of(workspace, made=True).workspace)


def _write(asked: Asked) -> dict[str, Any]:
    if extra := sorted(set(asked.body) - _TAKEN):
        raise Refusal(f"Settings here take no {', '.join(extra)}.")
    with refused():
        return settings.write(_hmz(asked), asked.body)


#: What a page reads of the settings and changes in them.
ROUTES = routes(
    ("GET", "/api/settings", lambda asked: settings.read(_hmz(asked))),
    ("POST", "/api/settings", _write),
    ("POST", "/api/settings/forget", lambda asked: settings.forget(_hmz(asked))),
)

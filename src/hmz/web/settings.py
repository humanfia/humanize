"""What humanize remembers, as a page reads it and changes it.

The same settings the terminal interface's `/settings` reads and writes, through the same
object: what a workspace was last set up to run, which agent a side question goes to,
whether a turn's working is shown, and whether humanize reports its own failures.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .routing import Refusal, routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["ROUTES"]


def general(hmz: Any) -> dict[str, Any]:
    """What a page shows of humanize's own settings and of this workspace's."""
    settings = hmz.settings
    return {
        "workspace": str(hmz.workspace),
        "flow": settings.flow,
        "btw": settings.btw,
        "details": settings.details,
        "reports": settings.enable_sentry,
        "flows": sorted(settings.flows()),
    }


def _hmz(asked: Asked) -> Any:
    """humanize, for the workspace a request names, or where the interface started."""
    said = asked.body.get("workspace") if "workspace" in asked.body else None
    workspace = said if isinstance(said, str) else asked.query.get("workspace", "")
    from hmz import daemon

    # Afresh, as what a workspace remembers is written by its runs as well as by this.
    return daemon.Hmz(asked.site.places.of(workspace, made=True).workspace)


def _read(asked: Asked) -> dict[str, Any]:
    return general(_hmz(asked))


def _write(asked: Asked) -> dict[str, Any]:
    hmz = _hmz(asked)
    said = asked.body
    if extra := sorted(set(said) - {"btw", "details", "reports", "workspace"}):
        raise Refusal(f"Settings here take no {', '.join(extra)}.")
    # All of it read before any of it is written: a request refused changes nothing.
    if "btw" in said and not isinstance(said["btw"], str):
        raise Refusal("btw is an agent as -a spells one, or nothing.")
    if "details" in said and not isinstance(said["details"], bool):
        raise Refusal("details is true or false.")
    if "reports" in said and not isinstance(said["reports"], bool):
        raise Refusal("reports is true or false.")
    if "btw" in said:
        hmz.settings.btw = said["btw"]
    if "details" in said:
        hmz.settings.detailing(on=said["details"])
    if "reports" in said:
        hmz.settings.answers(enable_sentry=said["reports"])
    return general(hmz)


def _forget(asked: Asked) -> dict[str, Any]:
    hmz = _hmz(asked)
    return {"forgot": hmz.settings.forget()} | general(hmz)


#: What a page reads of the settings and changes in them.
ROUTES = routes(
    ("GET", "/api/settings", _read),
    ("POST", "/api/settings", _write),
    ("POST", "/api/settings/forget", _forget),
)

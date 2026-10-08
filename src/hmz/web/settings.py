"""What humanize remembers, as a page reads it and changes it.

The same settings the terminal interface's `/settings` reads and writes, through the same
object: what this workspace was last set up to run, which agent a side question goes to,
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


def _read(asked: Asked) -> dict[str, Any]:
    return general(asked.site.hmz)


def _write(asked: Asked) -> dict[str, Any]:
    hmz = asked.site.hmz
    said = asked.body
    if extra := sorted(set(said) - {"btw", "details", "reports"}):
        raise Refusal(f"Settings here take no {', '.join(extra)}.")
    if "btw" in said:
        if not isinstance(said["btw"], str):
            raise Refusal("btw is an agent as -a spells one, or nothing.")
        hmz.settings.btw = said["btw"]
    if "details" in said:
        if not isinstance(said["details"], bool):
            raise Refusal("details is true or false.")
        hmz.settings.detailing(on=said["details"])
    if "reports" in said:
        if not isinstance(said["reports"], bool):
            raise Refusal("reports is true or false.")
        hmz.settings.answers(enable_sentry=said["reports"])
    return general(hmz)


def _forget(asked: Asked) -> dict[str, Any]:
    hmz = asked.site.hmz
    return {"forgot": hmz.settings.forget()} | general(hmz)


#: What a page reads of the settings and changes in them.
ROUTES = routes(
    ("GET", "/api/settings", _read),
    ("POST", "/api/settings", _write),
    ("POST", "/api/settings/forget", _forget),
)

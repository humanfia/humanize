"""What Humanize remembers, as a page reads it and changes it.

The same settings the terminal interface's `/settings` reads and writes, through the same
object: what a workspace was last set up to run, which agent a side question goes to,
whether a turn's working is shown, whether Humanize reports its own failures, and the git
repositories epics are backed up to -- each URL shown with nothing signed into it, and one sent
back as it was shown kept as it is written.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from .routing import Refusal, routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["ROUTES"]


def general(hmz: Any) -> dict[str, Any]:
    """What a page shows of Humanize's own settings and of this workspace's."""
    settings = hmz.settings
    return {
        "workspace": str(hmz.workspace),
        "flow": settings.flow,
        "btw": settings.btw,
        "details": settings.details,
        "reports": settings.enable_sentry,
        "flows": sorted(settings.flows()),
        "backup": {
            "targets": [
                {
                    "name": one.name,
                    "url": hmz.verses.plain(one.url),
                    "branch": one.branch,
                    "policies": list(one.policies),
                    "every": one.every,
                }
                for one in hmz.backups.targets()
            ],
            "defaults": list(hmz.backups.defaults()),
        },
    }


def _hmz(asked: Asked) -> Any:
    """Humanize, for the workspace a request names, or where the interface started."""
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
    if extra := sorted(
        set(said) - {"btw", "details", "reports", "backup", "workspace"}
    ):
        raise Refusal(f"Settings here take no {', '.join(extra)}.")
    # All of it read before any of it is written: a request refused changes nothing.
    if "btw" in said and not isinstance(said["btw"], str):
        raise Refusal("btw is an agent as -a spells one, or nothing.")
    if "details" in said and not isinstance(said["details"], bool):
        raise Refusal("details is true or false.")
    if "reports" in said and not isinstance(said["reports"], bool):
        raise Refusal("reports is true or false.")
    # First of what is written, as it is refused without writing anything.
    if "backup" in said:
        _back_up_to(hmz, said["backup"])
    if "btw" in said:
        hmz.settings.btw = said["btw"]
    if "details" in said:
        hmz.settings.detailing(on=said["details"])
    if "reports" in said:
        hmz.settings.answers(enable_sentry=said["reports"])
    return general(hmz)


def _back_up_to(hmz: Any, said: object) -> None:
    """Writes down every backup target and the defaults, or nothing where one is not one."""
    if not isinstance(said, dict):
        raise Refusal("backup is an object of targets and defaults.")
    backup = cast("dict[str, Any]", said)
    targets: object = backup.get("targets", [])
    defaults: object = backup.get("defaults", [])
    if not isinstance(targets, list) or not all(
        isinstance(one, dict) for one in cast("list[Any]", targets)
    ):
        raise Refusal("backup's targets are a list of objects.")
    if not isinstance(defaults, list):
        raise Refusal("backup's defaults are a list of target names.")
    # A URL sent back as it was shown, struck of what was signed into it, is the one written.
    written = {one.name: one.url for one in hmz.backups.targets()}
    kept: list[dict[str, Any]] = []
    for one in cast("list[dict[str, Any]]", targets):
        url = written.get(str(one.get("name")))
        if url is not None and one.get("url") == hmz.verses.plain(url):
            kept.append(one | {"url": url})
        elif "***@" in str(one.get("url")):
            raise Refusal(f"Type {one.get('name')}'s URL whole, signed in again.")
        else:
            kept.append(one)
    try:
        hmz.settings.back_up_to(kept, [str(one) for one in cast("list[Any]", defaults)])
    except ValueError as why:
        raise Refusal(f"{str(why)[:1].upper()}{str(why)[1:]}.") from why


def _forget(asked: Asked) -> dict[str, Any]:
    hmz = _hmz(asked)
    return {"forgot": hmz.settings.forget()} | general(hmz)


#: What a page reads of the settings and changes in them.
ROUTES = routes(
    ("GET", "/api/settings", _read),
    ("POST", "/api/settings", _write),
    ("POST", "/api/settings/forget", _forget),
)

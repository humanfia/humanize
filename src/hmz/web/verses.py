"""Where flows come from, as a page reads it and changes it: the flowverses, and installing.

The flowverses page `/flow` opens in the terminal interface, through the same object and into
the same directories: every flowverse -- but this project's flows and yours, places read where
they stand rather than indexes, which are listed with what is installed -- whether its index
was fetched or has something written into it, the flows it lists at their newest release with
what of each is installed, every release of one, and installing, updating, switching or
uninstalling one -- and adding, fetching and removing a flowverse. A URL is never handed a page
with anything signed into it. Nothing is installed, updated or uninstalled while an epic runs
anywhere on the machine, as the terminal interface does nothing of it while its flow runs.

Every flowverse's index is fetched once as the interface starts, in the background and saying
nothing -- `official` too where it was never fetched, and never one with something written
into it -- so that what the page says has a newer release is what the indexes say now.
"""

from __future__ import annotations

import contextlib
import threading
from typing import TYPE_CHECKING, Any

from .routing import Refusal, routes

if TYPE_CHECKING:
    from collections.abc import Callable

    from .routing import Asked

__all__ = ["ROUTES", "fetches"]

#: The flowverse humanize's own flows are installed out of: what it lists goes bare.
_OFFICIAL = "official"


def _indexed(one: Any) -> bool:
    """Whether flows are installed out of this place's index: not this project's, nor yours."""
    return not one.fixed or one.name == _OFFICIAL


def fetches(hmz: Any) -> threading.Thread:
    """Fetches every flowverse's index, on a thread of its own, saying nothing of how it went.

    Args:
      hmz: humanize.

    Returns:
      The thread, started.
    """

    def fetching() -> None:
        verses = hmz.flows.verses
        for one in verses.all():
            # A place nothing is fetched from, or one somebody wrote into, is left as it is.
            if not _indexed(one) or (one.fetched and verses.edited(one)):
                continue
            with contextlib.suppress(Exception):
                verses.fetch(one.name)

    thread = threading.Thread(target=fetching, daemon=True, name="hmz-web-fetch")
    thread.start()
    return thread


def listed(hmz: Any) -> dict[str, Any]:
    """Every flowverse, every flow installed out of one, and the newer releases there are."""
    verses = hmz.flows.verses
    installed = verses.installed()
    return {
        "verses": [
            {
                "name": one.name,
                "url": verses.whence(one, ""),
                "fetched": one.fetched,
                "fixed": one.fixed,
                "edited": bool(one.fetched and verses.edited(one)),
                "installed": sum(1 for each in installed if each.verse == one.name),
            }
            for one in verses.all()
            if _indexed(one)
        ],
        "installed": [_installed(one) for one in installed],
        "updates": [
            {
                "flow": one.installed.called,
                "from": one.installed.version,
                "to": one.version,
            }
            for one in verses.updates()
        ],
    }


def _installed(one: Any) -> dict[str, Any]:
    return {
        "flow": one.called,
        "verse": one.verse,
        "listed": one.listed,
        "version": one.version,
        "repo": one.repo,
        "ref": one.ref,
    }


def _called(verse: str, listed: str) -> str:
    """What a flow an index lists is offered under once installed, as `install` takes it."""
    return listed if verse == _OFFICIAL else f"@{verse}/{listed}"


def _index(asked: Asked) -> dict[str, Any]:
    verses = asked.site.hmz.flows.verses
    name = asked.matched["name"]
    one = verses.find(name)
    if one is None:
        raise Refusal(f"There is no flowverse {name}.", 404)
    index = verses.index(name)
    mine = {
        each.listed: each.version for each in verses.installed() if each.verse == name
    }
    return {
        "name": name,
        "url": verses.whence(one, ""),
        "fetched": one.fetched,
        "fixed": one.fixed,
        "edited": bool(one.fetched and verses.edited(one)),
        "flows": [
            {
                "listed": flow,
                "flow": _called(name, flow),
                "installed": mine.get(flow, ""),
                "releases": [
                    {
                        "version": release.version,
                        "description": release.description,
                        "prerelease": bool(release.semver.prerelease),
                        "license": release.license,
                        "repo": release.repo,
                        "dependencies": release.dependencies,
                    }
                    for release in index.versions(flow)
                ],
            }
            for flow in index.flows()
        ],
        "skipped": [{"at": str(each.at), "why": each.why} for each in index.skipped],
    }


def _idle(asked: Asked) -> None:
    """Refuses a change to what is installed while an epic runs anywhere on the machine."""
    if asked.site.places.running():
        raise Refusal("An epic is running: flows change once none is.", 409)


def _changed(asked: Asked, change: Callable[[Any], str]) -> dict[str, Any]:
    """Makes one change to the flowverses, refused with what refused it."""
    try:
        said = change(asked.site.hmz.flows.verses)
    except (ValueError, OSError) as why:
        raise Refusal(str(why)) from why
    return {"said": said} | listed(asked.site.hmz)


def _add(asked: Asked) -> dict[str, Any]:
    url, name = asked.text("url"), asked.text("name", required=False)

    def add(verses: Any) -> str:
        return f"added {verses.add(url, name).name}"

    return _changed(asked, add)


def _fetch(asked: Asked) -> dict[str, Any]:
    name = asked.text("name")

    def fetch(verses: Any) -> str:
        return f"fetched {verses.fetch(name).name}"

    return _changed(asked, fetch)


def _remove(asked: Asked) -> dict[str, Any]:
    _idle(asked)
    name = asked.text("name")

    def remove(verses: Any) -> str:
        return f"removed {name}" if verses.remove(name) else f"there was no {name}"

    return _changed(asked, remove)


def _install(asked: Asked) -> dict[str, Any]:
    _idle(asked)
    flow, version = asked.text("flow"), asked.text("version", required=False)

    def install(verses: Any) -> str:
        done = verses.install(flow, version)
        return ", ".join(f"{one.called} {one.version}" for one in done) or "nothing"

    return _changed(asked, install)


def _uninstall(asked: Asked) -> dict[str, Any]:
    _idle(asked)
    flow = asked.text("flow")

    def uninstall(verses: Any) -> str:
        return (
            f"uninstalled {flow}"
            if verses.uninstall(flow)
            else f"{flow} was not installed"
        )

    return _changed(asked, uninstall)


def _fork(asked: Asked) -> dict[str, Any]:
    flow = asked.text("flow")
    place = asked.site.places.of(asked.text("workspace", required=False))
    try:
        at = place.hmz.flows.fork(flow)
    except (ValueError, OSError) as why:
        raise Refusal(str(why)) from why
    return {"said": f"copied {flow} to {at}", "at": str(at)}


#: What a page reads of where flows come from, and changes there.
ROUTES = routes(
    ("GET", "/api/flowverses", lambda asked: listed(asked.site.hmz)),
    ("GET", "/api/flowverses/{name}", _index),
    ("POST", "/api/flowverses", _add),
    ("POST", "/api/flowverses/fetch", _fetch),
    ("POST", "/api/flowverses/remove", _remove),
    ("POST", "/api/flowverses/install", _install),
    ("POST", "/api/flowverses/uninstall", _uninstall),
    ("POST", "/api/flows/fork", _fork),
)

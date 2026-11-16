"""Where flows come from, as a page reads it and changes it: the flowverses, and installing.

The daemon's `flowverses.*` (:mod:`hmz.daemon.api.flowverses`), served over HTTP until the page
calls them, and `flows.fork` beside them. Nothing is installed, updated or uninstalled while an
epic runs anywhere on the machine, as the terminal interface does nothing of it while its flow
runs.

Every flowverse's index is fetched once as the interface starts, in the background and saying
nothing -- `official` too where it was never fetched, and never one with something written
into it -- so that what the page says has a newer release is what the indexes say now.
"""

from __future__ import annotations

import contextlib
import threading
from typing import TYPE_CHECKING, Any

from .routing import refused, routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["ROUTES", "fetches", "listed"]


def fetches(hmz: Any) -> threading.Thread:
    """Fetches every flowverse's index, on a thread of its own, saying nothing of how it went.

    Args:
      hmz: Humanize.

    Returns:
      The thread, started.
    """
    from hmz.daemon.api.flowverses import indexed

    def fetching() -> None:
        verses = hmz.flows.verses
        for one in verses.all():
            # A place nothing is fetched from, or one somebody wrote into, is left as it is.
            if not indexed(one) or (one.fetched and verses.edited(one)):
                continue
            with contextlib.suppress(Exception):
                verses.fetch(one.name)

    thread = threading.Thread(target=fetching, daemon=True, name="hmz-web-fetch")
    thread.start()
    return thread


def listed(hmz: Any) -> dict[str, Any]:
    """Every flowverse, every flow installed out of one, and the newer releases there are."""
    from hmz.daemon.api import flowverses

    return flowverses.listed(hmz)


def _index(asked: Asked) -> dict[str, Any]:
    from hmz.daemon.api import flowverses

    with refused():
        return flowverses.index(asked.site.hmz, asked.matched["name"])


def _changes(change: str, *texts: str) -> Any:
    """The route making one change, given the texts its body says, the first required."""

    def route(asked: Asked) -> dict[str, Any]:
        from hmz.daemon.api import flowverses

        said = {
            name: asked.text(name, required=not at) for at, name in enumerate(texts)
        }
        running = bool(asked.site.places.running())
        with refused():
            return flowverses.changed(asked.site.hmz, change, said, running=running)

    return route


def _fork(asked: Asked) -> dict[str, Any]:
    from hmz.daemon.api import flows

    flow = asked.text("flow")
    place = asked.site.places.of(asked.text("workspace", required=False))
    with refused():
        return flows.forked(place.hmz, flow)


#: What a page reads of where flows come from, and changes there.
ROUTES = routes(
    ("GET", "/api/flowverses", lambda asked: listed(asked.site.hmz)),
    ("GET", "/api/flowverses/{name}", _index),
    ("POST", "/api/flowverses", _changes("add", "url", "name")),
    ("POST", "/api/flowverses/fetch", _changes("fetch", "name")),
    ("POST", "/api/flowverses/remove", _changes("remove", "name")),
    ("POST", "/api/flowverses/install", _changes("install", "flow", "version")),
    ("POST", "/api/flowverses/uninstall", _changes("uninstall", "flow")),
    ("POST", "/api/flows/fork", _fork),
)

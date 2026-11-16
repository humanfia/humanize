"""`flowverses.*`: where flows come from, as a client reads it and changes it.

What `/flow` in the terminal interface opens, through the same object and into the same
directories: every flowverse -- but this project's flows and yours, places read where they
stand rather than indexes -- whether its index was fetched or has something written into it,
the flows it lists with what of each is installed, every release of one, installing,
updating, switching or uninstalling one, and adding, fetching and removing a flowverse. A URL is
never answered with anything signed into it. Nothing is installed, uninstalled or removed while
an epic runs anywhere on the machine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from hmz.rpc import Call, Handler

__all__ = ["METHODS", "changed", "fetches", "index", "indexed", "listed"]

#: The flowverse Humanize's own flows are installed out of: what it lists goes bare.
_OFFICIAL = "official"


def indexed(one: Any) -> bool:
    """Whether flows are installed out of this place's index: not this project's, nor yours."""
    return not one.fixed or one.name == _OFFICIAL


def fetches() -> None:
    """Fetches every flowverse's index, on a thread of its own, saying nothing of how it went.

    A place nothing is fetched from, or one somebody wrote into, is left as it is.
    """
    import contextlib
    import threading

    def fetching() -> None:
        verses = _machine().flows.verses
        for one in verses.all():
            if not indexed(one) or (one.fetched and verses.edited(one)):
                continue
            with contextlib.suppress(Exception):
                verses.fetch(one.name)

    threading.Thread(target=fetching, daemon=True, name="hmz-fetch-verses").start()


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
            if indexed(one)
        ],
        "installed": [
            {
                "flow": one.called,
                "verse": one.verse,
                "listed": one.listed,
                "version": one.version,
                "repo": one.repo,
                "ref": one.ref,
            }
            for one in installed
        ],
        "updates": [
            {
                "flow": one.installed.called,
                "from": one.installed.version,
                "to": one.version,
            }
            for one in verses.updates()
        ],
    }


def index(hmz: Any, name: str) -> dict[str, Any]:
    """One flowverse: the flows its index lists, each with every release, and what it skipped.

    Raises:
      RpcError: 404, if there is no such flowverse.
    """
    verses = hmz.flows.verses
    one = verses.find(name)
    if one is None:
        raise RpcError(Code.NOT_FOUND, f"There is no flowverse {name}.")
    found = verses.index(name)
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
                # What it is offered under once installed, as `install` takes it.
                "flow": flow if name == _OFFICIAL else f"@{name}/{flow}",
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
                    for release in found.versions(flow)
                ],
            }
            for flow in found.flows()
        ],
        "skipped": [{"at": str(each.at), "why": each.why} for each in found.skipped],
    }


#: What each change does to the flowverses, given what the call says, and says it did.
_CHANGES: dict[str, Callable[[Any, Mapping[str, Any]], str]] = {
    "add": lambda verses, said: (
        f"added {verses.add(said['url'], said.get('name', '')).name}"
    ),
    "fetch": lambda verses, said: f"fetched {verses.fetch(said['name']).name}",
    "remove": lambda verses, said: (
        f"removed {said['name']}"
        if verses.remove(said["name"])
        else f"there was no {said['name']}"
    ),
    "install": lambda verses, said: (
        ", ".join(
            f"{one.called} {one.version}"
            for one in verses.install(said["flow"], said.get("version", ""))
        )
        or "nothing"
    ),
    "uninstall": lambda verses, said: (
        f"uninstalled {said['flow']}"
        if verses.uninstall(said["flow"])
        else f"{said['flow']} was not installed"
    ),
}

#: The changes that wait for no epic to be running anywhere on the machine.
_IDLE = ("remove", "install", "uninstall")


def changed(
    hmz: Any, change: str, said: Mapping[str, Any], *, running: bool
) -> dict[str, Any]:
    """Makes one change to the flowverses, and answers what was done beside the list.

    Args:
      hmz: Humanize.
      change: `add`, `fetch`, `remove`, `install` or `uninstall`.
      said: What the change is given, by name, as its method takes it.
      running: Whether an epic is going anywhere on the machine.

    Raises:
      RpcError: 409 for a change to what is installed while an epic runs, 400 for what the
        change itself refuses.
    """
    if running and change in _IDLE:
        raise RpcError(Code.CONFLICT, "An epic is running: flows change once none is.")
    try:
        done = _CHANGES[change](hmz.flows.verses, said)
    except (ValueError, OSError) as why:
        raise RpcError(Code.REFUSED, str(why)) from why
    return {"said": done} | listed(hmz)


def _machine() -> Any:
    """Humanize, for the flowverses of the machine, which are no one workspace's."""
    from pathlib import Path

    from hmz.runtime import Hmz

    return Hmz(Path.home())


def _changes(change: str) -> Handler:
    def handler(call: Call) -> dict[str, Any]:
        from .workspaces import going

        running = change in _IDLE and bool(going())
        return changed(_machine(), change, call.params, running=running)

    return handler


#: Each method of the family, by name.
METHODS: Mapping[str, Handler] = {
    "flowverses.list": lambda _: listed(_machine()),
    "flowverses.get": lambda call: index(_machine(), call.params["name"]),
    **{f"flowverses.{change}": _changes(change) for change in _CHANGES},
}

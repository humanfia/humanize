"""Every run on this machine as its epic wrote it down: the list, one run, its trace, its timeline.

What a page reads of a run that is over, or of the one going, as far as the epic says it,
of every workspace. The daemon serves the same as `runs.*` and `backups.*`
(:mod:`hmz.daemon.api.runs`), which is where it is worked out: each route here only reads the
request, asks that, and says its refusals as HTTP ones. The run going in a workspace is also
followed live (`held`); this is what is written down of it.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz.daemon.api import backups
from hmz.daemon.api import runs as api
from hmz.daemon.api.runs import BUNDLE, held_by, local, resolved, row
from hmz.rpc import RpcError

from .routing import Download, Made, Refusal, Route, routes

if TYPE_CHECKING:
    from collections.abc import Generator

    from hmz.runtime.epic import Ran

    from .places import Places
    from .routing import Asked

__all__ = ["BUNDLE", "ROUTES", "Runs", "held_by", "local", "refused", "row"]


class Runs(api.Runs):
    """The runs of every workspace, read off the disk and kept until they change there.

    Args:
      places: Every workspace, for Humanize in the one a run was run in.
    """

    def __init__(self, places: Places) -> None:
        super().__init__(
            lambda workspace: places.of(workspace or str(places.here), made=True).hmz
        )
        self._places = places

    def workspaces(self) -> list[dict[str, Any]]:
        """Every workspace there is to offer, with how many runs it has and when it last ran."""
        runs = self.all()
        running = {one["workspace"] for one in self._places.running()}
        mine: dict[str, list[Ran]] = {}
        for ran in runs:
            mine.setdefault(resolved(ran.workspace), []).append(ran)
        return [
            {
                "path": where,
                "name": Path(where).name or where,
                "epics": len(mine.get(where, [])),
                "last": mine[where][0].began if mine.get(where) else "",
                "running": where in running,
                "here": where == str(self._places.here),
                "there": Path(where).is_dir(),
            }
            for where in self._places.known(list(mine))
        ]

    def named(self, name: str) -> Ran:
        """One run, by the name of its epic, of whichever workspace it was run in.

        Raises:
          Refusal: If no workspace has a run of that name.
        """
        with _said():
            return super().named(name)


def refused(why: ValueError) -> Refusal:
    """What a page is told of an archive that could not be imported, as the runtime said it.

    Args:
      why: What importing it raised.

    Returns:
      A conflict naming the epic, for one here already; otherwise a bad request.
    """
    return _refusal(api.refused(why))


def _refusal(why: RpcError) -> Refusal:
    """A refusal of the daemon's, said as the HTTP one of the same number."""
    return Refusal(why.message, why.code, **(why.data or {}))


@contextlib.contextmanager
def _said() -> Generator[None]:
    """Says a refusal of the daemon's as an HTTP one."""
    try:
        yield
    except RpcError as why:
        raise _refusal(why) from why


def _whole(asked: Asked, name: str, default: int) -> int:
    try:
        return int(asked.query.get(name, str(default)))
    except ValueError as why:
        raise Refusal(f"{name} is a whole number.") from why


def _listed(asked: Asked) -> dict[str, Any]:
    offset, limit = _whole(asked, "offset", 0), _whole(asked, "limit", 50)
    return api.listed(
        asked.site.runs,
        asked.site.places.running(),
        workspace=asked.query.get("workspace", ""),
        status=asked.query.get("status", ""),
        flow=asked.query.get("flow", ""),
        q=asked.query.get("q", ""),
        offset=max(0, offset),
        limit=min(200, max(1, limit)),
    )


def _one(asked: Asked) -> dict[str, Any]:
    with _said():
        return api.one(
            asked.site.runs, asked.site.places.running(), asked.matched["name"]
        )


def _trace(asked: Asked) -> dict[str, Any]:
    runs = asked.site.runs
    return {"sessions": runs.traced(runs.named(asked.matched["name"]))}


def _timeline(asked: Asked) -> dict[str, Any]:
    runs = asked.site.runs
    return runs.timeline(runs.named(asked.matched["name"])).document


def _span(asked: Asked) -> dict[str, Any]:
    runs = asked.site.runs
    ran = runs.named(asked.matched["name"])
    with _said():
        return runs.span(ran, asked.matched["id"], asked.query.get("layout", ""))


def _bundle(asked: Asked) -> Download:
    runs = asked.site.runs
    at = runs.bundled(runs.named(asked.matched["name"]))
    return Download(at, at.name, BUNDLE, gone=True)


def _backup(asked: Asked) -> dict[str, Any]:
    to: object = asked.body.get("to")
    if to is not None and not (
        isinstance(to, list)
        and all(isinstance(one, str) for one in cast("list[Any]", to))
    ):
        raise Refusal("to is a list of backup target names.")
    with _said():
        return api.backup(
            asked.site.runs, asked.matched["name"], cast("list[str] | None", to)
        )


def _stored(asked: Asked) -> dict[str, Any]:
    with _said():
        return backups.stored(asked.site.runs, asked.matched["target"])


def _pull(asked: Asked) -> dict[str, Any]:
    key = asked.text("key")
    with _said():
        return backups.pulled(asked.site.runs, asked.matched["target"], key)


def _import(asked: Asked) -> Made:
    archive = asked.file
    if archive is None:
        said = local(asked.text("path"))
        if not said.is_absolute():
            raise Refusal("Say path as a whole path on this machine.")
        archive = said
    with _said():
        return Made(asked.site.runs.imported(archive))


def _usage(asked: Asked) -> dict[str, Any]:
    days = min(365, max(1, _whole(asked, "days", 30)))
    return api.usage(asked.site.runs, days, asked.query.get("workspace", ""))


#: What a page reads of the runs written down here.
ROUTES = (
    *routes(
        ("GET", "/api/runs", _listed),
        ("GET", "/api/runs/{name}", _one),
        ("GET", "/api/runs/{name}/trace", _trace),
        ("GET", "/api/runs/{name}/timeline", _timeline),
        ("GET", "/api/runs/{name}/timeline/span/{id}", _span),
        ("GET", "/api/runs/{name}/bundle", _bundle),
        ("POST", "/api/runs/{name}/backup", _backup),
        ("GET", "/api/usage", _usage),
        ("GET", "/api/backups/{target}/epics", _stored),
        ("POST", "/api/backups/{target}/pull", _pull),
    ),
    Route("POST", "/api/runs/import", _import, file=BUNDLE),
)

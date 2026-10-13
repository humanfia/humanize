"""Every workspace on this machine, as the web interface serves them: one daemon, many places.

The terminal interface is about the directory it is opened in; the web interface is about the
machine, as the daemon is. It offers every workspace an epic was run in or that was set up or
written down here, and holds, per workspace, humanize for it and -- only while a page follows
its runs or acts on them -- a link to the host holding them. A link nobody has used for a while,
whose runs are idle, is let go of, so that a host with nothing to do and nobody reading goes as
it would with no interface open. What is running where nobody here holds a link is asked of the
daemon instead, which starts nothing.
"""

from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .routing import Refusal, routes

if TYPE_CHECKING:
    from collections.abc import Iterator

    from hmz.daemon import Link

    from .held import Held
    from .routing import Asked, Stream

__all__ = ["ROUTES", "Place", "Places"]

#: How long a link no page has followed or asked anything of is kept while its runs are idle,
#: in seconds.
_IDLE = 60.0

#: How often links are looked over for one to let go of, and the daemon asked what runs.
_LOOKING = 5.0


@dataclass
class Place:
    """One workspace, as this interface holds it.

    Attributes:
      workspace: Its directory, resolved.
      hmz: humanize, for it.
      held: Its runs as this interface follows them, while it does.
      used: When a page last asked anything of its runs, on the monotonic clock.
      streams: How many pages follow its runs now.
    """

    workspace: Path
    hmz: Any
    held: Held | None = None
    used: float = field(default_factory=time.monotonic)
    streams: int = 0
    #: The runs held in this process, where they are not held apart.
    hosting: Any = None


class Places:
    """Every workspace this interface serves, and the links it holds to their runs.

    Args:
      here: Where the interface was started, which a new epic is offered first.
      apart: Whether the runs are held apart from this process, by each workspace's host --
        which is what lets them outlive it -- or in it.
    """

    def __init__(self, here: Path, *, apart: bool) -> None:
        from hmz import daemon

        self.here = here.resolve()
        self._apart = apart
        self._lock = threading.Lock()
        self._places: dict[Path, Place] = {}
        self._closed = threading.Event()
        #: What the daemon last said is running, by workspace, where nothing here holds it.
        self._running: dict[str, dict[str, Any]] = {}
        self.hmz = self.of(str(self.here)).hmz
        self._daemon = daemon
        threading.Thread(target=self._looking, daemon=True, name="hmz-web").start()

    def of(self, workspace: str, *, made: bool = False) -> Place:
        """One workspace, as this holds it.

        Args:
          workspace: Its directory, `~` and all, or "" for where the interface started.
          made: Whether a directory that is not there may still be named -- an epic read
            back from a workspace since removed.

        Raises:
          Refusal: If there is no such directory.
        """
        at = Path(workspace).expanduser() if workspace else self.here
        if not at.is_absolute():
            raise Refusal(f"Say the workspace as a whole path, not {workspace}.")
        if not made and not at.is_dir():
            raise Refusal(f"There is no directory {at}.", 404)
        at = at.resolve()
        with self._lock:
            place = self._places.get(at)
            if place is None:
                from hmz import daemon

                place = self._places[at] = Place(at, daemon.Hmz(at))
            return place

    def held(self, workspace: str) -> Held:
        """The runs of one workspace as this follows them, reaching them first where it does not.

        Reaching them starts the workspace's host where none is, as the terminal interface's
        opening there would: asked of only where a page follows its runs or acts on them.

        Raises:
          Refusal: If there is no such directory, or its runs cannot be reached.
        """
        from .held import Held

        place = self.of(workspace)
        with self._lock:
            place.used = time.monotonic()
            if place.held is not None:
                return place.held
        try:
            held = Held(lambda: self._linking(place))
        except Exception as why:
            older = getattr(self._daemon, "Older", None)
            if older is not None and isinstance(why, older):
                raise Refusal(str(why), 409) from why
            raise Refusal(
                f"The runs of {place.workspace} could not be reached: {why}", 503
            ) from why
        with self._lock:
            if place.held is None:
                place.held = held
                return held
        held.close()
        return place.held

    def attached(self, workspace: str) -> Held | None:
        """The runs of one workspace as this follows them, where it does, reaching nothing."""
        place = self.of(workspace, made=True)
        with self._lock:
            return place.held

    def stream(self, workspace: str) -> Stream:
        """The runs of one workspace as a page follows them, counted as followed while it does."""
        from .routing import Stream

        place = self.of(workspace)
        held = self.held(workspace)
        inner = held.stream()

        def events(last: str, going: threading.Event) -> Iterator[Any]:
            with self._lock:
                place.streams += 1
            try:
                yield from inner.events(last, going)
            finally:
                with self._lock:
                    place.streams -= 1
                    place.used = time.monotonic()

        return Stream(events)

    def running(self) -> dict[str, dict[str, Any]]:
        """What runs in each workspace, by its path: the state, the run's number and its flow.

        And of a chat, its turn. Out of the links held here where there is one, and what the
        daemon last said of the rest; a workspace running nothing is left out.
        """
        with self._lock:
            said = dict(self._running)
            held = [
                (str(one.workspace), one.held)
                for one in self._places.values()
                if one.held
            ]
        for workspace, one in held:
            run = one.standing("run")
            if run is not None:
                said[workspace] = run
        return {
            where: run
            for where, run in said.items()
            if run.get("state") in ("running", "stopping")
        }

    def known(self, epics: list[str]) -> list[str]:
        """Every workspace there is to offer: where an epic ran, set up or written down here.

        Args:
          epics: The workspaces epics were run in, newest first.

        Returns:
          Each once: where the interface started, then those running, then the rest in the
          order given -- epics' first, then those only written down.
        """
        seen: dict[str, None] = {str(self.here): None}
        # Read afresh: another workspace's humanize, or another interface, may have written one.
        written = self._daemon.Hmz(self.here).settings.workspaces()
        for one in (*self.running(), *epics, *written):
            seen.setdefault(str(one), None)
        return list(seen)

    def close(self) -> None:
        """Lets go of every link, and of the runs held in this process where they are."""
        self._closed.set()
        with self._lock:
            places, self._places = list(self._places.values()), {}
        for place in places:
            if place.held is not None:
                place.held.close()
            if place.hosting is not None:
                place.hosting.close()

    def _linking(self, place: Place) -> Link:
        """A link to one workspace's runs, attached: through its host, or in this process."""
        daemon = self._daemon
        if self._apart:
            return daemon.attach("web", "browser", workspace=place.workspace)
        with self._lock:
            if place.hosting is None:
                place.hosting = place.hmz.host()
            hosting = place.hosting
        return daemon.linked(hosting, "browser", kind="web")

    def _looking(self) -> None:
        """Lets go of links nobody uses, and asks the daemon what runs, until closed."""
        while not self._closed.wait(_LOOKING):
            moment = time.monotonic()
            with self._lock:
                idle = [
                    one
                    for one in self._places.values()
                    if one.held is not None
                    and not one.streams
                    and moment - one.used > _IDLE
                    and (one.held.standing("run") or {}).get("state") in (None, "idle")
                ]
                for one in idle:
                    one.held, held = None, one.held
                    if held is not None:
                        threading.Thread(
                            target=held.close, daemon=True, name="hmz-web"
                        ).start()
            if self._apart:
                self._asks_the_daemon()

    def statuses(self) -> dict[str, dict[str, Any]]:
        """How the runs of every workspace held on this machine stand, attaching to none.

        Apart, what each host the daemon holds says of itself; otherwise, what the runs held
        in this process say, of each workspace a page has reached.

        Returns:
          Each host's status, by the whole path of its workspace.
        """
        said: dict[str, dict[str, Any]] = {}
        if not self._apart:
            with self._lock:
                hosts = [
                    (str(one.workspace), one.hosting)
                    for one in self._places.values()
                    if one.hosting is not None
                ]
            for workspace, hosting in hosts:
                with contextlib.suppress(Exception):
                    said[workspace] = hosting.status()
            return said
        with contextlib.suppress(Exception):
            for one in self._daemon.daemons():
                with contextlib.suppress(Exception):
                    said[str(Path(one.workspace).resolve())] = one.status()
        return said

    def _asks_the_daemon(self) -> None:
        """What the daemon says runs in each workspace no link here follows."""
        running = {
            workspace: {
                "state": status.get("state") or "idle",
                "run": status.get("run") or 0,
                "flow": status.get("flow") or "",
                **({"turn": status["turn"]} if "turn" in status else {}),
            }
            for workspace, status in self.statuses().items()
        }
        with self._lock:
            self._running = running


def _workspaces(asked: Asked) -> dict[str, Any]:
    places = asked.site.places
    return {"here": str(places.here), "workspaces": asked.site.runs.workspaces()}


def _keep(asked: Asked) -> dict[str, Any]:
    place = asked.site.places.of(asked.text("workspace"))
    place.hmz.settings.keeps()
    return {"kept": str(place.workspace)} | _workspaces(asked)


def _forget(asked: Asked) -> dict[str, Any]:
    place = asked.site.places.of(asked.text("workspace"), made=True)
    place.hmz.settings.forget()
    return _workspaces(asked)


#: What a page reads of the workspaces, and adds to them or takes from them.
ROUTES = routes(
    ("GET", "/api/workspaces", _workspaces),
    ("POST", "/api/workspaces", _keep),
    ("POST", "/api/workspaces/forget", _forget),
)

"""Every workspace on this machine, as the web interface serves them: one daemon, many places.

The terminal interface is about the directory it is opened in; the web interface is about the
machine, as the daemon is. It offers every workspace an epic was run in or that was set up or
written down here, and holds, per workspace, humanize for it and -- only while a page follows
its runs or acts on them -- a link to each host holding them: the workspace's own, and each
chat's beside it. A link nobody has used for a while,
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

    Each of its hosts is held by its slot: "" for the workspace's own, which runs its flows one
    at a time, and `chat:<hex>` for each chat's, beside it.

    Attributes:
      workspace: Its directory, resolved.
      hmz: humanize, for it.
      held: Each of its hosts' runs as this interface follows them, while it does.
      used: When a page last asked anything of each, on the monotonic clock.
      streams: How many pages follow each now.
      hosting: The runs held in this process, where they are not held apart.
    """

    workspace: Path
    hmz: Any
    held: dict[str, Held] = field(default_factory=dict[str, "Held"])
    used: dict[str, float] = field(default_factory=dict[str, float])
    streams: dict[str, int] = field(default_factory=dict[str, int])
    hosting: dict[str, Any] = field(default_factory=dict[str, Any])


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
        #: What the daemon last said runs, host by host, where nothing here holds it.
        self._running: list[dict[str, Any]] = []
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

    def held(self, workspace: str, slot: str = "", *, starts: bool = False) -> Held:
        """The runs of one of a workspace's hosts as this follows them, reaching them first.

        Reaching the workspace's own starts it where none is, as the terminal interface's
        opening there would: asked of only where a page follows its runs or acts on them. A
        chat's is started only to start its chat: one that has gone has folded away, and is
        carried on by a host of its own.

        Args:
          workspace: The workspace.
          slot: Which of its hosts: "" for its own, `chat:<hex>` for a chat's.
          starts: Whether a chat is being started there, which starts its host.

        Raises:
          Refusal: If there is no such directory, its runs cannot be reached, or the chat has
            folded away.
        """
        from .held import Held

        place = self.of(workspace)
        with self._lock:
            place.used[slot] = time.monotonic()
            there = place.held.get(slot)
            if there is not None and not (slot and there.gone):
                return there
            hosting = place.hosting.get(slot)
        if (
            slot
            and not starts
            and not (
                hosting is not None and not hosting.closed
                if not self._apart
                else self._daemon.running(place.workspace, slot=slot)
            )
        ):
            raise Refusal("This chat has folded away.", 409)
        try:
            held = Held(lambda: self._linking(place, slot), again=not slot)
        except Exception as why:
            older = getattr(self._daemon, "Older", None)
            if older is not None and isinstance(why, older):
                raise Refusal(str(why), 409) from why
            raise Refusal(
                f"The epics of {place.workspace} could not be reached: {why}", 503
            ) from why
        with self._lock:
            if place.held.get(slot) is there:
                place.held[slot] = held
                if there is not None:
                    threading.Thread(target=there.close, daemon=True).start()
                return held
        held.close()
        return place.held[slot]

    def attached(self, workspace: str, slot: str = "") -> Held | None:
        """The runs of one of a workspace's hosts as this follows them, where it does."""
        place = self.of(workspace, made=True)
        with self._lock:
            return place.held.get(slot)

    def stream(self, workspace: str, slot: str = "") -> Stream:
        """The runs of one of a workspace's hosts as a page follows them, counted while it does."""
        from .routing import Stream

        place = self.of(workspace)
        held = self.held(workspace, slot)
        inner = held.stream()

        def events(last: str, going: threading.Event) -> Iterator[Any]:
            with self._lock:
                place.streams[slot] = place.streams.get(slot, 0) + 1
            try:
                yield from inner.events(last, going)
            finally:
                with self._lock:
                    place.streams[slot] -= 1
                    place.used[slot] = time.monotonic()

        return Stream(events)

    def running(self) -> list[dict[str, Any]]:
        """What each host runs: the state, the run's number, its flow and its epic.

        And of a chat, its turn; and of every one, its `workspace` and its `slot`. Out of the
        links held here where there is one, and what the daemon last said of the rest; a host
        running nothing is left out.
        """
        with self._lock:
            said = {(one["workspace"], one["slot"]): one for one in self._running}
            held = [
                (str(one.workspace), slot, link)
                for one in self._places.values()
                for slot, link in one.held.items()
            ]
        for workspace, slot, one in held:
            run = one.standing("run")
            if run is not None:
                said[workspace, slot] = {**run, "workspace": workspace, "slot": slot}
        return [
            run for run in said.values() if run.get("state") in ("running", "stopping")
        ]

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
        running = [one["workspace"] for one in self.running()]
        for one in (*running, *epics, *written):
            seen.setdefault(str(one), None)
        return list(seen)

    def close(self) -> None:
        """Lets go of every link, and of the runs held in this process where they are."""
        self._closed.set()
        with self._lock:
            places, self._places = list(self._places.values()), {}
        for place in places:
            for held in place.held.values():
                held.close()
            for hosting in place.hosting.values():
                hosting.close()

    def _linking(self, place: Place, slot: str) -> Link:
        """A link to one of a workspace's hosts, attached: apart, or in this process."""
        daemon = self._daemon
        if self._apart:
            return daemon.attach("web", "browser", workspace=place.workspace, slot=slot)
        with self._lock:
            hosting = place.hosting.get(slot)
            if hosting is None:
                hosting = place.hosting[slot] = place.hmz.host(slot)
        return daemon.linked(hosting, "browser", kind="web")

    def _looking(self) -> None:
        """Lets go of links nobody uses, and asks the daemon what runs, until closed."""
        while not self._closed.wait(_LOOKING):
            moment = time.monotonic()
            with self._lock:
                for one in self._places.values():
                    for slot, held in list(one.held.items()):
                        run = held.standing("run") or {}
                        # A chat between turns is let go of too: nobody reading it is what
                        # folds it away.
                        resting = run.get("state") in (None, "idle") or (
                            bool(slot) and run.get("turn") == "done"
                        )
                        if not (slot and held.gone) and (
                            one.streams.get(slot, 0)
                            or moment - one.used.get(slot, moment) <= _IDLE
                            or not resting
                        ):
                            continue
                        del one.held[slot]
                        threading.Thread(
                            target=held.close, daemon=True, name="hmz-web"
                        ).start()
                    # A chat's runs held here, folded away and read by nobody, are let go of
                    # as its host process would go.
                    for slot, hosting in list(one.hosting.items()):
                        if slot and slot not in one.held and hosting.idle:
                            del one.hosting[slot]
                            threading.Thread(
                                target=hosting.close, daemon=True, name="hmz-web"
                            ).start()
            if self._apart:
                self._asks_the_daemon()

    def statuses(self) -> dict[str, dict[str, Any]]:
        """How the runs of every host on this machine stand, attaching to none.

        Apart, what each host the daemon holds says of itself; otherwise, what the runs held
        in this process say, of each workspace a page has reached.

        Returns:
          Each host's status with its `workspace`, its whole path, by workspace and slot.
        """
        said: dict[str, dict[str, Any]] = {}
        if not self._apart:
            with self._lock:
                hosts = [
                    (str(one.workspace), slot, hosting)
                    for one in self._places.values()
                    for slot, hosting in one.hosting.items()
                ]
            for workspace, slot, hosting in hosts:
                with contextlib.suppress(Exception):
                    said[f"{workspace}\0{slot}"] = {
                        **hosting.status(),
                        "workspace": workspace,
                    }
            return said
        with contextlib.suppress(Exception):
            for one in self._daemon.daemons():
                with contextlib.suppress(Exception):
                    workspace = str(Path(one.workspace).resolve())
                    said[f"{workspace}\0{one.slot}"] = {
                        **one.status(),
                        "workspace": workspace,
                        "slot": one.slot,
                    }
        return said

    def _asks_the_daemon(self) -> None:
        """What the daemon says runs in each host no link here follows."""
        running = [
            {
                "state": status.get("state") or "idle",
                "run": status.get("run") or 0,
                "flow": status.get("flow") or "",
                "epic": status.get("epic") or "",
                "task": status.get("task") or "",
                "workspace": status["workspace"],
                "slot": status.get("slot") or "",
                **({"turn": status["turn"]} if "turn" in status else {}),
            }
            for status in self.statuses().values()
        ]
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

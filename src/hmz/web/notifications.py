"""Notifications: what every daemon's notices come to, on this machine's interface alone.

Each `hmz web` serves its own machine's notices -- an epic ended, a chat's turn done, a flow
asking a person or waiting for what to say next. The interface a person has open is told them
of every daemon at once: this machine's as they are heard, and each SSH daemon's, while it is
reached, off the stream its own interface serves. Each is told by which daemon said it, kept
only where the kinds a person wants to be told of say so, and kept a while -- the last few
hundred -- with whether it was read, for every page this interface serves to follow from where
it last heard.

Which kinds are told, and whether the system is asked to show them too, are the app's own
settings, kept under `notifications` in this machine's `settings.yaml` and never a daemon's.
"""

from __future__ import annotations

import collections
import contextlib
import http.client
import json
import threading
import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, cast

from .routing import Refusal, Stream, routes

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from .routing import Asked

__all__ = ["KINDS", "ROUTES", "Notifications", "daemons", "preferences"]

#: Every kind of notice there is: an epic or a chat's turn done, an epic failed or stopped, a
#: person asked, and a flow listening for what to say next.
KINDS = ("done", "failed", "stopped", "asked", "listening")

#: How many notifications are kept.
_KEPT = 200

#: How often the daemons there are, and which are reached, are looked at again.
_LOOKING = 2.0

#: How long a stream says nothing before it says it is still there.
_QUIET = 15.0

#: How long a daemon's interface may say nothing before its stream is given up on: it says it is
#: still there more often than this.
_SILENT = 60.0


def preferences(held: dict[str, Any] | None = None) -> dict[str, Any]:
    """Which notifications are wanted, as `settings.yaml` holds them: every one, where it is silent.

    Args:
      held: Everything `settings.yaml` holds; read afresh where None.

    Returns:
      `kinds`, whether each kind is told, and `system`, whether the system is asked to show
      them too.
    """
    if held is None:
        from hmz.coganchor import settings

        held = settings.read()
    said: object = held.get("notifications")
    wanted = cast("dict[str, Any]", said) if isinstance(said, dict) else {}
    kinds: object = wanted.get("kinds")
    each = cast("dict[str, Any]", kinds) if isinstance(kinds, dict) else {}
    return {
        "kinds": {kind: each.get(kind) is not False for kind in KINDS},
        "system": wanted.get("system") is not False,
    }


def daemons(held: dict[str, Any] | None = None) -> list[str]:
    """The name of every SSH daemon `settings.yaml` holds, as it holds them.

    Args:
      held: Everything `settings.yaml` holds; read afresh where None.
    """
    if held is None:
        from hmz.coganchor import settings

        held = settings.read()
    said: object = held.get("daemons")
    entries = cast("list[object]", said) if isinstance(said, list) else []
    named = [
        cast("dict[str, Any]", one).get("name")
        for one in entries
        if isinstance(one, dict)
    ]
    return [str(one) for one in named if one and one != "local"]


class Notifications:
    """Every daemon's notices, as this machine's interface tells them.

    Hears this machine's own as they come, and follows each SSH daemon's while it is reached:
    the notices held as `site.notices` and the daemons reached through `site.remotes`, each
    looked for again as long as it is missing.

    Args:
      site: What holds this machine's notices and the daemons reached, where it has them.
      wanted: Which notifications are wanted, asked afresh of every notice.
      named: The SSH daemons there are, asked afresh every little while.
    """

    def __init__(
        self,
        site: Any,
        *,
        wanted: Callable[[], dict[str, Any]] = preferences,
        named: Callable[[], list[str]] = daemons,
    ) -> None:
        self._site = site
        self._wanted = wanted
        self._named = named
        self._changed = threading.Condition()
        self._kept: collections.deque[dict[str, Any]] = collections.deque(maxlen=_KEPT)
        self._told = 0
        self._closed = threading.Event()
        self._hearing: object = None
        #: Each daemon followed, by name: the connection its stream comes over, once there is one.
        self._following: dict[str, list[http.client.HTTPConnection]] = {}
        #: The last notice heard of each daemon, by name: where its stream is taken up again.
        self._last: dict[str, str] = {}
        self._hears()
        threading.Thread(
            target=self._looks, daemon=True, name="hmz-web-notifications"
        ).start()

    def told(self, daemon: str, notice: dict[str, Any]) -> dict[str, Any] | None:
        """Keeps one daemon's notice as a notification, where its kind is wanted.

        Args:
          daemon: Which said it: `local`, or an SSH daemon's name.
          notice: The notice, as its daemon serves it.

        Returns:
          The notification, or None where its kind is not wanted.
        """
        if not self._wanted()["kinds"].get(str(notice.get("kind")), True):
            return None
        with self._changed:
            self._told += 1
            made = notice | {"id": str(self._told), "daemon": daemon, "read": False}
            self._kept.append(made)
            self._changed.notify_all()
        return dict(made)

    def listed(self) -> dict[str, Any]:
        """Every notification kept, newest first, and how many are unread."""
        with self._changed:
            items = [dict(one) for one in reversed(self._kept)]
        return {"items": items, "unread": sum(not one["read"] for one in items)}

    def read(self, ids: list[str] | None = None) -> dict[str, Any]:
        """Marks notifications read: those named, or every one where none are.

        Returns:
          As `listed`.
        """
        with self._changed:
            for one in self._kept:
                if ids is None or one["id"] in ids:
                    one["read"] = True
        return self.listed()

    def clear(self) -> dict[str, Any]:
        """Forgets every notification kept.

        Returns:
          As `listed`.
        """
        with self._changed:
            self._kept.clear()
        return self.listed()

    def stream(self) -> Stream:
        """Every notification after the one a page last heard, then each as it comes."""
        return Stream(self._events)

    def close(self) -> None:
        """Stops following every daemon, and ends every stream."""
        self._closed.set()
        with self._changed:
            following = [one for held in self._following.values() for one in held]
            self._changed.notify_all()
        for connection in following:
            with contextlib.suppress(OSError):
                connection.close()

    def _events(
        self, last: str, going: threading.Event
    ) -> Iterator[tuple[str, str, Any] | None]:
        with self._changed:
            told = self._told
        # One heard of an interface before this, which counted from the start again, has
        # heard none of this one's. Where it starts from is as it is asked for, not as it is
        # first read.
        heard = int(last) if last.isdigit() else told
        return self._after(heard if heard <= told else 0, going)

    def _after(
        self, after: int, going: threading.Event
    ) -> Iterator[tuple[str, str, Any] | None]:
        while not (going.is_set() or self._closed.is_set()):
            with self._changed:
                fresh = [dict(one) for one in self._kept if int(one["id"]) > after]
                if not fresh:
                    self._changed.wait(_QUIET)
                    fresh = [dict(one) for one in self._kept if int(one["id"]) > after]
            if not fresh:
                yield None
                continue
            for one in fresh:
                after = int(one["id"])
                yield one["id"], "notification", one

    def _hears(self) -> None:
        """Hears this machine's own notices, once there are any to hear."""
        notices = getattr(self._site, "notices", None)
        if notices is None or self._hearing is notices:
            return
        self._hearing = notices
        notices.heard(self._heard)

    def _heard(self, said: dict[str, Any] | list[dict[str, Any]]) -> None:
        for notice in said if isinstance(said, list) else [said]:
            self.told("local", notice)

    def _looks(self) -> None:
        """Every little while: this machine's notices, and every SSH daemon reached, followed."""
        while not self._closed.wait(_LOOKING):
            # Whatever went wrong is looked at again in a while.
            with contextlib.suppress(Exception):
                self._hears()
                self._reaches(getattr(self._site, "remotes", None))

    def _reaches(self, remotes: Any) -> None:
        """Follows every SSH daemon reached that is not followed yet."""
        if remotes is None:
            return
        for name in self._named():
            if name in self._following or remotes.state(name).get("state") != "up":
                continue
            with self._changed:
                self._following[name] = []
            threading.Thread(
                target=self._follows,
                args=(remotes, name),
                daemon=True,
                name=f"hmz-web-notices-{name}",
            ).start()

    def _follows(self, remotes: Any, name: str) -> None:
        """Follows one daemon's notices while it is reached, from where it was last heard."""
        try:
            port, key = remotes.reached(name)
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=_SILENT)
            with self._changed:
                if self._closed.is_set():
                    return
                self._following[name].append(connection)
            cookie = _signs_in(connection, key)
            # What it said before it was first reached was said to nobody here, and is not
            # told; one started again since it was last heard counts from the start again.
            now = str(_asks(connection, cookie, "/api/notices")["last"])
            heard = self._last.get(name)
            if heard is None or (
                heard.isdigit() and now.isdigit() and int(heard) > int(now)
            ):
                self._last[name] = now if heard is None else "0"
            connection.request(
                "GET",
                "/api/notices/stream",
                headers={"Cookie": cookie, "Last-Event-ID": self._last[name]},
            )
            answer = connection.getresponse()
            if answer.status != HTTPStatus.OK:
                return
            event, ident, data = "", "", list[str]()
            while not self._closed.is_set():
                line = answer.readline()
                if not line:
                    return
                said = line.decode().rstrip("\r\n")
                if said.startswith("id:"):
                    ident = said[3:].strip()
                elif said.startswith("event:"):
                    event = said[6:].strip()
                elif said.startswith("data:"):
                    data.append(said[5:].removeprefix(" "))
                elif not said:
                    if event == "notice" and data:
                        notice = json.loads("\n".join(data))
                        self._last[name] = ident or str(notice.get("id", ""))
                        self.told(name, notice)
                    event, ident, data = "", "", list[str]()
        except Exception:  # noqa: BLE001 -- followed again once it is reached again
            time.sleep(_LOOKING)
        finally:
            with self._changed:
                for connection in self._following.pop(name, []):
                    with contextlib.suppress(OSError):
                        connection.close()


def _signs_in(connection: http.client.HTTPConnection, key: str) -> str:
    """Lets this in to a daemon's interface with its key, as a browser is let in.

    Returns:
      The cookie it is handed, named for the port that interface listens on there.

    Raises:
      OSError: If it would not let this in.
    """
    connection.request("GET", f"/?key={key}")
    answer = connection.getresponse()
    answer.read()
    cookie = (answer.getheader("Set-Cookie") or "").partition(";")[0]
    if not cookie:
        raise OSError(f"the daemon's interface would not let this in: {answer.status}")
    return cookie


def _asks(
    connection: http.client.HTTPConnection, cookie: str, path: str
) -> dict[str, Any]:
    """What a daemon's interface answers one read with."""
    connection.request("GET", path, headers={"Cookie": cookie})
    answer = connection.getresponse()
    body = answer.read()
    if answer.status != HTTPStatus.OK:
        raise OSError(f"the daemon's interface answered {answer.status}")
    return cast("dict[str, Any]", json.loads(body))


def _held(asked: Asked) -> Notifications:
    held = getattr(asked.site, "notifications", None)
    if held is None:
        raise Refusal("Notifications are not kept here.", 404)
    return cast("Notifications", held)


def _read(asked: Asked) -> dict[str, Any]:
    if asked.body.get("all") is True:
        return _held(asked).read()
    said: object = asked.body.get("ids")
    if not isinstance(said, list) or not all(
        isinstance(one, str | int) and not isinstance(one, bool)
        for one in cast("list[object]", said)
    ):
        raise Refusal("Say ids as a list, or all as true.")
    return _held(asked).read([str(one) for one in cast("list[object]", said)])


def _prefers(asked: Asked) -> dict[str, Any]:
    said = asked.body
    if extra := sorted(set(said) - {"kinds", "system"}):
        raise Refusal(f"Notifications take no {', '.join(extra)}.")
    if not isinstance(said.get("kinds", {}), dict):
        raise Refusal("kinds is whether each kind is told, by name.")
    kinds = asked.named("kinds")
    if extra := sorted(set(kinds) - set(KINDS)):
        raise Refusal(f"There is no kind {', '.join(extra)}.")
    if not all(isinstance(one, bool) for one in kinds.values()):
        raise Refusal("Each kind is true or false.")
    if "system" in said and not isinstance(said["system"], bool):
        raise Refusal("system is true or false.")

    def change(held: dict[str, Any]) -> None:
        now = preferences(held)
        now["kinds"] |= kinds
        if "system" in said:
            now["system"] = said["system"]
        held["notifications"] = now

    from hmz.coganchor import settings

    try:
        return preferences(settings.changes(change))
    except OSError as why:
        raise Refusal(f"The settings cannot be written: {why}", 409) from why


#: What a page reads of the notifications, and does to them.
ROUTES = routes(
    ("GET", "/api/notifications", lambda asked: _held(asked).listed()),
    ("GET", "/api/notifications/stream", lambda asked: _held(asked).stream()),
    ("POST", "/api/notifications/read", _read),
    ("POST", "/api/notifications/clear", lambda asked: _held(asked).clear()),
    ("GET", "/api/notifications/settings", lambda _: preferences()),
    ("POST", "/api/notifications/settings", _prefers),
)

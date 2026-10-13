"""What happened to the runs of this machine worth telling somebody about, as notices.

An epic ending, a question for a person, a chat's turn done: each is a notice,
worked out of how every workspace's runs stand -- asked of each host every couple of seconds,
as a frontend asks what runs, and never by attaching to it, which would keep a host that would
otherwise go. What stood when this started is where it starts from rather than news. The last
few are kept, each numbered after the one before and after any this machine numbered before it
was started again, so that a page -- or another machine's interface -- carries on from the last
one it heard.

Written once here rather than in each way in: the web interface and the terminal interface tell
of the same runs, and which kinds a person wants told -- kept under `notifications` in this
machine's `settings.yaml` -- is one answer for both.
"""

from __future__ import annotations

import collections
import contextlib
import threading
import time
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

__all__ = ["KINDS", "Notices", "prefer", "preferences"]

#: Every kind of notice there is: an epic or a chat's turn done, an epic failed or stopped, a
#: person asked, and a flow listening for what to say next.
KINDS = ("done", "failed", "stopped", "asked", "listening")

#: How often how the runs stand is asked, in seconds.
_EVERY = 2.0

#: How many notices are kept.
_KEPT = 200

#: How long a stream says nothing before it says it is still there, in seconds.
_QUIET = 15.0

#: The kind of notice each way an epic can end is.
_ENDED = {
    "done": "done",
    "stopped": "stopped",
    "failed": "failed",
    "crashed": "failed",
    "budget": "failed",
    "refused": "failed",
}

#: The kind of notice a question waited on is, by its mode.
_ASKED = {"ask": "asked", "listen": "listening"}


class Notices:
    """The notices of this machine's runs, worked out of how they stand as that changes.

    Args:
      statuses: How the runs of each host stand -- a workspace's own and each chat's beside
        it -- as its `status` says, with its `workspace`: by anything that tells the hosts
        apart, asked once a look, and never of a host it would keep.
      every: How often to look once started, in seconds.
    """

    def __init__(
        self,
        statuses: Callable[[], dict[str, dict[str, Any]]],
        *,
        every: float = _EVERY,
    ) -> None:
        self._statuses = statuses
        self._every = every
        self._changed = threading.Condition()
        self._kept: collections.deque[dict[str, Any]] = collections.deque(maxlen=_KEPT)
        self._last = 0
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        #: How each host last stood, where it said: what is news is against this.
        self._stood: dict[str, dict[str, Any]] | None = None
        #: When it first looked: an epic that ended before then is no news, wherever it is.
        self._began = 0.0
        self._closed = threading.Event()

    @property
    def last(self) -> int:
        """The id of the newest notice, or 0 where there is none."""
        with self._changed:
            return self._last

    def start(self) -> None:
        """Looks every so often, on a thread of its own, until closed."""
        threading.Thread(target=self._looking, daemon=True, name="hmz-notices").start()

    def look(self) -> list[dict[str, Any]]:
        """Asks how the runs stand, once, and tells what is new since the last look.

        The first look is where it starts from: nothing that stood then is news.

        Returns:
          The notices that look made, oldest first.
        """
        statuses = self._statuses()
        made: list[dict[str, Any]] = []
        with self._changed:
            first = self._stood is None
            if first:
                self._began = time.time()
            stood = self._stood if self._stood is not None else {}
            for key, status in statuses.items():
                # A host that would not answer says neither: unknown, rather than nothing.
                if "pending" not in status or "ended" not in status:
                    continue
                if not first:
                    was = stood.get(key, {})
                    workspace = str(status.get("workspace") or key)
                    made += _noticed(workspace, was, status, self._began)
                stood[key] = {
                    # Which host it was, apart: another one numbers its questions afresh.
                    "host": (status.get("pid"), status.get("started")),
                    "ended": status.get("ended"),
                    "pending": list(status.get("pending") or []),
                    "turn": status.get("turn"),
                }
            self._stood = stood
            for one in made:
                self._last = one["id"] = max(self._last + 1, int(time.time() * 1000))
                self._kept.append(one)
            if made:
                self._changed.notify_all()
            listeners = list(self._listeners)
        for one in made:
            for listener in listeners:
                with contextlib.suppress(Exception):
                    listener(dict(one))
        return made

    def since(self, after: int | str = 0) -> list[dict[str, Any]]:
        """The notices kept after one, oldest first.

        Args:
          after: The id of the last one heard, or 0 for every one kept.

        Raises:
          ValueError: If `after` is not a whole number.
        """
        heard = int(after or 0)
        with self._changed:
            return [dict(one) for one in self._kept if one["id"] > heard]

    def heard(self, listener: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        """Tells a listener each notice as it is made, on the thread that looks.

        Args:
          listener: Told each notice; what it raises is not this one's.

        Returns:
          What stops telling it.
        """
        with self._changed:
            self._listeners.append(listener)

        def unheard() -> None:
            with self._changed, contextlib.suppress(ValueError):
                self._listeners.remove(listener)

        return unheard

    def close(self) -> None:
        """Stops looking, and ends every stream."""
        self._closed.set()
        with self._changed:
            self._changed.notify_all()

    def events(
        self, last: str, going: threading.Event
    ) -> Iterator[tuple[str, str, Any] | None]:
        """Every notice after the last one heard, then each as it comes, as server-sent events.

        Args:
          last: The id of the last one heard, or "" for none: then only those made from now on.
          going: Set once whoever hears them has gone.

        Yields:
          Each one's id, `notice` and the notice; or None after a while of nothing, to say it
          is still there.
        """
        # Where it starts from is as it is asked for, not as it is first read.
        return self._after(int(last) if last.isdigit() else self.last, going)

    def _after(
        self, after: int, going: threading.Event
    ) -> Iterator[tuple[str, str, Any] | None]:
        while not (going.is_set() or self._closed.is_set()):
            with self._changed:
                fresh = [one for one in self._kept if one["id"] > after]
                if not fresh:
                    self._changed.wait(_QUIET)
                    fresh = [one for one in self._kept if one["id"] > after]
            if not fresh:
                yield None
                continue
            for one in fresh:
                after = one["id"]
                yield str(after), "notice", dict(one)

    def _looking(self) -> None:
        while True:
            with contextlib.suppress(Exception):
                self.look()
            if self._closed.wait(self._every):
                return


def _noticed(
    workspace: str, was: dict[str, Any], now: dict[str, Any], began: float
) -> list[dict[str, Any]]:
    """What is news in how one workspace's runs stand now against how they stood.

    Args:
      workspace: Whose runs.
      was: How they last stood, or nothing where they were not seen before.
      now: How they stand now.
      began: When the first look was: an epic that ended before is no news.
    """
    made: list[dict[str, Any]] = []
    ended = now.get("ended")
    # A host says the turn of a chat alone, and of the run it shows: the one going, or the last.
    chat = "turn" in now
    if ended and ended != was.get("ended") and float(ended.get("at") or began) >= began:
        why = str(ended.get("why") or "").strip()
        kind = _ENDED.get(str(ended.get("how")), "failed")
        # A chat left is no news, nor one whose last turn was told done already.
        left = kind == "stopped" or (kind == "done" and was.get("turn") == "done")
        if not (chat and now.get("run") == ended.get("run") and left):
            made.append(
                {
                    "kind": kind,
                    "workspace": workspace,
                    "slot": now.get("slot") or "",
                    "epic": ended.get("epic") or "",
                    "flow": ended.get("flow") or now.get("flow") or "",
                    "task": ended.get("task") or now.get("task") or "",
                    "role": "",
                    # Why in a line: of a crash, the last of its traceback.
                    "text": why.splitlines()[-1] if why else "",
                    "at": ended.get("at") or time.time(),
                }
            )
    same = was.get("host") == (now.get("pid"), now.get("started"))
    stood: list[dict[str, Any]] = (was.get("pending") or []) if same else []
    pending: list[dict[str, Any]] = now.get("pending") or []
    asked = {one.get("question") for one in stood}
    for one in pending:
        kind = _ASKED.get(one.get("mode", ""))
        if kind is None or one.get("question") in asked:
            continue
        made.append(
            {
                # A chat asking what to say next is its turn done.
                "kind": "done" if chat and kind == "listening" else kind,
                "workspace": workspace,
                "slot": now.get("slot") or "",
                "epic": now.get("epic") or "",
                "flow": now.get("flow") or "",
                "task": now.get("task") or "",
                "role": one.get("role") or "",
                "text": one.get("text") or "",
                "at": time.time(),
            }
        )
    return made


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


def prefer(
    kinds: dict[str, bool] | None = None, *, system: bool | None = None
) -> dict[str, Any]:
    """Writes which notifications are wanted into `settings.yaml`, leaving the rest as it was.

    Args:
      kinds: Whether each kind named is told; the kinds not named are left as they are.
      system: Whether the system is asked to show them too, or None to leave it.

    Returns:
      As `preferences`, once written.

    Raises:
      OSError: If the settings cannot be written.
    """

    def change(held: dict[str, Any]) -> None:
        now = preferences(held)
        now["kinds"] |= kinds or {}
        if system is not None:
            now["system"] = system
        held["notifications"] = now

    from hmz.coganchor import settings

    return preferences(settings.changes(change))

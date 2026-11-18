"""`notices.*`: what happened to the epics of the daemon's machine worth telling somebody about.

The notices are worked out of how each host stands (:mod:`hmz.runtime.watching.notices`),
asked of every host every couple of seconds and never by attaching to it -- and, of a host
that went in between, as it said it stood as it went -- from the moment they are first
watched: :func:`watched`, which the daemon calls as it starts. A client reads those kept, or
subscribes and is sent each as `notices.event` `{sub, notice}`, after every one kept past the
id it last heard where it says one. Which kinds a person is told of is the client's to choose:
every one is sent.

A subscription ends with `notices.unsubscribe`, or with its session: the thread sending it reads
the session closed when a notice will not go, or at the latest when it next wakes with nothing
to send.
"""

from __future__ import annotations

import itertools
import threading
from typing import TYPE_CHECKING, Any
from weakref import WeakKeyDictionary

from hmz.daemon import reach
from hmz.rpc import Closed, Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

    from hmz.rpc import Call, Handler, Peer
    from hmz.runtime.watching.notices import Notices

__all__ = ["METHODS", "listed", "watched"]

#: The notices of this machine, once they are watched.
_held: Notices | None = None

#: Guards what follows, and the notices being made.
_lock = threading.Lock()

#: Each session's notices subscriptions, by `sub`, forgotten with the session.
_subs: WeakKeyDictionary[Peer, dict[str, _Sub]] = WeakKeyDictionary()

#: What tells the subscriptions of a session apart from one another.
_count = itertools.count(1)


class _Sub:
    """One subscription: whether it has ended, and what one notice going out holds."""

    def __init__(self) -> None:
        self.ended = threading.Event()
        #: Held while a notice goes out, so that none goes once it has ended.
        self.sending = threading.Lock()


def watched() -> Notices:
    """The notices of this machine, watched from the first time this is called.

    Returns:
      The one :class:`~hmz.runtime.watching.notices.Notices` there is in this process.
    """
    global _held  # noqa: PLW0603 -- one per daemon, from the moment it is first asked for
    with _lock:
        if _held is None:
            from hmz.runtime.watching.notices import Notices

            from .workspaces import left, statuses

            # A host that went since the last look says how it stood as it went, over what
            # it said while it was up: an `hmz exec`'s goes right after its epic ends.
            _held = Notices(lambda: {**statuses(), **left()})
            _held.start()
        return _held


def listed(notices: Notices, after: int | str = 0) -> dict[str, Any]:
    """The notices kept after one, oldest first, and the newest id.

    Args:
      notices: Whose.
      after: The id of the last one heard, or 0 for every one kept.

    Raises:
      RpcError: 400, if `after` is not a whole number.
    """
    try:
        heard = int(after or 0)
    except ValueError:
        heard = -1
    if heard < 0:
        raise RpcError(Code.REFUSED, "Say after as a whole number.")
    return {"notices": notices.since(heard), "last": notices.last}


def _list(call: Call) -> dict[str, Any]:
    return listed(watched(), call.params.get("after", 0))


def _subscribe(call: Call) -> dict[str, Any]:
    after: int | None = call.params.get("after")
    if after is not None and after < 0:
        raise RpcError(Code.REFUSED, "Say after as a whole number.")
    notices = watched()
    last = notices.last
    sub, held = f"notices-{next(_count)}", _Sub()
    with _lock:
        _subs.setdefault(call.peer, {})[sub] = held
    answer = {"sub": sub, "last": last}
    # Answered before the first notice is sent, which names a `sub` the client has been told.
    call.answer(answer)
    events = notices.events(str(last if after is None else after), held.ended)
    threading.Thread(
        target=_sends,
        args=(call.peer, sub, held, events, reach.notices()),
        name=f"hmz-{sub}",
        daemon=True,
    ).start()
    return answer


def _sends(
    peer: Peer,
    sub: str,
    held: _Sub,
    events: Iterator[tuple[str, str, Any] | None],
    kept: Callable[[Mapping[str, Any]], bool] | None = None,
) -> None:
    """Sends each notice to one subscription, until it ends or its session closes.

    Those of a host Ai-chan's reach does not reach, where `kept` is it, are not sent.
    """
    try:
        for one in events:
            if peer.closed:
                return
            if one is None or (kept is not None and not kept(one[2])):
                continue
            with held.sending:
                if held.ended.is_set():
                    return
                peer.notify("notices.event", {"sub": sub, "notice": one[2]})
    except Closed:
        return
    finally:
        held.ended.set()
        with _lock:
            _subs.get(peer, {}).pop(sub, None)


def _unsubscribe(call: Call) -> dict[str, Any]:
    sub: str = call.params["sub"]
    with _lock:
        held = _subs.get(call.peer, {}).pop(sub, None)
    if held is None:
        raise RpcError(Code.UNKNOWN_SUBSCRIPTION, f"There is no subscription {sub}.")
    with held.sending:
        held.ended.set()
    return {}


#: Each method of the family, by name.
METHODS: Mapping[str, Handler] = {
    "notices.list": _list,
    "notices.subscribe": _subscribe,
    "notices.unsubscribe": _unsubscribe,
}

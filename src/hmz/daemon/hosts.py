"""The hosts this machine's daemon holds, and the epic subscriptions attached to them.

Each host is a process of its own, standing in its workspace (Section 4.13.2 of daemon.md),
started here with one end of a socket pair and reached down it alone (:mod:`hmz.daemon.carrying`
says what goes over it). A client never reaches a host: its session ends at the daemon, and each
epic subscription it opens is one frontend the daemon attaches to the host for it, whose
messages come back up the link tagged with the subscription and go out to the session as
`epic.event`. Two calls needing a host of one slot of one workspace at once take on one.
"""

from __future__ import annotations

import contextlib
import itertools
import socket
import threading
import time
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any

from hmz.daemon import where

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.daemon.sessions import Session
    from hmz.rpc import Call, Peer

__all__ = ["Hosted", "Hosts", "Subscription"]

#: How long a host is given to come up.
_PATIENCE = 10.0

#: How long a host is given to say how it stands before it is answered for.
_ANSWERING = 5.0

#: How often a subscription that asked for figures has them worked out again, at most.
_FIGURING = 1.0

#: Why a subscription ends whose host process ended without closing.
WENT_AWAY = "the host went away"


class Subscription:
    """One epic subscription: one frontend the daemon attached to a host for one session.

    What the host tells it waits until the subscription has been answered with its `sub`,
    so that a client never hears of a `sub` before it knows it.

    Attributes:
      session: The session it belongs to.
      sub: Its name in that session.
      hosted: The host it is attached to.
      tag: What the host's link names it by.
      client: Its client id, once the host gave one.
    """

    def __init__(
        self, session: Session, sub: str, hosted: Hosted, *, figures: bool
    ) -> None:
        self.session = session
        self.sub = sub
        self.hosted = hosted
        self.tag = f"{id(session):x}/{sub}"
        self.client = ""
        self._lock = threading.RLock()
        self._open = False
        self._held: list[dict[str, Any]] = []
        self._gone = False
        self._following: Any = None
        if figures:
            from hmz.runtime.watching.following import Following

            self._following = Following()

    @property
    def gone(self) -> bool:
        """Whether it has ended."""
        with self._lock:
            return self._gone

    def opened(self) -> None:
        """Sends what the host told it so far, now that it has been answered with its `sub`."""
        with self._lock:
            self._open = True
            held, self._held = self._held, []
            for message in held:
                self._sends(message)
        if self._following is not None and not self.gone:
            threading.Thread(
                target=self._figuring, daemon=True, name="hmz-figures"
            ).start()

    def told(self, message: dict[str, Any]) -> None:
        """Takes one message the host told this frontend."""
        with self._lock:
            if self._gone:
                return
            if self._following is not None:
                _follows(self._following, message)
            if not self._open:
                self._held.append(message)
                return
            self._sends(message)

    def _sends(self, message: dict[str, Any]) -> None:
        """Sends one message, under the lock; `gone` ends the subscription."""
        if self._gone:
            return
        self.session.tell("epic.event", {"sub": self.sub, "message": message})
        if message.get("type") == "gone":
            self._ends()

    def end(self, why: str, *, detaching: bool = True) -> None:
        """Ends it, telling the session why, and lets the host's frontend go.

        Args:
          why: What `gone` says.
          detaching: Whether the host is still to be told to let its frontend go.
        """
        with self._lock:
            if self._gone:
                return
            self._open = True
            self._sends({"type": "gone", "why": why})
        if detaching and self.client:
            self.hosted.detach(self.client)

    def dropped(self) -> None:
        """Ends it silently, its session gone, and lets the host's frontend go."""
        with self._lock:
            if self._gone:
                return
            self._ends()
        if self.client:
            self.hosted.detach(self.client)

    def _ends(self) -> None:
        """Takes it off its session and its host. Under the lock."""
        self._gone = True
        with self.session.lock:
            if self.session.subs.get(self.sub) is self:
                del self.session.subs[self.sub]
        self.hosted.forget(self)
        if self._following is not None:
            with contextlib.suppress(Exception):
                self._following.close()

    def _figuring(self) -> None:
        """Sends the figures of the epic as they change, at most once a second."""
        last: dict[str, Any] | None = None
        while not self.gone:
            following = self._following
            if following is not None and following.run:
                with contextlib.suppress(Exception):
                    figures = {"type": "figures", **_figures(following)}
                    if figures != last:
                        last = figures
                        with self._lock:
                            self._sends(figures)
            time.sleep(_FIGURING)


class Hosted:
    """One host the daemon took on, reached down its link.

    Attributes:
      workspace: Its workspace.
      slot: Its slot.
      said: What it said of itself: `pid`, `workspace`, `started`, `slot`, `kind`, `protocol`.
      peer: The daemon's end of its link.
    """

    def __init__(self, workspace: str, slot: str) -> None:
        self.workspace = workspace
        self.slot = slot
        self.said: dict[str, Any] = {}
        self.peer: Peer | None = None
        self._lock = threading.Lock()
        self._subs: dict[str, Subscription] = {}

    @property
    def listed(self) -> dict[str, Any]:
        """Its entry in `hosts.list`."""
        return {
            key: self.said.get(key) for key in ("pid", "workspace", "started", "slot")
        }

    @property
    def keys(self) -> dict[str, Any]:
        """Its host-process keys (Section 4.6.4.2 of daemon.md)."""
        return {
            key: self.said.get(key)
            for key in ("pid", "workspace", "started", "kind", "protocol")
        }

    def told(self, call: Call) -> None:
        """Takes one message the host sent up the link, for the subscription it names."""
        if call.method != "told":
            return
        with self._lock:
            sub = self._subs.get(str(call.params.get("tag")))
        message = call.params.get("message")
        if sub is not None and isinstance(message, dict):
            sub.told(message)  # pyright: ignore[reportUnknownArgumentType]

    def attach(
        self,
        sub: Subscription,
        *,
        replay: bool,
        since: dict[str, Any] | None,
    ) -> str:
        """Attaches one frontend for a subscription, and answers its client id.

        Raises:
          RpcError: 409, as the host refused it.
        """
        with self._lock:
            self._subs[sub.tag] = sub
        try:
            said = self._call(
                "attach",
                {
                    "tag": sub.tag,
                    "name": sub.session.name or f"{_user()}@{sub.session.kind}",
                    "kind": sub.session.kind,
                    "replay": replay,
                    "since": since,
                },
            )
        except BaseException:
            self.forget(sub)
            raise
        return str(said["client"])

    def ask(self, client: str, said: dict[str, Any]) -> dict[str, Any]:
        """Asks the host what one frontend asked, as it answers it: `ok`, and `why` where not.

        Raises:
          RpcError: 409, where the host could not be asked.
        """
        answer: Any = self._call("ask", {"client": client, "said": said})
        return answer if isinstance(answer, dict) else {"ok": False, "why": "no answer"}  # pyright: ignore[reportUnknownVariableType]

    def detach(self, client: str) -> None:
        """Lets one frontend go, without waiting on the host."""
        threading.Thread(
            target=self._quietly, args=("detach", {"client": client}), daemon=True
        ).start()

    def status(self) -> dict[str, Any]:
        """How the host stands, or what is known of it without asking where it will not say."""
        try:
            said: Any = self._call("status", {}, timeout=_ANSWERING)
        except Exception:  # noqa: BLE001 -- a host that will not say is answered for
            said = None
        if isinstance(said, dict):
            return said  # pyright: ignore[reportUnknownVariableType]
        return {**self.keys, "slot": self.slot, "attached": 0, "flows": [], "calls": []}

    def detach_all(self) -> int:
        """Lets every frontend go, and answers how many."""
        said: Any = self._call("detach_all", {}, timeout=_ANSWERING)
        return int(said.get("let_go") or 0) if isinstance(said, dict) else 0  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]

    def stop(self) -> None:
        """Closes the host, which then goes."""
        from hmz.rpc import Closed

        if self.peer is not None:
            with contextlib.suppress(Closed):
                self.peer.notify("close")

    def forget(self, sub: Subscription) -> None:
        """Stops handing a subscription what the host tells it."""
        with self._lock:
            if self._subs.get(sub.tag) is sub:
                del self._subs[sub.tag]

    def went(self) -> None:
        """Ends every subscription still attached, once the host's link has closed."""
        with self._lock:
            subs = list(self._subs.values())
        for sub in subs:
            sub.end(WENT_AWAY, detaching=False)

    def _call(
        self, method: str, params: dict[str, Any], timeout: float | None = None
    ) -> Any:
        from hmz.rpc import Closed, Code, RpcError

        if self.peer is None:
            raise RpcError(Code.CONFLICT, "this host has closed")
        try:
            return self.peer.call(method, params, timeout=timeout)
        except Closed:
            raise RpcError(Code.CONFLICT, "this host has closed") from None
        except RpcError as why:
            raise RpcError(Code.CONFLICT, _why(why.message)) from None

    def _quietly(self, method: str, params: dict[str, Any]) -> None:
        with contextlib.suppress(Exception):
            self._call(method, params, timeout=_ANSWERING)


def _why(message: str) -> str:
    """A host's failure as it is refused: its own words, without what the link adds."""
    return message.removeprefix("Something went wrong here: ")


def _user() -> str:
    """Who is at this end, as a frontend is named for want of a name."""
    import getpass
    import os

    user = os.environ.get("HUMANIZE_NAME", "")
    if not user:
        with contextlib.suppress(OSError, KeyError):
            user = getpass.getuser()
    return user or "somebody"


class Hosts:
    """Every host the daemon took on, by workspace and slot.

    Args:
      changed: Called whenever a host is taken on or goes.
    """

    def __init__(self, changed: Callable[[], None]) -> None:
        self._changed = changed
        self._lock = threading.Lock()
        self._held: dict[tuple[str, str], Hosted] = {}
        self._starting: dict[tuple[str, str], Future[Hosted]] = {}
        #: Every slot of a chat or an `hmz exec` whose host has gone, which is not started again.
        self._gone: set[tuple[str, str]] = set()
        self._order = itertools.count()
        #: Whether a host was ever taken on.
        self.ever = False

    def __len__(self) -> int:
        with self._lock:
            return len(self._held) + len(self._starting)

    def listed(self) -> list[Hosted]:
        """Every host taken on, in the order taken on."""
        with self._lock:
            return list(self._held.values())

    def get(self, workspace: str, slot: str) -> Hosted | None:
        """The host of a workspace and slot, or None where none is held."""
        with self._lock:
            return self._held.get((workspace, slot))

    def opened(self, workspace: str, slot: str) -> Hosted:
        """The host of a workspace and slot, started where none is.

        `slot` `chat:` or `exec:` alone is a new slot of that kind.

        Raises:
          RpcError: 409 for a chat or an `hmz exec` whose host has gone, and 503 where the
            host could not be started.
        """
        from hmz.rpc import Code, RpcError

        if slot in ("chat:", "exec:"):
            slot = where.chat(slot[:-1])
        key = (workspace, slot)
        with self._lock:
            held = self._held.get(key)
            if held is not None:
                return held
            if key in self._gone:
                raise RpcError(
                    Code.CONFLICT,
                    "This chat has folded away."
                    if slot.startswith("chat:")
                    else "This epic has ended.",
                )
            starting = self._starting.get(key)
            mine = starting is None
            if starting is None:
                starting = self._starting[key] = Future()
        if mine:
            try:
                hosted = self._starts(workspace, slot)
            except OSError as why:
                with self._lock:
                    del self._starting[key]
                starting.set_exception(
                    RpcError(Code.UNAVAILABLE, f"The host could not be started: {why}")
                )
            else:
                with self._lock:
                    del self._starting[key]
                    self._held[key] = hosted
                    self.ever = True
                starting.set_result(hosted)
                self._changed()
        return starting.result()

    def _starts(self, workspace: str, slot: str) -> Hosted:
        """Starts a host process, and links it."""
        from hmz.daemon.detaching import forks, hosts_in
        from hmz.reach.pipes import SocketPipe
        from hmz.rpc import Peer

        ours, theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            kept = theirs.fileno()
            forks(
                lambda telling: hosts_in(workspace, telling, kept, slot),
                _PATIENCE,
                keep=(kept,),
            )
        except OSError:
            ours.close()
            raise
        finally:
            theirs.close()
        hosted = Hosted(workspace, slot)
        key = (workspace, slot)

        def went() -> None:
            with self._lock:
                if self._held.get(key) is hosted:
                    del self._held[key]
                if slot:
                    self._gone.add(key)
            hosted.went()
            self._changed()

        hosted.peer = Peer(
            SocketPipe(ours, trusted=True), hosted.told, on_close=went, name="hmz-link"
        )
        try:
            said: Any = hosted.peer.call("status", {}, timeout=_PATIENCE)
        except Exception as why:
            hosted.peer.close()
            raise OSError(f"the host did not say what it holds: {why}") from why
        hosted.said = dict(said)
        return hosted

    def stop_all(self) -> None:
        """Closes every host, as the daemon goes."""
        for hosted in self.listed():
            hosted.stop()
            if hosted.peer is not None:
                hosted.peer.close()


def _follows(following: Any, message: dict[str, Any]) -> None:
    """Works out what one message means for the figures of its epic."""
    kind = message.get("type")
    with contextlib.suppress(Exception):
        if kind == "started":
            following.started(message)
        elif kind == "printed":
            following.printed(str(message.get("text") or ""))
        elif kind == "opened":
            following.opened(message)
        elif kind == "event":
            following.heard(message)
        elif kind == "ended":
            following.ended(message)
        elif (
            kind == "run"
            and message.get("state") == "running"
            and int(message.get("run") or 0) > following.run
        ):
            following.started(message)


def _figures(following: Any) -> dict[str, Any]:
    """What an epic has done and spent, worked out of its history records (Section 4.9.1.5)."""
    from hmz.runtime.watching.monitor import lasting, tallied, thousands

    monitor = following.monitor
    moment = time.monotonic()
    ended = monitor.until
    elapsed = max(0.0, (ended if ended is not None else moment) - monitor.began)
    agents = monitor.shape()
    sessions = monitor.shape(sessions=True)
    lines = tallied(monitor)

    def node(name: str, shape: Any) -> dict[str, Any]:
        return {
            "name": name,
            "turns": shape.turns.get(name, 0),
            "working": name in shape.working,
            "since": round(shape.since.get(name, 0.0), 1),
            "lasting": lasting(shape.since.get(name, 0.0)),
            "used": shape.used.get(name, 0),
            "tokens": thousands(shape.used.get(name, 0)),
            "under": [
                {"whose": one.whose, "about": one.about, "working": one.working}
                for one in shape.under.get(name, ())
            ],
        }

    return {
        "run": following.run,
        "elapsed": round(elapsed, 1),
        "lasting": lasting(elapsed),
        "ended": ended is not None,
        "agents": [node(name, agents) for name in agents.turns],
        "sessions": [node(key, sessions) for key in sessions.turns],
        "handovers": [
            {"from": sender, "to": receiver, "count": count}
            for (sender, receiver), count in agents.handovers.items()
        ],
        "latest": list(agents.latest) if agents.latest else None,
        "spending": [
            {
                "model": spend.model,
                "tokens": spend.tokens,
                "rate": round(spend.rate, 1),
                "dollars": spend.dollars,
                "money": _money(spend.dollars),
                "kinds": dict(spend.kinds),
            }
            for spend in monitor.spending()
        ],
        "reckoning": [
            {"kind": one.kind, "tokens": one.tokens, "whole": one.whole}
            for one in monitor.reckoning()
        ],
        "tally": list(lines) if lines else [],
    }


def _money(dollars: float | None) -> str:
    """Dollars as the figures write them, "" for a price nobody knows."""
    if dollars is None:
        return ""
    from hmz.coganchor.prices import money

    return money(dollars)

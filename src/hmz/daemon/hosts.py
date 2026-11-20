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

    from hmz.daemon.reach import Links
    from hmz.daemon.sessions import Session
    from hmz.rpc import Call, Peer

__all__ = ["CLOSED", "Hosted", "Hosts", "Subscription"]

#: How long a host is given to come up.
_PATIENCE = 10.0

#: How long a host is given to say how it stands before it is answered for.
_ANSWERING = 5.0

#: How many hosts that went are kept as they last stood, where nobody asks: as many as notices.
_LEFT = 200

#: How often a subscription that asked for figures has them worked out again, at most.
_FIGURING = 1.0

#: What a host that is going, or has gone, refuses what it is asked with.
CLOSED = "this host has closed"

#: Why a subscription ends whose host process ended without closing.
WENT_AWAY = "the host went away"

#: Why an epic-scoped Ai-chan's subscription ends once another epic starts on its host.
OUT_OF_SCOPE = "out of Ai-chan's scope"


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
        """Takes one message the host told this frontend.

        One of an epic-scoped Ai-chan's ends once another epic than hers starts on its host
        (Section 4.21.3.3 of daemon.md).
        """
        with self._lock:
            if self._gone:
                return
            # The daemon's own frontends, side questions' among them, carry no reach.
            reach = getattr(self.session, "reach", None)
            if (
                reach is not None
                and reach.scope == "epic"
                and self._open
                and message.get("type") == "run"
                and message.get("epic") not in (None, "", reach.epic)
            ):
                self.end(OUT_OF_SCOPE)
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
        #: How it stood as it went, as it said last of all; None while it is up, or where it
        #: went without saying.
        self.last: dict[str, Any] | None = None
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
        """Takes one message the host sent up the link, for the subscription it names.

        What it says as it goes, `went`, is kept as how it last stood.
        """
        if call.method == "went":
            self.last = dict(call.params)
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

    def started(self, said: dict[str, Any]) -> dict[str, Any]:
        """Starts an epic on the host as the daemon's own frontend, let go of once answered.

        Args:
          said: The start: `do` `start`, and what that takes.

        Returns:
          The host's answer, which says `ok`.
        """
        attached: Any = self._call(
            "attach",
            {
                "tag": f"daemon/{id(said):x}",
                "name": "hmz",
                "kind": "daemon",
                "replay": False,
                "since": None,
            },
        )
        client = str(attached["client"])
        try:
            return self.ask(client, said)
        finally:
            self.detach(client)

    def chat(self, said: dict[str, Any]) -> dict[str, Any]:
        """Asks the chat held there what `chat.*` asks, as the host answers it.

        Answered `ok`, and `why` and the `code` to refuse it with where not.

        Raises:
          RpcError: 409, where the host could not be asked.
        """
        answer: Any = self._call("chat", {"said": said})
        return answer if isinstance(answer, dict) else {"ok": False, "why": "no answer"}  # pyright: ignore[reportUnknownVariableType]

    def env(self, said: dict[str, Any]) -> dict[str, Any]:
        """Asks the host for one `hosts.env.*`, attaching nobody: `ok`, else `why` and `code`.

        Raises:
          RpcError: 409, where the host could not be asked.
        """
        answer: Any = self._call("env", {"said": said})
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
            raise RpcError(Code.CONFLICT, CLOSED)
        try:
            return self.peer.call(method, params, timeout=timeout)
        except Closed:
            raise RpcError(Code.CONFLICT, CLOSED) from None
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
        #: How each host that has gone stood as it went, until `left` is asked.
        self._left: dict[tuple[str, str], dict[str, Any]] = {}
        self._order = itertools.count()
        #: Whether a host was ever taken on.
        self.ever = False
        #: What starts the host of an `ai:` slot, and listens on its scoped link while it is
        #: up; None where nothing does, and every `ai:` slot is of no conversation.
        self.ai: Links | None = None

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

    def gone(self, workspace: str, slot: str) -> bool:
        """Whether the host of a chat's or an `hmz exec`'s slot has gone, not to come back."""
        with self._lock:
            return (workspace, slot) in self._gone

    def left(self) -> dict[tuple[str, str], dict[str, Any]]:
        """How each host that went since this was last asked stood as it went, asked once.

        A host goes as soon as it is idle, an `hmz exec`'s right after its epic ends: how it
        stood then is what the notice of that epic is made of, which no status asked of the
        hosts still held would say.

        Returns:
          Each one's last status by workspace and slot, less those that went without saying.
        """
        with self._lock:
            left, self._left = self._left, {}
        return left

    def opened(self, workspace: str, slot: str) -> Hosted:
        """The host of a workspace and slot, started where none is.

        `slot` `chat:` or `exec:` alone is a new slot of that kind. An `ai:` slot's host is
        started as its Ai-chan conversation's (Section 4.22.5 of daemon.md), again once it
        has gone.

        Raises:
          RpcError: 409 for a chat or an `hmz exec` whose host has gone, or an Ai-chan host
            that refused its start; 404 for an `ai:` slot of no conversation; and 503 where
            the host could not be started.
        """
        from hmz.rpc import Code, RpcError

        if slot in ("chat:", "exec:"):
            slot = where.chat(slot[:-1])
        key = (workspace, slot)
        with self._lock:
            held = self._held.get(key)
            if held is not None:
                return held
            if slot.startswith("ai:") and self.ai is None:
                raise RpcError(
                    Code.NOT_FOUND, f"There is no Ai-chan conversation {slot}."
                )
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
            self._starts_up(workspace, slot, starting)
        return starting.result()

    def _starts_up(self, workspace: str, slot: str, starting: Future[Hosted]) -> None:
        """Starts the host of a slot, and settles what those waiting on it are answered."""
        from hmz.rpc import Code, RpcError

        key = (workspace, slot)
        ai = self.ai if slot.startswith("ai:") else None
        try:
            env = ai.before(workspace, slot) if ai is not None else None
            hosted = self._starts(workspace, slot, env)
        except Exception as why:  # noqa: BLE001 -- whoever waits on it is told why
            with self._lock:
                del self._starting[key]
            if ai is not None:
                ai.went(slot)
            starting.set_exception(
                why
                if isinstance(why, RpcError)
                else RpcError(Code.UNAVAILABLE, f"The host could not be started: {why}")
            )
            return
        with self._lock:
            del self._starting[key]
            self.ever = True
            # Held only while its link is open: one that closed on its way here is
            # gone already, and its link's closing found nothing to let go of.
            if hosted.peer is not None and not hosted.peer.closed:
                self._held[key] = hosted
            up = key in self._held
        if not up:
            starting.set_exception(
                RpcError(Code.UNAVAILABLE, "The host went as it came up.")
            )
        elif ai is not None:
            try:
                ai.after(hosted)
            except Exception as why:  # noqa: BLE001 -- whoever waits on it is told why
                hosted.stop()
                starting.set_exception(
                    why
                    if isinstance(why, RpcError)
                    else RpcError(Code.CONFLICT, f"Ai-chan could not start: {why}")
                )
            else:
                starting.set_result(hosted)
        else:
            starting.set_result(hosted)
        self._changed()

    def _starts(
        self, workspace: str, slot: str, env: dict[str, str] | None = None
    ) -> Hosted:
        """Starts a host process, with `env` beside the daemon's environment, and links it."""
        from hmz.daemon.detaching import spawns
        from hmz.reach.pipes import SocketPipe
        from hmz.rpc import Peer

        ours, theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            kept = theirs.fileno()
            spawns(
                ["host", workspace, slot, str(kept)], _PATIENCE, keep=(kept,), env=env
            )
        except OSError:
            ours.close()
            raise
        finally:
            theirs.close()
        hosted = Hosted(workspace, slot)
        hosted.peer = Peer(
            SocketPipe(ours, trusted=True),
            hosted.told,
            on_close=lambda: self.went(hosted),
            name="hmz-link",
        )
        try:
            said: Any = hosted.peer.call("status", {}, timeout=_PATIENCE)
        except Exception as why:
            hosted.peer.close()
            raise OSError(f"the host did not say what it holds: {why}") from why
        hosted.said = dict(said)
        return hosted

    def went(self, hosted: Hosted) -> None:
        """Lets go of a host whose link has closed, and of every subscription to it.

        A slot is gone for good only once its host was held: one that never came up may be
        started again. An Ai-chan host is started again as it is attached to, and its scoped
        link goes with it.
        """
        key = (hosted.workspace, hosted.slot)
        with self._lock:
            mine = self._held.get(key) is hosted
            if mine:
                del self._held[key]
                if hosted.last is not None:
                    self._left[key] = hosted.last
                    # Nobody asks a private daemon: the oldest go, rather than all be kept.
                    while len(self._left) > _LEFT:
                        del self._left[next(iter(self._left))]
                if hosted.slot and not hosted.slot.startswith("ai:"):
                    self._gone.add(key)
        if mine and hosted.slot.startswith("ai:") and self.ai is not None:
            self.ai.went(hosted.slot)
        hosted.went()
        self._changed()

    def outwaited(self, hosted: Hosted) -> bool:
        """Whether a host that said it has closed is gone, waited for a while.

        Its link closes a moment after it lets its frontends go; until then it is held still.
        """
        ended = time.monotonic() + _ANSWERING
        while self.get(hosted.workspace, hosted.slot) is hosted:
            if time.monotonic() > ended:
                return False
            time.sleep(0.05)
        return True

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

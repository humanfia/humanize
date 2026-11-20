"""This machine's one daemon: one JSON-RPC endpoint, on its socket and on every listener.

Every client -- the terminal interface, `hmz exec`, the page, the desktop application, a
program of the SDK -- reaches the daemon over a session of `protocol/wire.md` and nothing else:
on the socket, trusted and paired as the device `local` from its start; on a listener, only
through mutual TLS or a WebRTC data channel, and paired only once its device has claimed a
code. A session that is not paired may say hello, claim a code and ask what there is to call,
and is refused everything else 401.

The daemon holds the hosts (:mod:`hmz.daemon.hosts`) and ends each client's session itself:
what a client asks of an epic it asks the daemon, which asks the host down its link. It makes
no call of its own to any client. It goes once it has held no host and no session for 2
seconds, or a minute after it started where nothing ever came -- unless it listens beyond its
socket or was started by `hmz daemon serve`, after which it goes on `SIGTERM` alone.
"""

from __future__ import annotations

import contextlib
import logging
import os
import socket
import threading
import time
from typing import TYPE_CHECKING, Any, cast

from hmz.daemon import where

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Sequence
    from pathlib import Path

    from hmz.daemon.listening import Listener
    from hmz.daemon.reach import Reach
    from hmz.daemon.sessions import Session
    from hmz.rpc import Call, Dispatcher, Handler, Peer, Pipe
    from hmz.trust.identity import Identity

__all__ = ["Router", "serves", "serving"]

_log = logging.getLogger(__name__)

#: How often the daemon looks at whether it is still wanted.
_TICK = 0.5

#: How long a daemon nobody has reached waits for somebody to.
_GRACE = 60.0

#: How long `pair.create` waits for the listeners still being opened to have their routes.
_OPENING = 5.0

#: How long a daemon whose last host and session have gone waits before it goes as well.
_LINGER = 2.0

#: The daemon this process is, while it serves, which asks its own hosts how they stand in
#: this process: asked over its own socket, every question would be a session that kept it
#: from ever going.
serving: Router | None = None

#: How often the daemon's own files are marked as used (Section 7.6.6 of files.md).
_RETOUCH = 3600.0

#: How often the daemon asks again which release of hmz is the newest (Section 13.3.2.3 of
#: core.md).
_REFETCH = 24 * 3600.0


class Router:
    """This machine's daemon: its sessions, its hosts, and every method it serves.

    Args:
      at: The daemon's directory.
      listening: Its socket, bound and listening.
      listen: The listener specs `--listen` named, kept beside those the setting `listen`
        names, which are opened and closed as it changes.
      kept: Whether it goes on `SIGTERM` alone, as `hmz daemon serve` started it.
      opened: Told the route of each listener as it opens.
    """

    def __init__(
        self,
        at: Path,
        listening: socket.socket,
        *,
        listen: Sequence[str] = (),
        kept: bool = False,
        opened: Callable[[str], None] | None = None,
    ) -> None:
        from hmz.daemon.hosts import Hosts
        from hmz.daemon.reach import Links
        from hmz.daemon.sessions import Idems
        from hmz.trust.devices import Devices
        from hmz.trust.pairing import Codes

        self._at = at
        self._listening = listening
        self._given = list(listen)
        self._kept = kept
        #: When the settings file was last changed, as last read for `listen`.
        self._stamp: int | None = None
        self._opened: Callable[[str], None] = opened or _nothing
        self._lock = threading.Lock()
        self._sessions: dict[Peer, Session] = {}
        self._pending: set[Session] = set()
        self._since = time.monotonic()
        self._ever = False
        self._done = threading.Event()
        self._identity: Identity | None = None
        self._revoking = threading.local()
        self.listeners: list[Listener] = []
        self.hosts = Hosts(self._touched)
        #: The Ai-chan conversations, the hosts of their `ai:` slots and their scoped links.
        self.links = Links(
            lambda pipe, reach: self.admit(
                pipe, fingerprint="", trusted=True, reach=reach
            ),
            self._dropped,
        )
        self.hosts.ai = self.links
        self.devices = Devices()
        self.codes = Codes()
        self.idems = Idems()
        self.dispatcher = self._dispatcher()
        self._unwatch = self.devices.watch(self._revoked)

    # -- what the methods read

    @property
    def identity(self) -> Identity:
        """This machine's device identity, made the first time it is asked for."""
        if self._identity is None:
            from hmz.trust.identity import device

            self._identity = device()
        return self._identity

    @property
    def daemon_id(self) -> str:
        """This daemon's id: the SPKI fingerprint of this machine's device certificate."""
        return self.identity.fingerprint

    def routes(self) -> list[str]:
        """The routes of every listener open, as a pairing code carries them.

        A listener opens on a thread of its own, so one the daemon began to open a moment
        ago, as it started, is waited for, for a while: answered at once, a code would be
        refused for want of a route that is on its way.
        """
        listeners = self.listeners
        until = time.monotonic() + _OPENING
        for one in listeners:
            one.settled(max(0.0, until - time.monotonic()))
        return [one.route for one in listeners if one.route]

    def capabilities(self) -> list[str]:
        """What this daemon offers of what a session may ask about: `webrtc`, where it is."""
        from hmz import rtc

        webrtc = any(one.spec.startswith("webrtc:") for one in self.listeners)
        return ["webrtc"] if webrtc and rtc.available() else []

    def session(self, call: Call) -> Session:
        """The session a call came in on."""
        with self._lock:
            return self._sessions[call.peer]

    def live(self) -> dict[str, int]:
        """How many sessions each device fingerprint holds open."""
        counted: dict[str, int] = {}
        with self._lock:
            for one in self._sessions.values():
                if one.paired and not one.closed:
                    counted[one.fingerprint] = counted.get(one.fingerprint, 0) + 1
        return counted

    def claimed(self, fingerprint: str, device: str) -> None:
        """Reads every session a device holds open as paired, once it claimed a code."""
        with self._lock:
            for one in self._sessions.values():
                if one.fingerprint == fingerprint:
                    one.device = device

    @contextlib.contextmanager
    def revoking(self, session: Session) -> Generator[None]:
        """Revokes in a session's call: every session of the device is closed but that one."""
        self._revoking.session = session
        try:
            yield
        finally:
            self._revoking.session = None

    # -- the loop

    def start(self) -> None:
        """Starts taking sessions on the socket, and opens every listener.

        Notices are watched for from the start (Section 4.19.1.3 of daemon.md), where the
        family that serves them is there.
        """
        import importlib

        try:
            notices = importlib.import_module("hmz.daemon.api.notices")
        except ImportError:
            notices = None
        watched = getattr(notices, "watched", None)
        if callable(watched):
            try:
                watched()
            except Exception:  # noqa: BLE001 -- the daemon serves without them
                _log.exception("notices could not be watched")
        self._relistens()
        threading.Thread(target=self._takes, name="hmz-daemon", daemon=True).start()

    def _relistens(self) -> None:
        """Opens and closes listeners as the setting `listen` names them, once it changes.

        Those `hmz daemon serve --listen` named are kept whatever the setting says.
        """
        from hmz.coganchor import settings
        from hmz.daemon.listening import listener

        try:
            stamp = settings.where().stat().st_mtime_ns
        except OSError:
            stamp = 0
        if stamp == self._stamp:
            return
        self._stamp = stamp
        wanted = list(dict.fromkeys([*_listened(), *self._given]))
        kept = [one for one in self.listeners if one.spec in wanted]
        for one in self.listeners:
            if one.spec not in wanted:
                one.close()
        held = {one.spec for one in kept}
        self.listeners = kept + listener(
            [one for one in wanted if one not in held],
            lambda pipe, fingerprint: self.admit(pipe, fingerprint=fingerprint),
            lambda: self.identity,
            self._opened,
        )

    def wait(self, timeout: float | None = None) -> bool:
        """Waits for the daemon to be over: closed, or holding nothing for long enough."""
        return self._done.wait(timeout)

    def close(self) -> None:
        """Stops being reachable, closes every session, and lets go of every host."""
        self._unwatch()
        with contextlib.suppress(OSError):
            self._listening.close()
        for one in self.listeners:
            one.close()
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            session.close()
        self.hosts.stop_all()
        self.links.close()
        for name in (where.SOCKET, where.RECORD):
            with contextlib.suppress(OSError):
                (self._at / name).unlink()
        self._done.set()

    def _takes(self) -> None:
        from hmz.reach.pipes import SocketPipe

        self._listening.settimeout(_TICK)
        touched = time.monotonic()
        try:
            while not self._done.is_set() and not self._idle():
                self._relistens()
                if time.monotonic() - touched > _RETOUCH:
                    touched = time.monotonic()
                    for name in (*_FILES, "."):
                        with contextlib.suppress(OSError):
                            os.utime(self._at / name)
                try:
                    one, _ = self._listening.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break
                one.settimeout(None)
                self.admit(SocketPipe(one, trusted=True), fingerprint="", trusted=True)
        finally:
            self._done.set()

    def _idle(self) -> bool:
        """Whether nothing is left for this daemon to be reached for."""
        if self._kept or self.listeners:
            return False
        with self._lock:
            if self._sessions or self._pending or len(self.hosts):
                return False
            waited = time.monotonic() - self._since
        return waited > (_LINGER if self._ever or self.hosts.ever else _GRACE)

    def _touched(self) -> None:
        with self._lock:
            self._since = time.monotonic()

    # -- sessions

    def admit(
        self,
        pipe: Pipe,
        *,
        fingerprint: str,
        trusted: bool = False,
        reach: Reach | None = None,
    ) -> Peer:
        """Takes a session on: over the socket, a scoped link, or secured over a listener.

        Args:
          pipe: Its pipe, secured where its carrier is untrusted.
          fingerprint: Its client's device fingerprint; "" over a trusted carrier.
          trusted: Whether its carrier is trusted.
          reach: The reach of the Ai-chan conversation whose scoped link it came over.

        Returns:
          Its JSON-RPC end, which reads it from now on.
        """
        from hmz.daemon.sessions import Outgoing, Session
        from hmz.rpc import Peer
        from hmz.trust.devices import LOCAL

        device = LOCAL if trusted else (self.devices.named(fingerprint) or "")
        if device and not trusted:
            self.devices.seen(fingerprint)
        held: list[Session] = []
        out = Outgoing(pipe, lambda: held[0].behind())  # noqa: PLW0108 -- made after
        session = Session(
            out,
            trusted=trusted,
            fingerprint=fingerprint or LOCAL,
            device=device,
            reach=reach,
        )
        held.append(session)
        with self._lock:
            self._pending.add(session)
            self._ever = True

        def serve(call: Call) -> None:
            with self._lock:
                if session.peer is None:
                    session.peer = call.peer
                    self._sessions[call.peer] = session
            self.dispatcher(call)

        peer = Peer(
            out, serve, on_close=lambda: self._closed(session), name="hmz-session"
        )
        with self._lock:
            self._pending.discard(session)
            if session.peer is None and not peer.closed:
                session.peer = peer
                self._sessions[peer] = session
        return peer

    def _closed(self, session: Session) -> None:
        """Lets go of everything a session held, once it has closed."""
        with self._lock:
            self._pending.discard(session)
            if session.peer is not None:
                self._sessions.pop(session.peer, None)
            self._since = time.monotonic()
        session.out.close()
        with session.lock:
            subs = list(session.subs.values())
        for sub in subs:
            sub.dropped()

    def _dropped(self, ident: int) -> None:
        """Closes every session over the scoped link of a conversation, as its host goes."""
        with self._lock:
            dropped = [
                one
                for one in self._sessions.values()
                if one.reach is not None and one.reach.id == ident
            ]
        for one in dropped:
            one.close()

    def _revoked(self, device: Any) -> None:
        """Closes every session of a device revoked, but the one revoking it, which goes last."""
        sparing = getattr(self._revoking, "session", None)
        with self._lock:
            dropped = [
                one
                for one in self._sessions.values()
                if one.fingerprint == device.fingerprint and one is not sparing
            ]
        for one in dropped:
            one.close()

    # -- the methods

    def _dispatcher(self) -> Dispatcher:
        from hmz.daemon.methods import families, methods
        from hmz.rpc import Dispatcher

        dispatcher = Dispatcher()
        #: The families' methods, which `epic.start` checks an epic with as it is served.
        self.families = families()
        served = {**self.families, **methods(self, self.families)}
        for name, handler in served.items():
            try:
                dispatcher.register(name, self._guarded(name, handler))
            except ValueError:
                _log.warning("%s is not in the OpenRPC document, so not served", name)
        return dispatcher

    def _guarded(self, name: str, handler: Handler) -> Handler:
        """A handler held to the pairing gate, to a reach, and to `idem`.

        The pairing gate of Section 4.5.10, the reach of a session that carries one of Section
        4.21, and `idem` of Section 6.7.
        """
        from hmz.daemon.reach import Held, holding
        from hmz.rpc import Code, RpcError
        from hmz.trust.pairing import NOT_PAIRED, UNPAIRED

        def carried(call: Call) -> Any:
            session = self.session(call)
            if name not in UNPAIRED and not session.paired:
                raise RpcError(Code.NOT_PAIRED, NOT_PAIRED)
            if session.reach is None:
                return idempotent(session, call)
            held = Held(session.reach, session, self.hosts, self.links.kept)
            refusal = held.refusal(name, call.params)
            if refusal is not None:
                raise RpcError(Code.FORBIDDEN, refusal)
            token = holding.set(held)
            try:
                return held.answered(name, idempotent(session, call))
            finally:
                holding.reset(token)

        def idempotent(session: Session, call: Call) -> Any:
            idem = call.params.get("idem")
            if not isinstance(idem, str):
                return handler(call)
            return self.idems.once(
                session.fingerprint, idem, name, lambda: handler(call)
            )

        if name == "notices.subscribe":
            return self._noticed(carried)
        if name == "notices.unsubscribe":
            return self._unnoticed(carried)
        return carried

    def _noticed(self, handler: Handler) -> Handler:
        """Keeps the notices subscriptions a session opens, to end them where it falls behind."""

        def carried(call: Call) -> Any:
            answer: Any = handler(call)
            said: object = answer
            sub = (
                cast("dict[str, Any]", said).get("sub")
                if isinstance(said, dict)
                else None
            )
            if isinstance(sub, str):
                session = self.session(call)
                with session.lock:
                    session.notices.add(sub)
            return answer

        return carried

    def _unnoticed(self, handler: Handler) -> Handler:
        def carried(call: Call) -> Any:
            session = self.session(call)
            with session.lock:
                session.notices.discard(str(call.params.get("sub")))
            return handler(call)

        return carried


def _nothing(said: str) -> None:
    del said


#: The daemon's own files, which it marks as used.
_FILES = (where.SOCKET, where.RECORD, where.LOCK, where.LOG)


def serves(
    telling: int | None = None,
    *,
    listen: Sequence[str] = (),
    kept: bool = False,
    opened: Callable[[str], None] | None = None,
) -> None:
    """Holds this machine's daemon until it goes.

    Args:
      telling: A descriptor to say on that it is listening, and then close, or None.
      listen: The listener specs besides the setting `listen`'s.
      kept: Whether it goes on `SIGTERM` alone, as `hmz daemon serve` started it.
      opened: Told the route of each listener as it opens.

    Raises:
      OSError: If a daemon of this machine is already running, or the socket cannot be bound
        -- the one failure whoever asked for a daemon has to hear about.
    """
    from hmz.rpc import PROTOCOL

    at = where.at()
    # Taken before anything is looked at: two started in the same second would both find
    # nothing here, and one of them would take the other's socket away as stale.
    holding = where.holds(at)
    try:
        listening = _listens(at)
        where.wrote(
            at,
            {
                "pid": os.getpid(),
                "started": where.now(),
                "kind": "daemon",
                "protocol": PROTOCOL,
            },
        )
        _logs(at)
        _migrates()
        router = Router(
            at,
            listening,
            listen=listen,
            kept=kept,
            opened=opened,
        )
        if telling is not None:
            # Said and left open: the descriptor is whoever forked this one's to close.
            with contextlib.suppress(OSError):
                os.write(telling, b"listening\n")
        global serving  # noqa: PLW0603 -- one daemon per process, while it serves
        serving = router
        router.start()
        _fetches()
        fetched = time.monotonic()
        try:
            # A tick at a time: a signal is handled on this thread, and one the kernel hands to
            # another thread never wakes one blocked here for good -- so a terminate would
            # wait for whatever ended the daemon next.
            while not router.wait(_TICK):
                if time.monotonic() - fetched > _REFETCH:
                    fetched = time.monotonic()
                    _fetches(verses=False)
        finally:
            router.close()
            serving = None
    finally:
        with contextlib.suppress(OSError):
            os.close(holding)


def _fetches(*, verses: bool = True) -> None:
    """Fetches what the daemon tells its clients of, in the background, telling none of them.

    The newest release of hmz, where what is kept has got old, which `session.hello` reads,
    and every flowverse's index, which `flowverses.list` reads (Section 3.9.8 of daemon.md).

    Args:
      verses: Whether the flowverses' indexes are fetched as well, which is as it starts alone.
    """
    import importlib

    from hmz.coganchor import releases

    releases.refresh()
    if verses:
        # Found as the families are, above this layer.
        importlib.import_module("hmz.daemon.api.flowverses").fetches()


def _listened() -> list[str]:
    """The listener specs of the setting `listen`, those that are none left out."""
    from hmz.coganchor import settings
    from hmz.daemon.listening import spec

    said: object = settings.read().get("listen")
    found: list[str] = []
    for one in cast("list[object]", said) if isinstance(said, list) else []:
        try:
            spec(str(one))
        except ValueError:
            _log.warning("%s is not a listener, so not listened on", one)
            continue
        found.append(str(one))
    return found


def _migrates() -> None:
    """Moves the chats an earlier hmz kept as epics among the chats (Section 8.7.10 of core.md).

    Before anything is served, so that no client reads one as an epic; and never what keeps
    the daemon from coming up.
    """
    from hmz.runtime.epic import migrated

    try:
        moved, left = migrated()
    except Exception:  # noqa: BLE001 -- the daemon comes up whatever was left on disk
        _log.exception("the chats an earlier hmz kept as epics could not be moved")
        return
    if moved:
        _log.info("moved %d chat(s) kept as epics: %s", len(moved), ", ".join(moved))
    for name, why in left.items():
        _log.warning("left the chat %s among the epics: %s", name, why)


def _logs(at: Path) -> None:
    """Writes what the daemon logs to `daemon.log`, as its standard error is (Section 7.6.5)."""
    del at
    if logging.getLogger("hmz").handlers or logging.getLogger().handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s: %(message)s"))
    logging.getLogger("hmz").addHandler(handler)
    logging.getLogger("hmz").setLevel(logging.INFO)


def _listens(at: Path) -> socket.socket:
    """Binds the socket this daemon is reached on, taking away one a daemon that is gone left.

    Called with this machine's daemon lock already held, so that taking a socket away as stale
    cannot be taking one from a daemon that is coming up beside this.
    """
    path = at / where.SOCKET
    if path.exists():
        with contextlib.suppress(OSError):
            path.unlink()
    listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with where.reached(at) as reaching:
            listening.bind(reaching)
        path.chmod(0o600)
        listening.listen(64)
    except OSError:
        listening.close()
        raise
    return listening

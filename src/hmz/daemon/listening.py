"""Where this machine's daemon listens beside its socket (Section 3.9 of daemon.md).

Each listener spec of the setting `listen`, and of `hmz daemon serve --listen`, is one carrier
end: `tcp://<address>:<port>` and `ws://<address>:<port>` accept clients directly,
`relay:<url>` and `webrtc:<url>` register with a relay and accept the clients that join there,
natively or by WebRTC, and `easytier:<name>` joins an EasyTier network and accepts on a TCP port
of the loopback that network reaches. Every carrier here is untrusted: a native client is
admitted only through the mutual TLS of `hmz.trust`, and a browser through the DTLS of a data
channel `hmz.rtc` answers, before a single frame.

A listener that cannot be opened, or a relay that cannot be reached, is written to the daemon's
log and tried again after 1 second, the wait doubling to 60, and keeps nothing else from being
served.
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import queue
import threading
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from websockets.sync.client import ClientConnection
    from websockets.sync.server import ServerConnection

    from hmz.reach import Route
    from hmz.rpc import Peer, Pipe
    from hmz.trust.identity import Identity

__all__ = ["Admit", "Listener", "listener", "spec"]

_log = logging.getLogger(__name__)

#: What a listener hands each client it has secured to: the pipe, and its device fingerprint;
#: what it gives back is waited on, `wait()`, for as long as the session lasts.
type Admit = Callable[[Pipe, str], Peer]

#: How long a client is given to say anything at all of its handshake.
_SHAKING = 30.0

#: The kinds of route that are listener specs.
_KINDS = frozenset({"tcp", "ws", "relay", "webrtc", "easytier"})


def spec(text: str) -> Route:
    """Reads one listener spec: a route of a kind a daemon listens on, or one of port `0`.

    A spec is not a route: port `0` names any free port (Section 3.9.2 of daemon.md), which no
    route names (Section 3.3.4 of wire.md), and the route of the listener is the port taken.
    So a `tcp` or `ws` spec of port `0` is read as a route of another port, and then given `0`.

    A `ws` spec is `ws://<address>:<port>` alone: a daemon serves no `wss`, takes a port only
    as it is told one, and answers at no path.

    Raises:
      ValueError: `<spec> is not a listener.`
    """
    import dataclasses
    import re

    from hmz.reach import Route

    anywhere = re.fullmatch(r"((?:tcp|ws)://.+):0(/.*)?", text)
    read = f"{anywhere[1]}:1{anywhere[2] or ''}" if anywhere else text
    try:
        route = Route.parse(read)
    except ValueError:
        route = None
    if (
        route is None
        or route.kind not in _KINDS
        or (route.kind == "ws" and not _plain(route.url))
    ):
        raise ValueError(f"{text} is not a listener.")
    if anywhere:
        route = dataclasses.replace(route, port=0, url=text if route.url else "")
    return route


def _plain(url: str) -> bool:
    """Whether a WebSocket URL is `ws://<address>:<port>` and no more: the one a daemon serves."""
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    return url == f"ws://{parts.netloc}" and parts.port is not None


class Listener:
    """One listener, open or being opened, until it is closed.

    Attributes:
      spec: Its listener spec, as given.
      route: Its route, as a pairing code carries it (Section 3.9.3), "" until it opens.
    """

    def __init__(
        self,
        text: str,
        admit: Admit,
        identity: Callable[[], Identity],
        opened: Callable[[str], None],
    ) -> None:
        self.spec = text
        self.route = ""
        self._admit = admit
        self._identity = identity
        self._opened = opened
        self._closed = threading.Event()
        self._held: list[Callable[[], object]] = []
        self._lock = threading.Lock()
        threading.Thread(target=self._keeps, daemon=True, name="hmz-listen").start()

    def close(self) -> None:
        """Stops listening, and stops whatever it started."""
        with self._lock:
            self._closed.set()
            held, self._held = self._held, []
        for one in held:
            with contextlib.suppress(Exception):
                one()

    def _holds(self, closing: Callable[[], object]) -> bool:
        """Keeps what closes something it opened; closes it at once where it is closed."""
        with self._lock:
            if not self._closed.is_set():
                self._held.append(closing)
                return True
        closing()
        return False

    def _keeps(self) -> None:
        """Opens it, and opens it again after a wait each time it cannot be."""
        from hmz.reach import Backoff

        backoff = Backoff()
        route = spec(self.spec)
        while not self._closed.is_set():
            try:
                self._opens(route)
            except Exception as why:  # noqa: BLE001 -- written down, and tried again
                _log.warning("%s could not be listened on: %s", self.spec, why)
                with self._lock:
                    held, self._held = self._held, []
                for one in held:
                    with contextlib.suppress(Exception):
                        one()
            else:
                return
            self._closed.wait(backoff.next())

    def _opens(self, route: Route) -> None:
        if route.kind == "tcp":
            self._tcp(route.host, route.port or 0, route)
        elif route.kind == "ws":
            self._ws(route)
        elif route.kind == "easytier":
            self._easytier(route.name)
        else:
            self._relay(route)

    def _says(self, route: str) -> None:
        self.route = route
        self._opened(route)

    def _tcp(self, host: str, port: int, route: Route) -> None:
        from hmz.reach import TcpListener

        listening = TcpListener(host, port)
        if not self._holds(listening.close):
            return
        said = listening.route
        self._says(str(said) if route.kind == "tcp" else str(route))
        while not self._closed.is_set():
            try:
                pipe = listening.accept()
            except OSError:
                if self._closed.is_set():
                    return
                raise
            threading.Thread(
                target=self._secures, args=(pipe,), daemon=True, name="hmz-tls"
            ).start()

    def _secures(self, pipe: Pipe) -> Peer | None:
        """Answers a native client's mutual TLS, and admits it once its key is known."""
        from hmz.trust import tls

        try:
            secured = tls.answer(pipe, self._identity())
        except Exception as why:  # noqa: BLE001 -- one client's failure is that client's
            _log.info("a client of %s was refused: %s", self.spec, why)
            with contextlib.suppress(OSError):
                pipe.close()
            return None
        return self._admit(secured, secured.peer)

    def _ws(self, route: Route) -> None:
        import socket
        from urllib.parse import urlsplit

        from websockets.sync.server import serve

        from hmz.reach import MESSAGE, WebSocketPipe

        parts = urlsplit(route.url)

        def carries(connection: ServerConnection) -> None:
            # The connection lasts as long as this does: it is closed with its session.
            peer = self._secures(WebSocketPipe(connection))
            if peer is not None:
                peer.wait()

        def answers(connection: ServerConnection, request: Any) -> Any:
            if request.headers.get("Upgrade", "").lower() != "websocket":
                return connection.respond(404, "Not Found\n")
            return None

        host = parts.hostname or ""
        server = serve(
            carries,
            host,
            parts.port or 0,
            # The family is the address's, as `hmz.reach.TcpListener` takes it: IPv4 unless said.
            family=socket.AF_INET6 if ":" in host else socket.AF_INET,
            process_request=answers,
            max_size=MESSAGE,
            compression=None,
        )
        if not self._holds(server.shutdown):
            return
        port: int = server.socket.getsockname()[1]
        self._says(f"ws://{_named(host)}:{port}{parts.path}")
        server.serve_forever()

    def _easytier(self, name: str) -> None:
        from hmz.coganchor import easytier, settings
        from hmz.reach import Route

        entries: object = settings.read().get("easytier")
        entry: object = (
            cast("dict[str, Any]", entries).get(name)
            if isinstance(entries, dict)
            else None
        )
        held = cast("dict[str, Any] | None", entry if isinstance(entry, dict) else None)
        if held is None:
            raise LookupError(f"There is no EasyTier entry {name}.")

        nodes: object = held.get("nodes")
        joined = easytier.serving(
            str(held.get("secret") or ""),
            easytier.PORT,
            peers=[str(one) for one in cast("list[object]", nodes or [])],
        )
        if not self._holds(joined.terminate):
            return
        self._tcp("127.0.0.1", easytier.PORT, Route("easytier", name=name))

    def _relay(self, route: Route) -> None:
        if self._holds(_registered(route, self._identity(), self._admit)):
            self._says(str(route))


def _named(host: str) -> str:
    """A host as a route names it: this machine's name for an address that is any of its own."""
    import socket

    if host in ("", "0.0.0.0", "::"):  # noqa: S104 -- what is replaced, not bound
        return socket.gethostname()
    return f"[{host}]" if ":" in host else host


def listener(
    texts: Sequence[str],
    admit: Admit,
    identity: Callable[[], Identity],
    opened: Callable[[str], None],
) -> list[Listener]:
    """Opens a listener for each spec, each on a thread of its own.

    Args:
      texts: The listener specs.
      admit: What each client secured is handed to.
      identity: This machine's device identity, asked for once a listener needs it.
      opened: Told the route of each listener as it opens.

    Returns:
      The listeners.
    """
    return [Listener(one, admit, identity, opened) for one in dict.fromkeys(texts)]


class _Signals:
    """The signals of one WebRTC join, as `hmz.rtc` reads and writes them."""

    def __init__(
        self,
        send: Callable[[dict[str, Any]], None],
        refuse: Callable[[str], None],
    ) -> None:
        self._send = send
        self._refuse = refuse
        self.inbox: queue.SimpleQueue[object] = queue.SimpleQueue()

    def send(self, data: dict[str, Any]) -> None:
        self._send(data)

    def refuse(self, why: str) -> None:
        self._refuse(why)

    def receive(self, timeout: float) -> object:
        try:
            said = self.inbox.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError("no signal came") from None
        if said is None:
            raise EOFError("the join has gone")
        return said


class Registration:
    """This daemon registered at one relay, accepting the clients that join it there.

    Native joins, where a spec is `relay:`, are spliced and carry mutual TLS; WebRTC joins,
    where a spec is `webrtc:` and the optional dependency is installed, are answered as a data
    channel whose DTLS holds the browser to its own fingerprint (Section 4.7 of wire.md). A
    join this registration does not take is refused with why. One control connection for
    every listener at the relay (Section 5.4.1), opened again as Section 3.6.4 says where it
    drops.

    Attributes:
      url: The relay's URL.
      kinds: The kind of each listener open here: `relay`, `webrtc`.
    """

    def __init__(self, url: str, identity: Identity, admit: Admit) -> None:
        self.url = url
        self.kinds: list[str] = []
        self._identity = identity
        self._admit = admit
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._control: ClientConnection | None = None
        self._joins: dict[str, _Signals] = {}
        threading.Thread(target=self._keeps, daemon=True, name="hmz-relay").start()

    def close(self) -> None:
        """Stops registering."""
        with self._lock:
            self._closed.set()
            control = self._control
            joins, self._joins = list(self._joins.values()), {}
        if control is not None:
            control.close()
        for one in joins:
            one.inbox.put(None)

    def _keeps(self) -> None:
        from websockets.exceptions import ConnectionClosed

        from hmz.reach import Backoff, websocket

        backoff = Backoff()
        while not self._closed.is_set():
            try:
                control = websocket(self.url)
            except OSError as why:
                _log.warning("The relay at %s could not be reached: %s", self.url, why)
                self._closed.wait(backoff.next())
                continue
            with self._lock:
                self._control = control
            try:
                if not self._closed.is_set():
                    self._registers(control)
                    backoff.reset()
                    self._serves(control)
            except (ConnectionClosed, OSError, ValueError) as why:
                if not self._closed.is_set():
                    _log.warning("The registration at %s ended: %s", self.url, why)
            finally:
                control.close()
            self._closed.wait(backoff.next())

    def _registers(self, control: ClientConnection) -> None:
        identity = self._identity
        control.send(json.dumps({"t": "register", "id": identity.fingerprint}))
        challenge = _read(control.recv(_SHAKING))
        nonce = challenge.get("nonce")
        if challenge.get("t") != "challenge" or not isinstance(nonce, str):
            raise ConnectionError(_why(challenge, self.url))
        from cryptography.hazmat.primitives.serialization import Encoding

        cert = base64.b64encode(identity.certificate.public_bytes(Encoding.DER))
        sig = identity.signs(f"hmz-relay/1\n{nonce}".encode())
        control.send(
            json.dumps(
                {
                    "t": "prove",
                    "cert": cert.decode(),
                    "sig": base64.urlsafe_b64encode(sig).decode().rstrip("="),
                }
            )
        )
        answer = _read(control.recv(_SHAKING))
        if answer.get("t") != "registered":
            raise ConnectionError(_why(answer, self.url))

    def _serves(self, control: ClientConnection) -> None:
        while True:
            told = _read(control.recv())
            kind, conn = told.get("t"), told.get("conn")
            if kind == "error":
                raise ConnectionError(_why(told, self.url))
            if not isinstance(conn, str):
                continue
            if kind == "join" and told.get("kind") == "native":
                threading.Thread(
                    target=self._native, args=(control, conn), daemon=True
                ).start()
            elif kind == "join" and told.get("kind") == "webrtc":
                self._offered(control, conn)
            elif kind == "signal":
                with self._lock:
                    join = self._joins.get(conn)
                if join is not None:
                    join.inbox.put(told.get("data"))

    def _refuses(self, control: ClientConnection, conn: str, why: str) -> None:
        with self._lock, contextlib.suppress(Exception):
            control.send(json.dumps({"t": "refuse", "conn": conn, "why": why}))

    def _native(self, control: ClientConnection, conn: str) -> None:
        from websockets.exceptions import ConnectionClosed

        from hmz.reach import WebSocketPipe, websocket
        from hmz.trust import tls

        if "relay" not in self.kinds:
            self._refuses(control, conn, "This daemon answers WebRTC alone here.")
            return
        try:
            joined = websocket(self.url)
        except OSError as why:
            self._refuses(control, conn, str(why))
            return
        try:
            joined.send(json.dumps({"t": "accept", "conn": conn}))
            secured = tls.answer(WebSocketPipe(joined), self._identity)
        except (ConnectionClosed, OSError) as why:
            _log.info("a join at %s was refused: %s", self.url, why)
            joined.close()
            return
        self._admit(secured, secured.peer)

    def _offered(self, control: ClientConnection, conn: str) -> None:
        from hmz import rtc

        if "webrtc" not in self.kinds:
            self._refuses(control, conn, "This daemon takes native joins alone here.")
            return
        if not rtc.available():
            self._refuses(control, conn, "This daemon cannot answer WebRTC.")
            return

        def send(data: dict[str, Any]) -> None:
            with self._lock:
                control.send(json.dumps({"t": "signal", "conn": conn, "data": data}))

        signals = _Signals(send, lambda why: self._refuses(control, conn, why))
        with self._lock:
            self._joins[conn] = signals
        threading.Thread(
            target=self._answers, args=(conn, signals), daemon=True
        ).start()

    def _answers(self, conn: str, signals: _Signals) -> None:
        from cryptography.hazmat.primitives.serialization import Encoding

        from hmz import rtc
        from hmz.coganchor import settings

        servers: object = settings.read().get("ice_servers") or []
        try:
            pipe = rtc.answer(
                signals,
                cert=self._identity.certificate.public_bytes(Encoding.DER),
                sign=self._identity.signs,
                ice_servers=[
                    cast("Mapping[str, Any]", one)
                    for one in cast("list[object]", servers)
                    if isinstance(one, dict)
                ]
                if isinstance(servers, list)
                else [],
            )
        except (rtc.Refused, ModuleNotFoundError):
            # Refused through its signals already, saying why.
            return
        except (TimeoutError, EOFError, OSError, ValueError) as why:
            _log.info("a WebRTC join at %s failed: %s", self.url, why)
            return
        finally:
            with self._lock:
                self._joins.pop(conn, None)
        self._admit(pipe, pipe.device)


#: The registrations open, by relay URL and daemon id.
_registrations: dict[tuple[str, str], Registration] = {}
_registering = threading.Lock()


def _registered(route: Route, identity: Identity, admit: Admit) -> Callable[[], None]:
    """Opens a `relay:` or `webrtc:` listener on the one registration at its relay.

    Returns:
      What closes the listener, and the registration with the last listener on it.
    """
    key = (route.url, identity.fingerprint)
    with _registering:
        held = _registrations.get(key)
        if held is None:
            held = _registrations[key] = Registration(route.url, identity, admit)
        held.kinds.append(route.kind)

    def closes() -> None:
        with _registering:
            held.kinds.remove(route.kind)
            if held.kinds:
                return
            del _registrations[key]
        held.close()

    return closes


def _read(message: str | bytes) -> dict[str, Any]:
    """A control message, or nothing at all for one that is not a JSON object in text."""
    if not isinstance(message, str):
        return {}
    try:
        held: object = json.loads(message)
    except ValueError:
        return {}
    return cast("dict[str, Any]", held) if isinstance(held, dict) else {}


def _why(said: dict[str, Any], url: str) -> str:
    why = said.get("why")
    return why if isinstance(why, str) else f"The relay at {url} answered out of turn."

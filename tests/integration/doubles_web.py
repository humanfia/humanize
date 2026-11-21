"""What the web interface's integration tests share: the interface served, and a browser.

The interface is served on a thread of the test's own until the test is done, bridging to this
machine's daemon -- the test's `daemon` fixture, or one it starts. A browser is a client on this
machine: it asks for the page's files over HTTP, one connection a request -- let in with the
key the address carries, or not -- and speaks JSON-RPC to a daemon over the WebSocket `/rpc` or
`/dial` as the page does, through the real bridge. The page itself, drawn by a real browser, is
`tests/system/web`'s.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import threading
import urllib.parse
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from websockets.sync.client import ClientConnection, connect

from hmz.reach import WebSocketPipe
from hmz.rpc import Code, Peer, RpcError, hello
from hmz.web import listening

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from hmz.rpc import Call
    from hmz.web.site import Site

#: How long anything here waits for the interface before failing the test.
PATIENCE = 30.0


@contextlib.contextmanager
def served(origin: str = "") -> Generator[Site]:
    """The web interface, answering on a thread of its own until the block ends.

    Args:
      origin: The origin a proxy that rewrites `Host` serves its page at, or "" for none.
    """
    with listening(origin=origin) as site:
        threading.Thread(
            target=site.serve_forever,
            kwargs={"poll_interval": 0.05},
            daemon=True,
            name="hmz-web-test",
        ).start()
        try:
            yield site
        finally:
            site.shutdown()


@dataclass
class Answer:
    """What the interface answered one request with."""

    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        """The body, read as the JSON it is."""
        return json.loads(self.body)


@dataclass
class Session:
    """A JSON-RPC session the page holds with a daemon, and every notification it was sent."""

    peer: Peer
    said: dict[str, Any]
    told: list[tuple[str, dict[str, Any]]] = field(
        default_factory=list[tuple[str, dict[str, Any]]]
    )
    heard: threading.Condition = field(default_factory=threading.Condition)

    def call(self, method: str, **params: Any) -> Any:
        """Calls one method, and answers its result."""
        return self.peer.call(method, params, timeout=PATIENCE)

    def until(
        self, wanted: Callable[[str, dict[str, Any]], bool], what: str
    ) -> dict[str, Any]:
        """The first notification `wanted(method, params)` says is the one, waited for."""
        with self.heard:
            found = self.heard.wait_for(
                lambda: next((p for m, p in self.told if wanted(m, p)), None),
                PATIENCE,
            )
        assert found is not None, f"never told {what}"
        return found


@dataclass
class Browser:
    """A browser on this machine: what it names the server as, and the cookie it carries.

    Attributes:
      site: The interface it reaches.
      host: What its requests name the server as, which is the address's own by default.
      cookie: The cookie it carries, or "" before it is let in.
      at: Which loopback it connects to.
    """

    site: Site
    host: str = ""
    cookie: str = field(default="")
    at: str = "127.0.0.1"

    def signs_in(self) -> Answer:
        """Opens the address the interface printed, keeping the cookie it is handed."""
        query = urllib.parse.urlsplit(self.site.address).query
        answer = self.get(f"/?{query}")
        said = answer.headers.get("set-cookie", "")
        self.cookie = said.split(";", 1)[0]
        return answer

    def get(self, path: str, **headers: str) -> Answer:
        """Asks for one thing."""
        return self.asks("GET", path, headers=headers)

    def asks(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Answer:
        """Asks one thing by any method."""
        connection = http.client.HTTPConnection(
            self.at, self.site.port, timeout=PATIENCE
        )
        try:
            sent = {"Host": self._host()} | (
                {"Cookie": self.cookie} if self.cookie else {}
            )
            connection.request(method, path, body=body, headers=sent | (headers or {}))
            answer = connection.getresponse()
            return Answer(
                answer.status,
                {name.lower(): value for name, value in answer.getheaders()},
                answer.read(),
            )
        finally:
            connection.close()

    def opens(self, path: str, **headers: str) -> ClientConnection:
        """Opens a WebSocket of the server, as the page's own script opens one.

        Raises:
          websockets.exceptions.InvalidStatus: If the server refused it.
        """
        sent = {
            "Origin": f"http://{self._host()}",
            "Sec-Fetch-Site": "same-origin",
        } | ({"Cookie": self.cookie} if self.cookie else {})
        opening = connect(
            f"ws://{self._host_at()}{path}",
            additional_headers=sent | headers,
            open_timeout=PATIENCE,
            max_size=None,
            compression=None,
        )
        # Entered and never left: it lives as long as the session over it.
        return contextlib.ExitStack().enter_context(opening)

    @contextlib.contextmanager
    def session(self, path: str = "/rpc") -> Generator[Session]:
        """A JSON-RPC session over `/rpc`, or over a `/dial` once it is up, hello said."""
        socket = self.opens(path)
        if path.startswith("/dial"):
            said = states(socket)
            assert said, "the dial said nothing"
            assert said[-1]["state"] == "up", said
        heard: list[tuple[str, dict[str, Any]]] = []
        changed = threading.Condition()

        def serves(call: Call) -> None:
            if call.id is not None:
                call.fail(
                    RpcError(Code.METHOD_NOT_FOUND, f"There is no {call.method}.")
                )
                return
            with changed:
                heard.append((call.method, call.params))
                changed.notify_all()

        peer = Peer(WebSocketPipe(socket, trusted=True), serves, name="page")
        try:
            said = hello(peer, "page", "web", timeout=PATIENCE)
            yield Session(peer, said, heard, changed)
        finally:
            peer.close()
            socket.close()

    def _host(self) -> str:
        return self.host or f"127.0.0.1:{self.site.port}"

    def _host_at(self) -> str:
        return (
            f"[{self.at}]:{self.site.port}"
            if ":" in self.at
            else f"{self.at}:{self.site.port}"
        )


def states(socket: ClientConnection) -> list[dict[str, Any]]:
    """Every text message `/dial` says until `up` or the WebSocket closes, in order."""
    said: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        while True:
            message = socket.recv(timeout=PATIENCE)
            if not isinstance(message, str):
                break
            said.append(json.loads(message))
            if said[-1]["state"] in ("up", "failed"):
                break
    return said

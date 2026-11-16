"""A daemon's side of a carrier: a TCP listener, and the clients it accepts.

The daemon always answers on its socket; beside it, it may listen where the setting `listen`
says (Section 3.9 of the daemon protocol). A `tcp://` listener is a socket bound where the spec
says, and every connection it accepts is untrusted, carrying mutual TLS before any frame. A
`relay:` listener is :class:`hmz.reach.relays.RelayListener`, which accepts the same way.
"""

from __future__ import annotations

import contextlib
import socket
from typing import TYPE_CHECKING

from hmz.reach.pipes import SocketPipe
from hmz.reach.routes import Route

if TYPE_CHECKING:
    from hmz.reach.pipes import Pipe

__all__ = ["TcpListener"]

#: The addresses that are any of this machine's, which a route cannot name a daemon by.
_ANY = frozenset({"0.0.0.0", "::", ""})  # noqa: S104 -- what is replaced, not bound


class TcpListener:
    """A TCP socket listening for clients, each one an untrusted pipe."""

    def __init__(self, host: str, port: int) -> None:
        """Listens.

        Args:
          host: The address to listen on, an IPv6 one without its brackets.
          port: The port, `0` for any free one.

        Raises:
          OSError: If it cannot be listened on.
        """
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        self._sock = socket.create_server((host, port), family=family)
        self.host = host

    @property
    def port(self) -> int:
        """The port taken."""
        port: int = self._sock.getsockname()[1]
        return port

    @property
    def route(self) -> Route:
        """The route a client reaches it by, as a pairing code carries it (Section 3.9.3).

        An address that is any of this machine's is replaced by this machine's host name, and a
        port `0` by the one taken.
        """
        host = socket.gethostname() if self.host in _ANY else self.host
        return Route("tcp", host=host, port=self.port)

    def accept(self) -> Pipe:
        """The next client, waiting for one.

        Raises:
          OSError: Once it is closed.
        """
        one, _ = self._sock.accept()
        one.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return SocketPipe(one, trusted=False)

    def close(self) -> None:
        """Stops listening; an accept waiting is answered with an `OSError`."""
        with contextlib.suppress(OSError):
            self._sock.shutdown(socket.SHUT_RDWR)
        self._sock.close()

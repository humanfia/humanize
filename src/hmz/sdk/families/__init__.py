"""What a daemon does, a family of its methods at a time, as a program of the SDK asks for it.

A :class:`hmz.sdk.Client` makes any call there is (`client.call("chat.list", {...})`), and what
it is answered is whatever JSON the daemon said. A family is the same calls with names and
types: `client.chats.list(workspace=...)`. There is one family for each group of methods in
`protocol/openrpc.json`, each in a module of its own here and reached as an attribute of the
client, and between them they cover every method a daemon serves -- which is what makes
anything the web page does something a program can do.

A family holds nothing but its client: it is made when first asked for and costs one object.
"""

from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING, Any, ClassVar, Self

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from types import TracebackType

    from hmz.sdk.client import Client

__all__ = ["Family", "Subscription"]


class Family:
    """One group of a daemon's methods, asked through one client."""

    #: Every method of `protocol/openrpc.json` this family makes, each by a method of its own.
    METHODS: ClassVar[tuple[str, ...]] = ()

    def __init__(self, client: Client) -> None:
        """Holds the client the calls are made through.

        Args:
          client: It. Closing it is still its holder's to do.
        """
        self._client = client

    def _call(
        self,
        method: str,
        /,
        *,
        idem: str | None = None,
        wait: float | None = None,
        **params: Any,
    ) -> Any:
        """Makes one call with what was given, and returns its result.

        Args:
          method: The method.
          idem: The key a write is made once under, however often it is sent.
          wait: How many seconds an answer is waited for, None for as long as it takes.
            Not `seconds`, which is a parameter of some methods.
          **params: Its parameters; one given None is left out, which is how the daemon is
            told nothing was said about it.

        Raises:
          hmz.sdk.Refused: With the daemon's message, `code` and `data`.
          TimeoutError: If no answer came within `wait`.
        """
        given = {name: value for name, value in params.items() if value is not None}
        return self._client.call(method, given, idem=idem, seconds=wait)

    def _heard(self, method: str, sub: str) -> Subscription:
        """What one subscription is told from here on, and what it was told before this."""
        return Subscription(self._client, method, sub)

    def _listens(self) -> None:
        """Keeps what the client is told from here on, for a subscription about to be opened.

        Called before the call that opens one: a client hears nothing until it has a
        listener, and a daemon may speak before that call has returned.

        Raises:
          RuntimeError: If the client was given a listener of its own.
        """
        _hub(self._client)


class _Hub:
    """Every notification one client hears, handed to whichever subscription it is for.

    A client has one listener. This is it, for a client whose families subscribe: it keeps
    what arrived for a subscription nobody has taken up yet -- the daemon may speak before the
    call that opened it has returned -- and hands it over when somebody does. What arrives for
    one that was taken up and closed is for nobody, and is dropped: a host says `gone` to a
    frontend after the call that let it go has been answered.
    """

    #: How many notifications are kept for a subscription nobody has taken up.
    KEPT = 4096

    #: How many subscriptions closed are remembered as closed, the newest: what a daemon
    #: says to one after it was let go comes at once, not thousands of subscriptions later.
    LEFT = 1024

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._taken: dict[
            tuple[str, str], queue.SimpleQueue[dict[str, Any] | None]
        ] = {}
        self._waiting: dict[tuple[str, str], list[dict[str, Any]]] = {}
        #: The subscriptions closed, in the order they were: a dict for its order.
        self._left: dict[tuple[str, str], None] = {}

    def hears(self, method: str, params: dict[str, Any]) -> None:
        key = (method, str(params.get("sub", "")))
        with self._lock:
            inbox = self._taken.get(key)
            if inbox is None:
                if key in self._left:
                    return
                waiting = self._waiting.setdefault(key, [])
                if len(waiting) < self.KEPT:
                    waiting.append(params)
                return
        inbox.put(params)

    def takes(self, key: tuple[str, str]) -> queue.SimpleQueue[dict[str, Any] | None]:
        inbox: queue.SimpleQueue[dict[str, Any] | None] = queue.SimpleQueue()
        with self._lock:
            for params in self._waiting.pop(key, []):
                inbox.put(params)
            self._left.pop(key, None)
            self._taken[key] = inbox
        return inbox

    def leaves(self, key: tuple[str, str]) -> None:
        with self._lock:
            inbox = self._taken.pop(key, None)
            self._waiting.pop(key, None)
            self._left[key] = None
            while len(self._left) > self.LEFT:
                del self._left[next(iter(self._left))]
        if inbox is not None:
            inbox.put(None)


_hubs_lock = threading.Lock()


def _hub(client: Client) -> _Hub:
    """The one hub of a client, made its listener the first time one is wanted.

    Raises:
      RuntimeError: If the client was given a listener of its own, which hears everything
        and leaves nothing to hand out.
    """
    with _hubs_lock:
        hub: _Hub | None = getattr(client, "_families_hub", None)
        if hub is None:
            hub = _Hub()
            client.heard(hub.hears)
            client._families_hub = hub  # noqa: SLF001  # pyright: ignore[reportAttributeAccessIssue]
        return hub


class Subscription:
    """What a daemon says to one subscription, in order: iterated, and closed to stop hearing.

    Iterating blocks until the next notification and ends once this is closed. Closing it
    stops the hearing only -- ending the subscription at the daemon is its family's to do.
    """

    def __init__(self, client: Client, method: str, sub: str) -> None:
        """Takes up one subscription of a client. Made by a family.

        Args:
          client: The client it was opened through.
          method: The notification it is told by: `epic.event`, `notices.event`.
          sub: The subscription, as the call that opened it named it.
        """
        self.sub = sub
        self._key = (method, sub)
        self._hub = _hub(client)
        self._inbox = self._hub.takes(self._key)

    def next(self, seconds: float | None = None) -> Mapping[str, Any] | None:
        """The next notification's parameters.

        Args:
          seconds: How long to wait for one, None for as long as it takes.

        Returns:
          Them, or None where this was closed or nothing came in time.
        """
        try:
            return self._inbox.get(timeout=seconds)
        except queue.Empty:
            return None

    def __iter__(self) -> Iterator[Mapping[str, Any]]:
        """Every notification from here on, until this is closed."""
        while (one := self._inbox.get()) is not None:
            yield one

    def close(self) -> None:
        """Stops hearing it, and drops whatever it is told from here on."""
        self._hub.leaves(self._key)

    def __enter__(self) -> Self:
        """Hears it for as long as the block runs."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        why: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stops hearing it, however the block ended."""
        self.close()

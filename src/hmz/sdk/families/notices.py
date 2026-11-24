"""What a daemon tells its person: listed and subscribed to (`notices.*`).

A daemon makes a notice of each epic or chat that ends, fails, is stopped, asks a person
something or waits for what to say next (Section 4.19 of daemon.md), numbers them, and keeps
the latest. They are read after a number (`notices.list`) or heard as they are made
(`notices.subscribe`); which kinds a person is told of is the client's choice.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from . import Family, Subscription

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

__all__ = ["KINDS", "Notice", "Notices"]

#: Every kind of notice a daemon makes.
KINDS = ("done", "failed", "stopped", "asked", "listening")

#: How long one wait for a notice is, between looks at whether the session still stands.
_LOOK = 1.0

#: The code a call is refused with where the session has ended.
_WENT = 503


@dataclass(frozen=True)
class Notice:
    """One notice."""

    id: int
    """Its number, greater than every earlier one's."""
    kind: str
    """One of :data:`KINDS`."""
    workspace: str
    """The workspace of the host it is of."""
    slot: str
    """That host's slot."""
    epic: str
    """The epic it is of, "" for a chat's."""
    chat: str
    """The chat it is of, "" for an epic's."""
    flow: str
    """The epic's flow, `chat` for a chat."""
    task: str
    """The epic's task, or the chat's first message."""
    role: str
    """The role a question is asked of, else ""."""
    text: str
    """What it says: the question, the reply, why it failed."""
    at: float
    """When it was made, in seconds since the epoch."""

    @classmethod
    def of(cls, said: Mapping[str, Any]) -> Notice:
        """A notice as a daemon says one: the `notice` of a `notices.event`."""
        return cls(
            int(said["id"]),
            str(said["kind"]),
            str(said.get("workspace") or ""),
            str(said.get("slot") or ""),
            str(said.get("epic") or ""),
            str(said.get("chat") or ""),
            str(said.get("flow") or ""),
            str(said.get("task") or ""),
            str(said.get("role") or ""),
            str(said.get("text") or ""),
            float(said.get("at") or 0),
        )


class Notices(Family):
    """What a daemon tells its person: listed and subscribed to."""

    METHODS: ClassVar = ("notices.list", "notices.subscribe", "notices.unsubscribe")

    def list(self, after: int | None = None) -> list[Notice]:
        """The notices kept after one, oldest first, the latest 200.

        Args:
          after: The number of the last one read, None for every one kept.
        """
        return self.kept(after)[0]

    def last(self) -> int:
        """The number of the newest notice, 0 where there is none."""
        return self.kept()[1]

    def kept(self, after: int | None = None) -> tuple[list[Notice], int]:
        """The notices kept after one, and the number of the newest, as one call says both.

        Args:
          after: The number of the last one read, None for every one kept.

        Returns:
          Them, oldest first, the latest 200; and the newest notice's number, 0 for none.
        """
        said = self._call("notices.list", after=after)
        return [Notice.of(one) for one in said["notices"]], int(said["last"])

    def subscribe(self, after: int | None = None) -> Subscription:
        """Opens a notices subscription, told each notice as `{sub, notice}`.

        A subscription the session fell too far behind on is told `{sub, gone}` once and
        nothing after it; :meth:`follow` subscribes again where that happens.

        Args:
          after: The number of the last notice heard, every one kept after which is told
            first; None for those made from now on.

        Returns:
          It, to iterate. Closing it stops the hearing; :meth:`unsubscribe` ends it.
        """
        return self._subscribed(after)[0]

    def _subscribed(self, after: int | None) -> tuple[Subscription, int]:
        """A subscription opened, and the number of the newest notice as it was."""
        # Listening first: the notices kept after `after` are told before this returns.
        self._listens()
        said = self._call("notices.subscribe", after=after)
        return self._heard("notices.event", str(said["sub"])), int(said["last"])

    def unsubscribe(self, subscription: Subscription | str) -> None:
        """Ends a notices subscription, and stops hearing it.

        Args:
          subscription: What :meth:`subscribe` returned, or its `sub`.

        Raises:
          hmz.sdk.Refused: 410 where it is not open on this session.
        """
        if isinstance(subscription, Subscription):
            subscription.close()
            subscription = subscription.sub
        self._call("notices.unsubscribe", sub=subscription)

    def follow(self, after: int | None = None) -> Generator[Notice]:
        """Every notice as it is made, for as long as this is iterated.

        Subscribes, subscribes again after the last notice heard where the daemon ended the
        subscription for falling behind, and unsubscribes once the iteration is closed.

        Args:
          after: As :meth:`subscribe` takes it.

        Raises:
          ConnectionError: Once the session has ended, with nothing more to hear.
        """
        from hmz.runtime import Refused

        heard, last = self._subscribed(after)
        if after is None:
            # From now: what a subscription opened again takes up after.
            after = last
        try:
            while True:
                said = heard.next(_LOOK)
                if said is None:
                    if self._client.wait(0):
                        raise ConnectionError("the session with the daemon has ended")
                    continue
                if "notice" in said:
                    notice = Notice.of(said["notice"])
                    after = notice.id
                    yield notice
                elif "gone" in said:
                    heard.close()
                    try:
                        heard, _ = self._subscribed(after)
                    except Refused as why:
                        if why.code == _WENT:
                            raise ConnectionError(str(why)) from None
                        raise
        finally:
            # Ended already where the session went, or the daemon ended it itself.
            with contextlib.suppress(Refused, OSError, TimeoutError):
                self.unsubscribe(heard)

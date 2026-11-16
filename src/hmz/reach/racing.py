"""Choosing among the routes of one daemon, and trying again once a session is lost.

A daemon known by several routes is raced over them: each started a quarter of a second after
the one before it, or at once where every one before it has failed, so that a route that
hangs costs the next only that quarter second, and a route that fails costs it nothing. The
first to get through the handshake it is given wins, and every other is closed. The handshake
is whatever the caller says it is -- TLS pinned to the daemon id, then `session.hello` -- so
that what wins is a daemon proven, not a port that merely answered (Section 3.6).
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from hmz.reach.pipes import Pipe

__all__ = ["FIRST", "LONGEST", "STAGGER", "Backoff", "Won", "race"]

#: How long after one route starts the next one does (Section 3.6.1).
STAGGER = 0.25

#: The first wait before a session lost is tried again, and the longest (Section 3.6.4).
FIRST, LONGEST = 1.0, 60.0


@dataclass(frozen=True, slots=True)
class Won[R, T]:
    """The route that won a race, its pipe, and what the handshake over it gave.

    Attributes:
      route: The route.
      pipe: The carrier it opened, which the winner now holds.
      answer: What the handshake returned.
    """

    route: R
    pipe: Pipe
    answer: T


def race[R, T](
    routes: Sequence[R],
    opening: Callable[[R], Pipe],
    handshake: Callable[[Pipe], T],
    *,
    stagger: float = STAGGER,
) -> Won[R, T]:
    """Opens the routes of one daemon in turn, and keeps the first to complete a handshake.

    Args:
      routes: The routes, in the order kept.
      opening: What opens one: :func:`hmz.reach.dial`, told whatever else it needs.
      handshake: What is done over a carrier opened before it counts, raising where it fails.
      stagger: How long after one starts the next does.

    Returns:
      The winner. Every other attempt has been, or is being, closed.

    Raises:
      ValueError: If there are no routes.
      Exception: Once every route has failed, the failure of the last to fail (Section
        3.6.3).
    """
    if not routes:
        raise ValueError("A daemon with no route cannot be reached.")
    told: queue.Queue[tuple[int, Won[R, T] | Exception]] = queue.Queue()
    holding = threading.Lock()
    opened: dict[int, Pipe] = {}
    over = False

    def attempts(index: int) -> None:
        try:
            pipe = opening(routes[index])
        except Exception as why:  # noqa: BLE001 -- whatever it is, it is this route's failure
            told.put((index, why))
            return
        with holding:
            kept = not over
            if kept:
                opened[index] = pipe
        if not kept:
            pipe.close()
            return
        try:
            answer = handshake(pipe)
        except Exception as why:  # noqa: BLE001 -- as above
            pipe.close()
            told.put((index, why))
            return
        told.put((index, Won(routes[index], pipe, answer)))

    def starts(index: int) -> None:
        threading.Thread(
            target=attempts, args=(index,), daemon=True, name="hmz-race"
        ).start()

    winner = -1
    try:
        starts(0)
        started, failed, next_at = 1, 0, time.monotonic() + stagger
        while True:
            wait = (
                max(next_at - time.monotonic(), 0.0) if started < len(routes) else None
            )
            try:
                index, outcome = told.get(timeout=wait)
            except queue.Empty:
                starts(started)
                started, next_at = started + 1, time.monotonic() + stagger
                continue
            if isinstance(outcome, Won):
                winner = index
                return outcome
            failed += 1
            if failed < started:
                continue
            if started == len(routes):
                raise outcome
            starts(started)
            started, next_at = started + 1, time.monotonic() + stagger
    finally:
        with holding:
            over = True
            losers = [pipe for index, pipe in opened.items() if index != winner]
        for pipe in losers:
            pipe.close()


class Backoff:
    """The wait before a session that dropped or failed is tried again (Section 3.6.4).

    One second, doubling after each further failure up to sixty, and one second again once a
    session is up.
    """

    def __init__(self, first: float = FIRST, longest: float = LONGEST) -> None:
        self._first = first
        self._longest = longest
        self._wait = first

    def next(self) -> float:
        """The wait before the next try, which makes the one after it longer."""
        wait = self._wait
        self._wait = min(wait * 2, self._longest)
        return wait

    def reset(self) -> None:
        """Starts again at the first wait, a session being up."""
        self._wait = self._first

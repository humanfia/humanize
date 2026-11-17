"""Racing routes as Section 3.6 of wire.md says, and spacing the tries of a session lost."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import pytest

from hmz.reach import FIRST, LONGEST, STAGGER, Backoff, race
from tests.unit.reach.memory import Memory

if TYPE_CHECKING:
    from hmz.rpc import Pipe


def test_the_first_route_hanging_costs_the_second_only_the_stagger() -> None:
    hung, quick = Memory(), Memory()
    pipes = {"hangs": hung, "answers": quick}
    started: dict[str, float] = {}
    began = time.monotonic()

    def opening(route: str) -> Pipe:
        started[route] = time.monotonic() - began
        return pipes[route]

    def handshake(pipe: Pipe) -> str:
        said = pipe.recv(5)
        if not said:
            raise ConnectionError("closed before it answered")
        return said.decode()

    quick.feed(b"hello")
    won = race(["hangs", "answers"], opening, handshake, stagger=0.1)
    assert won.route == "answers"
    assert won.pipe is quick
    assert won.answer == "hello"
    assert started["answers"] >= 0.1
    # The loser was closed, which is what ended its handshake.
    assert hung.closed
    assert not quick.closed


def test_a_route_starts_at_once_where_every_one_before_it_failed() -> None:
    began = time.monotonic()

    def opening(route: str) -> Pipe:
        if route == "fails":
            raise ConnectionRefusedError("refused")
        return Memory()

    won = race(["fails", "works"], opening, lambda _pipe: "up", stagger=10.0)
    assert won.route == "works"
    assert time.monotonic() - began < 5.0


def test_every_route_failing_raises_the_failure_of_the_last_to_fail() -> None:
    order = iter([0.2, 0.0])

    def opening(route: str) -> Pipe:
        time.sleep(next(order))
        raise ConnectionError(f"{route} failed")

    with pytest.raises(ConnectionError, match=r"^first failed$"):
        race(["first", "second"], opening, lambda _pipe: None, stagger=0.05)


def test_a_failed_handshake_closes_its_pipe_and_is_the_route_failing() -> None:
    pipe = Memory()

    def refuses(_pipe: Pipe) -> None:
        raise PermissionError("not the daemon it was paired with")

    with pytest.raises(PermissionError):
        race(["only"], lambda _route: pipe, refuses)
    assert pipe.closed


def test_a_loser_still_opening_when_the_race_is_won_is_closed_once_it_opens() -> None:
    late = Memory()
    release = threading.Event()

    def opening(route: str) -> Pipe:
        if route == "slow":
            release.wait(5)
            return late
        return Memory()

    def handshake(pipe: Pipe) -> str:
        return "won" if pipe is not late else "late"

    won = race(["slow", "fast"], opening, handshake, stagger=0.01)
    assert won.route == "fast"
    release.set()
    deadline = time.monotonic() + 5
    while not late.closed and time.monotonic() < deadline:
        time.sleep(0.01)
    assert late.closed


def test_no_route_is_refused() -> None:
    with pytest.raises(ValueError, match=r"^There is no route to try\.$"):
        race([], lambda _route: Memory(), lambda _pipe: None)


def test_the_stagger_is_a_quarter_second() -> None:
    assert STAGGER == 0.25


def test_the_wait_doubles_from_one_second_to_sixty_and_starts_again_once_up() -> None:
    backoff = Backoff()
    waits = [backoff.next() for _ in range(9)]
    assert waits == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0]
    assert (FIRST, LONGEST) == (1.0, 60.0)
    backoff.reset()
    assert backoff.next() == 1.0

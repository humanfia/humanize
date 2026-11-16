"""Two ends of one pipe held in memory, which is what every peer here runs over."""

import json
import threading
from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest

from hmz.rpc import Frames, Pipe


class End:
    """One end of an in-memory pipe: what the other end writes, this one reads."""

    def __init__(self) -> None:
        self.inbox = bytearray()
        self.shut = False
        self.cond = threading.Condition()
        self.other: End = self

    def read(self, size: int) -> bytes:
        with self.cond:
            self.cond.wait_for(lambda: bool(self.inbox) or self.shut)
            data = bytes(self.inbox[:size])
            del self.inbox[:size]
            return data

    def write(self, data: bytes) -> None:
        if self.shut:
            raise OSError("closed")
        with self.other.cond:
            if self.other.shut:
                raise OSError("closed")
            self.other.inbox += data
            self.other.cond.notify_all()

    def close(self) -> None:
        for end in (self, self.other):
            with end.cond:
                end.shut = True
                end.cond.notify_all()


def joined() -> tuple[End, End]:
    one, two = End(), End()
    one.other, two.other = two, one
    return one, two


@pytest.fixture
def pipes() -> Iterator[Callable[[], tuple[Pipe, Pipe]]]:
    made: list[End] = []

    def make() -> tuple[Pipe, Pipe]:
        one, two = joined()
        made.extend((one, two))
        return one, two

    yield make
    for end in made:
        end.close()


@pytest.fixture
def received() -> Callable[[Pipe], dict[str, Any]]:
    """Reads the next frame's JSON off a pipe that has no peer on it."""
    frames: dict[int, tuple[Frames, list[bytes]]] = {}

    def receive(pipe: Pipe) -> dict[str, Any]:
        reader, held = frames.setdefault(id(pipe), (Frames(), []))
        while not held:
            data = pipe.read(1 << 16)
            if not data:
                raise EOFError
            held.extend(reader.feed(data))
        return cast("dict[str, Any]", json.loads(held.pop(0)))

    return receive

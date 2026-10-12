"""How slices that overlap are laid out in rows, for every document a trace is drawn as."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["stacked"]


def stacked(spans: Iterable[tuple[float, float]]) -> list[tuple[int, int]]:
    """Packs slices into lanes in which each one nests inside the one under it.

    A slice goes into the first lane where it either starts after everything still open has
    ended or ends inside the slice open on top, so that a session, its turns and their calls
    read as one stack of bars; one that overlaps without nesting spills into the next lane.

    Args:
      spans: Each slice's start and end, sorted by start and then by end, latest first --
        which is what puts a slice before the ones inside it.

    Returns:
      Each slice's lane, from 0, and how deep it is inside that lane, from 0, in the order
      they were given. Two slices of one lane at one depth never overlap.
    """
    lanes: list[list[float]] = []
    placed: list[tuple[int, int]] = []
    for start, end in spans:
        lane = 0
        while lane < len(lanes):
            stack = lanes[lane]
            while stack and stack[-1] <= start:
                stack.pop()
            if not stack or stack[-1] >= end:
                break
            lane += 1
        if lane == len(lanes):
            lanes.append([])
        placed.append((lane, len(lanes[lane])))
        lanes[lane].append(end)
    return placed

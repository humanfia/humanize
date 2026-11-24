"""The nous: named ways of trying agents in turn (`nous.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["Nous"]


class Nous(Family):
    """The nous: named ways of trying agents in turn."""

    METHODS: ClassVar = ()

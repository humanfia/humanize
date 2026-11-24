"""Side questions asked beside an epic or a chat (`btw.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["SideQuestions"]


class SideQuestions(Family):
    """Side questions asked beside an epic or a chat."""

    METHODS: ClassVar = ()

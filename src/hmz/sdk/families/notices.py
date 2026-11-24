"""What a daemon tells its person: listed and subscribed to (`notices.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["Notices"]


class Notices(Family):
    """What a daemon tells its person: listed and subscribed to."""

    METHODS: ClassVar = ()

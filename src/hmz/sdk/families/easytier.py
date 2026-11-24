"""The EasyTier networks a daemon is reached over (`easytier.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["EasyTier"]


class EasyTier(Family):
    """The EasyTier networks a daemon is reached over."""

    METHODS: ClassVar = ()

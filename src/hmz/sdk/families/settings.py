"""A daemon's settings, and a workspace's (`settings.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["Settings"]


class Settings(Family):
    """A daemon's settings, and a workspace's."""

    METHODS: ClassVar = ()

"""Recorded epics: listed, read back, traced, exported, imported (`runs.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["Runs"]


class Runs(Family):
    """Recorded epics: listed, read back, traced, exported, imported."""

    METHODS: ClassVar = ()

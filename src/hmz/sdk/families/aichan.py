"""Ai-chan's conversations (`aichan.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["AiChan"]


class AiChan(Family):
    """Ai-chan's conversations."""

    METHODS: ClassVar = ()

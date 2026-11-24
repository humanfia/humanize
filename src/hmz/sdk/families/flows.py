"""The flows a daemon can run, and what runs them (`flows.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["Flows"]


class Flows(Family):
    """The flows a daemon can run, and what runs them."""

    METHODS: ClassVar = ()

"""The runtimes environments are made on (`runtimes.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["Runtimes"]


class Runtimes(Family):
    """The runtimes environments are made on."""

    METHODS: ClassVar = ()

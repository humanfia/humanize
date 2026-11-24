"""The daemon machine's directories, for choosing a folder (`paths.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["Paths"]


class Paths(Family):
    """The daemon machine's directories, for choosing a folder."""

    METHODS: ClassVar = ()

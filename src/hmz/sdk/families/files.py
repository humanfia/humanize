"""File handles: how bytes are carried to and from a daemon (`files.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["Files"]


class Files(Family):
    """File handles: how bytes are carried to and from a daemon."""

    METHODS: ClassVar = ()

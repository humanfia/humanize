"""What a backup target holds, and pulling it back (`backups.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["Backups"]


class Backups(Family):
    """What a backup target holds, and pulling it back."""

    METHODS: ClassVar = ()

"""The accounts agents are run as (`accounts.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["Accounts"]


class Accounts(Family):
    """The accounts agents are run as."""

    METHODS: ClassVar = ()

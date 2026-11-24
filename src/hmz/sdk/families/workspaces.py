"""The folders a daemon knows as workspaces (`workspaces.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["Workspaces"]


class Workspaces(Family):
    """The folders a daemon knows as workspaces."""

    METHODS: ClassVar = ()

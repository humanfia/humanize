"""A host's environments: files, terminals and git (`env.*`, `hosts.env.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["Envs"]


class Envs(Family):
    """A host's environments: files, terminals and git."""

    METHODS: ClassVar = ()

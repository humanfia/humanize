"""An epic of a host, as one of its frontends: started, steered, heard (`epic.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["Epics"]


class Epics(Family):
    """An epic of a host, as one of its frontends: started, steered, heard."""

    METHODS: ClassVar = ()

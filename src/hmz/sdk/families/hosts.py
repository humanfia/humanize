"""The hosts a daemon holds epics and chats in (`hosts.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["Hosts"]


class Hosts(Family):
    """The hosts a daemon holds epics and chats in."""

    METHODS: ClassVar = ()

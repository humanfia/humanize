"""Chats, and the sessions a harness ran on its own (`chat.*`, `chat.harness.*`)."""

from __future__ import annotations

from typing import ClassVar

from . import Family

__all__ = ["Chats"]


class Chats(Family):
    """Chats, and the sessions a harness ran on its own."""

    METHODS: ClassVar = ()

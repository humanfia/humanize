"""Settings: every setting Humanize has, opened over the screen by a key.

The page is `/settings` (:mod:`hmz.tui.settings`), which the command opens as well: a key for
it puts it on the hint line, so that it is reached without knowing there is a word to type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.tui.settings import menu
from hmz.tui.shell import View

if TYPE_CHECKING:
    from textual.app import App
    from textual.widget import Widget

__all__ = ["VIEWS"]


def _made(_app: App[None]) -> Widget:
    return menu()


VIEWS = (View("settings", "page", "Settings", _made, key="f2", hint="settings"),)

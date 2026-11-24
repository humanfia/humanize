"""Files, Changes, Terminal: an environment of the chat or epic in front, beside its log.

What `/env` opens over the log, these open next to it, so that what an agent says and the
files it is changing are read side by side: the pane stays open while the prompt is typed
at, takes the keys only when its key is pressed, and gives them back on `esc`. Each shows
the environment its chat or epic was last turned to that has that page -- `tab` turns to the
next where there are several -- and `ctrl+w` makes the context wider, which a diff and a
terminal want.

What each pane is, and what it asks the host, is in `hmz.tui.envs`; this says where they
open and on which keys. The keys a pane takes change with what is open in it -- a tree or a
file, a list or a diff, a row of tabs or a terminal that takes every key -- so each pane says
them itself, on a line at its foot, rather than in one fixed list here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from hmz.tui.envs import ChangesPane, FilesPane, Pane, Reach, TerminalPane
from hmz.tui.shell import View

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import App

__all__ = ["VIEWS"]


def _reach(app: App[None]) -> Reach:
    """The host as the interface reaches it; one that holds no environment where it has none."""
    held = getattr(app, "reach", None)
    return held if isinstance(held, Reach) else Reach(lambda _said: {}, lambda: ())


def _made(pane: type[Pane]) -> Callable[[App[None]], Pane]:
    """What makes one pane for an interface."""

    def made(app: App[None]) -> Pane:
        return pane(_reach(app), cast("App[Any]", app))

    return made


VIEWS = (
    View(
        "files",
        "context",
        "Files",
        _made(FilesPane),
        key="f5",
        hint="Files",
    ),
    View(
        "changes",
        "context",
        "Changes",
        _made(ChangesPane),
        key="f6",
        hint="Changes",
    ),
    View(
        "terminal",
        "context",
        "Terminal",
        _made(TerminalPane),
        key="f7",
        hint="Terminal",
    ),
)

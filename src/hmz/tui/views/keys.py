"""Keys: every key that opens something, and what it opens."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Static

from hmz.tui import humanfia
from hmz.tui.shell import View, views
from hmz.words import t

if TYPE_CHECKING:
    from textual.app import App

__all__ = ["VIEWS"]


class Keys(Static, can_focus=True):
    """The keys, a line apiece: the key in cyan, since it is what can be followed."""

    DEFAULT_CSS = """
    Keys { padding: 1 1; height: auto; color: $foreground; }
    """

    def on_mount(self) -> None:
        """Writes them: what works from anywhere, then going back."""
        keyed = [(view.key, view.hint) for view in views().values() if view.key]
        keyed.append(("esc", "Back"))
        wide = max(len(key) for key, _ in keyed)
        lines = [f"[$hmz-ink-3]{t('These keys work from anywhere.')}[/]", ""]
        lines += [
            f"[b $primary]{key.ljust(wide)}[/]  {humanfia.POINT} {t(does)}"
            for key, does in keyed
        ]
        self.update("\n".join(lines))


def _made(_app: App[None]) -> Keys:
    return Keys()


VIEWS = (View("keys", "context", "Keys", _made, key="f1", hint="keys"),)

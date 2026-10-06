"""`hmz.tui`: the package says one thing, the interface."""

from __future__ import annotations

from textual.app import App

import hmz.tui
from hmz.tui.app import Humanize


def test_the_package_exports_the_interface_alone() -> None:
    assert hmz.tui.__all__ == ["Humanize"]
    assert hmz.tui.Humanize is Humanize


def test_the_interface_is_a_textual_app() -> None:
    assert issubclass(hmz.tui.Humanize, App)

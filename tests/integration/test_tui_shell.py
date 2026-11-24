"""The zones of the real interface: nothing beside the log until a view's key is pressed."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.tui import Humanize
from hmz.tui.shell import Zone
from tests.integration.doubles_tui import SIZE, screen, stand_in, until

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.timeout(120)]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, really asked what it runs as the interface opens."""
    del asking
    return stand_in(tmp_path, monkeypatch)


@pytest.mark.usefixtures("workspace")
async def test_f1_opens_the_keys_beside_the_log_and_esc_gives_the_prompt_the_keys_back() -> (
    None
):
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        context = app.query_one("#context", Zone)
        assert app.theme == "humanfia-dark"
        assert not context.has_class("open")
        await until(pilot, lambda: "F1 keys" in screen(app), "the hint line")

        await pilot.press("f1")
        await until(pilot, lambda: "KEYS" in screen(app), "the keys")

        assert context.has_class("open")
        assert "These keys work from anywhere." in screen(app)
        assert "esc Back" in screen(app)
        assert app.focused is not None
        assert app.focused.id != "editor"

        await pilot.press("escape")
        await until(
            pilot, lambda: getattr(app.focused, "id", "") == "editor", "the prompt"
        )
        assert context.has_class("open")

        await pilot.press("f1")
        await pilot.press("f1")
        await until(pilot, lambda: not context.has_class("open"), "the zone to close")
        assert getattr(app.focused, "id", "") == "editor"

"""`/settings`: walking its pages, and what is saved there landing in the settings file."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from hmz.tui import Humanize
from hmz.tui.settings import PAGES, Adjusts
from tests.integration.doubles_tui import (
    SIZE,
    leaves,
    on,
    opened,
    opens,
    picks,
    rows,
    shows,
    stand_in,
    trail,
    typed,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, really asked what it runs as the interface opens."""
    del asking
    return stand_in(tmp_path, monkeypatch)


def kept(tmp_path: Path) -> dict[str, object]:
    """The settings file, as read back, or nothing where none was written."""
    at = tmp_path / "humanize-home" / "settings.yaml"
    return dict(yaml.safe_load(at.read_text()) or {}) if at.exists() else {}


async def into_settings(pilot: Pilot[None], page: str = "") -> Adjusts:
    """Opens `/settings`, on one of its pages where one is named."""
    await opened(pilot)
    await typed(pilot, f"/settings {page}".strip())
    return await on(pilot, Adjusts)


async def test_settings_opens_on_its_five_pages_and_esc_closes_it(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await into_settings(pilot)

        assert rows(app) == list(PAGES)
        await shows(pilot, "General", "Accounts", "Fallback", "Runtimes", "Workspace")

        await pilot.press("escape")
        await shows(pilot, "◉ chat")
        assert len(app.screen_stack) == 1


async def test_details_turned_on_and_saved_is_written_and_applied(
    workspace: Path, tmp_path: Path
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await into_settings(pilot)
        await opens(pilot, "general")
        await shows(pilot, "show every tool call and all of the thinking")

        await picks(pilot, "details", "on")
        await shows(pilot, "● on")
        await leaves(pilot)

        await shows(pilot, "showing details")
    assert kept(tmp_path)["details"] is True

    async with Humanize().run_test(size=SIZE) as pilot:
        await into_settings(pilot)
        await shows(pilot, "details on")


async def test_a_change_discarded_on_the_way_out_is_not_written(
    workspace: Path, tmp_path: Path
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await into_settings(pilot)
        await opens(pilot, "general")
        await picks(pilot, "details", "on")
        await shows(pilot, "unsaved changes")

        await leaves(pilot, saving=False)

        await shows(pilot, "◉ chat")
    assert "details" not in kept(tmp_path)


async def test_a_page_named_on_the_command_opens_on_that_page(workspace: Path) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await into_settings(pilot, "workspace")

        await shows(
            pilot,
            trail("/settings", "Workspace"),
            f"What {workspace.parent.name}/workspace remembers",
        )


async def test_a_page_that_is_not_one_is_said_so(workspace: Path) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/settings nowhere")

        await shows(pilot, "has no page 'nowhere'")


async def test_the_accounts_and_runtimes_pages_start_empty(workspace: Path) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await into_settings(pilot)
        await shows(pilot, "0 accounts", "0 machines")

        await opens(pilot, "accounts")
        await shows(pilot, "no accounts yet", "Add an account")

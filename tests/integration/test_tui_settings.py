"""`/settings`: walking its pages, and what is saved there landing in the settings file."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest
import yaml
from textual.widgets import OptionList

from hmz.tui import Humanize
from hmz.tui.dropdown import Dropdown
from hmz.tui.pick import Slurming
from hmz.tui.settings import PAGES, Adjusts
from tests.integration.doubles_tui import (
    SIZE,
    leaves,
    on,
    onto,
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


async def test_settings_opens_on_its_seven_pages_and_esc_closes_it(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await into_settings(pilot)

        assert rows(app) == list(PAGES)
        await shows(
            pilot,
            "General",
            "Notifications",
            "Accounts",
            "Fallback",
            "Runtimes",
            "Backup",
            "Workspace",
        )

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


@pytest.mark.parametrize("gatewayable", [True, False])
async def test_the_ways_through_the_gateway_are_dropped_under_one_heading(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, *, gatewayable: bool
) -> None:
    from hmz.coganchor import backends, gateway

    claude = backends.named("claude")
    assert claude is not None
    monkeypatch.setattr(gateway, "gatewayable", lambda: gatewayable)
    async with Humanize().run_test(size=SIZE) as pilot:
        await into_settings(pilot, "accounts")
        await pilot.click("#act-add")
        await shows(pilot, "Add an account")
        await opens(pilot, "way")
        dropped = await on(pilot, Dropdown)

        options = dropped.query_one(OptionList).options
        listed = [str(one.id or "") for one in options]
        heading = listed.index("")
        # The CLI's own ways first, then the heading and every way under it, or the line.
        assert all(one.startswith("=") for one in listed[:heading])
        assert not any(one.startswith("=litellm-") for one in listed[:heading])
        if gatewayable:
            assert listed[heading + 1 :] == [
                f"={one.name}" for one in backends.routed(claude)
            ]
        else:
            assert listed[heading + 1 :] == [""]
        # The list runs past the bottom of what it shows, and the heading is near its end.
        await pilot.press("end")
        await shows(
            pilot,
            "litellm-azure" if gatewayable else "litellm is not installed; run: uv pip",
        )


#: A stand-in `sinfo`: Slurm's version, and three nodes of which two may take a job.
_SINFO = """
import sys

if "--version" in sys.argv:
    print("slurm 23.02.7")
else:
    print("gpu-01|64|512000|idle")
    print("gpu-02|64|512000|mix")
    print("gpu-03|64|512000|drain")
"""


async def test_a_slurm_cluster_made_on_its_form_is_saved_listed_and_checked(
    workspace: Path, tmp_path: Path
) -> None:
    sinfo = tmp_path / "bin" / "sinfo"
    sinfo.write_text(f"#!{sys.executable}\n{_SINFO}")
    sinfo.chmod(0o755)
    async with Humanize().run_test(size=SIZE) as pilot:
        await into_settings(pilot, "runtimes")
        await pilot.click("#act-add")
        await on(pilot, Dropdown)
        await onto(pilot, "slurm", "OptionList")
        await pilot.press("enter")
        await on(pilot, Slurming)
        await shows(pilot, "Add a Slurm cluster")

        await onto(pilot, "partition")
        await pilot.press(*"gpu", "enter")
        await onto(pilot, "max_jobs")
        await pilot.press("4", "enter")
        await pilot.click("#act-done")

        await shows(
            pilot,
            "slurm/gpu answers: slurm 23.02.7; 2 nodes: gpu-01, gpu-02; "
            "128 CPUs, 1000G all told",
            "partition gpu · no limits · max 4 jobs",
        )
    saved = kept(tmp_path)["runtimes"]
    assert isinstance(saved, dict)
    assert saved["slurm"]["gpu"]["partition"] == "gpu"
    assert saved["slurm"]["gpu"]["max_jobs"] == 4

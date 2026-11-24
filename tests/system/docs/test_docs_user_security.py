"""The pictures of `docs/user/security.md`: what holds an agent, and who reaches the daemon.

A chat's permission picked from its chip in the app; another machine, `laptop`, paired with
this one's daemon by a code, as the page's Settings lists it and as `hmz daemon devices`
lists and revokes it; and the switch for error reports, in the page and in the terminal.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_security.py`.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.conftest import own
from tests.integration.doubles_tui import onto, shows, typed
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

_PAGE = "user-security"

#: The other machine, as this one's daemon is told it is called.
_LAPTOP = "laptop"

_CLAIMS = """
import sys
from hmz.runtime.doing.daemons import Remotes
remotes = Remotes()
try:
    remotes.pair("studio", sys.argv[1], device=sys.argv[2])
finally:
    remotes.close()
"""


def _paired(world: World) -> None:
    """Pairs a machine called `laptop` with the world's daemon, by a code it claims.

    The daemon listens on a port of loopback and makes a code; a Python under a home of
    its own, which has a device key of its own, claims it as another machine would.
    """
    world.call("settings.set", listen=["tcp://127.0.0.1:0"])
    code = world.call("pair.create")["code"]
    base = world.home.parent
    home = base / _LAPTOP / "alex"
    home.mkdir(parents=True)
    there = dict(
        os.environ,
        HOME=str(home),
        **own(home),
        # Short, as a socket's path under it must be.
        TMPDIR=tempfile.mkdtemp(prefix="l", dir=str(base)),
    )
    subprocess.run(
        [sys.executable, "-c", _CLAIMS, code, _LAPTOP],
        env=there,
        check=True,
        timeout=120,
    )


def test_a_chat_is_held_to_a_permission(world: World) -> None:
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        expect(page.get_by_role("textbox", name="First message")).to_be_visible()
        expect(
            page.get_by_role("button", name=re.compile("Nous: .*Haiku"))
        ).to_be_visible()
        chip = page.locator("[data-hmz=permission]").first
        expect(chip).to_contain_text("Edit this folder")
        reel = shots.Reel(f"{_PAGE}-permission", window="desktop")
        reel.web(page, hold=1.6, pointer=chip, click=True)
        chip.click()
        menu = page.get_by_role("menu", name="Permissions")
        expect(menu).to_be_visible()
        read = menu.locator("[data-permission=read-only]")
        page.wait_for_timeout(300)
        reel.web(page, hold=3.2, pointer=read, click=True, poster=True)
        read.click()
        expect(chip).to_contain_text("Read only")
        page.wait_for_timeout(300)
        reel.web(page, hold=2.4)
        reel.save()


def test_a_paired_device_is_listed_in_settings(world: World) -> None:
    _paired(world)
    with world.page(desktop=True) as page:
        go(page, "/settings/daemons")
        device = page.locator(f"[data-hmz=device][data-name={_LAPTOP}]").first
        expect(device).to_be_visible()
        revoke = device.get_by_role("button", name="Revoke")
        expect(revoke).to_be_visible()
        page.wait_for_timeout(300)
        shots.web(
            page,
            f"{_PAGE}-devices",
            clip="[data-hmz=daemons]",
            pad=8,
            pointer=revoke,
        )


def test_devices_are_listed_and_revoked_from_the_command_line(world: World) -> None:
    _paired(world)
    reel = shots.Reel(f"{_PAGE}-revoke")
    reel.cli(["hmz", "daemon", "devices"], columns=100, rows=6, hold=3.0)
    reel.cli(
        ["hmz", "daemon", "devices", "revoke", _LAPTOP], columns=100, rows=6, hold=3.5
    )
    reel.save()


def test_error_reports_are_switched_in_settings(world: World) -> None:
    with world.page(desktop=True) as page:
        go(page, "/settings/general")
        reports = page.get_by_label(re.compile("Report Humanize.s own failures"))
        expect(reports).to_be_visible()
        page.wait_for_timeout(300)
        shots.web(page, f"{_PAGE}-reports", window="desktop")


async def test_the_terminal_says_what_a_report_holds(world: World) -> None:
    async with world.tui((100, 36)) as (app, pilot):
        await shows(pilot, MODEL)
        await typed(pilot, "/settings general")
        await shows(pilot, "Error reports", "What is sent")
        await onto(pilot, "sent")
        await pilot.press("enter")
        await shows(pilot, "Never sent")
        await pilot.pause(0.3)
        shots.tui(app, f"{_PAGE}-terminal")

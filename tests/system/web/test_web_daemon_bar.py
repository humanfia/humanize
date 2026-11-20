"""The daemon bar at the foot of `hmz web`'s sidebar, and the picker it opens.

The bar names the daemon the page is of, its host and how it stands; the picker lists every
daemon this browser keeps, switches to one, connects one that failed and opens where they are
managed. `lab` is another machine's daemon, real and paired; `farm` is kept, but nothing answers
where it is reached.
"""

from __future__ import annotations

import re
import socket
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, another, kept, opened, paired

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.parametrize("engine", ENGINES)

#: A daemon kept, pinned, whose route nothing listens on.
_FARM = {"name": "farm", "id": "a" * 52, "routes": ["tcp://127.0.0.1:9"]}

#: This machine, as its daemons say hello: Local and `lab` alike.
_HOST = socket.gethostname().split(".")[0]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, asked what it runs, and a project to serve."""
    return install(tmp_path, monkeypatch)


def test_the_bar_names_the_daemon_and_its_picker_switches(
    project: Path, tmp_path: Path, engine: str
) -> None:
    with (
        another(tmp_path) as lab,
        served() as site,
        opened(site, engine=engine) as page,
    ):
        paired(page, "lab", lab.code())
        kept(page, _FARM)
        bar = page.locator("[data-hmz=daemon-bar]")
        expect(bar.locator("[data-hmz=daemon-name]")).to_have_text("Local")
        expect(bar.locator("[data-hmz=daemon-host]")).to_have_text(_HOST)
        expect(bar.locator("[data-hmz=state]")).to_have_text("idle")

        bar.click()
        picker = page.locator("[data-hmz=daemon-picker]")
        expect(picker).to_have_attribute("role", "menu")
        expect(
            picker.locator(
                ":scope > .choice .choice-label, :scope > .choice-sub > .choice .choice-label"
            )
        ).to_have_text(["Daemon", "Settings", "Usage"])
        # The daemons open beside it, under Daemon rather than as a heading.
        picker.get_by_role("menuitem", name=re.compile(r"^Daemon")).click()
        daemons = page.locator("[data-hmz=daemons]")
        expect(daemons.locator(".choice-label")).to_have_text(
            ["Local", "farm", "lab", "Manage"]
        )
        expect(daemons.locator(".choice.chosen .choice-label")).to_have_text("Local")

        # Picked, a remote daemon is reached: `lab` over its route, through `/dial`.
        daemons.get_by_role("menuitem", name=re.compile(r"^lab")).click()
        page.wait_for_url(re.compile(r".*#/@lab/new/chat$"))
        expect(bar.locator("[data-hmz=daemon-name]")).to_have_text("lab")
        expect(bar.locator("[data-hmz=daemon-host]")).to_have_text(_HOST)
        expect(bar).to_have_attribute("data-state", "up")

        # `farm` fails, saying why, and is offered to connect again.
        bar.click()
        picker.get_by_role("menuitem", name=re.compile(r"^Daemon")).hover()
        daemons.get_by_role("menuitem", name=re.compile(r"^farm")).click()
        page.wait_for_url(re.compile(r".*#/@farm/new/chat$"))
        expect(bar).to_have_attribute("data-state", "failed")
        bar.click()
        picker.get_by_role("menuitem", name=re.compile(r"^Daemon")).click()
        expect(daemons.locator(".choice-label")).to_have_text(
            ["Local", "farm", "Connect", "lab", "Manage"]
        )
        daemons.get_by_role("menuitem", name="Connect").click()
        expect(picker).to_have_count(0)
        expect(page.locator(".toast")).to_have_text("Connecting farm")

        # One popup at a time: the box's menu opened by the keyboard, with no press outside
        # the picker, shuts the picker and the menu open beside it.
        bar.click()
        picker.get_by_role("menuitem", name=re.compile(r"^Daemon")).click()
        expect(daemons).to_be_visible()
        add = page.locator("[data-hmz=composer-add]")
        add.focus()
        page.keyboard.press("Enter")
        expect(add).to_have_attribute("aria-expanded", "true")
        expect(picker).to_have_count(0)
        expect(daemons).to_have_count(0)
        page.keyboard.press("Escape")
        expect(add).to_have_attribute("aria-expanded", "false")
        expect(add).to_be_focused()

        bar.click()
        picker.get_by_role("menuitem", name=re.compile(r"^Daemon")).press("ArrowRight")
        daemons.get_by_role("menuitem", name="Manage").click()
        page.wait_for_url(re.compile(r".*#/@farm/settings/daemons$"))


def test_with_no_daemon_kept_the_bar_is_local(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine, width=375) as page:
        page.locator("[data-hmz=bar] .bar-side").click()
        bar = page.locator("[data-hmz=daemon-bar]")
        expect(bar.locator("[data-hmz=daemon-name]")).to_have_text("Local")
        bar.click()
        picker = page.locator("[data-hmz=daemon-picker]")
        picker.get_by_role("menuitem", name=re.compile(r"^Daemon")).click()
        expect(picker.locator(".choice-label")).to_have_text(
            ["Daemon", "Local", "Manage", "Settings", "Usage"]
        )

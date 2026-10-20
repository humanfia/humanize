"""The daemon bar at the foot of `hmz web`'s sidebar, and the picker it opens.

The bar names the daemon the page is of, its host and how it stands; the picker lists every
daemon the machine serving the page keeps, switches to one, connects one that failed and
opens where they are managed. The daemons are answered here, as the machine would.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, opened

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.parametrize("engine", ENGINES)

_DAEMONS = [
    {"name": "local", "host": "here", "state": "up"},
    {"name": "lab", "host": "lab.example", "state": "up"},
    {"name": "farm", "host": "farm.example", "state": "failed"},
]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, asked what it runs, and a project to serve."""
    return install(tmp_path, monkeypatch)


def _answering(status: int, body: object) -> str:
    """A script answering the daemons, and connecting one, as a machine would, before the page asks.

    The page is let in by the address as it opens, so the answer is given in the page itself.
    """
    return f"""
        window.hmzConnected = []
        const fetched = window.fetch.bind(window)
        window.fetch = (url, how) => {{
          const path = new URL(String(url), location.href).pathname
          const json = (code, said) => new Response(JSON.stringify(said), {{
            status: code, headers: {{ 'Content-Type': 'application/json' }},
          }})
          if (path === '/api/daemons') return Promise.resolve(json({status}, {json.dumps(body)}))
          const connect = /^\\/api\\/daemons\\/([^/]+)\\/connect$/.exec(path)
          if (connect) {{
            window.hmzConnected.push(connect[1])
            // Held, where the test says so, until it lets the daemon answer.
            if (window.hmzHold) return new Promise((answer) => {{
              window.hmzAnswer = () => answer(json(200, {{}}))
            }})
            return Promise.resolve(json(200, {{}}))
          }}
          return fetched(url, how)
        }}
    """


def test_the_bar_names_the_daemon_and_its_picker_switches(
    project: Path, engine: str
) -> None:
    with (
        served() as site,
        opened(site, engine=engine, init=_answering(200, _DAEMONS)) as page,
    ):
        bar = page.locator("[data-hmz=daemon-bar]")
        expect(bar.locator("[data-hmz=daemon-name]")).to_have_text("Local")
        expect(bar.locator("[data-hmz=daemon-host]")).to_have_text("here")
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
            ["Local", "lab", "farm", "Connect", "Manage"]
        )
        expect(daemons.locator(".choice.chosen .choice-label")).to_have_text("Local")

        # One that failed is connected again.
        daemons.get_by_role("menuitem", name="Connect").click()
        expect(picker).to_have_count(0)
        assert page.evaluate("window.hmzConnected") == ["farm"]

        bar.click()
        picker.get_by_role("menuitem", name=re.compile(r"^Daemon")).hover()
        daemons.get_by_role("menuitem", name=re.compile(r"^lab")).click()
        page.wait_for_url(re.compile(r".*#/@lab/new$"))
        expect(bar.locator("[data-hmz=daemon-name]")).to_have_text("lab")
        expect(bar.locator("[data-hmz=daemon-host]")).to_have_text("lab.example")

        bar.click()
        picker.get_by_role("menuitem", name=re.compile(r"^Daemon")).press("ArrowRight")
        daemons.get_by_role("menuitem", name="Manage").click()
        page.wait_for_url(re.compile(r".*#/@lab/settings/daemons$"))


def test_connecting_says_so_until_the_daemon_answers(
    project: Path, engine: str
) -> None:
    with (
        served() as site,
        opened(site, engine=engine, init=_answering(200, _DAEMONS)) as page,
    ):
        page.evaluate("window.hmzHold = true")
        bar = page.locator("[data-hmz=daemon-bar]")
        bar.click()
        picker = page.locator("[data-hmz=daemon-picker]")
        picker.get_by_role("menuitem", name=re.compile(r"^Daemon")).click()
        page.locator("[data-hmz=daemons]").get_by_role(
            "menuitem", name="Connect"
        ).click()
        working = page.locator("[data-hmz=working]")
        expect(working).to_have_text("Connecting farm…")
        expect(working).to_have_attribute("role", "status")

        page.evaluate("window.hmzAnswer()")
        expect(working).to_have_count(0)
        expect(page.locator(".toast")).to_have_text("Connecting farm")


def test_without_daemons_the_bar_is_local(project: Path, engine: str) -> None:
    missing = {"error": "Nothing is here."}
    with (
        served() as site,
        opened(site, engine=engine, width=375, init=_answering(404, missing)) as page,
    ):
        page.locator("[data-hmz=bar] .bar-side").click()
        bar = page.locator("[data-hmz=daemon-bar]")
        expect(bar.locator("[data-hmz=daemon-name]")).to_have_text("Local")
        bar.click()
        picker = page.locator("[data-hmz=daemon-picker]")
        picker.get_by_role("menuitem", name=re.compile(r"^Daemon")).click()
        expect(picker.locator(".choice-label")).to_have_text(
            ["Daemon", "Local", "Manage", "Settings", "Usage"]
        )

"""Settings, per daemon.

The app's own pages apart from a daemon's, which daemon those read and write, and what a page
holds copied to several daemons at once.

The daemons are the browser's to fake: the list of them is answered in the page's browser, and
so is everything sent to the remote ones -- `gpu` mirrors what Local reads and takes whatever
is written to it, and `lab` refuses everything, as a daemon that is not up does.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, go, opened

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Page, Route

pytestmark = pytest.mark.parametrize("engine", ENGINES)

#: Every daemon the page is told of: Local, one that is up and one that is not.
_DAEMONS = {
    "daemons": [
        {"name": "local", "state": "up"},
        {"name": "gpu", "host": "gpu.example", "state": "up"},
        {"name": "lab", "host": "lab.example", "state": "failed"},
    ]
}


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, asked what it runs, and a project to serve."""
    return install(tmp_path, monkeypatch)


def _daemons(page: Page) -> list[tuple[str, str, Any]]:
    """Fakes every daemon but Local, keeping what each was asked: its name, method and body."""
    asked: list[tuple[str, str, Any]] = []

    def listed(route: Route) -> None:
        route.fulfill(json=_DAEMONS)

    def remote(route: Route) -> None:
        request = route.request
        found = re.match(r".*/d/([^/]+)(/api/.*)", request.url)
        assert found
        name, path = found.groups()
        if name == "local":
            # The page's own daemon, which it asks as it asks everything: no fake of it.
            route.fallback()
            return
        body = json.loads(request.post_data) if request.post_data else None
        asked.append((name, f"{request.method} {path.split('?')[0]}", body))
        if name == "lab":
            route.fulfill(status=409, json={"error": "lab is not up."})
        elif request.method == "POST":
            route.fulfill(json={})
        else:
            route.fulfill(response=route.fetch(url=request.url.replace("/d/gpu", "")))

    page.route(re.compile(r".*/api/daemons$"), listed)
    page.route(re.compile(r".*/d/[^/]+/api/.*"), remote)
    return asked


def test_the_app_and_the_daemon_are_set_apart(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/general")
        nav = page.locator(".settings-nav")
        expect(nav.locator(".settings-group")).to_have_text(["App", "Daemon"])
        expect(nav.locator("a:visible").first).to_have_text("Themes")
        expect(nav.locator("a:visible")).to_contain_text(
            ["Themes", "General", "Accounts", "Fallback", "Runtimes", "Backup"]
        )
        picker = page.locator("[data-hmz=settings-daemon]")
        expect(picker.locator("option")).to_have_text(["Local"])
        go(page, "/settings/themes")
        expect(page.locator("[data-hmz=settings-daemon]")).to_have_count(0)


def test_the_daemon_picked_is_the_one_read_and_written(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        asked = _daemons(page)
        go(page, "/settings/general")
        picker = page.locator("[data-hmz=settings-daemon]")
        expect(picker.locator("option")).to_have_text(["Local", "gpu", "lab"])
        expect(picker).to_have_value("local")
        assert not asked

        picker.select_option("gpu")
        expect(page.locator("[data-hmz=btw-whom]")).to_be_visible()
        assert ("gpu", "GET /api/settings", None) in asked
        assert ("gpu", "GET /api/backends", None) in asked
        assert "daemon=gpu" in page.url
        expect(page.locator(".settings-nav a", has_text="Backup")).to_have_attribute(
            "href", "#/settings/backup?daemon=gpu"
        )

        page.get_by_role("button", name="Save").click()
        expect(page.get_by_role("button", name="Saved")).to_be_visible()
        assert any(one[:2] == ("gpu", "POST /api/settings") for one in asked)

        # Kept in the address, the daemon is the one the page opens on again.
        asked.clear()
        go(page, "/settings/backup?daemon=gpu")
        expect(page.locator("[data-hmz=backups] h2")).to_have_text("Targets")
        expect(page.locator("[data-hmz=settings-daemon]")).to_have_value("gpu")
        assert ("gpu", "GET /api/settings", None) in asked


def test_batch_apply_sends_the_page_to_each_daemon_ticked(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        asked = _daemons(page)
        go(page, "/settings/general")
        page.locator("[data-hmz=settings-general] input[type=checkbox]").check()
        page.locator("[data-hmz=batch-apply]").click()
        dialog = page.locator("[data-hmz=batch-dialog]")
        expect(dialog.locator("label.check")).to_have_text(["All", "gpu", "lab"])
        dialog.locator("[data-hmz=batch-all]").check()
        dialog.locator("[data-hmz=batch-go]").click()

        results = dialog.locator("[data-hmz=batch-result]")
        expect(results.and_(page.locator("[data-daemon=gpu]"))).to_contain_text(
            "Applied"
        )
        expect(results.and_(page.locator("[data-daemon=lab]"))).to_contain_text(
            "lab is not up."
        )
        sent = [one for one in asked if one[1] == "POST /api/settings"]
        assert sorted(one[0] for one in sent) == ["gpu", "lab"]
        assert all(one[2]["details"] is True for one in sent)

        # Closed, it leaves Settings open; nothing was written on Local.
        page.keyboard.press("Escape")
        expect(dialog).to_have_count(0)
        expect(page.locator("[data-hmz=settings-general]")).to_be_visible()


def test_accounts_keep_their_secrets_on_their_daemon(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _daemons(page)
        go(page, "/settings/accounts")
        expect(page.locator("[data-hmz=batch-apply]")).to_be_disabled()
        expect(page.locator("[data-hmz=batch-off]")).to_have_text("Secrets stay put")
        go(page, "/settings/usage")
        expect(page.locator("[data-hmz=usage] .panel").first).to_be_visible()
        expect(page.locator("[data-hmz=batch-apply]")).to_have_count(0)


def test_settings_fit_a_phone(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine, width=390, height=800) as page:
        _daemons(page)
        go(page, "/settings/runtimes")
        expect(page.locator("[data-hmz=settings-daemon]")).to_be_visible()
        page.locator("[data-hmz=batch-apply]").click()
        dialog = page.locator("[data-hmz=batch-dialog]")
        expect(dialog).to_be_visible()
        box = dialog.bounding_box()
        assert box
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= 390

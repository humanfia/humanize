"""Settings, per daemon.

The app's own pages apart from a daemon's, which daemon those read and write, and what a page
holds copied to several daemons at once.

The daemons are the browser's to fake: the list of them is answered in the page's browser, and
so is everything sent to the remote ones -- `gpu` mirrors what Local reads and takes whatever
is written to it, and `lab` refuses everything, as a daemon that is not up does.

Then the New daemon form, in each kind and mode: SSH Config and hmz-stored against the real
daemons, with an ssh config in the test's home; EasyTier against a registry and a community
node list faked in the browser.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, go, opened

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from playwright.sync_api import Locator, Page, Request, Route

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


#: A host of the ssh config, as `ssh -G` resolves it.
_SSH_CONFIG = """\
Host gpu
  HostName gpu.example
  User ann
  Port 2200
  IdentityFile ~/.ssh/gpu
"""


def _ssh_config(project: Path) -> None:
    """Writes the ssh config of the test's home."""
    ssh = project.parent / "home" / ".ssh"
    ssh.mkdir(parents=True)
    (ssh / "config").write_text(_SSH_CONFIG)


def _pressed(form: Locator, group: str) -> Locator:
    return form.locator(f"[data-hmz={group}] button[aria-pressed=true]")


def _written(request: Request) -> bool:
    return request.method == "POST" and request.url.endswith("/api/daemons")


def _fields(request: Request) -> dict[str, Any]:
    """What a write of a daemon said it is reached by."""
    return json.loads(request.post_data or "{}")["fields"]


def test_a_host_of_the_ssh_config_is_picked(project: Path, engine: str) -> None:
    _ssh_config(project)
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/daemons")
        form = page.locator("[data-hmz=write-daemon]")
        expect(_pressed(form, "daemon-kind")).to_have_text("SSH")
        expect(_pressed(form, "daemon-mode")).to_have_text("SSH Config")
        form.locator("#daemon-alias").select_option("gpu")
        expect(form.get_by_label("Name")).to_have_value("gpu")
        with page.expect_request(_written) as sent:
            form.get_by_role("button", name="Add", exact=True).click()
        assert _fields(sent.value) == {"via": "ssh", "alias": "gpu"}
        row = page.locator("[data-hmz=daemon][data-name=gpu]")
        expect(row.locator("[data-hmz=daemon-via]")).to_have_text("SSH · SSH Config")

        # Edited, it opens in its own mode, its host picked.
        row.get_by_role("button", name="Edit").click()
        expect(_pressed(form, "daemon-mode")).to_have_text("SSH Config")
        expect(form.locator("#daemon-alias")).to_have_value("gpu")


def _resolved(route: Route) -> None:
    """The hosts of the ssh config, as `ssh -G` resolves them, which reads the real home's."""
    host = {
        "alias": "gpu",
        "name": "gpu",
        "host": "gpu.example",
        "user": "ann",
        "port": 2200,
        "identity_files": ["~/.ssh/gpu"],
        "proxy_jump": "",
    }
    route.fulfill(json={"hosts": [host]})


def test_a_stored_daemon_is_filled_from_the_ssh_config(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        page.route("**/api/daemons/hosts", _resolved)
        go(page, "/settings/daemons")
        form = page.locator("[data-hmz=write-daemon]")
        form.get_by_role("button", name="hmz-stored").click()
        form.locator("#daemon-import").select_option("gpu")
        form.locator("[data-hmz=daemon-import]").click()
        expect(form.get_by_label("Name")).to_have_value("gpu")
        expect(form.locator("#daemon-host")).to_have_value("gpu.example")
        expect(form.locator("#daemon-user")).to_have_value("ann")
        expect(form.locator("#daemon-port")).to_have_value("2200")
        expect(form.locator("#daemon-identity")).to_have_value("~/.ssh/gpu")
        form.get_by_label("Name").fill("box")
        with page.expect_request(_written) as sent:
            form.get_by_role("button", name="Add", exact=True).last.click()
        fields = _fields(sent.value)
        assert fields["via"] == "ssh"
        assert "alias" not in fields
        row = page.locator("[data-hmz=daemon][data-name=box]")
        expect(row.locator("[data-hmz=daemon-via]")).to_have_text("SSH · hmz-stored")
        expect(row).to_contain_text("ann@gpu.example:2200")

        row.get_by_role("button", name="Edit").click()
        expect(_pressed(form, "daemon-mode")).to_have_text("hmz-stored")
        expect(form.locator("#daemon-host")).to_have_value("gpu.example")


#: The community's shared nodes, as the list of them is answered.
_NODES = {
    "nodes": [
        {
            "url": "tcp://public.easytier.example:11010",
            "name": "Public",
            "version": "2.4.5",
            "up": True,
            "uptime": 99.9,
        },
        {
            "url": "udp://gone.example:11010",
            "name": "Gone",
            "version": "2.4.5",
            "up": False,
            "uptime": 12.5,
        },
    ]
}


class _Registry:
    """The daemons, as the page asks them, a P2P one written already; each write kept."""

    def __init__(self) -> None:
        self.daemons: list[dict[str, Any]] = [
            {
                "name": "far",
                "label": "far",
                "via": "easytier",
                "secret": True,
                "peers": ["tcp://mine.example:11010"],
                "state": "idle",
            }
        ]
        self.writes: list[dict[str, Any]] = []

    def answer(self, route: Route) -> None:
        path = urllib.parse.urlsplit(route.request.url).path
        if path == "/api/daemons/hosts":
            route.fulfill(json={"hosts": []})
            return
        if route.request.method == "POST":
            body = json.loads(route.request.post_data or "{}")
            self.writes.append(body)
            kept = {k: v for k, v in body["fields"].items() if k != "secret"}
            self.daemons = [one for one in self.daemons if one["name"] != body["name"]]
            self.daemons.append({"name": body["name"], **kept, "secret": True})
        listed = [{"name": "local", "state": "up"}, *self.daemons]
        route.fulfill(json={"daemons": listed})


def _registry(page: Page, nodes: Callable[[Route], None]) -> _Registry:
    fake = _Registry()
    page.route("**/api/daemons**", fake.answer)
    page.route("**/api/daemons/easytier/nodes", nodes)
    return fake


def _listing(route: Route) -> None:
    route.fulfill(json=_NODES)


def test_an_easytier_daemon_takes_a_secret_and_nodes(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        fake = _registry(page, _listing)
        go(page, "/settings/daemons")
        far = page.locator("[data-hmz=daemon][data-name=far]")
        expect(far.locator("[data-hmz=daemon-via]")).to_have_text("P2P · EasyTier")
        form = page.locator("[data-hmz=write-daemon]")
        kinds = form.locator("[data-hmz=daemon-kind]")
        kinds.get_by_role("button", name="P2P").click()
        expect(_pressed(form, "daemon-mode")).to_have_text("EasyTier")
        expect(form.locator("[data-hmz=daemon-mode] button")).to_have_count(1)
        expect(form.locator("#daemon-secret")).to_have_attribute("type", "password")
        community = form.locator("[data-hmz=daemon-community] label")
        expect(community).to_have_count(2)
        expect(community.first).to_contain_text("up")
        expect(community.first).to_contain_text("99.9% up in 24h")
        expect(community.last).to_contain_text("down")

        form.get_by_label("Name").fill("edge")
        community.first.locator("input").check()
        typed = form.locator("#daemon-node")
        typed.fill("relay.example")
        form.get_by_role("button", name="Add node").click()
        expect(form.locator(".error")).to_contain_text("tcp://host:port")
        typed.fill("wss://relay.example:443")
        typed.press("Enter")
        expect(form.locator("[data-hmz=daemon-own-nodes] input")).to_be_checked()

        # Fifteen bytes are too few; eight characters of two bytes each are enough.
        form.locator("#daemon-secret").fill("x" * 15)
        add = form.get_by_role("button", name="Add", exact=True)
        add.click()
        expect(form.locator(".error")).to_have_text(
            "A secret must be at least 16 bytes."
        )
        assert not fake.writes
        form.locator("#daemon-secret").fill("ü" * 8)
        add.click()
        expect(page.locator("[data-hmz=daemon][data-name=edge]")).to_be_visible()
        assert fake.writes == [
            {
                "name": "edge",
                "fields": {
                    "via": "easytier",
                    "secret": "ü" * 8,
                    "peers": [
                        "tcp://public.easytier.example:11010",
                        "wss://relay.example:443",
                    ],
                },
                "replace": False,
            }
        ]


def test_without_the_community_list_nodes_are_typed(project: Path, engine: str) -> None:
    def unreachable(route: Route) -> None:
        route.fulfill(status=503, json={"error": "The node list could not be read."})

    with served() as site, opened(site, engine=engine) as page:
        fake = _registry(page, unreachable)
        go(page, "/settings/daemons")
        form = page.locator("[data-hmz=write-daemon]")
        form.get_by_role("button", name="P2P").click()
        expect(form.locator("[data-hmz=daemon-nodes]")).to_contain_text(
            "The node list could not be read."
        )
        form.get_by_label("Name").fill("edge")
        form.locator("#daemon-secret").fill("a secret of enough bytes")
        add = form.get_by_role("button", name="Add", exact=True)
        add.click()
        expect(form.locator(".error").last).to_have_text(
            "Pick or add at least one node."
        )
        form.locator("#daemon-node").fill("tcp://mine.example:11010")
        form.get_by_role("button", name="Add node").click()
        add.click()
        expect(page.locator("[data-hmz=daemon][data-name=edge]")).to_be_visible()
        assert fake.writes[-1]["fields"]["peers"] == ["tcp://mine.example:11010"]


def test_an_easytier_daemon_edited_keeps_its_secret(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        fake = _registry(page, _listing)
        go(page, "/settings/daemons")
        far = page.locator("[data-hmz=daemon][data-name=far]")
        far.get_by_role("button", name="Edit").click()
        form = page.locator("[data-hmz=write-daemon]")
        expect(form.locator("h2")).to_have_text("Edit far")
        expect(_pressed(form, "daemon-kind")).to_have_text("P2P")
        expect(_pressed(form, "daemon-mode")).to_have_text("EasyTier")
        secret = form.locator("#daemon-secret")
        expect(secret).to_have_value("")
        expect(secret).to_have_attribute("placeholder", "Left empty, kept as it is")
        expect(form.locator("[data-hmz=daemon-community] label")).to_have_count(2)
        mine = form.locator("[data-node='tcp://mine.example:11010'] input")
        expect(mine).to_be_checked()
        form.get_by_role("button", name="Save").click()
        expect(form.locator("h2")).to_have_text("New daemon")
        assert fake.writes == [
            {
                "name": "far",
                "fields": {"via": "easytier", "peers": ["tcp://mine.example:11010"]},
                "replace": True,
            }
        ]

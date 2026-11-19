"""Settings, per daemon.

The app's own pages apart from a daemon's, which daemon those read and write, and what a page
holds copied to several daemons at once.

`gpu` is another machine's daemon, real and paired with this browser, reached through `/dial`;
`lab` is kept, but nothing answers where it is reached, as a daemon that is not up.

Then the New daemon form, in each kind and mode: Code against `gpu`'s pairing code; SSH Config
against the real ssh config of the test's home; Custom and EasyTier with what Local answers of
the ssh config, the community's nodes and the EasyTier entries faked on its wire.
"""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import (
    ENGINES,
    Wire,
    another,
    go,
    kept,
    opened,
    paired,
)

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Locator, Page

pytestmark = pytest.mark.parametrize("engine", ENGINES)

#: A daemon kept, pinned, whose route nothing listens on.
_LAB = {"name": "lab", "id": "a" * 52, "routes": ["tcp://127.0.0.1:9"]}


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, asked what it runs, and a project to serve."""
    return install(tmp_path, monkeypatch)


def _settings(page: Page, on: str) -> dict[str, Any]:
    """What a daemon's settings are now, as the page reads them."""
    return page.evaluate(
        "async (on) => (await import('/api.js')).call('settings.get', {}, { on })", on
    )


def _kept(page: Page) -> list[dict[str, Any]]:
    """Every remote daemon this browser keeps."""
    return page.evaluate("async () => (await import('/api.js')).daemons.list()")


def test_the_app_and_the_daemon_are_set_apart(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/general")
        nav = page.locator(".settings-nav")
        expect(nav.locator(".settings-group")).to_have_text(["App", "Daemon"])
        expect(nav.locator("a:visible").first).to_have_text("Themes")
        expect(nav.locator("a:visible")).to_contain_text(
            ["Themes", "General", "Accounts", "Nous", "Runtimes", "Backup"]
        )
        picker = page.locator("[data-hmz=settings-daemon]")
        expect(picker.locator("option")).to_have_text(["Local"])
        go(page, "/settings/themes")
        expect(page.locator("[data-hmz=settings-daemon]")).to_have_count(0)


def test_the_daemon_picked_is_the_one_read_and_written(
    project: Path, tmp_path: Path, engine: str
) -> None:
    with (
        another(tmp_path) as gpu,
        served() as site,
        opened(site, engine=engine) as page,
    ):
        paired(page, "gpu", gpu.code())
        kept(page, _LAB)
        go(page, "/settings/general")
        picker = page.locator("[data-hmz=settings-daemon]")
        expect(picker.locator("option")).to_have_text(["Local", "gpu", "lab"])
        expect(picker).to_have_value("local")

        picker.select_option("gpu")
        expect(page.locator("[data-hmz=ai-chan-nous]")).to_be_visible()
        assert "daemon=gpu" in page.url
        expect(page.locator(".settings-nav a", has_text="Backup")).to_have_attribute(
            "href", "#/settings/backup?daemon=gpu"
        )

        page.locator("[data-hmz=settings-general] input[type=checkbox]").check()
        page.get_by_role("button", name="Save").click()
        expect(page.get_by_role("button", name="Saved")).to_be_visible()
        assert _settings(page, "gpu")["details"] is True
        assert _settings(page, "local")["details"] is False

        # Kept in the address, the daemon is the one the page opens on again.
        go(page, "/settings/backup?daemon=gpu")
        expect(page.locator("[data-hmz=backups] h2")).to_have_text("Targets")
        expect(page.locator("[data-hmz=settings-daemon]")).to_have_value("gpu")

        # One that is not up is said to be unavailable, with its state.
        picker.select_option("lab")
        expect(page.locator("[data-hmz=settings-backup] .error")).to_contain_text(
            "lab is unavailable, failed"
        )


def test_batch_apply_sends_the_page_to_each_daemon_ticked(
    project: Path, tmp_path: Path, engine: str
) -> None:
    with (
        another(tmp_path) as gpu,
        served() as site,
        opened(site, engine=engine) as page,
    ):
        paired(page, "gpu", gpu.code())
        kept(page, _LAB)
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
            "lab is unavailable"
        )
        assert _settings(page, "gpu")["details"] is True

        # Closed, it leaves Settings open; nothing was written on Local.
        page.keyboard.press("Escape")
        expect(dialog).to_have_count(0)
        expect(page.locator("[data-hmz=settings-general]")).to_be_visible()
        assert _settings(page, "local")["details"] is False


def test_accounts_keep_their_secrets_on_their_daemon(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/accounts")
        expect(page.locator("[data-hmz=batch-apply]")).to_be_disabled()
        expect(page.locator("[data-hmz=batch-off]")).to_have_text("Secrets stay put")
        go(page, "/settings/usage")
        expect(page.locator("[data-hmz=usage] .panel").first).to_be_visible()
        expect(page.locator("[data-hmz=batch-apply]")).to_have_count(0)


def test_settings_fit_a_phone(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine, width=390, height=800) as page:
        kept(page, _LAB)
        go(page, "/settings/runtimes")
        expect(page.locator("[data-hmz=settings-daemon]")).to_be_visible()
        page.locator("[data-hmz=batch-apply]").click()
        dialog = page.locator("[data-hmz=batch-dialog]")
        expect(dialog).to_be_visible()
        box = dialog.bounding_box()
        assert box
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= 390


def _pressed(form: Locator, group: str) -> Locator:
    return form.locator(f"[data-hmz={group}] button[aria-pressed=true]")


def test_a_daemon_is_paired_by_its_code_and_pairs_devices(
    project: Path, tmp_path: Path, engine: str
) -> None:
    with (
        another(tmp_path) as gpu,
        served() as site,
        opened(site, engine=engine) as page,
    ):
        go(page, "/settings/daemons")
        form = page.locator("[data-hmz=write-daemon]")
        expect(_pressed(form, "daemon-kind")).to_have_text("Code")
        form.get_by_label("Name").fill("gpu")
        form.locator("#daemon-code").fill("hmz-pair:nope")
        add = form.get_by_role("button", name="Add", exact=True)
        add.click()
        expect(form.locator(".error")).to_have_text("That is not a pairing code.")
        assert _kept(page) == []

        form.locator("#daemon-code").fill(gpu.code())
        add.click()
        row = page.locator("[data-hmz=daemon][data-name=gpu]")
        expect(row.locator("[data-hmz=daemon-via]")).to_have_text("Paired")
        expect(row).to_contain_text(f"tcp://127.0.0.1:{gpu.port}")
        [entry] = _kept(page)
        assert entry["routes"] == [f"tcp://127.0.0.1:{gpu.port}"]
        assert len(entry["id"]) == 52

        # Reached, it lists this machine among its devices, paired as it is called.
        row.get_by_role("button", name="Connect").click()
        expect(row.locator("[data-hmz=daemon-state]")).to_contain_text("up")
        devices = page.locator("[data-hmz=daemon-devices][data-name=gpu]")
        expect(devices.locator("[data-hmz=device] b")).to_contain_text(
            [socket.gethostname().split(".")[0]]
        )
        devices.get_by_role("button", name="Pair a device").click()
        expect(devices.locator("[data-hmz=pairing-code] code")).to_contain_text(
            "hmz-pair:"
        )

        # Local listens nowhere: no code can be made of it, and the page says why.
        local = page.locator("[data-hmz=daemon-devices][data-name=local]")
        local.get_by_role("button", name="Pair a device").click()
        expect(local.locator(".error")).to_contain_text(
            "There is no route to pair over"
        )


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


def test_a_host_of_the_ssh_config_is_picked(project: Path, engine: str) -> None:
    _ssh_config(project)
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/daemons")
        form = page.locator("[data-hmz=write-daemon]")
        form.locator("[data-hmz=daemon-kind]").get_by_role("button", name="SSH").click()
        expect(_pressed(form, "daemon-mode")).to_have_text("SSH Config")
        form.locator("#daemon-alias").select_option("gpu")
        expect(form.get_by_label("Name")).to_have_value("gpu")
        form.get_by_role("button", name="Add", exact=True).click()
        row = page.locator("[data-hmz=daemon][data-name=gpu]")
        expect(row.locator("[data-hmz=daemon-via]")).to_have_text("SSH · SSH Config")
        assert _kept(page) == [{"name": "gpu", "id": "", "routes": ["stdio:ssh://gpu"]}]

        # Edited, it opens in its own mode, its host picked.
        row.get_by_role("button", name="Edit").click()
        expect(_pressed(form, "daemon-mode")).to_have_text("SSH Config")
        expect(form.locator("#daemon-alias")).to_have_value("gpu")


#: The hosts of the ssh config, as `ssh -G` resolves them, which reads the real home's.
_HOSTS = {
    "hosts": [
        {
            "alias": "gpu",
            "host": "gpu.example",
            "user": "ann",
            "port": 2200,
            "identity_files": ["~/.ssh/gpu"],
            "proxy_jump": "",
            "saved": False,
        }
    ]
}


def test_a_custom_daemon_is_filled_from_the_ssh_config(
    project: Path, engine: str
) -> None:
    wire = Wire(faked={"runtimes.hosts": lambda _: {"result": _HOSTS}})
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, "/settings/daemons")
        form = page.locator("[data-hmz=write-daemon]")
        form.locator("[data-hmz=daemon-kind]").get_by_role("button", name="SSH").click()
        form.get_by_role("button", name="Custom").click()
        form.locator("#daemon-import").select_option("gpu")
        form.locator("[data-hmz=daemon-import]").click()
        expect(form.get_by_label("Name")).to_have_value("gpu")
        expect(form.locator("#daemon-host")).to_have_value("gpu.example")
        expect(form.locator("#daemon-user")).to_have_value("ann")
        expect(form.locator("#daemon-port")).to_have_value("2200")
        expect(form.locator("#daemon-identity")).to_have_value("~/.ssh/gpu")
        form.get_by_label("Name").fill("box")
        form.get_by_role("button", name="Add", exact=True).last.click()
        row = page.locator("[data-hmz=daemon][data-name=box]")
        expect(row.locator("[data-hmz=daemon-via]")).to_have_text("SSH · Custom")
        route = "stdio:ssh://ann@gpu.example:2200?identity=~%2F.ssh%2Fgpu"
        expect(row).to_contain_text(route)
        assert _kept(page) == [{"name": "box", "id": "", "routes": [route]}]

        row.get_by_role("button", name="Edit").click()
        expect(_pressed(form, "daemon-mode")).to_have_text("Custom")
        expect(form.locator("#daemon-host")).to_have_value("gpu.example")
        expect(form.locator("#daemon-identity")).to_have_value("~/.ssh/gpu")


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


class _EasyTier:
    """Local's EasyTier entries, `far` among them, as its wire answers them; each write kept."""

    def __init__(self, nodes: dict[str, Any]) -> None:
        self.networks = [
            {"name": "far", "nodes": ["tcp://mine.example:11010"], "secret": True}
        ]
        self.writes: list[dict[str, Any]] = []
        self.wire = Wire(
            faked={
                "easytier.nodes": lambda _: nodes,
                "easytier.list": lambda _: {"result": {"networks": self.networks}},
                "easytier.set": self._set,
            }
        )

    def _set(self, params: dict[str, Any]) -> dict[str, Any]:
        said = {key: value for key, value in params.items() if key != "idem"}
        self.writes.append(said)
        self.networks = [one for one in self.networks if one["name"] != said["name"]]
        self.networks.append(
            {"name": said["name"], "nodes": said["nodes"], "secret": True}
        )
        return {"result": {"networks": self.networks}}


def test_an_easytier_daemon_takes_a_secret_nodes_and_a_pairing_code(
    project: Path, tmp_path: Path, engine: str
) -> None:
    fake = _EasyTier({"result": _NODES})
    with (
        another(tmp_path) as gpu,
        served() as site,
        opened(site, engine=engine, routed=fake.wire.routes) as page,
    ):
        go(page, "/settings/daemons")
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
        # What is no pairing code is refused before the secret is written.
        add.click()
        expect(form.locator(".error")).to_have_text("That is not a pairing code.")
        assert not fake.writes
        form.locator("#daemon-code").fill(gpu.code())
        add.click()
        row = page.locator("[data-hmz=daemon][data-name=edge]")
        expect(row.locator("[data-hmz=daemon-via]")).to_have_text("P2P · EasyTier")
        assert fake.writes == [
            {
                "name": "edge",
                "secret": "ü" * 8,
                "nodes": [
                    "tcp://public.easytier.example:11010",
                    "wss://relay.example:443",
                ],
            }
        ]
        # Claimed, it is held to the id its code gave: its EasyTier route first, as this
        # machine names it, then the code's other routes.
        [entry] = _kept(page)
        assert len(entry["id"]) == 52
        assert entry["routes"] == ["easytier:edge", f"tcp://127.0.0.1:{gpu.port}"]


def test_without_the_community_list_nodes_are_typed(
    project: Path, tmp_path: Path, engine: str
) -> None:
    unreadable = {"error": {"code": 503, "message": "The node list could not be read."}}
    fake = _EasyTier(unreadable)
    with (
        another(tmp_path) as gpu,
        served() as site,
        opened(site, engine=engine, routed=fake.wire.routes) as page,
    ):
        go(page, "/settings/daemons")
        form = page.locator("[data-hmz=write-daemon]")
        form.get_by_role("button", name="P2P").click()
        expect(form.locator("[data-hmz=daemon-nodes]")).to_contain_text(
            "The node list could not be read."
        )
        form.get_by_label("Name").fill("edge")
        form.locator("#daemon-secret").fill("a secret of enough bytes")
        form.locator("#daemon-code").fill(gpu.code())
        add = form.get_by_role("button", name="Add", exact=True)
        add.click()
        expect(form.locator(".error").last).to_have_text(
            "An EasyTier daemon needs at least one node."
        )
        form.locator("#daemon-node").fill("tcp://mine.example:11010")
        form.get_by_role("button", name="Add node").click()
        add.click()
        expect(page.locator("[data-hmz=daemon][data-name=edge]")).to_be_visible()
        assert fake.writes[-1]["nodes"] == ["tcp://mine.example:11010"]


def test_an_easytier_daemon_edited_keeps_its_secret(project: Path, engine: str) -> None:
    fake = _EasyTier({"result": _NODES})
    with served() as site, opened(site, engine=engine, routed=fake.wire.routes) as page:
        kept(page, {"name": "far", "id": "b" * 52, "routes": ["easytier:far"]})
        go(page, "/settings/daemons")
        far = page.locator("[data-hmz=daemon][data-name=far]")
        expect(far.locator("[data-hmz=daemon-via]")).to_have_text("P2P · EasyTier")
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
        assert fake.writes == [{"name": "far", "nodes": ["tcp://mine.example:11010"]}]
        # Its id stays pinned, its route as it was.
        assert _kept(page) == [
            {"name": "far", "id": "b" * 52, "routes": ["easytier:far"]}
        ]

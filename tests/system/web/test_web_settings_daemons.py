"""Settings, per daemon.

The app's own pages apart from a daemon's, which daemon those read and write, and what a page
holds copied to several daemons at once.

`gpu` is another machine's daemon, real and paired with this browser, reached through `/dial`;
`lab` is kept, but nothing answers where it is reached, as a daemon that is not up.

Then the New daemon form, on each carrier, with what is said beside it, and what stands under
each daemon's line: its devices, and a remote daemon's own WebRTC servers. TCP against `gpu`'s
pairing code; a Host of the ssh config against the real ssh config of the test's home; Custom
and EasyTier with what Local answers of the ssh config, the shared nodes and the EasyTier
entries faked on its wire.
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
    again,
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
        expect(nav.locator(".settings-group")).to_have_text(
            ["App", "Daemon", "Workspace"]
        )
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
        expect(page.locator("[data-hmz=harness-sessions]")).to_be_visible()
        assert "daemon=gpu" in page.url
        expect(page.locator(".settings-nav a", has_text="Backup")).to_have_attribute(
            "href", "#/settings/backup?daemon=gpu"
        )

        page.locator("[data-hmz=settings-general] input[type=checkbox]").first.check()
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
        page.locator("[data-hmz=settings-general] input[type=checkbox]").first.check()
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

        # A press beside it closes it as Escape does, and Settings stays.
        page.locator("[data-hmz=batch-apply]").click()
        expect(dialog).to_be_visible()
        page.mouse.click(4, 4)
        expect(dialog).to_have_count(0)
        expect(page.locator("[data-hmz=settings-general]")).to_be_visible()


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
        # The carriers stand side by side, with nothing under them.
        kinds = form.locator("[data-hmz=daemon-kind]")
        expect(kinds.locator("button")).to_have_text(
            ["SSH", "EasyTier", "TCP", "WebSocket", "Relay", "WebRTC"]
        )
        expect(form.locator("[data-hmz=daemon-mode]")).to_have_count(0)
        expect(_pressed(form, "daemon-kind")).to_have_text("SSH")
        # Beside the form, what the carrier chosen is and what the other machine needs for it.
        about = form.locator("[data-hmz=daemon-about]")
        expect(about.locator("h3")).to_have_text("Reach over SSH")
        kinds.get_by_role("button", name="EasyTier", exact=True).click()
        expect(about.locator("h3")).to_have_text("Reach over EasyTier")
        kinds.get_by_role("button", name="TCP", exact=True).click()
        expect(about.locator("h3")).to_have_text("Reach over TCP")
        expect(about).to_contain_text("hmz daemon pair")
        # With only Local, the page says so, and what its devices are.
        expect(page.locator("[data-hmz=daemons-none]")).to_contain_text("Only Local")
        expect(page.locator("[data-hmz=daemons-about]")).to_contain_text(
            "the browsers and machines paired with it"
        )
        form.get_by_label("Name").fill("gpu")
        form.locator("#daemon-code").fill("hmz-pair:nope")
        add = form.get_by_role("button", name="Add", exact=True)
        add.click()
        expect(form.locator(".error")).to_have_text("That is not a pairing code.")
        assert _kept(page) == []

        form.locator("#daemon-code").fill(gpu.code())
        add.click()
        row = page.locator("[data-hmz=daemon][data-name=gpu]")
        expect(row.locator("[data-hmz=daemon-via]")).to_have_text("TCP")
        expect(row).to_contain_text(f"tcp://127.0.0.1:{gpu.port}")
        [entry] = _kept(page)
        assert entry["routes"] == [f"tcp://127.0.0.1:{gpu.port}"]
        assert len(entry["id"]) == 52

        expect(page.locator("[data-hmz=daemons-none]")).to_have_count(0)
        # Its devices are its own, under its line: none are listed until it is reached.
        own = page.locator("[data-hmz=daemon-own][data-name=gpu]")
        devices = own.locator("[data-hmz=daemon-devices][data-name=gpu]")
        expect(devices.locator("h3")).to_have_text("Devices")
        expect(devices.locator("[data-hmz=devices-none]")).to_contain_text(
            "Not reached"
        )

        # Reached, it lists this machine among its devices, paired as it is called.
        row.get_by_role("button", name="Connect").click()
        expect(row.locator("[data-hmz=daemon-state]")).to_contain_text("up")
        # Reached, it offers no Connect; Local, up from the start, never did.
        expect(row.get_by_role("button", name="Connect")).to_have_count(0)
        local = page.locator("[data-hmz=daemon][data-name=local]")
        expect(local.get_by_role("button", name="Connect")).to_have_count(0)
        expect(devices.locator("[data-hmz=device] b")).to_contain_text(
            [socket.gethostname().split(".")[0]]
        )
        # The page is a client of its daemons: it makes no pairing code.
        expect(page.get_by_role("button", name="Pair a device")).to_have_count(0)
        # No panel of every daemon's devices stands apart from them.
        expect(page.locator("[data-hmz=pairing]")).to_have_count(0)


#: A daemon kept, pinned, with a route over WebRTC, which nothing answers.
_RELAYED = {
    "name": "relayed",
    "id": "a" * 52,
    "routes": ["webrtc:ws://127.0.0.1:9/r", "tcp://127.0.0.1:9"],
}

#: Two servers, as a daemon keeps them: a STUN server, and a TURN server with who uses it.
_SERVERS = [
    {"urls": "stun:stun.example:3478"},
    {"urls": "turn:turn.example:3478", "username": "ann", "credential": "secret"},
]

#: A pairing code whose one route is over WebRTC, as a daemon behind a relay makes one.
_RELAYED_CODE = """async () => {
  const { toBase64url } = await import('/rpc/pipe.js')
  const routes = ['webrtc:ws://127.0.0.1:9/r']
  const said = { v: 1, id: 'a'.repeat(52), routes, token: 't'.repeat(43), expires: 2e9 }
  return 'hmz-pair:' + toBase64url(new TextEncoder().encode(JSON.stringify(said)))
}"""


def test_each_daemon_keeps_its_own_webrtc_servers(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        kept(page, _LAB, _RELAYED)
        go(page, "/settings/daemons")
        # No list for every daemon: each remote daemon has its own, and Local none.
        form = page.locator("[data-hmz=write-daemon]")
        expect(form.locator("form")).to_be_visible()
        expect(page.locator("[data-hmz=ice-servers]")).to_have_count(0)
        expect(page.locator("[data-hmz=daemon-ice]")).to_have_count(2)
        expect(page.locator("[data-hmz=daemon-ice][data-name=local]")).to_have_count(0)
        # Folded away, but under the daemon a route of which is WebRTC's.
        lab = page.locator("[data-hmz=daemon-own][data-name=lab] [data-hmz=daemon-ice]")
        own = page.locator("[data-hmz=daemon-ice][data-name=relayed]")
        assert lab.evaluate("(one) => one.open") is False
        assert own.evaluate("(one) => one.open") is True
        expect(lab.locator("textarea")).to_be_hidden()
        lines = own.locator("textarea")
        expect(lines).to_have_value("")
        expect(own.locator(".hint")).to_contain_text("webrtc: route")

        # What is no STUN or TURN server is refused, and nothing is kept.
        save = own.get_by_role("button", name="Save")
        lines.fill("stun:stun.example:3478\nhttps://nope.example")
        save.click()
        expect(own.locator(".error")).to_contain_text(
            "https://nope.example is not a STUN or TURN server"
        )
        assert _kept(page) == [_LAB, _RELAYED]

        lines.fill("stun:stun.example:3478\nturn:turn.example:3478 ann secret")
        save.click()
        # The credential is masked from then on, and kept where it is left as shown.
        masked = "turn:turn.example:3478 ann ••••"
        expect(lines).to_have_value(f"stun:stun.example:3478\n{masked}")
        assert _kept(page) == [_LAB, {**_RELAYED, "ice": _SERVERS}]
        lines.fill(masked)
        save.click()
        expect(save).to_have_text("Saved")
        assert _kept(page) == [_LAB, {**_RELAYED, "ice": _SERVERS[1:]}]
        # Its URLs edited and the credential left as shown, the credential is kept still.
        both = "turn:turn.example:3478,turns:turn.example:5349"
        lines.fill(f"{both} ann ••••")
        save.click()
        expect(save).to_have_text("Saved")
        wider = {**_SERVERS[1], "urls": both.split(",")}
        assert _kept(page) == [_LAB, {**_RELAYED, "ice": [wider]}]
        # A mask where no credential is kept is asked for again, and nothing is kept without one.
        lines.fill(f"{both} ann ••••\nturn:other.example:3478 bob ••••")
        save.click()
        expect(own.locator(".error")).to_contain_text(
            "Write the credential of turn:other.example:3478 again"
        )
        assert _kept(page) == [_LAB, {**_RELAYED, "ice": [wider]}]
        lines.fill(masked)
        save.click()
        expect(save).to_have_text("Saved")
        assert _kept(page) == [_LAB, {**_RELAYED, "ice": _SERVERS[1:]}]

        # Opened again, they are that daemon's still; its routes edited, they stay.
        again(page)
        expect(own.locator("textarea")).to_have_value(masked)
        page.locator("[data-hmz=daemon][data-name=relayed]").get_by_role(
            "button", name="Edit"
        ).click()
        expect(_pressed(form, "daemon-kind")).to_have_text("WebRTC")
        form.locator("[data-hmz=route-editor] .list-row").nth(1).get_by_role(
            "button", name="Remove"
        ).click()
        form.get_by_role("button", name="Save", exact=True).click()
        expect(form.locator("h2")).to_have_text("New daemon")
        assert _kept(page) == [
            _LAB,
            {**_RELAYED, "routes": _RELAYED["routes"][:1], "ice": _SERVERS[1:]},
        ]

        # A new WebRTC daemon's are asked in the form; TCP asks none.
        kinds = form.locator("[data-hmz=daemon-kind]")
        kinds.get_by_role("button", name="TCP", exact=True).click()
        expect(form.locator("#daemon-ice")).to_have_count(0)
        kinds.get_by_role("button", name="WebRTC", exact=True).click()
        form.locator("#daemon-code").fill(page.evaluate(_RELAYED_CODE))
        expect(form.locator("#daemon-ice")).to_be_visible()
        # Wrong, they are refused before the code is claimed.
        form.get_by_label("Name").fill("far")
        form.locator("#daemon-ice").fill("nope")
        form.get_by_role("button", name="Add", exact=True).click()
        expect(form.locator(".error")).to_contain_text(
            "nope is not a STUN or TURN server"
        )


def test_the_servers_kept_for_every_daemon_become_each_daemons_own(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        # The base as an earlier version of the page left it, made where no page runs.
        root = page.url.split("#")[0].split("?")[0]
        page.goto(f"{root}style.css")
        page.evaluate(
            """({ daemons, ice }) => new Promise((done, failed) => {
              const gone = indexedDB.deleteDatabase('hmz-daemons')
              // Blocked while the page left lets go of the base, it is deleted once it has.
              gone.onerror = () => failed(gone.error)
              gone.onsuccess = () => {
                const asked = indexedDB.open('hmz-daemons', 1)
                asked.onupgradeneeded = () => {
                  asked.result.createObjectStore('daemons', { keyPath: 'name' })
                  asked.result.createObjectStore('keys')
                  for (const one of daemons) asked.transaction.objectStore('daemons').put(one)
                  asked.transaction.objectStore('keys').put(ice, 'ice')
                }
                asked.onsuccess = () => (asked.result.close(), done())
                asked.onerror = () => failed(asked.error)
              }
            })""",
            {"daemons": [_LAB, _RELAYED], "ice": _SERVERS},
        )
        # Opened once, and left to draw: a page opened again while its first view loads has
        # that view's files given up, which WebKit says as an error of the page.
        page.goto(root)
        page.wait_for_selector("[data-hmz=sidebar] .brand")
        page.wait_for_selector("[data-hmz=page]:not([aria-busy])", state="attached")
        go(page, "/settings/daemons")
        own = page.locator("[data-hmz=daemon-ice][data-name=relayed]")
        expect(own.locator("textarea")).to_have_value(
            "stun:stun.example:3478\nturn:turn.example:3478 ann ••••"
        )
        expect(
            page.locator("[data-hmz=daemon-ice][data-name=lab] textarea")
        ).to_have_value("")
        assert _kept(page) == [_LAB, {**_RELAYED, "ice": _SERVERS}]


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
        expect(_pressed(form, "daemon-kind")).to_have_text("SSH")
        form.locator("#daemon-alias").select_option("gpu")
        expect(form.get_by_label("Name")).to_have_value("gpu")
        form.get_by_role("button", name="Add", exact=True).click()
        row = page.locator("[data-hmz=daemon][data-name=gpu]")
        expect(row.locator("[data-hmz=daemon-via]")).to_have_text("SSH")
        assert _kept(page) == [{"name": "gpu", "id": "", "routes": ["stdio:ssh://gpu"]}]

        # Edited, it opens on SSH, its host picked.
        row.get_by_role("button", name="Edit").click()
        expect(_pressed(form, "daemon-kind")).to_have_text("SSH")
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


def test_a_custom_daemon_is_written_a_part_at_a_time(
    project: Path, engine: str
) -> None:
    wire = Wire(faked={"runtimes.hosts": lambda _: {"result": _HOSTS}})
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, "/settings/daemons")
        form = page.locator("[data-hmz=write-daemon]")
        custom = form.locator("[data-hmz=daemon-custom]")
        expect(custom).to_be_hidden()
        form.locator("#daemon-alias").select_option(label="Custom")
        expect(custom).to_be_visible()
        form.get_by_label("Name").fill("box")
        form.locator("#daemon-host").fill("gpu.example")
        form.locator("#daemon-user").fill("ann")
        form.locator("#daemon-port").fill("2200")
        form.locator("#daemon-identity").fill("~/.ssh/gpu")
        form.get_by_role("button", name="Add", exact=True).last.click()
        row = page.locator("[data-hmz=daemon][data-name=box]")
        expect(row.locator("[data-hmz=daemon-via]")).to_have_text("SSH")
        route = "stdio:ssh://ann@gpu.example:2200?identity=~%2F.ssh%2Fgpu"
        expect(row).to_contain_text(route)
        assert _kept(page) == [{"name": "box", "id": "", "routes": [route]}]

        row.get_by_role("button", name="Edit").click()
        expect(custom).to_be_visible()
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
            "uptime": 0.999,
        },
        {
            "url": "udp://gone.example:11010",
            "name": "Gone",
            "version": "2.4.5",
            "up": False,
            "uptime": 0.125,
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
        kinds.get_by_role("button", name="EasyTier").click()
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
        expect(row.locator("[data-hmz=daemon-via]")).to_have_text("EasyTier")
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
        form.get_by_role("button", name="EasyTier").click()
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
        expect(far.locator("[data-hmz=daemon-via]")).to_have_text("EasyTier")
        far.get_by_role("button", name="Edit").click()
        form = page.locator("[data-hmz=write-daemon]")
        expect(form.locator("h2")).to_have_text("Edit far")
        expect(_pressed(form, "daemon-kind")).to_have_text("EasyTier")
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

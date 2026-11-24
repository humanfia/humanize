"""The pictures of `docs/user/relay.md`: a relay, and a daemon reached through it over WebRTC.

`hmz relay serve` as it says where it listens; a second machine, `devbox`, whose daemon is
real and registers at a real relay; and the page, which claims `devbox`'s pairing code over
WebRTC -- a real data channel between Chromium and the daemon -- and keeps STUN and TURN
servers for it.

The relay is at `wss://relay.example.com` in every picture. No such machine exists: the
relay runs on a port of loopback, and the two ends that dial it -- `devbox`'s Python and the
page's `WebSocket` -- are each handed that port where they ask for that URL, which is what a
name and a TLS proxy in front of the relay do for a real one.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_relay.py`.
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import TYPE_CHECKING, Any

import psutil
from playwright.sync_api import expect

from tests.conftest import own
from tests.integration.doubles_tui import onto, shows, typed
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import Wire, again, go

if TYPE_CHECKING:
    from collections.abc import Generator

    import pytest
    from playwright.sync_api import Page

    from tests.system.docs.conftest import World

_PAGE = "user-relay"

#: The second machine, and the relay as both ends name it.
_DEVBOX = "devbox"
_RELAY = "wss://relay.example.com"

#: The servers the page keeps for `devbox`, a line each as they are typed.
_SERVERS = "stun:stun.example.com:3478\nturn:turn.example.com:3478 alex not-a-real-key"

#: Shared EasyTier nodes as the community's status page lists them, made up, and after them
#: the two public nodes hmz offers whatever that page says (`hmz.coganchor.easytier.KNOWN`).
_NODES = [
    {
        "url": "tcp://fra.example.net:11010",
        "name": "Frankfurt",
        "version": "2.6.4",
        "up": True,
        "uptime": 0.999,
    },
    {
        "url": "tcp://sgp.example.net:11010",
        "name": "Singapore",
        "version": "2.6.4",
        "up": True,
        "uptime": 0.982,
    },
    {
        "url": "tcp://sea.example.net:11010",
        "name": "Seattle",
        "version": "2.6.2",
        "up": False,
        "uptime": 0.614,
    },
    {
        "url": "tcp://public.easytier.top:11010",
        "name": "EasyTier public node",
        "version": "",
        "up": None,
        "uptime": None,
    },
    {
        "url": "tcp://easytier.public.kkrainbow.top:11010",
        "name": "kkRainbow public node",
        "version": "",
        "up": None,
        "uptime": None,
    },
]


def _interrupted(
    told: str, port: int | None = None, after: float = 1.0
) -> threading.Thread:
    """Interrupts the `hmz` started from here whose command line holds `told`, once it serves.

    `hmz relay serve` and `hmz daemon serve` serve until they are stopped, and a picture is
    of a command that ended: each is stopped as ctrl+c stops it, a moment after it listens
    on `port`, or after it started where it listens on none.
    """

    def waits() -> None:
        until = time.monotonic() + 90
        while time.monotonic() < until:
            for one in psutil.Process().children(recursive=True):
                with contextlib.suppress(psutil.Error, OSError):
                    if told in one.cmdline() and (
                        port is None
                        or any(
                            at.laddr.port == port for at in one.net_connections("tcp")
                        )
                    ):
                        time.sleep(after)
                        one.send_signal(signal.SIGINT)
                        return
            time.sleep(0.2)

    thread = threading.Thread(target=waits, daemon=True)
    thread.start()
    return thread


def test_a_relay_says_where_it_listens(world: World) -> None:
    stopping = _interrupted("relay", 8765)
    shots.cli(["hmz", "relay", "serve"], f"{_PAGE}-serve", columns=64)
    stopping.join(10)


# --------------------------------------------------------------------------------------
# A relay, and a second machine registered at it.
# --------------------------------------------------------------------------------------


@contextlib.contextmanager
def _relay() -> Generator[int]:
    """`hmz relay serve` on a free port of loopback, until the block ends: the port."""
    serving = subprocess.Popen(
        [sys.executable, "-m", "hmz", "relay", "serve", "--listen", "127.0.0.1:0"],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert serving.stdout is not None
        said = serving.stdout.readline()
        assert "listening on ws://" in said, said
        yield int(said.strip().rsplit(":", 1)[1])
    finally:
        serving.terminate()
        serving.wait(10)


@dataclasses.dataclass(frozen=True)
class _Devbox:
    """`hmz daemon serve` on a machine called `devbox`, under a home of its own."""

    env: dict[str, str]

    def code(self) -> str:
        """A pairing code it makes, carrying the routes of its listeners."""
        return subprocess.run(
            [sys.executable, "-m", "hmz", "daemon", "pair"],
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()[0]


def _devbox_env(world: World, port: int) -> dict[str, str]:
    """The environment of `devbox`: a name and a home of its own, and the relay at its URL."""
    base = world.home.parent
    site = base / "devbox-site"
    site.mkdir()
    (site / "sitecustomize.py").write_text(
        "import socket\n"
        f"socket.gethostname = lambda: {_DEVBOX!r}\n"
        "import websockets.sync.client as _client\n"
        "_connect = _client.connect\n"
        "def _named(uri, *more, **how):\n"
        f"    there = uri.replace({_RELAY!r}, 'ws://127.0.0.1:{port}')\n"
        "    return _connect(there, *more, **how)\n"
        "_client.connect = _named\n"
    )
    home = base / _DEVBOX / "alex"
    home.mkdir(parents=True)
    return dict(
        os.environ,
        HOME=str(home),
        **own(home),
        PYTHONPATH=str(site),
        # Short, as a socket's path under it must be.
        TMPDIR=tempfile.mkdtemp(prefix="d", dir=str(base)),
    )


@contextlib.contextmanager
def _devbox(world: World, port: int, kind: str = "webrtc") -> Generator[_Devbox]:
    """Another machine's daemon, registered at the relay, until the block ends.

    It takes joins of one kind there, `webrtc` or `relay`, so that the code it makes carries
    that one route and nothing here dials a name that is not this machine's.
    """
    there = _devbox_env(world, port)
    serving = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "hmz",
            "daemon",
            "serve",
            "--listen",
            f"{kind}:{_RELAY}",
        ],
        env=there,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert serving.stdout is not None
        said = serving.stdout.readline()
        assert f"listening on {kind}:{_RELAY}" in said, said
        yield _Devbox(there)
    finally:
        serving.terminate()
        serving.wait(10)


def _reaches(page: Page, port: int) -> None:
    """Has the page's WebSockets to the relay's URL open on the relay's port, from here on."""
    page.add_init_script(
        "{ const Real = window.WebSocket;"
        " window.WebSocket = new Proxy(Real, { construct: (target, [url, ...more]) =>"
        f" new target(String(url).replace({_RELAY!r}, 'ws://127.0.0.1:{port}'), ...more)"
        " }) }"
    )
    again(page)


def test_a_daemon_registers_at_a_relay(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _relay() as port:
        for name, value in _devbox_env(world, port).items():
            monkeypatch.setenv(name, value)
        stopping = _interrupted(f"relay:{_RELAY}", after=6)
        shots.cli(
            [
                "hmz",
                "daemon",
                "serve",
                "--listen",
                f"relay:{_RELAY}",
                "--listen",
                f"webrtc:{_RELAY}",
            ],
            f"{_PAGE}-register",
            columns=100,
        )
        stopping.join(10)


def test_a_daemon_is_added_over_webrtc(world: World) -> None:
    with (
        _relay() as port,
        _devbox(world, port) as devbox,
        world.page(desktop=True) as page,
    ):
        _reaches(page, port)
        go(page, "/settings/daemons")
        form = page.locator("[data-hmz=write-daemon]")
        form.locator("[data-hmz=daemon-kind]").get_by_role(
            "button", name="WebRTC", exact=True
        ).click()
        expect(form.locator("[data-hmz=daemon-about] h3")).to_have_text(
            "Reach over WebRTC"
        )
        form.get_by_label("Name").fill(_DEVBOX)
        form.locator("#daemon-code").fill(devbox.code())
        form.locator("#daemon-address").fill(f"webrtc:{_RELAY}")
        form.locator("#daemon-ice").fill(_SERVERS.splitlines()[0])
        add = form.get_by_role("button", name="Add", exact=True)
        add.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        shots.web(page, f"{_PAGE}-add", clip=form, pad=8)

        add.click()
        row = page.locator(f"[data-hmz=daemon][data-name={_DEVBOX}]")
        expect(row).to_contain_text(f"webrtc:{_RELAY}")
        connect = row.get_by_role("button", name="Connect")
        if connect.is_visible():
            connect.click()
        expect(row.locator("[data-hmz=daemon-state]")).to_contain_text("up")
        devices = page.locator(f"[data-hmz=daemon-devices][data-name={_DEVBOX}]")
        expect(devices.locator("[data-hmz=device]")).to_have_count(1)

        # Under its line, its own servers: a TURN server added, its credential kept masked.
        own = page.locator(f"[data-hmz=daemon-ice][data-name={_DEVBOX}]")
        expect(own.get_by_text("STUN and TURN")).to_be_visible()
        lines = own.locator("[data-hmz=ice-lines]")
        lines.fill(_SERVERS)
        own.get_by_role("button", name="Save").click()
        expect(lines).to_have_value(_SERVERS.replace("not-a-real-key", "••••"))
        expect(row.locator("[data-hmz=daemon-state]")).to_contain_text("up")
        row.scroll_into_view_if_needed()
        page.wait_for_timeout(1500)
        shots.web(page, f"{_PAGE}-daemons", clip=page.locator("[data-hmz=daemons]"))


async def test_the_terminal_reaches_it_through_the_relay(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from websockets.sync import client

    from hmz.runtime.doing.daemons import Remotes

    with _relay() as port, _devbox(world, port, "relay") as devbox:
        real = client.connect

        def named(uri: str, *more: Any, **how: Any) -> Any:
            return real(uri.replace(_RELAY, f"ws://127.0.0.1:{port}"), *more, **how)

        monkeypatch.setattr(client, "connect", named)
        reaching = Remotes()
        try:
            reaching.pair(_DEVBOX, devbox.code())
        finally:
            reaching.close()
        async with world.tui((88, 16)) as (app, pilot):
            await shows(pilot, MODEL)
            await typed(pilot, "/settings daemons")
            await shows(pilot, _DEVBOX, f"relay:{_RELAY}")
            # Its menu's first line connects it.
            await onto(pilot, _DEVBOX)
            await pilot.press("enter")
            await shows(pilot, "connect")
            await pilot.press("enter")
            await shows(pilot, f"relay:{_RELAY} · up")
            await pilot.pause(0.5)
            shots.tui(app, f"{_PAGE}-terminal")


def test_shared_easytier_nodes_are_ticked(world: World) -> None:
    # The community's status page is another's, on the internet: what it lists is said here.
    wire = Wire(faked={"easytier.nodes": lambda _: {"result": {"nodes": _NODES}}})
    with world.page(wire=wire) as page:
        go(page, "/settings/daemons")
        form = page.locator("[data-hmz=write-daemon]")
        form.locator("[data-hmz=daemon-kind]").get_by_role(
            "button", name="EasyTier", exact=True
        ).click()
        nodes = form.locator("[data-hmz=daemon-nodes]")
        expect(nodes.locator("[data-hmz=daemon-community] label")).to_have_count(
            len(_NODES)
        )
        nodes.locator("label", has_text="fra.example").get_by_role("checkbox").check()
        typed_node = form.locator("#daemon-node")
        typed_node.fill("tcp://node.example.com:11010")
        nodes.get_by_role("button", name="Add node").click()
        expect(nodes.locator("[data-hmz=daemon-own-nodes] label")).to_have_count(1)
        typed_node.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        shots.web(page, f"{_PAGE}-nodes", clip=nodes.locator(".."), pad=8)

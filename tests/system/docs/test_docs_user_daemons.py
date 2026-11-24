"""The pictures of `docs/user/daemons.md`: other machines' daemons, reached from this one.

A second machine, `devbox`, whose daemon is real and listens on a port of loopback: added to
the app by its pairing code, listed in Settings with the devices paired with it, turned to
from the foot of the sidebar and written this machine's settings by Batch apply; the form
that adds a machine over SSH; the same in the terminal interface's
`/settings daemons`; and `hmz devices pair` and `hmz devices list` on the command line.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_daemons.py`.
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import re
import socket
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.conftest import own
from tests.integration.doubles_tui import on, onto, picks, shows, typed
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Locator, Page

    from tests.system.docs.conftest import World

_PAGE = "user-daemons"

#: The second machine, and the port its daemon listens on.
_DEVBOX = "devbox"
_LISTENS = 41820

#: A third, which is paired with this machine's daemon: a device of it.
_LAPTOP = "laptop"

#: The hosts of the person's ssh config.
_SSH_CONFIG = """
Host gpu-box
    HostName gpu.example
    User alex

Host build-server
    HostName build.example
    User alex
    Port 2222
"""

_CLAIMS = """
import sys
from hmz.runtime.doing.daemons import Remotes
remotes = Remotes()
try:
    remotes.pair("studio", sys.argv[1], device=sys.argv[2])
finally:
    remotes.close()
"""


@dataclasses.dataclass(frozen=True)
class _Devbox:
    """`hmz daemon serve` on a machine called `devbox`, under a home of its own."""

    env: dict[str, str]
    port: int

    def code(self) -> str:
        """A pairing code it makes, carrying the route another machine reaches it by."""
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "hmz",
                "daemon",
                "pair",
                "--route",
                f"tcp://{_DEVBOX}:{self.port}",
            ],
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()[0]


@contextlib.contextmanager
def _devbox(world: World, port: int = _LISTENS) -> Generator[_Devbox]:
    """Another machine's daemon, listening on a TCP port, until the block ends.

    Every Python it starts is told it is `devbox`, as the world's are told they are `studio`.
    """
    base = world.home.parent
    site = base / "devbox-site"
    site.mkdir()
    (site / "sitecustomize.py").write_text(
        f"import socket\nsocket.gethostname = lambda: {_DEVBOX!r}\n"
    )
    home = base / _DEVBOX / "alex"
    home.mkdir(parents=True)
    there = dict(
        os.environ,
        HOME=str(home),
        **own(home),
        PYTHONPATH=str(site),
        # Short, as a socket's path under it must be.
        TMPDIR=tempfile.mkdtemp(prefix="d", dir=str(base)),
    )
    serving = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "hmz",
            "daemon",
            "serve",
            "--listen",
            f"tcp://127.0.0.1:{port}",
        ],
        env=there,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert serving.stdout is not None
        said = serving.stdout.readline()
        assert "listening on tcp://" in said, said
        yield _Devbox(there, int(said.strip().rsplit(":", 1)[1]))
    finally:
        serving.terminate()
        serving.wait(10)


@pytest.fixture
def _named(monkeypatch: pytest.MonkeyPatch) -> None:
    """`devbox` is a machine this one finds by its name: its address is this machine's own."""
    asked = socket.getaddrinfo

    def found(host: Any, *more: Any, **how: Any) -> Any:
        return asked("127.0.0.1" if host == _DEVBOX else host, *more, **how)

    monkeypatch.setattr(socket, "getaddrinfo", found)


def _paired(world: World) -> None:
    """Pairs a machine called `laptop` with the world's daemon, by a code it claims."""
    world.call("settings.set", listen=["tcp://127.0.0.1:0"])
    code = world.call("pair.create")["code"]
    base = world.home.parent
    home = base / _LAPTOP / "alex"
    home.mkdir(parents=True)
    there = dict(
        os.environ,
        HOME=str(home),
        **own(home),
        TMPDIR=tempfile.mkdtemp(prefix="l", dir=str(base)),
    )
    subprocess.run(
        [sys.executable, "-c", _CLAIMS, code, _LAPTOP],
        env=there,
        check=True,
        timeout=120,
    )


def _form(page: Page, kind: str, title: str) -> Locator:
    """The New daemon form of Settings > Daemons, turned to one kind."""
    form = page.locator("[data-hmz=write-daemon]")
    form.locator("[data-hmz=daemon-kind]").get_by_role(
        "button", name=kind, exact=True
    ).click()
    expect(form.locator("[data-hmz=daemon-about] h3")).to_have_text(title)
    return form


def _centred(page: Page, part: Locator) -> None:
    """Scrolls a part of Settings to the middle of what shows, so that all of it does."""
    part.evaluate("el => el.scrollIntoView({ block: 'center' })")
    page.wait_for_timeout(400)


def _added(page: Page, devbox: _Devbox) -> Locator:
    """Adds `devbox` to the page by its pairing code, and answers its line once it is up."""
    form = _form(page, "TCP", "Reach over TCP")
    form.get_by_label("Name").fill(_DEVBOX)
    form.locator("#daemon-code").fill(devbox.code())
    form.get_by_role("button", name="Add", exact=True).click()
    return _up(page, devbox)


def _up(page: Page, devbox: _Devbox) -> Locator:
    """The line of `devbox`, once it is reached and lists its devices."""
    row = page.locator(f"[data-hmz=daemon][data-name={_DEVBOX}]")
    expect(row).to_contain_text(f"tcp://{_DEVBOX}:{devbox.port}")
    connect = row.get_by_role("button", name="Connect")
    if connect.count() and connect.is_visible():
        connect.click()
    expect(row.locator("[data-hmz=daemon-state]")).to_contain_text("up")
    devices = page.locator(f"[data-hmz=daemon-devices][data-name={_DEVBOX}]")
    expect(devices.locator("[data-hmz=device] b")).to_contain_text(["studio"])
    return row


@pytest.mark.usefixtures("_named")
def test_a_machine_is_added_by_its_code_and_turned_to(world: World) -> None:
    with _devbox(world) as devbox, world.page(desktop=True) as page:
        go(page, "/settings/daemons")
        dialog = page.get_by_role("dialog")
        form = page.locator("[data-hmz=write-daemon]")
        tcp = form.locator("[data-hmz=daemon-kind]").get_by_role(
            "button", name="TCP", exact=True
        )
        expect(tcp).to_be_visible()
        page.wait_for_timeout(400)
        reel = shots.Reel(f"{_PAGE}-add", clip=dialog, pad=0)
        reel.web(page, hold=1.8, pointer=tcp, click=True)
        tcp.click()
        expect(form.locator("[data-hmz=daemon-about] h3")).to_have_text(
            "Reach over TCP"
        )
        form.get_by_label("Name").fill(_DEVBOX)
        form.locator("#daemon-code").fill(devbox.code())
        add = form.get_by_role("button", name="Add", exact=True)
        add.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        reel.web(page, hold=2.4, pointer=add, click=True)
        add.click()
        row = _up(page, devbox)
        row.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        reel.web(page, hold=4, pointer=row, poster=True)
        reel.save()

        # The list alone: each machine's line, and under it the devices paired with it,
        # clear of the heading that stays at the top of the page.
        _centred(page, page.locator("[data-hmz=daemons]"))
        shots.web(page, f"{_PAGE}-list", clip="[data-hmz=daemons]", pad=8)

        # Back on the page, the foot of the sidebar turns it to the other machine.
        go(page, "/new/chat")
        expect(page.get_by_role("textbox", name="First message")).to_be_visible()
        bar = page.locator("[data-hmz=daemon-bar]")
        expect(bar).to_be_visible()
        page.wait_for_timeout(400)
        reel = shots.Reel(f"{_PAGE}-switch", window="desktop")
        reel.web(page, hold=1.6, pointer=bar, click=True)
        bar.click()
        picker = page.locator("[data-hmz=daemon-picker]")
        expect(picker).to_be_visible()
        pick = page.get_by_role("menuitemradio", name=re.compile(_DEVBOX)).first
        if not pick.count():
            pick = page.locator(".popover").get_by_text(_DEVBOX, exact=True).first
        if not pick.is_visible():
            daemon = picker.get_by_text("Daemon", exact=True).first
            page.wait_for_timeout(300)
            reel.web(page, hold=1.4, pointer=daemon, click=True)
            daemon.click()
            expect(pick).to_be_visible()
        page.wait_for_timeout(300)
        reel.web(page, hold=2.2, pointer=pick, click=True)
        pick.click()
        expect(page.locator("[data-hmz=daemon-name]")).to_have_text(_DEVBOX)
        page.wait_for_timeout(1500)
        expect(page.get_by_text(re.compile("^Asking"))).to_have_count(0)
        reel.web(page, hold=4, poster=True)
        reel.save()


@pytest.mark.usefixtures("_named")
def test_settings_are_batch_applied_to_another_machine(world: World) -> None:
    with _devbox(world, _LISTENS + 1) as devbox, world.page(desktop=True) as page:
        go(page, "/settings/daemons")
        _added(page, devbox)
        go(page, "/settings/general")
        batch = page.locator("[data-hmz=batch-apply]").first
        expect(batch).to_be_visible()
        batch.click()
        dialog = page.locator("[data-hmz=batch-dialog]")
        expect(dialog).to_be_visible()
        dialog.locator(f"input[data-daemon={_DEVBOX}]").check()
        dialog.locator("[data-hmz=batch-go]").click()
        expect(dialog.locator("[data-hmz=batch-result]")).to_contain_text("Applied")
        page.wait_for_timeout(300)
        shots.web(page, f"{_PAGE}-batch", clip=dialog, pad=24)


def test_a_machine_is_added_over_ssh(world: World) -> None:
    ssh = world.home / ".ssh"
    ssh.mkdir(mode=0o700)
    (ssh / "config").write_text(_SSH_CONFIG)
    with world.page(desktop=True) as page:
        go(page, "/settings/daemons")
        form = _form(page, "SSH", "Reach over SSH")
        host = form.locator("#daemon-alias")
        expect(host.locator("option", has_text="gpu-box")).to_be_attached()
        host.select_option("gpu-box")
        expect(form.get_by_label("Name")).to_have_value("gpu-box")
        _centred(page, form)
        shots.web(page, f"{_PAGE}-ssh", clip=form, pad=8)


@pytest.mark.usefixtures("_named")
async def test_a_machine_is_added_in_the_terminal(world: World) -> None:
    from hmz.tui.pick import Acts, Daemoning
    from hmz.tui.settings import Adjusts

    with _devbox(world, _LISTENS + 2) as devbox:
        code = devbox.code()
        async with world.tui((100, 26)) as (app, pilot):
            await shows(pilot, MODEL)
            reel = shots.Reel(f"{_PAGE}-terminal")
            await typed(pilot, "/settings daemons")
            await on(pilot, Adjusts)
            await shows(pilot, "Local", "Only Local so far")
            await pilot.pause(0.4)
            reel.tui(app, hold=2.2, keys="/settings daemons")

            await pilot.click("#act-add")
            await on(pilot, Daemoning)
            await pilot.press(*_DEVBOX, "enter")
            await shows(pilot, "Pairing code")
            await pilot.pause(0.4)
            reel.tui(app, hold=2.6, caption="New daemon")
            await picks(pilot, "mode", "pair")
            await onto(pilot, "code")
            await pilot.press(*code, "enter")
            await pilot.click("#act-done")
            await on(pilot, Adjusts)
            await shows(pilot, f"{_DEVBOX} saved", "idle")
            await pilot.pause(0.4)
            reel.tui(app, hold=2.2)

            # Its menu: reaching it now.
            await onto(pilot, _DEVBOX)
            await pilot.press("enter")
            await on(pilot, Acts)
            await shows(pilot, "Connect", "Copy name")
            await pilot.pause(0.4)
            reel.tui(app, hold=2.6, keys="enter")
            await onto(pilot, "connect")
            await pilot.press("enter")
            await on(pilot, Adjusts)
            await shows(pilot, "up, hmz")
            await pilot.pause(0.4)
            reel.tui(app, hold=4, keys="enter", poster=True)
            reel.save()


def test_a_code_is_made_and_devices_are_listed(world: World) -> None:
    _paired(world)
    reel = shots.Reel(f"{_PAGE}-pair")
    reel.cli(["hmz", "devices", "pair"], columns=100, rows=9, hold=3.5)
    reel.cli(["hmz", "devices", "list"], columns=100, rows=9, hold=3.5)
    reel.save()

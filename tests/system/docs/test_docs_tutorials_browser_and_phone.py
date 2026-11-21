"""The pictures of `docs/tutorials/browser-and-phone.md`: the page in a browser and on a phone.

`hmz web` as it says where it serves; a chat started in the browser; the page at a phone's
width, its sidebar a drawer; the Notifications settings; and a second machine, `devbox`, whose
daemon is real, listens on a port of loopback and is added to the page by its pairing code.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_tutorials_browser_and_phone.py`.
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import TYPE_CHECKING, Any

import psutil
import pytest
from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.web.doubles_browser import again, go

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Locator, Page

    from tests.system.docs.conftest import World

_PAGE = "tutorials-browser-and-phone"

#: The port the tutorial serves the page on, and what a browser's window says it is at.
_PORT = 8420
_AT = f"127.0.0.1:{_PORT}"

#: A phone's screen, in CSS pixels. Both are whole numbers of points (three to four pixels):
#: a page 390 pixels wide is printed on paper 292.5 points wide, which is rounded, and what
#: is set against its right edge is then drawn a part of a pixel off its screenshot.
_PHONE = (392, 760)

#: The second machine, and the port its daemon listens on.
_DEVBOX = "devbox"
_LISTENS = 41817

_TASK = "Add a discount code to checkout"
_NEXT = "Should an expired code be refused?"

_ANSWER = (
    "Checkout takes a discount code now: charge() looks the code up and takes its"
    " discount off the total. WELCOME10 is 10% off. Two new tests cover it, and all"
    " six pass."
)
_REFUSED = "Yes. charge() now raises ExpiredCode for a code past its date."


def _ready(page: Page) -> Locator:
    """The box of a new chat, once the agent it would start is on offer under it."""
    expect(page.get_by_role("button", name=re.compile("Nous: .*Haiku"))).to_be_visible()
    return page.get_by_role("textbox", name="First message")


def _in_view(part: Locator) -> bool:
    """Whether any of a part of the page is on the screen: a drawer put away is off its edge."""
    box = part.bounding_box()
    return box is not None and box["x"] >= 0


def _interrupted(told: str, after: float = 1.5) -> threading.Thread:
    """Interrupts the `hmz` started from here whose command line holds `told`, once it serves.

    `hmz web` serves until it is stopped, and a picture is of a command that ended: it is
    stopped as ctrl+c stops it, a moment after it has said where it listens.
    """

    def waits() -> None:
        until = time.monotonic() + 90
        while time.monotonic() < until:
            for one in psutil.Process().children(recursive=True):
                with contextlib.suppress(psutil.Error, OSError):
                    if told in one.cmdline() and any(
                        at.laddr.port == _PORT for at in one.net_connections("tcp")
                    ):
                        time.sleep(after)
                        one.send_signal(signal.SIGINT)
                        return
            time.sleep(0.2)

    thread = threading.Thread(target=waits, daemon=True)
    thread.start()
    return thread


def test_hmz_web_says_where_it_serves(world: World) -> None:
    stopping = _interrupted("--no-open")
    shots.cli(
        ["hmz", "web", "--port", str(_PORT), "--no-open"], f"{_PAGE}-serve", columns=72
    )
    stopping.join(10)


def test_a_chat_is_started_in_the_browser(world: World) -> None:
    world.says({"discount": {"text": _ANSWER, "after": 1.5}})
    with world.page() as page:
        go(page, "/new/chat")
        box = _ready(page)
        reel = shots.Reel(f"{_PAGE}-chat", window="browser", address=_AT)
        reel.web(page, hold=1.6, pointer=box, click=True)
        reel.type(page, box, _TASK, per=11)
        box.press("Enter")
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        expect(page.get_by_role("log")).to_contain_text(_TASK)
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        # The sidebar lists the chat a moment after it is started.
        sidebar = page.locator("[data-hmz=sidebar]")
        expect(sidebar).to_contain_text(_TASK)
        reel.web(page, hold=1.4)
        expect(page.get_by_role("log")).to_contain_text("WELCOME10")
        expect(page.get_by_role("button", name="Send")).to_be_visible()
        # And hears that the turn is over a moment after the chat does.
        expect(sidebar).not_to_contain_text("Running")
        reel.web(page, hold=4, poster=True)
        reel.save()


def test_on_a_phone_the_sidebar_is_a_drawer(world: World) -> None:
    world.says({"discount": _ANSWER, "expired": _REFUSED})
    chat = world.chat(_TASK, _NEXT)
    with world.page(width=_PHONE[0], height=_PHONE[1]) as page:
        go(page, "/new/chat")
        _ready(page)
        sidebar = page.locator("[data-hmz=sidebar]")
        expect(sidebar).not_to_be_in_viewport()
        show = page.get_by_role("button", name="Show sidebar")
        reel = shots.Reel(f"{_PAGE}-drawer")
        reel.web(page, hold=1.6, pointer=show, click=True)
        show.click()
        expect(sidebar).to_be_in_viewport()
        row = sidebar.locator(f"a[href$='/chats/{chat}']").first
        expect(row).to_be_visible()
        page.wait_for_timeout(400)
        reel.web(page, hold=1.8, pointer=row, click=True)
        row.click()
        expect(sidebar).not_to_be_in_viewport()
        expect(page.get_by_role("log")).to_contain_text("ExpiredCode")
        page.wait_for_timeout(600)
        page.wait_for_timeout(400)
        reel.web(page, hold=4, poster=True)
        reel.save()
        shots.web(page, f"{_PAGE}-phone")


def test_a_chat_in_the_drawer_has_a_menu(world: World) -> None:
    world.says({"discount": _ANSWER})
    chat = world.chat(_TASK)
    with world.page(width=_PHONE[0], height=_PHONE[1]) as page:
        go(page, "/new/chat")
        _ready(page)
        page.get_by_role("button", name="Show sidebar").click()
        sidebar = page.locator("[data-hmz=sidebar]")
        expect(sidebar).to_be_in_viewport()
        row = sidebar.locator(f"a[href$='/chats/{chat}']").first
        expect(row).to_be_visible()
        # Under a finger the button is always drawn; under a pointer, once its row is pointed at.
        row.hover()
        more = sidebar.get_by_role("button", name="More options").first
        more.click()
        expect(page.get_by_role("menu")).to_be_visible()
        page.wait_for_timeout(400)
        shots.web(page, f"{_PAGE}-menu")


def test_notifications_are_allowed_in_settings(world: World) -> None:
    with world.page() as page:
        # A browser that was never asked: a headless one says it was, and said no.
        page.add_init_script(
            "Object.defineProperty(Notification, 'permission', { get: () => 'default' })"
        )
        again(page)
        go(page, "/settings/notifications")
        allow = page.get_by_role("button", name="Allow")
        expect(allow).to_be_visible()
        # The dialog alone: any of the page kept around it is slivers of what stands behind.
        shots.web(
            page, f"{_PAGE}-notifications", clip=page.get_by_role("dialog"), pad=0
        )


def test_a_chat_answered_elsewhere_is_marked_unread(world: World) -> None:
    world.says({"discount": {"text": _ANSWER, "after": 2.5}})
    with world.page(width=_PHONE[0], height=_PHONE[1]) as page:
        go(page, "/new/chat")
        box = _ready(page)
        box.fill(_TASK)
        box.press("Enter")
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        # Left while its turn is open: what it answers is heard on another view.
        go(page, "/new/chat")
        expect(page.locator("[data-hmz=unread]").first).to_be_attached()
        page.get_by_role("button", name="Show sidebar").click()
        sidebar = page.locator("[data-hmz=sidebar]")
        expect(sidebar).to_be_in_viewport()
        expect(sidebar.locator("[data-hmz=unread]").first).to_be_visible()
        expect(sidebar).not_to_contain_text("Running")
        page.wait_for_timeout(400)
        shots.web(page, f"{_PAGE}-unread")


# --------------------------------------------------------------------------------------
# A second machine.
# --------------------------------------------------------------------------------------


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
def _devbox(world: World) -> Generator[_Devbox]:
    """Another machine's daemon, listening on a TCP port, until the block ends.

    As `tests.system.web.doubles_browser.another`, but a machine with a name of its own: every
    Python it starts is told it is `devbox`, as the world's are told they are `studio`.
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
        HUMANIZE_HOME=str(home / ".hmz"),
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
            f"tcp://127.0.0.1:{_LISTENS}",
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


def test_a_pairing_code_is_made(world: World) -> None:
    # A daemon makes a code over its listeners: this machine's is given one, as the
    # tutorial gives the other machine's.
    world.call("settings.set", listen=["tcp://127.0.0.1:0"])
    shots.cli(["hmz", "daemon", "pair"], f"{_PAGE}-pair", columns=72)


@pytest.mark.usefixtures("_named")
def test_another_machine_is_added_by_its_code(world: World) -> None:
    with (
        _devbox(world) as devbox,
        world.page(width=_PHONE[0], height=_PHONE[1]) as page,
    ):
        go(page, "/settings/daemons")
        form = page.locator("[data-hmz=write-daemon]")
        form.locator("[data-hmz=daemon-kind]").get_by_role(
            "button", name="TCP", exact=True
        ).click()
        expect(form.locator("[data-hmz=daemon-about] h3")).to_have_text(
            "Reach over TCP"
        )
        form.get_by_label("Name").fill(_DEVBOX)
        form.locator("#daemon-code").fill(devbox.code())
        add = form.get_by_role("button", name="Add", exact=True)
        add.scroll_into_view_if_needed()
        shots.web(page, f"{_PAGE}-add", clip=form, pad=8)

        add.click()
        row = page.locator(f"[data-hmz=daemon][data-name={_DEVBOX}]")
        expect(row).to_contain_text(f"tcp://{_DEVBOX}:{devbox.port}")
        connect = row.get_by_role("button", name="Connect")
        if connect.count():
            connect.click()
        expect(row.locator("[data-hmz=daemon-state]")).to_contain_text("up")
        devices = page.locator(f"[data-hmz=daemon-devices][data-name={_DEVBOX}]")
        expect(devices.locator("[data-hmz=device] b")).to_contain_text(["studio"])
        # Its line alone: under it stand its devices, where this machine is now listed.
        row.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        shots.web(page, f"{_PAGE}-daemons", clip=row, pad=6)

        # Back on the page, the foot of the sidebar switches between the two.
        go(page, "/new/chat")
        page.get_by_role("button", name="Show sidebar").click()
        sidebar = page.locator("[data-hmz=sidebar]")
        expect(sidebar).to_be_in_viewport()
        bar = page.locator("[data-hmz=daemon-bar]")
        page.wait_for_timeout(400)
        reel = shots.Reel(f"{_PAGE}-switch")
        reel.web(page, hold=1.6, pointer=bar, click=True)
        bar.click()
        picker = page.locator("[data-hmz=daemon-picker]")
        expect(picker).to_be_visible()
        pick = picker.get_by_text(_DEVBOX, exact=True).first
        if not pick.is_visible():
            daemon = picker.get_by_text("Daemon", exact=True).first
            reel.web(page, hold=1.2, pointer=daemon, click=True)
            daemon.click()
            expect(pick).to_be_visible()
        reel.web(page, hold=1.8, pointer=pick, click=True)
        pick.click()
        expect(page.locator("[data-hmz=daemon-name]")).to_have_text(_DEVBOX)
        # What it offers a new chat is asked of it first.
        page.wait_for_timeout(1000)
        expect(page.get_by_text(re.compile("^Asking"))).to_have_count(0)
        if not _in_view(sidebar):
            page.get_by_role("button", name="Show sidebar").click()
        expect(sidebar).to_be_in_viewport()
        page.wait_for_timeout(500)
        reel.web(page, hold=4, poster=True)
        reel.save()

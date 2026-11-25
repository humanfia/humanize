"""The web interface's page, drawn by a real browser opened on its address.

Headless Chromium, or WebKit as the desktop app's window draws it, as Playwright drives them;
anything the page throws or logs as an error fails the test. Fetch both with
`uv run playwright install chromium webkit` first.

The page speaks JSON-RPC to each daemon, Local's over `/rpc`: what a test fakes it fakes on that
wire (`Wire`), or keeps in the browser's own storage as the page would (`kept`); a
remote daemon is a real one, under a home of its own (`another`).
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import os
import re
import struct
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hmz.runtime.epic import JOURNAL
from tests.conftest import places, rehome
from tests.integration.doubles_web import PATIENCE

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator

    import pytest
    from playwright.sync_api import Page, WebSocketRoute

    from hmz.web.site import Site
    from tests.integration.doubles_web import Session

#: The engines a page is drawn by: Chromium's, and WebKit's, which the macOS app's window is.
ENGINES = ("chromium", "webkit")

# Where Playwright keeps its browsers is under the home of whoever installed them, and a test
# gives the stand-in a home of its own: the browsers are pinned to the real one before it does.
os.environ.setdefault(
    "PLAYWRIGHT_BROWSERS_PATH",
    str(
        Path.home() / "Library" / "Caches" / "ms-playwright"
        if sys.platform == "darwin"
        else Path.home() / ".cache" / "ms-playwright"
    ),
)

#: The home a browser runs in: the real one, since WebKit on macOS never loads a page from a
#: home made in a temporary directory.
_HOME = str(Path.home())


@contextlib.contextmanager
def opened(
    site: Site,
    *,
    engine: str = "chromium",
    width: int = 1280,
    height: int = 860,
    dark: bool = False,
    touch: bool = False,
    locale: str = "en-US",
    user_agent: str | None = None,
    init: str | None = None,
    routed: Callable[[Page], object] | None = None,
) -> Generator[Page]:
    """The page, in a browser let in by the address, until the block ends.

    Args:
      site: The interface it is opened on.
      engine: One of `ENGINES`, the browser it is drawn by.
      width: How wide the window is: under 860, a phone's layout.
      height: How tall it is.
      dark: Whether the system the browser runs on asks for dark colours.
      touch: Whether the device is touched, with nothing to point at the page with.
      locale: The language the browser asks for, which the page is written in where none is
        chosen: American English, whatever the machine the test runs on speaks.
      user_agent: What the browser says it is, where not its own: as the macOS app's window.
      init: A script run in the page before any of its own.
      routed: Told the page before it is opened, to answer some of its requests itself.

    Yields:
      The page, drawn and with its sidebar up.

    Raises:
      AssertionError: If the page threw anything, or logged an error, while it was open.
    """
    from playwright.sync_api import expect, sync_playwright

    expect.set_options(timeout=PATIENCE * 1000)

    with sync_playwright() as driving:
        kind = driving.webkit if engine == "webkit" else driving.chromium
        browser = kind.launch(env={**os.environ, "HOME": _HOME})
        try:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                color_scheme="dark" if dark else "light",
                locale=locale,
                user_agent=user_agent,
                has_touch=touch,
                is_mobile=touch,
            )
            context.set_default_timeout(PATIENCE * 1000)
            if init:
                context.add_init_script(init)
            page = context.new_page()
            if routed:
                routed(page)
            failed: list[str] = []
            # Bar the browser's word that a resize took more than one frame to settle: a
            # notice, not a failure, which WebKit raises as an error on a busy machine.
            page.on(
                "pageerror",
                lambda error: (
                    failed.append(str(error))
                    if not str(error).startswith("ResizeObserver loop")
                    else None
                ),
            )
            # A refusal is the server answering, which the page says where it happened; what
            # fails the test is the page throwing, or the server failing.
            page.on(
                "console",
                lambda said: (
                    failed.append(said.text)
                    if said.type == "error"
                    and not re.search(r"status of (4\d\d|50[23])", said.text)
                    else None
                ),
            )
            page.goto(site.address)
            page.wait_for_selector("[data-hmz=sidebar] .brand")
            _drawn(page)
            yield page
            assert not failed, f"the page went wrong: {failed}"
        finally:
            browser.close()


def go(page: Page, address: str) -> None:
    """Goes to another view of the page by its address, as a link does, once it is drawn.

    Until then, the view left still stands, and what is done on the page would be done to it.
    """
    page.evaluate(
        """(to) => new Promise((done) => {
            const was = location.hash
            addEventListener('hashchange', () => done(), { once: true })
            location.hash = to
            // The address it is on already, which goes nowhere.
            if (location.hash === was) done()
        })""",
        address,
    )
    _drawn(page)


def _drawn(page: Page) -> None:
    page.wait_for_selector("[data-hmz=page]:not([aria-busy])", state="attached")


def stop(page: Page) -> None:
    """Stops the epic in front, as a script would, until it has ended -- or rests the chat.

    A chat is never ended: its turn is stopped by the button of its box, and the chat stays.
    What rests it is its host going (`hosts.stop`), which this waits for, as a chat left
    alone folds away.
    """
    from playwright.sync_api import expect

    chat = page.evaluate(
        """async () => {
          const api = await import('/api.js')
          const [, kind, said] = location.hash.match(/(chats|epics)\\/([^/?]+)/)
          const name = decodeURIComponent(said)
          if (kind === 'chats') {
            const resting = (one) => !one.slot && one.state !== 'going'
            let chat = await api.call('chat.get', { chat: name })
            const host = { workspace: chat.workspace, slot: chat.slot }
            if (chat.slot) await api.call('hosts.stop', host).catch(() => {})
            while (!resting(chat)) {
              await new Promise((done) => setTimeout(done, 100))
              chat = await api.call('chat.get', { chat: name })
            }
            return true
          }
          const epic = await api.call('runs.get', { name })
          const where = { workspace: epic.workspace, slot: epic.slot, replay: false }
          const held = await api.attach(where, () => {})
          // One already ended, or stopping, has nothing to stop: as it is, it is stopped.
          await api.call('epic.stop', { sub: held.sub }).catch(() => {})
          await held.close()
          return false
        }"""
    )
    if not chat:
        expect(page.locator("[data-hmz=bar] .badge")).to_have_text(
            re.compile("stopped")
        )


def again(page: Page) -> None:
    """Opens the page again where it is, as a reload does, once it is drawn."""
    page.reload()
    page.wait_for_selector("[data-hmz=sidebar] .brand")
    _drawn(page)


def kept(page: Page, *entries: dict[str, Any]) -> None:
    """Keeps remote daemons in the browser, as the Daemons settings do, and opens the page again.

    Args:
      page: The page.
      entries: Each `{name, id, routes}`.
    """
    page.evaluate(
        """async (entries) => {
          const { daemons } = await import('/api.js')
          for (const one of entries) await daemons.add(one)
        }""",
        list(entries),
    )
    again(page)


def _frames(buffer: bytearray, message: str | bytes) -> Iterator[tuple[bytes, Any]]:
    """Each whole frame of the bytes heard so far, and what it says, as `/rpc` carries them."""
    buffer.extend(message.encode() if isinstance(message, str) else message)
    while len(buffer) >= 4:
        (length,) = struct.unpack(">I", buffer[:4])
        if len(buffer) < 4 + length:
            return
        frame = bytes(buffer[: 4 + length])
        del buffer[: 4 + length]
        yield frame, json.loads(frame[4:])


def frame(value: Any) -> bytes:
    """One value as one frame of the wire: its length, then its JSON."""
    payload = json.dumps(value).encode()
    return struct.pack(">I", len(payload)) + payload


#: What answers a method faked on the wire, given its params.
type _Answers = Callable[[Any], dict[str, Any] | None]


@dataclasses.dataclass
class Wire:
    """`/rpc`, carried between the page and Local as it is, a frame at a time.

    What the page calls is kept; a method `faked` names is answered here, never reaching Local,
    with what it gives -- `{"result": ...}` or `{"error": {"code": ..., "message": ...}}` --
    for the params it was called with, or None to be answered later by `answer`; and a
    notice is told the page as Local's, on the notices subscription the page opened.

    Attributes:
      faked: What answers each method faked, by name.
      calls: Every call the page made of Local, in order: each its method and params.
      sub: The notices subscription the page opened on Local, once it has.
    """

    faked: dict[str, _Answers] = dataclasses.field(default_factory=dict[str, _Answers])
    #: Which `/rpc` each call came over, counting from 1 in the order they opened: one per
    #: daemon the page reaches over `/rpc`.
    over: list[int] = dataclasses.field(default_factory=list[int])
    #: How many `/rpc` the page has opened.
    opened: int = 0
    #: The methods whose calls are held back from Local until `lets_through`.
    held: set[str] = dataclasses.field(default_factory=set[str])
    #: The calls held back, as they were sent.
    waiting: list[bytes] = dataclasses.field(default_factory=list[bytes])
    calls: list[tuple[str, Any]] = dataclasses.field(
        default_factory=list[tuple[str, Any]]
    )
    sub: str = ""
    _page: WebSocketRoute | None = None
    _server: WebSocketRoute | None = None
    _later: list[tuple[str, Any]] = dataclasses.field(
        default_factory=list[tuple[str, Any]]
    )

    def routes(self, page: Page) -> None:
        """Carries the page's `/rpc` from here on."""
        page.route_web_socket(re.compile(r".*/rpc$"), self._carries)

    def holds(self, method: str) -> None:
        """Holds back each call of `method` from Local, until `lets_through`."""
        self.held.add(method)

    def waits(self, page: Page) -> None:
        """Waits until a call held back is waiting."""
        while not self.waiting:
            page.wait_for_timeout(50)

    def lets_through(self) -> None:
        """Sends Local every call held back, and holds back no more."""
        assert self._server is not None
        self.held.clear()
        waiting, self.waiting = self.waiting, []
        for whole in waiting:
            self._server.send(whole)

    def answer(self, page: Page, method: str, result: Any) -> None:
        """Answers the first call of `method` faked to be answered later, once one is made."""
        while not any(one == method for one, _ in self._later):
            page.wait_for_timeout(50)
        at = next(i for i, (one, _) in enumerate(self._later) if one == method)
        _, ident = self._later.pop(at)
        assert self._page is not None
        self._page.send(frame({"jsonrpc": "2.0", "id": ident, "result": result}))

    def params(self, method: str) -> list[Any]:
        """What each call of `method` so far was called with."""
        return [params for called, params in self.calls if called == method]

    def tell(self, page: Page, notice: dict[str, Any]) -> None:
        """Tells the page a notice of Local's, once it follows Local's notices."""
        while not self.sub:
            page.wait_for_timeout(50)
        assert self._page is not None
        self._page.send(
            frame(
                {
                    "jsonrpc": "2.0",
                    "method": "notices.event",
                    "params": {"sub": self.sub, "notice": notice},
                }
            )
        )

    def _carries(self, ws: WebSocketRoute) -> None:
        server = ws.connect_to_server()
        self.opened += 1
        which = self.opened
        self._page = ws
        self._server = server
        up, down = bytearray(), bytearray()

        def from_page(message: str | bytes) -> None:
            for whole, said in _frames(up, message):
                method = said.get("method")
                if method:
                    self.calls.append((method, said.get("params")))
                    self.over.append(which)
                if method in self.faked and "id" in said:
                    answer = self.faked[method](said.get("params") or {})
                    if answer is None:
                        self._later.append((method, said["id"]))
                    else:
                        ws.send(frame({"jsonrpc": "2.0", "id": said["id"], **answer}))
                elif method in self.held:
                    self.waiting.append(whole)
                else:
                    server.send(whole)

        def from_server(message: str | bytes) -> None:
            for whole, said in _frames(down, message):
                result = said.get("result")
                if isinstance(result, dict) and {"sub", "last"} <= result.keys():
                    self.sub = result["sub"]
                ws.send(whole)

        ws.on_message(from_page)
        server.on_message(from_server)


@dataclasses.dataclass(frozen=True)
class Another:
    """`hmz daemon serve` under a home of its own, as another machine's daemon: its TCP port."""

    env: dict[str, str]
    port: int

    def code(self) -> str:
        """A pairing code it makes, over its listener."""
        return subprocess.run(
            [sys.executable, "-m", "hmz", "devices", "pair"],
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()[0]


@contextlib.contextmanager
def another(under: Path) -> Generator[Another]:
    """Another machine's daemon, listening on a TCP port of loopback, until the block ends."""
    # A home of its own, which is where it reads Humanize's own settings.
    (under / "another-home").mkdir(exist_ok=True)
    there = dict(
        os.environ,
        HOME=str(under / "another-home"),
        **places(under / "another"),
        # Short, as a socket's path under it must be.
        TMPDIR=tempfile.mkdtemp(prefix="a", dir=os.environ.get("TMPDIR")),
    )
    serving = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "hmz",
            "daemon",
            "serve",
            "--listen",
            "tcp://127.0.0.1:0",
        ],
        env=there,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert serving.stdout is not None
        said = serving.stdout.readline()
        assert "listening on tcp://" in said, said
        yield Another(there, int(said.strip().rsplit(":", 1)[1]))
    finally:
        serving.terminate()
        serving.wait(10)


def paired(page: Page, name: str, code: str) -> None:
    """Pairs the page with a daemon by its code, as the Daemons settings do, and opens it again."""
    page.evaluate(
        "async ([name, code]) => (await import('/api.js')).pair(name, code)",
        [name, code],
    )
    again(page)


def chatted(page: Session, workspace: Path, task: str, *, stopped: bool = True) -> str:
    """Starts a chat in a workspace as a page starts one, until its agent has answered.

    A chat is of no flow: it starts on a host of its own (`chat.start`, Section 4.25 of
    protocol/daemon.md), which is then followed as the page follows it.

    Args:
      page: A session with the daemon.
      workspace: Where the chat starts.
      task: Its first message.
      stopped: Whether its host is stopped once it has answered, and waited for until
        the chat rests.

    Returns:
      The chat's id.
    """
    import time
    import uuid

    from tests.integration.doubles_core import AGENT

    started = page.call(
        "chat.start",
        workspace=str(workspace),
        slot="chat:",
        agent=AGENT,
        task=task,
        idem=uuid.uuid4().hex,
    )
    sub = page.call("epic.attach", workspace=str(workspace), slot=started["slot"])[
        "sub"
    ]

    def record(kind: str) -> Callable[[str, dict[str, Any]], bool]:
        return lambda method, said: (
            method == "epic.event"
            and said["sub"] == sub
            and said["message"].get("type") == kind
        )

    page.until(record("asked"), "the chat's agent answering")
    page.call("epic.detach", sub=sub)
    chat = str(started["chat"])
    if stopped:
        # A chat is never ended: its host goes, and the chat rests.
        page.call(
            "hosts.stop",
            workspace=str(workspace),
            slot=started["slot"],
            idem=uuid.uuid4().hex,
        )
        while page.call("chat.get", chat=chat)["slot"]:
            time.sleep(0.1)
    return chat


def backed_up_elsewhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """An epic run here and backed up to `t`, then this machine made one that has not got it.

    Another machine is a home of its own, sharing the workspace and the repository: what it
    has is a target `t` in its settings and nothing else.

    Returns:
      The epic's name.
    """
    import subprocess

    import tomlkit

    from hmz import config
    from hmz.runtime.epic import every
    from tests.integration.doubles_core import AGENT, hmz_exec

    bare = tmp_path / "epics.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    target = {"name": "t", "url": str(bare), "policies": ["end"]}

    def targets() -> None:
        config().mkdir(parents=True, exist_ok=True)
        said = {"backup": {"targets": [target], "defaults": []}}
        (config() / "settings.toml").write_text(tomlkit.dumps(said))

    targets()
    ran = hmz_exec(
        "-f",
        "goal",
        "-a",
        f"worker={AGENT}",
        "-p",
        "budget.cost=1",
        "--backup",
        "t",
        "hi",
    )
    assert ran.returncode == 0, ran.stderr
    (name,) = [one.name for one in every()]
    rehome(monkeypatch, tmp_path / "elsewhere")
    targets()
    return name


def elsewhere(archive: Path, workspace: str, to: Path) -> Path:
    """A copy of an epic's archive whose run says it ran in another workspace.

    Args:
      archive: The `.hmzepic`.
      workspace: Where the copy says its run ran.
      to: The directory the copy is written into, under the archive's own name.

    Returns:
      The copy.
    """
    copy = to / archive.name
    with (
        tarfile.open(archive, "r:gz") as reading,
        tarfile.open(copy, "w:gz") as writing,
    ):
        for member in reading.getmembers():
            held = reading.extractfile(member)
            body = held.read() if held is not None else b""
            if member.name.endswith(f"/{JOURNAL}"):
                lines = [json.loads(line) for line in body.splitlines()]
                for line in lines:
                    if line.get("event") == "began":
                        line["workspace"] = workspace
                body = b"".join(json.dumps(line).encode() + b"\n" for line in lines)
                member.size = len(body)
            writing.addfile(member, io.BytesIO(body) if member.isfile() else None)
    return copy

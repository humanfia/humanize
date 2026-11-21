"""A conversation opened again is drawn at once, and read again behind what is drawn.

Section 3.6.12 of protocol/web.md. The page keeps what it last saw of each chat, each epic and
each of Ai-chan's conversations, and draws one opened again by it in the frame it opens in: no
note that it is being read is ever put on the page, no frame shows the view without its lines,
and what the daemon then answers is drawn over what was kept in place -- the lines it had stay
the nodes they were, what is new is added under them, the reader stays where they were and
what they were typing stays typed. What the daemon says is gone is gone, whatever was kept.

The chat and its host are faked on the wire, so that the daemon answers only when the test
lets it: what is drawn before that can only be what the page kept. Each in Chromium and in
WebKit.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, Wire, again, frame, go, opened

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from playwright.sync_api import Page

pytestmark = [
    pytest.mark.parametrize("engine", ENGINES),
    pytest.mark.usefixtures("daemon"),
]

#: A workspace no host is on, so the page asks the faked host alone.
_FAKE = "/nowhere/fake-workspace"
_SUB = "s-chat"
_SLOT = "chat:fake"
_CHAT = "20261117T000000.000Z-c4a7e0"
_STARTED = {
    "flow": "chat",
    "ref": "chat:chat",
    "task": "hello there",
    "by": "me@web",
    "client": "c1",
    "roles": ["assistant"],
    "names": {"assistant": "Ada"},
    "outworlders": ["human"],
    "agents": {"assistant": "claude/claude-haiku-4-5"},
    "envs": {},
    "params": {},
    "began": 100.0,
    "at": 1794879452.0,
}
#: The chat as `chat.list` rows it, no host holding it.
_ROW: dict[str, Any] = {
    "id": _CHAT,
    "title": "hello there",
    "workspace": _FAKE,
    "workdir": _FAKE,
    "agent": "claude/claude-haiku-4-5",
    "model": "claude-haiku-4-5",
    "began": "2026-11-17T00:00:00.000Z",
    "updated": "2026-11-17T00:00:00.000Z",
    "state": "resting",
    "slot": "",
    "asking": [],
    "permission": "workspace-write",
    "archived": False,
    "spent": None,
}
#: The chat as `chat.get` answers it, with the one session it opened.
_DETAIL: dict[str, Any] = {
    **_ROW,
    "at": "/nowhere/chat",
    "task": "hello there",
    "prefer": "",
    "forked": "",
    "agents": [
        {
            "name": "Ada",
            "role": "assistant",
            "runs": "claude/claude-haiku-4-5",
            "backend": "claude",
            "model": "claude-haiku-4-5",
            "effort": "",
            "provider": "",
        }
    ],
    "sessions": [
        {
            "agent": "Ada",
            "role": "assistant",
            "backend": "claude",
            "provider": "",
            "ident": "s1",
            "at": "2026-11-17T00:00:00.000Z",
            "flow": "",
            "harness": "",
        }
    ],
    "earlier": 0,
    "backup": [],
    "backed": {},
}

#: What a test watches the page by, from before any of its own scripts run: every note that
#: something is being read or opened that is ever put on the page, and every frame in which a
#: conversation's view stands without a line of its conversation.
_WATCHED = """
window.__notes = []
window.__blank = 0
const NOTES = [
  '.view-epic .loading',
  '.view-epic .thread-empty',
  '[data-hmz=aichan-chat] .thread-empty',
].join(', ')
new MutationObserver((changes) => {
  for (const change of changes) {
    for (const node of change.addedNodes) {
      if (node.nodeType !== 1) continue
      for (const one of [node, ...node.querySelectorAll('*')]) {
        if (one.matches(NOTES)) window.__notes.push(one.textContent)
      }
    }
  }
}).observe(document, { childList: true, subtree: true })
const frame = () => {
  const view = document.querySelector('.view-epic')
  if (view && !view.querySelector('[data-hmz=thread] .said')) window.__blank += 1
  requestAnimationFrame(frame)
}
requestAnimationFrame(frame)
"""

#: Marks each line drawn by where it stands, and says what the page shows: the lines, the
#: marks they bore before, the notes ever put on it and the frames that showed no line.
_SHOWN = """(mark) => {
  const lines = [...document.querySelectorAll('[data-hmz=thread] .said')]
  const was = lines.map((one) => one.__was ?? null)
  if (mark) lines.forEach((one, at) => (one.__was = at))
  const scroller = document.querySelector('.thread-scroll')
  return {
    lines: lines.map((one) => one.querySelector('.body').textContent),
    was,
    notes: window.__notes,
    blank: window.__blank,
    top: scroller ? Math.round(scroller.scrollTop) : null,
  }
}"""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, asked what it runs, and a project to serve."""
    project = install(tmp_path, monkeypatch)
    (tmp_path / "home").mkdir(exist_ok=True)
    return project


class _Wire(Wire):
    """The wire, which also tells the page what a faked host says, and answers late."""

    def event(self, message: dict[str, Any]) -> None:
        """Tells the page one message of the faked host."""
        assert self._page is not None
        self._page.send(
            frame(
                {
                    "jsonrpc": "2.0",
                    "method": "epic.event",
                    "params": {"sub": _SUB, "message": message},
                }
            )
        )

    def reply(self, page: Page, method: str, reply: dict[str, Any]) -> None:
        """Answers the first call of `method` held back: a result, or an error."""
        while not any(one == method for one, _ in self._later):
            page.wait_for_timeout(50)
        at = next(i for i, (one, _) in enumerate(self._later) if one == method)
        _, ident = self._later.pop(at)
        assert self._page is not None
        self._page.send(frame({"jsonrpc": "2.0", "id": ident, **reply}))


@dataclasses.dataclass
class _Gate:
    """What answers one method: at once, or, while `shut`, only once it is opened.

    Attributes:
      method: The method.
      answers: What it answers, given the params it was called with.
      shut: Whether what is called is held back.
      waiting: The params of each call held back, in order.
    """

    method: str
    answers: Callable[[dict[str, Any]], dict[str, Any]]
    shut: bool = False
    waiting: list[dict[str, Any]] = dataclasses.field(
        default_factory=list[dict[str, Any]]
    )

    def __call__(self, params: dict[str, Any]) -> dict[str, Any] | None:
        if self.shut:
            self.waiting.append(params)
            return None
        return self.answers(params)

    def open(self, page: Page, wire: _Wire) -> None:
        """Answers every call held back, in the order they came, and holds back no more."""
        self.shut = False
        waiting, self.waiting = self.waiting, []
        for params in waiting:
            wire.reply(page, self.method, self.answers(params))


def _trace(said: list[str]) -> list[dict[str, Any]]:
    """What the chat's logs say: its first message, then each answer."""
    return [
        {
            "key": "claude:s1",
            "agent": "Ada",
            "actions": [
                {
                    "category": "turn",
                    "name": "turn",
                    "start": 1.0,
                    "seconds": 1.0,
                    "args": {"prompt": "hello there"},
                },
                *(
                    {
                        "category": "message",
                        "name": "message",
                        "start": 2.0 + at,
                        "seconds": 0.0,
                        "args": {"text": text},
                    }
                    for at, text in enumerate(said)
                ),
            ],
        }
    ]


def _rested(said: list[str]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """`chat.get` of the chat at rest, with what its logs say where they are asked for."""

    def answers(params: dict[str, Any]) -> dict[str, Any]:
        return {
            "result": {
                **_DETAIL,
                **({"trace": _trace(said)} if params.get("trace") else {}),
            }
        }

    return answers


def _shown(page: Page, *, mark: bool = False) -> dict[str, Any]:
    return page.evaluate(_SHOWN, mark)


def _fresh(page: Page) -> None:
    """Forgets what was watched so far: what is watched from here is what is opened next."""
    page.evaluate("() => { window.__notes.length = 0; window.__blank = 0 }")


def test_a_chat_opened_again_is_drawn_at_once_and_read_again_behind_what_is_drawn(
    project: Path, engine: str
) -> None:
    said = [f"answer {at} " + "and a good deal more of it " * 6 for at in range(40)]
    gate = _Gate("chat.get", _rested(said))
    wire = _Wire(faked={"chat.get": gate})
    with (
        served() as site,
        opened(site, engine=engine, routed=wire.routes, init=_WATCHED) as page,
    ):
        go(page, f"/chats/{_CHAT}")
        lines = page.locator("[data-hmz=thread] .said")
        expect(lines).to_have_count(41)
        # Read from where the reader left it: some way up from its end.
        page.evaluate("document.querySelector('.thread-scroll').scrollTop = 300")
        go(page, "/new/chat")
        expect(page.locator("[data-hmz=thread]")).to_have_count(0)

        # A line is said meanwhile, and the daemon is slow to answer anything of the chat.
        said.append("said meanwhile")
        gate.shut = True
        _fresh(page)
        go(page, f"/chats/{_CHAT}")
        expect(lines).to_have_count(41)
        first = _shown(page, mark=True)
        # Drawn by what was kept alone -- the daemon has answered nothing -- in the frame
        # it opened in, where it was left, with no note of its being read ever on the page.
        assert gate.waiting
        assert first["lines"][0] == "hello there"
        assert first["lines"][-1] == said[39]
        assert first["notes"] == []
        assert first["blank"] == 0
        assert first["top"] == 300
        expect(page.locator("[data-hmz=chat-title]")).to_have_text("hello there")
        # What is typed while the daemon is asked stays typed, where it is typed.
        box = page.locator("[data-hmz=say] textarea")
        box.fill("a draft")

        gate.open(page, wire)
        expect(lines).to_have_count(42)
        after = _shown(page)
        # Only the new line is made: every line drawn is the node it was, and nothing moved.
        assert after["lines"][-1] == "said meanwhile"
        assert after["was"] == [*range(41), None]
        assert after["notes"] == []
        assert after["blank"] == 0
        assert after["top"] == 300
        expect(box).to_have_value("a draft")
        expect(box).to_be_focused()

        # Kept in the browser too: the page opened again on it draws it before the
        # daemon has said anything of it.
        go(page, "/new/chat")
        gate.shut = True
        page.evaluate(
            """async (chat) => {
              const { logs } = await import('/logged.js')
              await logs.flush()
              location.hash = '/chats/' + chat
            }""",
            _CHAT,
        )
        again(page)
        expect(lines).to_have_count(42)
        assert gate.waiting
        assert _shown(page)["notes"] == []
        gate.open(page, wire)
        expect(lines).to_have_count(42)


def test_a_chat_deleted_elsewhere_is_not_drawn_by_what_was_kept_of_it(
    project: Path, engine: str
) -> None:
    gate = _Gate("chat.get", _rested(["an answer"]))
    wire = _Wire(faked={"chat.get": gate})
    with (
        served() as site,
        opened(site, engine=engine, routed=wire.routes, init=_WATCHED) as page,
    ):
        go(page, f"/chats/{_CHAT}")
        lines = page.locator("[data-hmz=thread] .said")
        expect(lines).to_have_count(2)
        go(page, "/new/chat")
        # Deleted meanwhile, from another page or the terminal.
        gate.answers = lambda _: {
            "error": {"code": 404, "message": f"There is no chat {_CHAT}."}
        }
        for _ in range(2):
            go(page, f"/chats/{_CHAT}")
            expect(page.locator(".view-epic")).to_contain_text("There is no chat")
            expect(lines).to_have_count(0)
            expect(page.locator("[data-hmz=say]")).to_have_count(0)
            # And nothing is kept of it to draw it by.
            assert (
                page.evaluate(
                    "async () => (await import('/logged.js')).logs.keys().length"
                )
                == 0
            )
            go(page, "/new/chat")


def test_the_latest_chats_of_the_sidebar_are_read_ahead_and_open_at_once(
    project: Path, engine: str
) -> None:
    gate = _Gate("chat.get", _rested(["an answer"]))
    wire = _Wire(
        faked={
            "chat.get": gate,
            "chat.list": lambda _: {
                "result": {"chats": [_ROW], "total": 1, "offset": 0, "limit": 60}
            },
        }
    )
    with (
        served() as site,
        opened(site, engine=engine, routed=wire.routes, init=_WATCHED) as page,
    ):
        go(page, "/new/chat")
        # Read ahead once the page has nothing else to do: asked for with its logs.
        while not any(one.get("trace") for one in wire.params("chat.get")):
            page.wait_for_timeout(100)
        page.wait_for_function(
            "async () => (await import('/logged.js')).logs.keys().length === 1"
        )
        gate.shut = True
        _fresh(page)
        # Never opened here, it is drawn at once all the same.
        page.locator("[data-hmz=sidebar]").get_by_text("hello there").first.click()
        lines = page.locator("[data-hmz=thread] .said")
        expect(lines).to_have_count(2)
        first = _shown(page)
        assert gate.waiting
        assert first["lines"] == ["hello there", "an answer"]
        assert first["notes"] == []
        assert first["blank"] == 0
        gate.open(page, wire)
        expect(lines).to_have_count(2)
        assert _shown(page)["notes"] == []


def _welcomed(wire: _Wire, epoch: str, said: list[str]) -> None:
    """What the chat's faked host tells a page that attaches: all it holds, then `live`."""
    messages: list[dict[str, Any]] = [
        {
            "type": "welcome",
            "epoch": epoch,
            "client": "c1",
            "workspace": _FAKE,
            "slot": _SLOT,
        },
        {"type": "started", "seq": 1, "run": 1, **_STARTED},
        {
            "type": "opened",
            "seq": 2,
            "run": 1,
            "key": "Ada/1",
            "agent": "Ada",
            "role": "assistant",
        },
        *(
            {
                "type": "event",
                "seq": 3 + at,
                "run": 1,
                "session": "Ada/1",
                "kind": "text",
                "text": text,
                "at": 1794879460.0 + at,
            }
            for at, text in enumerate(said)
        ),
        {
            "type": "run",
            "state": "running",
            "run": 1,
            "epic": "",
            "chat": _CHAT,
            "slot": _SLOT,
            "turn": "",
            **_STARTED,
        },
        {"type": "sessions", "run": 1, "open": ["Ada/1"], "working": []},
        {"type": "pending", "pending": []},
        {"type": "live", "seq": 2 + len(said), "elided": 0},
    ]
    for message in messages:
        wire.event(message)


def _attached(page: Page, wire: _Wire, times: int) -> None:
    """Waits until the page has attached to the chat's host `times` times."""
    while len(wire.params("epic.attach")) < times:
        page.wait_for_timeout(50)


def test_a_chat_a_host_holds_is_drawn_at_once_and_added_to_as_its_host_tells_it(
    project: Path, engine: str
) -> None:
    going = {**_DETAIL, "state": "going", "slot": _SLOT}
    gate = _Gate("chat.get", lambda _: {"result": going})
    wire = _Wire(
        faked={
            "chat.get": gate,
            "epic.attach": lambda _: {
                "result": {"sub": _SUB, "workspace": _FAKE, "slot": _SLOT}
            },
            "epic.detach": lambda _: {"result": {}},
            "chat.commands": lambda _: {
                "result": {"entries": [], "prefer": "native", "prefer_from": "settings"}
            },
        }
    )
    with (
        served() as site,
        opened(site, engine=engine, routed=wire.routes, init=_WATCHED) as page,
    ):
        go(page, f"/chats/{_CHAT}")
        _attached(page, wire, 1)
        _welcomed(wire, "e1", ["first answer"])
        lines = page.locator("[data-hmz=thread] .said")
        expect(lines).to_have_count(2)
        go(page, "/new/chat")
        # Its host is let go of once nothing follows it: the next opening attaches anew.
        while not wire.params("epic.detach"):
            page.wait_for_timeout(100)

        gate.shut = True
        _fresh(page)
        go(page, f"/chats/{_CHAT}")
        expect(lines).to_have_count(2)
        first = _shown(page, mark=True)
        # Drawn by what was kept alone: the daemon has answered nothing, and no host is
        # attached to on the word of what was kept.
        assert gate.waiting
        assert len(wire.params("epic.attach")) == 1
        assert first["lines"] == ["hello there", "first answer"]
        assert first["notes"] == []
        assert first["blank"] == 0
        box = page.locator("[data-hmz=say] textarea")
        box.fill("a draft")

        # The daemon answers, its host is attached to, and tells what it holds from the
        # top: only what it says beyond what is drawn is added.
        gate.open(page, wire)
        _attached(page, wire, 2)
        _welcomed(wire, "e1", ["first answer", "said meanwhile"])
        expect(lines).to_have_count(3)
        after = _shown(page)
        assert after["lines"] == ["hello there", "first answer", "said meanwhile"]
        assert after["was"] == [0, 1, None]
        assert after["notes"] == []
        assert after["blank"] == 0
        expect(page.locator("[data-hmz=say] textarea")).to_have_value("a draft")

        # Another life of its host, which holds another conversation: drawn over what was
        # kept at once, once it has told all of it, with the view never emptied meanwhile.
        go(page, "/new/chat")
        while len(wire.params("epic.detach")) < 2:
            page.wait_for_timeout(100)
        _fresh(page)
        go(page, f"/chats/{_CHAT}")
        expect(lines).to_have_count(3)
        _attached(page, wire, 3)
        _welcomed(wire, "e2", ["rewritten"])
        expect(lines).to_have_count(2)
        last = _shown(page)
        assert last["lines"] == ["hello there", "rewritten"]
        assert last["notes"] == []
        assert last["blank"] == 0


def test_a_conversation_of_ai_chans_opened_again_is_drawn_at_once_and_added_to(
    project: Path, engine: str
) -> None:
    held = [
        {
            "id": 1,
            "title": "Hello",
            "scope": "daemon",
            "workspace": _FAKE,
            "epic": "",
            "nous": "claude/claude-opus-4-1",
            "preset": "read-only",
            "slot": _SLOT,
            "state": "waiting",
            "created": "2026-01-01T00:00:00Z",
            "latest": "hi",
            "updated": "2026-01-01T00:00:00Z",
        }
    ]
    wire = _Wire(
        faked={
            "aichan.list": lambda _: {"result": {"conversations": list(held)}},
            "chat.get": lambda _: {"result": {**_DETAIL, "slot": _SLOT}},
            "epic.attach": lambda _: {
                "result": {"sub": _SUB, "workspace": _FAKE, "slot": _SLOT}
            },
            "epic.detach": lambda _: {"result": {}},
        }
    )
    with (
        served() as site,
        opened(site, engine=engine, routed=wire.routes, init=_WATCHED) as page,
    ):
        go(page, "/new/chat")
        page.locator("[data-hmz=bar] [data-hmz=aichan-toggle]").click()
        drawer = page.locator("[data-hmz=aichan]")
        row = drawer.locator("[data-hmz=aichan-conversation] .aichan-pick")
        row.click()
        _attached(page, wire, 1)
        _welcomed(wire, "e1", ["first answer"])
        lines = drawer.locator("[data-hmz=aichan-log] .said")
        expect(lines).to_have_count(2)
        drawer.locator("[data-hmz=aichan-back]").click()
        while not wire.params("epic.detach"):
            page.wait_for_timeout(100)

        _fresh(page)
        row.click()
        # Drawn by what was kept, before her host has told anything, and never said to be
        # being opened.
        expect(lines).to_have_count(2)
        marked = page.evaluate(
            """() => {
              const lines = [...document.querySelectorAll('[data-hmz=aichan-log] .said')]
              lines.forEach((one, at) => (one.__was = at))
              const said = lines.map((one) => one.querySelector('.body').textContent)
              return { lines: said, notes: window.__notes }
            }"""
        )
        assert marked == {"lines": ["hello there", "first answer"], "notes": []}
        _attached(page, wire, 2)
        _welcomed(wire, "e1", ["first answer", "said meanwhile"])
        expect(lines).to_have_count(3)
        after = page.evaluate(
            """() => ({
              was: [...document.querySelectorAll('[data-hmz=aichan-log] .said')].map(
                (one) => one.__was ?? null,
              ),
              notes: window.__notes,
            })"""
        )
        assert after == {"was": [0, 1, None], "notes": []}

"""A question asked of a person, answered on the web page as one form with what it shows.

A flow of the project's own asks its person each line its agent says, as a stand-in host runs
it; on the wire between the page and Local, each question it asks is dressed as a flow asking
a schema with context would ask it -- `schema` and `context` on its `asked` record and on its
`pending` entry -- and an answer sent as a `value` is refused or let through as the host would
take it, as JSON text. So the page is driven as a person drives it: reading what is shown,
filling the form, sending a misfit and fixing it, leaving and coming back to a draft.

Run it by naming it: `uv run pytest tests/system/web/test_web_asks.py`. Set `HMZ_ASKS_SHOTS`
to a directory to keep the screenshots of the card it takes.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import os
import re
import struct
import urllib.parse
import zlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, again, go, opened

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page, WebSocketRoute

pytestmark = pytest.mark.usefixtures("daemon")

_TALK = '''
from hmz.flows import (
    Agent, AgentCollection, EnvCollection, FlowContext, FlowParams, LocalEnv, Outworlder,
    flow,
)


class Agents(AgentCollection):
    """An agent and its person."""

    assistant: Agent
    human: Outworlder


class Envs(EnvCollection):
    """The workspace."""

    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def talk(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Says each line to the agent, until its person says nothing."""
    assistant, human = agents["assistant"], agents["human"]
    conversation, person = await assistant.spawn(), await human.spawn()
    said = task
    while said:
        said = await human.run(
            await assistant.run(said, session=conversation, env=envs["workspace"]),
            session=person,
        )
'''

#: What the person is asked to answer: a review, as pydantic writes its schema.
_REVIEW: dict[str, Any] = {
    "title": "Review",
    "type": "object",
    "$defs": {
        "Verdict": {
            "enum": ["approve", "request changes", "reject"],
            "title": "Verdict",
            "type": "string",
        }
    },
    "properties": {
        "verdict": {"$ref": "#/$defs/Verdict", "description": "What to do with it."},
        "notes": {"title": "Notes", "type": "string", "maxLength": 400},
        "tests": {
            "default": True,
            "description": "Write tests",
            "title": "Tests",
            "type": "boolean",
        },
        "reviewers": {
            "default": 1,
            "minimum": 1,
            "title": "Reviewers",
            "type": "integer",
        },
        "labels": {
            "default": [],
            "items": {"type": "string"},
            "title": "Labels",
            "type": "array",
        },
        "summary": {
            "default": "",
            "title": "Summary",
            "type": "string",
            "hmz:widget": "markdown",
        },
    },
    "required": ["verdict", "notes"],
}

_PATCH = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
 import os
-print("hi")
+print("hello")
+print("world")
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-Old title
+New title
"""


def _png(width: int, height: int) -> str:
    """A small picture as base64 PNG: a band of the page's cyan fading to pink."""
    rows = b""
    for y in range(height):
        rows += b"\x00" + b"".join(
            bytes(
                (
                    31 + (236 - 31) * x // width,
                    179 - (179 - 111) * x // width,
                    199 - (199 - 163) * y // height,
                )
            )
            for x in range(width)
        )

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )
    return base64.b64encode(png).decode()


#: What each question shows beside what it asks: one block of every kind.
_CONTEXT: list[dict[str, Any]] = [
    {
        "kind": "markdown",
        "title": "What changed",
        "text": "The greeting now says **hello world**.\n\n- `src/app.py`\n- `README.md`",
    },
    {"kind": "diff", "patch": _PATCH},
    {
        "kind": "table",
        "title": "Timings",
        "columns": ["test", "ms"],
        "rows": [[f"test_{n}", 10 + n] for n in range(40)],
    },
    {"kind": "image", "mime": "image/png", "data": _png(160, 60), "alt": "a gradient"},
    {"kind": "json", "value": {"files": 2, "ok": True, "by": None}},
    {
        "kind": "chart",
        "title": "Coverage",
        "spec": {
            "mark": "bar",
            "data": {"values": [{"week": 1, "pct": 71}, {"week": 2, "pct": 78}]},
            "encoding": {
                "x": {"field": "week", "type": "ordinal"},
                "y": {"field": "pct", "type": "quantitative"},
            },
        },
    },
]


def _framed(value: Any) -> bytes:
    payload = json.dumps(value).encode()
    return struct.pack(">I", len(payload)) + payload


def _unframed(buffer: bytearray, message: str | bytes) -> list[Any]:
    buffer.extend(message.encode() if isinstance(message, str) else message)
    said: list[Any] = []
    while len(buffer) >= 4:
        (length,) = struct.unpack(">I", buffer[:4])
        if len(buffer) < 4 + length:
            break
        said.append(json.loads(bytes(buffer[4 : 4 + length])))
        del buffer[: 4 + length]
    return said


@dataclasses.dataclass
class _Asks:
    """`/rpc` between the page and Local, each question dressed as one asking a schema.

    Attributes:
      dress: What each `asked` record and `pending` entry is given besides its own.
      others: Frontends added to the `clients` the host says are attached.
      refusals: The errors each next answer sent as a value is refused with, in turn.
      answers: The params of every `epic.answer` the page called.
    """

    dress: dict[str, Any] = dataclasses.field(default_factory=dict[str, Any])
    others: list[dict[str, Any]] = dataclasses.field(
        default_factory=list[dict[str, Any]]
    )
    refusals: list[list[dict[str, Any]]] = dataclasses.field(
        default_factory=list[list[dict[str, Any]]]
    )
    answers: list[dict[str, Any]] = dataclasses.field(
        default_factory=list[dict[str, Any]]
    )

    _page: WebSocketRoute | None = None
    _sub: str = ""
    _run: int = 0
    _seq: float = 0

    def routes(self, page: Page) -> None:
        """Carries the page's `/rpc` from here on."""
        page.route_web_socket(re.compile(r".*/rpc$"), self._carries)

    def show(self, page: Page, context: list[dict[str, Any]]) -> None:
        """Tells the page the run showed its person `context`, as a `shown` record."""
        while not self._run:
            page.wait_for_timeout(50)
        assert self._page is not None
        self._seq += 0.5
        record = {
            "type": "shown",
            "seq": self._seq,
            "run": self._run,
            "role": "human",
            "session": "human/1",
            "context": context,
        }
        self._page.send(
            _framed(
                {
                    "jsonrpc": "2.0",
                    "method": "epic.event",
                    "params": {"sub": self._sub, "message": record},
                }
            )
        )

    def _dressed(self, said: dict[str, Any]) -> dict[str, Any]:
        if said.get("method") != "epic.event":
            return said
        message = said["params"]["message"]
        kind = message.get("type")
        if isinstance(message.get("seq"), int) and message.get("run"):
            self._sub = said["params"]["sub"]
            self._run = message["run"]
            self._seq = max(self._seq, message["seq"])
        if kind == "pending":
            message["pending"] = [
                {**one, **self.dress, "options": []}
                for one in message.get("pending", [])
            ]
        elif kind == "asked" and message.get("role") == "human":
            message.update(self.dress, options=[])
        elif kind == "clients" and self.others:
            message["clients"] = [*message.get("clients", []), *self.others]
        return said

    def _carries(self, ws: WebSocketRoute) -> None:
        server = ws.connect_to_server()
        self._page = ws
        up, down = bytearray(), bytearray()

        def from_page(message: str | bytes) -> None:
            for said in _unframed(up, message):
                params: dict[str, Any] = said.get("params") or {}
                if said.get("method") == "epic.answer" and "value" in params:
                    self.answers.append(params)
                    if self.refusals:
                        errors = self.refusals.pop(0)
                        ws.send(
                            _framed(
                                {
                                    "jsonrpc": "2.0",
                                    "id": said["id"],
                                    "error": {
                                        "code": 400,
                                        "message": "the answer does not fit: "
                                        + errors[0]["message"],
                                        "data": {"errors": errors},
                                    },
                                }
                            )
                        )
                        continue
                    # Taken as the host takes a schema's answer: as its JSON text.
                    rest = {key: one for key, one in params.items() if key != "value"}
                    said["params"] = {**rest, "text": json.dumps(params["value"])}
                server.send(_framed(said))

        def from_server(message: str | bytes) -> None:
            for said in _unframed(down, message):
                ws.send(_framed(self._dressed(said)))

        ws.on_message(from_page)
        server.on_message(from_server)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, and the project's own `talk` flow."""
    project = install(tmp_path, monkeypatch)
    (tmp_path / "home").mkdir(exist_ok=True)
    flows = project / ".hmz" / "flows" / "talk"
    flows.mkdir(parents=True)
    (flows / "__init__.py").write_text(_TALK)
    return project


def _start_talk(page: Page, task: str) -> str:
    """Starts the project's own `talk` as a page would, opens its graph, and answers its name."""
    started = page.evaluate(
        """async (task) => {
          const { started } = await import('/api.js')
          const { ask } = await import('/held.js')
          return ask(await started(), 'start', {flow: '@local/talk', task,
            budget: {cost: 5, duration: 600, output_tokens: 100000},
            agents: {assistant: 'claude/claude-haiku-4-5'}})
        }""",
        task,
    )
    go(page, f"/live?{urllib.parse.urlencode({'workspace': started['workspace']})}")
    page.wait_for_url(re.compile(r".*#/epics/[^/]+$"))
    return urllib.parse.unquote(page.url.split("#/epics/")[1])


def _card(page: Page) -> Locator:
    return page.locator("[data-hmz=waiting] [data-hmz=question]")


def _field(card: Locator, name: str) -> Locator:
    return card.locator(f"[data-hmz=ask-field][data-path={name}]")


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.usefixtures("project")
def test_a_schema_is_asked_as_one_form_under_what_it_shows(engine: str) -> None:
    wire = _Asks(
        dress={
            "schema": _REVIEW,
            "context": _CONTEXT,
            "face": None,
            "session": "human/1",
        },
        refusals=[[{"path": ["notes"], "message": "Say what to change."}]],
    )
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        _start_talk(page, "review this")
        card = _card(page)
        expect(card).to_be_visible()
        # Long as the form is, the graph over it keeps its floor and the box under it
        # stays whole in the window: the form scrolls between them.
        graph = page.locator(".epic-main").bounding_box()
        box = page.locator("[data-hmz=say]").bounding_box()
        assert graph is not None
        assert box is not None
        assert graph["height"] >= 260
        assert box["y"] + box["height"] <= 860
        # Read, then decide: the question, what it shows, then the form.
        blocks = card.locator("[data-hmz=ask-block]")
        expect(blocks).to_have_count(len(_CONTEXT))
        expect(blocks.nth(0)).to_have_attribute("open", "")
        expect(blocks.nth(0)).to_contain_text("hello world")
        expect(blocks.nth(1).locator("[data-hmz=ask-block-summary]")).to_have_text(
            "+3 \u22122 in 2 files"
        )
        # A long table is folded behind what it holds, until asked for.
        table = blocks.nth(2)
        expect(table.locator("[data-hmz=ask-block-summary]")).to_have_text(
            "table · 40 rows"
        )
        expect(table).not_to_have_attribute("open", "")
        table.locator("summary").click()
        expect(table.locator("tbody tr")).to_have_count(20)
        table.get_by_role("button", name="Show all 40 rows").click()
        expect(table.locator("tbody tr")).to_have_count(40)
        # Every block past the first waits behind its summary, drawn once it is opened.
        for at in (1, 3, 4, 5):
            expect(blocks.nth(at)).not_to_have_attribute("open", "")
            blocks.nth(at).locator("summary").click()
        expect(blocks.nth(3).locator("img")).to_have_attribute("alt", "a gradient")
        expect(blocks.nth(4).locator("[data-hmz=ask-json]")).to_contain_text("files: 2")
        # A chart is drawn, or, without the page's Vega, its data is a table.
        expect(blocks.nth(5).locator("table, svg, canvas").first).to_be_visible()
        expect(blocks.nth(1).locator("[data-hmz=ask-diff-file]")).to_have_count(2)

        # Few choices are buttons; what is required comes first; a suggestion is folded away.
        verdict = _field(card, "verdict")
        expect(verdict.get_by_role("radio")).to_have_count(3)
        fields = card.locator("[data-hmz=ask-fields] > [data-hmz=ask-field]")
        expect(fields.first).to_have_attribute("data-path", "verdict")
        expect(fields.nth(1)).to_have_attribute("data-path", "notes")
        more = card.locator("[data-hmz=ask-more]")
        expect(more.locator("summary")).to_have_text("More options (4)")
        more.locator("summary").click()
        tests = _field(card, "tests")
        expect(tests.get_by_role("radio", name="Yes, write tests")).to_have_attribute(
            "aria-checked", "true"
        )
        expect(tests.locator("[data-hmz=suggested]")).to_be_visible()

        # What is left is said on the button; sent early, each missing field says so.
        send = card.locator("[data-hmz=ask-send]")
        expect(send).to_have_text("2 required left")
        send.click()
        expect(verdict.locator(".problem")).to_have_text("This needs an answer.")
        expect(_field(card, "notes").locator(".problem")).to_have_text(
            "This needs an answer."
        )
        expect(verdict.get_by_role("radio").first).to_be_focused()
        assert not wire.answers

        # A number picks a choice where nothing is typed; picking clears what was wrong.
        page.keyboard.press("2")
        expect(verdict.get_by_role("radio", name="request changes")).to_have_attribute(
            "aria-checked", "true"
        )
        expect(verdict.locator(".problem")).to_be_hidden()
        expect(send).to_have_text("1 required left")
        notes = _field(card, "notes").locator("textarea")
        notes.fill("nits")
        expect(send).to_have_text("Send answer")

        # Refused by the host, its word is said beside its field, and the cursor goes there.
        notes.press("ControlOrMeta+Enter")
        expect(_field(card, "notes").locator(".problem")).to_have_text(
            "Say what to change."
        )
        expect(notes).to_be_focused()
        expect(notes).to_have_attribute("aria-invalid", "true")
        # What is optional and left blank is left out, for the flow's own default.
        assert wire.answers[0]["value"] == {
            "verdict": "request changes",
            "notes": "nits",
            "tests": True,
            "reviewers": 1,
        }

        notes.fill("Rename the greeting.")
        send.click()
        settled = page.locator(
            "[data-hmz=asked-settled] [data-hmz=ask-closed-said]"
        ).first
        expect(settled).to_have_text(
            "You answered: request changes · \u2018Rename the greeting.\u2019 · tests: yes"
            " · reviewers: 1"
        )
        assert wire.answers[1]["value"]["notes"] == "Rename the greeting."
        assert "text" not in wire.answers[1]
        # The run goes on, and asks again.
        expect(_card(page)).to_be_visible()


@pytest.mark.usefixtures("project")
def test_a_draft_outlives_a_reload_and_a_list_is_added_to() -> None:
    wire = _Asks(
        dress={"schema": _REVIEW, "context": [], "face": None, "session": "human/1"}
    )
    with served() as site, opened(site, routed=wire.routes) as page:
        _start_talk(page, "draft me")
        card = _card(page)
        _field(card, "notes").locator("textarea").fill("half a thought")
        card.locator("[data-hmz=ask-more] summary").click()
        labels = _field(card, "labels")
        labels.get_by_role("button", name="+ Add label").click()
        labels.locator("[data-hmz=ask-item] input").fill("ui")
        expect(card.locator("[data-hmz=ask-draft]")).to_have_text("Draft kept")

        again(page)
        card = _card(page)
        expect(_field(card, "notes").locator("textarea")).to_have_value(
            "half a thought"
        )
        # What was changed from a suggestion is not folded away.
        expect(card.locator("[data-hmz=ask-more]")).to_have_attribute("open", "")
        expect(
            _field(card, "labels").locator("[data-hmz=ask-item] input")
        ).to_have_value("ui")
        _field(card, "labels").get_by_role("button", name="Remove label 1").click()
        expect(_field(card, "labels").locator("[data-hmz=ask-item]")).to_have_count(0)

        # Left untouched, a field passed by is not told it is missing; a bad number is, once left.
        reviewers = _field(card, "reviewers").locator("input")
        reviewers.fill("0")
        reviewers.press("Tab")
        expect(_field(card, "reviewers").locator(".problem")).to_have_text(
            "At least 1."
        )
        expect(_field(card, "verdict").locator(".problem")).to_be_hidden()


@pytest.mark.usefixtures("project")
def test_a_question_another_frontend_holds_is_read_waiting_for_it() -> None:
    wire = _Asks(
        dress={"schema": _REVIEW, "context": _CONTEXT[:1], "owner": "c-other"},
        others=[{"client": "c-other", "name": "Ana\u2019s laptop"}],
    )
    with served() as site, opened(site, routed=wire.routes) as page:
        _start_talk(page, "held")
        card = _card(page)
        expect(card.locator("[data-hmz=ask-held]")).to_have_text(
            "●Waiting for Ana\u2019s laptop to answer: that frontend holds human."
        )
        expect(card.locator("[data-hmz=ask-block]")).to_have_count(1)
        expect(_field(card, "verdict").get_by_role("radio").first).to_be_disabled()
        expect(card.locator("[data-hmz=ask-send]")).to_have_count(0)


@pytest.mark.usefixtures("project")
def test_what_a_flow_shows_and_asks_is_in_its_persons_log() -> None:
    wire = _Asks(
        dress={"schema": _REVIEW, "context": _CONTEXT[:2], "session": "human/1"}
    )
    with served() as site, opened(site, routed=wire.routes) as page:
        name = _start_talk(page, "log me")
        expect(_card(page)).to_be_visible()
        go(page, f"/epics/{urllib.parse.quote(name)}/logs/human")
        asked = page.locator("[data-hmz=thread] .said.asks").first
        expect(asked.locator("[data-hmz=ask-block]")).to_have_count(2)
        expect(asked.locator("[data-hmz=ask-form-note]")).to_have_text(
            "form · 6 fields"
        )

        # What a flow shows its person with nothing asked is in their log, as it comes.
        wire.show(page, _CONTEXT[2:3])
        shown = page.locator("[data-hmz=thread] [data-hmz=said-shown]")
        expect(shown).to_contain_text("shown to human")
        expect(shown.locator("[data-hmz=ask-block-summary]")).to_have_text(
            "table · 40 rows"
        )
        # The only block, it is open, long as it is.
        expect(shown.locator("[data-hmz=ask-block]")).to_have_attribute("open", "")


@pytest.mark.parametrize(
    ("width", "dark"), [(375, False), (375, True), (1280, False), (1280, True)]
)
@pytest.mark.usefixtures("project")
def test_the_card_as_it_looks(width: int, dark: bool, tmp_path: Path) -> None:
    shots = Path(os.environ.get("HMZ_ASKS_SHOTS") or tmp_path)
    shots.mkdir(parents=True, exist_ok=True)
    wire = _Asks(dress={"schema": _REVIEW, "context": _CONTEXT, "session": "human/1"})
    with (
        served() as site,
        opened(site, routed=wire.routes, width=width, height=900, dark=dark) as page,
    ):
        _start_talk(page, "look")
        card = _card(page)
        expect(card).to_be_visible()
        page.emulate_media(reduced_motion="reduce")
        tone = "dark" if dark else "light"
        page.screenshot(path=shots / f"page-{width}-{tone}.png", animations="disabled")
        # The card whole, past the height the dock gives it.
        page.add_style_tag(content=".questions { max-height: none !important; }")
        card.screenshot(path=shots / f"card-{width}-{tone}.png", animations="disabled")
        card.locator("[data-hmz=ask-send]").click()
        card.locator("[data-hmz=ask-more] summary").click()
        card.screenshot(
            path=shots / f"card-{width}-{tone}-problems.png", animations="disabled"
        )
        blocks = card.locator("[data-hmz=ask-block]")
        for at in range(1, len(_CONTEXT)):
            blocks.nth(at).locator("summary").click()
        card.screenshot(
            path=shots / f"card-{width}-{tone}-open.png", animations="disabled"
        )
        # Nothing runs past the card's edge, on a phone or a desk.
        assert page.evaluate(
            "(el) => el.scrollWidth <= el.clientWidth + 1", card.element_handle()
        )

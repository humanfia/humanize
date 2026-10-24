"""`hmz web`'s page, driven in a browser: starting an epic, reading and steering it, finding it.

Each test opens the page the way somebody does -- the printed address in a browser -- over runs
held in the test's own process, with the stand-in `claude` the only coding agent on PATH, and
does what they would: clicks, types and reads what is drawn. Each does so in Chromium and in
WebKit, which the macOS app's window is.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect

import hmz.coganchor.models
import hmz.web.places
from hmz.runtime.doing import hosting
from tests.integration.doubles_core import install
from tests.integration.doubles_web import backed_up_elsewhere, elsewhere, served
from tests.system.web.doubles_browser import ENGINES, go, opened, stop

if TYPE_CHECKING:
    from playwright.sync_api import FloatRect, Locator, Page, Route

#: Every settings page, by the word its address ends in.
_PAGES = (
    "general",
    "themes",
    "accounts",
    "fallback",
    "runtimes",
    "backup",
    "workspace",
    "usage",
)

#: What the macOS app's window says it is: WKWebView, and the app.
_APP = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) humanize-desktop/0.0.0"
)

pytestmark = pytest.mark.parametrize("engine", ENGINES)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, asked what it runs, and a project to serve."""
    return install(tmp_path, monkeypatch)


def _start_chat(page: Page, task: str) -> None:
    """Starts chat from a new epic's box, on whichever model its agent is offered first.

    A chat is opened on its conversation, as a chat app opens on one, not on its graph.
    """
    go(page, "/new?flow=chat")
    expect(page.locator("[data-hmz=flow-picker] b")).to_have_text("chat")
    page.get_by_role("button", name="Options").click()
    expect(page.locator("[data-role=assistant] [data-hmz=pick-model]")).to_have_value(
        "claude-haiku-4-5"
    )
    page.locator("[data-hmz=composer-text]").fill(task)
    page.locator("[data-hmz=composer-text]").press("Enter")
    page.wait_for_url(re.compile(r".*#/epics/[^/]+/sessions/[^/]+%2F1$"))


#: A flow of the project's own that talks as chat does, but is a flow: drawn as a graph of its
#: agents, and stopped from its page.
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


@pytest.fixture
def talking(project: Path) -> None:
    """The project's own `talk`, offered from the start."""
    flows = project / ".hmz" / "flows" / "talk"
    flows.mkdir(parents=True)
    (flows / "__init__.py").write_text(_TALK)


def _start_talk(page: Page, task: str) -> None:
    """Starts the project's own `talk` from the API, as a page would, and opens its graph."""
    started = page.evaluate(
        """async (task) => {
          const answer = await fetch('/api/held/start', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({flow: '@local/talk', task,
              budget: {cost: 5, duration: 600, output_tokens: 100000},
              agents: {assistant: 'claude/claude-haiku-4-5'}}),
          })
          return [answer.status, await answer.text()]
        }""",
        task,
    )
    assert started[0] == 200, started[1]
    go(page, "/live")
    page.wait_for_url(re.compile(r".*#/epics/[^/]+$"))
    expect(page.locator("[data-hmz=graph-session]").first).to_be_visible()


def test_a_new_epic_offers_each_role_the_models_its_cli_runs(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new?flow=chat")
        page.get_by_role("button", name="Options").click()
        role = page.locator("[data-role=assistant]")
        expect(role.locator("[data-hmz=pick-cli]")).to_have_value("claude")
        expect(role.locator("[data-hmz=pick-account] option").first).to_have_text(
            "Local"
        )
        models = role.locator("[data-hmz=pick-model] option")
        expect(models).to_have_text(["claude-haiku-4-5", "claude-opus-4-1", "Other…"])

        role.locator("[data-hmz=pick-model]").select_option("claude-opus-4-1")
        efforts = role.locator("[data-hmz=pick-effort] option")
        expect(efforts).to_have_text(
            ["Default", "ultracode", "max", "high", "medium", "low"]
        )
        role.locator("[data-hmz=pick-effort]").select_option("max")
        expect(page.locator(".composer-summary")).to_contain_text(
            "assistant: claude/claude-opus-4-1:max"
        )


def _centre(node: Locator) -> dict[str, float]:
    """Where a node's middle is on the graph: what is drawn around the graph can move it."""
    expect(node).to_be_visible()
    box = node.bounding_box()
    canvas = node.page.locator("[data-hmz=graph]").bounding_box()
    assert box
    assert canvas
    return {
        "x": box["x"] + box["width"] / 2 - canvas["x"],
        "y": box["y"] + box["height"] / 2 - canvas["y"],
    }


def _comes_to(node: Locator, x: float, y: float) -> dict[str, float]:
    """Where a node's middle comes to rest, once it is within a pixel or two of where asked.

    A drag, a wheel or a button moves the graph on the page's next frame, and a page under
    load draws that frame late: what is measured at once can be where it was.
    """
    deadline = time.monotonic() + 10
    while not _near(at := _centre(node), x, y) and time.monotonic() < deadline:
        node.page.wait_for_timeout(50)
    assert _near(at, x, y), f"{at} is not ({x}, {y})"
    return at


def _near(at: dict[str, float], x: float, y: float) -> bool:
    """Whether a point is within a pixel or two of another."""
    return abs(at["x"] - x) < 2 and abs(at["y"] - y) < 2


def _box(node: Locator) -> FloatRect:
    """Where a node is on the page, once it is drawn: a graph redrawn replaces its nodes."""
    deadline = time.monotonic() + 10
    while (box := node.bounding_box()) is None and time.monotonic() < deadline:
        node.page.wait_for_timeout(50)
    assert box
    return box


@pytest.mark.usefixtures("talking")
def test_the_graph_is_dragged_anywhere_zoomed_by_the_wheel_and_recentred(
    engine: str,
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_talk(page, "move me")
        agent = page.locator("[data-hmz=graph-agent]").filter(has_text="assistant")
        expect(agent.locator("[data-hmz=graph-session]")).to_be_visible()
        # Stopped, so nothing it goes on to do redraws the graph while it is moved.
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()
        expect(page.locator("[data-hmz=bar] .badge")).to_have_text(
            re.compile("stopped")
        )
        # Measured once the graph and what is drawn around it have stopped moving: what
        # settles around it -- what the run spent, how long it took -- resizes the canvas.
        page.wait_for_function(
            """() => new Promise((settled) => {
              const at = () => JSON.stringify(['[data-hmz=graph-agent]:not(.person)',
                '[data-hmz=graph]'].map((one) => document.querySelector(one)
                  ?.getBoundingClientRect()))
              const before = at()
              setTimeout(() => settled(!before.includes('null') && at() === before), 1000)
            })""",
            polling=100,
        )
        canvas = _box(page.locator("[data-hmz=graph]"))
        drawn = _centre(agent)
        address = page.url

        # Dragged from a session on the node, past where the graph ends: nothing opens.
        session = _box(agent.locator("[data-hmz=graph-session]"))
        page.mouse.move(session["x"] + 10, session["y"] + 10)
        page.mouse.down()
        page.mouse.move(session["x"] - 290, session["y"] - 190, steps=8)
        page.mouse.up()
        moved = _comes_to(agent, drawn["x"] - 300, drawn["y"] - 200)
        assert page.url == address

        # Two fingers slid over a trackpad move it; a pinch and a mouse's wheel zoom it.
        zoom = page.locator("[data-hmz=graph] + .zoom .zoom-said")
        before = zoom.inner_text()
        page.mouse.move(canvas["x"] + canvas["width"] / 2, canvas["y"] + 40)
        page.mouse.wheel(30, 40)
        _comes_to(agent, moved["x"] - 30, moved["y"] - 40)
        expect(zoom).to_have_text(before)
        for wheel in ({"deltaY": -60, "ctrlKey": True}, {"deltaY": -3, "deltaMode": 1}):
            said = zoom.inner_text()
            page.evaluate(
                """(wheel) => document.querySelector('[data-hmz=graph]').dispatchEvent(
                  new WheelEvent('wheel', { ...wheel, clientX: 300, clientY: 300 }))""",
                wheel,
            )
            expect(zoom).not_to_have_text(said)

        page.get_by_role("button", name="Recenter").click()
        expect(zoom).to_have_text(before)
        _comes_to(agent, drawn["x"], drawn["y"])


def test_a_model_no_cli_would_list_is_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    install(tmp_path, monkeypatch)

    def refused(cli: str, provider: str = "", seconds: float = 0.0) -> tuple[()]:
        raise OSError(f"{cli} is not answering")

    monkeypatch.setattr(hmz.coganchor.models, "ask", refused)
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new?flow=chat")
        page.get_by_role("button", name="Options").click()
        role = page.locator("[data-role=assistant]")
        expect(role.locator("[data-hmz=agent-picker] .hint")).to_contain_text(
            "claude is not answering"
        )
        typed = role.locator("[data-hmz=pick-model-typed]")
        typed.fill("claude-sonnet-4-5")
        expect(page.locator(".composer-summary")).to_contain_text(
            "assistant: claude/claude-sonnet-4-5"
        )


def test_a_chat_is_its_conversation_alone_answered_and_read(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "hello there")

        # Read as a conversation: what you said, what it said back, and a follow-up typed
        # under it, never a question waiting for you.
        thread = page.locator("[data-hmz=thread]")
        expect(thread.locator(".said.you .body")).to_have_text(["hello there"])
        expect(thread).to_contain_text("did: hello there")
        # Running or done, as a chat app says it, never live or held.
        expect(page.locator("[data-hmz=epic] .pill-live")).to_have_count(0)
        say = page.locator("[data-hmz=say] textarea")
        # Its conversation goes by its agent's own name, not by the role it fills.
        expect(say).to_have_attribute("placeholder", re.compile(r"^Message \w+/1$"))
        expect(say).not_to_have_attribute("placeholder", "Message assistant/1")
        say.fill("and again")
        say.press("Enter")
        expect(thread).to_contain_text("did: and again")
        expect(thread.locator(".said.you .body")).to_have_text(
            ["hello there", re.compile(r"said\s*and again$")]
        )
        expect(page.locator("[data-hmz=waiting]")).to_have_count(0)

        # Only the conversation, as a chat app draws one: no graph, nothing under its row,
        # no Exomyth, and nothing to stop it by -- running while it answers, else done.
        bar = page.locator("[data-hmz=bar]")
        expect(bar.locator(".badge")).to_have_text(re.compile("running|done"))
        expect(bar.locator(".crumbs")).to_have_count(0)
        expect(page.get_by_role("button", name="Stop")).to_have_count(0)
        expect(page.locator("[data-hmz=exomyth-open]")).to_have_count(0)
        expect(page.locator("[data-hmz=graph]")).to_have_count(0)
        row = page.locator("[data-hmz=sidebar] .side-item").first
        expect(row.locator(".side-toggle, .side-tree")).to_have_count(0)
        expect(row.locator(".side-mark")).to_have_text(re.compile("[●✔]"))
        expect(page.get_by_role("tab", name="People")).to_have_count(0)
        bar.locator(".bar-title").click(button="right")
        expect(page.get_by_role("menuitem", name="Open")).to_be_visible()
        expect(page.get_by_role("menuitem", name="Exomyth")).to_have_count(0)
        expect(page.get_by_role("menuitem", name="Stop")).to_have_count(0)
        page.keyboard.press("Escape")

        # Opened again from its row, it is its conversation again, never a graph.
        page.locator("[data-hmz=epic]").first.click()
        page.wait_for_url(re.compile(r".*#/epics/[^/]+/sessions/[^/]+%2F1$"))
        expect(thread).to_contain_text("did: and again")

        stop(page)
        expect(bar.locator(".badge")).to_have_text(re.compile("done"))
        expect(page.locator("[data-hmz=epic] .side-mark").first).to_have_text("✔")


def test_a_chat_says_in_its_conversation_that_a_turn_could_not_be_taken(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "hello there")
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("did: hello there")
        say = page.locator("[data-hmz=say] textarea")
        say.fill("fail: the model is down")
        say.press("Enter")

        # Said where the answer would have been, and the conversation goes on.
        failed = thread.locator(".said.notice", has_text="That turn could not be taken")
        expect(failed).to_have_count(1)
        expect(failed).to_contain_text("the model is down")
        # An answer said back to ask what next is the answer drawn already, never twice.
        expect(thread.locator(".said", has_text="did: hello there")).to_have_count(1)
        say.fill("and again")
        say.press("Enter")
        expect(thread).to_contain_text("did: and again")
        stop(page)


def test_a_chat_that_kept_nothing_to_carry_on_says_it_cannot_be_continued(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "hello there")
        expect(page.locator("[data-hmz=thread]")).to_contain_text("did: hello there")
        stop(page)
        # As a chat of an earlier humanize was written down: with no journal to pick up.
        journals = list(project.parent.glob("humanize-home/epics/*/*/resume.jsonl"))
        assert journals
        for journal in journals:
            journal.unlink()
        page.reload()

        expect(page.locator("[data-hmz=not-carried]")).to_have_text(
            "This chat cannot be continued here."
        )
        expect(page.locator("[data-hmz=composer], [data-hmz=say]")).to_have_count(0)
        expect(page.get_by_role("link", name="Resume")).to_have_count(0)


def test_an_epic_is_found_by_its_task(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "find me later")
        stop(page)

        page.keyboard.press("Control+k")
        search = page.get_by_role("searchbox", name="Find")
        expect(page.locator("[data-hmz=found] .result")).to_have_count(1)
        # What is listed stays, marked old, until the search typed is answered.
        held: list[Route] = []

        def hold(route: Route) -> None:
            # Playwright takes a function of Python's, not a bound builtin.
            held.append(route)

        page.route("**/api/runs?*", hold)
        search.fill("find")
        found = page.locator("[data-hmz=found]")
        page.wait_for_timeout(500)
        assert held
        expect(found).to_have_attribute("aria-busy", "true")
        expect(found.locator(".result")).to_have_count(1)
        expect(search).to_have_value("find")
        for one in held:
            one.continue_()
        page.unroute("**/api/runs?*")
        expect(found).not_to_have_attribute("aria-busy", "true")
        search.fill("nothing like it")
        expect(page.locator("[data-hmz=found]")).to_contain_text(
            "No epic is like that."
        )
        search.fill("find me")
        expect(page.locator("[data-hmz=found] .result")).to_have_count(1)
        page.keyboard.press("Escape")
        expect(page.locator("[data-hmz=overlay]")).to_be_hidden()


#: A chat of the project's own that asks its person to pick one of two before going on.
_PICKING = '''
from typing import Literal

from pydantic import BaseModel

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


class Pick(BaseModel):
    colour: Literal["red", "blue"]


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def chat(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Asks which, then says it."""
    assistant, human = agents["assistant"], agents["human"]
    conversation, person = await assistant.spawn(), await human.spawn()
    await assistant.run(task, session=conversation, env=envs["workspace"])
    picked = await human.run("Which colour?", session=person, output_schema=Pick)
    said = f"colour {picked.colour}"
    while said:
        said = await human.run(
            await assistant.run(said, session=conversation, env=envs["workspace"]),
            session=person,
        )
'''


def test_a_chat_asks_in_its_conversation_and_is_answered_there(
    project: Path, engine: str
) -> None:
    flows = project / ".hmz" / "flows" / "chat"
    flows.mkdir(parents=True)
    (flows / "__init__.py").write_text(_PICKING)
    with served() as site, opened(site, engine=engine) as page:
        started = page.evaluate(
            """async () => {
              const answer = await fetch('/api/held/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({flow: 'chat', task: 'first',
                  budget: {cost: 5, duration: 600, output_tokens: 100000},
                  agents: {assistant: 'claude/claude-haiku-4-5'}}),
              })
              return [answer.status, await answer.text()]
            }"""
        )
        assert started[0] == 200, started[1]
        # A chat of its own, followed on its own host.
        slot = json.loads(started[1])["slot"]
        go(page, f"/live?{urllib.parse.urlencode({'slot': slot})}")
        page.wait_for_url(re.compile(r".*#/epics/[^/]+/sessions/[^/]+%2F1$"))

        # What it asks is asked in the thread, its answers there to pick, never as a card.
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("Which colour?")
        chips = page.locator("[data-hmz=thread-ask] button")
        expect(chips).to_have_text(["red", "blue"])
        expect(page.locator("[data-hmz=waiting]")).to_have_count(0)
        chips.nth(1).click()
        expect(thread).to_contain_text("did: colour blue")
        expect(page.locator("[data-hmz=thread-ask]")).to_have_count(0)

        say = page.locator("[data-hmz=say] textarea")
        say.fill("more")
        say.press("Enter")
        expect(thread).to_contain_text("did: more")


@pytest.mark.parametrize("name", _PAGES)
def test_every_settings_page_opens_and_reads(
    project: Path, name: str, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, f"/settings/{name}")
        body = page.locator(f"[data-hmz=settings-{name}]")
        expect(body).to_be_visible()
        expect(body.locator(".loading")).to_have_count(0)
        expect(body.locator(".error")).to_have_count(0)
        expect(page.locator(".settings-nav [aria-current=page]")).to_have_count(1)


#: A picture that moves: a disc drawn sliding to and fro, as an SVG animates itself.
_MOVING = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40">'
    b'<circle cx="10" cy="20" r="8" fill="#ec6fa3">'
    b'<animate attributeName="cx" values="10;30;10" dur="2s" repeatCount="indefinite"/>'
    b"</circle></svg>"
)


def _paints(page: Page, token: str) -> str:
    return page.evaluate(
        "(token) => getComputedStyle(document.documentElement)"
        ".getPropertyValue(token).trim()",
        token,
    )


def _painted(page: Page, token: str, said: str) -> None:
    """Waits for the page to paint a token with what says `said`: the page lets no string run."""
    for _ in range(100):
        if said in _paints(page, token):
            return
        page.wait_for_timeout(100)
    raise AssertionError(f"{token} is {_paints(page, token)!r}, not {said!r}")


#: Every pair of themes humanize comes with: its own, then twelve more, each named for a mood
#: and its colour.
_PAIRS = [
    "Humanize Green",
    "Temperate Gold",
    "Concordant Scarlet",
    "Restrained Crimson",
    "Critical Teal",
    "Desirous Indigo",
    "Peaceful Lilac",
    "Hateful Silver",
    "Devoted Pink",
    "Self-Negating Plum",
    "Dominant Azure",
    "Surviving Jade",
    "Lamenting Orchid",
]


def test_the_colours_are_a_pair_under_auto_or_a_theme(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        # A theme is chosen only in Settings: the daemon picker offers none.
        page.locator("[data-hmz=daemon-bar]").click()
        expect(page.locator("[role=menu] .choice-label")).to_have_text(
            ["Daemon", "Settings", "Usage"]
        )
        page.keyboard.press("Escape")
        go(page, "/settings/themes")
        expect(page.locator("[data-hmz=pair]")).to_have_count(len(_PAIRS))
        expect(page.locator("[data-hmz=auto-pair]")).to_have_value("humanize")
        page.locator("[data-hmz=auto-pair]").select_option(label="Peaceful Lilac")
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        _painted(page, "--paper", "#f7f2f7")
        page.emulate_media(color_scheme="dark")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        _painted(page, "--paper", "#151019")
        # Opened again, the pair is painted before the page is drawn.
        again = page.context.new_page()
        again.emulate_media(color_scheme="dark")
        again.goto(site.address)
        assert _paints(again, "--paper") == "#151019"
        again.close()

        # One theme of a pair, chosen outright, holds whatever the system is.
        expect(page.locator("[data-hmz=auto-pair]")).to_have_value("peaceful-lilac")
        page.get_by_role("button", name="Use Devoted Pink · Light").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        _painted(page, "--paper", "#fdf6f5")
        page.locator("[data-hmz=auto-pair]").select_option(label="Critical Teal")
        _painted(page, "--paper", "#0f1518")
        page.locator("[data-hmz=auto-light]").select_option(
            label="Hateful Silver · Light"
        )
        expect(page.locator("[data-hmz=auto-pair]")).to_have_value("")


def test_a_theme_is_made_written_out_read_back_and_paired_under_auto(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/themes")
        expect(page.locator("[data-hmz=theme]")).to_have_count(0)
        page.get_by_role("button", name="New", exact=True).click()
        editor = page.locator("[data-hmz=theme-editor]")
        expect(editor).to_be_visible()
        page.locator("[data-hmz=theme-name]").fill("Night")
        page.locator("[data-hmz=theme-base]").select_option("dark")
        # Shown on the page as it is changed, while it is edited.
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.locator("[data-hmz=colour-paper]").fill("#102030")
        page.locator("[data-hmz=colour-control]").fill("not a colour")
        expect(page.locator("[data-hmz=colour-control]")).to_have_attribute(
            "aria-invalid", "true"
        )
        assert _paints(page, "--paper") == "#102030"
        page.locator("[data-hmz=picture-page]").set_input_files(
            {"name": "moving.svg", "mimeType": "image/svg+xml", "buffer": _MOVING}
        )
        expect(page.locator("[data-hmz=plane-page] .theme-thumb")).not_to_have_class(
            re.compile("none")
        )
        assert _paints(page, "--page-image").startswith('url("data:image/svg+xml')

        # Left, the page is drawn in the theme chosen again.
        page.get_by_role("link", name="Done").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        night = page.locator("[data-hmz=theme]", has_text="Night")
        with page.expect_download() as saving:
            night.get_by_role("button", name="Export").click()
        saved = saving.value
        assert saved.suggested_filename == "Night.hmztheme"
        written = Path(saved.path()).read_text()
        night.get_by_role("button", name="Delete").click()
        night.get_by_role("button", name="Delete").click()
        expect(night).to_have_count(0)

        page.locator("[data-hmz=theme-file]").set_input_files(
            {
                "name": "Night.hmztheme",
                "mimeType": "application/json",
                "buffer": written.encode(),
            }
        )
        expect(night).to_have_count(1)
        page.locator("[data-hmz=auto-dark]").select_option(label="Night · Dark")
        page.emulate_media(color_scheme="dark")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        _painted(page, "--paper", "#102030")
        _painted(page, "--page-image", "data:image/svg+xml")
        # Where motion is asked to be reduced, the picture is held as it is first drawn.
        page.emulate_media(reduced_motion="reduce")
        _painted(page, "--page-image", "data:image/png")
        page.emulate_media(color_scheme="light")
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        # Opened again, it is painted before the page is drawn.
        again = page.context.new_page()
        again.emulate_media(color_scheme="dark")
        again.goto(site.address)
        assert again.evaluate("document.documentElement.dataset.theme") == "dark"
        assert _paints(again, "--paper") == "#102030"
        again.close()


def test_a_pair_is_made_written_out_with_both_its_themes_and_read_back(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/themes")
        page.get_by_role("button", name="New pair").click()
        expect(page.locator("[data-hmz=theme-side] [aria-pressed=true]")).to_have_text(
            "Light"
        )
        page.locator("[data-hmz=theme-name]").fill("Dusk")
        page.locator("[data-hmz=colour-paper]").fill("#fff8e0")
        page.locator("[data-hmz=theme-side]").get_by_role("button", name="Dark").click()
        expect(page.locator("[data-hmz=theme-side] [aria-pressed=true]")).to_have_text(
            "Dark"
        )
        expect(page.locator("[data-hmz=theme-name]")).to_have_value("Dusk")
        page.locator("[data-hmz=colour-paper]").fill("#201008")
        page.get_by_role("link", name="Done").click()

        dusk = page.locator("[data-hmz=pair]", has_text="Dusk")
        dusk.get_by_role("button", name="Export").click()
        with page.expect_download() as saving:
            page.get_by_role("menuitem", name="Pair").click()
        saved = saving.value
        assert saved.suggested_filename == "Dusk.hmztheme"
        written = json.loads(Path(saved.path()).read_text())
        assert written["name"] == "Dusk"
        assert written["light"]["colors"]["paper"] == "#fff8e0"
        assert written["dark"]["colors"]["paper"] == "#201008"

        dusk.get_by_role("button", name="Delete").click()
        dusk.get_by_role("button", name="Delete").click()
        expect(dusk).to_have_count(0)
        page.locator("[data-hmz=theme-file]").set_input_files(
            {
                "name": "Dusk.hmztheme",
                "mimeType": "application/json",
                "buffer": json.dumps(written).encode(),
            }
        )
        expect(dusk).to_have_count(1)
        page.locator("[data-hmz=auto-pair]").select_option(label="Dusk")
        _painted(page, "--paper", "#fff8e0")
        page.emulate_media(color_scheme="dark")
        _painted(page, "--paper", "#201008")
        expect(dusk).to_have_class(re.compile("chosen"))


def test_a_file_that_is_not_a_theme_is_refused(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/themes")
        page.locator("[data-hmz=theme-file]").set_input_files(
            {"name": "x.hmztheme", "mimeType": "application/json", "buffer": b"{}"}
        )
        expect(page.locator(".toast")).to_have_text("This is not a theme file")
        expect(page.locator("[data-hmz=theme]")).to_have_count(0)


def test_a_newer_release_is_offered_under_the_machine(
    project: Path, engine: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    import hmz.coganchor
    from hmz.coganchor import releases

    pypi = project.parent / "pypi.json"
    pypi.write_text(json.dumps({"info": {"version": "99.0.0"}}))
    monkeypatch.setenv(releases.WHENCE, str(pypi))
    monkeypatch.setattr(hmz.coganchor, "__version__", "0.1.0", raising=False)
    releases.fetch()
    with served() as site, opened(site, engine=engine) as page:
        expect(page.locator("[data-hmz=newer]")).to_be_visible()
        page.locator("[data-hmz=daemon-bar]").click()
        expect(page.locator("[role=menu] .choice-label")).to_have_text(
            ["Daemon", "Update", "Settings", "Usage"]
        )
        expect(page.locator("[role=menu] .choice-about").last).to_have_text(
            "hmz 99.0.0"
        )


def test_a_flow_is_opened_and_started_from_the_flows(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        page.get_by_role("link", name="Flows").click()
        page.locator(".card[data-flow=chat]").click()
        expect(page.locator(".flow-detail h2")).to_have_text("chat")
        page.get_by_role("link", name="New epic").last.click()
        expect(page.locator("[data-hmz=flow-picker] b")).to_have_text("chat")


def test_on_a_phone_the_sidebar_is_a_drawer(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine, width=390, height=844) as page:
        sidebar = page.locator("[data-hmz=sidebar]")
        expect(sidebar).not_to_be_in_viewport()
        page.locator("[data-hmz=bar] .bar-side").click()
        expect(sidebar).to_be_in_viewport()
        page.get_by_role("link", name="Flows").click()
        expect(sidebar).not_to_be_in_viewport()


def test_in_the_macos_app_the_top_row_is_drawn_around_the_traffic_lights(
    project: Path, engine: str
) -> None:
    """The app's window draws the page to its top edge, its traffic lights over the top left."""
    # How far across, and how far down, they reach, at most.
    lights = 76
    strip = 30
    clicked = "a, button, input, select, textarea, summary, [role=tab]"

    def left(page: Page, selector: str) -> float:
        box = page.locator(selector).first.bounding_box()
        assert box
        return box["x"]

    def top(page: Page, selector: str) -> float:
        box = page.locator(selector).first.bounding_box()
        assert box
        return box["y"]

    with served() as site, opened(site, engine=engine) as page:
        assert page.evaluate("document.documentElement.dataset.shell") is None
        expect(page.locator("[data-tauri-drag-region]")).to_have_count(0)
        assert left(page, ".brand") < lights
        assert top(page, ".brand") < strip

    # Said before the page is drawn: by the time its body is, so it never moves.
    at_body = (
        "new MutationObserver((_, seen) => { if (document.body) {"
        " window.shellAtBody = document.documentElement.dataset.shell; seen.disconnect() }"
        " }).observe(document, { childList: true, subtree: true })"
    )
    with (
        served() as site,
        opened(site, engine=engine, user_agent=_APP, init=at_body) as page,
    ):
        assert page.evaluate("window.shellAtBody") == "macos"
        # The sidebar keeps a strip for them, its top row drawn under it.
        assert top(page, ".brand") >= strip
        assert top(page, ".side-fold") >= strip
        for row in ("[data-hmz=sidebar] .side-top", "[data-hmz=bar]"):
            expect(page.locator(row)).to_have_attribute(
                "data-tauri-drag-region", "deep"
            )
        # The view itself, whose strip over what it draws is all of it not covered.
        expect(page.locator("[data-hmz=page]")).to_have_attribute(
            "data-tauri-drag-region", ""
        )
        expect(page.locator(f":is({clicked})[data-tauri-drag-region]")).to_have_count(0)
        # A menu opened in a row is not what the window is dragged by.
        page.locator("[data-hmz=daemon-bar]").click()
        expect(page.locator("[role=menu]")).to_have_attribute(
            "data-tauri-drag-region", "false"
        )
        page.keyboard.press("Escape")

        # Across the whole window: the view is drawn under the strip too.
        page.locator(".side-fold").click()
        assert top(page, "[data-hmz=bar] .bar-side") >= strip
        assert left(page, "[data-hmz=bar] .bar-side") < lights
        # Full screen, where they are gone, it is drawn as in a browser.
        page.evaluate(
            "document.documentElement.toggleAttribute('data-fullscreen', true)"
        )
        assert top(page, "[data-hmz=bar] .bar-side") < strip

        page.set_viewport_size({"width": 700, "height": 800})
        page.evaluate(
            "document.documentElement.toggleAttribute('data-fullscreen', false)"
        )
        assert top(page, "[data-hmz=bar] .bar-side") >= strip


def test_every_label_is_a_word_or_a_phrase(project: Path, engine: str) -> None:
    """A button, a tab, a menu item or a heading names a thing; it never says a sentence."""
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "label me")
        said: list[str] = []
        settings = (f"/settings/{one}" for one in _PAGES)
        for address in ("/new?flow=chat", "/flows", "/search", *settings):
            go(page, address)
            page.wait_for_timeout(300)
            if address.startswith("/new"):
                page.get_by_role("button", name="Options").click()
            said += page.locator(
                "button:visible, [role=tab]:visible, [role=menuitem]:visible, "
                "h2:visible:not(.greeting), h3:visible, .field > .label:visible, "
                ".field > label:visible"
            ).all_inner_texts()
        page.go_back()
        # A card or a row drawn as one button -- a flow, the workspace -- says several
        # things a line apiece; each of those lines is what is held to it.
        long = [
            one
            for one in (text.strip() for text in said)
            if one
            and "\n" not in one
            and (len(one.split()) > 4 or re.search(r"[.?!]$", one))
        ]
        assert not long, f"labels said as sentences: {long}"


def test_a_setup_is_saved_without_starting_an_epic(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new?flow=chat")
        page.get_by_role("button", name="Options").click()
        role = page.locator("[data-role=assistant]")
        expect(role.locator("[data-hmz=pick-model] option").first).to_have_text(
            "claude-haiku-4-5"
        )
        role.locator("[data-hmz=pick-model]").select_option("claude-opus-4-1")
        page.locator("[data-hmz=options]").get_by_role("button", name="Save").click()
        expect(
            page.locator("[data-hmz=options]").get_by_role("button", name="Saved")
        ).to_be_visible()

        page.reload()
        go(page, "/new?flow=chat")
        page.get_by_role("button", name="Options").click()
        expect(role.locator("[data-hmz=pick-model]")).to_have_value("claude-opus-4-1")


def test_a_start_says_it_is_starting_until_the_epic_opens(
    project: Path, engine: str
) -> None:
    held: list[Route] = []

    def hold(route: Route) -> None:
        held.append(route)

    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new?flow=chat")
        page.route("**/api/held/start", hold)
        page.get_by_role("button", name="Options").click()
        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_value("claude-haiku-4-5")
        page.locator("[data-hmz=composer-text]").fill("hold on")
        page.locator("[data-hmz=composer-text]").press("Enter")
        box = page.locator("[data-hmz=start]")
        expect(box).to_have_attribute("aria-busy", "true")
        expect(box.get_by_role("status")).to_have_text("Starting…")
        expect(box.get_by_role("button", name="Starting…")).to_be_disabled()
        held[0].continue_()
        page.wait_for_url(re.compile(r".*#/epics/[^/]+/sessions/[^/]+%2F1$"))


def test_a_workspace_read_marks_the_flow_drawn_until_it_is_read(
    project: Path, engine: str
) -> None:
    held: list[Route] = []

    def hold(route: Route) -> None:
        held.append(route)

    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new?flow=chat")
        expect(page.locator("[data-hmz=flow-picker] b")).to_have_text("chat")
        expect(page.locator("[data-hmz=options]")).not_to_have_class(
            re.compile("stale")
        )
        page.route(re.compile(r".*/api/flow\?name="), hold)
        page.locator("[data-hmz=flow-picker]").click()
        page.get_by_role("menuitem", name=re.compile("chat")).first.click()
        expect(page.locator(".greeting-about [role=status]")).to_have_text("Reading…")
        expect(page.locator("[data-hmz=options]")).to_have_class(re.compile("stale"))
        held[0].continue_()
        expect(page.locator(".greeting-about [role=status]")).to_have_count(0)
        expect(page.locator("[data-hmz=options]")).not_to_have_class(
            re.compile("stale")
        )


def test_the_flow_and_its_environment_are_profiled_apart(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new?flow=chat")
        page.get_by_role("button", name="Options").click()
        flow = page.get_by_label("Profile flow")
        environment = page.get_by_label("Profile environment")
        expect(flow).not_to_be_checked()
        expect(environment).not_to_be_checked()
        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_value("claude-haiku-4-5")
        flow.check()
        page.locator("[data-hmz=options]").get_by_role("button", name="Save").click()
        expect(
            page.locator("[data-hmz=options]").get_by_role("button", name="Saved")
        ).to_be_visible()
        page.reload()
        go(page, "/new?flow=chat")
        page.get_by_role("button", name="Options").click()
        expect(flow).to_be_checked()
        expect(environment).not_to_be_checked()
        environment.check()

        with page.expect_request(
            lambda asked: asked.url.endswith("/api/held/start")
        ) as started:
            page.locator("[data-hmz=composer-text]").fill("profile me")
            page.locator("[data-hmz=composer-text]").press("Enter")
        said = json.loads(started.value.post_data or "{}")
        assert (said["profile_flow"], said["profile_environment"]) == (True, True)
        page.wait_for_url(re.compile(r".*#/epics/[^/]+/sessions/[^/]+%2F1$"))


@pytest.mark.usefixtures("talking")
def test_an_epic_is_read_by_its_agents_logs_and_its_agents_as_a_list(
    engine: str,
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_talk(page, "log me")

        inspector = page.locator("[data-hmz=inspector]")
        expect(inspector.locator("[data-hmz=spending]")).to_contain_text(
            "claude-haiku-4-5"
        )
        expect(inspector.locator("[data-hmz=frontends]")).to_contain_text("this page")

        # No log of every session, and no Exomyth, under the epic in the sidebar: Exomyth is
        # opened from the epic's menu or its bar, and a log is one agent's.
        side = page.locator("[data-hmz=sidebar]")
        expect(side.locator("[data-hmz=agent]").first).to_be_visible()
        expect(side.locator("[data-hmz=log], [data-hmz=exomyth-link]")).to_have_count(0)
        page.locator("[data-hmz=bar] .bar-title").click(button="right")
        menu = page.locator(".popover.context")
        expect(menu.get_by_role("menuitem", name="Exomyth")).to_be_visible()
        expect(menu.get_by_role("menuitem", name="Open log")).to_have_count(0)
        page.keyboard.press("Escape")
        # Where that log was, the epic's graph is.
        found = re.search(r"#/epics/([^/]+)", page.url)
        assert found is not None
        name = found[1]
        go(page, f"/epics/{name}/logs")
        page.wait_for_url(re.compile(rf"#/epics/{name}$"))
        expect(page.locator("[data-hmz=thread]")).to_have_count(0)
        expect(page.locator("[data-hmz=bar] .crumbs")).to_have_count(0)

        page.locator(".shape-switch").get_by_role("button", name="List").click()
        listed = page.locator("[data-hmz=agent-list] [data-agent]").filter(
            has_text="assistant"
        )
        expect(listed).to_contain_text(re.compile(r"\w+/1"))
        listed.get_by_role("link", name="≡ log").click()
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("did: log me")
        expect(page.locator("[data-hmz=bar] .crumbs")).to_contain_text("log")
        page.locator("[data-hmz=bar] .crumbs a").click()
        page.locator(".shape-switch").get_by_role("button", name="Graph").click()
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()


def test_an_ended_epic_is_exported_and_its_address_copied(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "keep me")
        stop(page)

        with page.expect_download() as saving:
            page.get_by_role("link", name="Export").click()
        saved = saving.value
        assert saved.suggested_filename.endswith(".hmzepic")
        assert Path(saved.path()).read_bytes()[:2] == b"\x1f\x8b"

        # WebKit lets a click write unasked, and knows no permission to write by.
        writes = ["clipboard-write"] if engine == "chromium" else []
        page.context.grant_permissions(["clipboard-read", *writes])
        page.get_by_role("button", name="Copy link").click()
        expect(page.get_by_role("button", name="Copied")).to_be_visible()
        assert page.evaluate("navigator.clipboard.readText()") == page.url


def test_a_backup_target_is_added_picked_at_a_start_and_an_epic_uploaded_to_it(
    project: Path, engine: str
) -> None:
    import subprocess

    bare = project.parent / "epics.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/backup")
        writing = page.locator("[data-hmz=write-backup]")
        writing.get_by_label("Name").fill("t")
        writing.get_by_label("Repository").fill(str(bare))
        writing.get_by_role("button", name="Save").click()
        listed = page.locator("[data-hmz=backup-target][data-name=t]")
        expect(listed).to_contain_text("Manual")
        # Ticked, it is written down before a new epic reads it.
        with page.expect_response(
            lambda answer: (
                answer.url.endswith("/api/settings") and answer.request.method == "POST"
            )
        ) as saved:
            listed.locator("[data-hmz=backup-default]").check()
        assert saved.value.ok
        expect(listed.locator("[data-hmz=backup-default]")).to_be_checked()
        page.keyboard.press("Escape")

        go(page, "/new?flow=chat")
        page.get_by_role("button", name="Options").click()
        expect(page.locator("[data-hmz=backup] input[value=t]")).to_be_checked()
        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_value("claude-haiku-4-5")
        page.locator("[data-hmz=composer-text]").fill("back me up")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(re.compile(r".*#/epics/[^/]+/sessions/[^/]+%2F1$"))
        stop(page)

        page.locator("[data-hmz=bar] .bar-title").click(button="right")
        page.get_by_role("menuitem", name="Upload").click()
        expect(page.locator(".toast")).to_have_text("Uploading to t")
        expect(page.locator("[data-hmz=upload]")).to_have_attribute(
            "title", re.compile(r"^t: uploaded")
        )
        log = subprocess.run(
            ["git", "--git-dir", str(bare), "log", "--format=%s", "main"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert re.fullmatch(r"Back up epic \S+ \(manual\)\n", log.stdout)


def test_an_epic_backed_up_elsewhere_is_downloaded_and_opened(
    project: Path, engine: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = backed_up_elsewhere(tmp_path, monkeypatch)
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/backup")
        page.locator("[data-hmz=download]").click()

        stored = page.locator(f"[data-hmz=stored-epic][data-epic='{name}']")
        expect(stored).to_contain_text("hi")
        # The one target there is is the only one to pick.
        expect(page.locator("[data-hmz=download-target]")).to_be_hidden()
        stored.get_by_role("button", name="Download").click()

        page.wait_for_url(re.compile(rf".*#/epics/{re.escape(name)}"))
        expect(page.locator("[data-hmz=bar] .badge")).to_have_text(re.compile("done"))
        expect(page.locator("[data-hmz=epic]")).to_have_count(1)

        go(page, "/download")
        expect(stored).to_contain_text("Here")
        expect(stored.get_by_role("link", name="Open")).to_be_visible()


@pytest.mark.parametrize(("width", "dark"), [(1280, False), (390, True)])
def test_the_panel_says_every_figure_in_words_and_within_its_edges(
    project: Path, engine: str, width: int, dark: bool
) -> None:
    with served() as site, opened(site, engine=engine, width=width, dark=dark) as page:
        _start_chat(page, "fit me")
        expect(page.locator("[data-hmz=thread]")).to_contain_text("did: fit me")
        if width < 860:
            page.locator("[data-hmz=bar] .panel-toggle").click()
        inspector = page.locator("[data-hmz=inspector]")
        expect(inspector.locator("[data-hmz=environments]")).to_contain_text(
            re.compile(r"\w+/1 workspace · local")
        )
        expect(inspector.locator("[data-hmz=spending]")).to_contain_text("cache write")
        assert not re.search(
            r"\[object |\bundefined\b|\bNaN\b|\bnull\b", inspector.inner_text()
        )
        # Its last column inside the panel, as drawn or once scrolled to.
        outside = page.evaluate(
            """() => {
              const wrap = document.querySelector('[data-hmz=spending]').parentElement
              wrap.scrollLeft = wrap.scrollWidth
              const last = wrap.querySelector('th:last-child').getBoundingClientRect()
              const panel = document.querySelector('[data-hmz=inspector]').getBoundingClientRect()
              return last.right - Math.min(wrap.getBoundingClientRect().right, panel.right)
            }"""
        )
        assert outside <= 1


def _asks_of(page: Page, session: str) -> None:
    """Picks a conversation to ask from the Ask menu: its agent, then the conversation."""
    page.locator("[data-hmz=btw-to]").click()
    page.locator(".ask-list .choice-sub > [role=menuitem]").first.click()
    page.locator("[data-hmz=btw-agent] [role=menuitem]", has_text=session).first.click()
    expect(page.locator("[data-hmz=btw-to]")).to_contain_text(session)


def test_asides_each_ask_one_picked_at_their_start_and_say_while_they_answer(
    project: Path, engine: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.runtime.watching.btw import Btw, FlowSnapshot

    opens, asks = Btw.__init__, Btw.ask
    #: What each side conversation tells whoever opened it of whom it asks, as it asks.
    told: dict[int, Any] = {}

    def opening(self: Btw, target: str, **given: Any) -> None:
        told[id(self)] = given.get("asking")
        opens(self, target, **given)

    def slowly(self: Btw, question: str, snapshot: FlowSnapshot) -> str:
        # Long enough to be seen answering, saying whom it asks on the way.
        if "slowly" in question:
            told[id(self)]("someone/1", "are you there")
            time.sleep(3)
        return asks(self, question, snapshot)

    monkeypatch.setattr(Btw, "__init__", opening)
    monkeypatch.setattr(Btw, "ask", slowly)
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "remember papaya")
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("did: remember papaya")
        page.get_by_role("tab", name="Aside").click()
        aside = page.locator("[data-hmz=btw]")
        ask = page.locator("[data-hmz=btw-to]")

        # Of The Epic until a conversation is picked, picked above the box rather than in it,
        # and no agent to pick here at all.
        expect(ask).to_contain_text("The Epic")
        expect(aside.locator("[data-hmz=btw-to]")).to_have_count(0)
        expect(
            page.locator("[data-hmz=btw-whom], [data-hmz=btw-picker]")
        ).to_have_count(0)
        ask.click()
        epic = page.locator("[data-hmz=btw-the-epic]")
        expect(epic).to_contain_text("set its agent in Settings")
        # Laid out as the epic is: its agent, with the role it fills, opening its sessions.
        agent = page.locator(
            ".choice-sub", has=page.get_by_role("menuitem").filter(has_text="assistant")
        )
        expect(agent).to_have_count(1)
        agent.get_by_role("menuitem").first.click()
        expect(page.locator("[data-hmz=btw-agent] [role=menuitem]")).to_have_count(1)
        # Narrowed by typing: what matches, wherever it is in the tree.
        page.locator("[data-hmz=btw-find]").fill("/1")
        expect(page.locator(".ask-list [role=menuitem]")).to_have_count(1)
        page.locator("[data-hmz=btw-find]").fill("nobody like it")
        expect(page.locator(".ask-list")).to_contain_text("Nobody matches.")
        page.keyboard.press("Escape")

        # Asked of The Epic with nobody named to answer it: the settings are where to say who.
        aside.locator("textarea").fill("what is it doing")
        aside.locator("textarea").press("Enter")
        expect(aside).to_contain_text("settings")
        # Refused before it opened: whom it asks is still to pick.
        expect(ask).to_be_visible()
        named = page.evaluate(
            """async () => (await fetch('/api/settings', {method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({btw: 'claude/claude-haiku-4-5'})})).status"""
        )
        assert named == 200
        aside.locator("textarea").fill("what now")
        aside.locator("textarea").press("Enter")
        log = page.locator("[data-hmz=btw-log]")
        expect(log).to_contain_text("btw · The Epic")
        expect(log.locator(".said.btw")).to_have_count(1)
        # Whom it asks was fixed by its first answer: nothing to pick for it any more.
        expect(ask).to_be_hidden()

        # A second aside, of a conversation, picked at its start.
        page.locator("[data-hmz=btw-new]").click()
        expect(ask).to_be_visible()
        _asks_of(page, "/1")
        aside.locator("textarea").fill("and you, slowly")
        aside.locator("textarea").press("Enter")
        # Answering, it says so, and whom it asks on the way, as it asks.
        working = page.locator("[data-hmz=btw-working]")
        expect(working).to_contain_text("is thinking")
        expect(log).to_contain_text("asking someone/1: are you there")
        expect(aside.locator("button.send")).to_be_disabled()
        expect(page.locator("[data-hmz=btw-tab].busy")).to_have_count(1)
        expect(log.locator(".said.btw")).to_have_count(1)
        expect(working).to_have_count(0)
        expect(ask).to_be_hidden()
        tabs = page.locator("[data-hmz=btw-tab]")
        expect(tabs).to_have_count(2)
        expect(tabs.nth(1)).to_contain_text("/1")

        # Opened again, both are read back, each with what was said in it.
        page.reload()
        page.get_by_role("tab", name="Aside").click()
        expect(tabs).to_have_count(2)
        expect(log).to_contain_text("and you, slowly")
        tabs.first.click()
        expect(log).to_contain_text("what now")
        # Closed, one goes, and the other stays.
        page.locator("[data-hmz=btw-close]").click()
        expect(tabs).to_have_count(1)
        expect(log).to_contain_text("and you, slowly")
        stop(page)


def test_what_is_pressed_on_an_epic_says_it_is_busy_until_its_reply(
    project: Path, engine: str, talking: None
) -> None:
    #: Each request held back until let through, so what is pressed is seen waiting on it.
    waiting: list[Route] = []

    def held(route: Route) -> None:
        waiting.append(route)

    def holding(path: str) -> None:
        page.route(f"**{path}", held, times=1)

    def through() -> None:
        deadline = time.monotonic() + 10
        while not waiting:
            assert time.monotonic() < deadline, "nothing was sent"
            page.wait_for_timeout(100)
        waiting.pop().continue_()

    with served() as site, opened(site, engine=engine) as page:
        _start_talk(page, "busy me")

        # The question's typed answer.
        card = page.locator("[data-hmz=question]")
        expect(card).to_be_visible()
        holding("/api/held/answer")
        card.get_by_label("Answer").fill("go on")
        card.get_by_label("Answer").press("Enter")
        answering = card.get_by_role("button", name="Answering…")
        expect(answering).to_be_disabled()
        through()
        expect(answering).to_have_count(0)

        # An aside's Close.
        named = page.evaluate(
            """async () => (await fetch('/api/settings', {method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({btw: 'claude/claude-haiku-4-5'})})).status"""
        )
        assert named == 200
        page.get_by_role("tab", name="Aside").click()
        aside = page.locator("[data-hmz=btw]")
        aside.locator("textarea").fill("what now")
        aside.locator("textarea").press("Enter")
        expect(page.locator("[data-hmz=btw-log] .said.btw")).to_have_count(1)
        holding("/api/btw/leave")
        page.locator("[data-hmz=btw-close]").click()
        closing = page.get_by_role("button", name="Closing…")
        expect(closing).to_be_disabled()
        through()
        expect(page.locator("[data-hmz=btw-tab]")).to_have_count(1)
        expect(closing).to_have_count(0)

        # Upload, from the bar: the button says it is busy, and nothing else says so too.
        holding("/api/runs/*/backup")
        page.locator("[data-hmz=upload]").click()
        expect(page.locator("[data-hmz=upload]")).to_have_attribute("aria-busy", "true")
        expect(page.locator("[data-hmz=upload]")).to_be_disabled()
        expect(page.locator("[data-hmz=working]")).to_have_count(0)
        through()
        expect(page.locator(".toast")).to_be_visible()
        expect(page.locator("[data-hmz=upload]")).not_to_have_attribute(
            "aria-busy", "true"
        )

        # Stop, which stays stopping until the epic says it is.
        holding("/api/held/stop")
        page.get_by_role("button", name="Stop", exact=True).click()
        page.get_by_role("button", name="Stop", exact=True).click()
        stopping = page.get_by_role("button", name="Stopping…")
        expect(stopping).to_be_disabled()
        # The bar drawn again, for another view of the epic, asks no second time.
        page.locator("[data-hmz=graph-session]").first.click()
        expect(page).to_have_url(re.compile(r".*/sessions/[^/]+$"))
        expect(stopping).to_be_disabled()
        expect(page.get_by_role("button", name="Stop", exact=True)).to_have_count(0)
        through()
        expect(page.get_by_role("button", name="Stop", exact=True)).to_have_count(0)
        expect(page.locator("[data-hmz=bar] .badge")).to_have_text(
            re.compile("stopping|stopped")
        )
        stop(page)


def test_a_composer_built_before_it_is_shown_is_a_line_tall_once_shown(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "remember papaya")
        expect(page.locator("[data-hmz=thread]")).to_contain_text(
            "did: remember papaya"
        )
        page.get_by_role("tab", name="Aside").click()
        # Nothing typed yet: typing fires `input`, which would size it either way.
        text = page.locator("[data-hmz=btw] textarea")
        expect(text).to_be_visible()
        line = text.evaluate("t => parseFloat(getComputedStyle(t).lineHeight)")
        box = text.bounding_box()
        ask = page.locator(".ask-to").bounding_box()
        assert box is not None
        assert ask is not None
        assert box["height"] >= line
        # Whom it asks is picked above the box, outside it, and covers none of it.
        expect(page.locator("[data-hmz=btw] .ask-to")).to_have_count(0)
        assert ask["y"] + ask["height"] <= box["y"]
        stop(page)


def test_an_earlier_epic_is_read_out_of_its_logs_and_asked_beside(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "remember papaya")
        expect(page.locator("[data-hmz=thread]")).to_contain_text(
            "did: remember papaya"
        )
        # A new chat leaves the last going, on a host of its own.
        _start_chat(page, "and then this")
        expect(page.locator("[data-hmz=thread]")).to_contain_text("did: and then this")
        stop(page)

        page.locator("[data-hmz=epic]", has_text="remember papaya").click()
        page.wait_for_url(re.compile(r".*#/epics/[^/]+/sessions/[^/]+%2F1$"))
        expect(page.locator("[data-hmz=thread]")).to_contain_text(
            "did: remember papaya"
        )

        page.get_by_role("tab", name="Aside").click()
        aside = page.locator("[data-hmz=btw]")
        _asks_of(page, "/1")
        aside.locator("textarea").fill("what was the word")
        aside.locator("textarea").press("Enter")
        expect(page.locator("[data-hmz=btw-log]")).to_contain_text(
            "read-only side copy of the flow session"
        )


@pytest.mark.parametrize("gatewayable", [True, False])
def test_the_ways_through_the_gateway_are_one_group_or_the_line_that_adds_them(
    project: Path, monkeypatch: pytest.MonkeyPatch, engine: str, *, gatewayable: bool
) -> None:
    from hmz.coganchor import backends, gateway

    claude = backends.named("claude")
    assert claude is not None
    monkeypatch.setattr(gateway, "gatewayable", lambda: gatewayable)
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/accounts")
        page.locator("#account-cli").select_option("claude")
        group = page.locator("#account-way optgroup[label=LiteLLM]")
        wants = page.locator("[data-hmz=gateway-wants]")
        if gatewayable:
            expect(group.locator("option")).to_have_count(len(backends.routed(claude)))
            expect(
                page.locator("#account-way > option[value^=litellm-]")
            ).to_have_count(0)
            expect(wants).to_be_hidden()
        else:
            expect(group).to_have_attribute("disabled", "")
            expect(wants).to_contain_text("litellm is not installed; run: uv pip")


#: Drags a file over the page, a step at a time, as one is dragged out of a folder: the file is
#: made where it is named, and kept for the steps after.
_DRAG = """([kinds, name, bytes]) => {
  if (name) {
    window.moved = new DataTransfer()
    window.moved.items.add(new File([new Uint8Array(bytes)], name))
  }
  const page = document.querySelector('[data-hmz=page]')
  for (const kind of kinds) {
    const how = {dataTransfer: window.moved, bubbles: true, cancelable: true}
    page.dispatchEvent(new DragEvent(kind, how))
  }
}"""


def test_an_exported_epic_is_imported_by_picking_dropping_or_its_path(
    project: Path, tmp_path: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "take me home")
        stop(page)
        found = re.search(r"#/epics/([^/]+)", page.url)
        assert found is not None
        name = found[1]
        with page.expect_download() as saving:
            page.get_by_role("link", name="Export").click()
        archive = tmp_path / saving.value.suggested_filename
        saving.value.save_as(archive)
        at = page.evaluate(
            "async (name) => (await (await fetch(`/api/runs/${name}`)).json()).at",
            name,
        )
        opened_on = re.compile(rf".*#/epics/{re.escape(name)}$")
        # By its path, an epic opens on its Exomyth, as the desktop app opens a file.
        on_exomyth = re.compile(rf".*#/epics/{re.escape(name)}/exomyth$")
        listed = page.locator(f"[data-hmz=sidebar] .side-item[data-epic='{name}']")

        def gone() -> None:
            go(page, "/new")
            shutil.rmtree(at)

        # Picked, from Search epics.
        gone()
        page.keyboard.press("Control+k")
        with page.expect_file_chooser() as choosing:
            page.locator("[data-hmz=import]").click()
        choosing.value.set_files(archive)
        page.wait_for_url(opened_on)
        expect(listed).to_have_count(1)

        # Picked again, from between the epics: it is here already, and is opened from there.
        go(page, "/new")
        page.evaluate(
            """() => document.querySelector('[data-hmz=epics]').dispatchEvent(
                new MouseEvent('contextmenu', {bubbles: true, cancelable: true}))"""
        )
        with page.expect_file_chooser() as choosing:
            page.get_by_role("menuitem", name="Import").click()
        choosing.value.set_files(archive)
        notice = page.locator("[data-hmz=import-notice]")
        expect(notice).to_contain_text("is already here")
        notice.get_by_role("link", name="Open").click()
        page.wait_for_url(opened_on)
        expect(notice).to_have_count(0)

        # Dropped on the window.
        gone()
        page.evaluate(
            _DRAG, [["dragenter", "dragover"], archive.name, list(archive.read_bytes())]
        )
        expect(page.locator("body")).to_have_class(re.compile("dropping"))
        page.evaluate(_DRAG, [["drop"], "", []])
        page.wait_for_url(opened_on)
        expect(page.locator("body")).not_to_have_class(re.compile("dropping"))
        expect(listed).to_have_count(1)

        # By its path: asked first, in a browser any page could have linked here from.
        gone()
        go(page, f"/epics/import?path={urllib.parse.quote(str(archive))}")
        importing = page.locator("[data-hmz=importing]")
        expect(importing).to_contain_text(str(archive))
        importing.get_by_role("button", name="Import").click()
        page.wait_for_url(on_exomyth)

        junk = tmp_path / "junk.hmzepic"
        junk.write_bytes(b"not a bundle")
        go(page, f"/epics/import?path={urllib.parse.quote(str(junk))}")
        importing.get_by_role("button", name="Import").click()
        expect(importing.locator(".error")).to_contain_text(
            "junk.hmzepic is not a bundle"
        )

        # Somebody else's, opened in the desktop app, which imports it as it is opened and
        # says why it is not picked up here.
        gone()
        (tmp_path / "theirs").mkdir()
        theirs = elsewhere(archive, "/nowhere/at/all", tmp_path / "theirs")
        browser = page.context.browser
        assert browser is not None
        app = browser.new_context(user_agent=_APP).new_page()
        # As the app opens it: at the address with the key, whose hash outlives signing in.
        app.goto(f"{site.address}#/epics/import?path={urllib.parse.quote(str(theirs))}")
        try:
            app.wait_for_url(on_exomyth)
        except PlaywrightError as why:
            said = app.locator("[data-hmz=page]").inner_text()
            raise AssertionError(f"{app.url} says {said!r}") from why
        go(app, f"/epics/{name}")
        expect(app.locator("[data-hmz=foreign]")).to_contain_text(
            "not resumable here: the workspace it ran in, /nowhere/at/all, is not on"
        )
        expect(app.get_by_role("link", name="Resume")).to_have_count(0)


def _held(page: Page) -> dict[str, dict[str, object]]:
    """Each epic listed, by its task: whether a host holds it, how it stands, and which."""
    return page.evaluate(
        """async () => Object.fromEntries((await (await fetch('/api/runs')).json()).runs
          .map((one) => [one.task, {held: one.held, how: one.how, slot: one.slot,
            name: one.name}]))"""
    )


@pytest.mark.usefixtures("talking")
def test_chats_go_beside_each_other_and_a_flow_and_one_folded_is_carried_on(
    project: Path, engine: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Nobody reading a chat between turns lets it go, and it folds, in a moment.
    monkeypatch.setattr(hosting, "FOLD", 0.5)
    monkeypatch.setattr(hmz.web.places, "_IDLE", 0.5)
    monkeypatch.setattr(hmz.web.places, "_LOOKING", 0.2)
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "remember teal")
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("did: remember teal")
        first = page.url
        # A flow, and a second chat: none of them ends another.
        _start_talk(page, "a flow beside")
        _start_chat(page, "another chat")
        expect(thread).to_contain_text("did: another chat")
        page.wait_for_function(
            """async () => (await (await fetch('/api/runs')).json()).runs
              .filter((one) => one.held).length === 3""",
            polling=200,
        )
        held = _held(page)
        assert len({one["slot"] for one in held.values()}) == 3
        rows = page.locator("[data-hmz=sidebar] [data-hmz=epic]")
        expect(rows).to_have_count(3)
        # Kept to be looked at; WebKit's screenshot styles the page, which its policy refuses.
        if engine == "chromium":
            page.locator("[data-hmz=sidebar]").screenshot(
                path=str(tmp_path / "two-chats.png")
            )

        # The first keeps its conversation.
        page.goto(first)
        expect(thread).to_contain_text("did: remember teal")
        expect(thread).not_to_contain_text("another chat")

        # Looked away from, between turns, it folds: done, and held no more.
        page.locator("[data-hmz=epic]", has_text="a flow beside").click()
        page.wait_for_function(
            """async () => (await (await fetch('/api/runs')).json()).runs
              .some((one) => one.task === 'remember teal' && !one.held)""",
            polling=200,
            timeout=30000,
        )
        name = _held(page)["remember teal"]["name"]

        # Said something, it is carried on in the same epic, what was said before above.
        page.goto(first)
        expect(thread).to_contain_text("did: remember teal")
        say = page.locator("[data-hmz=say] textarea")
        say.fill("what was it")
        say.press("Enter")
        expect(thread).to_contain_text("did: what was it")
        expect(thread).to_contain_text("did: remember teal")
        assert f"/epics/{name}/" in page.url
        held = _held(page)
        assert len(held) == 3
        assert held["remember teal"]["name"] == name
        page.wait_for_function(
            """(name) => fetch('/api/runs').then((one) => one.json()).then((said) =>
              said.runs.some((one) => one.name === name && one.held))""",
            arg=name,
            polling=200,
        )
        stop(page)

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
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect

import hmz.coganchor.models
from tests.integration.doubles_core import install
from tests.integration.doubles_web import backed_up_elsewhere, elsewhere, served
from tests.system.web.doubles_browser import ENGINES, go, opened

if TYPE_CHECKING:
    from playwright.sync_api import FloatRect, Locator, Page

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


def test_the_graph_is_dragged_anywhere_zoomed_by_the_wheel_and_recentred(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "move me")
        expect(page.locator("[data-hmz=thread]")).to_contain_text("did: move me")
        page.locator("[data-hmz=bar] .crumbs a").click()
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


def test_an_epic_started_from_the_page_is_drawn_answered_read_and_stopped(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "hello there")

        # Read as a conversation: what you said, what it said back, and a follow-up typed
        # under it, never a question waiting for you.
        thread = page.locator("[data-hmz=thread]")
        expect(thread.locator(".said.you .body")).to_have_text(["hello there"])
        expect(thread).to_contain_text("did: hello there")
        expect(page.locator("[data-hmz=epic] .pill-live")).to_be_visible()
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

        page.locator("[data-hmz=bar] .crumbs a").click()
        agent = page.locator("[data-hmz=graph-agent]").filter(has_text="assistant")
        expect(agent).to_be_visible()
        expect(agent.locator("[data-hmz=graph-session] .unread")).to_have_count(0)
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()
        expect(page.locator("[data-hmz=bar] .badge")).to_have_text(
            re.compile("stopped")
        )
        expect(page.locator("[data-hmz=epic] .side-mark").first).to_have_text("■")


def test_an_epic_is_found_by_its_task(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "find me later")
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()

        page.keyboard.press("Control+k")
        search = page.get_by_role("searchbox", name="Find")
        expect(page.locator("[data-hmz=found] .result")).to_have_count(1)
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
        go(page, "/live")
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
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()


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


def test_an_epic_is_read_as_its_log_and_its_agents_as_a_list(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "log me")
        expect(page.locator("[data-hmz=thread]")).to_contain_text("did: log me")

        inspector = page.locator("[data-hmz=inspector]")
        expect(inspector.locator("[data-hmz=spending]")).to_contain_text(
            "claude-haiku-4-5"
        )
        expect(inspector.locator("[data-hmz=frontends]")).to_contain_text("this page")

        page.locator("[data-hmz=sidebar] [data-hmz=log]").click()
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("did: log me")
        # What a chat asks next is the reply said back, which is not said twice.
        expect(thread).not_to_contain_text("human asks")
        expect(page.locator("[data-hmz=bar] .crumbs")).to_contain_text("Log")

        page.locator("[data-hmz=bar] .crumbs a").click()
        page.locator(".shape-switch").get_by_role("button", name="List").click()
        listed = page.locator("[data-hmz=agent-list] [data-agent]").filter(
            has_text="assistant"
        )
        expect(listed).to_contain_text(re.compile(r"\w+/1"))
        listed.get_by_role("link", name="≡ log").click()
        expect(page.locator("[data-hmz=thread]")).to_contain_text("did: log me")
        page.locator("[data-hmz=bar] .crumbs a").click()
        page.locator(".shape-switch").get_by_role("button", name="Graph").click()
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()


def test_an_ended_epic_is_exported_and_its_address_copied(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "keep me")
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()
        expect(page.locator("[data-hmz=bar] .badge")).to_have_text(
            re.compile("stopped")
        )

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
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()
        expect(page.locator("[data-hmz=bar] .badge")).to_have_text(
            re.compile("stopped")
        )

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


def test_an_earlier_epic_is_read_out_of_its_logs_and_asked_beside(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "remember papaya")
        expect(page.locator("[data-hmz=thread]")).to_contain_text(
            "did: remember papaya"
        )
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()
        _start_chat(page, "and then this")
        expect(page.locator("[data-hmz=thread]")).to_contain_text("did: and then this")
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()

        page.locator("[data-hmz=epic]", has_text="remember papaya").click()
        page.locator(".graph-note").get_by_role("button", name="Read turns").click()
        agent = page.locator("[data-hmz=graph-agent]").filter(has_text="assistant")
        expect(agent.locator(".capsule")).to_have_count(1)

        agent.locator("[data-hmz=graph-session]").click()
        expect(page.locator("[data-hmz=thread]")).to_contain_text(
            "did: remember papaya"
        )

        page.get_by_role("tab", name="Aside").click()
        aside = page.locator("[data-hmz=btw]")
        aside.get_by_role("combobox").select_option(index=1)
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
        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()
        expect(page.locator("[data-hmz=bar] .badge")).to_have_text(
            re.compile("stopped")
        )
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

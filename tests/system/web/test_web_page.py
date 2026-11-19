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
from hmz.runtime.doing import hosting
from tests.integration.doubles_core import AGENT, hmz_exec, install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import (
    ENGINES,
    Wire,
    backed_up_elsewhere,
    elsewhere,
    go,
    opened,
    stop,
)

if TYPE_CHECKING:
    from playwright.sync_api import FloatRect, Locator, Page

#: Every settings page, by the word its address ends in.
_PAGES = (
    "general",
    "themes",
    "accounts",
    "nous",
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

#: What the Windows app's window says it is: WebView2, and the app.
_WINDOWS_APP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
    " humanize-desktop/0.0.0"
)

#: Local is a daemon of this process: what a test patches of a host, its hosts take.
pytestmark = [
    pytest.mark.parametrize("engine", ENGINES),
    pytest.mark.usefixtures("daemon"),
]


def _call(page: Page, method: str, params: dict[str, Any] | None = None) -> Any:
    """Calls one method of the daemon shown, as the page's own script does."""
    return page.evaluate(
        """async ([method, params]) => (await import('/api.js')).call(method, params)""",
        [method, params or {}],
    )


def _starts(page: Page, flow: str, task: str) -> dict[str, Any]:
    """Starts an epic where `hmz web` started, as a new epic does, and answers where it went."""
    return page.evaluate(
        """async ([flow, task]) => {
          const { started } = await import('/api.js')
          const { ask } = await import('/held.js')
          return ask(await started(), 'start', {flow, task,
            budget: {cost: 5, duration: 600, output_tokens: 100000},
            agents: {assistant: 'claude/claude-haiku-4-5'}})
        }""",
        [flow, task],
    )


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, asked what it runs, and a project to serve."""
    project = install(tmp_path, monkeypatch)
    # The home it gives the CLI is this machine's home, which the daemon's own settings are of.
    (tmp_path / "home").mkdir(exist_ok=True)
    return project


def _start_chat(page: Page, task: str) -> None:
    """Starts chat from a new epic's box, on whichever model its agent is offered first.

    A chat is opened on its conversation, as a chat app opens on one, not on its graph.
    """
    go(page, "/new/chat")
    expect(page.locator("div[data-hmz=new-chat]")).to_be_visible()
    expect(
        page.locator("[data-role=assistant] [data-hmz=pick-model]")
    ).to_have_attribute("data-value", "claude-haiku-4-5")
    page.locator("[data-hmz=composer-text]").fill(task)
    page.locator("[data-hmz=composer-text]").press("Enter")
    page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))


def _details(page: Page) -> None:
    """Opens the pane of what a chat is, beside it, from its bar; shut until asked for."""
    button = page.locator("[data-hmz=bar] [data-hmz=pane-details]")
    if button.get_attribute("aria-pressed") != "true":
        button.click()
    expect(page.locator("[data-hmz=inspector]")).to_be_visible()


def _side_questions(page: Page) -> None:
    """Opens a chat's side questions beside it, from its bar's View options."""
    page.locator("[data-hmz=bar] [data-hmz=chat-view]").click()
    page.get_by_role("menu", name="View options").get_by_role(
        "menuitem", name="Side questions"
    ).click()
    expect(page.locator("[data-hmz=inspector] [data-hmz=pane-title]")).to_have_text(
        "Side questions"
    )


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


#: A new epic of the project's own `talk`: a chat is of no flow, and a flow's epic has options.
_NEW = "/new?flow=%40local%2Ftalk"


def _options(page: Page) -> None:
    """Opens a new epic's options and gives it a budget, without which no flow starts."""
    page.get_by_role("button", name="Options").click()
    page.get_by_label("Most it may cost, in dollars").fill("5")


#: The address of a flow's epic, as it opens: on its graph.
_EPIC = re.compile(r".*#/epics/[^/?]+$")


@pytest.fixture
def talking(project: Path) -> None:
    """The project's own `talk`, offered from the start."""
    flows = project / ".hmz" / "flows" / "talk"
    flows.mkdir(parents=True)
    (flows / "__init__.py").write_text(_TALK)


def _start_talk(page: Page, task: str) -> None:
    """Starts the project's own `talk` from the API, as a page would, and opens its graph."""
    started = _starts(page, "@local/talk", task)
    go(page, f"/live?{urllib.parse.urlencode({'workspace': started['workspace']})}")
    page.wait_for_url(re.compile(r".*#/epics/[^/]+$"))
    expect(page.locator("[data-hmz=graph-session]").first).to_be_visible()


@pytest.mark.usefixtures("talking")
def test_a_new_epic_offers_each_role_the_models_its_cli_runs(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, _NEW)
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


@pytest.mark.usefixtures("talking")
def test_an_epic_asking_a_person_calls_until_one_looks(engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        # Not looked at, as a page behind another window is not.
        page.evaluate("document.hasFocus = () => false")
        _start_talk(page, "ask me")
        badge = page.locator("[data-hmz=bar] .badge")
        glyph = badge.locator(".glyph")
        # Going on nobody's word, it is steady: only what calls for a person moves.
        expect(badge.locator(".glyph")).to_have_text("●")
        expect(badge).to_have_text(re.compile("running|asking"))
        expect(page.locator("[data-hmz=waiting]")).to_be_visible()
        expect(badge).to_have_text(re.compile("asking"))
        expect(badge).to_have_class(re.compile("tone-asking"))
        expect(glyph).to_have_css("animation-name", "pulse")

        # Looked at, it waits, steady.
        page.evaluate(
            "delete document.hasFocus, window.dispatchEvent(new Event('focus'))"
        )
        expect(badge).to_have_text(re.compile("waiting"))
        expect(glyph).to_have_css("animation-name", "none")
        expect(
            page.locator("[data-hmz=epic] [data-hmz=epic-state]").first
        ).to_have_text("Waiting")
        assert "hmz-seen" in page.evaluate("Object.keys(localStorage)")

        page.get_by_role("button", name="Stop").click()
        page.get_by_role("button", name="Stop").click()
        expect(badge).to_have_text(re.compile("stopped"))
        expect(badge).to_have_class(re.compile("tone-stopped"))


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


@pytest.mark.usefixtures("talking")
def test_a_model_no_cli_would_list_is_typed(
    monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:

    def refused(cli: str, provider: str = "", seconds: float = 0.0) -> tuple[()]:
        raise OSError(f"{cli} is not answering")

    monkeypatch.setattr(hmz.coganchor.models, "ask", refused)
    with served() as site, opened(site, engine=engine) as page:
        go(page, _NEW)
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


def _at(page: Page, selector: str) -> FloatRect:
    """Where an element is drawn, in CSS pixels."""
    box = page.locator(selector).bounding_box()
    assert box is not None, selector
    return box


#: A chat that waits on its person mid-turn, as `chat.list` lists it.
_WAITING: dict[str, Any] = {
    "id": "20261117T000000.000Z-c4a7e0",
    "title": "which colour is the button",
    "workspace": "/nowhere/fake-workspace",
    "workdir": "/nowhere/fake-workspace",
    "agent": "claude/claude-haiku-4-5",
    "model": "claude-haiku-4-5",
    "began": "2026-11-17T00:00:00.000Z",
    "updated": "2026-11-17T00:00:00.000Z",
    "state": "resting",
    "slot": "",
    "asking": ["1:q1"],
    "permission": "workspace-write",
    "archived": False,
    "spent": None,
}


@pytest.mark.parametrize("width", [1296, 390])
def test_a_new_chat_is_laid_out_as_a_chat_apps_new_session(
    project: Path, engine: str, width: int
) -> None:
    wire = Wire(
        faked={"chat.list": lambda _: {"result": {"chats": [_WAITING], "total": 1}}}
    )
    with (
        served() as site,
        opened(
            site, engine=engine, width=width, height=792, routed=wire.routes
        ) as page,
    ):
        go(page, "/new/chat")
        view = page.locator("[data-hmz=new-chat]")
        expect(view).to_be_visible()
        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_attribute("data-value", "claude-haiku-4-5")

        # Its bar: 44px, a plain heading at its left, no control of the form's own.
        bar = _at(page, "[data-hmz=bar]")
        assert bar["height"] == 44
        expect(view.locator("[data-hmz=bar] h1")).to_have_text("New chat")
        expect(view.locator("[data-hmz=bar] .bar-title button")).to_have_count(0)
        # No greeting, no mark, no box in the middle.
        expect(view.locator(".greeting, .home-mark")).to_have_count(0)

        # The box is docked at the foot, in the column a conversation is read in: inside
        # it only Add, what is typed and the button that sends, 28px high in one row.
        pane = _at(page, "[data-hmz=new-chat]")
        boxed = _at(page, "[data-hmz=start] .composer-box")
        under = _at(page, "[data-hmz=start] [data-hmz=composer-under]")
        expect(view.locator(".composer-box > *")).to_have_count(3)
        inside = [
            _at(page, f"[data-hmz=start] {one}")
            for one in ("[data-hmz=composer-add]", "textarea", ".send")
        ]
        assert [one["height"] for one in inside] == [28, 28, 28]
        assert [one["x"] for one in inside] == sorted(one["x"] for one in inside)
        assert boxed["width"] <= 780
        middle = boxed["x"] + boxed["width"] / 2
        assert abs(middle - (pane["x"] + pane["width"] / 2)) <= 1
        assert under["y"] >= boxed["y"] + boxed["height"]
        assert pane["y"] + pane["height"] - (under["y"] + under["height"]) == 8
        if width > 860:
            # A chat app's own numbers, in a window 792 high: the row inside the box at
            # 716 to 744, the chips under it at 760 to 784.
            assert (inside[0]["y"], inside[0]["height"]) == (716, 28)
            assert (under["y"], under["height"]) == (760, 24)

        # Under the box: where it runs at the left, how at the right, each 24px high.
        chips = view.locator(
            "[data-hmz=composer-under] button:visible, [data-hmz=composer-under] a"
        )
        assert chips.evaluate_all("all => all.map((one) => one.dataset.hmz)") == [
            "environment",
            "workspace-picker",
            "pick-model",
            "permission",
            "new-usage",
        ]
        for at in range(5):
            box = chips.nth(at).bounding_box()
            assert box
            assert box["height"] == 24
        # Set in from the box's edges, as a chat app's are: on a wide page the first
        # starts a hair right of the Add button, and the last ends as far from the edge.
        inset = 12 if width > 860 else 4
        assert _at(page, "[data-hmz=environment]")["x"] == boxed["x"] + inset
        if width > 860:
            assert _at(page, "[data-hmz=environment]")["x"] == inside[0]["x"] + 2
        # The row ends, as a chat app's does, with the ring that says what was used.
        last = _at(page, "[data-hmz=start] [data-hmz=new-usage]")
        assert last["width"] == 24
        assert (
            abs(last["x"] + last["width"] - (boxed["x"] + boxed["width"] - inset)) <= 1
        )
        expect(view.locator("[data-hmz=environment]")).to_have_text("Local")
        # Said, to whoever cannot see it, with what it picks.
        expect(view.locator("[data-hmz=environment]")).to_have_attribute(
            "aria-label", "Environment: Local"
        )
        expect(view.locator("[data-hmz=workspace-picker] b")).to_have_text(project.name)

        # Environment is the daemon the page shows, and offers the others.
        view.locator("[data-hmz=environment]").click()
        offered = page.get_by_role("menu", name="Environment")
        expect(offered.get_by_role("menuitem")).to_have_text(
            [re.compile("Local"), "New environment"]
        )
        expect(offered.locator("[data-daemon=local]")).to_have_class(
            re.compile("chosen")
        )
        # A menu of the desk is a chat app's: a choice of one line is a row of 28px.
        assert _at(page, "[role=menu] [data-daemon=local]")["height"] == 28
        page.keyboard.press("Escape")
        # The folder: the recent ones, then opening one, then none.
        view.locator("[data-hmz=workspace-picker]").click()
        folders = page.get_by_role("menu", name="Folders").get_by_role("menuitem")
        expect(folders.nth(-2)).to_contain_text("Open folder…")
        expect(folders.nth(-1)).to_contain_text("No folder")
        page.keyboard.press("Escape")

        # Before there is a chat, Add offers the one prefix the page completes by
        # itself: `@`, which completes the folder's files.
        (project / "notes.md").write_text("notes\n", encoding="utf-8")
        text = view.locator("[data-hmz=composer-text]")
        view.locator("[data-hmz=composer-add]").click()
        adding = page.get_by_role("menu", name="Add")
        expect(adding.get_by_role("menuitem")).to_have_text(["Add files"])
        assert _at(page, "[role=menu][aria-label=Add]")["width"] == 218
        adding.get_by_role("menuitem", name="Add files").click()
        expect(text).to_have_value("@")
        expect(page.locator("[data-hmz=completions]")).to_contain_text("@notes.md")
        text.fill("")

        # In the middle, the chats that wait on their person, as a chat app lists them:
        # the list alone, 320 wide at most, its rows of 32px set in 4px, each opening
        # its chat, each dismissed with a 28px button inside the row, at its right.
        steps = view.locator("[data-hmz=next-steps]")
        expect(steps).to_have_attribute("aria-label", "Next steps")
        expect(steps.locator("h2")).to_have_count(0)
        row = steps.locator("[data-hmz=next-step]")
        expect(row).to_have_count(1)
        expect(row).to_contain_text("which colour is the button")
        expect(row.locator(".next-state")).to_have_text("Asked a question")
        listed = _at(page, "[data-hmz=next-steps]")
        assert listed["width"] == min(320, pane["width"] - (40 if width > 860 else 28))
        assert abs(listed["x"] + listed["width"] / 2 - middle) <= 1
        lined = _at(page, "[data-hmz=next-step]")
        assert (lined["x"], lined["width"]) == (listed["x"] + 4, listed["width"] - 8)
        assert lined["height"] == 32
        dismiss = _at(page, "[data-hmz=next-dismiss]")
        assert (dismiss["width"], dismiss["height"]) == (28, 28)
        assert dismiss["x"] + dismiss["width"] == lined["x"] + lined["width"] - 4
        expect(row.locator("a")).to_have_attribute("href", f"#/chats/{_WAITING['id']}")
        # Dismissed, it is off the list in this browser, a reload later too.
        row.locator("[data-hmz=next-dismiss]").click()
        expect(steps).to_be_hidden()
        page.reload()
        expect(page.locator("[data-hmz=new-chat]")).to_be_visible()
        page.wait_for_timeout(500)
        expect(page.locator("[data-hmz=next-steps]")).to_be_hidden()
        # And once the chat has folded away, when its row lists nothing it asks: what
        # this browser holds it owing is what it was dismissed by.
        wire.faked["chat.list"] = lambda _: {
            "result": {"chats": [{**_WAITING, "asking": []}], "total": 1}
        }
        asked = len(wire.params("chat.list"))
        page.reload()
        expect(page.locator("[data-hmz=new-chat]")).to_be_visible()
        while len(wire.params("chat.list")) <= asked:
            page.wait_for_timeout(50)
        page.wait_for_timeout(500)
        expect(page.locator("[data-hmz=next-steps]")).to_be_hidden()
        # It still waits: forgotten as dismissed, it is listed again.
        page.evaluate("localStorage.removeItem('hmz-next-dismissed')")
        page.reload()
        expect(page.locator("[data-hmz=next-step]")).to_have_count(1)


def test_a_new_epic_stands_in_the_frame_of_a_new_chat(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine, width=1296, height=792) as page:
        go(page, "/new")
        view = page.locator("[data-hmz=new-epic]")
        expect(view.locator("[data-hmz=flow-picker] b")).not_to_have_text("…")
        # The heading in a 44px bar, the flow picked right beside it.
        assert _at(page, "[data-hmz=bar]")["height"] == 44
        expect(view.locator("[data-hmz=bar] h1")).to_have_text("New epic")
        heading = _at(page, "[data-hmz=bar] h1")
        picker = _at(page, "[data-hmz=flow-picker]")
        assert 0 <= picker["x"] - (heading["x"] + heading["width"]) <= 12
        # The box docked at the foot, as a new chat's: Add, what is typed and the button
        # that sends in it, where it runs under it at the left, Options and what is set
        # at the right.
        pane = _at(page, "[data-hmz=new-epic]")
        boxed = _at(page, "[data-hmz=start] .composer-box")
        under = _at(page, "[data-hmz=start] [data-hmz=composer-under]")
        expect(view.locator(".composer-box > *")).to_have_count(3)
        assert under["y"] >= boxed["y"] + boxed["height"]
        assert pane["y"] + pane["height"] - (under["y"] + under["height"]) == 8
        assert _at(page, "[data-hmz=environment]")["x"] == boxed["x"] + 12
        # Add offers the files of the folder alone, which `@` completes in a task too.
        view.locator("[data-hmz=composer-add]").click()
        expect(
            page.get_by_role("menu", name="Add").get_by_role("menuitem")
        ).to_have_text(["Add files"])
        page.keyboard.press("Escape")
        assert _at(page, "[data-hmz=workspace-picker]")["x"] < boxed["x"] + 200
        options = page.get_by_role("button", name="Options")
        chip = options.bounding_box()
        assert chip
        assert chip["height"] == 24
        assert abs(chip["x"] + chip["width"] - (boxed["x"] + boxed["width"] - 12)) <= 1
        # Options opens in the middle of the page, over the box.
        expect(page.locator("[data-hmz=options]")).to_be_hidden()
        options.click()
        opened_ = _at(page, "[data-hmz=options]")
        assert opened_["y"] >= 44
        assert opened_["y"] < boxed["y"]
        expect(view.locator(".greeting, .home-mark")).to_have_count(0)


def test_a_new_chat_picks_its_model_from_the_chip_on_its_box(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new/chat")
        chip = page.locator("[data-role=assistant] [data-hmz=pick-model]")
        # It says the model as a person reads it, and is what `-a` spells.
        expect(chip).to_have_text("Haiku 4.5")
        expect(chip).to_have_attribute("data-agent", "claude/claude-haiku-4-5")
        expect(page.get_by_role("button", name="Options")).to_have_count(0)
        # Under the box, at its right, before what the chat may touch: never in it.
        chip_box, send_box = chip.bounding_box(), page.locator(".send").bounding_box()
        boxed = page.locator("[data-hmz=start] .composer-box").bounding_box()
        permission = page.locator("[data-hmz=start] [data-hmz=permission]")
        permission_box = permission.bounding_box()
        assert chip_box
        assert send_box
        assert boxed
        assert permission_box
        assert chip_box["y"] >= boxed["y"] + boxed["height"]
        assert chip_box["height"] == 24
        assert chip_box["x"] > boxed["x"] + boxed["width"] / 2
        assert chip_box["x"] + chip_box["width"] <= permission_box["x"]
        assert (
            permission_box["x"] + permission_box["width"] <= boxed["x"] + boxed["width"]
        )
        assert (send_box["width"], send_box["height"]) == (28, 28)

        chip.click()
        menu = page.get_by_role("menu", name="Model")
        models = menu.locator(".model-menu > [role=menuitem][data-value]")
        expect(models).to_have_count(2)
        expect(models.nth(0)).to_have_class(re.compile("chosen"))
        # One row a model, by the name a person reads; its own is said where pointed at.
        expect(models.nth(0)).to_have_text("Haiku 4.5")
        expect(models.nth(0)).to_have_attribute("data-tip", "claude-haiku-4-5")
        expect(menu.locator(".popover-head")).to_have_count(0)
        assert set(
            models.evaluate_all(
                "all => all.map((one) => Math.round(one.getBoundingClientRect().height))"
            )
        ) == {28}
        menu.locator("[data-value=claude-opus-4-1]").click()
        expect(menu).to_have_count(0)
        expect(chip).to_have_text("Opus 4.1")

        chip.click()
        menu.get_by_role("menuitem", name="Effort").click()
        efforts = page.locator("[data-hmz=pick-effort] [role=menuitem]")
        expect(efforts).to_have_text(
            ["Default", "Ultracode", "Max", "High", "Medium", "Low"]
        )
        efforts.nth(2).click()
        expect(chip).to_have_text("Opus 4.1 Max")
        expect(chip).to_have_attribute("data-agent", "claude/claude-opus-4-1:max")

        # The harness and the account it runs as are under More, one row of the same menu.
        chip.click()
        expect(menu.get_by_role("menuitem", name="CLI")).to_have_count(0)
        menu.get_by_role("menuitem", name="More").click()
        menu.get_by_role("menuitem", name="CLI").click()
        expect(page.locator("[data-hmz=pick-cli] [role=menuitem]")).to_have_text(
            ["claude", "dsh", "litellm"]
        )
        menu.get_by_role("menuitem", name="Account").click()
        accounts = page.locator("[data-hmz=pick-account] [role=menuitem]")
        expect(accounts).to_have_text(["Local", "Add account…"])
        expect(menu.get_by_role("menuitem", name="Refresh models")).to_be_enabled()
        # A model no CLI lists is typed, and Enter there sends nothing.
        typed = menu.locator("[data-hmz=pick-model-typed]")
        typed.fill("claude-sonnet-4-5")
        typed.press("Enter")
        expect(menu).to_have_count(0)
        expect(page).to_have_url(re.compile(r"#/new/chat"))
        expect(chip).to_have_text("Sonnet 4.5")
        expect(chip).to_have_attribute("data-agent", "claude/claude-sonnet-4-5")


def test_a_chat_model_no_cli_would_list_is_typed_in_the_chip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    install(tmp_path, monkeypatch)

    def refused(cli: str, provider: str = "", seconds: float = 0.0) -> tuple[()]:
        raise OSError(f"{cli} is not answering")

    monkeypatch.setattr(hmz.coganchor.models, "ask", refused)
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new/chat")
        chip = page.locator("[data-role=assistant] [data-hmz=pick-model]")
        expect(chip).to_have_text("Pick a model")
        chip.click()
        menu = page.get_by_role("menu", name="Model")
        expect(menu.locator(".hint")).to_contain_text("claude is not answering")
        menu.get_by_role("menuitem", name="More").click()
        menu.locator("[data-hmz=pick-model-typed]").fill("claude-sonnet-4-5")
        expect(chip).to_have_text("Sonnet 4.5")
        expect(chip).to_have_attribute("data-agent", "claude/claude-sonnet-4-5")


def test_a_chat_says_its_model_on_the_chip_of_its_box(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new/chat")
        chip = page.locator("[data-role=assistant] [data-hmz=pick-model]")
        chip.click()
        page.locator(".model-menu [data-value=claude-opus-4-1]").click()
        page.locator("[data-hmz=composer-text]").fill("which model are you")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        said = page.locator("[data-hmz=say] [data-hmz=chat-model]")
        expect(said).to_have_text("Opus 4.1")
        said.click()
        about = page.get_by_role("menu", name="Model")
        expect(about.locator("[data-value=claude-opus-4-1]")).to_have_class(
            re.compile("chosen")
        )
        expect(about.locator(".model-fact")).to_contain_text(
            ["CLIclaude", "AccountLocal"]
        )
        about.get_by_role("menuitem", name="New chat").click()
        expect(page).to_have_url(re.compile(r"#/new/chat\?workspace="))


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
        # Its box is as quiet as a chat app's; what else it takes is offered by Add.
        expect(say).to_have_attribute("placeholder", "Reply…")
        page.locator("[data-hmz=say] [data-hmz=composer-add]").click()
        expect(
            page.get_by_role("menu", name="Add").get_by_role("menuitem")
        ).to_have_text(
            ["Add files", "Slash commands", "Skills and flows", "Run a shell command"]
        )
        page.keyboard.press("Escape")
        expect(say).not_to_have_attribute("placeholder", "Message assistant/1")
        say.fill("and again")
        say.press("Enter")
        expect(thread).to_contain_text("did: and again")
        expect(thread.locator(".said.you .body")).to_have_text(
            ["hello there", re.compile(r"said\s*and again$")]
        )
        expect(page.locator("[data-hmz=waiting]")).to_have_count(0)

        # Only the conversation, as a chat app draws one: no graph, nothing under its row,
        # no Exomyth, and between turns nothing to stop -- running while it answers, its
        # reply looked at here, else resting.
        bar = page.locator("[data-hmz=bar]")
        expect(bar.locator(".badge")).to_have_count(0)
        expect(bar.locator(".crumbs")).to_have_count(0)
        expect(page.get_by_role("button", name="Stop")).to_have_count(0)
        expect(page.locator("[data-hmz=exomyth-open]")).to_have_count(0)
        expect(page.locator("[data-hmz=graph]")).to_have_count(0)
        row = page.locator("[data-hmz=sidebar] .side-item").first
        expect(row.locator(".side-toggle, .side-tree")).to_have_count(0)
        # Its row is a chat app's: what was asked, with no mark of a state and no flow.
        expect(row.locator(".side-mark, [data-hmz=epic-flow]")).to_have_count(0)
        expect(row.locator("[data-hmz=epic]")).to_have_attribute("data-kind", "chat")
        expect(page.get_by_role("tab", name="People")).to_have_count(0)
        # Nothing on it is called an epic, a flow or native: its bar holds its title, one
        # menu and a button for each pane, and its panel says what it is in a chat's words.
        expect(bar.locator(".bar-actions button")).to_have_count(5)
        expect(bar.locator("[data-hmz=prefer]")).to_have_count(0)
        expect(bar).not_to_contain_text(re.compile("epic|flow|native", re.IGNORECASE))
        expect(page.locator("[data-hmz=inspector]")).to_be_hidden()
        _details(page)
        # The pane is headed by its name: the bar picks it, and no row of tabs does.
        expect(page.locator("[data-hmz=inspector] [data-hmz=pane-title]")).to_have_text(
            "Details"
        )
        expect(page.locator("[data-hmz=inspector]").get_by_role("tab")).to_have_count(0)
        expect(page.locator("[data-hmz=inspector] dt")).to_contain_text(
            ["Chat ID", "Saved at", "Folder", "Started", "Model"]
        )
        # What a `$` name that is both a skill and a flow does is picked in that menu, in
        # plain words, saying where what is in force comes from.
        bar.locator("[data-hmz=chat-menu]").click()
        page.get_by_role("menuitem", name="Skill or flow").click()
        prefer = page.locator("[data-hmz=prefer]")
        expect(prefer.locator("[data-prefer=native]")).to_have_attribute(
            "aria-checked", "true"
        )
        expect(prefer.locator("[data-hmz=prefer-from]")).to_have_text("From settings")
        page.keyboard.press("Escape")
        bar.locator(".bar-title").click(button="right")
        expect(page.get_by_role("menuitem", name="Open")).to_be_visible()
        expect(page.get_by_role("menuitem", name="Exomyth")).to_have_count(0)
        expect(page.get_by_role("menuitem", name="Stop")).to_have_count(0)
        page.keyboard.press("Escape")

        # Opened again from its row, it is its conversation again, never a graph.
        page.locator("[data-hmz=epic]").first.click()
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        expect(thread).to_contain_text("did: and again")

        stop(page)
        expect(page.locator("[data-hmz=chat-status]")).to_have_count(0)
        expect(page.locator("[data-hmz=epic] [data-hmz=chat-state]")).to_have_count(0)


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


def test_a_chat_is_started_with_a_permission_and_set_to_another(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new/chat")
        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_attribute("data-value", "claude-haiku-4-5")
        chip = page.locator("[data-hmz=start] [data-hmz=permission]")
        expect(chip).to_have_text("Edit this folder")
        chip.click()
        menu = page.get_by_role("menu", name="Permissions")
        expect(menu.get_by_role("menuitem")).to_have_count(3)
        expect(menu.locator(".choice.chosen")).to_contain_text("Edit this folder")
        menu.locator("[data-permission=danger-full-access]").click()
        expect(chip).to_have_text("Full access")
        page.locator("[data-hmz=composer-text]").fill("hello there")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("did: hello there")
        (record,) = project.parent.glob("humanize-home/chats/*/*/chat.jsonl")
        began = json.loads(record.read_text().splitlines()[0])
        assert began["permission"] == "danger-full-access"

        # The chat's own chip says what its host does, and sets it there.
        live = page.locator("[data-hmz=say] [data-hmz=permission]")
        expect(live).to_have_attribute("data-permission", "danger-full-access")
        live.click()
        page.get_by_role("menu", name="Permissions").locator(
            "[data-permission=read-only]"
        ).click()
        expect(live).to_have_text("Read only")
        say = page.locator("[data-hmz=say] textarea")
        say.fill("and again")
        say.press("Enter")
        expect(thread).to_contain_text("did: and again")
        sets = [
            json.loads(line)
            for line in record.read_text().splitlines()
            if '"event": "set"' in line
        ]
        assert [one["permission"] for one in sets] == ["read-only"]
        # Held to it from that turn: what it was told then, it could not write down.
        assert (project / "landed.txt").read_text() == "hello there\n"
        expect(live).to_have_text("Read only")
        stop(page)


def test_a_chat_is_listed_renamed_stopped_and_carried_on_by_its_id(
    project: Path, engine: str
) -> None:
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        # With nothing to fence it in, so that its turns are taken wherever this runs.
        go(page, "/new/chat")
        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_attribute("data-value", "claude-haiku-4-5")
        page.locator("[data-hmz=start] [data-hmz=permission]").click()
        page.get_by_role("menu", name="Permissions").locator(
            "[data-permission=danger-full-access]"
        ).click()
        page.locator("[data-hmz=composer-text]").fill("hello there")
        page.locator("[data-hmz=composer-text]").press("Enter")

        # A chat is no epic: it is at its own address, by its id, and its record is its own.
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        name = urllib.parse.unquote(page.url.split("#/chats/")[1])
        (record,) = project.parent.glob("humanize-home/chats/*/*/chat.jsonl")
        assert record.parent.name == name
        assert not list(project.parent.glob("humanize-home/epics/*/*"))
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("did: hello there")

        # Listed in the sidebar off `chat.list`, as a chat, at that address.
        row = page.locator("[data-hmz=sidebar] [data-hmz=epic]")
        expect(row).to_have_count(1)
        expect(row).to_have_attribute("data-kind", "chat")
        expect(row).to_have_attribute("href", f"#/chats/{name}")
        expect(row).to_have_attribute("aria-current", "page")
        assert [one["id"] for one in _call(page, "chat.list")["chats"]] == [name]
        assert _call(page, "runs.list")["runs"] == []

        # Renamed, its bar and its row say its title.
        _call(page, "chat.rename", {"chat": name, "title": "Renamed live"})
        expect(page.locator("[data-hmz=bar] [data-hmz=chat-title]")).to_have_text(
            "Renamed live"
        )
        expect(row.locator(".side-label")).to_have_text("Renamed live")

        # A turn open: the button of its box stops it, and the chat stays, between turns.
        button = page.locator("[data-hmz=say] .send")
        expect(button).to_have_attribute("aria-label", "Send")
        say = page.locator("[data-hmz=say] textarea")
        say.fill('run: [["sleep", "60"]]')
        say.press("Enter")
        expect(button).to_have_attribute("aria-label", "Stop")
        expect(row.locator("[data-hmz=chat-state]")).to_have_text("Running")
        button.click()
        expect(thread).to_contain_text("That turn was stopped.")
        expect(button).to_have_attribute("aria-label", "Send")
        stopped = wire.params("chat.stop")
        assert [one["slot"].split(":")[0] for one in stopped] == ["chat"]
        assert not wire.params("epic.stop")
        say.fill("and again")
        say.press("Enter")
        expect(thread).to_contain_text("did: and again")
        # With no turn open, there is nothing to stop: the daemon's own sentence says so.
        refused = page.evaluate(
            """async ([workspace, slot]) => {
              const { chatAsk } = await import('/held.js')
              return chatAsk({ workspace, slot }, 'stop').then(() => '', (error) =>
                `${error.status} ${error.message}`)
            }""",
            [stopped[0]["workspace"], stopped[0]["slot"]],
        )
        assert refused == "409 no turn is open, so there is nothing to stop"

        # Found by Search among the chats, at the same address.
        page.keyboard.press("Control+k")
        page.get_by_role("tab", name="Chats").click()
        found = page.locator("[data-hmz=found] [data-hmz=epic]")
        expect(found).to_have_count(1)
        expect(found).to_have_attribute("href", f"#/chats/{name}")
        expect(found.locator(".result-task")).to_have_text("Renamed live")
        page.get_by_role("tab", name="Epics").click()
        expect(found).to_have_count(0)
        page.keyboard.press("Escape")

        # At rest, what is said in it carries it on: the same chat, resumed by its id.
        stop(page)
        carry = page.locator("[data-hmz=say] textarea")
        carry.fill("what was it")
        carry.press("Enter")
        expect(thread).to_contain_text("did: what was it")
        expect(thread).to_contain_text("did: hello there")
        assert [one.get("resume") for one in wire.params("chat.start")] == [None, name]
        assert page.url.endswith(f"#/chats/{name}")
        assert [one["id"] for one in _call(page, "chat.list")["chats"]] == [name]
        # Read by `chat.*` alone, what was said before with its trace: never as an epic.
        assert not wire.params("runs.get")
        assert not wire.params("runs.trace")
        assert {"chat": name, "trace": True} in wire.params("chat.get")
        stop(page)


@pytest.mark.skip(
    reason="`chat.get` does not say whether a chat kept what carries it on: the page "
    "offers the box of every chat that rests, and the daemon refuses what cannot be"
)
def test_a_chat_that_kept_nothing_to_carry_on_says_it_cannot_be_continued(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "hello there")
        expect(page.locator("[data-hmz=thread]")).to_contain_text("did: hello there")
        stop(page)
        # A chat whose conversation was never kept: nothing in its record to carry on from.
        kept = list(project.parent.glob("humanize-home/chats/*/*/sessions"))
        assert kept
        for one in kept:
            shutil.rmtree(one)
        page.reload()

        expect(page.locator("[data-hmz=not-carried]")).to_have_text(
            "This chat cannot be continued here."
        )
        expect(page.locator("[data-hmz=composer], [data-hmz=say]")).to_have_count(0)
        expect(page.get_by_role("link", name="Resume")).to_have_count(0)


@pytest.mark.usefixtures("loops")
def test_an_epic_given_a_year_or_more_is_resumed_on_its_budget(
    project: Path, engine: str
) -> None:
    chasers = ["-a", f"first_chaser={AGENT}", "-a", f"second_chaser={AGENT}"]
    ran = hmz_exec("-f", "flame_chase", *chasers, "-p", "budget.duration=2s", "work")
    assert ran.returncode == 0, ran.stderr
    (record,) = project.parent.glob("humanize-home/epics/*/*/epic.jsonl")
    origin = record.parent.name
    # As an earlier Humanize wrote a year down: in ISO 8601, in years.
    began, *rest = record.read_text().splitlines()
    year = {"duration": "P1Y", "cost": None, "output_tokens": None, "graceful": True}
    record.write_text(
        "\n".join([json.dumps(json.loads(began) | {"budget": year}), *rest]) + "\n"
    )
    with served() as site, opened(site, engine=engine) as page:
        go(page, f"/epics/{origin}")
        page.get_by_role("link", name="Resume").first.click()
        page.get_by_role("button", name="Options").click()
        minutes = page.get_by_label("Longest it may take, in minutes")
        expect(minutes).to_have_value("525600")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(re.compile(rf".*#/epics/(?!{re.escape(origin)})[^/]+$"))
        name = urllib.parse.unquote(page.url.split("#/epics/")[1].split("?")[0])
        resumed = _call(page, "runs.get", {"name": name})
        assert resumed["picked_up"] == origin
        assert resumed["budget"]["duration"] == 365 * 86400
        stop(page)

        # Kept for the flow as settings says a year, and a new epic of it opens on it.
        go(page, "/new?flow=flame_chase")
        page.get_by_role("button", name="Options").click()
        expect(minutes).to_have_value("525600")


def test_an_epic_is_found_by_its_task(project: Path, engine: str) -> None:
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        _start_chat(page, "find me later")
        stop(page)

        page.keyboard.press("Control+k")
        search = page.get_by_role("combobox", name="Search")
        expect(page.locator("[data-hmz=found] .result")).to_have_count(1)
        # What is listed stays, marked old, until the search typed is answered.
        wire.holds("runs.list")
        search.fill("find")
        found = page.locator("[data-hmz=found]")
        wire.waits(page)
        expect(found).to_have_attribute("aria-busy", "true")
        expect(found.locator(".result")).to_have_count(1)
        expect(search).to_have_value("find")
        wire.lets_through()
        expect(found).not_to_have_attribute("aria-busy", "true")
        search.fill("nothing like it")
        expect(page.locator("[data-hmz=found]")).to_contain_text(
            "Nothing is like that."
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


@pytest.mark.skip(
    reason="a chat asks only what its harness asks, and this page's stand-in `claude` "
    "asks nothing; the TUI and host tests cover a chat's question"
)
def test_a_chat_asks_in_its_conversation_and_is_answered_there(
    project: Path, engine: str
) -> None:
    flows = project / ".hmz" / "flows" / "chat"
    flows.mkdir(parents=True)
    (flows / "__init__.py").write_text(_PICKING)
    with served() as site, opened(site, engine=engine) as page:
        started = _starts(page, "chat", "first")
        # A chat of its own, followed on its own host.
        where = {"workspace": started["workspace"], "slot": started["slot"]}
        go(page, f"/live?{urllib.parse.urlencode(where)}")
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))

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


#: Every pair of themes Humanize comes with: its own, then twelve more, each named for a mood
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


@pytest.mark.usefixtures("talking")
def test_a_flow_is_opened_and_started_from_the_flows(engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        page.get_by_role("link", name="Flows").click()
        page.locator(".card[data-flow='@local/talk']").click()
        expect(page.locator(".flow-detail h2")).to_have_text("@local/talk")
        page.get_by_role("link", name="New epic").last.click()
        expect(page.locator("[data-hmz=flow-picker] b")).to_have_text("@local/talk")


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
        # The sidebar's top row stands beside them, in their strip: what hides the sidebar
        # straight after them, and the mark, which they took the place of, before the bell.
        assert left(page, ".side-fold") >= lights
        assert top(page, ".side-fold") < strip
        assert left(page, ".brand") > left(page, ".side-forward")
        assert left(page, ".brand") < left(page, "[data-hmz=notifications]")
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


def test_in_the_windows_app_the_top_row_keeps_clear_of_the_caption_buttons(
    project: Path, engine: str
) -> None:
    """The app's window draws the page to its top edge, its caption buttons over the top right."""
    # What can be clicked where they stand, the window's top 32 pixels and its right 138: what
    # is drawn there, every 4 pixels.
    under = (
        "(() => { const found = new Set(); for (let x = innerWidth - 138; x < innerWidth;"
        " x += 4) for (let y = 0; y < 32; y += 4) { const el = document"
        ".elementFromPoint(x, y)?.closest('a, button, input, select, textarea, summary,"
        " [role=tab]'); if (el) found.add(el.outerHTML.slice(0, 80)) } return [...found] })()"
    )
    windows = "Object.defineProperty(navigator, 'platform', { get: () => 'Win32' })"
    with (
        served() as site,
        opened(site, engine=engine, user_agent=_WINDOWS_APP, init=windows) as page,
    ):
        assert page.evaluate("document.documentElement.dataset.shell") == "windows"
        expect(page.locator("[data-hmz=bar]")).to_have_attribute(
            "data-tauri-drag-region", "deep"
        )
        # The shortcuts as Windows writes them.
        expect(page.locator(".side-nav kbd")).to_have_text(["Ctrl+Shift+O", "Ctrl+K"])
        assert page.evaluate(under) == []

        # The panel beside the epic, open, is the top right; and shut, the bar is.
        _start_chat(page, "hello there")
        _details(page)
        assert page.evaluate(under) == []
        page.locator("[data-hmz=inspector] .panel-close").click()
        expect(page.locator("[data-hmz=inspector]")).to_be_hidden()
        assert page.evaluate(under) == []
        # Full screen, where they are gone, it is drawn as in a browser.
        page.evaluate(
            "document.documentElement.toggleAttribute('data-fullscreen', true)"
        )
        assert page.evaluate(under) != []
        page.evaluate(
            "document.documentElement.toggleAttribute('data-fullscreen', false)"
        )

        # A narrow window: the bar, and a dialog that fills it.
        page.set_viewport_size({"width": 700, "height": 800})
        assert page.evaluate(under) == []
        page.keyboard.press("Control+k")
        expect(page.locator("[data-hmz=dialog-search]")).to_be_visible()
        assert page.evaluate(under) == []
        go(page, "/settings/general")
        expect(page.locator("[data-hmz=settings-general]")).to_be_visible()
        assert page.evaluate(under) == []


@pytest.mark.usefixtures("talking")
def test_every_label_is_a_word_or_a_phrase(project: Path, engine: str) -> None:
    """A button, a tab, a menu item or a heading names a thing; it never says a sentence."""
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "label me")
        said: list[str] = []
        settings = (f"/settings/{one}" for one in _PAGES)
        for address in (_NEW, "/flows", "/search", *settings):
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


@pytest.mark.usefixtures("talking")
def test_a_setup_is_saved_without_starting_an_epic(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, _NEW)
        _options(page)
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
        go(page, _NEW)
        page.get_by_role("button", name="Options").click()
        expect(role.locator("[data-hmz=pick-model]")).to_have_value("claude-opus-4-1")


@pytest.mark.usefixtures("talking")
def test_a_start_says_it_is_starting_until_the_epic_opens(
    project: Path, engine: str
) -> None:
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, _NEW)
        wire.holds("epic.start")
        _options(page)
        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_value("claude-haiku-4-5")
        page.locator("[data-hmz=composer-text]").fill("hold on")
        page.locator("[data-hmz=composer-text]").press("Enter")
        box = page.locator("[data-hmz=start]")
        expect(box).to_have_attribute("aria-busy", "true")
        expect(box.get_by_role("status")).to_have_text("Starting…")
        expect(box.get_by_role("button", name="Starting…")).to_be_disabled()
        wire.waits(page)
        wire.lets_through()
        page.wait_for_url(_EPIC)
        stop(page)


@pytest.mark.usefixtures("talking")
def test_a_workspace_read_marks_the_flow_drawn_until_it_is_read(
    project: Path, engine: str
) -> None:
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, _NEW)
        expect(page.locator("[data-hmz=flow-picker] b")).to_have_text("@local/talk")
        expect(page.locator("[data-hmz=options]")).not_to_have_class(
            re.compile("stale")
        )
        wire.holds("flows.get")
        page.locator("[data-hmz=flow-picker]").click()
        page.get_by_role("menuitem", name=re.compile("talk")).first.click()
        expect(page.locator(".greeting-about [role=status]")).to_have_text("Reading…")
        expect(page.locator("[data-hmz=options]")).to_have_class(re.compile("stale"))
        wire.waits(page)
        wire.lets_through()
        expect(page.locator(".greeting-about [role=status]")).to_have_count(0)
        expect(page.locator("[data-hmz=options]")).not_to_have_class(
            re.compile("stale")
        )


@pytest.mark.usefixtures("talking")
def test_the_flow_and_its_environment_are_profiled_apart(
    project: Path, engine: str
) -> None:
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, _NEW)
        _options(page)
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
        go(page, _NEW)
        page.get_by_role("button", name="Options").click()
        expect(flow).to_be_checked()
        expect(environment).not_to_be_checked()
        environment.check()

        page.locator("[data-hmz=composer-text]").fill("profile me")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(_EPIC)
        (said,) = wire.params("epic.start")
        assert (said["profile_flow"], said["profile_environment"]) == (True, True)
        stop(page)


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

        # A chat's bar is its title, one menu and the panel's button: what is done to the
        # chat is in that menu.
        more = page.locator("[data-hmz=chat-menu]")
        more.click()
        with page.expect_download() as saving:
            page.get_by_role("menuitem", name="Export").click()
        saved = saving.value
        assert saved.suggested_filename.endswith(".hmzepic")
        assert Path(saved.path()).read_bytes()[:2] == b"\x1f\x8b"

        # WebKit lets a click write unasked, and knows no permission to write by.
        writes = ["clipboard-write"] if engine == "chromium" else []
        page.context.grant_permissions(["clipboard-read", *writes])
        more.click()
        page.get_by_role("menuitem", name="Copy link").click()
        expect(page.locator(".toast")).to_have_text("Link copied")
        assert page.url.startswith(page.evaluate("navigator.clipboard.readText()"))


@pytest.mark.usefixtures("talking")
def test_a_backup_target_is_added_picked_at_a_start_and_an_epic_uploaded_to_it(
    project: Path, engine: str
) -> None:
    import subprocess

    bare = project.parent / "epics.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, "/settings/backup")
        writing = page.locator("[data-hmz=write-backup]")
        writing.get_by_label("Name").fill("t")
        writing.get_by_label("Repository").fill(str(bare))
        writing.get_by_role("button", name="Save").click()
        listed = page.locator("[data-hmz=backup-target][data-name=t]")
        expect(listed).to_contain_text("Manual")
        # Ticked, it is written down before a new epic reads it.
        writes = len(wire.params("settings.set"))
        listed.locator("[data-hmz=backup-default]").check()
        expect(listed.locator("[data-hmz=backup-default]")).to_be_checked()
        assert len(wire.params("settings.set")) > writes
        assert _call(page, "settings.get")["backup"]["defaults"] == ["t"]
        page.keyboard.press("Escape")

        go(page, _NEW)
        _options(page)
        expect(page.locator("[data-hmz=backup] input[value=t]")).to_be_checked()
        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_value("claude-haiku-4-5")
        page.locator("[data-hmz=composer-text]").fill("back me up")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(_EPIC)
        stop(page)

        page.locator("[data-hmz=bar] .bar-title").click(button="right")
        page.get_by_role("menuitem", name="Upload").click()
        expect(page.locator(".toast")).to_have_text("Uploading to t")
        # How it went is said on the epic's bar, where Upload is.
        expect(page.locator("[data-hmz=bar] [data-hmz=upload]")).to_have_attribute(
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
        expect(page.locator("[data-hmz=thread]")).to_be_visible()
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
        _details(page)
        inspector = page.locator("[data-hmz=inspector]")
        expect(inspector.locator("[data-hmz=environments]")).to_contain_text(
            re.compile(r"\w+/1 local · ")
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

    asks = Btw.ask

    def slowly(self: Btw, question: str, snapshot: FlowSnapshot) -> str:
        # Long enough to be seen answering.
        if "slowly" in question:
            time.sleep(3)
        return asks(self, question, snapshot)

    monkeypatch.setattr(Btw, "ask", slowly)
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "remember papaya")
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("did: remember papaya")
        _side_questions(page)
        aside = page.locator("[data-hmz=btw]")
        ask = page.locator("[data-hmz=btw-to]")

        # No conversation until one is picked, picked above the box rather than in it, and no
        # agent to pick here at all, nor The Epic.
        expect(ask).to_contain_text("Pick a conversation")
        expect(aside.locator("[data-hmz=btw-to]")).to_have_count(0)
        expect(
            page.locator("[data-hmz=btw-whom], [data-hmz=btw-picker]")
        ).to_have_count(0)
        ask.click()
        expect(page.locator("[data-hmz=btw-the-epic]")).to_have_count(0)
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

        # Asked with no conversation picked: it says to pick one first.
        aside.locator("textarea").fill("what is it doing")
        aside.locator("textarea").press("Enter")
        expect(aside).to_contain_text("Pick the conversation to ask first.")
        expect(ask).to_be_visible()
        _asks_of(page, "/1")
        aside.locator("textarea").fill("what now")
        aside.locator("textarea").press("Enter")
        log = page.locator("[data-hmz=btw-log]")
        expect(log).to_contain_text(re.compile(r"btw · \w+/1"))
        expect(log.locator(".said.btw")).to_have_count(1)
        # Whom it asks was fixed by its first answer: nothing to pick for it any more.
        expect(ask).to_be_hidden()

        # A second aside, of a conversation, picked at its start.
        page.locator("[data-hmz=btw-new]").click()
        expect(ask).to_be_visible()
        _asks_of(page, "/1")
        aside.locator("textarea").fill("and you, slowly")
        aside.locator("textarea").press("Enter")
        # Answering, it says so.
        working = page.locator("[data-hmz=btw-working]")
        expect(working).to_contain_text("is thinking")
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
        _side_questions(page)
        expect(tabs).to_have_count(2)
        expect(log).to_contain_text("and you, slowly")
        tabs.first.click()
        expect(log).to_contain_text("what now")
        # Closed, one goes, and the other stays.
        page.locator("[data-hmz=btw-close]").click()
        expect(tabs).to_have_count(1)
        expect(log).to_contain_text("and you, slowly")
        stop(page)


def test_ai_chan_drawer_opens_from_every_view_with_her_avatar_and_new_form(
    project: Path, engine: str, tmp_path: Path
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new")
        drawer = page.locator("[data-hmz=aichan]")
        expect(drawer).to_be_hidden()
        toggle = page.locator("[data-hmz=aichan-toggle]").first
        expect(toggle).to_have_attribute("aria-pressed", "false")
        toggle.click()
        expect(drawer).to_be_visible()
        expect(toggle).to_have_attribute("aria-pressed", "true")
        # Her avatar, loaded and drawn in hard pixels.
        avatar = drawer.locator(".aichan-head img")
        expect(avatar).to_have_attribute("src", "/ai-chan/avatar.png")
        assert avatar.evaluate("(img) => img.complete && img.naturalWidth") == 512
        assert (
            avatar.evaluate("(img) => getComputedStyle(img).imageRendering")
            == "pixelated"
        )
        # Open from view to view, until closed.
        go(page, "/flows")
        expect(drawer).to_be_visible()
        # New: the scope the page shows, a preset, the network off, and the task.
        drawer.locator("[data-hmz=aichan-new]").click()
        form = drawer.locator("[data-hmz=aichan-form]")
        expect(form).to_be_visible()
        # The flows of a workspace show it: the scope starts on it.
        expect(form.locator("[data-hmz=aichan-scope]")).to_have_value("workspace")
        expect(form.locator("[data-hmz=aichan-workspace]")).to_be_visible()
        expect(form.locator("[data-hmz=aichan-preset]")).to_have_value("read-only")
        expect(form.locator("[data-hmz=aichan-network]")).not_to_be_checked()
        expect(form.locator("[data-hmz=aichan-epic]")).to_be_hidden()
        page.screenshot(path=str(tmp_path / "aichan-drawer.png"))
        form.locator("[data-hmz=aichan-scope]").select_option("daemon")
        expect(form.locator("[data-hmz=aichan-workspace]")).to_be_hidden()
        form.locator("[data-hmz=aichan-scope]").select_option("epic")
        expect(form.locator("[data-hmz=aichan-epic]")).to_be_visible()
        expect(form.locator("[data-hmz=aichan-task] textarea")).to_be_visible()
        drawer.get_by_role("button", name="Close panel").click()
        expect(drawer).to_be_hidden()


@pytest.mark.usefixtures("talking")
@pytest.mark.parametrize(
    ("link", "held", "read"),
    [
        ("new", "flows.get", "[data-hmz=composer-text][placeholder^='What should']"),
        ("new/chat", "settings.get", "[data-hmz=role][data-role=assistant]"),
    ],
)
def test_a_new_view_read_under_ai_chans_drawer_takes_no_focus_out_of_it(
    project: Path, engine: str, link: str, held: str, read: str
) -> None:
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, "/flows")
        page.locator("[data-hmz=aichan-toggle]").first.click()
        drawer = page.locator("[data-hmz=aichan]")
        drawer.locator("[data-hmz=aichan-new]").click()
        task = drawer.locator("[data-hmz=aichan-task] textarea")
        expect(task).to_be_focused()
        # The view is asked for from the sidebar, and what it reads is slow to come.
        wire.holds(held)
        page.locator(f"a[data-nav='{link}']:not(.brand)").click()
        wire.waits(page)
        # Meanwhile the person goes to tell Ai-chan something.
        task.click()
        page.keyboard.type("stop ")
        wire.lets_through()
        # Read, the view is drawn whole, and what is typed still goes to her.
        expect(page.locator(f"[data-hmz=page] {read}")).to_be_visible()
        expect(task).to_be_focused()
        page.keyboard.type("the epic")
        expect(task).to_have_value("stop the epic")
        expect(page.locator("[data-hmz=page] [data-hmz=composer-text]")).to_have_value(
            ""
        )
        # Asked for from her drawer itself, by its shortcut, a new chat is typed into.
        go(page, "/flows")
        task.click()
        page.keyboard.press("ControlOrMeta+Shift+O")
        expect(page.locator("[data-hmz=page] [data-hmz=composer-text]")).to_be_focused()


def test_what_is_pressed_on_an_epic_says_it_is_busy_until_its_reply(
    project: Path, engine: str, talking: None
) -> None:
    #: Each call held back until let through, so what is pressed is seen waiting on it.
    wire = Wire()
    holding = wire.holds

    def through() -> None:
        wire.waits(page)
        wire.lets_through()

    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        _start_talk(page, "busy me")

        # The question's typed answer.
        card = page.locator("[data-hmz=question]")
        expect(card).to_be_visible()
        holding("epic.answer")
        card.get_by_label("Answer").fill("go on")
        card.get_by_label("Answer").press("Enter")
        answering = card.get_by_role("button", name="Answering…")
        expect(answering).to_be_disabled()
        through()
        expect(answering).to_have_count(0)

        # An aside's Close.
        page.get_by_role("tab", name="Aside").click()
        aside = page.locator("[data-hmz=btw]")
        _asks_of(page, "/1")
        aside.locator("textarea").fill("what now")
        aside.locator("textarea").press("Enter")
        expect(page.locator("[data-hmz=btw-log] .said.btw")).to_have_count(1)
        holding("btw.leave")
        page.locator("[data-hmz=btw-close]").click()
        closing = page.get_by_role("button", name="Closing…")
        expect(closing).to_be_disabled()
        through()
        expect(page.locator("[data-hmz=btw-tab]")).to_have_count(1)
        expect(closing).to_have_count(0)

        # Upload, from the bar: the button says it is busy, and nothing else says so too.
        holding("runs.backup")
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
        holding("epic.stop")
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
        _side_questions(page)
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
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        expect(page.locator("[data-hmz=thread]")).to_contain_text(
            "did: remember papaya"
        )

        _side_questions(page)
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
        page.locator("[data-hmz=chat-menu]").click()
        with page.expect_download() as saving:
            page.get_by_role("menuitem", name="Export").click()
        archive = tmp_path / saving.value.suggested_filename
        saving.value.save_as(archive)
        at = _call(page, "runs.get", {"name": name})["at"]
        opened_on = re.compile(rf".*#/epics/{re.escape(name)}$")
        # By its path, an epic opens on its Exomyth, as the desktop app opens a file.
        on_exomyth = re.compile(rf".*#/epics/{re.escape(name)}/exomyth$")
        listed = page.locator(f"[data-hmz=sidebar] .side-item[data-epic='{name}']")

        def gone() -> None:
            go(page, "/new")
            shutil.rmtree(at)

        # Picked, from Search.
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
            "cannot be continued here: the workspace it ran in, /nowhere/at/all, is not"
        )
        expect(app.get_by_role("link", name="Resume")).to_have_count(0)


def _held(page: Page) -> dict[str, dict[str, object]]:
    """Each chat and epic listed, by its task: whether a host holds it, how it stands, and which.

    A chat is listed by `chat.list`, an epic by `runs.list`: each as the page's lists row it.
    """
    return page.evaluate(
        """async () => {
          const api = await import('/api.js')
          const { chatRow } = await import('/chats.js')
          const rows = [...(await api.call('chat.list')).chats.map((one) => chatRow(one)),
            ...(await api.call('runs.list')).runs]
          return Object.fromEntries(rows.map((one) => [one.task, {held: one.held, how: one.how,
            slot: one.slot, name: one.name}]))
        }"""
    )


@pytest.mark.usefixtures("talking")
def test_a_chat_answered_unread_still_asks_once_folded_until_one_looks(
    engine: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hosting, "FOLD", 0.5)
    with served() as site, opened(site, engine=engine) as page:
        _start_talk(page, "a flow beside")
        # Not looked at, as a page behind another window is not, while the chat answers.
        page.evaluate("document.hasFocus = () => false")
        _start_chat(page, "remember teal")
        # A chat says how it stands over its box; a flow's epic, on its bar.
        status = page.locator("[data-hmz=chat-status]")
        expect(status).to_have_attribute("data-state", "asking")
        expect(status).to_have_text("Waiting for you")

        # Looked away from, it folds -- and still asks, as nobody has read what it said.
        page.locator("[data-hmz=epic]", has_text="a flow beside").click()
        expect(page.locator("[data-hmz=bar] .badge")).to_have_text(
            re.compile("running|waiting|asking")
        )
        page.evaluate("delete document.hasFocus")
        # Folded for good: what folds says it goes a moment yet, and held a moment before.
        folded, deadline = 0, time.monotonic() + 30
        while folded < 5:
            assert time.monotonic() < deadline, _held(page)
            one = _held(page)["remember teal"]
            folded = folded + 1 if not one["held"] and one["how"] == "stopped" else 0
            page.wait_for_timeout(500)
        # Opened afresh, so the list is read as it stands now.
        page.reload()
        row = page.locator("[data-hmz=epic]", has_text="remember teal")
        state = row.locator("[data-hmz=chat-state]")
        expect(state).to_have_attribute("data-state", "asking")
        expect(state).to_have_text("Awaiting input")

        # Read, it is stopped: its row says nothing beside what was asked.
        row.click()
        expect(state).to_have_count(0)
        expect(status).to_have_count(0)


@pytest.mark.usefixtures("talking")
def test_chats_go_beside_each_other_and_a_flow_and_one_folded_is_carried_on(
    project: Path, engine: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Nobody reading a chat between turns lets it go, and it folds, in a moment.
    monkeypatch.setattr(hosting, "FOLD", 0.5)
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "remember teal")
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("did: remember teal")
        first = page.url
        # A flow, and a second chat: none of them ends another.
        _start_talk(page, "a flow beside")
        _start_chat(page, "another chat")
        expect(thread).to_contain_text("did: another chat")
        while sum(1 for one in _held(page).values() if one["held"]) != 3:
            page.wait_for_timeout(200)
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
        while _held(page)["remember teal"]["held"]:
            page.wait_for_timeout(200)
        name = _held(page)["remember teal"]["name"]

        # Said something, it is carried on, the same chat, what was said before above.
        page.goto(first)
        expect(thread).to_contain_text("did: remember teal")
        say = page.locator("[data-hmz=say] textarea")
        say.fill("what was it")
        say.press("Enter")
        expect(thread).to_contain_text("did: what was it")
        expect(thread).to_contain_text("did: remember teal")
        assert page.url.endswith(f"/chats/{name}")
        held = _held(page)
        assert len(held) == 3
        assert held["remember teal"]["name"] == name
        while not _held(page)["remember teal"]["held"]:
            page.wait_for_timeout(200)
        stop(page)

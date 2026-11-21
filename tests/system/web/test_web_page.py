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
    "language",
    "accounts",
    "nous",
    "runtimes",
    "backup",
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


#: A new epic of the project's own `talk`: a chat is of no flow, and a flow's epic is set up.
_NEW = "/new?flow=%40local%2Ftalk"


def _options(page: Page) -> None:
    """Gives a new epic a budget, without which no flow starts: its set-up is in sight."""
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
        # The role is a row of the page's middle, in sight with nothing pressed: its
        # name, and the nous that fills it on a chip.
        row = page.locator(
            "[data-hmz=options] [data-hmz=role-row][data-role=assistant]"
        )
        expect(row).to_be_visible()
        expect(row.locator(".setup-role")).to_have_text("assistant")
        chip = row.locator("[data-hmz=pick-model]")
        expect(chip).to_have_text("Claude Code Haiku 4.5 Default")
        expect(chip).to_have_attribute(
            "aria-label", "Nous: Claude Code Haiku 4.5 Default"
        )
        chip.click()
        menu = page.get_by_role("menu", name="Nous")
        # A row a level, never a list of every nous: what is picked at each.
        expect(menu.locator(".choice.step")).to_contain_text(
            ["Claude Code", "Haiku 4.5", "Default"]
        )
        # Under the chip, its left edge on the chip's: never over the page's bar.
        chip_box, menu_box = chip.bounding_box(), menu.bounding_box()
        assert chip_box
        assert menu_box
        assert menu_box["y"] >= chip_box["y"] + chip_box["height"]
        assert abs(menu_box["x"] - chip_box["x"]) <= 1
        # The models the harness picked runs, and no other's.
        menu.locator("[data-hmz=step-model]").click()
        expect(menu.locator(".nous-list [role=menuitem]")).to_have_text(
            ["Haiku 4.5", "Opus 4.1"]
        )
        menu.locator("[data-value=claude-opus-4-1]").click()
        expect(chip).to_have_text("Claude Code Opus 4.1 Default")
        chip.click()
        menu.locator("[data-hmz=step-effort]").click()
        efforts = menu.locator("[role=menuitem][data-value]")
        expect(efforts).to_have_text(
            ["Default", "Ultracode", "Max", "High", "Medium", "Low"]
        )
        efforts.nth(2).click()
        expect(chip).to_have_text("Claude Code Opus 4.1 Max")
        expect(chip).to_have_attribute("data-agent", "claude/claude-opus-4-1:max")
        # What is set is said where it is set, and nowhere under the box.
        expect(page.locator(".composer-summary")).to_have_count(0)
        expect(
            page.locator("[data-hmz=start] [data-hmz=composer-under] button")
        ).to_have_count(0)


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
        _answer(page, "Stop this epic?", "Stop")
        expect(badge).to_have_text(re.compile("stopped"))
        expect(badge).to_have_class(re.compile("tone-stopped"))


def _answer(within: Page | Locator, ask: str, yes: str) -> None:
    """Answers the question a button asks beside itself: the button stays, the popup asks.

    The popup is focused on the answer that does nothing, and is the one transient open.
    """
    asked = within.get_by_role("dialog", name=ask)
    expect(asked.get_by_role("button", name="Cancel")).to_be_focused()
    asked.get_by_role("button", name=yes).click()
    expect(asked).to_have_count(0)


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
        _answer(page, "Stop this epic?", "Stop")
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
        chip = page.locator("[data-role=assistant] [data-hmz=pick-model]")
        chip.click()
        menu = page.get_by_role("menu", name="Nous")
        expect(menu).to_contain_text("claude is not answering")
        menu.locator("[data-hmz=step-model]").click()
        typed = menu.locator("[data-hmz=pick-model-typed]")
        typed.fill("claude-sonnet-4-5")
        typed.press("Enter")
        expect(chip).to_have_text("Claude Code Sonnet 4.5 Default")
        expect(chip).to_have_attribute("data-agent", "claude/claude-sonnet-4-5")


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
            # 715 to 743, the chips under it at 760 to 784.
            assert (inside[0]["y"], inside[0]["height"]) == (715, 28)
            assert (under["y"], under["height"]) == (760, 24)

        # Under the box: what it is of and where it works at the left, how at the right,
        # each 24px high.
        chips = view.locator("[data-hmz=composer-under] button:visible")
        assert chips.evaluate_all("all => all.map((one) => one.dataset.hmz)") == [
            "folder",
            "environment",
            "pick-model",
            "permission",
            "new-usage",
        ]
        # At the left the two chips, and nothing else: no daemon, no box to tick.
        expect(view.locator("[data-hmz=composer-under] .under-left > *")).to_have_count(
            2
        )
        expect(view.locator("[data-hmz=workspace-picker]")).to_have_count(0)
        expect(
            view.locator("[data-hmz=composer-under] [data-hmz=daemon]")
        ).to_have_count(0)
        for at in range(5):
            box = chips.nth(at).bounding_box()
            assert box
            assert box["height"] == 24
        # Set in from the box's edges, as a chat app's are, on a phone too: the first
        # starts a hair right of the Add button.
        inset = 12
        first = _at(page, "[data-hmz=start] [data-hmz=folder]")
        assert first["x"] == boxed["x"] + inset
        assert first["x"] == inside[0]["x"] + 3
        # The row ends, as a chat app's does, with the ring that says what was used: as
        # far from the box's edge as the first chip is from the other. On a phone the
        # two ends do not fit side by side: the second stands under the first, still
        # ending at that edge, and the row is never scrolled sideways.
        last = _at(page, "[data-hmz=start] [data-hmz=new-usage]")
        assert last["width"] == 24
        end = boxed["x"] + boxed["width"] - inset
        assert abs(last["x"] + last["width"] - end) <= 1
        if width <= 860:
            second = _at(page, "[data-hmz=start] [data-hmz=pick-model]")
            assert second["x"] >= first["x"]
            assert second["y"] == first["y"] + first["height"] + 4
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
                " && document.querySelector('[data-hmz=start] [data-hmz=composer-under]')"
                ".scrollWidth <= document.querySelector('[data-hmz=start]"
                " [data-hmz=composer-under]').clientWidth"
            )
        # Folder is what the chat is of: the folder picked, and nothing of a daemon.
        folder_chip = view.locator("[data-hmz=start] [data-hmz=folder]")
        expect(folder_chip).to_have_text(project.name)
        # Said, to whoever cannot see it, with what it picks.
        expect(folder_chip).to_have_attribute("aria-label", f"Folder: {project.name}")
        folder_chip.click()
        folders = page.get_by_role("menu", name="Folder")
        expect(folders.locator("[data-daemon]")).to_have_count(0)
        rows = folders.get_by_role("menuitem")
        # None, then the ones there are, then opening one.
        expect(folders.locator("[data-folder].chosen")).to_have_text(project.name)
        expect(rows.nth(0)).to_contain_text("No folder")
        expect(rows.nth(-1)).to_contain_text("Open folder…")
        expect(folders.locator("[data-folder].chosen")).to_be_focused()
        # A menu of the desk is a chat app's: a choice of one line is a row of 28px.
        assert _at(page, "[role=menu] [data-folder].chosen")["height"] == 28
        page.keyboard.press("Escape")

        # Environment is where the chat works: this computer until another is picked,
        # said in one line over the places, and never a daemon.
        where = view.locator("[data-hmz=start] [data-hmz=environment]")
        expect(where).to_have_text("This computer")
        expect(where).to_have_attribute("aria-label", "Environment: This computer")
        where.click()
        offered = page.get_by_role("menu", name="Environment")
        expect(offered.locator("[data-hmz=environment-about]")).to_have_text(
            "Where this chat\u2019s commands run and its files live."
        )
        expect(offered.locator("[data-daemon]")).to_have_count(0)
        places = offered.get_by_role("menuitemradio")
        expect(places.locator(".choice-label")).to_have_text(
            ["This computer", "New worktree"]
        )
        expect(offered.locator("[data-env=local]")).to_have_attribute(
            "aria-checked", "true"
        )
        expect(offered.get_by_role("menuitem")).to_have_text(["Add runtime…"])
        # Over the chip, its lower edge by the chip's upper edge.
        chip_box = _at(page, "[data-hmz=start] [data-hmz=environment]")
        menu_box = offered.bounding_box()
        assert menu_box
        assert menu_box["y"] + menu_box["height"] <= chip_box["y"]
        page.keyboard.press("Escape")

        # Before there is a chat, Add offers the one prefix the page completes by
        # itself: `@`, which completes the folder's files.
        (project / "notes.md").write_text("notes\n", encoding="utf-8")
        text = view.locator("[data-hmz=composer-text]")
        view.locator("[data-hmz=composer-add]").click()
        adding = page.get_by_role("menu", name="Add")
        expect(adding.get_by_role("menuitem")).to_have_text(["Add files"])
        assert _at(page, "[role=menu][aria-label=Add]")["width"] == 180
        adding.get_by_role("menuitem", name="Add files").click()
        expect(text).to_have_value("@")
        expect(page.locator("[data-hmz=completions]")).to_contain_text("@notes.md")
        text.fill("")

        # In the middle, the chats that wait on their person, as a chat app lists them:
        # the list alone, 320 wide at most, its rows of 32px as wide as it, each opening
        # its chat, each dismissed with a 24px button inside the row, at its right.
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
        assert (lined["x"], lined["width"]) == (listed["x"], listed["width"])
        assert lined["height"] == 32
        dismiss = _at(page, "[data-hmz=next-dismiss]")
        assert (dismiss["width"], dismiss["height"]) == (24, 24)
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
        # that sends in it, and nothing under it at either end.
        pane = _at(page, "[data-hmz=new-epic]")
        boxed = _at(page, "[data-hmz=start] .composer-box")
        under = _at(page, "[data-hmz=start] [data-hmz=composer-under]")
        expect(view.locator(".composer-box > *")).to_have_count(3)
        assert under["y"] >= boxed["y"] + boxed["height"]
        assert pane["y"] + pane["height"] - (under["y"] + under["height"]) == 8
        expect(view.locator("[data-hmz=composer-under] .under-left > *")).to_have_count(
            0
        )
        expect(
            view.locator("[data-hmz=composer-under] .under-right > *")
        ).to_have_count(0)
        # Add offers the files of the folder alone, which `@` completes in a task too.
        view.locator("[data-hmz=composer-add]").click()
        expect(
            page.get_by_role("menu", name="Add").get_by_role("menuitem")
        ).to_have_text(["Add files"])
        page.keyboard.press("Escape")
        # What the flow is set up with is in the middle of the page, over the box, with
        # nothing pressed: no Options, no Save, and nothing said of it under the box.
        expect(page.get_by_role("button", name="Options", exact=True)).to_have_count(0)
        expect(page.get_by_role("button", name="Save")).to_have_count(0)
        expect(page.locator(".composer-summary")).to_have_count(0)
        expect(page.locator("[data-hmz=options]")).to_be_visible()
        opened_ = _at(page, "[data-hmz=options]")
        assert opened_["y"] >= 44
        assert opened_["y"] < boxed["y"]
        # Environment first, the folder its first row: the names in one column and what
        # each picks in the next. The form neither names nor offers a daemon: which hmz
        # serves it is the whole page's, said and picked at the foot of the sidebar.
        parts = view.locator("[data-hmz=options] > *")
        expect(parts.nth(0)).to_have_attribute("data-hmz", "setup-environment")
        expect(parts.nth(0).locator("h3")).to_have_text("Environment")
        expect(parts.nth(0).locator(".setup-row > .setup-name")).to_have_text(
            ["Folder"]
        )
        expect(view.locator("[data-hmz=setup-serving]")).to_have_count(0)
        expect(view.locator("[data-hmz=daemon]")).to_have_count(0)
        expect(view.get_by_role("button", name=re.compile("^Daemon"))).to_have_count(0)
        expect(view.locator("[data-hmz=options] h3")).not_to_contain_text(["Daemon"])
        folder = _at(page, "[data-hmz=setup-folder] [data-hmz=workspace-picker]")
        assert folder["height"] == 24
        expect(view.locator("[data-hmz=workspace-picker] b")).to_have_text(project.name)
        # Its menu opens under it.
        view.locator("[data-hmz=workspace-picker]").click()
        folders = page.get_by_role("menu", name="Folders")
        expect(folders.get_by_role("menuitem").nth(0)).to_contain_text("No folder")
        expect(folders.get_by_role("menuitem").nth(-1)).to_contain_text("Open folder…")
        box = folders.bounding_box()
        assert box
        assert box["y"] >= folder["y"] + folder["height"]
        page.keyboard.press("Escape")
        # Each role of the flow is a line of its own, under the one before it.
        tops = view.locator("[data-hmz=role-row]").evaluate_all(
            "all => all.map((one) => one.getBoundingClientRect().top)"
        )
        assert tops
        assert tops == sorted(set(tops))
        expect(view.locator(".greeting, .home-mark")).to_have_count(0)


def test_a_new_chat_picks_its_model_from_the_chip_on_its_box(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new/chat")
        chip = page.locator("[data-role=assistant] [data-hmz=pick-model]")
        # It says the harness, the model and the effort by name, and is what `-a` spells.
        expect(chip).to_have_text("Claude Code Haiku 4.5 Default")
        # Each of the three is told from the next by its colour.
        inks = chip.locator(".nous-said > span").evaluate_all(
            "all => all.map((one) => getComputedStyle(one).color)"
        )
        assert len(set(inks)) == 3
        expect(chip).to_have_attribute("data-agent", "claude/claude-haiku-4-5")
        expect(page.get_by_role("button", name="Options", exact=True)).to_have_count(0)
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
        menu = page.get_by_role("menu", name="Nous")
        # It opens from the chip: its foot by the chip's top, over the box.
        opened_at = menu.bounding_box()
        assert opened_at
        assert boxed["y"] < opened_at["y"] + opened_at["height"] <= chip_box["y"]
        assert chip_box["y"] - opened_at["y"] - opened_at["height"] <= 6
        # A row a level, each saying what is picked at it: never a list of every nous. One
        # account alone is no level, and no virtual nous is no heading.
        levels = menu.locator(".choice.step")
        expect(levels.locator(".choice-label")).to_have_text(
            ["Harness", "Model", "Effort"]
        )
        expect(levels.locator(".choice-about")).to_have_text(
            ["Claude Code", "Haiku 4.5", "Default"]
        )
        expect(menu.locator(".nous-list, .popover-head")).to_have_count(0)
        assert set(
            levels.evaluate_all(
                "all => all.map((one) => Math.round(one.getBoundingClientRect().height))"
            )
        ) == {28}
        # Every harness here is a choice of its own level, and no model of any stands there.
        menu.locator("[data-hmz=step-harness]").click()
        harnesses = menu.locator("[role=menuitem][data-cli]")
        expect(harnesses.first).to_have_text("Claude Code")
        expect(harnesses.first).to_have_class(re.compile("chosen"))
        expect(menu.locator("[role=menuitem][data-cli=dsh]")).to_have_count(1)
        # The way back is the level's own name, over its choices.
        menu.locator("[data-hmz=step-back]").click()
        expect(menu.locator("[data-hmz=step-harness]")).to_be_focused()
        # The models of the harness picked alone; as `-a` spells one where it is pointed at.
        menu.locator("[data-hmz=step-model]").click()
        models = menu.locator(".nous-list > [role=menuitem]")
        expect(models).to_have_text(["Haiku 4.5", "Opus 4.1"])
        expect(models.nth(0)).to_have_class(re.compile("chosen"))
        expect(models.nth(0)).to_be_focused()
        expect(models.nth(0)).to_have_attribute("data-tip", "claude/claude-haiku-4-5")
        expect(menu.get_by_role("menuitem", name="Refresh models")).to_be_enabled()
        # The left arrow goes back as well, and the keys alone pick: down to Model, in, down
        # to the next model, Enter.
        page.keyboard.press("ArrowLeft")
        expect(menu.locator("[data-hmz=step-model]")).to_be_focused()
        page.keyboard.press("ArrowRight")
        expect(models.nth(0)).to_be_focused()
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        expect(menu).to_have_count(0)
        expect(chip).to_have_text("Claude Code Opus 4.1 Default")

        chip.click()
        menu.locator("[data-hmz=step-effort]").click()
        efforts = menu.locator("[role=menuitem][data-value]")
        expect(efforts).to_have_text(
            ["Default", "Ultracode", "Max", "High", "Medium", "Low"]
        )
        efforts.nth(2).click()
        expect(chip).to_have_text("Claude Code Opus 4.1 Max")
        expect(chip).to_have_attribute("data-agent", "claude/claude-opus-4-1:max")

        # A harness picked again starts from what was last picked of it, and its model is next.
        chip.click()
        menu.locator("[data-hmz=step-harness]").click()
        menu.locator("[role=menuitem][data-cli=dsh]").click()
        expect(menu.locator("[data-hmz=step-back]")).to_have_text("Model")
        expect(chip).to_have_attribute("data-agent", re.compile(r"^dsh/"))
        menu.locator("[data-hmz=step-back]").click()
        menu.locator("[data-hmz=step-harness]").click()
        menu.locator("[role=menuitem][data-cli=claude]").click()
        expect(chip).to_have_attribute("data-agent", "claude/claude-opus-4-1:max")
        # A model no CLI lists is typed, and Enter there sends nothing.
        typed = menu.locator("[data-hmz=pick-model-typed]")
        typed.fill("claude-sonnet-4-5")
        typed.press("Enter")
        expect(menu).to_have_count(0)
        expect(page).to_have_url(re.compile(r"#/new/chat"))
        expect(chip).to_have_text("Claude Code Sonnet 4.5 Default")
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
        expect(chip).to_have_text("Pick a nous")
        chip.click()
        menu = page.get_by_role("menu", name="Nous")
        expect(menu.locator(".hint")).to_contain_text("claude is not answering")
        menu.locator("[data-hmz=step-model]").click()
        menu.locator("[data-hmz=pick-model-typed]").fill("claude-sonnet-4-5")
        expect(chip).to_have_text("Claude Code Sonnet 4.5 Default")
        expect(chip).to_have_attribute("data-agent", "claude/claude-sonnet-4-5")


def test_a_chat_says_its_model_on_the_chip_of_its_box(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new/chat")
        chip = page.locator("[data-role=assistant] [data-hmz=pick-model]")
        chip.click()
        page.locator(".model-menu [data-hmz=step-model]").click()
        page.locator(".model-menu [data-value=claude-opus-4-1]").click()
        page.locator("[data-hmz=composer-text]").fill("which model are you")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        said = page.locator("[data-hmz=say] [data-hmz=chat-model]")
        expect(said).to_have_text("Claude Code Opus 4.1 Default")
        said.click()
        about = page.get_by_role("menu", name="Nous")
        # The parts of its agent, a level a line in the order a new chat picks them.
        expect(about.locator(".model-fact, .choice.step")).to_have_text(
            [
                "HarnessClaude Code",
                "AccountLocal",
                re.compile(r"^ModelOpus 4\.1$"),
                re.compile(r"^EffortDefault$"),
            ]
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
        # menu, a button for each pane and, as every view's, Ai-chan's at its end, and its
        # panel says what it is in a chat's words.
        expect(bar.locator(".bar-actions button")).to_have_count(6)
        expect(bar.locator(".bar-actions > *").last).to_have_attribute(
            "data-hmz", "aichan-toggle"
        )
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
            ["Chat ID", "Saved at", "Folder", "Started", "Nous"]
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


#: Every theme Humanize comes with: its own, then twelve more, each named for a mood and its
#: colour.
_PRESETS = [
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


def _kept(page: Page, name: str) -> str | None:
    """What the browser keeps under a name; None where it keeps nothing."""
    return page.evaluate("(name) => localStorage.getItem(name)", name)


def test_a_theme_is_chosen_whole_and_under_auto_the_system_says_which_side_is_shown(
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
        presets = page.locator("[data-hmz=presets] [data-hmz=theme]")
        expect(presets.locator(".theme-name b")).to_have_text(_PRESETS)
        # Each is drawn as its two sides, and no row picks one of them: nothing is copied or
        # written out from the list. Which side is shown is one choice for them all, Auto
        # where none was made.
        expect(presets.locator(".theme-swatch")).to_have_count(2 * len(_PRESETS))
        expect(presets.locator("button")).to_have_text(["Use"] * len(_PRESETS))
        expect(page.locator("[data-hmz=theme-mode] button")).to_have_text(
            ["Auto", "Light", "Dark"]
        )
        expect(page.locator("[data-hmz=theme-mode] [aria-pressed=true]")).to_have_text(
            "Auto"
        )
        assert _kept(page, "hmz-mode") is None
        expect(page.locator("[data-hmz=presets] select")).to_have_count(0)
        custom = page.locator("[data-hmz=custom]")
        expect(custom.locator("h2")).to_have_text("Custom")
        expect(custom.locator("header button")).to_have_text(["New", "Import"])
        expect(custom.locator("p")).to_have_text("No custom themes yet.")
        expect(custom.locator("select")).to_have_count(0)

        # Humanize's own is in use where none was chosen.
        own = page.locator("[data-hmz=theme][data-key=humanize]")
        expect(own).to_have_class(re.compile("chosen"))
        expect(own.locator(".theme-name .dim")).to_have_text("In use")
        expect(own.get_by_role("button", name="Use")).to_be_disabled()

        lilac = page.locator("[data-hmz=theme][data-key=peaceful-lilac]")
        lilac.get_by_role("button", name="Use").click()
        expect(lilac).to_have_class(re.compile("chosen"))
        expect(own).not_to_have_class(re.compile("chosen"))
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        _painted(page, "--paper", "#f7f2f7")
        page.emulate_media(color_scheme="dark")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        _painted(page, "--paper", "#151019")
        assert _kept(page, "hmz-pair") == "peaceful-lilac"
        # Opened again, the theme is painted before the page is drawn.
        again = page.context.new_page()
        again.emulate_media(color_scheme="dark")
        again.goto(site.address)
        assert _paints(again, "--paper") == "#151019"
        again.close()

        # What a right click offers is the theme, whole.
        lilac.click(button="right", position={"x": 300, "y": 20})
        expect(page.locator(".popover.context [role=menuitem]")).to_have_text(["Use"])
        page.keyboard.press("Escape")
        own.get_by_role("button", name="Use").click()
        expect(own).to_have_class(re.compile("chosen"))
        assert _kept(page, "hmz-pair") is None
        assert page.evaluate("document.documentElement.style.length") == 0


def test_a_theme_is_made_of_the_one_in_use_written_out_and_read_back(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/themes")
        custom = page.locator("[data-hmz=custom] [data-hmz=theme]")
        expect(custom).to_have_count(0)
        pink = page.locator("[data-hmz=theme][data-key=devoted-pink]")
        pink.get_by_role("button", name="Use").click()
        _painted(page, "--paper", "#fdf6f5")

        # New copies both sides of the theme in use, and opens the side the system shows.
        page.get_by_role("button", name="New", exact=True).click()
        editor = page.locator("[data-hmz=theme-editor]")
        expect(editor).to_be_visible()
        side = page.locator("[data-hmz=theme-side]")
        expect(side.locator("button")).to_have_text(["Light", "Dark"])
        expect(side.locator("[aria-pressed=true]")).to_have_text("Light")
        expect(page.locator("[data-hmz=theme-base]")).to_have_count(0)
        expect(page.locator("[data-hmz=theme-name]")).to_have_value("New theme")
        expect(page.locator("[data-hmz=colour-paper]")).to_have_value("#fdf6f5")
        page.locator("[data-hmz=theme-name]").fill("Dusk")
        page.locator("[data-hmz=colour-paper]").fill("#fff8e0")
        page.locator("[data-hmz=colour-control]").fill("not a colour")
        expect(page.locator("[data-hmz=colour-control]")).to_have_attribute(
            "aria-invalid", "true"
        )
        # Shown on the page as it is changed, while it is edited.
        assert _paints(page, "--paper") == "#fff8e0"
        side.get_by_role("button", name="Dark").click()
        expect(side.locator("[aria-pressed=true]")).to_have_text("Dark")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        expect(page.locator("[data-hmz=theme-name]")).to_have_value("Dusk")
        page.locator("[data-hmz=colour-paper]").fill("#201008")
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
        _painted(page, "--paper", "#fdf6f5")
        dusk = custom.filter(has_text="Dusk")
        expect(dusk.locator(".theme-swatch")).to_have_count(2)
        # It is written out where it is edited, and nowhere else.
        expect(dusk.locator(".row").locator("button, a")).to_have_text(
            ["Use", "Edit", "Delete"]
        )
        dusk.get_by_role("link", name="Edit").click()
        with page.expect_download() as saving:
            editor.get_by_role("button", name="Export").click()
        saved = saving.value
        assert saved.suggested_filename == "Dusk.hmztheme"
        written = json.loads(Path(saved.path()).read_text())
        assert sorted(written) == ["dark", "hmztheme", "light", "name"]
        assert written["name"] == "Dusk"
        assert written["light"]["colors"]["paper"] == "#fff8e0"
        assert written["dark"]["colors"]["paper"] == "#201008"
        assert written["dark"]["images"]["page"]["data"].startswith("data:image/svg")
        page.get_by_role("link", name="Done").click()

        dusk.get_by_role("button", name="Delete").click()
        _answer(dusk, "Delete Dusk?", "Delete")
        expect(custom).to_have_count(0)
        page.locator("[data-hmz=theme-file]").set_input_files(
            {
                "name": "Dusk.hmztheme",
                "mimeType": "application/json",
                "buffer": json.dumps(written).encode(),
            }
        )
        expect(dusk).to_have_count(1)
        dusk.get_by_role("button", name="Use").click()
        expect(dusk).to_have_class(re.compile("chosen"))
        _painted(page, "--paper", "#fff8e0")
        page.emulate_media(color_scheme="dark")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        _painted(page, "--paper", "#201008")
        _painted(page, "--page-image", "data:image/svg+xml")
        # Where motion is asked to be reduced, the picture is held as it is first drawn.
        page.emulate_media(reduced_motion="reduce")
        _painted(page, "--page-image", "data:image/png")
        # Opened again, it is painted before the page is drawn.
        again = page.context.new_page()
        again.emulate_media(color_scheme="dark")
        again.goto(site.address)
        assert again.evaluate("document.documentElement.dataset.theme") == "dark"
        assert _paints(again, "--paper") == "#201008"
        again.close()

        # Deleted while in use, Humanize's own is shown instead.
        dusk.get_by_role("button", name="Delete").click()
        _answer(dusk, "Delete Dusk?", "Delete")
        expect(custom).to_have_count(0)
        expect(page.locator("[data-hmz=theme][data-key=humanize]")).to_have_class(
            re.compile("chosen")
        )
        assert _kept(page, "hmz-pair") is None


def test_the_side_shown_is_the_one_chosen_and_under_auto_the_systems(
    project: Path, engine: str, tmp_path: Path
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/themes")
        mode = page.locator("[data-hmz=theme-mode]")
        pressed = mode.locator("[aria-pressed=true]")
        root = page.locator("html")
        page.locator("[data-hmz=theme][data-key=peaceful-lilac]").get_by_role(
            "button", name="Use"
        ).click()
        _painted(page, "--paper", "#f7f2f7")

        # Dark is drawn at once, where the system is light, and stays whatever the system says.
        mode.get_by_role("button", name="Dark").click()
        expect(pressed).to_have_text("Dark")
        expect(root).to_have_attribute("data-theme", "dark")
        _painted(page, "--paper", "#151019")
        assert _kept(page, "hmz-mode") == "dark"
        assert _kept(page, "hmz-pair") == "peaceful-lilac"
        for scheme in ("dark", "light"):
            page.emulate_media(color_scheme=scheme)
            page.wait_for_timeout(150)
            expect(root).to_have_attribute("data-theme", "dark")
            assert "#151019" in _paints(page, "--paper")
            # The mark's chevron is in the ink of the side shown, whatever the system's is,
            # and its wedge in the theme's green.
            chevron, ink, wedge, green = page.evaluate(
                """() => {
                    const mark = document.querySelector('.side-top .brand-mark')
                    const probe = document.createElement('i')
                    document.body.append(probe)
                    const painted = (token) => {
                        probe.style.color = `var(${token})`
                        return getComputedStyle(probe).color
                    }
                    const fill = (part) => getComputedStyle(mark.querySelector(part)).fill
                    const said = [fill('.ink'), painted('--ink')]
                    said.push(fill('.green'), painted('--green'))
                    probe.remove()
                    return said
                }"""
            )
            assert chevron == ink != "rgb(20, 26, 31)"
            assert wedge == green
            page.screenshot(path=str(tmp_path / f"mark-dark-on-{scheme}.png"))

        # Another theme used is drawn on the same side.
        page.locator("[data-hmz=theme][data-key=devoted-pink]").get_by_role(
            "button", name="Use"
        ).click()
        _painted(page, "--paper", "#1a1016")
        expect(root).to_have_attribute("data-theme", "dark")
        expect(pressed).to_have_text("Dark")

        # Light, where the system is dark.
        page.emulate_media(color_scheme="dark")
        mode.get_by_role("button", name="Light").click()
        expect(pressed).to_have_text("Light")
        expect(root).to_have_attribute("data-theme", "light")
        _painted(page, "--paper", "#fdf6f5")
        assert _kept(page, "hmz-mode") == "light"
        page.emulate_media(color_scheme="light")
        page.emulate_media(color_scheme="dark")
        page.wait_for_timeout(150)
        expect(root).to_have_attribute("data-theme", "light")

        # Opened again, the side chosen is painted before the page is drawn, and another page
        # this browser has open follows the choice made here.
        again = page.context.new_page()
        again.emulate_media(color_scheme="dark")
        again.goto(site.address)
        assert again.evaluate("document.documentElement.dataset.theme") == "light"
        assert "#fdf6f5" in _paints(again, "--paper")

        # Auto keeps nothing, and follows the system as it changes.
        mode.get_by_role("button", name="Auto").click()
        expect(pressed).to_have_text("Auto")
        assert _kept(page, "hmz-mode") is None
        _painted(page, "--paper", "#1a1016")
        expect(root).to_have_attribute("data-theme", "dark")
        _painted(again, "--paper", "#1a1016")
        again.close()
        page.emulate_media(color_scheme="light")
        expect(root).to_have_attribute("data-theme", "light")
        _painted(page, "--paper", "#fdf6f5")
        page.emulate_media(color_scheme="dark")
        expect(root).to_have_attribute("data-theme", "dark")

        # A theme of one's own is opened on the side shown, not the system's.
        mode.get_by_role("button", name="Light").click()
        page.locator("[data-hmz=custom]").get_by_role("button", name="New").click()
        expect(page.locator("[data-hmz=theme-side] [aria-pressed=true]")).to_have_text(
            "Light"
        )


#: What an earlier Humanize kept in a browser: a theme of one side, a dark alone, shown where
#: the system is dark, and the light of a preset where it is light. Kept once: the page it is
#: kept for is the first this browser opens.
_EARLIER = """
if (!localStorage.getItem('seeded')) {
  localStorage.setItem('seeded', '1')
  localStorage.setItem('hmz-themes', JSON.stringify([
    { id: 'tnight', name: 'Night', base: 'dark', colors: { paper: '#102030' }, images: {} },
  ]))
  localStorage.setItem('hmz-theme-light', 'hateful-silver-light')
  localStorage.setItem('hmz-theme-dark', 'tnight')
}
"""


def test_what_an_earlier_version_kept_is_kept_as_themes_of_two_sides(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine, init=_EARLIER) as page:
        go(page, "/settings/themes")
        custom = page.locator("[data-hmz=custom] [data-hmz=theme]")
        # The theme of one side has both now, and the two picked apart are one theme, in use.
        expect(custom.locator(".theme-name b")).to_have_text(["Night", "Custom"])
        expect(custom.locator(".theme-swatch")).to_have_count(4)
        mixed = custom.filter(has_text="Custom")
        expect(mixed).to_have_class(re.compile("chosen"))
        silver = page.locator("[data-hmz=theme][data-key=hateful-silver]")
        paper = silver.locator(".theme-swatch").first.evaluate(
            "(one) => one.style.getPropertyValue('--paper')"
        )
        assert paper.startswith("#")
        _painted(page, "--paper", paper)
        page.emulate_media(color_scheme="dark")
        _painted(page, "--paper", "#102030")
        for gone in ("hmz-theme", "hmz-theme-light", "hmz-theme-dark"):
            assert _kept(page, gone) is None
        assert (_kept(page, "hmz-pair") or "").startswith("p")
        # Night's other side sets nothing: used where the system is light, it is Humanize's own.
        page.emulate_media(color_scheme="light")
        night = custom.filter(has_text="Night")
        night.get_by_role("button", name="Use").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        assert page.evaluate("document.documentElement.style.length") == 0
        page.emulate_media(color_scheme="dark")
        _painted(page, "--paper", "#102030")
        page.emulate_media(color_scheme="light")

        # One side chosen outright, whatever the system was: its theme is chosen, and that
        # side of it stays the one shown.
        page.evaluate(
            """() => {
              localStorage.removeItem('hmz-pair')
              localStorage.setItem('hmz-theme', 'devoted-pink-dark')
            }"""
        )
        page.reload()
        _painted(page, "--paper", "#1a1016")
        assert _kept(page, "hmz-pair") == "devoted-pink"
        assert _kept(page, "hmz-mode") == "dark"
        assert _kept(page, "hmz-theme") is None
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        go(page, "/settings/themes")
        expect(page.locator("[data-hmz=theme-mode] [aria-pressed=true]")).to_have_text(
            "Dark"
        )
        page.locator("[data-hmz=theme-mode]").get_by_role("button", name="Auto").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "light")

        # A file an earlier version wrote for one side is read as a theme of two.
        go(page, "/settings/themes")
        page.locator("[data-hmz=theme-file]").set_input_files(
            {
                "name": "Solo.hmztheme",
                "mimeType": "application/json",
                "buffer": json.dumps(
                    {
                        "hmztheme": 1,
                        "name": "Solo",
                        "base": "dark",
                        "colors": {"paper": "#0a0b0c", "nothing": "#fff"},
                    }
                ).encode(),
            }
        )
        expect(page.locator(".toast")).to_have_text("Imported Solo")
        solo = custom.filter(has_text="Solo")
        expect(solo.locator(".theme-swatch")).to_have_count(2)
        solo.get_by_role("button", name="Use").click()
        assert page.evaluate("document.documentElement.style.length") == 0
        page.emulate_media(color_scheme="dark")
        _painted(page, "--paper", "#0a0b0c")


def test_a_file_that_is_not_a_theme_is_refused(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/themes")
        page.locator("[data-hmz=theme-file]").set_input_files(
            {"name": "x.hmztheme", "mimeType": "application/json", "buffer": b"{}"}
        )
        expect(page.locator(".toast")).to_have_text("This is not a theme file")
        expect(page.locator("[data-hmz=custom] [data-hmz=theme]")).to_have_count(0)


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
    # The user's own `talk`, on offer whatever the workspace, beside the project's.
    mine = Path.home() / ".hmz" / "flows" / "talk"
    mine.mkdir(parents=True)
    (mine / "__init__.py").write_text(_TALK)
    with served() as site, opened(site, engine=engine) as page:
        # Flows is the daemon's and no folder's: it names and picks no workspace, and lists
        # no project's own flows.
        page.get_by_role("link", name="Flows").click()
        card = page.locator(".card[data-flow='@user/talk']")
        expect(card).to_be_visible()
        expect(page.locator("[data-hmz=workspace-picker]")).to_have_count(0)
        expect(page.locator(".card[data-flow='@local/talk']")).to_have_count(0)
        # A workspace an address names is left out of the page and of its address.
        go(page, f"/flows?workspace={site.here}")
        expect(card).to_be_visible()
        expect(page.locator("[data-hmz=bar] .bar-sub")).to_have_count(0)
        expect(page.locator(".card[data-flow='@local/talk']")).to_have_count(0)
        page.wait_for_url(lambda url: "workspace" not in url)
        # No flow is marked a default, and none is copied into a folder.
        expect(
            page.locator("[data-hmz=flows] .node-tag", has_text="Default")
        ).to_have_count(0)
        card.click(button="right")
        menu = page.locator(".popover.context")
        expect(menu.get_by_role("menuitem", name="New epic")).to_be_visible()
        expect(menu.get_by_role("menuitem", name="Copy here")).to_have_count(0)
        page.keyboard.press("Escape")
        card.click()
        expect(page.locator(".flow-detail h2")).to_have_text("@user/talk")
        # What it says of the flow names no folder the page is on: it is on none.
        facts = page.locator(".flow-detail .facts")
        expect(facts).to_contain_text("workspace (the folder the epic runs in)")
        expect(facts).not_to_contain_text("this directory")
        expect(facts.locator("dt", has_text="resumable").locator("+ dd")).to_have_text(
            re.compile("^(yes|no)$")
        )
        expect(
            page.locator(".flow-detail").get_by_role("button", name="Copy here")
        ).to_have_count(0)
        page.get_by_role("link", name="New epic").last.click()
        expect(page.locator("[data-hmz=flow-picker] b")).to_have_text("@user/talk")


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
    # How far across they reach, at most, and how high the row they stand in is.
    lights = 76
    row = 44
    clicked = "a, button, input, select, textarea, summary, [role=tab]"
    # What can be clicked where they stand, the window's left 76 pixels and its top 44: what is
    # drawn there, every 4 pixels.
    under = (
        "(() => { const found = new Set(); for (let x = 0; x < 76; x += 4) for (let y = 0;"
        " y < 44; y += 4) { const el = document.elementFromPoint(x, y)?.closest('a, button,"
        " input, select, textarea, summary, [role=tab]'); if (el) found.add(el.outerHTML"
        ".slice(0, 80)) } return [...found] })()"
    )

    def box(page: Page, selector: str) -> dict[str, float]:
        found = page.locator(selector).first.bounding_box()
        assert found
        return {key: found[key] for key in ("x", "y", "width", "height")}

    def left(page: Page, selector: str) -> float:
        return box(page, selector)["x"]

    def top(page: Page, selector: str) -> float:
        return box(page, selector)["y"]

    def foot(page: Page, selector: str) -> float:
        found = box(page, selector)
        return found["y"] + found["height"]

    with served() as site, opened(site, engine=engine) as page:
        assert page.evaluate("document.documentElement.dataset.shell") is None
        expect(page.locator("[data-tauri-drag-region]")).to_have_count(0)
        assert left(page, ".brand") < lights
        assert top(page, ".brand") < row
        assert page.evaluate(under) != []

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
        # One row across the window, the lights in it: the sidebar's title row and the bar over
        # the view are as high, their feet on one line, and the first entry stands under it.
        assert top(page, ".side-top") == 0
        assert foot(page, ".side-top") == row
        assert top(page, "[data-hmz=bar]") == 0
        assert foot(page, "[data-hmz=bar]") == row
        assert top(page, ".side-nav a") >= row
        # What hides the sidebar stands straight after them, and the mark, which they took the
        # place of, at the row's far end: in the row's middle, as far from the sidebar's edge
        # as it stands from it in a browser.
        assert left(page, ".side-fold") >= lights
        assert left(page, ".brand") > left(page, ".side-forward")
        assert page.evaluate(
            "document.querySelector('.side-top .brand').getBoundingClientRect().right"
        ) == page.evaluate(
            "(() => { const row = document.querySelector('.side-top');"
            " return row.getBoundingClientRect().right"
            " - parseFloat(getComputedStyle(row).paddingRight) })()"
        )
        mark = box(page, ".side-top .brand .brand-mark")
        side = box(page, "[data-hmz=sidebar] .side-top")
        assert (mark["width"], mark["height"]) == (24, 24)
        assert mark["y"] == row - mark["y"] - mark["height"] == 10
        assert side["x"] + side["width"] - mark["x"] - mark["width"] == 16
        for one in ("[data-hmz=sidebar] .side-top", "[data-hmz=bar]"):
            expect(page.locator(one)).to_have_attribute(
                "data-tauri-drag-region", "deep"
            )
        # Nothing but the rows moves the window: no strip is kept over the view.
        expect(page.locator("[data-hmz=page]")).not_to_have_attribute(
            "data-tauri-drag-region", re.compile("")
        )
        expect(page.locator(f":is({clicked})[data-tauri-drag-region]")).to_have_count(0)
        assert page.evaluate(under) == []
        # A menu opened in a row is not what the window is dragged by.
        page.locator("[data-hmz=daemon-bar]").click()
        expect(page.locator("[role=menu]")).to_have_attribute(
            "data-tauri-drag-region", "false"
        )
        page.keyboard.press("Escape")

        # The sidebar hidden, the bar is the top left: no higher, and what shows the sidebar
        # stands straight after them.
        page.locator(".side-fold").click()
        assert top(page, "[data-hmz=bar]") == 0
        assert foot(page, "[data-hmz=bar]") == row
        assert left(page, "[data-hmz=bar] .bar-side") >= lights
        assert page.evaluate(under) == []
        # Full screen, where they are gone, it is drawn as in a browser.
        page.evaluate(
            "document.documentElement.toggleAttribute('data-fullscreen', true)"
        )
        assert left(page, "[data-hmz=bar] .bar-side") < lights
        assert page.evaluate(under) != []
        page.evaluate(
            "document.documentElement.toggleAttribute('data-fullscreen', false)"
        )

        # A narrow window: the bar, the sidebar drawn over it, and a dialog that fills it.
        page.set_viewport_size({"width": 700, "height": 800})
        assert top(page, "[data-hmz=bar]") == 0
        assert left(page, "[data-hmz=bar] .bar-side") >= lights
        assert page.evaluate(under) == []
        page.locator("[data-hmz=bar] .bar-side").click()
        expect(page.locator("[data-hmz=sidebar]")).to_be_in_viewport(ratio=1)
        assert left(page, ".side-fold") >= lights
        assert page.evaluate(under) == []
        page.keyboard.press("Escape")
        page.keyboard.press("Meta+k")
        expect(page.locator("[data-hmz=dialog-search]")).to_be_visible()
        assert top(page, "[data-hmz=dialog-search]") == 0
        assert page.evaluate(under) == []
        go(page, "/settings/general")
        expect(page.locator("[data-hmz=settings-general]")).to_be_visible()
        assert top(page, ".settings-nav") == 0
        assert page.evaluate(under) == []


def test_in_the_app_the_window_is_moved_by_its_top_while_something_is_over_the_page(
    project: Path, engine: str
) -> None:
    """A dialog's scrim, or a drawer's, covers the top row: a strip over it moves the window."""
    # What a press at a point of the window lands on: the strip, as what moves the window says
    # it; what is shown over the page; or the class of whatever else is there.
    at = (
        "([x, y]) => { const el = document.elementFromPoint(x, y); return"
        " el?.dataset.hmz === 'window-strip' ? `strip:${el.getAttribute("
        "'data-tauri-drag-region')}` : el?.closest('.dialog, dialog, .sidebar') ? 'shown'"
        " : el?.className }"
    )
    strip = "[data-hmz=window-strip]"

    # A browser's window has a title bar: nothing is put over the scrim.
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/general")
        expect(page.locator("[data-hmz=settings-general]")).to_be_visible()
        expect(page.locator(strip)).to_have_count(0)
        assert page.evaluate(at, [640, 10]) == "dialog-scrim"

    with served() as site, opened(site, engine=engine, user_agent=_APP) as page:
        # Nothing over the page, nothing but its rows moves the window.
        expect(page.locator(f"{strip}:visible")).to_have_count(0)
        go(page, "/settings/general")
        expect(page.locator("[data-hmz=settings-general]")).to_be_visible()
        # Across the whole top of the window, the lights' room and the far corner included,
        # 44 high and no higher: under it the scrim is pressed, which closes the dialog.
        for x in (4, 200, 640, 1276):
            assert page.evaluate(at, [x, 4]) == "strip:"
            assert page.evaluate(at, [x, 43]) == "strip:"
        assert page.evaluate(at, [4, 45]) == "dialog-scrim"
        # The dialog is over the strip, and what is in it is pressed as ever.
        page.locator(".settings-nav a[href$='/settings/themes']").click()
        expect(page.locator("[data-hmz=settings-themes]")).to_be_visible()
        assert page.evaluate(at, [640, 4]) == "strip:"

        # A dialog of the browser's own, whose backdrop is over all of that, brings its own.
        page.evaluate(
            "import('/layers.js').then(({ modal }) => { const asked = document"
            ".createElement('dialog'); asked.id = 'asked'; asked.append('Sure?');"
            " document.body.append(asked); modal(asked) })"
        )
        expect(page.locator("#asked")).to_be_visible()
        expect(page.locator(f"#asked > {strip}")).to_have_count(1)
        for x in (4, 640, 1276):
            assert page.evaluate(at, [x, 4]) == "strip:"
        assert page.evaluate(at, [4, 45]) == "shown"
        page.keyboard.press("Escape")
        expect(page.locator("#asked")).to_be_hidden()

        # However low the window, at the app's own size and under it, the dialog keeps clear
        # of the top row: all of the row moves the window, over the dialog's width too.
        for height in (820, 800, 700, 300):
            page.set_viewport_size({"width": 1280, "height": height})
            for x in (4, 400, 640, 900, 1276):
                assert page.evaluate(at, [x, 4]) == "strip:", (height, x)
                assert page.evaluate(at, [x, 43]) == "strip:", (height, x)
            assert page.evaluate(at, [640, 45]) == "shown", height
        page.locator("[data-hmz=dialog-settings]").get_by_role(
            "button", name="Close"
        ).click()
        expect(page.locator("[data-hmz=dialog-settings]")).to_have_count(0)
        expect(page.locator(f"{strip}:visible")).to_have_count(0)

        # A narrow window, the sidebar a drawer over the page: beside it, over its scrim.
        page.set_viewport_size({"width": 700, "height": 800})
        page.locator("[data-hmz=bar] .bar-side").click()
        expect(page.locator("[data-hmz=sidebar]")).to_be_in_viewport(ratio=1)
        assert page.evaluate(at, [690, 4]) == "strip:"
        assert page.evaluate(at, [690, 45]) == "scrim"
        assert page.evaluate(at, [100, 4]) == "shown"
        page.locator("[data-hmz=scrim]").click(position={"x": 690, "y": 400})
        expect(page.locator(f"{strip}:visible")).to_have_count(0)


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
        # The shortcuts as Windows writes them: a key apiece, in the row's own face, in no box,
        # each row's ending where the other's does.
        expect(page.locator(".side-keys")).to_have_text(["Ctrl+Shift+O", "Ctrl+K"])
        expect(page.locator(".side-keys kbd")).to_have_text(
            ["Ctrl", "Shift", "O", "Ctrl", "K"]
        )
        assert page.evaluate(
            "(() => { const keys = [...document.querySelectorAll('.side-keys')], style ="
            " getComputedStyle(keys[0]); return !/mono/i.test(style.fontFamily) &&"
            " style.fontSize === '12px' && style.borderTopWidth === '0px' && new Set(keys.map("
            "(el) => Math.round(el.getBoundingClientRect().right))).size === 1 })()"
        )
        expect(page.get_by_role("link", name="New chat", exact=True)).to_have_attribute(
            "aria-keyshortcuts", "Control+Shift+O"
        )
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
        folder = (f"/workspace/{one}" for one in ("setup", "usage", "archived"))
        for address in (_NEW, "/flows", "/search", *settings, *folder):
            go(page, address)
            page.wait_for_timeout(300)
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
def test_a_setup_is_kept_by_starting_an_epic_and_by_nothing_else(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, _NEW)
        _options(page)
        chip = page.locator("[data-role=assistant] [data-hmz=pick-model]")
        expect(chip).to_have_text("Claude Code Haiku 4.5 Default")
        chip.click()
        nous = page.get_by_role("menu", name="Nous")
        nous.locator("[data-hmz=step-model]").click()
        nous.locator("[data-value=claude-opus-4-1]").click()
        expect(chip).to_have_text("Claude Code Opus 4.1 Default")
        # Nothing saves it but a start: the form holds no Save.
        expect(page.get_by_role("button", name="Save")).to_have_count(0)
        page.reload()
        go(page, _NEW)
        expect(chip).to_have_text("Claude Code Haiku 4.5 Default")
        expect(page.get_by_label("Most it may cost, in dollars")).to_have_value("")

        # Started with, it is what a new epic of that flow opens on there.
        _options(page)
        chip.click()
        nous = page.get_by_role("menu", name="Nous")
        nous.locator("[data-hmz=step-model]").click()
        nous.locator("[data-value=claude-opus-4-1]").click()
        page.locator("[data-hmz=composer-text]").fill("keep this")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(_EPIC)
        stop(page)
        go(page, _NEW)
        expect(chip).to_have_text("Claude Code Opus 4.1 Default")
        expect(page.get_by_label("Most it may cost, in dollars")).to_have_value("5")


@pytest.mark.usefixtures("talking")
def test_a_start_with_nothing_bounding_it_is_refused_where_the_budget_is_set(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, _NEW)
        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_text("Claude Code Haiku 4.5 Default")
        page.locator("[data-hmz=composer-text]").fill("spend what you like")
        page.locator("[data-hmz=composer-text]").press("Enter")
        expect(page.locator("[data-hmz=start] .composer-said")).to_contain_text(
            "Set at least one limit of the budget."
        )
        # The keys are where what is missing is set.
        expect(page.get_by_label("Most it may cost, in dollars")).to_be_focused()
        assert "#/new" in page.url


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
        ).to_have_attribute("data-value", "claude-haiku-4-5")
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
        ).to_have_text("Claude Code Haiku 4.5 Default")
        flow.check()
        page.locator("[data-hmz=composer-text]").fill("profile the flow")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(_EPIC)
        (said,) = wire.params("epic.start")
        assert (said["profile_flow"], said["profile_environment"]) == (True, False)
        stop(page)
        # Kept by the start, each apart.
        page.reload()
        go(page, _NEW)
        expect(flow).to_be_checked()
        expect(environment).not_to_be_checked()
        environment.check()

        page.locator("[data-hmz=composer-text]").fill("profile me")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(_EPIC)
        *_, said = wire.params("epic.start")
        assert (said["profile_flow"], said["profile_environment"]) == (True, True)
        stop(page)


@pytest.mark.usefixtures("talking")
def test_an_epic_is_read_by_its_agents_logs_and_its_agents_as_a_list(
    engine: str,
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        _start_talk(page, "log me")

        inspector = page.locator("[data-hmz=inspector]")
        expect(inspector.locator("[data-hmz=spending]")).to_contain_text("Haiku 4.5")
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
        _answer(page, "Stop this epic?", "Stop")


@pytest.mark.usefixtures("talking")
def test_an_ended_epic_is_exported_and_its_address_copied(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        # A flow's epic: a chat is no epic, and is not exported.
        _start_talk(page, "keep me")
        stop(page)

        # What is done to an ended epic is in its bar.
        actions = page.locator("[data-hmz=bar]")
        with page.expect_download() as saving:
            actions.get_by_role("button", name="Export").click()
        saved = saving.value
        assert saved.suggested_filename.endswith(".hmzepic")
        assert Path(saved.path()).read_bytes()[:2] == b"\x1f\x8b"

        # WebKit lets a click write unasked, and knows no permission to write by.
        writes = ["clipboard-write"] if engine == "chromium" else []
        page.context.grant_permissions(["clipboard-read", *writes])
        actions.get_by_role("button", name="Copy link").click()
        expect(actions.get_by_role("button", name="Copied")).to_be_visible()
        assert page.evaluate("navigator.clipboard.readText()") == page.url


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
        ).to_have_attribute("data-value", "claude-haiku-4-5")
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

        # A flow's epic, it opens on its graph, and is listed.
        page.wait_for_url(re.compile(rf".*#/epics/{re.escape(name)}"))
        expect(page.locator("[data-hmz=graph]")).to_be_visible()
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
        # What it works in said whole, with no session or role named before it, its path
        # under it, whole on hover.
        works = inspector.locator("[data-hmz=environments] li")
        expect(works).to_have_count(1)
        expect(works).to_contain_text("local")
        expect(works).not_to_contain_text(re.compile(r"\w+/1|assistant"))
        expect(works.locator(".path")).to_have_attribute(
            "title", re.compile(rf"{re.escape(project.name)}$")
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


def _slow_asides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Makes a side question that says `slowly` take long enough to be seen answering."""
    from hmz.runtime.watching.btw import Btw, FlowSnapshot

    asks = Btw.ask

    def slowly(self: Btw, question: str, snapshot: FlowSnapshot) -> str:
        if "slowly" in question:
            time.sleep(3)
        return asks(self, question, snapshot)

    monkeypatch.setattr(Btw, "ask", slowly)


def test_a_side_question_about_a_chat_names_no_session_and_picks_none(
    project: Path, engine: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _slow_asides(monkeypatch)
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "remember papaya")
        expect(page.locator("[data-hmz=thread]")).to_contain_text(
            "did: remember papaya"
        )
        _side_questions(page)
        aside = page.locator("[data-hmz=btw]")
        ask = page.locator("[data-hmz=btw-to]")
        tabs = page.locator("[data-hmz=btw-tab]")
        log = page.locator("[data-hmz=btw-log]")

        # A chat is one conversation: nothing to pick, and it is asked at once.
        expect(ask).to_be_hidden()
        expect(tabs).to_have_text(["New question"])
        aside.locator("textarea").fill("what now")
        aside.locator("textarea").press("Enter")
        expect(log.locator(".said.btw")).to_have_count(1)
        expect(aside).not_to_contain_text("Pick the conversation")
        expect(ask).to_be_hidden()
        # The side conversation goes by what it first asked, and names no session.
        expect(tabs).to_have_text(["what now"])

        page.locator("[data-hmz=btw-new]").click()
        expect(ask).to_be_hidden()
        aside.locator("textarea").fill("and you, slowly")
        aside.locator("textarea").press("Enter")
        working = page.locator("[data-hmz=btw-working]")
        expect(working).to_have_text("Thinking…")
        expect(page.locator("[data-hmz=btw-tab].busy")).to_have_count(1)
        expect(log.locator(".said.btw")).to_have_count(1)
        expect(working).to_have_count(0)
        expect(tabs).to_have_text(["what now", "and you, slowly"])
        # Nor does what was asked say whom it was asked of.
        expect(log.locator(".said.you .body")).to_have_text("and you, slowly")
        expect(log.locator(".said.you .who")).to_have_count(0)

        # Opened again, both are read back, each with what was said in it.
        page.reload()
        _side_questions(page)
        expect(tabs).to_have_text(["what now", "and you, slowly"])
        expect(log).to_contain_text("and you, slowly")
        tabs.first.click()
        expect(log).to_contain_text("what now")
        expect(log.locator(".said.you .body")).to_have_text("what now")
        page.locator("[data-hmz=btw-close]").click()
        expect(tabs).to_have_count(1)
        stop(page)


@pytest.mark.usefixtures("talking")
def test_asides_each_ask_one_picked_at_their_start_and_say_while_they_answer(
    project: Path, engine: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _slow_asides(monkeypatch)
    with served() as site, opened(site, engine=engine) as page:
        _start_talk(page, "remember papaya")
        page.get_by_role("tab", name="Aside").click()
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
        # Whom it asks is picked above the box, outside it, and covers none of it.
        above, box = ask.bounding_box(), aside.locator("textarea").bounding_box()
        assert above is not None
        assert box is not None
        assert above["y"] + above["height"] <= box["y"]
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
        task = drawer.locator("[data-hmz=aichan-say] textarea")
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
        _answer(page, "Stop this epic?", "Stop")
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
        assert box is not None
        assert box["height"] >= line
        # A chat has nobody to pick to ask: nothing stands in the box but what is typed.
        expect(page.locator("[data-hmz=btw] .ask-to")).to_have_count(0)
        expect(page.locator(".ask-to")).to_be_hidden()
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


@pytest.mark.usefixtures("talking")
def test_an_exported_epic_is_imported_by_picking_dropping_or_its_path(
    project: Path, tmp_path: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        # A flow's epic: a chat is no epic, and is not exported.
        _start_talk(page, "take me home")
        stop(page)
        found = re.search(r"#/epics/([^/]+)", page.url)
        assert found is not None
        name = found[1]
        with page.expect_download() as saving:
            page.locator("[data-hmz=bar]").get_by_role("button", name="Export").click()
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
            "not resumable here: the workspace it ran in, /nowhere/at/all, is not"
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
        # A chat that answered and waits says nothing of it over its box; a flow's epic
        # says how it stands on its bar.
        expect(page.locator("[data-hmz=thread]")).to_contain_text("did: remember teal")
        status = page.locator("[data-hmz=chat-status]")
        expect(status).to_have_count(0)
        expect(page.locator("[data-hmz=dock]")).not_to_contain_text("Waiting for you")

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
        # Marked by a dot, as a row unread is, which says so to whoever cannot see it.
        expect(state).to_have_text("")
        expect(state).to_have_attribute("aria-label", "Awaiting input")
        expect(row).not_to_contain_text("Awaiting input")

        # Read, it is stopped: its row says nothing beside what was asked.
        row.click()
        expect(state).to_have_count(0)
        expect(status).to_have_count(0)


def test_a_chat_no_host_holds_opens_its_terminal_changes_and_files_and_is_said_to(
    project: Path, engine: str
) -> None:
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.name=Ada", "-c", "user.email=ada@example.com", *args],
            cwd=project,
            check=True,
            capture_output=True,
        )

    (project / "kept.txt").write_text("kept\n")
    git("init", "-q")
    git("add", "kept.txt")
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "one")
    (project / "kept.txt").write_text("kept\nand changed\n")
    with served() as site, opened(site, engine=engine) as page:
        _start_chat(page, "remember teal")
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("did: remember teal")
        name = page.url.rsplit("/", 1)[1]
        # Its host goes: an old chat, opened afresh.
        stop(page)
        page.reload()
        expect(thread).to_contain_text("did: remember teal")
        chat = _call(page, "chat.get", {"chat": name})
        assert (chat["slot"], chat["state"]) == ("", "resting")
        record = Path(chat["at"]) / "chat.jsonl"
        wrote = record.read_bytes()

        # Nothing says it is not going: its row and its box say nothing of how it
        # stands, its box is there, and every pane of it is offered.
        row = page.locator("[data-hmz=sidebar] [data-hmz=epic]", has_text="remember")
        expect(row.locator("[data-hmz=chat-state]")).to_have_count(0)
        expect(page.locator("[data-hmz=chat-status]")).to_have_count(0)
        expect(page.locator("[data-hmz=not-carried]")).to_have_count(0)
        say = page.locator("[data-hmz=say] textarea")
        expect(say).to_be_visible()
        bar = page.locator("[data-hmz=bar]")
        for pane in ("details", "terminal", "changes", "files"):
            button = bar.locator(f"[data-hmz=pane-{pane}]")
            expect(button).to_be_enabled()
            expect(button).to_have_attribute("title", pane.capitalize())

        # Its files: its folder is brought up with nothing said, and nothing written.
        bar.locator("[data-hmz=pane-files]").click()
        frame_ = page.locator("[data-hmz=inspector] [data-hmz=envs]")
        expect(frame_.locator("[data-hmz=envs-tab-files]")).to_have_attribute(
            "aria-selected", "true"
        )
        expect(frame_.locator("[data-hmz=files-tree]")).to_contain_text("kept.txt")
        expect(bar.locator("[data-hmz=pane-files]")).to_have_attribute(
            "aria-pressed", "true"
        )
        assert record.read_bytes() == wrote
        expect(thread).to_contain_text("did: remember teal")
        expect(row.locator("[data-hmz=chat-state]")).to_have_count(0)
        expect(page.locator("[data-hmz=chat-status]")).to_have_count(0)

        # Its changes, and a terminal in it.
        bar.locator("[data-hmz=pane-changes]").click()
        expect(
            frame_.locator("[data-hmz=change][data-path='kept.txt']")
        ).to_be_visible()
        bar.locator("[data-hmz=pane-terminal]").click()
        expect(frame_.locator("[data-hmz=term-host]").first).to_be_visible()
        for pane in ("terminal", "changes", "files"):
            expect(bar.locator(f"[data-hmz=pane-{pane}]")).to_be_enabled()
        assert record.read_bytes() == wrote

        # Said something, it is carried on, the same chat, what was said before above.
        expect(say).to_be_visible()
        say.fill("what was it")
        say.press("Enter")
        expect(thread).to_contain_text("did: what was it")
        expect(thread).to_contain_text("did: remember teal")
        assert page.url.endswith(f"#/chats/{name}")
        assert [one["id"] for one in _call(page, "chat.list")["chats"]] == [name]
        # Its terminal is still the one open beside it.
        expect(frame_.locator("[data-hmz=term-host]").first).to_be_visible()

    # One whose host has gone again is brought up again as a pane of it is opened.
    with served() as site, opened(site, engine=engine) as page:
        go(page, f"/chats/{name}")
        expect(page.locator("[data-hmz=thread]")).to_contain_text("did: what was it")
        stop(page)
        page.reload()
        page.locator("[data-hmz=chat-menu]").click()
        page.locator("[data-hmz=env-open]").click()
        frame_ = page.locator("[data-hmz=inspector] [data-hmz=envs]")
        expect(frame_.locator("[data-hmz=files-tree]")).to_contain_text("kept.txt")

        # Its environment's own view, at the address of a host that has gone, finds the
        # chat again, and goes on to the address of the host it is on now.
        slot = _call(page, "chat.get", {"chat": name})["slot"]
        assert slot
        stop(page)
        was = {"workspace": str(project.resolve()), "slot": slot, "chat": name}
        go(page, f"/envs/live?{urllib.parse.urlencode(was)}")
        whole = page.locator("[data-hmz=envs-view]")
        expect(whole.locator("[data-hmz=files-tree]")).to_contain_text("kept.txt")
        now = _call(page, "chat.get", {"chat": name})["slot"]
        assert now not in ("", slot)
        assert urllib.parse.quote(now, safe="") in page.url


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

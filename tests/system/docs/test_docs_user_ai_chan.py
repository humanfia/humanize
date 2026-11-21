"""The pictures of `docs/user/ai-chan.md`: Ai-chan's drawer in the app, and `/ai` in the terminal.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_ai_chan.py`.

Her conversations are real ones of the staged daemon, played by the stand-in `claude`. The
stand-in calls no tool of hers, so what a picture shows her calling is scripted: the calls a
real nous makes of the same tools, by the names its harness gives them.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_tui import on, onto, shows, typed, until
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

    from tests.integration.doubles_web import Session
    from tests.system.docs.conftest import World

_ASK = "What did the discount epic do?"
_STEER = "Tell its actor to refuse an expired code"
_TODAY = "What ran in shop today?"
_SPENT = "How much did this week cost?"

#: How many seconds she is given to answer a line.
_PATIENCE = 60.0

_DID = (
    "It finished. The actor added a discount code to checkout: charge() takes a code"
    " and takes its discount off the total, and WELCOME10 is 10% off. The reviewer"
    " passed it in the second round. Six tests pass."
)
_TOLD = (
    "I cannot say that to the epic: this conversation is read-only. Start one with"
    " Full access and I will tell the actor."
)
_RAN = "One epic of rlar, which finished, and one chat about the checkout."
_COST = (
    "Nothing is priced on this machine, so no cost is recorded: 3 epics, 41k tokens."
)


def _tool(name: str, said: dict[str, Any], result: str) -> dict[str, Any]:
    """One of her tools, called as a real harness names it."""
    return {
        "name": f"mcp__humanize__{name}",
        "input": said,
        "result": result,
        "takes": 0.2,
    }


def _looks(epic: str) -> list[dict[str, Any]]:
    """What she does when asked what an epic did: lists the epics, and reads the one meant."""
    return [
        _tool("epics_list", {"limit": 5}, f"1 epic: {epic}, rlar, done"),
        _tool("epic_view", {"name": epic}, "flow rlar, done, 2 agents, 4 sessions"),
        _tool("transcript_read", {"name": epic}, "actor/1 ... reviewer/2: done"),
    ]


@pytest.fixture(autouse=True)
def _linked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Her hosts, which are threads of the scene's own daemon, told a scoped link is theirs.

    A host of its own is told its link in its environment as it starts. The stand-in calls
    none of her tools, so the link is named and never opened.
    """
    from hmz.daemon import where

    monkeypatch.setenv("HUMANIZE_AICHAN_LINK", str(where.at() / "ai-0000.sock"))


def _conversation(world: World, task: str, *more: str, scope: str = "workspace") -> int:
    """Holds a conversation with her: each line said, and answered, in turn."""
    here = str(world.workspace)
    with world.session() as session:
        made = session.call(
            "aichan.create",
            scope=scope,
            nous=AGENT,
            preset="read-only",
            task=task,
            idem=uuid.uuid4().hex,
            **({} if scope == "daemon" else {"workspace": here}),
        )
        sub = session.call(
            "epic.attach", workspace=made["workspace"], slot=made["slot"]
        )["sub"]
        for turn, line in enumerate((task, *more), 1):
            if turn > 1:
                session.call(
                    "chat.say",
                    workspace=made["workspace"],
                    slot=made["slot"],
                    text=line,
                )
            _answered(session, sub, turn)
        session.call("epic.detach", sub=sub)
    return int(made["id"])


def _answered(session: Session, sub: str, turns: int) -> None:
    """Waits until she has answered so many lines: each answer asks what next."""
    until = time.monotonic() + _PATIENCE
    while time.monotonic() < until:
        with session.heard:
            asked = sum(
                1
                for method, said in session.told
                if method == "epic.event"
                and said["sub"] == sub
                and said["message"].get("type") == "asked"
            )
        if asked >= turns:
            return
        time.sleep(0.05)
    raise AssertionError(f"she did not answer line {turns}")


def _drawer(page: Page) -> Locator:
    """Her drawer, opened from the view's bar."""
    page.get_by_role("button", name="Ai-chan").click()
    drawer = page.locator("[data-hmz=aichan]")
    expect(drawer).to_be_visible()
    return drawer


def _said(world: World, epic: str, *, slowly: float = 0) -> None:
    """Scripts what she answers to each thing the scenes ask her."""
    world.says(
        {
            "discount epic": {"text": _DID, "tools": _looks(epic), "after": slowly},
            "expired": _TOLD,
            "today": _RAN,
            "this week": _COST,
        }
    )


def test_a_conversation_is_made_from_the_drawer(world: World) -> None:
    epic = world.epic("rlar", "Add a discount code to checkout")
    _said(world, epic, slowly=2.5)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{epic}")
        expect(page.get_by_role("button", name="Ai-chan")).to_be_visible()
        # The epic's graph is fitted to its view a moment after it is drawn.
        page.wait_for_timeout(1500)
        reel = shots.Reel("user-ai-chan-new", window="desktop")
        avatar = page.get_by_role("button", name="Ai-chan")
        reel.web(page, hold=1.3, pointer=avatar, click=True)
        drawer = _drawer(page)
        new = drawer.get_by_role("button", name="New conversation")
        expect(new).to_be_visible()
        reel.web(page, hold=1.3, pointer=new, click=True)
        new.click()
        box = drawer.get_by_role("textbox")
        expect(box).to_be_focused()
        permission = drawer.locator("[data-hmz=aichan-say] [data-hmz=permission]")
        expect(permission).to_have_text("Read only · Epic")
        expect(
            drawer.locator("[data-hmz=aichan-say] [data-hmz=pick-model]")
        ).to_have_attribute("data-value", "claude-haiku-4-5")
        reel.web(page, hold=1.1, pointer=permission, click=True)
        permission.click()
        menu = page.get_by_role("menu", name="Permissions")
        expect(menu).to_be_visible()
        reel.web(page, hold=2.4, caption="what she may change, and how far she reaches")
        shots.web(page, "user-ai-chan-scope", clip=menu, pad=16)
        page.keyboard.press("Escape")
        expect(menu).to_be_hidden()
        reel.web(page, hold=0.5, pointer=box, click=True)
        reel.type(page, box, _ASK, per=10)
        box.press("Enter")
        stop = drawer.get_by_role("button", name="Stop")
        expect(stop).to_be_visible()
        expect(drawer.locator("[data-hmz=aichan-typing]")).to_be_visible()
        # Her three dots bounce for ever, and a frame is of one instant: held still for it.
        page.add_style_tag(
            content="[data-hmz=aichan-typing] * { animation: none !important }"
        )
        reel.web(page, hold=1.5, caption="she is answering")
        expect(drawer).to_contain_text("WELCOME10")
        expect(drawer.get_by_role("button", name="Send")).to_be_visible()
        reel.web(page, hold=4.5, poster=True)
        reel.save()
        shots.web(page, "user-ai-chan-open", window="desktop", most=shots.REEL)


def test_her_conversations_are_listed_and_a_row_has_a_menu(world: World) -> None:
    epic = world.epic("rlar", "Add a discount code to checkout")
    _said(world, epic)
    _conversation(world, _TODAY)
    _conversation(world, _SPENT, scope="daemon")
    _conversation(world, _ASK, _STEER)
    # A shorter window, since the list is three rows, but no smaller: a menu's words are
    # printed a hair from where the screen draws them, and in a picture of little else that
    # is more of it than a picture may differ from its screenshot by.
    with world.page(desktop=True, height=600) as page:
        go(page, f"/epics/{epic}")
        drawer = _drawer(page)
        rows = drawer.locator("[data-hmz=aichan-conversation]")
        expect(rows).to_have_count(3)
        reel = shots.Reel("user-ai-chan-list", clip=drawer, pad=96)
        row = rows.filter(has_text=_TODAY)
        reel.web(page, hold=1.6, pointer=row, click=True, caption="right-click a row")
        row.click(button="right")
        menu = page.get_by_role("menu")
        pin = menu.get_by_role("menuitem", name="Pin")
        expect(pin).to_be_visible()
        reel.web(page, hold=2.0, pointer=pin, click=True)
        pin.click()
        expect(rows.first).to_contain_text(_TODAY)
        expect(rows.first.get_by_role("img", name="Pinned")).to_be_visible()
        reel.web(page, hold=1.8, caption="pinned rows come first")
        other = rows.filter(has_text=_SPENT)
        other.click(button="right")
        delete = page.get_by_role("menu").get_by_role("menuitem", name="Delete")
        expect(delete).to_be_visible()
        reel.web(page, hold=1.6, pointer=delete, click=True)
        delete.click()
        expect(drawer.get_by_role("alertdialog")).to_be_visible()
        reel.web(page, hold=3.2, poster=True, caption="deleting asks first")
        reel.save()


async def test_ai_chan_in_the_terminal(world: World) -> None:
    from hmz.tui.pick import AiChanNew, AiChans

    epic = world.epic("rlar", "Add a discount code to checkout")
    _said(world, epic)
    _conversation(world, _TODAY)
    async with world.tui((100, 28)) as (app, pilot):
        await shows(pilot, MODEL)
        reel = shots.Reel("user-ai-chan-terminal")
        await pilot.press(*"/ai")
        await pilot.pause()
        reel.tui(app, hold=1.4)
        await pilot.press("enter")
        await on(pilot, AiChans)
        await shows(pilot, "New", "Ai-chan#1")
        reel.tui(app, hold=2.2)
        await onto(pilot, "new")
        await pilot.press("enter")
        await on(pilot, AiChanNew)
        await shows(pilot, "scope", "nous", "preset", "read-only")
        reel.tui(app, hold=2.4)
        await pilot.click("#act-done")
        await until(pilot, lambda: len(app.screen_stack) == 1, "the log screen")
        await shows(pilot, "Ai-chan: the next line")
        reel.tui(app, hold=1.6)
        await typed(pilot, _ASK)
        await shows(pilot, "WELCOME10", "Ai-chan#2")
        await pilot.pause()
        reel.tui(app, hold=4.5, poster=True)
        reel.save()

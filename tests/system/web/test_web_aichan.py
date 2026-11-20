"""Ai-chan's drawer in a real browser: her button, her list, its menu and swipe, and her chat.

Section 3.16 of protocol/web.md. Her conversations are faked on the wire where only how the
list is drawn is under test, and real -- the stand-in `claude` answering -- where a conversation
is made and talked to.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import Browser, served
from tests.system.web.doubles_browser import ENGINES, Wire, go, opened

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import FloatRect, Locator, Page

pytestmark = [
    pytest.mark.parametrize("engine", ENGINES),
    pytest.mark.usefixtures("daemon"),
]

#: What a row never says: what the conversation reaches, thinks with or may do, or how it stands.
_UNSAID = re.compile(
    r"daemon|workspace|epic|folded|waiting|answering|claude|opus|read-only|network",
    re.IGNORECASE,
)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, and a project."""
    return install(tmp_path, monkeypatch)


@pytest.fixture
def linked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Her host told its scoped link, where it is a thread of the test's own daemon.

    A host of its own is told the link in its environment as it starts; a thread of this
    process reads this process's, so the one conversation a test makes is given a slot known
    beforehand, and the link of that slot is named here.
    """
    from hmz.daemon import where

    def slot(kind: str = "chat") -> str:
        return "ai:feedc0de0001" if kind == "ai" else fresh(kind)

    fresh = where.chat
    monkeypatch.setattr(where, "chat", slot)
    monkeypatch.setenv("HUMANIZE_AICHAN_LINK", str(where.at() / "ai-feedc0de0001.sock"))


def _conversation(ident: int, title: str, latest: str, **said: Any) -> dict[str, Any]:
    return {
        "id": ident,
        "title": title,
        "scope": "daemon",
        "workspace": "/home/ai/m",
        "epic": "",
        "nous": "claude/claude-opus-4-1",
        "preset": "read-only",
        "network": False,
        "slot": f"ai:{ident}",
        "state": "folded",
        "created": f"2026-01-0{ident}T00:00:00Z",
        "latest": latest,
        "updated": f"2026-01-0{ident}T00:00:00Z",
    } | said


def _listed() -> list[dict[str, Any]]:
    """Four conversations, newest first as the daemon lists them."""
    return [
        _conversation(4, "Stop the refactor", "Told the actor to stop."),
        _conversation(3, "Run the tests", "x" * 120, state="running"),
        # Said in last of all, though made before the two above.
        _conversation(
            2,
            "What happened today, every bit of it, one line for each thing that was done",
            "Four things today: " + "all of them done " * 6,
            updated="2026-01-09T00:00:00Z",
        ),
        _conversation(1, "", "hi"),
    ]


def _wire(held: list[dict[str, Any]]) -> Wire:
    """A wire whose daemon lists `held`, and forgets the one it is told to."""

    def forgets(params: dict[str, Any]) -> dict[str, Any]:
        held[:] = [one for one in held if one["id"] != params["id"]]
        return {"result": {}}

    return Wire(
        faked={
            "aichan.list": lambda _: {"result": {"conversations": list(held)}},
            "aichan.forget": forgets,
        }
    )


def _drawer(page: Page) -> Locator:
    """Opens her drawer from the view's bar, and answers it."""
    page.locator("[data-hmz=bar] [data-hmz=aichan-toggle]").click()
    drawer = page.locator("[data-hmz=aichan]")
    expect(drawer).to_be_visible()
    return drawer


def _box(of: Locator) -> FloatRect:
    """Where something is drawn."""
    found = of.bounding_box()
    assert found is not None
    return found


def _titles(drawer: Locator) -> list[str]:
    return drawer.locator(
        "[data-hmz=aichan-conversation] .aichan-title"
    ).all_inner_texts()


def _swipe(page: Page, row: Locator, by: int) -> None:
    """Drags a finger along a row, from near its right edge, and lets go."""
    box = _box(row)
    row.evaluate(
        """(row, [x, y, by]) => {
            const touch = (type, at) => row.querySelector('.aichan-pick').dispatchEvent(
                new PointerEvent(type, {pointerId: 7, pointerType: 'touch', isPrimary: true,
                    bubbles: true, cancelable: true, clientX: at, clientY: y}))
            touch('pointerdown', x)
            for (let step = 1; step <= 6; step++) touch('pointermove', x + (by * step) / 6)
            touch('pointerup', x + by)
        }""",
        [box["x"] + box["width"] - 30, box["y"] + box["height"] / 2, by],
    )


def test_ai_chans_button_ends_the_bar_of_every_view(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        drawer = page.locator("[data-hmz=aichan]")
        for address in (
            "/new",
            "/new/chat",
            f"/new/chat?workspace={project.resolve()}",
            "/flows",
            "/envs",
            "/epics/import",
            "/chats/none-such",
        ):
            go(page, address)
            bar = page.locator("[data-hmz=page] [data-hmz=bar]")
            last = bar.locator(".bar-actions > *").last
            expect(last).to_have_attribute("data-hmz", "aichan-toggle")
            expect(last).to_be_visible()
            # Drawn as her avatar, loaded: a WebP of the page's own, round, not pixel art.
            avatar = last.locator("img")
            expect(avatar).to_have_attribute("src", "/ai-chan/avatar.webp")
            assert avatar.evaluate("(img) => img.complete && img.naturalWidth") == 256
            assert avatar.evaluate("(img) => getComputedStyle(img).imageRendering") in (
                "auto",
                "",
            )
            # It says whether the drawer is open, which stays as it was from view to view.
            expect(last).to_have_attribute(
                "aria-pressed", "true" if drawer.is_visible() else "false"
            )
        page.locator("[data-hmz=bar] [data-hmz=aichan-toggle]").click()
        expect(drawer).to_be_visible()
        go(page, "/new/chat")
        expect(drawer).to_be_visible()
        expect(
            page.locator("[data-hmz=bar] [data-hmz=aichan-toggle]")
        ).to_have_attribute("aria-pressed", "true")
        # No avatar over the drawer itself: her name, and New.
        expect(drawer.locator(".aichan-head img")).to_have_count(0)
        expect(drawer.locator(".aichan-head h2")).to_have_text("Ai-chan")


def test_the_new_form_asks_the_scope_and_picks_her_nous_on_a_chip(
    project: Path, engine: str, tmp_path: Path
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, f"/new?workspace={project.resolve()}")
        drawer = _drawer(page)
        # None yet: the drawer says so, and offers to make one.
        none = drawer.locator("[data-hmz=aichan-none]")
        expect(none).to_contain_text("No conversations yet")
        none.get_by_role("button", name="New conversation").click()
        form = drawer.locator("[data-hmz=aichan-form]")
        expect(form).to_be_visible()
        # A new epic in a folder shows a workspace: the scope starts on it.
        expect(form.locator("[data-hmz=aichan-scope]")).to_have_value("workspace")
        expect(form.locator("[data-hmz=aichan-workspace]")).to_be_visible()
        expect(form.locator("[data-hmz=aichan-preset]")).to_have_value("read-only")
        expect(form.locator("[data-hmz=aichan-network]")).not_to_be_checked()
        expect(form.locator("[data-hmz=aichan-epic]")).to_be_hidden()
        # Her nous is a chip under the box of the task, as a new chat's: no field to spell
        # one in, and a menu of every nous the harnesses here run.
        expect(form.locator("[data-hmz=aichan-nous] input")).to_have_count(0)
        chip = form.locator("[data-hmz=composer-under] [data-hmz=pick-model]")
        expect(chip).to_have_attribute("data-value", "claude-haiku-4-5")
        chip.click()
        menu = page.get_by_role("menu", name="Nous")
        expect(menu.locator("[data-value=claude-opus-4-1]")).to_be_visible()
        page.screenshot(path=str(tmp_path / "aichan-new.png"))
        page.keyboard.press("Escape")
        form.locator("[data-hmz=aichan-scope]").select_option("daemon")
        expect(form.locator("[data-hmz=aichan-workspace]")).to_be_hidden()
        form.locator("[data-hmz=aichan-scope]").select_option("epic")
        expect(form.locator("[data-hmz=aichan-epic]")).to_be_visible()
        expect(form.locator("[data-hmz=aichan-task] textarea")).to_be_visible()
        drawer.get_by_role("button", name="Close panel").click()
        expect(drawer).to_be_hidden()


def test_her_conversations_are_listed_as_a_chat_app_lists_them(
    project: Path, engine: str, tmp_path: Path
) -> None:
    held = _listed()
    wire = _wire(held)
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, "/new/chat")
        drawer = _drawer(page)
        rows = drawer.locator("[data-hmz=aichan-conversation]")
        expect(rows).to_have_count(4)
        # The latest said in first: not the order they were made in.
        assert _titles(drawer) == [
            "What happened today, every bit of it, one line for each thing that was done",
            "Stop the refactor",
            "Run the tests",
            "Ai-chan #1",
        ]
        # A face, a title and one line: nothing of its scope, its nous, its permission
        # or how it stands, and no button of its own.
        for at in range(4):
            row = rows.nth(at)
            expect(row).not_to_contain_text(_UNSAID)
            face = row.locator("img.aichan-face")
            assert re.fullmatch(
                r"/ai-chan/face-(0[1-9]|1[0-6])\.webp", face.get_attribute("src") or ""
            )
            assert face.evaluate("(img) => img.complete && img.naturalWidth") == 160
            assert face.evaluate("(img) => getComputedStyle(img).borderRadius") != "0px"
            expect(row.locator("button:visible")).to_have_count(1)
            assert _box(row)["height"] <= 60
        expect(drawer.get_by_role("button", name="Forget")).to_have_count(0)
        # Her turn open: typing, in place of what was last said.
        expect(rows.nth(2).locator("[data-hmz=aichan-latest]")).to_have_text("typing…")
        expect(rows.nth(1).locator("[data-hmz=aichan-latest]")).to_have_text(
            "Told the actor to stop."
        )
        # A long title and a long line are each one line, cut short, inside the row.
        for cut in (".aichan-title", "[data-hmz=aichan-latest]"):
            long = rows.nth(0).locator(cut)
            assert long.evaluate("(el) => el.scrollWidth > el.clientWidth")
            assert (
                long.evaluate("(el) => getComputedStyle(el).textOverflow") == "ellipsis"
            )
            assert _box(long)["height"] <= 20
        # Two conversations are told apart by their faces.
        faces = {rows.nth(at).locator("img").get_attribute("src") for at in range(4)}
        assert len(faces) == 4
        page.screenshot(path=str(tmp_path / "aichan-list.png"))

        # Its menu, under the pointer's other button: three things.
        rows.nth(1).click(button="right")
        menu = page.locator(".popover.context")
        expect(menu.get_by_role("menuitem")).to_have_text(
            ["Pin", "Mark as unread", "Delete"]
        )
        assert menu.evaluate("(el) => getComputedStyle(el).boxShadow") == "none"
        menu.get_by_role("menuitem", name="Pin").click()
        # Pinned, it is first, and says so.
        assert _titles(drawer)[0] == "Stop the refactor"
        expect(rows.nth(0).locator("[data-hmz=aichan-pinned]")).to_have_count(1)
        # By the keys: Alt and Enter on the row, as the menu key.
        rows.nth(3).locator(".aichan-pick").focus()
        page.keyboard.press("Alt+Enter")
        expect(menu.get_by_role("menuitem")).to_have_text(
            ["Pin", "Mark as unread", "Delete"]
        )
        page.keyboard.press("Enter")
        assert _titles(drawer)[:2] == ["Stop the refactor", "Ai-chan #1"]
        rows.nth(1).locator(".aichan-pick").focus()
        page.keyboard.press("ContextMenu")
        expect(menu.get_by_role("menuitem").first).to_have_text("Unpin")
        menu.get_by_role("menuitem", name="Mark as unread").click()
        unread = rows.nth(1)
        expect(unread.locator("[data-hmz=aichan-unread]")).to_have_count(1)
        assert (
            unread.locator(".aichan-title").evaluate(
                "(el) => getComputedStyle(el).fontWeight"
            )
            == "700"
        )
        # Both are kept in this browser: there again once the page is read again.
        page.reload()
        drawer = page.locator("[data-hmz=aichan]")
        expect(drawer).to_be_visible()
        rows = drawer.locator("[data-hmz=aichan-conversation]")
        expect(rows).to_have_count(4)
        assert _titles(drawer)[:2] == ["Stop the refactor", "Ai-chan #1"]
        expect(rows.nth(1).locator("[data-hmz=aichan-unread]")).to_have_count(1)
        rows.nth(1).click(button="right")
        menu.get_by_role("menuitem", name="Mark as read").click()
        expect(rows.nth(1).locator("[data-hmz=aichan-unread]")).to_have_count(0)
        rows.nth(1).click(button="right")
        menu.get_by_role("menuitem", name="Unpin").click()
        assert _titles(drawer)[-1] == "Ai-chan #1"

        # Something said in one since it was read makes it unread, and puts it first
        # under the pinned.
        held[0] = {**held[0], "updated": "2026-02-01T00:00:00Z", "latest": "And done."}
        said = drawer.locator("[data-id='4']")
        expect(said.locator("[data-hmz=aichan-latest]")).to_have_text("And done.")
        expect(said.locator("[data-hmz=aichan-unread]")).to_have_count(1)
        held[2] = {**held[2], "updated": "2026-02-02T00:00:00Z", "latest": "More."}
        other = drawer.locator("[data-id='2']")
        expect(other.locator("[data-hmz=aichan-unread]")).to_have_count(1)
        assert _titles(drawer)[:2] == [
            "Stop the refactor",
            "What happened today, every bit of it, one line for each thing that was done",
        ]

        # Delete asks first, in the row's place, and Cancel and Escape take it back.
        other.click(button="right")
        menu.get_by_role("menuitem", name="Delete").click()
        ask = other.locator("[data-hmz=aichan-ask]")
        expect(ask).to_contain_text("Delete this conversation?")
        expect(ask.locator("[data-hmz=aichan-keep]")).to_be_focused()
        page.keyboard.press("Escape")
        expect(ask).to_have_count(0)
        expect(drawer).to_be_visible()
        assert wire.params("aichan.forget") == []
        other.click(button="right")
        menu.get_by_role("menuitem", name="Delete").click()
        ask.locator("[data-hmz=aichan-delete]").click()
        expect(rows).to_have_count(3)
        assert [one["id"] for one in wire.params("aichan.forget")] == [2]
        # Nothing is kept of it: the next conversation of its number starts unmarked.
        kept = page.evaluate("() => localStorage.getItem('hmz-aichan-marks')")
        assert '"2"' not in kept
        assert "[2" not in kept

        # The last gone, the drawer says there is none.
        del held[:]
        expect(drawer.locator("[data-hmz=aichan-none]")).to_be_visible()
        expect(rows).to_have_count(0)


def test_a_row_swiped_left_by_a_finger_shows_what_its_menu_offers(
    project: Path, engine: str, tmp_path: Path
) -> None:
    held = _listed()
    wire = _wire(held)
    with (
        served() as site,
        opened(
            site, engine=engine, width=390, height=844, touch=True, routed=wire.routes
        ) as page,
    ):
        go(page, "/new/chat")
        # On a phone the drawer covers the view, and its rows run its whole width.
        drawer = _drawer(page)
        rows = drawer.locator("[data-hmz=aichan-conversation]")
        expect(rows).to_have_count(4)
        assert _box(rows.nth(0))["width"] == 390
        tray = rows.nth(1).locator("[data-hmz=aichan-swipe]")
        expect(tray).to_be_hidden()
        # A short drag is no swipe: the row slides back.
        _swipe(page, rows.nth(1), -60)
        expect(rows.nth(1)).not_to_have_class(re.compile("swiped"))
        expect(tray).to_be_hidden()
        # Past the half of what stands beside it, it stays open on the same three.
        _swipe(page, rows.nth(1), -160)
        expect(rows.nth(1)).to_have_class(re.compile("swiped"))
        expect(tray.locator("button")).to_have_text(["Pin", "Mark as unread", "Delete"])
        # Slid in whole, its last at the row's right edge.
        page.wait_for_timeout(400)
        last = _box(tray.locator("button").last)
        assert round(last["x"] + last["width"]) == 390
        assert tray.evaluate("(el) => !el.inert")
        page.screenshot(path=str(tmp_path / "aichan-swiped.png"))
        # One row is open at a time.
        _swipe(page, rows.nth(2), -160)
        expect(rows.nth(2)).to_have_class(re.compile("swiped"))
        expect(rows.nth(1)).not_to_have_class(re.compile("swiped"))
        # A press of the row open shuts it, and opens no conversation.
        rows.nth(2).locator(".aichan-pick").click(position={"x": 250, "y": 20})
        expect(rows.nth(2)).not_to_have_class(re.compile("swiped"))
        expect(drawer.locator("[data-hmz=aichan-chat]")).to_have_count(0)
        # What stands beside it does what the menu does.
        _swipe(page, rows.nth(2), -160)
        rows.nth(2).locator("[data-act=pin]").click()
        assert _titles(drawer)[0] == "Run the tests"
        expect(rows.nth(0)).not_to_have_class(re.compile("swiped"))
        _swipe(page, rows.nth(0), -160)
        expect(rows.nth(0).locator("[data-act=pin]")).to_have_text("Unpin")
        rows.nth(0).locator("[data-act=read]").click()
        expect(rows.nth(0).locator("[data-hmz=aichan-unread]")).to_have_count(1)
        _swipe(page, rows.nth(3), -160)
        rows.nth(3).locator("[data-act=delete]").click()
        ask = rows.nth(3).locator("[data-hmz=aichan-ask]")
        expect(ask).to_be_visible()
        ask.locator("[data-hmz=aichan-delete]").click()
        expect(rows).to_have_count(3)
        assert [one["id"] for one in wire.params("aichan.forget")] == [1]

        # A finger resting on a row opens its menu, and the row is not opened by it.
        rows.nth(1).locator(".aichan-pick").evaluate(
            """(pick) => {
                const box = pick.getBoundingClientRect()
                pick.dispatchEvent(new PointerEvent('pointerdown', {pointerId: 9,
                    pointerType: 'touch', isPrimary: true, bubbles: true,
                    clientX: box.x + 100, clientY: box.y + 20}))
            }"""
        )
        menu = page.locator(".popover.context")
        expect(menu.get_by_role("menuitem")).to_have_text(
            ["Pin", "Mark as unread", "Delete"]
        )
        expect(drawer.locator("[data-hmz=aichan-chat]")).to_have_count(0)


@pytest.mark.usefixtures("linked")
def test_a_conversation_is_made_with_the_nous_picked_and_drawn_in_bubbles(
    project: Path, engine: str, tmp_path: Path
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new")
        drawer = _drawer(page)
        drawer.locator("[data-hmz=aichan-new]").click()
        form = drawer.locator("[data-hmz=aichan-form]")
        form.locator("[data-hmz=aichan-scope]").select_option("daemon")
        # Another nous than the one the chip starts on.
        chip = form.locator("[data-hmz=pick-model]")
        expect(chip).to_have_attribute("data-value", "claude-haiku-4-5")
        chip.click()
        page.get_by_role("menu", name="Nous").locator(
            "[data-value=claude-opus-4-1]"
        ).click()
        expect(chip).to_have_attribute("data-value", "claude-opus-4-1")
        task = form.locator("[data-hmz=aichan-task] textarea")
        task.fill("hello there")
        task.press("Enter")

        # Opened as a chat: what was said at the right, her answer in a bubble at the
        # left beside the conversation's face.
        chat = drawer.locator("[data-hmz=aichan-chat]")
        expect(chat).to_be_visible()
        expect(chat.locator("[data-hmz=aichan-title]")).to_have_text("hello there")
        log = chat.locator("[data-hmz=aichan-log]")
        mine = log.locator(".said.you .body").first
        expect(mine).to_have_text("hello there")
        hers = log.locator(".said.text").first
        expect(hers).to_be_visible()
        whole = _box(log)
        said, answered = _box(mine), _box(hers.locator(".body"))
        assert said["x"] + said["width"] == pytest.approx(
            whole["x"] + whole["width"], abs=1
        )
        face = _box(hers.locator(".g"))
        assert (face["width"], face["height"]) == (28, 28)
        assert face["x"] == pytest.approx(whole["x"], abs=1)
        assert answered["x"] > face["x"] + face["width"]
        shown = hers.locator(".g").evaluate(
            "(el) => getComputedStyle(el).backgroundImage"
        )
        assert re.search(r"/ai-chan/face-(0[1-9]|1[0-6])\.webp", shown)
        for bubble in (mine, hers.locator(".body")):
            style = bubble.evaluate(
                "(el) => [getComputedStyle(el).borderTopLeftRadius,"
                " getComputedStyle(el).backgroundColor, getComputedStyle(el).boxShadow]"
            )
            assert style[0] == "12px"
            assert style[1] != "rgba(0, 0, 0, 0)"
            assert style[2] == "none"
        # Nobody is named, nothing says she waits, and nothing is counted.
        expect(chat).not_to_contain_text(
            re.compile(r"is working|ai_chan|/1\b|Waiting|Folded|\$\d", re.IGNORECASE)
        )
        expect(
            chat.locator("[data-hmz=aichan-state], [data-hmz=aichan-folded]")
        ).to_have_count(0)
        expect(chat.locator(".usage-chip, [aria-label=Usage]")).to_have_count(0)
        expect(chat).to_have_attribute("data-state", "waiting")

        # While she answers: three dots in a bubble of hers at the foot, and Stop.
        say = chat.locator("[data-hmz=aichan-say] textarea")
        say.fill('run: [["sleep", "6"]]')
        say.press("Enter")
        typing = log.locator("[data-hmz=aichan-typing]")
        expect(typing).to_be_visible()
        expect(typing.locator("i")).to_have_count(3)
        assert (
            log.locator(":scope > *").last.get_attribute("data-hmz") == "aichan-typing"
        )
        expect(chat.get_by_role("button", name="Stop")).to_be_visible()
        expect(chat).to_have_attribute("data-state", "running")
        page.screenshot(path=str(tmp_path / "aichan-chat.png"))
        expect(typing).to_have_count(0, timeout=30000)
        expect(log.locator(".said.ends .body").last).to_have_text(
            re.compile(r"^Worked for \d+s$")
        )

        # In the list it is a row of the same face, and what she said last.
        drawer.locator("[data-hmz=aichan-back]").click()
        row = drawer.locator("[data-hmz=aichan-conversation]")
        expect(row).to_have_count(1)
        assert (row.locator("img").get_attribute("src") or "") in shown
        expect(row.locator(".aichan-title")).to_have_text("hello there")
        expect(row.locator("[data-hmz=aichan-latest]")).not_to_have_text("")
        expect(row.locator("[data-hmz=aichan-unread]")).to_have_count(0)

        # Her nous was written down as the one last used, by making her and by nothing
        # else: the next form starts on it, and Settings offers no such field.
        browser = Browser(site)
        browser.signs_in()
        with browser.session() as asked:
            assert asked.call("settings.get")["ai_chan"] == "claude/claude-opus-4-1"
            (listed,) = asked.call("aichan.list")["conversations"]
        assert listed["nous"] == "claude/claude-opus-4-1"
        drawer.locator("[data-hmz=aichan-new]").click()
        expect(
            drawer.locator("[data-hmz=aichan-form] [data-hmz=pick-model]")
        ).to_have_attribute("data-value", "claude-opus-4-1")
        go(page, "/settings/general")
        expect(page.locator("[data-hmz=harness-sessions]")).to_be_visible()
        expect(page.locator("[data-hmz=ai-chan-setting]")).to_have_count(0)
        expect(page.locator("[data-hmz=dialog-settings]")).not_to_contain_text(
            "Ai-chan"
        )

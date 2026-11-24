"""The pictures of `docs/user/chat-input.md`: what a chat's box takes besides words.

Its Add menu and what it completes, a file mentioned, a shell line and a line refused, the
model changed from the chip under the box, the choice between a skill and a flow, the same
in the terminal, and a shell line from the command line. Run it by naming it: `uv run pytest
tests/system/docs/test_docs_user_chat_input.py`.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from playwright.sync_api import expect

from tests.integration.doubles_tui import shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-chat-input"

_TASK = "Add a discount code to checkout"
_ANSWER = (
    "Checkout takes a discount code now: charge() looks the code up and takes its"
    " discount off the total. WELCOME10 is 10% off."
)
_ASK = "What does @shop/cart.py add up?"
_SAID = "shop/cart.py adds up what a cart costs, in cents: each item's price times its count."

_CHECKOUT = '''"""Paying for a cart."""

from shop.cart import total

CODES = {"WELCOME10": 10}


def charge(items: dict[str, int], code: str = "") -> int:
    """What is charged for a cart, in cents, less what a code takes off."""
    owed = total(items)
    return owed - owed * CODES.get(code, 0) // 100
'''

#: What the agent does when told the task: edits the checkout, and says so.
_WORK = {
    "text": _ANSWER,
    "tools": [
        {
            "name": "Edit",
            "input": {"file_path": "shop/checkout.py"},
            "result": "edited",
            "takes": 0.2,
        },
    ],
    "writes": {"shop/checkout.py": _CHECKOUT},
}

#: The commands and the skill the stand-in says its conversation has, as Claude Code lists
#: its own when a conversation opens.
_COMMANDS = ["compact", "context", "init", "review", "security-review", "release-notes"]
_SKILLS = ["release-notes"]


def _lists_its_commands() -> None:
    """Teaches the stand-in `claude` what Claude Code does that a chat's native input needs.

    The conftest's stand-in opens a conversation listing no commands, and answers no request
    made of it between turns. A real Claude Code lists its slash commands and skills in its
    `system/init`, and answers `set_model`: so does this one, from here on.
    """
    found = shutil.which("claude")
    assert found is not None
    claude = Path(found)
    source = claude.read_text()
    init = 'out({"type": "system", "subtype": "init", "session_id": session, "model": model})'
    skip = '    if said.get("type") != "user":\n        continue\n'
    assert source.count(init) == 1
    assert source.count(skip) == 1
    source = source.replace(
        init,
        'out({"type": "system", "subtype": "init", "session_id": session, "model": model,'
        f' "slash_commands": {_COMMANDS!r}, "skills": {_SKILLS!r}}})',
    )
    source = source.replace(
        skip,
        '    if said.get("type") == "control_request":\n'
        '        out({"type": "control_response", "response": {"subtype": "success",\n'
        '             "request_id": said["request_id"], "response": {}}})\n'
        "        continue\n" + skip,
    )
    claude.write_text(source)


class _Part:
    """A part of the page that no one element is: a box of it, found as a locator's is."""

    def __init__(self, left: float, top: float, right: float, bottom: float) -> None:
        self._box = {"x": left, "y": top, "width": right - left, "height": bottom - top}

    def bounding_box(self) -> dict[str, float]:
        return self._box


def _around(*parts: Locator, pad: float = 14) -> Any:
    """The box that holds every one of these parts of the page, with room around it."""
    boxes = [one.bounding_box() for one in parts]
    found = [one for one in boxes if one is not None]
    assert len(found) == len(parts)
    return cast(
        "Any",
        _Part(
            min(one["x"] for one in found) - pad,
            min(one["y"] for one in found) - pad,
            max(one["x"] + one["width"] for one in found) + pad,
            max(one["y"] + one["height"] for one in found) + pad,
        ),
    )


def _open(page: Page) -> Locator:
    """A chat begun on the page and answered: its box, once its catalogue has been read."""
    go(page, "/new/chat")
    expect(page.get_by_role("button", name=re.compile("Nous: .*Haiku"))).to_be_visible()
    first = page.get_by_role("textbox", name="First message")
    first.fill(_TASK)
    first.press("Enter")
    page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
    expect(page.get_by_role("log")).to_contain_text("WELCOME10")
    expect(page.get_by_role("button", name="Send")).to_be_visible()
    expect(page.get_by_role("button", name=re.compile("Nous: .*Haiku"))).to_be_visible()
    # Its row is in the sidebar, and its catalogue is the whole of what its CLI lists.
    expect(page.get_by_role("link", name=_TASK).first).to_be_visible()
    box = page.get_by_role("textbox", name="What to say")
    box.fill("/comp")
    expect(page.locator("[data-hmz=completions]")).to_contain_text("/compact")
    box.fill("")
    return box


def test_the_add_menu_and_what_the_box_completes(world: World) -> None:
    _lists_its_commands()
    world.says({"discount": _WORK})
    with world.page(desktop=True) as page:
        box = _open(page)
        say = page.locator("[data-hmz=say]")
        add = say.locator("[data-hmz=composer-add]")
        offered = page.locator("[data-hmz=completions]")

        reel = shots.Reel(f"{_PAGE}-add", window="desktop")
        reel.web(page, hold=1.2, pointer=add, click=True)
        add.click()
        adding = page.get_by_role("menu", name="Add")
        slash = adding.get_by_role("menuitem", name="Slash commands")
        expect(slash).to_be_visible()
        reel.web(page, hold=1.8, pointer=slash, click=True, caption="the Add menu")
        slash.click()
        expect(box).to_have_value("/")
        expect(offered).to_contain_text("compact")
        reel.web(page, hold=2.4, caption="what a / line can be", poster=True)
        box.press_sequentially("re")
        expect(offered).to_contain_text("review")
        reel.web(page, hold=1.4, keys="re", cut=True)
        box.press("Tab")
        expect(box).to_have_value("/review ")
        reel.web(page, hold=2.4, keys="tab")
        reel.save()

        box.fill("")
        add.click()
        expect(slash).to_be_visible()
        shots.web(page, f"{_PAGE}-menu", clip=_around(say, adding), pad=0)
        page.keyboard.press("Escape")

        box.fill("/")
        expect(offered).to_contain_text("compact")
        shots.web(page, f"{_PAGE}-commands", clip=_around(say, offered), pad=0)

        box.fill("$")
        expect(offered).to_contain_text("ralph_loop")
        shots.web(page, f"{_PAGE}-flows", clip=_around(say, offered), pad=0)

        box.fill("")
        box.press_sequentially("What does @shop/c")
        expect(offered).to_contain_text("cart.py")
        shots.web(page, f"{_PAGE}-files", clip=_around(say, offered), pad=0)


def test_a_shell_line_and_a_line_refused(world: World) -> None:
    _lists_its_commands()
    world.says({"discount": _WORK, "add up": _SAID})
    with world.page(desktop=True) as page:
        box = _open(page)
        log = page.get_by_role("log")
        box.fill("!git status --short")
        box.press("Enter")
        expect(log).to_contain_text("M shop/checkout.py")
        box.fill(_ASK)
        page.keyboard.press("Escape")
        box.press("Enter")
        expect(log).to_contain_text("each item's price")
        expect(page.get_by_role("button", name="Send")).to_be_visible()
        box.fill("/config")
        page.keyboard.press("Escape")
        box.press("Enter")
        expect(page.locator("[data-hmz=dock]")).to_contain_text("cannot be said here")
        shots.web(page, f"{_PAGE}-shell", window="desktop")


def test_the_model_is_changed_from_the_chip(world: World) -> None:
    _lists_its_commands()
    world.says({"discount": _WORK})
    with world.page(desktop=True) as page:
        _open(page)
        log = page.get_by_role("log")
        chip = page.get_by_role("button", name=re.compile("Nous: .*Haiku"))
        reel = shots.Reel(f"{_PAGE}-model", window="desktop")
        reel.web(page, hold=1.2, pointer=chip, click=True)
        chip.click()
        menu = page.get_by_role("menu", name="Nous")
        model = menu.get_by_text("Model", exact=True)
        expect(model).to_be_visible()
        reel.web(page, hold=1.6, pointer=model, click=True, caption="the chat's agent")
        model.click()
        opus = menu.get_by_text(re.compile("Opus")).first
        expect(opus).to_be_visible()
        reel.web(page, hold=1.6, pointer=opus, click=True, caption="its models")
        opus.click()
        # Said on the chip at once, and nothing said to the chat for it.
        expect(
            page.get_by_role("button", name=re.compile("Nous: .*Opus"))
        ).to_be_visible()
        expect(log).not_to_contain_text("/model")
        expect(page.get_by_role("button", name="Send")).to_be_visible()
        reel.web(page, hold=4, poster=True, caption="from its next turn")
        reel.save()


def test_a_skill_or_a_flow_is_chosen_in_the_chat_menu(world: World) -> None:
    _lists_its_commands()
    world.says({"discount": _WORK})
    with world.page(desktop=True) as page:
        _open(page)
        page.locator("[data-hmz=bar] [data-hmz=chat-menu]").click()
        menu = page.get_by_role("menu", name="Chat menu")
        menu.get_by_role("menuitem", name="Skill or flow").click()
        prefer = page.locator("[data-hmz=prefer]")
        expect(prefer.locator("[data-prefer=native]")).to_contain_text("Use the skill")
        shots.web(page, f"{_PAGE}-prefer", clip=_around(menu, prefer), pad=0)


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


async def test_native_input_in_the_terminal(world: World) -> None:
    _lists_its_commands()
    world.says({"discount": _WORK})
    async with world.tui((96, 28)) as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*_TASK, "enter")
        await shows(pilot, "WELCOME10")
        await shows(pilot, "Worked for")
        await _settled(pilot)

        reel = shots.Reel(f"{_PAGE}-terminal")
        reel.tui(app, hold=1.2)
        await pilot.press("/")
        await shows(pilot, "tab select")
        await _settled(pilot, 0.2)
        reel.tui(app, hold=2.0, keys="/", cut=True, caption="Humanize's commands first")
        await pilot.press("r", "e")
        await shows(pilot, "/review")
        await _settled(pilot, 0.2)
        reel.tui(app, hold=2.2, keys="/re", cut=True, caption="then the CLI's own")
        await pilot.press("backspace", "backspace", "backspace")
        await _settled(pilot, 0.2)
        await pilot.press(*"!git status --short")
        await _settled(pilot, 0.2)
        reel.tui(app, hold=1.2, keys="!git status --short", cut=True)
        await pilot.press("enter")
        await shows(pilot, "M shop/checkout.py")
        await _settled(pilot)
        reel.tui(app, hold=3.5, keys="enter", poster=True, caption="a shell line")
        reel.save()

        await pilot.press(*"/prefer", "enter")
        await shows(pilot, "where it names both")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-terminal-prefer")


def test_a_shell_line_from_the_command_line(world: World) -> None:
    _lists_its_commands()
    shots.cli(
        ["hmz", "chat", "start", "-a", AGENT, "!git log --oneline"], f"{_PAGE}-cli"
    )

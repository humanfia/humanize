"""The pictures of `docs/user/skills.md`: the skills an agent carries, yours and a flow's.

A skill of the person's own used in a chat, in the app and in the terminal, and a flow run
from the command line whose reviewer carries a skill the flow brought and whose actor does
not. Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_skills.py`.
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
    from playwright.sync_api import Locator
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-skills"

_TASK = "Add a discount code to checkout"
_ANSWER = (
    "Checkout takes a discount code now: charge() looks the code up and takes its"
    " discount off the total. WELCOME10 is 10% off."
)
_NOTES = (
    "shop 0.4.0. New: checkout takes a discount code, and WELCOME10 is 10% off."
    " Changed: nothing else. Written the way the release-notes skill lays it out."
)

#: The person's own skill, as they installed it for Claude Code.
_SKILL = """---
name: release-notes
description: Write the release notes for a version from the commits since the last tag.
---

List what is new, what changed and what was fixed, one line each, newest first.
"""

#: The project's own skill, kept in the repository.
_PROJECT = """---
name: price-check
description: Check that every price in the catalogue is a whole number of cents.
---

Read shop/catalogue.py and report any price that is not a positive integer.
"""

#: The commands the stand-in says its conversation has, as Claude Code lists its own.
_COMMANDS = ["compact", "context", "init", "review", "security-review"]


def _installs_skills(world: World) -> None:
    """Puts a skill where the person keeps theirs, and one in the project."""
    yours = world.home / ".claude" / "skills" / "release-notes"
    yours.mkdir(parents=True)
    (yours / "SKILL.md").write_text(_SKILL)
    world.committed(
        "Add the price-check skill",
        {".claude/skills/price-check/SKILL.md": _PROJECT},
    )


def _reads_its_skills() -> None:
    """Teaches the stand-in `claude` to find its skills where Claude Code finds them.

    The conftest's stand-in lists no commands and no skills. A real Claude Code lists, in
    its `system/init`, the skills under its own home's `skills/` -- the home it was started
    in, which is the one Humanize built for it -- and under the project's `.claude/skills/`:
    so does this one, by reading those directories. A tool a line scripts with `runs` is a
    command it runs for real, in the environment it was started in, and what that printed is
    the tool's result, and stands where its answer says `{ran}`: so that what a picture shows
    of a session's skills is what is on disk.
    """
    found = shutil.which("claude")
    assert found is not None
    claude = Path(found)
    source = claude.read_text()
    init = 'out({"type": "system", "subtype": "init", "session_id": session, "model": model})'
    skip = '    if said.get("type") != "user":\n        continue\n'
    result = '        time.sleep(tool.get("takes", 0))\n'
    assert source.count(init) == 1
    assert source.count(skip) == 1
    assert source.count(result) == 1
    source = source.replace(
        init,
        "carried = sorted({one.parent.name for root in (home / 'skills',"
        " pathlib.Path('.claude/skills')) for one in root.glob('*/SKILL.md')})\n    "
        'out({"type": "system", "subtype": "init", "session_id": session, "model": model,'
        f' "slash_commands": {_COMMANDS!r} + carried, "skills": carried}})',
    )
    source = source.replace(
        skip,
        '    if said.get("type") == "control_request":\n'
        '        out({"type": "control_response", "response": {"subtype": "success",\n'
        '             "request_id": said["request_id"], "response": {}}})\n'
        "        continue\n" + skip,
    )
    source = source.replace(
        result,
        result + '        if tool.get("runs"):\n'
        "            import subprocess\n"
        '            tool["result"] = subprocess.run(\n'
        '                tool["input"]["command"], shell=True, capture_output=True,\n'
        "                text=True, check=False).stdout.strip()\n"
        '            text = text.replace("{ran}", ", ".join(tool["result"].split()))\n',
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


def test_a_skill_of_yours_is_used_in_a_chat(world: World) -> None:
    _installs_skills(world)
    _reads_its_skills()
    world.says({"release-notes": _NOTES, "discount": _ANSWER})
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        expect(
            page.get_by_role("button", name=re.compile("Nous: .*Haiku"))
        ).to_be_visible()
        first = page.get_by_role("textbox", name="First message")
        first.fill(_TASK)
        first.press("Enter")
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        log = page.get_by_role("log")
        expect(log).to_contain_text("WELCOME10")
        expect(page.get_by_role("button", name="Send")).to_be_visible()
        expect(page.get_by_role("link", name=_TASK).first).to_be_visible()
        box = page.get_by_role("textbox", name="What to say")
        offered = page.locator("[data-hmz=completions]")
        say = page.locator("[data-hmz=say]")
        box.fill("/comp")
        expect(offered).to_contain_text("/compact")
        box.fill("")

        reel = shots.Reel(f"{_PAGE}-chat", window="desktop")
        reel.web(page, hold=1.2, pointer=box, click=True)
        box.click()
        box.press_sequentially("/")
        expect(offered).to_contain_text("release-notes")
        reel.web(page, hold=1.6, keys="/", cut=True)
        shots.web(page, f"{_PAGE}-offered", clip=_around(say, offered), pad=0)
        box.press_sequentially("rel")
        expect(offered).not_to_contain_text("compact")
        reel.web(page, hold=2.2, keys="/rel", cut=True, caption="a skill of yours")
        box.press("Tab")
        expect(box).to_have_value("/release-notes ")
        reel.web(page, hold=1.2, keys="tab")
        reel.type(page, box, "for 0.4.0")
        box.press("Enter")
        expect(log).to_contain_text("shop 0.4.0")
        expect(page.get_by_role("button", name="Send")).to_be_visible()
        reel.web(page, hold=4, keys="enter", poster=True, caption="the agent uses it")
        reel.save()


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


async def test_a_skill_is_offered_in_the_terminal(world: World) -> None:
    _installs_skills(world)
    _reads_its_skills()
    world.says({"release-notes": _NOTES, "discount": _ANSWER})
    async with world.tui((96, 26)) as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*_TASK, "enter")
        await shows(pilot, "WELCOME10")
        await shows(pilot, "Worked for")
        await _settled(pilot)
        await pilot.press(*"/p")
        await shows(pilot, "/price-check")
        await _settled(pilot, 0.2)
        shots.tui(app, f"{_PAGE}-terminal")


#: What an agent runs to see what its own home holds as skills.
_LOOK = {
    "name": "Bash",
    "input": {"command": "ls $CLAUDE_CONFIG_DIR/skills"},
    "runs": True,
    "takes": 0.4,
}


def test_a_flow_brings_a_skill_to_one_role(world: World) -> None:
    _installs_skills(world)
    _reads_its_skills()
    world.says(
        {
            "meticulous reviewer": {
                "json": {
                    "done": True,
                    "notes": "charge() takes a code, tests pass. My skills: {ran}.",
                },
                "tools": [_LOOK],
            },
            "discount": {
                "text": "Checkout takes a discount code now. My skills: {ran}.",
                "tools": [_LOOK],
            },
        }
    )
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "rlar",
            "-a",
            f"actor={AGENT}",
            "-a",
            f"reviewer={AGENT}",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        f"{_PAGE}-exec",
    )

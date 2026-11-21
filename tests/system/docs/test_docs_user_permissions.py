"""The pictures of `docs/user/permissions.md`: what a chat and a flow's role may touch.

A chat's permission picked from its chip in the app, on a chat that has begun; the menu of
the three alone; a flow of the project's own, `audit`, whose one role is granted `read-only`,
run from the command line; and a chat in the terminal interface at the permission every chat
starts with.

Nothing a picture shows of a write refused is scripted. The stand-in agent is fenced by the
real fence, as every agent is, and here it is taught (`_runs_commands`) to really run the
commands a scripted line marks `runs`, in a shell of its own inside that fence: what a
picture shows as a command's result is what the shell printed, and the agent says its
`refused` words only where a command failed. Each scene then checks the file is not there.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_permissions.py`.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_tui import shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

_PAGE = "user-permissions"

_TASK = "Add a discount code to checkout"
_SAVE = "Save these notes to NOTES.md"
_BOTH = "Write inside.txt here and /Users/Shared/outside.txt"
_ANSWER = (
    "Checkout takes a discount code now: charge() looks the code up and takes its"
    " discount off the total. WELCOME10 is 10% off."
)

#: The project's own flow: one role, which may read everything and change nothing.
_FLOW = '''"""An auditor reads the project and reports; it may change nothing."""

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Permission,
    ShellEnvMixin,
    flow,
)


class Auditor(Agent):
    """Reads the work and changes nothing."""

    _permission = Permission("read-only")


class Agents(AgentCollection):
    auditor: Auditor


class Repo(LocalEnv, ShellEnvMixin):
    """The project."""


class Envs(EnvCollection):
    repo: Repo


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def audit(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """One agent reads the project and says what it found."""
    auditor = agents["auditor"]
    return await auditor.run(task, session=await auditor.spawn(), env=envs["repo"])
'''


def _runs_commands() -> None:
    """Teaches the stand-in agent to run a scripted tool's command for real.

    A tool of a line that says `"runs": True` is run by a shell, inside the fence the agent
    itself is held in, and its result is what that printed. Where one fails, the line's
    `refused` is what the agent answers in place of its `text`.
    """
    found = shutil.which("claude")
    assert found, "the world stages a stand-in claude"
    stand_in = Path(found)
    source = stand_in.read_text()
    was = (
        '        result = [{"type": "tool_result", "tool_use_id": ident,\n'
        '                   "content": tool.get("result", "")}]\n'
    )
    now = (
        '        printed = tool.get("result", "")\n'
        '        if tool.get("runs"):\n'
        "            import subprocess\n"
        '            ran = subprocess.run(tool["input"]["command"], shell=True,\n'
        "                                 capture_output=True, text=True, check=False)\n"
        '            printed = (ran.stdout + ran.stderr).strip() or "(no output)"\n'
        "            if ran.returncode:\n"
        '                text = line.get("refused", text)\n'
        '        result = [{"type": "tool_result", "tool_use_id": ident,\n'
        '                   "content": printed}]\n'
    )
    assert source.count(was) == 1, (
        "the stand-in claude no longer says a tool's result so"
    )
    stand_in.write_text(source.replace(was, now))


def _there(path: Path) -> bool:
    """Whether a file is there."""
    return path.exists()


def _gone(path: Path) -> None:
    """Removes a file, if it is there."""
    path.unlink(missing_ok=True)


def _tries(command: str, *, wrote: str, refused: str) -> dict[str, object]:
    """A scripted line: the agent runs one command for real, and says how it went."""
    return {
        "text": wrote,
        "refused": refused,
        "tools": [
            {"name": "Bash", "input": {"command": command}, "runs": True, "takes": 0.4}
        ],
        "after": 0.4,
    }


def test_a_chat_begun_is_set_to_read_only(world: World) -> None:
    _runs_commands()
    world.says(
        {
            "discount": _ANSWER,
            "NOTES": _tries(
                "echo 'WELCOME10 is 10% off' > NOTES.md",
                wrote="Saved the notes to NOTES.md.",
                refused="I could not save NOTES.md: this chat may not change files.",
            ),
        }
    )
    chat = world.chat(_TASK, going=True)
    with world.page(desktop=True) as page:
        go(page, f"/chats/{chat}")
        expect(page.get_by_role("log")).to_contain_text("WELCOME10")
        chip = page.locator("[data-hmz=permission]").first
        expect(chip).to_contain_text("Edit this folder")
        reel = shots.Reel(f"{_PAGE}-pick", window="desktop")
        reel.web(page, hold=1.6, pointer=chip, click=True)
        chip.click()
        menu = page.get_by_role("menu", name="Permissions")
        expect(menu).to_be_visible()
        read = menu.locator("[data-permission=read-only]")
        page.wait_for_timeout(300)
        shots.web(page, f"{_PAGE}-menu", clip=menu, pad=56)
        reel.web(page, hold=3.2, pointer=read, click=True)
        read.click()
        expect(chip).to_contain_text("Read only")
        page.wait_for_timeout(300)
        box = page.get_by_role("textbox", name="What to say")
        reel.web(page, hold=1.4, pointer=box, click=True)
        reel.type(page, box, _SAVE, per=9)
        box.press("Enter")
        expect(page.get_by_role("log")).to_contain_text("could not save")
        expect(page.get_by_role("button", name="Send")).to_be_visible()
        page.wait_for_timeout(300)
        reel.web(page, hold=5, poster=True)
        reel.save()
    assert world.call("chat.get", chat=chat)["permission"] == "read-only"
    assert not (world.workspace / "NOTES.md").exists()


def test_a_read_only_role_cannot_write(world: World) -> None:
    _runs_commands()
    flows = world.workspace / ".hmz" / "flows"
    flows.mkdir(parents=True, exist_ok=True)
    (flows / "audit.py").write_text(_FLOW)
    world.says(
        {
            "AUDIT": _tries(
                "echo 'checkout: no findings' > AUDIT.md",
                wrote="Wrote the findings to AUDIT.md.",
                refused=(
                    "The checkout has no findings. I could not write AUDIT.md:"
                    " this role may not change files."
                ),
            )
        }
    )
    reel = shots.Reel(f"{_PAGE}-exec")
    reel.cli(
        [
            "hmz",
            "exec",
            "-f",
            "@local/audit",
            "-a",
            f"auditor={AGENT}",
            "-p",
            "budget.output_tokens=20000",
            "Audit the checkout and write AUDIT.md",
        ],
        rows=12,
    )
    reel.save()
    assert not (world.workspace / "AUDIT.md").exists()


async def test_a_chat_in_the_terminal_writes_its_folder_only(world: World) -> None:
    # The made-up home is under the temporary directory, which a chat may write: what is
    # outside is a folder every user of a Mac may write, so that only the fence refuses it.
    if sys.platform != "darwin":
        pytest.skip("the folder outside the project is a Mac's /Users/Shared")
    outside = Path("/Users/Shared/outside.txt")
    assert not _there(outside), f"{outside} is somebody's own"
    _runs_commands()
    world.says(
        {
            "outside": _tries(
                f"echo hi > inside.txt; echo hi > {outside}",
                wrote="Wrote both files.",
                refused=(
                    f"inside.txt is written. {outside} was refused:"
                    " it is outside this folder."
                ),
            )
        }
    )
    try:
        async with world.tui((96, 16)) as (app, pilot):
            await shows(pilot, MODEL)
            await pilot.press(*_BOTH)
            await pilot.press("enter")
            await shows(pilot, "Worked for")
            await shows(pilot, "refused")
            await pilot.pause(0.4)
            shots.tui(app, f"{_PAGE}-terminal")
        assert _there(world.workspace / "inside.txt")
        assert not _there(outside)
    finally:
        _gone(outside)

"""The pictures of `docs/builder/skills.md`: what a flow's roles are given and held to.

The flow is the page's own, as the page prints it: a coder that may change the project but
not what is vendored in it, and a reviewer that reads only and carries a skill the flow
brings. It is run with `hmz exec`, shown in the app's New epic form, and refused where a
role names a skill the flow has not got or widens what it was granted.

Nothing a picture shows of a write refused or of a skill carried is scripted. The stand-in
agent is fenced by the real fence, and here it is taught (`_runs_commands`) to really run
the commands a scripted line marks `runs`, inside that fence: what a picture shows as a
command's doing is what happened, and each scene checks the files afterwards.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_builder_skills.py`.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.docs.conftest import AGENT
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "builder-skills"

_TASK = "Add a discount code to checkout"

#: The flow as the page prints it.
_GUARDED = '''
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Permission,
    deny,
    flow,
    read_only,
)


class Coder(Agent):
    """Changes the project, but not what is vendored in it."""

    _permission = Permission(
        preset="workspace-write",
        network=False,
        granular=(read_only("./vendor"), deny("~/.ssh")),
    )


class Reviewer(Agent):
    """Reads the change by the house style and changes nothing."""

    _permission = Permission(preset="read-only")
    _skills = ("house-style",)


class Agents(AgentCollection):
    coder: Coder
    reviewer: Reviewer


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def guarded(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """A fenced coder does the task; a read-only reviewer checks it."""
    coder, reviewer = agents["coder"], agents["reviewer"]
    workspace = envs["workspace"]
    await coder.run(task, session=await coder.spawn(), env=workspace)
    return await reviewer.run(
        "Review the change with the house-style skill.",
        session=await reviewer.spawn(),
        env=workspace,
    )
'''

#: The skill the flow brings, as the page prints it.
_SKILL = """---
name: house-style
description: Review a change against this team's house style.
---

Check that every public function has a docstring and a test, and that no price is a float.
"""

#: The same flow whose reviewer is derived with a permission wider than its own.
_WIDENED = _GUARDED.replace(
    "    await coder.run(task, session=await coder.spawn(), env=workspace)\n",
    "    await coder.run(task, session=await coder.spawn(), env=workspace)\n"
    '    reviewer = reviewer.derive(permission=Permission(preset="workspace-write"))\n',
)

#: What is vendored in the project, which the coder may read and not change.
_VENDORED = (
    '"""The payment client, vendored: change it upstream."""\n\nVERSION = "2.1.0"\n'
)


def _own(world: World, source: str = _GUARDED, *, skill: bool = True) -> None:
    """Puts the flow among the project's own, as `@local/guarded`, with its skill."""
    flow = world.workspace / ".hmz" / "flows" / "guarded"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(source.lstrip())
    if skill:
        at = flow / "skills" / "house-style"
        at.mkdir(parents=True)
        (at / "SKILL.md").write_text(_SKILL)


def _runs_commands() -> None:
    """Teaches the stand-in agent to run a scripted tool's command for real.

    A tool of a line that says `"runs": True` is run by a shell, inside the fence the agent
    itself is held in. Where one fails, the line's `refused` is what the agent answers in
    place of its `text`; and `{ran}` in what it answers is what the last of them printed.
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
        "            else:\n"
        '                text = text.replace("{ran}", ", ".join(ran.stdout.split()))\n'
        '        result = [{"type": "tool_result", "tool_use_id": ident,\n'
        '                   "content": printed}]\n'
    )
    assert source.count(was) == 1, (
        "the stand-in claude no longer says a tool's result so"
    )
    stand_in.write_text(source.replace(was, now))


class _Part:
    """A part of the page that no one element is: a box of it, found as a locator's is."""

    def __init__(self, left: float, top: float, right: float, bottom: float) -> None:
        self._box = {"x": left, "y": top, "width": right - left, "height": bottom - top}

    def bounding_box(self) -> dict[str, float]:
        return self._box


def _bash(command: str) -> dict[str, object]:
    return {"name": "Bash", "input": {"command": command}, "runs": True, "takes": 0.4}


def _exec() -> list[str]:
    return [
        "hmz",
        "exec",
        "-f",
        "@local/guarded",
        "-a",
        f"coder={AGENT}",
        "-a",
        f"reviewer={AGENT}",
        "-p",
        "budget.output_tokens=20000",
        _TASK,
    ]


def test_each_role_is_held_to_its_own(world: World) -> None:
    world.committed("Vendor the payment client", {"vendor/pay.py": _VENDORED})
    _own(world)
    _runs_commands()
    world.says(
        {
            "discount": {
                "text": "Wrote both files.",
                "refused": (
                    "Wrote shop/discounts.py. vendor/pay.py was refused:"
                    " this role only reads vendor/."
                ),
                "tools": [
                    _bash("echo 'CODES = {\"WELCOME10\": 10}' > shop/discounts.py"),
                    _bash("echo 'VERSION = \"2.2.0\"' > vendor/pay.py"),
                ],
            },
            "house-style": {
                "text": "The change follows the house style. My skills: {ran}.",
                "refused": "I could not list my skills.",
                "tools": [_bash("ls $CLAUDE_CONFIG_DIR/skills")],
            },
        }
    )
    shots.cli(_exec(), f"{_PAGE}-exec")
    assert (world.workspace / "shop" / "discounts.py").exists()
    assert (world.workspace / "vendor" / "pay.py").read_text() == _VENDORED


def test_the_app_says_what_each_role_is_held_to(world: World) -> None:
    _own(world)
    with world.page(desktop=True) as page:
        go(page, "/new")
        view = page.locator("[data-hmz=new-epic]")
        picker = view.locator("[data-hmz=flow-picker]")
        expect(picker.locator("b")).not_to_have_text("…")
        picker.click()
        page.get_by_text("@local/guarded", exact=True).click()
        expect(picker.locator("b")).to_have_text("@local/guarded")
        expect(view.locator('[data-hmz="role-row"]')).to_have_count(2)
        expect(view.get_by_text("Asking…")).to_have_count(0)
        name = view.locator('[data-role="reviewer"] .setup-name')
        name.hover()
        expect(page.get_by_text("skills: house-style")).to_be_visible()
        page.wait_for_timeout(300)
        whole, top = view.bounding_box(), picker.bounding_box()
        bottom = view.get_by_text("Budget", exact=True).bounding_box()
        assert whole is not None
        assert top is not None
        assert bottom is not None
        part = _Part(
            whole["x"],
            top["y"] - 14,
            whole["x"] + whole["width"],
            bottom["y"] + bottom["height"] + 8,
        )
        shots.web(page, f"{_PAGE}-role", clip=cast("Any", part), pad=0, pointer=name)


def test_a_skill_the_flow_has_not_got_is_refused(world: World) -> None:
    _own(world, skill=False)
    shots.cli(_exec(), f"{_PAGE}-missing")


def test_a_wider_permission_is_not_granted(world: World) -> None:
    _own(world, _WIDENED)
    shots.cli(_exec(), f"{_PAGE}-widened")

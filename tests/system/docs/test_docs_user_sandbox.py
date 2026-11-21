"""The pictures of `docs/user/sandbox.md`: the fence that holds an agent to its permission.

A flow of the project's own, `offline`, whose one role may write its folder and reach no
host (`network=False`), run from the command line and read back in the app.

Nothing a picture shows of a refusal is scripted. The stand-in agent is fenced by the real
fence, as every agent is, and here it is taught (`_runs_commands`) to really run the
commands a scripted line marks `runs`, in a shell of its own inside that fence: what a
picture shows as a command's result is what the shell printed, and the agent says its
`refused` words only where a command failed. Each scene then checks what the fence let
through and what it did not.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_sandbox.py`.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.docs.conftest import AGENT
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

_PAGE = "user-sandbox"

_TASK = "Note the release in NOTES.md and fetch example.com"

#: What the agent runs: a write inside its folder, then a host that is not its model's.
_COMMAND = "echo 'shop 0.3.0' > NOTES.md; curl -sS -m 20 https://example.com"

#: The project's own flow: one role, which writes its folder and reaches no host.
_FLOW = '''"""A writer works in the project with the network cut."""

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


class Writer(Agent):
    """Changes the project and reaches no host but its model's."""

    _permission = Permission("workspace-write", network=False)


class Agents(AgentCollection):
    writer: Writer


class Repo(LocalEnv, ShellEnvMixin):
    """The project."""


class Envs(EnvCollection):
    repo: Repo


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def offline(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """One agent does the task with the network cut."""
    writer = agents["writer"]
    return await writer.run(task, session=await writer.spawn(), env=envs["repo"])
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


def _staged(world: World) -> None:
    """The flow in the project, and the agent set to try both sides of its fence."""
    _runs_commands()
    flows = world.workspace / ".hmz" / "flows"
    flows.mkdir(parents=True, exist_ok=True)
    (flows / "offline.py").write_text(_FLOW)
    world.says(
        {
            "NOTES": {
                "text": "Wrote NOTES.md and fetched example.com.",
                "refused": (
                    "NOTES.md is written. example.com was refused:"
                    " this role has no network."
                ),
                "tools": [
                    {
                        "name": "Bash",
                        "input": {"command": _COMMAND},
                        "runs": True,
                        "takes": 0.4,
                    }
                ],
                "after": 0.4,
            }
        }
    )


def test_a_role_with_no_network_reaches_no_host(world: World) -> None:
    _staged(world)
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "@local/offline",
            "-a",
            f"writer={AGENT}",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        f"{_PAGE}-exec",
        columns=96,
    )
    assert (world.workspace / "NOTES.md").read_text() == "shop 0.3.0\n"


def test_the_app_shows_what_the_fence_refused(world: World) -> None:
    _staged(world)
    name = world.epic("@local/offline", _TASK, agents={"writer": AGENT})
    assert (world.workspace / "NOTES.md").read_text() == "shop 0.3.0\n"
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        graph = page.locator("[data-hmz=graph]")
        writer = graph.locator("[data-hmz=graph-agent]").filter(has_text="writer")
        writer.locator(".node-head").click()
        page.wait_for_timeout(1000)
        writer.locator("[data-hmz=graph-session]").first.click()
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("refused")
        # The panel shut, and the command opened to what it really printed.
        page.get_by_role("button", name="Toggle panel").click()
        page.wait_for_timeout(800)
        thread.get_by_text("Bash:").first.click()
        page.wait_for_timeout(800)
        expect(thread).to_contain_text("CONNECT tunnel failed")
        shots.web(page, f"{_PAGE}-thread", clip=thread, pad=24)

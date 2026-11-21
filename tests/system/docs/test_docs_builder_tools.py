"""The pictures of `docs/builder/tools.md`: a flow's own tool and command line, called by an agent.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_builder_tools.py`.
"""

from __future__ import annotations

import re
import subprocess
import sys
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.docs.conftest import AGENT
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

_PAGE = "builder-tools"
_TASK = "The build is red: find out why"

#: The page's flow, as the page prints it: a triager with a tool and a command line.
_TRIAGE = r'''
import pydantic

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FakeCli,
    FakeCommand,
    FakeTool,
    FakeToolAgentMixin,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)

OWNERS = {"shop/checkout.py": "payments", "shop/cart.py": "storefront"}


class File(pydantic.BaseModel):
    path: str = pydantic.Field(description="A file of this repository.")


def owner(asked: File) -> str:
    return OWNERS.get(asked.path, "nobody")


tickets: list[str] = []


class Ticket(pydantic.BaseModel):
    title: str = pydantic.Field(description="What the ticket says.")
    urgent: bool = pydantic.Field(False, description="Whether it jumps the queue.")


def file(ticket: Ticket) -> str:
    tickets.append(("urgent: " if ticket.urgent else "") + ticket.title)
    return f"filed #{len(tickets)}"


def listed() -> list[str]:
    return tickets


class Triager(Agent, FakeToolAgentMixin):
    _tools = (
        FakeTool("owner", "Says which team owns a file of this repository.", owner, File),
    )
    _clis = (
        FakeCli(
            "tix",
            "Files and lists the tickets of this run.",
            (
                FakeCommand("file", "Files a ticket.", file, Ticket),
                FakeCommand("list", "Lists the tickets filed so far.", listed),
            ),
        ),
    )


class Agents(AgentCollection):
    triager: Triager


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def triage(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> list[str]:
    """Find what is wrong and file a ticket for the team that owns it."""
    triager = agents["triager"]
    tickets.clear()
    prompt = (
        f"{task}\n\nCall the `owner` tool to find the team that owns a file. "
        "File each problem with `tix file`; `tix --help` says how."
    )
    await triager.run(prompt, session=await triager.spawn(), env=envs["workspace"])
    return list(tickets)
'''

# `tix` as the agent's shell finds it, for a picture of what it prints with no agent in
# it: the flow's own `FakeCli`, answered by its `run`, which is what answers the agent's.
_TIX = """
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("triage", {flow!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
status, out, err = module.Triager._clis[0].run(sys.argv[1:])
sys.stdout.write(out)
sys.stderr.write(err)
sys.exit(status)
"""

# The stand-in agent, taught to do what a scripted tool call says for real where the line
# marks it `real`: a tool of the flow's is called over the bridge the flow serves it on, and
# a command is run by the shell on the PATH the agent was given. What came back is what the
# transcript holds, and `{0}`, `{1}`... in the answer are the results, in order.
_REALLY = """
REAL = []


def really(one):
    said = one.get("result", "")
    if one.get("real"):
        import subprocess

        if one["name"] == "Bash":
            ran = subprocess.run(one["input"]["command"], shell=True, text=True,
                                 capture_output=True, check=False)
            said = ran.stdout + ran.stderr
        else:
            asked = one["name"].rpartition("__")[2] + " " + json.dumps(one["input"])
            said = tool(asked).partition("; said: ")[2]
    REAL.append(said.strip())
    return said


"""

#: What the triager does when told the task: the last three for real.
_WORK = {
    "text": "test_total fails: total() ignores the coupon. shop/checkout.py belongs to"
    " {1}, so I {3} for them, as urgent.",
    "tools": [
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": "1 failed, 1 passed in 0.19s",
            "takes": 0.5,
        },
        {
            "name": "mcp__humanize__owner",
            "input": {"path": "shop/checkout.py"},
            "real": True,
            "takes": 0.3,
        },
        {
            "name": "Bash",
            "input": {"command": "tix --help"},
            "real": True,
            "takes": 0.3,
        },
        {
            "name": "Bash",
            "input": {
                "command": "tix file --urgent --title 'payments: total() ignores the coupon'"
            },
            "real": True,
            "takes": 0.3,
        },
    ],
}


def _own(world: World) -> None:
    """Puts the page's flow among the project's own, as `@local/triage`."""
    flow = world.workspace / ".hmz" / "flows" / "triage"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(_TRIAGE)


def _really(world: World) -> None:
    """Has the stand-in agent make the calls a line marks `real`, and say what they said."""
    claude = world.home.parent / "bin" / "claude"
    source = claude.read_text()
    for was, now in (
        ("\ndef scripted(said):\n", f"\n{_REALLY.strip()}\n\n\ndef scripted(said):\n"),
        ('"content": tool.get("result", "")}]', '"content": really(tool)}]'),
        ("    return text\n", "    return text.format(*REAL) if REAL else text\n"),
    ):
        assert source.count(was) == 1, f"the stand-in claude no longer says {was!r}"
        source = source.replace(was, now)
    claude.write_text(source)


def test_the_command_line_as_the_agent_finds_it(world: World) -> None:
    _own(world)
    flow = world.workspace / ".hmz" / "flows" / "triage" / "__init__.py"
    tix = world.home.parent / "bin" / "tix"
    tix.write_text(f"#!{sys.executable}\n{_TIX.format(flow=str(flow))}")
    tix.chmod(0o755)
    subprocess.run([str(tix), "--help"], check=True, capture_output=True)
    reel = shots.Reel(f"{_PAGE}-cli")
    reel.cli(["tix", "--help"], rows=13, hold=2.6)
    reel.cli(["tix", "file", "--help"], rows=13, hold=2.6)
    reel.cli(["tix", "file"], rows=13, hold=2.2)
    reel.cli(["tix", "file", "--title", "the build is red"], rows=13, hold=2.2)
    reel.save()


def test_the_agent_calls_the_tool_and_runs_the_command_line(world: World) -> None:
    _own(world)
    _really(world)
    world.says({"build is red": _WORK})
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "@local/triage",
            "-a",
            f"triager={AGENT}",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        f"{_PAGE}-exec",
    )


def test_the_app_shows_the_calls_among_the_agent_s_work(world: World) -> None:
    _own(world)
    _really(world)
    world.says({"build is red": _WORK})
    name = world.epic("@local/triage", _TASK)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        # The triager's one session, in the sidebar under the epic: its transcript.
        page.get_by_text(re.compile(r"^\w+/1$")).first.click()
        expect(page.get_by_text("belongs to payments").first).to_be_visible()
        expect(page.get_by_text("mcp__humanize__owner").first).to_be_visible()
        page.wait_for_timeout(800)
        shots.web(page, f"{_PAGE}-app", clip=page.get_by_role("log").first, pad=16)

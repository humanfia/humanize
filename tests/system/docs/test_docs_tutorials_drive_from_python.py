"""The pictures of `docs/tutorials/drive-from-python.md`: a script runs a flow through the SDK.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_tutorials_drive_from_python.py`.

The flow and the scripts are the page's own, character for character: what the page prints
is what ran here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

_TASK = "Add a coupon code to checkout"

#: Step 1 of the page: the project's own flow, `.hmz/flows/ship.py`.
_SHIP = '''
from typing import Literal

import pydantic

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Markdown,
    Outworlder,
    flow,
)


class Decision(pydantic.BaseModel):
    """What the person decides."""

    action: Literal["ship", "hold"] = "hold"
    notes: str = ""


class Agents(AgentCollection):
    coder: Agent
    human: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def ship(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """A coder does the task, and a person decides whether it ships."""
    coder, human = agents["coder"], agents["human"]
    said = await coder.run(task, session=await coder.spawn(), env=envs["workspace"])
    decision = await human.run(
        "Ship this change?",
        session=await human.spawn(),
        output_schema=Decision,
        context=(Markdown(text=said),),
    )
    return decision.action
'''

#: Step 2: the shortest script that runs it, `drive.py`.
_FIRST = """
from hmz.sdk import Hmz

run = Hmz().run(
    "ship",
    "Add a coupon code to checkout",
    agents={"coder": "claude/claude-haiku-4-5"},
    budget={"output_tokens": 20000},
)
print("result:", run.run())
"""

#: Step 3: what replaces the script's last line, to follow the run.
_FOLLOW = """
def opened(role, session):
    print(f"[{role}] {session.cli} {session.model} opened")


def event(agent, session, record):
    if record["text"]:
        print(f"  {record['kind']}: {record['text'][:60]}")


run.opened(opened)
run.watch(event)
run.start()
run.wait()
print(f"result: {run.result!r}, raised: {run.raised!r}")
"""

#: Step 4: what replaces the script's import, to answer the flow's question.
_REVIEWER = """
from hmz.sdk import Ask, Hmz


class Reviewer:
    def away_for(self, role: str) -> bool:
        return False

    async def run(self, ask: Ask, role: str) -> dict[str, str]:
        print(f"[{role}] asked: {ask.prompt}")
        print(f"  choices: {ask.schema['properties']['action']['enum']}")
        return {"action": "ship", "notes": "approved by drive.py"}
"""

#: Step 4: the argument that hands the reviewer to the run.
_GIVEN = "    outworlder=Reviewer(),\n"

#: Step 5: what is added at the end, to read what the run spent.
_SPENT = """
usage = run.usage
print(f"spent: {usage.output_tokens} output tokens, {usage.duration.total_seconds():.0f}s")
print("epic:", run.epic.name)
"""

#: Step 6: what replaces `run.wait()`, to stop a run that takes too long.
_STOP = """
if not run.wait(timeout=5):
    print("too slow, stopping")
    run.stop()
    run.wait()
"""


def _swapped(script: str, was: str, now: str) -> str:
    """A script with one piece of it replaced, which must be there exactly once."""
    assert script.count(was) == 1, f"the script does not say {was!r} once"
    return script.replace(was, now)


_FOLLOWED = _swapped(_FIRST, 'print("result:", run.run())\n', _FOLLOW.lstrip("\n"))
_ANSWERED = (
    _swapped(
        _swapped(_FOLLOWED, "\nfrom hmz.sdk import Hmz\n", _REVIEWER + "\n"),
        '    budget={"output_tokens": 20000},\n',
        '    budget={"output_tokens": 20000},\n' + _GIVEN,
    )
    + _SPENT
)
_STOPPED = _swapped(_ANSWERED, "\nrun.wait()\n", _STOP)

#: What the coder does when told the task.
_WORK = {
    "text": "Checkout takes a coupon now: WELCOME10 is 10% off. The tests pass.",
    "tools": [
        {
            "name": "Edit",
            "input": {"file_path": "shop/checkout.py"},
            "result": "edited",
            "takes": 0.5,
        },
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": "5 passed in 0.18s",
            "takes": 0.7,
        },
    ],
    "after": 0.6,
}


def _staged(world: World, script: str) -> None:
    """Puts the flow among the project's own and the script beside it, as the page says to."""
    flows = world.workspace / ".hmz" / "flows"
    flows.mkdir(parents=True, exist_ok=True)
    (flows / "ship.py").write_text(_SHIP)
    (world.workspace / "drive.py").write_text(script)


def test_a_script_runs_a_flow_and_prints_what_it_returned(world: World) -> None:
    _staged(world, _FIRST)
    world.says({"coupon": _WORK})
    shots.cli(["python", "drive.py"], "tutorials-drive-from-python-first")


def test_the_script_follows_the_run_as_it_goes(world: World) -> None:
    _staged(world, _FOLLOWED)
    world.says({"coupon": _WORK})
    reel = shots.Reel("tutorials-drive-from-python-followed")
    reel.cli(["python", "drive.py"], rows=11)
    reel.save()


def test_the_script_answers_the_question_and_the_app_shows_the_epic(
    world: World,
) -> None:
    _staged(world, _ANSWERED)
    world.says({"coupon": _WORK})
    shots.cli(["python", "drive.py"], "tutorials-drive-from-python-answered")
    with world.page(desktop=True) as page:
        name = world.call("runs.list", workspace=str(world.workspace))["runs"][0][
            "name"
        ]
        go(page, f"/epics/{name}")
        expect(page.get_by_text("output tokens", exact=True)).to_be_visible()
        expect(page.get_by_text("1 turn", exact=True)).to_be_visible()
        shots.web(
            page, "tutorials-drive-from-python-app", window="desktop", most=shots.REEL
        )


def test_the_script_stops_a_run_that_takes_too_long(world: World) -> None:
    _staged(world, _STOPPED)
    world.says({"coupon": _WORK | {"after": 60}})
    shots.cli(["python", "drive.py"], "tutorials-drive-from-python-stopped")

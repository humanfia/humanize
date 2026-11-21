"""The pictures of `docs/builder/resumable.md`: a flow of the project's own, picked up.

The flow is the page's own, as the page prints it: `in_rounds` hands a coder the task for
four rounds in one conversation, and keeps the round it finished and the conversation in its
state. It is run with `hmz exec` under a budget that ends it after two rounds, its journal
is printed, and it is run again with `--resume`, which goes on at round three -- read back
in the app as the session that carried the kept conversation on.
Run it by naming it: `uv run pytest tests/system/docs/test_docs_builder_resumable.py`.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.docs.conftest import AGENT
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "builder-resumable"

_TASK = "Add a discount code to checkout"

#: The flow as the page prints it.
_IN_ROUNDS = '''
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


class Params(FlowParams):
    rounds: int = 4


@flow(agents=Agents, envs=Envs, params=Params, resumable=True)
async def in_rounds(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> int:
    """Work on the task in rounds, picking up at the round it stopped in."""
    coder, workspace = agents["coder"], envs["workspace"]
    state = ctx.state
    assert state is not None  # a resumable flow always has one
    done = state["done"] if "done" in state else 0
    session = state["session"] if "session" in state else await coder.spawn()
    for n in range(done + 1, params.rounds + 1):
        prompt = f"{task}\\n\\nThis is round {n} of {params.rounds}."
        await coder.run(prompt, session=session, env=workspace)
        state["session"] = session  # the conversation as it stands now
        state["done"] = n  # on disk before this line returns
    return params.rounds
'''

#: What the agent says of the task, round after round.
_ROUNDS = [
    "Round 1: charge() takes a code now, and WELCOME10 takes 10% off.",
    "Round 2: covered the code with tests. An unknown code changes nothing. 3 passed.",
    "Round 3: a code past its date is refused, with a test for it. 4 passed.",
    "Round 4: wrote the codes up in README.md. Nothing is left to do.",
]

#: What ends the first epic after two rounds, and what lets the second finish.
_SHORT = "budget.output_tokens=160"
_ENOUGH = "budget.output_tokens=20000"


#: The program of the page's own that picks the epic up, as the page prints it.
_CARRY_ON = """
from hmz.sdk import Hmz

hmz = Hmz()
epic = hmz.epics.resumed("@local/in_rounds")
print("picks up:", epic.name)
print("rounds done:", hmz.epics.state(epic)["done"])

run = hmz.run(
    "@local/in_rounds",
    "Add a discount code to checkout",
    agents={"coder": "claude/claude-haiku-4-5"},
    budget={"output_tokens": 20000},
    resume=True,
)
print("returned:", run.run())
"""


def _staged(world: World) -> None:
    """The flow where the page says to put it, and what its agent says round by round."""
    flows = world.workspace / ".hmz" / "flows"
    shutil.rmtree(flows)
    (flows / "in_rounds").mkdir(parents=True)
    (flows / "in_rounds" / "__init__.py").write_text(_IN_ROUNDS.lstrip())
    world.says({"discount": {"text": _ROUNDS}})


def _exec(budget: str, *more: str) -> list[str]:
    return [
        "hmz",
        "exec",
        "-f",
        "@local/in_rounds",
        *more,
        "-a",
        f"coder={AGENT}",
        "-p",
        budget,
        _TASK,
    ]


def test_a_stopped_run_is_picked_up_at_its_round(world: World) -> None:
    _staged(world)
    shots.cli(_exec(_SHORT), f"{_PAGE}-stopped", columns=92)
    # What it wrote down, with the staged home said as a person would say it.
    shots.cli(
        ["sh", "-c", 'cat ~/.hmz/epics/*/*/resume.jsonl | sed "s#$HOME#~#"'],
        f"{_PAGE}-journal",
        columns=118,
    )
    shots.cli(_exec(_ENOUGH, "--resume"), f"{_PAGE}-resumed", columns=103)

    # The epic that picked it up, in the app: its session carries the kept conversation on.
    runs = world.call("runs.list", workspace=str(world.workspace))["runs"]
    name = max(str(one["name"]) for one in runs)
    with world.page(desktop=True, height=700) as page:
        go(page, f"/epics/{name}")
        page.locator("[data-hmz=graph-session]").first.click()
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("This is round 1 of 4.")
        expect(thread).to_contain_text("This is round 3 of 4.")
        expect(thread).to_contain_text("Nothing is left to do.")
        page.wait_for_timeout(1000)
        shots.web(page, f"{_PAGE}-thread", window="desktop", most=shots.REEL)


def test_a_program_reads_the_state_and_picks_the_epic_up(world: World) -> None:
    _staged(world)
    world.epic("@local/in_rounds", _TASK, budget={"output_tokens": 160})
    (world.workspace / "carry_on.py").write_text(_CARRY_ON.lstrip())
    shots.cli(["python", "carry_on.py"], f"{_PAGE}-python")

"""The pictures of `docs/builder/budgets.md`: a flow that reads and sets budgets, as it runs.

The page's two flows, as the page prints them, are a project's own here: `capped`, whose
turns each have a time limit of their own, and `drafted`, which calls a flow under a budget
of its own. Run it by naming it: `uv run pytest tests/system/docs/test_docs_builder_budgets.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.docs.conftest import AGENT
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "builder-budgets"

_TASK = "Add a discount code to checkout"

#: The page's first flow, as the page prints it: every turn under a time limit of its own.
_CAPPED = '''
import datetime

from hmz.flows import (
    Agent,
    AgentCollection,
    Budget,
    BudgetExceeded,
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
    seconds: float = 600
    """The most one turn may take."""


@flow(agents=Agents, envs=Envs, params=Params)
async def capped(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> str:
    """Up to four rounds on a task, each turn held to a time limit of its own."""
    coder, workspace = agents["coder"], envs["workspace"]
    session = await coder.spawn()
    turn = Budget(duration=datetime.timedelta(seconds=params.seconds), graceful=False)
    cut = 0
    for round in range(4):
        allowed = ctx.budget.output_tokens  # None when no token limit is set
        if allowed is not None and allowed - ctx.usage.output_tokens < 500:
            break  # too little left for a useful round: end normally
        try:
            await coder.run(
                task if round == 0 else "Carry on.",
                session=session,
                env=workspace,
                budget=turn,
            )
        except BudgetExceeded as spent:
            if not spent.own:
                raise  # the epic's budget is spent: let it end the epic
            cut += 1  # only this turn's limit: the flow goes on
    return f"{cut} turns cut off, {ctx.usage.output_tokens} output tokens written"
'''

#: The page's second flow, as the page prints it: a flow called under a budget of its own.
_DRAFTED = '''
from hmz.flows import (
    Agent,
    AgentCollection,
    Budget,
    BudgetExceeded,
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


@flow(agents=Agents, envs=Envs, params=FlowParams, hidden=True)
async def polish(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Round after round on one task, until its budget ends it."""
    coder = agents["coder"]
    session = await coder.spawn()
    while True:
        await coder.run(f"Polish: {task}", session=session, env=envs["workspace"])


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def drafted(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """A draft, some polish under a budget of its own, then a summary."""
    coder, workspace = agents["coder"], envs["workspace"]
    session = await coder.spawn()
    await coder.run(task, session=session, env=workspace)
    try:
        await polish(
            task,
            agents=agents,
            envs=envs,
            params=params,
            budget=Budget(output_tokens=300),
        )
    except BudgetExceeded:
        pass  # the polish spent its share; the next turn raises if the epic's is spent too
    return await coder.run("Summarise the change.", session=session, env=workspace)
'''

#: What the coder says of the task, and of being told to carry on, round after round. The
#: scene of the cut-off turn has it take the task slowly: longer than a turn is given.
_SAYS = {
    "discount": "Checkout takes a discount code now: WELCOME10 is 10% off.",
    "Carry on": {
        "text": [
            "Covered the code with tests: an unknown code changes nothing. 3 passed.",
            "Refused a code past its date, with a test for it. 4 passed.",
            "Read it through again: the discount code works and its tests pass.",
        ],
    },
}


def _own(world: World, name: str, source: str) -> None:
    """Puts a flow among the project's own, as `@local/<name>`."""
    flow = world.workspace / ".hmz" / "flows" / name
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(source)


def test_a_turn_over_its_own_limit_is_cut_off_and_the_flow_goes_on(
    world: World,
) -> None:
    _own(world, "capped", _CAPPED)
    world.says(
        _SAYS
        | {
            "discount": {
                "text": "Still reading the checkout.",
                "after": 6,
            }
        }
    )
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "@local/capped",
            "-a",
            f"coder={AGENT}",
            "-p",
            "budget.output_tokens=20000",
            "-p",
            "seconds=2",
            _TASK,
        ],
        f"{_PAGE}-exec",
    )


def test_a_called_flow_is_ended_by_its_own_budget_in_the_app(world: World) -> None:
    _own(world, "drafted", _DRAFTED)
    world.says(
        {
            "Polish": [
                "Named the discount table, and typed charge() throughout.",
                "Moved the codes into shop/discounts.py.",
                "Rounded a discount down to a whole cent.",
                "Wrote the codes up in README.md.",
            ],
            "discount": "Checkout takes a discount code now: WELCOME10 is 10% off.",
            "Summarise": "A discount code at checkout, tested, with the codes in a file.",
        }
    )
    name = world.epic("@local/drafted", _TASK, budget={"output_tokens": 20000})
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_text("Done", exact=True).first).to_be_visible()
        expect(page.get_by_text("drafted:polish")).to_be_visible()
        expect(page.get_by_text("Reading handovers")).to_have_count(0)
        expect(page.get_by_text("Reading its turns")).to_have_count(0)
        shots.web(page, f"{_PAGE}-called", window="desktop", most=shots.REEL)

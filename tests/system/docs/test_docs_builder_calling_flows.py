"""The pictures of `docs/builder/calling-flows.md`: a flow that calls two others, as it runs.

The page's flow, as the page prints it, is a project's own here: `shipped`, which calls the
installed `goal` and then a hidden flow of its own module, `review`, under a budget of its
own. Run it by naming it: `uv run pytest tests/system/docs/test_docs_builder_calling_flows.py`.
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
_PAGE = "builder-calling-flows"

_TASK = "Add a discount code to checkout"

#: The page's flow, as the page prints it.
_SHIPPED = '''
from hmz.flows import (
    Agent,
    AgentCollection,
    Budget,
    EnvCollection,
    FlowContext,
    FlowParams,
    GoalCommandAgentMixin,
    LocalEnv,
    flow,
    load,
)


class Coder(Agent, GoalCommandAgentMixin): ...


class Agents(AgentCollection):
    coder: Coder


class Reviewers(AgentCollection):
    reviewer: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


class Focus(FlowParams):
    focus: str = "bugs"


@flow(agents=Reviewers, envs=Envs, params=Focus, name="review", hidden=True)
async def review(
    task: str, *, agents: Reviewers, envs: Envs, params: Focus, ctx: FlowContext
) -> str:
    """Read the change and say what is wrong with it."""
    reviewer = agents["reviewer"]
    session = await reviewer.spawn()
    return await reviewer.run(
        f"Review the change for {params.focus}: {task}",
        session=session,
        env=envs["workspace"],
    )


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def shipped(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """The task as a goal, then a review of the change."""
    goal = load("goal")
    await goal(
        task,
        agents={"worker": agents["coder"]},
        envs={},
        params=goal.expected_params(),
    )
    review = load(":review")
    return await review(
        task,
        agents={"reviewer": agents["coder"]},
        envs=envs,
        params=review.expected_params(focus="security"),
        budget=Budget(output_tokens=2000),
    )
'''

#: The same flow with its role typed a plain `Agent`: less than `goal`'s `worker` asks for.
_PLAIN = _SHIPPED.replace(
    "class Coder(Agent, GoalCommandAgentMixin): ...", "Coder = Agent"
)

#: What the coder says as `goal`'s worker, and as the reviewer of its own change.
_SAYS = {
    "Review the change": "One problem: an unknown code raises KeyError. Use CODES.get(code, 0).",
    "discount": "Goal met: charge() takes a code now, and WELCOME10 takes 10% off.",
}


def _own(world: World, source: str) -> None:
    """Puts the flow among the project's own, as `@local/shipped`."""
    flow = world.workspace / ".hmz" / "flows" / "shipped"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(source.lstrip())


def _exec() -> list[str]:
    return [
        "hmz",
        "exec",
        "-f",
        "@local/shipped",
        "-a",
        f"coder={AGENT}",
        "-p",
        "budget.output_tokens=20000",
        _TASK,
    ]


def test_each_called_flow_takes_its_turn_under_its_own_role_name(world: World) -> None:
    _own(world, _SHIPPED)
    world.says(_SAYS)
    shots.cli(_exec(), f"{_PAGE}-exec")


def test_a_call_that_hands_on_too_little_is_refused_before_it_starts(
    world: World,
) -> None:
    assert _PLAIN != _SHIPPED
    _own(world, _PLAIN)
    world.says(_SAYS)
    shots.cli(_exec(), f"{_PAGE}-refused")


def test_the_calls_are_branches_of_the_epic_in_the_app(world: World) -> None:
    _own(world, _SHIPPED)
    world.says(_SAYS)
    name = world.epic("@local/shipped", _TASK, budget={"output_tokens": 20000})
    # Short enough that the panel ends at its list of called flows, which is the point.
    with world.page(desktop=True, height=568) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_text("Done", exact=True).first).to_be_visible()
        expect(page.get_by_text("shipped:review")).to_be_visible()
        expect(page.get_by_text("Reading handovers")).to_have_count(0)
        expect(page.get_by_text("Reading its turns")).to_have_count(0)
        page.get_by_role("button", name="Recenter").click()
        page.wait_for_timeout(600)
        shots.web(page, f"{_PAGE}-called", window="desktop", most=shots.REEL)

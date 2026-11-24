"""The pictures of `docs/builder/outworlder.md`: a flow with a person as one of its agents.

The flows are the page's own, written into the project word for word as the page has them:
`approve`, whose agent does the task and whose person is told the work is done, shown what
changed and asked whether to keep it; and `judged`, which calls `approve` and has an agent
answer in the person's place. `approve` is asked in the app and in the terminal, and run
from a command line where nobody is there; `judged` is run from a command line. Run it by
naming it: `uv run pytest tests/system/docs/test_docs_builder_outworlder.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.integration.doubles_tui import shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "builder-outworlder"

_TASK = "Add a discount code to checkout"

#: The page's first flow, as the page prints it.
_APPROVE = '''"""Approve: an agent does the task, and a person decides whether to keep it."""

from pydantic import BaseModel, Field

from hmz.flows import (
    Agent,
    AgentCollection,
    Diff,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Markdown,
    Outworlder,
    ShellEnvMixin,
    Table,
    flow,
)


class Review(BaseModel):
    keep: bool = Field(False, description="Keep the change.")
    notes: str = Field("", description="What to change, if anything.")


class Agents(AgentCollection):
    coder: Agent
    human: Outworlder


class Workspace(LocalEnv, ShellEnvMixin): ...


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def approve(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> bool:
    """An agent does the task, and a person decides whether to keep it."""
    coder, human = agents["coder"], agents["human"]
    workspace = envs["workspace"]
    work = await coder.spawn()
    asking = await human.spawn()
    said = await coder.run(task, session=work, env=workspace)
    await human.show(
        (Markdown(text="The coder is done. Running the checks."),), session=asking
    )
    _, patch, _ = await workspace.exec(["git", "diff"])
    code, _, _ = await workspace.exec(["python", "-m", "compileall", "-q", "."])
    review = await human.run(
        "Keep this change?",
        session=asking,
        output_schema=Review,
        context=(
            Markdown(title="What the coder says", text=said),
            Diff(patch=patch),
            Table(
                title="Checks",
                columns=("check", "result"),
                rows=(("compiles", "yes" if code == 0 else "no"),),
            ),
        ),
    )
    if review.keep:
        title = await human.run("What should the commit say?", session=asking)
        await coder.run(f"Commit the change as: {title or task}", session=work, env=workspace)
    else:
        await coder.run(f"Undo the change. {review.notes}", session=work, env=workspace)
    return review.keep
'''

#: The page's second flow, as the page prints it.
_JUDGED = '''"""Judged: run approve, with an agent answering in the person's place."""

from hmz.flows import (
    Agent,
    AgentCollection,
    Diff,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Outworlder,
    OutworlderRunHookParams,
    OutworlderRunHookResult,
    ShellEnvMixin,
    flow,
    load,
)

approve = load("approve")


class Agents(AgentCollection):
    coder: Agent
    judge: Agent


class Workspace(LocalEnv, ShellEnvMixin): ...


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def judged(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> bool:
    """Run approve, with an agent answering in the person's place."""
    judge = agents["judge"]
    judging = await judge.spawn()

    async def answer(asked: OutworlderRunHookParams) -> OutworlderRunHookResult:
        if asked.output_schema is None:
            return OutworlderRunHookResult(output="")
        patch = "".join(b.patch for b in asked.context if isinstance(b, Diff))
        verdict = await judge.run(
            f"{asked.prompt}\\n\\n{patch}",
            session=judging,
            env=envs["workspace"],
            output_schema=asked.output_schema,
        )
        return OutworlderRunHookResult(output=verdict)

    stand_in = Outworlder.new()
    stand_in.on_outworlder_run(answer)
    return await approve(
        task,
        agents={"coder": agents["coder"], "human": stand_in},
        envs=envs,
        params=FlowParams(),
    )
'''

_CHECKOUT = '''"""Paying for a cart."""

from shop.cart import total

CODES = {"WELCOME10": 10}


def charge(items: dict[str, int], code: str = "") -> int:
    """What is charged for a cart, in cents, less what a code takes off."""
    owed = total(items)
    return owed - owed * CODES.get(code, 0) // 100
'''

#: What the agents say: the judge, asked for a schema, and the coder, told the task.
_WORK = {
    "Keep this change?": {"json": {"keep": True, "notes": ""}},
    "Undo the change": "Undid the change: checkout is as it was.",
    "Commit the change": "Committed it: Add a discount code.",
    "discount": {
        "text": (
            "Checkout takes a discount code now: charge() looks the code up and takes"
            " its discount off the total. WELCOME10 is 10% off."
        ),
        "writes": {"shop/checkout.py": _CHECKOUT},
    },
}


def _own(world: World) -> None:
    """Commits the page's flows into the project, as `@local/approve` and `@local/judged`.

    Committed, so that the diff the person is shown is of what the agent changed alone.
    """
    world.committed(
        "Add the approve and judged flows",
        {
            ".hmz/flows/approve/__init__.py": _APPROVE,
            ".hmz/flows/judged/__init__.py": _JUDGED,
            ".gitignore": "__pycache__/\n",
        },
    )
    world.says(_WORK)


def _exec(flow: str, roles: tuple[str, ...], name: str) -> None:
    argv = ["hmz", "exec", "-f", flow]
    for role in roles:
        argv += ["-a", f"{role}={AGENT}"]
    argv += ["-p", "budget.duration=10m", "Add a discount code"]
    shots.cli(argv, name, columns=100)


def test_the_person_is_asked_in_the_app(world: World) -> None:
    _own(world)
    name = world.epic("@local/approve", _TASK, until="asked")
    with world.page(desktop=True, height=1040) as page:
        go(page, f"/epics/{name}")
        card = page.locator('[data-hmz="question"]').first
        expect(card.get_by_text("Keep this change?")).to_be_visible(timeout=60_000)
        expect(card.get_by_text("in 1 file")).to_be_visible()
        page.wait_for_timeout(800)
        shots.web(page, f"{_PAGE}-asked", window="desktop", most=shots.REEL)
        shots.web(page, f"{_PAGE}-card", clip=card, pad=0)
        # What `show` put in front of the person: in their own log, opened from the graph.
        page.get_by_text("a person").first.click()
        told = page.locator('[data-hmz="said-shown"]').first
        expect(told).to_contain_text("Running the checks")
        told.scroll_into_view_if_needed()
        page.wait_for_timeout(600)
        shots.web(page, f"{_PAGE}-shown", clip=told, pad=4)
    world.stop(name)


async def test_the_person_is_asked_in_the_terminal(world: World) -> None:
    _own(world)
    world.epic("@local/approve", _TASK, until="asked")
    async with world.tui(size=(100, 40)) as (app, pilot):
        await shows(pilot, "Enter opens it")
        await pilot.pause(1.0)
        await pilot.pause()
        shots.tui(app, f"{_PAGE}-terminal")


def test_nobody_is_there_from_the_command_line(world: World) -> None:
    _own(world)
    _exec("approve", ("coder",), f"{_PAGE}-exec-away")


def test_an_agent_answers_for_the_person(world: World) -> None:
    _own(world)
    _exec("judged", ("coder", "judge"), f"{_PAGE}-exec-judged")

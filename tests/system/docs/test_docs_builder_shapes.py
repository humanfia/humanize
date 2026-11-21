"""The pictures of `docs/builder/shapes.md`: a typed answer from an agent, and from a person.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_builder_shapes.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.docs.conftest import AGENT
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

_TASK = "Add a coupon code to checkout"

#: The page's first flow, as the page prints it: a checker answers as a `Check`.
_CHECKED = '''
import pydantic

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    OutputSchemaError,
    flow,
)


class Check(pydantic.BaseModel):
    """What the checker found."""

    passed: bool = pydantic.Field(description="True only if nothing is left to fix.")
    notes: str = pydantic.Field(description="What to fix, said to the coder as it is.")


class Agents(AgentCollection):
    coder: Agent
    checker: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def checked(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> bool:
    """A coder works until a checker passes the change."""
    coder, checker = agents["coder"], agents["checker"]
    workspace = envs["workspace"]
    work = await coder.spawn()
    await coder.run(task, session=work, env=workspace)
    for _ in range(3):
        try:
            check = await checker.run(
                "Check the change in this repository.",
                session=await checker.spawn(),
                env=workspace,
                output_schema=Check,
            )
        except OutputSchemaError:
            continue  # not a Check: ask again
        if check.passed:
            return True
        await coder.run(check.notes, session=work, env=workspace)
    return False
'''

#: The page's second flow, whose model the page prints: a person answers as a `Release`.
_RELEASE = '''
from typing import Literal

import pydantic

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Outworlder,
    flow,
)


class Release(pydantic.BaseModel):
    """What the person decides."""

    action: Literal["ship", "hold", "revert"] = pydantic.Field(
        description="What to do with the change."
    )
    announce: bool = pydantic.Field(description="Post it to the changelog")
    risk: int = pydantic.Field(ge=1, le=5, description="1 is safe, 5 is risky.")
    notes: str = pydantic.Field("", description="Anything the team should know.")


class Agents(AgentCollection):
    coder: Agent
    human: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def release(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """A coder does the task, and a person decides what happens to it."""
    coder, human = agents["coder"], agents["human"]
    await coder.run(task, session=await coder.spawn(), env=envs["workspace"])
    decision = await human.run(
        "Release this change?", session=await human.spawn(), output_schema=Release
    )
    return decision.action
'''

#: What the coder does when told the task.
_WORK = {
    "text": "Checkout takes a coupon now: WELCOME10 is 10% off. The tests pass.",
    "tools": [
        {
            "name": "Edit",
            "input": {"file_path": "shop/checkout.py"},
            "result": "edited",
            "takes": 0.4,
        },
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": "5 passed in 0.18s",
            "takes": 0.6,
        },
    ],
}

#: What the checker answers, in the shape it is asked for.
_CHECK = {"json": {"passed": True, "notes": "WELCOME10 applies once. Tests pass."}}


def _own(world: World, name: str, source: str) -> None:
    """Puts a flow among the project's own, as `@local/<name>`."""
    flow = world.workspace / ".hmz" / "flows" / name
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(source)


def test_an_agent_answers_in_a_shape(world: World) -> None:
    _own(world, "checked", _CHECKED)
    world.says({"coupon": _WORK, "Check the change": _CHECK})
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "@local/checked",
            "-a",
            f"coder={AGENT}",
            "-a",
            f"checker={AGENT}",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        "builder-shapes-exec",
    )


def test_a_person_answers_the_same_shape_as_a_form(world: World) -> None:
    _own(world, "release", _RELEASE)
    world.says({"coupon": _WORK})
    name = world.epic("@local/release", _TASK, until="asked")
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_text("Release this change?").first).to_be_visible()
        expect(page.get_by_role("radio", name="ship")).to_be_visible()
        shots.web(page, "builder-shapes-form", window="desktop", most=shots.REEL)
    world.stop(name)


def test_an_answer_that_does_not_fit_is_refused_beside_its_field(world: World) -> None:
    _own(world, "release", _RELEASE)
    world.says({"coupon": _WORK})
    name = world.epic("@local/release", _TASK, until="asked")
    with world.page(desktop=True, height=1000) as page:
        go(page, f"/epics/{name}")
        card = page.locator('[data-hmz="question"]').first
        expect(card.get_by_role("radio", name="ship")).to_be_visible()
        risk = card.get_by_role("spinbutton")
        send = card.locator('[data-hmz="ask-send"]')
        reel = shots.Reel("builder-shapes-refused", clip=card, pad=30)
        ship = card.get_by_role("radio", name="ship")
        reel.web(page, hold=1.4, pointer=ship, click=True)
        ship.click()
        yes = card.get_by_role("radio", name="Yes, post it to the changelog")
        reel.web(page, hold=0.8, pointer=yes, click=True)
        yes.click()
        risk.click()
        risk.press_sequentially("9")
        reel.web(page, hold=0.9, pointer=send, click=True)
        send.click()
        expect(card.get_by_text("At most 5.")).to_be_visible()
        reel.web(page, hold=2.4, poster=True)
        risk.fill("2")
        expect(card.get_by_text("At most 5.")).to_be_hidden()
        reel.web(page, hold=2.2, pointer=send)
        reel.save()
        send.click()
        expect(card.locator('[data-hmz="ask-closed-said"]')).to_be_visible()

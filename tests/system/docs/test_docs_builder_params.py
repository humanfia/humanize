"""The pictures of `docs/builder/params.md`: one flow's params, on every interface.

The flow is the page's own, as the page prints it: `polish`, whose four params say how many
review rounds it takes, what each looks for and whether it commits. It is put among the
project's own flows, run and refused by `hmz exec`, filled in on the app's New epic page and
set up on the terminal's params sheet. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_builder_params.py`.
"""

from __future__ import annotations

import re
import shutil
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.integration.doubles_tui import on, onto, opens, screen, shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "builder-params"

_TASK = "Add a discount code to checkout"

#: The flow as the page prints it.
_POLISH = '''
from typing import Literal

from pydantic import Field, model_validator

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)

REVIEW = {"section": "Review"}
AFTER = {"section": "After"}


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


class Params(FlowParams):
    rounds: int = Field(
        2, ge=1, le=5, description="Review rounds after the work.",
        json_schema_extra=REVIEW,
    )
    focus: Literal["correctness", "style", "tests"] = Field(
        "correctness", description="What each round looks for.",
        json_schema_extra=REVIEW,
    )
    commit: bool = Field(
        False, description="Commit when done", json_schema_extra=AFTER
    )
    message: str = Field(
        "", title="Commit message", description="Empty for the agent's own.",
        json_schema_extra=AFTER,
    )

    @model_validator(mode="after")
    def _message_needs_commit(self) -> "Params":
        if self.message and not self.commit:
            raise ValueError("a message needs commit=true")
        return self


@flow(agents=Agents, envs=Envs, params=Params)
async def polish(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> None:
    """Do the task, then review it for one thing."""
    coder, workspace = agents["coder"], envs["workspace"]
    session = await coder.spawn()
    await coder.run(task, session=session, env=workspace)
    for _ in range(params.rounds):
        await coder.run(
            f"Review your change for {params.focus} only. Fix what you find.",
            session=session,
            env=workspace,
        )
    if params.commit:
        how = f"the message {params.message!r}" if params.message else "your own message"
        await coder.run(f"Commit your work with {how}.", session=session, env=workspace)
'''

#: What the agent says when told the task, to review it, and to commit it.
_SAYS = {
    "discount": {
        "text": (
            "Added a discount code to checkout: charge() takes a code, and WELCOME10"
            " takes 10% off."
        ),
        "tools": [
            {
                "name": "Edit",
                "input": {"file_path": "shop/checkout.py"},
                "result": "edited",
                "takes": 0.4,
            },
        ],
    },
    "Review your change for tests": {
        "text": "No test covered an unknown code. Added one: 3 tests pass.",
        "tools": [
            {
                "name": "Bash",
                "input": {"command": "pytest -q"},
                "result": "3 passed in 0.12s",
                "takes": 0.5,
            }
        ],
    },
    "Commit your work": {
        "text": "Committed checkout.py and its tests as 'Add discount codes'.",
        "tools": [
            {
                "name": "Bash",
                "input": {"command": "git commit -am 'Add discount codes'"},
                "result": "[main 4f1c2aa] Add discount codes",
                "takes": 0.3,
            }
        ],
    },
}


def _written(world: World) -> None:
    """Writes the flow where the page says to: `.hmz/flows/polish/`, the project's only."""
    flows = world.workspace / ".hmz" / "flows"
    shutil.rmtree(flows)
    (flows / "polish").mkdir(parents=True)
    (flows / "polish" / "__init__.py").write_text(_POLISH.lstrip())


def _exec(*params: str) -> list[str]:
    return [
        "hmz",
        "exec",
        "-f",
        "polish",
        "-a",
        f"coder={AGENT}",
        "-p",
        "budget.duration=10m",
        *(part for one in params for part in ("-p", one)),
        _TASK,
    ]


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


def test_the_params_steer_a_run_from_the_command_line(world: World) -> None:
    _written(world)
    world.says(_SAYS)
    shots.cli(_exec("rounds=1,focus=tests", "commit=true"), f"{_PAGE}-exec", columns=96)


def test_a_value_out_of_bounds_is_refused_before_anything_runs(world: World) -> None:
    _written(world)
    shots.cli(_exec("rounds=9"), f"{_PAGE}-refused", columns=96)


def test_a_combination_is_refused_in_the_validators_words(world: World) -> None:
    _written(world)
    shots.cli(_exec("message=Add discount codes"), f"{_PAGE}-validator", columns=96)


def test_the_app_asks_each_param_as_a_field_of_its_type(world: World) -> None:
    _written(world)
    with world.page(desktop=True, height=900) as page:
        go(page, "/new")
        view = page.locator("[data-hmz=new-epic]")
        picker = view.locator("[data-hmz=flow-picker]")
        expect(picker.locator("b")).not_to_have_text("…")
        expect(view.get_by_text("Asking…")).to_have_count(0)
        reel = shots.Reel(f"{_PAGE}-app", window="desktop")
        reel.web(page, hold=1.1, pointer=picker, click=True)
        picker.click()
        flow = page.get_by_text("@local/polish", exact=True)
        expect(flow).to_be_visible()
        reel.web(page, hold=1.2, pointer=flow, click=True)
        flow.click()
        expect(picker.locator("b")).to_have_text("@local/polish")
        rounds = view.get_by_role("spinbutton", name="rounds")
        expect(rounds).to_have_value("2")
        expect(view.get_by_text("Asking…")).to_have_count(0)
        form = view.locator("section.option-group").filter(
            has=page.get_by_role("spinbutton", name="rounds")
        )
        shots.web(page, f"{_PAGE}-form", clip=form, pad=24)
        reel.web(page, hold=3.0, pointer=rounds, click=True, poster=True)
        rounds.fill("9")
        tests = form.get_by_role("radio", name="tests")
        reel.web(page, hold=1.0, pointer=tests, click=True)
        tests.click()
        view.get_by_label("Longest it may take, in minutes").fill("10")
        box = view.get_by_placeholder(re.compile("What should"))
        box.fill(_TASK)
        reel.web(page, hold=1.2, pointer=box)
        box.press("Enter")
        expect(view.get_by_text("less than or equal to 5")).to_be_visible()
        reel.web(page, hold=3.4)
        reel.save()


async def test_the_terminal_asks_them_on_one_sheet(world: World) -> None:
    from hmz.tui.dropdown import Dropdown
    from hmz.tui.flows import Flows
    from hmz.tui.pick import Configures

    _written(world)
    async with world.tui(size=(100, 32)) as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*"/flow polish", "enter")
        await on(pilot, Flows)
        await shows(pilot, "coder")
        await onto(pilot, "\x1eparams")
        await pilot.press("enter")
        await on(pilot, Configures)
        await shows(pilot, "Set up polish")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-terminal")

        reel = shots.Reel(f"{_PAGE}-terminal-set")
        reel.tui(app, hold=1.8, caption="one row per param")
        await opens(pilot, "focus")
        await on(pilot, Dropdown)
        await _settled(pilot)
        reel.tui(app, hold=2.0, keys="enter", caption="a Literal drops its values")
        await pilot.press("down", "down", "enter")
        await on(pilot, Configures)
        await shows(pilot, "tests")
        await _settled(pilot)
        await onto(pilot, "message")
        await pilot.press("enter")
        await pilot.pause(0.3)
        await pilot.press(*"Add discount codes", "enter")
        await _settled(pilot)
        for _ in range(4):
            if "enter Set" in screen(app):
                break
            await pilot.press("tab")
            await _settled(pilot, 0.3)
        await pilot.press("enter")
        await shows(pilot, "a message needs commit=true")
        await _settled(pilot)
        reel.tui(
            app, hold=3.0, keys="enter", caption="the model refuses it", poster=True
        )
        reel.save()

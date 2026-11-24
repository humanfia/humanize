"""The pictures of `docs/user/epics.md`: an epic set up and started, on each interface.

One flow, set up three ways: on the app's New epic page, on its page of `/flow` in the
terminal interface, and on a line of `hmz exec`. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_epics.py`.

Two things are staged here, since the world comes with neither:

- a flow of the project's own, `review_loop`, with two agent roles, an environment role
  that is not the folder's own and a param, so that every row of the set-up is there;
- a backup target, `offsite`, written into settings and naming a made-up repository.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import tomlkit
from playwright.sync_api import expect

from hmz import config
from hmz.tui.flows import Flows
from hmz.tui.pick import Agent, Configures, Confirms
from tests.integration.doubles_tui import on, onto, screen, shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from hmz.tui import Humanize
    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-epics"

_TASK = "Add a discount code to checkout"

#: The project's own flow: an actor, a reviewer, the project, and how many rounds.
_FLOW = '''"""An actor works on the task until a reviewer approves it."""

import pydantic

from hmz.flows import (
    Agent,
    AgentCollection,
    CPUEnvMixin,
    Env,
    EnvCollection,
    FlowContext,
    FlowParams,
    Permission,
    ShellEnvMixin,
    flow,
)


class Verdict(pydantic.BaseModel):
    """What the reviewer decides."""

    approved: bool = pydantic.Field(description="True only if the task is done.")
    notes: str = pydantic.Field(description="What to fix, said to the actor.")


class Reviewer(Agent):
    """Reads the work and changes nothing."""

    _permission = Permission("read-only")


class Agents(AgentCollection):
    actor: Agent
    reviewer: Reviewer


class Repo(Env, ShellEnvMixin, CPUEnvMixin):
    """The repository both work in."""

    _cpu_count = 2


class Envs(EnvCollection):
    repo: Repo


class Params(FlowParams):
    rounds: int = pydantic.Field(3, ge=1, description="The most rounds of work and review.")


@flow(agents=Agents, envs=Envs, params=Params)
async def review_loop(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> bool:
    """An actor works on the task until a reviewer approves it."""
    actor, reviewer = agents["actor"], agents["reviewer"]
    workspace = envs["repo"]
    work = await actor.spawn()
    prompt = task
    for _ in range(params.rounds):
        await actor.run(prompt, session=work, env=workspace)
        verdict = await reviewer.run(
            f"Review the change in this repository. The task: {task}",
            session=await reviewer.spawn(),
            env=workspace,
            output_schema=Verdict,
        )
        if verdict.approved:
            return True
        prompt = verdict.notes
    return False
'''

#: What the agents say: the actor does the work, and the reviewer approves it.
_SAYS = {
    "Review the change": {
        "json": {"approved": True, "notes": "The code is taken off; tests pass."},
        "after": 0.6,
    },
    "discount": {
        "text": "Checkout takes a discount code now: WELCOME10 is 10% off. Tests pass.",
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
                "result": "2 passed in 0.12s",
                "takes": 0.6,
            },
        ],
        "after": 0.6,
    },
}


def _staged(world: World) -> None:
    """Writes the flow in the project, and a backup target into settings."""
    flows = world.workspace / ".hmz" / "flows"
    flows.mkdir(parents=True, exist_ok=True)
    (flows / "review_loop.py").write_text(_FLOW)
    settings = config() / "settings.toml"
    assert not settings.exists(), "the made-up home has settings of its own to keep"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        tomlkit.dumps(
            {
                "backup": {
                    "targets": [
                        {
                            "name": "offsite",
                            "url": "git@github.com:alex/epic-backups.git",
                            "policies": ["end"],
                        }
                    ]
                }
            }
        )
    )
    world.says(_SAYS)


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


async def _done(pilot: Pilot[None], says: str = "enter done") -> None:
    """Walks to the button under a form with tab, and presses it."""
    app = cast("Humanize", pilot.app)
    for _ in range(4):
        if says in screen(app):
            break
        await pilot.press("tab")
        await _settled(pilot, 0.3)
    assert says in screen(app), f"the form never offered {says!r}"
    await pilot.press("enter")
    await pilot.pause()


def _exec(*more: str) -> list[str]:
    """The page's line of `hmz exec`, with what one picture adds to it."""
    return [
        "hmz",
        "exec",
        "-f",
        "@local/review_loop",
        "-a",
        f"actor={AGENT}:high",
        "-a",
        "reviewer=claude/claude-opus-4-1",
        "-e",
        "repo=local/~/shop",
        *more,
        _TASK,
    ]


def test_an_epic_is_set_up_in_the_app(world: World) -> None:
    _staged(world)
    reel = shots.Reel(f"{_PAGE}-app", window="desktop")
    with world.page(desktop=True, height=940) as page:
        go(page, "/new")
        view = page.locator("[data-hmz=new-epic]")
        picker = view.locator("[data-hmz=flow-picker]")
        expect(picker.locator("b")).not_to_have_text("…")
        expect(view.get_by_text("Asking…")).to_have_count(0)
        picker.click()
        flow = page.get_by_text("@local/review_loop", exact=True)
        expect(flow).to_be_visible()
        reel.web(page, hold=1.4, pointer=flow, click=True)
        flow.click()
        expect(picker.locator("b")).to_have_text("@local/review_loop")
        chip = view.locator("[data-role=reviewer] [data-hmz=pick-model]")
        expect(chip).to_contain_text("Haiku 4.5")
        expect(view.get_by_text("Asking…")).to_have_count(0)
        # The role's directory as somebody writes it, not the made-up home's whole path.
        where = view.locator("[data-hmz=pick-dir]")
        where.fill("~/shop")
        page.keyboard.press("Escape")
        page.locator("body").click(position={"x": 5, "y": 5})
        reel.web(page, hold=1.4, pointer=chip, click=True)
        chip.click()
        menu = page.get_by_role("menu", name="Nous")
        model = menu.locator("[data-hmz=step-model]")
        expect(model).to_be_visible()
        reel.web(page, hold=1.4, pointer=model, click=True)
        model.click()
        opus = menu.locator("[data-value=claude-opus-4-1]")
        expect(opus).to_be_visible()
        reel.web(page, hold=1.3, pointer=opus, click=True)
        opus.click()
        expect(chip).to_contain_text("Opus 4.1")
        # Picking a model shuts the menu: the chip is opened again for the effort.
        expect(menu).to_have_count(0)
        reel.web(page, hold=1.3, pointer=chip, click=True)
        chip.click()
        effort = menu.locator("[data-hmz=step-effort]")
        expect(effort).to_be_visible()
        reel.web(page, hold=1.3, pointer=effort, click=True)
        effort.click()
        high = menu.get_by_role("menuitem", name="High", exact=True)
        expect(high).to_be_visible()
        reel.web(page, hold=1.3, pointer=high, click=True)
        high.click()
        expect(chip).to_have_text("Claude Code Opus 4.1 High")
        if menu.count():
            page.keyboard.press("Escape")
        expect(menu).to_have_count(0)
        reel.web(page, hold=3.5, poster=True)
        reel.save()

        # The rest of the form, filled as the page says, and the task typed.
        view.get_by_role("spinbutton", name="rounds").fill("2")
        view.get_by_label("Most it may cost, in dollars").fill("5")
        view.get_by_label("Longest it may take, in minutes").fill("30")
        view.get_by_role("checkbox", name="offsite").check()
        view.get_by_role("textbox", name="Task").fill(_TASK)
        shots.web(page, f"{_PAGE}-new", window="desktop", most=shots.REEL)


async def test_an_epic_is_set_up_in_the_terminal(world: World) -> None:
    _staged(world)
    async with world.tui((100, 36)) as (app, pilot):
        await shows(pilot, MODEL)
        reel = shots.Reel(f"{_PAGE}-terminal")
        await pilot.press(*"/flow review_loop", "enter")
        await on(pilot, Flows)
        await shows(pilot, "an epic needs one")
        reel.tui(app, hold=2.0, keys="/flow review_loop")

        # -- an agent role: its sheet -----------------------------------------------
        await pilot.press("enter")
        await on(pilot, Agent)
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-agent-sheet")
        reel.tui(app, hold=1.8, keys="enter", caption="an agent role")
        await pilot.press("escape")
        await on(pilot, Flows)

        # -- the environment role: where it works -----------------------------------
        await onto(pilot, "@repo")
        await pilot.press("enter")
        await shows(pilot, "Environment for repo")
        await onto(pilot, "workdir")
        await pilot.press(*"~/shop")
        await _settled(pilot)
        reel.tui(app, hold=1.8, caption="where repo works")
        await pilot.press("enter")
        await _settled(pilot, 0.3)
        await _done(pilot)
        await on(pilot, Flows)
        await shows(pilot, "local/~/shop")

        # -- what the flow takes: its params ----------------------------------------
        await onto(pilot, "\x1eparams")
        await pilot.press("enter")
        await on(pilot, Configures)
        await shows(pilot, "Set up review_loop")
        await pilot.press("enter")
        await pilot.pause(0.3)
        await pilot.press("2", "enter")
        await _settled(pilot)
        await _done(pilot, "enter set")
        await on(pilot, Flows)
        await shows(pilot, "rounds 2")

        # -- what an epic may spend: its budget -------------------------------------
        await onto(pilot, "\x1ebudget")
        await pilot.press("enter")
        await on(pilot, Configures)
        await shows(pilot, "Set budget for review_loop")
        await pilot.press("enter")
        await pilot.pause(0.3)
        await pilot.press(*"30m", "enter")
        await onto(pilot, "cost")
        await pilot.press("enter")
        await pilot.pause(0.3)
        await pilot.press("5", "enter")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-budget-sheet")
        reel.tui(app, hold=2.0, caption="the budget")
        await _done(pilot, "enter set")
        await on(pilot, Flows)
        await shows(pilot, "stops at")
        await onto(pilot, "0")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-roles")
        reel.tui(app, hold=2.2, caption="every row set")

        # -- saved, and started on a task -------------------------------------------
        await pilot.press("escape")
        await on(pilot, Confirms)
        reel.tui(app, hold=1.6, keys="esc", caption="it asks before leaving")
        await pilot.press("enter")
        await shows(pilot, "set up: /flow review_loop <task> starts it")
        await _settled(pilot)
        reel.tui(app, hold=1.8, keys="enter", caption="saved")
        await pilot.press(*f"/flow review_loop {_TASK}")
        await pilot.pause()
        reel.tui(app, hold=1.2, caption="the task", cut=True)
        await pilot.press("enter")
        await shows(pilot, "WELCOME10")
        await _settled(pilot)
        reel.tui(app, hold=4, keys="enter", poster=True)
        reel.save()


def test_an_epic_is_started_from_the_command_line(world: World) -> None:
    _staged(world)
    shots.cli(_exec(), f"{_PAGE}-refused", columns=100)
    shots.cli(
        _exec("-p", "rounds=2", "-p", "budget.output_tokens=20000"),
        f"{_PAGE}-exec",
        columns=100,
    )

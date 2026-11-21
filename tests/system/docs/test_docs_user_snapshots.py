"""The pictures of `docs/user/snapshots.md`: an environment put back as a snapshot had it.

A flow of the project's own snapshots its workspace before its agent works and after each of
two rounds, then asks its person whether to keep the change. While it waits, the person opens
the workspace's Changes in the app and rewinds it to the first round; the same list is the
Snapshots page of `/env` in the terminal interface; and the snapshots are refs of the
repository, as git lists them. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_snapshots.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from hmz.tui.envs import Envs, Snapshots, Sure
from tests.integration.doubles_tui import on, shows
from tests.system.docs import shots
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-snapshots"

_TASK = "Add a discount code to checkout"

#: A flow of the project's own that snapshots its workspace as it goes.
_FLOW = '''
"""Checkpointed -- an agent works in two rounds, and the workspace is snapshotted at each.

    hmz exec -f @local/checkpointed -a coder=claude/claude-opus-4-1 -p budget.cost=5 "the task"
"""

from hmz.flows import (
    Agent, AgentCollection, EnvCollection, FlowContext, FlowParams, GitEnvMixin, LocalEnv,
    Outworlder, ShellEnvMixin, flow,
)


class Agents(AgentCollection):
    """The agent that does the work, and the person who keeps it or not."""

    coder: Agent
    reviewer: Outworlder


class Workspace(LocalEnv, GitEnvMixin, ShellEnvMixin):
    """The project: a shell in it, and snapshots of it."""


class Envs(EnvCollection):
    """Where it works."""

    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def checkpointed(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """An agent works in two rounds, each snapshotted, and a person keeps it or not."""
    coder, reviewer, repo = agents["coder"], agents["reviewer"], envs["workspace"]
    session, person = await coder.spawn(), await reviewer.spawn()
    await repo.snapshot("before")
    await coder.run(task, session=session, env=repo)
    await repo.snapshot("round-1")
    await coder.run("Now cover it with tests.", session=session, env=repo)
    await repo.snapshot("round-2")
    await reviewer.run("Keep this change?", session=person)
'''

_CHECKOUT = '''"""Paying for a cart."""

from shop.cart import total

CODES = {"WELCOME10": 10}


def charge(items: dict[str, int], code: str = "") -> int:
    """What is charged for a cart, in cents, less what a code takes off."""
    owed = total(items)
    return owed - owed * CODES.get(code, 0) // 100
'''

_TESTS = """from shop.checkout import charge


def test_a_code_takes_ten_percent_off() -> None:
    assert charge({"mug": 2}, "WELCOME10") == 2160
"""

#: What the agent does in each round: it edits checkout, then writes tests for it.
_ROUNDS = {
    "discount": {
        "text": "Checkout takes a discount code now: WELCOME10 is 10% off.",
        "tools": [
            {
                "name": "Edit",
                "input": {"file_path": "shop/checkout.py"},
                "result": "edited",
                "takes": 0.2,
            }
        ],
        "writes": {"shop/checkout.py": _CHECKOUT},
        "after": 1.2,
    },
    "cover it": {
        "text": "I added a test for the code in tests/test_checkout.py.",
        "tools": [
            {
                "name": "Write",
                "input": {"file_path": "tests/test_checkout.py"},
                "result": "written",
                "takes": 0.2,
            }
        ],
        "writes": {"tests/test_checkout.py": _TESTS},
        "after": 1.2,
    },
}


def _waiting(world: World) -> str:
    """An epic of the flow, both rounds done and snapshotted, waiting on its person."""
    world.committed(
        "Add the checkpointed flow", {".hmz/flows/checkpointed/__init__.py": _FLOW}
    )
    world.says(_ROUNDS)
    return world.epic("@local/checkpointed", _TASK, until="asked")


async def _settled(pilot: Pilot[None], seconds: float = 0.5) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


def _dragged(page: Page, handle: str, by: int) -> None:
    """Drags one of the page's dividers sideways, as a person does to read a long name."""
    box = page.locator(handle).first.bounding_box()
    assert box is not None
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + by, y, steps=8)
    page.mouse.up()


def test_an_environment_is_rewound_in_the_app(world: World) -> None:
    name = _waiting(world)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        page.locator("[data-hmz=envs-open]").first.click()
        page.locator("[data-tab=changes]").first.click()
        expect(page.locator("[data-hmz=change]")).to_have_count(2)
        # The list is dragged wider, so that a snapshot's whole name is read.
        _dragged(page, "[data-hmz=envs-resizer]", -200)
        _dragged(page, "[data-hmz=changes-split]", 300)
        section = page.locator("[data-hmz=snapshots]")
        section.locator("summary").click()
        rows = section.locator("[data-hmz=snapshot]")
        expect(rows).to_have_count(3)
        page.wait_for_timeout(800)
        shots.web(page, f"{_PAGE}-app", window="desktop")

        reel = shots.Reel(f"{_PAGE}-app-rewind", window="desktop")
        button = rows.nth(1).get_by_role("button", name="Rewind")
        reel.web(page, hold=1.8, pointer=button, click=True)
        button.click()
        sure = page.locator("[data-hmz=envs-confirm]")
        expect(sure).to_be_visible()
        page.wait_for_timeout(500)
        yes = sure.get_by_role("button", name="OK")
        reel.web(page, hold=2.6, pointer=yes, click=True, caption="it asks first")
        yes.click()
        expect(page.locator("[data-hmz=change]")).to_have_count(1)
        page.wait_for_timeout(800)
        reel.web(page, hold=3.5, poster=True, caption="the second round's file is gone")
        reel.save()


# -- in the terminal ------------------------------------------------------------------


async def test_an_environment_is_rewound_in_the_terminal(world: World) -> None:
    _waiting(world)
    async with world.tui(size=(100, 26)) as (app, pilot):
        await shows(pilot, "Keep this change?")
        await _settled(pilot, 1.0)
        await pilot.press(*"/env workspace", "enter")
        await _settled(pilot, 1.0)
        for _ in range(4):
            if isinstance(app.screen, Snapshots):
                break
            # Backwards: forwards is the Shell page, which takes the terminal over.
            await pilot.press("shift+tab")
            await _settled(pilot)
        await on(pilot, Snapshots)
        await shows(pilot, "round-2")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-terminal")

        reel = shots.Reel(f"{_PAGE}-terminal-rewind")
        reel.tui(app, hold=1.8)
        await pilot.press("down")
        await _settled(pilot)
        reel.tui(app, hold=1.2, keys="down", caption="to the snapshot")
        await pilot.press("enter")
        await on(pilot, Sure)
        await _settled(pilot)
        reel.tui(app, hold=2.6, keys="enter", caption="it asks first")
        await pilot.press("enter")
        await on(pilot, Envs)
        await pilot.press("escape")
        await shows(pilot, "rewound workspace")
        await _settled(pilot, 1.0)
        reel.tui(
            app,
            hold=3.5,
            keys="enter esc",
            caption="the transcript says so",
            poster=True,
        )
        reel.save()


# -- from the command line ------------------------------------------------------------


def test_snapshots_are_refs_of_the_repository(world: World) -> None:
    name = _waiting(world)
    shots.cli(
        ["git", "for-each-ref", "refs/hmz/snapshots"],
        f"{_PAGE}-cli",
        columns=80,
    )
    world.stop(name)

"""The pictures of `docs/builder/environments.md`: a flow's environment roles, filled.

The page's own flow, `tested`, declares two environment roles: the workspace, which Humanize
fills, and `reports`, which whoever runs it fills. It has its agent work in a directory under
the workspace, runs the project's tests itself and writes what they printed into `reports`.
It is shown refused for want of `reports` and run with it from the command line, set up on
the app's New epic page and in the terminal's flow sheet, and as its epic's environments
while it runs. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_builder_environments.py`.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from playwright.sync_api import expect

from hmz.tui.flows import Flows
from tests.integration.doubles_tui import on, onto, shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    import pytest
    from playwright.sync_api import Locator

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "builder-environments"

_TASK = "Add a discount code to checkout"

#: Where the person keeps the reports, as `-e` names it: a directory of their home.
_REPORTS = "local/~/reports"

#: The flow as the page prints it.
_TESTED = '''
from hmz.flows import (
    Agent,
    AgentCollection,
    BashEnvMixin,
    Env,
    EnvCollection,
    FilesEnvMixin,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)


class Workspace(LocalEnv, BashEnvMixin):
    """The folder the run started in. The flow runs commands in it."""


class Reports(Env, FilesEnvMixin):
    """Where the test report is kept. The flow writes files in it."""


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    workspace: Workspace  # filled by Humanize
    reports: Reports  # filled by whoever runs the flow


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def tested(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """A coder does the task in the package; the flow runs the tests and files the report."""
    coder, workspace, reports = agents["coder"], envs["workspace"], envs["reports"]
    package = await workspace.derive_subdir(subdir="shop")
    session = await coder.spawn()
    await coder.run(task, session=session, env=package)
    code, out, err = await workspace.exec(["python3", "-m", "pytest", "-q"], timeout=600)
    await reports.write("tests/latest.txt", (out + err).encode())
    return "tests pass" if code == 0 else "tests fail"
'''

#: What the agent does when told the task.
_WORK: dict[str, Any] = {
    "text": (
        "Added a discount code to checkout: charge() takes a code, and WELCOME10"
        " takes 10% off."
    ),
    "tools": [
        {
            "name": "Edit",
            "input": {"file_path": "checkout.py"},
            "result": "edited",
            "takes": 0.4,
        },
    ],
}


def _own(world: World) -> None:
    """Puts the page's flow among the project's own, and makes the reports' directory."""
    flow = world.workspace / ".hmz" / "flows" / "tested"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(_TESTED.lstrip())
    (world.home / "reports").mkdir()


def _exec(*envs: str) -> list[str]:
    return [
        "hmz",
        "exec",
        "-f",
        "tested",
        "-a",
        f"coder={AGENT}",
        *(part for one in envs for part in ("-e", one)),
        "-p",
        "budget.output_tokens=20000",
        _TASK,
    ]


class _Part:
    """A part of the page that no one element is: a box of it, found as a locator's is."""

    def __init__(self, left: float, top: float, right: float, bottom: float) -> None:
        self._box = {"x": left, "y": top, "width": right - left, "height": bottom - top}

    def bounding_box(self) -> dict[str, float]:
        return self._box


def _around(*parts: Locator, pad: float = 14) -> Any:
    """The box that holds every one of these parts of the page, with room around it."""
    boxes = [one.bounding_box() for one in parts]
    assert all(boxes), "a part of the page to crop to is not drawn"
    held = [one for one in boxes if one]
    return _Part(
        min(one["x"] for one in held) - pad,
        min(one["y"] for one in held) - pad,
        max(one["x"] + one["width"] for one in held) + pad,
        max(one["y"] + one["height"] for one in held) + pad,
    )


def _running(world: World) -> str:
    """Starts the flow on the task with its `reports` given, and answers its epic's name."""
    here = str(world.workspace)
    with world.session() as session:
        sub = session.call("epic.attach", workspace=here)["sub"]
        session.call(
            "epic.start",
            sub=sub,
            flow="@local/tested",
            task=_TASK,
            budget={"output_tokens": 20000},
            agents={"coder": AGENT},
            envs={"reports": _REPORTS},
            idem=uuid.uuid4().hex,
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            for one in session.call("runs.list", workspace=here)["runs"]:
                if one["task"] == _TASK:
                    session.call("epic.detach", sub=sub)
                    return str(one["name"])
            time.sleep(0.2)
    raise AssertionError("the epic was never listed")


def test_a_role_nobody_filled_is_refused_before_anything_runs(world: World) -> None:
    _own(world)
    shots.cli(_exec(), f"{_PAGE}-refused", columns=104)


def test_the_flow_runs_with_its_role_filled_on_the_command_line(world: World) -> None:
    _own(world)
    world.says({"discount": _WORK})
    shots.cli(_exec(f"reports={_REPORTS}"), f"{_PAGE}-exec", columns=96)
    shots.cli(["cat", "../reports/tests/latest.txt"], f"{_PAGE}-report", columns=96)


def test_a_machine_without_bash_is_refused_for_the_mixin(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _own(world)
    # A machine with no bash: every program of the system's but that one, behind links.
    tools = world.home.parent / "tools"
    tools.mkdir()
    for system in ("/bin", "/usr/bin"):
        for one in Path(system).iterdir():
            if one.name != "bash" and not (tools / one.name).exists():
                (tools / one.name).symlink_to(one)
    kept = [
        one
        for one in os.environ["PATH"].split(os.pathsep)
        if one not in ("/bin", "/usr/bin")
    ]
    monkeypatch.setenv("PATH", os.pathsep.join([*kept, str(tools)]))
    shots.cli(_exec(f"reports={_REPORTS}"), f"{_PAGE}-missing", columns=104)


def test_the_app_asks_where_each_role_works(world: World) -> None:
    _own(world)
    with world.page(desktop=True) as page:
        go(page, "/new?flow=%40local%2Ftested")
        row = page.locator("[data-hmz=env][data-role=reports]")
        expect(row).to_be_visible()
        expect(page.get_by_text("Asking…")).to_have_count(0)
        where = row.locator("[data-hmz=pick-dir]")
        where.fill("~/reports")
        where.blur()
        expect(page.get_by_text("Asking…")).to_have_count(0)
        heading = page.get_by_text("Environment", exact=True).first
        shots.web(page, f"{_PAGE}-form", clip=_around(heading, row, pad=18), pad=0)


def test_the_environments_of_the_epic_while_it_runs(world: World) -> None:
    _own(world)
    world.says({"discount": {**_WORK, "after": 60}})
    name = _running(world)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        opens = page.locator("[data-hmz=envs-open]")
        expect(opens).to_be_visible()
        opens.click()
        expect(page.locator("[data-hmz=envs-view]")).to_be_visible()
        expect(page.locator("[data-hmz=envs-item]")).to_have_count(3)
        # Room for the names: the list of environments drawn wider.
        page.get_by_role("separator", name="Resize the list of environments").focus()
        for _ in range(8):
            page.keyboard.press("ArrowRight")
        # The directory the flow derived, under the workspace it was derived from.
        page.locator("[data-hmz=envs-item]", has_text="subdir").click()
        page.locator("[data-hmz=envs-tab-files]").click()
        expect(
            page.locator("[data-hmz=files-row]:visible", has_text="checkout.py")
        ).to_be_visible()
        page.wait_for_timeout(1500)
        shots.web(page, f"{_PAGE}-view", window="desktop")
    world.stop(name)


async def test_the_terminal_asks_where_each_role_works(world: World) -> None:
    _own(world)
    async with world.tui((100, 30)) as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*"/flow tested", "enter")
        await on(pilot, Flows)
        await onto(pilot, "@reports")
        await pilot.pause(0.6)
        shots.tui(app, f"{_PAGE}-terminal")

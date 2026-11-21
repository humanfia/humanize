"""The pictures of `docs/tutorials/review-loop.md`: an actor and a reviewer, built under test.

The page's own flow and its own test are staged in the project as the page prints them: the
test is run red against the flow's first body and green against its loop, then the flow is
run from the command line and looked at in the app. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_tutorials_review_loop.py`.

Two things are stood in for here, and only here:

- `uvx`, which would fetch `hmz` and pytest: a script of that name runs this checkout's
  pytest on the arguments after `pytest`, so the picture is of the page's own line and of
  what pytest really printed for the page's own test;
- the reviewer's second verdict: the stand-in agent answers a schema the same way each time
  it is asked, so the scene changes what it is scripted to answer once the actor's second
  turn has written its file.
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.docs.conftest import AGENT
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from collections.abc import Generator

    import pytest

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "tutorials-review-loop"

_TASK = "Add a coupon code to checkout"

#: The flow as the page first writes it: its roles and its verdict, and one turn.
_HEAD = '''# .hmz/flows/review_loop/__init__.py
import pydantic

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    GoalCommandAgentMixin,
    LocalEnv,
    Permission,
    flow,
)


class Verdict(pydantic.BaseModel):
    """What the reviewer decides."""

    approved: bool = pydantic.Field(description="True only if the goal is met.")
    notes: str = pydantic.Field(description="What to fix, said to the actor as it is.")


class Actor(Agent, GoalCommandAgentMixin):
    """Does the work."""


class Reviewer(Agent):
    """Reads the work and changes nothing."""

    _permission = Permission("read-only")


class Agents(AgentCollection):
    actor: Actor
    reviewer: Reviewer


class Envs(EnvCollection):
    workspace: LocalEnv


class Params(FlowParams):
    rounds: int = 3


@flow(agents=Agents, envs=Envs, params=Params)
async def review_loop(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> bool:
    """An actor works on a goal until a reviewer approves it."""
'''

_FIRST = """    actor = agents["actor"]
    await actor.run(f"/goal {task}", session=await actor.spawn(), env=envs["workspace"])
    return False
"""

#: And the body the page replaces that turn with: the loop.
_LOOP = """    actor, reviewer = agents["actor"], agents["reviewer"]
    workspace = envs["workspace"]
    work = await actor.spawn()
    prompt = f"/goal {task}"
    for _ in range(params.rounds):
        await actor.run(prompt, session=work, env=workspace)
        verdict = await reviewer.run(
            f"Review the change in this repository. The goal: {task}",
            session=await reviewer.spawn(),
            env=workspace,
            output_schema=Verdict,
        )
        if verdict.approved:
            return True
        prompt = verdict.notes
    return False
"""

#: The page's test of it.
_TEST = """# .hmz/tests/test_review_loop.py
from hmz.sdk import fakes


async def test_notes_go_back_until_approved() -> None:
    actor = fakes.FakeAgentDriver()
    reviewer = fakes.FakeAgentDriver(
        reply=[
            {"approved": False, "notes": "cover the empty cart"},
            {"approved": True, "notes": ""},
        ]
    )

    approved = await fakes.run_fake(
        "review_loop", "add a coupon", agents={"actor": actor, "reviewer": reviewer}
    )

    assert approved is True
    assert actor.prompts == ["/goal add a coupon", "cover the empty cart"]
    assert len(reviewer.sessions) == 2


async def test_it_gives_up_after_its_rounds() -> None:
    reviewer = fakes.FakeAgentDriver(reply={"approved": False, "notes": "not yet"})

    approved = await fakes.run_fake(
        "review_loop",
        "add a coupon",
        agents={"reviewer": reviewer},
        params={"rounds": 2},
    )

    assert approved is False
    assert len(reviewer.prompts) == 2
"""

#: The line the page runs its tests with.
_PYTEST = [
    "uvx",
    "--with",
    "hmz",
    "--with",
    "pytest-asyncio",
    "pytest",
    "-q",
    "-o",
    "asyncio_mode=auto",
    ".hmz/tests",
]

_CHECKOUT = '''"""Paying for a cart."""

from shop.cart import total

COUPONS = {"WELCOME10": 10}


def charge(items: dict[str, int], coupon: str = "") -> int:
    """What is charged for a cart, in cents, less what a coupon takes off."""
    owed = total(items)
    return owed - owed * COUPONS.get(coupon, 0) // 100
'''

_COVERED = """from shop.checkout import charge


def test_an_empty_cart_with_a_coupon_is_charged_nothing() -> None:
    assert charge({}, "WELCOME10") == 0
"""

#: The file the actor's second turn writes: what tells the scene the first review is over.
_MARK = "tests/test_checkout.py"

#: What the actor does when set the goal.
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
            "result": "1 passed in 0.12s",
            "takes": 0.6,
        },
    ],
    "writes": {"shop/checkout.py": _CHECKOUT},
}

#: What the reviewer's notes are, and what the actor does when handed them.
_NOTES = "No test covers an empty cart with a coupon. Add one."
_FIX = {
    "text": "Added a test for an empty cart with a coupon: it is charged nothing.",
    "tools": [
        {
            "name": "Write",
            "input": {"file_path": _MARK},
            "result": "written",
            "takes": 0.6,
        },
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": "2 passed in 0.14s",
            "takes": 0.8,
        },
    ],
    "writes": {_MARK: _COVERED},
}

_NO = {"json": {"approved": False, "notes": _NOTES}}
_YES = {"json": {"approved": True, "notes": "The empty cart is covered. Tests pass."}}

#: The page's line that runs the flow for real.
_EXEC = [
    "hmz",
    "exec",
    "-f",
    "@local/review_loop",
    "-a",
    f"actor={AGENT}",
    "-a",
    f"reviewer={AGENT}",
    "-p",
    "budget.output_tokens=20000",
    _TASK,
]


def _flow(world: World, body: str) -> None:
    """Writes the page's flow in the project, with one body or the other."""
    flow = world.workspace / ".hmz" / "flows" / "review_loop"
    flow.mkdir(parents=True, exist_ok=True)
    (flow / "__init__.py").write_text(_HEAD + body)


def _uvx(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """Puts a `uvx` on the path that runs this checkout's pytest, fetching nothing."""
    tools = world.home.parent / "tools"
    tools.mkdir()
    uvx = tools / "uvx"
    uvx.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "argv = sys.argv[1:]\n"
        "argv = argv[argv.index('pytest') + 1:]\n"
        "os.environ['PYTHONDONTWRITEBYTECODE'] = '1'\n"
        "os.execv(sys.executable, [sys.executable, '-m', 'pytest', '-p',"
        " 'no:cacheprovider', *argv])\n"
    )
    uvx.chmod(0o755)
    monkeypatch.setenv("PATH", os.pathsep.join((str(tools), os.environ["PATH"])))


@contextlib.contextmanager
def _reviewed_twice(world: World) -> Generator[None]:
    """Scripts a run of two rounds: the reviewer refuses the work once, then approves it."""
    world.says({"Review the change": _NO, "empty cart": _FIX, "coupon": _WORK})
    mark = world.workspace / _MARK
    over = threading.Event()

    def turn() -> None:
        while not over.wait(0.05):
            if mark.exists():
                # Said whole again, in order: the first line found in a prompt answers it.
                world.says(
                    {"Review the change": _YES, "empty cart": _FIX, "coupon": _WORK}
                )
                return

    watching = threading.Thread(target=turn, daemon=True)
    watching.start()
    try:
        yield
    finally:
        over.set()
        watching.join()


def test_the_test_fails_then_passes(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _uvx(world, monkeypatch)
    tests = world.workspace / ".hmz" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_review_loop.py").write_text(_TEST)
    _flow(world, _FIRST)
    shots.cli(_PYTEST, f"{_PAGE}-red")
    reel = shots.Reel(f"{_PAGE}-test")
    reel.cli(_PYTEST, rows=20, hold=2.6, frames=2)
    _flow(world, _LOOP)
    reel.cli(_PYTEST, rows=20, hold=3.4, frames=2)
    reel.save()


def test_the_flow_is_run_from_the_command_line(world: World) -> None:
    _flow(world, _LOOP)
    with _reviewed_twice(world):
        shots.cli(_EXEC, f"{_PAGE}-exec")


def test_the_epic_is_read_in_the_app(world: World) -> None:
    _flow(world, _LOOP)
    with _reviewed_twice(world):
        name = world.epic("@local/review_loop", _TASK, budget={"output_tokens": 20000})
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_role("heading", name="Handovers")).to_be_visible()
        # The graph alone, as large as the window lets it be: the panel beside it shut.
        page.get_by_role("button", name="Close panel").click()
        page.get_by_role("button", name="Recenter").click()
        for _ in range(2):
            page.get_by_role("button", name="Zoom in").click()
        page.mouse.move(640, 700)
        page.wait_for_timeout(600)
        expect(page.get_by_text("Reading handovers")).to_have_count(0)
        shots.web(page, f"{_PAGE}-epic", window="desktop", most=shots.REEL)
        go(page, f"/epics/{name}/exomyth")
        page.wait_for_function("() => window.__exomyth && window.__exomyth.model()")
        shots.web(page, f"{_PAGE}-trace", window="desktop", most=shots.REEL)

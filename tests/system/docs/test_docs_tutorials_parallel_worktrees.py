"""The pictures of `docs/tutorials/parallel-worktrees.md`: three attempts, a worktree each.

The page builds one flow, `best_of`, among the project's own: it checks out a git worktree
per attempt, has one agent take a turn in each at once, runs the project's check in every
worktree, puts the smallest change that passed into the project, and removes the worktrees.
Here it is tested on fakes, run from the command line, and watched while its three sessions
work. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_tutorials_parallel_worktrees.py`.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from hmz.runtime.kept import Runs
from tests.integration.doubles_tui import shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "tutorials-parallel-worktrees"

_TASK = "Add a discount code to checkout"

#: The page's flow, as the page prints it.
_FLOW = '''
import asyncio
import shlex
from datetime import timedelta
from typing import NamedTuple

from hmz.flows import (
    Agent,
    AgentCollection,
    Budget,
    BudgetExceeded,
    EnvCollection,
    FlowContext,
    FlowParams,
    GitWorktreeEnvMixin,
    LocalEnv,
    ShellEnvMixin,
    flow,
)


class Agents(AgentCollection):
    coder: Agent


class Workspace(LocalEnv, ShellEnvMixin, GitWorktreeEnvMixin):
    """The project. The flow may run programs in it and add worktrees of it."""


class Envs(EnvCollection):
    workspace: Workspace


class Params(FlowParams):
    count: int = 3
    minutes: float = 10
    check: str = "python3 -m pytest -q"


class Attempt(NamedTuple):
    number: int
    tree: Workspace
    passed: bool
    lines: int


@flow(agents=Agents, envs=Envs, params=Params)
async def best_of(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> int | None:
    """Several attempts at one task, each in its own worktree. The best is kept."""
    coder, workspace = agents["coder"], envs["workspace"]
    trees: list[Workspace] = []

    async def attempt(number: int) -> Attempt | None:
        tree = await workspace.derive_worktree()
        trees.append(tree)
        try:
            await coder.run(
                f"{task}\\n\\nYou are attempt {number} of {params.count}.",
                session=await coder.spawn(),
                env=tree,
                budget=Budget(
                    duration=timedelta(minutes=params.minutes), graceful=False
                ),
            )
        except BudgetExceeded as error:
            if not error.own:
                raise  # the run's own budget is spent
            print(f"attempt {number}: out of time")
            return None
        await tree.exec(["git", "add", "-A"])
        status, _, _ = await tree.exec(shlex.split(params.check))
        _, stat, _ = await tree.exec(["git", "diff", "--cached", "--numstat"])
        lines = sum(
            int(n) for row in stat.splitlines() for n in row.split()[:2] if n.isdigit()
        )
        verdict = "passed" if status == 0 else "failed"
        print(f"attempt {number}: check {verdict}, {lines} lines changed")
        return Attempt(number, tree, status == 0, lines)

    try:
        done = await asyncio.gather(*(attempt(n) for n in range(1, params.count + 1)))
        passed = [one for one in done if one and one.passed]
        if not passed:
            print("no attempt passed the check: nothing kept")
            return None
        best = min(passed, key=lambda one: one.lines)
        _, kept, _ = await best.tree.exec(["git", "write-tree"])
        await workspace.exec(
            ["git", "restore", f"--source={kept.strip()}", "--worktree", "--", "."]
        )
        print(f"kept attempt {best.number}")
        return best.number
    finally:
        for tree in trees:
            await workspace.exec(
                ["git", "worktree", "remove", "--force", str(tree.workdir)]
            )
'''

#: The page's test of it, as the page prints it.
_TEST = """
import asyncio

from hmz.sdk import fakes

CHANGED = {"1": 40, "2": 9, "3": 12}  # lines each attempt changes
FAILS = "2"  # the attempt whose check fails


def test_the_smallest_passing_attempt_is_kept() -> None:
    attempts: dict[str, str] = {}  # worktree -> attempt number

    async def reply(prompt: str, *, session: fakes.FakeSession, **_: object) -> str:
        number = prompt.split("attempt ")[1][0]
        attempts[str(session.placement.workdir)] = number
        await asyncio.sleep(0.01)  # long enough for the turns to overlap
        return "done"

    def run(command: tuple[str, ...], env: fakes.FakeEnvDriver) -> tuple[int, str, str]:
        number = attempts.get(str(env.workdir), "")
        if command == ("python3", "-m", "pytest", "-q"):
            return int(number == FAILS), "", ""
        if command == ("git", "diff", "--cached", "--numstat"):
            return 0, f"{CHANGED[number]}\\t0\\tshop/checkout.py\\n", ""
        return 0, "", ""

    project = fakes.FakeEnvDriver({"shop/checkout.py": b""}, run=run)
    coder = fakes.FakeAgentDriver(reply=reply)

    kept = asyncio.run(
        fakes.run_fake(
            "best_of", "add a discount code", agents={"coder": coder}, local=project
        )
    )

    assert kept == 3  # attempt 2 is smaller, but its check failed
    assert coder.peak == 3  # three turns at once
    removed = sum(one[:3] == ("git", "worktree", "remove") for one in project.commands)
    assert removed == 3  # every worktree is gone
"""

#: Attempt 1: a module of its own for the codes, and a test. It passes, at some length.
_ONE = {
    "shop/discounts.py": (
        '"""Discount codes, and what each takes off."""\n\n'
        "from dataclasses import dataclass\n\n\n"
        "@dataclass(frozen=True)\n"
        "class Discount:\n"
        '    """A code and the share of the total it takes off, in percent."""\n\n'
        "    code: str\n"
        "    percent: int\n\n"
        "    def off(self, owed: int) -> int:\n"
        "        return owed * self.percent // 100\n\n\n"
        'DISCOUNTS = {"WELCOME10": Discount("WELCOME10", 10)}\n\n\n'
        "def find(code: str) -> Discount | None:\n"
        '    """The discount a code names, if it names one."""\n'
        "    return DISCOUNTS.get(code.strip().upper())\n"
    ),
    "shop/checkout.py": (
        '"""Paying for a cart."""\n\n'
        "from shop.cart import total\n"
        "from shop.discounts import find\n\n\n"
        'def charge(items: dict[str, int], code: str = "") -> int:\n'
        '    """What is charged for a cart, in cents, after a discount code."""\n'
        "    owed = total(items)\n"
        "    discount = find(code)\n"
        "    if discount is None:\n"
        "        return owed\n"
        "    return owed - discount.off(owed)\n"
    ),
    "tests/test_checkout.py": (
        "from shop.checkout import charge\n\n\n"
        "def test_a_code_takes_ten_percent_off() -> None:\n"
        '    assert charge({"mug": 2}, "WELCOME10") == 2160\n\n\n'
        "def test_an_unknown_code_changes_nothing() -> None:\n"
        '    assert charge({"mug": 2}, "NOPE") == 2400\n'
    ),
}

#: Attempt 2: the discount put in the cart's total, which the cart's own test does not allow.
_TWO = {
    "shop/cart.py": (
        '"""A cart: what somebody means to buy."""\n\n'
        "from shop.catalogue import PRICES\n\n\n"
        'def total(items: dict[str, int], code: str = "WELCOME10") -> int:\n'
        '    """What a cart comes to, in cents, after a discount code."""\n'
        "    owed = sum(PRICES[name] * count for name, count in items.items())\n"
        '    return owed * 90 // 100 if code == "WELCOME10" else owed\n'
    ),
}

#: Attempt 3: the codes beside `charge`, in a few lines. It passes, and is the smallest.
_THREE = {
    "shop/checkout.py": (
        '"""Paying for a cart."""\n\n'
        "from shop.cart import total\n\n"
        'CODES = {"WELCOME10": 10}\n\n\n'
        'def charge(items: dict[str, int], code: str = "") -> int:\n'
        '    """What is charged for a cart, in cents, after a discount code."""\n'
        "    return total(items) * (100 - CODES.get(code, 0)) // 100\n"
    ),
}


def _script(world: World, *, after: float) -> None:
    """Scripts the three attempts: what each writes in its worktree, and says of it.

    All three think as long as each other, so that their turns end together and what the
    flow prints of each comes after the last: `hmz exec` writes a printed line where its
    clock stands while a turn is still working, and the two run together on one line.
    """

    def line(text: str, writes: dict[str, str], wait: float) -> dict[str, Any]:
        return {
            "text": text,
            "writes": writes,
            "tools": [
                {
                    "name": "Edit",
                    "input": {"file_path": next(reversed(writes))},
                    "result": "edited",
                    "takes": 0.4,
                },
                {
                    "name": "Bash",
                    "input": {"command": "python3 -m pytest -q"},
                    "result": "passed",
                    "takes": 0.6,
                },
            ],
            "after": wait,
        }

    world.says(
        {
            "attempt 1 of": line(
                "Added shop/discounts.py with a Discount for each code, used it in"
                " charge(), and covered it with two tests.",
                _ONE,
                after,
            ),
            "attempt 2 of": line(
                "total() in shop/cart.py takes a discount code now: WELCOME10 is"
                " 10% off.",
                _TWO,
                after,
            ),
            "attempt 3 of": line(
                "charge() takes a discount code: WELCOME10 is 10% off, any other"
                " code changes nothing.",
                _THREE,
                after,
            ),
        }
    )


@pytest.fixture
def printing(monkeypatch: pytest.MonkeyPatch) -> None:
    """What a flow prints is said to every frontend, as in a daemon's own host process.

    A real daemon holds a workspace's runs in a process of their own, whose `print` is told
    to whoever follows the run (`hmz.daemon.detached`): `hmz exec` writes it out. The staged
    daemon holds them on threads of the test, where nothing does: this puts the same writer
    in place once a host is held, so that a picture of `hmz exec` has the lines a flow prints.
    """
    from hmz.daemon.carrying import Printed
    from hmz.runtime import Host

    made = Host.__init__

    def init(self: Host, *args: Any, **kwargs: Any) -> None:
        made(self, *args, **kwargs)
        monkeypatch.setattr(sys, "stdout", Printed(self))

    monkeypatch.setattr(Host, "__init__", init)


def _own(world: World) -> None:
    """Puts the page's flow among the project's own, as `@local/best_of`."""
    flow = world.workspace / ".hmz" / "flows" / "best_of"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(_FLOW)


_EXEC = [
    "hmz",
    "exec",
    "-f",
    "@local/best_of",
    "-a",
    f"coder={AGENT}",
    "-p",
    "budget.duration=30m",
    _TASK,
]


def test_the_flow_is_tested_on_fakes(world: World) -> None:
    _own(world)
    (world.workspace / "tests" / "test_best_of.py").write_text(_TEST)
    shots.cli(
        ["python3", "-m", "pytest", "-q", "tests/test_best_of.py"],
        f"{_PAGE}-test",
        columns=72,
    )


def test_three_attempts_from_the_command_line(world: World, printing: None) -> None:
    _own(world)
    _script(world, after=1.6)
    reel = shots.Reel(f"{_PAGE}-exec")
    reel.cli(_EXEC, rows=30, hold=4.0)
    reel.save()
    # What is left of it: the change that was kept, and no worktree but the project's own.
    shots.cli(["git", "diff"], f"{_PAGE}-diff", columns=88)
    shots.cli(["git", "worktree", "list"], f"{_PAGE}-cleaned", columns=88)
    # And an epic `hmz exec` ran is listed in the app like any other.
    with world.page(desktop=True) as page:
        expect(page.get_by_text(_TASK).first).to_be_visible()


def _running(world: World) -> str:
    """Starts the flow on the task and answers its epic's name, the three turns under way.

    `World.epic` looks its epic up the instant it started, which is before this one is
    listed: looked up again here until it is.
    """
    import time

    try:
        return world.epic(
            "@local/best_of", _TASK, budget={"output_tokens": 200_000}, until=None
        )
    except StopIteration:
        pass
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        runs = world.call("runs.list", workspace=str(world.workspace))["runs"]
        for one in runs:
            if one["task"] == _TASK:
                return str(one["name"])
        time.sleep(0.2)
    raise AssertionError("the epic was never listed")


def test_three_sessions_in_the_app(world: World) -> None:
    _own(world)
    _script(world, after=60)
    name = _running(world)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        expect(page.get_by_text("worktrees/").first).to_be_visible()
        zoom = page.get_by_role("button", name="Zoom in")
        zoom.click()
        zoom.click()
        page.wait_for_timeout(1500)
        shots.web(page, f"{_PAGE}-app", window="desktop", most=shots.REEL)
    world.stop(name)


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


async def test_three_sessions_in_the_terminal_monitor(world: World) -> None:
    _own(world)
    _script(world, after=60)
    async with world.tui(size=(100, 34)) as (app, pilot):
        await shows(pilot, MODEL)
        # Set up as its `/flow best_of` page would leave it: an agent for `coder`, a budget.
        app.settings.remember(
            "@local/best_of",
            {"coder": Runs(AGENT)},
            {},
            None,
            {"output_tokens": 200_000},
        )
        await pilot.press(*f"/flow @local/best_of {_TASK}", "enter")
        await shows(pilot, "conversation 3 of 3")
        await _settled(pilot)
        reel = shots.Reel(f"{_PAGE}-monitor")
        reel.tui(app, hold=1.8, caption="three turns start")
        await pilot.press("left")
        await shows(pilot, "monitor · graph", "3 sessions")
        await _settled(pilot, 1.0)
        reel.tui(app, hold=2.0, keys="left", caption="the monitor")
        await pilot.press("space")
        await shows(pilot, "session 3")
        await _settled(pilot, 1.0)
        reel.tui(app, hold=3.5, keys="space", caption="its sessions", poster=True)
        reel.save()
        await pilot.press(*"/stop", "enter")
        await _settled(pilot, 2.0)

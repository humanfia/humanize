"""The pictures of `docs/builder/loops.md`: one loop of the project's own, run until green.

The flow is the page's own, as the page prints it: `until_green` hands a coder the task round
after round, a fresh session each round, until the project's tests pass. It is run with
`hmz exec`, read back in the app as an epic of two sessions, run again as one long session,
and run once more with a turn that stalls, which the watchdog ends and the loop survives.
Run it by naming it: `uv run pytest tests/system/docs/test_docs_builder_loops.py`.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.docs.conftest import AGENT
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    import pytest
    from playwright.sync_api import Page

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "builder-loops"

_TASK = "Add a discount code to checkout"

#: The flow as the page prints it.
_UNTIL_GREEN = '''
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    HarnessError,
    LocalEnv,
    ShellEnvMixin,
    flow,
)

TESTS = ["python", "-m", "pytest", "-q"]


class Agents(AgentCollection):
    coder: Agent


class Workspace(LocalEnv, ShellEnvMixin):
    """The project, and a shell in it."""


class Envs(EnvCollection):
    workspace: Workspace


class Params(FlowParams):
    rounds: int = 5


@flow(agents=Agents, envs=Envs, params=Params)
async def until_green(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> bool:
    """Work on the task, round after round, until the tests pass."""
    coder, workspace = agents["coder"], envs["workspace"]
    prompt = task
    for _ in range(params.rounds):
        session = await coder.spawn()  # a fresh conversation every round
        try:
            await coder.run(prompt, session=session, env=workspace)
        except HarnessError:
            prompt = f"{task}\\n\\nThe last turn failed. Check what is already there."
            continue
        status, out, _ = await workspace.exec(TESTS)
        if status == 0:
            return True
        prompt = f"{task}\\n\\nThe tests still fail:\\n{out[-2000:]}"
    return False
'''

#: The same loop as one long conversation: `spawn` moved above the `for`.
_ONE_SESSION = _UNTIL_GREEN.replace(
    "    for _ in range(params.rounds):\n"
    "        session = await coder.spawn()  # a fresh conversation every round\n",
    "    session = await coder.spawn()  # one conversation for every round\n"
    "    for _ in range(params.rounds):\n",
)

#: The tests the loop runs: the second fails until no code is given its own answer.
_TEST = (
    "from shop.checkout import charge\n\n\n"
    "def test_a_code_takes_its_share_off() -> None:\n"
    '    assert charge({"mug": 1}, code="WELCOME10") == 1080\n\n\n'
    "def test_no_code_charges_in_full() -> None:\n"
    '    assert charge({"mug": 1}) == 1200\n'
)

_HALF = (
    '"""Paying for a cart."""\n\n'
    "from shop.cart import total\n\n"
    'CODES = {"WELCOME10": 10}\n\n\n'
    'def charge(items: dict[str, int], code: str = "") -> int:\n'
    '    """What is charged for a cart, in cents."""\n'
    "    return total(items) * (100 - CODES[code]) // 100\n"
)

_WHOLE = _HALF.replace("CODES[code]", "CODES.get(code, 0)")

_EDIT = {
    "name": "Edit",
    "input": {"file_path": "shop/checkout.py"},
    "result": "edited",
    "takes": 0.4,
}

#: What the agent says to the task, and to the task with the failing tests under it.
_SAYS = {
    "tests still fail": {
        "text": "charge() raised KeyError with no code. No code is no discount now.",
        "writes": {"shop/checkout.py": _WHOLE},
        "tools": [_EDIT],
    },
    "discount": {
        "text": "charge() takes a code now: WELCOME10 takes 10% off.",
        "writes": {"shop/checkout.py": _HALF},
        "tools": [_EDIT],
    },
}

#: The same, but its first turn starts the tests and never says another word.
_STALLS = {
    "last turn failed": {
        "text": "charge() takes a code now: WELCOME10 takes 10% off. 3 tests pass.",
        "writes": {"shop/checkout.py": _WHOLE},
        "tools": [_EDIT],
    },
    "discount": {
        "text": "never said",
        "tools": [
            {
                "name": "Bash",
                "input": {"command": "pytest -q"},
                "result": "",
                "takes": 600,
            }
        ],
    },
}


def _staged(world: World, source: str = _UNTIL_GREEN) -> None:
    """The flow where the page says to put it, and the tests it runs until they pass."""
    flows = world.workspace / ".hmz" / "flows"
    shutil.rmtree(flows)
    (flows / "until_green").mkdir(parents=True)
    (flows / "until_green" / "__init__.py").write_text(source.lstrip())
    world.committed("Test the discount code", {"tests/test_checkout.py": _TEST})


def _exec() -> list[str]:
    return [
        "hmz",
        "exec",
        "-f",
        "@local/until_green",
        "-a",
        f"coder={AGENT}",
        "-p",
        "budget.output_tokens=20000",
        _TASK,
    ]


def _opened(page: Page, name: str, sessions: str) -> None:
    """Opens an epic that is over on its graph alone, read whole, its side panel shut."""
    go(page, f"/epics/{name}")
    expect(page.get_by_text(sessions, exact=True)).to_be_visible()
    expect(page.get_by_text("Reading handovers")).to_have_count(0)
    page.get_by_role("button", name="Close panel").click()
    expect(page.get_by_role("complementary", name="the epic")).to_have_count(0)
    page.get_by_role("button", name="Recenter").click()
    page.wait_for_timeout(600)


def test_the_loop_runs_until_the_tests_pass(world: World) -> None:
    _staged(world)
    world.says(_SAYS)
    shots.cli(_exec(), f"{_PAGE}-exec")


def test_a_fresh_session_every_round_is_two_sessions_in_the_app(world: World) -> None:
    _staged(world)
    world.says(_SAYS)
    name = world.epic("@local/until_green", _TASK, budget={"output_tokens": 20000})
    with world.page(desktop=True, height=460) as page:
        _opened(page, name, "2 sessions")
        shots.web(page, f"{_PAGE}-fresh", window="desktop", most=shots.REEL)


def test_one_session_for_every_round_is_one_session_in_the_app(world: World) -> None:
    _staged(world, _ONE_SESSION)
    world.says(_SAYS)
    name = world.epic("@local/until_green", _TASK, budget={"output_tokens": 20000})
    with world.page(desktop=True, height=460) as page:
        _opened(page, name, "1 session")
        shots.web(page, f"{_PAGE}-one", window="desktop", most=shots.REEL)


def test_a_turn_that_stalls_is_ended_and_the_loop_goes_on(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _staged(world)
    world.says(_STALLS)
    # Five seconds of silence in place of fifteen minutes, said to the daemon, which is what
    # holds the epic and so what watches its turns: the page says the picture's window is.
    monkeypatch.setenv("HUMANIZE_WATCHDOG", "5")
    shots.cli(_exec(), f"{_PAGE}-watchdog")

"""The pictures of `docs/builder/worktrees.md`: more places to work than the one handed over.

The page prints two flows of the project's own. `guarded` snapshots the workspace, lets its
agent work, runs the project's check and rewinds when the check fails: here it is run from
the command line on a task that breaks the check, and git is asked what is left. `places`
derives a worktree, a temporary copy and a scratch directory and has its agent work in the
copy: here Humanize's `envs/` is listed while it runs and after it ended, and the epic is
opened in the app while its agent works in the copy. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_builder_worktrees.py`.
"""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.docs.conftest import AGENT
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Page

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "builder-worktrees"

_TASK = "Add a discount code to checkout"

#: The page's first flow, as the page prints it.
_GUARDED = '''
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    GitEnvMixin,
    LocalEnv,
    ShellEnvMixin,
    flow,
)

CHECK = ["python3", "-m", "pytest", "-q"]


class Agents(AgentCollection):
    coder: Agent


class Workspace(LocalEnv, ShellEnvMixin, GitEnvMixin):
    """The project. The flow may run programs in it and put it back."""


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def guarded(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> bool:
    """Try the task, and put everything back if the check fails."""
    coder, workspace = agents["coder"], envs["workspace"]
    before = await workspace.snapshot("before-task")
    await coder.run(task, session=await coder.spawn(), env=workspace)
    status, _, _ = await workspace.exec(CHECK)
    if status == 0:
        print("check passed: change kept")
        return True
    await workspace.rewind(before)
    print(f"check failed: rewound to {before}")
    return False
'''

#: The page's second flow: its three derivations are the page's three snippets.
_PLACES = '''
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FilesEnvMixin,
    FlowContext,
    FlowParams,
    GitWorktreeEnvMixin,
    LocalEnv,
    ScratchDirEnvMixin,
    TemporaryClonedDirEnvMixin,
    flow,
)


class Agents(AgentCollection):
    coder: Agent


class Workspace(
    LocalEnv,
    FilesEnvMixin,
    GitWorktreeEnvMixin,
    TemporaryClonedDirEnvMixin,
    ScratchDirEnvMixin,
):
    """The project, and what the flow may derive from it."""


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def places(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """One turn in a throwaway copy, with a worktree and notes beside it."""
    coder, workspace = agents["coder"], envs["workspace"]
    tree = await workspace.derive_worktree()
    trial = await workspace.derive_temp_clone("try-1")
    notes = await workspace.derive_scratch("notes")
    said = await coder.run(task, session=await coder.spawn(), env=trial)
    await notes.write("try-1.md", said.encode())
    return str(tree.workdir)
'''

#: What the agent leaves of the cart: the discount taken off every total, which the cart's
#: own test does not allow.
_BROKEN = (
    '"""A cart: what somebody means to buy."""\n\n'
    "from shop.catalogue import PRICES\n\n\n"
    'def total(items: dict[str, int], code: str = "WELCOME10") -> int:\n'
    '    """What a cart comes to, in cents, after a discount code."""\n'
    "    owed = sum(PRICES[name] * count for name, count in items.items())\n"
    '    return owed * 90 // 100 if code == "WELCOME10" else owed\n'
)


def _own(world: World, name: str, source: str) -> None:
    """Commits one of the page's flows among the project's own, as `@local/<name>`."""
    world.committed(f"Add the {name} flow", {f".hmz/flows/{name}/__init__.py": source})


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


# -- snapshots and rewinding ----------------------------------------------------------


def test_a_failed_check_is_rewound(world: World, printing: None) -> None:
    _own(world, "guarded", _GUARDED)
    world.says(
        {
            "discount": {
                "text": "total() in shop/cart.py takes a discount code now, and"
                " NOTES.md says why.",
                "tools": [
                    {
                        "name": "Edit",
                        "input": {"file_path": "shop/cart.py"},
                        "result": "edited",
                        "takes": 0.4,
                    },
                    {
                        "name": "Write",
                        "input": {"file_path": "NOTES.md"},
                        "result": "written",
                        "takes": 0.3,
                    },
                ],
                "writes": {
                    "shop/cart.py": _BROKEN,
                    "NOTES.md": "The discount is taken off in the cart.\n",
                },
                "after": 1.0,
            }
        }
    )
    reel = shots.Reel(f"{_PAGE}-rewound")
    reel.cli(
        [
            "hmz",
            "exec",
            "-f",
            "@local/guarded",
            "-a",
            f"coder={AGENT}",
            "-p",
            "budget.duration=30m",
            _TASK,
        ],
        rows=12,
        hold=4.0,
    )
    reel.save()
    # What is left of it: nothing the agent wrote, and the snapshot it was put back to.
    assert not (world.workspace / "NOTES.md").exists()
    shots.cli(["git", "status"], f"{_PAGE}-clean", columns=80)


# -- where what is derived is kept, and for how long ----------------------------------


def _listed(home: Path, name: str) -> None:
    """A picture of what Humanize keeps under `envs/` in its home, three levels of it."""
    shots.cli(
        [
            "find",
            ".local/state/humanize/envs",
            "-mindepth",
            "3",
            "-maxdepth",
            "3",
            "-type",
            "d",
        ],
        name,
        cwd=home,
        columns=80,
    )


def _running(world: World) -> str:
    """Starts `places` on the task and answers its epic's name, its one turn under way.

    `World.epic` looks its epic up the instant it started, which may be before it is
    listed: looked up again here until it is.
    """
    try:
        return world.epic(
            "@local/places", _TASK, budget={"output_tokens": 200_000}, until=None
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


def _waited(ready: Any, seconds: float = 120) -> None:
    deadline = time.monotonic() + seconds
    while not ready():
        assert time.monotonic() < deadline, "what was waited for never came"
        time.sleep(0.2)


def test_copies_and_scratch_go_when_the_flow_ends(world: World) -> None:
    _own(world, "places", _PLACES)
    world.says(
        {"discount": {"text": "charge() takes a discount code now.", "after": 25}}
    )
    envs = world.state / "envs"
    _running(world)
    _waited(lambda: any(envs.glob("*/scratch/*")))
    _listed(world.home, f"{_PAGE}-kept-running")
    _waited(
        lambda: not any(envs.glob("*/scratch/*")) and not any(envs.glob("*/clones/*/"))
    )
    assert any(envs.glob("*/worktrees/*"))
    _listed(world.home, f"{_PAGE}-kept-after")


def _dragged(page: Page, handle: str, by: int) -> None:
    """Drags one of the page's dividers sideways, as a person does to read a long name."""
    box = page.locator(handle).first.bounding_box()
    assert box is not None
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + by, y, steps=8)
    page.mouse.up()


def test_a_turn_in_a_copy_in_the_app(world: World) -> None:
    _own(world, "places", _PLACES)
    world.says(
        {"discount": {"text": "charge() takes a discount code now.", "after": 90}}
    )
    name = _running(world)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        expect(page.get_by_text("clones/").first).to_be_visible()
        page.locator("[data-hmz=envs-open]").first.click()
        copy = page.get_by_text("workspace#temp").first
        expect(copy).to_be_visible()
        # The list is dragged wider, so that each environment's whole name is read.
        _dragged(page, "[data-hmz=envs-resizer]", 170)
        copy.click()
        page.wait_for_timeout(2500)
        shots.web(page, f"{_PAGE}-app", window="desktop", most=shots.REEL)
    world.stop(name)

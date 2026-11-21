"""The pictures of `docs/user/environments.md`: where a chat or an epic works.

The folder chip and the form that opens a folder by its path; the environment chip of a new
chat, and a chat started in a new git worktree; a chat moved to another directory between its
turns; the rows of a new epic that say where each environment role works; `/env`, a role's
form and the hosts its machine is picked from in the terminal interface; and
`hmz chat --worktree` from the command line. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_environments.py`.

No machine but this one is reached: the runtimes are saved, which reaches nothing, and are
only listed. A chat is moved to another directory of this machine, not to one of them.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import TYPE_CHECKING, Any, cast

from playwright.sync_api import expect

from hmz.tui.flows import Flows
from hmz.tui.pick import Hosts
from tests.integration.doubles_tui import on, onto, shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Locator, Page

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-environments"

_TASK = "Add a discount code to checkout"
_TRY = "Try the discount as a percentage"
_NEXT = "Run the tests here too"

_ANSWER = (
    "Checkout takes a discount code now: charge() looks the code up and takes its"
    " discount off the total. WELCOME10 is 10% off. The tests pass."
)
_TRIED = (
    "Done in this worktree: charge() takes a percentage off the total. Your folder is"
    " as it was."
)
_RAN = "Ran pytest in this directory: 3 passed."

#: Another checkout of the project on this machine, which a chat is moved to.
_OTHER = "shop-staging"

#: A flow of the project's own with an environment role its person fills.
_ON_BOX = '''"""One agent does the task in an environment you choose."""

from hmz.flows import (
    Agent,
    AgentCollection,
    Env,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    ShellEnvMixin,
    flow,
)


class Box(Env, ShellEnvMixin):
    """Another machine, and a shell on it."""


class Agents(AgentCollection):
    builder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv  # the folder the epic starts in
    box: Box  # wherever you say


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def on_box(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """One agent does the task in an environment you choose."""
    builder = agents["builder"]
    session = await builder.spawn()
    await builder.run(task, session=session, env=envs["box"])
'''


#: How tall the bar over a view is, in CSS pixels.
_BAR = 46


class _Part:
    """A part of the page that no one element is: a box of it, found as a locator's is."""

    def __init__(self, left: float, top: float, right: float, bottom: float) -> None:
        self._box = {"x": left, "y": top, "width": right - left, "height": bottom - top}

    def bounding_box(self) -> dict[str, float]:
        return self._box


def _around(*parts: Locator, pad: float = 14) -> Any:
    """The box that holds every one of these parts of the page, with room around it."""
    boxes = [one.bounding_box() for one in parts]
    found = [one for one in boxes if one is not None]
    assert len(found) == len(parts)
    return cast(
        "Any",
        _Part(
            min(one["x"] for one in found) - pad,
            min(one["y"] for one in found) - pad,
            max(one["x"] + one["width"] for one in found) + pad,
            max(one["y"] + one["height"] for one in found) + pad,
        ),
    )


def _foot(
    page: Page, above: float | None = 330, *, left: float = 0, right: float = 0
) -> Any:
    """The column a chat is read and written in: its box, and what stands over it.

    Args:
      page: The page.
      above: How much over the box is kept, where a chip's menu opens: None for all of it,
        which is the transcript.
      left: How much more is kept at the left of the column, where a panel opens wider.
      right: How much of the column's right is left out.
    """
    found = page.locator("form.composer:visible").first.bounding_box()
    view = page.get_by_role("main").bounding_box()
    assert found is not None
    assert view is not None
    # Under the view's own bar, which a column of it would cut the title of.
    top = max(view["y"] + _BAR, found["y"] - (above or view["height"]))
    return cast(
        "Any",
        _Part(
            max(view["x"], found["x"] - 20 - left),
            top,
            found["x"] + found["width"] + 20 - right,
            view["y"] + view["height"],
        ),
    )


def _runtimes(world: World) -> None:
    """Saves two runtimes, which reaches neither: what the chip's menu then lists."""
    world.call(
        "runtimes.set",
        backend="ssh",
        name="gpu-box",
        fields={"host": "gpu.example", "workdir": "~/shop"},
    )
    world.call(
        "runtimes.set",
        backend="docker",
        name="sandbox",
        fields={"image": "shop-dev:latest"},
    )


def _on_box(world: World) -> None:
    flow = world.workspace / ".hmz" / "flows" / "on_box"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(_ON_BOX)


def _other(world: World) -> Path:
    """Another checkout of the project beside it, a git repository of its own."""
    other = world.home / _OTHER
    shutil.copytree(
        world.workspace,
        other,
        ignore=shutil.ignore_patterns(".git", ".hmz", "__pycache__"),
    )
    for argv in (
        ("init", "-q", "-b", "main"),
        ("add", "-A"),
        ("commit", "-q", "-m", "Start the shop"),
    ):
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Alex Kim",
                "-c",
                "user.email=alex@example.com",
                *argv,
            ],
            cwd=other,
            check=True,
            capture_output=True,
        )
    return other


def _ready(page: Page) -> Locator:
    """The box of a new chat, once the agent it would start is on offer under it."""
    expect(page.get_by_role("button", name=re.compile("Nous: .*Haiku"))).to_be_visible()
    return page.get_by_role("textbox", name="First message")


def test_a_folder_is_picked_or_opened_by_its_path(world: World) -> None:
    _other(world)
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        _ready(page)
        chip = page.locator("[data-hmz=folder]")
        reel = shots.Reel(
            f"{_PAGE}-folder", clip=_foot(page, 300, left=110, right=240), pad=0
        )
        reel.web(page, hold=1.3, pointer=chip, click=True)
        chip.click()
        open_ = page.get_by_role("menuitem", name="Open folder…")
        expect(open_).to_be_visible()
        reel.web(page, hold=1.8, pointer=open_, click=True)
        open_.click()
        browse = page.get_by_role("button", name=re.compile("^Browse for"))
        expect(browse.first).to_be_visible()
        reel.web(page, hold=1.2, pointer=browse.first, click=True)
        browse.first.click()
        row = page.get_by_text(_OTHER, exact=True).last
        expect(row).to_be_visible()
        reel.web(page, hold=2.6, pointer=row, poster=True)
        reel.save()


def test_where_a_new_chat_works_is_picked_under_its_box(world: World) -> None:
    _runtimes(world)
    world.says({"percentage": {"text": _TRIED, "after": 1.2}})
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        box = _ready(page)
        chip = page.locator("[data-hmz=environment]")
        chip.click()
        menu = page.get_by_role("menu", name="Environment")
        expect(menu.get_by_role("menuitemradio", name="gpu-box")).to_be_visible()
        tree = page.locator("[data-hmz=new-worktree]")
        expect(tree).not_to_have_attribute("aria-disabled", "true")
        shots.web(page, f"{_PAGE}-menu", clip=_around(menu, chip, pad=20), pad=0)
        page.keyboard.press("Escape")
        expect(menu).to_be_hidden()

        reel = shots.Reel(f"{_PAGE}-worktree", clip=_foot(page, None), pad=0)
        reel.web(page, hold=1.2, pointer=chip, click=True)
        chip.click()
        expect(tree).to_be_visible()
        reel.web(page, hold=1.6, pointer=tree, click=True)
        tree.click()
        expect(chip).to_contain_text("New worktree")
        reel.web(page, hold=1.2, pointer=box, click=True)
        reel.type(page, box, _TRY, per=11)
        box.press("Enter")
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        expect(page.get_by_role("log")).to_contain_text("worktree")
        expect(page.get_by_role("button", name="Send")).to_be_visible()
        reel.web(page, hold=4, poster=True)
        reel.save()


def test_a_chat_is_moved_between_turns(world: World) -> None:
    _other(world)
    _runtimes(world)
    world.says({"discount": _ANSWER, "tests here": _RAN})
    chat = world.chat(_TASK, going=True)
    with world.page(desktop=True) as page:
        go(page, f"/chats/{chat}")
        expect(page.get_by_role("log")).to_contain_text("WELCOME10")
        box = page.get_by_role("textbox", name="What to say")
        expect(page.get_by_role("button", name="Send")).to_be_visible()
        chip = page.locator("[data-hmz=environment]")
        expect(chip).to_contain_text("This computer")
        reel = shots.Reel(f"{_PAGE}-move", clip=_foot(page, None), pad=0)
        reel.web(page, hold=1.2, pointer=chip, click=True)
        chip.click()
        choose = page.locator("[data-hmz=env-dir-choose]")
        expect(choose).to_be_visible()
        reel.web(page, hold=1.6, pointer=choose, click=True)
        choose.click()
        directory = page.locator("[data-hmz=env-dir]")
        expect(directory).to_be_visible()
        directory.fill("")
        reel.web(page, hold=0.8)
        reel.type(page, directory, f"~/{_OTHER}", per=4)
        use = page.locator("[data-hmz=env-dir-pick]")
        reel.web(page, hold=0.9, pointer=use, click=True)
        use.click()
        expect(chip).to_contain_text(_OTHER)
        reel.web(page, hold=1.4, pointer=box, click=True)
        reel.type(page, box, _NEXT, per=11)
        box.press("Enter")
        expect(page.get_by_role("log")).to_contain_text("3 passed")
        expect(page.get_by_role("button", name="Send")).to_be_visible()
        reel.web(page, hold=4, poster=True)
        reel.save()


def test_an_epic_says_where_each_environment_role_works(world: World) -> None:
    _runtimes(world)
    _on_box(world)
    with world.page(desktop=True) as page:
        go(page, "/new?flow=%40local%2Fon_box")
        row = page.locator("[data-hmz=env][data-role=box]")
        expect(row).to_be_visible()
        row.locator("[data-hmz=pick-backend]").select_option("ssh")
        expect(row.locator("[data-hmz=pick-runtime]")).to_have_value("gpu-box")
        expect(page.get_by_text("Asking…")).to_have_count(0)
        heading = page.get_by_text("Environment", exact=True).first
        shots.web(page, f"{_PAGE}-epic", clip=_around(heading, row, pad=18), pad=0)


async def test_the_environments_in_the_terminal(world: World) -> None:
    world.says({"discount": _ANSWER})
    async with world.tui((100, 26)) as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*_TASK, "enter")
        await shows(pilot, "WELCOME10")
        await shows(pilot, "Worked for")
        await pilot.press(*"/env", "enter")
        await shows(pilot, "Environments", "workspace")
        await pilot.pause(0.6)
        shots.tui(app, f"{_PAGE}-terminal")


async def test_a_role_is_placed_in_the_terminal(world: World) -> None:
    _runtimes(world)
    _on_box(world)
    async with world.tui((100, 30)) as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*"/flow on_box", "enter")
        await on(pilot, Flows)
        await onto(pilot, "@box")
        await pilot.press("enter")
        await shows(pilot, "Environment for box")
        # A whole spec typed in the last row sets the rows over it.
        await onto(pilot, "spelled")
        await pilot.press(*"ssh@gpu-box")
        await pilot.pause(0.4)
        await pilot.press("enter")
        await shows(pilot, "ssh@gpu-box", "~/shop")
        await pilot.pause(0.6)
        shots.tui(app, f"{_PAGE}-terminal-role")
        # The machine's row opens the saved hosts of the backend, and the buttons under them.
        await onto(pilot, "provider")
        await pilot.press("enter")
        await on(pilot, Hosts)
        await shows(pilot, "Select the ssh host to use", "gpu-box", "Name a host")
        await pilot.pause(0.6)
        shots.tui(app, f"{_PAGE}-terminal-host")


def test_a_chat_in_a_worktree_from_the_command_line(world: World) -> None:
    world.says({"percentage": {"text": _TRIED, "after": 0.8}})
    reel = shots.Reel(f"{_PAGE}-cli")
    reel.cli(["hmz", "chat", "--worktree", "-a", AGENT, _TRY], rows=9)
    reel.save()
    shots.cli(["git", "worktree", "list"], f"{_PAGE}-cli-worktrees", columns=116)

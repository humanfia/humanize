"""The pictures of `docs/user/environment-panels.md`: files, changes and a terminal.

A chat whose agent changed two files of the project is left going, and its environment is
opened beside it: the changes and a diff, a commit made from the panel, a file in the editor,
a shell. Then the same environment from the terminal interface, under `/env`, and the
Environments view of an epic while it runs. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_environment_panels.py`.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect
from textual.widgets import OptionList

from hmz.tui.envs import Changes, Diff, Editing, Envs, Files
from tests.integration.doubles_tui import on, shows
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-environment-panels"

_TASK = "Add a discount code to checkout"

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


def test_an_unknown_code_changes_nothing() -> None:
    assert charge({"mug": 2}, "SPRING") == 2400
"""

_README = """# shop

A small storefront: a catalogue, a cart and a checkout.

Checkout takes a discount code: `WELCOME10` is 10% off.
"""

#: What the agent does when told the task: it edits checkout, and writes tests for it.
_WORK = {
    "text": (
        "Checkout takes a discount code now: WELCOME10 is 10% off. I added two tests"
        " for it in tests/test_checkout.py, and a line in the README."
    ),
    "tools": [
        {
            "name": "Edit",
            "input": {"file_path": "shop/checkout.py"},
            "result": "edited",
            "takes": 0.2,
        },
        {
            "name": "Write",
            "input": {"file_path": "tests/test_checkout.py"},
            "result": "written",
            "takes": 0.2,
        },
    ],
    "writes": {
        "shop/checkout.py": _CHECKOUT,
        "tests/test_checkout.py": _TESTS,
        "README.md": _README,
    },
}

#: What the shell of the person's machine says before a command: nothing of this machine's.
_PROMPT = "PROMPT='alex@studio shop %# '\nPS1='alex@studio shop $ '\n"


def _prompted(world: World) -> None:
    """Gives the person's shell a prompt of their own: their name, and their machine's."""
    for name in (".zshrc", ".bashrc", ".bash_profile", ".profile"):
        (world.home / name).write_text(_PROMPT)


def _no_webgl(page: Page) -> None:
    """Has the page draw its terminal itself, as it does in a browser with no WebGL.

    A terminal drawn by WebGL is not printed, so no picture would hold it.
    """
    page.evaluate(
        """() => {
            const was = HTMLCanvasElement.prototype.getContext
            HTMLCanvasElement.prototype.getContext = function (kind, ...more) {
                return /webgl/.test(kind) ? null : was.call(this, kind, ...more)
            }
        }"""
    )


#: A name MuPDF gave something inside a definition, which is only that page's own.
_LOCAL = re.compile(r'id="([a-z]+_\d+)"')


@pytest.fixture
def _own_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keeps what one frame of a reel defines apart from what another does.

    A page's icon drawn through a CSS mask is printed as a mask holding a clip path under a
    name of that printed page's own (`clip_90`). `shots` keeps that name as it is, so two
    frames of one reel whose icons stand in different places both define `clip_90`, and the
    file draws the later frame's icon through the earlier one's clip: a square. Here such a
    name is said after what it is inside, so that two things never share one.
    """
    put = shots._Defs.put  # noqa: SLF001

    def named(self: Any, tag: str, attributes: dict[str, str], inner: str = "") -> str:
        local = set(_LOCAL.findall(inner))
        if local:
            mark = hashlib.sha1(inner.encode()).hexdigest()[:8]  # noqa: S324
            for name in local:
                for was in (f'id="{name}"', f"url(#{name})", f'href="#{name}"'):
                    inner = inner.replace(was, was.replace(name, f"{name}-{mark}"))
        return put(self, tag, attributes, inner)

    monkeypatch.setattr(shots._Defs, "put", named)  # noqa: SLF001


def _typed(page: Page, command: str) -> None:
    """Runs a command in the terminal on show, and leaves it with its cursor standing still."""
    page.locator("[data-hmz=term-host]:visible").click()
    page.keyboard.type(command, delay=20)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)
    page.evaluate("() => document.activeElement.blur()")
    page.wait_for_timeout(800)


def test_the_panes_beside_a_chat(world: World) -> None:
    _prompted(world)
    world.says({"discount": _WORK})
    chat = world.chat(_TASK, going=True)
    with world.page(desktop=True) as page:
        go(page, f"/chats/{chat}")
        _no_webgl(page)
        expect(page.get_by_role("log")).to_contain_text("WELCOME10")
        reel = shots.Reel(f"{_PAGE}-panes", window="desktop")

        changes = page.get_by_role("button", name="Changes")
        reel.web(page, hold=1.4, pointer=changes, click=True)
        changes.click()
        changed = page.locator("[data-hmz=change][data-path='shop/checkout.py']")
        expect(changed).to_be_visible()
        page.wait_for_timeout(800)
        reel.web(page, hold=1.6, pointer=changed, click=True, caption="Changes")
        changed.click()
        expect(page.get_by_text("WELCOME10").last).to_be_visible()
        page.wait_for_timeout(800)
        files = page.get_by_role("button", name="Files")
        reel.web(page, hold=2.2, pointer=files, click=True, caption="Changes: a diff")
        files.click()
        readme = page.locator("[data-hmz=files-row]", has_text="README.md")
        expect(readme).to_be_visible()
        readme.dblclick()
        expect(page.locator("[data-hmz=files-tab]")).to_have_count(1)
        page.wait_for_timeout(800)
        terminal = page.get_by_role("button", name="Terminal")
        reel.web(page, hold=2.0, pointer=terminal, click=True, caption="Files")
        terminal.click()
        expect(page.locator("[data-hmz=term-tab]")).to_have_count(1)
        page.wait_for_timeout(1500)
        _typed(page, "git status --short")
        reel.web(page, hold=3.0, caption="Terminal", poster=True)
        reel.save()


@pytest.mark.usefixtures("_own_names")
def test_the_environment_in_its_own_view(world: World) -> None:
    _prompted(world)
    # What is committed from the panel is the person's, by the project's own git settings.
    for key, value in (("user.name", "Alex Kim"), ("user.email", "alex@example.com")):
        subprocess.run(["git", "config", key, value], cwd=world.workspace, check=True)
    world.says({"discount": _WORK})
    chat = world.chat(_TASK, going=True)
    with world.page(desktop=True) as page:
        go(page, f"/chats/{chat}")
        page.get_by_role("button", name="Changes").click()
        changed = page.locator("[data-hmz=change][data-path='shop/checkout.py']")
        expect(changed).to_be_visible()
        page.locator("[data-hmz=envs-full]").click()
        _no_webgl(page)
        expect(page.locator("[data-hmz=envs-view]")).to_be_visible()
        # Room for the panels: the sidebar folded, and the list of changes drawn wider.
        page.get_by_role("button", name="Hide sidebar").click()
        split = page.locator("[data-hmz=changes-split]")
        split.focus()
        for _ in range(6):
            page.keyboard.press("ArrowRight")

        # -- Changes: the list, and the diff of one file beside it --------------------
        changed = page.locator("[data-hmz=change][data-path='shop/checkout.py']")
        changed.click()
        expect(page.get_by_text("WELCOME10").last).to_be_visible()
        page.wait_for_timeout(800)
        shots.web(page, f"{_PAGE}-changes", window="desktop")

        # -- Files: the explorer, and a file in the editor ------------------------------
        page.locator("[data-hmz=diff-close]").click()
        page.locator("[data-hmz=envs-tab-files]").click()
        tree = page.locator("[data-hmz=files-tree]")
        tree.locator("[data-hmz=files-row]", has_text="shop").first.click()
        row = tree.locator("[data-hmz=files-row]", has_text="cart.py")
        expect(row).to_be_visible()
        row.dblclick()
        expect(page.locator("[data-hmz=files-editor]")).to_contain_text("PRICES")
        tree.locator("[data-hmz=files-row]", has_text="checkout.py").dblclick()
        expect(page.locator("[data-hmz=files-editor]")).to_contain_text("CODES")
        page.wait_for_timeout(800)
        shots.web(page, f"{_PAGE}-files", window="desktop")

        # -- a commit: one file staged, a message, and the commit among the last ------
        page.set_viewport_size({"width": shots.DESKTOP[0], "height": 540})
        page.locator("[data-hmz=envs-tab-changes]").click()
        side = page.locator("[data-hmz=changes] > :first-child")
        changed.hover()
        page.locator("[data-hmz=commits] summary").click()
        expect(page.locator("[data-hmz=commit-row]")).to_have_count(1)
        page.locator("[data-hmz=changes-refresh]").click()
        page.wait_for_timeout(1500)
        reel = shots.Reel(f"{_PAGE}-commit", clip=side, pad=4)
        changed.hover()
        stage = changed.get_by_role("button", name="Stage Changes")
        reel.web(page, hold=1.4, pointer=stage, click=True, caption="Stage Changes")
        stage.click()
        expect(page.get_by_text("Staged Changes")).to_be_visible()
        message = page.locator("[data-hmz=commit-message]")
        reel.web(page, hold=1.0, pointer=message, click=True)
        reel.type(page, message, "Add a discount code to checkout", per=6)
        commit = page.locator("[data-hmz=changes-commit]")
        reel.web(page, hold=1.0, pointer=commit, click=True, caption="Commit")
        commit.click()
        expect(page.get_by_text("Staged Changes")).to_have_count(0)
        expect(page.locator("[data-hmz=commit-row]")).to_have_count(2)
        page.wait_for_timeout(3000)
        reel.web(page, hold=3.0, caption="Commits", poster=True)
        reel.save()

        # -- a conflict: the file changes on disk under an edit not yet written --------
        page.locator("[data-hmz=envs-tab-files]").click()
        page.wait_for_timeout(1500)
        page.locator("[data-hmz=files-editor] .cm-content").click()
        page.keyboard.press("ControlOrMeta+End")
        page.keyboard.type("\n# TODO: codes that expire\n")
        world.changed(
            {"shop/checkout.py": _CHECKOUT.replace("10}", '10, "SPRING5": 5}')}
        )
        expect(page.locator("[data-hmz=files-conflict]")).to_be_visible()
        page.evaluate("() => document.activeElement.blur()")
        page.wait_for_timeout(600)
        shots.web(page, f"{_PAGE}-conflict", clip="[data-hmz=files]", pad=0)
        page.locator("[data-hmz=files-reload]").click()
        expect(page.locator("[data-hmz=files-conflict]")).to_be_hidden()

        # -- search in files -----------------------------------------------------------
        page.locator("[data-hmz=files-side-search]").click()
        query = page.locator("[data-hmz=files-search-query]")
        query.fill("total")
        query.press("Enter")
        expect(page.locator("[data-hmz=files-search-summary]")).to_contain_text("files")
        page.wait_for_timeout(500)
        shots.web(page, f"{_PAGE}-search", clip="[data-hmz=files]", pad=0)

        # -- the menu of an editor tab: a kept tab, a preview tab, and what a tab offers -
        page.locator("[data-hmz=files-side-explorer]").click()
        tree.locator("[data-hmz=files-row]", has_text="cart.py").click()
        expect(page.locator("[data-hmz=files-editor]")).to_contain_text("PRICES")
        preview = page.locator("[data-hmz=files-tab]", has_text="cart.py")
        expect(preview).to_be_visible()
        preview.click(button="right")
        expect(page.get_by_role("menuitem", name="Keep open")).to_be_visible()
        page.wait_for_timeout(500)
        shots.web(page, f"{_PAGE}-tab-menu", clip="[data-hmz=files]", pad=0)
        page.keyboard.press("Escape")

        # -- Terminal: two shells, and what one printed --------------------------------
        page.locator("[data-hmz=envs-tab-terminal]").click()
        expect(page.locator("[data-hmz=term-tab]")).to_have_count(1)
        page.wait_for_timeout(1500)
        _typed(page, "git status --short")
        page.locator("[data-hmz=term-new]").click()
        expect(page.locator("[data-hmz=term-tab]")).to_have_count(2)
        page.wait_for_timeout(1500)
        page.locator("[data-hmz=term-tab]").first.click()
        page.wait_for_timeout(800)
        page.evaluate("() => document.activeElement.blur()")
        page.wait_for_timeout(500)
        shots.web(page, f"{_PAGE}-terminal", window="desktop")


#: A flow of the project's own that tries the task twice, each try in a worktree of its own.
_TWO_TRIES = '''
"""Two tries at one task, each in a git worktree of its own."""

import asyncio

from hmz.flows import (
    Agent, AgentCollection, EnvCollection, FlowContext, FlowParams, GitWorktreeEnvMixin,
    LocalEnv, ShellEnvMixin, flow,
)


class Agents(AgentCollection):
    coder: Agent


class Workspace(LocalEnv, ShellEnvMixin, GitWorktreeEnvMixin):
    """The project, a shell in it, and worktrees of it."""


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def two_tries(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Two tries at one task, each in a git worktree of its own."""
    coder, workspace = agents["coder"], envs["workspace"]

    async def attempt() -> None:
        tree = await workspace.derive_worktree()
        await coder.run(task, session=await coder.spawn(), env=tree)

    await asyncio.gather(attempt(), attempt())
'''


def test_the_environments_of_an_epic_while_it_runs(world: World) -> None:
    _prompted(world)
    flow = world.workspace / ".hmz" / "flows" / "two_tries"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(_TWO_TRIES)
    world.says({"discount": {**_WORK, "after": 60}})
    name = world.epic("@local/two_tries", _TASK, until=None)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        _no_webgl(page)
        opens = page.locator("[data-hmz=envs-open]")
        expect(opens).to_be_visible()
        opens.click()
        expect(page.locator("[data-hmz=envs-view]")).to_be_visible()
        expect(page.locator("[data-hmz=envs-item]")).to_have_count(3)
        page.locator("[data-hmz=envs-item]").nth(1).click()
        page.locator("[data-hmz=envs-tab-files]").click()
        expect(
            page.locator("[data-hmz=files-row]:visible", has_text="README.md")
        ).to_be_visible()
        page.wait_for_timeout(1500)
        shots.web(page, f"{_PAGE}-view", window="desktop")
    world.stop(name)


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


async def _onto(pilot: Pilot[None], name: str) -> None:
    """Walks the cursor of the list on top on to the row that says a name."""
    listed = pilot.app.screen.query_one("#choices", OptionList)
    at = next(at for at, one in enumerate(listed.options) if name in str(one.prompt))
    for _ in range(len(listed.options) + 1):
        if listed.highlighted == at:
            break
        await pilot.press("down" if (listed.highlighted or 0) < at else "up")
    assert listed.highlighted == at, f"the cursor never reached {name!r}"
    await pilot.pause()


async def test_the_environment_in_the_terminal_interface(world: World) -> None:
    _prompted(world)
    world.says({"discount": _WORK})
    async with world.tui() as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*_TASK, "enter")
        await shows(pilot, "README", "done")
        await _settled(pilot)

        # -- /env: the list, an environment's files, and its changes -------------------
        reel = shots.Reel(f"{_PAGE}-tui")
        reel.tui(app, hold=1.2)
        await pilot.press(*"/env")
        await _settled(pilot)
        reel.tui(app, hold=0.8, keys="/env", cut=True)
        await pilot.press("enter")
        await on(pilot, Envs)
        await _settled(pilot)
        reel.tui(app, hold=1.6, keys="enter", caption="the environments")
        await pilot.press("enter")
        await on(pilot, Files)
        await shows(pilot, "pyproject.toml")
        await _onto(pilot, "shop/")
        await _settled(pilot)
        reel.tui(app, hold=1.6, keys="enter", caption="Files")
        await pilot.press("enter")
        await shows(pilot, "checkout.py")
        await _onto(pilot, "checkout.py")
        await _settled(pilot)
        reel.tui(app, hold=1.4, keys="enter", caption="into a folder")
        await pilot.press("enter")
        await on(pilot, Editing)
        await shows(pilot, "CODES")
        await _settled(pilot)
        reel.tui(app, hold=2.2, keys="enter", caption="a file, in the editor")
        shots.tui(app, f"{_PAGE}-tui-editor")
        await pilot.press("escape")
        await on(pilot, Files)
        await pilot.press("tab")
        await on(pilot, Changes)
        await shows(pilot, "Untracked")
        await _onto(pilot, "checkout.py")
        await _settled(pilot)
        reel.tui(app, hold=1.8, keys="esc tab", caption="Changes")
        await pilot.press("enter")
        await on(pilot, Diff)
        await _settled(pilot)
        reel.tui(app, hold=3.0, keys="enter", caption="a diff", poster=True)
        reel.save()
        await pilot.press("q")
        await on(pilot, Changes)

        # -- a file staged, and the commit form ---------------------------------------
        await pilot.press("s")
        await shows(pilot, "Staged")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-tui-changes")
        await pilot.press("c")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-tui-commit")

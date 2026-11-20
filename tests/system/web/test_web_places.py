"""`hmz web` serves the machine, as the daemon does: every workspace's epics, started anywhere.

The interface is started in one project and asked about another, as a browser on it would: the
epics of both are listed, each under its own workspace, an epic is started in either, and a
workspace is opened by its path and forgotten again.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from hmz.rpc import RpcError
from tests.integration.doubles_core import install, write_flow
from tests.integration.doubles_web import Browser, Session, served
from tests.system.web.doubles_browser import ENGINES, Wire, chatted, go, opened, stop

if TYPE_CHECKING:
    from pathlib import Path

#: Local is a daemon of this process, which the page reaches over `/rpc` as any other.
pytestmark = pytest.mark.usefixtures("daemon")


#: The control that names the folder picked, by the form it is on: a new chat keeps it on
#: `Environment` under its box, a new epic in `Environment` in the middle of the page.
_FOLDER = {
    "/new/chat": "[data-hmz=start] [data-hmz=environment]",
    "/new": "[data-hmz=setup-folder] [data-hmz=workspace-picker]",
}


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, and the project the interface is started in."""
    project = install(tmp_path, monkeypatch)
    # The home it gives the CLI is this machine's home, which the daemon's own settings are of.
    (tmp_path / "home").mkdir(exist_ok=True)
    return project


@pytest.fixture
def other(tmp_path: Path) -> Path:
    """Another project on the same machine."""
    at = tmp_path / "other"
    at.mkdir()
    return at.resolve()


def _ran(browser: Browser, workspace: Path, task: str) -> None:
    """Starts a chat in a workspace and rests it once it has answered, as a page would."""
    with browser.session() as page:
        chatted(page, workspace, task)


def test_every_workspaces_chats_are_listed_and_found_by_workspace(
    project: Path, other: Path
) -> None:
    here = project.resolve()
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        _ran(browser, here, "in the first")
        _ran(browser, other, "in the second")

        with browser.session() as page:
            listed = page.call("chat.list")["chats"]
            assert {(one["title"], one["workspace"]) for one in listed} == {
                ("in the first", str(here)),
                ("in the second", str(other)),
            }
            only = page.call("chat.list", workspace=str(other))["chats"]
            assert [one["title"] for one in only] == ["in the second"]
            (one,) = only
            assert page.call("chat.get", chat=one["id"])["workspace"] == str(other)
            # A chat is no epic: none is listed among the epics.
            assert page.call("runs.list")["runs"] == []
            places = page.call("workspaces.list", here=str(here))
        assert places["here"] == str(here)
        assert [one["path"] for one in places["workspaces"]][:1] == [str(here)]
        # Each counts its chat as a chat, and no epic (Section 4.17.5.1 of [DAEMON]).
        assert {
            one["path"]: (one["epics"], one["chats"]) for one in places["workspaces"]
        } == {str(here): (0, 1), str(other): (0, 1)}


def test_a_workspace_is_opened_by_its_path_and_forgotten(
    project: Path, other: Path, tmp_path: Path
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()

        with browser.session() as page:
            kept = _writes(page, "workspaces.add", workspace=str(other))
            assert kept["kept"] == str(other)
            assert str(other) in [one["path"] for one in kept["workspaces"]]
            for workspace, code in (("relative", 400), (str(tmp_path / "gone"), 404)):
                with pytest.raises(RpcError) as refused:
                    _writes(page, "workspaces.add", workspace=workspace)
                assert refused.value.code == code

            _writes(page, "workspaces.forget", workspace=str(other))
            listed = page.call("workspaces.list")["workspaces"]
        assert str(other) not in [one["path"] for one in listed]


def _writes(page: Session, method: str, **params: Any) -> Any:
    """Calls a write, as the page does: with an `idem` of its own."""
    return page.call(method, **params, idem=uuid.uuid4().hex)


@pytest.mark.parametrize("engine", ENGINES)
def test_the_sidebar_is_a_folder_of_epics_per_workspace(
    project: Path, other: Path, engine: str
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        _ran(browser, project.resolve(), "first task")
        _ran(browser, other, "second task")

        with opened(site, engine=engine) as page:
            folders = page.locator("[data-hmz=workspace]")
            expect(folders).to_have_count(2)
            second = page.locator(f"[data-hmz=workspace][data-path='{other}']")
            expect(second.locator("[data-hmz=epic]")).to_have_text(
                [re.compile("second task")]
            )
            second.get_by_role("button", name="New chat in other").click()
            expect(page.locator(_FOLDER["/new/chat"]).locator("b")).to_have_text(
                "other"
            )

            page.keyboard.press("Control+k")
            page.locator("[data-hmz=search-filtering]").click()
            page.locator("[data-hmz=search-workspace]").select_option(str(other))
            expect(page.locator("[data-hmz=found] .result")).to_have_count(1)
            expect(page.locator("[data-hmz=found] .result")).to_contain_text(
                "second task"
            )


@pytest.mark.parametrize("engine", ENGINES)
def test_an_epic_is_started_in_a_folder_opened_by_its_path(
    project: Path, other: Path, engine: str
) -> None:
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, "/new/chat")
        page.locator(_FOLDER["/new/chat"]).click()
        page.get_by_role("menuitem", name="Open folder…").click()
        page.locator("[data-hmz=workspace-path]").fill(str(other))
        # Opening it says so until the daemon answers.
        wire.holds("workspaces.add")
        page.get_by_role("button", name="Open", exact=True).click()
        expect(page.get_by_role("button", name="Opening…")).to_be_disabled()
        wire.waits(page)
        wire.lets_through()
        expect(page.locator(_FOLDER["/new/chat"]).locator("b")).to_have_text("other")

        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_attribute("data-value", "claude-haiku-4-5")
        page.locator("[data-hmz=composer-text]").fill("over there")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        folder = page.locator(f"[data-hmz=workspace][data-path='{other}']")
        expect(folder.locator("[data-hmz=epic]")).to_contain_text("over there")
        stop(page)


@pytest.mark.parametrize("engine", ENGINES)
def test_a_folder_that_is_gone_is_never_opened_on_and_says_so_where_it_is_named(
    project: Path, other: Path, tmp_path: Path, engine: str
) -> None:
    """Sections 3.3.5.1, 3.5.7.1 and 3.8.2.3 of protocol/web.md."""
    written = tmp_path / "written"
    written.mkdir()
    gone = "The folder other is no longer on this machine. Pick another folder."
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        _ran(browser, project.resolve(), "first task")
        # The one worked in last, and one only written down: both deleted since.
        _ran(browser, other, "second task")
        with browser.session() as page:
            _writes(page, "workspaces.add", workspace=str(written.resolve()))
        shutil.rmtree(other)
        written.rmdir()

        with opened(site, engine=engine) as page:
            # Neither form opens on it, nor offers it.
            for address in ("/new/chat", "/new"):
                go(page, address)
                chip = page.locator(_FOLDER[address])
                expect(chip.locator("b")).to_have_text(project.name)
                expect(page.locator("#page")).not_to_contain_text(
                    "There is no directory"
                )
                expect(page.locator("#page [data-hmz=folder-gone]")).to_have_count(0)
                chip.click()
                expect(page.locator(".popover [data-folder]")).to_have_text(
                    [
                        re.compile(f"^{re.escape(project.name)}"),
                        re.compile("^No folder"),
                    ]
                )
                page.keyboard.press("Escape")
            # The sidebar keeps the one that holds a chat, said to be missing, and starts
            # nothing there; the one that holds nothing is not listed.
            folder = page.locator(f"[data-hmz=workspace][data-path='{other}']")
            expect(folder.locator("[data-hmz=folder-missing]")).to_have_text("missing")
            expect(folder.locator("[data-hmz=group-add]")).to_have_count(0)
            expect(
                page.locator(f"[data-hmz=workspace][data-path='{written.resolve()}']")
            ).to_have_count(0)
            folder.locator(".side-folder").click(button="right")
            menu = page.locator(".popover.context")
            expect(menu.get_by_role("menuitem", name="Search here")).to_be_visible()
            for label in ("New chat here", "New epic here", "Flows here"):
                expect(menu.get_by_role("menuitem", name=label)).to_have_count(0)
            page.keyboard.press("Escape")
            # Named by the address, it stays picked, says so, and starts nothing.
            for address in ("/new/chat", "/new"):
                go(page, f"{address}?workspace={other}")
                chip = page.locator(_FOLDER[address])
                expect(page.locator("#page [data-hmz=folder-gone]")).to_have_text(gone)
                expect(chip.locator("b")).to_have_text("other (missing)")
                expect(chip).to_have_attribute("aria-invalid", "true")
                expect(page.locator("#page")).not_to_contain_text(
                    "There is no directory"
                )
                chip.click()
                # A new chat lists the folders in its `Environment`, a new epic in `Folders`.
                rows = page.locator(".popover[role=menu]")
                expect(rows.locator("[data-missing]")).to_have_text("otherMissing")
                page.keyboard.press("Escape")
                page.locator("[data-hmz=composer-text]").fill("anything")
                page.locator("[data-hmz=composer-text]").press("Enter")
                expect(page.locator(".composer-said [role=alert]")).to_have_text(gone)
            # Put back, the form reads it again by itself.
            other.mkdir()
            expect(page.locator("#page [data-hmz=folder-gone]")).to_have_count(
                0, timeout=20000
            )
            expect(chip.locator("b")).to_have_text("other")
            # Gone again before the form reads so, the daemon's own refusal is said the same.
            go(page, f"/new/chat?workspace={other}")
            chip = page.locator(_FOLDER["/new/chat"])
            expect(chip.locator("b")).to_have_text("other")
            page.locator("[data-hmz=composer-text]").fill("anything")
            shutil.rmtree(other)
            page.locator("[data-hmz=composer-text]").press("Enter")
            expect(page.locator(".composer-said [role=alert]")).to_have_text(gone)
            # The flows name no folder, this one neither: nothing there says it is missing.
            go(page, f"/flows?workspace={other}")
            expect(
                page.locator("[data-hmz=flows] :is(.card, .empty)").first
            ).to_be_visible()
            expect(page.locator("[data-hmz=bar] .bar-sub")).to_have_count(0)
            expect(page.locator("#page [data-hmz=folder-missing]")).to_have_count(0)


@pytest.mark.parametrize("engine", ENGINES)
def test_an_epic_is_started_in_no_workspace_in_a_new_directory(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    scratch = tmp_path / "temporary"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new/chat")
        page.locator(_FOLDER["/new/chat"]).click()
        page.get_by_role("menuitem", name="No folder").click()
        expect(page.locator(_FOLDER["/new/chat"]).locator("b")).to_have_text(
            "No folder"
        )
        page.wait_for_url(re.compile(r".*scratch=1.*"))

        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_attribute("data-value", "claude-haiku-4-5")
        page.locator("[data-hmz=composer-text]").fill("nowhere in particular")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        # Under a folder of its own, made in the temporary directory.
        made = f"[data-hmz=workspace][data-path^='{scratch.resolve()}/hmz-']"
        expect(page.locator(made).locator("[data-hmz=epic]")).to_contain_text(
            "nowhere in particular"
        )
        stop(page)


#: A flow of a project's own: one agent, one turn.
_OWN = '''
from hmz.flows import (
    Agent, AgentCollection, EnvCollection, FlowContext, FlowParams, LocalEnv, flow,
)


class Agents(AgentCollection):
    """The one."""

    solo: Agent


class Envs(EnvCollection):
    """Where it works."""

    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def mine(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """A project's own flow."""
    one = agents["solo"]
    return await one.run(task, session=await one.spawn(), env=envs["workspace"])
'''


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("form", ["/new/chat", "/new"])
def test_the_folder_is_picked_in_environment_and_not_in_the_bar(
    project: Path, other: Path, form: str, engine: str
) -> None:
    """A new chat and a new epic keep the folder in Environment, and neither switches kind."""
    chat = form == "/new/chat"
    with served() as site, opened(site, engine=engine) as page:
        go(page, f"{form}?workspace={other}")
        chip = page.locator(_FOLDER[form])
        named = chip.locator("b")
        expect(named).to_have_text("other")
        expect(
            page.locator("[data-hmz=bar] [data-hmz=workspace-picker]")
        ).to_have_count(0)
        expect(page.locator("[data-hmz=new-kind]")).to_have_count(0)
        # A new chat's bar holds nothing of the form's; a new epic's, its flow alone.
        expect(page.locator("[data-hmz=bar] [data-hmz=flow-picker]")).to_have_count(
            0 if chat else 1
        )
        box = page.locator("[data-hmz=start] .composer-box").bounding_box()
        under = chip.bounding_box()
        assert box is not None
        assert under is not None
        if chat:
            # Under the box, at its left, the one chip there, set in from the box's
            # edge as its Add button is: it names the daemon, then the folder.
            expect(chip).to_have_text("Local · other")
            assert under["y"] >= box["y"] + box["height"]
            assert 0 <= under["x"] - box["x"] <= 12
            expect(
                page.locator("[data-hmz=composer-under] [data-hmz=workspace-picker]")
            ).to_have_count(0)
        else:
            # In the middle of the page, over the box, under where it runs: nothing of
            # where it runs is under the box.
            runs = page.locator("[data-hmz=setup-daemon] [data-hmz=environment]")
            before = runs.bounding_box()
            assert before is not None
            assert under["y"] + under["height"] <= box["y"]
            assert under["y"] >= before["y"] + before["height"]
            expect(
                page.locator("[data-hmz=composer-under] :is(button, input)")
            ).to_have_count(0)

        chip.click()
        menu = page.get_by_role("menu", name="Environment" if chat else "Folders")
        if chat:
            # A chat app's folder menu: each folder one row by its name, its path said
            # where it is pointed at, under the one heading that parts them from the daemons.
            expect(menu.locator(".popover-head")).to_have_text(["Runs on", "Folder"])
            expect(menu.locator("[data-folder] .choice-about")).to_have_count(0)
            expect(menu.get_by_role("menuitem", name="project")).to_have_attribute(
                "data-tip", str(project)
            )
        else:
            # Each folder a row that says its path.
            expect(
                menu.get_by_role("menuitem", name="project").locator(".choice-about")
            ).to_have_text(str(project))
        expect(menu.get_by_role("menuitem", name="Open folder…")).to_be_visible()
        menu.get_by_role("menuitem", name="No folder").click()
        expect(named).to_have_text("No folder")
        # Named, as every chip is, by what it picks and what is picked.
        expect(chip).to_have_attribute(
            "aria-label",
            "Environment: Local, No folder" if chat else "Folder: No folder",
        )
        page.wait_for_url(re.compile(r".*scratch=1.*"))
        # With no folder there are no files to name: Add says so, and offers none.
        page.locator("[data-hmz=composer-add]").click()
        files = page.get_by_role("menu", name="Add").locator("[data-add=files]")
        expect(files).to_be_disabled()
        expect(files).to_contain_text("Pick a folder first")
        # One popup at a time: the folder menu opened by the keyboard, with no press
        # outside the Add menu, shuts it.
        chip.focus()
        page.keyboard.press("Enter")
        expect(menu).to_be_visible()
        expect(page.get_by_role("menu", name="Add")).to_have_count(0)
        expect(page.locator(".popover:visible")).to_have_count(1)
        page.keyboard.press("Escape")
        expect(page.locator(".popover:visible")).to_have_count(0)
        expect(chip).to_be_focused()


def test_a_projects_own_flows_are_offered_in_that_project_alone(
    project: Path, other: Path
) -> None:
    write_flow(other / ".hmz" / "flows", "mine", _OWN)
    with served() as site:
        browser = Browser(site)
        browser.signs_in()

        with browser.session() as page:
            there = page.call("flows.list", workspace=str(other))["flows"]
            assert ("local", "@local/mine") in [
                (one["whose"], one["name"]) for one in there
            ]
            here = page.call("flows.list", workspace=str(project))["flows"]
            assert "@local/mine" not in [one["name"] for one in here]
            declared = page.call("flows.get", name="@local/mine", workspace=str(other))
            assert [one["name"] for one in declared["agents"]] == ["solo"]
            with pytest.raises(RpcError) as missing:
                page.call("flows.get", name="@local/mine", workspace=str(project))
            assert missing.value.code == 404


@pytest.mark.parametrize("engine", ENGINES)
def test_a_long_name_stays_inside_what_shows_it(
    project: Path, tmp_path: Path, engine: str
) -> None:
    """A flow's name and a workspace's have nowhere to break, and still fit a phone."""
    long = "a_flow_whose_name_runs_on_and_on_with_nowhere_at_all_to_break"
    at = tmp_path / "a-workspace-whose-name-runs-on-and-on-with-nowhere-to-break"
    write_flow(at / ".hmz" / "flows", long, _OWN)
    # The same under the user's own flows, which the flows list whatever the workspace.
    write_flow(tmp_path / "home" / ".hmz" / "flows", long, _OWN)
    with served() as site, opened(site, engine=engine, width=390, height=844) as page:
        go(page, f"/flows?flow=@user/{long}")
        expect(page.locator(".flow-detail h2")).to_have_text(f"@user/{long}")
        out = page.evaluate(
            """() => [...document.querySelectorAll(
                '[data-hmz=bar], .card, .flow-detail'
            )].filter((one) => one.scrollWidth > one.clientWidth).map((one) => one.className)"""
        )
        assert not out, f"run out of: {out}"
        assert page.evaluate("document.documentElement.scrollWidth") <= 390
        expect(page.locator("[data-hmz=workspace-picker]")).to_have_count(0)
        # What is cut short says itself in full on hover.
        go(page, f"/new?workspace={at.resolve()}&flow=@local/{long}")
        page.locator("[data-hmz=flow-picker] b").hover()
        expect(page.locator(".tip")).to_have_text(f"@local/{long}")

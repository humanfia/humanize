"""`hmz web` serves the machine, as the daemon does: every workspace's epics, started anywhere.

The interface is started in one project and asked about another, as a browser on it would: the
epics of both are listed, each under its own workspace, an epic is started in either, and a
workspace is opened by its path and forgotten again.
"""

from __future__ import annotations

import re
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
    """Starts a chat in a workspace and stops it once it has answered, as a page would."""
    with browser.session() as page:
        chatted(page, workspace, task)


def test_every_workspaces_epics_are_listed_and_found_by_workspace(
    project: Path, other: Path
) -> None:
    here = project.resolve()
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        _ran(browser, here, "in the first")
        _ran(browser, other, "in the second")

        with browser.session() as page:
            listed = page.call("runs.list")["runs"]
            assert {(one["task"], one["workspace"]) for one in listed} == {
                ("in the first", str(here)),
                ("in the second", str(other)),
            }
            only = page.call("runs.list", workspace=str(other))["runs"]
            assert [one["task"] for one in only] == ["in the second"]
            (one,) = only
            assert page.call("runs.get", name=one["name"])["workspace"] == str(other)
            places = page.call("workspaces.list", here=str(here))
        assert places["here"] == str(here)
        assert [one["path"] for one in places["workspaces"]][:1] == [str(here)]
        assert {one["path"]: one["epics"] for one in places["workspaces"]} == {
            str(here): 1,
            str(other): 1,
        }


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
            expect(page.locator("[data-hmz=workspace-picker] b")).to_have_text("other")

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
        page.locator("[data-hmz=workspace-picker]").click()
        page.get_by_role("menuitem", name="Open folder…").click()
        page.locator("[data-hmz=workspace-path]").fill(str(other))
        # Opening it says so until the daemon answers.
        wire.holds("workspaces.add")
        page.get_by_role("button", name="Open", exact=True).click()
        expect(page.get_by_role("button", name="Opening…")).to_be_disabled()
        wire.waits(page)
        wire.lets_through()
        expect(page.locator("[data-hmz=workspace-picker] b")).to_have_text("other")

        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_attribute("data-value", "claude-haiku-4-5")
        page.locator("[data-hmz=composer-text]").fill("over there")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(re.compile(r".*#/epics/[^/]+/sessions/[^/]+$"))
        folder = page.locator(f"[data-hmz=workspace][data-path='{other}']")
        expect(folder.locator("[data-hmz=epic]")).to_contain_text("over there")
        stop(page)


@pytest.mark.parametrize("engine", ENGINES)
def test_an_epic_is_started_in_no_workspace_in_a_new_directory(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    scratch = tmp_path / "temporary"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new/chat")
        page.locator("[data-hmz=workspace-picker]").click()
        page.get_by_role("menuitem", name="No workspace").click()
        expect(page.locator("[data-hmz=workspace-picker] b")).to_have_text(
            "No workspace"
        )
        page.wait_for_url(re.compile(r".*scratch=1.*"))

        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_attribute("data-value", "claude-haiku-4-5")
        page.locator("[data-hmz=composer-text]").fill("nowhere in particular")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(re.compile(r".*#/epics/[^/]+/sessions/[^/]+$"))
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
def test_the_folder_is_picked_under_the_box_and_not_in_the_bar(
    project: Path, other: Path, form: str, engine: str
) -> None:
    """A new chat and a new epic keep the folder under the box, and neither switches kind."""
    with served() as site, opened(site, engine=engine) as page:
        go(page, f"{form}?workspace={other}")
        chip = page.locator("[data-hmz=composer-under] [data-hmz=workspace-picker]")
        expect(chip.locator("b")).to_have_text("other")
        expect(
            page.locator("[data-hmz=bar] [data-hmz=workspace-picker]")
        ).to_have_count(0)
        expect(page.locator("[data-hmz=new-kind]")).to_have_count(0)
        # A new chat's bar holds nothing of the form's; a new epic's, its flow alone.
        flows = 0 if form == "/new/chat" else 1
        expect(page.locator("[data-hmz=bar] [data-hmz=flow-picker]")).to_have_count(
            flows
        )
        # Under the box, at its left, right after where it runs.
        box = page.locator("[data-hmz=start] .composer-box").bounding_box()
        under = chip.bounding_box()
        runs = page.locator("[data-hmz=composer-under] [data-hmz=environment]")
        before = runs.bounding_box()
        assert box is not None
        assert under is not None
        assert before is not None
        assert under["y"] >= box["y"] + box["height"]
        # Set in from the box's edge, as its Add button is.
        assert 0 <= before["x"] - box["x"] <= 12
        assert 0 <= under["x"] - (before["x"] + before["width"]) < 8

        chip.click()
        menu = page.get_by_role("menu", name="Folders")
        # A chat app's folder menu: each folder one row by its name, under no heading,
        # its path said where it is pointed at.
        expect(menu.locator(".popover-head")).to_have_count(0)
        expect(menu.locator(".choice-about")).to_have_count(0)
        expect(menu.get_by_role("menuitem", name="project")).to_have_attribute(
            "data-tip", str(project)
        )
        expect(menu.get_by_role("menuitem", name="Open folder…")).to_be_visible()
        menu.get_by_role("menuitem", name="No workspace").click()
        expect(chip.locator("b")).to_have_text("No workspace")
        page.wait_for_url(re.compile(r".*scratch=1.*"))


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
    with served() as site, opened(site, engine=engine, width=390, height=844) as page:
        go(page, f"/flows?workspace={at.resolve()}&flow=@local/{long}")
        expect(page.locator(".flow-detail h2")).to_have_text(f"@local/{long}")
        out = page.evaluate(
            """() => [...document.querySelectorAll(
                '[data-hmz=bar], .card, .flow-detail'
            )].filter((one) => one.scrollWidth > one.clientWidth).map((one) => one.className)"""
        )
        assert not out, f"run out of: {out}"
        assert page.evaluate("document.documentElement.scrollWidth") <= 390
        # What is cut short says itself in full on hover.
        page.locator("[data-hmz=workspace-picker]").hover()
        expect(page.locator(".tip")).to_have_text(str(at.resolve()))
        go(page, f"/new?workspace={at.resolve()}&flow=@local/{long}")
        page.locator("[data-hmz=flow-picker] b").hover()
        expect(page.locator(".tip")).to_have_text(f"@local/{long}")

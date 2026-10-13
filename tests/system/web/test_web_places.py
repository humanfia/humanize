"""`hmz web` serves the machine, as the daemon does: every workspace's epics, started anywhere.

The interface is started in one project and asked about another, as a browser on it would: the
epics of both are listed, each under its own workspace, an epic is started in either, and a
workspace is opened by its path and forgotten again.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import AGENT, install, write_flow
from tests.integration.doubles_web import Browser, served, until
from tests.system.web.doubles_browser import ENGINES, go, opened, stop

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, and the project the interface is started in."""
    return install(tmp_path, monkeypatch)


@pytest.fixture
def other(tmp_path: Path) -> Path:
    """Another project on the same machine."""
    at = tmp_path / "other"
    at.mkdir()
    return at.resolve()


def _ran(browser: Browser, workspace: Path, task: str) -> None:
    """Starts chat in a workspace and stops it once it has answered, as a page would."""
    chat = {"flow": "chat", "task": task, "agents": {"assistant": AGENT}}
    with browser.follows(workspace=str(workspace)) as heard:
        until(heard, lambda event, data: event == "hello", "hello")
        said = browser.post("/api/held/start", chat | {"workspace": str(workspace)})
        assert said.status == 200, said.body
        until(heard, _asked, "chat asking")
        assert (
            browser.post("/api/held/stop", {"workspace": str(workspace)}).status == 200
        )
        until(heard, _ended, "the epic ending")


def _asked(event: str, data: Any) -> bool:
    return event == "record" and data.get("type") == "asked"


def _ended(event: str, data: Any) -> bool:
    return event == "record" and data.get("type") == "ended"


def test_every_workspaces_epics_are_listed_and_found_by_workspace(
    project: Path, other: Path
) -> None:
    here = project.resolve()
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        _ran(browser, here, "in the first")
        _ran(browser, other, "in the second")

        listed = browser.get("/api/runs").json()["runs"]
        assert {(one["task"], one["workspace"]) for one in listed} == {
            ("in the first", str(here)),
            ("in the second", str(other)),
        }
        only = browser.get(f"/api/runs?workspace={other}").json()["runs"]
        assert [one["task"] for one in only] == ["in the second"]
        (one,) = only
        assert browser.get(f"/api/runs/{one['name']}").json()["workspace"] == str(other)
        places = browser.get("/api/workspaces").json()
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

        kept = browser.post("/api/workspaces", {"workspace": str(other)}).json()
        assert kept["kept"] == str(other)
        assert str(other) in [one["path"] for one in kept["workspaces"]]
        assert browser.post("/api/workspaces", {"workspace": "relative"}).status == 400
        missing = browser.post("/api/workspaces", {"workspace": str(tmp_path / "gone")})
        assert missing.status == 404

        browser.post("/api/workspaces/forget", {"workspace": str(other)})
        listed = browser.get("/api/workspaces").json()["workspaces"]
        assert str(other) not in [one["path"] for one in listed]


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
            second.get_by_role("button", name="New epic in other").click()
            expect(page.locator("[data-hmz=workspace-picker] b")).to_have_text("other")

            page.keyboard.press("Control+k")
            page.locator("[data-hmz=search-workspace]").select_option(str(other))
            expect(page.locator("[data-hmz=found] .result")).to_have_count(1)
            expect(page.locator("[data-hmz=found] .result")).to_contain_text(
                "second task"
            )


@pytest.mark.parametrize("engine", ENGINES)
def test_an_epic_is_started_in_a_folder_opened_by_its_path(
    project: Path, other: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new?flow=chat")
        page.locator("[data-hmz=workspace-picker]").click()
        page.get_by_role("menuitem", name="Open folder…").click()
        page.locator("[data-hmz=workspace-path]").fill(str(other))
        page.get_by_role("button", name="Open", exact=True).click()
        expect(page.locator("[data-hmz=workspace-picker] b")).to_have_text("other")

        page.get_by_role("button", name="Options").click()
        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_value("claude-haiku-4-5")
        page.locator("[data-hmz=composer-text]").fill("over there")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(re.compile(r".*#/epics/[^/]+$"))
        folder = page.locator(f"[data-hmz=workspace][data-path='{other}']")
        expect(folder.locator("[data-hmz=epic]")).to_contain_text("over there")
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


def test_a_projects_own_flows_are_offered_in_that_project_alone(
    project: Path, other: Path
) -> None:
    write_flow(other / ".hmz" / "flows", "mine", _OWN)
    with served() as site:
        browser = Browser(site)
        browser.signs_in()

        there = browser.get(f"/api/flows?workspace={other}").json()["flows"]
        assert ("local", "@local/mine") in [
            (one["whose"], one["name"]) for one in there
        ]
        here = browser.get("/api/flows").json()["flows"]
        assert "@local/mine" not in [one["name"] for one in here]
        declared = browser.get(f"/api/flow?name=@local/mine&workspace={other}").json()
        assert [one["name"] for one in declared["agents"]] == ["solo"]
        assert browser.get("/api/flow?name=@local/mine").status == 404


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

"""`hmz web` and the flowverses: adding one, installing out of it, updating and taking it away.

A flowverse here is a real one, on this machine: a repository holding a flow, and an index --
another repository -- listing two releases of it, each a commit of the first. The page adds the
index, installs the older release, is told of the newer one, updates to it, uninstalls it and
removes the index, as somebody would from the Flows page.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
import yaml
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import Browser, served
from tests.system.web.doubles_browser import ENGINES, opened

if TYPE_CHECKING:
    from pathlib import Path

#: The flow the index lists: one agent, one turn.
_FLOW = '''
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
async def solo(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """One agent, one turn."""
    one = agents["solo"]
    return await one.run(task, session=await one.spawn(), env=envs["workspace"])
'''


def _git(at: Path, *argv: str) -> str:
    said = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *argv],
        cwd=at,
        capture_output=True,
        text=True,
        check=True,
    )
    return said.stdout.strip()


@pytest.fixture
def index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """An index on this machine listing `solo` 1.0.0 and 1.1.0, in a project of its own."""
    install(tmp_path, monkeypatch)
    flow = tmp_path / "solo"
    flow.mkdir()
    (flow / "__init__.py").write_text(_FLOW)
    _git(flow, "init", "-q")
    _git(flow, "add", ".")
    _git(flow, "commit", "-qm", "solo")
    commit = _git(flow, "rev-parse", "HEAD")
    listing = tmp_path / "theirs"
    for version in ("1.0.0", "1.1.0"):
        at = listing / "flows" / "solo" / version
        at.mkdir(parents=True)
        (at / "flow.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "solo",
                    "version": version,
                    "description": f"one agent, one turn, {version}",
                    "repo": flow.as_uri(),
                    "commit": commit,
                }
            )
        )
    _git(listing, "init", "-q")
    _git(listing, "add", ".")
    _git(listing, "commit", "-qm", "index")
    return listing


def test_a_flow_is_installed_updated_and_uninstalled_out_of_a_flowverse(
    index: Path,
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()

        added = browser.post("/api/flowverses", {"url": str(index), "name": "theirs"})
        assert added.status == 200, added.body
        named = [one["name"] for one in added.json()["verses"]]
        assert "theirs" in named
        assert "local" not in named
        assert "user" not in named
        listed = browser.get("/api/flowverses/theirs").json()
        (solo,) = listed["flows"]
        assert (solo["flow"], solo["installed"]) == ("@theirs/solo", "")
        assert [one["version"] for one in solo["releases"]] == ["1.1.0", "1.0.0"]

        done = browser.post(
            "/api/flowverses/install", {"flow": "@theirs/solo", "version": "1.0.0"}
        )
        assert done.status == 200, done.body
        assert done.json()["updates"] == [
            {"flow": "@theirs/solo", "from": "1.0.0", "to": "1.1.0"}
        ]
        offered = browser.get("/api/flows").json()["flows"]
        assert "@theirs/solo" in [one["name"] for one in offered]

        browser.post(
            "/api/flowverses/install", {"flow": "@theirs/solo", "version": "1.1.0"}
        )
        assert browser.get("/api/flowverses").json()["updates"] == []
        assert (
            browser.post("/api/flowverses/uninstall", {"flow": "@theirs/solo"}).status
            == 200
        )
        gone = browser.post("/api/flowverses/remove", {"name": "theirs"}).json()
        assert "theirs" not in [one["name"] for one in gone["verses"]]
        assert browser.get("/api/flowverses/theirs").status == 404


@pytest.mark.parametrize("engine", ENGINES)
def test_the_flows_page_installs_out_of_a_flowverse_and_says_what_is_newer(
    index: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        page.get_by_role("link", name="Flows").click()
        page.get_by_role("tab", name="Flowverses").click()
        expect(page.locator(".card[data-verse=official]")).to_be_visible()
        expect(page.locator(".card[data-verse=local]")).to_have_count(0)
        expect(page.locator(".card[data-verse=user]")).to_have_count(0)
        expect(page.locator(".flow-detail")).to_be_hidden()
        page.locator(".card[data-verse=official]").click()
        expect(page.locator(".flow-detail h2")).to_have_text("official")
        page.locator(".card[data-verse=official]").click()
        expect(page.locator(".flow-detail")).to_be_hidden()
        page.locator("[data-hmz=add-verse]").click()
        form = page.locator("[data-hmz=add-verse-form]")
        expect(form).to_be_visible()
        form.get_by_role("textbox", name="URL").fill(str(index))
        form.get_by_role("textbox", name="Name").fill("theirs")
        form.get_by_role("button", name="Add").click()

        solo = page.locator("[data-hmz=release][data-flow='@theirs/solo']")
        expect(solo).to_be_visible()
        solo.get_by_role("combobox").select_option("1.0.0")
        solo.get_by_role("button", name="Install").click()
        expect(solo).to_contain_text("1.0.0 installed")
        expect(page.locator("[data-hmz=update-banner]")).to_contain_text(
            "@theirs/solo 1.0.0 → 1.1.0"
        )
        expect(page.locator("[data-hmz=sidebar] [data-hmz=updates]")).to_have_text("1")

        page.get_by_role("tab", name="Installed").click()
        page.locator(".card[data-flow='@theirs/solo']").click()
        page.get_by_role("button", name="Update to 1.1.0").click()
        expect(page.locator("[data-hmz=update-banner]")).to_have_count(0)

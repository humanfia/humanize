"""`hmz web` and the flowverses: adding one, installing out of it, updating and taking it away.

A flowverse here is a real one, on this machine: a repository holding a flow, and an index --
another repository -- listing two releases of it, each a commit of the first. The page adds the
index, installs the older release, is told of the newer one, updates to it, uninstalls it and
removes the index, as somebody would from the Flows page.
"""

from __future__ import annotations

import subprocess
import uuid
from typing import TYPE_CHECKING, Any

import pytest
import yaml
from playwright.sync_api import expect

from hmz.rpc import RpcError
from tests.integration.doubles_core import install
from tests.integration.doubles_web import Browser, Session, served
from tests.system.web.doubles_browser import ENGINES, Wire, opened

if TYPE_CHECKING:
    from pathlib import Path

#: Local is a daemon of this process, which the page reaches over `/rpc` as any other.
pytestmark = pytest.mark.usefixtures("daemon")

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

#: What is drawn with a shadow: nothing floats by one, a hairline edge parts it from the page.
_SHADOWED = """() => [...document.querySelectorAll('*')]
  .filter((one) => getComputedStyle(one).boxShadow !== 'none')
  .map((one) => `${one.tagName.toLowerCase()}.${one.className}`)"""


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
    # The home it gives the CLI is this machine's home, whose flowverses these are.
    (tmp_path / "home").mkdir(exist_ok=True)
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


def _writes(page: Session, method: str, **params: Any) -> Any:
    """Calls a write, as the page does: with an `idem` of its own."""
    return page.call(method, **params, idem=uuid.uuid4().hex)


def test_a_flow_is_installed_updated_and_uninstalled_out_of_a_flowverse(
    index: Path,
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        with browser.session() as page:
            added = _writes(page, "flowverses.add", url=str(index), name="theirs")
            named = [one["name"] for one in added["verses"]]
            assert "theirs" in named
            assert "local" not in named
            assert "user" not in named
            listed = page.call("flowverses.get", name="theirs")
            (solo,) = listed["flows"]
            assert (solo["flow"], solo["installed"]) == ("@theirs/solo", "")
            assert [one["version"] for one in solo["releases"]] == ["1.1.0", "1.0.0"]

            done = _writes(
                page, "flowverses.install", flow="@theirs/solo", version="1.0.0"
            )
            assert done["updates"] == [
                {"flow": "@theirs/solo", "from": "1.0.0", "to": "1.1.0"}
            ]
            offered = page.call("flows.list", workspace=str(site.here))["flows"]
            assert "@theirs/solo" in [one["name"] for one in offered]

            _writes(page, "flowverses.install", flow="@theirs/solo", version="1.1.0")
            assert page.call("flowverses.list")["updates"] == []
            _writes(page, "flowverses.uninstall", flow="@theirs/solo")
            gone = _writes(page, "flowverses.remove", name="theirs")
            assert "theirs" not in [one["name"] for one in gone["verses"]]
            with pytest.raises(RpcError) as missing:
                page.call("flowverses.get", name="theirs")
            assert missing.value.code == 404


@pytest.mark.parametrize("engine", ENGINES)
def test_the_flows_page_installs_out_of_a_flowverse_and_says_what_is_newer(
    index: Path, engine: str
) -> None:
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
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

        # One popup at a time: a second card's menu shuts the first's, the bell's list shuts
        # that, and Escape leaves none; and none of them is parted from the page by a shadow.
        floating = page.locator(".popover:visible")
        page.locator(".card[data-verse=official]").click(button="right")
        expect(floating).to_have_count(1)
        expect(floating.get_by_role("menuitem", name="Fetch")).to_be_visible()
        page.locator(".card[data-verse=theirs]").click(button="right", force=True)
        expect(floating).to_have_count(1)
        expect(floating).to_contain_text(str(index))
        assert page.evaluate(_SHADOWED) == []
        page.locator("[data-hmz=notifications]").click(force=True)
        expect(floating).to_have_count(1)
        expect(floating.get_by_role("menuitem", name="Fetch")).to_have_count(0)
        page.keyboard.press("Escape")
        expect(floating).to_have_count(0)
        expect(page.locator("[aria-expanded=true][aria-haspopup]")).to_have_count(0)

        # Fetched out of a card's menu, it says so until the daemon answers.
        wire.holds("flowverses.fetch")
        page.locator(".card[data-verse=theirs]").click(button="right")
        page.get_by_role("menuitem", name="Fetch").click()
        expect(page.locator("[data-hmz=busy]")).to_have_text("Fetching theirs…")
        wire.waits(page)
        wire.lets_through()
        expect(page.locator("[data-hmz=busy]")).to_have_count(0)
        expect(page.locator(".flows-said .note")).to_be_visible()

        page.get_by_role("tab", name="Installed").click()
        wire.holds("flowverses.install")
        page.locator(".card[data-flow='@theirs/solo']").click(button="right")
        page.get_by_role("menuitem", name="Update to 1.1.0").click()
        expect(page.locator("[data-hmz=busy]")).to_have_text("Updating @theirs/solo…")
        wire.waits(page)
        wire.lets_through()
        expect(page.locator("[data-hmz=busy]")).to_have_count(0)
        expect(page.locator("[data-hmz=update-banner]")).to_have_count(0)

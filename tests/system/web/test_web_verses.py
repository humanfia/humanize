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
from tests.system.web.doubles_browser import ENGINES, Wire, go, opened

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
        # The flowverses are tabs saying a name alone, and the first is open with no press:
        # no mark made of a letter, no word over its name, its address said once, under it.
        official = page.locator("[role=tab][data-verse=official]")
        expect(official).to_have_text("Official")
        expect(official).to_have_attribute("aria-selected", "true")
        expect(page.locator("[data-verse=local]")).to_have_count(0)
        expect(page.locator("[data-verse=user]")).to_have_count(0)
        shown = page.locator(".flow-detail")
        expect(shown.locator("h2")).to_have_text("Official")
        expect(page.locator("[data-hmz=flows] .card-mark")).to_have_count(0)
        expect(shown.locator("header .kicker")).to_have_count(0)
        expect(page.locator("[data-hmz=flows]")).not_to_contain_text("Built in")
        expect(page.locator("[data-hmz=flows]")).not_to_contain_text("github.com")
        expect(
            shown.get_by_text("https://github.com/humanfia/flowverse")
        ).to_have_count(1)
        assert official.evaluate("(el) => el.getBoundingClientRect().height") == 29
        # Fetching it is an arrow with no frame, right after its name.
        fetch = shown.get_by_role("button", name="Fetch")
        expect(fetch).to_have_attribute("title", "Fetch")
        assert fetch.evaluate("(el) => getComputedStyle(el).borderTopWidth") == "0px"
        gap = page.evaluate(
            """() => document.querySelector('[data-hmz=fetch-verse]').getBoundingClientRect().left
                - document.querySelector('.flow-detail h2').getBoundingClientRect().right"""
        )
        assert 0 <= gap <= 8, gap
        # Nothing picks a workspace here.
        expect(
            page.locator("[data-hmz=bar] [data-hmz=workspace-picker]")
        ).to_have_count(0)
        add = page.get_by_role("button", name="Add flowverse")
        add.click()
        form = page.locator("[data-hmz=add-verse-form]")
        expect(form).to_be_visible()
        expect(official).to_have_attribute("aria-selected", "false")
        # Chosen again, its form gives way to the first flowverse.
        add.click()
        expect(shown.locator("h2")).to_have_text("Official")
        add.click()
        form.get_by_role("textbox", name="URL").fill(str(index))
        form.get_by_role("textbox", name="Name").fill("theirs")
        form.get_by_role("button", name="Add").click()

        solo = page.locator("[data-hmz=release][data-flow='@theirs/solo']")
        expect(solo).to_be_visible()
        solo.get_by_role("combobox").select_option("1.0.0")
        # What installs a release ends its line, installed or not.
        ends = """(el) => {
            const row = el.querySelector('.row')
            return el.getBoundingClientRect().right - el.clientLeft
                - row.lastElementChild.getBoundingClientRect().right
        }"""
        assert abs(solo.evaluate(ends)) < 1
        solo.get_by_role("button", name="Install").click()
        expect(solo).to_contain_text("1.0.0 installed")
        expect(solo.get_by_role("button", name="Uninstall")).to_be_visible()
        assert abs(solo.evaluate(ends)) < 1
        expect(page.locator("[data-hmz=update-banner]")).to_contain_text(
            "@theirs/solo 1.0.0 → 1.1.0"
        )
        expect(page.locator("[data-hmz=sidebar] [data-hmz=updates]")).to_have_text("1")

        # One popup at a time: a second tab's menu shuts the first's, the daemon's menu shuts
        # that, and Escape leaves none; and none of them is parted from the page by a shadow.
        floating = page.locator(".popover:visible")
        # (The later tab's first: its menu opens rightwards, clear of the tab before it.)
        page.locator("[role=tab][data-verse=theirs]").click(button="right")
        expect(floating).to_have_count(1)
        expect(floating).to_contain_text(str(index))
        page.locator("[role=tab][data-verse=official]").click(
            button="right", force=True
        )
        expect(floating).to_have_count(1)
        expect(floating.get_by_role("menuitem", name="Fetch")).to_be_visible()
        expect(floating).not_to_contain_text(str(index))
        assert page.evaluate(_SHADOWED) == []
        page.locator("[data-hmz=daemon-bar]").click(force=True)
        expect(floating).to_have_count(1)
        expect(floating.get_by_role("menuitem", name="Fetch")).to_have_count(0)
        page.keyboard.press("Escape")
        expect(floating).to_have_count(0)
        expect(page.locator("[aria-expanded=true][aria-haspopup]")).to_have_count(0)

        # Fetched out of a tab's menu, it says so until the daemon answers.
        wire.holds("flowverses.fetch")
        page.locator("[role=tab][data-verse=theirs]").click(button="right")
        page.get_by_role("menuitem", name="Fetch").click()
        expect(page.locator("[data-hmz=busy]")).to_have_text("Fetching theirs…")
        wire.waits(page)
        wire.lets_through()
        expect(page.locator("[data-hmz=busy]")).to_have_count(0)
        expect(page.locator(".flows-said .note")).to_have_text("Fetched theirs.")

        # And by the arrow after its name, which is busy until then: it says so where nothing
        # moves for it, and, pressed by the keys, keeps the focus once it is drawn again.
        wire.holds("flowverses.fetch")
        arrow = page.locator("[data-hmz=fetch-verse]")
        top = arrow.evaluate("(el) => el.getBoundingClientRect().top")
        arrow.focus()
        page.keyboard.press("Enter")
        expect(arrow).to_have_attribute("aria-busy", "true")
        expect(page.locator("[data-hmz=fetching-verse]")).to_have_text(
            "Fetching theirs…"
        )
        expect(page.locator("[data-hmz=busy]")).to_have_count(0)
        assert arrow.evaluate("(el) => el.getBoundingClientRect().top") == top
        wire.waits(page)
        wire.lets_through()
        expect(arrow).not_to_have_attribute("aria-busy", "true")
        expect(arrow).to_be_focused()

        # The tabs are one stop of the Tab key: the arrows move among them, Enter picks, and
        # what a tab opens is its panel. Its name stands where the first one's stood.
        theirs = page.locator("[role=tab][data-verse=theirs]")
        official = page.locator("[role=tab][data-verse=official]")
        expect(theirs).to_have_attribute("tabindex", "0")
        expect(official).to_have_attribute("tabindex", "-1")
        panel = page.get_by_role("tabpanel", name="theirs")
        expect(panel.locator("h2")).to_have_text("theirs")
        name_at = panel.locator("h2").evaluate("(el) => el.getBoundingClientRect().top")
        theirs.focus()
        page.keyboard.press("ArrowLeft")
        expect(official).to_be_focused()
        page.keyboard.press("Enter")
        panel = page.get_by_role("tabpanel", name="Official")
        expect(panel.locator("h2")).to_have_text("Official")
        assert (
            panel.locator("h2").evaluate("(el) => el.getBoundingClientRect().top")
            == name_at
        )

        # An address naming a flowverse that is not listed stands on the first.
        go(page, "/flows?tab=verses&verse=nosuch")
        expect(official).to_have_attribute("aria-selected", "true")
        expect(page.locator(".flow-detail h2")).to_have_text("Official")

        page.get_by_role("tab", name="Installed").click()
        wire.holds("flowverses.install")
        page.locator(".card[data-flow='@theirs/solo']").click(button="right")
        page.get_by_role("menuitem", name="Update to 1.1.0").click()
        expect(page.locator("[data-hmz=busy]")).to_have_text("Updating @theirs/solo…")
        wire.waits(page)
        wire.lets_through()
        expect(page.locator("[data-hmz=busy]")).to_have_count(0)
        expect(page.locator("[data-hmz=update-banner]")).to_have_count(0)

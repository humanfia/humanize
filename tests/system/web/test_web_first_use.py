"""`hmz web` on a home nothing was installed into yet, and on a daemon it cannot reach.

A new epic where no flow is on offer says how a first one starts, in three steps, and takes the
first itself: the example flow installed out of the official flowverse. Here the official index
is one on this machine, cloned where Humanize keeps it, listing a stand-in `ralph_loop`; nothing
is fetched. A daemon the page cannot reach is said in the sidebar as it is said everywhere else,
with what to do next and a button that does it.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, Wire, go, opened

pytestmark = pytest.mark.parametrize("engine", ENGINES)

#: The example, as the official index lists it: one agent, one turn.
_FLOW = '''
from hmz.flows import (
    Agent, AgentCollection, EnvCollection, FlowContext, FlowParams, LocalEnv, flow,
)


class Agents(AgentCollection):
    """The one."""

    agent: Agent


class Envs(EnvCollection):
    """Where it works."""

    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def ralph_loop(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """The task, once."""
    one = agents["agent"]
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


@pytest.fixture(autouse=True)
def _loops_installed() -> None:
    """Overrides `tests/system`'s: a home nothing was installed into, as a new machine's is."""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, asked what it runs, and a project to serve."""
    return install(tmp_path, monkeypatch)


@pytest.fixture
def official(project: Path, tmp_path: Path) -> Path:
    """The official index, fetched already, listing `ralph_loop` 0.1.0 out of this machine."""
    flow = tmp_path / "ralph"
    flow.mkdir()
    (flow / "__init__.py").write_text(_FLOW)
    _git(flow, "init", "-q")
    _git(flow, "add", ".")
    _git(flow, "commit", "-qm", "ralph_loop")
    index = Path(os.environ["HUMANIZE_HOME"]) / "flowverses" / "official" / "index"
    listed = index / "flows" / "ralph_loop" / "0.1.0"
    listed.mkdir(parents=True)
    (listed / "flow.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "ralph_loop",
                "version": "0.1.0",
                "description": "The task again and again.",
                "repo": flow.as_uri(),
                "commit": _git(flow, "rev-parse", "HEAD"),
            }
        )
    )
    _git(index, "init", "-q")
    _git(index, "add", ".")
    _git(index, "commit", "-qm", "index")
    return project


@pytest.mark.usefixtures("official")
def test_a_first_epic_is_started_in_the_three_steps_the_guide_says(engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/new")
        guide = page.locator("[data-hmz=first-use]")
        expect(guide.locator("[data-hmz=step] b")).to_have_text(
            ["Install", "Set a budget", "Describe the task"]
        )

        # 1. The example, installed out of the official flowverse, opens with its Options.
        guide.get_by_role("button", name="Install example").click()
        expect(guide.locator("[data-hmz=installed]")).to_have_text("Installed")
        expect(page.locator("[data-hmz=flow-picker] b")).to_have_text("ralph_loop")
        options = page.locator("[data-hmz=options]")
        expect(options).to_be_visible()
        # Its role on the stand-in, wherever another CLI this machine has is listed first.
        role = page.locator("[data-role=agent]")
        role.locator("[data-hmz=pick-cli]").select_option("claude")
        expect(role.locator("[data-hmz=pick-model] option").first).to_have_text(
            "claude-haiku-4-5"
        )
        # The steps after it stay said, until the epic starts.
        expect(guide.locator("[data-hmz=step]")).to_have_count(3)

        # 2. A budget.
        options.get_by_label("Longest it may take, in minutes").fill("5")

        # 3. The task, and Enter.
        text = page.locator("[data-hmz=composer-text]")
        text.fill("Fix the bug in calc.py.")
        text.press("Enter")
        page.wait_for_url(re.compile(r".*#/live\?workspace=.+"))
        epic = page.locator("[data-hmz=epics] [data-hmz=epic][data-kind=flow]")
        expect(epic).to_contain_text("Fix the bug in calc.py.")
        expect(epic.locator("[data-hmz=epic-flow]")).to_have_text("ralph_loop")


def _listed(fetched: bool) -> dict[str, Any]:
    return {
        "result": {
            "verses": [
                {
                    "name": "official",
                    "url": "https://github.com/humanfia/flowverse",
                    "fetched": fetched,
                    "fixed": True,
                    "edited": False,
                    "installed": 0,
                }
            ],
            "installed": [],
            "updates": [],
        }
    }


@pytest.mark.usefixtures("project")
def test_an_index_never_fetched_is_fetched_first_and_a_refusal_said_by_the_button(
    engine: str,
) -> None:
    wire = Wire(
        faked={
            "flowverses.list": lambda _: _listed(fetched=False),
            "flowverses.fetch": lambda _: None,
            "flowverses.install": lambda _: {
                "error": {
                    "code": 400,
                    "message": "official lists no ralph_loop.",
                }
            },
        }
    )
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, "/new")
        guide = page.locator("[data-hmz=first-use]")
        install = guide.get_by_role("button", name="Install example")
        install.click()
        expect(guide.get_by_role("button", name="Installing…")).to_be_disabled()
        wire.answer(page, "flowverses.fetch", {"said": "fetched official"})
        expect(guide.get_by_role("alert")).to_have_text("official lists no ralph_loop.")
        expect(install).to_be_enabled()
        assert [one["name"] for one in wire.params("flowverses.fetch")] == ["official"]
        assert [one["flow"] for one in wire.params("flowverses.install")] == [
            "ralph_loop"
        ]


@pytest.mark.usefixtures("project")
def test_a_home_with_no_flow_says_where_one_comes_from_on_the_flows(
    engine: str,
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/flows")
        none = page.locator("[data-hmz=no-flows]")
        expect(none.locator("strong")).to_have_text("No flows yet.")
        none.get_by_role("link", name="New epic").click()
        expect(page.locator("[data-hmz=first-use]")).to_be_visible()


#: `/rpc` as `hmz web` answers it where the daemon cannot be reached (Section 4.7.4 of
#: protocol/web.md), while `window.unreached` holds: closed with 1011 and why.
_UNREACHED = """
const Real = WebSocket
window.unreached = true
class Refusing {
  constructor() {
    this.readyState = 0
    setTimeout(() => {
      this.readyState = 3
      this.onclose?.({ code: 1011, reason: 'The daemon cannot be reached: no socket' })
    }, 10)
  }
  send() {}
  close() {}
}
window.WebSocket = new Proxy(Real, {
  construct: (made, [url, ...rest]) =>
    window.unreached && /\\/rpc$/.test(url) ? new Refusing() : new made(url, ...rest),
})
"""


@pytest.mark.usefixtures("project")
def test_local_out_of_reach_says_why_and_what_next_until_it_is_reached(
    engine: str,
) -> None:
    with served() as site, opened(site, engine=engine, init=_UNREACHED) as page:
        card = page.locator("[data-hmz=sidebar] [data-hmz=unreached]")
        expect(card.get_by_role("alert")).to_contain_text(
            "Local is unavailable, failed: The daemon cannot be reached: no socket."
        )
        expect(card.locator("[data-hmz=next]")).to_have_text(
            "Check that hmz web is still running, then press Connect. If it stopped,"
            " start it again and open the address it prints."
        )
        expect(card.get_by_role("link", name="Manage")).to_have_attribute(
            "href", "#/settings/daemons"
        )
        # The view in front says the same, where it asked.
        expect(page.locator("[data-hmz=page] [data-hmz=next]").first).to_have_text(
            re.compile("^Check that hmz web is still running")
        )

        page.evaluate("window.unreached = false")
        card.get_by_role("button", name="Connect").click()
        expect(page.locator("[data-hmz=epics] [data-hmz=workspace]")).to_have_count(1)
        expect(card).to_have_count(0)

"""The pictures of `docs/user/flows.md`: flows found, installed, updated and copied.

The official flowverse as a reader has it -- fetched, listing its six flows -- and one of
the person's team's, `team`, listing a flow `review` at two releases. A flow is installed
out of the official one in the app; the Installed tab is read with a newer release out; a
flowverse is added; the same is walked in the terminal interface, where a flow is copied
into the project too; and a flow not installed is refused on the command line. Run it by
naming it: `uv run pytest tests/system/docs/test_docs_user_flows.py`.

Nothing is fetched from anywhere: the suite tells git that `https://github.com/` is a
directory of this machine's, so the repositories made there are cloned, listed and
installed by the interfaces as the real ones would be.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import TYPE_CHECKING

import yaml
from playwright.sync_api import expect

from hmz.tui.flows import Flows
from tests.integration.conftest import FLOWS
from tests.integration.doubles_tui import on, onto, shows
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-flows"

#: The team's flowverse: what it is called once added, and where it and its flow live.
_VERSE = "team"
_INDEX = "alex/flowverse"
_REPO = "alex/review-flow"

#: What the index says of the flow.
_ABOUT = "Review the current diff and write the findings to REVIEW.md."

#: The flows the official index lists, and what it says of each.
_OFFICIAL = {
    "continue_loop": (
        'Send the task once, then keep nudging "continue" until the budget is spent.'
    ),
    "flame_chase": "Two agents take turns on the same task until the budget is spent.",
    "goal": "The task set once as the agent's own goal.",
    "ralph_loop": "The task again and again, a fresh session every round.",
    "rlar": "An actor works in one session until a fresh reviewer says the task is done.",
    "stateful_ralph": "The task again and again, in one session that remembers.",
}

#: The team's flow: `review/__init__.py`.
_REVIEW = '''from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)


class Agents(AgentCollection):
    reviewer: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def review(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Review the current diff and write the findings to REVIEW.md."""
    reviewer = agents["reviewer"]
    session = await reviewer.spawn()
    await reviewer.run(
        f"Write what is wrong with the diff to REVIEW.md.\\n\\n{task}",
        session=session,
        env=envs["workspace"],
    )
'''


def _git(at: Path, *argv: str) -> str:
    said = subprocess.run(
        ["git", "-c", "user.name=Alex Kim", "-c", "user.email=alex@example.com", *argv],
        cwd=at,
        check=True,
        capture_output=True,
        text=True,
    )
    return said.stdout.strip()


def _listed(listing: Path, name: str, version: str, said: dict[str, str]) -> None:
    """Writes one release's manifest into an index, and commits it."""
    at = listing / "flows" / name / version
    at.mkdir(parents=True)
    (at / "flow.yaml").write_text(
        yaml.safe_dump({"name": name, "version": version, **said}, sort_keys=False)
    )
    if not (listing / ".git").exists():
        _git(listing, "init", "-q", "-b", "main")
    _git(listing, "add", "-A")
    _git(listing, "commit", "-q", "-m", f"{name} {version}")


def _official(world: World, tmp_path: Path, *installed: str) -> None:
    """Stages the official flowverse as a reader has it: fetched, some of its flows installed."""
    from hmz.runtime.flowing import verses
    from hmz.runtime.flowing.index import kept

    shutil.rmtree(kept(verses.OFFICIAL), ignore_errors=True)
    github = tmp_path / "no-github" / "humanfia"
    for name, about in _OFFICIAL.items():
        repo = github / f"{name.replace('_', '-')}-flow"
        shutil.copytree(
            FLOWS / name, repo, ignore=shutil.ignore_patterns("__pycache__")
        )
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", name)
        _listed(
            github / "flowverse",
            name,
            "1.0.0",
            {
                "description": about,
                "repo": f"humanfia/{repo.name}",
                "ref": "v1.0.0",
                "commit": _git(repo, "rev-parse", "HEAD"),
                "license": "MIT",
            },
        )
    at = verses.where(verses.OFFICIAL) / verses.INDEX
    at.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "-q", str(github / "flowverse"), str(at)], check=True
    )
    for name in installed:
        world.call("flowverses.install", flow=name, version="1.0.0")


def _released(tmp_path: Path, version: str) -> None:
    """Tags a release of the team's flow in its repository, and lists it in the team's index."""
    github = tmp_path / "no-github" / "alex"
    repo = github / "review-flow"
    if not repo.exists():
        (repo / "review").mkdir(parents=True)
        (repo / "review" / "__init__.py").write_text(_REVIEW)
        (repo / "README.md").write_text(f"# review\n\n{_ABOUT}\n")
        _git(repo, "init", "-q", "-b", "main")
    else:
        (repo / "review" / "__init__.py").write_text(
            _REVIEW.replace("Write what is wrong", "Write, file by file, what is wrong")
        )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"review {version}")
    _git(repo, "tag", f"v{version}")
    _listed(
        github / "flowverse",
        "review",
        version,
        {
            "description": _ABOUT,
            "repo": _REPO,
            "ref": f"v{version}",
            "commit": _git(repo, "rev-parse", "HEAD"),
            "subdir": "review",
            "license": "MIT",
        },
    )


def _team(world: World, tmp_path: Path) -> None:
    """The team's flowverse added, `review` installed at 0.1.0, and 0.2.0 out since."""
    _released(tmp_path, "0.1.0")
    world.call("flowverses.add", url=_INDEX, name=_VERSE)
    world.call("flowverses.install", flow=f"@{_VERSE}/review", version="0.1.0")
    _released(tmp_path, "0.2.0")
    world.call("flowverses.fetch", name=_VERSE)


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


def test_a_flow_is_installed_in_the_app(world: World, tmp_path: Path) -> None:
    _official(world, tmp_path, "goal")
    with world.page(desktop=True) as page:
        go(page, "/flows")
        expect(page.get_by_role("button", name=re.compile("goal"))).to_be_visible()
        reel = shots.Reel(f"{_PAGE}-install", window="desktop")
        tab = page.get_by_role("tab", name="Flowverses")
        reel.web(page, hold=1.4, pointer=tab, click=True)
        tab.click()
        expect(page.get_by_text("stateful_ralph")).to_be_visible()
        row = page.locator('[data-hmz="release"][data-flow="rlar"]')
        install = row.get_by_role("button", name="Install", exact=True)
        expect(install).to_be_visible()
        reel.web(page, hold=1.8, pointer=install, click=True)
        install.click()
        expect(row.get_by_text("1.0.0 installed")).to_be_visible()
        reel.web(page, hold=1.6)
        tab = page.get_by_role("tab", name="Installed")
        reel.web(page, hold=0.8, pointer=tab, click=True)
        tab.click()
        card = page.locator('[data-hmz="flows"] button[data-flow="rlar"]')
        expect(card).to_be_visible()
        reel.web(page, hold=1.2, pointer=card, click=True)
        card.click()
        expect(page.get_by_role("link", name="New epic")).to_be_visible()
        expect(page.get_by_text("reviewer", exact=True)).to_be_visible()
        reel.web(page, hold=3.5, poster=True)
        reel.save()


def test_what_is_installed_and_a_newer_release(world: World, tmp_path: Path) -> None:
    _official(world, tmp_path, "goal", "ralph_loop", "rlar")
    _team(world, tmp_path)
    with world.page(desktop=True) as page:
        go(page, "/flows")
        card = page.locator(f'[data-flow="@{_VERSE}/review"]')
        expect(card).to_contain_text("0.2.0 out")
        expect(page.get_by_text("1 update", exact=True)).to_be_visible()
        card.click()
        update = page.get_by_role("button", name="Update to 0.2.0")
        expect(update).to_be_visible()
        expect(page.get_by_text("reviewer", exact=True)).to_be_visible()
        shots.web(page, f"{_PAGE}-installed", window="desktop", pointer=update)

        # -- the flowverse it came out of: its releases, Fetch and Remove ----------------
        page.get_by_role("tab", name="Flowverses").click()
        page.get_by_role("tab", name=_VERSE).click()
        expect(page.get_by_text("0.1.0 installed")).to_be_visible()
        pick = page.get_by_role("combobox", name="Release of review")
        pick.select_option("0.2.0")
        switch = page.get_by_role("button", name="Switch")
        shots.web(page, f"{_PAGE}-flowverse", window="desktop", pointer=switch)


def test_a_flowverse_is_added_in_the_app(world: World, tmp_path: Path) -> None:
    _official(world, tmp_path, "goal")
    _released(tmp_path, "0.1.0")
    with world.page(desktop=True) as page:
        go(page, "/flows?tab=verses")
        expect(page.get_by_text("stateful_ralph")).to_be_visible()
        reel = shots.Reel(f"{_PAGE}-add", window="desktop")
        add = page.get_by_role("button", name="Add flowverse")
        reel.web(page, hold=1.3, pointer=add, click=True)
        add.click()
        url = page.get_by_role("textbox", name="URL")
        expect(url).to_be_visible()
        reel.type(page, url, _INDEX, per=5)
        reel.type(page, page.get_by_role("textbox", name="Name"), _VERSE, per=4)
        submit = page.get_by_role("button", name="Add", exact=True)
        reel.web(page, hold=1.0, pointer=submit, click=True)
        submit.click()
        expect(page.get_by_role("button", name="Install", exact=True)).to_be_visible()
        expect(page.get_by_text(_ABOUT)).to_be_visible()
        reel.web(page, hold=3.5, poster=True)
        reel.save()


def test_a_flow_is_named_on_a_chat_line_in_the_app(
    world: World, tmp_path: Path
) -> None:
    _official(world, tmp_path, "goal", "ralph_loop", "rlar")
    world.says(
        {"discount": "Checkout takes a discount code now: WELCOME10 is 10% off."}
    )
    chat = world.chat("Add a discount code to checkout")
    with world.page(desktop=True) as page:
        go(page, f"/chats/{chat}")
        expect(page.get_by_role("log")).to_contain_text("WELCOME10")
        box = page.get_by_role("textbox", name="What to say")
        box.click()
        box.press_sequentially("$r", delay=120)
        offers = page.get_by_role("listbox", name="Completions")
        expect(offers).to_contain_text("ralph_loop")
        shots.web(page, f"{_PAGE}-dollar", clip=offers, pad=110)


async def test_flows_are_installed_in_the_terminal(
    world: World, tmp_path: Path
) -> None:
    _official(world, tmp_path, "goal")
    async with world.tui(size=(100, 28)) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        reel = shots.Reel(f"{_PAGE}-terminal")
        await pilot.press(*"/flow")
        await pilot.pause()
        reel.tui(app, hold=1.0, keys="/flow")
        await pilot.press("enter")
        await on(pilot, Flows)
        await shows(pilot, "goal")
        await _settled(pilot)
        reel.tui(app, hold=1.8, keys="enter", caption="what is installed")
        await pilot.press("tab")
        await _settled(pilot)
        await pilot.press("enter")
        await shows(pilot, "humanfia/flowverse")
        await _settled(pilot)
        reel.tui(app, hold=1.6, keys="tab enter", caption="install more…")
        await pilot.press("enter")
        await shows(pilot, "stateful_ralph")
        await _settled(pilot)
        reel.tui(app, hold=1.4, keys="enter", caption="into official")
        await onto(pilot, "rlar")
        await pilot.press("enter")
        await shows(pilot, "Releases of rlar")
        await _settled(pilot)
        reel.tui(app, hold=1.6, keys="down enter", caption="its releases")
        await pilot.press("enter")
        await shows(pilot, "1.0.0 is installed")
        await _settled(pilot)
        reel.tui(app, hold=3.5, keys="enter", caption="installed", poster=True)
        reel.save()


async def test_an_installed_flow_is_updated_or_copied_in_the_terminal(
    world: World, tmp_path: Path
) -> None:
    _official(world, tmp_path, "goal", "ralph_loop", "rlar")
    _team(world, tmp_path)
    async with world.tui(size=(100, 30)) as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*"/flow", "enter")
        await on(pilot, Flows)
        await shows(pilot, f"@{_VERSE}/review")
        await onto(pilot, f"@{_VERSE}/review")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-terminal-installed")

        # -- and one of the official ones copied into the project, to be changed ---------
        await onto(pilot, "rlar")
        await pilot.click("#act-copy")
        await shows(pilot, "copied to")
        await _settled(pilot)
        assert (world.workspace / ".hmz" / "flows" / "rlar" / "__init__.py").exists()
        shots.tui(app, f"{_PAGE}-terminal-copied")


async def test_a_flow_is_named_on_a_line_in_the_terminal(
    world: World, tmp_path: Path
) -> None:
    _official(world, tmp_path, "goal", "ralph_loop", "rlar")
    async with world.tui(size=(100, 20)) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        await pilot.press(*"$r")
        await shows(pilot, "$ralph_loop")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-terminal-dollar")


def test_a_flow_not_installed_is_refused_on_the_command_line(
    world: World, tmp_path: Path
) -> None:
    _official(world, tmp_path, "goal")
    shots.cli(
        ["hmz", "exec", "-f", "rlar", "Add a discount code to checkout"],
        f"{_PAGE}-exec-refused",
    )

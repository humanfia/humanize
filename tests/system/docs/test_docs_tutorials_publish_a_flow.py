"""The pictures of `docs/tutorials/publish-a-flow.md`: a flow published to a flowverse.

One flow, `review`, as the page publishes it: a repository of its own with two tagged
releases, and an index of the person's own that lists them. The release is run by its URL
from a command line; the index is added in the app, the flow installed out of it, updated
when the index lists a newer release, and switched back; and the same is walked in the
terminal interface. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_tutorials_publish_a_flow.py`.

Nothing is fetched from anywhere: the suite tells git that `https://github.com/` is a
directory of this machine's, so the repositories made there -- `alex/review-flow`,
`alex/flowverse`, and the official index with its flows -- are cloned, listed and installed
by the interfaces as the real ones would be, under the names a reader would give theirs.
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
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "tutorials-publish-a-flow"

#: What the person's flowverse is called once added, and where it and the flow live.
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

#: The flow, as the page writes it: `review/__init__.py`.
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

#: What the reviewer answers, and the file it writes.
_FOUND = {
    "REVIEW.md": {
        "text": (
            "Wrote REVIEW.md: an unknown discount code is not refused, and nothing"
            " tests it."
        ),
        "tools": [
            {
                "name": "Bash",
                "input": {"command": "git diff"},
                "result": "1 file changed, 6 insertions(+), 1 deletion(-)",
                "takes": 0.8,
            }
        ],
        "writes": {
            "REVIEW.md": "# Review\n\n- An unknown discount code is not refused.\n"
        },
        "after": 0.8,
    }
}


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


def _official(world: World, tmp_path: Path, *, installed: bool = True) -> None:
    """Stages the official flowverse as a reader has it: fetched, its flows installed or not."""
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
    for name in _OFFICIAL if installed else ():
        world.call("flowverses.install", flow=name, version="1.0.0")


def _released(tmp_path: Path, version: str) -> None:
    """Tags a release of the flow in its repository, and lists it in the person's index."""
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


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


def test_a_release_is_run_by_its_url(world: World, tmp_path: Path) -> None:
    _released(tmp_path, "0.1.0")
    world.says(_FOUND)
    reel = shots.Reel(f"{_PAGE}-exec")
    reel.cli(
        [
            "hmz",
            "exec",
            "-f",
            f"git+https://github.com/{_REPO}@v0.1.0#review",
            "-a",
            f"reviewer={AGENT}",
            "-p",
            "budget.output_tokens=20000",
            "the checkout module",
        ],
        rows=10,
        frames=8,
    )
    reel.save()
    # And installed, it runs by the name the page gives it.
    world.call("flowverses.add", url=_INDEX, name=_VERSE)
    world.call("flowverses.install", flow=f"@{_VERSE}/review", version="0.1.0")
    subprocess.run(
        [
            "hmz",
            "exec",
            "-f",
            f"@{_VERSE}/review",
            "-a",
            f"reviewer={AGENT}",
            "-p",
            "budget.output_tokens=20000",
            "the checkout module",
        ],
        check=True,
        capture_output=True,
    )


def test_a_flowverse_is_added_and_its_flow_installed_updated_and_switched(
    world: World, tmp_path: Path
) -> None:
    _official(world, tmp_path)
    _released(tmp_path, "0.1.0")
    with world.page(desktop=True) as page:
        go(page, "/flows")
        expect(
            page.get_by_role("button", name=re.compile("ralph_loop"))
        ).to_be_visible()

        # -- the index is added, and the flow installed out of it -----------------------
        reel = shots.Reel(f"{_PAGE}-add", window="desktop")
        tab = page.get_by_role("tab", name="Flowverses")
        reel.web(page, hold=1.3, pointer=tab, click=True)
        tab.click()
        expect(page.get_by_text("stateful_ralph")).to_be_visible()
        add = page.get_by_role("button", name="Add flowverse")
        reel.web(page, hold=1.2, pointer=add, click=True)
        add.click()
        url = page.get_by_role("textbox", name="URL")
        expect(url).to_be_visible()
        reel.web(page, hold=0.8, pointer=url, click=True)
        reel.type(page, url, _INDEX, per=5)
        reel.type(page, page.get_by_role("textbox", name="Name"), _VERSE, per=4)
        submit = page.get_by_role("button", name="Add", exact=True)
        reel.web(page, hold=0.9, pointer=submit, click=True)
        submit.click()
        install = page.get_by_role("button", name="Install", exact=True)
        expect(install).to_be_visible()
        expect(page.get_by_text(_ABOUT)).to_be_visible()
        reel.web(page, hold=1.6, pointer=install, click=True)
        install.click()
        expect(page.get_by_text("0.1.0 installed")).to_be_visible()
        expect(page.get_by_role("button", name="Switch")).to_be_visible()
        reel.web(page, hold=3.5, poster=True)
        reel.save()

        # -- what is installed, opened ----------------------------------------------------
        page.get_by_role("tab", name="Installed").click()
        card = page.locator(f'[data-flow="@{_VERSE}/review"]')
        card.click()
        expect(page.get_by_role("link", name="New epic")).to_be_visible()
        expect(page.get_by_text("reviewer", exact=True)).to_be_visible()
        shots.web(page, f"{_PAGE}-installed", window="desktop")

        # -- a newer release is listed, fetched, and updated to ---------------------------
        _released(tmp_path, "0.2.0")
        page.get_by_role("tab", name="Flowverses").click()
        page.get_by_role("tab", name=_VERSE).click()
        fetch = page.get_by_role("button", name="Fetch")
        expect(fetch).to_be_visible()
        fetch.click()
        expect(page.get_by_text("1 update", exact=True)).to_be_visible()
        page.get_by_role("tab", name="Installed").click()
        expect(card).to_contain_text("0.2.0 out")
        card.click()
        update = page.get_by_role("button", name="Update to 0.2.0")
        expect(update).to_be_visible()
        shots.web(page, f"{_PAGE}-update", window="desktop", pointer=update)
        update.click()
        expect(page.get_by_text("1 update", exact=True)).to_have_count(0)
        expect(card).to_contain_text("0.2.0")

        # -- and an older one switched back to ------------------------------------------
        page.get_by_role("tab", name="Flowverses").click()
        page.get_by_role("tab", name=_VERSE).click()
        expect(page.get_by_text("0.2.0 installed")).to_be_visible()
        pick = page.get_by_role("combobox", name="Release of review")
        pick.select_option("0.1.0")
        switch = page.get_by_role("button", name="Switch")
        shots.web(
            page,
            f"{_PAGE}-switch",
            clip=page.locator(".flow-detail"),
            pad=52,
            pointer=switch,
        )


async def test_the_same_is_done_in_the_terminal(world: World, tmp_path: Path) -> None:
    _official(world, tmp_path, installed=False)
    _released(tmp_path, "0.1.0")
    world.call("flowverses.add", url=_INDEX, name=_VERSE)
    world.call("flowverses.install", flow=f"@{_VERSE}/review", version="0.1.0")
    _released(tmp_path, "0.2.0")
    world.call("flowverses.fetch", name=_VERSE)
    async with world.tui(size=(100, 28)) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        reel = shots.Reel(f"{_PAGE}-terminal")
        await pilot.press(*"/flow")
        await pilot.pause()
        reel.tui(app, hold=1.0, keys="/flow")
        await pilot.press("enter")
        await on(pilot, Flows)
        await shows(pilot, f"@{_VERSE}/review")
        await _settled(pilot)
        reel.tui(app, hold=1.8, keys="enter", caption="what is installed")
        await pilot.press("tab")
        await _settled(pilot)
        await pilot.press("enter")
        await shows(pilot, _INDEX)
        await _settled(pilot)
        reel.tui(app, hold=1.6, keys="tab enter", caption="Install more…")
        await onto(pilot, _VERSE)
        await pilot.press("enter")
        await shows(pilot, "0.2.0")
        await _settled(pilot)
        reel.tui(app, hold=1.6, keys="down enter", caption="into team")
        await pilot.press("enter")
        await shows(pilot, "Releases of review")
        await _settled(pilot)
        reel.tui(app, hold=1.8, keys="enter", caption="its releases")
        await onto(pilot, "0.2.0")
        await _settled(pilot)
        reel.tui(app, hold=1.0, keys="up", caption="to 0.2.0")
        await pilot.press("enter")
        await shows(pilot, "0.2.0 is installed")
        await _settled(pilot)
        reel.tui(app, hold=3.5, keys="enter", caption="on 0.2.0", poster=True)
        reel.save()


async def test_a_flowverse_is_added_in_the_terminal(
    world: World, tmp_path: Path
) -> None:
    _official(world, tmp_path, installed=False)
    _released(tmp_path, "0.1.0")
    async with world.tui(size=(100, 24)) as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*"/flow", "enter")
        await on(pilot, Flows)
        await _settled(pilot)
        await pilot.press("tab", "enter")
        await shows(pilot, "humanfia/flowverse")
        await _settled(pilot)
        await pilot.press("tab", "enter")
        await shows(pilot, "Add a flowverse")
        await pilot.press(*_INDEX)
        await pilot.pause(0.3)
        await pilot.press("enter")
        await pilot.pause(0.3)
        await pilot.press(*_VERSE)
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-terminal-add")
        # And the form does what the page says of it: an enter keeps the name, another answers it.
        for key in ("enter", "enter"):
            await pilot.press(key)
            await pilot.pause(0.3)
        await shows(pilot, f"{_INDEX} · 1 flow")

"""The pictures of `docs/builder/publishing.md`: a flow's releases, as an index lists them.

One index, `alex/flowverse`, added as `team`. It lists two flows: `lint`, in three releases,
and `review`, whose later releases need a `lint` of the first major version, with a release
candidate after them and one manifest that does not read. The page's own script adds the
index, installs `review` and copies it into the project; the app shows the index with what
it skipped; and the terminal interface shows every release of `review`. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_builder_publishing.py`.

Nothing is fetched from anywhere: the suite tells git that `https://github.com/` is a
directory of this machine's, so the repositories made there are cloned, listed and installed
by the interfaces as real ones would be, under the names a reader would give theirs.
"""

from __future__ import annotations

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
_PAGE = "builder-publishing"

#: What the person's flowverse is called once added, and where it lives.
_VERSE = "team"
_INDEX = "alex/flowverse"

#: What the index says of each flow.
_ABOUT = {
    "review": "Review the current diff and write the findings to REVIEW.md.",
    "lint": "Run the linters and fix what they report.",
}

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

#: A flow of one agent and one turn, as each of the two repositories holds it.
_FLOW = '''from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def NAME(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """ABOUT"""
    worker = agents["worker"]
    session = await worker.spawn()
    await worker.run(task, session=session, env=envs["workspace"])
'''

#: The page's script: the index added, the flow installed, and what did not read.
_INSTALL = """from hmz.sdk import Hmz

verses = Hmz().verses
verses.add("alex/flowverse", "team")

for one in verses.install("@team/review"):
    print("installed", one.called, one.version)

for bad in verses.index("team").skipped:
    print("skipped", bad.at.parent.name, "-", bad.why)
"""

#: The page's other script: the installed flow copied into the project.
_FORK = """import os

from hmz.sdk import Hmz

flows = Hmz().flows
print(os.path.relpath(flows.fork("@team/review")))
print(os.path.relpath(flows.find("review")))
"""


def _git(at: Path, *argv: str) -> str:
    said = subprocess.run(
        ["git", "-c", "user.name=Alex Kim", "-c", "user.email=alex@example.com", *argv],
        cwd=at,
        check=True,
        capture_output=True,
        text=True,
    )
    return said.stdout.strip()


def _listed(listing: Path, name: str, version: str, said: dict[str, object]) -> None:
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


def _released(
    tmp_path: Path, name: str, version: str, needs: dict[str, str] | None = None
) -> None:
    """Tags a release of a flow in its repository, and lists it in the person's index."""
    github = tmp_path / "no-github" / "alex"
    repo = github / f"{name}-flow"
    fresh = not repo.exists()
    (repo / name).mkdir(parents=True, exist_ok=True)
    (repo / name / "__init__.py").write_text(
        _FLOW.replace("NAME", name).replace("ABOUT", _ABOUT[name]) + f"\n# {version}\n"
    )
    if fresh:
        _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"{name} {version}")
    _git(repo, "tag", f"v{version}")
    said: dict[str, object] = {
        "description": _ABOUT[name],
        "repo": f"alex/{name}-flow",
        "ref": f"v{version}",
        "commit": _git(repo, "rev-parse", "HEAD"),
        "subdir": name,
        "license": "MIT",
    }
    if needs:
        said["dependencies"] = needs
    _listed(github / "flowverse", name, version, said)


def _published(tmp_path: Path) -> None:
    """The index as the page has it: two flows, a release candidate, a manifest that fails."""
    for version in ("1.0.0", "1.1.0", "2.0.0"):
        _released(tmp_path, "lint", version)
    needs = {"lint": ">=1.0.0,<2.0.0"}
    _released(tmp_path, "review", "0.1.0")
    _released(tmp_path, "review", "0.2.0", needs)
    _released(tmp_path, "review", "0.3.0-rc.1", needs)
    # And one written with the short commit `git log --oneline` prints, which is not listed.
    _listed(
        tmp_path / "no-github" / "alex" / "flowverse",
        "review",
        "0.4.0",
        {
            "description": _ABOUT["review"],
            "repo": "alex/review-flow",
            "ref": "v0.4.0",
            "commit": "4b1f0c9",
            "subdir": "review",
            "license": "MIT",
        },
    )


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


def test_a_script_installs_a_release_and_copies_it(
    world: World, tmp_path: Path
) -> None:
    _published(tmp_path)
    (world.workspace / "install.py").write_text(_INSTALL)
    (world.workspace / "fork.py").write_text(_FORK)
    shots.cli(["python", "install.py"], f"{_PAGE}-install", columns=96)
    from hmz.runtime.flowing.index import installed

    held = {one.called: one.version for one in installed(_VERSE)}
    assert held == {"@team/lint": "1.1.0", "@team/review": "0.2.0"}
    shots.cli(["python", "fork.py"], f"{_PAGE}-fork", columns=64)
    assert (world.workspace / ".hmz" / "flows" / "review" / "__init__.py").is_file()


def test_the_app_lists_the_index_and_what_it_skipped(
    world: World, tmp_path: Path
) -> None:
    _official(world, tmp_path)
    _published(tmp_path)
    world.call("flowverses.add", url=_INDEX, name=_VERSE)
    world.call("flowverses.install", flow=f"@{_VERSE}/review", version="")
    with world.page(desktop=True) as page:
        go(page, "/flows")
        page.get_by_role("tab", name="Flowverses").click()
        page.get_by_role("tab", name=_VERSE).click()
        expect(page.get_by_text("0.2.0 installed")).to_be_visible()
        skipped = page.get_by_text("1 skipped")
        expect(skipped).to_be_visible()
        skipped.click()
        expect(page.get_by_text("40 hex")).to_be_visible()
        shots.web(page, f"{_PAGE}-index", window="desktop")


async def test_the_terminal_lists_every_release_of_a_flow(
    world: World, tmp_path: Path
) -> None:
    _official(world, tmp_path, installed=False)
    _published(tmp_path)
    world.call("flowverses.add", url=_INDEX, name=_VERSE)
    world.call("flowverses.install", flow=f"@{_VERSE}/review", version="")
    async with world.tui(size=(100, 26)) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        await pilot.press(*"/flow", "enter")
        await on(pilot, Flows)
        await shows(pilot, f"@{_VERSE}/review")
        await _settled(pilot)
        await pilot.press("tab")
        await _settled(pilot)
        await pilot.press("enter")
        await shows(pilot, _INDEX)
        await _settled(pilot)
        await onto(pilot, _VERSE)
        await pilot.press("enter")
        await shows(pilot, "lint")
        await _settled(pilot)
        await onto(pilot, "review")
        await pilot.press("enter")
        await shows(pilot, "Releases of review")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-releases")

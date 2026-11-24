"""The Flows page and the transfer pages of the real interface, against real git on this machine.

A flowverse here is a real one, as `hmz web`'s own test makes one: a repository holding a flow,
and an index -- another repository -- listing two releases of it. The page adds the index,
installs out of it, updates and uninstalls, as somebody would with the keys; an epic is
exported to a file and read back in, and one is downloaded out of a backup target.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import tomlkit
import yaml
from textual.widgets import OptionList

from hmz import config
from hmz.runtime import Hmz
from hmz.runtime.epic import Epic, epics
from hmz.tui import Humanize
from hmz.tui.flows import Fetches, Uninstalls
from hmz.tui.pick import Exporting, ImportingEpic
from hmz.tui.views.flowspage import FlowsPage
from hmz.tui.views.transfers import Download, Export, Import, moving
from tests.integration.doubles_tui import (
    OWN,
    SIZE,
    folds_fast,
    on,
    opened,
    screen,
    shows,
    stand_in,
    until,
)

#: Every epic here is held by a daemon of the test's own, in this process.
pytestmark = [pytest.mark.usefixtures("daemon", "loops"), pytest.mark.timeout(180)]

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


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, and a chat left that folds away at once."""
    del asking
    folds_fast(monkeypatch)
    return stand_in(tmp_path, monkeypatch)


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
def index(tmp_path: Path) -> Path:
    """An index on this machine listing `solo` 1.0.0 and 1.1.0, each a commit of one flow."""
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


def _rows(app: Humanize) -> list[str]:
    """The ids of the rows the page on top lists that can be picked."""
    listing = app.screen.query_one("#rows", OptionList)
    return [str(one.id) for one in listing.options if one.id]


async def _onto(pilot: Any, app: Humanize, row: str) -> None:
    """Walks the cursor of the page on top on to one row."""
    listing = app.screen.query_one("#rows", OptionList)
    await until(pilot, lambda: row in _rows(app), f"the row {row}")
    at = [str(one.id) for one in listing.options].index(row)
    for _ in range(len(listing.options) + 1):
        if listing.highlighted == at:
            return
        await pilot.press("down" if (listing.highlighted or 0) < at else "up")
    assert listing.highlighted == at


async def test_a_flow_is_installed_updated_and_uninstalled_from_the_flows_page(
    workspace: Path, index: Path
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await shows(pilot, "^L Flows")

        await pilot.press("ctrl+l")
        page = await on(pilot, FlowsPage)
        await shows(pilot, "FLOWS", "▸ INSTALLED", "FLOWVERSES", "goal")
        assert "@theirs/solo" not in _rows(app)

        # A flowverse is added, by where it is and what to call it.
        await pilot.press("tab")
        await shows(pilot, "▸ FLOWVERSES", "A Add flowverse")
        await pilot.press("a")
        await on(pilot, Fetches)
        await pilot.press(*str(index), "enter", *"theirs", "enter")
        await pilot.click("#act-done")
        await on(pilot, FlowsPage)
        await shows(pilot, "Fetched theirs.", "1 flow")

        # The older of its two releases is installed out of it.
        await _onto(pilot, app, "theirs")
        await pilot.press("enter")
        await shows(pilot, "solo", "1.1.0", "I Install")
        await pilot.press("enter")
        await shows(pilot, "Releases of solo")
        await _onto(pilot, app, "1.0.0")
        await pilot.press("enter")
        await shows(pilot, "@theirs/solo 1.0.0 is installed.")

        # Under Installed it is first, marked as having a newer release, and counted.
        await pilot.press("escape", "escape", "tab")
        await shows(pilot, "▸ INSTALLED", "1 flow has a newer release", "↑ 1.1.0")
        assert _rows(app)[0] == "@theirs/solo"

        # Opened: what it says of itself, and what it declares.
        await _onto(pilot, app, "@theirs/solo")
        await pilot.press("enter")
        await shows(pilot, "One agent, one turn.", "AGENTS", "solo", "U Update")

        await pilot.press("u")
        await shows(pilot, "@theirs/solo 1.1.0 is installed.")
        assert "newer release" not in screen(app)

        # Uninstalling asks first, by name; walking out of the question keeps it.
        await pilot.press("x")
        await on(pilot, Uninstalls)
        await shows(pilot, "Uninstall @theirs/solo?")
        await pilot.press("escape")
        await on(pilot, FlowsPage)
        assert Hmz().verses.installed()[-1].called == "@theirs/solo"

        await pilot.press("x")
        await on(pilot, Uninstalls)
        await pilot.press("enter")
        await on(pilot, FlowsPage)
        await shows(pilot, "@theirs/solo is uninstalled.", "▸ INSTALLED")
        assert "@theirs/solo" not in _rows(app)

        # The key that opened the page closes it, and what was done is in the transcript.
        await pilot.press("ctrl+l")
        await until(pilot, lambda: app.screen is not page, "the page to close")
        await shows(pilot, "@theirs/solo is uninstalled.")
    assert "@theirs/solo" not in [one.called for one in Hmz().verses.installed()]


async def test_nothing_is_installed_from_the_flows_page_while_an_epic_is_going(
    workspace: Path, index: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    Hmz().verses.add(str(index), "theirs")
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        monkeypatch.setattr(app, "flow_running", lambda: True)
        await pilot.press("ctrl+l")
        await on(pilot, FlowsPage)
        await shows(pilot, "An epic is going; flows are installed")

        await pilot.press("tab")
        await _onto(pilot, app, "theirs")
        await pilot.press("enter")
        await shows(pilot, "solo")
        await pilot.press("i")
        await pilot.pause()

    assert Hmz().verses.installed() == []


async def test_an_epic_is_exported_from_the_export_page_and_imported_back(
    workspace: Path,
) -> None:
    with Epic(OWN, "here", workspace) as here:
        pass
    archive = Path.home() / "out.hmzepic"
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)

        await app.shell.opens("export")
        await on(pilot, Export)
        await shows(pilot, "EXPORT", "No transfer yet.", "enter Export")
        await _onto(pilot, app, here.path.name)
        await pilot.press("enter")
        await on(pilot, Exporting)
        await pilot.press(*"~/out.hmzepic", "enter", "enter")
        await on(pilot, Export)
        await until(pilot, archive.exists, "the archive")
        await shows(pilot, f"Exported {here.path.name} to ~/out.hmzepic")

        # Left and opened again, the page still says what came of it.
        await pilot.press("escape")
        await until(pilot, lambda: len(app.screen_stack) == 1, "the page to close")
        shutil.rmtree(here.path)

        # Nothing imported yet, so the page asks for the file as it opens.
        await app.shell.opens("import")
        await on(pilot, ImportingEpic)
        await pilot.press(*"~/out.hmzepic", "enter", "enter")
        await on(pilot, Import)
        await shows(pilot, "IMPORT", f"Exported {here.path.name}", "enter Import")
        await until(pilot, here.path.is_dir, "the epic to be read back in")
        await shows(pilot, "Imported into")

        (exporting, importing) = moving(app)
        assert (exporting.kind, exporting.done, exporting.failed) == (
            "export",
            True,
            False,
        )
        assert (importing.kind, importing.failed) == ("import", False)
    assert epics(workspace) == [here.path]


def _bare(tmp_path: Path) -> Path:
    at = tmp_path / "lab.git"
    subprocess.run(["git", "init", "-q", "--bare", str(at)], check=True)
    return at


def _targets(*targets: dict[str, Any]) -> None:
    config().mkdir(parents=True, exist_ok=True)
    (config() / "settings.toml").write_text(
        tomlkit.dumps({"backup": {"targets": list(targets), "defaults": []}})
    )


async def test_an_epic_is_downloaded_from_the_download_page(
    workspace: Path, tmp_path: Path
) -> None:
    _targets({"name": "lab", "url": str(_bare(tmp_path))})
    with Epic("chat", "fix the build", workspace) as epic:
        pass
    Hmz().backups.push(epic.path, ["lab"])
    assert Hmz().backups.wait(60)
    shutil.rmtree(epic.path)
    (held,) = Hmz().backups.listed("lab")

    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await app.shell.opens("download")
        await on(pilot, Download)
        await shows(pilot, "DOWNLOAD", "Download from lab", held.machine)
        await shows(pilot, "fix the build · done", "enter Download", "F Fetch")

        await _onto(pilot, app, held.key)
        await pilot.press("enter")
        await until(pilot, epic.path.is_dir, "the epic to land")
        await shows(pilot, f"Downloaded {epic.path.name} into", "· Here")

        await pilot.press("enter")
        await shows(pilot, "is here already")
        await pilot.press("escape")
        await until(pilot, lambda: len(app.screen_stack) == 1, "the page to close")
        await shows(pilot, f"Downloaded {epic.path.name} into")
    assert epics(workspace) == [epic.path]

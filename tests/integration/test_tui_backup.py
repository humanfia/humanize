"""Backing epics up from the interface: the targets on `/settings`, `/flow` and `/epics`.

Each target is a bare repository in the test's own directory, reached by the git on this
machine as any remote is; the runs are held in this process, so their backups are too.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from typing import TYPE_CHECKING, Any

import pytest
import tomlkit

from hmz import config
from hmz.runtime import Hmz
from hmz.runtime.epic import Epic, chats, epics, read
from hmz.tui import Humanize
from hmz.tui.flows import Flows
from hmz.tui.pick import Backing, Does, Epics, Targets
from hmz.tui.settings import Adjusts
from hmz.tui.stored import Stored
from tests.integration.doubles_tui import (
    OWN,
    RUNS,
    SIZE,
    folds_fast,
    gives_a_budget,
    leaves,
    on,
    onto,
    opened,
    opens,
    own_flow,
    picks,
    set_up_own_flow,
    shows,
    stand_in,
    typed,
    until,
    wrapped,
)

if TYPE_CHECKING:
    from pathlib import Path

#: Every epic here is held by a daemon of the test's own, in this process.
pytestmark = pytest.mark.usefixtures("daemon", "loops")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, and a chat left that folds away at once."""
    del asking
    folds_fast(monkeypatch)
    return stand_in(tmp_path, monkeypatch)


def _bare(tmp_path: Path, name: str) -> Path:
    at = tmp_path / f"{name}.git"
    subprocess.run(["git", "init", "-q", "--bare", str(at)], check=True)
    return at


def _targets(*targets: dict[str, Any], defaults: tuple[str, ...] = ()) -> None:
    config().mkdir(parents=True, exist_ok=True)
    (config() / "settings.toml").write_text(
        tomlkit.dumps(
            {"backup": {"targets": list(targets), "defaults": list(defaults)}}
        )
    )


def _ended(workspace: Path) -> bool:
    found = epics(workspace)
    ran = read(found[0]) if found else None
    return ran is not None and bool(ran.ended)


def _log(bare: Path) -> list[str]:
    return subprocess.run(
        ["git", "--git-dir", str(bare), "log", "--format=%s", "main"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()


async def test_a_target_added_on_the_backup_page_is_written_to_settings(
    workspace: Path, tmp_path: Path
) -> None:
    bare = _bare(tmp_path, "lab")
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/settings backup")
        await on(pilot, Adjusts)
        await shows(pilot, "No backup target yet.")

        await pilot.click("#act-add")
        await on(pilot, Backing)
        await picks(pilot, "end", "on")
        await picks(pilot, "default", "on")
        await onto(pilot, "name")
        await pilot.press(*"lab", "enter")
        await pilot.press(*f"file://{bare}", "enter")
        await pilot.click("#act-done")

        await on(pilot, Adjusts)
        await shows(pilot, "lab ✔", "On epic end")
        await leaves(pilot)
        await shows(pilot, "1 backup target saved")

    saved = tomllib.loads((config() / "settings.toml").read_text())["backup"]
    assert saved == {
        "targets": [
            {
                "name": "lab",
                "url": f"file://{bare}",
                "branch": "main",
                "policies": ["end"],
                "every": 30,
            }
        ],
        "defaults": ["lab"],
    }


async def test_flow_offers_the_defaults_and_starts_the_epic_on_the_targets_chosen(
    workspace: Path, tmp_path: Path
) -> None:
    lab, spare = _bare(tmp_path, "lab"), _bare(tmp_path, "spare")
    _targets(
        {"name": "lab", "url": str(lab), "policies": ["end"]},
        {"name": "spare", "url": str(spare), "policies": ["end"]},
        defaults=("lab",),
    )
    own_flow(workspace)
    async with Humanize().run_test(size=SIZE) as pilot:
        await set_up_own_flow(pilot)
        await typed(pilot, "/flow")
        await on(pilot, Flows)
        await opens(pilot, OWN)
        await shows(pilot, "where each epic is backed up (the defaults)")

        await opens(pilot, "\x1ebackup")
        await on(pilot, Targets)
        await picks(pilot, "spare", "on")
        await pilot.click("#act-done")
        await on(pilot, Flows)
        await shows(pilot, "lab, spare")
        await leaves(pilot)

        # A flow, which a chat is not: its epic goes where the flow menu said.
        await typed(pilot, f"${OWN} hello")
        await shows(pilot, "Flow done")
        await until(pilot, lambda: _ended(workspace), "the epic to end")

    assert Hmz().backups.wait(60)
    (epic,) = epics(workspace)
    ran = read(epic)
    assert ran is not None
    assert ran.backup == ("lab", "spare")
    assert _log(lab) == [f"Back up epic {epic.name} (end)"]
    assert _log(spare) == [f"Back up epic {epic.name} (end)"]
    # Remembered for the flow here, and opened on next time.
    assert Hmz().settings.backup(OWN) == ("lab", "spare")
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/flow")
        await on(pilot, Flows)
        await opens(pilot, OWN)
        await shows(pilot, "lab, spare")


async def test_a_flow_saved_without_choosing_backup_follows_the_defaults(
    workspace: Path, tmp_path: Path
) -> None:
    _targets({"name": "lab", "url": str(_bare(tmp_path, "lab"))}, defaults=("lab",))
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/flow")
        await on(pilot, Flows)
        await opens(pilot, "goal")
        await picks(pilot, "\x1eprofile-environment", "on")
        await gives_a_budget(pilot)
        await leaves(pilot)
        await shows(pilot, f"◉ {RUNS}")

    assert Hmz().settings.profile_environment("goal")
    assert Hmz().settings.backup("goal") is None


async def test_an_epic_uploaded_from_epics_lands_in_its_target(
    workspace: Path, tmp_path: Path
) -> None:
    lab = _bare(tmp_path, "lab")
    _targets({"name": "lab", "url": str(lab)}, defaults=("lab",))
    own_flow(workspace)
    async with Humanize().run_test(size=SIZE) as pilot:
        await set_up_own_flow(pilot)
        await typed(pilot, f"${OWN} hello")
        await shows(pilot, "Flow done")
        await until(pilot, lambda: _ended(workspace), "the epic to end")
        assert _log(lab) == []  # no policy, so only by hand

        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await wrapped(pilot, "1 session")
        await pilot.press("enter")
        await on(pilot, Does)
        await opens(pilot, "upload")

        await on(pilot, Epics)
        (epic,) = epics(workspace)
        await shows(pilot, "Uploading to lab")
        assert Hmz().backups.wait(60)

        await pilot.press("enter")
        await on(pilot, Does)
        await shows(pilot, "lab: uploaded")

    assert _log(lab) == [f"Back up epic {epic.name} (manual)"]


async def test_an_epic_downloaded_from_the_backup_page_lands_here_again(
    workspace: Path, tmp_path: Path
) -> None:
    _targets({"name": "lab", "url": str(_bare(tmp_path, "lab"))})
    with Epic("chat", "fix the build", workspace) as epic:
        pass
    Hmz().backups.push(epic.path, ["lab"])
    assert Hmz().backups.wait(60)
    shutil.rmtree(epic.path)
    (held,) = Hmz().backups.listed("lab")

    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/settings backup")
        await on(pilot, Adjusts)
        await pilot.click("#act-download")
        await on(pilot, Stored)
        await shows(pilot, "Download from lab", held.machine, "fix the build · done")

        await opens(pilot, held.key)
        await shows(pilot, f"Downloaded {epic.path.name}")
        await until(pilot, epic.path.is_dir, "the epic to land")
        await shows(pilot, "fix the build · done · Here")
        await pilot.press("enter")
        await shows(pilot, "is here already")

        await leaves(pilot)
        await shows(pilot, f"Downloaded {epic.path.name} into")
    assert epics(workspace) == [epic.path]


async def test_a_chat_downloaded_from_the_backup_page_lands_among_the_chats(
    workspace: Path, tmp_path: Path
) -> None:
    _targets({"name": "lab", "url": str(_bare(tmp_path, "lab"))})
    with Epic("", "what is here?", workspace, kind="chat") as chat:
        pass
    Hmz().backups.push(chat.path, ["lab"])
    assert Hmz().backups.wait(60)
    shutil.rmtree(chat.path)
    (held,) = Hmz().backups.listed("lab")

    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/settings backup")
        await on(pilot, Adjusts)
        await pilot.click("#act-download")
        await on(pilot, Stored)
        # Named a chat, having no flow, and gone back to as a chat is.
        await wrapped(pilot, "· chat", "what is here? · done")

        await opens(pilot, held.key)
        await until(pilot, chat.path.is_dir, "the chat to land")
        await wrapped(pilot, "carry it on with /resume in a chat")
        await wrapped(pilot, "what is here? · done · Here")
        await leaves(pilot)
    assert chats(workspace) == [chat.path]
    assert epics(workspace) == []

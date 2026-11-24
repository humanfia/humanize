"""The chats written down, tidied from the interface: `/resume` in a chat, and `/settings`.

Each chat on `/resume` has a menu of what `chat.*` does to one as it is written down -- it is
renamed, forked, archived, backed up and deleted there, the one on the screen among them --
and the archived ones are on the Workspace page of `/settings`, where one picked is put back.
The chats are the daemon's own, held in this process, and the assistant the stand-in `claude`.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
import tomlkit

from hmz import config
from hmz.runtime import Hmz
from hmz.runtime.epic import Ran, chats, read
from hmz.tui import Humanize
from hmz.tui.chats import Archived, Deletes, Renames, Resumes
from hmz.tui.pick import Acts
from hmz.tui.settings import Adjusts
from tests.integration.doubles_tui import (
    RUNS,
    SIZE,
    Chats,
    folds_fast,
    leaves,
    on,
    onto,
    opened,
    opens,
    rows,
    screen,
    shows,
    stand_in,
    typed,
    until,
    wrapped,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: Every chat here is held by a daemon of the test's own, in this process.
pytestmark = pytest.mark.usefixtures("daemon", "loops")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, and a chat left that folds away at once."""
    del asking
    folds_fast(monkeypatch)
    return stand_in(tmp_path, monkeypatch)


def _said(chat: Path) -> Ran:
    return read(chat) or Ran(chat)


async def _two(pilot: Pilot[None], workspace: Path) -> tuple[Path, Path]:
    """Has one chat, leaves it to fold away, and has a second, which is on the screen."""
    await opened(pilot)
    await typed(pilot, "first")
    await shows(pilot, "heard first", "◉ done")
    await typed(pilot, "/clear")
    await until(pilot, lambda: len(chats(workspace)) == 1, "the chat")
    (first,) = chats(workspace)
    await until(pilot, lambda: bool(_said(first).ended), "it to fold")
    await typed(pilot, "second")
    await shows(pilot, "heard second", "◉ done")
    _, second = chats(workspace)
    return first, second


async def _does(pilot: Pilot[None], chat: Path, what: str) -> None:
    """Opens `/resume`, and takes one row of one chat's menu."""
    await typed(pilot, "/resume")
    await on(pilot, Resumes)
    await onto(pilot, chat.name)
    await pilot.press("m")
    await on(pilot, Acts)
    await opens(pilot, what)


async def test_resume_lists_the_chat_on_the_screen_too_and_renames_one(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        first, second = await _two(pilot, workspace)

        await typed(pilot, "/resume")
        listing = await on(pilot, Resumes)
        # Newest first, the one already had among them and under the cursor.
        assert rows(app) == [second.name, first.name]
        assert listing.under() == second.name

        await pilot.press("m")
        await on(pilot, Acts)
        assert rows(app) == ["rename", "fork", "archive", "delete", "copy-name"]
        await opens(pilot, "rename")
        await on(pilot, Renames)
        await pilot.press(*"the parser", "enter")
        await pilot.click("#act-done")

        await on(pilot, Resumes)
        await wrapped(pilot, "renamed the parser")
        assert _said(second).title == "the parser"

        # Picked, the one on the screen stays there.
        await pilot.press("enter")
        await shows(pilot, "heard second")
        assert len(app.screen_stack) == 1
    assert chats(workspace) == [first, second]


async def test_a_chat_archived_leaves_resume_and_is_put_back_from_settings(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = Chats().install(monkeypatch).asked
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        first, second = await _two(pilot, workspace)

        await _does(pilot, first, "archive")
        await on(pilot, Resumes)
        await wrapped(pilot, "archived first; /settings workspace puts it back")
        assert rows(app) == [second.name]
        assert _said(first).archived
        await pilot.press("escape")

        await typed(pilot, "/settings workspace")
        await on(pilot, Adjusts)
        await opens(pilot, "archived")
        await on(pilot, Archived)
        await until(pilot, lambda: rows(app) == [first.name], "the archived chat")
        await pilot.press("enter")
        await wrapped(pilot, "put back first")
        assert rows(app) == []
        assert not _said(first).archived
        await leaves(pilot)

        await typed(pilot, "/resume")
        await on(pilot, Resumes)
        assert rows(app) == [second.name, first.name]
    assert ("chat.archive", {"chat": first.name}) in asked


async def test_the_chat_on_the_screen_archived_gives_way_to_a_new_one(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        first, second = await _two(pilot, workspace)

        await _does(pilot, second, "archive")
        await on(pilot, Resumes)
        await wrapped(pilot, "archived second")
        await pilot.press("escape")

        await shows(pilot, f"◉ {RUNS}")
        assert "heard second" not in screen(app)
        await typed(pilot, "third")
        await shows(pilot, "heard third")
    assert len(chats(workspace)) == 3
    assert [_said(one).archived for one in (first, second)] == [False, True]


async def test_a_chat_is_deleted_only_once_it_is_said_to_be_for_good(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        first, second = await _two(pilot, workspace)

        await _does(pilot, first, "delete")
        await on(pilot, Deletes)
        await shows(pilot, "Delete first?", "Permanent", "cannot be brought back")
        # Keeping it is the answer under the cursor.
        await pilot.press("enter")
        await on(pilot, Resumes)
        assert first.is_dir()

        await pilot.press("m")
        await on(pilot, Acts)
        await opens(pilot, "delete")
        await on(pilot, Deletes)
        await pilot.press("right", "enter")
        await on(pilot, Resumes)
        await wrapped(pilot, "deleted first")
        assert rows(app) == [second.name]
        assert not first.exists()

        # The one a host holds between turns is deleted too: its host is ended first.
        await pilot.press("m")
        await on(pilot, Acts)
        await opens(pilot, "delete")
        await on(pilot, Deletes)
        await pilot.press("right", "enter")
        await on(pilot, Resumes)
        await wrapped(pilot, "deleted second")
    assert chats(workspace) == []


async def test_a_chat_forked_is_gone_on_with_as_a_chat_of_its_own(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = Chats().install(monkeypatch).asked
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        first, second = await _two(pilot, workspace)

        await _does(pilot, first, "fork")

        await shows(pilot, "say something to continue chat")
        assert len(app.screen_stack) == 1
        fork = next(one for one in chats(workspace) if one not in (first, second))
        assert _said(fork).forked == first.name
        await typed(pilot, "more")
        await shows(pilot, "heard more")
    starts = [said for method, said in asked if method == "chat.start"]
    assert starts[-1]["resume"] == fork.name
    assert len(chats(workspace)) == 3


def _target(tmp_path: Path) -> Path:
    """A bare repository of the test's own, saved as the default backup target `lab`."""
    lab = tmp_path / "lab.git"
    subprocess.run(["git", "init", "-q", "--bare", str(lab)], check=True)
    config().mkdir(parents=True, exist_ok=True)
    (config() / "settings.toml").write_text(
        tomlkit.dumps(
            {
                "backup": {
                    "targets": [{"name": "lab", "url": str(lab)}],
                    "defaults": ["lab"],
                }
            }
        )
    )
    return lab


def _log(bare: Path) -> list[str]:
    return subprocess.run(
        ["git", "--git-dir", str(bare), "log", "--format=%s", "main"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()


async def test_a_chat_uploaded_from_resume_lands_in_its_target(
    workspace: Path, tmp_path: Path
) -> None:
    lab = _target(tmp_path)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        first, _ = await _two(pilot, workspace)

        await _does(pilot, first, "upload")
        await on(pilot, Resumes)
        await wrapped(pilot, "backing up to lab")
        await until(pilot, lambda: "lab" in _said(first).backed, "the backup")

    assert _said(first).backed["lab"]["ok"]
    assert _log(lab) == [f"Back up epic {first.name} (manual)"]
    assert [one.chat for one in Hmz().backups.listed("lab")] == [True]

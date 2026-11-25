"""Files, Changes and Terminal beside a chat: its environment, read while it is talked to.

The real interface, a chat with the stand-in agent in a git workspace, and this machine's
daemon answering `env.*` for the chat's own environment: a file is read in the pane, a change
is staged and committed from it, and a shell in it runs a command -- each with the prompt a
key away, and the pane still open once it has the keys back.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
from textual.widgets import OptionList

from hmz.tui import Humanize
from hmz.tui.envs import ChangesPane, Commit, FilesPane, TerminalPane, Tty
from hmz.tui.shell import Zone
from tests.integration.doubles_tui import (
    SIZE,
    on,
    opened,
    screen,
    shows,
    stand_in,
    typed,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: The chat here is held by a daemon of the test's own, in this process.
pytestmark = [pytest.mark.usefixtures("daemon", "loops"), pytest.mark.timeout(180)]


def _git(workspace: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *argv],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """A git repository with one commit, and the stand-in `claude` to chat with in it."""
    del asking
    workspace = stand_in(tmp_path, monkeypatch)
    for name in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(name, "t")
    for name in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(name, "t@example.com")
    _git(workspace, "init", "-q", "-b", "main")
    (workspace / "README.md").write_text("# The readme\n")
    (workspace / "src").mkdir()
    (workspace / "src" / "app.py").write_text("x = 1\n")
    (workspace / ".gitignore").write_text(".stand-in/\n.hmz/\n.humanize/\n")
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-q", "-m", "first")
    return workspace


def _editor_has_the_keys(app: Humanize) -> bool:
    return getattr(app.focused, "id", "") == "editor"


def _rows(pane: FilesPane | ChangesPane) -> list[str]:
    listing = pane.query_one("#pane-list", OptionList)
    return [str(one.id) for one in listing.options if not one.disabled]


async def _onto(pilot: Pilot[None], pane: FilesPane | ChangesPane, ending: str) -> None:
    """Puts the cursor of a pane's list on the row whose id ends as given."""
    await until(
        pilot,
        lambda: any(one.endswith(ending) for one in _rows(pane)),
        f"the row {ending!r}",
    )
    listing = pane.query_one("#pane-list", OptionList)
    listing.highlighted = next(
        at
        for at, one in enumerate(listing.options)
        if str(one.id).endswith(ending) and not one.disabled
    )
    await pilot.pause()


async def _chatting(pilot: Pilot[None]) -> None:
    """Says one thing to the stand-in, so that the chat and its environment are open."""
    await opened(pilot)
    await typed(pilot, "hello")
    await shows(pilot, "heard hello", "◉ Done")


async def test_a_file_is_read_beside_the_chat_and_esc_gives_the_prompt_the_keys_back(
    workspace: Path,
) -> None:
    del workspace
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await _chatting(pilot)
        context = app.query_one("#context", Zone)
        assert not context.has_class("open")

        await pilot.press("f5")
        await until(pilot, lambda: bool(app.query(FilesPane)), "the pane")
        pane = app.query_one(FilesPane)
        await _onto(pilot, pane, "/README.md")
        drawn = screen(app)
        assert "FILES" in drawn
        assert "src/" in drawn
        # Beside the chat, which is still on the screen.
        assert "heard hello" in drawn

        await pilot.press("enter")
        await shows(pilot, "# The readme")
        assert pane.reading.endswith("/README.md")

        await pilot.press("escape")
        await until(pilot, lambda: _editor_has_the_keys(app), "the prompt")
        assert context.has_class("open")
        assert "# The readme" in screen(app)

        # And the chat goes on with the file still open beside it.
        await typed(pilot, "again")
        await shows(pilot, "heard again", "# The readme")


async def test_a_change_is_staged_and_committed_from_the_pane(workspace: Path) -> None:
    (workspace / "src" / "app.py").write_text("x = 2\n")
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await _chatting(pilot)

        await pilot.press("f6")
        await until(pilot, lambda: bool(app.query(ChangesPane)), "the pane")
        pane = app.query_one(ChangesPane)
        await _onto(pilot, pane, "src/app.py")
        drawn = await shows(pilot, "CHANGES", "Changes (1)", "+x = 2")
        assert "-x = 1" in drawn
        assert "main" in drawn

        await pilot.press("s")
        await shows(pilot, "Staged Changes (1)")
        assert "M  src/app.py" in _git(workspace, "status", "--porcelain")

        await pilot.press("c")
        form = await on(pilot, Commit)
        await pilot.press(*"second", "enter")
        form.action_done()
        await until(
            pilot,
            lambda: "second" in _git(workspace, "log", "--format=%s"),
            "the commit",
        )
        await shows(pilot, "No changes")
        assert _git(workspace, "status", "--porcelain") == ""

        await pilot.press("l")
        await shows(pilot, "second", "first")

        await pilot.press("escape")
        await until(pilot, lambda: _editor_has_the_keys(app), "the prompt")
        assert app.query_one("#context", Zone).has_class("open")


async def test_a_shell_in_the_pane_runs_a_command_and_tilde_dot_then_esc_leaves_it(
    workspace: Path,
) -> None:
    del workspace
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await _chatting(pilot)

        await pilot.press("f7")
        await until(pilot, lambda: isinstance(app.focused, Tty), "a terminal")
        tty = app.query_one(TerminalPane).tty
        assert tty is not None
        await until(pilot, lambda: bool(tty.term), "it to open")

        # Typed as two words, so that what is waited for is what it printed, not the echo.
        await pilot.press(*"echo pane-$((40+2))", "enter")
        await until(pilot, lambda: "pane-42" in tty.text, "what echo printed")
        assert "TERMINAL" in screen(app)
        assert "pane-42" in screen(app)

        # `tab` and the arrows are the log's keys elsewhere; here they are the shell's.
        await pilot.press(*"cat -v", "enter", "tab", "left", "enter")
        await until(pilot, lambda: "^[[D" in tty.text, "the tab and the arrow typed")
        assert getattr(app.focused, "id", "") != "editor"
        await pilot.press("ctrl+d")

        await pilot.press("enter", "~", ".")
        await until(pilot, lambda: not isinstance(app.focused, Tty), "the keys back")
        await pilot.press("escape")
        await until(pilot, lambda: _editor_has_the_keys(app), "the prompt")
        assert app.query_one("#context", Zone).has_class("open")
        assert "pane-42" in screen(app)

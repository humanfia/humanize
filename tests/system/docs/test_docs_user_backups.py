"""The pictures of `docs/user/backups.md`: epics backed up to git, and brought back.

A backup target is added in the app; an epic's targets are picked on the New epic form; an
epic is uploaded by hand; what a target holds is listed and one epic of another machine is
downloaded, in the app, in the terminal interface and on the command line. Run it by naming
it: `uv run pytest tests/system/docs/test_docs_user_backups.py`.

Nothing is pushed off this machine. The targets are written as `git@github.com:alex/…`, which
is what every interface shows, and the made-up home's own git config sends that to bare
repositories under the scene's temporary directory (`url.<base>.insteadOf`), so the pushes
and fetches are git's own. The epic "of another machine" is one of this world's, moved in the
repository under `gpu-box/` with its paths rewritten, and taken off this machine.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from typing import TYPE_CHECKING, Any

from playwright.sync_api import expect

from tests.integration.doubles_tui import onto, opens, shows
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Page

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-backups"

#: The targets, as settings name them, and where each is said to be.
_LAB = "lab"
_OFFSITE = "offsite"
_URLS = {
    _LAB: "git@github.com:alex/epics.git",
    _OFFSITE: "git@github.com:alex/epics-offsite.git",
}

#: The other machine whose epic the target holds, and where the project is there.
_AWAY = "gpu-box"
_THERE = "/srv/shop"

_TASK = "Add a discount code to checkout"
_OTHER = "Fix the flaky cart test"
_CHAT = "Where is the total rounded?"

_SAID = {
    "discount": "Checkout takes a discount code now: WELCOME10 is 10% off. The tests pass.",
    "flaky": "The cart test no longer depends on the clock. It passed 50 times in a row.",
    "rounded": "In shop/cart.py, total() rounds once, after the discount is taken off.",
}

#: How long a backup is waited for.
_PATIENCE = 60.0


def _git(at: Path, *argv: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=Alex Kim", "-c", "user.email=alex@example.com", *argv],
        cwd=at,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout


def _remotes(world: World) -> Path:
    """Makes the repositories the targets push to, and has git reach them by their URLs."""
    base = world.home.parent / "remote"
    base.mkdir()
    for url in _URLS.values():
        name = url.rsplit("/", 1)[-1]
        _git(base, "init", "-q", "--bare", "-b", "main", name)
    (world.home / ".gitconfig").write_text(
        f'[url "{base}/"]\n\tinsteadOf = git@github.com:alex/\n'
    )
    return base


def _targets(world: World, *names: str) -> None:
    """Writes targets into settings: `lab` after each epic and a default, `offsite` by hand."""
    world.call(
        "settings.set",
        backup={
            "targets": [
                {
                    "name": one,
                    "url": _URLS[one],
                    "branch": "main",
                    "policies": ["end"] if one == _LAB else [],
                    "every": 30,
                }
                for one in names
            ],
            "defaults": [_LAB] if _LAB in names else [],
        },
    )


def _backed(world: World, name: str, target: str = _LAB) -> None:
    """Waits until an epic says its backup to a target went through."""
    deadline = time.monotonic() + _PATIENCE
    said: Any = None
    while time.monotonic() < deadline:
        said = world.call("runs.get", name=name).get("backed") or {}
        if said.get(target, {}).get("ok"):
            return
        time.sleep(0.3)
    raise AssertionError(f"{name} was never backed up to {target}: {said}")


def _staged(world: World, *, away: bool = True, chat: bool = False) -> tuple[str, str]:
    """Two targets, an epic backed up from here, and one the target holds of another machine.

    Returns:
      The name of the epic that is here, and the name of the one that is not.
    """
    base = _remotes(world)
    _targets(world, _LAB, _OFFSITE)
    world.says(_SAID)
    there = world.epic("goal", _OTHER)
    _backed(world, there)
    here = world.epic("goal", _TASK)
    _backed(world, here)
    if chat:
        _chatted(world, base / "epics.git")
    if away:
        _moved(world, base / "epics.git", there)
    return here, there


def _chatted(world: World, remote: Path) -> None:
    """Holds a chat and backs it up by hand, as Upload in its menu does."""
    chat = world.chat(_CHAT)
    world.call("chat.backup", chat=chat)
    deadline = time.monotonic() + _PATIENCE
    while chat not in _git(remote, "log", "--format=%s", "main"):
        assert time.monotonic() < deadline, "the chat was never backed up"
        time.sleep(0.3)


def _moved(world: World, remote: Path, name: str) -> None:
    """Has one epic be another machine's: moved in the repository, and gone from this one."""
    clone = remote.parent / "moving"
    _git(remote.parent, "clone", "-q", str(remote), str(clone))
    was = next(clone.glob(f"*/*/{name}"))
    now = clone / _AWAY / _THERE.replace("/", "-") / name
    now.parent.mkdir(parents=True)
    was.rename(now)
    for one in now.rglob("*"):
        if one.is_file():
            text = one.read_text()
            for path in (str(world.workspace.resolve()), str(world.workspace)):
                text = text.replace(path, _THERE)
            one.write_text(text.replace('"studio"', f'"{_AWAY}"'))
    _git(clone, "add", "-A")
    _git(clone, "commit", "-q", "-m", f"Back up epic {name} (end)")
    _git(clone, "push", "-q", "origin", "HEAD:refs/heads/main")
    shutil.rmtree(clone)
    for one in (world.home / ".hmz").rglob(name):
        if one.is_dir() and "backup" not in one.parts:
            shutil.rmtree(one)


def _settled(page: Page) -> None:
    """Waits for the page behind the settings to have read what a new chat would start."""
    go(page, "/new/chat")
    expect(page.get_by_role("button", name=re.compile("Nous: .*Haiku"))).to_be_visible()


def test_a_target_is_added_in_the_app(world: World) -> None:
    _remotes(world)
    with world.page(desktop=True) as page:
        _settled(page)
        go(page, "/settings/backup")
        add = page.get_by_role("button", name="Add target")
        expect(add).to_be_visible()
        page.wait_for_timeout(600)
        reel = shots.Reel(f"{_PAGE}-add", window="desktop")
        reel.web(page, hold=1.6, pointer=add, click=True)
        add.click()
        reel.type(page, page.locator("#backup-name"), _LAB)
        reel.type(page, page.locator("#backup-url"), _URLS[_LAB], per=10)
        end = page.locator("[data-policy=end]")
        reel.web(page, hold=0.9, pointer=end, click=True)
        end.check()
        save = page.get_by_role("button", name="Save")
        reel.web(page, hold=1.1, pointer=save, click=True)
        save.click()
        row = page.locator("[data-hmz=backup-target]")
        expect(row).to_contain_text("On epic end")
        default = row.locator("[data-hmz=backup-default]")
        reel.web(page, hold=1.4, pointer=default, click=True)
        default.check()
        expect(default).to_be_checked()
        page.wait_for_timeout(500)
        reel.web(page, hold=3.5, poster=True)
        reel.save()


def test_the_targets_and_an_epics_own_in_the_app(world: World) -> None:
    _staged(world)
    with world.page(desktop=True) as page:
        _settled(page)
        go(page, "/settings/backup")
        expect(page.locator("[data-hmz=backup-target]")).to_have_count(2)
        page.wait_for_timeout(600)
        shots.web(page, f"{_PAGE}-settings", window="desktop")

        go(page, "/new?flow=goal")
        expect(page.locator("[data-hmz=backup]")).to_be_visible()
        page.wait_for_timeout(600)
        shots.web(page, f"{_PAGE}-new-epic", window="desktop")


def test_an_epic_is_uploaded_in_the_app(world: World) -> None:
    here, _ = _staged(world, away=False)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{here}")
        upload = page.locator("[data-hmz=upload]")
        expect(upload).to_be_visible()
        page.wait_for_timeout(800)
        reel = shots.Reel(f"{_PAGE}-upload", window="desktop")
        reel.web(page, hold=1.8, pointer=upload, click=True)
        upload.click()
        expect(page.get_by_text(f"Uploading to {_LAB}")).to_be_visible()
        reel.web(page, hold=3.5, poster=True)
        reel.save()


def test_an_epic_is_downloaded_in_the_app(world: World) -> None:
    _staged(world)
    with world.page(desktop=True) as page:
        _settled(page)
        go(page, "/settings/backup")
        link = page.locator("[data-hmz=download]")
        expect(link).to_be_visible()
        page.wait_for_timeout(600)
        reel = shots.Reel(f"{_PAGE}-download", window="desktop")
        reel.web(page, hold=1.5, pointer=link, click=True)
        link.click()
        expect(page.locator("[data-hmz=stored-epic]")).to_have_count(2)
        bring = page.get_by_role("button", name="Download", exact=True)
        page.wait_for_timeout(500)
        reel.web(page, hold=2.4, pointer=bring, click=True)
        bring.click()
        expect(page.get_by_role("heading", name=_OTHER).first).to_be_visible()
        page.wait_for_timeout(1200)
        reel.web(page, hold=3.5, poster=True)
        reel.save()


async def test_the_targets_in_the_terminal_interface(world: World) -> None:
    _staged(world)
    async with world.tui((100, 32)) as (app, pilot):
        await shows(pilot, MODEL)
        reel = shots.Reel(f"{_PAGE}-tui")
        await pilot.press(*"/settings backup", "enter")
        await shows(pilot, _LAB, _OFFSITE, "Download…")
        await pilot.pause(0.5)
        reel.tui(app, hold=2.4, keys="/settings backup")
        await opens(pilot, _LAB)
        await shows(pilot, "On epic end", "new epics go here")
        await pilot.pause(0.5)
        reel.tui(app, hold=3.5, keys="enter", poster=True)
        reel.save()

        await pilot.press("escape")
        await shows(pilot, "Download…")
        await pilot.click("#act-download")
        await shows(pilot, f"Download from {_LAB}", _AWAY)
        await pilot.pause(0.5)
        shots.tui(app, f"{_PAGE}-tui-download")


async def test_a_flows_targets_in_the_terminal_interface(world: World) -> None:
    _staged(world, away=False)
    async with world.tui((100, 26)) as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*"/flow goal", "enter")
        await shows(pilot, "backup")
        await onto(pilot, "\x1ebackup")
        await pilot.press("enter")
        await shows(pilot, _URLS[_OFFSITE])
        await pilot.pause(0.5)
        shots.tui(app, f"{_PAGE}-tui-flow")


def test_backing_up_and_downloading_from_the_command_line(world: World) -> None:
    here, there = _staged(world, chat=True)
    reel = shots.Reel(f"{_PAGE}-cli")
    for argv in (
        ["hmz", "backup", here],
        ["hmz", "backup", "--list", "--to", _LAB],
        ["hmz", "backup", "--pull", there],
    ):
        reel.cli(argv, columns=116, rows=8, hold=4.0)
    reel.save()

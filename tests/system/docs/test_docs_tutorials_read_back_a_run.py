"""The pictures of `docs/tutorials/read-back-a-run.md`: an epic read back, exported and shared.

One finished epic of the project, as the page tells it: opened from the sidebar and one of its
sessions read, its trace opened in Exomyth as a timeline and as a flame graph, what it spent
looked up in Usage, the epic exported as a `.hmzepic` and imported again, and a git repository
added as a backup target that the epic is uploaded to and listed from. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_tutorials_read_back_a_run.py`.

The backup repository is staged here: a bare repository made on this machine, where the staged
home's git is told `git@github.com:alex/` is, so that the interfaces name it as a person's own
on GitHub would be named and really push to it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Page

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "tutorials-read-back-a-run"

#: The epic the page reads back, and an earlier one beside it in the history.
_TASK = "Add a discount code to checkout"
_EARLIER = "Show prices with a currency symbol"

#: The backup target the page adds, and the repository it names.
_TARGET = "epics"
_REPO = "git@github.com:alex/epic-backups.git"

_CHECKOUT = '''"""Paying for a cart."""

from shop.cart import total

CODES = {"WELCOME10": 10}


def charge(items: dict[str, int], code: str = "") -> int:
    """What is charged for a cart, in cents, less what a code takes off."""
    owed = total(items)
    return owed - owed * CODES.get(code, 0) // 100
'''

#: What the actor does when told the task: reads, edits, tests, and says so.
_WORK = {
    "text": (
        "Checkout takes a discount code now: charge() looks the code up and takes its"
        " discount off the total. WELCOME10 is 10% off. Two new tests cover it, and all"
        " six pass."
    ),
    "tools": [
        {
            "name": "Read",
            "input": {"file_path": "shop/checkout.py"},
            "result": "def charge(items): ...",
            "takes": 0.7,
        },
        {
            "name": "Edit",
            "input": {"file_path": "shop/checkout.py"},
            "result": "edited",
            "takes": 1.1,
        },
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": "6 passed in 0.21s",
            "takes": 1.6,
        },
    ],
    "writes": {"shop/checkout.py": _CHECKOUT},
    "after": 0.9,
}

#: What the reviewer does with it: reads the diff, runs the tests, and passes it.
_REVIEW = {
    "json": {
        "done": True,
        "notes": "charge() takes a code and WELCOME10 takes 10% off. All six tests pass.",
    },
    "tools": [
        {
            "name": "Bash",
            "input": {"command": "git diff"},
            "result": "shop/checkout.py | 7 +++++--",
            "takes": 0.6,
        },
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": "6 passed in 0.21s",
            "takes": 1.2,
        },
    ],
    "after": 0.5,
}


def _ran(world: World) -> str:
    """Stages the history: an earlier epic, and the one the page reads back, both done."""
    world.says(
        {
            "meticulous reviewer": _REVIEW,
            "currency": "Prices are shown with a currency symbol now: $12.00.",
            "discount": _WORK,
        }
    )
    world.epic("goal", _EARLIER)
    return world.epic("rlar", _TASK)


def _remote(world: World) -> Path:
    """Stages the repository `_REPO` names: a bare one here, which the home's git goes to."""
    bare = world.home.parent / "remote" / "epic-backups.git"
    bare.parent.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    (world.home / ".gitconfig").write_text(
        "[user]\n\tname = Alex Kim\n\temail = alex@example.com\n"
        f'[url "{bare.parent}/"]\n\tinsteadOf = git@github.com:alex/\n'
    )
    return bare


def _open(page: Page, name: str) -> None:
    """Opens the epic's own page, drawn as an ended epic is."""
    go(page, f"/epics/{name}")
    expect(page.get_by_role("link", name="Resume").first).to_be_visible()
    expect(page.get_by_text("Reading handovers")).to_have_count(0)
    expect(page.locator(".side-scroll").get_by_text("Running")).to_have_count(0)


def _traced(page: Page, name: str) -> None:
    """Opens the epic's Exomyth once its trace holds every session's log, the reviewer's too.

    A trace read the instant the epic ended can come before its last session's log is whole,
    and still say the epic is running: it is opened again until the reviewer's work is in it
    and the epic is said to be done.
    """
    _open(page, name)
    deadline = time.monotonic() + 60
    while True:
        go(page, f"/epics/{name}/exomyth")
        page.wait_for_function("() => window.__exomyth && window.__exomyth.model()")
        whole = page.evaluate(
            """() => {
              const model = window.__exomyth.model()
              return model.tracks.some((track) =>
                Array.from(track.name_, (at) => model.strings[at]).includes('Bash: git diff'))
            }"""
        )
        if whole and page.locator("[data-hmz=bar]").get_by_text("done").count():
            return
        assert time.monotonic() < deadline, "the trace never held the reviewer's work"
        go(page, f"/epics/{name}")
        page.wait_for_timeout(1000)


def _span(page: Page, name: str) -> dict[str, float]:
    """Where on the page the first span of a name is drawn in the timeline."""
    at = page.evaluate(
        """(name) => {
          const model = window.__exomyth.model()
          for (const track of model.tracks)
            for (let i = 0; i < track.count; i++)
              if ((model.strings[track.name_[i]] || '').includes(name))
                return window.__exomyth.where(track.first + i)
          return null
        }""",
        name,
    )
    assert at, f"the timeline has no span named {name!r}"
    return at


def test_the_epic_is_opened_from_the_sidebar_and_a_session_read(world: World) -> None:
    name = _ran(world)
    with world.page(desktop=True) as page:
        _open(page, name)
        shots.web(page, f"{_PAGE}-epic", window="desktop", most=shots.REEL)

        go(page, "/new/chat")
        expect(page.get_by_role("textbox", name="First message")).to_be_visible()
        reel = shots.Reel(f"{_PAGE}-session", window="desktop")
        row = page.locator(".side-scroll").get_by_text(_TASK[:18]).first
        reel.web(page, hold=1.4, pointer=row, click=True)
        row.click()
        expect(page.get_by_role("link", name="Resume").first).to_be_visible()
        expect(page.get_by_text("Reading handovers")).to_have_count(0)
        session = page.locator("[data-hmz=graph-session]").first
        expect(session).to_be_visible()
        reel.web(page, hold=1.8, pointer=session, click=True)
        session.click()
        expect(page.get_by_role("log")).to_contain_text("WELCOME10")
        reel.web(page, hold=4.5, poster=True)
        reel.save()


def test_the_trace_is_read_as_a_timeline_and_as_a_flame_graph(world: World) -> None:
    name = _ran(world)
    with world.page(desktop=True) as page:
        _traced(page, name)
        at = _span(page, "Edit: shop/checkout.py")
        page.mouse.click(at["x"], at["y"])
        expect(page.locator("[data-hmz=exomyth-span-name]")).to_contain_text("Edit")
        shots.web(page, f"{_PAGE}-trace", window="desktop", most=shots.REEL)

        page.keyboard.press("Escape")
        page.get_by_role("tab", name="Flame").click()
        expect(page.get_by_text("Slices")).to_be_visible()
        page.wait_for_function("() => window.__exomyth.flame()")
        shots.web(page, f"{_PAGE}-flame", window="desktop", most=shots.REEL)


def test_what_it_spent_is_read_in_usage(world: World) -> None:
    name = _ran(world)
    with world.page(desktop=True) as page:
        _open(page, name)
        # Settings open over the page they were opened from: a plain one, so the still is light.
        go(page, "/new/chat")
        expect(page.get_by_role("textbox", name="First message")).to_be_visible()
        go(page, "/settings/usage")
        expect(page.get_by_role("heading", name="By flow")).to_be_visible()
        expect(page.get_by_role("link", name="rlar", exact=True)).to_be_visible()
        shots.web(page, f"{_PAGE}-usage", window="desktop", most=shots.REEL)


def test_the_epic_is_exported_and_imported_again(world: World) -> None:
    name = _ran(world)
    downloads = world.home / "Downloads"
    downloads.mkdir()
    with world.page(desktop=True) as page:
        _open(page, name)
        bar = page.locator("[data-hmz=bar]")
        export = bar.get_by_role("button", name="Export")
        export.hover()
        page.wait_for_timeout(500)
        shots.web(page, f"{_PAGE}-export", clip=bar, pad=40, pointer=export)
        with page.expect_download() as saving:
            export.click()
        archive = downloads / saving.value.suggested_filename
        saving.value.save_as(archive)
    assert archive.name == f"{name}.hmzepic"

    # Another machine has the archive and not the epic: here, the epic is taken away.
    (kept,) = world.data.rglob(name)
    shutil.rmtree(kept)
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        expect(page.get_by_role("textbox", name="First message")).to_be_visible()
        expect(page.locator(".side-scroll").get_by_text(_TASK[:18])).to_have_count(0)
        reel = shots.Reel(f"{_PAGE}-import", window="desktop")
        search = page.get_by_role("link", name=re.compile("Search")).first
        reel.web(page, hold=1.3, pointer=search, click=True)
        search.click()
        button = page.locator("[data-hmz=import]")
        expect(button).to_be_visible()
        reel.web(page, hold=1.6, pointer=button, click=True)
        with page.expect_file_chooser() as picking:
            button.click()
        picking.value.set_files(archive)
        page.wait_for_url(re.compile(r".*#/epics/[^/?]+$"))
        expect(page.get_by_role("link", name="Resume").first).to_be_visible()
        expect(page.get_by_text("Reading handovers")).to_have_count(0)
        expect(
            page.locator(".side-scroll").get_by_text(_TASK[:18]).first
        ).to_be_visible()
        reel.web(page, hold=4.5, caption="the epic is here again", poster=True)
        reel.save()


def test_a_git_repository_is_added_and_the_epic_backed_up_to_it(world: World) -> None:
    bare = _remote(world)
    name = _ran(world)
    with world.page(desktop=True) as page:
        # Settings open over the page they were opened from: a plain one, so the reel is light.
        go(page, "/new/chat")
        expect(page.get_by_role("textbox", name="First message")).to_be_visible()
        go(page, "/settings/backup")
        add = page.get_by_role("button", name="Add target")
        expect(add).to_be_visible()
        reel = shots.Reel(f"{_PAGE}-target", window="desktop")
        reel.web(page, hold=1.4, pointer=add, click=True)
        add.click()
        box = page.locator("#backup-name")
        reel.type(page, box, _TARGET, per=5, rest=0.3)
        url = page.locator("#backup-url")
        reel.type(page, url, _REPO, per=18, rest=0.5)
        end = page.get_by_role("checkbox", name="On epic end")
        reel.web(page, hold=0.6, pointer=end, click=True)
        end.check()
        save = page.get_by_role("button", name="Save")
        reel.web(page, hold=0.9, pointer=save, click=True)
        save.click()
        listed = page.locator("[data-hmz=backup-target]")
        expect(listed).to_contain_text(_REPO)
        default = listed.get_by_role("checkbox", name="Default")
        reel.web(page, hold=1.2, pointer=default, click=True)
        default.check()
        expect(default).to_be_checked()
        reel.web(page, hold=4, poster=True)
        reel.save()

        page.keyboard.press("Escape")
        _open(page, name)
        upload = page.locator("[data-hmz=bar]").get_by_role("button", name="Upload")
        upload.click()
        expect(page.get_by_text(f"Uploading to {_TARGET}")).to_be_visible()
        shots.web(
            page, f"{_PAGE}-upload", window="desktop", pointer=upload, most=shots.REEL
        )

    # The push is the daemon's, made after it answered: the repository has it once it landed.
    deadline = time.monotonic() + 60
    while subprocess.run(
        ["git", "-C", str(bare), "rev-parse", "-q", "--verify", "main"],
        check=False,
        capture_output=True,
    ).returncode:
        assert time.monotonic() < deadline, "the epic was never pushed"
        time.sleep(0.2)
    shots.cli(
        ["hmz", "backup", "list", "--target", _TARGET],
        f"{_PAGE}-backup-list",
        columns=116,
    )

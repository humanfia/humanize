"""An environment's Changes panel, drawn by a real browser over a repository the page fakes.

The panel is mounted alone, as the environments frame mounts it, on a `ctx` whose `call`
answers `env.git.*` out of a repository held in the page: files with a HEAD, an index and a
worktree side each, staged, unstaged, discarded and committed as git would. The editor it draws
diffs with is CodeMirror, from `/vendor/codemirror.js`, the bundle the package ships.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlsplit

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, opened

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

    from playwright.sync_api import Locator, Page, Route

    from hmz.web.site import Site

pytestmark = [
    pytest.mark.parametrize("engine", ENGINES),
    pytest.mark.usefixtures("daemon"),
]

#: Mounts the panel on a repository held in the page, kept on `window.repo`.
_MOUNT = (Path(__file__).parent / "envs_changes_bench.js").read_text()


def _mounted(
    page: Page, *, caps: list[str], conflict: bool = False, refusal: str = ""
) -> None:
    page.evaluate(_MOUNT, {"caps": caps, "conflict": conflict, "refusal": refusal})
    expect(page.locator("[data-hmz=changes-branch]")).to_have_text("main")


def _group(page: Page, title: str) -> Locator:
    return page.locator("[data-hmz=changes-group]", has_text=title)


def _row(page: Page, group: str, path: str) -> Locator:
    return page.locator(f"[data-hmz=change][data-group={group}][data-path='{path}']")


def _counts(page: Page) -> dict[str, str]:
    said = page.evaluate(
        """() => Object.fromEntries(
          [...document.querySelectorAll('[data-hmz=changes-group]')].map((g) =>
            [g.dataset.group, g.querySelector('[data-hmz=changes-count]').textContent]))"""
    )
    return dict(said)


#: The page the panel is mounted on alone: the page's stylesheet, and a policy letting the
#: editor style what it draws and a stylesheet carry its own pictures, as the page's own does
#: (Section 4.5.5 of web.md).
_BENCH = (
    "<!doctype html><html lang=en data-theme=light><head><meta charset=utf-8>"
    "<title>Changes</title><link rel=stylesheet href=/style.css></head><body></body></html>"
)
_POLICY = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'"
)


def _through(route: Route) -> None:
    """A file of the page's, fetched from the interface and handed over as it came."""
    route.fulfill(response=route.fetch())


@contextlib.contextmanager
def _opened(site: Site, engine: str) -> Generator[Page]:
    """The page, then a bench of its own on the same interface to mount the panel on."""
    with opened(site, engine=engine) as page:
        # The bench is handed over by the test, and what a page so handed reaches is fetched
        # for it too: the browser lets such a page reach this machine's addresses no other way.
        page.route(
            lambda url: urlsplit(url).path.endswith((".js", ".css")),
            _through,
        )
        page.route(
            "**/changes_bench.html",
            lambda route: route.fulfill(
                body=_BENCH,
                content_type="text/html",
                headers={"Content-Security-Policy": _POLICY},
            ),
        )
        page.goto(urljoin(site.address, "/changes_bench.html"))
        yield page


@pytest.fixture
def site() -> Iterator[Site]:
    """The web interface the page is opened on."""
    with served() as one:
        yield one


def _shots(tmp_path: Path) -> Path:
    """Where a screenshot is kept: `HMZ_SHOTS` where set, to be looked at, else the test's own."""
    return Path(os.environ.get("HMZ_SHOTS") or tmp_path)


def test_groups_stage_unstage_discard_and_commit(
    site: Site, engine: str, tmp_path: Path
) -> None:
    with _opened(site, engine) as page:
        _mounted(page, caps=["files", "git"])
        expect(page.locator("[data-hmz=changes-sync]")).to_have_text("↑0↓2")
        assert _counts(page) == {"staged": "1", "changes": "2", "untracked": "2"}
        expect(
            _row(page, "changes", "src/app.py").locator("[data-hmz=change-letter]")
        ).to_have_text("M")
        expect(
            _row(page, "changes", "old.txt").locator("[data-hmz=change-letter]")
        ).to_have_text("D")
        expect(
            _row(page, "untracked", "notes/todo.txt").locator(
                "[data-hmz=change-letter]"
            )
        ).to_have_text("?")

        # Staging a file moves it to Staged Changes; unstaging it moves it back.
        row = _row(page, "changes", "src/app.py")
        row.hover()
        row.locator("[data-act=stage]").click()
        expect(_row(page, "staged", "src/app.py")).to_be_visible()
        assert _counts(page) == {"staged": "2", "changes": "1", "untracked": "2"}
        staged = _row(page, "staged", "src/app.py")
        staged.hover()
        staged.locator("[data-act=unstage]").click()
        expect(_row(page, "changes", "src/app.py")).to_be_visible()
        expect(_row(page, "staged", "src/app.py")).to_have_count(0)

        # Discarding asks first, and an untracked file is said to be deleted.
        page.evaluate("() => { window.repo.answer = false }")
        todo = _row(page, "untracked", "notes/todo.txt")
        todo.hover()
        todo.locator("[data-act=discard]").click()
        expect(todo).to_be_visible()
        asked = page.evaluate("() => window.repo.asked.at(-1)")
        assert "Delete the untracked file todo.txt" in asked
        page.evaluate("() => { window.repo.answer = true }")
        old = _row(page, "changes", "old.txt")
        old.hover()
        old.locator("[data-act=discard]").click()
        expect(old).to_have_count(0)
        assert "Discard the changes to old.txt" in page.evaluate(
            "() => window.repo.asked.at(-1)"
        )

        # Opening a file asks the frame for the Files panel.
        app = _row(page, "changes", "src/app.py")
        app.hover()
        app.locator("[data-act=open]").click()
        assert page.evaluate("() => window.repo.opened") == [
            ["files", {"path": "/work/src/app.py"}]
        ]

        # A right click offers the same in a menu, what cannot be undone last; a second one
        # on another row leaves one menu open, that row's, and Escape shuts it.
        app.click(button="right")
        menu = page.get_by_role("menu")
        expect(menu).to_have_count(1)
        assert menu.get_by_role("menuitem").all_inner_texts() == [
            "Open File",
            "Stage Changes",
            "Discard Changes",
        ]
        _row(page, "untracked", "logo.png").click(button="right", force=True)
        expect(menu).to_have_count(1)
        assert menu.get_by_role("menuitem").all_inner_texts() == [
            "Open File",
            "Stage Changes",
            "Delete File",
        ]
        page.keyboard.press("Escape")
        expect(menu).to_have_count(0)
        assert page.evaluate("() => window.repo.asked.length") == 2

        # Keyboard: Space stages what is picked, Shift+Down picks a run.
        _row(page, "untracked", "logo.png").click()
        page.keyboard.press("Shift+ArrowDown")
        page.keyboard.press("Space")
        expect(_row(page, "staged", "notes/todo.txt")).to_be_visible()
        assert _counts(page) == {"staged": "3", "changes": "1"}

        # A commit takes the staged changes, and empties the box.
        message = page.locator("[data-hmz=commit-message]")
        message.fill("Change the app")
        message.press("Control+Enter")
        expect(_group(page, "Staged Changes")).to_have_count(0)
        expect(message).to_have_value("")
        page.locator("[data-hmz=commits] summary").click()
        expect(page.locator("[data-hmz=commit-row]").first).to_contain_text(
            "Change the app"
        )
        expect(page.locator("[data-hmz=commit-row]").nth(1)).to_contain_text(
            "3 hours ago"
        )

        # Nothing staged: committing offers to stage everything first.
        message.fill("Add notes")
        page.locator("[data-hmz=changes-commit]").click()
        expect(page.locator("[data-hmz=change]")).to_have_count(0)
        assert "There are no staged changes" in page.evaluate(
            "() => window.repo.asked.at(-1)"
        )
        expect(page.locator("[data-hmz=changes-none]")).to_be_visible()
        page.screenshot(path=str(_shots(tmp_path) / f"changes-empty-{engine}.png"))


def test_diff_side_by_side_and_inline(site: Site, engine: str, tmp_path: Path) -> None:
    with _opened(site, engine) as page:
        _mounted(page, caps=["files", "git"])
        _row(page, "changes", "src/app.py").click()
        side = page.locator("[data-hmz=diff-side]")
        expect(side).to_be_visible()
        expect(side.locator(".cm-editor")).to_have_count(2)
        expect(side.locator(".cm-changedLine").first).to_be_visible()
        expect(page.locator("[data-hmz=diff-counter]")).to_have_text("\u2013 of 2")
        page.locator("[data-hmz=diff-next]").click()
        expect(page.locator("[data-hmz=diff-counter]")).to_have_text("1 of 2")
        page.keyboard.press("F7")
        expect(page.locator("[data-hmz=diff-counter]")).to_have_text("2 of 2")
        # Flat: nothing drawn here, the editor included, casts a shadow.
        assert (
            page.evaluate(
                """() => [...document.querySelectorAll('*')]
                  .filter((el) => getComputedStyle(el).boxShadow !== 'none')
                  .map((el) => `${el.tagName}.${el.className}`)"""
            )
            == []
        )
        page.screenshot(path=str(_shots(tmp_path) / f"changes-diff-{engine}.png"))

        page.locator("[data-hmz=diff-mode]").click()
        inline = page.locator("[data-hmz=diff-inline]")
        expect(inline).to_be_visible()
        expect(inline.locator(".cm-deletedChunk", has_text="return 1")).to_be_visible()

        # A binary file says so instead.
        _row(page, "untracked", "logo.png").click()
        expect(page.locator("[data-hmz=diff-notice]")).to_contain_text("binary")

        # A staged file's diff is the index against HEAD.
        _row(page, "staged", "README.md").click()
        expect(page.locator("[data-hmz=diff-inline]")).to_contain_text("More words.")
        calls = page.evaluate(
            "() => window.repo.calls.filter(([m]) => m === 'env.git.diff').at(-1)"
        )
        assert calls == ["env.git.diff", {"path": "README.md", "staged": True}]


def test_conflicts_bar_the_commit_and_snapshots_are_gated(
    site: Site, engine: str
) -> None:
    with _opened(site, engine) as page:
        _mounted(page, caps=["files", "git"], conflict=True)
        assert _counts(page)["merge"] == "1"
        expect(page.locator("[data-hmz=changes-commit]")).to_be_disabled()
        expect(page.locator("[data-hmz=commit-reason]")).to_have_text(
            "Resolve the merge conflicts before committing."
        )
        expect(page.locator("[data-hmz=snapshots]")).to_have_count(0)

        _mounted(
            page,
            caps=["files", "git", "rewind"],
            refusal="coder is working here; stop it first",
        )
        page.locator("[data-hmz=snapshots] summary").click()
        expect(page.locator("[data-hmz=snapshot]")).to_have_count(2)
        page.locator("[data-hmz=snapshot]").first.get_by_role(
            "button", name="Rewind"
        ).click()
        expect(page.locator("[data-hmz=snapshots] .error")).to_have_text(
            "coder is working here; stop it first"
        )
        assert "reset to that snapshot" in page.evaluate(
            "() => window.repo.asked.at(-1)"
        )

        # A closed environment stays shown as last read, and offers nothing that changes it.
        # The read the rewind itself asked for is let finish first, so that the press on
        # Refresh below is what finds the environment closed.
        page.wait_for_function(
            """() => {
              const { calls, pending } = window.repo
              const after = calls.slice(calls.findLastIndex(([m]) => m === 'env.git.rewind'))
              return after.some(([m]) => m === 'env.git.snapshots') && pending === 0
            }"""
        )
        page.evaluate("() => { window.repo.closed = true }")
        page.locator("[data-hmz=changes-refresh]").click()
        expect(page.locator("[data-hmz=changes-closed]")).to_be_visible()
        expect(page.locator("[data-hmz=changes-commit]")).to_be_disabled()
        expect(page.get_by_role("button", name="Rewind").first).to_be_disabled()
        expect(page.locator("[data-hmz=change]").first).to_be_visible()


def test_the_tree_view_folds_folders(site: Site, engine: str) -> None:
    with _opened(site, engine) as page:
        _mounted(page, caps=["files", "git"])
        page.locator("[data-hmz=changes-view]").click()
        folder = page.locator(".ch-kind-dir[data-group=changes][data-path=src]")
        expect(folder).to_be_visible()
        expect(_row(page, "changes", "src/app.py")).to_be_visible()
        folder.click()
        expect(_row(page, "changes", "src/app.py")).to_have_count(0)
        expect(folder).to_have_attribute("aria-expanded", "false")

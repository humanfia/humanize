"""An environment's Files panel, driven in a real browser over an environment held in the page.

The panel is mounted by itself, as the environments frame mounts it, on a stand-in `ctx` that
answers the `env.*` files methods from files held in memory. Its editor is CodeMirror, which the
page imports from `/vendor/codemirror.js`: the test builds a small bundle of it with pnpm and
esbuild, and answers that address with it, so it is skipped where node and pnpm are not there.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, opened

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.sync_api import Page, Route

pytestmark = pytest.mark.parametrize("engine", ENGINES)

#: What the bundle is built of, each pinned.
_PACKAGES = {
    "codemirror": "6.0.1",
    "@codemirror/view": "6.36.2",
    "@codemirror/state": "6.5.2",
    "@codemirror/commands": "6.8.0",
    "@codemirror/search": "6.5.8",
    "@codemirror/merge": "6.8.0",
    "@codemirror/lang-python": "6.1.7",
    "@codemirror/lang-javascript": "6.2.2",
    "esbuild": "0.24.2",
}

#: `/vendor/codemirror.js` as the contract has it, with two languages and a theme of tokens.
_ENTRY = """
import { EditorView } from '@codemirror/view'
import { python } from '@codemirror/lang-python'
import { javascript } from '@codemirror/lang-javascript'
export { EditorView, keymap } from '@codemirror/view'
export { EditorState, Compartment } from '@codemirror/state'
export { basicSetup } from 'codemirror'
export { indentWithTab } from '@codemirror/commands'
export { search, openSearchPanel, gotoLine } from '@codemirror/search'
export { MergeView, unifiedMergeView } from '@codemirror/merge'
export function languageFor(name) {
  if (/\\.py$/.test(name)) return python()
  if (/\\.m?js$/.test(name)) return javascript()
  return null
}
export function themeFor({ dark }) {
  const own = { backgroundColor: 'var(--surface)', color: 'var(--ink)' }
  return EditorView.theme({ '&': own }, { dark })
}
"""

#: The stand-in `ctx`: an environment of a few files, each call kept in `window.fake.calls`.
_MOUNT = (Path(__file__).parent / "envs_files_ctx.js").read_text()


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    """CodeMirror, bundled as `/vendor/codemirror.js` serves it."""
    pnpm = shutil.which("pnpm")
    node = shutil.which("node")
    if not (pnpm and node):
        pytest.skip("node and pnpm are needed to bundle CodeMirror")
    where = tmp_path_factory.mktemp("codemirror")
    (where / "package.json").write_text(
        '{"name": "cm", "private": true, "dependencies": {'
        + ", ".join(f'"{name}": "{version}"' for name, version in _PACKAGES.items())
        + "}}"
    )
    (where / "entry.mjs").write_text(_ENTRY)
    installed = subprocess.run(
        [pnpm, "install", "--ignore-scripts", "--silent"],
        cwd=where,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "CI": "1"},
    )
    if installed.returncode:
        pytest.skip(f"CodeMirror could not be installed: {installed.stderr[-400:]}")
    subprocess.run(
        [
            node,
            "-e",
            (
                "require('esbuild').buildSync({entryPoints: ['entry.mjs'],"
                " bundle: true, format: 'esm', outfile: 'codemirror.js'})"
            ),
        ],
        cwd=where,
        check=True,
    )
    return (where / "codemirror.js").read_bytes()


def _mounted(page: Page) -> None:
    page.evaluate(_MOUNT)
    expect(
        page.locator("[data-hmz=files-tree] [data-path='/w/main.py']")
    ).to_be_visible()


def _calls(page: Page, method: str) -> list[dict[str, Any]]:
    return [
        params
        for called, params in page.evaluate("window.fake.calls")
        if called == method
    ]


def test_a_file_is_opened_edited_and_saved_and_a_conflict_offered(
    engine: str, bundle: bytes
) -> None:

    with served() as site, opened(site, engine=engine, routed=_routed(bundle)) as page:
        _mounted(page)

        # Opened from the explorer: a preview tab, highlighted as Python.
        page.locator("[data-hmz=files-tree] [data-path='/w/main.py']").click()
        tab = page.locator("[data-hmz=files-tab][data-path='/w/main.py']")
        expect(tab).to_have_class(re.compile("preview"))
        content = page.locator("[data-hmz=files-editor] .cm-content")
        expect(content).to_contain_text("def greet(name):")
        expect(page.locator("[data-hmz=files-language]")).to_have_text("Python")
        assert page.locator("[data-hmz=files-editor] .cm-line span").count() > 0

        # Edited: the tab is pinned, and written back a moment after the typing stops.
        page.locator("[data-hmz=files-editor] .cm-line").first.click()
        page.keyboard.press("Home")
        page.keyboard.type("# hello\n")
        expect(tab).not_to_have_class(re.compile("preview"))
        expect(page.locator("[data-hmz=files-saved]")).to_have_text("Saved")
        writes = _calls(page, "env.write")
        assert len(writes) == 1
        assert writes[0]["if_match"] == "e1"
        assert page.evaluate("window.fake.text('/w/main.py')").startswith(
            "# hello\ndef greet"
        )

        # Changed elsewhere, then edited here: the write is refused, and a banner offers
        # what to do.
        page.evaluate("window.fake.put('/w/main.py', 'theirs\\n')")
        content.click()
        page.keyboard.type("more ")
        banner = page.locator("[data-hmz=files-conflict]")
        expect(banner).to_be_visible()
        expect(tab).to_have_class(re.compile("conflict"))
        banner.locator("[data-hmz=files-compare]").click()
        expect(page.locator("[data-hmz=files-merge] .cm-mergeView")).to_be_visible()
        banner.locator("[data-hmz=files-reload]").click()
        expect(banner).to_have_count(0)
        expect(content).to_have_text("theirs")

        # Quick open, by a few letters of the name.
        page.locator("[data-hmz=files-editor] .cm-content").click()
        page.keyboard.press("Control+p")
        quick = page.locator("[data-hmz=files-quick-input]")
        expect(quick).to_be_focused()
        quick.fill("utl")
        expect(page.locator("[data-hmz=files-pick]").first).to_have_attribute(
            "data-path", "src/util.py"
        )
        expect(page.locator("[data-hmz=files-pick] mark").first).to_have_text("ut")
        quick.press("Enter")
        expect(page.locator("[data-hmz=files-tab].active")).to_have_attribute(
            "data-path", "/w/src/util.py"
        )
        expect(content).to_contain_text("def here():")

        # Searched: a result opens its file on its line, from another file.
        page.locator("[data-hmz=files-tab][data-path='/w/main.py']").click()
        page.locator("[data-hmz=files-side-search]").click()
        page.locator("[data-hmz=files-search-query]").fill("os")
        page.locator("[data-hmz=files-search-query]").press("Enter")
        expect(page.locator("[data-hmz=files-search-summary]")).to_have_text(
            re.compile("2 results in 1 file")
        )
        page.locator("[data-hmz=files-result][data-line='5']").click()
        expect(page.locator("[data-hmz=files-tab].active")).to_have_attribute(
            "data-path", "/w/src/util.py"
        )
        expect(page.locator("[data-hmz=files-position]")).to_have_text(
            re.compile(r"^Ln 5, Col 12")
        )
        page.screenshot(path=str(_shots() / f"envs_files_{engine}.png"))


def test_the_explorer_makes_renames_and_removes_files(
    engine: str, bundle: bytes
) -> None:

    with served() as site, opened(site, engine=engine, routed=_routed(bundle)) as page:
        _mounted(page)
        tree = page.locator("[data-hmz=files-tree]")

        # A new file, named in the tree, made only where there is none, and opened.
        page.locator("[data-hmz=files-new-file]").click()
        # Named once it is focused, its name picked out for typing over.
        expect(page.locator("[data-hmz=files-name]")).to_be_focused()
        page.locator("[data-hmz=files-name]").fill("notes.txt")
        page.locator("[data-hmz=files-name]").press("Enter")
        expect(tree.locator("[data-path='/w/notes.txt']")).to_be_visible()
        assert _calls(page, "env.write")[0] == {
            "path": "/w/notes.txt",
            "data": "",
            "if_match": "",
        }
        expect(page.locator("[data-hmz=files-tab].active")).to_have_attribute(
            "data-path", "/w/notes.txt"
        )

        # Renamed with F2: its tab follows.
        tree.locator("[data-path='/w/notes.txt']").click()
        tree.press("F2")
        # Named once it is focused, its name picked out for typing over.
        expect(page.locator("[data-hmz=files-name]")).to_be_focused()
        page.locator("[data-hmz=files-name]").fill("todo.txt")
        page.locator("[data-hmz=files-name]").press("Enter")
        expect(tree.locator("[data-path='/w/todo.txt']")).to_be_visible()
        expect(page.locator("[data-hmz=files-tab].active")).to_have_attribute(
            "data-path", "/w/todo.txt"
        )

        # Deleted with the Delete key: its tab closes.
        tree.locator("[data-path='/w/todo.txt']").click()
        tree.press("Delete")
        expect(tree.locator("[data-path='/w/todo.txt']")).to_have_count(0)
        expect(page.locator("[data-hmz=files-tab]")).to_have_count(0)

        # A binary file opens read-only, saying why.
        tree.locator("[data-path='/w/blob.bin']").click()
        expect(page.locator("[data-hmz=files-read-only]")).to_contain_text(
            "not UTF-8 text"
        )
        expect(page.locator("[data-hmz=files-saved]")).to_have_text("Read-only")

        # A folder opens and closes with the arrow keys.
        tree.locator("[data-path='/w/src']").click()
        expect(tree.locator("[data-path='/w/src/util.py']")).to_be_visible()
        tree.press("ArrowLeft")
        expect(tree.locator("[data-path='/w/src/util.py']")).to_have_count(0)
        tree.press("ArrowRight")
        expect(tree.locator("[data-path='/w/src/util.py']")).to_be_visible()


def _routed(bundle: bytes) -> Callable[[Page], object]:
    """Answers `/vendor/codemirror.js` with the bundle."""

    def vendor(route: Route) -> None:
        route.fulfill(
            status=200, body=bundle, content_type="text/javascript; charset=utf-8"
        )

    return lambda page: page.route(re.compile(r".*/vendor/codemirror\.js$"), vendor)


@pytest.fixture(autouse=True)
def _inline_styles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lets the page set inline styles, as CodeMirror does to what it draws.

    The vendored bundles' change to the page's policy (`style-src 'self' 'unsafe-inline'`)
    allows it; until that is the policy served, it is made so here.
    """
    import hmz.web.site

    policy: str = getattr(hmz.web.site, "_POLICY")  # noqa: B009
    if "'unsafe-inline'" not in policy:
        monkeypatch.setattr(
            hmz.web.site,
            "_POLICY",
            policy.replace("style-src 'self'", "style-src 'self' 'unsafe-inline'"),
        )


def _shots() -> Path:
    """Where a screenshot is left to be looked at: `HMZ_SHOTS`, else a temporary directory."""
    where = Path(
        os.environ.get("HMZ_SHOTS") or Path(tempfile.gettempdir()) / "hmz-shots"
    )
    where.mkdir(parents=True, exist_ok=True)
    return where
